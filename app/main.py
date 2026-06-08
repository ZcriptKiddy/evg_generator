from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from .auth import (
    COOKIE_NAME,
    create_session_token,
    get_auth_settings,
    read_session_token,
    require_auth,
    verify_login,
)

from .docx_engine import (
    DocumentTooLargeError,
    ImageMissingError,
    TemplateMissingError,
    analyze_docx_placeholders,
    render_docx,
)


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
HISTORY_DIR = BASE_DIR / "data" / "history"
WORK_DIR = BASE_DIR / "data" / "work"

TEMPLATE_CADENA = TEMPLATES_DIR / "Plantilla_Cadena.docx"
TEMPLATE_INFORME = TEMPLATES_DIR / "Plantilla_Informe.docx"
INFORME_UPPERCASE_KEYS = {
    "Txt_NombreMP",
    "Txt_Cargo_UnidadSolicitante",
    "Txt_UnidadSolicitante",
    "Txt_Municipio",
}

app = FastAPI(
    title="Generador de plantillas periciales",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/")
def index(request: Request):
    if read_session_token(request.cookies.get(COOKIE_NAME)) is None:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login")
def login_page(request: Request):
    if read_session_token(request.cookies.get(COOKIE_NAME)) is not None:
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/login")
async def login(
    username: str = Form(""),
    password: str = Form(""),
) -> RedirectResponse:
    if not verify_login(username, password):
        return RedirectResponse("/login?error=1", status_code=303)

    settings = get_auth_settings()
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="lax",
    )
    return response


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/api/me")
def me(session: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    return {"username": session["sub"], "email": session["email"]}


@app.get("/api/plantillas")
def plantillas(session: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    return {
        "templates": [_template_info(path) for path in _available_templates()],
        "defaults": {
            "cadena": TEMPLATE_CADENA.name,
            "informe": TEMPLATE_INFORME.name,
        },
    }


@app.post("/api/plantilla/analizar")
async def analizar_plantilla(
    session: dict[str, Any] = Depends(require_auth),
    template_file: UploadFile | None = File(None),
    template_id: str = Form(""),
) -> dict[str, list[str]]:
    work_dir = WORK_DIR / f"analizar-{uuid4().hex[:8]}"
    template_path: Path | None = None

    try:
        if template_file is not None and template_file.filename:
            _validate_template_upload(template_file)
            work_dir.mkdir(parents=True, exist_ok=True)
            template_path = work_dir / "plantilla_analizar.docx"
            with template_path.open("wb") as dst:
                shutil.copyfileobj(template_file.file, dst)
        else:
            template_path = _resolve_template(template_id, default_path=TEMPLATE_INFORME)

        return analyze_docx_placeholders(template_path)
    except TemplateMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@app.post("/api/generar/cadena")
async def generar_cadena(
    session: dict[str, Any] = Depends(require_auth),
    json_text: str = Form(""),
    json_file: UploadFile | None = File(None),
    template_id: str = Form(""),
    template_file: UploadFile | None = File(None),
) -> FileResponse:
    payload = await _read_payload(json_text=json_text, json_file=json_file)
    payload = {key: value for key, value in payload.items() if not key.startswith("Img_")}
    template_name = _validate_template_upload(template_file) if template_file is not None and template_file.filename else None
    template_path = None if template_name else _resolve_template(template_id, default_path=TEMPLATE_CADENA)
    return await _generate(
        kind="cadena",
        payload=payload,
        template_path=template_path,
        template_file=template_file,
        template_name=template_name,
    )


@app.post("/api/generar/informe")
async def generar_informe(
    session: dict[str, Any] = Depends(require_auth),
    json_text: str = Form(""),
    json_file: UploadFile | None = File(None),
    images_zip: UploadFile | None = File(None),
    template_id: str = Form(""),
) -> FileResponse:
    payload = await _read_payload(json_text=json_text, json_file=json_file)
    payload = _uppercase_fields(payload, INFORME_UPPERCASE_KEYS)
    if images_zip is not None and images_zip.filename and not images_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Por ahora el informe acepta ZIP. El PDF lo dejamos para una segunda fase.")

    return await _generate(
        kind="informe",
        payload=payload,
        template_path=_resolve_template(template_id, default_path=TEMPLATE_INFORME),
        images_zip=images_zip,
    )


@app.post("/api/generar/custom")
async def generar_custom(
    session: dict[str, Any] = Depends(require_auth),
    template_file: UploadFile = File(...),
    json_text: str = Form(""),
    json_file: UploadFile | None = File(None),
    images_zip: UploadFile | None = File(None),
) -> FileResponse:
    payload = await _read_payload(json_text=json_text, json_file=json_file)
    payload = _uppercase_fields(payload, INFORME_UPPERCASE_KEYS)
    template_name = _validate_template_upload(template_file)

    if images_zip is not None and images_zip.filename and not images_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="El archivo de imagenes debe ser un ZIP.")

    return await _generate(
        kind="custom",
        payload=payload,
        template_path=None,
        template_file=template_file,
        template_name=template_name,
        images_zip=images_zip,
    )


@app.get("/api/historial")
def historial(session: dict[str, Any] = Depends(require_auth)) -> list[dict[str, Any]]:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    for record_dir in HISTORY_DIR.iterdir():
        if not record_dir.is_dir():
            continue

        meta_path = record_dir / "meta.json"
        if not meta_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        output_path = record_dir / meta.get("document_file", "resultado.docx")
        meta["id"] = record_dir.name
        meta["exists"] = output_path.exists()
        meta["document_url"] = f"/api/historial/{record_dir.name}/documento"
        meta["json_url"] = f"/api/historial/{record_dir.name}/json"
        records.append(meta)

    return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)


@app.get("/api/historial/{record_id}/documento")
def descargar_documento(record_id: str, session: dict[str, Any] = Depends(require_auth)) -> FileResponse:
    record_dir = _record_dir(record_id)
    meta = _read_meta(record_dir)
    output_path = record_dir / meta.get("document_file", "resultado.docx")

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="No encontre el documento.")

    return FileResponse(
        output_path,
        filename=meta.get("download_name", output_path.name),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/historial/{record_id}/json")
def descargar_json(record_id: str, session: dict[str, Any] = Depends(require_auth)) -> FileResponse:
    record_dir = _record_dir(record_id)
    json_path = record_dir / "entrada.json"

    if not json_path.exists():
        raise HTTPException(status_code=404, detail="No encontre el JSON.")

    return FileResponse(json_path, filename=f"{record_id}_entrada.json", media_type="application/json")


async def _read_payload(*, json_text: str, json_file: UploadFile | None) -> dict[str, Any]:
    raw = json_text.strip()

    if json_file is not None and json_file.filename:
        contents = await json_file.read()
        raw = contents.decode("utf-8-sig").strip()

    if not raw:
        raise HTTPException(status_code=400, detail="Pega o sube un JSON.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON invalido: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="El JSON debe ser un objeto con variables Txt_ e Img_.")

    return payload


async def _generate(
    *,
    kind: str,
    payload: dict[str, Any],
    template_path: Path | None,
    images_zip: UploadFile | None = None,
    template_file: UploadFile | None = None,
    template_name: str | None = None,
) -> FileResponse:
    record_id = _new_record_id(kind)
    record_dir = HISTORY_DIR / record_id
    work_dir = WORK_DIR / record_id
    record_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    if template_file is not None and template_file.filename:
        template_path = work_dir / "plantilla_custom.docx"
        with template_path.open("wb") as dst:
            shutil.copyfileobj(template_file.file, dst)

    if template_path is None:
        raise HTTPException(status_code=400, detail="Sube una plantilla DOCX.")

    zip_path: Path | None = None
    if images_zip is not None and images_zip.filename:
        zip_path = work_dir / "imagenes.zip"
        with zip_path.open("wb") as dst:
            shutil.copyfileobj(images_zip.file, dst)

    placeholders = analyze_docx_placeholders(template_path)
    if kind == "cadena":
        placeholders["img"] = []
    missing = _missing_placeholders(payload, placeholders, has_images_zip=zip_path is not None)
    generation_status = "parcial" if missing["txt"] or missing["img"] else "completo"
    generation_hash = secrets.token_hex(4)
    render_payload = _payload_for_render(payload, placeholders, has_images_zip=zip_path is not None)

    json_path = record_dir / "entrada.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    output_name = _download_name(kind, payload, status=generation_status, generation_hash=generation_hash)
    document_file = output_name
    output_path = record_dir / document_file

    try:
        stats = render_docx(
            template_path=template_path,
            payload=render_payload,
            output_path=output_path,
            work_dir=work_dir,
            images_zip_path=zip_path,
        )
    except TemplateMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImageMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "template": template_name or template_path.name,
        "document_file": document_file,
        "download_name": output_name,
        "status": generation_status,
        "hash": generation_hash,
        "missing": missing,
        "size_bytes": stats.size_bytes,
        "size_mb": round(stats.size_bytes / 1024 / 1024, 2),
        "image_count": stats.image_count,
        "image_quality": stats.image_quality,
        "image_max_side": stats.image_max_side,
        "summary": _summary(payload),
    }
    (record_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return FileResponse(
        output_path,
        filename=output_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "X-Document-Status": generation_status,
            "X-Document-Hash": generation_hash,
            "X-Missing-Fields": quote(json.dumps(missing, ensure_ascii=False, separators=(",", ":"))),
        },
    )


def _available_templates() -> list[Path]:
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(
        (path for path in TEMPLATES_DIR.glob("*.docx") if path.is_file()),
        key=lambda path: path.name.lower(),
    )


def _template_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "id": path.name,
        "name": path.stem,
        "file_name": path.name,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _resolve_template(template_id: str, *, default_path: Path) -> Path:
    selected = template_id.strip()
    if not selected:
        return default_path

    if "/" in selected or "\\" in selected:
        raise HTTPException(status_code=400, detail="Plantilla invalida.")

    candidate = TEMPLATES_DIR / selected
    templates_dir = TEMPLATES_DIR.resolve()
    try:
        resolved_candidate = candidate.resolve(strict=False)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Plantilla invalida.") from exc

    if resolved_candidate.parent != templates_dir:
        raise HTTPException(status_code=400, detail="Plantilla invalida.")
    if candidate.suffix.lower() != ".docx" or not candidate.is_file():
        raise HTTPException(status_code=400, detail="No encontre la plantilla seleccionada.")

    return candidate


def _validate_template_upload(template_file: UploadFile) -> str:
    file_name = _upload_file_name(template_file.filename)
    if not file_name:
        raise HTTPException(status_code=400, detail="Sube una plantilla DOCX.")
    if Path(file_name).suffix.lower() != ".docx":
        raise HTTPException(status_code=400, detail="La plantilla debe ser un archivo .docx.")
    return file_name


def _upload_file_name(file_name: str | None) -> str:
    return (file_name or "").replace("\\", "/").split("/")[-1].strip()


def _missing_placeholders(
    payload: dict[str, Any],
    placeholders: dict[str, list[str]],
    *,
    has_images_zip: bool,
) -> dict[str, list[str]]:
    missing = {"txt": [], "img": []}

    for key in placeholders.get("txt", []):
        value = payload.get(key)
        if value is None or not str(value).strip() or str(value).strip() == "[Pendiente]":
            missing["txt"].append(key)

    for key in placeholders.get("img", []):
        if not has_images_zip or not _has_image_assignment(payload.get(key)):
            missing["img"].append(key)

    return missing


def _payload_for_render(
    payload: dict[str, Any],
    placeholders: dict[str, list[str]],
    *,
    has_images_zip: bool,
) -> dict[str, Any]:
    normalized = dict(payload)
    for key in placeholders.get("img", []):
        if not has_images_zip or not _has_image_assignment(normalized.get(key)):
            normalized[key] = []
    return normalized


def _has_image_assignment(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(isinstance(item, str) and item.strip() for item in value)
    return False


def _new_record_id(kind: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{kind}-{uuid4().hex[:8]}"


def _download_name(
    kind: str,
    payload: dict[str, Any],
    *,
    status: str | None = None,
    generation_hash: str | None = None,
) -> str:
    if kind in {"cadena", "informe", "custom"} and status and generation_hash:
        return f"{status}_{generation_hash}.docx"

    if kind == "cadena":
        base = payload.get("Txt_No_Carpeta") or payload.get("Txt_CarpetaInvestigacion") or "cadena"
    elif kind == "informe":
        base = payload.get("Txt_CarpetaInvestigacion") or payload.get("Txt_OficioInterno") or "informe"
    else:
        base = (
            payload.get("Txt_CarpetaInvestigacion")
            or payload.get("Txt_No_Carpeta")
            or payload.get("Txt_OficioInterno")
            or kind
        )

    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(base)).strip("_") or kind
    return f"{kind}_{safe}.docx"


def _summary(payload: dict[str, Any]) -> str:
    for key in ("Txt_CarpetaInvestigacion", "Txt_No_Carpeta", "Txt_OficioInterno", "Txt_NumeroOficio"):
        value = payload.get(key)
        if value:
            return f"{key}: {value}"
    return f"{len(payload)} variables"


def _uppercase_fields(payload: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    normalized = dict(payload)
    for key in keys:
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = value.upper()
    return normalized


def _record_dir(record_id: str) -> Path:
    if not re.match(r"^[A-Za-z0-9_.-]+$", record_id):
        raise HTTPException(status_code=400, detail="ID invalido.")

    record_dir = HISTORY_DIR / record_id
    if not record_dir.exists() or not record_dir.is_dir():
        raise HTTPException(status_code=404, detail="No encontre ese registro.")

    return record_dir


def _read_meta(record_dir: Path) -> dict[str, Any]:
    meta_path = record_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="No encontre los metadatos.")

    return json.loads(meta_path.read_text(encoding="utf-8"))

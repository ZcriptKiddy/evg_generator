from __future__ import annotations

import os
import threading
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "data" / "models" / "paddlex"
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(MODEL_DIR))
os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")

_engine: Any | None = None
_engine_lock = threading.Lock()
_predict_lock = threading.Lock()


def _get_engine() -> Any:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                from paddleocr import PaddleOCR

                _engine = PaddleOCR(
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=True,
                    text_rec_score_thresh=0.35,
                )
    return _engine


def _prepare_image(data: bytes) -> Any:
    import numpy as np

    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        longest_side = max(image.size)
        if longest_side > 1200:
            scale = 1200 / longest_side
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        elif longest_side < 1000:
            scale = min(3.0, 1000 / max(image.size))
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        image = ImageOps.autocontrast(image, cutoff=0.5)
        image = ImageEnhance.Sharpness(image).enhance(1.35)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=2))
        return np.asarray(image)


def recognize_region(data: bytes) -> dict[str, Any]:
    if not data:
        raise ValueError("La región seleccionada está vacía.")
    image = _prepare_image(data)
    with _predict_lock:
        results = list(
            _get_engine().predict(
                image,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
        )

    lines: list[str] = []
    scores: list[float] = []
    for result in results:
        payload = getattr(result, "json", {})
        if callable(payload):
            payload = payload()
        if isinstance(payload, str):
            import json

            payload = json.loads(payload)
        data_block = payload.get("res", payload) if isinstance(payload, dict) else {}
        texts = data_block.get("rec_texts", [])
        confidences = data_block.get("rec_scores", [])
        for position, value in enumerate(texts):
            text = str(value).strip()
            if not text:
                continue
            lines.append(text)
            if position < len(confidences):
                scores.append(float(confidences[position]))

    return {
        "text": "\n".join(lines),
        "lines": lines,
        "confidence": round(sum(scores) / len(scores), 4) if scores else None,
    }

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException, Request


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

COOKIE_NAME = "docx_session"
HASH_ALGORITHM = "pbkdf2_sha256"


@dataclass(frozen=True)
class AuthSettings:
    username: str
    email: str
    password_hash: str
    session_secret: str
    secure_cookie: bool
    session_max_age_seconds: int


def get_auth_settings() -> AuthSettings:
    settings = AuthSettings(
        username=os.getenv("APP_USER", "").strip(),
        email=os.getenv("APP_EMAIL", "").strip(),
        password_hash=os.getenv("APP_PASSWORD_HASH", "").strip(),
        session_secret=os.getenv("SESSION_SECRET", "").strip(),
        secure_cookie=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        session_max_age_seconds=int(os.getenv("SESSION_MAX_AGE_SECONDS", "28800")),
    )

    missing = [
        name
        for name, value in (
            ("APP_USER", settings.username),
            ("APP_EMAIL", settings.email),
            ("APP_PASSWORD_HASH", settings.password_hash),
            ("SESSION_SECRET", settings.session_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Faltan variables de seguridad en .env: " + ", ".join(missing))

    if len(settings.session_secret) < 40:
        raise RuntimeError("SESSION_SECRET debe tener al menos 40 caracteres.")

    return settings


def verify_login(username_or_email: str, password: str) -> bool:
    settings = get_auth_settings()
    identity = username_or_email.strip().lower()
    allowed = {settings.username.lower(), settings.email.lower()}
    return identity in allowed and verify_password(password, settings.password_hash)


def create_session_token() -> str:
    settings = get_auth_settings()
    now = int(time.time())
    payload = {
        "sub": settings.username,
        "email": settings.email,
        "iat": now,
        "exp": now + settings.session_max_age_seconds,
        "jti": secrets.token_urlsafe(16),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = _b64encode(payload_bytes)
    signature = _sign(encoded_payload, settings.session_secret)
    return f"{encoded_payload}.{signature}"


def read_session_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None

    settings = get_auth_settings()
    encoded_payload, signature = token.rsplit(".", 1)
    expected = _sign(encoded_payload, settings.session_secret)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None

    if payload.get("sub") != settings.username:
        return None

    return payload


def require_auth(request: Request) -> dict[str, Any]:
    session = read_session_token(request.cookies.get(COOKIE_NAME))
    if session is None:
        raise HTTPException(status_code=401, detail="Sesion no valida o expirada.")
    return session


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, expected_raw = encoded_hash.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError as exc:
        raise RuntimeError("APP_PASSWORD_HASH no tiene un formato valido.") from exc

    if algorithm != HASH_ALGORITHM:
        raise RuntimeError("APP_PASSWORD_HASH usa un algoritmo no soportado.")

    salt = _b64decode(salt_raw)
    expected = _b64decode(expected_raw)
    calculated = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(calculated, expected)


def hash_password(password: str, *, iterations: int = 260_000) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            HASH_ALGORITHM,
            str(iterations),
            _b64encode(salt),
            _b64encode(password_hash),
        ]
    )


def _sign(encoded_payload: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(signature)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)

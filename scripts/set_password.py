from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.auth import hash_password  # noqa: E402


ENV_PATH = ROOT_DIR / ".env"


def main() -> int:
    if not ENV_PATH.exists():
        print("No encontre .env")
        return 1

    password = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("Nueva contrasena: ")
    confirm = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Repite la contrasena: ")

    if password != confirm:
        print("Las contrasenas no coinciden.")
        return 1

    if len(password) < 16:
        print("Usa una contrasena de al menos 16 caracteres.")
        return 1

    new_hash = hash_password(password)
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    updated = False
    next_lines: list[str] = []

    for line in lines:
        if line.startswith("APP_PASSWORD_HASH="):
            next_lines.append(f"APP_PASSWORD_HASH={new_hash}")
            updated = True
        else:
            next_lines.append(line)

    if not updated:
        next_lines.append(f"APP_PASSWORD_HASH={new_hash}")

    ENV_PATH.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    print("Contrasena actualizada. Reinicia el servidor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Генерация bcrypt password.db для file-based auth Trino (FR-015, T6).

Читает TRINO_USER/TRINO_PASSWORD из окружения (I-7), пишет infra/trino/auth/password.db
(в git не попадает — .gitignore). Вызывается из `make up` до старта Trino.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import bcrypt


def main() -> int:
    user = os.environ.get("TRINO_USER")
    password = os.environ.get("TRINO_PASSWORD")
    if not user or not password:
        print(
            "gen_password: TRINO_USER/TRINO_PASSWORD не заданы — скопируй .env.example в .env",
            file=sys.stderr,
        )
        return 1
    out = Path(__file__).resolve().parent / "auth" / "password.db"
    out.parent.mkdir(parents=True, exist_ok=True)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()
    out.write_text(f"{user}:{hashed}\n", encoding="utf-8")
    out.chmod(0o600)
    print(f"gen_password: {out} готов (пользователь {user})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Создание первого администратора на сервере.

    BOOTSTRAP_ADMIN_PASSWORD=... python -m app.cli create-admin --login admin --name "Администратор"

Пароль берётся из переменной окружения или запрашивается без отображения; в аргументы командной
строки он не передаётся, чтобы не попасть в историю shell и список процессов.
"""

import argparse
import getpass
import os
import re
import sys

import psycopg

from app.config import load_settings
from app.security import hash_password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin")
    create.add_argument("--login", required=True)
    create.add_argument("--name", default="Администратор")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[a-z0-9_.]{3,32}", args.login):
        print("login must match [a-z0-9_.]{3,32}", file=sys.stderr)
        return 2
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    if not 10 <= len(password) <= 128:
        print("password length must be 10..128", file=sys.stderr)
        return 2

    with psycopg.connect(load_settings().database_url) as conn:
        cur = conn.execute(
            "insert into users (login, password_hash, full_name, role) values (%s, %s, %s, 'admin')"
            " on conflict (login) do nothing returning id",
            (args.login, hash_password(password), args.name),
        )
        created = cur.fetchone() is not None
    print("admin created" if created else "login already exists, nothing changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

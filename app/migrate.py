"""Применяет SQL-миграции из каталога migrations/ по порядку имён.

Запуск: python -m app.migrate  (DSN берётся из DATABASE_URL)
"""

from pathlib import Path

import psycopg

from app.config import load_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def apply_migrations(dsn: str) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "create table if not exists schema_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        done = {r[0] for r in conn.execute("select name from schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations(name) values (%s)", (path.name,))
            applied.append(path.name)
    return applied


if __name__ == "__main__":
    names = apply_migrations(load_settings().database_url)
    print("applied:", ", ".join(names) if names else "nothing new")

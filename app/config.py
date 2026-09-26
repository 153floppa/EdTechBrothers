"""Настройки читаются из окружения; секреты в коде и репозитории не хранятся."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_ttl_hours: int = 12
    max_body_bytes: int = 16 * 1024


def load_settings() -> Settings:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return Settings(
        database_url=url,
        session_ttl_hours=int(os.environ.get("SESSION_TTL_HOURS", "12")),
    )

"""Интеграционные тесты идут на отдельной тестовой PostgreSQL.

TEST_DATABASE_URL — пустая база только для тестов: схема public пересоздаётся перед каждым тестом.
"""

import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.migrate import apply_migrations
from app.security import hash_password

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/checkbalance_test")
PASSWORD = "correct-horse-42"


@pytest.fixture
def db() -> str:
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("drop schema public cascade")
        conn.execute("create schema public")
    apply_migrations(TEST_DSN)
    return TEST_DSN


@pytest.fixture
def client(db: str):
    app = create_app(Settings(database_url=db, session_ttl_hours=12))
    with TestClient(app) as c:
        yield c


def insert_user(dsn: str, login: str, role: str, password: str = PASSWORD) -> str:
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "insert into users (login, password_hash, full_name, role) values (%s, %s, %s, %s) returning id",
            (login, hash_password(password), login.title(), role),
        ).fetchone()
    return str(row[0])


def login(client: TestClient, login_name: str, password: str = PASSWORD) -> dict:
    r = client.post("/auth/login", json={"login": login_name, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def admin(client, db) -> dict:
    insert_user(db, "admin", "admin")
    return login(client, "admin")

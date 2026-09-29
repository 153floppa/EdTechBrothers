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


@pytest.fixture
def school(client, db, admin) -> dict:
    """Два преподавателя, два родителя, по ученику у каждой пары; на балансе первого — 5000 ₽."""
    ids = {
        "tutor_a": insert_user(db, "tutor_a", "tutor"),
        "tutor_b": insert_user(db, "tutor_b", "tutor"),
        "parent_a": insert_user(db, "parent_a", "parent"),
        "parent_b": insert_user(db, "parent_b", "parent"),
    }
    students = {}
    for suffix in ("a", "b"):
        r = client.post(
            "/students",
            headers=admin,
            json={
                "full_name": f"Ученик {suffix.upper()}",
                "grade": 11,
                "tutor_id": ids[f"tutor_{suffix}"],
                "parent_id": ids[f"parent_{suffix}"],
                "parent_phone": "+79990000000",
                "lesson_price": 2000,
            },
        )
        assert r.status_code == 201, r.text
        students[suffix] = r.json()["id"]
    r = client.post(f"/students/{students['a']}/payments", headers=admin, json={"amount": 5000, "external_id": "op-1"})
    assert r.status_code == 201, r.text
    return {
        "ids": ids,
        "student_a": students["a"],
        "student_b": students["b"],
        "admin": admin,
        "tutor_a": login(client, "tutor_a"),
        "tutor_b": login(client, "tutor_b"),
        "parent_a": login(client, "parent_a"),
        "parent_b": login(client, "parent_b"),
    }


def past(minutes: int = 90) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def future(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

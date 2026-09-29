"""SR-11: строгий разбор тела запроса."""

import pytest
from fastapi import HTTPException

from app.input import StrictModel, parse_strict


class Payment(StrictModel):
    amount: int
    external_id: str


def status_of(raw: bytes) -> int:
    with pytest.raises(HTTPException) as exc:
        parse_strict(raw, Payment)
    return exc.value.status_code


def test_valid_body_parsed():
    assert parse_strict(b'{"amount": 100, "external_id": "op-1"}', Payment).amount == 100


@pytest.mark.parametrize(
    "raw, code",
    [
        (b'{"amount": 100, "amount": -500, "external_id": "x"}', 400),  # повторный ключ
        (b'{"amount": 100, "external_id": "x", "student_id": "y"}', 422),  # лишнее поле
        (b'{"Amount": 100, "external_id": "x"}', 422),  # неверный регистр ключа
        (b'{"amount": "100", "external_id": "x"}', 422),  # строка вместо числа
        (b'{"amount": 100.5, "external_id": "x"}', 422),  # дробь вместо целого
        (b'{"amount": NaN, "external_id": "x"}', 400),
        (b'{"amount": 100, "external_id": "x"} {}', 400),  # два JSON-значения
        (b"[1, 2]", 422),
        (b'{"amount": 100, "external_id": "\xff"}', 400),  # не UTF-8
        (b"", 400),
    ],
)
def test_rejected_bodies(raw, code):
    assert status_of(raw) == code


def test_validation_error_does_not_echo_values():
    with pytest.raises(HTTPException) as exc:
        parse_strict(b'{"amount": "secret-value", "external_id": "x"}', Payment)
    assert "secret-value" not in str(exc.value.detail)


def test_api_rejects_wrong_content_type_and_oversized_body(client):
    r = client.post("/auth/login", content=b"login=a&password=b", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    big = b'{"login": "admin", "password": "' + b"a" * 20000 + b'"}'
    r = client.post("/auth/login", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_login_with_extra_role_field_rejected(client):
    r = client.post("/auth/login", json={"login": "admin", "password": "x" * 12, "role": "admin"})
    assert r.status_code == 422

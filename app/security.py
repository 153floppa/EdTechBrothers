"""Секреты: хеши паролей и токены сессий (D-01, SR-03).

- Пароль хранится только как argon2id-хеш.
- Токен сессии — 256 бит из криптографического ГСЧ; в БД попадает только его SHA-256.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()  # argon2id с параметрами библиотеки по умолчанию
# Хеш-«пустышка»: проверяется при неизвестном логине, чтобы время ответа не выдавало,
# существует ли логин (SR-04).
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_dummy_verification(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()

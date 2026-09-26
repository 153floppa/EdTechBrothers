"""Вход, выход, текущий пользователь и учётные записи (D-01).

Субъект запроса определяется только по действующей серверной сессии (SR-01):
роль и идентификатор пользователя из тела или параметров запроса не принимаются.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field

from app.db import tx
from app.input import StrictModel, json_body
from app.security import (
    burn_dummy_verification,
    hash_password,
    new_session_token,
    token_digest,
    verify_password,
)

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)

Login = Annotated[str, Field(pattern=r"^[a-z0-9_.]{3,32}$")]
Password = Annotated[str, Field(min_length=10, max_length=128)]
FullName = Annotated[str, Field(min_length=1, max_length=100)]


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    login: str
    full_name: str
    role: str


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="unauthorized", headers={"WWW-Authenticate": "Bearer"})


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> CurrentUser:
    if cred is None:
        raise _unauthorized()
    with tx() as conn:
        row = conn.execute(
            """
            select u.id, u.login, u.full_name, u.role
            from sessions s join users u on u.id = s.user_id
            where s.token_hash = %s
              and s.revoked_at is null
              and s.expires_at > now()
              and u.is_active
            """,
            (token_digest(cred.credentials),),
        ).fetchone()
    if row is None:
        raise _unauthorized()
    return CurrentUser(**row)


def require_role(*roles: str):
    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="forbidden for this role")
        return user

    return dependency


class LoginIn(StrictModel):
    login: Login
    password: Password


class LoginOut(StrictModel):
    token: str
    expires_at: datetime
    role: str


@router.post("/auth/login", response_model=LoginOut)
def login(request: Request, body: LoginIn = Depends(json_body(LoginIn))) -> LoginOut:
    ttl_hours = request.app.state.settings.session_ttl_hours
    with tx() as conn:
        user = conn.execute(
            "select id, password_hash, role from users where login = %s and is_active",
            (body.login,),
        ).fetchone()
        if user is None:
            burn_dummy_verification(body.password)
            raise HTTPException(status_code=401, detail="invalid credentials")
        if not verify_password(user["password_hash"], body.password):
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = new_session_token()
        row = conn.execute(
            "insert into sessions (token_hash, user_id, expires_at)"
            " values (%s, %s, now() + make_interval(hours => %s)) returning expires_at",
            (token_digest(token), user["id"], ttl_hours),
        ).fetchone()
    return LoginOut(token=token, expires_at=row["expires_at"], role=user["role"])


@router.post("/auth/logout", status_code=204)
def logout(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _user: CurrentUser = Depends(current_user),
) -> Response:
    with tx() as conn:
        conn.execute(
            "update sessions set revoked_at = now() where token_hash = %s and revoked_at is null",
            (token_digest(cred.credentials),),
        )
    return Response(status_code=204)


class MeOut(StrictModel):
    id: UUID
    login: str
    full_name: str
    role: str


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(current_user)) -> MeOut:
    return MeOut(id=user.id, login=user.login, full_name=user.full_name, role=user.role)


class UserCreate(StrictModel):
    login: Login
    password: Password
    full_name: FullName
    # Администратор создаётся только командой bootstrap на сервере, через API — нет.
    role: Literal["tutor", "parent"]


@router.post("/users", response_model=MeOut, status_code=201)
def create_user(
    body: UserCreate = Depends(json_body(UserCreate)),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> MeOut:
    try:
        with tx() as conn:
            row = conn.execute(
                "insert into users (login, password_hash, full_name, role) values (%s, %s, %s, %s)"
                " returning id, login, full_name, role",
                (body.login, hash_password(body.password), body.full_name, body.role),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="login already taken")
    return MeOut(**row)

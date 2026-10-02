"""Точка входа API CheckBalance.

Запуск: uvicorn app.main:app  (настройки — из окружения, см. .env.example)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import auth, lessons, students
from app.config import Settings, load_settings
from app.db import close_pool, open_pool, tx

log = logging.getLogger("checkbalance")


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings or load_settings()
        open_pool(app.state.settings.database_url)
        try:
            yield
        finally:
            close_pool()

    app = FastAPI(title="CheckBalance", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Без отражения введённых значений в ответе.
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        return JSONResponse(status_code=422, content={"detail": {"error": "invalid input", "fields": fields}})

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        # Подробности — только в серверный лог; клиент не получает трассировку и SQL.
        log.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    @app.get("/health")
    def health() -> dict:
        with tx() as conn:
            conn.execute("select 1")
        return {"status": "ok", "db": "ok"}

    app.include_router(auth.router)
    app.include_router(students.router)
    app.include_router(lessons.router)
    return app


app = create_app()

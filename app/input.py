"""Строгий разбор JSON-тела запроса (SR-11).

Почему не стандартный разбор FastAPI:
- стандартный json молча берёт последнее значение повторного ключа ({"amount": 1, "amount": -500});
- лишние поля по умолчанию игнорируются, и клиент может считать, что передал, например, "role";
- размер тела не ограничен.

Здесь: только application/json, тело не больше max_body_bytes, корректный UTF-8, без повторных ключей
и NaN/Infinity, ровно один JSON-объект, модель без лишних полей и без приведения типов ("100" ≠ 100).
"""

import json
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

DEFAULT_MAX_BODY_BYTES = 16 * 1024

M = TypeVar("M", bound=BaseModel)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class _DuplicateKey(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-finite number {name}")


def parse_strict(raw: bytes, model: type[M]) -> M:
    """Разбирает уже прочитанное тело. Вынесено отдельно для модульных тестов."""
    try:
        text = raw.decode("utf-8")
        obj = json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except _DuplicateKey:
        raise HTTPException(status_code=400, detail="duplicate key in JSON")
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="malformed JSON")
    if not isinstance(obj, dict):
        raise HTTPException(status_code=422, detail="JSON object expected")
    try:
        return model.model_validate_json(text)
    except ValidationError as exc:
        # В ответ попадают только имена полей, без значений: введённые пароли не отражаются обратно.
        fields = sorted({".".join(str(p) for p in err["loc"]) or "body" for err in exc.errors()})
        raise HTTPException(status_code=422, detail={"error": "invalid input", "fields": fields})


def json_body(model: type[M], max_bytes: int = DEFAULT_MAX_BODY_BYTES) -> Callable[[Request], Awaitable[M]]:
    async def dependency(request: Request) -> M:
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(status_code=415, detail="application/json required")
        declared = request.headers.get("content-length")
        if declared is not None:
            if not declared.isdigit():
                raise HTTPException(status_code=400, detail="bad content-length")
            if int(declared) > max_bytes:
                raise HTTPException(status_code=413, detail="body too large")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > max_bytes:
                raise HTTPException(status_code=413, detail="body too large")
        return parse_strict(bytes(body), model)

    return dependency

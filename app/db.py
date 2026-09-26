"""Пул соединений с PostgreSQL.

`tx()` выдаёт соединение в транзакции: при выходе без исключения — COMMIT, при исключении — ROLLBACK.
Все запросы параметризованы (%s), склейка SQL со значениями из запроса не используется.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def open_pool(dsn: str) -> None:
    global _pool
    _pool = ConnectionPool(dsn, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def tx() -> Iterator[Connection]:
    if _pool is None:
        raise RuntimeError("database pool is not open")
    with _pool.connection() as conn:
        yield conn

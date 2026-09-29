"""Область видимости учеников по роли (D-02, SR-05).

Правило проверяется в самом SQL-запросе: чужой объект не загружается вовсе, поэтому
«забытая проверка после загрузки» невозможна. Для чужого и несуществующего id ответ одинаковый — 404.
"""

from uuid import UUID

from fastapi import HTTPException
from psycopg import Connection

from app.auth import CurrentUser


def student_scope(user: CurrentUser, alias: str = "s") -> tuple[str, tuple]:
    if user.role == "admin":
        return "true", ()
    if user.role == "tutor":
        return f"{alias}.tutor_id = %s", (user.id,)
    if user.role == "parent":
        return f"{alias}.parent_id = %s", (user.id,)
    return "false", ()


def balance_sql(alias: str = "s") -> str:
    return f"(select coalesce(sum(le.amount), 0) from ledger_entries le where le.student_id = {alias}.id)"


def get_student_in_scope(conn: Connection, user: CurrentUser, student_id: UUID) -> dict:
    clause, params = student_scope(user)
    row = conn.execute(
        f"select s.*, {balance_sql()} as balance from students s where s.id = %s and {clause}",
        (student_id, *params),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="student not found")
    return row

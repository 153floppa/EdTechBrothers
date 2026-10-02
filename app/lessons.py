"""Занятия и отчёт о занятии со списанием с баланса (D-03, SR-07, SR-08).

Отчёт — один условный UPDATE: строка меняется, только если занятие своё, начавшееся и ещё в статусе
'planned'. Параллельный второй отчёт ждёт блокировку строки, после чего условие уже ложно — 0 строк.
Уникальный lesson_id в ledger_entries — второй барьер от двойного списания.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, Field

from app.access import get_student_in_scope, student_scope
from app.auth import CurrentUser, current_user, require_role
from app.db import tx
from app.input import StrictModel, json_body

router = APIRouter()

CHARGED_STATUSES = {"done", "no_show_burned"}


class LessonCreate(StrictModel):
    student_id: UUID
    starts_at: AwareDatetime
    duration_min: Literal[60, 90, 120]


class LessonOut(StrictModel):
    id: UUID
    student_id: UUID
    tutor_id: UUID
    starts_at: datetime
    duration_min: int
    status: str
    price_snapshot: int | None
    reported_at: datetime | None


class ReportIn(StrictModel):
    status: Literal["done", "no_show_excused", "no_show_burned"]


class ReportOut(StrictModel):
    lesson: LessonOut
    charged: int


_LESSON_COLS = "l.id, l.student_id, l.tutor_id, l.starts_at, l.duration_min, l.status, l.price_snapshot, l.reported_at"


@router.post("/lessons", response_model=LessonOut, status_code=201)
def create_lesson(
    body: LessonCreate = Depends(json_body(LessonCreate)),
    tutor: CurrentUser = Depends(require_role("tutor")),
) -> LessonOut:
    now = datetime.now(timezone.utc)
    if not (now - timedelta(days=30) <= body.starts_at <= now + timedelta(days=90)):
        raise HTTPException(status_code=422, detail="starts_at out of allowed range")
    with tx() as conn:
        get_student_in_scope(conn, tutor, body.student_id)  # чужой ученик → 404
        row = conn.execute(
            "insert into lessons as l (student_id, tutor_id, starts_at, duration_min)"
            f" values (%s, %s, %s, %s) returning {_LESSON_COLS}",
            (body.student_id, tutor.id, body.starts_at, body.duration_min),
        ).fetchone()
    return LessonOut(**row)


@router.get("/lessons", response_model=list[LessonOut])
def list_lessons(
    student_id: Annotated[UUID, Query()],
    user: CurrentUser = Depends(current_user),
) -> list[LessonOut]:
    clause, params = student_scope(user)
    with tx() as conn:
        rows = conn.execute(
            f"select {_LESSON_COLS} from lessons l join students s on s.id = l.student_id"
            f" where l.student_id = %s and {clause} order by l.starts_at",
            (student_id, *params),
        ).fetchall()
    return [LessonOut(**r) for r in rows]


@router.post("/lessons/{lesson_id}/report", response_model=ReportOut)
def report_lesson(
    lesson_id: UUID,
    body: ReportIn = Depends(json_body(ReportIn)),
    tutor: CurrentUser = Depends(require_role("tutor")),
) -> ReportOut:
    charge = body.status in CHARGED_STATUSES
    with tx() as conn:
        row = conn.execute(
            f"""
            update lessons l
               set status = %(status)s,
                   reported_at = now(),
                   reported_by = %(tutor)s,
                   price_snapshot = case when %(charge)s then s.lesson_price * l.duration_min / 60 else 0 end
              from students s
             where l.id = %(lesson)s
               and s.id = l.student_id
               and l.tutor_id = %(tutor)s
               and s.tutor_id = %(tutor)s
               and l.status = 'planned'
               and l.starts_at <= now()
            returning {_LESSON_COLS}
            """,
            {"status": body.status, "tutor": tutor.id, "charge": charge, "lesson": lesson_id},
        ).fetchone()
        if row is None:
            current = conn.execute(
                "select l.status, l.starts_at <= now() as started from lessons l join students s"
                " on s.id = l.student_id where l.id = %s and l.tutor_id = %s and s.tutor_id = %s",
                (lesson_id, tutor.id, tutor.id),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="lesson not found")
            if current["status"] != "planned":
                raise HTTPException(status_code=409, detail="lesson already reported")
            raise HTTPException(status_code=422, detail="lesson has not started yet")
        charged = row["price_snapshot"] if charge else 0
        if charged:
            conn.execute(
                "insert into ledger_entries (student_id, kind, amount, lesson_id, created_by)"
                " values (%s, 'lesson_charge', %s, %s, %s)",
                (row["student_id"], -charged, lesson_id, tutor.id),
            )
    return ReportOut(lesson=LessonOut(**row), charged=charged)

"""Ученики, ручное зачисление оплаты и денежная история (D-02, D-03).

Ответ собирается из отдельной модели для каждой роли (белый список полей, SR-06):
преподаватель получает только имя и класс — без телефона родителя, цены и баланса.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.access import balance_sql, get_student_in_scope, student_scope
from app.auth import CurrentUser, current_user, require_role
from app.db import tx
from app.input import StrictModel, json_body

router = APIRouter()


class StudentCreate(StrictModel):
    full_name: Annotated[str, Field(min_length=1, max_length=100)]
    grade: Annotated[int, Field(ge=1, le=11)]
    tutor_id: UUID
    parent_id: UUID
    parent_phone: Annotated[str, Field(pattern=r"^\+7[0-9]{10}$")]
    lesson_price: Annotated[int, Field(ge=100, le=20000)]


class AdminStudentOut(StrictModel):
    id: UUID
    full_name: str
    grade: int
    tutor_id: UUID
    parent_id: UUID
    parent_phone: str
    lesson_price: int
    balance: int


class TutorStudentOut(StrictModel):
    id: UUID
    full_name: str
    grade: int


class ParentStudentOut(StrictModel):
    id: UUID
    full_name: str
    grade: int
    lesson_price: int
    balance: int


StudentOut = AdminStudentOut | ParentStudentOut | TutorStudentOut

_VIEW = {"admin": AdminStudentOut, "tutor": TutorStudentOut, "parent": ParentStudentOut}


def project(user: CurrentUser, row: dict) -> StudentOut:
    model = _VIEW[user.role]
    return model(**{name: row[name] for name in model.model_fields})


@router.post("/students", response_model=AdminStudentOut, status_code=201)
def create_student(
    body: StudentCreate = Depends(json_body(StudentCreate)),
    admin: CurrentUser = Depends(require_role("admin")),
) -> AdminStudentOut:
    with tx() as conn:
        roles = {
            r["id"]: r["role"]
            for r in conn.execute(
                "select id, role from users where id = any(%s) and is_active",
                ([body.tutor_id, body.parent_id],),
            )
        }
        if roles.get(body.tutor_id) != "tutor" or roles.get(body.parent_id) != "parent":
            raise HTTPException(status_code=422, detail="tutor_id/parent_id must reference an active tutor/parent")
        row = conn.execute(
            "insert into students (full_name, grade, tutor_id, parent_id, parent_phone, lesson_price)"
            " values (%s, %s, %s, %s, %s, %s) returning *, 0 as balance",
            (body.full_name, body.grade, body.tutor_id, body.parent_id, body.parent_phone, body.lesson_price),
        ).fetchone()
    return project(admin, row)


@router.get("/students", response_model=list[StudentOut])
def list_students(user: CurrentUser = Depends(current_user)) -> list[StudentOut]:
    clause, params = student_scope(user)
    with tx() as conn:
        rows = conn.execute(
            f"select s.*, {balance_sql()} as balance from students s where {clause} order by s.full_name",
            params,
        ).fetchall()
    return [project(user, r) for r in rows]


@router.get("/students/{student_id}", response_model=StudentOut)
def get_student(student_id: UUID, user: CurrentUser = Depends(current_user)) -> StudentOut:
    with tx() as conn:
        row = get_student_in_scope(conn, user, student_id)
    return project(user, row)


class PaymentIn(StrictModel):
    amount: Annotated[int, Field(ge=1, le=1_000_000)]
    # Номер операции в банке. Повтор того же номера не создаёт второе зачисление (SR-10).
    external_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    comment: Annotated[str, Field(max_length=200)] | None = None


class PaymentOut(StrictModel):
    student_id: UUID
    amount: int
    external_id: str
    duplicate: bool
    balance: int


@router.post("/students/{student_id}/payments", response_model=PaymentOut, status_code=201)
def add_payment(
    student_id: UUID,
    body: PaymentIn = Depends(json_body(PaymentIn)),
    admin: CurrentUser = Depends(require_role("admin")),
) -> PaymentOut:
    """Ручное зачисление администратором по выписке банка. Автоматический приём уведомлений банка — D-04."""
    with tx() as conn:
        get_student_in_scope(conn, admin, student_id)
        inserted = conn.execute(
            "insert into ledger_entries (student_id, kind, amount, external_id, comment, created_by)"
            " values (%s, 'payment', %s, %s, %s, %s)"
            " on conflict (external_id) do nothing returning id",
            (student_id, body.amount, body.external_id, body.comment, admin.id),
        ).fetchone()
        if inserted is None:
            existing = conn.execute(
                "select student_id, amount from ledger_entries where external_id = %s", (body.external_id,)
            ).fetchone()
            if existing["student_id"] != student_id or existing["amount"] != body.amount:
                raise HTTPException(status_code=409, detail="external_id already used for another payment")
        balance = get_student_in_scope(conn, admin, student_id)["balance"]
    return PaymentOut(
        student_id=student_id,
        amount=body.amount,
        external_id=body.external_id,
        duplicate=inserted is None,
        balance=balance,
    )


class LedgerEntryOut(StrictModel):
    kind: Literal["payment", "lesson_charge"]
    amount: int
    lesson_id: UUID | None
    created_at: datetime


class LedgerOut(StrictModel):
    student_id: UUID
    balance: int
    entries: list[LedgerEntryOut]


@router.get("/students/{student_id}/ledger", response_model=LedgerOut)
def get_ledger(
    student_id: UUID,
    user: CurrentUser = Depends(require_role("admin", "parent")),
) -> LedgerOut:
    with tx() as conn:
        student = get_student_in_scope(conn, user, student_id)
        rows = conn.execute(
            "select kind, amount, lesson_id, created_at from ledger_entries"
            " where student_id = %s order by created_at, id",
            (student_id,),
        ).fetchall()
    return LedgerOut(
        student_id=student_id,
        balance=student["balance"],
        entries=[LedgerEntryOut(**r) for r in rows],
    )

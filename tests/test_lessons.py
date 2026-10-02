"""SR-07, SR-08: одно списание на занятие, отчёт только своего начавшегося занятия."""

import threading

import psycopg
import pytest

from tests.conftest import future, past


def create_lesson(client, school, starts_at, tutor="tutor_a", student="student_a", duration=60):
    r = client.post(
        "/lessons",
        headers=school[tutor],
        json={"student_id": school[student], "starts_at": starts_at, "duration_min": duration},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def balance(client, school) -> int:
    return client.get(f"/students/{school['student_a']}", headers=school["parent_a"]).json()["balance"]


def test_report_charges_once_and_parent_sees_it(client, school):
    lesson = create_lesson(client, school, past(), duration=90)
    r = client.post(f"/lessons/{lesson}/report", headers=school["tutor_a"], json={"status": "done"})
    assert r.status_code == 200 and r.json()["charged"] == 3000
    assert balance(client, school) == 2000

    again = client.post(f"/lessons/{lesson}/report", headers=school["tutor_a"], json={"status": "done"})
    assert again.status_code == 409
    assert balance(client, school) == 2000

    ledger = client.get(f"/students/{school['student_a']}/ledger", headers=school["parent_a"]).json()
    assert [(e["kind"], e["amount"]) for e in ledger["entries"]] == [("payment", 5000), ("lesson_charge", -3000)]


def test_excused_absence_is_not_charged(client, school):
    lesson = create_lesson(client, school, past())
    r = client.post(f"/lessons/{lesson}/report", headers=school["tutor_a"], json={"status": "no_show_excused"})
    assert r.status_code == 200 and r.json()["charged"] == 0
    assert balance(client, school) == 5000


def test_parallel_reports_charge_once(client, school, db):
    lesson = create_lesson(client, school, past())
    barrier = threading.Barrier(5)
    codes = []

    def send():
        barrier.wait()
        codes.append(
            client.post(f"/lessons/{lesson}/report", headers=school["tutor_a"], json={"status": "done"}).status_code
        )

    threads = [threading.Thread(target=send) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 409, 409, 409, 409]
    with psycopg.connect(db) as conn:
        n = conn.execute("select count(*) from ledger_entries where lesson_id = %s", (lesson,)).fetchone()[0]
    assert n == 1
    assert balance(client, school) == 3000


def test_cannot_report_future_lesson(client, school):
    lesson = create_lesson(client, school, future())
    r = client.post(f"/lessons/{lesson}/report", headers=school["tutor_a"], json={"status": "done"})
    assert r.status_code == 422
    assert balance(client, school) == 5000


def test_foreign_tutor_cannot_report_or_create(client, school):
    lesson = create_lesson(client, school, past())
    r = client.post(f"/lessons/{lesson}/report", headers=school["tutor_b"], json={"status": "done"})
    assert r.status_code == 404
    r = client.post(
        "/lessons",
        headers=school["tutor_b"],
        json={"student_id": school["student_a"], "starts_at": past(), "duration_min": 60},
    )
    assert r.status_code == 404


@pytest.mark.parametrize("role", ["admin", "parent_a"])
def test_only_tutor_reports(client, school, role):
    lesson = create_lesson(client, school, past())
    r = client.post(f"/lessons/{lesson}/report", headers=school[role], json={"status": "done"})
    assert r.status_code == 403


def test_ledger_is_append_only_in_db(client, school, db):
    with psycopg.connect(db) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("update ledger_entries set amount = 1000000")

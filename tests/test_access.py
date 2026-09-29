"""SR-05, SR-06: доступ по области видимости роли и минимизация полей."""


def test_tutor_sees_only_own_students_without_contacts_and_money(client, school):
    r = client.get("/students", headers=school["tutor_a"])
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == [school["student_a"]]
    assert set(r.json()[0]) == {"id", "full_name", "grade"}

    one = client.get(f"/students/{school['student_a']}", headers=school["tutor_a"]).json()
    assert "parent_phone" not in one and "balance" not in one and "lesson_price" not in one


def test_foreign_student_is_404_for_tutor_and_parent(client, school):
    foreign = school["student_b"]
    assert client.get(f"/students/{foreign}", headers=school["tutor_a"]).status_code == 404
    assert client.get(f"/students/{foreign}", headers=school["parent_a"]).status_code == 404
    assert client.get(f"/students/{foreign}/ledger", headers=school["parent_a"]).status_code == 404
    # Ответ для чужого и несуществующего id одинаков.
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/students/{missing}", headers=school["tutor_a"]).status_code == 404


def test_parent_sees_balance_but_not_phone(client, school):
    one = client.get(f"/students/{school['student_a']}", headers=school["parent_a"]).json()
    assert one["balance"] == 5000
    assert "parent_phone" not in one and "tutor_id" not in one


def test_tutor_has_no_access_to_ledger_and_payments(client, school):
    sid = school["student_a"]
    assert client.get(f"/students/{sid}/ledger", headers=school["tutor_a"]).status_code == 403
    r = client.post(f"/students/{sid}/payments", headers=school["tutor_a"], json={"amount": 100, "external_id": "t"})
    assert r.status_code == 403


def test_admin_sees_everything(client, school):
    rows = client.get("/students", headers=school["admin"]).json()
    assert len(rows) == 2 and all("parent_phone" in r for r in rows)


def test_repeated_payment_external_id_credits_once(client, school):
    sid, admin = school["student_a"], school["admin"]
    r = client.post(f"/students/{sid}/payments", headers=admin, json={"amount": 5000, "external_id": "op-1"})
    assert r.status_code == 201 and r.json()["duplicate"] is True and r.json()["balance"] == 5000
    r = client.post(f"/students/{sid}/payments", headers=admin, json={"amount": 999, "external_id": "op-1"})
    assert r.status_code == 409

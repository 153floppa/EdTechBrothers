"""Проверка работоспособности запущенного API (python scripts/smoke.py).

Нужен созданный администратор: ADMIN_LOGIN (по умолчанию admin) и ADMIN_PASSWORD.
Сценарий: вход → преподаватель и родитель → ученик → оплата → занятие → отчёт →
родитель видит списание; повторный отчёт — 409; чужой преподаватель — 404; logout отзывает токен.
"""

import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
PASSWORD = "smoke-" + secrets.token_hex(8)


def check(cond: bool, what: str) -> None:
    print(("OK   " if cond else "FAIL ") + what)
    if not cond:
        sys.exit(1)


def login(c: httpx.Client, name: str, password: str) -> dict:
    r = c.post("/auth/login", json={"login": name, "password": password})
    check(r.status_code == 200, f"login {name}")
    return {"Authorization": "Bearer " + r.json()["token"]}


def main() -> None:
    sfx = secrets.token_hex(3)
    with httpx.Client(base_url=BASE, timeout=10) as c:
        check(c.get("/health").json() == {"status": "ok", "db": "ok"}, "health")
        check(c.get("/students").status_code == 401, "no session -> 401")
        admin = login(c, os.environ.get("ADMIN_LOGIN", "admin"), os.environ["ADMIN_PASSWORD"])

        ids = {}
        for name, role in [(f"tutor_{sfx}", "tutor"), (f"tutor2_{sfx}", "tutor"), (f"parent_{sfx}", "parent")]:
            r = c.post("/users", headers=admin, json={"login": name, "password": PASSWORD, "full_name": name, "role": role})
            check(r.status_code == 201, f"create {role} {name}")
            ids[name] = r.json()["id"]

        r = c.post("/students", headers=admin, json={
            "full_name": "Смоук Ученик", "grade": 11, "tutor_id": ids[f"tutor_{sfx}"],
            "parent_id": ids[f"parent_{sfx}"], "parent_phone": "+79990000000", "lesson_price": 2000})
        check(r.status_code == 201, "create student")
        sid = r.json()["id"]
        r = c.post(f"/students/{sid}/payments", headers=admin, json={"amount": 5000, "external_id": f"smoke-{sfx}"})
        check(r.status_code == 201 and r.json()["balance"] == 5000, "payment -> balance 5000")

        tutor = login(c, f"tutor_{sfx}", PASSWORD)
        other = login(c, f"tutor2_{sfx}", PASSWORD)
        parent = login(c, f"parent_{sfx}", PASSWORD)

        card = c.get(f"/students/{sid}", headers=tutor).json()
        check("parent_phone" not in card and "balance" not in card, "tutor sees no phone/balance")

        starts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = c.post("/lessons", headers=tutor, json={"student_id": sid, "starts_at": starts, "duration_min": 60})
        check(r.status_code == 201, "tutor creates lesson")
        lid = r.json()["id"]

        check(c.post(f"/lessons/{lid}/report", headers=other, json={"status": "done"}).status_code == 404,
              "foreign tutor report -> 404")
        r = c.post(f"/lessons/{lid}/report", headers=tutor, json={"status": "done"})
        check(r.status_code == 200 and r.json()["charged"] == 2000, "report -> charged 2000")
        check(c.post(f"/lessons/{lid}/report", headers=tutor, json={"status": "done"}).status_code == 409,
              "second report -> 409")
        check(c.get(f"/students/{sid}", headers=parent).json()["balance"] == 3000, "parent sees balance 3000")

        check(c.post("/auth/logout", headers=tutor).status_code == 204, "logout")
        check(c.get("/me", headers=tutor).status_code == 401, "token after logout -> 401")
    print("SMOKE PASSED")


if __name__ == "__main__":
    main()

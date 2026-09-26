"""SR-01–SR-04: субъект только из действующей сессии, отзыв при logout, секреты, единый отказ входа."""

import psycopg

from tests.conftest import PASSWORD, insert_user, login


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_protected_endpoint_requires_session(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer forged-token"}).status_code == 401


def test_login_me_logout_revokes_token(client, db):
    insert_user(db, "tutor_a", "tutor")
    headers = login(client, "tutor_a")
    me = client.get("/me", headers=headers)
    assert me.status_code == 200 and me.json()["role"] == "tutor"

    assert client.post("/auth/logout", headers=headers).status_code == 204
    # Тот же токен после logout больше не принимается (SR-02).
    assert client.get("/me", headers=headers).status_code == 401


def test_expired_session_rejected(client, db):
    insert_user(db, "tutor_a", "tutor")
    headers = login(client, "tutor_a")
    with psycopg.connect(db) as conn:
        conn.execute("update sessions set expires_at = now() - interval '1 second'")
    assert client.get("/me", headers=headers).status_code == 401


def test_deactivated_user_session_rejected(client, db):
    insert_user(db, "tutor_a", "tutor")
    headers = login(client, "tutor_a")
    with psycopg.connect(db) as conn:
        conn.execute("update users set is_active = false where login = 'tutor_a'")
    assert client.get("/me", headers=headers).status_code == 401


def test_db_stores_only_token_digest_and_password_hash(client, db):
    insert_user(db, "tutor_a", "tutor")
    token = login(client, "tutor_a")["Authorization"].split()[1]
    with psycopg.connect(db) as conn:
        dump = str(conn.execute("select * from sessions").fetchall()) + str(
            conn.execute("select password_hash from users").fetchall()
        )
    assert token not in dump
    assert PASSWORD not in dump


def test_failed_login_same_answer_for_unknown_and_wrong_password(client, db):
    insert_user(db, "tutor_a", "tutor")
    wrong = client.post("/auth/login", json={"login": "tutor_a", "password": "wrong-password-1"})
    unknown = client.post("/auth/login", json={"login": "nobody", "password": "wrong-password-1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_only_admin_creates_users_and_never_admins(client, db, admin):
    insert_user(db, "tutor_a", "tutor")
    tutor = login(client, "tutor_a")
    body = {"login": "new_parent", "password": PASSWORD, "full_name": "Родитель", "role": "parent"}
    assert client.post("/users", headers=tutor, json=body).status_code == 403
    assert client.post("/users", headers=admin, json=body).status_code == 201
    assert client.post("/users", headers=admin, json=body).status_code == 409
    escalate = {**body, "login": "evil", "role": "admin"}
    assert client.post("/users", headers=admin, json=escalate).status_code == 422

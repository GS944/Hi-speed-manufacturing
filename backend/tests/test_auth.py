"""Accounts: standard sign-up/sign-in with any credentials, sign-up switch, lockout, user management, revocation."""
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, User
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def bearer(r):
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_admin_management_and_revocation(client):
    h = bearer(login(client, "admin", "Test@12345"))
    # any credentials are accepted - no format rules
    r = client.post("/api/users", headers=h, json={"username": "Ravi K", "password": "x1"})
    assert r.status_code == 200, r.text
    assert client.post("/api/users", headers=h, json={"username": "ravi k", "password": "y"}).status_code == 409
    assert login(client, "RAVI K", "x1").status_code == 200          # usernames are case-insensitive
    h2 = bearer(login(client, "Ravi K", "x1"))

    # rename + new password; old sessions of that account stop working
    r = client.put("/api/auth/account", headers=h2, json={"current_password": "x1", "new_username": "ravi", "new_password": "a very long passphrase " * 5})
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=h2).status_code == 401
    h2 = bearer(r)
    assert client.get("/api/auth/me", headers=h2).json()["username"] == "ravi"
    assert login(client, "ravi", "a very long passphrase " * 5).status_code == 200   # >72 bytes works

    # cannot delete yourself or the last admin
    me_id = client.get("/api/auth/me", headers=h).json()["id"]
    assert client.delete(f"/api/users/{me_id}", headers=h).status_code == 400
    rid = client.get("/api/auth/me", headers=h2).json()["id"]
    assert client.delete(f"/api/users/{rid}", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h2).status_code == 401


def test_lockout_after_repeated_failures(client):
    h = bearer(login(client, "admin", "Test@12345"))
    client.post("/api/users", headers=h, json={"username": "temp", "password": "right"})
    codes = [login(client, "temp", "wrong").status_code for _ in range(5)]
    assert codes == [401] * 5
    assert login(client, "temp", "right").status_code == 423            # locked even with the right password
    uid = next(u["id"] for u in client.get("/api/users", headers=h).json()["users"] if u["username"] == "temp")
    assert client.post(f"/api/users/{uid}/unlock", headers=h).status_code == 200
    assert login(client, "temp", "right").status_code == 200


def test_signup_then_signin_on_later_visits(client):
    assert client.get("/api/auth/signup-status").json()["allowed"] is True
    r = client.post("/api/auth/signup", json={"username": "Priya", "password": "pq"})          # any credentials
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=bearer(r)).json()["username"] == "Priya"
    assert client.post("/api/auth/signup", json={"username": "priya", "password": "x"}).status_code == 409
    # a later visit: no session, just the same credentials
    assert login(client, "Priya", "pq").status_code == 200
    assert login(client, "Priya", "wrong").status_code == 401


def test_signup_switch(client):
    h = bearer(login(client, "admin", "Test@12345"))
    assert client.put("/api/auth/signup-setting", headers=h, json={"allowed": False}).status_code == 200
    assert client.get("/api/auth/signup-status").json()["allowed"] is False
    assert client.post("/api/auth/signup", json={"username": "stranger", "password": "s"}).status_code == 403
    assert client.get("/api/users", headers=h).json()["signup_allowed"] is False
    assert login(client, "Priya", "pq").status_code == 200                                   # existing users unaffected
    client.put("/api/auth/signup-setting", headers=h, json={"allowed": True})
    assert client.post("/api/auth/signup", json={"username": "stranger", "password": "s"}).status_code == 200


def test_fresh_installation_can_always_sign_up(client):
    h = bearer(login(client, "admin", "Test@12345"))
    client.put("/api/auth/signup-setting", headers=h, json={"allowed": False})
    with SessionLocal() as db:                     # no accounts at all, sign-ups switched off
        db.query(User).delete()
        db.commit()
    assert client.get("/api/auth/signup-status").json() == {"allowed": True, "first_account": True}
    assert client.post("/api/auth/signup", json={"username": "owner", "password": "o"}).status_code == 200

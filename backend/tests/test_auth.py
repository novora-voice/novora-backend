from fastapi.testclient import TestClient

from novora.api.auth import (
    AuthStore,
    SESSION_COOKIE_NAME,
    hash_password,
    session_token_hash,
)
from novora.api.main import create_app


def make_client(db_path):
    return TestClient(create_app(auth_store=AuthStore(db_path)))


def signup_payload(email="member@example.com"):
    return {
        "full_name": "Novora Member",
        "email": email,
        "password": "correct-horse-battery",
    }


def test_protected_api_requires_authenticated_session(tmp_path):
    client = make_client(tmp_path / "auth.sqlite3")

    response = client.get("/api/v1/scenarios")

    assert response.status_code == 401


def test_signup_login_and_logout_use_http_only_session_cookie(tmp_path):
    client = make_client(tmp_path / "auth.sqlite3")

    signup = client.post("/api/v1/auth/signup", json=signup_payload())

    assert signup.status_code == 201
    assert signup.json()["email"] == "member@example.com"
    assert "password" not in signup.json()
    set_cookie = signup.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie
    assert "httponly" in set_cookie
    assert client.get("/api/v1/auth/me").json()["full_name"] == "Novora Member"

    duplicate = client.post("/api/v1/auth/signup", json=signup_payload("MEMBER@example.com"))
    assert duplicate.status_code == 409

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "MEMBER@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    assert login.json()["email"] == "member@example.com"


def test_login_rejects_wrong_password_without_revealing_account_state(tmp_path):
    client = make_client(tmp_path / "auth.sqlite3")
    client.post("/api/v1/auth/signup", json=signup_payload())

    existing = client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": "incorrect-password"},
    )
    missing = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "incorrect-password"},
    )

    assert existing.status_code == missing.status_code == 401
    assert existing.json()["detail"] == missing.json()["detail"]


def test_sessions_survive_store_recreation(tmp_path):
    db_path = tmp_path / "auth.sqlite3"
    store = AuthStore(db_path)
    user = store.create_user(
        "member@example.com",
        "Novora Member",
        hash_password("correct-horse-battery"),
    )
    assert user is not None
    token = "session-token"
    store.create_session(user.id, session_token_hash(token), 4_102_444_800)

    restarted_store = AuthStore(db_path)

    restored = restarted_store.get_user_for_session(session_token_hash(token))
    assert restored is not None
    assert restored.id == user.id

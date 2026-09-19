from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_with_valid_credentials_returns_a_token_and_role():
    resp = client.post("/auth/login", json={"username": "alex.kim", "password": "agent123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == "agent-demo-token"
    assert body["user"]["role"] == 1
    assert body["user"]["display_name"] == "Alex Kim"


def test_login_with_wrong_password_is_rejected():
    resp = client.post("/auth/login", json={"username": "alex.kim", "password": "wrong"})
    assert resp.status_code == 401


def test_login_with_unknown_username_is_rejected():
    resp = client.post("/auth/login", json={"username": "nobody", "password": "whatever"})
    assert resp.status_code == 401


def test_me_endpoint_reflects_the_logged_in_user():
    resp = client.get("/auth/me", headers={"X-Demo-Token": "lead-demo-token"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Priya Nair"
    assert resp.json()["role"] == 2


def test_me_endpoint_requires_a_token():
    resp = client.get("/auth/me")
    assert resp.status_code == 401

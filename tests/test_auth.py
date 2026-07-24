"""
tests/test_auth.py

Tests for POST /register and POST /login.
"""
from conftest import register_user, login_user


def test_register_success(client):
    response = register_user(client)
    assert response.status_code == 201
    data = response.get_json()
    assert data["username"] == "alice"


def test_register_missing_fields(client):
    response = client.post("/register", json={"username": "bob"})
    assert response.status_code == 400


def test_register_duplicate_username(client):
    register_user(client)
    response = register_user(client)
    assert response.status_code == 409


def test_login_success(client):
    register_user(client)
    response = login_user(client)
    assert response.status_code == 200
    assert "token" in response.get_json()


def test_login_wrong_password(client):
    register_user(client)
    response = login_user(client, password="wrongpass")
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    response = login_user(client, username="ghost")
    assert response.status_code == 401


def test_login_missing_fields(client):
    response = client.post("/login", json={"username": "alice"})
    assert response.status_code == 400
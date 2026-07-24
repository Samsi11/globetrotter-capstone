"""
tests/test_recommendations.py

Tests for GET /recommendations, covering auth requirements, scoring order,
the optional limit parameter, and invalid input handling.
"""
from conftest import register_user, login_user, auth_header


def get_token(client, preferences=None):
    register_user(client, preferences=preferences)
    response = login_user(client)
    return response.get_json()["token"]


def test_recommendations_requires_auth(client):
    response = client.get("/recommendations")
    assert response.status_code == 401


def test_recommendations_returns_scored_destinations(client):
    token = get_token(client, preferences=["food"])
    response = client.get("/recommendations", headers=auth_header(token))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) > 0
    # Results should be sorted by match_score descending
    assert data[0]["match_score"] >= data[-1]["match_score"]


def test_recommendations_respects_limit(client):
    token = get_token(client, preferences=["food"])
    response = client.get("/recommendations?limit=1", headers=auth_header(token))
    data = response.get_json()
    assert len(data) == 1


def test_recommendations_invalid_limit_returns_400(client):
    token = get_token(client)
    response = client.get("/recommendations?limit=notanumber", headers=auth_header(token))
    assert response.status_code == 400


def test_recommendations_invalid_token_returns_401(client):
    response = client.get("/recommendations", headers=auth_header("garbage.token.value"))
    assert response.status_code == 401
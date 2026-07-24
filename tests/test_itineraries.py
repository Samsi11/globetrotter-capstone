"""
tests/test_itineraries.py

Tests for POST /itineraries and GET /itineraries, covering auth requirements,
successful creation, and validation errors.
"""
from conftest import register_user, login_user, auth_header


def get_token(client):
    register_user(client)
    response = login_user(client)
    return response.get_json()["token"]


def test_create_itinerary_requires_auth(client):
    response = client.post("/itineraries", json={"title": "Trip"})
    assert response.status_code == 401


def test_create_itinerary_success(client):
    token = get_token(client)
    response = client.post(
        "/itineraries",
        json={
            "title": "Beach Escape",
            "destinations": ["Bali"],
            "start_date": "2025-07-01",
            "end_date": "2025-07-14",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["title"] == "Beach Escape"
    assert "id" in data


def test_create_itinerary_missing_title_returns_400(client):
    token = get_token(client)
    response = client.post(
        "/itineraries",
        json={"destinations": ["Bali"]},
        headers=auth_header(token),
    )
    assert response.status_code == 400


def test_create_itinerary_invalid_destinations_type_returns_400(client):
    token = get_token(client)
    response = client.post(
        "/itineraries",
        json={"title": "Trip", "destinations": "Bali"},  # should be a list, not a string
        headers=auth_header(token),
    )
    assert response.status_code == 400


def test_list_itineraries_requires_auth(client):
    response = client.get("/itineraries")
    assert response.status_code == 401


def test_list_itineraries_returns_created_itinerary(client):
    token = get_token(client)
    client.post(
        "/itineraries",
        json={"title": "Trip", "destinations": ["Paris"]},
        headers=auth_header(token),
    )
    response = client.get("/itineraries", headers=auth_header(token))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["title"] == "Trip"
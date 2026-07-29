"""
tests/test_locations.py

Tests for GET /api/pois.
"""


def test_list_all_pois(client):
    response = client.get("/api/pois")
    assert response.status_code == 200
    assert len(response.get_json()) == 3


def test_filter_by_category(client):
    response = client.get("/api/pois?category=fuel")
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "TotalEnergies Ekoumdoum"


def test_filter_by_text_query(client):
    response = client.get("/api/pois?q=grill")
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "SIZZLE & SIP"


def test_filter_with_no_matches(client):
    response = client.get("/api/pois?q=doesnotexist")
    assert response.get_json() == []
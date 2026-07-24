"""
tests/test_destinations.py

Tests for GET /destinations, including filtering by tag, continent,
max_cost, and free-text query.
"""


def test_list_all_destinations(client):
    response = client.get("/destinations")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3


def test_filter_by_tag(client):
    response = client.get("/destinations?tag=food")
    assert response.status_code == 200
    names = [d["name"] for d in response.get_json()]
    assert "Paris" in names
    assert "Bangkok" in names
    assert "Bali" not in names


def test_filter_by_continent(client):
    response = client.get("/destinations?continent=Europe")
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "Paris"


def test_filter_by_max_cost(client):
    response = client.get("/destinations?max_cost=50")
    names = [d["name"] for d in response.get_json()]
    assert "Bali" in names
    assert "Bangkok" in names
    assert "Paris" not in names


def test_filter_by_query_text(client):
    response = client.get("/destinations?q=temples")
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "Bali"


def test_invalid_max_cost_returns_400(client):
    response = client.get("/destinations?max_cost=notanumber")
    assert response.status_code == 400
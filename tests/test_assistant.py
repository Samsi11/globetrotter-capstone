"""
tests/test_assistant.py

Tests for POST /api/assistant.

Since no ANTHROPIC_API_KEY is set during tests, these exercise the
fallback rule-based assistant path — which is also exactly what runs for
any user who hasn't configured a live API key, so it's the most
important path to have solid coverage on.
"""


def test_missing_message_returns_400(client):
    response = client.post("/api/assistant", json={})
    assert response.status_code == 400


def test_fallback_used_when_no_api_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post("/api/assistant", json={"message": "hello"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["source"] == "fallback"
    assert "Tropicana" in data["reply"]


def test_fallback_matches_category_keyword(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post("/api/assistant", json={"message": "where can I get fuel near here"})
    data = response.get_json()
    assert data["source"] == "fallback"
    assert "TotalEnergies Ekoumdoum" in data["reply"]


def test_fallback_handles_unknown_topic_gracefully(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post("/api/assistant", json={"message": "what's the weather like on Mars"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["source"] == "fallback"
    assert len(data["reply"]) > 0
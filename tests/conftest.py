"""
tests/conftest.py

Shared pytest fixtures for the GlobeTrotter test suite.

Key idea: we monkeypatch the file paths used by app/models.py so that every
test run reads/writes to temporary files instead of your real data/*.json
files. This means running tests will NEVER corrupt your actual users,
itineraries, or destinations data.
"""
import json
import os
import sys

import pytest

# Make sure "app" package is importable regardless of where pytest is invoked from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app import models


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a Flask app configured to use isolated, temporary JSON files."""
    users_file = tmp_path / "users.json"
    itineraries_file = tmp_path / "itineraries.json"
    destinations_file = tmp_path / "destinations.json"

    # Redirect the model layer's file paths to our temp files
    monkeypatch.setattr(models, "USERS_FILE", str(users_file))
    monkeypatch.setattr(models, "ITINERARIES_FILE", str(itineraries_file))
    monkeypatch.setattr(models, "DESTINATIONS_FILE", str(destinations_file))

    # Seed a small, predictable destinations catalogue for tests
    seed_destinations = [
        {
            "id": "dest-001",
            "name": "Bali",
            "country": "Indonesia",
            "continent": "Asia",
            "description": "Tropical island known for beaches and temples.",
            "tags": ["beach", "culture", "budget"],
            "avg_cost_per_day": 45,
        },
        {
            "id": "dest-002",
            "name": "Paris",
            "country": "France",
            "continent": "Europe",
            "description": "City of art and cuisine.",
            "tags": ["culture", "food", "city"],
            "avg_cost_per_day": 150,
        },
        {
            "id": "dest-003",
            "name": "Bangkok",
            "country": "Thailand",
            "continent": "Asia",
            "description": "Street food capital.",
            "tags": ["food", "budget", "culture"],
            "avg_cost_per_day": 35,
        },
    ]
    destinations_file.write_text(json.dumps(seed_destinations), encoding="utf-8")

    flask_app = create_app()
    flask_app.config.update({"TESTING": True})

    yield flask_app


@pytest.fixture
def client(app):
    """A Flask test client for firing requests at the app without a real server."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Shared helper functions (imported directly by test files)
# ---------------------------------------------------------------------------
def register_user(client, username="alice", password="s3cr3t", preferences=None):
    if preferences is None:
        preferences = ["beach", "food"]
    return client.post(
        "/register",
        json={"username": username, "password": password, "preferences": preferences},
    )


def login_user(client, username="alice", password="s3cr3t"):
    return client.post("/login", json={"username": username, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}
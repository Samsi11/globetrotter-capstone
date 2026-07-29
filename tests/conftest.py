"""
tests/conftest.py

Shared pytest fixtures. Isolates test data from the real data/pois.json
by monkeypatching the file path models.py reads from.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app import models


@pytest.fixture
def app(tmp_path, monkeypatch):
    pois_file = tmp_path / "pois.json"

    monkeypatch.setattr(models, "POIS_FILE", str(pois_file))

    seed_pois = [
        {"id": "p1", "name": "Pharmacie Tropicana", "category": "pharmacy",
         "lat": 3.8192646, "lng": 11.5233073, "address": "N2, Tropicana, Mvan, Yaoundé",
         "phone": "+237 6 73 22 71 44", "rating": 3.8, "note": "Central pharmacy.", "image": None},
        {"id": "p2", "name": "TotalEnergies Ekoumdoum", "category": "fuel",
         "lat": 3.8251685, "lng": 11.5368803, "address": "Ekoumdoum, Yaoundé",
         "phone": "+237 6 70 95 00 00", "rating": 3.6, "note": "24-hour fuel station.", "image": None},
        {"id": "p3", "name": "SIZZLE & SIP", "category": "restaurant",
         "lat": 3.823414, "lng": 11.5198316, "address": "Montée Mvan, Yaoundé",
         "phone": "+237 6 50 52 08 68", "rating": 4.3, "note": "Grill restaurant.", "image": None},
    ]
    pois_file.write_text(json.dumps(seed_pois), encoding="utf-8")

    flask_app = create_app()
    flask_app.config.update({"TESTING": True})

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
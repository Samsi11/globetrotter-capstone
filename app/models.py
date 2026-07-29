"""
app/models.py

Data access helpers for the Tropicana Guide app.

All persistent data is stored in JSON files under the /data directory:
    - data/pois.json  – points of interest around Tropicana / Mvan (seed data)

This mirrors the original GlobeTrotter pattern: simple file-based storage,
resolved relative to this file so the app works regardless of the current
working directory.
"""
import json
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_BASE_DIR, "data")
POIS_FILE = os.path.join(DATA_DIR, "pois.json")


def _read_json(filepath: str) -> list:
    """Read a JSON file and return its contents as a Python list.

    Returns an empty list if the file does not exist or is empty.
    """
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        if not content:
            return []
        return json.loads(content)


def get_all_pois() -> list:
    """Return every point of interest in the Tropicana / Mvan dataset."""
    return _read_json(POIS_FILE)
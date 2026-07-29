"""
app/locations.py

Search endpoint for points of interest around Tropicana / Mvan.

Routes
------
GET /api/pois?q=&category=
    Returns points of interest, optionally filtered by free-text query
    and/or category.
"""
from flask import Blueprint, request, jsonify

from app.models import get_all_pois

locations_bp = Blueprint("locations", __name__)


@locations_bp.route("/api/pois", methods=["GET"])
def search_pois():
    """Search points of interest.

    Query parameters (all optional):
        q         – free-text search against name and address
        category  – filter by a single category key (e.g. "hotel")

    Returns a JSON list of matching POI objects.
    """
    q = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip().lower()

    pois = get_all_pois()
    results = []
    for poi in pois:
        if category and poi.get("category", "").lower() != category:
            continue
        if q:
            searchable = " ".join([
                poi.get("name", ""),
                poi.get("address", ""),
                poi.get("category", ""),
                poi.get("note", "") or "",
            ]).lower()
            if q not in searchable:
                continue
        results.append(poi)

    return jsonify(results), 200
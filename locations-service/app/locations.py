from flask import Blueprint, request, jsonify
from app.db import fetch_pois

locations_bp = Blueprint("locations", __name__)


@locations_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@locations_bp.route("/api/pois", methods=["GET"])
def search_pois():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    return jsonify(fetch_pois(q=q, category=category)), 200

"""
app/assistant.py — assistant-service

Same live+fallback design as the monolith version: tries the live Claude
API first if ANTHROPIC_API_KEY is set, falls back to the rule-based local
guide on any failure. POI data now comes over HTTP from locations-service
(via Docker DNS) instead of a local JSON file — that's the service boundary.
"""
import math
import os

import requests
from flask import Blueprint, current_app, jsonify, request

assistant_bp = Blueprint("assistant", __name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
LOCATIONS_SERVICE_URL = os.environ.get("LOCATIONS_SERVICE_URL", "http://locations-service:5001")

TROPICANA_LANDMARK = {"lat": 3.8171, "lng": 11.5257, "label": "Carrefour Tropicana"}

CURRENT_LOCATION_PHRASES = [
    "here", "my location", "current location", "where i am",
    "where i'm standing", "standing at", "right now", "this spot",
]
DIRECTION_PHRASES = [
    "how do i get", "how to get", "direction", "route", "way to",
    "get to", "get from", " to ",
]
CATEGORY_KEYWORDS = {
    "hotel": ["hotel", "stay", "sleep", "lodging", "room"],
    "restaurant": ["restaurant", "eat", "food", "dinner", "lunch", "grill", "meal"],
    "hospital": ["hospital", "clinic", "doctor", "emergency", "sick", "health"],
    "pharmacy": ["pharmacy", "medicine", "drug", "chemist"],
    "school": ["school", "education", "class", "student"],
    "market": ["market", "shopping", "buy", "groceries", "supermarket"],
    "fuel": ["fuel", "petrol", "gas", "station", "diesel"],
    "bank": ["bank", "money", "atm", "withdraw", "cash"],
    "office": ["office", "organisation", "organization", "association"],
}


def _get_all_pois():
    resp = requests.get(f"{LOCATIONS_SERVICE_URL}/api/pois", timeout=5)
    resp.raise_for_status()
    return resp.json()


def _build_system_prompt(pois):
    context_lines = []
    for p in pois:
        line = f"{p['name']} ({p['category']}) — {p['address']}."
        if p.get("note"):
            line += f" {p['note']}"
        if p.get("phone"):
            line += f" Phone: {p['phone']}."
        context_lines.append(line)
    context = "\n".join(context_lines)
    return (
        "You are a warm, knowledgeable local tour guide assistant for the "
        "Tropicana area in Mvan/Ekoumdoum, Yaoundé, Cameroon. You help "
        "residents and visitors find hotels, restaurants, hospitals, "
        "pharmacies, schools, markets, fuel stations, banks, and offices in "
        "this specific area.\n\nReal, current data about places in and "
        f"around the area:\n{context}\n\nGround your answers in this data "
        "whenever a question matches it, mentioning specific place names "
        "and short practical notes. If asked about something not covered "
        "in the data, say so honestly rather than inventing details. Keep "
        "answers conversational and concise."
    )


def _call_claude(message, history, pois):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("No ANTHROPIC_API_KEY configured")

    messages = list(history) + [{"role": "user", "content": message}]
    response = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 500,
            "system": _build_system_prompt(pois),
            "messages": messages,
        },
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    reply = "\n".join(text_blocks).strip()
    return reply or "Sorry, I couldn't put together an answer just then."


def _haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


GENERIC_AREA_WORDS = {
    "tropicana", "carrefour", "yaounde", "yaoundé", "mvan",
    "ekoumdoum", "fokou", "odza", "amitie", "amitié",
}


def _unique_words_by_poi(pois):
    from collections import Counter

    word_counts = Counter()
    poi_words = {}
    for p in pois:
        words = {
            w.strip(",.()")
            for w in p["name"].lower().replace("&", " ").split()
            if len(w.strip(",.()")) >= 5 and w.strip(",.()") not in GENERIC_AREA_WORDS
        }
        poi_words[p["id"]] = words
        for w in words:
            word_counts[w] += 1

    return {pid: {w for w in words if word_counts[w] == 1} for pid, words in poi_words.items()}


def _find_matching_pois(message, pois):
    lowered = message.lower()
    unique_words = _unique_words_by_poi(pois)

    full_matches, word_matches = [], []
    for p in pois:
        name_lower = p["name"].lower()
        if name_lower in lowered:
            full_matches.append(p)
        elif any(w in lowered for w in unique_words.get(p["id"], set())):
            word_matches.append(p)

    seen, unique = set(), []
    for p in full_matches + word_matches:
        if p["id"] not in seen:
            unique.append(p)
            seen.add(p["id"])
    return unique


def _mentions_current_location(message):
    lowered = message.lower()
    if any(phrase in lowered for phrase in CURRENT_LOCATION_PHRASES):
        return True
    return "tropicana" in lowered and "carrefour" in lowered


def _looks_like_directions_query(message):
    lowered = message.lower()
    return any(phrase in lowered for phrase in DIRECTION_PHRASES)


def _poi_detail_line(p):
    line = f"{p['name']} — {p['address']}"
    if p.get("note"):
        line += f" ({p['note']})"
    if p.get("phone"):
        line += f" · {p['phone']}"
    return line


def _fallback_response(message, pois):
    named_matches = _find_matching_pois(message, pois)

    if _looks_like_directions_query(message):
        origin = destination = None
        if len(named_matches) >= 2:
            origin, destination = named_matches[0], named_matches[1]
        elif len(named_matches) == 1:
            destination = named_matches[0]
            origin = TROPICANA_LANDMARK

        if origin and destination:
            o_lat, o_lng = origin["lat"], origin["lng"]
            o_label = origin.get("label") or origin.get("name")
            d_lat, d_lng, d_label = destination["lat"], destination["lng"], destination["name"]
            km = _haversine_km(o_lat, o_lng, d_lat, d_lng)
            reply = (
                f"{o_label} to {d_label} is about {km:.1f} km as the crow flies. "
                f"I've drawn the real driving route on the map for you — check the "
                f"distance and time shown there for the actual road path."
            )
            action = {
                "type": "directions",
                "from": {"lat": o_lat, "lng": o_lng, "label": o_label},
                "to": {"lat": d_lat, "lng": d_lng, "label": d_label},
            }
            return reply, action

    if named_matches:
        p = named_matches[0]
        return (
            f"Here's what I have on {p['name']}:\n- {_poi_detail_line(p)}",
            {"type": "focus", "lat": p["lat"], "lng": p["lng"], "label": p["name"]},
        )

    if _mentions_current_location(message) and "tropicana" in message.lower():
        return (
            "Carrefour Tropicana is the main roundabout this whole guide is "
            "centered on — Neptune Tropicana fuel station and the CABTAL "
            "office both sit right on it. I've centered the map there for you.",
            {"type": "focus", "lat": TROPICANA_LANDMARK["lat"], "lng": TROPICANA_LANDMARK["lng"], "label": "Carrefour Tropicana"},
        )

    lowered = message.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            matches = [p for p in pois if p["category"] == category][:3]
            if matches:
                lines = [f"- {_poi_detail_line(p)}" for p in matches]
                return "Here's what I have near Tropicana:\n" + "\n".join(lines), None

    if any(g in lowered for g in ["hello", "hi", "mbolo", "hey"]):
        return (
            "Mbolo! I'm your Tropicana area guide. Ask me to find a specific "
            "place by name, ask about a category (hotels, restaurants, "
            "hospitals, pharmacies, schools, markets, fuel stations, banks, "
            "offices), or ask for directions between two places.",
            None,
        )
    if any(g in lowered for g in ["thank", "thanks", "merci"]):
        return "You're welcome! Safe travels around Tropicana.", None

    return (
        "I couldn't match that to a specific place in my data. Try naming a "
        "place directly (e.g. \"find CABTAL\"), asking about a category "
        "(hotels, restaurants, hospitals, pharmacies, schools, markets, fuel "
        "stations, banks, offices), or asking for directions between two "
        "named places.",
        None,
    )


@assistant_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@assistant_bp.route("/api/assistant", methods=["POST"])
def ask_assistant():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "message is required"}), 400

    pois = _get_all_pois()

    try:
        reply = _call_claude(message, history, pois)
        source = "live"
        _, action = _fallback_response(message, pois)
    except Exception as exc:  # noqa: BLE001 - deliberate broad catch for resilience
        current_app.logger.info("Falling back to local assistant: %s", exc)
        reply, action = _fallback_response(message, pois)
        source = "fallback"

    return jsonify({"reply": reply, "source": source, "action": action}), 200

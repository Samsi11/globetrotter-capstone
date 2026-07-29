"""
app/assistant.py

AI tour guide assistant endpoint.

Design note (resilience pattern):
    This endpoint tries a live Claude API call first, IF an ANTHROPIC_API_KEY
    is configured in the environment. If the key is missing, the request
    times out, or the API call fails for any reason, it automatically falls
    back to a lightweight, rule-based local assistant grounded in the same
    real POI data. The caller always gets a helpful answer either way — this
    graceful degradation is a deliberate design choice, not an accident.

The rule-based assistant understands three kinds of questions:
    1. Direct name lookups        — "find Pharmacie Tropicana"
    2. Category questions          — "where can I get fuel near here"
    3. Point-to-point directions    — "how do I get from Carrefour Tropicana
                                        to Pharmacie Tropicana"
For (3), it also returns a small "action" payload so the frontend can
automatically draw the real route on the map, not just describe it in text.

Routes
------
POST /api/assistant
    Body: {"message": "...", "history": [...]}
    Returns: {"reply": "...", "source": "live"|"fallback", "action": {...}|null}
"""
import math
import os

from flask import Blueprint, current_app, jsonify, request

from app.models import get_all_pois

assistant_bp = Blueprint("assistant", __name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

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
        "this specific area.\n\n"
        "Real, current data about places in and around the area:\n"
        f"{context}\n\n"
        "Ground your answers in this data whenever a question matches it, "
        "mentioning specific place names and short practical notes. If "
        "asked about something not covered in the data, say so honestly "
        "rather than inventing details. Keep answers conversational and "
        "concise."
    )


def _call_claude(message, history, pois):
    """Attempt a live Claude API call. Raises on any failure.

    'requests' is imported here, not at the top of the file, so the whole
    app can start and run perfectly (using the local fallback assistant)
    even on a machine where 'requests' isn't installed yet.
    """
    import requests  # local import — see docstring above

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
    """Straight-line ('as the crow flies') distance between two points."""
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
    """Map each POI id to the words in its name that don't appear in any
    other POI's name — so a shared word like 'Pharmacie' or 'Tropicana'
    can never be mistaken for a specific place on its own.
    """
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
    """Find POIs mentioned by name in the message, in the order they appear.

    Exact full-name mentions always count. A single distinctive word only
    counts if it's unique to that one place across the entire dataset —
    otherwise a shared word (e.g. two different "Pharmacie ..." names)
    could wrongly match the wrong business.
    """
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
    """Rule-based local assistant. Returns (reply_text, action_or_none)."""
    named_matches = _find_matching_pois(message, pois)

    # 1. Directions between two points
    if _looks_like_directions_query(message):
        origin = destination = None

        if len(named_matches) >= 2:
            origin, destination = named_matches[0], named_matches[1]
        elif len(named_matches) == 1:
            destination = named_matches[0]
            origin = TROPICANA_LANDMARK

        if origin and destination:
            o_lat = origin["lat"]
            o_lng = origin["lng"]
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

    # 2. Direct name lookup (e.g. "find Pharmacie Tropicana")
    if named_matches:
        p = named_matches[0]
        return (
            f"Here's what I have on {p['name']}:\n- {_poi_detail_line(p)}",
            {"type": "focus", "lat": p["lat"], "lng": p["lng"], "label": p["name"]},
        )

    # 2b. Mentions of the Tropicana landmark/roundabout itself
    if _mentions_current_location(message) and "tropicana" in message.lower():
        return (
            "Carrefour Tropicana is the main roundabout this whole guide is "
            "centered on — Neptune Tropicana fuel station and the CABTAL "
            "office both sit right on it. I've centered the map there for you.",
            {"type": "focus", "lat": TROPICANA_LANDMARK["lat"], "lng": TROPICANA_LANDMARK["lng"], "label": "Carrefour Tropicana"},
        )

    # 3. Category questions
    lowered = message.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            matches = [p for p in pois if p["category"] == category][:3]
            if matches:
                lines = [f"- {_poi_detail_line(p)}" for p in matches]
                return "Here's what I have near Tropicana:\n" + "\n".join(lines), None

    # 4. Small talk
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

    # 5. Nothing matched
    return (
        "I couldn't match that to a specific place in my data. Try naming a "
        "place directly (e.g. \"find CABTAL\"), asking about a category "
        "(hotels, restaurants, hospitals, pharmacies, schools, markets, fuel "
        "stations, banks, offices), or asking for directions between two "
        "named places.",
        None,
    )


@assistant_bp.route("/api/assistant", methods=["POST"])
def ask_assistant():
    """Answer a tour-guide question, grounded in the real POI dataset.

    Tries a live Claude call first (if ANTHROPIC_API_KEY is set); falls back
    to a rule-based local assistant on any failure, so this endpoint always
    returns a helpful answer rather than an error.
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "message is required"}), 400

    pois = get_all_pois()

    try:
        reply = _call_claude(message, history, pois)
        source = "live"
        _, action = _fallback_response(message, pois)
    except Exception as exc:  # noqa: BLE001 - deliberate broad catch for resilience
        current_app.logger.info("Falling back to local assistant: %s", exc)
        reply, action = _fallback_response(message, pois)
        source = "fallback"

    return jsonify({"reply": reply, "source": source, "action": action}), 200
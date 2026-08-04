"""
app/assistant.py — assistant-service

Wura: the local tour guide assistant for the Tropicana area. Tries a live
Claude API call first if ANTHROPIC_API_KEY is set; otherwise (and normally,
for this deployment) runs entirely on the local rule-based engine below —
which is the primary path, not a degraded fallback. POI data comes over
HTTP from locations-service (via Docker DNS).
"""
import difflib
import math
import os
import random
import re

import requests
from flask import Blueprint, current_app, jsonify, request

from app.db import (
    save_message,
    create_conversation,
    touch_conversation,
    get_conversations,
    get_conversation_owner,
    get_conversation_messages,
    delete_conversation,
)
from app.auth_util import get_user_id_from_request

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
    "get to", "get from", " to ", "take me", "get there",
]
CATEGORY_KEYWORDS = {
    "hotel": ["hotel", "stay", "sleep", "lodging", "room"],
    "restaurant": ["restaurant", "eat", "food", "dinner", "lunch", "grill", "meal"],
    "hospital": ["hospital", "clinic", "doctor", "emergency", "sick", "health"],
    "pharmacy": ["pharmacy", "pharmacies", "medicine", "drug", "chemist"],
    "school": ["school", "education", "class", "student"],
    "market": ["market", "shopping", "buy", "groceries", "supermarket"],
    "fuel": ["fuel", "petrol", "gas", "station", "diesel"],
    "bank": ["bank", "money", "atm", "withdraw", "cash"],
    "office": ["office", "organisation", "organization", "association"],
}
CATEGORY_LABELS = {
    "hotel": "Hotels", "restaurant": "Restaurants", "hospital": "Hospitals & Clinics",
    "pharmacy": "Pharmacies", "school": "Schools", "market": "Markets",
    "fuel": "Fuel Stations", "bank": "Banks", "office": "Offices & Organisations",
}

REFERENCE_PHRASES = [
    "it", "there", "that place", "them", "their", "its",
    "that one", "this place", "the place", "over there",
]
ATTRIBUTE_KEYWORDS = {
    "phone": ["phone", "number", "call", "contact"],
    "rating": ["rating", "rated", "review", "reviews", "stars"],
    "address": ["address", "located", "where is"],
}
WHOAMI_PHRASES = ["who are you", "what are you", "your name"]
HELP_PHRASES = ["what can you do", "help me", "how do you work", "how does this work"]

GENERIC_AREA_WORDS = {
    "tropicana", "carrefour", "yaounde", "yaoundé", "mvan",
    "ekoumdoum", "fokou", "odza", "amitie", "amitié",
}

FUZZY_CUTOFF = 0.78

LOOKUP_INTROS = [
    "Here's what I have on {name}:",
    "Sure — here's {name}:",
    "Found it — {name}:",
]
CATEGORY_INTROS = [
    "Here's what I have near Tropicana:",
    "A few options nearby:",
    "Here's what's around:",
]
GREETING_RESPONSES = [
    "Mbolo! I'm Wura, your Tropicana area guide. Ask me to find a specific "
    "place by name, ask about a category (hotels, restaurants, hospitals, "
    "pharmacies, schools, markets, fuel stations, banks, offices), or ask "
    "for directions between two places.",
    "Hey there! I'm Wura. Tell me a place name, a category, or ask for "
    "directions and I'll help you get around Tropicana.",
]
THANKS_RESPONSES = [
    "You're welcome! Safe travels around Tropicana.",
    "Anytime! Let me know if you need anything else around Tropicana.",
    "Happy to help — enjoy Tropicana!",
]
WHOAMI_RESPONSE = (
    "I'm Wura — a local guide for the Tropicana area in Mvan/Ekoumdoum, "
    "Yaoundé. I know real hotels, restaurants, hospitals, pharmacies, "
    "schools, markets, fuel stations, banks, and offices around here, and "
    "I can give you directions between any of them."
)
HELP_RESPONSE = (
    "You can ask me to find a place by name (\"find CABTAL\"), browse a "
    "category (\"any pharmacies nearby\"), get directions (\"how do I get "
    "to Mvan Market\"), or ask a follow-up about whatever we were just "
    "talking about (\"what's their number\")."
)


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
        "You are Wura, a warm, knowledgeable local tour guide assistant for "
        "the Tropicana area in Mvan/Ekoumdoum, Yaoundé, Cameroon. You help "
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


def _fuzzy_find_pois(message, pois):
    """Catch close-but-imperfect name matches (typos, a missing/extra
    letter) using string similarity. Only called when exact/word matching
    found nothing, so it never overrides a confident match with a guess.
    """
    lowered = message.lower()
    tokens = re.findall(r"[a-zà-ÿ]+", lowered)
    scored = []
    for p in pois:
        name_lower = p["name"].lower()
        best = difflib.SequenceMatcher(None, name_lower, lowered).ratio()
        for nw in [w for w in re.findall(r"[a-zà-ÿ]+", name_lower) if len(w) >= 4]:
            close = difflib.get_close_matches(nw, tokens, n=1, cutoff=FUZZY_CUTOFF)
            if close:
                best = max(best, difflib.SequenceMatcher(None, nw, close[0]).ratio())
        if best >= FUZZY_CUTOFF:
            scored.append((best, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:3]]


def _find_matching_pois(message, pois, allow_fuzzy=True):
    lowered = message.lower()
    unique_words = _unique_words_by_poi(pois)

    full_matches, word_matches = [], []
    for p in pois:
        name_lower = p["name"].lower()
        if name_lower in lowered:
            full_matches.append(p)
        elif any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in unique_words.get(p["id"], set())):
            word_matches.append(p)

    seen, unique = set(), []
    for p in full_matches + word_matches:
        if p["id"] not in seen:
            unique.append(p)
            seen.add(p["id"])

    if unique:
        return unique
    if not allow_fuzzy:
        return []
    return _fuzzy_find_pois(message, pois)


CATEGORY_BROWSE_WORDS = ["near", "nearby", "close by", "around", "close to"]


def _looks_like_category_browse(message):
    """True when the message reads as browsing a whole category ("any
    pharmacies nearby") rather than naming a specific place — used to stop
    the fuzzy typo-matcher from guessing a single place in these cases.
    """
    lowered = message.lower()
    has_category_kw = any(
        any(k in lowered for k in keywords) for keywords in CATEGORY_KEYWORDS.values()
    )
    has_browse_word = any(w in lowered for w in CATEGORY_BROWSE_WORDS)
    return has_category_kw and has_browse_word


def _mentions_reference(message):
    lowered = message.lower()
    return any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in REFERENCE_PHRASES)


def _last_mentioned_pois(history, pois):
    """Return every place mentioned in the most recent conversation turn
    (either side) that named at least one — so callers can tell a single
    clear reference (one place) from an ambiguous one (a list Wura gave,
    e.g. a category answer with several options).
    """
    for turn in reversed(history or []):
        content = turn.get("content", "")
        if not content:
            continue
        matches = _find_matching_pois(content, pois)
        if matches:
            return matches
    return []


def _resolve_subject(message, pois, history):
    """Returns (matches, ambiguous_candidates).

    matches: places named directly in the current message (possibly empty).
    ambiguous_candidates: set when the message uses a reference word
    ("it", "there", "their"...) and the most recently mentioned turn named
    MORE THAN ONE place — so Wura should ask which one, not guess. None
    when there's no ambiguity.
    """
    named_matches = _find_matching_pois(message, pois, allow_fuzzy=not _looks_like_category_browse(message))
    if named_matches:
        return named_matches, None
    if _mentions_reference(message):
        candidates = _last_mentioned_pois(history, pois)
        if len(candidates) == 1:
            return candidates, None
        if len(candidates) > 1:
            return [], candidates
    return [], None


def _ambiguous_reply(candidates):
    names = [c["name"] for c in candidates[:4]]
    if len(names) == 2:
        listing = f"{names[0]} or {names[1]}"
    else:
        listing = ", ".join(names[:-1]) + f", or {names[-1]}"
    return f"Just to be sure — which one did you mean: {listing}?"


def _detect_attribute_request(message):
    lowered = message.lower()
    for attribute, keywords in ATTRIBUTE_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return attribute
    return None


def _attribute_response(p, attribute):
    if attribute == "phone":
        if p.get("phone"):
            return f"{p['name']}'s number is {p['phone']}."
        return f"I don't have a phone number on file for {p['name']}."
    if attribute == "address":
        return f"{p['name']} is at {p['address']}."
    if attribute == "rating":
        if p.get("rating"):
            return f"{p['name']} is rated {p['rating']} out of 5."
        return f"I don't have a rating on file for {p['name']}."
    return None


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


def _generate_conversation_title(message, pois):
    named_matches = _find_matching_pois(message, pois)
    if _looks_like_directions_query(message) and named_matches:
        dest = named_matches[-1]
        return f"Directions to {dest['name']}"
    if named_matches:
        return named_matches[0]["name"]
    lowered = message.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return f"{CATEGORY_LABELS.get(category, category.title())} near Tropicana"
    title = message.strip()
    return (title[:40] + "…") if len(title) > 40 else (title or "New chat")


def _fallback_response(message, pois, history=None):
    history = history or []
    named_matches, ambiguous_candidates = _resolve_subject(message, pois, history)

    if ambiguous_candidates:
        return _ambiguous_reply(ambiguous_candidates), None

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
        attribute = _detect_attribute_request(message)
        if attribute:
            attr_reply = _attribute_response(p, attribute)
            if attr_reply:
                return attr_reply, {"type": "focus", "lat": p["lat"], "lng": p["lng"], "label": p["name"]}
        intro = random.choice(LOOKUP_INTROS).format(name=p["name"])
        return (
            f"{intro}\n- {_poi_detail_line(p)}",
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
                return random.choice(CATEGORY_INTROS) + "\n" + "\n".join(lines), None

    if any(phrase in lowered for phrase in WHOAMI_PHRASES):
        return WHOAMI_RESPONSE, None
    if any(phrase in lowered for phrase in HELP_PHRASES):
        return HELP_RESPONSE, None
    if any(g in lowered for g in ["hello", "hi", "mbolo", "hey"]):
        return random.choice(GREETING_RESPONSES), None
    if any(g in lowered for g in ["thank", "thanks", "merci"]):
        return random.choice(THANKS_RESPONSES), None

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
    conversation_id = data.get("conversation_id")

    if not message:
        return jsonify({"error": "message is required"}), 400

    user_id = get_user_id_from_request(request)
    pois = _get_all_pois()

    try:
        reply = _call_claude(message, history, pois)
        source = "live"
        _, action = _fallback_response(message, pois, history)
    except Exception as exc:  # noqa: BLE001 - deliberate broad catch for resilience
        current_app.logger.info("Falling back to local assistant: %s", exc)
        reply, action = _fallback_response(message, pois, history)
        source = "fallback"

    if user_id is not None:
        if conversation_id:
            owner = get_conversation_owner(conversation_id)
            if owner != user_id:
                conversation_id = None
        if not conversation_id:
            title = _generate_conversation_title(message, pois)
            conversation_id = create_conversation(user_id, title)
        save_message(conversation_id, "user", message)
        save_message(conversation_id, "assistant", reply, source)
        touch_conversation(conversation_id)

    return jsonify(
        {"reply": reply, "source": source, "action": action, "conversation_id": conversation_id}
    ), 200


@assistant_bp.route("/api/assistant/conversations", methods=["GET"])
def list_conversations():
    user_id = get_user_id_from_request(request)
    if user_id is None:
        return jsonify({"error": "Sign in to view your chats"}), 401
    return jsonify(get_conversations(user_id)), 200


@assistant_bp.route("/api/assistant/conversations/<int:conversation_id>/messages", methods=["GET"])
def conversation_messages(conversation_id):
    user_id = get_user_id_from_request(request)
    if user_id is None:
        return jsonify({"error": "Sign in to view your chats"}), 401
    owner = get_conversation_owner(conversation_id)
    if owner != user_id:
        return jsonify({"error": "Not found"}), 404
    return jsonify(get_conversation_messages(conversation_id)), 200


@assistant_bp.route("/api/assistant/conversations/<int:conversation_id>", methods=["DELETE"])
def remove_conversation(conversation_id):
    user_id = get_user_id_from_request(request)
    if user_id is None:
        return jsonify({"error": "Sign in required"}), 401
    owner = get_conversation_owner(conversation_id)
    if owner != user_id:
        return jsonify({"error": "Not found"}), 404
    delete_conversation(conversation_id)
    return jsonify({"status": "deleted"}), 200

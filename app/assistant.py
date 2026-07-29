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

Routes
------
POST /api/assistant
    Body: {"message": "...", "history": [{"role": "user"/"assistant", "content": "..."}]}
    Returns: {"reply": "...", "source": "live" | "fallback"}
"""
import os

from flask import Blueprint, current_app, jsonify, request

from app.models import get_all_pois

assistant_bp = Blueprint("assistant", __name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

CATEGORY_KEYWORDS = {
    "hotel": ["hotel", "stay", "sleep", "lodging", "room"],
    "restaurant": ["restaurant", "eat", "food", "dinner", "lunch", "grill", "meal"],
    "hospital": ["hospital", "clinic", "doctor", "emergency", "sick", "health"],
    "pharmacy": ["pharmacy", "medicine", "drug", "chemist"],
    "school": ["school", "education", "class", "student"],
    "market": ["market", "shopping", "buy", "groceries", "supermarket"],
    "fuel": ["fuel", "petrol", "gas", "station", "diesel"],
    "bank": ["bank", "money", "atm", "withdraw", "cash"],
}


def _build_system_prompt(pois):
    """Build the system prompt grounding the assistant in real POI data."""
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
        "pharmacies, schools, markets, fuel stations, and banks in this "
        "specific area.\n\n"
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
    even on a machine where 'requests' isn't installed yet. Only this one
    optional, upgrade-path function actually needs it.
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


def _fallback_response(message, pois):
    """Rule-based local assistant used when the live API is unavailable."""
    lowered = message.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            matches = [p for p in pois if p["category"] == category][:3]
            if matches:
                lines = []
                for p in matches:
                    line = f"- {p['name']} — {p['address']}"
                    if p.get("note"):
                        line += f" ({p['note']})"
                    lines.append(line)
                return "Here's what I have near Tropicana:\n" + "\n".join(lines)

    if any(g in lowered for g in ["hello", "hi", "mbolo", "hey"]):
        return (
            "Mbolo! I'm your Tropicana area guide. Ask me about hotels, "
            "restaurants, hospitals, pharmacies, schools, markets, fuel "
            "stations, or banks nearby."
        )
    if any(g in lowered for g in ["thank", "thanks", "merci"]):
        return "You're welcome! Safe travels around Tropicana."

    return (
        "I don't have specific information on that yet, but I can help you "
        "find hotels, restaurants, hospitals, pharmacies, schools, markets, "
        "fuel stations, or banks around Tropicana — just ask!"
    )


@assistant_bp.route("/api/assistant", methods=["POST"])
def ask_assistant():
    """Answer a tour-guide question, grounded in the real POI dataset.

    Expected JSON body:
        {
            "message": "where can I get fuel near here",
            "history": [{"role": "user", "content": "..."}, ...]   # optional
        }

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
    except Exception as exc:  # noqa: BLE001 - deliberate broad catch for resilience
        current_app.logger.info("Falling back to local assistant: %s", exc)
        reply = _fallback_response(message, pois)
        source = "fallback"

    return jsonify({"reply": reply, "source": source}), 200
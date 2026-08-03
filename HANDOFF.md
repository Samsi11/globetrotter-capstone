# Project Handoff — Tropicana Guide

**Purpose of this file:** paste or upload this into a new Claude conversation, alongside your GitHub repo link, so a fresh session can pick up exactly where this one left off without you re-explaining everything.

---

## How to start the new conversation

Open a new chat and say something like:

> "I'm continuing a project called Tropicana Guide — a location-based travel guide web app for Yaoundé, Cameroon, built with Flask. Here's the handoff doc from my last session, and here's my GitHub repo: [link]. Please read both and confirm you understand where things stand before we continue."

Then paste this whole file, and share the repo link. If your repo is private, either make it public temporarily, or upload the key files directly (`app/*.py`, `data/pois.json`, `static/js/app.js`, `templates/index.html`) as attachments instead.

---

## 1. What this project is

A university capstone (originally "GlobeTrotter," a generic distributed-systems exercise) that pivoted into a real product: a **travel/tour guide web app for the Tropicana area in Mvan/Ekoumdoum, Yaoundé, Cameroon**. Built for a lecturer who explicitly wants: real map integration, category-based POI search, real driving directions, and a conversational AI assistant — as a full working app with real UI/UX, not just a backend API demo.

This was a **make-up submission after an initial F**, built in a single overnight session under a hard deadline, then iterated on afterward.

## 2. Current tech stack

- **Backend:** Flask (Python), organized as an app factory (`app/__init__.py`) with two blueprints: `locations.py` (POI search) and `assistant.py` (AI assistant)
- **Data:** `data/pois.json` — real, sourced location data (not invented) for ~27 places across 9 categories (hotel, restaurant, hospital, pharmacy, school, market, fuel, bank, office)
- **Frontend:** Vanilla HTML/CSS/JS + Jinja2, single page (`templates/index.html`, `static/css/style.css`, `static/js/app.js`)
- **Map:** Leaflet.js + OpenStreetMap tiles (no API key needed)
- **Directions:** OSRM public routing API, called client-side from the browser
- **AI assistant:** Custom rule-based fallback engine in Python (name matching, category matching, point-to-point directions detection), with an **optional live Claude API upgrade path** that activates automatically if an `ANTHROPIC_API_KEY` is added to `.env` — currently running on the fallback only, since no key is configured yet
- **Containerization:** Docker + Docker Compose — confirmed working (`docker-compose up --build` builds and runs cleanly)
- **Testing:** pytest, 12 tests across `test_locations.py` and `test_assistant.py`, all passing, using isolated temp data

## 3. What's fully working and verified (not just written — actually tested)

- Full map with real markers, real data
- Search by name and by category
- Real driving directions via OSRM, drawn live on the map
- AI assistant: name lookup, category questions, point-to-point directions via chat (with the map auto-reacting to chat answers via an "action" payload system)
- Docker build and run, confirmed via `docker ps` showing the container properly bound to port 5000
- 6 real photos wired in for specific places (Santa Lucia Supermarket, Mvan Market, SIZZLE & SIP, Ladybird Group of Schools), shown as a large photo in the detail panel (not a tiny icon)

## 4. Known open items / not yet done

- **One placeholder photo**: TotalEnergies Ekoumdoum currently uses a generic (not verified real) stock-style photo, explicitly flagged in the data with `"image_placeholder": true`, which shows a visible "Reference photo — to be replaced" badge in the app itself. Needs a real photo of that actual station to fully resolve.
- **No live LLM key configured yet** — assistant runs on the rule-based fallback only. Getting an Anthropic API key (console.anthropic.com) would upgrade this automatically, no code changes needed.
- **No resizable sidebar** — requested once, deprioritized due to time; purely cosmetic, not started.
- **Most places still have no photo at all** (only 5 of ~27 have real photos so far) — the data model already supports adding more any time (just set the `"image"` field to a path and drop the file in `static/images/`).
- **Real microservices / Kubernetes / cloud deployment** (the original course's Phase 2–4 architecture) was deliberately not built as literal separate services given the timeline — the code is structured with clear service boundaries (blueprints) that could be split later, but this hasn't been done.
- **`.gitignore` may still need review** — worth double-checking `data/pois.json` is actually tracked in git and not accidentally excluded by an old ignore rule from the original project template.

## 5. Real bugs already found and fixed (useful history, don't reintroduce these)

1. **Docker Python version mismatch** — original Dockerfile used `python:3.9-slim`, which broke on newer type-hint syntax elsewhere in the project. Fixed by moving to `python:3.11-slim`.
2. **Docker/local module invocation** — running `python app/main.py` directly caused `ModuleNotFoundError`. Must run as `python -m app.main` (both locally and in the Dockerfile's `CMD`).
3. **AI assistant false-positive name matching** — generic words shared across multiple place names (e.g., "Tropicana," "Pharmacie") caused the assistant to match the wrong place. Fixed with a word-uniqueness map: a single word only counts as a match signal if it belongs to exactly one place in the whole dataset; otherwise the full name must match.
4. **`requests` import was too eager** — originally imported at the top of `assistant.py`, which crashed the whole app on any machine without that package installed, even though it's only needed for the optional live-AI path. Fixed by moving the import inside the function that actually uses it.
5. **Search endpoint didn't search descriptive notes** — originally only matched name/address/category, missing useful matches like "24 hour." Fixed by including the `note` field in the searchable text.

## 6. Suggested next steps, roughly in priority order

1. Get more real photos from the user (batches of 2-3 uploaded directly in chat) and wire them into `data/pois.json` + `static/images/`
2. Replace the TotalEnergies Ekoumdoum placeholder photo once a real one is available
3. Consider whether the lecturer wants to see any actual service decomposition (splitting `locations.py`/`assistant.py` into genuinely separate deployed services) for full marks on the original architecture requirements
4. Optional: resizable sidebar UI polish
5. Optional: if the user gets an Anthropic API key, test the live LLM path end-to-end (currently only the fallback path has been tested live)

## 7. Important context about how this user works (for the new Claude session)

- Works solo, on Windows, using VS Code + PowerShell, with a Python venv
- Has hit real environment friction before: PowerShell execution policy issues, path-with-spaces quoting, port/process confusion (old servers left running causing "site can't be reached" errors), download-link failures on this platform (had to have full files pasted directly into chat instead of relying on file download links)
- Prefers being walked through terminal commands exactly, one step at a time, with clear confirmation checkpoints
- Values honesty about limitations (e.g., was told directly that stock photos would misrepresent real places, and made an informed choice to use one placeholder temporarily with clear labeling rather than pretend it was verified)

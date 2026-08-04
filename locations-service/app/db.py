"""
app/db.py — Postgres access + POI seeding for locations-service.

data/pois.json (mounted read-only into this container) stays the curated,
human-edited source of truth. Every startup, sync_pois_from_json() upserts
it into the database — so adding a place is still just editing that file.
"""
import json
import os

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]
POIS_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pois.json"
)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def sync_pois_from_json():
    if not os.path.exists(POIS_JSON_PATH):
        return
    with open(POIS_JSON_PATH, "r", encoding="utf-8") as fh:
        pois = json.load(fh)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for p in pois:
                cur.execute(
                    """
                    INSERT INTO pois (id, name, category, lat, lng, address, phone, rating, note, image, image_placeholder)
                    VALUES (%(id)s, %(name)s, %(category)s, %(lat)s, %(lng)s, %(address)s, %(phone)s, %(rating)s, %(note)s, %(image)s, %(image_placeholder)s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name, category = EXCLUDED.category,
                        lat = EXCLUDED.lat, lng = EXCLUDED.lng,
                        address = EXCLUDED.address, phone = EXCLUDED.phone,
                        rating = EXCLUDED.rating, note = EXCLUDED.note,
                        image = EXCLUDED.image, image_placeholder = EXCLUDED.image_placeholder
                    """,
                    {
                        "id": p["id"], "name": p["name"], "category": p["category"],
                        "lat": p["lat"], "lng": p["lng"], "address": p.get("address"),
                        "phone": p.get("phone"), "rating": p.get("rating"),
                        "note": p.get("note"), "image": p.get("image"),
                        "image_placeholder": p.get("image_placeholder", False),
                    },
                )
        conn.commit()
    finally:
        conn.close()


def fetch_pois(q="", category=""):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            query = "SELECT * FROM pois WHERE 1=1"
            params = {}
            if category:
                query += " AND LOWER(category) = %(category)s"
                params["category"] = category.lower()
            if q:
                query += """ AND (
                    LOWER(name) LIKE %(q)s OR LOWER(address) LIKE %(q)s OR
                    LOWER(category) LIKE %(q)s OR LOWER(COALESCE(note, '')) LIKE %(q)s
                )"""
                params["q"] = f"%{q.lower()}%"
            query += " ORDER BY name ASC"
            cur.execute(query, params)
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                row["rating"] = float(row["rating"]) if row["rating"] is not None else None
            return rows
    finally:
        conn.close()

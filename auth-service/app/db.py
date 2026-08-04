"""
app/db.py — Postgres access for auth-service.
"""
import os

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def create_user(username, password_hash):
    """Insert a new user. Returns the new user's id, or None if the
    username is already taken."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
                (username, password_hash),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, username, created_at FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()

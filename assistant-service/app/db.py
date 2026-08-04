"""
app/db.py — Postgres access for assistant-service (conversations + chat history).
"""
import os

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def create_conversation(user_id, title):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id",
                (user_id, title),
            )
            conv_id = cur.fetchone()[0]
        conn.commit()
        return conv_id
    finally:
        conn.close()


def touch_conversation(conversation_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE conversations SET updated_at = NOW() WHERE id = %s", (conversation_id,))
        conn.commit()
    finally:
        conn.close()


def get_conversations(user_id):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE user_id = %s ORDER BY updated_at DESC",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_conversation_owner(conversation_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM conversations WHERE id = %s", (conversation_id,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def get_conversation_messages(conversation_id):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT role, content, source, created_at FROM chat_messages WHERE conversation_id = %s ORDER BY created_at ASC",
                (conversation_id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def delete_conversation(conversation_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
        conn.commit()
    finally:
        conn.close()


def save_message(conversation_id, role, content, source=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_messages (conversation_id, role, content, source) VALUES (%s, %s, %s, %s)",
                (conversation_id, role, content, source),
            )
        conn.commit()
    finally:
        conn.close()

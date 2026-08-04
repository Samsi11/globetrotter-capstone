"""
app/auth.py — auth-service

Optional accounts: register/login issue a JWT the client stores and sends
back as 'Authorization: Bearer <token>' on future requests. Nothing else in
the app requires an account — this service just proves who someone is, if
they choose to be someone.
"""
import datetime
import os

import jwt
from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import create_user, get_user_by_id, get_user_by_username

auth_bp = Blueprint("auth", __name__)

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME_DAYS = 30


def _make_token(user_id, username):
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_LIFETIME_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token):
    """Returns the payload dict if valid, or None if missing/expired/bad."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


@auth_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    password_hash = generate_password_hash(password)
    user_id = create_user(username, password_hash)
    if user_id is None:
        return jsonify({"error": "That username is already taken"}), 409

    token = _make_token(user_id, username)
    return jsonify({"token": token, "username": username}), 201


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    token = _make_token(user["id"], user["username"])
    return jsonify({"token": token, "username": user["username"]}), 200


@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "No token provided"}), 401

    payload = decode_token(auth_header.removeprefix("Bearer "))
    if not payload:
        return jsonify({"error": "Invalid or expired token"}), 401

    user = get_user_by_id(payload["user_id"])
    if not user:
        return jsonify({"error": "User no longer exists"}), 401

    return jsonify({"id": user["id"], "username": user["username"]}), 200

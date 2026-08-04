"""
app/auth_util.py — verifies JWTs issued by auth-service.

Deliberately duplicated rather than shared as a library, so this service
has no build-time dependency on auth-service's code.
"""
import os

import jwt

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"


def get_user_id_from_request(request):
    """Returns the user_id if a valid Bearer token is present, else None.
    Never raises — an invalid/missing token just means 'anonymous user'.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("user_id")
    except jwt.PyJWTError:
        return None

"""
Covenant Study — authentication helpers.

Session tokens live in users.db (userdata volume). Every request resolves
a token from either the Authorization: Bearer header or the __session cookie.
Tokens expire after 30 days but are extended on each use; the cleanup in
init_users_db() removes tokens idle for more than 7 days.
"""
import secrets
import time
from typing import Optional

from fastapi import Header, HTTPException, Request, Response

from database import get_users_db


# ---------------------------------------------------------------------------
# USER REPRESENTATION
# ---------------------------------------------------------------------------

class UserRow:
    """Thin wrapper around a row from the users table."""
    def __init__(self, id: int, username: str, display_name: Optional[str], role: str):
        self.id = id
        self.username = username
        self.display_name = display_name
        self.role = role


# ---------------------------------------------------------------------------
# TOKEN RESOLUTION
# ---------------------------------------------------------------------------

def _resolve_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    """Extract raw token from Authorization header or __session cookie.

    Prefers the Authorization header so API clients can omit cookies.
    """
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return request.cookies.get("__session")


# ---------------------------------------------------------------------------
# SESSION MANAGEMENT
# ---------------------------------------------------------------------------

def _create_session(conn, user_id: int) -> str:
    """Insert a new 30-day session token and return it."""
    token = secrets.token_hex(32)
    now = int(time.time())
    conn.execute(
        "INSERT INTO user_sessions(user_id, token, created_at, expires_at, last_active)"
        " VALUES(?, ?, ?, ?, ?)",
        (user_id, token, now, now + 2592000, now),  # 2592000 = 30 days
    )
    return token


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="__session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=2592000,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.set_cookie(
        key="__session",
        value="",
        httponly=True,
        samesite="lax",
        max_age=0,
        path="/",
    )


# ---------------------------------------------------------------------------
# FASTAPI DEPENDENCY FUNCTIONS
# ---------------------------------------------------------------------------

def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Optional[UserRow]:
    """Return the authenticated UserRow, or None if not authenticated.

    Also bumps last_active on the session so the 7-day idle window resets.
    """
    token = _resolve_token(request, authorization)
    if not token:
        return None
    now = int(time.time())
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT u.id, u.username, u.display_name, u.role "
            "FROM user_sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND (s.expires_at > ? OR s.last_active > ?)",
            (token, now, now - 604800),  # 604800 = 7 days idle grace
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE user_sessions SET last_active = ? WHERE token = ?",
            (now, token),
        )
        conn.commit()
        return UserRow(row[0], row[1], row[2], row[3])
    finally:
        conn.close()


def require_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> UserRow:
    """Dependency: return UserRow or raise HTTP 401."""
    user = get_current_user(request, authorization)
    if user is None:
        raise HTTPException(401, detail="Authentication required")
    return user


def require_admin(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> UserRow:
    """Dependency: return admin UserRow or raise HTTP 401/403."""
    user = get_current_user(request, authorization)
    if user is None:
        raise HTTPException(401, detail="Authentication required")
    if user.role != "admin":
        raise HTTPException(403, detail="Admin access required")
    return user

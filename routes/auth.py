"""Authentication endpoints — register, login, logout, me."""
import time
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from auth import (
    _clear_session_cookie,
    _create_session,
    _set_session_cookie,
    enforce_auth_rate_limit,
    get_current_user,
    require_user,
)
from database import get_users_db
from models import LoginBody, RegisterBody, UpdateMeBody

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Computed once at import time, not per-request — bcrypt.hashpw is the
# expensive part (that's the point), and this hash is never meant to match
# anything real. It exists purely so a login against a username that
# doesn't exist costs the same wall-clock time as a wrong password against
# one that does, closing the username-enumeration timing side channel in
# auth_login below.
_DUMMY_HASH = bcrypt.hashpw(b"covenant-study-timing-safety", bcrypt.gensalt(rounds=12))


@router.post("/register", status_code=201, dependencies=[Depends(enforce_auth_rate_limit)])
async def auth_register(body: RegisterBody, response: Response):
    """Register a new user account; returns session token + user object."""
    hashed = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
    conn = get_users_db()
    try:
        now = int(time.time())
        try:
            conn.execute(
                "INSERT INTO users(username, password_hash, display_name, role, created_at)"
                " VALUES(?, ?, ?, 'user', ?)",
                (body.username, hashed, body.display_name, now),
            )
        except Exception:
            raise HTTPException(409, detail="Username already taken")

        row = conn.execute(
            "SELECT id, display_name, role FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()
        uid, display_name, role = row[0], row[1], row[2]

        token = _create_session(conn, uid)
        conn.commit()
        _set_session_cookie(response, token)
        return {
            "token": token,
            "user": {"id": uid, "username": body.username, "display_name": display_name, "role": role},
        }
    finally:
        conn.close()


@router.post("/login", dependencies=[Depends(enforce_auth_rate_limit)])
async def auth_login(body: LoginBody, response: Response):
    """Authenticate with username + password; returns session token + user object."""
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id, password_hash, display_name, role FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()

        # Always run a bcrypt comparison, even for a username that doesn't
        # exist — checking `if not row` first and skipping straight to 401
        # would make unknown usernames fail fast while real ones take the
        # full bcrypt cost, letting an attacker enumerate valid usernames
        # purely from response timing.
        stored_hash = row[1].encode("utf-8") if row else _DUMMY_HASH
        password_ok = bcrypt.checkpw(body.password.encode("utf-8"), stored_hash)
        if not row or not password_ok:
            raise HTTPException(401, detail="Invalid credentials")

        uid, display_name, role = row[0], row[2], row[3]
        token = _create_session(conn, uid)
        conn.commit()
        _set_session_cookie(response, token)
        return {
            "token": token,
            "user": {"id": uid, "username": body.username, "display_name": display_name, "role": role},
        }
    finally:
        conn.close()


@router.post("/logout")
async def auth_logout(
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    """Delete the current session (idempotent)."""
    from auth import _resolve_token
    token = _resolve_token(request, authorization)
    if token:
        conn = get_users_db()
        try:
            conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()
    _clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me")
async def auth_me(request: Request, authorization: Optional[str] = Header(None)):
    """Return the currently authenticated user's profile."""
    user = get_current_user(request, authorization)
    if user is None:
        raise HTTPException(401, detail="Authentication required")
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }


@router.put("/me")
async def auth_update_me(
    body: UpdateMeBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Self-service profile update: display name and/or password.

    A password change requires the caller to prove they know the CURRENT
    password — a stolen session token is enough to read/write notes etc.,
    but should never be enough to permanently take over the account by
    changing the password out from under its real owner.
    """
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        if body.new_password is not None:
            if not body.current_password:
                raise HTTPException(400, detail="Current password is required to set a new one")
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user.id,)
            ).fetchone()
            if not row or not bcrypt.checkpw(
                body.current_password.encode("utf-8"), row[0].encode("utf-8")
            ):
                raise HTTPException(401, detail="Current password is incorrect")
            new_hash = bcrypt.hashpw(
                body.new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
            ).decode()
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user.id))

        if body.display_name is not None:
            conn.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (body.display_name.strip() or None, user.id),
            )

        conn.commit()
        row = conn.execute(
            "SELECT id, username, display_name, role FROM users WHERE id = ?", (user.id,)
        ).fetchone()
        return {"id": row[0], "username": row[1], "display_name": row[2], "role": row[3]}
    finally:
        conn.close()

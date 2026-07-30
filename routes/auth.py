"""Authentication endpoints — register, login, logout, me."""
import time
from typing import Optional

import bcrypt
from fastapi import APIRouter, Header, HTTPException, Request, Response

from auth import (
    _clear_session_cookie,
    _create_session,
    _set_session_cookie,
    get_current_user,
)
from database import get_users_db
from models import LoginBody, RegisterBody

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
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


@router.post("/login")
async def auth_login(body: LoginBody, response: Response):
    """Authenticate with username + password; returns session token + user object."""
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id, password_hash, display_name, role FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()
        if not row:
            raise HTTPException(401, detail="Invalid credentials")

        uid, stored_hash, display_name, role = row[0], row[1], row[2], row[3]
        if not bcrypt.checkpw(body.password.encode("utf-8"), stored_hash.encode("utf-8")):
            raise HTTPException(401, detail="Invalid credentials")

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

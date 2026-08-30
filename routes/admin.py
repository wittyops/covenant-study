"""Admin-only endpoints — user management."""
import time
from typing import Optional

import bcrypt
from fastapi import APIRouter, Header, HTTPException, Request

from auth import require_admin
from database import get_users_db
from models import AdminCreateUserBody, AdminResetPasswordBody

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
async def admin_list_users(request: Request, authorization: Optional[str] = Header(None)):
    """List all users. Admin only."""
    require_admin(request, authorization)
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT id, username, display_name, role FROM users ORDER BY id"
        ).fetchall()
        return [
            {"id": r[0], "username": r[1], "display_name": r[2] or "", "role": r[3] or "user"}
            for r in rows
        ]
    finally:
        conn.close()


@router.post("/users", status_code=201)
async def admin_create_user(
    body: AdminCreateUserBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Create a new user with a given role. Admin only.

    The frontend's AdminPanel has always called this endpoint
    (POST /api/admin/users) — it never had a handler until now, so every
    admin-created account silently failed with a 405.
    """
    require_admin(request, authorization)
    hashed = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
    conn = get_users_db()
    try:
        now = int(time.time())
        try:
            conn.execute(
                "INSERT INTO users(username, password_hash, display_name, role, created_at)"
                " VALUES(?, ?, ?, ?, ?)",
                (body.username, hashed, body.display_name, body.role, now),
            )
            conn.commit()
        except Exception:
            raise HTTPException(409, detail="Username already taken")

        row = conn.execute(
            "SELECT id, username, display_name, role FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()
        return {"id": row[0], "username": row[1], "display_name": row[2] or "", "role": row[3]}
    finally:
        conn.close()


@router.post("/users/{uid}/reset-password")
async def admin_reset_password(
    uid: int,
    body: AdminResetPasswordBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Reset any user's password. Admin only."""
    require_admin(request, authorization)
    hashed = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
    conn = get_users_db()
    try:
        result = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (hashed, uid)
        )
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(404, detail="User not found")
        return {"ok": True}
    finally:
        conn.close()

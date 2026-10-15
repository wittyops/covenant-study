"""Admin-only endpoints — user management."""
import time
from typing import Optional

import bcrypt
from fastapi import APIRouter, Header, HTTPException, Request

from auth import require_admin
from database import get_users_db
from models import AdminCreateUserBody, AdminResetPasswordBody, AdminUpdateUserBody

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
async def admin_list_users(request: Request, authorization: Optional[str] = Header(None)):
    """List all users. Admin only."""
    require_admin(request, authorization)
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT id, username, display_name, role, mfa_enabled FROM users ORDER BY id"
        ).fetchall()
        return [
            {
                "id": r[0],
                "username": r[1],
                "display_name": r[2] or "",
                "role": r[3] or "user",
                "mfa_enabled": bool(r[4]),
            }
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


def _admin_count(conn, excluding_uid: Optional[int] = None) -> int:
    if excluding_uid is None:
        return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin' AND id != ?", (excluding_uid,)
    ).fetchone()[0]


@router.put("/users/{uid}")
async def admin_update_user(
    uid: int,
    body: AdminUpdateUserBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Edit a user's display name and/or role. Admin only.

    Demoting the last remaining admin to 'user' is refused — that would
    strip admin access from the whole platform with no account left able
    to grant it back, a self-lockout that should never be reachable from a
    single click in the UI.
    """
    require_admin(request, authorization)
    conn = get_users_db()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(404, detail="User not found")

        if body.role is not None and body.role != "admin" and row[0] == "admin":
            if _admin_count(conn, excluding_uid=uid) == 0:
                raise HTTPException(409, detail="Cannot remove the last remaining admin")

        if body.display_name is not None:
            conn.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (body.display_name.strip() or None, uid),
            )
        if body.role is not None:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, uid))
        conn.commit()

        row = conn.execute(
            "SELECT id, username, display_name, role FROM users WHERE id = ?", (uid,)
        ).fetchone()
        return {"id": row[0], "username": row[1], "display_name": row[2] or "", "role": row[3]}
    finally:
        conn.close()


@router.delete("/users/{uid}", status_code=204)
async def admin_delete_user(
    uid: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Delete a user and everything they own. Admin only.

    All of a user's own data (sessions, bookmarks, notes, highlights,
    reading history, plan progress) is declared ON DELETE CASCADE in the
    schema and foreign_keys=ON is set on every connection, so this one
    DELETE cleans up everything without needing a manual fan-out.

    Two things this refuses, both to prevent locking the whole platform
    out of its own admin panel from a single click: deleting your own
    account, and deleting the last remaining admin.
    """
    admin = require_admin(request, authorization)
    if uid == admin.id:
        raise HTTPException(400, detail="You cannot delete your own account")
    conn = get_users_db()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(404, detail="User not found")
        if row[0] == "admin" and _admin_count(conn, excluding_uid=uid) == 0:
            raise HTTPException(409, detail="Cannot delete the last remaining admin")

        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()

"""Study session endpoints — save, restore, and manage named reading sessions."""
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from auth import require_user
from database import get_users_db
from models import SessionCreateBody, SessionUpdateBody

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(request: Request, authorization: Optional[str] = Header(None)):
    """List all saved sessions for the authenticated user, newest first."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT id, name, updated_at FROM study_sessions"
            " WHERE user_id = ? ORDER BY updated_at DESC",
            (user.id,),
        ).fetchall()
        return [{"id": r[0], "name": r[1], "updated_at": r[2]} for r in rows]
    finally:
        conn.close()


@router.post("", status_code=201)
async def create_session(
    body: SessionCreateBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Save a new named study session containing the full app state as JSON."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        cur = conn.execute(
            "INSERT INTO study_sessions(user_id, name, state_json, created_at, updated_at)"
            " VALUES(?, ?, ?, ?, ?)",
            (user.id, body.name, body.state_json, now, now),
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": body.name, "updated_at": now}
    finally:
        conn.close()


@router.get("/{sid}")
async def get_session(
    sid: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Return a single session including its full state JSON."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id, name, state_json, created_at, updated_at"
            " FROM study_sessions WHERE id = ? AND user_id = ?",
            (sid, user.id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return {
            "id": row[0], "name": row[1], "state_json": row[2],
            "created_at": row[3], "updated_at": row[4],
        }
    finally:
        conn.close()


@router.put("/{sid}")
async def update_session(
    sid: int,
    body: SessionUpdateBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Update session name and/or state JSON (COALESCE — omitted fields are unchanged)."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        result = conn.execute(
            "UPDATE study_sessions"
            " SET name = COALESCE(?, name), state_json = COALESCE(?, state_json), updated_at = ?"
            " WHERE id = ? AND user_id = ?",
            (body.name, body.state_json, now, sid, user.id),
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Session not found")
        conn.commit()
        row = conn.execute(
            "SELECT id, name, state_json, created_at, updated_at FROM study_sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        return {
            "id": row[0], "name": row[1], "state_json": row[2],
            "created_at": row[3], "updated_at": row[4],
        }
    finally:
        conn.close()


@router.delete("/{sid}", status_code=204)
async def delete_session(
    sid: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Delete a session. Returns 404 if not found or not owned by the user."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        result = conn.execute(
            "DELETE FROM study_sessions WHERE id = ? AND user_id = ?",
            (sid, user.id),
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Session not found")
        conn.commit()
    finally:
        conn.close()

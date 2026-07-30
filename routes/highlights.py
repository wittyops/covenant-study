"""Highlight endpoints — colour + optional note per verse reference."""
import time
from typing import Optional

from fastapi import APIRouter, Header, Request

from auth import get_current_user, require_user
from database import get_users_db
from models import HighlightCreateBody

router = APIRouter(prefix="/api/highlights", tags=["highlights"])


@router.get("")
async def list_highlights(request: Request, authorization: Optional[str] = Header(None)):
    """Return all highlights for the current user (empty list if unauthenticated)."""
    user = get_current_user(request, authorization)
    if user is None:
        return []
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT ref, color, note, created_at FROM highlights"
            " WHERE user_id = ? ORDER BY created_at DESC",
            (user.id,),
        ).fetchall()
        return [{"ref": r[0], "color": r[1], "note": r[2], "created_at": r[3]} for r in rows]
    finally:
        conn.close()


@router.post("", status_code=201)
async def set_highlight(
    body: HighlightCreateBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Create or update a highlight (upsert on user_id + ref)."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            "INSERT INTO highlights(user_id, ref, color, note, created_at) VALUES(?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, ref) DO UPDATE SET color = excluded.color, note = excluded.note",
            (user.id, body.ref, body.color, body.note, now),
        )
        conn.commit()
        return {"ref": body.ref, "color": body.color, "note": body.note}
    finally:
        conn.close()


@router.delete("/{ref:path}", status_code=204)
async def delete_highlight(
    ref: str,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Remove a highlight. Silent success if it doesn't exist."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        conn.execute(
            "DELETE FROM highlights WHERE user_id = ? AND ref = ?",
            (user.id, ref),
        )
        conn.commit()
    finally:
        conn.close()

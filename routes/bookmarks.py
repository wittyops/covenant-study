"""Bookmark endpoints.

Note: /check MUST be registered before /{bid} so FastAPI doesn't try to
match the literal string "check" as a bookmark ID integer.
"""
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from auth import get_current_user, require_user
from database import get_users_db
from models import BookmarkCreateBody

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


@router.get("/check")
async def check_bookmark(
    ref: str = Query(...),
    request: Request = None,  # type: ignore[assignment]
    authorization: Optional[str] = Header(None),
):
    """Return whether the current user has bookmarked a reference (unauthenticated → False)."""
    if request is None:
        return {"bookmarked": False}
    user = get_current_user(request, authorization)
    if user is None:
        return {"bookmarked": False}
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id FROM bookmarks WHERE user_id = ? AND ref = ?",
            (user.id, ref),
        ).fetchone()
        return {"bookmarked": bool(row), "id": row[0] if row else None}
    finally:
        conn.close()


@router.get("")
async def list_bookmarks(request: Request, authorization: Optional[str] = Header(None)):
    """Return all bookmarks for the current user, newest first."""
    user = get_current_user(request, authorization)
    if user is None:
        return []
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT id, ref, label, color, created_at FROM bookmarks"
            " WHERE user_id = ? ORDER BY created_at DESC",
            (user.id,),
        ).fetchall()
        return [
            {"id": r[0], "ref": r[1], "label": r[2], "color": r[3], "created_at": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


@router.post("", status_code=201)
async def create_bookmark(
    body: BookmarkCreateBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Create or update a bookmark (upsert on user_id + ref)."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            "INSERT INTO bookmarks(user_id, ref, label, color, created_at) VALUES(?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, ref) DO UPDATE SET label = excluded.label, color = excluded.color",
            (user.id, body.ref, body.label, body.color, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, ref, label, color, created_at FROM bookmarks WHERE user_id = ? AND ref = ?",
            (user.id, body.ref),
        ).fetchone()
        return {"id": row[0], "ref": row[1], "label": row[2], "color": row[3], "created_at": row[4]}
    finally:
        conn.close()


@router.delete("/{bid}", status_code=204)
async def delete_bookmark(
    bid: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Delete a bookmark by ID. The user_id check prevents cross-user deletion."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        result = conn.execute(
            "DELETE FROM bookmarks WHERE id = ? AND user_id = ?",
            (bid, user.id),
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Bookmark not found")
        conn.commit()
    finally:
        conn.close()

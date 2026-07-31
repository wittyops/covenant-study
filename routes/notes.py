"""User notes endpoints — one note per user per scripture reference."""
import time
from typing import Optional

from fastapi import APIRouter, Header, Request

from auth import require_user
from database import get_users_db
from models import NoteBody

router = APIRouter(tags=["notes"])


@router.get("/api/note/{ref:path}")
async def get_note(
    ref: str,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Return the authenticated user's note for this reference, or empty body."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT body, updated_at FROM notes WHERE user_id = ? AND ref = ?",
            (user.id, ref),
        ).fetchone()
        return {"ref": ref, "body": row[0] if row else "", "updated_at": row[1] if row else None}
    finally:
        conn.close()


@router.post("/api/note/{ref:path}")
async def save_note(
    ref: str,
    body: NoteBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Insert or update the authenticated user's note for this reference."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            "INSERT INTO notes(user_id, ref, body, updated_at) VALUES(?, ?, ?, ?)"
            " ON CONFLICT(user_id, ref) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at",
            (user.id, ref, body.body, now),
        )
        conn.commit()
        return {"status": "ok", "ref": ref, "updated_at": now}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# REACT SPA COMPAT — /api/notes/* (plural path + PUT method)
# ---------------------------------------------------------------------------

@router.get("/api/notes/{ref:path}")
async def get_note_plural(
    ref: str,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    return await get_note(ref=ref, request=request, authorization=authorization)


@router.put("/api/notes/{ref:path}")
async def save_note_plural(
    ref: str,
    body: NoteBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    return await save_note(ref=ref, body=body, request=request, authorization=authorization)

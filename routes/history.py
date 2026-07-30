"""Reading history endpoints — rolling 100-entry log per user."""
import time
from typing import Optional

from fastapi import APIRouter, Header, Request

from auth import require_user
from database import get_users_db
from models import HistoryBody

router = APIRouter(prefix="/api/history", tags=["history"])

# Keep at most this many history entries per user. Older entries are pruned
# in the same transaction as each new insert so the table stays bounded.
_HISTORY_LIMIT = 100


@router.post("", status_code=201)
async def add_history(
    body: HistoryBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Record a verse/chapter visit. Prunes entries beyond the rolling limit."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            "INSERT INTO reading_history(user_id, ref, visited_at) VALUES(?, ?, ?)",
            (user.id, body.ref, now),
        )
        # Keep only the most recent _HISTORY_LIMIT entries; delete the rest.
        conn.execute(
            "DELETE FROM reading_history WHERE user_id = ?"
            "  AND id NOT IN ("
            "    SELECT id FROM reading_history WHERE user_id = ?"
            "    ORDER BY visited_at DESC LIMIT ?"
            "  )",
            (user.id, user.id, _HISTORY_LIMIT),
        )
        conn.commit()
        return {"ref": body.ref, "visited_at": now}
    finally:
        conn.close()


@router.get("")
async def get_history(request: Request, authorization: Optional[str] = Header(None)):
    """Return the 20 most recently visited references."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT ref, visited_at FROM reading_history"
            " WHERE user_id = ? ORDER BY visited_at DESC LIMIT 20",
            (user.id,),
        ).fetchall()
        return [{"ref": r[0], "visited_at": r[1]} for r in rows]
    finally:
        conn.close()

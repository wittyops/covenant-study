"""Reading plan endpoints — catalogue + per-user progress tracking."""
import time
from typing import Optional

from fastapi import APIRouter, Header, Request

from auth import get_current_user, require_user
from database import get_users_db
from models import READING_PLANS_META, ReadingPlanProgressBody

router = APIRouter(prefix="/api/reading-plans", tags=["plans"])


@router.get("")
async def list_reading_plans():
    """Return the static catalogue of available reading plans."""
    return READING_PLANS_META


@router.get("/progress")
async def get_reading_plan_progress(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Return all in-progress plans for the current user (empty list if unauthenticated)."""
    user = get_current_user(request, authorization)
    if user is None:
        return []
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT plan_id, day_index, started_at, updated_at"
            " FROM reading_plan_progress WHERE user_id = ?",
            (user.id,),
        ).fetchall()
        return [{"plan_id": r[0], "day_index": r[1], "started_at": r[2], "updated_at": r[3]} for r in rows]
    finally:
        conn.close()


@router.post("/progress", status_code=200)
async def update_reading_plan_progress(
    body: ReadingPlanProgressBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Upsert the current user's progress for a plan (started_at only set on first insert)."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            "INSERT INTO reading_plan_progress(user_id, plan_id, day_index, started_at, updated_at)"
            " VALUES(?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, plan_id)"
            " DO UPDATE SET day_index = excluded.day_index, updated_at = excluded.updated_at",
            (user.id, body.plan_id, body.day_index, now, now),
        )
        conn.commit()
        return {"plan_id": body.plan_id, "day_index": body.day_index, "updated_at": now}
    finally:
        conn.close()


@router.delete("/progress/{plan_id}", status_code=204)
async def reset_reading_plan_progress(
    plan_id: str,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Delete all progress for a plan (user can restart from day 0)."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        conn.execute(
            "DELETE FROM reading_plan_progress WHERE user_id = ? AND plan_id = ?",
            (user.id, plan_id),
        )
        conn.commit()
    finally:
        conn.close()

"""
Covenant Study — Pydantic request/response models.

All route handlers that accept a JSON body import their model from here.
Keeping them in one file makes validation rules easy to audit at a glance.
"""
from typing import Optional
from pydantic import BaseModel, Field


class RegisterBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None


class LoginBody(BaseModel):
    username: str
    password: str


class AdminResetPasswordBody(BaseModel):
    password: str = Field(..., min_length=8)


class AdminCreateUserBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None
    role: str = Field("user", pattern=r"^(user|admin)$")


class AdminUpdateUserBody(BaseModel):
    """Admin edit of another user's profile — display name and/or role.

    Username and password are deliberately not editable here: username is
    the account's stable identity, and password changes go through the
    dedicated reset-password endpoint so that flow stays auditable as its
    own action rather than folded into a generic PATCH-everything body.
    """
    display_name: Optional[str] = None
    role: Optional[str] = Field(None, pattern=r"^(user|admin)$")


class UpdateMeBody(BaseModel):
    """Self-service profile update — the authenticated user's own account.

    A password change requires current_password so a stolen/leaked session
    token alone isn't enough to lock the real owner out of their own
    account; display_name has no such requirement since it carries no
    access implications.
    """
    display_name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = Field(None, min_length=8)


class SessionCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    state_json: str


class SessionUpdateBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    state_json: Optional[str] = None


class BookmarkCreateBody(BaseModel):
    ref: str = Field(..., min_length=1)
    label: Optional[str] = None
    color: str = "#b8962e"


class HistoryBody(BaseModel):
    ref: str = Field(..., min_length=1)


class NoteBody(BaseModel):
    body: str = ""


class HighlightCreateBody(BaseModel):
    ref: str = Field(..., min_length=1)
    color: str = "#ffeb3b"
    note: Optional[str] = None


class HighlightSetBody(BaseModel):
    # ref comes from the URL path on PUT /api/highlights/{ref} — not the body.
    color: str = "#ffeb3b"
    note: Optional[str] = None


class ReadingPlanProgressBody(BaseModel):
    plan_id: str = Field(..., min_length=1)
    day_index: int = 0


# ---------------------------------------------------------------------------
# STATIC DATA — reading plan catalogue
# ---------------------------------------------------------------------------

# Plan metadata lives here rather than in a database because the plans
# themselves are not user-editable; only progress tracking is persisted.
READING_PLANS_META = [
    {
        "id": "bible-in-a-year",
        "name": "Bible in a Year",
        "description": "Read the entire Bible in 365 days with balanced OT/NT daily readings.",
        "days": 365,
        "category": "Complete Bible",
    },
    {
        "id": "nt-90-days",
        "name": "New Testament in 90 Days",
        "description": "Read the entire New Testament in 90 days (~3 chapters per day).",
        "days": 90,
        "category": "New Testament",
    },
    {
        "id": "gospels-28",
        "name": "Gospels Survey",
        "description": "Matthew, Mark, Luke, and John in 28 days.",
        "days": 28,
        "category": "Gospels",
    },
    {
        "id": "psalms-proverbs-30",
        "name": "Psalms & Proverbs",
        "description": "A Psalm and a chapter of Proverbs each day for 30 days.",
        "days": 30,
        "category": "Wisdom",
    },
    {
        "id": "pauline-21",
        "name": "Pauline Epistles",
        "description": "Romans through Philemon — 13 letters in 21 days.",
        "days": 21,
        "category": "Epistles",
    },
]

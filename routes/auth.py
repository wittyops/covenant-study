"""Authentication endpoints — register, login, logout, me."""
import time
from typing import Optional

import bcrypt
import pyotp
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from auth import (
    _clear_session_cookie,
    _create_session,
    _set_session_cookie,
    consume_pending_mfa_token,
    create_pending_mfa_token,
    enforce_auth_rate_limit,
    get_current_user,
    require_user,
    resolve_pending_mfa_token,
)
from database import get_users_db
from models import (
    LoginBody,
    MfaConfirmBody,
    MfaDisableBody,
    MfaVerifyLoginBody,
    RegisterBody,
    UpdateMeBody,
)

TOTP_ISSUER = "Covenant Study"

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Computed once at import time, not per-request — bcrypt.hashpw is the
# expensive part (that's the point), and this hash is never meant to match
# anything real. It exists purely so a login against a username that
# doesn't exist costs the same wall-clock time as a wrong password against
# one that does, closing the username-enumeration timing side channel in
# auth_login below.
_DUMMY_HASH = bcrypt.hashpw(b"covenant-study-timing-safety", bcrypt.gensalt(rounds=12))


@router.post("/register", status_code=201, dependencies=[Depends(enforce_auth_rate_limit)])
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
            "user": {
                "id": uid,
                "username": body.username,
                "display_name": display_name,
                "role": role,
                "mfa_enabled": False,  # new accounts always start without MFA
            },
        }
    finally:
        conn.close()


@router.post("/login", dependencies=[Depends(enforce_auth_rate_limit)])
async def auth_login(body: LoginBody, response: Response):
    """Authenticate with username + password.

    Returns a full session (token + user) for an account without MFA.  For
    an MFA-enabled account, the password alone is deliberately NOT enough —
    returns {"mfa_required": true, "pending_token": ...} instead, with no
    cookie set, and the caller must complete POST /api/auth/mfa/verify-login
    with that token + a TOTP code before a real session exists.
    """
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id, password_hash, display_name, role, mfa_enabled FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()

        # Always run a bcrypt comparison, even for a username that doesn't
        # exist — checking `if not row` first and skipping straight to 401
        # would make unknown usernames fail fast while real ones take the
        # full bcrypt cost, letting an attacker enumerate valid usernames
        # purely from response timing.
        stored_hash = row[1].encode("utf-8") if row else _DUMMY_HASH
        password_ok = bcrypt.checkpw(body.password.encode("utf-8"), stored_hash)
        if not row or not password_ok:
            raise HTTPException(401, detail="Invalid credentials")

        uid, display_name, role, mfa_enabled = row[0], row[2], row[3], row[4]

        if mfa_enabled:
            pending_token = create_pending_mfa_token(uid)
            return {"mfa_required": True, "pending_token": pending_token}

        token = _create_session(conn, uid)
        conn.commit()
        _set_session_cookie(response, token)
        return {
            "token": token,
            "user": {
                "id": uid,
                "username": body.username,
                "display_name": display_name,
                "role": role,
                "mfa_enabled": False,
            },
        }
    finally:
        conn.close()


@router.post("/mfa/verify-login", dependencies=[Depends(enforce_auth_rate_limit)])
async def auth_mfa_verify_login(body: MfaVerifyLoginBody, response: Response):
    """Second step of login for an MFA-enabled account.

    Rate-limited by the same IP-bucket as /login and /register — a 6-digit
    TOTP code is only 1,000,000 possibilities, so this endpoint needs the
    same brute-force protection password login gets, not a separate,
    looser budget.
    """
    user_id = resolve_pending_mfa_token(body.pending_token)
    if user_id is None:
        raise HTTPException(401, detail="Login session expired — sign in again")

    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id, username, display_name, role, totp_secret FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row or not row[4]:
            # mfa_enabled was true but totp_secret is somehow missing —
            # shouldn't happen (confirm is what sets mfa_enabled), but fail
            # closed rather than crash on pyotp.TOTP(None).
            raise HTTPException(401, detail="MFA is not configured for this account")

        totp = pyotp.TOTP(row[4])
        if not totp.verify(body.code, valid_window=1):
            raise HTTPException(401, detail="Invalid code")

        consume_pending_mfa_token(body.pending_token)
        uid, username, display_name, role = row[0], row[1], row[2], row[3]
        token = _create_session(conn, uid)
        conn.commit()
        _set_session_cookie(response, token)
        return {
            "token": token,
            "user": {
                "id": uid,
                "username": username,
                "display_name": display_name,
                "role": role,
                "mfa_enabled": True,
            },
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
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT mfa_enabled FROM users WHERE id = ?", (user.id,)
        ).fetchone()
    finally:
        conn.close()
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "mfa_enabled": bool(row[0]) if row else False,
    }


@router.put("/me")
async def auth_update_me(
    body: UpdateMeBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Self-service profile update: display name and/or password.

    A password change requires the caller to prove they know the CURRENT
    password — a stolen session token is enough to read/write notes etc.,
    but should never be enough to permanently take over the account by
    changing the password out from under its real owner.
    """
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        if body.new_password is not None:
            if not body.current_password:
                raise HTTPException(400, detail="Current password is required to set a new one")
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user.id,)
            ).fetchone()
            if not row or not bcrypt.checkpw(
                body.current_password.encode("utf-8"), row[0].encode("utf-8")
            ):
                raise HTTPException(401, detail="Current password is incorrect")
            new_hash = bcrypt.hashpw(
                body.new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
            ).decode()
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user.id))

        if body.display_name is not None:
            conn.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (body.display_name.strip() or None, user.id),
            )

        conn.commit()
        row = conn.execute(
            "SELECT id, username, display_name, role, mfa_enabled FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
        return {
            "id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "mfa_enabled": bool(row[4]),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MFA (TOTP) — enrollment, confirmation, disable
# ---------------------------------------------------------------------------

@router.post("/mfa/enroll")
async def auth_mfa_enroll(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Start enrollment: generate a new TOTP secret and store it, but leave
    mfa_enabled off until /mfa/confirm proves the user actually captured it.
    Calling this again before confirming simply overwrites the pending
    secret — there's nothing to lose, since nothing was ever activated.
    """
    user = require_user(request, authorization)
    secret = pyotp.random_base32()
    conn = get_users_db()
    try:
        conn.execute(
            "UPDATE users SET totp_secret = ?, mfa_enabled = 0 WHERE id = ?",
            (secret, user.id),
        )
        conn.commit()
    finally:
        conn.close()

    otpauth_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name=TOTP_ISSUER
    )
    return {"secret": secret, "otpauth_uri": otpauth_uri}


@router.post("/mfa/confirm")
async def auth_mfa_confirm(
    body: MfaConfirmBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Finish enrollment: verify a live code against the secret /mfa/enroll
    just stored, and only then flip mfa_enabled on."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT totp_secret FROM users WHERE id = ?", (user.id,)
        ).fetchone()
        if not row or not row[0]:
            raise HTTPException(400, detail="Call /mfa/enroll first")

        totp = pyotp.TOTP(row[0])
        if not totp.verify(body.code, valid_window=1):
            raise HTTPException(400, detail="Invalid code — try again")

        conn.execute("UPDATE users SET mfa_enabled = 1 WHERE id = ?", (user.id,))
        conn.commit()
        return {"status": "ok", "mfa_enabled": True}
    finally:
        conn.close()


@router.post("/mfa/disable")
async def auth_mfa_disable(
    body: MfaDisableBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Turn MFA off — requires the current password, same reasoning as a
    password change (see auth_update_me): a stolen session token alone
    shouldn't be enough to strip the account's second factor."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user.id,)
        ).fetchone()
        if not row or not bcrypt.checkpw(body.password.encode("utf-8"), row[0].encode("utf-8")):
            raise HTTPException(401, detail="Current password is incorrect")

        conn.execute(
            "UPDATE users SET mfa_enabled = 0, totp_secret = NULL WHERE id = ?",
            (user.id,),
        )
        conn.commit()
        return {"status": "ok", "mfa_enabled": False}
    finally:
        conn.close()

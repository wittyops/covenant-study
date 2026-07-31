"""
Covenant Study — FastAPI application entry point.

This file owns:
  - App creation and lifespan hooks
  - Static file mounting (/static → /app/static)
  - Template engine initialisation (Jinja2 → /app/templates)
  - Router registration (one include per domain module)
  - The single HTML-serving root route

Everything else lives in separate modules:
  config.py   — BOOKS, TRANSLATIONS, PLACES and runtime paths
  database.py — SQLite connection helpers + startup self-check
  auth.py     — session token resolution and dependency functions
  models.py   — Pydantic request/response bodies
  routes/     — one file per API domain (bible, auth, admin, …)
"""
import os
import secrets
import time

import bcrypt
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import DATA, NOTES
from database import get_users_db, verify_data_layer
from routes import bible, auth, admin, sessions, bookmarks, history, notes, highlights, plans, fragments

# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Covenant Study",
    description="Scripture study platform — Strong's, interlinear, maps, cross-references.",
    docs_url=None,   # Swagger UI disabled in production
    redoc_url=None,
)

# Serve CSS, JS, and other static assets from the container's /app/static directory.
# The browser caches these independently; the Python string embedding is gone.
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

templates = Jinja2Templates(directory="/app/templates")


# ---------------------------------------------------------------------------
# ROUTER REGISTRATION
# ---------------------------------------------------------------------------

app.include_router(bible.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(sessions.router)
app.include_router(bookmarks.router)
app.include_router(history.router)
app.include_router(notes.router)
app.include_router(highlights.router)
app.include_router(plans.router)
app.include_router(fragments.router)


# ---------------------------------------------------------------------------
# ROOT ROUTE
# ---------------------------------------------------------------------------

_SPA_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/", response_class=HTMLResponse)
async def index(_request: Request) -> FileResponse:
    """Serve the React SPA entry point."""
    return FileResponse("/app/static/dist/index.html", headers=_SPA_HEADERS)


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(_request: Request, full_path: str) -> FileResponse:
    """Catch-all SPA fallback — API routes registered before this handler take priority."""
    _ = full_path
    return FileResponse("/app/static/dist/index.html", headers=_SPA_HEADERS)


# ---------------------------------------------------------------------------
# STARTUP: DB schema init, legacy migration, self-check
# ---------------------------------------------------------------------------

def init_users_db() -> None:
    """Create users.db tables if absent; seed admin account if table is empty."""
    DATA.mkdir(parents=True, exist_ok=True)
    conn = get_users_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                display_name  TEXT,
                role          TEXT    NOT NULL DEFAULT 'user',
                created_at    INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token       TEXT    NOT NULL UNIQUE,
                created_at  INTEGER NOT NULL,
                expires_at  INTEGER NOT NULL,
                last_active INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token);
            CREATE INDEX IF NOT EXISTS idx_sessions_user  ON user_sessions(user_id);

            CREATE TABLE IF NOT EXISTS bookmarks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ref        TEXT    NOT NULL,
                label      TEXT,
                color      TEXT    NOT NULL DEFAULT '#b8962e',
                created_at INTEGER NOT NULL,
                UNIQUE (user_id, ref)
            );
            CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id);

            CREATE TABLE IF NOT EXISTS study_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name       TEXT    NOT NULL,
                state_json TEXT    NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_study_sessions_user
                ON study_sessions(user_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ref        TEXT    NOT NULL,
                body       TEXT    NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL,
                UNIQUE (user_id, ref)
            );
            CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
            CREATE INDEX IF NOT EXISTS idx_notes_ref  ON notes(ref);

            CREATE TABLE IF NOT EXISTS reading_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ref        TEXT    NOT NULL,
                visited_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_history_user
                ON reading_history(user_id, visited_at DESC);

            CREATE TABLE IF NOT EXISTS highlights (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ref        TEXT    NOT NULL,
                color      TEXT    NOT NULL DEFAULT '#ffeb3b',
                note       TEXT,
                created_at INTEGER NOT NULL,
                UNIQUE (user_id, ref)
            );
            CREATE INDEX IF NOT EXISTS idx_highlights_user ON highlights(user_id);

            CREATE TABLE IF NOT EXISTS reading_plan_progress (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                plan_id     TEXT    NOT NULL,
                day_index   INTEGER NOT NULL DEFAULT 0,
                started_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL,
                UNIQUE (user_id, plan_id)
            );
            CREATE INDEX IF NOT EXISTS idx_plan_progress_user ON reading_plan_progress(user_id);
        """)

        # Seed an admin account on the very first boot when the users table is empty.
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            username = os.environ.get("ADMIN_USERNAME", "admin")
            password = os.environ.get("ADMIN_PASSWORD") or secrets.token_hex(12)
            hashed   = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
            conn.execute(
                "INSERT INTO users(username, password_hash, display_name, role, created_at)"
                " VALUES(?, ?, 'Administrator', 'admin', ?)",
                (username, hashed, int(time.time())),
            )
            conn.commit()
            if os.environ.get("ADMIN_PASSWORD"):
                print(f"[startup] Admin account created: {username}", flush=True)
            else:
                print(f"[startup] Admin account created. Username: {username}  Password: {password}", flush=True)
                print("[startup] Set ADMIN_PASSWORD env var to control this on next fresh deploy.", flush=True)

        # Prune sessions idle for more than 7 days to keep the DB trim.
        now = int(time.time())
        conn.execute(
            "DELETE FROM user_sessions WHERE expires_at < ? AND last_active < ?",
            (now, now - 604800),
        )
        conn.commit()
    finally:
        conn.close()


def migrate_file_notes() -> None:
    """One-time migration: import legacy /app/notes/*.md files as the admin user's notes.

    Runs only when the notes table is empty to avoid re-importing on every restart.
    The /app/notes volume is kept for backward compatibility but is no longer written to.
    """
    notes_dir = NOTES
    if not notes_dir.exists():
        return
    conn = get_users_db()
    try:
        if conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] > 0:
            return
        admin = conn.execute(
            "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1"
        ).fetchone()
        if not admin:
            return
        admin_id = admin[0]

        migrated = 0
        for note_file in notes_dir.glob("*.md"):
            stem  = note_file.stem
            parts = stem.split("_")
            # Filename format: BookName_chapter_verse.md (from legacy export)
            if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
                ref = " ".join(parts[:-2]) + f" {parts[-2]}:{parts[-1]}"
            else:
                ref = stem.replace("_", " ")
            try:
                body = note_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if body.strip():
                conn.execute(
                    "INSERT OR IGNORE INTO notes(user_id, ref, body, updated_at) VALUES(?,?,?,?)",
                    (admin_id, ref, body, int(time.time())),
                )
                migrated += 1

        if migrated > 0:
            conn.commit()
            print(f"[startup] Migrated {migrated} legacy note(s) to admin user.", flush=True)
    finally:
        conn.close()


@app.on_event("startup")
async def startup_event():
    """Run schema init, legacy migration, and data-layer self-check on boot."""
    NOTES.mkdir(exist_ok=True)
    init_users_db()
    migrate_file_notes()
    checks = verify_data_layer()
    missing = [k for k, ok in checks.items() if not ok and k != "kjv_fallback_db"]
    if missing:
        print(f"[startup] WARNING — missing data files: {missing}", flush=True)
    else:
        print("[startup] All data checks passed.", flush=True)

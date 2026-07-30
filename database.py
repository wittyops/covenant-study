"""
Covenant Study — database connection helpers and reference parser.

All functions return either an open sqlite3.Connection (caller must close it)
or None when the database file does not exist. They never cache connections
because uvicorn runs multiple async workers that must not share SQLite handles.

Startup self-check: database.verify_data_layer() is called from app startup
to log the status of every expected database file.
"""
import re
import sqlite3
from typing import Optional

from config import DATA, USERDATA, BOOK_ABBR


# ---------------------------------------------------------------------------
# BIBLE DATA CONNECTIONS
# ---------------------------------------------------------------------------

def get_db() -> tuple[Optional[sqlite3.Connection], bool]:
    """Return (connection, is_multi_translation) for the verse database.

    Prefers bible_multi.db (all translations) over kjv.db (KJV only).
    Returns (None, False) when neither file is present.
    """
    multi = DATA / "bible_multi.db"
    single = DATA / "kjv.db"
    if multi.exists():
        return sqlite3.connect(str(multi)), True
    if single.exists():
        return sqlite3.connect(str(single)), False
    return None, False


def get_strongs_db() -> Optional[sqlite3.Connection]:
    """Return a connection to strongs.db, or None."""
    db_path = DATA / "strongs.db"
    if not db_path.exists():
        return None
    return sqlite3.connect(str(db_path))


def get_crossrefs_db() -> Optional[sqlite3.Connection]:
    """Return a connection to cross_references.db with Row factory, or None."""
    db_path = DATA / "cross_references.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_interlinear_db() -> Optional[sqlite3.Connection]:
    """Return a connection to interlinear.db with Row factory, or None."""
    db_path = DATA / "interlinear.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_commentary_db() -> Optional[sqlite3.Connection]:
    """Return a connection to commentary.db with Row factory, or None."""
    db_path = DATA / "commentary.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# USER DATA CONNECTION
# ---------------------------------------------------------------------------

def get_users_db() -> sqlite3.Connection:
    """Return a WAL-mode FK-enabled connection to /app/userdata/users.db.

    Creates the userdata directory if absent (only needed on first boot
    before the volume is initialised).
    """
    USERDATA.mkdir(parents=True, exist_ok=True)
    db_path = USERDATA / "users.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# STRONG'S NUMBER NORMALISATION
# ---------------------------------------------------------------------------

def normalize_strongs(number: str) -> list[str]:
    """Return candidate lookup keys for a Strong's number.

    strongs.db stores Hebrew as 'H1'/'H2' and Greek as '00001'/'00025'
    (5-digit zero-padded, no prefix). The interlinear uses 'G25', 'H1',
    'G3588_A', 'H1004B', etc. This function returns all likely forms so
    callers can try them in order.
    """
    n = number.upper().split("_")[0]   # strip disambiguation suffix (e.g. G3588_A → G3588)
    candidates = [n]

    # Strip trailing alphabetic annotation added by STEPBible (H7225G → H7225)
    base = re.sub(r"[A-Z]+$", "", n)
    if base and base != n:
        candidates.append(base)

    # Convert Greek G-prefix to zero-padded 5-digit format used in strongs.db
    for candidate in (n, base):
        if candidate.startswith("G"):
            try:
                digits = int(re.sub(r"[A-Z]+$", "", candidate[1:]))
                zero_padded = f"{digits:05d}"
                if zero_padded not in candidates:
                    candidates.append(zero_padded)
            except ValueError:
                pass

    return candidates


# ---------------------------------------------------------------------------
# REFERENCE PARSER
# ---------------------------------------------------------------------------

def parse_reference(ref: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Parse a human-readable Scripture reference into (book_num, chapter, verse).

    Accepts:
      'John 3'       → (43, 3, None)
      'John 3:16'    → (43, 3, 16)
      'Gen 1:1'      → (1, 1, 1)
      '1 John 3:16'  → (62, 3, 16)

    Returns (None, None, None) on failure.
    """
    ref = ref.strip()
    m = re.match(r'^((?:\d\s+)?[a-zA-Z\s]+?)\s+(\d+)(?::(\d+))?$', ref)
    if not m:
        return None, None, None

    book_str = m.group(1).strip().lower().rstrip()
    chapter  = int(m.group(2))
    verse    = int(m.group(3)) if m.group(3) else None

    # Exact match first, then prefix fuzzy fallback
    book_num = BOOK_ABBR.get(book_str) or BOOK_ABBR.get(re.sub(r'\s+', '', book_str))
    if not book_num:
        for abbr, num in BOOK_ABBR.items():
            if book_str.startswith(abbr) or abbr.startswith(book_str[:4]):
                book_num = num
                break

    return book_num, chapter, verse


# ---------------------------------------------------------------------------
# STARTUP SELF-CHECK
# ---------------------------------------------------------------------------

def verify_data_layer() -> dict[str, bool]:
    """Check that every expected database file exists and return a status dict.

    Called from app.py startup_event() so problems appear in the container
    log immediately on boot rather than as 503s at query time.
    """
    checks = {
        "bible_multi_db":    (DATA / "bible_multi.db").exists(),
        "kjv_fallback_db":   (DATA / "kjv.db").exists(),
        "strongs_db":        (DATA / "strongs.db").exists(),
        "cross_references":  (DATA / "cross_references.db").exists(),
        "interlinear_db":    (DATA / "interlinear.db").exists(),
        "commentary_db":     (DATA / "commentary.db").exists(),
        "userdata_dir":      USERDATA.exists(),
    }
    for name, ok in checks.items():
        status = "OK" if ok else "MISSING"
        print(f"[startup] {name}: {status}", flush=True)
    return checks

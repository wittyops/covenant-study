"""
Bible data endpoints — verse retrieval, search, Strong's, interlinear,
cross-references, commentary, places, and the /api/health self-check.
"""
import re
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from config import BOOKS, APOCRYPHA_BOOKS, PLACES, DATA
from database import (
    get_crossrefs_db,
    get_db,
    get_interlinear_db,
    get_commentary_db,
    get_strongs_db,
    normalize_strongs,
    parse_reference,
)

router = APIRouter(tags=["bible"])


# ---------------------------------------------------------------------------
# VERSE RETRIEVAL
# ---------------------------------------------------------------------------

@router.get("/api/verse")
async def get_verse(ref: str = Query(...), translation: str = Query("KJV")):
    """Return verse(s) for a chapter or specific verse reference.

    Chapter ref ('John 3')  → all verses in that chapter.
    Verse ref ('John 3:16') → single verse.
    """
    conn, multi = get_db()
    if not conn:
        raise HTTPException(503, "Bible database not loaded")
    try:
        book_num, chapter, verse = parse_reference(ref)
        if not book_num:
            raise HTTPException(400, f"Could not parse reference: {ref}")
        cur = conn.cursor()
        tr = translation
        if multi:
            if verse:
                cur.execute(
                    "SELECT b, c, v, t FROM verses WHERE translation=? AND b=? AND c=? AND v=?",
                    (tr, book_num, chapter, verse),
                )
            else:
                cur.execute(
                    "SELECT b, c, v, t FROM verses WHERE translation=? AND b=? AND c=? ORDER BY v",
                    (tr, book_num, chapter),
                )
        else:
            if verse:
                cur.execute("SELECT b, c, v, t FROM t_kjv WHERE b=? AND c=? AND v=?", (book_num, chapter, verse))
            else:
                cur.execute("SELECT b, c, v, t FROM t_kjv WHERE b=? AND c=? ORDER BY v", (book_num, chapter))
            tr = "KJV"
        rows = cur.fetchall()
        verses = [{"book": BOOKS.get(r[0], r[0]), "chapter": r[1], "verse": r[2], "text": r[3]} for r in rows]
        return {"reference": ref, "translation": tr, "verses": verses}
    finally:
        conn.close()


@router.get("/api/compare")
async def compare_verse(
    ref: str = Query(...),
    translations: str = Query("KJV,ASV,YLT,Darby"),
):
    """Return the same verse in up to 12 translations side-by-side.

    Requires a specific verse reference (e.g. 'John 3:16').
    """
    conn, multi = get_db()
    if not conn:
        raise HTTPException(503, "Bible database not loaded")
    try:
        book_num, chapter, verse = parse_reference(ref)
        if not book_num or not verse:
            raise HTTPException(400, "Comparison requires a specific verse (e.g. John 3:16)")
        trans_list = [t.strip() for t in translations.split(",")][:12]
        cur = conn.cursor()
        results = {}
        for tr in trans_list:
            if multi:
                row = cur.execute(
                    "SELECT t FROM verses WHERE translation=? AND b=? AND c=? AND v=?",
                    (tr, book_num, chapter, verse),
                ).fetchone()
            else:
                row = cur.execute(
                    "SELECT t FROM t_kjv WHERE b=? AND c=? AND v=?",
                    (book_num, chapter, verse),
                ).fetchone()
                tr = "KJV"
            if row:
                results[tr] = row[0]
        return {"reference": ref, "comparisons": results}
    finally:
        conn.close()


@router.get("/api/translations")
async def list_translations():
    """Return every translation available in the live database."""
    conn, multi = get_db()
    if not conn:
        return {"translations": ["KJV"]}
    try:
        if multi:
            rows = conn.execute("SELECT DISTINCT translation FROM verses ORDER BY translation").fetchall()
            return {"translations": [r[0] for r in rows]}
        return {"translations": ["KJV"]}
    finally:
        conn.close()


@router.get("/api/search")
async def search(
    q: str = Query(..., min_length=3),
    translation: str = Query("KJV"),
    limit: int = 20,
):
    """Full-text LIKE search across verse text. Returns up to `limit` results."""
    conn, multi = get_db()
    if not conn:
        raise HTTPException(503, "Bible database not loaded")
    try:
        cur = conn.cursor()
        tr = translation
        if multi:
            cur.execute(
                "SELECT b, c, v, t FROM verses WHERE translation=? AND t LIKE ? LIMIT ?",
                (tr, f"%{q}%", limit),
            )
        else:
            cur.execute("SELECT b, c, v, t FROM t_kjv WHERE t LIKE ? LIMIT ?", (f"%{q}%", limit))
            tr = "KJV"
        rows = cur.fetchall()
        results = [{"ref": f"{BOOKS.get(r[0])} {r[1]}:{r[2]}", "text": r[3]} for r in rows]
        return {"query": q, "translation": tr, "count": len(results), "results": results}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# STRONG'S LEXICON
# ---------------------------------------------------------------------------

@router.get("/api/strongs/{number}")
async def strongs_lookup(number: str):
    """Return the lexicon entry for a Strong's number (Hebrew or Greek).

    Tries multiple key formats (H123, G00123, etc.) via normalize_strongs().
    """
    db = get_strongs_db()
    if not db:
        raise HTTPException(503, "Strong's database not loaded")
    try:
        row = None
        for key in normalize_strongs(number):
            row = db.execute(
                "SELECT number, language, original, transliteration, pronunciation,"
                " definition, kjv_usage FROM strongs WHERE number=?",
                (key,),
            ).fetchone()
            if row:
                break
        if not row:
            raise HTTPException(404, f"Strong's {number} not found")
        return {
            "number": row[0], "language": row[1], "original": row[2],
            "transliteration": row[3], "pronunciation": row[4],
            "definition": row[5], "kjv_usage": row[6],
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GEOGRAPHIC PLACES
# ---------------------------------------------------------------------------

@router.get("/api/places")
async def get_places(ref: Optional[str] = Query(default=None)):
    """Return biblical place coordinates.

    Without ref: all known places.
    With ref: only places whose names appear in that passage's KJV text.
    """
    if ref is None:
        return {
            "places": [
                {"name": name, "lat": d["lat"], "lng": d["lon"], "notes": d.get("notes", "")}
                for name, d in PLACES.items()
            ]
        }
    conn, multi = get_db()
    if not conn:
        return {"reference": ref, "places": []}
    try:
        book_num, chapter, verse = parse_reference(ref)
        if not book_num:
            return {"reference": ref, "places": []}
        cur = conn.cursor()
        if multi:
            rows = (
                cur.execute(
                    "SELECT t FROM verses WHERE translation='KJV' AND b=? AND c=? AND v=?",
                    (book_num, chapter, verse),
                ).fetchall()
                if verse
                else cur.execute(
                    "SELECT t FROM verses WHERE translation='KJV' AND b=? AND c=? ORDER BY v",
                    (book_num, chapter),
                ).fetchall()
            )
        else:
            rows = (
                cur.execute("SELECT t FROM t_kjv WHERE b=? AND c=? AND v=?", (book_num, chapter, verse)).fetchall()
                if verse
                else cur.execute("SELECT t FROM t_kjv WHERE b=? AND c=? ORDER BY v", (book_num, chapter)).fetchall()
            )
        passage_text = " ".join(r[0] for r in rows)
        found = [
            {"name": name, "lat": d["lat"], "lng": d["lon"], "notes": d.get("notes", "")}
            for name, d in PLACES.items()
            if re.search(r"\b" + re.escape(name) + r"\b", passage_text, re.IGNORECASE)
        ]
        return {"reference": ref, "passage_length": len(rows), "places": found}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# REFERENCE DATA
# ---------------------------------------------------------------------------

@router.get("/api/books")
async def list_books():
    """Return the canonical list of 66 books with their numeric IDs."""
    return {"books": [{"num": k, "name": v} for k, v in BOOKS.items()]}


@router.get("/api/health")
async def health():
    """Self-check endpoint — reports database availability at a glance.

    Returns HTTP 200 regardless of database state so the load-balancer
    (Caddy upstream health check) can distinguish a crashed container from
    a running one with missing data files.
    """
    from config import USERDATA, NOTES
    multi = (DATA / "bible_multi.db").exists()
    lxx_brenton = False
    if multi:
        try:
            from database import get_db
            conn, _ = get_db()
            if conn:
                lxx_brenton = bool(conn.execute(
                    "SELECT 1 FROM verses WHERE translation='Brenton' LIMIT 1"
                ).fetchone())
                conn.close()
        except Exception:
            pass
    return {
        "db":              multi or (DATA / "kjv.db").exists(),
        "multi_translation": multi,
        "lxx_brenton":     lxx_brenton,
        "strongs":         (DATA / "strongs.db").exists(),
        "crossrefs":       (DATA / "cross_references.db").exists(),
        "interlinear":     (DATA / "interlinear.db").exists(),
        "commentary":      (DATA / "commentary.db").exists(),
        "users_db":        (USERDATA / "users.db").exists(),
        "notes_dir":       str(NOTES),
        "places_count":    len(PLACES),
    }


# ---------------------------------------------------------------------------
# WORD-LEVEL STRONG'S (TAGGED VERSE)
# ---------------------------------------------------------------------------

@router.get("/api/verse/tagged")
async def get_tagged_verse(ref: str = Query(...)):
    """Return verse(s) with per-word Strong's numbers and glosses.

    Prefers word_strongs table in kjv.db when available (faster, richer
    morphology). Falls back to interlinear.db which is always populated.
    """
    book_num, chapter, verse = parse_reference(ref)
    if not book_num:
        raise HTTPException(400, f"Could not parse reference: {ref}")

    strongs_path = DATA / "strongs.db"
    kjv_path = DATA / "kjv.db"

    # --- Try word_strongs table in kjv.db first ---
    has_data = False
    if kjv_path.exists():
        conn = sqlite3.connect(str(kjv_path))
        conn.row_factory = sqlite3.Row
        try:
            has_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='word_strongs'"
            ).fetchone()
            has_data = bool(has_table and conn.execute("SELECT 1 FROM word_strongs LIMIT 1").fetchone())
        finally:
            conn.close()

    if has_data:
        conn = sqlite3.connect(str(kjv_path))
        conn.row_factory = sqlite3.Row
        try:
            if strongs_path.exists():
                conn.execute("ATTACH DATABASE ? AS sdb", (str(strongs_path),))
                strongs_join = "LEFT JOIN (SELECT number, original, definition FROM sdb.strongs) s ON s.number = ws.strong_number"
                strongs_sel  = "s.original, s.definition"
            else:
                strongs_join = ""
                strongs_sel  = "NULL as original, NULL as definition"

            def fetch_word_strongs(v_num: int) -> list:
                rows = conn.execute(
                    f"SELECT ws.word_position, ws.phrase_text, ws.strong_number,"
                    f"       ws.extra_strongs, ws.morph, {strongs_sel}"
                    f" FROM word_strongs ws {strongs_join}"
                    f" WHERE ws.book_id = ? AND ws.chapter = ? AND ws.verse = ?"
                    f" ORDER BY ws.word_position",
                    (book_num, chapter, v_num),
                ).fetchall()
                return [
                    {
                        "pos": r["word_position"], "text": r["phrase_text"],
                        "strongs": r["strong_number"], "extra_strongs": r["extra_strongs"],
                        "morph": r["morph"], "original": r["original"], "definition": r["definition"],
                    }
                    for r in rows
                ]

            if verse is None:
                verse_nums = [
                    r[0] for r in conn.execute(
                        "SELECT DISTINCT verse FROM word_strongs WHERE book_id=? AND chapter=? ORDER BY verse",
                        (book_num, chapter),
                    ).fetchall()
                ]
                verses = [{"num": v, "words": fetch_word_strongs(v)} for v in verse_nums if fetch_word_strongs(v)]
                return {"reference": ref, "verses": verses, "source": "word_strongs"}
            else:
                words = fetch_word_strongs(verse)
                if not words:
                    raise HTTPException(404, f"No tagged data found for {ref}")
                return {"reference": ref, "verses": [{"num": verse, "words": words}], "source": "word_strongs"}
        finally:
            conn.close()

    # --- Fallback: interlinear.db ---
    interlinear_path = DATA / "interlinear.db"
    if not interlinear_path.exists():
        raise HTTPException(503, "No word-level Strong's data available")

    conn = sqlite3.connect(str(interlinear_path))
    conn.row_factory = sqlite3.Row
    try:
        if strongs_path.exists():
            conn.execute("ATTACH DATABASE ? AS sdb", (str(strongs_path),))
            strongs_join = "LEFT JOIN (SELECT number, original, definition FROM sdb.strongs) s ON s.number = i.strongs_num"
            strongs_sel  = "s.original AS str_orig, s.definition"
        else:
            strongs_join = ""
            strongs_sel  = "NULL as str_orig, NULL as definition"

        def fetch_interlinear(v_num: int) -> list:
            rows = conn.execute(
                f"SELECT i.word_num, i.english_gloss, i.strongs_num,"
                f"       i.original_word, i.transliteration, i.morphology, {strongs_sel}"
                f" FROM interlinear i {strongs_join}"
                f" WHERE i.book = ? AND i.chapter = ? AND i.verse = ? ORDER BY i.word_num",
                (book_num, chapter, v_num),
            ).fetchall()
            return [
                {
                    "pos": r["word_num"],
                    "text": r["english_gloss"] or r["original_word"] or "",
                    "strongs": r["strongs_num"], "extra_strongs": None,
                    "morph": r["morphology"], "original": r["original_word"],
                    "definition": r["definition"],
                }
                for r in rows
            ]

        if verse is None:
            verse_nums = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT verse FROM interlinear WHERE book=? AND chapter=? ORDER BY verse",
                    (book_num, chapter),
                ).fetchall()
            ]
            verses = [{"num": v, "words": fetch_interlinear(v)} for v in verse_nums if fetch_interlinear(v)]
            if not verses:
                raise HTTPException(404, f"No word data found for {ref}")
            return {"reference": ref, "verses": verses, "source": "interlinear"}
        else:
            words = fetch_interlinear(verse)
            if not words:
                raise HTTPException(404, f"No word data found for {ref}")
            return {"reference": ref, "verses": [{"num": verse, "words": words}], "source": "interlinear"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CROSS-REFERENCES
# ---------------------------------------------------------------------------

@router.get("/api/crossrefs")
async def get_crossrefs(
    ref: str = Query(...),
    min_votes: int = Query(0),
    limit: int = Query(25, ge=1, le=200),
):
    """Return cross-references for a verse, sorted by vote count descending."""
    ref = ref.strip()
    m = re.match(r"^(.*?)\s+(\d+):(\d+)$", ref)
    if not m:
        raise HTTPException(400, f"Could not parse reference: {ref}")
    book_name = m.group(1).strip()
    chapter   = int(m.group(2))
    verse     = int(m.group(3))

    db = get_crossrefs_db()
    if not db:
        raise HTTPException(503, "Cross-references database not loaded")
    try:
        rows = db.execute(
            "SELECT to_book, to_chapter, to_verse_start, to_verse_end, votes"
            " FROM cross_refs"
            " WHERE from_book = ? AND from_chapter = ? AND from_verse = ?"
            "   AND votes >= ?"
            " ORDER BY votes DESC LIMIT ?",
            (book_name, chapter, verse, min_votes, limit),
        ).fetchall()
        cross_refs = [
            {
                "book": r["to_book"], "chapter": r["to_chapter"],
                "verse_start": r["to_verse_start"], "verse_end": r["to_verse_end"],
                "votes": r["votes"],
            }
            for r in rows
        ]
        return {"ref": ref, "cross_references": cross_refs}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# INTERLINEAR
# ---------------------------------------------------------------------------

@router.get("/api/interlinear")
async def get_interlinear(ref: str = Query(...)):
    """Return word-level Hebrew/Greek interlinear data for a single verse.

    Each word includes the original text, transliteration, Strong's number,
    morphology code, English gloss, and full lexicon definition when available.
    """
    book_num, chapter, verse = parse_reference(ref)
    if not book_num or not verse:
        raise HTTPException(400, f"Interlinear requires a specific verse reference: {ref}")

    db = get_interlinear_db()
    if not db:
        raise HTTPException(503, "Interlinear database not loaded")
    try:
        rows = db.execute(
            "SELECT word_num, testament, original_word, transliteration,"
            "       strongs_num, morphology, english_gloss"
            " FROM interlinear WHERE book = ? AND chapter = ? AND verse = ?"
            " ORDER BY word_num",
            (book_num, chapter, verse),
        ).fetchall()
        if not rows:
            raise HTTPException(404, f"No interlinear data found for {ref}")

        testament  = rows[0]["testament"]
        strongs_db = None
        strongs_path = DATA / "strongs.db"
        if strongs_path.exists():
            strongs_db = sqlite3.connect(str(strongs_path))
            strongs_db.row_factory = sqlite3.Row

        words = []
        for r in rows:
            entry = {
                "num": r["word_num"], "original": r["original_word"],
                "translit": r["transliteration"], "strongs": r["strongs_num"],
                "morph": r["morphology"], "gloss": r["english_gloss"], "definition": None,
            }
            if strongs_db and r["strongs_num"]:
                s_row = strongs_db.execute(
                    "SELECT definition FROM strongs WHERE number = ?", (r["strongs_num"],)
                ).fetchone()
                if s_row:
                    entry["definition"] = s_row["definition"]
            words.append(entry)

        if strongs_db:
            strongs_db.close()

        return {"ref": ref, "testament": testament, "words": words}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# COMMENTARY
# ---------------------------------------------------------------------------

@router.get("/api/commentary")
async def get_commentary(ref: str = Query(...)):
    """Return Matthew Henry commentary section(s) covering the requested verse.

    Matches sections where verse_start ≤ requested verse ≤ verse_end,
    plus any sections with NULL boundaries (chapter-level commentary).
    """
    book_num, chapter, verse = parse_reference(ref)
    if not book_num or not verse:
        raise HTTPException(400, f"Commentary requires a specific verse reference: {ref}")

    db = get_commentary_db()
    if not db:
        raise HTTPException(503, "Commentary database not loaded")
    try:
        rows = db.execute(
            "SELECT verse_start, verse_end, author, text FROM commentary"
            " WHERE book = ? AND chapter = ?"
            "   AND (verse_start IS NULL OR verse_start <= ?)"
            "   AND (verse_end   IS NULL OR verse_end   >= ?)"
            " ORDER BY verse_start NULLS FIRST",
            (book_num, chapter, verse, verse),
        ).fetchall()
        return {
            "ref": ref,
            "commentary": [
                {
                    "verse_start": r["verse_start"], "verse_end": r["verse_end"],
                    "author": r["author"], "text": r["text"],
                }
                for r in rows
            ],
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# REACT SPA COMPAT — /api/bible/* routes
#
# The React frontend uses /api/bible/chapter, /api/bible/books, etc. with
# numeric params and typed response shapes.  These endpoints wrap the same
# SQLite logic as the legacy /api/* routes but speak the frontend's dialect.
# ---------------------------------------------------------------------------

# Reverse-lookup: book name → number (used to parse crossref results from DB)
_BOOK_NUMS: dict[str, int] = {v: k for k, v in BOOKS.items()}

# Testament assignment (OT=1-39, NT=40-66, AP=67-80 deuterocanon/apocrypha)
# and canonical chapter counts.
_TESTAMENT: dict[int, str] = {
    **{i: "OT" for i in range(1, 40)},
    **{i: "NT" for i in range(40, 67)},
    **{i: "AP" for i in APOCRYPHA_BOOKS},
}
_CHAPTERS: dict[int, int] = {
    1: 50, 2: 40, 3: 27, 4: 36, 5: 34, 6: 24, 7: 21, 8: 4, 9: 31, 10: 24,
    11: 22, 12: 25, 13: 29, 14: 36, 15: 10, 16: 13, 17: 10, 18: 42, 19: 150,
    20: 31, 21: 12, 22: 8,  23: 66, 24: 52, 25: 5,  26: 48, 27: 12, 28: 14,
    29: 3,  30: 9,  31: 1,  32: 4,  33: 7,  34: 3,  35: 3,  36: 3,  37: 2,
    38: 14, 39: 4,  40: 28, 41: 16, 42: 24, 43: 21, 44: 28, 45: 16, 46: 16,
    47: 13, 48: 6,  49: 6,  50: 4,  51: 4,  52: 5,  53: 3,  54: 6,  55: 4,
    56: 3,  57: 1,  58: 13, 59: 5,  60: 5,  61: 3,  62: 5,  63: 1,  64: 1,
    65: 1,  66: 22,
    # Apocrypha — chapter counts confirmed live from bible_multi.db KJVA data
    # (queried under the pre-remap source IDs 40-53, which map 1:1 to 67-80).
    67: 9,  68: 16, 69: 14, 70: 16, 71: 16, 72: 19, 73: 51, 74: 6,
    75: 1,  76: 1,  77: 1,  78: 1,  79: 16, 80: 15,
}


@router.get("/api/bible/books")
async def react_books():
    """Book list for the React SPA — returns BookInfo[] directly (no wrapper object)."""
    return [
        {
            "book":      k,
            "name":      v,
            "testament": _TESTAMENT.get(k, "OT"),
            "chapters":  _CHAPTERS.get(k, 1),
        }
        for k, v in BOOKS.items()
    ]


@router.get("/api/bible/translations")
async def react_translations():
    """Translation list for the React SPA — returns Translation[] (id + name) directly."""
    conn, multi = get_db()
    if not conn:
        return [{"id": "KJV", "name": "King James Version"}]
    try:
        if multi:
            rows = conn.execute(
                "SELECT DISTINCT translation FROM verses ORDER BY translation"
            ).fetchall()
            return [{"id": r[0], "name": r[0]} for r in rows]
        return [{"id": "KJV", "name": "King James Version"}]
    finally:
        conn.close()


@router.get("/api/bible/chapter")
async def react_chapter(
    book:        int = Query(..., ge=1, le=80),
    chapter:     int = Query(..., ge=1),
    translation: str = Query("KJV"),
):
    """Chapter text for the React SPA — takes numeric book/chapter params.

    Returns ChapterResponse shape: {book, book_name, chapter, translation, verses[]}.
    """
    conn, multi = get_db()
    if not conn:
        raise HTTPException(503, "Bible database not loaded")
    try:
        book_name = BOOKS.get(book, str(book))
        cur = conn.cursor()
        if multi:
            cur.execute(
                "SELECT v, t FROM verses WHERE translation=? AND b=? AND c=? ORDER BY v",
                (translation, book, chapter),
            )
        else:
            cur.execute(
                "SELECT v, t FROM t_kjv WHERE b=? AND c=? ORDER BY v",
                (book, chapter),
            )
            translation = "KJV"
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(404, f"No verses found for book {book} chapter {chapter}")
        verses = [
            {
                "book":        book,
                "book_name":   book_name,
                "chapter":     chapter,
                "verse":       r[0],
                "text":        r[1],
                "translation": translation,
            }
            for r in rows
        ]
        return {
            "book":        book,
            "book_name":   book_name,
            "chapter":     chapter,
            "translation": translation,
            "verses":      verses,
        }
    finally:
        conn.close()


@router.get("/api/bible/search")
async def react_search(
    q:           str = Query(..., min_length=3),
    translation: str = Query("KJV"),
    limit:       int = Query(20, ge=1, le=100),
):
    """Search for the React SPA — returns Verse[] directly."""
    conn, multi = get_db()
    if not conn:
        raise HTTPException(503, "Bible database not loaded")
    try:
        cur = conn.cursor()
        if multi:
            cur.execute(
                "SELECT b, c, v, t FROM verses WHERE translation=? AND t LIKE ? LIMIT ?",
                (translation, f"%{q}%", limit),
            )
        else:
            cur.execute("SELECT b, c, v, t FROM t_kjv WHERE t LIKE ? LIMIT ?", (f"%{q}%", limit))
            translation = "KJV"
        rows = cur.fetchall()
        return [
            {
                "book":        r[0],
                "book_name":   BOOKS.get(r[0], str(r[0])),
                "chapter":     r[1],
                "verse":       r[2],
                "text":        r[3],
                "translation": translation,
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/api/bible/strongs/{number}")
async def react_strongs(number: str):
    """Strong's entry for the React SPA — field names mapped to StrongsEntry type."""
    db = get_strongs_db()
    if not db:
        raise HTTPException(503, "Strong's database not loaded")
    try:
        row = None
        for key in normalize_strongs(number):
            row = db.execute(
                "SELECT number, language, original, transliteration, pronunciation,"
                " definition, kjv_usage FROM strongs WHERE number=?",
                (key,),
            ).fetchone()
            if row:
                break
        if not row:
            raise HTTPException(404, f"Strong's {number} not found")
        return {
            "number":          row[0],
            "word":            row[2],   # original → word
            "transliteration": row[3],
            "pronunciation":   row[4],
            "definition":      row[5],
            "derivation":      row[6] or "",  # kjv_usage → derivation
            "language":        row[1],
        }
    finally:
        db.close()


@router.get("/api/bible/crossrefs")
async def react_crossrefs(
    book:    int = Query(..., ge=1, le=80),
    chapter: int = Query(..., ge=1),
    verse:   int = Query(..., ge=1),
    limit:   int = Query(25, ge=1, le=200),
):
    """Cross-references for the React SPA — numeric params, CrossRef[] response."""
    book_name = BOOKS.get(book, str(book))
    db = get_crossrefs_db()
    if not db:
        raise HTTPException(503, "Cross-references database not loaded")
    try:
        rows = db.execute(
            "SELECT to_book, to_chapter, to_verse_start, votes"
            " FROM cross_refs"
            " WHERE from_book = ? AND from_chapter = ? AND from_verse = ?"
            " ORDER BY votes DESC LIMIT ?",
            (book_name, chapter, verse, limit),
        ).fetchall()
        return [
            {
                "from_book":    book,
                "from_chapter": chapter,
                "from_verse":   verse,
                "to_book":      _BOOK_NUMS.get(r["to_book"], 0),
                "to_chapter":   r["to_chapter"],
                "to_verse":     r["to_verse_start"],
                "to_book_name": r["to_book"],
            }
            for r in rows
        ]
    finally:
        db.close()


@router.get("/api/bible/interlinear")
async def react_interlinear(
    book:    int = Query(..., ge=1, le=80),
    chapter: int = Query(..., ge=1),
):
    """Interlinear for the React SPA — takes numeric book/chapter, returns InterlinearWord[]."""
    db = get_interlinear_db()
    if not db:
        raise HTTPException(503, "Interlinear database not loaded")
    try:
        rows = db.execute(
            "SELECT word_num, original_word, transliteration, strongs_num,"
            "       morphology, english_gloss"
            " FROM interlinear WHERE book = ? AND chapter = ?"
            " ORDER BY verse, word_num",
            (book, chapter),
        ).fetchall()
        return [
            {
                "position": r["word_num"],
                "original": r["original_word"],
                "translit": r["transliteration"],
                "strongs":  r["strongs_num"],
                "morph":    r["morphology"],
                "english":  r["english_gloss"],
            }
            for r in rows
        ]
    finally:
        db.close()

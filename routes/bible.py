"""
Bible data endpoints — verse retrieval, search, Strong's, interlinear,
cross-references, commentary, places, and the /api/health self-check.
"""
import re
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from config import BOOKS, PLACES, DATA
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
    return {
        "db":              multi or (DATA / "kjv.db").exists(),
        "multi_translation": multi,
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

"""
fragments.py — HTML fragment endpoints for htmx (server-rendered partials).

PURPOSE
-------
Each endpoint here returns a snippet of HTML (Content-Type: text/html), NOT
JSON.  htmx swaps these fragments directly into the matching DOM target on the
page without any client-side parsing or template rendering.

This pattern keeps rendering logic on the server where it is easy to test,
version, and read — and it dramatically reduces the amount of JavaScript the
browser has to execute.  The 2,670-line covenant.js that previously built DOM
nodes by hand is replaced by these Python functions that return clean HTML.

ROUTE MAP
---------
  GET /fragments/books               → sidebar book/testament navigation tree
  GET /fragments/chapter             → all verses in a chapter (with optional tagging)
  GET /fragments/strongs/{number}    → Strong's lexicon card for one entry
  GET /fragments/crossrefs           → cross-reference list for a verse
  GET /fragments/interlinear         → word-by-word interlinear table for a verse
  GET /fragments/commentary          → commentary excerpts for a verse
  GET /fragments/search              → full-text search result list

HOW IT FITS TOGETHER
--------------------
index.html declares htmx attributes on container elements:

  <div id="chapter-display"
       hx-get="/fragments/chapter"
       hx-include="[name='book'],[name='chapter'],[name='translation']"
       hx-trigger="chapter-change from:body"
       hx-swap="innerHTML">

When Alpine.js changes the reader store (new book, next chapter), it fires the
"chapter-change" event.  htmx sees the trigger, reads the hidden input values
Alpine keeps updated, makes the GET request, and swaps the response into
#chapter-display.  No custom fetch() code needed on the client.

SECURITY NOTE
-------------
All user-supplied strings pass through _esc() before appearing in markup.
No fragment endpoint writes to the database — they are read-only.
"""
import html
import re
import sqlite3

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from config import BOOK_ABBR, BOOKS, DATA
from database import (
    get_crossrefs_db,
    get_db,
    get_interlinear_db,
    get_commentary_db,
    get_strongs_db,
    normalize_strongs,
    parse_reference,
)

router = APIRouter(prefix="/fragments", tags=["fragments"])

# Genesis–Malachi (39 books) and Matthew–Revelation (27 books).
# These ranges drive the sidebar accordion structure.
OT_BOOK_NUMS = list(range(1, 40))
NT_BOOK_NUMS = list(range(40, 67))


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================

def _esc(value) -> str:
    """HTML-escape any value for safe embedding in markup.

    Called on every piece of user-originated or database-originated content
    that appears in an HTML attribute or text node.  Never skip this.
    """
    return html.escape(str(value), quote=True)


def _html(markup: str) -> HTMLResponse:
    """Wrap a markup string in an HTMLResponse with the correct content-type."""
    return HTMLResponse(content=markup, media_type="text/html; charset=utf-8")


# ===========================================================================
# BOOKS — sidebar book navigation tree
# ===========================================================================

@router.get("/books", response_class=HTMLResponse)
async def fragment_books():
    """Render the sidebar book tree (OT + NT accordions).

    Each book name becomes a button that does two things when clicked:
      1. Tells htmx to load chapter 1 of that book into #chapter-display.
      2. Updates the Alpine.js reader store via @click so the header
         reference display stays in sync.

    The server renders this once on page load; there is no JS-side
    buildBookNav() function needed.  The HTML is cached by the browser
    (static for any given deployment).
    """
    def book_button(book_name: str) -> str:
        # Three-letter abbreviation for the compact grid view.
        abbr = BOOK_ABBR.get(book_name, book_name[:3])
        safe_name = _esc(book_name)
        return (
            f'<button class="book-btn"'
            f' data-book="{safe_name}"'
            # htmx: load chapter 1 of this book into the main display area.
            f' hx-get="/fragments/chapter"'
            f' hx-vals=\'{{"book":"{safe_name}","chapter":"1","tagged":"true"}}\''
            f' hx-target="#chapter-display"'
            f' hx-swap="innerHTML"'
            # Alpine: sync the reader store and close the sidebar on mobile.
            f' @click="$store.reader.setBook(\'{safe_name}\'); $store.ui.closeSidebar()"'
            f' title="{safe_name}">'
            f'<abbr class="book-abbr">{_esc(abbr)}</abbr>'
            f'<span class="book-name">{safe_name}</span>'
            f'</button>'
        )

    ot_buttons = "\n".join(
        book_button(BOOKS[n]) for n in OT_BOOK_NUMS if n in BOOKS
    )
    nt_buttons = "\n".join(
        book_button(BOOKS[n]) for n in NT_BOOK_NUMS if n in BOOKS
    )

    return _html(f"""
<nav class="book-tree" role="navigation" aria-label="Bible books">

  <details open>
    <summary class="testament-header">Old Testament</summary>
    <div class="book-grid">{ot_buttons}</div>
  </details>

  <details open>
    <summary class="testament-header">New Testament</summary>
    <div class="book-grid">{nt_buttons}</div>
  </details>

</nav>
""")


# ===========================================================================
# CHAPTER — verse display
# ===========================================================================

@router.get("/chapter", response_class=HTMLResponse)
async def fragment_chapter(
    book:        str  = Query("Genesis"),
    chapter:     int  = Query(1),
    translation: str  = Query("KJV"),
    tagged:      bool = Query(True),
):
    """Render all verses in a chapter as HTML.

    When tagged=true (the default), each word that has a Strong's mapping
    gets a data-strongs attribute.  Alpine.js event delegation on the parent
    container picks these up without individual onclick handlers — one
    listener on the container, not N listeners on N words.

    When tagged data is unavailable (e.g. a non-KJV translation with no
    interlinear), the verses render as plain text.  The reading experience
    is preserved; only the word-click interactivity is lost for that chapter.

    Navigation arrows (prev/next chapter) are rendered server-side so
    they are always correct for the book's chapter count.
    """
    # ── Fetch verse text ────────────────────────────────────────────────
    conn, multi = get_db()
    if not conn:
        return _html('<p class="error-msg">Bible database not available.</p>')

    try:
        book_num, _, _ = parse_reference(f"{book} {chapter}")
        if not book_num:
            return _html(f'<p class="error-msg">Unknown book: {_esc(book)}</p>')

        if multi:
            rows = conn.execute(
                "SELECT v, t FROM verses"
                " WHERE translation=? AND b=? AND c=? ORDER BY v",
                (translation, book_num, chapter),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT v, t FROM t_kjv WHERE b=? AND c=? ORDER BY v",
                (book_num, chapter),
            ).fetchall()
            translation = "KJV"   # single-translation DB always returns KJV
    finally:
        conn.close()

    if not rows:
        return _html(
            f'<p class="error-msg">'
            f'{_esc(book)} {chapter} not found in {_esc(translation)}.'
            f'</p>'
        )

    # ── Fetch tagged word data (optional) ───────────────────────────────
    verse_map   = {r[0]: r[1] for r in rows}
    tagged_map  = _load_tagged_words(book_num, chapter) if tagged else {}
    total_chs   = _chapter_count(book_num)
    safe_book   = _esc(book)

    # ── Navigation buttons ───────────────────────────────────────────────
    # Each button updates BOTH the htmx content and the Alpine.js store so
    # the header reference display stays in sync.
    def nav_btn(label: str, target_ch: int, aria: str, enabled: bool) -> str:
        if not enabled:
            return (
                f'<button class="chapter-nav-btn" disabled aria-label="{aria}">'
                f'{label}</button>'
            )
        return (
            f'<button class="chapter-nav-btn"'
            f' hx-get="/fragments/chapter"'
            f' hx-vals=\'{{"book":"{safe_book}","chapter":"{target_ch}","tagged":"true"}}\''
            f' hx-target="#chapter-display" hx-swap="innerHTML"'
            f' @click="$store.reader.chapter = {target_ch}"'
            f' aria-label="{aria}">{label}</button>'
        )

    prev_btn = nav_btn("‹", chapter - 1, "Previous chapter", chapter > 1)
    next_btn = nav_btn("›", chapter + 1, "Next chapter",     chapter < total_chs)

    header = (
        f'<div class="chapter-header">'
        f'{prev_btn}'
        f'<h2 class="chapter-title">{safe_book} {chapter}'
        f' <small class="translation-badge">{_esc(translation)}</small>'
        f'</h2>'
        f'{next_btn}'
        f'</div>'
    )

    # ── Verse list ───────────────────────────────────────────────────────
    verse_parts = []
    for verse_num, plain_text in sorted(verse_map.items()):
        ref  = f"{book} {chapter}:{verse_num}"
        safe_ref = _esc(ref)
        words = tagged_map.get(verse_num, [])
        body  = _render_tagged_words(words) if words else _esc(plain_text)

        verse_parts.append(
            f'<div class="verse" id="v{verse_num}" data-ref="{safe_ref}"'
            # Right-click context menu (copy, highlight, bookmark, etc.)
            f' @contextmenu.prevent="$store.reader.showVerseMenu($event, \'{safe_ref}\')">'
            f'<span class="verse-num" aria-label="Verse {verse_num}">{verse_num}</span>'
            f'<span class="verse-text">{body}</span>'
            f'</div>'
        )

    # The outer div carries Alpine.js event delegation for word clicks:
    # one listener on the container catches every tagged-word click inside.
    return _html(
        f'<div class="chapter-display"'
        f' data-book="{safe_book}" data-chapter="{chapter}"'
        f' data-translation="{_esc(translation)}"'
        f' @click="$store.reader.handleWordClick($event)">'
        f'{header}'
        f'<div class="verse-list">{"".join(verse_parts)}</div>'
        f'</div>'
    )


# ── Chapter / tagged-word helpers ────────────────────────────────────────────

def _chapter_count(book_num: int) -> int:
    """Return the number of chapters in a book.

    Queries the live database so the answer is always accurate for whatever
    translation set is loaded.  Falls back to 1 on any error so navigation
    arrows never cause a crash.
    """
    try:
        conn, multi = get_db()
        if not conn:
            return 1
        try:
            if multi:
                row = conn.execute("SELECT MAX(c) FROM verses WHERE b=?", (book_num,)).fetchone()
            else:
                row = conn.execute("SELECT MAX(c) FROM t_kjv WHERE b=?", (book_num,)).fetchone()
            return row[0] if row and row[0] else 1
        finally:
            conn.close()
    except Exception:
        return 1


def _load_tagged_words(book_num: int, chapter: int) -> dict:
    """Load per-word Strong's mappings for every verse in a chapter.

    Returns a dict keyed by verse number; each value is a list of word dicts:
      {"text": str, "strongs": str, "morph": str}

    Tries two sources in order of preference:
      1. word_strongs table in kjv.db  — richer morphology, faster lookup
      2. interlinear.db                — always present, slightly less data

    Returns {} on any error so the caller degrades gracefully to plain text.
    """
    kjv_path         = DATA / "kjv.db"
    interlinear_path = DATA / "interlinear.db"

    # — Source 1: word_strongs in kjv.db —
    if kjv_path.exists():
        try:
            conn = sqlite3.connect(str(kjv_path))
            conn.row_factory = sqlite3.Row
            try:
                has_table = conn.execute(
                    "SELECT name FROM sqlite_master"
                    " WHERE type='table' AND name='word_strongs'"
                ).fetchone()
                has_rows = (
                    has_table
                    and conn.execute("SELECT 1 FROM word_strongs LIMIT 1").fetchone()
                )
                if has_rows:
                    rows = conn.execute(
                        "SELECT verse, phrase_text, strong_number, morph"
                        " FROM word_strongs"
                        " WHERE book_id=? AND chapter=?"
                        " ORDER BY verse, word_position",
                        (book_num, chapter),
                    ).fetchall()
                    result: dict = {}
                    for r in rows:
                        result.setdefault(r["verse"], []).append({
                            "text":    r["phrase_text"] or "",
                            "strongs": r["strong_number"] or "",
                            "morph":   r["morph"] or "",
                        })
                    return result
            finally:
                conn.close()
        except Exception:
            pass   # fall through to interlinear

    # — Source 2: interlinear.db —
    if interlinear_path.exists():
        try:
            conn = sqlite3.connect(str(interlinear_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT verse, english_gloss, original_word, strongs_num, morphology"
                    " FROM interlinear"
                    " WHERE book=? AND chapter=?"
                    " ORDER BY verse, word_num",
                    (book_num, chapter),
                ).fetchall()
                result = {}
                for r in rows:
                    result.setdefault(r["verse"], []).append({
                        "text":    r["english_gloss"] or r["original_word"] or "",
                        "strongs": r["strongs_num"] or "",
                        "morph":   r["morphology"] or "",
                    })
                return result
            finally:
                conn.close()
        except Exception:
            pass

    return {}


def _render_tagged_words(words: list) -> str:
    """Build a sequence of <span> elements for a tagged verse.

    Words with a Strong's number get:
      - class="word tagged" for CSS highlighting on hover
      - data-strongs="H7225" so Alpine.js event delegation can read it
      - data-morph="..." for the morphology tooltip
      - title="H7225" for a native browser tooltip as fallback

    Alpine.js's handleWordClick() on the container element intercepts these
    clicks and calls htmx.ajax() to load the Strong's panel — no individual
    onclick attributes on each word.
    """
    parts = []
    for w in words:
        text    = _esc(w.get("text", ""))
        strongs = w.get("strongs", "")
        morph   = _esc(w.get("morph", ""))
        if strongs:
            parts.append(
                f'<span class="word tagged"'
                f' data-strongs="{_esc(strongs)}"'
                f' data-morph="{morph}"'
                f' title="{_esc(strongs)}">'
                f'{text}</span>'
            )
        else:
            parts.append(f'<span class="word">{text}</span>')
    return " ".join(parts)


# ===========================================================================
# STRONG'S LEXICON — single entry card
# ===========================================================================

@router.get("/strongs/{number}", response_class=HTMLResponse)
async def fragment_strongs(number: str):
    """Render the Strong's lexicon entry for one number (e.g. H7225, G3056).

    Called by Alpine.js event delegation when the user clicks a tagged word
    in the chapter display.  The result is swapped into #strongs-panel.

    normalize_strongs() in database.py expands the number into a list of
    candidate lookup keys that handle prefix variations and zero-padding, so
    "7225", "H7225", and "H07225" all resolve to the same entry.
    """
    conn = get_strongs_db()
    if not conn:
        return _html('<p class="error-msg">Strong\'s database not loaded.</p>')

    candidates = normalize_strongs(number)
    row = None
    try:
        for candidate in candidates:
            row = conn.execute(
                "SELECT number, original, transliteration, pronunciation,"
                "       definition, strongs_def, kjv_def"
                " FROM strongs WHERE number=?",
                (candidate,),
            ).fetchone()
            if row:
                break
    finally:
        conn.close()

    if not row:
        return _html(
            f'<p class="error-msg">No Strong\'s entry found for {_esc(number)}.</p>'
        )

    num         = row[0]
    original    = _esc(row[1] or "")
    translit    = _esc(row[2] or "")
    pronunc     = _esc(row[3] or "")
    definition  = _esc(row[4] or "")
    strongs_def = _esc(row[5] or "")
    kjv_def     = _esc(row[6] or "")
    testament   = "Old Testament (Hebrew)" if num.startswith("H") else "New Testament (Greek)"

    # RTL direction for Hebrew original text; LTR for Greek.
    orig_dir = 'dir="rtl" lang="he"' if num.startswith("H") else 'lang="grc"'

    return _html(f"""
<div class="strongs-card">

  <div class="strongs-header">
    <span class="strongs-number">{_esc(num)}</span>
    <span class="strongs-original" {orig_dir}>{original}</span>
    <span class="strongs-translit">{translit}</span>
    {"<span class='strongs-pronunc'>(" + pronunc + ")</span>" if pronunc else ""}
  </div>

  <p class="strongs-testament">{_esc(testament)}</p>

  {"<p class='strongs-def'>" + definition + "</p>" if definition else ""}

  {"<details class='strongs-more'><summary>Strong's definition</summary><p>" + strongs_def + "</p></details>" if strongs_def else ""}

  {"<details class='strongs-more'><summary>KJV usage</summary><p>" + kjv_def + "</p></details>" if kjv_def else ""}

</div>
""")


# ===========================================================================
# CROSS-REFERENCES
# ===========================================================================

@router.get("/crossrefs", response_class=HTMLResponse)
async def fragment_crossrefs(
    ref:   str = Query(...),
    limit: int = Query(20, ge=1, le=100),
):
    """Render a navigable list of cross-references for a verse.

    Each listed reference is itself an htmx trigger so clicking it loads
    that chapter into the main display — no JavaScript needed on the client
    beyond what htmx provides declaratively.

    Results are sorted by vote count descending (most-referenced passages
    first), which surfaces the most theologically significant parallels.
    """
    m = re.match(r"^(.*?)\s+(\d+):(\d+)$", ref.strip())
    if not m:
        return _html(f'<p class="error-msg">Invalid reference: {_esc(ref)}</p>')

    book_name, ch, v = m.group(1), int(m.group(2)), int(m.group(3))
    book_num, _, _   = parse_reference(f"{book_name} {ch}:{v}")
    if not book_num:
        return _html(f'<p class="error-msg">Unknown book: {_esc(book_name)}</p>')

    conn = get_crossrefs_db()
    if not conn:
        return _html('<p class="error-msg">Cross-reference database not loaded.</p>')

    try:
        rows = conn.execute(
            "SELECT v_to_book_id, v_to_chapter, v_to_verse_start, votes"
            " FROM cross_references"
            " WHERE v_from_book_id=? AND v_from_chapter=? AND v_from_verse=?"
            " ORDER BY votes DESC, v_to_book_id, v_to_chapter, v_to_verse_start"
            " LIMIT ?",
            (book_num, ch, v, limit),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return _html(f'<p class="muted">No cross-references found for {_esc(ref)}.</p>')

    items = []
    for to_book_num, to_ch, to_v, votes in rows:
        to_book  = BOOKS.get(to_book_num, str(to_book_num))
        to_ref   = f"{to_book} {to_ch}:{to_v}"
        safe_ref = _esc(to_ref)
        safe_bk  = _esc(to_book)

        items.append(
            f'<li class="xref-item">'
            f'<button class="xref-link"'
            f' hx-get="/fragments/chapter"'
            f' hx-vals=\'{{"book":"{safe_bk}","chapter":"{to_ch}","tagged":"true"}}\''
            f' hx-target="#chapter-display" hx-swap="innerHTML"'
            f' @click="$store.reader.setBook(\'{safe_bk}\'); $store.reader.chapter={to_ch}">'
            f'{safe_ref}'
            f'</button>'
            + (f'<small class="votes">{votes}</small>' if votes else "")
            + f'</li>'
        )

    return _html(
        f'<div class="crossrefs-panel">'
        f'<h3>Cross-references for {_esc(ref)}</h3>'
        f'<ul class="crossrefs-list">{"".join(items)}</ul>'
        f'</div>'
    )


# ===========================================================================
# INTERLINEAR — word-by-word table
# ===========================================================================

@router.get("/interlinear", response_class=HTMLResponse)
async def fragment_interlinear(ref: str = Query(...)):
    """Render a word-by-word interlinear table for a single verse.

    Columns: position · original (Hebrew/Greek) · transliteration ·
    English gloss · Strong's number · morphology.

    Strong's numbers in the table are themselves clickable — clicking one
    loads the lexicon card into #strongs-panel via Alpine.js.
    A verse-level reference is required (e.g. "John 3:16", not "John 3").
    """
    book_num, chapter, verse = parse_reference(ref)
    if not book_num or not verse:
        return _html(
            '<p class="error-msg">A verse-level reference is required (e.g. John 3:16).</p>'
        )

    conn = get_interlinear_db()
    if not conn:
        return _html('<p class="error-msg">Interlinear database not loaded.</p>')

    try:
        rows = conn.execute(
            "SELECT word_num, original_word, transliteration, english_gloss,"
            "       strongs_num, morphology"
            " FROM interlinear WHERE book=? AND chapter=? AND verse=?"
            " ORDER BY word_num",
            (book_num, chapter, verse),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return _html(f'<p class="muted">No interlinear data found for {_esc(ref)}.</p>')

    body_rows = []
    for pos, original, translit, gloss, snum, morph in rows:
        # Determine text direction from the Strong's prefix:
        # H = Hebrew (right-to-left), G = Greek (left-to-right).
        orig_dir = 'dir="rtl"' if (snum or "").startswith("H") else ""
        strongs_cell = (
            f'<button class="strongs-link"'
            f' @click="$store.reader.openStrongs(\'{_esc(snum)}\')">'
            f'{_esc(snum)}</button>'
            if snum else ""
        )
        body_rows.append(
            f"<tr>"
            f"<td>{_esc(str(pos))}</td>"
            f"<td class='original' {orig_dir}>{_esc(original or '')}</td>"
            f"<td>{_esc(translit or '')}</td>"
            f"<td>{_esc(gloss or '')}</td>"
            f"<td>{strongs_cell}</td>"
            f"<td class='morph'>{_esc(morph or '')}</td>"
            f"</tr>"
        )

    return _html(
        f'<div class="interlinear-panel">'
        f'<h3>Interlinear: {_esc(ref)}</h3>'
        f'<div class="table-scroll">'
        f'<table class="interlinear-table">'
        f'<thead><tr>'
        f'<th>#</th><th>Original</th><th>Transliteration</th>'
        f'<th>Gloss</th><th>Strong\'s</th><th>Morphology</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        f'</table>'
        f'</div>'
        f'</div>'
    )


# ===========================================================================
# COMMENTARY — verse excerpts
# ===========================================================================

@router.get("/commentary", response_class=HTMLResponse)
async def fragment_commentary(ref: str = Query(...)):
    """Render commentary excerpts for a verse.

    Each excerpt is an <article> block with the author name as a heading.
    A verse-level reference is required (e.g. "Romans 8:28").
    """
    book_num, chapter, verse = parse_reference(ref)
    if not book_num or not verse:
        return _html('<p class="error-msg">A verse-level reference is required.</p>')

    conn = get_commentary_db()
    if not conn:
        return _html('<p class="error-msg">Commentary database not loaded.</p>')

    try:
        rows = conn.execute(
            "SELECT author, text FROM commentary"
            " WHERE book=? AND chapter=? AND verse=?"
            " ORDER BY author",
            (book_num, chapter, verse),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return _html(f'<p class="muted">No commentary available for {_esc(ref)}.</p>')

    entries = [
        f'<article class="commentary-entry">'
        f'<h4 class="commentary-author">{_esc(author)}</h4>'
        f'<p>{_esc(text)}</p>'
        f'</article>'
        for author, text in rows
    ]
    return _html(
        f'<div class="commentary-panel">'
        f'<h3>Commentary: {_esc(ref)}</h3>'
        + "".join(entries)
        + f'</div>'
    )


# ===========================================================================
# SEARCH — full-text verse search
# ===========================================================================

@router.get("/search", response_class=HTMLResponse)
async def fragment_search(
    q:           str = Query(..., min_length=2, description="Search term (2+ characters)"),
    translation: str = Query("KJV"),
    limit:       int = Query(30, ge=1, le=100),
):
    """Render search results as a navigable list of verse references.

    Results are ordered by canonical Bible order (book/chapter/verse).
    The search term is highlighted within each result snippet using <mark>.
    Each result is an htmx trigger that loads that chapter when clicked.

    This endpoint uses SQL LIKE which is case-insensitive for ASCII content.
    For a production deployment with millions of users, a dedicated FTS5
    index would be faster — but for a personal study tool this is fine.
    """
    conn, multi = get_db()
    if not conn:
        return _html('<p class="error-msg">Bible database not available.</p>')

    try:
        if multi:
            rows = conn.execute(
                "SELECT b, c, v, t FROM verses"
                " WHERE translation=? AND LOWER(t) LIKE LOWER(?)"
                " ORDER BY b, c, v LIMIT ?",
                (translation, f"%{q}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT b, c, v, t FROM t_kjv"
                " WHERE LOWER(t) LIKE LOWER(?)"
                " ORDER BY b, c, v LIMIT ?",
                (f"%{q}%", limit),
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        return _html(f'<p class="muted">No results for &ldquo;{_esc(q)}&rdquo;.</p>')

    q_lower = q.lower()
    items   = []
    for book_num, ch, v, text in rows:
        book_name = BOOKS.get(book_num, str(book_num))
        ref       = f"{book_name} {ch}:{v}"
        safe_bk   = _esc(book_name)
        safe_ref  = _esc(ref)

        # Highlight the matched term without double-escaping:
        # escape before the match, insert raw <mark> tags around it.
        start = text.lower().find(q_lower)
        if start >= 0:
            before = _esc(text[:start])
            match  = _esc(text[start:start + len(q)])
            after  = _esc(text[start + len(q):])
            snippet = f'{before}<mark>{match}</mark>{after}'
        else:
            snippet = _esc(text)

        items.append(
            f'<li class="search-result">'
            f'<button class="search-ref-btn"'
            f' hx-get="/fragments/chapter"'
            f' hx-vals=\'{{"book":"{safe_bk}","chapter":"{ch}","tagged":"true"}}\''
            f' hx-target="#chapter-display" hx-swap="innerHTML"'
            f' @click="$store.reader.setBook(\'{safe_bk}\'); $store.reader.chapter={ch}; $store.ui.closeSearch()">'
            f'<strong class="search-ref">{safe_ref}</strong>'
            f'<span class="search-snippet">{snippet}</span>'
            f'</button>'
            f'</li>'
        )

    count_note = (
        f" (first {limit})" if len(rows) == limit else ""
    )
    return _html(
        f'<div class="search-results">'
        f'<p class="result-count">{len(rows)} result{"s" if len(rows) != 1 else ""}{count_note}</p>'
        f'<ul class="result-list">{"".join(items)}</ul>'
        f'</div>'
    )

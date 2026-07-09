import sqlite3
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import aiofiles

app = FastAPI(title="Christ Pillar — Bible Study", docs_url=None)

DATA = Path("/app/data")
NOTES = Path("/app/notes")
NOTES.mkdir(exist_ok=True)

BOOKS = {
    1:"Genesis",2:"Exodus",3:"Leviticus",4:"Numbers",5:"Deuteronomy",
    6:"Joshua",7:"Judges",8:"Ruth",9:"1 Samuel",10:"2 Samuel",
    11:"1 Kings",12:"2 Kings",13:"1 Chronicles",14:"2 Chronicles",
    15:"Ezra",16:"Nehemiah",17:"Esther",18:"Job",19:"Psalms",20:"Proverbs",
    21:"Ecclesiastes",22:"Song of Solomon",23:"Isaiah",24:"Jeremiah",
    25:"Lamentations",26:"Ezekiel",27:"Daniel",28:"Hosea",29:"Joel",
    30:"Amos",31:"Obadiah",32:"Jonah",33:"Micah",34:"Nahum",35:"Habakkuk",
    36:"Zephaniah",37:"Haggai",38:"Zechariah",39:"Malachi",
    40:"Matthew",41:"Mark",42:"Luke",43:"John",44:"Acts",
    45:"Romans",46:"1 Corinthians",47:"2 Corinthians",48:"Galatians",
    49:"Ephesians",50:"Philippians",51:"Colossians",52:"1 Thessalonians",
    53:"2 Thessalonians",54:"1 Timothy",55:"2 Timothy",56:"Titus",
    57:"Philemon",58:"Hebrews",59:"James",60:"1 Peter",61:"2 Peter",
    62:"1 John",63:"2 John",64:"3 John",65:"Jude",66:"Revelation"
}
BOOK_ABBR = {v.lower(): k for k, v in BOOKS.items()}
BOOK_ABBR.update({
    "gen":1,"ex":2,"lev":3,"num":4,"deut":5,"josh":6,"judg":7,
    "1sa":9,"2sa":10,"1ki":11,"2ki":12,"1ch":13,"2ch":14,
    "ps":19,"psa":19,"prov":20,"eccl":21,"eccles":21,"song":22,"sos":22,
    "isa":23,"jer":24,"lam":25,"ezek":26,"dan":27,"hos":28,
    "zech":38,"mal":39,"matt":40,"mk":41,"lk":42,"jn":43,
    "rom":45,"1cor":46,"2cor":47,"gal":48,"eph":49,"phil":50,
    "col":51,"1th":52,"2th":53,"1ti":54,"2ti":55,"tit":56,
    "phm":57,"heb":58,"jas":59,"1pe":60,"2pe":61,"rev":66,
})

TRANSLATIONS = ['KJV', 'ASV', 'YLT', 'Darby', 'Geneva1599', 'Webster', 'BBE', 'BSB', 'Jubilee2000']

def get_db():
    # Use multi-translation DB if available, fall back to single KJV
    multi = DATA / "bible_multi.db"
    single = DATA / "kjv.db"
    if multi.exists():
        return sqlite3.connect(str(multi)), True
    if single.exists():
        return sqlite3.connect(str(single)), False
    return None, False

def get_strongs_db():
    db_path = DATA / "strongs.db"
    if not db_path.exists():
        return None
    return sqlite3.connect(str(db_path))


def parse_reference(ref: str):
    """Parse 'Genesis 1:1' or 'Gen 1:1' → (book_num, chapter, verse)"""
    ref = ref.strip()
    # Match "Book chapter:verse" or "Book chapter"
    m = re.match(r'^((?:\d\s+)?[a-zA-Z\s]+?)\s+(\d+)(?::(\d+))?$', ref)
    if not m:
        return None, None, None
    book_str = m.group(1).strip().lower().rstrip()
    chapter = int(m.group(2))
    verse = int(m.group(3)) if m.group(3) else None
    # Look up book
    book_num = BOOK_ABBR.get(book_str) or BOOK_ABBR.get(re.sub(r'\s+', '', book_str))
    if not book_num:
        # Try prefix match
        for abbr, num in BOOK_ABBR.items():
            if book_str.startswith(abbr) or abbr.startswith(book_str[:4]):
                book_num = num
                break
    return book_num, chapter, verse


@app.get("/", response_class=HTMLResponse)
async def index():
    template = Path("/app/templates/index.html")
    if template.exists():
        async with aiofiles.open(template) as f:
            return await f.read()
    return HTMLResponse(INLINE_HTML)


@app.get("/api/verse")
async def get_verse(
    ref: str = Query(..., description="e.g. 'John 3:16' or 'Proverbs 3'"),
    translation: str = Query("KJV", description="Translation code e.g. KJV, ASV, YLT, Darby")
):
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
                cur.execute("SELECT b, c, v, t FROM verses WHERE translation=? AND b=? AND c=? AND v=?",
                            (tr, book_num, chapter, verse))
            else:
                cur.execute("SELECT b, c, v, t FROM verses WHERE translation=? AND b=? AND c=? ORDER BY v",
                            (tr, book_num, chapter))
        else:
            # Single KJV DB fallback
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


@app.get("/api/compare")
async def compare_verse(ref: str = Query(...), translations: str = Query("KJV,ASV,YLT,Darby")):
    """Compare a verse across multiple translations side-by-side."""
    conn, multi = get_db()
    if not conn:
        raise HTTPException(503, "Bible database not loaded")
    try:
        book_num, chapter, verse = parse_reference(ref)
        if not book_num or not verse:
            raise HTTPException(400, "Comparison requires a specific verse (e.g. John 3:16)")
        trans_list = [t.strip() for t in translations.split(',')][:12]
        cur = conn.cursor()
        results = {}
        for tr in trans_list:
            if multi:
                row = cur.execute(
                    "SELECT t FROM verses WHERE translation=? AND b=? AND c=? AND v=?",
                    (tr, book_num, chapter, verse)
                ).fetchone()
            else:
                row = cur.execute(
                    "SELECT t FROM t_kjv WHERE b=? AND c=? AND v=?",
                    (book_num, chapter, verse)
                ).fetchone()
                tr = "KJV"
            if row:
                results[tr] = row[0]
        return {"reference": ref, "comparisons": results}
    finally:
        conn.close()


@app.get("/api/translations")
async def list_translations():
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


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=3),
    translation: str = Query("KJV"),
    limit: int = 20
):
    conn, multi = get_db()
    if not conn:
        raise HTTPException(503, "Bible database not loaded")
    try:
        cur = conn.cursor()
        tr = translation
        if multi:
            cur.execute(
                "SELECT b, c, v, t FROM verses WHERE translation=? AND t LIKE ? LIMIT ?",
                (tr, f"%{q}%", limit)
            )
        else:
            cur.execute("SELECT b, c, v, t FROM t_kjv WHERE t LIKE ? LIMIT ?", (f"%{q}%", limit))
            tr = "KJV"
        rows = cur.fetchall()
        results = [{"ref": f"{BOOKS.get(r[0])} {r[1]}:{r[2]}", "text": r[3]} for r in rows]
        return {"query": q, "translation": tr, "count": len(results), "results": results}
    finally:
        conn.close()


@app.get("/api/strongs/{number}")
async def strongs_lookup(number: str):
    """Look up a Strong's number: H1234 (Hebrew) or G5547 (Greek)"""
    db = get_strongs_db()
    if not db:
        raise HTTPException(503, "Strong's database not loaded")
    try:
        key = number.upper()
        row = db.execute(
            "SELECT number,language,original,transliteration,pronunciation,definition,kjv_usage FROM strongs WHERE number=?",
            (key,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Strong's {number} not found")
        return {
            "number": row[0], "language": row[1], "original": row[2],
            "transliteration": row[3], "pronunciation": row[4],
            "definition": row[5], "kjv_usage": row[6]
        }
    finally:
        db.close()


@app.get("/api/note/{ref}")
async def get_note(ref: str):
    safe = re.sub(r'[^\w\s\-:]', '', ref).strip().replace(' ', '_')
    note_file = NOTES / f"{safe}.md"
    if not note_file.exists():
        return {"ref": ref, "content": ""}
    async with aiofiles.open(note_file) as f:
        return {"ref": ref, "content": await f.read()}


@app.post("/api/note/{ref}")
async def save_note(ref: str, body: dict):
    safe = re.sub(r'[^\w\s\-:]', '', ref).strip().replace(' ', '_')
    note_file = NOTES / f"{safe}.md"
    async with aiofiles.open(note_file, 'w') as f:
        await f.write(body.get("content", ""))
    return {"status": "saved", "ref": ref}


@app.get("/api/books")
async def list_books():
    return {"books": [{"num": k, "name": v} for k, v in BOOKS.items()]}


@app.get("/api/health")
async def health():
    multi = (DATA / "bible_multi.db").exists()
    db_ok = multi or (DATA / "kjv.db").exists()
    strongs_ok = (DATA / "strongs.db").exists()
    return {"db": db_ok, "multi_translation": multi, "strongs": strongs_ok, "notes_dir": str(NOTES)}


INLINE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Christ Pillar — Bible Study</title>
<style>
  :root { --gold: #b8962e; --dark: #1a1a1a; --bg: #0f0f0f; --card: #1e1e1e; --text: #e8e4da; --muted: #888; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Georgia, serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  header { background: var(--card); border-bottom: 1px solid var(--gold); padding: 1rem 2rem; display: flex; align-items: center; gap: 1rem; }
  header h1 { font-size: 1.1rem; color: var(--gold); letter-spacing: 0.1em; font-weight: normal; }
  header span { color: var(--muted); font-size: 0.8rem; font-style: italic; }
  .container { max-width: 900px; margin: 0 auto; padding: 2rem 1rem; }
  .search-bar { display: flex; gap: 0.5rem; margin-bottom: 2rem; }
  .search-bar input { flex: 1; padding: 0.75rem 1rem; background: var(--card); border: 1px solid #333; border-radius: 4px; color: var(--text); font-size: 1rem; font-family: Georgia, serif; }
  .search-bar input:focus { outline: none; border-color: var(--gold); }
  .search-bar button { padding: 0.75rem 1.5rem; background: var(--gold); border: none; border-radius: 4px; color: var(--dark); cursor: pointer; font-weight: bold; }
  .tabs { display: flex; gap: 1rem; margin-bottom: 1.5rem; border-bottom: 1px solid #333; }
  .tab { padding: 0.5rem 1rem; cursor: pointer; border-bottom: 2px solid transparent; color: var(--muted); font-size: 0.9rem; }
  .tab.active { color: var(--gold); border-bottom-color: var(--gold); }
  .verse-result { background: var(--card); border-radius: 6px; padding: 1.5rem; margin-bottom: 1rem; }
  .verse-ref { color: var(--gold); font-size: 0.85rem; margin-bottom: 0.5rem; letter-spacing: 0.05em; }
  .verse-text { line-height: 1.8; font-size: 1.05rem; }
  .strongs-result { background: var(--card); border-radius: 6px; padding: 1.5rem; }
  .strongs-num { color: var(--gold); font-size: 1.2rem; font-weight: bold; margin-bottom: 0.5rem; }
  .strongs-original { font-size: 1.5rem; margin-bottom: 0.5rem; }
  .strongs-def { line-height: 1.7; color: var(--text); }
  .strongs-label { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 1rem; margin-bottom: 0.25rem; }
  .note-area { width: 100%; min-height: 200px; background: var(--card); border: 1px solid #333; border-radius: 4px; color: var(--text); font-family: Georgia, serif; font-size: 0.95rem; padding: 1rem; resize: vertical; }
  .note-area:focus { outline: none; border-color: var(--gold); }
  .save-btn { margin-top: 0.5rem; padding: 0.5rem 1.25rem; background: transparent; border: 1px solid var(--gold); color: var(--gold); border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
  .save-btn:hover { background: var(--gold); color: var(--dark); }
  .muted { color: var(--muted); font-style: italic; font-size: 0.9rem; }
  .error { color: #c0392b; font-size: 0.9rem; padding: 1rem; background: var(--card); border-radius: 4px; }
  #loading { color: var(--muted); text-align: center; padding: 2rem; display: none; }
</style>
</head>
<body>
<header>
  <h1>&#9770; THE CHRIST PILLAR</h1>
  <span>Bible Study — King James Version</span>
</header>
<div class="container">
  <div class="search-bar">
    <input type="text" id="query" placeholder="John 3:16  |  Proverbs 3  |  &quot;the fear of the Lord&quot;  |  H2617  |  G26" />
    <button onclick="search()">Search</button>
  </div>
  <div class="tabs">
    <div class="tab active" onclick="setTab('passage')">Passage</div>
    <div class="tab" onclick="setTab('keyword')">Keyword</div>
    <div class="tab" onclick="setTab('strongs')">Strong's</div>
    <div class="tab" onclick="setTab('notes')">Notes</div>
  </div>
  <div id="loading">Searching...</div>
  <div id="results"></div>
</div>
<script>
let currentTab = 'passage';
let currentRef = '';

function setTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['passage','keyword','strongs','notes'][i] === tab);
  });
  document.getElementById('results').innerHTML = '';
}

async function search() {
  const q = document.getElementById('query').value.trim();
  if (!q) return;
  document.getElementById('loading').style.display = 'block';
  document.getElementById('results').innerHTML = '';
  try {
    if (currentTab === 'strongs' || /^[HG]\\d+$/i.test(q)) {
      await lookupStrongs(q);
    } else if (currentTab === 'keyword' || q.startsWith('"')) {
      await keywordSearch(q.replace(/"/g,''));
    } else {
      await lookupVerse(q);
    }
  } catch(e) {
    document.getElementById('results').innerHTML = '<div class="error">'+e.message+'</div>';
  }
  document.getElementById('loading').style.display = 'none';
}

async function lookupVerse(ref) {
  currentRef = ref;
  const r = await fetch('/api/verse?ref='+encodeURIComponent(ref));
  if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Not found'); }
  const d = await r.json();
  let html = '';
  for (const v of d.verses) {
    html += '<div class="verse-result"><div class="verse-ref">'+v.book+' '+v.chapter+':'+v.verse+' (KJV)</div><div class="verse-text">'+v.text+'</div></div>';
  }
  if (d.verses.length === 0) html = '<p class="muted">No verses found for that reference.</p>';
  document.getElementById('results').innerHTML = html + noteSection(ref);
  loadNote(ref);
}

async function keywordSearch(q) {
  const r = await fetch('/api/search?q='+encodeURIComponent(q));
  if (!r.ok) throw new Error('Search failed');
  const d = await r.json();
  let html = '<p class="muted">'+d.count+' results for "'+q+'"</p><br>';
  for (const v of d.results) {
    const hl = v.text.replace(new RegExp('('+q+')','gi'), '<strong style="color:var(--gold)">$1</strong>');
    html += '<div class="verse-result"><div class="verse-ref">'+v.ref+'</div><div class="verse-text">'+hl+'</div></div>';
  }
  document.getElementById('results').innerHTML = html;
}

async function lookupStrongs(num) {
  const r = await fetch('/api/strongs/'+encodeURIComponent(num.toUpperCase()));
  if (!r.ok) throw new Error('Strong\'s '+num+' not found');
  const d = await r.json();
  document.getElementById('results').innerHTML = '<div class="strongs-result">'
    +'<div class="strongs-num">'+d.number+'</div>'
    +'<div class="strongs-original">'+d.original+'</div>'
    +'<div class="strongs-label">Transliteration</div><div>'+d.transliteration+' ('+d.pronunciation+')</div>'
    +'<div class="strongs-label">Definition</div><div class="strongs-def">'+d.definition+'</div>'
    +'<div class="strongs-label">KJV Usage</div><div class="strongs-def">'+d.kjv_usage+'</div>'
    +'</div>';
}

function noteSection(ref) {
  return '<div style="margin-top:2rem"><h3 style="color:var(--gold);font-size:0.9rem;letter-spacing:0.1em;margin-bottom:0.75rem">STUDY NOTES — '+ref+'</h3>'
    +'<textarea class="note-area" id="note-content" placeholder="Your notes on this passage..."></textarea>'
    +'<button class="save-btn" onclick="saveNote(\''+ref+'\')">Save Notes</button>'
    +'<span id="save-status" style="margin-left:1rem;color:var(--muted);font-size:0.85rem"></span></div>';
}

async function loadNote(ref) {
  try {
    const r = await fetch('/api/note/'+encodeURIComponent(ref));
    const d = await r.json();
    const el = document.getElementById('note-content');
    if (el) el.value = d.content;
  } catch(e) {}
}

async function saveNote(ref) {
  const content = document.getElementById('note-content').value;
  await fetch('/api/note/'+encodeURIComponent(ref), {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({content})
  });
  const s = document.getElementById('save-status');
  if (s) { s.textContent = 'Saved ✓'; setTimeout(() => s.textContent = '', 2000); }
}

document.getElementById('query').addEventListener('keydown', e => { if (e.key === 'Enter') search(); });
</script>
</body>
</html>"""

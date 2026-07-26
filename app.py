import sqlite3
import secrets
import time
import re
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
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

# Biblical places with coordinates (WGS84) and short descriptions
# Used for map tab: passage text is scanned for place name matches
PLACES = {
    # === HOLY LAND — CITIES & TOWNS ===
    "Jerusalem": {"lat": 31.7767, "lon": 35.2345, "notes": "City of David; site of the Temple; crucifixion and resurrection of Christ"},
    "Bethlehem": {"lat": 31.7054, "lon": 35.2024, "notes": "Birthplace of David and Jesus; Rachel's tomb nearby"},
    "Nazareth": {"lat": 32.7021, "lon": 35.2975, "notes": "Hometown of Jesus; where He was raised"},
    "Capernaum": {"lat": 32.8812, "lon": 35.5747, "notes": "Jesus' ministry headquarters on the Sea of Galilee"},
    "Jericho": {"lat": 31.8661, "lon": 35.4436, "notes": "First city conquered by Israel; walls fell at God's command"},
    "Hebron": {"lat": 31.5326, "lon": 35.0998, "notes": "Abraham, Isaac, Jacob and their wives buried here (Cave of Machpelah)"},
    "Beersheba": {"lat": 31.2530, "lon": 34.7915, "notes": "Southern boundary of Israel; 'from Dan to Beersheba'"},
    "Dan": {"lat": 33.2485, "lon": 35.6518, "notes": "Northern boundary of Israel; site of golden calf idolatry (Jeroboam)"},
    "Bethel": {"lat": 31.9290, "lon": 35.2197, "notes": "Jacob's ladder; 'house of God'; Ark housed here after conquest"},
    "Shechem": {"lat": 32.2087, "lon": 35.2856, "notes": "Where Abraham built first altar in Canaan; Joseph buried here"},
    "Sychar": {"lat": 32.2118, "lon": 35.2871, "notes": "Samaritan city; Jesus speaks with the woman at Jacob's Well"},
    "Samaria": {"lat": 32.2748, "lon": 35.1980, "notes": "Capital of northern kingdom of Israel; city of Omri"},
    "Shiloh": {"lat": 32.0567, "lon": 35.2919, "notes": "Home of the Tabernacle for 300+ years; where Hannah prayed"},
    "Gilgal": {"lat": 31.8681, "lon": 35.4561, "notes": "First campsite in Canaan; Israel circumcised; Saul anointed king"},
    "Gibeon": {"lat": 31.8391, "lon": 35.1771, "notes": "Sun stood still; Tabernacle housed here in Solomon's early reign"},
    "Mizpah": {"lat": 31.8737, "lon": 35.2153, "notes": "Samuel judged Israel; Saul chosen as first king by lot"},
    "Ramah": {"lat": 31.9197, "lon": 35.2203, "notes": "Birthplace of Samuel; Rachel weeping for her children"},
    "Gibeah": {"lat": 31.8462, "lon": 35.2214, "notes": "Capital of Saul; scene of the Levite's concubine outrage"},
    "Peniel": {"lat": 32.1896, "lon": 35.6082, "notes": "Where Jacob wrestled with God and received the name Israel"},
    "Dothan": {"lat": 32.3983, "lon": 35.2025, "notes": "Joseph thrown into pit by brothers; Elisha surrounded by angels here"},
    "Endor": {"lat": 32.6383, "lon": 35.3911, "notes": "Saul consulted the witch (medium) of Endor"},
    "Jezreel": {"lat": 32.5468, "lon": 35.3281, "notes": "Ahab's palace; Naboth's vineyard; Jezebel killed here"},
    "Megiddo": {"lat": 32.5837, "lon": 35.1842, "notes": "Strategic pass; site of many battles; Armageddon (Har Megiddo)"},
    "Hazor": {"lat": 33.0181, "lon": 35.5687, "notes": "Greatest Canaanite city; defeated by Joshua; rebuilt by Solomon"},
    "Lachish": {"lat": 31.5607, "lon": 34.8489, "notes": "Second-largest Judean city; besieged by Sennacherib and Nebuchadnezzar"},
    "Joppa": {"lat": 32.0519, "lon": 34.7507, "notes": "Jonah sailed from here; Peter raised Dorcas; received vision about Gentiles"},
    "Lydda": {"lat": 31.9530, "lon": 34.8950, "notes": "Peter healed Aeneas here; called Lod in OT"},
    "Caesarea": {"lat": 32.5002, "lon": 34.8891, "notes": "Roman capital of Judea; Cornelius' household; Paul imprisoned here"},
    "Caesarea Philippi": {"lat": 33.2484, "lon": 35.6941, "notes": "Peter's confession: 'Thou art the Christ'"},
    "Bethsaida": {"lat": 32.9069, "lon": 35.6372, "notes": "Hometown of Peter, Andrew, and Philip; Jesus healed a blind man"},
    "Chorazin": {"lat": 32.9183, "lon": 35.5583, "notes": "Condemned by Jesus for rejecting His miracles"},
    "Magdala": {"lat": 32.8336, "lon": 35.5100, "notes": "Hometown of Mary Magdalene"},
    "Cana": {"lat": 32.7467, "lon": 35.3403, "notes": "Jesus' first miracle: water to wine at a wedding"},
    "Nain": {"lat": 32.6408, "lon": 35.3533, "notes": "Jesus raised the widow's son from the dead"},
    "Emmaus": {"lat": 31.8406, "lon": 35.0616, "notes": "Jesus appeared to two disciples on the road after resurrection"},
    "Bethany": {"lat": 31.7742, "lon": 35.2633, "notes": "Home of Lazarus, Mary, and Martha; Jesus raised Lazarus here"},
    "Bethphage": {"lat": 31.7804, "lon": 35.2530, "notes": "Jesus sent for the colt here before His triumphal entry"},
    "Gethsemane": {"lat": 31.7794, "lon": 35.2420, "notes": "Garden where Jesus prayed and was arrested the night before crucifixion"},
    "Golgotha": {"lat": 31.7784, "lon": 35.2298, "notes": "Place of the skull; site of the crucifixion"},
    "Antioch": {"lat": 36.2021, "lon": 36.1607, "notes": "Disciples first called Christians here; Paul's missionary base"},
    "Gaza": {"lat": 31.5017, "lon": 34.4673, "notes": "Philistine city; Samson's captivity and death; Philip met the Ethiopian eunuch nearby"},
    "Ashkelon": {"lat": 31.6688, "lon": 34.5742, "notes": "Major Philistine city on the coast"},
    "Ashdod": {"lat": 31.8000, "lon": 34.6500, "notes": "Philistine city; Ark of the Covenant captured and placed in Dagon's temple"},
    "Ekron": {"lat": 31.7784, "lon": 34.8357, "notes": "Philistine city; where the Ark was returned to Israel"},
    "En Gedi": {"lat": 31.4611, "lon": 35.3889, "notes": "Wilderness oasis; David hid from Saul in caves here"},
    "Arad": {"lat": 31.2761, "lon": 35.1252, "notes": "Canaanite city defeated by Israel"},
    # === WATER BODIES ===
    "Sea of Galilee": {"lat": 32.8208, "lon": 35.5842, "notes": "Also called Lake of Gennesaret; site of much of Jesus' ministry; storms calmed"},
    "Jordan": {"lat": 32.0000, "lon": 35.5500, "notes": "Israel crossed into the promised land; Jesus baptized by John"},
    "Dead Sea": {"lat": 31.5590, "lon": 35.4732, "notes": "Saltiest lake on earth; cities of Sodom and Gomorrah were near here"},
    "Galilee": {"lat": 32.8000, "lon": 35.5000, "notes": "Northern region of Israel; Jesus' primary ministry area"},
    "Judea": {"lat": 31.5000, "lon": 35.0000, "notes": "Southern region; tribe of Judah; home of Jerusalem"},
    "Decapolis": {"lat": 32.6000, "lon": 35.9000, "notes": "League of ten Gentile cities east of Jordan; Jesus ministered here"},
    "Perea": {"lat": 31.8000, "lon": 35.7000, "notes": "Region east of Jordan; 'beyond Jordan' in Scripture"},
    # === MOUNTAINS ===
    "Sinai": {"lat": 28.5402, "lon": 33.9750, "notes": "Mountain of God; Moses received the Ten Commandments; Elijah fled here"},
    "Horeb": {"lat": 28.5402, "lon": 33.9750, "notes": "Another name for Sinai; burning bush; Elijah's still small voice"},
    "Zion": {"lat": 31.7717, "lon": 35.2292, "notes": "Hill of Jerusalem; City of David; the LORD's holy mountain"},
    "Carmel": {"lat": 32.7345, "lon": 34.9684, "notes": "Elijah's contest with 450 prophets of Baal; fire from heaven"},
    "Hermon": {"lat": 33.4148, "lon": 35.8569, "notes": "Highest peak in region; traditionally the Transfiguration site"},
    "Tabor": {"lat": 32.6870, "lon": 35.3931, "notes": "Traditional Transfiguration site; Barak gathered troops here"},
    "Nebo": {"lat": 31.7691, "lon": 35.7298, "notes": "Moses viewed the promised land from here; Moses died here"},
    "Ebal": {"lat": 32.2133, "lon": 35.2869, "notes": "Mountain of curses (Deut 27); Joshua built an altar here"},
    "Gerizim": {"lat": 32.1991, "lon": 35.2728, "notes": "Mountain of blessings; Samaritan temple site; woman at the well"},
    "Moriah": {"lat": 31.7782, "lon": 35.2357, "notes": "Abraham offered Isaac here; Solomon built the Temple here"},
    "Gilboa": {"lat": 32.5142, "lon": 35.4049, "notes": "Where Saul and Jonathan fell in battle against the Philistines"},
    # === REGIONS AROUND ISRAEL ===
    "Egypt": {"lat": 26.8206, "lon": 30.8025, "notes": "House of slavery; Joseph's rise; Exodus; flight of Jesus as infant"},
    "Goshen": {"lat": 30.7067, "lon": 31.9227, "notes": "Land in Egypt given to Jacob's family; protected from the plagues; Israel dwelt here"},
    "Memphis": {"lat": 29.8499, "lon": 31.2513, "notes": "Ancient Egyptian capital; called Noph in Scripture"},
    "Alexandria": {"lat": 31.2001, "lon": 29.9187, "notes": "Great Egyptian city; Apollos was from here (Acts 18:24)"},
    "Edom": {"lat": 30.5000, "lon": 35.5000, "notes": "Land of Esau; perpetual enemy of Israel; Petra (Sela) its capital"},
    "Petra": {"lat": 30.3285, "lon": 35.4444, "notes": "Rock city; capital of Edom/Nabataeans; called Sela in Scripture"},
    "Moab": {"lat": 31.2000, "lon": 35.8000, "notes": "East of Dead Sea; Ruth's homeland; Israel camped here before conquest"},
    "Ammon": {"lat": 31.9500, "lon": 35.9333, "notes": "East of Jordan; enemy of Israel; modern Amman"},
    "Midian": {"lat": 28.0000, "lon": 36.0000, "notes": "Moses fled here; married Zipporah; burning bush; Jethro's land"},
    "Bashan": {"lat": 32.9000, "lon": 36.0000, "notes": "Rich pastureland; giant Og's kingdom defeated by Israel"},
    "Gilead": {"lat": 32.1000, "lon": 35.9000, "notes": "East of Jordan; balm of Gilead; Jephthah's home; Elijah's birthplace"},
    "Philistia": {"lat": 31.7000, "lon": 34.6000, "notes": "Coastal plain; people of the sea; enemies of Israel for generations"},
    "Phoenicia": {"lat": 33.5000, "lon": 35.4000, "notes": "Lebanon coast; Tyre and Sidon; great seafarers and traders"},
    "Tyre": {"lat": 33.2705, "lon": 35.1954, "notes": "Great Phoenician port city; Hiram helped Solomon build the Temple"},
    "Sidon": {"lat": 33.5607, "lon": 35.3706, "notes": "Phoenician city north of Tyre; Jesus ministered here briefly"},
    # === MESOPOTAMIA ===
    "Ur": {"lat": 30.9625, "lon": 46.1031, "notes": "Abraham's birthplace; 'Ur of the Chaldees'; left by faith"},
    "Haran": {"lat": 36.8613, "lon": 39.0241, "notes": "Abraham's family settled here; Jacob fled here to Laban"},
    "Babylon": {"lat": 32.5427, "lon": 44.4212, "notes": "Nebuchadnezzar's empire; Israel exiled here; symbol of worldly power in Revelation"},
    "Nineveh": {"lat": 36.3583, "lon": 43.1425, "notes": "Assyrian capital; Jonah sent here; repented at preaching of Jonah"},
    "Assyria": {"lat": 36.0000, "lon": 43.0000, "notes": "Conquered northern Israel (722 BC); carried ten tribes into exile"},
    "Susa": {"lat": 32.1897, "lon": 48.2566, "notes": "Persian capital; Esther and Mordecai; Daniel's vision of the ram"},
    "Persepolis": {"lat": 29.9353, "lon": 52.8909, "notes": "Ceremonial capital of Persian Empire; Cyrus issued decree for Israelites to return"},
    "Carchemish": {"lat": 36.8308, "lon": 38.0111, "notes": "Battle where Nebuchadnezzar defeated Egypt (605 BC); Babylon rises to power"},
    # === NEW TESTAMENT — PAUL'S JOURNEYS ===
    "Damascus": {"lat": 33.5102, "lon": 36.2913, "notes": "Paul's conversion on the road here; blinded by light; Ananias restored his sight"},
    "Tarsus": {"lat": 36.9145, "lon": 34.8952, "notes": "Paul's birthplace; 'no mean city'"},
    "Cyprus": {"lat": 35.1264, "lon": 33.4299, "notes": "Barnabas' homeland; first stop on Paul's first journey; Sergius Paulus converted"},
    "Paphos": {"lat": 34.7751, "lon": 32.4228, "notes": "Capital of Cyprus; Paul blinded Elymas the sorcerer here"},
    "Perga": {"lat": 36.9611, "lon": 30.8570, "notes": "Coastal city; John Mark left Paul here on first journey"},
    "Iconium": {"lat": 37.8722, "lon": 32.4844, "notes": "Paul and Barnabas preached and were driven out; Lystra/Derbe nearby"},
    "Lystra": {"lat": 37.5836, "lon": 32.5233, "notes": "Paul stoned and left for dead; Timothy was from here"},
    "Derbe": {"lat": 37.3580, "lon": 33.3430, "notes": "Paul's furthest point on first journey; many disciples made"},
    "Troas": {"lat": 39.7532, "lon": 26.1606, "notes": "Paul's Macedonian vision; Eutychus fell from window and was raised"},
    "Philippi": {"lat": 41.0069, "lon": 24.2822, "notes": "First European church; Lydia converted; Paul and Silas jailed, earthquake"},
    "Thessalonica": {"lat": 40.6401, "lon": 22.9444, "notes": "Paul preached three Sabbaths; Jason's house attacked; church commended for faith"},
    "Berea": {"lat": 40.4686, "lon": 22.2007, "notes": "Bereans 'more noble' — searched Scriptures daily to verify Paul's teaching"},
    "Athens": {"lat": 37.9792, "lon": 23.7166, "notes": "Mars Hill (Areopagus); Paul's sermon on the Unknown God; Dionysius converted"},
    "Corinth": {"lat": 37.9055, "lon": 22.8786, "notes": "Paul's 18-month ministry; Priscilla and Aquila; letters to Corinthians"},
    "Ephesus": {"lat": 37.9413, "lon": 27.3426, "notes": "Temple of Artemis; Paul's 3-year ministry; riot of silversmiths; Timothy pastored here"},
    "Colossae": {"lat": 37.7756, "lon": 29.2975, "notes": "Church addressed in Colossians; Philemon's church; Epaphras founded it"},
    "Laodicea": {"lat": 37.8383, "lon": 29.1072, "notes": "Lukewarm church; 'neither hot nor cold'; Rev 3:15-16"},
    "Hierapolis": {"lat": 37.9239, "lon": 29.1251, "notes": "Near Colossae; Phillip the Evangelist buried here (tradition)"},
    "Pergamum": {"lat": 39.1293, "lon": 27.1837, "notes": "One of 7 churches; 'Satan's throne'; Balaam and Jezebel errors"},
    "Smyrna": {"lat": 38.4192, "lon": 27.1287, "notes": "One of 7 churches; praised for suffering; 'be faithful unto death'"},
    "Thyatira": {"lat": 38.9218, "lon": 27.8447, "notes": "Lydia's hometown; one of 7 churches; Jezebel false prophetess"},
    "Sardis": {"lat": 38.4882, "lon": 28.0438, "notes": "One of 7 churches; 'a name that you are alive, but you are dead'"},
    "Philadelphia": {"lat": 38.3534, "lon": 28.5154, "notes": "One of 7 churches; 'I have set before you an open door'"},
    "Patmos": {"lat": 37.3210, "lon": 26.5428, "notes": "Island where John received the Revelation in exile"},
    "Malta": {"lat": 35.9375, "lon": 14.3754, "notes": "Paul shipwrecked here; bitten by viper with no harm; healed many"},
    "Crete": {"lat": 35.2401, "lon": 24.8093, "notes": "Titus left here to set church in order; Cretans at Pentecost"},
    "Rome": {"lat": 41.9028, "lon": 12.4964, "notes": "Capital of the empire; Paul's letter to the Romans; Paul martyred here (tradition)"},
    "Macedonia": {"lat": 41.0000, "lon": 22.0000, "notes": "Northern Greece; Paul's vision 'Come over to Macedonia and help us'"},
    "Greece": {"lat": 38.0000, "lon": 23.5000, "notes": "Paul's journey through; Achaia in NT; Athens and Corinth"},
    "Arabia": {"lat": 27.0000, "lon": 37.0000, "notes": "Paul went here after conversion (Galatians 1:17); 3 years before Jerusalem"},
    "Galatia": {"lat": 39.0000, "lon": 33.0000, "notes": "Roman province; Paul's first journey churches; letter to the Galatians"},
    "Cappadocia": {"lat": 38.5000, "lon": 35.5000, "notes": "Roman province; mentioned in 1 Peter 1:1; Pentecost crowd (Acts 2:9)"},
    "Pontus": {"lat": 41.0000, "lon": 36.5000, "notes": "Aquila's birthplace; mentioned in 1 Peter 1:1"},
    "Bithynia": {"lat": 40.5000, "lon": 30.0000, "notes": "Paul prevented by Holy Spirit from going here (Acts 16:7)"},
    "Asia": {"lat": 38.5000, "lon": 27.5000, "notes": "Roman province (western Turkey); the 7 churches are here"},
    # === SINAI / WILDERNESS ===
    "Wilderness": {"lat": 30.5000, "lon": 34.0000, "notes": "Israel wandered 40 years; tested and formed as God's people"},
    "Kadesh": {"lat": 30.6417, "lon": 34.4067, "notes": "Israel's main camp in the Sinai wilderness; Miriam died here"},
    "Paran": {"lat": 29.5000, "lon": 33.5000, "notes": "Wilderness region; Ishmael lived here; Israel camped here"},
    "Rephidim": {"lat": 28.6000, "lon": 33.7000, "notes": "Water from the rock; Amalekites defeated while Moses held up his staff"},
    "Marah": {"lat": 29.5000, "lon": 33.0000, "notes": "Bitter water made sweet; Israel murmured against Moses here"},
}


# ---------------------------------------------------------------------------
# DB HELPERS
# ---------------------------------------------------------------------------

def get_db():
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


def get_users_db() -> sqlite3.Connection:
    """Return an open connection to /app/data/users.db (WAL mode, FK on)."""
    db_path = DATA / "users.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_crossrefs_db() -> Optional[sqlite3.Connection]:
    """Return an open connection to /app/data/cross_references.db, or None."""
    db_path = DATA / "cross_references.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_interlinear_db() -> Optional[sqlite3.Connection]:
    """Return an open connection to /app/data/interlinear.db, or None."""
    db_path = DATA / "interlinear.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_commentary_db() -> Optional[sqlite3.Connection]:
    """Return an open connection to /app/data/commentary.db, or None."""
    db_path = DATA / "commentary.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------------

def parse_reference(ref: str):
    ref = ref.strip()
    m = re.match(r'^((?:\d\s+)?[a-zA-Z\s]+?)\s+(\d+)(?::(\d+))?$', ref)
    if not m:
        return None, None, None
    book_str = m.group(1).strip().lower().rstrip()
    chapter = int(m.group(2))
    verse = int(m.group(3)) if m.group(3) else None
    book_num = BOOK_ABBR.get(book_str) or BOOK_ABBR.get(re.sub(r'\s+', '', book_str))
    if not book_num:
        for abbr, num in BOOK_ABBR.items():
            if book_str.startswith(abbr) or abbr.startswith(book_str[:4]):
                book_num = num
                break
    return book_num, chapter, verse


# ---------------------------------------------------------------------------
# STARTUP: users.db schema + default admin + legacy note migration
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
        """)

        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            password = secrets.token_hex(12)
            hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
            conn.execute(
                "INSERT INTO users(username, password_hash, display_name, role, created_at)"
                " VALUES('admin', ?, 'Administrator', 'admin', ?)",
                (hashed, int(time.time()))
            )
            conn.commit()
            print(f"[INIT] Admin account created. Username: admin  Password: {password}", flush=True)
            print("[INIT] Change this password immediately via POST /api/auth/register", flush=True)

        now = int(time.time())
        conn.execute(
            "DELETE FROM user_sessions WHERE expires_at < ? AND last_active < ?",
            (now, now - 604800)
        )
        conn.commit()
    finally:
        conn.close()


def migrate_file_notes() -> None:
    """
    One-time migration: import legacy /app/notes/*.md files as the admin user's notes.
    Runs only if the notes table is empty.
    """
    notes_dir = NOTES
    if not notes_dir.exists():
        return
    conn = get_users_db()
    try:
        existing_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        if existing_count > 0:
            return

        admin = conn.execute(
            "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1"
        ).fetchone()
        if not admin:
            return
        admin_id = admin[0]

        migrated = 0
        for note_file in notes_dir.glob("*.md"):
            stem = note_file.stem
            parts = stem.split("_")
            if len(parts) >= 3:
                verse_part = parts[-1]
                chap_part = parts[-2]
                book_parts = parts[:-2]
                if verse_part.isdigit() and chap_part.isdigit():
                    ref = " ".join(book_parts) + f" {chap_part}:{verse_part}"
                else:
                    ref = stem.replace("_", " ")
            else:
                ref = stem.replace("_", " ")

            try:
                body = note_file.read_text(encoding="utf-8")
            except Exception:
                continue

            if body.strip():
                conn.execute(
                    "INSERT OR IGNORE INTO notes(user_id, ref, body, updated_at) VALUES(?,?,?,?)",
                    (admin_id, ref, body, int(time.time()))
                )
                migrated += 1

        if migrated > 0:
            conn.commit()
            print(f"[INIT] Migrated {migrated} legacy note(s) to admin user.", flush=True)
    finally:
        conn.close()


@app.on_event("startup")
async def startup_event():
    init_users_db()
    migrate_file_notes()


# ---------------------------------------------------------------------------
# AUTH HELPERS
# ---------------------------------------------------------------------------

class UserRow:
    """Thin wrapper around a users row tuple."""
    def __init__(self, id: int, username: str, display_name: Optional[str], role: str):
        self.id = id
        self.username = username
        self.display_name = display_name
        self.role = role


def _resolve_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    """Extract raw token from Authorization header or __session cookie."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return request.cookies.get("__session")


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Optional[UserRow]:
    """Returns authenticated UserRow or None."""
    token = _resolve_token(request, authorization)
    if not token:
        return None
    now = int(time.time())
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT u.id, u.username, u.display_name, u.role "
            "FROM user_sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND (s.expires_at > ? OR s.last_active > ?)",
            (token, now, now - 604800)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE user_sessions SET last_active = ? WHERE token = ?",
            (now, token)
        )
        conn.commit()
        return UserRow(row[0], row[1], row[2], row[3])
    finally:
        conn.close()


def require_user(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> UserRow:
    """Returns authenticated UserRow or raises HTTP 401."""
    user = get_current_user(request, authorization)
    if user is None:
        raise HTTPException(401, detail="Authentication required")
    return user


def _create_session(conn: sqlite3.Connection, user_id: int) -> str:
    """Insert a new session token and return the raw token string."""
    token = secrets.token_hex(32)
    now = int(time.time())
    conn.execute(
        "INSERT INTO user_sessions(user_id, token, created_at, expires_at, last_active)"
        " VALUES(?, ?, ?, ?, ?)",
        (user_id, token, now, now + 2592000, now)
    )
    return token


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="__session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=2592000,
        path="/"
    )


def _clear_session_cookie(response: Response) -> None:
    response.set_cookie(
        key="__session",
        value="",
        httponly=True,
        samesite="lax",
        max_age=0,
        path="/"
    )


# ---------------------------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------------------------

class RegisterBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None


class LoginBody(BaseModel):
    username: str
    password: str


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


# ---------------------------------------------------------------------------
# BIBLE DATA ENDPOINTS (existing)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INLINE_HTML)


@app.get("/api/verse")
async def get_verse(
    ref: str = Query(...),
    translation: str = Query("KJV")
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


@app.get("/api/places")
async def get_places(ref: str = Query(None)):
    """Return biblical places with coordinates. Without ref: all places. With ref: places found in that passage's text."""
    if ref is None:
        return {
            "places": [
                {"name": name, "lat": data["lat"], "lon": data["lon"], "notes": data.get("notes", "")}
                for name, data in PLACES.items()
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
            if verse:
                rows = cur.execute(
                    "SELECT t FROM verses WHERE translation='KJV' AND b=? AND c=? AND v=?",
                    (book_num, chapter, verse)
                ).fetchall()
            else:
                rows = cur.execute(
                    "SELECT t FROM verses WHERE translation='KJV' AND b=? AND c=? ORDER BY v",
                    (book_num, chapter)
                ).fetchall()
        else:
            if verse:
                rows = cur.execute("SELECT t FROM t_kjv WHERE b=? AND c=? AND v=?",
                                   (book_num, chapter, verse)).fetchall()
            else:
                rows = cur.execute("SELECT t FROM t_kjv WHERE b=? AND c=? ORDER BY v",
                                   (book_num, chapter)).fetchall()
        passage_text = " ".join(r[0] for r in rows)
        found = []
        for name, data in PLACES.items():
            if re.search(r'\b' + re.escape(name) + r'\b', passage_text, re.IGNORECASE):
                found.append({
                    "name": name,
                    "lat": data["lat"],
                    "lon": data["lon"],
                    "notes": data.get("notes", "")
                })
        return {"reference": ref, "passage_length": len(rows), "places": found}
    finally:
        conn.close()


@app.get("/api/books")
async def list_books():
    return {"books": [{"num": k, "name": v} for k, v in BOOKS.items()]}


@app.get("/api/health")
async def health():
    multi = (DATA / "bible_multi.db").exists()
    db_ok = multi or (DATA / "kjv.db").exists()
    strongs_ok = (DATA / "strongs.db").exists()
    crossrefs_ok = (DATA / "cross_references.db").exists()
    interlinear_ok = (DATA / "interlinear.db").exists()
    commentary_ok = (DATA / "commentary.db").exists()
    users_ok = (DATA / "users.db").exists()
    return {
        "db": db_ok,
        "multi_translation": multi,
        "strongs": strongs_ok,
        "crossrefs": crossrefs_ok,
        "interlinear": interlinear_ok,
        "commentary": commentary_ok,
        "users_db": users_ok,
        "notes_dir": str(NOTES),
        "places_count": len(PLACES)
    }


# ---------------------------------------------------------------------------
# BIBLE DATA: NEW CONTENT ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/api/verse/tagged")
async def get_tagged_verse(ref: str = Query(...)):
    """Return KJV verse text with per-word Strong's numbers from the word_strongs table."""
    book_num, chapter, verse = parse_reference(ref)
    if not book_num or not verse:
        raise HTTPException(400, f"Tagged verse requires a specific verse reference: {ref}")

    kjv_path = DATA / "kjv.db"
    multi_path = DATA / "bible_multi.db"
    db_path = multi_path if multi_path.exists() else kjv_path
    if not db_path.exists():
        raise HTTPException(503, "Bible database not loaded")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='word_strongs'"
        ).fetchone()
        if not has_table:
            raise HTTPException(503, "word_strongs table not populated yet")

        rows = conn.execute(
            """
            SELECT ws.word_position, ws.phrase_text, ws.strong_number,
                   ws.extra_strongs, ws.morph,
                   s.original, s.definition
            FROM word_strongs ws
            LEFT JOIN (
                SELECT number, original, definition FROM strongs
            ) s ON s.number = ws.strong_number
            WHERE ws.book_id = ? AND ws.chapter = ? AND ws.verse = ?
            ORDER BY ws.word_position
            """,
            (book_num, chapter, verse)
        ).fetchall()

        if not rows:
            raise HTTPException(404, f"No tagged data found for {ref}")

        words = [
            {
                "pos": r["word_position"],
                "text": r["phrase_text"],
                "strongs": r["strong_number"],
                "extra_strongs": r["extra_strongs"],
                "morph": r["morph"],
                "original": r["original"],
                "definition": r["definition"],
            }
            for r in rows
        ]
        return {"reference": ref, "words": words}
    finally:
        conn.close()


@app.get("/api/crossrefs")
async def get_crossrefs(
    ref: str = Query(...),
    min_votes: int = Query(0),
    limit: int = Query(25, ge=1, le=200),
):
    """Return cross-references for a verse from the cross_references.db."""
    ref = ref.strip()
    m = re.match(r'^(.*?)\s+(\d+):(\d+)$', ref)
    if not m:
        raise HTTPException(400, f"Could not parse reference: {ref}")
    book_name = m.group(1).strip()
    chapter = int(m.group(2))
    verse = int(m.group(3))

    db = get_crossrefs_db()
    if not db:
        raise HTTPException(503, "Cross-references database not loaded")
    try:
        rows = db.execute(
            """
            SELECT to_book, to_chapter, to_verse_start, to_verse_end, votes
            FROM cross_refs
            WHERE from_book = ? AND from_chapter = ? AND from_verse = ?
              AND votes >= ?
            ORDER BY votes DESC
            LIMIT ?
            """,
            (book_name, chapter, verse, min_votes, limit)
        ).fetchall()

        cross_refs = [
            {
                "book": r["to_book"],
                "chapter": r["to_chapter"],
                "verse_start": r["to_verse_start"],
                "verse_end": r["to_verse_end"],
                "votes": r["votes"],
            }
            for r in rows
        ]
        return {"ref": ref, "cross_references": cross_refs}
    finally:
        db.close()


@app.get("/api/interlinear")
async def get_interlinear(ref: str = Query(...)):
    """Return word-level Hebrew/Greek interlinear data for a single verse."""
    book_num, chapter, verse = parse_reference(ref)
    if not book_num or not verse:
        raise HTTPException(400, f"Interlinear requires a specific verse reference: {ref}")

    db = get_interlinear_db()
    if not db:
        raise HTTPException(503, "Interlinear database not loaded")
    try:
        rows = db.execute(
            """
            SELECT word_num, testament, original_word, transliteration,
                   strongs_num, morphology, english_gloss
            FROM interlinear
            WHERE book = ? AND chapter = ? AND verse = ?
            ORDER BY word_num
            """,
            (book_num, chapter, verse)
        ).fetchall()

        if not rows:
            raise HTTPException(404, f"No interlinear data found for {ref}")

        testament = rows[0]["testament"]

        strongs_db = None
        strongs_path = DATA / "strongs.db"
        if strongs_path.exists():
            strongs_db = sqlite3.connect(str(strongs_path))
            strongs_db.row_factory = sqlite3.Row

        words = []
        for r in rows:
            entry = {
                "num": r["word_num"],
                "original": r["original_word"],
                "translit": r["transliteration"],
                "strongs": r["strongs_num"],
                "morph": r["morphology"],
                "gloss": r["english_gloss"],
                "definition": None,
            }
            if strongs_db and r["strongs_num"]:
                s_row = strongs_db.execute(
                    "SELECT definition FROM strongs WHERE number = ?",
                    (r["strongs_num"],)
                ).fetchone()
                if s_row:
                    entry["definition"] = s_row["definition"]
            words.append(entry)

        if strongs_db:
            strongs_db.close()

        return {"ref": ref, "testament": testament, "words": words}
    finally:
        db.close()


@app.get("/api/commentary")
async def get_commentary(ref: str = Query(...)):
    """Return Matthew Henry commentary section(s) that cover the requested verse."""
    book_num, chapter, verse = parse_reference(ref)
    if not book_num or not verse:
        raise HTTPException(400, f"Commentary requires a specific verse reference: {ref}")

    db = get_commentary_db()
    if not db:
        raise HTTPException(503, "Commentary database not loaded")
    try:
        rows = db.execute(
            """
            SELECT verse_start, verse_end, author, text
            FROM commentary
            WHERE book = ? AND chapter = ?
              AND (verse_start IS NULL OR verse_start <= ?)
              AND (verse_end   IS NULL OR verse_end   >= ?)
            ORDER BY verse_start NULLS FIRST
            """,
            (book_num, chapter, verse, verse)
        ).fetchall()

        sections = [
            {
                "verse_start": r["verse_start"],
                "verse_end": r["verse_end"],
                "author": r["author"],
                "text": r["text"],
            }
            for r in rows
        ]
        return {"ref": ref, "commentary": sections}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AUTH ENDPOINTS
# ---------------------------------------------------------------------------

@app.post("/api/auth/register", status_code=201)
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
                (body.username, hashed, body.display_name, now)
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, detail="Username already taken")

        user_row = conn.execute(
            "SELECT id, display_name, role FROM users WHERE username = ?",
            (body.username,)
        ).fetchone()
        uid, display_name, role = user_row[0], user_row[1], user_row[2]

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
            }
        }
    finally:
        conn.close()


@app.post("/api/auth/login")
async def auth_login(body: LoginBody, response: Response):
    """Authenticate with username + password; returns session token + user object."""
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id, password_hash, display_name, role FROM users WHERE username = ?",
            (body.username,)
        ).fetchone()
        if not row:
            raise HTTPException(401, detail="Invalid credentials")

        uid, stored_hash, display_name, role = row[0], row[1], row[2], row[3]
        if not bcrypt.checkpw(body.password.encode("utf-8"), stored_hash.encode("utf-8")):
            raise HTTPException(401, detail="Invalid credentials")

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
            }
        }
    finally:
        conn.close()


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response,
                      authorization: Optional[str] = Header(None)):
    """Delete the current session (idempotent)."""
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


@app.get("/api/auth/me")
async def auth_me(request: Request, authorization: Optional[str] = Header(None)):
    """Return the currently authenticated user's profile."""
    user = get_current_user(request, authorization)
    if user is None:
        raise HTTPException(401, detail="Authentication required")
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }


# ---------------------------------------------------------------------------
# STUDY SESSIONS
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
async def list_sessions(request: Request, authorization: Optional[str] = Header(None)):
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT id, name, updated_at FROM study_sessions"
            " WHERE user_id = ? ORDER BY updated_at DESC",
            (user.id,)
        ).fetchall()
        return [{"id": r[0], "name": r[1], "updated_at": r[2]} for r in rows]
    finally:
        conn.close()


@app.post("/api/sessions", status_code=201)
async def create_session(
    body: SessionCreateBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        cur = conn.execute(
            "INSERT INTO study_sessions(user_id, name, state_json, created_at, updated_at)"
            " VALUES(?, ?, ?, ?, ?)",
            (user.id, body.name, body.state_json, now, now)
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": body.name, "updated_at": now}
    finally:
        conn.close()


@app.get("/api/sessions/{sid}")
async def get_session(
    sid: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id, name, state_json, created_at, updated_at"
            " FROM study_sessions WHERE id = ? AND user_id = ?",
            (sid, user.id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return {
            "id": row[0],
            "name": row[1],
            "state_json": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
    finally:
        conn.close()


@app.put("/api/sessions/{sid}")
async def update_session(
    sid: int,
    body: SessionUpdateBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        result = conn.execute(
            """
            UPDATE study_sessions
            SET name       = COALESCE(?, name),
                state_json = COALESCE(?, state_json),
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (body.name, body.state_json, now, sid, user.id)
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Session not found")
        conn.commit()
        row = conn.execute(
            "SELECT id, name, state_json, created_at, updated_at"
            " FROM study_sessions WHERE id = ?",
            (sid,)
        ).fetchone()
        return {
            "id": row[0],
            "name": row[1],
            "state_json": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
    finally:
        conn.close()


@app.delete("/api/sessions/{sid}", status_code=204)
async def delete_session(
    sid: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        result = conn.execute(
            "DELETE FROM study_sessions WHERE id = ? AND user_id = ?",
            (sid, user.id)
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Session not found")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# BOOKMARKS
# NOTE: /api/bookmarks/check MUST be registered before /api/bookmarks/{bid}
# ---------------------------------------------------------------------------

@app.get("/api/bookmarks/check")
async def check_bookmark(
    ref: str = Query(...),
    request: Request = None,
    authorization: Optional[str] = Header(None),
):
    if request is None:
        return {"bookmarked": False}
    user = get_current_user(request, authorization)
    if user is None:
        return {"bookmarked": False}
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT id FROM bookmarks WHERE user_id = ? AND ref = ?",
            (user.id, ref)
        ).fetchone()
        if row:
            return {"bookmarked": True, "id": row[0]}
        return {"bookmarked": False}
    finally:
        conn.close()


@app.get("/api/bookmarks")
async def list_bookmarks(request: Request, authorization: Optional[str] = Header(None)):
    user = get_current_user(request, authorization)
    if user is None:
        return []
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT id, ref, label, color, created_at"
            " FROM bookmarks WHERE user_id = ? ORDER BY created_at DESC",
            (user.id,)
        ).fetchall()
        return [
            {
                "id": r[0], "ref": r[1], "label": r[2],
                "color": r[3], "created_at": r[4]
            }
            for r in rows
        ]
    finally:
        conn.close()


@app.post("/api/bookmarks", status_code=201)
async def create_bookmark(
    body: BookmarkCreateBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            """
            INSERT INTO bookmarks(user_id, ref, label, color, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(user_id, ref)
            DO UPDATE SET label = excluded.label, color = excluded.color
            """,
            (user.id, body.ref, body.label, body.color, now)
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, ref, label, color, created_at"
            " FROM bookmarks WHERE user_id = ? AND ref = ?",
            (user.id, body.ref)
        ).fetchone()
        return {"id": row[0], "ref": row[1], "label": row[2], "color": row[3], "created_at": row[4]}
    finally:
        conn.close()


@app.delete("/api/bookmarks/{bid}", status_code=204)
async def delete_bookmark(
    bid: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        result = conn.execute(
            "DELETE FROM bookmarks WHERE id = ? AND user_id = ?",
            (bid, user.id)
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Bookmark not found")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# READING HISTORY
# ---------------------------------------------------------------------------

@app.post("/api/history", status_code=201)
async def add_history(
    body: HistoryBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            "INSERT INTO reading_history(user_id, ref, visited_at) VALUES(?, ?, ?)",
            (user.id, body.ref, now)
        )
        conn.execute(
            """
            DELETE FROM reading_history
            WHERE user_id = ?
              AND id NOT IN (
                SELECT id FROM reading_history
                WHERE user_id = ?
                ORDER BY visited_at DESC
                LIMIT 100
              )
            """,
            (user.id, user.id)
        )
        conn.commit()
        return {"ref": body.ref, "visited_at": now}
    finally:
        conn.close()


@app.get("/api/history")
async def get_history(request: Request, authorization: Optional[str] = Header(None)):
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT ref, visited_at FROM reading_history"
            " WHERE user_id = ? ORDER BY visited_at DESC LIMIT 20",
            (user.id,)
        ).fetchall()
        return [{"ref": r[0], "visited_at": r[1]} for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# NOTES — User-scoped (replaces legacy file-based /api/note/{ref} endpoints)
# ---------------------------------------------------------------------------

@app.get("/api/note/{ref:path}")
async def get_note_user(
    ref: str,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Return the authenticated user's note for this reference."""
    user = require_user(request, authorization)
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT body, updated_at FROM notes WHERE user_id = ? AND ref = ?",
            (user.id, ref)
        ).fetchone()
        if row:
            return {"ref": ref, "body": row[0], "updated_at": row[1]}
        return {"ref": ref, "body": "", "updated_at": None}
    finally:
        conn.close()


@app.post("/api/note/{ref:path}")
async def save_note_user(
    ref: str,
    body: NoteBody,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Insert or update the authenticated user's note for this reference."""
    user = require_user(request, authorization)
    now = int(time.time())
    conn = get_users_db()
    try:
        conn.execute(
            """
            INSERT INTO notes(user_id, ref, body, updated_at) VALUES(?, ?, ?, ?)
            ON CONFLICT(user_id, ref)
            DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at
            """,
            (user.id, ref, body.body, now)
        )
        conn.commit()
        return {"status": "ok", "ref": ref, "updated_at": now}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# FRONTEND
# ---------------------------------------------------------------------------

INLINE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Christ Pillar — Bible Study</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root { --gold: #b8962e; --dark: #1a1a1a; --bg: #0f0f0f; --card: #1e1e1e; --text: #e8e4da; --muted: #888; --accent: #c9a84c; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Georgia, serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  header { background: var(--card); border-bottom: 1px solid var(--gold); padding: 1rem 2rem; display: flex; align-items: center; gap: 1rem; }
  header h1 { font-size: 1.1rem; color: var(--gold); letter-spacing: 0.1em; font-weight: normal; }
  header span { color: var(--muted); font-size: 0.8rem; font-style: italic; }
  .container { max-width: 960px; margin: 0 auto; padding: 2rem 1rem; }
  .search-bar { display: flex; gap: 0.5rem; margin-bottom: 1.25rem; }
  .search-bar input { flex: 1; padding: 0.75rem 1rem; background: var(--card); border: 1px solid #333; border-radius: 4px; color: var(--text); font-size: 1rem; font-family: Georgia, serif; }
  .search-bar input:focus { outline: none; border-color: var(--gold); }
  .search-bar button { padding: 0.75rem 1.5rem; background: var(--gold); border: none; border-radius: 4px; color: var(--dark); cursor: pointer; font-weight: bold; }
  .tabs { display: flex; gap: 1rem; margin-bottom: 1.5rem; border-bottom: 1px solid #333; }
  .tab { padding: 0.5rem 1rem; cursor: pointer; border-bottom: 2px solid transparent; color: var(--muted); font-size: 0.9rem; transition: color 0.2s; }
  .tab.active { color: var(--gold); border-bottom-color: var(--gold); }
  .tab:hover { color: var(--accent); }
  .verse-result { background: var(--card); border-radius: 6px; padding: 1.5rem; margin-bottom: 1rem; }
  .verse-ref { color: var(--gold); font-size: 0.85rem; margin-bottom: 0.5rem; letter-spacing: 0.05em; }
  .verse-text { line-height: 1.8; font-size: 1.05rem; }
  .compare-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
  .compare-card { background: var(--card); border-radius: 6px; padding: 1.25rem; border-left: 3px solid var(--gold); }
  .compare-label { color: var(--gold); font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.5rem; }
  .compare-text { line-height: 1.7; font-size: 0.95rem; }
  .strongs-result { background: var(--card); border-radius: 6px; padding: 1.5rem; }
  .strongs-num { color: var(--gold); font-size: 1.2rem; font-weight: bold; margin-bottom: 0.5rem; }
  .strongs-original { font-size: 1.5rem; margin-bottom: 0.5rem; }
  .strongs-def { line-height: 1.7; color: var(--text); }
  .strongs-label { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 1rem; margin-bottom: 0.25rem; }
  .note-area { width: 100%; min-height: 200px; background: var(--card); border: 1px solid #333; border-radius: 4px; color: var(--text); font-family: Georgia, serif; font-size: 0.95rem; padding: 1rem; resize: vertical; }
  .note-area:focus { outline: none; border-color: var(--gold); }
  .save-btn { margin-top: 0.5rem; padding: 0.5rem 1.25rem; background: transparent; border: 1px solid var(--gold); color: var(--gold); border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
  .save-btn:hover { background: var(--gold); color: var(--dark); }
  .map-btn { display: inline-flex; align-items: center; gap: 0.4rem; margin-top: 1rem; padding: 0.45rem 1rem; background: transparent; border: 1px solid #444; color: var(--muted); border-radius: 4px; cursor: pointer; font-size: 0.85rem; font-family: Georgia, serif; transition: all 0.2s; }
  .map-btn:hover { border-color: var(--gold); color: var(--gold); }
  .compare-btn { padding: 0.45rem 1rem; background: transparent; border: 1px solid #444; color: var(--muted); border-radius: 4px; cursor: pointer; font-size: 0.85rem; font-family: Georgia, serif; margin-bottom: 1rem; transition: all 0.2s; }
  .compare-btn:hover { border-color: var(--gold); color: var(--gold); }
  .muted { color: var(--muted); font-style: italic; font-size: 0.9rem; }
  .error { color: #c0392b; font-size: 0.9rem; padding: 1rem; background: var(--card); border-radius: 4px; }
  #loading { color: var(--muted); text-align: center; padding: 2rem; display: none; }
  /* Map pane */
  #map-pane { display: none; }
  #map { height: 520px; border-radius: 6px; border: 1px solid #333; }
  .map-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
  .map-title { color: var(--gold); font-size: 0.95rem; letter-spacing: 0.05em; }
  .map-search { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
  .map-search input { flex: 1; padding: 0.5rem 0.75rem; background: var(--card); border: 1px solid #333; border-radius: 4px; color: var(--text); font-family: Georgia, serif; font-size: 0.9rem; }
  .map-search input:focus { outline: none; border-color: var(--gold); }
  .map-search button { padding: 0.5rem 1rem; background: var(--gold); border: none; border-radius: 4px; color: var(--dark); cursor: pointer; font-size: 0.85rem; }
  .place-list { margin-top: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .place-chip { background: var(--card); border: 1px solid #333; border-radius: 3px; padding: 0.3rem 0.6rem; font-size: 0.8rem; color: var(--muted); cursor: pointer; transition: all 0.15s; }
  .place-chip:hover, .place-chip.active { border-color: var(--gold); color: var(--gold); }
  .place-count { color: var(--muted); font-size: 0.85rem; margin-bottom: 0.5rem; }
  /* Leaflet popup override */
  .leaflet-popup-content-wrapper { background: #1e1e1e; color: #e8e4da; border: 1px solid #b8962e; border-radius: 4px; }
  .leaflet-popup-tip { background: #1e1e1e; }
  .leaflet-popup-content { font-family: Georgia, serif; font-size: 0.9rem; line-height: 1.5; }
  .leaflet-popup-content strong { color: #b8962e; }
  .leaflet-container a.leaflet-popup-close-button { color: #888; }
</style>
</head>
<body>
<header>
  <h1>&#9770; THE CHRIST PILLAR</h1>
  <span>Bible Study — study.wittycomp.com</span>
</header>
<div class="container">
  <div class="search-bar">
    <input type="text" id="query" placeholder="John 3:16  |  Exodus 3  |  &quot;the fear of the Lord&quot;  |  H2617  |  G26" />
    <button onclick="search()">Search</button>
  </div>
  <div class="tabs">
    <div class="tab active" onclick="setTab('passage')">Passage</div>
    <div class="tab" onclick="setTab('compare')">Compare</div>
    <div class="tab" onclick="setTab('keyword')">Keyword</div>
    <div class="tab" onclick="setTab('strongs')">Strong's</div>
    <div class="tab" onclick="setTab('maps')">Maps</div>
    <div class="tab" onclick="setTab('notes')">Notes</div>
  </div>
  <div id="loading">Searching...</div>
  <div id="results"></div>
  <div id="map-pane">
    <div class="map-header">
      <span class="map-title" id="map-title">Biblical Geography</span>
    </div>
    <div class="map-search">
      <input type="text" id="place-search" placeholder="Search a place: Jerusalem, Babylon, Ephesus..." />
      <button onclick="searchPlace()">Go</button>
    </div>
    <div id="map"></div>
    <div class="place-list" id="place-chips"></div>
  </div>
</div>
<script>
let currentTab = 'passage';
let currentRef = '';
let map = null;
let allMarkers = {};
let passageMarkers = [];
let allPlaces = {};

function setTab(tab) {
  currentTab = tab;
  const tabNames = ['passage','compare','keyword','strongs','maps','notes'];
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', tabNames[i] === tab);
  });
  if (tab !== 'maps') {
    document.getElementById('map-pane').style.display = 'none';
    document.getElementById('results').style.display = '';
  } else {
    document.getElementById('results').style.display = 'none';
    document.getElementById('map-pane').style.display = '';
    initMap();
  }
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
    } else if (currentTab === 'compare') {
      await compareVerse(q);
    } else if (currentTab === 'maps') {
      await mapPassage(q);
    } else {
      await lookupVerse(q);
    }
  } catch(e) {
    document.getElementById('results').innerHTML = '<div class="error">'+e.message+'</div>';
    document.getElementById('results').style.display = '';
  }
  document.getElementById('loading').style.display = 'none';
}

async function lookupVerse(ref) {
  currentRef = ref;
  const tParam = '';
  const r = await fetch('/api/verse?ref='+encodeURIComponent(ref));
  if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Not found'); }
  const d = await r.json();
  let html = '<div style="display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap;">';
  html += '<button class="compare-btn" onclick="compareVerse(\\''+ref+'\\')">Compare Translations</button>';
  html += '<button class="map-btn" onclick="mapPassage(\\''+ref+'\\')">&#127757; Map This Passage</button>';
  html += '</div>';
  for (const v of d.verses) {
    html += '<div class="verse-result"><div class="verse-ref">'+v.book+' '+v.chapter+':'+v.verse+' ('+d.translation+')</div><div class="verse-text">'+v.text+'</div></div>';
  }
  if (d.verses.length === 0) html += '<p class="muted">No verses found for that reference.</p>';
  html += noteSection(ref);
  document.getElementById('results').innerHTML = html;
  document.getElementById('results').style.display = '';
  loadNote(ref);
}

async function compareVerse(ref) {
  if (!ref) ref = document.getElementById('query').value.trim();
  currentRef = ref;
  setTab('compare');
  const allTrans = 'KJV,ASV,YLT,Darby,Geneva1599,Webster,BBE,BSB,Jubilee2000';
  const r = await fetch('/api/compare?ref='+encodeURIComponent(ref)+'&translations='+allTrans);
  if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Not found'); }
  const d = await r.json();
  const comps = d.comparisons;
  const keys = Object.keys(comps);
  if (keys.length === 0) {
    document.getElementById('results').innerHTML = '<p class="muted">No comparison data for that reference. Try a specific verse like John 3:16.</p>';
    document.getElementById('results').style.display = '';
    return;
  }
  let html = '<p style="color:var(--gold);font-size:0.9rem;letter-spacing:0.05em;margin-bottom:1rem">'+ref+' — '+keys.length+' translations</p>';
  html += '<div class="compare-grid">';
  for (const [tr, text] of Object.entries(comps)) {
    html += '<div class="compare-card"><div class="compare-label">'+tr+'</div><div class="compare-text">'+text+'</div></div>';
  }
  html += '</div>';
  document.getElementById('results').innerHTML = html;
  document.getElementById('results').style.display = '';
}

async function keywordSearch(q) {
  setTab('keyword');
  const r = await fetch('/api/search?q='+encodeURIComponent(q));
  if (!r.ok) throw new Error('Search failed');
  const d = await r.json();
  let html = '<p class="muted">'+d.count+' results for \\"'+q+'\\" in '+d.translation+'</p><br>';
  for (const v of d.results) {
    const hl = v.text.replace(new RegExp('('+q+')','gi'), '<strong style="color:var(--gold)">$1</strong>');
    html += '<div class="verse-result"><div class="verse-ref">'+v.ref+'</div><div class="verse-text">'+hl+'</div></div>';
  }
  document.getElementById('results').innerHTML = html;
  document.getElementById('results').style.display = '';
}

async function lookupStrongs(num) {
  setTab('strongs');
  const r = await fetch('/api/strongs/'+encodeURIComponent(num.toUpperCase()));
  if (!r.ok) throw new Error('Strong\\'s '+num+' not found');
  const d = await r.json();
  document.getElementById('results').innerHTML = '<div class="strongs-result">'
    +'<div class="strongs-num">'+d.number+'</div>'
    +'<div class="strongs-original">'+d.original+'</div>'
    +'<div class="strongs-label">Transliteration</div><div>'+d.transliteration+' ('+d.pronunciation+')</div>'
    +'<div class="strongs-label">Definition</div><div class="strongs-def">'+d.definition+'</div>'
    +'<div class="strongs-label">KJV Usage</div><div class="strongs-def">'+d.kjv_usage+'</div>'
    +'</div>';
  document.getElementById('results').style.display = '';
}

// ── MAP ─────────────────────────────────────────────────────────────────────

async function initMap() {
  if (map) {
    setTimeout(() => map.invalidateSize(), 100);
    return;
  }
  map = L.map('map').setView([32.0, 35.3], 7);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&#169; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18
  }).addTo(map);

  const resp = await fetch('/api/places');
  const data = await resp.json();
  allPlaces = {};
  for (const p of data.places) {
    allPlaces[p.name] = p;
    const marker = L.circleMarker([p.lat, p.lon], {
      radius: 4,
      color: '#b8962e',
      fillColor: '#b8962e',
      fillOpacity: 0.25,
      weight: 1
    }).bindPopup('<strong>'+p.name+'</strong>'+(p.notes ? '<br><span style="font-size:0.85rem;color:#aaa">'+p.notes+'</span>' : ''));
    marker.addTo(map);
    allMarkers[p.name] = marker;
  }
}

async function mapPassage(ref) {
  if (!ref) ref = document.getElementById('query').value.trim();
  if (!ref) return;
  currentRef = ref;
  setTab('maps');
  document.getElementById('map-title').textContent = 'Places in ' + ref;

  for (const m of passageMarkers) map.removeLayer(m);
  passageMarkers = [];
  document.getElementById('place-chips').innerHTML = '';

  const resp = await fetch('/api/places?ref='+encodeURIComponent(ref));
  const data = await resp.json();

  if (data.places.length === 0) {
    document.getElementById('place-chips').innerHTML = '<span class="muted">No named biblical places detected in this passage.</span>';
    return;
  }

  document.getElementById('place-count') && (document.getElementById('place-count').textContent = data.places.length + ' places found');

  const bounds = [];
  const chips = document.getElementById('place-chips');
  chips.innerHTML = '<span class="place-count">'+data.places.length+' places found in this passage:</span>';

  for (const p of data.places) {
    const marker = L.marker([p.lat, p.lon], {
      icon: L.divIcon({
        className: '',
        html: '<div style="background:#b8962e;color:#111;font-size:0.7rem;font-weight:bold;padding:2px 5px;border-radius:3px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,0.5)">'+p.name+'</div>',
        iconAnchor: [0, 0]
      })
    }).bindPopup('<strong>'+p.name+'</strong>'+(p.notes ? '<br><span style="font-size:0.85rem;color:#aaa">'+p.notes+'</span>' : ''));
    marker.addTo(map);
    passageMarkers.push(marker);
    bounds.push([p.lat, p.lon]);

    const chip = document.createElement('span');
    chip.className = 'place-chip';
    chip.textContent = p.name;
    chip.onclick = () => {
      map.setView([p.lat, p.lon], 10);
      marker.openPopup();
      document.querySelectorAll('.place-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
    };
    chips.appendChild(chip);
  }

  if (bounds.length === 1) {
    map.setView(bounds[0], 9);
  } else if (bounds.length > 1) {
    map.fitBounds(bounds, {padding: [60, 60], maxZoom: 11});
  }
}

function searchPlace() {
  const q = document.getElementById('place-search').value.trim();
  if (!q) return;
  for (const [name, p] of Object.entries(allPlaces)) {
    if (name.toLowerCase().includes(q.toLowerCase())) {
      map.setView([p.lat, p.lon], 10);
      if (allMarkers[name]) allMarkers[name].openPopup();
      return;
    }
  }
  alert('Place not found: ' + q);
}

// ── NOTES ───────────────────────────────────────────────────────────────────

function noteSection(ref) {
  return '<div style="margin-top:2rem"><h3 style="color:var(--gold);font-size:0.9rem;letter-spacing:0.1em;margin-bottom:0.75rem">STUDY NOTES — '+ref+'</h3>'
    +'<textarea class="note-area" id="note-content" placeholder="Your notes, reflections, and observations on this passage..."></textarea>'
    +'<button class="save-btn" onclick="saveNote(\\''+ref+'\\')">Save Notes</button>'
    +'<span id="save-status" style="margin-left:1rem;color:var(--muted);font-size:0.85rem"></span></div>';
}

async function loadNote(ref) {
  try {
    const r = await fetch('/api/note/'+encodeURIComponent(ref));
    if (!r.ok) return;
    const d = await r.json();
    const el = document.getElementById('note-content');
    if (el) el.value = d.body || d.content || '';
  } catch(e) {}
}

async function saveNote(ref) {
  const body = document.getElementById('note-content').value;
  await fetch('/api/note/'+encodeURIComponent(ref), {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({body})
  });
  const s = document.getElementById('save-status');
  if (s) { s.textContent = 'Saved ✓'; setTimeout(() => s.textContent = '', 2000); }
}

// ── INIT ────────────────────────────────────────────────────────────────────

document.getElementById('query').addEventListener('keydown', e => {
  if (e.key === 'Enter') search();
});
document.getElementById('place-search').addEventListener('keydown', e => {
  if (e.key === 'Enter') searchPlace();
});

window.addEventListener('load', () => {
  document.getElementById('query').value = 'John 3:16';
  lookupVerse('John 3:16');
});
</script>
</body>
</html>"""

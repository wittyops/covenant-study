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

app = FastAPI(title="Christ Pillar — Bible Study", docs_url=None)

DATA      = Path("/app/data")      # Bible text DBs — baked into image, never volume-mounted
USERDATA  = Path("/app/userdata")  # User accounts, sessions, bookmarks — persisted on named volume
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

TRANSLATIONS = [
    # English public-domain
    'KJV', 'KJVA', 'KJVPCE', 'AKJV', 'ASV', 'YLT', 'Darby', 'Geneva1599',
    'Webster', 'BBE', 'BSB', 'Jubilee2000', 'ACV', 'DRC', 'CPDV',
    'Tyndale', 'Wycliffe', 'OEB', 'LITV', 'MKJV', 'RNKJV', 'UKJV',
    'RWebster', 'Rotherham', 'NHEB', 'LEB', 'Anderson', 'Noyes', 'Haweis', 'Twenty',
    # Scholarly originals
    'JPS', 'HebModern', 'Vulgate', 'VulgClementine', 'Peshitta', 'TR', 'Byz',
    # Other languages
    'FreSynodale', 'FreGeneve',
]

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
    """Return an open connection to /app/userdata/users.db (WAL mode, FK on)."""
    USERDATA.mkdir(parents=True, exist_ok=True)
    db_path = USERDATA / "users.db"
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
async def get_places(ref: Optional[str] = Query(default=None)):
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
    users_ok = (USERDATA / "users.db").exists()
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
    """Return KJV verse(s) with per-word Strong's numbers from word_strongs in kjv.db.

    Chapter ref ('John 3')  → {"reference", "verses": [{"num", "words"}, ...]}
    Verse ref ('John 3:16') → {"reference", "verses": [{"num": 16, "words": [...]}]}
    word_strongs lives in kjv.db; strongs definitions ATTACHed from strongs.db.
    """
    book_num, chapter, verse = parse_reference(ref)
    if not book_num:
        raise HTTPException(400, f"Could not parse reference: {ref}")

    kjv_path = DATA / "kjv.db"
    if not kjv_path.exists():
        raise HTTPException(503, "KJV database not loaded")

    strongs_path = DATA / "strongs.db"

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

        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='word_strongs'"
        ).fetchone()
        if not has_table:
            raise HTTPException(503, "word_strongs table not populated yet")

        def fetch_verse_words(v_num: int) -> list:
            rows = conn.execute(
                f"""
                SELECT ws.word_position, ws.phrase_text, ws.strong_number,
                       ws.extra_strongs, ws.morph,
                       {strongs_sel}
                FROM word_strongs ws
                {strongs_join}
                WHERE ws.book_id = ? AND ws.chapter = ? AND ws.verse = ?
                ORDER BY ws.word_position
                """,
                (book_num, chapter, v_num),
            ).fetchall()
            return [
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

        if verse is None:
            # Chapter-level: collect all tagged verses
            verse_nums = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT verse FROM word_strongs WHERE book_id=? AND chapter=? ORDER BY verse",
                    (book_num, chapter),
                ).fetchall()
            ]
            verses = []
            for v_num in verse_nums:
                words = fetch_verse_words(v_num)
                if words:
                    verses.append({"num": v_num, "words": words})
            return {"reference": ref, "verses": verses}
        else:
            words = fetch_verse_words(verse)
            if not words:
                raise HTTPException(404, f"No tagged data found for {ref}")
            return {"reference": ref, "verses": [{"num": verse, "words": words}]}
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
    request: Request = None,  # type: ignore[assignment]
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

INLINE_HTML = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>The Christ Pillar</title>
  <style>
/* ============================================================
   CUSTOM PROPERTIES
   ============================================================ */
:root {
  --gold: #b8962e;
  --gold-light: #c9a84c;
  --dark: #1a1a1a;
  --bg: #0f0f0f;
  --card: #1e1e1e;
  --card2: #252525;
  --text: #e8e4da;
  --text-dim: #b0aa9e;
  --muted: #888;
  --accent: #c9a84c;
  --border: #333;
  --verse-num: #b8962e;
  --highlight: rgba(185,150,46,0.15);
  --sheet-bg: #171717;

  /* Layout dimensions */
  --topbar-h: 52px;
  --bottomnav-h: 56px;
  --sidebar-w: 260px;
  --sidebar-desktop-w: 200px;
  --right-panel-w: 300px;
  --drawer-max-w: min(80vw, 320px);

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.5);
  --shadow-lg: 0 8px 40px rgba(0,0,0,0.7);
  --shadow-panel: 0 -4px 24px rgba(0,0,0,0.5);
  --shadow-dropdown: 0 8px 32px rgba(0,0,0,0.65);

  /* Transitions */
  --t-sheet: cubic-bezier(0.32,0.72,0,1) 300ms;
  --t-drawer: ease-out 200ms;
  --t-fast: ease-out 150ms;
  --t-micro: ease-out 100ms;

  /* Z-index scale */
  --z-sidebar: 300;
  --z-backdrop: 299;
  --z-bottom-sheet: 400;
  --z-drawer: 500;
  --z-dropdown: 600;
  --z-search-overlay: 700;
  --z-toast: 800;
  --z-login: 1000;
}

/* ============================================================
   RESET & BASE
   ============================================================ */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  font-size: 16px;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
  height: 100%;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  height: 100%;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

button {
  font-family: inherit;
  cursor: pointer;
  background: none;
  border: none;
  color: inherit;
}

input, select, textarea {
  font-family: inherit;
  font-size: 16px; /* prevents iOS zoom */
  background: none;
  border: none;
  color: inherit;
  outline: none;
}

a {
  color: inherit;
  text-decoration: none;
}

ul, ol {
  list-style: none;
}

img, svg {
  display: block;
  max-width: 100%;
}

/* Focus visible */
:focus-visible {
  outline: 2px solid var(--gold-light);
  outline-offset: 2px;
  border-radius: 3px;
}

/* Scroll containers */
.scroll-y {
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

.scroll-x {
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

/* ============================================================
   LOGIN SCREEN
   ============================================================ */
#login-screen {
  position: fixed;
  inset: 0;
  z-index: var(--z-login);
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

#login-screen.hidden {
  display: none;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 40px 36px 36px;
  box-shadow: var(--shadow-lg);
}

.login-logo {
  text-align: center;
  margin-bottom: 28px;
}

.login-logo .cross-mark {
  display: inline-block;
  font-size: 28px;
  color: var(--gold);
  letter-spacing: 0.02em;
}

.login-logo h1 {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 20px;
  font-weight: 400;
  color: var(--text);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-top: 8px;
}

.login-logo .tagline {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.15em;
  text-transform: uppercase;
  margin-top: 4px;
}

#login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.form-field label {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.form-field input {
  background: var(--dark);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 10px 14px;
  font-size: 16px;
  color: var(--text);
  transition: border-color var(--t-fast);
  min-height: 44px;
}

.form-field input:focus {
  border-color: var(--gold);
}

.form-field input::placeholder {
  color: var(--muted);
  opacity: 0.7;
}

.form-error {
  font-size: 12px;
  color: #e05555;
  min-height: 16px;
}

.btn-primary {
  background: var(--gold);
  color: #0f0f0f;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 12px 20px;
  border-radius: 5px;
  min-height: 44px;
  transition: background var(--t-fast), opacity var(--t-fast);
  cursor: pointer;
  border: none;
}

.btn-primary:hover {
  background: var(--gold-light);
}

.btn-primary:active {
  opacity: 0.85;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.login-toggle {
  text-align: center;
  margin-top: 8px;
}

.login-toggle button {
  font-size: 13px;
  color: var(--gold-light);
  cursor: pointer;
  background: none;
  border: none;
  padding: 4px 0;
  min-height: 44px;
}

.login-toggle button:hover {
  color: var(--text);
}

.login-divider {
  text-align: center;
  position: relative;
  margin: 4px 0;
}

.login-divider::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--border);
}

.login-divider span {
  position: relative;
  background: var(--card);
  padding: 0 10px;
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.1em;
}

/* Create account panel (toggled) */
#create-account-form {
  display: none;
  flex-direction: column;
  gap: 14px;
}

#create-account-form.active {
  display: flex;
}

/* ============================================================
   APP SHELL
   ============================================================ */
#app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

#app-shell.hidden {
  display: none;
}

/* ============================================================
   TOP BAR
   ============================================================ */
#top-bar {
  height: var(--topbar-h);
  background: var(--card);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  flex-shrink: 0;
  position: relative;
  z-index: 10;
}

.app-title {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 15px;
  font-weight: 400;
  color: var(--gold-light);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  white-space: nowrap;
  flex: 1;
}

#hamburger-btn {
  display: none;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--text-dim);
  flex-shrink: 0;
}

#hamburger-btn:hover {
  color: var(--text);
  background: var(--card2);
}

.hamburger-icon {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hamburger-icon span {
  display: block;
  width: 18px;
  height: 2px;
  background: currentColor;
  border-radius: 1px;
  transition: transform var(--t-fast), opacity var(--t-fast);
}

#translation-select {
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text-dim);
  cursor: pointer;
  min-height: 36px;
  appearance: none;
  -webkit-appearance: none;
  padding-right: 24px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23888' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  transition: border-color var(--t-fast);
}

#translation-select:focus {
  border-color: var(--gold);
  color: var(--text);
}

#translation-select option {
  background: var(--card2);
  color: var(--text);
}

#search-toggle-btn {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--text-dim);
  flex-shrink: 0;
}

#search-toggle-btn:hover {
  color: var(--text);
  background: var(--card2);
}

#search-input {
  display: none;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 7px 14px;
  font-size: 14px;
  color: var(--text);
  width: 220px;
  min-height: 36px;
  transition: border-color var(--t-fast), width var(--t-fast);
}

#search-input:focus {
  border-color: var(--gold);
}

#search-input::placeholder {
  color: var(--muted);
}

#parallel-toggle-btn {
  height: 44px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 5px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--text-dim);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border: 1px solid transparent;
  transition: border-color var(--t-fast), color var(--t-fast);
  flex-shrink: 0;
}

#parallel-toggle-btn:hover {
  color: var(--text);
  border-color: var(--border);
}

#parallel-toggle-btn.active {
  color: var(--gold-light);
  border-color: rgba(185,150,46,0.3);
}

/* User chip */
#user-chip {
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px 5px 5px;
  border-radius: 5px;
  cursor: pointer;
  min-height: 36px;
  transition: background var(--t-fast);
  flex-shrink: 0;
}

#user-chip:hover {
  background: var(--card2);
}

.user-initials {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(185,150,46,0.2);
  border: 1px solid rgba(185,150,46,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--gold-light);
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

.user-display-name {
  font-size: 13px;
  color: var(--text-dim);
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-caret {
  color: var(--muted);
  font-size: 9px;
}

.user-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 200px;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 7px;
  box-shadow: var(--shadow-dropdown);
  z-index: var(--z-dropdown);
  display: none;
  overflow: hidden;
  padding: 4px 0;
}

.user-dropdown.open {
  display: block;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  font-size: 13px;
  color: var(--text-dim);
  cursor: pointer;
  transition: background var(--t-micro), color var(--t-micro);
  min-height: 44px;
}

.dropdown-item:hover {
  background: var(--dark);
  color: var(--text);
}

.dropdown-item.danger {
  color: #e05555;
}

.dropdown-item.danger:hover {
  background: rgba(224,85,85,0.08);
  color: #e57070;
}

.dropdown-item .item-icon {
  width: 16px;
  text-align: center;
  flex-shrink: 0;
  color: var(--muted);
}

.dropdown-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}

/* ============================================================
   MAIN LAYOUT
   ============================================================ */
#main-layout {
  flex: 1;
  overflow: hidden;
  display: flex;
  position: relative;
}

/* ============================================================
   SIDEBAR
   ============================================================ */
#sidebar {
  width: var(--sidebar-desktop-w);
  background: var(--card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
  transition: transform var(--t-drawer);
}

.sidebar-search {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.sidebar-search-inner {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--dark);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 0 10px;
  height: 34px;
  transition: border-color var(--t-fast);
}

.sidebar-search-inner:focus-within {
  border-color: rgba(185,150,46,0.4);
}

.sidebar-search-inner svg {
  color: var(--muted);
  flex-shrink: 0;
}

.sidebar-search-inner input {
  flex: 1;
  font-size: 13px;
  color: var(--text);
  background: none;
  border: none;
  outline: none;
  min-width: 0;
}

.sidebar-search-inner input::placeholder {
  color: var(--muted);
  opacity: 0.7;
}

.book-nav {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding-bottom: 16px;
}

.nav-section {
  padding-top: 6px;
}

.nav-section-label {
  padding: 10px 14px 5px;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.15em;
  text-transform: uppercase;
  font-weight: 600;
  position: sticky;
  top: 0;
  background: var(--card);
  z-index: 1;
  border-bottom: 1px solid rgba(51,51,51,0.5);
}

.book-list {
  padding: 2px 0;
}

.book-item {
  border-bottom: 1px solid rgba(51,51,51,0.3);
}

.book-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: var(--text-dim);
  cursor: pointer;
  transition: background var(--t-micro), color var(--t-micro);
  min-height: 38px;
  text-align: left;
}

.book-btn:hover {
  background: var(--card2);
  color: var(--text);
}

.book-btn.active {
  color: var(--gold-light);
  background: var(--highlight);
}

.book-abbr {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  width: 30px;
  flex-shrink: 0;
  font-family: system-ui, sans-serif;
}

.book-btn.active .book-abbr {
  color: var(--gold);
}

.book-name {
  flex: 1;
}

.book-chevron {
  color: var(--muted);
  font-size: 11px;
  transition: transform var(--t-fast);
  flex-shrink: 0;
}

.book-item.expanded .book-chevron {
  transform: rotate(90deg);
}

.chapter-list {
  display: none;
  flex-wrap: wrap;
  gap: 3px;
  padding: 4px 12px 8px 12px;
  background: rgba(0,0,0,0.15);
}

.book-item.expanded .chapter-list {
  display: flex;
}

.chapter-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 26px;
  padding: 0 4px;
  font-size: 12px;
  color: var(--text-dim);
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: background var(--t-micro), color var(--t-micro), border-color var(--t-micro);
  font-variant-numeric: tabular-nums;
}

.chapter-chip:hover {
  background: var(--dark);
  color: var(--text);
  border-color: rgba(185,150,46,0.3);
}

.chapter-chip.active {
  background: var(--highlight);
  color: var(--gold-light);
  border-color: rgba(185,150,46,0.4);
}

/* ============================================================
   READER AREA
   ============================================================ */
#reader-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

#chapter-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg);
}

.chapter-nav-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--text-dim);
  border: 1px solid var(--border);
  flex-shrink: 0;
  transition: color var(--t-fast), border-color var(--t-fast), background var(--t-fast);
}

.chapter-nav-btn:hover {
  color: var(--text);
  border-color: rgba(185,150,46,0.3);
  background: var(--card2);
}

.chapter-title-group {
  flex: 1;
  text-align: center;
}

.chapter-book-name {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 19px;
  font-weight: 400;
  color: var(--text);
  letter-spacing: 0.03em;
}

.chapter-number {
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-top: 1px;
}

.chapter-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.chapter-verse-count {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.05em;
}

.chapter-bookmark-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--muted);
  transition: color var(--t-fast);
}

.chapter-bookmark-btn:hover {
  color: var(--gold-light);
}

.chapter-bookmark-btn.bookmarked {
  color: var(--gold);
}

#chapter-content {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding: 20px 0 40px;
}

.chapter-intro {
  text-align: center;
  padding: 0 24px 20px;
  border-bottom: 1px solid rgba(51,51,51,0.4);
  margin-bottom: 16px;
}

.chapter-intro-ref {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.15em;
  text-transform: uppercase;
}

/* Verse rows */
.verse-row {
  display: flex;
  gap: 14px;
  padding: 4px 24px 4px 20px;
  border-left: 3px solid transparent;
  transition: background var(--t-micro), border-color var(--t-micro);
  cursor: default;
}

.verse-row:hover {
  background: var(--highlight);
  border-left-color: rgba(185,150,46,0.4);
}

.verse-row.selected {
  background: var(--highlight);
  border-left-color: var(--gold);
}

.verse-row.highlighted {
  background: rgba(185,150,46,0.1);
  border-left-color: rgba(185,150,46,0.25);
}

.verse-num {
  font-size: 11px;
  color: var(--verse-num);
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  line-height: 1.8;
  padding-top: 3px;
  min-width: 24px;
  text-align: right;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  user-select: none;
}

.verse-text {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 18px;
  line-height: 1.85;
  color: var(--text);
  flex: 1;
}

.verse-text .word {
  display: inline;
  border-radius: 2px;
  transition: background var(--t-micro), color var(--t-micro);
}

.verse-text .word[data-strongs] {
  cursor: pointer;
}

.verse-text .word[data-strongs]:hover {
  background: rgba(185,150,46,0.2);
  color: var(--gold-light);
}

.verse-text .word[data-strongs].active {
  background: rgba(185,150,46,0.25);
  color: var(--gold-light);
}

/* Red letter (words of Christ) */
.red-letter {
  color: #c97060;
}

.verse-actions {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding-top: 6px;
  opacity: 0;
  transition: opacity var(--t-micro);
}

.verse-row:hover .verse-actions {
  opacity: 1;
}

.verse-action-btn {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--muted);
  transition: color var(--t-micro), background var(--t-micro);
}

.verse-action-btn:hover {
  color: var(--gold-light);
  background: var(--card2);
}

/* Parallel Bible view */
.verse-row.parallel {
  gap: 20px;
}

.parallel-col {
  flex: 1;
  min-width: 0;
}

.parallel-col-label {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 4px;
}

/* Poetry / Psalms indent */
.verse-text.poetry {
  padding-left: 20px;
  text-indent: -20px;
}

.verse-text.poetry-indent {
  padding-left: 36px;
}

/* Chapter heading within content */
.content-heading {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-dim);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 18px 24px 6px 44px;
}

/* ============================================================
   RIGHT / CONTEXT PANEL (desktop)
   ============================================================ */
#context-panel {
  width: var(--right-panel-w);
  background: var(--card);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

/* Panel tabs (shared by context-panel and bottom-sheet) */
.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  flex-shrink: 0;
}

.panel-tabs::-webkit-scrollbar {
  display: none;
}

.tab-btn {
  padding: 0 12px;
  height: 40px;
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
  transition: color var(--t-fast), border-color var(--t-fast);
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 5px;
}

.tab-btn:hover {
  color: var(--text-dim);
}

.tab-btn.active {
  color: var(--gold-light);
  border-bottom-color: var(--gold);
}

/* Tab panes */
.tab-pane {
  display: none;
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding: 16px;
}

.tab-pane.active {
  display: flex;
  flex-direction: column;
}

/* Cross references tab */
#tab-crossrefs .crossref-item {
  display: flex;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(51,51,51,0.5);
  cursor: pointer;
  transition: background var(--t-micro);
}

#tab-crossrefs .crossref-item:hover .crossref-ref {
  color: var(--gold-light);
}

.crossref-ref {
  font-size: 12px;
  color: var(--gold);
  white-space: nowrap;
  letter-spacing: 0.04em;
  min-width: 80px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.crossref-preview {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 13px;
  color: var(--text-dim);
  line-height: 1.55;
}

/* Strong's tab */
#tab-strongs .strongs-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.strongs-number {
  font-size: 20px;
  font-family: Georgia, serif;
  color: var(--gold-light);
}

.strongs-transliteration {
  font-size: 15px;
  color: var(--text-dim);
  font-style: italic;
}

.strongs-original {
  font-size: 22px;
  color: var(--text);
  letter-spacing: 0.04em;
}

.strongs-section-label {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 5px;
  margin-top: 12px;
}

.strongs-definition {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  color: var(--text);
  line-height: 1.65;
}

/* Interlinear tab */
#tab-interlinear .interlinear-word {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin: 4px 6px 8px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  transition: background var(--t-micro);
}

#tab-interlinear .interlinear-word:hover {
  background: var(--highlight);
}

.interlinear-original {
  font-size: 17px;
  color: var(--text);
  line-height: 1.2;
}

.interlinear-transliteration {
  font-size: 10px;
  color: var(--muted);
  font-style: italic;
}

.interlinear-gloss {
  font-size: 11px;
  color: var(--gold-light);
  letter-spacing: 0.04em;
}

.interlinear-strongs {
  font-size: 10px;
  color: var(--muted);
}

/* Commentary tab */
#tab-commentary .commentary-source {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.commentary-source-select {
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--text-dim);
  cursor: pointer;
}

.commentary-body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  color: var(--text-dim);
  line-height: 1.7;
}

/* Notes tab */
#tab-notes .notes-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.notes-toolbar-btn {
  height: 32px;
  padding: 0 10px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-dim);
  border: 1px solid var(--border);
  transition: border-color var(--t-fast), color var(--t-fast);
}

.notes-toolbar-btn:hover {
  border-color: rgba(185,150,46,0.3);
  color: var(--text);
}

.notes-textarea {
  flex: 1;
  background: var(--dark);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 10px 12px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  color: var(--text);
  line-height: 1.65;
  resize: none;
  min-height: 140px;
  transition: border-color var(--t-fast);
  width: 100%;
}

.notes-textarea:focus {
  border-color: rgba(185,150,46,0.4);
}

.notes-textarea::placeholder {
  color: var(--muted);
  opacity: 0.6;
}

.notes-save-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.notes-save-btn {
  height: 32px;
  padding: 0 16px;
  border-radius: 4px;
  background: var(--gold);
  color: #0f0f0f;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  transition: background var(--t-fast);
}

.notes-save-btn:hover {
  background: var(--gold-light);
}

.notes-list {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.note-item {
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
}

.note-item-ref {
  font-size: 11px;
  color: var(--gold);
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}

.note-item-body {
  font-family: Georgia, serif;
  font-size: 13px;
  color: var(--text-dim);
  line-height: 1.55;
}

.note-item-date {
  font-size: 11px;
  color: var(--muted);
  margin-top: 6px;
}

/* Maps tab */
#tab-maps .map-placeholder {
  flex: 1;
  background: var(--dark);
  border: 1px solid var(--border);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 200px;
  color: var(--muted);
}

.map-location-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.map-location-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--card2);
  border-radius: 5px;
  cursor: pointer;
  transition: background var(--t-micro);
}

.map-location-item:hover {
  background: var(--dark);
}

.map-location-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--gold);
  flex-shrink: 0;
}

.map-location-name {
  font-size: 13px;
  color: var(--text-dim);
}

/* Empty state */
.panel-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--muted);
  padding: 24px;
  text-align: center;
}

.panel-empty-icon {
  font-size: 28px;
  opacity: 0.4;
}

.panel-empty-text {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.55;
}

/* ============================================================
   BOTTOM NAV (mobile only)
   ============================================================ */
#bottom-nav {
  display: none;
  height: var(--bottomnav-h);
  background: var(--card);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.bottom-nav-inner {
  display: flex;
  height: 100%;
}

.bottom-nav-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  cursor: pointer;
  transition: color var(--t-fast);
  min-height: 56px;
}

.bottom-nav-btn:hover,
.bottom-nav-btn.active {
  color: var(--gold-light);
}

.bottom-nav-btn svg {
  width: 20px;
  height: 20px;
}

/* ============================================================
   BOTTOM SHEET (mobile context panel)
   ============================================================ */
#bottom-sheet {
  display: none;
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 65vh;
  background: var(--sheet-bg);
  border-top: 1px solid var(--border);
  border-radius: 16px 16px 0 0;
  z-index: var(--z-bottom-sheet);
  flex-direction: column;
  transform: translateY(100%);
  transition: transform var(--t-sheet);
  will-change: transform;
  box-shadow: var(--shadow-panel);
}

#bottom-sheet.open {
  transform: translateY(0);
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  margin: 10px auto 6px;
  flex-shrink: 0;
  cursor: grab;
}

.sheet-handle:active {
  cursor: grabbing;
}

.sheet-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ============================================================
   BACKDROP OVERLAY
   ============================================================ */
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.55);
  z-index: var(--z-backdrop);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--t-drawer);
}

.backdrop.visible {
  opacity: 1;
  pointer-events: auto;
}

/* ============================================================
   SLIDE-IN DRAWERS (sessions, bookmarks, history)
   ============================================================ */
.slide-drawer {
  position: fixed;
  top: 0;
  bottom: 0;
  width: var(--drawer-max-w);
  background: var(--card);
  border-right: 1px solid var(--border);
  z-index: var(--z-drawer);
  display: flex;
  flex-direction: column;
  transform: translateX(-100%);
  transition: transform var(--t-drawer);
  will-change: transform;
  overflow: hidden;
}

.slide-drawer.from-right {
  left: auto;
  right: 0;
  border-right: none;
  border-left: 1px solid var(--border);
  transform: translateX(100%);
}

.slide-drawer.open {
  transform: translateX(0);
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  height: var(--topbar-h);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.drawer-title {
  flex: 1;
  font-size: 13px;
  color: var(--text-dim);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
}

.drawer-close-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--muted);
  transition: color var(--t-fast), background var(--t-fast);
  cursor: pointer;
}

.drawer-close-btn:hover {
  color: var(--text);
  background: var(--card2);
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding: 14px;
}

/* Sessions panel */
#sessions-panel .session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.session-item {
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color var(--t-fast);
}

.session-item:hover {
  border-color: rgba(185,150,46,0.25);
}

.session-item-name {
  font-size: 14px;
  color: var(--text);
  font-weight: 500;
}

.session-item-meta {
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-item-meta .meta-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--muted);
}

.session-item-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.session-btn-resume {
  flex: 1;
  height: 32px;
  background: var(--gold);
  color: #0f0f0f;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-radius: 4px;
  transition: background var(--t-fast);
}

.session-btn-resume:hover {
  background: var(--gold-light);
}

.session-btn-delete {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--muted);
  transition: color var(--t-fast), border-color var(--t-fast);
}

.session-btn-delete:hover {
  color: #e05555;
  border-color: rgba(224,85,85,0.35);
}

.drawer-section-label {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

#new-session-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

#new-session-form input {
  background: var(--dark);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 9px 12px;
  font-size: 14px;
  color: var(--text);
  transition: border-color var(--t-fast);
  min-height: 44px;
  width: 100%;
}

#new-session-form input:focus {
  border-color: var(--gold);
}

#new-session-form input::placeholder {
  color: var(--muted);
  opacity: 0.6;
}

.session-save-btn {
  height: 40px;
  background: var(--gold);
  color: #0f0f0f;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-radius: 5px;
  transition: background var(--t-fast);
}

.session-save-btn:hover {
  background: var(--gold-light);
}

/* Bookmarks panel */
#bookmarks-panel .bookmark-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bookmark-item {
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: border-color var(--t-fast), background var(--t-fast);
}

.bookmark-item:hover {
  border-color: rgba(185,150,46,0.25);
  background: var(--dark);
}

.bookmark-color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.bookmark-ref {
  font-size: 13px;
  color: var(--gold-light);
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.bookmark-label {
  flex: 1;
  font-size: 13px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bookmark-navigate-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--muted);
  flex-shrink: 0;
  transition: color var(--t-fast);
}

.bookmark-navigate-btn:hover {
  color: var(--gold-light);
}

/* History panel */
#history-panel .history-list {
  display: flex;
  flex-direction: column;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid rgba(51,51,51,0.4);
  cursor: pointer;
  transition: background var(--t-micro);
}

.history-item:hover .history-ref {
  color: var(--gold-light);
}

.history-ref {
  font-size: 14px;
  color: var(--text-dim);
  flex: 1;
  letter-spacing: 0.03em;
  transition: color var(--t-fast);
}

.history-time {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}

/* ============================================================
   TOAST CONTAINER
   ============================================================ */
#toast-container {
  position: fixed;
  top: calc(var(--topbar-h) + 12px);
  right: 16px;
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
  max-width: 300px;
}

.toast {
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: var(--shadow-md);
  display: flex;
  align-items: flex-start;
  gap: 10px;
  pointer-events: auto;
  opacity: 0;
  transform: translateX(12px);
  transition: opacity var(--t-fast), transform var(--t-fast);
}

.toast.visible {
  opacity: 1;
  transform: translateX(0);
}

.toast.leaving {
  opacity: 0;
  transform: translateX(12px);
}

.toast-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 1px;
}

.toast.success .toast-icon { color: #5aad6e; }
.toast.error .toast-icon { color: #e05555; }
.toast.info .toast-icon { color: var(--gold-light); }

.toast-message {
  font-size: 13px;
  color: var(--text-dim);
  line-height: 1.45;
  flex: 1;
}

.toast-close {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  border-radius: 3px;
  transition: color var(--t-micro);
  flex-shrink: 0;
}

.toast-close:hover {
  color: var(--text);
}

/* ============================================================
   SEARCH OVERLAY (mobile full-screen)
   ============================================================ */
#search-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg);
  z-index: var(--z-search-overlay);
  display: flex;
  flex-direction: column;
  transform: translateY(-100%);
  transition: transform var(--t-sheet);
  will-change: transform;
}

#search-overlay.open {
  transform: translateY(0);
}

.search-overlay-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  height: var(--topbar-h);
}

.search-overlay-back {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
  border-radius: 5px;
  flex-shrink: 0;
}

.search-overlay-back:hover {
  color: var(--text);
  background: var(--card2);
}

.search-overlay-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0 12px;
  height: 40px;
  transition: border-color var(--t-fast);
}

.search-overlay-input-wrap:focus-within {
  border-color: rgba(185,150,46,0.4);
}

.search-overlay-input-wrap input {
  flex: 1;
  font-size: 16px;
  color: var(--text);
  background: none;
  border: none;
  outline: none;
}

.search-overlay-input-wrap input::placeholder {
  color: var(--muted);
  opacity: 0.7;
}

.search-overlay-clear {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  border-radius: 3px;
  transition: color var(--t-micro);
}

.search-overlay-clear:hover {
  color: var(--text);
}

.search-overlay-body {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

.search-filters {
  display: flex;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(51,51,51,0.4);
  overflow-x: auto;
  scrollbar-width: none;
}

.search-filters::-webkit-scrollbar {
  display: none;
}

.search-filter-chip {
  height: 30px;
  padding: 0 12px;
  border-radius: 15px;
  font-size: 12px;
  color: var(--text-dim);
  border: 1px solid var(--border);
  white-space: nowrap;
  cursor: pointer;
  transition: border-color var(--t-fast), color var(--t-fast), background var(--t-fast);
  flex-shrink: 0;
}

.search-filter-chip.active {
  border-color: rgba(185,150,46,0.4);
  color: var(--gold-light);
  background: var(--highlight);
}

.search-result-item {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(51,51,51,0.3);
  cursor: pointer;
  transition: background var(--t-micro);
}

.search-result-item:hover {
  background: var(--card);
}

.search-result-ref {
  font-size: 12px;
  color: var(--gold);
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}

.search-result-text {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  color: var(--text-dim);
  line-height: 1.55;
}

.search-result-text mark {
  background: var(--highlight);
  color: var(--gold-light);
  border-radius: 2px;
  padding: 0 1px;
}

.search-empty {
  padding: 48px 24px;
  text-align: center;
}

.search-empty-label {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.55;
}

/* ============================================================
   RESPONSIVE — MOBILE (< 768px)
   ============================================================ */
@media (max-width: 767px) {
  #hamburger-btn {
    display: flex;
  }

  #search-input {
    display: none !important;
  }

  #parallel-toggle-btn .btn-label {
    display: none;
  }

  .user-display-name {
    display: none;
  }

  #sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: var(--drawer-max-w);
    z-index: var(--z-sidebar);
    transform: translateX(-100%);
  }

  #sidebar.open {
    transform: translateX(0);
  }

  #context-panel {
    display: none;
  }

  #bottom-nav {
    display: flex;
    flex-shrink: 0;
  }

  #bottom-sheet {
    display: flex;
  }

  #main-layout {
    flex-direction: column;
  }

  #reader-area {
    height: 100%;
  }

  #chapter-header {
    padding: 10px 16px;
  }

  #chapter-content {
    padding-bottom: calc(var(--bottomnav-h) + 24px);
  }

  .verse-row {
    padding: 4px 16px 4px 14px;
  }

  .verse-text {
    font-size: 18px;
  }

  .app-title {
    font-size: 14px;
  }
}

/* ============================================================
   RESPONSIVE — TABLET (768px – 1199px)
   ============================================================ */
@media (min-width: 768px) and (max-width: 1199px) {
  #hamburger-btn {
    display: flex;
  }

  #sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: var(--sidebar-w);
    z-index: var(--z-sidebar);
    transform: translateX(-100%);
  }

  #sidebar.open {
    transform: translateX(0);
  }

  #context-panel {
    display: none;
  }

  #bottom-sheet {
    display: flex;
  }

  #search-input {
    display: block;
  }

  #search-toggle-btn {
    display: none;
  }

  .verse-text {
    font-size: 17px;
  }

  #chapter-content {
    padding-bottom: 48px;
  }
}

/* ============================================================
   RESPONSIVE — DESKTOP (≥ 1200px)
   ============================================================ */
@media (min-width: 1200px) {
  #main-layout {
    display: grid;
    grid-template-columns: var(--sidebar-desktop-w) 1fr var(--right-panel-w);
    grid-template-rows: 1fr;
  }

  #sidebar {
    display: flex;
    position: static;
    width: auto;
    transform: none;
  }

  #sidebar.hidden-desktop {
    display: none;
  }

  #reader-area {
    grid-column: 2;
  }

  #context-panel {
    display: flex;
    grid-column: 3;
  }

  #bottom-sheet {
    display: none !important;
  }

  #bottom-nav {
    display: none;
  }

  #hamburger-btn {
    display: none;
  }

  #search-input {
    display: block;
  }

  #search-toggle-btn {
    display: none;
  }

  .verse-text {
    font-size: 17px;
  }

  #chapter-content {
    padding: 28px 0 56px;
  }

  .verse-row {
    padding: 5px 28px 5px 22px;
    max-width: 760px;
  }
}

/* ============================================================
   REDUCED MOTION
   ============================================================ */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }

  #bottom-sheet,
  #search-overlay,
  .slide-drawer,
  #sidebar {
    transition: none !important;
  }
}

/* ============================================================
   UTILITY CLASSES
   ============================================================ */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0,0,0,0);
  white-space: nowrap;
  border-width: 0;
}

.flex { display: flex; }
.flex-col { flex-direction: column; }
.items-center { align-items: center; }
.gap-8 { gap: 8px; }
.w-full { width: 100%; }
.hidden { display: none !important; }
.muted { color: var(--muted); }
.gold { color: var(--gold-light); }

/* ============================================================
   SCROLLBAR STYLING
   ============================================================ */
::-webkit-scrollbar {
  width: 4px;
  height: 4px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}

::-webkit-scrollbar-thumb:hover {
  background: #444;
}

* {
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
  </style>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV/XN/WLs=" crossorigin=""></script>
</head>
<body>
<!-- ============================================================
     LOGIN SCREEN
     ============================================================ -->
<div id="js-error-banner" style="display:none;position:fixed;top:0;left:0;right:0;background:#c0392b;color:#fff;padding:10px 16px;font-size:13px;z-index:9999;font-family:monospace;word-break:break-all;"></div>
<div id="login-screen">
  <div class="login-card">
    <div class="login-logo">
      <div class="cross-mark">✝</div>
      <h1>The Christ Pillar</h1>
      <div class="tagline">Scripture Study Platform</div>
    </div>

    <form id="login-form" autocomplete="on" novalidate>
      <div class="form-field">
        <label for="login-username">Username</label>
        <input type="text" id="login-username" name="username" placeholder="Enter your username" autocomplete="username" required>
      </div>
      <div class="form-field">
        <label for="login-password">Password</label>
        <input type="password" id="login-password" name="password" placeholder="Enter your password" autocomplete="current-password" required>
      </div>
      <div class="form-error" id="login-error" role="alert" aria-live="polite"></div>
      <button type="submit" class="btn-primary" id="login-submit-btn">Sign In</button>
      <div class="login-toggle">
        <button type="button" id="show-create-account-btn">Create an account</button>
      </div>
    </form>

    <form id="create-account-form" autocomplete="on" novalidate>
      <div class="login-divider"><span>New Account</span></div>
      <div class="form-field">
        <label for="reg-display-name">Display Name</label>
        <input type="text" id="reg-display-name" name="displayName" placeholder="Your name" autocomplete="name" required>
      </div>
      <div class="form-field">
        <label for="reg-username">Username</label>
        <input type="text" id="reg-username" name="username" placeholder="Choose a username" autocomplete="username" required>
      </div>
      <div class="form-field">
        <label for="reg-password">Password</label>
        <input type="password" id="reg-password" name="password" placeholder="Choose a password" autocomplete="new-password" required>
      </div>
      <div class="form-field">
        <label for="reg-password-confirm">Confirm Password</label>
        <input type="password" id="reg-password-confirm" name="passwordConfirm" placeholder="Repeat password" autocomplete="new-password" required>
      </div>
      <div class="form-error" id="register-error" role="alert" aria-live="polite"></div>
      <button type="submit" class="btn-primary" id="register-submit-btn">Create Account</button>
      <div class="login-toggle">
        <button type="button" id="show-login-btn">Back to sign in</button>
      </div>
    </form>
  </div>
</div>

<!-- ============================================================
     APP SHELL
     ============================================================ -->
<div id="app-shell" class="hidden">

  <!-- TOP BAR -->
  <header id="top-bar" role="banner">
    <button id="hamburger-btn" aria-label="Open book navigation" aria-expanded="false" aria-controls="sidebar">
      <span class="sr-only">Menu</span>
      <span class="hamburger-icon" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
      </span>
    </button>

    <span class="app-title" aria-hidden="true">✝ THE CHRIST PILLAR</span>

    <label for="translation-select" class="sr-only">Bible Translation</label>
    <select id="translation-select" aria-label="Select Bible translation">
      <option value="KJV">KJV</option>
      <option value="ESV" selected>ESV</option>
      <option value="NIV">NIV</option>
      <option value="NASB">NASB</option>
      <option value="NLT">NLT</option>
      <option value="NKJV">NKJV</option>
      <option value="AMP">AMP</option>
      <option value="CSB">CSB</option>
      <option value="MSG">MSG</option>
      <option value="RSV">RSV</option>
    </select>

    <button id="search-toggle-btn" aria-label="Open search" aria-controls="search-overlay">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
        <circle cx="7.5" cy="7.5" r="5.5" stroke="currentColor" stroke-width="1.5"/>
        <path d="M11.5 11.5L16 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>

    <input type="search" id="search-input" placeholder="Search scriptures…" aria-label="Search scriptures" autocomplete="off" spellcheck="false">

    <button id="parallel-toggle-btn" aria-pressed="false" aria-label="Toggle parallel Bible view">
      <svg width="15" height="14" viewBox="0 0 15 14" fill="none" aria-hidden="true">
        <rect x="0.75" y="1" width="5.5" height="12" rx="1" stroke="currentColor" stroke-width="1.3"/>
        <rect x="8.75" y="1" width="5.5" height="12" rx="1" stroke="currentColor" stroke-width="1.3"/>
      </svg>
      <span class="btn-label">Parallel</span>
    </button>

    <div id="user-chip" role="button" tabindex="0" aria-haspopup="true" aria-expanded="false" aria-label="User menu">
      <div class="user-initials" aria-hidden="true">JD</div>
      <span class="user-display-name">John Doe</span>
      <span class="user-caret" aria-hidden="true">▾</span>
      <nav class="user-dropdown" role="menu" aria-label="User options">
        <button class="dropdown-item" role="menuitem" data-action="sessions">
          <span class="item-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="1" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
              <path d="M4 13h6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              <path d="M7 10v3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
          </span>
          Study Sessions
        </button>
        <button class="dropdown-item" role="menuitem" data-action="bookmarks">
          <span class="item-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 1.5h10v11l-5-3-5 3V1.5z" stroke="currentColor" stroke-width="1.2"/>
            </svg>
          </span>
          Bookmarks
        </button>
        <button class="dropdown-item" role="menuitem" data-action="history">
          <span class="item-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.2"/>
              <path d="M7 4v3.5l2 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
          </span>
          History
        </button>
        <div class="dropdown-divider" role="separator"></div>
        <button class="dropdown-item" role="menuitem" data-action="manage-users" id="manage-users-item" style="display:none">
          <span class="item-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="5" cy="4.5" r="2.5" stroke="currentColor" stroke-width="1.2"/>
              <path d="M1 12c0-2.2 1.8-4 4-4s4 1.8 4 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              <path d="M11 6v4M9 8h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
          </span>
          Manage Users
        </button>
        <button class="dropdown-item danger" role="menuitem" data-action="signout">
          <span class="item-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5 2H2.5A1.5 1.5 0 001 3.5v7A1.5 1.5 0 002.5 12H5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              <path d="M9 4l3 3-3 3M12 7H5.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </span>
          Sign Out
        </button>
      </nav>
    </div>
  </header>

  <!-- MAIN LAYOUT -->
  <div id="main-layout">

    <!-- SIDEBAR -->
    <aside id="sidebar" aria-label="Book navigation">
      <div class="sidebar-search">
        <div class="sidebar-search-inner">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
            <circle cx="5.5" cy="5.5" r="4" stroke="currentColor" stroke-width="1.3"/>
            <path d="M8.5 8.5L12 12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
          <input type="search" placeholder="Find a book…" aria-label="Search books" autocomplete="off">
        </div>
      </div>

      <nav class="book-nav scroll-y" aria-label="Books of the Bible">
        <div class="nav-section">
          <div class="nav-section-label">Old Testament</div>
          <div class="book-list">
            <div class="book-item" data-book="genesis" data-chapters="50">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-genesis">
                <span class="book-abbr">GEN</span>
                <span class="book-name">Genesis</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-genesis" role="group" aria-label="Genesis chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span><span class="chapter-chip" data-chapter="37" tabindex="0">37</span><span class="chapter-chip" data-chapter="38" tabindex="0">38</span><span class="chapter-chip" data-chapter="39" tabindex="0">39</span><span class="chapter-chip" data-chapter="40" tabindex="0">40</span><span class="chapter-chip" data-chapter="41" tabindex="0">41</span><span class="chapter-chip" data-chapter="42" tabindex="0">42</span><span class="chapter-chip" data-chapter="43" tabindex="0">43</span><span class="chapter-chip" data-chapter="44" tabindex="0">44</span><span class="chapter-chip" data-chapter="45" tabindex="0">45</span><span class="chapter-chip" data-chapter="46" tabindex="0">46</span><span class="chapter-chip" data-chapter="47" tabindex="0">47</span><span class="chapter-chip" data-chapter="48" tabindex="0">48</span><span class="chapter-chip" data-chapter="49" tabindex="0">49</span><span class="chapter-chip" data-chapter="50" tabindex="0">50</span></div>
            </div>
            <div class="book-item" data-book="exodus" data-chapters="40">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-exodus">
                <span class="book-abbr">EXO</span>
                <span class="book-name">Exodus</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-exodus" role="group" aria-label="Exodus chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span><span class="chapter-chip" data-chapter="37" tabindex="0">37</span><span class="chapter-chip" data-chapter="38" tabindex="0">38</span><span class="chapter-chip" data-chapter="39" tabindex="0">39</span><span class="chapter-chip" data-chapter="40" tabindex="0">40</span></div>
            </div>
            <div class="book-item" data-book="leviticus" data-chapters="27">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-leviticus">
                <span class="book-abbr">LEV</span>
                <span class="book-name">Leviticus</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-leviticus" role="group" aria-label="Leviticus chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span></div>
            </div>
            <div class="book-item" data-book="numbers" data-chapters="36">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-numbers">
                <span class="book-abbr">NUM</span>
                <span class="book-name">Numbers</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-numbers" role="group" aria-label="Numbers chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span></div>
            </div>
            <div class="book-item" data-book="deuteronomy" data-chapters="34">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-deuteronomy">
                <span class="book-abbr">DEU</span>
                <span class="book-name">Deuteronomy</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-deuteronomy" role="group" aria-label="Deuteronomy chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span></div>
            </div>
            <div class="book-item" data-book="joshua" data-chapters="24">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-joshua">
                <span class="book-abbr">JOS</span>
                <span class="book-name">Joshua</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-joshua" role="group" aria-label="Joshua chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span></div>
            </div>
            <div class="book-item" data-book="judges" data-chapters="21">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-judges">
                <span class="book-abbr">JDG</span>
                <span class="book-name">Judges</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-judges" role="group" aria-label="Judges chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span></div>
            </div>
            <div class="book-item" data-book="ruth" data-chapters="4">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-ruth">
                <span class="book-abbr">RUT</span>
                <span class="book-name">Ruth</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-ruth" role="group" aria-label="Ruth chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span></div>
            </div>
            <div class="book-item" data-book="1_samuel" data-chapters="31">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_samuel">
                <span class="book-abbr">1SA</span>
                <span class="book-name">1 Samuel</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_samuel" role="group" aria-label="1 Samuel chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span></div>
            </div>
            <div class="book-item" data-book="2_samuel" data-chapters="24">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_samuel">
                <span class="book-abbr">2SA</span>
                <span class="book-name">2 Samuel</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_samuel" role="group" aria-label="2 Samuel chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span></div>
            </div>
            <div class="book-item" data-book="1_kings" data-chapters="22">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_kings">
                <span class="book-abbr">1KI</span>
                <span class="book-name">1 Kings</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_kings" role="group" aria-label="1 Kings chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span></div>
            </div>
            <div class="book-item" data-book="2_kings" data-chapters="25">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_kings">
                <span class="book-abbr">2KI</span>
                <span class="book-name">2 Kings</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_kings" role="group" aria-label="2 Kings chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span></div>
            </div>
            <div class="book-item" data-book="1_chronicles" data-chapters="29">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_chronicles">
                <span class="book-abbr">1CH</span>
                <span class="book-name">1 Chronicles</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_chronicles" role="group" aria-label="1 Chronicles chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span></div>
            </div>
            <div class="book-item" data-book="2_chronicles" data-chapters="36">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_chronicles">
                <span class="book-abbr">2CH</span>
                <span class="book-name">2 Chronicles</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_chronicles" role="group" aria-label="2 Chronicles chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span></div>
            </div>
            <div class="book-item" data-book="ezra" data-chapters="10">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-ezra">
                <span class="book-abbr">EZR</span>
                <span class="book-name">Ezra</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-ezra" role="group" aria-label="Ezra chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span></div>
            </div>
            <div class="book-item" data-book="nehemiah" data-chapters="13">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-nehemiah">
                <span class="book-abbr">NEH</span>
                <span class="book-name">Nehemiah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-nehemiah" role="group" aria-label="Nehemiah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span></div>
            </div>
            <div class="book-item" data-book="esther" data-chapters="10">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-esther">
                <span class="book-abbr">EST</span>
                <span class="book-name">Esther</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-esther" role="group" aria-label="Esther chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span></div>
            </div>
            <div class="book-item" data-book="job" data-chapters="42">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-job">
                <span class="book-abbr">JOB</span>
                <span class="book-name">Job</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-job" role="group" aria-label="Job chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span><span class="chapter-chip" data-chapter="37" tabindex="0">37</span><span class="chapter-chip" data-chapter="38" tabindex="0">38</span><span class="chapter-chip" data-chapter="39" tabindex="0">39</span><span class="chapter-chip" data-chapter="40" tabindex="0">40</span><span class="chapter-chip" data-chapter="41" tabindex="0">41</span><span class="chapter-chip" data-chapter="42" tabindex="0">42</span></div>
            </div>
            <div class="book-item" data-book="psalms" data-chapters="150">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-psalms">
                <span class="book-abbr">PSA</span>
                <span class="book-name">Psalms</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-psalms" role="group" aria-label="Psalms chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span><span class="chapter-chip" data-chapter="37" tabindex="0">37</span><span class="chapter-chip" data-chapter="38" tabindex="0">38</span><span class="chapter-chip" data-chapter="39" tabindex="0">39</span><span class="chapter-chip" data-chapter="40" tabindex="0">40</span><span class="chapter-chip" data-chapter="41" tabindex="0">41</span><span class="chapter-chip" data-chapter="42" tabindex="0">42</span><span class="chapter-chip" data-chapter="43" tabindex="0">43</span><span class="chapter-chip" data-chapter="44" tabindex="0">44</span><span class="chapter-chip" data-chapter="45" tabindex="0">45</span><span class="chapter-chip" data-chapter="46" tabindex="0">46</span><span class="chapter-chip" data-chapter="47" tabindex="0">47</span><span class="chapter-chip" data-chapter="48" tabindex="0">48</span><span class="chapter-chip" data-chapter="49" tabindex="0">49</span><span class="chapter-chip" data-chapter="50" tabindex="0">50</span><span class="chapter-chip" data-chapter="51" tabindex="0">51</span><span class="chapter-chip" data-chapter="52" tabindex="0">52</span><span class="chapter-chip" data-chapter="53" tabindex="0">53</span><span class="chapter-chip" data-chapter="54" tabindex="0">54</span><span class="chapter-chip" data-chapter="55" tabindex="0">55</span><span class="chapter-chip" data-chapter="56" tabindex="0">56</span><span class="chapter-chip" data-chapter="57" tabindex="0">57</span><span class="chapter-chip" data-chapter="58" tabindex="0">58</span><span class="chapter-chip" data-chapter="59" tabindex="0">59</span><span class="chapter-chip" data-chapter="60" tabindex="0">60</span><span class="chapter-chip" data-chapter="61" tabindex="0">61</span><span class="chapter-chip" data-chapter="62" tabindex="0">62</span><span class="chapter-chip" data-chapter="63" tabindex="0">63</span><span class="chapter-chip" data-chapter="64" tabindex="0">64</span><span class="chapter-chip" data-chapter="65" tabindex="0">65</span><span class="chapter-chip" data-chapter="66" tabindex="0">66</span><span class="chapter-chip" data-chapter="67" tabindex="0">67</span><span class="chapter-chip" data-chapter="68" tabindex="0">68</span><span class="chapter-chip" data-chapter="69" tabindex="0">69</span><span class="chapter-chip" data-chapter="70" tabindex="0">70</span><span class="chapter-chip" data-chapter="71" tabindex="0">71</span><span class="chapter-chip" data-chapter="72" tabindex="0">72</span><span class="chapter-chip" data-chapter="73" tabindex="0">73</span><span class="chapter-chip" data-chapter="74" tabindex="0">74</span><span class="chapter-chip" data-chapter="75" tabindex="0">75</span><span class="chapter-chip" data-chapter="76" tabindex="0">76</span><span class="chapter-chip" data-chapter="77" tabindex="0">77</span><span class="chapter-chip" data-chapter="78" tabindex="0">78</span><span class="chapter-chip" data-chapter="79" tabindex="0">79</span><span class="chapter-chip" data-chapter="80" tabindex="0">80</span><span class="chapter-chip" data-chapter="81" tabindex="0">81</span><span class="chapter-chip" data-chapter="82" tabindex="0">82</span><span class="chapter-chip" data-chapter="83" tabindex="0">83</span><span class="chapter-chip" data-chapter="84" tabindex="0">84</span><span class="chapter-chip" data-chapter="85" tabindex="0">85</span><span class="chapter-chip" data-chapter="86" tabindex="0">86</span><span class="chapter-chip" data-chapter="87" tabindex="0">87</span><span class="chapter-chip" data-chapter="88" tabindex="0">88</span><span class="chapter-chip" data-chapter="89" tabindex="0">89</span><span class="chapter-chip" data-chapter="90" tabindex="0">90</span><span class="chapter-chip" data-chapter="91" tabindex="0">91</span><span class="chapter-chip" data-chapter="92" tabindex="0">92</span><span class="chapter-chip" data-chapter="93" tabindex="0">93</span><span class="chapter-chip" data-chapter="94" tabindex="0">94</span><span class="chapter-chip" data-chapter="95" tabindex="0">95</span><span class="chapter-chip" data-chapter="96" tabindex="0">96</span><span class="chapter-chip" data-chapter="97" tabindex="0">97</span><span class="chapter-chip" data-chapter="98" tabindex="0">98</span><span class="chapter-chip" data-chapter="99" tabindex="0">99</span><span class="chapter-chip" data-chapter="100" tabindex="0">100</span><span class="chapter-chip" data-chapter="101" tabindex="0">101</span><span class="chapter-chip" data-chapter="102" tabindex="0">102</span><span class="chapter-chip" data-chapter="103" tabindex="0">103</span><span class="chapter-chip" data-chapter="104" tabindex="0">104</span><span class="chapter-chip" data-chapter="105" tabindex="0">105</span><span class="chapter-chip" data-chapter="106" tabindex="0">106</span><span class="chapter-chip" data-chapter="107" tabindex="0">107</span><span class="chapter-chip" data-chapter="108" tabindex="0">108</span><span class="chapter-chip" data-chapter="109" tabindex="0">109</span><span class="chapter-chip" data-chapter="110" tabindex="0">110</span><span class="chapter-chip" data-chapter="111" tabindex="0">111</span><span class="chapter-chip" data-chapter="112" tabindex="0">112</span><span class="chapter-chip" data-chapter="113" tabindex="0">113</span><span class="chapter-chip" data-chapter="114" tabindex="0">114</span><span class="chapter-chip" data-chapter="115" tabindex="0">115</span><span class="chapter-chip" data-chapter="116" tabindex="0">116</span><span class="chapter-chip" data-chapter="117" tabindex="0">117</span><span class="chapter-chip" data-chapter="118" tabindex="0">118</span><span class="chapter-chip" data-chapter="119" tabindex="0">119</span><span class="chapter-chip" data-chapter="120" tabindex="0">120</span><span class="chapter-chip" data-chapter="121" tabindex="0">121</span><span class="chapter-chip" data-chapter="122" tabindex="0">122</span><span class="chapter-chip" data-chapter="123" tabindex="0">123</span><span class="chapter-chip" data-chapter="124" tabindex="0">124</span><span class="chapter-chip" data-chapter="125" tabindex="0">125</span><span class="chapter-chip" data-chapter="126" tabindex="0">126</span><span class="chapter-chip" data-chapter="127" tabindex="0">127</span><span class="chapter-chip" data-chapter="128" tabindex="0">128</span><span class="chapter-chip" data-chapter="129" tabindex="0">129</span><span class="chapter-chip" data-chapter="130" tabindex="0">130</span><span class="chapter-chip" data-chapter="131" tabindex="0">131</span><span class="chapter-chip" data-chapter="132" tabindex="0">132</span><span class="chapter-chip" data-chapter="133" tabindex="0">133</span><span class="chapter-chip" data-chapter="134" tabindex="0">134</span><span class="chapter-chip" data-chapter="135" tabindex="0">135</span><span class="chapter-chip" data-chapter="136" tabindex="0">136</span><span class="chapter-chip" data-chapter="137" tabindex="0">137</span><span class="chapter-chip" data-chapter="138" tabindex="0">138</span><span class="chapter-chip" data-chapter="139" tabindex="0">139</span><span class="chapter-chip" data-chapter="140" tabindex="0">140</span><span class="chapter-chip" data-chapter="141" tabindex="0">141</span><span class="chapter-chip" data-chapter="142" tabindex="0">142</span><span class="chapter-chip" data-chapter="143" tabindex="0">143</span><span class="chapter-chip" data-chapter="144" tabindex="0">144</span><span class="chapter-chip" data-chapter="145" tabindex="0">145</span><span class="chapter-chip" data-chapter="146" tabindex="0">146</span><span class="chapter-chip" data-chapter="147" tabindex="0">147</span><span class="chapter-chip" data-chapter="148" tabindex="0">148</span><span class="chapter-chip" data-chapter="149" tabindex="0">149</span><span class="chapter-chip" data-chapter="150" tabindex="0">150</span></div>
            </div>
            <div class="book-item" data-book="proverbs" data-chapters="31">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-proverbs">
                <span class="book-abbr">PRO</span>
                <span class="book-name">Proverbs</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-proverbs" role="group" aria-label="Proverbs chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span></div>
            </div>
            <div class="book-item" data-book="ecclesiastes" data-chapters="12">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-ecclesiastes">
                <span class="book-abbr">ECC</span>
                <span class="book-name">Ecclesiastes</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-ecclesiastes" role="group" aria-label="Ecclesiastes chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span></div>
            </div>
            <div class="book-item" data-book="song_of_solomon" data-chapters="8">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-song_of_solomon">
                <span class="book-abbr">SNG</span>
                <span class="book-name">Song of Solomon</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-song_of_solomon" role="group" aria-label="Song of Solomon chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span></div>
            </div>
            <div class="book-item" data-book="isaiah" data-chapters="66">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-isaiah">
                <span class="book-abbr">ISA</span>
                <span class="book-name">Isaiah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-isaiah" role="group" aria-label="Isaiah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span><span class="chapter-chip" data-chapter="37" tabindex="0">37</span><span class="chapter-chip" data-chapter="38" tabindex="0">38</span><span class="chapter-chip" data-chapter="39" tabindex="0">39</span><span class="chapter-chip" data-chapter="40" tabindex="0">40</span><span class="chapter-chip" data-chapter="41" tabindex="0">41</span><span class="chapter-chip" data-chapter="42" tabindex="0">42</span><span class="chapter-chip" data-chapter="43" tabindex="0">43</span><span class="chapter-chip" data-chapter="44" tabindex="0">44</span><span class="chapter-chip" data-chapter="45" tabindex="0">45</span><span class="chapter-chip" data-chapter="46" tabindex="0">46</span><span class="chapter-chip" data-chapter="47" tabindex="0">47</span><span class="chapter-chip" data-chapter="48" tabindex="0">48</span><span class="chapter-chip" data-chapter="49" tabindex="0">49</span><span class="chapter-chip" data-chapter="50" tabindex="0">50</span><span class="chapter-chip" data-chapter="51" tabindex="0">51</span><span class="chapter-chip" data-chapter="52" tabindex="0">52</span><span class="chapter-chip" data-chapter="53" tabindex="0">53</span><span class="chapter-chip" data-chapter="54" tabindex="0">54</span><span class="chapter-chip" data-chapter="55" tabindex="0">55</span><span class="chapter-chip" data-chapter="56" tabindex="0">56</span><span class="chapter-chip" data-chapter="57" tabindex="0">57</span><span class="chapter-chip" data-chapter="58" tabindex="0">58</span><span class="chapter-chip" data-chapter="59" tabindex="0">59</span><span class="chapter-chip" data-chapter="60" tabindex="0">60</span><span class="chapter-chip" data-chapter="61" tabindex="0">61</span><span class="chapter-chip" data-chapter="62" tabindex="0">62</span><span class="chapter-chip" data-chapter="63" tabindex="0">63</span><span class="chapter-chip" data-chapter="64" tabindex="0">64</span><span class="chapter-chip" data-chapter="65" tabindex="0">65</span><span class="chapter-chip" data-chapter="66" tabindex="0">66</span></div>
            </div>
            <div class="book-item" data-book="jeremiah" data-chapters="52">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-jeremiah">
                <span class="book-abbr">JER</span>
                <span class="book-name">Jeremiah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-jeremiah" role="group" aria-label="Jeremiah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span><span class="chapter-chip" data-chapter="37" tabindex="0">37</span><span class="chapter-chip" data-chapter="38" tabindex="0">38</span><span class="chapter-chip" data-chapter="39" tabindex="0">39</span><span class="chapter-chip" data-chapter="40" tabindex="0">40</span><span class="chapter-chip" data-chapter="41" tabindex="0">41</span><span class="chapter-chip" data-chapter="42" tabindex="0">42</span><span class="chapter-chip" data-chapter="43" tabindex="0">43</span><span class="chapter-chip" data-chapter="44" tabindex="0">44</span><span class="chapter-chip" data-chapter="45" tabindex="0">45</span><span class="chapter-chip" data-chapter="46" tabindex="0">46</span><span class="chapter-chip" data-chapter="47" tabindex="0">47</span><span class="chapter-chip" data-chapter="48" tabindex="0">48</span><span class="chapter-chip" data-chapter="49" tabindex="0">49</span><span class="chapter-chip" data-chapter="50" tabindex="0">50</span><span class="chapter-chip" data-chapter="51" tabindex="0">51</span><span class="chapter-chip" data-chapter="52" tabindex="0">52</span></div>
            </div>
            <div class="book-item" data-book="lamentations" data-chapters="5">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-lamentations">
                <span class="book-abbr">LAM</span>
                <span class="book-name">Lamentations</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-lamentations" role="group" aria-label="Lamentations chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span></div>
            </div>
            <div class="book-item" data-book="ezekiel" data-chapters="48">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-ezekiel">
                <span class="book-abbr">EZK</span>
                <span class="book-name">Ezekiel</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-ezekiel" role="group" aria-label="Ezekiel chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span><span class="chapter-chip" data-chapter="29" tabindex="0">29</span><span class="chapter-chip" data-chapter="30" tabindex="0">30</span><span class="chapter-chip" data-chapter="31" tabindex="0">31</span><span class="chapter-chip" data-chapter="32" tabindex="0">32</span><span class="chapter-chip" data-chapter="33" tabindex="0">33</span><span class="chapter-chip" data-chapter="34" tabindex="0">34</span><span class="chapter-chip" data-chapter="35" tabindex="0">35</span><span class="chapter-chip" data-chapter="36" tabindex="0">36</span><span class="chapter-chip" data-chapter="37" tabindex="0">37</span><span class="chapter-chip" data-chapter="38" tabindex="0">38</span><span class="chapter-chip" data-chapter="39" tabindex="0">39</span><span class="chapter-chip" data-chapter="40" tabindex="0">40</span><span class="chapter-chip" data-chapter="41" tabindex="0">41</span><span class="chapter-chip" data-chapter="42" tabindex="0">42</span><span class="chapter-chip" data-chapter="43" tabindex="0">43</span><span class="chapter-chip" data-chapter="44" tabindex="0">44</span><span class="chapter-chip" data-chapter="45" tabindex="0">45</span><span class="chapter-chip" data-chapter="46" tabindex="0">46</span><span class="chapter-chip" data-chapter="47" tabindex="0">47</span><span class="chapter-chip" data-chapter="48" tabindex="0">48</span></div>
            </div>
            <div class="book-item" data-book="daniel" data-chapters="12">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-daniel">
                <span class="book-abbr">DAN</span>
                <span class="book-name">Daniel</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-daniel" role="group" aria-label="Daniel chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span></div>
            </div>
            <div class="book-item" data-book="hosea" data-chapters="14">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-hosea">
                <span class="book-abbr">HOS</span>
                <span class="book-name">Hosea</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-hosea" role="group" aria-label="Hosea chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span></div>
            </div>
            <div class="book-item" data-book="joel" data-chapters="3">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-joel">
                <span class="book-abbr">JOL</span>
                <span class="book-name">Joel</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-joel" role="group" aria-label="Joel chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span></div>
            </div>
            <div class="book-item" data-book="amos" data-chapters="9">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-amos">
                <span class="book-abbr">AMO</span>
                <span class="book-name">Amos</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-amos" role="group" aria-label="Amos chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span></div>
            </div>
            <div class="book-item" data-book="obadiah" data-chapters="1">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-obadiah">
                <span class="book-abbr">OBA</span>
                <span class="book-name">Obadiah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-obadiah" role="group" aria-label="Obadiah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span></div>
            </div>
            <div class="book-item" data-book="jonah" data-chapters="4">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-jonah">
                <span class="book-abbr">JON</span>
                <span class="book-name">Jonah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-jonah" role="group" aria-label="Jonah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span></div>
            </div>
            <div class="book-item" data-book="micah" data-chapters="7">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-micah">
                <span class="book-abbr">MIC</span>
                <span class="book-name">Micah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-micah" role="group" aria-label="Micah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span></div>
            </div>
            <div class="book-item" data-book="nahum" data-chapters="3">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-nahum">
                <span class="book-abbr">NAH</span>
                <span class="book-name">Nahum</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-nahum" role="group" aria-label="Nahum chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span></div>
            </div>
            <div class="book-item" data-book="habakkuk" data-chapters="3">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-habakkuk">
                <span class="book-abbr">HAB</span>
                <span class="book-name">Habakkuk</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-habakkuk" role="group" aria-label="Habakkuk chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span></div>
            </div>
            <div class="book-item" data-book="zephaniah" data-chapters="3">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-zephaniah">
                <span class="book-abbr">ZEP</span>
                <span class="book-name">Zephaniah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-zephaniah" role="group" aria-label="Zephaniah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span></div>
            </div>
            <div class="book-item" data-book="haggai" data-chapters="2">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-haggai">
                <span class="book-abbr">HAG</span>
                <span class="book-name">Haggai</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-haggai" role="group" aria-label="Haggai chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span></div>
            </div>
            <div class="book-item" data-book="zechariah" data-chapters="14">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-zechariah">
                <span class="book-abbr">ZEC</span>
                <span class="book-name">Zechariah</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-zechariah" role="group" aria-label="Zechariah chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span></div>
            </div>
            <div class="book-item" data-book="malachi" data-chapters="4">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-malachi">
                <span class="book-abbr">MAL</span>
                <span class="book-name">Malachi</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-malachi" role="group" aria-label="Malachi chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span></div>
            </div>
          </div>
        </div>
        <div class="nav-section">
          <div class="nav-section-label">New Testament</div>
          <div class="book-list">
            <div class="book-item" data-book="matthew" data-chapters="28">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-matthew">
                <span class="book-abbr">MAT</span>
                <span class="book-name">Matthew</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-matthew" role="group" aria-label="Matthew chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span></div>
            </div>
            <div class="book-item" data-book="mark" data-chapters="16">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-mark">
                <span class="book-abbr">MRK</span>
                <span class="book-name">Mark</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-mark" role="group" aria-label="Mark chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span></div>
            </div>
            <div class="book-item" data-book="luke" data-chapters="24">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-luke">
                <span class="book-abbr">LUK</span>
                <span class="book-name">Luke</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-luke" role="group" aria-label="Luke chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span></div>
            </div>
            <div class="book-item" data-book="john" data-chapters="21">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-john">
                <span class="book-abbr">JHN</span>
                <span class="book-name">John</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-john" role="group" aria-label="John chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span></div>
            </div>
            <div class="book-item" data-book="acts" data-chapters="28">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-acts">
                <span class="book-abbr">ACT</span>
                <span class="book-name">Acts</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-acts" role="group" aria-label="Acts chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span><span class="chapter-chip" data-chapter="23" tabindex="0">23</span><span class="chapter-chip" data-chapter="24" tabindex="0">24</span><span class="chapter-chip" data-chapter="25" tabindex="0">25</span><span class="chapter-chip" data-chapter="26" tabindex="0">26</span><span class="chapter-chip" data-chapter="27" tabindex="0">27</span><span class="chapter-chip" data-chapter="28" tabindex="0">28</span></div>
            </div>
            <div class="book-item" data-book="romans" data-chapters="16">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-romans">
                <span class="book-abbr">ROM</span>
                <span class="book-name">Romans</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-romans" role="group" aria-label="Romans chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span></div>
            </div>
            <div class="book-item" data-book="1_corinthians" data-chapters="16">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_corinthians">
                <span class="book-abbr">1CO</span>
                <span class="book-name">1 Corinthians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_corinthians" role="group" aria-label="1 Corinthians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span></div>
            </div>
            <div class="book-item" data-book="2_corinthians" data-chapters="13">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_corinthians">
                <span class="book-abbr">2CO</span>
                <span class="book-name">2 Corinthians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_corinthians" role="group" aria-label="2 Corinthians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span></div>
            </div>
            <div class="book-item" data-book="galatians" data-chapters="6">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-galatians">
                <span class="book-abbr">GAL</span>
                <span class="book-name">Galatians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-galatians" role="group" aria-label="Galatians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span></div>
            </div>
            <div class="book-item" data-book="ephesians" data-chapters="6">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-ephesians">
                <span class="book-abbr">EPH</span>
                <span class="book-name">Ephesians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-ephesians" role="group" aria-label="Ephesians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span></div>
            </div>
            <div class="book-item" data-book="philippians" data-chapters="4">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-philippians">
                <span class="book-abbr">PHP</span>
                <span class="book-name">Philippians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-philippians" role="group" aria-label="Philippians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span></div>
            </div>
            <div class="book-item" data-book="colossians" data-chapters="4">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-colossians">
                <span class="book-abbr">COL</span>
                <span class="book-name">Colossians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-colossians" role="group" aria-label="Colossians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span></div>
            </div>
            <div class="book-item" data-book="1_thessalonians" data-chapters="5">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_thessalonians">
                <span class="book-abbr">1TH</span>
                <span class="book-name">1 Thessalonians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_thessalonians" role="group" aria-label="1 Thessalonians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span></div>
            </div>
            <div class="book-item" data-book="2_thessalonians" data-chapters="3">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_thessalonians">
                <span class="book-abbr">2TH</span>
                <span class="book-name">2 Thessalonians</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_thessalonians" role="group" aria-label="2 Thessalonians chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span></div>
            </div>
            <div class="book-item" data-book="1_timothy" data-chapters="6">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_timothy">
                <span class="book-abbr">1TI</span>
                <span class="book-name">1 Timothy</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_timothy" role="group" aria-label="1 Timothy chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span></div>
            </div>
            <div class="book-item" data-book="2_timothy" data-chapters="4">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_timothy">
                <span class="book-abbr">2TI</span>
                <span class="book-name">2 Timothy</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_timothy" role="group" aria-label="2 Timothy chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span></div>
            </div>
            <div class="book-item" data-book="titus" data-chapters="3">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-titus">
                <span class="book-abbr">TIT</span>
                <span class="book-name">Titus</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-titus" role="group" aria-label="Titus chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span></div>
            </div>
            <div class="book-item" data-book="philemon" data-chapters="1">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-philemon">
                <span class="book-abbr">PHM</span>
                <span class="book-name">Philemon</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-philemon" role="group" aria-label="Philemon chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span></div>
            </div>
            <div class="book-item" data-book="hebrews" data-chapters="13">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-hebrews">
                <span class="book-abbr">HEB</span>
                <span class="book-name">Hebrews</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-hebrews" role="group" aria-label="Hebrews chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span></div>
            </div>
            <div class="book-item" data-book="james" data-chapters="5">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-james">
                <span class="book-abbr">JAS</span>
                <span class="book-name">James</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-james" role="group" aria-label="James chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span></div>
            </div>
            <div class="book-item" data-book="1_peter" data-chapters="5">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_peter">
                <span class="book-abbr">1PE</span>
                <span class="book-name">1 Peter</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_peter" role="group" aria-label="1 Peter chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span></div>
            </div>
            <div class="book-item" data-book="2_peter" data-chapters="3">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_peter">
                <span class="book-abbr">2PE</span>
                <span class="book-name">2 Peter</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_peter" role="group" aria-label="2 Peter chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span></div>
            </div>
            <div class="book-item" data-book="1_john" data-chapters="5">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-1_john">
                <span class="book-abbr">1JN</span>
                <span class="book-name">1 John</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-1_john" role="group" aria-label="1 John chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span></div>
            </div>
            <div class="book-item" data-book="2_john" data-chapters="1">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-2_john">
                <span class="book-abbr">2JN</span>
                <span class="book-name">2 John</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-2_john" role="group" aria-label="2 John chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span></div>
            </div>
            <div class="book-item" data-book="3_john" data-chapters="1">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-3_john">
                <span class="book-abbr">3JN</span>
                <span class="book-name">3 John</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-3_john" role="group" aria-label="3 John chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span></div>
            </div>
            <div class="book-item" data-book="jude" data-chapters="1">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-jude">
                <span class="book-abbr">JUD</span>
                <span class="book-name">Jude</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-jude" role="group" aria-label="Jude chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span></div>
            </div>
            <div class="book-item" data-book="revelation" data-chapters="22">
              <button class="book-btn" aria-expanded="false" aria-controls="chapters-revelation">
                <span class="book-abbr">REV</span>
                <span class="book-name">Revelation</span>
                <svg class="book-chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true"><path d="M2 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <div class="chapter-list" id="chapters-revelation" role="group" aria-label="Revelation chapters" hidden><span class="chapter-chip" data-chapter="1" tabindex="0">1</span><span class="chapter-chip" data-chapter="2" tabindex="0">2</span><span class="chapter-chip" data-chapter="3" tabindex="0">3</span><span class="chapter-chip" data-chapter="4" tabindex="0">4</span><span class="chapter-chip" data-chapter="5" tabindex="0">5</span><span class="chapter-chip" data-chapter="6" tabindex="0">6</span><span class="chapter-chip" data-chapter="7" tabindex="0">7</span><span class="chapter-chip" data-chapter="8" tabindex="0">8</span><span class="chapter-chip" data-chapter="9" tabindex="0">9</span><span class="chapter-chip" data-chapter="10" tabindex="0">10</span><span class="chapter-chip" data-chapter="11" tabindex="0">11</span><span class="chapter-chip" data-chapter="12" tabindex="0">12</span><span class="chapter-chip" data-chapter="13" tabindex="0">13</span><span class="chapter-chip" data-chapter="14" tabindex="0">14</span><span class="chapter-chip" data-chapter="15" tabindex="0">15</span><span class="chapter-chip" data-chapter="16" tabindex="0">16</span><span class="chapter-chip" data-chapter="17" tabindex="0">17</span><span class="chapter-chip" data-chapter="18" tabindex="0">18</span><span class="chapter-chip" data-chapter="19" tabindex="0">19</span><span class="chapter-chip" data-chapter="20" tabindex="0">20</span><span class="chapter-chip" data-chapter="21" tabindex="0">21</span><span class="chapter-chip" data-chapter="22" tabindex="0">22</span></div>
            </div>
          </div>
        </div>
      </nav>
    </aside><!-- /#sidebar -->

    <!-- READER AREA -->
    <main id="reader-area" role="main" aria-label="Scripture reader">

      <div id="chapter-header">
        <button class="chapter-nav-btn" id="prev-chapter-btn" aria-label="Previous chapter">
          <svg width="8" height="14" viewBox="0 0 8 14" fill="none" aria-hidden="true">
            <path d="M6 2L2 7l4 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <div class="chapter-title-group">
          <div class="chapter-book-name" id="chapter-book-display">John</div>
          <div class="chapter-number" id="chapter-num-display">Chapter 3</div>
        </div>

        <div class="chapter-meta">
          <span class="chapter-verse-count" id="chapter-verse-count">36 verses</span>
          <button class="chapter-bookmark-btn" id="chapter-bookmark-btn" aria-label="Bookmark this chapter" aria-pressed="false">
            <svg width="14" height="16" viewBox="0 0 14 16" fill="none" aria-hidden="true">
              <path d="M2 1.5h10v13l-5-3-5 3V1.5z" stroke="currentColor" stroke-width="1.4"/>
            </svg>
          </button>
        </div>

        <button class="chapter-nav-btn" id="next-chapter-btn" aria-label="Next chapter">
          <svg width="8" height="14" viewBox="0 0 8 14" fill="none" aria-hidden="true">
            <path d="M2 2l4 5-4 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div><!-- /#chapter-header -->

      <div id="chapter-content" class="scroll-y" role="region" aria-label="Chapter text" aria-live="polite" aria-atomic="false">

        <div class="chapter-intro">
          <div class="chapter-intro-ref">John · Chapter 3</div>
        </div>

        <article class="content-heading">The New Birth</article>

        <div class="verse-row" data-verse="1" id="v-1">
          <span class="verse-num" aria-label="Verse 1">1</span>
          <span class="verse-text">Now there was a <span class="word" data-strongs="G5330" tabindex="0">Pharisee</span>, a <span class="word" data-strongs="G444" tabindex="0">man</span> named <span class="word" data-strongs="G3530" tabindex="0">Nicodemus</span> who was a <span class="word" data-strongs="G758" tabindex="0">member of the Jewish ruling council</span>.</span>
          <div class="verse-actions" aria-label="Verse 1 actions">
            <button class="verse-action-btn" aria-label="Bookmark verse 1" title="Bookmark">
              <svg width="12" height="14" viewBox="0 0 12 14" fill="none"><path d="M1.5 1.5h9v11l-4.5-2.7L1.5 12.5V1.5z" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Add note to verse 1" title="Note">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="1" width="11" height="11" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M3.5 4.5h6M3.5 7h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Copy verse 1" title="Copy">
              <svg width="12" height="13" viewBox="0 0 12 13" fill="none"><rect x="4" y="1" width="7" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M1 4.5V12h7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>

        <div class="verse-row" data-verse="2" id="v-2">
          <span class="verse-num" aria-label="Verse 2">2</span>
          <span class="verse-text">He came to Jesus at night and said, <span class="red-letter">"<span class="word" data-strongs="G4461" tabindex="0">Rabbi</span>, we know that you are a <span class="word" data-strongs="G1320" tabindex="0">teacher</span> who has come from God. For no one could perform the <span class="word" data-strongs="G4592" tabindex="0">signs</span> you are doing if God were not with him."</span></span>
          <div class="verse-actions" aria-label="Verse 2 actions">
            <button class="verse-action-btn" aria-label="Bookmark verse 2" title="Bookmark">
              <svg width="12" height="14" viewBox="0 0 12 14" fill="none"><path d="M1.5 1.5h9v11l-4.5-2.7L1.5 12.5V1.5z" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Add note to verse 2" title="Note">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="1" width="11" height="11" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M3.5 4.5h6M3.5 7h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Copy verse 2" title="Copy">
              <svg width="12" height="13" viewBox="0 0 12 13" fill="none"><rect x="4" y="1" width="7" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M1 4.5V12h7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>

        <div class="verse-row selected" data-verse="16" id="v-16">
          <span class="verse-num" aria-label="Verse 16">16</span>
          <span class="verse-text"><span class="red-letter">For <span class="word" data-strongs="G3779" tabindex="0">God</span> so <span class="word" data-strongs="G25" tabindex="0">loved</span> the <span class="word" data-strongs="G2889" tabindex="0">world</span> that he gave his one and only <span class="word" data-strongs="G3439" tabindex="0">Son</span>, that whoever <span class="word" data-strongs="G4100" tabindex="0">believes</span> in him shall not perish but have <span class="word" data-strongs="G166" tabindex="0">eternal life</span>.</span></span>
          <div class="verse-actions" aria-label="Verse 16 actions">
            <button class="verse-action-btn" aria-label="Bookmark verse 16" title="Bookmark">
              <svg width="12" height="14" viewBox="0 0 12 14" fill="none"><path d="M1.5 1.5h9v11l-4.5-2.7L1.5 12.5V1.5z" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Add note to verse 16" title="Note">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="1" width="11" height="11" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M3.5 4.5h6M3.5 7h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Copy verse 16" title="Copy">
              <svg width="12" height="13" viewBox="0 0 12 13" fill="none"><rect x="4" y="1" width="7" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M1 4.5V12h7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>

        <div class="verse-row" data-verse="17" id="v-17">
          <span class="verse-num" aria-label="Verse 17">17</span>
          <span class="verse-text"><span class="red-letter">For God did not send his Son into the world to <span class="word" data-strongs="G2919" tabindex="0">condemn</span> the world, but to <span class="word" data-strongs="G4982" tabindex="0">save</span> the world through him.</span></span>
          <div class="verse-actions" aria-label="Verse 17 actions">
            <button class="verse-action-btn" aria-label="Bookmark verse 17" title="Bookmark">
              <svg width="12" height="14" viewBox="0 0 12 14" fill="none"><path d="M1.5 1.5h9v11l-4.5-2.7L1.5 12.5V1.5z" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Add note to verse 17" title="Note">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="1" width="11" height="11" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M3.5 4.5h6M3.5 7h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Copy verse 17" title="Copy">
              <svg width="12" height="13" viewBox="0 0 12 13" fill="none"><rect x="4" y="1" width="7" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M1 4.5V12h7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>

        <div class="verse-row" data-verse="36" id="v-36">
          <span class="verse-num" aria-label="Verse 36">36</span>
          <span class="verse-text"><span class="word" data-strongs="G4100" tabindex="0">Whoever believes</span> in the Son has <span class="word" data-strongs="G166" tabindex="0">eternal life</span>, but whoever <span class="word" data-strongs="G544" tabindex="0">rejects</span> the Son will not see life, for God's <span class="word" data-strongs="G3709" tabindex="0">wrath</span> remains on them.</span>
          <div class="verse-actions" aria-label="Verse 36 actions">
            <button class="verse-action-btn" aria-label="Bookmark verse 36" title="Bookmark">
              <svg width="12" height="14" viewBox="0 0 12 14" fill="none"><path d="M1.5 1.5h9v11l-4.5-2.7L1.5 12.5V1.5z" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Add note to verse 36" title="Note">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="1" width="11" height="11" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M3.5 4.5h6M3.5 7h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            </button>
            <button class="verse-action-btn" aria-label="Copy verse 36" title="Copy">
              <svg width="12" height="13" viewBox="0 0 12 13" fill="none"><rect x="4" y="1" width="7" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M1 4.5V12h7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>

      </div><!-- /#chapter-content -->

    </main><!-- /#reader-area -->

    <!-- CONTEXT PANEL (desktop right panel) -->
    <aside id="context-panel" aria-label="Study tools">

      <div class="panel-tabs" role="tablist" aria-label="Study panel tabs">
        <button class="tab-btn active" role="tab" aria-selected="true" aria-controls="tab-crossrefs" id="tab-btn-crossrefs" data-tab="crossrefs">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
          Cross-refs
        </button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-strongs" id="tab-btn-strongs" data-tab="strongs">Strong's</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-interlinear" id="tab-btn-interlinear" data-tab="interlinear">Interlinear</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-commentary" id="tab-btn-commentary" data-tab="commentary">Commentary</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-notes" id="tab-btn-notes" data-tab="notes">Notes</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-maps" id="tab-btn-maps" data-tab="maps">Maps</button>
      </div>

      <!-- Cross-references tab -->
      <div class="tab-pane active" id="tab-crossrefs" role="tabpanel" aria-labelledby="tab-btn-crossrefs">
        <div class="panel-empty" id="crossrefs-empty">
          <div class="panel-empty-icon" aria-hidden="true">✝</div>
          <div class="panel-empty-text">Tap a verse to see cross-references</div>
        </div>
        <div id="crossrefs-content" hidden>
          <div class="crossref-item" tabindex="0" role="button" data-ref="Romans 5:8">
            <span class="crossref-ref">Romans 5:8</span>
            <span class="crossref-preview">But God demonstrates his own love for us in this: While we were still sinners, Christ died for us.</span>
          </div>
          <div class="crossref-item" tabindex="0" role="button" data-ref="1 John 4:9">
            <span class="crossref-ref">1 John 4:9</span>
            <span class="crossref-preview">This is how God showed his love among us: He sent his one and only Son into the world that we might live through him.</span>
          </div>
          <div class="crossref-item" tabindex="0" role="button" data-ref="John 1:14">
            <span class="crossref-ref">John 1:14</span>
            <span class="crossref-preview">The Word became flesh and made his dwelling among us. We have seen his glory, the glory of the one and only Son, who came from the Father, full of grace and truth.</span>
          </div>
          <div class="crossref-item" tabindex="0" role="button" data-ref="Ephesians 2:8–9">
            <span class="crossref-ref">Ephesians 2:8–9</span>
            <span class="crossref-preview">For it is by grace you have been saved, through faith — and this is not from yourselves, it is the gift of God.</span>
          </div>
        </div>
      </div>

      <!-- Strong's tab -->
      <div class="tab-pane" id="tab-strongs" role="tabpanel" aria-labelledby="tab-btn-strongs">
        <div class="panel-empty" id="strongs-empty">
          <div class="panel-empty-icon" aria-hidden="true">α</div>
          <div class="panel-empty-text">Tap a highlighted word to see its Strong's definition</div>
        </div>
        <div id="strongs-content" hidden>
          <div class="strongs-header">
            <span class="strongs-number">G25</span>
            <span class="strongs-original">ἀγαπάω</span>
            <span class="strongs-transliteration">agapaō</span>
          </div>
          <div class="strongs-section-label">Part of Speech</div>
          <div class="strongs-definition">Verb</div>
          <div class="strongs-section-label">Definition</div>
          <div class="strongs-definition">To love, to be full of goodwill and exhibit the same; of the love of God toward his Son; of the love of men toward God; of the love of God and Christ toward men.</div>
          <div class="strongs-section-label">Occurrences</div>
          <div class="strongs-definition">143× in the New Testament</div>
          <div class="strongs-section-label">Root</div>
          <div class="strongs-definition">From ἄγαν (agan) — much; akin to ἄγω (agō), to lead</div>
        </div>
      </div>

      <!-- Interlinear tab -->
      <div class="tab-pane" id="tab-interlinear" role="tabpanel" aria-labelledby="tab-btn-interlinear">
        <div class="panel-empty" id="interlinear-empty">
          <div class="panel-empty-icon" aria-hidden="true">λ</div>
          <div class="panel-empty-text">Select a verse to view interlinear text</div>
        </div>
        <div id="interlinear-content" hidden>
          <div style="display:flex;flex-wrap:wrap;direction:ltr">
            <div class="interlinear-word" tabindex="0" data-strongs="G3779">
              <span class="interlinear-original">Οὕτως</span>
              <span class="interlinear-transliteration">Houtōs</span>
              <span class="interlinear-gloss">For so</span>
              <span class="interlinear-strongs">G3779</span>
            </div>
            <div class="interlinear-word" tabindex="0" data-strongs="G1063">
              <span class="interlinear-original">γὰρ</span>
              <span class="interlinear-transliteration">gar</span>
              <span class="interlinear-gloss">for</span>
              <span class="interlinear-strongs">G1063</span>
            </div>
            <div class="interlinear-word" tabindex="0" data-strongs="G25">
              <span class="interlinear-original">ἠγάπησεν</span>
              <span class="interlinear-transliteration">ēgapēsen</span>
              <span class="interlinear-gloss">loved</span>
              <span class="interlinear-strongs">G25</span>
            </div>
            <div class="interlinear-word" tabindex="0" data-strongs="G2316">
              <span class="interlinear-original">ὁ θεὸς</span>
              <span class="interlinear-transliteration">ho theos</span>
              <span class="interlinear-gloss">God</span>
              <span class="interlinear-strongs">G2316</span>
            </div>
            <div class="interlinear-word" tabindex="0" data-strongs="G2889">
              <span class="interlinear-original">τὸν κόσμον</span>
              <span class="interlinear-transliteration">ton kosmon</span>
              <span class="interlinear-gloss">the world</span>
              <span class="interlinear-strongs">G2889</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Commentary tab -->
      <div class="tab-pane" id="tab-commentary" role="tabpanel" aria-labelledby="tab-btn-commentary">
        <div class="panel-empty" id="commentary-empty">
          <div class="panel-empty-icon" aria-hidden="true">📜</div>
          <div class="panel-empty-text">Select a verse to read commentary</div>
        </div>
        <div id="commentary-content" hidden>
          <div class="commentary-source">
            <span>Commentary on John 3:16</span>
            <select class="commentary-source-select" aria-label="Select commentary source">
              <option value="matthew-henry">Matthew Henry</option>
              <option value="spurgeon">Spurgeon</option>
              <option value="calvin">Calvin</option>
              <option value="benson">Benson</option>
            </select>
          </div>
          <div class="commentary-body">
            God so loved the world — The world of mankind; not only the Jews but the Gentiles also. The word so here points at the manner of this love, which was such as had never been before. He gave his only-begotten Son — A gift freely made; not merely sent as an ambassador or servant, but given up to suffer and die for us. That whosoever believeth — On these terms, open to all without distinction.</div>
        </div>
      </div>

      <!-- Notes tab -->
      <div class="tab-pane" id="tab-notes" role="tabpanel" aria-labelledby="tab-btn-notes">
        <div class="notes-toolbar">
          <button class="notes-toolbar-btn" title="Bold" aria-label="Bold text">B</button>
          <button class="notes-toolbar-btn" title="Italic" aria-label="Italic text" style="font-style:italic">I</button>
          <button class="notes-toolbar-btn" title="Underline" aria-label="Underline text" style="text-decoration:underline">U</button>
        </div>
        <textarea class="notes-textarea" id="verse-note-textarea" placeholder="Add a personal note for this verse…" aria-label="Personal verse note" rows="5"></textarea>
        <div class="notes-save-row">
          <button class="notes-save-btn" id="save-note-btn">Save Note</button>
        </div>
        <div class="notes-list" id="notes-list" aria-label="Saved notes" aria-live="polite">
          <div class="note-item">
            <div class="note-item-ref">John 3:16</div>
            <div class="note-item-body">The word "so" (Greek: houtōs) describes the manner and degree — God loved in this extraordinary way. See also Romans 5:8 for parallel.</div>
            <div class="note-item-date">Added 2 days ago</div>
          </div>
        </div>
      </div>

      <!-- Maps tab -->
      <div class="tab-pane" id="tab-maps" role="tabpanel" aria-labelledby="tab-btn-maps">
        <div class="map-placeholder" role="img" aria-label="Bible map viewer (select a location to view)">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <rect x="2" y="6" width="28" height="20" rx="2" stroke="currentColor" stroke-width="1.5"/>
            <path d="M11 6v20M21 6v20M2 16h28" stroke="currentColor" stroke-width="1" stroke-dasharray="2 2"/>
            <circle cx="16" cy="13" r="2.5" stroke="currentColor" stroke-width="1.5"/>
            <path d="M16 15.5C16 15.5 12 19 12 21.5" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
          </svg>
          <span style="font-size:12px">Interactive map loading</span>
        </div>
        <div class="map-location-list" aria-label="Locations mentioned in this passage">
          <div class="map-location-item" tabindex="0" role="button" aria-label="View Jerusalem on map">
            <div class="map-location-dot" style="background:#b8962e"></div>
            <span class="map-location-name">Jerusalem</span>
          </div>
          <div class="map-location-item" tabindex="0" role="button" aria-label="View Judea on map">
            <div class="map-location-dot" style="background:#7a6020"></div>
            <span class="map-location-name">Judea</span>
          </div>
          <div class="map-location-item" tabindex="0" role="button" aria-label="View Jordan River on map">
            <div class="map-location-dot" style="background:#4a7a9b"></div>
            <span class="map-location-name">Jordan River</span>
          </div>
        </div>
      </div>

    </aside><!-- /#context-panel -->

  </div><!-- /#main-layout -->

  <!-- BOTTOM NAV (mobile) -->
  <nav id="bottom-nav" aria-label="Primary navigation">
    <div class="bottom-nav-inner">
      <button class="bottom-nav-btn" id="bottomnav-books" aria-label="Books" aria-controls="sidebar" aria-expanded="false">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <rect x="3" y="2" width="11" height="14" rx="1.5" stroke="currentColor" stroke-width="1.4"/>
          <path d="M6 2v14" stroke="currentColor" stroke-width="1.4"/>
          <path d="M16 4v14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          <path d="M6 16l10 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
        Books
      </button>
      <button class="bottom-nav-btn" id="bottomnav-search" aria-label="Search" aria-controls="search-overlay">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="9" cy="9" r="6" stroke="currentColor" stroke-width="1.4"/>
          <path d="M13.5 13.5L18 18" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
        Search
      </button>
      <button class="bottom-nav-btn" id="bottomnav-notes" aria-label="Notes" aria-controls="bottom-sheet">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <rect x="3" y="2" width="14" height="16" rx="1.5" stroke="currentColor" stroke-width="1.4"/>
          <path d="M7 7h6M7 10h6M7 13h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
        Notes
      </button>
    </div>
  </nav><!-- /#bottom-nav -->

  <!-- BOTTOM SHEET (mobile context panel) -->
  <div id="bottom-sheet" role="dialog" aria-modal="false" aria-label="Study tools" aria-hidden="true">
    <div class="sheet-handle" role="presentation" aria-hidden="true"></div>
    <div class="sheet-body">
      <div class="panel-tabs" role="tablist" aria-label="Study panel tabs">
        <button class="tab-btn active" role="tab" aria-selected="true" aria-controls="sheet-tab-crossrefs" id="sheet-tab-btn-crossrefs" data-tab="crossrefs">Cross-refs</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="sheet-tab-strongs" id="sheet-tab-btn-strongs" data-tab="strongs">Strong's</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="sheet-tab-interlinear" id="sheet-tab-btn-interlinear" data-tab="interlinear">Interlinear</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="sheet-tab-commentary" id="sheet-tab-btn-commentary" data-tab="commentary">Commentary</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="sheet-tab-notes" id="sheet-tab-btn-notes" data-tab="notes">Notes</button>
        <button class="tab-btn" role="tab" aria-selected="false" aria-controls="sheet-tab-maps" id="sheet-tab-btn-maps" data-tab="maps">Maps</button>
      </div>
      <div class="tab-pane active scroll-y" id="sheet-tab-crossrefs" role="tabpanel" aria-labelledby="sheet-tab-btn-crossrefs">
        <div class="panel-empty"><div class="panel-empty-icon" aria-hidden="true">✝</div><div class="panel-empty-text">Tap a verse to see cross-references</div></div>
      </div>
      <div class="tab-pane scroll-y" id="sheet-tab-strongs" role="tabpanel" aria-labelledby="sheet-tab-btn-strongs">
        <div class="panel-empty"><div class="panel-empty-icon" aria-hidden="true">α</div><div class="panel-empty-text">Tap a highlighted word for Strong's definition</div></div>
      </div>
      <div class="tab-pane scroll-y" id="sheet-tab-interlinear" role="tabpanel" aria-labelledby="sheet-tab-btn-interlinear">
        <div class="panel-empty"><div class="panel-empty-icon" aria-hidden="true">λ</div><div class="panel-empty-text">Select a verse to view interlinear</div></div>
      </div>
      <div class="tab-pane scroll-y" id="sheet-tab-commentary" role="tabpanel" aria-labelledby="sheet-tab-btn-commentary">
        <div class="panel-empty"><div class="panel-empty-icon" aria-hidden="true">📜</div><div class="panel-empty-text">Select a verse to read commentary</div></div>
      </div>
      <div class="tab-pane scroll-y" id="sheet-tab-notes" role="tabpanel" aria-labelledby="sheet-tab-btn-notes">
        <textarea class="notes-textarea" placeholder="Add a personal note…" aria-label="Personal verse note" rows="4" style="margin-top:10px"></textarea>
        <div class="notes-save-row"><button class="notes-save-btn">Save Note</button></div>
      </div>
      <div class="tab-pane scroll-y" id="sheet-tab-maps" role="tabpanel" aria-labelledby="sheet-tab-btn-maps">
        <div class="panel-empty"><div class="panel-empty-icon" aria-hidden="true">🗺</div><div class="panel-empty-text">Select a location to view on map</div></div>
      </div>
    </div>
  </div><!-- /#bottom-sheet -->

  <!-- BACKDROP OVERLAY (shared) -->
  <div class="backdrop" id="main-backdrop" aria-hidden="true"></div>

  <!-- SESSIONS PANEL (slide-in drawer) -->
  <div id="sessions-panel" class="slide-drawer" role="dialog" aria-modal="true" aria-label="Study Sessions" aria-hidden="true">
    <div class="drawer-header">
      <span class="drawer-title">Study Sessions</span>
      <button class="drawer-close-btn" data-close="sessions-panel" aria-label="Close study sessions">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="drawer-body scroll-y">
      <div class="drawer-section-label">Active Sessions</div>
      <div class="session-list" id="session-list" aria-label="Your study sessions">
        <div class="session-item" data-session-id="1">
          <div class="session-item-name">The Gospel of John</div>
          <div class="session-item-meta">
            <span>John 3:16</span>
            <span class="meta-dot"></span>
            <span>Last read 2 hours ago</span>
          </div>
          <div class="session-item-actions">
            <button class="session-btn-resume" aria-label="Resume The Gospel of John session">Resume</button>
            <button class="session-btn-delete" aria-label="Delete The Gospel of John session" title="Delete session">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M2 3.5h9M4.5 3.5V2.5h4v1M5 5.5v4M8 5.5v4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><rect x="2.5" y="3.5" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
          </div>
        </div>
        <div class="session-item" data-session-id="2">
          <div class="session-item-name">Psalms of Praise</div>
          <div class="session-item-meta">
            <span>Psalm 23:1</span>
            <span class="meta-dot"></span>
            <span>Last read 3 days ago</span>
          </div>
          <div class="session-item-actions">
            <button class="session-btn-resume" aria-label="Resume Psalms of Praise session">Resume</button>
            <button class="session-btn-delete" aria-label="Delete Psalms of Praise session" title="Delete session">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M2 3.5h9M4.5 3.5V2.5h4v1M5 5.5v4M8 5.5v4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><rect x="2.5" y="3.5" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div class="drawer-section-label" style="margin-top:20px">New Session</div>
      <form id="new-session-form" novalidate>
        <input type="text" id="session-name-input" name="sessionName" placeholder="Session name…" aria-label="New session name" autocomplete="off" required>
        <button type="submit" class="session-save-btn">Start Session</button>
      </form>
    </div>
  </div><!-- /#sessions-panel -->

  <!-- BOOKMARKS PANEL (slide-in drawer) -->
  <div id="bookmarks-panel" class="slide-drawer" role="dialog" aria-modal="true" aria-label="Bookmarks" aria-hidden="true">
    <div class="drawer-header">
      <span class="drawer-title">Bookmarks</span>
      <button class="drawer-close-btn" data-close="bookmarks-panel" aria-label="Close bookmarks">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="drawer-body scroll-y">
      <div class="drawer-section-label">Saved Verses</div>
      <div class="bookmark-list" id="bookmark-list" aria-label="Your bookmarks">
        <div class="bookmark-item" tabindex="0" role="button" data-ref="john_3_16" aria-label="Go to John 3:16">
          <div class="bookmark-color-dot" style="background:#b8962e"></div>
          <span class="bookmark-ref">John 3:16</span>
          <span class="bookmark-label">God so loved the world</span>
          <button class="bookmark-navigate-btn" aria-label="Navigate to John 3:16" tabindex="-1">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
        <div class="bookmark-item" tabindex="0" role="button" data-ref="psalm_23_1" aria-label="Go to Psalm 23:1">
          <div class="bookmark-color-dot" style="background:#5aad6e"></div>
          <span class="bookmark-ref">Psalm 23:1</span>
          <span class="bookmark-label">The Lord is my shepherd</span>
          <button class="bookmark-navigate-btn" aria-label="Navigate to Psalm 23:1" tabindex="-1">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
        <div class="bookmark-item" tabindex="0" role="button" data-ref="romans_8_28" aria-label="Go to Romans 8:28">
          <div class="bookmark-color-dot" style="background:#6a7ad4"></div>
          <span class="bookmark-ref">Romans 8:28</span>
          <span class="bookmark-label">All things work together for good</span>
          <button class="bookmark-navigate-btn" aria-label="Navigate to Romans 8:28" tabindex="-1">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
      </div>
    </div>
  </div><!-- /#bookmarks-panel -->

  <!-- HISTORY PANEL (slide-in drawer) -->
  <div id="history-panel" class="slide-drawer" role="dialog" aria-modal="true" aria-label="Reading History" aria-hidden="true">
    <div class="drawer-header">
      <span class="drawer-title">History</span>
      <button class="drawer-close-btn" data-close="history-panel" aria-label="Close reading history">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="drawer-body scroll-y">
      <div class="history-list" id="history-list" role="list" aria-label="Recently read passages">
        <div class="history-item" role="listitem" tabindex="0" data-ref="john_3">
          <span class="history-ref">John 3</span>
          <span class="history-time">2 hours ago</span>
        </div>
        <div class="history-item" role="listitem" tabindex="0" data-ref="john_2">
          <span class="history-ref">John 2</span>
          <span class="history-time">Yesterday</span>
        </div>
        <div class="history-item" role="listitem" tabindex="0" data-ref="psalm_23">
          <span class="history-ref">Psalm 23</span>
          <span class="history-time">3 days ago</span>
        </div>
        <div class="history-item" role="listitem" tabindex="0" data-ref="romans_8">
          <span class="history-ref">Romans 8</span>
          <span class="history-time">5 days ago</span>
        </div>
        <div class="history-item" role="listitem" tabindex="0" data-ref="genesis_1">
          <span class="history-ref">Genesis 1</span>
          <span class="history-time">1 week ago</span>
        </div>
        <div class="history-item" role="listitem" tabindex="0" data-ref="isaiah_53">
          <span class="history-ref">Isaiah 53</span>
          <span class="history-time">1 week ago</span>
        </div>
      </div>
    </div>
  </div><!-- /#history-panel -->

  <!-- TOAST CONTAINER -->
  <div id="toast-container" role="region" aria-label="Notifications" aria-live="polite" aria-atomic="false"></div>

  <!-- SEARCH OVERLAY (mobile full-screen) -->
  <div id="search-overlay" role="dialog" aria-modal="true" aria-label="Search scriptures" aria-hidden="true">
    <div class="search-overlay-bar">
      <button class="search-overlay-back" aria-label="Close search" data-close="search-overlay">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path d="M11 4L6 9l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <div class="search-overlay-input-wrap">
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
          <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" stroke-width="1.3"/>
          <path d="M10 10L14 14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
        </svg>
        <input type="search" id="search-overlay-input" placeholder="Search scriptures…" aria-label="Search scriptures" autocomplete="off" spellcheck="false">
        <button class="search-overlay-clear" id="search-overlay-clear" aria-label="Clear search" hidden>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M3 3l8 8M11 3L3 11" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
        </button>
      </div>
    </div>

    <div class="search-filters" role="group" aria-label="Search filters">
      <button class="search-filter-chip active" data-filter="all">All</button>
      <button class="search-filter-chip" data-filter="ot">Old Testament</button>
      <button class="search-filter-chip" data-filter="nt">New Testament</button>
      <button class="search-filter-chip" data-filter="gospels">Gospels</button>
      <button class="search-filter-chip" data-filter="epistles">Epistles</button>
      <button class="search-filter-chip" data-filter="prophecy">Prophecy</button>
    </div>

    <div class="search-overlay-body scroll-y" id="search-overlay-body" role="region" aria-label="Search results" aria-live="polite">
      <div class="search-empty" id="search-overlay-empty">
        <div class="panel-empty-icon" aria-hidden="true">🔍</div>
        <p class="search-empty-label">Type a word, phrase, or reference<br>(e.g. "faith", "love", "John 3:16")</p>
      </div>
      <div id="search-results-list" hidden aria-label="Search results">
        <!-- Results rendered by JS -->
      </div>
    </div>
  </div><!-- /#search-overlay -->

</div><!-- /#app-shell -->

<script>
/* =============================================================================
   wn-bible-01 — Christ Pillar Bible App
   part3_auth.js — Auth, Session, Bookmark, History, Notes, Admin, Toast
   ============================================================================= */

'use strict';

// =============================================================================
// 1. AUTH STATE & HELPERS
// =============================================================================

let currentUser = null;
let authToken = null;
let activeSessionId = null;
let autoSaveInterval = null;

// State that is tracked across session snapshots
let _activeRef = 'John 1:1';
let currentTranslation = 'KJV';
let parallelMode = false;
let parallelTranslations = [];
let activeTab = 'strongs';

// In-memory bookmark cache: Map<ref, bookmarkObject>
const bookmarkCache = new Map();

/**
 * Persist auth credentials and update module-level state.
 * @param {string} token
 * @param {object} user  — {id, username, display_name, role}
 */
function setAuth(token, user) {
  authToken = token;
  currentUser = user;
  localStorage.setItem('bible_token', token);
  localStorage.setItem('bible_user', JSON.stringify(user));
}

/**
 * Remove all auth state from memory and localStorage.
 */
function clearAuth() {
  authToken = null;
  currentUser = null;
  activeSessionId = null;
  localStorage.removeItem('bible_token');
  localStorage.removeItem('bible_user');
}

/**
 * Returns true when the signed-in user holds the admin role.
 * @returns {boolean}
 */
function isAdmin() {
  return currentUser?.role === 'admin';
}

/**
 * fetch() wrapper that automatically injects the Bearer token header.
 * Callers can still override or add further headers via opts.headers.
 *
 * @param {string} url
 * @param {RequestInit} [opts={}]
 * @returns {Promise<Response>}
 */
async function authFetch(url, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (authToken) {
    headers.set('Authorization', `Bearer ${authToken}`);
  }
  if (!headers.has('Content-Type') && opts.body && typeof opts.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }
  return fetch(url, { ...opts, headers });
}

// =============================================================================
// 2. APP STARTUP AUTH CHECK
// =============================================================================

/**
 * Called once on page load.  Reads any persisted token and validates it
 * against the server.  Transitions the UI to either the login screen or
 * the app shell depending on the result.
 */
async function checkAuth() {
  const storedToken = localStorage.getItem('bible_token');
  if (!storedToken) {
    _showLoginScreen();
    return;
  }

  // Optimistically restore from cache so the UI can start rendering
  const cachedUser = localStorage.getItem('bible_user');
  if (cachedUser) {
    try {
      authToken = storedToken;
      currentUser = JSON.parse(cachedUser);
    } catch (_) {
      // Corrupted cache — fall through to server validation
    }
  }

  try {
    authToken = storedToken;
    const res = await authFetch('/api/auth/me');
    if (res.ok) {
      const user = await res.json();
      setAuth(storedToken, user);
      _showAppShell();
      updateUserChip();
      init(); // Defined in part1 / part2 — initialises the reader
    } else {
      clearAuth();
      _showLoginScreen();
    }
  } catch (_) {
    // Network failure: treat as logged-out rather than looping
    clearAuth();
    _showLoginScreen();
  }
}

function _showLoginScreen() {
  const loginScreen = document.getElementById('login-screen');
  const appShell = document.getElementById('app-shell');
  if (loginScreen) loginScreen.classList.remove('hidden');
  if (appShell) appShell.classList.add('hidden');
}

function _showAppShell() {
  const loginScreen = document.getElementById('login-screen');
  const appShell = document.getElementById('app-shell');
  if (loginScreen) loginScreen.classList.add('hidden');
  if (appShell) appShell.classList.remove('hidden');
}

// =============================================================================
// 3. LOGIN / REGISTER UI
// =============================================================================

let _authMode = 'login'; // 'login' | 'register'

/**
 * Submit handler wired to #login-form.
 * @param {SubmitEvent} e
 */
async function handleLogin(e) {
  e.preventDefault();
  const form = e.target;
  const username = form.querySelector('[name="username"]')?.value?.trim();
  const password = form.querySelector('[name="password"]')?.value;
  const errEl = form.querySelector('.auth-error');

  if (!username || !password) {
    _setAuthError(errEl, 'Username and password are required.');
    return;
  }

  const btn = form.querySelector('[type="submit"]');
  if (btn) btn.disabled = true;
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (res.ok) {
      const data = await res.json();
      setAuth(data.token, data.user);
      _clearAuthError(errEl);
      await checkAuth();
    } else {
      const err = await res.json().catch(() => ({}));
      _setAuthError(errEl, err.detail || 'Invalid username or password.');
    }
  } catch (e) {
    console.error('[bible] login fetch error:', e);
    _setAuthError(errEl, 'Network error: ' + (e?.message || e));
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * Submit handler wired to #register-form.
 * @param {SubmitEvent} e
 */
async function handleRegister(e) {
  e.preventDefault();
  const form = e.target;
  const username = form.querySelector('[name="username"]')?.value?.trim();
  const password = form.querySelector('[name="password"]')?.value;
  const displayName = form.querySelector('[name="display_name"]')?.value?.trim();
  const errEl = form.querySelector('.auth-error');

  if (!username || !password) {
    _setAuthError(errEl, 'Username and password are required.');
    return;
  }

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, display_name: displayName || username }),
    });

    if (res.ok) {
      const data = await res.json();
      setAuth(data.token, data.user);
      _clearAuthError(errEl);
      showToast('Account created — welcome!', 'success');
      await checkAuth();
    } else {
      const err = await res.json().catch(() => ({}));
      _setAuthError(errEl, err.detail || 'Registration failed.');
    }
  } catch (_) {
    _setAuthError(errEl, 'Network error — please try again.');
  }
}

/**
 * Toggle between the login and register form panels.
 */
function toggleAuthMode() {
  _authMode = _authMode === 'login' ? 'register' : 'login';

  const loginPanel = document.getElementById('login-form');
  const registerPanel = document.getElementById('register-form');
  const toggleBtn = document.querySelector('.auth-toggle');

  if (_authMode === 'register') {
    if (loginPanel) loginPanel.style.display = 'none';
    if (registerPanel) registerPanel.style.display = '';
    if (toggleBtn) toggleBtn.textContent = 'Back to sign in';
  } else {
    if (loginPanel) loginPanel.style.display = '';
    if (registerPanel) registerPanel.style.display = 'none';
    if (toggleBtn) toggleBtn.textContent = 'Create an account';
  }
}

function _setAuthError(el, msg) {
  if (!el) return;
  el.textContent = msg;
  el.style.display = '';
}

function _clearAuthError(el) {
  if (!el) return;
  el.textContent = '';
  el.style.display = 'none';
}

// =============================================================================
// 4. USER CHIP
// =============================================================================

/**
 * Populate the user avatar chip with initials and display name.
 */
function updateUserChip() {
  if (!currentUser) return;

  const initialsEl = document.querySelector('.user-chip .initials');
  const nameEl = document.querySelector('.user-chip .display-name');
  const adminItem = document.querySelector('.user-dropdown .admin-item');

  const displayName = currentUser.display_name || currentUser.username || '?';
  if (initialsEl) initialsEl.textContent = displayName.charAt(0).toUpperCase();
  if (nameEl) nameEl.textContent = displayName;

  // Show / hide admin menu item
  if (adminItem) adminItem.style.display = isAdmin() ? '' : 'none';
}

/**
 * Toggle visibility of the user dropdown menu.
 */
function toggleUserDropdown() {
  const dropdown = document.querySelector('.user-dropdown');
  if (!dropdown) return;
  const isOpen = dropdown.classList.toggle('open');
  if (isOpen) {
    // Close on next outside click
    setTimeout(() => {
      document.addEventListener('click', _closeUserDropdownOnOutsideClick, { once: true });
    }, 0);
  }
}

function _closeUserDropdownOnOutsideClick(e) {
  const dropdown = document.querySelector('.user-dropdown');
  const chip = document.querySelector('.user-chip');
  if (dropdown && !dropdown.contains(e.target) && chip && !chip.contains(e.target)) {
    dropdown.classList.remove('open');
  }
}

/**
 * Sign the current user out: revoke token on the server, wipe local state,
 * and reload the page so the login screen is presented fresh.
 */
async function handleSignOut() {
  try {
    await authFetch('/api/auth/logout', { method: 'POST' });
  } catch (_) {
    // Best-effort — we clear locally regardless
  }
  clearAuth();
  location.reload();
}

// =============================================================================
// 5. STUDY SESSIONS PANEL
// =============================================================================

function openSessionsPanel() {
  const panel = document.getElementById('sessions-panel');
  if (panel) {
    panel.classList.add('open');
    loadSessions();
  }
}

function closeSessionsPanel() {
  const panel = document.getElementById('sessions-panel');
  if (panel) panel.classList.remove('open');
}

/**
 * Fetch all sessions for the current user and render them into .session-list.
 */
async function loadSessions() {
  const listEl = document.querySelector('.session-list');
  if (!listEl) return;

  listEl.innerHTML = '<li class="session-loading">Loading sessions…</li>';

  try {
    const res = await authFetch('/api/sessions');
    if (!res.ok) throw new Error('Failed to load sessions');
    const sessions = await res.json();

    if (!sessions.length) {
      listEl.innerHTML = '<li class="session-empty">No saved sessions yet.</li>';
      return;
    }

    listEl.innerHTML = '';
    for (const s of sessions) {
      const li = document.createElement('li');
      li.className = 'session-item';
      li.dataset.id = s.id;

      const ts = s.updated_at || s.created_at;
      const relDate = ts ? relativeTime(Math.floor(new Date(ts).getTime() / 1000)) : '';

      li.innerHTML = `
        <div class="session-info">
          <span class="session-name">${_escHtml(s.name)}</span>
          <span class="session-date">${relDate}</span>
        </div>
        <div class="session-actions">
          <button class="btn-icon session-resume" title="Resume" data-id="${s.id}">▶</button>
          <button class="btn-icon session-delete" title="Delete" data-id="${s.id}">🗑</button>
        </div>`;

      li.querySelector('.session-resume').addEventListener('click', () => resumeSession(s.id));
      li.querySelector('.session-delete').addEventListener('click', () => deleteSession(s.id));

      listEl.appendChild(li);
    }
  } catch (err) {
    listEl.innerHTML = '<li class="session-error">Could not load sessions.</li>';
    console.error('loadSessions:', err);
  }
}

/**
 * Load a saved session by id and restore all UI state.
 * @param {string|number} id
 */
async function resumeSession(id) {
  try {
    const res = await authFetch(`/api/sessions/${id}`);
    if (!res.ok) throw new Error('Session not found');
    const session = await res.json();

    let state;
    try {
      state = typeof session.state_json === 'string'
        ? JSON.parse(session.state_json)
        : session.state_json;
    } catch (_) {
      showToast('Session data is corrupted.', 'error');
      return;
    }

    // Restore module-level state
    if (state.translation) {
      currentTranslation = state.translation;
      const sel = document.getElementById('translation-select');
      if (sel) sel.value = currentTranslation;
    }

    if (state.parallelMode !== undefined) parallelMode = state.parallelMode;
    if (state.parallelTranslations) parallelTranslations = state.parallelTranslations;
    if (state.activeTab) {
      activeTab = state.activeTab;
      _activateTab(activeTab);
    }

    if (state.ref) {
      _activeRef = state.ref;
      // loadChapter is defined in part1/part2 — call if available
      if (typeof loadChapter === 'function') {
        await loadChapter(state.ref);
      }
    }

    activeSessionId = id;
    closeSessionsPanel();
    showToast(`Resumed: ${session.name}`, 'success');
  } catch (err) {
    showToast('Could not resume session.', 'error');
    console.error('resumeSession:', err);
  }
}

/**
 * Capture current state and save a new named session.
 * @param {string} [name] — defaults to a prompt dialog
 */
async function saveSession(name) {
  const sessionName = name || prompt('Session name:', `Study – ${new Date().toLocaleDateString()}`);
  if (!sessionName) return;

  const snapshot = _captureStateSnapshot();

  try {
    const res = await authFetch('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ name: sessionName, state_json: JSON.stringify(snapshot) }),
    });
    if (!res.ok) throw new Error('Save failed');
    const saved = await res.json();
    activeSessionId = saved.id;
    showToast('Session saved.', 'success');
  } catch (err) {
    showToast('Could not save session.', 'error');
    console.error('saveSession:', err);
  }
}

/**
 * Auto-save the active session (called on interval).
 */
async function autoSaveSession() {
  if (!activeSessionId || !authToken) return;

  const snapshot = _captureStateSnapshot();
  try {
    await authFetch(`/api/sessions/${activeSessionId}`, {
      method: 'PUT',
      body: JSON.stringify({ state_json: JSON.stringify(snapshot) }),
    });
  } catch (err) {
    console.warn('autoSaveSession silent fail:', err);
  }
}

/**
 * Delete a session by id and refresh the list.
 * @param {string|number} id
 */
async function deleteSession(id) {
  if (!confirm('Delete this session?')) return;
  try {
    const res = await authFetch(`/api/sessions/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Delete failed');
    if (activeSessionId === id) activeSessionId = null;
    showToast('Session deleted.', 'info');
    await loadSessions();
  } catch (err) {
    showToast('Could not delete session.', 'error');
    console.error('deleteSession:', err);
  }
}

/**
 * Build a state snapshot from the current module-level variables.
 * @returns {object}
 */
function _captureStateSnapshot() {
  return {
    ref: _activeRef,
    translation: currentTranslation,
    parallelMode,
    parallelTranslations: [...parallelTranslations],
    activeTab,
  };
}

/**
 * Activate a named tab in the study panel.
 * @param {string} tabName
 */
function _activateTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('active', pane.id === `tab-${tabName}`);
  });
}

// =============================================================================
// 6. BOOKMARKS
// =============================================================================

/**
 * Fetch all bookmarks for the current user and populate the in-memory cache.
 */
async function loadBookmarks() {
  bookmarkCache.clear();
  try {
    const res = await authFetch('/api/bookmarks');
    if (!res.ok) return;
    const bookmarks = await res.json();
    for (const bm of bookmarks) {
      bookmarkCache.set(bm.ref, bm);
    }
  } catch (err) {
    console.warn('loadBookmarks:', err);
  }
}

/**
 * Return the cached bookmark object for a ref, or null if not bookmarked.
 * @param {string} ref
 * @returns {object|null}
 */
function checkBookmark(ref) {
  return bookmarkCache.get(ref) ?? null;
}

/**
 * Toggle a bookmark for the given ref.
 * @param {string} ref
 */
async function toggleBookmark(ref) {
  const existing = checkBookmark(ref);
  try {
    if (existing) {
      const res = await authFetch(`/api/bookmarks/${existing.id}`, { method: 'DELETE' });
      if (res.ok) {
        bookmarkCache.delete(ref);
        updateBookmarkIcon(ref);
        showToast('Bookmark removed.', 'info');
      }
    } else {
      const res = await authFetch('/api/bookmarks', {
        method: 'POST',
        body: JSON.stringify({ ref, label: ref, color: '#D4AF37' }),
      });
      if (res.ok) {
        const bm = await res.json();
        bookmarkCache.set(ref, bm);
        updateBookmarkIcon(ref);
        showToast('Bookmarked.', 'success');
      }
    }
  } catch (err) {
    showToast('Bookmark action failed.', 'error');
    console.error('toggleBookmark:', err);
  }
}

/**
 * Refresh the bookmark icon (☆ / ★) for any verse row displaying this ref.
 * @param {string} ref
 */
function updateBookmarkIcon(ref) {
  const isBookmarked = bookmarkCache.has(ref);
  document.querySelectorAll(`[data-ref="${CSS.escape(ref)}"] .bookmark-btn`).forEach(btn => {
    btn.textContent = isBookmarked ? '★' : '☆';
    btn.classList.toggle('bookmarked', isBookmarked);
    btn.title = isBookmarked ? 'Remove bookmark' : 'Add bookmark';
  });
}

function openBookmarksPanel() {
  const panel = document.getElementById('bookmarks-panel');
  if (panel) {
    panel.classList.add('open');
    renderBookmarksList();
  }
}

function closeBookmarksPanel() {
  const panel = document.getElementById('bookmarks-panel');
  if (panel) panel.classList.remove('open');
}

/**
 * Render bookmarks grouped by book into .bookmark-list.
 */
function renderBookmarksList() {
  const listEl = document.querySelector('.bookmark-list');
  if (!listEl) return;

  if (!bookmarkCache.size) {
    listEl.innerHTML = '<div class="bookmark-empty">No bookmarks yet. Click ☆ on any verse.</div>';
    return;
  }

  // Group by book name (first word of ref)
  const groups = new Map();
  for (const [ref, bm] of bookmarkCache) {
    const book = ref.split(' ').slice(0, -1).join(' ') || ref;
    if (!groups.has(book)) groups.set(book, []);
    groups.get(book).push(bm);
  }

  listEl.innerHTML = '';
  for (const [book, items] of [...groups.entries()].sort()) {
    const section = document.createElement('div');
    section.className = 'bookmark-group';

    const header = document.createElement('h4');
    header.className = 'bookmark-group-header';
    header.textContent = book;
    section.appendChild(header);

    for (const bm of items) {
      const div = document.createElement('div');
      div.className = 'bookmark-item';
      div.innerHTML = `
        <span class="bookmark-ref" style="border-left: 3px solid ${_escHtml(bm.color || '#D4AF37')}">
          ${_escHtml(bm.ref)}
        </span>
        <button class="btn-icon bookmark-remove" title="Remove" data-id="${bm.id}" data-ref="${_escHtml(bm.ref)}">✕</button>`;

      div.querySelector('.bookmark-ref').addEventListener('click', () => onBookmarkItemClick(bm.ref));
      div.querySelector('.bookmark-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        toggleBookmark(bm.ref).then(() => renderBookmarksList());
      });

      section.appendChild(div);
    }
    listEl.appendChild(section);
  }
}

/**
 * Navigate to a ref from the bookmarks panel.
 * @param {string} ref
 */
function onBookmarkItemClick(ref) {
  closeBookmarksPanel();
  if (typeof loadChapter === 'function') {
    loadChapter(ref);
  }
}

// =============================================================================
// 7. READING HISTORY
// =============================================================================

/**
 * Record a ref visit silently; used by the reader on every chapter load.
 * @param {string} ref
 */
async function logHistory(ref) {
  if (!authToken) return;
  try {
    await authFetch('/api/history', {
      method: 'POST',
      body: JSON.stringify({ ref }),
    });
  } catch (_) {
    // Silent fail — history is non-critical
  }
}

function openHistoryPanel() {
  const panel = document.getElementById('history-panel');
  if (panel) {
    panel.classList.add('open');
    loadHistory();
  }
}

function closeHistoryPanel() {
  const panel = document.getElementById('history-panel');
  if (panel) panel.classList.remove('open');
}

/**
 * Fetch and render reading history into .history-list.
 */
async function loadHistory() {
  const listEl = document.querySelector('.history-list');
  if (!listEl) return;

  listEl.innerHTML = '<div class="history-loading">Loading history…</div>';

  try {
    const res = await authFetch('/api/history');
    if (!res.ok) throw new Error('Failed to load history');
    const history = await res.json();

    if (!history.length) {
      listEl.innerHTML = '<div class="history-empty">No reading history yet.</div>';
      return;
    }

    listEl.innerHTML = '';
    for (const entry of history) {
      const div = document.createElement('div');
      div.className = 'history-item';

      const ts = entry.visited_at || entry.created_at;
      const tsSeconds = ts
        ? Math.floor(new Date(ts).getTime() / 1000)
        : null;

      div.innerHTML = `
        <span class="history-ref">${_escHtml(entry.ref)}</span>
        ${tsSeconds ? `<span class="history-time">${relativeTime(tsSeconds)}</span>` : ''}`;

      div.addEventListener('click', () => {
        closeHistoryPanel();
        if (typeof loadChapter === 'function') loadChapter(entry.ref);
      });

      listEl.appendChild(div);
    }
  } catch (err) {
    listEl.innerHTML = '<div class="history-error">Could not load history.</div>';
    console.error('loadHistory:', err);
  }
}

/**
 * Convert a Unix timestamp (seconds) into a human-readable relative string.
 * @param {number} unixSeconds
 * @returns {string}
 */
function relativeTime(unixSeconds) {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const diff = nowSeconds - unixSeconds;

  if (diff < 60) return 'just now';
  if (diff < 3600) {
    const m = Math.floor(diff / 60);
    return `${m} minute${m !== 1 ? 's' : ''} ago`;
  }
  if (diff < 86400) {
    const h = Math.floor(diff / 3600);
    return `${h} hour${h !== 1 ? 's' : ''} ago`;
  }
  if (diff < 86400 * 30) {
    const d = Math.floor(diff / 86400);
    return `${d} day${d !== 1 ? 's' : ''} ago`;
  }
  if (diff < 86400 * 365) {
    const mo = Math.floor(diff / (86400 * 30));
    return `${mo} month${mo !== 1 ? 's' : ''} ago`;
  }
  const y = Math.floor(diff / (86400 * 365));
  return `${y} year${y !== 1 ? 's' : ''} ago`;
}

// =============================================================================
// 8. NOTES (user-scoped)
// =============================================================================

/**
 * Load the saved note for a ref and populate the notes textarea.
 * @param {string} ref
 */
async function loadNote(ref) {
  const textarea = document.querySelector('#tab-notes textarea');
  const unauthMsg = document.querySelector('#tab-notes .notes-unauth');

  if (!authToken) {
    if (textarea) textarea.style.display = 'none';
    if (unauthMsg) {
      unauthMsg.textContent = 'Sign in to save notes.';
      unauthMsg.style.display = '';
    }
    return;
  }

  if (unauthMsg) unauthMsg.style.display = 'none';
  if (textarea) textarea.style.display = '';

  try {
    const encodedRef = encodeURIComponent(ref);
    const res = await authFetch(`/api/note/${encodedRef}`);
    if (res.ok) {
      const data = await res.json();
      if (textarea) textarea.value = data.body || '';
    } else if (res.status === 404) {
      if (textarea) textarea.value = '';
    }
  } catch (err) {
    console.warn('loadNote:', err);
  }
}

/**
 * Persist a note for the given ref.
 * @param {string} ref
 * @param {string} body
 */
async function saveNote(ref, body) {
  if (!authToken) {
    showToast('Sign in to save notes.', 'error');
    return;
  }
  try {
    const encodedRef = encodeURIComponent(ref);
    const res = await authFetch(`/api/note/${encodedRef}`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    });
    if (res.ok) {
      showToast('Note saved.', 'success');
    } else {
      showToast('Could not save note.', 'error');
    }
  } catch (err) {
    showToast('Could not save note.', 'error');
    console.error('saveNote:', err);
  }
}

// =============================================================================
// 9. ADMIN — USER MANAGEMENT
// =============================================================================

/**
 * Render and open the admin user-management modal.
 * No-ops if the current user is not an admin.
 */
async function showAdminPanel() {
  if (!isAdmin()) return;

  let modal = document.getElementById('admin-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'admin-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-dialog admin-dialog">
        <div class="modal-header">
          <h2>User Management</h2>
          <button class="modal-close" id="admin-modal-close">✕</button>
        </div>
        <div class="modal-body">
          <div id="admin-user-list">Loading users…</div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector('#admin-modal-close').addEventListener('click', () => {
      modal.style.display = 'none';
    });
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.style.display = 'none';
    });
  }

  modal.style.display = 'flex';
  _loadAdminUsers();
}

async function _loadAdminUsers() {
  const container = document.getElementById('admin-user-list');
  if (!container) return;

  try {
    const res = await authFetch('/api/admin/users');
    if (!res.ok) throw new Error('Unauthorized or not found');
    const users = await res.json();

    if (!users.length) {
      container.innerHTML = '<p>No users found.</p>';
      return;
    }

    container.innerHTML = '';
    const table = document.createElement('table');
    table.className = 'admin-user-table';
    table.innerHTML = `
      <thead>
        <tr>
          <th>Username</th><th>Display Name</th><th>Role</th><th>Actions</th>
        </tr>
      </thead>`;

    const tbody = document.createElement('tbody');
    for (const user of users) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${_escHtml(user.username)}</td>
        <td>${_escHtml(user.display_name || '')}</td>
        <td>${_escHtml(user.role || 'user')}</td>
        <td>
          <button class="btn-sm admin-reset-pw" data-uid="${user.id}" data-uname="${_escHtml(user.username)}">
            Reset password
          </button>
        </td>`;

      tr.querySelector('.admin-reset-pw').addEventListener('click', async (e) => {
        const uid = e.currentTarget.dataset.uid;
        const uname = e.currentTarget.dataset.uname;
        _handleAdminResetPassword(uid, uname, e.currentTarget);
      });

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    container.appendChild(table);
  } catch (err) {
    container.innerHTML = `<p class="admin-error">Could not load users: ${_escHtml(err.message)}</p>`;
    console.error('_loadAdminUsers:', err);
  }
}

async function _handleAdminResetPassword(uid, username, btn) {
  const tempPw = _generateTempPassword();
  const confirmed = confirm(`Reset password for "${username}"?\\nTemp password: ${tempPw}\\n\\nSave this before confirming.`);
  if (!confirmed) return;

  try {
    const res = await authFetch(`/api/admin/users/${uid}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password: tempPw }),
    });
    if (res.ok) {
      showToast(`Password reset for ${username}. Temp: ${tempPw}`, 'success');
    } else {
      showToast('Password reset failed.', 'error');
    }
  } catch (err) {
    showToast('Password reset failed.', 'error');
    console.error('_handleAdminResetPassword:', err);
  }
}

/**
 * Generate a random temporary password.
 * @returns {string}
 */
function _generateTempPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$';
  return Array.from({ length: 14 }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
}

// =============================================================================
// 10. TOAST NOTIFICATIONS
// =============================================================================

const _TOAST_COLORS = {
  info: '#D4AF37',    // gold
  success: '#4CAF50', // green
  error: '#E53E3E',   // red
  warning: '#F6AD55', // orange
};

/**
 * Display a non-blocking toast message that auto-dismisses after 3 seconds.
 * @param {string} message
 * @param {'info'|'success'|'error'|'warning'} [type='info']
 */
function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-atomic', 'false');
    container.style.cssText = [
      'position:fixed',
      'bottom:1.5rem',
      'right:1.5rem',
      'z-index:9999',
      'display:flex',
      'flex-direction:column',
      'gap:0.5rem',
      'pointer-events:none',
    ].join(';');
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', 'status');
  toast.style.cssText = [
    'background:#1a1a2e',
    `border-left:4px solid ${_TOAST_COLORS[type] || _TOAST_COLORS.info}`,
    'color:#f0e6d3',
    'padding:0.75rem 1.25rem',
    'border-radius:6px',
    'font-size:0.95rem',
    'max-width:320px',
    'box-shadow:0 4px 12px rgba(0,0,0,0.4)',
    'opacity:0',
    'transform:translateX(1rem)',
    'transition:opacity 0.2s ease, transform 0.2s ease',
    'pointer-events:auto',
    'cursor:pointer',
  ].join(';');
  toast.textContent = message;

  toast.addEventListener('click', () => _dismissToast(toast));
  container.appendChild(toast);

  // Trigger entry animation
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(0)';
    });
  });

  const timer = setTimeout(() => _dismissToast(toast), 3000);
  toast._dismissTimer = timer;
}

function _dismissToast(toast) {
  clearTimeout(toast._dismissTimer);
  toast.style.opacity = '0';
  toast.style.transform = 'translateX(1rem)';
  toast.addEventListener('transitionend', () => toast.remove(), { once: true });
}

// =============================================================================
// UTILITIES
// =============================================================================

/**
 * Escape a string for safe insertion into innerHTML.
 * @param {string} str
 * @returns {string}
 */
function _escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// =============================================================================
// 11. INIT HOOK
// =============================================================================

/**
 * Primary entry point — called once by the page on DOMContentLoaded.
 * Wires up all auth-related event listeners, checks session, and starts
 * the auto-save interval.
 */
async function initAuth() {
  // --- Auth form event listeners ---
  const loginForm = document.getElementById('login-form');
  if (loginForm) loginForm.addEventListener('submit', handleLogin);

  const registerForm = document.getElementById('register-form');
  if (registerForm) registerForm.addEventListener('submit', handleRegister);

  document.querySelectorAll('.auth-toggle').forEach(el => {
    el.addEventListener('click', (e) => { e.preventDefault(); toggleAuthMode(); });
  });

  // --- User chip ---
  const userChip = document.querySelector('.user-chip');
  if (userChip) userChip.addEventListener('click', toggleUserDropdown);

  document.querySelectorAll('.sign-out-btn').forEach(el => {
    el.addEventListener('click', handleSignOut);
  });

  // --- Dropdown menu items ---
  const sessionsMenuBtn = document.querySelector('.menu-sessions');
  if (sessionsMenuBtn) sessionsMenuBtn.addEventListener('click', openSessionsPanel);

  const bookmarksMenuBtn = document.querySelector('.menu-bookmarks');
  if (bookmarksMenuBtn) bookmarksMenuBtn.addEventListener('click', openBookmarksPanel);

  const historyMenuBtn = document.querySelector('.menu-history');
  if (historyMenuBtn) historyMenuBtn.addEventListener('click', openHistoryPanel);

  const adminMenuBtn = document.querySelector('.admin-item');
  if (adminMenuBtn) adminMenuBtn.addEventListener('click', showAdminPanel);

  // --- Panel close buttons ---
  const sessionsClose = document.querySelector('#sessions-panel .panel-close');
  if (sessionsClose) sessionsClose.addEventListener('click', closeSessionsPanel);

  const bookmarksClose = document.querySelector('#bookmarks-panel .panel-close');
  if (bookmarksClose) bookmarksClose.addEventListener('click', closeBookmarksPanel);

  const historyClose = document.querySelector('#history-panel .panel-close');
  if (historyClose) historyClose.addEventListener('click', closeHistoryPanel);

  // --- Save session button ---
  const saveSessionBtn = document.getElementById('save-session-btn');
  if (saveSessionBtn) {
    saveSessionBtn.addEventListener('click', () => saveSession());
  }

  // --- Notes auto-save (debounced) ---
  const notesArea = document.querySelector('#tab-notes textarea');
  if (notesArea) {
    let _notesDebounce = null;
    notesArea.addEventListener('input', () => {
      clearTimeout(_notesDebounce);
      _notesDebounce = setTimeout(() => {
        if (_activeRef) saveNote(_activeRef, notesArea.value);
      }, 1500);
    });
  }

  // --- Ensure auth inputs stay >= 16px to prevent iOS zoom ---
  document.querySelectorAll('#login-form input, #register-form input').forEach(input => {
    if (!input.style.fontSize) {
      input.style.fontSize = '16px';
    }
  });

  // --- Auto-save interval: every 60 seconds ---
  if (autoSaveInterval) clearInterval(autoSaveInterval);
  autoSaveInterval = setInterval(autoSaveSession, 60_000);

  // --- Check auth last so the UI is wired before any redirect ---
  await checkAuth();
}

// Global error handler — surfaces JS crashes as a visible banner.
window.onerror = function(msg, src, line, col, err) {
  const b = document.getElementById('js-error-banner');
  if (b) { b.textContent = 'JS Error: ' + msg + ' (' + (src||'').split('/').pop() + ':' + line + ')'; b.style.display = 'block'; }
  console.error('[bible] uncaught:', msg, src, line, col, err);
};
window.onunhandledrejection = function(e) {
  const b = document.getElementById('js-error-banner');
  if (b) { b.textContent = 'Unhandled promise: ' + (e.reason?.message || e.reason || 'unknown'); b.style.display = 'block'; }
  console.error('[bible] unhandled rejection:', e.reason);
};

// Kick everything off when the DOM is ready.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAuth);
} else {
  initAuth();
}

</script>

<script>
/* ============================================================
   part2_reader.js — Bible Reader UI Logic
   wn-bible-01 · Christ Pillar · Wittycomp Lab
   ============================================================ */

'use strict';

// ── Book Data ──────────────────────────────────────────────────────────────

const OT_BOOKS = [
  { name: 'Genesis',        chapters: 50 },
  { name: 'Exodus',         chapters: 40 },
  { name: 'Leviticus',      chapters: 27 },
  { name: 'Numbers',        chapters: 36 },
  { name: 'Deuteronomy',    chapters: 34 },
  { name: 'Joshua',         chapters: 24 },
  { name: 'Judges',         chapters: 21 },
  { name: 'Ruth',           chapters: 4  },
  { name: '1 Samuel',       chapters: 31 },
  { name: '2 Samuel',       chapters: 24 },
  { name: '1 Kings',        chapters: 22 },
  { name: '2 Kings',        chapters: 25 },
  { name: '1 Chronicles',   chapters: 29 },
  { name: '2 Chronicles',   chapters: 36 },
  { name: 'Ezra',           chapters: 10 },
  { name: 'Nehemiah',       chapters: 13 },
  { name: 'Esther',         chapters: 10 },
  { name: 'Job',            chapters: 42 },
  { name: 'Psalms',         chapters: 150 },
  { name: 'Proverbs',       chapters: 31 },
  { name: 'Ecclesiastes',   chapters: 12 },
  { name: 'Song of Solomon', chapters: 8 },
  { name: 'Isaiah',         chapters: 66 },
  { name: 'Jeremiah',       chapters: 52 },
  { name: 'Lamentations',   chapters: 5  },
  { name: 'Ezekiel',        chapters: 48 },
  { name: 'Daniel',         chapters: 12 },
  { name: 'Hosea',          chapters: 14 },
  { name: 'Joel',           chapters: 3  },
  { name: 'Amos',           chapters: 9  },
  { name: 'Obadiah',        chapters: 1  },
  { name: 'Jonah',          chapters: 4  },
  { name: 'Micah',          chapters: 7  },
  { name: 'Nahum',          chapters: 3  },
  { name: 'Habakkuk',       chapters: 3  },
  { name: 'Zephaniah',      chapters: 3  },
  { name: 'Haggai',         chapters: 2  },
  { name: 'Zechariah',      chapters: 14 },
  { name: 'Malachi',        chapters: 4  },
];

const NT_BOOKS = [
  { name: 'Matthew',         chapters: 28 },
  { name: 'Mark',            chapters: 16 },
  { name: 'Luke',            chapters: 24 },
  { name: 'John',            chapters: 21 },
  { name: 'Acts',            chapters: 28 },
  { name: 'Romans',          chapters: 16 },
  { name: '1 Corinthians',   chapters: 16 },
  { name: '2 Corinthians',   chapters: 13 },
  { name: 'Galatians',       chapters: 6  },
  { name: 'Ephesians',       chapters: 6  },
  { name: 'Philippians',     chapters: 4  },
  { name: 'Colossians',      chapters: 4  },
  { name: '1 Thessalonians', chapters: 5  },
  { name: '2 Thessalonians', chapters: 3  },
  { name: '1 Timothy',       chapters: 6  },
  { name: '2 Timothy',       chapters: 4  },
  { name: 'Titus',           chapters: 3  },
  { name: 'Philemon',        chapters: 1  },
  { name: 'Hebrews',         chapters: 13 },
  { name: 'James',           chapters: 5  },
  { name: '1 Peter',         chapters: 5  },
  { name: '2 Peter',         chapters: 3  },
  { name: '1 John',          chapters: 5  },
  { name: '2 John',          chapters: 1  },
  { name: '3 John',          chapters: 1  },
  { name: 'Jude',            chapters: 1  },
  { name: 'Revelation',      chapters: 22 },
];

const ALL_BOOKS = [...OT_BOOKS, ...NT_BOOKS];

const BIBLICAL_PLACES = [
  { name: 'Jerusalem',   lat: 31.7683,  lng: 35.2137,  refs: ['Luke 2:22', 'Matt 21:10'] },
  { name: 'Bethlehem',   lat: 31.7054,  lng: 35.2024,  refs: ['Luke 2:4',  'Mic 5:2']    },
  { name: 'Nazareth',    lat: 32.6996,  lng: 35.3035,  refs: ['Luke 1:26', 'Matt 2:23']  },
  { name: 'Capernaum',   lat: 32.8808,  lng: 35.5752,  refs: ['Matt 4:13', 'John 6:17']  },
  { name: 'Jordan River',lat: 31.8400,  lng: 35.5400,  refs: ['Matt 3:13', 'Josh 1:2']   },
  { name: 'Sea of Galilee', lat: 32.8208, lng: 35.5825, refs: ['Matt 4:18', 'John 6:1'] },
  { name: 'Jericho',     lat: 31.8571,  lng: 35.4610,  refs: ['Luke 19:1', 'Josh 6:1']   },
  { name: 'Bethany',     lat: 31.7700,  lng: 35.2600,  refs: ['John 11:1', 'Luke 10:38'] },
  { name: 'Sinai',       lat: 28.5395,  lng: 33.9756,  refs: ['Exod 19:1', 'Gal 4:25']   },
  { name: 'Babylon',     lat: 32.5420,  lng: 44.4210,  refs: ['Isa 13:1',  '2 Kgs 20:14']},
  { name: 'Egypt',       lat: 26.8200,  lng: 30.8025,  refs: ['Gen 12:10', 'Matt 2:14']  },
  { name: 'Athens',      lat: 37.9838,  lng: 23.7275,  refs: ['Acts 17:15','1 Thess 3:1']},
  { name: 'Rome',        lat: 41.9028,  lng: 12.4964,  refs: ['Acts 28:14','Rom 1:7']    },
  { name: 'Antioch',     lat: 36.2021,  lng: 36.1600,  refs: ['Acts 11:26','Gal 2:11']   },
  { name: 'Ephesus',     lat: 37.9390,  lng: 27.3417,  refs: ['Acts 19:1', 'Rev 2:1']    },
  { name: 'Corinth',     lat: 37.9060,  lng: 22.8780,  refs: ['Acts 18:1', '1 Cor 1:2']  },
  { name: 'Thessalonica',lat: 40.6401,  lng: 22.9444,  refs: ['Acts 17:1', '1 Thess 1:1']},
];

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  currentBook:    'John',
  currentChapter: 3,
  currentVerse:   null,
  currentTranslation: 'KJV',
  parallelTranslation: null,
  parallelMode:   false,
  activeTab:      'crossrefs',
  mapInitialized: false,
  leafletMap:     null,
  mapMarkers:     [],
  sidebarOpen:    false,
  bottomSheetOpen: false,
  expandedBooks:  new Set(),
  isDesktop:      () => window.innerWidth >= 768,
};

// ── DOM helpers ────────────────────────────────────────────────────────────

const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

// ── 1. BOOK NAVIGATOR ──────────────────────────────────────────────────────

function buildBookNav() {
  const sidebar = $('#sidebar .book-list') || $('#sidebar');
  if (!sidebar) return;
  sidebar.innerHTML = '';

  const buildSection = (title, books) => {
    const section = el('div', { class: 'nav-section' });
    const header  = el('div', { class: 'nav-section-header' }, title);
    section.appendChild(header);

    for (const book of books) {
      const bookEl = el('div', { class: 'nav-book' });
      const nameEl = el('div', {
        class: 'nav-book-name',
        onclick: () => toggleBook(book.name),
        'data-book': book.name,
      }, book.name);
      bookEl.appendChild(nameEl);

      const chList = el('div', { class: 'nav-chapter-list hidden', 'data-chapters-for': book.name });
      for (let c = 1; c <= book.chapters; c++) {
        const chEl = el('span', {
          class: 'nav-chapter-num',
          onclick: () => loadChapter(book.name, c),
          'data-book': book.name,
          'data-chapter': c,
        }, String(c));
        chList.appendChild(chEl);
      }
      bookEl.appendChild(chList);
      section.appendChild(bookEl);
    }
    return section;
  };

  sidebar.appendChild(buildSection('Old Testament', OT_BOOKS));
  sidebar.appendChild(buildSection('New Testament', NT_BOOKS));
  highlightActiveNav();
}

function toggleBook(bookName) {
  const chList = $(`[data-chapters-for="${CSS.escape(bookName)}"]`);
  if (!chList) return;

  if (state.expandedBooks.has(bookName)) {
    state.expandedBooks.delete(bookName);
    chList.classList.add('hidden');
  } else {
    state.expandedBooks.add(bookName);
    chList.classList.remove('hidden');
  }
}

function highlightActiveNav() {
  $$('.nav-book-name.active').forEach(n => n.classList.remove('active'));
  $$('.nav-chapter-num.active').forEach(n => n.classList.remove('active'));

  const bookEl = $(`[data-book="${CSS.escape(state.currentBook)}"].nav-book-name`);
  if (bookEl) {
    bookEl.classList.add('active');
    // auto-expand active book
    if (!state.expandedBooks.has(state.currentBook)) {
      state.expandedBooks.add(state.currentBook);
      const chList = $(`[data-chapters-for="${CSS.escape(state.currentBook)}"]`);
      if (chList) chList.classList.remove('hidden');
    }
    // scroll into view within sidebar
    bookEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  const chEl = $(`[data-book="${CSS.escape(state.currentBook)}"][data-chapter="${state.currentChapter}"].nav-chapter-num`);
  if (chEl) chEl.classList.add('active');
}

// ── 2. CHAPTER LOADER ─────────────────────────────────────────────────────

async function loadChapter(book, chapter, verseHighlight = null) {
  state.currentBook    = book;
  state.currentChapter = chapter;
  state.currentVerse   = verseHighlight;

  // Update URL hash
  const hash = verseHighlight
    ? `#${book.replace(/\\s+/g, '-')}-${chapter}:${verseHighlight}`
    : `#${book.replace(/\\s+/g, '-')}-${chapter}`;
  history.replaceState(null, '', hash);

  // Update chapter header
  const header = $('#chapter-header') || $('#chapter-title');
  if (header) header.textContent = `${book} ${chapter}`;

  // Clear content
  const content = $('#chapter-content');
  if (!content) return;
  content.innerHTML = '<div class="loading-spinner">Loading…</div>';

  try {
    const ref = encodeURIComponent(`${book} ${chapter}`);
    const verseUrl = `/api/verse?ref=${ref}&translation=${encodeURIComponent(state.currentTranslation)}`;
    const [verseData] = await Promise.all([apiFetch(verseUrl)]);

    let taggedData = null;
    if (state.currentTranslation === 'KJV') {
      taggedData = await apiFetch(`/api/verse/tagged?ref=${ref}`).catch(() => null);
    }

    content.innerHTML = '';
    const verses = normalizeVerses(verseData);
    for (const v of verses) {
      const tagged = taggedData ? getTaggedWords(taggedData, v.num) : null;
      content.appendChild(renderVerse(v.num, v.text, tagged));
    }

    // Parallel column
    if (state.parallelMode && state.parallelTranslation) {
      await loadParallelColumn(book, chapter);
    }

    highlightActiveNav();

    // Scroll to highlighted verse
    if (verseHighlight) {
      const verseEl = $(`[data-verse="${verseHighlight}"]`, content);
      if (verseEl) {
        setTimeout(() => verseEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
        verseEl.classList.add('highlighted');
      }
    } else {
      content.scrollTop = 0;
    }

    // Update prev/next buttons
    updateChapterNav();
  } catch (err) {
    content.innerHTML = `<p class="error-msg">Failed to load chapter: ${escHtml(err.message)}</p>`;
  }

  // Silent history POST
  postHistory(`${book} ${chapter}`);
}

function normalizeVerses(data) {
  const norm = v => ({ ...v, num: v.num ?? v.verse });
  if (Array.isArray(data)) return data.map(norm);
  if (data && data.verses) return data.verses.map(norm);
  if (data && data.text) return [{ num: 1, text: data.text }];
  return [];
}

function getTaggedWords(taggedData, verseNum) {
  if (!taggedData) return null;
  const verses = taggedData.verses || taggedData;
  if (Array.isArray(verses)) {
    const v = verses.find(v => v.num === verseNum || v.verse === verseNum);
    return v ? (v.words || v.tagged) : null;
  }
  return null;
}

function renderVerse(verseNum, text, taggedWords = null) {
  const row = el('div', { class: 'verse-row', 'data-verse': verseNum });

  const numEl = el('span', {
    class: 'verse-num',
    onclick: () => {
      const ref = `${state.currentBook} ${state.currentChapter}:${verseNum}`;
      selectVerse(ref);
    },
  }, String(verseNum));
  row.appendChild(numEl);

  const textEl = el('span', { class: 'verse-text' });
  if (taggedWords && Array.isArray(taggedWords) && taggedWords.length > 0) {
    for (const word of taggedWords) {
      const wordStr  = word.word || word.text || '';
      const strongs  = word.strongs || word.strong || '';
      const morph    = word.morph || '';
      const span = el('span', {
        class: `word${strongs ? ' has-strongs' : ''}`,
        'data-strongs': strongs,
        'data-morph': morph,
        onclick: strongs ? () => onWordClick(strongs) : null,
        title: strongs || undefined,
      }, wordStr + ' ');
      textEl.appendChild(span);
    }
  } else {
    textEl.textContent = text;
  }
  row.appendChild(textEl);
  return row;
}

function prevChapter() {
  const bookData = ALL_BOOKS.find(b => b.name === state.currentBook);
  if (!bookData) return;

  if (state.currentChapter > 1) {
    loadChapter(state.currentBook, state.currentChapter - 1);
  } else {
    const idx = ALL_BOOKS.indexOf(bookData);
    if (idx > 0) {
      const prev = ALL_BOOKS[idx - 1];
      loadChapter(prev.name, prev.chapters);
    }
  }
}

function nextChapter() {
  const bookData = ALL_BOOKS.find(b => b.name === state.currentBook);
  if (!bookData) return;

  if (state.currentChapter < bookData.chapters) {
    loadChapter(state.currentBook, state.currentChapter + 1);
  } else {
    const idx = ALL_BOOKS.indexOf(bookData);
    if (idx < ALL_BOOKS.length - 1) {
      loadChapter(ALL_BOOKS[idx + 1].name, 1);
    }
  }
}

function updateChapterNav() {
  const prevBtn = $('#btn-prev-chapter');
  const nextBtn = $('#btn-next-chapter');
  if (!prevBtn || !nextBtn) return;

  const bookData = ALL_BOOKS.find(b => b.name === state.currentBook);
  const isFirst  = ALL_BOOKS[0].name === state.currentBook && state.currentChapter === 1;
  const isLast   = ALL_BOOKS[ALL_BOOKS.length - 1].name === state.currentBook
                   && bookData && state.currentChapter === bookData.chapters;

  prevBtn.disabled = isFirst;
  nextBtn.disabled = isLast;
}

// ── 3. VERSE SELECTION ─────────────────────────────────────────────────────

async function selectVerse(ref) {
  // Highlight row
  $$('.verse-row.selected').forEach(r => r.classList.remove('selected'));
  const match = ref.match(/:(\\d+)$/);
  if (match) {
    const verseEl = $(`[data-verse="${match[1]}"]`);
    if (verseEl) verseEl.classList.add('selected');
  }

  state.currentVerse = ref;

  // Update URL
  const urlRef = ref.replace(/\\s+/g, '-');
  history.replaceState(null, '', `#${urlRef}`);

  // Load cross-refs
  await loadCrossRefs(ref);
  switchTab('crossrefs');

  // Mobile: open bottom sheet
  if (!state.isDesktop()) openBottomSheet();
}

async function loadCrossRefs(ref) {
  const container = $('#tab-crossrefs');
  if (!container) return;
  container.innerHTML = '<span class="loading-text">Loading cross-references…</span>';

  try {
    const data = await apiFetch(`/api/crossrefs?ref=${encodeURIComponent(ref)}`);
    container.innerHTML = '';

    const refs = data.crossrefs || data.refs || data || [];
    if (refs.length === 0) {
      container.innerHTML = '<p class="empty-state">No cross-references found.</p>';
      return;
    }

    const header = el('p', { class: 'xref-header' }, `Cross-references for ${ref}`);
    container.appendChild(header);

    const chipList = el('div', { class: 'xref-chip-list' });
    for (const xref of refs) {
      const xrefRef  = xref.ref || xref.reference || xref;
      const xrefText = xref.text || '';
      const chip = el('button', {
        class: 'xref-chip',
        title: xrefText,
        onclick: () => navigateToRef(xrefRef),
      }, String(xrefRef));
      chipList.appendChild(chip);
    }
    container.appendChild(chipList);
  } catch (err) {
    container.innerHTML = `<p class="error-msg">Could not load cross-references.</p>`;
  }
}

function navigateToRef(ref) {
  const parsed = parseRef(ref);
  if (parsed) {
    loadChapter(parsed.book, parsed.chapter, parsed.verse);
  }
}

// ── 4. STRONG'S LOOKUP ────────────────────────────────────────────────────

async function onWordClick(strongsNum) {
  if (!strongsNum) return;
  switchTab('strongs');
  const container = $('#tab-strongs');
  if (!container) return;
  container.innerHTML = '<span class="loading-text">Loading…</span>';

  try {
    const data = await apiFetch(`/api/strongs/${encodeURIComponent(strongsNum)}`);
    renderStrongsCard(data, container);
  } catch (err) {
    container.innerHTML = `<p class="error-msg">Strong's entry not found for ${escHtml(strongsNum)}.</p>`;
  }
}

function renderStrongsCard(data, container) {
  if (!container) container = $('#tab-strongs');
  if (!container) return;
  container.innerHTML = '';

  const card = el('div', { class: 'strongs-card' });

  const num      = data.number || data.strongs || '';
  const original = data.original || data.lemma || data.word || '';
  const translit = data.transliteration || data.translit || '';
  const definition = data.definition || data.meaning || '';
  const usage    = data.kjv_usage || data.usage || data.appears || '';
  const pronunciation = data.pronunciation || data.phonetic || '';

  card.appendChild(el('div', { class: 'strongs-number' }, num));
  if (original)  card.appendChild(el('div', { class: 'strongs-original' }, original));
  if (translit)  card.appendChild(el('div', { class: 'strongs-translit' }, `(${translit})`));
  if (pronunciation) card.appendChild(el('div', { class: 'strongs-pronunciation' }, pronunciation));
  if (definition) {
    card.appendChild(el('div', { class: 'strongs-label' }, 'Definition'));
    card.appendChild(el('div', { class: 'strongs-definition' }, definition));
  }
  if (usage) {
    card.appendChild(el('div', { class: 'strongs-label' }, 'KJV Usage'));
    card.appendChild(el('div', { class: 'strongs-usage' }, usage));
  }

  container.appendChild(card);
}

// ── 5. INTERLINEAR ─────────────────────────────────────────────────────────

async function loadInterlinear(ref) {
  const container = $('#tab-interlinear');
  if (!container) return;
  container.innerHTML = '<span class="loading-text">Loading interlinear…</span>';

  try {
    const data = await apiFetch(`/api/interlinear?ref=${encodeURIComponent(ref || currentRef())}`);
    renderInterlinear(data, container);
  } catch (err) {
    container.innerHTML = `<p class="error-msg">Interlinear data unavailable.</p>`;
  }
}

function renderInterlinear(data, container) {
  container.innerHTML = '';
  const words = data.words || data.interlinear || data || [];
  if (words.length === 0) {
    container.innerHTML = '<p class="empty-state">No interlinear data.</p>';
    return;
  }

  const table = el('table', { class: 'interlinear-table' });
  const thead = el('thead');
  thead.appendChild(el('tr', {},
    el('th', {}, 'English'),
    el('th', {}, 'Original'),
    el('th', {}, 'Transliteration'),
    el('th', {}, "Strong's"),
    el('th', {}, 'Morphology'),
  ));
  table.appendChild(thead);

  const tbody = el('tbody');
  for (const word of words) {
    const strongsNum = word.strongs || word.strong || '';
    const tr = el('tr', {},
      el('td', { class: 'il-english'  }, word.english  || word.text || ''),
      el('td', { class: 'il-original' }, word.original || word.lemma || ''),
      el('td', { class: 'il-translit' }, word.transliteration || word.translit || ''),
      el('td', { class: 'il-strongs'  },
        strongsNum
          ? el('button', { class: 'strongs-link', onclick: () => onWordClick(strongsNum) }, strongsNum)
          : ''
      ),
      el('td', { class: 'il-morph'    }, word.morphology || word.morph || ''),
    );
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);

  const wrapper = el('div', { class: 'interlinear-wrapper' });
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}

// ── 6. COMMENTARY ─────────────────────────────────────────────────────────

async function loadCommentary(ref) {
  const container = $('#tab-commentary');
  if (!container) return;
  container.innerHTML = '<span class="loading-text">Loading commentary…</span>';

  try {
    const data = await apiFetch(`/api/commentary?ref=${encodeURIComponent(ref || currentRef())}`);
    renderCommentary(data, container);
  } catch (err) {
    container.innerHTML = `<p class="error-msg">Commentary unavailable.</p>`;
  }
}

function renderCommentary(data, container) {
  container.innerHTML = '';
  const blocks = data.commentary || data.blocks || (Array.isArray(data) ? data : [data]);

  if (blocks.length === 0) {
    container.innerHTML = '<p class="empty-state">No commentary found.</p>';
    return;
  }

  for (const block of blocks) {
    if (!block) continue;
    const section = el('div', { class: 'commentary-section' });
    const source  = block.source || block.author || block.title || 'Commentary';
    const text    = block.text   || block.body   || block.content || String(block);

    const summaryEl = el('summary', { class: 'commentary-source' }, source);
    const textEl    = el('div',    { class: 'commentary-text'   }, text);
    const details   = el('details', { class: 'commentary-details', open: blocks.length === 1 });
    details.appendChild(summaryEl);
    details.appendChild(textEl);
    section.appendChild(details);
    container.appendChild(section);
  }
}

// ── 7. MAPS ────────────────────────────────────────────────────────────────

function initMap() {
  if (state.mapInitialized) {
    refreshMapMarkers();
    return;
  }

  const mapContainer = document.getElementById('tab-maps');
  if (!mapContainer) return;

  // Leaflet must be loaded in the page — check before init
  if (typeof L === 'undefined') {
    mapContainer.innerHTML = '<p class="error-msg">Leaflet not loaded.</p>';
    return;
  }

  // Clear any previous content, create map div
  mapContainer.innerHTML = '';
  const mapDiv = el('div', { id: 'leaflet-map', style: 'width:100%;height:100%;min-height:320px;' });
  mapContainer.appendChild(mapDiv);

  state.leafletMap = L.map('leaflet-map').setView([31.5, 35.0], 6);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 18,
  }).addTo(state.leafletMap);

  state.mapInitialized = true;
  refreshMapMarkers();
}

function refreshMapMarkers() {
  if (!state.leafletMap) return;

  // Clear existing markers
  for (const marker of state.mapMarkers) marker.remove();
  state.mapMarkers = [];

  const ref = currentRef();

  // Async: fetch places for current passage, fall back to hardcoded set
  apiFetch(`/api/places?ref=${encodeURIComponent(ref)}`)
    .then(data => {
      const places = (data.places || data || []).length > 0
        ? (data.places || data)
        : BIBLICAL_PLACES;
      renderMapMarkers(places);
    })
    .catch(() => renderMapMarkers(BIBLICAL_PLACES));
}

function renderMapMarkers(places) {
  if (!state.leafletMap || !places) return;
  for (const place of places) {
    if (place.lat == null || place.lng == null) continue;
    const popup  = `<strong>${escHtml(place.name)}</strong>` +
      (place.refs ? `<br><small>${place.refs.join(', ')}</small>` : '');
    const marker = L.marker([place.lat, place.lng])
      .addTo(state.leafletMap)
      .bindPopup(popup);
    state.mapMarkers.push(marker);
  }
}

// ── 8. PANEL / TAB MANAGEMENT ─────────────────────────────────────────────

function switchTab(tabName) {
  state.activeTab = tabName;

  $$('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  $$('.tab-content').forEach(pane => {
    pane.classList.toggle('hidden', pane.id !== `tab-${tabName}`);
  });

  // Lazy-init map on first open
  if (tabName === 'maps') initMap();

  // Load data for newly-visible tab if a verse is selected
  if (state.currentVerse) {
    if (tabName === 'interlinear') loadInterlinear(state.currentVerse);
    if (tabName === 'commentary')  loadCommentary(state.currentVerse);
  }
}

function openBottomSheet() {
  const sheet = $('#bottom-sheet');
  if (!sheet) return;
  sheet.classList.add('open');
  state.bottomSheetOpen = true;
  document.body.classList.add('sheet-open');
}

function closeBottomSheet() {
  const sheet = $('#bottom-sheet');
  if (!sheet) return;
  sheet.classList.remove('open');
  state.bottomSheetOpen = false;
  document.body.classList.remove('sheet-open');
}

function toggleSidebar() {
  const sidebar = $('#sidebar');
  if (!sidebar) return;

  if (state.isDesktop()) {
    sidebar.classList.toggle('collapsed');
    state.sidebarOpen = !sidebar.classList.contains('collapsed');
  } else {
    sidebar.classList.toggle('drawer-open');
    state.sidebarOpen = sidebar.classList.contains('drawer-open');
    const overlay = $('#sidebar-overlay');
    if (overlay) overlay.classList.toggle('visible', state.sidebarOpen);
  }
}

function handleResize() {
  if (state.isDesktop()) {
    // Close mobile sheet/overlay if switching to desktop
    const overlay = $('#sidebar-overlay');
    if (overlay) overlay.classList.remove('visible');
    closeBottomSheet();
    const sidebar = $('#sidebar');
    if (sidebar) sidebar.classList.remove('drawer-open');
  }
}

// ── 9. PARALLEL MODE ──────────────────────────────────────────────────────

function toggleParallelMode() {
  state.parallelMode = !state.parallelMode;
  const readerArea = $('#reader-area');
  const btn        = $('#btn-parallel');

  if (!readerArea) return;

  if (state.parallelMode) {
    readerArea.classList.add('parallel-mode');
    if (btn) btn.classList.add('active');

    // Pick a complementary translation
    if (!state.parallelTranslation) {
      state.parallelTranslation = state.currentTranslation === 'KJV' ? 'ESV' : 'KJV';
    }
    ensureParallelColumn();
    loadParallelColumn(state.currentBook, state.currentChapter);
  } else {
    readerArea.classList.remove('parallel-mode');
    if (btn) btn.classList.remove('active');
    const col = $('#parallel-column');
    if (col) col.remove();
  }
}

function ensureParallelColumn() {
  if ($('#parallel-column')) return;
  const readerArea = $('#reader-area');
  if (!readerArea) return;

  const col = el('div', { id: 'parallel-column', class: 'parallel-col' });

  const header = el('div', { class: 'parallel-col-header' });
  const select = el('select', {
    class: 'parallel-translation-select',
    onchange: (e) => {
      state.parallelTranslation = e.target.value;
      loadParallelColumn(state.currentBook, state.currentChapter);
    },
  });
  // Populate from cached translations or placeholder
  const cached = state.cachedTranslations || ['KJV', 'ESV', 'NIV', 'NASB', 'NKJV'];
  for (const t of cached) {
    const opt = el('option', { value: t }, t);
    if (t === state.parallelTranslation) opt.selected = true;
    select.appendChild(opt);
  }
  header.appendChild(select);
  col.appendChild(header);

  const content = el('div', { id: 'parallel-content', class: 'parallel-content' });
  col.appendChild(content);

  readerArea.appendChild(col);
}

async function loadParallelColumn(book, chapter) {
  const content = $('#parallel-content');
  if (!content) return;
  content.innerHTML = '<div class="loading-spinner">Loading…</div>';

  try {
    const ref  = encodeURIComponent(`${book} ${chapter}`);
    const data = await apiFetch(`/api/verse?ref=${ref}&translation=${encodeURIComponent(state.parallelTranslation)}`);
    content.innerHTML = '';
    for (const v of normalizeVerses(data)) {
      content.appendChild(renderVerse(v.num, v.text));
    }
  } catch (err) {
    content.innerHTML = `<p class="error-msg">Could not load ${escHtml(state.parallelTranslation)}.</p>`;
  }
}

// ── 10. SEARCH ─────────────────────────────────────────────────────────────

const REF_PATTERN = /^([1-3]?\\s*[A-Za-z]+(?:\\s+[A-Za-z]+)?)\\s+(\\d+)(?::(\\d+))?$/;

function handleSearch(query) {
  if (!query || !query.trim()) return;
  const q = query.trim();

  const refMatch = REF_PATTERN.exec(q);
  if (refMatch) {
    const bookRaw = refMatch[1].trim();
    const chapter = parseInt(refMatch[2], 10);
    const verse   = refMatch[3] ? parseInt(refMatch[3], 10) : null;
    const bookData = ALL_BOOKS.find(b =>
      b.name.toLowerCase() === bookRaw.toLowerCase() ||
      b.name.toLowerCase().startsWith(bookRaw.toLowerCase())
    );
    if (bookData) {
      closeSearchOverlay();
      loadChapter(bookData.name, chapter, verse);
      return;
    }
  }

  // Keyword search
  performKeywordSearch(q);
}

async function performKeywordSearch(query) {
  showSearchOverlay();
  const resultsEl = $('#search-results');
  if (!resultsEl) return;
  resultsEl.innerHTML = '<span class="loading-text">Searching…</span>';

  try {
    const data = await apiFetch(`/api/search?q=${encodeURIComponent(query)}&translation=${encodeURIComponent(state.currentTranslation)}`);
    const results = data.results || data.verses || data || [];

    resultsEl.innerHTML = '';

    if (results.length === 0) {
      resultsEl.innerHTML = '<p class="empty-state">No results found.</p>';
      return;
    }

    const countEl = el('p', { class: 'search-count' }, `${results.length} result${results.length !== 1 ? 's' : ''} for "${escHtml(query)}"`);
    resultsEl.appendChild(countEl);

    for (const result of results) {
      const ref   = result.ref || result.reference || '';
      const text  = result.text || result.verse || '';
      const item  = el('div', {
        class: 'search-result-item',
        onclick: () => {
          closeSearchOverlay();
          navigateToRef(ref);
        },
      });
      item.appendChild(el('div', { class: 'search-result-ref'  }, ref));
      item.appendChild(el('div', { class: 'search-result-text' }, text));
      resultsEl.appendChild(item);
    }
  } catch (err) {
    resultsEl.innerHTML = `<p class="error-msg">Search failed: ${escHtml(err.message)}</p>`;
  }
}

function showSearchOverlay() {
  const overlay = $('#search-overlay');
  if (overlay) {
    overlay.classList.remove('hidden');
    overlay.classList.add('visible');
  }
}

function closeSearchOverlay() {
  const overlay = $('#search-overlay');
  if (overlay) {
    overlay.classList.remove('visible');
    overlay.classList.add('hidden');
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

async function apiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function postHistory(ref) {
  try {
    await fetch('/api/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref }),
    });
  } catch {
    // silent
  }
}

function currentRef() {
  if (state.currentVerse) return state.currentVerse;
  return `${state.currentBook} ${state.currentChapter}`;
}

function parseRef(ref) {
  const m = REF_PATTERN.exec(ref.trim());
  if (!m) return null;
  const bookRaw = m[1].trim();
  const book = ALL_BOOKS.find(b =>
    b.name.toLowerCase() === bookRaw.toLowerCase() ||
    b.name.toLowerCase().startsWith(bookRaw.toLowerCase())
  );
  if (!book) return null;
  return { book: book.name, chapter: parseInt(m[2], 10), verse: m[3] ? parseInt(m[3], 10) : null };
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function restoreFromHash() {
  const hash = window.location.hash.replace('#', '');
  if (!hash) return false;

  // e.g. John-3 or John-3:16 or 1-Samuel-5:3
  const m = hash.match(/^(.+?)-(\\d+)(?::(\\d+))?$/);
  if (!m) return false;

  const bookSlug = m[1].replace(/-/g, ' ');
  const chapter  = parseInt(m[2], 10);
  const verse    = m[3] ? parseInt(m[3], 10) : null;
  const book = ALL_BOOKS.find(b => b.name.toLowerCase() === bookSlug.toLowerCase());
  if (!book) return false;

  loadChapter(book.name, chapter, verse);
  return true;
}

function saveLastPosition() {
  try {
    localStorage.setItem('bible_last_book',    state.currentBook);
    localStorage.setItem('bible_last_chapter', state.currentChapter);
  } catch { /* localStorage unavailable */ }
}

function loadLastPosition() {
  try {
    return {
      book:    localStorage.getItem('bible_last_book')    || 'John',
      chapter: parseInt(localStorage.getItem('bible_last_chapter') || '3', 10),
    };
  } catch {
    return { book: 'John', chapter: 3 };
  }
}

// ── Translation selector ───────────────────────────────────────────────────

async function loadTranslations() {
  try {
    const data = await apiFetch('/api/translations');
    const translations = data.translations || data || [];
    state.cachedTranslations = translations.map(t => t.abbreviation || t.name || t);

    const selector = $('#translation-select');
    if (!selector || state.cachedTranslations.length === 0) return;

    selector.innerHTML = '';
    for (const t of state.cachedTranslations) {
      const abbr = t.abbreviation || t.name || t;
      const name = t.full_name || t.name || abbr;
      const opt  = el('option', { value: abbr }, name);
      if (abbr === state.currentTranslation) opt.selected = true;
      selector.appendChild(opt);
    }
  } catch {
    // Non-fatal — KJV default still works
  }
}

// ── 11. INIT ───────────────────────────────────────────────────────────────

function init() {
  buildBookNav();
  loadTranslations();

  // Restore from URL hash, then localStorage, then default
  const restored = restoreFromHash();
  if (!restored) {
    const last = loadLastPosition();
    loadChapter(last.book, last.chapter);
  }

  // Translation selector change
  const transSelect = $('#translation-select');
  if (transSelect) {
    transSelect.value = state.currentTranslation;
    transSelect.addEventListener('change', e => {
      state.currentTranslation = e.target.value;
      loadChapter(state.currentBook, state.currentChapter, state.currentVerse);
    });
  }

  // Prev / Next chapter buttons
  const prevBtn = $('#btn-prev-chapter');
  const nextBtn = $('#btn-next-chapter');
  if (prevBtn) prevBtn.addEventListener('click', prevChapter);
  if (nextBtn) nextBtn.addEventListener('click', nextChapter);

  // Keyboard nav
  document.addEventListener('keydown', e => {
    // Don't intercept when user is typing
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
    if (e.key === 'ArrowLeft'  && !e.altKey) prevChapter();
    if (e.key === 'ArrowRight' && !e.altKey) nextChapter();
    if (e.key === 'Escape') {
      closeSearchOverlay();
      closeBottomSheet();
    }
  });

  // Sidebar toggle
  const sidebarToggle = $('#btn-sidebar-toggle') || $('#sidebar-toggle');
  if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);

  // Sidebar overlay (mobile tap-to-close)
  const overlay = $('#sidebar-overlay');
  if (overlay) overlay.addEventListener('click', toggleSidebar);

  // Bottom sheet close button
  const sheetClose = $('#btn-sheet-close');
  if (sheetClose) sheetClose.addEventListener('click', closeBottomSheet);

  // Swipe-down on bottom sheet handle
  const sheetHandle = $('#sheet-handle');
  if (sheetHandle) {
    let touchStartY = 0;
    sheetHandle.addEventListener('touchstart', e => { touchStartY = e.touches[0].clientY; }, { passive: true });
    sheetHandle.addEventListener('touchend', e => {
      const dy = e.changedTouches[0].clientY - touchStartY;
      if (dy > 60) closeBottomSheet();
    }, { passive: true });
  }

  // Tab buttons
  $$('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Parallel mode toggle
  const parallelBtn = $('#btn-parallel');
  if (parallelBtn) parallelBtn.addEventListener('click', toggleParallelMode);

  // Search input
  const searchInput = $('#search-input');
  if (searchInput) {
    searchInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') handleSearch(searchInput.value);
    });
  }
  const searchBtn = $('#btn-search');
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      const input = $('#search-input');
      if (input) handleSearch(input.value);
    });
  }

  // Search overlay close
  const searchOverlay = $('#search-overlay');
  if (searchOverlay) {
    searchOverlay.addEventListener('click', e => {
      if (e.target === searchOverlay) closeSearchOverlay();
    });
  }

  // Hash change (browser back/forward)
  window.addEventListener('hashchange', () => restoreFromHash());

  // Resize handler
  window.addEventListener('resize', handleResize);

  // Persist position before unload
  window.addEventListener('beforeunload', saveLastPosition);

  // Activate first tab
  switchTab(state.activeTab);

  console.log('[bible-reader] init complete');
}

// ── Entry Point ────────────────────────────────────────────────────────────
// Called by part1_shell.js after auth is confirmed, or directly here as fallback.

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if (window.__bibleAuthReady) init();
      // else: part3_auth.js will call init() after login
    });
  } else {
    if (window.__bibleAuthReady) init();
  }
}

// Expose public API for other parts
window.BibleReader = {
  init,
  loadChapter,
  selectVerse,
  onWordClick,
  handleSearch,
  switchTab,
  openBottomSheet,
  closeBottomSheet,
  toggleSidebar,
  toggleParallelMode,
  prevChapter,
  nextChapter,
  buildBookNav,
  OT_BOOKS,
  NT_BOOKS,
  ALL_BOOKS,
  BIBLICAL_PLACES,
  state,
};

</script>

<script>document.addEventListener('DOMContentLoaded', () => { initAuth(); });</script>

</body>
</html>
"""

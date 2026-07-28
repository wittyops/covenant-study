import os
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

app = FastAPI(title="Covenant Study", docs_url=None)

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


def normalize_strongs(number: str) -> list[str]:
    """Return candidate lookup keys for a Strong's number.

    strongs.db uses 'H1'/'H2' for Hebrew and '00001'/'00025' (5-digit, no prefix) for Greek.
    Interlinear uses 'G25', 'H1', 'G3588_A', 'H1004B', 'H7225G', etc.

    Returns a list of candidates to try in order.
    """
    import re
    n = number.upper().split("_")[0]  # strip _ disambiguation suffix (e.g. G3588_A → G3588)
    candidates = [n]

    # Strip trailing letter annotation used by STEPBible (e.g. H7225G → H7225, H1004A → H1004)
    base = re.sub(r"[A-Z]+$", "", n)
    if base and base != n:
        candidates.append(base)

    # For Greek G-prefixed numbers: convert to zero-padded 5-digit format
    for candidate in [n, base]:
        if candidate.startswith("G"):
            try:
                digits = int(re.sub(r"[A-Z]+$", "", candidate[1:]))
                zero_padded = f"{digits:05d}"
                if zero_padded not in candidates:
                    candidates.append(zero_padded)
            except ValueError:
                pass

    return candidates


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
            username = os.environ.get("ADMIN_USERNAME", "admin")
            password = os.environ.get("ADMIN_PASSWORD") or secrets.token_hex(12)
            hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
            conn.execute(
                "INSERT INTO users(username, password_hash, display_name, role, created_at)"
                " VALUES(?, ?, 'Administrator', 'admin', ?)",
                (username, hashed, int(time.time()))
            )
            conn.commit()
            if os.environ.get("ADMIN_PASSWORD"):
                print(f"[INIT] Admin account created: {username}", flush=True)
            else:
                print(f"[INIT] Admin account created. Username: {username}  Password: {password}", flush=True)
                print("[INIT] Set ADMIN_PASSWORD env var to control this on next fresh deploy.", flush=True)

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
        row = None
        for key in normalize_strongs(number):
            row = db.execute(
                "SELECT number,language,original,transliteration,pronunciation,definition,kjv_usage FROM strongs WHERE number=?",
                (key,)
            ).fetchone()
            if row:
                break
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
                {"name": name, "lat": data["lat"], "lng": data["lon"], "notes": data.get("notes", "")}
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
                    "lng": data["lon"],
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
    """Return verse(s) with per-word Strong's numbers.

    Chapter ref ('John 3')  → {"reference", "verses": [{"num", "words"}, ...]}
    Verse ref ('John 3:16') → {"reference", "verses": [{"num": 16, "words": [...]}]}
    Uses word_strongs table if populated; falls back to interlinear.db (always populated).
    """
    book_num, chapter, verse = parse_reference(ref)
    if not book_num:
        raise HTTPException(400, f"Could not parse reference: {ref}")

    strongs_path = DATA / "strongs.db"

    # --- Prefer word_strongs in kjv.db when available ---
    kjv_path = DATA / "kjv.db"
    if kjv_path.exists():
        conn = sqlite3.connect(str(kjv_path))
        conn.row_factory = sqlite3.Row
        try:
            has_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='word_strongs'"
            ).fetchone()
            has_data = has_table and conn.execute(
                "SELECT 1 FROM word_strongs LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    else:
        has_data = False

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
                return {"reference": ref, "verses": verses, "source": "word_strongs"}
            else:
                words = fetch_verse_words(verse)
                if not words:
                    raise HTTPException(404, f"No tagged data found for {ref}")
                return {"reference": ref, "verses": [{"num": verse, "words": words}], "source": "word_strongs"}
        finally:
            conn.close()

    # --- Fallback: interlinear.db (Hebrew/Greek with English glosses) ---
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

        def fetch_interlinear_words(v_num: int) -> list:
            rows = conn.execute(
                f"""
                SELECT i.word_num, i.english_gloss, i.strongs_num,
                       i.original_word, i.transliteration, i.morphology,
                       {strongs_sel}
                FROM interlinear i
                {strongs_join}
                WHERE i.book = ? AND i.chapter = ? AND i.verse = ?
                ORDER BY i.word_num
                """,
                (book_num, chapter, v_num),
            ).fetchall()
            return [
                {
                    "pos": r["word_num"],
                    "text": r["english_gloss"] or r["original_word"] or "",
                    "strongs": r["strongs_num"],
                    "extra_strongs": None,
                    "morph": r["morphology"],
                    "original": r["original_word"],
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
            verses = []
            for v_num in verse_nums:
                words = fetch_interlinear_words(v_num)
                if words:
                    verses.append({"num": v_num, "words": words})
            if not verses:
                raise HTTPException(404, f"No word data found for {ref}")
            return {"reference": ref, "verses": verses, "source": "interlinear"}
        else:
            words = fetch_interlinear_words(verse)
            if not words:
                raise HTTPException(404, f"No word data found for {ref}")
            return {"reference": ref, "verses": [{"num": verse, "words": words}], "source": "interlinear"}
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
  <title>Covenant Study</title>
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
#tab-maps {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 360px;
  overflow: hidden;
}
#leaflet-map {
  flex: 1;
  min-height: 360px;
}
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
  <style>
/* required styles */

.leaflet-pane,
.leaflet-tile,
.leaflet-marker-icon,
.leaflet-marker-shadow,
.leaflet-tile-container,
.leaflet-pane > svg,
.leaflet-pane > canvas,
.leaflet-zoom-box,
.leaflet-image-layer,
.leaflet-layer {
	position: absolute;
	left: 0;
	top: 0;
	}
.leaflet-container {
	overflow: hidden;
	}
.leaflet-tile,
.leaflet-marker-icon,
.leaflet-marker-shadow {
	-webkit-user-select: none;
	   -moz-user-select: none;
	        user-select: none;
	  -webkit-user-drag: none;
	}
/* Prevents IE11 from highlighting tiles in blue */
.leaflet-tile::selection {
	background: transparent;
}
/* Safari renders non-retina tile on retina better with this, but Chrome is worse */
.leaflet-safari .leaflet-tile {
	image-rendering: -webkit-optimize-contrast;
	}
/* hack that prevents hw layers "stretching" when loading new tiles */
.leaflet-safari .leaflet-tile-container {
	width: 1600px;
	height: 1600px;
	-webkit-transform-origin: 0 0;
	}
.leaflet-marker-icon,
.leaflet-marker-shadow {
	display: block;
	}
/* .leaflet-container svg: reset svg max-width decleration shipped in Joomla! (joomla.org) 3.x */
/* .leaflet-container img: map is broken in FF if you have max-width: 100% on tiles */
.leaflet-container .leaflet-overlay-pane svg {
	max-width: none !important;
	max-height: none !important;
	}
.leaflet-container .leaflet-marker-pane img,
.leaflet-container .leaflet-shadow-pane img,
.leaflet-container .leaflet-tile-pane img,
.leaflet-container img.leaflet-image-layer,
.leaflet-container .leaflet-tile {
	max-width: none !important;
	max-height: none !important;
	width: auto;
	padding: 0;
	}

.leaflet-container img.leaflet-tile {
	/* See: https://bugs.chromium.org/p/chromium/issues/detail?id=600120 */
	mix-blend-mode: plus-lighter;
}

.leaflet-container.leaflet-touch-zoom {
	-ms-touch-action: pan-x pan-y;
	touch-action: pan-x pan-y;
	}
.leaflet-container.leaflet-touch-drag {
	-ms-touch-action: pinch-zoom;
	/* Fallback for FF which doesn't support pinch-zoom */
	touch-action: none;
	touch-action: pinch-zoom;
}
.leaflet-container.leaflet-touch-drag.leaflet-touch-zoom {
	-ms-touch-action: none;
	touch-action: none;
}
.leaflet-container {
	-webkit-tap-highlight-color: transparent;
}
.leaflet-container a {
	-webkit-tap-highlight-color: rgba(51, 181, 229, 0.4);
}
.leaflet-tile {
	filter: inherit;
	visibility: hidden;
	}
.leaflet-tile-loaded {
	visibility: inherit;
	}
.leaflet-zoom-box {
	width: 0;
	height: 0;
	-moz-box-sizing: border-box;
	     box-sizing: border-box;
	z-index: 800;
	}
/* workaround for https://bugzilla.mozilla.org/show_bug.cgi?id=888319 */
.leaflet-overlay-pane svg {
	-moz-user-select: none;
	}

.leaflet-pane         { z-index: 400; }

.leaflet-tile-pane    { z-index: 200; }
.leaflet-overlay-pane { z-index: 400; }
.leaflet-shadow-pane  { z-index: 500; }
.leaflet-marker-pane  { z-index: 600; }
.leaflet-tooltip-pane   { z-index: 650; }
.leaflet-popup-pane   { z-index: 700; }

.leaflet-map-pane canvas { z-index: 100; }
.leaflet-map-pane svg    { z-index: 200; }

.leaflet-vml-shape {
	width: 1px;
	height: 1px;
	}
.lvml {
	behavior: url(#default#VML);
	display: inline-block;
	position: absolute;
	}


/* control positioning */

.leaflet-control {
	position: relative;
	z-index: 800;
	pointer-events: visiblePainted; /* IE 9-10 doesn't have auto */
	pointer-events: auto;
	}
.leaflet-top,
.leaflet-bottom {
	position: absolute;
	z-index: 1000;
	pointer-events: none;
	}
.leaflet-top {
	top: 0;
	}
.leaflet-right {
	right: 0;
	}
.leaflet-bottom {
	bottom: 0;
	}
.leaflet-left {
	left: 0;
	}
.leaflet-control {
	float: left;
	clear: both;
	}
.leaflet-right .leaflet-control {
	float: right;
	}
.leaflet-top .leaflet-control {
	margin-top: 10px;
	}
.leaflet-bottom .leaflet-control {
	margin-bottom: 10px;
	}
.leaflet-left .leaflet-control {
	margin-left: 10px;
	}
.leaflet-right .leaflet-control {
	margin-right: 10px;
	}


/* zoom and fade animations */

.leaflet-fade-anim .leaflet-popup {
	opacity: 0;
	-webkit-transition: opacity 0.2s linear;
	   -moz-transition: opacity 0.2s linear;
	        transition: opacity 0.2s linear;
	}
.leaflet-fade-anim .leaflet-map-pane .leaflet-popup {
	opacity: 1;
	}
.leaflet-zoom-animated {
	-webkit-transform-origin: 0 0;
	    -ms-transform-origin: 0 0;
	        transform-origin: 0 0;
	}
svg.leaflet-zoom-animated {
	will-change: transform;
}

.leaflet-zoom-anim .leaflet-zoom-animated {
	-webkit-transition: -webkit-transform 0.25s cubic-bezier(0,0,0.25,1);
	   -moz-transition:    -moz-transform 0.25s cubic-bezier(0,0,0.25,1);
	        transition:         transform 0.25s cubic-bezier(0,0,0.25,1);
	}
.leaflet-zoom-anim .leaflet-tile,
.leaflet-pan-anim .leaflet-tile {
	-webkit-transition: none;
	   -moz-transition: none;
	        transition: none;
	}

.leaflet-zoom-anim .leaflet-zoom-hide {
	visibility: hidden;
	}


/* cursors */

.leaflet-interactive {
	cursor: pointer;
	}
.leaflet-grab {
	cursor: -webkit-grab;
	cursor:    -moz-grab;
	cursor:         grab;
	}
.leaflet-crosshair,
.leaflet-crosshair .leaflet-interactive {
	cursor: crosshair;
	}
.leaflet-popup-pane,
.leaflet-control {
	cursor: auto;
	}
.leaflet-dragging .leaflet-grab,
.leaflet-dragging .leaflet-grab .leaflet-interactive,
.leaflet-dragging .leaflet-marker-draggable {
	cursor: move;
	cursor: -webkit-grabbing;
	cursor:    -moz-grabbing;
	cursor:         grabbing;
	}

/* marker & overlays interactivity */
.leaflet-marker-icon,
.leaflet-marker-shadow,
.leaflet-image-layer,
.leaflet-pane > svg path,
.leaflet-tile-container {
	pointer-events: none;
	}

.leaflet-marker-icon.leaflet-interactive,
.leaflet-image-layer.leaflet-interactive,
.leaflet-pane > svg path.leaflet-interactive,
svg.leaflet-image-layer.leaflet-interactive path {
	pointer-events: visiblePainted; /* IE 9-10 doesn't have auto */
	pointer-events: auto;
	}

/* visual tweaks */

.leaflet-container {
	background: #ddd;
	outline-offset: 1px;
	}
.leaflet-container a {
	color: #0078A8;
	}
.leaflet-zoom-box {
	border: 2px dotted #38f;
	background: rgba(255,255,255,0.5);
	}


/* general typography */
.leaflet-container {
	font-family: "Helvetica Neue", Arial, Helvetica, sans-serif;
	font-size: 12px;
	font-size: 0.75rem;
	line-height: 1.5;
	}


/* general toolbar styles */

.leaflet-bar {
	box-shadow: 0 1px 5px rgba(0,0,0,0.65);
	border-radius: 4px;
	}
.leaflet-bar a {
	background-color: #fff;
	border-bottom: 1px solid #ccc;
	width: 26px;
	height: 26px;
	line-height: 26px;
	display: block;
	text-align: center;
	text-decoration: none;
	color: black;
	}
.leaflet-bar a,
.leaflet-control-layers-toggle {
	background-position: 50% 50%;
	background-repeat: no-repeat;
	display: block;
	}
.leaflet-bar a:hover,
.leaflet-bar a:focus {
	background-color: #f4f4f4;
	}
.leaflet-bar a:first-child {
	border-top-left-radius: 4px;
	border-top-right-radius: 4px;
	}
.leaflet-bar a:last-child {
	border-bottom-left-radius: 4px;
	border-bottom-right-radius: 4px;
	border-bottom: none;
	}
.leaflet-bar a.leaflet-disabled {
	cursor: default;
	background-color: #f4f4f4;
	color: #bbb;
	}

.leaflet-touch .leaflet-bar a {
	width: 30px;
	height: 30px;
	line-height: 30px;
	}
.leaflet-touch .leaflet-bar a:first-child {
	border-top-left-radius: 2px;
	border-top-right-radius: 2px;
	}
.leaflet-touch .leaflet-bar a:last-child {
	border-bottom-left-radius: 2px;
	border-bottom-right-radius: 2px;
	}

/* zoom control */

.leaflet-control-zoom-in,
.leaflet-control-zoom-out {
	font: bold 18px 'Lucida Console', Monaco, monospace;
	text-indent: 1px;
	}

.leaflet-touch .leaflet-control-zoom-in, .leaflet-touch .leaflet-control-zoom-out  {
	font-size: 22px;
	}


/* layers control */

.leaflet-control-layers {
	box-shadow: 0 1px 5px rgba(0,0,0,0.4);
	background: #fff;
	border-radius: 5px;
	}
.leaflet-control-layers-toggle {
	background-image: url(images/layers.png);
	width: 36px;
	height: 36px;
	}
.leaflet-retina .leaflet-control-layers-toggle {
	background-image: url(images/layers-2x.png);
	background-size: 26px 26px;
	}
.leaflet-touch .leaflet-control-layers-toggle {
	width: 44px;
	height: 44px;
	}
.leaflet-control-layers .leaflet-control-layers-list,
.leaflet-control-layers-expanded .leaflet-control-layers-toggle {
	display: none;
	}
.leaflet-control-layers-expanded .leaflet-control-layers-list {
	display: block;
	position: relative;
	}
.leaflet-control-layers-expanded {
	padding: 6px 10px 6px 6px;
	color: #333;
	background: #fff;
	}
.leaflet-control-layers-scrollbar {
	overflow-y: scroll;
	overflow-x: hidden;
	padding-right: 5px;
	}
.leaflet-control-layers-selector {
	margin-top: 2px;
	position: relative;
	top: 1px;
	}
.leaflet-control-layers label {
	display: block;
	font-size: 13px;
	font-size: 1.08333em;
	}
.leaflet-control-layers-separator {
	height: 0;
	border-top: 1px solid #ddd;
	margin: 5px -10px 5px -6px;
	}

/* Default icon URLs */
.leaflet-default-icon-path { /* used only in path-guessing heuristic, see L.Icon.Default */
	background-image: url(images/marker-icon.png);
	}


/* attribution and scale controls */

.leaflet-container .leaflet-control-attribution {
	background: #fff;
	background: rgba(255, 255, 255, 0.8);
	margin: 0;
	}
.leaflet-control-attribution,
.leaflet-control-scale-line {
	padding: 0 5px;
	color: #333;
	line-height: 1.4;
	}
.leaflet-control-attribution a {
	text-decoration: none;
	}
.leaflet-control-attribution a:hover,
.leaflet-control-attribution a:focus {
	text-decoration: underline;
	}
.leaflet-attribution-flag {
	display: inline !important;
	vertical-align: baseline !important;
	width: 1em;
	height: 0.6669em;
	}
.leaflet-left .leaflet-control-scale {
	margin-left: 5px;
	}
.leaflet-bottom .leaflet-control-scale {
	margin-bottom: 5px;
	}
.leaflet-control-scale-line {
	border: 2px solid #777;
	border-top: none;
	line-height: 1.1;
	padding: 2px 5px 1px;
	white-space: nowrap;
	-moz-box-sizing: border-box;
	     box-sizing: border-box;
	background: rgba(255, 255, 255, 0.8);
	text-shadow: 1px 1px #fff;
	}
.leaflet-control-scale-line:not(:first-child) {
	border-top: 2px solid #777;
	border-bottom: none;
	margin-top: -2px;
	}
.leaflet-control-scale-line:not(:first-child):not(:last-child) {
	border-bottom: 2px solid #777;
	}

.leaflet-touch .leaflet-control-attribution,
.leaflet-touch .leaflet-control-layers,
.leaflet-touch .leaflet-bar {
	box-shadow: none;
	}
.leaflet-touch .leaflet-control-layers,
.leaflet-touch .leaflet-bar {
	border: 2px solid rgba(0,0,0,0.2);
	background-clip: padding-box;
	}


/* popup */

.leaflet-popup {
	position: absolute;
	text-align: center;
	margin-bottom: 20px;
	}
.leaflet-popup-content-wrapper {
	padding: 1px;
	text-align: left;
	border-radius: 12px;
	}
.leaflet-popup-content {
	margin: 13px 24px 13px 20px;
	line-height: 1.3;
	font-size: 13px;
	font-size: 1.08333em;
	min-height: 1px;
	}
.leaflet-popup-content p {
	margin: 17px 0;
	margin: 1.3em 0;
	}
.leaflet-popup-tip-container {
	width: 40px;
	height: 20px;
	position: absolute;
	left: 50%;
	margin-top: -1px;
	margin-left: -20px;
	overflow: hidden;
	pointer-events: none;
	}
.leaflet-popup-tip {
	width: 17px;
	height: 17px;
	padding: 1px;

	margin: -10px auto 0;
	pointer-events: auto;

	-webkit-transform: rotate(45deg);
	   -moz-transform: rotate(45deg);
	    -ms-transform: rotate(45deg);
	        transform: rotate(45deg);
	}
.leaflet-popup-content-wrapper,
.leaflet-popup-tip {
	background: white;
	color: #333;
	box-shadow: 0 3px 14px rgba(0,0,0,0.4);
	}
.leaflet-container a.leaflet-popup-close-button {
	position: absolute;
	top: 0;
	right: 0;
	border: none;
	text-align: center;
	width: 24px;
	height: 24px;
	font: 16px/24px Tahoma, Verdana, sans-serif;
	color: #757575;
	text-decoration: none;
	background: transparent;
	}
.leaflet-container a.leaflet-popup-close-button:hover,
.leaflet-container a.leaflet-popup-close-button:focus {
	color: #585858;
	}
.leaflet-popup-scrolled {
	overflow: auto;
	}

.leaflet-oldie .leaflet-popup-content-wrapper {
	-ms-zoom: 1;
	}
.leaflet-oldie .leaflet-popup-tip {
	width: 24px;
	margin: 0 auto;

	-ms-filter: "progid:DXImageTransform.Microsoft.Matrix(M11=0.70710678, M12=0.70710678, M21=-0.70710678, M22=0.70710678)";
	filter: progid:DXImageTransform.Microsoft.Matrix(M11=0.70710678, M12=0.70710678, M21=-0.70710678, M22=0.70710678);
	}

.leaflet-oldie .leaflet-control-zoom,
.leaflet-oldie .leaflet-control-layers,
.leaflet-oldie .leaflet-popup-content-wrapper,
.leaflet-oldie .leaflet-popup-tip {
	border: 1px solid #999;
	}


/* div icon */

.leaflet-div-icon {
	background: #fff;
	border: 1px solid #666;
	}


/* Tooltip */
/* Base styles for the element that has a tooltip */
.leaflet-tooltip {
	position: absolute;
	padding: 6px;
	background-color: #fff;
	border: 1px solid #fff;
	border-radius: 3px;
	color: #222;
	white-space: nowrap;
	-webkit-user-select: none;
	-moz-user-select: none;
	-ms-user-select: none;
	user-select: none;
	pointer-events: none;
	box-shadow: 0 1px 3px rgba(0,0,0,0.4);
	}
.leaflet-tooltip.leaflet-interactive {
	cursor: pointer;
	pointer-events: auto;
	}
.leaflet-tooltip-top:before,
.leaflet-tooltip-bottom:before,
.leaflet-tooltip-left:before,
.leaflet-tooltip-right:before {
	position: absolute;
	pointer-events: none;
	border: 6px solid transparent;
	background: transparent;
	content: "";
	}

/* Directions */

.leaflet-tooltip-bottom {
	margin-top: 6px;
}
.leaflet-tooltip-top {
	margin-top: -6px;
}
.leaflet-tooltip-bottom:before,
.leaflet-tooltip-top:before {
	left: 50%;
	margin-left: -6px;
	}
.leaflet-tooltip-top:before {
	bottom: 0;
	margin-bottom: -12px;
	border-top-color: #fff;
	}
.leaflet-tooltip-bottom:before {
	top: 0;
	margin-top: -12px;
	margin-left: -6px;
	border-bottom-color: #fff;
	}
.leaflet-tooltip-left {
	margin-left: -6px;
}
.leaflet-tooltip-right {
	margin-left: 6px;
}
.leaflet-tooltip-left:before,
.leaflet-tooltip-right:before {
	top: 50%;
	margin-top: -6px;
	}
.leaflet-tooltip-left:before {
	right: 0;
	margin-right: -12px;
	border-left-color: #fff;
	}
.leaflet-tooltip-right:before {
	left: 0;
	margin-left: -12px;
	border-right-color: #fff;
	}

/* Printing */

@media print {
	/* Prevent printers from removing background-images of controls. */
	.leaflet-control {
		-webkit-print-color-adjust: exact;
		print-color-adjust: exact;
		}
	}

  </style>
  <script>
/* @preserve
 * Leaflet 1.9.4, a JS library for interactive maps. https://leafletjs.com
 * (c) 2010-2023 Vladimir Agafonkin, (c) 2010-2011 CloudMade
 */
!function(t,e){"object"==typeof exports&&"undefined"!=typeof module?e(exports):"function"==typeof define&&define.amd?define(["exports"],e):e((t="undefined"!=typeof globalThis?globalThis:t||self).leaflet={})}(this,function(t){"use strict";function l(t){for(var e,i,n=1,o=arguments.length;n<o;n++)for(e in i=arguments[n])t[e]=i[e];return t}var R=Object.create||function(t){return N.prototype=t,new N};function N(){}function a(t,e){var i,n=Array.prototype.slice;return t.bind?t.bind.apply(t,n.call(arguments,1)):(i=n.call(arguments,2),function(){return t.apply(e,i.length?i.concat(n.call(arguments)):arguments)})}var D=0;function h(t){return"_leaflet_id"in t||(t._leaflet_id=++D),t._leaflet_id}function j(t,e,i){var n,o,s=function(){n=!1,o&&(r.apply(i,o),o=!1)},r=function(){n?o=arguments:(t.apply(i,arguments),setTimeout(s,e),n=!0)};return r}function H(t,e,i){var n=e[1],e=e[0],o=n-e;return t===n&&i?t:((t-e)%o+o)%o+e}function u(){return!1}function i(t,e){return!1===e?t:(e=Math.pow(10,void 0===e?6:e),Math.round(t*e)/e)}function W(t){return t.trim?t.trim():t.replace(/^\s+|\s+$/g,"")}function F(t){return W(t).split(/\s+/)}function c(t,e){for(var i in Object.prototype.hasOwnProperty.call(t,"options")||(t.options=t.options?R(t.options):{}),e)t.options[i]=e[i];return t.options}function U(t,e,i){var n,o=[];for(n in t)o.push(encodeURIComponent(i?n.toUpperCase():n)+"="+encodeURIComponent(t[n]));return(e&&-1!==e.indexOf("?")?"&":"?")+o.join("&")}var V=/\{ *([\w_ -]+) *\}/g;function q(t,i){return t.replace(V,function(t,e){e=i[e];if(void 0===e)throw new Error("No value provided for variable "+t);return e="function"==typeof e?e(i):e})}var d=Array.isArray||function(t){return"[object Array]"===Object.prototype.toString.call(t)};function G(t,e){for(var i=0;i<t.length;i++)if(t[i]===e)return i;return-1}var K="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";function Y(t){return window["webkit"+t]||window["moz"+t]||window["ms"+t]}var X=0;function J(t){var e=+new Date,i=Math.max(0,16-(e-X));return X=e+i,window.setTimeout(t,i)}var $=window.requestAnimationFrame||Y("RequestAnimationFrame")||J,Q=window.cancelAnimationFrame||Y("CancelAnimationFrame")||Y("CancelRequestAnimationFrame")||function(t){window.clearTimeout(t)};function x(t,e,i){if(!i||$!==J)return $.call(window,a(t,e));t.call(e)}function r(t){t&&Q.call(window,t)}var tt={__proto__:null,extend:l,create:R,bind:a,get lastId(){return D},stamp:h,throttle:j,wrapNum:H,falseFn:u,formatNum:i,trim:W,splitWords:F,setOptions:c,getParamString:U,template:q,isArray:d,indexOf:G,emptyImageUrl:K,requestFn:$,cancelFn:Q,requestAnimFrame:x,cancelAnimFrame:r};function et(){}et.extend=function(t){function e(){c(this),this.initialize&&this.initialize.apply(this,arguments),this.callInitHooks()}var i,n=e.__super__=this.prototype,o=R(n);for(i in(o.constructor=e).prototype=o,this)Object.prototype.hasOwnProperty.call(this,i)&&"prototype"!==i&&"__super__"!==i&&(e[i]=this[i]);if(t.statics&&l(e,t.statics),t.includes){var s=t.includes;if("undefined"!=typeof L&&L&&L.Mixin){s=d(s)?s:[s];for(var r=0;r<s.length;r++)s[r]===L.Mixin.Events&&console.warn("Deprecated include of L.Mixin.Events: this property will be removed in future releases, please inherit from L.Evented instead.",(new Error).stack)}l.apply(null,[o].concat(t.includes))}return l(o,t),delete o.statics,delete o.includes,o.options&&(o.options=n.options?R(n.options):{},l(o.options,t.options)),o._initHooks=[],o.callInitHooks=function(){if(!this._initHooksCalled){n.callInitHooks&&n.callInitHooks.call(this),this._initHooksCalled=!0;for(var t=0,e=o._initHooks.length;t<e;t++)o._initHooks[t].call(this)}},e},et.include=function(t){var e=this.prototype.options;return l(this.prototype,t),t.options&&(this.prototype.options=e,this.mergeOptions(t.options)),this},et.mergeOptions=function(t){return l(this.prototype.options,t),this},et.addInitHook=function(t){var e=Array.prototype.slice.call(arguments,1),i="function"==typeof t?t:function(){this[t].apply(this,e)};return this.prototype._initHooks=this.prototype._initHooks||[],this.prototype._initHooks.push(i),this};var e={on:function(t,e,i){if("object"==typeof t)for(var n in t)this._on(n,t[n],e);else for(var o=0,s=(t=F(t)).length;o<s;o++)this._on(t[o],e,i);return this},off:function(t,e,i){if(arguments.length)if("object"==typeof t)for(var n in t)this._off(n,t[n],e);else{t=F(t);for(var o=1===arguments.length,s=0,r=t.length;s<r;s++)o?this._off(t[s]):this._off(t[s],e,i)}else delete this._events;return this},_on:function(t,e,i,n){"function"!=typeof e?console.warn("wrong listener type: "+typeof e):!1===this._listens(t,e,i)&&(e={fn:e,ctx:i=i===this?void 0:i},n&&(e.once=!0),this._events=this._events||{},this._events[t]=this._events[t]||[],this._events[t].push(e))},_off:function(t,e,i){var n,o,s;if(this._events&&(n=this._events[t]))if(1===arguments.length){if(this._firingCount)for(o=0,s=n.length;o<s;o++)n[o].fn=u;delete this._events[t]}else"function"!=typeof e?console.warn("wrong listener type: "+typeof e):!1!==(e=this._listens(t,e,i))&&(i=n[e],this._firingCount&&(i.fn=u,this._events[t]=n=n.slice()),n.splice(e,1))},fire:function(t,e,i){if(this.listens(t,i)){var n=l({},e,{type:t,target:this,sourceTarget:e&&e.sourceTarget||this});if(this._events){var o=this._events[t];if(o){this._firingCount=this._firingCount+1||1;for(var s=0,r=o.length;s<r;s++){var a=o[s],h=a.fn;a.once&&this.off(t,h,a.ctx),h.call(a.ctx||this,n)}this._firingCount--}}i&&this._propagateEvent(n)}return this},listens:function(t,e,i,n){"string"!=typeof t&&console.warn('"string" type argument expected');var o=e,s=("function"!=typeof e&&(n=!!e,i=o=void 0),this._events&&this._events[t]);if(s&&s.length&&!1!==this._listens(t,o,i))return!0;if(n)for(var r in this._eventParents)if(this._eventParents[r].listens(t,e,i,n))return!0;return!1},_listens:function(t,e,i){if(this._events){var n=this._events[t]||[];if(!e)return!!n.length;i===this&&(i=void 0);for(var o=0,s=n.length;o<s;o++)if(n[o].fn===e&&n[o].ctx===i)return o}return!1},once:function(t,e,i){if("object"==typeof t)for(var n in t)this._on(n,t[n],e,!0);else for(var o=0,s=(t=F(t)).length;o<s;o++)this._on(t[o],e,i,!0);return this},addEventParent:function(t){return this._eventParents=this._eventParents||{},this._eventParents[h(t)]=t,this},removeEventParent:function(t){return this._eventParents&&delete this._eventParents[h(t)],this},_propagateEvent:function(t){for(var e in this._eventParents)this._eventParents[e].fire(t.type,l({layer:t.target,propagatedFrom:t.target},t),!0)}},it=(e.addEventListener=e.on,e.removeEventListener=e.clearAllEventListeners=e.off,e.addOneTimeEventListener=e.once,e.fireEvent=e.fire,e.hasEventListeners=e.listens,et.extend(e));function p(t,e,i){this.x=i?Math.round(t):t,this.y=i?Math.round(e):e}var nt=Math.trunc||function(t){return 0<t?Math.floor(t):Math.ceil(t)};function m(t,e,i){return t instanceof p?t:d(t)?new p(t[0],t[1]):null==t?t:"object"==typeof t&&"x"in t&&"y"in t?new p(t.x,t.y):new p(t,e,i)}function f(t,e){if(t)for(var i=e?[t,e]:t,n=0,o=i.length;n<o;n++)this.extend(i[n])}function _(t,e){return!t||t instanceof f?t:new f(t,e)}function s(t,e){if(t)for(var i=e?[t,e]:t,n=0,o=i.length;n<o;n++)this.extend(i[n])}function g(t,e){return t instanceof s?t:new s(t,e)}function v(t,e,i){if(isNaN(t)||isNaN(e))throw new Error("Invalid LatLng object: ("+t+", "+e+")");this.lat=+t,this.lng=+e,void 0!==i&&(this.alt=+i)}function w(t,e,i){return t instanceof v?t:d(t)&&"object"!=typeof t[0]?3===t.length?new v(t[0],t[1],t[2]):2===t.length?new v(t[0],t[1]):null:null==t?t:"object"==typeof t&&"lat"in t?new v(t.lat,"lng"in t?t.lng:t.lon,t.alt):void 0===e?null:new v(t,e,i)}p.prototype={clone:function(){return new p(this.x,this.y)},add:function(t){return this.clone()._add(m(t))},_add:function(t){return this.x+=t.x,this.y+=t.y,this},subtract:function(t){return this.clone()._subtract(m(t))},_subtract:function(t){return this.x-=t.x,this.y-=t.y,this},divideBy:function(t){return this.clone()._divideBy(t)},_divideBy:function(t){return this.x/=t,this.y/=t,this},multiplyBy:function(t){return this.clone()._multiplyBy(t)},_multiplyBy:function(t){return this.x*=t,this.y*=t,this},scaleBy:function(t){return new p(this.x*t.x,this.y*t.y)},unscaleBy:function(t){return new p(this.x/t.x,this.y/t.y)},round:function(){return this.clone()._round()},_round:function(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this},floor:function(){return this.clone()._floor()},_floor:function(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this},ceil:function(){return this.clone()._ceil()},_ceil:function(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this},trunc:function(){return this.clone()._trunc()},_trunc:function(){return this.x=nt(this.x),this.y=nt(this.y),this},distanceTo:function(t){var e=(t=m(t)).x-this.x,t=t.y-this.y;return Math.sqrt(e*e+t*t)},equals:function(t){return(t=m(t)).x===this.x&&t.y===this.y},contains:function(t){return t=m(t),Math.abs(t.x)<=Math.abs(this.x)&&Math.abs(t.y)<=Math.abs(this.y)},toString:function(){return"Point("+i(this.x)+", "+i(this.y)+")"}},f.prototype={extend:function(t){var e,i;if(t){if(t instanceof p||"number"==typeof t[0]||"x"in t)e=i=m(t);else if(e=(t=_(t)).min,i=t.max,!e||!i)return this;this.min||this.max?(this.min.x=Math.min(e.x,this.min.x),this.max.x=Math.max(i.x,this.max.x),this.min.y=Math.min(e.y,this.min.y),this.max.y=Math.max(i.y,this.max.y)):(this.min=e.clone(),this.max=i.clone())}return this},getCenter:function(t){return m((this.min.x+this.max.x)/2,(this.min.y+this.max.y)/2,t)},getBottomLeft:function(){return m(this.min.x,this.max.y)},getTopRight:function(){return m(this.max.x,this.min.y)},getTopLeft:function(){return this.min},getBottomRight:function(){return this.max},getSize:function(){return this.max.subtract(this.min)},contains:function(t){var e,i;return(t=("number"==typeof t[0]||t instanceof p?m:_)(t))instanceof f?(e=t.min,i=t.max):e=i=t,e.x>=this.min.x&&i.x<=this.max.x&&e.y>=this.min.y&&i.y<=this.max.y},intersects:function(t){t=_(t);var e=this.min,i=this.max,n=t.min,t=t.max,o=t.x>=e.x&&n.x<=i.x,t=t.y>=e.y&&n.y<=i.y;return o&&t},overlaps:function(t){t=_(t);var e=this.min,i=this.max,n=t.min,t=t.max,o=t.x>e.x&&n.x<i.x,t=t.y>e.y&&n.y<i.y;return o&&t},isValid:function(){return!(!this.min||!this.max)},pad:function(t){var e=this.min,i=this.max,n=Math.abs(e.x-i.x)*t,t=Math.abs(e.y-i.y)*t;return _(m(e.x-n,e.y-t),m(i.x+n,i.y+t))},equals:function(t){return!!t&&(t=_(t),this.min.equals(t.getTopLeft())&&this.max.equals(t.getBottomRight()))}},s.prototype={extend:function(t){var e,i,n=this._southWest,o=this._northEast;if(t instanceof v)i=e=t;else{if(!(t instanceof s))return t?this.extend(w(t)||g(t)):this;if(e=t._southWest,i=t._northEast,!e||!i)return this}return n||o?(n.lat=Math.min(e.lat,n.lat),n.lng=Math.min(e.lng,n.lng),o.lat=Math.max(i.lat,o.lat),o.lng=Math.max(i.lng,o.lng)):(this._southWest=new v(e.lat,e.lng),this._northEast=new v(i.lat,i.lng)),this},pad:function(t){var e=this._southWest,i=this._northEast,n=Math.abs(e.lat-i.lat)*t,t=Math.abs(e.lng-i.lng)*t;return new s(new v(e.lat-n,e.lng-t),new v(i.lat+n,i.lng+t))},getCenter:function(){return new v((this._southWest.lat+this._northEast.lat)/2,(this._southWest.lng+this._northEast.lng)/2)},getSouthWest:function(){return this._southWest},getNorthEast:function(){return this._northEast},getNorthWest:function(){return new v(this.getNorth(),this.getWest())},getSouthEast:function(){return new v(this.getSouth(),this.getEast())},getWest:function(){return this._southWest.lng},getSouth:function(){return this._southWest.lat},getEast:function(){return this._northEast.lng},getNorth:function(){return this._northEast.lat},contains:function(t){t=("number"==typeof t[0]||t instanceof v||"lat"in t?w:g)(t);var e,i,n=this._southWest,o=this._northEast;return t instanceof s?(e=t.getSouthWest(),i=t.getNorthEast()):e=i=t,e.lat>=n.lat&&i.lat<=o.lat&&e.lng>=n.lng&&i.lng<=o.lng},intersects:function(t){t=g(t);var e=this._southWest,i=this._northEast,n=t.getSouthWest(),t=t.getNorthEast(),o=t.lat>=e.lat&&n.lat<=i.lat,t=t.lng>=e.lng&&n.lng<=i.lng;return o&&t},overlaps:function(t){t=g(t);var e=this._southWest,i=this._northEast,n=t.getSouthWest(),t=t.getNorthEast(),o=t.lat>e.lat&&n.lat<i.lat,t=t.lng>e.lng&&n.lng<i.lng;return o&&t},toBBoxString:function(){return[this.getWest(),this.getSouth(),this.getEast(),this.getNorth()].join(",")},equals:function(t,e){return!!t&&(t=g(t),this._southWest.equals(t.getSouthWest(),e)&&this._northEast.equals(t.getNorthEast(),e))},isValid:function(){return!(!this._southWest||!this._northEast)}};var ot={latLngToPoint:function(t,e){t=this.projection.project(t),e=this.scale(e);return this.transformation._transform(t,e)},pointToLatLng:function(t,e){e=this.scale(e),t=this.transformation.untransform(t,e);return this.projection.unproject(t)},project:function(t){return this.projection.project(t)},unproject:function(t){return this.projection.unproject(t)},scale:function(t){return 256*Math.pow(2,t)},zoom:function(t){return Math.log(t/256)/Math.LN2},getProjectedBounds:function(t){var e;return this.infinite?null:(e=this.projection.bounds,t=this.scale(t),new f(this.transformation.transform(e.min,t),this.transformation.transform(e.max,t)))},infinite:!(v.prototype={equals:function(t,e){return!!t&&(t=w(t),Math.max(Math.abs(this.lat-t.lat),Math.abs(this.lng-t.lng))<=(void 0===e?1e-9:e))},toString:function(t){return"LatLng("+i(this.lat,t)+", "+i(this.lng,t)+")"},distanceTo:function(t){return st.distance(this,w(t))},wrap:function(){return st.wrapLatLng(this)},toBounds:function(t){var t=180*t/40075017,e=t/Math.cos(Math.PI/180*this.lat);return g([this.lat-t,this.lng-e],[this.lat+t,this.lng+e])},clone:function(){return new v(this.lat,this.lng,this.alt)}}),wrapLatLng:function(t){var e=this.wrapLng?H(t.lng,this.wrapLng,!0):t.lng;return new v(this.wrapLat?H(t.lat,this.wrapLat,!0):t.lat,e,t.alt)},wrapLatLngBounds:function(t){var e=t.getCenter(),i=this.wrapLatLng(e),n=e.lat-i.lat,e=e.lng-i.lng;return 0==n&&0==e?t:(i=t.getSouthWest(),t=t.getNorthEast(),new s(new v(i.lat-n,i.lng-e),new v(t.lat-n,t.lng-e)))}},st=l({},ot,{wrapLng:[-180,180],R:6371e3,distance:function(t,e){var i=Math.PI/180,n=t.lat*i,o=e.lat*i,s=Math.sin((e.lat-t.lat)*i/2),e=Math.sin((e.lng-t.lng)*i/2),t=s*s+Math.cos(n)*Math.cos(o)*e*e,i=2*Math.atan2(Math.sqrt(t),Math.sqrt(1-t));return this.R*i}}),rt=6378137,rt={R:rt,MAX_LATITUDE:85.0511287798,project:function(t){var e=Math.PI/180,i=this.MAX_LATITUDE,i=Math.max(Math.min(i,t.lat),-i),i=Math.sin(i*e);return new p(this.R*t.lng*e,this.R*Math.log((1+i)/(1-i))/2)},unproject:function(t){var e=180/Math.PI;return new v((2*Math.atan(Math.exp(t.y/this.R))-Math.PI/2)*e,t.x*e/this.R)},bounds:new f([-(rt=rt*Math.PI),-rt],[rt,rt])};function at(t,e,i,n){d(t)?(this._a=t[0],this._b=t[1],this._c=t[2],this._d=t[3]):(this._a=t,this._b=e,this._c=i,this._d=n)}function ht(t,e,i,n){return new at(t,e,i,n)}at.prototype={transform:function(t,e){return this._transform(t.clone(),e)},_transform:function(t,e){return t.x=(e=e||1)*(this._a*t.x+this._b),t.y=e*(this._c*t.y+this._d),t},untransform:function(t,e){return new p((t.x/(e=e||1)-this._b)/this._a,(t.y/e-this._d)/this._c)}};var lt=l({},st,{code:"EPSG:3857",projection:rt,transformation:ht(lt=.5/(Math.PI*rt.R),.5,-lt,.5)}),ut=l({},lt,{code:"EPSG:900913"});function ct(t){return document.createElementNS("http://www.w3.org/2000/svg",t)}function dt(t,e){for(var i,n,o,s,r="",a=0,h=t.length;a<h;a++){for(i=0,n=(o=t[a]).length;i<n;i++)r+=(i?"L":"M")+(s=o[i]).x+" "+s.y;r+=e?b.svg?"z":"x":""}return r||"M0 0"}var _t=document.documentElement.style,pt="ActiveXObject"in window,mt=pt&&!document.addEventListener,n="msLaunchUri"in navigator&&!("documentMode"in document),ft=y("webkit"),gt=y("android"),vt=y("android 2")||y("android 3"),yt=parseInt(/WebKit\/([0-9]+)|$/.exec(navigator.userAgent)[1],10),yt=gt&&y("Google")&&yt<537&&!("AudioNode"in window),xt=!!window.opera,wt=!n&&y("chrome"),bt=y("gecko")&&!ft&&!xt&&!pt,Pt=!wt&&y("safari"),Lt=y("phantom"),o="OTransition"in _t,Tt=0===navigator.platform.indexOf("Win"),Mt=pt&&"transition"in _t,zt="WebKitCSSMatrix"in window&&"m11"in new window.WebKitCSSMatrix&&!vt,_t="MozPerspective"in _t,Ct=!window.L_DISABLE_3D&&(Mt||zt||_t)&&!o&&!Lt,Zt="undefined"!=typeof orientation||y("mobile"),St=Zt&&ft,Et=Zt&&zt,kt=!window.PointerEvent&&window.MSPointerEvent,Ot=!(!window.PointerEvent&&!kt),At="ontouchstart"in window||!!window.TouchEvent,Bt=!window.L_NO_TOUCH&&(At||Ot),It=Zt&&xt,Rt=Zt&&bt,Nt=1<(window.devicePixelRatio||window.screen.deviceXDPI/window.screen.logicalXDPI),Dt=function(){var t=!1;try{var e=Object.defineProperty({},"passive",{get:function(){t=!0}});window.addEventListener("testPassiveEventSupport",u,e),window.removeEventListener("testPassiveEventSupport",u,e)}catch(t){}return t}(),jt=!!document.createElement("canvas").getContext,Ht=!(!document.createElementNS||!ct("svg").createSVGRect),Wt=!!Ht&&((Wt=document.createElement("div")).innerHTML="<svg/>","http://www.w3.org/2000/svg"===(Wt.firstChild&&Wt.firstChild.namespaceURI));function y(t){return 0<=navigator.userAgent.toLowerCase().indexOf(t)}var b={ie:pt,ielt9:mt,edge:n,webkit:ft,android:gt,android23:vt,androidStock:yt,opera:xt,chrome:wt,gecko:bt,safari:Pt,phantom:Lt,opera12:o,win:Tt,ie3d:Mt,webkit3d:zt,gecko3d:_t,any3d:Ct,mobile:Zt,mobileWebkit:St,mobileWebkit3d:Et,msPointer:kt,pointer:Ot,touch:Bt,touchNative:At,mobileOpera:It,mobileGecko:Rt,retina:Nt,passiveEvents:Dt,canvas:jt,svg:Ht,vml:!Ht&&function(){try{var t=document.createElement("div"),e=(t.innerHTML='<v:shape adj="1"/>',t.firstChild);return e.style.behavior="url(#default#VML)",e&&"object"==typeof e.adj}catch(t){return!1}}(),inlineSvg:Wt,mac:0===navigator.platform.indexOf("Mac"),linux:0===navigator.platform.indexOf("Linux")},Ft=b.msPointer?"MSPointerDown":"pointerdown",Ut=b.msPointer?"MSPointerMove":"pointermove",Vt=b.msPointer?"MSPointerUp":"pointerup",qt=b.msPointer?"MSPointerCancel":"pointercancel",Gt={touchstart:Ft,touchmove:Ut,touchend:Vt,touchcancel:qt},Kt={touchstart:function(t,e){e.MSPOINTER_TYPE_TOUCH&&e.pointerType===e.MSPOINTER_TYPE_TOUCH&&O(e);ee(t,e)},touchmove:ee,touchend:ee,touchcancel:ee},Yt={},Xt=!1;function Jt(t,e,i){return"touchstart"!==e||Xt||(document.addEventListener(Ft,$t,!0),document.addEventListener(Ut,Qt,!0),document.addEventListener(Vt,te,!0),document.addEventListener(qt,te,!0),Xt=!0),Kt[e]?(i=Kt[e].bind(this,i),t.addEventListener(Gt[e],i,!1),i):(console.warn("wrong event specified:",e),u)}function $t(t){Yt[t.pointerId]=t}function Qt(t){Yt[t.pointerId]&&(Yt[t.pointerId]=t)}function te(t){delete Yt[t.pointerId]}function ee(t,e){if(e.pointerType!==(e.MSPOINTER_TYPE_MOUSE||"mouse")){for(var i in e.touches=[],Yt)e.touches.push(Yt[i]);e.changedTouches=[e],t(e)}}var ie=200;function ne(t,i){t.addEventListener("dblclick",i);var n,o=0;function e(t){var e;1!==t.detail?n=t.detail:"mouse"===t.pointerType||t.sourceCapabilities&&!t.sourceCapabilities.firesTouchEvents||((e=Ne(t)).some(function(t){return t instanceof HTMLLabelElement&&t.attributes.for})&&!e.some(function(t){return t instanceof HTMLInputElement||t instanceof HTMLSelectElement})||((e=Date.now())-o<=ie?2===++n&&i(function(t){var e,i,n={};for(i in t)e=t[i],n[i]=e&&e.bind?e.bind(t):e;return(t=n).type="dblclick",n.detail=2,n.isTrusted=!1,n._simulated=!0,n}(t)):n=1,o=e))}return t.addEventListener("click",e),{dblclick:i,simDblclick:e}}var oe,se,re,ae,he,le,ue=we(["transform","webkitTransform","OTransform","MozTransform","msTransform"]),ce=we(["webkitTransition","transition","OTransition","MozTransition","msTransition"]),de="webkitTransition"===ce||"OTransition"===ce?ce+"End":"transitionend";function _e(t){return"string"==typeof t?document.getElementById(t):t}function pe(t,e){var i=t.style[e]||t.currentStyle&&t.currentStyle[e];return"auto"===(i=i&&"auto"!==i||!document.defaultView?i:(t=document.defaultView.getComputedStyle(t,null))?t[e]:null)?null:i}function P(t,e,i){t=document.createElement(t);return t.className=e||"",i&&i.appendChild(t),t}function T(t){var e=t.parentNode;e&&e.removeChild(t)}function me(t){for(;t.firstChild;)t.removeChild(t.firstChild)}function fe(t){var e=t.parentNode;e&&e.lastChild!==t&&e.appendChild(t)}function ge(t){var e=t.parentNode;e&&e.firstChild!==t&&e.insertBefore(t,e.firstChild)}function ve(t,e){return void 0!==t.classList?t.classList.contains(e):0<(t=xe(t)).length&&new RegExp("(^|\\s)"+e+"(\\s|$)").test(t)}function M(t,e){var i;if(void 0!==t.classList)for(var n=F(e),o=0,s=n.length;o<s;o++)t.classList.add(n[o]);else ve(t,e)||ye(t,((i=xe(t))?i+" ":"")+e)}function z(t,e){void 0!==t.classList?t.classList.remove(e):ye(t,W((" "+xe(t)+" ").replace(" "+e+" "," ")))}function ye(t,e){void 0===t.className.baseVal?t.className=e:t.className.baseVal=e}function xe(t){return void 0===(t=t.correspondingElement?t.correspondingElement:t).className.baseVal?t.className:t.className.baseVal}function C(t,e){if("opacity"in t.style)t.style.opacity=e;else if("filter"in t.style){var i=!1,n="DXImageTransform.Microsoft.Alpha";try{i=t.filters.item(n)}catch(t){if(1===e)return}e=Math.round(100*e),i?(i.Enabled=100!==e,i.Opacity=e):t.style.filter+=" progid:"+n+"(opacity="+e+")"}}function we(t){for(var e=document.documentElement.style,i=0;i<t.length;i++)if(t[i]in e)return t[i];return!1}function be(t,e,i){e=e||new p(0,0);t.style[ue]=(b.ie3d?"translate("+e.x+"px,"+e.y+"px)":"translate3d("+e.x+"px,"+e.y+"px,0)")+(i?" scale("+i+")":"")}function Z(t,e){t._leaflet_pos=e,b.any3d?be(t,e):(t.style.left=e.x+"px",t.style.top=e.y+"px")}function Pe(t){return t._leaflet_pos||new p(0,0)}function Le(){S(window,"dragstart",O)}function Te(){k(window,"dragstart",O)}function Me(t){for(;-1===t.tabIndex;)t=t.parentNode;t.style&&(ze(),le=(he=t).style.outlineStyle,t.style.outlineStyle="none",S(window,"keydown",ze))}function ze(){he&&(he.style.outlineStyle=le,le=he=void 0,k(window,"keydown",ze))}function Ce(t){for(;!((t=t.parentNode).offsetWidth&&t.offsetHeight||t===document.body););return t}function Ze(t){var e=t.getBoundingClientRect();return{x:e.width/t.offsetWidth||1,y:e.height/t.offsetHeight||1,boundingClientRect:e}}ae="onselectstart"in document?(re=function(){S(window,"selectstart",O)},function(){k(window,"selectstart",O)}):(se=we(["userSelect","WebkitUserSelect","OUserSelect","MozUserSelect","msUserSelect"]),re=function(){var t;se&&(t=document.documentElement.style,oe=t[se],t[se]="none")},function(){se&&(document.documentElement.style[se]=oe,oe=void 0)});pt={__proto__:null,TRANSFORM:ue,TRANSITION:ce,TRANSITION_END:de,get:_e,getStyle:pe,create:P,remove:T,empty:me,toFront:fe,toBack:ge,hasClass:ve,addClass:M,removeClass:z,setClass:ye,getClass:xe,setOpacity:C,testProp:we,setTransform:be,setPosition:Z,getPosition:Pe,get disableTextSelection(){return re},get enableTextSelection(){return ae},disableImageDrag:Le,enableImageDrag:Te,preventOutline:Me,restoreOutline:ze,getSizedParentNode:Ce,getScale:Ze};function S(t,e,i,n){if(e&&"object"==typeof e)for(var o in e)ke(t,o,e[o],i);else for(var s=0,r=(e=F(e)).length;s<r;s++)ke(t,e[s],i,n);return this}var E="_leaflet_events";function k(t,e,i,n){if(1===arguments.length)Se(t),delete t[E];else if(e&&"object"==typeof e)for(var o in e)Oe(t,o,e[o],i);else if(e=F(e),2===arguments.length)Se(t,function(t){return-1!==G(e,t)});else for(var s=0,r=e.length;s<r;s++)Oe(t,e[s],i,n);return this}function Se(t,e){for(var i in t[E]){var n=i.split(/\d/)[0];e&&!e(n)||Oe(t,n,null,null,i)}}var Ee={mouseenter:"mouseover",mouseleave:"mouseout",wheel:!("onwheel"in window)&&"mousewheel"};function ke(e,t,i,n){var o,s,r=t+h(i)+(n?"_"+h(n):"");e[E]&&e[E][r]||(s=o=function(t){return i.call(n||e,t||window.event)},!b.touchNative&&b.pointer&&0===t.indexOf("touch")?o=Jt(e,t,o):b.touch&&"dblclick"===t?o=ne(e,o):"addEventListener"in e?"touchstart"===t||"touchmove"===t||"wheel"===t||"mousewheel"===t?e.addEventListener(Ee[t]||t,o,!!b.passiveEvents&&{passive:!1}):"mouseenter"===t||"mouseleave"===t?e.addEventListener(Ee[t],o=function(t){t=t||window.event,We(e,t)&&s(t)},!1):e.addEventListener(t,s,!1):e.attachEvent("on"+t,o),e[E]=e[E]||{},e[E][r]=o)}function Oe(t,e,i,n,o){o=o||e+h(i)+(n?"_"+h(n):"");var s,r,i=t[E]&&t[E][o];i&&(!b.touchNative&&b.pointer&&0===e.indexOf("touch")?(n=t,r=i,Gt[s=e]?n.removeEventListener(Gt[s],r,!1):console.warn("wrong event specified:",s)):b.touch&&"dblclick"===e?(n=i,(r=t).removeEventListener("dblclick",n.dblclick),r.removeEventListener("click",n.simDblclick)):"removeEventListener"in t?t.removeEventListener(Ee[e]||e,i,!1):t.detachEvent("on"+e,i),t[E][o]=null)}function Ae(t){return t.stopPropagation?t.stopPropagation():t.originalEvent?t.originalEvent._stopped=!0:t.cancelBubble=!0,this}function Be(t){return ke(t,"wheel",Ae),this}function Ie(t){return S(t,"mousedown touchstart dblclick contextmenu",Ae),t._leaflet_disable_click=!0,this}function O(t){return t.preventDefault?t.preventDefault():t.returnValue=!1,this}function Re(t){return O(t),Ae(t),this}function Ne(t){if(t.composedPath)return t.composedPath();for(var e=[],i=t.target;i;)e.push(i),i=i.parentNode;return e}function De(t,e){var i,n;return e?(n=(i=Ze(e)).boundingClientRect,new p((t.clientX-n.left)/i.x-e.clientLeft,(t.clientY-n.top)/i.y-e.clientTop)):new p(t.clientX,t.clientY)}var je=b.linux&&b.chrome?window.devicePixelRatio:b.mac?3*window.devicePixelRatio:0<window.devicePixelRatio?2*window.devicePixelRatio:1;function He(t){return b.edge?t.wheelDeltaY/2:t.deltaY&&0===t.deltaMode?-t.deltaY/je:t.deltaY&&1===t.deltaMode?20*-t.deltaY:t.deltaY&&2===t.deltaMode?60*-t.deltaY:t.deltaX||t.deltaZ?0:t.wheelDelta?(t.wheelDeltaY||t.wheelDelta)/2:t.detail&&Math.abs(t.detail)<32765?20*-t.detail:t.detail?t.detail/-32765*60:0}function We(t,e){var i=e.relatedTarget;if(!i)return!0;try{for(;i&&i!==t;)i=i.parentNode}catch(t){return!1}return i!==t}var mt={__proto__:null,on:S,off:k,stopPropagation:Ae,disableScrollPropagation:Be,disableClickPropagation:Ie,preventDefault:O,stop:Re,getPropagationPath:Ne,getMousePosition:De,getWheelDelta:He,isExternalTarget:We,addListener:S,removeListener:k},Fe=it.extend({run:function(t,e,i,n){this.stop(),this._el=t,this._inProgress=!0,this._duration=i||.25,this._easeOutPower=1/Math.max(n||.5,.2),this._startPos=Pe(t),this._offset=e.subtract(this._startPos),this._startTime=+new Date,this.fire("start"),this._animate()},stop:function(){this._inProgress&&(this._step(!0),this._complete())},_animate:function(){this._animId=x(this._animate,this),this._step()},_step:function(t){var e=+new Date-this._startTime,i=1e3*this._duration;e<i?this._runFrame(this._easeOut(e/i),t):(this._runFrame(1),this._complete())},_runFrame:function(t,e){t=this._startPos.add(this._offset.multiplyBy(t));e&&t._round(),Z(this._el,t),this.fire("step")},_complete:function(){r(this._animId),this._inProgress=!1,this.fire("end")},_easeOut:function(t){return 1-Math.pow(1-t,this._easeOutPower)}}),A=it.extend({options:{crs:lt,center:void 0,zoom:void 0,minZoom:void 0,maxZoom:void 0,layers:[],maxBounds:void 0,renderer:void 0,zoomAnimation:!0,zoomAnimationThreshold:4,fadeAnimation:!0,markerZoomAnimation:!0,transform3DLimit:8388608,zoomSnap:1,zoomDelta:1,trackResize:!0},initialize:function(t,e){e=c(this,e),this._handlers=[],this._layers={},this._zoomBoundLayers={},this._sizeChanged=!0,this._initContainer(t),this._initLayout(),this._onResize=a(this._onResize,this),this._initEvents(),e.maxBounds&&this.setMaxBounds(e.maxBounds),void 0!==e.zoom&&(this._zoom=this._limitZoom(e.zoom)),e.center&&void 0!==e.zoom&&this.setView(w(e.center),e.zoom,{reset:!0}),this.callInitHooks(),this._zoomAnimated=ce&&b.any3d&&!b.mobileOpera&&this.options.zoomAnimation,this._zoomAnimated&&(this._createAnimProxy(),S(this._proxy,de,this._catchTransitionEnd,this)),this._addLayers(this.options.layers)},setView:function(t,e,i){if((e=void 0===e?this._zoom:this._limitZoom(e),t=this._limitCenter(w(t),e,this.options.maxBounds),i=i||{},this._stop(),this._loaded&&!i.reset&&!0!==i)&&(void 0!==i.animate&&(i.zoom=l({animate:i.animate},i.zoom),i.pan=l({animate:i.animate,duration:i.duration},i.pan)),this._zoom!==e?this._tryAnimatedZoom&&this._tryAnimatedZoom(t,e,i.zoom):this._tryAnimatedPan(t,i.pan)))return clearTimeout(this._sizeTimer),this;return this._resetView(t,e,i.pan&&i.pan.noMoveStart),this},setZoom:function(t,e){return this._loaded?this.setView(this.getCenter(),t,{zoom:e}):(this._zoom=t,this)},zoomIn:function(t,e){return t=t||(b.any3d?this.options.zoomDelta:1),this.setZoom(this._zoom+t,e)},zoomOut:function(t,e){return t=t||(b.any3d?this.options.zoomDelta:1),this.setZoom(this._zoom-t,e)},setZoomAround:function(t,e,i){var n=this.getZoomScale(e),o=this.getSize().divideBy(2),t=(t instanceof p?t:this.latLngToContainerPoint(t)).subtract(o).multiplyBy(1-1/n),n=this.containerPointToLatLng(o.add(t));return this.setView(n,e,{zoom:i})},_getBoundsCenterZoom:function(t,e){e=e||{},t=t.getBounds?t.getBounds():g(t);var i=m(e.paddingTopLeft||e.padding||[0,0]),n=m(e.paddingBottomRight||e.padding||[0,0]),o=this.getBoundsZoom(t,!1,i.add(n));return(o="number"==typeof e.maxZoom?Math.min(e.maxZoom,o):o)===1/0?{center:t.getCenter(),zoom:o}:(e=n.subtract(i).divideBy(2),n=this.project(t.getSouthWest(),o),i=this.project(t.getNorthEast(),o),{center:this.unproject(n.add(i).divideBy(2).add(e),o),zoom:o})},fitBounds:function(t,e){if((t=g(t)).isValid())return t=this._getBoundsCenterZoom(t,e),this.setView(t.center,t.zoom,e);throw new Error("Bounds are not valid.")},fitWorld:function(t){return this.fitBounds([[-90,-180],[90,180]],t)},panTo:function(t,e){return this.setView(t,this._zoom,{pan:e})},panBy:function(t,e){var i;return e=e||{},(t=m(t).round()).x||t.y?(!0===e.animate||this.getSize().contains(t)?(this._panAnim||(this._panAnim=new Fe,this._panAnim.on({step:this._onPanTransitionStep,end:this._onPanTransitionEnd},this)),e.noMoveStart||this.fire("movestart"),!1!==e.animate?(M(this._mapPane,"leaflet-pan-anim"),i=this._getMapPanePos().subtract(t).round(),this._panAnim.run(this._mapPane,i,e.duration||.25,e.easeLinearity)):(this._rawPanBy(t),this.fire("move").fire("moveend"))):this._resetView(this.unproject(this.project(this.getCenter()).add(t)),this.getZoom()),this):this.fire("moveend")},flyTo:function(n,o,t){if(!1===(t=t||{}).animate||!b.any3d)return this.setView(n,o,t);this._stop();var s=this.project(this.getCenter()),r=this.project(n),e=this.getSize(),a=this._zoom,h=(n=w(n),o=void 0===o?a:o,Math.max(e.x,e.y)),i=h*this.getZoomScale(a,o),l=r.distanceTo(s)||1,u=1.42,c=u*u;function d(t){t=(i*i-h*h+(t?-1:1)*c*c*l*l)/(2*(t?i:h)*c*l),t=Math.sqrt(t*t+1)-t;return t<1e-9?-18:Math.log(t)}function _(t){return(Math.exp(t)-Math.exp(-t))/2}function p(t){return(Math.exp(t)+Math.exp(-t))/2}var m=d(0);function f(t){return h*(p(m)*(_(t=m+u*t)/p(t))-_(m))/c}var g=Date.now(),v=(d(1)-m)/u,y=t.duration?1e3*t.duration:1e3*v*.8;return this._moveStart(!0,t.noMoveStart),function t(){var e=(Date.now()-g)/y,i=(1-Math.pow(1-e,1.5))*v;e<=1?(this._flyToFrame=x(t,this),this._move(this.unproject(s.add(r.subtract(s).multiplyBy(f(i)/l)),a),this.getScaleZoom(h/(e=i,h*(p(m)/p(m+u*e))),a),{flyTo:!0})):this._move(n,o)._moveEnd(!0)}.call(this),this},flyToBounds:function(t,e){t=this._getBoundsCenterZoom(t,e);return this.flyTo(t.center,t.zoom,e)},setMaxBounds:function(t){return t=g(t),this.listens("moveend",this._panInsideMaxBounds)&&this.off("moveend",this._panInsideMaxBounds),t.isValid()?(this.options.maxBounds=t,this._loaded&&this._panInsideMaxBounds(),this.on("moveend",this._panInsideMaxBounds)):(this.options.maxBounds=null,this)},setMinZoom:function(t){var e=this.options.minZoom;return this.options.minZoom=t,this._loaded&&e!==t&&(this.fire("zoomlevelschange"),this.getZoom()<this.options.minZoom)?this.setZoom(t):this},setMaxZoom:function(t){var e=this.options.maxZoom;return this.options.maxZoom=t,this._loaded&&e!==t&&(this.fire("zoomlevelschange"),this.getZoom()>this.options.maxZoom)?this.setZoom(t):this},panInsideBounds:function(t,e){this._enforcingBounds=!0;var i=this.getCenter(),t=this._limitCenter(i,this._zoom,g(t));return i.equals(t)||this.panTo(t,e),this._enforcingBounds=!1,this},panInside:function(t,e){var i=m((e=e||{}).paddingTopLeft||e.padding||[0,0]),n=m(e.paddingBottomRight||e.padding||[0,0]),o=this.project(this.getCenter()),t=this.project(t),s=this.getPixelBounds(),i=_([s.min.add(i),s.max.subtract(n)]),s=i.getSize();return i.contains(t)||(this._enforcingBounds=!0,n=t.subtract(i.getCenter()),i=i.extend(t).getSize().subtract(s),o.x+=n.x<0?-i.x:i.x,o.y+=n.y<0?-i.y:i.y,this.panTo(this.unproject(o),e),this._enforcingBounds=!1),this},invalidateSize:function(t){if(!this._loaded)return this;t=l({animate:!1,pan:!0},!0===t?{animate:!0}:t);var e=this.getSize(),i=(this._sizeChanged=!0,this._lastCenter=null,this.getSize()),n=e.divideBy(2).round(),o=i.divideBy(2).round(),n=n.subtract(o);return n.x||n.y?(t.animate&&t.pan?this.panBy(n):(t.pan&&this._rawPanBy(n),this.fire("move"),t.debounceMoveend?(clearTimeout(this._sizeTimer),this._sizeTimer=setTimeout(a(this.fire,this,"moveend"),200)):this.fire("moveend")),this.fire("resize",{oldSize:e,newSize:i})):this},stop:function(){return this.setZoom(this._limitZoom(this._zoom)),this.options.zoomSnap||this.fire("viewreset"),this._stop()},locate:function(t){var e,i;return t=this._locateOptions=l({timeout:1e4,watch:!1},t),"geolocation"in navigator?(e=a(this._handleGeolocationResponse,this),i=a(this._handleGeolocationError,this),t.watch?this._locationWatchId=navigator.geolocation.watchPosition(e,i,t):navigator.geolocation.getCurrentPosition(e,i,t)):this._handleGeolocationError({code:0,message:"Geolocation not supported."}),this},stopLocate:function(){return navigator.geolocation&&navigator.geolocation.clearWatch&&navigator.geolocation.clearWatch(this._locationWatchId),this._locateOptions&&(this._locateOptions.setView=!1),this},_handleGeolocationError:function(t){var e;this._container._leaflet_id&&(e=t.code,t=t.message||(1===e?"permission denied":2===e?"position unavailable":"timeout"),this._locateOptions.setView&&!this._loaded&&this.fitWorld(),this.fire("locationerror",{code:e,message:"Geolocation error: "+t+"."}))},_handleGeolocationResponse:function(t){if(this._container._leaflet_id){var e,i,n=new v(t.coords.latitude,t.coords.longitude),o=n.toBounds(2*t.coords.accuracy),s=this._locateOptions,r=(s.setView&&(e=this.getBoundsZoom(o),this.setView(n,s.maxZoom?Math.min(e,s.maxZoom):e)),{latlng:n,bounds:o,timestamp:t.timestamp});for(i in t.coords)"number"==typeof t.coords[i]&&(r[i]=t.coords[i]);this.fire("locationfound",r)}},addHandler:function(t,e){return e&&(e=this[t]=new e(this),this._handlers.push(e),this.options[t]&&e.enable()),this},remove:function(){if(this._initEvents(!0),this.options.maxBounds&&this.off("moveend",this._panInsideMaxBounds),this._containerId!==this._container._leaflet_id)throw new Error("Map container is being reused by another instance");try{delete this._container._leaflet_id,delete this._containerId}catch(t){this._container._leaflet_id=void 0,this._containerId=void 0}for(var t in void 0!==this._locationWatchId&&this.stopLocate(),this._stop(),T(this._mapPane),this._clearControlPos&&this._clearControlPos(),this._resizeRequest&&(r(this._resizeRequest),this._resizeRequest=null),this._clearHandlers(),this._loaded&&this.fire("unload"),this._layers)this._layers[t].remove();for(t in this._panes)T(this._panes[t]);return this._layers=[],this._panes=[],delete this._mapPane,delete this._renderer,this},createPane:function(t,e){e=P("div","leaflet-pane"+(t?" leaflet-"+t.replace("Pane","")+"-pane":""),e||this._mapPane);return t&&(this._panes[t]=e),e},getCenter:function(){return this._checkIfLoaded(),this._lastCenter&&!this._moved()?this._lastCenter.clone():this.layerPointToLatLng(this._getCenterLayerPoint())},getZoom:function(){return this._zoom},getBounds:function(){var t=this.getPixelBounds();return new s(this.unproject(t.getBottomLeft()),this.unproject(t.getTopRight()))},getMinZoom:function(){return void 0===this.options.minZoom?this._layersMinZoom||0:this.options.minZoom},getMaxZoom:function(){return void 0===this.options.maxZoom?void 0===this._layersMaxZoom?1/0:this._layersMaxZoom:this.options.maxZoom},getBoundsZoom:function(t,e,i){t=g(t),i=m(i||[0,0]);var n=this.getZoom()||0,o=this.getMinZoom(),s=this.getMaxZoom(),r=t.getNorthWest(),t=t.getSouthEast(),i=this.getSize().subtract(i),t=_(this.project(t,n),this.project(r,n)).getSize(),r=b.any3d?this.options.zoomSnap:1,a=i.x/t.x,i=i.y/t.y,t=e?Math.max(a,i):Math.min(a,i),n=this.getScaleZoom(t,n);return r&&(n=Math.round(n/(r/100))*(r/100),n=e?Math.ceil(n/r)*r:Math.floor(n/r)*r),Math.max(o,Math.min(s,n))},getSize:function(){return this._size&&!this._sizeChanged||(this._size=new p(this._container.clientWidth||0,this._container.clientHeight||0),this._sizeChanged=!1),this._size.clone()},getPixelBounds:function(t,e){t=this._getTopLeftPoint(t,e);return new f(t,t.add(this.getSize()))},getPixelOrigin:function(){return this._checkIfLoaded(),this._pixelOrigin},getPixelWorldBounds:function(t){return this.options.crs.getProjectedBounds(void 0===t?this.getZoom():t)},getPane:function(t){return"string"==typeof t?this._panes[t]:t},getPanes:function(){return this._panes},getContainer:function(){return this._container},getZoomScale:function(t,e){var i=this.options.crs;return e=void 0===e?this._zoom:e,i.scale(t)/i.scale(e)},getScaleZoom:function(t,e){var i=this.options.crs,t=(e=void 0===e?this._zoom:e,i.zoom(t*i.scale(e)));return isNaN(t)?1/0:t},project:function(t,e){return e=void 0===e?this._zoom:e,this.options.crs.latLngToPoint(w(t),e)},unproject:function(t,e){return e=void 0===e?this._zoom:e,this.options.crs.pointToLatLng(m(t),e)},layerPointToLatLng:function(t){t=m(t).add(this.getPixelOrigin());return this.unproject(t)},latLngToLayerPoint:function(t){return this.project(w(t))._round()._subtract(this.getPixelOrigin())},wrapLatLng:function(t){return this.options.crs.wrapLatLng(w(t))},wrapLatLngBounds:function(t){return this.options.crs.wrapLatLngBounds(g(t))},distance:function(t,e){return this.options.crs.distance(w(t),w(e))},containerPointToLayerPoint:function(t){return m(t).subtract(this._getMapPanePos())},layerPointToContainerPoint:function(t){return m(t).add(this._getMapPanePos())},containerPointToLatLng:function(t){t=this.containerPointToLayerPoint(m(t));return this.layerPointToLatLng(t)},latLngToContainerPoint:function(t){return this.layerPointToContainerPoint(this.latLngToLayerPoint(w(t)))},mouseEventToContainerPoint:function(t){return De(t,this._container)},mouseEventToLayerPoint:function(t){return this.containerPointToLayerPoint(this.mouseEventToContainerPoint(t))},mouseEventToLatLng:function(t){return this.layerPointToLatLng(this.mouseEventToLayerPoint(t))},_initContainer:function(t){t=this._container=_e(t);if(!t)throw new Error("Map container not found.");if(t._leaflet_id)throw new Error("Map container is already initialized.");S(t,"scroll",this._onScroll,this),this._containerId=h(t)},_initLayout:function(){var t=this._container,e=(this._fadeAnimated=this.options.fadeAnimation&&b.any3d,M(t,"leaflet-container"+(b.touch?" leaflet-touch":"")+(b.retina?" leaflet-retina":"")+(b.ielt9?" leaflet-oldie":"")+(b.safari?" leaflet-safari":"")+(this._fadeAnimated?" leaflet-fade-anim":"")),pe(t,"position"));"absolute"!==e&&"relative"!==e&&"fixed"!==e&&"sticky"!==e&&(t.style.position="relative"),this._initPanes(),this._initControlPos&&this._initControlPos()},_initPanes:function(){var t=this._panes={};this._paneRenderers={},this._mapPane=this.createPane("mapPane",this._container),Z(this._mapPane,new p(0,0)),this.createPane("tilePane"),this.createPane("overlayPane"),this.createPane("shadowPane"),this.createPane("markerPane"),this.createPane("tooltipPane"),this.createPane("popupPane"),this.options.markerZoomAnimation||(M(t.markerPane,"leaflet-zoom-hide"),M(t.shadowPane,"leaflet-zoom-hide"))},_resetView:function(t,e,i){Z(this._mapPane,new p(0,0));var n=!this._loaded,o=(this._loaded=!0,e=this._limitZoom(e),this.fire("viewprereset"),this._zoom!==e);this._moveStart(o,i)._move(t,e)._moveEnd(o),this.fire("viewreset"),n&&this.fire("load")},_moveStart:function(t,e){return t&&this.fire("zoomstart"),e||this.fire("movestart"),this},_move:function(t,e,i,n){void 0===e&&(e=this._zoom);var o=this._zoom!==e;return this._zoom=e,this._lastCenter=t,this._pixelOrigin=this._getNewPixelOrigin(t),n?i&&i.pinch&&this.fire("zoom",i):((o||i&&i.pinch)&&this.fire("zoom",i),this.fire("move",i)),this},_moveEnd:function(t){return t&&this.fire("zoomend"),this.fire("moveend")},_stop:function(){return r(this._flyToFrame),this._panAnim&&this._panAnim.stop(),this},_rawPanBy:function(t){Z(this._mapPane,this._getMapPanePos().subtract(t))},_getZoomSpan:function(){return this.getMaxZoom()-this.getMinZoom()},_panInsideMaxBounds:function(){this._enforcingBounds||this.panInsideBounds(this.options.maxBounds)},_checkIfLoaded:function(){if(!this._loaded)throw new Error("Set map center and zoom first.")},_initEvents:function(t){this._targets={};var e=t?k:S;e((this._targets[h(this._container)]=this)._container,"click dblclick mousedown mouseup mouseover mouseout mousemove contextmenu keypress keydown keyup",this._handleDOMEvent,this),this.options.trackResize&&e(window,"resize",this._onResize,this),b.any3d&&this.options.transform3DLimit&&(t?this.off:this.on).call(this,"moveend",this._onMoveEnd)},_onResize:function(){r(this._resizeRequest),this._resizeRequest=x(function(){this.invalidateSize({debounceMoveend:!0})},this)},_onScroll:function(){this._container.scrollTop=0,this._container.scrollLeft=0},_onMoveEnd:function(){var t=this._getMapPanePos();Math.max(Math.abs(t.x),Math.abs(t.y))>=this.options.transform3DLimit&&this._resetView(this.getCenter(),this.getZoom())},_findEventTargets:function(t,e){for(var i,n=[],o="mouseout"===e||"mouseover"===e,s=t.target||t.srcElement,r=!1;s;){if((i=this._targets[h(s)])&&("click"===e||"preclick"===e)&&this._draggableMoved(i)){r=!0;break}if(i&&i.listens(e,!0)){if(o&&!We(s,t))break;if(n.push(i),o)break}if(s===this._container)break;s=s.parentNode}return n=n.length||r||o||!this.listens(e,!0)?n:[this]},_isClickDisabled:function(t){for(;t&&t!==this._container;){if(t._leaflet_disable_click)return!0;t=t.parentNode}},_handleDOMEvent:function(t){var e,i=t.target||t.srcElement;!this._loaded||i._leaflet_disable_events||"click"===t.type&&this._isClickDisabled(i)||("mousedown"===(e=t.type)&&Me(i),this._fireDOMEvent(t,e))},_mouseEvents:["click","dblclick","mouseover","mouseout","contextmenu"],_fireDOMEvent:function(t,e,i){"click"===t.type&&((a=l({},t)).type="preclick",this._fireDOMEvent(a,a.type,i));var n=this._findEventTargets(t,e);if(i){for(var o=[],s=0;s<i.length;s++)i[s].listens(e,!0)&&o.push(i[s]);n=o.concat(n)}if(n.length){"contextmenu"===e&&O(t);var r,a=n[0],h={originalEvent:t};for("keypress"!==t.type&&"keydown"!==t.type&&"keyup"!==t.type&&(r=a.getLatLng&&(!a._radius||a._radius<=10),h.containerPoint=r?this.latLngToContainerPoint(a.getLatLng()):this.mouseEventToContainerPoint(t),h.layerPoint=this.containerPointToLayerPoint(h.containerPoint),h.latlng=r?a.getLatLng():this.layerPointToLatLng(h.layerPoint)),s=0;s<n.length;s++)if(n[s].fire(e,h,!0),h.originalEvent._stopped||!1===n[s].options.bubblingMouseEvents&&-1!==G(this._mouseEvents,e))return}},_draggableMoved:function(t){return(t=t.dragging&&t.dragging.enabled()?t:this).dragging&&t.dragging.moved()||this.boxZoom&&this.boxZoom.moved()},_clearHandlers:function(){for(var t=0,e=this._handlers.length;t<e;t++)this._handlers[t].disable()},whenReady:function(t,e){return this._loaded?t.call(e||this,{target:this}):this.on("load",t,e),this},_getMapPanePos:function(){return Pe(this._mapPane)||new p(0,0)},_moved:function(){var t=this._getMapPanePos();return t&&!t.equals([0,0])},_getTopLeftPoint:function(t,e){return(t&&void 0!==e?this._getNewPixelOrigin(t,e):this.getPixelOrigin()).subtract(this._getMapPanePos())},_getNewPixelOrigin:function(t,e){var i=this.getSize()._divideBy(2);return this.project(t,e)._subtract(i)._add(this._getMapPanePos())._round()},_latLngToNewLayerPoint:function(t,e,i){i=this._getNewPixelOrigin(i,e);return this.project(t,e)._subtract(i)},_latLngBoundsToNewLayerBounds:function(t,e,i){i=this._getNewPixelOrigin(i,e);return _([this.project(t.getSouthWest(),e)._subtract(i),this.project(t.getNorthWest(),e)._subtract(i),this.project(t.getSouthEast(),e)._subtract(i),this.project(t.getNorthEast(),e)._subtract(i)])},_getCenterLayerPoint:function(){return this.containerPointToLayerPoint(this.getSize()._divideBy(2))},_getCenterOffset:function(t){return this.latLngToLayerPoint(t).subtract(this._getCenterLayerPoint())},_limitCenter:function(t,e,i){var n,o;return!i||(n=this.project(t,e),o=this.getSize().divideBy(2),o=new f(n.subtract(o),n.add(o)),o=this._getBoundsOffset(o,i,e),Math.abs(o.x)<=1&&Math.abs(o.y)<=1)?t:this.unproject(n.add(o),e)},_limitOffset:function(t,e){var i;return e?(i=new f((i=this.getPixelBounds()).min.add(t),i.max.add(t)),t.add(this._getBoundsOffset(i,e))):t},_getBoundsOffset:function(t,e,i){e=_(this.project(e.getNorthEast(),i),this.project(e.getSouthWest(),i)),i=e.min.subtract(t.min),e=e.max.subtract(t.max);return new p(this._rebound(i.x,-e.x),this._rebound(i.y,-e.y))},_rebound:function(t,e){return 0<t+e?Math.round(t-e)/2:Math.max(0,Math.ceil(t))-Math.max(0,Math.floor(e))},_limitZoom:function(t){var e=this.getMinZoom(),i=this.getMaxZoom(),n=b.any3d?this.options.zoomSnap:1;return n&&(t=Math.round(t/n)*n),Math.max(e,Math.min(i,t))},_onPanTransitionStep:function(){this.fire("move")},_onPanTransitionEnd:function(){z(this._mapPane,"leaflet-pan-anim"),this.fire("moveend")},_tryAnimatedPan:function(t,e){t=this._getCenterOffset(t)._trunc();return!(!0!==(e&&e.animate)&&!this.getSize().contains(t))&&(this.panBy(t,e),!0)},_createAnimProxy:function(){var t=this._proxy=P("div","leaflet-proxy leaflet-zoom-animated");this._panes.mapPane.appendChild(t),this.on("zoomanim",function(t){var e=ue,i=this._proxy.style[e];be(this._proxy,this.project(t.center,t.zoom),this.getZoomScale(t.zoom,1)),i===this._proxy.style[e]&&this._animatingZoom&&this._onZoomTransitionEnd()},this),this.on("load moveend",this._animMoveEnd,this),this._on("unload",this._destroyAnimProxy,this)},_destroyAnimProxy:function(){T(this._proxy),this.off("load moveend",this._animMoveEnd,this),delete this._proxy},_animMoveEnd:function(){var t=this.getCenter(),e=this.getZoom();be(this._proxy,this.project(t,e),this.getZoomScale(e,1))},_catchTransitionEnd:function(t){this._animatingZoom&&0<=t.propertyName.indexOf("transform")&&this._onZoomTransitionEnd()},_nothingToAnimate:function(){return!this._container.getElementsByClassName("leaflet-zoom-animated").length},_tryAnimatedZoom:function(t,e,i){if(!this._animatingZoom){if(i=i||{},!this._zoomAnimated||!1===i.animate||this._nothingToAnimate()||Math.abs(e-this._zoom)>this.options.zoomAnimationThreshold)return!1;var n=this.getZoomScale(e),n=this._getCenterOffset(t)._divideBy(1-1/n);if(!0!==i.animate&&!this.getSize().contains(n))return!1;x(function(){this._moveStart(!0,i.noMoveStart||!1)._animateZoom(t,e,!0)},this)}return!0},_animateZoom:function(t,e,i,n){this._mapPane&&(i&&(this._animatingZoom=!0,this._animateToCenter=t,this._animateToZoom=e,M(this._mapPane,"leaflet-zoom-anim")),this.fire("zoomanim",{center:t,zoom:e,noUpdate:n}),this._tempFireZoomEvent||(this._tempFireZoomEvent=this._zoom!==this._animateToZoom),this._move(this._animateToCenter,this._animateToZoom,void 0,!0),setTimeout(a(this._onZoomTransitionEnd,this),250))},_onZoomTransitionEnd:function(){this._animatingZoom&&(this._mapPane&&z(this._mapPane,"leaflet-zoom-anim"),this._animatingZoom=!1,this._move(this._animateToCenter,this._animateToZoom,void 0,!0),this._tempFireZoomEvent&&this.fire("zoom"),delete this._tempFireZoomEvent,this.fire("move"),this._moveEnd(!0))}});function Ue(t){return new B(t)}var B=et.extend({options:{position:"topright"},initialize:function(t){c(this,t)},getPosition:function(){return this.options.position},setPosition:function(t){var e=this._map;return e&&e.removeControl(this),this.options.position=t,e&&e.addControl(this),this},getContainer:function(){return this._container},addTo:function(t){this.remove(),this._map=t;var e=this._container=this.onAdd(t),i=this.getPosition(),t=t._controlCorners[i];return M(e,"leaflet-control"),-1!==i.indexOf("bottom")?t.insertBefore(e,t.firstChild):t.appendChild(e),this._map.on("unload",this.remove,this),this},remove:function(){return this._map&&(T(this._container),this.onRemove&&this.onRemove(this._map),this._map.off("unload",this.remove,this),this._map=null),this},_refocusOnMap:function(t){this._map&&t&&0<t.screenX&&0<t.screenY&&this._map.getContainer().focus()}}),Ve=(A.include({addControl:function(t){return t.addTo(this),this},removeControl:function(t){return t.remove(),this},_initControlPos:function(){var i=this._controlCorners={},n="leaflet-",o=this._controlContainer=P("div",n+"control-container",this._container);function t(t,e){i[t+e]=P("div",n+t+" "+n+e,o)}t("top","left"),t("top","right"),t("bottom","left"),t("bottom","right")},_clearControlPos:function(){for(var t in this._controlCorners)T(this._controlCorners[t]);T(this._controlContainer),delete this._controlCorners,delete this._controlContainer}}),B.extend({options:{collapsed:!0,position:"topright",autoZIndex:!0,hideSingleBase:!1,sortLayers:!1,sortFunction:function(t,e,i,n){return i<n?-1:n<i?1:0}},initialize:function(t,e,i){for(var n in c(this,i),this._layerControlInputs=[],this._layers=[],this._lastZIndex=0,this._handlingClick=!1,this._preventClick=!1,t)this._addLayer(t[n],n);for(n in e)this._addLayer(e[n],n,!0)},onAdd:function(t){this._initLayout(),this._update(),(this._map=t).on("zoomend",this._checkDisabledLayers,this);for(var e=0;e<this._layers.length;e++)this._layers[e].layer.on("add remove",this._onLayerChange,this);return this._container},addTo:function(t){return B.prototype.addTo.call(this,t),this._expandIfNotCollapsed()},onRemove:function(){this._map.off("zoomend",this._checkDisabledLayers,this);for(var t=0;t<this._layers.length;t++)this._layers[t].layer.off("add remove",this._onLayerChange,this)},addBaseLayer:function(t,e){return this._addLayer(t,e),this._map?this._update():this},addOverlay:function(t,e){return this._addLayer(t,e,!0),this._map?this._update():this},removeLayer:function(t){t.off("add remove",this._onLayerChange,this);t=this._getLayer(h(t));return t&&this._layers.splice(this._layers.indexOf(t),1),this._map?this._update():this},expand:function(){M(this._container,"leaflet-control-layers-expanded"),this._section.style.height=null;var t=this._map.getSize().y-(this._container.offsetTop+50);return t<this._section.clientHeight?(M(this._section,"leaflet-control-layers-scrollbar"),this._section.style.height=t+"px"):z(this._section,"leaflet-control-layers-scrollbar"),this._checkDisabledLayers(),this},collapse:function(){return z(this._container,"leaflet-control-layers-expanded"),this},_initLayout:function(){var t="leaflet-control-layers",e=this._container=P("div",t),i=this.options.collapsed,n=(e.setAttribute("aria-haspopup",!0),Ie(e),Be(e),this._section=P("section",t+"-list")),o=(i&&(this._map.on("click",this.collapse,this),S(e,{mouseenter:this._expandSafely,mouseleave:this.collapse},this)),this._layersLink=P("a",t+"-toggle",e));o.href="#",o.title="Layers",o.setAttribute("role","button"),S(o,{keydown:function(t){13===t.keyCode&&this._expandSafely()},click:function(t){O(t),this._expandSafely()}},this),i||this.expand(),this._baseLayersList=P("div",t+"-base",n),this._separator=P("div",t+"-separator",n),this._overlaysList=P("div",t+"-overlays",n),e.appendChild(n)},_getLayer:function(t){for(var e=0;e<this._layers.length;e++)if(this._layers[e]&&h(this._layers[e].layer)===t)return this._layers[e]},_addLayer:function(t,e,i){this._map&&t.on("add remove",this._onLayerChange,this),this._layers.push({layer:t,name:e,overlay:i}),this.options.sortLayers&&this._layers.sort(a(function(t,e){return this.options.sortFunction(t.layer,e.layer,t.name,e.name)},this)),this.options.autoZIndex&&t.setZIndex&&(this._lastZIndex++,t.setZIndex(this._lastZIndex)),this._expandIfNotCollapsed()},_update:function(){if(this._container){me(this._baseLayersList),me(this._overlaysList),this._layerControlInputs=[];for(var t,e,i,n=0,o=0;o<this._layers.length;o++)i=this._layers[o],this._addItem(i),e=e||i.overlay,t=t||!i.overlay,n+=i.overlay?0:1;this.options.hideSingleBase&&(this._baseLayersList.style.display=(t=t&&1<n)?"":"none"),this._separator.style.display=e&&t?"":"none"}return this},_onLayerChange:function(t){this._handlingClick||this._update();var e=this._getLayer(h(t.target)),t=e.overlay?"add"===t.type?"overlayadd":"overlayremove":"add"===t.type?"baselayerchange":null;t&&this._map.fire(t,e)},_createRadioElement:function(t,e){t='<input type="radio" class="leaflet-control-layers-selector" name="'+t+'"'+(e?' checked="checked"':"")+"/>",e=document.createElement("div");return e.innerHTML=t,e.firstChild},_addItem:function(t){var e,i=document.createElement("label"),n=this._map.hasLayer(t.layer),n=(t.overlay?((e=document.createElement("input")).type="checkbox",e.className="leaflet-control-layers-selector",e.defaultChecked=n):e=this._createRadioElement("leaflet-base-layers_"+h(this),n),this._layerControlInputs.push(e),e.layerId=h(t.layer),S(e,"click",this._onInputClick,this),document.createElement("span")),o=(n.innerHTML=" "+t.name,document.createElement("span"));return i.appendChild(o),o.appendChild(e),o.appendChild(n),(t.overlay?this._overlaysList:this._baseLayersList).appendChild(i),this._checkDisabledLayers(),i},_onInputClick:function(){if(!this._preventClick){var t,e,i=this._layerControlInputs,n=[],o=[];this._handlingClick=!0;for(var s=i.length-1;0<=s;s--)t=i[s],e=this._getLayer(t.layerId).layer,t.checked?n.push(e):t.checked||o.push(e);for(s=0;s<o.length;s++)this._map.hasLayer(o[s])&&this._map.removeLayer(o[s]);for(s=0;s<n.length;s++)this._map.hasLayer(n[s])||this._map.addLayer(n[s]);this._handlingClick=!1,this._refocusOnMap()}},_checkDisabledLayers:function(){for(var t,e,i=this._layerControlInputs,n=this._map.getZoom(),o=i.length-1;0<=o;o--)t=i[o],e=this._getLayer(t.layerId).layer,t.disabled=void 0!==e.options.minZoom&&n<e.options.minZoom||void 0!==e.options.maxZoom&&n>e.options.maxZoom},_expandIfNotCollapsed:function(){return this._map&&!this.options.collapsed&&this.expand(),this},_expandSafely:function(){var t=this._section,e=(this._preventClick=!0,S(t,"click",O),this.expand(),this);setTimeout(function(){k(t,"click",O),e._preventClick=!1})}})),qe=B.extend({options:{position:"topleft",zoomInText:'<span aria-hidden="true">+</span>',zoomInTitle:"Zoom in",zoomOutText:'<span aria-hidden="true">&#x2212;</span>',zoomOutTitle:"Zoom out"},onAdd:function(t){var e="leaflet-control-zoom",i=P("div",e+" leaflet-bar"),n=this.options;return this._zoomInButton=this._createButton(n.zoomInText,n.zoomInTitle,e+"-in",i,this._zoomIn),this._zoomOutButton=this._createButton(n.zoomOutText,n.zoomOutTitle,e+"-out",i,this._zoomOut),this._updateDisabled(),t.on("zoomend zoomlevelschange",this._updateDisabled,this),i},onRemove:function(t){t.off("zoomend zoomlevelschange",this._updateDisabled,this)},disable:function(){return this._disabled=!0,this._updateDisabled(),this},enable:function(){return this._disabled=!1,this._updateDisabled(),this},_zoomIn:function(t){!this._disabled&&this._map._zoom<this._map.getMaxZoom()&&this._map.zoomIn(this._map.options.zoomDelta*(t.shiftKey?3:1))},_zoomOut:function(t){!this._disabled&&this._map._zoom>this._map.getMinZoom()&&this._map.zoomOut(this._map.options.zoomDelta*(t.shiftKey?3:1))},_createButton:function(t,e,i,n,o){i=P("a",i,n);return i.innerHTML=t,i.href="#",i.title=e,i.setAttribute("role","button"),i.setAttribute("aria-label",e),Ie(i),S(i,"click",Re),S(i,"click",o,this),S(i,"click",this._refocusOnMap,this),i},_updateDisabled:function(){var t=this._map,e="leaflet-disabled";z(this._zoomInButton,e),z(this._zoomOutButton,e),this._zoomInButton.setAttribute("aria-disabled","false"),this._zoomOutButton.setAttribute("aria-disabled","false"),!this._disabled&&t._zoom!==t.getMinZoom()||(M(this._zoomOutButton,e),this._zoomOutButton.setAttribute("aria-disabled","true")),!this._disabled&&t._zoom!==t.getMaxZoom()||(M(this._zoomInButton,e),this._zoomInButton.setAttribute("aria-disabled","true"))}}),Ge=(A.mergeOptions({zoomControl:!0}),A.addInitHook(function(){this.options.zoomControl&&(this.zoomControl=new qe,this.addControl(this.zoomControl))}),B.extend({options:{position:"bottomleft",maxWidth:100,metric:!0,imperial:!0},onAdd:function(t){var e="leaflet-control-scale",i=P("div",e),n=this.options;return this._addScales(n,e+"-line",i),t.on(n.updateWhenIdle?"moveend":"move",this._update,this),t.whenReady(this._update,this),i},onRemove:function(t){t.off(this.options.updateWhenIdle?"moveend":"move",this._update,this)},_addScales:function(t,e,i){t.metric&&(this._mScale=P("div",e,i)),t.imperial&&(this._iScale=P("div",e,i))},_update:function(){var t=this._map,e=t.getSize().y/2,t=t.distance(t.containerPointToLatLng([0,e]),t.containerPointToLatLng([this.options.maxWidth,e]));this._updateScales(t)},_updateScales:function(t){this.options.metric&&t&&this._updateMetric(t),this.options.imperial&&t&&this._updateImperial(t)},_updateMetric:function(t){var e=this._getRoundNum(t);this._updateScale(this._mScale,e<1e3?e+" m":e/1e3+" km",e/t)},_updateImperial:function(t){var e,i,t=3.2808399*t;5280<t?(i=this._getRoundNum(e=t/5280),this._updateScale(this._iScale,i+" mi",i/e)):(i=this._getRoundNum(t),this._updateScale(this._iScale,i+" ft",i/t))},_updateScale:function(t,e,i){t.style.width=Math.round(this.options.maxWidth*i)+"px",t.innerHTML=e},_getRoundNum:function(t){var e=Math.pow(10,(Math.floor(t)+"").length-1),t=t/e;return e*(t=10<=t?10:5<=t?5:3<=t?3:2<=t?2:1)}})),Ke=B.extend({options:{position:"bottomright",prefix:'<a href="https://leafletjs.com" title="A JavaScript library for interactive maps">'+(b.inlineSvg?'<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="12" height="8" viewBox="0 0 12 8" class="leaflet-attribution-flag"><path fill="#4C7BE1" d="M0 0h12v4H0z"/><path fill="#FFD500" d="M0 4h12v3H0z"/><path fill="#E0BC00" d="M0 7h12v1H0z"/></svg> ':"")+"Leaflet</a>"},initialize:function(t){c(this,t),this._attributions={}},onAdd:function(t){for(var e in(t.attributionControl=this)._container=P("div","leaflet-control-attribution"),Ie(this._container),t._layers)t._layers[e].getAttribution&&this.addAttribution(t._layers[e].getAttribution());return this._update(),t.on("layeradd",this._addAttribution,this),this._container},onRemove:function(t){t.off("layeradd",this._addAttribution,this)},_addAttribution:function(t){t.layer.getAttribution&&(this.addAttribution(t.layer.getAttribution()),t.layer.once("remove",function(){this.removeAttribution(t.layer.getAttribution())},this))},setPrefix:function(t){return this.options.prefix=t,this._update(),this},addAttribution:function(t){return t&&(this._attributions[t]||(this._attributions[t]=0),this._attributions[t]++,this._update()),this},removeAttribution:function(t){return t&&this._attributions[t]&&(this._attributions[t]--,this._update()),this},_update:function(){if(this._map){var t,e=[];for(t in this._attributions)this._attributions[t]&&e.push(t);var i=[];this.options.prefix&&i.push(this.options.prefix),e.length&&i.push(e.join(", ")),this._container.innerHTML=i.join(' <span aria-hidden="true">|</span> ')}}}),n=(A.mergeOptions({attributionControl:!0}),A.addInitHook(function(){this.options.attributionControl&&(new Ke).addTo(this)}),B.Layers=Ve,B.Zoom=qe,B.Scale=Ge,B.Attribution=Ke,Ue.layers=function(t,e,i){return new Ve(t,e,i)},Ue.zoom=function(t){return new qe(t)},Ue.scale=function(t){return new Ge(t)},Ue.attribution=function(t){return new Ke(t)},et.extend({initialize:function(t){this._map=t},enable:function(){return this._enabled||(this._enabled=!0,this.addHooks()),this},disable:function(){return this._enabled&&(this._enabled=!1,this.removeHooks()),this},enabled:function(){return!!this._enabled}})),ft=(n.addTo=function(t,e){return t.addHandler(e,this),this},{Events:e}),Ye=b.touch?"touchstart mousedown":"mousedown",Xe=it.extend({options:{clickTolerance:3},initialize:function(t,e,i,n){c(this,n),this._element=t,this._dragStartTarget=e||t,this._preventOutline=i},enable:function(){this._enabled||(S(this._dragStartTarget,Ye,this._onDown,this),this._enabled=!0)},disable:function(){this._enabled&&(Xe._dragging===this&&this.finishDrag(!0),k(this._dragStartTarget,Ye,this._onDown,this),this._enabled=!1,this._moved=!1)},_onDown:function(t){var e,i;this._enabled&&(this._moved=!1,ve(this._element,"leaflet-zoom-anim")||(t.touches&&1!==t.touches.length?Xe._dragging===this&&this.finishDrag():Xe._dragging||t.shiftKey||1!==t.which&&1!==t.button&&!t.touches||((Xe._dragging=this)._preventOutline&&Me(this._element),Le(),re(),this._moving||(this.fire("down"),i=t.touches?t.touches[0]:t,e=Ce(this._element),this._startPoint=new p(i.clientX,i.clientY),this._startPos=Pe(this._element),this._parentScale=Ze(e),i="mousedown"===t.type,S(document,i?"mousemove":"touchmove",this._onMove,this),S(document,i?"mouseup":"touchend touchcancel",this._onUp,this)))))},_onMove:function(t){var e;this._enabled&&(t.touches&&1<t.touches.length?this._moved=!0:!(e=new p((e=t.touches&&1===t.touches.length?t.touches[0]:t).clientX,e.clientY)._subtract(this._startPoint)).x&&!e.y||Math.abs(e.x)+Math.abs(e.y)<this.options.clickTolerance||(e.x/=this._parentScale.x,e.y/=this._parentScale.y,O(t),this._moved||(this.fire("dragstart"),this._moved=!0,M(document.body,"leaflet-dragging"),this._lastTarget=t.target||t.srcElement,window.SVGElementInstance&&this._lastTarget instanceof window.SVGElementInstance&&(this._lastTarget=this._lastTarget.correspondingUseElement),M(this._lastTarget,"leaflet-drag-target")),this._newPos=this._startPos.add(e),this._moving=!0,this._lastEvent=t,this._updatePosition()))},_updatePosition:function(){var t={originalEvent:this._lastEvent};this.fire("predrag",t),Z(this._element,this._newPos),this.fire("drag",t)},_onUp:function(){this._enabled&&this.finishDrag()},finishDrag:function(t){z(document.body,"leaflet-dragging"),this._lastTarget&&(z(this._lastTarget,"leaflet-drag-target"),this._lastTarget=null),k(document,"mousemove touchmove",this._onMove,this),k(document,"mouseup touchend touchcancel",this._onUp,this),Te(),ae();var e=this._moved&&this._moving;this._moving=!1,Xe._dragging=!1,e&&this.fire("dragend",{noInertia:t,distance:this._newPos.distanceTo(this._startPos)})}});function Je(t,e,i){for(var n,o,s,r,a,h,l,u=[1,4,2,8],c=0,d=t.length;c<d;c++)t[c]._code=si(t[c],e);for(s=0;s<4;s++){for(h=u[s],n=[],c=0,o=(d=t.length)-1;c<d;o=c++)r=t[c],a=t[o],r._code&h?a._code&h||((l=oi(a,r,h,e,i))._code=si(l,e),n.push(l)):(a._code&h&&((l=oi(a,r,h,e,i))._code=si(l,e),n.push(l)),n.push(r));t=n}return t}function $e(t,e){var i,n,o,s,r,a,h;if(!t||0===t.length)throw new Error("latlngs not passed");I(t)||(console.warn("latlngs are not flat! Only the first ring will be used"),t=t[0]);for(var l=w([0,0]),u=g(t),c=(u.getNorthWest().distanceTo(u.getSouthWest())*u.getNorthEast().distanceTo(u.getNorthWest())<1700&&(l=Qe(t)),t.length),d=[],_=0;_<c;_++){var p=w(t[_]);d.push(e.project(w([p.lat-l.lat,p.lng-l.lng])))}for(_=r=a=h=0,i=c-1;_<c;i=_++)n=d[_],o=d[i],s=n.y*o.x-o.y*n.x,a+=(n.x+o.x)*s,h+=(n.y+o.y)*s,r+=3*s;u=0===r?d[0]:[a/r,h/r],u=e.unproject(m(u));return w([u.lat+l.lat,u.lng+l.lng])}function Qe(t){for(var e=0,i=0,n=0,o=0;o<t.length;o++){var s=w(t[o]);e+=s.lat,i+=s.lng,n++}return w([e/n,i/n])}var ti,gt={__proto__:null,clipPolygon:Je,polygonCenter:$e,centroid:Qe};function ei(t,e){if(e&&t.length){var i=t=function(t,e){for(var i=[t[0]],n=1,o=0,s=t.length;n<s;n++)(function(t,e){var i=e.x-t.x,e=e.y-t.y;return i*i+e*e})(t[n],t[o])>e&&(i.push(t[n]),o=n);o<s-1&&i.push(t[s-1]);return i}(t,e=e*e),n=i.length,o=new(typeof Uint8Array!=void 0+""?Uint8Array:Array)(n);o[0]=o[n-1]=1,function t(e,i,n,o,s){var r,a,h,l=0;for(a=o+1;a<=s-1;a++)h=ri(e[a],e[o],e[s],!0),l<h&&(r=a,l=h);n<l&&(i[r]=1,t(e,i,n,o,r),t(e,i,n,r,s))}(i,o,e,0,n-1);var s,r=[];for(s=0;s<n;s++)o[s]&&r.push(i[s]);return r}return t.slice()}function ii(t,e,i){return Math.sqrt(ri(t,e,i,!0))}function ni(t,e,i,n,o){var s,r,a,h=n?ti:si(t,i),l=si(e,i);for(ti=l;;){if(!(h|l))return[t,e];if(h&l)return!1;a=si(r=oi(t,e,s=h||l,i,o),i),s===h?(t=r,h=a):(e=r,l=a)}}function oi(t,e,i,n,o){var s,r,a=e.x-t.x,e=e.y-t.y,h=n.min,n=n.max;return 8&i?(s=t.x+a*(n.y-t.y)/e,r=n.y):4&i?(s=t.x+a*(h.y-t.y)/e,r=h.y):2&i?(s=n.x,r=t.y+e*(n.x-t.x)/a):1&i&&(s=h.x,r=t.y+e*(h.x-t.x)/a),new p(s,r,o)}function si(t,e){var i=0;return t.x<e.min.x?i|=1:t.x>e.max.x&&(i|=2),t.y<e.min.y?i|=4:t.y>e.max.y&&(i|=8),i}function ri(t,e,i,n){var o=e.x,e=e.y,s=i.x-o,r=i.y-e,a=s*s+r*r;return 0<a&&(1<(a=((t.x-o)*s+(t.y-e)*r)/a)?(o=i.x,e=i.y):0<a&&(o+=s*a,e+=r*a)),s=t.x-o,r=t.y-e,n?s*s+r*r:new p(o,e)}function I(t){return!d(t[0])||"object"!=typeof t[0][0]&&void 0!==t[0][0]}function ai(t){return console.warn("Deprecated use of _flat, please use L.LineUtil.isFlat instead."),I(t)}function hi(t,e){var i,n,o,s,r,a;if(!t||0===t.length)throw new Error("latlngs not passed");I(t)||(console.warn("latlngs are not flat! Only the first ring will be used"),t=t[0]);for(var h=w([0,0]),l=g(t),u=(l.getNorthWest().distanceTo(l.getSouthWest())*l.getNorthEast().distanceTo(l.getNorthWest())<1700&&(h=Qe(t)),t.length),c=[],d=0;d<u;d++){var _=w(t[d]);c.push(e.project(w([_.lat-h.lat,_.lng-h.lng])))}for(i=d=0;d<u-1;d++)i+=c[d].distanceTo(c[d+1])/2;if(0===i)a=c[0];else for(n=d=0;d<u-1;d++)if(o=c[d],s=c[d+1],i<(n+=r=o.distanceTo(s))){a=[s.x-(r=(n-i)/r)*(s.x-o.x),s.y-r*(s.y-o.y)];break}l=e.unproject(m(a));return w([l.lat+h.lat,l.lng+h.lng])}var vt={__proto__:null,simplify:ei,pointToSegmentDistance:ii,closestPointOnSegment:function(t,e,i){return ri(t,e,i)},clipSegment:ni,_getEdgeIntersection:oi,_getBitCode:si,_sqClosestPointOnSegment:ri,isFlat:I,_flat:ai,polylineCenter:hi},yt={project:function(t){return new p(t.lng,t.lat)},unproject:function(t){return new v(t.y,t.x)},bounds:new f([-180,-90],[180,90])},xt={R:6378137,R_MINOR:6356752.314245179,bounds:new f([-20037508.34279,-15496570.73972],[20037508.34279,18764656.23138]),project:function(t){var e=Math.PI/180,i=this.R,n=t.lat*e,o=this.R_MINOR/i,o=Math.sqrt(1-o*o),s=o*Math.sin(n),s=Math.tan(Math.PI/4-n/2)/Math.pow((1-s)/(1+s),o/2),n=-i*Math.log(Math.max(s,1e-10));return new p(t.lng*e*i,n)},unproject:function(t){for(var e,i=180/Math.PI,n=this.R,o=this.R_MINOR/n,s=Math.sqrt(1-o*o),r=Math.exp(-t.y/n),a=Math.PI/2-2*Math.atan(r),h=0,l=.1;h<15&&1e-7<Math.abs(l);h++)e=s*Math.sin(a),e=Math.pow((1-e)/(1+e),s/2),a+=l=Math.PI/2-2*Math.atan(r*e)-a;return new v(a*i,t.x*i/n)}},wt={__proto__:null,LonLat:yt,Mercator:xt,SphericalMercator:rt},Pt=l({},st,{code:"EPSG:3395",projection:xt,transformation:ht(bt=.5/(Math.PI*xt.R),.5,-bt,.5)}),li=l({},st,{code:"EPSG:4326",projection:yt,transformation:ht(1/180,1,-1/180,.5)}),Lt=l({},ot,{projection:yt,transformation:ht(1,0,-1,0),scale:function(t){return Math.pow(2,t)},zoom:function(t){return Math.log(t)/Math.LN2},distance:function(t,e){var i=e.lng-t.lng,e=e.lat-t.lat;return Math.sqrt(i*i+e*e)},infinite:!0}),o=(ot.Earth=st,ot.EPSG3395=Pt,ot.EPSG3857=lt,ot.EPSG900913=ut,ot.EPSG4326=li,ot.Simple=Lt,it.extend({options:{pane:"overlayPane",attribution:null,bubblingMouseEvents:!0},addTo:function(t){return t.addLayer(this),this},remove:function(){return this.removeFrom(this._map||this._mapToAdd)},removeFrom:function(t){return t&&t.removeLayer(this),this},getPane:function(t){return this._map.getPane(t?this.options[t]||t:this.options.pane)},addInteractiveTarget:function(t){return this._map._targets[h(t)]=this},removeInteractiveTarget:function(t){return delete this._map._targets[h(t)],this},getAttribution:function(){return this.options.attribution},_layerAdd:function(t){var e,i=t.target;i.hasLayer(this)&&(this._map=i,this._zoomAnimated=i._zoomAnimated,this.getEvents&&(e=this.getEvents(),i.on(e,this),this.once("remove",function(){i.off(e,this)},this)),this.onAdd(i),this.fire("add"),i.fire("layeradd",{layer:this}))}})),ui=(A.include({addLayer:function(t){var e;if(t._layerAdd)return e=h(t),this._layers[e]||((this._layers[e]=t)._mapToAdd=this,t.beforeAdd&&t.beforeAdd(this),this.whenReady(t._layerAdd,t)),this;throw new Error("The provided object is not a Layer.")},removeLayer:function(t){var e=h(t);return this._layers[e]&&(this._loaded&&t.onRemove(this),delete this._layers[e],this._loaded&&(this.fire("layerremove",{layer:t}),t.fire("remove")),t._map=t._mapToAdd=null),this},hasLayer:function(t){return h(t)in this._layers},eachLayer:function(t,e){for(var i in this._layers)t.call(e,this._layers[i]);return this},_addLayers:function(t){for(var e=0,i=(t=t?d(t)?t:[t]:[]).length;e<i;e++)this.addLayer(t[e])},_addZoomLimit:function(t){isNaN(t.options.maxZoom)&&isNaN(t.options.minZoom)||(this._zoomBoundLayers[h(t)]=t,this._updateZoomLevels())},_removeZoomLimit:function(t){t=h(t);this._zoomBoundLayers[t]&&(delete this._zoomBoundLayers[t],this._updateZoomLevels())},_updateZoomLevels:function(){var t,e=1/0,i=-1/0,n=this._getZoomSpan();for(t in this._zoomBoundLayers)var o=this._zoomBoundLayers[t].options,e=void 0===o.minZoom?e:Math.min(e,o.minZoom),i=void 0===o.maxZoom?i:Math.max(i,o.maxZoom);this._layersMaxZoom=i===-1/0?void 0:i,this._layersMinZoom=e===1/0?void 0:e,n!==this._getZoomSpan()&&this.fire("zoomlevelschange"),void 0===this.options.maxZoom&&this._layersMaxZoom&&this.getZoom()>this._layersMaxZoom&&this.setZoom(this._layersMaxZoom),void 0===this.options.minZoom&&this._layersMinZoom&&this.getZoom()<this._layersMinZoom&&this.setZoom(this._layersMinZoom)}}),o.extend({initialize:function(t,e){var i,n;if(c(this,e),this._layers={},t)for(i=0,n=t.length;i<n;i++)this.addLayer(t[i])},addLayer:function(t){var e=this.getLayerId(t);return this._layers[e]=t,this._map&&this._map.addLayer(t),this},removeLayer:function(t){t=t in this._layers?t:this.getLayerId(t);return this._map&&this._layers[t]&&this._map.removeLayer(this._layers[t]),delete this._layers[t],this},hasLayer:function(t){return("number"==typeof t?t:this.getLayerId(t))in this._layers},clearLayers:function(){return this.eachLayer(this.removeLayer,this)},invoke:function(t){var e,i,n=Array.prototype.slice.call(arguments,1);for(e in this._layers)(i=this._layers[e])[t]&&i[t].apply(i,n);return this},onAdd:function(t){this.eachLayer(t.addLayer,t)},onRemove:function(t){this.eachLayer(t.removeLayer,t)},eachLayer:function(t,e){for(var i in this._layers)t.call(e,this._layers[i]);return this},getLayer:function(t){return this._layers[t]},getLayers:function(){var t=[];return this.eachLayer(t.push,t),t},setZIndex:function(t){return this.invoke("setZIndex",t)},getLayerId:h})),ci=ui.extend({addLayer:function(t){return this.hasLayer(t)?this:(t.addEventParent(this),ui.prototype.addLayer.call(this,t),this.fire("layeradd",{layer:t}))},removeLayer:function(t){return this.hasLayer(t)?((t=t in this._layers?this._layers[t]:t).removeEventParent(this),ui.prototype.removeLayer.call(this,t),this.fire("layerremove",{layer:t})):this},setStyle:function(t){return this.invoke("setStyle",t)},bringToFront:function(){return this.invoke("bringToFront")},bringToBack:function(){return this.invoke("bringToBack")},getBounds:function(){var t,e=new s;for(t in this._layers){var i=this._layers[t];e.extend(i.getBounds?i.getBounds():i.getLatLng())}return e}}),di=et.extend({options:{popupAnchor:[0,0],tooltipAnchor:[0,0],crossOrigin:!1},initialize:function(t){c(this,t)},createIcon:function(t){return this._createIcon("icon",t)},createShadow:function(t){return this._createIcon("shadow",t)},_createIcon:function(t,e){var i=this._getIconUrl(t);if(i)return i=this._createImg(i,e&&"IMG"===e.tagName?e:null),this._setIconStyles(i,t),!this.options.crossOrigin&&""!==this.options.crossOrigin||(i.crossOrigin=!0===this.options.crossOrigin?"":this.options.crossOrigin),i;if("icon"===t)throw new Error("iconUrl not set in Icon options (see the docs).");return null},_setIconStyles:function(t,e){var i=this.options,n=i[e+"Size"],n=m(n="number"==typeof n?[n,n]:n),o=m("shadow"===e&&i.shadowAnchor||i.iconAnchor||n&&n.divideBy(2,!0));t.className="leaflet-marker-"+e+" "+(i.className||""),o&&(t.style.marginLeft=-o.x+"px",t.style.marginTop=-o.y+"px"),n&&(t.style.width=n.x+"px",t.style.height=n.y+"px")},_createImg:function(t,e){return(e=e||document.createElement("img")).src=t,e},_getIconUrl:function(t){return b.retina&&this.options[t+"RetinaUrl"]||this.options[t+"Url"]}});var _i=di.extend({options:{iconUrl:"marker-icon.png",iconRetinaUrl:"marker-icon-2x.png",shadowUrl:"marker-shadow.png",iconSize:[25,41],iconAnchor:[12,41],popupAnchor:[1,-34],tooltipAnchor:[16,-28],shadowSize:[41,41]},_getIconUrl:function(t){return"string"!=typeof _i.imagePath&&(_i.imagePath=this._detectIconPath()),(this.options.imagePath||_i.imagePath)+di.prototype._getIconUrl.call(this,t)},_stripUrl:function(t){function e(t,e,i){return(e=e.exec(t))&&e[i]}return(t=e(t,/^url\((['"])?(.+)\1\)$/,2))&&e(t,/^(.*)marker-icon\.png$/,1)},_detectIconPath:function(){var t=P("div","leaflet-default-icon-path",document.body),e=pe(t,"background-image")||pe(t,"backgroundImage");return document.body.removeChild(t),(e=this._stripUrl(e))?e:(t=document.querySelector('link[href$="leaflet.css"]'))?t.href.substring(0,t.href.length-"leaflet.css".length-1):""}}),pi=n.extend({initialize:function(t){this._marker=t},addHooks:function(){var t=this._marker._icon;this._draggable||(this._draggable=new Xe(t,t,!0)),this._draggable.on({dragstart:this._onDragStart,predrag:this._onPreDrag,drag:this._onDrag,dragend:this._onDragEnd},this).enable(),M(t,"leaflet-marker-draggable")},removeHooks:function(){this._draggable.off({dragstart:this._onDragStart,predrag:this._onPreDrag,drag:this._onDrag,dragend:this._onDragEnd},this).disable(),this._marker._icon&&z(this._marker._icon,"leaflet-marker-draggable")},moved:function(){return this._draggable&&this._draggable._moved},_adjustPan:function(t){var e=this._marker,i=e._map,n=this._marker.options.autoPanSpeed,o=this._marker.options.autoPanPadding,s=Pe(e._icon),r=i.getPixelBounds(),a=i.getPixelOrigin(),a=_(r.min._subtract(a).add(o),r.max._subtract(a).subtract(o));a.contains(s)||(o=m((Math.max(a.max.x,s.x)-a.max.x)/(r.max.x-a.max.x)-(Math.min(a.min.x,s.x)-a.min.x)/(r.min.x-a.min.x),(Math.max(a.max.y,s.y)-a.max.y)/(r.max.y-a.max.y)-(Math.min(a.min.y,s.y)-a.min.y)/(r.min.y-a.min.y)).multiplyBy(n),i.panBy(o,{animate:!1}),this._draggable._newPos._add(o),this._draggable._startPos._add(o),Z(e._icon,this._draggable._newPos),this._onDrag(t),this._panRequest=x(this._adjustPan.bind(this,t)))},_onDragStart:function(){this._oldLatLng=this._marker.getLatLng(),this._marker.closePopup&&this._marker.closePopup(),this._marker.fire("movestart").fire("dragstart")},_onPreDrag:function(t){this._marker.options.autoPan&&(r(this._panRequest),this._panRequest=x(this._adjustPan.bind(this,t)))},_onDrag:function(t){var e=this._marker,i=e._shadow,n=Pe(e._icon),o=e._map.layerPointToLatLng(n);i&&Z(i,n),e._latlng=o,t.latlng=o,t.oldLatLng=this._oldLatLng,e.fire("move",t).fire("drag",t)},_onDragEnd:function(t){r(this._panRequest),delete this._oldLatLng,this._marker.fire("moveend").fire("dragend",t)}}),mi=o.extend({options:{icon:new _i,interactive:!0,keyboard:!0,title:"",alt:"Marker",zIndexOffset:0,opacity:1,riseOnHover:!1,riseOffset:250,pane:"markerPane",shadowPane:"shadowPane",bubblingMouseEvents:!1,autoPanOnFocus:!0,draggable:!1,autoPan:!1,autoPanPadding:[50,50],autoPanSpeed:10},initialize:function(t,e){c(this,e),this._latlng=w(t)},onAdd:function(t){this._zoomAnimated=this._zoomAnimated&&t.options.markerZoomAnimation,this._zoomAnimated&&t.on("zoomanim",this._animateZoom,this),this._initIcon(),this.update()},onRemove:function(t){this.dragging&&this.dragging.enabled()&&(this.options.draggable=!0,this.dragging.removeHooks()),delete this.dragging,this._zoomAnimated&&t.off("zoomanim",this._animateZoom,this),this._removeIcon(),this._removeShadow()},getEvents:function(){return{zoom:this.update,viewreset:this.update}},getLatLng:function(){return this._latlng},setLatLng:function(t){var e=this._latlng;return this._latlng=w(t),this.update(),this.fire("move",{oldLatLng:e,latlng:this._latlng})},setZIndexOffset:function(t){return this.options.zIndexOffset=t,this.update()},getIcon:function(){return this.options.icon},setIcon:function(t){return this.options.icon=t,this._map&&(this._initIcon(),this.update()),this._popup&&this.bindPopup(this._popup,this._popup.options),this},getElement:function(){return this._icon},update:function(){var t;return this._icon&&this._map&&(t=this._map.latLngToLayerPoint(this._latlng).round(),this._setPos(t)),this},_initIcon:function(){var t=this.options,e="leaflet-zoom-"+(this._zoomAnimated?"animated":"hide"),i=t.icon.createIcon(this._icon),n=!1,i=(i!==this._icon&&(this._icon&&this._removeIcon(),n=!0,t.title&&(i.title=t.title),"IMG"===i.tagName&&(i.alt=t.alt||"")),M(i,e),t.keyboard&&(i.tabIndex="0",i.setAttribute("role","button")),this._icon=i,t.riseOnHover&&this.on({mouseover:this._bringToFront,mouseout:this._resetZIndex}),this.options.autoPanOnFocus&&S(i,"focus",this._panOnFocus,this),t.icon.createShadow(this._shadow)),o=!1;i!==this._shadow&&(this._removeShadow(),o=!0),i&&(M(i,e),i.alt=""),this._shadow=i,t.opacity<1&&this._updateOpacity(),n&&this.getPane().appendChild(this._icon),this._initInteraction(),i&&o&&this.getPane(t.shadowPane).appendChild(this._shadow)},_removeIcon:function(){this.options.riseOnHover&&this.off({mouseover:this._bringToFront,mouseout:this._resetZIndex}),this.options.autoPanOnFocus&&k(this._icon,"focus",this._panOnFocus,this),T(this._icon),this.removeInteractiveTarget(this._icon),this._icon=null},_removeShadow:function(){this._shadow&&T(this._shadow),this._shadow=null},_setPos:function(t){this._icon&&Z(this._icon,t),this._shadow&&Z(this._shadow,t),this._zIndex=t.y+this.options.zIndexOffset,this._resetZIndex()},_updateZIndex:function(t){this._icon&&(this._icon.style.zIndex=this._zIndex+t)},_animateZoom:function(t){t=this._map._latLngToNewLayerPoint(this._latlng,t.zoom,t.center).round();this._setPos(t)},_initInteraction:function(){var t;this.options.interactive&&(M(this._icon,"leaflet-interactive"),this.addInteractiveTarget(this._icon),pi&&(t=this.options.draggable,this.dragging&&(t=this.dragging.enabled(),this.dragging.disable()),this.dragging=new pi(this),t&&this.dragging.enable()))},setOpacity:function(t){return this.options.opacity=t,this._map&&this._updateOpacity(),this},_updateOpacity:function(){var t=this.options.opacity;this._icon&&C(this._icon,t),this._shadow&&C(this._shadow,t)},_bringToFront:function(){this._updateZIndex(this.options.riseOffset)},_resetZIndex:function(){this._updateZIndex(0)},_panOnFocus:function(){var t,e,i=this._map;i&&(t=(e=this.options.icon.options).iconSize?m(e.iconSize):m(0,0),e=e.iconAnchor?m(e.iconAnchor):m(0,0),i.panInside(this._latlng,{paddingTopLeft:e,paddingBottomRight:t.subtract(e)}))},_getPopupAnchor:function(){return this.options.icon.options.popupAnchor},_getTooltipAnchor:function(){return this.options.icon.options.tooltipAnchor}});var fi=o.extend({options:{stroke:!0,color:"#3388ff",weight:3,opacity:1,lineCap:"round",lineJoin:"round",dashArray:null,dashOffset:null,fill:!1,fillColor:null,fillOpacity:.2,fillRule:"evenodd",interactive:!0,bubblingMouseEvents:!0},beforeAdd:function(t){this._renderer=t.getRenderer(this)},onAdd:function(){this._renderer._initPath(this),this._reset(),this._renderer._addPath(this)},onRemove:function(){this._renderer._removePath(this)},redraw:function(){return this._map&&this._renderer._updatePath(this),this},setStyle:function(t){return c(this,t),this._renderer&&(this._renderer._updateStyle(this),this.options.stroke&&t&&Object.prototype.hasOwnProperty.call(t,"weight")&&this._updateBounds()),this},bringToFront:function(){return this._renderer&&this._renderer._bringToFront(this),this},bringToBack:function(){return this._renderer&&this._renderer._bringToBack(this),this},getElement:function(){return this._path},_reset:function(){this._project(),this._update()},_clickTolerance:function(){return(this.options.stroke?this.options.weight/2:0)+(this._renderer.options.tolerance||0)}}),gi=fi.extend({options:{fill:!0,radius:10},initialize:function(t,e){c(this,e),this._latlng=w(t),this._radius=this.options.radius},setLatLng:function(t){var e=this._latlng;return this._latlng=w(t),this.redraw(),this.fire("move",{oldLatLng:e,latlng:this._latlng})},getLatLng:function(){return this._latlng},setRadius:function(t){return this.options.radius=this._radius=t,this.redraw()},getRadius:function(){return this._radius},setStyle:function(t){var e=t&&t.radius||this._radius;return fi.prototype.setStyle.call(this,t),this.setRadius(e),this},_project:function(){this._point=this._map.latLngToLayerPoint(this._latlng),this._updateBounds()},_updateBounds:function(){var t=this._radius,e=this._radiusY||t,i=this._clickTolerance(),t=[t+i,e+i];this._pxBounds=new f(this._point.subtract(t),this._point.add(t))},_update:function(){this._map&&this._updatePath()},_updatePath:function(){this._renderer._updateCircle(this)},_empty:function(){return this._radius&&!this._renderer._bounds.intersects(this._pxBounds)},_containsPoint:function(t){return t.distanceTo(this._point)<=this._radius+this._clickTolerance()}});var vi=gi.extend({initialize:function(t,e,i){if(c(this,e="number"==typeof e?l({},i,{radius:e}):e),this._latlng=w(t),isNaN(this.options.radius))throw new Error("Circle radius cannot be NaN");this._mRadius=this.options.radius},setRadius:function(t){return this._mRadius=t,this.redraw()},getRadius:function(){return this._mRadius},getBounds:function(){var t=[this._radius,this._radiusY||this._radius];return new s(this._map.layerPointToLatLng(this._point.subtract(t)),this._map.layerPointToLatLng(this._point.add(t)))},setStyle:fi.prototype.setStyle,_project:function(){var t,e,i,n,o,s=this._latlng.lng,r=this._latlng.lat,a=this._map,h=a.options.crs;h.distance===st.distance?(n=Math.PI/180,o=this._mRadius/st.R/n,t=a.project([r+o,s]),e=a.project([r-o,s]),e=t.add(e).divideBy(2),i=a.unproject(e).lat,n=Math.acos((Math.cos(o*n)-Math.sin(r*n)*Math.sin(i*n))/(Math.cos(r*n)*Math.cos(i*n)))/n,!isNaN(n)&&0!==n||(n=o/Math.cos(Math.PI/180*r)),this._point=e.subtract(a.getPixelOrigin()),this._radius=isNaN(n)?0:e.x-a.project([i,s-n]).x,this._radiusY=e.y-t.y):(o=h.unproject(h.project(this._latlng).subtract([this._mRadius,0])),this._point=a.latLngToLayerPoint(this._latlng),this._radius=this._point.x-a.latLngToLayerPoint(o).x),this._updateBounds()}});var yi=fi.extend({options:{smoothFactor:1,noClip:!1},initialize:function(t,e){c(this,e),this._setLatLngs(t)},getLatLngs:function(){return this._latlngs},setLatLngs:function(t){return this._setLatLngs(t),this.redraw()},isEmpty:function(){return!this._latlngs.length},closestLayerPoint:function(t){for(var e=1/0,i=null,n=ri,o=0,s=this._parts.length;o<s;o++)for(var r=this._parts[o],a=1,h=r.length;a<h;a++){var l,u,c=n(t,l=r[a-1],u=r[a],!0);c<e&&(e=c,i=n(t,l,u))}return i&&(i.distance=Math.sqrt(e)),i},getCenter:function(){if(this._map)return hi(this._defaultShape(),this._map.options.crs);throw new Error("Must add layer to map before using getCenter()")},getBounds:function(){return this._bounds},addLatLng:function(t,e){return e=e||this._defaultShape(),t=w(t),e.push(t),this._bounds.extend(t),this.redraw()},_setLatLngs:function(t){this._bounds=new s,this._latlngs=this._convertLatLngs(t)},_defaultShape:function(){return I(this._latlngs)?this._latlngs:this._latlngs[0]},_convertLatLngs:function(t){for(var e=[],i=I(t),n=0,o=t.length;n<o;n++)i?(e[n]=w(t[n]),this._bounds.extend(e[n])):e[n]=this._convertLatLngs(t[n]);return e},_project:function(){var t=new f;this._rings=[],this._projectLatlngs(this._latlngs,this._rings,t),this._bounds.isValid()&&t.isValid()&&(this._rawPxBounds=t,this._updateBounds())},_updateBounds:function(){var t=this._clickTolerance(),t=new p(t,t);this._rawPxBounds&&(this._pxBounds=new f([this._rawPxBounds.min.subtract(t),this._rawPxBounds.max.add(t)]))},_projectLatlngs:function(t,e,i){var n,o,s=t[0]instanceof v,r=t.length;if(s){for(o=[],n=0;n<r;n++)o[n]=this._map.latLngToLayerPoint(t[n]),i.extend(o[n]);e.push(o)}else for(n=0;n<r;n++)this._projectLatlngs(t[n],e,i)},_clipPoints:function(){var t=this._renderer._bounds;if(this._parts=[],this._pxBounds&&this._pxBounds.intersects(t))if(this.options.noClip)this._parts=this._rings;else for(var e,i,n,o,s=this._parts,r=0,a=0,h=this._rings.length;r<h;r++)for(e=0,i=(o=this._rings[r]).length;e<i-1;e++)(n=ni(o[e],o[e+1],t,e,!0))&&(s[a]=s[a]||[],s[a].push(n[0]),n[1]===o[e+1]&&e!==i-2||(s[a].push(n[1]),a++))},_simplifyPoints:function(){for(var t=this._parts,e=this.options.smoothFactor,i=0,n=t.length;i<n;i++)t[i]=ei(t[i],e)},_update:function(){this._map&&(this._clipPoints(),this._simplifyPoints(),this._updatePath())},_updatePath:function(){this._renderer._updatePoly(this)},_containsPoint:function(t,e){var i,n,o,s,r,a,h=this._clickTolerance();if(this._pxBounds&&this._pxBounds.contains(t))for(i=0,s=this._parts.length;i<s;i++)for(n=0,o=(r=(a=this._parts[i]).length)-1;n<r;o=n++)if((e||0!==n)&&ii(t,a[o],a[n])<=h)return!0;return!1}});yi._flat=ai;var xi=yi.extend({options:{fill:!0},isEmpty:function(){return!this._latlngs.length||!this._latlngs[0].length},getCenter:function(){if(this._map)return $e(this._defaultShape(),this._map.options.crs);throw new Error("Must add layer to map before using getCenter()")},_convertLatLngs:function(t){var t=yi.prototype._convertLatLngs.call(this,t),e=t.length;return 2<=e&&t[0]instanceof v&&t[0].equals(t[e-1])&&t.pop(),t},_setLatLngs:function(t){yi.prototype._setLatLngs.call(this,t),I(this._latlngs)&&(this._latlngs=[this._latlngs])},_defaultShape:function(){return(I(this._latlngs[0])?this._latlngs:this._latlngs[0])[0]},_clipPoints:function(){var t=this._renderer._bounds,e=this.options.weight,e=new p(e,e),t=new f(t.min.subtract(e),t.max.add(e));if(this._parts=[],this._pxBounds&&this._pxBounds.intersects(t))if(this.options.noClip)this._parts=this._rings;else for(var i,n=0,o=this._rings.length;n<o;n++)(i=Je(this._rings[n],t,!0)).length&&this._parts.push(i)},_updatePath:function(){this._renderer._updatePoly(this,!0)},_containsPoint:function(t){var e,i,n,o,s,r,a,h,l=!1;if(!this._pxBounds||!this._pxBounds.contains(t))return!1;for(o=0,a=this._parts.length;o<a;o++)for(s=0,r=(h=(e=this._parts[o]).length)-1;s<h;r=s++)i=e[s],n=e[r],i.y>t.y!=n.y>t.y&&t.x<(n.x-i.x)*(t.y-i.y)/(n.y-i.y)+i.x&&(l=!l);return l||yi.prototype._containsPoint.call(this,t,!0)}});var wi=ci.extend({initialize:function(t,e){c(this,e),this._layers={},t&&this.addData(t)},addData:function(t){var e,i,n,o=d(t)?t:t.features;if(o){for(e=0,i=o.length;e<i;e++)((n=o[e]).geometries||n.geometry||n.features||n.coordinates)&&this.addData(n);return this}var s,r=this.options;return(!r.filter||r.filter(t))&&(s=bi(t,r))?(s.feature=Zi(t),s.defaultOptions=s.options,this.resetStyle(s),r.onEachFeature&&r.onEachFeature(t,s),this.addLayer(s)):this},resetStyle:function(t){return void 0===t?this.eachLayer(this.resetStyle,this):(t.options=l({},t.defaultOptions),this._setLayerStyle(t,this.options.style),this)},setStyle:function(e){return this.eachLayer(function(t){this._setLayerStyle(t,e)},this)},_setLayerStyle:function(t,e){t.setStyle&&("function"==typeof e&&(e=e(t.feature)),t.setStyle(e))}});function bi(t,e){var i,n,o,s,r="Feature"===t.type?t.geometry:t,a=r?r.coordinates:null,h=[],l=e&&e.pointToLayer,u=e&&e.coordsToLatLng||Li;if(!a&&!r)return null;switch(r.type){case"Point":return Pi(l,t,i=u(a),e);case"MultiPoint":for(o=0,s=a.length;o<s;o++)i=u(a[o]),h.push(Pi(l,t,i,e));return new ci(h);case"LineString":case"MultiLineString":return n=Ti(a,"LineString"===r.type?0:1,u),new yi(n,e);case"Polygon":case"MultiPolygon":return n=Ti(a,"Polygon"===r.type?1:2,u),new xi(n,e);case"GeometryCollection":for(o=0,s=r.geometries.length;o<s;o++){var c=bi({geometry:r.geometries[o],type:"Feature",properties:t.properties},e);c&&h.push(c)}return new ci(h);case"FeatureCollection":for(o=0,s=r.features.length;o<s;o++){var d=bi(r.features[o],e);d&&h.push(d)}return new ci(h);default:throw new Error("Invalid GeoJSON object.")}}function Pi(t,e,i,n){return t?t(e,i):new mi(i,n&&n.markersInheritOptions&&n)}function Li(t){return new v(t[1],t[0],t[2])}function Ti(t,e,i){for(var n,o=[],s=0,r=t.length;s<r;s++)n=e?Ti(t[s],e-1,i):(i||Li)(t[s]),o.push(n);return o}function Mi(t,e){return void 0!==(t=w(t)).alt?[i(t.lng,e),i(t.lat,e),i(t.alt,e)]:[i(t.lng,e),i(t.lat,e)]}function zi(t,e,i,n){for(var o=[],s=0,r=t.length;s<r;s++)o.push(e?zi(t[s],I(t[s])?0:e-1,i,n):Mi(t[s],n));return!e&&i&&0<o.length&&o.push(o[0].slice()),o}function Ci(t,e){return t.feature?l({},t.feature,{geometry:e}):Zi(e)}function Zi(t){return"Feature"===t.type||"FeatureCollection"===t.type?t:{type:"Feature",properties:{},geometry:t}}Tt={toGeoJSON:function(t){return Ci(this,{type:"Point",coordinates:Mi(this.getLatLng(),t)})}};function Si(t,e){return new wi(t,e)}mi.include(Tt),vi.include(Tt),gi.include(Tt),yi.include({toGeoJSON:function(t){var e=!I(this._latlngs);return Ci(this,{type:(e?"Multi":"")+"LineString",coordinates:zi(this._latlngs,e?1:0,!1,t)})}}),xi.include({toGeoJSON:function(t){var e=!I(this._latlngs),i=e&&!I(this._latlngs[0]),t=zi(this._latlngs,i?2:e?1:0,!0,t);return Ci(this,{type:(i?"Multi":"")+"Polygon",coordinates:t=e?t:[t]})}}),ui.include({toMultiPoint:function(e){var i=[];return this.eachLayer(function(t){i.push(t.toGeoJSON(e).geometry.coordinates)}),Ci(this,{type:"MultiPoint",coordinates:i})},toGeoJSON:function(e){var i,n,t=this.feature&&this.feature.geometry&&this.feature.geometry.type;return"MultiPoint"===t?this.toMultiPoint(e):(i="GeometryCollection"===t,n=[],this.eachLayer(function(t){t.toGeoJSON&&(t=t.toGeoJSON(e),i?n.push(t.geometry):"FeatureCollection"===(t=Zi(t)).type?n.push.apply(n,t.features):n.push(t))}),i?Ci(this,{geometries:n,type:"GeometryCollection"}):{type:"FeatureCollection",features:n})}});var Mt=Si,Ei=o.extend({options:{opacity:1,alt:"",interactive:!1,crossOrigin:!1,errorOverlayUrl:"",zIndex:1,className:""},initialize:function(t,e,i){this._url=t,this._bounds=g(e),c(this,i)},onAdd:function(){this._image||(this._initImage(),this.options.opacity<1&&this._updateOpacity()),this.options.interactive&&(M(this._image,"leaflet-interactive"),this.addInteractiveTarget(this._image)),this.getPane().appendChild(this._image),this._reset()},onRemove:function(){T(this._image),this.options.interactive&&this.removeInteractiveTarget(this._image)},setOpacity:function(t){return this.options.opacity=t,this._image&&this._updateOpacity(),this},setStyle:function(t){return t.opacity&&this.setOpacity(t.opacity),this},bringToFront:function(){return this._map&&fe(this._image),this},bringToBack:function(){return this._map&&ge(this._image),this},setUrl:function(t){return this._url=t,this._image&&(this._image.src=t),this},setBounds:function(t){return this._bounds=g(t),this._map&&this._reset(),this},getEvents:function(){var t={zoom:this._reset,viewreset:this._reset};return this._zoomAnimated&&(t.zoomanim=this._animateZoom),t},setZIndex:function(t){return this.options.zIndex=t,this._updateZIndex(),this},getBounds:function(){return this._bounds},getElement:function(){return this._image},_initImage:function(){var t="IMG"===this._url.tagName,e=this._image=t?this._url:P("img");M(e,"leaflet-image-layer"),this._zoomAnimated&&M(e,"leaflet-zoom-animated"),this.options.className&&M(e,this.options.className),e.onselectstart=u,e.onmousemove=u,e.onload=a(this.fire,this,"load"),e.onerror=a(this._overlayOnError,this,"error"),!this.options.crossOrigin&&""!==this.options.crossOrigin||(e.crossOrigin=!0===this.options.crossOrigin?"":this.options.crossOrigin),this.options.zIndex&&this._updateZIndex(),t?this._url=e.src:(e.src=this._url,e.alt=this.options.alt)},_animateZoom:function(t){var e=this._map.getZoomScale(t.zoom),t=this._map._latLngBoundsToNewLayerBounds(this._bounds,t.zoom,t.center).min;be(this._image,t,e)},_reset:function(){var t=this._image,e=new f(this._map.latLngToLayerPoint(this._bounds.getNorthWest()),this._map.latLngToLayerPoint(this._bounds.getSouthEast())),i=e.getSize();Z(t,e.min),t.style.width=i.x+"px",t.style.height=i.y+"px"},_updateOpacity:function(){C(this._image,this.options.opacity)},_updateZIndex:function(){this._image&&void 0!==this.options.zIndex&&null!==this.options.zIndex&&(this._image.style.zIndex=this.options.zIndex)},_overlayOnError:function(){this.fire("error");var t=this.options.errorOverlayUrl;t&&this._url!==t&&(this._url=t,this._image.src=t)},getCenter:function(){return this._bounds.getCenter()}}),ki=Ei.extend({options:{autoplay:!0,loop:!0,keepAspectRatio:!0,muted:!1,playsInline:!0},_initImage:function(){var t="VIDEO"===this._url.tagName,e=this._image=t?this._url:P("video");if(M(e,"leaflet-image-layer"),this._zoomAnimated&&M(e,"leaflet-zoom-animated"),this.options.className&&M(e,this.options.className),e.onselectstart=u,e.onmousemove=u,e.onloadeddata=a(this.fire,this,"load"),t){for(var i=e.getElementsByTagName("source"),n=[],o=0;o<i.length;o++)n.push(i[o].src);this._url=0<i.length?n:[e.src]}else{d(this._url)||(this._url=[this._url]),!this.options.keepAspectRatio&&Object.prototype.hasOwnProperty.call(e.style,"objectFit")&&(e.style.objectFit="fill"),e.autoplay=!!this.options.autoplay,e.loop=!!this.options.loop,e.muted=!!this.options.muted,e.playsInline=!!this.options.playsInline;for(var s=0;s<this._url.length;s++){var r=P("source");r.src=this._url[s],e.appendChild(r)}}}});var Oi=Ei.extend({_initImage:function(){var t=this._image=this._url;M(t,"leaflet-image-layer"),this._zoomAnimated&&M(t,"leaflet-zoom-animated"),this.options.className&&M(t,this.options.className),t.onselectstart=u,t.onmousemove=u}});var Ai=o.extend({options:{interactive:!1,offset:[0,0],className:"",pane:void 0,content:""},initialize:function(t,e){t&&(t instanceof v||d(t))?(this._latlng=w(t),c(this,e)):(c(this,t),this._source=e),this.options.content&&(this._content=this.options.content)},openOn:function(t){return(t=arguments.length?t:this._source._map).hasLayer(this)||t.addLayer(this),this},close:function(){return this._map&&this._map.removeLayer(this),this},toggle:function(t){return this._map?this.close():(arguments.length?this._source=t:t=this._source,this._prepareOpen(),this.openOn(t._map)),this},onAdd:function(t){this._zoomAnimated=t._zoomAnimated,this._container||this._initLayout(),t._fadeAnimated&&C(this._container,0),clearTimeout(this._removeTimeout),this.getPane().appendChild(this._container),this.update(),t._fadeAnimated&&C(this._container,1),this.bringToFront(),this.options.interactive&&(M(this._container,"leaflet-interactive"),this.addInteractiveTarget(this._container))},onRemove:function(t){t._fadeAnimated?(C(this._container,0),this._removeTimeout=setTimeout(a(T,void 0,this._container),200)):T(this._container),this.options.interactive&&(z(this._container,"leaflet-interactive"),this.removeInteractiveTarget(this._container))},getLatLng:function(){return this._latlng},setLatLng:function(t){return this._latlng=w(t),this._map&&(this._updatePosition(),this._adjustPan()),this},getContent:function(){return this._content},setContent:function(t){return this._content=t,this.update(),this},getElement:function(){return this._container},update:function(){this._map&&(this._container.style.visibility="hidden",this._updateContent(),this._updateLayout(),this._updatePosition(),this._container.style.visibility="",this._adjustPan())},getEvents:function(){var t={zoom:this._updatePosition,viewreset:this._updatePosition};return this._zoomAnimated&&(t.zoomanim=this._animateZoom),t},isOpen:function(){return!!this._map&&this._map.hasLayer(this)},bringToFront:function(){return this._map&&fe(this._container),this},bringToBack:function(){return this._map&&ge(this._container),this},_prepareOpen:function(t){if(!(i=this._source)._map)return!1;if(i instanceof ci){var e,i=null,n=this._source._layers;for(e in n)if(n[e]._map){i=n[e];break}if(!i)return!1;this._source=i}if(!t)if(i.getCenter)t=i.getCenter();else if(i.getLatLng)t=i.getLatLng();else{if(!i.getBounds)throw new Error("Unable to get source layer LatLng.");t=i.getBounds().getCenter()}return this.setLatLng(t),this._map&&this.update(),!0},_updateContent:function(){if(this._content){var t=this._contentNode,e="function"==typeof this._content?this._content(this._source||this):this._content;if("string"==typeof e)t.innerHTML=e;else{for(;t.hasChildNodes();)t.removeChild(t.firstChild);t.appendChild(e)}this.fire("contentupdate")}},_updatePosition:function(){var t,e,i;this._map&&(e=this._map.latLngToLayerPoint(this._latlng),t=m(this.options.offset),i=this._getAnchor(),this._zoomAnimated?Z(this._container,e.add(i)):t=t.add(e).add(i),e=this._containerBottom=-t.y,i=this._containerLeft=-Math.round(this._containerWidth/2)+t.x,this._container.style.bottom=e+"px",this._container.style.left=i+"px")},_getAnchor:function(){return[0,0]}}),Bi=(A.include({_initOverlay:function(t,e,i,n){var o=e;return o instanceof t||(o=new t(n).setContent(e)),i&&o.setLatLng(i),o}}),o.include({_initOverlay:function(t,e,i,n){var o=i;return o instanceof t?(c(o,n),o._source=this):(o=e&&!n?e:new t(n,this)).setContent(i),o}}),Ai.extend({options:{pane:"popupPane",offset:[0,7],maxWidth:300,minWidth:50,maxHeight:null,autoPan:!0,autoPanPaddingTopLeft:null,autoPanPaddingBottomRight:null,autoPanPadding:[5,5],keepInView:!1,closeButton:!0,autoClose:!0,closeOnEscapeKey:!0,className:""},openOn:function(t){return!(t=arguments.length?t:this._source._map).hasLayer(this)&&t._popup&&t._popup.options.autoClose&&t.removeLayer(t._popup),t._popup=this,Ai.prototype.openOn.call(this,t)},onAdd:function(t){Ai.prototype.onAdd.call(this,t),t.fire("popupopen",{popup:this}),this._source&&(this._source.fire("popupopen",{popup:this},!0),this._source instanceof fi||this._source.on("preclick",Ae))},onRemove:function(t){Ai.prototype.onRemove.call(this,t),t.fire("popupclose",{popup:this}),this._source&&(this._source.fire("popupclose",{popup:this},!0),this._source instanceof fi||this._source.off("preclick",Ae))},getEvents:function(){var t=Ai.prototype.getEvents.call(this);return(void 0!==this.options.closeOnClick?this.options.closeOnClick:this._map.options.closePopupOnClick)&&(t.preclick=this.close),this.options.keepInView&&(t.moveend=this._adjustPan),t},_initLayout:function(){var t="leaflet-popup",e=this._container=P("div",t+" "+(this.options.className||"")+" leaflet-zoom-animated"),i=this._wrapper=P("div",t+"-content-wrapper",e);this._contentNode=P("div",t+"-content",i),Ie(e),Be(this._contentNode),S(e,"contextmenu",Ae),this._tipContainer=P("div",t+"-tip-container",e),this._tip=P("div",t+"-tip",this._tipContainer),this.options.closeButton&&((i=this._closeButton=P("a",t+"-close-button",e)).setAttribute("role","button"),i.setAttribute("aria-label","Close popup"),i.href="#close",i.innerHTML='<span aria-hidden="true">&#215;</span>',S(i,"click",function(t){O(t),this.close()},this))},_updateLayout:function(){var t=this._contentNode,e=t.style,i=(e.width="",e.whiteSpace="nowrap",t.offsetWidth),i=Math.min(i,this.options.maxWidth),i=(i=Math.max(i,this.options.minWidth),e.width=i+1+"px",e.whiteSpace="",e.height="",t.offsetHeight),n=this.options.maxHeight,o="leaflet-popup-scrolled";(n&&n<i?(e.height=n+"px",M):z)(t,o),this._containerWidth=this._container.offsetWidth},_animateZoom:function(t){var t=this._map._latLngToNewLayerPoint(this._latlng,t.zoom,t.center),e=this._getAnchor();Z(this._container,t.add(e))},_adjustPan:function(){var t,e,i,n,o,s,r,a;this.options.autoPan&&(this._map._panAnim&&this._map._panAnim.stop(),this._autopanning?this._autopanning=!1:(t=this._map,e=parseInt(pe(this._container,"marginBottom"),10)||0,e=this._container.offsetHeight+e,a=this._containerWidth,(i=new p(this._containerLeft,-e-this._containerBottom))._add(Pe(this._container)),i=t.layerPointToContainerPoint(i),o=m(this.options.autoPanPadding),n=m(this.options.autoPanPaddingTopLeft||o),o=m(this.options.autoPanPaddingBottomRight||o),s=t.getSize(),r=0,i.x+a+o.x>s.x&&(r=i.x+a-s.x+o.x),i.x-r-n.x<(a=0)&&(r=i.x-n.x),i.y+e+o.y>s.y&&(a=i.y+e-s.y+o.y),i.y-a-n.y<0&&(a=i.y-n.y),(r||a)&&(this.options.keepInView&&(this._autopanning=!0),t.fire("autopanstart").panBy([r,a]))))},_getAnchor:function(){return m(this._source&&this._source._getPopupAnchor?this._source._getPopupAnchor():[0,0])}})),Ii=(A.mergeOptions({closePopupOnClick:!0}),A.include({openPopup:function(t,e,i){return this._initOverlay(Bi,t,e,i).openOn(this),this},closePopup:function(t){return(t=arguments.length?t:this._popup)&&t.close(),this}}),o.include({bindPopup:function(t,e){return this._popup=this._initOverlay(Bi,this._popup,t,e),this._popupHandlersAdded||(this.on({click:this._openPopup,keypress:this._onKeyPress,remove:this.closePopup,move:this._movePopup}),this._popupHandlersAdded=!0),this},unbindPopup:function(){return this._popup&&(this.off({click:this._openPopup,keypress:this._onKeyPress,remove:this.closePopup,move:this._movePopup}),this._popupHandlersAdded=!1,this._popup=null),this},openPopup:function(t){return this._popup&&(this instanceof ci||(this._popup._source=this),this._popup._prepareOpen(t||this._latlng)&&this._popup.openOn(this._map)),this},closePopup:function(){return this._popup&&this._popup.close(),this},togglePopup:function(){return this._popup&&this._popup.toggle(this),this},isPopupOpen:function(){return!!this._popup&&this._popup.isOpen()},setPopupContent:function(t){return this._popup&&this._popup.setContent(t),this},getPopup:function(){return this._popup},_openPopup:function(t){var e;this._popup&&this._map&&(Re(t),e=t.layer||t.target,this._popup._source!==e||e instanceof fi?(this._popup._source=e,this.openPopup(t.latlng)):this._map.hasLayer(this._popup)?this.closePopup():this.openPopup(t.latlng))},_movePopup:function(t){this._popup.setLatLng(t.latlng)},_onKeyPress:function(t){13===t.originalEvent.keyCode&&this._openPopup(t)}}),Ai.extend({options:{pane:"tooltipPane",offset:[0,0],direction:"auto",permanent:!1,sticky:!1,opacity:.9},onAdd:function(t){Ai.prototype.onAdd.call(this,t),this.setOpacity(this.options.opacity),t.fire("tooltipopen",{tooltip:this}),this._source&&(this.addEventParent(this._source),this._source.fire("tooltipopen",{tooltip:this},!0))},onRemove:function(t){Ai.prototype.onRemove.call(this,t),t.fire("tooltipclose",{tooltip:this}),this._source&&(this.removeEventParent(this._source),this._source.fire("tooltipclose",{tooltip:this},!0))},getEvents:function(){var t=Ai.prototype.getEvents.call(this);return this.options.permanent||(t.preclick=this.close),t},_initLayout:function(){var t="leaflet-tooltip "+(this.options.className||"")+" leaflet-zoom-"+(this._zoomAnimated?"animated":"hide");this._contentNode=this._container=P("div",t),this._container.setAttribute("role","tooltip"),this._container.setAttribute("id","leaflet-tooltip-"+h(this))},_updateLayout:function(){},_adjustPan:function(){},_setPosition:function(t){var e,i=this._map,n=this._container,o=i.latLngToContainerPoint(i.getCenter()),i=i.layerPointToContainerPoint(t),s=this.options.direction,r=n.offsetWidth,a=n.offsetHeight,h=m(this.options.offset),l=this._getAnchor(),i="top"===s?(e=r/2,a):"bottom"===s?(e=r/2,0):(e="center"===s?r/2:"right"===s?0:"left"===s?r:i.x<o.x?(s="right",0):(s="left",r+2*(h.x+l.x)),a/2);t=t.subtract(m(e,i,!0)).add(h).add(l),z(n,"leaflet-tooltip-right"),z(n,"leaflet-tooltip-left"),z(n,"leaflet-tooltip-top"),z(n,"leaflet-tooltip-bottom"),M(n,"leaflet-tooltip-"+s),Z(n,t)},_updatePosition:function(){var t=this._map.latLngToLayerPoint(this._latlng);this._setPosition(t)},setOpacity:function(t){this.options.opacity=t,this._container&&C(this._container,t)},_animateZoom:function(t){t=this._map._latLngToNewLayerPoint(this._latlng,t.zoom,t.center);this._setPosition(t)},_getAnchor:function(){return m(this._source&&this._source._getTooltipAnchor&&!this.options.sticky?this._source._getTooltipAnchor():[0,0])}})),Ri=(A.include({openTooltip:function(t,e,i){return this._initOverlay(Ii,t,e,i).openOn(this),this},closeTooltip:function(t){return t.close(),this}}),o.include({bindTooltip:function(t,e){return this._tooltip&&this.isTooltipOpen()&&this.unbindTooltip(),this._tooltip=this._initOverlay(Ii,this._tooltip,t,e),this._initTooltipInteractions(),this._tooltip.options.permanent&&this._map&&this._map.hasLayer(this)&&this.openTooltip(),this},unbindTooltip:function(){return this._tooltip&&(this._initTooltipInteractions(!0),this.closeTooltip(),this._tooltip=null),this},_initTooltipInteractions:function(t){var e,i;!t&&this._tooltipHandlersAdded||(e=t?"off":"on",i={remove:this.closeTooltip,move:this._moveTooltip},this._tooltip.options.permanent?i.add=this._openTooltip:(i.mouseover=this._openTooltip,i.mouseout=this.closeTooltip,i.click=this._openTooltip,this._map?this._addFocusListeners():i.add=this._addFocusListeners),this._tooltip.options.sticky&&(i.mousemove=this._moveTooltip),this[e](i),this._tooltipHandlersAdded=!t)},openTooltip:function(t){return this._tooltip&&(this instanceof ci||(this._tooltip._source=this),this._tooltip._prepareOpen(t)&&(this._tooltip.openOn(this._map),this.getElement?this._setAriaDescribedByOnLayer(this):this.eachLayer&&this.eachLayer(this._setAriaDescribedByOnLayer,this))),this},closeTooltip:function(){if(this._tooltip)return this._tooltip.close()},toggleTooltip:function(){return this._tooltip&&this._tooltip.toggle(this),this},isTooltipOpen:function(){return this._tooltip.isOpen()},setTooltipContent:function(t){return this._tooltip&&this._tooltip.setContent(t),this},getTooltip:function(){return this._tooltip},_addFocusListeners:function(){this.getElement?this._addFocusListenersOnLayer(this):this.eachLayer&&this.eachLayer(this._addFocusListenersOnLayer,this)},_addFocusListenersOnLayer:function(t){var e="function"==typeof t.getElement&&t.getElement();e&&(S(e,"focus",function(){this._tooltip._source=t,this.openTooltip()},this),S(e,"blur",this.closeTooltip,this))},_setAriaDescribedByOnLayer:function(t){t="function"==typeof t.getElement&&t.getElement();t&&t.setAttribute("aria-describedby",this._tooltip._container.id)},_openTooltip:function(t){var e;this._tooltip&&this._map&&(this._map.dragging&&this._map.dragging.moving()&&!this._openOnceFlag?(this._openOnceFlag=!0,(e=this)._map.once("moveend",function(){e._openOnceFlag=!1,e._openTooltip(t)})):(this._tooltip._source=t.layer||t.target,this.openTooltip(this._tooltip.options.sticky?t.latlng:void 0)))},_moveTooltip:function(t){var e=t.latlng;this._tooltip.options.sticky&&t.originalEvent&&(t=this._map.mouseEventToContainerPoint(t.originalEvent),t=this._map.containerPointToLayerPoint(t),e=this._map.layerPointToLatLng(t)),this._tooltip.setLatLng(e)}}),di.extend({options:{iconSize:[12,12],html:!1,bgPos:null,className:"leaflet-div-icon"},createIcon:function(t){var t=t&&"DIV"===t.tagName?t:document.createElement("div"),e=this.options;return e.html instanceof Element?(me(t),t.appendChild(e.html)):t.innerHTML=!1!==e.html?e.html:"",e.bgPos&&(e=m(e.bgPos),t.style.backgroundPosition=-e.x+"px "+-e.y+"px"),this._setIconStyles(t,"icon"),t},createShadow:function(){return null}}));di.Default=_i;var Ni=o.extend({options:{tileSize:256,opacity:1,updateWhenIdle:b.mobile,updateWhenZooming:!0,updateInterval:200,zIndex:1,bounds:null,minZoom:0,maxZoom:void 0,maxNativeZoom:void 0,minNativeZoom:void 0,noWrap:!1,pane:"tilePane",className:"",keepBuffer:2},initialize:function(t){c(this,t)},onAdd:function(){this._initContainer(),this._levels={},this._tiles={},this._resetView()},beforeAdd:function(t){t._addZoomLimit(this)},onRemove:function(t){this._removeAllTiles(),T(this._container),t._removeZoomLimit(this),this._container=null,this._tileZoom=void 0},bringToFront:function(){return this._map&&(fe(this._container),this._setAutoZIndex(Math.max)),this},bringToBack:function(){return this._map&&(ge(this._container),this._setAutoZIndex(Math.min)),this},getContainer:function(){return this._container},setOpacity:function(t){return this.options.opacity=t,this._updateOpacity(),this},setZIndex:function(t){return this.options.zIndex=t,this._updateZIndex(),this},isLoading:function(){return this._loading},redraw:function(){var t;return this._map&&(this._removeAllTiles(),(t=this._clampZoom(this._map.getZoom()))!==this._tileZoom&&(this._tileZoom=t,this._updateLevels()),this._update()),this},getEvents:function(){var t={viewprereset:this._invalidateAll,viewreset:this._resetView,zoom:this._resetView,moveend:this._onMoveEnd};return this.options.updateWhenIdle||(this._onMove||(this._onMove=j(this._onMoveEnd,this.options.updateInterval,this)),t.move=this._onMove),this._zoomAnimated&&(t.zoomanim=this._animateZoom),t},createTile:function(){return document.createElement("div")},getTileSize:function(){var t=this.options.tileSize;return t instanceof p?t:new p(t,t)},_updateZIndex:function(){this._container&&void 0!==this.options.zIndex&&null!==this.options.zIndex&&(this._container.style.zIndex=this.options.zIndex)},_setAutoZIndex:function(t){for(var e,i=this.getPane().children,n=-t(-1/0,1/0),o=0,s=i.length;o<s;o++)e=i[o].style.zIndex,i[o]!==this._container&&e&&(n=t(n,+e));isFinite(n)&&(this.options.zIndex=n+t(-1,1),this._updateZIndex())},_updateOpacity:function(){if(this._map&&!b.ielt9){C(this._container,this.options.opacity);var t,e=+new Date,i=!1,n=!1;for(t in this._tiles){var o,s=this._tiles[t];s.current&&s.loaded&&(o=Math.min(1,(e-s.loaded)/200),C(s.el,o),o<1?i=!0:(s.active?n=!0:this._onOpaqueTile(s),s.active=!0))}n&&!this._noPrune&&this._pruneTiles(),i&&(r(this._fadeFrame),this._fadeFrame=x(this._updateOpacity,this))}},_onOpaqueTile:u,_initContainer:function(){this._container||(this._container=P("div","leaflet-layer "+(this.options.className||"")),this._updateZIndex(),this.options.opacity<1&&this._updateOpacity(),this.getPane().appendChild(this._container))},_updateLevels:function(){var t=this._tileZoom,e=this.options.maxZoom;if(void 0!==t){for(var i in this._levels)i=Number(i),this._levels[i].el.children.length||i===t?(this._levels[i].el.style.zIndex=e-Math.abs(t-i),this._onUpdateLevel(i)):(T(this._levels[i].el),this._removeTilesAtZoom(i),this._onRemoveLevel(i),delete this._levels[i]);var n=this._levels[t],o=this._map;return n||((n=this._levels[t]={}).el=P("div","leaflet-tile-container leaflet-zoom-animated",this._container),n.el.style.zIndex=e,n.origin=o.project(o.unproject(o.getPixelOrigin()),t).round(),n.zoom=t,this._setZoomTransform(n,o.getCenter(),o.getZoom()),u(n.el.offsetWidth),this._onCreateLevel(n)),this._level=n}},_onUpdateLevel:u,_onRemoveLevel:u,_onCreateLevel:u,_pruneTiles:function(){if(this._map){var t,e,i,n=this._map.getZoom();if(n>this.options.maxZoom||n<this.options.minZoom)this._removeAllTiles();else{for(t in this._tiles)(i=this._tiles[t]).retain=i.current;for(t in this._tiles)(i=this._tiles[t]).current&&!i.active&&(e=i.coords,this._retainParent(e.x,e.y,e.z,e.z-5)||this._retainChildren(e.x,e.y,e.z,e.z+2));for(t in this._tiles)this._tiles[t].retain||this._removeTile(t)}}},_removeTilesAtZoom:function(t){for(var e in this._tiles)this._tiles[e].coords.z===t&&this._removeTile(e)},_removeAllTiles:function(){for(var t in this._tiles)this._removeTile(t)},_invalidateAll:function(){for(var t in this._levels)T(this._levels[t].el),this._onRemoveLevel(Number(t)),delete this._levels[t];this._removeAllTiles(),this._tileZoom=void 0},_retainParent:function(t,e,i,n){var t=Math.floor(t/2),e=Math.floor(e/2),i=i-1,o=new p(+t,+e),o=(o.z=i,this._tileCoordsToKey(o)),o=this._tiles[o];return o&&o.active?o.retain=!0:(o&&o.loaded&&(o.retain=!0),n<i&&this._retainParent(t,e,i,n))},_retainChildren:function(t,e,i,n){for(var o=2*t;o<2*t+2;o++)for(var s=2*e;s<2*e+2;s++){var r=new p(o,s),r=(r.z=i+1,this._tileCoordsToKey(r)),r=this._tiles[r];r&&r.active?r.retain=!0:(r&&r.loaded&&(r.retain=!0),i+1<n&&this._retainChildren(o,s,i+1,n))}},_resetView:function(t){t=t&&(t.pinch||t.flyTo);this._setView(this._map.getCenter(),this._map.getZoom(),t,t)},_animateZoom:function(t){this._setView(t.center,t.zoom,!0,t.noUpdate)},_clampZoom:function(t){var e=this.options;return void 0!==e.minNativeZoom&&t<e.minNativeZoom?e.minNativeZoom:void 0!==e.maxNativeZoom&&e.maxNativeZoom<t?e.maxNativeZoom:t},_setView:function(t,e,i,n){var o=Math.round(e),o=void 0!==this.options.maxZoom&&o>this.options.maxZoom||void 0!==this.options.minZoom&&o<this.options.minZoom?void 0:this._clampZoom(o),s=this.options.updateWhenZooming&&o!==this._tileZoom;n&&!s||(this._tileZoom=o,this._abortLoading&&this._abortLoading(),this._updateLevels(),this._resetGrid(),void 0!==o&&this._update(t),i||this._pruneTiles(),this._noPrune=!!i),this._setZoomTransforms(t,e)},_setZoomTransforms:function(t,e){for(var i in this._levels)this._setZoomTransform(this._levels[i],t,e)},_setZoomTransform:function(t,e,i){var n=this._map.getZoomScale(i,t.zoom),e=t.origin.multiplyBy(n).subtract(this._map._getNewPixelOrigin(e,i)).round();b.any3d?be(t.el,e,n):Z(t.el,e)},_resetGrid:function(){var t=this._map,e=t.options.crs,i=this._tileSize=this.getTileSize(),n=this._tileZoom,o=this._map.getPixelWorldBounds(this._tileZoom);o&&(this._globalTileRange=this._pxBoundsToTileRange(o)),this._wrapX=e.wrapLng&&!this.options.noWrap&&[Math.floor(t.project([0,e.wrapLng[0]],n).x/i.x),Math.ceil(t.project([0,e.wrapLng[1]],n).x/i.y)],this._wrapY=e.wrapLat&&!this.options.noWrap&&[Math.floor(t.project([e.wrapLat[0],0],n).y/i.x),Math.ceil(t.project([e.wrapLat[1],0],n).y/i.y)]},_onMoveEnd:function(){this._map&&!this._map._animatingZoom&&this._update()},_getTiledPixelBounds:function(t){var e=this._map,i=e._animatingZoom?Math.max(e._animateToZoom,e.getZoom()):e.getZoom(),i=e.getZoomScale(i,this._tileZoom),t=e.project(t,this._tileZoom).floor(),e=e.getSize().divideBy(2*i);return new f(t.subtract(e),t.add(e))},_update:function(t){var e=this._map;if(e){var i=this._clampZoom(e.getZoom());if(void 0===t&&(t=e.getCenter()),void 0!==this._tileZoom){var n,e=this._getTiledPixelBounds(t),o=this._pxBoundsToTileRange(e),s=o.getCenter(),r=[],e=this.options.keepBuffer,a=new f(o.getBottomLeft().subtract([e,-e]),o.getTopRight().add([e,-e]));if(!(isFinite(o.min.x)&&isFinite(o.min.y)&&isFinite(o.max.x)&&isFinite(o.max.y)))throw new Error("Attempted to load an infinite number of tiles");for(n in this._tiles){var h=this._tiles[n].coords;h.z===this._tileZoom&&a.contains(new p(h.x,h.y))||(this._tiles[n].current=!1)}if(1<Math.abs(i-this._tileZoom))this._setView(t,i);else{for(var l=o.min.y;l<=o.max.y;l++)for(var u=o.min.x;u<=o.max.x;u++){var c,d=new p(u,l);d.z=this._tileZoom,this._isValidTile(d)&&((c=this._tiles[this._tileCoordsToKey(d)])?c.current=!0:r.push(d))}if(r.sort(function(t,e){return t.distanceTo(s)-e.distanceTo(s)}),0!==r.length){this._loading||(this._loading=!0,this.fire("loading"));for(var _=document.createDocumentFragment(),u=0;u<r.length;u++)this._addTile(r[u],_);this._level.el.appendChild(_)}}}}},_isValidTile:function(t){var e=this._map.options.crs;if(!e.infinite){var i=this._globalTileRange;if(!e.wrapLng&&(t.x<i.min.x||t.x>i.max.x)||!e.wrapLat&&(t.y<i.min.y||t.y>i.max.y))return!1}return!this.options.bounds||(e=this._tileCoordsToBounds(t),g(this.options.bounds).overlaps(e))},_keyToBounds:function(t){return this._tileCoordsToBounds(this._keyToTileCoords(t))},_tileCoordsToNwSe:function(t){var e=this._map,i=this.getTileSize(),n=t.scaleBy(i),i=n.add(i);return[e.unproject(n,t.z),e.unproject(i,t.z)]},_tileCoordsToBounds:function(t){t=this._tileCoordsToNwSe(t),t=new s(t[0],t[1]);return t=this.options.noWrap?t:this._map.wrapLatLngBounds(t)},_tileCoordsToKey:function(t){return t.x+":"+t.y+":"+t.z},_keyToTileCoords:function(t){var t=t.split(":"),e=new p(+t[0],+t[1]);return e.z=+t[2],e},_removeTile:function(t){var e=this._tiles[t];e&&(T(e.el),delete this._tiles[t],this.fire("tileunload",{tile:e.el,coords:this._keyToTileCoords(t)}))},_initTile:function(t){M(t,"leaflet-tile");var e=this.getTileSize();t.style.width=e.x+"px",t.style.height=e.y+"px",t.onselectstart=u,t.onmousemove=u,b.ielt9&&this.options.opacity<1&&C(t,this.options.opacity)},_addTile:function(t,e){var i=this._getTilePos(t),n=this._tileCoordsToKey(t),o=this.createTile(this._wrapCoords(t),a(this._tileReady,this,t));this._initTile(o),this.createTile.length<2&&x(a(this._tileReady,this,t,null,o)),Z(o,i),this._tiles[n]={el:o,coords:t,current:!0},e.appendChild(o),this.fire("tileloadstart",{tile:o,coords:t})},_tileReady:function(t,e,i){e&&this.fire("tileerror",{error:e,tile:i,coords:t});var n=this._tileCoordsToKey(t);(i=this._tiles[n])&&(i.loaded=+new Date,this._map._fadeAnimated?(C(i.el,0),r(this._fadeFrame),this._fadeFrame=x(this._updateOpacity,this)):(i.active=!0,this._pruneTiles()),e||(M(i.el,"leaflet-tile-loaded"),this.fire("tileload",{tile:i.el,coords:t})),this._noTilesToLoad()&&(this._loading=!1,this.fire("load"),b.ielt9||!this._map._fadeAnimated?x(this._pruneTiles,this):setTimeout(a(this._pruneTiles,this),250)))},_getTilePos:function(t){return t.scaleBy(this.getTileSize()).subtract(this._level.origin)},_wrapCoords:function(t){var e=new p(this._wrapX?H(t.x,this._wrapX):t.x,this._wrapY?H(t.y,this._wrapY):t.y);return e.z=t.z,e},_pxBoundsToTileRange:function(t){var e=this.getTileSize();return new f(t.min.unscaleBy(e).floor(),t.max.unscaleBy(e).ceil().subtract([1,1]))},_noTilesToLoad:function(){for(var t in this._tiles)if(!this._tiles[t].loaded)return!1;return!0}});var Di=Ni.extend({options:{minZoom:0,maxZoom:18,subdomains:"abc",errorTileUrl:"",zoomOffset:0,tms:!1,zoomReverse:!1,detectRetina:!1,crossOrigin:!1,referrerPolicy:!1},initialize:function(t,e){this._url=t,(e=c(this,e)).detectRetina&&b.retina&&0<e.maxZoom?(e.tileSize=Math.floor(e.tileSize/2),e.zoomReverse?(e.zoomOffset--,e.minZoom=Math.min(e.maxZoom,e.minZoom+1)):(e.zoomOffset++,e.maxZoom=Math.max(e.minZoom,e.maxZoom-1)),e.minZoom=Math.max(0,e.minZoom)):e.zoomReverse?e.minZoom=Math.min(e.maxZoom,e.minZoom):e.maxZoom=Math.max(e.minZoom,e.maxZoom),"string"==typeof e.subdomains&&(e.subdomains=e.subdomains.split("")),this.on("tileunload",this._onTileRemove)},setUrl:function(t,e){return this._url===t&&void 0===e&&(e=!0),this._url=t,e||this.redraw(),this},createTile:function(t,e){var i=document.createElement("img");return S(i,"load",a(this._tileOnLoad,this,e,i)),S(i,"error",a(this._tileOnError,this,e,i)),!this.options.crossOrigin&&""!==this.options.crossOrigin||(i.crossOrigin=!0===this.options.crossOrigin?"":this.options.crossOrigin),"string"==typeof this.options.referrerPolicy&&(i.referrerPolicy=this.options.referrerPolicy),i.alt="",i.src=this.getTileUrl(t),i},getTileUrl:function(t){var e={r:b.retina?"@2x":"",s:this._getSubdomain(t),x:t.x,y:t.y,z:this._getZoomForUrl()};return this._map&&!this._map.options.crs.infinite&&(t=this._globalTileRange.max.y-t.y,this.options.tms&&(e.y=t),e["-y"]=t),q(this._url,l(e,this.options))},_tileOnLoad:function(t,e){b.ielt9?setTimeout(a(t,this,null,e),0):t(null,e)},_tileOnError:function(t,e,i){var n=this.options.errorTileUrl;n&&e.getAttribute("src")!==n&&(e.src=n),t(i,e)},_onTileRemove:function(t){t.tile.onload=null},_getZoomForUrl:function(){var t=this._tileZoom,e=this.options.maxZoom;return(t=this.options.zoomReverse?e-t:t)+this.options.zoomOffset},_getSubdomain:function(t){t=Math.abs(t.x+t.y)%this.options.subdomains.length;return this.options.subdomains[t]},_abortLoading:function(){var t,e,i;for(t in this._tiles)this._tiles[t].coords.z!==this._tileZoom&&((i=this._tiles[t].el).onload=u,i.onerror=u,i.complete||(i.src=K,e=this._tiles[t].coords,T(i),delete this._tiles[t],this.fire("tileabort",{tile:i,coords:e})))},_removeTile:function(t){var e=this._tiles[t];if(e)return e.el.setAttribute("src",K),Ni.prototype._removeTile.call(this,t)},_tileReady:function(t,e,i){if(this._map&&(!i||i.getAttribute("src")!==K))return Ni.prototype._tileReady.call(this,t,e,i)}});function ji(t,e){return new Di(t,e)}var Hi=Di.extend({defaultWmsParams:{service:"WMS",request:"GetMap",layers:"",styles:"",format:"image/jpeg",transparent:!1,version:"1.1.1"},options:{crs:null,uppercase:!1},initialize:function(t,e){this._url=t;var i,n=l({},this.defaultWmsParams);for(i in e)i in this.options||(n[i]=e[i]);var t=(e=c(this,e)).detectRetina&&b.retina?2:1,o=this.getTileSize();n.width=o.x*t,n.height=o.y*t,this.wmsParams=n},onAdd:function(t){this._crs=this.options.crs||t.options.crs,this._wmsVersion=parseFloat(this.wmsParams.version);var e=1.3<=this._wmsVersion?"crs":"srs";this.wmsParams[e]=this._crs.code,Di.prototype.onAdd.call(this,t)},getTileUrl:function(t){var e=this._tileCoordsToNwSe(t),i=this._crs,i=_(i.project(e[0]),i.project(e[1])),e=i.min,i=i.max,e=(1.3<=this._wmsVersion&&this._crs===li?[e.y,e.x,i.y,i.x]:[e.x,e.y,i.x,i.y]).join(","),i=Di.prototype.getTileUrl.call(this,t);return i+U(this.wmsParams,i,this.options.uppercase)+(this.options.uppercase?"&BBOX=":"&bbox=")+e},setParams:function(t,e){return l(this.wmsParams,t),e||this.redraw(),this}});Di.WMS=Hi,ji.wms=function(t,e){return new Hi(t,e)};var Wi=o.extend({options:{padding:.1},initialize:function(t){c(this,t),h(this),this._layers=this._layers||{}},onAdd:function(){this._container||(this._initContainer(),M(this._container,"leaflet-zoom-animated")),this.getPane().appendChild(this._container),this._update(),this.on("update",this._updatePaths,this)},onRemove:function(){this.off("update",this._updatePaths,this),this._destroyContainer()},getEvents:function(){var t={viewreset:this._reset,zoom:this._onZoom,moveend:this._update,zoomend:this._onZoomEnd};return this._zoomAnimated&&(t.zoomanim=this._onAnimZoom),t},_onAnimZoom:function(t){this._updateTransform(t.center,t.zoom)},_onZoom:function(){this._updateTransform(this._map.getCenter(),this._map.getZoom())},_updateTransform:function(t,e){var i=this._map.getZoomScale(e,this._zoom),n=this._map.getSize().multiplyBy(.5+this.options.padding),o=this._map.project(this._center,e),n=n.multiplyBy(-i).add(o).subtract(this._map._getNewPixelOrigin(t,e));b.any3d?be(this._container,n,i):Z(this._container,n)},_reset:function(){for(var t in this._update(),this._updateTransform(this._center,this._zoom),this._layers)this._layers[t]._reset()},_onZoomEnd:function(){for(var t in this._layers)this._layers[t]._project()},_updatePaths:function(){for(var t in this._layers)this._layers[t]._update()},_update:function(){var t=this.options.padding,e=this._map.getSize(),i=this._map.containerPointToLayerPoint(e.multiplyBy(-t)).round();this._bounds=new f(i,i.add(e.multiplyBy(1+2*t)).round()),this._center=this._map.getCenter(),this._zoom=this._map.getZoom()}}),Fi=Wi.extend({options:{tolerance:0},getEvents:function(){var t=Wi.prototype.getEvents.call(this);return t.viewprereset=this._onViewPreReset,t},_onViewPreReset:function(){this._postponeUpdatePaths=!0},onAdd:function(){Wi.prototype.onAdd.call(this),this._draw()},_initContainer:function(){var t=this._container=document.createElement("canvas");S(t,"mousemove",this._onMouseMove,this),S(t,"click dblclick mousedown mouseup contextmenu",this._onClick,this),S(t,"mouseout",this._handleMouseOut,this),t._leaflet_disable_events=!0,this._ctx=t.getContext("2d")},_destroyContainer:function(){r(this._redrawRequest),delete this._ctx,T(this._container),k(this._container),delete this._container},_updatePaths:function(){if(!this._postponeUpdatePaths){for(var t in this._redrawBounds=null,this._layers)this._layers[t]._update();this._redraw()}},_update:function(){var t,e,i,n;this._map._animatingZoom&&this._bounds||(Wi.prototype._update.call(this),t=this._bounds,e=this._container,i=t.getSize(),n=b.retina?2:1,Z(e,t.min),e.width=n*i.x,e.height=n*i.y,e.style.width=i.x+"px",e.style.height=i.y+"px",b.retina&&this._ctx.scale(2,2),this._ctx.translate(-t.min.x,-t.min.y),this.fire("update"))},_reset:function(){Wi.prototype._reset.call(this),this._postponeUpdatePaths&&(this._postponeUpdatePaths=!1,this._updatePaths())},_initPath:function(t){this._updateDashArray(t);t=(this._layers[h(t)]=t)._order={layer:t,prev:this._drawLast,next:null};this._drawLast&&(this._drawLast.next=t),this._drawLast=t,this._drawFirst=this._drawFirst||this._drawLast},_addPath:function(t){this._requestRedraw(t)},_removePath:function(t){var e=t._order,i=e.next,e=e.prev;i?i.prev=e:this._drawLast=e,e?e.next=i:this._drawFirst=i,delete t._order,delete this._layers[h(t)],this._requestRedraw(t)},_updatePath:function(t){this._extendRedrawBounds(t),t._project(),t._update(),this._requestRedraw(t)},_updateStyle:function(t){this._updateDashArray(t),this._requestRedraw(t)},_updateDashArray:function(t){if("string"==typeof t.options.dashArray){for(var e,i=t.options.dashArray.split(/[, ]+/),n=[],o=0;o<i.length;o++){if(e=Number(i[o]),isNaN(e))return;n.push(e)}t.options._dashArray=n}else t.options._dashArray=t.options.dashArray},_requestRedraw:function(t){this._map&&(this._extendRedrawBounds(t),this._redrawRequest=this._redrawRequest||x(this._redraw,this))},_extendRedrawBounds:function(t){var e;t._pxBounds&&(e=(t.options.weight||0)+1,this._redrawBounds=this._redrawBounds||new f,this._redrawBounds.extend(t._pxBounds.min.subtract([e,e])),this._redrawBounds.extend(t._pxBounds.max.add([e,e])))},_redraw:function(){this._redrawRequest=null,this._redrawBounds&&(this._redrawBounds.min._floor(),this._redrawBounds.max._ceil()),this._clear(),this._draw(),this._redrawBounds=null},_clear:function(){var t,e=this._redrawBounds;e?(t=e.getSize(),this._ctx.clearRect(e.min.x,e.min.y,t.x,t.y)):(this._ctx.save(),this._ctx.setTransform(1,0,0,1,0,0),this._ctx.clearRect(0,0,this._container.width,this._container.height),this._ctx.restore())},_draw:function(){var t,e,i=this._redrawBounds;this._ctx.save(),i&&(e=i.getSize(),this._ctx.beginPath(),this._ctx.rect(i.min.x,i.min.y,e.x,e.y),this._ctx.clip()),this._drawing=!0;for(var n=this._drawFirst;n;n=n.next)t=n.layer,(!i||t._pxBounds&&t._pxBounds.intersects(i))&&t._updatePath();this._drawing=!1,this._ctx.restore()},_updatePoly:function(t,e){if(this._drawing){var i,n,o,s,r=t._parts,a=r.length,h=this._ctx;if(a){for(h.beginPath(),i=0;i<a;i++){for(n=0,o=r[i].length;n<o;n++)s=r[i][n],h[n?"lineTo":"moveTo"](s.x,s.y);e&&h.closePath()}this._fillStroke(h,t)}}},_updateCircle:function(t){var e,i,n,o;this._drawing&&!t._empty()&&(e=t._point,i=this._ctx,n=Math.max(Math.round(t._radius),1),1!=(o=(Math.max(Math.round(t._radiusY),1)||n)/n)&&(i.save(),i.scale(1,o)),i.beginPath(),i.arc(e.x,e.y/o,n,0,2*Math.PI,!1),1!=o&&i.restore(),this._fillStroke(i,t))},_fillStroke:function(t,e){var i=e.options;i.fill&&(t.globalAlpha=i.fillOpacity,t.fillStyle=i.fillColor||i.color,t.fill(i.fillRule||"evenodd")),i.stroke&&0!==i.weight&&(t.setLineDash&&t.setLineDash(e.options&&e.options._dashArray||[]),t.globalAlpha=i.opacity,t.lineWidth=i.weight,t.strokeStyle=i.color,t.lineCap=i.lineCap,t.lineJoin=i.lineJoin,t.stroke())},_onClick:function(t){for(var e,i,n=this._map.mouseEventToLayerPoint(t),o=this._drawFirst;o;o=o.next)(e=o.layer).options.interactive&&e._containsPoint(n)&&(("click"===t.type||"preclick"===t.type)&&this._map._draggableMoved(e)||(i=e));this._fireEvent(!!i&&[i],t)},_onMouseMove:function(t){var e;!this._map||this._map.dragging.moving()||this._map._animatingZoom||(e=this._map.mouseEventToLayerPoint(t),this._handleMouseHover(t,e))},_handleMouseOut:function(t){var e=this._hoveredLayer;e&&(z(this._container,"leaflet-interactive"),this._fireEvent([e],t,"mouseout"),this._hoveredLayer=null,this._mouseHoverThrottled=!1)},_handleMouseHover:function(t,e){if(!this._mouseHoverThrottled){for(var i,n,o=this._drawFirst;o;o=o.next)(i=o.layer).options.interactive&&i._containsPoint(e)&&(n=i);n!==this._hoveredLayer&&(this._handleMouseOut(t),n&&(M(this._container,"leaflet-interactive"),this._fireEvent([n],t,"mouseover"),this._hoveredLayer=n)),this._fireEvent(!!this._hoveredLayer&&[this._hoveredLayer],t),this._mouseHoverThrottled=!0,setTimeout(a(function(){this._mouseHoverThrottled=!1},this),32)}},_fireEvent:function(t,e,i){this._map._fireDOMEvent(e,i||e.type,t)},_bringToFront:function(t){var e,i,n=t._order;n&&(e=n.next,i=n.prev,e&&((e.prev=i)?i.next=e:e&&(this._drawFirst=e),n.prev=this._drawLast,(this._drawLast.next=n).next=null,this._drawLast=n,this._requestRedraw(t)))},_bringToBack:function(t){var e,i,n=t._order;n&&(e=n.next,(i=n.prev)&&((i.next=e)?e.prev=i:i&&(this._drawLast=i),n.prev=null,n.next=this._drawFirst,this._drawFirst.prev=n,this._drawFirst=n,this._requestRedraw(t)))}});function Ui(t){return b.canvas?new Fi(t):null}var Vi=function(){try{return document.namespaces.add("lvml","urn:schemas-microsoft-com:vml"),function(t){return document.createElement("<lvml:"+t+' class="lvml">')}}catch(t){}return function(t){return document.createElement("<"+t+' xmlns="urn:schemas-microsoft.com:vml" class="lvml">')}}(),zt={_initContainer:function(){this._container=P("div","leaflet-vml-container")},_update:function(){this._map._animatingZoom||(Wi.prototype._update.call(this),this.fire("update"))},_initPath:function(t){var e=t._container=Vi("shape");M(e,"leaflet-vml-shape "+(this.options.className||"")),e.coordsize="1 1",t._path=Vi("path"),e.appendChild(t._path),this._updateStyle(t),this._layers[h(t)]=t},_addPath:function(t){var e=t._container;this._container.appendChild(e),t.options.interactive&&t.addInteractiveTarget(e)},_removePath:function(t){var e=t._container;T(e),t.removeInteractiveTarget(e),delete this._layers[h(t)]},_updateStyle:function(t){var e=t._stroke,i=t._fill,n=t.options,o=t._container;o.stroked=!!n.stroke,o.filled=!!n.fill,n.stroke?(e=e||(t._stroke=Vi("stroke")),o.appendChild(e),e.weight=n.weight+"px",e.color=n.color,e.opacity=n.opacity,n.dashArray?e.dashStyle=d(n.dashArray)?n.dashArray.join(" "):n.dashArray.replace(/( *, *)/g," "):e.dashStyle="",e.endcap=n.lineCap.replace("butt","flat"),e.joinstyle=n.lineJoin):e&&(o.removeChild(e),t._stroke=null),n.fill?(i=i||(t._fill=Vi("fill")),o.appendChild(i),i.color=n.fillColor||n.color,i.opacity=n.fillOpacity):i&&(o.removeChild(i),t._fill=null)},_updateCircle:function(t){var e=t._point.round(),i=Math.round(t._radius),n=Math.round(t._radiusY||i);this._setPath(t,t._empty()?"M0 0":"AL "+e.x+","+e.y+" "+i+","+n+" 0,23592600")},_setPath:function(t,e){t._path.v=e},_bringToFront:function(t){fe(t._container)},_bringToBack:function(t){ge(t._container)}},qi=b.vml?Vi:ct,Gi=Wi.extend({_initContainer:function(){this._container=qi("svg"),this._container.setAttribute("pointer-events","none"),this._rootGroup=qi("g"),this._container.appendChild(this._rootGroup)},_destroyContainer:function(){T(this._container),k(this._container),delete this._container,delete this._rootGroup,delete this._svgSize},_update:function(){var t,e,i;this._map._animatingZoom&&this._bounds||(Wi.prototype._update.call(this),e=(t=this._bounds).getSize(),i=this._container,this._svgSize&&this._svgSize.equals(e)||(this._svgSize=e,i.setAttribute("width",e.x),i.setAttribute("height",e.y)),Z(i,t.min),i.setAttribute("viewBox",[t.min.x,t.min.y,e.x,e.y].join(" ")),this.fire("update"))},_initPath:function(t){var e=t._path=qi("path");t.options.className&&M(e,t.options.className),t.options.interactive&&M(e,"leaflet-interactive"),this._updateStyle(t),this._layers[h(t)]=t},_addPath:function(t){this._rootGroup||this._initContainer(),this._rootGroup.appendChild(t._path),t.addInteractiveTarget(t._path)},_removePath:function(t){T(t._path),t.removeInteractiveTarget(t._path),delete this._layers[h(t)]},_updatePath:function(t){t._project(),t._update()},_updateStyle:function(t){var e=t._path,t=t.options;e&&(t.stroke?(e.setAttribute("stroke",t.color),e.setAttribute("stroke-opacity",t.opacity),e.setAttribute("stroke-width",t.weight),e.setAttribute("stroke-linecap",t.lineCap),e.setAttribute("stroke-linejoin",t.lineJoin),t.dashArray?e.setAttribute("stroke-dasharray",t.dashArray):e.removeAttribute("stroke-dasharray"),t.dashOffset?e.setAttribute("stroke-dashoffset",t.dashOffset):e.removeAttribute("stroke-dashoffset")):e.setAttribute("stroke","none"),t.fill?(e.setAttribute("fill",t.fillColor||t.color),e.setAttribute("fill-opacity",t.fillOpacity),e.setAttribute("fill-rule",t.fillRule||"evenodd")):e.setAttribute("fill","none"))},_updatePoly:function(t,e){this._setPath(t,dt(t._parts,e))},_updateCircle:function(t){var e=t._point,i=Math.max(Math.round(t._radius),1),n="a"+i+","+(Math.max(Math.round(t._radiusY),1)||i)+" 0 1,0 ",e=t._empty()?"M0 0":"M"+(e.x-i)+","+e.y+n+2*i+",0 "+n+2*-i+",0 ";this._setPath(t,e)},_setPath:function(t,e){t._path.setAttribute("d",e)},_bringToFront:function(t){fe(t._path)},_bringToBack:function(t){ge(t._path)}});function Ki(t){return b.svg||b.vml?new Gi(t):null}b.vml&&Gi.include(zt),A.include({getRenderer:function(t){t=(t=t.options.renderer||this._getPaneRenderer(t.options.pane)||this.options.renderer||this._renderer)||(this._renderer=this._createRenderer());return this.hasLayer(t)||this.addLayer(t),t},_getPaneRenderer:function(t){var e;return"overlayPane"!==t&&void 0!==t&&(void 0===(e=this._paneRenderers[t])&&(e=this._createRenderer({pane:t}),this._paneRenderers[t]=e),e)},_createRenderer:function(t){return this.options.preferCanvas&&Ui(t)||Ki(t)}});var Yi=xi.extend({initialize:function(t,e){xi.prototype.initialize.call(this,this._boundsToLatLngs(t),e)},setBounds:function(t){return this.setLatLngs(this._boundsToLatLngs(t))},_boundsToLatLngs:function(t){return[(t=g(t)).getSouthWest(),t.getNorthWest(),t.getNorthEast(),t.getSouthEast()]}});Gi.create=qi,Gi.pointsToPath=dt,wi.geometryToLayer=bi,wi.coordsToLatLng=Li,wi.coordsToLatLngs=Ti,wi.latLngToCoords=Mi,wi.latLngsToCoords=zi,wi.getFeature=Ci,wi.asFeature=Zi,A.mergeOptions({boxZoom:!0});var _t=n.extend({initialize:function(t){this._map=t,this._container=t._container,this._pane=t._panes.overlayPane,this._resetStateTimeout=0,t.on("unload",this._destroy,this)},addHooks:function(){S(this._container,"mousedown",this._onMouseDown,this)},removeHooks:function(){k(this._container,"mousedown",this._onMouseDown,this)},moved:function(){return this._moved},_destroy:function(){T(this._pane),delete this._pane},_resetState:function(){this._resetStateTimeout=0,this._moved=!1},_clearDeferredResetState:function(){0!==this._resetStateTimeout&&(clearTimeout(this._resetStateTimeout),this._resetStateTimeout=0)},_onMouseDown:function(t){if(!t.shiftKey||1!==t.which&&1!==t.button)return!1;this._clearDeferredResetState(),this._resetState(),re(),Le(),this._startPoint=this._map.mouseEventToContainerPoint(t),S(document,{contextmenu:Re,mousemove:this._onMouseMove,mouseup:this._onMouseUp,keydown:this._onKeyDown},this)},_onMouseMove:function(t){this._moved||(this._moved=!0,this._box=P("div","leaflet-zoom-box",this._container),M(this._container,"leaflet-crosshair"),this._map.fire("boxzoomstart")),this._point=this._map.mouseEventToContainerPoint(t);var t=new f(this._point,this._startPoint),e=t.getSize();Z(this._box,t.min),this._box.style.width=e.x+"px",this._box.style.height=e.y+"px"},_finish:function(){this._moved&&(T(this._box),z(this._container,"leaflet-crosshair")),ae(),Te(),k(document,{contextmenu:Re,mousemove:this._onMouseMove,mouseup:this._onMouseUp,keydown:this._onKeyDown},this)},_onMouseUp:function(t){1!==t.which&&1!==t.button||(this._finish(),this._moved&&(this._clearDeferredResetState(),this._resetStateTimeout=setTimeout(a(this._resetState,this),0),t=new s(this._map.containerPointToLatLng(this._startPoint),this._map.containerPointToLatLng(this._point)),this._map.fitBounds(t).fire("boxzoomend",{boxZoomBounds:t})))},_onKeyDown:function(t){27===t.keyCode&&(this._finish(),this._clearDeferredResetState(),this._resetState())}}),Ct=(A.addInitHook("addHandler","boxZoom",_t),A.mergeOptions({doubleClickZoom:!0}),n.extend({addHooks:function(){this._map.on("dblclick",this._onDoubleClick,this)},removeHooks:function(){this._map.off("dblclick",this._onDoubleClick,this)},_onDoubleClick:function(t){var e=this._map,i=e.getZoom(),n=e.options.zoomDelta,i=t.originalEvent.shiftKey?i-n:i+n;"center"===e.options.doubleClickZoom?e.setZoom(i):e.setZoomAround(t.containerPoint,i)}})),Zt=(A.addInitHook("addHandler","doubleClickZoom",Ct),A.mergeOptions({dragging:!0,inertia:!0,inertiaDeceleration:3400,inertiaMaxSpeed:1/0,easeLinearity:.2,worldCopyJump:!1,maxBoundsViscosity:0}),n.extend({addHooks:function(){var t;this._draggable||(t=this._map,this._draggable=new Xe(t._mapPane,t._container),this._draggable.on({dragstart:this._onDragStart,drag:this._onDrag,dragend:this._onDragEnd},this),this._draggable.on("predrag",this._onPreDragLimit,this),t.options.worldCopyJump&&(this._draggable.on("predrag",this._onPreDragWrap,this),t.on("zoomend",this._onZoomEnd,this),t.whenReady(this._onZoomEnd,this))),M(this._map._container,"leaflet-grab leaflet-touch-drag"),this._draggable.enable(),this._positions=[],this._times=[]},removeHooks:function(){z(this._map._container,"leaflet-grab"),z(this._map._container,"leaflet-touch-drag"),this._draggable.disable()},moved:function(){return this._draggable&&this._draggable._moved},moving:function(){return this._draggable&&this._draggable._moving},_onDragStart:function(){var t,e=this._map;e._stop(),this._map.options.maxBounds&&this._map.options.maxBoundsViscosity?(t=g(this._map.options.maxBounds),this._offsetLimit=_(this._map.latLngToContainerPoint(t.getNorthWest()).multiplyBy(-1),this._map.latLngToContainerPoint(t.getSouthEast()).multiplyBy(-1).add(this._map.getSize())),this._viscosity=Math.min(1,Math.max(0,this._map.options.maxBoundsViscosity))):this._offsetLimit=null,e.fire("movestart").fire("dragstart"),e.options.inertia&&(this._positions=[],this._times=[])},_onDrag:function(t){var e,i;this._map.options.inertia&&(e=this._lastTime=+new Date,i=this._lastPos=this._draggable._absPos||this._draggable._newPos,this._positions.push(i),this._times.push(e),this._prunePositions(e)),this._map.fire("move",t).fire("drag",t)},_prunePositions:function(t){for(;1<this._positions.length&&50<t-this._times[0];)this._positions.shift(),this._times.shift()},_onZoomEnd:function(){var t=this._map.getSize().divideBy(2),e=this._map.latLngToLayerPoint([0,0]);this._initialWorldOffset=e.subtract(t).x,this._worldWidth=this._map.getPixelWorldBounds().getSize().x},_viscousLimit:function(t,e){return t-(t-e)*this._viscosity},_onPreDragLimit:function(){var t,e;this._viscosity&&this._offsetLimit&&(t=this._draggable._newPos.subtract(this._draggable._startPos),e=this._offsetLimit,t.x<e.min.x&&(t.x=this._viscousLimit(t.x,e.min.x)),t.y<e.min.y&&(t.y=this._viscousLimit(t.y,e.min.y)),t.x>e.max.x&&(t.x=this._viscousLimit(t.x,e.max.x)),t.y>e.max.y&&(t.y=this._viscousLimit(t.y,e.max.y)),this._draggable._newPos=this._draggable._startPos.add(t))},_onPreDragWrap:function(){var t=this._worldWidth,e=Math.round(t/2),i=this._initialWorldOffset,n=this._draggable._newPos.x,o=(n-e+i)%t+e-i,n=(n+e+i)%t-e-i,t=Math.abs(o+i)<Math.abs(n+i)?o:n;this._draggable._absPos=this._draggable._newPos.clone(),this._draggable._newPos.x=t},_onDragEnd:function(t){var e,i,n,o,s=this._map,r=s.options,a=!r.inertia||t.noInertia||this._times.length<2;s.fire("dragend",t),!a&&(this._prunePositions(+new Date),t=this._lastPos.subtract(this._positions[0]),a=(this._lastTime-this._times[0])/1e3,e=r.easeLinearity,a=(t=t.multiplyBy(e/a)).distanceTo([0,0]),i=Math.min(r.inertiaMaxSpeed,a),t=t.multiplyBy(i/a),n=i/(r.inertiaDeceleration*e),(o=t.multiplyBy(-n/2).round()).x||o.y)?(o=s._limitOffset(o,s.options.maxBounds),x(function(){s.panBy(o,{duration:n,easeLinearity:e,noMoveStart:!0,animate:!0})})):s.fire("moveend")}})),St=(A.addInitHook("addHandler","dragging",Zt),A.mergeOptions({keyboard:!0,keyboardPanDelta:80}),n.extend({keyCodes:{left:[37],right:[39],down:[40],up:[38],zoomIn:[187,107,61,171],zoomOut:[189,109,54,173]},initialize:function(t){this._map=t,this._setPanDelta(t.options.keyboardPanDelta),this._setZoomDelta(t.options.zoomDelta)},addHooks:function(){var t=this._map._container;t.tabIndex<=0&&(t.tabIndex="0"),S(t,{focus:this._onFocus,blur:this._onBlur,mousedown:this._onMouseDown},this),this._map.on({focus:this._addHooks,blur:this._removeHooks},this)},removeHooks:function(){this._removeHooks(),k(this._map._container,{focus:this._onFocus,blur:this._onBlur,mousedown:this._onMouseDown},this),this._map.off({focus:this._addHooks,blur:this._removeHooks},this)},_onMouseDown:function(){var t,e,i;this._focused||(i=document.body,t=document.documentElement,e=i.scrollTop||t.scrollTop,i=i.scrollLeft||t.scrollLeft,this._map._container.focus(),window.scrollTo(i,e))},_onFocus:function(){this._focused=!0,this._map.fire("focus")},_onBlur:function(){this._focused=!1,this._map.fire("blur")},_setPanDelta:function(t){for(var e=this._panKeys={},i=this.keyCodes,n=0,o=i.left.length;n<o;n++)e[i.left[n]]=[-1*t,0];for(n=0,o=i.right.length;n<o;n++)e[i.right[n]]=[t,0];for(n=0,o=i.down.length;n<o;n++)e[i.down[n]]=[0,t];for(n=0,o=i.up.length;n<o;n++)e[i.up[n]]=[0,-1*t]},_setZoomDelta:function(t){for(var e=this._zoomKeys={},i=this.keyCodes,n=0,o=i.zoomIn.length;n<o;n++)e[i.zoomIn[n]]=t;for(n=0,o=i.zoomOut.length;n<o;n++)e[i.zoomOut[n]]=-t},_addHooks:function(){S(document,"keydown",this._onKeyDown,this)},_removeHooks:function(){k(document,"keydown",this._onKeyDown,this)},_onKeyDown:function(t){if(!(t.altKey||t.ctrlKey||t.metaKey)){var e,i,n=t.keyCode,o=this._map;if(n in this._panKeys)o._panAnim&&o._panAnim._inProgress||(i=this._panKeys[n],t.shiftKey&&(i=m(i).multiplyBy(3)),o.options.maxBounds&&(i=o._limitOffset(m(i),o.options.maxBounds)),o.options.worldCopyJump?(e=o.wrapLatLng(o.unproject(o.project(o.getCenter()).add(i))),o.panTo(e)):o.panBy(i));else if(n in this._zoomKeys)o.setZoom(o.getZoom()+(t.shiftKey?3:1)*this._zoomKeys[n]);else{if(27!==n||!o._popup||!o._popup.options.closeOnEscapeKey)return;o.closePopup()}Re(t)}}})),Et=(A.addInitHook("addHandler","keyboard",St),A.mergeOptions({scrollWheelZoom:!0,wheelDebounceTime:40,wheelPxPerZoomLevel:60}),n.extend({addHooks:function(){S(this._map._container,"wheel",this._onWheelScroll,this),this._delta=0},removeHooks:function(){k(this._map._container,"wheel",this._onWheelScroll,this)},_onWheelScroll:function(t){var e=He(t),i=this._map.options.wheelDebounceTime,e=(this._delta+=e,this._lastMousePos=this._map.mouseEventToContainerPoint(t),this._startTime||(this._startTime=+new Date),Math.max(i-(+new Date-this._startTime),0));clearTimeout(this._timer),this._timer=setTimeout(a(this._performZoom,this),e),Re(t)},_performZoom:function(){var t=this._map,e=t.getZoom(),i=this._map.options.zoomSnap||0,n=(t._stop(),this._delta/(4*this._map.options.wheelPxPerZoomLevel)),n=4*Math.log(2/(1+Math.exp(-Math.abs(n))))/Math.LN2,i=i?Math.ceil(n/i)*i:n,n=t._limitZoom(e+(0<this._delta?i:-i))-e;this._delta=0,this._startTime=null,n&&("center"===t.options.scrollWheelZoom?t.setZoom(e+n):t.setZoomAround(this._lastMousePos,e+n))}})),kt=(A.addInitHook("addHandler","scrollWheelZoom",Et),A.mergeOptions({tapHold:b.touchNative&&b.safari&&b.mobile,tapTolerance:15}),n.extend({addHooks:function(){S(this._map._container,"touchstart",this._onDown,this)},removeHooks:function(){k(this._map._container,"touchstart",this._onDown,this)},_onDown:function(t){var e;clearTimeout(this._holdTimeout),1===t.touches.length&&(e=t.touches[0],this._startPos=this._newPos=new p(e.clientX,e.clientY),this._holdTimeout=setTimeout(a(function(){this._cancel(),this._isTapValid()&&(S(document,"touchend",O),S(document,"touchend touchcancel",this._cancelClickPrevent),this._simulateEvent("contextmenu",e))},this),600),S(document,"touchend touchcancel contextmenu",this._cancel,this),S(document,"touchmove",this._onMove,this))},_cancelClickPrevent:function t(){k(document,"touchend",O),k(document,"touchend touchcancel",t)},_cancel:function(){clearTimeout(this._holdTimeout),k(document,"touchend touchcancel contextmenu",this._cancel,this),k(document,"touchmove",this._onMove,this)},_onMove:function(t){t=t.touches[0];this._newPos=new p(t.clientX,t.clientY)},_isTapValid:function(){return this._newPos.distanceTo(this._startPos)<=this._map.options.tapTolerance},_simulateEvent:function(t,e){t=new MouseEvent(t,{bubbles:!0,cancelable:!0,view:window,screenX:e.screenX,screenY:e.screenY,clientX:e.clientX,clientY:e.clientY});t._simulated=!0,e.target.dispatchEvent(t)}})),Ot=(A.addInitHook("addHandler","tapHold",kt),A.mergeOptions({touchZoom:b.touch,bounceAtZoomLimits:!0}),n.extend({addHooks:function(){M(this._map._container,"leaflet-touch-zoom"),S(this._map._container,"touchstart",this._onTouchStart,this)},removeHooks:function(){z(this._map._container,"leaflet-touch-zoom"),k(this._map._container,"touchstart",this._onTouchStart,this)},_onTouchStart:function(t){var e,i,n=this._map;!t.touches||2!==t.touches.length||n._animatingZoom||this._zooming||(e=n.mouseEventToContainerPoint(t.touches[0]),i=n.mouseEventToContainerPoint(t.touches[1]),this._centerPoint=n.getSize()._divideBy(2),this._startLatLng=n.containerPointToLatLng(this._centerPoint),"center"!==n.options.touchZoom&&(this._pinchStartLatLng=n.containerPointToLatLng(e.add(i)._divideBy(2))),this._startDist=e.distanceTo(i),this._startZoom=n.getZoom(),this._moved=!1,this._zooming=!0,n._stop(),S(document,"touchmove",this._onTouchMove,this),S(document,"touchend touchcancel",this._onTouchEnd,this),O(t))},_onTouchMove:function(t){if(t.touches&&2===t.touches.length&&this._zooming){var e=this._map,i=e.mouseEventToContainerPoint(t.touches[0]),n=e.mouseEventToContainerPoint(t.touches[1]),o=i.distanceTo(n)/this._startDist;if(this._zoom=e.getScaleZoom(o,this._startZoom),!e.options.bounceAtZoomLimits&&(this._zoom<e.getMinZoom()&&o<1||this._zoom>e.getMaxZoom()&&1<o)&&(this._zoom=e._limitZoom(this._zoom)),"center"===e.options.touchZoom){if(this._center=this._startLatLng,1==o)return}else{i=i._add(n)._divideBy(2)._subtract(this._centerPoint);if(1==o&&0===i.x&&0===i.y)return;this._center=e.unproject(e.project(this._pinchStartLatLng,this._zoom).subtract(i),this._zoom)}this._moved||(e._moveStart(!0,!1),this._moved=!0),r(this._animRequest);n=a(e._move,e,this._center,this._zoom,{pinch:!0,round:!1},void 0);this._animRequest=x(n,this,!0),O(t)}},_onTouchEnd:function(){this._moved&&this._zooming?(this._zooming=!1,r(this._animRequest),k(document,"touchmove",this._onTouchMove,this),k(document,"touchend touchcancel",this._onTouchEnd,this),this._map.options.zoomAnimation?this._map._animateZoom(this._center,this._map._limitZoom(this._zoom),!0,this._map.options.zoomSnap):this._map._resetView(this._center,this._map._limitZoom(this._zoom))):this._zooming=!1}})),Xi=(A.addInitHook("addHandler","touchZoom",Ot),A.BoxZoom=_t,A.DoubleClickZoom=Ct,A.Drag=Zt,A.Keyboard=St,A.ScrollWheelZoom=Et,A.TapHold=kt,A.TouchZoom=Ot,t.Bounds=f,t.Browser=b,t.CRS=ot,t.Canvas=Fi,t.Circle=vi,t.CircleMarker=gi,t.Class=et,t.Control=B,t.DivIcon=Ri,t.DivOverlay=Ai,t.DomEvent=mt,t.DomUtil=pt,t.Draggable=Xe,t.Evented=it,t.FeatureGroup=ci,t.GeoJSON=wi,t.GridLayer=Ni,t.Handler=n,t.Icon=di,t.ImageOverlay=Ei,t.LatLng=v,t.LatLngBounds=s,t.Layer=o,t.LayerGroup=ui,t.LineUtil=vt,t.Map=A,t.Marker=mi,t.Mixin=ft,t.Path=fi,t.Point=p,t.PolyUtil=gt,t.Polygon=xi,t.Polyline=yi,t.Popup=Bi,t.PosAnimation=Fe,t.Projection=wt,t.Rectangle=Yi,t.Renderer=Wi,t.SVG=Gi,t.SVGOverlay=Oi,t.TileLayer=Di,t.Tooltip=Ii,t.Transformation=at,t.Util=tt,t.VideoOverlay=ki,t.bind=a,t.bounds=_,t.canvas=Ui,t.circle=function(t,e,i){return new vi(t,e,i)},t.circleMarker=function(t,e){return new gi(t,e)},t.control=Ue,t.divIcon=function(t){return new Ri(t)},t.extend=l,t.featureGroup=function(t,e){return new ci(t,e)},t.geoJSON=Si,t.geoJson=Mt,t.gridLayer=function(t){return new Ni(t)},t.icon=function(t){return new di(t)},t.imageOverlay=function(t,e,i){return new Ei(t,e,i)},t.latLng=w,t.latLngBounds=g,t.layerGroup=function(t,e){return new ui(t,e)},t.map=function(t,e){return new A(t,e)},t.marker=function(t,e){return new mi(t,e)},t.point=m,t.polygon=function(t,e){return new xi(t,e)},t.polyline=function(t,e){return new yi(t,e)},t.popup=function(t,e){return new Bi(t,e)},t.rectangle=function(t,e){return new Yi(t,e)},t.setOptions=c,t.stamp=h,t.svg=Ki,t.svgOverlay=function(t,e,i){return new Oi(t,e,i)},t.tileLayer=ji,t.tooltip=function(t,e){return new Ii(t,e)},t.transformation=ht,t.version="1.9.4",t.videoOverlay=function(t,e,i){return new ki(t,e,i)},window.L);t.noConflict=function(){return window.L=Xi,this},window.L=t});
//# sourceMappingURL=leaflet.js.map
  </script>
  <style>
/* ── RESPONSIVE REDESIGN OVERRIDES ───────────────────────────────────── */

/* Neutralize old layout wrappers */
#main-layout { display: contents !important; }
#sidebar, #sidebar-overlay, #context-panel, #bottom-sheet { display: none !important; }

/* App shell — full-height column */
#app-shell {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  overflow: hidden;
}

/* ── TOP BAR ── */
#top-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 52px;
  padding: 0 10px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  position: relative;
  z-index: 100;
}

#btn-menu {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px; color: var(--muted);
  flex-shrink: 0; cursor: pointer;
  background: none; border: none;
}
#btn-menu:hover { color: var(--text); background: var(--bg-inset); }

.ref-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  background: var(--bg-inset); border: 1px solid var(--border);
  border-radius: 20px; color: var(--text);
  font-size: 15px; font-weight: 600;
  cursor: pointer; white-space: nowrap;
  flex: 1; min-width: 0; max-width: 220px;
  justify-content: space-between;
}
.ref-pill:hover { border-color: var(--gold-light); }
.ref-pill-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.topbar-gap { flex: 1; }

.trans-pill {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 10px;
  background: var(--bg-inset); border: 1px solid var(--border);
  border-radius: 16px; color: var(--text-dim);
  font-size: 13px; font-weight: 500;
  cursor: pointer; white-space: nowrap; flex-shrink: 0;
}
.trans-pill:hover { border-color: var(--gold-light); color: var(--text); }

#btn-search-open, #btn-parallel-new {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px; color: var(--muted);
  flex-shrink: 0; cursor: pointer;
  background: none; border: none;
}
#btn-search-open:hover, #btn-parallel-new:hover { color: var(--text); background: var(--bg-inset); }
#btn-parallel-new.active { color: var(--gold-light); }

/* ── LAYOUT CONTAINER ── */
#layout-container {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

/* ── READER AREA ── */
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
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.chapter-title-center {
  flex: 1;
  text-align: center;
  min-width: 0;
}

#chapter-book-display {
  font-size: 16px; font-weight: 700;
  color: var(--gold-light); line-height: 1.2;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

#chapter-num-display {
  font-size: 11px; color: var(--muted);
}

.ch-nav-btn {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px; color: var(--muted);
  cursor: pointer; flex-shrink: 0;
  background: none; border: 1px solid var(--border);
  transition: all 0.1s;
}
.ch-nav-btn:hover { color: var(--text); border-color: var(--gold-light); }
.ch-nav-btn:disabled { opacity: 0.3; pointer-events: none; }

#chapter-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px 80px;
}

/* ── STUDY PANEL (desktop right column + mobile bottom sheet) ── */
#study-panel {
  display: none;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-panel);
}

.sheet-handle-row {
  display: none;
  justify-content: center;
  padding: 10px 0 6px;
  flex-shrink: 0;
  cursor: grab;
  touch-action: none;
}
.sheet-handle-pill {
  width: 40px; height: 4px;
  background: var(--border); border-radius: 2px;
}

.panel-tab-bar-wrap {
  position: relative;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
}
.panel-tab-bar-wrap::after {
  content: '';
  position: absolute;
  right: 0; top: 0; bottom: 0;
  width: 36px;
  background: linear-gradient(to right, transparent, var(--bg-panel, var(--bg)));
  pointer-events: none;
  transition: opacity 0.2s;
}
.panel-tab-bar-wrap.scrolled-end::after { opacity: 0; }

.panel-tab-bar {
  display: flex;
  overflow-x: auto;
  scrollbar-width: none;
}
.panel-tab-bar::-webkit-scrollbar { display: none; }

.panel-tab-bar .tab-btn {
  padding: 8px 9px;
  font-size: 11.5px; color: var(--muted);
  white-space: nowrap;
  border-bottom: 2px solid transparent;
  flex-shrink: 0; cursor: pointer;
  background: none;
  border-top: none; border-left: none; border-right: none;
  transition: color 0.1s;
}
.panel-tab-bar .tab-btn.active {
  color: var(--gold-light);
  border-bottom-color: var(--gold-light);
}

.tab-content {
  flex: 1; overflow-y: auto;
  padding: 14px;
}
.tab-content.hidden { display: none; }

/* ── MOBILE BOTTOM BAR ── */
#mobile-bottom-bar {
  display: flex;
  height: 52px;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.mob-nav-btn {
  flex: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 2px; color: var(--muted);
  font-size: 11px; cursor: pointer;
  background: none; border: none; padding: 4px;
  transition: color 0.1s;
}
.mob-nav-btn:hover { color: var(--gold-light); }
.mob-nav-btn:disabled { opacity: 0.35; pointer-events: none; }

/* ── MOBILE-SPECIFIC OVERRIDES ── */
@media (max-width: 767px) {
  #study-panel {
    display: flex;
    position: fixed;
    left: 0; right: 0; bottom: 0;
    height: 0;
    z-index: 500;
    border-top: 1px solid var(--border);
    border-radius: 16px 16px 0 0;
    transition: height 0.3s cubic-bezier(0.4,0,0.2,1);
    box-shadow: 0 -4px 24px rgba(0,0,0,0.35);
  }
  #study-panel.panel-open { height: 58%; }
  #study-panel.panel-expanded { height: 92%; }

  .sheet-handle-row { display: flex; }

  #chapter-content { padding-bottom: 56px; }

  .app-title { display: none; }
}

/* ── DESKTOP ── */
@media (min-width: 768px) {
  #study-panel {
    display: flex;
    width: 340px; flex-shrink: 0;
    border-left: 1px solid var(--border);
  }
  #mobile-bottom-bar { display: none; }
  #chapter-content { padding: 20px 28px 40px; }
  #top-bar { padding: 0 16px; gap: 10px; }
}

@media (min-width: 768px) and (max-width: 1023px) {
  #study-panel { width: 290px; }
}

/* ── PICKER MODALS ── */
.picker-overlay {
  position: fixed; inset: 0;
  z-index: 800;
  display: flex; align-items: flex-end;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s;
}
.picker-overlay.open {
  pointer-events: auto; opacity: 1;
}

.picker-backdrop {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.6);
}

.picker-sheet {
  position: relative; width: 100%;
  max-height: 82vh;
  background: var(--bg-panel);
  border-radius: 18px 18px 0 0;
  display: flex; flex-direction: column;
  overflow: hidden;
  transform: translateY(100%);
  transition: transform 0.3s cubic-bezier(0.4,0,0.2,1);
  box-shadow: 0 -4px 32px rgba(0,0,0,0.4);
}
.picker-overlay.open .picker-sheet { transform: translateY(0); }

.picker-header {
  display: flex; align-items: center;
  gap: 8px; padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.picker-tab-btn {
  flex: 1; padding: 8px 10px;
  font-size: 13px; font-weight: 600;
  color: var(--muted);
  background: var(--bg-inset);
  border-radius: 8px; cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}
.picker-tab-btn.active {
  background: var(--gold-dark);
  color: #0a0a14;
  border-color: var(--gold-dark);
}

.picker-close {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%; background: var(--bg-inset);
  color: var(--muted); font-size: 14px;
  cursor: pointer; flex-shrink: 0; border: none;
}
.picker-close:hover { color: var(--text); background: var(--border); }

.picker-body { flex: 1; overflow-y: auto; padding: 12px; }

.picker-book-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 5px;
}

.picker-book-btn {
  padding: 8px 2px;
  font-size: 9.5px; font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text-dim);
  background: var(--bg-inset); border: 1px solid var(--border);
  border-radius: 6px; cursor: pointer;
  text-align: center; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  transition: all 0.1s;
}
.picker-book-btn:hover, .picker-book-btn.active {
  background: var(--gold-dark); color: #0a0a14;
  border-color: var(--gold-dark);
}

.picker-chapter-header {
  display: flex; align-items: center;
  gap: 12px; margin-bottom: 12px;
}

.picker-back-btn {
  font-size: 13px; color: var(--gold-light);
  cursor: pointer; background: none; border: none; padding: 4px 0;
}

#picker-selected-book {
  font-size: 16px; font-weight: 700; color: var(--text);
}

.picker-chapter-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 5px;
}

.picker-chapter-btn {
  padding: 11px 2px;
  font-size: 14px; font-weight: 500;
  color: var(--text-dim);
  background: var(--bg-inset); border: 1px solid var(--border);
  border-radius: 6px; cursor: pointer;
  text-align: center; transition: all 0.1s;
}
.picker-chapter-btn:hover { background: var(--bg-selected); color: var(--text); }
.picker-chapter-btn.active {
  background: var(--gold-dark); color: #0a0a14;
  border-color: var(--gold-dark); font-weight: 800;
}

/* Translation picker */
.picker-sheet--trans { max-height: 65vh; }
.picker-title { font-size: 15px; font-weight: 600; color: var(--text); }

.trans-picker-list { overflow-y: auto; padding: 8px 10px 16px; }

.trans-picker-item {
  display: flex; align-items: center; gap: 12px;
  width: 100%; padding: 12px 14px;
  border-radius: 8px; cursor: pointer;
  background: none; border: none;
  color: var(--text); transition: background 0.1s;
  text-align: left;
}
.trans-picker-item:hover { background: var(--bg-inset); }
.trans-picker-item.active { background: color-mix(in srgb, var(--gold-dark) 15%, transparent); }

.trans-abbr { font-size: 15px; font-weight: 800; color: var(--gold-light); width: 56px; flex-shrink: 0; }
.trans-name { font-size: 13px; color: var(--text-dim); }

/* ── MENU DRAWER ── */
#menu-drawer {
  position: fixed;
  left: 0; top: 52px;
  width: 220px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 0 0 12px 0;
  z-index: 600; overflow: hidden;
  transform: translateX(-100%);
  transition: transform 0.25s cubic-bezier(0.4,0,0.2,1);
  box-shadow: 4px 4px 20px rgba(0,0,0,0.35);
}
#menu-drawer.open { transform: translateX(0); }

.menu-drawer-item {
  display: flex; align-items: center; gap: 12px;
  padding: 13px 16px;
  font-size: 14px; color: var(--text);
  cursor: pointer;
  border-bottom: 1px solid var(--border);
  background: none;
  border-left: none; border-right: none; border-top: none;
  width: 100%; text-align: left;
}
.menu-drawer-item:hover { background: var(--bg-inset); }
.menu-drawer-item:last-child { border-bottom: none; }
.menu-drawer-item.danger { color: #e05555; }

/* Desktop center pickers as dialogs */
@media (min-width: 768px) {
  .picker-overlay { align-items: center; justify-content: center; }
  .picker-sheet {
    border-radius: 12px;
    width: 500px; max-width: 90vw;
    transform: scale(0.94) translateY(0);
    box-shadow: 0 16px 48px rgba(0,0,0,0.55);
  }
  .picker-overlay.open .picker-sheet { transform: scale(1) translateY(0); }
  .picker-sheet--trans { width: 380px; }
  .picker-book-grid { grid-template-columns: repeat(8, 1fr); }
  .picker-chapter-grid { grid-template-columns: repeat(10, 1fr); }
}
  </style>
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
      <h1>Covenant Study</h1>
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

    <!-- Menu button (sessions, bookmarks, history) -->
    <button id="btn-menu" aria-label="Open menu" aria-expanded="false" aria-controls="menu-drawer">
      <svg width="18" height="14" viewBox="0 0 18 14" fill="none" aria-hidden="true">
        <path d="M1 1h16M1 7h16M1 13h16" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
      </svg>
    </button>

    <!-- Reference pill — tapping opens the book/chapter picker -->
    <button id="btn-ref-pill" class="ref-pill" aria-label="Navigate to book and chapter" aria-haspopup="dialog">
      <span class="ref-pill-text" id="ref-display">John 3</span>
      <svg class="pill-chevron" width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
        <path d="M1 1l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>

    <div class="topbar-gap"></div>

    <!-- Translation pill -->
    <button id="btn-trans-pill" class="trans-pill" aria-label="Select translation" aria-haspopup="dialog">
      <span id="trans-display">KJV</span>
      <svg class="pill-chevron" width="8" height="5" viewBox="0 0 8 5" fill="none" aria-hidden="true">
        <path d="M1 1l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>

    <!-- Search button -->
    <button id="btn-search-open" aria-label="Search scriptures" aria-controls="search-overlay">
      <svg width="17" height="17" viewBox="0 0 17 17" fill="none" aria-hidden="true">
        <circle cx="7" cy="7" r="5.2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M10.5 10.5L15 15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>

    <!-- Parallel toggle -->
    <button id="btn-parallel-new" aria-pressed="false" aria-label="Toggle parallel view">
      <svg width="14" height="13" viewBox="0 0 14 13" fill="none" aria-hidden="true">
        <rect x="0.7" y="0.7" width="5" height="11.6" rx="1" stroke="currentColor" stroke-width="1.3"/>
        <rect x="8.3" y="0.7" width="5" height="11.6" rx="1" stroke="currentColor" stroke-width="1.3"/>
      </svg>
    </button>

    <!-- User chip -->
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

  <!-- MENU DRAWER (sessions / bookmarks / history / admin) -->
  <div id="menu-drawer" role="dialog" aria-label="Menu" aria-hidden="true">
    <button class="menu-drawer-item" id="menu-item-sessions" aria-label="Study Sessions">
      <svg width="15" height="15" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <rect x="1" y="1" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
        <path d="M4 13h6M7 10v3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      </svg>
      Study Sessions
    </button>
    <button class="menu-drawer-item" id="menu-item-bookmarks" aria-label="Bookmarks">
      <svg width="15" height="15" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M2 1.5h10v11l-5-3-5 3V1.5z" stroke="currentColor" stroke-width="1.2"/>
      </svg>
      Bookmarks
    </button>
    <button class="menu-drawer-item" id="menu-item-history" aria-label="History">
      <svg width="15" height="15" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.2"/>
        <path d="M7 4v3.5l2 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      </svg>
      History
    </button>
    <button class="menu-drawer-item" id="menu-item-admin" style="display:none" aria-label="Manage Users">
      <svg width="15" height="15" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <circle cx="5" cy="4.5" r="2.5" stroke="currentColor" stroke-width="1.2"/>
        <path d="M1 12c0-2.2 1.8-4 4-4s4 1.8 4 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
        <path d="M11 6v4M9 8h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      </svg>
      Manage Users
    </button>
  </div><!-- /#menu-drawer -->

  <!-- NAV PICKER MODAL — book/chapter grid -->
  <div id="nav-picker" class="picker-overlay" role="dialog" aria-modal="true" aria-label="Navigate to book and chapter" aria-hidden="true">
    <div class="picker-backdrop" id="nav-picker-backdrop"></div>
    <div class="picker-sheet">
      <div class="picker-header">
        <button class="picker-tab-btn active" data-testament="OT" id="picker-ot-btn">Old Testament</button>
        <button class="picker-tab-btn" data-testament="NT" id="picker-nt-btn">New Testament</button>
        <button class="picker-close" id="btn-nav-picker-close" aria-label="Close">✕</button>
      </div>
      <div class="picker-body">
        <div id="picker-book-view">
          <div id="picker-book-grid" class="picker-book-grid"></div>
        </div>
        <div id="picker-chapter-view" class="hidden">
          <div class="picker-chapter-header">
            <button class="picker-back-btn" id="btn-picker-back">← Books</button>
            <span id="picker-selected-book"></span>
          </div>
          <div id="picker-chapter-grid" class="picker-chapter-grid"></div>
        </div>
      </div>
    </div>
  </div><!-- /#nav-picker -->

  <!-- TRANSLATION PICKER MODAL -->
  <div id="trans-picker" class="picker-overlay" role="dialog" aria-modal="true" aria-label="Select translation" aria-hidden="true">
    <div class="picker-backdrop" id="trans-picker-backdrop"></div>
    <div class="picker-sheet picker-sheet--trans">
      <div class="picker-header">
        <span class="picker-title">Select Translation</span>
        <button class="picker-close" id="btn-trans-picker-close" aria-label="Close">✕</button>
      </div>
      <div id="trans-picker-list" class="trans-picker-list"></div>
    </div>
  </div><!-- /#trans-picker -->

  <!-- LAYOUT CONTAINER — reader + study panel -->
  <div id="layout-container">

    <!-- READER AREA -->
    <main id="reader-area" role="main" aria-label="Scripture reader">

      <div id="chapter-header">
        <button class="ch-nav-btn" id="btn-prev-chapter" aria-label="Previous chapter">
          <svg width="8" height="13" viewBox="0 0 8 13" fill="none" aria-hidden="true">
            <path d="M6 1.5L2 6.5l4 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <div class="chapter-title-center">
          <div id="chapter-book-display">John</div>
          <div id="chapter-num-display">Chapter 3</div>
        </div>
        <button class="ch-nav-btn" id="btn-next-chapter" aria-label="Next chapter">
          <svg width="8" height="13" viewBox="0 0 8 13" fill="none" aria-hidden="true">
            <path d="M2 1.5l4 5-4 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div><!-- /#chapter-header -->

      <div id="chapter-content" class="scroll-y" role="region" aria-label="Chapter text" aria-live="polite" aria-atomic="false">
        <div class="loading-spinner" aria-label="Loading chapter">Loading…</div>
      </div><!-- /#chapter-content -->

    </main><!-- /#reader-area -->

    <!-- STUDY PANEL — right column desktop / bottom sheet mobile -->
    <aside id="study-panel" aria-label="Study tools">

      <div class="sheet-handle-row" id="sheet-drag-handle" aria-hidden="true">
        <div class="sheet-handle-pill"></div>
      </div>

      <div class="panel-tab-bar-wrap">
        <div class="panel-tab-bar" role="tablist" aria-label="Study panel tabs">
          <button class="tab-btn active" role="tab" aria-selected="true" data-tab="crossrefs">Cross-refs</button>
          <button class="tab-btn" role="tab" aria-selected="false" data-tab="strongs">Strong's</button>
          <button class="tab-btn" role="tab" aria-selected="false" data-tab="interlinear">Interlinear</button>
          <button class="tab-btn" role="tab" aria-selected="false" data-tab="commentary">Commentary</button>
          <button class="tab-btn" role="tab" aria-selected="false" data-tab="notes">Notes</button>
          <button class="tab-btn" role="tab" aria-selected="false" data-tab="maps">🗺 Maps</button>
        </div>
      </div>

      <div class="tab-content" id="tab-crossrefs" role="tabpanel">
        <div class="panel-empty">
          <div class="panel-empty-icon" aria-hidden="true">✝</div>
          <div class="panel-empty-text">Tap a verse to see cross-references</div>
        </div>
      </div>

      <div class="tab-content hidden" id="tab-strongs" role="tabpanel">
        <div class="panel-empty">
          <div class="panel-empty-icon" aria-hidden="true">α</div>
          <div class="panel-empty-text">Tap a highlighted word for Strong's definition</div>
        </div>
      </div>

      <div class="tab-content hidden" id="tab-interlinear" role="tabpanel">
        <div class="panel-empty">
          <div class="panel-empty-icon" aria-hidden="true">λ</div>
          <div class="panel-empty-text">Select a verse to view interlinear text</div>
        </div>
      </div>

      <div class="tab-content hidden" id="tab-commentary" role="tabpanel">
        <div class="panel-empty">
          <div class="panel-empty-icon" aria-hidden="true">📜</div>
          <div class="panel-empty-text">Select a verse to read commentary</div>
        </div>
      </div>

      <div class="tab-content hidden" id="tab-notes" role="tabpanel">
        <textarea class="notes-textarea" placeholder="Add a personal note…" aria-label="Personal verse note" rows="4" style="margin-top:10px;width:100%;box-sizing:border-box;resize:vertical;background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:10px;font-size:13px;"></textarea>
        <div class="notes-save-row" style="margin-top:8px">
          <button class="notes-save-btn">Save Note</button>
        </div>
      </div>

      <div class="tab-content hidden" id="tab-maps" role="tabpanel">
        <div class="panel-empty">
          <div class="panel-empty-icon" aria-hidden="true">🗺</div>
          <div class="panel-empty-text">Select a location to view on map</div>
        </div>
      </div>

    </aside><!-- /#study-panel -->

  </div><!-- /#layout-container -->

  <!-- MOBILE BOTTOM BAR — prev / study / next -->
  <nav id="mobile-bottom-bar" aria-label="Chapter navigation">
    <button class="mob-nav-btn" id="btn-mob-prev" aria-label="Previous chapter">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M10 3L6 8l4 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>Prev</span>
    </button>
    <button class="mob-nav-btn" id="btn-mob-study" aria-label="Open study tools">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <rect x="1" y="2" width="14" height="11" rx="2" stroke="currentColor" stroke-width="1.4"/>
        <path d="M4 6h8M4 9h5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
      </svg>
      <span>Study</span>
    </button>
    <button class="mob-nav-btn" id="btn-mob-next" aria-label="Next chapter">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M6 3l4 5-4 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>Next</span>
    </button>
  </nav><!-- /#mobile-bottom-bar -->

  <!-- LEGACY STUBS — kept so JS querySelector calls don't crash -->
  <div id="main-layout" aria-hidden="true" style="display:none">
    <aside id="sidebar" aria-hidden="true"></aside>
    <aside id="context-panel" aria-hidden="true"></aside>
  </div>
  <div id="bottom-sheet" aria-hidden="true" style="display:none"></div>

  <!-- Legacy sidebar/reader/panel stubs removed; structure replaced above -->

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
   wn-bible-01 — Covenant Study
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

  const initialsEl = document.querySelector('#user-chip .user-initials');
  const nameEl = document.querySelector('#user-chip .user-display-name');
  const adminItem = document.querySelector('.user-dropdown .admin-item');

  const displayName = currentUser.display_name || currentUser.username || '?';
  const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  if (initialsEl) initialsEl.textContent = initials;
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
  // Delegate to the reader's switchTab for consistent behaviour
  if (typeof switchTab === 'function') switchTab(tabName);
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
   Covenant Study · wn-bible-01 · Wittycomp Lab
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

  // Update chapter title displays
  const bookDisplay = $('#chapter-book-display');
  const numDisplay  = $('#chapter-num-display');
  if (bookDisplay) bookDisplay.textContent = book;
  if (numDisplay)  numDisplay.textContent  = `Chapter ${chapter}`;
  updateRefDisplay();

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

    // Auto-load cross-refs and interlinear for verse 1 so the study panel always has content
    if (!verseHighlight) {
      loadCrossRefs(`${book} ${chapter}:1`);
      if (state.activeTab === 'interlinear') loadInterlinear(`${book} ${chapter}:1`);
    }
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

  // Clicking anywhere on the row (except a Strong's word) selects the verse
  row.addEventListener('click', (e) => {
    if (!e.target.closest('.has-strongs')) {
      const ref = `${state.currentBook} ${state.currentChapter}:${verseNum}`;
      selectVerse(ref);
    }
  });

  const numEl = el('span', { class: 'verse-num' }, String(verseNum));
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

    const refs = data.cross_references || data.crossrefs || data.refs || [];
    if (refs.length === 0) {
      container.innerHTML = '<p class="empty-state">No cross-references found.</p>';
      return;
    }

    const header = el('p', { class: 'xref-header' }, `Cross-references for ${ref}`);
    container.appendChild(header);

    const chipList = el('div', { class: 'xref-chip-list' });
    for (const xref of refs) {
      // API shape: {book, chapter, verse_start, verse_end, votes}
      let xrefRef, xrefLabel;
      if (xref.book) {
        const vEnd = xref.verse_end && xref.verse_end !== xref.verse_start ? `-${xref.verse_end}` : '';
        xrefRef   = `${xref.book} ${xref.chapter}:${xref.verse_start}`;
        xrefLabel = `${xref.book} ${xref.chapter}:${xref.verse_start}${vEnd}`;
      } else {
        xrefRef = xref.ref || xref.reference || String(xref);
        xrefLabel = xrefRef;
      }
      const chip = el('button', {
        class: 'xref-chip',
        title: xrefLabel,
        onclick: () => navigateToRef(xrefRef),
      }, xrefLabel);
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
      el('td', { class: 'il-english'  }, word.gloss || word.english || word.text || ''),
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
    const subtitle = place.notes
      ? `<br><small>${escHtml(place.notes)}</small>`
      : place.refs
        ? `<br><small>${place.refs.map(escHtml).join(', ')}</small>`
        : '';
    const popup = `<strong>${escHtml(place.name)}</strong>${subtitle}`;
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

  // Load data for newly-visible tab, falling back to verse 1 of current chapter
  const activeRef = state.currentVerse
    || (state.currentBook ? `${state.currentBook} ${state.currentChapter}:1` : null);
  if (activeRef) {
    if (tabName === 'interlinear') loadInterlinear(activeRef);
    if (tabName === 'commentary')  loadCommentary(activeRef);
  }
}

function openBottomSheet() {
  if (state.isDesktop()) return; // desktop: panel always visible
  const panel = $('#study-panel');
  if (!panel) return;
  panel.classList.add('panel-open');
  state.bottomSheetOpen = true;
  document.body.classList.add('sheet-open');
}

function closeBottomSheet() {
  const panel = $('#study-panel');
  if (!panel) return;
  panel.classList.remove('panel-open');
  panel.classList.remove('panel-expanded');
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
  const btn        = $('#btn-parallel-new');

  if (!readerArea) return;

  if (state.parallelMode) {
    readerArea.classList.add('parallel-mode');
    if (btn) btn.classList.add('active');

    // Pick a complementary translation
    if (!state.parallelTranslation) {
      const avail = state.cachedTranslations || [];
      const alts  = avail.filter(t => t !== state.currentTranslation);
      state.parallelTranslation = alts.includes('AKJV') ? 'AKJV'
        : alts.includes('ASV') ? 'ASV'
        : alts[0] || 'KJV';
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

// ── 11. NAVIGATION PICKER ─────────────────────────────────────────────────

const _BOOK_ABBR = {
  'Genesis':'GEN','Exodus':'EXO','Leviticus':'LEV','Numbers':'NUM','Deuteronomy':'DEU',
  'Joshua':'JOS','Judges':'JDG','Ruth':'RUT','1 Samuel':'1SA','2 Samuel':'2SA',
  '1 Kings':'1KI','2 Kings':'2KI','1 Chronicles':'1CH','2 Chronicles':'2CH',
  'Ezra':'EZR','Nehemiah':'NEH','Esther':'EST','Job':'JOB','Psalms':'PSA',
  'Proverbs':'PRO','Ecclesiastes':'ECC','Song of Solomon':'SNG','Isaiah':'ISA',
  'Jeremiah':'JER','Lamentations':'LAM','Ezekiel':'EZK','Daniel':'DAN','Hosea':'HOS',
  'Joel':'JOL','Amos':'AMO','Obadiah':'OBA','Jonah':'JON','Micah':'MIC',
  'Nahum':'NAH','Habakkuk':'HAB','Zephaniah':'ZEP','Haggai':'HAG','Zechariah':'ZEC',
  'Malachi':'MAL','Matthew':'MAT','Mark':'MRK','Luke':'LUK','John':'JHN',
  'Acts':'ACT','Romans':'ROM','1 Corinthians':'1CO','2 Corinthians':'2CO',
  'Galatians':'GAL','Ephesians':'EPH','Philippians':'PHP','Colossians':'COL',
  '1 Thessalonians':'1TH','2 Thessalonians':'2TH','1 Timothy':'1TI','2 Timothy':'2TI',
  'Titus':'TIT','Philemon':'PHM','Hebrews':'HEB','James':'JAS','1 Peter':'1PE',
  '2 Peter':'2PE','1 John':'1JN','2 John':'2JN','3 John':'3JN','Jude':'JUD',
  'Revelation':'REV',
};

let _pickerTestament = 'OT';

function openNavPicker() {
  _buildPickerBookGrid(_pickerTestament);
  const picker = $('#nav-picker');
  if (picker) { picker.classList.add('open'); picker.setAttribute('aria-hidden','false'); }
}

function closeNavPicker() {
  const picker = $('#nav-picker');
  if (picker) { picker.classList.remove('open'); picker.setAttribute('aria-hidden','true'); }
}

function _buildPickerBookGrid(testament) {
  _pickerTestament = testament;
  $$('.picker-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.testament === testament));

  const grid = $('#picker-book-grid');
  if (!grid) return;
  grid.innerHTML = '';
  const books = testament === 'OT' ? OT_BOOKS : NT_BOOKS;
  for (const book of books) {
    const abbr = _BOOK_ABBR[book.name] || book.name.slice(0,3).toUpperCase();
    const btn = el('button', {
      class: 'picker-book-btn' + (book.name === state.currentBook ? ' active' : ''),
      title: book.name,
      onclick: () => _selectPickerBook(book),
    }, abbr);
    grid.appendChild(btn);
  }

  const bv = $('#picker-book-view');
  const cv = $('#picker-chapter-view');
  if (bv) bv.classList.remove('hidden');
  if (cv) cv.classList.add('hidden');
}

function _selectPickerBook(book) {
  const label = $('#picker-selected-book');
  if (label) label.textContent = book.name;

  const grid = $('#picker-chapter-grid');
  if (!grid) return;
  grid.innerHTML = '';
  for (let c = 1; c <= book.chapters; c++) {
    const ch = c;
    const btn = el('button', {
      class: 'picker-chapter-btn' + (book.name === state.currentBook && ch === state.currentChapter ? ' active' : ''),
      onclick: () => { closeNavPicker(); loadChapter(book.name, ch); },
    }, String(ch));
    grid.appendChild(btn);
  }

  const bv = $('#picker-book-view');
  const cv = $('#picker-chapter-view');
  if (bv) bv.classList.add('hidden');
  if (cv) cv.classList.remove('hidden');
}

function updateRefDisplay() {
  const el2 = $('#ref-display');
  if (el2) el2.textContent = `${state.currentBook} ${state.currentChapter}`;
  const bookDisplay = $('#chapter-book-display');
  const numDisplay  = $('#chapter-num-display');
  if (bookDisplay) bookDisplay.textContent = state.currentBook;
  if (numDisplay)  numDisplay.textContent  = `Chapter ${state.currentChapter}`;
}

function openTransPicker() {
  const list = $('#trans-picker-list');
  if (list) {
    list.innerHTML = '';
    const translations = state.cachedTranslations || ['KJV','ESV','NIV','NASB','NKJV','NLT','AMP','CSB','MSG','RSV'];
    for (const t of translations) {
      const abbr = t.abbreviation || t;
      const name = t.full_name || t.name || abbr;
      const item = el('button', {
        class: 'trans-picker-item' + (abbr === state.currentTranslation ? ' active' : ''),
        onclick: () => {
          state.currentTranslation = abbr;
          const td = $('#trans-display');
          if (td) td.textContent = abbr;
          loadChapter(state.currentBook, state.currentChapter, state.currentVerse);
          closeTransPicker();
        },
      });
      item.appendChild(el('span', {class:'trans-abbr'}, abbr));
      if (name !== abbr) item.appendChild(el('span', {class:'trans-name'}, name));
      list.appendChild(item);
    }
  }
  const picker = $('#trans-picker');
  if (picker) { picker.classList.add('open'); picker.setAttribute('aria-hidden','false'); }
}

function closeTransPicker() {
  const picker = $('#trans-picker');
  if (picker) { picker.classList.remove('open'); picker.setAttribute('aria-hidden','true'); }
}

let _menuOpen = false;
function toggleMenuDrawer() {
  _menuOpen = !_menuOpen;
  const drawer = $('#menu-drawer');
  if (drawer) {
    drawer.classList.toggle('open', _menuOpen);
    drawer.setAttribute('aria-hidden', _menuOpen ? 'false' : 'true');
  }
  const btn = $('#btn-menu');
  if (btn) btn.setAttribute('aria-expanded', _menuOpen ? 'true' : 'false');
}

function closeMenuDrawer() {
  _menuOpen = false;
  const drawer = $('#menu-drawer');
  if (drawer) { drawer.classList.remove('open'); drawer.setAttribute('aria-hidden','true'); }
}

// ── 12. INIT ───────────────────────────────────────────────────────────────

function init() {
  buildBookNav();
  loadTranslations();

  // Restore from URL hash, then localStorage, then default
  const restored = restoreFromHash();
  if (!restored) {
    const last = loadLastPosition();
    loadChapter(last.book, last.chapter);
  }

  // Reference pill → nav picker
  const refPill = $('#btn-ref-pill');
  if (refPill) refPill.addEventListener('click', openNavPicker);

  // Nav picker close / backdrop
  const navPickerClose = $('#btn-nav-picker-close');
  if (navPickerClose) navPickerClose.addEventListener('click', closeNavPicker);
  const navPickerBackdrop = $('#nav-picker-backdrop');
  if (navPickerBackdrop) navPickerBackdrop.addEventListener('click', closeNavPicker);

  // Nav picker testament tabs
  $$('.picker-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => _buildPickerBookGrid(btn.dataset.testament));
  });

  // Nav picker back button (chapter view → book view)
  const pickerBack = $('#btn-picker-back');
  if (pickerBack) pickerBack.addEventListener('click', () => _buildPickerBookGrid(_pickerTestament));

  // Translation pill → trans picker
  const transPill = $('#btn-trans-pill');
  if (transPill) transPill.addEventListener('click', openTransPicker);
  const transPickerClose = $('#btn-trans-picker-close');
  if (transPickerClose) transPickerClose.addEventListener('click', closeTransPicker);
  const transPickerBackdrop = $('#trans-picker-backdrop');
  if (transPickerBackdrop) transPickerBackdrop.addEventListener('click', closeTransPicker);

  // Menu drawer
  const menuBtn = $('#btn-menu');
  if (menuBtn) menuBtn.addEventListener('click', toggleMenuDrawer);
  const menuSessions = $('#menu-item-sessions');
  if (menuSessions) menuSessions.addEventListener('click', () => { closeMenuDrawer(); openSessionsPanel(); });
  const menuBookmarks = $('#menu-item-bookmarks');
  if (menuBookmarks) menuBookmarks.addEventListener('click', () => { closeMenuDrawer(); openBookmarksPanel(); });
  const menuHistory = $('#menu-item-history');
  if (menuHistory) menuHistory.addEventListener('click', () => { closeMenuDrawer(); openHistoryPanel(); });
  const menuAdmin = $('#menu-item-admin');
  if (menuAdmin) menuAdmin.addEventListener('click', () => { closeMenuDrawer(); showAdminPanel(); });

  // Show admin menu item if admin
  if (isAdmin()) {
    if (menuAdmin) menuAdmin.style.display = '';
    const oldAdminItem = $('#manage-users-item');
    if (oldAdminItem) oldAdminItem.style.display = '';
  }

  // Prev / Next chapter buttons
  const prevBtn = $('#btn-prev-chapter');
  const nextBtn = $('#btn-next-chapter');
  if (prevBtn) prevBtn.addEventListener('click', prevChapter);
  if (nextBtn) nextBtn.addEventListener('click', nextChapter);

  // Mobile bottom bar
  const mobPrev = $('#btn-mob-prev');
  const mobNext = $('#btn-mob-next');
  const mobStudy = $('#btn-mob-study');
  if (mobPrev) mobPrev.addEventListener('click', prevChapter);
  if (mobNext) mobNext.addEventListener('click', nextChapter);
  if (mobStudy) mobStudy.addEventListener('click', openBottomSheet);

  // Search button
  const searchOpenBtn = $('#btn-search-open');
  if (searchOpenBtn) searchOpenBtn.addEventListener('click', showSearchOverlay);

  // Parallel toggle
  const parallelBtn = $('#btn-parallel-new');
  if (parallelBtn) parallelBtn.addEventListener('click', () => {
    toggleParallelMode();
    parallelBtn.classList.toggle('active', state.parallelMode);
  });

  // Drag-to-expand study panel on mobile
  const dragHandle = $('#sheet-drag-handle');
  if (dragHandle) {
    let _startY = 0;
    dragHandle.addEventListener('touchstart', e => {
      _startY = e.touches[0].clientY;
    }, { passive: true });
    dragHandle.addEventListener('touchend', e => {
      const dy = e.changedTouches[0].clientY - _startY;
      const panel = $('#study-panel');
      if (!panel) return;
      if (dy > 60) {
        // Swipe down — collapse
        closeBottomSheet();
      } else if (dy < -60) {
        // Swipe up — expand
        panel.classList.add('panel-expanded');
      }
    }, { passive: true });
  }

  // Tap outside study panel to close (mobile)
  document.addEventListener('click', e => {
    if (!state.isDesktop() && state.bottomSheetOpen) {
      const panel = $('#study-panel');
      if (panel && !panel.contains(e.target) && e.target !== $('#btn-mob-study')) {
        closeBottomSheet();
      }
    }
    // Close menu drawer if clicking outside
    if (_menuOpen) {
      const drawer = $('#menu-drawer');
      const menuBtnEl = $('#btn-menu');
      if (drawer && menuBtnEl && !drawer.contains(e.target) && !menuBtnEl.contains(e.target)) {
        closeMenuDrawer();
      }
    }
  });

  // Tab buttons (using event delegation on study panel)
  const studyPanel = $('#study-panel');
  if (studyPanel) {
    studyPanel.addEventListener('click', e => {
      const btn = e.target.closest('.tab-btn');
      if (btn && btn.dataset.tab) switchTab(btn.dataset.tab);
    });
  }

  // Keyboard nav
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
    if (e.key === 'ArrowLeft'  && !e.altKey) prevChapter();
    if (e.key === 'ArrowRight' && !e.altKey) nextChapter();
    if (e.key === 'Escape') {
      closeSearchOverlay();
      closeBottomSheet();
      closeNavPicker();
      closeTransPicker();
      closeMenuDrawer();
    }
  });

  // Legacy translation selector (still in DOM as hidden fallback)
  const transSelect = $('#translation-select');
  if (transSelect) {
    transSelect.value = state.currentTranslation;
    transSelect.addEventListener('change', e => {
      state.currentTranslation = e.target.value;
      const td = $('#trans-display');
      if (td) td.textContent = e.target.value;
      loadChapter(state.currentBook, state.currentChapter, state.currentVerse);
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
  window.addEventListener('resize', () => {
    handleResize();
    if (state.isDesktop()) {
      closeNavPicker();
      closeTransPicker();
    }
  });

  // Persist position before unload
  window.addEventListener('beforeunload', saveLastPosition);

  // Initialize trans display
  const td = $('#trans-display');
  if (td) td.textContent = state.currentTranslation;

  // Activate first tab
  switchTab(state.activeTab);

  // Tab bar scroll-fade: hide the right gradient once scrolled to end
  const tabBar = document.querySelector('.panel-tab-bar');
  const tabWrap = document.querySelector('.panel-tab-bar-wrap');
  if (tabBar && tabWrap) {
    const updateFade = () => {
      const atEnd = tabBar.scrollLeft + tabBar.clientWidth >= tabBar.scrollWidth - 4;
      tabWrap.classList.toggle('scrolled-end', atEnd);
    };
    tabBar.addEventListener('scroll', updateFade, { passive: true });
    updateFade();
  }

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

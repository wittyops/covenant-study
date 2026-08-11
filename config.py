"""
Covenant Study — static configuration and canonical data tables.

Everything here is read-only at runtime. Nothing is fetched from the
database or environment; this module is safe to import anywhere.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# RUNTIME PATHS
# ---------------------------------------------------------------------------

# Bible text SQLite databases — baked into the image at build time.
# Never volume-mounted; always present once the Dockerfile build_data.py runs.
DATA = Path("/app/data")

# User accounts, sessions, bookmarks, notes, highlights, reading progress.
# Mounted as a named Docker volume so data survives container rebuilds.
USERDATA = Path("/app/userdata")

# Legacy file-based notes directory; only touched at startup for one-time migration.
NOTES = Path("/app/notes")

# ---------------------------------------------------------------------------
# CANONICAL BOOK TABLE
# ---------------------------------------------------------------------------

BOOKS: dict[int, str] = {
    1: "Genesis",      2: "Exodus",         3: "Leviticus",      4: "Numbers",
    5: "Deuteronomy",  6: "Joshua",         7: "Judges",         8: "Ruth",
    9: "1 Samuel",    10: "2 Samuel",       11: "1 Kings",       12: "2 Kings",
    13: "1 Chronicles", 14: "2 Chronicles", 15: "Ezra",          16: "Nehemiah",
    17: "Esther",     18: "Job",            19: "Psalms",        20: "Proverbs",
    21: "Ecclesiastes", 22: "Song of Solomon", 23: "Isaiah",     24: "Jeremiah",
    25: "Lamentations", 26: "Ezekiel",      27: "Daniel",        28: "Hosea",
    29: "Joel",       30: "Amos",           31: "Obadiah",       32: "Jonah",
    33: "Micah",      34: "Nahum",          35: "Habakkuk",      36: "Zephaniah",
    37: "Haggai",     38: "Zechariah",      39: "Malachi",
    40: "Matthew",    41: "Mark",           42: "Luke",          43: "John",
    44: "Acts",       45: "Romans",         46: "1 Corinthians", 47: "2 Corinthians",
    48: "Galatians",  49: "Ephesians",      50: "Philippians",   51: "Colossians",
    52: "1 Thessalonians", 53: "2 Thessalonians", 54: "1 Timothy", 55: "2 Timothy",
    56: "Titus",      57: "Philemon",       58: "Hebrews",       59: "James",
    60: "1 Peter",    61: "2 Peter",        62: "1 John",        63: "2 John",
    64: "3 John",     65: "Jude",           66: "Revelation",
}

# Abbreviation → book number mapping used by parse_reference().
# Longer/exact matches must win over prefix matches, so keep both full
# lowercase names and common short forms.
BOOK_ABBR: dict[str, int] = {v.lower(): k for k, v in BOOKS.items()}
BOOK_ABBR.update({
    "gen": 1,  "ex": 2,    "lev": 3,   "num": 4,   "deut": 5,
    "josh": 6, "judg": 7,
    "1sa": 9,  "2sa": 10,  "1ki": 11,  "2ki": 12,
    "1ch": 13, "2ch": 14,
    "ps": 19,  "psa": 19,  "prov": 20, "eccl": 21, "eccles": 21,
    "song": 22, "sos": 22,
    "isa": 23, "jer": 24,  "lam": 25,  "ezek": 26, "dan": 27,
    "hos": 28,
    "zech": 38, "mal": 39,
    "matt": 40, "mk": 41,  "lk": 42,   "jn": 43,
    "rom": 45,  "1cor": 46, "2cor": 47, "gal": 48,  "eph": 49,
    "phil": 50, "col": 51,  "1th": 52,  "2th": 53,
    "1ti": 54,  "2ti": 55,  "tit": 56,  "phm": 57,
    "heb": 58,  "jas": 59,  "1pe": 60,  "2pe": 61,
    "rev": 66,
})

# ---------------------------------------------------------------------------
# AVAILABLE TRANSLATIONS
# ---------------------------------------------------------------------------

# Public-domain English, scholarly originals, and other languages available
# in the bible_multi.db built at image time. The /api/translations endpoint
# queries the live database for what's actually present; this list is a
# reference for UI defaults and validation.
TRANSLATIONS: list[str] = [
    # English public-domain
    "KJV", "KJVA", "KJVPCE", "AKJV", "ASV", "YLT", "Darby", "Geneva1599",
    "Webster", "BBE", "BSB", "Jubilee2000", "ACV", "DRC", "CPDV",
    "Tyndale", "Wycliffe", "OEB", "LITV", "MKJV", "RNKJV", "UKJV",
    "RWebster", "Rotherham", "NHEB", "LEB", "Anderson", "Noyes", "Haweis", "Twenty",
    # Scholarly originals
    "JPS", "HebModern", "Vulgate", "VulgClementine", "Peshitta", "TR", "Byz",
    # Septuagint (LXX) — Greek OT used by the New Testament writers
    "Brenton",       # Brenton English Septuagint (1844) — public domain
    "FreLXXGiguet",  # Giguet French Septuagint (1872) — public domain
    # Other languages
    "FreSynodale", "FreGeneve",
]

# ---------------------------------------------------------------------------
# BIBLICAL PLACES — coordinates + notes for the map tab
# ---------------------------------------------------------------------------

# Keys are canonical place names that the /api/places endpoint scans for in
# passage text using a word-boundary regex. Lat/lon are WGS84 decimal degrees.
PLACES: dict[str, dict] = {
    # === HOLY LAND — CITIES & TOWNS ===
    "Jerusalem":          {"lat": 31.7767, "lon": 35.2345, "notes": "City of David; site of the Temple; crucifixion and resurrection of Christ"},
    "Bethlehem":          {"lat": 31.7054, "lon": 35.2024, "notes": "Birthplace of David and Jesus; Rachel's tomb nearby"},
    "Nazareth":           {"lat": 32.7021, "lon": 35.2975, "notes": "Hometown of Jesus; where He was raised"},
    "Capernaum":          {"lat": 32.8812, "lon": 35.5747, "notes": "Jesus' ministry headquarters on the Sea of Galilee"},
    "Jericho":            {"lat": 31.8661, "lon": 35.4436, "notes": "First city conquered by Israel; walls fell at God's command"},
    "Hebron":             {"lat": 31.5326, "lon": 35.0998, "notes": "Abraham, Isaac, Jacob and their wives buried here (Cave of Machpelah)"},
    "Beersheba":          {"lat": 31.2530, "lon": 34.7915, "notes": "Southern boundary of Israel; 'from Dan to Beersheba'"},
    "Dan":                {"lat": 33.2485, "lon": 35.6518, "notes": "Northern boundary of Israel; site of golden calf idolatry (Jeroboam)"},
    "Bethel":             {"lat": 31.9290, "lon": 35.2197, "notes": "Jacob's ladder; 'house of God'; Ark housed here after conquest"},
    "Shechem":            {"lat": 32.2087, "lon": 35.2856, "notes": "Where Abraham built first altar in Canaan; Joseph buried here"},
    "Sychar":             {"lat": 32.2118, "lon": 35.2871, "notes": "Samaritan city; Jesus speaks with the woman at Jacob's Well"},
    "Samaria":            {"lat": 32.2748, "lon": 35.1980, "notes": "Capital of northern kingdom of Israel; city of Omri"},
    "Shiloh":             {"lat": 32.0567, "lon": 35.2919, "notes": "Home of the Tabernacle for 300+ years; where Hannah prayed"},
    "Gilgal":             {"lat": 31.8681, "lon": 35.4561, "notes": "First campsite in Canaan; Israel circumcised; Saul anointed king"},
    "Gibeon":             {"lat": 31.8391, "lon": 35.1771, "notes": "Sun stood still; Tabernacle housed here in Solomon's early reign"},
    "Mizpah":             {"lat": 31.8737, "lon": 35.2153, "notes": "Samuel judged Israel; Saul chosen as first king by lot"},
    "Ramah":              {"lat": 31.9197, "lon": 35.2203, "notes": "Birthplace of Samuel; Rachel weeping for her children"},
    "Gibeah":             {"lat": 31.8462, "lon": 35.2214, "notes": "Capital of Saul; scene of the Levite's concubine outrage"},
    "Peniel":             {"lat": 32.1896, "lon": 35.6082, "notes": "Where Jacob wrestled with God and received the name Israel"},
    "Dothan":             {"lat": 32.3983, "lon": 35.2025, "notes": "Joseph thrown into pit by brothers; Elisha surrounded by angels here"},
    "Endor":              {"lat": 32.6383, "lon": 35.3911, "notes": "Saul consulted the witch (medium) of Endor"},
    "Jezreel":            {"lat": 32.5468, "lon": 35.3281, "notes": "Ahab's palace; Naboth's vineyard; Jezebel killed here"},
    "Megiddo":            {"lat": 32.5837, "lon": 35.1842, "notes": "Strategic pass; site of many battles; Armageddon (Har Megiddo)"},
    "Hazor":              {"lat": 33.0181, "lon": 35.5687, "notes": "Greatest Canaanite city; defeated by Joshua; rebuilt by Solomon"},
    "Lachish":            {"lat": 31.5607, "lon": 34.8489, "notes": "Second-largest Judean city; besieged by Sennacherib and Nebuchadnezzar"},
    "Joppa":              {"lat": 32.0519, "lon": 34.7507, "notes": "Jonah sailed from here; Peter raised Dorcas; received vision about Gentiles"},
    "Lydda":              {"lat": 31.9530, "lon": 34.8950, "notes": "Peter healed Aeneas here; called Lod in OT"},
    "Caesarea":           {"lat": 32.5002, "lon": 34.8891, "notes": "Roman capital of Judea; Cornelius' household; Paul imprisoned here"},
    "Caesarea Philippi":  {"lat": 33.2484, "lon": 35.6941, "notes": "Peter's confession: 'Thou art the Christ'"},
    "Bethsaida":          {"lat": 32.9069, "lon": 35.6372, "notes": "Hometown of Peter, Andrew, and Philip; Jesus healed a blind man"},
    "Chorazin":           {"lat": 32.9183, "lon": 35.5583, "notes": "Condemned by Jesus for rejecting His miracles"},
    "Magdala":            {"lat": 32.8336, "lon": 35.5100, "notes": "Hometown of Mary Magdalene"},
    "Cana":               {"lat": 32.7467, "lon": 35.3403, "notes": "Jesus' first miracle: water to wine at a wedding"},
    "Nain":               {"lat": 32.6408, "lon": 35.3533, "notes": "Jesus raised the widow's son from the dead"},
    "Emmaus":             {"lat": 31.8406, "lon": 35.0616, "notes": "Jesus appeared to two disciples on the road after resurrection"},
    "Bethany":            {"lat": 31.7742, "lon": 35.2633, "notes": "Home of Lazarus, Mary, and Martha; Jesus raised Lazarus here"},
    "Bethphage":          {"lat": 31.7804, "lon": 35.2530, "notes": "Jesus sent for the colt here before His triumphal entry"},
    "Gethsemane":         {"lat": 31.7794, "lon": 35.2420, "notes": "Garden where Jesus prayed and was arrested the night before crucifixion"},
    "Golgotha":           {"lat": 31.7784, "lon": 35.2298, "notes": "Place of the skull; site of the crucifixion"},
    "Antioch":            {"lat": 36.2021, "lon": 36.1607, "notes": "Disciples first called Christians here; Paul's missionary base"},
    "Gaza":               {"lat": 31.5017, "lon": 34.4673, "notes": "Philistine city; Samson's captivity and death; Philip met the Ethiopian eunuch nearby"},
    "Ashkelon":           {"lat": 31.6688, "lon": 34.5742, "notes": "Major Philistine city on the coast"},
    "Ashdod":             {"lat": 31.8000, "lon": 34.6500, "notes": "Philistine city; Ark of the Covenant captured and placed in Dagon's temple"},
    "Ekron":              {"lat": 31.7784, "lon": 34.8357, "notes": "Philistine city; where the Ark was returned to Israel"},
    "En Gedi":            {"lat": 31.4611, "lon": 35.3889, "notes": "Wilderness oasis; David hid from Saul in caves here"},
    "Arad":               {"lat": 31.2761, "lon": 35.1252, "notes": "Canaanite city defeated by Israel"},
    # === WATER BODIES ===
    "Sea of Galilee":     {"lat": 32.8208, "lon": 35.5842, "notes": "Also called Lake of Gennesaret; site of much of Jesus' ministry; storms calmed"},
    "Jordan":             {"lat": 32.0000, "lon": 35.5500, "notes": "Israel crossed into the promised land; Jesus baptized by John"},
    "Dead Sea":           {"lat": 31.5590, "lon": 35.4732, "notes": "Saltiest lake on earth; cities of Sodom and Gomorrah were near here"},
    "Galilee":            {"lat": 32.8000, "lon": 35.5000, "notes": "Northern region of Israel; Jesus' primary ministry area"},
    "Judea":              {"lat": 31.5000, "lon": 35.0000, "notes": "Southern region; tribe of Judah; home of Jerusalem"},
    "Decapolis":          {"lat": 32.6000, "lon": 35.9000, "notes": "League of ten Gentile cities east of Jordan; Jesus ministered here"},
    "Perea":              {"lat": 31.8000, "lon": 35.7000, "notes": "Region east of Jordan; 'beyond Jordan' in Scripture"},
    # === MOUNTAINS ===
    "Sinai":              {"lat": 28.5402, "lon": 33.9750, "notes": "Mountain of God; Moses received the Ten Commandments; Elijah fled here"},
    "Horeb":              {"lat": 28.5402, "lon": 33.9750, "notes": "Another name for Sinai; burning bush; Elijah's still small voice"},
    "Zion":               {"lat": 31.7717, "lon": 35.2292, "notes": "Hill of Jerusalem; City of David; the LORD's holy mountain"},
    "Carmel":             {"lat": 32.7345, "lon": 34.9684, "notes": "Elijah's contest with 450 prophets of Baal; fire from heaven"},
    "Hermon":             {"lat": 33.4148, "lon": 35.8569, "notes": "Highest peak in region; traditionally the Transfiguration site"},
    "Tabor":              {"lat": 32.6870, "lon": 35.3931, "notes": "Traditional Transfiguration site; Barak gathered troops here"},
    "Nebo":               {"lat": 31.7691, "lon": 35.7298, "notes": "Moses viewed the promised land from here; Moses died here"},
    "Ebal":               {"lat": 32.2133, "lon": 35.2869, "notes": "Mountain of curses (Deut 27); Joshua built an altar here"},
    "Gerizim":            {"lat": 32.1991, "lon": 35.2728, "notes": "Mountain of blessings; Samaritan temple site; woman at the well"},
    "Moriah":             {"lat": 31.7782, "lon": 35.2357, "notes": "Abraham offered Isaac here; Solomon built the Temple here"},
    "Gilboa":             {"lat": 32.5142, "lon": 35.4049, "notes": "Where Saul and Jonathan fell in battle against the Philistines"},
    # === REGIONS AROUND ISRAEL ===
    "Egypt":              {"lat": 26.8206, "lon": 30.8025, "notes": "House of slavery; Joseph's rise; Exodus; flight of Jesus as infant"},
    "Goshen":             {"lat": 30.7067, "lon": 31.9227, "notes": "Land in Egypt given to Jacob's family; protected from the plagues; Israel dwelt here"},
    "Memphis":            {"lat": 29.8499, "lon": 31.2513, "notes": "Ancient Egyptian capital; called Noph in Scripture"},
    "Alexandria":         {"lat": 31.2001, "lon": 29.9187, "notes": "Great Egyptian city; Apollos was from here (Acts 18:24)"},
    "Edom":               {"lat": 30.5000, "lon": 35.5000, "notes": "Land of Esau; perpetual enemy of Israel; Petra (Sela) its capital"},
    "Petra":              {"lat": 30.3285, "lon": 35.4444, "notes": "Rock city; capital of Edom/Nabataeans; called Sela in Scripture"},
    "Moab":               {"lat": 31.2000, "lon": 35.8000, "notes": "East of Dead Sea; Ruth's homeland; Israel camped here before conquest"},
    "Ammon":              {"lat": 31.9500, "lon": 35.9333, "notes": "East of Jordan; enemy of Israel; modern Amman"},
    "Midian":             {"lat": 28.0000, "lon": 36.0000, "notes": "Moses fled here; married Zipporah; burning bush; Jethro's land"},
    "Bashan":             {"lat": 32.9000, "lon": 36.0000, "notes": "Rich pastureland; giant Og's kingdom defeated by Israel"},
    "Gilead":             {"lat": 32.1000, "lon": 35.9000, "notes": "East of Jordan; balm of Gilead; Jephthah's home; Elijah's birthplace"},
    "Philistia":          {"lat": 31.7000, "lon": 34.6000, "notes": "Coastal plain; people of the sea; enemies of Israel for generations"},
    "Phoenicia":          {"lat": 33.5000, "lon": 35.4000, "notes": "Lebanon coast; Tyre and Sidon; great seafarers and traders"},
    "Tyre":               {"lat": 33.2705, "lon": 35.1954, "notes": "Great Phoenician port city; Hiram helped Solomon build the Temple"},
    "Sidon":              {"lat": 33.5607, "lon": 35.3706, "notes": "Phoenician city north of Tyre; Jesus ministered here briefly"},
    # === MESOPOTAMIA ===
    "Ur":                 {"lat": 30.9625, "lon": 46.1031, "notes": "Abraham's birthplace; 'Ur of the Chaldees'; left by faith"},
    "Haran":              {"lat": 36.8613, "lon": 39.0241, "notes": "Abraham's family settled here; Jacob fled here to Laban"},
    "Babylon":            {"lat": 32.5427, "lon": 44.4212, "notes": "Nebuchadnezzar's empire; Israel exiled here; symbol of worldly power in Revelation"},
    "Nineveh":            {"lat": 36.3583, "lon": 43.1425, "notes": "Assyrian capital; Jonah sent here; repented at preaching of Jonah"},
    "Assyria":            {"lat": 36.0000, "lon": 43.0000, "notes": "Conquered northern Israel (722 BC); carried ten tribes into exile"},
    "Susa":               {"lat": 32.1897, "lon": 48.2566, "notes": "Persian capital; Esther and Mordecai; Daniel's vision of the ram"},
    "Persepolis":         {"lat": 29.9353, "lon": 52.8909, "notes": "Ceremonial capital of Persian Empire; Cyrus issued decree for Israelites to return"},
    "Carchemish":         {"lat": 36.8308, "lon": 38.0111, "notes": "Battle where Nebuchadnezzar defeated Egypt (605 BC); Babylon rises to power"},
    # === NEW TESTAMENT — PAUL'S JOURNEYS ===
    "Damascus":           {"lat": 33.5102, "lon": 36.2913, "notes": "Paul's conversion on the road here; blinded by light; Ananias restored his sight"},
    "Tarsus":             {"lat": 36.9145, "lon": 34.8952, "notes": "Paul's birthplace; 'no mean city'"},
    "Cyprus":             {"lat": 35.1264, "lon": 33.4299, "notes": "Barnabas' homeland; first stop on Paul's first journey; Sergius Paulus converted"},
    "Paphos":             {"lat": 34.7751, "lon": 32.4228, "notes": "Capital of Cyprus; Paul blinded Elymas the sorcerer here"},
    "Perga":              {"lat": 36.9611, "lon": 30.8570, "notes": "Coastal city; John Mark left Paul here on first journey"},
    "Iconium":            {"lat": 37.8722, "lon": 32.4844, "notes": "Paul and Barnabas preached and were driven out; Lystra/Derbe nearby"},
    "Lystra":             {"lat": 37.5836, "lon": 32.5233, "notes": "Paul stoned and left for dead; Timothy was from here"},
    "Derbe":              {"lat": 37.3580, "lon": 33.3430, "notes": "Paul's furthest point on first journey; many disciples made"},
    "Troas":              {"lat": 39.7532, "lon": 26.1606, "notes": "Paul's Macedonian vision; Eutychus fell from window and was raised"},
    "Philippi":           {"lat": 41.0069, "lon": 24.2822, "notes": "First European church; Lydia converted; Paul and Silas jailed, earthquake"},
    "Thessalonica":       {"lat": 40.6401, "lon": 22.9444, "notes": "Paul preached three Sabbaths; Jason's house attacked; church commended for faith"},
    "Berea":              {"lat": 40.4686, "lon": 22.2007, "notes": "Bereans 'more noble' — searched Scriptures daily to verify Paul's teaching"},
    "Athens":             {"lat": 37.9792, "lon": 23.7166, "notes": "Mars Hill (Areopagus); Paul's sermon on the Unknown God; Dionysius converted"},
    "Corinth":            {"lat": 37.9055, "lon": 22.8786, "notes": "Paul's 18-month ministry; Priscilla and Aquila; letters to Corinthians"},
    "Ephesus":            {"lat": 37.9413, "lon": 27.3426, "notes": "Temple of Artemis; Paul's 3-year ministry; riot of silversmiths; Timothy pastored here"},
    "Colossae":           {"lat": 37.7756, "lon": 29.2975, "notes": "Church addressed in Colossians; Philemon's church; Epaphras founded it"},
    "Laodicea":           {"lat": 37.8383, "lon": 29.1072, "notes": "Lukewarm church; 'neither hot nor cold'; Rev 3:15-16"},
    "Hierapolis":         {"lat": 37.9239, "lon": 29.1251, "notes": "Near Colossae; Phillip the Evangelist buried here (tradition)"},
    "Pergamum":           {"lat": 39.1293, "lon": 27.1837, "notes": "One of 7 churches; 'Satan's throne'; Balaam and Jezebel errors"},
    "Smyrna":             {"lat": 38.4192, "lon": 27.1287, "notes": "One of 7 churches; praised for suffering; 'be faithful unto death'"},
    "Thyatira":           {"lat": 38.9218, "lon": 27.8447, "notes": "Lydia's hometown; one of 7 churches; Jezebel false prophetess"},
    "Sardis":             {"lat": 38.4882, "lon": 28.0438, "notes": "One of 7 churches; 'a name that you are alive, but you are dead'"},
    "Philadelphia":       {"lat": 38.3534, "lon": 28.5154, "notes": "One of 7 churches; 'I have set before you an open door'"},
    "Patmos":             {"lat": 37.3210, "lon": 26.5428, "notes": "Island where John received the Revelation in exile"},
    "Malta":              {"lat": 35.9375, "lon": 14.3754, "notes": "Paul shipwrecked here; bitten by viper with no harm; healed many"},
    "Crete":              {"lat": 35.2401, "lon": 24.8093, "notes": "Titus left here to set church in order; Cretans at Pentecost"},
    "Rome":               {"lat": 41.9028, "lon": 12.4964, "notes": "Capital of the empire; Paul's letter to the Romans; Paul martyred here (tradition)"},
    "Macedonia":          {"lat": 41.0000, "lon": 22.0000, "notes": "Northern Greece; Paul's vision 'Come over to Macedonia and help us'"},
    "Greece":             {"lat": 38.0000, "lon": 23.5000, "notes": "Paul's journey through; Achaia in NT; Athens and Corinth"},
    "Arabia":             {"lat": 27.0000, "lon": 37.0000, "notes": "Paul went here after conversion (Galatians 1:17); 3 years before Jerusalem"},
    "Galatia":            {"lat": 39.0000, "lon": 33.0000, "notes": "Roman province; Paul's first journey churches; letter to the Galatians"},
    "Cappadocia":         {"lat": 38.5000, "lon": 35.5000, "notes": "Roman province; mentioned in 1 Peter 1:1; Pentecost crowd (Acts 2:9)"},
    "Pontus":             {"lat": 41.0000, "lon": 36.5000, "notes": "Aquila's birthplace; mentioned in 1 Peter 1:1"},
    "Bithynia":           {"lat": 40.5000, "lon": 30.0000, "notes": "Paul prevented by Holy Spirit from going here (Acts 16:7)"},
    "Asia":               {"lat": 38.5000, "lon": 27.5000, "notes": "Roman province (western Turkey); the 7 churches are here"},
    # === SINAI / WILDERNESS ===
    "Wilderness":         {"lat": 30.5000, "lon": 34.0000, "notes": "Israel wandered 40 years; tested and formed as God's people"},
    "Kadesh":             {"lat": 30.6417, "lon": 34.4067, "notes": "Israel's main camp in the Sinai wilderness; Miriam died here"},
    "Paran":              {"lat": 29.5000, "lon": 33.5000, "notes": "Wilderness region; Ishmael lived here; Israel camped here"},
    "Rephidim":           {"lat": 28.6000, "lon": 33.7000, "notes": "Water from the rock; Amalekites defeated while Moses held up his staff"},
    "Marah":              {"lat": 29.5000, "lon": 33.0000, "notes": "Bitter water made sweet; Israel murmured against Moses here"},
}

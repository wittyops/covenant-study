"""
build_data.py — wn-bible-01 Bible study app
Runs once at Docker image build time (RUN python /app/build_data.py).
Working directory: /app   Data directory: /app/data/

Steps:
  1. word_strongs  — parse KJV-osis.json → word_strongs table in kjv.db
  2. cross_refs    — merge 7 shard DBs → cross_refs table in cross_references.db
  3. strongs       — parse strongs_hebrew.xml + strongs_greek.xml → strongs.db
  4. interlinear   — parse STEPBible TAHOT/TAGNT TSV files → interlinear.db
  5. commentary    — fetch Matthew Henry via HelloAO API → commentary.db

Each step is idempotent: checks row count before processing.
Errors are caught per-step; build exits 0 regardless.
"""

import json
import re
import sqlite3
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA = Path("/app/data")

BOOKS = {
    1: "Genesis", 2: "Exodus", 3: "Leviticus", 4: "Numbers", 5: "Deuteronomy",
    6: "Joshua", 7: "Judges", 8: "Ruth", 9: "1 Samuel", 10: "2 Samuel",
    11: "1 Kings", 12: "2 Kings", 13: "1 Chronicles", 14: "2 Chronicles",
    15: "Ezra", 16: "Nehemiah", 17: "Esther", 18: "Job", 19: "Psalms",
    20: "Proverbs", 21: "Ecclesiastes", 22: "Song of Solomon", 23: "Isaiah",
    24: "Jeremiah", 25: "Lamentations", 26: "Ezekiel", 27: "Daniel",
    28: "Hosea", 29: "Joel", 30: "Amos", 31: "Obadiah", 32: "Jonah",
    33: "Micah", 34: "Nahum", 35: "Habakkuk", 36: "Zephaniah", 37: "Haggai",
    38: "Zechariah", 39: "Malachi",
    40: "Matthew", 41: "Mark", 42: "Luke", 43: "John", 44: "Acts",
    45: "Romans", 46: "1 Corinthians", 47: "2 Corinthians", 48: "Galatians",
    49: "Ephesians", 50: "Philippians", 51: "Colossians",
    52: "1 Thessalonians", 53: "2 Thessalonians", 54: "1 Timothy",
    55: "2 Timothy", 56: "Titus", 57: "Philemon", 58: "Hebrews",
    59: "James", 60: "1 Peter", 61: "2 Peter", 62: "1 John",
    63: "2 John", 64: "3 John", 65: "Jude", 66: "Revelation",
}

# Canonical lowercase → book ID
BOOK_NAME_TO_ID: dict[str, int] = {v.lower(): k for k, v in BOOKS.items()}

# OSIS / STEPBible abbreviation aliases
_OSIS_ALIASES: dict[str, int] = {
    # OT
    "gen": 1, "exo": 2, "exod": 2, "lev": 3, "num": 4, "deu": 5, "deut": 5,
    "jos": 6, "josh": 6, "jdg": 7, "judg": 7, "jug": 7,
    "rut": 8, "ruth": 8,
    "1sa": 9, "1sam": 9, "2sa": 10, "2sam": 10,
    "1ki": 11, "1kgs": 11, "2ki": 12, "2kgs": 12,
    "1ch": 13, "1chr": 13, "2ch": 14, "2chr": 14,
    "ezr": 15, "ezra": 15, "neh": 16,
    "est": 17, "esth": 17,
    "job": 18,
    "psa": 19, "ps": 19, "pss": 19,
    "pro": 20, "prov": 20,
    "ecc": 21, "eccl": 21,
    "sng": 22, "song": 22, "sol": 22,
    "isa": 23, "jer": 24, "lam": 25,
    "ezk": 26, "ezek": 26,
    "dan": 27, "hos": 28,
    "joe": 29, "joel": 29,
    "amo": 30, "amos": 30,
    "oba": 31, "obad": 31,
    "jon": 32, "jonah": 32,
    "mic": 33, "nah": 34, "hab": 35,
    "zep": 36, "zeph": 36,
    "hag": 37,
    "zec": 38, "zech": 38,
    "mal": 39,
    # NT
    "mat": 40, "matt": 40,
    "mrk": 41, "mar": 41, "mark": 41,
    "luk": 42, "luke": 42,
    "jhn": 43, "john": 43,
    "act": 44, "acts": 44,
    "rom": 45,
    "1co": 46, "1cor": 46,
    "2co": 47, "2cor": 47,
    "gal": 48, "eph": 49,
    "php": 50, "phil": 50,
    "col": 51,
    "1th": 52, "1thes": 52,
    "2th": 53, "2thes": 53,
    "1ti": 54, "1tim": 54,
    "2ti": 55, "2tim": 55,
    "tit": 56,
    "phm": 57, "phlm": 57,
    "heb": 58,
    "jas": 59, "jam": 59,
    "1pe": 60, "1pet": 60,
    "2pe": 61, "2pet": 61,
    "1jn": 62, "1john": 62,
    "2jn": 63, "2john": 63,
    "3jn": 64, "3john": 64,
    "jud": 65, "jude": 65,
    "rev": 66,
}
BOOK_NAME_TO_ID.update(_OSIS_ALIASES)

# HelloAO API book abbreviation → book integer
HELLOAO_MAP: dict[str, int] = {
    "GEN": 1, "EXO": 2, "LEV": 3, "NUM": 4, "DEU": 5, "JOS": 6, "JDG": 7,
    "RUT": 8, "1SA": 9, "2SA": 10, "1KI": 11, "2KI": 12, "1CH": 13, "2CH": 14,
    "EZR": 15, "NEH": 16, "EST": 17, "JOB": 18, "PSA": 19, "PRO": 20,
    "ECC": 21, "SNG": 22, "ISA": 23, "JER": 24, "LAM": 25, "EZK": 26,
    "DAN": 27, "HOS": 28, "JOL": 29, "AMO": 30, "OBA": 31, "JON": 32,
    "MIC": 33, "NAH": 34, "HAB": 35, "ZEP": 36, "HAG": 37, "ZEC": 38,
    "MAL": 39, "MAT": 40, "MRK": 41, "LUK": 42, "JHN": 43, "ACT": 44,
    "ROM": 45, "1CO": 46, "2CO": 47, "GAL": 48, "EPH": 49, "PHP": 50,
    "COL": 51, "1TH": 52, "2TH": 53, "1TI": 54, "2TI": 55, "TIT": 56,
    "PHM": 57, "HEB": 58, "JAS": 59, "1PE": 60, "2PE": 61, "1JN": 62,
    "2JN": 63, "3JN": 64, "JUD": 65, "REV": 66,
}

# Standard KJV verse counts: (book_int, chapter) → verse_count
# Used to compute verse_end for the last commentary group in each chapter.
KJV_VERSE_COUNTS: dict[tuple[int, int], int] = {
    # Genesis (1)
    (1,1):31,(1,2):25,(1,3):24,(1,4):26,(1,5):32,(1,6):22,(1,7):24,(1,8):22,
    (1,9):29,(1,10):32,(1,11):32,(1,12):20,(1,13):18,(1,14):24,(1,15):21,
    (1,16):16,(1,17):27,(1,18):33,(1,19):38,(1,20):18,(1,21):34,(1,22):24,
    (1,23):20,(1,24):67,(1,25):34,(1,26):35,(1,27):46,(1,28):22,(1,29):35,
    (1,30):43,(1,31):55,(1,32):32,(1,33):20,(1,34):31,(1,35):29,(1,36):43,
    (1,37):36,(1,38):30,(1,39):23,(1,40):23,(1,41):57,(1,42):38,(1,43):34,
    (1,44):34,(1,45):28,(1,46):34,(1,47):31,(1,48):22,(1,49):33,(1,50):26,
    # Exodus (2)
    (2,1):22,(2,2):25,(2,3):22,(2,4):31,(2,5):23,(2,6):30,(2,7):25,(2,8):32,
    (2,9):35,(2,10):29,(2,11):10,(2,12):51,(2,13):22,(2,14):31,(2,15):27,
    (2,16):36,(2,17):16,(2,18):27,(2,19):25,(2,20):26,(2,21):36,(2,22):31,
    (2,23):33,(2,24):18,(2,25):40,(2,26):37,(2,27):21,(2,28):43,(2,29):46,
    (2,30):38,(2,31):18,(2,32):35,(2,33):23,(2,34):35,(2,35):35,(2,36):38,
    (2,37):29,(2,38):31,(2,39):43,(2,40):38,
    # Leviticus (3)
    (3,1):17,(3,2):16,(3,3):17,(3,4):35,(3,5):19,(3,6):30,(3,7):38,(3,8):36,
    (3,9):24,(3,10):20,(3,11):47,(3,12):8,(3,13):59,(3,14):57,(3,15):33,
    (3,16):34,(3,17):16,(3,18):30,(3,19):37,(3,20):27,(3,21):24,(3,22):33,
    (3,23):44,(3,24):23,(3,25):55,(3,26):46,(3,27):34,
    # Numbers (4)
    (4,1):54,(4,2):34,(4,3):51,(4,4):49,(4,5):31,(4,6):27,(4,7):89,(4,8):26,
    (4,9):23,(4,10):36,(4,11):35,(4,12):16,(4,13):33,(4,14):45,(4,15):41,
    (4,16):50,(4,17):13,(4,18):32,(4,19):22,(4,20):29,(4,21):35,(4,22):41,
    (4,23):30,(4,24):25,(4,25):18,(4,26):65,(4,27):23,(4,28):31,(4,29):40,
    (4,30):16,(4,31):54,(4,32):42,(4,33):56,(4,34):29,(4,35):34,(4,36):13,
    # Deuteronomy (5)
    (5,1):46,(5,2):37,(5,3):29,(5,4):49,(5,5):33,(5,6):25,(5,7):26,(5,8):20,
    (5,9):29,(5,10):22,(5,11):32,(5,12):32,(5,13):18,(5,14):29,(5,15):23,
    (5,16):22,(5,17):20,(5,18):22,(5,19):21,(5,20):20,(5,21):23,(5,22):30,
    (5,23):25,(5,24):22,(5,25):19,(5,26):19,(5,27):26,(5,28):68,(5,29):29,
    (5,30):20,(5,31):30,(5,32):52,(5,33):29,(5,34):12,
    # Joshua (6)
    (6,1):18,(6,2):24,(6,3):17,(6,4):24,(6,5):15,(6,6):27,(6,7):26,(6,8):35,
    (6,9):27,(6,10):43,(6,11):23,(6,12):24,(6,13):33,(6,14):15,(6,15):63,
    (6,16):10,(6,17):18,(6,18):28,(6,19):51,(6,20):9,(6,21):45,(6,22):34,
    (6,23):16,(6,24):33,
    # Judges (7)
    (7,1):36,(7,2):23,(7,3):31,(7,4):24,(7,5):31,(7,6):40,(7,7):25,(7,8):35,
    (7,9):57,(7,10):18,(7,11):40,(7,12):15,(7,13):25,(7,14):20,(7,15):20,
    (7,16):31,(7,17):13,(7,18):31,(7,19):30,(7,20):48,(7,21):25,
    # Ruth (8)
    (8,1):22,(8,2):23,(8,3):18,(8,4):22,
    # 1 Samuel (9)
    (9,1):28,(9,2):36,(9,3):21,(9,4):22,(9,5):12,(9,6):21,(9,7):17,(9,8):22,
    (9,9):27,(9,10):27,(9,11):15,(9,12):25,(9,13):23,(9,14):52,(9,15):35,
    (9,16):23,(9,17):58,(9,18):30,(9,19):24,(9,20):42,(9,21):15,(9,22):23,
    (9,23):29,(9,24):22,(9,25):44,(9,26):25,(9,27):12,(9,28):25,(9,29):11,
    (9,30):31,(9,31):13,
    # 2 Samuel (10)
    (10,1):27,(10,2):32,(10,3):39,(10,4):12,(10,5):25,(10,6):23,(10,7):29,
    (10,8):18,(10,9):13,(10,10):19,(10,11):27,(10,12):31,(10,13):39,(10,14):33,
    (10,15):37,(10,16):23,(10,17):29,(10,18):33,(10,19):43,(10,20):26,
    (10,21):22,(10,22):51,(10,23):39,(10,24):25,
    # 1 Kings (11)
    (11,1):53,(11,2):46,(11,3):28,(11,4):34,(11,5):18,(11,6):38,(11,7):51,
    (11,8):66,(11,9):28,(11,10):29,(11,11):43,(11,12):33,(11,13):34,
    (11,14):31,(11,15):34,(11,16):34,(11,17):24,(11,18):46,(11,19):21,
    (11,20):43,(11,21):29,(11,22):53,
    # 2 Kings (12)
    (12,1):18,(12,2):25,(12,3):27,(12,4):44,(12,5):27,(12,6):33,(12,7):20,
    (12,8):29,(12,9):37,(12,10):36,(12,11):21,(12,12):21,(12,13):25,
    (12,14):29,(12,15):38,(12,16):20,(12,17):41,(12,18):37,(12,19):37,
    (12,20):21,(12,21):26,(12,22):20,(12,23):37,(12,24):20,(12,25):30,
    # 1 Chronicles (13)
    (13,1):54,(13,2):55,(13,3):24,(13,4):43,(13,5):26,(13,6):81,(13,7):40,
    (13,8):40,(13,9):44,(13,10):14,(13,11):47,(13,12):40,(13,13):14,
    (13,14):17,(13,15):29,(13,16):43,(13,17):27,(13,18):17,(13,19):19,
    (13,20):8,(13,21):30,(13,22):19,(13,23):32,(13,24):31,(13,25):31,
    (13,26):32,(13,27):34,(13,28):21,(13,29):30,
    # 2 Chronicles (14)
    (14,1):17,(14,2):18,(14,3):17,(14,4):22,(14,5):14,(14,6):42,(14,7):22,
    (14,8):18,(14,9):31,(14,10):19,(14,11):23,(14,12):16,(14,13):22,
    (14,14):15,(14,15):19,(14,16):14,(14,17):19,(14,18):34,(14,19):11,
    (14,20):37,(14,21):20,(14,22):12,(14,23):21,(14,24):27,(14,25):28,
    (14,26):23,(14,27):9,(14,28):27,(14,29):36,(14,30):27,(14,31):21,
    (14,32):33,(14,33):25,(14,34):33,(14,35):27,(14,36):23,
    # Ezra (15)
    (15,1):11,(15,2):70,(15,3):13,(15,4):24,(15,5):17,(15,6):22,(15,7):28,
    (15,8):36,(15,9):15,(15,10):44,
    # Nehemiah (16)
    (16,1):11,(16,2):20,(16,3):32,(16,4):23,(16,5):19,(16,6):19,(16,7):73,
    (16,8):18,(16,9):38,(16,10):39,(16,11):36,(16,12):47,(16,13):31,
    # Esther (17)
    (17,1):22,(17,2):23,(17,3):15,(17,4):17,(17,5):14,(17,6):14,(17,7):10,
    (17,8):17,(17,9):32,(17,10):3,
    # Job (18)
    (18,1):22,(18,2):13,(18,3):26,(18,4):21,(18,5):27,(18,6):30,(18,7):21,
    (18,8):22,(18,9):35,(18,10):22,(18,11):20,(18,12):25,(18,13):28,
    (18,14):22,(18,15):35,(18,16):22,(18,17):16,(18,18):21,(18,19):29,
    (18,20):29,(18,21):34,(18,22):30,(18,23):17,(18,24):25,(18,25):6,
    (18,26):14,(18,27):23,(18,28):28,(18,29):25,(18,30):31,(18,31):40,
    (18,32):22,(18,33):33,(18,34):37,(18,35):16,(18,36):33,(18,37):24,
    (18,38):41,(18,39):30,(18,40):24,(18,41):34,(18,42):17,
    # Psalms (19)
    (19,1):6,(19,2):12,(19,3):8,(19,4):8,(19,5):12,(19,6):10,(19,7):17,
    (19,8):9,(19,9):20,(19,10):18,(19,11):7,(19,12):8,(19,13):6,(19,14):7,
    (19,15):5,(19,16):11,(19,17):15,(19,18):50,(19,19):14,(19,20):9,
    (19,21):13,(19,22):31,(19,23):6,(19,24):10,(19,25):22,(19,26):12,
    (19,27):14,(19,28):9,(19,29):11,(19,30):12,(19,31):24,(19,32):11,
    (19,33):22,(19,34):22,(19,35):28,(19,36):12,(19,37):40,(19,38):22,
    (19,39):13,(19,40):17,(19,41):13,(19,42):11,(19,43):5,(19,44):26,
    (19,45):17,(19,46):11,(19,47):9,(19,48):14,(19,49):20,(19,50):23,
    (19,51):19,(19,52):9,(19,53):6,(19,54):7,(19,55):23,(19,56):13,
    (19,57):11,(19,58):11,(19,59):17,(19,60):12,(19,61):8,(19,62):12,
    (19,63):11,(19,64):10,(19,65):13,(19,66):20,(19,67):7,(19,68):35,
    (19,69):36,(19,70):5,(19,71):24,(19,72):20,(19,73):28,(19,74):23,
    (19,75):10,(19,76):12,(19,77):20,(19,78):72,(19,79):13,(19,80):19,
    (19,81):16,(19,82):8,(19,83):18,(19,84):12,(19,85):13,(19,86):17,
    (19,87):7,(19,88):18,(19,89):52,(19,90):17,(19,91):16,(19,92):15,
    (19,93):5,(19,94):23,(19,95):11,(19,96):13,(19,97):12,(19,98):9,
    (19,99):9,(19,100):5,(19,101):8,(19,102):28,(19,103):22,(19,104):35,
    (19,105):45,(19,106):48,(19,107):43,(19,108):13,(19,109):31,(19,110):7,
    (19,111):10,(19,112):10,(19,113):9,(19,114):8,(19,115):18,(19,116):19,
    (19,117):2,(19,118):29,(19,119):176,(19,120):7,(19,121):8,(19,122):9,
    (19,123):4,(19,124):8,(19,125):5,(19,126):6,(19,127):5,(19,128):6,
    (19,129):8,(19,130):8,(19,131):3,(19,132):18,(19,133):3,(19,134):3,
    (19,135):21,(19,136):26,(19,137):9,(19,138):8,(19,139):24,(19,140):13,
    (19,141):10,(19,142):7,(19,143):12,(19,144):15,(19,145):21,(19,146):10,
    (19,147):20,(19,148):14,(19,149):9,(19,150):6,
    # Proverbs (20)
    (20,1):33,(20,2):22,(20,3):35,(20,4):27,(20,5):23,(20,6):35,(20,7):27,
    (20,8):36,(20,9):18,(20,10):32,(20,11):31,(20,12):28,(20,13):25,
    (20,14):35,(20,15):33,(20,16):33,(20,17):28,(20,18):24,(20,19):29,
    (20,20):30,(20,21):31,(20,22):29,(20,23):35,(20,24):34,(20,25):28,
    (20,26):28,(20,27):27,(20,28):28,(20,29):27,(20,30):33,(20,31):31,
    # Ecclesiastes (21)
    (21,1):18,(21,2):26,(21,3):22,(21,4):16,(21,5):20,(21,6):12,(21,7):29,
    (21,8):17,(21,9):18,(21,10):20,(21,11):10,(21,12):14,
    # Song of Solomon (22)
    (22,1):17,(22,2):17,(22,3):11,(22,4):16,(22,5):16,(22,6):13,(22,7):13,
    (22,8):14,
    # Isaiah (23)
    (23,1):31,(23,2):22,(23,3):26,(23,4):6,(23,5):30,(23,6):13,(23,7):25,
    (23,8):22,(23,9):21,(23,10):34,(23,11):16,(23,12):6,(23,13):22,
    (23,14):32,(23,15):9,(23,16):14,(23,17):14,(23,18):7,(23,19):25,
    (23,20):6,(23,21):17,(23,22):25,(23,23):18,(23,24):23,(23,25):12,
    (23,26):21,(23,27):13,(23,28):29,(23,29):24,(23,30):33,(23,31):9,
    (23,32):20,(23,33):24,(23,34):17,(23,35):10,(23,36):22,(23,37):38,
    (23,38):22,(23,39):8,(23,40):31,(23,41):29,(23,42):25,(23,43):28,
    (23,44):28,(23,45):25,(23,46):13,(23,47):15,(23,48):22,(23,49):26,
    (23,50):11,(23,51):23,(23,52):15,(23,53):12,(23,54):17,(23,55):13,
    (23,56):12,(23,57):21,(23,58):14,(23,59):21,(23,60):22,(23,61):11,
    (23,62):12,(23,63):19,(23,64):12,(23,65):25,(23,66):24,
    # Jeremiah (24)
    (24,1):19,(24,2):37,(24,3):25,(24,4):31,(24,5):31,(24,6):30,(24,7):34,
    (24,8):22,(24,9):26,(24,10):25,(24,11):23,(24,12):17,(24,13):27,
    (24,14):22,(24,15):21,(24,16):21,(24,17):27,(24,18):23,(24,19):15,
    (24,20):18,(24,21):14,(24,22):30,(24,23):40,(24,24):10,(24,25):38,
    (24,26):24,(24,27):22,(24,28):17,(24,29):32,(24,30):24,(24,31):40,
    (24,32):44,(24,33):26,(24,34):22,(24,35):19,(24,36):32,(24,37):21,
    (24,38):28,(24,39):18,(24,40):16,(24,41):18,(24,42):22,(24,43):13,
    (24,44):30,(24,45):5,(24,46):28,(24,47):7,(24,48):47,(24,49):39,
    (24,50):46,(24,51):64,(24,52):34,
    # Lamentations (25)
    (25,1):22,(25,2):22,(25,3):66,(25,4):22,(25,5):22,
    # Ezekiel (26)
    (26,1):28,(26,2):10,(26,3):27,(26,4):17,(26,5):17,(26,6):14,(26,7):27,
    (26,8):18,(26,9):11,(26,10):22,(26,11):25,(26,12):28,(26,13):23,
    (26,14):23,(26,15):8,(26,16):63,(26,17):24,(26,18):32,(26,19):14,
    (26,20):49,(26,21):32,(26,22):31,(26,23):49,(26,24):27,(26,25):17,
    (26,26):21,(26,27):36,(26,28):26,(26,29):21,(26,30):26,(26,31):18,
    (26,32):32,(26,33):33,(26,34):31,(26,35):15,(26,36):38,(26,37):28,
    (26,38):23,(26,39):29,(26,40):49,(26,41):26,(26,42):20,(26,43):27,
    (26,44):31,(26,45):25,(26,46):24,(26,47):23,(26,48):35,
    # Daniel (27)
    (27,1):21,(27,2):49,(27,3):30,(27,4):37,(27,5):31,(27,6):28,(27,7):28,
    (27,8):27,(27,9):27,(27,10):21,(27,11):45,(27,12):13,
    # Hosea (28)
    (28,1):11,(28,2):23,(28,3):5,(28,4):19,(28,5):15,(28,6):11,(28,7):16,
    (28,8):14,(28,9):17,(28,10):15,(28,11):12,(28,12):14,(28,13):16,
    (28,14):9,
    # Joel (29)
    (29,1):20,(29,2):32,(29,3):21,
    # Amos (30)
    (30,1):15,(30,2):16,(30,3):15,(30,4):13,(30,5):27,(30,6):14,(30,7):17,
    (30,8):14,(30,9):15,
    # Obadiah (31)
    (31,1):21,
    # Jonah (32)
    (32,1):17,(32,2):10,(32,3):10,(32,4):11,
    # Micah (33)
    (33,1):16,(33,2):13,(33,3):12,(33,4):13,(33,5):15,(33,6):16,(33,7):20,
    # Nahum (34)
    (34,1):15,(34,2):13,(34,3):19,
    # Habakkuk (35)
    (35,1):17,(35,2):20,(35,3):19,
    # Zephaniah (36)
    (36,1):18,(36,2):15,(36,3):20,
    # Haggai (37)
    (37,1):15,(37,2):23,
    # Zechariah (38)
    (38,1):21,(38,2):13,(38,3):10,(38,4):14,(38,5):11,(38,6):15,(38,7):14,
    (38,8):23,(38,9):17,(38,10):12,(38,11):17,(38,12):14,(38,13):9,
    (38,14):21,
    # Malachi (39)
    (39,1):14,(39,2):17,(39,3):18,(39,4):6,
    # Matthew (40)
    (40,1):25,(40,2):23,(40,3):17,(40,4):25,(40,5):48,(40,6):34,(40,7):29,
    (40,8):34,(40,9):38,(40,10):42,(40,11):30,(40,12):50,(40,13):58,
    (40,14):36,(40,15):39,(40,16):28,(40,17):27,(40,18):35,(40,19):30,
    (40,20):34,(40,21):46,(40,22):46,(40,23):39,(40,24):51,(40,25):46,
    (40,26):75,(40,27):66,(40,28):20,
    # Mark (41)
    (41,1):45,(41,2):28,(41,3):35,(41,4):41,(41,5):43,(41,6):56,(41,7):37,
    (41,8):38,(41,9):50,(41,10):52,(41,11):33,(41,12):44,(41,13):37,
    (41,14):72,(41,15):47,(41,16):20,
    # Luke (42)
    (42,1):80,(42,2):52,(42,3):38,(42,4):44,(42,5):39,(42,6):49,(42,7):50,
    (42,8):56,(42,9):62,(42,10):42,(42,11):54,(42,12):59,(42,13):35,
    (42,14):35,(42,15):32,(42,16):31,(42,17):37,(42,18):43,(42,19):48,
    (42,20):47,(42,21):38,(42,22):71,(42,23):56,(42,24):53,
    # John (43)
    (43,1):51,(43,2):25,(43,3):36,(43,4):54,(43,5):47,(43,6):71,(43,7):53,
    (43,8):59,(43,9):41,(43,10):42,(43,11):57,(43,12):50,(43,13):38,
    (43,14):31,(43,15):27,(43,16):33,(43,17):26,(43,18):40,(43,19):42,
    (43,20):31,(43,21):25,
    # Acts (44)
    (44,1):26,(44,2):47,(44,3):26,(44,4):37,(44,5):42,(44,6):15,(44,7):60,
    (44,8):40,(44,9):43,(44,10):48,(44,11):30,(44,12):25,(44,13):52,
    (44,14):28,(44,15):41,(44,16):40,(44,17):34,(44,18):28,(44,19):41,
    (44,20):38,(44,21):40,(44,22):30,(44,23):35,(44,24):27,(44,25):27,
    (44,26):32,(44,27):44,(44,28):31,
    # Romans (45)
    (45,1):32,(45,2):29,(45,3):31,(45,4):25,(45,5):21,(45,6):23,(45,7):25,
    (45,8):39,(45,9):33,(45,10):21,(45,11):36,(45,12):21,(45,13):14,
    (45,14):23,(45,15):33,(45,16):27,
    # 1 Corinthians (46)
    (46,1):31,(46,2):16,(46,3):23,(46,4):21,(46,5):13,(46,6):20,(46,7):40,
    (46,8):13,(46,9):27,(46,10):33,(46,11):34,(46,12):31,(46,13):13,
    (46,14):40,(46,15):58,(46,16):24,
    # 2 Corinthians (47)
    (47,1):24,(47,2):17,(47,3):18,(47,4):18,(47,5):21,(47,6):18,(47,7):16,
    (47,8):24,(47,9):15,(47,10):18,(47,11):33,(47,12):21,(47,13):14,
    # Galatians (48)
    (48,1):24,(48,2):21,(48,3):29,(48,4):31,(48,5):26,(48,6):18,
    # Ephesians (49)
    (49,1):23,(49,2):22,(49,3):21,(49,4):32,(49,5):33,(49,6):24,
    # Philippians (50)
    (50,1):30,(50,2):30,(50,3):21,(50,4):23,
    # Colossians (51)
    (51,1):29,(51,2):23,(51,3):25,(51,4):18,
    # 1 Thessalonians (52)
    (52,1):10,(52,2):20,(52,3):13,(52,4):18,(52,5):28,
    # 2 Thessalonians (53)
    (53,1):12,(53,2):17,(53,3):18,
    # 1 Timothy (54)
    (54,1):20,(54,2):15,(54,3):16,(54,4):16,(54,5):25,(54,6):21,
    # 2 Timothy (55)
    (55,1):18,(55,2):26,(55,3):17,(55,4):22,
    # Titus (56)
    (56,1):16,(56,2):15,(56,3):15,
    # Philemon (57)
    (57,1):25,
    # Hebrews (58)
    (58,1):14,(58,2):18,(58,3):19,(58,4):16,(58,5):14,(58,6):20,(58,7):28,
    (58,8):13,(58,9):28,(58,10):39,(58,11):40,(58,12):29,(58,13):25,
    # James (59)
    (59,1):27,(59,2):26,(59,3):18,(59,4):17,(59,5):20,
    # 1 Peter (60)
    (60,1):25,(60,2):25,(60,3):22,(60,4):19,(60,5):14,
    # 2 Peter (61)
    (61,1):21,(61,2):22,(61,3):18,
    # 1 John (62)
    (62,1):10,(62,2):29,(62,3):24,(62,4):21,(62,5):21,
    # 2 John (63)
    (63,1):13,
    # 3 John (64)
    (64,1):14,
    # Jude (65)
    (65,1):25,
    # Revelation (66)
    (66,1):20,(66,2):29,(66,3):22,(66,4):11,(66,5):14,(66,6):17,(66,7):17,
    (66,8):13,(66,9):21,(66,10):11,(66,11):19,(66,12):17,(66,13):18,
    (66,14):20,(66,15):8,(66,16):21,(66,17):18,(66,18):24,(66,19):21,
    (66,20):15,(66,21):27,(66,22):21,
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def normalize_strongs(s: str) -> str:
    """Strip common prefixes and normalize zero-padding from Strong's numbers.

    Examples:
        'strong:H07225'      → 'H7225'
        'lemma:strong:G0976' → 'G976'
        'strongMorph:TH8804' → 'TH8804'  (morphology tag — returned as-is after prefix strip)
        'H007225'            → 'H7225'
    """
    s = s.strip()
    for prefix in ("lemma:strong:", "strong:", "strongMorph:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    if len(s) >= 2 and s[0] in "HG":
        letter = s[0]
        digits = s[1:].lstrip("0") or "0"
        return letter + digits
    return s


def book_name_to_id(name: str) -> int | None:
    """Return integer book ID (1–66) for a book name or abbreviation.

    Returns None and prints a warning if the name is unrecognised.
    """
    key = name.strip().lower()
    result = BOOK_NAME_TO_ID.get(key)
    if result is None:
        print(f"  [WARN] Unrecognised book name/abbr: '{name}'", flush=True)
    return result


def table_has_rows(con: sqlite3.Connection, table: str) -> bool:
    """Return True if *table* exists and has at least one row."""
    try:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return count > 0
    except sqlite3.OperationalError:
        return False


def flush_rows(
    con: sqlite3.Connection,
    sql: str,
    rows: list,
) -> None:
    """Insert *rows* using *sql* then clear the list in-place."""
    if rows:
        con.executemany(sql, rows)
        rows.clear()


# ---------------------------------------------------------------------------
# Step 1 — word_strongs (KJV-osis.json → kjv.db)
# ---------------------------------------------------------------------------

def build_kjv() -> None:
    """Convert KJV_raw.db (scrollmapper new format) → kjv.db with t_kjv schema.

    The upstream repo reorganised from sqlite/t_kjv.db to formats/sqlite/KJV.db.
    The new file uses table KJV_verses(id, book_id, chapter, verse, text) and
    contains 7 identical copies of every verse (multi-edition artefact).
    We deduplicate and write the canonical t_kjv(b, c, v, t) schema.
    """
    raw_path = DATA / "KJV_raw.db"
    out_path = DATA / "kjv.db"

    if not raw_path.exists():
        print("  KJV_raw.db not found — skipping step kjv.", flush=True)
        return

    # Skip if already built with valid content
    if out_path.exists() and out_path.stat().st_size > 0:
        try:
            c = sqlite3.connect(str(out_path))
            count = c.execute("SELECT COUNT(*) FROM t_kjv").fetchone()[0]
            c.close()
            if count >= 31000:
                print(f"  kjv.db already has {count} rows — skipping.", flush=True)
                return
        except Exception:
            pass  # rebuild

    src = sqlite3.connect(str(raw_path))
    if out_path.exists():
        out_path.unlink()
    dst = sqlite3.connect(str(out_path))
    try:
        dst.execute("CREATE TABLE t_kjv (b INTEGER, c INTEGER, v INTEGER, t TEXT)")
        dst.execute("CREATE UNIQUE INDEX idx_t_kjv ON t_kjv (b, c, v)")
        rows = src.execute(
            "SELECT book_id, chapter, verse, text "
            "FROM KJV_verses "
            "GROUP BY book_id, chapter, verse "
            "ORDER BY book_id, chapter, verse"
        ).fetchall()
        dst.executemany("INSERT OR IGNORE INTO t_kjv (b,c,v,t) VALUES (?,?,?,?)", rows)
        dst.commit()
        count = dst.execute("SELECT COUNT(*) FROM t_kjv").fetchone()[0]
        print(f"  kjv.db built: {count} unique verses (expected 31,102)", flush=True)
    finally:
        src.close()
        dst.close()


def build_word_strongs() -> None:
    print("\n=== Step 1: word_strongs ===", flush=True)
    src = DATA / "KJV-osis.json"
    if not src.exists():
        print("  KJV-osis.json not found — skipping step 1.", flush=True)
        return

    db_path = DATA / "kjv.db"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    con.execute("""
        CREATE TABLE IF NOT EXISTS word_strongs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id       INTEGER NOT NULL,
            chapter       INTEGER NOT NULL,
            verse         INTEGER NOT NULL,
            word_position INTEGER NOT NULL,
            phrase_text   TEXT    NOT NULL,
            strong_number TEXT    NOT NULL,
            extra_strongs TEXT,
            morph         TEXT,
            UNIQUE (book_id, chapter, verse, word_position)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_ws_bcv     ON word_strongs(book_id, chapter, verse)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ws_strongs ON word_strongs(strong_number)")
    con.commit()

    if table_has_rows(con, "word_strongs"):
        print("  word_strongs already populated — skipping.", flush=True)
        con.close()
        return

    W_TAG  = re.compile(r'<w\s+([^>]*)>(.*?)</w>', re.DOTALL)
    LEMMA  = re.compile(r'lemma="([^"]+)"')
    MORPH  = re.compile(r'morph="([^"]+)"')
    TRANS  = re.compile(r'<transChange[^>]*>.*?</transChange>', re.DOTALL)

    insert_sql = (
        "INSERT OR IGNORE INTO word_strongs"
        "(book_id, chapter, verse, word_position, phrase_text, strong_number, extra_strongs, morph)"
        " VALUES (?,?,?,?,?,?,?,?)"
    )

    print("  Loading KJV-osis.json …", flush=True)
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    rows: list = []
    total = 0

    for book_obj in data.get("books", []):
        book_id = book_name_to_id(book_obj.get("name", ""))
        if not book_id:
            continue
        for chap_obj in book_obj.get("chapters", []):
            chap = int(chap_obj["chapter"])
            for verse_obj in chap_obj.get("verses", []):
                verse = int(verse_obj["verse"])
                text  = verse_obj.get("text", "")
                # Remove transChange (KJV italics — no Strong's mapping)
                text  = TRANS.sub("", text)
                pos   = 0
                for m in W_TAG.finditer(text):
                    attrs  = m.group(1)
                    phrase = m.group(2)
                    phrase_clean = re.sub(r'<[^>]+>', '', phrase).strip()
                    if not phrase_clean:
                        continue
                    lemma_m = LEMMA.search(attrs)
                    if not lemma_m:
                        continue
                    tokens = lemma_m.group(1).split()
                    numbers = [
                        normalize_strongs(t) for t in tokens
                        if t.startswith("strong:") or t.startswith("lemma:strong:")
                    ]
                    if not numbers:
                        continue
                    morph_m = MORPH.search(attrs)
                    morph_v = normalize_strongs(morph_m.group(1)) if morph_m else None
                    pos += 1
                    rows.append((
                        book_id, chap, verse, pos, phrase_clean,
                        numbers[0],
                        " ".join(numbers[1:]) or None,
                        morph_v,
                    ))
                    if len(rows) >= 10_000:
                        flush_rows(con, insert_sql, rows)
                        total += 10_000

    flush_rows(con, insert_sql, rows)
    con.commit()
    final = con.execute("SELECT COUNT(*) FROM word_strongs").fetchone()[0]
    print(f"  word_strongs: {final:,} rows inserted (expected ~230,000)", flush=True)
    con.close()


# ---------------------------------------------------------------------------
# Step 2 — cross_refs (7 shard DBs → cross_references.db)
# ---------------------------------------------------------------------------

def build_cross_refs() -> None:
    print("\n=== Step 2: cross_refs ===", flush=True)
    db_path = DATA / "cross_references.db"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    con.execute("""
        CREATE TABLE IF NOT EXISTS cross_refs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            from_book      TEXT    NOT NULL,
            from_chapter   INTEGER NOT NULL,
            from_verse     INTEGER NOT NULL,
            to_book        TEXT    NOT NULL,
            to_chapter     INTEGER NOT NULL,
            to_verse_start INTEGER NOT NULL,
            to_verse_end   INTEGER NOT NULL,
            votes          INTEGER NOT NULL DEFAULT 0
        )
    """)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_xref_unique ON cross_refs(
            from_book, from_chapter, from_verse,
            to_book, to_chapter, to_verse_start, to_verse_end
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_xref_from ON cross_refs(from_book, from_chapter, from_verse)")
    con.commit()

    if table_has_rows(con, "cross_refs"):
        print("  cross_refs already populated — skipping.", flush=True)
        con.close()
        return

    insert_sql = (
        "INSERT OR IGNORE INTO cross_refs"
        "(from_book, from_chapter, from_verse, to_book, to_chapter, to_verse_start, to_verse_end, votes)"
        " VALUES (?,?,?,?,?,?,?,?)"
    )

    grand_total = 0
    for i in range(7):
        shard_path = DATA / f"cross_references_{i}.db"
        if not shard_path.exists():
            print(f"  shard {i}: not found — skipping.", flush=True)
            continue
        try:
            shard = sqlite3.connect(shard_path)
            # The scrollmapper shards use table name "cross_references"
            rows = shard.execute(
                "SELECT from_book, from_chapter, from_verse,"
                "       to_book, to_chapter, to_verse_start, to_verse_end, votes"
                " FROM cross_references"
            ).fetchall()
            shard.close()
            con.executemany(insert_sql, rows)
            con.commit()
            grand_total += len(rows)
            print(f"  shard {i}: {len(rows):,} rows processed", flush=True)
        except Exception:
            print(f"  shard {i}: ERROR — {traceback.format_exc().splitlines()[-1]}", flush=True)

    # Fallback: scrollmapper distributes a single cross_references.db (not shards).
    # If it was downloaded to /app/data/cross_references.db it will already be open
    # as our output DB — read from its embedded cross_references table directly.
    if grand_total == 0:
        try:
            rows = con.execute(
                "SELECT from_book, from_chapter, from_verse,"
                "       to_book, to_chapter, to_verse_start, to_verse_end, votes"
                " FROM cross_references"
            ).fetchall()
            if rows:
                con.executemany(insert_sql, rows)
                con.commit()
                grand_total = len(rows)
                print(f"  cross_refs: {grand_total:,} rows loaded from embedded cross_references table", flush=True)
            else:
                print("  cross_refs: no cross-reference data found in any source.", flush=True)
        except sqlite3.OperationalError:
            print("  cross_refs: cross_references table not present in downloaded DB.", flush=True)

    total = con.execute("SELECT COUNT(*) FROM cross_refs").fetchone()[0]
    print(f"  cross_refs: {total:,} unique rows (expected ~432,949)", flush=True)
    con.close()


# ---------------------------------------------------------------------------
# Step 3 — strongs (XML → strongs.db)
# ---------------------------------------------------------------------------

def build_strongs() -> None:
    print("\n=== Step 3: strongs ===", flush=True)
    db_path = DATA / "strongs.db"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    con.execute("""
        CREATE TABLE IF NOT EXISTS strongs (
            number          TEXT PRIMARY KEY,
            language        TEXT,
            original        TEXT,
            transliteration TEXT,
            pronunciation   TEXT,
            definition      TEXT,
            kjv_usage       TEXT
        )
    """)
    con.commit()

    if table_has_rows(con, "strongs"):
        print("  strongs already populated — skipping.", flush=True)
        con.close()
        return

    insert_sql = (
        "INSERT OR REPLACE INTO strongs"
        "(number, language, original, transliteration, pronunciation, definition, kjv_usage)"
        " VALUES (?,?,?,?,?,?,?)"
    )

    def parse_strongs_xml(xml_path: Path, language: str) -> int:
        if not xml_path.exists():
            print(f"  {xml_path.name} not found — skipping {language}.", flush=True)
            return 0
        print(f"  Parsing {xml_path.name} ({language}) …", flush=True)
        count = 0
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            # Handle optional namespace
            ns_match = re.match(r'\{([^}]+)\}', root.tag)
            ns = f"{{{ns_match.group(1)}}}" if ns_match else ""

            # Try classic DTD schema first: <entry strongs="NNN">
            entries = root.findall(f".//{ns}entry")
            if entries:
                for entry in entries:
                    raw_num = entry.get("strongs") or entry.get("id") or ""
                    if not raw_num:
                        continue
                    number = normalize_strongs(raw_num)

                    w_el = entry.find(f"{ns}w")
                    original = w_el.text.strip() if w_el is not None and w_el.text else ""
                    xlit  = (w_el.get("xlit", "") or "") if w_el is not None else ""
                    pron  = (w_el.get("pron", "") or "") if w_el is not None else ""

                    def_parts = []
                    for tag in (f"{ns}strongs_def", f"{ns}def"):
                        for el in entry.findall(f".//{tag}"):
                            if el.text:
                                def_parts.append(el.text.strip())
                    definition = " ".join(def_parts).strip()

                    usage_el = entry.find(f".//{ns}kjv_def")
                    if usage_el is None:
                        usage_el = entry.find(f".//{ns}usage")
                    kjv_usage = (usage_el.text or "").strip() if usage_el is not None else ""

                    con.execute(insert_sql, (number, language, original, xlit, pron, definition, kjv_usage))
                    count += 1
                    if count % 1000 == 0:
                        con.commit()
            else:
                # OSIS schema (StrongHebrewG.xml): <div type="entry" n="NNN">
                #   <w ID="H1" xlit="..." POS="...">word</w>
                #   <note type="exegesis">definition</note>
                #   <note type="translation">KJV usage</note>
                osis_entries = [
                    d for d in root.findall(f".//{ns}div")
                    if d.get("type") == "entry"
                ]
                print(f"    (OSIS schema detected — {len(osis_entries)} entries)", flush=True)
                for div in osis_entries:
                    w_el = div.find(f"{ns}w")
                    if w_el is None:
                        continue
                    raw_num = w_el.get("ID") or div.get("n", "")
                    if not raw_num:
                        continue
                    number = normalize_strongs(raw_num)
                    original = (w_el.text or "").strip()
                    xlit = w_el.get("xlit", "") or ""
                    pron = w_el.get("POS", "") or ""

                    def_parts: list[str] = []
                    kjv_usage = ""
                    for note in div.findall(f"{ns}note"):
                        ntype = note.get("type", "")
                        txt = (note.text or "").strip()
                        if ntype == "exegesis" and txt:
                            def_parts.append(txt)
                        elif ntype == "translation" and txt:
                            kjv_usage = txt
                    definition = " ".join(def_parts).strip()

                    con.execute(insert_sql, (number, language, original, xlit, pron, definition, kjv_usage))
                    count += 1
                    if count % 1000 == 0:
                        con.commit()
        except Exception:
            print(f"  ERROR parsing {xml_path.name}: {traceback.format_exc().splitlines()[-1]}", flush=True)
        con.commit()
        return count

    heb_count = parse_strongs_xml(DATA / "strongs_hebrew.xml", "Hebrew")
    grk_count = parse_strongs_xml(DATA / "strongs_greek.xml", "Greek")
    total = con.execute("SELECT COUNT(*) FROM strongs").fetchone()[0]
    print(
        f"  strongs: Hebrew={heb_count:,}  Greek={grk_count:,}  total={total:,}"
        f" (expected ~8,674 + ~5,624)",
        flush=True,
    )
    con.close()


# ---------------------------------------------------------------------------
# Step 4 — interlinear (STEPBible TAHOT + TAGNT → interlinear.db)
# ---------------------------------------------------------------------------

def build_interlinear() -> None:
    print("\n=== Step 4: interlinear ===", flush=True)
    db_path = DATA / "interlinear.db"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    con.execute("""
        CREATE TABLE IF NOT EXISTS interlinear (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            book            INTEGER NOT NULL,
            chapter         INTEGER NOT NULL,
            verse           INTEGER NOT NULL,
            word_num        INTEGER NOT NULL,
            testament       TEXT    NOT NULL,
            original_word   TEXT    NOT NULL,
            transliteration TEXT,
            strongs_num     TEXT,
            morphology      TEXT,
            english_gloss   TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_interlinear_ref     ON interlinear(book, chapter, verse, word_num)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_interlinear_strongs ON interlinear(strongs_num)")
    con.commit()

    if table_has_rows(con, "interlinear"):
        print("  interlinear already populated — skipping.", flush=True)
        con.close()
        return

    insert_sql = (
        "INSERT OR IGNORE INTO interlinear"
        "(book, chapter, verse, word_num, testament, original_word,"
        " transliteration, strongs_num, morphology, english_gloss)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)"
    )

    # Regex matching TAHOT/TAGNT reference column: "Gen.1.1#01"
    REF_RE = re.compile(r'^([A-Z1-9][a-zA-Z]{1,3})\.(\d+)\.(\d+)#(\d+)')
    # For TAHOT: curly-brace root Strong's, e.g. {H7225}
    CURLY  = re.compile(r'\{(H\d+[A-Za-z]?)\}')
    H_BARE = re.compile(r'H\d+')
    G_BARE = re.compile(r'G\d+')

    rows: list = []
    grand_total = 0

    def flush_interlinear() -> None:
        nonlocal grand_total
        flush_rows(con, insert_sql, rows)
        grand_total += len(rows)

    # --- OT (TAHOT) ---
    tahot_files = [
        DATA / "TAHOT_Gen-Deu.txt",
        DATA / "TAHOT_Jos-Est.txt",
        DATA / "TAHOT_Job-Sng.txt",
        DATA / "TAHOT_Isa-Mal.txt",
    ]

    for filepath in tahot_files:
        if not filepath.exists():
            print(f"  {filepath.name} not found — skipping.", flush=True)
            continue
        print(f"  Parsing {filepath.name} …", flush=True)
        file_count = 0
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for line in f:
                ref_m = REF_RE.match(line)
                if not ref_m:
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 4:
                    continue
                book_abbr, chap_s, verse_s, wordnum_s = ref_m.groups()
                book_id = book_name_to_id(book_abbr)
                if not book_id:
                    continue

                # col 1: original Hebrew word (may have / or \ as vowel-pointing markers)
                original = cols[1].replace("/", "").replace("\\", "").strip() if len(cols) > 1 else ""
                # col 2: transliteration
                translit = cols[2].strip() if len(cols) > 2 else None
                # col 3: English gloss (may have < > [ ] brackets)
                gloss_raw = cols[3].strip() if len(cols) > 3 else ""
                gloss = re.sub(r'[<>\[\]]', '', gloss_raw).strip() or None
                # col 4: detailed Strong's field e.g. "H=H07225 {H7225} ..."
                dstrong = cols[4].strip() if len(cols) > 4 else ""
                # col 5: morphology code
                morph = cols[5].strip() if len(cols) > 5 else None

                # Extract root Strong's number
                curly_m = CURLY.search(dstrong)
                if curly_m:
                    strongs = normalize_strongs(curly_m.group(1))
                else:
                    h_m = H_BARE.search(dstrong)
                    strongs = normalize_strongs(h_m.group()) if h_m else None

                rows.append((
                    book_id, int(chap_s), int(verse_s), int(wordnum_s),
                    "OT", original or "", translit, strongs, morph or None, gloss,
                ))
                file_count += 1
                if len(rows) >= 10_000:
                    flush_interlinear()
        flush_interlinear()
        con.commit()
        print(f"    {filepath.name}: {file_count:,} words", flush=True)

    # --- NT (TAGNT) ---
    tagnt_files = [
        DATA / "TAGNT_Mat-Jhn.txt",
        DATA / "TAGNT_Act-Rev.txt",
    ]

    for filepath in tagnt_files:
        if not filepath.exists():
            print(f"  {filepath.name} not found — skipping.", flush=True)
            continue
        print(f"  Parsing {filepath.name} …", flush=True)
        file_count = 0
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for line in f:
                ref_m = REF_RE.match(line)
                if not ref_m:
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 3:
                    continue
                book_abbr, chap_s, verse_s, wordnum_s = ref_m.groups()
                book_id = book_name_to_id(book_abbr)
                if not book_id:
                    continue

                # col 1: "Οὕτως (Houtōs)" — split on " ("
                word_raw = cols[1].strip() if len(cols) > 1 else ""
                word_parts = word_raw.split(" (", 1)
                original = word_parts[0].strip()
                translit = word_parts[1].rstrip(")").strip() if len(word_parts) > 1 else None

                # col 2: English gloss (BSB)
                gloss = cols[2].strip() if len(cols) > 2 else None

                # col 3: dStrong field, e.g. "dStrong=G3779=ADV" or "G3779"
                morph_raw = cols[3].strip() if len(cols) > 3 else ""
                morph = morph_raw.split("=")[-1] if "=" in morph_raw else morph_raw or None

                # col 11 (0-indexed): simple Strong's number, most reliable
                strongs: str | None = None
                if len(cols) > 11 and cols[11].strip():
                    raw_s = cols[11].strip()
                    if raw_s.startswith("G") or raw_s.startswith("H"):
                        strongs = normalize_strongs(raw_s)
                if not strongs:
                    # fallback: extract from dStrong col
                    g_m = G_BARE.search(morph_raw)
                    strongs = normalize_strongs(g_m.group()) if g_m else None

                rows.append((
                    book_id, int(chap_s), int(verse_s), int(wordnum_s),
                    "NT", original or "", translit, strongs, morph or None, gloss,
                ))
                file_count += 1
                if len(rows) >= 10_000:
                    flush_interlinear()
        flush_interlinear()
        con.commit()
        print(f"    {filepath.name}: {file_count:,} words", flush=True)

    total = con.execute("SELECT COUNT(*) FROM interlinear").fetchone()[0]
    print(f"  interlinear: {total:,} rows total (expected ~443,000)", flush=True)
    con.close()


# ---------------------------------------------------------------------------
# Step 5 — commentary (Matthew Henry via HelloAO API → commentary.db)
# ---------------------------------------------------------------------------

def build_commentary() -> None:
    print("\n=== Step 5: commentary (Matthew Henry via HelloAO) ===", flush=True)
    db_path = DATA / "commentary.db"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    con.execute("""
        CREATE TABLE IF NOT EXISTS commentary (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            book        INTEGER NOT NULL,
            chapter     INTEGER NOT NULL,
            verse_start INTEGER,
            verse_end   INTEGER,
            author      TEXT    NOT NULL DEFAULT 'Matthew Henry',
            text        TEXT    NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_commentary_lookup ON commentary(book, chapter, verse_start)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_commentary_range  ON commentary(book, chapter, verse_end)")
    con.commit()

    if table_has_rows(con, "commentary"):
        print("  commentary already populated — skipping.", flush=True)
        con.close()
        return

    BASE_URL = "https://bible.helloao.org/api/c/matthew-henry"
    HTML_TAG = re.compile(r'<[^>]+>')

    print("  Fetching book list from HelloAO …", flush=True)
    try:
        resp = requests.get(f"{BASE_URL}/books.json", timeout=30)
        resp.raise_for_status()
        raw = resp.json()
    except Exception:
        print(f"  ERROR fetching book list: {traceback.format_exc().splitlines()[-1]}", flush=True)
        con.close()
        return

    # Normalise the book list regardless of API shape.
    # Old format: list of dicts with "id", "numberOfChapters", ...
    # New format: list of strings (book abbreviations) or dict wrapping a list.
    if isinstance(raw, dict):
        # Try common wrapper keys
        inner = raw.get("books") or raw.get("data") or []
        books_raw = inner if isinstance(inner, list) else list(raw.values())
    elif isinstance(raw, list):
        books_raw = raw
    else:
        books_raw = []

    # Build a uniform list of (abbr, num_chapters) tuples
    book_entries: list[tuple[str, int]] = []
    for item in books_raw:
        if isinstance(item, dict):
            abbr = (item.get("id") or item.get("abbreviation") or "").upper()
            chaps = int(item.get("numberOfChapters") or item.get("chapters") or 0)
        elif isinstance(item, str):
            abbr = item.upper()
            chaps = 0  # derive from our own verse-count table
        else:
            continue
        if not abbr:
            continue
        # Derive chapter count from KJV_VERSE_COUNTS if not provided
        if chaps == 0:
            book_int_tmp = HELLOAO_MAP.get(abbr)
            if book_int_tmp:
                chaps = max(c for (b, c) in KJV_VERSE_COUNTS if b == book_int_tmp) if book_int_tmp else 0
        book_entries.append((abbr, chaps))

    # Fall back: if the API gave us nothing, iterate all 66 books ourselves
    if not book_entries:
        print("  WARNING: books.json returned no usable entries — iterating all 66 books.", flush=True)
        for abbr, book_int in HELLOAO_MAP.items():
            chaps = max((c for (b, c) in KJV_VERSE_COUNTS if b == book_int), default=0)
            book_entries.append((abbr, chaps))

    total_rows = 0
    total_chapters = sum(c for _, c in book_entries)
    chapters_done = 0

    for book_abbr, num_chaps in book_entries:
        book_int  = HELLOAO_MAP.get(book_abbr)
        if not book_int:
            continue

        for chap in range(1, num_chaps + 1):
            url = f"{BASE_URL}/{book_abbr}/{chap}.json"
            try:
                r = requests.get(url, timeout=30)
                if r.status_code != 200:
                    chapters_done += 1
                    continue
                chapter_data = r.json()
            except Exception:
                chapters_done += 1
                continue

            # HelloAO chapter response: {chapter: {number, content: [{type, number, content}]}}
            # data["commentary"] is metadata (not the text); data["chapter"]["content"] is
            # the list of verse groups.
            chapter_obj = chapter_data.get("chapter", {}) if isinstance(chapter_data, dict) else {}
            content = chapter_obj.get("content") or []
            if not isinstance(content, list):
                content = []

            groups = [v for v in content if isinstance(v, dict) and v.get("type") == "verse"]
            if not groups:
                groups = [v for v in content if isinstance(v, dict) and "number" in v]

            for i, grp in enumerate(groups):
                verse_start = grp.get("number") or grp.get("verse")
                if verse_start is None:
                    continue
                verse_start = int(verse_start)

                if i + 1 < len(groups):
                    next_num = grp.get("number") or groups[i + 1].get("number") or groups[i + 1].get("verse")
                    verse_end = int(next_num) - 1 if next_num else verse_start
                    # Make sure verse_end is from the next group, not current
                    next_start = groups[i + 1].get("number") or groups[i + 1].get("verse")
                    verse_end = (int(next_start) - 1) if next_start else verse_start
                else:
                    verse_end = KJV_VERSE_COUNTS.get((book_int, chap), verse_start)

                raw_content = grp.get("content") or grp.get("text") or []
                if isinstance(raw_content, list):
                    text = "\n".join(str(c) for c in raw_content)
                else:
                    text = str(raw_content)
                # Strip HTML tags
                text = HTML_TAG.sub("", text).strip()

                if text:
                    con.execute(
                        "INSERT INTO commentary(book, chapter, verse_start, verse_end, author, text)"
                        " VALUES (?,?,?,?,?,?)",
                        (book_int, chap, verse_start, verse_end, "Matthew Henry", text),
                    )
                    total_rows += 1

            con.commit()
            chapters_done += 1

            if chapters_done % 50 == 0:
                print(f"  Progress: {chapters_done}/{total_chapters} chapters, {total_rows:,} rows …", flush=True)

            time.sleep(0.15)  # politeness delay — ~150ms between requests

    total = con.execute("SELECT COUNT(*) FROM commentary").fetchone()[0]
    print(f"  commentary: {total:,} rows (expected ~7,000–9,000 sections)", flush=True)
    con.close()


# ---------------------------------------------------------------------------
# Step 7 — bible_multi (all translations → bible_multi.db)
# ---------------------------------------------------------------------------

# Every entry: (display_name, scrollmapper_filename)
# All sourced from https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/sqlite/
TRANSLATION_SOURCES = [
    # Core English public-domain
    ("KJV",          "KJV.db"),
    ("KJVA",         "KJVA.db"),         # KJV with Apocrypha
    ("KJVPCE",       "KJVPCE.db"),       # Pure Cambridge Edition
    ("AKJV",         "AKJV.db"),         # Authorized KJV
    ("ASV",          "ASV.db"),          # American Standard Version (1901)
    ("YLT",          "YLT.db"),          # Young's Literal Translation (1898)
    ("Darby",        "Darby.db"),        # Darby Bible (1890)
    ("Geneva1599",   "Geneva1599.db"),   # Geneva Bible (1599)
    ("Webster",      "Webster.db"),      # Webster Bible (1833)
    ("BBE",          "BBE.db"),          # Bible in Basic English
    ("BSB",          "BSB.db"),          # Berean Standard Bible
    ("Jubilee2000",  "Jubilee2000.db"),  # Jubilee Bible 2000
    ("ACV",          "ACV.db"),          # A Conservative Version
    ("DRC",          "DRC.db"),          # Douay-Rheims Catholic (1899)
    ("CPDV",         "CPDV.db"),         # Catholic Public Domain Version
    ("Tyndale",      "Tyndale.db"),      # Tyndale Bible (1526)
    ("Wycliffe",     "Wycliffe.db"),     # Wycliffe Bible (1382)
    ("OEB",          "OEB.db"),          # Open English Bible
    ("LITV",         "LITV.db"),         # Literal Translation (Green)
    ("MKJV",         "MKJV.db"),         # Modern KJV (Green)
    ("RNKJV",        "RNKJV.db"),        # Restored Name KJV
    ("UKJV",         "UKJV.db"),         # Updated KJV
    ("RWebster",     "RWebster.db"),     # Revised Webster
    ("Rotherham",    "Rotherham.db"),    # Rotherham Emphasized Bible
    ("NHEB",         "NHEB.db"),         # New Heart English Bible
    ("LEB",          "LEB.db"),          # Lexham English Bible
    ("Anderson",     "Anderson.db"),     # Anderson NT
    ("Noyes",        "Noyes.db"),        # Noyes NT
    ("Haweis",       "Haweis.db"),       # Haweis NT
    ("Twenty",       "Twenty.db"),       # 20th Century NT
    # Scholarly originals
    ("JPS",          "JPS.db"),          # Jewish Publication Society (Hebrew OT)
    ("HebModern",    "HebModern.db"),    # Modern Hebrew Bible
    ("Vulgate",      "Vulgate.db"),      # Latin Vulgate (Jerome)
    ("VulgClementine", "VulgClementine.db"),
    ("Peshitta",     "Peshitta.db"),     # Aramaic Peshitta
    ("TR",           "TR.db"),           # Greek Textus Receptus
    ("Byz",          "Byz.db"),          # Greek Byzantine Majority Text
    # Other languages useful for research
    ("FreSynodale",  "FreSynodale1921.db"),  # French Synodale
    ("FreGeneve",    "FreGeneve1669.db"),     # French Geneva 1669
]

SCROLLMAPPER_BASE = (
    "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/sqlite/"
)


def _detect_verses_table(conn: sqlite3.Connection) -> tuple:
    """Return (table, book_col, chap_col, verse_col, text_col) or all-None on failure."""
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    for table in tables:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            book_col  = next((c for c in ("book_id", "b", "book", "bk")   if c in cols), None)
            chap_col  = next((c for c in ("chapter",  "c", "chap", "ch")  if c in cols), None)
            verse_col = next((c for c in ("verse",    "v", "vs",   "ver") if c in cols), None)
            text_col  = next((c for c in ("text",     "t", "verse_text", "vtext", "content") if c in cols), None)
            if book_col and chap_col and verse_col and text_col:
                return table, book_col, chap_col, verse_col, text_col
        except Exception:
            pass
    return None, None, None, None, None


def build_multi_translation() -> None:
    """Download all translations and merge into bible_multi.db verses(translation,b,c,v,t)."""
    out_path = DATA / "bible_multi.db"

    con = sqlite3.connect(str(out_path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS verses (
            translation TEXT NOT NULL,
            b           INTEGER NOT NULL,
            c           INTEGER NOT NULL,
            v           INTEGER NOT NULL,
            t           TEXT NOT NULL,
            PRIMARY KEY (translation, b, c, v)
        )
    """)
    con.commit()

    done = set(
        r[0] for r in con.execute("SELECT DISTINCT translation FROM verses").fetchall()
    )
    print(f"  multi: already have {len(done)} translations: {sorted(done)}", flush=True)

    imported = 0
    skipped  = 0
    failed   = []

    for display_name, filename in TRANSLATION_SOURCES:
        if display_name in done:
            print(f"  multi: {display_name} already present — skip", flush=True)
            skipped += 1
            continue

        tmp = DATA / f"_dl_{filename}"
        url = SCROLLMAPPER_BASE + filename
        try:
            print(f"  multi: downloading {display_name} ({filename}) …", flush=True)
            resp = requests.get(url, timeout=60, stream=True)
            if resp.status_code != 200:
                print(f"  multi: HTTP {resp.status_code} for {filename} — skip", flush=True)
                failed.append(display_name)
                continue
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(65536):
                    fh.write(chunk)
        except Exception as exc:
            print(f"  multi: download error {display_name}: {exc}", flush=True)
            failed.append(display_name)
            if tmp.exists():
                tmp.unlink()
            continue

        try:
            src = sqlite3.connect(str(tmp))
            table, bc, cc, vc, tc = _detect_verses_table(src)
            if not table:
                print(f"  multi: no recognisable verses table in {filename} — skip", flush=True)
                src.close()
                tmp.unlink()
                failed.append(display_name)
                continue

            rows = src.execute(
                f"SELECT {bc}, {cc}, {vc}, {tc} FROM {table} ORDER BY {bc},{cc},{vc}"
            ).fetchall()
            src.close()

            con.executemany(
                "INSERT OR IGNORE INTO verses(translation,b,c,v,t) VALUES(?,?,?,?,?)",
                [(display_name, r[0], r[1], r[2], r[3]) for r in rows],
            )
            con.commit()
            count = con.execute(
                "SELECT COUNT(*) FROM verses WHERE translation=?", (display_name,)
            ).fetchone()[0]
            print(f"  multi: {display_name}: {count:,} verses imported", flush=True)
            imported += 1
        except Exception as exc:
            print(f"  multi: import error {display_name}: {exc}", flush=True)
            failed.append(display_name)
        finally:
            if tmp.exists():
                tmp.unlink()

    total = con.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    trans_count = con.execute("SELECT COUNT(DISTINCT translation) FROM verses").fetchone()[0]
    con.close()

    print(
        f"  multi: done — {trans_count} translations, {total:,} total verses "
        f"(imported {imported} new, skipped {skipped}, failed {len(failed)})",
        flush=True,
    )
    if failed:
        print(f"  multi: failed translations: {failed}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60, flush=True)
    print("build_data.py — wn-bible-01 data build", flush=True)
    print(f"Data directory: {DATA}", flush=True)
    print("=" * 60, flush=True)

    DATA.mkdir(parents=True, exist_ok=True)

    steps = [
        ("kjv",               build_kjv),
        ("word_strongs",      build_word_strongs),
        ("cross_refs",        build_cross_refs),
        ("strongs",           build_strongs),
        ("interlinear",       build_interlinear),
        ("commentary",        build_commentary),
        ("multi_translation", build_multi_translation),
    ]

    results: dict[str, str] = {}
    for name, fn in steps:
        try:
            fn()
            results[name] = "OK"
        except Exception:
            print(f"\n[ERROR] Step '{name}' failed:\n{traceback.format_exc()}", flush=True)
            results[name] = "FAILED"

    print("\n" + "=" * 60, flush=True)
    print("Build summary:", flush=True)
    for name, status in results.items():
        print(f"  {name:20s} {status}", flush=True)
    print("=" * 60, flush=True)
    # Always exit 0 so the Docker build layer continues.
    sys.exit(0)


if __name__ == "__main__":
    main()

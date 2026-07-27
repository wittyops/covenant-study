FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] aiofiles jinja2 bcrypt lxml requests

# Download public domain Bible data at build time
RUN apt-get update && apt-get install -y wget unzip sqlite3 && rm -rf /var/lib/apt/lists/*

# Ensure /app/data exists before downloading
RUN mkdir -p /app/data

# scrollmapper/bible_databases — KJV text (repo reorganised 2024; new path)
# The new DB has 7 duplicate rows per verse; build_data.py deduplicates into t_kjv schema.
RUN wget -q https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/sqlite/KJV.db \
      -O /app/data/KJV_raw.db 2>/dev/null || true
# Cross-references — try new formats/sqlite/ path first, fall back to legacy sqlite/ path.
# build_data.py reads from the embedded cross_references table if shards are absent.
RUN wget -q https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/sqlite/cross_references.db \
      -O /app/data/cross_references.db 2>/dev/null || \
    wget -q https://github.com/scrollmapper/bible_databases/raw/master/sqlite/cross_references.db \
      -O /app/data/cross_references.db 2>/dev/null || true
# openscriptures/strongs — Hebrew and Greek lexicons (public domain)
RUN wget -q https://github.com/openscriptures/strongs/raw/master/hebrew/StrongsHebrewDictionary.xml \
      -O /app/data/strongs_hebrew.xml 2>/dev/null || true
RUN wget -q https://github.com/openscriptures/strongs/raw/master/greek/StrongsGreekDictionary.xml \
      -O /app/data/strongs_greek.xml 2>/dev/null || true
# STEPBible-Data — Translators Amalgamated Hebrew OT + Greek NT interlinear TSVs
# Source: https://github.com/tyndale/STEPBible-Data (CC BY 4.0)
RUN wget -q "https://raw.githubusercontent.com/tyndale/STEPBible-Data/master/TAHOT%20-%20Translators%20Amalgamated%20Hebrew%20OT/TAHOT%20Gen-Deu%20-%20STEPBible.org%20CC%20BY.txt" \
      -O /app/data/TAHOT_Gen-Deu.txt 2>/dev/null || true
RUN wget -q "https://raw.githubusercontent.com/tyndale/STEPBible-Data/master/TAHOT%20-%20Translators%20Amalgamated%20Hebrew%20OT/TAHOT%20Jos-Est%20-%20STEPBible.org%20CC%20BY.txt" \
      -O /app/data/TAHOT_Jos-Est.txt 2>/dev/null || true
RUN wget -q "https://raw.githubusercontent.com/tyndale/STEPBible-Data/master/TAHOT%20-%20Translators%20Amalgamated%20Hebrew%20OT/TAHOT%20Job-Sng%20-%20STEPBible.org%20CC%20BY.txt" \
      -O /app/data/TAHOT_Job-Sng.txt 2>/dev/null || true
RUN wget -q "https://raw.githubusercontent.com/tyndale/STEPBible-Data/master/TAHOT%20-%20Translators%20Amalgamated%20Hebrew%20OT/TAHOT%20Isa-Mal%20-%20STEPBible.org%20CC%20BY.txt" \
      -O /app/data/TAHOT_Isa-Mal.txt 2>/dev/null || true
RUN wget -q "https://raw.githubusercontent.com/tyndale/STEPBible-Data/master/TAGNT%20-%20Translators%20Amalgamated%20Greek%20NT/TAGNT%20Mat-Jhn%20-%20STEPBible.org%20CC%20BY.txt" \
      -O /app/data/TAGNT_Mat-Jhn.txt 2>/dev/null || true
RUN wget -q "https://raw.githubusercontent.com/tyndale/STEPBible-Data/master/TAGNT%20-%20Translators%20Amalgamated%20Greek%20NT/TAGNT%20Act-Rev%20-%20STEPBible.org%20CC%20BY.txt" \
      -O /app/data/TAGNT_Act-Rev.txt 2>/dev/null || true

# Run the data pipeline (idempotent — skips steps already complete)
COPY build_data.py /app/build_data.py
RUN python3 /app/build_data.py

# Copy application last so code changes don't invalidate the data build cache
COPY app.py /app/

# /app/notes preserved for legacy note migration at startup
VOLUME ["/app/notes"]
# /app/userdata is the ONLY volume-mounted path — users.db, sessions, bookmarks live here
# /app/data is NOT volume-mounted so the baked-in Bible DBs are always visible in the container
RUN mkdir -p /app/userdata
VOLUME ["/app/userdata"]

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

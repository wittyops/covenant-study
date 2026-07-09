FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] aiofiles jinja2

# Download public domain Bible data at build time
RUN apt-get update && apt-get install -y wget unzip sqlite3 && rm -rf /var/lib/apt/lists/*

# scrollmapper/bible_databases — KJV with Strong's cross-reference numbers (public domain)
RUN wget -q https://github.com/scrollmapper/bible_databases/raw/master/sqlite/t_kjv.db \
      -O /app/data/kjv.db 2>/dev/null || true
RUN wget -q https://github.com/scrollmapper/bible_databases/raw/master/sqlite/cross_references.db \
      -O /app/data/cross_references.db 2>/dev/null || true
# openscriptures/strongs — Hebrew and Greek lexicons (public domain)
RUN wget -q https://github.com/openscriptures/strongs/raw/master/hebrew/StrongsHebrewDictionary.xml \
      -O /app/data/strongs_hebrew.xml 2>/dev/null || true
RUN wget -q https://github.com/openscriptures/strongs/raw/master/greek/StrongsGreekDictionary.xml \
      -O /app/data/strongs_greek.xml 2>/dev/null || true

COPY app.py /app/

VOLUME ["/app/notes"]

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

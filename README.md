# Covenant Study

A self-hosted Bible study platform — built for depth. Strong's concordance, interlinear Hebrew/Greek, cross-references, biblical maps, verse highlights, study notes, and reading plans. Fully offline after the Docker image is built.

## Features

- **Scripture** — KJV + 30+ public-domain translations (ASV, YLT, Darby, Vulgate, and more), plus the Brenton English Septuagint (LXX)
- **Word tagging** — click any word to open its Strong's entry (Hebrew or Greek)
- **Interlinear** — original language with transliteration and morphology
- **Cross-references** — linked verse network drawn from scrollmapper's database
- **Biblical map** — 200+ geocoded locations with study notes (Leaflet.js, offline tiles optional)
- **Highlights** — 5 colours, persistent per user
- **Study notes** — per verse or chapter, saved to your account
- **Bookmarks** — coloured, labelled, navigable
- **Reading history** — pick up where you left off
- **Reading plans** — structured multi-day schedules
- **Study sessions** — save and restore reader state
- **Multi-user** — bcrypt auth, JWT sessions, admin role
- **Offline** — all Bible data baked into the Docker image at build time; no runtime network calls

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.12), Uvicorn, SQLite |
| Frontend | React 19, Vite 8 (Rolldown), Tailwind CSS v4, TanStack Query v5 |
| Linter | Biome 2.5.6 |
| Data | scrollmapper/bible_databases, STEPBible-Data (CC BY 4.0), openscriptures/strongs |
| Deploy | Docker multi-stage, Caddy reverse proxy, Cloudflare Tunnel |

## Quick Start (Standalone)

```bash
cp .env.example .env
# Edit .env — set ADMIN_PASSWORD before exposing to the network
docker compose -f compose.standalone.yml up -d
```

Then open `http://localhost:8000`. Register the first user — that user receives admin rights automatically.

> **Note:** The first `docker compose build` downloads ~100MB of Bible data from GitHub and processes it into SQLite. Subsequent builds use Docker layer cache and are fast.

## Development

### Backend (hot reload)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (hot reload with Vite proxy)

```bash
cd frontend
npm ci --legacy-peer-deps
npm run dev
```

Vite proxies `/api/*` and `/fragments/*` to the local FastAPI instance on port 8000.

### Lint + Build

```bash
cd frontend
npm run build
# Runs: biome check --diagnostic-level=error → tsc -b → vite build
```

## Deployment (Wittycomp Lab)

See [`infra/README.md`](infra/README.md) for lab-specific deployment (wn-bible-01, witty_vlan30, Caddy, CF tunnel).

## Data Sources

All Bible content is public domain or CC BY 4.0 and is downloaded at image build time.

| Source | Content | License |
|--------|---------|---------|
| [scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases) | KJV + 30+ translations | Public domain |
| Brenton English Septuagint (1844) | Septuagint (LXX) | Public domain |
| [tyndale/STEPBible-Data](https://github.com/tyndale/STEPBible-Data) | Hebrew OT + Greek NT interlinear | CC BY 4.0 |
| [openscriptures/strongs](https://github.com/openscriptures/strongs) | Strong's Hebrew + Greek lexicons | CC BY 4.0 / Public domain |

## Versioning

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- **MAJOR** — breaking API changes, auth scheme changes
- **MINOR** — new features (new panel, endpoint, translation)
- **PATCH** — bug fixes, dependency updates, accessibility improvements

See [CHANGELOG.md](CHANGELOG.md) for full history.

## License

Bible text data: public domain or CC BY 4.0 (see source repos above).
Application code: proprietary — Wittycomp Lab / Tony Thomas. All rights reserved.

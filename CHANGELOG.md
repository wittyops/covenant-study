# Changelog

All notable changes to Covenant Study are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Added
- Brenton English Septuagint (LXX, 1844) as a translation source, public domain

### Note
- FreLXXGiguet (French LXX) was added and then removed in the same window; it is not an available translation

## [3.1.0] — 2026-07-31

### Added
- Biome 2.5.6 linter + formatter wired into build pipeline (`biome check --diagnostic-level=error && tsc -b && vite build`)
- Word-level Strong's tagging in ChapterView via `/fragments/chapter/words` JSON endpoint
- Verse highlight overlay in ChapterView — colour fetched once per session, applied via CSS `color-mix()`
- Keyboard accessibility on scripture container (`onKeyDown` delegated handler, Enter/Space)
- `infra/` directory: Caddy block, DNS docs, deployment guide
- `.env.example` documenting all environment variables
- `CHANGELOG.md` and `README.md`
- Dedicated Forgejo repo (`covenant-study`) split from wittycomp-lab monorepo with full history

### Fixed
- Blank screen after login: React SPA was calling `/api/bible/*` but FastAPI backend only had `/api/verse` and `/api/books` — added 7 compat routes (`/api/bible/books`, `/api/bible/chapter`, `/api/bible/translations`, `/api/bible/strongs`, `/api/bible/crossrefs`, `/api/bible/interlinear`, `/api/bible/search`)
- Browser cache preventing redeploy visibility: `index.html` now served with `Cache-Control: no-cache, no-store, must-revalidate`
- Notes panel path mismatch: added `/api/notes/` plural alias (React used `/api/notes/`, backend had `/api/note/`)
- `noNonNullAssertion` on token in highlight/bookmark/history panels: `token!` → `token ?? ''`
- `noShadowRestrictedNames`: renamed lucide `Map` import to `MapIcon` (shadowed global `Map`)
- `useButtonType`: added `type="button"` to all raw `<button>` elements
- `noStaticElementInteractions`: scripture container `<div>` → `<section aria-label>` with `role` and keyboard handler
- `isNaN` → `Number.isNaN` in highlight map builder

## [3.0.0] — 2026-07-30

### Added
- Complete rewrite: React 19 + Vite 8.2 + Tailwind CSS v4 SPA replacing HTMX/Alpine.js stack
- FastAPI backend with modular route structure (`routes/bible.py`, `routes/auth.py`, etc.)
- Multi-stage Docker build: Node 22 (frontend build) → Python 3.12-slim (runtime)
- Multi-user authentication: JWT bearer tokens, bcrypt password hashing, admin role
- Strong's lexicon floating card (click tagged word to open, keyboard dismissal)
- Cross-reference panel
- Biblical map with 200+ geocoded locations (Leaflet.js)
- Verse highlights (5 colours, persistent per user)
- Study notes (per reference, PUT/GET)
- Bookmarks (coloured, with labels)
- Reading history
- Reading plans
- Saved study sessions
- Translation picker (KJV + 30+ public-domain translations)
- TanStack Query v5 for all data fetching (staleTime, enabled guards)
- Zustand stores for auth, reader state, UI

### Changed
- Frontend build: Vite 6 → 8.2 (Rolldown bundler)
- TypeScript: TS 5 → 7
- Zod: v3 → v4 (ESM-first)
- lucide-react: v0.x → v1.28

## [2.x] — 2026-07-28

### Added
- HTMX + Alpine.js frontend with server-side Jinja2 rendering
- FastAPI backend with interlinear, Strong's, and cross-reference support
- SQLite Bible data baked into Docker image at build time
- Scrollmapper KJV text, STEPBible-Data interlinear TSVs, openscriptures Strong's lexicons

## [1.x] — 2026-07-01

### Added
- Initial Flask-based Bible reader — KJV text, basic chapter navigation
- SQLite backend

---

[Unreleased]: https://git.wittycomp.com/bearboss/covenant-study/compare/v3.1.0...HEAD
[3.1.0]: https://git.wittycomp.com/bearboss/covenant-study/compare/v3.0.0...v3.1.0
[3.0.0]: https://git.wittycomp.com/bearboss/covenant-study/compare/v2.0.0...v3.0.0

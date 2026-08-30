# Changelog

All notable changes to Covenant Study are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Added
- Brenton English Septuagint (LXX, 1844) as a translation source, public domain
- Deuterocanonical / Apocrypha books (1–2 Esdras, Tobit, Judith, Rest of Esther, Wisdom, Sirach, Baruch, Song of the Three Holy Children, Susanna, Bel and the Dragon, Prayer of Manasses, 1–2 Maccabees) — book IDs 67–80, `config.APOCRYPHA_BOOKS`, third "Apocrypha" tab in `BookPicker.tsx`, `/api/bible/*` numeric-param routes raised from `le=66` to `le=80`
- **Verse range selection + the missing highlight/bookmark creation flow.** Tapping a verse *number* (as opposed to its text) now selects that verse for annotation; tapping a second, different verse number extends it into a range. A floating `SelectionActionBar` appears with 5 highlight colors, Bookmark, Note, and Clear. This is also the first time highlights and bookmarks could actually be *created* from the reading view at all — `HighlightsPanel`/`BookmarksPanel` only ever listed and deleted; the "Long-press a verse to highlight/bookmark it" hint text they showed described a gesture that was never implemented. See Fixed below.
  - `stores/reader.ts`: `selectionEnd` field + `selectVerseNumber()`/`clearSelection()` actions. Tapping verse *text* (unchanged) always collapses any pending range back to a single verse.
  - `components/reader/SelectionActionBar.tsx` (new): highlight applies to every verse in the range (one PUT per verse, reusing the existing single-verse `PUT /api/highlights/{ref}`); bookmark applies to the range's start verse only (a bookmark is a "return here" marker, not a colored span); note is disabled for a range and opens the existing single-verse `NotesPanel`.
  - `index.css`: `.verse-selected` (dashed outline) for pending selection, visually distinct from `.verse-highlighted` (a saved highlight).

### Fixed
- **KJVA book-numbering bug (data corruption, not just a missing feature).** KJVA (KJV with Apocrypha) was merged into `bible_multi.db` using the source's own `book_id` scheme, which inserts its 14 Apocrypha books at IDs 40–53 and shifts the entire NT to 54–80. The app's own numbering has no such gap (NT is 40–66, contiguous). Result: any request for `translation=KJVA` + a book number in our NT range silently returned the wrong text (e.g. book 40/Matthew returned 1 Esdras instead). Fixed both in the live `bible_multi.db` (one-time remap, done via a staged two-phase `UPDATE` to avoid transient `UNIQUE` constraint collisions — see `build_data.py::_KJVA_REMAP`) and in `build_data.py`'s import pipeline so a future image rebuild reproduces the fix instead of the bug.
- **Admin "Add User" 500.** The `wittycomp-lab` deployment copy of `routes/admin.py` had drifted to a stale version whose INSERT omitted `created_at` (`NOT NULL`, no default) — every create attempt threw `sqlite3.IntegrityError`. Canonical (this repo) already had the correct version; synced deployment to match.
- **`/api/places` response shape.** Had drifted to `{"places": [{name, lat, lng, notes}]}`; the frontend's `Place` type and `MapsPanel.tsx` expect a bare array of `{id, name, latitude, longitude, reference}`. This was the root cause of the "Maps are gone" report — reverted to match the frontend on both the unfiltered and `?ref=` branches of the handler.
- **Map links rendered place names in local script (Hebrew/Arabic), not English.** OpenStreetMap's default "Standard" layer has no per-URL English override. Switched `MapsPanel.tsx`'s `osmUrl()` to OSM's "Cycle Map" layer (`&layers=C`), which renders major place names in Latin/English script — confirmed against OSM's own layer switcher before picking it.

### Note
- FreLXXGiguet (French LXX) was added and then removed in the same window; it is not an available translation
- Brenton (LXX) had 0 rows in the pre-2026-08-30 production `bible_multi.db` — its per-chapter fetch (`build_lxx()`) had never completed there, though the fetch logic itself was correct. The `docker compose build --no-cache` run that shipped the Apocrypha/KJVA-remap fix (this entry) also happened to complete the Brenton fetch successfully — `lxx_brenton: true` in `/api/health` as of this deploy. LXX is Old-Testament-only by nature (Genesis–Malachi, books 1–39) and does not cover the Apocrypha books (67–80); KJVA remains the source for those.

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

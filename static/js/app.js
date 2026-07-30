/**
 * app.js — Covenant Study client application
 *
 * ARCHITECTURE
 * ────────────
 * Three Alpine.js stores hold all shared reactive state.  Alpine's reactivity
 * system updates the DOM automatically when store values change — no manual
 * querySelector/innerHTML needed for state-driven UI.
 *
 * Stores
 *   auth   — session token, current user object, login/logout, register
 *   reader — current book / chapter / translation; word click handler; verse menu
 *   ui     — which panels are open, toast queue, search overlay, nav picker
 *
 * Everything that loads or renders Bible content (chapter text, Strong's cards,
 * search results, cross-refs, interlinear) is handled by htmx fragment endpoints
 * on the server.  This file only manages:
 *   - Auth flows (login, register, logout)
 *   - Bookmarks, notes, highlights, history (user data via JSON API)
 *   - Study sessions (save / restore reading position)
 *   - Reading plan progress (progress tracking)
 *   - The Leaflet map (no htmx alternative for interactive maps)
 *   - Toast notifications
 *   - Clipboard / share actions
 *
 * DEPENDENCIES
 * ────────────
 *   Alpine.js 3.x  (loaded BEFORE this file in index.html — defer attribute)
 *   htmx 2.x       (declarative server requests, loaded separately)
 *   Leaflet 1.9.x  (map, loaded separately)
 *
 * CONVENTIONS
 * ────────────
 *   - Functions prefixed _  are private to this module; not called from HTML.
 *   - All fetch calls go through authFetch() so the Authorization header is
 *     included automatically without repeating it everywhere.
 *   - Error boundaries: every async function catches and routes to ui.toast().
 *
 * FILE LAYOUT
 * ────────────
 *   §1  Constants
 *   §2  Alpine.store — auth
 *   §3  Alpine.store — reader
 *   §4  Alpine.store — ui
 *   §5  Alpine component — bookmarks panel
 *   §6  Alpine component — notes panel
 *   §7  Alpine component — highlights panel
 *   §8  Alpine component — history panel
 *   §9  Alpine component — sessions panel
 *   §10 Alpine component — reading plans panel
 *   §11 Alpine component — admin panel
 *   §12 Leaflet map initialisation
 *   §13 htmx event hooks
 *   §14 Boot
 */

'use strict';

// ===========================================================================
// §1  CONSTANTS
// ===========================================================================

/** Storage key for the auth token in localStorage. */
const TOKEN_KEY = 'covenant_token';

/** Storage key for last reading position in localStorage. */
const POS_KEY = 'covenant_pos';

/**
 * Base function for all authenticated API calls.
 * Reads the current token from the auth store and injects it as a
 * Bearer header so every caller stays concise.
 *
 * @param {string} url
 * @param {RequestInit} opts
 * @returns {Promise<Response>}
 */
function authFetch(url, opts = {}) {
  const token = Alpine.store('auth').token;
  return fetch(url, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.body && typeof opts.body === 'string'
        ? { 'Content-Type': 'application/json' }
        : {}),
    },
  });
}

// ===========================================================================
// §2  ALPINE.STORE — auth
// ===========================================================================

/**
 * auth store — session token and current user identity.
 *
 * On startup Alpine calls init(), which checks localStorage for a saved
 * token and validates it with the /api/auth/me endpoint.  If valid, the
 * user object is populated and the app shell renders; otherwise the login
 * screen appears (controlled by x-show in index.html).
 */
document.addEventListener('alpine:init', () => {

  Alpine.store('auth', {
    /** Populated user object from /api/auth/me, or null when logged out. */
    user:    null,
    /** The raw session token string (Bearer token). */
    token:   null,
    /** True while a login/register request is in flight. */
    loading: false,
    /** Server-side error message from the last failed request. */
    error:   null,

    /**
     * init() is called by Alpine automatically when the store is created.
     * Restores the previous session from localStorage if the token is still valid.
     */
    async init() {
      const saved = localStorage.getItem(TOKEN_KEY);
      if (!saved) return;
      this.token = saved;
      try {
        const r = await authFetch('/api/auth/me');
        if (r.ok) {
          this.user = await r.json();
          // Kick off the initial chapter load now that we have a user.
          await Alpine.store('reader').boot();
        } else {
          // Token expired or revoked — clear it and show login.
          this._clear();
        }
      } catch {
        this._clear();
      }
    },

    /**
     * Submit login credentials.
     * @param {HTMLFormElement} formEl — the <form> element from the template
     */
    async login(formEl) {
      this.loading = true;
      this.error   = null;
      const data   = Object.fromEntries(new FormData(formEl));
      try {
        const r = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ username: data.username, password: data.password }),
        });
        const j = await r.json().catch(() => ({}));
        if (r.ok) {
          this.token = j.token;
          this.user  = j.user;
          localStorage.setItem(TOKEN_KEY, j.token);
          await Alpine.store('reader').boot();
        } else {
          this.error = j.detail || 'Login failed.  Check your username and password.';
        }
      } catch {
        this.error = 'Network error.  Please try again.';
      } finally {
        this.loading = false;
      }
    },

    /**
     * Submit a new account registration.
     * @param {HTMLFormElement} formEl
     */
    async register(formEl) {
      this.loading = true;
      this.error   = null;
      const data   = Object.fromEntries(new FormData(formEl));
      try {
        const r = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            username:     data.username,
            password:     data.password,
            display_name: data.display_name || data.username,
          }),
        });
        const j = await r.json().catch(() => ({}));
        if (r.ok) {
          this.token = j.token;
          this.user  = j.user;
          localStorage.setItem(TOKEN_KEY, j.token);
          await Alpine.store('reader').boot();
        } else {
          this.error = j.detail || 'Registration failed.';
        }
      } catch {
        this.error = 'Network error.  Please try again.';
      } finally {
        this.loading = false;
      }
    },

    /** Sign out: revoke token on the server, clear local state. */
    async logout() {
      await authFetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
      this._clear();
    },

    /** Wipe local auth state (called on logout or expired token). */
    _clear() {
      this.user  = null;
      this.token = null;
      localStorage.removeItem(TOKEN_KEY);
    },

    /** Convenience getter — true when the current user has the admin role. */
    get isAdmin() { return this.user?.role === 'admin'; },

    /** Convenience getter — the user's display name with a fallback. */
    get displayName() { return this.user?.display_name || this.user?.username || '…'; },
  });


  // =========================================================================
  // §3  ALPINE.STORE — reader
  // =========================================================================

  /**
   * reader store — current reading position and verse interactions.
   *
   * The reading position (book + chapter + translation) is mirrored into
   * three hidden <input> elements in the HTML (Alpine :value bindings).
   * htmx reads those inputs via hx-include="[name='book'],...", so when
   * Alpine updates the store the next htmx trigger automatically sends the
   * correct values without any glue code.
   *
   * Chapter content is loaded by dispatching "chapter-change" on document.body.
   * The #chapter-display element listens for that event (hx-trigger in HTML).
   */
  Alpine.store('reader', {
    book:        'Genesis',
    chapter:     1,
    verse:       null,     // currently highlighted verse number (or null)
    translation: 'KJV',

    /** All translations available in the loaded database. */
    translations: ['KJV'],

    /** Whether the verse context menu is visible. */
    verseMenuOpen: false,
    verseMenuRef:  null,   // e.g. "John 3:16"
    verseMenuX:    0,
    verseMenuY:    0,

    /**
     * Called once after login/session-restore.
     * Loads saved position, available translations, then triggers first chapter load.
     */
    async boot() {
      try {
        const saved = JSON.parse(localStorage.getItem(POS_KEY) || '{}');
        if (saved.book)        this.book        = saved.book;
        if (saved.chapter)     this.chapter     = Number(saved.chapter) || 1;
        if (saved.translation) this.translation = saved.translation;
      } catch { /* ignore corrupt storage */ }

      await this._loadTranslations();
      await Alpine.store('ui').loadBookmarks();
      await Alpine.store('ui').loadHighlights();
      this._triggerChapterLoad();
    },

    /**
     * Navigate to a new book (always starts at chapter 1).
     * @param {string} book — canonical book name, e.g. "Genesis"
     */
    setBook(book) {
      this.book    = book;
      this.chapter = 1;
      this.verse   = null;
      this._save();
      this._triggerChapterLoad();
    },

    /**
     * Navigate to a specific chapter in the current book.
     * @param {number} chapter
     */
    setChapter(chapter) {
      this.chapter = chapter;
      this.verse   = null;
      this._save();
      this._triggerChapterLoad();
    },

    /**
     * Change the active translation and reload the current chapter.
     * @param {string} translation — e.g. "ASV", "YLT"
     */
    setTranslation(translation) {
      this.translation = translation;
      this._save();
      this._triggerChapterLoad();
    },

    /**
     * Dispatch the htmx trigger that reloads #chapter-display.
     * The hidden <input> values are already updated by Alpine before this runs,
     * so htmx will read the correct book/chapter/translation when it fires.
     */
    _triggerChapterLoad() {
      document.body.dispatchEvent(new CustomEvent('chapter-change'));
    },

    /**
     * Event delegation handler for word clicks inside #chapter-display.
     * Attached via @click on the container element so only ONE listener exists
     * regardless of how many tagged words are on the page.
     *
     * When a .tagged word is clicked, loads its Strong's entry into
     * #strongs-panel via htmx.ajax() and opens the strongs tool panel.
     *
     * @param {MouseEvent} event
     */
    handleWordClick(event) {
      const word = event.target.closest('[data-strongs]');
      if (!word) return;
      const num = word.dataset.strongs;
      htmx.ajax('GET', `/fragments/strongs/${encodeURIComponent(num)}`, '#strongs-panel');
      Alpine.store('ui').openPanel('strongs');
    },

    /**
     * Programmatically open the Strong's panel for a known number.
     * Called from interlinear table buttons.
     * @param {string} num — e.g. "H7225"
     */
    openStrongs(num) {
      htmx.ajax('GET', `/fragments/strongs/${encodeURIComponent(num)}`, '#strongs-panel');
      Alpine.store('ui').openPanel('strongs');
    },

    /**
     * Show the right-click verse context menu.
     * @param {MouseEvent} event
     * @param {string}     ref   — e.g. "Genesis 1:1"
     */
    showVerseMenu(event, ref) {
      this.verseMenuRef  = ref;
      this.verseMenuX    = event.clientX;
      this.verseMenuY    = event.clientY;
      this.verseMenuOpen = true;
    },

    closeVerseMenu() { this.verseMenuOpen = false; },

    /**
     * Copy the verse text + reference to the clipboard.
     * Called from the verse context menu.
     * @param {string} ref — e.g. "John 3:16"
     */
    async copyVerse(ref) {
      try {
        const r = await fetch(
          `/api/verse?ref=${encodeURIComponent(ref)}&translation=${this.translation}`
        );
        const j = await r.json();
        const text = (j.verses || []).map(v => `${ref} (${this.translation}) — ${v.text}`).join('\n');
        await navigator.clipboard.writeText(text);
        Alpine.store('ui').toast('Verse copied!', 'success');
      } catch {
        Alpine.store('ui').toast('Could not copy verse.', 'error');
      }
      this.closeVerseMenu();
    },

    /**
     * Share a verse via the Web Share API, falling back to clipboard copy.
     * @param {string} ref
     */
    async shareVerse(ref) {
      try {
        const r = await fetch(
          `/api/verse?ref=${encodeURIComponent(ref)}&translation=${this.translation}`
        );
        const j = await r.json();
        const text = (j.verses || []).map(v => `${ref} — ${v.text}`).join('\n');
        if (navigator.share) {
          await navigator.share({ title: ref, text });
        } else {
          await navigator.clipboard.writeText(text);
          Alpine.store('ui').toast('Verse copied to clipboard!', 'info');
        }
      } catch (e) {
        if (e.name !== 'AbortError') {
          Alpine.store('ui').toast('Share failed.', 'error');
        }
      }
      this.closeVerseMenu();
    },

    /** Log a verse visit to reading history. */
    async logHistory(ref) {
      await authFetch('/api/history', {
        method: 'POST',
        body:   JSON.stringify({ ref }),
      }).catch(() => {});
    },

    async _loadTranslations() {
      try {
        const r = await fetch('/api/translations');
        const j = await r.json();
        this.translations = j.translations || ['KJV'];
      } catch { /* keep default */ }
    },

    /** Persist reading position to localStorage for next session. */
    _save() {
      localStorage.setItem(POS_KEY, JSON.stringify({
        book: this.book, chapter: this.chapter, translation: this.translation,
      }));
    },

    /** Current chapter reference string, e.g. "Genesis 1". */
    get ref() { return `${this.book} ${this.chapter}`; },
  });


  // =========================================================================
  // §4  ALPINE.STORE — ui
  // =========================================================================

  /**
   * ui store — all UI state that isn't reader position or auth.
   *
   * The "active panel" pattern: only one tool panel is visible at a time.
   * Opening a panel sets activePanel to a name string; closing it sets null.
   * index.html uses x-show="$store.ui.activePanel === 'strongs'" etc.
   *
   * Bookmarks and highlights are stored here (not in reader) because they
   * need to survive chapter navigation and need to be readable from multiple
   * template locations.
   */
  Alpine.store('ui', {
    /** Which sidebar tool panel is open. One of:
     *  'strongs' | 'crossrefs' | 'interlinear' | 'commentary' |
     *  'notes'   | 'bookmarks' | 'history'     | 'sessions'   |
     *  'plans'   | 'map'       | 'admin'        | null (none)
     */
    activePanel:   null,
    sidebarOpen:   false,
    searchOpen:    false,
    userMenuOpen:  false,
    navPickerOpen: false,

    /** Accumulated toast notifications rendered via x-for in index.html. */
    toasts: [],

    /** Bookmark refs for the current user (Set for O(1) lookup). */
    bookmarkRefs: new Set(),

    /** Full bookmark objects for the bookmarks panel. */
    bookmarks: [],

    /** Highlight map: ref → color (for applying CSS classes to verses). */
    highlights: {},

    // ── Sidebar / panels ──────────────────────────────────────────────────

    toggleSidebar() { this.sidebarOpen = !this.sidebarOpen; },
    closeSidebar()  { this.sidebarOpen = false; },

    openPanel(name) {
      this.activePanel = this.activePanel === name ? null : name;
    },
    closePanel() { this.activePanel = null; },

    // ── Search ────────────────────────────────────────────────────────────

    openSearch()  { this.searchOpen = true; },
    closeSearch() { this.searchOpen = false; },

    // ── User menu ─────────────────────────────────────────────────────────

    toggleUserMenu() { this.userMenuOpen = !this.userMenuOpen; },
    closeUserMenu()  { this.userMenuOpen = false; },

    // ── Nav / chapter picker ──────────────────────────────────────────────

    openNavPicker()  { this.navPickerOpen = true; },
    closeNavPicker() { this.navPickerOpen = false; },

    // ── Toasts ────────────────────────────────────────────────────────────

    /**
     * Show a toast notification that auto-dismisses after `ms` milliseconds.
     * @param {string} message
     * @param {'info'|'success'|'error'|'warning'} type
     * @param {number} ms
     */
    toast(message, type = 'info', ms = 3500) {
      const id = Date.now() + Math.random();
      this.toasts.push({ id, message, type });
      setTimeout(() => {
        const idx = this.toasts.findIndex(t => t.id === id);
        if (idx >= 0) this.toasts.splice(idx, 1);
      }, ms);
    },

    dismissToast(id) {
      const idx = this.toasts.findIndex(t => t.id === id);
      if (idx >= 0) this.toasts.splice(idx, 1);
    },

    // ── Close everything (Escape key) ─────────────────────────────────────

    closeAll() {
      this.searchOpen    = false;
      this.userMenuOpen  = false;
      this.navPickerOpen = false;
      this.activePanel   = null;
      Alpine.store('reader').closeVerseMenu();
    },

    // ── Bookmarks ─────────────────────────────────────────────────────────

    /** Load all bookmarks for the current user into local state. */
    async loadBookmarks() {
      try {
        const r = await authFetch('/api/bookmarks');
        if (!r.ok) return;
        const j = await r.json();
        this.bookmarks    = j;
        this.bookmarkRefs = new Set(j.map(b => b.ref));
      } catch { /* silently skip — bookmarks are non-critical */ }
    },

    /** Toggle a bookmark for a verse ref.  Optimistically updates local state. */
    async toggleBookmark(ref) {
      const had = this.bookmarkRefs.has(ref);
      if (had) {
        // Find the bookmark ID.
        const bm = this.bookmarks.find(b => b.ref === ref);
        if (!bm) return;
        this.bookmarkRefs.delete(ref);
        this.bookmarks = this.bookmarks.filter(b => b.ref !== ref);
        const r = await authFetch(`/api/bookmarks/${bm.id}`, { method: 'DELETE' });
        if (!r.ok) {
          // Roll back on failure.
          this.bookmarkRefs.add(ref);
          this.bookmarks.push(bm);
          this.toast('Could not remove bookmark.', 'error');
        }
      } else {
        // Optimistically add.
        const temp = { id: null, ref, label: '', color: '#b8962e' };
        this.bookmarkRefs.add(ref);
        this.bookmarks.push(temp);
        const r = await authFetch('/api/bookmarks', {
          method: 'POST',
          body:   JSON.stringify({ ref }),
        });
        if (r.ok) {
          const j = await r.json();
          // Replace temporary entry with real server data.
          const idx = this.bookmarks.findIndex(b => b.ref === ref && b.id === null);
          if (idx >= 0) this.bookmarks[idx] = j;
        } else {
          this.bookmarkRefs.delete(ref);
          this.bookmarks = this.bookmarks.filter(b => !(b.ref === ref && b.id === null));
          this.toast('Could not save bookmark.', 'error');
        }
      }
    },

    isBookmarked(ref) { return this.bookmarkRefs.has(ref); },

    // ── Highlights ────────────────────────────────────────────────────────

    /** Load all highlights for the current user. */
    async loadHighlights() {
      try {
        const r = await authFetch('/api/highlights');
        if (!r.ok) return;
        const j = await r.json();
        this.highlights = Object.fromEntries(j.map(h => [h.ref, h.color]));
      } catch { /* non-critical */ }
    },

    /** Set or clear a highlight for a verse. */
    async setHighlight(ref, color) {
      if (!color) {
        await authFetch(`/api/highlights/${encodeURIComponent(ref)}`, { method: 'DELETE' });
        delete this.highlights[ref];
      } else {
        await authFetch('/api/highlights', {
          method: 'POST',
          body:   JSON.stringify({ ref, color }),
        });
        this.highlights[ref] = color;
      }
    },

    highlightColor(ref) { return this.highlights[ref] || null; },
  });

});  // end alpine:init


// ===========================================================================
// §5  ALPINE COMPONENT — bookmarks panel
// ===========================================================================

/**
 * Attached to the bookmarks panel element via x-data="bookmarksPanel()".
 * Reads its list from $store.ui.bookmarks so the data is shared with the
 * bookmark icon in the header.
 */
function bookmarksPanel() {
  return {
    /** Navigate to a bookmarked reference and close the panel. */
    navigate(ref) {
      const m = ref.match(/^(.*?)\s+(\d+)(?::(\d+))?$/);
      if (!m) return;
      Alpine.store('reader').setBook(m[1]);
      if (m[2]) Alpine.store('reader').setChapter(Number(m[2]));
      Alpine.store('ui').closePanel();
    },

    /** Remove a bookmark by ref. */
    async remove(ref) {
      await Alpine.store('ui').toggleBookmark(ref);
    },

    get bookmarks() { return Alpine.store('ui').bookmarks; },
  };
}


// ===========================================================================
// §6  ALPINE COMPONENT — notes panel
// ===========================================================================

/**
 * Attached to the notes panel via x-data="notesPanel()".
 * The note is tied to the current verse ref (reader.verse) or chapter.
 */
function notesPanel() {
  return {
    body:    '',
    saving:  false,
    dirty:   false,
    ref:     '',

    async init() {
      this.ref = Alpine.store('reader').verseMenuRef
              || Alpine.store('reader').ref;
      await this.load();
    },

    async load() {
      try {
        const r = await authFetch(`/api/note/${encodeURIComponent(this.ref)}`);
        if (r.ok) {
          const j = await r.json();
          this.body = j.body || '';
        }
      } catch { /* no note yet */ }
      this.dirty = false;
    },

    async save() {
      this.saving = true;
      try {
        const r = await authFetch(`/api/note/${encodeURIComponent(this.ref)}`, {
          method: 'POST',
          body:   JSON.stringify({ body: this.body }),
        });
        if (r.ok) {
          Alpine.store('ui').toast('Note saved.', 'success');
          this.dirty = false;
        } else {
          Alpine.store('ui').toast('Could not save note.', 'error');
        }
      } finally {
        this.saving = false;
      }
    },
  };
}


// ===========================================================================
// §7  ALPINE COMPONENT — highlights panel
// ===========================================================================

/**
 * Attached to the highlights panel via x-data="highlightsPanel()".
 * Colour swatches let the user apply or clear a highlight on the context-menu ref.
 */
function highlightsPanel() {
  const COLORS = [
    { name: 'yellow',  hex: '#ffeb3b' },
    { name: 'green',   hex: '#a5d6a7' },
    { name: 'blue',    hex: '#90caf9' },
    { name: 'pink',    hex: '#f48fb1' },
    { name: 'orange',  hex: '#ffcc80' },
    { name: 'purple',  hex: '#ce93d8' },
  ];

  return {
    colors: COLORS,
    ref:    '',

    init() {
      this.ref = Alpine.store('reader').verseMenuRef || Alpine.store('reader').ref;
    },

    currentColor() {
      return Alpine.store('ui').highlightColor(this.ref);
    },

    async apply(hex) {
      await Alpine.store('ui').setHighlight(this.ref, hex);
      Alpine.store('ui').toast('Highlight applied.', 'success');
    },

    async clear() {
      await Alpine.store('ui').setHighlight(this.ref, null);
      Alpine.store('ui').toast('Highlight cleared.', 'info');
    },
  };
}


// ===========================================================================
// §8  ALPINE COMPONENT — history panel
// ===========================================================================

function historyPanel() {
  return {
    entries: [],
    loading: false,

    async init() { await this.load(); },

    async load() {
      this.loading = true;
      try {
        const r = await authFetch('/api/history');
        if (r.ok) this.entries = await r.json();
      } catch {
        Alpine.store('ui').toast('Could not load history.', 'error');
      } finally {
        this.loading = false;
      }
    },

    navigate(ref) {
      const m = ref.match(/^(.*?)\s+(\d+)/);
      if (!m) return;
      Alpine.store('reader').setBook(m[1]);
      Alpine.store('reader').setChapter(Number(m[2]));
      Alpine.store('ui').closePanel();
    },

    /** Format a Unix timestamp as a relative human-readable string. */
    relTime(unix) {
      const diff = Math.floor((Date.now() / 1000) - unix);
      if (diff < 60)   return 'just now';
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
      return `${Math.floor(diff / 86400)}d ago`;
    },
  };
}


// ===========================================================================
// §9  ALPINE COMPONENT — sessions panel
// ===========================================================================

/**
 * Study sessions let users save and restore named reading positions
 * (with any associated state stored as JSON on the server).
 */
function sessionsPanel() {
  return {
    sessions: [],
    newName:  '',
    loading:  false,
    saving:   false,

    async init() { await this.load(); },

    async load() {
      this.loading = true;
      try {
        const r = await authFetch('/api/sessions');
        if (r.ok) this.sessions = await r.json();
      } catch {
        Alpine.store('ui').toast('Could not load sessions.', 'error');
      } finally {
        this.loading = false;
      }
    },

    async save() {
      if (!this.newName.trim()) return;
      this.saving = true;
      const reader = Alpine.store('reader');
      const state  = {
        book: reader.book, chapter: reader.chapter, translation: reader.translation,
      };
      try {
        const r = await authFetch('/api/sessions', {
          method: 'POST',
          body:   JSON.stringify({ name: this.newName.trim(), state_json: JSON.stringify(state) }),
        });
        if (r.ok) {
          this.newName = '';
          await this.load();
          Alpine.store('ui').toast('Session saved.', 'success');
        }
      } finally {
        this.saving = false;
      }
    },

    async resume(session) {
      try {
        const state = JSON.parse(session.state_json || '{}');
        if (state.book)        Alpine.store('reader').setBook(state.book);
        if (state.chapter)     Alpine.store('reader').setChapter(Number(state.chapter));
        if (state.translation) Alpine.store('reader').setTranslation(state.translation);
        Alpine.store('ui').closePanel();
        Alpine.store('ui').toast(`Resumed "${session.name}".`, 'info');
      } catch {
        Alpine.store('ui').toast('Could not restore session.', 'error');
      }
    },

    async remove(id) {
      await authFetch(`/api/sessions/${id}`, { method: 'DELETE' });
      this.sessions = this.sessions.filter(s => s.id !== id);
    },
  };
}


// ===========================================================================
// §10  ALPINE COMPONENT — reading plans panel
// ===========================================================================

function plansPanel() {
  return {
    plans:    [],
    progress: [],
    loading:  false,

    async init() { await this.load(); },

    async load() {
      this.loading = true;
      try {
        const [pr, pp] = await Promise.all([
          authFetch('/api/reading-plans').then(r => r.json()),
          authFetch('/api/reading-plans/progress').then(r => r.json()),
        ]);
        this.plans    = pr || [];
        this.progress = pp || [];
      } catch {
        Alpine.store('ui').toast('Could not load reading plans.', 'error');
      } finally {
        this.loading = false;
      }
    },

    /** Return progress for a plan, or null if not started. */
    getProgress(planId) {
      return this.progress.find(p => p.plan_id === planId) || null;
    },

    /** Advance to the next day in a reading plan. */
    async advance(planId) {
      const p    = this.getProgress(planId);
      const next = (p ? p.day_index : 0) + 1;
      const r = await authFetch('/api/reading-plans/progress', {
        method: 'POST',
        body:   JSON.stringify({ plan_id: planId, day_index: next }),
      });
      if (r.ok) {
        await this.load();
        Alpine.store('ui').toast('Progress updated!', 'success');
      }
    },

    /** Restart a plan from day 0. */
    async reset(planId) {
      await authFetch(`/api/reading-plans/progress/${encodeURIComponent(planId)}`, {
        method: 'DELETE',
      });
      await this.load();
      Alpine.store('ui').toast('Plan reset.', 'info');
    },
  };
}


// ===========================================================================
// §11  ALPINE COMPONENT — admin panel
// ===========================================================================

function adminPanel() {
  return {
    users:   [],
    loading: false,

    async init() { await this.load(); },

    async load() {
      this.loading = true;
      try {
        const r = await authFetch('/api/admin/users');
        if (r.ok) this.users = await r.json();
        else Alpine.store('ui').toast('Admin access denied.', 'error');
      } catch {
        Alpine.store('ui').toast('Could not load users.', 'error');
      } finally {
        this.loading = false;
      }
    },

    /**
     * Prompt for a new password and POST it to the server.
     * Using prompt() here is acceptable for an admin-only panel where
     * the audience is technical staff, not general public users.
     * @param {{id: number, username: string}} user
     */
    async resetPassword(user) {
      const pw = window.prompt(
        `Set a new password for "${user.username}" (min 8 characters):`
      );
      if (!pw || pw.length < 8) {
        if (pw !== null) Alpine.store('ui').toast('Password must be at least 8 characters.', 'error');
        return;
      }
      const r = await authFetch(`/api/admin/users/${user.id}/reset-password`, {
        method: 'POST',
        body:   JSON.stringify({ password: pw }),
      });
      if (r.ok) {
        Alpine.store('ui').toast(`Password reset for ${user.username}.`, 'success');
      } else {
        Alpine.store('ui').toast('Password reset failed.', 'error');
      }
    },
  };
}


// ===========================================================================
// §12  LEAFLET MAP INITIALISATION
// ===========================================================================

/**
 * Initialise the Leaflet map and populate it with biblical place markers.
 *
 * Called once when the user opens the Map panel (x-init on the panel div).
 * Leaflet requires the container to be visible before initialising, which
 * is why this is deferred rather than run at startup.
 *
 * The `window._mapInitialised` guard prevents double-init if the user
 * opens and closes the panel multiple times.
 */
async function initMap() {
  if (window._mapInitialised) return;
  window._mapInitialised = true;

  // Ensure the map container div is in the DOM and visible.
  const container = document.getElementById('map-container');
  if (!container) {
    console.error('[Covenant/map] #map-container not found.');
    return;
  }

  const map = L.map('map-container').setView([31.7683, 35.2137], 7);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(map);

  // Fetch biblical places from the API and add a popup marker for each.
  try {
    const r = await fetch('/api/places');
    const j = await r.json();
    const places = j.places || [];
    places.forEach(place => {
      if (place.lat == null || place.lng == null) return;
      const marker = L.marker([place.lat, place.lng]);
      marker.bindPopup(`
        <strong>${place.name}</strong>
        ${place.description ? `<br><small>${place.description}</small>` : ''}
        ${place.references  ? `<br><em>${place.references}</em>`  : ''}
      `);
      marker.addTo(map);
    });
  } catch (e) {
    console.error('[Covenant/map] Could not load places:', e);
  }

  // Fix the tile size after the container becomes visible — Leaflet sometimes
  // miscalculates dimensions when the parent was hidden during init.
  setTimeout(() => map.invalidateSize(), 100);
}


// ===========================================================================
// §13  HTMX EVENT HOOKS
// ===========================================================================

/**
 * htmx fires "htmx:afterSwap" after every DOM swap.
 * We use it to re-apply highlight colours whenever the chapter display
 * is refreshed, because the new HTML doesn't carry the inline styles —
 * those are applied dynamically by this function.
 */
document.addEventListener('htmx:afterSwap', function (event) {
  const target = event.detail.target;
  if (!target || target.id !== 'chapter-display') return;

  // Apply highlight colours to verse elements in the freshly swapped chapter.
  const highlights = Alpine.store('ui').highlights;
  if (!highlights) return;

  Object.entries(highlights).forEach(([ref, color]) => {
    const verseEl = target.querySelector(`[data-ref="${CSS.escape(ref)}"]`);
    if (verseEl) {
      verseEl.style.setProperty('--highlight-color', color);
      verseEl.classList.add('highlighted');
    }
  });

  // Log the newly loaded chapter to reading history.
  const chEl = target.querySelector('.chapter-display');
  if (chEl) {
    const b = chEl.dataset.book;
    const c = chEl.dataset.chapter;
    if (b && c) Alpine.store('reader').logHistory(`${b} ${c}`);
  }
});


// ===========================================================================
// §14  BOOT
// ===========================================================================

/**
 * Register all Alpine.js component factories on window so index.html can
 * reference them as x-data="bookmarksPanel()" etc.
 *
 * This runs synchronously — before Alpine initialises — so the functions
 * are available when Alpine processes x-data attributes on startup.
 */
Object.assign(window, {
  bookmarksPanel,
  notesPanel,
  highlightsPanel,
  historyPanel,
  sessionsPanel,
  plansPanel,
  adminPanel,
  initMap,
});

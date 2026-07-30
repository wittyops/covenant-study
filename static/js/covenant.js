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
  const chip = document.querySelector('#user-chip');
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
  const userChip = document.querySelector('#user-chip');
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
  highlights:     {},
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

  // Apply stored highlights to newly-rendered verse rows
  applyHighlights();

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

  // Lazy-load plans and highlights on first open
  if (tabName === 'plans') loadReadingPlans();
  if (tabName === 'highlights') renderHighlightsList();

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

// ── 12. HIGHLIGHTS ──────────────────────────────────────────────────────────

const HL_HEX = { yellow:'#ffeb3b', green:'#66bb6a', blue:'#42a5f5', pink:'#f06292', purple:'#ab47bc' };
const HL_HEX_INV = Object.fromEntries(Object.entries(HL_HEX).map(([k,v])=>[v,k]));

// Apply stored highlights to verse rows in the current chapter
function applyHighlights() {
  const rows = $$('.verse-row[data-verse]');
  for (const row of rows) {
    const verseNum = row.getAttribute('data-verse');
    const ref = `${state.currentBook} ${state.currentChapter}:${verseNum}`;
    const color = state.highlights[ref];
    if (color) {
      row.setAttribute('data-hl', color);
    } else {
      row.removeAttribute('data-hl');
    }
  }
}

async function loadHighlights() {
  try {
    const data = await apiFetch('/api/highlights');
    state.highlights = {};
    for (const h of (data || [])) {
      const colorName = HL_HEX_INV[h.color] || h.color;
      state.highlights[h.ref] = colorName;
    }
    applyHighlights();
    renderHighlightsList();
  } catch (_) { /* not logged in or no data */ }
}

function renderHighlightsList() {
  const container = $('#highlights-list');
  if (!container) return;
  const entries = Object.entries(state.highlights);
  if (!entries.length) {
    container.innerHTML = '<div class="panel-empty"><div class="panel-empty-icon">🖊</div><div class="panel-empty-text">No highlights yet — right-click any verse</div></div>';
    return;
  }
  container.innerHTML = '';
  for (const [ref, color] of entries.sort((a,b)=>a[0].localeCompare(b[0]))) {
    const hex = HL_HEX[color] || '#ffeb3b';
    const item = el('div', {
      class: 'ctx-menu-item',
      style: `border-left: 3px solid ${hex}; padding-left: 10px; cursor:pointer;`,
      onclick: () => {
        const parsed = parseRef(ref);
        if (parsed) loadChapter(parsed.book, parsed.chapter, parsed.verse);
      }
    });
    item.textContent = ref;
    container.appendChild(item);
  }
}

async function setHighlight(ref, colorName) {
  const hex = HL_HEX[colorName];
  if (!hex) return;
  try {
    await fetch('/api/highlights', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ ref, color: hex })
    });
    state.highlights[ref] = colorName;
    applyHighlights();
    renderHighlightsList();
  } catch (_) { showToast('Sign in to save highlights'); }
}

async function clearHighlight(ref) {
  try {
    await fetch(`/api/highlights/${encodeURIComponent(ref)}`, { method: 'DELETE' });
    delete state.highlights[ref];
    applyHighlights();
    renderHighlightsList();
  } catch (_) {}
}

// ── 13. CONTEXT MENU ────────────────────────────────────────────────────────

let _ctxRef = null;

function showVerseContextMenu(ref, x, y) {
  _ctxRef = ref;
  const menu = $('#verse-context-menu');
  if (!menu) return;

  // Mark active swatch
  const currentColor = state.highlights[ref];
  menu.querySelectorAll('.hl-swatch').forEach(sw => {
    sw.classList.toggle('active', sw.dataset.color === currentColor);
  });

  // Position: stay within viewport
  menu.classList.add('open');
  const vw = window.innerWidth, vh = window.innerHeight;
  const mw = menu.offsetWidth || 190, mh = menu.offsetHeight || 180;
  menu.style.left = Math.min(x, vw - mw - 8) + 'px';
  menu.style.top  = Math.min(y, vh - mh - 8) + 'px';
}

function closeVerseContextMenu() {
  const menu = $('#verse-context-menu');
  if (menu) menu.classList.remove('open');
  _ctxRef = null;
}

// ── 14. SHARE / COPY ────────────────────────────────────────────────────────

async function copyVerse(ref) {
  try {
    const parts = ref.match(/^(.+?)\\s+(\\d+):(\\d+)$/);
    if (!parts) return;
    const data = await apiFetch(`/api/verse?ref=${encodeURIComponent(ref)}&translation=${encodeURIComponent(state.currentTranslation)}`);
    const verses = data.verses || data;
    const verseNum = parseInt(parts[3]);
    const verse = (verses || []).find(v => v.num === verseNum || v.verse === verseNum);
    const text = verse ? (verse.text || verse.verse_text || '') : '';
    const formatted = `"${text}" — ${ref} (${state.currentTranslation})`;
    await navigator.clipboard.writeText(formatted);
    showToast('Verse copied to clipboard');
  } catch (_) {
    showToast('Copy failed');
  }
}

async function shareVerse(ref) {
  try {
    const parts = ref.match(/^(.+?)\\s+(\\d+):(\\d+)$/);
    if (!parts) return;
    const data = await apiFetch(`/api/verse?ref=${encodeURIComponent(ref)}&translation=${encodeURIComponent(state.currentTranslation)}`);
    const verses = data.verses || data;
    const verseNum = parseInt(parts[3]);
    const verse = (verses || []).find(v => v.num === verseNum || v.verse === verseNum);
    const text = verse ? (verse.text || verse.verse_text || '') : '';
    const formatted = `"${text}" — ${ref} (${state.currentTranslation})`;
    if (navigator.share) {
      await navigator.share({ title: ref, text: formatted });
    } else {
      await navigator.clipboard.writeText(formatted);
      showToast('Verse copied (share not supported on this device)');
    }
  } catch (_) {
    showToast('Share failed');
  }
}

function showToast(msg) {
  let toast = $('#cs-toast');
  if (!toast) {
    toast = el('div', { id: 'cs-toast', style: 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:8px 16px;border-radius:20px;font-size:13px;z-index:var(--z-toast);pointer-events:none;transition:opacity 0.3s;' });
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toast.style.opacity = '0'; }, 2500);
}

// ── 15. READING PLANS ───────────────────────────────────────────────────────

const PLAN_PASSAGES = {
  'nt-90-days': [
    // 90 entries — first chapter of each block for navigation purposes
    // Matthew (28ch), Mark (16ch), Luke (24ch), John (21ch), Acts (28ch),
    // Romans–Philemon, Hebrews–Revelation
    ...Array.from({length:9}, (_,i)=>`Matthew ${i*3+1}`),
    `Matthew 28`, `Mark 1`,
    ...Array.from({length:5}, (_,i)=>`Mark ${i*3+2}`),
    `Luke 1`,
    ...Array.from({length:8}, (_,i)=>`Luke ${i*3+1}`),
    `John 1`,
    ...Array.from({length:7}, (_,i)=>`John ${i*3+1}`),
    `Acts 1`,
    ...Array.from({length:9}, (_,i)=>`Acts ${i*3+1}`),
    `Romans 1`, `Romans 9`, `1 Corinthians 1`, `1 Corinthians 10`,
    `2 Corinthians 1`, `Galatians 1`, `Ephesians 1`, `Philippians 1`,
    `Colossians 1`, `1 Thessalonians 1`, `2 Thessalonians 1`, `1 Timothy 1`,
    `2 Timothy 1`, `Titus 1`, `Philemon 1`, `Hebrews 1`, `Hebrews 8`,
    `James 1`, `1 Peter 1`, `2 Peter 1`, `1 John 1`, `2 John 1`,
    `3 John 1`, `Jude 1`, `Revelation 1`, `Revelation 11`, `Revelation 19`
  ].slice(0, 90),
  'gospels-28': [
    `Matthew 1`,`Matthew 4`,`Matthew 7`,`Matthew 10`,`Matthew 13`,`Matthew 16`,`Matthew 19`,
    `Matthew 22`,`Matthew 25`,`Matthew 28`,
    `Mark 1`,`Mark 4`,`Mark 8`,`Mark 12`,`Mark 16`,
    `Luke 1`,`Luke 4`,`Luke 7`,`Luke 10`,`Luke 13`,`Luke 16`,`Luke 19`,`Luke 22`,
    `John 1`,`John 6`,`John 11`,`John 16`,`John 20`
  ],
  'psalms-proverbs-30': Array.from({length:30}, (_,i)=>`Psalms ${i*5+1}`),
  'pauline-21': [
    `Romans 1`,`Romans 5`,`Romans 9`,`Romans 13`,`1 Corinthians 1`,`1 Corinthians 6`,
    `1 Corinthians 11`,`2 Corinthians 1`,`2 Corinthians 8`,`Galatians 1`,`Galatians 4`,
    `Ephesians 1`,`Ephesians 4`,`Philippians 1`,`Colossians 1`,
    `1 Thessalonians 1`,`2 Thessalonians 1`,`1 Timothy 1`,`2 Timothy 1`,
    `Titus 1`,`Philemon 1`
  ],
  'bible-in-a-year': Array.from({length:365}, (_,i) => {
    // Simplified sequential reading: OT + NT interleaved
    // Genesis(50) + Exodus(40) + … distribute over 365 days
    const OT = ['Genesis','Exodus','Leviticus','Numbers','Deuteronomy','Joshua','Judges','Ruth',
      '1 Samuel','2 Samuel','1 Kings','2 Kings','1 Chronicles','2 Chronicles','Ezra','Nehemiah',
      'Esther','Job','Psalms','Proverbs','Ecclesiastes','Song of Solomon','Isaiah','Jeremiah',
      'Lamentations','Ezekiel','Daniel','Hosea','Joel','Amos','Obadiah','Jonah','Micah',
      'Nahum','Habakkuk','Zephaniah','Haggai','Zechariah','Malachi'];
    const NT = ['Matthew','Mark','Luke','John','Acts','Romans','1 Corinthians','2 Corinthians',
      'Galatians','Ephesians','Philippians','Colossians','1 Thessalonians','2 Thessalonians',
      '1 Timothy','2 Timothy','Titus','Philemon','Hebrews','James','1 Peter','2 Peter',
      '1 John','2 John','3 John','Jude','Revelation'];
    // Each day: approx one OT + one NT chapter
    const ntIndex = Math.floor(i / 4) % NT.length;
    const otIndex = Math.floor(i * 39 / 365);
    return OT[Math.min(otIndex, OT.length - 1)] + ' 1';
  })
};

let _planState = {}; // plan_id → day_index

async function loadReadingPlans() {
  const container = $('#plans-list');
  if (!container) return;
  try {
    const [plans, progress] = await Promise.all([
      apiFetch('/api/reading-plans'),
      apiFetch('/api/reading-plans/progress').catch(() => [])
    ]);
    _planState = {};
    for (const p of (progress || [])) _planState[p.plan_id] = p.day_index;
    renderReadingPlans(plans || []);
  } catch (_) {
    if (container) container.innerHTML = '<div class="panel-empty"><div class="panel-empty-icon">📅</div><div class="panel-empty-text">Sign in to track reading plans</div></div>';
  }
}

function renderReadingPlans(plans) {
  const container = $('#plans-list');
  if (!container) return;
  container.innerHTML = '';
  const list = el('div', { class: 'plans-list' });
  for (const plan of plans) {
    const dayIdx = _planState[plan.id] || 0;
    const pct = Math.round((dayIdx / plan.days) * 100);
    const passages = PLAN_PASSAGES[plan.id] || [];
    const todayPassage = passages[Math.min(dayIdx, passages.length - 1)] || '';

    const card = el('div', { class: 'plan-card' + (dayIdx > 0 ? ' active' : '') });
    const header = el('div', { class: 'plan-card-header' });
    header.appendChild(el('span', { class: 'plan-card-name' }, plan.name));
    header.appendChild(el('span', { class: 'plan-card-category' }, plan.category));
    card.appendChild(header);
    card.appendChild(el('p', { class: 'plan-card-desc' }, plan.description));

    const progBar = el('div', { class: 'plan-progress-bar' });
    const fill = el('div', { class: 'plan-progress-fill', style: `width:${pct}%` });
    progBar.appendChild(fill);
    card.appendChild(progBar);

    const progLabel = el('div', { class: 'plan-progress-label' });
    progLabel.appendChild(el('span', {}, `Day ${dayIdx} of ${plan.days}`));
    progLabel.appendChild(el('span', {}, `${pct}%`));
    card.appendChild(progLabel);

    if (todayPassage && dayIdx < plan.days) {
      const today = el('p', { style: 'font-size:12px;color:var(--gold);margin-top:5px;' }, `Today: ${todayPassage}`);
      card.appendChild(today);
    } else if (dayIdx >= plan.days) {
      const done = el('p', { style: 'font-size:12px;color:#66bb6a;margin-top:5px;' }, '✓ Complete!');
      card.appendChild(done);
    }

    const actions = el('div', { class: 'plan-actions' });
    if (todayPassage && dayIdx < plan.days) {
      const readBtn = el('button', { class: 'plan-btn primary', onclick: async () => {
        const parsed = parseRef(todayPassage + ':1');
        if (parsed) loadChapter(parsed.book, parsed.chapter, null);
        else {
          // todayPassage is "Book Chapter" — parse manually
          const m = todayPassage.match(/^(.+)\\s+(\\d+)$/);
          if (m) {
            const bk = ALL_BOOKS.find(b => b.name === m[1]);
            if (bk) loadChapter(bk.name, parseInt(m[2]), null);
          }
        }
      }}, 'Read Today');
      actions.appendChild(readBtn);

      const markBtn = el('button', { class: 'plan-btn', onclick: async () => {
        const newDay = dayIdx + 1;
        await fetch('/api/reading-plans/progress', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ plan_id: plan.id, day_index: newDay })
        });
        _planState[plan.id] = newDay;
        renderReadingPlans(plans);
        showToast(`Day ${newDay} marked — great work!`);
      }}, 'Mark Read');
      actions.appendChild(markBtn);
    }

    if (dayIdx > 0) {
      const resetBtn = el('button', { class: 'plan-btn', onclick: async () => {
        if (!confirm(`Reset "${plan.name}" progress?`)) return;
        await fetch(`/api/reading-plans/progress/${encodeURIComponent(plan.id)}`, { method: 'DELETE' });
        _planState[plan.id] = 0;
        renderReadingPlans(plans);
      }}, 'Reset');
      actions.appendChild(resetBtn);
    } else {
      const startBtn = el('button', { class: 'plan-btn', onclick: async () => {
        await fetch('/api/reading-plans/progress', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ plan_id: plan.id, day_index: 1 })
        });
        _planState[plan.id] = 1;
        renderReadingPlans(plans);
        showToast(`Started ${plan.name}!`);
      }}, 'Start Plan');
      actions.appendChild(startBtn);
    }

    card.appendChild(actions);
    list.appendChild(card);
  }
  container.appendChild(list);
}

// ── 16. HELP MODAL ──────────────────────────────────────────────────────────

function openHelpModal() {
  const modal = $('#help-modal');
  if (modal) modal.classList.add('open');
}

function closeHelpModal() {
  const modal = $('#help-modal');
  if (modal) modal.classList.remove('open');
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

  // Slide-drawer close buttons (×) — delegated so SVG child clicks resolve correctly
  document.addEventListener('click', e => {
    const btn = e.target.closest('.drawer-close-btn');
    if (!btn) return;
    const target = btn.dataset.close;
    if (target === 'sessions-panel') closeSessionsPanel();
    else if (target === 'bookmarks-panel') closeBookmarksPanel();
    else if (target === 'history-panel') closeHistoryPanel();
  });

  // Show admin menu item if admin
  if (isAdmin()) {
    if (menuAdmin) menuAdmin.style.display = '';
    const oldAdminItem = $('#manage-users-item');
    if (oldAdminItem) oldAdminItem.style.display = '';
  }

  // User dropdown — event delegation on all data-action buttons
  const userDropdown = $('#user-chip .user-dropdown') || document.querySelector('.user-dropdown');
  if (userDropdown) {
    userDropdown.addEventListener('click', e => {
      const item = e.target.closest('[data-action]');
      if (!item) return;
      const action = item.dataset.action;
      // Close the dropdown first
      userDropdown.classList.remove('open');
      if (action === 'sessions')      openSessionsPanel();
      else if (action === 'bookmarks') openBookmarksPanel();
      else if (action === 'history')   openHistoryPanel();
      else if (action === 'manage-users') showAdminPanel();
      else if (action === 'signout')   handleSignOut();
    });
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

  // Help button
  const helpBtn = $('#btn-help');
  if (helpBtn) helpBtn.addEventListener('click', openHelpModal);
  const helpClose = $('#btn-help-close');
  if (helpClose) helpClose.addEventListener('click', closeHelpModal);
  const helpModal = $('#help-modal');
  if (helpModal) helpModal.addEventListener('click', e => {
    if (e.target === helpModal) closeHelpModal();
  });

  // Context menu — right-click and long-press on verse rows
  const verseArea = $('#verse-area') || $('#chapter-content') || document.querySelector('.chapter-content, #reader-pane, #reader');
  document.addEventListener('contextmenu', e => {
    const row = e.target.closest('.verse-row[data-verse]');
    if (!row) { closeVerseContextMenu(); return; }
    e.preventDefault();
    const ref = `${state.currentBook} ${state.currentChapter}:${row.getAttribute('data-verse')}`;
    showVerseContextMenu(ref, e.clientX + 4, e.clientY + 4);
  });

  // Long-press for mobile context menu
  let _longPressTimer = null;
  document.addEventListener('touchstart', e => {
    const row = e.target.closest('.verse-row[data-verse]');
    if (!row) return;
    _longPressTimer = setTimeout(() => {
      const ref = `${state.currentBook} ${state.currentChapter}:${row.getAttribute('data-verse')}`;
      const touch = e.touches[0];
      showVerseContextMenu(ref, touch.clientX, touch.clientY);
    }, 600);
  }, { passive: true });
  document.addEventListener('touchend', () => clearTimeout(_longPressTimer), { passive: true });
  document.addEventListener('touchmove', () => clearTimeout(_longPressTimer), { passive: true });

  // Context menu actions
  const ctxMenu = $('#verse-context-menu');
  if (ctxMenu) {
    ctxMenu.querySelectorAll('.hl-swatch').forEach(sw => {
      sw.addEventListener('click', () => {
        if (!_ctxRef) return;
        if (sw.dataset.color === 'clear') clearHighlight(_ctxRef);
        else setHighlight(_ctxRef, sw.dataset.color);
        closeVerseContextMenu();
      });
    });
    $('#ctx-copy').addEventListener('click', () => { if (_ctxRef) copyVerse(_ctxRef); closeVerseContextMenu(); });
    $('#ctx-share').addEventListener('click', () => { if (_ctxRef) shareVerse(_ctxRef); closeVerseContextMenu(); });
    $('#ctx-bookmark').addEventListener('click', () => {
      if (!_ctxRef) return;
      // Reuse existing bookmark toggle if available
      if (window.BibleReader && window.BibleReader.toggleBookmark) {
        window.BibleReader.toggleBookmark(_ctxRef);
      } else {
        fetch('/api/bookmarks', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ref: _ctxRef}) })
          .then(() => showToast('Bookmarked!'))
          .catch(() => showToast('Sign in to bookmark'));
      }
      closeVerseContextMenu();
    });
    $('#ctx-note').addEventListener('click', () => {
      if (!_ctxRef) return;
      switchTab('notes');
      openBottomSheet();
      closeVerseContextMenu();
    });
  }

  // Close context menu on click outside
  document.addEventListener('click', e => {
    const menu = $('#verse-context-menu');
    if (menu && !menu.contains(e.target)) closeVerseContextMenu();
  });

  // Escape key closes context menu and help modal
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      closeVerseContextMenu();
      closeHelpModal();
    }
  }, true);

  // Load highlights after init (if logged in)
  loadHighlights();

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

document.addEventListener('DOMContentLoaded', () => { initAuth(); });

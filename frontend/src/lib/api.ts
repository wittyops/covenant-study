/**
 * api.ts — Typed API client for the Covenant Study FastAPI backend.
 *
 * All requests go through `apiFetch`, which:
 *   1. Injects the Authorization header when a token is present
 *   2. Parses JSON and throws a descriptive Error on non-2xx responses
 *
 * Token management is intentionally outside this file — the auth store owns
 * the token and passes it in when needed.  This keeps the client stateless
 * and easy to test.
 */

import type {
  BookInfo,
  Bookmark,
  ChapterResponse,
  CrossRef,
  Highlight,
  HistoryEntry,
  InterlinearWord,
  Place,
  StrongsEntry,
  StudySession,
  TaggedWord,
  Translation,
  User,
  Verse,
} from './types'

// ─── Core fetch wrapper ────────────────────────────────────────────────────

// Every request through this app — login, chapter text, highlights, every
// panel — funnels through here. Without a bound, a hung backend, a dropped
// VPN session, or a proxy that accepts a connection and never answers all
// produce the same symptom: the browser's fetch() just never settles, and
// whatever UI was waiting on it (a spinner, a skeleton) sits there forever
// with no error, no retry, and nothing for the user to act on. There is no
// universal browser-level fetch timeout to fall back on — some network
// failure modes genuinely never time out on their own. So every request
// gets an explicit ceiling here, once, instead of trusting each call site
// to remember to add one.
const REQUEST_TIMEOUT_MS = 15_000

async function apiFetch<T>(
  path: string,
  opts: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, ...fetchOpts } = opts

  const headers = new Headers(fetchOpts.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let res: Response
  try {
    res = await fetch(path, {
      ...fetchOpts,
      headers,
      signal: fetchOpts.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      throw new Error('Request timed out — check your connection and try again.')
    }
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error('Request was cancelled.')
    }
    // Network failure (offline, DNS, TLS, connection refused) — fetch's own
    // TypeError carries no useful message for the user.
    throw new Error('Could not reach the server — check your connection and try again.')
  }

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      message = body.detail ?? message
    } catch (_) {}
    throw new Error(message)
  }

  // 204 No Content — return undefined cast to T
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ─── Auth ──────────────────────────────────────────────────────────────────

export const auth = {
  login(username: string, password: string) {
    return apiFetch<{ token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  register(username: string, password: string, displayName?: string) {
    return apiFetch<{ token: string; user: User }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, display_name: displayName ?? null }),
    })
  },

  logout(token: string | null) {
    return apiFetch<void>('/api/auth/logout', { method: 'POST', token })
  },

  me(token: string) {
    return apiFetch<User>('/api/auth/me', { token })
  },

  updateMe(
    updates: { displayName?: string; currentPassword?: string; newPassword?: string },
    token: string,
  ) {
    return apiFetch<User>('/api/auth/me', {
      method: 'PUT',
      body: JSON.stringify({
        display_name: updates.displayName,
        current_password: updates.currentPassword,
        new_password: updates.newPassword,
      }),
      token,
    })
  },
}

// ─── Bible content ─────────────────────────────────────────────────────────

export const bible = {
  books(token?: string | null) {
    return apiFetch<BookInfo[]>('/api/bible/books', { token })
  },

  translations(token?: string | null) {
    return apiFetch<Translation[]>('/api/bible/translations', { token })
  },

  chapter(book: number, chapter: number, translation: string, token?: string | null) {
    const qs = new URLSearchParams({ book: String(book), chapter: String(chapter), translation })
    return apiFetch<ChapterResponse>(`/api/bible/chapter?${qs}`, { token })
  },

  search(q: string, translation: string, token?: string | null) {
    const qs = new URLSearchParams({ q, translation })
    return apiFetch<Verse[]>(`/api/bible/search?${qs}`, { token })
  },

  strongs(number: string, token?: string | null) {
    return apiFetch<StrongsEntry>(`/api/bible/strongs/${encodeURIComponent(number)}`, { token })
  },

  crossrefs(book: number, chapter: number, verse: number, token?: string | null) {
    const qs = new URLSearchParams({
      book: String(book),
      chapter: String(chapter),
      verse: String(verse),
    })
    return apiFetch<CrossRef[]>(`/api/bible/crossrefs?${qs}`, { token })
  },

  interlinear(book: number, chapter: number, token?: string | null) {
    const qs = new URLSearchParams({ book: String(book), chapter: String(chapter) })
    return apiFetch<InterlinearWord[]>(`/api/bible/interlinear?${qs}`, { token })
  },

  chapterWords(book: number, chapter: number, token?: string | null) {
    const qs = new URLSearchParams({ book: String(book), chapter: String(chapter) })
    return apiFetch<Record<string, TaggedWord[]>>(`/fragments/chapter/words?${qs}`, { token })
  },

  places(token?: string | null) {
    return apiFetch<Place[]>('/api/places', { token })
  },

  compare(book: number, chapter: number, translations: string[], token?: string | null) {
    const qs = new URLSearchParams({
      book: String(book),
      chapter: String(chapter),
      translations: translations.join(','),
    })
    return apiFetch<ChapterResponse[]>(`/api/bible/compare?${qs}`, { token })
  },

  // Legacy single-verse route (predates the React rewrite) — takes a ref
  // string ('John 3:16') rather than numeric book/chapter, so it stays on
  // its own /api/compare path instead of the /api/bible/* SPA dialect.
  compareVerse(ref: string, translations: string[], token?: string | null) {
    const qs = new URLSearchParams({ ref, translations: translations.join(',') })
    return apiFetch<{ reference: string; comparisons: Record<string, string> }>(
      `/api/compare?${qs}`,
      { token },
    )
  },
}

// ─── User data ─────────────────────────────────────────────────────────────

export const bookmarks = {
  list(token: string) {
    return apiFetch<Bookmark[]>('/api/bookmarks', { token })
  },
  add(ref: string, label: string | null, color: string, token: string) {
    return apiFetch<Bookmark>('/api/bookmarks', {
      method: 'POST',
      body: JSON.stringify({ ref, label, color }),
      token,
    })
  },
  remove(id: number, token: string) {
    return apiFetch<void>(`/api/bookmarks/${id}`, { method: 'DELETE', token })
  },
  check(ref: string, token: string) {
    const qs = new URLSearchParams({ ref })
    return apiFetch<{ bookmarked: boolean; id: number | null }>(`/api/bookmarks/check?${qs}`, {
      token,
    })
  },
}

export const highlights = {
  list(token: string) {
    return apiFetch<Highlight[]>('/api/highlights', { token })
  },
  set(ref: string, color: string, note: string | null, token: string) {
    return apiFetch<Highlight>(`/api/highlights/${encodeURIComponent(ref)}`, {
      method: 'PUT',
      body: JSON.stringify({ color, note }),
      token,
    })
  },
  remove(ref: string, token: string) {
    return apiFetch<void>(`/api/highlights/${encodeURIComponent(ref)}`, { method: 'DELETE', token })
  },
}

export const history = {
  list(token: string) {
    return apiFetch<HistoryEntry[]>('/api/history', { token })
  },
  log(ref: string, token: string) {
    return apiFetch<void>('/api/history', { method: 'POST', body: JSON.stringify({ ref }), token })
  },
}

export const notes = {
  get(ref: string, token: string) {
    return apiFetch<{ ref: string; body: string }>(`/api/notes/${encodeURIComponent(ref)}`, {
      token,
    })
  },
  save(ref: string, body: string, token: string) {
    return apiFetch<void>(`/api/notes/${encodeURIComponent(ref)}`, {
      method: 'PUT',
      body: JSON.stringify({ body }),
      token,
    })
  },
}

export const sessions = {
  list(token: string) {
    return apiFetch<StudySession[]>('/api/sessions', { token })
  },
  save(name: string, state: object, token: string) {
    return apiFetch<StudySession>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ name, state_json: JSON.stringify(state) }),
      token,
    })
  },
  load(id: number, token: string) {
    return apiFetch<StudySession>(`/api/sessions/${id}`, { token })
  },
  remove(id: number, token: string) {
    return apiFetch<void>(`/api/sessions/${id}`, { method: 'DELETE', token })
  },
}

export const admin = {
  users(token: string) {
    return apiFetch<User[]>('/api/admin/users', { token })
  },
  createUser(
    username: string,
    password: string,
    displayName: string | null,
    role: 'user' | 'admin',
    token: string,
  ) {
    return apiFetch<User>('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({ username, password, display_name: displayName, role }),
      token,
    })
  },
  resetPassword(uid: number, password: string, token: string) {
    return apiFetch<{ ok: boolean }>(`/api/admin/users/${uid}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
      token,
    })
  },
  updateUser(
    uid: number,
    updates: { displayName?: string; role?: 'user' | 'admin' },
    token: string,
  ) {
    return apiFetch<User>(`/api/admin/users/${uid}`, {
      method: 'PUT',
      body: JSON.stringify({ display_name: updates.displayName, role: updates.role }),
      token,
    })
  },
  deleteUser(uid: number, token: string) {
    return apiFetch<void>(`/api/admin/users/${uid}`, { method: 'DELETE', token })
  },
}

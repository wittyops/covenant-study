// ─── Domain types (mirroring FastAPI Pydantic models) ─────────────────────

export interface User {
  id: number
  username: string
  display_name: string | null
  role: 'user' | 'admin'
  created_at: number
}

export interface BookInfo {
  book: number
  name: string
  testament: 'OT' | 'NT' | 'AP'
  chapters: number
}

export interface Verse {
  book: number
  book_name: string
  chapter: number
  verse: number
  text: string
  translation: string
}

export interface ChapterResponse {
  book: number
  book_name: string
  chapter: number
  translation: string
  verses: Verse[]
}

export interface StrongsEntry {
  number: string
  word: string
  transliteration: string
  pronunciation: string
  definition: string
  derivation: string
  language: 'Hebrew' | 'Greek'
}

export interface CrossRef {
  from_book: number
  from_chapter: number
  from_verse: number
  to_book: number
  to_chapter: number
  to_verse: number
  to_book_name: string
}

export interface TaggedWord {
  text: string
  strongs: string
  morph: string
}

export interface InterlinearWord {
  position: number
  original: string
  translit: string
  morph: string
  strongs: string
  english: string
}

export interface Bookmark {
  id: number
  ref: string
  label: string | null
  color: string
  created_at: number
}

export interface Highlight {
  ref: string
  color: string
  note: string | null
}

export interface HistoryEntry {
  ref: string
  visited_at: number
}

export interface StudySession {
  id: number
  name: string
  state_json: string
  created_at: number
  updated_at: number
}

export interface Place {
  id: number
  name: string
  latitude: number
  longitude: number
  reference: string | null
}

export interface Translation {
  id: string
  name: string
}

// Panel IDs for the tool sidebar
export type PanelId =
  | 'bookmarks'
  | 'notes'
  | 'highlights'
  | 'history'
  | 'sessions'
  | 'plans'
  | 'admin'
  | 'map'
  | null

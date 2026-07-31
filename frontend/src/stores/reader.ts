/**
 * Reader store — current reading position and selected verse.
 *
 * Position (book + chapter + translation) is persisted to localStorage so the
 * user returns to where they left off.  The selected verse is session-only —
 * it resets on navigation.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ReaderState {
  // ── Persisted position ────────────────────────────────────────────────
  book: number // 1–66
  chapter: number // 1–150
  verse: number | null
  translation: string // translation key, e.g. 'KJV'

  // ── Active Strong's word (session-only) ───────────────────────────────
  activeStrongs: string | null

  // ── Actions ───────────────────────────────────────────────────────────
  setBook(book: number): void
  setChapter(chapter: number): void
  setVerse(verse: number | null): void
  setTranslation(t: string): void
  navigate(book: number, chapter: number, verse?: number): void
  openStrongs(number: string | null): void
}

export const useReaderStore = create<ReaderState>()(
  persist(
    (set) => ({
      book: 1,
      chapter: 1,
      verse: null,
      translation: 'KJV',
      activeStrongs: null,

      setBook(book) {
        set({ book, chapter: 1, verse: null, activeStrongs: null })
      },
      setChapter(chapter) {
        set({ chapter, verse: null, activeStrongs: null })
      },
      setVerse(verse) {
        set({ verse })
      },
      setTranslation(t) {
        set({ translation: t })
      },
      navigate(book, chapter, verse?) {
        set({ book, chapter, verse: verse ?? null, activeStrongs: null })
      },
      openStrongs(number) {
        set({ activeStrongs: number })
      },
    }),
    {
      name: 'covenant-reader',
      partialize: (s) => ({ book: s.book, chapter: s.chapter, translation: s.translation }),
    },
  ),
)

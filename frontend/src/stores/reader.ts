/**
 * Reader store — current reading position and selected verse(s).
 *
 * Position (book + chapter + translation) is persisted to localStorage so the
 * user returns to where they left off.  Selection is session-only — it
 * resets on navigation.
 *
 * Selection model: `verse` is the anchor (first tap); `selectionEnd` is set
 * only once a second, different verse number is tapped, extending the
 * selection into a range. `selectionEnd === null` means "just `verse`" —
 * every existing call site that reads `verse` alone keeps working unchanged.
 * Tapping verse *text* (as opposed to the verse *number*) always calls
 * setVerse(), which collapses any pending range back to a single verse —
 * see ChapterView's handleContainerClick vs handleVerseNumberClick.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ReaderState {
  // ── Persisted position ────────────────────────────────────────────────
  book: number // 1–66
  chapter: number // 1–150
  verse: number | null
  translation: string // translation key, e.g. 'KJV'

  // ── Selection (session-only) ────────────────────────────────────────────
  selectionEnd: number | null

  // ── Active Strong's word (session-only) ───────────────────────────────
  activeStrongs: string | null

  // ── Actions ───────────────────────────────────────────────────────────
  setBook(book: number): void
  setChapter(chapter: number): void
  setVerse(verse: number | null): void
  selectVerseNumber(verse: number): void
  clearSelection(): void
  setTranslation(t: string): void
  navigate(book: number, chapter: number, verse?: number): void
  openStrongs(number: string | null): void
}

export const useReaderStore = create<ReaderState>()(
  persist(
    (set, get) => ({
      book: 1,
      chapter: 1,
      verse: null,
      selectionEnd: null,
      translation: 'KJV',
      activeStrongs: null,

      setBook(book) {
        set({ book, chapter: 1, verse: null, selectionEnd: null, activeStrongs: null })
      },
      setChapter(chapter) {
        set({ chapter, verse: null, selectionEnd: null, activeStrongs: null })
      },
      setVerse(verse) {
        set({ verse, selectionEnd: null })
      },
      selectVerseNumber(verse) {
        const { verse: current, selectionEnd } = get()
        if (current === null) {
          // Nothing selected yet — this tap becomes the anchor.
          set({ verse, selectionEnd: null })
        } else if (selectionEnd === null && current === verse) {
          // Tapping the sole selected verse again — toggle off.
          set({ verse: null, selectionEnd: null })
        } else if (selectionEnd !== null && (verse === current || verse === selectionEnd)) {
          // Tapping either end of an existing range again — toggle off.
          set({ verse: null, selectionEnd: null })
        } else {
          // A different verse — extend (or re-extend) the range from the
          // original anchor, not from wherever selectionEnd currently is.
          set({ selectionEnd: verse })
        }
      },
      clearSelection() {
        set({ verse: null, selectionEnd: null })
      },
      setTranslation(t) {
        set({ translation: t })
      },
      navigate(book, chapter, verse?) {
        set({ book, chapter, verse: verse ?? null, selectionEnd: null, activeStrongs: null })
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

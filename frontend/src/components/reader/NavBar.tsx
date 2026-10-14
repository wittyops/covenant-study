/**
 * NavBar — persistent bottom bar for fast chapter/book navigation plus the
 * reading-text-size control. Sits alongside the header (not a sheet/overlay)
 * so jumping to a specific book+chapter never requires opening the full
 * BookPicker sheet — that stays around for visual browsing, this is for
 * "I know where I want to go."
 *
 * h-14 is a hard height, not just a Tailwind default: SelectionActionBar
 * (reader/SelectionActionBar.tsx) is fixed to the viewport bottom and has
 * to clear this bar's height exactly, or the two overlap.
 */
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Minus, Plus } from 'lucide-react'
import { bible } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { FONT_SCALE_STEPS, useSettingsStore } from '@/stores/settings'

export function NavBar() {
  const { book, chapter, translation, setBook, setChapter, setTranslation } = useReaderStore()
  const { token } = useAuthStore()
  const { fontScale, increaseFontScale, decreaseFontScale } = useSettingsStore()

  const { data: books = [] } = useQuery({
    queryKey: ['books'],
    queryFn: () => bible.books(token),
    staleTime: Infinity,
  })

  const current = books.find((b) => b.book === book)
  const chapterCount = current?.chapters ?? 1

  const ot = books.filter((b) => b.testament === 'OT')
  const nt = books.filter((b) => b.testament === 'NT')
  const ap = books.filter((b) => b.testament === 'AP')

  // Same Apocrypha/translation guard as BookPicker's pickBook — picking an
  // AP book on a translation that doesn't cover it is exactly the stuck
  // state behind the hang bug fixed 2026-10-14. Keep this in sync with
  // BookPicker.tsx if that guard ever changes.
  function pickBook(bookNum: number) {
    const target = books.find((b) => b.book === bookNum)
    if (target?.testament === 'AP' && translation !== 'KJVA') setTranslation('KJVA')
    setBook(bookNum)
  }

  function prevChapter() {
    if (chapter > 1) setChapter(chapter - 1)
  }
  function nextChapter() {
    if (chapter < chapterCount) setChapter(chapter + 1)
  }

  const atMin = fontScale <= FONT_SCALE_STEPS[0]
  const atMax = fontScale >= FONT_SCALE_STEPS[FONT_SCALE_STEPS.length - 1]

  return (
    <nav className="flex h-14 shrink-0 items-center gap-2 border-t border-bg-overlay bg-bg-surface px-3">
      <button
        type="button"
        title="Previous chapter"
        aria-label="Previous chapter"
        onClick={prevChapter}
        disabled={chapter <= 1}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary disabled:opacity-30 disabled:hover:bg-transparent"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      <select
        aria-label="Book"
        value={book}
        onChange={(e) => pickBook(Number(e.target.value))}
        className="h-9 min-w-0 flex-1 rounded border border-bg-overlay bg-bg-elevated px-2 text-sm text-text-primary focus:border-gold focus:outline-none"
      >
        {ot.length > 0 && (
          <optgroup label="Old Testament">
            {ot.map((b) => (
              <option key={b.book} value={b.book}>
                {b.name}
              </option>
            ))}
          </optgroup>
        )}
        {nt.length > 0 && (
          <optgroup label="New Testament">
            {nt.map((b) => (
              <option key={b.book} value={b.book}>
                {b.name}
              </option>
            ))}
          </optgroup>
        )}
        {ap.length > 0 && (
          <optgroup label="Apocrypha">
            {ap.map((b) => (
              <option key={b.book} value={b.book}>
                {b.name}
              </option>
            ))}
          </optgroup>
        )}
      </select>

      <select
        aria-label="Chapter"
        value={chapter}
        onChange={(e) => setChapter(Number(e.target.value))}
        className="h-9 w-[4.5rem] shrink-0 rounded border border-bg-overlay bg-bg-elevated px-2 text-sm text-text-primary focus:border-gold focus:outline-none"
      >
        {Array.from({ length: chapterCount }, (_, i) => i + 1).map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      <button
        type="button"
        title="Next chapter"
        aria-label="Next chapter"
        onClick={nextChapter}
        disabled={chapter >= chapterCount}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary disabled:opacity-30 disabled:hover:bg-transparent"
      >
        <ChevronRight className="h-4 w-4" />
      </button>

      <div className="mx-1 h-6 w-px shrink-0 bg-bg-overlay" />

      {/* Text size — the actual accessibility ask: everything above is
          navigation, this is reading comfort. */}
      <div className="flex shrink-0 items-center gap-0.5">
        <button
          type="button"
          title="Decrease text size"
          aria-label="Decrease text size"
          onClick={decreaseFontScale}
          disabled={atMin}
          className="flex h-9 w-9 items-center justify-center rounded text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary disabled:opacity-30 disabled:hover:bg-transparent"
        >
          <Minus className="h-3.5 w-3.5" />
        </button>
        <span className="w-9 text-center text-xs text-text-muted" aria-live="polite">
          {Math.round(fontScale * 100)}%
        </span>
        <button
          type="button"
          title="Increase text size"
          aria-label="Increase text size"
          onClick={increaseFontScale}
          disabled={atMax}
          className="flex h-9 w-9 items-center justify-center rounded text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary disabled:opacity-30 disabled:hover:bg-transparent"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
    </nav>
  )
}

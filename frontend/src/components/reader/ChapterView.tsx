/**
 * ChapterView — renders the current chapter with verse-level interactions.
 *
 * Data flow:
 *   useReaderStore (book, chapter, translation)
 *     → /api/bible/chapter          (verse text JSON)
 *     → /fragments/chapter/words    (per-word Strong's tagging, parallel fetch)
 *     → /api/highlights             (user highlight colours, when logged in)
 *
 * Word tagging: the backend returns {verse: [{text, strongs, morph}]} from the
 * same interlinear pipeline used by the htmx fragment renderer.  Tagged words
 * render as <span data-strongs="H7225"> so the delegated click handler can open
 * the Strong's card without individual onclick handlers on every word.
 *
 * Highlights: loaded once per session and filtered to the current chapter.
 * Each highlighted verse span gets class="verse-highlighted" plus an inline
 * --highlight-color CSS variable that index.css picks up via color-mix().
 */
import { useQuery } from '@tanstack/react-query'
import { Volume2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { bible, highlights as highlightsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { speechSupported, useSpeechStore } from '@/stores/speech'
import { useUiStore } from '@/stores/ui'
import { StrongsCard } from './StrongsCard'

export function ChapterView() {
  const {
    book,
    chapter,
    translation,
    verse: selectedVerse,
    selectionEnd,
    setVerse,
    selectVerseNumber,
    openStrongs,
    activeStrongs,
    navigate,
  } = useReaderStore()
  const { token } = useAuthStore()
  const { toast } = useUiStore()
  const containerRef = useRef<HTMLElement>(null)

  // ── Verse text ────────────────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ['chapter', book, chapter, translation],
    queryFn: () => bible.chapter(book, chapter, translation, token),
    staleTime: 5 * 60 * 1000,
    enabled: book > 0 && chapter > 0 && translation.length > 0,
  })

  // ── Word-level Strong's tagging (parallel, non-blocking) ──────────────────
  const { data: wordData } = useQuery({
    queryKey: ['chapter-words', book, chapter],
    queryFn: () => bible.chapterWords(book, chapter, token),
    staleTime: 30 * 60 * 1000,
    enabled: book > 0 && chapter > 0,
  })

  // ── User highlights (load once, filter per chapter) ───────────────────────
  const { data: allHighlights } = useQuery({
    queryKey: ['highlights'],
    queryFn: () => highlightsApi.list(token ?? ''),
    staleTime: 60 * 1000,
    enabled: !!token,
  })

  // Build verse-number → color map scoped to this chapter
  const highlightMap = useMemo(() => {
    const m = new Map<number, string>()
    if (!allHighlights || !data?.book_name) return m
    const prefix = `${data.book_name} ${chapter}:`
    for (const h of allHighlights) {
      if (h.ref.startsWith(prefix)) {
        const n = parseInt(h.ref.slice(prefix.length), 10)
        if (!Number.isNaN(n)) m.set(n, h.color)
      }
    }
    return m
  }, [allHighlights, data?.book_name, chapter])

  // ── Delegated handler — catches [data-verse-number], [data-verse], [data-strongs] ──
  // Shared by onClick + onKeyDown so keyboard users can select verses and words.
  //
  // [data-verse-number] (the small superscript verse number) is checked FIRST
  // and, if matched, short-circuits the rest: tapping the number is the
  // range-selection gesture (selectVerseNumber) and must never also fire the
  // single-verse-select-and-maybe-open-Strong's behavior below, even though
  // the number sits inside the same [data-verse] wrapper.
  //
  // Tapping anywhere else in the verse (the body text) keeps the original,
  // unchanged behavior: select just this verse (collapsing any pending
  // range — see setVerse in reader.ts) and open Strong's if a tagged word
  // was hit.
  const handleContainerClick = useCallback(
    (e: React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLElement>) => {
      if ('key' in e && e.key !== 'Enter' && e.key !== ' ') return

      const numberEl = (e.target as Element).closest('[data-verse-number]') as HTMLElement | null
      if (numberEl) {
        selectVerseNumber(Number(numberEl.dataset.verseNumber))
        return
      }

      const verseEl = (e.target as Element).closest('[data-verse]') as HTMLElement | null
      if (verseEl) setVerse(Number(verseEl.dataset.verse))

      const strongsEl = (e.target as Element).closest('[data-strongs]') as HTMLElement | null
      if (strongsEl) {
        openStrongs(strongsEl.dataset.strongs ?? null)
        // The Strong's card is a bottom sheet on mobile (up to 60vh tall) — if the
        // tapped word is already near the bottom of the viewport, the sheet opens
        // directly on top of it. scroll-mb-[65vh] on the word (below) tells the
        // browser how much clearance to leave; 'nearest' means it only scrolls if
        // the word would actually be covered, not unconditionally on every tap.
        strongsEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    },
    [setVerse, selectVerseNumber, openStrongs],
  )

  // Range is always stored as [verse, selectionEnd] in tap order, not
  // necessarily low-to-high — normalize here for the membership check.
  const selectionRange = useMemo(() => {
    if (selectedVerse === null) return null
    const lo = selectionEnd === null ? selectedVerse : Math.min(selectedVerse, selectionEnd)
    const hi = selectionEnd === null ? selectedVerse : Math.max(selectedVerse, selectionEnd)
    return [lo, hi] as const
  }, [selectedVerse, selectionEnd])

  // Side effect must live in an effect, not the render body: calling toast()
  // directly while rendering updates useUiStore's `toasts` array, and since
  // this component reads from useUiStore() without a selector, that update
  // re-renders ChapterView itself — which would call toast() again on every
  // single render for as long as isError stays true, pegging the JS thread
  // in an infinite synchronous loop. The effect only re-fires when isError
  // itself flips, not on every render.
  useEffect(() => {
    if (isError) toast('Failed to load chapter', 'error')
  }, [isError, toast])

  // Stop any in-progress read-aloud the moment the reader moves to a
  // different book/chapter — otherwise the browser keeps reading the OLD
  // chapter's text out loud while the screen shows a different one, which
  // is confusing (and listening to the right text matters more here than
  // almost anywhere else in the app).
  const stopSpeech = useSpeechStore((s) => s.stop)
  // biome-ignore lint/correctness/useExhaustiveDependencies: book/chapter aren't read in the effect body — they're the re-trigger signal for the cleanup, not a value it uses.
  useEffect(() => {
    return () => stopSpeech()
  }, [book, chapter, stopSpeech])

  // Sync book_name into the store so SelectionActionBar (now living in the
  // right-hand tool rail, not nested here) can read it without ChapterView
  // having to pass it down as a prop.
  const setBookName = useReaderStore((s) => s.setBookName)
  useEffect(() => {
    if (data?.book_name) setBookName(data.book_name)
  }, [data?.book_name, setBookName])

  if (isLoading) return <ChapterSkeleton />
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-text-muted">
        <p>
          {translation} doesn't have text for this book/chapter — it may not cover the Apocrypha, or
          this reference doesn't exist.
        </p>
        <button
          type="button"
          onClick={() => navigate(1, 1)}
          className="rounded-lg bg-gold px-4 py-2 text-sm font-semibold text-bg-base transition-opacity hover:opacity-90"
        >
          Return to Genesis 1
        </button>
      </div>
    )
  }

  return (
    <>
      {/* Chapter heading */}
      <header className="mb-6 flex items-start justify-between gap-3 border-b border-bg-overlay pb-4">
        <div>
          <h2 className="text-2xl font-bold text-gold">
            {data?.book_name} {chapter}
          </h2>
          <p className="text-xs text-text-muted mt-1 uppercase tracking-wide">{translation}</p>
        </div>
        {speechSupported() && data && (
          <ReadAloudButton chapterLabel={`${data.book_name} ${chapter}`} verses={data.verses} />
        )}
      </header>

      {/* Verse list — delegated click for verse selection and Strong's */}
      <section
        ref={containerRef}
        aria-label="Scripture text"
        className="scripture-text readable-text space-y-2 leading-8 text-text-primary"
        onClick={handleContainerClick}
        onKeyDown={handleContainerClick}
      >
        {(data?.verses ?? []).map((v) => {
          const words = wordData?.[String(v.verse)]
          const hlColor = highlightMap.get(v.verse)
          const isSelected =
            !!selectionRange && v.verse >= selectionRange[0] && v.verse <= selectionRange[1]

          return (
            <span
              key={v.verse}
              data-verse={v.verse}
              className={`cursor-pointer rounded px-0.5 transition-colors hover:bg-bg-elevated${hlColor ? ' verse-highlighted' : ''}${isSelected ? ' verse-selected' : ''}`}
              style={
                hlColor ? ({ '--highlight-color': hlColor } as React.CSSProperties) : undefined
              }
            >
              <sup
                data-verse-number={v.verse}
                className="mr-1 text-xs font-bold text-gold-muted select-none cursor-pointer"
              >
                {v.verse}
              </sup>
              {/* words has no stable per-word id (TaggedWord is just
                  {text, strongs, morph} — duplicate text/strongs within a
                  verse is normal, e.g. repeated "the"), but the list itself
                  is never reordered or filtered after fetch: it's rendered
                  once per verse and replaced wholesale on the next
                  chapter/translation query, never mutated in place. Index
                  is a genuinely stable identity for that lifecycle. */}
              {words?.length
                ? words.map((w, i) =>
                    w.strongs ? (
                      <span
                        // biome-ignore lint/suspicious/noArrayIndexKey: see comment above — list is replace-wholesale, never reordered in place.
                        key={i}
                        className="word-tagged"
                        data-strongs={w.strongs}
                        data-morph={w.morph}
                      >
                        {w.text}{' '}
                      </span>
                    ) : (
                      // biome-ignore lint/suspicious/noArrayIndexKey: see comment above — list is replace-wholesale, never reordered in place.
                      <span key={i}>{w.text} </span>
                    ),
                  )
                : v.text}{' '}
            </span>
          )
        })}
      </section>

      {/* Strong's lexicon dialog — opens when a tagged word is clicked */}
      {activeStrongs && <StrongsCard number={activeStrongs} onClose={() => openStrongs(null)} />}
    </>
  )
}

/** Toggle button for reading the current chapter aloud via Web Speech API. */
function ReadAloudButton({
  chapterLabel,
  verses,
}: {
  chapterLabel: string
  verses: { verse: number; text: string }[]
}) {
  const { speaking, label, speak, stop } = useSpeechStore()
  const isThisChapter = speaking && label === chapterLabel

  function toggle() {
    if (isThisChapter) {
      stop()
      return
    }
    const text = verses.map((v) => v.text).join(' ')
    speak(text, chapterLabel)
  }

  return (
    <button
      type="button"
      title={isThisChapter ? 'Stop reading aloud' : 'Read this chapter aloud'}
      aria-label={isThisChapter ? 'Stop reading aloud' : 'Read this chapter aloud'}
      aria-pressed={isThisChapter}
      onClick={toggle}
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded transition-colors ${
        isThisChapter
          ? 'bg-gold-subtle text-gold'
          : 'text-text-muted hover:bg-bg-elevated hover:text-text-primary'
      }`}
    >
      <Volume2 className="h-4 w-4" />
    </button>
  )
}

function ChapterSkeleton() {
  return (
    <div className="space-y-3 py-4">
      <div className="loading-shimmer h-8 w-48 rounded" />
      {Array.from({ length: 12 }, (_, i) => (
        <div
          // biome-ignore lint/suspicious/noArrayIndexKey: no underlying array exists at all — i is pure index-generation, the only identity there is.
          key={i}
          className="loading-shimmer h-5 rounded"
          style={{ width: `${60 + (i % 5) * 8}%` }}
        />
      ))}
    </div>
  )
}

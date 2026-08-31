/**
 * ComparePassageView — full-chapter multi-translation comparison.
 *
 * Replaces ChapterView in the main content area while useUiStore().compareActive
 * is true (see App.tsx). Renders the same chapter across up to 4 translations,
 * fetched in one call via bible.compare() → GET /api/bible/compare.
 *
 * Two layouts, chosen by CSS breakpoint (not user-agent sniffing — a resized
 * browser window should behave the same as an actual phone, and viewport
 * queries are the reliable way to get that):
 *   - md and up: side-by-side grid columns, one per translation.
 *   - below md: swipeable full-width cards, one translation at a time, with
 *     dot navigation. Switching cards keeps the same verse anchored near the
 *     top rather than resetting scroll to the top of the chapter.
 *
 * Verse alignment is by verse number only — a translation missing a given
 * verse number (rare versification differences) renders a placeholder dash
 * rather than attempting fuzzy alignment.
 */
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { bible } from '@/lib/api'
import type { ChapterResponse } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'

export function ComparePassageView() {
  const { book, chapter } = useReaderStore()
  const { compareTranslations, stopCompare } = useUiStore()
  const { token } = useAuthStore()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['compare', book, chapter, compareTranslations],
    queryFn: () => bible.compare(book, chapter, compareTranslations, token),
    staleTime: 5 * 60 * 1000,
    enabled: book > 0 && chapter > 0 && compareTranslations.length > 0,
  })

  return (
    <div className="flex flex-col h-full">
      <header className="mb-4 flex items-center justify-between border-b border-bg-overlay pb-4 shrink-0">
        <div>
          <h2 className="text-xl font-bold text-gold">
            {data?.[0]?.book_name ?? ''} {chapter}
          </h2>
          <p className="text-xs text-text-muted mt-1 uppercase tracking-wide">
            Comparing {compareTranslations.join(', ')}
          </p>
        </div>
        <button
          type="button"
          title="Back to reading"
          onClick={() => stopCompare()}
          className="flex h-8 w-8 items-center justify-center rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      {isLoading ? (
        <div className="space-y-3 py-4">
          {Array.from({ length: 10 }, (_, i) => (
            <div
              key={i}
              className="loading-shimmer h-5 rounded"
              style={{ width: `${60 + (i % 5) * 8}%` }}
            />
          ))}
        </div>
      ) : isError || !data?.length ? (
        <p className="text-text-muted text-center py-20">Could not load this comparison.</p>
      ) : (
        <>
          <DesktopColumns data={data} />
          <MobileCarousel data={data} />
        </>
      )}
    </div>
  )
}

// ─── Desktop / wide viewport — side-by-side grid columns ───────────────────

function DesktopColumns({ data }: { data: ChapterResponse[] }) {
  return (
    <div
      className="hidden md:grid flex-1 gap-4 overflow-y-auto"
      style={{ gridTemplateColumns: `repeat(${data.length}, minmax(0, 1fr))` }}
    >
      {data.map((col) => (
        <div key={col.translation} className="min-w-0">
          <h3 className="mb-2 text-sm font-bold text-gold-muted uppercase tracking-wide sticky top-0 bg-bg-base py-1">
            {col.translation}
          </h3>
          <div className="space-y-2 leading-7 text-sm text-text-primary">
            {col.verses.map((v) => (
              <p key={v.verse}>
                <sup className="mr-1 text-xs font-bold text-gold-muted select-none">{v.verse}</sup>
                {v.text}
              </p>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Mobile / narrow viewport — swipeable one-translation-at-a-time cards ──

const SWIPE_THRESHOLD_PX = 50

function MobileCarousel({ data }: { data: ChapterResponse[] }) {
  const [active, setActive] = useState(0)
  const touchStartX = useRef<number | null>(null)
  const lastVisibleVerse = useRef<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Bounds-check in case the translation list shrank (shouldn't happen mid-view).
  const clampedActive = Math.min(active, data.length - 1)
  const current = data[clampedActive]

  function goTo(index: number) {
    if (index < 0 || index >= data.length) return
    setActive(index)
    // Anchor the new card to roughly the same verse the user was reading,
    // rather than resetting to the top of the chapter.
    requestAnimationFrame(() => {
      if (lastVisibleVerse.current == null) return
      const el = scrollRef.current?.querySelector(
        `[data-compare-verse="${lastVisibleVerse.current}"]`,
      )
      el?.scrollIntoView({ block: 'start' })
    })
  }

  function handleScroll() {
    const container = scrollRef.current
    if (!container) return
    const verseEls = container.querySelectorAll('[data-compare-verse]')
    for (const el of Array.from(verseEls)) {
      const rect = (el as HTMLElement).getBoundingClientRect()
      const containerRect = container.getBoundingClientRect()
      if (rect.top >= containerRect.top) {
        lastVisibleVerse.current = Number((el as HTMLElement).dataset.compareVerse)
        break
      }
    }
  }

  const dots = useMemo(() => data.map((d) => d.translation), [data])

  return (
    <div
      className="md:hidden flex flex-1 flex-col min-h-0"
      onTouchStart={(e) => {
        touchStartX.current = e.touches[0].clientX
      }}
      onTouchEnd={(e) => {
        if (touchStartX.current == null) return
        const delta = e.changedTouches[0].clientX - touchStartX.current
        if (delta > SWIPE_THRESHOLD_PX) goTo(clampedActive - 1)
        else if (delta < -SWIPE_THRESHOLD_PX) goTo(clampedActive + 1)
        touchStartX.current = null
      }}
    >
      <div className="flex items-center justify-between mb-2 shrink-0">
        <button
          type="button"
          disabled={clampedActive === 0}
          onClick={() => goTo(clampedActive - 1)}
          className="flex h-8 w-8 items-center justify-center rounded text-text-muted hover:text-text-primary disabled:opacity-30"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-bold text-gold-muted uppercase tracking-wide">
          {current.translation}
        </span>
        <button
          type="button"
          disabled={clampedActive === data.length - 1}
          onClick={() => goTo(clampedActive + 1)}
          className="flex h-8 w-8 items-center justify-center rounded text-text-muted hover:text-text-primary disabled:opacity-30"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto space-y-2 leading-7 text-text-primary"
      >
        {current.verses.map((v) => (
          <p key={v.verse} data-compare-verse={v.verse}>
            <sup className="mr-1 text-xs font-bold text-gold-muted select-none">{v.verse}</sup>
            {v.text}
          </p>
        ))}
      </div>

      <div className="flex items-center justify-center gap-1.5 pt-3 shrink-0">
        {dots.map((t, i) => (
          <button
            key={t}
            type="button"
            title={t}
            onClick={() => goTo(i)}
            className={`h-1.5 w-1.5 rounded-full transition-colors ${
              i === clampedActive ? 'bg-gold' : 'bg-bg-overlay'
            }`}
          />
        ))}
      </div>
    </div>
  )
}

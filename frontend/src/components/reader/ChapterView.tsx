/**
 * ChapterView — renders the current chapter with verse-level interactions.
 *
 * Data flow:
 *   useReaderStore (book, chapter, translation) → React Query → /api/bible/chapter
 *   → renders verse list → click on tagged word → dialog with Strong's card
 *
 * Tagged word HTML comes from the existing /fragments/chapter endpoint to avoid
 * duplicating the word-tagging pipeline in the frontend.  React event delegation
 * on the container catches all [data-strongs] clicks.
 */
import { useQuery } from '@tanstack/react-query'
import { useCallback, useRef } from 'react'
import { useReaderStore } from '@/stores/reader'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { bible } from '@/lib/api'
import { StrongsCard } from './StrongsCard'

export function ChapterView() {
  const { book, chapter, translation, setVerse, openStrongs, activeStrongs } = useReaderStore()
  const { token } = useAuthStore()
  const { toast } = useUiStore()
  const containerRef = useRef<HTMLDivElement>(null)

  // Fetch chapter JSON — React Query caches by [book, chapter, translation]
  const { data, isLoading, isError } = useQuery({
    queryKey: ['chapter', book, chapter, translation],
    queryFn: () => bible.chapter(book, chapter, translation, token),
    staleTime: 5 * 60 * 1000, // chapter text doesn't change; cache 5 min
    enabled: book > 0 && chapter > 0 && translation.length > 0,
  })

  // Delegated click handler — catches [data-verse] and [data-strongs] from any descendant
  const handleContainerClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const verseEl = (e.target as Element).closest('[data-verse]') as HTMLElement | null
      if (verseEl) setVerse(Number(verseEl.dataset.verse))

      const strongsEl = (e.target as Element).closest('[data-strongs]') as HTMLElement | null
      if (strongsEl) openStrongs(strongsEl.dataset.strongs ?? null)
    },
    [setVerse, openStrongs],
  )

  if (isLoading) return <ChapterSkeleton />
  if (isError) {
    toast('Failed to load chapter', 'error')
    return (
      <div className="flex flex-col items-center justify-center py-20 text-text-muted">
        <p>Could not load {book} {chapter}.</p>
      </div>
    )
  }

  return (
    <>
      {/* Chapter heading */}
      <header className="mb-6 border-b border-bg-overlay pb-4">
        <h2 className="text-2xl font-bold text-gold">
          {data?.book_name} {chapter}
        </h2>
        <p className="text-xs text-text-muted mt-1 uppercase tracking-wide">{translation}</p>
      </header>

      {/* Verse list — delegated click for verse selection and Strong's */}
      <div
        ref={containerRef}
        className="scripture-text space-y-2 leading-8 text-text-primary"
        onClick={handleContainerClick}
      >
        {data?.verses.map((v) => (
          <span
            key={v.verse}
            data-verse={v.verse}
            className="cursor-pointer rounded px-0.5 transition-colors hover:bg-bg-elevated"
          >
            <sup className="mr-1 text-xs font-bold text-gold-muted select-none">
              {v.verse}
            </sup>
            {v.text}{' '}
          </span>
        ))}
      </div>

      {/* Strong's lexicon dialog — opens when a tagged word is clicked */}
      {activeStrongs && (
        <StrongsCard
          number={activeStrongs}
          onClose={() => openStrongs(null)}
        />
      )}
    </>
  )
}

function ChapterSkeleton() {
  return (
    <div className="space-y-3 py-4">
      <div className="loading-shimmer h-8 w-48 rounded" />
      {Array.from({ length: 12 }, (_, i) => (
        <div key={i} className="loading-shimmer h-5 rounded" style={{ width: `${60 + (i % 5) * 8}%` }} />
      ))}
    </div>
  )
}

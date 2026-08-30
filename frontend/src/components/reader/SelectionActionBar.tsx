/**
 * SelectionActionBar — floating bar for acting on a tap-number verse
 * selection (single verse or range). Appears whenever useReaderStore.verse
 * is set. Every action here calls an API that already exists and already
 * works (the panels use the same calls for listing/deleting) — this file
 * is the previously-missing piece that actually creates highlights and
 * bookmarks from the reading view.
 *
 * Range handling:
 *   - Highlight applies to every verse in the range (one PUT per verse).
 *   - Bookmark applies to the range's start verse only — a bookmark is a
 *     "return to this spot" marker, not a colored span, so a multi-verse
 *     bookmark isn't meaningful.
 *   - Note is disabled for a range (notes are one-per-verse in the schema);
 *     it opens the existing NotesPanel for the single selected verse.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bookmark, StickyNote, X } from 'lucide-react'
import { bookmarks as bookmarksApi, highlights as highlightsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'

// Same five colors HighlightsPanel already knows how to label.
const HIGHLIGHT_COLORS = ['#ffe066', '#b8f0c8', '#a0c8ff', '#ffb3b3', '#d4b3ff']

interface Props {
  bookName: string
  chapter: number
}

export function SelectionActionBar({ bookName, chapter }: Props) {
  const { token } = useAuthStore()
  const { toast, openPanel } = useUiStore()
  const qc = useQueryClient()
  const { verse, selectionEnd, clearSelection } = useReaderStore()

  // lo/hi collapse to the same value when nothing (or just one verse) is
  // selected — safe to compute unconditionally so every hook below runs on
  // every render, per the Rules of Hooks. The actual "nothing selected"
  // bail-out happens after all hooks are declared, right before the return.
  const lo = verse === null ? 0 : selectionEnd === null ? verse : Math.min(verse, selectionEnd)
  const hi = verse === null ? 0 : selectionEnd === null ? verse : Math.max(verse, selectionEnd)
  const isRange = lo !== hi
  const refFor = (v: number) => `${bookName} ${chapter}:${v}`

  const applyHighlight = useMutation({
    mutationFn: async (color: string) => {
      const verses = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
      await Promise.all(verses.map((v) => highlightsApi.set(refFor(v), color, null, token ?? '')))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['highlights'] })
      toast(isRange ? `Highlighted ${hi - lo + 1} verses` : 'Verse highlighted', 'success')
      clearSelection()
    },
    onError: () => toast('Could not save highlight', 'error'),
  })

  const addBookmark = useMutation({
    mutationFn: () => bookmarksApi.add(refFor(lo), null, '#b8962e', token ?? ''),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bookmarks'] })
      toast('Bookmark added', 'success')
      clearSelection()
    },
    onError: () => toast('Could not add bookmark', 'error'),
  })

  if (verse === null) return null

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-center gap-3 border-t
        border-bg-overlay bg-bg-elevated px-4 py-3 shadow-lg"
      role="toolbar"
      aria-label="Selected verse actions"
    >
      <span className="text-xs text-text-muted mr-1">
        {isRange ? `${bookName} ${chapter}:${lo}-${hi}` : `${bookName} ${chapter}:${lo}`}
      </span>

      <div className="flex items-center gap-1.5">
        {HIGHLIGHT_COLORS.map((color) => (
          <button
            key={color}
            type="button"
            title="Highlight"
            disabled={applyHighlight.isPending}
            onClick={() => applyHighlight.mutate(color)}
            className="h-6 w-6 rounded-full border border-bg-overlay transition-transform hover:scale-110 disabled:opacity-50"
            style={{ background: color }}
          />
        ))}
      </div>

      <button
        type="button"
        title="Bookmark"
        disabled={addBookmark.isPending}
        onClick={() => addBookmark.mutate()}
        className="text-text-muted hover:text-gold transition-colors disabled:opacity-50"
      >
        <Bookmark className="h-4 w-4" />
      </button>

      <button
        type="button"
        title={isRange ? 'Notes apply to a single verse' : 'Add note'}
        disabled={isRange}
        onClick={() => openPanel('notes')}
        className="text-text-muted hover:text-gold transition-colors disabled:opacity-30"
      >
        <StickyNote className="h-4 w-4" />
      </button>

      <button
        type="button"
        title="Clear selection"
        onClick={() => clearSelection()}
        className="text-text-muted hover:text-text-primary transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

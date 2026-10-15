/**
 * SelectionActionBar — compact vertical action block for acting on a
 * tap-number verse selection (single verse or range). Lives in the
 * right-hand tool rail (rendered by App.tsx), not floated over the reading
 * area — it used to be a fixed bottom bar, but that put it directly in the
 * same screen real estate as StrongsCard's mobile bottom sheet: tapping any
 * Strong's-tagged word sets the verse selection AND opens the Strong's card
 * at once, so the two fought over the same strip on nearly every word tap.
 * Moving this into the already-present right rail (there was room) gives
 * each its own space instead of layering them. Appears whenever
 * useReaderStore.verse is set; reads bookName/chapter from the store
 * instead of props now that it's no longer nested inside ChapterView.
 *
 * Every action here calls an API that already exists and already
 * works (the panels use the same calls for listing/deleting) — this file
 * is the previously-missing piece that actually creates highlights and
 * bookmarks from the reading view.
 *
 * Range handling:
 *   - Highlight applies to every verse in the range (one PUT per verse).
 *   - Remove highlight (the eraser icon) deletes any highlight on every
 *     verse in the range (one DELETE per verse) — a no-op per verse that
 *     was never highlighted, per the backend's "silent success" contract,
 *     so it's always safe to show regardless of current highlight state.
 *   - Bookmark is a toggle on the range's start verse only — a bookmark is a
 *     "return to this spot" marker, not a colored span, so a multi-verse
 *     bookmark isn't meaningful. Uses GET /api/bookmarks/check (existed on
 *     the backend with no frontend caller until now) to show filled/gold
 *     when the verse is already bookmarked, and removes on a second tap
 *     instead of just clearing the selection (the "X" only ever clears the
 *     pending selection — it was never a bookmark-remove action, which read
 *     as a bug when there was no other way to un-bookmark from here).
 *   - Note is disabled for a range (notes are one-per-verse in the schema);
 *     it opens the existing NotesPanel for the single selected verse.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftRight, Bookmark, Eraser, StickyNote, X } from 'lucide-react'
import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { bible, bookmarks as bookmarksApi, highlights as highlightsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'

// Same translations offered by the passage-compare picker's default
// selection — kept small since this is a quick inline glance, not the full
// research view (that's ComparePassageView).
const VERSE_COMPARE_TRANSLATIONS = ['KJV', 'ASV', 'YLT', 'Darby']

// Same five colors HighlightsPanel already knows how to label.
const HIGHLIGHT_COLORS = ['#ffe066', '#b8f0c8', '#a0c8ff', '#ffb3b3', '#d4b3ff']

export function SelectionActionBar() {
  const { token } = useAuthStore()
  const { toast, openPanel } = useUiStore()
  const qc = useQueryClient()
  const { bookName, chapter, verse, selectionEnd, clearSelection } = useReaderStore()
  const [compareOpen, setCompareOpen] = useState(false)

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
    onError: (e: Error) => toast(e.message || 'Could not save highlight', 'error'),
  })

  const removeHighlight = useMutation({
    mutationFn: async () => {
      const verses = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
      await Promise.all(verses.map((v) => highlightsApi.remove(refFor(v), token ?? '')))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['highlights'] })
      toast(
        isRange ? `Removed highlight from ${hi - lo + 1} verses` : 'Highlight removed',
        'success',
      )
      clearSelection()
    },
    onError: (e: Error) => toast(e.message || 'Could not remove highlight', 'error'),
  })

  // Single-verse-only, same as Note — a bookmark is a "return here" marker
  // for one spot, not a span, so toggle state only makes sense for the
  // range's start verse. Uses the /api/bookmarks/check endpoint, which
  // existed on the backend with no frontend caller until now.
  const bookmarkRef = refFor(lo)
  const { data: bookmarkStatus } = useQuery({
    queryKey: ['bookmark-check', bookmarkRef],
    queryFn: () => bookmarksApi.check(bookmarkRef, token ?? ''),
    enabled: verse !== null && !!token,
  })

  const addBookmark = useMutation({
    mutationFn: () => bookmarksApi.add(bookmarkRef, null, '#b8962e', token ?? ''),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bookmarks'] })
      qc.invalidateQueries({ queryKey: ['bookmark-check', bookmarkRef] })
      toast('Bookmark added', 'success')
      clearSelection()
    },
    onError: (e: Error) => toast(e.message || 'Could not add bookmark', 'error'),
  })

  const removeBookmark = useMutation({
    mutationFn: () => {
      if (!bookmarkStatus?.id) throw new Error('Bookmark not found')
      return bookmarksApi.remove(bookmarkStatus.id, token ?? '')
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bookmarks'] })
      qc.invalidateQueries({ queryKey: ['bookmark-check', bookmarkRef] })
      toast('Bookmark removed', 'success')
      clearSelection()
    },
    onError: (e: Error) => toast(e.message || 'Could not remove bookmark', 'error'),
  })

  // Single-verse-only — the compare dialog is a quick inline glance, not a
  // range tool. Only fetched once the dialog is actually opened.
  const compareRef = !isRange ? refFor(lo) : ''
  const { data: compareData, isLoading: compareLoading } = useQuery({
    queryKey: ['compare-verse', compareRef],
    queryFn: () => bible.compareVerse(compareRef, VERSE_COMPARE_TRANSLATIONS, token),
    enabled: compareOpen && !isRange,
  })

  if (verse === null) return null

  const ref = isRange ? `${bookName} ${chapter}:${lo}-${hi}` : `${bookName} ${chapter}:${lo}`

  return (
    // Vertical block, sized to match the rail it lives in (App.tsx's
    // right-hand <aside>) — icon buttons stay h-9 w-9 like the persistent
    // TOOL_BUTTONS below it for visual consistency; color swatches shrink
    // to fit the narrow column. No `fixed` positioning — this is a normal
    // flex child of the rail now, not an overlay.
    <div
      className="flex flex-col items-center gap-2 border-b border-bg-overlay pb-3 mb-1 w-full"
      role="toolbar"
      aria-label="Selected verse actions"
    >
      {/* Verse ref has no room to show as text in a ~56px column — carried as
          a title tooltip on the clear button instead (see below). */}
      <div className="flex flex-col items-center gap-1">
        {HIGHLIGHT_COLORS.map((color) => (
          <button
            key={color}
            type="button"
            title="Highlight"
            disabled={applyHighlight.isPending}
            onClick={() => applyHighlight.mutate(color)}
            className="h-5 w-5 rounded-full border border-bg-overlay transition-transform hover:scale-110 disabled:opacity-50"
            style={{ background: color }}
          />
        ))}
        <button
          type="button"
          title="Remove highlight"
          disabled={removeHighlight.isPending}
          onClick={() => removeHighlight.mutate()}
          className="flex h-9 w-9 items-center justify-center text-text-muted hover:text-red-400 transition-colors disabled:opacity-50"
        >
          <Eraser className="h-4 w-4" />
        </button>
      </div>

      <button
        type="button"
        title={bookmarkStatus?.bookmarked ? 'Remove bookmark' : 'Bookmark'}
        disabled={addBookmark.isPending || removeBookmark.isPending}
        onClick={() =>
          bookmarkStatus?.bookmarked ? removeBookmark.mutate() : addBookmark.mutate()
        }
        className={`flex h-9 w-9 items-center justify-center transition-colors disabled:opacity-50 ${
          bookmarkStatus?.bookmarked ? 'text-gold' : 'text-text-muted hover:text-gold'
        }`}
      >
        <Bookmark className="h-4 w-4" fill={bookmarkStatus?.bookmarked ? 'currentColor' : 'none'} />
      </button>

      <button
        type="button"
        title={isRange ? 'Notes apply to a single verse' : 'Add note'}
        disabled={isRange}
        onClick={() => openPanel('notes')}
        className="flex h-9 w-9 items-center justify-center text-text-muted hover:text-gold transition-colors disabled:opacity-30"
      >
        <StickyNote className="h-4 w-4" />
      </button>

      <button
        type="button"
        title={isRange ? 'Compare applies to a single verse' : 'Compare translations'}
        disabled={isRange}
        onClick={() => setCompareOpen(true)}
        className="flex h-9 w-9 items-center justify-center text-text-muted hover:text-gold transition-colors disabled:opacity-30"
      >
        <ArrowLeftRight className="h-4 w-4" />
      </button>

      <button
        type="button"
        title={`Clear selection (${ref})`}
        onClick={() => clearSelection()}
        className="flex h-9 w-9 items-center justify-center text-text-muted hover:text-text-primary transition-colors"
      >
        <X className="h-4 w-4" />
      </button>

      <Dialog open={compareOpen} onOpenChange={setCompareOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{compareRef}</DialogTitle>
          </DialogHeader>
          {compareLoading ? (
            <div className="space-y-2 py-2">
              {[90, 75, 85].map((w, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: static literal array, never reordered/filtered/mutated — decorative shimmer widths, not real data.
                <div key={i} className="loading-shimmer h-5 rounded" style={{ width: `${w}%` }} />
              ))}
            </div>
          ) : (
            <dl className="space-y-3">
              {Object.entries(compareData?.comparisons ?? {}).map(([tr, text]) => (
                <div key={tr}>
                  <dt className="text-xs font-bold text-gold-muted uppercase tracking-wide">
                    {tr}
                  </dt>
                  <dd className="text-sm text-text-primary leading-6 mt-0.5">{text}</dd>
                </div>
              ))}
            </dl>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

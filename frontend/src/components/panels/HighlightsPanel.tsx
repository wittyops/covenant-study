/**
 * HighlightsPanel — list all verse highlights with colour swatches.
 * Clicking a row navigates to that reference; the X button removes it.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Highlighter, X } from 'lucide-react'
import { bible, highlights as highlightsApi } from '@/lib/api'
import type { Highlight } from '@/lib/types'
import { parseRef } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'

// Human-readable names for the five highlight colours
const COLOUR_LABELS: Record<string, string> = {
  '#ffe066': 'Yellow',
  '#b8f0c8': 'Green',
  '#a0c8ff': 'Blue',
  '#ffb3b3': 'Red',
  '#d4b3ff': 'Purple',
}

export function HighlightsPanel() {
  const { token } = useAuthStore()
  const { navigate } = useReaderStore()
  const { toast, closePanel } = useUiStore()
  const qc = useQueryClient()

  const { data = [], isLoading } = useQuery({
    queryKey: ['highlights'],
    queryFn: () => highlightsApi.list(token ?? ''),
    enabled: !!token,
  })

  // Refs only carry the book's display name ("John 3:16"), not its numeric
  // id, so resolving a click to an actual navigate() call needs the same
  // book list the picker uses. Cheap and already cached app-wide.
  const { data: books = [] } = useQuery({
    queryKey: ['books'],
    queryFn: () => bible.books(token),
    staleTime: Infinity,
  })

  const remove = useMutation({
    mutationFn: (ref: string) => highlightsApi.remove(ref, token ?? ''),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['highlights'] }),
    onError: () => toast('Could not remove highlight', 'error'),
  })

  function goTo(ref: string) {
    const parsed = parseRef(ref)
    if (!parsed) return
    const book = books.find((b) => b.name === parsed.book)
    if (!book) {
      toast(`Could not find "${parsed.book}" in the book list`, 'error')
      return
    }
    navigate(book.book, parsed.chapter, parsed.verse)
    closePanel()
  }

  if (isLoading)
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="loading-shimmer h-12 rounded-lg" />
        ))}
      </div>
    )

  if (!data.length)
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-text-muted">
        <Highlighter className="h-10 w-10 opacity-30" />
        <p className="text-sm">No highlights yet.</p>
        <p className="text-xs">Long-press a verse to highlight it.</p>
      </div>
    )

  // Group highlights by colour for visual scanning
  const byColour = data.reduce<Record<string, Highlight[]>>((acc, h) => {
    if (!acc[h.color]) acc[h.color] = []
    acc[h.color].push(h)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {Object.entries(byColour).map(([colour, items]) => (
        <div key={colour}>
          <div className="mb-1.5 flex items-center gap-2">
            <span className="h-3 w-3 rounded-full" style={{ background: colour }} />
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              {COLOUR_LABELS[colour] ?? colour}
            </span>
          </div>
          <ul className="space-y-0.5">
            {items.map((h) => (
              <li
                key={h.ref}
                className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-bg-elevated group"
              >
                <button
                  type="button"
                  onClick={() => goTo(h.ref)}
                  className="flex-1 text-left text-sm text-text-primary"
                >
                  {h.ref}
                </button>
                {h.note && (
                  <span className="max-w-[120px] truncate text-xs text-text-muted">{h.note}</span>
                )}
                <button
                  type="button"
                  onClick={() => remove.mutate(h.ref)}
                  className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-red-400 transition"
                  title="Remove highlight"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

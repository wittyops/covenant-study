/**
 * BookmarksPanel — lists the user's bookmarks, navigate or delete each one.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bookmark, ChevronRight, Trash2 } from 'lucide-react'
import { bible, bookmarks as bookmarksApi } from '@/lib/api'
import type { Bookmark as BookmarkType } from '@/lib/types'
import { parseRef, relativeTime } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'

export function BookmarksPanel() {
  const { token } = useAuthStore()
  const { navigate } = useReaderStore()
  const { toast, closePanel } = useUiStore()
  const qc = useQueryClient()

  const { data = [], isLoading } = useQuery({
    queryKey: ['bookmarks'],
    queryFn: () => bookmarksApi.list(token ?? ''),
    enabled: !!token,
  })

  // Refs only carry the book's display name ("John 3:16"), not its numeric
  // id, so resolving a click to an actual navigate() call needs the book
  // list to map name -> id. Cheap and already cached app-wide.
  const { data: books = [] } = useQuery({
    queryKey: ['books'],
    queryFn: () => bible.books(token),
    staleTime: Infinity,
  })

  const remove = useMutation({
    mutationFn: (id: number) => bookmarksApi.remove(id, token ?? ''),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bookmarks'] }),
    onError: () => toast('Could not remove bookmark', 'error'),
  })

  function goTo(bm: BookmarkType) {
    const parsed = parseRef(bm.ref)
    if (!parsed) return
    const book = books.find((b) => b.name === parsed.book)
    if (!book) {
      toast(`Could not find "${parsed.book}" in the book list`, 'error')
      return
    }
    navigate(book.book, parsed.chapter, parsed.verse)
    closePanel()
  }

  if (isLoading) return <PanelSkeleton />

  if (!data.length)
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-text-muted">
        <Bookmark className="h-10 w-10 opacity-30" />
        <p className="text-sm">No bookmarks yet.</p>
        <p className="text-xs">Long-press a verse to bookmark it.</p>
      </div>
    )

  return (
    <ul className="space-y-1">
      {data.map((bm) => (
        <li
          key={bm.id}
          className="flex items-center gap-2 rounded-lg px-3 py-2.5 hover:bg-bg-elevated group"
        >
          {/* Colour swatch */}
          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: bm.color }} />

          {/* Ref + timestamp */}
          <button type="button" className="flex-1 text-left" onClick={() => goTo(bm)}>
            <p className="text-sm font-medium text-text-primary">{bm.ref}</p>
            {bm.label && <p className="text-xs text-text-muted truncate">{bm.label}</p>}
            <p className="text-xs text-text-muted">{relativeTime(bm.created_at)}</p>
          </button>

          {/* Navigate arrow */}
          <ChevronRight className="h-3.5 w-3.5 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />

          {/* Delete */}
          <button
            type="button"
            onClick={() => remove.mutate(bm.id)}
            className="text-text-muted hover:text-red-400 transition-colors"
            title="Remove bookmark"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </li>
      ))}
    </ul>
  )
}

function PanelSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="loading-shimmer h-14 rounded-lg" />
      ))}
    </div>
  )
}

/**
 * NotesPanel — inline note editor for the current verse reference.
 * Notes are per-ref, stored via PUT /api/notes/{ref}.
 */
import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Save, StickyNote } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'
import { notes as notesApi } from '@/lib/api'
import { Button } from '@/components/ui/button'

export function NotesPanel() {
  const { token } = useAuthStore()
  const { book, chapter, verse } = useReaderStore()
  const { toast } = useUiStore()

  // Build ref from current position — default to chapter if no verse selected
  const ref = verse ? `${book} ${chapter}:${verse}` : `${book} ${chapter}`

  const { data, isLoading } = useQuery({
    queryKey: ['note', ref],
    queryFn: () => notesApi.get(ref, token!),
    enabled: !!token,
  })

  const [body, setBody] = useState('')
  useEffect(() => { setBody(data?.body ?? '') }, [data?.body])

  const save = useMutation({
    mutationFn: () => notesApi.save(ref, body, token!),
    onSuccess: () => toast('Note saved', 'success'),
    onError: () => toast('Could not save note', 'error'),
  })

  if (isLoading) return <div className="loading-shimmer h-40 rounded-lg" />

  return (
    <div className="flex flex-col gap-3">
      {/* Context header */}
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <StickyNote className="h-3.5 w-3.5" />
        <span>Note for <span className="text-text-secondary font-medium">{ref}</span></span>
      </div>

      {/* Hint when no verse is selected */}
      {!verse && (
        <p className="text-xs text-text-muted italic">
          Tap a verse number to anchor this note to a specific verse.
        </p>
      )}

      {/* Editor */}
      <textarea
        className="min-h-[200px] w-full resize-y rounded-lg border border-bg-overlay bg-bg-elevated
          px-3 py-2 text-sm text-text-primary placeholder:text-text-muted
          focus:border-gold focus:outline-none focus:ring-1 focus:ring-gold"
        placeholder="Write your study notes here…"
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />

      <Button
        size="sm"
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="self-end gap-1.5"
      >
        <Save className="h-3.5 w-3.5" />
        {save.isPending ? 'Saving…' : 'Save'}
      </Button>
    </div>
  )
}

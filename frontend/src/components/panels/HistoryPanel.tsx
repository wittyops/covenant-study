/**
 * HistoryPanel — recent reading history, click any entry to return to it.
 */
import { useQuery } from '@tanstack/react-query'
import { Clock } from 'lucide-react'
import { history as historyApi } from '@/lib/api'
import { relativeTime } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'

export function HistoryPanel() {
  const { token } = useAuthStore()
  const { navigate } = useReaderStore()
  const { closePanel } = useUiStore()

  const { data = [], isLoading } = useQuery({
    queryKey: ['history'],
    queryFn: () => historyApi.list(token ?? ''),
    enabled: !!token,
    // History can change on every chapter load — keep it fresh
    staleTime: 30 * 1000,
  })

  function goTo(ref: string) {
    const m = ref.match(/^(.+)\s+(\d+):(\d+)$/)
    if (m) navigate(parseInt(m[2], 10), parseInt(m[3], 10))
    closePanel()
  }

  if (isLoading)
    return (
      <div className="space-y-1.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="loading-shimmer h-10 rounded" />
        ))}
      </div>
    )

  if (!data.length)
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-text-muted">
        <Clock className="h-10 w-10 opacity-30" />
        <p className="text-sm">No reading history yet.</p>
      </div>
    )

  return (
    <ul className="space-y-0.5">
      {data.map((entry, i) => (
        <li key={`${entry.ref}-${i}`}>
          <button
            type="button"
            onClick={() => goTo(entry.ref)}
            className="flex w-full items-center justify-between rounded px-3 py-2
              text-left hover:bg-bg-elevated transition-colors group"
          >
            <span className="text-sm text-text-primary group-hover:text-gold transition-colors">
              {entry.ref}
            </span>
            <span className="text-xs text-text-muted">{relativeTime(entry.visited_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Badge } from '@/components/ui/badge'
import { bible } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

interface Props {
  number: string
  onClose: () => void
}

export function StrongsCard({ number, onClose }: Props) {
  const { token } = useAuthStore()
  const panelRef = useRef<HTMLElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['strongs', number],
    queryFn: () => bible.strongs(number, token),
    staleTime: Infinity,
  })

  // Dismiss on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Dismiss on click outside the panel
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        // Only close if the click wasn't on a tagged word (ChapterView handles that)
        const target = e.target as Element
        if (!target.closest('[data-strongs]')) onClose()
      }
    }
    // Delay so the opening click doesn't immediately close the panel
    const id = setTimeout(() => document.addEventListener('mousedown', handler), 50)
    return () => {
      clearTimeout(id)
      document.removeEventListener('mousedown', handler)
    }
  }, [onClose])

  return (
    <aside
      ref={panelRef}
      aria-label={`Strong's ${number}`}
      className={[
        'fixed bottom-0 left-0 right-0 z-40',
        'sm:bottom-4 sm:right-4 sm:left-auto sm:w-96',
        'bg-bg-surface border border-bg-overlay shadow-2xl',
        'rounded-t-2xl sm:rounded-2xl',
        'p-5 pb-6',
        'animate-slide-up sm:animate-slide-in-right',
        'max-h-[60vh] overflow-y-auto',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <Badge variant="gold" className="text-base px-3 py-1 font-mono shrink-0">
            {number}
          </Badge>
          <div>
            <p className="text-xl font-bold text-text-primary leading-tight">
              {isLoading ? '…' : data?.word}
            </p>
            {data && (
              <p className="font-mono text-sm text-text-secondary mt-0.5">
                {data.transliteration} · {data.pronunciation}
              </p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-text-muted hover:text-text-primary transition-colors shrink-0 mt-0.5"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Loading shimmer */}
      {isLoading && (
        <div className="space-y-2">
          {[40, 70, 55, 80].map((w, i) => (
            <div key={i} className="loading-shimmer h-4 rounded" style={{ width: `${w}%` }} />
          ))}
        </div>
      )}

      {/* Content */}
      {data && (
        <div className="space-y-4 text-sm">
          <Badge variant="outline">{data.language}</Badge>

          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
              Definition
            </h4>
            <p className="text-text-primary leading-relaxed select-text">{data.definition}</p>
          </div>

          {data.derivation && (
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
                Derivation
              </h4>
              <p className="text-text-secondary leading-relaxed select-text">{data.derivation}</p>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

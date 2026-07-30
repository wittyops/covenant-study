/**
 * StrongsCard — modal dialog showing the Strong's lexicon entry for a word.
 * Opened by clicking a tagged word in ChapterView.
 */
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth'
import { bible } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'

interface Props {
  number:  string
  onClose: () => void
}

export function StrongsCard({ number, onClose }: Props) {
  const { token } = useAuthStore()

  const { data, isLoading } = useQuery({
    queryKey: ['strongs', number],
    queryFn: () => bible.strongs(number, token),
    staleTime: Infinity, // lexicon entries never change
  })

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <Badge variant="gold" className="text-lg px-3 py-1 font-mono">
              {number}
            </Badge>
            <div>
              <DialogTitle className="text-xl">
                {isLoading ? '…' : data?.word}
              </DialogTitle>
              {data && (
                <DialogDescription className="font-mono text-sm text-text-secondary">
                  {data.transliteration} · {data.pronunciation}
                </DialogDescription>
              )}
            </div>
          </div>
        </DialogHeader>

        {isLoading && (
          <div className="space-y-2">
            {[40, 70, 55, 80].map((w, i) => (
              <div key={i} className="loading-shimmer h-4 rounded" style={{ width: `${w}%` }} />
            ))}
          </div>
        )}

        {data && (
          <div className="space-y-4 text-sm">
            {/* Language tag */}
            <Badge variant="outline">{data.language}</Badge>

            {/* Definition */}
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
                Definition
              </h4>
              <p className="text-text-primary leading-relaxed">{data.definition}</p>
            </div>

            {/* Derivation */}
            {data.derivation && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Derivation
                </h4>
                <p className="text-text-secondary leading-relaxed">{data.derivation}</p>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

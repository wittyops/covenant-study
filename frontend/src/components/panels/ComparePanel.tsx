/**
 * ComparePanel — translation picker for full-passage comparison.
 *
 * Lives in the tool rail like the other panels. Pick up to 4 translations,
 * hit Compare, and the reader's main content area switches to
 * ComparePassageView for the current book/chapter (see stores/ui.ts
 * startCompare()/stopCompare()) — this panel only decides *which*
 * translations, not how they're laid out.
 */
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { bible } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useUiStore } from '@/stores/ui'

const MAX_COMPARE = 4

export function ComparePanel() {
  const { token } = useAuthStore()
  const { translation } = useReaderStore()
  const { startCompare } = useUiStore()

  const { data: translations = [], isLoading } = useQuery({
    queryKey: ['translations'],
    queryFn: () => bible.translations(token),
    staleTime: Infinity,
  })

  const [selected, setSelected] = useState<string[]>(() =>
    Array.from(new Set([translation, 'KJV', 'ASV'])).slice(0, MAX_COMPARE),
  )

  function toggle(id: string) {
    setSelected((cur) => {
      if (cur.includes(id)) return cur.filter((t) => t !== id)
      if (cur.length >= MAX_COMPARE) return cur
      return [...cur, id]
    })
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-text-muted px-0.5">
        Pick up to {MAX_COMPARE} translations to read the current chapter side by side.
      </p>

      {isLoading ? (
        <div className="space-y-2 pt-1">
          {[80, 60, 90, 70].map((w, i) => (
            <div key={i} className="loading-shimmer h-8 rounded-lg" style={{ width: `${w}%` }} />
          ))}
        </div>
      ) : (
        <ul className="space-y-1 max-h-[50vh] overflow-y-auto">
          {translations.map((t) => {
            const checked = selected.includes(t.id)
            const disabled = !checked && selected.length >= MAX_COMPARE
            return (
              <li key={t.id}>
                <label
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors
                    ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:bg-bg-elevated'}`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={disabled}
                    onChange={() => toggle(t.id)}
                    className="accent-gold h-3.5 w-3.5"
                  />
                  <span className="text-text-primary">{t.name}</span>
                </label>
              </li>
            )
          })}
        </ul>
      )}

      <button
        type="button"
        disabled={selected.length === 0}
        onClick={() => startCompare(selected)}
        className="mt-1 rounded-lg bg-gold px-3 py-2 text-sm font-semibold text-bg-base
          transition-opacity hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Compare {selected.length ? `(${selected.length})` : ''}
      </button>
    </div>
  )
}

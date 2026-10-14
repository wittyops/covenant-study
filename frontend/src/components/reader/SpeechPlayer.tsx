/**
 * SpeechPlayer — floating pill shown while read-aloud is active (see
 * stores/speech.ts). Rendered unconditionally in App.tsx; returns null
 * when nothing is speaking, same pattern as ToastStack.
 *
 * Positioned above NavBar (h-14, 56px) with headroom to also clear
 * SelectionActionBar when both happen to be visible at once (reading aloud
 * while also mid-verse-selection) — not pixel-perfect for every
 * combination, but avoids the common overlap case.
 */
import { Gauge, Pause, Play, Square } from 'lucide-react'
import { useSpeechStore } from '@/stores/speech'

export function SpeechPlayer() {
  const { speaking, paused, label, rate, pause, resume, stop, cycleRate } = useSpeechStore()

  if (!speaking) return null

  return (
    <div
      role="status"
      className="fixed bottom-20 right-4 z-40 flex items-center gap-2 rounded-full border border-bg-overlay bg-bg-surface px-3 py-2 shadow-xl animate-fade-in"
    >
      <button
        type="button"
        title={paused ? 'Resume' : 'Pause'}
        aria-label={paused ? 'Resume reading' : 'Pause reading'}
        onClick={paused ? resume : pause}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-gold text-bg-base hover:bg-gold-dark transition-colors"
      >
        {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
      </button>

      <span className="max-w-[9rem] truncate text-xs text-text-secondary">
        {paused ? 'Paused — ' : 'Reading — '}
        {label}
      </span>

      <button
        type="button"
        title="Playback speed"
        aria-label={`Playback speed, currently ${rate}x`}
        onClick={cycleRate}
        className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
      >
        <Gauge className="h-3.5 w-3.5" />
        {rate}x
      </button>

      <button
        type="button"
        title="Stop reading"
        aria-label="Stop reading"
        onClick={stop}
        className="flex h-8 w-8 items-center justify-center rounded-full text-text-muted hover:text-red-400 hover:bg-bg-elevated transition-colors"
      >
        <Square className="h-3 w-3" />
      </button>
    </div>
  )
}

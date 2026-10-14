/**
 * Speech store — read-aloud via the browser's built-in Web Speech API
 * (window.speechSynthesis). No backend involved: this is entirely
 * client-side, so voice quality and availability depend on the device/OS,
 * and playback is NOT guaranteed to continue once the tab is backgrounded
 * or the phone is locked (a real limitation on iOS Safari in particular —
 * speechSynthesis commonly pauses there). Good enough for "read this
 * chapter to me while I'm doing something else on this device/tab"; not a
 * true background-audio experience like a podcast player. See
 * [[project_covenant_study_hang_bug_and_hardening_2026_10_14]] for the
 * tradeoff discussion — a server-rendered-audio approach was the
 * alternative and can replace this later without changing the UI contract
 * (speak/pause/resume/stop/setRate).
 */
import { create } from 'zustand'

export const SPEECH_RATE_STEPS = [0.75, 1, 1.25, 1.5] as const

interface SpeechState {
  speaking: boolean
  paused: boolean
  rate: number
  /** Label for what's currently queued, e.g. "Genesis 1" — shown in the player. */
  label: string | null

  speak(text: string, label: string): void
  pause(): void
  resume(): void
  stop(): void
  cycleRate(): void
}

function supported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

// Chrome/Chromium has a long-standing bug where speechSynthesis silently
// stops after ~15 seconds on a single utterance — no onerror, no onend,
// it just goes quiet. Since almost every chapter takes well over 15
// seconds to read, this would make "read aloud" appear to work for a
// sentence or two and then mysteriously die on real content, defeating
// the point of the feature. The standard workaround (used by most
// speechSynthesis libraries): resume-after-pause on a timer resets
// Chrome's internal watchdog. Module-level, not store state, because it's
// a side-channel implementation detail, not something any UI reads.
const KEEP_ALIVE_INTERVAL_MS = 10_000
let keepAliveTimer: ReturnType<typeof setInterval> | null = null

function stopKeepAlive() {
  if (keepAliveTimer !== null) {
    clearInterval(keepAliveTimer)
    keepAliveTimer = null
  }
}

function startKeepAlive() {
  stopKeepAlive()
  keepAliveTimer = setInterval(() => {
    // Skip the tick if the user paused it themselves — pause()/resume()
    // here would silently override their intent.
    if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
      window.speechSynthesis.pause()
      window.speechSynthesis.resume()
    }
  }, KEEP_ALIVE_INTERVAL_MS)
}

export const useSpeechStore = create<SpeechState>()((set, get) => ({
  speaking: false,
  paused: false,
  rate: SPEECH_RATE_STEPS[1],
  label: null,

  speak(text, label) {
    if (!supported()) return
    window.speechSynthesis.cancel() // clear anything already queued/speaking

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = get().rate
    utterance.onend = () => {
      stopKeepAlive()
      set({ speaking: false, paused: false, label: null })
    }
    utterance.onerror = () => {
      stopKeepAlive()
      set({ speaking: false, paused: false, label: null })
    }

    window.speechSynthesis.speak(utterance)
    startKeepAlive()
    set({ speaking: true, paused: false, label })
  },

  pause() {
    if (!supported()) return
    window.speechSynthesis.pause()
    set({ paused: true })
  },

  resume() {
    if (!supported()) return
    window.speechSynthesis.resume()
    set({ paused: false })
  },

  stop() {
    if (!supported()) return
    stopKeepAlive()
    window.speechSynthesis.cancel()
    set({ speaking: false, paused: false, label: null })
  },

  cycleRate() {
    const i = SPEECH_RATE_STEPS.indexOf(get().rate as (typeof SPEECH_RATE_STEPS)[number])
    const next = SPEECH_RATE_STEPS[(i + 1) % SPEECH_RATE_STEPS.length]
    set({ rate: next })
    // Rate only takes effect on the next speak() call — the Web Speech API
    // has no way to change the rate of an utterance already in progress.
  },
}))

export const speechSupported = supported

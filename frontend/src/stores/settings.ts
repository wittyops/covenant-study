/**
 * Settings store — accessibility/display preferences, persisted per device.
 *
 * Separate from reader.ts (which persists reading *position*) because this
 * is a display preference, not navigation state — keeping them apart means
 * a future "reset reading position" action can't accidentally also wipe
 * someone's chosen text size.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// 1.0 = the CSS base size baked into .readable-text. Six steps from "small"
// to "extra large" — enough range for genuine low-vision use without
// stepping so finely that +/- feels like it's doing nothing.
export const FONT_SCALE_STEPS = [0.85, 1, 1.15, 1.3, 1.5, 1.75] as const
const DEFAULT_STEP_INDEX = 1 // → 1.0

interface SettingsState {
  fontScale: number

  increaseFontScale(): void
  decreaseFontScale(): void
  resetFontScale(): void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      fontScale: FONT_SCALE_STEPS[DEFAULT_STEP_INDEX],

      increaseFontScale() {
        const i = FONT_SCALE_STEPS.indexOf(get().fontScale as (typeof FONT_SCALE_STEPS)[number])
        const next = FONT_SCALE_STEPS[Math.min(FONT_SCALE_STEPS.length - 1, i + 1)]
        set({ fontScale: next })
      },

      decreaseFontScale() {
        const i = FONT_SCALE_STEPS.indexOf(get().fontScale as (typeof FONT_SCALE_STEPS)[number])
        const next = FONT_SCALE_STEPS[Math.max(0, i - 1)]
        set({ fontScale: next })
      },

      resetFontScale() {
        set({ fontScale: FONT_SCALE_STEPS[DEFAULT_STEP_INDEX] })
      },
    }),
    { name: 'covenant-settings' },
  ),
)

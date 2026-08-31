/**
 * UI store — panel visibility, toast queue, search overlay.
 * This state is session-only (not persisted) since it represents transient UI state.
 */
import { create } from 'zustand'
import type { PanelId } from '@/lib/types'

export interface Toast {
  id: number
  message: string
  type: 'info' | 'success' | 'error' | 'warning'
}

interface UiState {
  activePanel: PanelId
  sidebarOpen: boolean
  searchOpen: boolean
  userMenuOpen: boolean
  toasts: Toast[]
  _toastSeq: number

  // Passage compare mode — replaces ChapterView's main content with
  // ComparePassageView while active. Separate from activePanel/sidebarOpen
  // since the compare picker (a panel) and the compare view (the main
  // content area) are two different pieces of UI.
  compareActive: boolean
  compareTranslations: string[]

  openPanel(id: PanelId): void
  closePanel(): void
  togglePanel(id: PanelId): void
  setSidebarOpen(v: boolean): void
  setSearchOpen(v: boolean): void
  setUserMenuOpen(v: boolean): void
  startCompare(translations: string[]): void
  stopCompare(): void

  // Pushes a toast that auto-dismisses after `ms` milliseconds (default 3500)
  toast(message: string, type?: Toast['type'], ms?: number): void
  dismissToast(id: number): void
}

export const useUiStore = create<UiState>()((set, get) => ({
  activePanel: null,
  sidebarOpen: false,
  searchOpen: false,
  userMenuOpen: false,
  toasts: [],
  _toastSeq: 0,
  compareActive: false,
  compareTranslations: [],

  openPanel(id) {
    set({ activePanel: id, sidebarOpen: true })
  },
  closePanel() {
    set({ activePanel: null, sidebarOpen: false })
  },
  togglePanel(id) {
    const { activePanel, sidebarOpen } = get()
    if (activePanel === id && sidebarOpen) {
      set({ activePanel: null, sidebarOpen: false })
    } else {
      set({ activePanel: id, sidebarOpen: true })
    }
  },
  setSidebarOpen(v) {
    set({ sidebarOpen: v })
  },
  setSearchOpen(v) {
    set({ searchOpen: v })
  },
  setUserMenuOpen(v) {
    set({ userMenuOpen: v })
  },
  startCompare(translations) {
    set({
      compareActive: true,
      compareTranslations: translations,
      activePanel: null,
      sidebarOpen: false,
    })
  },
  stopCompare() {
    set({ compareActive: false })
  },

  toast(message, type = 'info', ms = 3500) {
    const id = get()._toastSeq + 1
    set((s) => ({ _toastSeq: id, toasts: [...s.toasts, { id, message, type }] }))
    setTimeout(() => get().dismissToast(id), ms)
  },

  dismissToast(id) {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
  },
}))

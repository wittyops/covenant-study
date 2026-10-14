/**
 * App — main reader shell, rendered when the user is authenticated.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────┐
 *   │  Header: book/chapter nav, translation, user menu   │
 *   ├─────────────────────────────────────────────────────┤
 *   │  Chapter content (ChapterView)                      │
 *   │                                                     │
 *   │                                           Tool rail │
 *   └─────────────────────────────────────────────────────┘
 *
 * Tool panels (bookmarks, notes, etc.) slide in from the right via Sheet.
 */

import {
  Bookmark,
  BookOpen,
  Clock,
  Columns2,
  Highlighter,
  LogOut,
  Map as MapIcon,
  Settings,
  Shield,
  StickyNote,
  User as UserIcon,
} from 'lucide-react'
import { useLayoutEffect, useState } from 'react'
import { AuthGate } from '@/components/auth/AuthGate'
import { AccountPanel } from '@/components/panels/AccountPanel'
import { AdminPanel } from '@/components/panels/AdminPanel'
import { BookmarksPanel } from '@/components/panels/BookmarksPanel'
import { ComparePanel } from '@/components/panels/ComparePanel'
import { HighlightsPanel } from '@/components/panels/HighlightsPanel'
import { HistoryPanel } from '@/components/panels/HistoryPanel'
import { MapsPanel } from '@/components/panels/MapsPanel'
import { NotesPanel } from '@/components/panels/NotesPanel'
import { BookPicker } from '@/components/reader/BookPicker'
import { ChapterView } from '@/components/reader/ChapterView'
import { ComparePassageView } from '@/components/reader/ComparePassageView'
import { NavBar } from '@/components/reader/NavBar'
import { SpeechPlayer } from '@/components/reader/SpeechPlayer'
import { TranslationPicker } from '@/components/reader/TranslationPicker'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { PanelId } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'

export default function App() {
  return (
    <AuthGate>
      <ReaderShell />
    </AuthGate>
  )
}

function ReaderShell() {
  const { user, logout } = useAuthStore()
  const { toast, activePanel, togglePanel, compareActive } = useUiStore()
  const { fontScale } = useSettingsStore()
  const [bookPickerOpen, setBookPickerOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  // Sync the persisted font-scale preference onto :root as a CSS custom
  // property. Done here (once, at the shell level) rather than scattering
  // inline styles through every component that wants to scale — any
  // element can opt in later via the .readable-text class. useLayoutEffect
  // (not useEffect) so this applies before the browser paints — otherwise
  // a returning visitor briefly sees text at the wrong size for one frame
  // before their saved preference kicks in, which undercuts the whole
  // point of an accessibility setting.
  useLayoutEffect(() => {
    document.documentElement.style.setProperty('--reading-font-scale', String(fontScale))
  }, [fontScale])

  async function handleLogout() {
    await logout()
    toast('Signed out', 'success')
  }

  return (
    <div className="flex h-screen flex-col bg-bg-base overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className="flex items-center gap-2 border-b border-bg-overlay bg-bg-surface px-4 py-2 shrink-0">
        {/* Book picker trigger */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setBookPickerOpen(true)}
          className="gap-1.5 font-medium"
        >
          <BookOpen className="h-4 w-4 text-gold" />
          <span className="hidden sm:inline">Books</span>
        </Button>

        {/* Translation picker */}
        <TranslationPicker />

        {/* Spacer */}
        <div className="flex-1" />

        {/* User menu (simplified — full dropdown can be added in a follow-up) */}
        <div className="relative">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="gap-1.5"
          >
            <UserIcon className="h-4 w-4" />
            <span className="hidden sm:inline text-sm">{user?.display_name ?? user?.username}</span>
          </Button>

          {userMenuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-full z-50 mt-1 w-44 rounded-lg border border-bg-overlay bg-bg-surface py-1 shadow-xl"
              onMouseLeave={() => setUserMenuOpen(false)}
            >
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
                onClick={() => {
                  setUserMenuOpen(false)
                  togglePanel('account')
                }}
              >
                <Settings className="h-3.5 w-3.5" />
                Account Settings
              </button>
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
                onClick={handleLogout}
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chapter content — swaps to the full-passage compare view while active */}
        <main
          className={`flex-1 overflow-y-auto px-6 py-8 w-full ${
            compareActive ? 'max-w-5xl mx-auto' : 'max-w-3xl mx-auto'
          }`}
        >
          {compareActive ? <ComparePassageView /> : <ChapterView />}
        </main>

        {/* Tool rail — vertical icon strip */}
        <aside className="flex flex-col items-center gap-1 border-l border-bg-overlay bg-bg-surface px-2 py-4 shrink-0">
          {TOOL_BUTTONS.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              type="button"
              title={label}
              onClick={() => togglePanel(id)}
              className={`flex h-9 w-9 items-center justify-center rounded transition-colors
                ${
                  activePanel === id
                    ? 'bg-gold-subtle text-gold'
                    : 'text-text-muted hover:text-text-primary hover:bg-bg-elevated'
                }`}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
          {user?.role === 'admin' && (
            <>
              <div className="my-1 w-5 border-t border-bg-overlay" />
              <button
                type="button"
                title="Administration"
                onClick={() => togglePanel('admin')}
                className={`flex h-9 w-9 items-center justify-center rounded transition-colors
                  ${
                    activePanel === 'admin'
                      ? 'bg-gold-subtle text-gold'
                      : 'text-text-muted hover:text-text-primary hover:bg-bg-elevated'
                  }`}
              >
                <Shield className="h-4 w-4" />
              </button>
            </>
          )}
        </aside>
      </div>

      {/* ── Bottom nav bar — book/chapter jump + text size ────────────── */}
      <NavBar />

      {/* ── Tool panels ────────────────────────────────────────────── */}
      {/* Each panel slides in from the right as a Sheet.
          activePanel drives which content component is rendered inside. */}
      <ToolSheet />

      {/* Book picker sheet (left side) */}
      <BookPicker open={bookPickerOpen} onClose={() => setBookPickerOpen(false)} />

      {/* Read-aloud mini-player — floats above NavBar while active */}
      <SpeechPlayer />

      {/* Toast stack */}
      <ToastStack />
    </div>
  )
}

// Panel titles shown in the Sheet header
const PANEL_META: Record<string, string> = {
  bookmarks: 'Bookmarks',
  notes: 'Notes',
  highlights: 'Highlights',
  history: 'Reading History',
  map: 'Bible Map',
  compare: 'Compare Translations',
  admin: 'Administration',
  account: 'Account Settings',
}

// Renders the correct panel content inside the Sheet
function PanelContent({ id }: { id: PanelId }) {
  if (id === 'bookmarks') return <BookmarksPanel />
  if (id === 'notes') return <NotesPanel />
  if (id === 'highlights') return <HighlightsPanel />
  if (id === 'history') return <HistoryPanel />
  if (id === 'map') return <MapsPanel />
  if (id === 'compare') return <ComparePanel />
  if (id === 'admin') return <AdminPanel />
  if (id === 'account') return <AccountPanel />
  return null
}

// Slide-in Sheet that houses all tool panels
function ToolSheet() {
  const { activePanel, sidebarOpen, closePanel } = useUiStore()
  return (
    <Sheet
      open={sidebarOpen}
      onOpenChange={(open) => {
        if (!open) closePanel()
      }}
    >
      <SheetContent side="right" className="w-[340px] overflow-y-auto pb-10">
        <SheetHeader>
          <SheetTitle>{activePanel ? (PANEL_META[activePanel] ?? 'Tools') : 'Tools'}</SheetTitle>
        </SheetHeader>
        <div className="mt-4">
          <PanelContent id={activePanel} />
        </div>
      </SheetContent>
    </Sheet>
  )
}

// Tool rail button definitions
const TOOL_BUTTONS = [
  { id: 'bookmarks' as const, icon: Bookmark, label: 'Bookmarks' },
  { id: 'notes' as const, icon: StickyNote, label: 'Notes' },
  { id: 'highlights' as const, icon: Highlighter, label: 'Highlights' },
  { id: 'history' as const, icon: Clock, label: 'History' },
  { id: 'map' as const, icon: MapIcon, label: 'Bible Map' },
  { id: 'compare' as const, icon: Columns2, label: 'Compare Translations' },
]

// Minimal toast renderer — replaces Alpine's $store.ui.toasts
function ToastStack() {
  const { toasts, dismissToast } = useUiStore()
  if (!toasts.length) return null

  const colourMap: Record<string, string> = {
    info: 'bg-bg-elevated border-bg-overlay text-text-primary',
    success: 'bg-bg-elevated border-gold       text-gold',
    error: 'bg-bg-elevated border-red-700    text-red-400',
    warning: 'bg-bg-elevated border-gold-muted text-gold',
  }

  return (
    // bottom-36 clears both NavBar (h-14) and the SpeechPlayer pill that
    // floats just above it, so a toast never overlaps either.
    <div className="fixed bottom-36 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm shadow-xl
            animate-fade-in ${colourMap[t.type] ?? colourMap.info}`}
          onClick={() => dismissToast(t.id)}
        >
          {t.message}
        </button>
      ))}
    </div>
  )
}

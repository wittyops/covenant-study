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
import { useState } from 'react'
import { useReaderStore } from '@/stores/reader'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { ChapterView } from '@/components/reader/ChapterView'
import { BookPicker } from '@/components/reader/BookPicker'
import { TranslationPicker } from '@/components/reader/TranslationPicker'
import { AuthGate } from '@/components/auth/AuthGate'
import { BookmarksPanel } from '@/components/panels/BookmarksPanel'
import { NotesPanel } from '@/components/panels/NotesPanel'
import { HighlightsPanel } from '@/components/panels/HighlightsPanel'
import { HistoryPanel } from '@/components/panels/HistoryPanel'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import {
  BookOpen, ChevronLeft, ChevronRight, Bookmark, StickyNote,
  Highlighter, Clock, Map, LogOut, User as UserIcon,
} from 'lucide-react'
import type { PanelId } from '@/lib/types'

export default function App() {
  return (
    <AuthGate>
      <ReaderShell />
    </AuthGate>
  )
}

function ReaderShell() {
  const { chapter, setChapter } = useReaderStore()
  const { user, logout } = useAuthStore()
  const { toast, activePanel, togglePanel } = useUiStore()
  const [bookPickerOpen, setBookPickerOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  // Look up chapter count from books query — for now cap nav at 150
  // (TODO: pull from useQuery(['books']) and find the matching book)
  function prevChapter() { if (chapter > 1) setChapter(chapter - 1) }
  function nextChapter() { setChapter(chapter + 1) }

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

        {/* Chapter navigation */}
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={prevChapter} disabled={chapter <= 1}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[2.5rem] text-center text-sm font-semibold text-text-primary">
            {chapter}
          </span>
          <Button variant="ghost" size="icon" onClick={nextChapter}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

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
            <span className="hidden sm:inline text-sm">
              {user?.display_name ?? user?.username}
            </span>
          </Button>

          {userMenuOpen && (
            <div
              className="absolute right-0 top-full z-50 mt-1 w-44 rounded-lg border border-bg-overlay bg-bg-surface py-1 shadow-xl"
              onMouseLeave={() => setUserMenuOpen(false)}
            >
              <button
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

        {/* Chapter content */}
        <main className="flex-1 overflow-y-auto px-6 py-8 max-w-3xl mx-auto w-full">
          <ChapterView />
        </main>

        {/* Tool rail — vertical icon strip */}
        <aside className="flex flex-col items-center gap-1 border-l border-bg-overlay bg-bg-surface px-2 py-4 shrink-0">
          {TOOL_BUTTONS.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              title={label}
              onClick={() => togglePanel(id)}
              className={`flex h-9 w-9 items-center justify-center rounded transition-colors
                ${activePanel === id
                  ? 'bg-gold-subtle text-gold'
                  : 'text-text-muted hover:text-text-primary hover:bg-bg-elevated'
                }`}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
        </aside>
      </div>

      {/* ── Tool panels ────────────────────────────────────────────── */}
      {/* Each panel slides in from the right as a Sheet.
          activePanel drives which content component is rendered inside. */}
      <ToolSheet />

      {/* Book picker sheet (left side) */}
      <BookPicker open={bookPickerOpen} onClose={() => setBookPickerOpen(false)} />

      {/* Toast stack */}
      <ToastStack />
    </div>
  )
}

// Panel titles shown in the Sheet header
const PANEL_META: Record<string, string> = {
  bookmarks:  'Bookmarks',
  notes:      'Notes',
  highlights: 'Highlights',
  history:    'Reading History',
}

// Renders the correct panel content inside the Sheet
function PanelContent({ id }: { id: PanelId }) {
  if (id === 'bookmarks')  return <BookmarksPanel />
  if (id === 'notes')      return <NotesPanel />
  if (id === 'highlights') return <HighlightsPanel />
  if (id === 'history')    return <HistoryPanel />
  return null
}

// Slide-in Sheet that houses all tool panels
function ToolSheet() {
  const { activePanel, sidebarOpen, closePanel } = useUiStore()
  return (
    <Sheet open={sidebarOpen} onOpenChange={(open) => { if (!open) closePanel() }}>
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
  { id: 'bookmarks'  as const, icon: Bookmark,    label: 'Bookmarks'  },
  { id: 'notes'      as const, icon: StickyNote,  label: 'Notes'      },
  { id: 'highlights' as const, icon: Highlighter, label: 'Highlights' },
  { id: 'history'    as const, icon: Clock,       label: 'History'    },
  { id: 'map'        as const, icon: Map,         label: 'Bible Map'  },
]

// Minimal toast renderer — replaces Alpine's $store.ui.toasts
function ToastStack() {
  const { toasts, dismissToast } = useUiStore()
  if (!toasts.length) return null

  const colourMap: Record<string, string> = {
    info:    'bg-bg-elevated border-bg-overlay text-text-primary',
    success: 'bg-bg-elevated border-gold       text-gold',
    error:   'bg-bg-elevated border-red-700    text-red-400',
    warning: 'bg-bg-elevated border-gold-muted text-gold',
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm shadow-xl
            animate-fade-in ${colourMap[t.type] ?? colourMap.info}`}
          onClick={() => dismissToast(t.id)}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}

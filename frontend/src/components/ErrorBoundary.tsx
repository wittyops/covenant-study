/**
 * ErrorBoundary — last line of defense against an uncaught render error.
 *
 * React Query failures never reach this (ChapterView etc. already turn a
 * failed fetch into isError + a recoverable UI). This catches everything
 * else: a bad response shape, a null a component didn't guard against, any
 * genuine bug in render. Without a boundary, React unmounts the entire tree
 * on an uncaught error and the browser shows a blank page — no message, no
 * way back in short of the user realizing they should reload. That failure
 * mode is indistinguishable from "broken" to someone using this live in a
 * pew on Sunday morning.
 *
 * Deliberately a class component — getDerivedStateFromError/componentDidCatch
 * have no hook equivalent; this is the one place React still requires one.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('Uncaught render error:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-bg-base px-6 text-center text-text-muted">
        <h1 className="text-xl font-semibold text-gold">Something went wrong</h1>
        <p className="max-w-sm text-sm">
          Covenant Study hit an unexpected error and couldn't continue. Reloading usually fixes it —
          your notes, highlights, and bookmarks are safe on the server.
        </p>
        <p className="max-w-sm text-xs opacity-60">{error.message}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg bg-gold px-4 py-2 text-sm font-semibold text-bg-base transition-opacity hover:opacity-90"
        >
          Reload
        </button>
      </div>
    )
  }
}

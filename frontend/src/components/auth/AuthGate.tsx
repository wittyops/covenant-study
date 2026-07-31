/**
 * AuthGate — wraps the entire app.
 * Shows the login/register form when no authenticated user is present,
 * otherwise renders children (the reader shell).
 */
import { useEffect, useState } from 'react'
import { useAuthStore } from '@/stores/auth'
import { LoginForm } from './LoginForm'
import { RegisterForm } from './RegisterForm'

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, restore } = useAuthStore()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [ready, setReady] = useState(false)

  // On mount, revalidate any persisted token against the server
  useEffect(() => {
    restore().finally(() => setReady(true))
  }, [restore])

  if (!ready) {
    // Thin splash while we check the token — avoids flashing the login screen
    return (
      <div className="flex h-screen items-center justify-center bg-bg-base">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-bg-overlay border-t-gold" />
      </div>
    )
  }

  if (user) return <>{children}</>

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-base px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Wordmark */}
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight text-gold">Covenant Study</h1>
          <p className="mt-1 text-sm text-text-muted">Scripture study platform</p>
        </div>

        {/* Form card */}
        <div className="rounded-lg border border-bg-overlay bg-bg-surface p-6 shadow-xl">
          {mode === 'login' ? (
            <LoginForm onSwitchToRegister={() => setMode('register')} />
          ) : (
            <RegisterForm onSwitchToLogin={() => setMode('login')} />
          )}
        </div>
      </div>
    </div>
  )
}

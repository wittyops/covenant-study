/**
 * Auth store — owns the session token and current user object.
 *
 * Only the token is persisted to localStorage (via Zustand persist middleware).
 * On mount, the app calls restore() which revalidates the token against /api/auth/me.
 * If the server rejects it, the user is cleared and sent back to the login screen.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { auth as authApi } from '@/lib/api'
import type { User } from '@/lib/types'

interface AuthState {
  // ── State ──────────────────────────────────────────────────────────────
  user: User | null
  token: string | null
  loading: boolean
  error: string | null

  // ── Computed ───────────────────────────────────────────────────────────
  isAdmin: boolean
  displayName: string

  // ── Actions ───────────────────────────────────────────────────────────
  /** Returns {mfaRequired: true, pendingToken} when the account has MFA on
   *  — the caller (LoginForm) is responsible for collecting a code next and
   *  calling verifyMfaLogin. A normal account completes the session here
   *  directly and returns {mfaRequired: false}. */
  login(
    username: string,
    password: string,
  ): Promise<{ mfaRequired: true; pendingToken: string } | { mfaRequired: false }>
  /** Second step of an MFA login — completes the session once the pending
   *  token + a valid TOTP code are both supplied. */
  verifyMfaLogin(pendingToken: string, code: string): Promise<void>
  register(username: string, password: string, displayName?: string): Promise<void>
  logout(): Promise<void>
  restore(): Promise<void>
  clearError(): void
  /** Replace the local user object — used after a self-service profile update
   *  (PUT /api/auth/me) so the header/menu reflect a new display name without
   *  a full re-login. */
  setUser(user: User): void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      loading: false,
      error: null,

      get isAdmin() {
        return get().user?.role === 'admin'
      },
      get displayName() {
        return get().user?.display_name ?? get().user?.username ?? ''
      },

      async login(username, password) {
        set({ loading: true, error: null })
        try {
          const result = await authApi.login(username, password)
          if ('mfa_required' in result) {
            // Don't touch token/user — the session doesn't exist yet.
            set({ loading: false })
            return { mfaRequired: true, pendingToken: result.pending_token }
          }
          set({ token: result.token, user: result.user, loading: false })
          return { mfaRequired: false }
        } catch (e) {
          set({ loading: false, error: (e as Error).message })
          throw e
        }
      },

      async verifyMfaLogin(pendingToken, code) {
        set({ loading: true, error: null })
        try {
          const { token, user } = await authApi.mfa.verifyLogin(pendingToken, code)
          set({ token, user, loading: false })
        } catch (e) {
          set({ loading: false, error: (e as Error).message })
          throw e
        }
      },

      async register(username, password, displayName) {
        set({ loading: true, error: null })
        try {
          const { token, user } = await authApi.register(username, password, displayName)
          set({ token, user, loading: false })
        } catch (e) {
          set({ loading: false, error: (e as Error).message })
          throw e
        }
      },

      async logout() {
        const { token } = get()
        set({ user: null, token: null, error: null })
        if (token) await authApi.logout(token).catch(() => {})
      },

      async restore() {
        const { token } = get()
        if (!token) return
        try {
          const user = await authApi.me(token)
          set({ user })
        } catch {
          // Token is stale — clear it so the login screen shows
          set({ user: null, token: null })
        }
      },

      clearError() {
        set({ error: null })
      },

      setUser(user) {
        set({ user })
      },
    }),
    {
      name: 'covenant-auth',
      // Only persist the token — everything else is derived at startup
      partialize: (s) => ({ token: s.token }),
    },
  ),
)

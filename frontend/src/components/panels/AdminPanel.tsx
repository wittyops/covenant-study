import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Loader2, Plus, ShieldCheck, User, X } from 'lucide-react'
import { useState } from 'react'
import { admin } from '@/lib/api'
import type { User as UserType } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

type View = 'list' | 'create' | 'reset'

export function AdminPanel() {
  const { token } = useAuthStore()
  const { toast } = useUiStore()
  const qc = useQueryClient()
  const [view, setView] = useState<View>('list')
  const [resetTarget, setResetTarget] = useState<UserType | null>(null)

  // Create form state
  const [createForm, setCreateForm] = useState({
    username: '',
    displayName: '',
    password: '',
    role: 'user' as 'user' | 'admin',
  })
  const [showCreatePw, setShowCreatePw] = useState(false)

  // Reset form state
  const [newPassword, setNewPassword] = useState('')
  const [showResetPw, setShowResetPw] = useState(false)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => admin.users(token!),
    staleTime: 30_000,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      admin.createUser(
        createForm.username.trim(),
        createForm.password,
        createForm.displayName.trim() || null,
        createForm.role,
        token!,
      ),
    onSuccess: () => {
      toast('User created', 'success')
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      setView('list')
      setCreateForm({ username: '', displayName: '', password: '', role: 'user' })
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  const resetMutation = useMutation({
    mutationFn: ({ uid, password }: { uid: number; password: string }) =>
      admin.resetPassword(uid, password, token!),
    onSuccess: () => {
      toast('Password updated', 'success')
      setView('list')
      setResetTarget(null)
      setNewPassword('')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  function openReset(u: UserType) {
    setResetTarget(u)
    setNewPassword('')
    setShowResetPw(false)
    setView('reset')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-text-muted">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading users…
      </div>
    )
  }

  // ── Create user form ──────────────────────────────────────────────────────
  if (view === 'create') {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            New User
          </span>
          <button
            type="button"
            onClick={() => setView('list')}
            className="text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <label htmlFor="cu-username" className="block text-xs text-text-muted mb-1">
              Username *
            </label>
            <input
              id="cu-username"
              type="text"
              placeholder="lowercase, no spaces"
              value={createForm.username}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, username: e.target.value.toLowerCase() }))
              }
              className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
            />
          </div>

          <div>
            <label htmlFor="cu-display" className="block text-xs text-text-muted mb-1">
              Display Name
            </label>
            <input
              id="cu-display"
              type="text"
              placeholder="Full name (optional)"
              value={createForm.displayName}
              onChange={(e) => setCreateForm((f) => ({ ...f, displayName: e.target.value }))}
              className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
            />
          </div>

          <div>
            <label htmlFor="cu-password" className="block text-xs text-text-muted mb-1">
              Password *
            </label>
            <div className="relative">
              <input
                id="cu-password"
                type={showCreatePw ? 'text' : 'password'}
                placeholder="Min 8 characters"
                value={createForm.password}
                onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
                className="w-full rounded-lg border border-bg-overlay bg-bg-elevated pl-3 pr-12 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
              />
              <button
                type="button"
                onClick={() => setShowCreatePw(!showCreatePw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-text-muted hover:text-text-primary"
              >
                {showCreatePw ? 'hide' : 'show'}
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="cu-role" className="block text-xs text-text-muted mb-1">
              Role
            </label>
            <select
              id="cu-role"
              value={createForm.role}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, role: e.target.value as 'user' | 'admin' }))
              }
              className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-gold"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>

        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={() => createMutation.mutate()}
            disabled={
              !createForm.username.trim() ||
              createForm.password.length < 8 ||
              createMutation.isPending
            }
            className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-gold text-bg-base text-xs font-semibold py-2 disabled:opacity-50 hover:bg-gold-dark transition-colors"
          >
            {createMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create User
          </button>
          <button
            type="button"
            onClick={() => setView('list')}
            className="px-3 rounded-lg border border-bg-overlay text-xs text-text-muted hover:text-text-primary transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // ── Reset password form ───────────────────────────────────────────────────
  if (view === 'reset' && resetTarget) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Reset Password
          </span>
          <button
            type="button"
            onClick={() => setView('list')}
            className="text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="text-sm text-text-secondary">
          Setting new password for{' '}
          <span className="font-medium text-text-primary">@{resetTarget.username}</span>
        </p>

        <div className="relative">
          <input
            type={showResetPw ? 'text' : 'password'}
            placeholder="New password (min 8 chars)"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            onKeyDown={(e) =>
              e.key === 'Enter' &&
              resetMutation.mutate({ uid: resetTarget.id, password: newPassword })
            }
            className="w-full rounded-lg border border-bg-overlay bg-bg-elevated pl-3 pr-12 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
          />
          <button
            type="button"
            onClick={() => setShowResetPw(!showResetPw)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-text-muted hover:text-text-primary"
          >
            {showResetPw ? 'hide' : 'show'}
          </button>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => resetMutation.mutate({ uid: resetTarget.id, password: newPassword })}
            disabled={newPassword.length < 8 || resetMutation.isPending}
            className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-gold text-bg-base text-xs font-semibold py-2 disabled:opacity-50 hover:bg-gold-dark transition-colors"
          >
            {resetMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Set Password
          </button>
          <button
            type="button"
            onClick={() => setView('list')}
            className="px-3 rounded-lg border border-bg-overlay text-xs text-text-muted hover:text-text-primary transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // ── User list ─────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-text-muted font-semibold uppercase tracking-wider">
          <ShieldCheck className="h-3.5 w-3.5 text-gold" />
          {users.length} account{users.length !== 1 ? 's' : ''}
        </div>
        <button
          type="button"
          onClick={() => setView('create')}
          className="flex items-center gap-1.5 rounded-lg border border-bg-overlay px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:border-gold transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New User
        </button>
      </div>

      <ul className="space-y-1.5">
        {users.map((u) => (
          <li key={u.id} className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-bg-elevated">
            <User className="h-4 w-4 text-text-muted shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">
                {u.display_name || u.username}
              </p>
              <p className="text-xs text-text-muted">
                @{u.username} · {u.role}
              </p>
            </div>
            <button
              type="button"
              title="Reset password"
              onClick={() => openReset(u)}
              className="text-text-muted hover:text-gold transition-colors shrink-0 p-1"
            >
              <KeyRound className="h-3.5 w-3.5" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

import { useMutation, useQuery } from '@tanstack/react-query'
import { KeyRound, Loader2, ShieldCheck, User } from 'lucide-react'
import { useState } from 'react'
import { admin } from '@/lib/api'
import type { User as UserType } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

export function AdminPanel() {
  const { token } = useAuthStore()
  const { toast } = useUiStore()
  const [resetTarget, setResetTarget] = useState<UserType | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => admin.users(token!),
    staleTime: 30_000,
  })

  const resetMutation = useMutation({
    mutationFn: ({ uid, password }: { uid: number; password: string }) =>
      admin.resetPassword(uid, password, token!),
    onSuccess: () => {
      toast('Password updated', 'success')
      setResetTarget(null)
      setNewPassword('')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  function submitReset() {
    if (!resetTarget || !newPassword.trim()) return
    resetMutation.mutate({ uid: resetTarget.id, password: newPassword })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-text-muted">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading users…
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-xs text-text-muted font-semibold uppercase tracking-wider">
        <ShieldCheck className="h-3.5 w-3.5 text-gold" />
        User Management · {users.length} account{users.length !== 1 ? 's' : ''}
      </div>

      {/* User list */}
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
              onClick={() => {
                setResetTarget(u)
                setNewPassword('')
                setShowPassword(false)
              }}
              className="text-text-muted hover:text-gold transition-colors shrink-0 p-1"
            >
              <KeyRound className="h-3.5 w-3.5" />
            </button>
          </li>
        ))}
      </ul>

      {/* Inline reset form */}
      {resetTarget && (
        <div className="rounded-lg border border-gold-muted bg-bg-elevated p-4 flex flex-col gap-3">
          <p className="text-xs font-semibold text-text-secondary">
            Reset password for <span className="text-text-primary">@{resetTarget.username}</span>
          </p>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitReset()}
              className="w-full rounded-lg border border-bg-overlay bg-bg-base pl-3 pr-10 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-text-muted hover:text-text-primary"
            >
              {showPassword ? 'hide' : 'show'}
            </button>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={submitReset}
              disabled={!newPassword.trim() || resetMutation.isPending}
              className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-gold text-bg-base text-xs font-semibold py-2 disabled:opacity-50 hover:bg-gold-dark transition-colors"
            >
              {resetMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Set Password
            </button>
            <button
              type="button"
              onClick={() => setResetTarget(null)}
              className="px-3 rounded-lg border border-bg-overlay text-xs text-text-muted hover:text-text-primary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * AccountPanel — self-service "My Account": change display name and/or
 * password. Every user gets this, not just admins — before this panel
 * existed, a password change could only happen by asking an admin to reset
 * it and relay the new one back out of band.
 */
import { useMutation } from '@tanstack/react-query'
import { KeyRound, Loader2, User as UserIcon } from 'lucide-react'
import { useState } from 'react'
import { auth } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

export function AccountPanel() {
  const { user, token, setUser } = useAuthStore()
  const { toast } = useUiStore()

  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPasswords, setShowPasswords] = useState(false)

  const profileMutation = useMutation({
    mutationFn: () => auth.updateMe({ displayName: displayName.trim() }, token!),
    onSuccess: (updated) => {
      setUser(updated)
      toast('Profile updated', 'success')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  const passwordMutation = useMutation({
    mutationFn: () => auth.updateMe({ currentPassword, newPassword }, token!),
    onSuccess: (updated) => {
      setUser(updated)
      toast('Password changed', 'success')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  const passwordsMismatch = newPassword.length > 0 && newPassword !== confirmPassword

  return (
    <div className="flex flex-col gap-6">
      {/* ── Profile ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
          <UserIcon className="h-3.5 w-3.5 text-gold" />
          Profile
        </div>

        <p className="text-xs text-text-muted">
          @{user?.username} · {user?.role}
        </p>

        <div>
          <label htmlFor="acc-display" className="block text-xs text-text-muted mb-1">
            Display Name
          </label>
          <input
            id="acc-display"
            type="text"
            placeholder="Full name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
          />
        </div>

        <button
          type="button"
          onClick={() => profileMutation.mutate()}
          disabled={!displayName.trim() || profileMutation.isPending}
          className="flex items-center justify-center gap-1.5 rounded-lg bg-gold text-bg-base text-xs font-semibold py-2 disabled:opacity-50 hover:bg-gold-dark transition-colors"
        >
          {profileMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save Profile
        </button>
      </div>

      <div className="border-t border-bg-overlay" />

      {/* ── Password ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
          <KeyRound className="h-3.5 w-3.5 text-gold" />
          Change Password
        </div>

        <div>
          <label htmlFor="acc-current-pw" className="block text-xs text-text-muted mb-1">
            Current Password
          </label>
          <input
            id="acc-current-pw"
            type={showPasswords ? 'text' : 'password'}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-gold"
          />
        </div>

        <div>
          <label htmlFor="acc-new-pw" className="block text-xs text-text-muted mb-1">
            New Password
          </label>
          <input
            id="acc-new-pw"
            type={showPasswords ? 'text' : 'password'}
            placeholder="Min 8 characters"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
          />
        </div>

        <div>
          <label htmlFor="acc-confirm-pw" className="block text-xs text-text-muted mb-1">
            Confirm New Password
          </label>
          <input
            id="acc-confirm-pw"
            type={showPasswords ? 'text' : 'password'}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-gold"
          />
          {passwordsMismatch && <p className="mt-1 text-xs text-red-400">Passwords don't match</p>}
        </div>

        <button
          type="button"
          onClick={() => setShowPasswords(!showPasswords)}
          className="self-start text-xs text-text-muted hover:text-text-primary"
        >
          {showPasswords ? 'hide passwords' : 'show passwords'}
        </button>

        <button
          type="button"
          onClick={() => passwordMutation.mutate()}
          disabled={
            !currentPassword ||
            newPassword.length < 8 ||
            passwordsMismatch ||
            passwordMutation.isPending
          }
          className="flex items-center justify-center gap-1.5 rounded-lg bg-gold text-bg-base text-xs font-semibold py-2 disabled:opacity-50 hover:bg-gold-dark transition-colors"
        >
          {passwordMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Change Password
        </button>
      </div>
    </div>
  )
}

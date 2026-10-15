/**
 * AccountPanel — self-service "My Account": change display name and/or
 * password. Every user gets this, not just admins — before this panel
 * existed, a password change could only happen by asking an admin to reset
 * it and relay the new one back out of band.
 */
import { useMutation } from '@tanstack/react-query'
import { KeyRound, Loader2, ShieldCheck, User as UserIcon } from 'lucide-react'
import QRCode from 'qrcode'
import { useEffect, useRef, useState } from 'react'
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

      <div className="border-t border-bg-overlay" />

      {/* ── Two-Factor Authentication ──────────────────────────────────── */}
      <MfaSection />
    </div>
  )
}

/** Separate component, not inline in AccountPanel, so its own enrollment
 *  state (pending secret, confirm-code field) doesn't tangle with the
 *  profile/password forms above — they're independent flows that happen to
 *  live on the same screen. */
function MfaSection() {
  const { user, token, setUser } = useAuthStore()
  const { toast } = useUiStore()

  // Non-null only while mid-enrollment: secret just generated, waiting on
  // the user to scan it and type back a code to prove they captured it.
  const [enrolling, setEnrolling] = useState<{ secret: string; otpauthUri: string } | null>(null)
  const [confirmCode, setConfirmCode] = useState('')
  const [disablePassword, setDisablePassword] = useState('')
  const [showDisableForm, setShowDisableForm] = useState(false)
  const qrCanvasRef = useRef<HTMLCanvasElement>(null)

  const enrollMutation = useMutation({
    mutationFn: () => auth.mfa.enroll(token!),
    onSuccess: (data) => setEnrolling({ secret: data.secret, otpauthUri: data.otpauth_uri }),
    onError: (e: Error) => toast(e.message, 'error'),
  })

  // Render the QR once the canvas exists and the secret is known — the
  // otpauth:// URI only ever goes into this canvas, never to any network
  // request, so the secret never leaves the browser during enrollment.
  useEffect(() => {
    if (enrolling && qrCanvasRef.current) {
      QRCode.toCanvas(qrCanvasRef.current, enrolling.otpauthUri, { width: 200 }).catch(() => {
        toast('Could not render QR code — use the manual key below instead', 'error')
      })
    }
  }, [enrolling, toast])

  const confirmMutation = useMutation({
    mutationFn: () => auth.mfa.confirm(confirmCode, token!),
    onSuccess: async () => {
      toast('Two-factor authentication enabled', 'success')
      setEnrolling(null)
      setConfirmCode('')
      setUser(await auth.me(token!))
    },
    onError: (e: Error) => {
      toast(e.message, 'error')
      setConfirmCode('')
    },
  })

  const disableMutation = useMutation({
    mutationFn: () => auth.mfa.disable(disablePassword, token!),
    onSuccess: async () => {
      toast('Two-factor authentication disabled', 'success')
      setShowDisableForm(false)
      setDisablePassword('')
      setUser(await auth.me(token!))
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
        <ShieldCheck className="h-3.5 w-3.5 text-gold" />
        Two-Factor Authentication
      </div>

      {user?.mfa_enabled ? (
        <>
          <p className="text-xs text-text-secondary">
            Enabled — your account requires a code from your authenticator app at sign-in.
          </p>
          {!showDisableForm ? (
            <button
              type="button"
              onClick={() => setShowDisableForm(true)}
              className="self-start rounded-lg border border-bg-overlay px-3 py-1.5 text-xs text-text-muted hover:text-red-400 hover:border-red-900 transition-colors"
            >
              Disable Two-Factor Authentication
            </button>
          ) : (
            <div className="flex flex-col gap-2 rounded-lg border border-bg-overlay bg-bg-elevated p-3">
              <label htmlFor="mfa-disable-pw" className="text-xs text-text-muted">
                Confirm your password to disable
              </label>
              <input
                id="mfa-disable-pw"
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                className="w-full rounded-lg border border-bg-overlay bg-bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-gold"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => disableMutation.mutate()}
                  disabled={!disablePassword || disableMutation.isPending}
                  className="flex-1 rounded-lg bg-red-900/40 text-red-300 text-xs font-semibold py-2 disabled:opacity-50 hover:bg-red-900/60 transition-colors"
                >
                  {disableMutation.isPending ? 'Disabling…' : 'Confirm Disable'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowDisableForm(false)
                    setDisablePassword('')
                  }}
                  className="rounded-lg border border-bg-overlay px-3 text-xs text-text-muted hover:text-text-primary"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      ) : enrolling ? (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-text-secondary">
            Scan this with your authenticator app (Google Authenticator, Authy, 1Password, etc.),
            then enter the 6-digit code it shows to confirm.
          </p>
          <canvas ref={qrCanvasRef} className="self-center rounded-lg" />
          <div>
            <p className="text-xs text-text-muted mb-1">Can't scan? Enter this key manually:</p>
            <code className="block rounded-lg bg-bg-elevated px-3 py-2 text-xs text-text-primary break-all select-text">
              {enrolling.secret}
            </code>
          </div>
          <input
            type="text"
            inputMode="numeric"
            placeholder="000000"
            maxLength={6}
            value={confirmCode}
            onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            className="w-full rounded-lg border border-bg-overlay bg-bg-elevated px-3 py-2 text-center text-lg tracking-[0.3em] text-text-primary focus:outline-none focus:border-gold"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => confirmMutation.mutate()}
              disabled={confirmCode.length !== 6 || confirmMutation.isPending}
              className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-gold text-bg-base text-xs font-semibold py-2 disabled:opacity-50 hover:bg-gold-dark transition-colors"
            >
              {confirmMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Confirm & Enable
            </button>
            <button
              type="button"
              onClick={() => {
                setEnrolling(null)
                setConfirmCode('')
              }}
              className="rounded-lg border border-bg-overlay px-3 text-xs text-text-muted hover:text-text-primary"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <p className="text-xs text-text-secondary">
            Not enabled. Add a second step at sign-in using an authenticator app.
          </p>
          <button
            type="button"
            onClick={() => enrollMutation.mutate()}
            disabled={enrollMutation.isPending}
            className="flex items-center justify-center gap-1.5 self-start rounded-lg bg-gold text-bg-base text-xs font-semibold px-3 py-2 disabled:opacity-50 hover:bg-gold-dark transition-colors"
          >
            {enrollMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Enable Two-Factor Authentication
          </button>
        </>
      )}
    </div>
  )
}

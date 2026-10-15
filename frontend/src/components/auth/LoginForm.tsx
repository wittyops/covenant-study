/**
 * LoginForm — TanStack Form + Zod validation.
 *
 * TanStack Form renders each field via a render-prop pattern so validation
 * errors are field-isolated.  Zod schemas are used both for type inference
 * and for runtime validation via the @tanstack/zod-form-adapter.
 */
import { useForm } from '@tanstack/react-form'
import { useState } from 'react'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatFieldError } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
})

interface Props {
  onSwitchToRegister: () => void
}

export function LoginForm({ onSwitchToRegister }: Props) {
  const { login, loading } = useAuthStore()
  const { toast } = useUiStore()

  // Set once the password step succeeds for an MFA-enabled account — at
  // that point the form below switches from username/password to a single
  // code field. Nothing else about the account is known/trusted yet; there
  // is no session until verifyMfaLogin succeeds.
  const [pendingToken, setPendingToken] = useState<string | null>(null)

  const form = useForm({
    defaultValues: { username: '', password: '' },
    validators: { onChange: loginSchema },
    onSubmit: async ({ value }) => {
      try {
        const result = await login(value.username, value.password)
        if (result.mfaRequired) setPendingToken(result.pendingToken)
      } catch (e) {
        toast((e as Error).message, 'error')
      }
    },
  })

  if (pendingToken) {
    return <MfaCodeStep pendingToken={pendingToken} onCancel={() => setPendingToken(null)} />
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        form.handleSubmit()
      }}
      className="space-y-4"
    >
      <h2 className="text-xl font-semibold text-text-primary">Sign in</h2>

      {/* Username */}
      <form.Field name="username" validators={{ onChange: z.string().min(1, 'Required') }}>
        {(field) => (
          <div className="space-y-1">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              autoComplete="username"
              autoFocus
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(e) => field.handleChange(e.target.value)}
            />
            {field.state.meta.errors.length > 0 && (
              <p className="text-xs text-red-400">{formatFieldError(field.state.meta.errors[0])}</p>
            )}
          </div>
        )}
      </form.Field>

      {/* Password */}
      <form.Field name="password" validators={{ onChange: z.string().min(1, 'Required') }}>
        {(field) => (
          <div className="space-y-1">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(e) => field.handleChange(e.target.value)}
            />
            {field.state.meta.errors.length > 0 && (
              <p className="text-xs text-red-400">{formatFieldError(field.state.meta.errors[0])}</p>
            )}
          </div>
        )}
      </form.Field>

      <Button type="submit" className="w-full" disabled={loading}>
        {loading ? 'Signing in…' : 'Sign in'}
      </Button>

      <p className="text-center text-sm text-text-muted">
        No account?{' '}
        <button type="button" onClick={onSwitchToRegister} className="text-gold hover:underline">
          Register
        </button>
      </p>
    </form>
  )
}

/** Second step of login for an MFA-enabled account — a single 6-digit TOTP
 *  code. Separate small form rather than folding into the main one above:
 *  the fields are genuinely different (no username/password here), and
 *  keeping it separate means the password step's validators/state can't
 *  leak into this one. */
function MfaCodeStep({ pendingToken, onCancel }: { pendingToken: string; onCancel: () => void }) {
  const { verifyMfaLogin, loading } = useAuthStore()
  const { toast } = useUiStore()
  const [code, setCode] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try {
      await verifyMfaLogin(pendingToken, code)
    } catch (e) {
      toast((e as Error).message, 'error')
      setCode('')
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <h2 className="text-xl font-semibold text-text-primary">Two-Factor Code</h2>
      <p className="text-sm text-text-muted">Enter the 6-digit code from your authenticator app.</p>

      <div className="space-y-1">
        <Label htmlFor="mfa-code">Code</Label>
        <Input
          id="mfa-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          maxLength={6}
          placeholder="000000"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          className="text-center text-lg tracking-[0.3em]"
        />
      </div>

      <Button type="submit" className="w-full" disabled={loading || code.length !== 6}>
        {loading ? 'Verifying…' : 'Verify'}
      </Button>

      <button
        type="button"
        onClick={onCancel}
        className="block w-full text-center text-sm text-text-muted hover:text-text-primary"
      >
        Back to sign in
      </button>
    </form>
  )
}

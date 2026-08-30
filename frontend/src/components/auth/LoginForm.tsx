/**
 * LoginForm — TanStack Form + Zod validation.
 *
 * TanStack Form renders each field via a render-prop pattern so validation
 * errors are field-isolated.  Zod schemas are used both for type inference
 * and for runtime validation via the @tanstack/zod-form-adapter.
 */
import { useForm } from '@tanstack/react-form'
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

  const form = useForm({
    defaultValues: { username: '', password: '' },
    validators: { onChange: loginSchema },
    onSubmit: async ({ value }) => {
      try {
        await login(value.username, value.password)
      } catch (e) {
        toast((e as Error).message, 'error')
      }
    },
  })

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

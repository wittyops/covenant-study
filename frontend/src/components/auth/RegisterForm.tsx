import { useForm } from '@tanstack/react-form'
import { z } from 'zod'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const registerSchema = z.object({
  username:    z.string().min(3, 'Min 3 characters').max(32, 'Max 32 characters'),
  displayName: z.string(),
  password:    z.string().min(8, 'Min 8 characters'),
  confirm:     z.string(),
}).refine((d) => d.password === d.confirm, {
  message: 'Passwords do not match',
  path: ['confirm'],
})

interface Props { onSwitchToLogin: () => void }

export function RegisterForm({ onSwitchToLogin }: Props) {
  const { register, loading } = useAuthStore()
  const { toast } = useUiStore()

  const form = useForm({
    defaultValues: { username: '', displayName: '', password: '', confirm: '' },
    validators: { onChange: registerSchema },
    onSubmit: async ({ value }) => {
      try {
        await register(value.username, value.password, value.displayName || undefined)
      } catch (e) {
        toast((e as Error).message, 'error')
      }
    },
  })

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); form.handleSubmit() }}
      className="space-y-4"
    >
      <h2 className="text-xl font-semibold text-text-primary">Create account</h2>

      <form.Field name="username" validators={{ onChange: z.string().min(3, 'Min 3 characters') }}>
        {(field) => (
          <div className="space-y-1">
            <Label htmlFor="reg-username">Username</Label>
            <Input
              id="reg-username"
              autoComplete="username"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(e) => field.handleChange(e.target.value)}
            />
            {field.state.meta.errors.length > 0 && (
              <p className="text-xs text-red-400">{field.state.meta.errors[0] != null ? String(field.state.meta.errors[0]) : ''}</p>
            )}
          </div>
        )}
      </form.Field>

      <form.Field name="displayName">
        {(field) => (
          <div className="space-y-1">
            <Label htmlFor="reg-display">Display name <span className="text-text-muted">(optional)</span></Label>
            <Input
              id="reg-display"
              autoComplete="name"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(e) => field.handleChange(e.target.value)}
            />
          </div>
        )}
      </form.Field>

      <form.Field name="password" validators={{ onChange: z.string().min(8, 'Min 8 characters') }}>
        {(field) => (
          <div className="space-y-1">
            <Label htmlFor="reg-password">Password</Label>
            <Input
              id="reg-password"
              type="password"
              autoComplete="new-password"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(e) => field.handleChange(e.target.value)}
            />
            {field.state.meta.errors.length > 0 && (
              <p className="text-xs text-red-400">{field.state.meta.errors[0] != null ? String(field.state.meta.errors[0]) : ''}</p>
            )}
          </div>
        )}
      </form.Field>

      <form.Field name="confirm">
        {(field) => (
          <div className="space-y-1">
            <Label htmlFor="reg-confirm">Confirm password</Label>
            <Input
              id="reg-confirm"
              type="password"
              autoComplete="new-password"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(e) => field.handleChange(e.target.value)}
            />
            {field.state.meta.errors.length > 0 && (
              <p className="text-xs text-red-400">{field.state.meta.errors[0] != null ? String(field.state.meta.errors[0]) : ''}</p>
            )}
          </div>
        )}
      </form.Field>

      <Button type="submit" className="w-full" disabled={loading}>
        {loading ? 'Creating account…' : 'Create account'}
      </Button>

      <p className="text-center text-sm text-text-muted">
        Already have an account?{' '}
        <button type="button" onClick={onSwitchToLogin} className="text-gold hover:underline">
          Sign in
        </button>
      </p>
    </form>
  )
}

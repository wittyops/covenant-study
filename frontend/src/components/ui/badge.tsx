import * as React from 'react'
import { cn } from '@/lib/utils'

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'outline' | 'gold'
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        variant === 'default' && 'bg-bg-elevated text-text-secondary',
        variant === 'outline' && 'border border-bg-overlay text-text-secondary',
        variant === 'gold'    && 'bg-gold-subtle text-gold',
        className,
      )}
      {...props}
    />
  )
}

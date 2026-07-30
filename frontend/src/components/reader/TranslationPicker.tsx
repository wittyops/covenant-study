/**
 * TranslationPicker — Radix Select for switching Bible translation.
 * Populates from /api/bible/translations.
 */
import { useQuery } from '@tanstack/react-query'
import * as SelectPrimitive from '@radix-ui/react-select'
import { ChevronDown, Check } from 'lucide-react'
import { useReaderStore } from '@/stores/reader'
import { useAuthStore } from '@/stores/auth'
import { bible } from '@/lib/api'
import { cn } from '@/lib/utils'

export function TranslationPicker() {
  const { translation, setTranslation } = useReaderStore()
  const { token } = useAuthStore()

  const { data: translations = [] } = useQuery({
    queryKey: ['translations'],
    queryFn: () => bible.translations(token),
    staleTime: Infinity,
  })

  return (
    <SelectPrimitive.Root value={translation} onValueChange={setTranslation}>
      <SelectPrimitive.Trigger
        className={cn(
          'flex items-center gap-1.5 rounded border border-bg-overlay bg-bg-elevated',
          'px-3 py-1.5 text-sm text-text-primary',
          'hover:border-gold focus:outline-none focus:ring-1 focus:ring-gold',
        )}
      >
        <SelectPrimitive.Value />
        <SelectPrimitive.Icon>
          <ChevronDown className="h-3.5 w-3.5 text-text-muted" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>

      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className={cn(
            'z-50 overflow-hidden rounded-lg border border-bg-overlay bg-bg-surface shadow-xl',
            'animate-fade-in',
          )}
          position="popper"
          sideOffset={4}
        >
          <SelectPrimitive.Viewport className="p-1">
            {translations.map((t) => (
              <SelectPrimitive.Item
                key={t.id}
                value={t.id}
                className={cn(
                  'relative flex cursor-pointer items-center rounded px-8 py-2 text-sm',
                  'text-text-primary hover:bg-bg-elevated focus:bg-bg-elevated focus:outline-none',
                )}
              >
                <SelectPrimitive.ItemIndicator className="absolute left-2">
                  <Check className="h-3.5 w-3.5 text-gold" />
                </SelectPrimitive.ItemIndicator>
                <SelectPrimitive.ItemText>{t.name}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}

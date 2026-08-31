/**
 * BookPicker — slide-in sheet showing the OT/NT/Apocrypha book grid.
 * Tabs split Old Testament, New Testament, and Apocrypha (same structure as
 * the backend's BOOKS + APOCRYPHA_BOOKS lists).
 */

import * as TabsPrimitive from '@radix-ui/react-tabs'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { bible } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'

interface Props {
  open: boolean
  onClose: () => void
}

export function BookPicker({ open, onClose }: Props) {
  const { book: currentBook, translation, setBook, setTranslation } = useReaderStore()
  const { token } = useAuthStore()

  const { data: books = [] } = useQuery({
    queryKey: ['books'],
    queryFn: () => bible.books(token),
    staleTime: Infinity,
  })

  const ot = books.filter((b) => b.testament === 'OT')
  const nt = books.filter((b) => b.testament === 'NT')
  const ap = books.filter((b) => b.testament === 'AP')

  // KJVA is currently the only translation with Apocrypha text (67-80) — see
  // config.APOCRYPHA_BOOKS in the backend. Picking an Apocrypha book on any
  // other translation would otherwise leave the reader pointed at a
  // book/translation combo the backend 404s on every chapter fetch, with no
  // way back short of knowing to reopen this picker.
  function pickBook(bookNum: number, testament: 'OT' | 'NT' | 'AP') {
    if (testament === 'AP' && translation !== 'KJVA') setTranslation('KJVA')
    setBook(bookNum)
    onClose()
  }

  return (
    <Sheet
      open={open}
      onOpenChange={(v) => {
        if (!v) onClose()
      }}
    >
      <SheetContent side="left" className="w-[340px] overflow-y-auto pb-10">
        <SheetHeader>
          <SheetTitle>Select a Book</SheetTitle>
        </SheetHeader>

        <TabsPrimitive.Root defaultValue="OT" className="mt-4">
          <TabsPrimitive.List className="flex rounded-lg bg-bg-elevated p-1 gap-1 mb-4">
            {(['OT', 'NT', 'AP'] as const).map((t) => (
              <TabsPrimitive.Trigger
                key={t}
                value={t}
                className={cn(
                  'flex-1 rounded py-1.5 text-sm font-medium transition-colors',
                  'text-text-muted data-[state=active]:bg-bg-overlay data-[state=active]:text-gold',
                )}
              >
                {t === 'OT' ? 'Old Testament' : t === 'NT' ? 'New Testament' : 'Apocrypha'}
              </TabsPrimitive.Trigger>
            ))}
          </TabsPrimitive.List>

          {[
            { value: 'OT', items: ot },
            { value: 'NT', items: nt },
            { value: 'AP', items: ap },
          ].map(({ value, items }) => (
            <TabsPrimitive.Content key={value} value={value}>
              <div className="grid grid-cols-2 gap-1.5">
                {items.map((b) => (
                  <Button
                    key={b.book}
                    variant={b.book === currentBook ? 'default' : 'ghost'}
                    size="sm"
                    className="justify-start text-left h-auto py-2 px-3"
                    onClick={() => pickBook(b.book, b.testament)}
                  >
                    <span className="truncate">{b.name}</span>
                  </Button>
                ))}
              </div>
            </TabsPrimitive.Content>
          ))}
        </TabsPrimitive.Root>
      </SheetContent>
    </Sheet>
  )
}

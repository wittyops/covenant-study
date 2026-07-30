/**
 * BookPicker — slide-in sheet showing the OT/NT book grid.
 * Tabs split Old Testament from New Testament (same structure as the backend's BOOKS list).
 */
import { useQuery } from '@tanstack/react-query'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { useReaderStore } from '@/stores/reader'
import { useAuthStore } from '@/stores/auth'
import { bible } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'

interface Props {
  open:    boolean
  onClose: () => void
}

export function BookPicker({ open, onClose }: Props) {
  const { book: currentBook, setBook } = useReaderStore()
  const { token } = useAuthStore()

  const { data: books = [] } = useQuery({
    queryKey: ['books'],
    queryFn: () => bible.books(token),
    staleTime: Infinity,
  })

  const ot = books.filter((b) => b.testament === 'OT')
  const nt = books.filter((b) => b.testament === 'NT')

  function pickBook(bookNum: number) {
    setBook(bookNum)
    onClose()
  }

  return (
    <Sheet open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <SheetContent side="left" className="w-[340px] overflow-y-auto pb-10">
        <SheetHeader>
          <SheetTitle>Select a Book</SheetTitle>
        </SheetHeader>

        <TabsPrimitive.Root defaultValue="OT" className="mt-4">
          <TabsPrimitive.List className="flex rounded-lg bg-bg-elevated p-1 gap-1 mb-4">
            {(['OT', 'NT'] as const).map((t) => (
              <TabsPrimitive.Trigger
                key={t}
                value={t}
                className={cn(
                  'flex-1 rounded py-1.5 text-sm font-medium transition-colors',
                  'text-text-muted data-[state=active]:bg-bg-overlay data-[state=active]:text-gold',
                )}
              >
                {t === 'OT' ? 'Old Testament' : 'New Testament'}
              </TabsPrimitive.Trigger>
            ))}
          </TabsPrimitive.List>

          {[{ value: 'OT', items: ot }, { value: 'NT', items: nt }].map(({ value, items }) => (
            <TabsPrimitive.Content key={value} value={value}>
              <div className="grid grid-cols-2 gap-1.5">
                {items.map((b) => (
                  <Button
                    key={b.book}
                    variant={b.book === currentBook ? 'default' : 'ghost'}
                    size="sm"
                    className="justify-start text-left h-auto py-2 px-3"
                    onClick={() => pickBook(b.book)}
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

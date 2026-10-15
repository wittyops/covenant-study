/**
 * MapsPanel — browse biblical places, view each on an embedded map without
 * leaving the app, and take notes against it.
 *
 * Used to open every place in a new browser tab (target="_blank" to
 * OpenStreetMap) — functional, but broke the single-app feel, and gave no
 * way to jot something down about what you were looking at without losing
 * your place in the reader. Now a click opens an in-app dialog: an OSM
 * iframe embed (same underlying service, just the embeddable endpoint
 * instead of the full-page one) plus a note editor scoped to that place.
 * The full external map is still one click away inside the dialog — not
 * removed, just no longer the forced default.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { ExternalLink, MapPin, Save, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { bible, notes as notesApi } from '@/lib/api'
import type { Place } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

export function MapsPanel() {
  const { token } = useAuthStore()
  const [query, setQuery] = useState('')
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null)

  const { data: places = [], isLoading } = useQuery({
    queryKey: ['places'],
    queryFn: () => bible.places(token),
    staleTime: Infinity,
  })

  const filtered = query.trim()
    ? places.filter(
        (p) =>
          p.name.toLowerCase().includes(query.toLowerCase()) ||
          (p.reference ?? '').toLowerCase().includes(query.toLowerCase()),
      )
    : places

  function osmUrl(p: Place) {
    const zoom = 10
    // layers=C selects OSM's "Cycle Map" style, which renders major place
    // names in Latin/English script. The default "Standard" style uses each
    // place's local-script name tag with no per-URL English override, which
    // is unreadable for this app's English-speaking audience across most of
    // the biblical Middle East (Hebrew/Arabic script by default).
    return `https://www.openstreetmap.org/?mlat=${p.latitude}&mlon=${p.longitude}#map=${zoom}/${p.latitude}/${p.longitude}&layers=C`
  }

  function osmEmbedUrl(p: Place) {
    // The embeddable endpoint takes a bounding box, not a zoom level — ~0.08°
    // of padding on each side lands at roughly the same zoom as the zoom=10
    // link above, enough surrounding geography to be legible without the
    // place being a single pixel.
    const pad = 0.08
    const bbox = [p.longitude - pad, p.latitude - pad, p.longitude + pad, p.latitude + pad].join(
      '%2C',
    )
    return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=cyclemap&marker=${p.latitude}%2C${p.longitude}`
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Search box */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted pointer-events-none" />
        <input
          type="search"
          placeholder="Search places…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-lg border border-bg-overlay bg-bg-elevated pl-8 pr-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-gold"
        />
      </div>

      {/* Context hint */}
      {!query && (
        <p className="text-xs text-text-muted px-0.5">
          All biblical places — search to filter, or browse by name.
        </p>
      )}

      {/* Place list */}
      {isLoading ? (
        <div className="space-y-2 pt-1">
          {[60, 80, 50, 70].map((w, i) => (
            <div
              // biome-ignore lint/suspicious/noArrayIndexKey: static literal array, never reordered/filtered/mutated — decorative shimmer widths, not real data.
              key={i}
              className="loading-shimmer h-14 rounded-lg"
              style={{ width: `${w}%` }}
            ></div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-text-muted text-center py-8">No places match "{query}"</p>
      ) : (
        <ul className="space-y-1.5">
          {filtered.map((place) => (
            <li key={place.id}>
              <button
                type="button"
                onClick={() => setSelectedPlace(place)}
                className="flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left hover:bg-bg-elevated transition-colors"
              >
                <MapPin className="h-3.5 w-3.5 text-gold shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-text-primary">{place.name}</span>
                  {place.reference && (
                    <p className="text-xs text-text-secondary leading-snug mt-0.5 line-clamp-2">
                      {place.reference}
                    </p>
                  )}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-text-muted text-center pt-1">
        {filtered.length} place{filtered.length !== 1 ? 's' : ''}
      </p>

      {/* In-app place view — map + notes, replacing the old new-tab jump */}
      <Dialog
        open={selectedPlace !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedPlace(null)
        }}
      >
        <DialogContent className="max-w-xl">
          {selectedPlace && (
            <PlaceDetail place={selectedPlace} osmUrl={osmUrl} osmEmbedUrl={osmEmbedUrl} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function PlaceDetail({
  place,
  osmUrl,
  osmEmbedUrl,
}: {
  place: Place
  osmUrl: (p: Place) => string
  osmEmbedUrl: (p: Place) => string
}) {
  const { token } = useAuthStore()
  const { toast } = useUiStore()

  // Place notes reuse the same free-text-ref /api/notes/{ref} endpoint the
  // verse-based NotesPanel uses — the ref column has no format constraint,
  // so "place:<id>" is a clean, collision-free namespace alongside the
  // existing numeric "<book> <chapter>:<verse>" verse refs, with zero
  // backend changes needed.
  const ref = `place:${place.id}`
  const { data, isLoading } = useQuery({
    queryKey: ['note', ref],
    queryFn: () => notesApi.get(ref, token ?? ''),
    enabled: !!token,
  })

  const [body, setBody] = useState('')
  useEffect(() => {
    setBody(data?.body ?? '')
  }, [data?.body])

  const save = useMutation({
    mutationFn: () => notesApi.save(ref, body, token ?? ''),
    onSuccess: () => toast('Note saved', 'success'),
    onError: () => toast('Could not save note', 'error'),
  })

  return (
    <div className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{place.name}</DialogTitle>
        {place.reference && <p className="text-sm text-text-secondary">{place.reference}</p>}
      </DialogHeader>

      <iframe
        title={`Map of ${place.name}`}
        src={osmEmbedUrl(place)}
        className="w-full h-56 rounded-lg border border-bg-overlay"
        loading="lazy"
      />

      <a
        href={osmUrl(place)}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 self-start text-xs text-text-muted hover:text-gold transition-colors"
      >
        <ExternalLink className="h-3 w-3" />
        Open full map in OpenStreetMap
      </a>

      <div className="flex flex-col gap-2">
        <span className="text-xs text-text-muted">Notes</span>
        {isLoading ? (
          <div className="loading-shimmer h-28 rounded-lg" />
        ) : (
          <textarea
            className="readable-text min-h-[112px] w-full resize-y rounded-lg border border-bg-overlay bg-bg-elevated
              px-3 py-2 text-sm text-text-primary placeholder:text-text-muted
              focus:border-gold focus:outline-none focus:ring-1 focus:ring-gold"
            placeholder={`Write your notes on ${place.name} here…`}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        )}
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending || isLoading}
          className="inline-flex items-center gap-1.5 self-end rounded-lg bg-gold px-3 py-1.5 text-xs font-semibold text-bg-base transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <Save className="h-3.5 w-3.5" />
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

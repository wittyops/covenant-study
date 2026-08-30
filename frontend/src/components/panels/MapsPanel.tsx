import { useQuery } from '@tanstack/react-query'
import { ExternalLink, MapPin, Search } from 'lucide-react'
import { useState } from 'react'
import { bible } from '@/lib/api'
import type { Place } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'

export function MapsPanel() {
  const { token } = useAuthStore()
  const [query, setQuery] = useState('')

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
              <a
                href={osmUrl(place)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-2.5 rounded-lg px-3 py-2.5 hover:bg-bg-elevated transition-colors group"
              >
                <MapPin className="h-3.5 w-3.5 text-gold shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-text-primary">{place.name}</span>
                    <ExternalLink className="h-3 w-3 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                  </div>
                  {place.reference && (
                    <p className="text-xs text-text-secondary leading-snug mt-0.5 line-clamp-2">
                      {place.reference}
                    </p>
                  )}
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-text-muted text-center pt-1">
        {filtered.length} place{filtered.length !== 1 ? 's' : ''} · opens in OpenStreetMap
      </p>
    </div>
  )
}

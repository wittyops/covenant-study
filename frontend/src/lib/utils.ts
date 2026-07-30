import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind class names safely — handles conflicts, conditionals, arrays. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format a verse reference for display, e.g. "Genesis 1:1" */
export function formatRef(bookName: string, chapter: number, verse?: number) {
  return verse ? `${bookName} ${chapter}:${verse}` : `${bookName} ${chapter}`
}

/** Parse a ref string like "Genesis 1:1" into parts. Returns null if malformed. */
export function parseRef(ref: string): { book: string; chapter: number; verse: number } | null {
  const m = ref.match(/^(.+?)\s+(\d+):(\d+)$/)
  if (!m) return null
  return { book: m[1], chapter: Number(m[2]), verse: Number(m[3]) }
}

/** Truncate a string to maxLen chars, appending '…' if cut. */
export function truncate(s: string, maxLen: number) {
  return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
}

/** Convert a Unix timestamp to a human-readable relative string. */
export function relativeTime(unix: number) {
  const diff = Date.now() / 1000 - unix
  if (diff < 60)   return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

/** Shared display helpers, so dates and coordinates read the same everywhere. */

const DATE_TIME = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const DATE_ONLY = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' })

export function formatDateTime(value: string | null): string {
  if (!value) return '—'
  return DATE_TIME.format(new Date(value))
}

export function formatDate(value: string | null): string {
  if (!value) return '—'
  return DATE_ONLY.format(new Date(value))
}

/** Decimal degrees to 6 places - roughly 0.1 m, far finer than a camera site needs. */
export function formatCoordinates(latitude: number | null, longitude: number | null): string {
  if (latitude === null || longitude === null) return '—'
  return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`
}

export function orDash(value: string | null | undefined): string {
  return value && value.trim() ? value : '—'
}

const RELATIVE = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 60 * 60],
  ['month', 30 * 24 * 60 * 60],
  ['day', 24 * 60 * 60],
  ['hour', 60 * 60],
  ['minute', 60],
]

/** "3 hours ago" — easier to scan in a feed than a full timestamp. */
export function formatRelative(value: string | null): string {
  if (!value) return '—'
  const seconds = (Date.now() - new Date(value).getTime()) / 1000
  if (seconds < 60) return 'just now'

  for (const [unit, size] of UNITS) {
    if (seconds >= size) return RELATIVE.format(-Math.floor(seconds / size), unit)
  }
  return 'just now'
}

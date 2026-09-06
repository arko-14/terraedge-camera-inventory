/** Turning a history row into readable text.
 *
 * Shared by the dashboard feed and the camera timeline so both describe the
 * same event the same way.
 */

import { formatCoordinates } from './format'
import type { HistoryEntry } from './types'
import { STATUS_LABELS } from './types'

/** Where a camera sat, as one string. */
function locationLabel(rangeName: string | null, beatName: string | null): string {
  if (!rangeName) return 'reserve stock'
  return beatName ? `${rangeName} · ${beatName}` : rangeName
}

/** A one-line headline: what happened, in the operator's terms. */
export function describeChange(entry: HistoryEntry): string {
  switch (entry.change_type) {
    case 'registered':
      return entry.to_range_name
        ? `Registered into ${locationLabel(entry.to_range_name, entry.to_beat_name)}`
        : 'Registered into reserve stock'
    case 'allocated':
      return `Allocated to ${locationLabel(entry.to_range_name, entry.to_beat_name)}`
    case 'transferred':
      return `Moved from ${locationLabel(entry.from_range_name, entry.from_beat_name)} to ${locationLabel(entry.to_range_name, entry.to_beat_name)}`
    case 'deployed':
      return `Deployed at ${entry.to_site_name ?? 'a new site'}`
    case 'returned_to_stock':
      return `Returned to stock from ${locationLabel(entry.from_range_name, entry.from_beat_name)}`
    default:
      return 'Deployment details updated'
  }
}

export interface FieldChange {
  label: string
  from: string
  to: string
}

/** Every field that actually moved, as before/after pairs. */
export function fieldChanges(entry: HistoryEntry): FieldChange[] {
  const changes: FieldChange[] = []
  const add = (label: string, from: string | null, to: string | null) => {
    if (from !== to) changes.push({ label, from: from ?? '—', to: to ?? '—' })
  }

  add('Range', entry.from_range_name, entry.to_range_name)
  add('Beat', entry.from_beat_name, entry.to_beat_name)
  add('Site', entry.from_site_name, entry.to_site_name)
  add(
    'Status',
    entry.from_status ? STATUS_LABELS[entry.from_status] : null,
    entry.to_status ? STATUS_LABELS[entry.to_status] : null,
  )
  add('Contact', entry.from_contact_name, entry.to_contact_name)
  add('Phone', entry.from_contact_phone, entry.to_contact_phone)

  const from = formatCoordinates(entry.from_latitude, entry.from_longitude)
  const to = formatCoordinates(entry.to_latitude, entry.to_longitude)
  if (from !== to) changes.push({ label: 'Coordinates', from, to })

  return changes
}

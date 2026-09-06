import { formatDateTime } from '../../lib/format'
import { fieldChanges } from '../../lib/history'
import type { HistoryEntry } from '../../lib/types'
import { CHANGE_LABELS } from '../../lib/types'

/** The full change history of one camera, newest first. */
export function HistoryTimeline({ history }: { history: HistoryEntry[] }) {
  if (history.length === 0) {
    return <p className="px-4 py-6 text-sm text-gray-500">No changes recorded yet.</p>
  }

  return (
    <ol className="divide-y divide-gray-100">
      {history.map((entry) => (
        <li key={entry.id} className="px-4 py-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <span className="text-sm font-medium text-gray-900">
              {CHANGE_LABELS[entry.change_type]}
            </span>
            <time dateTime={entry.changed_at} className="text-xs text-gray-500">
              {formatDateTime(entry.changed_at)}
            </time>
          </div>

          <dl className="mt-1 space-y-0.5">
            {fieldChanges(entry).map((change) => (
              <div key={change.label} className="flex flex-wrap items-baseline gap-1.5 text-sm">
                <dt className="text-gray-500">{change.label}</dt>
                <dd className="text-gray-800">
                  <span className="text-gray-500 line-through decoration-gray-300">
                    {change.from}
                  </span>
                  <span className="mx-1 text-gray-400">→</span>
                  <span className="font-medium">{change.to}</span>
                </dd>
              </div>
            ))}
          </dl>

          {entry.note && <p className="mt-1 text-sm italic text-gray-600">“{entry.note}”</p>}
          <p className="mt-1 text-xs text-gray-500">
            by {entry.changed_by_name ?? 'a removed account'}
            {entry.changed_by_email ? ` (${entry.changed_by_email})` : ''}
          </p>
        </li>
      ))}
    </ol>
  )
}

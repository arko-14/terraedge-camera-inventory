import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'
import { formatDateTime, formatRelative } from '../lib/format'
import { describeChange, fieldChanges } from '../lib/history'
import type { ChangeType, HistoryEntry, Summary } from '../lib/types'
import { CHANGE_LABELS } from '../lib/types'
import { Card, ErrorBanner, LoadingBlock, PageHeading, StatusBadge } from '../components/ui'

function StatTile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <Card className="p-4">
      <p className="text-sm text-gray-600">{label}</p>
      <p className={`mt-1 text-3xl font-semibold tabular-nums ${tone}`}>{value}</p>
    </Card>
  )
}

const CHANGE_TONES: Record<ChangeType, string> = {
  registered: 'bg-gray-100 text-gray-700',
  allocated: 'bg-amber-50 text-amber-800',
  transferred: 'bg-blue-50 text-blue-800',
  deployed: 'bg-forest-100 text-forest-800',
  details_updated: 'bg-gray-100 text-gray-700',
  returned_to_stock: 'bg-gray-100 text-gray-700',
}

/** One row of the feed: which camera, what changed, by whom, when. */
function ActivityRow({ entry }: { entry: HistoryEntry }) {
  const changes = fieldChanges(entry)

  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Link
          to={`/cameras/${entry.camera_id}`}
          className="font-medium text-forest-700 hover:underline"
        >
          {entry.camera_serial ?? `Camera ${entry.camera_id}`}
        </Link>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${CHANGE_TONES[entry.change_type]}`}
        >
          {CHANGE_LABELS[entry.change_type]}
        </span>
        {entry.to_status && <StatusBadge status={entry.to_status} />}
        <time
          dateTime={entry.changed_at}
          title={formatDateTime(entry.changed_at)}
          className="ml-auto text-xs text-gray-500"
        >
          {formatRelative(entry.changed_at)}
        </time>
      </div>

      <p className="mt-1 text-sm text-gray-800">{describeChange(entry)}</p>

      {changes.length > 0 && (
        <dl className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
          {changes.map((change) => (
            <div key={change.label} className="flex items-baseline gap-1.5 text-xs">
              <dt className="text-gray-500">{change.label}</dt>
              <dd className="text-gray-700">
                <span className="text-gray-500 line-through decoration-gray-300">{change.from}</span>
                <span aria-label="changed to" className="mx-1 text-gray-400">→</span>
                <span className="font-medium">{change.to}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {entry.note && <p className="mt-1.5 text-sm italic text-gray-600">“{entry.note}”</p>}

      <p className="mt-1.5 text-xs text-gray-500">
        {entry.changed_by_name ?? 'A removed account'}
        {entry.changed_by_email ? ` · ${entry.changed_by_email}` : ''}
      </p>
    </li>
  )
}

export function DashboardPage() {
  const { user, isAdmin } = useAuth()

  const summary = useQuery({
    queryKey: ['summary'],
    queryFn: () => api.get<Summary>('/api/stats/summary'),
  })

  const activity = useQuery({
    queryKey: ['activity'],
    queryFn: () => api.get<HistoryEntry[]>('/api/activity?limit=12'),
  })

  return (
    <div className="space-y-6">
      <PageHeading
        title={`Good to see you, ${user?.full_name.split(' ')[0]}`}
        subtitle={
          isAdmin
            ? 'Every camera supplied to the reserve, across all ranges.'
            : `Cameras currently allocated to ${user?.range_name}.`
        }
      />

      {summary.isPending && <LoadingBlock label="Loading totals…" />}
      {summary.isError && (
        <ErrorBanner
          message={(summary.error as Error).message}
          onRetry={() => void summary.refetch()}
        />
      )}

      {summary.data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <StatTile label="Total cameras" value={summary.data.total} tone="text-gray-900" />
            <StatTile label="In stock" value={summary.data.in_stock} tone="text-gray-600" />
            <StatTile label="Allocated" value={summary.data.allocated} tone="text-amber-700" />
            <StatTile label="Deployed" value={summary.data.deployed} tone="text-forest-700" />
          </div>

          {summary.data.by_range.length > 0 && (
            <Card className="overflow-hidden">
              <h2 className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-900">
                By range
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th scope="col" className="px-4 py-2 font-medium">Range</th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">Cameras</th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">Allocated</th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">Deployed</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {summary.data.by_range.map((row) => (
                      <tr key={row.range_id}>
                        <td className="px-4 py-2.5 font-medium text-gray-900">{row.range_name}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{row.total}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-amber-700">{row.allocated}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-forest-700">{row.deployed}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}

      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-900">Recent movement</h2>
          <Link to="/cameras" className="text-xs font-medium text-forest-700 hover:underline">
            All cameras →
          </Link>
        </div>
        {activity.isPending && <LoadingBlock label="Loading activity…" />}
        {activity.isError && (
          <div className="p-4">
            <ErrorBanner message={(activity.error as Error).message} />
          </div>
        )}
        {activity.data?.length === 0 && (
          <p className="px-4 py-6 text-sm text-gray-500">No changes recorded yet.</p>
        )}
        {activity.data && activity.data.length > 0 && (
          <ul className="divide-y divide-gray-100">
            {activity.data.map((entry) => (
              <ActivityRow key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

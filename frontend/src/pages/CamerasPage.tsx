import { useMemo, useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { api, toQueryString } from '../lib/api'
import { useDebounced, useRanges } from '../lib/hooks'
import { orDash } from '../lib/format'
import type { CameraListResponse, CameraStatus } from '../lib/types'
import { STATUS_LABELS } from '../lib/types'
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  LoadingBlock,
  PageHeading,
  Select,
  StatusBadge,
} from '../components/ui'

const PAGE_SIZE = 25

export function CamerasPage() {
  const { isAdmin } = useAuth()
  const navigate = useNavigate()
  const ranges = useRanges()

  const [search, setSearch] = useState('')
  const [rangeId, setRangeId] = useState('')
  const [beatId, setBeatId] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [exporting, setExporting] = useState(false)

  const debouncedSearch = useDebounced(search)

  // Changing a filter resets paging, and changing the range clears the beat
  // (a beat only makes sense within its range). Done in the handlers rather
  // than in effects, so there is no second render pass to undo the first.
  function applySearch(value: string) {
    setSearch(value)
    setPage(1)
  }

  function applyRange(value: string) {
    setRangeId(value)
    setBeatId('')
    setPage(1)
  }

  function applyBeat(value: string) {
    setBeatId(value)
    setPage(1)
  }

  function applyStatus(value: string) {
    setStatus(value)
    setPage(1)
  }

  // Only send a range or beat the current reference data still offers. Held
  // selections are dropped rather than sent, so a page open across a change to
  // the hierarchy cannot filter on an id that no longer exists.
  const known = useMemo(() => {
    const list = ranges.data ?? []
    return {
      ranges: new Set(list.map((r) => String(r.id))),
      beats: new Set(list.flatMap((r) => r.beats.map((b) => String(b.id)))),
    }
  }, [ranges.data])

  const activeRangeId = known.ranges.has(rangeId) ? rangeId : ''
  const activeBeatId = known.beats.has(beatId) ? beatId : ''

  const beats = useMemo(() => {
    if (!ranges.data) return []
    if (activeRangeId) {
      return ranges.data.find((r) => String(r.id) === activeRangeId)?.beats ?? []
    }
    return ranges.data.flatMap((r) => r.beats)
  }, [ranges.data, activeRangeId])

  const params = toQueryString({
    search: debouncedSearch,
    range_id: activeRangeId,
    beat_id: activeBeatId,
    status,
    page,
    page_size: PAGE_SIZE,
  })

  const cameras = useQuery({
    queryKey: ['cameras', params],
    queryFn: () => api.get<CameraListResponse>(`/api/cameras${params}`),
    placeholderData: keepPreviousData,
  })

  // The API scopes /api/ranges, so a range user gets exactly one back.
  const onlyRange = ranges.data?.length === 1 ? ranges.data[0] : null
  const hasFilters = Boolean(debouncedSearch || activeRangeId || activeBeatId || status)

  function clearFilters() {
    setSearch('')
    setRangeId('')
    setBeatId('')
    setStatus('')
    setPage(1)
  }

  return (
    <div className="space-y-5">
      <PageHeading
        title="Cameras"
        subtitle="Search by serial number, site or responsible contact."
        action={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              loading={exporting}
              onClick={() => {
                setExporting(true)
                void api
                  .download(`/api/cameras/export${params}`, 'camera-inventory.csv')
                  .finally(() => setExporting(false))
              }}
            >
              Export CSV
            </Button>
            {isAdmin && (
              <Button onClick={() => navigate('/cameras/new')}>Register camera</Button>
            )}
          </div>
        }
      />

      <Card className="p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2 lg:col-span-1">
            <Field label="Search" htmlFor="search">
              <Input
                id="search"
                type="search"
                value={search}
                onChange={(event) => applySearch(event.target.value)}
                placeholder="TE-CAM-001"
              />
            </Field>
          </div>

          {/* A range user has exactly one range, so the control is shown locked
              rather than hidden: the layout stays identical to an administrator's
              and the account's scope is visible instead of merely implied. */}
          <Field
            label="Range"
            htmlFor="range"
            hint={onlyRange ? 'Your account is scoped to this range.' : undefined}
          >
            <Select
              id="range"
              value={onlyRange ? String(onlyRange.id) : activeRangeId}
              disabled={Boolean(onlyRange)}
              onChange={(e) => applyRange(e.target.value)}
            >
              {!onlyRange && <option value="">All ranges</option>}
              {ranges.data?.map((range) => (
                <option key={range.id} value={range.id}>
                  {range.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Beat" htmlFor="beat">
            <Select id="beat" value={activeBeatId} onChange={(e) => applyBeat(e.target.value)}>
              <option value="">All beats</option>
              {beats.map((beat) => (
                <option key={beat.id} value={beat.id}>
                  {beat.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Status" htmlFor="status">
            <Select id="status" value={status} onChange={(e) => applyStatus(e.target.value)}>
              <option value="">Any status</option>
              {(Object.keys(STATUS_LABELS) as CameraStatus[]).map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABELS[value]}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {hasFilters && (
          <div className="mt-3 flex items-center gap-3">
            <Button variant="ghost" onClick={clearFilters}>
              Clear filters
            </Button>
            {cameras.isFetching && <span className="text-xs text-gray-500">Updating…</span>}
          </div>
        )}
      </Card>

      {cameras.isPending && <LoadingBlock label="Loading cameras…" />}

      {cameras.isError && (
        <ErrorBanner
          message={(cameras.error as Error).message}
          onRetry={() => void cameras.refetch()}
        />
      )}

      {cameras.data && cameras.data.items.length === 0 && (
        <EmptyState title="No cameras match these filters">
          {hasFilters ? 'Try widening your search.' : 'No cameras are visible to your account yet.'}
        </EmptyState>
      )}

      {cameras.data && cameras.data.items.length > 0 && (
        <>
          <Card className="hidden overflow-hidden md:block">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-medium">Serial</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Range</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Beat</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Site</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Contact</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {cameras.data.items.map((camera) => (
                    <tr key={camera.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5">
                        <Link
                          to={`/cameras/${camera.id}`}
                          className="font-medium text-forest-700 hover:underline"
                        >
                          {camera.serial_number}
                        </Link>
                      </td>
                      <td className="px-4 py-2.5"><StatusBadge status={camera.status} /></td>
                      <td className="px-4 py-2.5 text-gray-700">{orDash(camera.range_name)}</td>
                      <td className="px-4 py-2.5 text-gray-700">{orDash(camera.beat_name)}</td>
                      <td className="px-4 py-2.5 text-gray-700">{orDash(camera.site_name)}</td>
                      <td className="px-4 py-2.5 text-gray-700">{orDash(camera.contact_name)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Mobile: cards, since a six-column table is unusable on a phone. */}
          <ul className="space-y-3 md:hidden">
            {cameras.data.items.map((camera) => (
              <li key={camera.id}>
                <Link to={`/cameras/${camera.id}`} className="block">
                  <Card className="p-4 transition-shadow hover:shadow-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-forest-700">{camera.serial_number}</span>
                      <StatusBadge status={camera.status} />
                    </div>
                    <dl className="mt-2 space-y-0.5 text-sm text-gray-600">
                      <div className="flex gap-2">
                        <dt className="text-gray-500">Location:</dt>
                        <dd>
                          {camera.range_name
                            ? `${camera.range_name}${camera.beat_name ? ` · ${camera.beat_name}` : ''}`
                            : 'Unallocated stock'}
                        </dd>
                      </div>
                      {camera.site_name && (
                        <div className="flex gap-2">
                          <dt className="text-gray-500">Site:</dt>
                          <dd>{camera.site_name}</dd>
                        </div>
                      )}
                    </dl>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-gray-600">
              Showing {(cameras.data.page - 1) * cameras.data.page_size + 1}–
              {Math.min(cameras.data.page * cameras.data.page_size, cameras.data.total)} of{' '}
              {cameras.data.total}
            </p>
            {cameras.data.total_pages > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => current - 1)}
                >
                  Previous
                </Button>
                <span className="text-sm text-gray-600">
                  Page {cameras.data.page} of {cameras.data.total_pages}
                </span>
                <Button
                  variant="secondary"
                  disabled={page >= cameras.data.total_pages}
                  onClick={() => setPage((current) => current + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

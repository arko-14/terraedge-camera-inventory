import { useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { ApiError, api } from '../lib/api'
import { formatCoordinates, formatDate, formatDateTime, orDash } from '../lib/format'
import { useRanges } from '../lib/hooks'
import type { CameraDetail } from '../lib/types'
import { DeploymentDialog } from '../components/camera/DeploymentDialog'
import { HistoryTimeline } from '../components/camera/HistoryTimeline'
import { TransferDialog } from '../components/camera/TransferDialog'
import { Card, ErrorBanner, LoadingBlock, PageHeading, StatusBadge } from '../components/ui'
import { Button } from '../components/ui'

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-b border-gray-100 px-4 py-2.5 last:border-0 sm:grid sm:grid-cols-3 sm:gap-4">
      <dt className="text-sm text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900 sm:col-span-2 sm:mt-0">{value}</dd>
    </div>
  )
}

export function CameraDetailPage() {
  const { cameraId } = useParams()
  const { user, isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const ranges = useRanges()

  const [deployOpen, setDeployOpen] = useState(false)
  const [transferOpen, setTransferOpen] = useState(false)

  const camera = useQuery({
    queryKey: ['camera', cameraId],
    queryFn: () => api.get<CameraDetail>(`/api/cameras/${cameraId}`),
  })

  function invalidateAll() {
    void queryClient.invalidateQueries({ queryKey: ['camera', cameraId] })
    void queryClient.invalidateQueries({ queryKey: ['cameras'] })
    void queryClient.invalidateQueries({ queryKey: ['summary'] })
    void queryClient.invalidateQueries({ queryKey: ['activity'] })
  }

  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.patch<CameraDetail>(`/api/cameras/${cameraId}`, body),
    onSuccess: () => {
      invalidateAll()
      setDeployOpen(false)
    },
  })

  const transfer = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<CameraDetail>(`/api/cameras/${cameraId}/transfer`, body),
    onSuccess: () => {
      invalidateAll()
      setTransferOpen(false)
    },
  })

  if (camera.isPending) return <LoadingBlock label="Loading camera…" />

  if (camera.isError) {
    const error = camera.error as ApiError
    return (
      <div className="space-y-4">
        <ErrorBanner message={error.message} />
        <Link to="/cameras" className="text-sm font-medium text-forest-700 hover:underline">
          ← Back to cameras
        </Link>
      </div>
    )
  }

  const data = camera.data
  // Decides which buttons are worth showing. The API enforces the real rule.
  const canEdit = isAdmin || data.range_id === user?.range_id
  const canTransferAnywhere = isAdmin

  return (
    <div className="space-y-5">
      <Link to="/cameras" className="inline-block text-sm text-gray-600 hover:text-gray-900">
        ← Back to cameras
      </Link>

      <PageHeading
        title={data.serial_number}
        subtitle={data.model ?? undefined}
        action={
          canEdit ? (
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => setDeployOpen(true)}>
                {data.status === 'deployed' ? 'Update deployment' : 'Record deployment'}
              </Button>
              <Button variant="secondary" onClick={() => setTransferOpen(true)}>
                {data.range_id ? 'Transfer' : 'Allocate'}
              </Button>
            </div>
          ) : undefined
        }
      />

      <Card>
        <div className="flex items-center gap-3 border-b border-gray-200 px-4 py-3">
          <StatusBadge status={data.status} />
          <span className="text-sm text-gray-600">
            {data.range_name
              ? `${data.range_name}${data.beat_name ? ` · ${data.beat_name}` : ' · beat not set'}`
              : 'Unallocated reserve stock'}
          </span>
        </div>
        <dl>
          <DetailRow label="Site" value={orDash(data.site_name)} />
          <DetailRow
            label="Coordinates"
            value={formatCoordinates(data.latitude, data.longitude)}
          />
          <DetailRow
            label="Responsible contact"
            value={
              data.contact_name ? (
                <>
                  {data.contact_name}
                  {data.contact_phone && (
                    <>
                      {' · '}
                      <a href={`tel:${data.contact_phone}`} className="text-forest-700 hover:underline">
                        {data.contact_phone}
                      </a>
                    </>
                  )}
                </>
              ) : (
                '—'
              )
            }
          />
          <DetailRow label="Allocated on" value={formatDate(data.allocated_at)} />
          <DetailRow label="Deployed on" value={formatDate(data.deployed_at)} />
          <DetailRow label="Notes" value={orDash(data.notes)} />
          <DetailRow label="Last updated" value={formatDateTime(data.updated_at)} />
        </dl>
      </Card>

      <Card className="overflow-hidden">
        <h2 className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-900">
          Assignment history
          <span className="ml-2 font-normal text-gray-500">
            ({data.history.length} {data.history.length === 1 ? 'entry' : 'entries'})
          </span>
        </h2>
        <HistoryTimeline history={data.history} />
      </Card>

      {/* Keyed on updated_at so the forms re-seed after a successful save. */}
      <DeploymentDialog
        key={`deploy-${data.updated_at}`}
        open={deployOpen}
        camera={data}
        onClose={() => {
          setDeployOpen(false)
          update.reset()
        }}
        onSubmit={(body) => update.mutate(body)}
        pending={update.isPending}
        error={update.error instanceof ApiError ? update.error : null}
      />

      <TransferDialog
        key={`transfer-${data.updated_at}`}
        open={transferOpen}
        camera={data}
        ranges={ranges.data ?? []}
        restrictToRangeId={canTransferAnywhere ? null : (user?.range_id ?? null)}
        onClose={() => {
          setTransferOpen(false)
          transfer.reset()
        }}
        onSubmit={(body) => transfer.mutate(body)}
        pending={transfer.isPending}
        error={transfer.error instanceof ApiError ? transfer.error : null}
      />
    </div>
  )
}

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression, LatLngTuple } from 'leaflet'
import 'leaflet/dist/leaflet.css'

import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'
import { formatCoordinates, formatDate, orDash } from '../lib/format'
import type { Camera, CameraListResponse } from '../lib/types'
import { Card, EmptyState, ErrorBanner, LoadingBlock, PageHeading } from '../components/ui'

// Similipal Tiger Reserve, used only until real markers arrive.
const RESERVE_CENTRE: LatLngTuple = [21.87, 86.33]

/** Vector markers, so there are no icon image assets to break under a bundler. */
const MARKER = {
  radius: 7,
  weight: 2,
  color: '#245537',
  fillColor: '#2f6b45',
  fillOpacity: 0.85,
}

/** Pan and zoom to fit whatever is actually deployed. */
function FitToMarkers({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap()
  if (bounds) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 })
  return null
}

export function MapPage() {
  const { user, isAdmin } = useAuth()

  const cameras = useQuery({
    queryKey: ['cameras', 'deployed-map'],
    queryFn: () => api.get<CameraListResponse>('/api/cameras?status=deployed&page_size=100'),
  })

  // Only deployed cameras carry coordinates; the status filter already
  // guarantees that, and the null check keeps TypeScript honest.
  const placed = useMemo(
    () =>
      (cameras.data?.items ?? []).filter(
        (c): c is Camera & { latitude: number; longitude: number } =>
          c.latitude !== null && c.longitude !== null,
      ),
    [cameras.data],
  )

  const bounds = useMemo<LatLngBoundsExpression | null>(
    () => (placed.length ? placed.map((c) => [c.latitude, c.longitude] as LatLngTuple) : null),
    [placed],
  )

  return (
    <div className="space-y-5">
      <PageHeading
        title="Deployment map"
        subtitle={
          isAdmin
            ? 'Every camera currently in the field, across the reserve.'
            : `Cameras currently deployed in ${user?.range_name}.`
        }
      />

      {cameras.isPending && <LoadingBlock label="Loading deployed cameras…" />}

      {cameras.isError && (
        <ErrorBanner
          message={(cameras.error as Error).message}
          onRetry={() => void cameras.refetch()}
        />
      )}

      {cameras.data && placed.length === 0 && (
        <EmptyState title="Nothing deployed yet">
          Cameras appear here once they are marked deployed with coordinates.
        </EmptyState>
      )}

      {placed.length > 0 && (
        <>
          <Card className="overflow-hidden">
            <MapContainer
              center={RESERVE_CENTRE}
              zoom={11}
              scrollWheelZoom={false}
              className="h-[78vh] min-h-[26rem] w-full"
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                maxZoom={19}
              />
              <FitToMarkers bounds={bounds} />

              {placed.map((camera) => (
                <CircleMarker
                  key={camera.id}
                  center={[camera.latitude, camera.longitude]}
                  pathOptions={MARKER}
                  radius={MARKER.radius}
                >
                  <Popup>
                    <span className="block text-sm font-semibold text-gray-900">
                      {camera.serial_number}
                    </span>
                    <span className="block text-sm text-gray-700">
                      {orDash(camera.site_name)}
                    </span>
                    <span className="block text-xs text-gray-500">
                      {camera.range_name}
                      {camera.beat_name ? ` · ${camera.beat_name}` : ''}
                    </span>
                    <span className="mt-1 block text-xs text-gray-500">
                      {formatCoordinates(camera.latitude, camera.longitude)}
                    </span>
                    {camera.contact_name && (
                      <span className="block text-xs text-gray-500">
                        {camera.contact_name}
                        {camera.contact_phone ? ` · ${camera.contact_phone}` : ''}
                      </span>
                    )}
                    <span className="block text-xs text-gray-500">
                      Deployed {formatDate(camera.deployed_at)}
                    </span>
                    <Link
                      to={`/cameras/${camera.id}`}
                      className="mt-1 inline-block text-sm font-medium text-forest-700 underline underline-offset-2"
                    >
                      Open camera
                    </Link>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </Card>

          <p className="text-sm text-gray-600">
            Showing {placed.length} deployed{' '}
            {placed.length === 1 ? 'camera' : 'cameras'}. Cameras in stock or awaiting deployment
            have no coordinates and are not mapped.
          </p>
        </>
      )}
    </div>
  )
}

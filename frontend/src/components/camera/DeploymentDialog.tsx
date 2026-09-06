import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import type { ApiError } from '../../lib/api'
import { useRanges } from '../../lib/hooks'
import type { CameraDetail } from '../../lib/types'
import { Button, ErrorBanner, Field, Input, Modal, Select } from '../ui'

/** Record or update where a camera is deployed, and optionally mark it deployed. */
export function DeploymentDialog({
  open,
  camera,
  onClose,
  onSubmit,
  pending,
  error,
}: {
  open: boolean
  camera: CameraDetail
  onClose: () => void
  onSubmit: (body: Record<string, unknown>) => void
  pending: boolean
  error: ApiError | null
}) {
  const ranges = useRanges()
  const [siteName, setSiteName] = useState(camera.site_name ?? '')
  const [latitude, setLatitude] = useState(camera.latitude?.toString() ?? '')
  const [longitude, setLongitude] = useState(camera.longitude?.toString() ?? '')
  const [contactName, setContactName] = useState(camera.contact_name ?? '')
  const [contactPhone, setContactPhone] = useState(camera.contact_phone ?? '')
  const [beatId, setBeatId] = useState(camera.beat_id?.toString() ?? '')
  const [markDeployed, setMarkDeployed] = useState(camera.status === 'deployed')

  const beats = useMemo(
    () => ranges.data?.find((range) => range.id === camera.range_id)?.beats ?? [],
    [ranges.data, camera.range_id],
  )

  const fieldError = (name: string) => error?.fieldErrors.find((f) => f.field === name)?.message

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    onSubmit({
      site_name: siteName || null,
      latitude: latitude === '' ? null : Number(latitude),
      longitude: longitude === '' ? null : Number(longitude),
      contact_name: contactName || null,
      contact_phone: contactPhone || null,
      beat_id: beatId === '' ? null : Number(beatId),
      ...(markDeployed ? { status: 'deployed' } : {}),
    })
  }

  return (
    <Modal open={open} title="Deployment details" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && !error.fieldErrors.length && <ErrorBanner message={error.message} />}

        {camera.range_id === null && (
          <ErrorBanner message="Allocate this camera to a range before recording a deployment." />
        )}

        <Field label="Beat" htmlFor="deploy-beat" error={fieldError('beat_id')}>
          <Select
            id="deploy-beat"
            value={beatId}
            disabled={camera.range_id === null}
            onChange={(event) => setBeatId(event.target.value)}
          >
            <option value="">Not decided yet</option>
            {beats.map((beat) => (
              <option key={beat.id} value={beat.id}>
                {beat.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Site name" htmlFor="site" error={fieldError('site_name')}>
          <Input
            id="site"
            value={siteName}
            onChange={(event) => setSiteName(event.target.value)}
            placeholder="Bakua Nala Crossing"
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Latitude" htmlFor="lat" hint="Decimal degrees" error={fieldError('latitude')}>
            <Input
              id="lat"
              type="number"
              step="any"
              min={-90}
              max={90}
              value={latitude}
              onChange={(event) => setLatitude(event.target.value)}
              placeholder="21.904200"
              invalid={Boolean(fieldError('latitude'))}
            />
          </Field>
          <Field label="Longitude" htmlFor="lon" hint="Decimal degrees" error={fieldError('longitude')}>
            <Input
              id="lon"
              type="number"
              step="any"
              min={-180}
              max={180}
              value={longitude}
              onChange={(event) => setLongitude(event.target.value)}
              placeholder="86.361100"
              invalid={Boolean(fieldError('longitude'))}
            />
          </Field>
        </div>

        <Field label="Responsible contact" htmlFor="contact" error={fieldError('contact_name')}>
          <Input
            id="contact"
            value={contactName}
            onChange={(event) => setContactName(event.target.value)}
            placeholder="Name of the person responsible"
          />
        </Field>

        <Field
          label="Contact phone"
          htmlFor="phone"
          hint="The contact does not need a login account."
          error={fieldError('contact_phone')}
        >
          <Input
            id="phone"
            type="tel"
            value={contactPhone}
            onChange={(event) => setContactPhone(event.target.value)}
            placeholder="+91 98110 20034"
            invalid={Boolean(fieldError('contact_phone'))}
          />
        </Field>

        <label className="flex items-start gap-2 rounded-md bg-gray-50 p-3">
          <input
            type="checkbox"
            checked={markDeployed}
            onChange={(event) => setMarkDeployed(event.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-forest-600 focus:ring-forest-600"
          />
          <span className="text-sm text-gray-700">
            Mark as deployed
            <span className="block text-xs text-gray-500">
              Requires a beat, site name, coordinates and a responsible contact.
            </span>
          </span>
        </label>

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  )
}

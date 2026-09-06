import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { ApiError, api } from '../lib/api'
import { useRanges } from '../lib/hooks'
import type { Camera } from '../lib/types'
import {
  Button,
  Card,
  ErrorBanner,
  Field,
  Input,
  PageHeading,
  Select,
} from '../components/ui'

export function RegisterCameraPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const ranges = useRanges()

  const [serial, setSerial] = useState('')
  const [model, setModel] = useState('')
  const [rangeId, setRangeId] = useState('')
  const [beatId, setBeatId] = useState('')
  const [notes, setNotes] = useState('')

  const beats = useMemo(
    () => ranges.data?.find((range) => String(range.id) === rangeId)?.beats ?? [],
    [ranges.data, rangeId],
  )

  const register = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<Camera>('/api/cameras', body),
    onSuccess: (camera) => {
      void queryClient.invalidateQueries({ queryKey: ['cameras'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
      void queryClient.invalidateQueries({ queryKey: ['activity'] })
      navigate(`/cameras/${camera.id}`)
    },
  })

  const error = register.error instanceof ApiError ? register.error : null
  const fieldError = (name: string) => error?.fieldErrors.find((f) => f.field === name)?.message

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    register.mutate({
      serial_number: serial,
      model: model || null,
      range_id: rangeId ? Number(rangeId) : null,
      beat_id: beatId ? Number(beatId) : null,
      notes: notes || null,
    })
  }

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <PageHeading
        title="Register a camera"
        subtitle="Add a camera to the reserve inventory. It can be allocated now or left in stock."
      />

      <Card className="p-5">
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {error && !error.fieldErrors.length && <ErrorBanner message={error.message} />}

          <Field
            label="Serial number"
            htmlFor="serial"
            required
            error={fieldError('serial_number') ?? (error?.status === 409 ? error.message : null)}
            hint="Printed on the camera body. Stored in upper case and unique across the reserve."
          >
            <Input
              id="serial"
              value={serial}
              onChange={(event) => setSerial(event.target.value)}
              placeholder="TE-CAM-025"
              autoFocus
              required
              invalid={Boolean(fieldError('serial_number')) || error?.status === 409}
            />
          </Field>

          <Field label="Model" htmlFor="model" error={fieldError('model')}>
            <Input
              id="model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="PantheraCam S3"
            />
          </Field>

          <Field
            label="Range"
            htmlFor="range"
            hint="Leave blank to keep the camera in reserve stock."
            error={fieldError('range_id')}
          >
            <Select id="range" value={rangeId} onChange={(event) => setRangeId(event.target.value)}>
              <option value="">Keep in stock</option>
              {ranges.data?.map((range) => (
                <option key={range.id} value={range.id}>
                  {range.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Beat"
            htmlFor="beat"
            hint="Optional — a camera can be allocated to a range before its beat is decided."
            error={fieldError('beat_id')}
          >
            <Select
              id="beat"
              value={beatId}
              disabled={!rangeId}
              onChange={(event) => setBeatId(event.target.value)}
            >
              <option value="">{rangeId ? 'Not decided yet' : 'Select a range first'}</option>
              {beats.map((beat) => (
                <option key={beat.id} value={beat.id}>
                  {beat.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Notes" htmlFor="notes" error={fieldError('notes')}>
            <Input
              id="notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Optional"
            />
          </Field>

          <div className="flex gap-2 pt-2">
            <Button type="submit" loading={register.isPending}>
              Register camera
            </Button>
            <Button type="button" variant="secondary" onClick={() => navigate('/cameras')}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}

import { useState } from 'react'
import type { FormEvent } from 'react'

import type { ApiError } from '../../lib/api'
import type { CameraDetail } from '../../lib/types'
import { Button, ErrorBanner, Field, Input, Modal, Select } from '../ui'

/** Allocate, move between beats/ranges, or return a camera to stock. */
export function TransferDialog({
  open,
  camera,
  ranges,
  restrictToRangeId,
  onClose,
  onSubmit,
  pending,
  error,
}: {
  open: boolean
  camera: CameraDetail
  ranges: { id: number; name: string; beats: { id: number; name: string }[] }[]
  restrictToRangeId: number | null
  onClose: () => void
  onSubmit: (body: Record<string, unknown>) => void
  pending: boolean
  error: ApiError | null
}) {
  const [rangeId, setRangeId] = useState(camera.range_id?.toString() ?? '')
  const [beatId, setBeatId] = useState(camera.beat_id?.toString() ?? '')
  const [note, setNote] = useState('')

  const selectableRanges =
    restrictToRangeId === null ? ranges : ranges.filter((range) => range.id === restrictToRangeId)
  const beats = ranges.find((range) => String(range.id) === rangeId)?.beats ?? []

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    onSubmit({
      range_id: rangeId === '' ? null : Number(rangeId),
      beat_id: beatId === '' ? null : Number(beatId),
      note: note || null,
    })
  }

  return (
    <Modal open={open} title="Transfer camera" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && <ErrorBanner message={error.message} />}

        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">
          Moving a camera ends its current deployment. The site, coordinates and contact are
          cleared for re-entry at the new location — the previous values stay in its history.
        </p>

        <Field label="Range" htmlFor="transfer-range" required>
          <Select
            id="transfer-range"
            value={rangeId}
            onChange={(event) => {
              setRangeId(event.target.value)
              setBeatId('')
            }}
          >
            {restrictToRangeId === null && <option value="">Return to reserve stock</option>}
            {selectableRanges.map((range) => (
              <option key={range.id} value={range.id}>
                {range.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Beat"
          htmlFor="transfer-beat"
          hint="Optional — a camera can sit with a range before its beat is decided."
        >
          <Select
            id="transfer-beat"
            value={beatId}
            disabled={rangeId === ''}
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

        <Field label="Reason" htmlFor="note" hint="Recorded against this movement in the history.">
          <Input
            id="note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="e.g. Moved for the winter census"
          />
        </Field>

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            Confirm transfer
          </Button>
        </div>
      </form>
    </Modal>
  )
}

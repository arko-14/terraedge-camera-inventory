import { useState } from 'react'
import type { ChangeEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, api } from '../lib/api'
import type { ImportResult } from '../lib/types'
import { Button, Card, ErrorBanner, PageHeading } from '../components/ui'

function Tally({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-md bg-gray-50 px-3 py-2">
      <p className="text-xs text-gray-600">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${tone}`}>{value}</p>
    </div>
  )
}

export function ImportCamerasPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)

  const importFile = useMutation({
    mutationFn: (csv: File) => api.upload<ImportResult>('/api/cameras/import', csv),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cameras'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
      void queryClient.invalidateQueries({ queryKey: ['activity'] })
    },
  })

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null)
    importFile.reset()
  }

  const result = importFile.data
  const error = importFile.error instanceof ApiError ? importFile.error : null

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeading
        title="Import cameras"
        subtitle="Bulk-register cameras from a spreadsheet exported as CSV."
      />

      <Card className="space-y-4 p-5">
        <ol className="space-y-2 text-sm text-gray-700">
          <li>
            <span className="font-medium">1.</span> Download the{' '}
            <button
              type="button"
              onClick={() =>
                void api.download('/api/cameras/import/template', 'camera-import-template.csv')
              }
              className="font-medium text-forest-700 underline underline-offset-2 hover:text-forest-800"
            >
              CSV template
            </button>{' '}
            — only <code className="rounded bg-gray-100 px-1">serial_number</code> is required.
          </li>
          <li>
            <span className="font-medium">2.</span> Fill it in. Range and beat are matched by name;
            a beat must belong to its range.
          </li>
          <li>
            <span className="font-medium">3.</span> Upload it below. Valid rows are imported even if
            others fail, and you get a report of anything that did not go through.
          </li>
        </ol>

        <div className="space-y-3 border-t border-gray-200 pt-4">
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={handleFile}
            aria-label="CSV file"
            className="block w-full text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-forest-600 file:px-3.5 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-forest-700"
          />

          {error && <ErrorBanner message={error.message} />}

          <div className="flex gap-2">
            <Button
              disabled={!file}
              loading={importFile.isPending}
              onClick={() => file && importFile.mutate(file)}
            >
              Import
            </Button>
            <Button variant="secondary" onClick={() => navigate('/cameras')}>
              Back to cameras
            </Button>
          </div>
        </div>
      </Card>

      {result && (
        <Card className="space-y-4 p-5">
          <h2 className="text-sm font-semibold text-gray-900">
            Import finished — {result.total_rows} {result.total_rows === 1 ? 'row' : 'rows'} read
          </h2>

          <div className="grid grid-cols-3 gap-3">
            <Tally label="Registered" value={result.created_count} tone="text-forest-700" />
            <Tally label="Already present" value={result.skipped_count} tone="text-gray-600" />
            <Tally label="Failed" value={result.error_count} tone="text-red-700" />
          </div>

          {result.errors.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-sm font-medium text-gray-900">Rows that did not import</h3>
              <div className="overflow-x-auto rounded-md ring-1 ring-gray-200">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th scope="col" className="px-3 py-2 font-medium">Row</th>
                      <th scope="col" className="px-3 py-2 font-medium">Serial</th>
                      <th scope="col" className="px-3 py-2 font-medium">Problem</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {result.errors.map((row) => (
                      <tr key={`${row.row}-${row.serial_number}`}>
                        <td className="px-3 py-2 tabular-nums text-gray-600">{row.row}</td>
                        <td className="px-3 py-2 font-medium text-gray-900">
                          {row.serial_number || '—'}
                        </td>
                        <td className="px-3 py-2 text-red-700">{row.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-1.5 text-xs text-gray-500">
                Row numbers match your spreadsheet, counting the header as row 1. Fix these rows and
                re-upload the file — cameras already registered are skipped, not duplicated.
              </p>
            </div>
          )}

          {result.skipped.length > 0 && (
            <p className="text-sm text-gray-600">
              Skipped as already registered:{' '}
              <span className="text-gray-800">
                {result.skipped.map((s) => s.serial_number).join(', ')}
              </span>
            </p>
          )}

          {result.created_count > 0 && (
            <Link
              to="/cameras"
              className="inline-block text-sm font-medium text-forest-700 hover:underline"
            >
              View the {result.created_count} newly registered{' '}
              {result.created_count === 1 ? 'camera' : 'cameras'} →
            </Link>
          )}
        </Card>
      )}
    </div>
  )
}

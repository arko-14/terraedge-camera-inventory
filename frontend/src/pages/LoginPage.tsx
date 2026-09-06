import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../lib/api'
import { Button, ErrorBanner, Field, Input, LoadingBlock } from '../components/ui'

export function LoginPage() {
  const { user, initialising, login } = useAuth()
  const location = useLocation() as { state?: { from?: string } }

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (initialising) return <LoadingBlock label="Checking your session…" />
  if (user) return <Navigate to={location.state?.from ?? '/'} replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : 'Something went wrong. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-md bg-forest-600 text-sm font-bold text-white">
            TE
          </span>
          <div className="leading-tight">
            <h1 className="text-lg font-semibold text-gray-900">Camera Inventory</h1>
            <p className="text-sm text-gray-500">Similipal Tiger Reserve</p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-lg bg-white p-6 ring-1 ring-gray-200"
          noValidate
        >
          {error && <ErrorBanner message={error} />}

          <Field label="Email" htmlFor="email" required>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              autoFocus
              required
              value={email}
              invalid={Boolean(error)}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@similipal.test"
            />
          </Field>

          <Field label="Password" htmlFor="password" required>
            <div className="relative">
              <Input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                value={password}
                invalid={Boolean(error)}
                onChange={(event) => setPassword(event.target.value)}
                className="pr-16"
              />
              <button
                type="button"
                onClick={() => setShowPassword((shown) => !shown)}
                aria-pressed={showPassword}
                aria-controls="password"
                className="absolute inset-y-0 right-0 flex items-center rounded-r-md px-3 text-xs font-medium text-gray-600 hover:text-gray-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-700"
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </Field>

          <Button type="submit" loading={submitting} className="w-full">
            Sign in
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-gray-500">
          Demo accounts are listed in the README. All data in this prototype is fictional.
        </p>
      </div>
    </div>
  )
}

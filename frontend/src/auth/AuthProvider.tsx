import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, api } from '../lib/api'
import type { User } from '../lib/types'
import { AuthContext } from './AuthContext'
import type { AuthState } from './AuthContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [initialising, setInitialising] = useState(true)

  // The session cookie is httpOnly, so the only way to know whether we are
  // signed in is to ask the API.
  useEffect(() => {
    let cancelled = false
    api
      .get<User>('/api/auth/me')
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setInitialising(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post<{ user: User }>('/api/auth/login', { email, password })
    setUser(response.user)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/api/auth/logout')
    } catch (error) {
      if (!(error instanceof ApiError)) throw error // already signed out
    }
    setUser(null)
  }, [])

  const value = useMemo<AuthState>(
    () => ({ user, initialising, login, logout, isAdmin: user?.role === 'reserve_admin' }),
    [user, initialising, login, logout],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

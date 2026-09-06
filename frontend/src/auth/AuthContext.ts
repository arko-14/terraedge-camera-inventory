import { createContext, use } from 'react'

import type { User } from '../lib/types'

export interface AuthState {
  user: User | null
  /** True until the initial "am I already signed in?" check completes. */
  initialising: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isAdmin: boolean
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const context = use(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}

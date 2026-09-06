import { useEffect, useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { api } from './api'
import type { Range } from './types'

/** Delay a fast-changing value so typing does not fire a request per keystroke. */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}

/** Ranges and their beats change rarely, so they are cached and rarely refetched.
 *
 * Deliberately not `Infinity`: filters send range and beat *ids*, so a tab left
 * open across a reseed would keep offering ids that no longer exist and every
 * filter would silently return nothing. A finite window lets it recover.
 */
export function useRanges() {
  return useQuery({
    queryKey: ['ranges'],
    queryFn: () => api.get<Range[]>('/api/ranges'),
    staleTime: 10 * 60_000,
  })
}

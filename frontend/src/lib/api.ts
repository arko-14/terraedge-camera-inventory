/**
 * Fetch wrapper around the TerraEdge API.
 *
 * Nothing here stores a token: the session is a cookie the browser sends
 * automatically. Unsafe requests echo the readable CSRF cookie back in an
 * `X-CSRF-Token` header, which the API requires for cookie-authenticated
 * writes.
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

const CSRF_COOKIE = 'terraedge_csrf'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export interface FieldError {
  field: string
  message: string
}

export class ApiError extends Error {
  status: number
  fieldErrors: FieldError[]

  constructor(status: number, message: string, fieldErrors: FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
  }

  get isUnauthenticated() {
    return this.status === 401
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) headers['X-CSRF-Token'] = csrf
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    // No response at all. A sleeping free-tier instance takes ~50s to wake.
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }

  if (response.status === 204) return undefined as T

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : null
    throw new ApiError(
      response.status,
      detail ?? `Request failed (${response.status}).`,
      Array.isArray(payload?.errors) ? payload.errors : [],
    )
  }

  return payload as T
}

/** POST a file as multipart/form-data. The browser sets the boundary itself. */
async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)

  const headers: Record<string, string> = {}
  const csrf = readCookie(CSRF_COOKIE)
  if (csrf) headers['X-CSRF-Token'] = csrf

  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: form,
  })

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      response.status,
      typeof payload?.detail === 'string' ? payload.detail : 'Upload failed.',
      Array.isArray(payload?.errors) ? payload.errors : [],
    )
  }
  return payload as T
}

/** Fetch a file through the API (so auth headers apply) and save it. */
async function download(path: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include' })
  if (!response.ok) {
    throw new ApiError(response.status, 'Could not download the file.')
  }

  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export const api = {
  get: <T>(path: string) => request<T>(path, 'GET'),
  post: <T>(path: string, body?: unknown) => request<T>(path, 'POST', body),
  patch: <T>(path: string, body?: unknown) => request<T>(path, 'PATCH', body),
  upload,
  download,
}

/** Build a querystring, omitting empty values so the URL stays readable. */
export function toQueryString(
  params: Record<string, string | number | null | undefined>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

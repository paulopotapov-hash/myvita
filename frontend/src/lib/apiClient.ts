/**
 * Single fetch wrapper for the whole app. Every backend call goes through
 * here — no component or service should call `fetch` directly.
 *
 * Security-critical behavior implemented here, matching backend/app/core/security.py
 * and backend/README.md#segurança-csrf exactly:
 *   - `credentials: 'include'` on every request — the session lives in an
 *     httpOnly cookie (myvita_session), never in JS-accessible storage.
 *   - CSRF: on every non-safe method (POST/PUT/PATCH/DELETE), reads the
 *     `myvita_csrf` cookie (deliberately NOT httpOnly, readable by design)
 *     and echoes it in the `X-CSRF-Token` header. GET/HEAD/OPTIONS never
 *     need this — the backend doesn't check it there either.
 *   - Reads `X-Request-ID` off every response (backend/app/core/request_context.py)
 *     and attaches it to thrown errors, so a support conversation can
 *     reference the exact backend log line without exposing anything
 *     sensitive to the user.
 */

const CSRF_COOKIE_NAME = 'myvita_csrf'
const CSRF_HEADER_NAME = 'X-CSRF-Token'
const REQUEST_ID_HEADER = 'X-Request-ID'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
export const SESSION_EXPIRED_EVENT = 'myvita:session-expired'

/**
 * API base path. Empty string in both dev (Vite proxies /api, see
 * vite.config.ts) and production (the SPA is served from the same origin
 * as the API, or a reverse proxy forwards /api through) — see
 * frontend/README section on VITE_API_BASE_URL for the one case where an
 * absolute URL is genuinely needed (API on a different origin/subdomain).
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  readonly status: number
  readonly requestId: string | null
  /** Backend's own `detail` field when present — safe to show to the user
   * as-is; the backend never puts stack traces or internals there (see
   * backend/app/main.py's exception handlers). */
  readonly detail: string | null
  /** Field-level validation errors, when the backend returned FastAPI's
   * standard 422 shape. Keyed by field name for form display. */
  readonly fieldErrors: Record<string, string> | null

  constructor(
    status: number,
    message: string,
    options: { requestId?: string | null; detail?: string | null; fieldErrors?: Record<string, string> | null } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.requestId = options.requestId ?? null
    this.detail = options.detail ?? null
    this.fieldErrors = options.fieldErrors ?? null
  }
}

/** Thrown when the request never reached the backend at all (offline, DNS,
 * CORS misconfiguration, the API being down) — distinct from ApiError so
 * the UI can show "sem ligação" instead of a generic error. */
export class NetworkError extends Error {
  constructor() {
    super('network_error')
    this.name = 'NetworkError'
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

/** Parses FastAPI's standard 422 validation error shape into
 * `{ field: message }`, ignoring anything that isn't in that exact shape
 * rather than guessing — an unrecognized error body just falls back to
 * the generic message, never a crash. */
function parseFieldErrors(body: unknown): Record<string, string> | null {
  if (
    typeof body !== 'object' ||
    body === null ||
    !('detail' in body) ||
    !Array.isArray((body as { detail: unknown }).detail)
  ) {
    return null
  }
  const out: Record<string, string> = {}
  for (const item of (body as { detail: unknown[] }).detail) {
    if (
      typeof item === 'object' &&
      item !== null &&
      'loc' in item &&
      'msg' in item &&
      Array.isArray((item as { loc: unknown }).loc)
    ) {
      const loc = (item as { loc: unknown[] }).loc
      const field = String(loc[loc.length - 1])
      out[field] = String((item as { msg: unknown }).msg)
    }
  }
  return Object.keys(out).length > 0 ? out : null
}

export interface RequestOptions {
  method?: string
  body?: unknown
  signal?: AbortSignal
  onResponse?: (response: Response) => void
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (!SAFE_METHODS.has(method)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME)
    if (csrfToken) {
      headers[CSRF_HEADER_NAME] = csrfToken
    }
    // No CSRF cookie yet (never logged in) — let the request go through
    // anyway; the backend will correctly reject it with 403, which the
    // UI surfaces as a normal ApiError. Silently blocking it here would
    // just turn one clear error into a more confusing one.
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: 'include',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    })
  } catch {
    throw new NetworkError()
  }

  const requestId = response.headers.get(REQUEST_ID_HEADER)

  if (response.status === 204) {
    options.onResponse?.(response)
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  const rawBody = contentType.includes('application/json') ? await response.json().catch(() => null) : null

  if (!response.ok) {
    const detail =
      rawBody && typeof rawBody === 'object' && rawBody !== null && 'detail' in rawBody
        ? typeof (rawBody as { detail: unknown }).detail === 'string'
          ? ((rawBody as { detail: string }).detail as string)
          : null
        : null
    if (response.status === 401 && path !== '/api/v1/auth/me' && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { path } }))
    }
    throw new ApiError(response.status, detail ?? `HTTP ${response.status}`, {
      requestId,
      detail,
      fieldErrors: parseFieldErrors(rawBody),
    })
  }

  options.onResponse?.(response)
  return rawBody as T
}

export interface PageResult<T> {
  items: T[]
  total: number
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => apiRequest<T>(path, { method: 'GET', signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    apiRequest<T>(path, { method: 'POST', body, signal }),
  patch: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    apiRequest<T>(path, { method: 'PATCH', body, signal }),
  delete: <T>(path: string, signal?: AbortSignal) => apiRequest<T>(path, { method: 'DELETE', signal }),
  getPage: async <T>(path: string, signal?: AbortSignal): Promise<PageResult<T>> => {
    let total = 0
    const items = await apiRequest<T[]>(path, {
      method: 'GET',
      signal,
      onResponse: (response) => {
        total = Number(response.headers.get('X-Total-Count') ?? 0)
      },
    })
    return { items, total }
  },
}

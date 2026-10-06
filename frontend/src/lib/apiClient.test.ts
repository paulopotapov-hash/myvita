import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, api, apiRequest } from '../lib/apiClient'

function mockFetchOnce(response: Partial<Response> & { jsonBody?: unknown }) {
  const { jsonBody, ...rest } = response
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => jsonBody,
      ...rest,
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'myvita_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;'
})

describe('apiClient', () => {
  it('always sends credentials: include', async () => {
    mockFetchOnce({ jsonBody: { ok: true }, headers: new Headers({ 'content-type': 'application/json' }) })
    await apiRequest('/api/v1/auth/me')
    const call = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call[1].credentials).toBe('include')
  })

  it('attaches X-CSRF-Token from the myvita_csrf cookie on POST', async () => {
    document.cookie = 'myvita_csrf=test-csrf-value'
    mockFetchOnce({ jsonBody: { ok: true }, headers: new Headers({ 'content-type': 'application/json' }) })

    await apiRequest('/api/v1/staff', { method: 'POST', body: { foo: 'bar' } })

    const call = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call[1].headers['X-CSRF-Token']).toBe('test-csrf-value')
  })

  it('never attaches X-CSRF-Token on GET', async () => {
    document.cookie = 'myvita_csrf=test-csrf-value'
    mockFetchOnce({ jsonBody: {}, headers: new Headers({ 'content-type': 'application/json' }) })

    await apiRequest('/api/v1/auth/me', { method: 'GET' })

    const call = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call[1].headers['X-CSRF-Token']).toBeUndefined()
  })

  it('throws ApiError with the backend detail message on a non-2xx response', async () => {
    mockFetchOnce({
      ok: false,
      status: 401,
      headers: new Headers({ 'content-type': 'application/json' }),
      jsonBody: { detail: 'Email ou palavra-passe incorretos.' },
    })

    await expect(apiRequest('/api/v1/auth/login', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 401,
      detail: 'Email ou palavra-passe incorretos.',
    })
  })

  it('captures the request id from the response header on error', async () => {
    mockFetchOnce({
      ok: false,
      status: 500,
      headers: new Headers({ 'X-Request-ID': 'abc123', 'content-type': 'application/json' }),
      jsonBody: { detail: 'Erro interno do servidor.' },
    })

    try {
      await apiRequest('/api/v1/auth/me')
      throw new Error('should have thrown')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).requestId).toBe('abc123')
    }
  })

  it('throws NetworkError when fetch itself fails (offline, DNS, etc.)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    )
    await expect(apiRequest('/api/v1/auth/me')).rejects.toBeInstanceOf(NetworkError)
  })

  it('parses FastAPI 422 validation errors into field errors', async () => {
    mockFetchOnce({
      ok: false,
      status: 422,
      headers: new Headers({ 'content-type': 'application/json' }),
      jsonBody: { detail: [{ loc: ['body', 'email'], msg: 'value is not a valid email address' }] },
    })

    try {
      await apiRequest('/api/v1/auth/login', { method: 'POST', body: {} })
      throw new Error('should have thrown')
    } catch (error) {
      expect((error as ApiError).fieldErrors).toEqual({ email: 'value is not a valid email address' })
    }
  })

  it('reads the B6 pagination total from X-Total-Count', async () => {
    mockFetchOnce({
      jsonBody: [{ id: 'patient-1' }],
      headers: new Headers({ 'content-type': 'application/json', 'X-Total-Count': '27' }),
    })

    await expect(api.getPage('/api/v1/patients?page=2&page_size=20')).resolves.toEqual({
      items: [{ id: 'patient-1' }],
      total: 27,
    })
  })
})

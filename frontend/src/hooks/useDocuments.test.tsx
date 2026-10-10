import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDownloadDocument, usePatientDocuments, useUploadDocument } from './useDocuments'
import { parseContentDispositionFilename } from '../lib/apiClient'
import { documentsService } from '../services/documents'

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json', ...(init.headers ?? {}) }, ...init })
}

describe('useDocuments', () => {
  afterEach(() => vi.restoreAllMocks())

  it('lists with page params, reads X-Total-Count, uploads file + title as multipart and refetches', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    const docs = [{ id: 'd1', patient_id: 'p1', title: 'Análises', uploaded_by_name: 'Dra. Rita', original_filename: 'a.pdf', content_type: 'application/pdf', file_size: 1, created_at: '2026-09-24T10:00:00Z' }]
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'POST') {
        expect(init.body).toBeInstanceOf(FormData)
        expect((init.body as FormData).get('file')).toBeInstanceOf(File)
        expect((init.body as FormData).get('title')).toBe('Análises')
        expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
        expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-1')
        return jsonResponse(docs[0], { status: 201 })
      }
      expect(url).toContain('/api/v1/patients/p1/documents?page=1&page_size=20')
      return jsonResponse(docs, { headers: { 'X-Total-Count': '7' } })
    })
    document.cookie = 'myvita_csrf=csrf-1'
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => ({
      list: usePatientDocuments('p1', 1, 20),
      upload: useUploadDocument('p1'),
    }), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.list.data?.total).toBe(7))
    const listCalls = () => fetchMock.mock.calls.filter(([, init]) => (init?.method ?? 'GET') === 'GET').length
    expect(listCalls()).toBe(1)

    await act(() => result.current.upload.mutateAsync({ file: new File(['%PDF-'], 'a.pdf', { type: 'application/pdf' }), title: 'Análises' }))
    await waitFor(() => expect(listCalls()).toBe(2))
  })

  it('has no delete call at all: documents are append-only (D3)', () => {
    expect(Object.keys(documentsService).sort()).toEqual(['download', 'listForPatient', 'upload'])
  })

  it('downloads via the authenticated endpoint and names the file from Content-Disposition', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('%PDF-', {
      status: 200,
      headers: { 'content-type': 'application/pdf', 'content-disposition': "attachment; filename*=UTF-8''an%C3%A1lises.pdf" },
    }))
    const createObjectURL = vi.fn(() => 'blob:doc')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const client = new QueryClient()
    const { result } = renderHook(() => useDownloadDocument(), { wrapper: wrapper(client) })
    await act(() => result.current.mutateAsync({ documentId: 'd1', fallbackName: 'fallback.pdf' }))
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('/api/v1/documents/d1/download')
    expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({ credentials: 'include' })
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:doc')
  })

  it('rejects downloads with a typed ApiError on 404', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'Documento não encontrado.' }, { status: 404 }))
    const client = new QueryClient()
    const { result } = renderHook(() => useDownloadDocument(), { wrapper: wrapper(client) })
    await expect(act(() => result.current.mutateAsync({ documentId: 'x', fallbackName: 'x.pdf' }))).rejects.toMatchObject({ status: 404, detail: 'Documento não encontrado.' })
  })

  it('parses both Content-Disposition filename variants', () => {
    expect(parseContentDispositionFilename("attachment; filename*=UTF-8''relat%C3%B3rio.pdf")).toBe('relatório.pdf')
    expect(parseContentDispositionFilename('attachment; filename="plain.png"')).toBe('plain.png')
    expect(parseContentDispositionFilename(null)).toBeNull()
  })
})

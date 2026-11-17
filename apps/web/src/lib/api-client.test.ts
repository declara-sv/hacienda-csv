import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getToken } from '@clerk/tanstack-react-start'
import {
  ApiError,
  catalogsApi,
  clientsApi,
  documentsApi,
  meApi,
  runsApi,
  setUnauthorizedHandler,
  uploadsApi,
} from './api-client'
import { documentDto, rentaCatalog } from '#/test/fixtures'

const upload = {
  id: 'u1',
  filingPeriodId: 'p1',
  originalFileName: 'ventas.xlsx',
  sourceFileKind: 'Excel',
  contentType: 'application/octet-stream',
  sizeBytes: 10,
  createdAtUtc: '2026-09-06T00:00:00Z',
  includedInLatestRun: false,
  extractionStatus: 'Completed',
  extractionError: null,
  documentsCount: 2,
}
const run = {
  id: 'r1',
  filingPeriodId: 'p1',
  version: 1,
  status: 'Pending',
  errorMessage: null,
  createdAtUtc: '2026-09-06T00:00:00Z',
  startedAtUtc: null,
  completedAtUtc: null,
  artifacts: [],
  issues: [],
  files: [
    {
      uploadId: 'u1',
      originalFileName: 'ventas.xlsx',
      sourceFileKind: 'Excel',
      status: 'Pending',
      errorMessage: null,
    },
  ],
}
const fetchMock = vi.fn<typeof fetch>()
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  fetchMock.mockReset()
})

describe('Clerk session token', () => {
  it('sends the current Clerk token as a Bearer header on every request', async () => {
    vi.mocked(getToken)
      .mockResolvedValueOnce('token-1')
      .mockResolvedValueOnce('token-2')
    fetchMock
      .mockResolvedValueOnce(json([]))
      .mockResolvedValueOnce(json(rentaCatalog))

    await clientsApi.list()
    await catalogsApi.renta()

    const authHeader = (call: number) =>
      new Headers(fetchMock.mock.calls[call][1]?.headers).get('Authorization')
    expect(authHeader(0)).toBe('Bearer token-1')
    expect(authHeader(1)).toBe('Bearer token-2')
    expect(getToken).toHaveBeenCalledTimes(2)
  })

  it('sends no Authorization header when there is no Clerk session', async () => {
    vi.mocked(getToken).mockResolvedValueOnce(null)
    fetchMock.mockResolvedValueOnce(json([]))

    await clientsApi.list()

    expect(
      new Headers(fetchMock.mock.calls[0][1]?.headers).has('Authorization'),
    ).toBe(false)
  })

  it('reads the signed-in user and account from /api/me', async () => {
    const me = {
      user: { id: 'u1', email: 'ana@example.com', fullName: 'Ana' },
      account: { id: 'a1', name: 'Despacho Ana', role: 'owner' },
    }
    fetchMock.mockResolvedValueOnce(json(me))

    await expect(meApi.get()).resolves.toEqual(me)
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/me$/)
  })

  it('authorizes artifact downloads with the Clerk token', async () => {
    vi.stubGlobal('window', {
      URL: { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() },
      document: {
        createElement: () => ({ click: vi.fn(), remove: vi.fn() }),
        body: { appendChild: vi.fn() },
      },
    })
    fetchMock.mockResolvedValueOnce(new Response('csv'))

    await uploadsApi.downloadArtifact('a1', 'anexo.csv')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/artifacts\/a1\/download$/)
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer test-token',
    )
  })
})

describe('401 from the API', () => {
  it('sends the user to sign-in and still rejects with the ApiError', async () => {
    const onUnauthorized = vi.fn()
    const restore = setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockResolvedValueOnce(json({ title: 'Token inválido.' }, 401))

    await expect(clientsApi.list()).rejects.toMatchObject({
      status: 401,
      message: 'Token inválido.',
    })
    await vi.waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1))
    restore()
  })

  it('redirects once when several requests fail together', async () => {
    let finish: () => void = () => {}
    const onUnauthorized = vi.fn(
      () => new Promise<void>((resolve) => (finish = resolve)),
    )
    const restore = setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockImplementation(async () => json({ title: 'No' }, 401))

    await Promise.allSettled([
      clientsApi.list(),
      catalogsApi.renta(),
      runsApi.list('c1', 'p1'),
    ])
    await vi.waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1))
    finish()
    restore()
  })

  it('falls back to a full page load of /login without a registered handler', async () => {
    const assign = vi.fn()
    vi.stubGlobal('window', { location: { assign } })
    fetchMock.mockResolvedValueOnce(json({ title: 'No' }, 401))

    await expect(clientsApi.list()).rejects.toBeInstanceOf(ApiError)
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('/login'))
  })

  it('does not redirect on other errors', async () => {
    const onUnauthorized = vi.fn()
    const restore = setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockResolvedValueOnce(json({ title: 'Prohibido' }, 403))

    await expect(clientsApi.list()).rejects.toMatchObject({ status: 403 })
    await Promise.resolve()
    expect(onUnauthorized).not.toHaveBeenCalled()
    restore()
  })
})

describe('document API', () => {
  it('lists real uploads without obsolete jobs', async () => {
    fetchMock.mockResolvedValueOnce(json([upload]))
    await expect(uploadsApi.list('c1', 'p1')).resolves.toEqual([upload])
    expect(fetchMock.mock.calls[0][0]).toMatch(
      /\/api\/clients\/c1\/periods\/p1\/uploads$/,
    )
  })

  it('uploads one multipart document and never starts generation', async () => {
    fetchMock.mockResolvedValueOnce(json(upload, 201))
    const file = new File(['data'], 'ventas.xlsx')
    await expect(
      uploadsApi.create('c1', 'p1', { file, sourceFileKind: 'Excel' }),
    ).resolves.toEqual(upload)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/uploads$/)
    expect(init?.method).toBe('POST')
    const body = init?.body as FormData
    expect([...body.keys()]).toEqual(['file', 'sourceFileKind'])
    expect((body.get('file') as File).name).toBe(file.name)
    expect(await (body.get('file') as File).text()).toBe('data')
    expect(body.get('sourceFileKind')).toBe('Excel')
    expect(new Headers(init?.headers).get('Content-Type')).toBeNull()
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer test-token',
    )
  })

  it('deletes an upload with a bodyless 204 response', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(uploadsApi.remove('c1', 'p1', 'u1')).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][0]).toMatch(
      /\/api\/clients\/c1\/periods\/p1\/uploads\/u1$/,
    )
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE')
  })
})

describe('generation API', () => {
  it('lists runs and normalizes nested numeric statuses', async () => {
    fetchMock.mockResolvedValueOnce(
      json([{ ...run, status: 3, files: [{ ...run.files[0], status: 2 }] }]),
    )
    await expect(runsApi.list('c1', 'p1')).resolves.toEqual([
      {
        ...run,
        status: 'Completed',
        files: [{ ...run.files[0], status: 'Included' }],
      },
    ])
    expect(fetchMock.mock.calls[0][0]).toMatch(
      /\/api\/clients\/c1\/periods\/p1\/runs$/,
    )
    expect(fetchMock.mock.calls[0][1]?.method ?? 'GET').toBe('GET')
  })

  it('explicitly starts generation with a bodyless POST and accepts 202', async () => {
    fetchMock.mockResolvedValueOnce(json(run, 202))
    await expect(runsApi.create('c1', 'p1')).resolves.toEqual(run)
    expect(fetchMock.mock.calls[0][0]).toMatch(
      /\/api\/clients\/c1\/periods\/p1\/runs$/,
    )
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
  })
})

describe('validation errors', () => {
  it('prefers the first validation detail over the ProblemDetails title', async () => {
    const details = {
      title: 'One or more validation errors occurred.',
      status: 400,
      errors: { uploads: ['El período no tiene archivos para generar.'] },
    }
    fetchMock.mockResolvedValueOnce(json(details, 400))

    const error = await runsApi.create('c1', 'p1').catch((reason) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).message).toBe(
      'El período no tiene archivos para generar.',
    )
    expect((error as ApiError).status).toBe(400)
    expect((error as ApiError).details).toEqual(details)
  })

  it('accepts a plain string validation detail', async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        { title: 'Bad Request', errors: { file: 'Archivo inválido.' } },
        400,
      ),
    )
    await expect(uploadsApi.remove('c1', 'p1', 'u1')).rejects.toMatchObject({
      message: 'Archivo inválido.',
    })
  })

  it('keeps the title when the body carries no validation errors', async () => {
    fetchMock.mockResolvedValueOnce(json({ title: 'Conflicto.' }, 409))
    await expect(runsApi.create('c1', 'p1')).rejects.toMatchObject({
      message: 'Conflicto.',
    })
  })
})

describe.each([400, 409])('API errors %s', (status) => {
  it.each(['remove', 'createRun'] as const)(
    'surfaces %s validation/conflict failures',
    async (action) => {
      const details = { title: 'Request rejected' }
      fetchMock.mockResolvedValueOnce(json(details, status))
      const request =
        action === 'remove'
          ? uploadsApi.remove('c1', 'p1', 'u1')
          : runsApi.create('c1', 'p1')
      await expect(request).rejects.toMatchObject({
        status,
        message: details.title,
        details,
      })
    },
  )
})

describe('extraction fields on uploads', () => {
  it('defaults the extraction fields of uploads that predate extraction', async () => {
    const {
      extractionStatus: _status,
      extractionError: _error,
      documentsCount: _count,
      ...legacy
    } = upload
    fetchMock.mockResolvedValueOnce(json([legacy]))
    await expect(uploadsApi.list('c1', 'p1')).resolves.toEqual([
      {
        ...legacy,
        extractionStatus: 'Completed',
        extractionError: null,
        documentsCount: 0,
      },
    ])
  })

  it('re-reads an upload with a bodyless POST', async () => {
    fetchMock.mockResolvedValueOnce(
      json({ ...upload, extractionStatus: 'Pending' }, 202),
    )
    await expect(uploadsApi.reextract('c1', 'p1', 'u1')).resolves.toEqual({
      ...upload,
      extractionStatus: 'Pending',
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(
      /\/api\/clients\/c1\/periods\/p1\/uploads\/u1\/reextract$/,
    )
    expect(init?.method).toBe('POST')
    expect(init?.body).toBeUndefined()
  })

  it('accepts a 204 from reextract', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(
      uploadsApi.reextract('c1', 'p1', 'u1'),
    ).resolves.toBeUndefined()
  })
})

describe('documents API', () => {
  it('lists documents and keeps money as decimal strings', async () => {
    const raw = { ...documentDto('d1'), total: 48.1, totalExentas: null }
    fetchMock.mockResolvedValueOnce(json([raw]))
    const [item] = await documentsApi.list('c1', 'p1')
    expect(item.total).toBe('48.10')
    expect(item.totalExentas).toBe('0.00')
    expect(item.totalGravadas).toBe('48.14')
    expect(fetchMock.mock.calls[0][0]).toMatch(
      /\/api\/clients\/c1\/periods\/p1\/documents$/,
    )
  })

  it('patches only the given fields, sending null to restore the client default', async () => {
    const updated = documentDto('d1', { tipoOperacionRenta: null })
    fetchMock.mockResolvedValueOnce(json(updated))
    await expect(
      documentsApi.update('c1', 'p1', 'd1', {
        tipoOperacionRenta: null,
        total: '50.00',
      }),
    ).resolves.toEqual(updated)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/documents\/d1$/)
    expect(init?.method).toBe('PATCH')
    expect(JSON.parse(String(init?.body))).toEqual({
      tipoOperacionRenta: null,
      total: '50.00',
    })
  })

  it('applies bulk changes to several documents', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(
      documentsApi.bulkUpdate('c1', 'p1', {
        documentIds: ['d1', 'd2'],
        tipoIngresoRenta: '4',
      }),
    ).resolves.toBeUndefined()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/clients\/c1\/periods\/p1\/documents\/bulk$/)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({
      documentIds: ['d1', 'd2'],
      tipoIngresoRenta: '4',
    })
  })
})

describe('clients and catalogs API', () => {
  const payload = {
    name: 'Cliente',
    taxId: '0614-010101-101-1',
    notes: null,
    nit: '06140101011011',
    nrc: '1234567',
    defaultTipoOperacion: '1',
    defaultTipoIngreso: '3',
  }

  it('creates a client with its fiscal identity and Renta defaults', async () => {
    fetchMock.mockResolvedValueOnce(json({ id: 'c1', ...payload }, 201))
    await clientsApi.create(payload)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/clients$/)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual(payload)
  })

  it('updates a client with PUT', async () => {
    fetchMock.mockResolvedValueOnce(json({ id: 'c1', ...payload }))
    await clientsApi.update('c1', payload)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/clients\/c1$/)
    expect(init?.method).toBe('PUT')
    expect(JSON.parse(String(init?.body))).toEqual(payload)
  })

  it('reads the Renta catalog', async () => {
    fetchMock.mockResolvedValueOnce(json(rentaCatalog))
    await expect(catalogsApi.renta()).resolves.toEqual(rentaCatalog)
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/catalogs\/renta$/)
  })
})

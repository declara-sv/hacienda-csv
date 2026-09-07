import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, runsApi, uploadsApi } from './api-client'

vi.mock('#/auth/auth-storage', () => ({
  readSession: vi.fn(() => ({ accessToken: 'test-token' })),
  writeSession: vi.fn(),
  clearSession: vi.fn(),
}))

const upload = {
  id: 'u1',
  filingPeriodId: 'p1',
  originalFileName: 'ventas.xlsx',
  sourceFileKind: 'Excel',
  contentType: 'application/octet-stream',
  sizeBytes: 10,
  createdAtUtc: '2026-09-06T00:00:00Z',
  includedInLatestRun: false,
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
      json({ title: 'Bad Request', errors: { file: 'Archivo inválido.' } }, 400),
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

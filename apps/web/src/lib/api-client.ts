import { getToken } from '@clerk/tanstack-react-start'
import { normalizeDocument, normalizeRun, normalizeUpload } from './normalize'
import type {
  ClientDetail,
  ClientPayload,
  ClientSummary,
  DocumentBulkUpdate,
  DocumentDto,
  DocumentPatch,
  GenerationRun,
  MeResponse,
  RentaCatalog,
  Upload,
} from './api-types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:5184'

export class ApiError extends Error {
  readonly status: number
  readonly details: unknown

  constructor(status: number, message: string, details: unknown) {
    super(message)
    this.status = status
    this.details = details
  }
}

/**
 * ValidationProblemDetails carries the human message in `errors`; its `title`
 * is English framework boilerplate ("One or more validation errors occurred.").
 */
function firstValidationDetail(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null) return null
  const errors = (payload as { errors?: unknown }).errors
  if (typeof errors !== 'object' || errors === null || Array.isArray(errors))
    return null

  for (const value of Object.values(errors)) {
    if (typeof value === 'string' && value.trim()) return value
    if (!Array.isArray(value)) continue
    const first = value.find(
      (item): item is string => typeof item === 'string' && item.trim() !== '',
    )
    if (first) return first
  }

  return null
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: unknown = null

  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  const messageFromServer =
    firstValidationDetail(payload) ??
    (typeof payload === 'object' && payload !== null && 'title' in payload
      ? String((payload as { title: string }).title)
      : typeof payload === 'object' && payload !== null && 'message' in payload
        ? String((payload as { message: string }).message)
        : 'Error inesperado en la API.')

  return new ApiError(response.status, messageFromServer, payload)
}

type UnauthorizedHandler = () => void | Promise<void>

/** Used until the app registers a router-aware handler (see ClerkSessionBridge). */
const defaultUnauthorizedHandler: UnauthorizedHandler = () => {
  if (typeof window !== 'undefined') {
    window.location.assign('/login')
  }
}

let unauthorizedHandler: UnauthorizedHandler = defaultUnauthorizedHandler
let unauthorizedInFlight: Promise<void> | null = null

/**
 * Sets what happens when the API answers 401 (missing or invalid Clerk token).
 * Returns a function that restores the default handler.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler) {
  unauthorizedHandler = handler
  return () => {
    if (unauthorizedHandler === handler) {
      unauthorizedHandler = defaultUnauthorizedHandler
    }
  }
}

/** Runs the handler once even when several requests fail together. */
function notifyUnauthorized() {
  if (!unauthorizedInFlight) {
    unauthorizedInFlight = Promise.resolve()
      .then(() => unauthorizedHandler())
      .catch(() => undefined)
      .finally(() => {
        unauthorizedInFlight = null
      })
  }
  return unauthorizedInFlight
}

/** Fetches with the current Clerk session token; Clerk refreshes it itself. */
async function authorizedFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  const token = await getToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_URL}${path}`, { ...init, headers })

  if (response.status === 401) {
    void notifyUnauthorized()
  }

  return response
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const bodyIsFormData = init.body instanceof FormData
  if (!bodyIsFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await authorizedFetch(path, { ...init, headers })

  if (!response.ok) {
    throw await parseError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('Content-Type') ?? ''
  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }

  return undefined as T
}

export const meApi = {
  get: () => request<MeResponse>('/api/me'),
}

export const clientsApi = {
  list: () => request<ClientSummary[]>('/api/clients'),

  get: (clientId: string) => request<ClientDetail>(`/api/clients/${clientId}`),

  create: (payload: ClientPayload) =>
    request<ClientDetail>('/api/clients', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  update: (clientId: string, payload: ClientPayload) =>
    request<ClientDetail>(`/api/clients/${clientId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  createPeriod: (clientId: string, payload: { year: number; month: number }) =>
    request(`/api/clients/${clientId}/periods`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  createConfig: (
    clientId: string,
    payload: {
      name: string
      prefillValuesJson: string
      transformationRulesJson?: string
      isActive: boolean
    },
  ) =>
    request(`/api/clients/${clientId}/configs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

export const uploadsApi = {
  list: (clientId: string, periodId: string) =>
    request<Upload[]>(
      `/api/clients/${clientId}/periods/${periodId}/uploads`,
    ).then((uploads) => uploads.map(normalizeUpload)),

  create: (
    clientId: string,
    periodId: string,
    payload: { file: File; sourceFileKind: 'Excel' | 'PDF' },
  ) => {
    const body = new FormData()
    body.append('file', payload.file)
    body.append('sourceFileKind', payload.sourceFileKind)

    return request<Upload>(
      `/api/clients/${clientId}/periods/${periodId}/uploads`,
      {
        method: 'POST',
        body,
      },
    ).then(normalizeUpload)
  },

  /** Reads the file again; the API replaces the upload's documents. */
  reextract: (clientId: string, periodId: string, uploadId: string) =>
    request<Upload | undefined>(
      `/api/clients/${clientId}/periods/${periodId}/uploads/${uploadId}/reextract`,
      { method: 'POST' },
    ).then((upload) => (upload ? normalizeUpload(upload) : undefined)),

  remove: (clientId: string, periodId: string, uploadId: string) =>
    request<void>(
      `/api/clients/${clientId}/periods/${periodId}/uploads/${uploadId}`,
      { method: 'DELETE' },
    ),

  async downloadArtifact(artifactId: string, fileName: string) {
    const response = await authorizedFetch(
      `/api/artifacts/${artifactId}/download`,
    )

    if (!response.ok) {
      throw await parseError(response)
    }

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = window.document.createElement('a')
    link.href = url
    link.download = fileName
    window.document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
}

export const runsApi = {
  list: (clientId: string, periodId: string) =>
    request<GenerationRun[]>(
      `/api/clients/${clientId}/periods/${periodId}/runs`,
    ).then((runs) => runs.map(normalizeRun)),

  create: (clientId: string, periodId: string) =>
    request<GenerationRun>(
      `/api/clients/${clientId}/periods/${periodId}/runs`,
      { method: 'POST' },
    ).then(normalizeRun),
}

const documentsPath = (clientId: string, periodId: string) =>
  `/api/clients/${clientId}/periods/${periodId}/documents`

export const documentsApi = {
  list: (clientId: string, periodId: string) =>
    request<DocumentDto[]>(documentsPath(clientId, periodId)).then((items) =>
      items.map(normalizeDocument),
    ),

  update: (
    clientId: string,
    periodId: string,
    documentId: string,
    patch: DocumentPatch,
  ) =>
    request<DocumentDto | undefined>(
      `${documentsPath(clientId, periodId)}/${documentId}`,
      { method: 'PATCH', body: JSON.stringify(patch) },
    ).then((item) => (item ? normalizeDocument(item) : undefined)),

  bulkUpdate: (
    clientId: string,
    periodId: string,
    update: DocumentBulkUpdate,
  ) =>
    request<unknown>(`${documentsPath(clientId, periodId)}/bulk`, {
      method: 'POST',
      body: JSON.stringify(update),
    }).then(() => undefined),
}

export const catalogsApi = {
  renta: () => request<RentaCatalog>('/api/catalogs/renta'),
}

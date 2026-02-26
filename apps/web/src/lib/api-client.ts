import { clearSession, readSession, writeSession } from '#/auth/auth-storage'
import type {
  AuthSession,
  ClientDetail,
  ClientSummary,
  Upload,
  UploadCreated,
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

let refreshPromise: Promise<AuthSession | null> | null = null

async function parseError(response: Response): Promise<ApiError> {
  let payload: unknown = null

  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  const messageFromServer =
    typeof payload === 'object' && payload !== null && 'title' in payload
      ? String((payload as { title: string }).title)
      : typeof payload === 'object' && payload !== null && 'message' in payload
        ? String((payload as { message: string }).message)
        : 'Error inesperado en la API.'

  return new ApiError(response.status, messageFromServer, payload)
}

async function refreshSession(current: AuthSession): Promise<AuthSession | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const response = await fetch(`${API_URL}/api/auth/refresh`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ refreshToken: current.refreshToken }),
        })

        if (!response.ok) {
          clearSession()
          return null
        }

        const next = (await response.json()) as AuthSession
        writeSession(next)
        return next
      } catch {
        clearSession()
        return null
      } finally {
        refreshPromise = null
      }
    })()
  }

  return refreshPromise
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { authenticated?: boolean } = {},
): Promise<T> {
  const authenticated = options.authenticated ?? true
  const headers = new Headers(init.headers)

  const bodyIsFormData = init.body instanceof FormData
  if (!bodyIsFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let session = readSession()
  if (authenticated && session?.accessToken) {
    headers.set('Authorization', `Bearer ${session.accessToken}`)
  }

  let response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  })

  if (response.status === 401 && authenticated && session) {
    const refreshed = await refreshSession(session)
    if (!refreshed) {
      throw await parseError(response)
    }

    session = refreshed
    const retryHeaders = new Headers(init.headers)
    if (!bodyIsFormData && !retryHeaders.has('Content-Type')) {
      retryHeaders.set('Content-Type', 'application/json')
    }
    retryHeaders.set('Authorization', `Bearer ${refreshed.accessToken}`)

    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: retryHeaders,
    })
  }

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

export const authApi = {
  register: (payload: { email: string; password: string; fullName: string }) =>
    request<AuthSession>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, { authenticated: false }),

  login: (payload: { email: string; password: string }) =>
    request<AuthSession>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, { authenticated: false }),

  logout: (refreshToken: string) =>
    request<void>('/api/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refreshToken }),
    }),
}

export const clientsApi = {
  list: () => request<ClientSummary[]>('/api/clients'),

  get: (clientId: string) => request<ClientDetail>(`/api/clients/${clientId}`),

  create: (payload: { name: string; taxId: string; notes?: string }) =>
    request<ClientDetail>('/api/clients', {
      method: 'POST',
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
    request<Upload[]>(`/api/clients/${clientId}/periods/${periodId}/uploads`),

  create: (
    clientId: string,
    periodId: string,
    payload: { file: File; sourceFileKind: 'Excel' | 'PDF' },
  ) => {
    const body = new FormData()
    body.append('file', payload.file)
    body.append('sourceFileKind', payload.sourceFileKind)

    return request<UploadCreated>(`/api/clients/${clientId}/periods/${periodId}/uploads`, {
      method: 'POST',
      body,
    })
  },

  async downloadArtifact(artifactId: string, fileName: string) {
    const session = readSession()
    if (!session) {
      throw new Error('No hay sesión activa.')
    }

    const response = await fetch(`${API_URL}/api/artifacts/${artifactId}/download`, {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    })

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

// @vitest-environment jsdom
import { useAuth, useClerk } from '@clerk/tanstack-react-start'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ClerkSessionBridge } from './ClerkSessionBridge'
import { clientsApi } from '#/lib/api-client'

const navigate = vi.fn(async () => undefined)
vi.mock('@tanstack/react-router', () => ({
  useRouter: () => ({ navigate }),
}))

const fetchMock = vi.fn<typeof fetch>()
const unauthorized = () =>
  new Response(JSON.stringify({ title: 'Token inválido.' }), {
    status: 401,
    headers: { 'Content-Type': 'application/json' },
  })

type AuthState = ReturnType<typeof useAuth>
type ClerkState = ReturnType<typeof useClerk>

function mockClerk(isSignedIn: boolean, userId: string | null = 'user_1') {
  const signOut = vi.fn(async () => undefined)
  vi.mocked(useClerk).mockReturnValue({
    isSignedIn,
    signOut,
  } as unknown as ClerkState)
  vi.mocked(useAuth).mockReturnValue({
    isLoaded: true,
    isSignedIn,
    userId,
  } as unknown as AuthState)
  return signOut
}

function renderBridge(queryClient = new QueryClient()) {
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ClerkSessionBridge />
    </QueryClientProvider>,
  )
  return { ...view, queryClient }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('ClerkSessionBridge', () => {
  it('ends the Clerk session and goes to /login when the API rejects the token', async () => {
    const signOut = mockClerk(true)
    vi.stubGlobal('fetch', fetchMock.mockResolvedValueOnce(unauthorized()))
    renderBridge()

    await expect(clientsApi.list()).rejects.toMatchObject({ status: 401 })

    await waitFor(() =>
      expect(signOut).toHaveBeenCalledWith({ redirectUrl: '/login' }),
    )
    expect(navigate).not.toHaveBeenCalled()
  })

  it('navigates to /login when there is no Clerk session', async () => {
    const signOut = mockClerk(false, null)
    vi.stubGlobal('fetch', fetchMock.mockResolvedValueOnce(unauthorized()))
    renderBridge()

    await expect(clientsApi.list()).rejects.toMatchObject({ status: 401 })

    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/login' }))
    expect(signOut).not.toHaveBeenCalled()
  })

  it('clears cached API data when the signed-in user changes', () => {
    mockClerk(true, 'user_1')
    const { rerender, queryClient } = renderBridge()
    queryClient.setQueryData(['clients'], [{ id: 'c1' }])

    rerender(
      <QueryClientProvider client={queryClient}>
        <ClerkSessionBridge />
      </QueryClientProvider>,
    )
    expect(queryClient.getQueryData(['clients'])).toEqual([{ id: 'c1' }])

    mockClerk(true, 'user_2')
    rerender(
      <QueryClientProvider client={queryClient}>
        <ClerkSessionBridge />
      </QueryClientProvider>,
    )
    expect(queryClient.getQueryData(['clients'])).toBeUndefined()
  })
})

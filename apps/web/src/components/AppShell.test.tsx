// @vitest-environment jsdom
import { useAuth } from '@clerk/tanstack-react-start'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'
import { I18nProvider } from '#/i18n/I18nProvider'
import { meApi } from '#/lib/api-client'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}))

function renderShell() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider>
        <AppShell>
          <p>contenido</p>
        </AppShell>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('AppShell', () => {
  it('shows the account name from /api/me for a signed-in user', async () => {
    vi.spyOn(meApi, 'get').mockResolvedValue({
      user: { id: 'u1', email: 'ana@example.com', fullName: 'Ana' },
      account: { id: 'a1', name: 'Despacho Ana', role: 'owner' },
    })

    renderShell()

    expect(await screen.findByText('Despacho Ana')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Clientes' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Ingresar' })).toBeNull()
  })

  it('does not call /api/me while signed out', () => {
    vi.mocked(useAuth).mockReturnValueOnce({
      isLoaded: true,
      isSignedIn: false,
      userId: null,
    } as unknown as ReturnType<typeof useAuth>)
    const get = vi.spyOn(meApi, 'get')

    renderShell()

    expect(get).not.toHaveBeenCalled()
  })
})

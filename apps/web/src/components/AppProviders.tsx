import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '#/auth/AuthContext'
import { I18nProvider } from '#/i18n/I18nProvider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>{children}</AuthProvider>
      </I18nProvider>
    </QueryClientProvider>
  )
}

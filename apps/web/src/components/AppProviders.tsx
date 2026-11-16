import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ClerkSessionBridge } from '#/auth/ClerkSessionBridge'
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
      <ClerkSessionBridge />
      <I18nProvider>{children}</I18nProvider>
    </QueryClientProvider>
  )
}

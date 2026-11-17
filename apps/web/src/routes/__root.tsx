import { ClerkProvider } from '@clerk/tanstack-react-start'
import { esES } from '@clerk/localizations'
import { HeadContent, Scripts, createRootRoute } from '@tanstack/react-router'
import { clerkAppearance } from '#/auth/clerk-appearance'
import { AFTER_AUTH_PATH, SIGN_IN_PATH, SIGN_UP_PATH } from '#/auth/paths'
import { AppProviders } from '#/components/AppProviders'
import { AppShell } from '#/components/AppShell'
import { ErrorView } from '#/components/ui/ErrorView'
import appCss from '../styles.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'HaciendaCSV' },
      { name: 'color-scheme', content: 'light dark' },
      {
        name: 'theme-color',
        media: '(prefers-color-scheme: light)',
        content: '#f7f5ef',
      },
      {
        name: 'theme-color',
        media: '(prefers-color-scheme: dark)',
        content: '#121917',
      },
    ],
    links: [
      { rel: 'stylesheet', href: appCss },
      { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
      { rel: 'apple-touch-icon', href: '/icon-192.png' },
      { rel: 'manifest', href: '/manifest.json' },
    ],
  }),
  shellComponent: RootDocument,
  errorComponent: ErrorView,
})

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        <HeadContent />
      </head>
      <body>
        <ClerkProvider
          localization={esES}
          appearance={clerkAppearance}
          signInUrl={SIGN_IN_PATH}
          signUpUrl={SIGN_UP_PATH}
          signInFallbackRedirectUrl={AFTER_AUTH_PATH}
          signUpFallbackRedirectUrl={AFTER_AUTH_PATH}
          afterSignOutUrl={SIGN_IN_PATH}
        >
          <AppProviders>
            <AppShell>{children}</AppShell>
          </AppProviders>
        </ClerkProvider>
        <Scripts />
      </body>
    </html>
  )
}

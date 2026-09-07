import { HeadContent, Scripts, createRootRoute } from '@tanstack/react-router'
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
        <AppProviders>
          <AppShell>{children}</AppShell>
        </AppProviders>
        <Scripts />
      </body>
    </html>
  )
}

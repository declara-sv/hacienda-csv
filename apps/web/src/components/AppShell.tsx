import { Show, UserButton, useAuth } from '@clerk/tanstack-react-start'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useI18n } from '#/i18n/I18nProvider'
import { meApi } from '#/lib/api-client'
import { buttonClasses } from './ui/Button'

const navLink =
  'inline-flex h-9 items-center rounded-full px-3.5 text-sm font-semibold text-ink transition duration-200 hover:bg-accent-soft sm:px-4'

const meQueryKey = ['me'] as const

function AccountName() {
  const { isSignedIn } = useAuth()
  const { data } = useQuery({
    queryKey: meQueryKey,
    queryFn: meApi.get,
    enabled: isSignedIn === true,
    staleTime: 5 * 60 * 1000,
  })

  if (!data) return null

  return (
    <span
      className="hidden max-w-[20ch] truncate text-sm text-ink-muted md:block"
      title={data.account.name}
    >
      {data.account.name}
    </span>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n()

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-surface-raised">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" className="flex flex-col leading-none">
            <span className="font-title text-xl tracking-wide text-ink sm:text-2xl">
              {t('appName')}
            </span>
            <span className="hidden text-[11px] uppercase tracking-[0.24em] text-accent sm:block">
              {t('appSubtitle')}
            </span>
          </Link>

          <nav
            aria-label="Principal"
            className="flex items-center gap-1 sm:gap-2"
          >
            <Show when="signed-in">
              <Link
                to="/clientes"
                className={navLink}
                activeProps={{
                  className: `${navLink} bg-ink text-surface hover:bg-ink`,
                }}
              >
                {t('menuClients')}
              </Link>
              <AccountName />
              <span className="inline-flex size-9 items-center justify-center">
                <UserButton />
              </span>
            </Show>
            <Show when="signed-out">
              <Link to="/login" className={navLink}>
                {t('menuLogin')}
              </Link>
              <Link
                to="/registro"
                className={buttonClasses('primary', 'sm', 'h-9 rounded-full')}
              >
                {t('menuRegister')}
              </Link>
            </Show>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 md:py-10">
        {children}
      </main>
    </div>
  )
}

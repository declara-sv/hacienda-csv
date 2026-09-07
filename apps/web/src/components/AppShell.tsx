import { Link, useRouter } from '@tanstack/react-router'
import { LogOut } from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '#/auth/AuthContext'
import { useI18n } from '#/i18n/I18nProvider'
import { buttonClasses } from './ui/Button'

const navLink =
  'inline-flex h-9 items-center rounded-full px-3.5 text-sm font-semibold text-ink transition duration-200 hover:bg-accent-soft sm:px-4'

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n()
  const { session, logout } = useAuth()
  const router = useRouter()
  const [loggingOut, setLoggingOut] = useState(false)

  const onLogout = async () => {
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      setLoggingOut(false)
      await router.navigate({ to: '/login' })
    }
  }

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
            {session ? (
              <>
                <Link
                  to="/clientes"
                  className={navLink}
                  activeProps={{
                    className: `${navLink} bg-ink text-surface hover:bg-ink`,
                  }}
                >
                  {t('menuClients')}
                </Link>
                <span
                  className="hidden max-w-[16ch] truncate text-sm text-ink-muted md:block"
                  title={session.user.fullName}
                >
                  {session.user.fullName}
                </span>
                <button
                  type="button"
                  className={buttonClasses('secondary', 'sm', 'h-9')}
                  onClick={onLogout}
                  aria-label={t('logout')}
                  disabled={loggingOut}
                  aria-busy={loggingOut || undefined}
                >
                  <LogOut className="size-4" strokeWidth={2} aria-hidden />
                  <span className="hidden sm:inline">{t('logout')}</span>
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className={navLink}>
                  {t('menuLogin')}
                </Link>
                <Link
                  to="/registro"
                  className={buttonClasses('primary', 'sm', 'h-9 rounded-full')}
                >
                  {t('menuRegister')}
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 md:py-10">
        {children}
      </main>
    </div>
  )
}

import { Link, useRouter } from '@tanstack/react-router'
import { useAuth } from '#/auth/AuthContext'
import { useI18n } from '#/i18n/I18nProvider'

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n()
  const { session, logout } = useAuth()
  const router = useRouter()

  const onLogout = async () => {
    try {
      await logout()
    } finally {
      await router.navigate({ to: '/login' })
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,#f5edd2,transparent_40%),radial-gradient(circle_at_bottom_right,#d8eee5,transparent_40%),#f7f5ef] text-[#1c2b2f]">
      <header className="border-b border-[#1c2b2f]/15 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="flex flex-col leading-none">
            <span className="font-title text-2xl tracking-wide">{t('appName')}</span>
            <span className="text-xs uppercase tracking-[0.24em] text-[#2f5f53]">
              {t('appSubtitle')}
            </span>
          </Link>

          <nav className="flex items-center gap-2">
            {session ? (
              <>
                <Link
                  to="/clientes"
                  className="rounded-full px-4 py-2 text-sm font-semibold text-[#1c2b2f] transition hover:bg-[#1c2b2f]/10"
                  activeProps={{ className: 'rounded-full bg-[#1c2b2f] px-4 py-2 text-sm font-semibold text-white' }}
                >
                  {t('menuClients')}
                </Link>
                <span className="hidden text-sm text-[#1c2b2f]/75 sm:block">{session.user.fullName}</span>
                <button
                  type="button"
                  className="rounded-full border border-[#1c2b2f]/20 px-4 py-2 text-sm font-semibold transition hover:bg-[#1c2b2f]/10"
                  onClick={onLogout}
                >
                  {t('logout')}
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="rounded-full px-4 py-2 text-sm font-semibold hover:bg-[#1c2b2f]/10">
                  {t('menuLogin')}
                </Link>
                <Link to="/registro" className="rounded-full bg-[#24513f] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1c2b2f]">
                  {t('menuRegister')}
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  )
}

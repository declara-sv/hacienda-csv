import { FileDown, FileUp, Users } from 'lucide-react'
import { useI18n } from '#/i18n/I18nProvider'
import type { CSSProperties, ReactNode } from 'react'

type AuthLayoutProps = {
  title: string
  intro: string
  footer: ReactNode
  children: ReactNode
}

export function AuthLayout({
  title,
  intro,
  footer,
  children,
}: AuthLayoutProps) {
  const { t } = useI18n()

  const points = [
    { Icon: Users, text: t('authPanelPoint1') },
    { Icon: FileUp, text: t('authPanelPoint2') },
    { Icon: FileDown, text: t('authPanelPoint3') },
  ]

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-start lg:gap-16">
      <aside className="rise hidden rounded-container bg-accent p-8 text-accent-ink lg:sticky lg:top-24 lg:block xl:p-10">
        <p className="font-title text-3xl leading-tight xl:text-4xl">
          {t('authPanelTitle')}
        </p>
        <p className="mt-4 max-w-[38ch] text-base leading-relaxed text-accent-ink/85">
          {t('authPanelBody')}
        </p>
        <ul className="mt-10 space-y-4">
          {points.map(({ Icon, text }) => (
            <li
              key={text}
              className="flex items-center gap-3 text-sm font-semibold"
            >
              <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-control bg-accent-ink/12">
                <Icon className="size-4" strokeWidth={1.75} aria-hidden />
              </span>
              {text}
            </li>
          ))}
        </ul>
      </aside>

      <section
        className="rise w-full max-w-md lg:pt-2"
        style={{ '--i': 1 } as CSSProperties}
      >
        <h1 className="font-title text-3xl leading-tight text-ink md:text-4xl">
          {title}
        </h1>
        <p className="mt-2 text-base text-ink-muted">{intro}</p>
        <div className="mt-8">{children}</div>
        <p className="mt-8 text-sm text-ink-muted">{footer}</p>
      </section>
    </div>
  )
}

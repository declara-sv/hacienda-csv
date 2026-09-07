import { Link } from '@tanstack/react-router'
import { ChevronRight } from 'lucide-react'
import { useI18n } from '#/i18n/I18nProvider'
import { Skeleton } from './Skeleton'
import type { LinkProps } from '@tanstack/react-router'

export type Crumb = {
  label: string | null
  to?: LinkProps['to']
  params?: LinkProps['params']
}

export function Breadcrumb({ items }: { items: Crumb[] }) {
  const { t } = useI18n()

  return (
    <nav aria-label={t('breadcrumbLabel')} className="text-sm">
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, index) => {
          const last = index === items.length - 1
          return (
            <li key={index} className="flex items-center gap-1.5">
              {index > 0 ? (
                <ChevronRight
                  className="size-3.5 text-ink-muted"
                  strokeWidth={2}
                  aria-hidden
                />
              ) : null}
              {item.label === null ? (
                <Skeleton className="h-4 w-24" />
              ) : last || !item.to ? (
                <span
                  className="font-semibold text-ink"
                  aria-current={last ? 'page' : undefined}
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  to={item.to}
                  params={item.params}
                  className="rounded-control text-ink-muted transition hover:text-accent"
                >
                  {item.label}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

import { Link, useRouter } from '@tanstack/react-router'
import { AlertTriangle } from 'lucide-react'
import { useI18n } from '#/i18n/I18nProvider'
import { Button, buttonClasses } from './Button'

export function ErrorView({ error }: { error: unknown }) {
  const { t } = useI18n()
  const router = useRouter()
  const detail = error instanceof Error ? error.message : null

  return (
    <div
      role="alert"
      className="rise mx-auto flex max-w-lg flex-col items-start gap-4 rounded-container border border-line bg-surface-raised p-6 shadow-raised"
    >
      <span className="inline-flex size-11 items-center justify-center rounded-container bg-danger-soft text-danger">
        <AlertTriangle className="size-5" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="space-y-1">
        <h1 className="text-lg font-semibold text-ink">{t('errorTitle')}</h1>
        <p className="text-sm text-ink-muted">{t('errorBody')}</p>
        {detail ? (
          <p className="pt-2 font-mono text-xs text-ink-muted">{detail}</p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        <Button onClick={() => router.invalidate()}>{t('errorRetry')}</Button>
        <Link to="/clientes" className={buttonClasses('secondary')}>
          {t('errorHome')}
        </Link>
      </div>
    </div>
  )
}

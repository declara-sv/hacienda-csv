import { AlertCircle, CheckCircle2, X } from 'lucide-react'
import { useI18n } from '#/i18n/I18nProvider'
import { cn } from '#/lib/cn'

type NoticeProps = {
  variant: 'error' | 'success'
  children: React.ReactNode
  onDismiss?: () => void
  className?: string
}

export function Notice({
  variant,
  children,
  onDismiss,
  className,
}: NoticeProps) {
  const { t } = useI18n()
  const isError = variant === 'error'
  const Icon = isError ? AlertCircle : CheckCircle2

  return (
    <div
      role={isError ? 'alert' : 'status'}
      className={cn(
        'rise flex items-start gap-3 rounded-control px-3 py-2.5 text-sm',
        isError ? 'bg-danger-soft text-danger' : 'bg-success-soft text-success',
        className,
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" strokeWidth={2} aria-hidden />
      <p className="flex-1">{children}</p>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={t('dismiss')}
          className="-m-1 rounded-control p-1 transition hover:bg-surface-raised/60"
        >
          <X className="size-4" aria-hidden />
        </button>
      ) : null}
    </div>
  )
}

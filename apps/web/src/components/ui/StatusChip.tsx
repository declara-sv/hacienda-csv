import { AlertCircle, CheckCircle2, Clock, Loader2 } from 'lucide-react'
import { useI18n } from '#/i18n/I18nProvider'
import { cn } from '#/lib/cn'
import type { MessageKey } from '#/i18n/messages'
import type { GenerationRunStatus } from '#/lib/api-types'
import type { LucideIcon } from 'lucide-react'

const config: Record<
  GenerationRunStatus,
  { label: MessageKey; className: string; Icon: LucideIcon; spin?: boolean }
> = {
  Pending: {
    label: 'statusPending',
    className: 'bg-surface-sunken text-ink-muted',
    Icon: Clock,
  },
  Running: {
    label: 'statusRunning',
    className: 'bg-accent-soft text-accent',
    Icon: Loader2,
    spin: true,
  },
  Completed: {
    label: 'statusCompleted',
    className: 'bg-success-soft text-success',
    Icon: CheckCircle2,
  },
  Failed: {
    label: 'statusFailed',
    className: 'bg-danger-soft text-danger',
    Icon: AlertCircle,
  },
}

export function StatusChip({ status }: { status: GenerationRunStatus }) {
  const { t } = useI18n()
  const { label, className, Icon, spin } = config[status]

  return (
    <span
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold',
        className,
      )}
    >
      <Icon
        className={cn('size-3.5', spin && 'animate-spin')}
        strokeWidth={2}
        aria-hidden
      />
      {t(label)}
    </span>
  )
}

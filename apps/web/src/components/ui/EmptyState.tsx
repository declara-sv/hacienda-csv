import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

type EmptyStateProps = {
  icon: LucideIcon
  title: string
  body?: string
  action?: ReactNode
}

export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: EmptyStateProps) {
  return (
    <div className="rise flex flex-col items-start gap-3 rounded-container border border-dashed border-line-strong px-6 py-10 sm:items-center sm:text-center">
      <span className="inline-flex size-11 items-center justify-center rounded-container bg-accent-soft text-accent">
        <Icon className="size-5" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="space-y-1">
        <p className="text-base font-semibold text-ink">{title}</p>
        {body ? (
          <p className="max-w-[48ch] text-sm text-ink-muted">{body}</p>
        ) : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  )
}

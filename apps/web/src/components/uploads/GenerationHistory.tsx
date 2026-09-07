import { Download, FileSpreadsheet } from 'lucide-react'
import type {
  Artifact,
  GenerationRun,
  GenerationRunFileStatus,
} from '#/lib/api-types'
import type { MessageKey } from '#/i18n/messages'
import { Button } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import { Notice } from '#/components/ui/Notice'
import { RowListSkeleton } from '#/components/ui/Skeleton'
import { StatusChip } from '#/components/ui/StatusChip'
import { useI18n } from '#/i18n/I18nProvider'
import { formatDateTime } from '#/lib/format'
import { cn } from '#/lib/cn'

export type GenerationHistoryProps = {
  runs: GenerationRun[]
  isLoading?: boolean
  error?: string | null
  downloadingArtifactIds?: ReadonlySet<string>
  onDownload: (artifact: Artifact) => void
  onRetry?: () => void
}

const fileStatusLabels: Record<GenerationRunFileStatus, MessageKey> = {
  Pending: 'statusPending',
  Included: 'generationFileIncluded',
  Failed: 'statusFailed',
}

export function GenerationHistory({
  runs,
  isLoading = false,
  error,
  downloadingArtifactIds,
  onDownload,
  onRetry,
}: GenerationHistoryProps) {
  const { t } = useI18n()
  const sortedRuns = [...runs].sort((a, b) => b.version - a.version)
  const latestCompletedId = sortedRuns.find(
    (run) => run.status === 'Completed',
  )?.id

  return (
    <div className="space-y-4">
      {error ? (
        <div className="space-y-2">
          <Notice variant="error">{error}</Notice>
          {onRetry ? (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              {t('errorRetry')}
            </Button>
          ) : null}
        </div>
      ) : null}
      {isLoading && runs.length === 0 ? (
        <div role="status">
          <span className="sr-only">{t('loading')}</span>
          <RowListSkeleton />
        </div>
      ) : null}
      {!isLoading && !error && runs.length === 0 ? (
        <EmptyState
          icon={FileSpreadsheet}
          title={t('generationsEmpty')}
          body={t('generationsEmptyBody')}
        />
      ) : null}
      {sortedRuns.map((run) => {
        const latestCompleted = run.id === latestCompletedId
        const failedFiles = run.files.filter(
          (file) => file.status === 'Failed',
        ).length
        return (
          <article
            key={run.id}
            className={cn(
              'space-y-4 rounded-container border bg-surface-raised p-4 sm:p-5',
              latestCompleted ? 'border-accent' : 'border-line',
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="text-base font-semibold text-ink">
                  {t('generationVersion', { version: run.version })}
                </h3>
                {latestCompleted ? (
                  <span className="rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent">
                    {t('generationLatestCompleted')}
                  </span>
                ) : null}
              </div>
              <StatusChip status={run.status} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
              <p>
                {t('generationCreated', {
                  date: formatDateTime(run.createdAtUtc),
                })}
              </p>
              {run.startedAtUtc ? (
                <p>
                  {t('generationStarted', {
                    date: formatDateTime(run.startedAtUtc),
                  })}
                </p>
              ) : null}
              {run.completedAtUtc ? (
                <p>
                  {t('generationCompleted', {
                    date: formatDateTime(run.completedAtUtc),
                  })}
                </p>
              ) : null}
            </div>
            {run.errorMessage ? (
              <Notice variant="error">{run.errorMessage}</Notice>
            ) : null}
            {run.status === 'Completed' && failedFiles > 0 ? (
              <Notice variant="error">
                {t('generationPartialFailure', { count: failedFiles })}
              </Notice>
            ) : null}
            <details className="border-t border-line pt-3">
              <summary className="cursor-pointer text-sm font-semibold text-ink">
                {t('generationFiles', { count: run.files.length })}
              </summary>
              <ul className="mt-3 divide-y divide-line">
                {run.files.map((file, index) => (
                  <li key={`${run.id}-${index}`} className="py-2 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="min-w-0 break-all text-ink">
                        {file.originalFileName}
                      </span>
                      <span
                        className={cn(
                          'text-xs font-semibold',
                          file.status === 'Failed'
                            ? 'text-danger'
                            : 'text-ink-muted',
                        )}
                      >
                        {t(fileStatusLabels[file.status])}
                      </span>
                    </div>
                    {file.errorMessage ? (
                      <p className="mt-1 break-words text-danger">
                        {file.errorMessage}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
            {run.artifacts.length > 0 ? (
              <ul className="space-y-2 border-t border-line pt-3">
                {run.artifacts.map((artifact) => (
                  <li
                    key={artifact.id}
                    className="flex flex-wrap items-center justify-between gap-3"
                  >
                    <span className="min-w-0 break-all text-sm text-ink-muted">
                      {artifact.fileName}
                    </span>
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<Download className="size-4" />}
                      loading={downloadingArtifactIds?.has(artifact.id)}
                      loadingLabel={t('downloading')}
                      aria-label={`${t('downloadCsv')}: ${artifact.fileName}`}
                      onClick={() => onDownload(artifact)}
                    >
                      {t('downloadCsv')}
                    </Button>
                  </li>
                ))}
              </ul>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}

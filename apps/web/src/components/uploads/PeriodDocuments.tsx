import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FileSpreadsheet,
  FileText,
  Inbox,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { GenerationHistory } from './GenerationHistory'
import { MultiFileUpload } from './MultiFileUpload'
import { Button } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import { Notice } from '#/components/ui/Notice'
import { Section } from '#/components/ui/PageHeader'
import { RowListSkeleton } from '#/components/ui/Skeleton'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, runsApi, uploadsApi } from '#/lib/api-client'
import { formatBytes, formatDateTime } from '#/lib/format'
import type { UploadQueueState } from './MultiFileUpload'
import type { MessageKey } from '#/i18n/messages'
import type { Artifact, GenerationRun } from '#/lib/api-types'
import type { CSSProperties } from 'react'

type Props = { clientId: string; periodId: string }

const isActive = (run: GenerationRun) =>
  run.status === 'Pending' || run.status === 'Running'

const messageOf = (error: unknown, fallback: string) =>
  error instanceof ApiError ? error.message : fallback

/**
 * Documents and generation runs of one filing period. Mount with a period key:
 * the local upload queue and mutation notices must not survive navigation.
 */
export function PeriodDocuments({ clientId, periodId }: Props) {
  const { t } = useI18n()
  const queryClient = useQueryClient()

  const uploadsKey = useMemo(
    () => ['uploads', clientId, periodId],
    [clientId, periodId],
  )
  const runsKey = useMemo(
    () => ['runs', clientId, periodId],
    [clientId, periodId],
  )

  const [queue, setQueue] = useState<UploadQueueState>({
    pendingCount: 0,
    busy: false,
  })
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(
    null,
  )
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [downloadingArtifactIds, setDownloadingArtifactIds] = useState<
    ReadonlySet<string>
  >(new Set())

  const uploadsQuery = useQuery({
    queryKey: uploadsKey,
    queryFn: () => uploadsApi.list(clientId, periodId),
    refetchOnWindowFocus: true,
  })
  const runsQuery = useQuery({
    queryKey: runsKey,
    queryFn: () => runsApi.list(clientId, periodId),
    refetchOnWindowFocus: true,
    refetchInterval: (query) =>
      query.state.data?.some(isActive) ? 5000 : false,
  })

  const uploads = useMemo(() => uploadsQuery.data ?? [], [uploadsQuery.data])
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data])

  const activeRun = runs.find(isActive) ?? null
  // Snapshots of deleted documents keep a null uploadId; they block nothing.
  const idsInActiveRuns = useMemo(() => {
    const ids = new Set<string>()
    for (const run of runs) {
      if (!isActive(run)) continue
      for (const file of run.files) if (file.uploadId) ids.add(file.uploadId)
    }
    return ids
  }, [runs])

  const latestCompletedRunId = useMemo(() => {
    let latest: GenerationRun | null = null
    for (const run of runs) {
      if (run.status !== 'Completed') continue
      if (!latest || run.version > latest.version) latest = run
    }
    return latest?.id ?? null
  }, [runs])

  // The API recomputes includedInLatestRun, so re-read documents whenever a new
  // run finishes. Keyed on the run id, never on every render.
  const knownCompletedRunId = useRef<string | null>(null)
  const knownCompletedRunSeeded = useRef(false)
  useEffect(() => {
    if (!runsQuery.isSuccess) return
    if (!knownCompletedRunSeeded.current) {
      knownCompletedRunSeeded.current = true
      knownCompletedRunId.current = latestCompletedRunId
      return
    }
    if (!latestCompletedRunId) return
    if (latestCompletedRunId === knownCompletedRunId.current) return
    knownCompletedRunId.current = latestCompletedRunId
    void queryClient.invalidateQueries({ queryKey: uploadsKey })
  }, [runsQuery.isSuccess, latestCompletedRunId, queryClient, uploadsKey])

  const refetchAll = () => {
    void queryClient.invalidateQueries({ queryKey: uploadsKey })
    void queryClient.invalidateQueries({ queryKey: runsKey })
  }

  const onMutationError = (error: unknown, fallback: MessageKey) => {
    setMutationError(messageOf(error, t(fallback)))
    // Another session changed the period; both snapshots are stale.
    if (error instanceof ApiError && error.status === 409) refetchAll()
  }

  const createRunMutation = useMutation({
    mutationFn: () => runsApi.create(clientId, periodId),
    onMutate: () => setMutationError(null),
    onSuccess: (created) => {
      // Seed before invalidating so the guards hold while runs refetch.
      queryClient.setQueryData<GenerationRun[]>(runsKey, (current) => [
        created,
        ...(current ?? []).filter((run) => run.id !== created.id),
      ])
      void queryClient.invalidateQueries({ queryKey: runsKey })
    },
    onError: (error) => onMutationError(error, 'generateError'),
  })

  const deleteUploadMutation = useMutation({
    mutationFn: (uploadId: string) =>
      uploadsApi.remove(clientId, periodId, uploadId),
    onMutate: () => setMutationError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: uploadsKey })
    },
    onError: (error) => onMutationError(error, 'documentDeleteError'),
    onSettled: () => setConfirmingDeleteId(null),
  })

  const downloadMutation = useMutation({
    mutationFn: (artifact: Artifact) =>
      uploadsApi.downloadArtifact(artifact.id, artifact.fileName),
    onMutate: (artifact) => {
      setDownloadError(null)
      setDownloadingArtifactIds((current) => new Set(current).add(artifact.id))
    },
    onError: (error) => setDownloadError(messageOf(error, t('downloadError'))),
    onSettled: (_data, _error, artifact) =>
      setDownloadingArtifactIds((current) => {
        const next = new Set(current)
        next.delete(artifact.id)
        return next
      }),
  })

  const creatingRun = createRunMutation.isPending
  const filesMutating = deleteUploadMutation.isPending || queue.busy

  const generateBlockedReason: MessageKey | null =
    uploadsQuery.isError || runsQuery.isError
      ? 'generateBlockedUnavailable'
      : !uploadsQuery.isSuccess || !runsQuery.isSuccess
        ? 'generateBlockedLoading'
        : activeRun
          ? 'generateBlockedActiveRun'
          : filesMutating
            ? 'generateBlockedMutations'
            : queue.pendingCount > 0
              ? 'generateBlockedQueue'
              : uploads.length === 0
                ? 'generateBlockedNoDocuments'
                : null

  return (
    <div className="space-y-8">
      {mutationError ? (
        <Notice variant="error" onDismiss={() => setMutationError(null)}>
          {mutationError}
        </Notice>
      ) : null}

      <Section
        title={t('uploadDocumentsTitle')}
        description={t('uploadDocumentsIntro')}
      >
        <MultiFileUpload
          clientId={clientId}
          periodId={periodId}
          disabled={creatingRun}
          onUploaded={() =>
            queryClient.invalidateQueries({ queryKey: uploadsKey })
          }
          onQueueStateChange={setQueue}
        />
      </Section>

      <Section
        title={t('documentsTitle')}
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw className="size-4" strokeWidth={2} />}
            onClick={refetchAll}
          >
            {t('refresh')}
          </Button>
        }
      >
        {uploadsQuery.isLoading ? (
          <div role="status">
            <span className="sr-only">{t('documentsLoading')}</span>
            <RowListSkeleton />
          </div>
        ) : null}

        {uploadsQuery.isError ? (
          <div className="space-y-2">
            <Notice variant="error">
              {messageOf(uploadsQuery.error, t('documentsError'))}
            </Notice>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void uploadsQuery.refetch()}
            >
              {t('errorRetry')}
            </Button>
          </div>
        ) : null}

        {uploadsQuery.isSuccess && uploads.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title={t('uploadsEmpty')}
            body={t('uploadsEmptyBody')}
          />
        ) : null}

        {uploads.length > 0 ? (
          <ul
            className="divide-y divide-line"
            aria-label={t('uploadsListLabel')}
          >
            {uploads.map((upload, index) => {
              const lockedByActiveRun = idsInActiveRuns.has(upload.id)
              const deleting =
                deleteUploadMutation.isPending &&
                deleteUploadMutation.variables === upload.id
              // One guard for the trigger and the confirmation: an open
              // confirmation must lock the moment a run claims the document,
              // whether the run is ours or arrived from another session.
              const deleteBlocked =
                creatingRun ||
                deleteUploadMutation.isPending ||
                lockedByActiveRun
              return (
                <li
                  key={upload.id}
                  className="rise flex flex-wrap items-start gap-4 py-5 first:pt-0"
                  style={{ '--i': index } as CSSProperties}
                >
                  <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-control bg-accent-soft text-accent">
                    {upload.sourceFileKind === 'PDF' ? (
                      <FileText
                        className="size-5"
                        strokeWidth={1.75}
                        aria-hidden
                      />
                    ) : (
                      <FileSpreadsheet
                        className="size-5"
                        strokeWidth={1.75}
                        aria-hidden
                      />
                    )}
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-ink">
                      {upload.originalFileName}
                    </p>
                    <p className="text-sm text-ink-muted">
                      {upload.sourceFileKind}, {formatBytes(upload.sizeBytes)} ·{' '}
                      {formatDateTime(upload.createdAtUtc)}
                    </p>
                    <p className="mt-1 text-sm text-ink-muted">
                      {upload.includedInLatestRun
                        ? t('documentIncluded')
                        : t('documentNotIncluded')}
                    </p>
                    {lockedByActiveRun ? (
                      <p className="mt-1 text-xs text-ink-muted">
                        {t('documentDeleteBlocked')}
                      </p>
                    ) : null}
                  </div>

                  {confirmingDeleteId === upload.id ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm text-ink">
                        {t('documentDeleteQuestion')}
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={deleting}
                        disabled={deleteBlocked}
                        onClick={() => deleteUploadMutation.mutate(upload.id)}
                      >
                        {t('documentDeleteConfirm')}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={deleting}
                        onClick={() => setConfirmingDeleteId(null)}
                      >
                        {t('cancel')}
                      </Button>
                    </div>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Trash2 className="size-4" strokeWidth={2} />}
                      disabled={deleteBlocked}
                      aria-label={t('documentDelete', {
                        name: upload.originalFileName,
                      })}
                      onClick={() => setConfirmingDeleteId(upload.id)}
                    >
                      {t('delete')}
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        ) : null}
      </Section>

      <Section
        title={t('generationsTitle')}
        description={t('generationsIntro')}
        actions={
          <Button
            icon={<Sparkles className="size-4" strokeWidth={2} />}
            loading={creatingRun}
            loadingLabel={t('generating')}
            disabled={generateBlockedReason !== null}
            aria-describedby={
              generateBlockedReason ? 'generate-blocked' : undefined
            }
            onClick={() => createRunMutation.mutate()}
          >
            {t('generateCsv')}
          </Button>
        }
      >
        <div className="space-y-4">
          {generateBlockedReason ? (
            <p id="generate-blocked" className="text-sm text-ink-muted">
              {t(generateBlockedReason)}
            </p>
          ) : null}

          {downloadError ? (
            <Notice variant="error" onDismiss={() => setDownloadError(null)}>
              {downloadError}
            </Notice>
          ) : null}

          <GenerationHistory
            runs={runs}
            isLoading={runsQuery.isLoading}
            error={
              runsQuery.isError
                ? messageOf(runsQuery.error, t('generationsError'))
                : null
            }
            downloadingArtifactIds={downloadingArtifactIds}
            onDownload={(artifact) => downloadMutation.mutate(artifact)}
            onRetry={() => void runsQuery.refetch()}
          />
        </div>
      </Section>
    </div>
  )
}

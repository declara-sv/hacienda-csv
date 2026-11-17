import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  Inbox,
  Loader2,
  RefreshCw,
  RotateCw,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { GenerationHistory } from './GenerationHistory'
import { fileInputId, MultiFileUpload } from './MultiFileUpload'
import {
  PeriodReview,
  documentsQueryKey,
} from '#/components/review/PeriodReview'
import { Button } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import { Notice } from '#/components/ui/Notice'
import { Section } from '#/components/ui/PageHeader'
import { RowListSkeleton } from '#/components/ui/Skeleton'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, documentsApi, runsApi, uploadsApi } from '#/lib/api-client'
import { summarizeDocuments } from '#/lib/dte'
import { cn } from '#/lib/cn'
import { formatBytes, formatDateTime } from '#/lib/format'
import type { UploadQueueState } from './MultiFileUpload'
import type { MessageKey } from '#/i18n/messages'
import type { ClientRentaDefaults } from '#/components/review/DocumentEditDialog'
import type { Artifact, GenerationRun, Upload } from '#/lib/api-types'
import type { CSSProperties } from 'react'

type Props = {
  clientId: string
  periodId: string
  /** The client's Renta defaults, shown as the fallback in the review. */
  clientDefaults?: ClientRentaDefaults | null
}

const isActive = (run: GenerationRun) =>
  run.status === 'Pending' || run.status === 'Running'

const isExtracting = (upload: Upload) =>
  upload.extractionStatus === 'Pending' || upload.extractionStatus === 'Running'

const EXTRACTION_POLL_MS = 3000
/** Above this many read files, they fold behind a toggle. */
const READ_FILES_FOLD_AT = 5
const reviewSectionId = 'revision'

type BlockedReason = { key: MessageKey; vars?: Record<string, number> }

const messageOf = (error: unknown, fallback: string) =>
  error instanceof ApiError ? error.message : fallback

const deleteTriggerId = (uploadId: string) => `delete-${uploadId}`
const confirmDeleteId = (uploadId: string) => `confirm-delete-${uploadId}`
const focusById = (id: string) => {
  const target = document.getElementById(id)
  target?.focus({ preventScroll: true })
  return target !== null && document.activeElement === target
}

/**
 * Documents and generation runs of one filing period. Mount with a period key:
 * the local upload queue and mutation notices must not survive navigation.
 */
export function PeriodDocuments({
  clientId,
  periodId,
  clientDefaults = null,
}: Props) {
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
  const documentsKey = useMemo(
    () => documentsQueryKey(clientId, periodId),
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
    // Poll while the API is still reading files.
    refetchInterval: (query) =>
      query.state.data?.some(isExtracting) ? EXTRACTION_POLL_MS : false,
  })
  const extracting = uploadsQuery.data?.some(isExtracting) ?? false
  const documentsQuery = useQuery({
    queryKey: documentsKey,
    queryFn: () => documentsApi.list(clientId, periodId),
    refetchOnWindowFocus: true,
    refetchInterval: extracting ? EXTRACTION_POLL_MS : false,
  })
  const documentsMutating = useIsMutating({ mutationKey: documentsKey }) > 0
  const runsQuery = useQuery({
    queryKey: runsKey,
    queryFn: () => runsApi.list(clientId, periodId),
    refetchOnWindowFocus: true,
    refetchInterval: (query) =>
      query.state.data?.some(isActive) ? 5000 : false,
  })

  const uploads = useMemo(() => uploadsQuery.data ?? [], [uploadsQuery.data])
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data])
  const documents = useMemo(
    () => documentsQuery.data ?? [],
    [documentsQuery.data],
  )
  const summary = useMemo(() => summarizeDocuments(documents), [documents])

  // The last poll may land after the documents were read: re-read them once
  // extraction finishes.
  const wasExtracting = useRef(false)
  useEffect(() => {
    if (wasExtracting.current && !extracting)
      void queryClient.invalidateQueries({ queryKey: documentsKey })
    wasExtracting.current = extracting
  }, [extracting, queryClient, documentsKey])

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

  // The delete trigger unmounts when its inline confirmation opens (and the
  // confirmation unmounts when it closes), so focus can only be moved once the
  // replacement exists. Without this, the browser drops focus on <body> and
  // keyboard users lose their place in the document list.
  const restoreFocusUploadId = useRef<string | null>(null)
  useEffect(() => {
    if (confirmingDeleteId) {
      focusById(confirmDeleteId(confirmingDeleteId))
      return
    }
    const uploadId = restoreFocusUploadId.current
    restoreFocusUploadId.current = null
    if (uploadId) focusById(deleteTriggerId(uploadId))
  }, [confirmingDeleteId])

  // A deleted row only unmounts once the refetched list arrives, so focus has
  // to wait for that commit too. Candidates are tried in order: the neighbour
  // row that took its place, then the file picker when nothing is left.
  const focusAfterDelete = useRef<readonly string[] | null>(null)
  useEffect(() => {
    const candidates = focusAfterDelete.current
    if (!candidates) return
    focusAfterDelete.current = null
    for (const id of candidates) if (focusById(id)) return
  }, [uploads])

  const refetchAll = () => {
    void queryClient.invalidateQueries({ queryKey: uploadsKey })
    void queryClient.invalidateQueries({ queryKey: runsKey })
    void queryClient.invalidateQueries({ queryKey: documentsKey })
  }
  const refetchFiles = () => {
    void queryClient.invalidateQueries({ queryKey: uploadsKey })
    void queryClient.invalidateQueries({ queryKey: documentsKey })
  }

  const onMutationError = (
    error: unknown,
    fallback: MessageKey,
    refetchOn: readonly number[] = [409],
  ) => {
    setMutationError(messageOf(error, t(fallback)))
    // The server rejected our view of the period; both snapshots are stale.
    if (error instanceof ApiError && refetchOn.includes(error.status))
      refetchAll()
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
    // A rejected generation (400) is as stale a view as a conflict (409):
    // the documents or the run history moved under us.
    onError: (error) => onMutationError(error, 'generateError', [400, 409]),
  })

  const deleteUploadMutation = useMutation({
    mutationFn: (uploadId: string) =>
      uploadsApi.remove(clientId, periodId, uploadId),
    onMutate: () => setMutationError(null),
    onSuccess: (_data, uploadId) => {
      // The row that takes the deleted one's place, or the last one left.
      const index = uploads.findIndex((item) => item.id === uploadId)
      const survivors = uploads.filter((item) => item.id !== uploadId)
      const neighbour = survivors.at(Math.min(index, survivors.length - 1))
      focusAfterDelete.current = [
        ...(neighbour ? [deleteTriggerId(neighbour.id)] : []),
        fileInputId,
      ]
      refetchFiles()
    },
    onError: (error) => onMutationError(error, 'documentDeleteError'),
    onSettled: (_data, error, uploadId) => {
      // A failed delete leaves the row in place; keep the keyboard there.
      if (error) restoreFocusUploadId.current = uploadId
      setConfirmingDeleteId(null)
    },
  })

  const reextractMutation = useMutation({
    mutationFn: (uploadId: string) =>
      uploadsApi.reextract(clientId, periodId, uploadId),
    onMutate: () => setMutationError(null),
    onSuccess: refetchFiles,
    onError: (error) => onMutationError(error, 'reextractError'),
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
  const filesMutating =
    deleteUploadMutation.isPending ||
    reextractMutation.isPending ||
    documentsMutating ||
    queue.busy

  const generateBlockedReason: BlockedReason | null =
    uploadsQuery.isError || runsQuery.isError || documentsQuery.isError
      ? { key: 'generateBlockedUnavailable' }
      : !uploadsQuery.isSuccess ||
          !runsQuery.isSuccess ||
          !documentsQuery.isSuccess
        ? { key: 'generateBlockedLoading' }
        : activeRun
          ? { key: 'generateBlockedActiveRun' }
          : filesMutating
            ? { key: 'generateBlockedMutations' }
            : queue.pendingCount > 0
              ? { key: 'generateBlockedQueue' }
              : uploads.length === 0
                ? { key: 'generateBlockedNoDocuments' }
                : extracting
                  ? { key: 'generateBlockedExtracting' }
                  : summary.included === 0
                    ? { key: 'generateBlockedNoIncluded' }
                    : summary.blockingErrors > 0
                      ? {
                          key: 'generateBlockedErrors',
                          vars: { count: summary.blockingErrors },
                        }
                      : null

  const failedUploads = uploads.filter(
    (upload) => upload.extractionStatus === 'Failed',
  ).length
  const extractingUploads = uploads.filter(isExtracting).length
  const latestCompletedRun =
    runs.find((run) => run.id === latestCompletedRunId) ?? null

  // Files that need attention stay in view; read ones fold away in long months.
  const [showRead, setShowRead] = useState(false)
  const readUploads = uploads.filter(
    (upload) => upload.extractionStatus === 'Completed',
  )
  const foldRead = readUploads.length > READ_FILES_FOLD_AT && !showRead
  const listedUploads = foldRead
    ? uploads.filter((upload) => upload.extractionStatus !== 'Completed')
    : uploads

  const [showErrorsSignal, setShowErrorsSignal] = useState(0)
  const showErrors = () => {
    setShowErrorsSignal((value) => value + 1)
    const target = document.getElementById(reviewSectionId)
    // jsdom has no scrollIntoView.
    if (target && 'scrollIntoView' in target)
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const readyMessage =
    summary.included === 1
      ? t('generateReadyOne')
      : t('generateReady', { count: summary.included })
  const blockedMessage = generateBlockedReason
    ? generateBlockedReason.key === 'generateBlockedErrors' &&
      summary.blockingErrors === 1
      ? t('generateBlockedErrorsOne')
      : t(generateBlockedReason.key, generateBlockedReason.vars)
    : null

  return (
    <div className="space-y-6">
      {mutationError ? (
        <Notice variant="error" onDismiss={() => setMutationError(null)}>
          {mutationError}
        </Notice>
      ) : null}

      <dl
        className="grid gap-3 sm:grid-cols-3"
        aria-label={t('periodStatusLabel')}
      >
        <StatusTile
          label={t('periodStepFiles')}
          value={
            uploads.length === 0
              ? t('periodFilesNone')
              : uploads.length === 1
                ? t('periodFilesCountOne')
                : t('periodFilesCount', { count: uploads.length })
          }
          detail={
            failedUploads > 0
              ? failedUploads === 1
                ? t('periodFilesFailedOne')
                : t('periodFilesFailed', { count: failedUploads })
              : extractingUploads > 0
                ? t('periodFilesReading', { count: extractingUploads })
                : uploads.length > 0
                  ? t('periodFilesAllRead')
                  : null
          }
          tone={failedUploads > 0 ? 'warning' : 'default'}
        />
        <StatusTile
          label={t('periodStepReview')}
          value={
            documents.length === 1
              ? t('periodReviewCountOne')
              : t('periodReviewCount', { count: documents.length })
          }
          detail={
            documents.length === 0
              ? null
              : summary.blockingErrors > 0
                ? summary.blockingErrors === 1
                  ? t('periodReviewErrorsOne')
                  : t('periodReviewErrors', { count: summary.blockingErrors })
                : summary.warnings > 0
                  ? t('periodReviewWarnings', { count: summary.warnings })
                  : t('periodReviewClean')
          }
          tone={summary.blockingErrors > 0 ? 'danger' : 'default'}
        />
        <StatusTile
          label={t('periodStepAnexos')}
          value={
            latestCompletedRun
              ? t('periodAnexosVersion', {
                  version: latestCompletedRun.version,
                })
              : t('periodAnexosNone')
          }
          detail={
            activeRun
              ? t('periodAnexosRunning', { version: activeRun.version })
              : latestCompletedRun?.completedAtUtc
                ? formatDateTime(latestCompletedRun.completedAtUtc)
                : null
          }
        />
      </dl>

      <section
        aria-label={t('periodGenerateLabel')}
        className={cn(
          'z-10 flex flex-col sm:sticky sm:top-16 gap-3 rounded-container border bg-surface-raised px-4 py-3 text-ink shadow-raised sm:flex-row sm:items-center sm:justify-between',
          generateBlockedReason ? 'border-line-strong' : 'border-accent',
        )}
      >
        <div className="min-w-0 text-sm" aria-live="polite">
          <p id="generate-blocked" className="font-semibold">
            {blockedMessage ?? readyMessage}
          </p>
          {failedUploads > 0 ? (
            <p className="text-warning">
              {failedUploads === 1
                ? t('generateFailedFilesOne')
                : t('generateFailedFiles', { count: failedUploads })}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {summary.blockingErrors > 0 ? (
            <button
              type="button"
              className="rounded-control px-1 text-sm font-semibold text-accent underline underline-offset-2"
              onClick={showErrors}
            >
              {t('generateShowErrors')}
            </button>
          ) : null}
          <Button
            icon={<Sparkles className="size-4" strokeWidth={2} />}
            loading={creatingRun}
            loadingLabel={t('generating')}
            disabled={generateBlockedReason !== null}
            aria-describedby="generate-blocked"
            onClick={() => {
              // Guard the same tick: the disabled state lands one render later.
              if (!createRunMutation.isPending) createRunMutation.mutate()
            }}
          >
            {t('generateCsv')}
          </Button>
        </div>
      </section>

      <section
        aria-labelledby="period-files-heading"
        className="space-y-3 rounded-container border border-line bg-surface-raised p-4"
      >
        <div className="flex items-center justify-between gap-3">
          <h2
            id="period-files-heading"
            className="text-lg font-semibold text-ink"
          >
            {t('documentsTitle')}
          </h2>
          <Button
            variant="ghost"
            size="sm"
            icon={<RefreshCw className="size-4" strokeWidth={2} />}
            onClick={refetchAll}
          >
            {t('refresh')}
          </Button>
        </div>

        <MultiFileUpload
          clientId={clientId}
          periodId={periodId}
          disabled={creatingRun}
          onUploaded={refetchFiles}
          onQueueStateChange={setQueue}
        />

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

        {listedUploads.length > 0 ? (
          <ul
            className="divide-y divide-line rounded-control border border-line"
            aria-label={t('uploadsListLabel')}
          >
            {listedUploads.map((upload, index) => {
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
                  className="rise flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-start sm:gap-4"
                  style={{ '--i': Math.min(index, 8) } as CSSProperties}
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <FileText
                      className="mt-0.5 size-4 shrink-0 text-ink-muted"
                      strokeWidth={1.75}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-ink">
                        {upload.originalFileName}
                        <span className="font-normal text-ink-muted">
                          {' · '}
                          {formatBytes(upload.sizeBytes)} ·{' '}
                          {formatDateTime(upload.createdAtUtc)}
                        </span>
                      </p>
                      <ExtractionStatusLine upload={upload} />
                      {latestCompletedRunId ? (
                        <p className="text-xs text-ink-muted">
                          {upload.includedInLatestRun
                            ? t('documentIncluded')
                            : t('documentNotIncluded')}
                        </p>
                      ) : null}
                      {lockedByActiveRun ? (
                        <p className="text-xs text-ink-muted">
                          {t('documentDeleteBlocked')}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1 pl-7 sm:pl-0">
                    {upload.extractionStatus === 'Failed' &&
                    confirmingDeleteId !== upload.id ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<RotateCw className="size-4" strokeWidth={2} />}
                        loading={
                          reextractMutation.isPending &&
                          reextractMutation.variables === upload.id
                        }
                        loadingLabel={t('reextracting')}
                        disabled={creatingRun || reextractMutation.isPending}
                        aria-label={t('reextractFile', {
                          name: upload.originalFileName,
                        })}
                        onClick={() => reextractMutation.mutate(upload.id)}
                      >
                        {t('reextract')}
                      </Button>
                    ) : null}

                    {confirmingDeleteId === upload.id ? (
                      <>
                        <span className="text-sm text-ink">
                          {t('documentDeleteQuestion')}
                        </span>
                        <Button
                          id={confirmDeleteId(upload.id)}
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
                          onClick={() => {
                            restoreFocusUploadId.current = upload.id
                            setConfirmingDeleteId(null)
                          }}
                        >
                          {t('cancel')}
                        </Button>
                      </>
                    ) : (
                      <Button
                        id={deleteTriggerId(upload.id)}
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
                  </div>
                </li>
              )
            })}
          </ul>
        ) : null}

        {readUploads.length > READ_FILES_FOLD_AT ? (
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={!foldRead}
            onClick={() => setShowRead((value) => !value)}
          >
            {!foldRead
              ? t('filesHideRead')
              : readUploads.length === 1
                ? t('filesShowReadOne')
                : t('filesShowRead', { count: readUploads.length })}
          </Button>
        ) : null}
      </section>

      <Section
        id={reviewSectionId}
        title={t('reviewTitle')}
        description={t('reviewIntro')}
      >
        <PeriodReview
          clientId={clientId}
          periodId={periodId}
          documents={documents}
          isLoading={documentsQuery.isLoading}
          error={
            documentsQuery.isError
              ? messageOf(documentsQuery.error, t('reviewError'))
              : null
          }
          onRetry={() => void documentsQuery.refetch()}
          clientDefaults={clientDefaults}
          disabled={creatingRun}
          showErrorsSignal={showErrorsSignal}
        />
      </Section>

      <Section
        title={t('generationsTitle')}
        description={t('generationsIntro')}
      >
        <div className="space-y-4">
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

function StatusTile({
  label,
  value,
  detail,
  tone = 'default',
}: {
  label: string
  value: string
  detail: string | null
  tone?: 'default' | 'warning' | 'danger'
}) {
  return (
    <div className="rounded-container border border-line bg-surface-raised px-4 py-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </dt>
      <dd className="mt-0.5 text-lg font-semibold text-ink tabular-nums">
        {value}
      </dd>
      {detail ? (
        <dd
          className={cn(
            'text-sm',
            tone === 'danger'
              ? 'font-semibold text-danger'
              : tone === 'warning'
                ? 'font-semibold text-warning'
                : 'text-ink-muted',
          )}
        >
          {detail}
        </dd>
      ) : null}
    </div>
  )
}

function ExtractionStatusLine({ upload }: { upload: Upload }) {
  const { t } = useI18n()
  switch (upload.extractionStatus) {
    case 'Pending':
      return (
        <p className="inline-flex items-center gap-1.5 text-sm text-ink-muted">
          <Clock className="size-4" strokeWidth={2} aria-hidden />
          {t('extractionPending')}
        </p>
      )
    case 'Running':
      return (
        <p className="inline-flex items-center gap-1.5 text-sm text-accent">
          <Loader2
            className="size-4 animate-spin"
            strokeWidth={2}
            aria-hidden
          />
          {t('extractionRunning')}
        </p>
      )
    case 'Completed':
      return (
        <p className="inline-flex items-center gap-1.5 text-sm text-success">
          <CheckCircle2 className="size-4" strokeWidth={2} aria-hidden />
          {upload.documentsCount === 1
            ? t('extractionCompletedOne')
            : t('extractionCompleted', { count: upload.documentsCount })}
        </p>
      )
    case 'Failed':
      return (
        <div className="text-sm text-danger">
          <p className="inline-flex items-center gap-1.5 font-semibold">
            <AlertCircle className="size-4" strokeWidth={2} aria-hidden />
            {t('extractionFailed')}
          </p>
          {upload.extractionError ? (
            <p className="break-words">{upload.extractionError}</p>
          ) : null}
        </div>
      )
  }
}

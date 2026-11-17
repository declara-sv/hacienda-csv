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
  FileSpreadsheet,
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
          onUploaded={refetchFiles}
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
                    <ExtractionStatusLine upload={upload} />
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
                    <div className="flex flex-wrap items-center gap-2">
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
                    </div>
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
                </li>
              )
            })}
          </ul>
        ) : null}
      </Section>

      <Section title={t('reviewTitle')} description={t('reviewIntro')}>
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
        />
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
            onClick={() => {
              // Guard the same tick: the disabled state lands one render later.
              if (!createRunMutation.isPending) createRunMutation.mutate()
            }}
          >
            {t('generateCsv')}
          </Button>
        }
      >
        <div className="space-y-4">
          {generateBlockedReason ? (
            <p id="generate-blocked" className="text-sm text-ink-muted">
              {t(generateBlockedReason.key, generateBlockedReason.vars)}
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

function ExtractionStatusLine({ upload }: { upload: Upload }) {
  const { t } = useI18n()
  switch (upload.extractionStatus) {
    case 'Pending':
      return (
        <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-ink-muted">
          <Clock className="size-4" strokeWidth={2} aria-hidden />
          {t('extractionPending')}
        </p>
      )
    case 'Running':
      return (
        <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-accent">
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
        <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-success">
          <CheckCircle2 className="size-4" strokeWidth={2} aria-hidden />
          {upload.documentsCount === 1
            ? t('extractionCompletedOne')
            : t('extractionCompleted', { count: upload.documentsCount })}
        </p>
      )
    case 'Failed':
      return (
        <div className="mt-1 text-sm text-danger">
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

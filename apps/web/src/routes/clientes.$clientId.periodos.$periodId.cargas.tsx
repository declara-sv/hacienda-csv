import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Download,
  FileSpreadsheet,
  FileText,
  Inbox,
  UploadCloud,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Breadcrumb } from '#/components/ui/Breadcrumb'
import { Button } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import { Field, Select } from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { PageHeader, Section } from '#/components/ui/PageHeader'
import { RowListSkeleton } from '#/components/ui/Skeleton'
import { StatusChip } from '#/components/ui/StatusChip'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, clientsApi, uploadsApi } from '#/lib/api-client'
import { cn } from '#/lib/cn'
import {
  detectSourceFileKind,
  formatBytes,
  formatDateTime,
  formatPeriod,
} from '#/lib/format'
import type { Artifact, Upload } from '#/lib/api-types'
import type { SourceFileKind } from '#/lib/format'
import type { CSSProperties } from 'react'

export const Route = createFileRoute(
  '/clientes/$clientId/periodos/$periodId/cargas',
)({
  head: () => ({ meta: [{ title: 'Carga de documentos | HaciendaCSV' }] }),
  component: UploadsPage,
})

const ACCEPT = '.xls,.xlsx,.pdf'

function hasActiveJobs(uploads: Upload[] | undefined) {
  return Boolean(
    uploads?.some((upload) =>
      upload.jobs.some(
        (job) => job.status === 'Pending' || job.status === 'Running',
      ),
    ),
  )
}

function UploadsPage() {
  const { clientId, periodId } = Route.useParams()
  const { t } = useI18n()
  const queryClient = useQueryClient()

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => clientsApi.get(clientId),
  })
  const client = clientQuery.data
  const period = client?.filingPeriods.find((p) => p.id === periodId)
  const periodLabel = period ? formatPeriod(period.year, period.month) : null

  const uploadsQuery = useQuery({
    queryKey: ['uploads', clientId, periodId],
    queryFn: () => uploadsApi.list(clientId, periodId),
    refetchInterval: (query) =>
      hasActiveJobs(query.state.data) ? 5000 : false,
  })

  const [success, setSuccess] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  useEffect(() => {
    if (!success) return
    const timer = window.setTimeout(() => setSuccess(null), 6000)
    return () => window.clearTimeout(timer)
  }, [success])

  const downloadMutation = useMutation({
    mutationFn: (artifact: Artifact) =>
      uploadsApi.downloadArtifact(artifact.id, artifact.fileName),
    onMutate: (artifact) => {
      setDownloadError(null)
      setDownloadingId(artifact.id)
    },
    onError: (err) => {
      setDownloadError(
        err instanceof ApiError ? err.message : t('downloadError'),
      )
    },
    onSettled: () => setDownloadingId(null),
  })

  const uploads = uploadsQuery.data ?? []

  return (
    <div className="space-y-8">
      <Breadcrumb
        items={[
          { label: t('menuClients'), to: '/clientes' },
          {
            label: client ? client.name : null,
            to: '/clientes/$clientId',
            params: { clientId },
          },
          { label: periodLabel },
        ]}
      />

      <PageHeader
        title={t('uploadsTitle')}
        meta={periodLabel ? <span>{periodLabel}</span> : undefined}
        description={t('uploadsIntro')}
      />

      <UploadForm
        onUploaded={() => {
          setSuccess(t('uploadSuccess'))
          queryClient.invalidateQueries({
            queryKey: ['uploads', clientId, periodId],
          })
        }}
        clientId={clientId}
        periodId={periodId}
      />

      {success ? (
        <Notice variant="success" onDismiss={() => setSuccess(null)}>
          {success}
        </Notice>
      ) : null}

      <Section title={t('uploadsHistory')}>
        {uploadsQuery.isLoading ? <RowListSkeleton /> : null}

        {uploadsQuery.isError ? (
          <Notice variant="error">
            {uploadsQuery.error instanceof ApiError
              ? uploadsQuery.error.message
              : t('uploadError')}
          </Notice>
        ) : null}

        {downloadError ? (
          <Notice
            variant="error"
            className="mb-4"
            onDismiss={() => setDownloadError(null)}
          >
            {downloadError}
          </Notice>
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
            {uploads.map((upload, index) => (
              <li
                key={upload.id}
                className="rise flex items-start gap-4 py-5 first:pt-0"
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

                  <ul className="mt-3 space-y-3">
                    {upload.jobs.map((job) => (
                      <li
                        key={job.id}
                        className="flex flex-wrap items-center gap-x-3 gap-y-2"
                      >
                        <StatusChip status={job.status} />
                        {job.errorMessage ? (
                          <p className="text-sm text-danger">
                            {job.errorMessage}
                          </p>
                        ) : null}
                        {job.artifacts.map((artifact) => (
                          <span
                            key={artifact.id}
                            className="inline-flex items-center gap-2"
                          >
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={
                                <Download className="size-4" strokeWidth={2} />
                              }
                              loading={downloadingId === artifact.id}
                              loadingLabel={t('downloading')}
                              onClick={() => downloadMutation.mutate(artifact)}
                              aria-label={`${t('downloadCsv')}: ${artifact.fileName}`}
                            >
                              {t('downloadCsv')}
                            </Button>
                            <span className="max-w-[24ch] truncate text-sm text-ink-muted">
                              {artifact.fileName}
                            </span>
                          </span>
                        ))}
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </Section>
    </div>
  )
}

function UploadForm({
  clientId,
  periodId,
  onUploaded,
}: {
  clientId: string
  periodId: string
  onUploaded: () => void
}) {
  const { t } = useI18n()
  const inputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [detected, setDetected] = useState<SourceFileKind | null>(null)
  const [kind, setKind] = useState<SourceFileKind>('Excel')
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pickFile = (next: File | null) => {
    setError(null)
    setFile(next)
    const found = next ? detectSourceFileKind(next.name) : null
    setDetected(found)
    setKind(found ?? 'Excel')
  }

  const reset = () => {
    pickFile(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error(t('uploadSelectFirst'))
      return uploadsApi.create(clientId, periodId, {
        file,
        sourceFileKind: kind,
      })
    },
    onSuccess: () => {
      reset()
      onUploaded()
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : t('uploadError'),
      )
    },
  })

  return (
    <form
      className="rise"
      style={{ '--i': 1 } as CSSProperties}
      onSubmit={(event) => {
        event.preventDefault()
        uploadMutation.mutate()
      }}
    >
      {!file ? (
        <label
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-container border-2 border-dashed px-6 py-12 text-center transition duration-200 ease-out-expo focus-within:ring-2 focus-within:ring-accent/30',
            dragging
              ? 'border-accent bg-accent-soft'
              : 'border-line-strong bg-surface-raised hover:border-accent hover:bg-accent-soft/40',
          )}
          onDragEnter={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            pickFile(event.dataTransfer.files.item(0))
          }}
        >
          <input
            ref={inputRef}
            type="file"
            name="file"
            accept={ACCEPT}
            className="sr-only"
            onChange={(event) => pickFile(event.target.files?.[0] ?? null)}
          />
          <UploadCloud
            className="size-8 text-accent"
            strokeWidth={1.5}
            aria-hidden
          />
          <span className="font-semibold text-ink">{t('dropzoneTitle')}</span>
          <span className="text-sm text-ink-muted">{t('dropzoneHint')}</span>
        </label>
      ) : (
        <div className="rise rounded-container border border-line bg-surface-raised p-4 shadow-raised sm:p-5">
          <div className="flex items-start gap-3">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-control bg-accent-soft text-accent">
              {kind === 'PDF' ? (
                <FileText className="size-5" strokeWidth={1.75} aria-hidden />
              ) : (
                <FileSpreadsheet
                  className="size-5"
                  strokeWidth={1.75}
                  aria-hidden
                />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold text-ink">{file.name}</p>
              <p className="text-sm text-ink-muted">{formatBytes(file.size)}</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={reset}
              icon={<X className="size-4" strokeWidth={2} />}
            >
              {t('remove')}
            </Button>
          </div>

          {detected ? (
            <div className="mt-5 grid gap-4 sm:grid-cols-[minmax(0,220px)_auto] sm:items-end">
              <Field
                id="sourceFileKind"
                label={t('fileKind')}
                hint={t('fileKindDetected')}
              >
                <Select
                  id="sourceFileKind"
                  name="sourceFileKind"
                  value={kind}
                  aria-describedby="sourceFileKind-hint"
                  onChange={(event) =>
                    setKind(event.target.value as SourceFileKind)
                  }
                >
                  <option value="Excel">Excel</option>
                  <option value="PDF">PDF</option>
                </Select>
              </Field>
              <Button
                type="submit"
                icon={<UploadCloud className="size-4" strokeWidth={2} />}
                loading={uploadMutation.isPending}
                loadingLabel={t('uploading')}
                className="sm:mt-7 sm:justify-self-start"
              >
                {t('upload')}
              </Button>
            </div>
          ) : (
            <Notice variant="error" className="mt-4">
              {t('fileUnsupported')}
            </Notice>
          )}

          {error ? (
            <Notice
              variant="error"
              className="mt-4"
              onDismiss={() => setError(null)}
            >
              {error}
            </Notice>
          ) : null}
        </div>
      )}
    </form>
  )
}

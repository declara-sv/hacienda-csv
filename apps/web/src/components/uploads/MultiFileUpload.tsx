import { Loader2, UploadCloud } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '#/components/ui/Button'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, uploadsApi } from '#/lib/api-client'
import { detectSourceFileKind, formatBytes } from '#/lib/format'
import type { SourceFileKind } from '#/lib/format'

/** pendingCount: files still waiting to reach the server (queued or uploading). */
export type UploadQueueState = { pendingCount: number; busy: boolean }
/** Focus target of last resort when the document list becomes empty. */
export const fileInputId = 'period-file-input'
type Props = {
  clientId: string
  periodId: string
  disabled?: boolean
  onUploaded: () => void | Promise<void>
  onQueueStateChange: (state: UploadQueueState) => void
}
type Entry = {
  id: number
  file: File
  kind: SourceFileKind | null
  state: 'queued' | 'uploading' | 'failed' | 'invalid'
  error?: string
}

const isPending = (entry: Entry) =>
  entry.state === 'queued' || entry.state === 'uploading'

/**
 * Drop or pick PDFs and they upload right away, one at a time. Files the API
 * would reject (not a PDF, empty) and failed uploads stay listed with their
 * reason; they never block the rest of the period.
 *
 * Mount with a period key: pending File objects must never cross periods.
 */
export function MultiFileUpload({
  clientId,
  periodId,
  disabled = false,
  onUploaded,
  onQueueStateChange,
}: Props) {
  const { t } = useI18n()
  const [queue, setQueueState] = useState<Entry[]>([])
  const queueRef = useRef<Entry[]>([])
  const [busy, setBusy] = useState(false)
  const [refreshError, setRefreshError] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const nextId = useRef(0)
  const inFlight = useRef(false)
  const mounted = useRef(false)
  const callbacks = useRef({ onUploaded, onQueueStateChange })
  useEffect(() => {
    callbacks.current = { onUploaded, onQueueStateChange }
  })
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const pendingCount = queue.filter(isPending).length
  useEffect(() => {
    callbacks.current.onQueueStateChange({ pendingCount, busy })
  }, [pendingCount, busy])

  const isMounted = () => mounted.current
  const updateQueue = (change: (current: Entry[]) => Entry[]) => {
    queueRef.current = change(queueRef.current)
    setQueueState(queueRef.current)
  }
  const patch = (id: number, values: Partial<Entry>) =>
    updateQueue((current) =>
      current.map((item) => (item.id === id ? { ...item, ...values } : item)),
    )

  async function pump() {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setRefreshError(false)
    try {
      for (;;) {
        if (!isMounted()) break
        const entry = queueRef.current.find((item) => item.state === 'queued')
        if (!entry?.kind) break
        patch(entry.id, { state: 'uploading', error: undefined })
        try {
          await uploadsApi.create(clientId, periodId, {
            file: entry.file,
            sourceFileKind: entry.kind,
          })
        } catch (error) {
          if (!isMounted()) break
          patch(entry.id, {
            state: 'failed',
            error: error instanceof ApiError ? error.message : t('uploadError'),
          })
          continue
        }
        if (!isMounted()) break
        // A saved file is never requeued, even when refreshing server data fails.
        updateQueue((current) => current.filter((item) => item.id !== entry.id))
        try {
          await callbacks.current.onUploaded()
        } catch {
          if (isMounted()) setRefreshError(true)
        }
      }
    } finally {
      inFlight.current = false
      if (isMounted()) setBusy(false)
    }
  }

  function append(files: FileList | File[]) {
    if (disabled) return
    const entries = Array.from(files).map((file): Entry => {
      const kind = detectSourceFileKind(file.name)
      const error = !kind
        ? t('fileUnsupported')
        : file.size === 0
          ? t('fileEmpty')
          : undefined
      return {
        id: nextId.current++,
        file,
        kind,
        state: error ? 'invalid' : 'queued',
        error,
      }
    })
    if (entries.length === 0) return
    updateQueue((current) => [...current, ...entries])
    void pump()
  }

  function retry(entry: Entry) {
    if (disabled) return
    patch(entry.id, { state: 'queued', error: undefined })
    void pump()
  }

  return (
    <div className="space-y-3">
      <input
        id={fileInputId}
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,application/pdf"
        className="sr-only"
        aria-label={t('selectFiles')}
        disabled={disabled}
        onChange={(event) => {
          if (event.currentTarget.files) append(event.currentTarget.files)
          event.currentTarget.value = ''
        }}
      />
      <button
        type="button"
        disabled={disabled}
        className="flex w-full flex-col items-center gap-1 rounded-control border-2 border-dashed border-line-strong bg-surface-raised px-4 py-4 text-center transition hover:border-accent hover:bg-accent-soft/40 disabled:opacity-60 sm:flex-row sm:justify-center sm:gap-3"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          append(event.dataTransfer.files)
        }}
      >
        {busy ? (
          <Loader2 className="size-5 animate-spin text-accent" aria-hidden />
        ) : (
          <UploadCloud className="size-5 text-accent" aria-hidden />
        )}
        <span className="font-semibold text-ink">{t('dropzoneTitle')}</span>
        <span className="text-sm text-ink-muted">{t('dropzoneHint')}</span>
      </button>
      {queue.length > 0 ? (
        <ul
          className="divide-y divide-line rounded-control border border-line"
          aria-label={t('uploadQueue')}
        >
          {queue.map((entry) => (
            <li
              key={entry.id}
              className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">
                  {entry.file.name}
                  <span className="font-normal text-ink-muted">
                    {' · '}
                    {formatBytes(entry.file.size)}
                  </span>
                </p>
                {entry.error ? (
                  <p role="alert" className="text-sm text-danger">
                    {entry.error}
                  </p>
                ) : (
                  <p role="status" className="text-sm text-ink-muted">
                    {entry.state === 'uploading'
                      ? t('uploading')
                      : t('statusPending')}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 gap-1">
                {entry.state === 'failed' ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={disabled}
                    aria-label={t('retryFile', { name: entry.file.name })}
                    onClick={() => retry(entry)}
                  >
                    {t('errorRetry')}
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={disabled || entry.state === 'uploading'}
                  aria-label={t('removeFile', { name: entry.file.name })}
                  onClick={() =>
                    updateQueue((current) =>
                      current.filter(
                        (item) =>
                          item.id !== entry.id || item.state === 'uploading',
                      ),
                    )
                  }
                >
                  {t('remove')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {refreshError ? (
        <p role="alert" className="text-sm text-danger">
          {t('uploadRefreshError')}
        </p>
      ) : null}
    </div>
  )
}

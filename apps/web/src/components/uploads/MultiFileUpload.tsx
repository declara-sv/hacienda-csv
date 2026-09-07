import { UploadCloud } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '#/components/ui/Button'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, uploadsApi } from '#/lib/api-client'
import { detectSourceFileKind, formatBytes } from '#/lib/format'
import type { SourceFileKind } from '#/lib/format'

export type UploadQueueState = { pendingCount: number; busy: boolean }
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

// Mount with a period key: pending File objects must never cross periods.
export function MultiFileUpload({
  clientId,
  periodId,
  disabled = false,
  onUploaded,
  onQueueStateChange,
}: Props) {
  const { t } = useI18n()
  const [queue, setQueue] = useState<Entry[]>([])
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
  useEffect(() => {
    callbacks.current.onQueueStateChange({ pendingCount: queue.length, busy })
  }, [queue.length, busy])

  const isMounted = () => mounted.current
  const locked = disabled || busy
  function append(files: FileList | File[]) {
    if (disabled || inFlight.current) return
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
    setQueue((current) => [...current, ...entries])
  }

  async function upload(entries: Entry[]) {
    if (disabled || inFlight.current || !entries.length) return
    inFlight.current = true
    setBusy(true)
    setRefreshError(false)
    try {
      for (const entry of entries) {
        if (!isMounted()) break
        if (!entry.kind) continue
        setQueue((current) =>
          current.map((item) =>
            item.id === entry.id
              ? { ...item, state: 'uploading', error: undefined }
              : item,
          ),
        )
        try {
          await uploadsApi.create(clientId, periodId, {
            file: entry.file,
            sourceFileKind: entry.kind,
          })
        } catch (error) {
          if (!isMounted()) break
          setQueue((current) =>
            current.map((item) =>
              item.id === entry.id
                ? {
                    ...item,
                    state: 'failed',
                    error:
                      error instanceof ApiError
                        ? error.message
                        : t('uploadError'),
                  }
                : item,
            ),
          )
          continue
        }
        if (!isMounted()) break
        // A saved file is never requeued, even when refreshing server data fails.
        setQueue((current) => current.filter((item) => item.id !== entry.id))
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

  return (
    <div className="space-y-4">
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".xls,.xlsx,.pdf"
        className="sr-only"
        aria-label={t('selectFiles')}
        disabled={locked}
        onChange={(event) => {
          if (event.currentTarget.files) append(event.currentTarget.files)
          event.currentTarget.value = ''
        }}
      />
      <button
        type="button"
        disabled={locked}
        className="flex w-full flex-col items-center gap-3 rounded-container border-2 border-dashed border-line-strong bg-surface-raised px-6 py-10 text-center transition hover:border-accent disabled:opacity-60"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          append(event.dataTransfer.files)
        }}
      >
        <UploadCloud className="size-8 text-accent" aria-hidden />
        <span className="font-semibold text-ink">{t('dropzoneTitle')}</span>
        <span className="text-sm text-ink-muted">{t('dropzoneHint')}</span>
      </button>
      {queue.length > 0 ? (
        <ul className="divide-y divide-line" aria-label={t('uploadQueue')}>
          {queue.map((entry) => (
            <li
              key={entry.id}
              className="flex flex-wrap items-center gap-3 py-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-ink">
                  {entry.file.name}
                </p>
                <p className="text-sm text-ink-muted">
                  {entry.kind ?? '—'} · {formatBytes(entry.file.size)}
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
              {entry.state === 'failed' ? (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={locked}
                  aria-label={t('retryFile', { name: entry.file.name })}
                  onClick={() => void upload([entry])}
                >
                  {t('errorRetry')}
                </Button>
              ) : null}
              <Button
                variant="ghost"
                size="sm"
                disabled={locked}
                aria-label={t('removeFile', { name: entry.file.name })}
                onClick={() => {
                  if (!disabled && !inFlight.current)
                    setQueue((current) =>
                      current.filter((item) => item.id !== entry.id),
                    )
                }}
              >
                {t('remove')}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      {refreshError ? (
        <p role="alert" className="text-sm text-danger">
          {t('uploadRefreshError')}
        </p>
      ) : null}
      <Button
        disabled={locked || !queue.some((entry) => entry.state === 'queued')}
        aria-busy={busy}
        onClick={() =>
          void upload(queue.filter((entry) => entry.state === 'queued'))
        }
      >
        {t('uploadFiles')}
      </Button>
    </div>
  )
}

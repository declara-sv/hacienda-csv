import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  FileSearch,
  Pencil,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { DocumentEditDialog } from './DocumentEditDialog'
import { Button } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import { Select } from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { RowListSkeleton } from '#/components/ui/Skeleton'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, documentsApi } from '#/lib/api-client'
import { cn } from '#/lib/cn'
import {
  documentReference,
  dteTypeLabel,
  filterDocuments,
  summarizeDocuments,
} from '#/lib/dte'
import { formatCents, formatIsoDate, formatMoney } from '#/lib/format'
import { rentaLabel, rentaOptionLabel, useRentaCatalog } from '#/lib/renta'
import type { ClientRentaDefaults } from './DocumentEditDialog'
import type { AnexoFilter, StatusFilter } from '#/lib/dte'
import type { MessageKey } from '#/i18n/messages'
import type {
  DocumentBulkUpdate,
  DocumentDto,
  DocumentPatch,
  DocumentStatus,
  RentaCatalogEntry,
} from '#/lib/api-types'
import type { LucideIcon } from 'lucide-react'

export const documentsQueryKey = (clientId: string, periodId: string) =>
  ['documents', clientId, periodId] as const

type PeriodReviewProps = {
  clientId: string
  periodId: string
  documents: DocumentDto[]
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
  clientDefaults?: ClientRentaDefaults | null
  /** Locks edits, e.g. while a generation request is in flight. */
  disabled?: boolean
}

const messageOf = (error: unknown, fallback: string) =>
  error instanceof ApiError ? error.message : fallback

const statusConfig: Record<
  DocumentStatus,
  { label: MessageKey; className: string; Icon: LucideIcon }
> = {
  Error: {
    label: 'reviewStatusError',
    className: 'bg-danger-soft text-danger',
    Icon: AlertCircle,
  },
  Warning: {
    label: 'reviewStatusWarning',
    className: 'bg-warning-soft text-warning',
    Icon: AlertTriangle,
  },
  Ok: {
    label: 'reviewStatusOk',
    className: 'bg-success-soft text-success',
    Icon: CheckCircle2,
  },
}

// Bulk selects: keep the current value, fall back to the client, or set a code.
const KEEP = '__keep'
const CLIENT = '__client'

const editTriggerId = (documentId: string) => `edit-document-${documentId}`

export function PeriodReview({
  clientId,
  periodId,
  documents,
  isLoading = false,
  error,
  onRetry,
  clientDefaults = null,
  disabled = false,
}: PeriodReviewProps) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const catalogQuery = useRentaCatalog()
  const catalog = catalogQuery.data
  const queryKey = documentsQueryKey(clientId, periodId)

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [anexoFilter, setAnexoFilter] = useState<AnexoFilter>('all')
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [bulkOperacion, setBulkOperacion] = useState(KEEP)
  const [bulkIngreso, setBulkIngreso] = useState(KEEP)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const summary = useMemo(() => summarizeDocuments(documents), [documents])
  const visible = useMemo(
    () => filterDocuments(documents, statusFilter, anexoFilter),
    [documents, statusFilter, anexoFilter],
  )

  // Drop selections of documents that disappeared (deleted or re-read files).
  useEffect(() => {
    setSelected((current) => {
      const ids = new Set(documents.map((document) => document.id))
      const next = new Set([...current].filter((id) => ids.has(id)))
      return next.size === current.size ? current : next
    })
  }, [documents])

  const invalidate = () => queryClient.invalidateQueries({ queryKey })

  const updateMutation = useMutation({
    mutationKey: queryKey,
    mutationFn: ({ id, patch }: { id: string; patch: DocumentPatch }) =>
      documentsApi.update(clientId, periodId, id, patch),
    onMutate: () => {
      setMutationError(null)
      setSuccess(null)
    },
    onSuccess: (updated) => {
      if (updated) {
        queryClient.setQueryData<DocumentDto[]>(queryKey, (current) =>
          current?.map((item) => (item.id === updated.id ? updated : item)),
        )
      }
    },
    // Issues depend on the whole period (duplicates), so always re-read.
    onSettled: () => invalidate(),
  })

  const bulkMutation = useMutation({
    mutationKey: queryKey,
    mutationFn: (update: DocumentBulkUpdate) =>
      documentsApi.bulkUpdate(clientId, periodId, update),
    onMutate: () => {
      setMutationError(null)
      setSuccess(null)
    },
    onSuccess: (_data, update) => {
      setSuccess(t('bulkApplied', { count: update.documentIds.length }))
      setSelected(new Set())
      setBulkOperacion(KEEP)
      setBulkIngreso(KEEP)
    },
    onError: (err) => setMutationError(messageOf(err, t('bulkError'))),
    onSettled: () => invalidate(),
  })

  const busy = disabled || bulkMutation.isPending
  const editing = documents.find((document) => document.id === editingId)

  const toggleIncluded = (document: DocumentDto) =>
    updateMutation.mutate(
      { id: document.id, patch: { excluded: !document.excluded } },
      {
        onError: (err) => setMutationError(messageOf(err, t('editSaveError'))),
      },
    )

  const visibleIds = visible.map((document) => document.id)
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selected.has(id))
  const someVisibleSelected = visibleIds.some((id) => selected.has(id))
  const selectAllRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (selectAllRef.current)
      selectAllRef.current.indeterminate =
        someVisibleSelected && !allVisibleSelected
  }, [someVisibleSelected, allVisibleSelected])

  const toggleAllVisible = () =>
    setSelected((current) => {
      const next = new Set(current)
      if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id))
      else visibleIds.forEach((id) => next.add(id))
      return next
    })

  const toggleOne = (id: string) =>
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const bulkValue = (value: string) =>
    value === KEEP ? undefined : value === CLIENT ? null : value

  const applyBulkCodes = () => {
    const update: DocumentBulkUpdate = { documentIds: [...selected] }
    const operacion = bulkValue(bulkOperacion)
    const ingreso = bulkValue(bulkIngreso)
    if (operacion !== undefined) update.tipoOperacionRenta = operacion
    if (ingreso !== undefined) update.tipoIngresoRenta = ingreso
    bulkMutation.mutate(update)
  }

  if (isLoading && documents.length === 0) {
    return (
      <div role="status">
        <span className="sr-only">{t('reviewLoading')}</span>
        <RowListSkeleton />
      </div>
    )
  }

  return (
    <div className="space-y-5">
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

      {!error && documents.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title={t('reviewEmpty')}
          body={t('reviewEmptyBody')}
        />
      ) : null}

      {documents.length > 0 ? (
        <>
          <dl
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
            aria-label={t('reviewSummaryLabel')}
          >
            <SummaryTile
              label={t('anexo1Title')}
              value={formatCents(summary.anexo1.totalCents)}
              detail={t('reviewDocumentsCount', {
                count: summary.anexo1.count,
              })}
            />
            <SummaryTile
              label={t('anexo2Title')}
              value={formatCents(summary.anexo2.totalCents)}
              detail={t('reviewDocumentsCount', {
                count: summary.anexo2.count,
              })}
            />
            <SummaryTile
              label={t('reviewSummaryOther')}
              value={String(summary.excluded + summary.withoutAnexo)}
              detail={t('reviewSummaryOtherDetail', {
                excluded: summary.excluded,
                none: summary.withoutAnexo,
              })}
            />
            <SummaryTile
              label={t('reviewSummaryErrors')}
              value={String(summary.blockingErrors)}
              detail={t('reviewSummaryWarnings', { count: summary.warnings })}
              tone={summary.blockingErrors > 0 ? 'danger' : 'default'}
            />
          </dl>

          {mutationError ? (
            <Notice variant="error" onDismiss={() => setMutationError(null)}>
              {mutationError}
            </Notice>
          ) : null}
          {success ? (
            <Notice variant="success" onDismiss={() => setSuccess(null)}>
              {success}
            </Notice>
          ) : null}

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1.5 text-sm font-semibold text-ink">
              {t('reviewFilterStatus')}
              <Select
                value={statusFilter}
                onChange={(event) =>
                  setStatusFilter(event.target.value as StatusFilter)
                }
              >
                <option value="all">{t('reviewFilterAll')}</option>
                <option value="Error">{t('reviewStatusError')}</option>
                <option value="Warning">{t('reviewStatusWarning')}</option>
                <option value="Ok">{t('reviewStatusOk')}</option>
              </Select>
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-semibold text-ink">
              {t('reviewFilterAnexo')}
              <Select
                value={anexoFilter}
                onChange={(event) =>
                  setAnexoFilter(event.target.value as AnexoFilter)
                }
              >
                <option value="all">{t('reviewFilterAll')}</option>
                <option value="1">{t('anexoLabel', { anexo: 1 })}</option>
                <option value="2">{t('anexoLabel', { anexo: 2 })}</option>
                <option value="none">{t('anexoNone')}</option>
              </Select>
            </label>
            <p className="pb-2 text-sm text-ink-muted" aria-live="polite">
              {t('reviewShowing', {
                shown: visible.length,
                total: documents.length,
              })}
            </p>
          </div>

          {selected.size > 0 ? (
            <section
              aria-label={t('bulkLabel')}
              className="flex flex-wrap items-end gap-3 rounded-container border border-accent bg-accent-soft/40 p-4"
            >
              <p className="w-full text-sm font-semibold text-ink">
                {t('bulkSelected', { count: selected.size })}
              </p>
              <BulkRentaSelect
                id="bulk-tipo-operacion"
                label={t('fieldTipoOperacion')}
                entries={catalog?.tipoOperacion}
                value={bulkOperacion}
                onChange={setBulkOperacion}
                disabled={busy}
              />
              <BulkRentaSelect
                id="bulk-tipo-ingreso"
                label={t('fieldTipoIngreso')}
                entries={catalog?.tipoIngreso}
                value={bulkIngreso}
                onChange={setBulkIngreso}
                disabled={busy}
              />
              <Button
                onClick={applyBulkCodes}
                disabled={
                  busy || (bulkOperacion === KEEP && bulkIngreso === KEEP)
                }
                loading={bulkMutation.isPending}
                loadingLabel={t('saving')}
              >
                {t('bulkApplyCodes')}
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() =>
                  bulkMutation.mutate({
                    documentIds: [...selected],
                    excluded: true,
                  })
                }
              >
                {t('bulkExclude')}
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() =>
                  bulkMutation.mutate({
                    documentIds: [...selected],
                    excluded: false,
                  })
                }
              >
                {t('bulkInclude')}
              </Button>
              <Button
                variant="ghost"
                disabled={bulkMutation.isPending}
                onClick={() => setSelected(new Set())}
              >
                {t('bulkClear')}
              </Button>
            </section>
          ) : null}

          <div className="overflow-x-auto rounded-container border border-line bg-surface-raised">
            <table className="w-full min-w-[96rem] border-collapse text-left text-sm">
              <caption className="sr-only">{t('reviewTableCaption')}</caption>
              <thead className="border-b border-line bg-surface-sunken/60 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <tr>
                  <th scope="col" className="w-10 px-3 py-2.5">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      className="size-4 accent-[var(--accent)]"
                      checked={allVisibleSelected}
                      onChange={toggleAllVisible}
                      disabled={visibleIds.length === 0}
                      aria-label={t('reviewSelectAll')}
                    />
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('colFecha')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('colTipo')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('colAnexo')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('colCodigoGeneracion')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('colReceptor')}
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-right">
                    {t('fieldExentas')}
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-right">
                    {t('fieldNoSujetas')}
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-right">
                    {t('fieldGravadas')}
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-right">
                    {t('fieldIva')}
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-right">
                    {t('fieldTotal')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('fieldTipoOperacion')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('fieldTipoIngreso')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('colEstado')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    {t('colIncluido')}
                  </th>
                  <th scope="col" className="px-3 py-2.5">
                    <span className="sr-only">{t('colAcciones')}</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {visible.map((document) => (
                  <DocumentRow
                    key={document.id}
                    document={document}
                    operacionEntries={catalog?.tipoOperacion}
                    ingresoEntries={catalog?.tipoIngreso}
                    selected={selected.has(document.id)}
                    onToggleSelected={() => toggleOne(document.id)}
                    onToggleIncluded={() => toggleIncluded(document)}
                    togglingIncluded={
                      updateMutation.isPending &&
                      updateMutation.variables.id === document.id
                    }
                    onEdit={() => setEditingId(document.id)}
                    disabled={busy}
                  />
                ))}
              </tbody>
            </table>
            {visible.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-ink-muted">
                {t('reviewNoMatches')}
              </p>
            ) : null}
          </div>
        </>
      ) : null}

      {editing ? (
        <DocumentEditDialog
          key={editing.id}
          document={editing}
          catalog={catalog}
          clientDefaults={clientDefaults}
          onClose={() => setEditingId(null)}
          onSave={(patch) =>
            updateMutation.mutateAsync({ id: editing.id, patch })
          }
        />
      ) : null}
    </div>
  )
}

function SummaryTile({
  label,
  value,
  detail,
  tone = 'default',
}: {
  label: string
  value: string
  detail: string
  tone?: 'default' | 'danger'
}) {
  return (
    <div
      className={cn(
        'rounded-container border bg-surface-raised px-4 py-3',
        tone === 'danger' ? 'border-danger' : 'border-line',
      )}
    >
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd
        className={cn(
          'mt-0.5 text-xl font-semibold tabular-nums',
          tone === 'danger' ? 'text-danger' : 'text-ink',
        )}
      >
        {value}
      </dd>
      <dd className="text-sm text-ink-muted">{detail}</dd>
    </div>
  )
}

function BulkRentaSelect({
  id,
  label,
  entries,
  value,
  onChange,
  disabled,
}: {
  id: string
  label: string
  entries: readonly RentaCatalogEntry[] | undefined
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}) {
  const { t } = useI18n()
  return (
    <div className="flex min-w-60 flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-ink">
        {label}
      </label>
      <Select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value={KEEP}>{t('bulkKeep')}</option>
        <option value={CLIENT}>{t('bulkUseClient')}</option>
        {entries?.map((entry) => (
          <option key={entry.code} value={entry.code}>
            {rentaOptionLabel(entry)}
          </option>
        ))}
      </Select>
    </div>
  )
}

type DocumentRowProps = {
  document: DocumentDto
  operacionEntries: readonly RentaCatalogEntry[] | undefined
  ingresoEntries: readonly RentaCatalogEntry[] | undefined
  selected: boolean
  onToggleSelected: () => void
  onToggleIncluded: () => void
  togglingIncluded: boolean
  onEdit: () => void
  disabled: boolean
}

function DocumentRow({
  document,
  operacionEntries,
  ingresoEntries,
  selected,
  onToggleSelected,
  onToggleIncluded,
  togglingIncluded,
  onEdit,
  disabled,
}: DocumentRowProps) {
  const { t } = useI18n()
  const reference = documentReference(document)
  const money = (value: string) => (
    <td className="px-3 py-3 text-right tabular-nums">{formatMoney(value)}</td>
  )

  return (
    <tr
      className={cn(
        'align-top',
        selected && 'bg-accent-soft/40',
        document.excluded && 'text-ink-muted',
      )}
    >
      <td className="px-3 py-3">
        <input
          type="checkbox"
          className="size-4 accent-[var(--accent)]"
          checked={selected}
          onChange={onToggleSelected}
          aria-label={t('reviewSelectDocument', { reference })}
        />
      </td>
      <td className="whitespace-nowrap px-3 py-3 tabular-nums">
        {formatIsoDate(document.fechaEmision) || '—'}
        {document.horaEmision ? (
          <span className="block text-xs text-ink-muted">
            {document.horaEmision}
          </span>
        ) : null}
      </td>
      <td className="px-3 py-3">
        <span className="whitespace-nowrap font-semibold">
          {dteTypeLabel(document.tipoDte)}
        </span>
        <span
          className="block max-w-40 truncate text-xs text-ink-muted"
          title={document.originalFileName}
        >
          {document.originalFileName}
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-3">
        {document.anexo ? (
          t('anexoLabel', { anexo: document.anexo })
        ) : (
          <span className="text-ink-muted" title={t('anexoNoneHint')}>
            {t('anexoNone')}
          </span>
        )}
      </td>
      <td className="px-3 py-3">
        {document.codigoGeneracion ? (
          <CopyableCode value={document.codigoGeneracion} />
        ) : (
          <span className="text-ink-muted">—</span>
        )}
      </td>
      <td className="px-3 py-3">
        <span className="block max-w-56 break-words">
          {document.receptorNombre ?? '—'}
        </span>
        <ReceptorIds document={document} />
      </td>
      {money(document.totalExentas)}
      {money(document.totalNoSujetas)}
      {money(document.totalGravadas)}
      {money(document.iva)}
      <td className="px-3 py-3 text-right font-semibold tabular-nums">
        {formatMoney(document.total)}
      </td>
      <td className="px-3 py-3">
        <RentaCell
          code={document.effectiveTipoOperacion}
          overridden={document.tipoOperacionRenta !== null}
          entries={operacionEntries}
        />
      </td>
      <td className="px-3 py-3">
        <RentaCell
          code={document.effectiveTipoIngreso}
          overridden={document.tipoIngresoRenta !== null}
          entries={ingresoEntries}
        />
      </td>
      <td className="px-3 py-3">
        <IssuesCell document={document} />
      </td>
      <td className="px-3 py-3">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            role="switch"
            className="size-4 accent-[var(--accent)]"
            checked={!document.excluded}
            disabled={disabled || togglingIncluded}
            onChange={onToggleIncluded}
            aria-label={t('reviewIncludeDocument', { reference })}
          />
          <span className="text-xs" aria-hidden>
            {document.excluded ? t('reviewExcluded') : t('reviewIncluded')}
          </span>
        </label>
      </td>
      <td className="px-3 py-3">
        <Button
          id={editTriggerId(document.id)}
          variant="ghost"
          size="sm"
          icon={<Pencil className="size-4" strokeWidth={2} />}
          disabled={disabled}
          aria-label={t('reviewEditDocument', { reference })}
          onClick={onEdit}
        >
          {t('edit')}
        </Button>
      </td>
    </tr>
  )
}

function ReceptorIds({ document }: { document: DocumentDto }) {
  const { t } = useI18n()
  const ids = [
    document.receptorNit ? `${t('fieldNit')} ${document.receptorNit}` : null,
    document.receptorDui ? `${t('fieldDui')} ${document.receptorDui}` : null,
    document.receptorNrc ? `${t('fieldNrc')} ${document.receptorNrc}` : null,
  ].filter(Boolean)
  if (ids.length === 0) return null
  return (
    <span className="block text-xs tabular-nums text-ink-muted">
      {ids.join(' · ')}
    </span>
  )
}

function CopyableCode({ value }: { value: string }) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  return (
    <span className="flex items-start gap-1">
      <code className="block w-[19ch] select-all break-all font-mono text-xs leading-5 text-ink">
        {value}
      </code>
      <button
        type="button"
        className="-my-0.5 rounded-control p-1 text-ink-muted transition hover:bg-accent-soft hover:text-accent"
        aria-label={copied ? t('copied') : t('copyCode', { code: value })}
        title={copied ? t('copied') : t('copy')}
        onClick={() => {
          // Clipboard is missing on insecure origins; the code stays selectable.
          try {
            void navigator.clipboard
              .writeText(value)
              .then(() => setCopied(true))
              .catch(() => setCopied(false))
          } catch {
            setCopied(false)
          }
        }}
      >
        {copied ? (
          <Check className="size-3.5" strokeWidth={2} aria-hidden />
        ) : (
          <Copy className="size-3.5" strokeWidth={2} aria-hidden />
        )}
      </button>
    </span>
  )
}

function RentaCell({
  code,
  overridden,
  entries,
}: {
  code: string | null
  overridden: boolean
  entries: readonly RentaCatalogEntry[] | undefined
}) {
  const { t } = useI18n()
  if (!code) {
    return (
      <span className="whitespace-nowrap font-semibold text-danger">
        {t('rentaMissing')}
      </span>
    )
  }
  const label = rentaLabel(entries, code)
  return (
    <span className="flex flex-col items-start gap-1" title={label}>
      <span className="font-semibold tabular-nums">{code}</span>
      <span
        className={cn(
          'rounded-full px-2 py-0.5 text-xs font-semibold',
          overridden
            ? 'bg-accent-soft text-accent'
            : 'bg-surface-sunken text-ink-muted',
        )}
      >
        {overridden ? t('rentaOverride') : t('rentaFromClient')}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  )
}

function IssuesCell({ document }: { document: DocumentDto }) {
  const { t } = useI18n()
  const { label, className, Icon } = statusConfig[document.status]
  const chip = (
    <span
      className={cn(
        'inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-semibold',
        className,
      )}
    >
      <Icon className="size-3.5" strokeWidth={2} aria-hidden />
      {t(label)}
      {document.issues.length > 0 ? ` (${document.issues.length})` : null}
    </span>
  )
  const badges = (
    <span className="mt-1 flex flex-wrap gap-1">
      {document.edited ? (
        <span className="text-xs text-ink-muted">{t('reviewEdited')}</span>
      ) : null}
      {document.extractionMethod === 'Ai' ? (
        <span className="text-xs text-ink-muted">{t('reviewReadByAi')}</span>
      ) : null}
    </span>
  )
  if (document.issues.length === 0) {
    return (
      <>
        {chip}
        {badges}
      </>
    )
  }
  return (
    <details className="max-w-72">
      <summary
        className="cursor-pointer list-none"
        title={document.issues.map((issue) => issue.message).join('\n')}
      >
        {chip}
        <span className="sr-only">{t('reviewShowIssues')}</span>
      </summary>
      <ul className="mt-2 space-y-1.5">
        {document.issues.map((issue, index) => (
          <li
            key={`${issue.code}-${index}`}
            className={cn(
              'text-xs',
              issue.severity === 'Error' ? 'text-danger' : 'text-warning',
            )}
          >
            <span className="font-semibold">
              {issue.severity === 'Error' ? t('issueError') : t('issueWarning')}
              :
            </span>{' '}
            {issue.message}
          </li>
        ))}
      </ul>
      {badges}
    </details>
  )
}

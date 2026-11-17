import { Link, createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CalendarDays, Pencil } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { ClientForm } from '#/components/clients/ClientForm'
import { RentaDefaultsHint } from '#/components/clients/RentaDefaultsHint'
import { Breadcrumb } from '#/components/ui/Breadcrumb'
import { Button, buttonClasses } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import { Input, Select } from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { PageHeader, Section } from '#/components/ui/PageHeader'
import { PageSkeleton } from '#/components/ui/Skeleton'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, clientsApi } from '#/lib/api-client'
import { MONTHS_ES, formatPeriod, previousMonth } from '#/lib/format'
import { rentaLabel, useRentaCatalog } from '#/lib/renta'
import type { ClientDetail, FilingPeriodSummary } from '#/lib/api-types'
import type { CSSProperties } from 'react'

export const Route = createFileRoute('/clients/$clientId/')({
  head: () => ({ meta: [{ title: 'Cliente | AnexosFácil' }] }),
  component: ClientDetailPage,
})

const sortPeriods = (periods: readonly FilingPeriodSummary[]) =>
  [...periods].sort((a, b) => b.year - a.year || b.month - a.month)

function ClientDetailPage() {
  const { clientId } = Route.useParams()
  const { t } = useI18n()

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => clientsApi.get(clientId),
  })

  const client = clientQuery.data
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const editTriggerRef = useRef<HTMLButtonElement>(null)
  const latestPeriod = client ? sortPeriods(client.filingPeriods)[0] : undefined

  const closeEditor = (didSave: boolean) => {
    setEditing(false)
    setSaved(didSave)
    // The form unmounts; keep keyboard users on the button that opened it.
    requestAnimationFrame(() => editTriggerRef.current?.focus())
  }

  return (
    <div className="space-y-8">
      <Breadcrumb
        items={[
          { label: t('menuClients'), to: '/clients' },
          { label: client ? client.name : null },
        ]}
      />

      {clientQuery.isLoading ? <PageSkeleton /> : null}

      {clientQuery.isError ? (
        <Notice variant="error">
          {clientQuery.error instanceof ApiError
            ? clientQuery.error.message
            : t('clientLoadingError')}
        </Notice>
      ) : null}

      {client ? (
        <>
          <PageHeader
            title={client.name}
            meta={
              <span className="tabular-nums">
                {[
                  client.nit ? `${t('clientNit')} ${client.nit}` : client.taxId,
                  client.nrc ? `${t('clientNrc')} ${client.nrc}` : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            }
            description={client.notes ?? undefined}
            actions={
              <>
                {!editing ? (
                  <Button
                    ref={editTriggerRef}
                    variant="secondary"
                    icon={<Pencil className="size-4" strokeWidth={2} />}
                    aria-controls="client-fiscal"
                    onClick={() => {
                      setSaved(false)
                      setEditing(true)
                    }}
                  >
                    {t('editClient')}
                  </Button>
                ) : null}
                {latestPeriod ? (
                  <Link
                    to="/clients/$clientId/periods/$periodId/uploads"
                    params={{ clientId, periodId: latestPeriod.id }}
                    className={buttonClasses('primary')}
                  >
                    {t('openPeriod', {
                      period: formatPeriod(
                        latestPeriod.year,
                        latestPeriod.month,
                      ).toLowerCase(),
                    })}
                  </Link>
                ) : null}
              </>
            }
          />

          {saved ? (
            <Notice variant="success" onDismiss={() => setSaved(false)}>
              {t('clientUpdated')}
            </Notice>
          ) : null}

          {!editing ? (
            <RentaDefaultsHint
              client={client}
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setEditing(true)}
                >
                  {t('rentaRequiredAction')}
                </Button>
              }
            />
          ) : null}

          <section
            id="client-fiscal"
            aria-labelledby="client-fiscal-heading"
            className="rounded-container border border-line bg-surface-raised p-5 sm:p-6"
          >
            <h2
              id="client-fiscal-heading"
              className="text-lg font-semibold text-ink"
            >
              {editing ? t('editClient') : t('clientFiscalTitle')}
            </h2>
            <div className="mt-4">
              {editing ? (
                <ClientForm
                  client={client}
                  idPrefix="edit-client"
                  onCancel={() => closeEditor(false)}
                  onSaved={() => closeEditor(true)}
                />
              ) : (
                <ClientFiscalData client={client} />
              )}
            </div>
          </section>

          <Section title={t('filingPeriods')} description={t('periodsIntro')}>
            <PeriodsPanel client={client} />
          </Section>
        </>
      ) : null}
    </div>
  )
}

function ClientFiscalData({ client }: { client: ClientDetail }) {
  const { t } = useI18n()
  const catalogQuery = useRentaCatalog()
  const missing = (
    <span className="text-ink-muted">{t('clientValueMissing')}</span>
  )
  const items: Array<{ label: string; value: React.ReactNode }> = [
    {
      label: t('clientNit'),
      value: client.nit ? (
        <span className="tabular-nums">{client.nit}</span>
      ) : (
        missing
      ),
    },
    {
      label: t('clientNrc'),
      value: client.nrc ? (
        <span className="tabular-nums">{client.nrc}</span>
      ) : (
        missing
      ),
    },
    {
      label: t('clientDefaultTipoOperacion'),
      value: client.defaultTipoOperacion
        ? rentaLabel(
            catalogQuery.data?.tipoOperacion,
            client.defaultTipoOperacion,
          )
        : missing,
    },
    {
      label: t('clientDefaultTipoIngreso'),
      value: client.defaultTipoIngreso
        ? rentaLabel(catalogQuery.data?.tipoIngreso, client.defaultTipoIngreso)
        : missing,
    },
  ]
  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label} className="space-y-0.5">
          <dt className="text-sm font-semibold text-ink">{item.label}</dt>
          <dd className="text-sm text-ink">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function PeriodsPanel({ client }: { client: ClientDetail }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const suggested = useMemo(() => previousMonth(new Date()), [])
  const [year, setYear] = useState(suggested.year)
  const [month, setMonth] = useState(suggested.month)
  const [error, setError] = useState<string | null>(null)

  const periods = useMemo(
    () => sortPeriods(client.filingPeriods),
    [client.filingPeriods],
  )
  const existing = client.filingPeriods.find(
    (p) => p.year === year && p.month === month,
  )

  const openPeriod = (periodId: string) =>
    navigate({
      to: '/clients/$clientId/periods/$periodId/uploads',
      params: { clientId: client.id, periodId },
    })

  const createPeriodMutation = useMutation({
    mutationFn: () => clientsApi.createPeriod(client.id, { year, month }),
    onSuccess: async () => {
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['clients'] })
      const refreshed = await queryClient.fetchQuery({
        queryKey: ['client', client.id],
        queryFn: () => clientsApi.get(client.id),
        staleTime: 0,
      })
      const created = refreshed.filingPeriods.find(
        (p) => p.year === year && p.month === month,
      )
      if (created) void openPeriod(created.id)
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : t('periodCreateError'))
    },
  })

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    if (existing) {
      void openPeriod(existing.id)
      return
    }
    createPeriodMutation.mutate()
  }

  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap items-end gap-3"
        aria-label={t('newPeriodLabel')}
        onSubmit={onSubmit}
      >
        <label className="flex w-44 flex-col gap-1.5 text-sm font-semibold text-ink">
          {t('periodMonth')}
          <Select
            name="month"
            value={month}
            onChange={(event) => setMonth(Number(event.target.value))}
          >
            {MONTHS_ES.map((name, index) => (
              <option key={name} value={index + 1}>
                {name}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex w-28 flex-col gap-1.5 text-sm font-semibold text-ink">
          {t('periodYear')}
          <Input
            name="year"
            type="number"
            inputMode="numeric"
            min={2000}
            max={2100}
            required
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
        </label>
        <Button
          type="submit"
          variant={existing ? 'secondary' : 'primary'}
          icon={
            existing ? <ArrowRight className="size-4" strokeWidth={2} /> : null
          }
          loading={createPeriodMutation.isPending}
          loadingLabel={t('addingPeriod')}
        >
          {existing ? t('openExistingPeriod') : t('addPeriod')}
        </Button>
      </form>

      {error ? (
        <Notice variant="error" onDismiss={() => setError(null)}>
          {error}
        </Notice>
      ) : null}

      {periods.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title={t('periodsEmpty')}
          body={t('periodsEmptyBody')}
        />
      ) : (
        <ul
          className="divide-y divide-line overflow-hidden rounded-container border border-line bg-surface-raised"
          aria-label={t('periodsListLabel')}
        >
          {periods.map((period, index) => (
            <li
              key={period.id}
              className="rise"
              style={{ '--i': index } as CSSProperties}
            >
              <Link
                to="/clients/$clientId/periods/$periodId/uploads"
                params={{ clientId: client.id, periodId: period.id }}
                className="group flex items-center justify-between gap-4 px-4 py-3 transition hover:bg-accent-soft/50"
              >
                <span className="font-semibold text-ink group-hover:text-accent">
                  {formatPeriod(period.year, period.month)}
                </span>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent">
                  {t('periodOpen')}
                  <ArrowRight
                    className="size-4 transition duration-200 group-hover:translate-x-0.5"
                    strokeWidth={2}
                    aria-hidden
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

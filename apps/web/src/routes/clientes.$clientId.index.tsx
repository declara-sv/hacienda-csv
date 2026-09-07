import { Link, createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CalendarDays, ChevronDown, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Breadcrumb } from '#/components/ui/Breadcrumb'
import { Button } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import {
  Field,
  Input,
  Select,
  Textarea,
  fieldDescribedBy,
} from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { PageHeader, Section } from '#/components/ui/PageHeader'
import { PageSkeleton } from '#/components/ui/Skeleton'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, clientsApi } from '#/lib/api-client'
import { MONTHS_ES, formatDateTime, formatPeriod } from '#/lib/format'
import type { ClientDetail } from '#/lib/api-types'
import type { CSSProperties } from 'react'

export const Route = createFileRoute('/clientes/$clientId/')({
  head: () => ({ meta: [{ title: 'Cliente | HaciendaCSV' }] }),
  component: ClientDetailPage,
})

function ClientDetailPage() {
  const { clientId } = Route.useParams()
  const { t } = useI18n()

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => clientsApi.get(clientId),
  })

  const client = clientQuery.data

  return (
    <div className="space-y-8">
      <Breadcrumb
        items={[
          { label: t('menuClients'), to: '/clientes' },
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
            meta={<span className="tabular-nums">{client.taxId}</span>}
            description={client.notes ?? undefined}
          />

          <Section title={t('filingPeriods')} description={t('periodsIntro')}>
            <PeriodsPanel client={client} />
          </Section>

          <AdvancedSettings client={client} />
        </>
      ) : null}
    </div>
  )
}

function PeriodsPanel({ client }: { client: ClientDetail }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()

  const now = useMemo(() => new Date(), [])
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [error, setError] = useState<string | null>(null)

  const periods = useMemo(
    () =>
      [...client.filingPeriods].sort(
        (a, b) => b.year - a.year || b.month - a.month,
      ),
    [client.filingPeriods],
  )

  const createPeriodMutation = useMutation({
    mutationFn: () => clientsApi.createPeriod(client.id, { year, month }),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['client', client.id] })
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : t('periodCreateError'))
    },
  })

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (
      client.filingPeriods.some((p) => p.year === year && p.month === month)
    ) {
      setError(t('periodExists'))
      return
    }
    setError(null)
    createPeriodMutation.mutate()
  }

  return (
    <div className="space-y-5">
      <form
        className="grid gap-4 rounded-container border border-line bg-surface-raised p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] sm:items-end"
        onSubmit={onSubmit}
      >
        <Field id="year" label={t('periodYear')}>
          <Input
            id="year"
            name="year"
            type="number"
            inputMode="numeric"
            min={2000}
            max={2100}
            required
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
        </Field>

        <Field id="month" label={t('periodMonth')}>
          <Select
            id="month"
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
        </Field>

        <Button
          type="submit"
          icon={<Plus className="size-4" strokeWidth={2} />}
          loading={createPeriodMutation.isPending}
          loadingLabel={t('addingPeriod')}
        >
          {t('addPeriod')}
        </Button>

        {error ? (
          <Notice
            variant="error"
            className="sm:col-span-3"
            onDismiss={() => setError(null)}
          >
            {error}
          </Notice>
        ) : null}
      </form>

      {periods.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title={t('periodsEmpty')}
          body={t('periodsEmptyBody')}
        />
      ) : (
        <ul
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
          aria-label={t('periodsListLabel')}
        >
          {periods.map((period, index) => (
            <li
              key={period.id}
              className="rise"
              style={{ '--i': index } as CSSProperties}
            >
              <Link
                to="/clientes/$clientId/periodos/$periodId/cargas"
                params={{ clientId: client.id, periodId: period.id }}
                className="group flex items-center justify-between gap-4 rounded-container border border-line bg-surface-raised px-4 py-3.5 transition duration-200 ease-out-expo hover:-translate-y-0.5 hover:border-accent"
              >
                <span>
                  <span className="block font-semibold text-ink transition group-hover:text-accent">
                    {formatPeriod(period.year, period.month)}
                  </span>
                  <span className="block text-sm text-ink-muted">
                    {t('periodOpen')}
                  </span>
                </span>
                <ArrowRight
                  className="size-4 shrink-0 text-accent transition duration-200 group-hover:translate-x-0.5"
                  strokeWidth={2}
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function isValidJson(value: string) {
  try {
    JSON.parse(value)
    return true
  } catch {
    return false
  }
}

function AdvancedSettings({ client }: { client: ClientDetail }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()

  const [configName, setConfigName] = useState('Base')
  const [prefill, setPrefill] = useState('{\n  "actividad": "SERVICIOS"\n}')
  const [rules, setRules] = useState('{}')
  const [fieldErrors, setFieldErrors] = useState<{
    prefill?: string
    rules?: string
  }>({})
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const createConfigMutation = useMutation({
    mutationFn: () =>
      clientsApi.createConfig(client.id, {
        name: configName,
        prefillValuesJson: prefill,
        transformationRulesJson: rules,
        isActive: true,
      }),
    onSuccess: () => {
      setError(null)
      setSuccess(t('configSaved'))
      queryClient.invalidateQueries({ queryKey: ['client', client.id] })
    },
    onError: (err) => {
      setSuccess(null)
      setError(err instanceof ApiError ? err.message : t('configSaveError'))
    },
  })

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const errors: { prefill?: string; rules?: string } = {}
    if (!isValidJson(prefill)) errors.prefill = t('configInvalidJson')
    if (!isValidJson(rules)) errors.rules = t('configInvalidJson')
    setFieldErrors(errors)
    if (errors.prefill || errors.rules) return
    setError(null)
    setSuccess(null)
    createConfigMutation.mutate()
  }

  return (
    <details className="group rounded-container border border-line bg-surface-raised">
      <summary className="flex cursor-pointer items-center justify-between gap-4 rounded-container px-5 py-4 transition hover:bg-accent-soft/40">
        <span>
          <span className="block font-semibold text-ink">
            {t('advancedTitle')}
          </span>
          <span className="block text-sm text-ink-muted">
            {t('advancedIntro')}
          </span>
        </span>
        <ChevronDown
          className="size-5 shrink-0 text-ink-muted transition duration-200 group-open:rotate-180"
          strokeWidth={2}
          aria-hidden
        />
      </summary>

      <div className="grid gap-8 border-t border-line px-5 py-5 lg:grid-cols-2">
        <form className="space-y-5" onSubmit={onSubmit}>
          <Field id="configName" label={t('configName')}>
            <Input
              id="configName"
              name="name"
              required
              maxLength={80}
              value={configName}
              onChange={(event) => setConfigName(event.target.value)}
            />
          </Field>

          <Field
            id="prefillValuesJson"
            label={t('configPrefill')}
            error={fieldErrors.prefill}
          >
            <Textarea
              id="prefillValuesJson"
              name="prefillValuesJson"
              className="font-mono text-sm"
              spellCheck={false}
              invalid={Boolean(fieldErrors.prefill)}
              aria-describedby={fieldDescribedBy(
                'prefillValuesJson',
                undefined,
                fieldErrors.prefill,
              )}
              value={prefill}
              onChange={(event) => setPrefill(event.target.value)}
            />
          </Field>

          <Field
            id="transformationRulesJson"
            label={t('configRules')}
            error={fieldErrors.rules}
          >
            <Textarea
              id="transformationRulesJson"
              name="transformationRulesJson"
              className="font-mono text-sm"
              spellCheck={false}
              invalid={Boolean(fieldErrors.rules)}
              aria-describedby={fieldDescribedBy(
                'transformationRulesJson',
                undefined,
                fieldErrors.rules,
              )}
              value={rules}
              onChange={(event) => setRules(event.target.value)}
            />
          </Field>

          {error ? (
            <Notice variant="error" onDismiss={() => setError(null)}>
              {error}
            </Notice>
          ) : null}
          {success ? (
            <Notice variant="success" onDismiss={() => setSuccess(null)}>
              {success}
            </Notice>
          ) : null}

          <Button
            type="submit"
            variant="secondary"
            loading={createConfigMutation.isPending}
            loadingLabel={t('savingConfig')}
          >
            {t('saveConfig')}
          </Button>
        </form>

        <div>
          {client.configurations.length === 0 ? (
            <p className="text-sm text-ink-muted">{t('configsEmpty')}</p>
          ) : (
            <ul className="divide-y divide-line">
              {client.configurations.map((config) => (
                <li
                  key={config.id}
                  className="flex items-start justify-between gap-4 py-3 first:pt-0"
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-ink">
                      {config.name}
                    </p>
                    <p className="text-sm text-ink-muted">
                      {t('configUpdated', {
                        date: formatDateTime(config.updatedAtUtc),
                      })}
                    </p>
                  </div>
                  {config.isActive ? (
                    <span className="inline-flex h-7 shrink-0 items-center rounded-full bg-success-soft px-2.5 text-xs font-semibold text-success">
                      {t('configActive')}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </details>
  )
}

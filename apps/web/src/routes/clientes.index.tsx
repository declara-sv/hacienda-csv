import { Link, createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  CalendarDays,
  Plus,
  Search,
  SearchX,
  Users,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Button } from '#/components/ui/Button'
import { EmptyState } from '#/components/ui/EmptyState'
import { Field, Input, Textarea, fieldDescribedBy } from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { PageHeader } from '#/components/ui/PageHeader'
import { TileGridSkeleton } from '#/components/ui/Skeleton'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, clientsApi } from '#/lib/api-client'
import type { ClientSummary } from '#/lib/api-types'
import type { CSSProperties } from 'react'

export const Route = createFileRoute('/clientes/')({
  head: () => ({ meta: [{ title: 'Clientes | HaciendaCSV' }] }),
  component: ClientsHomePage,
})

function ClientsHomePage() {
  const { t } = useI18n()

  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [success, setSuccess] = useState<string | null>(null)

  const clientsQuery = useQuery({
    queryKey: ['clients'],
    queryFn: clientsApi.list,
  })

  const clients = clientsQuery.data ?? []
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return clients
    return clients.filter(
      (client) =>
        client.name.toLowerCase().includes(needle) ||
        client.taxId.toLowerCase().includes(needle),
    )
  }, [clients, query])

  const openCreate = () => {
    setSuccess(null)
    setCreating(true)
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('clientsTitle')}
        description={t('clientsIntro')}
        actions={
          <Button
            icon={<Plus className="size-4" strokeWidth={2} />}
            onClick={() => (creating ? setCreating(false) : openCreate())}
            aria-expanded={creating}
            aria-controls="new-client"
            variant={creating ? 'secondary' : 'primary'}
          >
            {t('createClient')}
          </Button>
        }
      />

      {creating ? (
        <NewClientForm
          onCancel={() => setCreating(false)}
          onCreated={() => {
            setCreating(false)
            setSuccess(t('clientCreated'))
          }}
        />
      ) : null}

      {success ? (
        <Notice variant="success" onDismiss={() => setSuccess(null)}>
          {success}
        </Notice>
      ) : null}

      <section aria-labelledby="clients-list-heading" className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2
            id="clients-list-heading"
            className="text-lg font-semibold text-ink"
          >
            {clientsQuery.isSuccess
              ? clients.length === 1
                ? t('clientsCountOne')
                : t('clientsCount', { count: clients.length })
              : t('clientsListLabel')}
          </h2>
          <div className="relative w-full sm:max-w-xs">
            <label htmlFor="clients-search" className="sr-only">
              {t('clientsSearch')}
            </label>
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted"
              strokeWidth={2}
              aria-hidden
            />
            <Input
              id="clients-search"
              type="search"
              className="pl-9"
              placeholder={t('clientsSearch')}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              disabled={clientsQuery.isLoading || clients.length === 0}
            />
          </div>
        </div>

        {clientsQuery.isLoading ? <TileGridSkeleton /> : null}

        {clientsQuery.isError ? (
          <Notice variant="error">
            {clientsQuery.error instanceof ApiError
              ? clientsQuery.error.message
              : t('clientLoadingError')}
          </Notice>
        ) : null}

        {clientsQuery.isSuccess && clients.length === 0 ? (
          <EmptyState
            icon={Users}
            title={t('clientsEmpty')}
            body={t('clientsEmptyBody')}
            action={
              !creating ? (
                <Button
                  icon={<Plus className="size-4" strokeWidth={2} />}
                  onClick={openCreate}
                >
                  {t('createClient')}
                </Button>
              ) : undefined
            }
          />
        ) : null}

        {clientsQuery.isSuccess &&
        clients.length > 0 &&
        filtered.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title={t('clientsNoResults', { query: query.trim() })}
            body={t('clientsNoResultsBody')}
          />
        ) : null}

        {filtered.length > 0 ? (
          <ul
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
            aria-label={t('clientsListLabel')}
          >
            {filtered.map((client, index) => (
              <li
                key={client.id}
                className="rise"
                style={{ '--i': index } as CSSProperties}
              >
                <ClientTile client={client} />
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  )
}

function ClientTile({ client }: { client: ClientSummary }) {
  const { t } = useI18n()
  const periods =
    client.filingPeriodsCount === 1
      ? t('clientPeriodsOne')
      : t('clientPeriodsMany', { count: client.filingPeriodsCount })

  return (
    <Link
      to="/clientes/$clientId"
      params={{ clientId: client.id }}
      className="group flex h-full flex-col justify-between gap-6 rounded-container border border-line bg-surface-raised p-4 shadow-raised transition duration-200 ease-out-expo hover:-translate-y-0.5 hover:border-accent"
    >
      <div className="min-w-0">
        <p className="truncate font-semibold text-ink transition group-hover:text-accent">
          {client.name}
        </p>
        <p className="mt-0.5 text-sm tabular-nums text-ink-muted">
          {client.taxId}
        </p>
      </div>
      <div className="flex items-center justify-between text-sm text-ink-muted">
        <span className="inline-flex items-center gap-1.5">
          <CalendarDays className="size-4" strokeWidth={1.75} aria-hidden />
          {periods}
        </span>
        <ArrowRight
          className="size-4 text-accent transition duration-200 group-hover:translate-x-0.5"
          strokeWidth={2}
          aria-hidden
        />
      </div>
    </Link>
  )
}

function NewClientForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void
  onCreated: () => void
}) {
  const { t } = useI18n()
  const queryClient = useQueryClient()

  const [name, setName] = useState('')
  const [taxId, setTaxId] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const createClientMutation = useMutation({
    mutationFn: () => clientsApi.create({ name, taxId, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      onCreated()
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : t('clientCreateError'))
    },
  })

  return (
    <section
      id="new-client"
      aria-labelledby="new-client-heading"
      className="rise rounded-container border border-line bg-surface-raised p-5 shadow-raised sm:p-6"
    >
      <h2 id="new-client-heading" className="text-lg font-semibold text-ink">
        {t('newClientTitle')}
      </h2>

      <form
        className="mt-4 grid gap-5 md:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault()
          setError(null)
          createClientMutation.mutate()
        }}
      >
        <Field id="name" label={t('clientName')}>
          <Input
            id="name"
            name="name"
            autoFocus
            required
            maxLength={160}
            autoComplete="organization"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>

        <Field id="taxId" label={t('clientTaxId')} hint={t('clientTaxIdHint')}>
          <Input
            id="taxId"
            name="taxId"
            required
            maxLength={32}
            aria-describedby={fieldDescribedBy('taxId', t('clientTaxIdHint'))}
            value={taxId}
            onChange={(event) => setTaxId(event.target.value)}
          />
        </Field>

        <Field
          id="notes"
          label={t('clientNotes')}
          hint={t('clientNotesHint')}
          className="md:col-span-2"
        >
          <Textarea
            id="notes"
            name="notes"
            maxLength={2000}
            aria-describedby={fieldDescribedBy('notes', t('clientNotesHint'))}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>

        {error ? (
          <Notice
            variant="error"
            className="md:col-span-2"
            onDismiss={() => setError(null)}
          >
            {error}
          </Notice>
        ) : null}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end md:col-span-2">
          <Button variant="ghost" onClick={onCancel}>
            {t('cancel')}
          </Button>
          <Button
            type="submit"
            loading={createClientMutation.isPending}
            loadingLabel={t('savingClient')}
          >
            {t('saveClient')}
          </Button>
        </div>
      </form>
    </section>
  )
}

import { Link, createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, clientsApi } from '#/lib/api-client'
import { useI18n } from '#/i18n/I18nProvider'

export const Route = createFileRoute('/clientes/')({ component: ClientsHomePage })

function ClientsHomePage() {
  const { t } = useI18n()
  const queryClient = useQueryClient()

  const [name, setName] = useState('')
  const [taxId, setTaxId] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const clientsQuery = useQuery({
    queryKey: ['clients'],
    queryFn: clientsApi.list,
  })

  const createClientMutation = useMutation({
    mutationFn: () => clientsApi.create({ name, taxId, notes }),
    onSuccess: () => {
      setName('')
      setTaxId('')
      setNotes('')
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'No se pudo crear el cliente.')
    },
  })

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-[#173642]/15 bg-white/80 p-6 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)]">
        <h1 className="font-title text-4xl text-[#173642]">{t('clientsTitle')}</h1>
        <p className="mt-2 text-[#173642]/70">Organiza archivos por cliente y período fiscal (año/mes).</p>

        <form
          className="mt-6 grid gap-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault()
            createClientMutation.mutate()
          }}
        >
          <label className="text-sm font-semibold text-[#173642]">
            {t('clientName')}
            <input
              className="mt-1 w-full rounded-xl border border-[#173642]/20 bg-white px-3 py-2 outline-none ring-[#24513f] transition focus:ring-2"
              required
              maxLength={160}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>

          <label className="text-sm font-semibold text-[#173642]">
            {t('clientTaxId')}
            <input
              className="mt-1 w-full rounded-xl border border-[#173642]/20 bg-white px-3 py-2 outline-none ring-[#24513f] transition focus:ring-2"
              required
              maxLength={32}
              value={taxId}
              onChange={(event) => setTaxId(event.target.value)}
            />
          </label>

          <label className="text-sm font-semibold text-[#173642] md:col-span-2">
            {t('clientNotes')}
            <textarea
              className="mt-1 min-h-24 w-full rounded-xl border border-[#173642]/20 bg-white px-3 py-2 outline-none ring-[#24513f] transition focus:ring-2"
              maxLength={2000}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>

          {error ? <p className="md:col-span-2 rounded-lg bg-red-100 px-3 py-2 text-sm text-red-700">{error}</p> : null}

          <button
            className="md:col-span-2 rounded-xl bg-[#24513f] px-4 py-3 font-semibold text-white transition hover:bg-[#173642] disabled:opacity-60"
            type="submit"
            disabled={createClientMutation.isPending}
          >
            {createClientMutation.isPending ? 'Guardando...' : t('createClient')}
          </button>
        </form>
      </section>

      <section className="rounded-3xl border border-[#173642]/15 bg-white/80 p-6 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)]">
        <h2 className="font-title text-3xl text-[#173642]">Listado</h2>

        {clientsQuery.isLoading ? <p className="mt-4 text-sm">{t('loading')}</p> : null}

        {clientsQuery.isSuccess && clientsQuery.data.length === 0 ? (
          <p className="mt-4 text-sm text-[#173642]/75">{t('clientsEmpty')}</p>
        ) : null}

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {clientsQuery.data?.map((client) => (
            <Link
              key={client.id}
              to="/clientes/$clientId"
              params={{ clientId: client.id }}
              className="rounded-2xl border border-[#173642]/20 bg-[#fcfbf7] p-4 transition hover:-translate-y-1 hover:border-[#24513f]"
            >
              <p className="font-semibold text-[#173642]">{client.name}</p>
              <p className="text-sm text-[#173642]/80">{client.taxId}</p>
              <p className="mt-3 text-xs uppercase tracking-[0.18em] text-[#24513f]">
                {client.filingPeriodsCount} períodos
              </p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}

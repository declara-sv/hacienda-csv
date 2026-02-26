import { Link, Navigate, createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useAuth } from '#/auth/AuthContext'
import { ApiError, clientsApi } from '#/lib/api-client'

export const Route = createFileRoute('/clientes/$clientId')({
  component: ClientDetailPage,
})

function ClientDetailPage() {
  const { clientId } = Route.useParams()
  const { session } = useAuth()
  const queryClient = useQueryClient()

  const now = useMemo(() => new Date(), [])
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const [configName, setConfigName] = useState('Base')
  const [prefill, setPrefill] = useState('{\n  "actividad": "SERVICIOS"\n}')
  const [rules, setRules] = useState('{\n  "nota": "placeholder para reglas futuras"\n}')
  const [error, setError] = useState<string | null>(null)

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => clientsApi.get(clientId),
    enabled: Boolean(session),
  })

  const createPeriodMutation = useMutation({
    mutationFn: () => clientsApi.createPeriod(clientId, { year, month }),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['client', clientId] })
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'No se pudo crear el período.')
    },
  })

  const createConfigMutation = useMutation({
    mutationFn: () =>
      clientsApi.createConfig(clientId, {
        name: configName,
        prefillValuesJson: prefill,
        transformationRulesJson: rules,
        isActive: true,
      }),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['client', clientId] })
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar la configuración.')
    },
  })

  if (!session) {
    return <Navigate to="/login" />
  }

  return (
    <div className="space-y-6">
      <Link to="/clientes" className="text-sm font-semibold text-[#24513f] hover:underline">
        ← Volver al listado de clientes
      </Link>

      {clientQuery.isLoading ? <p>Cargando cliente...</p> : null}

      {clientQuery.data ? (
        <>
          <section className="rounded-3xl border border-[#173642]/15 bg-white/80 p-6 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)]">
            <h1 className="font-title text-4xl text-[#173642]">{clientQuery.data.name}</h1>
            <p className="mt-2 text-sm text-[#173642]/80">{clientQuery.data.taxId}</p>
            {clientQuery.data.notes ? <p className="mt-3 text-sm text-[#173642]/80">{clientQuery.data.notes}</p> : null}
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <article className="rounded-3xl border border-[#173642]/15 bg-white/80 p-6 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)]">
              <h2 className="font-title text-3xl text-[#173642]">Períodos fiscales</h2>

              <form
                className="mt-4 grid grid-cols-2 gap-3"
                onSubmit={(event) => {
                  event.preventDefault()
                  createPeriodMutation.mutate()
                }}
              >
                <label className="text-sm font-semibold text-[#173642]">
                  Año
                  <input
                    type="number"
                    min={2000}
                    max={2100}
                    className="mt-1 w-full rounded-xl border border-[#173642]/20 px-3 py-2"
                    value={year}
                    onChange={(event) => setYear(Number(event.target.value))}
                  />
                </label>
                <label className="text-sm font-semibold text-[#173642]">
                  Mes
                  <input
                    type="number"
                    min={1}
                    max={12}
                    className="mt-1 w-full rounded-xl border border-[#173642]/20 px-3 py-2"
                    value={month}
                    onChange={(event) => setMonth(Number(event.target.value))}
                  />
                </label>
                <button
                  type="submit"
                  className="col-span-2 rounded-xl bg-[#24513f] px-4 py-2 font-semibold text-white"
                  disabled={createPeriodMutation.isPending}
                >
                  {createPeriodMutation.isPending ? 'Guardando...' : 'Agregar período'}
                </button>
              </form>

              <div className="mt-4 space-y-3">
                {clientQuery.data.filingPeriods.map((period) => (
                  <Link
                    key={period.id}
                    to="/clientes/$clientId/periodos/$periodId/cargas"
                    params={{ clientId, periodId: period.id }}
                    className="block rounded-xl border border-[#173642]/15 bg-[#fcfbf7] px-4 py-3 hover:border-[#24513f]"
                  >
                    <p className="font-semibold text-[#173642]">
                      {period.year} / {String(period.month).padStart(2, '0')}
                    </p>
                    <p className="text-xs text-[#173642]/65">Gestionar cargas y resultados CSV</p>
                  </Link>
                ))}
              </div>
            </article>

            <article className="rounded-3xl border border-[#173642]/15 bg-white/80 p-6 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)]">
              <h2 className="font-title text-3xl text-[#173642]">Configuraciones</h2>

              <form
                className="mt-4 space-y-3"
                onSubmit={(event) => {
                  event.preventDefault()
                  createConfigMutation.mutate()
                }}
              >
                <label className="block text-sm font-semibold text-[#173642]">
                  Nombre
                  <input
                    className="mt-1 w-full rounded-xl border border-[#173642]/20 px-3 py-2"
                    value={configName}
                    onChange={(event) => setConfigName(event.target.value)}
                    maxLength={80}
                  />
                </label>

                <label className="block text-sm font-semibold text-[#173642]">
                  Prefill JSON
                  <textarea
                    className="mt-1 min-h-24 w-full rounded-xl border border-[#173642]/20 px-3 py-2 font-mono text-sm"
                    value={prefill}
                    onChange={(event) => setPrefill(event.target.value)}
                  />
                </label>

                <label className="block text-sm font-semibold text-[#173642]">
                  Reglas JSON (futuro)
                  <textarea
                    className="mt-1 min-h-24 w-full rounded-xl border border-[#173642]/20 px-3 py-2 font-mono text-sm"
                    value={rules}
                    onChange={(event) => setRules(event.target.value)}
                  />
                </label>

                <button
                  type="submit"
                  className="w-full rounded-xl bg-[#24513f] px-4 py-2 font-semibold text-white"
                  disabled={createConfigMutation.isPending}
                >
                  {createConfigMutation.isPending ? 'Guardando...' : 'Guardar configuración activa'}
                </button>
              </form>

              <div className="mt-4 space-y-2">
                {clientQuery.data.configurations.map((config) => (
                  <div key={config.id} className="rounded-xl border border-[#173642]/15 bg-[#fcfbf7] px-4 py-3">
                    <p className="font-semibold text-[#173642]">{config.name}</p>
                    <p className="text-xs text-[#173642]/70">Actualizada: {new Date(config.updatedAtUtc).toLocaleString('es-SV')}</p>
                    {config.isActive ? <p className="mt-1 text-xs font-semibold uppercase tracking-[0.18em] text-[#24513f]">Activa</p> : null}
                  </div>
                ))}
              </div>
            </article>
          </section>

          {error ? <p className="rounded-lg bg-red-100 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        </>
      ) : null}
    </div>
  )
}

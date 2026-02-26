import { Link, Navigate, createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useAuth } from '#/auth/AuthContext'
import { ApiError, uploadsApi } from '#/lib/api-client'
import type { ParseJobStatus } from '#/lib/api-types'

export const Route = createFileRoute('/clientes/$clientId/periodos/$periodId/cargas')({
  component: UploadsPage,
})

const statusLabel: Record<ParseJobStatus, string> = {
  Pending: 'Pendiente',
  Running: 'Procesando',
  Failed: 'Fallido',
  Completed: 'Completado',
}

function UploadsPage() {
  const { clientId, periodId } = Route.useParams()
  const { session } = useAuth()
  const queryClient = useQueryClient()

  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState<'Excel' | 'PDF'>('Excel')
  const [error, setError] = useState<string | null>(null)

  const uploadsQuery = useQuery({
    queryKey: ['uploads', clientId, periodId],
    queryFn: () => uploadsApi.list(clientId, periodId),
    enabled: Boolean(session),
    refetchInterval: 5000,
  })

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) {
        throw new Error('Selecciona un archivo.')
      }

      return uploadsApi.create(clientId, periodId, {
        file,
        sourceFileKind: kind,
      })
    },
    onSuccess: () => {
      setFile(null)
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['uploads', clientId, periodId] })
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'No se pudo subir el archivo.')
    },
  })

  if (!session) {
    return <Navigate to="/login" />
  }

  return (
    <div className="space-y-6">
      <Link to="/clientes/$clientId" params={{ clientId }} className="text-sm font-semibold text-[#24513f] hover:underline">
        ← Volver al cliente
      </Link>

      <section className="rounded-3xl border border-[#173642]/15 bg-white/80 p-6 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)]">
        <h1 className="font-title text-4xl text-[#173642]">Carga de documentos</h1>
        <p className="mt-2 text-sm text-[#173642]/70">Sube Excel o PDF para iniciar un ParseJob placeholder y generar CSV.</p>

        <form
          className="mt-5 grid gap-3 md:grid-cols-[1fr_160px_auto]"
          onSubmit={(event) => {
            event.preventDefault()
            uploadMutation.mutate()
          }}
        >
          <input
            type="file"
            className="rounded-xl border border-[#173642]/20 bg-white px-3 py-2"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            accept={kind === 'Excel' ? '.xls,.xlsx' : '.pdf'}
          />

          <select
            className="rounded-xl border border-[#173642]/20 bg-white px-3 py-2"
            value={kind}
            onChange={(event) => setKind(event.target.value as 'Excel' | 'PDF')}
          >
            <option value="Excel">Excel</option>
            <option value="PDF">PDF</option>
          </select>

          <button
            type="submit"
            className="rounded-xl bg-[#24513f] px-4 py-2 font-semibold text-white disabled:opacity-60"
            disabled={uploadMutation.isPending || !file}
          >
            {uploadMutation.isPending ? 'Subiendo...' : 'Subir'}
          </button>
        </form>

        {error ? <p className="mt-3 rounded-lg bg-red-100 px-3 py-2 text-sm text-red-700">{error}</p> : null}
      </section>

      <section className="rounded-3xl border border-[#173642]/15 bg-white/80 p-6 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)]">
        <h2 className="font-title text-3xl text-[#173642]">Historial de cargas y jobs</h2>

        {uploadsQuery.isLoading ? <p className="mt-4">Cargando historial...</p> : null}

        <div className="mt-4 space-y-4">
          {uploadsQuery.data?.map((upload) => (
            <article key={upload.id} className="rounded-2xl border border-[#173642]/15 bg-[#fcfbf7] p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-semibold text-[#173642]">{upload.originalFileName}</p>
                  <p className="text-xs text-[#173642]/70">
                    {upload.sourceFileKind} · {Math.round(upload.sizeBytes / 1024)} KB · {new Date(upload.createdAtUtc).toLocaleString('es-SV')}
                  </p>
                </div>
              </div>

              <div className="mt-3 space-y-2">
                {upload.jobs.map((job) => (
                  <div key={job.id} className="rounded-xl border border-[#173642]/15 bg-white px-3 py-2">
                    <p className="text-sm font-semibold text-[#173642]">Job: {statusLabel[job.status]}</p>
                    {job.errorMessage ? <p className="text-xs text-red-700">{job.errorMessage}</p> : null}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {job.artifacts.map((artifact) => (
                        <button
                          key={artifact.id}
                          type="button"
                          className="rounded-full border border-[#24513f]/35 px-3 py-1 text-xs font-semibold text-[#24513f] hover:bg-[#24513f]/10"
                          onClick={() => uploadsApi.downloadArtifact(artifact.id, artifact.fileName)}
                        >
                          Descargar CSV ({artifact.fileName})
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

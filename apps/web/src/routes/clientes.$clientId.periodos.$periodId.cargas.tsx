import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { PeriodDocuments } from '#/components/uploads/PeriodDocuments'
import { Breadcrumb } from '#/components/ui/Breadcrumb'
import { PageHeader } from '#/components/ui/PageHeader'
import { useI18n } from '#/i18n/I18nProvider'
import { clientsApi } from '#/lib/api-client'
import { formatPeriod } from '#/lib/format'

export const Route = createFileRoute(
  '/clientes/$clientId/periodos/$periodId/cargas',
)({
  head: () => ({ meta: [{ title: 'Carga de documentos | HaciendaCSV' }] }),
  component: UploadsPage,
})

function UploadsPage() {
  const { clientId, periodId } = Route.useParams()
  const { t } = useI18n()

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => clientsApi.get(clientId),
  })
  const client = clientQuery.data
  const period = client?.filingPeriods.find((p) => p.id === periodId)
  const periodLabel = period ? formatPeriod(period.year, period.month) : null

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

      {/* Keyed so the local upload queue and notices never cross periods. */}
      <PeriodDocuments
        key={`${clientId}:${periodId}`}
        clientId={clientId}
        periodId={periodId}
      />
    </div>
  )
}

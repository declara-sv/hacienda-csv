import { Link, createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { RentaDefaultsHint } from '#/components/clients/RentaDefaultsHint'
import { PeriodDocuments } from '#/components/uploads/PeriodDocuments'
import { buttonClasses } from '#/components/ui/Button'
import { Breadcrumb } from '#/components/ui/Breadcrumb'
import { PageHeader } from '#/components/ui/PageHeader'
import { useI18n } from '#/i18n/I18nProvider'
import { clientsApi } from '#/lib/api-client'
import { formatPeriod } from '#/lib/format'

export const Route = createFileRoute(
  '/clients/$clientId/periods/$periodId/uploads',
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
          { label: t('menuClients'), to: '/clients' },
          {
            label: client ? client.name : null,
            to: '/clients/$clientId',
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

      {client ? (
        <RentaDefaultsHint
          client={client}
          action={
            <Link
              to="/clients/$clientId"
              params={{ clientId }}
              className={buttonClasses('secondary', 'sm')}
            >
              {t('rentaRequiredAction')}
            </Link>
          }
        />
      ) : null}

      {/* Keyed so the local upload queue and notices never cross periods. */}
      <PeriodDocuments
        key={`${clientId}:${periodId}`}
        clientId={clientId}
        periodId={periodId}
        clientDefaults={
          client
            ? {
                tipoOperacion: client.defaultTipoOperacion,
                tipoIngreso: client.defaultTipoIngreso,
              }
            : null
        }
      />
    </div>
  )
}

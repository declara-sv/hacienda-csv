import { Notice } from '#/components/ui/Notice'
import { useI18n } from '#/i18n/I18nProvider'
import type { ClientDetail } from '#/lib/api-types'
import type { ReactNode } from 'react'

export function missingRentaDefaults(
  client: Pick<ClientDetail, 'defaultTipoOperacion' | 'defaultTipoIngreso'>,
) {
  return !client.defaultTipoOperacion || !client.defaultTipoIngreso
}

/** Shown while a client lacks the Renta codes every 2025+ anexo row needs. */
export function RentaDefaultsHint({
  client,
  action,
}: {
  client: Pick<ClientDetail, 'defaultTipoOperacion' | 'defaultTipoIngreso'>
  action?: ReactNode
}) {
  const { t } = useI18n()
  if (!missingRentaDefaults(client)) return null
  return (
    <Notice variant="warning">
      <p className="font-semibold">{t('rentaRequiredTitle')}</p>
      <p className="mt-0.5">{t('rentaRequiredBody')}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </Notice>
  )
}

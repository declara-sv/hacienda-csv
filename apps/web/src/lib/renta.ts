import { useQuery } from '@tanstack/react-query'
import { catalogsApi } from './api-client'
import type { RentaCatalogEntry } from './api-types'

export const rentaCatalogKey = ['catalogs', 'renta'] as const

/** The Renta catalog changes with the law, not with the session. */
export function useRentaCatalog() {
  return useQuery({
    queryKey: rentaCatalogKey,
    queryFn: catalogsApi.renta,
    staleTime: Infinity,
  })
}

export function rentaOptionLabel(entry: RentaCatalogEntry) {
  return `${entry.code} – ${entry.label}`
}

/** "code – label" when the code is in the catalog, the bare code otherwise. */
export function rentaLabel(
  entries: readonly RentaCatalogEntry[] | undefined,
  code: string | null | undefined,
) {
  if (!code) return ''
  const entry = entries?.find((item) => item.code === code)
  return entry ? rentaOptionLabel(entry) : code
}

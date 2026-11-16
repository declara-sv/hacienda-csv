import { toCents } from './format'
import type { DocumentDto, DocumentStatus } from './api-types'

/** Short names of DTE types (catálogo CAT-002 del MH). */
export const DTE_TYPE_NAMES: Record<string, string> = {
  '01': 'Factura',
  '03': 'CCF',
  '04': 'Nota de remisión',
  '05': 'NC',
  '06': 'ND',
  '07': 'Comprobante de retención',
  '08': 'Comprobante de liquidación',
  '09': 'Documento contable de liquidación',
  '11': 'Factura de exportación',
  '14': 'Sujeto excluido',
  '15': 'Comprobante de donación',
}

/** Types that the review form offers; others stay selectable if present. */
export const SALES_DTE_TYPES = ['01', '03', '05', '06'] as const

export function dteTypeLabel(code: string) {
  const name = DTE_TYPE_NAMES[code]
  return name ? `${code} ${name}` : code
}

/** Errors on excluded documents do not block generation. */
export function isBlocking(document: DocumentDto) {
  return !document.excluded && document.status === 'Error'
}

export function documentReference(document: DocumentDto) {
  return (
    document.numeroControl ??
    document.codigoGeneracion ??
    document.originalFileName
  )
}

export type AnexoSummary = { count: number; totalCents: number }

export type ReviewSummary = {
  anexo1: AnexoSummary
  anexo2: AnexoSummary
  /** Included documents that no sales anexo takes (04, 07, 11, ...). */
  withoutAnexo: number
  excluded: number
  included: number
  blockingErrors: number
  warnings: number
}

export function summarizeDocuments(
  documents: readonly DocumentDto[],
): ReviewSummary {
  const summary: ReviewSummary = {
    anexo1: { count: 0, totalCents: 0 },
    anexo2: { count: 0, totalCents: 0 },
    withoutAnexo: 0,
    excluded: 0,
    included: 0,
    blockingErrors: 0,
    warnings: 0,
  }
  for (const document of documents) {
    if (document.excluded) {
      summary.excluded += 1
      continue
    }
    summary.included += 1
    if (document.status === 'Error') summary.blockingErrors += 1
    if (document.status === 'Warning') summary.warnings += 1
    const bucket =
      document.anexo === 1
        ? summary.anexo1
        : document.anexo === 2
          ? summary.anexo2
          : null
    if (!bucket) {
      summary.withoutAnexo += 1
      continue
    }
    bucket.count += 1
    bucket.totalCents += toCents(document.total)
  }
  return summary
}

export type StatusFilter = 'all' | DocumentStatus
export type AnexoFilter = 'all' | '1' | '2' | 'none'

export function filterDocuments(
  documents: readonly DocumentDto[],
  status: StatusFilter,
  anexo: AnexoFilter,
) {
  return documents.filter(
    (document) =>
      (status === 'all' || document.status === status) &&
      (anexo === 'all' ||
        (anexo === 'none'
          ? document.anexo === null
          : document.anexo === Number(anexo))),
  )
}

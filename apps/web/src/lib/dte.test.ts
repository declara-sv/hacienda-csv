import { describe, expect, it } from 'vitest'
import {
  dteTypeLabel,
  filterDocuments,
  isBlocking,
  summarizeDocuments,
} from './dte'
import { documentDto } from '#/test/fixtures'

describe('dteTypeLabel', () => {
  it('names the sales DTE types', () => {
    expect(dteTypeLabel('01')).toBe('01 Factura')
    expect(dteTypeLabel('03')).toBe('03 CCF')
    expect(dteTypeLabel('05')).toBe('05 NC')
    expect(dteTypeLabel('06')).toBe('06 ND')
    expect(dteTypeLabel('99')).toBe('99')
  })
})

describe('summarizeDocuments', () => {
  const documents = [
    documentDto('1', { anexo: 2, total: '10.10' }),
    documentDto('2', { anexo: 2, total: '0.20' }),
    documentDto('3', { anexo: 1, total: '113.00', status: 'Warning' }),
    documentDto('4', { anexo: 1, total: '50.00', status: 'Error' }),
    documentDto('5', {
      anexo: 1,
      total: '99.00',
      excluded: true,
      status: 'Error',
    }),
    documentDto('6', { anexo: null, tipoDte: '07' }),
  ]

  it('counts and totals included documents per anexo in exact cents', () => {
    const summary = summarizeDocuments(documents)
    expect(summary.anexo2).toEqual({ count: 2, totalCents: 1030 })
    expect(summary.anexo1).toEqual({ count: 2, totalCents: 16300 })
    expect(summary.withoutAnexo).toBe(1)
    expect(summary.excluded).toBe(1)
    expect(summary.included).toBe(5)
    expect(summary.warnings).toBe(1)
  })

  it('ignores errors on excluded documents', () => {
    expect(summarizeDocuments(documents).blockingErrors).toBe(1)
    expect(isBlocking(documents[3])).toBe(true)
    expect(isBlocking(documents[4])).toBe(false)
  })
})

describe('filterDocuments', () => {
  const documents = [
    documentDto('1', { anexo: 2 }),
    documentDto('2', { anexo: 1, status: 'Error' }),
    documentDto('3', { anexo: null, status: 'Warning' }),
  ]
  const ids = (items: { id: string }[]) => items.map((item) => item.id)

  it('filters by status and anexo together', () => {
    expect(ids(filterDocuments(documents, 'all', 'all'))).toEqual([
      '1',
      '2',
      '3',
    ])
    expect(ids(filterDocuments(documents, 'Error', 'all'))).toEqual(['2'])
    expect(ids(filterDocuments(documents, 'all', '2'))).toEqual(['1'])
    expect(ids(filterDocuments(documents, 'all', 'none'))).toEqual(['3'])
    expect(ids(filterDocuments(documents, 'Ok', '1'))).toEqual([])
  })
})

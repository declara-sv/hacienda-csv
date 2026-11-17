import { describe, expect, it } from 'vitest'
import {
  detectSourceFileKind,
  formatBytes,
  formatIsoDate,
  formatMoney,
  formatPeriod,
  pluralize,
  previousMonth,
  toCents,
} from './format'

describe('formatPeriod', () => {
  it('names the month in Spanish', () => {
    expect(formatPeriod(2026, 3)).toBe('Marzo 2026')
    expect(formatPeriod(2025, 12)).toBe('Diciembre 2025')
  })

  it('falls back to a zero-padded number for an unknown month', () => {
    expect(formatPeriod(2026, 13)).toBe('13 2026')
    expect(formatPeriod(2026, 0)).toBe('00 2026')
  })
})

describe('formatBytes', () => {
  it('picks the right unit', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2 KB')
    expect(formatBytes(3.5 * 1024 * 1024)).toBe('3.5 MB')
    expect(formatBytes(42 * 1024 * 1024)).toBe('42 MB')
  })

  it('handles bad input', () => {
    expect(formatBytes(-1)).toBe('0 B')
    expect(formatBytes(Number.NaN)).toBe('0 B')
  })
})

describe('detectSourceFileKind', () => {
  it('detects PDF by extension, case-insensitive', () => {
    expect(detectSourceFileKind('factura.PDF')).toBe('PDF')
    expect(detectSourceFileKind('factura.pdf')).toBe('PDF')
  })

  it('rejects Excel, which the API cannot read yet', () => {
    expect(detectSourceFileKind('ventas.xlsx')).toBeNull()
    expect(detectSourceFileKind('VENTAS.XLS')).toBeNull()
  })

  it('returns null for anything else', () => {
    expect(detectSourceFileKind('notas.csv')).toBeNull()
    expect(detectSourceFileKind('sin-extension')).toBeNull()
  })
})

describe('pluralize', () => {
  it('uses singular only for exactly one', () => {
    expect(pluralize(1, 'período', 'períodos')).toBe('1 período')
    expect(pluralize(0, 'período', 'períodos')).toBe('0 períodos')
    expect(pluralize(4, 'período', 'períodos')).toBe('4 períodos')
  })
})

describe('money', () => {
  it('turns decimal strings into exact cents', () => {
    expect(toCents('48.14')).toBe(4814)
    expect(toCents('0.1')).toBe(10)
    expect(toCents('12')).toBe(1200)
    expect(toCents('-3.50')).toBe(-350)
    expect(toCents('')).toBe(0)
    expect(toCents(null)).toBe(0)
    expect(toCents('abc')).toBe(0)
    // Summing cents avoids 0.1 + 0.2 drift.
    expect(toCents('0.10') + toCents('0.20')).toBe(30)
  })

  it('formats dollars with two decimals', () => {
    expect(formatMoney('48.14')).toMatch(/48[.,]14/)
    expect(formatMoney('48.14')).toContain('$')
    expect(formatMoney('1234.5')).toMatch(/1[,.\s]?234[.,]50/)
  })
})

describe('formatIsoDate', () => {
  it('shows ISO dates as DD/MM/YYYY without time-zone shifts', () => {
    expect(formatIsoDate('2025-10-01')).toBe('01/10/2025')
    expect(formatIsoDate(null)).toBe('')
    expect(formatIsoDate('otra')).toBe('otra')
  })
})

describe('previousMonth', () => {
  it('suggests the month before today', () => {
    expect(previousMonth(new Date(2026, 10, 17))).toEqual({
      year: 2026,
      month: 10,
    })
  })

  it('wraps January back to December of the previous year', () => {
    expect(previousMonth(new Date(2027, 0, 5))).toEqual({
      year: 2026,
      month: 12,
    })
  })
})

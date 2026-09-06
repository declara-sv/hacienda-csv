import { describe, expect, it } from 'vitest'
import {
  detectSourceFileKind,
  formatBytes,
  formatPeriod,
  pluralize,
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
  it('detects Excel and PDF by extension, case-insensitive', () => {
    expect(detectSourceFileKind('ventas.xlsx')).toBe('Excel')
    expect(detectSourceFileKind('VENTAS.XLS')).toBe('Excel')
    expect(detectSourceFileKind('factura.PDF')).toBe('PDF')
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

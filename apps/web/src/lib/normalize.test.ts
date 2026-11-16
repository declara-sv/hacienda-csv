import { describe, expect, it } from 'vitest'
import {
  normalizeDocument,
  normalizeExtractionStatus,
  normalizeRun,
  normalizeRunFileStatus,
  normalizeRunStatus,
} from './normalize'
import { documentDto } from '#/test/fixtures'

describe('generation status normalization', () => {
  it.each([
    [1, 'Pending'],
    [2, 'Running'],
    [3, 'Completed'],
    [4, 'Failed'],
    ['Pending', 'Pending'],
    ['running', 'Running'],
    ['Completed', 'Completed'],
    ['Failed', 'Failed'],
    ['3', 'Completed'],
  ])('normalizes run status %s', (input, expected) => {
    expect(normalizeRunStatus(input)).toBe(expected)
  })

  it.each([
    [1, 'Pending'],
    [2, 'Included'],
    [3, 'Failed'],
    ['Pending', 'Pending'],
    ['included', 'Included'],
    ['Failed', 'Failed'],
    ['2', 'Included'],
  ])('normalizes file status %s', (input, expected) => {
    expect(normalizeRunFileStatus(input)).toBe(expected)
  })

  it.each([99, 'unknown', null, undefined, '', 'toString', {}, true])(
    'rejects unknown status %s rather than treating it as pending',
    (input) => {
      expect(() => normalizeRunStatus(input)).toThrow(
        /Unknown generation .*status/,
      )
      expect(() => normalizeRunFileStatus(input)).toThrow(
        /Unknown generation .*status/,
      )
    },
  )

  it('normalizes run and nested file statuses while preserving historical files', () => {
    const run = {
      id: 'r1',
      filingPeriodId: 'p1',
      version: 1,
      status: 3,
      errorMessage: null,
      createdAtUtc: '2026-09-06T00:00:00Z',
      startedAtUtc: null,
      completedAtUtc: null,
      artifacts: [],
      files: [
        {
          uploadId: null,
          originalFileName: 'ventas.xlsx',
          sourceFileKind: 'Excel' as const,
          status: 2,
          errorMessage: null,
        },
      ],
    }
    expect(normalizeRun(run)).toEqual({
      ...run,
      status: 'Completed',
      files: [{ ...run.files[0], status: 'Included' }],
      issues: [],
    })
  })
})

describe('extraction and document normalization', () => {
  it.each([
    ['Running', 'Running'],
    ['failed', 'Failed'],
    [3, 'Completed'],
    [undefined, 'Completed'],
    [null, 'Completed'],
  ])('normalizes extraction status %s', (input, expected) => {
    expect(normalizeExtractionStatus(input)).toBe(expected)
  })

  it('rejects an unknown extraction status', () => {
    expect(() => normalizeExtractionStatus('Queued')).toThrow(
      /Unknown generation extraction status/,
    )
  })

  it('derives a missing document status from its issues', () => {
    const { status: _status, ...raw } = documentDto('d1', {
      issues: [
        { code: 'iva', severity: 'Warning', message: 'IVA', field: 'iva' },
        { code: 'dup', severity: 'Error', message: 'Repetido', field: null },
      ],
    })
    expect(normalizeDocument(raw).status).toBe('Error')
    expect(normalizeDocument({ ...raw, issues: [raw.issues[0]] }).status).toBe(
      'Warning',
    )
    expect(normalizeDocument({ ...raw, issues: undefined }).status).toBe('Ok')
  })

  it('keeps the server status and coerces anexo numbers', () => {
    const raw = documentDto('d1', { status: 'Warning' })
    expect(normalizeDocument({ ...raw, anexo: '1' }).anexo).toBe(1)
    expect(normalizeDocument({ ...raw, anexo: null }).anexo).toBeNull()
    expect(normalizeDocument({ ...raw, anexo: 3 }).anexo).toBeNull()
    expect(normalizeDocument(raw).status).toBe('Warning')
  })
})

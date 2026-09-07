import { describe, expect, it } from 'vitest'
import {
  normalizeRun,
  normalizeRunFileStatus,
  normalizeRunStatus,
} from './normalize'

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
    })
  })
})

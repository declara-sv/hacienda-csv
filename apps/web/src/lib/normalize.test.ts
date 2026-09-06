import { describe, expect, it } from 'vitest'
import { normalizeJobStatus, normalizeUpload } from './normalize'
import type { Upload } from './api-types'

describe('normalizeJobStatus', () => {
  it('maps the numeric enum the API sends', () => {
    expect(normalizeJobStatus(1)).toBe('Pending')
    expect(normalizeJobStatus(2)).toBe('Running')
    expect(normalizeJobStatus(3)).toBe('Failed')
    expect(normalizeJobStatus(4)).toBe('Completed')
  })

  it('accepts string names in any case and numeric strings', () => {
    expect(normalizeJobStatus('Completed')).toBe('Completed')
    expect(normalizeJobStatus('failed')).toBe('Failed')
    expect(normalizeJobStatus('2')).toBe('Running')
  })

  it('falls back to Pending for anything unknown', () => {
    expect(normalizeJobStatus(99)).toBe('Pending')
    expect(normalizeJobStatus('weird')).toBe('Pending')
    expect(normalizeJobStatus(null)).toBe('Pending')
    expect(normalizeJobStatus(undefined)).toBe('Pending')
  })
})

describe('normalizeUpload', () => {
  it('normalizes every job status inside an upload', () => {
    const upload = {
      id: 'u1',
      filingPeriodId: 'p1',
      originalFileName: 'ventas.xlsx',
      sourceFileKind: 'Excel',
      contentType: 'application/octet-stream',
      sizeBytes: 10,
      createdAtUtc: '2026-09-06T00:00:00Z',
      jobs: [
        {
          id: 'j1',
          status: 4 as unknown as 'Completed',
          errorMessage: null,
          createdAtUtc: '2026-09-06T00:00:00Z',
          startedAtUtc: null,
          completedAtUtc: null,
          artifacts: [],
        },
      ],
    } satisfies Upload

    expect(normalizeUpload(upload).jobs[0].status).toBe('Completed')
  })
})

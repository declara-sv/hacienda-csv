import type {
  GenerationRun,
  GenerationRunFile,
  GenerationRunFileStatus,
  GenerationRunStatus,
} from './api-types'

// Enum values match GenerationRunStatus and GenerationRunFileStatus in the API.
const runStatuses: GenerationRunStatus[] = [
  'Pending',
  'Running',
  'Completed',
  'Failed',
]
const fileStatuses: GenerationRunFileStatus[] = [
  'Pending',
  'Included',
  'Failed',
]

function normalizeStatus<T extends string>(
  value: unknown,
  statuses: T[],
  label: string,
): T {
  const match = statuses.find((status, index) =>
    typeof value === 'number'
      ? value === index + 1
      : typeof value === 'string' &&
        (value.toLowerCase() === status.toLowerCase() ||
          value === String(index + 1)),
  )
  if (!match) {
    throw new Error(`Unknown generation ${label} status: ${String(value)}`)
  }
  return match
}

export function normalizeRunStatus(value: unknown): GenerationRunStatus {
  return normalizeStatus(value, runStatuses, 'run')
}

export function normalizeRunFileStatus(
  value: unknown,
): GenerationRunFileStatus {
  return normalizeStatus(value, fileStatuses, 'file')
}

type RawGenerationRun = Omit<GenerationRun, 'status' | 'files'> & {
  status: unknown
  files: Array<Omit<GenerationRunFile, 'status'> & { status: unknown }>
}

export function normalizeRun(run: RawGenerationRun): GenerationRun {
  return {
    ...run,
    status: normalizeRunStatus(run.status),
    files: run.files.map((file) => ({
      ...file,
      status: normalizeRunFileStatus(file.status),
    })),
  }
}

import type {
  ParseJob,
  ParseJobStatus,
  Upload,
  UploadCreated,
} from './api-types'

/*
  The API serializes the ParseJobStatus enum as a number
  (Pending = 1, Running = 2, Failed = 3, Completed = 4). Older responses and
  fixtures may use the string names. Normalize both to the string union the
  UI works with.
*/
const byNumber: Record<number, ParseJobStatus> = {
  1: 'Pending',
  2: 'Running',
  3: 'Failed',
  4: 'Completed',
}

const byName: Record<string, ParseJobStatus> = {
  pending: 'Pending',
  running: 'Running',
  failed: 'Failed',
  completed: 'Completed',
}

export function normalizeJobStatus(value: unknown): ParseJobStatus {
  if (typeof value === 'number') {
    return byNumber[value] ?? 'Pending'
  }
  if (typeof value === 'string') {
    const asNumber = Number(value)
    if (!Number.isNaN(asNumber) && value.trim() !== '') {
      return byNumber[asNumber] ?? 'Pending'
    }
    return byName[value.toLowerCase()] ?? 'Pending'
  }
  return 'Pending'
}

export function normalizeJob(job: ParseJob): ParseJob {
  return { ...job, status: normalizeJobStatus(job.status) }
}

export function normalizeUpload(upload: Upload): Upload {
  return { ...upload, jobs: upload.jobs.map(normalizeJob) }
}

export function normalizeUploadCreated(created: UploadCreated): UploadCreated {
  return { ...created, status: normalizeJobStatus(created.status) }
}

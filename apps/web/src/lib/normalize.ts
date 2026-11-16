import type {
  DocumentDto,
  DocumentMoneyField,
  DocumentStatus,
  ExtractionStatus,
  GenerationRun,
  GenerationRunFile,
  GenerationRunFileStatus,
  GenerationRunStatus,
  Issue,
  IssueSeverity,
  Upload,
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

const extractionStatuses: ExtractionStatus[] = [
  'Pending',
  'Running',
  'Completed',
  'Failed',
]
const severities: IssueSeverity[] = ['Warning', 'Error']

export function normalizeExtractionStatus(value: unknown): ExtractionStatus {
  // Uploads stored before extraction existed carry no status: nothing to wait on.
  if (value === undefined || value === null) return 'Completed'
  return normalizeStatus(value, extractionStatuses, 'extraction')
}

function normalizeIssues(value: unknown): Issue[] {
  if (!Array.isArray(value)) return []
  return value.map((raw: Partial<Issue> & { severity?: unknown }) => {
    const severity =
      severities.find(
        (item) =>
          typeof raw.severity === 'string' &&
          item.toLowerCase() === raw.severity.toLowerCase(),
      ) ?? 'Error'
    return {
      code: String(raw.code ?? ''),
      severity,
      message: String(raw.message ?? ''),
      field: raw.field ?? null,
    }
  })
}

export function statusFromIssues(issues: readonly Issue[]): DocumentStatus {
  if (issues.some((issue) => issue.severity === 'Error')) return 'Error'
  if (issues.some((issue) => issue.severity === 'Warning')) return 'Warning'
  return 'Ok'
}

type RawGenerationRun = Omit<GenerationRun, 'status' | 'files' | 'issues'> & {
  status: unknown
  files?: Array<Omit<GenerationRunFile, 'status'> & { status: unknown }>
  issues?: unknown
}

export function normalizeRun(run: RawGenerationRun): GenerationRun {
  return {
    ...run,
    status: normalizeRunStatus(run.status),
    files: (run.files ?? []).map((file) => ({
      ...file,
      status: normalizeRunFileStatus(file.status),
    })),
    issues: normalizeIssues(run.issues),
  }
}

type RawUpload = Omit<
  Upload,
  'extractionStatus' | 'extractionError' | 'documentsCount'
> & {
  extractionStatus?: unknown
  extractionError?: string | null
  documentsCount?: number | null
}

export function normalizeUpload(upload: RawUpload): Upload {
  return {
    ...upload,
    extractionStatus: normalizeExtractionStatus(upload.extractionStatus),
    extractionError: upload.extractionError ?? null,
    documentsCount: upload.documentsCount ?? 0,
  }
}

const moneyFields: DocumentMoneyField[] = [
  'totalNoSujetas',
  'totalExentas',
  'totalGravadas',
  'iva',
  'ivaRetenido',
  'total',
]
const documentStatuses: DocumentStatus[] = ['Ok', 'Warning', 'Error']

type RawDocument = Omit<
  DocumentDto,
  DocumentMoneyField | 'issues' | 'status' | 'anexo'
> &
  Partial<Record<DocumentMoneyField, string | number | null>> & {
    issues?: unknown
    status?: unknown
    anexo?: unknown
  }

function normalizeMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '0.00'
  return typeof value === 'number' ? value.toFixed(2) : value
}

export function normalizeDocument(raw: RawDocument): DocumentDto {
  const issues = normalizeIssues(raw.issues)
  const status =
    documentStatuses.find(
      (item) =>
        typeof raw.status === 'string' &&
        item.toLowerCase() === raw.status.toLowerCase(),
    ) ?? statusFromIssues(issues)
  const anexo = Number(raw.anexo)
  const money = Object.fromEntries(
    moneyFields.map((field) => [field, normalizeMoney(raw[field])]),
  ) as Record<DocumentMoneyField, string>
  return {
    ...raw,
    ...money,
    issues,
    status,
    anexo: anexo === 1 || anexo === 2 ? anexo : null,
  }
}

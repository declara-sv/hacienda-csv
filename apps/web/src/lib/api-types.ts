export type GenerationRunStatus = 'Pending' | 'Running' | 'Completed' | 'Failed'
export type GenerationRunFileStatus = 'Pending' | 'Included' | 'Failed'
export type ExtractionStatus = 'Pending' | 'Running' | 'Completed' | 'Failed'

export type AuthUser = {
  id: string
  email: string
  fullName: string
}

export type AuthSession = {
  accessToken: string
  accessTokenExpiresAtUtc: string
  refreshToken: string
  user: AuthUser
}

export type ClientSummary = {
  id: string
  name: string
  taxId: string
  filingPeriodsCount: number
  createdAtUtc: string
}

export type ClientConfig = {
  id: string
  name: string
  prefillValuesJson: string
  transformationRulesJson: string | null
  isActive: boolean
  updatedAtUtc: string
}

export type FilingPeriodSummary = {
  id: string
  year: number
  month: number
  createdAtUtc: string
}

export type ClientDetail = {
  id: string
  name: string
  taxId: string
  notes: string | null
  nit: string | null
  nrc: string | null
  defaultTipoOperacion: string | null
  defaultTipoIngreso: string | null
  createdAtUtc: string
  configurations: ClientConfig[]
  filingPeriods: FilingPeriodSummary[]
}

export type Artifact = {
  id: string
  artifactKind: string
  fileName: string
  createdAtUtc: string
  sizeBytes: number
  /** Rows written to the CSV; absent on artifacts from older runs. */
  rowCount?: number | null
}

export type GenerationRunFile = {
  uploadId: string | null
  originalFileName: string
  sourceFileKind: 'Excel' | 'PDF'
  status: GenerationRunFileStatus
  errorMessage: string | null
}

export type GenerationRun = {
  id: string
  filingPeriodId: string
  version: number
  status: GenerationRunStatus
  errorMessage: string | null
  createdAtUtc: string
  startedAtUtc: string | null
  completedAtUtc: string | null
  files: GenerationRunFile[]
  artifacts: Artifact[]
  /** Warnings found while building the anexos; never blocking. */
  issues: Issue[]
}

export type Upload = {
  id: string
  filingPeriodId: string
  originalFileName: string
  sourceFileKind: 'Excel' | 'PDF'
  contentType: string
  sizeBytes: number
  createdAtUtc: string
  includedInLatestRun: boolean
  extractionStatus: ExtractionStatus
  extractionError: string | null
  documentsCount: number
}

export type IssueSeverity = 'Warning' | 'Error'

export type Issue = {
  code: string
  severity: IssueSeverity
  message: string
  field: string | null
}

/** Worst severity among a document's issues; Ok when there are none. */
export type DocumentStatus = 'Ok' | 'Warning' | 'Error'

export type ExtractionMethod = 'Parser' | 'Ai' | 'Manual'

/** Money values travel as decimal strings ("48.14") to keep cents exact. */
export type Money = string

export type DocumentDto = {
  id: string
  uploadId: string
  originalFileName: string
  extractionMethod: ExtractionMethod
  status: DocumentStatus
  issues: Issue[]
  edited: boolean
  excluded: boolean
  tipoDte: string
  codigoGeneracion: string | null
  numeroControl: string | null
  selloRecepcion: string | null
  /** YYYY-MM-DD */
  fechaEmision: string | null
  /** HH:MM:SS */
  horaEmision: string | null
  emisorNombre: string | null
  emisorNit: string | null
  emisorNrc: string | null
  receptorNombre: string | null
  receptorNit: string | null
  receptorNrc: string | null
  receptorDui: string | null
  totalNoSujetas: Money
  totalExentas: Money
  totalGravadas: Money
  iva: Money
  ivaRetenido: Money
  total: Money
  /** Per-document override; null means the client's default applies. */
  tipoOperacionRenta: string | null
  tipoIngresoRenta: string | null
  effectiveTipoOperacion: string | null
  effectiveTipoIngreso: string | null
  anexo: 1 | 2 | null
}

export type DocumentTextField =
  | 'tipoDte'
  | 'codigoGeneracion'
  | 'numeroControl'
  | 'selloRecepcion'
  | 'fechaEmision'
  | 'horaEmision'
  | 'emisorNombre'
  | 'emisorNit'
  | 'emisorNrc'
  | 'receptorNombre'
  | 'receptorNit'
  | 'receptorNrc'
  | 'receptorDui'

export type DocumentMoneyField =
  | 'totalNoSujetas'
  | 'totalExentas'
  | 'totalGravadas'
  | 'iva'
  | 'ivaRetenido'
  | 'total'

/** PATCH body: only the fields being changed. */
export type DocumentPatch = Partial<
  Record<Exclude<DocumentTextField, 'tipoDte'>, string | null> &
    Record<DocumentMoneyField, Money>
> & {
  tipoDte?: string
  excluded?: boolean
  tipoOperacionRenta?: string | null
  tipoIngresoRenta?: string | null
}

export type DocumentBulkUpdate = {
  documentIds: string[]
  tipoOperacionRenta?: string | null
  tipoIngresoRenta?: string | null
  excluded?: boolean
}

export type RentaCatalogEntry = { code: string; label: string }

export type RentaCatalog = {
  tipoOperacion: RentaCatalogEntry[]
  tipoIngreso: RentaCatalogEntry[]
}

export type ClientPayload = {
  name: string
  taxId: string
  notes: string | null
  nit: string | null
  nrc: string | null
  defaultTipoOperacion: string | null
  defaultTipoIngreso: string | null
}

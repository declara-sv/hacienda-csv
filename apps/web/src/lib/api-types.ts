export type ParseJobStatus = 'Pending' | 'Running' | 'Failed' | 'Completed'

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
}

export type ParseJob = {
  id: string
  status: ParseJobStatus
  errorMessage: string | null
  createdAtUtc: string
  startedAtUtc: string | null
  completedAtUtc: string | null
  artifacts: Artifact[]
}

export type Upload = {
  id: string
  filingPeriodId: string
  originalFileName: string
  sourceFileKind: 'Excel' | 'PDF'
  contentType: string
  sizeBytes: number
  createdAtUtc: string
  jobs: ParseJob[]
}

export type UploadCreated = {
  uploadId: string
  parseJobId: string
  status: ParseJobStatus
}

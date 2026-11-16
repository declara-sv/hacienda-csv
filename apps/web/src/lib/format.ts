export const MONTHS_ES = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
] as const

export function formatPeriod(year: number, month: number) {
  const name = MONTHS_ES[month - 1] ?? String(month).padStart(2, '0')
  return `${name} ${year}`
}

export function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${Math.round(kb)} KB`
  const mb = kb / 1024
  return `${mb.toFixed(mb < 10 ? 1 : 0)} MB`
}

const dateTime = new Intl.DateTimeFormat('es-SV', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function formatDateTime(iso: string) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : dateTime.format(date)
}

export type SourceFileKind = 'Excel' | 'PDF'

export function detectSourceFileKind(fileName: string): SourceFileKind | null {
  const ext = fileName.toLowerCase().split('.').pop() ?? ''
  if (ext === 'pdf') return 'PDF'
  if (ext === 'xls' || ext === 'xlsx') return 'Excel'
  return null
}

export function pluralize(count: number, singular: string, plural: string) {
  return `${count} ${count === 1 ? singular : plural}`
}

/** Decimal string ("48.14") to integer cents, so sums never drift. */
export function toCents(value: string | null | undefined): number {
  if (!value) return 0
  const match = /^\s*(-)?(\d*)(?:\.(\d*))?\s*$/.exec(value)
  if (!match) return 0
  const [, sign, whole = '', fraction = ''] = match
  const cents =
    Number(whole || '0') * 100 + Number((fraction + '00').slice(0, 2))
  return sign ? -cents : cents
}

const money = new Intl.NumberFormat('es-SV', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function formatCents(cents: number) {
  return money.format(cents / 100)
}

export function formatMoney(value: string | null | undefined) {
  return formatCents(toCents(value))
}

/** YYYY-MM-DD as DD/MM/YYYY without going through time zones. */
export function formatIsoDate(value: string | null | undefined) {
  if (!value) return ''
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value
}

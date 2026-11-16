import { RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { RentaSelect } from '#/components/clients/RentaSelect'
import { Button } from '#/components/ui/Button'
import { Dialog } from '#/components/ui/Dialog'
import { Field, Input, Select, fieldDescribedBy } from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError } from '#/lib/api-client'
import {
  DTE_TYPE_NAMES,
  SALES_DTE_TYPES,
  dteTypeLabel,
  documentReference,
} from '#/lib/dte'
import { rentaLabel } from '#/lib/renta'
import type { MessageKey } from '#/i18n/messages'
import type {
  DocumentDto,
  DocumentMoneyField,
  DocumentPatch,
  DocumentTextField,
  RentaCatalog,
} from '#/lib/api-types'

export type ClientRentaDefaults = {
  tipoOperacion: string | null
  tipoIngreso: string | null
}

type EditableField =
  | DocumentTextField
  | DocumentMoneyField
  | 'tipoOperacionRenta'
  | 'tipoIngresoRenta'

type FormState = Record<EditableField, string>

type FieldSpec = {
  field: DocumentTextField | DocumentMoneyField
  label: MessageKey
  type?: 'date' | 'time'
  mono?: boolean
  money?: boolean
}

const groups: Array<{ title: MessageKey; fields: FieldSpec[] }> = [
  {
    title: 'editGroupDocument',
    fields: [
      { field: 'codigoGeneracion', label: 'fieldCodigoGeneracion', mono: true },
      { field: 'numeroControl', label: 'fieldNumeroControl', mono: true },
      { field: 'selloRecepcion', label: 'fieldSelloRecepcion', mono: true },
      { field: 'fechaEmision', label: 'fieldFechaEmision', type: 'date' },
      { field: 'horaEmision', label: 'fieldHoraEmision', type: 'time' },
    ],
  },
  {
    title: 'editGroupEmisor',
    fields: [
      { field: 'emisorNombre', label: 'fieldNombre' },
      { field: 'emisorNit', label: 'fieldNit' },
      { field: 'emisorNrc', label: 'fieldNrc' },
    ],
  },
  {
    title: 'editGroupReceptor',
    fields: [
      { field: 'receptorNombre', label: 'fieldNombre' },
      { field: 'receptorNit', label: 'fieldNit' },
      { field: 'receptorNrc', label: 'fieldNrc' },
      { field: 'receptorDui', label: 'fieldDui' },
    ],
  },
  {
    title: 'editGroupAmounts',
    fields: [
      { field: 'totalExentas', label: 'fieldExentas', money: true },
      { field: 'totalNoSujetas', label: 'fieldNoSujetas', money: true },
      { field: 'totalGravadas', label: 'fieldGravadas', money: true },
      { field: 'iva', label: 'fieldIva', money: true },
      { field: 'ivaRetenido', label: 'fieldIvaRetenido', money: true },
      { field: 'total', label: 'fieldTotal', money: true },
    ],
  },
]

const textFields: DocumentTextField[] = [
  'tipoDte',
  ...groups.flatMap((group) =>
    group.fields.filter((spec) => !spec.money).map((spec) => spec.field),
  ),
] as DocumentTextField[]
const moneyFields = groups
  .flatMap((group) => group.fields)
  .filter((spec) => spec.money)
  .map((spec) => spec.field) as DocumentMoneyField[]

const MONEY_PATTERN = /^-?\d+(\.\d{1,2})?$/

function toState(document: DocumentDto): FormState {
  const state = {} as FormState
  for (const field of textFields) state[field] = document[field] ?? ''
  for (const field of moneyFields) state[field] = document[field]
  state.tipoOperacionRenta = document.tipoOperacionRenta ?? ''
  state.tipoIngresoRenta = document.tipoIngresoRenta ?? ''
  return state
}

const sameMoney = (a: string, b: string) => Number(a) === Number(b)

/** Builds a PATCH with only the fields that changed; null clears a value. */
export function buildDocumentPatch(
  document: DocumentDto,
  state: FormState,
): DocumentPatch {
  const patch: DocumentPatch = {}
  const mutable = patch as Record<string, string | null>
  for (const field of textFields) {
    const next = state[field].trim()
    if (next === (document[field] ?? '')) continue
    mutable[field] = field === 'tipoDte' ? next : next || null
  }
  for (const field of moneyFields) {
    const next = state[field].trim()
    if (!sameMoney(next, document[field])) mutable[field] = next
  }
  for (const field of ['tipoOperacionRenta', 'tipoIngresoRenta'] as const) {
    const next = state[field] || null
    if (next !== document[field]) patch[field] = next
  }
  return patch
}

/** ProblemDetails `errors` keyed by field, tolerating "body.field" keys. */
function fieldErrorsOf(error: unknown): Partial<Record<string, string>> {
  if (!(error instanceof ApiError)) return {}
  const details = error.details as { errors?: unknown } | null
  const errors = details?.errors
  if (typeof errors !== 'object' || errors === null) return {}
  const result: Partial<Record<string, string>> = {}
  for (const [key, value] of Object.entries(errors)) {
    const field = key.split('.').pop() ?? key
    const message = Array.isArray(value) ? value[0] : value
    if (typeof message === 'string') result[field] = message
  }
  return result
}

type DocumentEditDialogProps = {
  document: DocumentDto
  catalog: RentaCatalog | undefined
  clientDefaults: ClientRentaDefaults | null
  onClose: () => void
  onSave: (patch: DocumentPatch) => Promise<unknown>
}

export function DocumentEditDialog({
  document,
  catalog,
  clientDefaults,
  onClose,
  onSave,
}: DocumentEditDialogProps) {
  const { t } = useI18n()
  const [state, setState] = useState<FormState>(() => toState(document))
  const [fieldErrors, setFieldErrors] = useState<
    Partial<Record<string, string>>
  >({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const set = (field: EditableField) => (value: string) =>
    setState((current) => ({ ...current, [field]: value }))
  const id = (field: string) => `edit-document-${field}`

  const typeOptions = Array.from(
    new Set<string>([...SALES_DTE_TYPES, document.tipoDte]),
  ).filter(Boolean)

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const errors: Partial<Record<string, string>> = {}
    for (const field of moneyFields) {
      if (!MONEY_PATTERN.test(state[field].trim()))
        errors[field] = t('editInvalidAmount')
    }
    setFieldErrors(errors)
    setError(null)
    if (Object.keys(errors).length > 0) return

    const patch = buildDocumentPatch(document, state)
    if (Object.keys(patch).length === 0) {
      onClose()
      return
    }
    setSaving(true)
    try {
      await onSave(patch)
      onClose()
    } catch (err) {
      setFieldErrors(fieldErrorsOf(err))
      setError(err instanceof ApiError ? err.message : t('editSaveError'))
      setSaving(false)
    }
  }

  const clientValueLabel = (
    entries: RentaCatalog['tipoOperacion'] | undefined,
    code: string | null | undefined,
  ) =>
    code
      ? t('rentaUseClientValue', { value: rentaLabel(entries, code) })
      : t('rentaUseClientValueMissing')

  const renta = [
    {
      field: 'tipoOperacionRenta' as const,
      label: t('fieldTipoOperacion'),
      entries: catalog?.tipoOperacion,
      clientCode: clientDefaults?.tipoOperacion,
    },
    {
      field: 'tipoIngresoRenta' as const,
      label: t('fieldTipoIngreso'),
      entries: catalog?.tipoIngreso,
      clientCode: clientDefaults?.tipoIngreso,
    },
  ]

  return (
    <Dialog
      title={t('editDocumentTitle')}
      description={`${dteTypeLabel(document.tipoDte)} · ${documentReference(document)}`}
      onClose={onClose}
      closeDisabled={saving}
      initialFocusId={id('tipoOperacionRenta')}
    >
      <form className="space-y-6 px-5 py-5" onSubmit={onSubmit} noValidate>
        <fieldset className="space-y-4">
          <legend className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
            {t('editGroupRenta')}
          </legend>
          <div className="grid gap-4 md:grid-cols-2">
            {renta.map((item) => {
              const hint = state[item.field]
                ? t('rentaOverrideHint')
                : t('rentaDefaultHint')
              return (
                <div key={item.field} className="space-y-2">
                  <Field
                    id={id(item.field)}
                    label={item.label}
                    hint={hint}
                    error={fieldErrors[item.field]}
                  >
                    <RentaSelect
                      id={id(item.field)}
                      entries={item.entries}
                      emptyLabel={clientValueLabel(
                        item.entries,
                        item.clientCode,
                      )}
                      aria-describedby={fieldDescribedBy(
                        id(item.field),
                        hint,
                        fieldErrors[item.field],
                      )}
                      value={state[item.field]}
                      onValueChange={set(item.field)}
                    />
                  </Field>
                  {state[item.field] ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<RotateCcw className="size-4" strokeWidth={2} />}
                      onClick={() => set(item.field)('')}
                    >
                      {t('rentaResetToClient')}
                    </Button>
                  ) : null}
                </div>
              )
            })}
          </div>
        </fieldset>

        <fieldset className="space-y-4">
          <legend className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
            {t('editGroupType')}
          </legend>
          <Field id={id('tipoDte')} label={t('fieldTipoDte')}>
            <Select
              id={id('tipoDte')}
              value={state.tipoDte}
              onChange={(event) => set('tipoDte')(event.target.value)}
            >
              {typeOptions.map((code) => (
                <option key={code} value={code}>
                  {DTE_TYPE_NAMES[code] ? dteTypeLabel(code) : code}
                </option>
              ))}
            </Select>
          </Field>
        </fieldset>

        {groups.map((group) => (
          <fieldset key={group.title} className="space-y-4">
            <legend className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
              {t(group.title)}
            </legend>
            <div className="grid gap-4 md:grid-cols-2">
              {group.fields.map((spec) => {
                const fieldId = id(spec.field)
                const fieldError = fieldErrors[spec.field]
                return (
                  <Field
                    key={spec.field}
                    id={fieldId}
                    label={t(spec.label)}
                    error={fieldError}
                  >
                    <Input
                      id={fieldId}
                      name={spec.field}
                      type={spec.type ?? 'text'}
                      step={spec.type === 'time' ? 1 : undefined}
                      inputMode={spec.money ? 'decimal' : undefined}
                      className={
                        spec.mono
                          ? 'font-mono text-sm'
                          : spec.money
                            ? 'text-right tabular-nums'
                            : undefined
                      }
                      spellCheck={spec.mono ? false : undefined}
                      invalid={Boolean(fieldError)}
                      aria-describedby={fieldDescribedBy(
                        fieldId,
                        undefined,
                        fieldError,
                      )}
                      value={state[spec.field]}
                      onChange={(event) => set(spec.field)(event.target.value)}
                    />
                  </Field>
                )
              })}
            </div>
          </fieldset>
        ))}

        {error ? (
          <Notice variant="error" onDismiss={() => setError(null)}>
            {error}
          </Notice>
        ) : null}

        <div className="flex flex-col-reverse gap-2 border-t border-line pt-4 sm:flex-row sm:justify-end">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            {t('cancel')}
          </Button>
          <Button type="submit" loading={saving} loadingLabel={t('saving')}>
            {t('saveChanges')}
          </Button>
        </div>
      </form>
    </Dialog>
  )
}

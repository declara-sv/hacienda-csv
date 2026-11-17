import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { RentaSelect } from './RentaSelect'
import { Button } from '#/components/ui/Button'
import { Field, Input, Textarea, fieldDescribedBy } from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError, clientsApi } from '#/lib/api-client'
import { useRentaCatalog } from '#/lib/renta'
import type { ClientDetail, ClientPayload } from '#/lib/api-types'

type ClientFormProps = {
  /** Present when editing; absent when creating. */
  client?: ClientDetail
  /** Prefix for control ids, so two forms never share an id. */
  idPrefix: string
  onCancel: () => void
  onSaved: (client: ClientDetail) => void
}

// taxId is not edited: the API keeps it as the list label, filled from the NIT.
type FormState = Record<Exclude<keyof ClientPayload, 'taxId'>, string>

const toState = (client?: ClientDetail): FormState => ({
  name: client?.name ?? '',
  notes: client?.notes ?? '',
  // Clients created before NIT existed only had the free-form identification.
  nit: client?.nit ?? client?.taxId ?? '',
  nrc: client?.nrc ?? '',
  defaultTipoOperacion: client?.defaultTipoOperacion ?? '',
  defaultTipoIngreso: client?.defaultTipoIngreso ?? '',
})

const orNull = (value: string) => value.trim() || null

export function toClientPayload(state: FormState): ClientPayload {
  return {
    name: state.name.trim(),
    taxId: state.nit.trim(),
    notes: orNull(state.notes),
    nit: orNull(state.nit),
    nrc: orNull(state.nrc),
    defaultTipoOperacion: orNull(state.defaultTipoOperacion),
    defaultTipoIngreso: orNull(state.defaultTipoIngreso),
  }
}

/** Create or edit a client, including its fiscal identity and Renta defaults. */
export function ClientForm({
  client,
  idPrefix,
  onCancel,
  onSaved,
}: ClientFormProps) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const catalogQuery = useRentaCatalog()
  const editing = client !== undefined

  const [state, setState] = useState<FormState>(() => toState(client))
  const [error, setError] = useState<string | null>(null)
  const set = (field: keyof FormState) => (value: string) =>
    setState((current) => ({ ...current, [field]: value }))

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = toClientPayload(state)
      return client
        ? clientsApi.update(client.id, payload)
        : clientsApi.create(payload)
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ['clients'] })
      if (client) {
        queryClient.setQueryData(['client', client.id], saved)
        void queryClient.invalidateQueries({ queryKey: ['client', client.id] })
        // Renta defaults and the client's NIT/NRC feed every document's issues.
        void queryClient.invalidateQueries({
          queryKey: ['documents', client.id],
        })
      }
      onSaved(saved)
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : t(editing ? 'clientUpdateError' : 'clientCreateError'),
      )
    },
  })

  const id = (field: string) => `${idPrefix}-${field}`
  const catalogError = catalogQuery.isError ? t('rentaCatalogError') : null
  const rentaHint = catalogError ?? t('clientRentaHint')

  return (
    <form
      className="grid gap-5 md:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault()
        setError(null)
        saveMutation.mutate()
      }}
    >
      <Field id={id('name')} label={t('clientName')} className="md:col-span-2">
        <Input
          id={id('name')}
          name="name"
          autoFocus
          required
          maxLength={160}
          autoComplete="organization"
          value={state.name}
          onChange={(event) => set('name')(event.target.value)}
        />
      </Field>

      <Field id={id('nit')} label={t('clientNit')} hint={t('clientNitHint')}>
        <Input
          id={id('nit')}
          name="nit"
          inputMode="numeric"
          required
          maxLength={20}
          aria-describedby={fieldDescribedBy(id('nit'), t('clientNitHint'))}
          value={state.nit}
          onChange={(event) => set('nit')(event.target.value)}
        />
      </Field>

      <Field id={id('nrc')} label={t('clientNrc')} hint={t('clientNrcHint')}>
        <Input
          id={id('nrc')}
          name="nrc"
          maxLength={20}
          aria-describedby={fieldDescribedBy(id('nrc'), t('clientNrcHint'))}
          value={state.nrc}
          onChange={(event) => set('nrc')(event.target.value)}
        />
      </Field>

      <Field
        id={id('defaultTipoOperacion')}
        label={t('clientDefaultTipoOperacion')}
        hint={rentaHint}
      >
        <RentaSelect
          id={id('defaultTipoOperacion')}
          name="defaultTipoOperacion"
          entries={catalogQuery.data?.tipoOperacion}
          emptyLabel={t('rentaNoDefault')}
          aria-describedby={fieldDescribedBy(
            id('defaultTipoOperacion'),
            rentaHint,
          )}
          value={state.defaultTipoOperacion}
          onValueChange={set('defaultTipoOperacion')}
        />
      </Field>

      <Field
        id={id('defaultTipoIngreso')}
        label={t('clientDefaultTipoIngreso')}
        hint={rentaHint}
      >
        <RentaSelect
          id={id('defaultTipoIngreso')}
          name="defaultTipoIngreso"
          entries={catalogQuery.data?.tipoIngreso}
          emptyLabel={t('rentaNoDefault')}
          aria-describedby={fieldDescribedBy(
            id('defaultTipoIngreso'),
            rentaHint,
          )}
          value={state.defaultTipoIngreso}
          onValueChange={set('defaultTipoIngreso')}
        />
      </Field>

      <Field
        id={id('notes')}
        label={t('clientNotes')}
        hint={t('clientNotesHint')}
        className="md:col-span-2"
      >
        <Textarea
          id={id('notes')}
          name="notes"
          maxLength={2000}
          aria-describedby={fieldDescribedBy(id('notes'), t('clientNotesHint'))}
          value={state.notes}
          onChange={(event) => set('notes')(event.target.value)}
        />
      </Field>

      {error ? (
        <Notice
          variant="error"
          className="md:col-span-2"
          onDismiss={() => setError(null)}
        >
          {error}
        </Notice>
      ) : null}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end md:col-span-2">
        <Button variant="ghost" onClick={onCancel}>
          {t('cancel')}
        </Button>
        <Button
          type="submit"
          loading={saveMutation.isPending}
          loadingLabel={t('savingClient')}
        >
          {t(editing ? 'saveClientChanges' : 'saveClient')}
        </Button>
      </div>
    </form>
  )
}

// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PeriodReview, documentsQueryKey } from './PeriodReview'
import { I18nProvider } from '#/i18n/I18nProvider'
import { ApiError, catalogsApi, documentsApi } from '#/lib/api-client'
import { documentDto, rentaCatalog } from '#/test/fixtures'
import type * as ApiClient from '#/lib/api-client'
import type { DocumentDto } from '#/lib/api-types'

vi.mock('#/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiClient>()),
  documentsApi: { list: vi.fn(), update: vi.fn(), bulkUpdate: vi.fn() },
  catalogsApi: { renta: vi.fn() },
}))

const updateDocument = vi.mocked(documentsApi.update)
const bulkUpdate = vi.mocked(documentsApi.bulkUpdate)
const listDocuments = vi.mocked(documentsApi.list)
const rentaCatalogApi = vi.mocked(catalogsApi.renta)

let client: QueryClient | null = null

function setup(
  documents: DocumentDto[],
  props: Partial<React.ComponentProps<typeof PeriodReview>> = {},
) {
  client ??= new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  client.setQueryData(documentsQueryKey('client', 'period'), documents)
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <PeriodReview
          clientId="client"
          periodId="period"
          documents={documents}
          clientDefaults={{ tipoOperacion: '1', tipoIngreso: '3' }}
          {...props}
        />
      </I18nProvider>
    </QueryClientProvider>,
  )
}

const table = () => screen.getByRole('table')
const rows = () => within(table()).getAllByRole('row').slice(1)
const rowOf = (name: string) => {
  const row = rows().find((item) => within(item).queryByText(name))
  if (!row) throw new Error(`No row for ${name}`)
  return row
}

beforeEach(() => {
  vi.resetAllMocks()
  rentaCatalogApi.mockResolvedValue(rentaCatalog)
  listDocuments.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  client?.clear()
  client = null
})

describe('PeriodReview', () => {
  it('summarizes counts, totals and blocking errors per anexo', () => {
    setup([
      documentDto('1', { anexo: 2, total: '10.10' }),
      documentDto('2', { anexo: 2, total: '0.20' }),
      documentDto('3', { anexo: 1, tipoDte: '03', total: '113.00' }),
      documentDto('4', {
        anexo: 1,
        tipoDte: '03',
        total: '5.00',
        status: 'Error',
        issues: [
          { code: 'x', severity: 'Error', message: 'Falla', field: null },
        ],
      }),
      documentDto('5', { anexo: 2, total: '9.00', excluded: true }),
    ])

    const summary = screen.getByLabelText('Resumen del período')
    const anexo1 = within(summary).getByText('Anexo 1 · Contribuyentes')
      .parentElement as HTMLElement
    expect(within(anexo1).getByText(/118[.,]00/)).toBeTruthy()
    expect(within(anexo1).getByText('Documentos incluidos: 2')).toBeTruthy()
    const anexo2 = within(summary).getByText('Anexo 2 · Consumidor final')
      .parentElement as HTMLElement
    expect(within(anexo2).getByText(/10[.,]30/)).toBeTruthy()
    expect(within(anexo2).getByText('Documentos incluidos: 2')).toBeTruthy()
    const errors = within(summary).getByText('Errores que bloquean')
      .parentElement as HTMLElement
    expect(within(errors).getByText('1')).toBeTruthy()
    expect(
      within(summary).getByText('Excluidos: 1 · Sin anexo: 0'),
    ).toBeTruthy()
  })

  it('shows each document with type, anexo, receptor, amounts and copyable code', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const document = documentDto('7', {
      tipoDte: '03',
      anexo: 1,
      receptorNombre: 'Ferretería El Sol',
      receptorNit: '0614-290190-102-3',
      receptorDui: null,
      totalGravadas: '100.00',
      iva: '13.00',
      total: '113.00',
    })
    setup([document])

    const row = rowOf('Ferretería El Sol')
    expect(within(row).getByText('05/10/2025')).toBeTruthy()
    expect(within(row).getByText('03 CCF')).toBeTruthy()
    expect(within(row).getByText('Anexo 1')).toBeTruthy()
    expect(within(row).getByText('NIT 0614-290190-102-3')).toBeTruthy()
    expect(within(row).getByText(/113[.,]00/)).toBeTruthy()
    const code = within(row).getByText(document.codigoGeneracion!)
    expect(code.tagName).toBe('CODE')

    fireEvent.click(
      within(row).getByRole('button', {
        name: `Copiar código ${document.codigoGeneracion}`,
      }),
    )
    expect(writeText).toHaveBeenCalledWith(document.codigoGeneracion)
    await within(row).findByRole('button', { name: 'Copiado' })
  })

  it('distinguishes Renta overrides from client defaults and flags missing codes', async () => {
    setup([
      documentDto('1', { receptorNombre: 'Receptor A' }),
      documentDto('2', {
        receptorNombre: 'Receptor B',
        tipoIngresoRenta: '4',
        effectiveTipoIngreso: '4',
      }),
      documentDto('3', {
        receptorNombre: 'Receptor C',
        effectiveTipoOperacion: null,
      }),
    ])

    const byDefault = rowOf('Receptor A')
    expect(within(byDefault).getAllByText('Del cliente')).toHaveLength(2)
    expect(within(byDefault).queryByText('Ajustado')).toBeNull()

    const overridden = rowOf('Receptor B')
    expect(within(overridden).getAllByText('Ajustado')).toHaveLength(1)
    expect(within(overridden).getAllByText('Del cliente')).toHaveLength(1)
    // Labels come from the catalog once it loads.
    await within(overridden).findByText('4 – Servicios')

    const missing = rowOf('Receptor C')
    expect(within(missing).getAllByText('Sin código')).toHaveLength(1)
  })

  it('lists issues with their severity behind the status chip', () => {
    setup([
      documentDto('1', {
        status: 'Error',
        issues: [
          {
            code: 'duplicate',
            severity: 'Error',
            message: 'Código de generación repetido.',
            field: 'codigoGeneracion',
          },
          {
            code: 'iva',
            severity: 'Warning',
            message: 'El IVA no es el 13 % de gravadas.',
            field: 'iva',
          },
        ],
      }),
    ])

    const row = rows()[0]
    expect(within(row).getByText('Error (2)')).toBeTruthy()
    const items = within(row).getAllByRole('listitem', { hidden: true })
    expect(items.map((item) => item.textContent)).toEqual([
      'Error: Código de generación repetido.',
      'Advertencia: El IVA no es el 13 % de gravadas.',
    ])
  })

  it('filters by status and anexo', () => {
    setup([
      documentDto('1', { receptorNombre: 'Uno', anexo: 2 }),
      documentDto('2', {
        receptorNombre: 'Dos',
        anexo: 1,
        status: 'Error',
        issues: [{ code: 'x', severity: 'Error', message: 'x', field: null }],
      }),
      documentDto('3', { receptorNombre: 'Tres', anexo: 1, status: 'Warning' }),
    ])

    fireEvent.change(screen.getByLabelText('Estado'), {
      target: { value: 'Error' },
    })
    expect(rows()).toHaveLength(1)
    expect(within(rows()[0]).getByText('Dos')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Estado'), {
      target: { value: 'all' },
    })
    fireEvent.change(screen.getByLabelText('Anexo'), {
      target: { value: '1' },
    })
    expect(rows().map((row) => within(row).queryByText('Uno'))).toEqual([
      null,
      null,
    ])
    expect(screen.getByText('Mostrando 2 de 3')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Estado'), {
      target: { value: 'Ok' },
    })
    expect(
      screen.getByText('Ningún documento coincide con los filtros.'),
    ).toBeTruthy()
  })

  it('excludes and includes a document with a PATCH and re-reads the period', async () => {
    updateDocument.mockResolvedValue(documentDto('1', { excluded: true }))
    setup([documentDto('1')])

    const toggle = screen.getByRole<HTMLInputElement>('switch', {
      name: /Incluir .* en los anexos/,
    })
    expect(toggle.checked).toBe(true)
    fireEvent.click(toggle)

    await waitFor(() =>
      expect(updateDocument).toHaveBeenCalledWith('client', 'period', '1', {
        excluded: true,
      }),
    )
    // Issues depend on the whole period, so the list is marked stale.
    await waitFor(() =>
      expect(
        client?.getQueryState(documentsQueryKey('client', 'period'))
          ?.isInvalidated,
      ).toBe(true),
    )
  })

  it('reports a failed include toggle', async () => {
    updateDocument.mockRejectedValue(
      new ApiError(409, 'El documento cambió.', null),
    )
    setup([documentDto('1')])
    fireEvent.click(screen.getByRole('switch'))
    await screen.findByText('El documento cambió.')
  })

  it('edits a document in a dialog that keeps and restores keyboard focus', async () => {
    updateDocument.mockResolvedValue(documentDto('1'))
    const document = documentDto('1', {
      tipoOperacionRenta: '2',
      effectiveTipoOperacion: '2',
    })
    setup([document])

    const trigger = screen.getByRole('button', {
      name: `Editar ${document.numeroControl}`,
    })
    trigger.focus()
    fireEvent.click(trigger)

    const dialog = await screen.findByRole('dialog', {
      name: 'Editar documento',
    })
    const operacion =
      within(dialog).getByLabelText<HTMLSelectElement>('Tipo de operación')
    expect(window.document.activeElement).toBe(operacion)
    expect(operacion.value).toBe('2')
    await within(dialog).findByRole('option', {
      name: 'Valor del cliente (1 – Gravada)',
    })

    // Escape closes without saving and returns focus to the trigger.
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(window.document.activeElement).toBe(trigger)
    expect(updateDocument).not.toHaveBeenCalled()
  })

  it('saves only the changed fields and restores Renta codes to the client value', async () => {
    updateDocument.mockResolvedValue(documentDto('1'))
    const document = documentDto('1', {
      tipoIngresoRenta: '4',
      effectiveTipoIngreso: '4',
    })
    setup([document])

    fireEvent.click(
      screen.getByRole('button', { name: `Editar ${document.numeroControl}` }),
    )
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'Restablecer al valor del cliente',
      }),
    )
    expect(
      within(dialog).getByLabelText<HTMLSelectElement>('Tipo de ingreso').value,
    ).toBe('')
    fireEvent.change(within(dialog).getByLabelText('Total'), {
      target: { value: '50.00' },
    })
    fireEvent.change(within(dialog).getByLabelText('Sello de recepción'), {
      target: { value: '' },
    })
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Guardar cambios' }),
    )

    await waitFor(() =>
      expect(updateDocument).toHaveBeenCalledWith('client', 'period', '1', {
        selloRecepcion: null,
        total: '50.00',
        tipoIngresoRenta: null,
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('validates amounts locally and shows API field errors', async () => {
    updateDocument.mockRejectedValue(
      new ApiError(400, 'El NIT no es válido.', {
        title: 'Bad Request',
        errors: { 'body.receptorNit': ['El NIT no es válido.'] },
      }),
    )
    setup([documentDto('1')])
    fireEvent.click(screen.getByRole('button', { name: /^Editar / }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText('IVA'), {
      target: { value: '1,5' },
    })
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Guardar cambios' }),
    )
    expect(within(dialog).getByText('Usa un monto como 48.14.')).toBeTruthy()
    expect(updateDocument).not.toHaveBeenCalled()

    fireEvent.change(within(dialog).getByLabelText('IVA'), {
      target: { value: '1.50' },
    })
    const receptor = within(dialog)
      .getByText('Receptor')
      .closest('fieldset') as HTMLElement
    fireEvent.change(within(receptor).getByLabelText('NIT'), {
      target: { value: '123' },
    })
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Guardar cambios' }),
    )

    await waitFor(() => expect(updateDocument).toHaveBeenCalledTimes(1))
    expect(
      await within(receptor).findByText('El NIT no es válido.'),
    ).toBeTruthy()
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('applies Renta codes and exclusion to the selection in bulk', async () => {
    bulkUpdate.mockResolvedValue(undefined)
    setup([
      documentDto('1', { receptorNombre: 'Uno' }),
      documentDto('2', { receptorNombre: 'Dos' }),
      documentDto('3', { receptorNombre: 'Tres' }),
    ])

    fireEvent.click(
      within(rowOf('Uno')).getByRole('checkbox', { name: /^Seleccionar / }),
    )
    fireEvent.click(
      within(rowOf('Tres')).getByRole('checkbox', { name: /^Seleccionar / }),
    )
    const bulk = screen.getByRole('region', {
      name: 'Acciones para la selección',
    })
    expect(within(bulk).getByText('Seleccionados: 2')).toBeTruthy()
    const apply = within(bulk).getByRole<HTMLButtonElement>('button', {
      name: 'Aplicar códigos',
    })
    expect(apply.disabled).toBe(true)

    await within(bulk).findByRole('option', { name: '4 – Servicios' })
    fireEvent.change(within(bulk).getByLabelText('Tipo de ingreso'), {
      target: { value: '4' },
    })
    fireEvent.change(within(bulk).getByLabelText('Tipo de operación'), {
      target: { value: '__client' },
    })
    fireEvent.click(apply)

    await waitFor(() =>
      expect(bulkUpdate).toHaveBeenCalledWith('client', 'period', {
        documentIds: ['1', '3'],
        tipoOperacionRenta: null,
        tipoIngresoRenta: '4',
      }),
    )
    await screen.findByText('Cambios aplicados a 2 documentos.')
    expect(
      screen.queryByRole('region', { name: 'Acciones para la selección' }),
    ).toBeNull()

    fireEvent.click(
      screen.getByRole('checkbox', {
        name: 'Seleccionar todos los documentos visibles',
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Excluir' }))
    await waitFor(() =>
      expect(bulkUpdate).toHaveBeenLastCalledWith('client', 'period', {
        documentIds: ['1', '2', '3'],
        excluded: true,
      }),
    )
  })

  it('reports a rejected bulk change and keeps the selection', async () => {
    bulkUpdate.mockRejectedValue(new ApiError(400, 'Código no válido.', null))
    setup([documentDto('1')])
    fireEvent.click(screen.getByRole('checkbox', { name: /^Seleccionar DTE/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Incluir' }))
    await screen.findByText('Código no válido.')
    expect(screen.getByText('Seleccionados: 1')).toBeTruthy()
  })

  it('shows loading, empty and error states', async () => {
    const onRetry = vi.fn()
    const view = setup([], { isLoading: true })
    expect(screen.getByText('Cargando la revisión')).toBeTruthy()

    view.unmount()
    setup([])
    expect(screen.getByText('Todavía no hay documentos leídos.')).toBeTruthy()
    cleanup()

    setup([], { error: 'No se pudo leer.', onRetry })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    })
    expect(onRetry).toHaveBeenCalled()
  })
})

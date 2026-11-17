// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ClientForm } from './ClientForm'
import { RentaDefaultsHint } from './RentaDefaultsHint'
import { I18nProvider } from '#/i18n/I18nProvider'
import { ApiError, catalogsApi, clientsApi } from '#/lib/api-client'
import { rentaCatalog } from '#/test/fixtures'
import type * as ApiClient from '#/lib/api-client'
import type { ClientDetail } from '#/lib/api-types'

vi.mock('#/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiClient>()),
  clientsApi: { create: vi.fn(), update: vi.fn() },
  catalogsApi: { renta: vi.fn() },
}))

const createClient = vi.mocked(clientsApi.create)
const updateClient = vi.mocked(clientsApi.update)
const rentaCatalogApi = vi.mocked(catalogsApi.renta)

const detail: ClientDetail = {
  id: 'c1',
  name: 'Comercial El Roble',
  taxId: '0614-010101-101-1',
  notes: null,
  nit: '0614-010101-101-1',
  nrc: '12345-6',
  defaultTipoOperacion: '1',
  defaultTipoIngreso: null,
  createdAtUtc: '2026-01-01T00:00:00Z',
  configurations: [],
  filingPeriods: [],
}

function show(props: Partial<React.ComponentProps<typeof ClientForm>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const onSaved = vi.fn()
  const onCancel = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <ClientForm
          idPrefix="test"
          onSaved={onSaved}
          onCancel={onCancel}
          {...props}
        />
      </I18nProvider>
    </QueryClientProvider>,
  )
  return { onSaved, onCancel }
}

const change = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } })

beforeEach(() => {
  vi.resetAllMocks()
  rentaCatalogApi.mockResolvedValue(rentaCatalog)
})
afterEach(cleanup)

describe('ClientForm', () => {
  it('creates a client with NIT, NRC and Renta defaults from the catalog', async () => {
    createClient.mockResolvedValue(detail)
    const { onSaved } = show()

    await screen.findByRole('option', { name: '1 – Gravada' })
    expect(screen.getByRole('option', { name: '4 – Servicios' })).toBeTruthy()

    change('Nombre del cliente', '  Comercial El Roble ')
    change('NIT', '06140101011011')
    change('NRC', '')
    change('Tipo de operación (Renta)', '1')
    change('Tipo de ingreso (Renta)', '4')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cliente' }))

    await waitFor(() =>
      expect(createClient).toHaveBeenCalledWith({
        name: 'Comercial El Roble',
        taxId: '06140101011011',
        notes: null,
        nit: '06140101011011',
        nrc: null,
        defaultTipoOperacion: '1',
        defaultTipoIngreso: '4',
      }),
    )
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(detail))
  })

  it('prefills an existing client and saves it with PUT', async () => {
    updateClient.mockResolvedValue({ ...detail, defaultTipoIngreso: '3' })
    const { onSaved } = show({ client: detail })

    expect(
      screen.getByLabelText<HTMLInputElement>('Nombre del cliente').value,
    ).toBe('Comercial El Roble')
    expect(
      screen.getByLabelText<HTMLSelectElement>('Tipo de operación (Renta)')
        .value,
    ).toBe('1')
    await screen.findByRole('option', { name: '3 – Comercial' })
    change('Tipo de ingreso (Renta)', '3')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() =>
      expect(updateClient).toHaveBeenCalledWith('c1', {
        name: 'Comercial El Roble',
        taxId: '0614-010101-101-1',
        notes: null,
        nit: '0614-010101-101-1',
        nrc: '12345-6',
        defaultTipoOperacion: '1',
        defaultTipoIngreso: '3',
      }),
    )
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('has no separate identification field', () => {
    show()
    expect(screen.queryByLabelText('Identificación')).toBeNull()
    expect(screen.getByLabelText<HTMLInputElement>('NIT').required).toBe(true)
  })

  it('prefills the NIT from the identification of an older client', () => {
    show({ client: { ...detail, nit: null, taxId: '0614-999999-101-1' } })
    expect(screen.getByLabelText<HTMLInputElement>('NIT').value).toBe(
      '0614-999999-101-1',
    )
  })

  it('shows the API validation message', async () => {
    updateClient.mockRejectedValue(
      new ApiError(400, 'El NIT debe tener 14 dígitos.', null),
    )
    show({ client: detail })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('El NIT debe tener 14 dígitos.')
  })

  it('keeps working when the catalog cannot be loaded', async () => {
    rentaCatalogApi.mockRejectedValue(new Error('offline'))
    show({ client: detail })
    await screen.findAllByText(
      'No se pudo cargar el catálogo de Renta. Recarga la página para elegir un código.',
    )
    // The saved code stays selected even without its label.
    expect(
      screen.getByLabelText<HTMLSelectElement>('Tipo de operación (Renta)')
        .value,
    ).toBe('1')
  })
})

describe('RentaDefaultsHint', () => {
  it('asks for the Renta codes only while a default is missing', () => {
    const { rerender } = render(
      <I18nProvider>
        <RentaDefaultsHint client={detail} />
      </I18nProvider>,
    )
    expect(
      screen.getByText(
        'Desde enero 2025 los códigos de Renta son obligatorios.',
      ),
    ).toBeTruthy()

    rerender(
      <I18nProvider>
        <RentaDefaultsHint client={{ ...detail, defaultTipoIngreso: '3' }} />
      </I18nProvider>,
    )
    expect(
      screen.queryByText(
        'Desde enero 2025 los códigos de Renta son obligatorios.',
      ),
    ).toBeNull()
  })
})

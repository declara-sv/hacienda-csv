// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MultiFileUpload } from './MultiFileUpload'
import { I18nProvider } from '#/i18n/I18nProvider'
import { ApiError, uploadsApi } from '#/lib/api-client'
import type * as ApiClient from '#/lib/api-client'

vi.mock('#/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiClient>()),
  uploadsApi: { create: vi.fn() },
}))
const create = vi.mocked(uploadsApi.create)
const file = (name: string, contents = 'data') => new File([contents], name)
const deferred = () => {
  let resolve!: () => void
  const promise = new Promise<void>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
function setup(
  props: Partial<React.ComponentProps<typeof MultiFileUpload>> = {},
) {
  return render(
    <I18nProvider>
      <MultiFileUpload
        clientId="client"
        periodId="period"
        onUploaded={vi.fn()}
        onQueueStateChange={vi.fn()}
        {...props}
      />
    </I18nProvider>,
  )
}
const input = () => screen.getByLabelText<HTMLInputElement>('Elegir PDF')
const select = (...files: File[]) =>
  fireEvent.change(input(), { target: { files } })
const dropzone = () =>
  screen.getByRole<HTMLButtonElement>('button', { name: /Arrastra los PDF/ })
afterEach(cleanup)
beforeEach(() => {
  vi.resetAllMocks()
  create.mockResolvedValue({} as never)
})

describe('MultiFileUpload', () => {
  it('uploads picked and dropped PDFs right away, without a submit step', async () => {
    setup()
    expect(input().multiple).toBe(true)
    expect(input().accept).toContain('.pdf')
    expect(screen.queryByRole('button', { name: 'Subir archivos' })).toBeNull()
    select(file('one.pdf'), file('two.pdf'))
    fireEvent.drop(dropzone(), {
      dataTransfer: { files: [file('three.PDF')] },
    })
    await waitFor(() => expect(create).toHaveBeenCalledTimes(3))
    expect(create.mock.calls.map((call) => call[2].file.name)).toEqual([
      'one.pdf',
      'two.pdf',
      'three.PDF',
    ])
    expect(
      create.mock.calls.every((call) => call[2].sourceFileKind === 'PDF'),
    ).toBe(true)
  })
  it('rejects non-PDF and empty files inline without blocking the period', async () => {
    const onQueueStateChange = vi.fn()
    setup({ onQueueStateChange })
    select(file('ventas.xlsx'), file('empty.pdf', ''))
    const alerts = screen.getAllByRole('alert')
    expect(alerts.map((alert) => alert.textContent)).toEqual([
      'Solo se aceptan PDF.',
      'El archivo está vacío.',
    ])
    expect(onQueueStateChange).toHaveBeenLastCalledWith({
      pendingCount: 0,
      busy: false,
    })
    fireEvent.click(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Quitar ventas.xlsx',
      }),
    )
    expect(screen.queryByText(/ventas\.xlsx/)).toBeNull()
    expect(create).not.toHaveBeenCalled()
  })
  it('uploads sequentially, queues files added meanwhile and awaits refresh', async () => {
    const first = deferred()
    const refresh = deferred()
    const onUploaded = vi.fn().mockReturnValueOnce(refresh.promise)
    const onQueueStateChange = vi.fn()
    create.mockImplementationOnce(async () => {
      await first.promise
      return {} as never
    })
    setup({ onUploaded, onQueueStateChange })
    select(file('one.pdf'))
    expect(create).toHaveBeenCalledTimes(1)
    select(file('two.pdf'))
    expect(create).toHaveBeenCalledTimes(1)
    expect(onQueueStateChange).toHaveBeenLastCalledWith({
      pendingCount: 2,
      busy: true,
    })
    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Quitar one.pdf' })
        .disabled,
    ).toBe(true)
    await act(async () => first.resolve())
    expect(create).toHaveBeenCalledTimes(1)
    await act(async () => refresh.resolve())
    await waitFor(() =>
      expect(onQueueStateChange).toHaveBeenLastCalledWith({
        pendingCount: 0,
        busy: false,
      }),
    )
    expect(create).toHaveBeenCalledTimes(2)
    expect(onUploaded).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('one.pdf')).toBeNull()
  })
  it('retains only failures and retries only the explicitly selected file', async () => {
    create
      .mockResolvedValueOnce({} as never)
      .mockRejectedValueOnce(new Error('network'))
    const onUploaded = vi.fn()
    setup({ onUploaded })
    select(file('saved.pdf'), file('failed.pdf'))
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(onUploaded).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('saved.pdf')).toBeNull()
    fireEvent.click(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Reintentar failed.pdf',
      }),
    )
    await waitFor(() => expect(create).toHaveBeenCalledTimes(3))
    expect(create.mock.calls.map((call) => call[2].file.name)).toEqual([
      'saved.pdf',
      'failed.pdf',
      'failed.pdf',
    ])
  })
  it('shows server validation errors for the failed file', async () => {
    create.mockRejectedValueOnce(new ApiError(400, 'Documento inválido', null))
    setup()
    select(file('invalid.pdf'))
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('Documento inválido'),
    )
  })
  it('never retries a saved file when refresh fails', async () => {
    setup({ onUploaded: vi.fn().mockRejectedValue(new Error('refresh')) })
    select(file('saved.pdf'))
    await waitFor(() =>
      expect(
        screen.getByText(
          'El archivo se guardó, pero no se pudo actualizar el listado. Recarga la página.',
        ),
      ).toBeTruthy(),
    )
    expect(screen.queryByText('saved.pdf')).toBeNull()
    expect(create).toHaveBeenCalledTimes(1)
  })
  it('honors disabled and ignores drops while disabled', () => {
    setup({ disabled: true })
    select(file('ignored.pdf'))
    fireEvent.drop(dropzone(), {
      dataTransfer: { files: [file('drop.pdf')] },
    })
    expect(input().disabled).toBe(true)
    expect(screen.queryByText('drop.pdf')).toBeNull()
    expect(create).not.toHaveBeenCalled()
  })
  it('stops later uploads and callbacks after unmount', async () => {
    const first = deferred()
    create.mockImplementationOnce(async () => {
      await first.promise
      return {} as never
    })
    const onUploaded = vi.fn()
    const onQueueStateChange = vi.fn()
    const view = setup({ onUploaded, onQueueStateChange })
    select(file('one.pdf'), file('two.pdf'))
    view.unmount()
    const notifications = onQueueStateChange.mock.calls.length
    await act(async () => first.resolve())
    expect(create).toHaveBeenCalledTimes(1)
    expect(onUploaded).not.toHaveBeenCalled()
    expect(onQueueStateChange).toHaveBeenCalledTimes(notifications)
  })
})

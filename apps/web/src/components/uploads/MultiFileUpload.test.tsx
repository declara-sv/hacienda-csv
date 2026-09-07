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
const input = () =>
  screen.getByLabelText<HTMLInputElement>('Seleccionar archivos')
const select = (...files: File[]) =>
  fireEvent.change(input(), { target: { files } })
const submit = () =>
  fireEvent.click(
    screen.getByRole<HTMLButtonElement>('button', { name: 'Subir archivos' }),
  )
afterEach(cleanup)
beforeEach(() => {
  vi.resetAllMocks()
  create.mockResolvedValue({} as never)
})

describe('MultiFileUpload', () => {
  it('appends mixed selections with detected types and supports drag and drop', async () => {
    setup()
    expect(input().multiple).toBe(true)
    select(file('one.xlsx'), file('two.pdf'))
    select(file('three.xls'))
    fireEvent.drop(
      screen.getByRole<HTMLButtonElement>('button', {
        name: /Arrastra archivos/,
      }),
      {
        dataTransfer: { files: [file('four.PDF')] },
      },
    )
    for (const name of ['one.xlsx', 'two.pdf', 'three.xls', 'four.PDF'])
      expect(screen.getByText(name)).toBeTruthy()
    submit()
    await waitFor(() => expect(create).toHaveBeenCalledTimes(4))
    expect(create.mock.calls.map((call) => call[2].sourceFileKind)).toEqual([
      'Excel',
      'PDF',
      'Excel',
      'PDF',
    ])
  })
  it('keeps invalid and empty files removable and reports all queued entries', async () => {
    const onQueueStateChange = vi.fn()
    setup({ onQueueStateChange })
    select(file('bad.csv'), file('empty.pdf', ''))
    expect(screen.getAllByRole('alert')).toHaveLength(2)
    const submitButton = screen.getByRole<HTMLButtonElement>('button', {
      name: 'Subir archivos',
    })
    expect(submitButton.disabled).toBe(true)
    // An idle action must not advertise aria-busy="false".
    expect(submitButton.getAttribute('aria-busy')).toBeNull()
    expect(onQueueStateChange).toHaveBeenLastCalledWith({
      pendingCount: 2,
      busy: false,
    })
    fireEvent.click(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Quitar bad.csv' }),
    )
    fireEvent.click(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Quitar empty.pdf',
      }),
    )
    expect(onQueueStateChange).toHaveBeenLastCalledWith({
      pendingCount: 0,
      busy: false,
    })
    expect(create).not.toHaveBeenCalled()
  })
  it('uploads sequentially, locks editing and awaits refresh before finishing', async () => {
    const first = deferred()
    const refresh = deferred()
    const onUploaded = vi.fn().mockReturnValueOnce(refresh.promise)
    const onQueueStateChange = vi.fn()
    create.mockImplementationOnce(async () => {
      await first.promise
      return {} as never
    })
    setup({ onUploaded, onQueueStateChange })
    select(file('one.pdf'), file('two.xlsx'))
    submit()
    submit()
    expect(create).toHaveBeenCalledTimes(1)
    expect(input().disabled).toBe(true)
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Quitar two.xlsx',
      }).disabled,
    ).toBe(true)
    select(file('ignored.pdf'))
    expect(screen.queryByText('ignored.pdf')).toBeNull()
    await act(async () => first.resolve())
    expect(create).toHaveBeenCalledTimes(1)
    expect(onQueueStateChange).toHaveBeenLastCalledWith({
      pendingCount: 1,
      busy: true,
    })
    await act(async () => refresh.resolve())
    await waitFor(() =>
      expect(onQueueStateChange).toHaveBeenLastCalledWith({
        pendingCount: 0,
        busy: false,
      }),
    )
    expect(onUploaded).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('one.pdf')).toBeNull()
  })
  it('retains only failures and retries only the explicitly selected file', async () => {
    create
      .mockResolvedValueOnce({} as never)
      .mockRejectedValueOnce(new Error('network'))
    const onUploaded = vi.fn()
    setup({ onUploaded })
    select(file('saved.xlsx'), file('failed.pdf'))
    submit()
    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1))
    expect(screen.queryByText('saved.xlsx')).toBeNull()
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Subir archivos',
      }).disabled,
    ).toBe(true)
    fireEvent.click(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Reintentar failed.pdf',
      }),
    )
    await waitFor(() => expect(create).toHaveBeenCalledTimes(3))
    expect(create.mock.calls.map((call) => call[2].file.name)).toEqual([
      'saved.xlsx',
      'failed.pdf',
      'failed.pdf',
    ])
  })
  it('shows server validation errors for the failed file', async () => {
    create.mockRejectedValueOnce(new ApiError(400, 'Documento inválido', null))
    setup()
    select(file('invalid.pdf'))
    submit()
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('Documento inválido'),
    )
  })
  it('never retries a saved file when refresh fails', async () => {
    setup({ onUploaded: vi.fn().mockRejectedValue(new Error('refresh')) })
    select(file('saved.pdf'))
    submit()
    await waitFor(() => expect(input().disabled).toBe(false))
    expect(screen.queryByText('saved.pdf')).toBeNull()
    expect(create).toHaveBeenCalledTimes(1)
  })
  it('honors disabled and ignores drops while disabled', () => {
    setup({ disabled: true })
    select(file('ignored.pdf'))
    fireEvent.drop(
      screen.getByRole<HTMLButtonElement>('button', {
        name: /Arrastra archivos/,
      }),
      {
        dataTransfer: { files: [file('drop.pdf')] },
      },
    )
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
    submit()
    view.unmount()
    const notifications = onQueueStateChange.mock.calls.length
    await act(async () => first.resolve())
    expect(create).toHaveBeenCalledTimes(1)
    expect(onUploaded).not.toHaveBeenCalled()
    expect(onQueueStateChange).toHaveBeenCalledTimes(notifications)
  })
})

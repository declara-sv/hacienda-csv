// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GenerationHistory } from './GenerationHistory'
import type { GenerationRun } from '#/lib/api-types'
import { I18nProvider } from '#/i18n/I18nProvider'
import { formatDateTime } from '#/lib/format'

afterEach(cleanup)

function run(
  version: number,
  overrides: Partial<GenerationRun> = {},
): GenerationRun {
  return {
    id: `run-${version}`,
    filingPeriodId: 'period',
    version,
    status: 'Completed',
    errorMessage: null,
    createdAtUtc: '2026-09-01T12:00:00Z',
    startedAtUtc: '2026-09-01T12:01:00Z',
    completedAtUtc: '2026-09-01T12:02:00Z',
    files: [],
    artifacts: [
      {
        id: `csv-${version}`,
        artifactKind: 'Csv',
        fileName: `version-${version}.csv`,
        createdAtUtc: '2026-09-01T12:02:00Z',
        sizeBytes: 100,
      },
    ],
    ...overrides,
  }
}
function show(
  props: Partial<React.ComponentProps<typeof GenerationHistory>> = {},
) {
  return render(
    <I18nProvider>
      <GenerationHistory runs={[]} onDownload={vi.fn()} {...props} />
    </I18nProvider>,
  )
}

describe('GenerationHistory', () => {
  it('sorts versions newest first without mutating input and highlights latest completed independently', () => {
    const runs = [
      run(1),
      run(3, {
        status: 'Failed',
        errorMessage: 'No se pudo generar',
        artifacts: [],
      }),
      run(2),
    ]
    show({ runs })
    const items = screen.getAllByRole('article')
    expect(
      items.map((item) => within(item).getByRole('heading').textContent),
    ).toEqual(['Versión 3', 'Versión 2', 'Versión 1'])
    expect(within(items[1]).getByText('Último CSV generado')).toBeTruthy()
    expect(within(items[0]).queryByText('Último CSV generado')).toBeNull()
    expect(screen.getByText('No se pudo generar')).toBeTruthy()
    expect(runs.map((item) => item.version)).toEqual([1, 3, 2])
  })
  it('shows all run timestamps and status', () => {
    const item = run(1)
    show({ runs: [item] })
    expect(screen.getByText('Completado')).toBeTruthy()
    expect(
      screen.getByText(`Creada ${formatDateTime(item.createdAtUtc)}`),
    ).toBeTruthy()
    expect(
      screen.getByText(`Iniciada ${formatDateTime(item.startedAtUtc!)}`),
    ).toBeTruthy()
    expect(
      screen.getByText(`Finalizada ${formatDateTime(item.completedAtUtc!)}`),
    ).toBeTruthy()
  })
  it('warns outside collapsed details when completed output omits failed files', () => {
    show({
      runs: [
        run(1, {
          files: [
            {
              uploadId: null,
              originalFileName: 'bad.pdf',
              sourceFileKind: 'PDF',
              status: 'Failed',
              errorMessage: 'PDF ilegible',
            },
          ],
        }),
      ],
    })
    const warning = screen.getByRole('alert')
    expect(warning.textContent).toContain(
      '1 archivo(s) no se incluyeron en este CSV',
    )
    expect(warning.closest('details')).toBeNull()
    const details = screen
      .getByText('Archivos de esta versión (1)')
      .closest('details')!
    expect(details.open).toBe(false)
    fireEvent.click(within(details).getByText('Archivos de esta versión (1)'))
    expect(details.open).toBe(true)
    expect(within(details).getByText('PDF ilegible')).toBeTruthy()
  })
  it('retains deleted snapshots and duplicate names and translates each file status', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    show({
      runs: [
        run(1, {
          files: ['Pending', 'Included', 'Failed'].map((status) => ({
            uploadId: null,
            originalFileName: 'duplicate.pdf',
            sourceFileKind: 'PDF',
            status: status as 'Pending' | 'Included' | 'Failed',
            errorMessage: null,
          })),
        }),
      ],
    })
    const details = screen
      .getByText('Archivos de esta versión (3)')
      .closest('details')!
    expect(within(details).getAllByText('duplicate.pdf')).toHaveLength(3)
    for (const status of ['Pendiente', 'Incluido', 'Fallido'])
      expect(within(details).getByText(status)).toBeTruthy()
    expect(error).not.toHaveBeenCalled()
    error.mockRestore()
  })
  it('renders an accessible loading state without empty text', () => {
    show({ isLoading: true })
    expect(screen.getByRole('status').textContent).toContain('Cargando')
    expect(screen.queryByText('Todavía no has generado un CSV.')).toBeNull()
  })
  it('renders an empty state', () => {
    show()
    expect(screen.getByText('Todavía no has generado un CSV.')).toBeTruthy()
  })
  it('renders load errors with retry, without claiming the history is empty', () => {
    const onRetry = vi.fn()
    show({ error: 'Servicio no disponible', onRetry })
    expect(screen.getByRole('alert').textContent).toContain(
      'Servicio no disponible',
    )
    expect(screen.queryByText('Todavía no has generado un CSV.')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
  it('keeps known runs visible on refresh errors', () => {
    show({ runs: [run(1)], error: 'No se pudo actualizar' })
    expect(screen.getByRole('article')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain(
      'No se pudo actualizar',
    )
  })
  it('downloads historical artifacts and marks only the active artifact busy', () => {
    const onDownload = vi.fn()
    const old = run(1)
    show({
      runs: [run(2), old],
      onDownload,
      downloadingArtifactIds: new Set(['csv-2']),
    })
    const buttons = screen.getAllByRole('button')
    expect(buttons[0].getAttribute('aria-busy')).toBe('true')
    expect(buttons[0].hasAttribute('disabled')).toBe(true)
    expect(buttons[1].hasAttribute('disabled')).toBe(false)
    fireEvent.click(buttons[1])
    expect(onDownload).toHaveBeenCalledWith(old.artifacts[0])
  })
})

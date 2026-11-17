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
import { PeriodDocuments } from './PeriodDocuments'
import { I18nProvider } from '#/i18n/I18nProvider'
import {
  ApiError,
  catalogsApi,
  documentsApi,
  runsApi,
  uploadsApi,
} from '#/lib/api-client'
import { documentDto, rentaCatalog } from '#/test/fixtures'
import type * as ApiClient from '#/lib/api-client'
import type { GenerationRun, GenerationRunFile, Upload } from '#/lib/api-types'

vi.mock('#/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiClient>()),
  uploadsApi: {
    list: vi.fn(),
    create: vi.fn(),
    remove: vi.fn(),
    reextract: vi.fn(),
    downloadArtifact: vi.fn(),
  },
  runsApi: { list: vi.fn(), create: vi.fn() },
  documentsApi: { list: vi.fn(), update: vi.fn(), bulkUpdate: vi.fn() },
  catalogsApi: { renta: vi.fn() },
}))

const listUploads = vi.mocked(uploadsApi.list)
const createUpload = vi.mocked(uploadsApi.create)
const removeUpload = vi.mocked(uploadsApi.remove)
const downloadArtifact = vi.mocked(uploadsApi.downloadArtifact)
const listRuns = vi.mocked(runsApi.list)
const createRun = vi.mocked(runsApi.create)
const reextractUpload = vi.mocked(uploadsApi.reextract)
const listDocuments = vi.mocked(documentsApi.list)
const rentaCatalogApi = vi.mocked(catalogsApi.renta)

function defer<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function upload(id: string, overrides: Partial<Upload> = {}): Upload {
  return {
    id,
    filingPeriodId: 'period',
    originalFileName: `${id}.xlsx`,
    sourceFileKind: 'Excel',
    contentType: 'application/vnd.ms-excel',
    sizeBytes: 2048,
    createdAtUtc: '2026-09-01T10:00:00Z',
    includedInLatestRun: false,
    extractionStatus: 'Completed',
    extractionError: null,
    documentsCount: 1,
    ...overrides,
  }
}

function runFile(
  overrides: Partial<GenerationRunFile> = {},
): GenerationRunFile {
  return {
    uploadId: null,
    originalFileName: 'snapshot.xlsx',
    sourceFileKind: 'Excel',
    status: 'Included',
    errorMessage: null,
    ...overrides,
  }
}

function run(version: number, overrides: Partial<GenerationRun> = {}) {
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
    issues: [],
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
  } satisfies GenerationRun
}

const pendingRun = (version: number) =>
  run(version, {
    status: 'Pending',
    startedAtUtc: null,
    completedAtUtc: null,
    artifacts: [],
  })

let client: QueryClient | null = null

function setup(props: { clientId?: string; periodId?: string } = {}) {
  client ??= new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <PeriodDocuments clientId="client" periodId="period" {...props} />
      </I18nProvider>
    </QueryClientProvider>,
  )
}

/**
 * Advance fake timers inside act. React Query schedules its store
 * notifications with setTimeout(0), so every flush must move the clock.
 */
async function tick(ms = 1) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

const button = (name: string | RegExp) =>
  screen.getByRole<HTMLButtonElement>('button', { name })
const generateButton = () => button('Generar anexos')

beforeEach(() => {
  vi.resetAllMocks()
  listUploads.mockResolvedValue([])
  listRuns.mockResolvedValue([])
  listDocuments.mockResolvedValue([documentDto('d1')])
  rentaCatalogApi.mockResolvedValue(rentaCatalog)
})

afterEach(() => {
  cleanup()
  client?.clear()
  client = null
  vi.useRealTimers()
})

describe('PeriodDocuments', () => {
  it('lists period documents with their membership in the latest completed generation', async () => {
    listUploads.mockResolvedValue([
      upload('u1', { includedInLatestRun: true }),
      upload('u2', { originalFileName: 'escaneo.pdf', sourceFileKind: 'PDF' }),
    ])
    listRuns.mockResolvedValue([run(1)])
    setup()

    const documents = await screen.findByRole('list', {
      name: 'Archivos del período',
    })
    const rows = within(documents).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('u1.xlsx')).toBeTruthy()
    expect(within(rows[0]).getByText('En la versión vigente')).toBeTruthy()
    expect(within(rows[1]).getByText('escaneo.pdf')).toBeTruthy()
    expect(
      within(rows[1]).getByText('No está en la versión vigente'),
    ).toBeTruthy()
    expect(within(rows[0]).getByText(/2 KB/)).toBeTruthy()
    // No per-upload processing status survives from the removed jobs model.
    expect(within(documents).queryByText('Procesando')).toBeNull()
    expect(within(documents).queryByText('Completado')).toBeNull()
  })

  it('shows a loading placeholder and then the empty documents state', async () => {
    const uploads = defer<Upload[]>()
    listUploads.mockReturnValue(uploads.promise)
    setup()

    expect(screen.getByText('Cargando documentos')).toBeTruthy()
    expect(screen.queryByText('Todavía no hay archivos en este período.')) //
      .toBeNull()

    await act(async () => uploads.resolve([]))
    await screen.findByText('Todavía no hay archivos en este período.')
    expect(
      screen.getByText('Todavía no has generado los anexos de este período.'),
    ).toBeTruthy()
  })

  it('shows a documents load error and retries the query', async () => {
    listUploads.mockRejectedValueOnce(
      new ApiError(500, 'No se pudo leer el período.', null),
    )
    listUploads.mockResolvedValue([upload('u1')])
    setup()

    await screen.findByText('No se pudo leer el período.')
    fireEvent.click(button('Reintentar'))

    await screen.findByText('u1.xlsx')
    expect(listUploads).toHaveBeenCalledTimes(2)
  })

  it('refreshes documents after an upload without ever creating a run', async () => {
    createUpload.mockResolvedValue(upload('u1'))
    setup()
    await screen.findByText('Todavía no hay archivos en este período.')
    expect(listUploads).toHaveBeenCalledTimes(1)

    // Picking a file uploads it right away; there is no submit step.
    listUploads.mockResolvedValue([upload('u1')])
    fireEvent.change(screen.getByLabelText('Elegir PDF'), {
      target: { files: [new File(['data'], 'nuevo.pdf')] },
    })

    await screen.findByText('u1.xlsx')
    expect(listUploads).toHaveBeenCalledTimes(2)
    expect(createRun).not.toHaveBeenCalled()
  })

  it('creates a version explicitly and keeps the action disabled while runs refetch', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    const created = defer<GenerationRun>()
    createRun.mockReturnValue(created.promise)
    setup()

    await screen.findByText('u1.xlsx')
    await waitFor(() => expect(generateButton().disabled).toBe(false))
    fireEvent.click(generateButton())

    await waitFor(() =>
      expect(createRun).toHaveBeenCalledWith('client', 'period'),
    )
    expect(button('Generando').disabled).toBe(true)

    const runsAfter = defer<GenerationRun[]>()
    listRuns.mockReturnValue(runsAfter.promise)
    await act(async () => created.resolve(pendingRun(1)))

    // Seeded from the response, so the guard holds while the refetch is inflight.
    await waitFor(() => expect(screen.getByRole('article')).toBeTruthy())
    expect(screen.getByText('Versión 1')).toBeTruthy()
    expect(generateButton().disabled).toBe(true)
    expect(
      screen.getByText('Ya hay una generación en curso. Espera a que termine.'),
    ).toBeTruthy()

    await act(async () => runsAfter.resolve([pendingRun(1)]))
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(generateButton().disabled).toBe(true)
  })

  it('explains every reason generation is unavailable', async () => {
    listUploads.mockResolvedValue([])
    setup()

    await screen.findByText(
      'Sube al menos un documento para generar los anexos.',
    )
    expect(generateButton().disabled).toBe(true)

    listUploads.mockResolvedValue([upload('u1')])
    fireEvent.click(button('Actualizar'))
    await screen.findByText('u1.xlsx')
    await waitFor(() => expect(generateButton().disabled).toBe(false))

    // A file still on its way to the server blocks generation.
    const attempt = defer<Upload>()
    createUpload.mockReturnValue(attempt.promise)
    fireEvent.change(screen.getByLabelText('Elegir PDF'), {
      target: { files: [new File(['data'], 'pendiente.pdf')] },
    })
    await screen.findByText(
      'Espera a que terminen los cambios sobre los documentos.',
    )
    expect(generateButton().disabled).toBe(true)

    // A rejected upload stays listed with its reason but blocks nothing.
    await act(async () => {
      attempt.reject(new ApiError(400, 'Archivo inválido', null))
      await attempt.promise.catch(() => {})
    })
    await screen.findByText('Archivo inválido')
    await waitFor(() => expect(generateButton().disabled).toBe(false))

    // A file the browser already rejects never blocks either.
    fireEvent.change(screen.getByLabelText('Elegir PDF'), {
      target: { files: [new File(['data'], 'ventas.xlsx')] },
    })
    expect(screen.getByText('Solo se aceptan PDF.')).toBeTruthy()
    expect(generateButton().disabled).toBe(false)
    expect(createRun).not.toHaveBeenCalled()
  })

  it('blocks uploads and deletions while the create-run request is pending', async () => {
    listUploads.mockResolvedValue([upload('u1'), upload('u2')])
    createRun.mockReturnValue(defer<GenerationRun>().promise)
    setup()

    await screen.findByText('u1.xlsx')
    await waitFor(() => expect(generateButton().disabled).toBe(false))
    // An open confirmation must not become a deletion mid-snapshot either.
    fireEvent.click(button('Eliminar u1.xlsx'))
    fireEvent.click(generateButton())

    // React Query publishes the pending state on its own tick.
    await waitFor(() =>
      expect(
        screen.getByLabelText<HTMLInputElement>('Elegir PDF').disabled,
      ).toBe(true),
    )
    expect(button('Eliminar u2.xlsx').disabled).toBe(true)
    expect(button('Sí, eliminar').disabled).toBe(true)

    fireEvent.click(button('Sí, eliminar'))
    fireEvent.click(button('Eliminar u2.xlsx'))
    expect(removeUpload).not.toHaveBeenCalled()
    // A second activation while the POST is inflight must not start a run.
    fireEvent.click(button('Generando'))
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1))
  })

  it('blocks generation while a document deletion is still pending', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    const removed = defer<void>()
    removeUpload.mockReturnValue(removed.promise)
    setup()

    await screen.findByText('u1.xlsx')
    await waitFor(() => expect(generateButton().disabled).toBe(false))
    fireEvent.click(button('Eliminar u1.xlsx'))
    fireEvent.click(button('Sí, eliminar'))

    await screen.findByText(
      'Espera a que terminen los cambios sobre los documentos.',
    )
    expect(generateButton().disabled).toBe(true)

    listUploads.mockResolvedValue([])
    await act(async () => removed.resolve())
    await screen.findByText(
      'Sube al menos un documento para generar los anexos.',
    )
    expect(createRun).not.toHaveBeenCalled()
  })

  it('refetches the period after a rejected generation, and dismisses it', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    createRun.mockRejectedValue(
      new ApiError(400, 'El período no tiene archivos para generar.', null),
    )
    setup()

    await screen.findByText('u1.xlsx')
    await waitFor(() => expect(generateButton().disabled).toBe(false))
    fireEvent.click(generateButton())

    await screen.findByText('El período no tiene archivos para generar.')
    // The server rejected our snapshot of the period; both lists are stale.
    await waitFor(() => expect(listUploads).toHaveBeenCalledTimes(2))
    expect(listRuns).toHaveBeenCalledTimes(2)
    expect(generateButton().disabled).toBe(false)

    fireEvent.click(button('Cerrar aviso'))
    expect(
      screen.queryByText('El período no tiene archivos para generar.'),
    ).toBeNull()
  })

  it('refetches documents and runs when generation conflicts with another session', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    createRun.mockRejectedValue(
      new ApiError(409, 'Ya existe una generación activa.', null),
    )
    setup()

    await screen.findByText('u1.xlsx')
    await waitFor(() => expect(generateButton().disabled).toBe(false))
    listRuns.mockResolvedValue([pendingRun(1)])
    fireEvent.click(generateButton())

    await screen.findByText('Ya existe una generación activa.')
    await waitFor(() => expect(screen.getByText('Versión 1')).toBeTruthy())
    expect(listUploads).toHaveBeenCalledTimes(2)
    expect(listRuns).toHaveBeenCalledTimes(2)
  })

  it('blocks generation while the run history cannot be loaded and retries it', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    listRuns.mockRejectedValueOnce(
      new ApiError(503, 'Servicio no disponible.', null),
    )
    listRuns.mockResolvedValue([])
    setup()

    await screen.findByText('Servicio no disponible.')
    expect(generateButton().disabled).toBe(true)
    expect(
      screen.getByText(
        'No pudimos cargar los datos del período. Actualiza antes de generar.',
      ),
    ).toBeTruthy()

    fireEvent.click(button('Reintentar'))
    await waitFor(() => expect(generateButton().disabled).toBe(false))
    expect(listRuns).toHaveBeenCalledTimes(2)
  })

  it('deletes a document after confirmation without losing the run history', async () => {
    listUploads.mockResolvedValue([upload('u1'), upload('u2')])
    listRuns.mockResolvedValue([run(1)])
    removeUpload.mockResolvedValue(undefined)
    setup()

    await screen.findByText('u1.xlsx')
    fireEvent.click(button('Eliminar u1.xlsx'))
    expect(screen.getByText('¿Eliminar este documento?')).toBeTruthy()
    expect(removeUpload).not.toHaveBeenCalled()

    listUploads.mockResolvedValue([upload('u2')])
    fireEvent.click(button('Sí, eliminar'))

    await waitFor(() => expect(screen.queryByText('u1.xlsx')).toBeNull())
    expect(removeUpload).toHaveBeenCalledWith('client', 'period', 'u1')
    expect(screen.getByText('u2.xlsx')).toBeTruthy()
    expect(screen.getByText('Versión 1')).toBeTruthy()
    expect(listRuns).toHaveBeenCalledTimes(1)
  })

  it('cancels a deletion without calling the API', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    setup()

    await screen.findByText('u1.xlsx')
    fireEvent.click(button('Eliminar u1.xlsx'))
    fireEvent.click(button('Cancelar'))

    expect(screen.queryByText('¿Eliminar este documento?')).toBeNull()
    expect(button('Eliminar u1.xlsx').disabled).toBe(false)
    expect(removeUpload).not.toHaveBeenCalled()
  })

  it('keeps keyboard focus on the delete confirmation and restores it on cancel', async () => {
    listUploads.mockResolvedValue([upload('u1'), upload('u2')])
    setup()

    await screen.findByText('u1.xlsx')
    const trigger = button('Eliminar u1.xlsx')
    trigger.focus()
    fireEvent.click(trigger)

    // The trigger unmounts when the confirmation opens; without an explicit
    // move, focus falls back to <body> and keyboard users lose their place.
    expect(document.activeElement).toBe(button('Sí, eliminar'))

    fireEvent.click(button('Cancelar'))

    expect(document.activeElement).toBe(button('Eliminar u1.xlsx'))
  })

  it('moves focus to the next document once a deletion removes the row', async () => {
    listUploads.mockResolvedValue([upload('u1'), upload('u2')])
    removeUpload.mockResolvedValue(undefined)
    setup()

    await screen.findByText('u1.xlsx')
    fireEvent.click(button('Eliminar u1.xlsx'))
    listUploads.mockResolvedValue([upload('u2')])
    fireEvent.click(button('Sí, eliminar'))

    // The deleted row unmounts on refetch; focus must land on a survivor.
    await waitFor(() => expect(screen.queryByText('u1.xlsx')).toBeNull())
    expect(document.activeElement).toBe(button('Eliminar u2.xlsx'))
  })

  it('falls back to the previous document when the last row is deleted', async () => {
    listUploads.mockResolvedValue([upload('u1'), upload('u2')])
    removeUpload.mockResolvedValue(undefined)
    setup()

    await screen.findByText('u2.xlsx')
    fireEvent.click(button('Eliminar u2.xlsx'))
    listUploads.mockResolvedValue([upload('u1')])
    fireEvent.click(button('Sí, eliminar'))

    await waitFor(() => expect(screen.queryByText('u2.xlsx')).toBeNull())
    expect(document.activeElement).toBe(button('Eliminar u1.xlsx'))
  })

  it('moves focus to the file picker when the last document is deleted', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    removeUpload.mockResolvedValue(undefined)
    setup()

    await screen.findByText('u1.xlsx')
    fireEvent.click(button('Eliminar u1.xlsx'))
    listUploads.mockResolvedValue([])
    fireEvent.click(button('Sí, eliminar'))

    await screen.findByText('Todavía no hay archivos en este período.')
    expect(document.activeElement).toBe(screen.getByLabelText('Elegir PDF'))
  })

  it('disables deletion only for documents referenced by an active run', async () => {
    listUploads.mockResolvedValue([upload('u1'), upload('u2')])
    listRuns.mockResolvedValue([
      run(2, {
        status: 'Running',
        completedAtUtc: null,
        artifacts: [],
        files: [
          runFile({ uploadId: 'u1', originalFileName: 'instantanea.xlsx' }),
          runFile({ uploadId: null, originalFileName: 'borrado.xlsx' }),
        ],
      }),
    ])
    setup()

    await screen.findByText('u1.xlsx')
    expect(button('Eliminar u1.xlsx').disabled).toBe(true)
    expect(button('Eliminar u2.xlsx').disabled).toBe(false)
    expect(
      screen.getByText(
        'No se puede eliminar mientras una generación en curso lo usa.',
      ),
    ).toBeTruthy()
  })

  it('locks an already-open confirmation once a run claims the document', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    setup()

    await screen.findByText('u1.xlsx')
    fireEvent.click(button('Eliminar u1.xlsx'))
    expect(button('Sí, eliminar').disabled).toBe(false)

    // Another session starts a run over this document while the prompt is open.
    listRuns.mockResolvedValue([
      run(2, {
        status: 'Running',
        completedAtUtc: null,
        artifacts: [],
        files: [runFile({ uploadId: 'u1' })],
      }),
    ])
    fireEvent.click(button('Actualizar'))

    await waitFor(() => expect(button('Sí, eliminar').disabled).toBe(true))
    fireEvent.click(button('Sí, eliminar'))
    expect(removeUpload).not.toHaveBeenCalled()
    expect(
      screen.getByText(
        'No se puede eliminar mientras una generación en curso lo usa.',
      ),
    ).toBeTruthy()
  })

  it('presents a delete conflict and refetches both queries', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    removeUpload.mockRejectedValue(
      new ApiError(409, 'El documento está en uso por una generación.', null),
    )
    setup()

    await screen.findByText('u1.xlsx')
    fireEvent.click(button('Eliminar u1.xlsx'))
    fireEvent.click(button('Sí, eliminar'))

    await screen.findByText('El documento está en uso por una generación.')
    expect(screen.getByText('u1.xlsx')).toBeTruthy()
    // The row survives a failed delete, so the keyboard stays on its trigger.
    expect(document.activeElement).toBe(button('Eliminar u1.xlsx'))
    await waitFor(() => expect(listUploads).toHaveBeenCalledTimes(2))
    expect(listRuns).toHaveBeenCalledTimes(2)
  })

  it('polls an active run and refreshes document flags once it completes', async () => {
    vi.useFakeTimers()
    listUploads.mockResolvedValue([upload('u1')])
    listRuns.mockResolvedValue([pendingRun(1)])
    setup()
    await tick()

    // Before any version exists there is no membership to report.
    expect(screen.queryByText('No está en la versión vigente')).toBeNull()
    expect(listRuns).toHaveBeenCalledTimes(1)
    expect(listUploads).toHaveBeenCalledTimes(1)

    listRuns.mockResolvedValue([
      run(1, { files: [runFile({ uploadId: 'u1' })] }),
    ])
    listUploads.mockResolvedValue([upload('u1', { includedInLatestRun: true })])
    await tick(5000)
    await tick()

    expect(listRuns).toHaveBeenCalledTimes(2)
    expect(listUploads).toHaveBeenCalledTimes(2)
    expect(screen.getByText('En la versión vigente')).toBeTruthy()

    // Terminal runs stop polling and stop invalidating documents.
    await tick(15000)
    expect(listRuns).toHaveBeenCalledTimes(2)
    expect(listUploads).toHaveBeenCalledTimes(2)
    expect(generateButton().disabled).toBe(false)
  })

  it('keeps older CSVs downloadable after a newer run fails and reports download errors', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    listRuns.mockResolvedValue([
      run(2, {
        status: 'Failed',
        errorMessage: 'La generación falló.',
        artifacts: [],
      }),
      run(1, {
        files: [
          runFile({ status: 'Failed', originalFileName: 'roto.pdf' }),
          runFile(),
        ],
      }),
    ])
    const started = defer<void>()
    downloadArtifact.mockReturnValue(started.promise)
    setup()

    await screen.findByText('La generación falló.')
    expect(
      screen.getByText(
        '1 archivo(s) no entraron en esta versión. Revisa los errores de abajo.',
      ),
    ).toBeTruthy()

    const download = button('Descargar version-1.csv')
    fireEvent.click(download)
    await waitFor(() =>
      expect(downloadArtifact).toHaveBeenCalledWith('csv-1', 'version-1.csv'),
    )
    expect(download.getAttribute('aria-busy')).toBe('true')

    await act(async () => {
      started.reject(new ApiError(404, 'El archivo ya no existe.', null))
      await started.promise.catch(() => {})
    })
    await screen.findByText('El archivo ya no existe.')
    expect(button('Descargar version-1.csv').disabled).toBe(false)
  })

  it('keeps a separate cache per period and drops local state on remount', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    createRun.mockRejectedValue(new ApiError(400, 'Período cerrado.', null))
    const view = setup({ periodId: 'period-1' })

    await screen.findByText('u1.xlsx')
    fireEvent.change(screen.getByLabelText('Elegir PDF'), {
      target: { files: [new File(['data'], 'pendiente.xlsx')] },
    })
    expect(screen.getByText('pendiente.xlsx')).toBeTruthy()
    await waitFor(() => expect(generateButton().disabled).toBe(false))
    fireEvent.click(generateButton())
    await screen.findByText('Período cerrado.')
    expect(listUploads).toHaveBeenCalledWith('client', 'period-1')

    view.unmount()
    listUploads.mockResolvedValue([upload('otro')])
    setup({ periodId: 'period-2' })

    await screen.findByText('otro.xlsx')
    expect(listUploads).toHaveBeenCalledWith('client', 'period-2')
    expect(screen.queryByText('u1.xlsx')).toBeNull()
    expect(screen.queryByText('Período cerrado.')).toBeNull()
    expect(screen.queryByText('pendiente.xlsx')).toBeNull()
  })

  it('shows the extraction status of each file', async () => {
    listUploads.mockResolvedValue([
      upload('a', { extractionStatus: 'Pending', documentsCount: 0 }),
      upload('b', { extractionStatus: 'Running', documentsCount: 0 }),
      upload('c', { extractionStatus: 'Completed', documentsCount: 3 }),
      upload('d', { extractionStatus: 'Completed', documentsCount: 1 }),
      upload('e', {
        extractionStatus: 'Failed',
        extractionError: 'El PDF no tiene texto legible.',
        documentsCount: 0,
      }),
    ])
    setup()

    const list = await screen.findByRole('list', {
      name: 'Archivos del período',
    })
    const items = within(list).getAllByRole('listitem')
    expect(within(items[0]).getByText('En cola para leer')).toBeTruthy()
    expect(within(items[1]).getByText('Leyendo el archivo')).toBeTruthy()
    expect(within(items[2]).getByText('Leído: 3 documentos')).toBeTruthy()
    expect(within(items[3]).getByText('Leído: 1 documento')).toBeTruthy()
    expect(
      within(items[4]).getByText('No se pudo leer el archivo'),
    ).toBeTruthy()
    expect(
      within(items[4]).getByText('El PDF no tiene texto legible.'),
    ).toBeTruthy()
    // Only failed files offer to read again.
    expect(
      within(items[2]).queryByRole('button', { name: /Volver a leer/ }),
    ).toBeNull()
    expect(
      within(items[4]).getByRole('button', { name: 'Volver a leer e.xlsx' }),
    ).toBeTruthy()
  })

  it('reads a failed file again and refreshes files and documents', async () => {
    listUploads.mockResolvedValue([
      upload('u1', {
        extractionStatus: 'Failed',
        extractionError: 'Plantilla desconocida.',
      }),
    ])
    reextractUpload.mockResolvedValue(
      upload('u1', { extractionStatus: 'Pending' }),
    )
    setup()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Volver a leer u1.xlsx' }),
    )
    await waitFor(() =>
      expect(reextractUpload).toHaveBeenCalledWith('client', 'period', 'u1'),
    )
    await waitFor(() => expect(listUploads).toHaveBeenCalledTimes(2))
    expect(listDocuments).toHaveBeenCalledTimes(2)
  })

  it('reports a failed re-read', async () => {
    listUploads.mockResolvedValue([
      upload('u1', { extractionStatus: 'Failed' }),
    ])
    reextractUpload.mockRejectedValue(
      new ApiError(409, 'El archivo ya se está leyendo.', null),
    )
    setup()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Volver a leer u1.xlsx' }),
    )
    await screen.findByText('El archivo ya se está leyendo.')
  })

  it('polls files and documents while extraction runs and blocks generation', async () => {
    vi.useFakeTimers()
    listUploads.mockResolvedValue([
      upload('u1', { extractionStatus: 'Running', documentsCount: 0 }),
    ])
    listDocuments.mockResolvedValue([])
    setup()
    await tick()

    expect(screen.getByText('Leyendo el archivo')).toBeTruthy()
    expect(
      screen.getByText('Espera a que termine la lectura de los archivos.'),
    ).toBeTruthy()
    expect(generateButton().disabled).toBe(true)
    expect(listUploads).toHaveBeenCalledTimes(1)
    expect(listDocuments).toHaveBeenCalledTimes(1)

    await tick(3000)
    expect(listUploads).toHaveBeenCalledTimes(2)
    expect(listDocuments).toHaveBeenCalledTimes(2)

    listUploads.mockResolvedValue([
      upload('u1', { extractionStatus: 'Completed', documentsCount: 1 }),
    ])
    listDocuments.mockResolvedValue([documentDto('d1')])
    await tick(3000)
    await tick()

    expect(screen.getByText('Leído: 1 documento')).toBeTruthy()
    // Finishing re-reads the documents one last time, then polling stops.
    const documentsCalls = listDocuments.mock.calls.length
    expect(documentsCalls).toBeGreaterThanOrEqual(3)
    expect(generateButton().disabled).toBe(false)

    await tick(15000)
    expect(listUploads).toHaveBeenCalledTimes(3)
    expect(listDocuments).toHaveBeenCalledTimes(documentsCalls)
  })

  it('blocks generation while included documents have errors, not for excluded ones', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    const failing = documentDto('d2', {
      status: 'Error',
      issues: [
        {
          code: 'period',
          severity: 'Error',
          message: 'Fuera del período',
          field: null,
        },
      ],
    })
    listDocuments.mockResolvedValue([documentDto('d1'), failing])
    setup()

    await screen.findByText(
      'Corrige o excluye 1 documento con error para generar.',
    )
    expect(generateButton().disabled).toBe(true)

    listDocuments.mockResolvedValue([
      documentDto('d1'),
      { ...failing, excluded: true },
    ])
    fireEvent.click(button('Actualizar'))
    await waitFor(() => expect(generateButton().disabled).toBe(false))
  })

  it('blocks generation when every document is excluded', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    listDocuments.mockResolvedValue([documentDto('d1', { excluded: true })])
    setup()

    await screen.findByText(
      'No hay documentos incluidos. Incluye al menos uno para generar.',
    )
    expect(generateButton().disabled).toBe(true)
  })

  it('shows the review table for the period documents', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    listDocuments.mockResolvedValue([
      documentDto('d1', { receptorNombre: 'Consumidor final' }),
    ])
    setup()

    const table = await screen.findByRole('table', {
      name: 'Documentos leídos del período',
    })
    expect(within(table).getByText('Consumidor final')).toBeTruthy()
  })
  it('warns in the generate bar about files that could not be read', async () => {
    listUploads.mockResolvedValue([
      upload('u1'),
      upload('roto', {
        extractionStatus: 'Failed',
        extractionError: 'El PDF no tiene texto legible.',
        documentsCount: 0,
      }),
    ])
    listDocuments.mockResolvedValue([documentDto('d1')])
    setup()

    const bar = await screen.findByRole('region', { name: 'Generar anexos' })
    await within(bar).findByText('Listo para generar con 1 documento incluido.')
    expect(
      within(bar).getByText(
        '1 archivo no se pudo leer y no entrará en los anexos.',
      ),
    ).toBeTruthy()
    expect(generateButton().disabled).toBe(false)
    const status = screen.getByLabelText('Estado del período')
    expect(within(status).getByText('1 no se pudo leer')).toBeTruthy()
  })

  it('folds read files in long months and keeps failures in view', async () => {
    listUploads.mockResolvedValue([
      ...['a', 'b', 'c', 'd', 'e', 'f'].map((id) => upload(id)),
      upload('roto', { extractionStatus: 'Failed', documentsCount: 0 }),
    ])
    setup()

    const list = await screen.findByRole('list', {
      name: 'Archivos del período',
    })
    await waitFor(() =>
      expect(within(list).getAllByRole('listitem')).toHaveLength(1),
    )
    expect(within(list).getByText('roto.xlsx')).toBeTruthy()

    fireEvent.click(button('Mostrar 6 archivos leídos'))
    expect(within(list).getAllByRole('listitem')).toHaveLength(7)
    expect(
      button('Ocultar archivos leídos').getAttribute('aria-expanded'),
    ).toBe('true')
  })

  it('jumps to the documents with errors from the generate bar', async () => {
    listUploads.mockResolvedValue([upload('u1')])
    listDocuments.mockResolvedValue([
      documentDto('d1', { receptorNombre: 'Correcto' }),
      documentDto('d2', {
        receptorNombre: 'Con error',
        status: 'Error',
        issues: [
          { code: 'x', severity: 'Error', message: 'Falla', field: null },
        ],
      }),
    ])
    setup()

    fireEvent.click(await screen.findByRole('button', { name: 'Ver errores' }))
    expect(screen.getByLabelText<HTMLSelectElement>('Estado').value).toBe(
      'Error',
    )
    const table = screen.getByRole('table', {
      name: 'Documentos leídos del período',
    })
    expect(within(table).queryByText('Correcto')).toBeNull()
    expect(within(table).getByText('Con error')).toBeTruthy()
  })
})

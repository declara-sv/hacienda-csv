import type { DocumentDto, RentaCatalog } from '#/lib/api-types'

export const rentaCatalog: RentaCatalog = {
  tipoOperacion: [
    { code: '1', label: 'Gravada' },
    { code: '2', label: 'No gravada o exenta' },
  ],
  tipoIngreso: [
    { code: '3', label: 'Comercial' },
    { code: '4', label: 'Servicios' },
  ],
}

export function documentDto(
  id: string,
  overrides: Partial<DocumentDto> = {},
): DocumentDto {
  return {
    id,
    uploadId: 'u1',
    originalFileName: `${id}.pdf`,
    extractionMethod: 'Parser',
    status: 'Ok',
    issues: [],
    edited: false,
    excluded: false,
    tipoDte: '01',
    codigoGeneracion: `0F9A1B2C-3D4E-5F60-7182-93A4B5C6D7${id.padStart(2, '0').slice(-2)}`,
    numeroControl: `DTE-01-M001P001-0000000000000${id.padStart(2, '0').slice(-2)}`,
    selloRecepcion: '2025ABCDEF',
    fechaEmision: '2025-10-05',
    horaEmision: '10:15:00',
    emisorNombre: 'Cliente S.A. de C.V.',
    emisorNit: '0614-010101-101-1',
    emisorNrc: '123456-7',
    receptorNombre: `Receptor ${id}`,
    receptorNit: null,
    receptorNrc: null,
    receptorDui: '01234567-8',
    totalNoSujetas: '0.00',
    totalExentas: '0.00',
    totalGravadas: '48.14',
    iva: '0.00',
    ivaRetenido: '0.00',
    total: '48.14',
    tipoOperacionRenta: null,
    tipoIngresoRenta: null,
    effectiveTipoOperacion: '1',
    effectiveTipoIngreso: '3',
    anexo: 2,
    ...overrides,
  }
}

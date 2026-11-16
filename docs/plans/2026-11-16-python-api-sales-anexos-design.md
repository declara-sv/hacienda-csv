# API en Python + anexos de ventas F-07 (diseño)

Fecha: 2026-11-16 · Estado: en implementación (rama `feat/python-api-sales-anexos`)

## Objetivo

Reemplazar el API .NET por uno en Python y convertir el generador placeholder en el flujo real:

1. El contador sube los PDF de DTE de un cliente para un período (mes).
2. Cada PDF se lee automáticamente: parser determinístico para la plantilla del sistema de facturación
   del MH; IA (Claude) solo como respaldo.
3. Los documentos aparecen en una tabla de revisión editable (con valores por defecto del cliente para los
   códigos de Renta, editables por documento).
4. Se generan los CSV del Anexo 1 (ventas a contribuyentes) y Anexo 2 (ventas a consumidor final),
   versionados en cada regeneración.

Fuera de alcance por ahora: Anexo 3 (compras), anulados, editor de lineamientos (la especificación de
columnas queda como datos para habilitarlo después).

## Stack

- Python 3.13, FastAPI, SQLAlchemy 2 (sync), Alembic, psycopg 3, Pydantic 2, uv.
- PDF: `pdfplumber` (texto con coordenadas). IA: SDK oficial `anthropic`, modelo configurable
  (`AI_EXTRACTION_MODEL`, por defecto `claude-opus-5-5`), salida estructurada.
- Postgres; almacenamiento local o Azure Blob (igual que antes).
- El worker corre dentro del proceso del API (hilo) y reclama trabajos con `FOR UPDATE SKIP LOCKED`.
- El código .NET se retiró en esta rama. No hay datos de producción (el único deploy falló), así que el esquema es nuevo (snake_case).

## Estructura (`apps/api`)

```text
app/
  domain.py          # contrato compartido: DteRecord, Issue, ClientProfile, ReviewedDocument, ...
  config.py db.py models.py
  extraction/        # PDF -> ExtractionResult (parser MH + respaldo IA) y validaciones del documento
  anexos/            # especificación F-07 como datos, catálogos de Renta, builder y escritor CSV
  api/               # routers FastAPI
  services/          # lógica de casos de uso (cuentas, alcance por cuenta, uploads, documentos, runs)
  usage/             # registro de uso (eventos) y tabla de precios de IA
  storage/           # Local / Azure Blob
  worker.py          # extracción de uploads + procesamiento de generation runs
alembic/
tests/
```

## Contrato entre módulos

`app/domain.py` es la frontera. Funciones públicas:

```python
# app/extraction/__init__.py
def extract_pdf(pdf_bytes: bytes, *, ai: AiExtractor | None) -> ExtractionResult
def validate_record(record: DteRecord) -> list[Issue]
def validate_in_period(record: DteRecord, *, year: int, month: int, client: ClientProfile) -> list[Issue]
def find_duplicate_codes(items: list[tuple[str, str | None]]) -> dict[str, list[Issue]]  # id -> issues

# app/anexos/__init__.py
def build_sales_anexos(*, year: int, month: int, client: ClientProfile,
                       documents: list[ReviewedDocument]) -> AnexoBuildResult
def validate_for_anexo(document: ReviewedDocument, *, year: int, month: int,
                       client: ClientProfile) -> list[Issue]
RENTA_CATALOG: dict  # {"tipoOperacion": [{"code","label"}], "tipoIngreso": [...]}
```

## Reglas de extracción

- Plantilla MH (JasperReports, encabezado `DOCUMENTO TRIBUTARIO ELECTRÓNICO`): se leen etiquetas por
  posición. Emisor y receptor están lado a lado, así que se separan por columna (coordenada x).
- Identificadores se guardan tal como aparecen: el código de generación conserva los guiones.
- Respaldo IA cuando: la plantilla no se reconoce, el PDF no tiene texto (escaneado), faltan campos
  requeridos o los montos no cuadran. El resultado de la IA pasa por las mismas validaciones.
- Validaciones del documento (Error bloquea la generación, Warning no):
  - formato de código de generación (UUID), número de control (`DTE-NN-XXXXXXXX-NNNNNNNNNNNNNNN`), fecha;
  - `no sujetas + exentas + gravadas + IVA = total` (±0.01);
  - CCF: `IVA ≈ gravadas × 13%` (Warning si difiere más de 0.01);
  - fecha fuera del período (Error); emisor distinto del NIT/NRC del cliente (Error: no es una venta);
  - código de generación repetido en el período (Error en cada copia hasta excluir una);
  - tipos que no van a anexos de ventas (04, 07, 11, 14, ...) quedan como Warning y no se exportan.

## Reglas de anexos (ver skill `iva-anexos-dgii-compliance`)

- CSV separado por `;`, sin encabezado, CRLF, codificación Windows-1252, nombre ≤ 25 caracteres
  (`anexo1_202610.csv`, `anexo2_202610.csv`). Montos con 2 decimales, punto decimal, sin separador de miles.
- Anexo 2 (tipo 01): una fila por (fecha, códigos de Renta). H/I = código de generación del primer/último
  DTE del día (orden por fecha y hora de emisión), D–G = `N/A`, J vacío, K exentas, M no sujetas,
  N gravadas (IVA incluido), T suma, U/V Renta, W = 2.
- Anexo 1 (tipos 03/05/06): una fila por documento. D número de control, E sello, F código de generación
  (tal como aparecen; la especificación permite activar "quitar guiones" por columna), H NIT del receptor
  (14 dígitos sin guiones; 13 dígitos se completa con 0; 9 dígitos se trata como DUI y va en Q),
  J exentas, K no sujetas, L gravadas, M débito fiscal, P suma, R/S Renta, T = 1.
- Desde 01/2025 los códigos de Renta son obligatorios: documento sin código efectivo = Error.
- La especificación de columnas vive en archivos de datos versionados (`app/anexos/specs/*.json`).

## API HTTP

Se mantiene el contrato que usa la web (rutas, JSON camelCase, errores tipo ProblemDetails
`{title, status, errors?}`; validación → 400 con `errors: {campo: [mensaje]}`). Cambios:

- Clientes: `nit`, `nrc`, `defaultTipoOperacion`, `defaultTipoIngreso` en crear/editar/detalle.
- Uploads: `UploadDto` agrega `extractionStatus`, `extractionError`, `documentsCount`.
  `POST .../uploads/{uploadId}/reextract` vuelve a leer el archivo (reemplaza sus documentos).
- Documentos (nuevo):
  - `GET  /api/clients/{c}/periods/{p}/documents` → `DocumentDto[]`
  - `PATCH /api/clients/{c}/periods/{p}/documents/{documentId}` → campos editables, `excluded`,
    `tipoOperacionRenta`, `tipoIngresoRenta` (null = usar el valor del cliente). Marca `edited`.
  - `POST /api/clients/{c}/periods/{p}/documents/bulk` → `{documentIds, tipoOperacionRenta?, tipoIngresoRenta?, excluded?}`
- Runs: crear devuelve 409 si hay extracciones en curso y 400 si no hay documentos incluidos o alguno
  incluido tiene Error. `GenerationRunDto` agrega `issues`. `OutputArtifactDto` agrega `rowCount`.
- Catálogo: `GET /api/catalogs/renta`.

`DocumentDto`: `id, uploadId, originalFileName, extractionMethod, status, issues[{code,severity,message,field}],
edited, excluded, tipoDte, codigoGeneracion, numeroControl, selloRecepcion, fechaEmision (YYYY-MM-DD),
horaEmision, emisorNombre, emisorNit, emisorNrc, receptorNombre, receptorNit, receptorNrc, receptorDui,
totalNoSujetas, totalExentas, totalGravadas, iva, ivaRetenido, total (montos como string "48.14"),
tipoOperacionRenta, tipoIngresoRenta, effectiveTipoOperacion, effectiveTipoIngreso, anexo (1 | 2 | null)`.

Los `issues` de un documento se recalculan al extraer, al editarlo, al editar el cliente y al listar
(duplicados y período dependen del conjunto).

## Cuentas y registro de uso

Pensado para que hoy lo use una sola persona y mañana varias personas de una misma firma contable, y
para registrar el uso desde ya y decidir precios con datos reales (no hay cobro).

- **Cuentas**: `accounts` (firma) y `account_members` (`Owner` | `Member`, único por cuenta y usuario).
  Los clientes pertenecen a la cuenta (`clients.account_id`), no al usuario. Registrarse crea, en una sola
  transacción, el usuario, una cuenta con su nombre completo y la membresía `Owner`.
- **Cuenta actual**: dependencia `CurrentAccount` → `(user_id, account_id)`. Sin encabezado se usa la
  membresía más antigua (hoy hay una sola). Con `X-Account-Id` debe ser una cuenta del usuario
  (403 si no; 400 si el identificador es inválido). Los recursos de otra cuenta siguen respondiendo 404.
  La respuesta de auth agrega `user.account: {id, name, role}`. No hay invitaciones todavía.
- **Registro de uso** (`usage_events`): tabla solo de inserción, **sin llaves foráneas** para que las filas
  sobrevivan al borrar uploads, clientes o cuentas; guarda `client_name` como foto del nombre. Se escribe
  en la misma transacción del cambio de negocio, dentro de un SAVEPOINT: si el insert del evento falla se
  registra en el log y la operación continúa.

  | Evento | Cuándo | Cantidades |
  | --- | --- | --- |
  | `upload_stored` | al crear el upload | `bytes` |
  | `extraction_completed` / `extraction_failed` | al guardar la lectura | método, `pages`, `documents`, `duration_ms`; error en `metadata` |
  | `ai_call` | cada llamada a Claude, también si el resultado se descarta o falla tras recibir respuesta | tokens (entrada, salida, caché lectura/escritura), `cost_usd`, `price_version`, `duration_ms`, `metadata.outcome` = `used` / `discarded` / `failed` |
  | `run_completed` | al completar una generación | `documents`, `rows` (suma de artefactos), `bytes`; `files` y `version` en `metadata` |
  | `artifact_downloaded` | al iniciar la descarga | `bytes` |

  El actor es el usuario que subió el archivo o pidió la generación/descarga. Re-extraer genera eventos
  nuevos (es un costo real). Si el upload se borra o se re-encola mientras se lee, los `ai_call` igual se
  registran (`metadata.resultDropped`).
- **Contrato de extracción**: `ExtractionResult` agrega `ai_calls: list[AiUsage]` y `page_count`
  (de pdfplumber). `AiExtractor.extract` devuelve `AiExtractorOutput(records, usage)` y
  `AiExtractionError` lleva `usage`. El extractor usa `messages.create` con `output_config` y valida el
  JSON localmente, para tener `response.usage` aun cuando la salida es un rechazo o no cumple el esquema.
- **Precios**: `app/usage/pricing.py`, tabla versionada (`PRICE_VERSION = "2026-11"`, USD por millón de
  tokens, `Decimal`). Modelo desconocido → `cost_usd` nulo (los tokens se guardan igual). Los tokens son la
  fuente de verdad para recalcular; los precios se verifican contra la página de precios de Anthropic
  cada vez que se actualizan.
- **Reportes**: vista `usage_monthly` (creada en la migración; autogenerate no compara vistas) agrupada por
  cuenta, cliente, mes UTC, tipo de evento, método y modelo. `GET /api/usage?year=&month=` devuelve
  totales por cliente y de la cuenta: `uploads`, `bytesStored`, `documentsExtracted {parser, ai, manual,
  total}`, `extractionsFailed`, `aiCalls`, tokens, `aiCostUsd` (texto con 6 decimales),
  `aiCallsUnpriced`, `runs`, `rowsGenerated`, `downloads`.

## Riesgos abiertos

- Solo hay muestras de Factura (01). El parser de CCF/NC/ND se escribe por etiquetas y cae a IA si no
  cuadra; hace falta un PDF de CCF real para afinarlo.
- Anexo 1 D/F: la skill indica quitar guiones; el uso actual del contador es copiarlos. Por defecto se
  copian tal cual y queda como opción de la especificación.
- Codificación del CSV (Windows-1252) a confirmar con una carga real al portal.
- Cloud Run limita CPU fuera de peticiones: el worker en proceso requiere CPU siempre asignada o
  instancias mínimas.

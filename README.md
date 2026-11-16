# HaciendaCSV

App contable (español-first) para contadores de El Salvador: lee los PDF de DTE de un cliente y genera
los CSV de los anexos de ventas del F-07 (Anexo 1 y Anexo 2).

## Stack
- Frontend: TanStack Start + TanStack Router + TanStack Query + TypeScript.
- Backend: Python 3.13 + FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL (psycopg 3), gestionado con `uv`.
- Auth: email/password + JWT access/refresh.
- Storage: implementación Local o Azure Blob (`STORAGE_PROVIDER`).
- Extracción: parser determinístico para la plantilla de DTE del MH + IA (Claude) de respaldo, opcional.
- Worker: hilo dentro del proceso del API; reclama trabajos con `FOR UPDATE SKIP LOCKED`.

Diseño: `docs/plans/2026-11-16-python-api-sales-anexos-design.md`.

## Estructura

```text
apps/
  web/                  # TanStack Start (UI en español)
  api/                  # API Python (uv)
    app/
      api/              # routers FastAPI
      extraction/       # PDF -> documento (parser MH + respaldo IA) y validaciones
      anexos/           # especificación F-07 como datos, catálogos de Renta, builder y CSV
      services/         # casos de uso
      storage/          # Local / Azure Blob
      worker.py         # extracción de uploads + generation runs
    alembic/            # migraciones
    tests/
    Dockerfile
docker-compose.yml      # PostgreSQL local opcional
```

## Variables de entorno

### Frontend (`apps/web/.env`)
```env
VITE_API_URL=http://localhost:5184
```

### API (`apps/api/.env` o entorno shell)

Cada ajuste de `app/config.py` se lee de la variable con su nombre en mayúsculas. Plantilla completa en
`apps/api/.env.example`.

| Variable | Default | Uso |
|---|---|---|
| `ENVIRONMENT` | `Development` | `Production` en Cloud Run |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/accounting_dev` | API y Alembic |
| `JWT_SIGNING_KEY` | marcador | Obligatorio cambiarlo fuera de desarrollo (32+ caracteres) |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `Accounting.Api` / `Accounting.Web` | |
| `JWT_ACCESS_TOKEN_MINUTES` / `JWT_REFRESH_TOKEN_DAYS` | `20` / `30` | |
| `STORAGE_PROVIDER` | `Local` | `Local` o `AzureBlob` |
| `STORAGE_LOCAL_ROOT_PATH` | `App_Data/files` | Solo con `Local` |
| `STORAGE_AZURE_BLOB_CONNECTION_STRING` | vacío | Solo con `AzureBlob` |
| `STORAGE_UPLOAD_CONTAINER` / `STORAGE_OUTPUT_CONTAINER` | `uploads` / `outputs` | |
| `CORS_ALLOWED_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | Lista JSON |
| `CORS_ALLOW_VERCEL_SUBDOMAINS` | `true` | Acepta `*.vercel.app` |
| `ENABLE_SWAGGER` | `false` | Swagger UI en `/swagger`; siempre `false` en producción |
| `WORKER_ENABLED` | `true` | Worker en el proceso del API |
| `WORKER_POLL_INTERVAL_SECONDS` / `WORKER_RUN_TIMEOUT_MINUTES` | `3` / `10` | |
| `ANTHROPIC_API_KEY` | vacío | IA de respaldo; vacío = deshabilitada |
| `AI_EXTRACTION_MODEL` | `claude-opus-5-5` | Modelo de la IA de respaldo |
| `AI_EXTRACTION_ENABLED` | `true` | Apaga la IA aunque haya llave |
| `MAX_UPLOAD_BYTES` | `20000000` | |

Si usas PostgreSQL local de Homebrew (sin usuario `postgres`), usa tu usuario del sistema:
```env
DATABASE_URL=postgresql+psycopg://kelvin@localhost:5432/accounting_dev
```

Para Azure Blob:
- `STORAGE_PROVIDER=AzureBlob`
- `STORAGE_AZURE_BLOB_CONNECTION_STRING=<cadena>`

## Levantar proyecto local

1. Levantar Postgres (opcional con Docker):
```bash
docker compose up -d
```

Si la base no existe, créala una vez:
```bash
createdb accounting_dev
```

2. API (requiere [uv](https://docs.astral.sh/uv/); instala Python 3.13 si hace falta):
```bash
cd apps/api
uv sync
cp .env.example .env
# Aplicar migraciones (la API no las aplica al iniciar)
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 5184
```

3. Frontend:
```bash
cd apps/web
cp .env.example .env
pnpm install
pnpm dev
```

4. Abrir:
- Web: http://localhost:3000
- API Swagger: http://localhost:5184/swagger (con `ENABLE_SWAGGER=true`, ya incluido en `.env.example`)

## Tests y lint del API

Los tests usan una base Postgres aparte (se borra su contenido), indicada con `TEST_DATABASE_URL`:

```bash
createdb accounting_test   # o: docker compose exec postgres createdb -U postgres accounting_test
cd apps/api
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/accounting_test
uv run pytest
uv run ruff check .
```

Los PDF reales de clientes van en `apps/api/tests/fixtures/private/` (ignorado por git y por Docker).

## Migraciones (Alembic)

```bash
cd apps/api
uv run alembic revision --autogenerate -m "<descripcion>"
uv run alembic upgrade head
```

Revisar siempre el archivo generado en `alembic/versions/` antes de commitearlo.

## Endpoints principales

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET/POST/PUT/DELETE /api/clients` (incluye `nit`, `nrc` y códigos de Renta por defecto)
- `GET/POST /api/clients/{clientId}/configs`
- `GET/POST /api/clients/{clientId}/periods`
- `GET/POST /api/clients/{clientId}/periods/{periodId}/uploads`
- `DELETE /api/clients/{clientId}/periods/{periodId}/uploads/{uploadId}`
- `POST /api/clients/{clientId}/periods/{periodId}/uploads/{uploadId}/reextract`
- `GET /api/clients/{clientId}/periods/{periodId}/documents`
- `PATCH /api/clients/{clientId}/periods/{periodId}/documents/{documentId}`
- `POST /api/clients/{clientId}/periods/{periodId}/documents/bulk`
- `GET/POST /api/clients/{clientId}/periods/{periodId}/runs`
- `GET /api/catalogs/renta`
- `GET /api/artifacts/{artifactId}/download`
- `GET /api/usage?year=AAAA&month=M` (uso del mes de la cuenta actual, por cliente y total)

Todos los recursos pertenecen a la cuenta del usuario (creada al registrarse). El encabezado opcional
`X-Account-Id` elige otra cuenta de la que el usuario sea miembro (403 si no lo es).

## Extracción de DTE

1. El contador sube los PDF de DTE de un cliente para un período (mes). Cada upload queda pendiente de
   extracción y el worker lo procesa.
2. **Parser MH**: lee por posición las etiquetas de la plantilla del sistema de facturación del MH
   (encabezado `DOCUMENTO TRIBUTARIO ELECTRÓNICO`). Emisor y receptor se separan por columna.
3. **IA de respaldo** (solo con `ANTHROPIC_API_KEY`): se usa cuando la plantilla no se reconoce, el PDF no
   tiene texto (escaneado), faltan campos requeridos o los montos no cuadran. Su resultado pasa por las
   mismas validaciones. Sin llave, esos documentos no se completan automáticamente y requieren
   revisión manual.
4. Validaciones (Error bloquea la generación, Warning no): formato de código de generación, número de
   control y fecha; `no sujetas + exentas + gravadas + IVA = total`; IVA de CCF ≈ 13 %; fecha fuera del
   período; emisor distinto del NIT/NRC del cliente; código de generación repetido en el período; tipos que
   no van a anexos de ventas (Warning, no se exportan).
5. Los documentos aparecen en la tabla de revisión: se pueden editar, excluir y asignar códigos de Renta
   por documento (por defecto, los del cliente). `reextract` vuelve a leer un archivo y reemplaza sus
   documentos.

## Generación de anexos

1. `POST .../runs` crea un generation run. Devuelve 409 si hay extracciones en curso y 400 si no hay
   documentos incluidos o alguno incluido tiene Error.
2. El worker construye los CSV con la especificación F-07 (`app/anexos/specs/*.json`):
   - **Anexo 1** (`anexo1_AAAAMM.csv`): ventas a contribuyentes (tipos 03/05/06), una fila por documento.
   - **Anexo 2** (`anexo2_AAAAMM.csv`): ventas a consumidor final (tipo 01), una fila por fecha y códigos
     de Renta, con el primer y último código de generación del día.
3. Formato: separador `;`, sin encabezado, CRLF, Windows-1252, montos con 2 decimales. Desde 01/2025 los
   códigos de Renta son obligatorios.
4. Cada regeneración crea una versión nueva de los archivos; se descargan con
   `GET /api/artifacts/{artifactId}/download`.

## Despliegue

- Frontend: Vercel (proyecto `apps/web`, build command `pnpm build`).
- API: Google Cloud Run con GitHub Actions (`.github/workflows/deploy-api.yml`).
- DB: Supabase/Neon PostgreSQL (`DATABASE_URL` con el driver `postgresql+psycopg://`).

### Vercel (frontend) para evitar 404

Configura el proyecto en Vercel así:
1. **Root Directory**: `apps/web`
2. **Build Command**: `pnpm build`
3. **Install Command**: `pnpm install`
4. **Output Directory**: vacío (no usar `dist`, TanStack Start + Nitro genera SSR)

Variables de entorno:
1. `VITE_API_URL=<URL pública del API en Cloud Run>`

### CI y releases del API

`ci-api.yml` instala dependencias con `uv sync --locked` (falla si `uv.lock` no está al día), ejecuta
`ruff check`, los tests contra un contenedor de servicio Postgres 16 y los contratos de los workflows
en pushes de ramas y PRs. Un push a `main` **no despliega** el API. El frontend sigue con push-to-deploy
en Vercel. Todos los jobs del API usan `blacksmith-2vcpu-ubuntu-2404`.

#### Configuración inicial (antes del primer tag)

1. Instalar la app de Blacksmith en la organización/repositorio y habilitar el runner.
2. Mantener Artifact Registry y Cloud Run habilitados en GCP. La cuenta de despliegue
   usada por WIF necesita permisos de push/lectura en Artifact Registry, deploy de
   Cloud Run (incluido acceso público) y `iam.serviceAccounts.actAs` sobre la cuenta runtime.
3. Permitir en WIF los refs `refs/tags/api-v*` del repositorio, además de `refs/heads/main`
   para dispatch. Si la condición actual está limitada a `main`, los tags no autenticarán.
   Restringir siempre al repositorio confiable; proteger los tags `api-v*` contra cambios/borrado.
4. Crear los cuatro secretos siguientes en Secret Manager en `GCP_PROJECT_ID`, con una
   versión `latest` habilitada. Otorgar `roles/secretmanager.secretAccessor` a la cuenta
   **runtime** sobre cada secreto. La cuenta **de despliegue** necesita
   `roles/secretmanager.viewer` sobre ellos para validar metadatos; el workflow no lee payloads.

   | Variable en Cloud Run | Nombre del secreto |
   |---|---|
   | `DATABASE_URL` | `api-database-url` |
   | `JWT_SIGNING_KEY` | `api-jwt-signing-key` |
   | `STORAGE_AZURE_BLOB_CONNECTION_STRING` | `api-storage-azure-blob-connection-string` |
   | `ANTHROPIC_API_KEY` | `api-anthropic-api-key` |

   Los cuatro son obligatorios. `DATABASE_URL` usa el formato
   `postgresql+psycopg://usuario:clave@host:5432/base?sslmode=require` (codificar caracteres
   especiales de la clave). Con storage Local, el secreto Azure puede tener un valor de marcador
   (no se consume); AzureBlob es recomendado: el filesystem de Cloud Run es efímero. Sin IA de
   respaldo, poner un marcador en `api-anthropic-api-key` y la variable `API_AI_EXTRACTION_ENABLED=false`.
   `latest` se resuelve al arrancar cada instancia; una rotación aplica también a nuevos arranques
   de revisiones anteriores.
5. Copiar la **misma URL de la misma base** a `API_DATABASE_URL` en GitHub Secrets: solo la usa el
   paso de migración, fuera de Cloud Run. Postgres debe ser alcanzable desde Blacksmith y la
   conexión debe tener permisos DDL y TLS según el proveedor. No imprimir valores ni pasarlos como
   expresiones inline de shell.
6. Migrar desde el API .NET: el secreto GitHub `API_CONNECTION_STRING_POSTGRES` se reemplaza por
   `API_DATABASE_URL` (formato URL, no cadena ADO.NET), y el secreto de Secret Manager
   `api-connection-string-postgres` por `api-database-url`. Los anteriores ya no se usan y pueden
   borrarse después del primer deploy. El nuevo deploy reemplaza el conjunto completo de env vars y
   secretos de la revisión (se quitan las variables `ASPNETCORE_*`, `Jwt__*`, `Storage__*`).

Variables de repositorio (Settings > Secrets and variables > Actions > Variables):
- `GCP_PROJECT_ID`
- `GCP_REGION` (ejemplo: `us-east1`)
- `GAR_REPOSITORY`
- `CLOUD_RUN_SERVICE`
- `CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT` (opcional; default `cloud-run-runtime@PROJECT_ID.iam.gserviceaccount.com`)
- `API_STORAGE_PROVIDER` (opcional, `AzureBlob` recomendado; default `Local`)
- `API_AI_EXTRACTION_ENABLED` (opcional; default `true`)
- `API_AI_EXTRACTION_MODEL` (opcional; default el de `app/config.py`)

Secrets de repositorio:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `API_DATABASE_URL` (solo releases nuevos; no requerido para rollback)

#### Publicar

Primero integrar estos workflows a `main` y completar la configuración externa.
Comprobar que **API CI está verde en el commit exacto** antes de crear el tag; esta
comprobación es procedural, no un gate automático del workflow de deploy.

```bash
git checkout main && git pull --ff-only
git tag api-v1.0.0
git push origin api-v1.0.0
```

Solo se aceptan tags estables `api-vMAJOR.MINOR.PATCH`, sin ceros iniciales, prerelease
ni metadata. Patch para fixes, minor para endpoints nuevos, major para cambios incompatibles.
No mover ni reutilizar tags publicados. Conservar sus imágenes en Artifact Registry.

El workflow valida tag/configuración, construye la imagen Linux amd64 (`apps/api/Dockerfile`) con
cache de Blacksmith, resuelve su digest, aplica migraciones con `alembic upgrade head` **desde esa misma
imagen** (`docker run` en el runner) y despliega por digest. Swagger está deshabilitado en producción.
El servicio se despliega con `--no-cpu-throttling` y `--min-instances=1`: el worker corre dentro del
proceso del API y necesita CPU fuera de las peticiones y al menos una instancia activa (esto tiene costo
fijo). Un fallo de migración impide el nuevo deploy: la revisión anterior continúa sirviendo, aunque
cambios de esquema ya aplicados pueden permanecer. Las migraciones deben ser compatibles con la revisión
viva (estrategia expand/contract). No hay downgrade automático de esquema.

Los releases se serializan con `cancel-in-progress: false` y `queue: max` (hasta 100
pendientes). FIFO corresponde a la llegada a la cola, no garantiza orden de push de tags;
para releases dependientes, esperar la finalización del anterior.

#### Reintentar y rollback

- Si un release falla al migrar o desplegar: corregir la causa y **re-ejecutar el workflow
  original del push** para repetir migraciones pendientes antes de desplegar. No usar
  dispatch para saltarse una migración fallida. No editar/recrear el tag; cambios de código
  requieren un tag nuevo.
- Rollback: Actions > Deploy API > Run workflow, seleccionar **main** como ref del
  workflow e indicar el tag anterior que se desplegó con éxito. Por CLI:

  ```bash
  gh workflow run deploy-api.yml --ref main -f tag=api-v1.0.0
  ```

  Dispatch comprueba que el tag y su imagen existan, y despliega el digest existente:
  **no construye ni ejecuta migraciones**. Una imagen inexistente aborta el workflow.
  Usar únicamente releases que ya migraron con éxito. El rollback de aplicación conserva
  el esquema actual y las referencias `latest` a secretos: verificar compatibilidad.
  Un rollback de esquema requiere una migración nueva y un tag nuevo.

#### Verificación local

```bash
cd apps/api && uv sync --locked && uv run ruff check . && uv run pytest && cd ../..
python3 -m venv /tmp/hacienda-workflow-tests
/tmp/hacienda-workflow-tests/bin/pip install -r .github/tests/requirements.txt
/tmp/hacienda-workflow-tests/bin/python -m unittest discover -s .github/tests -v
actionlint
git diff --check
```

`actionlint` 1.7.12 no reconoce aún `concurrency.queue`: `.github/actionlint.yaml`
ignora únicamente ese diagnóstico en deploy; los tests comprueban su valor `max`.

Referencias: [Blacksmith builder](https://github.com/useblacksmith/setup-docker-builder),
[concurrencia de GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
[uv en Docker](https://docs.astral.sh/uv/guides/integration/docker/),
[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[CPU siempre asignada en Cloud Run](https://cloud.google.com/run/docs/configuring/billing-settings),
[opciones de Cloud Run](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy).

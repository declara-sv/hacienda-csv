# HaciendaCSV Scaffold

Scaffold inicial para app contable (español-first) orientada a contadores de El Salvador.

## Stack
- Frontend: TanStack Start + TanStack Router + TanStack Query + TypeScript.
- Backend: .NET 10 Web API + EF Core + PostgreSQL.
- Auth: email/password + JWT access/refresh (preparado para reemplazo futuro por Azure AD B2C).
- Storage: abstracción `IFileStorage` con implementación `AzureBlobFileStorage` y `LocalFileStorage`.
- Parsing pipeline: placeholder con `ParseJob` + worker en background que genera CSV dummy.

## Estructura

```text
apps/
  web/                  # TanStack Start (UI en español)
  api/
    Accounting.Api/     # .NET 10 API + EF Core + worker + migraciones
docker-compose.yml      # PostgreSQL local opcional
```

## Variables de entorno

### Frontend (`apps/web/.env`)
```env
VITE_API_URL=http://localhost:5184
```

### API (`apps/api/Accounting.Api/.env` o entorno shell)
```env
ASPNETCORE_ENVIRONMENT=Development
ASPNETCORE_URLS=http://localhost:5184
ConnectionStrings__Postgres=Host=localhost;Port=5432;Database=accounting_dev;Username=postgres;Password=postgres
Jwt__Issuer=Accounting.Api
Jwt__Audience=Accounting.Web
Jwt__SigningKey=CAMBIAR_ESTA_LLAVE_EN_PRODUCCION_32+
Jwt__AccessTokenMinutes=20
Jwt__RefreshTokenDays=30
Storage__Provider=Local
Storage__UploadContainer=uploads
Storage__OutputContainer=outputs
Storage__LocalRootPath=App_Data/files
Storage__AzureBlobConnectionString=
```

Si usas PostgreSQL local de Homebrew (sin usuario `postgres`), usa tu usuario del sistema:
```env
ConnectionStrings__Postgres=Host=localhost;Port=5432;Database=accounting_dev;Username=kelvin
```

Para Azure Blob:
- `Storage__Provider=AzureBlob`
- `Storage__AzureBlobConnectionString=<cadena>`

## Levantar proyecto local

1. Levantar Postgres (opcional con Docker):
```bash
docker compose up -d
```

2. API (.NET 10):
```bash
cd apps/api/Accounting.Api
export PATH="/Users/kelvin/.dotnet10:$PATH" # si instalaste dotnet 10 local
# Aplicar migraciones (la API ya no las aplica al iniciar)
dotnet ef database update
dotnet run
```

Si la base no existe, créala una vez:
```bash
createdb accounting_dev
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
- API Swagger: http://localhost:5184/swagger

## Migraciones EF Core

```bash
cd apps/api/Accounting.Api
# dotnet-ef está instalado como herramienta local (apps/api/.config/dotnet-tools.json)
dotnet tool restore
dotnet ef migrations add <NombreMigracion>
dotnet ef database update
```

## Endpoints principales

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET/POST/PUT/DELETE /api/clients`
- `GET/POST /api/clients/{clientId}/configs`
- `GET/POST /api/clients/{clientId}/periods`
- `GET/POST /api/clients/{clientId}/periods/{periodId}/uploads`
- `GET /api/artifacts/{artifactId}/download`

## Placeholder de parsing

Flujo actual:
1. Usuario sube archivo (Excel/PDF).
2. Se crea `Upload` + `ParseJob(Pending)`.
3. Worker `ParsePipelineWorker` toma jobs pendientes.
4. Marca `Running` -> genera CSV dummy -> guarda `OutputArtifact` -> marca `Completed`.

## Despliegue

- Frontend: Vercel (proyecto `apps/web`, build command `pnpm build`).
- API: Google Cloud Run con GitHub Actions (`.github/workflows/deploy-api.yml`).
- DB: Supabase/Neon PostgreSQL (reemplaza `ConnectionStrings__Postgres`).

### Vercel (frontend) para evitar 404

Configura el proyecto en Vercel así:
1. **Root Directory**: `apps/web`
2. **Build Command**: `pnpm build`
3. **Install Command**: `pnpm install`
4. **Output Directory**: vacío (no usar `dist`, TanStack Start + Nitro genera SSR)

Variables de entorno:
1. `VITE_API_URL=<URL pública del API en Cloud Run>`

### CI y releases del API

`ci-api.yml` ejecuta restore, build con `-warnaserror`, los tests de integración
(Testcontainers/Postgres) y los contratos de los workflows en pushes de ramas y PRs.
Un push a `main` **no despliega** el API. El frontend sigue con push-to-deploy en Vercel.
Todos los jobs del API usan `blacksmith-2vcpu-ubuntu-2404`.

#### Configuración inicial (antes del primer tag)

1. Instalar la app de Blacksmith en la organización/repositorio y habilitar el runner.
2. Mantener Artifact Registry y Cloud Run habilitados en GCP. La cuenta de despliegue
   usada por WIF necesita permisos de push/lectura en Artifact Registry, deploy de
   Cloud Run (incluido acceso público) y `iam.serviceAccounts.actAs` sobre la cuenta runtime.
3. Permitir en WIF los refs `refs/tags/api-v*` del repositorio, además de `refs/heads/main`
   para dispatch. Si la condición actual está limitada a `main`, los tags no autenticarán.
   Restringir siempre al repositorio confiable; proteger los tags `api-v*` contra cambios/borrado.
4. Crear los tres secretos siguientes en Secret Manager en `GCP_PROJECT_ID`, con una
   versión `latest` habilitada. Otorgar `roles/secretmanager.secretAccessor` a la cuenta
   **runtime** sobre cada secreto. La cuenta **de despliegue** necesita
   `roles/secretmanager.viewer` sobre ellos para validar metadatos; el workflow no lee payloads.

   | Variable en Cloud Run | Nombre del secreto |
   |---|---|
   | `ConnectionStrings__Postgres` | `api-connection-string-postgres` |
   | `Jwt__SigningKey` | `api-jwt-signing-key` |
   | `Storage__AzureBlobConnectionString` | `api-storage-azure-blob-connection-string` |

   Los tres son obligatorios, incluso con storage Local. Para Local puede usarse un
   valor no vacío de marcador en el secreto Azure (no se consume). AzureBlob es recomendado:
   el filesystem de Cloud Run es efímero. `latest` se resuelve al arrancar cada instancia;
   una rotación aplica también a nuevos arranques de revisiones anteriores.
5. Copiar la **misma conexión a la misma base** a `API_CONNECTION_STRING_POSTGRES` en
   GitHub Secrets: solo la usa el paso de migración, fuera de Cloud Run. Postgres debe
   ser alcanzable desde Blacksmith y la conexión debe tener permisos DDL y TLS según
   el proveedor. No imprimir valores ni pasarlos como expresiones inline de shell.
6. Migrar la configuración anterior: el nuevo deploy reemplaza el conjunto de env vars
   ordinarias y de secretos, quitando los tres valores plaintext de la nueva revisión.
   Las revisiones antiguas conservan su configuración: revisar su retención y rotar
   credenciales según corresponda. Los secretos GitHub `API_JWT_SIGNING_KEY` y
   `API_STORAGE_AZURE_BLOB_CONNECTION_STRING` ya no son usados por este workflow.

Variables de repositorio (Settings > Secrets and variables > Actions > Variables):
- `GCP_PROJECT_ID`
- `GCP_REGION` (ejemplo: `us-east1`)
- `GAR_REPOSITORY`
- `CLOUD_RUN_SERVICE`
- `CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT` (opcional; default `cloud-run-runtime@PROJECT_ID.iam.gserviceaccount.com`)
- `API_STORAGE_PROVIDER` (opcional, `AzureBlob` recomendado; default `Local`)

Secrets de repositorio:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `API_CONNECTION_STRING_POSTGRES` (solo releases nuevos; no requerido para rollback)

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

El workflow valida tag/configuración, construye la imagen Linux amd64 con cache de
Blacksmith, crea un bundle EF autocontenido Linux x64, aplica migraciones y despliega
por digest. Swagger está deshabilitado en producción. Un fallo de migración impide el
nuevo deploy: la revisión anterior continúa sirviendo, aunque cambios de esquema ya
aplicados pueden permanecer. Las migraciones deben ser compatibles con la revisión viva
(estrategia expand/contract). No hay downgrade automático de esquema.

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
dotnet restore apps/api/Accounting.slnx
dotnet build apps/api/Accounting.slnx --no-restore -warnaserror
dotnet test apps/api/Accounting.Api.Tests --no-build
python3 -m venv /tmp/hacienda-workflow-tests
/tmp/hacienda-workflow-tests/bin/pip install -r .github/tests/requirements.txt
/tmp/hacienda-workflow-tests/bin/python -m unittest discover -s .github/tests -v
actionlint
git diff --check
```

`actionlint` 1.7.12 no reconoce aún `concurrency.queue`: `.github/actionlint.yaml`
ignora únicamente ese diagnóstico en deploy; los tests comprueban su valor `max`.
No se suprimen advertencias de .NET ni auditorías NuGet.

Referencias: [Blacksmith builder](https://github.com/useblacksmith/setup-docker-builder),
[concurrencia de GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
[bundles EF](https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/applying#bundles),
[opciones de Cloud Run](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy).

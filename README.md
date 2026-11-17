# AnexosFácil

App contable (español-first) para contadores de El Salvador: lee los PDF de DTE de un cliente y genera
los CSV de los anexos de ventas del F-07 (Anexo 1 y Anexo 2).

## Stack
- Frontend: TanStack Start + TanStack Router + TanStack Query + TypeScript (Node 26 LTS, pnpm 12, Vite 8).
- Backend: Python 3.13 + FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL (psycopg 3), gestionado con `uv`.
- Auth: [Clerk](https://clerk.com) (identidad). Cuentas, membresías y uso viven en la base del API.
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
docker-compose.yml      # PostgreSQL local opcional
```

## Variables de entorno

### Frontend (`apps/web/.env`)
```env
VITE_API_URL=http://localhost:5184
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

`VITE_CLERK_PUBLISHABLE_KEY` la usa el navegador; `CLERK_PUBLISHABLE_KEY` y `CLERK_SECRET_KEY` el
servidor (SSR). Las dos publishable keys tienen el mismo valor. `CLERK_SECRET_KEY` es secreta: no
commitearla ni exponerla con prefijo `VITE_`.

### API (`apps/api/.env` o entorno shell)

Cada ajuste de `app/config.py` se lee de la variable con su nombre en mayúsculas. Plantilla completa en
`apps/api/.env.example`.

| Variable | Default | Uso |
|---|---|---|
| `ENVIRONMENT` | `Development` | `Production` en el VPS |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/accounting_dev` | API y Alembic |
| `CLERK_ISSUER` | `https://exciting-gopher-5507.clerk.accounts.dev` | Instancia de Clerk (Frontend API URL); `iss` esperado |
| `CLERK_JWKS_URL` | `{CLERK_ISSUER}/.well-known/jwks.json` | Solo si difiere del default |
| `CLERK_AUTHORIZED_PARTIES` | `["http://localhost:3000","http://localhost:5173"]` | Lista JSON de orígenes aceptados en `azp` (más `*.vercel.app` si `CORS_ALLOW_VERCEL_SUBDOMAINS=true`) |
| `STORAGE_PROVIDER` | `Local` | `Local`, `AzureBlob` o `S3` (Supabase Storage u otro compatible con S3) |
| `STORAGE_LOCAL_ROOT_PATH` | `App_Data/files` | Solo con `Local` |
| `STORAGE_AZURE_BLOB_CONNECTION_STRING` | vacío | Solo con `AzureBlob` |
| `STORAGE_S3_ENDPOINT_URL` / `STORAGE_S3_REGION` | vacío | Solo con `S3` |
| `STORAGE_S3_ACCESS_KEY_ID` / `STORAGE_S3_SECRET_ACCESS_KEY` | vacío | Solo con `S3` (secretos) |
| `STORAGE_S3_BUCKET` | vacío | Solo con `S3`; un bucket privado. `uploads/` y `outputs/` son prefijos dentro de él |
| `STORAGE_S3_FORCE_PATH_STYLE` | `true` | Supabase requiere path-style |
| `STORAGE_UPLOAD_CONTAINER` / `STORAGE_OUTPUT_CONTAINER` | `uploads` / `outputs` | |
| `CORS_ALLOWED_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | Lista JSON |
| `CORS_ALLOW_VERCEL_SUBDOMAINS` | `true` | Acepta `https://*.vercel.app` (CORS y `azp` de Clerk) |
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

Para Supabase Storage (S3):
1. En Supabase: Storage > crear un bucket **privado** (p. ej. `hacienda-files`).
2. Storage > Settings > S3 Connection: habilitar, copiar el endpoint y la región, y crear un access key.
3. En `apps/api/.env`:
   - `STORAGE_PROVIDER=S3`
   - `STORAGE_S3_ENDPOINT_URL=https://<project-ref>.storage.supabase.co/storage/v1/s3`
   - `STORAGE_S3_REGION=<región del proyecto>`
   - `STORAGE_S3_BUCKET=hacienda-files`
   - `STORAGE_S3_ACCESS_KEY_ID=...` y `STORAGE_S3_SECRET_ACCESS_KEY=...`

Cambiar de proveedor no mueve los archivos ya guardados: cada archivo se lee del proveedor configurado.

## Autenticación (Clerk)

Clerk maneja el inicio de sesión. La web obtiene el session token con `getToken()` y lo envía en cada
llamada como `Authorization: Bearer <token>`; Clerk lo renueva solo, así que el API no tiene endpoints de
login, refresh ni logout. El API verifica el token con el JWKS de `CLERK_ISSUER` (RS256, firma, `exp`/`nbf`
con 30 s de tolerancia, `iss`, `sub` y, si viene, `azp`) y responde 401 si algo falla.

En la primera petición de un usuario de Clerk el API crea su usuario, una cuenta con su nombre y la
membresía `Owner`. `GET /api/me` devuelve `{user: {id, email, fullName}, account: {id, name, role}}`.

### Configurar el dashboard de Clerk

1. **API keys** (Configure > API keys): copiar la publishable key (`pk_test_...`) a
   `VITE_CLERK_PUBLISHABLE_KEY` y `CLERK_PUBLISHABLE_KEY`, y la secret key (`sk_test_...`) a
   `CLERK_SECRET_KEY`. En la misma página está la **Frontend API URL**: es el valor de `CLERK_ISSUER`.
2. **Claims del session token** (Configure > Sessions > Customize session token), pegar:
   ```json
   {
     "email": "{{user.primary_email_address}}",
     "name": "{{user.full_name}}"
   }
   ```
   Son opcionales para el API: sin `name` usa el correo (o `Usuario`) y sin `email` lo deja vacío. Cuando
   cambian, el API actualiza el usuario en la siguiente petición. El nombre de la cuenta se fija al crearla.
3. **Métodos de inicio de sesión** (Configure > User & authentication): habilitar los que se usarán
   (por ejemplo correo con código o contraseña y Google) y deshabilitar el resto.
4. **Orígenes permitidos**: el API acepta en `azp` los orígenes de `CLERK_AUTHORIZED_PARTIES` y, con
   `CORS_ALLOW_VERCEL_SUBDOMAINS=true`, cualquier `https://*.vercel.app`. Agregar el dominio propio de la
   web a `CLERK_AUTHORIZED_PARTIES` (y a `CORS_ALLOWED_ORIGINS`).
5. **Rutas** (Configure > Paths): inicio de sesión `<origen>/login`, registro `<origen>/signup`,
   después de cerrar sesión `/login`. La web ya pasa estas rutas en el código; esto alinea los correos y
   enlaces que envía Clerk.

La instancia actual es de desarrollo (`*.clerk.accounts.dev`). Una instancia de **producción** de Clerk
requiere un dominio propio (registros DNS que Clerk indica); al crearla cambian las llaves (`pk_live_...`,
`sk_live_...`) y `CLERK_ISSUER` (por ejemplo `https://clerk.tu-dominio.com`), y los usuarios de la
instancia de desarrollo no se copian.

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

3. Frontend (Node 26 fijado en `.node-version`/`.nvmrc`; `engines` rechaza otras versiones mayores):
```bash
fnm use            # o nvm use
cd apps/web
cp .env.example .env
pnpm install       # un solo lockfile, en la raíz del repo
pnpm dev
```
Paquetes nuevos con scripts de instalación deben agregarse a `allowBuilds` en `pnpm-workspace.yaml`.

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

- `GET /api/me` (usuario actual y cuenta actual con su rol)
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

Todos los recursos pertenecen a la cuenta del usuario (creada en su primera petición). El encabezado opcional
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

- Frontend: Vercel (proyecto `apps/web`).
- API: VPS (Ubuntu) con systemd + nginx + certbot, desplegado por SSH con los scripts de `deploy/`.
- Base de datos y archivos: Supabase (Postgres por el session pooler y Storage por S3).

### Vercel (frontend)

1. **Root Directory**: `apps/web`
2. **Build Command**: `pnpm build`
3. **Install Command**: `pnpm install`
4. **Output Directory**: vacío (TanStack Start + Nitro genera SSR)

Variables de entorno:
1. `VITE_API_URL=https://<dominio del API>`
2. `VITE_CLERK_PUBLISHABLE_KEY=<publishable key de Clerk>`
3. `CLERK_PUBLISHABLE_KEY=<publishable key de Clerk>`
4. `CLERK_SECRET_KEY=<secret key de Clerk>` (marcarla como sensible)
5. `ENABLE_EXPERIMENTAL_COREPACK=1` (para que Vercel use pnpm 12 de `packageManager`; Node 26 se toma de `engines`)

### API en el VPS

El servidor comparte nginx con otros sitios; el API corre como servicio `hacienda-api` (usuario
`hacienda`) en `127.0.0.1:8010`, con el código en `/opt/hacienda-api/releases/<fecha>-<commit>` y
`/opt/hacienda-api/current` como enlace al release activo. El worker corre dentro del mismo proceso.

Una sola vez:
```bash
ssh hacienda-vps 'bash -s' < deploy/setup-server.sh api.midominio.com   # usuario, uv, systemd, sitio nginx
cp apps/api/.env.example apps/api/.env.production                       # completar valores de producción
deploy/push-env.sh                                                      # copia el archivo a /opt/hacienda-api/shared/.env
ssh hacienda-vps sudo certbot --nginx -d api.midominio.com              # HTTPS (el DNS ya debe apuntar al VPS)
```

`apps/api/.env.production` (ignorado por git) debe tener al menos: `ENVIRONMENT=Production`,
`DATABASE_URL` (session pooler de Supabase, `...pooler.supabase.com:5432/postgres?sslmode=require`),
`STORAGE_PROVIDER=S3` y sus `STORAGE_S3_*`, `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES` y
`CORS_ALLOWED_ORIGINS` con el dominio de la web, y opcionalmente `ANTHROPIC_API_KEY`.

Cada despliegue:
```bash
deploy/deploy-api.sh              # publica el commit actual: copia el código, instala dependencias,
                                  # aplica migraciones, cambia `current`, reinicia y revisa /health
deploy/deploy-api.sh v1.2.0       # publica un tag o commit específico
deploy/deploy-api.sh --rollback   # vuelve al release anterior (no revierte migraciones)
```

Diagnóstico: `ssh hacienda-vps sudo journalctl -u hacienda-api -n 100 -f`.

Las migraciones deben ser compatibles con el release anterior (expand/contract) para que el rollback
funcione. En Supabase, mantener apagado el Data API: el API propio es el único acceso a los datos.

### CI

`ci-api.yml` corre `ruff` y `pytest` (con un Postgres de servicio) en cada push y PR que toque
`apps/api`. No despliega.

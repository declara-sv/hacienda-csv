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
# La migración ya existe; al iniciar, la API aplica migrations automáticamente
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
export PATH="/Users/kelvin/.dotnet10:$PATH:$HOME/.dotnet/tools"
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
- API: Azure Container Apps usando `apps/api/Accounting.Api/Dockerfile`.
- DB dev: Neon PostgreSQL free tier (reemplaza `ConnectionStrings__Postgres`).

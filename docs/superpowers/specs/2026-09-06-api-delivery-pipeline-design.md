# API delivery pipeline: tag releases, migration step, Blacksmith

Date: 2026-09-06
Status: approved design
Scope: `.github/workflows/`, `apps/api/Accounting.Api/Program.cs` (one removal), Cloud Run service configuration. No application logic changes.

## Problem

The API deploys on every push to `main` that touches `apps/api`, tagged by commit SHA. Schema migrations run inside the process at startup, so a deploy and a schema change are the same event and can race across Cloud Run instances. Secrets are injected as plain environment variables, Swagger UI is enabled on the unauthenticated production service, and all jobs run on GitHub-hosted runners.

## Decisions already made

1. Stay on Google Cloud Run and the current external managed Postgres. Hosting is revisited later.
2. Releases are git tags. Pushes to `main` run CI only.
3. The web keeps Vercel push-to-deploy. Tag releases apply to the API only.
4. Runners move to Blacksmith.
5. Startup `db.Database.Migrate()` is removed. Migrations run as an explicit pipeline step.
6. Secrets move to Secret Manager and Swagger is disabled in production. Both were flagged in the 2026-09-06 security review and each is a one-line workflow change.

## Workflows

### `ci-api.yml`

Trigger: `push` and `pull_request` on any branch when paths under `apps/api/**` or the workflow itself change.

Jobs, all on a Blacksmith Ubuntu label:

1. Checkout, setup .NET 10.
2. `dotnet restore`, `dotnet build --no-restore -warnaserror` for `apps/api/Accounting.slnx`.
3. `dotnet test --no-build` for `Accounting.Api.Tests`. Testcontainers needs Docker, which Blacksmith runners provide.

CI must be green before a tag is cut. This is procedural for a solo developer; branch protection is optional.

### `deploy-api.yml`

Trigger: `push` on tags matching `api-v*`, plus `workflow_dispatch` with a required `tag` input for re-deploying an existing tag.

Concurrency group `deploy-api`, no cancel-in-progress, so two tags pushed close together deploy in order.

Jobs, all on a Blacksmith Ubuntu label:

1. **Validate.** Same repo vars and secrets check as today, extended with the Secret Manager secret names.
2. **Build and push image.** Authenticate to GCP with Workload Identity as today. Build with the Blacksmith Docker builder action so layers cache between runs. Image tag is the git tag (for example `api-v1.2.0`), not the SHA. Push to Artifact Registry.
3. **Migrate.** `dotnet ef migrations bundle --self-contained -r linux-x64 -o efbundle` from `apps/api/Accounting.Api`, then run `./efbundle --connection "$CONNECTION_STRING"`. The connection string comes from the GitHub secret for this step only. If the bundle exits non-zero, the job fails and the deploy step does not run. The previous Cloud Run revision keeps serving.
4. **Deploy.** `gcloud run deploy` with the new image. Environment variables that are not secrets stay on `--set-env-vars`. The three secrets move to `--set-secrets`:

   | Env var | Secret Manager name |
   |---|---|
   | `ConnectionStrings__Postgres` | `api-connection-string-postgres` |
   | `Jwt__SigningKey` | `api-jwt-signing-key` |
   | `Storage__AzureBlobConnectionString` | `api-storage-azure-blob-connection-string` |

   `Features__EnableSwagger` is set to `false`. The flag stays in code so it can be turned on for a staging service later.

### Removed

`deploy-api-cloud-run.yml` is deleted once the two new workflows are in place.

## One-time setup outside the repo

- Install the Blacksmith GitHub app on the repository.
- Create the three secrets in Secret Manager and grant the Cloud Run runtime service account `roles/secretmanager.secretAccessor` on each.
- Keep the same values in GitHub secrets for the migrate step, which runs outside Cloud Run. `API_CONNECTION_STRING_POSTGRES` is the only one the pipeline itself needs.

## Application change

Remove the `CreateScope` block that calls `db.Database.Migrate()` from `Program.cs`. Local development applies migrations with:

```
dotnet ef database update --project apps/api/Accounting.Api
```

This removal ships with the generation runs feature, which already adds a migration and edits `Program.cs`. See `2026-09-06-generation-runs-design.md`.

## Release procedure

```
git checkout main && git pull
git tag api-v1.0.0
git push origin api-v1.0.0
```

Tags are semver with the `api-` prefix. Patch for fixes, minor for new endpoints, major for breaking contract changes the web must follow.

## Rollback

Re-run `deploy-api.yml` by dispatch with the previous tag. The image already exists in Artifact Registry so only the deploy step does work. Migrations are forward-only; a rollback that needs a schema revert is a new migration and a new tag.

## Out of scope

- Moving off GCP or changing the Postgres provider.
- Tag releases for the web.
- Rate limiting, CORS tightening, refresh-token reuse detection.
- Staging environment.

## Implementation notes (2026-09-06)

- Generation-runs/startup migration removal arrived on `origin/main` via PR #2 before this work.
- Delivery implementation plan: `docs/plans/2026-09-06-api-delivery-pipeline.md`.
- User approved minimal CI dependency repairs: explicit OpenAPI 2.7.5 (security patch)
  and EF Relational 10.0.3 (runtime dependency must flow beyond private Design assets).
- Release phases are sequential steps in one Blacksmith job. Manual dispatch is
  deploy-only and must target a previously successful release; an existing image
  alone does not prove migrations completed. Rerun the original tag-push run to
  recover failed migrations rather than using dispatch.
- Concurrency includes `queue: max`; `cancel-in-progress: false` alone replaces
  older pending runs. FIFO is queue-arrival order, not guaranteed tag-push order.
- Secret names are fixed as above; validation checks enabled latest-version metadata
  without fetching payloads. Deploy identity needs Secret Manager viewer; runtime
  identity needs secretAccessor. See README for one-time setup and release operations.

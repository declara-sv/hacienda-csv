# API Delivery Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship Blacksmith API CI and tag-based Cloud Run releases with explicit migrations and Secret Manager bindings.

**Architecture:** Keep validation, build, migration and deployment as ordered steps in one serialized release job. Tag pushes build and migrate; manual dispatch validates an existing tag and deploys its existing image without rebuilding or running an older migration bundle. Application migration removal and test infrastructure already arrived via PR #2.

**Tech Stack:** GitHub Actions, Blacksmith Ubuntu 24.04, .NET 10, EF migration bundles, Artifact Registry, Cloud Run, Secret Manager, Python unittest/PyYAML for workflow contract tests, actionlint.

## Task 1: Repair CI baseline and add CI

Files: `apps/api/Accounting.Api/Accounting.Api.csproj`, `.github/workflows/ci-api.yml`, `.github/tests/test_api_workflows.py`, `.github/tests/requirements.txt`, `.github/actionlint.yaml`.

1. Reproduce baseline with `dotnet restore apps/api/Accounting.slnx && dotnet build apps/api/Accounting.slnx --no-restore -warnaserror`. Observed NU1903 and MSB3277.
2. Trace dependencies using `dotnet nuget why`. EF Design's private dependency selects Relational 10.0.3 in API but does not flow to tests, which select 10.0.0 through Npgsql.
3. Add explicit Microsoft.OpenApi 2.7.5 (patched 2.x version per GHSA-v5pm-xwqc-g5wc), then explicit Microsoft.EntityFrameworkCore.Relational 10.0.3 so runtime version flows to tests. Do not suppress warnings or audit.
4. Repeat restore/build and run `dotnet test apps/api/Accounting.Api.Tests --no-build`; require all passing.
5. Write failing workflow contract tests for branch push/PR CI, Blacksmith runner, restore/build/test, read-only permissions and absence of branch-triggered deployment.
6. Add CI with branch-only push and PR path filters for API, global.json and delivery support/workflows. Run Python workflow tests in CI too. Register Blacksmith label for actionlint.

## Task 2: Replace deployment workflow

Files: `.github/workflows/deploy-api.yml`, delete `.github/workflows/deploy-api-cloud-run.yml`, extend `.github/tests/test_api_workflows.py`.

1. Write failing tests for tag-only push, required dispatch tag, serialization, tag validation, missing configuration, migration gating, manual rollback skipping build/migrate and secret mappings.
2. Validate stable tags with `^api-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$` before checkout/auth; reject nonexistent tags using an explicit refs/tags checkout. Never interpolate user input into shell code.
3. Validate required repo vars/WIF secrets; the DB secret is needed only for new releases. Use fixed Secret Manager names from the spec and validate their enabled latest versions without reading payloads.
4. Authenticate using existing WIF; set up gcloud. Use Blacksmith setup-docker-builder@v2 with stable cache-key and build-push-action@v2, linux/amd64 and tag-based Artifact Registry image.
5. For pushes only, restore local EF tool, build self-contained linux-x64 efbundle, execute with GitHub DB secret in step env and a quoted --connection argument. Preserve appsettings.json beside bundle. Fail normally so deploy cannot run on errors.
6. For dispatch, skip all build/migration steps. Resolve existing image digest; fail if absent. Deploy immutable digest, public API, Swagger false and the three --set-secrets bindings; ordinary env values remain --set-env-vars.
7. Concurrency: group deploy-api, cancel-in-progress false, queue max to avoid replacing pending releases. Document that FIFO is queue-arrival order, not guaranteed tag-push order.
8. Run actual validation shell blocks with fake configuration in unittest; use actionlint to check YAML, expressions and shell syntax.

## Task 3: Operations docs and end-to-end local verification

Files: `README.md`, `docs/superpowers/specs/2026-09-06-api-delivery-pipeline-design.md` (clarifying execution notes only).

1. Document Blacksmith installation, WIF tag ref permission, GAR/Cloud Run deploy roles, runtime Secret Manager access, fixed secret names and enabled versions, same DB value in GitHub and Secret Manager, externally reachable Postgres and one-time plaintext-to-secret transition.
2. Document CI-before-tag procedure, stable semver tags, immutability, dispatch from main with previous tag, failed-migration recovery by rerunning original push workflow (not dispatch), forward-only schema and rollback compatibility.
3. Run restore/build/test, workflow contract tests, actionlint and git diff --check.
4. Build linux-x64 self-contained migration bundle outside tracked files; run it in a disposable Linux .NET runtime-deps container against disposable Postgres, then rerun for idempotency. Never use production credentials or deploy during verification.
5. Report verified checks and explicitly distinguish one-time external setup/live deployment not performed. Leave changes for user review; no push or production release.

## Verification record

- [x] Task 1: explicit dependency fixes; strict build has 0 warnings/errors; 24 API tests pass.
- [x] Task 2: new workflows and 9 passing workflow contract/execution tests; independent review found no blocking bugs. Reviewer caveat about dispatching failed releases is documented.
- [x] Task 3: README setup/release/recovery/rollback docs; actionlint and git diff --check pass.
- Linux x64 self-contained bundle built successfully, applied both migrations to disposable Postgres 16, then reported already up to date on rerun; history count 2. Disposable container/network removed. The minimal runtime-deps image emitted a nonfatal missing Kerberos library notice; password authentication and migrations completed successfully. Initial history-table lookup logs an expected error before the table is created.
- actionlint 1.7.12 requires the narrowly scoped unknown `concurrency.queue` diagnostic exception; no .NET warning or vulnerability-audit suppression.
- External Blacksmith/GCP setup and live GitHub Actions/Cloud Run execution were not performed. No commit/push/release issued; changes remain for user review.

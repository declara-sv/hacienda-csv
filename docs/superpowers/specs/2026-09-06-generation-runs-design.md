# Generation Runs: period-level CSV generation

Date: 2026-09-06
Status: approved design, pending implementation plan
Scope: `apps/api/Accounting.Api` only. The web follow-up is described in the last section but is not part of this spec.

## Problem

Today every upload creates one `ParseJob` in the same request (`UploadsController.Upload`), and the background worker turns each job into its own CSV. Output is therefore per file, never per filing period. Accountants need to drop many source documents into a period and get one consolidated CSV for that period, regenerate after adding or removing files, and keep a history of what was generated.

The worker also has correctness problems that the redesign must not carry over: the job claim is not atomic, a crash after marking a job Running leaves it stuck forever, and enum statuses serialize as integers while the web expects strings.

## Decisions already made

1. A run consumes all files in the period. There is no file picker. To exclude a file, delete it and regenerate.
2. Runs are immutable and versioned. History is kept; the web highlights the latest.
3. `ParseJob` is removed. Per-file results live in a run-to-upload join row.
4. API first, with tests. Web changes follow in a separate spec.
5. Startup auto-migrate (`db.Database.Migrate()` in `Program.cs`) is removed. Migrations run as a deploy step, defined in `2026-09-06-api-delivery-pipeline-design.md`.
6. Outputs stay in `OutputArtifact`, re-pointed from the job to the run, so the download endpoint is unchanged and a run can produce several files later (Hacienda annexes).

## Data model

### `generation_runs` (new)

| Column | Type | Notes |
|---|---|---|
| Id | uuid | PK |
| ClientId | uuid | FK clients, cascade |
| FilingPeriodId | uuid | FK filing_periods, cascade |
| RequestedByUserId | uuid | FK users, restrict |
| Version | int | 1-based per period |
| Status | varchar(20) | `Pending`, `Running`, `Completed`, `Failed`, stored as string |
| ErrorMessage | varchar(2000) | null unless Failed |
| CreatedAtUtc | timestamp | |
| StartedAtUtc | timestamp | null until claimed |
| CompletedAtUtc | timestamp | null until terminal |

Indexes and constraints:

- Unique `(FilingPeriodId, Version)`.
- Partial unique index on `(FilingPeriodId)` where `Status IN ('Pending','Running')`. This enforces one active run per period in the database, so concurrent POSTs cannot both succeed.
- Index `(Status, CreatedAtUtc)` for the worker poll.

### `generation_run_files` (new)

| Column | Type | Notes |
|---|---|---|
| GenerationRunId | uuid | FK generation_runs, cascade |
| UploadId | uuid, nullable | FK uploads, set null on delete |
| OriginalFileName | varchar(260) | snapshot at run creation |
| SourceFileKind | varchar(20) | snapshot |
| Status | varchar(20) | `Pending`, `Included`, `Failed` |
| ErrorMessage | varchar(2000) | per-file failure |

PK `(GenerationRunId, UploadId)` is not possible with a nullable column, so the PK is a surrogate `Id uuid` with a unique index on `(GenerationRunId, UploadId)`.

Rows are inserted when the run is created, one per upload in the period at that moment. That snapshot is what "which files did this run include" means. Deleting an upload later nulls `UploadId` and keeps the name, so history survives.

### `output_artifacts` (changed)

`ParseJobId` is replaced by `GenerationRunId` (FK generation_runs, cascade). All other columns unchanged.

### Removed

- `parse_jobs` table, `ParseJob` entity, `ParseJobStatus` enum, `Upload.ParseJobs` navigation.
- All existing `output_artifacts` rows are deleted in the migration. They are placeholder output from the stub pipeline and have no value.

### Migration

One EF migration generated from the model, with an explicit `DELETE FROM output_artifacts` before the FK swap. Startup `Migrate()` is removed from `Program.cs`. Local development applies migrations with `dotnet ef database update`. Production applies them through the pipeline (`2026-09-06-api-delivery-pipeline-design.md`).

## API

All routes sit under `api/clients/{clientId:guid}/periods/{filingPeriodId:guid}`. Every action resolves the period through the existing `FindOwnedFilingPeriodAsync` helper and returns 404 when the caller does not own it. Not-owned is never 403.

### Uploads

| Verb | Route | Response | Notes |
|---|---|---|---|
| GET | `/uploads` | 200 `UploadDto[]` | newest first |
| POST | `/uploads` | 201 `UploadDto` | multipart `file` + `sourceFileKind`, unchanged input |
| DELETE | `/uploads/{uploadId}` | 204 | deletes the row, then the storage object best-effort (a failed blob delete is logged, never surfaced) |

`UploadDto`: `id`, `filingPeriodId`, `originalFileName`, `sourceFileKind`, `contentType`, `sizeBytes`, `createdAtUtc`, `includedInLatestRun` (bool). The bool is true when a `generation_run_files` row links this upload to the period's most recent Completed run. The `jobs` array is gone. `UploadCreatedDto` is gone; POST returns the same `UploadDto`.

Upload validation stays as it is today (non-empty, extension matches kind, 20 MB request limit). Delete of an upload that is referenced by a Pending or Running run returns 409, because the worker may be about to read it.

### Generation runs

| Verb | Route | Response | Notes |
|---|---|---|---|
| POST | `/runs` | 202 `GenerationRunDto` | 400 if period has no uploads, 409 if a run is Pending or Running |
| GET | `/runs` | 200 `GenerationRunDto[]` | newest version first |
| GET | `/runs/{runId}` | 200 `GenerationRunDto` | polling target |

`GenerationRunDto`: `id`, `filingPeriodId`, `version`, `status`, `errorMessage`, `createdAtUtc`, `startedAtUtc`, `completedAtUtc`, `files: GenerationRunFileDto[]`, `artifacts: OutputArtifactDto[]`.

`GenerationRunFileDto`: `uploadId` (nullable), `originalFileName`, `sourceFileKind`, `status`, `errorMessage`.

`OutputArtifactDto` is unchanged.

POST computes `Version = max(existing) + 1` inside the same transaction as the insert. A unique violation on the partial index is caught and mapped to 409, which also covers the race where two POSTs arrive together.

### Artifacts

`GET api/artifacts/{artifactId}/download` is unchanged. Ownership is still checked through the artifact's client.

### Cross-cutting

- `JsonStringEnumConverter` is registered globally. Today statuses serialize as integers while the web types declare string literals, which is a latent bug this fixes.
- A global exception handler returns RFC 7807 `ProblemDetails` for unhandled exceptions, with no exception detail outside Development. Validation errors keep using `ValidationProblemDetails` as they do now.

## Worker

`GenerationWorker` replaces `ParsePipelineWorker`. It is a `BackgroundService` with a poll loop and a fresh DI scope per iteration.

### Claim

A single statement claims a run atomically:

```sql
UPDATE generation_runs
SET "Status" = 'Running', "StartedAtUtc" = now()
WHERE "Id" = (
  SELECT "Id" FROM generation_runs
  WHERE "Status" = 'Pending'
  ORDER BY "CreatedAtUtc"
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING "Id";
```

Two instances cannot claim the same run. When nothing is returned the worker sleeps for the poll interval (default 3 seconds).

### Stuck-run recovery

Before each poll, runs in `Running` whose `StartedAtUtc` is older than `Generation:RunTimeoutMinutes` (default 10) are set to `Failed` with a timeout message. This covers process crash, Cloud Run instance replacement, and shutdown mid-run. No heartbeat column is needed at this scale.

### Processing

1. Load the run with its files, period, and the uploads still present.
2. For each file row: open the upload from storage. On success mark `Included`; on missing upload or storage error mark `Failed` with the message and continue. A run with zero included files fails.
3. Pass the included file streams and period metadata to `ICsvGenerator.GenerateAsync`, which returns a list of `(fileName, contentType, stream)`.
4. Save each result to the outputs container at `{clientId}/{yyyy}/{MM}/run-{version}/{fileName}` and insert an `OutputArtifact` per result.
5. Mark the run `Completed`. Any exception outside per-file handling marks the run `Failed` with the message. Both paths persist in one `SaveChangesAsync`.

### `ICsvGenerator`

```csharp
public interface ICsvGenerator
{
    Task<IReadOnlyList<GeneratedFile>> GenerateAsync(GenerationContext context, CancellationToken ct);
}
```

The only implementation in this spec is `PlaceholderCsvGenerator`, which emits one CSV with one row per included file (client id, year, month, file name, kind, size). It is the seam where the real Hacienda parser will go. Nothing in the worker or the controllers knows about the placeholder.

### Configuration

`GenerationOptions`: `PollIntervalSeconds` (3), `RunTimeoutMinutes` (10). Bound from the `Generation` section and validated on start.

## Code layout

New code lives in feature folders. Existing controllers for auth, clients, client configs, and filing periods are not touched.

```
Features/
  Uploads/
    UploadsController.cs      thin: bind, call service, map status code
    UploadsService.cs         list, create, delete; ownership via OwnershipQueries
    UploadDtos.cs
  Generation/
    GenerationRunsController.cs
    GenerationRunsService.cs  create (snapshot + version), list, get
    GenerationRunDtos.cs
    GenerationWorker.cs
    GenerationOptions.cs
    ICsvGenerator.cs
    PlaceholderCsvGenerator.cs
Domain/Entities/GenerationRun.cs, GenerationRunFile.cs
Domain/Enums/GenerationRunStatus.cs, GenerationRunFileStatus.cs
```

The old `Controllers/UploadsController.cs`, `DTOs/Uploads/`, and `Workers/ParsePipelineWorker.cs` are deleted. `ArtifactsController` stays where it is.

## Testing

New project `apps/api/Accounting.Api.Tests` using xUnit, `WebApplicationFactory<Program>`, and Testcontainers for PostgreSQL. Postgres runs in a container so the partial unique index and `SKIP LOCKED` are tested against the real engine. Storage uses `LocalFileStorage` pointed at a temp directory. Auth uses a helper that registers and logs in a user through the real endpoints.

Required tests:

1. Upload creates an upload and no run. Response has no job fields.
2. Delete upload removes the row and the storage object. Delete while a run is Pending returns 409.
3. Create run with no uploads returns 400.
4. Create run while one is Pending returns 409. Two concurrent creates yield one 202 and one 409.
5. Create run snapshots the current files and assigns version 1, then 2 on the next run.
6. Two concurrent claims return exactly one run id.
7. A run in Running with `StartedAtUtc` older than the timeout is marked Failed by the recovery step.
8. Processing a run with two files produces one artifact whose CSV has two data rows, marks both files Included, and marks the run Completed.
9. A file whose storage object is missing is marked Failed, the run still completes if another file was included, and fails if none were.
10. After a Completed run, a newly uploaded file reports `includedInLatestRun = false` and the earlier ones report true.
11. A second user gets 404 on list uploads, create run, get run, and artifact download for the first user's period.
12. Status fields serialize as strings.

## Out of scope, tracked as follow-ups

- Real Excel and PDF parsing behind `ICsvGenerator`.
- Pagination on list endpoints.
- Rate limiting and CORS tightening (security review, 2026-09-06). Secret Manager and disabling Swagger in production are covered by the delivery spec.
- Deployment pipeline changes: `2026-09-06-api-delivery-pipeline-design.md`.

## Web follow-up (separate spec)

The uploads page splits into Files and Output. Files: multi-file drop zone with a per-file queue and a remove action, plus a "not included yet" marker driven by `includedInLatestRun`. Output: a "Generar CSV del período" button, the latest run with status and downloads, and a list of previous versions. Polling moves from uploads to the active run via `GET /runs/{runId}`. The `file` and `sourceFileKind` form keys are unchanged, which keeps the preserved field list intact.

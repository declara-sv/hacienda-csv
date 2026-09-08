# Period documents and manual CSV generation UI

## Approval and scope

User approved the same-page approach: documents and generation remain on the existing period cargas route. User explicitly requested implementation in the current working directory, not a worktree. Preserve unrelated API launch settings and `.github/hooks/` changes. No backend changes, deployment, or visual redesign.

## Current failure

`normalizeUpload` dereferences the removed `jobs` array. Reproduced using a current-shape UploadDto: `Cannot read properties of undefined (reading 'map')`. The form selects one file, promises automatic processing, and renders artifacts underneath obsolete jobs. Existing 11 frontend tests pass but only exercise the old contract.

## Documents section

Retain existing design tokens and UI primitives. Enable multiple selection and dropping mixed Excel/PDF files. Append selections to a local queue, infer each file's kind with detectSourceFileKind, reject unsupported/empty files locally, and allow queue removal. One multipart request per file; no backend bulk endpoint exists. Upload sequentially to bound concurrency and associate errors reliably. Successful entries leave the queue and refresh persisted documents; failed entries remain with individual retry/removal controls. Do not automatically retry upload POSTs: an ambiguous network failure could have saved a file. Disable queue editing while its upload batch is running. Show uploaded documents independently of generation status, with filename, type, size, date and removal confirmation.

Removal calls the existing DELETE endpoint. Disable deletion of files referenced by known Pending/Running runs and handle 409 conflicts with an explanatory message and refetch. The API remains authoritative for concurrent sessions.

## Generation section

Separate explicit `Generar CSV` action describes that all currently uploaded documents are snapshotted into a new version. No upload callback creates a run. Disable generation until both initial queries succeed, while a run is active, while file mutations are pending, or while any selected/failed local queue entries remain; explain that these entries must be uploaded or removed first. Disable upload/delete initiation while the create-run request is pending to avoid a local snapshot race. Allow additional uploads during an already-created run: they belong to a later generation.

Use a period-scoped runs query. Poll every five seconds while any run is Pending/Running; preserve standard focus refetch and expose a refresh/retry action. Refresh uploads when runs settle so snapshot indicators update. Handle create 400/409 without optimistic success or automatic POST retry, then refetch authoritative state.

Display runs newest version first, distinguish newest run from latest completed output, and keep old downloads accessible even when a newer run fails. Display status, timestamps, run-level error and expandable file results (Pending/Included/Failed). Completed runs can still contain failed files, so expose warnings rather than presenting unconditional success. Deleted source files retain snapshot filenames and can have null uploadId. Artifacts belong to runs; use the existing authenticated artifact download endpoint.

`includedInLatestRun` means membership in the latest completed snapshot, not proof of successful file processing. Label accordingly; do not use it to lock deletion or infer active-run membership. Do not claim output is up to date solely from this flag, since deletion and partial failures make that inference unreliable.

## Contracts and components

Replace ParseJob/UploadCreated with Upload (including includedInLatestRun), GenerationRun, GenerationRunFile, and their distinct status unions. API emits enum names. If numeric normalization is retained, map run 3 to Completed and 4 to Failed (opposite old ParseJob), and file 2 to Included. Explicitly reject unknown statuses rather than silently portraying them as Pending.

Add runsApi.list/create and uploadsApi.remove. Keep single-file uploadsApi.create returning Upload. Split route body into a testable PeriodDocuments component receiving clientId/periodId, with a MultiFileUpload component and GenerationHistory component. Route retains breadcrumbs/client lookup. Local queue and mutation state must reset when route identifiers change (key the period component). TanStack Query owns persisted data; do not mirror query responses into React state.

## Error handling, accessibility and verification

Keep Spanish strings in messages.ts. Use accessible names, native disabled buttons, status/error announcements, keyboard-accessible file selection, confirmation for persisted deletion, and readable mobile layouts. Do not add image generation, new visual dependencies, or unrelated auth/download refactors.

Regression coverage: current UploadDto without jobs; multipart fields; run endpoints; DELETE 204/409; multi-selection and drop; partial upload failure and retry without re-uploading successes; upload never generates; generation guard conditions; explicit create; active-run polling/settlement; latest and historical downloads; per-file failures in completed runs; null uploadId; period switching; query and mutation errors. Run tests, TypeScript, scoped lint, production build, React Doctor and browser checks. Do not describe placeholder backend CSV output as validated Hacienda parsing; PlaceholderCsvGenerator is still registered.

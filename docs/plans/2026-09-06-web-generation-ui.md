# Web Manual Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace obsolete per-upload processing UI with multi-file document management and explicit period-level CSV generation.

**Architecture:** Keep the existing route and visual system. Extract a period-keyed feature component; use separate TanStack Query caches for documents and runs, and a local queue for not-yet-persisted files. Uploads never trigger generation.

**Tech Stack:** React 19, TypeScript, TanStack Router/Query, Vite, Vitest, Testing Library, Spanish i18n.

**Approved design:** `docs/plans/2026-09-06-web-generation-ui-design.md`.

**Workspace:** `/Users/kelvinrojas/Source/hacienda-csv` per explicit user choice. Do not modify or stage `apps/api/Accounting.Api/Properties/launchSettings.json` or `.github/hooks/`. No production writes. Baseline: 11 frontend tests pass.

---

## Task 1: Replace obsolete API contracts (TDD)

**Files**
- Modify `apps/web/src/lib/api-types.ts`
- Modify `apps/web/src/lib/normalize.ts`
- Modify `apps/web/src/lib/normalize.test.ts`
- Modify `apps/web/src/lib/api-client.ts`
- Create `apps/web/src/lib/api-client.test.ts`
- Modify `apps/web/src/components/ui/StatusChip.tsx`

1. Write request-level tests using `vi.stubGlobal('fetch', ...)` and mock auth-storage; return real JSON Responses. A GET uploads fixture must contain `includedInLatestRun: false` and no jobs. Assert it returns unchanged without throwing. Assert POST returns the same Upload shape and multipart contains only the correct file/kind fields. Do not add an obsolete jobs field to make the test pass.
2. Add cases asserting GET/POST `/api/clients/c1/periods/p1/runs`, POST 202 return shape, DELETE `/uploads/u1` 204, and surfaced 400/409 errors. Assert no runs POST occurs on upload. Restore mocks after each test.
3. Run `pnpm --dir apps/web exec vitest run src/lib/api-client.test.ts`; expect failure on current missing-jobs normalization or missing methods.
4. Replace ParseJob types with the following contract (retain existing unrelated types and Artifact):

```ts
export type GenerationRunStatus = 'Pending' | 'Running' | 'Completed' | 'Failed'
export type GenerationRunFileStatus = 'Pending' | 'Included' | 'Failed'
export type GenerationRunFile = {
  uploadId: string | null
  originalFileName: string
  sourceFileKind: 'Excel' | 'PDF'
  status: GenerationRunFileStatus
  errorMessage: string | null
}
export type GenerationRun = {
  id: string
  filingPeriodId: string
  version: number
  status: GenerationRunStatus
  errorMessage: string | null
  createdAtUtc: string
  startedAtUtc: string | null
  completedAtUtc: string | null
  files: GenerationRunFile[]
  artifacts: Artifact[]
}
export type Upload = {
  id: string
  filingPeriodId: string
  originalFileName: string
  sourceFileKind: 'Excel' | 'PDF'
  contentType: string
  sizeBytes: number
  createdAtUtc: string
  includedInLatestRun: boolean
}
```

5. Replace old normalization tests with run/file status fixtures. Test enum names plus numeric compatibility if retained: run Pending=1, Running=2, Completed=3, Failed=4; file Pending=1, Included=2, Failed=3. Reject unknown values with a clear error. Do not silently default an unknown enum to Pending. Normalize both run and nested file statuses at API boundary; remove upload normalization.
6. Add `runsApi.list/create`, `uploadsApi.remove`; preserve shared authenticated request helper and artifact downloader. `create` for runs takes identifiers only and sends POST with no source-file selection body. Update StatusChip type to GenerationRunStatus.
7. Re-run targeted tests. The old route will require replacement in Task 4; do not temporarily reintroduce jobs for type compatibility.
8. Commit only Task 1 files: `git commit -m "fix(web): align client contracts with generation runs"` after staging explicit paths.

## Task 2: Multi-file queue (TDD)

**Files**
- Create `apps/web/src/components/uploads/MultiFileUpload.tsx`
- Create `apps/web/src/components/uploads/MultiFileUpload.test.tsx`
- Modify `apps/web/src/i18n/messages.ts`
- Reuse `apps/web/src/lib/format.ts`, `components/ui/Button.tsx`, `components/ui/Notice.tsx`

1. Use `// @vitest-environment jsdom` and Testing Library with I18nProvider. Test two mixed File objects selected together; test drag/drop; reject unsupported and zero-length entries; ensure selections append rather than overwrite. Cleanup DOM after each case.
2. Test queue deletion, successful batch, and deferred promises proving sequential uploads. Simulate first upload success and second failure; retry only the failed entry. Assert queue remains locked while in flight and reports blocking state to parent while entries remain. Cover period unmount (no cross-period callback corruption).
3. Run `pnpm --dir apps/web exec vitest run src/components/uploads/MultiFileUpload.test.tsx`; expect missing component failure.
4. Implement component props `clientId`, `periodId`, `disabled`, `onUploaded`, and `onQueueStateChange` (pending count and busy). Queue entries use stable unique IDs and hold File, inferred kind, state and error. Invalid files are removable but not uploadable. Duplicate prevention can compare name/size/lastModified within the local queue, not across persisted documents. Do not silently deduplicate unrelated server files.
5. Snapshot eligible entries at submit; loop with await, catch errors individually, remove successes and retain failures. Use an immediate in-flight guard as well as disabled rendering. Invoke onUploaded after successful requests. Set busy false in finally. No automatic retries or byte-progress claims.
6. Preserve existing dropzone styling, add multiple input, queue rows, remove/retry controls and accessible status announcements. Use per-file extension inference; remove old global kind selector. Keep all new strings in messages.ts.
7. Re-run tests and stage explicit files; commit `feat(web): add multi-file upload queue with individual retries`.

## Task 3: Generation history presentation (TDD)

**Files**
- Create `apps/web/src/components/uploads/GenerationHistory.tsx`
- Create `apps/web/src/components/uploads/GenerationHistory.test.tsx`
- Modify `apps/web/src/i18n/messages.ts`

1. Write presentation tests for newest-first version sorting, latest completed highlighting independent of latest failed run, run errors, file failures inside Completed runs, null uploadId, loading/empty/error presentation, and artifact download callbacks for old versions.
2. Run `pnpm --dir apps/web exec vitest run src/components/uploads/GenerationHistory.test.tsx`; expect missing component failure.
3. Implement controlled presentation using GenerationRun[] and download callback/state props. Reuse StatusChip, Button, formatDateTime and existing surface classes. Show file results in native details/summary to keep long runs compact and keyboard accessible. Use stable run IDs; file rows must not key solely on nullable uploadId or potentially duplicate filenames.
4. Display latest completed output without hiding failed newer attempts. A Completed run with Failed files shows a warning. Artifacts are rendered from run.artifacts, never uploads. Historical source filenames remain even if their uploadId is null.
5. Re-run tests, stage explicit files and commit `feat(web): show versioned generation results and downloads`.

## Task 4: Integrate period workflow and concurrency guards (TDD)

**Files**
- Create `apps/web/src/components/uploads/PeriodDocuments.tsx`
- Create `apps/web/src/components/uploads/PeriodDocuments.test.tsx`
- Modify `apps/web/src/routes/clientes.$clientId.periodos.$periodId.cargas.tsx`
- Modify `apps/web/src/i18n/messages.ts`

1. Test feature component with a fresh QueryClient (retry false) and I18nProvider, mocking API methods rather than component internals. Use deferred promises for mutations. Test documents render without jobs; empty/loading/error queries; upload completion invalidates documents but never creates a run.
2. Test explicit generate action, disabled state for empty documents, unresolved/failed queries, nonempty queue (including failed uploads), active runs, and pending file mutations. Assert upload/delete initiation is blocked while run creation is pending. Exercise 400/409 and retry/refetch affordances.
3. Test confirmed delete and cancellation, disabling deletion only for uploads referenced by active runs, DELETE 409 presentation/refetch, and no loss of history after deletion.
4. Test active-run polling and terminal transition refresh of upload snapshot indicators; use fake timers with async act and clear query clients/timers. Include Completed-with-failed-file warning and a previous CSV still downloadable after latest failure. Test period IDs produce separate caches and a remount clears local queue/mutation notices.
5. Run `pnpm --dir apps/web exec vitest run src/components/uploads/PeriodDocuments.test.tsx`; expect missing component failure.
6. Implement these cache keys and active detection:

```ts
const uploadsKey = ['uploads', clientId, periodId]
const runsKey = ['runs', clientId, periodId]
const isActive = (run: GenerationRun) =>
  run.status === 'Pending' || run.status === 'Running'
```

Use list queries with runs polling every 5000 ms while active. After create success seed/invalidate runs immediately so duplicate requests stay disabled while refetching. On conflict refetch runs and uploads. Refresh upload flags when the completed-run identity changes, avoiding render-triggered invalidation loops. Standard focus refetch plus manual refresh handles other sessions.
7. Derive active referenced IDs from active runs' files, ignoring null IDs. Upload indicator text must say membership in latest completed generation; do not confuse it with Included file outcome or active membership. Use explicit deletion confirmation.
8. Compose MultiFileUpload and GenerationHistory. Keep breadcrumb/client lookup in route; replace old hasActiveJobs, UploadForm and upload.jobs rendering. Render `<PeriodDocuments key={`${clientId}:${periodId}`} clientId={clientId} periodId={periodId} />` so navigation resets local state.
9. Update existing copy to plural documents and manual generation; remove promises of automatic processing. Keep existing artifact download implementation; track per-artifact loading and surface errors.
10. Re-run full `pnpm --dir apps/web test` and `pnpm --dir apps/web exec tsc --noEmit`; expect all tests pass and zero TS errors. Stage explicit paths and commit `feat(web): integrate manual period CSV generation workflow`.

## Task 5: Verification and review

**Files:** Only scoped fixes and regression tests discovered by verification; no backend feature work.

1. Use @superpowers:verification-before-completion and @react-doctor. Read skill instructions before running their procedures.
2. Run `pnpm --dir apps/web test`, `pnpm --dir apps/web exec tsc --noEmit`, and `pnpm --dir apps/web exec eslint src/lib/api-types.ts src/lib/api-client.ts src/lib/api-client.test.ts src/lib/normalize.ts src/lib/normalize.test.ts src/components/uploads src/components/ui/StatusChip.tsx src/i18n/messages.ts 'src/routes/clientes.$clientId.periodos.$periodId.cargas.tsx'` (adjust removed files explicitly if needed). Expect all checks pass; do not reformat unrelated files.
3. Run `pnpm --dir apps/web build`. Build does not substitute for typecheck or interaction tests.
4. Run React Doctor per its installed skill and review new findings separately from baseline issues.
5. Use @superpowers:requesting-code-review for scoped review. Confirm one-file API semantics, mutation race guards, settled-run cache refresh, partial failures, and period navigation. Add tests before fixing findings.
6. Browser check at desktop and narrow width with local/test data only: multiple upload selection/drop, individual retry, deletion confirmation, explicit generation, polling, run/file errors, historical downloads, empty/error states, keyboard usability. If local auth/API setup blocks browser verification, state the limitation and rely only on actually executed tests; do not mutate production to validate UI.
7. Inspect `git diff --check`, `git status --short`, and scoped diffs; ensure launchSettings.json and .github/hooks remain unchanged from user's state. Re-run checks after fixes, record outcomes and save session memory.
8. Report exact checks and limitations. No deployment or push without user direction. Note backend CSV generation remains a placeholder, not validated tax conversion. Use @superpowers:finishing-a-development-branch when implementation is actually complete.

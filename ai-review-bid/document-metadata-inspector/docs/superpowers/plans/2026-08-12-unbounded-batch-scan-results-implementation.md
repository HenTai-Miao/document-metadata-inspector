# Unbounded Batch Scan Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop return usable results for arbitrarily large ordinary procurement batches without fixed bidder, document, folder-byte, report-byte, log-byte, or useful-duration cutoffs.

**Architecture:** Python scans documents through a bounded iterator, accumulates only exact-match candidates, and publishes a private per-document result bundle. Electron receives a compact summary and loads deduplicated document details through a trusted ID-based IPC only when a user expands a card. Existing authoritative CLI report contracts and per-document untrusted-input containment remain unchanged.

**Tech Stack:** Python 3.12.13, Pydantic 2, `ThreadPoolExecutor`, Typer, Electron 43, Node.js 24, TypeScript 7, Vitest 4, Ruff, BasedPyright.

## Global Constraints

- Do not impose product constants on bidder count, supported-document count, total selected bytes, result bytes, or total useful batch duration.
- Preserve `InspectionLimits` and all per-document archive, XML, object, memory, parser-output, and parser-timeout protections.
- A document-level failure must produce a terminal failed/partial document and must not erase other document results.
- Default document concurrency remains `min(4, CPU count)` and never creates an unbounded worker set.
- Preserve the public `ScanReport`, `ComparisonReport`, JSON, XLSX, HTML, and existing `compare --json` behavior.
- Never expose absolute paths, raw exceptions, passwords, document content, or credential-like values in renderer errors or progress.
- Use only private regular non-symlink files below the scan-owned temporary directory; renderer inputs are document hashes, never paths.

---

### Task 1: Bounded Incremental Scanner and Comparison Accumulator

**Files:**
- Modify: `src/document_metadata_inspector/scanner.py`
- Modify: `src/document_metadata_inspector/comparison.py`
- Test: `tests/unit/test_scanner.py`
- Test: `tests/unit/test_comparison.py`

**Interfaces:**
- Produces: `Scanner.scan_incrementally(request, on_document, password_provider=None) -> tuple[str, ...]`, where `on_document(document, completed, total)` is invoked serially in deterministic input order.
- Produces: `ComparisonAccumulator(document_groups=())`, `add(document)`, and `matches() -> tuple[TraceMatch, ...]`.
- Preserves: `Scanner.scan()` and `compare_documents()` results byte-for-byte at their model boundary.

- [ ] **Step 1: Write scanner RED tests**

Add tests using controlled blocking parser workers. Assert that `scan_incrementally` invokes the callback for every terminal document, returns expansion warnings, preserves stable order, and never has more than the requested concurrency in flight.

- [ ] **Step 2: Run scanner tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_scanner.py -k 'incremental or concurrency' -vv
```

Expected: failure because `Scanner.scan_incrementally` does not exist.

- [ ] **Step 3: Implement bounded submission**

Add a private iterator that submits at most `min(concurrency, len(paths))` futures. Pop and resolve the oldest future before submitting the next path. Implement `scan_incrementally`; make `scan()` collect it so both paths share extraction behavior.

- [ ] **Step 4: Write comparison accumulator RED tests**

Feed documents one at a time in several orders and assert that `matches()` equals `compare_documents(ComparisonRequest(...)).matches`, including cross-group suppression.

- [ ] **Step 5: Run comparison tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_comparison.py -k accumulator -vv
```

Expected: failure because `ComparisonAccumulator` does not exist.

- [ ] **Step 6: Factor and implement the accumulator**

Move grouping of `_Candidate` values behind `ComparisonAccumulator.add()` and reuse `_match()` and the existing deterministic sorting in `matches()`. Rewrite `compare_documents()` to use the accumulator.

- [ ] **Step 7: Run focused Python tests**

Run:

```bash
uv run pytest tests/unit/test_scanner.py tests/unit/test_comparison.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add src/document_metadata_inspector/scanner.py src/document_metadata_inspector/comparison.py tests/unit/test_scanner.py tests/unit/test_comparison.py
git commit -m "feat: stream bounded document scans"
```

---

### Task 2: Private Desktop Result Bundle and Streaming Manifest

**Files:**
- Create: `src/document_metadata_inspector/desktop_bundle.py`
- Modify: `src/document_metadata_inspector/cli.py`
- Test: `tests/unit/test_desktop_bundle.py`
- Test: `tests/unit/test_cli_workflows.py`

**Interfaces:**
- Produces: hidden CLI command `docmeta desktop-compare --output DIR --max-concurrency N MANIFEST.jsonl`.
- Produces bundle files `summary.json`, `details/<sha256>.json`, and `evidence/<sha256>.json`.
- `summary.json` is published last and contains compact documents, compact matches, batch warnings, and counts.
- `details/<id>.json` contains `{"schema_version":"1.0","document_id":...,"observations":[{"label":...,"value":...}]}` with exact duplicate label/value rows removed.

- [ ] **Step 1: Write desktop bundle RED tests**

Create synthetic `DocumentReport` values containing duplicate observations, parser warnings, embedded warnings, and failed documents. Assert full evidence is present per document, detail rows are deduplicated in stable order, raw observation counts remain exact, summary is written last, and unsafe/null/non-hash IDs fail closed with sanitized errors.

- [ ] **Step 2: Run bundle tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_desktop_bundle.py -vv
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement typed bundle models and writer**

Use focused frozen Pydantic models for the summary/detail transport. Write each file with `write_atomic_output`; use only validated lowercase 64-character SHA-256 IDs as filenames. Store full `DocumentReport` JSON separately from the presentation detail.

- [ ] **Step 4: Write streaming-manifest and CLI RED tests**

Build a version `2.0` JSON-lines manifest with a header followed by more documents than a small monkeypatched legacy threshold. Assert `desktop-compare` consumes it incrementally, rejects malformed lines, duplicates, symlinks, mutation, unsupported suffixes, and overlong individual records, but has no total byte/document cap.

- [ ] **Step 5: Run CLI RED tests**

Run:

```bash
uv run pytest tests/unit/test_cli_workflows.py -k desktop -vv
```

Expected: command/loader missing.

- [ ] **Step 6: Implement the hidden CLI command**

Open and identity-bind the regular manifest once; parse one bounded JSON line at a time; validate the final descriptor identity after EOF. Resolve the runtime once, call `scan_incrementally`, add each document to `ComparisonAccumulator` and the bundle, and emit one sanitized JSON progress line per completed document. Exit `0` when all documents are complete and `3` when at least one terminal document is partial/failed.

- [ ] **Step 7: Run focused Python tests and quality**

Run:

```bash
uv run pytest tests/unit/test_desktop_bundle.py tests/unit/test_cli_workflows.py -q
uv run ruff check src/document_metadata_inspector/desktop_bundle.py src/document_metadata_inspector/cli.py tests/unit/test_desktop_bundle.py tests/unit/test_cli_workflows.py
uv run ruff format --check src/document_metadata_inspector/desktop_bundle.py src/document_metadata_inspector/cli.py tests/unit/test_desktop_bundle.py tests/unit/test_cli_workflows.py
uv run basedpyright src/document_metadata_inspector/desktop_bundle.py src/document_metadata_inspector/cli.py
```

Expected: all exit zero.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/document_metadata_inspector/desktop_bundle.py src/document_metadata_inspector/cli.py tests/unit/test_desktop_bundle.py tests/unit/test_cli_workflows.py
git commit -m "feat: publish compact desktop scan bundles"
```

---

### Task 3: Electron Bundle Lifecycle Without Batch Cutoffs

**Files:**
- Modify: `desktop/src/main/folder-discovery.ts`
- Modify: `desktop/src/main/scan-service.ts`
- Modify: `desktop/src/main/report-adapter.ts`
- Modify: `desktop/src/main/main.ts`
- Modify: `desktop/src/shared/contracts.ts`
- Modify: `desktop/src/preload/preload.ts`
- Test: `desktop/tests/folder-discovery.test.ts`
- Test: `desktop/tests/scan-service.test.ts`
- Test: `desktop/tests/report-adapter.test.ts`
- Test: `desktop/tests/fixtures/fake-docmeta.mjs`

**Interfaces:**
- Produces: `ScanService.documentDetail(documentId: string) -> Promise<DocumentDetail>`.
- Produces: `ScanService.discardResult() -> Promise<void>` and `dispose() -> Promise<void>` for deterministic bundle cleanup.
- Produces trusted IPC `scan:document-detail` and preload `getDocumentDetail(documentId)`.
- Consumes the Task 2 summary/detail schemas and invokes `desktop-compare --max-concurrency 4`.

- [ ] **Step 1: Write folder-discovery RED test**

Mock or synthesize traversal beyond the former 50,000-entry boundary and assert supported files are returned instead of the old safety-limit error; retain symlink and special-file skipping assertions.

- [ ] **Step 2: Write ScanService RED tests for removed cutoffs**

Extend the fake CLI fixture to publish a bundle and configurable large stdout/stderr. Assert a run can outlive the former default wall-clock policy when no explicit test timeout is supplied, cumulative diagnostics above 1 MiB are drained without termination, no report-size check exists, partial exit `3` returns a result, and progress is monotonic.

- [ ] **Step 3: Write lifecycle and trusted-detail RED tests**

Assert only IDs present in the published summary can load details; traversal strings, unknown hashes, symlink detail files, and changed files are rejected. Assert success retains the bundle, a new scan removes the prior bundle, selection replacement calls `discardResult`, and `dispose` removes the final bundle or blocks on cleanup failure.

- [ ] **Step 4: Run desktop RED tests**

Run:

```bash
cd desktop && corepack pnpm test -- folder-discovery.test.ts scan-service.test.ts report-adapter.test.ts
```

Expected: failures for the old constants and missing bundle APIs.

- [ ] **Step 5: Implement incremental manifest writing and process draining**

Write the version `2.0` manifest through a private file handle, one JSON line per selected document. Remove total manifest serialization and byte checks. Make an explicit `maxRunMilliseconds` remain available only to tests/callers; omit the default absolute timer. Drain stderr and parse bounded stdout lines for progress without killing on cumulative byte count.

- [ ] **Step 6: Implement bundle validation and lifecycle**

Validate `summary.json` as a regular non-symlink file, adapt only its compact schema, and bind the returned document-ID set to the retained result directory. Resolve detail paths from that set. Update main-process selection and quit paths to clean retained bundles safely.

- [ ] **Step 7: Run focused desktop gates**

Run:

```bash
cd desktop
corepack pnpm test -- folder-discovery.test.ts scan-service.test.ts report-adapter.test.ts runtime-resolver.test.ts
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm format:check
```

Expected: all exit zero.

- [ ] **Step 8: Commit Task 3**

```bash
git add desktop/src/main desktop/src/shared/contracts.ts desktop/src/preload/preload.ts desktop/tests
git commit -m "feat: load desktop scan bundles on demand"
```

---

### Task 4: Lazy Metadata Detail Rendering

**Files:**
- Modify: `desktop/src/renderer/bridge.ts`
- Modify: `desktop/src/renderer/main.ts`
- Modify: `desktop/src/renderer/render-metadata.ts`
- Modify: `desktop/src/shared/contracts.ts`
- Modify: `desktop/vite.renderer.config.mts`
- Test: `desktop/tests/render-result.test.ts`
- Test: `desktop/tests/state.test.ts`
- Test: `desktop/tests/e2e/renderer_real_data.py`

**Interfaces:**
- Consumes: `DocmetaBridge.getDocumentDetail(documentId)` from Task 3.
- `DocumentSummary` carries counts, parser summaries, key fields, and no full observation array.
- `renderMetadata` loads and renders a `DocumentDetail` only on the first expansion of that document card.

- [ ] **Step 1: Write renderer RED tests**

Assert opening the metadata page creates no observation rows, first expansion makes one detail request and renders returned rows, repeated collapse/expand does not refetch, another document fetches independently, and a detail error appears only on that card without losing the batch result.

- [ ] **Step 2: Run renderer tests and verify RED**

Run:

```bash
cd desktop && corepack pnpm test -- render-result.test.ts state.test.ts
```

Expected: missing bridge/detail behavior.

- [ ] **Step 3: Implement lazy cards and preview detail storage**

Keep a per-card `idle/loading/loaded/failed` state. On expansion call the bridge with the document hash, render only that document's rows, and retain them for later toggles. Update the browser preview bridge to retain preview details by ID without using the removed 128-MiB preview constant.

- [ ] **Step 4: Run renderer and full desktop tests**

Run:

```bash
cd desktop
corepack pnpm test
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm format:check
corepack pnpm build
```

Expected: all exit zero.

- [ ] **Step 5: Commit Task 4**

```bash
git add desktop/src/renderer desktop/src/shared/contracts.ts desktop/vite.renderer.config.mts desktop/tests
git commit -m "feat: lazy-load metadata details"
```

---

### Task 5: Complete Verification and Real-Directory Acceptance

**Files:**
- Modify: `docs/superpowers/specs/2026-08-12-unbounded-batch-scan-results-design.md` only if verified behavior differs from the approved contract
- Create: `.superpowers/sdd/2026-08-12-unbounded-batch-scan-results-implementation/task-report.md` outside Git for evidence

**Interfaces:**
- Verifies the complete Python-to-Electron flow from exact manifest through bundle, summary IPC, detail IPC, cleanup, and child-process convergence.

- [ ] **Step 1: Run complete Python gates**

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
uv run docmeta verify
```

Expected: all commands exit zero; pytest has zero failures.

- [ ] **Step 2: Verify Java worker**

```bash
cd java-worker && ./mvnw --batch-mode --no-transfer-progress verify
```

Expected: Maven BUILD SUCCESS and zero failed tests.

- [ ] **Step 3: Run complete desktop gates**

```bash
cd desktop
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm format:check
corepack pnpm build
```

Expected: all commands exit zero.

- [ ] **Step 4: Run the supplied real directory through the new CLI bundle path**

Use the exact directory:

```text
/Users/zhongerbing/Downloads/[HNZB2026-04-3-412-01]华能蒙东公司2026-2028年热网检修、抢修维护框架服务标段包1
```

Require 12 bidder groups, 25 terminal documents, bundle summary publication, detail retrieval for the largest document, no former size-limit text, and no lingering Java/ExifTool/Python child.

- [ ] **Step 5: Run packaged Windows x64 acceptance**

Build natively on Windows x64, then select the same directory in the installed app. Require a visible result page, successful on-demand metadata detail, bounded worker concurrency, no visible CMD window, and no lingering process after completion/stop. Preserve logs and artifact hashes outside Git.

- [ ] **Step 6: Review the diff and commit verification-aligned updates**

```bash
git diff --check
git status --short
git log --oneline --decorate -8
```

Commit only source, tests, and approved documentation. Do not add reports, user documents, generated bundles, or release artifacts.

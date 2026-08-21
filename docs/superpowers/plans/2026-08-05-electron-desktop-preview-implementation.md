# Electron Desktop Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a real two-page Electron desktop frontend that scans the downloaded eight-document public test folder with the existing offline metadata core.

**Architecture:** A security-isolated Electron main/preload boundary owns folder access and the `docmeta` child process. Pure TypeScript discovery and report-adapter modules produce a compact renderer view model, and a framework-free Vite renderer displays selection, scan progress, bidder cards, and cross-bidder traces.

**Tech Stack:** Electron, Electron Forge, Vite, TypeScript, Vitest, HTML/CSS/SVG, existing `docmeta` frozen executable.

## Global Constraints

- Only modify this `document-metadata-inspector` project.
- Each immediate child directory is one bidder; documents inside the same bidder never conflict with one another.
- Red is reserved for cross-bidder `person_trace` evidence; software/environment traces remain neutral.
- The renderer has no Node.js access; every IPC operation is separately allowlisted through `contextBridge`.
- Never commit the downloaded documents or their generated full JSON report.
- Windows, Linux, and macOS releases bundle their own platform-native `docmeta` runtime and never install dependencies on end-user machines.

---

### Task 1: Desktop contracts, folder discovery, and report adaptation

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/tsconfig.json`
- Create: `desktop/src/shared/contracts.ts`
- Create: `desktop/src/main/folder-discovery.ts`
- Create: `desktop/src/main/report-adapter.ts`
- Test: `desktop/tests/folder-discovery.test.ts`
- Test: `desktop/tests/report-adapter.test.ts`

**Interfaces:**
- Produces: `discoverFolder(rootPath: string): Promise<FolderSelection>`.
- Produces: `adaptComparisonReport(report: ComparisonReportJson, selection: FolderSelection): ScanResult`.
- Produces: serializable `FolderSelection`, `ScanProgress`, `ScanResult`, `TraceSummary`, and `DocumentSummary` types.

- [x] **Step 1: Write the failing folder discovery test**

Create two bidder directories containing `.pdf`, `.docx`, and `.xlsx` names plus one ignored `.txt`. Assert the literal bidder count, supported count, sorted relative paths, and ignored count returned from `discoverFolder`.

- [x] **Step 2: Run the focused test and verify RED**

Run: `pnpm test -- folder-discovery.test.ts`

Expected: FAIL because `discoverFolder` does not exist.

- [x] **Step 3: Implement the minimum bounded directory discovery**

Walk regular files without following symbolic links, accept only the core's declared Office/PDF suffix set, sort deterministically, and assign the first relative path component as `groupId`.

- [x] **Step 4: Write and verify the failing report-adapter test**

Use a hand-authored two-group report containing one `person_trace` and one `software_trace`. Assert that only the person trace has `tone: "danger"`, duplicate display names map by `source_path_sha256`, and totals are literal expected values.

- [x] **Step 5: Implement the report adapter and run Task 1 tests**

Run: `pnpm test -- folder-discovery.test.ts report-adapter.test.ts`

Expected: PASS with no warnings.

### Task 2: Real scan process and safe Electron bridge

**Files:**
- Create: `desktop/src/main/runtime-resolver.ts`
- Create: `desktop/src/main/scan-service.ts`
- Create: `desktop/src/main/main.ts`
- Create: `desktop/src/preload/preload.ts`
- Create: `desktop/src/shared/window.d.ts`
- Test: `desktop/tests/runtime-resolver.test.ts`
- Test: `desktop/tests/scan-service.test.ts`

**Interfaces:**
- Consumes: `discoverFolder` and `adaptComparisonReport` from Task 1.
- Produces: `resolveDocmetaCommand(options): { command: string; argsPrefix: string[] }`.
- Produces: `ScanService.start(selection, onProgress): Promise<ScanResult>` and asynchronous `ScanService.stop()`.
- Produces: `window.docmeta.selectFolder`, argument-free `startScan`, `stopScan`, and `onScanProgress`; selected paths remain owned by the main process.

- [x] **Step 1: Write runtime-resolution tests and verify RED**

Assert literal platform/architecture frozen paths, packaged-resource preference, and development `uv run docmeta` fallback only when no frozen runtime exists.

- [x] **Step 2: Implement deterministic runtime resolution**

Do not search `PATH` for Java or ExifTool. Resolve only packaged resources, this repository's frozen build, or the explicit development fallback.

- [x] **Step 3: Write ScanService lifecycle tests and verify RED**

Use a short real child-process fixture that writes a report file. Assert a second start is rejected, the report is adapted, and `stop()` changes the result to a stopped error without killing unrelated processes.

- [x] **Step 4: Implement ScanService without shell execution**

Pass every CLI argument as a separate `spawn` array element, write the report to a private temporary directory, parse only bounded JSON, and remove temporary output in `finally`.

- [x] **Step 5: Add the allowlisted preload and BrowserWindow**

Enable `contextIsolation`, `sandbox`, and a restrictive CSP; disable `nodeIntegration`, navigation to remote origins, new windows, and arbitrary IPC access.

- [x] **Step 6: Run Task 2 tests**

Run: `pnpm test -- runtime-resolver.test.ts scan-service.test.ts`

Expected: PASS; no child remains after the stop test.

### Task 3: Two-page renderer

**Files:**
- Create: `desktop/index.html`
- Create: `desktop/src/renderer/main.ts`
- Create: `desktop/src/renderer/state.ts`
- Create: `desktop/src/renderer/render-selection.ts`
- Create: `desktop/src/renderer/render-result.ts`
- Create: `desktop/src/renderer/styles.css`
- Test: `desktop/tests/state.test.ts`

**Interfaces:**
- Consumes: the `window.docmeta` bridge and Task 1 contracts.
- Produces: deterministic `AppState` transitions and DOM with stable `data-testid` selectors.

- [x] **Step 1: Write state-transition tests and verify RED**

Assert `ready -> scanning -> result`, `scanning -> stopped -> ready`, and that a stale completed scan cannot replace a newer selection.

- [x] **Step 2: Implement the finite state transitions**

Keep side effects in `main.ts`; reducer functions remain pure and reject stale scan tokens.

- [x] **Step 3: Build the selection and scan page**

Render the real root name, bidder chips, file totals, start/stop controls, an accessible live status, and a reduced-motion-safe scanning beam.

- [x] **Step 4: Build the result page**

Render bidder icon/name headers above file rows, totals from the real report, red SVG identity links only for danger traces, neutral software/environment traces, and the explicit zero-person-trace conclusion.

- [x] **Step 5: Run renderer unit tests and type checking**

Run: `pnpm test -- state.test.ts && pnpm typecheck`

Expected: PASS with no TypeScript errors.

### Task 4: Electron Forge and browser-visible renderer verification

**Files:**
- Create: `desktop/forge.config.ts`
- Create: `desktop/vite.main.config.mts`
- Create: `desktop/vite.preload.config.mts`
- Create: `desktop/vite.renderer.config.mts`
- Create: `desktop/scripts/real-preview.mjs`
- Create: `desktop/tests/e2e/renderer_real_data.py`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: main, preload, and renderer entry points from Tasks 2 and 3.
- Produces: `pnpm start`, `pnpm package`, and `pnpm preview:real` commands.

- [x] **Step 1: Configure native platform makers and Vite entries**

Use Squirrel for Windows, ZIP/DMG for macOS, and DEB/RPM for Linux. Configure `extraResource` only for the platform-native frozen core provided by the build pipeline.

- [x] **Step 2: Install pinned dependencies and lock them**

Run: `pnpm install`

Expected: `pnpm-lock.yaml` is generated and audit output has no unresolved high-severity production issue.

- [x] **Step 3: Build a development-only real preview bridge**

`preview:real` receives the folder and authoritative report through environment variables, adapts them in Node, and serves the same renderer. It does not copy either input into the repository or the production bundle.

- [x] **Step 4: Run the web application test helper help command**

Run the installed web-application test helper with `--help`.

Expected: usage explains server and port arguments.

- [x] **Step 5: Run headless Playwright against the actual downloaded data**

Assert `2` bidder groups, `8` documents, zero red person traces, one neutral `WPS 文字` trace, working start/stop controls, no console errors, and save screenshots outside the repository.

- [x] **Step 6: Package the current macOS Electron app**

Run: `pnpm package`

Expected: Forge creates a launchable `.app` containing the renderer and the platform-native `docmeta` runtime.

### Task 5: Full verification and handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-08-05-electron-desktop-preview-implementation.md` (mark completed checkboxes)

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified Electron preview and one scoped Git commit.

- [x] **Step 1: Run desktop verification**

Run: `pnpm test && pnpm typecheck && pnpm lint && pnpm build && pnpm package`

Expected: every command exits `0`.

- [x] **Step 2: Run the existing Python regression suite**

Run: `uv run pytest`

Expected: all default tests pass and gated real-engine tests remain explicitly skipped unless enabled.

- [x] **Step 3: Run Python static and package gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run basedpyright && uv lock --check && uv build && uv run docmeta verify`

Expected: all commands exit `0`, and `docmeta verify` reports every bundled engine PASS.

- [x] **Step 4: Run one fresh real scan from the Electron service**

Select the external public `4-投标文件` fixture directory, start the scan, and verify the result page shows the literal real-data acceptance values from the design.

- [x] **Step 5: Inspect scope and commit**

Run `git status --short` from the parent Git worktree, stage only this project, and commit with `feat: add Electron metadata review desktop`.

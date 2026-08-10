# Three Interactive UI Mocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three design-spec-compliant, directly openable browser prototypes that each exercise the complete document-metadata review flow and can be compared with identical state and data.

**Architecture:** A static `index.html` loads classic scripts and styles so the prototype works from `file://` without a build or server. A pure model owns demo data, folder summaries, state transitions, and filters; one DOM controller owns side effects; three isolated renderers consume the same state and produce the Guided, Verdict, and Matrix presentations.

**Tech Stack:** HTML5, CSS custom properties and OKLCH/color-mix fallbacks, dependency-free JavaScript, existing Vitest 4.1.10, Python Playwright 1.62.0, Chromium.

## Global Constraints

- Create prototype files only under `desktop/mock/design-spec-variants/` plus narrowly scoped tests under `desktop/tests/`; do not modify `desktop/src/renderer/`, Electron main/preload code, Python extractors, or Java workers.
- Preserve every existing unstaged change; each commit must name only files created by this plan.
- The prototype must open from `file:///.../desktop/mock/design-spec-variants/index.html`; no server, bundler, framework, CDN, external font, external image, or remote request is allowed.
- Keep the three variants on one state model and one synthetic data set: 4 bidders, 16 documents, 148 metadata observations, 2 danger traces, and 3 caution traces.
- Treat person and organization evidence as danger; treat template, timestamp, software, and document-environment evidence as caution or neutral context. Never state that a software/template match proves collusion.
- Use the supplied design-spec tokens exactly: primary `#034ed6`, ink `#141928`, sub `#5d6579`, line `#e8eaf0`, dark panel `#0e1226`, danger `#c93438`, warning `#a85c00`, and success `#15803d`.
- Derive all brand variants from `--primary`; semantic and neutral colors do not change with the theme.
- Keep atmospheric wash within the 560px page header; shallow cards have no shadow; only the dark data panel and allowed floating UI use the specified shadows.
- Copy every used SVG `<symbol>` path exactly from `/Users/zhongerbing/Desktop/设计规范/图标库-icons.html`; do not add emoji, icon fonts, or invented icons.
- Do not read selected document content. Folder selection may use only browser-provided name, relative path, size, and extension, capped at 500 displayed files.
- All interactive targets are at least 28px, all keyboard-focusable elements show the specified 2px focus ring, and motion respects `prefers-reduced-motion: reduce`.
- Verify at 1440×900, 1280×800, and 1024×720. Store screenshots under the system temporary directory, never in the repository.

---

## File Structure

- `desktop/mock/design-spec-variants/index.html`: document shell, registered SVG sprite subset, hidden directory input, app mount, and deterministic script/style loading order.
- `desktop/mock/design-spec-variants/styles.css`: token layers, typography, wash, shell, controls, shared selection/scanning/report/metadata components, accessibility, and responsive rules.
- `desktop/mock/design-spec-variants/guided.css`: A-specific step rail, task cards, and guided metadata layout.
- `desktop/mock/design-spec-variants/verdict.css`: B-specific conclusion band, evidence timeline, and trust panel.
- `desktop/mock/design-spec-variants/matrix.css`: C-specific bidder tree, evidence matrix, sticky axes, and evidence drawer.
- `desktop/mock/design-spec-variants/model.js`: immutable demo data, JSDoc contracts, pure reducer, folder summarization, report filtering, and metadata filtering.
- `desktop/mock/design-spec-variants/render-common.js`: escaped markup helpers and common top bar, version switcher, buttons, badges, theme panel, selection, ready, scanning, stopped, empty-filter, and toast components.
- `desktop/mock/design-spec-variants/render-guided.js`: all A views, including the five-step rail and guided metadata page.
- `desktop/mock/design-spec-variants/render-verdict.js`: all B views, including the verdict-first report and conclusion-linked metadata page.
- `desktop/mock/design-spec-variants/render-matrix.js`: all C views, including folder tree scanning and interactive evidence matrix.
- `desktop/mock/design-spec-variants/app.js`: hash routing, event delegation, directory input, scan timer, local persistence, render scheduling, and test timing hook.
- `desktop/tests/mock-variants-model.test.ts`: Vitest coverage of the pure model and the static file contract.
- `desktop/tests/e2e/design_spec_variants.py`: Playwright flow, console, accessibility-smoke, viewport, theme, state-retention, and screenshot verification.

The scripts use one explicit global namespace because classic scripts are required for reliable `file://` execution:

```javascript
window.DocmetaPrototype = window.DocmetaPrototype ?? {
  model: {},
  common: {},
  renderers: {},
};
```

No other names are added to `window` except the optional test timing value
`window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__`.

---

### Task 1: Pure Prototype Model and Static Contract

**Files:**

- Create: `desktop/mock/design-spec-variants/model.js`
- Create: `desktop/tests/mock-variants-model.test.ts`

**Interfaces:**

- Produces: `DocmetaPrototype.model.createInitialState(hash): PrototypeState`.
- Produces: `DocmetaPrototype.model.reduce(state, action): PrototypeState`.
- Produces: `DocmetaPrototype.model.selectionFromFiles(files): SelectionSummary`.
- Produces: `DocmetaPrototype.model.visibleTraces(state): readonly Trace[]`.
- Produces: `DocmetaPrototype.model.visibleDocuments(state): readonly Document[]`.
- Produces: immutable `DocmetaPrototype.model.demoProject` with literal acceptance totals.

- [ ] **Step 1: Write a VM loader and failing model contract test**

Add this loader and the first assertions to `desktop/tests/mock-variants-model.test.ts`:

```typescript
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";
import { describe, expect, test } from "vitest";

function loadModel() {
  const window: Record<string, unknown> = {};
  const source = readFileSync(
    resolve(import.meta.dirname, "../mock/design-spec-variants/model.js"),
    "utf8",
  );
  vm.runInNewContext(source, { window, structuredClone });
  return (window.DocmetaPrototype as { model: Record<string, any> }).model;
}

describe("design-spec prototype model", () => {
  test("publishes the fixed demonstration totals", () => {
    const model = loadModel();
    expect(model.demoProject.groups).toHaveLength(4);
    expect(model.demoProject.documents).toHaveLength(16);
    expect(model.demoProject.observationCount).toBe(148);
    expect(model.demoProject.traces.filter((trace: any) => trace.tone === "danger")).toHaveLength(2);
    expect(model.demoProject.traces.filter((trace: any) => trace.tone === "caution")).toHaveLength(3);
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run from `desktop/`:

```bash
pnpm test -- mock-variants-model.test.ts
```

Expected: FAIL because `mock/design-spec-variants/model.js` does not exist.

- [ ] **Step 3: Define the immutable model and exact state vocabulary**

Implement `model.js` as an IIFE and define these JSDoc contracts verbatim before the data:

```javascript
/** @typedef {"guided" | "verdict" | "matrix"} Variant */
/** @typedef {"landing" | "empty" | "ready" | "scanning" | "stopped" | "failed" | "report" | "metadata"} View */
/** @typedef {"all" | "danger" | "caution"} ReportFilter */
/**
 * @typedef {object} PrototypeState
 * @property {Variant} variant
 * @property {View} view
 * @property {object | null} selection
 * @property {{stage: string, message: string, percent: number, completedFiles: number}} progress
 * @property {ReportFilter} reportFilter
 * @property {{bidderId: string, query: string, duplicatesOnly: boolean}} metadataFilters
 * @property {string | null} expandedTraceId
 * @property {string | null} selectedEvidenceId
 * @property {string} primary
 * @property {string | null} error
 */
```

Use the literal bidders `华远建设`, `启明工程`, `中筑科技`, and `新科咨询`; four file records per bidder; danger traces for author `王磊` and last modifier `zhangmin`; caution traces for shared template, 87-second creation-time proximity, and matching application/version.

- [ ] **Step 4: Add reducer, folder, and filter tests before their implementations**

Add these tests:

```typescript
test("switching variants preserves the current business view and filters", () => {
  const model = loadModel();
  const report = {
    ...model.createInitialState("#guided"),
    view: "report",
    reportFilter: "danger",
  };
  const next = model.reduce(report, { type: "SET_VARIANT", variant: "matrix" });
  expect(next.variant).toBe("matrix");
  expect(next.view).toBe("report");
  expect(next.reportFilter).toBe("danger");
});

test("folder files are grouped by their first relative directory", () => {
  const model = loadModel();
  const selection = model.selectionFromFiles([
    { name: "技术方案.docx", webkitRelativePath: "演示项目/华远建设/技术方案.docx", size: 1200 },
    { name: "报价.xlsx", webkitRelativePath: "演示项目/启明工程/报价.xlsx", size: 800 },
    { name: "说明.txt", webkitRelativePath: "演示项目/启明工程/说明.txt", size: 20 },
  ]);
  expect(selection.rootName).toBe("演示项目");
  expect(selection.bidderCount).toBe(2);
  expect(selection.fileCount).toBe(2);
  expect(selection.ignoredCount).toBe(1);
});

test("report and metadata filters compose deterministically", () => {
  const model = loadModel();
  const base = { ...model.createInitialState("#verdict"), selection: model.demoProject.selection };
  expect(model.visibleTraces({ ...base, reportFilter: "danger" })).toHaveLength(2);
  expect(model.visibleTraces({ ...base, reportFilter: "caution" })).toHaveLength(3);
  const filtered = model.visibleDocuments({
    ...base,
    metadataFilters: { bidderId: "bidder-a", query: "技术方案", duplicatesOnly: true },
  });
  expect(filtered.every((doc: any) => doc.bidderId === "bidder-a")).toBe(true);
  expect(filtered.every((doc: any) => doc.isDuplicate)).toBe(true);
});
```

- [ ] **Step 5: Implement the minimum pure functions and make the model tests GREEN**

The reducer must return the original state for unknown or invalid transitions, preserve all filters on `SET_VARIANT`, reset progress on `START_SCAN`, move to `stopped` on `STOP_SCAN`, and move to `report` only on `COMPLETE_SCAN`. `selectionFromFiles` must accept the PDF/Word/Excel suffix allowlist case-insensitively, ignore content, and truncate the displayed file list after 500 entries.

Run:

```bash
pnpm test -- mock-variants-model.test.ts
```

Expected: PASS with all model tests. A selection containing no supported documents returns `fileCount: 0`; the app keeps the `empty` view and sets the exact error text `未发现支持的 PDF、Word 或 Excel 文档`. A selection with files only at the chosen root returns a non-empty `boundaryWarning` instead of inventing bidder groups.

- [ ] **Step 6: Commit Task 1 only**

```bash
git add desktop/mock/design-spec-variants/model.js desktop/tests/mock-variants-model.test.ts
git commit -m "test: define interactive mock state model"
```

---

### Task 2: Design-System Shell, Launcher, Selection, and Ready States

**Files:**

- Create: `desktop/mock/design-spec-variants/index.html`
- Create: `desktop/mock/design-spec-variants/styles.css`
- Create: `desktop/mock/design-spec-variants/guided.css`
- Create: `desktop/mock/design-spec-variants/verdict.css`
- Create: `desktop/mock/design-spec-variants/matrix.css`
- Create: `desktop/mock/design-spec-variants/render-common.js`
- Create: `desktop/mock/design-spec-variants/render-guided.js`
- Create: `desktop/mock/design-spec-variants/render-verdict.js`
- Create: `desktop/mock/design-spec-variants/render-matrix.js`
- Create: `desktop/mock/design-spec-variants/app.js`
- Modify: `desktop/tests/mock-variants-model.test.ts`
- Create: `desktop/tests/e2e/design_spec_variants.py`

**Interfaces:**

- Consumes: Task 1 `model` namespace.
- Produces: `DocmetaPrototype.common.escapeHtml(value): string`.
- Produces: shared render helpers and `DocmetaPrototype.app.render()`.
- Produces: stable selectors `variant-card`, `load-demo`, `choose-folder`, `selection-page`, `selected-folder`, `bidder-count`, and `file-count`.

- [ ] **Step 1: Add a failing static-file contract test**

Append to the Vitest file:

```typescript
test("static entry loads only local classic assets", () => {
  const html = readFileSync(
    resolve(import.meta.dirname, "../mock/design-spec-variants/index.html"),
    "utf8",
  );
  expect(html).toContain('data-testid="app-root"');
  expect(html).toContain('type="file"');
  expect(html).not.toMatch(/https?:\/\//u);
  expect(html).not.toContain('type="module"');
  expect(html).not.toMatch(/[😀-🙏]/u);
  for (const asset of [
    "styles.css",
    "guided.css",
    "verdict.css",
    "matrix.css",
    "model.js",
    "render-common.js",
    "render-guided.js",
    "render-verdict.js",
    "render-matrix.js",
    "app.js",
  ]) {
    expect(html).toContain(asset);
  }
});
```

- [ ] **Step 2: Run the test and verify RED**

```bash
pnpm test -- mock-variants-model.test.ts
```

Expected: FAIL because `index.html` does not exist.

- [ ] **Step 3: Build the static shell and registered sprite**

Create `index.html` with this exact asset order:

```html
<link rel="stylesheet" href="styles.css">
<link rel="stylesheet" href="guided.css">
<link rel="stylesheet" href="verdict.css">
<link rel="stylesheet" href="matrix.css">
<!-- registered SVG symbols copied here -->
<input id="folder-input" type="file" webkitdirectory multiple hidden>
<div id="app" data-testid="app-root"></div>
<div id="toast-root" aria-live="polite"></div>
<script src="model.js"></script>
<script src="render-common.js"></script>
<script src="render-guided.js"></script>
<script src="render-verdict.js"></script>
<script src="render-matrix.js"></script>
<script src="app.js"></script>
```

Copy the exact registered symbols for `i-logo`, `i-file`, `i-shield`, `i-check`, `i-x`, `i-play`, `i-alert`, `i-clock`, `i-users`, `i-search`, `i-filter`, `i-eye`, `i-chev-r`, `i-chev-l`, `i-chev-d`, `i-node`, and `i-more` from the supplied icon registry.

- [ ] **Step 4: Implement the shared token and component layer**

In `styles.css`, define the three-layer primary token system before component CSS:

```css
:root {
  --primary: #034ed6;
  --primary-hover: #0342b8;
  --primary-weak: #eaf1fe;
  --primary-weak-2: #f4f8ff;
  --primary-line-hover: #bcd0f5;
  --primary-dk: #4d8bff;
  --primary-dk-text: #cfe0ff;
  --ink: #141928;
  --sub: #5d6579;
  --faint: #6b7489;
  --line: #e8eaf0;
  --line-soft: #f0f2f7;
  --dark: #0e1226;
  --dark-2: #131834;
  --danger: #c93438;
  --warning: #a85c00;
  --success: #15803d;
}
@supports (color: color-mix(in srgb, red 50%, blue)) {
  :root {
    --primary-hover: color-mix(in oklab, var(--primary), black 14%);
    --primary-weak: color-mix(in srgb, var(--primary) 9%, white);
    --primary-weak-2: color-mix(in srgb, var(--primary) 4.5%, white);
    --primary-line-hover: color-mix(in srgb, var(--primary) 27%, white);
    --primary-dk: color-mix(in oklab, var(--primary) 64%, white);
    --primary-dk-text: color-mix(in srgb, var(--primary) 22%, white);
  }
}
:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
```

Add the exact spacing, radius, shadow, type-size, motion, wash, button, chip, topbar, version switch, landing card, directory summary, dark panel, and responsive tokens from the design specification.

- [ ] **Step 5: Write the first failing Playwright journey**

Create `desktop/tests/e2e/design_spec_variants.py` with a direct file URL and these assertions:

```python
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Error, Page, sync_playwright

INDEX = Path(__file__).parents[2] / "mock" / "design-spec-variants" / "index.html"


def test_launcher_and_ready(page: Page) -> None:
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    assert page.get_by_test_id("variant-card").count() == 3
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    page.get_by_test_id("load-demo").click()
    page.get_by_test_id("selected-folder").wait_for()
    assert page.get_by_test_id("bidder-count").inner_text() == "4"
    assert page.get_by_test_id("file-count").inner_text() == "16"
```

The `main()` function must launch headless Chromium at 1440×900, collect console and page errors, call `test_launcher_and_ready`, assert both error lists are empty, and close the browser in `finally`.

- [ ] **Step 6: Implement launcher, empty, and ready rendering**

`render-common.js` must HTML-escape all folder-derived values and produce buttons through semantic `data-action` attributes. `app.js` must use one click/change event-delegation boundary, convert the folder input through `selectionFromFiles`, and render the active variant from the hash.

Create functional baseline renderers so every referenced local asset exists in this task. Each renderer wraps the common setup state in a variant-specific root; later tasks replace only that variant's report and metadata branches:

```javascript
window.DocmetaPrototype.renderers.guided = (state) =>
  `<div class="variant-shell guided-shell" data-variant="guided">${window.DocmetaPrototype.common.renderSetupState(state, "guided")}</div>`;
window.DocmetaPrototype.renderers.verdict = (state) =>
  `<div class="variant-shell verdict-shell" data-variant="verdict">${window.DocmetaPrototype.common.renderSetupState(state, "verdict")}</div>`;
window.DocmetaPrototype.renderers.matrix = (state) =>
  `<div class="variant-shell matrix-shell" data-variant="matrix">${window.DocmetaPrototype.common.renderSetupState(state, "matrix")}</div>`;
```

The three variant stylesheets must already set their real content widths and setup-state spatial signatures: A reserves the narrow step-rail column, B centers a report-width task statement, and C reserves the bidder-tree column. They must not be empty scaffolds.

Run:

```bash
pnpm test -- mock-variants-model.test.ts
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

Expected: both commands PASS; the page reports 3 variants, 4 bidders, 16 files, and no browser errors.

- [ ] **Step 7: Commit Task 2 only**

```bash
git add desktop/mock/design-spec-variants desktop/tests/mock-variants-model.test.ts desktop/tests/e2e/design_spec_variants.py
git commit -m "feat: add interactive mock launcher and selection flow"
```

---

### Task 3: Deterministic Scan, Stop, Retry, and Completion

**Files:**

- Modify: `desktop/mock/design-spec-variants/model.js`
- Modify: `desktop/mock/design-spec-variants/render-common.js`
- Modify: `desktop/mock/design-spec-variants/app.js`
- Modify: `desktop/mock/design-spec-variants/styles.css`
- Modify: `desktop/tests/mock-variants-model.test.ts`
- Modify: `desktop/tests/e2e/design_spec_variants.py`

**Interfaces:**

- Consumes: ready state from Task 2.
- Produces: semantic actions `START_SCAN`, `SCAN_PROGRESS`, `STOP_SCAN`, `FAIL_SCAN`, `RETRY_SCAN`, and `COMPLETE_SCAN`.
- Produces: selectors `start-scan`, `stop-scan`, `scan-progress`, `scan-stage`, `scan-completed-files`, `scan-summary`, `simulate-scan-failure`, `retry-scan`, and `report-page`.
- Produces: optional numeric test hook `window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__`.

- [ ] **Step 1: Add failing reducer transition tests**

```typescript
test("scan stop and completion are distinct terminal transitions", () => {
  const model = loadModel();
  const ready = {
    ...model.createInitialState("#guided"),
    view: "ready",
    selection: model.demoProject.selection,
  };
  const scanning = model.reduce(ready, { type: "START_SCAN" });
  expect(scanning.view).toBe("scanning");
  const stopped = model.reduce(scanning, { type: "STOP_SCAN" });
  expect(stopped.view).toBe("stopped");
  expect(stopped.progress.percent).toBeLessThan(100);
  const failed = model.reduce(scanning, { type: "FAIL_SCAN", error: "演示解析器未响应" });
  expect(failed.view).toBe("failed");
  expect(failed.error).toBe("演示解析器未响应");
  const restarted = model.reduce(stopped, { type: "START_SCAN" });
  const complete = model.reduce(restarted, { type: "COMPLETE_SCAN" });
  expect(complete.view).toBe("report");
  expect(complete.progress.percent).toBe(100);
  expect(complete.progress.completedFiles).toBe(16);
});
```

- [ ] **Step 2: Add a failing Playwright stop/restart journey**

Before navigation, install the fast timing hook:

```python
page.add_init_script("window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__ = 12")
page.get_by_test_id("start-scan").click()
page.get_by_test_id("stop-scan").wait_for()
page.get_by_test_id("stop-scan").click()
page.get_by_text("核验已停止，未生成报告", exact=True).wait_for()
page.get_by_test_id("start-scan").click()
page.get_by_test_id("report-page").wait_for(timeout=5_000)
assert page.get_by_test_id("scan-summary").get_attribute("data-complete") == "16"
```

- [ ] **Step 3: Implement the five-stage scan schedule**

Use these literal thresholds so the UI is deterministic:

```javascript
const SCAN_STAGES = Object.freeze([
  { percent: 8, completedFiles: 0, stage: "清单校验", message: "正在校验 16 份文档" },
  { percent: 24, completedFiles: 3, stage: "容器识别", message: "识别 PDF、OLE 与 OPC 容器" },
  { percent: 58, completedFiles: 9, stage: "多引擎解析", message: "原生解析、Apache 与 ExifTool 交叉取证" },
  { percent: 84, completedFiles: 14, stage: "证据比较", message: "比较跨投标人身份与环境痕迹" },
  { percent: 100, completedFiles: 16, stage: "生成报告", message: "核验完成，正在呈现报告" },
]);
```

`app.js` owns exactly one interval. Starting, stopping, resetting, switching away from scanning, or unloading the page must clear it. A stale timer callback must not move a newer scan.

Put “演示失败状态” inside the secondary demo-scenario menu, never beside the primary scan button. It dispatches `FAIL_SCAN` with `演示解析器未响应`; the failed view states that this is a prototype simulation, offers `retry-scan`, and never shows partial risk conclusions.

- [ ] **Step 4: Implement accessible shared scan UI and reduced motion**

Render a native `<progress max="100">`, visible stage/message, completed-file count, percentage, estimated remaining time, and stop button. Give the status container `aria-live="polite"`. Under reduced motion, hide the scanning beam and retain numeric progress.

- [ ] **Step 5: Run model and browser verification**

```bash
pnpm test -- mock-variants-model.test.ts
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

Expected: stop leaves no report, restart reaches a 16/16 report, and no console/page error is recorded.

- [ ] **Step 6: Commit Task 3 only**

```bash
git add desktop/mock/design-spec-variants/model.js desktop/mock/design-spec-variants/render-common.js desktop/mock/design-spec-variants/app.js desktop/mock/design-spec-variants/styles.css desktop/tests/mock-variants-model.test.ts desktop/tests/e2e/design_spec_variants.py
git commit -m "feat: add controllable prototype scan lifecycle"
```

---

### Task 4: A — Guided Review Workbench

**Files:**

- Modify: `desktop/mock/design-spec-variants/render-guided.js`
- Modify: `desktop/mock/design-spec-variants/guided.css`
- Modify: `desktop/tests/e2e/design_spec_variants.py`

**Interfaces:**

- Consumes: `PrototypeState`, model selectors, and common components.
- Produces: `DocmetaPrototype.renderers.guided(state): string`.
- Produces: selectors `guided-shell`, `workflow-step`, `guided-task-card`, `report-filter-all`, `report-filter-danger`, `report-filter-caution`, `trace-count`, `trace-row`, `trace-toggle`, `show-metadata`, and `metadata-page`.

- [ ] **Step 1: Add a failing guided report journey**

```python
def test_guided_report(page: Page) -> None:
    open_completed_variant(page, "guided")
    shell = page.get_by_test_id("guided-shell")
    assert shell.get_by_test_id("workflow-step").count() == 5
    assert shell.locator('[data-step="report"][aria-current="step"]').count() == 1
    assert shell.get_by_test_id("guided-task-card").count() == 4
    assert shell.get_by_test_id("trace-row").count() == 5
    shell.get_by_test_id("report-filter-danger").click()
    assert shell.get_by_test_id("trace-row").count() == 2
    shell.get_by_test_id("trace-toggle").first.click()
    shell.get_by_text("原始值", exact=True).wait_for()
```

`open_completed_variant` must enter the named variant, load demo data, use the fast scan hook, and wait for `report-page`.

- [ ] **Step 2: Run Playwright and verify RED**

```bash
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

Expected: FAIL because the guided renderer and stylesheet do not exist.

- [ ] **Step 3: Implement all guided views**

The guided renderer must show five truthful steps:

```javascript
const GUIDED_STEPS = Object.freeze([
  ["select", "选择目录"],
  ["identify", "文件识别"],
  ["scan", "离线扫描"],
  ["report", "核验报告"],
  ["metadata", "元数据明细"],
]);
```

Map `landing/empty` to `select`, `ready` to `identify`, `scanning/stopped/failed` to `scan`, `report` to `report`, and `metadata` to `metadata`. The report contains one dark completion panel and exactly four hairline task cards: high risk, review-needed, coverage, and next action.

- [ ] **Step 4: Implement guided report filtering and evidence disclosure**

Use `visibleTraces(state)` for all counts and rows. Each disclosure button has `aria-expanded`; evidence content includes field label, raw value, normalized value, involved bidders, involved relative filenames, and parser list. Only values/labels carry danger or warning colors.

- [ ] **Step 5: Implement guided metadata browsing**

The metadata view retains the step rail with step 05 active. Render bidder filter chips, text search, duplicates-only toggle, and document cards. Clicking a trace’s “定位元数据” action opens the metadata view with its bidder/query filters prefilled.

- [ ] **Step 6: Verify and commit A**

```bash
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
git add desktop/mock/design-spec-variants/render-guided.js desktop/mock/design-spec-variants/guided.css desktop/tests/e2e/design_spec_variants.py
git commit -m "feat: add guided review workbench mock"
```

Expected: the guided journey passes with five steps, four task cards, 5/2 trace filtering, disclosure, and metadata navigation.

---

### Task 5: B — Conclusion-First Review Report

**Files:**

- Modify: `desktop/mock/design-spec-variants/render-verdict.js`
- Modify: `desktop/mock/design-spec-variants/verdict.css`
- Modify: `desktop/tests/e2e/design_spec_variants.py`

**Interfaces:**

- Consumes: the same state/model/common interfaces as A.
- Produces: `DocmetaPrototype.renderers.verdict(state): string`.
- Produces: selectors `verdict-shell`, `verdict-title`, `trust-panel`, `evidence-timeline`, `trace-count`, `trace-row`, and `show-metadata`.

- [ ] **Step 1: Add the failing verdict journey**

```python
def test_verdict_report(page: Page) -> None:
    open_completed_variant(page, "verdict")
    shell = page.get_by_test_id("verdict-shell")
    assert shell.get_by_test_id("verdict-title").inner_text() == "本次核验发现 2 处高风险身份痕迹"
    assert "3 / 3" in shell.get_by_test_id("trust-panel").inner_text()
    assert shell.get_by_test_id("trace-row").count() == 5
    shell.get_by_test_id("report-filter-caution").click()
    assert shell.get_by_test_id("trace-row").count() == 3
    shell.get_by_test_id("trace-toggle").first.click()
    shell.get_by_test_id("show-metadata").first.click()
    page.get_by_test_id("metadata-page").wait_for()
    assert page.get_by_test_id("metadata-search").input_value() != ""
```

- [ ] **Step 2: Run Playwright and verify RED**

```bash
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

Expected: FAIL because `render-verdict.js` and `verdict.css` do not exist.

- [ ] **Step 3: Implement the conclusion-first hierarchy**

The report hero must contain the literal sentence from the test, project/date summary, a restrained danger rule, and four compact counts. The dark panel must answer evidence trust rather than repeat counts:

```text
3 / 3 解析器完成
16 / 16 文档可追溯
148 条归一化元数据
离线处理 · 未上传文件
```

Render danger evidence before caution evidence in one chronological evidence timeline. Use the common filter and disclosure contracts so count behavior matches A exactly.

- [ ] **Step 4: Implement conclusion-linked metadata**

“查看原始证据” dispatches `SHOW_METADATA_FOR_TRACE` with the trace ID. The metadata view opens with the query equal to the trace value, duplicates-only enabled, and the associated document card expanded. Returning to report restores the prior filter and expanded trace.

- [ ] **Step 5: Add the single orchestrated entry motion**

On the first transition into a completed B report, reveal the verdict, timeline, and trust panel in reading order using opacity/translate only. Add this exact reduced-motion override:

```css
@media (prefers-reduced-motion: reduce) {
  .verdict-enter,
  .verdict-enter > * {
    animation: none !important;
    transform: none !important;
    opacity: 1 !important;
  }
}
```

- [ ] **Step 6: Verify and commit B**

```bash
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
git add desktop/mock/design-spec-variants/render-verdict.js desktop/mock/design-spec-variants/verdict.css desktop/tests/e2e/design_spec_variants.py
git commit -m "feat: add conclusion-first report mock"
```

Expected: B shows the exact verdict, 3/3 trust evidence, 5/3 trace filtering, and a prefiltered metadata drill-down.

---

### Task 6: C — Evidence Matrix Console

**Files:**

- Modify: `desktop/mock/design-spec-variants/render-matrix.js`
- Modify: `desktop/mock/design-spec-variants/matrix.css`
- Modify: `desktop/tests/e2e/design_spec_variants.py`

**Interfaces:**

- Consumes: the same state/model/common interfaces as A and B.
- Produces: `DocmetaPrototype.renderers.matrix(state): string`.
- Produces: selectors `matrix-shell`, `bidder-tree`, `bidder-node`, `evidence-matrix`, `matrix-cell`, `evidence-drawer`, `trace-count`, and `matrix-field-row`.

- [ ] **Step 1: Add the failing matrix journey**

```python
def test_matrix_report(page: Page) -> None:
    open_completed_variant(page, "matrix")
    shell = page.get_by_test_id("matrix-shell")
    assert shell.get_by_test_id("bidder-tree").get_by_test_id("bidder-node").count() == 4
    matrix = shell.get_by_test_id("evidence-matrix")
    assert matrix.get_by_test_id("matrix-field-row").count() >= 8
    assert matrix.locator('[data-tone="danger"]').count() >= 4
    matrix.locator('[data-evidence-id="trace-author-wanglei"]').first.click()
    drawer = shell.get_by_test_id("evidence-drawer")
    drawer.wait_for()
    assert "王磊" in drawer.inner_text()
    assert "原始解析证据" in drawer.inner_text()
```

- [ ] **Step 2: Run Playwright and verify RED**

```bash
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

Expected: FAIL because the matrix renderer and stylesheet do not exist.

- [ ] **Step 3: Implement the bidder tree and scan queue continuity**

Selection, ready, and scanning states keep the same left tree footprint. During scanning, file nodes move through `等待`, `解析中`, and `完成` using text plus registered icons. Do not show invented per-file metadata before completion.

- [ ] **Step 4: Implement the semantic matrix**

Use a real table with a sticky first column and sticky bidder headers. Show 8–12 explanatory fields only: author, last modifier, organization, template, created time, modified time, application/version, page/word count, and parser coverage. Every colored cell must include `data-tone`, an accessible tone label, and a stable `data-evidence-id` where applicable.

Danger cells use `--danger-weak` plus a danger text/rule; caution cells use `--warning-weak`; neutral repeated software context uses a neutral blue-gray treatment and never a danger label.

- [ ] **Step 5: Implement matrix focus and evidence drawer**

Clicking a cell dispatches `SELECT_EVIDENCE`. Apply `.is-focused` to its row, bidder column, and all cells sharing the evidence ID. The drawer shows field, tone, normalized value, involved bidders, files, and three parser observations. The close action restores the matrix without changing report filters.

- [ ] **Step 6: Verify and commit C**

```bash
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
git add desktop/mock/design-spec-variants/render-matrix.js desktop/mock/design-spec-variants/matrix.css desktop/tests/e2e/design_spec_variants.py
git commit -m "feat: add evidence matrix console mock"
```

Expected: C shows four bidder nodes, at least eight evidence fields, selectable danger cells, and a source-rich evidence drawer.

---

### Task 7: Cross-Variant State, Theme, Metadata Filters, and Accessibility

**Files:**

- Modify: `desktop/mock/design-spec-variants/model.js`
- Modify: `desktop/mock/design-spec-variants/render-common.js`
- Modify: `desktop/mock/design-spec-variants/render-guided.js`
- Modify: `desktop/mock/design-spec-variants/render-verdict.js`
- Modify: `desktop/mock/design-spec-variants/render-matrix.js`
- Modify: `desktop/mock/design-spec-variants/app.js`
- Modify: `desktop/mock/design-spec-variants/styles.css`
- Modify: `desktop/tests/mock-variants-model.test.ts`
- Modify: `desktop/tests/e2e/design_spec_variants.py`

**Interfaces:**

- Produces: state-preserving `SET_VARIANT`, `SET_REPORT_FILTER`, `SET_METADATA_FILTER`, `TOGGLE_TRACE`, `SHOW_METADATA_FOR_TRACE`, `SHOW_REPORT`, `SET_PRIMARY`, and `RESET` actions.
- Produces: local keys `docmeta-mock-variant` and `docmeta-mock-primary` only; folder names, files, reports, and evidence never enter local storage.
- Produces: selectors `variant-switch`, `theme-toggle`, `theme-swatch`, `metadata-search`, `metadata-bidder-filter`, `duplicates-only`, and `reset-demo`.

- [ ] **Step 1: Add failing model invariants**

```typescript
test("reset clears evidence state without changing the selected theme", () => {
  const model = loadModel();
  const dirty = {
    ...model.createInitialState("#matrix"),
    view: "metadata",
    primary: "#7c3aed",
    expandedTraceId: "trace-author-wanglei",
    metadataFilters: { bidderId: "bidder-a", query: "王磊", duplicatesOnly: true },
  };
  const reset = model.reduce(dirty, { type: "RESET" });
  expect(reset.view).toBe("empty");
  expect(reset.primary).toBe("#7c3aed");
  expect(reset.expandedTraceId).toBeNull();
  expect(reset.metadataFilters).toEqual({ bidderId: "all", query: "", duplicatesOnly: false });
});
```

- [ ] **Step 2: Add the failing cross-variant Playwright journey**

```python
def test_state_theme_and_filters_survive_variant_switch(page: Page) -> None:
    open_completed_variant(page, "verdict")
    page.get_by_test_id("report-filter-danger").click()
    page.get_by_test_id("variant-switch").select_option("matrix")
    page.get_by_test_id("matrix-shell").wait_for()
    assert page.get_by_test_id("trace-count").inner_text() == "2"
    page.get_by_test_id("theme-toggle").click()
    page.get_by_test_id("theme-swatch").filter(has_text="电紫").click()
    assert page.locator("html").evaluate("node => getComputedStyle(node).getPropertyValue('--primary').trim()") == "#7c3aed"
    page.reload()
    assert page.locator("html").evaluate("node => getComputedStyle(node).getPropertyValue('--primary').trim()") == "#7c3aed"
```

- [ ] **Step 3: Implement one version/theme side-effect boundary**

`app.js` updates `location.hash`, `docmeta-mock-variant`, and `docmeta-mock-primary` only after successful reducer actions. Theme choices are the specification-approved `#034ed6`, `#7c3aed`, and `#0f766e`. The theme UI shows name and hex value; it never changes danger/warning/success variables.

- [ ] **Step 4: Complete shared metadata filter semantics**

All three metadata views use the same model selector. Query matching is case-insensitive over file name, field label, raw value, normalized value, and parser name. Bidder, query, and duplicates-only filters compose with logical AND. The empty result includes a `clear-metadata-filters` action.

- [ ] **Step 5: Verify keyboard and reduced-motion behavior**

Extend the Playwright script to use `page.keyboard.press("Tab")` until `load-demo` receives focus and assert the computed outline width is `2px`. Create a second context with `reduced_motion="reduce"`, enter scanning and B report states, and assert every element matched by `.scan-beam, .verdict-enter > *` has `animation-name: none`.

- [ ] **Step 6: Run focused static and browser checks**

```bash
pnpm test -- mock-variants-model.test.ts
pnpm exec biome check mock/design-spec-variants tests/mock-variants-model.test.ts
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

Expected: all commands PASS; switching B→C preserves the danger filter, theme survives reload, keyboard focus is visible, and reduced motion disables decorative animation.

- [ ] **Step 7: Commit Task 7 only**

```bash
git add desktop/mock/design-spec-variants desktop/tests/mock-variants-model.test.ts desktop/tests/e2e/design_spec_variants.py
git commit -m "feat: complete cross-variant mock interactions"
```

---

### Task 8: Screenshot Matrix, Visual Critique, and Final Verification

**Files:**

- Modify only if the visual/test evidence identifies a defect: files under `desktop/mock/design-spec-variants/` and `desktop/tests/e2e/design_spec_variants.py`
- Do not create repository screenshot files.

**Interfaces:**

- Consumes: all three completed variants.
- Produces: temporary screenshots named `<viewport>-<variant>-<view>.png`.
- Produces: a clean browser console and full interaction verification.

- [ ] **Step 1: Add deterministic screenshot capture**

Use this fixed matrix in the Playwright script:

```python
VIEWPORTS = {
    "1440x900": {"width": 1440, "height": 900},
    "1280x800": {"width": 1280, "height": 800},
    "1024x720": {"width": 1024, "height": 720},
}
VARIANTS = ("guided", "verdict", "matrix")
CAPTURE_VIEWS = ("empty", "scanning", "report", "metadata")
```

Default `DOCMETA_MOCK_SCREENSHOT_DIR` to
`Path(tempfile.gettempdir()) / "docmeta-design-spec-variants"`. Capture full-page PNGs after fonts/layout settle; never write them below the repository root.

- [ ] **Step 2: Run the screenshot and interaction suite**

```bash
DOCMETA_MOCK_SCREENSHOT_DIR="$(mktemp -d)" uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

Expected: 36 screenshots, no console errors, no page errors, and exit code 0.

- [ ] **Step 3: Visually inspect the 1440×900 report and metadata screenshots**

Inspect all six primary screenshots and answer these literal checks for each variant:

- Does the 560px wash end before ordinary body content?
- Are shallow surfaces separated by hairlines/space without shadow?
- Is the only large shadow attached to a dark data panel?
- Is brand blue scarce enough that danger and warning remain unmistakable?
- Is the signature device unique to the subject: step rail, verdict/trust chain, or evidence matrix?
- Are any labels clipped, controls overlapped, columns unreadable, or scroll regions hidden?

Fix every observed failure in the responsible variant stylesheet or renderer, then rerun Step 2.

- [ ] **Step 4: Remove one nonessential decorative element per variant if present**

For A, remove any decoration not encoding workflow. For B, remove any statistic that merely repeats the verdict/trust panel. For C, remove any matrix column or field that does not help explain a trace. Rerun the 1440×900 captures after the edit.

- [ ] **Step 5: Run repository-proportionate final verification**

From `desktop/`:

```bash
pnpm test
pnpm typecheck
pnpm exec biome check mock/design-spec-variants tests/mock-variants-model.test.ts
uv run --with playwright==1.62.0 python tests/e2e/design_spec_variants.py
```

From the repository root:

```bash
git diff --check
git status --short
```

Expected: desktop tests and typecheck pass; mock-specific Biome and Playwright checks pass; `git diff --check` reports no whitespace errors; existing unrelated user changes remain unstaged and unmodified.

- [ ] **Step 6: Commit only verified mock/test corrections**

```bash
git add desktop/mock/design-spec-variants desktop/tests/mock-variants-model.test.ts desktop/tests/e2e/design_spec_variants.py
git commit -m "test: verify three interactive UI mocks"
```

- [ ] **Step 7: Handoff**

Open `desktop/mock/design-spec-variants/index.html` in the user’s browser, leave it on the launcher, and report:

- the direct clickable local file;
- the three tested variant names;
- the tested viewports and interaction paths;
- the temporary screenshot directory;
- any unrelated pre-existing dirty files that were intentionally preserved.

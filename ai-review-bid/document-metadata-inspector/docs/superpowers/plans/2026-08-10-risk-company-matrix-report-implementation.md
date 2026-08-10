# 风险项 × 涉险公司矩阵报告 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把桌面端核验结果页改成“风险项为行、涉险公司为列”的矩阵报告，让管理者首屏只看到高风险与待复核项，并完全隐藏未涉险公司、无异常字段和通过项明细。

**Architecture:** 在现有 `ScanResult` 合同之上新增一个纯视图模型 `buildRiskMatrixModel()`，先稳定完成风险排序、公司有序并集、精确命中关系和证据文件分组，再由 `renderResult()` 将该模型渲染为可键盘操作的矩阵与局部联动证据面板。风险判定仍由既有报告适配器完成；本次不改共享合同、状态机、IPC 或 Python/Java 核心。

**Tech Stack:** TypeScript 7、原生 DOM API、CSS Grid/Table、Vitest 4、Vite 8、Python 3.12、Playwright 1.62、pnpm 11、uv。

## Global Constraints

- 事实规格是 `docs/superpowers/specs/2026-08-10-risk-company-matrix-report-design.md`，视觉事实源是 `/Users/zhongerbing/Desktop/设计规范/`。
- 页面只展示 `ScanResult.personTraces` 与 `ScanResult.cautionTraces`；不渲染无异常公司、无异常字段、通过项标签或正常文件列表。
- 高风险始终排在待复核之前；同等级内保持输入顺序，不按文字、公司或时间重排。
- 公司列只取所有风险 `groupIds` 与 `kind === "bidder"` 组的有序交集，并严格保持 `ScanResult.groups` 顺序。
- 不修改 `TraceSummary`、`ScanResult`、`ComparisonReportJson`、报告适配器、Electron IPC、状态机或后端风险判定。
- 不新增运行时依赖、UI 框架、图表库、外链资源或运行时下载。
- 使用现有颜色变量：主色 `#034ed6`、高风险 `#c93438`、高风险弱底 `#fdeeee`、待复核 `#a85c00`、待复核弱底 `#fdf3e4`、正文 `#141928`、次级文字 `#5d6579`、弱文字 `#6b7489`、边框 `#e8eaf0`、柔和分隔 `#f0f2f7`、深色面板 `#0e1226`。
- 浅色矩阵不加投影；仅右侧深色证据面板使用投影；不使用 emoji、图标字体、发光、玻璃拟态或装饰性动画。
- 风险项第一列必须是原生 `<button type="button">`；保留 2px 可见焦点环和至少 28px 可点击高度。
- 证据面板只显示映射成功的公司名与文件名；缺失文档映射时跳过内部 ID，全部缺失时显示“没有可显示的文件证据”。
- 可用宽度不超过 1150px 时证据面板落到矩阵下方；矩阵第一列最小 300px、公司列最小 150px；大量公司只让矩阵容器横向滚动，页面本身不横向溢出。
- 正式视觉验收尺寸为 1440×900、1280×800、1024×720，并检查 `prefers-reduced-motion: reduce`。
- 当前 `desktop/src/renderer/render-result.ts` 与 `desktop/src/renderer/styles.css` 已包含用户的未提交改动。实施时只做局部补丁，不覆盖其他差异；未经用户明确授权，不把这些重叠文件加入提交。每个任务以测试结果和 `git diff --check` 作为安全检查点。

---

## File Map

- Modify: `desktop/src/renderer/render-result.ts`
  - 保留字段中文映射、时间格式化、`connectionTracks()` 和报告签名。
  - 新增纯矩阵模型及矩阵、证据面板、无风险态和不一致输入态的 DOM 构建。
  - 删除结果页旧时间轴与“正常项”标签渲染，但不改其他页面。
- Modify: `desktop/src/renderer/styles.css`
  - 仅替换当前 `.cf-*`、`.tl-*`、`.r-co-file*` 结果页样式块，新增 `.rm-*` 作用域样式。
  - 保留顶栏、目录选择、扫描、元数据明细和状态栏样式。
- Modify: `desktop/tests/render-result.test.ts`
  - 保留 `connectionTracks()` 回归测试，新增纯矩阵模型的排序、公司过滤、命中、证据分组和边界测试。
- Create: `desktop/tests/e2e/risk_matrix_renderer.py`
  - 自建临时投标人目录和合成报告，启动真实 Vite 预览，覆盖风险矩阵、响应式、大量公司、键盘交互和极简无风险态。
- Modify: `desktop/tests/e2e/renderer_real_data.py`
  - 保留真实运行时的选目录、停止和重启流程，把旧“投标人卡片/SVG 连线”断言迁移到矩阵或极简无风险态。

---

### Task 1: 建立纯风险矩阵模型

**Files:**

- Modify: `desktop/tests/render-result.test.ts`
- Modify: `desktop/src/renderer/render-result.ts`（`Report helpers` 到 `Main render` 之间）

**Interfaces:**

- Consumes: `ScanResult`, `TraceSummary`, `ResultGroup`, `DocumentSummary`, `tField()`。
- Produces: `buildRiskMatrixModel(result: ScanResult): RiskMatrixModel`，以及导出的 `RiskMatrixCompany`、`RiskMatrixEvidenceGroup`、`RiskMatrixRow`、`RiskMatrixModel` 类型，供 Task 2 的 DOM 层直接消费。

- [ ] **Step 1: 在单元测试中补齐可复用的合成结果工厂**

在 `desktop/tests/render-result.test.ts` 将 import 扩为：

```ts
import { describe, expect, test } from "vitest";

import {
  buildRiskMatrixModel,
  connectionTracks,
} from "../src/renderer/render-result";
import type {
  DocumentSummary,
  ResultGroup,
  ScanResult,
  TraceSummary,
} from "../src/shared/contracts";
```

保留现有 `trace()` 与 `connectionTracks` 测试，并在其后加入这些工厂：

```ts
function document(id: string, name: string): DocumentSummary {
  return {
    id,
    name,
    relativePath: name,
    format: "docx",
    family: "ooxml",
    status: "complete",
    observationCount: 1,
    parserRunCount: 1,
    warningCount: 0,
    sizeBytes: 128,
    sha256Prefix: id.slice(0, 12),
    parserRuns: [],
    observations: [],
    keyFields: {
      author: "",
      created: "",
      modified: "",
      lastModifiedBy: "",
      company: "",
      template: "",
    },
  };
}

function group(
  id: string,
  name: string,
  documents: DocumentSummary[],
  kind: ResultGroup["kind"] = "bidder",
): ResultGroup {
  return { id, kind, name, documents };
}

function scanResult(overrides: Partial<ScanResult> = {}): ScanResult {
  return {
    rootName: "4-投标文件",
    scannedAt: "2026-08-10T01:58:00.000Z",
    documentCount: 6,
    completeDocumentCount: 6,
    observationCount: 120,
    parserRunCount: 18,
    warningCount: 0,
    bidderCount: 4,
    groups: [],
    personTraces: [],
    cautionTraces: [],
    ...overrides,
  };
}
```

- [ ] **Step 2: 写出排序、公司过滤、精确命中和证据分组的失败测试**

在同一测试文件加入：

```ts
describe("buildRiskMatrixModel", () => {
  test("orders risks by tone and keeps only involved bidder columns in group order", () => {
    const result = scanResult({
      groups: [
        group("root-files", "根目录文件", [document("root-doc", "说明.docx")], "root-files"),
        group("bidder-b", "正阳工程", [document("b-author", "投标函.docx")]),
        group("bidder-safe", "无异常公司", [document("safe-doc", "报价.xlsx")]),
        group("bidder-a", "宏达建设", [document("a-author", "技术方案.docx")]),
        group("bidder-c", "华盛路桥", [document("c-template", "施工组织.pdf")]),
      ],
      personTraces: [
        {
          ...trace("author", "danger", ["bidder-a", "bidder-b"]),
          value: "李建国",
          fieldNames: ["author", "last_modified_by"],
          documentIds: ["a-author", "missing-document", "b-author", "a-author"],
        },
        {
          ...trace("company", "danger", ["bidder-c", "bidder-a"]),
          value: "宏达建设集团有限公司",
          fieldNames: ["company"],
          documentIds: ["c-template", "a-author"],
        },
      ],
      cautionTraces: [
        {
          ...trace("template", "caution", ["bidder-b", "bidder-c"]),
          value: "Normal.dotm",
          fieldNames: ["template"],
          documentIds: ["b-author", "c-template"],
        },
      ],
    });

    const model = buildRiskMatrixModel(result);

    expect(model.companies).toEqual([
      { id: "bidder-b", name: "正阳工程" },
      { id: "bidder-a", name: "宏达建设" },
      { id: "bidder-c", name: "华盛路桥" },
    ]);
    expect(model.rows.map((row) => [row.id, row.tone])).toEqual([
      ["author", "danger"],
      ["company", "danger"],
      ["template", "caution"],
    ]);
    expect(model.rows[0]).toMatchObject({
      field: "作者/最后修改者",
      value: "李建国",
      companyIds: ["bidder-b", "bidder-a"],
      evidenceFileCount: 2,
      evidenceGroups: [
        { companyId: "bidder-b", company: "正阳工程", files: ["投标函.docx"] },
        { companyId: "bidder-a", company: "宏达建设", files: ["技术方案.docx"] },
      ],
    });
    expect(model.rows[1]?.companyIds).toEqual(["bidder-a", "bidder-c"]);
    expect(model.rows[2]?.companyIds).toEqual(["bidder-b", "bidder-c"]);
    expect(model.dangerCount).toBe(2);
    expect(model.cautionCount).toBe(1);
    expect(model.missingBidderContext).toBe(false);
    expect(JSON.stringify(model)).not.toContain("missing-document");
    expect(JSON.stringify(model)).not.toContain("无异常公司");
    expect(JSON.stringify(model)).not.toContain("root-doc");
  });

  test("returns an empty model without manufacturing safe details", () => {
    const model = buildRiskMatrixModel(
      scanResult({
        groups: [group("bidder-safe", "无异常公司", [document("safe", "报价.xlsx")])],
      }),
    );

    expect(model).toEqual({
      companies: [],
      rows: [],
      dangerCount: 0,
      cautionCount: 0,
      missingBidderContext: false,
    });
  });

  test("fails closed when traces have no displayable bidder group", () => {
    const model = buildRiskMatrixModel(
      scanResult({
        groups: [group("bidder-a", "宏达建设", [document("a", "投标函.docx")])],
        personTraces: [trace("ghost", "danger", ["unknown-bidder"])],
      }),
    );

    expect(model.rows).toHaveLength(1);
    expect(model.companies).toEqual([]);
    expect(model.missingBidderContext).toBe(true);
  });
});
```

- [ ] **Step 3: 运行新增单元测试，确认先红**

Run:

```bash
cd desktop
pnpm exec vitest run tests/render-result.test.ts
```

Expected: FAIL，TypeScript/Vitest 报告 `buildRiskMatrixModel` 尚未导出；现有 `connectionTracks` 测试仍通过。

- [ ] **Step 4: 在结果页模块实现纯矩阵模型**

在 `traceFieldLabel()` 后、`reportSignature()` 前加入：

```ts
export interface RiskMatrixCompany {
  id: string;
  name: string;
}

export interface RiskMatrixEvidenceGroup {
  companyId: string;
  company: string;
  files: string[];
}

export interface RiskMatrixRow {
  id: string;
  tone: "danger" | "caution";
  field: string;
  value: string;
  companyIds: string[];
  evidenceGroups: RiskMatrixEvidenceGroup[];
  evidenceFileCount: number;
}

export interface RiskMatrixModel {
  companies: RiskMatrixCompany[];
  rows: RiskMatrixRow[];
  dangerCount: number;
  cautionCount: number;
  missingBidderContext: boolean;
}

export function buildRiskMatrixModel(result: ScanResult): RiskMatrixModel {
  const traces = [...result.personTraces, ...result.cautionTraces];
  const riskyGroupIds = new Set(traces.flatMap((trace) => trace.groupIds));
  const groupNames = buildGroupNames(result);
  const bidderGroups = result.groups.filter(
    (group) => group.kind === "bidder" && riskyGroupIds.has(group.id),
  );
  const companies = bidderGroups.map((group) => ({
    id: group.id,
    name: groupNames.get(group.id) ?? group.name,
  }));
  const companyById = new Map(companies.map((company) => [company.id, company] as const));
  const documentInfo = new Map<
    string,
    { companyId: string; company: string; file: string }
  >();

  for (const group of bidderGroups) {
    const company = companyById.get(group.id);
    if (company === undefined) {
      continue;
    }
    for (const document of group.documents) {
      documentInfo.set(document.id, {
        companyId: company.id,
        company: company.name,
        file: document.name,
      });
    }
  }

  const rows = traces.map((trace): RiskMatrixRow => {
    const traceGroupIds = new Set(trace.groupIds);
    const companyIds = companies
      .filter((company) => traceGroupIds.has(company.id))
      .map((company) => company.id);
    const filesByCompany = new Map<string, string[]>();
    const seenDocumentIds = new Set<string>();

    for (const documentId of trace.documentIds) {
      if (seenDocumentIds.has(documentId)) {
        continue;
      }
      seenDocumentIds.add(documentId);
      const info = documentInfo.get(documentId);
      if (info === undefined || !traceGroupIds.has(info.companyId)) {
        continue;
      }
      const files = filesByCompany.get(info.companyId) ?? [];
      files.push(info.file);
      filesByCompany.set(info.companyId, files);
    }

    const evidenceGroups = companies.flatMap((company) => {
      const files = filesByCompany.get(company.id);
      return files === undefined
        ? []
        : [{ companyId: company.id, company: company.name, files }];
    });

    return {
      id: trace.id,
      tone: trace.tone,
      field: traceFieldLabel(trace),
      value: trace.value,
      companyIds,
      evidenceGroups,
      evidenceFileCount: evidenceGroups.reduce(
        (total, evidenceGroup) => total + evidenceGroup.files.length,
        0,
      ),
    };
  });

  return {
    companies,
    rows,
    dangerCount: result.personTraces.length,
    cautionCount: result.cautionTraces.length,
    missingBidderContext: traces.length > 0 && companies.length === 0,
  };
}
```

实现时继续使用大括号风格，不把 `continue` 压成单行；若 Biome 自动格式化上述片段，以仓库格式器结果为准，但函数签名和返回字段不得改变。

- [ ] **Step 5: 运行单元测试，确认纯模型转绿**

Run:

```bash
cd desktop
pnpm exec vitest run tests/render-result.test.ts
```

Expected: `connectionTracks` 与三个 `buildRiskMatrixModel` 测试全部 PASS。

- [ ] **Step 6: 做任务级安全检查点**

Run:

```bash
git diff --check -- desktop/src/renderer/render-result.ts desktop/tests/render-result.test.ts
git diff --stat -- desktop/src/renderer/render-result.ts desktop/tests/render-result.test.ts
git status --short
```

Expected: 无 whitespace error；状态只体现既有差异和本任务修改。由于 `render-result.ts` 的改动与用户现有未提交内容重叠，本任务不执行 `git add` 或 `git commit`。

---

### Task 2: 用真实浏览器测试锁定矩阵交互与响应式行为

**Files:**

- Create: `desktop/tests/e2e/risk_matrix_renderer.py`
- Modify: `desktop/src/renderer/render-result.ts`（`Main render` 及旧 `buildAllClear()` / `buildTimelineSection()`）
- Modify: `desktop/src/renderer/styles.css`（当前 `Card flow report layout` 到 `Signature line`）

**Interfaces:**

- Consumes: Task 1 的 `RiskMatrixModel` 与 `buildRiskMatrixModel(result)`。
- Produces: `renderResult(result: ScanResult): HTMLElement` 中的测试接口：`risk-summary`、`risk-matrix`、`risk-matrix-scroll`、`risk-company-header`、`risk-row`、`risk-row-button`、`risk-hit`、`risk-evidence-panel`、`risk-evidence-company`、`risk-evidence-file`、`risk-clear`、`risk-context-error`。

- [ ] **Step 1: 创建自包含的 Playwright 风险矩阵验收脚本**

创建 `desktop/tests/e2e/risk_matrix_renderer.py`，内容如下：

```python
"""Verify the risk matrix renderer with deterministic synthetic evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Error, Page, sync_playwright

type JsonObject = dict[str, object]


def _require(*, condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _document_id(path: Path) -> str:
    return _sha256_text(str(path.resolve()))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _report_document(path: Path) -> JsonObject:
    content = path.read_bytes()
    return {
        "display_name": path.name,
        "source_path_sha256": _document_id(path),
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "identity": {
            "declared_format": path.suffix.removeprefix("."),
            "family": "ooxml",
            "status": "identified",
        },
        "status": "complete",
        "observations": [],
        "parser_runs": [],
        "warnings": [],
    }


def _match(
    canonical_name: str,
    value: str,
    trace_kind: str,
    paths: list[Path],
) -> JsonObject:
    document_ids = [_document_id(path) for path in paths]
    return {
        "canonical_name": canonical_name,
        "normalized_value": value,
        "trace_kind": trace_kind,
        "field_names": [canonical_name],
        "raw_values": [value],
        "evidence_count": len(document_ids),
        "document_ids": document_ids,
    }


def _write_report(
    report_path: Path,
    documents: list[Path],
    matches: list[JsonObject],
) -> None:
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "documents": [_report_document(path) for path in documents],
                "matches": matches,
                "warnings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _wait_for_server(port: int, process: subprocess.Popen[str]) -> None:
    for _attempt in range(200):
        if process.poll() is not None:
            message = f"preview stopped with exit code {process.returncode}"
            raise RuntimeError(message)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    message = "preview did not become ready within 20 seconds"
    raise RuntimeError(message)


def _rescan(page: Page, expected_test_id: str) -> None:
    page.get_by_test_id("rescan").click()
    page.get_by_test_id(expected_test_id).wait_for(timeout=15_000)


def main() -> None:  # noqa: PLR0915 - one linear browser acceptance scenario
    """Run all synthetic matrix, responsive, and clear-state checks."""
    desktop_root = Path(__file__).resolve().parents[2]
    screenshot_root = Path(
        os.environ.get(
            "DOCMETA_SCREENSHOT_DIR",
            str(Path(tempfile.gettempdir()) / "docmeta-risk-matrix-preview"),
        )
    )
    screenshot_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="docmeta-risk-matrix-") as temporary:
        root = Path(temporary).resolve()
        bidder_names = [
            "01-宏达建设",
            "02-正阳工程",
            "03-华盛路桥",
            "04-无异常公司",
            "05-远山工程",
            "06-海川建设",
            "07-天成路桥",
            "08-嘉禾工程",
        ]
        documents: list[Path] = []
        for index, bidder_name in enumerate(bidder_names, start=1):
            bidder = root / bidder_name
            bidder.mkdir()
            document_path = bidder / f"证据-{index:02d}.docx"
            document_path.write_bytes(f"synthetic-{index}".encode())
            documents.append(document_path)

        report_path = root / "comparison-report.json"
        initial_matches = [
            _match("author", "李建国", "person_trace", documents[0:2]),
            _match("template", "Normal.dotm", "document_environment_trace", documents[0:3]),
            _match(
                "created",
                "2026-07-15T09:30:00+08:00",
                "document_environment_trace",
                documents[1:3],
            ),
        ]
        _write_report(report_path, documents, initial_matches)

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        pnpm = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm")
        if pnpm is None:
            message = "pnpm executable was not found"
            raise RuntimeError(message)
        command = [
            pnpm,
            "preview:real",
            "--",
            "--folder",
            str(root),
            "--report",
            str(report_path),
            "--port",
            str(port),
        ]
        process = subprocess.Popen(  # noqa: S603 - fixed local pnpm command and arguments
            command,
            cwd=desktop_root,
            text=True,
            start_new_session=os.name != "nt",
        )

        try:
            _wait_for_server(port, process)
            console_errors: list[str] = []
            page_errors: list[str] = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=os.environ.get("DOCMETA_CHROMIUM_EXECUTABLE"),
                )
                page = browser.new_page(viewport={"width": 1440, "height": 900})

                def record_console(message: ConsoleMessage) -> None:
                    if message.type == "error":
                        console_errors.append(message.text)

                def record_page_error(error: Error) -> None:
                    page_errors.append(str(error))

                page.on("console", record_console)
                page.on("pageerror", record_page_error)
                page.goto(base_url)
                page.wait_for_load_state("networkidle")
                page.get_by_role("button", name="选择文件夹", exact=True).click()
                selected_folder = page.get_by_test_id("selected-folder")
                selected_folder.wait_for()
                selected_folder.get_by_test_id("start-scan").click()
                page.get_by_test_id("risk-matrix").wait_for(timeout=15_000)

                _require(
                    condition=page.get_by_test_id("risk-summary").inner_text()
                    == "3 项风险涉及 3 家公司",
                    message="risk summary",
                )
                _require(
                    condition=page.get_by_test_id("risk-row").count() == 3,
                    message="risk row count",
                )
                _require(
                    condition=page.get_by_test_id("risk-company-header").count() == 3,
                    message="involved company count",
                )
                _require(
                    condition=page.get_by_test_id("risk-hit").count() == 7,
                    message="exact matrix hits",
                )
                _require(
                    condition="无异常公司" not in page.get_by_test_id("result-page").inner_text(),
                    message="uninvolved company must be hidden",
                )
                _require(
                    condition=page.locator(".cf-stats, .cf-stat").count() == 0,
                    message="legacy coverage statistics must be absent",
                )
                _require(
                    condition="元数据条" not in page.get_by_test_id("result-page").inner_text(),
                    message="metadata totals must not compete with risk conclusion",
                )
                _require(
                    condition="高风险" in page.get_by_test_id("risk-evidence-panel").inner_text(),
                    message="first danger row selected by default",
                )
                _require(
                    condition="李建国" in page.get_by_test_id("risk-evidence-panel").inner_text(),
                    message="default evidence value",
                )

                template_button = page.get_by_test_id("risk-row-button").nth(1)
                template_button.focus()
                template_button.press("Enter")
                panel_text = page.get_by_test_id("risk-evidence-panel").inner_text()
                _require(condition="待复核" in panel_text, message="keyboard-selected tone")
                _require(condition="Normal.dotm" in panel_text, message="keyboard-selected value")
                _require(
                    condition=page.get_by_test_id("risk-evidence-company").count() == 3,
                    message="evidence grouped by company",
                )
                _require(
                    condition=page.get_by_test_id("risk-evidence-file").count() == 3,
                    message="evidence file count",
                )
                focus_style = template_button.evaluate(
                    "element => getComputedStyle(element).outlineWidth"
                )
                _require(condition=focus_style == "2px", message="visible focus ring")

                matrix_box = page.get_by_test_id("risk-matrix").bounding_box()
                panel_box = page.get_by_test_id("risk-evidence-panel").bounding_box()
                _require(
                    condition=matrix_box is not None
                    and panel_box is not None
                    and panel_box["x"] > matrix_box["x"],
                    message="desktop evidence panel position",
                )
                page.screenshot(path=screenshot_root / "01-risk-matrix-1440.png", full_page=True)

                page.set_viewport_size({"width": 1280, "height": 800})
                _require(
                    condition=page.evaluate(
                        "document.documentElement.scrollWidth <= "
                        "document.documentElement.clientWidth"
                    ),
                    message="1280 page overflow",
                )
                page.screenshot(path=screenshot_root / "02-risk-matrix-1280.png", full_page=True)

                page.set_viewport_size({"width": 1024, "height": 720})
                matrix_box = page.get_by_test_id("risk-matrix").bounding_box()
                panel_box = page.get_by_test_id("risk-evidence-panel").bounding_box()
                _require(
                    condition=matrix_box is not None
                    and panel_box is not None
                    and panel_box["y"] >= matrix_box["y"] + matrix_box["height"],
                    message="1024 evidence panel must stack below matrix",
                )
                _require(
                    condition=page.evaluate(
                        "document.documentElement.scrollWidth <= "
                        "document.documentElement.clientWidth"
                    ),
                    message="1024 page overflow",
                )
                page.screenshot(path=screenshot_root / "03-risk-matrix-1024.png", full_page=True)

                _write_report(
                    report_path,
                    documents,
                    [
                        _match(
                            "template",
                            "Shared-template.dotm",
                            "document_environment_trace",
                            documents,
                        )
                    ],
                )
                _rescan(page, "risk-matrix")
                _require(
                    condition=page.get_by_test_id("risk-summary").inner_text()
                    == "1 项风险涉及 8 家公司",
                    message="many-company summary",
                )
                _require(
                    condition=page.locator(".rm-badge--danger").count() == 0,
                    message="absent danger tone must not render a zero badge",
                )
                _require(
                    condition="高风险 0" not in page.get_by_test_id("result-page").inner_text(),
                    message="absent risk level must remain hidden",
                )
                matrix_scroll = page.get_by_test_id("risk-matrix-scroll")
                _require(
                    condition=matrix_scroll.evaluate(
                        "element => element.scrollWidth > element.clientWidth"
                    ),
                    message="many-company matrix needs local horizontal scrolling",
                )
                sticky_cell = page.locator(".rm-risk-col").first
                sticky_before = sticky_cell.bounding_box()
                matrix_scroll.evaluate("element => { element.scrollLeft = 600; }")
                sticky_after = sticky_cell.bounding_box()
                _require(
                    condition=sticky_before is not None
                    and sticky_after is not None
                    and abs(sticky_before["x"] - sticky_after["x"]) < 1,
                    message="sticky first column",
                )

                page.emulate_media(reduced_motion="reduce")
                page.get_by_test_id("risk-row-button").first.press("Enter")
                _require(
                    condition=page.get_by_test_id("risk-evidence-panel").is_visible(),
                    message="reduced motion keeps interaction functional",
                )

                _write_report(report_path, documents, [])
                _rescan(page, "risk-clear")
                clear_text = page.get_by_test_id("risk-clear").inner_text()
                _require(
                    condition="未发现需关注的跨投标人风险" in clear_text,
                    message="minimal no-risk conclusion",
                )
                _require(
                    condition=page.get_by_test_id("risk-matrix").count() == 0,
                    message="no matrix in clear state",
                )
                for forbidden in ["公司名无重复", "作者无重复", "模板无重复", "无异常公司"]:
                    _require(
                        condition=forbidden not in page.get_by_test_id("result-page").inner_text(),
                        message=f"clear state leaked: {forbidden}",
                    )
                page.screenshot(path=screenshot_root / "04-risk-clear.png", full_page=True)

                _require(condition=not console_errors, message=console_errors)
                _require(condition=not page_errors, message=page_errors)
                browser.close()
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    process.terminate()
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行浏览器测试，确认旧页面先红**

Run:

```bash
cd desktop
uv run --with playwright==1.62.0 python tests/e2e/risk_matrix_renderer.py
```

Expected: FAIL，等待 `data-testid="risk-matrix"` 超时；临时 Vite 进程在 `finally` 中被终止，不遗留后台进程。

- [ ] **Step 3: 用矩阵和证据面板替换旧时间轴 DOM**

在 `desktop/src/renderer/render-result.ts` 中删除仅供旧时间轴使用的 `buildDocInfo()`、旧 `buildTimelineSection()`、旧统计卡片和带正常项标签的 `buildAllClear()`；保留 `buildGroupNames()` import、`connectionTracks()`、字段翻译、时间格式化与 `reportSignature()`。加入以下 DOM helpers：

```ts
function riskMeta(result: ScanResult): string {
  const time = result.scannedAt ? fmtScanTime(result.scannedAt) : "";
  return `${result.rootName} · 核验时间 ${time} · 离线分析`;
}

function buildRiskBadges(model: RiskMatrixModel): HTMLElement {
  const badges = element("div", "rm-badges");
  if (model.dangerCount > 0) {
    badges.append(element("span", "rm-badge rm-badge--danger", `高风险 ${model.dangerCount}`));
  }
  if (model.cautionCount > 0) {
    badges.append(
      element("span", "rm-badge rm-badge--caution", `待复核 ${model.cautionCount}`),
    );
  }
  badges.append(element("span", "rm-hidden-note", "未涉险公司已隐藏"));
  return badges;
}

function updateEvidencePanel(panel: HTMLElement, row: RiskMatrixRow): void {
  panel.dataset.tone = row.tone;
  const heading = element("div", "rm-evidence__heading");
  heading.append(
    element(
      "span",
      `rm-evidence__tone rm-evidence__tone--${row.tone}`,
      row.tone === "danger" ? "高风险" : "待复核",
    ),
    element("span", "rm-evidence__count", `${row.evidenceFileCount} 份证据文件`),
  );
  const title = element("h2", "rm-evidence__title", row.field);
  title.id = "risk-evidence-title";
  const value = element("div", "rm-evidence__value", row.value);
  const groups = element("div", "rm-evidence__groups");

  if (row.evidenceGroups.length === 0) {
    groups.append(element("p", "rm-evidence__empty", "没有可显示的文件证据"));
  } else {
    for (const evidenceGroup of row.evidenceGroups) {
      const company = element("section", "rm-evidence__company");
      testId(company, "risk-evidence-company");
      company.append(element("h3", "rm-evidence__company-name", evidenceGroup.company));
      const files = element("ul", "rm-evidence__files");
      for (const filename of evidenceGroup.files) {
        const item = element("li", "rm-evidence__file", filename);
        testId(item, "risk-evidence-file");
        files.append(item);
      }
      company.append(files);
      groups.append(company);
    }
  }

  panel.replaceChildren(heading, title, value, groups);
}

function buildEvidencePanel(row: RiskMatrixRow): HTMLElement {
  const panel = element("aside", "rm-evidence");
  testId(panel, "risk-evidence-panel");
  panel.setAttribute("aria-live", "polite");
  panel.setAttribute("aria-labelledby", "risk-evidence-title");
  updateEvidencePanel(panel, row);
  return panel;
}

function buildMatrix(
  model: RiskMatrixModel,
  panel: HTMLElement,
  initialRow: RiskMatrixRow,
): HTMLElement {
  const shell = element("div", "rm-matrix-shell");
  const scroll = element("div", "rm-matrix-scroll");
  testId(scroll, "risk-matrix-scroll");
  const table = element("table", "rm-table");
  testId(table, "risk-matrix");
  table.setAttribute("aria-label", "风险项与涉险公司命中矩阵");
  const head = element("thead");
  const headRow = element("tr");
  const riskHeading = element("th", "rm-risk-col rm-risk-col--head", "风险项 / 命中值");
  riskHeading.scope = "col";
  headRow.append(riskHeading);
  for (const company of model.companies) {
    const heading = element("th", "rm-company-head");
    heading.scope = "col";
    heading.title = company.name;
    testId(heading, "risk-company-header");
    const headingText = element("span", "rm-company-head__text", company.name);
    heading.append(headingText);
    headRow.append(heading);
  }
  head.append(headRow);

  const body = element("tbody");
  const rowNodes = new Map<string, HTMLTableRowElement>();
  const buttons = new Map<string, HTMLButtonElement>();
  const selectRow = (selected: RiskMatrixRow): void => {
    for (const row of model.rows) {
      const selectedNow = row.id === selected.id;
      const rowNode = rowNodes.get(row.id);
      if (rowNode !== undefined) {
        rowNode.dataset.selected = String(selectedNow);
      }
      buttons.get(row.id)?.setAttribute("aria-pressed", String(selectedNow));
    }
    updateEvidencePanel(panel, selected);
  };

  for (const row of model.rows) {
    const tableRow = element("tr", `rm-row rm-row--${row.tone}`);
    testId(tableRow, "risk-row");
    tableRow.dataset.selected = "false";
    const riskCell = element("th", "rm-risk-col");
    riskCell.scope = "row";
    const button = element("button", "rm-risk-button");
    button.type = "button";
    button.setAttribute("aria-label", `查看${row.field}：${row.value}的证据`);
    button.setAttribute("aria-pressed", "false");
    testId(button, "risk-row-button");
    button.append(
      element("span", `rm-risk-mark rm-risk-mark--${row.tone}`),
      element("span", "rm-risk-field", row.field),
      element("span", "rm-risk-value", row.value),
    );
    button.addEventListener("click", () => selectRow(row));
    riskCell.append(button);
    tableRow.append(riskCell);

    const rowCompanyIds = new Set(row.companyIds);
    for (const company of model.companies) {
      const cell = element("td", "rm-cell");
      if (rowCompanyIds.has(company.id)) {
        const hit = element("span", `rm-hit rm-hit--${row.tone}`, "命中");
        hit.setAttribute("aria-label", `${company.name}命中当前风险`);
        testId(hit, "risk-hit");
        cell.append(hit);
      } else {
        const empty = element("span", "rm-cell__empty", "—");
        empty.setAttribute("aria-label", `${company.name}未涉及当前风险`);
        cell.append(empty);
      }
      tableRow.append(cell);
    }

    rowNodes.set(row.id, tableRow);
    buttons.set(row.id, button);
    body.append(tableRow);
  }

  table.append(head, body);
  scroll.append(table);
  shell.append(scroll);
  selectRow(initialRow);
  return shell;
}

function buildClearResult(result: ScanResult): HTMLElement {
  const clear = element("section", "rm-clear");
  testId(clear, "risk-clear");
  clear.append(
    element("h1", "rm-clear__title", "未发现需关注的跨投标人风险"),
    element("p", "rm-clear__meta", riskMeta(result)),
  );
  return clear;
}

function buildContextError(result: ScanResult): HTMLElement {
  const error = element("section", "rm-context-error");
  testId(error, "risk-context-error");
  error.append(
    element("p", "rm-eyebrow", "风险报告 · 数据不完整"),
    element("h1", "rm-context-error__title", "风险关系缺少可显示的投标人信息"),
    element("p", "rm-context-error__meta", riskMeta(result)),
    element("p", "rm-context-error__help", "请进入元数据明细检查风险来源。"),
  );
  return error;
}
```

然后将 `renderResult()` 主体替换为：

```ts
export function renderResult(result: ScanResult): HTMLElement {
  const main = element("div", "main-scroll report-scroll");
  testId(main, "result-page");
  const wrap = element("div", "rm-wrap");
  const model = buildRiskMatrixModel(result);
  const firstRow = model.rows[0];

  if (firstRow === undefined) {
    wrap.classList.add("rm-wrap--empty");
    wrap.append(buildClearResult(result));
    main.append(wrap);
    return main;
  }

  if (model.missingBidderContext) {
    wrap.classList.add("rm-wrap--empty");
    wrap.append(buildContextError(result));
    main.append(wrap);
    return main;
  }

  const header = element("header", "rm-header");
  const summary = element(
    "h1",
    "rm-summary",
    `${model.rows.length} 项风险涉及 ${model.companies.length} 家公司`,
  );
  testId(summary, "risk-summary");
  header.append(
    element("p", "rm-eyebrow", "风险报告 · 仅显示异常项"),
    summary,
    element("p", "rm-meta", riskMeta(result)),
    buildRiskBadges(model),
  );

  const panel = buildEvidencePanel(firstRow);
  const content = element("div", "rm-layout");
  content.append(buildMatrix(model, panel, firstRow), panel);
  wrap.append(header, content, reportSignature(result));
  main.append(wrap);
  return main;
}
```

- [ ] **Step 4: 用 `.rm-*` 作用域样式替换旧结果页样式块**

在 `desktop/src/renderer/styles.css` 中，从 `Card flow report layout` 注释开始到 `.r-sign` 样式结束，只替换结果页相关选择器为：

```css
/* ════════════════════════════════════════════════════════════════
   Risk matrix report
   ════════════════════════════════════════════════════════════════ */

.main-scroll {
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
}

.report-scroll {
  position: relative;
  overflow-x: hidden;
  background:
    linear-gradient(180deg, #f4f8ff 0, #fff 190px),
    #fff;
}

.rm-wrap {
  width: min(100%, 1380px);
  min-height: 100%;
  margin: 0 auto;
  padding: 32px 32px 28px;
}

.rm-wrap--empty {
  display: grid;
  min-height: 100%;
  place-items: center;
}

.rm-header {
  margin-bottom: 22px;
}

.rm-eyebrow {
  margin-bottom: 6px;
  color: var(--blue);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.rm-summary,
.rm-clear__title,
.rm-context-error__title {
  color: var(--text);
  font-size: clamp(26px, 2.4vw, 36px);
  font-weight: 750;
  letter-spacing: -0.025em;
  line-height: 1.2;
}

.rm-meta,
.rm-clear__meta,
.rm-context-error__meta {
  margin-top: 8px;
  color: var(--text-3);
  font-size: 12px;
}

.rm-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.rm-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.rm-badge--danger {
  color: var(--red);
  background: var(--red-light);
}

.rm-badge--caution {
  color: var(--orange);
  background: var(--orange-light);
}

.rm-hidden-note {
  color: var(--text-3);
  font-size: 12px;
}

.rm-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 282px;
  align-items: start;
  gap: 18px;
  min-width: 0;
}

.rm-matrix-shell {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
}

.rm-matrix-scroll {
  max-width: 100%;
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

.rm-table {
  width: 100%;
  min-width: max-content;
  border-spacing: 0;
  border-collapse: separate;
  table-layout: fixed;
}

.rm-table th,
.rm-table td {
  border-right: 1px solid var(--border-soft);
  border-bottom: 1px solid var(--border-soft);
}

.rm-table tr > :last-child {
  border-right: 0;
}

.rm-table tbody tr:last-child > * {
  border-bottom: 0;
}

.rm-table thead th {
  height: 64px;
  padding: 10px 12px;
  color: var(--text-2);
  background: #fafbfe;
  font-size: 12px;
  font-weight: 700;
  text-align: center;
}

.rm-risk-col {
  position: sticky;
  left: 0;
  z-index: 2;
  width: 300px;
  min-width: 300px;
  max-width: 300px;
  background: var(--surface);
  text-align: left;
}

.rm-risk-col--head {
  z-index: 4;
  color: var(--text) !important;
  text-align: left !important;
}

.rm-company-head {
  width: 150px;
  min-width: 150px;
  max-width: 150px;
}

.rm-company-head__text {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: normal;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.rm-row[data-selected="true"] > * {
  background: #f4f8ff;
}

.rm-risk-button {
  display: grid;
  grid-template-columns: 4px minmax(72px, auto) minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 58px;
  padding: 10px 14px;
  border: 0;
  border-radius: 0;
  color: var(--text);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.rm-risk-button:hover {
  background: rgba(3, 78, 214, 0.045);
}

.rm-risk-button:focus-visible {
  position: relative;
  z-index: 5;
  outline: 2px solid var(--blue);
  outline-offset: -3px;
}

.rm-risk-mark {
  align-self: stretch;
  min-height: 30px;
  border-radius: 99px;
}

.rm-risk-mark--danger {
  background: var(--red);
}

.rm-risk-mark--caution {
  background: var(--orange);
}

.rm-risk-field {
  font-size: 12px;
  font-weight: 700;
}

.rm-risk-value {
  min-width: 0;
  overflow: hidden;
  font-family: var(--mono);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rm-cell {
  width: 150px;
  min-width: 150px;
  height: 58px;
  padding: 10px;
  background: var(--surface);
  text-align: center;
  vertical-align: middle;
}

.rm-hit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  min-height: 28px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 750;
}

.rm-hit--danger {
  color: var(--red);
  background: var(--red-light);
}

.rm-hit--caution {
  color: var(--orange);
  background: var(--orange-light);
}

.rm-cell__empty {
  color: var(--text-3);
  font-family: var(--mono);
}

.rm-evidence {
  position: sticky;
  top: 18px;
  overflow: hidden;
  min-width: 0;
  padding: 20px;
  border-radius: 14px;
  color: #fff;
  background: #0e1226;
  box-shadow: 0 18px 42px rgba(14, 18, 38, 0.22);
}

.rm-evidence__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.rm-evidence__tone {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  padding: 4px 9px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 750;
}

.rm-evidence__tone--danger {
  color: #ffd4d5;
  background: rgba(201, 52, 56, 0.28);
}

.rm-evidence__tone--caution {
  color: #ffe0b3;
  background: rgba(168, 92, 0, 0.32);
}

.rm-evidence__count {
  color: #aeb7cf;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.rm-evidence__title {
  margin-top: 18px;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
}

.rm-evidence__value {
  margin-top: 7px;
  overflow-wrap: anywhere;
  color: #d9e5ff;
  font-family: var(--mono);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  line-height: 1.55;
}

.rm-evidence__groups {
  display: grid;
  gap: 12px;
  margin-top: 22px;
}

.rm-evidence__company {
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.11);
}

.rm-evidence__company-name {
  overflow: hidden;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rm-evidence__files {
  display: grid;
  gap: 6px;
  margin-top: 8px;
  list-style: none;
}

.rm-evidence__file {
  position: relative;
  padding-left: 14px;
  overflow-wrap: anywhere;
  color: #aeb7cf;
  font-family: var(--mono);
  font-size: 10.5px;
  line-height: 1.5;
}

.rm-evidence__file::before {
  position: absolute;
  top: 0.62em;
  left: 1px;
  width: 5px;
  height: 5px;
  border-radius: 1px;
  background: #6fa0ff;
  content: "";
}

.rm-evidence__empty,
.rm-context-error__help {
  color: #aeb7cf;
  font-size: 12px;
  line-height: 1.6;
}

.rm-clear,
.rm-context-error {
  width: min(100%, 680px);
  padding: 48px 28px;
  text-align: center;
}

.rm-clear__title {
  color: var(--text);
}

.rm-context-error__title {
  color: var(--red);
}

.rm-context-error__help {
  margin-top: 18px;
  color: var(--text-2);
}

.r-sign {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 32px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  color: var(--text-2);
  font-size: 11px;
}

@media (max-width: 1150px) {
  .rm-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .rm-evidence {
    position: static;
  }

  .rm-evidence__groups {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .rm-wrap {
    padding: 24px 16px;
  }

  .rm-evidence__groups {
    grid-template-columns: minmax(0, 1fr);
  }

  .r-sign {
    flex-direction: column;
  }
}

```

- [ ] **Step 5: 格式化本任务改过的文件**

Run:

```bash
cd desktop
pnpm exec biome format --write src/renderer/render-result.ts src/renderer/styles.css tests/render-result.test.ts
uv run ruff format tests/e2e/risk_matrix_renderer.py
```

Expected: 只格式化列出的四个文件，不触碰其他脏文件。

- [ ] **Step 6: 运行单元测试与浏览器验收，确认转绿**

Run:

```bash
cd desktop
pnpm exec vitest run tests/render-result.test.ts
uv run --with playwright==1.62.0 python tests/e2e/risk_matrix_renderer.py
```

Expected:

- Vitest 全部 PASS。
- Playwright 依次生成 `01-risk-matrix-1440.png`、`02-risk-matrix-1280.png`、`03-risk-matrix-1024.png`、`04-risk-clear.png`。
- 1440/1280 下矩阵和证据面板并排，1024 下证据面板位于矩阵下方。
- 初始三家公司、三条风险、七个“命中”单元格；“无异常公司”不可见。
- 八家公司时只有矩阵容器横向滚动，第一列位置不变。
- 无风险时只有“未发现需关注的跨投标人风险”和目录/时间元信息，不出现正常项标签。
- 控制台与 page error 列表为空。

- [ ] **Step 7: 人工检查四张响应式截图**

打开 Playwright 输出目录中的四张 PNG，逐张确认：

```text
1440×900：结论、矩阵、282px 深色证据面板同屏；矩阵浅色区域无投影。
1280×800：公司表头不截断到不可辨识；证据面板仍在右侧；页面无横向滚动条。
1024×720：矩阵先出现，证据面板完整落在其下；风险第一列不少于 300px。
无风险态：页面中央只有结论和目录/核验时间，没有绿色通过标签或无异常公司名。
```

若任一项不满足，只调整 `.rm-*` 选择器后重新执行 Step 5–7；不得借机改顶栏、状态栏、目录选择或元数据页。

- [ ] **Step 8: 做任务级安全检查点**

Run:

```bash
git diff --check -- desktop/src/renderer/render-result.ts desktop/src/renderer/styles.css desktop/tests/render-result.test.ts desktop/tests/e2e/risk_matrix_renderer.py
git diff --stat -- desktop/src/renderer/render-result.ts desktop/src/renderer/styles.css desktop/tests/render-result.test.ts desktop/tests/e2e/risk_matrix_renderer.py
git status --short
```

Expected: 无 whitespace error；新 E2E 文件可明确识别，两个重叠源码文件仍保留用户既有差异。本任务不暂存或提交重叠文件。

---

### Task 3: 迁移真实数据 E2E 到新结果页合同

**Files:**

- Modify: `desktop/tests/e2e/renderer_real_data.py`

**Interfaces:**

- Consumes: Task 2 的 `risk-matrix`、`risk-row`、`risk-row-button`、`risk-evidence-panel`、`risk-clear`、`risk-context-error` 测试 ID。
- Produces: `pnpm verify:real` 可继续验证真实运行时、停止/重启扫描和新版结果页，不再依赖已删除的投标人卡片、SVG 连线或解析器展开行。

- [ ] **Step 1: 保留真实目录流程，替换旧结果页断言**

在 `desktop/tests/e2e/renderer_real_data.py`：

1. 删除 `EXPECTED_PARSER_RUN_COUNT`。
2. 保留 `EXPECTED_BIDDER_COUNT = 2`、选择目录、文件数、停止扫描、重新开始和截图逻辑；把存在于顶栏和工作区的重复 test ID 收窄到唯一可见操作，使用以下代码替换第一次选择到第二次开始扫描的操作段：

```python
        page.get_by_role("button", name="选择文件夹", exact=True).click()
        selected_folder = page.get_by_test_id("selected-folder")
        selected_folder.wait_for()
        _require(
            condition=page.get_by_test_id("bidder-count").inner_text() == "2",
            message="bidder count",
        )
        _require(
            condition=page.get_by_test_id("file-count").inner_text() == "8",
            message="file count",
        )
        page.screenshot(path=screenshot_dir / "01-selection.png", full_page=True)

        selected_folder.get_by_test_id("start-scan").click()
        page.get_by_role("button", name="停止核验", exact=True).wait_for()
        page.get_by_role("button", name="停止核验", exact=True).click()
        selected_folder.get_by_text(
            "核验已停止，可以重新开始",
            exact=True,
        ).wait_for()
        selected_folder.get_by_test_id("start-scan").wait_for()
```

3. 紧接该段，用 `selected_folder.get_by_test_id("start-scan").click()` 发起第二次扫描，然后把旧 `bidder-card`、`summary-complete`、`trace-danger`、`trace-neutral`、`bidder-connection`、`.document-summary-row`、`.parser-run-row` 断言替换为：

```python
        selected_folder.get_by_test_id("start-scan").click()
        page.get_by_test_id("result-page").wait_for(timeout=15_000)
        matrix_count = page.get_by_test_id("risk-matrix").count()
        clear_count = page.get_by_test_id("risk-clear").count()
        context_error_count = page.get_by_test_id("risk-context-error").count()
        _require(
            condition=context_error_count == 0,
            message="adapted real data must retain bidder context",
        )
        _require(
            condition=matrix_count + clear_count == 1,
            message="exactly one normal result state",
        )
        _require(
            condition=page.locator(".rm-row--danger").count() == 0,
            message="the public fixture has no high-risk person trace",
        )

        if matrix_count == 1:
            _require(
                condition=page.get_by_test_id("risk-row").count() >= 1,
                message="at least one reviewable risk row",
            )
            _require(
                condition=page.get_by_test_id("risk-company-header").count()
                == EXPECTED_BIDDER_COUNT,
                message="involved bidder columns",
            )
            first_button = page.get_by_test_id("risk-row-button").first
            _require(
                condition=first_button.evaluate("element => element.tagName") == "BUTTON",
                message="native risk button",
            )
            first_button.press("Enter")
            page.get_by_test_id("risk-evidence-panel").wait_for()
        elif clear_count == 1:
            _require(
                condition="未发现需关注的跨投标人风险"
                in page.get_by_test_id("risk-clear").inner_text(),
                message="minimal no-risk conclusion",
            )

        result_text = page.get_by_test_id("result-page").inner_text()
        for forbidden in [
            "公司名无重复",
            "作者无重复",
            "模板无重复",
            "未发现跨投标人人员痕迹",
        ]:
            _require(
                condition=forbidden not in result_text,
                message=f"legacy safe content leaked: {forbidden}",
            )
        page.screenshot(path=screenshot_dir / "02-result.png", full_page=True)
```

这里允许真实公共数据走“矩阵”或“极简无风险”分支，因为外部固定报告可能没有待复核项；同时明确要求 `risk-context-error` 不出现，因为正常适配器数据必须保留完整 bidder 上下文。

- [ ] **Step 2: 格式化并静态检查两个 Python E2E 文件**

Run:

```bash
cd desktop
uv run ruff format tests/e2e/renderer_real_data.py tests/e2e/risk_matrix_renderer.py
uv run ruff check tests/e2e/renderer_real_data.py tests/e2e/risk_matrix_renderer.py
```

Expected: 两个文件均无 Ruff 错误。

- [ ] **Step 3: 运行不依赖外部固定数据的浏览器回归**

Run:

```bash
cd desktop
uv run --with playwright==1.62.0 python tests/e2e/risk_matrix_renderer.py
```

Expected: PASS；四张截图重新生成，Vite 子进程正常结束。

- [ ] **Step 4: 在已有真实运行时参数可用时验证兼容入口**

先只读检查当前 shell 是否已提供三项真实资源：

```bash
test -n "${DOCMETA_REAL_FOLDER:-}" && test -n "${DOCMETA_REAL_REPORT:-}" && test -n "${DOCMETA_REAL_RUNTIME:-}"
```

若命令返回 0，执行：

```bash
cd desktop
pnpm verify:real -- \
  --folder "$DOCMETA_REAL_FOLDER" \
  --report "$DOCMETA_REAL_REPORT" \
  --runtime "$DOCMETA_REAL_RUNTIME" \
  --port 4176
```

Expected: `Real runtime and renderer verification passed`。若三项环境变量未提供，记录“真实外部样本未配置”，以 Step 3 的完全自包含回归作为本次 UI 交付的浏览器证据；不得猜测路径或下载新样本。

- [ ] **Step 5: 做任务级安全检查点**

Run:

```bash
git diff --check -- desktop/tests/e2e/renderer_real_data.py desktop/tests/e2e/risk_matrix_renderer.py
git diff --stat -- desktop/tests/e2e/renderer_real_data.py desktop/tests/e2e/risk_matrix_renderer.py
git status --short
```

Expected: 无 whitespace error；只显示预期 E2E 差异和工作区原有状态。继续不暂存用户既有修改。

---

### Task 4: 全量验证与交付审计

**Files:**

- Verify only: `desktop/` 全部 TypeScript/CSS/测试与构建配置。
- Verify only: 仓库 Python 核心、锁文件、构建与 Java Worker。
- Review: 本计划 File Map 中的五个文件。

**Interfaces:**

- Consumes: Tasks 1–3 的最终源码、测试与截图。
- Produces: 可复核的命令输出、范围受控的最终 diff 和明确的未运行项说明；不产生新的产品功能。

- [ ] **Step 1: 运行桌面端完整验证链**

Run:

```bash
cd desktop
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
```

Expected: 五条命令全部 exit 0。若 `pnpm lint` 或 `pnpm format:check` 报告任务范围外的既有脏文件，只记录其文件与错误，不批量改写；任务范围内错误必须修复并重跑对应命令。

- [ ] **Step 2: 重新运行风险矩阵浏览器验收并保留最终截图**

Run:

```bash
cd desktop
DOCMETA_SCREENSHOT_DIR="${TMPDIR:-/tmp}/docmeta-risk-matrix-final" \
  uv run --with playwright==1.62.0 python tests/e2e/risk_matrix_renderer.py
```

Expected: exit 0，最终截图位于 `${TMPDIR:-/tmp}/docmeta-risk-matrix-final/`，不在仓库内产生截图或测试结果文件。

- [ ] **Step 3: 运行仓库规定的 Python 交付检查**

Run from repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
uv run docmeta verify
```

Expected: 七条命令全部 exit 0；本次 UI 改动不改变 Python 公共模型、错误码、序列化或运行时验证结果。

- [ ] **Step 4: 使用 Java 21 验证 Java Worker**

Run:

```bash
cd java-worker
./mvnw --batch-mode --no-transfer-progress verify
```

Expected: Maven `BUILD SUCCESS`。若当前 `JAVA_HOME` 不是 Java 21，先用本机已安装的 Java 21 运行该命令；不得修改项目配置来绕过版本要求。

- [ ] **Step 5: 审计最终范围、文案和数据泄漏边界**

Run from repository root:

```bash
git diff --check -- \
  desktop/src/renderer/render-result.ts \
  desktop/src/renderer/styles.css \
  desktop/tests/render-result.test.ts \
  desktop/tests/e2e/risk_matrix_renderer.py \
  desktop/tests/e2e/renderer_real_data.py
git diff --name-only
git status --short
rg -n "公司名无重复|作者无重复|模板无重复|未发现跨投标人人员痕迹|bidder-card|bidder-connection|trace-neutral" \
  desktop/src/renderer/render-result.ts \
  desktop/tests/e2e/renderer_real_data.py \
  desktop/tests/e2e/risk_matrix_renderer.py
```

Expected:

- `git diff --check` 无输出。
- `git diff --name-only` 中本任务只新增/修改 File Map 的五个文件；其他文件若存在，是进入任务前已有的用户改动，保持原样。
- `rg` 无匹配；新结果页和新 E2E 不再包含旧正常项文案或旧结构选择器。
- `render-result.ts` 不输出无法映射的 `documentId`、绝对路径、正文或原始异常。
- 未修改 `desktop/src/shared/contracts.ts`、`desktop/src/main/report-adapter.ts`、`desktop/src/renderer/state.ts` 或任何 Python/Java产品代码。

- [ ] **Step 6: 对照设计规格做最终人工验收**

逐项确认并在交付说明中报告：

```text
首屏结论：风险项总数与涉险公司总数一眼可见。
风险顺序：高风险在前、待复核在后，等级内顺序稳定。
公司范围：只显示命中风险的 bidder，根目录组与未涉险公司完全隐藏。
矩阵语义：命中使用文字与语义色；未命中只显示中性破折号，不称为安全。
证据联动：默认第一条高风险；键盘/点击可切换；文件按公司分组；缺失映射不泄漏 ID。
无风险态：只显示“未发现需关注的跨投标人风险”和目录/时间。
不一致态：显示“风险关系缺少可显示的投标人信息”，不伪装为无风险。
响应式：1440×900、1280×800、1024×720 页面无横向溢出；1024 证据面板在矩阵下方。
视觉规范：矩阵无投影，深色证据面板是唯一投影区域，颜色与设计 token 一致。
范围控制：未改风险算法、共享合同、状态机、IPC、后端或元数据明细页。
```

- [ ] **Step 7: 交付而不误提交用户现有改动**

Run:

```bash
git status --short
git diff --stat -- \
  desktop/src/renderer/render-result.ts \
  desktop/src/renderer/styles.css \
  desktop/tests/render-result.test.ts \
  desktop/tests/e2e/risk_matrix_renderer.py \
  desktop/tests/e2e/renderer_real_data.py
```

Expected: 向用户交付测试结果、最终截图路径、五个任务文件和真实外部样本是否运行的说明。由于两个核心源码文件与用户进入任务前的未提交改动重叠，不自动执行 `git add`、`git commit` 或 `git push`；只有用户明确要求并确认提交范围后，才准备可审查的提交。

---

## Completion Criteria

- `buildRiskMatrixModel()` 的单元测试覆盖排序、公司有序并集、未涉险/根目录过滤、精确 group ID 命中、证据分组、缺失映射与空 trace。
- 结果页只呈现风险矩阵、当前风险证据、必要报告元信息和签名；不呈现统计卡片、时间轴、正常项标签或未涉险公司。
- 浏览器测试验证默认高风险、键盘切换、证据联动、三种正式尺寸、大量公司局部滚动、第一列粘性、reduced-motion 和极简无风险态。
- 真实数据 E2E 不再依赖旧的卡片、SVG 连线和解析器展开结构。
- 桌面端测试、类型检查、Lint、格式检查、构建以及仓库规定的 Python/Java 验证全部通过，或对无法运行的外部真实样本入口给出准确的环境说明。
- 最终 diff 保留用户进入任务前的所有未提交改动，且没有将它们误暂存或误提交。

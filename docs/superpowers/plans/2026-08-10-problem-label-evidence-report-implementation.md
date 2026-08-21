# 问题标签证据清单结果页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前结果页的“风险矩阵 + 证据侧栏”替换为固定 11 类问题标签的统一纵向证据清单，让有风险标签完整展示“命中值 → 公司组合 → 双方文件”，无风险标签使用相同卡片并明确写“无风险”。

**Architecture:** 在现有 `ScanResult` 之上建立纯视图模型 `buildProblemLabelReportModel()`，集中完成固定标签顺序、多字段 trace 复用、命中值合并、无向公司组合与双方文件归属。`renderResult()` 只消费该模型创建静态、无需点击即可完整阅读的 DOM；Python 比较器、报告 JSON、Electron IPC 和其他页面保持不变。

**Tech Stack:** TypeScript 7、原生 DOM API、CSS Grid、Vitest 4、Vite 8、Python 3.12、Playwright 1.62、pnpm 11。

## Global Constraints

- 事实规格是 `docs/superpowers/specs/2026-08-10-problem-label-evidence-report-design.md`。
- 固定显示 11 个标签，顺序为创建人、修改人、批注人、修订人、经理、公司、签名人、路径用户名、模板、创建时间、修改时间。
- 每个标题必须带“检测”后缀，例如“问题标签：创建人检测”。
- 页面不使用问题标签 Tab、矩阵、深色证据侧栏、折叠面板或点击联动。
- 有风险和无风险使用同一种全宽纵向卡片；有风险展开全部证据，无风险显示“0 个命中值 · 0 组公司关系”和“无风险”。
- 多字段 trace 同时进入每一个支持的问题标签；`author + last_modified_by` 必须同时出现在创建人检测和修改人检测。
- 公司和文档顺序遵循 `ScanResult.groups`；公司组合是稳定、不重复的无向两两组合。
- 不显示绝对路径、内部 document ID、正文、批注正文或原始异常。
- 不修改 `TraceSummary`、`ScanResult`、报告 JSON、Electron IPC、Python 比较器或 Java worker。
- 不新增运行时依赖、UI 框架、图表库、远程资源或运行时下载。
- 当前 `desktop/src/renderer/render-result.ts`、`desktop/src/renderer/styles.css` 和相关测试包含用户的未提交改动。只做局部补丁，不回滚其他差异；未经用户明确授权，不把这些重叠文件加入提交。
- 每个任务以聚焦测试、`git diff --check` 和可读差异作为安全检查点。

---

## File Map

- Modify: `desktop/src/renderer/render-result.ts`
  - 用纯问题标签模型替换矩阵模型。
  - 用统一纵向卡片替换矩阵和联动证据侧栏 DOM。
  - 保留字段翻译、时间格式、报告签名与 `connectionTracks()`。
- Modify: `desktop/src/renderer/styles.css`
  - 把当前 `.rm-*` 结果页样式替换为 `.pl-*` 问题标签清单样式。
  - 保留顶栏、目录选择、扫描和元数据明细样式。
- Modify: `desktop/tests/render-result.test.ts`
  - 用纯问题标签模型测试替换矩阵模型测试。
  - 保留 `connectionTracks()` 回归测试。
- Move/Modify: `desktop/tests/e2e/risk_matrix_renderer.py` → `desktop/tests/e2e/problem_label_renderer.py`
  - 把合成浏览器验收迁移到 11 标签清单、证据层级和响应式截图。
- Modify: `desktop/tests/e2e/renderer_real_data.py`
  - 把矩阵/极简无风险状态断言迁移到固定 11 标签页面。
- Modify: `desktop/tests/real-runtime.integration.test.ts`
  - 更新浏览器脚本文件名及输出标识。

## Task 1: 用失败测试锁定固定 11 标签视图模型

**Files:**

- Modify: `desktop/tests/render-result.test.ts`
- Test: `desktop/tests/render-result.test.ts`

**Interfaces:**

- Consumes: existing `ScanResult`, `TraceSummary`, `ResultGroup`, `DocumentSummary` fixtures.
- Produces test contract for `buildProblemLabelReportModel(result: ScanResult): ProblemLabelReportModel`.

- [ ] **Step 1: 把矩阵 import 改为问题标签模型 import**

```ts
import {
  buildProblemLabelReportModel,
  connectionTracks,
} from "../src/renderer/render-result";
```

- [ ] **Step 2: 写出固定标签、多字段复用和公司组合的失败测试**

测试数据使用四个 bidder 组和一个 root-files 组：

```ts
const result = scanResult({
  groups: [
    group("root", "根目录文件", [document("root-doc", "说明.docx")], "root-files"),
    group("a", "公司 A", [document("a-1", "投标函.docx")]),
    group("b", "公司 B", [document("b-1", "报价清单.xlsx")]),
    group("c", "公司 C", [document("c-1", "技术标.pdf")]),
    group("safe", "无异常公司", [document("safe-1", "附件.docx")]),
  ],
  personTraces: [
    {
      ...trace("person", "danger", ["a", "b", "c"]),
      value: "李建国",
      fieldNames: ["author", "last_modified_by"],
      documentIds: ["a-1", "b-1", "c-1", "a-1", "missing-id"],
    },
  ],
});
```

断言：

```ts
const model = buildProblemLabelReportModel(result);

expect(model.sections).toHaveLength(11);
expect(model.sections.map((section) => section.label)).toEqual([
  "创建人检测",
  "修改人检测",
  "批注人检测",
  "修订人检测",
  "经理检测",
  "公司检测",
  "签名人检测",
  "路径用户名检测",
  "模板检测",
  "创建时间检测",
  "修改时间检测",
]);
expect(model.riskCount).toBe(2);
expect(model.safeCount).toBe(9);
expect(model.sections[0]?.hits[0]).toMatchObject({
  value: "李建国",
  relationCount: 3,
  pairs: [
    {
      left: { company: "公司 A", files: ["投标函.docx"] },
      right: { company: "公司 B", files: ["报价清单.xlsx"] },
    },
    {
      left: { company: "公司 A", files: ["投标函.docx"] },
      right: { company: "公司 C", files: ["技术标.pdf"] },
    },
    {
      left: { company: "公司 B", files: ["报价清单.xlsx"] },
      right: { company: "公司 C", files: ["技术标.pdf"] },
    },
  ],
});
expect(model.sections[1]?.hits).toEqual(model.sections[0]?.hits);
expect(model.sections[2]).toMatchObject({
  label: "批注人检测",
  status: "safe",
  hits: [],
  relationCount: 0,
});
expect(JSON.stringify(model)).not.toContain("missing-id");
expect(JSON.stringify(model)).not.toContain("说明.docx");
expect(JSON.stringify(model)).not.toContain("附件.docx");
```

- [ ] **Step 3: 写出别名、同值合并和缺失证据的失败测试**

增加三个断言场景：

1. `annotation_author` 进入批注人检测。
2. `signature_signer_name` 进入签名人检测。
3. 有 trace 但公司文件无法映射时，section 仍是 `risk`，hit 的 `missingEvidence` 为 `true`，序列化模型不包含内部 ID。

- [ ] **Step 4: 运行测试确认先红**

Run:

```bash
cd desktop
pnpm exec vitest run tests/render-result.test.ts
```

Expected: FAIL because `buildProblemLabelReportModel` is not exported; existing `connectionTracks` test remains green.

## Task 2: 实现纯问题标签视图模型

**Files:**

- Modify: `desktop/src/renderer/render-result.ts`
- Test: `desktop/tests/render-result.test.ts`

**Interfaces:**

- Consumes: `ScanResult`, `TraceSummary`, `buildGroupNames(result)`.
- Produces:

```ts
export type ProblemLabelStatus = "risk" | "safe";

export interface ProblemPairSide {
  companyId: string;
  company: string;
  files: string[];
}

export interface ProblemCompanyPair {
  id: string;
  left: ProblemPairSide;
  right: ProblemPairSide;
}

export interface ProblemHitValue {
  value: string;
  pairs: ProblemCompanyPair[];
  relationCount: number;
  missingEvidence: boolean;
}

export interface ProblemLabelSection {
  key: string;
  label: string;
  status: ProblemLabelStatus;
  hits: ProblemHitValue[];
  relationCount: number;
}

export interface ProblemLabelReportModel {
  sections: ProblemLabelSection[];
  riskCount: number;
  safeCount: number;
  relationCount: number;
}

export function buildProblemLabelReportModel(
  result: ScanResult,
): ProblemLabelReportModel;
```

- [ ] **Step 1: 定义固定标签配置与字段别名**

在 `traceFieldLabel()` 后定义 11 项只读配置，并提供 `problemLabelKey(raw: string): string | undefined`：

```ts
const PROBLEM_LABEL_DEFINITIONS = [
  { key: "author", label: "创建人检测" },
  { key: "last_modified_by", label: "修改人检测" },
  { key: "comment_author", label: "批注人检测" },
  { key: "revision_author", label: "修订人检测" },
  { key: "manager", label: "经理检测" },
  { key: "company", label: "公司检测" },
  { key: "signer_identity", label: "签名人检测" },
  { key: "username_path_trace", label: "路径用户名检测" },
  { key: "template", label: "模板检测" },
  { key: "created_at", label: "创建时间检测" },
  { key: "modified_at", label: "修改时间检测" },
] as const;

const PROBLEM_LABEL_ALIASES: Readonly<Record<string, string>> = {
  annotation_author: "comment_author",
  signature_signer_name: "signer_identity",
};
```

- [ ] **Step 2: 建立 bidder 与文档索引**

只索引 `kind === "bidder"` 的组。文档索引值为 `{ companyId, company, file, order }`，并严格保持 `result.groups` 与组内 `documents` 的顺序。

- [ ] **Step 3: 为每个 trace 建立稳定公司组合**

对 `trace.groupIds` 与 bidder 索引取交集，按 bidder 原始顺序生成所有 `i < j` 的组合。每一侧文件来自当前 `trace.documentIds` 与文档索引的精确交集；去重后保留组内顺序。无法形成组合时设置 `missingEvidence: true`，但保留风险 hit。

- [ ] **Step 4: 把 trace 复用到每个支持字段并按值合并**

对 `trace.fieldNames` 先归一化别名、去重，再将同一 trace 追加到每个字段对应 section。相同 section、相同 `trace.value` 合并 pair；相同 pair 合并双方文件且保持首次出现顺序。

- [ ] **Step 5: 返回全部 11 section 与汇总**

无 hit 的 section 返回 `status: "safe"`；有 hit 返回 `status: "risk"`。`riskCount + safeCount === 11`，`relationCount` 为所有风险 section 的展示关系数量之和。

- [ ] **Step 6: 运行聚焦测试确认转绿**

Run:

```bash
cd desktop
pnpm exec vitest run tests/render-result.test.ts
pnpm typecheck
```

Expected: all focused tests pass and TypeScript reports no errors.

- [ ] **Step 7: 检查安全差异**

Run:

```bash
git diff --check -- desktop/src/renderer/render-result.ts desktop/tests/render-result.test.ts
```

Expected: no output. Do not stage these pre-existing dirty files.

## Task 3: 用统一纵向卡片渲染结果页

**Files:**

- Modify: `desktop/src/renderer/render-result.ts`
- Test: `desktop/tests/render-result.test.ts`

**Interfaces:**

- Consumes: `ProblemLabelReportModel`, `ProblemLabelSection`, `ProblemHitValue`, `ProblemCompanyPair`.
- Produces DOM test IDs:
  - `problem-label-summary`
  - `problem-label-section`
  - `problem-label-name`
  - `problem-label-status`
  - `problem-hit-value`
  - `problem-company-pair`
  - `problem-company-files`
  - `problem-evidence-file`
  - `problem-safe-result`

- [ ] **Step 1: 删除结果页矩阵和联动侧栏构建函数**

移除 `buildRiskBadges()`、`updateEvidencePanel()`、`buildEvidencePanel()`、`buildMatrix()`、`buildClearResult()` 和矩阵专用类型；保留报告时间、签名、`connectionTracks()` 与新纯模型。

- [ ] **Step 2: 实现文件侧和公司组合 DOM**

`buildProblemPair(pair)` 创建三列：公司组合、左公司文件、右公司文件。每个文件使用 `problem-evidence-file`，空文件侧显示“暂无可显示文件证据”。

- [ ] **Step 3: 实现命中值 DOM**

`buildProblemHit(hit)` 先渲染“命中值 + 原始值 + N 组公司关系”，再顺序追加全部公司组合；`missingEvidence` 且无 pair 时显示“风险关系缺少可显示的投标人文件证据”。

- [ ] **Step 4: 实现统一 section DOM**

`buildProblemSection(section)` 对 risk 与 safe 使用相同 article/header/body：

- risk：红色状态“有风险”，body 追加所有 hit。
- safe：绿色状态“无风险”，body 显示“无风险 · 未发现跨公司相同值”。

- [ ] **Step 5: 重写 `renderResult()`**

页头显示“11 类检查标签”、根目录与时间，并显示“有风险 N”“无风险 M”。之后一次性追加 11 个 section 和既有报告签名。不再存在空结果页特例；零 trace 时仍显示 11 个无风险 section。

- [ ] **Step 6: 运行单元与类型检查**

Run:

```bash
cd desktop
pnpm exec vitest run tests/render-result.test.ts tests/state.test.ts
pnpm typecheck
```

Expected: PASS.

## Task 4: 替换结果页样式并保持响应式

**Files:**

- Modify: `desktop/src/renderer/styles.css`

**Interfaces:**

- Consumes: Task 3 的 `.pl-*` DOM classes.
- Produces: desktop three-column evidence row and narrow stacked evidence row.

- [ ] **Step 1: 把 `.rm-*` 矩阵样式块替换为 `.pl-*` 清单样式**

实现这些视觉职责：

- `.pl-wrap`：结果页最大宽度和留白。
- `.pl-header`：柔光页头、标题和汇总状态。
- `.pl-list`：统一纵向间距。
- `.pl-section`：同一全宽卡片骨架。
- `.pl-section--risk` / `.pl-section--safe`：仅改变左边线和状态弱底。
- `.pl-value-head`：橙色弱底命中值行。
- `.pl-pair-row`：`120px minmax(0, 1fr) minmax(0, 1fr)` 三列。
- `.pl-pair-name`：蓝色弱底公司组合。
- `.pl-file`：白底细边框文件标签。
- `.pl-safe-result`：绿色弱底核验结果。

- [ ] **Step 2: 增加 760px 与 520px 响应式规则**

760px 以下 `.pl-pair-row` 改为单列；520px 以下 section header、value header 和汇总允许纵向排列。不得设置页面级固定宽度或横向滚动。

- [ ] **Step 3: 运行格式与样式差异检查**

Run:

```bash
cd desktop
pnpm exec biome format --write src/renderer/render-result.ts tests/render-result.test.ts
pnpm exec biome format --write src/renderer/styles.css
pnpm lint
git diff --check -- src/renderer/render-result.ts src/renderer/styles.css tests/render-result.test.ts
```

Expected: PASS/no output. Do not stage overlapping files.

## Task 5: 迁移合成浏览器验收与真实运行时断言

**Files:**

- Move/Modify: `desktop/tests/e2e/risk_matrix_renderer.py` → `desktop/tests/e2e/problem_label_renderer.py`
- Modify: `desktop/tests/e2e/renderer_real_data.py`
- Modify: `desktop/tests/real-runtime.integration.test.ts`

**Interfaces:**

- Consumes: Task 3 test IDs and Task 4 layout.
- Produces: deterministic screenshots at 1440×900, 1280×800 and 1024×720.

- [ ] **Step 1: 重命名合成浏览器脚本和临时输出**

使用 `problem_label_renderer.py`、`docmeta-problem-label-preview` 和 `docmeta-problem-label-*` 命名；更新 integration test 启动目标。

- [ ] **Step 2: 构造多字段与多公司报告**

初始 report 至少包含：

- `field_names: ["author", "last_modified_by"]`、值“李建国”、公司 A/B/C。
- `field_names: ["template"]`、值 `Normal.dotm`、公司 A/B。

预期 11 个 section、3 个有风险标签、8 个无风险标签；创建人检测和修改人检测都显示“李建国”。

- [ ] **Step 3: 替换浏览器断言**

验证：

```text
problem-label-section count == 11
problem-label-name contains 创建人检测 and 修改人检测
problem-label-status has 3 有风险 and 8 无风险
创建人检测 contains 李建国 and 3 company pairs
safe section contains 无风险
old risk-matrix and risk-evidence-panel count == 0
documentElement.scrollWidth <= clientWidth
console errors == []
page errors == []
```

- [ ] **Step 4: 更新真实数据脚本**

真实扫描完成后等待 `problem-label-section`，断言恰好 11 个；如果有风险状态，至少一个 section 存在命中值和公司组合；若全无风险，则 11 个状态均为“无风险”。

- [ ] **Step 5: 运行合成浏览器验收**

Run:

```bash
cd desktop
DOCMETA_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  uv run python tests/e2e/problem_label_renderer.py
```

Expected: PASS and screenshots written to `/tmp/docmeta-problem-label-preview/`.

## Task 6: 全量验证与视觉验收

**Files:**

- Verify all modified desktop files.

**Interfaces:**

- Consumes: completed renderer, styles, tests and browser script.
- Produces: buildable desktop frontend and reviewed screenshots.

- [ ] **Step 1: 运行桌面测试、类型、lint、格式和构建**

Run:

```bash
cd desktop
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
```

Expected: all commands exit 0.

- [ ] **Step 2: 运行真实运行时集成测试**

Run:

```bash
cd desktop
pnpm test:real-runtime
```

Expected: PASS, or report a concrete external runtime blocker without weakening assertions.

- [ ] **Step 3: 检查工作树和差异**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; existing unrelated dirty files remain untouched.

- [ ] **Step 4: 逐张检查截图**

检查 1440×900、1280×800、1024×720：

- 11 个标签名称完整。
- 有风险/无风险卡片骨架一致。
- 命中值、公司组合、双方文件层级清楚。
- 没有横向溢出、文字遮挡、卡片截断或旧矩阵残留。

- [ ] **Step 5: 启动本地效果供用户查看**

使用现有 `preview:real` 或 Electron Forge 启动正式 renderer，保留进程并把可访问地址或应用窗口交给用户查看。

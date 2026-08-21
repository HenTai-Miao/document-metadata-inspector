# Element Plus 国资稳健蓝结果页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把正式 Electron 结果页更新为已批准的 Element Plus 标签导航布局与国资稳健蓝主题，同时保持全部业务数据和证据语义不变。

**Architecture:** 保留 `buildProblemLabelReportModel()` 及全部扫描合同，只在 `renderResult()` 的展示构建中增加一个同页标签索引，并重组外层工作区。结果详情仍完整顺序渲染 11 个 section；样式通过现有 `styles.css` 的全局 token、顶栏和 `.pl-*` 作用域完成，不引入 Vue 或 Element Plus 运行时。

**Tech Stack:** Electron 43、TypeScript 7、原生 DOM、Vite 8、Vitest 4、Python Playwright。

## Global Constraints

- 业务内容、数据模型、排序、扫描 IPC、元数据明细和后端均不得修改。
- 固定 11 类问题标签必须同时出现在左侧索引和右侧完整详情中。
- 索引只负责定位，不能隐藏、过滤、折叠或延迟渲染证据。
- 命中值区域使用浅蓝体系，正式页面不得保留黄色/橙色命中值背景。
- 桌面大屏为 238px 索引 + 自适应详情；900px 以下堆叠，560px 以下单列。
- 不新增前端运行时依赖。

---

### Task 1: 先锁定标签索引与完整证据的浏览器契约

**Files:**
- Modify: `desktop/tests/e2e/problem_label_renderer.py`
- Test: `desktop/tests/e2e/problem_label_renderer.py`

**Interfaces:**
- Consumes: 现有合成报告、`problem-label-section`、`problem-label-name`、`problem-label-status` 测试接口。
- Produces: `problem-label-workspace`、`problem-label-nav`、`problem-label-nav-item`、`problem-label-detail` 浏览器契约。

- [ ] **Step 1: 写出失败的结构和主题测试**

在首次扫描后增加以下真实 DOM 断言：

```python
workspace = page.get_by_test_id("problem-label-workspace")
navigation = page.get_by_test_id("problem-label-nav")
detail = page.get_by_test_id("problem-label-detail")
expect(workspace).to_have_count(1)
expect(navigation.get_by_test_id("problem-label-nav-item")).to_have_count(11)
expect(detail.get_by_test_id("problem-label-section")).to_have_count(11)
expect(navigation).to_contain_text("创建人检测")
expect(navigation).to_contain_text("无风险")
```

用 `page.evaluate()` 读取 `.topbar`、`.pl-value-head`、`.pl-pair-name` 的计算背景色，断言顶栏为 `rgb(11, 49, 90)`，命中值栏不再是旧黄色 `rgb(255, 249, 239)`，并继续对每个正式尺寸调用 `_assert_no_page_overflow()`。

- [ ] **Step 2: 运行测试确认因新结构缺失而失败**

Run:

```bash
cd desktop && uv run --with playwright==1.62.0 python tests/e2e/problem_label_renderer.py
```

Expected: FAIL，首个失败明确指出 `problem-label-workspace` 或 `problem-label-nav` 数量为 0，而不是环境或语法错误。

---

### Task 2: 在原生渲染器中加入同页标签索引

**Files:**
- Modify: `desktop/src/renderer/render-result.ts`
- Test: `desktop/tests/e2e/problem_label_renderer.py`

**Interfaces:**
- Consumes: `ProblemLabelReportModel.sections` 的固定顺序、`ProblemLabelSection.status` 和现有 `buildProblemSection()`。
- Produces: `buildProblemNavigation(model)` 及新的结果页工作区 DOM；保留现有详情测试 ID。

- [ ] **Step 1: 为每个详情 section 提供稳定页内目标**

在 `buildProblemSection()` 中使用闭合展示 key 生成 `id="problem-label-${section.key}"`，不把后端原始值写入 id。

- [ ] **Step 2: 实现索引项**

新增纯 DOM 构建函数，为每个 section 渲染一个指向对应 section id 的 `<a>`，显示标签名称与“有风险/无风险”，并添加 `problem-label-nav-item` 测试接口。索引不注册过滤或隐藏事件。

- [ ] **Step 3: 重组结果页外层结构**

让 `renderResult()` 在摘要下构建：

```text
.pl-workspace[data-testid=problem-label-workspace]
  aside.pl-sidebar[data-testid=problem-label-nav]
  div.pl-detail[data-testid=problem-label-detail]
```

`pl-detail` 仍依次追加现有 11 个 `buildProblemSection()` 结果。保留报告签名并放在详情区之后。

- [ ] **Step 4: 运行浏览器测试，允许仅因样式断言继续失败**

Run:

```bash
cd desktop && uv run --with playwright==1.62.0 python tests/e2e/problem_label_renderer.py
```

Expected: 新结构计数通过；顶栏或命中值背景色断言仍失败。

---

### Task 3: 落实国资稳健蓝 token、顶栏和 Element Plus 证据布局

**Files:**
- Modify: `desktop/src/renderer/styles.css`
- Modify: `desktop/src/renderer/main.ts`
- Modify: `desktop/index.html`
- Test: `desktop/tests/e2e/problem_label_renderer.py`

**Interfaces:**
- Consumes: Task 2 的 `.pl-workspace`、`.pl-sidebar`、`.pl-detail` 和现有 `.pl-section*` 结构。
- Produces: 国资深蓝顶栏、238px 标签索引、浅蓝命中值栏、蓝色关系/文件标记和响应式堆叠。

- [ ] **Step 1: 替换全局主题 token**

把主要 token 更新为设计规格中的深蓝、主蓝、浅蓝、灰蓝背景和边框；风险红与安全绿只保留状态语义。更新 favicon 的主色使窗口品牌一致。

- [ ] **Step 2: 更新顶栏和主操作视觉**

顶栏改为 `#0b315a` 实色背景；标题、文件夹和离线状态使用可读的白色层级；主按钮使用 `#174b82` 或浅色反差方案，并保留键盘焦点。

- [ ] **Step 3: 重写 `.pl-*` 结果页布局**

实现 238px + 自适应详情网格，索引浅蓝标题、风险项选中底和状态文字；把 `.pl-value-head` 从旧黄色改为 `#eaf2f9`，`.pl-hit-label`、`.pl-hit-value`、`.pl-pair-name` 和 `.pl-file::before` 统一到蓝色体系。

- [ ] **Step 4: 实现响应式布局**

900px 以下索引置顶并变成两列；560px 以下索引单列、公司关系标题独占一行、双方文件单列。禁止根页面横向溢出。

- [ ] **Step 5: 运行浏览器测试确认转绿**

Run:

```bash
cd desktop && uv run --with playwright==1.62.0 python tests/e2e/problem_label_renderer.py
```

Expected: PASS，并生成风险态、全无风险态和正式尺寸截图。

---

### Task 4: 完整交付验证

**Files:**
- Verify: `desktop/src/renderer/render-result.ts`
- Verify: `desktop/src/renderer/styles.css`
- Verify: `desktop/tests/e2e/problem_label_renderer.py`

**Interfaces:**
- Consumes: 前三项产物。
- Produces: 可构建、可审计、无浏览器错误的正式前端页面。

- [ ] **Step 1: 运行前端自动化测试**

```bash
cd desktop && pnpm test
```

Expected: 0 failed。

- [ ] **Step 2: 运行类型、格式和 lint 检查**

```bash
cd desktop && pnpm typecheck
cd desktop && pnpm format:check
cd desktop && pnpm lint
```

Expected: 每条命令退出码 0。

- [ ] **Step 3: 运行正式构建**

```bash
cd desktop && pnpm build
```

Expected: Vite 构建退出码 0。

- [ ] **Step 4: 复核截图和浏览器错误**

检查浏览器测试生成的 1440、1280、1024、窄屏和全无风险截图，确认左侧索引与右侧详情关系清晰、文件名可读、页面无黄色命中值、无控制台/页面/资源错误。

- [ ] **Step 5: 检查变更范围**

```bash
git diff --check
git status --short
```

Expected: 无空白错误；改动只包含设计规格、实施计划、正式前端渲染/样式及对应测试。

# Product Name and Squirrel First-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前用户可见产品名精确改为“围标串标投标人名称一致检测工具”，修复 Windows Squirrel 安装后首次运行被退出和安装版快捷方式缺失的问题，并重新生成、真实验收 x64 安装版与绿色免安装版。

**Architecture:** 恢复 Electron Forge 官方推荐的 `electron-squirrel-startup@1.0.1`，但不把它作为 packaged app 的 external 运行时模块；Vite 将其直接内嵌到主进程 bundle，以同时获得正确的 Squirrel 生命周期行为和 pnpm 打包兼容性。产品显示名只改当前用户可见边界，内部 `DocumentMetadataInspector` 身份、可执行文件名和发布目录英文契约保持稳定。

**Tech Stack:** Python 3.12/pytest/Ruff/BasedPyright、Electron 43、TypeScript、Vite 8、Vitest、pnpm 11、Electron Forge 7.11、Squirrel.Windows、Windows PowerShell 5.1、Parallels Desktop Windows 11。

## Global Constraints

- 产品名称必须逐字为“围标串标投标人名称一致检测工具”。
- 不得把产品名称改成或拼成“围标串标投标人名称一致检测报告/软件/系统/平台”。
- 保留 `docmeta`、`docmeta-review.exe`、`docmeta-review-desktop`、`DocumentMetadataInspector` 安装目录/注册表/升级身份。
- 内部发布文件继续使用 `DocumentMetadataInspector-<version>-win-x64-*`；只在最终桌面交付副本使用精确中文产品名。
- `electron-squirrel-startup` 固定为 `1.0.1`，并打进 Vite 主进程 bundle；不得作为 packaged runtime external。
- `--squirrel-firstrun` 必须继续普通 GUI 启动；安装/升级/卸载/obsolete 事件按官方模块处理。
- 不更改扫描、报告数据模型、问题标签、离线运行时或历史规格/原型。
- 安装版与应用不得显示 CMD、PowerShell、Java 或 ExifTool 控制台窗口。
- 所有生产变更先有能在当前代码上正确失败的测试；没有 RED 证据不得实施。

---

### Task 1: Add RED product-name behavior coverage

**Files:**
- Modify: `tests/unit/test_html_export.py`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**
- Consumes: existing `export_report(...)` and active desktop/package/installer files.
- Produces: exact-name regression coverage used by Tasks 3 and 4.

- [ ] **Step 1: Add a failing HTML report title assertion**

Extend the existing HTML export test after parsing the generated document:

```python
assert "<title>围标串标投标人名称一致检测工具</title>" in html
assert "<h1>围标串标投标人名称一致检测工具</h1>" in html
assert "Document metadata inspection report" not in html
```

This catches a report exporter that retains the old generic title or invents a product-name suffix.

- [ ] **Step 2: Add a failing active-desktop name contract test**

Add one test to `test_desktop_release_workflow.py` that loads JSON for `desktop/package.json` and reads the active HTML, main process, renderer, README and NSIS files. Use the literal expected name and assert the specific user-visible fields:

```python
def test_active_product_surfaces_use_the_exact_approved_name() -> None:
    expected = "围标串标投标人名称一致检测工具"
    package = json.loads(
        (_PROJECT_ROOT / "desktop/package.json").read_text(encoding="utf-8")
    )
    index_html = (_PROJECT_ROOT / "desktop/index.html").read_text(encoding="utf-8")
    main = (_PROJECT_ROOT / "desktop/src/main/main.ts").read_text(encoding="utf-8")
    renderer = (_PROJECT_ROOT / "desktop/src/renderer/main.ts").read_text(
        encoding="utf-8"
    )
    installer = (_PROJECT_ROOT / "desktop/installer/windows-x64.nsi").read_text(
        encoding="utf-8"
    )
    readme = (_PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert package["productName"] == expected
    assert f"<title>{expected}</title>" in index_html
    assert f'title: "{expected}"' in main
    assert f'"topbar__title", "{expected}"' in renderer
    assert f'Name "{expected}"' in installer
    assert f'"ProductName" "{expected}"' in installer
    assert readme.startswith(f"# {expected}\n")
```

Do not scan historical specs or prototypes; this test covers only active user boundaries.

- [ ] **Step 3: Run the focused tests and capture RED**

Run:

```bash
uv run pytest \
  tests/unit/test_html_export.py \
  tests/unit/test_desktop_release_workflow.py::test_active_product_surfaces_use_the_exact_approved_name -q
```

Expected: failures show the current report/UI/package value is not the exact approved name. Fix test setup errors until the failure is specifically the old name. The real rendered title remains part of the final Parallels GUI acceptance in Task 7.

---

### Task 2: Add RED Squirrel lifecycle and bundling coverage

**Files:**
- Modify: `tests/unit/test_desktop_release_workflow.py`
- Test: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**
- Consumes: `desktop/package.json`, `desktop/vite.main.config.mts`, `desktop/src/main/main.ts`, final Squirrel Setup and installed `.lnk` files.
- Produces: source/bundle contract plus a native RED/GREEN acceptance route consumed by Tasks 6 and 7.

- [ ] **Step 1: Add a failing Squirrel source-and-bundle contract test**

Add a test that checks the application-owned integration boundary rather than re-testing the third-party module implementation:

```python
def test_squirrel_startup_handler_is_a_bundled_production_dependency() -> None:
    package = json.loads(
        (_PROJECT_ROOT / "desktop/package.json").read_text(encoding="utf-8")
    )
    main = (_PROJECT_ROOT / "desktop/src/main/main.ts").read_text(encoding="utf-8")
    vite = (_PROJECT_ROOT / "desktop/vite.main.config.mts").read_text(encoding="utf-8")

    assert package["dependencies"]["electron-squirrel-startup"] == "1.0.1"
    assert 'import squirrelStartup from "electron-squirrel-startup";' in main
    assert "if (squirrelStartup)" in main
    assert 'startsWith("--squirrel-")' not in main
    assert 'external: ["electron"]' in vite
    assert '"electron-squirrel-startup"' not in vite
```

The production mutation this catches is restoring the old wildcard quit or accidentally externalizing the dependency again.

- [ ] **Step 2: Run the Squirrel contract test and retain the native RED**

Run:

```bash
uv run pytest \
  tests/unit/test_desktop_release_workflow.py::test_squirrel_startup_handler_is_a_bundled_production_dependency -q
```

Expected: FAIL because `dependencies` is absent, the wildcard quit remains, and Vite still externalizes the module.

Retain the already captured native Parallels RED that proves `--squirrel-firstrun` exits without a visible window and no installed-target shortcut exists. Do not modify the security-sensitive committed release verifier for this narrowly scoped defect; the real installer/shortcut/first-run behavior is checked with a repository-external, hash-bound acceptance runner in Task 7.

---

### Task 3: Implement the exact product name

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/index.html`
- Modify: `desktop/src/main/main.ts`
- Modify: `desktop/src/renderer/main.ts`
- Modify: `desktop/installer/windows-x64.nsi`
- Modify: `src/document_metadata_inspector/exporters/html_export.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: exact approved literal from the design spec.
- Produces: active UI/package/report display name used by the Windows artifact and Task 6 acceptance.

- [ ] **Step 1: Replace only active display-name values**

Use exactly:

```text
围标串标投标人名称一致检测工具
```

Change `package.json.productName`, active HTML title, `BrowserWindow.title`, renderer topbar text, HTML report `<title>/<h1>`, README current title/description and all NSIS user-visible product strings. For NSIS action labels, retain action words while embedding the exact product name, for example:

```nsi
CreateShortcut "$SMPROGRAMS\围标串标投标人名称一致检测工具\卸载围标串标投标人名称一致检测工具.lnk" \
  "$INSTDIR\Uninstall.exe"
```

Do not change `DocumentMetadataInspector`, `docmeta-review`, `docmeta`, package names or historical documents.

- [ ] **Step 2: Run focused name tests and verify GREEN**

Run the Task 1 commands. Expected: all focused Python and renderer tests pass.

- [ ] **Step 3: Commit the isolated name change**

```bash
git add \
  README.md \
  desktop/package.json \
  desktop/index.html \
  desktop/src/main/main.ts \
  desktop/src/renderer/main.ts \
  desktop/installer/windows-x64.nsi \
  src/document_metadata_inspector/exporters/html_export.py \
  tests/unit/test_html_export.py \
  tests/unit/test_desktop_release_workflow.py
git commit -m "feat: rename the desktop product"
```

---

### Task 4: Restore and bundle the official Squirrel startup handler

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/pnpm-lock.yaml`
- Modify: `desktop/src/main/main.ts`
- Modify: `desktop/vite.main.config.mts`
- Retain: `desktop/src/shared/vendor.d.ts`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**
- Consumes: `electron-squirrel-startup` default boolean export and existing Electron `app` lifecycle.
- Produces: bundled Squirrel handler with correct install/update/uninstall/obsolete behavior and ordinary `--squirrel-firstrun` continuation.

- [ ] **Step 1: Add the exact production dependency**

From `desktop/`, run:

```bash
corepack pnpm add --save-exact electron-squirrel-startup@1.0.1
```

Verify `package.json` has a `dependencies` entry, not `devDependencies`, and the lockfile uses the existing pinned integrity record.

- [ ] **Step 2: Replace the wildcard quit with the official handler**

At the top of `desktop/src/main/main.ts`, import the module immediately after Electron imports:

```ts
import squirrelStartup from "electron-squirrel-startup";
```

Replace the wildcard block with:

```ts
if (squirrelStartup) {
  app.quit();
}
```

Do not add a branch for `--squirrel-firstrun`; the official handler deliberately returns `false` for it.

- [ ] **Step 3: Bundle the handler**

Change the Vite main config to:

```ts
rollupOptions: {
  external: ["electron"],
},
```

Keep `vendor.d.ts` so TypeScript retains the exact default-export type.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
uv run pytest \
  tests/unit/test_desktop_release_workflow.py::test_squirrel_startup_handler_is_a_bundled_production_dependency \
  tests/unit/test_desktop_release_workflow.py -q
(cd desktop && corepack pnpm test)
(cd desktop && corepack pnpm typecheck)
(cd desktop && corepack pnpm build)
```

Inspect `desktop/.vite/build/main.js` and require:

- no runtime `require("electron-squirrel-startup")` or equivalent external import;
- bundled literals `--createShortcut=`, `--removeShortcut=`, `--squirrel-install`,
  `--squirrel-updated`, `--squirrel-uninstall` and `--squirrel-obsolete`;
- no wildcard branch that exits on `--squirrel-firstrun`.

- [ ] **Step 5: Commit the isolated Squirrel fix**

```bash
git add \
  desktop/package.json \
  desktop/pnpm-lock.yaml \
  desktop/src/main/main.ts \
  desktop/vite.main.config.mts \
  tests/unit/test_desktop_release_workflow.py
git commit -m "fix: complete Squirrel first-run startup"
```

---

### Task 5: Run complete source gates

**Files:**
- Verify only; do not edit generated output into Git.

**Interfaces:**
- Consumes: committed Tasks 3 and 4.
- Produces: a frozen source commit eligible for Windows packaging.

- [ ] **Step 1: Run the complete Python gates**

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
```

Each command must exit `0`. Record the exact pass/skip counts from pytest.

- [ ] **Step 2: Verify the Java worker**

```bash
(cd java-worker && ./mvnw --batch-mode --no-transfer-progress verify)
```

Require Maven BUILD SUCCESS and zero failed/error tests.

- [ ] **Step 3: Run all desktop gates**

```bash
(cd desktop && corepack pnpm install --frozen-lockfile)
(cd desktop && corepack pnpm test)
(cd desktop && corepack pnpm typecheck)
(cd desktop && corepack pnpm lint)
(cd desktop && corepack pnpm format:check)
(cd desktop && corepack pnpm build)
```

Require every command to exit `0` and re-check the bundled Squirrel literals from Task 4.

- [ ] **Step 4: Audit Git scope**

```bash
git status --short
git diff --check
git log -3 --oneline
```

Only the intended commits may be new; generated `.vite`, `dist`, `out`, caches and diagnostic evidence must remain untracked/ignored.

---

### Task 6: Build fresh Windows x64 artifacts

**Files:**
- Windows generated: `desktop/out/**`
- Windows generated: `release/windows-x64/**`
- Repo-external evidence: `C:\docmeta-diagnosis\product-name-squirrel-<commit>-*`

**Interfaces:**
- Consumes: exact frozen Git HEAD, existing audited x64 Python/Node/Electron/runtime caches and the approved architecture diagnostic boundary for the ARM host.
- Produces: fresh Setup, portable ZIP, CLI ZIP, checksums, BUILD-INFO and notices tied to the new HEAD.

- [ ] **Step 1: Preserve and clean the old diagnostic installation**

Record the current `0bb2ce5` install root, SquirrelTemp, uninstall entry, target processes and hashes. Invoke its real `Update.exe --uninstall`, wait within the committed verifier bound, and preserve any accepted residue in a unique recoverable hold. Require a clean user install root before the new build acceptance.

- [ ] **Step 2: Synchronize only frozen source changes into the NTFS snapshot**

Reuse the proven NTFS snapshot only after recording before/after normalized manifests. Copy the exact committed files changed since `0bb2ce5`, including package/lock changes, and prove:

- shared Git HEAD equals the frozen commit;
- source and snapshot file SHA-256 values match;
- no unexpected non-generated file differs.

- [ ] **Step 3: Install the locked desktop dependency tree on NTFS**

Use Node v24 x64, pnpm 11.10.0 and a unique/process-local NTFS store configuration. Run:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm format:check
corepack pnpm build
```

Require `electron-squirrel-startup` to be present in the dependency graph and bundled in `.vite/build/main.js`; packaged runtime must not need its `node_modules` directory.

- [ ] **Step 4: Build and assemble the release**

Use the existing verified x64 runtime and offline Electron ZIP path, then run the same native Forge/release commands already accepted for this snapshot. Do not reuse old Setup/ZIP bytes. Require new artifact hashes and BUILD-INFO HEAD.

- [ ] **Step 5: Run the original Windows release verifier**

Run committed `scripts/verify_windows_release.ps1 -Mode All` for its existing release-integrity, portable, install, embedded-runtime and uninstall gates. On the ARM host, only the three exact SHA-bound frozen `docmeta.exe verify` calls may use the already-audited architecture surrogate. Do not claim this existing verifier checks the newly fixed first-run/shortcut path; those two behaviors are exercised separately and for real in Task 7.

---

### Task 7: Perform user-level Parallels acceptance and deliver artifacts

**Files:**
- Deliver: `/Users/zhongerbing/Desktop/围标串标投标人名称一致检测工具-安装版-x64-<commit>.exe`
- Deliver: `/Users/zhongerbing/Desktop/围标串标投标人名称一致检测工具-绿色免安装-x64-<commit>.zip`
- Evidence: `/Users/zhongerbing/Documents/xm/.superpowers/sdd/2026-08-12-installer-x64-diagnosis/final-<commit>/`

**Interfaces:**
- Consumes: Task 6 release artifacts and hashes.
- Produces: final user-deliverable files plus reproducible installation/GUI evidence.

- [ ] **Step 1: Copy and hash fresh artifacts**

Copy, do not rename in place, from the verified internal release directory. Require destination byte counts and SHA-256 values to equal sources. Preserve the old `0bb2ce5` desktop artifacts.

- [ ] **Step 2: Run one clean interactive installer launch**

Under `dae8\zhongerbing` session 1, launch the local NTFS copy once. Sample every 200–250 ms using process identity `(name, pid, start time, path)`. Require:

- Setup exit code `0` inside the 300-second safety bound;
- visible Squirrel progress is allowed;
- no CMD/PowerShell/Java/ExifTool visible window;
- exact product main-window title appears after first run;
- no target process is mistaken by PID reuse.

- [ ] **Step 3: Verify the installed shortcut by target**

Enumerate Start Menu and desktop `.lnk` files with `WScript.Shell`. Require at least one shortcut whose `TargetPath` belongs to `%LOCALAPPDATA%\DocumentMetadataInspector`; reject the existing green-portable shortcut as evidence. Launch that shortcut once, require the exact title, then close with `WM_CLOSE`.

- [ ] **Step 4: Verify the installed runtime and uninstall**

Require installed Electron and embedded `docmeta.exe` PE machine `0x8664` and core hash equal to release records. Invoke real `Update.exe --uninstall`, require bounded completion, strict owned-residue handling and zero product/Java/ExifTool processes.

- [ ] **Step 5: Verify the portable build**

Extract the new portable ZIP into a fresh C: directory with Chinese characters and spaces. Launch `docmeta-review.exe`, require the exact title, no CMD window and clean `WM_CLOSE`. Do not rerun the large private document scan unless a changed runtime or scan path requires it; this task changes only name and installer startup.

- [ ] **Step 6: Final fingerprint and handoff**

Re-hash both desktop artifacts and record:

- filename, byte count, SHA-256, source HEAD;
- Setup wrapper PE and payload PE architectures;
- installation/shortcut/first-run/uninstall outcomes;
- unsigned Authenticode status as a separate known limitation;
- final process and temporary-root residue counts.

Update the task report outside Git, then hand off clickable desktop paths to the user.

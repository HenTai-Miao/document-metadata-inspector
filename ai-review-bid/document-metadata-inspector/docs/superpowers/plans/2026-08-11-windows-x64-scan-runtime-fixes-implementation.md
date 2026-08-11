# Windows x64 Scan Runtime Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Windows x64 绿色版完成扫描后报告落盘失败的问题，并阻止 Java/ExifTool 子进程在扫描期间创建可见控制台窗口。

**Architecture:** 保留现有原子导出和 worker 接口，只把同步临时文件的描述符改为可写描述符。新增一个仅返回平台创建标志的共享 Python 边界，四个 Java/ExifTool 启动点显式消费它；Electron 主进程、解析协议和错误模型保持不变。

**Tech Stack:** Python 3.12.13、uv、pytest、Ruff、BasedPyright、Electron 43.3.0、Node.js 24、pnpm 11.10.0、Windows PowerShell 5.1、Temurin JRE 21.0.12+8、ExifTool 13.55。

## Global Constraints

- 实施分支固定为 `dev-yx/design-spec-style-polish-20260810`；不创建替代功能分支。
- 每项生产改动之前必须先写测试并观察到由原缺陷造成的失败。
- 只修复报告落盘和 Java/ExifTool 控制台窗口；不处理 Parallels ARM64 资源选择或 UNC 启动崩溃。
- 不改变公共模型、JSON 协议、错误码、解析器状态、扫描并发度或 UI 文案。
- 保留 `shell=False`、标准流管道、超时、输出预算、进程树终止和临时目录清理。
- 不引入依赖，不改用 `javaw.exe`，不修改 Java Worker 或随包二进制。
- 当前未提交的 `desktop/biome.json`、`desktop/scripts/build-icons.mjs`、
  `src/document_metadata_inspector/resources.py` 和 `tests/unit/test_tool_resources.py`
  含有前一任务的改动；编辑重叠文件时必须保留原有 hunk，并只暂存本计划新增的 hunk。
- 不暂存或删除任何其他未跟踪文件。
- 真实绿色版必须放在 Windows 本地盘运行；测试输入可以继续位于 `\\Mac\Home` 共享目录。

---

## File and interface map

### New file

- `src/document_metadata_inspector/subprocesses.py`：唯一的跨平台后台子进程创建标志边界。

### Existing files to modify

- `src/document_metadata_inspector/exporters/__init__.py`：用可写描述符执行临时报告 `fsync`。
- `src/document_metadata_inspector/resources.py`：ExifTool 和 Java 版本探测传入无窗口标志。
- `src/document_metadata_inspector/workers/apache.py`：Apache Worker `Popen` 传入无窗口标志。
- `src/document_metadata_inspector/workers/exiftool.py`：ExifTool `Popen` 传入无窗口标志。
- `tests/unit/test_json_export.py`：跨平台复现 Windows 只读描述符 `EBADF`。
- `tests/unit/test_tool_resources.py`：覆盖两个版本探测调用点。
- `tests/unit/test_apache_worker_adapter.py`：覆盖 Java Worker 调用点。
- `tests/unit/test_exiftool_adapter.py`：覆盖 ExifTool 调用点。

### Stable interface

```python
def hidden_subprocess_creation_flags() -> int:
    """Return CREATE_NO_WINDOW on Windows and zero elsewhere."""
```

---

### Task 1: Make atomic report durability Windows-safe

**Files:**

- Modify: `tests/unit/test_json_export.py`
- Modify: `src/document_metadata_inspector/exporters/__init__.py:45-63`

**Interfaces:**

- Consumes: existing `write_atomic_output(target: Path, writer: Callable[[Path], None]) -> Path`.
- Produces: unchanged interface with a write-capable descriptor at the durability boundary.

- [ ] **Step 1: Write the failing descriptor regression**

Add `import os` and import the exporter module itself, then add:

```python
def test_atomic_writer_fsyncs_a_write_capable_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = make_export_report()
    target = tmp_path / "report.json"
    real_fsync = exporters_module.os.fsync

    def require_write_capability(descriptor: int) -> None:
        assert os.write(descriptor, b"") == 0
        real_fsync(descriptor)

    monkeypatch.setattr(exporters_module.os, "fsync", require_write_capability)

    result = export_report(
        report,
        ExportTarget(path=target, format=ExportFormat.JSON),
    )

    assert result == target
    assert target.is_file()
```

This catches the production mutation “reopen the temporary report read-only before `fsync`”.

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
uv run pytest \
  tests/unit/test_json_export.py::test_atomic_writer_fsyncs_a_write_capable_descriptor -v
```

Expected: FAIL because the wrapped `fsync` performs a zero-byte write on the current `rb`
descriptor, raising `EBADF`, which is surfaced as `ExportError`.

- [ ] **Step 3: Implement the minimal production fix**

Change only the durability reopen mode:

```python
with temporary.open("r+b") as stream:
    os.fsync(stream.fileno())
```

- [ ] **Step 4: Verify GREEN and the complete exporter contract**

Run:

```bash
uv run pytest tests/unit/test_json_export.py -v
```

Expected: all JSON export tests PASS; the new test proves the descriptor is writable and the
existing failure test proves no partial or temporary file remains.

- [ ] **Step 5: Commit only Task 1**

```bash
git add -- \
  src/document_metadata_inspector/exporters/__init__.py \
  tests/unit/test_json_export.py
git diff --cached --check
git commit -m "fix: make Windows report export durable"
```

---

### Task 2: Hide Java and ExifTool version probes

**Files:**

- Create: `src/document_metadata_inspector/subprocesses.py`
- Modify: `tests/unit/test_tool_resources.py`
- Modify: `src/document_metadata_inspector/resources.py:398-457`

**Interfaces:**

- Produces: `hidden_subprocess_creation_flags() -> int`.
- Consumers: resource probes in this task and worker adapters in Task 3.

- [ ] **Step 1: Add failing ExifTool and Java probe tests**

Add `import os` and this independent expected-value helper to
`tests/unit/test_tool_resources.py`:

```python
def _expected_hidden_creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0
```

Add one test around the explicit ExifTool development resource and one around the explicit
Apache development resource. Each spy delegates to the existing successful result helper and
records kwargs:

```python
observed: dict[str, object] = {}

def successful_version(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    observed.update(kwargs)
    return _successful_version(*args, **kwargs)

monkeypatch.setattr(subprocess, "run", successful_version)
```

The Java test uses `_successful_java_version`. After resolution, each test asserts:

```python
assert observed.get("creationflags") == _expected_hidden_creation_flags()
```

The tests catch the production mutations “omit the creation flag from ExifTool version
validation” and “omit it from Java version validation”.

- [ ] **Step 2: Run the two tests and verify RED**

Run the two exact node IDs after adding them:

```bash
uv run pytest \
  tests/unit/test_tool_resources.py::test_exiftool_version_probe_suppresses_windows_console \
  tests/unit/test_tool_resources.py::test_java_version_probe_suppresses_windows_console -v
```

Expected: both FAIL because the existing calls do not pass `creationflags` and the observed
value is `None` rather than `0` on macOS or `CREATE_NO_WINDOW` on Windows.

- [ ] **Step 3: Add the focused subprocess flag boundary**

Create `src/document_metadata_inspector/subprocesses.py`:

```python
"""Cross-platform subprocess launch options for invisible offline workers."""

from __future__ import annotations

import os
import subprocess


def hidden_subprocess_creation_flags() -> int:
    """Return the Windows no-console flag without changing other platforms."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


__all__ = ("hidden_subprocess_creation_flags",)
```

- [ ] **Step 4: Apply the flag to both resource probes**

Import the helper into `resources.py` and add this keyword to both `subprocess.run()` calls:

```python
creationflags=hidden_subprocess_creation_flags(),
```

Do not alter command arguments, cwd, environment, capture, timeout, version matching, or error
translation.

- [ ] **Step 5: Verify GREEN and resource resolution regressions**

Run:

```bash
uv run pytest tests/unit/test_tool_resources.py -v
```

Expected: all resource tests PASS, including the pre-existing vendored Java metadata test in
the dirty worktree.

- [ ] **Step 6: Stage only this task’s hunks and commit**

Use interactive hunk selection for the two pre-dirty files:

```bash
git add -- src/document_metadata_inspector/subprocesses.py
git add -p -- src/document_metadata_inspector/resources.py
git add -p -- tests/unit/test_tool_resources.py
git diff --cached --check
git diff --cached --stat
git commit -m "fix: hide Windows runtime probes"
```

Reject the pre-existing manifest-model and vendored-metadata hunks from the staged patch.

---

### Task 3: Hide per-document Java and ExifTool workers

**Files:**

- Modify: `tests/unit/test_apache_worker_adapter.py`
- Modify: `tests/unit/test_exiftool_adapter.py`
- Modify: `src/document_metadata_inspector/workers/apache.py:264-271`
- Modify: `src/document_metadata_inspector/workers/exiftool.py:299-306`

**Interfaces:**

- Consumes: `hidden_subprocess_creation_flags() -> int` from Task 2.
- Produces: unchanged `ApacheWorker.scan()` and `ExifToolWorker.scan()` behavior without a
  Windows console window.

- [ ] **Step 1: Add a failing Apache worker launch test**

Import `os` and `subprocess`. Wrap the real `Popen`, run one real controlled worker, and assert
the creation flag:

```python
def test_worker_process_suppresses_windows_console(
    source: SourceSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    observed: list[int | None] = []

    def tracked_popen(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        value = kwargs.get("creationflags")
        observed.append(value if isinstance(value, int) else None)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(apache_module.subprocess, "Popen", tracked_popen)
    worker = ApacheWorker(
        command=_command(
            """
            import json, sys
            request = json.loads(sys.stdin.readline())
            print(json.dumps({
                "request_id": request["request_id"],
                "status": "ok",
                "content_type": "application/pdf",
                "metadata": {"dc:creator": ["Alice"]},
                "embedded_resources": [],
                "warnings": [],
            }))
            """
        ),
        version="3.3.2",
    )

    run = worker.scan(source, None, InspectionLimits())

    expected = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    assert run.status is ParserStatus.SUCCEEDED
    assert observed == [expected]
```

Use the same complete controlled JSON response as the existing success test; do not mock the
worker response.

- [ ] **Step 2: Add the equivalent failing ExifTool worker launch test**

Import the ExifTool module as `exiftool_module`, wrap its real `Popen`, run a controlled valid
ExifTool JSON response, and assert exactly one observed flag equal to the independent platform
expectation.

- [ ] **Step 3: Run both tests and verify RED**

Run:

```bash
uv run pytest \
  tests/unit/test_apache_worker_adapter.py::test_worker_process_suppresses_windows_console \
  tests/unit/test_exiftool_adapter.py::test_worker_process_suppresses_windows_console -v
```

Expected: both FAIL with observed `[None]` because neither current `Popen` call supplies the
keyword.

- [ ] **Step 4: Apply the shared flag to both worker launches**

Import the Task 2 helper in both worker modules and add:

```python
creationflags=hidden_subprocess_creation_flags(),
```

to each existing `Popen` call. Make no other worker changes.

- [ ] **Step 5: Verify GREEN and complete adapter behavior**

Run:

```bash
uv run pytest \
  tests/unit/test_apache_worker_adapter.py \
  tests/unit/test_exiftool_adapter.py -v
```

Expected: all adapter tests PASS, including timeout, output-budget, password, source-mutation,
and unavailable-process behavior.

- [ ] **Step 6: Commit Task 3**

```bash
git add -- \
  src/document_metadata_inspector/workers/apache.py \
  src/document_metadata_inspector/workers/exiftool.py \
  tests/unit/test_apache_worker_adapter.py \
  tests/unit/test_exiftool_adapter.py
git diff --cached --check
git commit -m "fix: hide Windows parser workers"
```

---

### Task 4: Verify source, package, and Windows runtime behavior

**Files:**

- Verify only: all files changed by Tasks 1-3.
- Preserve: every pre-existing dirty and untracked path listed in Global Constraints.

**Interfaces:**

- Consumes: both independent fixes.
- Produces: evidence that the original Windows screenshots no longer reproduce.

- [ ] **Step 1: Run focused Python verification**

```bash
uv run pytest \
  tests/unit/test_json_export.py \
  tests/unit/test_tool_resources.py \
  tests/unit/test_apache_worker_adapter.py \
  tests/unit/test_exiftool_adapter.py -q
uv run ruff check \
  src/document_metadata_inspector/exporters/__init__.py \
  src/document_metadata_inspector/resources.py \
  src/document_metadata_inspector/subprocesses.py \
  src/document_metadata_inspector/workers/apache.py \
  src/document_metadata_inspector/workers/exiftool.py \
  tests/unit/test_json_export.py \
  tests/unit/test_tool_resources.py \
  tests/unit/test_apache_worker_adapter.py \
  tests/unit/test_exiftool_adapter.py
uv run ruff format --check \
  src/document_metadata_inspector/exporters/__init__.py \
  src/document_metadata_inspector/resources.py \
  src/document_metadata_inspector/subprocesses.py \
  src/document_metadata_inspector/workers/apache.py \
  src/document_metadata_inspector/workers/exiftool.py \
  tests/unit/test_json_export.py \
  tests/unit/test_tool_resources.py \
  tests/unit/test_apache_worker_adapter.py \
  tests/unit/test_exiftool_adapter.py
uv run basedpyright
```

Expected: all focused tests and checks PASS with no new diagnostics.

- [ ] **Step 2: Run complete repository quality gates**

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
```

Expected: all commands exit `0`. If a pre-existing unrelated failure remains, record its exact
path and output without editing unrelated files.

- [ ] **Step 3: Run Java and desktop gates**

```bash
(cd java-worker && ./mvnw --batch-mode --no-transfer-progress verify)
(cd desktop && pnpm test)
(cd desktop && pnpm lint)
(cd desktop && pnpm typecheck)
(cd desktop && pnpm package)
```

Expected: all commands exit `0`; the packaged macOS artifact is only a build-integrity check,
not the Windows acceptance artifact.

- [ ] **Step 4: Build the Windows x64 release in Parallels**

From Windows PowerShell in the shared checkout, run:

```powershell
Set-Location "\\Mac\Home\Documents\xm\ai-review-bid\document-metadata-inspector"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows_x64.ps1
```

Expected: the one-command build and release verifier exit `0` and create a new portable x64
artifact using the fixed source.

- [ ] **Step 5: Reproduce the original report path with the specified input**

Copy the newly built portable directory to `C:\docmeta-diagnosis\app-fixed`. Because the
available Parallels guest is ARM64 while the release under test is x64, use this diagnostic-only
process-architecture override to select the x64 resources; it does not modify product files:

```powershell
$runtime = "C:\docmeta-diagnosis\app-fixed\resources\docmeta-runtime"
$python = Join-Path $runtime "python.exe"
$workingDirectory = Join-Path $runtime "app"
$input = (
  "\\Mac\Home\Desktop\101_[HNZB2023-11-3-031]_" +
  "华能陕西公司铜川煤电公司新建5号储煤场项目网架钢结构供货及安装施工标段-新方案1_副本\投标文件"
)
$runRoot = "C:\docmeta-diagnosis\run-fixed"
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$output = Join-Path $runRoot "comparison.json"
$code = (
  "import platform;" +
  "platform.machine=lambda:str().join(map(chr,[65,77,68,54,52]));" +
  "from document_metadata_inspector.cli import app;" +
  "app()"
)
Push-Location $workingDirectory
try {
  & $python -I -s -c $code compare --recursive `
    --group-by-top-level-dir --json $output $input
  $scanExitCode = $LASTEXITCODE
}
finally {
  Pop-Location
}
if ($scanExitCode -ne 0) {
  throw "Fixed packaged comparison returned exit code $scanExitCode"
}
$report = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if (@($report.documents).Count -ne 9) {
  throw "Fixed packaged comparison did not return nine documents"
}
```

Expected: exit code `0`, output JSON exists, parses as one comparison report, and contains 9
documents. A physical Windows x64 machine runs the same command with the ordinary `-m
document_metadata_inspector.cli` entry point and needs no architecture override.

- [ ] **Step 6: Verify there are no visible console descendants**

During the same Windows run, sample process starts for `python.exe`, `java.exe`,
`exiftool.exe`, `conhost.exe`, and `OpenConsole.exe`. Expected:

- Java and ExifTool are direct or owned descendants of the scan Python process;
- their `MainWindowHandle` values remain `0`;
- no new non-baseline visible `conhost` or `OpenConsole` window is created;
- no Python, Java, or ExifTool process remains after completion.

- [ ] **Step 7: Inspect final scope and commit verification documentation only if changed**

```bash
git status --short
git diff --check
git log --oneline -5
```

Expected: source/test commits contain only the planned fixes; the four pre-existing tracked
modifications remain unstaged unless separately completed by their owning task; no generated
release artifact is added to Git.

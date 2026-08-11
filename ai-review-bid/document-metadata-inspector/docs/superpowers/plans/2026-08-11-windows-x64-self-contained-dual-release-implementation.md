# Windows x64 Self-Contained Dual Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在原生 Windows 10/11 x64 构建中，同时生成内置 Python、私有 Java 21 JRE、Java Worker 和 ExifTool 的桌面安装版与桌面便携版，并为全部内部交付物生成统一、可验证的发布目录。

**Architecture:** 保留现有 PyInstaller `onefile` 核心和 Electron Squirrel 安装链路，给 Electron Forge 增加 Windows ZIP Maker，使两个桌面产物来自同一个经过哈希验证的 packaged app。新增独立 Python 发布汇总器完成版本一致性、产物发现、标准化命名、脱敏构建信息、SHA-256 和事务式目录发布；新增 PowerShell 成品验收脚本，在 Windows 上验证便携包、安装包和冻结核心。

**Tech Stack:** Python 3.12.13、PyInstaller 6.21.0、Temurin JDK/JRE 21.0.12+8、ExifTool 13.55、Electron 43.3.0、Electron Forge 7.11.2、TypeScript 7、Vitest 4、PowerShell 7、GitHub Actions Windows runner。

## Global Constraints

- 目标仅为 Windows 10/11 x64；不支持 Windows 7、32 位 Windows 或 Windows ARM64。
- 最终用户不得安装或依赖系统 Python、Java、ExifTool、Node.js、Microsoft Office 或 LibreOffice。
- 构建机使用完整 Temurin JDK 21.0.12+8；最终包只携带 `jlink` 裁剪的私有 Java 21 JRE。
- 保留 PyInstaller `onefile`；本计划不切换 `onedir`，性能不达标时另起设计。
- 保留 Electron Forge Squirrel 安装器，并由同一个 packaged app 生成 Windows 便携 ZIP。
- 内部发布暂不配置 Authenticode；不得把未签名产物描述为系统信任。
- 所有正式 Windows 产物必须在原生 Windows x64 环境构建和验证；macOS 不能代替该验收。
- 不增加运行时下载、系统工具回退、自动更新或新的打包框架。
- 不改变 Python 公共模型、JSON 序列化、错误码、解析器来源、完整度状态或 Java 网络拒绝边界。
- 只修改 `document-metadata-inspector/`；不得复制工作流到父 Git 仓库根目录或修改相邻项目。
- 正式文件名必须是 `DocumentMetadataInspector-<version>-win-x64-Setup.exe`、`DocumentMetadataInspector-<version>-win-x64-Portable.zip` 和 `DocumentMetadataInspector-<version>-win-x64-CLI.zip`。
- Python `pyproject.toml` 与 Electron `desktop/package.json` 的产品版本必须相同，否则发布汇总失败。
- `release/windows-x64/` 必须包含上述三个交付物、`SHA256SUMS`、`BUILD-INFO.json` 和 `THIRD_PARTY_NOTICES.md`。
- `BUILD-INFO.json` 只能记录 schema、产品版本、Git commit、目标平台、固定工具版本、核心 SHA-256 和 UTC 构建时间；不得记录用户名、主机名、绝对路径、环境变量值或凭据。
- 每个行为变更先写失败测试，再做最小实现；每个任务单独提交，不混入用户现有未跟踪文件。

---

## File and Interface Map

### Existing files to modify

- `desktop/forge.config.ts`：配置 Windows Squirrel/ZIP Makers，并在 Makers 运行前验证 packaged app 中的离线核心。
- `tests/unit/test_desktop_release_workflow.py`：对 Forge、Windows workflow、验收脚本和文档之间的静态发布契约做回归检查。
- `.github/workflows/build-offline-releases.yml`：仅在现有 Windows matrix 项中汇总、验收并上传统一 Windows 发布目录；其他平台维持现有产物。
- `README.md`：说明 Windows 安装版与便携版的最终用户入口。
- `docs/packaging.md`：记录原生 Windows 双交付构建命令、产物和未签名限制。

### New focused files

- `desktop/packaged-runtime-integrity.mts`：解析平台特定 packaged app 资源目录，并验证内嵌 `docmeta`/`docmeta.exe` 与其单记录 `SHA256SUMS`。
- `desktop/tests/packaged-runtime-integrity.test.ts`：覆盖 Windows/macOS 布局、正常哈希和篡改拒绝。
- `scripts/windows_release.py`：纯 Python 发布领域模块；负责版本读取、输入发现、安全验证、标准化复制、构建信息、SHA-256 和事务式目录替换。
- `scripts/assemble_windows_release.py`：Windows x64 CLI 门面；解析默认目录、取得 Git commit/UTC 时间并调用 `assemble_windows_release()`。
- `tests/unit/test_windows_release.py`：覆盖成功汇总、版本冲突、重复/符号链接输入、核心哈希异常和发布失败回滚。
- `scripts/verify_windows_release.ps1`：在 Windows 上验证统一哈希、解压/移动便携包、冻结核心六项自检，以及可选的 Squirrel 安装/卸载路径。
- `docs/windows-x64-release-acceptance.md`：人工成品验收清单，覆盖 Defender、GUI 启动、真实扫描、长路径、篡改和卸载保留用户文件。

### Stable interfaces introduced by this plan

```python
def assemble_windows_release(
    project_root: Path,
    forge_output: Path,
    cli_release_directory: Path,
    output_directory: Path,
    *,
    git_commit: str,
    built_at_utc: datetime,
) -> Path:
    """Publish one complete release/windows-x64 directory atomically."""
```

```typescript
export async function verifyPackagedRuntimeHash(
  applicationPath: string,
  platform: NodeJS.Platform,
): Promise<void>;
```

```powershell
scripts/verify_windows_release.ps1 `
  -ReleaseDirectory release/windows-x64 `
  -Mode Portable
scripts/verify_windows_release.ps1 `
  -ReleaseDirectory release/windows-x64 `
  -Mode All
```

`Portable` 只验证统一哈希、便携包、移动后运行和核心六项自检；`All` 另外执行 Squirrel 静默安装、已安装核心自检和卸载，且要求测试账户中不存在旧版安装目录。

---

### Task 1: Enable the Windows installer and portable ZIP makers

**Files:**

- Modify: `desktop/forge.config.ts:76-85`
- Test: `tests/unit/test_desktop_release_workflow.py:1-24`

**Interfaces:**

- Consumes: 已安装的 `@electron-forge/maker-squirrel` 和 `@electron-forge/maker-zip` 7.11.2。
- Produces: Windows `pnpm make` 同时运行 Squirrel Maker 与 ZIP Maker；macOS ZIP/DMG 和 Linux DEB/RPM 行为不变。

- [ ] **Step 1: Write the failing Forge maker regression test**

在 `tests/unit/test_desktop_release_workflow.py` 增加：

```python
def test_windows_forge_builds_an_installer_and_a_portable_zip() -> None:
    forge_config = (_PROJECT_ROOT / "desktop/forge.config.ts").read_text(
        encoding="utf-8"
    )

    assert 'name: "@electron-forge/maker-squirrel"' in forge_config
    assert 'platforms: ["win32"]' in forge_config
    assert (
        '{ name: "@electron-forge/maker-zip", '
        'platforms: ["darwin", "win32"], config: {} }'
        in forge_config
    )
```

- [ ] **Step 2: Run the focused test and confirm the missing Windows ZIP target**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py::test_windows_forge_builds_an_installer_and_a_portable_zip -v
```

Expected: FAIL because Maker ZIP currently contains only `platforms: ["darwin"]`.

- [ ] **Step 3: Add `win32` to the existing ZIP Maker**

Change only the ZIP Maker entry in `desktop/forge.config.ts`:

```typescript
{ name: "@electron-forge/maker-zip", platforms: ["darwin", "win32"], config: {} },
```

Do not add another Maker ZIP instance and do not change Squirrel configuration.

- [ ] **Step 4: Run focused Python and Electron configuration checks**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py -v
cd desktop
pnpm typecheck
pnpm lint
cd ..
```

Expected: all commands PASS.

- [ ] **Step 5: Commit the dual Maker configuration**

```bash
git add desktop/forge.config.ts tests/unit/test_desktop_release_workflow.py
git commit -m "feat: add Windows portable desktop archive"
```

---

### Task 2: Verify the packaged offline core before either Maker runs

**Files:**

- Create: `desktop/packaged-runtime-integrity.mts`
- Create: `desktop/tests/packaged-runtime-integrity.test.ts`
- Modify: `desktop/forge.config.ts:1-75`
- Modify: `tests/unit/test_desktop_release_workflow.py:38-47`

**Interfaces:**

- Consumes: `expectedExecutableSha256(manifest, executableName)` from `desktop/checksum-manifest.mjs` and Forge `postPackage` output paths.
- Produces: `verifyPackagedRuntimeHash(applicationPath, platform) -> Promise<void>`; it resolves only when the packaged core bytes match the copied single-record manifest.
- Error contract: any missing file, unsafe manifest or digest mismatch throws `Error("Packaged offline core failed checksum verification")` during the build, before Squirrel/ZIP Makers publish anything.

- [ ] **Step 1: Write Windows/macOS packaged-layout tests**

Create `desktop/tests/packaged-runtime-integrity.test.ts`:

```typescript
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { verifyPackagedRuntimeHash } from "../packaged-runtime-integrity.mts";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

async function applicationWithRuntime(
  platform: "darwin" | "win32",
  contents: string,
): Promise<string> {
  const application = await mkdtemp(join(tmpdir(), "docmeta-packaged-runtime-"));
  temporaryDirectories.push(application);
  const resources =
    platform === "darwin"
      ? join(application, "Contents", "Resources")
      : join(application, "resources");
  const runtime = join(resources, "docmeta-runtime");
  await mkdir(runtime, { recursive: true });
  const executableName = platform === "win32" ? "docmeta.exe" : "docmeta";
  await writeFile(join(runtime, executableName), contents);
  const digest = createHash("sha256").update(contents).digest("hex");
  await writeFile(join(runtime, "SHA256SUMS"), `${digest}  ${executableName}\n`, "utf8");
  return application;
}

describe("verifyPackagedRuntimeHash", () => {
  test.each(["darwin", "win32"] as const)(
    "accepts the %s packaged application layout",
    async (platform) => {
      const application = await applicationWithRuntime(platform, "trusted core");
      await expect(verifyPackagedRuntimeHash(application, platform)).resolves.toBeUndefined();
    },
  );

  test("rejects a modified Windows core", async () => {
    const application = await applicationWithRuntime("win32", "trusted core");
    await writeFile(
      join(application, "resources", "docmeta-runtime", "docmeta.exe"),
      "modified core",
    );
    await expect(verifyPackagedRuntimeHash(application, "win32")).rejects.toThrow(
      "Packaged offline core failed checksum verification",
    );
  });
});
```

- [ ] **Step 2: Run the Vitest file and confirm the module is missing**

Run:

```bash
cd desktop
pnpm exec vitest run tests/packaged-runtime-integrity.test.ts
cd ..
```

Expected: FAIL because `packaged-runtime-integrity.mts` does not exist.

- [ ] **Step 3: Implement the focused packaged-runtime verifier**

Create `desktop/packaged-runtime-integrity.mts` with this interface and behavior:

```typescript
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expectedExecutableSha256 } from "./checksum-manifest.mjs";

const INTEGRITY_ERROR = "Packaged offline core failed checksum verification";

async function sha256File(path: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    digest.update(chunk);
  }
  return digest.digest("hex");
}

function runtimeDirectory(applicationPath: string, platform: NodeJS.Platform): string {
  if (platform === "darwin") {
    return resolve(applicationPath, "Contents", "Resources", "docmeta-runtime");
  }
  return resolve(applicationPath, "resources", "docmeta-runtime");
}

export async function verifyPackagedRuntimeHash(
  applicationPath: string,
  platform: NodeJS.Platform,
): Promise<void> {
  try {
    const runtime = runtimeDirectory(applicationPath, platform);
    const executableName = platform === "win32" ? "docmeta.exe" : "docmeta";
    const manifest = await readFile(resolve(runtime, "SHA256SUMS"), "utf8");
    const expected = expectedExecutableSha256(manifest, executableName);
    if ((await sha256File(resolve(runtime, executableName))) !== expected) {
      throw new Error(INTEGRITY_ERROR);
    }
  } catch {
    throw new Error(INTEGRITY_ERROR);
  }
}
```

- [ ] **Step 4: Route every Forge packaged app through the verifier**

In `desktop/forge.config.ts`:

1. Import `verifyPackagedRuntimeHash` from `./packaged-runtime-integrity.mts`.
2. Remove the local crypto/read-stream verifier and its unused imports.
3. Extract the existing macOS `.app` lookup into a helper that requires exactly one `.app`.
4. In `postPackage`, treat non-macOS `result.outputPaths` entries as application directories, verify every platform, and retain `codesign --verify` only for macOS.

The hook body must have this ordering:

```typescript
for (const outputPath of result.outputPaths) {
  const applicationPath =
    result.platform === "darwin" ? await onlyMacApplication(outputPath) : outputPath;
  await verifyPackagedRuntimeHash(applicationPath, result.platform);
  if (result.platform === "darwin") {
    await execFileAsync("codesign", ["--verify", "--deep", "--strict", applicationPath]);
  }
}
```

Keep `onlyMacApplication(outputPath)` equivalent to the existing one-app check and preserve the existing error text for a missing/duplicate macOS bundle.

- [ ] **Step 5: Extend the source-level regression gate**

Add this assertion to the packaged-runtime source regression:

```python
assert "await verifyPackagedRuntimeHash(applicationPath, result.platform)" in forge_config
```

- [ ] **Step 6: Run focused and full desktop tests**

Run:

```bash
cd desktop
pnpm exec vitest run tests/packaged-runtime-integrity.test.ts
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
cd ..
uv run pytest tests/unit/test_desktop_release_workflow.py -v
```

Expected: all commands PASS.

- [ ] **Step 7: Commit the packaged-app integrity gate**

```bash
git add desktop/forge.config.ts desktop/packaged-runtime-integrity.mts \
  desktop/tests/packaged-runtime-integrity.test.ts \
  tests/unit/test_desktop_release_workflow.py
git commit -m "build: verify packaged desktop runtime"
```

---

### Task 3: Assemble one atomic, checksummed Windows release directory

**Files:**

- Create: `scripts/windows_release.py`
- Create: `scripts/assemble_windows_release.py`
- Create: `tests/unit/test_windows_release.py`

**Interfaces:**

- Consumes:
  - Forge Squirrel directory: `desktop/out/make/squirrel.windows/x64/`
  - Forge ZIP directory: `desktop/out/make/zip/win32/x64/`
  - CLI archive: `release/document-metadata-inspector-windows-x86_64.zip`
  - frozen core and checksum: `dist/windows-x86_64/onefile/docmeta.exe` and `SHA256SUMS`
  - versions from `.python-version`, `pyproject.toml`, `desktop/package.json` and `tools/manifest.json`
- Produces: `assemble_windows_release(project_root, forge_output, cli_release_directory, output_directory, *, git_commit, built_at_utc) -> Path`, returning the atomically published `release/windows-x64` directory.
- Failure contract: version mismatch, invalid Git commit/time, missing/duplicate/symlink input, malformed core checksum or publication failure raises `RuntimeError`/`OSError` and preserves the previous complete output directory.

- [ ] **Step 1: Write the successful assembly test and fixture builder**

Create `tests/unit/test_windows_release.py` with a fixture helper that writes only controlled bytes:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.windows_release import assemble_windows_release


def _write_file(path: Path, contents: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(contents)
    return path


def _project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    _ = _write_file(
        project / "pyproject.toml",
        b'[project]\nname = "document-metadata-inspector"\nversion = "0.1.0"\n',
    )
    _ = _write_file(project / ".python-version", b"3.12.13\n")
    desktop_package = {
        "version": "0.1.0",
        "devDependencies": {
            "electron": "43.3.0",
            "@electron-forge/cli": "7.11.2",
            "@electron-forge/maker-squirrel": "7.11.2",
            "@electron-forge/maker-zip": "7.11.2",
        },
    }
    _ = _write_file(
        project / "desktop/package.json",
        json.dumps(desktop_package).encode("utf-8"),
    )
    manifest = {
        "exiftool": {"version": "13.55"},
        "windows_exiftool": {"version": "13.55"},
        "apache_worker": {"java_runtime_version": "21.0.12+8"},
        "temurin_jdk": {"version": "21.0.12+8"},
    }
    _ = _write_file(
        project / "tools/manifest.json",
        json.dumps(manifest).encode("utf-8"),
    )
    _ = _write_file(project / "THIRD_PARTY_NOTICES.md", b"controlled notices\n")
    core = _write_file(
        project / "dist/windows-x86_64/onefile/docmeta.exe",
        b"trusted core",
    )
    _ = _write_file(
        core.parent / "SHA256SUMS",
        f"{sha256(core.read_bytes()).hexdigest()}  docmeta.exe\n".encode(),
    )
    forge = project / "desktop/out/make"
    _ = _write_file(
        forge / "squirrel.windows/x64/DocumentMetadataInspector-0.1.0 Setup.exe",
        b"setup",
    )
    _ = _write_file(
        forge / "zip/win32/x64/docmeta-review-win32-x64-0.1.0.zip",
        b"portable",
    )
    cli_release = project / "release"
    _ = _write_file(
        cli_release / "document-metadata-inspector-windows-x86_64.zip",
        b"cli",
    )
    return project, forge, cli_release


def test_assembles_a_normalized_checksummed_windows_release(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"

    result = assemble_windows_release(
        project,
        forge,
        cli_release,
        output,
        git_commit="a" * 40,
        built_at_utc=datetime(2026, 8, 11, 1, 2, 3, tzinfo=UTC),
    )

    assert result == output
    expected_names = {
        "DocumentMetadataInspector-0.1.0-win-x64-Setup.exe",
        "DocumentMetadataInspector-0.1.0-win-x64-Portable.zip",
        "DocumentMetadataInspector-0.1.0-win-x64-CLI.zip",
        "SHA256SUMS",
        "BUILD-INFO.json",
        "THIRD_PARTY_NOTICES.md",
    }
    assert {path.name for path in output.iterdir()} == expected_names
    build_info = json.loads((output / "BUILD-INFO.json").read_text(encoding="utf-8"))
    assert build_info == {
        "schema_version": "1",
        "product_version": "0.1.0",
        "git_commit": "a" * 40,
        "target_platform": "windows-x86_64",
        "core_sha256": sha256(b"trusted core").hexdigest(),
        "built_at_utc": "2026-08-11T01:02:03Z",
        "versions": {
            "python": "3.12.13",
            "java_runtime": "21.0.12+8",
            "exiftool": "13.55",
            "electron": "43.3.0",
            "electron_forge": "7.11.2",
        },
    }
    checksum_lines = (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(checksum_lines) == 5
    assert checksum_lines == sorted(checksum_lines, key=lambda line: line.split("  ", 1)[1])
    for line in checksum_lines:
        expected, filename = line.split("  ", 1)
        assert sha256((output / filename).read_bytes()).hexdigest() == expected
```

- [ ] **Step 2: Run the new test and confirm the module is missing**

Run:

```bash
uv run pytest tests/unit/test_windows_release.py::test_assembles_a_normalized_checksummed_windows_release -v
```

Expected: FAIL because `scripts.windows_release` does not exist.

- [ ] **Step 3: Implement metadata loading, source discovery and staging**

Create `scripts/windows_release.py`. Use only the Python standard library, including `dataclasses`, `datetime`, `hashlib`, `json`, `re`, `shutil`, `tempfile` and `tomllib`; do not add a dependency. Implement these exact private boundaries:

```python
@dataclass(frozen=True)
class _Sources:
    setup: Path
    portable: Path
    cli: Path
    core: Path
    core_checksum: Path
    notices: Path


def _one_regular_file(directory: Path, pattern: str, description: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"{description} must contain exactly one regular file")
    path = matches[0]
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{description} must contain exactly one regular file")
    return path


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
```

Implement `_load_release_metadata(project_root, git_commit, built_at_utc) -> dict[str, object]` so it:

1. Reads TOML/JSON files without executing code.
2. Requires Python and desktop product versions to be identical non-empty strings.
3. Requires `exiftool.version == windows_exiftool.version`.
4. Requires `apache_worker.java_runtime_version == temurin_jdk.version`.
5. Requires Forge CLI/Squirrel/ZIP versions to be exactly identical.
6. Requires `git_commit` to match `[0-9a-f]{40}`.
7. Requires an aware UTC datetime and serializes it with second precision plus `Z`.
8. Returns the asserted `BUILD-INFO.json` fields except `core_sha256`.

`assemble_windows_release()` must call `_load_release_metadata()` first, pass its string `product_version` to `_discover_sources()`, validate and hash the discovered core, then create the final build-info mapping with:

```python
build_info = {**metadata, "core_sha256": core_sha256}
```

No other keys may be added.

Implement this exact discovery interface:

```python
def _discover_sources(
    project_root: Path,
    forge_output: Path,
    cli_release_directory: Path,
    product_version: str,
) -> _Sources:
```

Use these exact locations and patterns in its body:

```python
setup = _one_regular_file(
    forge_output / "squirrel.windows" / "x64",
    "*Setup.exe",
    "the Squirrel output",
)
portable = _one_regular_file(
    forge_output / "zip" / "win32" / "x64",
    "*.zip",
    "the Windows ZIP output",
)
cli = cli_release_directory / "document-metadata-inspector-windows-x86_64.zip"
core = project_root / "dist/windows-x86_64/onefile/docmeta.exe"
core_checksum = core.parent / "SHA256SUMS"
notices = project_root / "THIRD_PARTY_NOTICES.md"
```

Require every exact-path input to be a non-symlink regular file. Require `setup.name.endswith(f"-{product_version} Setup.exe")` and `portable.name.endswith(f"-{product_version}.zip")`, so a stale Maker output cannot be renamed as the current release. Parse `core_checksum` as exactly one line equal to `f"{_hash(core)}  docmeta.exe"`; reject extra or malformed records.

Stage the three normalized artifacts, notices and sorted, indented `BUILD-INFO.json` in a temporary `windows-x64` directory. Write `SHA256SUMS` last, covering exactly the other five files and sorting lines by filename.

- [ ] **Step 4: Add atomic directory publication and finish `assemble_windows_release`**

Implement publication as a whole-directory swap, not six independent replacements:

```python
def _publish_directory(staged: Path, output: Path, temporary_root: Path) -> None:
    previous = temporary_root / "previous-windows-x64"
    failed = temporary_root / "failed-windows-x64"
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise RuntimeError("the Windows release output must be a safe directory")
    if output.exists():
        _ = output.replace(previous)
    try:
        _ = staged.replace(output)
    except BaseException:
        if output.exists():
            _ = output.replace(failed)
        if previous.exists():
            _ = previous.replace(output)
        raise
```

`assemble_windows_release()` must create `output_directory.parent`, create a `TemporaryDirectory` under that parent, build and re-read every staged hash, then call `_publish_directory()`. Return `output_directory` only after successful publication.

- [ ] **Step 5: Run the success test**

Run:

```bash
uv run pytest tests/unit/test_windows_release.py::test_assembles_a_normalized_checksummed_windows_release -v
```

Expected: PASS.

- [ ] **Step 6: Add fail-closed input and rollback tests**

Append these focused cases to `tests/unit/test_windows_release.py`:

```python
def test_rejects_mismatched_python_and_desktop_versions(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    package_path = project / "desktop/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = "0.2.0"
    _ = package_path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(RuntimeError, match="product versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_java_build_and_runtime_version_drift(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    manifest_path = project / "tools/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["temurin_jdk"]["version"] = "21.0.11+9"
    _ = manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Java runtime versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_windows_exiftool_version_drift(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    manifest_path = project / "tools/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["windows_exiftool"]["version"] = "13.54"
    _ = manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="ExifTool versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_forge_component_version_drift(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    package_path = project / "desktop/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["devDependencies"]["@electron-forge/maker-zip"] = "7.10.2"
    _ = package_path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Electron Forge versions must match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_untraceable_commit_or_naive_build_time(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"

    with pytest.raises(RuntimeError, match="Git commit must be a full lowercase SHA"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="short",
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )
    with pytest.raises(RuntimeError, match="build time must be UTC-aware"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="b" * 40,
            built_at_utc=datetime(2026, 8, 11),  # noqa: DTZ001 - invalid input probe
        )


def test_rejects_duplicate_setup_outputs(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    _ = _write_file(forge / "squirrel.windows/x64/duplicate Setup.exe", b"duplicate")

    with pytest.raises(RuntimeError, match="exactly one regular file"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="c" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_a_stale_portable_version(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    portable = forge / "zip/win32/x64/docmeta-review-win32-x64-0.1.0.zip"
    stale = portable.with_name("docmeta-review-win32-x64-0.0.9.zip")
    _ = portable.replace(stale)

    with pytest.raises(RuntimeError, match="Maker output version does not match"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="c" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_rejects_a_symlinked_cli_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    cli = cli_release / "document-metadata-inspector-windows-x86_64.zip"
    original_is_symlink = Path.is_symlink

    def controlled_is_symlink(path: Path) -> bool:
        return path == cli or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", controlled_is_symlink)

    with pytest.raises(RuntimeError, match="regular file"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="d" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )


def test_publication_failure_restores_the_previous_complete_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, forge, cli_release = _project(tmp_path)
    output = project / "release/windows-x64"
    output.mkdir(parents=True)
    _ = (output / "previous.txt").write_text("previous", encoding="utf-8")
    original_replace = Path.replace

    def fail_staged_publication(source: Path, target: Path) -> Path:
        if source.name == "windows-x64" and target == output and source != output:
            raise OSError("controlled publication failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_staged_publication)

    with pytest.raises(OSError, match="controlled publication failure"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            output,
            git_commit="e" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )

    assert {path.name for path in output.iterdir()} == {"previous.txt"}
    assert (output / "previous.txt").read_text(encoding="utf-8") == "previous"


def test_rejects_core_bytes_that_do_not_match_the_manifest(tmp_path: Path) -> None:
    project, forge, cli_release = _project(tmp_path)
    core = project / "dist/windows-x86_64/onefile/docmeta.exe"
    _ = core.write_bytes(b"modified after checksum")

    with pytest.raises(RuntimeError, match="the frozen core checksum is invalid"):
        _ = assemble_windows_release(
            project,
            forge,
            cli_release,
            project / "release/windows-x64",
            git_commit="f" * 40,
            built_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
        )
```

- [ ] **Step 7: Run all release-assembler unit tests**

Run:

```bash
uv run pytest tests/unit/test_windows_release.py -v
```

Expected initially: the new guard tests FAIL. Implement the version, file-kind, uniqueness, core-checksum and rollback validations specified in Steps 3, 4 and 6, then rerun until every test PASSES.

- [ ] **Step 8: Write the Windows x64 CLI facade**

Create `scripts/assemble_windows_release.py`:

```python
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if __package__:
    from scripts.windows_release import assemble_windows_release
else:
    from windows_release import assemble_windows_release

if TYPE_CHECKING:
    from collections.abc import Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _Arguments(Protocol):
    forge_output: Path
    cli_release_directory: Path
    output_directory: Path


def _require_windows_x64() -> None:
    if platform.system() != "Windows" or platform.machine().casefold() not in {
        "amd64",
        "x86_64",
    }:
        raise RuntimeError("Windows release assembly requires native Windows x64")


def _git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to record the release commit")
    result = subprocess.run(  # noqa: S603
        (git, "rev-parse", "HEAD"),
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the Windows x64 release")
    _ = parser.add_argument(
        "--forge-output",
        type=Path,
        default=_PROJECT_ROOT / "desktop/out/make",
    )
    _ = parser.add_argument(
        "--cli-release-directory",
        type=Path,
        default=_PROJECT_ROOT / "release",
    )
    _ = parser.add_argument(
        "--output-directory",
        type=Path,
        default=_PROJECT_ROOT / "release/windows-x64",
    )
    arguments = cast("_Arguments", cast("object", parser.parse_args(argv)))
    _require_windows_x64()
    output = assemble_windows_release(
        _PROJECT_ROOT,
        arguments.forge_output,
        arguments.cli_release_directory,
        arguments.output_directory,
        git_commit=_git_commit(),
        built_at_utc=datetime.now(UTC),
    )
    print(f"Windows x64 release is ready: {output}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Then add this import at the top of `tests/unit/test_windows_release.py`:

```python
from scripts import assemble_windows_release as assemble_windows_release_cli
```

Add the platform-boundary tests:

```python
def test_cli_accepts_native_windows_amd64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assemble_windows_release_cli.platform, "system", lambda: "Windows")
    monkeypatch.setattr(assemble_windows_release_cli.platform, "machine", lambda: "AMD64")

    assemble_windows_release_cli._require_windows_x64()  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("system", "machine"),
    (("Darwin", "arm64"), ("Windows", "arm64")),
)
def test_cli_rejects_non_windows_x64_hosts(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
) -> None:
    monkeypatch.setattr(assemble_windows_release_cli.platform, "system", lambda: system)
    monkeypatch.setattr(assemble_windows_release_cli.platform, "machine", lambda: machine)

    with pytest.raises(RuntimeError, match="requires native Windows x64"):
        assemble_windows_release_cli._require_windows_x64()  # pyright: ignore[reportPrivateUsage]
```

- [ ] **Step 9: Run focused quality checks**

Run:

```bash
uv run pytest tests/unit/test_windows_release.py -v
uv run ruff format scripts/windows_release.py scripts/assemble_windows_release.py tests/unit/test_windows_release.py
uv run ruff check scripts/windows_release.py scripts/assemble_windows_release.py tests/unit/test_windows_release.py
uv run ruff format --check scripts/windows_release.py scripts/assemble_windows_release.py tests/unit/test_windows_release.py
uv run basedpyright scripts/windows_release.py scripts/assemble_windows_release.py tests/unit/test_windows_release.py
```

Expected: all commands PASS. Do not loosen repository Ruff or BasedPyright settings.

- [ ] **Step 10: Commit the Windows release assembler**

```bash
git add scripts/windows_release.py scripts/assemble_windows_release.py tests/unit/test_windows_release.py
git commit -m "build: assemble atomic Windows release"
```

---

### Task 4: Verify final portable and installed Windows artifacts

**Files:**

- Create: `scripts/verify_windows_release.ps1`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**

- Consumes: a complete `release/windows-x64` directory and its `BUILD-INFO.json`/`SHA256SUMS`.
- Produces: exit code `0` only when all selected checks pass; any mismatch throws and returns nonzero.
- `Portable` mode never installs software. `All` mode requires a clean `%LOCALAPPDATA%\DocumentMetadataInspector` and uses the generated Squirrel installer/uninstaller.

- [ ] **Step 1: Add a failing source-level acceptance-script contract test**

Append to `tests/unit/test_desktop_release_workflow.py`:

```python
def test_windows_release_verifier_checks_hashes_portable_and_installed_cores() -> None:
    verifier = (_PROJECT_ROOT / "scripts/verify_windows_release.ps1").read_text(
        encoding="utf-8"
    )

    assert "Get-FileHash -Algorithm SHA256" in verifier
    assert "Expand-Archive" in verifier
    assert '"文档元数据核验 portable "' in verifier
    assert "ConvertFrom-Json" in verifier
    assert 'checks.Count -ne 6' in verifier
    assert 'ArgumentList "--silent"' in verifier
    assert 'ArgumentList "--uninstall", "-s"' in verifier
    assert "Test-Path $installRoot" in verifier
```

- [ ] **Step 2: Run the focused test and confirm the script is absent**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py::test_windows_release_verifier_checks_hashes_portable_and_installed_cores -v
```

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Implement manifest and frozen-core verification in PowerShell**

Create `scripts/verify_windows_release.ps1` with parameters and fail-closed defaults:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDirectory,

    [ValidateSet("Portable", "All")]
    [string]$Mode = "Portable"
)

$ErrorActionPreference = "Stop"
$release = (Resolve-Path -LiteralPath $ReleaseDirectory).Path
$buildInfo = Get-Content -LiteralPath (Join-Path $release "BUILD-INFO.json") -Raw |
    ConvertFrom-Json

function Get-SingleFile([string]$Pattern, [string]$Description) {
    $matches = @(Get-ChildItem -LiteralPath $release -File -Filter $Pattern)
    if ($matches.Count -ne 1) {
        throw "$Description must resolve to exactly one file"
    }
    return $matches[0].FullName
}

function Test-Core([string]$CorePath) {
    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $CorePath).Hash.ToLowerInvariant()
    if ($digest -ne $buildInfo.core_sha256) {
        throw "Packaged core hash does not match BUILD-INFO.json"
    }
    $jsonText = & $CorePath verify
    if ($LASTEXITCODE -ne 0) {
        throw "Frozen core verification returned a nonzero exit code"
    }
    $report = ($jsonText -join "`n") | ConvertFrom-Json
    if (-not $report.passed -or $report.checks.Count -ne 6) {
        throw "Frozen core verification did not return six passing checks"
    }
    foreach ($check in $report.checks) {
        if ($check.status -ne "pass") {
            throw "Frozen core verification contains a failed check"
        }
    }
}
```

Before extracting anything, parse every non-empty `SHA256SUMS` line with regex `^([0-9a-f]{64})  ([^\\/]+)$`, require exactly five records, require every named file to exist directly under `$release`, and compare each digest:

```powershell
$manifestLines = @(
    Get-Content -LiteralPath (Join-Path $release "SHA256SUMS") |
        Where-Object { $_.Length -gt 0 }
)
if ($manifestLines.Count -ne 5) {
    throw "SHA256SUMS must contain exactly five records"
}
foreach ($line in $manifestLines) {
    if ($line -notmatch '^([0-9a-f]{64})  ([^\\/]+)$') {
        throw "SHA256SUMS contains an invalid record"
    }
    $expected = $Matches[1]
    $filename = $Matches[2]
    $path = Join-Path $release $filename
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "SHA256SUMS references a missing file"
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "Release file hash does not match SHA256SUMS"
    }
}
```

- [ ] **Step 4: Implement portable extraction, relocation and cleanup**

Use an explicit GUID-scoped temporary directory containing Chinese and spaces:

```powershell
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "文档元数据核验 portable " + [guid]::NewGuid().ToString("N")
)
$movedRoot = "$testRoot moved"
$portable = Get-SingleFile "*-Portable.zip" "Portable archive"

try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    Expand-Archive -LiteralPath $portable -DestinationPath $testRoot
    $portableCores = @(
        Get-ChildItem -LiteralPath $testRoot -Recurse -File -Filter "docmeta.exe" |
            Where-Object { $_.FullName -like "*resources*docmeta-runtime*docmeta.exe" }
    )
    if ($portableCores.Count -ne 1) {
        throw "Portable archive must contain exactly one packaged core"
    }
    Test-Core $portableCores[0].FullName
    Move-Item -LiteralPath $testRoot -Destination $movedRoot
    $movedCore = @(
        Get-ChildItem -LiteralPath $movedRoot -Recurse -File -Filter "docmeta.exe" |
            Where-Object { $_.FullName -like "*resources*docmeta-runtime*docmeta.exe" }
    )
    if ($movedCore.Count -ne 1) {
        throw "Moved portable application must contain exactly one packaged core"
    }
    Test-Core $movedCore[0].FullName
}
finally {
    if (Test-Path -LiteralPath $movedRoot) {
        Remove-Item -LiteralPath $movedRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
```

The script may remove only its GUID-scoped `$testRoot`/`$movedRoot`; never remove a broad environment path.

- [ ] **Step 5: Implement clean-account Squirrel install/uninstall verification**

When `$Mode -eq "All"`:

1. Resolve exactly one `*-Setup.exe`.
2. Set `$installRoot = Join-Path $env:LOCALAPPDATA "DocumentMetadataInspector"`.
3. If `$installRoot` already exists, fail without deleting it.
4. Create a GUID-scoped canary file outside `$installRoot`.
5. Run `Start-Process -FilePath $setup -ArgumentList "--silent" -Wait -PassThru` and require exit code `0`.
6. Require exactly one `app-*\resources\docmeta-runtime\docmeta.exe`, compare its hash and run `Test-Core`.
7. In `finally`, run the installation's `Update.exe` with `Start-Process -ArgumentList "--uninstall", "-s" -Wait -PassThru` when it exists.
8. Require the canary still exists, then remove only that canary file and its GUID-scoped parent.

Implement those rules with this structure:

```powershell
if ($Mode -eq "All") {
    $setup = Get-SingleFile "*-Setup.exe" "Squirrel installer"
    $installRoot = Join-Path $env:LOCALAPPDATA "DocumentMetadataInspector"
    if (Test-Path $installRoot) {
        throw "All mode requires a clean test account without an existing installation"
    }
    $canaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "docmeta uninstall canary " + [guid]::NewGuid().ToString("N")
    )
    $canary = Join-Path $canaryRoot "preserve.txt"
    New-Item -ItemType Directory -Path $canaryRoot | Out-Null
    Set-Content -LiteralPath $canary -Value "preserve"
    $update = Join-Path $installRoot "Update.exe"
    try {
        $installer = Start-Process -FilePath $setup -ArgumentList "--silent" -Wait -PassThru
        if ($installer.ExitCode -ne 0) {
            throw "Squirrel installer returned a nonzero exit code"
        }
        $installDeadline = [DateTime]::UtcNow.AddSeconds(60)
        do {
            $installedCores = @(
                Get-ChildItem -LiteralPath $installRoot -Recurse -File `
                    -Filter "docmeta.exe" -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.FullName -like "*app-*resources*docmeta-runtime*docmeta.exe"
                    }
            )
            if ($installedCores.Count -eq 1) { break }
            Start-Sleep -Milliseconds 500
        } while ([DateTime]::UtcNow -lt $installDeadline)
        if ($installedCores.Count -ne 1) {
            throw "Installed application must contain exactly one packaged core"
        }
        Test-Core $installedCores[0].FullName
    }
    finally {
        try {
            if (Test-Path -LiteralPath $update -PathType Leaf) {
                $uninstaller = Start-Process -FilePath $update `
                    -ArgumentList "--uninstall", "-s" -Wait -PassThru
                if ($uninstaller.ExitCode -ne 0) {
                    throw "Squirrel uninstaller returned a nonzero exit code"
                }
            }
            $uninstallDeadline = [DateTime]::UtcNow.AddSeconds(60)
            do {
                $remainingApps = @(
                    Get-ChildItem -LiteralPath $installRoot -Directory `
                        -Filter "app-*" -ErrorAction SilentlyContinue
                )
                if ($remainingApps.Count -eq 0) { break }
                Start-Sleep -Milliseconds 500
            } while ([DateTime]::UtcNow -lt $uninstallDeadline)
            if ($remainingApps.Count -ne 0) {
                throw "Squirrel uninstall left an installed application directory"
            }
        }
        finally {
            $canaryPreserved = Test-Path -LiteralPath $canary -PathType Leaf
            if (Test-Path -LiteralPath $canaryRoot) {
                Remove-Item -LiteralPath $canaryRoot -Recurse -Force
            }
            if (-not $canaryPreserved) {
                throw "Uninstall removed a file outside the application directory"
            }
        }
    }
}
```

After successful uninstall, require that no `app-*` directory remains under `$installRoot`; do not require Squirrel's empty/package cache root to disappear. Do not pre-delete an existing install and do not inspect or remove user document/report directories.

- [ ] **Step 6: Run the source-level contract test and PowerShell parser check**

Run on the current development machine:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py -v
```

Run on Windows PowerShell 7 after the file exists:

```powershell
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path scripts/verify_windows_release.ps1),
    [ref]$tokens,
    [ref]$errors
) | Out-Null
if ($errors.Count -ne 0) { throw $errors[0] }
```

Expected: Python tests PASS and the PowerShell parser reports no errors.

- [ ] **Step 7: Commit the Windows artifact verifier**

```bash
git add scripts/verify_windows_release.ps1 tests/unit/test_desktop_release_workflow.py
git commit -m "test: verify Windows release artifacts"
```

---

### Task 5: Wire assembly, Windows verification and unified upload into CI

**Files:**

- Modify: `.github/workflows/build-offline-releases.yml:95-121`
- Modify: `tests/unit/test_desktop_release_workflow.py:7-24`

**Interfaces:**

- Consumes: existing Windows matrix build, Task 3 CLI, Task 4 PowerShell verifier.
- Produces: the Windows matrix uploads `release/windows-x64/**/*` only after `-Mode All` passes; Linux/macOS continue uploading `desktop/out/make/**/*`.

- [ ] **Step 1: Tighten the failing workflow regression test**

Extend `test_release_matrix_builds_and_uploads_native_desktop_installers()` with:

```python
assert "if: matrix.platform == 'windows-x86_64'" in workflow
assert "run: uv run python scripts/assemble_windows_release.py" in workflow
assert (
    "run: pwsh -File scripts/verify_windows_release.ps1 "
    "-ReleaseDirectory release/windows-x64 -Mode All"
    in workflow
)
assert "path: release/windows-x64/**/*" in workflow
assert "if: matrix.platform != 'windows-x86_64'" in workflow
```

- [ ] **Step 2: Run the focused workflow test and confirm the steps are missing**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py::test_release_matrix_builds_and_uploads_native_desktop_installers -v
```

Expected: FAIL because the workflow has no Windows assembly/verification steps and uploads raw Forge output for every platform.

- [ ] **Step 3: Add Windows-only assembly and verification after `pnpm make`**

Add these steps immediately after the existing desktop Maker step:

```yaml
      - name: Assemble Windows x64 delivery
        if: matrix.platform == 'windows-x86_64'
        run: uv run python scripts/assemble_windows_release.py
      - name: Verify Windows x64 delivery
        if: matrix.platform == 'windows-x86_64'
        run: pwsh -File scripts/verify_windows_release.ps1 -ReleaseDirectory release/windows-x64 -Mode All
```

The assembly step must run after `pnpm make`, because it consumes both Maker directories.

- [ ] **Step 4: Split Windows unified upload from other desktop uploads**

Replace the single cross-platform desktop upload with:

```yaml
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
        if: matrix.platform == 'windows-x86_64'
        with:
          name: docmeta-review-desktop-${{ matrix.platform }}
          path: release/windows-x64/**/*
          if-no-files-found: error
          retention-days: 14
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
        if: matrix.platform != 'windows-x86_64'
        with:
          name: docmeta-review-desktop-${{ matrix.platform }}
          path: desktop/out/make/**/*
          if-no-files-found: error
          retention-days: 14
```

Keep the existing native CLI archive upload unchanged; Windows unified upload intentionally includes a normalized copy of that CLI archive as well.

- [ ] **Step 5: Run focused tests and inspect the workflow diff**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py -v
git diff --check -- .github/workflows/build-offline-releases.yml tests/unit/test_desktop_release_workflow.py
```

Expected: tests PASS and `git diff --check` prints no errors.

- [ ] **Step 6: Commit the Windows CI handoff**

```bash
git add .github/workflows/build-offline-releases.yml tests/unit/test_desktop_release_workflow.py
git commit -m "ci: publish verified Windows dual release"
```

---

### Task 6: Document build, use and manual Windows acceptance

**Files:**

- Modify: `README.md:58-101`
- Modify: `docs/packaging.md:1-86`
- Create: `docs/windows-x64-release-acceptance.md`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**

- Consumes: exact commands and filenames produced by Tasks 1-5.
- Produces: one operator build procedure, separate installer/portable user instructions, and a reproducible manual acceptance record template without embedding real documents or machine secrets.

- [ ] **Step 1: Add failing documentation-contract assertions**

Append to `tests/unit/test_desktop_release_workflow.py`:

```python
def test_windows_dual_release_documentation_matches_the_build_commands() -> None:
    packaging = (_PROJECT_ROOT / "docs/packaging.md").read_text(encoding="utf-8")
    acceptance = (_PROJECT_ROOT / "docs/windows-x64-release-acceptance.md").read_text(
        encoding="utf-8"
    )

    for command in (
        "uv run python scripts/build_release.py --mode onefile",
        "uv run python scripts/package_release.py",
        "pnpm make",
        "uv run python scripts/assemble_windows_release.py",
        "scripts/verify_windows_release.ps1",
    ):
        assert command in packaging
    for filename in (
        "DocumentMetadataInspector-<version>-win-x64-Setup.exe",
        "DocumentMetadataInspector-<version>-win-x64-Portable.zip",
        "DocumentMetadataInspector-<version>-win-x64-CLI.zip",
    ):
        assert filename in packaging
    assert "Windows Defender" in acceptance
    assert "SmartScreen" in acceptance
    assert "docmeta-runtime/docmeta.exe" in acceptance
```

- [ ] **Step 2: Run the focused test and confirm the acceptance document is absent**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py::test_windows_dual_release_documentation_matches_the_build_commands -v
```

Expected: FAIL with `FileNotFoundError` for the new acceptance document.

- [ ] **Step 3: Update operator packaging documentation**

Add a Windows 10/11 x64 section to `docs/packaging.md` with this exact command order, run from repository root unless the command changes directory:

```powershell
uv python install 3.12.13
uv sync --all-groups --locked
uv run python scripts/build_release.py --mode onefile
uv run python scripts/package_release.py
Set-Location desktop
pnpm install --frozen-lockfile
pnpm make
Set-Location ..
uv run python scripts/assemble_windows_release.py
pwsh -File scripts/verify_windows_release.ps1 `
  -ReleaseDirectory release/windows-x64 `
  -Mode All
```

Document all six final files, explain that `pnpm make` deliberately rebuilds/self-tests the current core, and state that a final artifact is valid only after the frozen six-check verify and PowerShell delivery verification pass on native Windows x64.

State explicitly:

- full JDK/Python/Node/pnpm are build-machine tools;
- final users receive embedded Python plus private `jlink` JRE/Worker/ExifTool;
- unsigned internal packages may display SmartScreen/unknown-publisher warnings;
- the child workflow is discovered by GitHub only when this directory is a repository root or the parent owner separately integrates it.

- [ ] **Step 4: Update README user-facing release instructions**

In `README.md`, keep the generic native core commands and add a short Windows subsection:

- Installer: run `DocumentMetadataInspector-<version>-win-x64-Setup.exe`.
- Portable: fully extract `DocumentMetadataInspector-<version>-win-x64-Portable.zip`, then run `docmeta-review.exe`; do not run inside the ZIP preview.
- CLI: reserve `DocumentMetadataInspector-<version>-win-x64-CLI.zip` for operations/support.
- Neither desktop variant uses system Python/Java/ExifTool or runtime downloads.
- Verify downloaded/copied bytes against `SHA256SUMS` before internal distribution.

- [ ] **Step 5: Create the manual Windows acceptance checklist**

Create `docs/windows-x64-release-acceptance.md` with checkboxes and fields for version, Git commit, Windows version, CPU, Defender status and SHA-256 result. It must require the operator to perform these actions on a clean Windows 10 or 11 x64 VM/account:

1. Confirm no usable Python, Java or ExifTool is present on `PATH`.
2. Keep Windows Defender enabled and record any detection separately from an unsigned-publisher/SmartScreen reputation warning.
3. Recalculate every `SHA256SUMS` record.
4. Run the automated verifier in `All` mode.
5. Install Setup, launch the GUI in at most 10 seconds, select controlled PDF/DOCX/XLSX from a Chinese/space/long-path directory, and reach actual parsing in at most 15 seconds.
6. Stop a scan and confirm no owned `docmeta.exe`, Java or ExifTool process remains.
7. Complete a scan and preserve its report only outside the repository.
8. Uninstall and confirm the controlled input/report still exists.
9. Extract Portable to a Chinese/space path, launch, scan, close, move the whole folder and repeat.
10. Change only a copied test instance of `resources/docmeta-runtime/docmeta.exe`, start a scan and confirm the stable “离线分析组件缺失或损坏” message; delete the copied test directory afterward.
11. Confirm installer and portable reports are semantically identical for the same inputs.
12. Record PASS/FAIL without recording usernames, hostnames, absolute document paths, report contents or credentials.

The checklist must say that generated packages, real documents and extraction reports are not committed to Git.

- [ ] **Step 6: Run documentation-contract and formatting checks**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py -v
git diff --check -- README.md docs/packaging.md docs/windows-x64-release-acceptance.md tests/unit/test_desktop_release_workflow.py
```

Expected: tests PASS and no whitespace errors.

- [ ] **Step 7: Commit Windows release documentation**

```bash
git add README.md docs/packaging.md docs/windows-x64-release-acceptance.md tests/unit/test_desktop_release_workflow.py
git commit -m "docs: document Windows dual release acceptance"
```

---

### Task 7: Run complete repository and native Windows release verification

**Files:**

- Verify only: no source file should change as a result of this task.
- Do not add generated `dist/`, `build/`, `release/`, `desktop/.runtime/`, `desktop/out/`, real documents or scan reports to Git.

**Interfaces:**

- Consumes: all committed implementation tasks.
- Produces: evidence-backed handoff that distinguishes cross-platform quality checks from the mandatory native Windows artifact result.

- [ ] **Step 1: Run the complete Python quality gate from the project root**

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
uv run docmeta verify
```

Expected: every command exits `0`; `docmeta verify` reports `passed: true` and six passing checks.

- [ ] **Step 2: Run the Java 21 Worker gate**

On Unix development systems:

```bash
cd java-worker
./mvnw --batch-mode --no-transfer-progress verify
cd ..
```

On Windows:

```powershell
Set-Location java-worker
.\mvnw.cmd --batch-mode --no-transfer-progress verify
Set-Location ..
```

Expected: Maven exits `0` with all Java tests passing.

- [ ] **Step 3: Run the complete Electron gate**

```bash
cd desktop
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
cd ..
```

Expected: all commands PASS.

- [ ] **Step 4: Build and assemble on native Windows x64**

On a Windows 10/11 x64 build machine, or the existing `windows-2025` matrix runner when its workflow is actually discoverable, run:

```powershell
uv python install 3.12.13
uv sync --all-groups --locked
uv run python scripts/build_release.py --mode onefile
uv run python scripts/package_release.py
Set-Location desktop
pnpm install --frozen-lockfile
pnpm make
Set-Location ..
uv run python scripts/assemble_windows_release.py
pwsh -File scripts/verify_windows_release.ps1 `
  -ReleaseDirectory release/windows-x64 `
  -Mode All
```

Expected: every command exits `0`; the output directory contains exactly the six specified files.

- [ ] **Step 5: Recalculate and inspect the final delivery metadata**

Run on Windows:

```powershell
$release = Resolve-Path release/windows-x64
Get-ChildItem -LiteralPath $release -File | Sort-Object Name | Select-Object Name, Length
Get-Content -LiteralPath (Join-Path $release "SHA256SUMS")
Get-Content -LiteralPath (Join-Path $release "BUILD-INFO.json") | ConvertFrom-Json |
    Select-Object schema_version, product_version, git_commit, target_platform, core_sha256
```

Expected: three normalized binary/archive names plus the three metadata/notice files; no user, host, path or credential fields appear in build info.

- [ ] **Step 6: Complete the manual Windows checklist**

Follow `docs/windows-x64-release-acceptance.md` on clean Windows 10 and Windows 11 x64 test environments. Record the result outside the repository or in the organization's release system; do not commit real files or reports.

If no native Windows x64 machine/runner is available, stop here and report that artifact completion is blocked. Do not claim Windows packages are built or verified based only on macOS/Linux tests.

- [ ] **Step 7: Confirm repository hygiene and hand off**

```bash
git status --short
git log --oneline -7
```

Expected: only known pre-existing user files may remain untracked; implementation source and documentation changes are committed; generated release/build directories are ignored or unstaged. Do not create an empty verification commit.

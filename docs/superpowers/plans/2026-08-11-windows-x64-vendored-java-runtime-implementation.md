# Windows x64 Vendored Java Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前分支把 Windows x64 Temurin JRE 21 与 Apache Worker JAR 作为受校验的 Git 二进制纳入构建，使目标电脑仅依赖已有的 `uv`、`nvm` 和 Windows 自带 PowerShell 5.1，即可通过一条命令生成安装版、便携版和 CLI 包。

**Architecture:** 先把现有 Windows x64 双发布分支合并到当前分支，再新增独立的 `windows_vendored_java.py` 边界，统一解析清单、校验 JRE/JAR、计算 Worker 输入树指纹、安全解压并缓存 JRE。Windows 原生 PyInstaller 路径和 macOS 交叉组装路径都消费这一边界；非 Windows x64 平台继续使用精确 JDK、Maven 和 `jlink`。维护者通过单独命令生成或更新二进制，目标 Windows 打包入口永远不下载 Java、不执行 Maven、不读取系统 Java 17。

**Tech Stack:** Python 3.12.13、uv、Temurin JRE/JDK 21.0.12+8、Maven Wrapper 3.9.11、PyInstaller 6.21.0、Node.js 24、Corepack、pnpm 11.10.0、Electron 43.3.0、Electron Forge 7.11.2、Windows PowerShell 5.1/PowerShell 7、pytest、Ruff、BasedPyright、Vitest、Biome。

## Global Constraints

- 实施分支固定为 `dev-yx/design-spec-style-polish-20260810`；不得创建替代功能分支。
- 先合并 `dev-yx/windows-x64-dual-release-20260811` 的既有 Windows x64 发布能力，并保留当前分支的自定义标题栏提交。
- 目标仅为 Windows 10/11 x64；不支持 Windows 7、Windows x86 或 Windows ARM64。
- 目标 Windows 构建机仅预装 `uv`、`nvm`；Windows PowerShell 5.1 是系统组件，不要求另装 PowerShell 7。
- 目标 Windows 构建机的 Java 17 不参与打包；不得读取、修改或依赖其 `JAVA_HOME`、PATH 或安装目录。
- Windows x64 打包不得下载 JRE/JDK、不得执行 Maven、不得回退到系统 Java 或旧的未验证缓存。
- Java Worker 和最终运行时继续使用 Eclipse Adoptium Temurin `21.0.12+8`，不迁移到 Java 17。
- Git 跟踪官方原始 Windows x64 JRE ZIP 和最终 shaded Worker JAR；不跟踪完整 JDK、Maven 缓存、解压 JRE、`target/`、`tools/build-cache/` 或最终发布包。
- 普通 Git blob 承载 ZIP/JAR，不使用 Git LFS；如果远程拒绝大对象，保留本地提交并报告原始服务端错误。
- `tools/manifest.json` 是版本、来源、路径、大小、SHA-256 和 Worker 输入树指纹的唯一权威清单。
- JRE/JAR 任一缺失、符号链接、大小错误、哈希错误、版本/架构错误或源码指纹失配时必须失败关闭。
- macOS 只静态验证 Windows JRE 的 `release` 文件和 PE 架构，不执行 Windows `java.exe`；Windows 原生构建必须实际执行内置 `java.exe` 复核版本。
- Windows x64 原生与 macOS 交叉组装必须使用同一组 Git JRE/JAR 字节。
- 最终用户仍不安装 Python、Java、ExifTool、Node.js、Office 或 LibreOffice，运行时也不联网下载。
- 不改变公共 Python 模型、JSON 协议、错误码、解析器来源、完整度状态或 Java Worker 的 JVM 全局网络拒绝边界。
- 不在本计划修复 `scan:start` 或 CMD 窗口闪现问题；等待新的 Windows 证据后独立处理。
- 每个行为变更先写失败测试，再写最小实现；每个任务独立提交，不暂存用户现有未跟踪文件。

---

## File and interface map

### Existing files to modify after branch integration

- `.gitattributes`：把 `tools/prebuilt/**/*.zip` 和 `tools/prebuilt/**/*.jar` 标记为 Git 二进制。
- `tools/manifest.json`：记录 Windows x64 vendored 路径、大小、哈希和 Worker 输入树指纹。
- `scripts/build_release.py`：Windows x64 选择 Git 内置 JRE/JAR；其他平台保留 JDK/Maven/`jlink`。
- `scripts/prepare_platform_resources.py`：接受显式 Apache 运行时来源；复制已验证 JRE 或从 JDK 执行 `jlink`。
- `scripts/windows_embedded_runtime.py`：移除 Windows JRE 在线取得和 Worker 现场编译，改用共享 vendored 边界。
- `scripts/verify_windows_release.ps1`：删除 PowerShell 7 专属 `ConvertFrom-Json -NoEnumerate`。
- `.github/workflows/build-offline-releases.yml`：CI 继续验证 Worker 源码，Windows 最终验证使用 PowerShell 5.1。
- `tests/unit/test_build_release.py`、`tests/unit/test_prepare_platform_resources.py`、`tests/unit/test_windows_embedded_runtime.py`、`tests/unit/test_desktop_release_workflow.py`：覆盖新路由与入口。
- `README.md`、`docs/packaging.md`、`docs/windows-x64-release-acceptance.md`、`tools/README.md`：记录唯一命令、缓存、二进制维护和验收。

### New focused files

- `scripts/build_apache_worker.py`：唯一 Maven Wrapper 构建适配器，供非 Windows 发布和维护命令复用。
- `scripts/windows_vendored_java.py`：唯一 vendored JRE/JAR 读取、校验、安全解压和缓存模块；同时提供验证 CLI。
- `scripts/vendor_windows_java.py`：维护者入口；取得官方 JRE、用精确 JDK 21 验证并生成 Worker、原子更新二进制和清单。
- `scripts/build_windows_x64.ps1`：目标 Windows 电脑的一键质量检查、打包、汇总和 `-Mode All` 验收入口。
- `tests/unit/test_build_apache_worker.py`、`tests/unit/test_windows_vendored_java.py`、`tests/unit/test_vendor_windows_java.py`：对应的窄范围测试。

### New tracked binary files

```text
tools/prebuilt/windows-x86_64/
├── OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip
└── document-metadata-apache-worker.jar
```

### Stable interfaces

```text
@dataclass(frozen=True, slots=True)
class VendoredWindowsJavaFiles:
    jre_archive: Path
    worker_jar: Path
    java_runtime_version: str
    jre_sha256: str
    worker_sha256: str


@dataclass(frozen=True, slots=True)
class PreparedWindowsJava:
    java_home: Path
    worker_jar: Path


worker_inputs_sha256(project_root: Path) -> str
verify_vendored_windows_java_files(project_root: Path) -> VendoredWindowsJavaFiles
prepare_vendored_windows_java(
    project_root: Path, cache: Path
) -> PreparedWindowsJava
```

```text
type JavaHomeKind = Literal["jdk", "jre"]


@dataclass(frozen=True, slots=True)
class ApacheRuntimeSources:
    java_home: Path
    worker_jar: Path
    java_home_kind: JavaHomeKind


build_worker(project_root: Path, java_home: Path) -> Path
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows_x64.ps1
```

总入口无必填参数，必须从 `$PSScriptRoot` 解析仓库根目录。成功时打印 `release/windows-x64`
六个正式文件的相对名称、字节数和 SHA-256；失败时打印最后阶段和异常并返回非零退出码。

---

### Task 1: Integrate the existing Windows x64 release branch

**Files:**

- Merge source: `dev-yx/windows-x64-dual-release-20260811`
- Preserve: `docs/superpowers/specs/2026-08-11-windows-x64-vendored-java-runtime-design.md`
- Verify: `tests/unit/test_windows_release.py`
- Verify: `tests/unit/test_windows_embedded_runtime.py`
- Verify: `tests/unit/test_windows_embedded_release.py`
- Verify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**

- Consumes: 当前标题栏提交 `e6fa885` 与 Windows 双发布提交 `8dd35d98`。
- Produces: 当前分支同时包含标题栏和完整 Windows x64 打包基础。

- [ ] **Step 1: Confirm merge ancestry and tracked cleanliness**

```bash
git status --short --branch
git merge-base --is-ancestor 2263d0f dev-yx/windows-x64-dual-release-20260811
git diff --name-only HEAD..dev-yx/windows-x64-dual-release-20260811
```

Expected: ancestry exits `0`; no tracked modification exists. Preserve all unrelated untracked files.

- [ ] **Step 2: Merge into the current branch**

```bash
git merge --no-ff dev-yx/windows-x64-dual-release-20260811 \
  -m "merge: integrate Windows x64 release pipeline"
```

Expected: one clean merge commit; current titlebar and vendored-Java spec remain present.

- [ ] **Step 3: Verify the merged Windows baseline**

```bash
uv run pytest \
  tests/unit/test_windows_release.py \
  tests/unit/test_windows_embedded_runtime.py \
  tests/unit/test_windows_embedded_release.py \
  tests/unit/test_desktop_release_workflow.py -q
```

Expected: all tests PASS before new behavior.

- [ ] **Step 4: Inspect merge scope**

```bash
git show --stat --oneline --summary HEAD
git status --short
```

Expected: merge has two parents; unrelated paths remain untracked.

---

### Task 2: Extract the Worker builder and validate vendored metadata

**Files:**

- Create: `scripts/build_apache_worker.py`
- Create: `scripts/windows_vendored_java.py`
- Create: `tests/unit/test_build_apache_worker.py`
- Create: `tests/unit/test_windows_vendored_java.py`
- Modify: `scripts/build_release.py`
- Modify: `tests/unit/test_build_release.py`

**Interfaces:**

- Consumes: `scripts.bootstrap_jdk.ensure_jdk()` and current Maven Wrapper.
- Produces: `build_worker()`, `worker_inputs_sha256()` and `verify_vendored_windows_java_files()`.
- Errors: malformed manifest raises `TypeError`; unsafe, missing, stale or tampered files raise `RuntimeError`.

- [ ] **Step 1: Write failing Worker builder tests**

Create `tests/unit/test_build_apache_worker.py` and assert the Windows command exactly:

```python
assert command == (
    r"C:\Windows\System32\cmd.exe",
    "/d",
    "/s",
    "/c",
    str(project / "java-worker/mvnw.cmd"),
    "--batch-mode",
    "--no-transfer-progress",
    "verify",
)
```

Also assert Unix uses `("sh", str(mvnw), "--batch-mode", "--no-transfer-progress", "verify")`,
nonzero exit raises `RuntimeError("the Apache Java worker build failed")`, and absent output raises
`RuntimeError("the Apache Java worker JAR is missing")`.

- [ ] **Step 2: Confirm the test fails before implementation**

```bash
uv run pytest tests/unit/test_build_apache_worker.py -v
```

Expected: import/collection FAIL because the module is absent.

- [ ] **Step 3: Implement the focused builder**

Create `scripts/build_apache_worker.py`. `build_worker()` must pass this overlay and a 1200-second timeout:

```python
environment = {
    **os.environ,
    "JAVA_HOME": str(java_home),
    "PATH": f"{java_home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
}
```

Return only a regular non-symlink
`java-worker/target/document-metadata-apache-worker.jar`. Delete `_maven_command()` and
`_build_worker()` from `build_release.py`, import `build_worker`, and move the command-processor test
from `test_build_release.py` to the focused test module.

- [ ] **Step 4: Write failing manifest and fingerprint tests**

Build a synthetic project in `test_windows_vendored_java.py`. Assert changes under each of
`pom.xml`, `mvnw`, `mvnw.cmd`, `.mvn/**`, `src/main/**` and `src/test/**` change
`worker_inputs_sha256()`. Assert timestamps and `target/` do not.

Define these exact fixture constants before the assertions:

```python
JRE_RELATIVE_PATH = Path(
    "tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip"
)
WORKER_RELATIVE_PATH = Path(
    "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar"
)
```

Add success assertions:

```python
files = verify_vendored_windows_java_files(project)
assert files.jre_archive == project / JRE_RELATIVE_PATH
assert files.worker_jar == project / WORKER_RELATIVE_PATH
assert files.java_runtime_version == "21.0.12+8"
```

Add failure tests for absent, empty, sparse-placeholder, absolute, escaping or symlink paths; wrong
size/hash/target/version; and stale Worker input hash. All must fail before extraction or subprocess
execution. On Windows, sparse detection uses `stat.FILE_ATTRIBUTE_SPARSE_FILE`; on Unix tests, use
`st_blocks * 512 < st_size` when `st_blocks` is available.

- [ ] **Step 5: Confirm metadata tests fail**

```bash
uv run pytest tests/unit/test_windows_vendored_java.py -v
```

Expected: FAIL because the interfaces and manifest fields are absent.

- [ ] **Step 6: Define the fail-closed schema in synthetic fixtures**

Use this schema in the temporary-project fixture; do not change the real `tools/manifest.json` until Task 5
can publish the schema and matching binaries together:

```json
{
  "apache_worker": {
    "vendored": {
      "windows-x86_64": {
        "path": "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar",
        "size": 0,
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "source_tree_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "artifact_version": "0.1.0",
        "build_java_runtime_version": "21.0.12+8",
        "build_command": ["mvnw", "--batch-mode", "--no-transfer-progress", "verify"]
      }
    }
  },
  "temurin_jre": {
    "archives": {
      "windows-x86_64": {
        "url": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12%2B8/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip",
        "sha256": "b8aa18fef5edb69bee8618f99677d66d0873d22cb40d974c15ac9ffcdecf73ba",
        "archive_type": "zip",
        "vendored_path": "tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip",
        "size": 0
      }
    }
  }
}
```

The fixture replaces zero values with the synthetic files' real sizes and hashes before invoking the verifier.
Separate negative tests deliberately retain a zero size or zero hash and require rejection.

- [ ] **Step 7: Implement metadata validation**

In `windows_vendored_java.py`, implement strict JSON type checks, project-root-relative path resolution,
regular non-symlink checks, streaming SHA-256 and NUL-delimited sorted Worker input hashing. The input tree
is exactly `pom.xml`, both wrappers, `.mvn`, `src/main` and `src/test`; reject any symlink.

- [ ] **Step 8: Verify and commit**

```bash
uv run pytest \
  tests/unit/test_build_apache_worker.py \
  tests/unit/test_windows_vendored_java.py \
  tests/unit/test_build_release.py -q
uv run ruff check scripts/build_apache_worker.py scripts/windows_vendored_java.py \
  tests/unit/test_build_apache_worker.py tests/unit/test_windows_vendored_java.py
uv run basedpyright scripts/build_apache_worker.py scripts/windows_vendored_java.py
git add scripts/build_apache_worker.py scripts/windows_vendored_java.py \
  scripts/build_release.py \
  tests/unit/test_build_apache_worker.py tests/unit/test_windows_vendored_java.py \
  tests/unit/test_build_release.py
git commit -m "feat: validate vendored Windows Java inputs"
```

Expected: checks PASS; the existing real manifest and release flow remain unchanged until Task 5.

---

### Task 3: Safely materialize and cache the JRE

**Files:**

- Modify: `scripts/windows_vendored_java.py`
- Modify: `tests/unit/test_windows_vendored_java.py`

**Interfaces:**

- Consumes: `verify_vendored_windows_java_files()`.
- Produces: `prepare_vendored_windows_java(project_root, cache) -> PreparedWindowsJava`.
- Cache: `cache/{64-character-input-sha256}/jre/` and `integrity.json`; invalid cache rebuilds transactionally from Git ZIP.

- [ ] **Step 1: Add archive and provenance tests**

Create a ZIP with:

```text
jdk-21.0.12+8-jre/bin/java.exe
jdk-21.0.12+8-jre/bin/server/jvm.dll
jdk-21.0.12+8-jre/release
jdk-21.0.12+8-jre/legal/java.base/LICENSE
```

Use these exact release markers:

```text
IMPLEMENTOR="Eclipse Adoptium"
JAVA_RUNTIME_VERSION="21.0.12+8-LTS"
OS_ARCH="x86_64"
OS_NAME="Windows"
IMAGE_TYPE="JRE"
```

Construct minimal AMD64 PE bytes using `MZ`, a PE offset at `0x3c`, `PE\0\0` and machine `0x8664`.
Assert valid preparation returns the one JRE home and the verified Git JAR, and preserves the legal file
byte-for-byte.

Add tests rejecting `../outside`, drive paths, case-insensitive duplicates, ZIP symlinks, member/expanded-byte
budget excess, missing/duplicate JRE homes, non-AMD64 Java, and wrong release markers.

- [ ] **Step 2: Add cache and native execution tests**

Prepare once, tamper cached `bin/java.exe`, prepare again, and assert bytes are restored from the Git ZIP.
Change the input fingerprint and assert a new cache path.

For native Windows, monkeypatch the platform predicate and require:

```python
(
    str(java_home / "bin/java.exe"),
    "-XshowSettings:properties",
    "-version",
)
```

Require a 15-second timeout, at most 64 KiB combined captured output, return code `0`, and the expected
vendor/version. Assert static macOS validation never calls subprocess.

- [ ] **Step 3: Confirm new tests fail**

```bash
uv run pytest tests/unit/test_windows_vendored_java.py -v
```

Expected: extraction, malicious archive and cache tests FAIL.

- [ ] **Step 4: Implement bounded extraction and cache publication**

Implement:

```text
_extract_windows_jre(archive: Path, destination: Path) -> None
_find_windows_jre_home(root: Path, expected_version: str) -> Path
_require_amd64_pe(path: Path) -> None
_cache_fingerprint(files: VendoredWindowsJavaFiles) -> str
_cached_jre_is_valid(cache: Path, fingerprint: str) -> Path | None
_verify_native_windows_java(java_home: Path, expected_version: str) -> None
```

Use the existing limits of at most 50,000 ZIP entries and at most 4 GiB total declared expanded bytes.
Validate every member before creating output, write files with exclusive creation, write/fsync an integrity
record, and use `Path.replace()` only after full tree verification. Do not use `ZipFile.extract()` or
`extractall()`.

- [ ] **Step 5: Implement the public function and CLI**

```python
def prepare_vendored_windows_java(
    project_root: Path,
    cache: Path,
) -> PreparedWindowsJava:
    files = verify_vendored_windows_java_files(project_root)
    java_home = _materialize_verified_jre(files, cache)
    if os.name == "nt":
        _verify_native_windows_java(java_home, files.java_runtime_version)
    return PreparedWindowsJava(java_home=java_home, worker_jar=files.worker_jar)
```

CLI:

```bash
uv run python scripts/windows_vendored_java.py \
  --cache tools/build-cache/windows-vendored-java
```

Print only repository-relative paths and hashes.

- [ ] **Step 6: Verify and commit**

```bash
uv run pytest tests/unit/test_windows_vendored_java.py -q
uv run ruff check scripts/windows_vendored_java.py tests/unit/test_windows_vendored_java.py
uv run ruff format --check scripts/windows_vendored_java.py \
  tests/unit/test_windows_vendored_java.py
uv run basedpyright scripts/windows_vendored_java.py
git add scripts/windows_vendored_java.py tests/unit/test_windows_vendored_java.py
git commit -m "feat: materialize vendored Windows JRE safely"
```

---

### Task 4: Route native and cross-package Windows builds through vendored Java

**Files:**

- Modify: `scripts/prepare_platform_resources.py`
- Modify: `scripts/build_release.py`
- Modify: `scripts/windows_embedded_runtime.py`
- Modify: `tests/unit/test_prepare_platform_resources.py`
- Modify: `tests/unit/test_build_release.py`
- Modify: `tests/unit/test_windows_embedded_runtime.py`

**Interfaces:**

- Consumes: `PreparedWindowsJava` and `build_worker()`.
- Produces: both Windows build routes copy the same Git JRE/JAR; other platforms still build JAR and `jlink`.
- Prepare interface: `prepare(apache_sources, exiftool_runtime, exiftool_command, *, replace_existing=False)`.

- [ ] **Step 1: Write failing explicit-source tests**

In `test_prepare_platform_resources.py`, pass:

```python
ApacheRuntimeSources(
    java_home=prebuilt_jre,
    worker_jar=worker_jar,
    java_home_kind="jre",
)
```

Make `_build_jre` raise if called; assert exact JRE/JAR copy and manifest hashes. Keep a `java_home_kind="jdk"`
test requiring one `_build_jre` call.

In `test_build_release.py`, add a Windows test where `ensure_jdk()` and `build_worker()` raise if called,
`prepare_vendored_windows_java()` returns controlled paths, and `prepare()` receives kind `jre`. Add a Darwin
test requiring `ensure_jdk()`/`build_worker()` once and kind `jdk`.

Update `test_windows_embedded_runtime.py` to mock only `prepare_vendored_windows_java()` for Java and require
the legacy `_acquire_windows_jre`/`_build_apache_worker` names to disappear.

- [ ] **Step 2: Confirm old routing fails**

```bash
uv run pytest \
  tests/unit/test_prepare_platform_resources.py \
  tests/unit/test_build_release.py \
  tests/unit/test_windows_embedded_runtime.py -q
```

Expected: FAIL because explicit sources and vendored routing are absent.

- [ ] **Step 3: Add explicit Apache sources**

In `prepare_platform_resources.py`, add `JavaHomeKind` and `ApacheRuntimeSources`. Use:

```python
if sources.java_home_kind == "jdk":
    java = _build_jre(sources.java_home.resolve(), apache / "jre", staging.parent)
elif sources.java_home_kind == "jre":
    _copy_tree(sources.java_home.resolve(), apache / "jre")
    java = apache / "jre/bin/java.exe"
    if java.is_symlink() or not java.is_file():
        raise RuntimeError("the vendored Java runtime is missing java.exe")
else:
    raise ValueError("the Java home kind is unsupported")
_ = shutil.copy2(sources.worker_jar, apache / "worker.jar")
```

Remove implicit `_WORKER_JAR` access.

- [ ] **Step 4: Select vendored Java on native Windows only**

In `build_release.py`:

```python
key = platform_key()
if key == "windows-x86_64":
    vendored = prepare_vendored_windows_java(
        _PROJECT_ROOT,
        _BUILD_CACHE / "windows-vendored-java",
    )
    apache = ApacheRuntimeSources(vendored.java_home, vendored.worker_jar, "jre")
else:
    java_home = ensure_jdk(_BUILD_CACHE / "temurin")
    worker_jar = build_worker(_PROJECT_ROOT, java_home)
    apache = ApacheRuntimeSources(java_home, worker_jar, "jdk")
```

Pass `apache` into `prepare()`. Preserve ExifTool, manifest restoration, frozen build and resource resolution.

- [ ] **Step 5: Select vendored Java in cross-packaging**

In `windows_embedded_runtime.py`, import `prepare_vendored_windows_java`, delete JRE download/build functions
and their unused download helpers, then:

```python
java = prepare_vendored_windows_java(project_root, cache / "vendored-java")
```

Pass `java.java_home` and `java.worker_jar` into `WindowsRuntimeSources`. Preserve Python, ExifTool,
inventory and atomic assembly.

- [ ] **Step 6: Verify and commit**

```bash
uv run pytest \
  tests/unit/test_prepare_platform_resources.py \
  tests/unit/test_build_release.py \
  tests/unit/test_windows_embedded_runtime.py \
  tests/unit/test_windows_embedded_release.py -q
uv run ruff check scripts/prepare_platform_resources.py scripts/build_release.py \
  scripts/windows_embedded_runtime.py
uv run basedpyright scripts/prepare_platform_resources.py scripts/build_release.py \
  scripts/windows_embedded_runtime.py
git add scripts/prepare_platform_resources.py scripts/build_release.py \
  scripts/windows_embedded_runtime.py tests/unit/test_prepare_platform_resources.py \
  tests/unit/test_build_release.py tests/unit/test_windows_embedded_runtime.py
git commit -m "build: use vendored Java for Windows x64"
```

---

### Task 5: Add atomic vendoring and commit JRE/JAR

**Files:**

- Create: `scripts/vendor_windows_java.py`
- Create: `tests/unit/test_vendor_windows_java.py`
- Modify: `.gitattributes`
- Modify: `tools/manifest.json`
- Create: `tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip`
- Create: `tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar`

**Interfaces:**

- Consumes: `ensure_jdk()`, `build_worker()`, `worker_inputs_sha256()` and official JRE configuration.
- Produces: transactional maintenance command plus tracked bytes.
- Failure: old ZIP, JAR and manifest stay byte-identical on download/build/hash/publication failure.

- [ ] **Step 1: Write failing transaction tests**

In `test_vendor_windows_java.py`, use sentinel prior files. On success assert downloaded JRE and built JAR
bytes plus manifest sizes/hashes. Add failures for wrong official hash, Maven failure, missing shaded JAR and
manifest publication error; assert all three previous files remain unchanged.

- [ ] **Step 2: Confirm tests fail**

```bash
uv run pytest tests/unit/test_vendor_windows_java.py -v
```

Expected: import FAIL because module is absent.

- [ ] **Step 3: Implement the maintenance command**

`vendor_windows_java(project_root, cache)` must:

1. strictly read official JRE URL/hash/type;
2. stream download to `cache/downloads/*.download` and validate SHA-256;
3. obtain exact JDK through `ensure_jdk(cache / "temurin")`;
4. run `build_worker()` and require Maven `verify`;
5. stage both binaries and a complete new manifest privately;
6. add the Task 2 vendored schema to the staged manifest with real sizes, SHA-256 and Worker input hash;
7. fsync and atomically publish both binaries plus the real manifest with rollback;
8. call `verify_vendored_windows_java_files()` after publication.

CLI:

```bash
uv run python scripts/vendor_windows_java.py \
  --cache tools/build-cache/windows-java-vendor
```

Print only relative paths, sizes and hashes.

- [ ] **Step 4: Add binary attributes**

Append without LFS filters:

```gitattributes
tools/prebuilt/**/*.jar binary
tools/prebuilt/**/*.zip binary
```

- [ ] **Step 5: Verify unit behavior**

```bash
uv run pytest \
  tests/unit/test_vendor_windows_java.py \
  tests/unit/test_windows_vendored_java.py \
  tests/unit/test_build_apache_worker.py -q
uv run ruff check scripts/vendor_windows_java.py tests/unit/test_vendor_windows_java.py
uv run basedpyright scripts/vendor_windows_java.py
```

- [ ] **Step 6: Generate and verify real artifacts**

```bash
uv run python scripts/vendor_windows_java.py \
  --cache tools/build-cache/windows-java-vendor
uv run python scripts/windows_vendored_java.py \
  --cache tools/build-cache/windows-vendored-java
```

Expected: JRE SHA-256 is
`b8aa18fef5edb69bee8618f99677d66d0873d22cb40d974c15ac9ffcdecf73ba`; Worker is nonempty
and approximately 57 MiB; the real manifest contains no bootstrap zero values; Maven tests passed.

- [ ] **Step 7: Inspect and commit exact files**

```bash
git check-attr -a -- \
  tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip \
  tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar
git status --short
git diff --check
git add .gitattributes tools/manifest.json scripts/vendor_windows_java.py \
  tests/unit/test_vendor_windows_java.py \
  tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip \
  tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar
git commit -m "build: vendor Windows x64 Java runtime"
```

Expected attributes: `diff`, `merge`, `text` are unset; caches and release files stay unstaged.

- [ ] **Step 8: Test the remote binary limit immediately**

```bash
git push origin dev-yx/design-spec-style-polish-20260810
git ls-remote --heads origin dev-yx/design-spec-style-polish-20260810
```

Expected: remote hash equals local. If rejected, stop remote delivery, retain the local commit and report the
original server response; never split, encode or relocate binaries.

---

### Task 6: Add the uv+nvm PowerShell 5.1 build entry

**Files:**

- Create: `scripts/build_windows_x64.ps1`
- Modify: `scripts/verify_windows_release.ps1`
- Modify: `.github/workflows/build-offline-releases.yml`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**

- Consumes: existing release commands and vendored verifier.
- Produces: zero-argument one-command build using only `uv`, `nvm`, built-in PowerShell and non-Java downloads.
- Contract: check every native `$LASTEXITCODE`; use no PowerShell 7-only syntax.

- [ ] **Step 1: Write failing source-contract tests**

Require `build_windows_x64.ps1` to contain:

```python
for required in (
    "Set-StrictMode -Version Latest",
    '$ErrorActionPreference = "Stop"',
    "Get-Command uv",
    "Get-Command nvm",
    '"install", "24"',
    '"use", "24"',
    "pnpm@11.10.0",
    '"python", "install", "3.12.13"',
    "windows_vendored_java.py",
    '"pnpm", "make"',
    "assemble_windows_release.py",
    "verify_windows_release.ps1",
    '"All"',
):
    assert required in source
assert "mvnw" not in source
assert "JAVA_HOME" not in source
assert "bootstrap_jdk.py" not in source
```

Require `-NoEnumerate`, `ForEach-Object -Parallel`, `??`, `?.` and ternary syntax absent from both PS1
files. Require workflow verifier command `powershell.exe -NoProfile -File`.

- [ ] **Step 2: Confirm tests fail**

```bash
uv run pytest \
  tests/unit/test_desktop_release_workflow.py::test_windows_one_command_build_uses_uv_nvm_and_vendored_java \
  tests/unit/test_desktop_release_workflow.py::test_windows_scripts_support_powershell_51 -v
```

Expected: entry missing and verifier still uses `-NoEnumerate`.

- [ ] **Step 3: Make verifier 5.1-compatible**

Replace both:

```powershell
$jsonText | ConvertFrom-Json -NoEnumerate
```

with:

```powershell
ConvertFrom-Json -InputObject $jsonText
```

Preserve all timeout, process-tree, hash, installer and ownership semantics.

- [ ] **Step 4: Implement checked native execution**

Create `build_windows_x64.ps1`:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$LastStage = "startup"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "Native command failed with exit code $exitCode: $FilePath"
        }
    }
    finally {
        Pop-Location
    }
}
```

Wrap stages in `try/catch`; update `$LastStage`, use `Write-Error`, exit `1`, and never print full environment.

- [ ] **Step 5: Configure preflight and project caches**

Require 64-bit Windows, `uv`, `nvm`; run `nvm install 24`, `nvm use 24`, and require `node --version`
matches `^v24\.`.

```powershell
$BuildCache = Join-Path $ProjectRoot "tools\build-cache"
$env:UV_CACHE_DIR = Join-Path $BuildCache "uv"
$env:COREPACK_HOME = Join-Path $BuildCache "corepack"
$env:electron_config_cache = Join-Path $BuildCache "electron"
$PnpmStore = Join-Path $BuildCache "pnpm-store"
```

Use Corepack directly:

```powershell
corepack install --global pnpm@11.10.0
corepack pnpm --version
```

Require exactly `11.10.0`.

- [ ] **Step 6: Implement one final frozen build**

Run through `Invoke-NativeCommand`:

```text
uv python install 3.12.13
uv sync --all-groups --locked
uv run python scripts/windows_vendored_java.py --cache tools/build-cache/windows-vendored-java
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
corepack pnpm install --frozen-lockfile --store-dir $PnpmStore  [desktop]
corepack pnpm test                                             [desktop]
corepack pnpm typecheck                                        [desktop]
corepack pnpm lint                                             [desktop]
corepack pnpm format:check                                     [desktop]
corepack pnpm build                                            [desktop]
corepack pnpm make                                             [desktop]
uv run python scripts/package_release.py
uv run python scripts/assemble_windows_release.py
```

Do not separately call `build_release.py`: `pnpm make` already calls `prepare-runtime.mjs`, performs the
final clean onefile build and six checks.

Invoke final verification in-process:

```powershell
& (Join-Path $ProjectRoot "scripts\verify_windows_release.ps1") `
    -ReleaseDirectory (Join-Path $ProjectRoot "release\windows-x64") `
    -Mode All
```

Print relative release names, byte counts and lowercase hashes after success.

- [ ] **Step 7: Align CI and verify**

Keep CI JDK/Maven source verification. Change Windows final verifier to:

```yaml
run: powershell.exe -NoProfile -File scripts/verify_windows_release.ps1 -ReleaseDirectory release/windows-x64 -Mode All
```

Then:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py -q
git diff --check -- scripts/build_windows_x64.ps1 \
  scripts/verify_windows_release.ps1 .github/workflows/build-offline-releases.yml
git add scripts/build_windows_x64.ps1 scripts/verify_windows_release.ps1 \
  .github/workflows/build-offline-releases.yml tests/unit/test_desktop_release_workflow.py
git commit -m "build: add one-command Windows x64 release"
```

macOS source checks do not replace native Windows execution.

---

### Task 7: Document the target workflow and maintenance boundary

**Files:**

- Modify: `README.md`
- Modify: `docs/packaging.md`
- Modify: `docs/windows-x64-release-acceptance.md`
- Modify: `tools/README.md`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**

- Consumes: final Task 5–6 commands.
- Produces: one copy/paste Windows command, cache behavior, maintenance instructions and minimal diagnostics.

- [ ] **Step 1: Write failing doc-contract tests**

Require the Windows section to include:

```python
for fragment in (
    "powershell.exe -NoProfile -ExecutionPolicy Bypass",
    ".\\scripts\\build_windows_x64.ps1",
    "PowerShell 5.1",
    "OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip",
    "document-metadata-apache-worker.jar",
    "tools/build-cache",
    "不使用系统 Java 17",
):
    assert fragment in windows_packaging
```

Require old native commands `build_release.py --mode onefile` and `java-worker/mvnw.cmd` absent from that
section. Require acceptance to use `powershell.exe` and record whether Java download URLs were contacted.

- [ ] **Step 2: Confirm old docs fail**

```bash
uv run pytest \
  tests/unit/test_desktop_release_workflow.py::test_windows_dual_release_documentation_matches_the_build_commands -v
```

- [ ] **Step 3: Write the one-command quick start**

In `docs/packaging.md`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows_x64.ps1
```

Document:

- preinstalled: `uv`, `nvm`, PowerShell 5.1;
- Git-provided: JRE ZIP and Worker JAR;
- first-run downloads: Python 3.12.13, Node 24, pnpm 11.10.0, Python/Node/Electron dependencies, ExifTool;
- never used: system Java 17, system Python, Maven on target;
- caches: `tools/build-cache/uv`, `corepack`, `pnpm-store`, `electron`, `windows-vendored-java`;
- final six files under `release/windows-x64`.

- [ ] **Step 4: Document maintenance and acceptance**

In `tools/README.md`:

```bash
uv run python scripts/vendor_windows_java.py \
  --cache tools/build-cache/windows-java-vendor
```

Explain exact JDK 21, Maven verify, official JRE hash, source fingerprint and why target builds never run it.

Replace `pwsh` with `powershell.exe -NoProfile` in acceptance; permit installed Java 17 to remain while proving
logs have no system Java path; require disconnected app verification. Add explicit checklist items to:

1. clear `JAVA_HOME` and remove Java entries from PATH only in the current test process;
2. confirm the build does not contact a Java/JDK download URL;
3. delete `tools/build-cache/windows-vendored-java` and rebuild Java resources from Git while offline;
4. modify one byte in a disposable copy of the committed Worker JAR, confirm preflight fails before packaging,
   then restore the tracked file with `git restore`;
5. retain only stage name, exit code and non-sensitive hash evidence.

Document the binary refresh triggers: any Java production source, test, POM, Wrapper, dependency/plugin,
Worker version or Temurin patch change requires rerunning `vendor_windows_java.py`; Python/UI-only changes do
not.

Update README: Windows x64 uses verified vendored Java; other native platforms retain source build/`jlink`.

- [ ] **Step 5: Verify and commit docs**

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py -q
git diff --check -- README.md docs/packaging.md \
  docs/windows-x64-release-acceptance.md tools/README.md
git add README.md docs/packaging.md docs/windows-x64-release-acceptance.md \
  tools/README.md tests/unit/test_desktop_release_workflow.py
git commit -m "docs: explain vendored Windows Java build"
```

---

### Task 8: Complete verification, cross-package smoke test and push

**Files:**

- Verify: all changed tracked files.
- Ignore: `tools/build-cache/**`, `tools/packaged/**`, `java-worker/target/**`, `release/**`, `desktop/out/**`.

**Interfaces:**

- Consumes: every prior task.
- Produces: passing Mac-available gates, structural Windows cross-package evidence and exact remote hash.
- Limitation: the user's external x64 computer remains the native installation/scan gate.

- [ ] **Step 1: Verify vendored bytes and Java source**

```bash
uv run python scripts/windows_vendored_java.py \
  --cache tools/build-cache/windows-vendored-java
uv run python scripts/bootstrap_jdk.py --cache tools/build-cache/temurin
```

Capture the printed path as `DOCMETA_TASK_JAVA_HOME`, then:

```bash
JAVA_HOME="$DOCMETA_TASK_JAVA_HOME" \
PATH="$DOCMETA_TASK_JAVA_HOME/bin:$PATH" \
./java-worker/mvnw --batch-mode --no-transfer-progress verify
```

Expected: Java tests PASS and rebuilt shaded JAR hash equals the committed JAR. A mismatch blocks completion.

- [ ] **Step 2: Run the complete Python gate**

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
uv run docmeta verify
```

- [ ] **Step 3: Run the complete desktop gate**

```bash
cd desktop
pnpm install --frozen-lockfile
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
cd ..
```

- [ ] **Step 4: Cross-package a Windows smoke release**

```bash
uv run python scripts/windows_embedded_release.py \
  --output-directory release/windows-x64-vendored-smoke \
  --cache tools/build-cache/windows-embedded
```

Expected: setup/portable output, complete inventory, all PE files AMD64, and package JRE/JAR hashes equal Git.
Record this as structural evidence only.

- [ ] **Step 5: Review scope**

```bash
git diff --check
git status --short
git ls-files tools/prebuilt/windows-x86_64
git check-attr -a -- tools/prebuilt/windows-x86_64/*
```

Expected: exactly two prebuilt files; cache/release/target stay ignored; unrelated files remain unstaged.

- [ ] **Step 6: Request final code review**

Use `superpowers:requesting-code-review`. Check no Windows Java download/build/fallback, fail-closed
manifest/fingerprint, safe extraction, cache integrity, non-Windows behavior, PowerShell 5.1 and tracked scope.
For each concrete issue, first add a failing regression test, make the minimum fix, rerun the affected gate and
commit a scoped `fix:` change.

- [ ] **Step 7: Push and verify remote identity**

```bash
git push origin dev-yx/design-spec-style-polish-20260810
git rev-parse HEAD
git ls-remote --heads origin dev-yx/design-spec-style-polish-20260810
```

Expected: hashes equal. Do not open a merge request without a request.

- [ ] **Step 8: Hand off exact Windows commands**

```powershell
git fetch origin
git switch dev-yx/design-spec-style-polish-20260810
git pull --ff-only origin dev-yx/design-spec-style-polish-20260810
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows_x64.ps1
```

On failure request only `git rev-parse HEAD`, `uv --version`, `nvm version`, `node --version`, the printed
stage/error/exit code, and optional `release/windows-x64/BUILD-INFO.json`. Never request an environment dump,
username, absolute document path or document contents.

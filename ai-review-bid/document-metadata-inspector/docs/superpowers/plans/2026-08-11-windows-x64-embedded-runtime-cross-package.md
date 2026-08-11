# Windows x64 Embedded Runtime Cross-Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows 10/11 x64 application whose installed Electron
`resources` already contain Python 3.12.13, project dependencies and source,
Temurin JDK 21, the Java Worker, and ExifTool.

**Architecture:** A Python assembler running on macOS downloads a relocatable
Windows x64 CPython through `uv`, installs only locked `win_amd64` wheels, and
materializes the existing pinned Java/ExifTool resources into one
`desktop/.runtime/docmeta-runtime` tree. Electron resolves the tree's
`python.exe` as its packaged command and copies the entire tree with
`extraResource`; the identical packaged directory feeds both portable ZIP and
Windows installer outputs.

**Tech Stack:** Python 3.12, uv 0.11+, Electron 43 / Electron Forge 7,
TypeScript, Vitest, pytest, Temurin 21, and native macOS NSIS.

## Global Constraints

- Target only Windows 10/11 x64 (`windows-x86_64` / `win32-x64`).
- End users install or unzip once; they never install or locate Python, Java,
  ExifTool, or project files.
- Bundle Python 3.12.13 and Temurin JDK 21.0.12+8 exactly.
- Install Python dependencies from `uv.lock` as binary Windows x64 wheels;
  fail if a source build would be required.
- Keep `PYTHONHOME` and `PYTHONPATH` cleared at runtime.
- Every network artifact is version-pinned and integrity-checked before use.
- Do not modify neighboring projects or unrelated lint debt.
- Do not start, access, or modify Parallels or any Windows guest.

---

### Task 1: Packaged Embedded-Python Runtime Contract

**Files:**
- Modify: `desktop/src/main/runtime-resolver.ts`
- Modify: `desktop/packaged-runtime-integrity.mts`
- Modify: `desktop/vite.main.config.mts`
- Test: `desktop/tests/runtime-resolver.test.ts`
- Test: `desktop/tests/packaged-runtime-integrity.test.ts`

**Interfaces:**
- Consumes: `resources/docmeta-runtime/{docmeta.exe|python.exe}` and its
  one-record `SHA256SUMS`.
- Produces: `resolveDocmetaCommand()` returning embedded Python with
  `argsPrefix: ["-I", "-s", "-m", "document_metadata_inspector.cli"]`, while
  retaining the existing native one-file behavior.

- [ ] Add a Vitest case with a real temporary runtime containing `python.exe`,
  `app/src/document_metadata_inspector/cli.py`, and a matching `SHA256SUMS`;
  assert the exact command, prefix, source, and working directory.
- [ ] Run `pnpm test -- runtime-resolver.test.ts` and confirm the new case fails
  because packaged mode still requires `docmeta.exe`.
- [ ] Implement launcher discovery that accepts exactly one supported packaged
  layout, verifies the selected executable, and never falls back to `uv`.
- [ ] Add real post-package integrity cases for embedded Python success,
  missing application entry point, and tampered `python.exe`.
- [ ] Run focused Vitest, desktop typecheck, and scoped Biome checks.
- [ ] Commit the task as `feat: resolve embedded Windows Python runtime`.

### Task 2: Cross-Platform Windows Runtime Assembler

**Files:**
- Create: `scripts/windows_embedded_runtime.py`
- Create: `tests/unit/test_windows_embedded_runtime.py`
- Modify: `tools/manifest.json`
- Reuse: `scripts/bootstrap_jdk.py`
- Reuse: `scripts/build_windows_exiftool.py`

**Interfaces:**
- Produces:
  `build_windows_embedded_runtime(project_root: Path, destination: Path,
  cache: Path) -> Path`.
- The destination contains root `python.exe`, `Lib/site-packages`,
  `app/src`, `app/tools/manifest.json`, Windows packaged Java/Worker/ExifTool,
  `SHA256SUMS`, `RUNTIME-INFO.json`, notices, and licenses.

- [ ] Write pytest fixtures for a synthetic relocatable Python tree, JDK ZIP,
  ExifTool tree, Worker JAR, and locked dependency target.
- [ ] Add failing tests proving the assembler copies all required resources,
  writes a data-only `docmeta-app.pth` with `../../app/src`, and records only
  application-relative paths.
- [ ] Add failing tests proving a missing Windows wheel, wrong Python target,
  unsafe archive member, missing Worker, or hash mismatch leaves no published
  destination.
- [ ] Run the focused pytest file and confirm failures are caused by the absent
  module/API.
- [ ] Implement the minimal assembler with atomic staging, safe archive
  extraction, `uv python install
  cpython-3.12.13-windows-x86_64-none`, locked `uv export`, and `uv pip install
  --python-platform x86_64-pc-windows-msvc --only-binary :all:`.
- [ ] Generate a release-local tool manifest whose Windows x64 Java, Worker,
  and ExifTool entries cover every included file by SHA-256.
- [ ] Generate root launcher checksum and runtime metadata; publish only after
  the exact required tree is complete.
- [ ] Run focused pytest, scoped Ruff format/check, scoped BasedPyright, and
  `git diff --check`.
- [ ] Commit the task as `feat: assemble embedded Windows x64 runtime`.

### Task 3: Mac-to-Windows Portable Application Build

**Files:**
- Create: `scripts/build_windows_embedded_release.py`
- Modify: `desktop/package.json`
- Modify: `desktop/forge.config.ts`
- Test: `tests/unit/test_windows_embedded_release.py`

**Interfaces:**
- Produces:
  `release/windows-embedded-x64/DocumentMetadataInspector-0.1.0-win-x64-Portable.zip`
  and the unpacked application directory.
- Consumes the Task 2 runtime tree and runs Electron Forge with target
  `--platform win32 --arch x64` without invoking PyInstaller.

- [ ] Add failing orchestration tests asserting Task 2 runs before Forge,
  Forge receives explicit Windows x64 target flags, and publication refuses a
  packaged application without `resources/docmeta-runtime/python.exe`.
- [ ] Implement the thin CLI/orchestrator and a dedicated desktop package
  command that bypasses `prepare-runtime.mjs`.
- [ ] Zip the complete packaged application with a single top-level directory,
  deterministic sorted paths, and `SHA256SUMS`/`BUILD-INFO.json` beside it.
- [ ] Run focused pytest/Vitest, desktop typecheck, scoped format/lint, and
  `git diff --check`.
- [ ] Commit the task as `build: cross-package embedded Windows application`.

### Task 4: Download, Build, and Mac-Side Release Verification

**Files:**
- Generated only: `tools/build-cache/**`, `desktop/.runtime/**`,
  `desktop/out/**`, `release/windows-embedded-x64/**`
- Create: `desktop/installer/windows-x64.nsi`
- Update: `docs/packaging.md`

**Interfaces:**
- Consumes the Task 3 CLI.
- Produces an actual portable Windows x64 ZIP and a native-NSIS-built
  `DocumentMetadataInspector-0.1.0-win-x64-Setup.exe` containing the identical
  application tree.

- [ ] Run `uv run python scripts/build_windows_embedded_release.py` on macOS;
  allow it to download only the selected pinned Windows x64 artifacts and
  wheels.
- [ ] Inspect the generated ZIP and verify Python, JDK, Worker, ExifTool,
  source packages, manifests, and notices are all inside the installed
  application resources.
- [ ] Compile `desktop/installer/windows-x64.nsi` with native macOS `makensis`;
  do not invoke Parallels, Wine, Squirrel, or any Windows command.
- [ ] Inspect every executable PE header and require AMD64, verify the portable
  ZIP and installer hashes, and prove the runtime inventory is complete.
- [ ] Record native launch/install verification as pending for the user's later
  Windows x64 computer; do not claim it from macOS-only evidence.
- [ ] Run the repository's relevant focused suites, full pytest, full desktop
  tests/typecheck, Java Worker verify, lock check, build, and diff checks.
- [ ] Update documentation with the one-command build and exact output paths;
  commit as `docs: document embedded Windows release build`.

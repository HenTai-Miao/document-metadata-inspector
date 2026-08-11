# Windows x64 Embedded Runtime Cross-Package Design

## Outcome

Produce **文档元数据核验** for Windows 10/11 x64 with every runtime file
inside the application. An end user installs or unzips the product and starts
it directly. They never install Python, Java, ExifTool, or place files beside
the application manually.

The build starts on the current macOS host. Parallels is reserved for running
the finished Windows files and, if necessary, wrapping the already-complete
application directory in an installer. No Python, Java, or Node build
environment is installed into the Windows guest.

## Selected Approach

Use a directory-based embedded runtime instead of PyInstaller for the Windows
x64 target.

Two alternatives were rejected:

1. Keep PyInstaller one-file. This is already supported, but it requires a
   Windows Python build and is the reason the current macOS host cannot produce
   the Windows core.
2. Require a system Python/JDK. This makes packaging simpler but violates the
   zero-install end-user requirement.

The directory runtime is larger than a PyInstaller one-file executable, but it
is simpler to cross-assemble, transparent to audit, and appropriate for an
internal offline release.

## Installed Application Layout

Electron Forge copies the entire `docmeta-runtime` directory through
`packagerConfig.extraResource`. After installation, the relevant layout is:

```text
文档元数据核验/
├── 文档元数据核验.exe
└── resources/
    └── docmeta-runtime/
        ├── python/
        │   ├── python.exe
        │   ├── python312.dll
        │   ├── DLLs/
        │   └── Lib/site-packages/
        │       └── docmeta-app.pth
        ├── app/
        │   ├── src/document_metadata_inspector/
        │   ├── src/xlsx_metadata_forensics/
        │   └── tools/
        │       ├── manifest.json
        │       └── packaged/windows-x86_64/
        │           ├── apache/
        │           │   ├── jdk/bin/java.exe
        │           │   └── worker.jar
        │           └── exiftool/exiftool.exe
        ├── SHA256SUMS
        └── RUNTIME-INFO.json
```

The packaged Electron process launches only files below its own resources
directory:

```text
python/python.exe -I -s -m document_metadata_inspector.cli
```

The embedded Python search path includes only its standard library,
`Lib/site-packages`, and `app/src`. A data-only `docmeta-app.pth` entry adds the
relative `app/src` directory; it contains no executable import statement.
`PYTHONHOME` and `PYTHONPATH` remain cleared.

## Runtime Acquisition and Assembly

A new macOS-capable assembler performs these steps:

1. Ask `uv` for the relocatable
   `cpython-3.12.13-windows-x86_64-none` distribution. Python.org does not ship
   Windows binaries for Python 3.12.13, so a nonexistent official Embedded ZIP
   must not be assumed.
2. Export the locked production dependency set from `uv.lock` and install only
   binary `win_amd64` wheels into the embedded `Lib/site-packages`. The build
   fails if any dependency lacks a compatible wheel.
3. Copy the two project source packages into `app/src`; no source checkout or
   external path is referenced at runtime.
4. Build the platform-neutral shaded Java Worker JAR on macOS.
5. Download the already pinned Windows x64 Temurin 21 JDK archive and include
   the complete JDK tree below
   `app/tools/packaged/windows-x86_64/apache/jdk`. The worker only launches its
   `bin/java.exe`, but the requested JDK remains fully self-contained.
6. Download the already pinned standalone Windows x64 ExifTool archive and
   include it below the same packaged-resource tree.
7. Generate a release-local copy of `tools/manifest.json` whose Windows x64
   resource entries cover every Java, Worker, and ExifTool file by SHA-256.
8. Generate `SHA256SUMS` and `RUNTIME-INFO.json` covering the complete embedded
   Python, application, Java, Worker, and ExifTool tree.
9. Place the completed tree at `desktop/.runtime/docmeta-runtime`, then package
   Electron for `win32/x64`.

All downloaded archives are hash-checked before extraction. Archive entries
with absolute paths, traversal, links, or duplicate normalized names are
rejected. Build caches are optional; a cached file is accepted only when its
expected digest still matches.

## Desktop Runtime Contract

The runtime resolver supports two packaged runtime layouts:

- Existing native one-file layout for native platform builds.
- New Windows embedded-Python layout for cross-packaged Windows x64 builds.

For the embedded layout it returns:

- command: `resources/docmeta-runtime/python/python.exe`
- argument prefix: `-I`, `-s`, `-m`, `document_metadata_inspector.cli`
- working directory: `resources/docmeta-runtime/app`

Before returning the command, the resolver validates the release checksum
manifest and the required Python/application entry points. It does not fall
back to a system interpreter when the packaged runtime is incomplete.

## Deliverables

The first build produces one complete Windows x64 application directory and a
portable ZIP from macOS. Both contain all resources and require no manual file
placement.

The installation executable wraps that exact same prebuilt directory. The
current Squirrel maker officially requires Windows (or Linux with Wine/Mono),
so macOS does not rebuild the application for the installer. If Squirrel cannot
run on macOS, the already-complete directory is copied to Parallels and wrapped
there without installing Python, Java, or project dependencies.

Expected release files:

```text
DocumentMetadataInspector-0.1.0-win-x64-Portable.zip
DocumentMetadataInspector-0.1.0-win-x64-Setup.exe
SHA256SUMS
BUILD-INFO.json
THIRD_PARTY_NOTICES.md
```

## Verification

Automated tests must prove:

- the downloader selects only Windows x64 artifacts and rejects bad hashes;
- dependency installation requests Python 3.12 and
  `x86_64-pc-windows-msvc`, with source builds disabled;
- the runtime tree contains Python, project packages, Java, Worker, ExifTool,
  notices, manifests, and no external absolute paths;
- Electron resolves the embedded Python command and never falls back to a
  system Python in packaged mode;
- the packaged application contains the complete runtime tree;
- manifest tampering or a missing runtime file fails closed.

The finished portable package and installer are then launched in the existing
Windows 11 ARM Parallels guest under Windows x64 emulation. This verifies the
actual user path without installing a build environment in the guest. A real
Windows x64 machine remains the final compatibility check before wider
distribution.

## Explicit Non-Goals

- No end-user runtime download.
- No manual copying of `resources` after installation.
- No dependency on system Python, Java, ExifTool, `PATH`, `PYTHONHOME`, or
  `PYTHONPATH`.
- No attempt to make Windows ARM64 the release target.
- No code signing or public auto-update service for this internal release.

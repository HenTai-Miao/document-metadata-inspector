# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


project_root = Path(os.environ["DOCMETA_BUILD_PROJECT_ROOT"]).resolve()
platform_key = os.environ["DOCMETA_BUILD_PLATFORM_KEY"]
build_mode = os.environ["DOCMETA_BUILD_MODE"]
if build_mode not in {"onefile", "onedir"}:
    raise ValueError("DOCMETA_BUILD_MODE must be onefile or onedir")

analysis = Analysis(
    [str(project_root / "scripts/frozen_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(project_root / "tools/manifest.json"), "tools"),
        (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# This Tree is intentionally appended after Analysis. PyInstaller 6 reclassifies
# executable-looking files supplied to Analysis and rewrites/signs them on macOS.
# The private JRE and Perl runtime are already self-contained and hash-locked, so
# they must remain byte-for-byte DATA instead of becoming PyInstaller binaries.
analysis.datas += Tree(
    str(project_root / "tools/packaged" / platform_key),
    prefix=f"tools/packaged/{platform_key}",
    typecode="DATA",
)

python_archive = PYZ(analysis.pure)

if build_mode == "onefile":
    executable = EXE(
        python_archive,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="docmeta",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    executable = EXE(
        python_archive,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="docmeta",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        contents_directory="_internal",
    )
    collection = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name="docmeta",
    )

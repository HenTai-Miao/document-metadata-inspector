# Bundled parser tools

This directory contains build inputs for the offline application. It is not an
end-user installation directory.

## ExifTool

- Locked version: `13.55`
- Official source artifact and SHA-256: `manifest.json`
- Development source tree: `vendor/exiftool/13.55/source/`
- Bootstrap command: `uv run python scripts/bootstrap_tools.py`

The bootstrap command runs only on developer/build machines. It checks the
vendored tree first and downloads the official artifact only when that tree is
missing. It never runs from an installed application.

Release builds must populate the matching `packaged` manifest entry with a
self-contained platform command and SHA-256 for every runtime file. macOS and
Linux packages must include a private Perl runtime; Windows packages use the
controlled standalone ExifTool runtime. A release may not fall back to a
system `exiftool`, `perl`, Python, Java, Office, or LibreOffice installation.

The relocatable Unix runtime also pins Archive::Zip 1.68 so ExifTool can inspect
compressed Word and Excel OPC packages instead of reporting only their ZIP
inventory.

## Java

`scripts/bootstrap_jdk.py` detects an exact Eclipse Temurin 21.0.12+8 JDK and
downloads the hash-locked official archive into the ignored build cache only
when no compatible candidate exists. `jlink` produces the bundled runtime.
Maven 3.9.11 is provided by the checksummed Maven Wrapper under `java-worker/`.

At runtime the resolver verifies all declared hashes before starting the tool.
The application invokes ExifTool with fixed read-only arguments, sends the
temporary source path and optional password through standard input, and runs
without network access or write-tag arguments.

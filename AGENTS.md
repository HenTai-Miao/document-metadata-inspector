# AGENTS.md

## Project Purpose

`document-metadata-inspector` is an offline Python 3.12 application and library
for evidence-sourced metadata extraction and comparison across PDF, Word, and
Excel. It combines bounded native parsers, a Java 21 Apache Tika/POI/PDFBox
worker, and ExifTool 13.55. Treat every input document as untrusted. Public
models, error codes, JSON serialization, parser provenance, and completeness
states are stable downstream contracts.

## Layout

- `src/document_metadata_inspector/` owns the generic format boundary,
  multi-engine scanner, comparison, export, runtime resolution, and CLI.
- `src/document_metadata_inspector/native/` owns bounded PDF, OLE, OPC,
  property, comment, and revision extraction.
- `src/document_metadata_inspector/workers/` owns Apache Worker and ExifTool
  subprocess adapters.
- `src/xlsx_metadata_forensics/` remains the hardened Excel package reader used
  by the generic native engine; do not expand its public API casually.
- `java-worker/` is the Java 21 JSON-lines worker built as one shaded JAR.
- `tools/manifest.json` pins every downloaded source and packaged runtime file.
- `scripts/` owns build-machine dependency detection and native packaging.
- `src/xlsx_metadata_forensics/normalization.py` preserves timestamp evidence
  and redacts sensitive custom-property values.
- `tests/unit/` contains behavior and regression tests. Reuse
  `tests/factories.py` to create or mutate test packages.

## Environment and Commands

- Run commands from this repository root.
- Use `uv` and the pinned Python `3.12.13` from `.python-version`; do not use a
  system interpreter or set `PYTHONPATH`/`PYTHONHOME`.
- Install or refresh the development environment with `uv sync --all-groups`.
- Run focused tests with a concrete path, for example
  `uv run pytest tests/unit/test_normalization.py`.
- Before handing off code changes, run:

  ```bash
  uv run pytest
  uv run ruff check .
  uv run ruff format --check .
  uv run basedpyright
  uv lock --check
  uv build
  ```

- Verify the Java worker with Java 21 by entering `java-worker/` and running
  `./mvnw --batch-mode --no-transfer-progress verify` (`mvnw.cmd` on Windows).
- Run `uv run docmeta verify` before and after frozen application builds.
- End-user releases must be built natively on Windows, Linux, and macOS. They
  must bundle Python, Temurin JRE, the worker JAR, and ExifTool runtime; never
  introduce a runtime download or a system-tool fallback.

- When dependencies change, update `uv.lock` with the appropriate `uv` command
  and keep it consistent with `pyproject.toml`.

## Code Conventions

- Keep public boundary models immutable (`frozen=True`) and closed to unknown
  fields (`extra="forbid"`). Preserve the established JSON schema and error-code
  vocabulary unless a deliberate contract change is requested.
- Use modern Python 3.12 typing, including `type` aliases, `Literal`,
  `Final`, `@final`, and `@override` where the existing module patterns call for
  them.
- Follow the repository's Ruff configuration: 88-character lines, double
  quotes, Google-style docstrings, and strict linting.
- Add or update a narrowly scoped unit test with each behavior change. Tests
  commonly use Given/When/Then comments for non-obvious boundary behavior.

## Security and Evidence Rules

- Never extract an untrusted document archive to disk, dereference external
  relationships, fetch remote document content, execute macros/scripts, or run
  embedded objects. `openpyxl` is for controlled fixture/export creation, not
  untrusted-package inspection.
- Keep the Java 21 worker's JVM-wide network deny boundary enabled for every
  launch. URL handlers alone are insufficient; raw sockets, DNS, listeners,
  multicast, and Java HTTP clients must remain denied and covered by tests.
- A filename suffix identifies only the declared format; it never proves the
  actual PDF/OLE/OPC container is safe or valid. Preserve the declared-versus-
  detected identity boundary for every parser.
- Preserve the package reader's bounded-resource model: validate the inventory
  before use, honor entry/file/XML/read budgets, use defused XML parsing, and
  retain deterministic package closure.
- Fail closed for malformed, unsafe, corrupt, encrypted, or unsupported input
  using the existing typed `ExtractionError`/`ErrorCode` contracts. Do not leak
  raw exception details to callers.
- Preserve raw forensic evidence. Do not invent a missing date, time, timezone,
  relationship target, or property value during normalization.
- Keep embedded-document evidence in independent child reports identified by
  stable parent/path/content hashes. Do not flatten child identity metadata into
  the containing document, and preserve the depth/count/total-byte budgets.
- Never store passwords. Password callbacks may be invoked only after a parser
  proves encryption and must share the original timeout budget on retry.
- Comment bodies and document content are out of scope; retain only bounded
  hashes/lengths where needed to distinguish forensic records.
- Keep credential-like custom-property values redacted. Add boundary tests when
  changing redaction tokenization or evidence serialization.
- Optional OOXML property parts may yield the existing stable warnings; do not
  silently convert failures in required package validation into warnings.

## Repository Hygiene

- Do not add real workbooks, sensitive metadata, credentials, or generated
  extraction output to the repository. Use temporary paths and synthetic
  fixtures in tests.
- Keep changes scoped to this package. Do not modify neighboring projects in the
  parent workspace unless the task explicitly requires it.

# Document Metadata Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a headless `docmeta` core that scans, compares, and exports traceable metadata from the approved PDF, Word, and Excel families without modifying source files.

**Architecture:** Keep Python 3.12 as the immutable evidence-model and orchestration layer. Reuse the bounded OPC/OLE reader, add native PDF/Word evidence readers, call a Java 21 Tika/POI/PDFBox worker and an ExifTool read-only worker through typed JSON boundaries, then merge observations without overwriting conflicts.

**Tech Stack:** CPython 3.12.13, uv, Pydantic v2, Typer, defusedxml, olefile 0.47, pypdf, openpyxl (export/dev fixtures), Java 21, Maven 3.9, Apache Tika 3.3.2, Apache POI 5.5.1, PDFBox 3.0.8, Jackson 2.20.1, pytest, Ruff, BasedPyright, JUnit 5.

## Global Constraints

- Modify only `xlsx-metadata-forensics/` until the final in-parent directory rename.
- Preserve every existing user file; do not reset, checkout, stash, delete, or commit the outer unborn/dirty Git repository.
- Supported formats are exactly PDF; DOC/DOCX/DOCM/DOT/DOTX/DOTM; XLS/XLSX/XLSM/XLSB/XLT/XLTX/XLTM.
- CSV, RTF, ODS, WPS and PowerPoint are outside this plan.
- Runtime is offline and read-only: no URL fetches, macro/script/action execution, external relationship resolution, or source-file writes.
- End-user runtime is self-contained and never downloads dependencies; Python, a trimmed Java 21 runtime, the Apache worker and ExifTool ship inside each platform package.
- Passwords may enter only through an in-memory provider or secure terminal prompt; never accept a plaintext password CLI option.
- Preserve raw values, normalized values, parser/version and part/stream/object provenance. Conflicts remain visible.
- A missing optional worker is an explicit `unavailable` parser status and prevents a `complete` coverage claim.
- Use an explicit Java 21 `JAVA_HOME` on the build workstation.
- All Python commands use `env -u PYTHONPATH -u PYTHONHOME`; tests disable bytecode and pytest cache.
- Do not design or implement a desktop GUI in this plan.

---

### Task 1: Restore a trustworthy Excel baseline

**Files:**
- Modify: `src/xlsx_metadata_forensics/legacy/_biff_validation.py`
- Modify: `src/xlsx_metadata_forensics/legacy/_ole_adapter.py`
- Modify: `src/xlsx_metadata_forensics/legacy/package.py`
- Modify: `src/xlsx_metadata_forensics/legacy/properties.py`
- Modify: `tests/unit/test_legacy_package.py`
- Modify: `tests/unit/test_legacy_security.py`
- Modify: `tests/unit/test_extractor.py`

**Interfaces:**
- Preserves: `extract_metadata(ExtractionRequest) -> ExtractionReport`.
- Preserves: `open_legacy_workbook(...) -> AbstractContextManager[LegacyWorkbookView]`.
- Produces: a green legacy/OPC test baseline and zero Ruff/BasedPyright errors.

- [ ] **Step 1: Re-run the existing failing gates and save the exact failure list**

Run:

```bash
env -u PYTHONPATH -u PYTHONHOME PYTHONDONTWRITEBYTECODE=1 \
  uv run pytest -q -p no:cacheprovider
env -u PYTHONPATH -u PYTHONHOME uv run ruff check .
env -u PYTHONPATH -u PYTHONHOME uv run basedpyright
```

Expected: collection fails on obsolete `_validate_workbook`; Ruff and BasedPyright report the known legacy adapter/type failures.

- [ ] **Step 2: Replace private-implementation tests with public behavior tests**

Change `test_legacy_package.py` to call `open_legacy_workbook()` for valid identity and `extract_metadata()` for encryption/error behavior. Do not reintroduce `_validate_workbook` or expose `_check_encryption` as public API.

- [ ] **Step 3: Add typed unpack helpers and a narrow olefile boundary**

Implement explicit helpers such as:

```python
def _unpack_u16_pair(payload: bytes, offset: int = 0) -> tuple[int, int]:
    first, second = unpack_from("<HH", payload, offset)
    return int(first), int(second)
```

Keep the unavoidable pinned `olefile` private calls inside `_ole_adapter.py` with narrowly scoped per-file lint/type suppressions and explanatory comments; no project-wide ignores.

- [ ] **Step 4: Normalize OLE metadata through a typed Protocol**

Define the exact attributes consumed from `OleMetadata`, convert seconds to minutes correctly, and preserve UTC instead of converting to an assumed China timezone.

- [ ] **Step 5: Format and run focused legacy tests**

Run:

```bash
env -u PYTHONPATH -u PYTHONHOME uv run ruff format \
  src/xlsx_metadata_forensics/legacy tests/unit/test_legacy_package.py \
  tests/unit/test_legacy_security.py tests/unit/test_extractor.py
env -u PYTHONPATH -u PYTHONHOME PYTHONDONTWRITEBYTECODE=1 \
  uv run pytest -q -p no:cacheprovider tests/unit/test_legacy_package.py \
  tests/unit/test_legacy_security.py tests/unit/test_extractor.py
```

Expected: focused tests pass.

- [ ] **Step 6: Run the full Python gate**

Expected: all tests collect and pass; Ruff, format check and BasedPyright are clean.

---

### Task 2: Introduce the generic package and compatibility boundary

**Files:**
- Create: `src/document_metadata_inspector/__init__.py`
- Create: `src/document_metadata_inspector/models.py`
- Create: `src/document_metadata_inspector/errors.py`
- Create: `src/document_metadata_inspector/formats.py`
- Create: `src/document_metadata_inspector/normalization.py`
- Create: `src/document_metadata_inspector/cli.py`
- Modify: `src/xlsx_metadata_forensics/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/unit/test_document_formats.py`
- Create: `tests/unit/test_evidence_models.py`
- Create: `tests/unit/test_cli_help.py`

**Interfaces:**
- Produces: `DocumentFormat`, `DocumentFamily`, `ContainerKind`, `FormatIdentity`.
- Produces: immutable `EvidenceObservation`, `ParserRun`, `DocumentReport`, `ScanReport`, `ComparisonReport`.
- Produces: `docmeta --help` and legacy `xlsx_metadata_forensics.extract_metadata` compatibility.

- [ ] **Step 1: Write format-contract RED tests**

Assert the exact suffix list, case-insensitive parsing, unsupported suffix rejection and family/container mapping. Include mismatched extension vs magic as a separate identity status rather than trusting the suffix.

- [ ] **Step 2: Write evidence-model RED tests**

Use this minimum contract:

```python
class EvidenceObservation(FrozenModel):
    canonical_name: str
    raw_name: str
    raw_value: JsonValue
    normalized_value: JsonValue
    value_type: str
    source_kind: str
    location: str
    parser_name: str
    parser_version: str
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    warnings: tuple[str, ...] = ()
```

Assert frozen models, unknown-field rejection, tuple serialization and raw/normalized coexistence.

- [ ] **Step 3: Implement generic formats, errors and normalization**

`normalize_identity_text()` performs Unicode NFKC, trim, whitespace collapse and `casefold()` only. It must not apply pinyin, fuzzy matching or punctuation deletion.

- [ ] **Step 4: Add the new CLI entry point**

Update scripts to:

```toml
[project.scripts]
docmeta = "document_metadata_inspector.cli:main"
xlsx-forensics = "xlsx_metadata_forensics.cli:main"
```

The legacy entry either forwards to `docmeta` with a deprecation warning or remains functional until Task 10 removes the broken target.

- [ ] **Step 5: Run focused and full gates**

Expected: new model/format/CLI tests pass and all existing Excel tests remain green.

---

### Task 3: Build generic source snapshots and native Office property adapters

**Files:**
- Create: `src/document_metadata_inspector/source.py`
- Create: `src/document_metadata_inspector/native/__init__.py`
- Create: `src/document_metadata_inspector/native/ole.py`
- Create: `src/document_metadata_inspector/native/opc.py`
- Create: `src/document_metadata_inspector/native/office_properties.py`
- Create: `tests/unit/test_source_snapshot.py`
- Create: `tests/unit/test_native_ole.py`
- Create: `tests/unit/test_native_opc.py`

**Interfaces:**
- Produces: `open_source_snapshot(path, limits) -> ContextManager[SourceSnapshot]`.
- Produces: `extract_native_office(snapshot, identity, password_provider) -> ParserResult`.
- Consumes: Task 2 evidence contracts.

- [ ] **Step 1: Write snapshot RED tests**

Cover non-regular/missing files, size-before-read, a path replacement after open, in-place mutation, SHA-256 before/after and deterministic closure.

- [ ] **Step 2: Implement a single-open-file snapshot**

Hash and parse the same opened handle. Validate inode/file identity where the platform exposes it, and always verify size/mtime/hash before success.

- [ ] **Step 3: Write OLE family RED tests**

Use real synthetic DOC/DOT and XLS/XLT fixtures. Require Word root `WordDocument` for Word and exactly one `Workbook`/`Book` for Excel. Extract all available SummaryInformation and DocumentSummaryInformation fields while preserving unknown property IDs/types.

- [ ] **Step 4: Write OPC family RED tests**

Generate controlled DOCX/DOCM/DOTX/DOTM and Excel packages with exact officeDocument MIME identities. Assert core/app/custom properties, external relationship non-dereference, macro/signature/embedding inventory and ZIP budgets.

- [ ] **Step 5: Implement generic OLE/OPC adapters by extracting reusable logic from the legacy package**

Do not delete legacy modules. Make compatibility wrappers delegate only after public parity tests pass.

- [ ] **Step 6: Run focused native-adapter and regression gates**

Expected: generic Office property extraction works for all controlled Office extensions and old Excel tests remain green.

---

### Task 4: Add native PDF evidence extraction

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/document_metadata_inspector/native/pdf.py`
- Create: `tests/factories/pdf_factory.py`
- Create: `tests/unit/test_native_pdf.py`
- Create: `tests/unit/test_pdf_security.py`

**Interfaces:**
- Produces: `extract_native_pdf(snapshot, password_provider, limits) -> ParserResult`.
- Emits observations for DocumentInfo, Trailer ID, XMP locations, annotations, forms, attachments, signatures, encryption and permissions.

- [ ] **Step 1: Add pinned `pypdf` and write RED fixtures**

Create synthetic PDFs for Info/XMP, duplicate authors, annotations, attachment, incremental update, password encryption and malformed object graphs. Never use user documents as fixtures.

- [ ] **Step 2: Assert raw provenance and password states**

Tests distinguish `password_required`, `wrong_password` and unsupported encryption. Annotation contents and attachment bytes are hashed/length-counted by default, not emitted.

- [ ] **Step 3: Implement bounded read-only traversal**

Track visited indirect objects and enforce object/depth/output budgets. Walk metadata streams reachable from catalog/pages/resources where supported; mark coverage partial when a raw construct cannot be interpreted.

- [ ] **Step 4: Prove no source modification and run PDF gates**

Hash every fixture before and after extraction and assert equality.

---

### Task 5: Implement the Apache Java worker

**Files:**
- Create: `java-worker/pom.xml`
- Create: `java-worker/src/main/java/io/docmeta/worker/Main.java`
- Create: `java-worker/src/main/java/io/docmeta/worker/Protocol.java`
- Create: `java-worker/src/main/java/io/docmeta/worker/TikaExtractor.java`
- Create: `java-worker/src/main/java/io/docmeta/worker/ResourceLimits.java`
- Create: `java-worker/src/test/java/io/docmeta/worker/ProtocolTest.java`
- Create: `java-worker/src/test/java/io/docmeta/worker/TikaExtractorTest.java`
- Create: `src/document_metadata_inspector/workers/apache.py`
- Create: `tests/unit/test_apache_worker_adapter.py`

**Interfaces:**
- Worker consumes one JSON line with `request_id`, `path`, optional in-memory-delivered password token and limits.
- Worker produces one JSON line with `request_id`, `status`, `content_type`, raw metadata multimap, embedded resource descriptors, warnings and sanitized error.
- Python produces: `ApacheWorker.scan(snapshot, password_provider, limits) -> ParserResult`.

- [ ] **Step 1: Write Java protocol RED tests**

Assert unknown JSON fields reject, request IDs round-trip, metadata duplicate values remain arrays, passwords never appear in responses and errors contain no absolute path.

- [ ] **Step 2: Add the fixed Maven dependency set and reproducible shade build**

Use Tika 3.3.2, explicit POI 5.5.1/PDFBox 3.0.8 alignment where compatible, Jackson 2.20.1 and JUnit 5. Pin plugins; create a dependency-reduced shaded JAR and include LICENSE/NOTICE resources.

- [ ] **Step 3: Implement metadata-only recursive parsing**

Use `AutoDetectParser` and recursive metadata handling with content ignored. Preserve all duplicate metadata values and embedded resource paths. Configure external-access denial and parser limits.

- [ ] **Step 4: Write Python adapter RED tests with a fake worker**

Cover timeout, nonzero exit, malformed JSON, wrong request ID, excess output and parser unavailable.

- [ ] **Step 5: Implement the killable Python subprocess adapter**

Use an explicit argument list, controlled environment, task temp directory, stdout byte cap and timeout. Never invoke a shell.

- [ ] **Step 6: Build and run Java/Python integration tests**

Run:

```bash
JAVA_HOME=/path/to/java-21 \
PATH=/path/to/java-21/bin:$PATH \
  mvn -f java-worker/pom.xml verify
```

Then scan one synthetic file from each major family through the real shaded JAR.

---

### Task 6: Implement the read-only ExifTool adapter

**Files:**
- Create: `src/document_metadata_inspector/workers/exiftool.py`
- Create: `src/document_metadata_inspector/resources.py`
- Create: `tests/unit/test_exiftool_adapter.py`
- Create: `tests/integration/test_exiftool_real.py`
- Create: `tools/README.md`
- Create: `tools/manifest.json`
- Create: `scripts/bootstrap_tools.py`

**Interfaces:**
- Produces: `ExifToolWorker.scan(snapshot, password_provider, limits) -> ParserResult`.
- Resource resolver checks the packaged platform path first, then an explicit development-only `DOCMETA_EXIFTOOL` path. Version 13.55 is pinned. Runtime never downloads.

- [ ] **Step 1: Write argument and JSON RED tests**

Require read-only arguments equivalent to `-json -a -u -U -G3:1 -struct -ee3 -api RequestAll=3 -api LargeFileSupport=1`. Assert no write tag assignment or output path argument can enter the command.

- [ ] **Step 2: Install and lock ExifTool 13.55 for development/builds**

`scripts/bootstrap_tools.py` checks the project resource first and the system only in explicit development mode. If 13.55 is absent on a build machine, it downloads the official production artifact, verifies the pinned SHA-256 from `tools/manifest.json`, installs it under `tools/vendor/exiftool/13.55/<platform>/`, and records no machine-specific path. This bootstrap is never called by the installed application.

- [ ] **Step 3: Implement strict packaged-resource resolution**

The release resolver requires the packaged executable/script plus companion files and verifies the manifest hash before invocation. A release build fails if any target-platform ExifTool resource is missing; it cannot silently fall back to an arbitrary system version.

- [ ] **Step 4: Implement bounded subprocess parsing**

Preserve group/tag names, duplicate values and raw JSON scalars. Translate passwords without placing them in a visible process argument when the platform/tool permits; otherwise mark that encrypted subtype unsupported rather than leaking the password.

- [ ] **Step 5: Prove source hash stability and sanitized failures**

Run unit tests and the conditional real test.

---

### Task 7: Merge parser evidence and orchestrate scans

**Files:**
- Create: `src/document_metadata_inspector/merge.py`
- Create: `src/document_metadata_inspector/scanner.py`
- Create: `tests/unit/test_merge.py`
- Create: `tests/unit/test_scanner.py`
- Create: `tests/integration/test_multi_engine_scan.py`

**Interfaces:**
- Produces: `merge_parser_results(results: Sequence[ParserResult]) -> MergedEvidence`.
- Produces: `scan_documents(request: ScanRequest) -> ScanReport`.
- Consumes: native, Apache and ExifTool adapters.

- [ ] **Step 1: Write merge RED tests**

Cover exact duplicate collapse, independent-source corroboration, conflicting canonical values, unknown tags, partial/unavailable engines and deterministic ordering.

- [ ] **Step 2: Implement key-based deduplication without overwrite**

Use a stable key containing canonical/raw name, normalized/raw value, source location and parser. Generate `parser_value_conflict` only when the same canonical field has distinct normalized values.

- [ ] **Step 3: Write scan orchestration RED tests**

Cover multiple files, one failure among successes, directory non-recursive/recursive expansion, stable order, password provider routing and source-changed failure.

- [ ] **Step 4: Implement bounded concurrency and complete parser statuses**

Default concurrency is `min(4, cpu_count)` and configurable. Per-file parser failures remain in the file report; a file can be `complete`, `partial` or `failed` only by explicit coverage rules.

- [ ] **Step 5: Run real multi-engine integration tests**

Assert the same author from two engines corroborates rather than overwrites and missing ExifTool makes coverage partial.

---

### Task 8: Implement author-trace comparison

**Files:**
- Create: `src/document_metadata_inspector/comparison.py`
- Create: `tests/unit/test_comparison.py`
- Create: `tests/integration/test_multi_file_comparison.py`

**Interfaces:**
- Produces: `compare_documents(request: CompareRequest) -> ComparisonReport`.
- Identity fields are a closed enum: author, last modifier, comment/revision author, company, manager, application/version, template, signer certificate identity and confirmed username path trace.

- [ ] **Step 1: Write exact-match RED tests**

Assert NFKC/case/whitespace normalization, preservation of raw variants, at least two distinct files per match and no match for one-file duplicates.

- [ ] **Step 2: Write false-positive guard tests**

Assert no pinyin, edit-distance, token-subset or semantic matching. Generic applications such as Microsoft Word are labeled `software_trace`, not `person_trace`.

- [ ] **Step 3: Implement deterministic grouping and evidence links**

Each group lists file IDs, field names, raw values, observation IDs and source locations. Never emit collusion or identity conclusions.

- [ ] **Step 4: Run comparison unit/integration tests**

Expected: all groups are explainable and serializable.

---

### Task 9: Implement JSON, XLSX and HTML export

**Files:**
- Create: `src/document_metadata_inspector/exporters/__init__.py`
- Create: `src/document_metadata_inspector/exporters/json_export.py`
- Create: `src/document_metadata_inspector/exporters/xlsx_export.py`
- Create: `src/document_metadata_inspector/exporters/html_export.py`
- Create: `tests/unit/test_json_export.py`
- Create: `tests/unit/test_xlsx_export.py`
- Create: `tests/unit/test_html_export.py`

**Interfaces:**
- Produces: `export_report(report, ExportTarget) -> Path`.
- JSON is authoritative; XLSX/HTML are projections with explicit truncation-free row counts.

- [ ] **Step 1: Write atomic-output and collision RED tests**

Reject a target equal to any input. Simulate a writer exception and assert no partial target remains.

- [ ] **Step 2: Implement deterministic JSON export**

Use UTF-8, schema version, sorted stable arrays and atomic `os.replace()` from the target directory.

- [ ] **Step 3: Implement XLSX projection**

Create sheets for files, canonical metadata, identity matches, raw observations, forensic evidence, parser coverage and warnings/errors. Store text as cells, not screenshots; preserve all rows.

- [ ] **Step 4: Implement standalone HTML projection**

Escape every value, embed CSS/data locally and include exact totals. No script or remote URL is required.

- [ ] **Step 5: Run export tests and reopen outputs**

Load XLSX with openpyxl and parse HTML with a standard parser to verify counts and escaping.

---

### Task 10: Complete CLI, offline verification and documentation

**Files:**
- Modify: `src/document_metadata_inspector/cli.py`
- Create: `src/document_metadata_inspector/verify.py`
- Create: `tests/e2e/test_cli.py`
- Create: `tests/e2e/test_verify.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `scripts/build_core_bundle.py`

**Interfaces:**
- Delivers: `docmeta scan`, `compare`, `export`, `verify`.
- Delivers: one-folder offline core bundle staging with Python app, JRE/worker JAR, ExifTool resource slot, licenses and manifest hashes.

- [ ] **Step 1: Write real CLI subprocess RED tests**

Assert `--help`, multi-file scan, partial failure exit codes, secure password prompt, compare, export and verify. Parse stdout JSON and assert stderr never contains passwords or full metadata values.

- [ ] **Step 2: Implement CLI commands using only public core APIs**

No extraction logic lives in Typer callbacks. `scan`/`compare` accept paths and `--recursive`; `export` consumes a saved schema; `verify` is offline.

- [ ] **Step 3: Implement the controlled verification command**

Generate synthetic fixtures in a temporary directory, invoke native/Apache/ExifTool adapters, compare known fields, assert source hashes and print PASS/FAIL per capability. Missing packaged ExifTool is FAIL for a release bundle and explicit SKIP for a development checkout.

- [ ] **Step 4: Replace the empty README with exact Chinese usage and coverage tables**

Document every supported format as complete/partial/detection-only per evidence category, password behavior, security limits, offline operation, build commands and known limitations. Do not claim desktop GUI exists.

- [ ] **Step 5: Build and validate the core bundle staging**

Manifest every runtime file with SHA-256 and license. The staging tool refuses unpinned or missing release resources and never downloads at runtime.

- [ ] **Step 6: Run final fresh gates**

```bash
env -u PYTHONPATH -u PYTHONHOME PYTHONDONTWRITEBYTECODE=1 \
  uv run pytest -q -p no:cacheprovider
env -u PYTHONPATH -u PYTHONHOME uv run ruff check .
env -u PYTHONPATH -u PYTHONHOME uv run ruff format --check .
env -u PYTHONPATH -u PYTHONHOME uv run basedpyright
env -u PYTHONPATH -u PYTHONHOME uv lock --check
env -u PYTHONPATH -u PYTHONHOME uv build
JAVA_HOME=/path/to/java-21 \
PATH=/path/to/java-21/bin:$PATH \
  mvn -f java-worker/pom.xml verify
env -u PYTHONPATH -u PYTHONHOME uv run docmeta verify
```

Expected: every required gate is green, the real ExifTool 13.55 integration check passes, and the staged bundle runs after system Python, Java, Perl and ExifTool are removed from `PATH`.

---

### Task 11: Rename the project directory without data loss

**Files:**
- Move within parent: `xlsx-metadata-forensics/` to `document-metadata-inspector/`
- Update internal documentation references only inside the moved project.

**Interfaces:**
- Final project path: `document-metadata-inspector/`.

- [ ] **Step 1: Record a target-directory inventory and SHA-256 manifest**

Include every regular file except generated `.venv`, cache and build artifacts; keep user staged/untracked classification recorded read-only.

- [ ] **Step 2: Ensure no process has the old path as a live work directory**

Stop test/dev worker processes created by this plan. Do not touch unrelated processes.

- [ ] **Step 3: Rename the directory once within the same parent**

Use an explicit source and target; refuse if the target already exists. Do not copy/delete recursively.

- [ ] **Step 4: Recompute the manifest and run fresh gates from the new path**

Expected: all source/test/document hashes match pre-rename values and all gates pass.

## Plan Self-Review

- Spec coverage: format families, native provenance, Apache and ExifTool engines, merge conflicts, comparison, passwords, exports, CLI, offline verification, migration and final rename each have a task.
- Placeholder scan: no TBD/TODO or unspecified implementation step remains.
- Type consistency: `EvidenceObservation`, `ParserResult`, `ScanReport`, `ComparisonReport`, `scan_documents`, `compare_documents` and `export_report` are produced before consumption.
- Safety exception: commit steps are intentionally omitted because the enclosing Git repository is unborn and contains pre-existing user-staged/untracked work. Each task ends with fresh test/static gates instead.

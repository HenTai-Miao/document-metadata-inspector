# Unbounded Batch Scan Results Design

## Problem

The desktop currently asks the Python CLI to serialize one authoritative comparison
report, then reads and parses that report in Electron's main process. Four fixed
batch-wide limits can reject otherwise valid workloads:

- directory discovery stops after 50,000 entries;
- the exact-input manifest stops at 16 MiB or 50,000 documents;
- the child process is stopped after 30 minutes or after 1 MiB of cumulative logs;
- the desktop refuses reports larger than 128 MiB.

The supplied 12-bidder, 25-PDF, 1.1-GiB directory reproduces the last failure. The
core completes in about 26 seconds and writes a valid 366,450,678-byte report, but
the desktop rejects it before adapting the result. The report contains 198,708
merged observations, 259,034 parser-run observations, and 5,520 embedded-document
records. Reading it as one JavaScript string and object is not a scalable fix.

## Goals

- Do not impose product-defined limits on bidder count, supported-document count,
  total selected-directory bytes, result bytes, or total useful batch duration.
- Continue to use bounded parallelism so large jobs make progress without starting
  an unbounded number of Java, ExifTool, or Python workloads.
- Preserve a result for every selected document. A malformed, encrypted, timed-out,
  or resource-exhausting document becomes a visible failed or partial document; it
  does not erase successful documents from the batch.
- Never transfer the complete forensic report through Electron IPC or construct all
  metadata rows in the renderer at once.
- Preserve the existing public authoritative report schema for normal CLI users.
- Preserve per-document security budgets for untrusted file structures, parser
  output, memory, and subprocess execution. Those are containment controls, not
  batch-size policy.

## Non-goals

- This change does not make finite hardware literally unlimited.
- It does not remove ZIP/XML/object-count, parser-memory, or per-parser timeout
  protections from untrusted documents.
- It does not change exact-match semantics, public evidence models, or existing JSON,
  XLSX, and HTML export contracts.
- It does not raise default concurrency beyond a memory-safe worker pool merely to
  maximize CPU utilization.

## Selected Architecture

### 1. A desktop-specific streaming result bundle

Add an internal CLI output mode used only by the desktop. Instead of writing one
comparison JSON, it writes a private result bundle below the scan's private temporary
directory:

```text
result/
  summary.json
  details/<document-id>.json
  evidence/<document-id>.json
```

`evidence/` contains the full immutable `DocumentReport` for each completed document,
written as soon as that document finishes. This retains all sourced evidence without
holding the whole batch in memory. `details/` contains the presentation projection
used by the metadata screen. Exact duplicate label/value rows are represented once,
while the full observation count remains in `summary.json`. `summary.json` contains
document status/counts, parser summaries, warning counts, and compact exact-match
traces.

Every file is created in a private directory and published atomically. The final
summary is written last, so its presence means the bundle is complete. Paths are
derived only from validated lowercase SHA-256 document IDs.

### 2. Bounded streaming scan and comparison

Factor the scanner's per-document execution into a bounded iterator. At most the
configured worker count is submitted or retained at once. The existing `scan()` API
collects the iterator and therefore keeps its public behavior; the desktop bundle
writer consumes it incrementally.

Factor comparison into an accumulator that accepts one document at a time and keeps
only the small set of identity candidates required for cross-document exact matches.
The existing `compare_documents()` API uses the same accumulator, preventing semantic
drift between full reports and desktop bundles.

Default concurrency remains `min(4, CPU count)`, and the desktop passes that policy
explicitly. This is real multithreaded document parsing while bounding simultaneous
JVM and ExifTool memory. A later user-facing setting can tune it without changing the
bundle contract.

### 3. No batch-wide size or wall-clock cutoff

Remove the desktop's fixed report-size, input-manifest-size, discovered-entry-count,
input-document-count, cumulative-log-size, and absolute 30-minute batch cutoffs.

The exact-input manifest is written incrementally instead of first constructing one
large JavaScript string. Python validates the manifest incrementally and continues to
enforce path, identity, schema, duplicate-ID, and regular-file rules.

Child stdout/stderr are always drained. Diagnostic retention is a bounded tail rather
than a cumulative kill condition, so harmless warnings cannot terminate a large job.
There is no absolute batch deadline; per-document parser deadlines and explicit user
stop remain responsible for convergence.

### 4. Small initial IPC and on-demand details

`scan:start` returns only the compact summary. `ScanResult` document entries no longer
carry all observation rows. A new trusted IPC method fetches one document's detail by
validated document ID. The main process resolves that ID through its private active
bundle map and refuses paths supplied by the renderer.

The metadata page creates document cards without their rows. On first expansion it
requests that document's detail and renders it. This keeps startup and result-page
rendering proportional to the number of documents, not the number of observations.

The active result bundle remains available until a new folder/scan replaces it or the
application exits. Cleanup is explicit and uses the existing fail-closed temporary
directory behavior.

### 5. Progress and partial documents

The internal desktop CLI emits bounded JSON-lines progress messages. Messages report
completed documents and total documents without exposing local paths or raw exception
text. Electron converts those messages into monotonic progress updates.

Existing document-level failures remain `DocumentReport` entries. The desktop reports
the batch after all selected documents have a terminal status, including when the CLI
uses its existing partial-success exit code. Fatal bundle-integrity, runtime-integrity,
or unsafe-cleanup failures remain batch failures because no trustworthy result can be
published in those cases.

## Rejected Alternatives

### Delete only the 128-MiB check

This lets the supplied report reach `readFile()` but temporarily creates a hundreds-of-
MiB JavaScript string, a much larger parsed object, and nearly 200,000 DOM rows. It
will fail again on larger procurements and risks taking down Electron.

### Raise all fixed constants

Changing 128 MiB to 512 MiB or 50,000 entries to a larger number merely moves the same
failure. It does not satisfy the requirement that ordinary large procurements are not
rejected by batch size.

### Add a third-party streaming JSON parser in Electron

A maintained streaming parser could avoid the first JavaScript copy, but the desktop
would still parse and adapt evidence that it never displays, and the renderer would
still receive too many rows. Producing the purpose-built projection where the typed
Python models already exist is smaller and avoids another runtime dependency.

## Safety and Error Handling

- Selection traversal skips symbolic links and non-regular files.
- Manifest and bundle files are private, regular, non-symlink files; document IDs are
  validated hashes, never renderer-controlled paths.
- Per-document resource and parser limits return a failed/partial document with stable
  error codes and sanitized messages.
- A user stop terminates only the owned process tree and removes an unpublished bundle.
- Bundle publication and cleanup failures remain fail-closed and block reuse until the
  process tree or private temporary state is known safe.
- No raw subprocess error, absolute path, document content, password, or credential-like
  custom value is added to progress or renderer errors.

## Verification

1. Red/green tests for reports above the former 128-MiB boundary without allocating a
   matching fixture in the test process.
2. Scanner tests proving bounded in-flight documents and equivalence with `scan()`.
3. Comparison accumulator equivalence tests against `compare_documents()`.
4. Manifest tests beyond the former byte/document limits with symlink, duplicate,
   mutation, and malformed-entry rejection retained.
5. Desktop tests for unlimited batch duration, drained large logs, compact summary,
   trusted detail lookup, lazy rendering, stop, and cleanup.
6. Full Python and desktop quality gates, Java worker verification, runtime verify,
   and builds.
7. Real-data acceptance against the supplied 12-bidder/25-PDF directory: all 25
   documents reach terminal status, the result page appears, detail retrieval works,
   no visible command window appears, and no child process remains.
8. A synthetic many-bidder manifest verifies that bidder/document cardinality is not
   rejected by a product constant without requiring multi-gigabyte fixtures.

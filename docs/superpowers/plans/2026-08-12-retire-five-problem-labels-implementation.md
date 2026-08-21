# Retire Five Problem Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop manager, company, signer identity, username path trace, and template metadata from producing cross-bidder problems or visible problem-label cards while preserving those values in extraction evidence, report schemas, document summaries, and on-demand metadata details.

**Architecture:** Narrow the Python comparison allowlist at the point where observations become match candidates, then narrow the renderer's fixed problem-label registry to the six retained checks. Preserve all parser, normalization, serialization, report-adapter, and metadata-detail paths. Treat historical reports as untrusted compatibility input: retired-only traces are ignored, mixed traces still contribute only to retained labels, and no retired value leaks into the problem-label view.

**Tech Stack:** Python 3.12.13, Pydantic 2, pytest, Electron 43, Node.js 24, TypeScript 7, Vitest 4, Playwright 1.62, Ruff, Biome, BasedPyright.

## Global Constraints

- Retire exactly five visible problem labels: `manager`, `company`, `signer_identity` (including source alias `signature_signer_name`), `username_path_trace`, and `template`.
- Preserve exactly six visible problem labels in this order: `author`, `last_modified_by`, `comment_author`, `revision_author`, `created_at`, `modified_at`.
- Do not remove or rename raw observations, normalizers, native parser fields, Java/ExifTool evidence, `DocumentKeyFields.company`, `DocumentKeyFields.template`, report schemas, detail schemas, or existing field translations.
- Do not change parser resource limits, file-safety checks, network isolation, scan concurrency, large-batch streaming, result publication, or error contracts.
- New Python comparison reports must not contain matches created solely from retired fields.
- Historical desktop reports may still contain retired traces. Retired-only traces must produce no risk card, count, relation, hidden section, or leaked value. A mixed trace must contribute only to its retained field labels.
- Keep `annotation_author` as the supported historical alias for `comment_author`; remove only the `signature_signer_name` to `signer_identity` problem-label alias.
- Do not update `desktop/mock-designs/`: those files are archived design explorations, not runtime or acceptance contracts.
- Follow strict TDD. Capture the specified RED failure before each production edit, make the smallest production change, then rerun the focused GREEN gate.
- Use the repository-pinned Python through `uv`. For desktop commands on this host, use the bundled pnpm executable shown below rather than the mixed system Corepack installation.

Desktop command prefix used throughout this plan:

```bash
PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm
```

---

### Task 1: Retire the Five Fields at the Python Comparison Boundary

**Files:**
- Modify: `tests/unit/test_comparison.py`
- Modify: `src/document_metadata_inspector/comparison.py`

**Behavioral boundary:**
- `DocumentReport.observations` continues to contain every extracted field.
- `_candidates()` ignores retired canonical names because `_FIELD_FACTS` no longer recognizes them.
- `compare_documents()` and `ComparisonAccumulator` continue sharing exactly the same candidate logic.
- The six retained field families keep their existing `TraceKind`, normalization, grouping, evidence links, and cross-bidder suppression behavior.

- [ ] **Step 1: Add parameterized RED coverage for all retired canonical names**

Add `import pytest` and a focused regression in `tests/unit/test_comparison.py`:

```python
@pytest.mark.parametrize(
    "canonical_name",
    [
        "manager",
        "company",
        "signature_signer_name",
        "signer_identity",
        "username_path_trace",
        "template",
    ],
)
def test_retired_problem_fields_are_not_compared(canonical_name: str) -> None:
    first = _document("first.pdf", _observation(canonical_name, "Shared value"))
    second = _document("second.docx", _observation(canonical_name, "shared value"))

    result = compare_documents(ComparisonRequest(documents=(first, second)))

    assert result.matches == ()
```

The six parameter values represent five product labels because both signer canonical names formerly collapsed into `signer_identity`.

- [ ] **Step 2: Add a positive regression for all six retained problem fields**

Add a second parameterized test:

```python
@pytest.mark.parametrize(
    "canonical_name",
    [
        "author",
        "last_modified_by",
        "comment_author",
        "revision_author",
        "created_at",
        "modified_at",
    ],
)
def test_retained_problem_fields_still_match(canonical_name: str) -> None:
    first = _document("first.pdf", _observation(canonical_name, "Shared value"))
    second = _document("second.docx", _observation(canonical_name, "shared value"))

    result = compare_documents(ComparisonRequest(documents=(first, second)))

    assert len(result.matches) == 1
    assert result.matches[0].field_names == (canonical_name,)
```

This prevents an over-broad implementation from disabling comparison entirely.

- [ ] **Step 3: Run the new comparison tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_comparison.py \
  -k 'retired_problem_fields or retained_problem_fields' -vv
```

Expected before the production edit:

- all six retained cases pass;
- the retired cases fail because `result.matches` still contains one match;
- the failure proves the test is exercising the existing comparison allowlist rather than merely asserting enum contents.

- [ ] **Step 4: Remove only retired comparison enum members and field mappings**

In `src/document_metadata_inspector/comparison.py`, reduce `IdentityField` to:

```python
class IdentityField(StrEnum):
    """Closed set of fields permitted to participate in trace comparison."""

    AUTHOR = "author"
    LAST_MODIFIED_BY = "last_modified_by"
    COMMENT_AUTHOR = "comment_author"
    REVISION_AUTHOR = "revision_author"
    CREATED_AT = "created_at"
    MODIFIED_AT = "modified_at"
```

Reduce `_FIELD_FACTS` to the retained field mappings only:

```python
_FIELD_FACTS: Final[dict[str, tuple[IdentityField, TraceKind]]] = {
    "author": (IdentityField.AUTHOR, TraceKind.PERSON),
    "last_modified_by": (IdentityField.LAST_MODIFIED_BY, TraceKind.PERSON),
    "annotation_author": (IdentityField.COMMENT_AUTHOR, TraceKind.PERSON),
    "comment_author": (IdentityField.COMMENT_AUTHOR, TraceKind.PERSON),
    "revision_author": (IdentityField.REVISION_AUTHOR, TraceKind.PERSON),
    "created_at": (IdentityField.CREATED_AT, TraceKind.DOCUMENT_ENVIRONMENT),
    "modified_at": (IdentityField.MODIFIED_AT, TraceKind.DOCUMENT_ENVIRONMENT),
}
```

Do not edit `normalization.py`, native parsers, worker adapters, models, serializers, or evidence writers.

- [ ] **Step 5: Run focused Python GREEN gates**

Run:

```bash
uv run pytest tests/unit/test_comparison.py -q
uv run ruff check src/document_metadata_inspector/comparison.py tests/unit/test_comparison.py
uv run ruff format --check src/document_metadata_inspector/comparison.py tests/unit/test_comparison.py
uv run basedpyright src/document_metadata_inspector/comparison.py tests/unit/test_comparison.py
```

Expected: all commands exit zero; retired fields generate no matches; the six retained fields and incremental accumulator tests remain green.

- [ ] **Step 6: Audit scope and commit Task 1**

Run:

```bash
git diff --check
git diff -- src/document_metadata_inspector/comparison.py tests/unit/test_comparison.py
git add src/document_metadata_inspector/comparison.py tests/unit/test_comparison.py
git commit -m "feat: retire five comparison fields"
```

Expected diff: only the comparison allowlist and its tests; no extraction or schema file.

---

### Task 2: Shrink the Desktop Problem Model and Preserve Historical Compatibility

**Files:**
- Modify: `desktop/tests/render-result.test.ts`
- Modify: `desktop/tests/report-adapter.test.ts`
- Modify: `desktop/src/renderer/render-result.ts`

**Behavioral boundary:**
- `buildProblemLabelReportModel()` always returns exactly six sections in the approved order.
- Summary counts and navigation are derived from those six sections.
- Retired-only historical traces are ignored even when their values and document IDs are present.
- Mixed historical traces contribute to retained labels but not to retired labels.
- `adaptReportDocumentDetail()` continues returning retired raw metadata rows.

- [ ] **Step 1: Change the main renderer expectation to the six-label contract**

In the first `buildProblemLabelReportModel` test, include one retired field in the existing mixed trace:

```ts
fieldNames: ["author", "last_modified_by", "manager"],
```

Replace the expected section labels with:

```ts
[
  "创建人检测",
  "修改人检测",
  "批注人检测",
  "修订人检测",
  "创建时间检测",
  "修改时间检测",
]
```

Update the summary assertion to:

```ts
expect(model).toMatchObject({ riskCount: 2, safeCount: 4, relationCount: 6 });
```

Keep the existing exact pair/evidence assertions so the retained multi-field behavior cannot regress.

- [ ] **Step 2: Add historical retired-trace RED coverage**

Replace the signer-alias expectation with a compatibility test that supplies:

- `annotation_author`, which must still map to `comment_author`;
- retired-only `signature_signer_name`, `signer_identity`, `manager`, `company`, `username_path_trace`, and `template` fields with recognizable values.

Assert:

```ts
expect(model.sections).toHaveLength(6);
expect(model.sections[2]).toMatchObject({
  key: "comment_author",
  status: "risk",
  hits: [{ value: "批注用户" }],
});
expect(model).toMatchObject({ riskCount: 1, safeCount: 5 });
```

Also assert that serialized model output contains none of the retired trace values or internal field IDs. This explicitly verifies that old report data is ignored rather than hidden in a seventh internal section.

- [ ] **Step 3: Update all-safe and missing-evidence count contracts**

In `desktop/tests/render-result.test.ts`:

- change the all-safe section count from `11` to `6`;
- change the all-safe summary from `safeCount: 11` to `safeCount: 6`;
- change the one-risk missing-evidence summary from `safeCount: 10` to `safeCount: 5`;
- retain all relation-count, missing-evidence, filename-redaction, and bidder-pair assertions.

- [ ] **Step 4: Add a metadata-detail preservation test**

Import `adaptReportDocumentDetail` in `desktop/tests/report-adapter.test.ts`. Build one minimal report document containing observations with these raw names and values:

```ts
[
  { canonical_name: "manager", raw_name: "经理", raw_value: "王经理" },
  { canonical_name: "company", raw_name: "公司", raw_value: "示例公司" },
  {
    canonical_name: "signature_signer_name",
    raw_name: "签名人",
    raw_value: "张签名",
  },
  {
    canonical_name: "username_path_trace",
    raw_name: "路径用户名",
    raw_value: "review-user",
  },
  { canonical_name: "template", raw_name: "模板", raw_value: "Normal.dotm" },
]
```

Call `adaptReportDocumentDetail(report, documentId)` and assert the returned observation rows preserve every label/value pair in stable source order. This test is a characterization guard and may already pass during RED; the renderer tests are what must fail before production changes.

- [ ] **Step 5: Run focused desktop tests and capture RED**

Run from the repository root:

```bash
PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop test -- render-result.test.ts report-adapter.test.ts
```

Expected before the renderer production edit:

- detail-preservation assertion passes;
- six-section/count expectations fail because the model still returns eleven sections;
- retired historical values still create signer/manager/company/path/template risks and make the retired-trace assertions fail.

- [ ] **Step 6: Narrow the runtime problem-label registry**

In `desktop/src/renderer/render-result.ts`, set `PROBLEM_LABEL_DEFINITIONS` to exactly:

```ts
const PROBLEM_LABEL_DEFINITIONS = [
  { key: "author", label: "创建人检测" },
  { key: "last_modified_by", label: "修改人检测" },
  { key: "comment_author", label: "批注人检测" },
  { key: "revision_author", label: "修订人检测" },
  { key: "created_at", label: "创建时间检测" },
  { key: "modified_at", label: "修改时间检测" },
] as const;
```

Set the alias map to:

```ts
const PROBLEM_LABEL_ALIASES: Readonly<Record<string, string>> = {
  annotationauthor: "comment_author",
};
```

Do not remove `manager`, `company`, or `template` entries from the general metadata `LABELS` map. Do not change `DocumentKeyFields` or `report-adapter.ts`; the Task 2 detail test must pass without weakening metadata retention.

- [ ] **Step 7: Run focused desktop GREEN gates**

Run:

```bash
PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop test -- render-result.test.ts report-adapter.test.ts

PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop typecheck

PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop lint

PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop format:check
```

Expected: all commands exit zero. The detail adapter test proves no metadata was removed while the result model exposes exactly six problem labels.

- [ ] **Step 8: Audit scope and commit Task 2**

Run:

```bash
git diff --check
git diff -- desktop/src/renderer/render-result.ts desktop/tests/render-result.test.ts desktop/tests/report-adapter.test.ts
git add desktop/src/renderer/render-result.ts desktop/tests/render-result.test.ts desktop/tests/report-adapter.test.ts
git commit -m "feat: show six retained problem labels"
```

Expected diff: one problem-label registry, renderer expectations, historical-report coverage, and the detail-retention guard. No renderer layout, report schema, or detail adapter implementation change.

---

### Task 3: Update Browser Acceptance Contracts Without Erasing Historical Input

**Files:**
- Modify: `desktop/tests/e2e/renderer_real_data.py`
- Modify: `desktop/tests/e2e/problem_label_renderer.py`

**Acceptance boundary:**
- Browser output contains exactly six problem-label sections, six navigation entries, and six statuses.
- The existing synthetic `template` trace remains in the fixture as a historical retired trace and must no longer increase risk count or render a template section.
- Result hierarchy, evidence pairs, responsive layout, HTTP-error checks, all-safe rescan, and process cleanup remain unchanged.

- [ ] **Step 1: Update the real-renderer fixed label list**

Change `EXPECTED_PROBLEM_LABELS` in `desktop/tests/e2e/renderer_real_data.py` to:

```python
EXPECTED_PROBLEM_LABELS = [
    "创建人检测",
    "修改人检测",
    "批注人检测",
    "修订人检测",
    "创建时间检测",
    "修改时间检测",
]
```

Keep the existing ordering, status, legacy-panel, screenshot, console-error, and page-error assertions.

- [ ] **Step 2: Update the deterministic browser fixture counts**

In `desktop/tests/e2e/problem_label_renderer.py`, change only the expected visible contract:

```python
PROBLEM_LABEL_COUNT: Final = 6
RISK_LABEL_COUNT: Final = 2
SAFE_LABEL_COUNT: Final = 4
```

Change summary text from `11 类问题标签` to `6 类问题标签`.

Do not remove this fixture trace:

```python
_match(
    "template",
    "Normal.dotm",
    "document_environment_trace",
    ["template"],
    documents[1:3],
)
```

Keeping it ensures the browser acceptance proves historical template traces are ignored. Add an explicit assertion that neither the navigation nor result detail contains `模板检测` or `Normal.dotm`.

- [ ] **Step 3: Run Python style gates for both browser scripts**

Run:

```bash
uv run ruff check desktop/tests/e2e/renderer_real_data.py desktop/tests/e2e/problem_label_renderer.py
uv run ruff format --check desktop/tests/e2e/renderer_real_data.py desktop/tests/e2e/problem_label_renderer.py
uv run basedpyright desktop/tests/e2e/renderer_real_data.py desktop/tests/e2e/problem_label_renderer.py
```

Expected: all commands exit zero.

- [ ] **Step 4: Run the self-contained browser acceptance**

Run:

```bash
PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  uv run --with playwright==1.62.0 python desktop/tests/e2e/problem_label_renderer.py
```

Expected:

- six visible sections and six navigation entries;
- two risk labels from the retained author/last-modified-by trace;
- four safe labels;
- no template section or `Normal.dotm` leak;
- all-safe rescan shows six safe labels;
- no console/page/HTTP errors and no preview process residue.

- [ ] **Step 5: Run real-renderer acceptance when the approved real fixture is present**

With the existing approved real folder, comparison report, and frozen runtime paths, run:

```bash
PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop verify:real -- \
  --folder "$DOCMETA_REAL_FOLDER" \
  --report "$DOCMETA_REAL_REPORT" \
  --runtime "$DOCMETA_REAL_RUNTIME"
```

Before running, resolve each variable to a previously approved regular non-symlink artifact and record its SHA-256. If any fixture is unavailable, record this gate as environment-blocked rather than inventing a path or downloading runtime content. The self-contained browser acceptance in Step 4 remains mandatory.

- [ ] **Step 6: Audit scope and commit Task 3**

Run:

```bash
git diff --check
git diff -- desktop/tests/e2e/renderer_real_data.py desktop/tests/e2e/problem_label_renderer.py
git add desktop/tests/e2e/renderer_real_data.py desktop/tests/e2e/problem_label_renderer.py
git commit -m "test: align browser checks with six labels"
```

Expected diff: browser expectations only. Historical fixture input remains intentionally present.

---

### Task 4: Full Regression, Contract Audit, and Review

**Files:**
- Verify: all files changed in Tasks 1–3
- Preserve: all unrelated parent-workspace changes and untracked files

- [ ] **Step 1: Run the complete Python gate set**

Run from the project root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
```

Expected: every command exits zero. In particular, native PDF signer extraction tests must remain green, proving `signature_signer_name` is still extracted even though it no longer participates in comparison.

- [ ] **Step 2: Run the complete desktop gate set**

Run:

```bash
PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop test

PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop typecheck

PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop lint

PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop format:check

PATH=/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH \
  /Users/zhongerbing/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm \
  --dir desktop build
```

Expected: all commands exit zero. No packaging or runtime download is required for this renderer/comparison-only change.

- [ ] **Step 3: Perform a targeted contract audit**

Run:

```bash
git diff --check
git status --short
git diff --stat origin/dev-yx/design-spec-style-polish-20260810...HEAD
git diff origin/dev-yx/design-spec-style-polish-20260810...HEAD -- \
  src/document_metadata_inspector/comparison.py \
  tests/unit/test_comparison.py \
  desktop/src/renderer/render-result.ts \
  desktop/tests/render-result.test.ts \
  desktop/tests/report-adapter.test.ts \
  desktop/tests/e2e/renderer_real_data.py \
  desktop/tests/e2e/problem_label_renderer.py
```

Manually confirm:

- comparison candidate mappings contain exactly the six retained labels plus `annotation_author` alias;
- renderer problem definitions contain exactly the same six visible labels in approved order;
- no retired alias can map historical data into a hidden/visible problem section;
- general metadata translations and detail schemas still contain retired raw fields;
- native extraction and normalization files are unchanged;
- no batch-size limit, timeout, concurrency, report-size, or process-visibility behavior changed;
- all unrelated parent-workspace untracked/dirty files remain untouched.

- [ ] **Step 4: Request independent code review**

Use `superpowers:requesting-code-review` against the design commit/base and ask the reviewer to check two axes:

1. **Correctness:** five fields cannot create new matches/cards, six fields still can, mixed historical traces behave correctly, counts and navigation are six-based.
2. **Compatibility/security:** raw metadata remains available, no schema is changed, unrecognized traces fail closed in the view, and no large-batch or untrusted-input boundary regresses.

Fix every Critical/Important finding with a new focused RED test and rerun the affected task plus the full gates. Record Minor findings explicitly before deciding whether to fix or defer.

- [ ] **Step 5: Verify commit series and push only after approval**

Run:

```bash
git log --oneline --decorate origin/dev-yx/design-spec-style-polish-20260810..HEAD
git status --short --branch
git push origin dev-yx/design-spec-style-polish-20260810
git rev-parse HEAD
git rev-parse origin/dev-yx/design-spec-style-polish-20260810
```

Expected:

- design, plan, and implementation commits form a readable series;
- no uncommitted project-scoped files remain;
- local and remote branch SHAs match after push;
- parent-workspace unrelated untracked files are still present and untouched.

Do not claim the feature complete until the full verification output, browser acceptance, independent review, and remote SHA equality are all recorded.

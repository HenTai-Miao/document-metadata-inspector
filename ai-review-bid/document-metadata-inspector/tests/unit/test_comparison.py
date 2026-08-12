from document_metadata_inspector.comparison import (
    ComparisonAccumulator,
    ComparisonRequest,
    compare_documents,
)
from document_metadata_inspector.formats import identify_declared_format
from document_metadata_inspector.models import (
    DocumentReport,
    DocumentStatus,
    EvidenceObservation,
    TraceKind,
)
from document_metadata_inspector.normalization import (
    normalize_evidence_value,
    normalize_identity_text,
)

_FULLWIDTH_AUTHOR = "  \uff21lice  Zhang "


def _observation(
    canonical_name: str,
    raw_value: str,
    *,
    parser: str = "native",
) -> EvidenceObservation:
    return EvidenceObservation(
        canonical_name=canonical_name,
        raw_name=canonical_name,
        raw_value=raw_value,
        normalized_value=normalize_identity_text(raw_value),
        value_type="string",
        source_kind=f"{parser}_metadata",
        location="root",
        parser_name=parser,
        parser_version="1",
    )


def _document(
    name: str,
    *observations: EvidenceObservation,
    document_id: str | None = None,
) -> DocumentReport:
    return DocumentReport(
        display_name=name,
        source_path_sha256=document_id or name.encode().hex().ljust(64, "0")[:64],
        size_bytes=100,
        sha256=(name.encode().hex() * 64)[:64].ljust(64, "0"),
        identity=identify_declared_format(name),
        status=DocumentStatus.COMPLETE,
        observations=observations,
    )


def _numeric_observation(canonical_name: str, raw_value: int) -> EvidenceObservation:
    return EvidenceObservation(
        canonical_name=canonical_name,
        raw_name=canonical_name,
        raw_value=raw_value,
        normalized_value=normalize_evidence_value(canonical_name, raw_value),
        value_type="integer",
        source_kind="exiftool_metadata",
        location="root",
        parser_name="exiftool",
        parser_version="1",
    )


def test_exact_nfkc_case_and_whitespace_match_preserves_raw_evidence() -> None:
    first = _document("first.pdf", _observation("author", _FULLWIDTH_AUTHOR))
    second = _document("second.docx", _observation("author", "alice\tzhang"))

    result = compare_documents(ComparisonRequest(documents=(second, first)))

    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.normalized_value == "alice zhang"
    assert match.document_names == ("first.pdf", "second.docx")
    assert match.evidence_count == 2
    assert match.trace_kind is TraceKind.PERSON
    assert match.raw_values == (_FULLWIDTH_AUTHOR, "alice\tzhang")
    assert len(match.evidence) == 2
    assert all(link.observation_id for link in match.evidence)


def test_one_file_duplicates_never_create_a_cross_file_match() -> None:
    document = _document(
        "one.pdf",
        _observation("author", "Alice", parser="native"),
        _observation("author", "ALICE", parser="exiftool"),
    )

    result = compare_documents(ComparisonRequest(documents=(document,)))

    assert result.matches == ()


def test_person_fields_can_match_across_explainable_field_names() -> None:
    first = _document("first.pdf", _observation("author", "Alice"))
    second = _document(
        "second.docx",
        _observation("last_modified_by", "ALICE"),
    )

    result = compare_documents(ComparisonRequest(documents=(first, second)))

    assert len(result.matches) == 1
    assert result.matches[0].field_names == ("author", "last_modified_by")
    assert result.matches[0].canonical_name == "person_identity_trace"


def test_false_positive_guards_do_not_do_fuzzy_or_semantic_matching() -> None:
    documents = (
        _document("one.pdf", _observation("author", "张三")),
        _document("two.pdf", _observation("author", "Zhang San")),
        _document("three.pdf", _observation("author", "Alice Smith")),
        _document("four.pdf", _observation("author", "Alice")),
        _document("five.pdf", _observation("author", "Alicf")),
    )

    result = compare_documents(ComparisonRequest(documents=documents))

    assert result.matches == ()


def test_application_metadata_is_not_compared() -> None:
    first = _document("first.pdf", _observation("application", "Microsoft Word"))
    second = _document("second.docx", _observation("application", "microsoft word"))

    result = compare_documents(ComparisonRequest(documents=(first, second)))

    assert result.matches == ()


def test_non_identity_metadata_is_not_compared() -> None:
    first = _document("first.pdf", _observation("title", "Shared title"))
    second = _document("second.docx", _observation("title", "shared title"))

    result = compare_documents(ComparisonRequest(documents=(first, second)))

    assert result.matches == ()


def test_numeric_user_identifier_matches_the_same_textual_identity() -> None:
    first = _document(
        "first.xlsx",
        _numeric_observation("last_modified_by", 32522),
    )
    second = _document(
        "second.xlsx",
        _observation("last_modified_by", "32522"),
    )

    result = compare_documents(ComparisonRequest(documents=(first, second)))

    assert len(result.matches) == 1
    assert result.matches[0].normalized_value == "32522"
    assert result.matches[0].raw_values == (32522, "32522")


def test_duplicate_basenames_remain_distinct_in_match_evidence() -> None:
    first = _document(
        "bid.xlsx",
        _observation("author", "Alice"),
        document_id="1" * 64,
    )
    second = _document(
        "bid.xlsx",
        _observation("author", "ALICE"),
        document_id="2" * 64,
    )

    result = compare_documents(ComparisonRequest(documents=(first, second)))

    match = result.matches[0]
    assert match.document_names == ("bid.xlsx",)
    assert match.document_ids == ("1" * 64, "2" * 64)
    assert {link.document_id for link in match.evidence} == {"1" * 64, "2" * 64}


def test_grouped_comparison_suppresses_identity_repeated_only_inside_one_group() -> (
    None
):
    first = _document(
        "technical.pdf",
        _observation("author", "Alice"),
        document_id="1" * 64,
    )
    second = _document(
        "pricing.xlsx",
        _observation("author", "ALICE"),
        document_id="2" * 64,
    )

    result = compare_documents(
        ComparisonRequest(
            documents=(first, second),
            document_groups=(("1" * 64, "bidder-a"), ("2" * 64, "bidder-a")),
        )
    )

    assert result.matches == ()


def test_grouped_comparison_keeps_identity_spanning_two_groups() -> None:
    first = _document(
        "technical.pdf",
        _observation("author", "Alice"),
        document_id="1" * 64,
    )
    second = _document(
        "pricing.xlsx",
        _observation("author", "ALICE"),
        document_id="2" * 64,
    )
    third = _document(
        "schedule.docx",
        _observation("last_modified_by", "alice"),
        document_id="3" * 64,
    )

    result = compare_documents(
        ComparisonRequest(
            documents=(first, second, third),
            document_groups=(
                ("1" * 64, "bidder-a"),
                ("2" * 64, "bidder-a"),
                ("3" * 64, "bidder-b"),
            ),
        )
    )

    assert len(result.matches) == 1
    assert result.matches[0].document_ids == ("1" * 64, "2" * 64, "3" * 64)


def test_incremental_accumulator_matches_batch_comparison_in_any_input_order() -> None:
    documents = (
        _document(
            "technical.pdf",
            _observation("author", "Alice"),
            document_id="1" * 64,
        ),
        _document(
            "pricing.xlsx",
            _observation("author", "ALICE"),
            document_id="2" * 64,
        ),
        _document(
            "schedule.docx",
            _observation("last_modified_by", "alice"),
            document_id="3" * 64,
        ),
    )
    groups = (
        ("1" * 64, "bidder-a"),
        ("2" * 64, "bidder-a"),
        ("3" * 64, "bidder-b"),
    )
    expected = compare_documents(
        ComparisonRequest(documents=documents, document_groups=groups)
    ).matches

    accumulator = ComparisonAccumulator(document_groups=groups)
    for document in reversed(documents):
        accumulator.add(document)

    assert accumulator.matches() == expected


def test_incremental_accumulator_preserves_single_group_suppression() -> None:
    documents = (
        _document(
            "technical.pdf",
            _observation("author", "Alice"),
            document_id="1" * 64,
        ),
        _document(
            "pricing.xlsx",
            _observation("author", "ALICE"),
            document_id="2" * 64,
        ),
    )
    accumulator = ComparisonAccumulator(
        document_groups=(
            ("1" * 64, "bidder-a"),
            ("2" * 64, "bidder-a"),
        )
    )
    for document in documents:
        accumulator.add(document)

    assert accumulator.matches() == ()

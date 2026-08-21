from document_metadata_inspector.merge import merge_parser_results
from document_metadata_inspector.models import (
    EvidenceObservation,
    EvidenceStatus,
    ParserRun,
    ParserStatus,
)


def _observation(
    value: str,
    *,
    parser: str,
    raw_name: str = "dc:creator",
    canonical_name: str = "author",
) -> EvidenceObservation:
    return EvidenceObservation(
        canonical_name=canonical_name,
        raw_name=raw_name,
        raw_value=value,
        normalized_value=value.strip().casefold(),
        value_type="string",
        source_kind=f"{parser}_metadata",
        location="root",
        parser_name=parser,
        parser_version="1",
    )


def _run(
    parser: str,
    *observations: EvidenceObservation,
    status: ParserStatus = ParserStatus.SUCCEEDED,
    error_code: str | None = None,
) -> ParserRun:
    return ParserRun(
        parser_name=parser,
        parser_version="1",
        status=status,
        observations=observations,
        error_code=error_code,
    )


def test_exact_duplicates_from_the_same_source_collapse() -> None:
    observation = _observation("Alice", parser="native")

    merged = merge_parser_results((_run("native", observation, observation),))

    assert merged.observations == (observation,)


def test_independent_engines_corroborate_without_overwriting_raw_variants() -> None:
    native = _observation(" Alice ", parser="native")
    apache = _observation("ALICE", parser="apache", raw_name="dc:creator")

    merged = merge_parser_results((_run("native", native), _run("apache", apache)))

    assert len(merged.observations) == 2
    assert sorted(str(item.raw_value) for item in merged.observations) == [
        " Alice ",
        "ALICE",
    ]
    assert all(
        item.status is EvidenceStatus.CORROBORATED for item in merged.observations
    )
    assert "parser_value_conflict:author" not in merged.warnings


def test_conflicting_values_are_all_preserved_and_explicitly_warned() -> None:
    native = _observation("Alice", parser="native")
    apache = _observation("Bob", parser="apache")

    merged = merge_parser_results((_run("native", native), _run("apache", apache)))

    assert sorted(str(item.raw_value) for item in merged.observations) == [
        "Alice",
        "Bob",
    ]
    assert all(item.status is EvidenceStatus.CONFLICT for item in merged.observations)
    assert "parser_value_conflict:author" in merged.warnings
    assert all("parser_value_conflict" in item.warnings for item in merged.observations)


def test_distinct_values_from_one_parser_are_not_cross_parser_conflicts() -> None:
    first = _observation(
        "comment-a",
        parser="native",
        raw_name="comment:1",
        canonical_name="comment_reference",
    )
    second = _observation(
        "comment-b",
        parser="native",
        raw_name="comment:2",
        canonical_name="comment_reference",
    )

    merged = merge_parser_results((_run("native", first, second),))

    assert len(merged.observations) == 2
    assert all(item.status is EvidenceStatus.OBSERVED for item in merged.observations)
    assert "parser_value_conflict:comment_reference" not in merged.warnings


def test_equal_multivalue_sets_from_independent_parsers_are_corroborated() -> None:
    native = _run(
        "native",
        _observation("Alice", parser="native"),
        _observation("Bob", parser="native"),
    )
    apache = _run(
        "apache",
        _observation("Bob", parser="apache"),
        _observation("Alice", parser="apache"),
    )

    merged = merge_parser_results((native, apache))

    assert len(merged.observations) == 4
    assert all(
        item.status is EvidenceStatus.CORROBORATED for item in merged.observations
    )
    assert "parser_value_conflict:author" not in merged.warnings


def test_duplicate_provenance_combines_status_and_warnings() -> None:
    observed = _observation("Alice", parser="native").model_copy(
        update={"warnings": ("first_warning",)},
    )
    unknown = observed.model_copy(
        update={
            "status": EvidenceStatus.UNKNOWN,
            "warnings": ("second_warning",),
        }
    )

    merged = merge_parser_results((_run("native", observed, unknown),))

    assert len(merged.observations) == 1
    assert merged.observations[0].status is EvidenceStatus.UNKNOWN
    assert merged.observations[0].warnings == ("first_warning", "second_warning")


def test_unknown_tags_and_unavailable_parsers_remain_visible() -> None:
    unknown = _observation(
        "opaque",
        parser="exiftool",
        raw_name="Vendor:Unknown0x1234",
        canonical_name="exiftool.vendor_unknown0x1234",
    )
    unavailable = _run(
        "apache",
        status=ParserStatus.SKIPPED,
        error_code="parser_unavailable",
    )

    merged = merge_parser_results((_run("exiftool", unknown), unavailable))

    assert merged.observations == (unknown,)
    assert "parser_status:apache:skipped:parser_unavailable" in merged.warnings


def test_merge_order_is_deterministic_for_reversed_parser_inputs() -> None:
    first = _run("native", _observation("Alice", parser="native"))
    second = _run("apache", _observation("ALICE", parser="apache"))

    forward = merge_parser_results((first, second))
    reverse = merge_parser_results((second, first))

    assert forward == reverse

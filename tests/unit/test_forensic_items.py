"""Contract tests for singular forensic item models."""

from xlsx_metadata_forensics.models import CommentAuthor, ForensicInfo, OfficeBuild


def test_office_build_serializes_as_a_singular_typed_trace() -> None:
    # Given: a forensic report with one named Office build trace.
    office_build = OfficeBuild(
        source="docProps/app.xml",
        application="Microsoft Excel",
        version="16.0",
        build="17328",
        calculation_engine="Excel",
        calculation_id="191029",
    )
    forensics = ForensicInfo(office_build=office_build)

    # When: the forensic boundary crosses JSON serialization.
    payload = forensics.model_dump(mode="json")

    # Then: the singular model remains typed and all fields are stable.
    assert forensics.office_build == office_build
    assert payload["office_build"] == {
        "source": "docProps/app.xml",
        "application": "Microsoft Excel",
        "version": "16.0",
        "build": "17328",
        "calculation_engine": "Excel",
        "calculation_id": "191029",
    }


def test_comment_author_serialization_never_contains_comment_body_text() -> None:
    # Given: grouped authorship for two cells on one worksheet.
    comment = CommentAuthor(
        author="Reviewer",
        sheet="Sheet1",
        cells=("A1", "B2"),
        kind="legacy",
        count=2,
        source="xl/comments1.xml",
    )

    # When: the item crosses the JSON boundary.
    payload = comment.model_dump(mode="json")

    # Then: only the approved authorship fields are present.
    assert payload == {
        "author": "Reviewer",
        "sheet": "Sheet1",
        "cells": ["A1", "B2"],
        "kind": "legacy",
        "count": 2,
        "source": "xl/comments1.xml",
    }

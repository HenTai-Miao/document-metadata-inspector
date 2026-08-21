"""Contract tests for typed forensic evidence collections."""

from xlsx_metadata_forensics.models import (
    ActiveContent,
    CommentAuthor,
    CustomProperty,
    DataConnection,
    DigitalSignature,
    EmbeddedObject,
    ExternalLink,
    ForensicInfo,
    HiddenSheet,
    PathTrace,
    RevisionPart,
)


def _populated_forensic_info() -> ForensicInfo:
    return ForensicInfo(
        custom_properties=(
            CustomProperty(
                name="ProjectCode",
                value_type="lpwstr",
                value="BID-42",
                source="docProps/custom.xml",
            ),
        ),
        comment_authors=(
            CommentAuthor(
                author="Reviewer",
                sheet="Sheet1",
                cells=("A1", "B2"),
                kind="legacy",
                count=2,
                source="xl/comments1.xml",
            ),
        ),
        hidden_sheets=(
            HiddenSheet(
                name="Audit",
                state="veryHidden",
                source="xl/workbook.xml",
            ),
        ),
        external_links=(
            ExternalLink(
                target="[redacted-external-target]",
                relationship_type="externalLink",
                source="xl/_rels/workbook.xml.rels",
            ),
        ),
        data_connections=(
            DataConnection(
                name="Bid feed",
                connection_type="worksheet",
                target="[redacted-connection-target]",
                source="xl/connections.xml",
            ),
        ),
        embedded_objects=(
            EmbeddedObject(
                part_name="xl/embeddings/oleObject1.bin",
                display_name="Object 1",
                content_type="application/vnd.ms-office.oleObject",
                size_bytes=128,
                sha256="d" * 64,
                source="xl/worksheets/sheet1.xml",
            ),
        ),
        digital_signatures=(
            DigitalSignature(
                source="_xmlsignatures/sig1.xml",
                subject="CN=Signer",
                issuer="CN=Issuer",
                valid_from="2026-01-01T00:00:00Z",
                valid_to="2027-01-01T00:00:00Z",
                serial_number="01",
                certificate_sha256="e" * 64,
            ),
        ),
        office_build=None,
        active_content=(
            ActiveContent(
                kind="macro",
                part_name="xl/vbaProject.bin",
                content_type="application/vnd.ms-office.vbaProject",
                source="[Content_Types].xml",
            ),
        ),
        path_traces=(
            PathTrace(
                value="[redacted]/fixture.xlsx",
                kind="local",
                username="[redacted]",
                source="docProps/core.xml",
            ),
        ),
        revision_parts=(
            RevisionPart(
                part_name="xl/revisions/revision1.xml",
                content_type="application/vnd.ms-excel.revisionHeaders+xml",
                source="[Content_Types].xml",
            ),
        ),
    )


def test_every_populated_forensic_collection_is_exactly_tuple_shaped() -> None:
    # Given: every approved collection populated with its named item model.
    forensics = _populated_forensic_info()

    # When: the concrete container type of every collection is observed.
    container_types = (
        type(forensics.custom_properties),
        type(forensics.comment_authors),
        type(forensics.hidden_sheets),
        type(forensics.external_links),
        type(forensics.data_connections),
        type(forensics.embedded_objects),
        type(forensics.digital_signatures),
        type(forensics.active_content),
        type(forensics.path_traces),
        type(forensics.revision_parts),
    )

    # Then: every collection is an exact tuple, not another sequence type.
    assert container_types == (
        tuple,
        tuple,
        tuple,
        tuple,
        tuple,
        tuple,
        tuple,
        tuple,
        tuple,
        tuple,
    )


def test_every_forensic_collection_retains_its_named_non_empty_model() -> None:
    # Given: every approved collection populated with its named item model.
    forensics = _populated_forensic_info()

    # When: the concrete item type in each actual collection is observed.
    item_types = (
        type(forensics.custom_properties[0]),
        type(forensics.comment_authors[0]),
        type(forensics.hidden_sheets[0]),
        type(forensics.external_links[0]),
        type(forensics.data_connections[0]),
        type(forensics.embedded_objects[0]),
        type(forensics.digital_signatures[0]),
        type(forensics.active_content[0]),
        type(forensics.path_traces[0]),
        type(forensics.revision_parts[0]),
    )

    # Then: no collection can silently degrade to strings or raw mappings.
    assert item_types == (
        CustomProperty,
        CommentAuthor,
        HiddenSheet,
        ExternalLink,
        DataConnection,
        EmbeddedObject,
        DigitalSignature,
        ActiveContent,
        PathTrace,
        RevisionPart,
    )


def test_every_forensic_collection_serializes_a_non_empty_named_item() -> None:
    # Given: every actual forensic collection contains one named model.
    forensics = _populated_forensic_info()

    # When: the complete forensic boundary crosses JSON serialization.
    payload = forensics.model_dump(mode="json")

    # Then: each collection emits its model's distinguishing JSON evidence.
    assert (
        payload["custom_properties"][0]["name"],
        payload["comment_authors"][0]["author"],
        payload["hidden_sheets"][0]["name"],
        payload["external_links"][0]["target"],
        payload["data_connections"][0]["name"],
        payload["embedded_objects"][0]["part_name"],
        payload["digital_signatures"][0]["source"],
        payload["active_content"][0]["part_name"],
        payload["path_traces"][0]["value"],
        payload["revision_parts"][0]["part_name"],
    ) == (
        "ProjectCode",
        "Reviewer",
        "Audit",
        "[redacted-external-target]",
        "Bid feed",
        "xl/embeddings/oleObject1.bin",
        "_xmlsignatures/sig1.xml",
        "xl/vbaProject.bin",
        "[redacted]/fixture.xlsx",
        "xl/revisions/revision1.xml",
    )

"""Controlled report fixtures shared by export tests."""

from document_metadata_inspector.formats import identify_declared_format
from document_metadata_inspector.models import (
    DocumentReport,
    DocumentStatus,
    EmbeddedDocumentReport,
    EvidenceObservation,
    ParserRun,
    ParserStatus,
    ScanReport,
)
from document_metadata_inspector.normalization import normalize_identity_text


def make_export_report(raw_value: str = '<script>alert("x")</script>') -> ScanReport:
    """Build a serializable report containing hostile and formula-like text."""
    observations = (
        EvidenceObservation(
            canonical_name="author",
            raw_name="dc:creator",
            raw_value=raw_value,
            normalized_value=normalize_identity_text(raw_value),
            value_type="string",
            source_kind="opc_core_properties",
            location="docProps/core.xml",
            parser_name="native-office",
            parser_version="1",
        ),
        EvidenceObservation(
            canonical_name="custom_property.command",
            raw_name="Command",
            raw_value="=2+2",
            normalized_value="=2+2",
            value_type="string",
            source_kind="opc_custom_properties",
            location="docProps/custom.xml",
            parser_name="native-office",
            parser_version="1",
        ),
    )
    parser_run = ParserRun(
        parser_name="native-office",
        parser_version="1",
        status=ParserStatus.PARTIAL,
        observations=observations,
        warnings=("controlled_warning",),
    )
    child_observation = EvidenceObservation(
        canonical_name="author",
        raw_name="embedded[0].dc:creator",
        raw_value="Child <Author>",
        normalized_value="child <author>",
        value_type="string",
        source_kind="apache_tika_embedded",
        location="attachments/child.docx",
        parser_name="apache-tika",
        parser_version="3.3.2",
    )
    child = EmbeddedDocumentReport(
        resource_id="3" * 64,
        parent_id="2" * 64,
        depth=1,
        path="attachments/child.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        size_bytes=45,
        sha256="4" * 64,
        parser_names=("apache-tika",),
        observations=(child_observation,),
        warnings=("child_warning",),
    )
    parser_run = parser_run.model_copy(update={"embedded_documents": (child,)})
    document = DocumentReport(
        display_name="bid<script>.docx",
        source_path_sha256="1" * 64,
        size_bytes=123,
        sha256="2" * 64,
        identity=identify_declared_format("bid.docx"),
        status=DocumentStatus.PARTIAL,
        observations=observations,
        parser_runs=(parser_run,),
        warnings=("document_warning",),
        embedded_documents=(child,),
    )
    return ScanReport(documents=(document,), warnings=("report_warning",))

"""Shared export type contracts without package import cycles."""

from document_metadata_inspector.models import ComparisonReport, ScanReport

type ExportableReport = ScanReport | ComparisonReport

__all__ = ("ExportableReport",)

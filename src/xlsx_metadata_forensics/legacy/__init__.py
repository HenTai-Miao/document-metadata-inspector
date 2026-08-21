"""Legacy OLE package adapter — read-only, budget-aware, evidence-preserving."""

from xlsx_metadata_forensics.legacy.package import (
    LegacyWorkbookView,
    open_legacy_workbook,
)

__all__ = ("LegacyWorkbookView", "open_legacy_workbook")

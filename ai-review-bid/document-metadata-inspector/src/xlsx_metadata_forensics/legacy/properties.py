"""Parse standard OLE/CFB property streams into unified DocumentMetadata."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Final, Protocol, cast

from xlsx_metadata_forensics.legacy.package import LegacyWorkbookView
from xlsx_metadata_forensics.models import DocumentMetadata, TimestampValue
from xlsx_metadata_forensics.ooxml.properties import PropertyFacts

_UTC_SENTINEL: Final = datetime(1601, 1, 1, tzinfo=UTC)


_CHINESE_FALLBACK_ENCODINGS = ("gbk", "gb2312", "gb18030")
_CHINA_TZ: Final = timezone(timedelta(hours=8))


class _OleMetadata(Protocol):
    """Typed view of olefile's dynamically populated metadata attributes."""

    author: bytes | None
    last_saved_by: bytes | None
    create_time: datetime | None
    last_saved_time: datetime | None
    title: bytes | None
    subject: bytes | None
    comments: bytes | None
    keywords: bytes | None
    revision_number: bytes | None
    total_edit_time: int | None
    company: bytes | None
    manager: bytes | None
    creating_application: bytes | None


def _bytes_to_str(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        return value.decode("utf-8").strip() or None
    except UnicodeDecodeError:
        for enc in _CHINESE_FALLBACK_ENCODINGS:
            try:
                return value.decode(enc).strip() or None
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace").strip() or None


def _make_timestamp(dt: datetime | None) -> TimestampValue | None:
    if dt is None or dt == _UTC_SENTINEL:
        return None
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    china = aware.astimezone(_CHINA_TZ)
    raw = china.strftime("%Y-%m-%d %H:%M:%S")
    normalized = f"{aware.isoformat()} -> {raw} (CST)"
    return TimestampValue(raw=raw, normalized=normalized)


def read_legacy_properties(view: LegacyWorkbookView) -> PropertyFacts:
    """Extract standard document properties from one legacy OLE workbook.

    Returns the same ``PropertyFacts`` shape consumed by the OPC path so
    callers see a uniform metadata contract.
    """
    dynamic_meta = cast("object", view.ole.get_metadata())
    meta = cast("_OleMetadata", dynamic_meta)

    return PropertyFacts(
        metadata=DocumentMetadata(
            author=_bytes_to_str(meta.author),
            last_modified_by=_bytes_to_str(meta.last_saved_by),
            created_at=_make_timestamp(meta.create_time),
            modified_at=_make_timestamp(meta.last_saved_time),
            title=_bytes_to_str(meta.title),
            subject=_bytes_to_str(meta.subject),
            description=_bytes_to_str(meta.comments),
            keywords=_bytes_to_str(meta.keywords),
            revision=_bytes_to_str(meta.revision_number),
            total_editing_minutes=meta.total_edit_time or None,
            company=_bytes_to_str(meta.company),
            manager=_bytes_to_str(meta.manager),
            application=_bytes_to_str(meta.creating_application),
        ),
        custom_properties=(),
        warnings=(),
    )

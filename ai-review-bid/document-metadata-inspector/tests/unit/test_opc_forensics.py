from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from openpyxl.comments import Comment

from document_metadata_inspector.formats import identify_format
from document_metadata_inspector.models import InspectionLimits, JsonValue, ParserRun
from document_metadata_inspector.native import extract_native_office
from document_metadata_inspector.source import open_source_snapshot
from tests.factories import rewrite_package

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels"
    ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>
"""
_WORD_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:ins w:id="7" w:author="Revision Carol"
    w:date="2026-08-05T01:02:03Z"><w:r><w:t>changed</w:t></w:r></w:ins></w:p></w:body>
</w:document>
"""
_WORD_COMMENTS = """<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="Comment Alice" w:initials="CA"
    w:date="2026-08-05T02:03:04Z">
    <w:p><w:r><w:t>Sensitive note</w:t></w:r></w:p></w:comment>
</w:comments>
"""
_WORD_COMMENTS_EXTENDED = """<?xml version="1.0" encoding="UTF-8"?>
<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
  <w15:commentEx w15:paraId="11111111" w15:paraIdParent="22222222" w15:done="1"/>
</w15:commentsEx>
"""
_THREADED_COMMENTS = """<?xml version="1.0" encoding="UTF-8"?>
<ThreadedComments xmlns="http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments">
  <threadedComment ref="B2" dT="2026-08-05T03:04:05Z" personId="person-1"
    id="thread-1" parentId="thread-parent"><text>Thread secret</text></threadedComment>
</ThreadedComments>
"""
_PERSONS = """<?xml version="1.0" encoding="UTF-8"?>
<personList xmlns="http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments">
  <person displayName="Thread Bob" id="person-1" userId="bob@example.test"
    providerId="None"/>
</personList>
"""
_REVISION_HEADERS = """<?xml version="1.0" encoding="UTF-8"?>
<headers xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <header guid="revision-guid" dateTime="2026-08-05T04:05:06Z"
    maxSheetId="1" userName="Revision Dana"/>
</headers>
"""
_REVISION_LOG = """<?xml version="1.0" encoding="UTF-8"?>
<revisions xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <rrc rId="9" sId="1" ref="C3" action="0"/>
</revisions>
"""


def _extract(path: Path) -> ParserRun:
    with open_source_snapshot(path, InspectionLimits()) as snapshot:
        header = snapshot.stream.read(1024)
        _ = snapshot.stream.seek(0)
        return extract_native_office(snapshot, identify_format(path, header))


def _values(run: ParserRun, name: str) -> tuple[JsonValue, ...]:
    return tuple(
        item.raw_value for item in run.observations if item.canonical_name == name
    )


def _all_raw_strings(run: ParserRun) -> Iterable[str]:
    for observation in run.observations:
        if isinstance(observation.raw_value, str):
            yield observation.raw_value


def test_word_comments_and_revisions_preserve_identity_without_body_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "comments.docx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("word/document.xml", _WORD_DOCUMENT)
        archive.writestr("word/comments.xml", _WORD_COMMENTS)
        archive.writestr("word/commentsExtended.xml", _WORD_COMMENTS_EXTENDED)

    run = _extract(path)

    assert _values(run, "comment_author") == ("Comment Alice",)
    assert _values(run, "revision_author") == ("Revision Carol",)
    assert _values(run, "revision_type") == ("ins",)
    assert _values(run, "comment_reply_parent_id") == ("22222222",)
    assert _values(run, "comment_text_sha256") == (
        sha256(b"Sensitive note").hexdigest(),
    )
    assert _values(run, "comment_text_length") == (14,)
    assert "Sensitive note" not in set(_all_raw_strings(run))
    assert "changed" not in set(_all_raw_strings(run))


def test_excel_legacy_threaded_comments_and_revisions_are_linked(
    tmp_path: Path,
) -> None:
    path = tmp_path / "comments.xlsx"
    workbook = Workbook()
    try:
        sheet = workbook.active
        assert sheet is not None
        sheet["A1"].comment = Comment("Legacy secret", "Legacy Alice")
        workbook.save(path)
    finally:
        workbook.close()
    rewrite_package(
        path,
        {},
        {
            "xl/threadedComments/threadedComment1.xml": _THREADED_COMMENTS,
            "xl/persons/person.xml": _PERSONS,
            "xl/revisions/revisionHeaders.xml": _REVISION_HEADERS,
            "xl/revisions/revisionLog1.xml": _REVISION_LOG,
        },
    )

    run = _extract(path)

    assert set(_values(run, "comment_author")) == {"Legacy Alice", "Thread Bob"}
    assert _values(run, "revision_author") == ("Revision Dana",)
    assert "rrc" in _values(run, "revision_type")
    assert "A1" in _values(run, "comment_reference")
    assert "B2" in _values(run, "comment_reference")
    assert _values(run, "comment_reply_parent_id") == ("thread-parent",)
    assert sha256(b"Legacy secret").hexdigest() in _values(run, "comment_text_sha256")
    assert sha256(b"Thread secret").hexdigest() in _values(run, "comment_text_sha256")
    raw_strings = set(_all_raw_strings(run))
    assert "Legacy secret" not in raw_strings
    assert "Thread secret" not in raw_strings

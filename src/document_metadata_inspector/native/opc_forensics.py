"""Deep, metadata-only Word and Excel evidence extraction from OPC XML parts."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Protocol

from document_metadata_inspector.errors import InspectionError
from document_metadata_inspector.formats import DocumentFamily
from document_metadata_inspector.native.office_properties import (
    EvidenceSource,
    make_observation,
)

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

    from document_metadata_inspector.models import EvidenceObservation


class OpcForensicReader(Protocol):
    """Expose the small seam needed by all OPC forensic extractors."""

    names: tuple[str, ...]

    def read_xml(self, name: str) -> Element:
        """Return one bounded, entity-safe XML part."""
        ...


_WORD_REVISIONS = frozenset(
    {
        "ins",
        "del",
        "moveFrom",
        "moveTo",
        "cellIns",
        "cellDel",
        "cellMerge",
        "numberingChange",
        "pPrChange",
        "rPrChange",
        "sectPrChange",
        "tblPrChange",
        "tblGridChange",
        "trPrChange",
        "tcPrChange",
    }
)


def _local_name(value: str) -> str:
    return value.rpartition("}")[2] if "}" in value else value


def _attribute(element: Element, name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local_name(key) == name:
            return value
    return None


def _append_value(  # noqa: PLR0913, PLR0917 - private observation constructor
    observations: list[EvidenceObservation],
    source: EvidenceSource,
    canonical_name: str,
    raw_name: str,
    value: object | None,
    value_type: str,
) -> None:
    if value is None or value == "":
        return
    observations.append(
        make_observation(
            canonical_name,
            raw_name,
            value,
            value_type=value_type,
            source=source,
        )
    )


def _text_fingerprint(element: Element) -> tuple[str, int]:
    digest = sha256()
    length = 0
    for item in element.iter():
        if _local_name(item.tag) not in {"t", "delText", "text"}:
            continue
        text = item.text or ""
        digest.update(text.encode("utf-8", errors="surrogatepass"))
        length += len(text)
    return digest.hexdigest(), length


def _append_text_fingerprint(
    observations: list[EvidenceObservation],
    source: EvidenceSource,
    element: Element,
) -> None:
    digest, length = _text_fingerprint(element)
    _append_value(
        observations,
        source,
        "comment_text_sha256",
        "text_content_sha256",
        digest,
        "sha256",
    )
    _append_value(
        observations,
        source,
        "comment_text_length",
        "text_character_count",
        length,
        "integer",
    )


def _word_comments(
    root: Element,
    name: str,
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    for index, comment in enumerate(
        item for item in root if _local_name(item.tag) == "comment"
    ):
        source = EvidenceSource("opc_word_comment", f"{name}#comment[{index}]")
        for canonical, raw_name, value_type in (
            ("comment_author", "author", "string"),
            ("comment_date", "date", "datetime"),
            ("comment_initials", "initials", "string"),
            ("comment_id", "id", "identifier"),
        ):
            _append_value(
                observations,
                source,
                canonical,
                raw_name,
                _attribute(comment, raw_name),
                value_type,
            )
        _append_text_fingerprint(observations, source, comment)
    return tuple(observations)


def _word_comment_extensions(
    root: Element,
    name: str,
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    for index, element in enumerate(root.iter()):
        local = _local_name(element.tag)
        if local not in {"commentEx", "commentExtensible", "commentId", "person"}:
            continue
        source = EvidenceSource(
            "opc_word_comment_extension", f"{name}#{local}[{index}]"
        )
        field_map = (
            ("comment_author", "author", "string"),
            ("comment_id", "paraId", "identifier"),
            ("comment_durable_id", "durableId", "identifier"),
            ("comment_reply_parent_id", "paraIdParent", "identifier"),
            ("comment_date", "dateUtc", "datetime"),
            ("comment_resolved", "done", "boolean"),
            ("comment_person_user_id", "userId", "identifier"),
            ("comment_person_provider_id", "providerId", "identifier"),
        )
        for canonical, raw_name, value_type in field_map:
            _append_value(
                observations,
                source,
                canonical,
                raw_name,
                _attribute(element, raw_name),
                value_type,
            )
    return tuple(observations)


def _word_revisions(
    root: Element,
    name: str,
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    revision_index = 0
    for element in root.iter():
        revision_type = _local_name(element.tag)
        if revision_type not in _WORD_REVISIONS:
            continue
        source = EvidenceSource(
            "opc_word_revision",
            f"{name}#revision[{revision_index}]",
        )
        revision_index += 1
        _append_value(
            observations,
            source,
            "revision_type",
            "element",
            revision_type,
            "string",
        )
        for canonical, raw_name, value_type in (
            ("revision_author", "author", "string"),
            ("revision_date", "date", "datetime"),
            ("revision_id", "id", "identifier"),
        ):
            _append_value(
                observations,
                source,
                canonical,
                raw_name,
                _attribute(element, raw_name),
                value_type,
            )
    return tuple(observations)


def _read_word(
    reader: OpcForensicReader,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    observations: list[EvidenceObservation] = []
    warnings: set[str] = set()
    for name in reader.names:
        folded = name.casefold()
        if not folded.startswith("word/") or not folded.endswith(".xml"):
            continue
        try:
            root = reader.read_xml(name)
        except InspectionError:
            warnings.add("opc_word_forensic_part_unreadable")
            continue
        root_name = _local_name(root.tag)
        if root_name == "comments":
            observations.extend(_word_comments(root, name))
        if root_name in {
            "commentsEx",
            "commentsExtensible",
            "commentIds",
            "people",
        }:
            observations.extend(_word_comment_extensions(root, name))
        observations.extend(_word_revisions(root, name))
    return tuple(observations), tuple(sorted(warnings))


def _excel_persons(
    reader: OpcForensicReader,
    warnings: set[str],
) -> tuple[dict[str, str], tuple[EvidenceObservation, ...]]:
    people: dict[str, str] = {}
    observations: list[EvidenceObservation] = []
    for name in reader.names:
        folded = name.casefold()
        if not folded.startswith("xl/persons/") or not folded.endswith(".xml"):
            continue
        try:
            root = reader.read_xml(name)
        except InspectionError:
            warnings.add("opc_excel_person_part_unreadable")
            continue
        for index, person in enumerate(
            item for item in root.iter() if _local_name(item.tag) == "person"
        ):
            person_id = _attribute(person, "id")
            display_name = _attribute(person, "displayName")
            if person_id and display_name:
                people[person_id] = display_name
            source = EvidenceSource(
                "opc_excel_comment_person", f"{name}#person[{index}]"
            )
            for canonical, raw_name, value_type in (
                ("comment_person_display_name", "displayName", "string"),
                ("comment_person_id", "id", "identifier"),
                ("comment_person_user_id", "userId", "identifier"),
                ("comment_person_provider_id", "providerId", "identifier"),
            ):
                _append_value(
                    observations,
                    source,
                    canonical,
                    raw_name,
                    _attribute(person, raw_name),
                    value_type,
                )
    return people, tuple(observations)


def _excel_legacy_comments(
    reader: OpcForensicReader,
    warnings: set[str],
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    for name in reader.names:
        folded = name.casefold()
        if not folded.startswith("xl/comments") or not folded.endswith(".xml"):
            continue
        try:
            root = reader.read_xml(name)
        except InspectionError:
            warnings.add("opc_excel_comment_part_unreadable")
            continue
        authors = tuple(
            (item.text or "")
            for item in root.iter()
            if _local_name(item.tag) == "author"
        )
        comments = tuple(
            item for item in root.iter() if _local_name(item.tag) == "comment"
        )
        for index, comment in enumerate(comments):
            source = EvidenceSource("opc_excel_comment", f"{name}#comment[{index}]")
            raw_author_id = _attribute(comment, "authorId")
            author: str | None = None
            if raw_author_id is not None:
                try:
                    author_index = int(raw_author_id)
                except ValueError:
                    warnings.add("opc_excel_comment_author_invalid")
                else:
                    if 0 <= author_index < len(authors):
                        author = authors[author_index]
                    else:
                        warnings.add("opc_excel_comment_author_missing")
            _append_value(
                observations,
                source,
                "comment_author",
                "author",
                author,
                "string",
            )
            _append_value(
                observations,
                source,
                "comment_author_id",
                "authorId",
                raw_author_id,
                "integer",
            )
            _append_value(
                observations,
                source,
                "comment_reference",
                "ref",
                _attribute(comment, "ref"),
                "cell_reference",
            )
            _append_text_fingerprint(observations, source, comment)
    return tuple(observations)


def _excel_threaded_comments(
    reader: OpcForensicReader,
    people: dict[str, str],
    warnings: set[str],
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    for name in reader.names:
        folded = name.casefold()
        if not folded.startswith("xl/threadedcomments/") or not folded.endswith(".xml"):
            continue
        try:
            root = reader.read_xml(name)
        except InspectionError:
            warnings.add("opc_excel_threaded_comment_part_unreadable")
            continue
        comments = tuple(
            item for item in root.iter() if _local_name(item.tag) == "threadedComment"
        )
        for index, comment in enumerate(comments):
            source = EvidenceSource(
                "opc_excel_threaded_comment",
                f"{name}#threadedComment[{index}]",
            )
            person_id = _attribute(comment, "personId")
            author = people.get(person_id or "")
            if person_id and author is None:
                warnings.add("opc_excel_threaded_comment_person_missing")
            _append_value(
                observations,
                source,
                "comment_author",
                "person.displayName",
                author,
                "string",
            )
            for canonical, raw_name, value_type in (
                ("comment_person_id", "personId", "identifier"),
                ("comment_reference", "ref", "cell_reference"),
                ("comment_date", "dT", "datetime"),
                ("comment_id", "id", "identifier"),
                ("comment_reply_parent_id", "parentId", "identifier"),
            ):
                _append_value(
                    observations,
                    source,
                    canonical,
                    raw_name,
                    _attribute(comment, raw_name),
                    value_type,
                )
            _append_text_fingerprint(observations, source, comment)
    return tuple(observations)


def _excel_revision_xml(
    root: Element,
    name: str,
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    headers = tuple(item for item in root.iter() if _local_name(item.tag) == "header")
    for index, header in enumerate(headers):
        source = EvidenceSource(
            "opc_excel_revision_header",
            f"{name}#header[{index}]",
        )
        for canonical, raw_name, value_type in (
            ("revision_author", "userName", "string"),
            ("revision_date", "dateTime", "datetime"),
            ("revision_id", "guid", "identifier"),
        ):
            _append_value(
                observations,
                source,
                canonical,
                raw_name,
                _attribute(header, raw_name),
                value_type,
            )
    if headers:
        return tuple(observations)

    for index, revision in enumerate(root):
        revision_type = _local_name(revision.tag)
        source = EvidenceSource(
            "opc_excel_revision",
            f"{name}#revision[{index}]",
        )
        _append_value(
            observations,
            source,
            "revision_type",
            "element",
            revision_type,
            "string",
        )
        for canonical, raw_name, value_type in (
            ("revision_id", "rId", "identifier"),
            ("revision_reference", "ref", "cell_reference"),
            ("revision_sheet_id", "sId", "integer"),
            ("revision_action", "action", "integer"),
        ):
            _append_value(
                observations,
                source,
                canonical,
                raw_name,
                _attribute(revision, raw_name),
                value_type,
            )
    return tuple(observations)


def _excel_revisions(
    reader: OpcForensicReader,
    warnings: set[str],
) -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    for name in reader.names:
        folded = name.casefold()
        if not folded.startswith("xl/revisions/"):
            continue
        if folded.endswith(".bin"):
            source = EvidenceSource("opc_excel_binary_revision", name)
            _append_value(
                observations,
                source,
                "revision_binary_part",
                "part_name",
                name,
                "part_name",
            )
            warnings.add("opc_excel_binary_revision_not_decoded")
            continue
        if not folded.endswith(".xml"):
            continue
        try:
            root = reader.read_xml(name)
        except InspectionError:
            warnings.add("opc_excel_revision_part_unreadable")
            continue
        observations.extend(_excel_revision_xml(root, name))
    return tuple(observations)


def _read_excel(
    reader: OpcForensicReader,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    warnings: set[str] = set()
    people, person_observations = _excel_persons(reader, warnings)
    observations = (
        *person_observations,
        *_excel_legacy_comments(reader, warnings),
        *_excel_threaded_comments(reader, people, warnings),
        *_excel_revisions(reader, warnings),
    )
    return observations, tuple(sorted(warnings))


def read_opc_forensics(
    reader: OpcForensicReader,
    family: DocumentFamily,
) -> tuple[tuple[EvidenceObservation, ...], tuple[str, ...]]:
    """Enumerate body-free comment and revision evidence behind one interface."""
    if family is DocumentFamily.WORD:
        return _read_word(reader)
    if family is DocumentFamily.EXCEL:
        return _read_excel(reader)
    return (), ()


__all__ = ("OpcForensicReader", "read_opc_forensics")

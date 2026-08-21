"""Budgeted resource owner and immutable view for one Excel OPC package."""

import zlib
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from lzma import LZMAError
from typing import Final, Literal, final, overload
from xml.etree.ElementTree import Element, ParseError
from zipfile import ZIP_BZIP2, BadZipFile, ZipFile, ZipInfo

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from xlsx_metadata_forensics.errors import ErrorCode, ExtractionError
from xlsx_metadata_forensics.formats import ExcelFormat
from xlsx_metadata_forensics.models import ExtractionLimits

_CHUNK_BYTES: Final = 64 * 1024


def _failure(
    code: ErrorCode,
    message: str,
    source: str | None = None,
) -> ExtractionError:
    return ExtractionError(code, message, source)


@final
class PackageReader:
    """Own mutable lifecycle and read-budget state for one package view."""

    __slots__ = ("_archive", "_is_open", "_limits", "_parts", "_remaining")

    def __init__(
        self,
        archive: ZipFile,
        parts: Mapping[str, ZipInfo],
        limits: ExtractionLimits,
    ) -> None:
        self._archive = archive
        self._parts = parts
        self._limits = limits
        self._remaining = limits.max_total_read_bytes
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def require_open(self) -> None:
        if not self._is_open:
            raise _failure(
                ErrorCode.EXTRACTION_FAILED,
                "Package reads cannot outlive their owning context.",
            )

    def has_part(self, name: str) -> bool:
        return name in self._parts

    def read_bytes(self, name: str) -> bytes:
        return b"".join(self._chunks(self._part(name, ErrorCode.EXTRACTION_FAILED)))

    def read_prefix(self, name: str, length: int) -> bytes:
        info = self._part(name, ErrorCode.INVALID_EXCEL)
        chunks = self._chunks(
            info,
            chunk_bytes=length,
            preflight_bytes=length,
        )
        try:
            return next(chunks, b"")
        finally:
            chunks.close()

    def read_xml(self, name: str, failure_code: ErrorCode) -> Element:
        info = self._part(name, failure_code)
        if info.file_size > self._limits.max_xml_part_bytes:
            raise _failure(
                ErrorCode.FILE_TOO_LARGE,
                "An XML package part exceeds the configured size limit.",
                name,
            )
        payload = b"".join(self._chunks(info))
        try:
            return fromstring(
                payload,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
        except (ParseError, DefusedXmlException) as error:
            raise _failure(
                failure_code,
                "A required package XML part is malformed.",
                name,
            ) from error

    def sha256_part(self, name: str) -> str:
        digest = sha256()
        for chunk in self._chunks(self._part(name, ErrorCode.EXTRACTION_FAILED)):
            digest.update(chunk)
        return digest.hexdigest()

    def _part(self, name: str, failure_code: ErrorCode) -> ZipInfo:
        self.require_open()
        try:
            return self._parts[name]
        except KeyError as error:
            raise _failure(
                failure_code,
                "A required package part is missing.",
                name,
            ) from error

    def _chunks(
        self,
        info: ZipInfo,
        *,
        chunk_bytes: int = _CHUNK_BYTES,
        preflight_bytes: int | None = None,
    ) -> Generator[bytes, None, None]:
        self.require_open()
        required_bytes = (
            info.file_size
            if preflight_bytes is None
            else min(info.file_size, preflight_bytes)
        )
        if required_bytes > self._remaining:
            raise _failure(
                ErrorCode.FILE_TOO_LARGE,
                "The package read budget has been exhausted.",
                info.filename,
            )
        try:
            with self._archive.open(info, "r") as stream:
                while chunk := stream.read(chunk_bytes):
                    if len(chunk) > self._remaining:
                        raise _failure(
                            ErrorCode.FILE_TOO_LARGE,
                            "The package read budget has been exhausted.",
                            info.filename,
                        )
                    self._remaining -= len(chunk)
                    yield chunk
        except (BadZipFile, LZMAError, UnicodeDecodeError, zlib.error) as error:
            raise _failure(
                ErrorCode.CORRUPT_PACKAGE,
                "The ZIP package is corrupt.",
                info.filename,
            ) from error
        except NotImplementedError as error:
            raise _failure(
                ErrorCode.CORRUPT_PACKAGE,
                "The ZIP package uses an unreadable compression method.",
                info.filename,
            ) from error
        except RuntimeError as error:
            raise _failure(
                ErrorCode.ENCRYPTED_EXCEL,
                "Encrypted Excel OPC packages are not supported.",
                info.filename,
            ) from error
        except OSError as error:
            if info.compress_type == ZIP_BZIP2 and error.errno is None:
                raise _failure(
                    ErrorCode.CORRUPT_PACKAGE,
                    "The ZIP package is corrupt.",
                    info.filename,
                ) from error
            raise _failure(
                ErrorCode.EXTRACTION_FAILED,
                "A package part could not be read.",
                info.filename,
            ) from error


@dataclass(frozen=True, slots=True)
class PackageView:
    """Expose immutable inventory and bounded reads owned by one context."""

    _reader: PackageReader = field(repr=False, compare=False)
    entry_count: int
    names: tuple[str, ...]
    format: ExcelFormat

    def has_part(self, name: str) -> bool:
        """Report whether the immutable package inventory contains a part."""
        return self._reader.has_part(name)

    @overload
    def read_xml(self, name: str, *, required: Literal[True]) -> Element: ...

    @overload
    def read_xml(
        self,
        name: str,
        *,
        required: Literal[False] = False,
    ) -> Element | None: ...

    def read_xml(self, name: str, *, required: bool = False) -> Element | None:
        """Read and safely parse one XML part within both configured budgets."""
        if not self._reader.has_part(name):
            self._reader.require_open()
            if required:
                raise _failure(
                    ErrorCode.EXTRACTION_FAILED,
                    "A required package XML part is missing.",
                    name,
                )
            return None
        return self._reader.read_xml(name, ErrorCode.EXTRACTION_FAILED)

    def read_bytes(self, name: str) -> bytes:
        """Read one complete part while charging its uncompressed bytes."""
        return self._reader.read_bytes(name)

    def sha256_part(self, name: str) -> str:
        """Hash one part through bounded reads charged to the shared budget."""
        return self._reader.sha256_part(name)

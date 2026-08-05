"""Create a checksummed delivery archive around one verified executable."""

from __future__ import annotations

import argparse
import tarfile
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast
from zipfile import ZIP_DEFLATED, ZipFile

from document_metadata_inspector.resources import platform_key

if TYPE_CHECKING:
    from collections.abc import Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CHUNK_BYTES = 1024 * 1024


class _Arguments(Protocol):
    output_directory: Path


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _require_regular(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file():
        msg = f"{description} is missing or unsafe"
        raise RuntimeError(msg)


def _verify_executable_checksum(executable: Path, checksum: Path) -> None:
    lines = checksum.read_text(encoding="utf-8").splitlines()
    expected_line = f"{_hash(executable)}  {executable.name}"
    if lines != [expected_line]:
        msg = "the executable checksum file is invalid"
        raise RuntimeError(msg)


def _publish_release(
    temporary_archive: Path,
    temporary_checksum: Path,
    archive: Path,
    archive_checksum: Path,
    temporary_directory: Path,
) -> None:
    """Replace one archive/checksum pair and restore the previous pair on failure."""
    previous_archive = temporary_directory / "previous-archive"
    previous_checksum = temporary_directory / "previous-checksum"
    published_archive = False
    published_checksum = False
    try:
        if archive.exists():
            _ = archive.replace(previous_archive)
        if archive_checksum.exists():
            _ = archive_checksum.replace(previous_checksum)
        _ = temporary_archive.replace(archive)
        published_archive = True
        _ = temporary_checksum.replace(archive_checksum)
        published_checksum = True
    except BaseException:
        if published_archive and archive.exists():
            _ = archive.replace(temporary_directory / "failed-archive")
        if published_checksum and archive_checksum.exists():
            _ = archive_checksum.replace(temporary_directory / "failed-checksum")
        if previous_archive.exists():
            _ = previous_archive.replace(archive)
        if previous_checksum.exists():
            _ = previous_checksum.replace(archive_checksum)
        raise


def package_release(
    executable: Path,
    checksum: Path,
    notices: Path,
    output_directory: Path,
    key: str,
) -> Path:
    """Package a verified executable without losing Unix execute permissions."""
    for path, description in (
        (executable, "the verified executable"),
        (checksum, "the executable checksum"),
        (notices, "the third-party notices"),
    ):
        _require_regular(path, description)
    _verify_executable_checksum(executable, checksum)

    output_directory.mkdir(parents=True, exist_ok=True)
    base_name = f"document-metadata-inspector-{key}"
    archive = output_directory / (
        f"{base_name}.zip" if key.startswith("windows-") else f"{base_name}.tar.gz"
    )
    inputs = (executable, checksum, notices)
    archive_checksum = archive.with_name(f"{archive.name}.sha256")
    with TemporaryDirectory(prefix=f".{base_name}.", dir=output_directory) as temporary:
        temporary_archive = Path(temporary) / archive.name
        if key.startswith("windows-"):
            with ZipFile(
                temporary_archive,
                "x",
                ZIP_DEFLATED,
                compresslevel=9,
            ) as package:
                for path in inputs:
                    package.write(path, f"{base_name}/{path.name}")
        else:
            with tarfile.open(temporary_archive, "x:gz") as package:
                for path in inputs:
                    package.add(
                        path,
                        arcname=f"{base_name}/{path.name}",
                        recursive=False,
                    )
        temporary_checksum = Path(temporary) / archive_checksum.name
        _ = temporary_checksum.write_text(
            f"{_hash(temporary_archive)}  {archive.name}\n",
            encoding="utf-8",
            newline="\n",
        )
        _publish_release(
            temporary_archive,
            temporary_checksum,
            archive,
            archive_checksum,
            Path(temporary),
        )
    return archive


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a native release archive and SHA-256 sidecar."
    )
    _ = parser.add_argument(
        "--output-directory",
        type=Path,
        default=_PROJECT_ROOT / "release",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Package the current platform's verified one-file executable."""
    arguments = cast("_Arguments", cast("object", _parser().parse_args(argv)))
    key = platform_key()
    executable_name = "docmeta.exe" if key.startswith("windows-") else "docmeta"
    executable_directory = _PROJECT_ROOT / "dist" / key / "onefile"
    archive = package_release(
        executable_directory / executable_name,
        executable_directory / "SHA256SUMS",
        _PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
        arguments.output_directory,
        key,
    )
    print(f"Release archive is ready: {archive}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

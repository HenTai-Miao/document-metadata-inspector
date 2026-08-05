"""Security regressions for release runtime preparation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from scripts.prepare_platform_resources import (
    _materialize_internal_file_links,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from pathlib import Path


def test_materializes_internal_runtime_file_links(tmp_path: Path) -> None:
    """Safe jlink legal-file aliases become independently hashable files."""
    runtime = tmp_path / "jre"
    source = runtime / "legal/java.base/LICENSE"
    source.parent.mkdir(parents=True)
    _ = source.write_text("controlled license", encoding="utf-8")
    alias = runtime / "legal/java.sql/LICENSE"
    alias.parent.mkdir(parents=True)
    alias.symlink_to("../java.base/LICENSE")

    _materialize_internal_file_links(runtime)

    assert alias.is_file()
    assert not alias.is_symlink()
    assert alias.read_text(encoding="utf-8") == "controlled license"


def test_rejects_external_runtime_link_before_mutating_tree(tmp_path: Path) -> None:
    """A link escaping the generated runtime must fail closed."""
    runtime = tmp_path / "jre"
    runtime.mkdir()
    external = tmp_path / "outside.txt"
    _ = external.write_text("outside", encoding="utf-8")
    unsafe = runtime / "unsafe"
    unsafe.symlink_to(external)

    with pytest.raises(RuntimeError, match="outside"):
        _materialize_internal_file_links(runtime)

    assert unsafe.is_symlink()

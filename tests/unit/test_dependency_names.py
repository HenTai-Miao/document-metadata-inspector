"""Regressions for project paths that can shadow build dependencies."""

from __future__ import annotations

from pathlib import Path

import packaging.requirements


def test_project_does_not_shadow_python_packaging_library() -> None:
    module_path = Path(packaging.requirements.__file__).resolve()
    project_root = Path(__file__).resolve().parents[2]

    assert not module_path.is_relative_to(project_root / "packaging")

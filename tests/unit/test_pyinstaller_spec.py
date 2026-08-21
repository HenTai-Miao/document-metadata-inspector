"""Regressions for preserving hash-locked runtimes during freezing."""

from __future__ import annotations

from pathlib import Path


def test_runtime_tree_is_added_after_pyinstaller_analysis() -> None:
    project_root = Path(__file__).resolve().parents[2]
    specification = (project_root / "scripts/docmeta.spec").read_text(encoding="utf-8")

    analysis_end = specification.index("analysis = Analysis(")
    runtime_tree = specification.index("analysis.datas += Tree(")

    assert analysis_end < runtime_tree
    assert 'typecode="DATA"' in specification[runtime_tree:]
    assert "tools/packaged" not in specification[analysis_end:runtime_tree]

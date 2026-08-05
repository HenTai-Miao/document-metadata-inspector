"""Project Python runtime contract tests."""

import os
import sys
from pathlib import Path

import pydantic

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_is_pinned_to_uv_python_3_12_13() -> None:
    """Keep the project and static tools aligned with Python 3.12.13."""
    python_version = (PROJECT_ROOT / ".python-version").read_text(
        encoding="utf-8",
    )
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert python_version.strip() == "3.12.13"
    assert 'requires-python = ">=3.12,<3.13"' in pyproject
    assert 'pythonVersion = "3.12"' in pyproject
    assert 'target-version = "py312"' in pyproject


def test_project_runtime_is_exact_and_isolated() -> None:
    """Prove execution uses only the exact project-managed Python runtime."""
    expected_prefix = (PROJECT_ROOT / ".venv").resolve()
    pydantic_file = pydantic.__file__
    hermes_paths = tuple(entry for entry in sys.path if ".hermes" in Path(entry).parts)

    assert sys.version_info[:3] == (3, 12, 13)
    assert Path(sys.prefix).resolve() == expected_prefix
    assert pydantic_file is not None
    assert Path(pydantic_file).resolve().is_relative_to(expected_prefix)
    assert "PYTHONPATH" not in os.environ
    assert "PYTHONHOME" not in os.environ
    assert hermes_paths == ()

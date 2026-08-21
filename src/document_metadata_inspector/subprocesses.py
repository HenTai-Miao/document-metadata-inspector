"""Cross-platform subprocess launch options for invisible offline workers."""

from __future__ import annotations

import os
import subprocess


def hidden_subprocess_creation_flags() -> int:
    """Return the Windows no-console flag without changing other platforms."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


__all__ = ("hidden_subprocess_creation_flags",)

"""Regression tests for transient Windows ExifTool build locks."""

from __future__ import annotations

import pytest
from scripts import build_windows_exiftool


def _windows_error(winerror: int) -> OSError:
    error = PermissionError("controlled Windows filesystem lock")
    error.winerror = winerror
    return error


def test_retries_access_denied_until_operation_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _windows_error(5)

    monkeypatch.setattr(build_windows_exiftool, "_sleep", sleeps.append, raising=False)

    build_windows_exiftool._retry_transient_windows_lock(  # pyright: ignore[reportPrivateUsage]
        operation
    )

    assert attempts == 2
    assert sleeps == [0.1]


def test_retries_sharing_violation_until_operation_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _windows_error(32)

    monkeypatch.setattr(build_windows_exiftool, "_sleep", sleeps.append, raising=False)

    build_windows_exiftool._retry_transient_windows_lock(  # pyright: ignore[reportPrivateUsage]
        operation
    )

    assert attempts == 2
    assert sleeps == [0.1]


def test_unrelated_os_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []
    expected = OSError("controlled unrelated failure")

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise expected

    monkeypatch.setattr(build_windows_exiftool, "_sleep", sleeps.append, raising=False)

    with pytest.raises(OSError, match="controlled unrelated failure") as caught:
        build_windows_exiftool._retry_transient_windows_lock(  # pyright: ignore[reportPrivateUsage]
            operation
        )

    assert caught.value is expected
    assert attempts == 1
    assert sleeps == []


def test_persistent_windows_lock_stops_at_configured_attempt_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []
    expected = _windows_error(5)

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise expected

    monkeypatch.setattr(
        build_windows_exiftool,
        "_WINDOWS_LOCK_RETRY_ATTEMPTS",
        3,
        raising=False,
    )
    monkeypatch.setattr(build_windows_exiftool, "_sleep", sleeps.append, raising=False)

    with pytest.raises(OSError, match="controlled Windows filesystem lock") as caught:
        build_windows_exiftool._retry_transient_windows_lock(  # pyright: ignore[reportPrivateUsage]
            operation
        )

    assert caught.value is expected
    assert attempts == 3
    assert sleeps == [0.1, 0.1]

"""Verify the problem-label evidence renderer with deterministic synthetic data."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Final

from playwright.sync_api import (
    ConsoleMessage,
    Error,
    Locator,
    Page,
    Response,
    expect,
    sync_playwright,
)

type JsonObject = dict[str, object]

PROBLEM_LABEL_COUNT: Final = 6
RISK_LABEL_COUNT: Final = 2
SAFE_LABEL_COUNT: Final = 4
AUTHOR_PAIR_COUNT: Final = 3
PROCESS_STOP_TIMEOUT_SECONDS: Final = 10.0
HTTP_ERROR_STATUS: Final = 400
NAVIGATION_MIN_WIDTH: Final = 228.0
NAVIGATION_MAX_WIDTH: Final = 228.0
TITLEBAR_HEIGHT: Final = 58.0
WINDOW_CLOSE_HOVER_COLOR: Final = "rgb(196, 43, 53)"


def _require(*, condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _document_id(path: Path) -> str:
    return _sha256_text(str(path.resolve()))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _report_document(path: Path) -> JsonObject:
    content = path.read_bytes()
    return {
        "display_name": path.name,
        "source_path_sha256": _document_id(path),
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "identity": {
            "declared_format": path.suffix.removeprefix("."),
            "family": "ooxml",
            "status": "identified",
        },
        "status": "complete",
        "observations": [],
        "parser_runs": [],
        "warnings": [],
    }


def _match(
    canonical_name: str,
    value: str,
    trace_kind: str,
    field_names: list[str],
    paths: list[Path],
) -> JsonObject:
    document_ids = [_document_id(path) for path in paths]
    return {
        "canonical_name": canonical_name,
        "normalized_value": value.casefold(),
        "trace_kind": trace_kind,
        "field_names": field_names,
        "raw_values": [value for _path in paths],
        "evidence_count": len(document_ids),
        "document_ids": document_ids,
    }


def _write_report(
    report_path: Path,
    documents: list[Path],
    matches: list[JsonObject],
) -> None:
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "documents": [_report_document(path) for path in documents],
                "matches": matches,
                "warnings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _wait_for_server(port: int, process: subprocess.Popen[str]) -> None:
    for _attempt in range(200):
        if process.poll() is not None:
            message = f"preview stopped with exit code {process.returncode}"
            raise RuntimeError(message)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    message = "preview did not become ready within 20 seconds"
    raise RuntimeError(message)


def _terminate_posix_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def _terminate_windows_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        taskkill = shutil.which("taskkill")
        taskkill_succeeded = False
        if taskkill is not None:
            try:
                completed = subprocess.run(  # noqa: S603 - located OS taskkill
                    [taskkill, "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=PROCESS_STOP_TIMEOUT_SECONDS,
                )
                taskkill_succeeded = completed.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                taskkill_succeeded = False
        if not taskkill_succeeded and process.poll() is None:
            with suppress(OSError):
                process.terminate()
    try:
        process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        with suppress(OSError):
            process.kill()
        process.wait()


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        _terminate_windows_process_tree(process)
    else:
        _terminate_posix_process_group(process)


def _scan(page: Page) -> None:
    page.get_by_role("button", name="选择文件夹", exact=True).click()
    selected_folder = page.get_by_test_id("selected-folder")
    selected_folder.wait_for()
    selected_folder.get_by_test_id("start-scan").click()
    page.get_by_test_id("problem-label-section").first.wait_for(timeout=15_000)


def _rescan(page: Page) -> None:
    page.get_by_test_id("rescan").click()
    page.get_by_test_id("problem-label-section").first.wait_for(timeout=15_000)


def _problem_section(page: Page, label: str) -> Locator:
    return page.get_by_test_id("problem-label-section").filter(
        has_text=f"问题标签：{label}"  # noqa: RUF001 - product copy
    )


def _visible_box(locator: Locator, label: str) -> dict[str, float]:
    box = locator.bounding_box()
    if box is None:
        message = f"{label} is not visible"
        raise AssertionError(message)
    return box


def _assert_no_page_overflow(page: Page, viewport: str) -> None:
    fits_viewport = (
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    _require(
        condition=page.evaluate(fits_viewport),
        message=f"{viewport} page overflow",
    )


def main() -> None:  # noqa: PLR0915 - one linear browser acceptance scenario
    """Run problem-label hierarchy, responsive, and all-safe checks."""
    desktop_root = Path(__file__).resolve().parents[2]
    screenshot_root = Path(
        os.environ.get(
            "DOCMETA_SCREENSHOT_DIR",
            str(Path(tempfile.gettempdir()) / "docmeta-problem-label-preview"),
        )
    )
    screenshot_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="docmeta-problem-label-") as temporary:
        root = Path(temporary).resolve()
        bidder_names = ["公司A", "公司B", "公司C", "无异常公司"]
        file_names = ["投标函.docx", "报价清单.xlsx", "技术标.pdf", "附件.docx"]
        documents: list[Path] = []
        for bidder_name, file_name in zip(bidder_names, file_names, strict=True):
            bidder = root / bidder_name
            bidder.mkdir()
            document_path = bidder / file_name
            document_path.write_bytes(f"synthetic-{bidder_name}".encode())
            documents.append(document_path)

        report_path = root / "comparison-report.json"
        _write_report(
            report_path,
            documents,
            [
                _match(
                    "person_identity_trace",
                    "李建国",
                    "person_trace",
                    ["author", "last_modified_by"],
                    documents[0:3],
                ),
                _match(
                    "template",
                    "Normal.dotm",
                    "document_environment_trace",
                    ["template"],
                    documents[1:3],
                ),
            ],
        )

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        pnpm = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm")
        if pnpm is None:
            message = "pnpm executable was not found"
            raise RuntimeError(message)
        process = subprocess.Popen(  # noqa: S603 - fixed local pnpm command
            [
                pnpm,
                "preview:real",
                "--",
                "--folder",
                str(root),
                "--report",
                str(report_path),
                "--port",
                str(port),
            ],
            cwd=desktop_root,
            text=True,
            start_new_session=os.name != "nt",
        )

        try:
            _wait_for_server(port, process)
            console_errors: list[str] = []
            page_errors: list[str] = []
            response_errors: list[str] = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=os.environ.get("DOCMETA_CHROMIUM_EXECUTABLE"),
                )
                page = browser.new_page(viewport={"width": 1440, "height": 900})

                def record_console(message: ConsoleMessage) -> None:
                    if message.type == "error":
                        console_errors.append(f"{message.text} @ {message.location}")

                def record_page_error(error: Error) -> None:
                    page_errors.append(str(error))

                def record_response(response: Response) -> None:
                    if response.status >= HTTP_ERROR_STATUS:
                        response_errors.append(f"{response.status} {response.url}")

                page.on("console", record_console)
                page.on("pageerror", record_page_error)
                page.on("response", record_response)
                page.goto(base_url)
                page.wait_for_load_state("networkidle")

                minimize = page.get_by_test_id("window-minimize")
                maximize = page.get_by_test_id("window-maximize")
                close = page.get_by_test_id("window-close")
                expect(minimize).to_have_attribute("aria-label", "最小化窗口")
                expect(minimize).to_have_attribute("title", "最小化窗口")
                expect(maximize).to_have_attribute("aria-label", "最大化窗口")
                expect(maximize).to_have_attribute("title", "最大化窗口")
                expect(close).to_have_attribute("aria-label", "关闭窗口")
                expect(close).to_have_attribute("title", "关闭窗口")

                topbar_box = _visible_box(page.locator(".topbar"), "custom titlebar")
                _require(
                    condition=topbar_box["height"] == TITLEBAR_HEIGHT,
                    message={"unexpected_titlebar_height": topbar_box["height"]},
                )

                maximize.click()
                maximize = page.get_by_test_id("window-maximize")
                expect(maximize).to_have_attribute("aria-label", "还原窗口")
                expect(maximize).to_have_attribute("title", "还原窗口")
                maximize.click()
                maximize = page.get_by_test_id("window-maximize")
                expect(maximize).to_have_attribute("aria-label", "最大化窗口")

                maximize.focus()
                page.keyboard.press("Tab")
                active_test_id = page.evaluate(
                    "document.activeElement?.getAttribute('data-testid')"
                )
                close_outline = close.evaluate(
                    "node => getComputedStyle(node).outlineStyle"
                )
                _require(
                    condition=active_test_id == "window-close",
                    message={"unexpected_keyboard_focus": active_test_id},
                )
                _require(
                    condition=close_outline != "none",
                    message={"missing_close_focus_outline": close_outline},
                )

                close.hover()
                close_hover_background = close.evaluate(
                    "node => getComputedStyle(node).backgroundColor"
                )
                _require(
                    condition=close_hover_background == WINDOW_CLOSE_HOVER_COLOR,
                    message={
                        "unexpected_close_hover_background": close_hover_background
                    },
                )

                _scan(page)

                expect(page.get_by_test_id("problem-label-section")).to_have_count(
                    PROBLEM_LABEL_COUNT
                )
                expect(page.get_by_test_id("problem-label-name")).to_have_count(
                    PROBLEM_LABEL_COUNT
                )
                expect(
                    page.get_by_test_id("problem-label-status").filter(
                        has_text="有风险"
                    )
                ).to_have_count(RISK_LABEL_COUNT)
                expect(
                    page.get_by_test_id("problem-label-status").filter(
                        has_text="无风险"
                    )
                ).to_have_count(SAFE_LABEL_COUNT)
                expect(page.get_by_test_id("problem-label-summary")).to_contain_text(
                    "6 类问题标签"
                )

                workspace = page.get_by_test_id("problem-label-workspace")
                navigation = page.get_by_test_id("problem-label-nav")
                detail = page.get_by_test_id("problem-label-detail")
                expect(workspace).to_have_count(1)
                expect(navigation).to_have_count(1)
                expect(detail).to_have_count(1)
                expect(
                    navigation.get_by_test_id("problem-label-nav-item")
                ).to_have_count(PROBLEM_LABEL_COUNT)
                expect(navigation.get_by_role("link")).to_have_count(
                    PROBLEM_LABEL_COUNT
                )
                expect(detail.get_by_test_id("problem-label-section")).to_have_count(
                    PROBLEM_LABEL_COUNT
                )
                expect(navigation).to_contain_text("创建人检测")
                expect(navigation).to_contain_text("无风险")
                for retired_content in ("模板检测", "Normal.dotm"):
                    expect(navigation).not_to_contain_text(retired_content)
                    expect(detail).not_to_contain_text(retired_content)

                author_section = _problem_section(page, "创建人检测")
                modified_section = _problem_section(page, "修改人检测")
                safe_section = _problem_section(page, "批注人检测")
                expect(author_section).to_have_count(1)
                expect(modified_section).to_have_count(1)
                expect(safe_section).to_have_count(1)
                expect(author_section).to_contain_text("李建国")
                expect(modified_section).to_contain_text("李建国")
                expect(
                    author_section.get_by_test_id("problem-company-pair")
                ).to_have_count(AUTHOR_PAIR_COUNT)
                expect(author_section).to_contain_text("公司A ↔ 公司B")
                expect(author_section).to_contain_text("投标函.docx")
                expect(author_section).to_contain_text("报价清单.xlsx")
                expect(safe_section).to_contain_text("无风险")
                expect(safe_section).to_contain_text("0 个命中值 · 0 组公司关系")

                topbar_background = page.locator(".topbar").evaluate(
                    "node => getComputedStyle(node).backgroundColor"
                )
                value_background = author_section.locator(
                    ".pl-value-head"
                ).first.evaluate("node => getComputedStyle(node).backgroundColor")
                relation_background = author_section.locator(
                    ".pl-pair-name"
                ).first.evaluate("node => getComputedStyle(node).backgroundColor")
                _require(
                    condition=topbar_background == "rgb(11, 49, 90)",
                    message={"unexpected_topbar_background": topbar_background},
                )
                _require(
                    condition=value_background == "rgba(0, 0, 0, 0)",
                    message={"unexpected_value_background": value_background},
                )
                _require(
                    condition=relation_background == "rgb(250, 251, 252)",
                    message={"unexpected_relation_background": relation_background},
                )

                navigation_box = _visible_box(navigation, "desktop navigation")
                detail_box = _visible_box(detail, "desktop detail")
                _require(
                    condition=(
                        NAVIGATION_MIN_WIDTH
                        <= navigation_box["width"]
                        <= NAVIGATION_MAX_WIDTH
                    ),
                    message={"unexpected_navigation_width": navigation_box["width"]},
                )
                _require(
                    condition=detail_box["x"]
                    > navigation_box["x"] + navigation_box["width"],
                    message={
                        "navigation_box": navigation_box,
                        "detail_box": detail_box,
                    },
                )

                _require(
                    condition=page.get_by_test_id("risk-matrix").count() == 0,
                    message="legacy matrix must be absent",
                )
                _require(
                    condition=page.get_by_test_id("risk-evidence-panel").count() == 0,
                    message="legacy evidence panel must be absent",
                )
                _assert_no_page_overflow(page, "1440")
                page.screenshot(
                    path=screenshot_root / "01-problem-labels-1440.png",
                    full_page=True,
                )

                page.set_viewport_size({"width": 1280, "height": 800})
                _assert_no_page_overflow(page, "1280")
                page.screenshot(
                    path=screenshot_root / "02-problem-labels-1280.png",
                    full_page=True,
                )

                page.set_viewport_size({"width": 1024, "height": 720})
                _assert_no_page_overflow(page, "1024")
                page.screenshot(
                    path=screenshot_root / "03-problem-labels-1024.png",
                    full_page=True,
                )

                page.set_viewport_size({"width": 980, "height": 700})
                _assert_no_page_overflow(page, "980")
                page.screenshot(
                    path=screenshot_root / "04-problem-labels-980.png",
                    full_page=True,
                )

                page.set_viewport_size({"width": 760, "height": 760})
                _assert_no_page_overflow(page, "760")
                navigation_box = _visible_box(navigation, "stacked navigation")
                detail_box = _visible_box(detail, "stacked detail")
                _require(
                    condition=navigation_box["y"] < detail_box["y"],
                    message={
                        "navigation_box": navigation_box,
                        "detail_box": detail_box,
                    },
                )
                page.screenshot(
                    path=screenshot_root / "05-problem-labels-760.png",
                    full_page=True,
                )

                page.set_viewport_size({"width": 390, "height": 844})
                _assert_no_page_overflow(page, "390")
                page.screenshot(
                    path=screenshot_root / "06-problem-labels-390.png",
                    full_page=True,
                )

                _write_report(report_path, documents, [])
                _rescan(page)
                expect(page.get_by_test_id("problem-label-section")).to_have_count(
                    PROBLEM_LABEL_COUNT
                )
                expect(
                    page.get_by_test_id("problem-label-status").filter(
                        has_text="无风险"
                    )
                ).to_have_count(PROBLEM_LABEL_COUNT)
                expect(page.get_by_test_id("problem-hit-value")).to_have_count(0)
                page.screenshot(
                    path=screenshot_root / "07-problem-labels-all-safe.png",
                    full_page=True,
                )

                browser.close()

            _require(
                condition=console_errors == [],
                message={
                    "console_errors": console_errors,
                    "response_errors": response_errors,
                },
            )
            _require(condition=page_errors == [], message=page_errors)
            _require(condition=response_errors == [], message=response_errors)
        finally:
            _terminate_process_tree(process)

    print(  # noqa: T201 - CLI acceptance-test result
        f"problem-label renderer checks passed; screenshots: {screenshot_root}"
    )


if __name__ == "__main__":
    main()

"""Exercise the real renderer with the downloaded public document report."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Error, sync_playwright

EXPECTED_BIDDER_COUNT = 2
EXPECTED_PARSER_RUN_COUNT = 3


def _require(*, condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    """Exercise selection, stop/restart, and the real result renderer."""
    base_url = os.environ.get("DOCMETA_PREVIEW_URL", "http://127.0.0.1:4175")
    default_screenshot_dir = Path(tempfile.gettempdir()) / "docmeta-electron-preview"
    screenshot_dir = Path(
        os.environ.get("DOCMETA_SCREENSHOT_DIR", str(default_screenshot_dir))
    )
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        executable_path = os.environ.get("DOCMETA_CHROMIUM_EXECUTABLE")
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=executable_path,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        def record_console(message: ConsoleMessage) -> None:
            if message.type == "error":
                console_errors.append(message.text)

        def record_page_error(error: Error) -> None:
            page_errors.append(str(error))

        page.on("console", record_console)
        page.on("pageerror", record_page_error)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        page.get_by_test_id("choose-folder").click()
        page.get_by_test_id("selected-folder").wait_for()
        _require(
            condition=page.get_by_test_id("bidder-count").inner_text() == "2",
            message="bidder count",
        )
        _require(
            condition=page.get_by_test_id("file-count").inner_text() == "8",
            message="file count",
        )
        page.screenshot(path=screenshot_dir / "01-selection.png", full_page=True)

        page.get_by_test_id("start-scan").click()
        page.get_by_test_id("stop-scan").wait_for()
        page.get_by_test_id("stop-scan").click()
        page.get_by_test_id("selected-folder").get_by_text(
            "核验已停止\uff0c可以重新开始",
            exact=True,
        ).wait_for()
        page.get_by_test_id("start-scan").wait_for()

        page.get_by_test_id("start-scan").click()
        page.get_by_test_id("result-page").wait_for(timeout=15_000)
        _require(
            condition=page.get_by_test_id("bidder-card").count()
            == EXPECTED_BIDDER_COUNT,
            message="bidder card count",
        )
        _require(
            condition=page.get_by_test_id("summary-complete").inner_text() == "8 / 8",
            message="complete summary",
        )
        _require(
            condition=page.get_by_test_id("trace-danger").count() == 0,
            message="danger traces",
        )
        _require(
            condition=page.get_by_text("未发现跨投标人人员痕迹").count() == 1,
            message="clear person-trace conclusion",
        )
        _require(
            condition="WPS 文字" in page.get_by_test_id("trace-neutral").inner_text(),
            message="neutral software trace",
        )
        page.get_by_test_id("bidder-connection").first.wait_for()
        _require(
            condition=page.get_by_test_id("bidder-connection").count() >= 1,
            message="bidder-card SVG connection",
        )
        page.locator(".document-summary-row").first.click()
        _require(
            condition=page.locator(".parser-run-row").count()
            >= EXPECTED_PARSER_RUN_COUNT,
            message="expandable parser evidence",
        )
        page.screenshot(path=screenshot_dir / "02-result.png", full_page=True)

        _require(condition=not console_errors, message=console_errors)
        _require(condition=not page_errors, message=page_errors)
        browser.close()


if __name__ == "__main__":
    main()

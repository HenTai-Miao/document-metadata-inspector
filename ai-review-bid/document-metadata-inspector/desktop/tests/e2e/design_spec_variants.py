"""Exercise the static design-spec launcher and ready state."""

# ruff: noqa: PLR2004, RUF001, S101

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Error, Page, sync_playwright

INDEX = Path(__file__).parents[2] / "mock" / "design-spec-variants" / "index.html"


def test_launcher_and_ready(page: Page) -> None:
    """Load a variant and confirm the immutable demonstration selection."""
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    assert page.get_by_test_id("variant-card").count() == 3
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    page.get_by_test_id("load-demo").click()
    page.get_by_test_id("selected-folder").wait_for()
    assert page.get_by_test_id("bidder-count").inner_text() == "4"
    assert page.get_by_test_id("file-count").inner_text() == "16"


def test_back_returns_to_launcher(page: Page) -> None:
    """Restore the launcher when history returns to the empty hash route."""
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    assert page.get_by_test_id("selection-page").count() == 1
    page.go_back()
    page.get_by_test_id("variant-card").first.wait_for()
    assert page.get_by_test_id("variant-card").count() == 3


def test_scan_can_stop_then_restart_to_a_complete_report(page: Page) -> None:
    """Stop a deterministic scan without a report, then restart it to completion."""
    page.add_init_script("window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__ = 12")
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    page.get_by_test_id("load-demo").click()
    page.get_by_test_id("start-scan").click()
    page.get_by_test_id("stop-scan").wait_for()
    page.get_by_test_id("stop-scan").click()
    page.get_by_text("核验已停止，未生成报告", exact=True).wait_for()
    page.get_by_test_id("start-scan").click()
    page.get_by_test_id("report-page").wait_for(timeout=5_000)
    assert page.get_by_test_id("scan-summary").get_attribute("data-complete") == "16"


def test_simulated_scan_failure_can_retry_without_a_partial_report(page: Page) -> None:
    """Expose the secondary failure demo, then retry from its no-report state."""
    page.add_init_script("window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__ = 12")
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    page.get_by_test_id("load-demo").click()
    page.get_by_test_id("start-scan").click()
    page.get_by_text("演示场景", exact=True).click()
    page.get_by_test_id("simulate-scan-failure").click()
    page.get_by_text("这是原型模拟故障", exact=False).wait_for()
    assert page.get_by_test_id("report-page").count() == 0
    page.get_by_test_id("retry-scan").click()
    page.get_by_test_id("report-page").wait_for(timeout=5_000)


def main() -> None:
    """Run the journey in headless Chromium and reject browser errors."""
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshot_dir = Path(tempfile.gettempdir()) / "docmeta-design-spec-variants"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=os.environ.get("DOCMETA_CHROMIUM_EXECUTABLE"),
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            def record_console(message: ConsoleMessage) -> None:
                if message.type == "error":
                    console_errors.append(message.text)

            def record_page_error(error: Error) -> None:
                page_errors.append(str(error))

            page.on("console", record_console)
            page.on("pageerror", record_page_error)
            test_launcher_and_ready(page)
            page.screenshot(path=screenshot_dir / "task-2-ready.png", full_page=True)
            test_back_returns_to_launcher(page)
            test_scan_can_stop_then_restart_to_a_complete_report(page)
            test_simulated_scan_failure_can_retry_without_a_partial_report(page)
            assert not console_errors, console_errors
            assert not page_errors, page_errors
        finally:
            browser.close()


if __name__ == "__main__":
    main()

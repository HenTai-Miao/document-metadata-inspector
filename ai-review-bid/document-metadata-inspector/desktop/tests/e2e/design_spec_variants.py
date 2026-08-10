"""Exercise the static design-spec launcher and ready state."""

# ruff: noqa: PLR2004, S101

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
            assert not console_errors, console_errors
            assert not page_errors, page_errors
        finally:
            browser.close()


if __name__ == "__main__":
    main()

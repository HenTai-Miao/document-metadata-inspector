"""Exercise the real renderer with the downloaded public document report."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Error, sync_playwright

EXPECTED_PROBLEM_LABELS = [
    "创建人检测",
    "修改人检测",
    "批注人检测",
    "修订人检测",
    "创建时间检测",
    "修改时间检测",
]


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

        page.get_by_role("button", name="选择文件夹", exact=True).click()
        selected_folder = page.get_by_test_id("selected-folder")
        selected_folder.wait_for()
        _require(
            condition=page.get_by_test_id("bidder-count").inner_text() == "2",
            message="bidder count",
        )
        _require(
            condition=page.get_by_test_id("file-count").inner_text() == "8",
            message="file count",
        )
        page.screenshot(path=screenshot_dir / "01-selection.png", full_page=True)

        selected_folder.get_by_test_id("start-scan").click()
        page.get_by_role("button", name="停止核验", exact=True).wait_for()
        page.get_by_role("button", name="停止核验", exact=True).click()
        selected_folder.get_by_text(
            "核验已停止\uff0c可以重新开始",
            exact=True,
        ).wait_for()
        selected_folder.get_by_test_id("start-scan").wait_for()

        selected_folder.get_by_test_id("start-scan").click()
        page.get_by_test_id("result-page").wait_for(timeout=15_000)
        sections = page.get_by_test_id("problem-label-section")
        statuses = page.get_by_test_id("problem-label-status")
        _require(
            condition=sections.count() == len(EXPECTED_PROBLEM_LABELS),
            message="all problem labels must remain visible",
        )
        _require(
            condition=page.get_by_test_id("problem-label-name").all_inner_texts()
            == [
                f"问题标签：{label}"  # noqa: RUF001 - product copy
                for label in EXPECTED_PROBLEM_LABELS
            ],
            message="problem-label order and naming",
        )
        _require(
            condition=statuses.count() == len(EXPECTED_PROBLEM_LABELS),
            message="every problem label must show a result status",
        )
        _require(
            condition=page.get_by_test_id("problem-safe-result").count() >= 1,
            message="safe labels must be shown instead of hidden",
        )
        _require(
            condition=page.get_by_test_id("risk-matrix").count() == 0,
            message="legacy risk matrix must be absent",
        )
        _require(
            condition=page.get_by_test_id("risk-evidence-panel").count() == 0,
            message="legacy evidence panel must be absent",
        )

        result_text = page.get_by_test_id("result-page").inner_text()
        for forbidden in [
            "公司名无重复",
            "作者无重复",
            "模板无重复",
            "未发现跨投标人人员痕迹",
        ]:
            _require(
                condition=forbidden not in result_text,
                message=f"legacy safe content leaked: {forbidden}",
            )
        page.screenshot(path=screenshot_dir / "02-result.png", full_page=True)

        _require(condition=not console_errors, message=console_errors)
        _require(condition=not page_errors, message=page_errors)
        browser.close()


if __name__ == "__main__":
    main()

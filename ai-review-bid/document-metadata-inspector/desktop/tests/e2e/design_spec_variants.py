"""Exercise the static design-spec launcher and ready state."""

# ruff: noqa: PLR2004, RUF001, S101

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Error, Locator, Page, sync_playwright

INDEX = Path(__file__).parents[2] / "mock" / "design-spec-variants" / "index.html"
VARIANT_NAMES = {
    "guided": "引导式核验工作台",
    "verdict": "结论先行审查报告",
    "matrix": "证据矩阵控制台",
}


def open_completed_variant(page: Page, variant: str) -> None:
    """Enter one variant and complete its deterministic demonstration scan."""
    page.add_init_script("window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__ = 12")
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    page.get_by_test_id("variant-card").filter(has_text=VARIANT_NAMES[variant]).click()
    page.get_by_test_id("load-demo").click()
    page.get_by_test_id("start-scan").click()
    page.get_by_test_id("report-page").wait_for(timeout=5_000)


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
    """Restore the launcher on Back and the same variant again on Forward."""
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    assert page.get_by_test_id("selection-page").count() == 1
    page.go_back()
    page.get_by_test_id("variant-card").first.wait_for()
    assert page.get_by_test_id("variant-card").count() == 3
    page.go_forward()
    page.get_by_test_id("selection-page").wait_for()
    assert page.get_by_test_id("guided-shell").count() == 1


def test_direct_hash_navigation_switches_active_variants(page: Page) -> None:
    """Keep direct hash entry and external hash changes functional."""
    page.goto(f"{INDEX.resolve().as_uri()}#verdict")
    page.wait_for_load_state("load")
    page.get_by_test_id("selection-page").wait_for()
    assert page.get_by_test_id("verdict-shell").count() == 1
    page.evaluate("location.hash = 'matrix'")
    page.locator(".matrix-shell").wait_for()


def test_scan_can_stop_then_restart_to_a_complete_report(page: Page) -> None:
    """Stop a deterministic scan without a report, then restart it to completion."""
    page.add_init_script("window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__ = 100")
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


def test_launcher_reentry_stops_an_active_scan_before_restart(page: Page) -> None:
    """Back navigation must leave an active scan restartable instead of frozen."""
    page.add_init_script("window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__ = 100")
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    page.get_by_test_id("load-demo").click()
    page.get_by_test_id("start-scan").click()
    page.get_by_test_id("stop-scan").wait_for()
    page.go_back()
    page.get_by_test_id("variant-card").first.wait_for()
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    page.get_by_text("核验已停止，未生成报告", exact=True).wait_for()
    page.get_by_test_id("start-scan").click()
    page.get_by_test_id("report-page").wait_for(timeout=5_000)
    assert page.get_by_test_id("scan-summary").get_attribute("data-complete") == "16"


def test_simulated_scan_failure_can_retry_without_a_partial_report(page: Page) -> None:
    """Expose the secondary failure demo, then retry from its no-report state."""
    page.add_init_script("window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__ = 100")
    page.goto(INDEX.resolve().as_uri())
    page.wait_for_load_state("load")
    page.get_by_test_id("variant-card").filter(has_text="引导式核验工作台").click()
    page.get_by_test_id("load-demo").click()
    page.get_by_test_id("start-scan").click()
    scenario_summary = page.get_by_text("演示场景", exact=True)
    scenario_height = scenario_summary.evaluate(
        "element => element.getBoundingClientRect().height",
    )
    assert scenario_height >= 28
    scenario_summary.click()
    page.get_by_test_id("simulate-scan-failure").click()
    page.get_by_text("这是原型模拟故障", exact=False).wait_for()
    assert page.get_by_test_id("report-page").count() == 0
    page.get_by_test_id("retry-scan").click()
    page.get_by_test_id("report-page").wait_for(timeout=5_000)
    assert page.get_by_test_id("scan-summary").get_attribute("data-complete") == "16"


def test_guided_report(page: Page) -> None:
    """Filter and trace Guided evidence into prefiltered document metadata."""
    open_completed_variant(page, "guided")
    shell = page.get_by_test_id("guided-shell")
    assert shell.get_by_test_id("workflow-step").count() == 5
    assert shell.locator('[data-step="report"][aria-current="step"]').count() == 1
    assert shell.get_by_test_id("guided-task-card").count() == 4
    assert shell.get_by_test_id("trace-row").count() == 5
    assert shell.get_by_test_id("trace-count").inner_text() == "5"

    shell.get_by_test_id("report-filter-danger").click()
    assert shell.get_by_test_id("trace-row").count() == 2
    shell.get_by_test_id("trace-toggle").first.click()
    disclosure = shell.get_by_test_id("trace-disclosure")
    disclosure.get_by_text("原始值", exact=True).wait_for()
    for evidence in [
        "作者",
        "王磊",
        "华远建设",
        "启明工程",
        "华远建设/技术方案.docx",
        "启明工程/技术方案.docx",
        "原生解析器",
        "Apache Tika",
        "ExifTool",
    ]:
        assert evidence in disclosure.inner_text()
    assert (
        shell.get_by_test_id("trace-toggle").first.get_attribute("aria-expanded")
        == "true"
    )
    assert shell.get_by_test_id("trace-toggle").first.evaluate(
        "element => element === document.activeElement",
    )

    shell.get_by_test_id("show-metadata").first.click()
    metadata = page.get_by_test_id("metadata-page")
    metadata.wait_for()
    assert metadata.locator('[data-step="metadata"][aria-current="step"]').count() == 1
    assert metadata.get_by_test_id("metadata-search").input_value() == "技术方案.docx"
    assert (
        metadata.locator('[data-bidder-id="bidder-a"]').get_attribute("aria-pressed")
        == "true"
    )
    assert metadata.get_by_test_id("metadata-document-card").count() == 1

    metadata.locator('[data-bidder-id=""]').click()
    assert metadata.get_by_test_id("metadata-document-card").count() == 3
    metadata.get_by_test_id("metadata-duplicates-only").click()
    assert metadata.get_by_test_id("metadata-document-card").count() == 4
    metadata.get_by_test_id("metadata-search").fill("报价.xlsx")
    metadata.get_by_test_id("metadata-search").press("Tab")
    assert metadata.get_by_test_id("metadata-document-card").count() == 4

    page.get_by_test_id("metadata-back").click()
    page.get_by_test_id("report-page").wait_for()
    assert page.get_by_test_id("trace-row").count() == 2
    assert (
        page.get_by_test_id("trace-toggle").first.get_attribute("aria-expanded")
        == "true"
    )


def open_zhangmin_report_trace(page: Page) -> Locator:
    """Open the danger report and return the zhangmin metadata action."""
    open_completed_variant(page, "guided")
    page.get_by_test_id("report-filter-danger").click()
    origin_row = page.get_by_test_id("trace-row").nth(1)
    origin_locate = origin_row.get_by_test_id("show-metadata")
    origin_locate.scroll_into_view_if_needed()
    return origin_locate


def instrument_guided_render_count(page: Page) -> None:
    """Count real Guided renderer calls made by the delegated controller."""
    page.evaluate(
        """() => {
          const original = window.DocmetaPrototype.renderers.guided;
          window.__GUIDED_RENDER_COUNT__ = 0;
          window.DocmetaPrototype.renderers.guided = state => {
            window.__GUIDED_RENDER_COUNT__ += 1;
            return original(state);
          };
        }""",
    )


def test_guided_metadata_navigation_is_atomic_and_focuses_destination(
    page: Page,
) -> None:
    """Navigate once to the selected XLSX evidence and reveal its summary."""
    origin_locate = open_zhangmin_report_trace(page)
    instrument_guided_render_count(page)
    origin_locate.click()
    metadata = page.get_by_test_id("metadata-page")
    metadata.wait_for()
    assert page.evaluate("window.__GUIDED_RENDER_COUNT__") == 1
    assert (
        metadata.get_by_test_id("metadata-duplicates-only").get_attribute(
            "aria-checked",
        )
        == "true"
    )
    assert metadata.get_by_test_id("metadata-search").input_value() == "报价.xlsx"
    selected_summary = metadata.locator(
        '[data-evidence-id="bidder-c-document-2"]',
    )
    assert selected_summary.evaluate("element => element === document.activeElement")
    assert selected_summary.evaluate(
        """element => {
          const bounds = element.getBoundingClientRect();
          return bounds.top >= 0 && bounds.bottom <= window.innerHeight;
        }""",
    )
    metadata.get_by_text("搜索文件名、投标人或字段值", exact=True).wait_for()


def test_guided_metadata_search_keeps_keyboard_focus(page: Page) -> None:
    """Keep the search field useful after its immutable-state rerender."""
    open_zhangmin_report_trace(page).click()
    metadata = page.get_by_test_id("metadata-page")
    metadata.wait_for()
    search = metadata.get_by_test_id("metadata-search")
    search.fill("zhangmin")
    search.press("Tab")
    assert search.input_value() == "zhangmin"
    assert search.evaluate("element => element === document.activeElement")
    assert metadata.get_by_test_id("metadata-document-card").count() == 1


def test_guided_report_return_restores_focus_and_scroll(page: Page) -> None:
    """Return once to the originating trace control and report scroll offset."""
    origin_locate = open_zhangmin_report_trace(page)
    origin_scroll = page.evaluate("window.scrollY")
    origin_locate.click()
    metadata = page.get_by_test_id("metadata-page")
    metadata.wait_for()
    instrument_guided_render_count(page)
    page.evaluate("window.__GUIDED_RENDER_COUNT__ = 0")
    metadata.get_by_test_id("metadata-back").click()
    page.get_by_test_id("report-page").wait_for()
    assert page.evaluate("window.__GUIDED_RENDER_COUNT__") == 1
    returned_locate = (
        page.get_by_test_id("trace-row")
        .nth(1)
        .get_by_test_id(
            "show-metadata",
        )
    )
    assert returned_locate.evaluate("element => element === document.activeElement")
    assert abs(page.evaluate("window.scrollY") - origin_scroll) <= 1
    assert page.get_by_test_id("trace-row").count() == 2


def test_verdict_report(page: Page) -> None:
    """Read the conclusion first, then trace one caution value and return."""
    open_completed_variant(page, "verdict")
    shell = page.get_by_test_id("verdict-shell")
    assert (
        shell.get_by_test_id("verdict-title").inner_text()
        == "本次核验发现 2 处高风险身份痕迹"
    )
    assert shell.get_by_test_id("verdict-count").count() == 4
    trust_copy = shell.get_by_test_id("trust-panel").inner_text()
    for expected in [
        "3 / 3 解析器完成",
        "16 / 16 文档可追溯",
        "148 条归一化元数据",
        "离线处理 · 未上传文件",
    ]:
        assert expected in trust_copy, (expected, trust_copy)
    assert shell.get_by_test_id("workflow-step").count() == 0
    assert shell.get_by_test_id("guided-task-card").count() == 0
    assert shell.get_by_test_id("trace-row").count() == 5
    assert shell.get_by_test_id("trace-count").inner_text() == "5"
    assert shell.get_by_test_id("trace-row").evaluate_all(
        "rows => rows.map(row => row.dataset.tone)",
    ) == ["danger", "danger", "caution", "caution", "caution"]
    assert shell.locator(".verdict-enter").count() == 1

    shell.get_by_test_id("report-filter-caution").click()
    assert shell.locator(".verdict-enter").count() == 0
    assert shell.get_by_test_id("trace-row").count() == 3
    first_trace = shell.get_by_test_id("trace-row").first
    first_trace.get_by_test_id("trace-toggle").click()
    assert (
        first_trace.get_by_test_id("trace-toggle").get_attribute("aria-expanded")
        == "true"
    )
    assert (
        "SmartPark_Bid_v4.dotx"
        in first_trace.get_by_test_id(
            "trace-disclosure",
        ).inner_text()
    )
    origin_action = first_trace.get_by_test_id("show-metadata")
    origin_action.scroll_into_view_if_needed()
    origin_scroll = page.evaluate("window.scrollY")
    origin_action.click()

    metadata = page.get_by_test_id("metadata-page")
    metadata.wait_for()
    metadata.get_by_test_id("verdict-metadata-context").wait_for()
    assert metadata.get_by_test_id("metadata-search").input_value() == (
        "SmartPark_Bid_v4.dotx"
    )
    assert (
        metadata.get_by_test_id("metadata-duplicates-only").get_attribute(
            "aria-checked",
        )
        == "true"
    )
    selected_summary = metadata.locator(
        '[data-evidence-id="bidder-a-document-1"]',
    )
    assert selected_summary.evaluate("element => element.parentElement.open")
    assert selected_summary.evaluate("element => element === document.activeElement")

    metadata.get_by_test_id("metadata-back").click()
    report = page.get_by_test_id("report-page")
    report.wait_for()
    assert report.get_by_test_id("trace-row").count() == 3
    assert (
        report.get_by_test_id("trace-toggle").first.get_attribute("aria-expanded")
        == "true"
    )
    returned_action = report.get_by_test_id("show-metadata").first
    assert returned_action.evaluate("element => element === document.activeElement")
    assert abs(page.evaluate("window.scrollY") - origin_scroll) <= 1


def test_verdict_entry_motion_survives_real_variant_switch(page: Page) -> None:
    """Run B's one entry sequence after the real completed A-to-B switch."""
    open_completed_variant(page, "guided")
    page.evaluate(
        """() => {
          const original = window.DocmetaPrototype.renderers.verdict;
          window.__VERDICT_SWITCH_MOTION__ = {
            renders: 0,
            starts: [],
            ends: [],
            hashSettled: false,
          };
          window.DocmetaPrototype.renderers.verdict = state => {
            window.__VERDICT_SWITCH_MOTION__.renders += 1;
            return original(state);
          };
          document.addEventListener("animationstart", event => {
            if (event.animationName === "verdict-rise") {
              window.__VERDICT_SWITCH_MOTION__.starts.push(event.target.className);
            }
          });
          document.addEventListener("animationend", event => {
            if (event.animationName === "verdict-rise") {
              window.__VERDICT_SWITCH_MOTION__.ends.push(event.target.className);
            }
          });
          window.addEventListener("hashchange", () => {
            queueMicrotask(() => {
              window.__VERDICT_SWITCH_MOTION__.hashSettled = true;
            });
          }, { once: true });
        }""",
    )

    page.locator(
        'button[data-action="switch-variant"][data-variant="verdict"]',
    ).click()
    page.wait_for_function("window.__VERDICT_SWITCH_MOTION__.hashSettled")
    page.get_by_test_id("verdict-title").wait_for()
    assert page.evaluate("window.__VERDICT_SWITCH_MOTION__.renders") == 1
    assert page.locator(".verdict-enter > *").evaluate_all(
        """elements => elements.map(element => ({
          name: getComputedStyle(element).animationName,
          delay: getComputedStyle(element).animationDelay,
        }))""",
    ) == [
        {"name": "verdict-rise", "delay": "0s"},
        {"name": "verdict-rise", "delay": "0.11s"},
        {"name": "verdict-rise", "delay": "0.22s"},
    ]
    page.wait_for_function("window.__VERDICT_SWITCH_MOTION__.ends.length === 3")
    motion = page.evaluate("window.__VERDICT_SWITCH_MOTION__")
    assert motion["starts"] == [
        "verdict-conclusion",
        "verdict-timeline",
        "verdict-trust",
    ]
    assert motion["ends"] == motion["starts"]

    page.get_by_test_id("report-filter-caution").click()
    page.get_by_test_id("trace-toggle").first.click()
    assert page.locator(".verdict-enter").count() == 0
    assert page.evaluate("window.__VERDICT_SWITCH_MOTION__.starts.length") == 3
    assert page.evaluate("window.__VERDICT_SWITCH_MOTION__.ends.length") == 3


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
            test_direct_hash_navigation_switches_active_variants(page)
            test_scan_can_stop_then_restart_to_a_complete_report(page)
            test_launcher_reentry_stops_an_active_scan_before_restart(page)
            test_simulated_scan_failure_can_retry_without_a_partial_report(page)
            test_guided_report(page)
            test_guided_metadata_navigation_is_atomic_and_focuses_destination(page)
            test_guided_metadata_search_keeps_keyboard_focus(page)
            test_guided_report_return_restores_focus_and_scroll(page)
            test_verdict_entry_motion_survives_real_variant_switch(page)
            test_verdict_report(page)
            assert not console_errors, console_errors
            assert not page_errors, page_errors
        finally:
            browser.close()


if __name__ == "__main__":
    main()

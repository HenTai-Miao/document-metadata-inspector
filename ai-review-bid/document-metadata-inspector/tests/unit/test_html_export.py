from html.parser import HTMLParser
from pathlib import Path
from typing import final, override

from document_metadata_inspector.exporters import (
    ExportFormat,
    ExportTarget,
    export_report,
)
from tests.export_factories import make_export_report


@final
class _TableCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: int = 0
        self.rows: int = 0

    @override
    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag == "table":
            self.tables += 1
        elif tag == "tr":
            self.rows += 1


def test_html_projection_is_standalone_escaped_and_counted(tmp_path: Path) -> None:
    target = tmp_path / "report.html"

    _ = export_report(
        make_export_report(),
        ExportTarget(path=target, format=ExportFormat.HTML),
    )

    html = target.read_text(encoding="utf-8")
    lowered = html.casefold()
    assert "<title>围标串标投标人名称一致检测工具</title>" in html
    assert "<h1>围标串标投标人名称一致检测工具</h1>" in html
    assert "Document metadata inspection report" not in html
    assert "<script" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "&lt;script&gt;alert" in html
    assert "attachments/child.docx" in html
    assert "Child &lt;Author&gt;" in html
    assert "Documents: 1" in html
    assert "Observations: 3" in html
    assert "Embedded documents: 1" in html
    assert "Parser runs: 1" in html

    parser = _TableCounter()
    parser.feed(html)
    assert parser.tables >= 4
    assert parser.rows >= 5

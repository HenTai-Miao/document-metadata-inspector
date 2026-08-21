"""Generate a realistic bid folder with planted collusion traces for testing."""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "测试投标项目-围标检测演示"

# ═══════════════════════════════════════════════════════════════════
# Bidder profiles
# ═══════════════════════════════════════════════════════════════════
# 甲 and 乙 share author/company/template → RED flags (collusion)
# 丙 is independent → clean

BIDDERS = [
    {
        "folder": "投标人甲-宏达建设",
        "author": "李建国",
        "last_modified_by": "李建国",
        "company": "宏达建设集团有限公司",
        "manager": "王志强",
        "template": "宏达投标模板2024.dotx",
        "created": datetime(2026, 7, 15, 9, 30, 0, tzinfo=timezone.utc),
        "modified": datetime(2026, 7, 18, 14, 22, 0, tzinfo=timezone.utc),
        "app": "Microsoft Office Word",
        "app_version": "16.0",
        "amount": "1,280.00",
    },
    {
        "folder": "投标人乙-正阳工程",
        # ⚠️ SAME author as 甲 → red flag
        "author": "李建国",
        # ⚠️ SAME last_modified_by as 甲 → red flag
        "last_modified_by": "李建国",
        # ⚠️ SAME company as 甲 → red flag
        "company": "宏达建设集团有限公司",
        "manager": "赵磊",
        # ⚠️ SAME template as 甲 → yellow flag
        "template": "宏达投标模板2024.dotx",
        # ⚠️ SAME creation timestamp as 甲 → yellow flag
        "created": datetime(2026, 7, 15, 9, 30, 0, tzinfo=timezone.utc),
        "modified": datetime(2026, 7, 19, 10, 15, 0, tzinfo=timezone.utc),
        "app": "Microsoft Office Word",
        "app_version": "16.0",
        "amount": "1,295.00",
    },
    {
        "folder": "投标人丙-远东集团",
        "author": "陈伟",
        "last_modified_by": "陈伟",
        "company": "远东建设集团股份有限公司",
        "manager": "刘洋",
        "template": "远东标准投标文件.dotx",
        "created": datetime(2026, 7, 16, 11, 0, 0, tzinfo=timezone.utc),
        "modified": datetime(2026, 7, 20, 16, 45, 0, tzinfo=timezone.utc),
        "app": "WPS Office",
        "app_version": "12.1",
        "amount": "1,310.00",
    },
]


# ═══════════════════════════════════════════════════════════════════
# Document generators
# ═══════════════════════════════════════════════════════════════════

def make_docx(path: Path, bidder: dict) -> None:
    """Create a Word document with planted metadata."""
    doc = Document()

    # Core properties (author, dates, etc.)
    cp = doc.core_properties
    cp.author = bidder["author"]
    cp.last_modified_by = bidder["last_modified_by"]
    cp.created = bidder["created"]
    cp.modified = bidder["modified"]
    cp.category = "投标文件"
    cp.comments = "由投标部门编制"

    doc.add_heading(f'{bidder["folder"]} 投标函', level=1)
    doc.add_paragraph("致招标人：")
    doc.add_paragraph(
        f"根据贵方招标公告，我方（{bidder['company']}）"
        "正式提交投标文件，承诺按招标文件要求完成全部工作内容。"
    )
    doc.add_paragraph(f"投标报价：{bidder['amount']} 万元")
    doc.add_paragraph("工期：180日历天")
    doc.add_paragraph("质量标准：合格")

    doc.save(str(path))

    # Patch company & template into the OOXML app.xml
    _patch_docx_props(path, bidder)


def _patch_docx_props(path: Path, bidder: dict) -> None:
    """Inject company, template, manager into docProps/app.xml."""
    import zipfile
    import tempfile

    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        f'<Application>{bidder["app"]}</Application>'
        f'<AppVersion>{bidder["app_version"]}</AppVersion>'
        f'<Company>{bidder["company"]}</Company>'
        f'<Manager>{bidder["manager"]}</Manager>'
        f'<Template>{bidder["template"]}</Template>'
        "<TotalTime>45</TotalTime>"
        "<Pages>3</Pages>"
        "<Words>285</Words>"
        "<Characters>1632</Characters>"
        "<Paragraphs>12</Paragraphs>"
        "</Properties>"
    )

    # Read original zip, replace app.xml, write new zip
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(str(path), "r") as zin, zipfile.ZipFile(str(tmp), "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            if item == "docProps/app.xml":
                zout.writestr(item, app_xml)
            else:
                zout.writestr(item, zin.read(item))
    tmp.replace(path)


def make_xlsx(path: Path, bidder: dict) -> None:
    """Create an Excel spreadsheet with planted metadata."""
    wb = Workbook()
    ws = wb.active
    ws.title = "报价清单"

    ws.append(["序号", "项目名称", "单位", "数量", "单价(元)", "合价(元)"])
    ws.append([1, "土方开挖", "m³", "5000", "28.50", "142,500"])
    ws.append([2, "混凝土浇筑", "m³", "1200", "450.00", "540,000"])
    ws.append([3, "钢筋制作安装", "t", "85", "5,200.00", "442,000"])
    ws.append([4, "模板工程", "m²", "3200", "65.00", "208,000"])
    ws.append(["合计", "", "", "", "", f"{bidder['amount']} 万元"])

    # Column widths
    for col_letter, width in [("A", 8), ("B", 20), ("C", 8), ("D", 10), ("E", 12), ("F", 14)]:
        ws.column_dimensions[col_letter].width = width

    # Metadata
    props = wb.properties
    props.creator = bidder["author"]
    props.lastModifiedBy = bidder["last_modified_by"]
    props.created = bidder["created"]
    props.modified = bidder["modified"]
    props.title = f'{bidder["folder"]} 报价清单'
    props.description = "工程量清单计价"

    wb.save(str(path))

    # Patch company/template into xlsx app.xml
    _patch_xlsx_props(path, bidder)


def _patch_xlsx_props(path: Path, bidder: dict) -> None:
    """Inject company, template, manager into xlprs/app.xml."""
    import zipfile

    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        f'<Application>{bidder["app"]}</Application>'
        f'<AppVersion>{bidder["app_version"]}</AppVersion>'
        f'<Company>{bidder["company"]}</Company>'
        f'<Manager>{bidder["manager"]}</Manager>'
        f'<Template>{bidder["template"]}</Template>'
        "</Properties>"
    )

    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(str(path), "r") as zin, zipfile.ZipFile(str(tmp), "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            if item == "docProps/app.xml":
                zout.writestr(item, app_xml)
            else:
                zout.writestr(item, zin.read(item))
    tmp.replace(path)


def make_pdf(path: Path, bidder: dict) -> None:
    """Create a PDF with planted metadata."""
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    c.setFont("STSong-Light", 20)
    c.drawCentredString(width / 2, height - 80, f'{bidder["folder"]}')
    c.setFont("STSong-Light", 16)
    c.drawCentredString(width / 2, height - 110, "技术方案")

    c.setFont("STSong-Light", 12)
    y = height - 160
    lines = [
        f"编制单位：{bidder['company']}",
        f"编制人：{bidder['author']}",
        f"投标报价：{bidder['amount']} 万元",
        "",
        "一、工程概况",
        "    本项目为市政基础设施建设工程，主要包括道路、桥梁、排水等内容。",
        "    工程地点位于城区主干道沿线，施工区域总长约3.2公里。",
        "",
        "二、施工方案",
        "    1. 土方工程：采用机械开挖为主，人工配合修边。",
        "    2. 混凝土工程：采用商品混凝土，泵送浇筑。",
        "    3. 钢筋工程：集中加工，现场绑扎安装。",
        "",
        "三、质量保证措施",
        "    建立健全质量管理体系，严格执行三检制度，确保工程质量合格。",
        "",
        "四、安全文明施工",
        "    落实安全生产责任制，设置专职安全员，做好现场防护。",
    ]
    for line in lines:
        c.drawString(60, y, line)
        y -= 24

    c.drawCentredString(width / 2, 50, f'{bidder["company"]}')
    c.showPage()
    c.save()

    # Set PDF metadata
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    writer.add_metadata({
        "/Title": f'{bidder["folder"]} 技术方案',
        "/Author": bidder["author"],
        "/Creator": bidder["app"],
        "/Producer": bidder["app"],
        "/CreationDate": f"D:{bidder['created'].strftime('%Y%m%d%H%M%S')}+08'00'",
        "/ModDate": f"D:{bidder['modified'].strftime('%Y%m%d%H%M%S')}+08'00'",
        "/Company": bidder["company"],
        "/Subject": "技术方案",
    })

    with open(str(path), "wb") as f:
        writer.write(f)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    print(f"📂 创建测试项目目录: {OUTPUT}")
    print()

    for bidder in BIDDERS:
        folder = OUTPUT / bidder["folder"]
        folder.mkdir()
        print(f"  📁 {bidder['folder']}")

        # Word — 投标函
        make_docx(folder / "投标函.docx", bidder)
        print(f"     ✅ 投标函.docx  (作者={bidder['author']}, 公司={bidder['company']})")

        # Excel — 报价清单
        make_xlsx(folder / "报价清单.xlsx", bidder)
        print(f"     ✅ 报价清单.xlsx (作者={bidder['author']}, 公司={bidder['company']})")

        # PDF — 技术方案
        make_pdf(folder / "技术方案.pdf", bidder)
        print(f"     ✅ 技术方案.pdf  (作者={bidder['author']}, 公司={bidder['company']})")
        print()

    print("═" * 60)
    print("🔍 预期检测结果：")
    print("═" * 60)
    print()
    print("🔴 红色警告（人员/组织身份重复）:")
    print("   • 作者「李建国」— 甲、乙相同 → 疑似同一人操作")
    print("   • 最后修改者「李建国」— 甲、乙相同")
    print("   • 公司「宏达建设集团有限公司」— 甲、乙相同")
    print()
    print("🟡 黄色提示（需人工复核）:")
    print("   • 模板「宏达投标模板2024.dotx」— 甲、乙相同")
    print("   • 创建时间「2026-07-15 09:30」— 甲、乙精确一致")
    print()
    print("⚪ 不提示:")
    print("   • 应用程序甲乙都是 Microsoft Office Word → 不应出现")
    print("   • 丙用 WPS Office → 差异正常，不提示")
    print()
    print(f"✅ 测试数据已生成到桌面: {OUTPUT}")
    print(f"   在应用中选择此文件夹进行扫描即可。")


if __name__ == "__main__":
    sys.exit(main())

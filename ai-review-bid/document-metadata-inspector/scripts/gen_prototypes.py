"""Generate 3 HTML prototype designs for 30-bidder collusion review."""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "围标检测UI方案对比"

# ═══════════════════════════════════════════════════════════════════
# Mock data: 30 bidders with planted collusion traces
# ═══════════════════════════════════════════════════════════════════

BIDDERS = []
for i in range(1, 31):
    BIDDERS.append({
        "id": i,
        "name": f"投标人{i:02d}",
        "author": f"员工{i}",
        "company": f"公司{i}",
        "lastModifiedBy": f"员工{i}",
        "template": f"模板{i}.dotx",
        "created": f"2026-07-{15 + i % 10:02d} 09:{i % 60:02d}:00",
        "modified": f"2026-07-{16 + i % 10:02d} 14:{i % 60:02d}:00",
        "app": "Microsoft Office Word" if i % 2 == 0 else "WPS Office",
        "files": 3,
    })

# Cluster A: bidders 1,8,17,24 share author + company (RED)
for i in [0, 7, 16, 23]:
    BIDDERS[i]["author"] = "张明"
    BIDDERS[i]["company"] = "宏达建设集团有限公司"
    BIDDERS[i]["lastModifiedBy"] = "张明"

# Cluster B: bidders 5,13,29 share author (RED)
for i in [4, 12, 28]:
    BIDDERS[i]["author"] = "李芳"
    BIDDERS[i]["company"] = "正阳工程有限公司"
    BIDDERS[i]["lastModifiedBy"] = "李芳"

# Cluster C: bidders 3,19 share template + timestamp (YELLOW)
for i in [2, 18]:
    BIDDERS[i]["template"] = "通用投标模板V3.dotx"
    BIDDERS[i]["created"] = "2026-07-15 09:30:00"

CLUSTER_A = [1, 8, 17, 24]
CLUSTER_B = [5, 13, 29]
CLUSTER_C = [3, 19]

# ═══════════════════════════════════════════════════════════════════
# Shared CSS
# ═══════════════════════════════════════════════════════════════════

SHARED_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #1a1a2e; }
:root {
  --red: #dc2626; --red-light: #fef2f2; --red-bg: #fee2e2;
  --orange: #d97706; --orange-light: #fffbeb; --orange-bg: #fef3c7;
  --green: #16a34a; --green-light: #f0fdf4; --green-bg: #dcfce7;
  --blue: #2563eb; --blue-light: #eff6ff;
  --gray: #6b7280; --border: #e5e7eb; --surface: #fff;
  --text: #1a1a2e; --text-2: #4b5563; --text-3: #9ca3af;
}
"""

HEADER_HTML = """
<div class="page-header">
  <h1>📄 文档元数据核验 · 围标串标检测</h1>
  <span class="proj-name">XX市政工程采购项目 · 30家投标人</span>
</div>
"""


def design1_matrix() -> str:
    """方案一：风险矩阵视图 — 字段为行，投标人为列，色块标重复。"""
    # Determine which bidders share which fields
    flagged = {}  # bidder_id -> {field: "danger"|"caution", group: [...]}

    # Author matches (danger)
    for cluster in [CLUSTER_A, CLUSTER_B]:
        for bid in cluster:
            flagged.setdefault(bid, {})["author"] = ("danger", cluster)
            flagged.setdefault(bid, {})["lastModifiedBy"] = ("danger", cluster)
    # Company matches (danger) - cluster A only
    for bid in CLUSTER_A:
        flagged.setdefault(bid, {})["company"] = ("danger", CLUSTER_A)
    # Template matches (caution) - cluster C
    for bid in CLUSTER_C:
        flagged.setdefault(bid, {})["template"] = ("caution", CLUSTER_C)
        flagged.setdefault(bid, {})["created"] = ("caution", CLUSTER_C)

    def cell_class(bid: int, field: str) -> str:
        info = flagged.get(bid, {}).get(field)
        if info is None:
            return ""
        tone, cluster = info
        others = [f"{b:02d}" for b in cluster if b != bid]
        return f' class="cell-{tone}" title="同 投标人{'、'.join(others)}"'

    # Build matrix
    fields = [
        ("author", "作者"), ("lastModifiedBy", "最后修改者"), ("company", "公司"),
        ("template", "模板"), ("created", "创建时间"),
    ]

    cells = ""
    for fid, flabel in fields:
        cells += f'<tr><td class="row-label">{flabel}</td>'
        for b in BIDDERS:
            cls = cell_class(b["id"], fid)
            val = b[fid]
            if len(val) > 8:
                val = val[:7] + "…"
            cells += f'<td{cls}>{val}</td>'
        cells += "</tr>"

    # Count flags
    danger_count = len(CLUSTER_A) + len(CLUSTER_B) + len(CLUSTER_A)  # author+lmb+company
    caution_count = len(CLUSTER_C) * 2

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>方案一 · 风险矩阵视图</title>
<style>
{SHARED_CSS}
.page-header {{ background: var(--surface); padding: 16px 24px; border-bottom: 2px solid var(--border); display: flex; align-items: center; justify-content: space-between; }}
.page-header h1 {{ font-size: 18px; }}
.proj-name {{ color: var(--text-3); font-size: 13px; }}
.info-bar {{ padding: 12px 24px; background: var(--surface); border-bottom: 1px solid var(--border); display: flex; gap: 24px; align-items: center; }}
.info-bar .stat {{ display: flex; align-items: center; gap: 6px; font-size: 13px; }}
.info-bar .stat strong {{ font-size: 18px; }}
.legend {{ margin-left: auto; display: flex; gap: 16px; font-size: 12px; }}
.legend span {{ display: flex; align-items: center; gap: 4px; }}
.legend i {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
.legend .lg-danger {{ background: var(--red-bg); border: 1px solid #fca5a5; }}
.legend .lg-caution {{ background: var(--orange-bg); border: 1px solid #fde68a; }}
.table-wrap {{ overflow-x: auto; padding: 16px 24px; }}
table {{ border-collapse: collapse; font-size: 11px; background: var(--surface); }}
th, td {{ border: 1px solid var(--border); padding: 4px 6px; text-align: center; white-space: nowrap; max-width: 70px; overflow: hidden; text-overflow: ellipsis; }}
th {{ background: #f8fafc; font-weight: 600; position: sticky; top: 0; }}
.row-label {{ background: #f1f5f9; font-weight: 600; text-align: right; min-width: 80px; position: sticky; left: 0; }}
.col-num {{ background: #f8fafc; font-weight: 600; min-width: 45px; }}
.cell-danger {{ background: var(--red-bg); color: var(--red); font-weight: 600; }}
.cell-caution {{ background: var(--orange-bg); color: var(--orange); font-weight: 600; }}
.notes {{ padding: 8px 24px 24px; }}
.alert-box {{ padding: 12px 16px; border-radius: 8px; margin-bottom: 8px; font-size: 13px; line-height: 1.6; }}
.alert-danger {{ background: var(--red-light); border: 1px solid #fca5a5; color: var(--red); }}
.alert-caution {{ background: var(--orange-light); border: 1px solid #fde68a; color: var(--orange); }}
</style></head><body>
{HEADER_HTML}
<div class="info-bar">
  <div class="stat"><strong style="color:var(--red)">10</strong> 处人员/组织重复</div>
  <div class="stat"><strong style="color:var(--orange)">4</strong> 处模板/时间戳重复</div>
  <div class="stat"><strong>30</strong> 家投标人</div>
  <div class="legend">
    <span><i class="lg-danger"></i> 人员/组织重复</span>
    <span><i class="lg-caution"></i> 需人工复核</span>
  </div>
</div>
<div class="notes">
  <div class="alert-box alert-danger">⚠ 发现 2 组人员身份重复：
    <br>　• 作者/修改者「张明」+ 公司「宏达建设集团有限公司」→ 投标人01、08、17、24
    <br>　• 作者/修改者「李芳」+ 公司「正阳工程有限公司」→ 投标人05、13、29</div>
  <div class="alert-box alert-caution">⚠ 模板「通用投标模板V3.dotx」+ 创建时间精确一致 → 投标人03、19</div>
</div>
<div class="table-wrap">
  <table>
    <thead><tr><th class="row-label">字段＼投标人</th>
    {''.join(f'<th class="col-num">{b["id"]:02d}</th>' for b in BIDDERS)}
    </tr></thead>
    <tbody>{cells}</tbody>
  </table>
</div>
</body></html>"""


def design2_dashboard() -> str:
    """方案二：风险仪表盘 — KPI + 按风险排序的紧凑列表。"""

    # Build risk-sorted bidder list
    items = []
    for b in BIDDERS:
        bid = b["id"]
        risks = []
        if bid in CLUSTER_A:
            risks.append(("danger", f"作者/修改者「张明」+ 公司「宏达建设集团」", "01、07、15、23"))
        if bid in CLUSTER_B:
            risks.append(("danger", f"作者/修改者「李芳」+ 公司「正阳工程」", "05、12、28"))
        if bid in CLUSTER_C:
            risks.append(("caution", "模板「通用投标模板V3」+ 创建时间一致", "03、18"))
        items.append((b, risks))

    # Sort: danger first, then caution, then clean
    def sort_key(item):
        b, risks = item
        has_danger = any(r[0] == "danger" for r in risks)
        has_caution = any(r[0] == "caution" for r in risks)
        if has_danger: return 0
        if has_caution: return 1
        return 2
    items.sort(key=sort_key)

    list_rows = ""
    for b, risks in items:
        if not risks:
            list_rows += f"""
            <div class="bidder-row bidder-row--clean">
              <span class="bidder-num">{b["id"]:02d}</span>
              <span class="bidder-name">投标人{b["id"]:02d}</span>
              <span class="bidder-meta">{b["author"]} · {b["company"]}</span>
              <span class="pill pill--ok">✓ 无异常</span>
            </div>"""
            continue

        risk_badges = ""
        for tone, desc, others in risks:
            icon = "⚠" if tone == "danger" else "⚠"
            risk_badges += f'<span class="risk-badge risk-badge--{tone}">{icon} {desc} <em>同 {others}</em></span>'

        row_class = "bidder-row--danger" if any(r[0] == "danger" for r in risks) else "bidder-row--caution"
        list_rows += f"""
          <div class="bidder-row {row_class}">
            <div class="bidder-row-left">
              <span class="bidder-num">{b["id"]:02d}</span>
              <span class="bidder-name">投标人{b["id"]:02d}</span>
              <span class="bidder-meta">{b["author"]} · {b["company"]} · {b["files"]}个文件</span>
            </div>
            <div class="bidder-risk">{risk_badges}</div>
          </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>方案二 · 风险仪表盘</title>
<style>
{SHARED_CSS}
.page-header {{ background: var(--surface); padding: 16px 24px; border-bottom: 2px solid var(--border); display: flex; align-items: center; justify-content: space-between; }}
.page-header h1 {{ font-size: 18px; }}
.proj-name {{ color: var(--text-3); font-size: 13px; }}

.kpi-row {{ display: flex; gap: 12px; padding: 16px 24px; }}
.kpi {{ flex: 1; background: var(--surface); border-radius: 8px; padding: 16px; border: 1px solid var(--border); }}
.kpi__num {{ font-size: 28px; font-weight: 800; }}
.kpi__label {{ font-size: 12px; color: var(--text-3); margin-top: 2px; }}
.kpi--danger {{ border-left: 4px solid var(--red); }}
.kpi--danger .kpi__num {{ color: var(--red); }}
.kpi--caution {{ border-left: 4px solid var(--orange); }}
.kpi--caution .kpi__num {{ color: var(--orange); }}
.kpi--total {{ border-left: 4px solid var(--blue); }}
.kpi--clean {{ border-left: 4px solid var(--green); }}
.kpi--clean .kpi__num {{ color: var(--green); }}

.section-title {{ padding: 8px 24px 12px; font-size: 14px; font-weight: 700; color: var(--text-2); display: flex; align-items: center; gap: 8px; }}
.section-title .count {{ background: var(--red-bg); color: var(--red); font-size: 12px; padding: 1px 8px; border-radius: 10px; }}

.list-wrap {{ padding: 0 24px 24px; }}
.bidder-row {{ display: flex; align-items: center; gap: 12px; padding: 8px 14px; margin-bottom: 3px; border-radius: 6px; background: var(--surface); border: 1px solid var(--border); font-size: 13px; }}
.bidder-row--danger {{ border-left: 4px solid var(--red); background: var(--red-light); }}
.bidder-row--caution {{ border-left: 4px solid var(--orange); background: var(--orange-light); }}
.bidder-row--clean {{ opacity: 0.55; }}
.bidder-row-left {{ display: flex; align-items: center; gap: 10px; min-width: 340px; }}
.bidder-num {{ font-weight: 800; font-size: 14px; color: var(--text-3); min-width: 24px; }}
.bidder-row--danger .bidder-num {{ color: var(--red); }}
.bidder-name {{ font-weight: 600; min-width: 70px; }}
.bidder-meta {{ color: var(--text-3); font-size: 12px; }}
.bidder-risk {{ display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }}
.risk-badge {{ font-size: 11px; padding: 2px 8px; border-radius: 4px; }}
.risk-badge--danger {{ background: var(--red-bg); color: var(--red); }}
.risk-badge--caution {{ background: var(--orange-bg); color: var(--orange); }}
.risk-badge em {{ font-style: normal; opacity: 0.7; }}
.pill {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; }}
.pill--ok {{ background: var(--green-bg); color: var(--green); }}

.clean-toggle {{ text-align: center; padding: 10px; color: var(--text-3); font-size: 12px; cursor: pointer; }}
.clean-toggle:hover {{ color: var(--blue); }}
</style></head><body>
{HEADER_HTML}
<div class="kpi-row">
  <div class="kpi kpi--danger"><div class="kpi__num">7</div><div class="kpi__label">疑似围标投标人</div></div>
  <div class="kpi kpi--caution"><div class="kpi__num">2</div><div class="kpi__label">需人工复核</div></div>
  <div class="kpi kpi--clean"><div class="kpi__num">21</div><div class="kpi__label">未发现异常</div></div>
  <div class="kpi kpi--total"><div class="kpi__num">30</div><div class="kpi__label">投标人总数</div></div>
</div>

<div class="section-title">🔴 高风险（人员/组织身份重复）<span class="count">7家</span></div>
<div class="list-wrap">
{list_rows[:list_rows.index('bidder-row--clean')] if 'bidder-row--clean' in list_rows else list_rows}
</div>

<div class="section-title" style="margin-top:16px;">⚪ 未发现异常 <span class="count" style="background:#f1f5f9;color:var(--gray)">21家</span></div>
<div class="list-wrap" style="opacity:0.6;">
{''.join(r for r in list_rows.split('</div>') if 'clean' in r)}
</div>
</body></html>"""


def design3_network() -> str:
    """方案三：围标关系网络图 — 节点为投标人，连线为共享元数据。"""

    # Build SVG network
    # Cluster A nodes: positions around center-left
    # Cluster B nodes: center-right
    # Cluster C nodes: top
    # Clean nodes: scattered, gray, small

    import math

    nodes = []
    edges = []

    # Cluster A: 4 bidders in a tight circle
    center_a = (280, 380)
    for j, bid in enumerate(CLUSTER_A):
        angle = j * 2 * math.pi / len(CLUSTER_A) - math.pi / 2
        x = center_a[0] + 70 * math.cos(angle)
        y = center_a[1] + 70 * math.sin(angle)
        nodes.append((bid, x, y, "danger", "张明/宏达建设"))
    # Edges within cluster A (fully connected)
    for i in range(len(CLUSTER_A)):
        for j in range(i + 1, len(CLUSTER_A)):
            edges.append((CLUSTER_A[i], CLUSTER_A[j], "danger"))

    # Cluster B: 3 bidders
    center_b = (680, 350)
    for j, bid in enumerate(CLUSTER_B):
        angle = j * 2 * math.pi / len(CLUSTER_B) - math.pi / 2
        x = center_b[0] + 60 * math.cos(angle)
        y = center_b[1] + 60 * math.sin(angle)
        nodes.append((bid, x, y, "danger", "李芳/正阳工程"))
    for i in range(len(CLUSTER_B)):
        for j in range(i + 1, len(CLUSTER_B)):
            edges.append((CLUSTER_B[i], CLUSTER_B[j], "danger"))

    # Cluster C: 2 bidders
    center_c = (500, 160)
    for j, bid in enumerate(CLUSTER_C):
        angle = j * 2 * math.pi / len(CLUSTER_C) - math.pi / 2
        x = center_c[0] + 50 * math.cos(angle)
        y = center_c[1] + 50 * math.sin(angle)
        nodes.append((bid, x, y, "caution", "同模板/时间戳"))
    edges.append((CLUSTER_C[0], CLUSTER_C[1], "caution"))

    # Clean bidders: scattered in background grid
    clean_bids = [b["id"] for b in BIDDERS if b["id"] not in CLUSTER_A + CLUSTER_B + CLUSTER_C]
    cols = 8
    start_x, start_y = 80, 520
    spacing_x, spacing_y = 85, 60
    for j, bid in enumerate(clean_bids):
        col = j % cols
        row = j // cols
        x = start_x + col * spacing_x
        y = start_y + row * spacing_y
        nodes.append((bid, x, y, "clean", ""))

    # Build SVG
    node_map = {n[0]: n for n in nodes}
    edge_svg = ""
    for a, b, tone in edges:
        na = node_map[a]
        nb = node_map[b]
        color = "var(--red)" if tone == "danger" else "var(--orange)"
        width = "3" if tone == "danger" else "2"
        opacity = "0.5" if tone == "danger" else "0.4"
        edge_svg += f'<line x1="{na[1]}" y1="{na[2]}" x2="{nb[1]}" y2="{nb[2]}" stroke="{color}" stroke-width="{width}" opacity="{opacity}"/>'

    node_svg = ""
    for bid, x, y, tone, label in nodes:
        if tone == "danger":
            r, fill, stroke = 22, "#fee2e2", "#dc2626"
            font_color = "#dc2626"
        elif tone == "caution":
            r, fill, stroke = 18, "#fef3c7", "#d97706"
            font_color = "#d97706"
        else:
            r, fill, stroke = 12, "#f8fafc", "#cbd5e1"
            font_color = "#94a3b8"
        node_svg += f'''
        <g class="node" data-id="{bid}">
          <circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>
          <text x="{x}" y="{y+4}" text-anchor="middle" font-size="11" font-weight="700" fill="{font_color}">{bid:02d}</text>
        </g>'''
        if label:
            node_svg += f'<text x="{x}" y="{y+r+14}" text-anchor="middle" font-size="9" fill="{font_color}">{label}</text>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>方案三 · 围标关系网络</title>
<style>
{SHARED_CSS}
.page-header {{ background: var(--surface); padding: 16px 24px; border-bottom: 2px solid var(--border); display: flex; align-items: center; justify-content: space-between; }}
.page-header h1 {{ font-size: 18px; }}
.proj-name {{ color: var(--text-3); font-size: 13px; }}

.summary-row {{ display: flex; gap: 12px; padding: 16px 24px; }}
.summary-card {{ background: var(--surface); border-radius: 8px; padding: 14px 18px; border: 1px solid var(--border); flex: 1; }}
.summary-card h3 {{ font-size: 13px; margin-bottom: 6px; }}
.cluster-tag {{ display: inline-block; font-size: 11px; padding: 2px 10px; border-radius: 10px; margin-right: 4px; }}
.ct-danger {{ background: var(--red-bg); color: var(--red); }}
.ct-caution {{ background: var(--orange-bg); color: var(--orange); }}
.summary-card .detail {{ font-size: 12px; color: var(--text-2); line-height: 1.8; }}

.graph-wrap {{ background: var(--surface); margin: 0 24px 24px; border-radius: 8px; border: 1px solid var(--border); overflow: hidden; }}
.graph-wrap svg {{ display: block; }}
.legend-bar {{ display: flex; gap: 20px; padding: 10px 18px; border-bottom: 1px solid var(--border); font-size: 12px; color: var(--text-2); }}
.legend-bar .item {{ display: flex; align-items: center; gap: 6px; }}
.legend-bar .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
</style></head><body>
{HEADER_HTML}

<div class="summary-row">
  <div class="summary-card" style="border-left:4px solid var(--red);">
    <h3>🔴 围标组A — 4家投标人关联</h3>
    <div class="detail">
      <span class="cluster-tag ct-danger">组A: 01·08·17·24</span><br>
      作者/修改者「张明」、公司「宏达建设集团有限公司」一致<br>
      <strong>判定：疑似围标串标</strong>
    </div>
  </div>
  <div class="summary-card" style="border-left:4px solid var(--red);">
    <h3>🔴 围标组B — 3家投标人关联</h3>
    <div class="detail">
      <span class="cluster-tag ct-danger">组B: 05·13·29</span><br>
      作者/修改者「李芳」、公司「正阳工程有限公司」一致<br>
      <strong>判定：疑似围标串标</strong>
    </div>
  </div>
  <div class="summary-card" style="border-left:4px solid var(--orange);">
    <h3>🟡 疑似关联 — 2家投标人</h3>
    <div class="detail">
      <span class="cluster-tag ct-caution">03·19</span><br>
      模板「通用投标模板V3」+ 创建时间精确一致<br>
      <strong>判定：需人工复核</strong>
    </div>
  </div>
</div>

<div class="graph-wrap">
  <div class="legend-bar">
    <div class="item"><span class="dot" style="background:#fee2e2;border:2px solid #dc2626;"></span> 高风险投标人</div>
    <div class="item"><span class="dot" style="background:#fef3c7;border:2px solid #d97706;"></span> 待复核投标人</div>
    <div class="item"><span class="dot" style="background:#f8fafc;border:2px solid #cbd5e1;"></span> 正常投标人</div>
    <div class="item"><span style="display:inline-block;width:24px;height:3px;background:var(--red);opacity:0.5;"></span> 人员/组织重复</div>
    <div class="item"><span style="display:inline-block;width:24px;height:2px;background:var(--orange);opacity:0.4;"></span> 模板/时间戳一致</div>
  </div>
  <svg viewBox="0 0 800 800" width="100%">
    {edge_svg}
    {node_svg}
  </svg>
</div>
</body></html>"""


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    designs = [
        ("方案一-风险矩阵视图.html", design1_matrix, "风险矩阵"),
        ("方案二-风险仪表盘.html", design2_dashboard, "风险仪表盘"),
        ("方案三-围标关系网络.html", design3_network, "关系网络"),
    ]

    for filename, gen_func, title in designs:
        path = OUTPUT / filename
        path.write_text(gen_func(), encoding="utf-8")
        print(f"  ✅ {filename}")

    print(f"\n📂 已生成到: {OUTPUT}")
    print("   双击 HTML 文件即可在浏览器中打开对比。")


if __name__ == "__main__":
    main()

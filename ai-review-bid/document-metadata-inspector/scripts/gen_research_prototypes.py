"""
Generate 3 UI prototypes based on real-world bid collusion detection products.

Design A — 两两比对视图 (inspired by 法正智能AI围串标检测)
Design B — 热力矩阵+详情面板 (inspired by Power BI dashboards + OECD red flags)
Design C — 关系网络+调查面板 (inspired by Linkurious graph investigation)
"""

from __future__ import annotations

import math
import os
from pathlib import Path

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "围标检测UI方案对比-V2"

# ═══════════════════════════════════════════════════════════════════
# 30 bidders mock data
# ═══════════════════════════════════════════════════════════════════
B = []
for i in range(1, 31):
    B.append({"id":i,"author":f"员工{i}","company":f"公司{i}","lmb":f"员工{i}",
              "template":f"模板{i}.dotx","created":f"2026-07-{15+i%10:02d} 09:{i%60:02d}",
              "modified":f"2026-07-{16+i%10:02d} 14:{i%60:02d}",
              "app":"Word 2019" if i%2==0 else "WPS Office","size":f"{120+i*7}KB"})

CA=[1,8,17,24]; CB=[5,13,29]; CC=[3,19]
for i in [0,7,16,23]: B[i].update(author="张明",company="宏达建设集团",lmb="张明")
for i in [4,12,28]: B[i].update(author="李芳",company="正阳工程",lmb="李芳")
for i in [2,18]: B[i].update(template="通用投标模板V3.dotx",created="2026-07-15 09:30")

CSS_BASE = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--red:#dc2626;--rl:#fef2f2;--rb:#fee2e2;--or:#d97706;--ol:#fffbeb;--ob:#fef3c7;
--gr:#16a34a;--gl:#f0fdf4;--bl:#2563eb;--bll:#eff6ff;--gy:#6b7280;--bd:#e5e7eb;
--sf:#fff;--t1:#1a1a2e;--t2:#4b5563;--t3:#9ca3af}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;color:var(--t1);font-size:13px}
.hdr{background:var(--sf);padding:10px 20px;border-bottom:2px solid var(--bd);display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:16px}.hdr .sub{color:var(--t3);font-size:12px}
"""

# ═══════════════════════════════════════════════════════════════════
# Design A: Pairwise comparison (法正智能 style)
# ═══════════════════════════════════════════════════════════════════
def design_a() -> str:
    # Build risk pairs sorted by severity
    pairs = []
    # Danger pairs from clusters
    for cluster, label in [(CA,"张明/宏达建设集团"),(CB,"李芳/正阳工程")]:
        for i in range(len(cluster)):
            for j in range(i+1,len(cluster)):
                pairs.append({"a":cluster[i],"b":cluster[j],"level":"danger",
                    "label":label,"fields":["作者","最后修改者","公司"]})
    # Caution pairs
    pairs.append({"a":CC[0],"b":CC[1],"level":"caution",
        "label":"同模板+时间戳","fields":["模板","创建时间"]})

    pair_list = ""
    for p in pairs:
        lc = "danger" if p["level"]=="danger" else "caution"
        pair_list += f'<div class="pair-item pair-{lc}" onclick="selectPair(\'{p["a"]},{p["b"]}\')">'
        pair_list += f'<span class="pair-level pair-level--{lc}">{"🔴" if lc=="danger" else "🟡"}</span>'
        pair_list += f'<span class="pair-names">投标人{p["a"]:02d} ↔ 投标人{p["b"]:02d}</span>'
        pair_list += f'<span class="pair-reason">{p["label"]}</span>'
        pair_list += f'<span class="pair-count">{len(p["fields"])}项重复</span></div>'

    # All clean pairs (compact)
    clean_ids = [b["id"] for b in B if b["id"] not in CA+CB+CC]
    clean_chips = "".join(f'<span class="clean-chip">{i:02d}</span>' for i in clean_ids)

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>方案A · 两两比对视图（参考法正智能）</title>
<style>
{CSS_BASE}
.layout{{display:flex;height:calc(100vh - 50px)}}
/* Left: pair list */
.left{{width:300px;border-right:1px solid var(--bd);background:var(--sf);overflow-y:auto;flex-shrink:0}}
.left-title{{padding:10px 14px;font-weight:700;font-size:13px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}}
.left-title .cnt{{background:var(--rb);color:var(--red);font-size:11px;padding:1px 8px;border-radius:10px}}
.pair-item{{display:flex;align-items:center;gap:6px;padding:8px 14px;border-bottom:1px solid var(--bd);cursor:pointer;transition:background .15s}}
.pair-item:hover{{background:var(--bll)}}
.pair-item.active{{background:var(--bll);border-left:3px solid var(--bl)}}
.pair-danger{{border-left:3px solid var(--red);background:var(--rl)}}
.pair-caution{{border-left:3px solid var(--or);background:var(--ol)}}
.pair-level{{font-size:13px}}
.pair-names{{font-weight:600;font-size:12px}}
.pair-reason{{color:var(--t3);font-size:11px;flex:1}}
.pair-count{{font-size:10px;color:var(--red);background:var(--rb);padding:1px 6px;border-radius:3px}}
.section-sep{{padding:8px 14px 4px;font-size:11px;color:var(--t3);font-weight:600}}
.clean-chips{{padding:4px 14px 10px;display:flex;flex-wrap:wrap;gap:3px}}
.clean-chip{{font-size:10px;padding:1px 7px;border:1px solid var(--bd);border-radius:3px;color:var(--t3);background:#f8fafc}}
/* Right: comparison detail */
.right{{flex:1;overflow-y:auto;padding:16px 20px}}
.cmp-header{{display:flex;align-items:center;gap:16px;margin-bottom:16px}}
.cmp-bidder{{flex:1;background:var(--sf);border-radius:8px;border:1px solid var(--bd);padding:14px;text-align:center}}
.cmp-bidder .num{{font-size:22px;font-weight:800}}
.cmp-bidder .company{{color:var(--t3);font-size:12px;margin-top:2px}}
.cmp-vs{{font-size:18px;color:var(--t3);font-weight:700}}
/* Dimension tabs */
.dim-tabs{{display:flex;gap:4px;margin-bottom:12px;border-bottom:2px solid var(--bd)}}
.dim-tab{{padding:8px 16px;font-size:12px;font-weight:600;border:none;background:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;color:var(--t3)}}
.dim-tab.active{{color:var(--bl);border-bottom-color:var(--bl)}}
.dim-tab .badge{{font-size:10px;background:var(--rb);color:var(--red);padding:0 5px;border-radius:8px;margin-left:3px}}
/* Comparison table */
.cmp-table{{width:100%;border-collapse:collapse;background:var(--sf);border-radius:8px;overflow:hidden;border:1px solid var(--bd)}}
.cmp-table th{{background:#f8fafc;padding:8px 12px;text-align:left;font-size:11px;color:var(--t3);border-bottom:1px solid var(--bd)}}
.cmp-table td{{padding:8px 12px;border-bottom:1px solid var(--bd);font-size:12px}}
.cmp-table tr:last-child td{{border-bottom:none}}
.field-name{{font-weight:600;color:var(--t2);min-width:90px}}
.val-match{{background:var(--rb);color:var(--red);font-weight:600}}
.val-caution{{background:var(--ob);color:var(--or);font-weight:600}}
.val-diff{{color:var(--t2)}}
.alert-bar{{display:flex;gap:8px;align-items:center;padding:10px 14px;border-radius:6px;margin-bottom:12px;font-size:12px;font-weight:600}}
.alert-danger{{background:var(--rl);border:1px solid #fca5a5;color:var(--red)}}
</style></head><body>
<div class="hdr"><h1>📄 围标串标检测 · 两两比对视图</h1><span class="sub">XX市政工程 · 30家投标人 · 参考「法正智能」交互模式</span></div>
<div class="layout">
  <div class="left">
    <div class="left-title">重复组列表 <span class="cnt">{len(pairs)}组</span></div>
    {pair_list}
    <div class="section-sep">无重复投标人（{len(clean_ids)}家）</div>
    <div class="clean-chips">{clean_chips}</div>
  </div>
  <div class="right">
    <div class="alert-bar alert-danger">⚠ 检测到 {len(pairs)} 组投标人之间存在元数据重复，其中 {len([p for p in pairs if p["level"]=="danger"])} 组涉及人员/组织身份一致</div>
    <div class="cmp-header">
      <div class="cmp-bidder"><div class="num" style="color:var(--red)">01</div><div class="company">宏达建设集团</div></div>
      <div class="cmp-vs">VS</div>
      <div class="cmp-bidder"><div class="num" style="color:var(--red)">08</div><div class="company">宏达建设集团</div></div>
    </div>
    <div class="dim-tabs">
      <button class="dim-tab active">📋 文档属性 <span class="badge">3</span></button>
      <button class="dim-tab">👤 创建者信息 <span class="badge">3</span></button>
      <button class="dim-tab">🕐 时间戳 <span class="badge">1</span></button>
      <button class="dim-tab">📊 文件信息</button>
    </div>
    <table class="cmp-table">
      <thead><tr><th>字段</th><th>投标人01</th><th>投标人08</th><th>结果</th></tr></thead>
      <tbody>
        <tr><td class="field-name">作者</td><td class="val-match">张明</td><td class="val-match">张明</td><td class="val-match">🔴 重复</td></tr>
        <tr><td class="field-name">最后修改者</td><td class="val-match">张明</td><td class="val-match">张明</td><td class="val-match">🔴 重复</td></tr>
        <tr><td class="field-name">公司</td><td class="val-match">宏达建设集团</td><td class="val-match">宏达建设集团</td><td class="val-match">🔴 重复</td></tr>
        <tr><td class="field-name">模板</td><td>模板1.dotx</td><td>模板8.dotx</td><td class="val-diff">— 不同</td></tr>
        <tr><td class="field-name">创建时间</td><td>2026-07-15 09:01</td><td>2026-07-22 09:08</td><td class="val-diff">— 不同</td></tr>
        <tr><td class="field-name">应用程序</td><td>WPS Office</td><td>Word 2019</td><td class="val-diff">— 不同</td></tr>
        <tr><td class="field-name">文件大小</td><td>127KB</td><td>176KB</td><td class="val-diff">— 不同</td></tr>
      </tbody>
    </table>
    <p style="margin-top:12px;color:var(--t3);font-size:12px">💡 点击左侧重复组切换查看不同投标人之间的比对详情</p>
  </div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Design B: Heatmap matrix + side detail panel
# ═══════════════════════════════════════════════════════════════════
def design_b() -> str:
    # Build heatmap: rows=fields, cols=bidders
    fields = [("author","作者"),("lmb","最后修改者"),("company","公司"),
              ("template","模板"),("created","创建时间")]
    danger_clusters = {frozenset(CA):("author","lmb","company"),
                       frozenset(CB):("author","lmb","company")}
    caution_clusters = {frozenset(CC):("template","created")}

    def cell_val(bid, fkey):
        b = B[bid-1]
        return b[fkey]

    def cell_cls(bid, fkey):
        for cluster, fkeys in danger_clusters.items():
            if bid in cluster and fkey in fkeys:
                return "hm-danger"
        for cluster, fkeys in caution_clusters.items():
            if bid in cluster and fkey in fkeys:
                return "hm-caution"
        return ""

    rows = ""
    for fkey, flabel in fields:
        rows += f'<tr><td class="hm-rowlabel">{flabel}</td>'
        for b in B:
            cls = cell_cls(b["id"], fkey)
            val = cell_val(b["id"], fkey)
            if len(val) > 6: val = val[:5] + "…"
            rows += f'<td class="{cls}" title="{cell_val(b["id"], fkey)}">{val}</td>'
        rows += '</tr>'

    # Column headers
    col_headers = "".join(f'<th class="hm-col">{b["id"]:02d}</th>' for b in B)
    # Mark flagged columns
    flagged_ids = CA + CB + CC

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>方案B · 热力矩阵+详情面板（参考Power BI + OECD）</title>
<style>
{CSS_BASE}
.top-bar{{display:flex;gap:0;background:var(--sf);border-bottom:1px solid var(--bd)}}
.kpi{{flex:1;padding:8px 16px;text-align:center;border-right:1px solid var(--bd)}}
.kpi:last-child{{border-right:none}}
.kpi__n{{font-size:20px;font-weight:800}}
.kpi__l{{font-size:10px;color:var(--t3)}}
.legend-bar{{padding:6px 16px;background:var(--sf);border-bottom:1px solid var(--bd);display:flex;gap:16px;font-size:11px;color:var(--t2)}}
.legend-bar .item{{display:flex;align-items:center;gap:4px}}
.legend-bar .sw{{width:12px;height:12px;border-radius:2px;border:1px solid}}
.lg-d{{background:var(--rb);border-color:#fca5a5}}
.lg-c{{background:var(--ob);border-color:#fde68a}}
.lg-n{{background:#f8fafc;border-color:var(--bd)}}
.matrix-wrap{{overflow:auto;padding:12px 16px;background:var(--sf);border-bottom:1px solid var(--bd)}}
.hm-table{{border-collapse:collapse;font-size:10px}}
.hm-table th,.hm-table td{{border:1px solid var(--bd);padding:3px 5px;text-align:center;white-space:nowrap;max-width:55px;overflow:hidden;text-overflow:ellipsis}}
.hm-rowlabel{{background:#f1f5f9;font-weight:600;text-align:right;min-width:70px;position:sticky;left:0;z-index:2}}
.hm-col{{background:#f8fafc;font-weight:600;min-width:40px;position:sticky;top:0;z-index:1}}
.hm-col--flag{{color:var(--red)}}
.hm-danger{{background:var(--rb);color:var(--red);font-weight:600}}
.hm-caution{{background:var(--ob);color:var(--or);font-weight:600}}
/* Red flag list */
.flags-section{{padding:12px 16px}}
.flags-title{{font-size:13px;font-weight:700;margin-bottom:8px}}
.flag-card{{display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin-bottom:6px;border-radius:6px;border:1px solid var(--bd);background:var(--sf)}}
.flag-card--danger{{border-left:4px solid var(--red);background:var(--rl)}}
.flag-card--caution{{border-left:4px solid var(--or);background:var(--ol)}}
.flag-icon{{font-size:14px;flex-shrink:0}}
.flag-body{{flex:1}}
.flag-title{{font-weight:600;font-size:12px;margin-bottom:2px}}
.flag-detail{{font-size:11px;color:var(--t2)}}
.flag-bidders{{display:flex;gap:4px;margin-top:4px}}
.flag-chip{{font-size:10px;padding:1px 6px;border-radius:3px;background:var(--rb);color:var(--red)}}
</style></head><body>
<div class="hdr"><h1>📄 围标串标检测 · 热力矩阵视图</h1><span class="sub">XX市政工程 · 30家投标人 · 参考「Power BI仪表盘 + OECD红旗清单」</span></div>
<div class="top-bar">
  <div class="kpi"><div class="kpi__n" style="color:var(--red)">10</div><div class="kpi__l">🔴 人员/组织重复</div></div>
  <div class="kpi"><div class="kpi__n" style="color:var(--or)">4</div><div class="kpi__l">🟡 模板/时间重复</div></div>
  <div class="kpi"><div class="kpi__n" style="color:var(--gr)">21</div><div class="kpi__l">⚪ 无异常</div></div>
  <div class="kpi"><div class="kpi__n" style="color:var(--bl)">30</div><div class="kpi__l">投标人总数</div></div>
</div>
<div class="legend-bar">
  <div class="item"><span class="sw lg-d"></span> 人员/组织身份重复</div>
  <div class="item"><span class="sw lg-c"></span> 模板/时间戳重复</div>
  <div class="item"><span class="sw lg-n"></span> 无异常</div>
  <div class="item" style="margin-left:auto">💡 鼠标悬停查看完整值</div>
</div>
<div class="matrix-wrap">
  <table class="hm-table">
    <thead><tr><th class="hm-rowlabel">字段 ＼ 投标人</th>{col_headers}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="flags-section">
  <div class="flags-title">🚩 检测到的风险线索</div>
  <div class="flag-card flag-card--danger">
    <span class="flag-icon">🔴</span>
    <div class="flag-body">
      <div class="flag-title">作者/最后修改者/公司 完全一致 — 围标组A</div>
      <div class="flag-detail">「张明」「宏达建设集团」出现在 4 家不同投标人的文档属性中</div>
      <div class="flag-bidders">
        <span class="flag-chip">01</span><span class="flag-chip">08</span><span class="flag-chip">17</span><span class="flag-chip">24</span>
      </div>
    </div>
  </div>
  <div class="flag-card flag-card--danger">
    <span class="flag-icon">🔴</span>
    <div class="flag-body">
      <div class="flag-title">作者/最后修改者/公司 完全一致 — 围标组B</div>
      <div class="flag-detail">「李芳」「正阳工程」出现在 3 家不同投标人的文档属性中</div>
      <div class="flag-bidders">
        <span class="flag-chip">05</span><span class="flag-chip">13</span><span class="flag-chip">29</span>
      </div>
    </div>
  </div>
  <div class="flag-card flag-card--caution">
    <span class="flag-icon">🟡</span>
    <div class="flag-body">
      <div class="flag-title">模板和创建时间完全一致 — 待人工复核</div>
      <div class="flag-detail">「通用投标模板V3.dotx」+ 创建时间「2026-07-15 09:30」精确到秒一致</div>
      <div class="flag-bidders">
        <span class="flag-chip" style="background:var(--ob);color:var(--or)">03</span>
        <span class="flag-chip" style="background:var(--ob);color:var(--or)">19</span>
      </div>
    </div>
  </div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Design C: Network graph + investigation panel
# ═══════════════════════════════════════════════════════════════════
def design_c() -> str:
    # SVG network: cluster groups + clean scatter
    nodes = []
    edges = []

    positions = {
        "CA": {"center": (300, 300), "label": "围标组A", "ids": CA, "color": "#dc2626", "fill": "#fee2e2"},
        "CB": {"center": (620, 260), "label": "围标组B", "ids": CB, "color": "#dc2626", "fill": "#fee2e2"},
        "CC": {"center": (480, 130), "label": "待复核", "ids": CC, "color": "#d97706", "fill": "#fef3c7"},
    }

    for key, info in positions.items():
        center = info["center"]
        ids = info["ids"]
        for j, bid in enumerate(ids):
            angle = j * 2 * math.pi / len(ids) - math.pi / 2
            x = center[0] + 65 * math.cos(angle)
            y = center[1] + 65 * math.sin(angle)
            nodes.append((bid, x, y, info["color"], info["fill"], len(ids) > 2 and 22 or 18))
            # Edges within cluster
            for k in range(j+1, len(ids)):
                edges.append((ids[j], ids[k], info["color"], "3" if key != "CC" else "2", "0.45"))

    # Clean nodes in grid
    clean_ids = [b["id"] for b in B if b["id"] not in CA+CB+CC]
    for j, bid in enumerate(clean_ids):
        col = j % 10
        row = j // 10
        x = 90 + col * 72
        y = 470 + row * 55
        nodes.append((bid, x, y, "#cbd5e1", "#f8fafc", 12))

    node_map = {n[0]: n for n in nodes}
    edge_svg = "".join(
        f'<line x1="{node_map[a][1]}" y1="{node_map[a][2]}" x2="{node_map[b][1]}" y2="{node_map[b][2]}" '
        f'stroke="{color}" stroke-width="{w}" opacity="{op}"/>'
        for a, b, color, w, op in edges
    )

    node_svg = ""
    for bid, x, y, color, fill, r in nodes:
        fs = 10 if r > 15 else 9
        fw = "700" if r > 15 else "500"
        node_svg += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{color}" stroke-width="2"/>'
        node_svg += f'<text x="{x}" y="{y+3.5}" text-anchor="middle" font-size="{fs}" font-weight="{fw}" fill="{color}">{bid:02d}</text>'

    # Cluster labels
    cluster_labels = ""
    for key, info in positions.items():
        cx, cy = info["center"]
        color = info["color"]
        label = f'{info["label"]}（{len(info["ids"])}家）'
        cluster_labels += f'<text x="{cx}" y="{cy - 85}" text-anchor="middle" font-size="12" font-weight="700" fill="{color}">{label}</text>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>方案C · 关系网络调查视图（参考Linkurious）</title>
<style>
{CSS_BASE}
.top-kpi{{display:flex;gap:0;background:var(--sf);border-bottom:1px solid var(--bd)}}
.tk{{flex:1;padding:8px;text-align:center;border-right:1px solid var(--bd)}}
.tk__n{{font-size:18px;font-weight:800}}
.tk__l{{font-size:10px;color:var(--t3)}}
.main-area{{display:flex;height:calc(100vh - 110px)}}
.graph-area{{flex:1;background:var(--sf);overflow:hidden;position:relative}}
.graph-area svg{{width:100%;height:100%}}
.graph-info{{position:absolute;top:12px;left:12px;background:rgba(255,255,255,0.95);padding:10px 14px;border-radius:6px;border:1px solid var(--bd);font-size:11px;line-height:1.8;max-width:240px}}
.graph-info h4{{font-size:12px;margin-bottom:4px}}
.side-panel{{width:300px;border-left:1px solid var(--bd);background:var(--sf);overflow-y:auto;flex-shrink:0;padding:14px}}
.sp-title{{font-size:13px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:6px}}
.cluster-card{{padding:10px 12px;border-radius:6px;margin-bottom:8px;border:1px solid var(--bd)}}
.cluster-card--danger{{border-left:4px solid var(--red);background:var(--rl)}}
.cluster-card--caution{{border-left:4px solid var(--or);background:var(--ol)}}
.cc-title{{font-weight:700;font-size:12px;margin-bottom:4px}}
.cc-detail{{font-size:11px;color:var(--t2);line-height:1.6}}
.cc-members{{display:flex;gap:4px;margin-top:6px}}
.cc-chip{{font-size:10px;padding:1px 8px;border-radius:10px;font-weight:600}}
.cc-chip--danger{{background:var(--rb);color:var(--red)}}
.cc-chip--caution{{background:var(--ob);color:var(--or)}}
.cc-verdict{{margin-top:6px;font-weight:700;font-size:11px}}
.legend{{margin-top:8px;padding:8px 0;border-top:1px solid var(--bd)}}
.legend .li{{display:flex;align-items:center;gap:5px;font-size:10px;color:var(--t2);margin-bottom:3px}}
.legend .dt{{width:10px;height:10px;border-radius:50%;border:2px solid}}
</style></head><body>
<div class="hdr"><h1>📄 围标串标检测 · 关系网络视图</h1><span class="sub">XX市政工程 · 30家投标人 · 参考「Linkurious图分析调查」</span></div>
<div class="top-kpi">
  <div class="tk"><div class="tk__n" style="color:var(--red)">2</div><div class="tk__l">围标组</div></div>
  <div class="tk"><div class="tk__n" style="color:var(--red)">7</div><div class="tk__l">高风险投标人</div></div>
  <div class="tk"><div class="tk__n" style="color:var(--or)">1</div><div class="tk__l">待复核组</div></div>
  <div class="tk"><div class="tk__n" style="color:var(--gr)">21</div><div class="tk__l">无关联</div></div>
  <div class="tk"><div class="tk__n" style="color:var(--bl)">30</div><div class="tk__l">总数</div></div>
</div>
<div class="main-area">
  <div class="graph-area">
    <div class="graph-info">
      <h4>🔍 关系网络说明</h4>
      • <strong style="color:var(--red)">红色节点/连线</strong>：人员/组织身份重复<br>
      • <strong style="color:var(--or)">橙色节点/连线</strong>：模板/时间戳重复<br>
      • <strong style="color:var(--t3)">灰色节点</strong>：未发现关联<br>
      • 连线 = 两家投标人共享相同元数据<br>
      • 自动聚类的围标组一目了然
    </div>
    <svg viewBox="0 0 820 620">
      {edge_svg}
      {cluster_labels}
      {node_svg}
    </svg>
  </div>
  <div class="side-panel">
    <div class="sp-title">🔬 调查面板</div>
    <div class="cluster-card cluster-card--danger">
      <div class="cc-title">🔴 围标组A · 4家</div>
      <div class="cc-detail">
        作者/修改者「张明」<br>公司「宏达建设集团」<br>3项元数据完全一致
      </div>
      <div class="cc-members">
        <span class="cc-chip cc-chip--danger">01</span>
        <span class="cc-chip cc-chip--danger">08</span>
        <span class="cc-chip cc-chip--danger">17</span>
        <span class="cc-chip cc-chip--danger">24</span>
      </div>
      <div class="cc-verdict" style="color:var(--red)">判定：疑似围标串标</div>
    </div>
    <div class="cluster-card cluster-card--danger">
      <div class="cc-title">🔴 围标组B · 3家</div>
      <div class="cc-detail">
        作者/修改者「李芳」<br>公司「正阳工程」<br>3项元数据完全一致
      </div>
      <div class="cc-members">
        <span class="cc-chip cc-chip--danger">05</span>
        <span class="cc-chip cc-chip--danger">13</span>
        <span class="cc-chip cc-chip--danger">29</span>
      </div>
      <div class="cc-verdict" style="color:var(--red)">判定：疑似围标串标</div>
    </div>
    <div class="cluster-card cluster-card--caution">
      <div class="cc-title">🟡 待复核 · 2家</div>
      <div class="cc-detail">
        模板「通用投标模板V3.dotx」<br>创建时间精确到秒一致<br>需人工判断是否为公开模板
      </div>
      <div class="cc-members">
        <span class="cc-chip cc-chip--caution">03</span>
        <span class="cc-chip cc-chip--caution">19</span>
      </div>
      <div class="cc-verdict" style="color:var(--or)">判定：需人工复核</div>
    </div>
    <div class="legend">
      <div class="li"><span class="dt" style="border-color:var(--red);background:var(--rb)"></span> 高风险（人员/组织重复）</div>
      <div class="li"><span class="dt" style="border-color:var(--or);background:var(--ob)"></span> 待复核（模板/时间戳）</div>
      <div class="li"><span class="dt" style="border-color:#cbd5e1;background:#f8fafc"></span> 无关联</div>
    </div>
  </div>
</div>
</body></html>"""


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, func in [
        ("方案A-两两比对视图（法正智能风格）.html", design_a),
        ("方案B-热力矩阵+红旗清单（Power BI风格）.html", design_b),
        ("方案C-关系网络调查（Linkurious风格）.html", design_c),
    ]:
        path = OUTPUT / name
        path.write_text(func(), encoding="utf-8")
        print(f"  ✅ {name}")
    print(f"\n📂 {OUTPUT}")


if __name__ == "__main__":
    main()

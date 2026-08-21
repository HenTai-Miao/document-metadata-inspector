"""Generate a single interactive HTML prototype simulating 30-bidder app navigation."""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "围标检测原型-30投标人"

# ═══════════════════════════════════════════════════════════════════
# 30 bidders with collusion traces
# ═══════════════════════════════════════════════════════════════════
BIDDERS = []
for i in range(1, 31):
    BIDDERS.append({
        "id": i, "author": f"员工{i}", "company": f"公司{i}",
        "lastModifiedBy": f"员工{i}", "template": f"模板{i}.dotx",
        "created": f"2026-07-{15+i%10:02d} 09:{i%60:02d}",
        "modified": f"2026-07-{16+i%10:02d} 14:{i%60:02d}",
        "app": "Microsoft Office Word" if i%2==0 else "WPS Office",
        "size": f"{120+i*7} KB", "sha": f"a3f{i:03d}b2c1d9e8",
    })

CLUSTER_A = [1, 8, 17, 24]
CLUSTER_B = [5, 13, 29]
CLUSTER_C = [3, 19]
for i in [0,7,16,23]:
    BIDDERS[i].update(author="张明", company="宏达建设集团有限公司", lastModifiedBy="张明")
for i in [4,12,28]:
    BIDDERS[i].update(author="李芳", company="正阳工程有限公司", lastModifiedBy="李芳")
for i in [2,18]:
    BIDDERS[i].update(template="通用投标模板V3.dotx", created="2026-07-15 09:30")

def risk_level(bid: int) -> str:
    if bid in CLUSTER_A or bid in CLUSTER_B: return "danger"
    if bid in CLUSTER_C: return "caution"
    return "clean"

def risk_text(bid: int) -> str:
    if bid in CLUSTER_A:
        others = [f"{b:02d}" for b in CLUSTER_A if b != bid]
        return f'作者/修改者「张明」、公司「宏达建设集团」— 同 {",".join(others)}'
    if bid in CLUSTER_B:
        others = [f"{b:02d}" for b in CLUSTER_B if b != bid]
        return f'作者/修改者「李芳」、公司「正阳工程」— 同 {",".join(others)}'
    if bid in CLUSTER_C:
        others = [f"{b:02d}" for b in CLUSTER_C if b != bid]
        return f'模板「通用投标模板V3」+创建时间一致 — 同 {",".join(others)}'
    return ""

# ═══════════════════════════════════════════════════════════════════
# Helper functions (must be defined before HTML generation)
# ═══════════════════════════════════════════════════════════════════

def _build_overview_rows(level: str) -> str:
    rows = ""
    for b in BIDDERS:
        if risk_level(b["id"]) != level:
            continue
        bid = b["id"]
        rt = risk_text(bid)
        tag = f'<span class="ov-tag ov-tag--{level}">{rt[:40]}{"…" if len(rt)>40 else ""}</span>' if rt else '<span class="ov-tag ov-tag--ok">✓ 无异常</span>'
        rows += f'<div class="overview-row overview-row--{level}" data-bid="{bid}"><span class="ov-num">{bid:02d}</span><span class="ov-name">投标人{bid:02d}</span><span class="ov-meta">{b["author"]} · {b["company"]}</span>{tag}</div>'
    return rows


def _build_clean_chips() -> str:
    chips = ""
    for b in BIDDERS:
        if risk_level(b["id"]) != "clean":
            continue
        bid = b["id"]
        chips += f'<button class="tab" onclick="showTab({bid})" style="margin:1px;">{bid:02d}</button>\n'
    return chips


# Build tab buttons and content panels
tabs_html = ""
panels_html = ""

for b in BIDDERS:
    bid = b["id"]
    level = risk_level(bid)
    level_label = {"danger": "🔴", "caution": "🟡", "clean": ""}[level]
    tab_class = f"tab tab--{level}"

    tabs_html += f'<button class="{tab_class}" onclick="showTab({bid})" id="tab-{bid}">{level_label}{bid:02d}</button>\n'

    risk_banner = ""
    if level != "clean":
        tone_class = f"risk-banner--{level}"
        icon = "⚠"
        risk_banner = f'<div class="risk-banner {tone_class}"><span class="risk-icon">{icon}</span><span>{risk_text(bid)}</span></div>'

    # 3 mock files per bidder
    files_html = ""
    for fname, ftype, fcolor in [("投标函.docx","DOC","#3b82f6"), ("报价清单.xlsx","XLS","#16a34a"), ("技术方案.pdf","PDF","#ef4444")]:
        files_html += f'''
        <div class="file-card">
          <span class="file-type" style="background:{fcolor}1a;color:{fcolor};border-color:{fcolor}">{ftype}</span>
          <span class="file-name">{fname}</span>
          <span class="file-meta">{b["size"]} · {b["sha"]}</span>
        </div>'''

    # Key fields grid
    fields = [
        ("作者", b["author"], "author" if level!="clean" else ""),
        ("最后修改者", b["lastModifiedBy"], "lastModifiedBy" if level!="clean" else ""),
        ("公司", b["company"], "company" if level!="clean" else ""),
        ("模板", b["template"], "template" if level=="caution" else ""),
        ("创建时间", b["created"], "created" if level=="caution" else ""),
        ("修改时间", b["modified"], ""),
        ("文件大小", b["size"], ""),
        ("文件指纹", b["sha"], ""),
    ]
    kv_html = ""
    for label, val, flag_key in fields:
        flag_class = ""
        if flag_key and level == "danger":
            flag_class = "kv--danger"
        elif flag_key and level == "caution":
            flag_class = "kv--caution"
        kv_html += f'<div class="kv {flag_class}"><div class="kv-label">{label}</div><div class="kv-value">{val}</div></div>'

    panels_html += f'''
    <div class="panel" id="panel-{bid}" style="display:none;">
      <div class="panel-header">
        <h2>投标人{bid:02d}</h2>
        <span class="bidder-company">{b["company"]}</span>
      </div>
      {risk_banner}
      <div class="files-section">{files_html}</div>
      <div class="kv-grid">{kv_html}</div>
    </div>'''

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>围标检测原型 · 30投标人</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
:root {{
  --red:#dc2626; --red-light:#fef2f2; --red-bg:#fee2e2;
  --orange:#d97706; --orange-light:#fffbeb; --orange-bg:#fef3c7;
  --green:#16a34a; --green-light:#f0fdf4;
  --blue:#2563eb; --gray:#6b7280; --border:#e5e7eb;
  --surface:#fff; --text:#1a1a2e; --text2:#4b5563; --text3:#9ca3af;
}}
body {{ font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:#f0f2f5; color:var(--text); }}

/* ── Header ─── */
.app-header {{ background:var(--surface); padding:12px 20px; border-bottom:2px solid var(--border); display:flex; align-items:center; justify-content:space-between; }}
.app-header h1 {{ font-size:17px; }}
.proj-name {{ color:var(--text3); font-size:12px; }}

/* ── KPI strip ─── */
.kpi-strip {{ display:flex; gap:0; background:var(--surface); border-bottom:1px solid var(--border); }}
.kpi {{ flex:1; padding:10px 16px; border-right:1px solid var(--border); text-align:center; }}
.kpi:last-child {{ border-right:none; }}
.kpi__num {{ font-size:22px; font-weight:800; }}
.kpi__label {{ font-size:11px; color:var(--text3); }}
.kpi--danger .kpi__num {{ color:var(--red); }}
.kpi--caution .kpi__num {{ color:var(--orange); }}
.kpi--clean .kpi__num {{ color:var(--green); }}
.kpi--total .kpi__num {{ color:var(--blue); }}

/* ── Tab bar ─── */
.tab-bar {{ display:flex; gap:2px; padding:8px 16px; background:var(--surface); border-bottom:1px solid var(--border); overflow-x:auto; flex-wrap:wrap; }}
.tab {{ padding:5px 12px; border-radius:5px; font-size:12px; font-weight:600; border:1px solid var(--border); background:var(--surface); cursor:pointer; white-space:nowrap; transition:all .15s; color:var(--text2); }}
.tab:hover {{ border-color:var(--blue); color:var(--blue); }}
.tab.active {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
.tab--danger {{ border-color:#fca5a5; background:var(--red-light); color:var(--red); }}
.tab--danger.active {{ background:var(--red); border-color:var(--red); }}
.tab--caution {{ border-color:#fde68a; background:var(--orange-light); color:var(--orange); }}
.tab--caution.active {{ background:var(--orange); border-color:var(--orange); }}

/* ── Content ─── */
.content {{ max-width:900px; margin:0 auto; padding:16px 20px 40px; }}
.panel {{ background:var(--surface); border-radius:8px; border:1px solid var(--border); overflow:hidden; }}
.panel-header {{ padding:12px 16px; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:12px; }}
.panel-header h2 {{ font-size:16px; }}
.bidder-company {{ color:var(--text3); font-size:13px; }}

/* ── Risk banner ─── */
.risk-banner {{ display:flex; align-items:center; gap:8px; padding:8px 16px; font-size:13px; font-weight:600; }}
.risk-banner--danger {{ background:var(--red-light); border-bottom:1px solid #fca5a5; color:var(--red); }}
.risk-banner--caution {{ background:var(--orange-light); border-bottom:1px solid #fde68a; color:var(--orange); }}
.risk-icon {{ font-size:14px; }}

/* ── File cards ─── */
.files-section {{ padding:8px 16px; display:flex; gap:8px; border-bottom:1px solid var(--border); }}
.file-card {{ display:flex; align-items:center; gap:6px; padding:6px 10px; background:#f8fafc; border-radius:5px; border:1px solid var(--border); font-size:12px; }}
.file-type {{ padding:1px 6px; border-radius:3px; font-size:10px; font-weight:700; border:1px solid; }}
.file-name {{ font-weight:600; }}
.file-meta {{ color:var(--text3); font-size:11px; }}

/* ── KV grid ─── */
.kv-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:var(--border); }}
.kv {{ padding:8px 12px; background:var(--surface); }}
.kv-label {{ font-size:10px; color:var(--text3); margin-bottom:2px; }}
.kv-value {{ font-size:12px; font-family:monospace; word-break:break-all; }}
.kv--danger {{ background:var(--red-light); }}
.kv--danger .kv-value {{ color:var(--red); font-weight:600; }}
.kv--caution {{ background:var(--orange-light); }}
.kv--caution .kv-value {{ color:var(--orange); font-weight:600; }}

/* ── Overview ─── */
.overview {{ max-width:1100px; margin:0 auto; padding:16px 20px 40px; }}
.overview-title {{ font-size:14px; font-weight:700; color:var(--text2); margin:16px 0 8px; display:flex; align-items:center; gap:8px; }}
.overview-title .badge {{ font-size:12px; padding:1px 8px; border-radius:10px; }}
.overview-row {{ display:flex; align-items:center; gap:10px; padding:8px 14px; margin-bottom:3px; border-radius:6px; background:var(--surface); border:1px solid var(--border); font-size:13px; cursor:pointer; transition:all .15s; }}
.overview-row:hover {{ border-color:var(--blue); }}
.overview-row--danger {{ border-left:4px solid var(--red); background:var(--red-light); }}
.overview-row--caution {{ border-left:4px solid var(--orange); background:var(--orange-light); }}
.overview-row--clean {{ opacity:0.5; }}
.ov-num {{ font-weight:800; min-width:28px; font-size:14px; color:var(--text3); }}
.overview-row--danger .ov-num {{ color:var(--red); }}
.ov-name {{ font-weight:600; min-width:70px; }}
.ov-meta {{ color:var(--text3); font-size:12px; flex:1; }}
.ov-tag {{ font-size:11px; padding:2px 8px; border-radius:4px; }}
.ov-tag--danger {{ background:var(--red-bg); color:var(--red); }}
.ov-tag--caution {{ background:var(--orange-bg); color:var(--orange); }}
.ov-tag--ok {{ background:#dcfce7; color:var(--green); }}
</style>
</head>
<body>

<div class="app-header">
  <h1>📄 文档元数据核验 · 围标串标检测</h1>
  <span class="proj-name">XX市政工程采购项目 · 30家投标人</span>
</div>

<div class="kpi-strip">
  <div class="kpi kpi--danger"><div class="kpi__num">7</div><div class="kpi__label">疑似围标</div></div>
  <div class="kpi kpi--caution"><div class="kpi__num">2</div><div class="kpi__label">待复核</div></div>
  <div class="kpi kpi--clean"><div class="kpi__num">21</div><div class="kpi__label">无异常</div></div>
  <div class="kpi kpi--total"><div class="kpi__num">30</div><div class="kpi__label">总数</div></div>
</div>

<!-- Overview section -->
<div class="overview" id="overview">
  <div class="overview-title">🔴 高风险投标人 <span class="badge" style="background:var(--red-bg);color:var(--red);">7家</span></div>
  {_build_overview_rows("danger")}
  <div class="overview-title" style="margin-top:12px;">🟡 待复核 <span class="badge" style="background:var(--orange-bg);color:var(--orange);">2家</span></div>
  {_build_overview_rows("caution")}
  <div class="overview-title" style="margin-top:12px;">⚪ 未发现异常 <span class="badge" style="background:#f1f5f9;color:var(--gray);">21家</span></div>
  <div style="display:flex;flex-wrap:wrap;gap:3px;">
    {_build_clean_chips()}
  </div>
</div>

<!-- Tab bar -->
<div class="tab-bar">
  <button class="tab tab--overview active" onclick="showOverview()" id="tab-overview">📋 总览</button>
  {tabs_html}
</div>

<!-- Panels -->
<div class="content">
  {panels_html}
</div>

<script>
function showTab(id) {{
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('panel-'+id).style.display = 'block';
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('overview').style.display = 'none';
}}
function showOverview() {{
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-overview').classList.add('active');
  document.getElementById('overview').style.display = 'block';
}}
document.querySelectorAll('.overview-row').forEach(row => {{
  row.addEventListener('click', () => {{
    const id = row.dataset.bid;
    if (id) showTab(parseInt(id));
  }});
}});
</script>
</body>
</html>"""


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "围标检测原型.html"
    path.write_text(html, encoding="utf-8")
    print(f"✅ {path}")
    print(f"📂 {OUTPUT}")


if __name__ == "__main__":
    main()

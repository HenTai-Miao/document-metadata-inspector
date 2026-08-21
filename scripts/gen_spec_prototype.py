"""
Generate a complete, design-spec-compliant mock page for 30-bidder collusion review.
Strictly follows: 人机协同数智业务底座 设计规范 v1.0 (柔光过渡 · 静谧科技)
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "围标检测-数智底座规范" / "index.html"

# ═══════════════════════════════════════════════════════════════════
# 30 bidders mock data
# ═══════════════════════════════════════════════════════════════════
B = []
for i in range(1, 31):
    B.append({"id":i,"author":f"员工{i}","company":f"公司{i}","lmb":f"员工{i}",
              "template":f"模板{i}.dotx","created":f"2026-07-{15+i%10:02d} 09:{i%60:02d}",
              "modified":f"2026-07-{16+i%10:02d} 14:{i%60:02d}",
              "app":"Word 2019" if i%2==0 else "WPS Office","size":f"{120+i*7}KB","files":3})
CA=[1,8,17,24]; CB=[5,13,29]; CC=[3,19]
for i in [0,7,16,23]: B[i].update(author="张明",company="宏达建设集团",lmb="张明")
for i in [4,12,28]: B[i].update(author="李芳",company="正阳工程",lmb="李芳")
for i in [2,18]: B[i].update(template="通用投标模板V3.dotx",created="2026-07-15 09:30")

def lvl(bid):
    if bid in CA or bid in CB: return "danger"
    if bid in CC: return "caution"
    return "ok"

def risk_desc(bid):
    if bid in CA: return "作者/修改者/公司","张明 · 宏达建设集团",[f"{b:02d}" for b in CA if b!=bid]
    if bid in CB: return "作者/修改者/公司","李芳 · 正阳工程",[f"{b:02d}" for b in CB if b!=bid]
    if bid in CC: return "模板/创建时间","通用投标模板V3 + 时间戳一致",[f"{b:02d}" for b in CC if b!=bid]
    return "","",""

# ═══════════════════════════════════════════════════════════════════
# Build HTML sections
# ═══════════════════════════════════════════════════════════════════

# -- Risk alert cards (collusion groups) --
alert_cards = ""
for cluster_id, cluster_name, members, desc, fields, tone in [
    ("A","围标组A",CA,"张明 · 宏达建设集团","作者、最后修改者、公司","danger"),
    ("B","围标组B",CB,"李芳 · 正阳工程","作者、最后修改者、公司","danger"),
    ("C","待复核组",CC,"通用投标模板V3 + 时间戳一致","模板、创建时间","caution"),
]:
    color = "var(--danger)" if tone=="danger" else "var(--warn)"
    weak = "var(--danger-weak)" if tone=="danger" else "var(--warn-weak)"
    chips = "".join(f'<span class="code">{m:02d}</span>' for m in members)
    alert_cards += f"""
    <div class="card" style="border-left:3px solid {color}">
      <div class="card-h">
        <b>{cluster_name}</b>
        <span class="meta">· {len(members)}家投标人</span>
        <span class="right">{'疑似围标串标' if tone=='danger' else '需人工复核'}</span>
      </div>
      <div class="row">
        <div class="body">
          <div class="l1">
            <span class="name">{desc}</span>
            <span class="pill {'due' if tone=='danger' else 'today'}">{fields}</span>
          </div>
          <div class="l2" style="margin-top:6px">涉及投标人 {chips}</div>
        </div>
      </div>
    </div>"""

# -- Bidder list rows (sorted: danger → caution → ok) --
sorted_bids = sorted(B, key=lambda b: (
    0 if b["id"] in CA+CB else 1 if b["id"] in CC else 2
))

list_rows = ""
for b in sorted_bids:
    bid = b["id"]
    level = lvl(bid)
    if level == "ok":
        list_rows += f"""
        <div class="row" style="opacity:.5">
          <div class="body">
            <div class="l1">
              <span class="name">投标人{bid:02d}</span>
              <span class="pill week">{b['files']}个文件</span>
            </div>
            <div class="l2">{b['author']} <em>·</em> {b['company']}</div>
          </div>
          <span class="pill week">未发现异常</span>
        </div>"""
        continue

    field, desc, others = risk_desc(bid)
    pill_cls = "due" if level == "danger" else "today"
    stage_cls = "s1" if level == "danger" else "s3"
    stage_text = "高风险" if level == "danger" else "待复核"
    others_str = "、".join(others)
    list_rows += f"""
    <div class="row">
      <div class="body">
        <div class="l1">
          <span class="name">投标人{bid:02d}</span>
          <span class="pill {pill_cls}">{field}</span>
          <span class="stage {stage_cls}">{stage_text}</span>
        </div>
        <div class="l2">{b['author']} <em>·</em> {b['company']} <em>·</em> <span class="{'bad' if level=='danger' else ''}" style="{'color:var(--danger)' if level=='danger' else 'color:var(--warn)'}">同 投标人{others_str}</span></div>
      </div>
      <span class="code">{b['files']}个文件</span>
    </div>"""

# -- Detail comparison section (group A example) --
detail_rows = ""
fields_detail = [
    ("作者","张明","张明","张明","张明","match"),
    ("最后修改者","张明","张明","张明","张明","match"),
    ("公司","宏达建设集团","宏达建设集团","宏达建设集团","宏达建设集团","match"),
    ("模板","模板01.dotx","模板08.dotx","模板17.dotx","模板24.dotx","diff"),
    ("创建时间","2026-07-15 09:01","2026-07-22 09:08","2026-07-29 09:14","2026-08-05 09:20","diff"),
    ("应用程序","WPS Office","Word 2019","WPS Office","Word 2019","diff"),
]
for fname, v1, v2, v3, v4, status in fields_detail:
    cls = "m" if status == "match" else "d"
    cells = "".join(f'<td class="{cls}">{v}</td>' for v in [v1,v2,v3,v4])
    tag = '<span class="pill due">重复</span>' if status=="match" else '<span class="pill week">不同</span>'
    detail_rows += f"<tr><td class='fname'>{fname}</td>{cells}<td>{tag}</td></tr>"

# -- Matrix heatmap section --
matrix_fields = [("author","作者"),("lmb","修改者"),("company","公司"),("template","模板"),("created","创建时间")]
matrix_rows = ""
for fkey, flabel in matrix_fields:
    matrix_rows += f"<tr><td class='hm-l'>{flabel}</td>"
    for b in B:
        bid = b["id"]
        val = b[fkey]
        if len(val) > 6: val = val[:5]+"…"
        danger_fields = {"author","lmb","company"} if (bid in CA or bid in CB) else set()
        caution_fields = {"template","created"} if bid in CC else set()
        if fkey in danger_fields: cls = "hm-d"
        elif fkey in caution_fields: cls = "hm-c"
        else: cls = ""
        matrix_rows += f"<td class='{cls}' title='{b[fkey]}'>{val}</td>"
    matrix_rows += "</tr>"
matrix_cols = "".join(f"<th>{b['id']:02d}</th>" for b in B)

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>文档元数据核验 · 围标串标检测</title>
<style>
:root{{
  --primary:#034ed6; --primary-hover:#0342b8; --primary-weak:#eaf1fe; --primary-weak-2:#f4f8ff;
  --primary-line-hover:#bcd0f5; --primary-a07:rgba(3,78,214,.07); --primary-a08:rgba(3,78,214,.08);
  --primary-a09:rgba(3,78,214,.085); --primary-a10:rgba(3,78,214,.10); --primary-a28:rgba(3,78,214,.28);
  --ink:#141928; --sub:#5d6579; --faint:#6b7489;
  --line:#e8eaf0; --line-soft:#f0f2f7;
  --dark:#0e1226; --dark-2:#131834; --dark-line:rgba(125,145,205,.16);
  --dark-ink:#e9edfa; --dark-sub:#8b98bd;
  --ok:#15803d; --warn:#a85c00; --warn-weak:#fdf3e4; --danger:#c93438; --danger-weak:#fdeeee;
  --teal:#0f766e; --violet:#7c3aed; --cyan:#1fb2de;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --radius-chip:7px; --radius-item:8px; --radius-btn:9px; --radius-field:10px;
  --radius-panel:12px; --radius-card:13px; --radius-panel-dk:14px; --radius-full:999px;
  --shadow-panel:0 12px 32px rgba(14,18,38,.18);
  --shadow-float:0 4px 14px rgba(20,25,40,.10);
  --shadow-pop:0 6px 20px rgba(20,25,40,.12);
  --wash-warm:rgba(124,58,237,.055); --wash-cool:rgba(31,178,222,.075);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,-apple-system,"Segoe UI",sans-serif;
  background:#fff;color:var(--ink);font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased;
}}
.ic{{width:16px;height:16px;flex:none}}
:focus-visible{{outline:2px solid var(--primary);outline-offset:2px;border-radius:4px}}

/* ── Wash ── */
.wash{{position:absolute;top:0;left:0;right:0;height:420px;pointer-events:none;z-index:0;
  background:
    radial-gradient(720px 340px at 14% -12%, var(--primary-a09), transparent 66%),
    radial-gradient(860px 380px at 52% -16%, var(--wash-warm), transparent 64%),
    radial-gradient(640px 320px at 88% -10%, var(--wash-cool), transparent 66%);}}
.wash::after{{content:"";position:absolute;inset:auto 0 0 0;height:160px;
  background:linear-gradient(180deg,rgba(255,255,255,0),#fff)}}

/* ── Header ── */
.hdr{{position:sticky;top:0;z-index:40;height:56px;background:rgba(255,255,255,.78);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line-soft);display:flex;align-items:center;gap:12px;padding:0 28px}}
.hdr .brand{{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:600}}
.hdr .brand svg{{width:22px;height:22px}}
.hdr .sep{{color:var(--faint);font-weight:400}}
.hdr .sub-t{{font-size:13.5px;color:var(--sub)}}
.hdr .ver{{margin-left:auto;font-family:var(--mono);font-size:11.5px;color:var(--sub);
  border:1px solid var(--line);border-radius:var(--radius-full);padding:3px 12px;background:#fff}}

/* ── Layout ── */
.page{{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:0 28px}}
main{{padding:28px 0 80px;min-width:0}}

/* ── Section titles ── */
.sec-h{{font-size:15px;font-weight:700;margin:32px 0 14px;display:flex;align-items:center;gap:10px}}
.sec-h .no{{font-family:var(--mono);font-size:12px;color:var(--faint);font-weight:600}}
.sec-h .cnt{{font-size:12px;font-weight:600;padding:2px 10px;border-radius:var(--radius-full)}}
.sec-h .cnt.red{{color:var(--danger);background:var(--danger-weak)}}
.sec-h .cnt.org{{color:var(--warn);background:var(--warn-weak)}}
.sec-h .cnt.gry{{color:var(--faint);background:var(--line-soft)}}

/* ── Status bar ── */
.status-bar{{display:flex;align-items:center;gap:12px;height:48px;padding:0 8px 0 14px;
  background:#fff;border:1px solid var(--line);border-radius:var(--radius-panel)}}
.status-bar .tag{{flex:none;font-size:12px;font-weight:700;color:var(--ok);
  background:#e7f6f0;border-radius:var(--radius-chip);padding:4px 10px}}
.status-bar .txt{{font-size:14px;color:var(--ink)}}
.status-bar .txt b{{font-weight:600}}
.status-bar .spacer{{flex:1}}
.status-bar .num{{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:12.5px;color:var(--sub)}}

/* ── Dark data panel (KPI) ── */
.kpi-panel{{background:var(--dark);border-radius:var(--radius-panel-dk);color:var(--dark-ink);
  overflow:hidden;box-shadow:var(--shadow-panel)}}
.kpi-panel .panel-h{{display:flex;align-items:center;gap:10px;padding:13px 18px;background:var(--dark-2);
  border-bottom:1px solid var(--dark-line)}}
.kpi-panel .panel-h b{{font-size:13.5px;font-weight:600}}
.kpi-panel .panel-h .meta{{margin-left:auto;font-size:12px;color:var(--dark-sub)}}
.kgrid{{display:grid;grid-template-columns:repeat(4,1fr)}}
.kgrid .k{{padding:16px 18px;position:relative}}
.kgrid .k:not(:last-child)::after{{content:"";position:absolute;right:0;top:14px;bottom:14px;width:1px;background:var(--dark-line)}}
.kgrid .k .lbl{{font-size:12px;color:var(--dark-sub)}}
.kgrid .k .val{{margin-top:4px;font-family:var(--mono);font-size:26px;font-weight:700;line-height:1.25;
  font-variant-numeric:tabular-nums;color:#fff}}
.kgrid .k .val.bad{{color:#ff8a8f}}
.kgrid .k .val.warn{{color:#ffc46b}}
.kgrid .k .val.ok{{color:#5fd6a2}}
.kgrid .k .dlt{{margin-top:2px;font-size:11.5px;color:var(--dark-sub)}}

/* ── Card ── */
.card{{background:#fff;border:1px solid var(--line);border-radius:var(--radius-card);overflow:hidden}}
.card+.card{{margin-top:14px}}
.card-h{{display:flex;align-items:center;gap:9px;padding:14px 18px;border-bottom:1px solid var(--line-soft)}}
.card-h .ic{{width:14px;height:14px;color:var(--faint)}}
.card-h b{{font-size:15px;font-weight:600}}
.card-h .meta{{font-size:12px;color:var(--faint);font-weight:400}}
.card-h .right{{margin-left:auto;font-size:12.5px;color:var(--sub);font-weight:600}}
.row{{display:flex;align-items:flex-start;gap:12px;padding:13px 18px;border-bottom:1px solid var(--line-soft)}}
.row:last-child{{border-bottom:none}}
.row:hover{{background:#fafbfe}}
.row .body{{min-width:0;flex:1}}
.row .l1{{display:flex;align-items:center;gap:9px;flex-wrap:wrap}}
.row .name{{font-size:14px;font-weight:600;color:var(--ink)}}
.row .l2{{margin-top:4px;font-size:12.8px;color:var(--sub)}}
.row .l2 em{{font-style:normal;color:var(--faint);margin:0 5px}}
.row .l2 .bad{{color:var(--danger);font-weight:500}}
.row .pill{{align-self:center}}

.pill{{flex:none;font-size:12px;font-weight:600;border-radius:var(--radius-full);padding:3px 11px}}
.pill.due{{color:var(--danger);background:var(--danger-weak)}}
.pill.today{{color:var(--warn);background:var(--warn-weak)}}
.pill.week{{color:var(--sub);background:var(--line-soft)}}

.stage{{flex:none;font-size:12px;font-weight:600;border-radius:var(--radius-chip);padding:3px 10px}}
.stage.s1{{color:var(--danger);background:var(--danger-weak)}}
.stage.s3{{color:var(--warn);background:var(--warn-weak)}}
.stage.s4{{color:var(--teal);background:#e7f6f4}}

.code{{font-family:var(--mono);font-size:11.5px;color:var(--sub);background:var(--line-soft);
  border-radius:6px;padding:2px 7px;letter-spacing:.02em;margin-right:3px}}

/* ── Comparison table ── */
.cmp-tbl{{width:100%;border-collapse:collapse;font-size:13px;background:#fff;
  border:1px solid var(--line);border-radius:var(--radius-card);overflow:hidden}}
.cmp-tbl th{{font-size:12px;font-weight:600;color:var(--sub);text-align:left;padding:10px 14px;
  border-bottom:1px solid var(--line);background:#fcfcfe;white-space:nowrap}}
.cmp-tbl td{{padding:9px 14px;border-bottom:1px solid var(--line-soft);vertical-align:middle}}
.cmp-tbl tr:last-child td{{border-bottom:none}}
.cmp-tbl .fname{{font-weight:600;color:var(--ink);min-width:80px}}
.cmp-tbl td.m{{background:var(--danger-weak);color:var(--danger);font-weight:600;font-family:var(--mono);font-size:12.5px}}
.cmp-tbl td.d{{color:var(--sub);font-family:var(--mono);font-size:12.5px}}

/* ── Matrix ── */
.matrix-wrap{{overflow:auto;border:1px solid var(--line);border-radius:var(--radius-card);background:#fff}}
.hm-tbl{{border-collapse:collapse;font-size:10.5px;width:100%}}
.hm-tbl th,.hm-tbl td{{border:1px solid var(--line-soft);padding:4px 5px;text-align:center;white-space:nowrap;max-width:52px;overflow:hidden;text-overflow:ellipsis}}
.hm-tbl th{{background:#fcfcfe;font-weight:600;font-family:var(--mono);font-size:10px;color:var(--sub)}}
.hm-l{{background:#f8f9fc;font-weight:600;text-align:right !important;min-width:64px;font-size:11px;color:var(--ink);position:sticky;left:0;z-index:2}}
.hm-d{{background:var(--danger-weak);color:var(--danger);font-weight:600}}
.hm-c{{background:var(--warn-weak);color:var(--warn);font-weight:600}}

/* ── Legend ── */
.legend{{display:flex;gap:18px;align-items:center;font-size:12px;color:var(--sub);margin-bottom:10px;flex-wrap:wrap}}
.legend .li{{display:flex;align-items:center;gap:5px}}
.legend .sw{{width:12px;height:12px;border-radius:3px;border:1px solid}}
.legend .sw.d{{background:var(--danger-weak);border-color:#f0b8b8}}
.legend .sw.c{{background:var(--warn-weak);border-color:#f0d8a8}}
.legend .sw.n{{background:#f8f9fc;border-color:var(--line)}}

/* ── Grid layout for sections ── */
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:900px){{.two-col{{grid-template-columns:1fr}}}}

.ghost{{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border-radius:var(--radius-item);
  background:#fff;border:1px solid var(--line);font-size:12.5px;font-weight:500;color:var(--ink)}}
.ghost .ic{{width:13px;height:13px;color:var(--sub)}}
.primary-btn{{display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 16px;
  border-radius:var(--radius-btn);border:none;background:var(--primary);color:#fff;font-size:13.5px;font-weight:600}}
.primary-btn .ic{{width:13px;height:13px}}
</style>
</head>
<body>

<!-- SVG sprites (no emoji, all inline SVG per spec) -->
<svg style="display:none" xmlns="http://www.w3.org/2000/svg">
  <symbol id="i-logo" viewBox="0 0 24 24"><rect x="3" y="3" width="8.6" height="8.6" rx="2.4" fill="#034ed6"/><rect x="12.4" y="3" width="8.6" height="8.6" rx="2.4" fill="#034ed6" opacity=".28"/><rect x="3" y="12.4" width="8.6" height="8.6" rx="2.4" fill="#034ed6" opacity=".28"/><rect x="12.4" y="12.4" width="8.6" height="8.6" rx="2.4" fill="#1fb2de" opacity=".85"/></symbol>
  <symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 3.5l7 2.6v5.2c0 4.6-3 7.6-7 9.2-4-1.6-7-4.6-7-9.2V6.1l7-2.6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><path d="M12 4L2.8 20h18.4L12 4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17.4" r="1" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="M4.5 12.5l5 5 10-11" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-users" viewBox="0 0 24 24"><circle cx="9.5" cy="8.5" r="3.4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 19c.6-3 3-4.6 6-4.6s5.4 1.6 6 4.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M16 5.6a3 3 0 0 1 0 5.8M18.6 19c-.3-1.9-1.3-3.3-2.8-4.1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></symbol>
  <symbol id="i-download" viewBox="0 0 24 24"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-doc" viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 3v5h5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></symbol>
  <symbol id="i-grid" viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="4" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/></symbol>
</svg>

<div class="wash"></div>

<!-- ══ Header ══ -->
<header class="hdr">
  <div class="brand"><svg><use href="#i-logo"/></svg>文档元数据核验</div>
  <span class="sep">/</span>
  <span class="sub-t">XX市政工程采购项目</span>
  <span class="ver">v0.1.0</span>
</header>

<!-- ══ Main ══ -->
<div class="page">
<main>

  <!-- ── Status bar ── -->
  <div style="margin-top:20px">
    <div class="status-bar">
      <span class="tag"><svg class="ic" style="width:13px;height:13px;color:var(--ok)"><use href="#i-check"/></svg> 核验完成</span>
      <span class="txt"><b>30</b> 家投标人 · <b>90</b> 个文件 · <b>2,075</b> 条元数据</span>
      <span class="spacer"></span>
      <span class="num">2026-08-06 10:30</span>
      <button class="ghost"><svg class="ic"><use href="#i-download"/></svg>导出报告</button>
    </div>
  </div>

  <!-- ── KPI dark panel ── -->
  <div style="margin-top:16px">
    <div class="kpi-panel">
      <div class="panel-h">
        <svg class="ic" style="color:var(--dark-sub)"><use href="#i-shield"/></svg>
        <b>围标串标风险概览</b>
        <span class="meta">基于文档元数据交叉比对</span>
      </div>
      <div class="kgrid">
        <div class="k">
          <div class="lbl">疑似围标（人员/组织重复）</div>
          <div class="val bad">7</div>
          <div class="dlt">2 组 · 10 处重复</div>
        </div>
        <div class="k">
          <div class="lbl">待复核（模板/时间戳）</div>
          <div class="val warn">2</div>
          <div class="dlt">1 组 · 4 处重复</div>
        </div>
        <div class="k">
          <div class="lbl">未发现异常</div>
          <div class="val ok">21</div>
          <div class="dlt">占 70%</div>
        </div>
        <div class="k">
          <div class="lbl">投标人总数</div>
          <div class="val">30</div>
          <div class="dlt">90 个文件 · 3 种格式</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Risk alerts ── -->
  <div class="sec-h"><svg class="ic" style="color:var(--danger)"><use href="#i-alert"/></svg>检测到的风险线索</div>
  <div class="two-col">
    {alert_cards}
  </div>

  <!-- ── Matrix ── -->
  <div class="sec-h">
    <span class="no">01</span>元数据交叉比对矩阵
    <span class="cnt red">10</span><span style="color:var(--danger);font-size:12px">重复</span>
    <span class="cnt org">4</span><span style="color:var(--warn);font-size:12px">待复核</span>
  </div>
  <div class="legend">
    <div class="li"><span class="sw d"></span> 人员/组织身份重复</div>
    <div class="li"><span class="sw c"></span> 模板/时间戳重复</div>
    <div class="li"><span class="sw n"></span> 无异常</div>
  </div>
  <div class="matrix-wrap">
    <table class="hm-tbl">
      <thead><tr><th class="hm-l">字段 ＼ 投标人</th>{matrix_cols}</tr></thead>
      <tbody>{matrix_rows}</tbody>
    </table>
  </div>

  <!-- ── Bidder list ── -->
  <div class="sec-h">
    <svg class="ic" style="color:var(--primary)"><use href="#i-users"/></svg>
    投标人明细（按风险排序）
  </div>
  <div class="card">
    {list_rows}
  </div>

  <!-- ── Detail comparison ── -->
  <div class="sec-h">
    <span class="no">02</span>围标组A · 逐字段对比
    <span class="cnt red">3项重复</span>
  </div>
  <table class="cmp-tbl">
    <thead>
      <tr><th>字段</th><th>投标人01</th><th>投标人08</th><th>投标人17</th><th>投标人24</th><th>结果</th></tr>
    </thead>
    <tbody>{detail_rows}</tbody>
  </table>

  <p style="margin-top:24px;font-size:12.5px;color:var(--faint);text-align:center">
    文档元数据核验 · 离线分析 · 所有比对均在本地完成，不上传任何文件
  </p>

</main>
</div>

</body>
</html>"""


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(HTML, encoding="utf-8")
    print(f"✅ {OUTPUT}")
    print(f"📂 {OUTPUT.parent}")


if __name__ == "__main__":
    main()

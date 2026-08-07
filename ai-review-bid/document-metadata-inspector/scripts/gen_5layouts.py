"""
Generate 5 complete, design-spec-compliant page layouts for 30-bidder collusion review.
Strictly follows: 人机协同数智业务底座 设计规范 v1.0
Each layout is a different structural approach with full mock data.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "围标检测-5套方案"

# ═══════════════════════════════════════════════════════════════════
# Data
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
    if bid in CA+CB: return "danger"
    if bid in CC: return "caution"
    return "ok"

# ═══════════════════════════════════════════════════════════════════
# Shared CSS (exact tokens from design spec)
# ═══════════════════════════════════════════════════════════════════
SHARED_HEAD = """
<svg style="display:none" xmlns="http://www.w3.org/2000/svg">
  <symbol id="i-logo" viewBox="0 0 24 24"><rect x="3" y="3" width="8.6" height="8.6" rx="2.4" fill="#034ed6"/><rect x="12.4" y="3" width="8.6" height="8.6" rx="2.4" fill="#034ed6" opacity=".28"/><rect x="3" y="12.4" width="8.6" height="8.6" rx="2.4" fill="#034ed6" opacity=".28"/><rect x="12.4" y="12.4" width="8.6" height="8.6" rx="2.4" fill="#1fb2de" opacity=".85"/></symbol>
  <symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 3.5l7 2.6v5.2c0 4.6-3 7.6-7 9.2-4-1.6-7-4.6-7-9.2V6.1l7-2.6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><path d="M12 4L2.8 20h18.4L12 4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17.4" r="1" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="M4.5 12.5l5 5 10-11" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-users" viewBox="0 0 24 24"><circle cx="9.5" cy="8.5" r="3.4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 19c.6-3 3-4.6 6-4.6s5.4 1.6 6 4.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M16 5.6a3 3 0 0 1 0 5.8M18.6 19c-.3-1.9-1.3-3.3-2.8-4.1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></symbol>
  <symbol id="i-download" viewBox="0 0 24 24"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-doc" viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 3v5h5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></symbol>
  <symbol id="i-grid" viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="4" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/></symbol>
  <symbol id="i-chev-r" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-chev-d" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M20 20l-4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></symbol>
  <symbol id="i-list" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></symbol>
  <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
</svg>
"""

SHARED_CSS = """
:root{
  --primary:#034ed6;--primary-hover:#0342b8;--primary-weak:#eaf1fe;--primary-weak-2:#f4f8ff;
  --primary-a09:rgba(3,78,214,.085);--primary-a10:rgba(3,78,214,.10);
  --ink:#141928;--sub:#5d6579;--faint:#6b7489;
  --line:#e8eaf0;--line-soft:#f0f2f7;
  --dark:#0e1226;--dark-2:#131834;--dark-line:rgba(125,145,205,.16);--dark-ink:#e9edfa;--dark-sub:#8b98bd;
  --ok:#15803d;--warn:#a85c00;--warn-weak:#fdf3e4;--danger:#c93438;--danger-weak:#fdeeee;
  --teal:#0f766e;--violet:#7c3aed;--cyan:#1fb2de;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --radius-chip:7px;--radius-item:8px;--radius-btn:9px;--radius-field:10px;
  --radius-panel:12px;--radius-card:13px;--radius-panel-dk:14px;--radius-full:999px;
  --shadow-panel:0 12px 32px rgba(14,18,38,.18);--shadow-pop:0 6px 20px rgba(20,25,40,.12);
  --wash-warm:rgba(124,58,237,.055);--wash-cool:rgba(31,178,222,.075);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,-apple-system,"Segoe UI",sans-serif;
  background:#fff;color:var(--ink);font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
.ic{width:16px;height:16px;flex:none}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px;border-radius:4px}
.wash{position:absolute;top:0;left:0;right:0;height:380px;pointer-events:none;z-index:0;
  background:radial-gradient(720px 340px at 14% -12%,var(--primary-a09),transparent 66%),
  radial-gradient(860px 380px at 52% -16%,var(--wash-warm),transparent 64%),
  radial-gradient(640px 320px at 88% -10%,var(--wash-cool),transparent 66%)}
.wash::after{content:"";position:absolute;inset:auto 0 0 0;height:140px;background:linear-gradient(180deg,rgba(255,255,255,0),#fff)}
.hdr{position:sticky;top:0;z-index:40;height:56px;background:rgba(255,255,255,.78);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line-soft);display:flex;align-items:center;gap:12px;padding:0 28px}
.hdr .brand{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:600}
.hdr .brand svg{width:22px;height:22px}
.hdr .sep{color:var(--faint)}
.hdr .sub-t{font-size:13.5px;color:var(--sub)}
.hdr .ver{margin-left:auto;font-family:var(--mono);font-size:11.5px;color:var(--sub);
  border:1px solid var(--line);border-radius:var(--radius-full);padding:3px 12px;background:#fff}
.page{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:0 28px}
.sec-h{font-size:15px;font-weight:700;margin:32px 0 14px;display:flex;align-items:center;gap:10px}
.sec-h .ic{color:var(--faint)}
.card{background:#fff;border:1px solid var(--line);border-radius:var(--radius-card);overflow:hidden}
.card+.card{margin-top:12px}
.card-h{display:flex;align-items:center;gap:9px;padding:14px 18px;border-bottom:1px solid var(--line-soft)}
.card-h b{font-size:15px;font-weight:600}
.card-h .meta{font-size:12px;color:var(--faint)}
.card-h .right{margin-left:auto;font-size:12.5px;color:var(--sub);font-weight:600}
.row{display:flex;align-items:flex-start;gap:12px;padding:13px 18px;border-bottom:1px solid var(--line-soft)}
.row:last-child{border-bottom:none}
.row:hover{background:#fafbfe}
.row .body{min-width:0;flex:1}
.row .l1{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.row .name{font-size:14px;font-weight:600}
.row .l2{margin-top:4px;font-size:12.8px;color:var(--sub)}
.row .l2 em{font-style:normal;color:var(--faint);margin:0 5px}
.pill{flex:none;font-size:12px;font-weight:600;border-radius:var(--radius-full);padding:3px 11px}
.pill.due{color:var(--danger);background:var(--danger-weak)}
.pill.today{color:var(--warn);background:var(--warn-weak)}
.pill.week{color:var(--sub);background:var(--line-soft)}
.stage{flex:none;font-size:12px;font-weight:600;border-radius:var(--radius-chip);padding:3px 10px}
.stage.s1{color:var(--danger);background:var(--danger-weak)}
.stage.s3{color:var(--warn);background:var(--warn-weak)}
.code{font-family:var(--mono);font-size:11.5px;color:var(--sub);background:var(--line-soft);
  border-radius:6px;padding:2px 7px;margin-right:3px}
.ghost{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border-radius:var(--radius-item);
  background:#fff;border:1px solid var(--line);font-size:12.5px;font-weight:500;color:var(--ink);cursor:pointer}
.ghost .ic{width:13px;height:13px;color:var(--sub)}
.primary-btn{display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 16px;
  border-radius:var(--radius-btn);border:none;background:var(--primary);color:#fff;font-size:13.5px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
.tbl-wrap{border:1px solid var(--line);border-radius:var(--radius-card);overflow:auto;background:#fff}
th{font-size:12px;font-weight:600;color:var(--sub);text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);background:#fcfcfe;white-space:nowrap}
td{padding:9px 14px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
tr:last-child td{border-bottom:none}
.kpi-panel{background:var(--dark);border-radius:var(--radius-panel-dk);overflow:hidden;box-shadow:var(--shadow-panel)}
.kpi-panel .ph{display:flex;align-items:center;gap:10px;padding:13px 18px;background:var(--dark-2);border-bottom:1px solid var(--dark-line)}
.kpi-panel .ph b{font-size:13.5px;font-weight:600;color:var(--dark-ink)}
.kpi-panel .ph .meta{margin-left:auto;font-size:12px;color:var(--dark-sub)}
.kgrid{display:grid;grid-template-columns:repeat(4,1fr)}
.kgrid .k{padding:16px 18px;position:relative}
.kgrid .k:not(:last-child)::after{content:"";position:absolute;right:0;top:14px;bottom:14px;width:1px;background:var(--dark-line)}
.kgrid .k .lbl{font-size:12px;color:var(--dark-sub)}
.kgrid .k .val{margin-top:4px;font-family:var(--mono);font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;color:#fff}
.kgrid .k .val.bad{color:#ff8a8f}.kgrid .k .val.warn{color:#ffc46b}.kgrid .k .val.ok{color:#5fd6a2}
.kgrid .k .dlt{margin-top:2px;font-size:11.5px;color:var(--dark-sub)}
.legend{display:flex;gap:18px;font-size:12px;color:var(--sub);margin-bottom:10px;flex-wrap:wrap}
.legend .li{display:flex;align-items:center;gap:5px}
.legend .sw{width:12px;height:12px;border-radius:3px;border:1px solid}
.legend .sw.d{background:var(--danger-weak);border-color:#f0b8b8}
.legend .sw.c{background:var(--warn-weak);border-color:#f0d8a8}
.legend .sw.n{background:#f8f9fc;border-color:var(--line)}
@media(max-width:900px){.split{flex-direction:column!important}.split .sidebar{width:100%!important;border-right:none!important;border-bottom:1px solid var(--line)!important}}
"""

def header(title: str) -> str:
    return f"""<div class="wash"></div>
<header class="hdr">
  <div class="brand"><svg><use href="#i-logo"/></svg>文档元数据核验</div>
  <span class="sep">/</span><span class="sub-t">{title}</span>
  <span class="ver">v0.1.0</span>
</header>"""

# ═══════════════════════════════════════════════════════════════════
# Layout 1: 驾驶舱模式 (Dashboard command center)
# ═══════════════════════════════════════════════════════════════════
def layout1() -> str:
    # Risk alert cards
    alerts = ""
    for cn, members, desc, fields, tone in [
        ("围标组A",CA,"张明 · 宏达建设集团","作者/修改者/公司","danger"),
        ("围标组B",CB,"李芳 · 正阳工程","作者/修改者/公司","danger"),
        ("待复核组",CC,"通用投标模板V3","模板/创建时间","caution"),
    ]:
        c = "var(--danger)" if tone=="danger" else "var(--warn)"
        ch = "".join(f'<span class="code">{m:02d}</span>' for m in members)
        pc = "due" if tone=="danger" else "today"
        alerts += f"""<div class="card" style="border-left:3px solid {c}"><div class="card-h"><b>{cn}</b><span class="meta">· {len(members)}家</span><span class="right" style="color:{c}">{'疑似围标' if tone=='danger' else '需复核'}</span></div><div class="row"><div class="body"><div class="l1"><span class="name">{desc}</span><span class="pill {pc}">{fields}</span></div><div class="l2" style="margin-top:5px">涉及 {ch}</div></div></div></div>"""

    # Sorted bidder rows
    sbids = sorted(B, key=lambda b:(0 if b["id"] in CA+CB else 1 if b["id"] in CC else 2, b["id"]))
    rows = ""
    for b in sbids:
        bid=b["id"]; l=lvl(bid)
        if l=="ok":
            rows += f'<div class="row" style="opacity:.5"><div class="body"><div class="l1"><span class="name">投标人{bid:02d}</span><span class="pill week">{b["files"]}文件</span></div><div class="l2">{b["author"]} <em>·</em> {b["company"]}</div></div><span class="pill week">无异常</span></div>'
        else:
            cl = "danger" if l=="danger" else "caution"
            cvar = "var(--danger)" if l=="danger" else "var(--warn)"
            cluster = CA if bid in CA else CB if bid in CB else CC
            others = "、".join(f"{x:02d}" for x in cluster if x!=bid)
            rows += f'<div class="row" style="border-left:3px solid {cvar}"><div class="body"><div class="l1"><span class="name">投标人{bid:02d}</span><span class="pill {"due" if l=="danger" else "today"}">重复</span><span class="stage {"s1" if l=="danger" else "s3"}">{"高风险" if l=="danger" else "待复核"}</span></div><div class="l2">{b["author"]} <em>·</em> {b["company"]} <em>·</em> <span style="color:{cvar}">同 投标人{others}</span></div></div><span class="code">{b["files"]}文件</span></div>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>方案1 · 驾驶舱模式</title>
<style>{SHARED_CSS}
.status-bar{{display:flex;align-items:center;gap:12px;height:48px;padding:0 14px;background:#fff;border:1px solid var(--line);border-radius:var(--radius-panel)}}
.status-bar .tag{{font-size:12px;font-weight:700;color:var(--ok);background:#e7f6f0;border-radius:var(--radius-chip);padding:4px 10px;display:flex;align-items:center;gap:5px}}
.status-bar .txt{{font-size:14px}}
.status-bar .txt b{{font-weight:600}}
.status-bar .spacer{{flex:1}}
.status-bar .num{{font-family:var(--mono);font-size:12.5px;color:var(--sub)}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:760px){{.two-col{{grid-template-columns:1fr}}}}
</style></head><body>
{SHARED_HEAD}
{header("方案1 · 驾驶舱模式 · XX市政工程")}
<div class="page"><main style="padding:24px 0 80px">
  <div style="margin-top:16px"><div class="status-bar"><span class="tag"><svg class="ic" style="width:13px;height:13px"><use href="#i-check"/></svg>核验完成</span><span class="txt"><b>30</b> 家投标人 · <b>90</b> 文件 · <b>2,075</b> 条元数据</span><span class="spacer"></span><span class="num">2026-08-06 10:30</span><button class="ghost"><svg class="ic"><use href="#i-download"/></svg>导出报告</button></div></div>

  <div style="margin-top:16px"><div class="kpi-panel"><div class="ph"><svg class="ic" style="color:var(--dark-sub)"><use href="#i-shield"/></svg><b>围标串标风险概览</b><span class="meta">基于文档元数据交叉比对</span></div>
    <div class="kgrid"><div class="k"><div class="lbl">疑似围标</div><div class="val bad">7</div><div class="dlt">2组 · 10处重复</div></div><div class="k"><div class="lbl">待复核</div><div class="val warn">2</div><div class="dlt">1组 · 4处重复</div></div><div class="k"><div class="lbl">未发现异常</div><div class="val ok">21</div><div class="dlt">占 70%</div></div><div class="k"><div class="lbl">投标人总数</div><div class="val">30</div><div class="dlt">90 文件 · PDF/DOCX/XLSX</div></div></div></div></div>

  <div class="sec-h"><svg class="ic" style="color:var(--danger)"><use href="#i-alert"/></svg>检测到的风险线索</div>
  <div class="two-col">{alerts}</div>

  <div class="sec-h"><svg class="ic" style="color:var(--primary)"><use href="#i-users"/></svg>投标人明细（按风险排序）</div>
  <div class="card">{rows}</div>
</main></div></body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Layout 2: 左右分栏模式 (Split: pair list + detail)
# ═══════════════════════════════════════════════════════════════════
def layout2() -> str:
    # Left: risk pairs
    pairs = []
    for cluster in [CA, CB]:
        for i in range(len(cluster)):
            for j in range(i+1, len(cluster)):
                pairs.append((cluster[i],cluster[j],"danger"))
    pairs.append((CC[0],CC[1],"caution"))

    pair_items = ""
    for a,b,tone in pairs:
        c = "var(--danger)" if tone=="danger" else "var(--warn)"
        cls = "s1" if tone=="danger" else "s3"
        pair_items += f'<div style="padding:10px 14px;border-bottom:1px solid var(--line-soft);cursor:pointer;display:flex;align-items:center;gap:8px" onmouseover="this.style.background=\'#fafbfe\'" onmouseout="this.style.background=\'#fff\'"><span class="stage {cls}" style="min-width:50px;text-align:center">{"高风险" if tone=="danger" else "待复核"}</span><div style="flex:1"><div style="font-weight:600;font-size:13px">投标人{a:02d} <span style="color:var(--faint)">vs</span> 投标人{b:02d}</div><div style="font-size:12px;color:var(--sub);margin-top:2px">{"张明/宏达建设集团" if tone=="danger" and a in CA else "李芳/正阳工程" if tone=="danger" else "模板+时间戳一致"}</div></div><span class="code">{"3项" if tone=="danger" else "2项"}</span></div>'

    # Clean bidders
    clean_ids = [b["id"] for b in B if lvl(b["id"])=="ok"]
    clean_chips = "".join(f'<span class="code">{i:02d}</span>' for i in clean_ids)

    # Right: comparison table for pair 01 vs 08
    cmp_rows = ""
    for fn,v1,v2,st in [("作者","张明","张明","m"),("最后修改者","张明","张明","m"),("公司","宏达建设集团","宏达建设集团","m"),("模板","模板01.dotx","模板08.dotx","d"),("创建时间","2026-07-15 09:01","2026-07-22 09:08","d"),("修改时间","2026-07-16 14:01","2026-07-23 14:08","d"),("应用程序","WPS Office","Word 2019","d"),("文件大小","127KB","176KB","d")]:
        tag = '<span class="pill due">重复</span>' if st=="m" else '<span class="pill week">不同</span>'
        cmp_rows += f'<tr><td style="font-weight:600;min-width:80px">{fn}</td><td class="{"code" if st=="d" else ""}" style="{"background:var(--danger-weak);color:var(--danger);font-weight:600" if st=="m" else "color:var(--sub)"}">{v1}</td><td class="{"code" if st=="d" else ""}" style="{"background:var(--danger-weak);color:var(--danger);font-weight:600" if st=="m" else "color:var(--sub)"}">{v2}</td><td>{tag}</td></tr>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>方案2 · 左右分栏模式</title>
<style>{SHARED_CSS}
.split{{display:flex;height:calc(100vh - 56px)}}
.sidebar{{width:320px;border-right:1px solid var(--line);background:#fff;overflow-y:auto;flex-shrink:0}}
.sidebar .sh{{padding:12px 14px;font-weight:700;font-size:14px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px;position:sticky;top:0;background:#fff;z-index:2}}
.sidebar .sh .cnt{{margin-left:auto;font-size:12px;font-weight:600;color:var(--danger);background:var(--danger-weak);border-radius:var(--radius-full);padding:2px 10px}}
.detail{{flex:1;overflow-y:auto;padding:20px 24px}}
.cmp-head{{display:flex;align-items:center;gap:16px;margin-bottom:16px}}
.cmp-b{{flex:1;text-align:center;padding:14px;border:1px solid var(--line);border-radius:var(--radius-card);background:#fff}}
.cmp-b .n{{font-size:20px;font-weight:700;font-family:var(--mono)}}
.cmp-b .c{{font-size:12px;color:var(--sub);margin-top:2px}}
.vs{{font-size:14px;color:var(--faint);font-weight:600}}
.dim-tabs{{display:flex;gap:4px;margin-bottom:12px;border-bottom:1px solid var(--line)}}
.dim-tabs span{{padding:8px 14px;font-size:13px;font-weight:500;color:var(--sub);border-bottom:2px solid transparent;cursor:pointer}}
.dim-tabs span.on{{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}}
.dim-tabs span .b{{font-size:11px;background:var(--danger-weak);color:var(--danger);padding:0 5px;border-radius:8px;margin-left:3px}}
.sec-sep{{padding:8px 14px 4px;font-size:12px;color:var(--faint);font-weight:600}}
</style></head><body>
{SHARED_HEAD}
{header("方案2 · 左右分栏 · XX市政工程")}
<div class="split">
  <div class="sidebar">
    <div class="sh"><svg class="ic" style="color:var(--sub)"><use href="#i-list"/></svg>重复组列表<span class="cnt">{len(pairs)}组</span></div>
    {pair_items}
    <div class="sec-sep">无重复投标人（{len(clean_ids)}家）</div>
    <div style="padding:4px 14px 10px">{clean_chips}</div>
  </div>
  <div class="detail">
    <div style="padding:10px 14px;border-radius:var(--radius-field);background:var(--danger-weak);border-left:3px solid var(--danger);margin-bottom:16px;font-size:13px;color:var(--ink)">检测到 8 组投标人之间存在元数据重复，其中 7 组涉及人员/组织身份一致</div>
    <div class="cmp-head"><div class="cmp-b"><div class="n" style="color:var(--danger)">01</div><div class="c">宏达建设集团</div></div><div class="vs">VS</div><div class="cmp-b"><div class="n" style="color:var(--danger)">08</div><div class="c">宏达建设集团</div></div></div>
    <div class="dim-tabs"><span class="on">文档属性<span class="b">3</span></span><span>创建者信息<span class="b">3</span></span><span>时间戳</span><span>文件信息</span></div>
    <div class="tbl-wrap"><table><thead><tr><th>字段</th><th>投标人01</th><th>投标人08</th><th>结果</th></tr></thead><tbody>{cmp_rows}</tbody></table></div>
    <p style="margin-top:14px;font-size:12.5px;color:var(--faint)">点击左侧列表切换查看不同投标人之间的比对详情</p>
  </div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Layout 3: 矩阵表格模式 (Full-width heatmap matrix)
# ═══════════════════════════════════════════════════════════════════
def layout3() -> str:
    fields = [("author","作者"),("lmb","修改者"),("company","公司"),("template","模板"),("created","创建时间"),("modified","修改时间")]
    matrix_rows = ""
    for fkey,flabel in fields:
        matrix_rows += f'<tr><td class="hm-l">{flabel}</td>'
        for b in B:
            bid=b["id"]; val=b[fkey]
            if len(val)>7: val=val[:6]+"…"
            df = {"author","lmb","company"} if (bid in CA or bid in CB) else set()
            cf = {"template","created"} if bid in CC else set()
            cls = "hm-d" if fkey in df else "hm-c" if fkey in cf else ""
            matrix_rows += f'<td class="{cls}" title="{b[fkey]}">{val}</td>'
        matrix_rows += '</tr>'
    cols = "".join(f'<th>{b["id"]:02d}</th>' for b in B)

    # Flag cards
    flags = ""
    for cn,mem,desc,detail,tone in [("围标组A",CA,"张明 / 宏达建设集团","作者、修改者、公司完全一致","danger"),("围标组B",CB,"李芳 / 正阳工程","作者、修改者、公司完全一致","danger"),("待复核",CC,"通用投标模板V3","模板+创建时间精确到秒一致","caution")]:
        c="var(--danger)" if tone=="danger" else "var(--warn)"; wc="var(--danger-weak)" if tone=="danger" else "var(--warn-weak)"
        ch="".join(f'<span class="code" style="color:{c};background:{wc}">{m:02d}</span>' for m in mem)
        flags += f'<div class="card" style="border-left:3px solid {c}"><div class="card-h"><b>{cn}</b><span class="meta">· {len(mem)}家</span></div><div class="row"><div class="body"><div class="l1"><span class="name">{desc}</span></div><div class="l2" style="margin-top:4px">{detail}</div><div class="l2" style="margin-top:4px">{ch}</div></div></div></div>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>方案3 · 矩阵表格模式</title>
<style>{SHARED_CSS}
.hm-tbl{{border-collapse:collapse;font-size:10.5px;width:100%}}
.hm-tbl th,.hm-tbl td{{border:1px solid var(--line-soft);padding:4px 5px;text-align:center;white-space:nowrap;max-width:52px;overflow:hidden;text-overflow:ellipsis}}
.hm-tbl th{{background:#fcfcfe;font-weight:600;font-family:var(--mono);font-size:10px;color:var(--sub)}}
.hm-l{{background:#f8f9fc;font-weight:600;text-align:right!important;min-width:60px;font-size:11px;position:sticky;left:0;z-index:2}}
.hm-d{{background:var(--danger-weak);color:var(--danger);font-weight:600}}
.hm-c{{background:var(--warn-weak);color:var(--warn);font-weight:600}}
.matrix-wrap{{overflow:auto;border:1px solid var(--line);border-radius:var(--radius-card);background:#fff}}
.two-col{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
@media(max-width:760px){{.two-col{{grid-template-columns:1fr}}}}
</style></head><body>
{SHARED_HEAD}
{header("方案3 · 矩阵表格 · XX市政工程")}
<div class="page"><main style="padding:24px 0 80px">
  <div style="margin-top:16px"><div class="kpi-panel"><div class="ph"><svg class="ic" style="color:var(--dark-sub)"><use href="#i-grid"/></svg><b>元数据交叉比对矩阵</b><span class="meta">30 家投标人 × 6 个关键字段</span></div>
    <div class="kgrid"><div class="k"><div class="lbl">人员/组织重复</div><div class="val bad">10</div><div class="dlt">涉及 7 家投标人</div></div><div class="k"><div class="lbl">模板/时间戳重复</div><div class="val warn">4</div><div class="dlt">涉及 2 家投标人</div></div><div class="k"><div class="lbl">无异常</div><div class="val ok">21</div><div class="dlt">占 70%</div></div><div class="k"><div class="lbl">投标人总数</div><div class="val">30</div><div class="dlt">90 文件</div></div></div></div></div>

  <div class="legend" style="margin-top:20px"><div class="li"><span class="sw d"></span>人员/组织重复</div><div class="li"><span class="sw c"></span>模板/时间戳重复</div><div class="li"><span class="sw n"></span>无异常</div></div>
  <div class="matrix-wrap"><table class="hm-tbl"><thead><tr><th class="hm-l">字段 ＼ 投标人</th>{cols}</tr></thead><tbody>{matrix_rows}</tbody></table></div>

  <div class="sec-h"><svg class="ic" style="color:var(--danger)"><use href="#i-alert"/></svg>风险线索明细</div>
  <div class="two-col">{flags}</div>
</main></div></body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Layout 4: 卡片网格模式 (Risk-sorted card grid)
# ═══════════════════════════════════════════════════════════════════
def layout4() -> str:
    # Danger cards
    danger_cards = ""
    for bid in CA+CB:
        b=B[bid-1]; cluster = CA if bid in CA else CB
        others = "、".join(f"{x:02d}" for x in cluster if x!=bid)
        danger_cards += f'<div style="background:#fff;border:1px solid var(--line);border-left:3px solid var(--danger);border-radius:var(--radius-card);padding:14px 16px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="font-family:var(--mono);font-size:18px;font-weight:700;color:var(--danger)">{bid:02d}</span><span style="font-weight:600;font-size:14px">投标人{bid:02d}</span><span class="stage s1" style="margin-left:auto">高风险</span></div><div style="font-size:12.5px;color:var(--sub);line-height:1.8">作者：<span style="color:var(--danger);font-weight:600">{b["author"]}</span><br>修改者：<span style="color:var(--danger);font-weight:600">{b["lmb"]}</span><br>公司：<span style="color:var(--danger);font-weight:600">{b["company"]}</span></div><div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--line-soft);font-size:12px;color:var(--danger)">同 投标人{others}</div></div>'

    # Caution cards
    caution_cards = ""
    for bid in CC:
        b=B[bid-1]; others="、".join(f"{x:02d}" for x in CC if x!=bid)
        caution_cards += f'<div style="background:#fff;border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:var(--radius-card);padding:14px 16px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="font-family:var(--mono);font-size:18px;font-weight:700;color:var(--warn)">{bid:02d}</span><span style="font-weight:600;font-size:14px">投标人{bid:02d}</span><span class="stage s3" style="margin-left:auto">待复核</span></div><div style="font-size:12.5px;color:var(--sub);line-height:1.8">模板：<span style="color:var(--warn);font-weight:600">{b["template"]}</span><br>创建时间：<span style="color:var(--warn);font-weight:600">{b["created"]}</span></div><div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--line-soft);font-size:12px;color:var(--warn)">同 投标人{others}</div></div>'

    # Clean grid
    clean_ids = [b["id"] for b in B if lvl(b["id"])=="ok"]
    clean_grid = ""
    for bid in clean_ids:
        b=B[bid-1]
        clean_grid += f'<div style="background:#fff;border:1px solid var(--line-soft);border-radius:var(--radius-item);padding:10px 12px;display:flex;align-items:center;gap:8px"><span style="font-family:var(--mono);font-size:13px;font-weight:600;color:var(--faint)">{bid:02d}</span><span style="font-size:12.5px;color:var(--sub);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{b["author"]}</span></div>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>方案4 · 卡片网格模式</title>
<style>{SHARED_CSS}
.grid-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}}
.grid-clean{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:6px}}
.sec-label{{font-size:13px;font-weight:600;color:var(--sub);margin:20px 0 10px;display:flex;align-items:center;gap:8px}}
.sec-label .cnt{{font-size:12px;font-weight:600;padding:1px 8px;border-radius:var(--radius-full)}}
</style></head><body>
{SHARED_HEAD}
{header("方案4 · 卡片网格 · XX市政工程")}
<div class="page"><main style="padding:24px 0 80px">
  <div style="margin-top:16px"><div class="kpi-panel"><div class="ph"><svg class="ic" style="color:var(--dark-sub)"><use href="#i-users"/></svg><b>投标人风险分布</b><span class="meta">30 家投标人 · 按风险等级分组展示</span></div>
    <div class="kgrid"><div class="k"><div class="lbl">高风险（人员/组织重复）</div><div class="val bad">7</div><div class="dlt">2 个围标组</div></div><div class="k"><div class="lbl">待复核（模板/时间戳）</div><div class="val warn">2</div><div class="dlt">1 个疑似组</div></div><div class="k"><div class="lbl">未发现异常</div><div class="val ok">21</div><div class="dlt">占 70%</div></div><div class="k"><div class="lbl">投标人总数</div><div class="val">30</div><div class="dlt">90 个文件</div></div></div></div></div>

  <div class="sec-label"><svg class="ic" style="color:var(--danger);width:14px;height:14px"><use href="#i-alert"/></svg>高风险投标人<span class="cnt" style="color:var(--danger);background:var(--danger-weak)">7家</span></div>
  <div class="grid-cards">{danger_cards}</div>

  <div class="sec-label"><svg class="ic" style="color:var(--warn);width:14px;height:14px"><use href="#i-clock"/></svg>待复核投标人<span class="cnt" style="color:var(--warn);background:var(--warn-weak)">2家</span></div>
  <div class="grid-cards">{caution_cards}</div>

  <div class="sec-label"><svg class="ic" style="color:var(--ok);width:14px;height:14px"><use href="#i-check"/></svg>未发现异常<span class="cnt" style="color:var(--sub);background:var(--line-soft)">{len(clean_ids)}家</span></div>
  <div class="grid-clean">{clean_grid}</div>
</main></div></body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Layout 5: 关系图谱模式 (Network graph + investigation panel)
# ═══════════════════════════════════════════════════════════════════
def layout5() -> str:
    nodes = []; edges = []
    clusters = {"CA":{"center":(280,280),"ids":CA,"color":"#c93438","fill":"#fdeeee","label":"围标组A"},
                "CB":{"center":(580,250),"ids":CB,"color":"#c93438","fill":"#fdeeee","label":"围标组B"},
                "CC":{"center":(430,120),"ids":CC,"color":"#a85c00","fill":"#fdf3e4","label":"待复核"}}
    for key,info in clusters.items():
        cx,cy = info["center"]
        for j,bid in enumerate(info["ids"]):
            ang = j*2*math.pi/len(info["ids"])-math.pi/2
            x = cx+60*math.cos(ang); y = cy+60*math.sin(ang)
            nodes.append((bid,x,y,info["color"],info["fill"],20))
            for k in range(j+1,len(info["ids"])):
                edges.append((info["ids"][j],info["ids"][k],info["color"],"2.5" if key!="CC" else "2","0.4"))
    clean_ids = [b["id"] for b in B if lvl(b["id"])=="ok"]
    for j,bid in enumerate(clean_ids):
        col=j%9; row=j//9; x=80+col*72; y=430+row*52
        nodes.append((bid,x,y,"#cbd5e1","#f8fafc",11))
    nm = {n[0]:n for n in nodes}
    es = "".join(f'<line x1="{nm[a][1]}" y1="{nm[a][2]}" x2="{nm[b][1]}" y2="{nm[b][2]}" stroke="{c}" stroke-width="{w}" opacity="{o}"/>' for a,b,c,w,o in edges)
    ns = ""
    for bid,x,y,c,f,r in nodes:
        fs = 10 if r>15 else 9; fw = "700" if r>15 else "500"
        ns += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{f}" stroke="{c}" stroke-width="2"/><text x="{x}" y="{y+3.5}" text-anchor="middle" font-size="{fs}" font-weight="{fw}" fill="{c}" font-family="ui-monospace,monospace">{bid:02d}</text>'
    cl = ""
    for key,info in clusters.items():
        cx,cy = info["center"]; c = info["color"]
        cl += f'<text x="{cx}" y="{cy-80}" text-anchor="middle" font-size="12" font-weight="700" fill="{c}">{info["label"]}（{len(info["ids"])}家）</text>'

    # Investigation panel cards
    inv = ""
    for cn,mem,desc,detail,tone in [("围标组A",CA,"张明 · 宏达建设集团","作者/修改者/公司 3项完全一致","danger"),("围标组B",CB,"李芳 · 正阳工程","作者/修改者/公司 3项完全一致","danger"),("待复核组",CC,"通用投标模板V3","模板+创建时间精确到秒一致","caution")]:
        c="var(--danger)" if tone=="danger" else "var(--warn)"; wc="var(--danger-weak)" if tone=="danger" else "var(--warn-weak)"
        ch="".join(f'<span class="code" style="color:{c};background:{wc}">{m:02d}</span>' for m in mem)
        verdict = "疑似围标串标" if tone=="danger" else "需人工复核"
        inv += f'<div class="card" style="border-left:3px solid {c}"><div class="card-h"><b>{cn}</b><span class="meta">{len(mem)}家</span></div><div style="padding:12px 16px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">{desc}</div><div style="font-size:12.5px;color:var(--sub);line-height:1.6">{detail}</div><div style="margin-top:6px">{ch}</div><div style="margin-top:6px;font-size:12px;font-weight:700;color:{c}">判定：{verdict}</div></div></div>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>方案5 · 关系图谱模式</title>
<style>{SHARED_CSS}
.graph-area{{background:#fff;border:1px solid var(--line);border-radius:var(--radius-card);overflow:hidden;position:relative}}
.graph-area svg{{display:block;width:100%}}
.graph-info{{position:absolute;top:12px;left:12px;background:rgba(255,255,255,.95);padding:10px 14px;border-radius:var(--radius-item);border:1px solid var(--line);font-size:11.5px;line-height:1.8;max-width:220px}}
.graph-info b{{font-size:12.5px}}
.two-col{{display:grid;grid-template-columns:1fr 300px;gap:16px;align-items:start}}
@media(max-width:900px){{.two-col{{grid-template-columns:1fr}}}}
</style></head><body>
{SHARED_HEAD}
{header("方案5 · 关系图谱 · XX市政工程")}
<div class="page"><main style="padding:24px 0 80px">
  <div style="margin-top:16px"><div class="kpi-panel"><div class="ph"><svg class="ic" style="color:var(--dark-sub)"><use href="#i-shield"/></svg><b>围标关系网络</b><span class="meta">共享元数据的投标人自动聚簇</span></div>
    <div class="kgrid"><div class="k"><div class="lbl">围标组数</div><div class="val bad">2</div><div class="dlt">7家投标人</div></div><div class="k"><div class="lbl">待复核组</div><div class="val warn">1</div><div class="dlt">2家投标人</div></div><div class="k"><div class="lbl">无关联</div><div class="val ok">21</div><div class="dlt">占 70%</div></div><div class="k"><div class="lbl">投标人总数</div><div class="val">30</div><div class="dlt">90 文件</div></div></div></div></div>

  <div class="two-col" style="margin-top:20px">
    <div>
      <div class="graph-area">
        <div class="graph-info"><b>关系网络说明</b><br>红色连线 = 人员/组织重复<br>橙色连线 = 模板/时间戳重复<br>灰色节点 = 未发现关联<br>自动聚类的围标组一目了然</div>
        <svg viewBox="0 0 720 580">{es}{cl}{ns}</svg>
      </div>
    </div>
    <div>
      <div class="sec-h" style="margin-top:0"><svg class="ic" style="color:var(--sub)"><use href="#i-search"/></svg>调查面板</div>
      {inv}
    </div>
  </div>
</main></div></body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    layouts = [
        ("方案1-驾驶舱模式.html", layout1, "KPI深色面板 + 风险线索卡片 + 按风险排序的投标人列表"),
        ("方案2-左右分栏模式.html", layout2, "左侧重复组列表 + 右侧逐字段对比表（法正智能风格）"),
        ("方案3-矩阵表格模式.html", layout3, "30投标人×6字段热力矩阵 + 风险线索卡片"),
        ("方案4-卡片网格模式.html", layout4, "按风险分组的卡片网格，高风险/待复核/正常三区"),
        ("方案5-关系图谱模式.html", layout5, "SVG关系网络图 + 右侧调查面板（Linkurious风格）"),
    ]
    for fn, func, desc in layouts:
        path = OUTPUT / fn
        path.write_text(func(), encoding="utf-8")
        print(f"  ✅ {fn}")
        print(f"     {desc}")
    print(f"\n📂 {OUTPUT}")


if __name__ == "__main__":
    main()

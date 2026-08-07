"""
Generate 10 distinct UI layout designs for the document-metadata-inspector desktop app.
Each layout is a different visual/structural approach to the SAME business data:
  - Select bid folder → scan → view cross-bidder metadata comparison results
  - Detect person/org identity overlaps (danger) and template/timestamp overlaps (caution)
Follows: 人机协同数智业务底座 设计规范 v1.1
Output: ~/Desktop/文档元数据核验-10套页面/
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "文档元数据核验-10套页面"

# ═══════════════════════════════════════════════════════════════════
# Mock data (matches real ScanResult / DocumentSummary / TraceSummary)
# ═══════════════════════════════════════════════════════════════════
BIDDERS = [
    {"id":"A","name":"中铁建工集团有限公司","letter":"A","docs":[
        {"name":"商务标.pdf","fmt":"pdf","author":"张明","lmb":"张明","company":"宏达建设集团","template":"—","created":"2026-07-15 09:30","modified":"2026-07-16 14:20","size":"1.2 MB","sha":"a3f8…c1d2"},
        {"name":"技术标.docx","fmt":"word","author":"张明","lmb":"张明","company":"宏达建设集团","template":"通用投标模板V3.dotx","created":"2026-07-15 09:30","modified":"2026-07-16 14:20","size":"890 KB","sha":"b7e2…9f4a"},
        {"name":"报价标.xlsx","fmt":"excel","author":"张明","lmb":"刘洋","company":"宏达建设集团","template":"—","created":"2026-07-15 10:15","modified":"2026-07-16 15:00","size":"340 KB","sha":"c1d4…2e8b"},
    ]},
    {"id":"B","name":"华西建设股份有限公司","letter":"B","docs":[
        {"name":"商务标.pdf","fmt":"pdf","author":"李伟","lmb":"王芳","company":"华西建设","template":"—","created":"2026-07-12 10:00","modified":"2026-07-14 16:45","size":"1.1 MB","sha":"d5a1…7c3f"},
        {"name":"技术标.docx","fmt":"word","author":"李伟","lmb":"王芳","company":"华西建设","template":"—","created":"2026-07-12 10:30","modified":"2026-07-14 17:00","size":"920 KB","sha":"e8b3…1d6c"},
        {"name":"报价标.xlsx","fmt":"excel","author":"李伟","lmb":"王芳","company":"华西建设","template":"—","created":"2026-07-12 11:00","modified":"2026-07-14 17:30","size":"310 KB","sha":"f2c7…4a9e"},
    ]},
    {"id":"C","name":"宏达建设集团有限公司","letter":"C","docs":[
        {"name":"商务标.pdf","fmt":"pdf","author":"张明","lmb":"张明","company":"宏达建设集团","template":"—","created":"2026-07-15 09:30","modified":"2026-07-16 14:20","size":"1.3 MB","sha":"a3f8…d7e1"},
        {"name":"技术标.docx","fmt":"word","author":"张明","lmb":"张明","company":"宏达建设集团","template":"通用投标模板V3.dotx","created":"2026-07-15 09:30","modified":"2026-07-16 14:20","size":"880 KB","sha":"b7e2…0f3c"},
        {"name":"报价标.xlsx","fmt":"excel","author":"张明","lmb":"刘洋","company":"宏达建设集团","template":"—","created":"2026-07-15 10:15","modified":"2026-07-16 15:00","size":"350 KB","sha":"g4d9…8b1f"},
    ]},
    {"id":"D","name":"正阳工程有限公司","letter":"D","docs":[
        {"name":"商务标.pdf","fmt":"pdf","author":"张明","lmb":"刘洋","company":"正阳工程","template":"—","created":"2026-07-15 09:30","modified":"2026-07-17 11:00","size":"1.2 MB","sha":"h6e2…3f5a"},
        {"name":"技术标.docx","fmt":"word","author":"张明","lmb":"刘洋","company":"正阳工程","template":"通用投标模板V3.dotx","created":"2026-07-15 09:30","modified":"2026-07-17 11:00","size":"910 KB","sha":"i8f4…7b2d"},
        {"name":"报价标.xlsx","fmt":"excel","author":"张明","lmb":"刘洋","company":"正阳工程","template":"—","created":"2026-07-15 10:15","modified":"2026-07-17 11:30","size":"320 KB","sha":"j2a6…9c4e"},
    ]},
    {"id":"E","name":"新兴建设开发总公司","letter":"E","docs":[
        {"name":"商务标.pdf","fmt":"pdf","author":"赵强","lmb":"赵强","company":"新兴建设","template":"—","created":"2026-07-13 08:00","modified":"2026-07-15 10:30","size":"1.0 MB","sha":"k4b8…1d7f"},
        {"name":"技术标.docx","fmt":"word","author":"赵强","lmb":"赵强","company":"新兴建设","template":"—","created":"2026-07-13 08:30","modified":"2026-07-15 11:00","size":"850 KB","sha":"l6c2…5e3a"},
        {"name":"报价标.xlsx","fmt":"excel","author":"赵强","lmb":"赵强","company":"新兴建设","template":"—","created":"2026-07-13 09:00","modified":"2026-07-15 11:30","size":"300 KB","sha":"m8d4…8f1c"},
    ]},
]

# Traces: person (danger) and caution
TRACES_PERSON = [
    {"id":"t1","field":"作者","value":"张明","bidders":["A","C","D"],"color":"#dc2626"},
    {"id":"t2","field":"最后修改者","value":"张明","bidders":["A","C"],"color":"#7c3aed"},
    {"id":"t3","field":"公司","value":"宏达建设集团","bidders":["A","C"],"color":"#0891b2"},
]
TRACES_CAUTION = [
    {"id":"t4","field":"模板","value":"通用投标模板V3.dotx","bidders":["A","C","D"],"color":"#d97706"},
    {"id":"t5","field":"创建时间","value":"2026-07-15 09:30","bidders":["A","C","D"],"color":"#be123c"},
]

ALL_TRACES = TRACES_PERSON + TRACES_CAUTION

DANGER_BIDS = {"A","C","D"}
OK_BIDS = {"B","E"}

FMT_ICON = {"pdf":"📄","word":"📝","excel":"📊"}
FMT_BADGE = {"pdf":("pdf","PDF"),"word":("word","DOCX"),"excel":("excel","XLSX")}

# ═══════════════════════════════════════════════════════════════════
# Shared CSS + components
# ═══════════════════════════════════════════════════════════════════
CSS = """
:root{
  --primary:#034ed6;--primary-hover:#0342b8;--primary-weak:#eaf1fe;--primary-weak-2:#f4f8ff;
  --primary-line-hover:#bcd0f5;--primary-a07:rgba(3,78,214,.07);--primary-a09:rgba(3,78,214,.085);
  --primary-a10:rgba(3,78,214,.10);
  --ink:#141928;--sub:#5d6579;--faint:#6b7489;
  --line:#e8eaf0;--line-soft:#f0f2f7;
  --dark:#0e1226;--dark-2:#131834;--dark-line:rgba(125,145,205,.16);--dark-ink:#e9edfa;--dark-sub:#8b98bd;
  --ok:#15803d;--ok-weak:#e7f6f0;--warn:#a85c00;--warn-weak:#fdf3e4;
  --danger:#c93438;--danger-weak:#fdeeee;
  --teal:#0f766e;--violet:#7c3aed;--cyan:#1fb2de;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --r-chip:7px;--r-item:8px;--r-btn:9px;--r-field:10px;--r-panel:12px;--r-card:13px;--r-dk:14px;--r-full:999px;
  --sh-panel:0 12px 32px rgba(14,18,38,.18);--sh-float:0 4px 14px rgba(20,25,40,.10);--sh-pop:0 6px 20px rgba(20,25,40,.12);
  --wash-warm:rgba(124,58,237,.055);--wash-cool:rgba(31,178,222,.075);
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,-apple-system,"Segoe UI",sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:var(--sans);background:#fff;color:var(--ink);font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased;overflow:hidden}
.ic{width:16px;height:16px;flex:none}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px;border-radius:4px}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.wash{position:absolute;top:0;left:0;right:0;height:480px;pointer-events:none;z-index:0;
  background:radial-gradient(720px 340px at 14% -12%,var(--primary-a09),transparent 66%),
  radial-gradient(860px 380px at 52% -16%,var(--wash-warm),transparent 64%),
  radial-gradient(640px 320px at 88% -10%,var(--wash-cool),transparent 66%)}
.wash::after{content:"";position:absolute;inset:auto 0 0 0;height:180px;background:linear-gradient(180deg,rgba(255,255,255,0),#fff)}
/* topbar */
.topbar{display:flex;align-items:center;gap:12px;height:48px;padding:0 16px;background:rgba(255,255,255,.82);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line-soft);flex-shrink:0;z-index:40}
.topbar__logo{display:grid;width:26px;height:26px;place-items:center;border-radius:var(--r-chip);background:var(--primary)}
.topbar__logo svg{width:16px;height:16px}
.topbar__title{font-size:13.5px;font-weight:600;white-space:nowrap}
.topbar__sep{width:1px;height:20px;background:var(--line)}
.topbar__folder{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--sub)}
.topbar__folder-name{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.topbar__spacer{flex:1}
.topbar__btns{display:flex;gap:6px}
.topbar__status{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--sub)}
.topbar__dot{width:6px;height:6px;border-radius:50%;background:var(--ok)}
/* buttons */
.btn{height:30px;padding:0 12px;border:1px solid var(--line);border-radius:var(--r-item);background:#fff;color:var(--ink);
  font-size:12.5px;font-weight:500;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:5px;transition:border-color .15s,background .15s}
.btn:hover{background:var(--line-soft);border-color:#c9d2e3}
.btn--primary{background:var(--primary);border-color:var(--primary);color:#fff}
.btn--primary:hover{background:var(--primary-hover)}
.btn--danger{background:var(--danger-weak);border-color:#f0b8b8;color:var(--danger)}
.btn--sm{height:26px;font-size:11.5px;padding:0 10px}
/* statusbar */
.statusbar{display:flex;align-items:center;gap:14px;height:26px;padding:0 16px;background:#fff;border-top:1px solid var(--line);font-size:11px;color:var(--sub);flex-shrink:0}
.statusbar__alert{color:var(--danger);font-weight:600}
.statusbar__caution{color:var(--warn);font-weight:600}
.statusbar__spacer{flex:1}
/* scroll */
.scroll-area{flex:1;overflow-y:auto;overflow-x:hidden}
/* common */
.card{background:#fff;border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden}
.card-h{display:flex;align-items:center;gap:9px;padding:13px 16px;border-bottom:1px solid var(--line-soft)}
.card-h b{font-size:14px;font-weight:600}
.card-h .meta{font-size:12px;color:var(--faint)}
.pill{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;border-radius:var(--r-full);padding:2px 9px;white-space:nowrap}
.pill--danger{color:var(--danger);background:var(--danger-weak)}
.pill--warn{color:var(--warn);background:var(--warn-weak)}
.pill--ok{color:var(--ok);background:var(--ok-weak)}
.pill--info{color:var(--primary);background:var(--primary-weak)}
.pill--neutral{color:var(--sub);background:var(--line-soft)}
.fmt-badge{display:inline-flex;align-items:center;height:17px;padding:0 5px;border-radius:4px;font-family:var(--mono);font-size:9px;font-weight:700}
.fmt-badge.pdf{background:var(--danger-weak);color:#b91c1c}
.fmt-badge.word{background:var(--primary-weak);color:var(--primary-hover)}
.fmt-badge.excel{background:var(--ok-weak);color:#15803d}
.code{font-family:var(--mono);font-size:11.5px;color:var(--sub);background:var(--line-soft);border-radius:5px;padding:1px 6px}
.match-dot{display:inline-grid;width:18px;height:18px;place-items:center;border-radius:50%;color:#fff;font-size:10px;font-weight:700;flex-shrink:0}
/* dark KPI */
.dk-panel{background:var(--dark);border-radius:var(--r-dk);overflow:hidden;box-shadow:var(--sh-panel)}
.dk-panel__h{display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--dark-2);border-bottom:1px solid var(--dark-line)}
.dk-panel__h b{font-size:13px;font-weight:600;color:var(--dark-ink)}
.dk-panel__h .meta{margin-left:auto;font-size:11px;color:var(--dark-sub)}
.dk-grid{display:grid}
.dk-grid .dk-k{padding:14px 16px;position:relative}
.dk-grid .dk-k+.dk-k::before{content:"";position:absolute;left:0;top:12px;bottom:12px;width:1px;background:var(--dark-line)}
.dk-grid .dk-k .lbl{font-size:11px;color:var(--dark-sub)}
.dk-grid .dk-k .val{margin-top:3px;font-family:var(--mono);font-size:24px;font-weight:700;line-height:1.2;color:#fff}
.dk-grid .dk-k .val.bad{color:#ff8a8f}
.dk-grid .dk-k .val.warn{color:#ffc46b}
.dk-grid .dk-k .val.ok{color:#5fd6a2}
.dk-grid .dk-k .dlt{font-size:11px;color:var(--dark-sub);margin-top:1px}
/* collision banner */
.col-banner{display:flex;align-items:center;gap:8px;padding:10px 14px;border-radius:var(--r-chip);font-size:13px;font-weight:600;flex-wrap:wrap}
.col-banner--danger{background:var(--danger-weak);border:1px solid #f0b8b8;color:var(--danger)}
.col-banner--warn{background:var(--warn-weak);border:1px solid #f0d8a8;color:var(--warn)}
.col-banner--ok{background:var(--ok-weak);border:1px solid #a8d8c0;color:var(--ok)}
.col-chips{display:flex;flex-wrap:wrap;gap:5px;width:100%;margin-top:3px}
.col-chip{display:inline-flex;align-items:center;gap:5px;padding:3px 8px 3px 4px;border:1px solid var(--line);border-left:3px solid var(--tag-color,var(--danger));border-radius:5px;background:#fff;font-weight:400}
"""

def svg_logo():
    return '<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="2.5" width="11" height="14" rx="1.5" fill="#fff" opacity="0.9"/><circle cx="14.5" cy="14.5" r="5.5" stroke="#fff" stroke-width="1.8"/><line x1="18.5" y1="18.5" x2="21.5" y2="21.5" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>'

def topbar(folder="4-投标文件"):
    return f"""<div class="topbar">
  <span class="topbar__logo">{svg_logo()}</span>
  <span class="topbar__title">文档元数据核验</span>
  <span class="topbar__sep"></span>
  <span class="topbar__folder">📁 <span class="topbar__folder-name">{folder}</span></span>
  <span class="topbar__spacer"></span>
  <div class="topbar__btns">
    <button class="btn btn--sm">选择目录</button>
    <button class="btn btn--sm btn--primary">重新核验</button>
  </div>
  <span class="topbar__sep"></span>
  <span class="topbar__status"><span class="topbar__dot"></span>离线</span>
</div>"""

def statusbar():
    return """<div class="statusbar">
  <span>5 投标人</span><span>15 文件</span><span>2,075 条元数据</span>
  <span class="statusbar__alert">3 条人员重复</span>
  <span class="statusbar__caution">2 条待复核</span>
  <span class="statusbar__spacer"></span>
  <span>14.2 MB</span>
</div>"""

def shell(title, inner_css, content, use_wash=True):
    wash = '<div class="wash"></div>' if use_wash else ''
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}
{inner_css}
</style></head><body>
{wash}
<div style="display:flex;flex-direction:column;height:100vh">
{topbar()}
<div class="scroll-area" style="position:relative;z-index:1">
{content}
</div>
{statusbar()}
</div>
</body></html>"""

# ═══════════════════════════════════════════════════════════════════
# Layout 1: 驾驶舱模式 — Dark KPI + risk group cards + bidder list
# ═══════════════════════════════════════════════════════════════════
def layout1():
    css = """
.l1-wrap{max-width:1200px;margin:0 auto;padding:16px}
.l1-gap{margin-bottom:12px}
.col-banner.l1-banner{margin-bottom:12px}
"""
    # KPI panel
    kpi = f"""<div class="dk-panel l1-gap">
  <div class="dk-panel__h">📊 <b>核验概览</b><span class="meta">基于三条独立解析链</span></div>
  <div class="dk-grid" style="grid-template-columns:repeat(5,1fr)">
    <div class="dk-k"><div class="lbl">投标人</div><div class="val">5</div></div>
    <div class="dk-k"><div class="lbl">提取完成</div><div class="val ok">15/15</div></div>
    <div class="dk-k"><div class="lbl">人员重复</div><div class="val bad">3</div><div class="dlt">作者/修改者/公司</div></div>
    <div class="dk-k"><div class="lbl">待复核</div><div class="val warn">2</div><div class="dlt">模板/时间戳</div></div>
    <div class="dk-k"><div class="lbl">无异常</div><div class="val ok">2</div><div class="dlt">B · E</div></div>
  </div>
</div>"""

    # Risk group card
    risk_card = f"""<div class="card l1-gap" style="border-left:3px solid var(--danger)">
  <div class="card-h"><span class="pill pill--danger">高风险</span><b>疑似围标组</b><span class="meta">· 投标人 A、C、D</span></div>
  <div style="padding:14px 16px">
    <p style="font-size:13.5px">三家投标人的文档作者均为<b style="color:var(--danger)">「张明」</b>，使用同一模板<b style="color:var(--danger)">「通用投标模板V3.dotx」</b>，创建时间均为<b class="num" style="color:var(--danger)">2026-07-15 09:30</b>。</p>
    <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap">"""
    for t in ALL_TRACES:
        risk_card += f"""<span class="col-chip" style="--tag-color:{t['color']}">
        <span class="match-dot" style="background:{t['color']};width:14px;height:14px;font-size:8px">!</span>
        <span style="font-size:11px;font-weight:600;color:var(--sub)">{t['field']}</span>
        <span class="num" style="font-size:11px;font-weight:600">{t['value']}</span>
        <span style="font-size:10px;color:var(--faint)">{'·'.join(t['bidders'])}</span></span>"""
    risk_card += """</div></div></div>"""

    # Bidder list
    rows = ""
    for b in BIDDERS:
        is_danger = b["id"] in DANGER_BIDS
        bg = ' style="border-left:3px solid var(--danger)"' if is_danger else ""
        cls = 'pill pill--danger' if is_danger else 'pill pill--ok'
        lbl = "高风险" if is_danger else "无异常"
        linked = "、".join([x for x in DANGER_BIDS if x != b["id"]]) if is_danger else "—"
        link_html = f'<span style="font-size:12px;color:var(--danger)">同 {linked}</span>' if is_danger else ""
        rows += f"""<div{bg} style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line-soft)">
  <span style="display:grid;width:28px;height:28px;place-items:center;border-radius:var(--r-item);background:{'var(--danger-weak)' if is_danger else 'var(--line-soft)'};color:{'var(--danger)' if is_danger else 'var(--sub)'};font-weight:700;font-size:13px">{b['letter']}</span>
  <div style="flex:1;min-width:0">
    <div style="font-size:13.5px;font-weight:600">{b['name']}</div>
    <div style="font-size:12px;color:var(--sub)">作者：{b['docs'][0]['author']} · {len(b['docs'])} 文件</div>
  </div>
  {link_html}
  <span class="{cls}">{lbl}</span>
  <span class="code">{len(b['docs'])}文件</span>
</div>"""

    bidder_list = f"""<div class="card l1-gap"><div class="card-h">📋 <b>投标人清单</b><span class="meta">按风险排序</span></div>{rows}</div>"""

    content = f"""<div class="l1-wrap">{kpi}{risk_card}<div class="col-banner col-banner--danger">⚠ 发现 3 处人员/组织身份重复 — 疑似围标串标</div>{bidder_list}</div>"""
    return shell("方案1 · 驾驶舱模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 2: 数据表模式 — Full audit table, bidders as columns
# ═══════════════════════════════════════════════════════════════════
def layout2():
    css = """.l2-wrap{max-width:1400px;margin:0 auto;padding:16px}"""
    # Build table: rows = metadata fields, columns = bidders
    fields = [
        ("作者", "author", True),
        ("最后修改者", "lmb", True),
        ("公司", "company", True),
        ("模板", "template", False),
        ("创建时间", "created", False),
        ("修改时间", "modified", False),
    ]
    header = '<tr><th style="width:120px">元数据字段</th>'
    for b in BIDDERS:
        danger = b["id"] in DANGER_BIDS
        bg = ' style="background:var(--danger-weak)"' if danger else ""
        header += f'<th{bg}><div style="display:flex;align-items:center;gap:4px;justify-content:center"><span class="match-dot" style="background:{"var(--danger)" if danger else "var(--line)"};width:16px;height:16px;font-size:9px">{b["letter"]}</span>{b["name"][:6]}</div></th>'
    header += '</tr>'

    body_rows = ""
    for label, field, is_person in fields:
        row_bg = ' style="background:var(--danger-weak)"' if is_person else ""
        body_rows += f'<tr><td{row_bg} style="font-weight:600;font-size:12px">{label}</td>'
        for b in BIDDERS:
            val = b["docs"][0][field]
            # Check if this field matches across danger bidders
            highlight = is_person and b["id"] in DANGER_BIDS and val != "—"
            cls = ' style="color:var(--danger);font-weight:600;background:var(--danger-weak)"' if highlight else ""
            body_rows += f'<td{cls} class="num">{val}</td>'
        body_rows += '</tr>'

    content = f"""<div class="l2-wrap">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <div><h2 style="font-size:18px">元数据交叉对比表</h2><p style="font-size:13px;color:var(--sub);margin-top:2px">红色 = 跨投标人重合的人员痕迹（同组内重复不标记）</p></div>
    <div style="display:flex;gap:6px"><button class="btn btn--sm">导出</button><button class="btn btn--sm">展开文件</button></div>
  </div>
  <div class="col-banner col-banner--danger" style="margin-bottom:12px">⚠ 发现 3 处人员/组织身份重复 — 投标人 A、C、D 的作者、修改者完全一致</div>
  <div class="card"><div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12.5px">
    <thead>{header}</thead>
    <tbody>{body_rows}</tbody>
  </table></div></div>
  <div style="margin-top:14px;padding:14px;background:var(--primary-weak-2);border:1px solid var(--line);border-radius:var(--r-card);font-size:12.5px;color:var(--sub)">
    💡 <b>解读：</b>投标人 A、C、D 的「作者」「最后修改者」「公司」字段完全一致，且使用了同一文档模板和创建时间。三链解析（原生/Tika/ExifTool）均独立确认。
  </div>
</div>"""
    return shell("方案2 · 数据表模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 3: 卡片网格模式 — Each bidder as a rich card
# ═══════════════════════════════════════════════════════════════════
def layout3():
    css = """.l3-wrap{max-width:1200px;margin:0 auto;padding:16px}
.l3-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.l3-card{border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden;transition:box-shadow .15s}
.l3-card:hover{box-shadow:var(--sh-float)}
.l3-card--danger{border-left:3px solid var(--danger)}
.l3-card__h{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--line-soft)}
.l3-card__letter{display:grid;width:32px;height:32px;place-items:center;border-radius:var(--r-item);font-weight:700;font-size:14px;flex-shrink:0}
.l3-card__name{font-size:13.5px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.l3-card__body{padding:12px 16px}
.l3-kv{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.l3-kv .item{padding:8px 10px;border:1px solid var(--line-soft);border-radius:var(--r-item)}
.l3-kv .item.danger{border-color:#f0b8b8;background:var(--danger-weak)}
.l3-kv .lbl{font-size:10.5px;color:var(--faint)}
.l3-kv .val{font-family:var(--mono);font-size:11.5px;font-weight:500;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.l3-kv .val.danger{color:var(--danger);font-weight:600}
.l3-files{display:flex;gap:5px;margin-top:10px;flex-wrap:wrap}"""
    cards = ""
    for b in BIDDERS:
        is_danger = b["id"] in DANGER_BIDS
        card_cls = "l3-card l3-card--danger" if is_danger else "l3-card"
        letter_bg = f"background:var(--danger);color:#fff" if is_danger else f"background:var(--line-soft);color:var(--sub)"
        pill_cls = "pill pill--danger" if is_danger else "pill pill--ok"
        pill_lbl = f'{len([t for t in ALL_TRACES if b["id"] in t["bidders"]])} 处重合' if is_danger else "无异常"
        # Key fields
        kv_items = ""
        for label, field in [("作者","author"),("修改者","lmb"),("公司","company"),("模板","template")]:
            val = b["docs"][0][field]
            d = is_danger and b["id"] in DANGER_BIDS and field in ("author","lmb","company")
            kv_items += f'<div class="item{" danger" if d else ""}"><div class="lbl">{label}</div><div class="val{" danger" if d else ""}">{val}</div></div>'
        # File badges
        files = ""
        for d in b["docs"]:
            files += f'<span class="code">{d["name"]}</span>'
        cards += f"""<div class="{card_cls}">
  <div class="l3-card__h">
    <span class="l3-card__letter" style="{letter_bg}">{b['letter']}</span>
    <span class="l3-card__name">{b['name']}</span>
    <span class="{pill_cls}">{pill_lbl}</span>
  </div>
  <div class="l3-card__body">
    <div class="l3-kv">{kv_items}</div>
    <div class="l3-files">{files}</div>
  </div>
</div>"""

    content = f"""<div class="l3-wrap">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <h2 style="font-size:18px">投标人概览</h2>
    <span style="font-size:12px;color:var(--sub)">点击卡片查看完整元数据</span>
  </div>
  <div class="l3-grid">{cards}</div>
</div>"""
    return shell("方案3 · 卡片网格模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 4: 左右分栏 — Left bidder list, right detail panel
# ═══════════════════════════════════════════════════════════════════
def layout4():
    css = """.l4-split{display:flex;height:100%}
.l4-left{width:260px;flex:none;border-right:1px solid var(--line);overflow-y:auto;padding:12px 0}
.l4-right{flex:1;overflow-y:auto;padding:16px}
.l4-item{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;transition:background .15s}
.l4-item:hover{background:var(--line-soft)}
.l4-item--active{background:var(--primary-weak-2);border-left:3px solid var(--primary)}
.l4-item--danger{border-left:3px solid var(--danger)}
.l4-letter{display:grid;width:28px;height:28px;place-items:center;border-radius:var(--r-item);font-weight:700;font-size:13px;flex-shrink:0}
.l4-kv{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--r-item);overflow:hidden;margin-bottom:12px}
.l4-kv .cell{padding:10px 12px;background:#fff}
.l4-kv .cell.danger{background:var(--danger-weak)}
.l4-kv .cell .lbl{font-size:10px;color:var(--faint)}
.l4-kv .cell .val{font-family:var(--mono);font-size:12px;font-weight:500;margin-top:2px}
.l4-kv .cell.danger .val{color:var(--danger);font-weight:600}
.doc-row{display:flex;align-items:center;gap:10px;padding:10px 14px;border:1px solid var(--line);border-radius:var(--r-item);margin-bottom:6px}"""
    # Left list
    left_items = ""
    for b in BIDDERS:
        is_danger = b["id"] in DANGER_BIDS
        active = b["id"] == "A"
        cls = "l4-item"
        cls += " l4-item--active" if active else ""
        cls += " l4-item--danger" if (is_danger and not active) else ""
        bg = "background:var(--danger);color:#fff" if is_danger else "background:var(--line-soft);color:var(--sub)"
        pill_cls = "pill pill--danger" if is_danger else "pill pill--ok"
        pill_lbl = "高风险" if is_danger else "无异常"
        left_items += f"""<div class="{cls}">
  <span class="l4-letter" style="{bg}">{b['letter']}</span>
  <div style="flex:1;min-width:0">
    <div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{b['name']}</div>
    <div style="font-size:11px;color:var(--sub)">{len(b['docs'])} 文件 · {b['docs'][0]['author']}</div>
  </div>
  <span class="{pill_cls}" style="font-size:10px">{pill_lbl}</span>
</div>"""

    # Right detail for bidder A
    b = BIDDERS[0]
    fields_kv = ""
    for label, field, danger in [("作者","author",True),("最后修改者","lmb",True),("公司","company",True),("模板","template",False),("创建时间","created",False),("修改时间","modified",False)]:
        val = b["docs"][0][field]
        cls = " cell danger" if danger else ""
        fields_kv += f'<div class="cell{cls}"><div class="lbl">{label}</div><div class="val">{val}</div></div>'

    doc_list = ""
    for d in b["docs"]:
        fmt_cls = FMT_BADGE[d["fmt"]][0]
        fmt_lbl = FMT_BADGE[d["fmt"]][1]
        doc_list += f"""<div class="doc-row">
  <span class="fmt-badge {fmt_cls}">{fmt_lbl}</span>
  <span style="font-size:13px;font-weight:500;flex:1">{d['name']}</span>
  <span class="code">{d['size']}</span>
  <span class="code">{d['sha']}</span>
  <span class="pill pill--danger" style="font-size:10px">作者重合</span>
</div>"""

    content = f"""<div class="l4-split">
  <div class="l4-left">{left_items}</div>
  <div class="l4-right">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <span style="display:grid;width:36px;height:36px;place-items:center;border-radius:var(--r-item);background:var(--danger);color:#fff;font-weight:700;font-size:16px">{b['letter']}</span>
      <div><div style="font-size:16px;font-weight:700">{b['name']}</div><div style="font-size:12px;color:var(--sub)">3 个文件 · 作者「张明」与投标人 C、D 一致</div></div>
      <span class="pill pill--danger" style="margin-left:auto">高风险</span>
    </div>
    <div class="col-banner col-banner--danger" style="margin-bottom:14px">⚠ 作者「张明」与投标人 C、D 相同 · 模板「通用投标模板V3.dotx」与 C、D 相同</div>
    <div style="font-size:13px;font-weight:600;margin-bottom:8px">关键元数据</div>
    <div class="l4-kv">{fields_kv}</div>
    <div style="font-size:13px;font-weight:600;margin-bottom:8px;margin-top:16px">文件列表</div>
    {doc_list}
  </div>
</div>"""
    return shell("方案4 · 左右分栏模式", css, content, use_wash=False)


# ═══════════════════════════════════════════════════════════════════
# Layout 5: 关系网络图 — Visual connection graph between bidders
# ═══════════════════════════════════════════════════════════════════
def layout5():
    css = """.l5-wrap{max-width:1000px;margin:0 auto;padding:16px}
.l5-graph{position:relative;height:380px;background:var(--line-soft);border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden;margin-bottom:16px}
.l5-node{position:absolute;display:flex;flex-direction:column;align-items:center;gap:4px;z-index:2}
.l5-node__circle{display:grid;width:56px;height:56px;place-items:center;border-radius:var(--r-full);font-weight:700;font-size:20px;border:3px solid;box-shadow:0 4px 14px rgba(0,0,0,.12)}
.l5-node__label{font-size:11px;font-weight:600;text-align:center;max-width:90px}
.l5-legend{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}"""
    # Position nodes in a pentagon
    import math
    positions = {}
    cx, cy = 500, 190
    radius = 140
    for i, b in enumerate(BIDDERS):
        angle = -90 + i * 72
        x = cx + radius * math.cos(math.radians(angle)) - 30
        y = cy + radius * math.sin(math.radians(angle)) - 30
        positions[b["id"]] = (x + 30, y + 30)

    # SVG connections
    svg_lines = ""
    for t in ALL_TRACES:
        bids = t["bidders"]
        for i in range(len(bids)):
            for j in range(i+1, len(bids)):
                a, b_id = bids[i], bids[j]
                x1, y1 = positions[a]
                x2, y2 = positions[b_id]
                svg_lines += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{t["color"]}" stroke-width="2" opacity="0.5" stroke-dasharray="5,3"/>'

    nodes = ""
    for b in BIDDERS:
        is_danger = b["id"] in DANGER_BIDS
        x, y = positions[b["id"]]
        color = "var(--danger)" if is_danger else "var(--ok)"
        bg = "#fff5f5" if is_danger else "var(--ok-weak)"
        left = x - 30
        top = y - 30
        nodes += f"""<div class="l5-node" style="left:{left}px;top:{top}px">
  <div class="l5-node__circle" style="background:{bg};color:{color};border-color:{color}">{b['letter']}</div>
  <div class="l5-node__label">{b['name'][:8]}</div>
</div>"""

    # Legend
    legend = ""
    for t in ALL_TRACES:
        legend += f"""<span class="col-chip" style="--tag-color:{t['color']}">
  <span class="match-dot" style="background:{t['color']};width:14px;height:14px;font-size:8px">·</span>
  <span style="font-size:11px;font-weight:600">{t['field']}</span>
  <span class="num" style="font-size:11px">{t['value']}</span></span>"""

    content = f"""<div class="l5-wrap">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <div><h2 style="font-size:18px">跨投标人关系网络</h2><p style="font-size:13px;color:var(--sub);margin-top:2px">线条颜色对应不同元数据痕迹的重合类型</p></div>
    <span class="pill pill--danger">3 家高风险</span>
  </div>
  <div class="l5-graph">
    <svg style="position:absolute;inset:0;width:100%;height:100%;z-index:1">{svg_lines}</svg>
    {nodes}
  </div>
  <div class="l5-legend">{legend}</div>
  <div class="card" style="border-left:3px solid var(--danger)">
    <div class="card-h"><span class="pill pill--danger">分析结论</span><b>投标人 A、C、D 构成疑似围标组</b></div>
    <div style="padding:14px 16px;font-size:13px;line-height:1.8">
      <p>• <b>作者痕迹</b>：A、C、D 的文档作者均为「张明」，修改者 A/C 也完全一致</p>
      <p>• <b>模板复用</b>：A、C、D 均使用「通用投标模板V3.dotx」创建技术标</p>
      <p>• <b>时间戳</b>：A、C、D 文档创建时间均为 2026-07-15 09:30（精确到分钟）</p>
      <p>• <b>公司痕迹</b>：A、C 文档元数据中公司字段均为「宏达建设集团」</p>
      <p style="color:var(--sub);margin-top:8px">投标人 B、E 未发现任何跨投标人痕迹重合。</p>
    </div>
  </div>
</div>"""
    return shell("方案5 · 关系网络图模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 6: 热力图矩阵 — Bidders × fields heatmap
# ═══════════════════════════════════════════════════════════════════
def layout6():
    css = """.l6-wrap{max-width:1000px;margin:0 auto;padding:16px}
.l6-matrix{display:grid;grid-template-columns:120px repeat(5,1fr);gap:2px;background:var(--line);border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden}
.l6-cell{padding:10px 8px;background:#fff;text-align:center;font-size:12px}
.l6-cell--header{background:#fcfcfe;font-weight:600;font-size:11px;color:var(--sub)}
.l6-cell--field{background:#fcfcfe;text-align:left;font-weight:600;font-size:12px;color:var(--ink);padding-left:14px}
.l6-cell--hot{background:var(--danger);color:#fff;font-weight:700}
.l6-cell--warm{background:var(--warn-weak);color:var(--warn);font-weight:600}
.l6-cell--cool{background:var(--ok-weak);color:var(--ok)}"""
    # Header row
    matrix = '<div class="l6-cell l6-cell--header"></div>'
    for b in BIDDERS:
        matrix += f'<div class="l6-cell l6-cell--header">{b["letter"]} · {b["name"][:6]}</div>'

    # Field rows
    fields = [("作者","author",True),("最后修改者","lmb",True),("公司","company",True),("模板","template",False),("创建时间","created",False),("修改时间","modified",False)]
    for label, field, is_person in fields:
        matrix += f'<div class="l6-cell l6-cell--field">{label}</div>'
        for b in BIDDERS:
            val = b["docs"][0][field]
            is_danger = is_person and b["id"] in DANGER_BIDS and val != "—"
            is_caution = (not is_person) and b["id"] in DANGER_BIDS and val != "—" and field in ("template","created")
            if is_danger:
                cls = "l6-cell l6-cell--hot"
            elif is_caution:
                cls = "l6-cell l6-cell--warm"
            elif b["id"] in OK_BIDS:
                cls = "l6-cell l6-cell--cool"
            else:
                cls = "l6-cell"
            display = val[:12] + "…" if len(val) > 13 else val
            matrix += f'<div class="{cls} num">{display}</div>'

    content = f"""<div class="l6-wrap">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <div><h2 style="font-size:18px">痕迹热力矩阵</h2><p style="font-size:13px;color:var(--sub);margin-top:2px">红色=人员重合 · 橙色=模板/时间重合 · 绿色=无异常</p></div>
  </div>
  <div class="l6-matrix">{matrix}</div>
  <div style="display:flex;gap:16px;margin-top:14px;font-size:12px;color:var(--sub)">
    <span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:14px;border-radius:3px;background:var(--danger)"></span>人员/组织身份重合</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:14px;border-radius:3px;background:var(--warn-weak);border:1px solid #f0d8a8"></span>模板/时间戳重合</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:14px;border-radius:3px;background:var(--ok-weak);border:1px solid #a8d8c0"></span>无跨投标人重合</span>
  </div>
</div>"""
    return shell("方案6 · 热力图矩阵模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 7: 投标人手风琴 — Full-width collapsible panels (current style, refined)
# ═══════════════════════════════════════════════════════════════════
def layout7():
    css = """.l7-wrap{max-width:1200px;margin:0 auto;padding:16px}
.l7-panel{border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden;margin-bottom:10px}
.l7-panel--danger{border-left:3px solid var(--danger)}
.l7-panel__h{display:flex;align-items:center;gap:10px;padding:12px 16px;background:#f8f9fb;border-bottom:1px solid var(--line-soft);cursor:pointer}
.l7-panel--danger .l7-panel__h{background:var(--danger-weak)}
.l7-panel__letter{display:grid;width:30px;height:30px;place-items:center;border-radius:var(--r-item);font-weight:700;font-size:14px;flex-shrink:0}
.l7-panel__body{padding:10px;display:flex;flex-direction:column;gap:6px}
.l7-doc{display:flex;border:1px solid var(--line);border-radius:var(--r-item);overflow:hidden}
.l7-doc--flagged{border-color:#f0b8b8}
.l7-doc__bar{width:4px;flex-shrink:0}
.l7-doc__body{flex:1;padding:10px 12px}
.l7-doc__h{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.l7-doc__name{font-size:12.5px;font-weight:600}
.l7-kv{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--r-item);overflow:hidden}
.l7-kv .kv{padding:5px 8px;background:#fff;display:flex;flex-direction:column;gap:1px}
.l7-kv .kv.danger{background:var(--danger-weak)}
.l7-kv .kv .lbl{font-size:9.5px;color:var(--faint)}
.l7-kv .kv .val{font-family:var(--mono);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.l7-kv .kv.danger .val{color:var(--danger);font-weight:600}"""
    panels = ""
    for b in BIDDERS:
        is_danger = b["id"] in DANGER_BIDS
        panel_cls = "l7-panel l7-panel--danger" if is_danger else "l7-panel"
        letter_bg = "background:var(--danger);color:#fff" if is_danger else "background:var(--primary);color:#fff"
        pill_cls = "pill pill--danger" if is_danger else "pill pill--ok"
        pill_lbl = "高风险" if is_danger else "无异常"

        # Documents
        docs_html = ""
        for d in b["docs"]:
            has_match = is_danger and d["fmt"] == "word"
            bar_color = "var(--danger)" if has_match else "transparent"
            doc_cls = "l7-doc l7-doc--flagged" if has_match else "l7-doc"
            fmt_cls = FMT_BADGE[d["fmt"]][0]
            fmt_lbl = FMT_BADGE[d["fmt"]][1]
            fields_data = [("作者",d["author"]),("修改者",d["lmb"]),("公司",d["company"]),("模板",d["template"]),("创建",d["created"]),("修改",d["modified"])]
            kv_cells = ""
            for fl, fv in fields_data:
                d_cell = is_danger and fl in ("作者","修改者","公司") and fv != "—"
                kv_cells += f'<div class="kv{" danger" if d_cell else ""}"><div class="lbl">{fl}</div><div class="val">{fv}</div></div>'
            match_tag = '<span class="match-dot" style="background:#dc2626;width:16px;height:16px;font-size:9px">1</span>' if has_match else ""
            docs_html += f"""<div class="{doc_cls}">
  <div class="l7-doc__bar" style="background:{bar_color}"></div>
  <div class="l7-doc__body">
    <div class="l7-doc__h">
      <span class="fmt-badge {fmt_cls}">{fmt_lbl}</span>
      <span class="l7-doc__name">{d['name']}</span>
      {match_tag}
      <span class="code">{d['size']}</span>
    </div>
    <div class="l7-kv">{kv_cells}</div>
  </div>
</div>"""

        collapse = "▾" if b["id"] in ("A","B") else "▸"
        body_display = "" if b["id"] in ("A","B") else ' style="display:none"'
        panels += f"""<div class="{panel_cls}">
  <div class="l7-panel__h">
    <span class="l7-panel__letter" style="{letter_bg}">{b['letter']}</span>
    <div style="flex:1;min-width:0">
      <div style="font-size:13.5px;font-weight:600">{b['name']}</div>
      <div style="font-size:11px;color:var(--sub)">作者：{b['docs'][0]['author']} · {len(b['docs'])} 文件</div>
    </div>
    {'<span class="pill pill--danger">⚠ 2 文件存疑</span>' if is_danger else '<span class="pill pill--ok">无异常</span>'}
    <span style="font-size:12px;color:var(--faint)">{collapse}</span>
  </div>
  <div class="l7-panel__body"{body_display}>{docs_html}</div>
</div>"""

    content = f"""<div class="l7-wrap">
  <div class="col-banner col-banner--danger" style="margin-bottom:12px">⚠ 3 处人员重合 + 2 处模板/时间重合 — 投标人 A、C、D 高度关联</div>
  {panels}
</div>"""
    return shell("方案7 · 手风琴展开模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 8: 三链证据对比 — Three parser columns per bidder
# ═══════════════════════════════════════════════════════════════════
def layout8():
    css = """.l8-wrap{max-width:1200px;margin:0 auto;padding:16px}
.l8-card{border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden;margin-bottom:12px}
.l8-card--danger{border-left:3px solid var(--danger)}
.l8-card__h{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line-soft);background:#f8f9fb}
.l8-card__h--danger{background:var(--danger-weak)}
.l8-chains{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--line)}
.l8-chain{padding:12px 14px;background:#fff}
.l8-chain__h{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;margin-bottom:8px}
.l8-chain__body{font-size:11.5px;line-height:1.8;color:var(--sub);font-family:var(--mono)}
.l8-chain__body b{color:var(--ink);font-weight:600}
.l8-chain__body .danger{color:var(--danger);font-weight:600}"""
    cards = ""
    for b in BIDDERS:
        is_danger = b["id"] in DANGER_BIDS
        card_cls = "l8-card l8-card--danger" if is_danger else "l8-card"
        h_cls = "l8-card__h l8-card__h--danger" if is_danger else "l8-card__h"
        letter_bg = "background:var(--danger);color:#fff" if is_danger else "background:var(--primary);color:#fff"
        author = b["docs"][0]["author"]
        lmb = b["docs"][0]["lmb"]
        company = b["docs"][0]["company"]
        template = b["docs"][0]["template"]
        created = b["docs"][0]["created"]

        d_cls = ' class="danger"' if is_danger else ""

        cards += f"""<div class="{card_cls}">
  <div class="{h_cls}">
    <span style="display:grid;width:28px;height:28px;place-items:center;border-radius:var(--r-item);{letter_bg};font-weight:700">{b['letter']}</span>
    <span style="font-size:13.5px;font-weight:600">{b['name']}</span>
    {'<span class="pill pill--danger">高风险</span>' if is_danger else '<span class="pill pill--ok">无异常</span>'}
  </div>
  <div class="l8-chains">
    <div class="l8-chain">
      <div class="l8-chain__h">🛡 原生解析器</div>
      <div class="l8-chain__body">
        <div>作者: <b>{author}</b></div>
        <div>修改者: <b>{lmb}</b></div>
        <div>公司: <b>{company}</b></div>
        <div>模板: <b>{template}</b></div>
        <div>创建: <b>{created}</b></div>
      </div>
    </div>
    <div class="l8-chain">
      <div class="l8-chain__h">📄 Apache Tika</div>
      <div class="l8-chain__body">
        <div>Author: <b>{author}</b></div>
        <div>LastModifiedBy: <b>{lmb}</b></div>
        <div>Company: <b>{company}</b></div>
        <div>Template: <b>{template}</b></div>
        <div>Created: <b>{created}</b></div>
      </div>
    </div>
    <div class="l8-chain">
      <div class="l8-chain__h">🔍 ExifTool 13.55</div>
      <div class="l8-chain__body">
        <div>Creator: <b>{author}</b></div>
        <div>ModifyBy: <b>{lmb}</b></div>
        <div>Organization: <b>{company}</b></div>
        <div>Template: <b>{template}</b></div>
        <div>CreateDate: <b>{created}</b></div>
      </div>
    </div>
  </div>
</div>"""

    content = f"""<div class="l8-wrap">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <div><h2 style="font-size:18px">三链证据对比</h2><p style="font-size:13px;color:var(--sub);margin-top:2px">每条元数据由原生解析器、Apache Tika、ExifTool 独立提取并交叉验证</p></div>
    <span class="pill pill--ok">三链一致</span>
  </div>
  {cards}
</div>"""
    return shell("方案8 · 三链证据对比模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 9: 时间线聚类 — Metadata grouped by creation timestamps
# ═══════════════════════════════════════════════════════════════════
def layout9():
    css = """.l9-wrap{max-width:1000px;margin:0 auto;padding:16px}
.l9-cluster{display:flex;gap:16px;margin-bottom:16px}
.l9-time{width:140px;flex:none;text-align:right;padding-top:12px}
.l9-time__val{font-family:var(--mono);font-size:13px;font-weight:700}
.l9-time__count{font-size:11px;color:var(--sub);margin-top:2px}
.l9-line{width:2px;background:var(--line);flex:none;position:relative}
.l9-dot{position:absolute;top:14px;left:-4px;width:10px;height:10px;border-radius:50%;border:2px solid #fff}
.l9-items{flex:1;display:flex;flex-direction:column;gap:6px}
.l9-item{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line);border-radius:var(--r-item);background:#fff}
.l9-item--danger{border-color:#f0b8b8;background:var(--danger-weak)}"""
    # Group by created time
    clusters = [
        ("2026-07-12 10:00", "B", [("B","华西建设","李伟","商务标.pdf")]),
        ("2026-07-13 08:00", "E", [("E","新兴建设","赵强","商务标.pdf")]),
        ("2026-07-15 09:30", "A+C+D", [("A","中铁建工","张明","技术标.docx"),("C","宏达建设","张明","技术标.docx"),("D","正阳工程","张明","技术标.docx")]),
    ]

    timeline = ""
    for time_str, group, items in clusters:
        is_danger = len(items) > 1
        dot_color = "var(--danger)" if is_danger else "var(--ok)"
        count_text = f"{len(items)} 个文件" + (" · 同一时刻" if is_danger else "")
        items_html = ""
        for bid, bname, author, doc_name in items:
            item_cls = "l9-item l9-item--danger" if is_danger else "l9-item"
            items_html += f"""<div class="{item_cls}">
  <span class="match-dot" style="background:{'var(--danger)' if is_danger else 'var(--ok)'};width:16px;height:16px;font-size:9px">{bid}</span>
  <span style="font-size:12.5px;font-weight:600">{bname}</span>
  <span class="code">{doc_name}</span>
  <span style="font-size:11px;color:var(--sub)">作者：{author}</span>
  {'<span class="pill pill--danger" style="font-size:10px">同时创建</span>' if is_danger else '<span class="pill pill--ok" style="font-size:10px">独立</span>'}
</div>"""
        timeline += f"""<div class="l9-cluster">
  <div class="l9-time"><div class="l9-time__val" {"style='color:var(--danger)'" if is_danger else ""}>{time_str}</div><div class="l9-time__count">{count_text}</div></div>
  <div class="l9-line"><div class="l9-dot" style="background:{dot_color}"></div></div>
  <div class="l9-items">{items_html}</div>
</div>"""

    content = f"""<div class="l9-wrap">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <div><h2 style="font-size:18px">创建时间聚类分析</h2><p style="font-size:13px;color:var(--sub);margin-top:2px">按文档创建时间排序，同时段创建的跨投标人文件标红</p></div>
  </div>
  <div class="col-banner col-banner--danger" style="margin-bottom:16px">⚠ 投标人 A、C、D 的文件在同一分钟（07-15 09:30）创建</div>
  {timeline}
</div>"""
    return shell("方案9 · 时间线聚类模式", css, content)


# ═══════════════════════════════════════════════════════════════════
# Layout 10: 正式报告模式 — Print-ready audit report
# ═══════════════════════════════════════════════════════════════════
def layout10():
    css = """.l10-wrap{max-width:800px;margin:0 auto;padding:32px 24px}
.l10-report{font-size:13px;line-height:1.8}
.l10-report h1{font-size:24px;font-weight:700;text-align:center;margin-bottom:6px}
.l10-report .sub{text-align:center;font-size:13px;color:var(--sub);margin-bottom:24px}
.l10-section{margin-bottom:24px}
.l10-section h2{font-size:16px;font-weight:700;border-bottom:2px solid var(--primary);padding-bottom:6px;margin-bottom:12px}
.l10-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:12px}
.l10-table th{background:var(--primary-weak);color:var(--ink);font-weight:600;text-align:left;padding:8px 10px;border:1px solid var(--line);font-size:11.5px}
.l10-table td{padding:7px 10px;border:1px solid var(--line)}
.l10-table td.danger{background:var(--danger-weak);color:var(--danger);font-weight:600}
.l10-conclusion{border:1px solid var(--line);border-left:4px solid var(--danger);border-radius:var(--r-item);padding:14px 16px;margin-bottom:16px}
.l10-sign{display:flex;justify-content:space-between;margin-top:40px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--sub)}"""
    # Conclusion box
    conclusion = """<div class="l10-conclusion">
  <div style="font-size:14px;font-weight:700;color:var(--danger);margin-bottom:6px">核验结论：存在围标串标重大嫌疑</div>
  <p style="font-size:13px;line-height:1.7">投标人 A（中铁建工集团）、C（宏达建设集团）、D（正阳工程）的投标文件存在以下重合：</p>
  <ol style="font-size:12.5px;line-height:1.8;padding-left:20px;margin-top:6px">
    <li>文档作者均为「张明」，最后修改者 A/C 完全一致</li>
    <li>技术标文档使用同一模板「通用投标模板V3.dotx」</li>
    <li>文档创建时间均为 2026-07-15 09:30（精确到分钟）</li>
    <li>A/C 公司字段均为「宏达建设集团」</li>
  </ol>
  <p style="font-size:12px;color:var(--sub);margin-top:8px">以上结论由原生解析器、Apache Tika 3.3.2、ExifTool 13.55 三条独立解析链交叉验证。</p>
</div>"""

    # Person trace table
    trace_rows = ""
    for t in TRACES_PERSON:
        bids = "、".join(t["bidders"])
        trace_rows += f'<tr><td class="danger">{t["field"]}</td><td class="danger">{t["value"]}</td><td class="danger">{bids}</td></tr>'

    # Caution trace table
    caution_rows = ""
    for t in TRACES_CAUTION:
        bids = "、".join(t["bidders"])
        caution_rows += f'<tr><td style="background:var(--warn-weak);color:var(--warn);font-weight:600">{t["field"]}</td><td style="background:var(--warn-weak)">{t["value"]}</td><td style="background:var(--warn-weak)">{bids}</td></tr>'

    content = f"""<div class="l10-wrap"><div class="l10-report">
  <h1>文档元数据核验报告</h1>
  <div class="sub">4-投标文件 · 核验时间 2026-08-07 10:30 · 离线分析</div>

  <div class="l10-section">
    <h2>一、基本信息</h2>
    <table class="l10-table">
      <tr><th style="width:120px">核验目录</th><td>4-投标文件</td></tr>
      <tr><th>投标人数</th><td>5 家</td></tr>
      <tr><th>文件总数</th><td>15 个（PDF 5 · DOCX 5 · XLSX 5）</td></tr>
      <tr><th>元数据条目</th><td>2,075 条</td></tr>
      <tr><th>提取完成</th><td>15/15（100%）</td></tr>
      <tr><th>解析链</th><td>原生解析器 · Apache Tika 3.3.2 · ExifTool 13.55</td></tr>
    </table>
  </div>

  {conclusion}

  <div class="l10-section">
    <h2>二、人员/组织身份重复（高风险）</h2>
    <table class="l10-table">
      <thead><tr><th>痕迹类型</th><th>重复值</th><th>涉及投标人</th></tr></thead>
      <tbody>{trace_rows}</tbody>
    </table>
  </div>

  <div class="l10-section">
    <h2>三、模板/时间戳重复（待复核）</h2>
    <table class="l10-table">
      <thead><tr><th>痕迹类型</th><th>重复值</th><th>涉及投标人</th></tr></thead>
      <tbody>{caution_rows}</tbody>
    </table>
  </div>

  <div class="l10-section">
    <h2>四、建议</h2>
    <p style="font-size:12.5px;line-height:1.8">鉴于投标人 A、C、D 的文档元数据存在多处精确重合，建议：</p>
    <ol style="font-size:12.5px;line-height:1.8;padding-left:20px;margin-top:6px">
      <li>要求三家投标人分别说明文档编制过程</li>
      <li>核实「张明」的身份及与三家公司的关系</li>
      <li>结合报价文件和施工组织方案进一步审查</li>
    </ol>
  </div>

  <div class="l10-sign">
    <span>核验人：审计员</span>
    <span>核验日期：2026-08-07</span>
    <span>报告编号：RV-20260807-001</span>
  </div>
</div></div>"""
    return shell("方案10 · 正式报告模式", css, content, use_wash=False)


# ═══════════════════════════════════════════════════════════════════
# Index page
# ═══════════════════════════════════════════════════════════════════
def index_html(pages):
    items = ""
    for i, (fname, title, desc) in enumerate(pages, 1):
        items += f"""<a href="{fname}" style="display:flex;align-items:center;gap:14px;padding:18px 20px;background:#fff;border:1px solid var(--line);border-radius:var(--r-card);text-decoration:none;transition:border-color .15s,box-shadow .15s">
  <span style="display:grid;width:36px;height:36px;place-items:center;border-radius:var(--r-btn);background:var(--primary-weak);color:var(--primary);font-family:var(--mono);font-size:14px;font-weight:700;flex:none">{i:02d}</span>
  <div style="flex:1;min-width:0"><div style="font-size:15px;font-weight:600;color:var(--ink)">{title}</div><div style="font-size:12.5px;color:var(--sub);margin-top:2px">{desc}</div></div>
  <span style="color:var(--faint);font-size:13px">→</span>
</a>"""

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>文档元数据核验 · 10套页面布局</title>
<style>{CSS}
.idx-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:20px}}
</style></head><body>
<div class="wash"></div>
<div style="display:flex;flex-direction:column;height:100vh">
<div class="topbar">
  <span class="topbar__logo">{svg_logo()}</span>
  <span class="topbar__title">文档元数据核验</span>
  <span class="topbar__sep"></span>
  <span class="topbar__folder">原型索引</span>
  <span class="topbar__spacer"></span>
  <span class="topbar__status"><span class="topbar__dot"></span>10 套布局</span>
</div>
<div class="scroll-area" style="position:relative;z-index:1">
<div style="max-width:1000px;margin:0 auto;padding:40px 24px 80px">
  <div style="font-size:13px;color:var(--sub)">企业级 UI 原型</div>
  <h1 style="font-size:28px;font-weight:700;margin-top:8px">文档元数据核验 · 页面布局方案</h1>
  <p style="font-size:14px;color:var(--sub);max-width:700px;margin-top:10px">遵循<b style="color:var(--ink)">数智底座设计规范 v1.1</b>。同一份核验数据（5 家投标人、15 文件、5 处痕迹重合），10 种不同结构布局。</p>
  <div class="idx-grid">{items}</div>
</div>
</div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    pages = [
        ("01-驾驶舱模式.html", "驾驶舱模式", "深色 KPI 面板 + 风险组卡片 + 投标人清单（按风险排序）"),
        ("02-数据表模式.html", "数据表模式", "全宽数据表 — 投标人为列、元数据为行，红色标记跨投标人重合"),
        ("03-卡片网格模式.html", "卡片网格模式", "每个投标人一张卡片，关键元数据一览，红色边框标记高风险"),
        ("04-左右分栏模式.html", "左右分栏模式", "左侧投标人列表，右侧选中投标人的文件 + 元数据详情"),
        ("05-关系网络图.html", "关系网络图模式", "投标人节点 + 痕迹连线，可视化跨投标人关联强度"),
        ("06-热力图矩阵.html", "热力图矩阵模式", "投标人 × 元数据字段矩阵，颜色深浅表示重合程度"),
        ("07-手风琴展开.html", "手风琴展开模式", "全宽折叠面板 — 当前生产版本的精致改良版"),
        ("08-三链证据对比.html", "三链证据对比模式", "每投标人三列并排展示原生/Tika/ExifTool 的独立解析结果"),
        ("09-时间线聚类.html", "时间线聚类模式", "按创建时间排序，同一时刻创建的文件聚在一起并标红"),
        ("10-正式报告.html", "正式报告模式", "可打印的审计报告版式 — 结论 + 证据表 + 建议 + 签名"),
    ]

    gens = [layout1,layout2,layout3,layout4,layout5,layout6,layout7,layout8,layout9,layout10]
    for (fname,_,_),gen in zip(pages,gens):
        html = gen()
        (OUTPUT / fname).write_text(html, encoding="utf-8")
        print(f"  ✓ {fname}")

    (OUTPUT / "index.html").write_text(index_html(pages), encoding="utf-8")
    print(f"  ✓ index.html")
    print(f"\n完成！输出目录: {OUTPUT}")


if __name__ == "__main__":
    main()

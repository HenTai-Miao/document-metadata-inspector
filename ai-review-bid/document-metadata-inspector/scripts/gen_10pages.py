"""
Generate 10 complete, design-spec-compliant enterprise UI page prototypes
for the bid collusion detection platform.

Follows: 人机协同数智业务底座 设计规范 v1.1 (tokens.json)
Output: ~/Desktop/围标检测-10套企业页面/
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT = Path(os.path.expanduser("~/Desktop")) / "围标检测-10套企业页面"

# ═══════════════════════════════════════════════════════════════════
# SVG icons
# ═══════════════════════════════════════════════════════════════════
ICONS = """
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
<symbol id="i-play" viewBox="0 0 24 24"><path d="M7 5l12 7-12 7V5z" fill="currentColor"/></symbol>
<symbol id="i-stop" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/></symbol>
<symbol id="i-refresh" viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.6M20 5v4h-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-folder" viewBox="0 0 24 24"><path d="M3 7h6l2 2h10v10H3z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></symbol>
<symbol id="i-upload" viewBox="0 0 24 24"><path d="M12 16V5m0 0L8 9m4-4l4 4M5 19h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-file" viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 3v5h5M10 13h6M10 16h4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></symbol>
<symbol id="i-pdf" viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 3v5h5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><text x="9" y="18" font-size="6" font-weight="700" fill="currentColor">PDF</text></symbol>
<symbol id="i-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.5v2.5M12 19v2.5M4.5 4.5l1.8 1.8M17.7 17.7l1.8 1.8M2.5 12H5M19 12h2.5M4.5 19.5l1.8-1.8M17.7 6.3l1.8-1.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></symbol>
<symbol id="i-bell" viewBox="0 0 24 24"><path d="M12 3a6 6 0 0 0-6 6c0 4-2 6-2 6h16s-2-2-2-6a6 6 0 0 0-6-6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M10 19a2 2 0 0 0 4 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></symbol>
<symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-link" viewBox="0 0 24 24"><path d="M10 14a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1 1M14 10a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1-1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></symbol>
<symbol id="i-exit" viewBox="0 0 24 24"><path d="M14 5H6v14h8M13 12h8m0 0l-3-3m3 3l-3 3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></symbol>
<symbol id="i-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 11v5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="8" r="1" fill="currentColor" stroke="none"/></symbol>
<symbol id="i-arrow-r" viewBox="0 0 24 24"><path d="M5 12h14m0 0l-6-6m6 6l-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-filter" viewBox="0 0 24 24"><path d="M3 5h18l-7 8v5l-4 2v-7L3 5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></symbol>
<symbol id="i-trend" viewBox="0 0 24 24"><path d="M3 17l6-6 4 4 8-8M14 7h7v7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-warn" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></symbol>
<symbol id="i-fingerprint" viewBox="0 0 24 24"><path d="M12 4a8 8 0 0 0-8 8v4M20 12v-0a8 8 0 0 0-4-7M8 20v-4a4 4 0 0 1 8 0v2M12 12v4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></symbol>
<symbol id="i-scale" viewBox="0 0 24 24"><path d="M12 4v16M7 8H4l3-4 3 4H7zM17 8h-3l3-4 3 4h-3zM5 20h14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-target" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></symbol>
</svg>
"""

# ═══════════════════════════════════════════════════════════════════
# Shared CSS (from tokens.json v1.1)
# ═══════════════════════════════════════════════════════════════════
CSS = """
:root{
  --primary:#034ed6;--primary-hover:#0342b8;--primary-weak:#eaf1fe;--primary-weak-2:#f4f8ff;
  --primary-line-hover:#bcd0f5;--primary-dk:#4d8bff;--primary-dk-text:#cfe0ff;
  --primary-a07:rgba(3,78,214,.07);--primary-a08:rgba(3,78,214,.08);
  --primary-a09:rgba(3,78,214,.085);--primary-a10:rgba(3,78,214,.10);--primary-a28:rgba(3,78,214,.28);
  --ink:#141928;--sub:#5d6579;--faint:#6b7489;
  --line:#e8eaf0;--line-soft:#f0f2f7;
  --dark:#0e1226;--dark-2:#131834;--dark-line:rgba(125,145,205,.16);--dark-ink:#e9edfa;--dark-sub:#8b98bd;
  --ok:#15803d;--warn:#a85c00;--warn-weak:#fdf3e4;--danger:#c93438;--danger-weak:#fdeeee;
  --teal:#0f766e;--violet:#7c3aed;--cyan:#1fb2de;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --r-chip:7px;--r-item:8px;--r-btn:9px;--r-field:10px;--r-panel:12px;--r-card:13px;--r-panel-dk:14px;--r-full:999px;
  --sh-panel:0 12px 32px rgba(14,18,38,.18);--sh-float:0 4px 14px rgba(20,25,40,.10);--sh-pop:0 6px 20px rgba(20,25,40,.12);
  --wash-warm:rgba(124,58,237,.055);--wash-cool:rgba(31,178,222,.075);
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,-apple-system,"Segoe UI",sans-serif;
  background:#fff;color:var(--ink);font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--primary);text-decoration:none}
button{font:inherit;cursor:pointer;border:none;background:none}
.ic{width:16px;height:16px;flex:none;color:var(--sub)}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px;border-radius:4px}

/* wash */
.wash{position:absolute;top:0;left:0;right:0;height:480px;pointer-events:none;z-index:0;
  background:radial-gradient(720px 340px at 14% -12%,var(--primary-a09),transparent 66%),
  radial-gradient(860px 380px at 52% -16%,var(--wash-warm),transparent 64%),
  radial-gradient(640px 320px at 88% -10%,var(--wash-cool),transparent 66%)}
.wash::after{content:"";position:absolute;inset:auto 0 0 0;height:180px;background:linear-gradient(180deg,rgba(255,255,255,0),#fff)}

/* header */
.hdr{position:sticky;top:0;z-index:40;height:56px;background:rgba(255,255,255,.78);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line-soft);display:flex;align-items:center;gap:12px;padding:0 28px}
.hdr .brand{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:600}
.hdr .brand svg{width:22px;height:22px}
.hdr .sep{color:var(--faint);font-weight:400}
.hdr .sub-t{font-size:13.5px;color:var(--sub)}
.hdr .ver{margin-left:auto;font-family:var(--mono);font-size:11.5px;color:var(--sub);
  border:1px solid var(--line);border-radius:var(--r-full);padding:3px 12px;background:#fff}
.hdr .nav-links{display:flex;gap:2px;margin-left:24px}
.hdr .nav-links a{display:flex;align-items:center;gap:6px;height:36px;padding:0 13px;border-radius:var(--r-item);
  font-size:13.5px;color:var(--sub);font-weight:500;transition:background .15s,color .15s}
.hdr .nav-links a:hover{background:var(--line-soft);color:var(--ink)}
.hdr .nav-links a.on{color:var(--primary);font-weight:600;background:var(--primary-weak-2)}
.hdr .right-zone{display:flex;align-items:center;gap:8px;margin-left:auto}
.hdr .avatar{width:30px;height:30px;border-radius:var(--r-full);background:var(--primary);color:#fff;
  display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:600}
.icon-btn{width:34px;height:34px;border-radius:var(--r-item);border:1px solid var(--line);background:#fff;
  display:inline-flex;align-items:center;justify-content:center;position:relative}
.icon-btn:hover{border-color:#c9d2e3}
.icon-btn .dot{position:absolute;top:7px;right:7px;width:7px;height:7px;border-radius:50%;background:var(--danger);border:1.5px solid #fff}

/* page layout */
.page{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:0 28px}
.page-wide{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:0 28px}
main{padding:24px 0 80px;min-width:0}

/* typography */
.kicker{font-size:13px;color:var(--sub)}
.kicker b{font-weight:400}
h1{font-size:32px;line-height:1.3;font-weight:700;letter-spacing:.3px}
h2{font-size:20px;font-weight:700;letter-spacing:.2px}
.sec-h{font-size:15px;font-weight:700;margin:32px 0 14px;display:flex;align-items:center;gap:10px}
.sec-h .ic{color:var(--faint)}
.sec-h .count{font-family:var(--mono);font-size:12px;color:var(--faint);font-weight:400;margin-left:auto}
.lede{font-size:14.5px;color:var(--sub);max-width:760px;margin-top:10px}

/* card */
.card{background:#fff;border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden}
.card+.card{margin-top:12px}
.card-h{display:flex;align-items:center;gap:9px;padding:14px 18px;border-bottom:1px solid var(--line-soft)}
.card-h .ic{color:var(--faint)}
.card-h b{font-size:15px;font-weight:600}
.card-h .meta{font-size:12px;color:var(--faint);font-weight:400}
.card-h .right{margin-left:auto;font-size:12.5px;color:var(--sub);font-weight:600}
.card-h .right a{font-weight:500}
.card-b{padding:0}

/* row */
.row{display:flex;align-items:flex-start;gap:12px;padding:14px 18px;border-bottom:1px solid var(--line-soft)}
.row:last-child{border-bottom:none}
.row:hover{background:#fafbfe}
.row .body{min-width:0;flex:1}
.row .l1{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.row .name{font-size:14px;font-weight:600;color:var(--ink)}
.row .l2{margin-top:4px;font-size:12.8px;color:var(--sub)}
.row .l2 em{font-style:normal;color:var(--faint);margin:0 5px}
.row .l2 .bad{color:var(--danger);font-weight:500}

/* tags */
.pill{flex:none;font-size:12px;font-weight:600;border-radius:var(--r-full);padding:3px 11px;white-space:nowrap}
.pill.danger{color:var(--danger);background:var(--danger-weak)}
.pill.warn{color:var(--warn);background:var(--warn-weak)}
.pill.ok{color:var(--ok);background:#e7f6f0}
.pill.neutral{color:var(--sub);background:var(--line-soft)}
.pill.info{color:var(--primary);background:var(--primary-weak)}
.stage{flex:none;font-size:12px;font-weight:600;border-radius:var(--r-chip);padding:3px 10px;white-space:nowrap}
.stage.s1{color:var(--danger);background:var(--danger-weak)}
.stage.s2{color:var(--warn);background:var(--warn-weak)}
.stage.s3{color:var(--ok);background:#e7f6f0}
.stage.s4{color:var(--primary);background:var(--primary-weak)}
.stage.s5{color:var(--violet);background:#f3edfd}
.code{font-family:var(--mono);font-size:11.5px;color:var(--sub);background:var(--line-soft);
  border-radius:6px;padding:2px 7px;letter-spacing:.02em}

/* buttons */
.primary-btn{display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 16px;
  border-radius:var(--r-btn);border:none;background:var(--primary);color:#fff;font-size:13.5px;font-weight:600;
  transition:background .15s;cursor:pointer}
.primary-btn:hover{background:var(--primary-hover)}
.primary-btn .ic{width:14px;height:14px}
.primary-btn:disabled{opacity:.5;cursor:not-allowed}
.ghost{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border-radius:var(--r-item);
  background:#fff;border:1px solid var(--line);font-size:12.5px;font-weight:500;color:var(--ink);cursor:pointer;transition:border-color .15s}
.ghost:hover{border-color:#c9d2e3}
.ghost .ic{width:13px;height:13px;color:var(--sub)}
.link-btn{display:inline-flex;align-items:center;gap:4px;font-size:13px;font-weight:500;color:var(--primary);cursor:pointer}
.link-btn .ic{width:13px;height:13px}

/* table */
table{width:100%;border-collapse:collapse;font-size:13px}
.tbl-wrap{border:1px solid var(--line);border-radius:var(--r-card);overflow:auto;background:#fff}
th{font-size:12px;font-weight:600;color:var(--sub);text-align:left;padding:11px 16px;
  border-bottom:1px solid var(--line);background:#fcfcfe;white-space:nowrap}
td{padding:10px 16px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafbfe}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}

/* dark panel */
.kpi-panel{background:var(--dark);border-radius:var(--r-panel-dk);overflow:hidden;box-shadow:var(--sh-panel)}
.kpi-panel .ph{display:flex;align-items:center;gap:10px;padding:13px 18px;background:var(--dark-2);border-bottom:1px solid var(--dark-line)}
.kpi-panel .ph .ic{color:var(--dark-sub)}
.kpi-panel .ph b{font-size:13.5px;font-weight:600;color:var(--dark-ink)}
.kpi-panel .ph .meta{margin-left:auto;font-size:12px;color:var(--dark-sub)}
.kgrid{display:grid}
.kgrid .k{padding:16px 18px;position:relative}
.kgrid .k+.k::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:1px;background:var(--dark-line)}
.kgrid .k .lbl{font-size:12px;color:var(--dark-sub)}
.kgrid .k .val{margin-top:4px;font-family:var(--mono);font-size:26px;font-weight:700;line-height:1.25;font-variant-numeric:tabular-nums;color:#fff}
.kgrid .k .val.bad{color:#ff8a8f}
.kgrid .k .val.warn{color:#ffc46b}
.kgrid .k .val.ok{color:#5fd6a2}
.kgrid .k .dlt{margin-top:2px;font-size:11.5px;color:var(--dark-sub)}

/* status bar */
.status-bar{display:flex;align-items:center;gap:12px;height:48px;padding:0 14px;background:#fff;
  border:1px solid var(--line);border-radius:var(--r-panel)}
.status-bar .tag{font-size:12px;font-weight:700;border-radius:var(--r-chip);padding:4px 10px;display:flex;align-items:center;gap:5px;white-space:nowrap}
.status-bar .tag.ok{color:var(--ok);background:#e7f6f0}
.status-bar .tag.run{color:var(--primary);background:var(--primary-weak)}
.status-bar .tag.err{color:var(--danger);background:var(--danger-weak)}
.status-bar .txt{font-size:14px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.status-bar .txt b{font-weight:600}
.status-bar .spacer{flex:1}
.status-bar .num{font-family:var(--mono);font-size:12.5px;color:var(--sub)}

/* layout utilities */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.flex{display:flex;align-items:center;gap:12px}
.flex-col{display:flex;flex-direction:column;gap:12px}
.mt-0{margin-top:0}.mt-1{margin-top:4px}.mt-2{margin-top:8px}.mt-3{margin-top:12px}.mt-4{margin-top:16px}.mt-5{margin-top:20px}.mt-6{margin-top:24px}.mt-8{margin-top:32px}
.mb-0{margin-bottom:0}.mb-1{margin-bottom:4px}.mb-2{margin-bottom:8px}.mb-3{margin-bottom:12px}.mb-4{margin-bottom:16px}.mb-6{margin-bottom:24px}
.gap-1{gap:4px}.gap-2{gap:8px}.gap-3{gap:12px}
.flex-1{flex:1;min-width:0}
.right-ml{margin-left:auto}

/* progress */
.progress-track{height:6px;border-radius:var(--r-full);background:var(--line-soft);overflow:hidden}
.progress-fill{height:100%;border-radius:var(--r-full);background:var(--primary);transition:width .3s}

/* sidebar nav */
.side-nav{width:200px;flex:none;border-right:1px solid var(--line);padding:16px 0;height:calc(100vh - 56px);
  position:sticky;top:56px;overflow-y:auto}
.side-nav .grp-h{display:flex;align-items:center;gap:6px;padding:6px 16px;font-size:14px;font-weight:600;color:var(--ink)}
.side-nav .grp-h .ic{width:13px;height:13px;color:var(--faint);margin-left:auto}
.side-nav ul{list-style:none;margin:2px 0 0;padding:0}
.side-nav li a{display:flex;align-items:center;gap:8px;height:36px;padding:0 16px;font-size:13.5px;
  color:var(--sub);font-weight:400;transition:background .15s,color .15s}
.side-nav li a:hover{background:var(--line-soft);color:var(--ink)}
.side-nav li a.on{color:var(--primary);font-weight:600;background:var(--primary-weak-2)}
.side-nav li a .n{margin-left:auto;font-size:11px;font-weight:600;font-family:var(--mono);
  color:var(--danger);background:var(--danger-weak);border-radius:var(--r-full);padding:1px 7px}
.side-nav li a .n.neutral{color:var(--faint);background:var(--line-soft)}

/* stepper */
.stepper{display:flex;align-items:center;gap:0;width:100%}
.step{display:flex;align-items:center;gap:10px;flex:1;cursor:pointer}
.step .dot{width:32px;height:32px;border-radius:var(--r-full);border:2px solid var(--line);
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;color:var(--faint);flex:none;transition:all .15s}
.step .label{font-size:13.5px;font-weight:500;color:var(--faint)}
.step.done .dot{background:var(--ok);border-color:var(--ok);color:#fff}
.step.done .label{color:var(--sub)}
.step.active .dot{background:var(--primary);border-color:var(--primary);color:#fff}
.step.active .label{color:var(--ink);font-weight:600}
.step-line{flex:1;height:2px;background:var(--line);margin:0 8px}
.step-line.done{background:var(--ok)}

/* responsive */
@media(max-width:760px){.grid-2,.grid-3,.grid-4{grid-template-columns:1fr}.side-nav{display:none}
  .kgrid{grid-template-columns:1fr 1fr!important}.stepper{flex-direction:column}}
"""

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def header(title: str, active_nav: str = "") -> str:
    nav_items = [
        ("任务列表", "tasks"),
        ("数据看板", "dashboard"),
        ("元数据核验", "metadata"),
        ("系统设置", "settings"),
    ]
    links = ""
    for label, key in nav_items:
        cls = ' class="on"' if key == active_nav else ""
        links += f'<a{cls} href="#">{label}</a>'
    return f"""<div class="wash"></div>
<header class="hdr">
  <div class="brand"><svg><use href="#i-logo"/></svg>围标串标检测系统</div>
  <div class="nav-links">{links}</div>
  <div class="right-zone">
    <button class="icon-btn"><svg class="ic"><use href="#i-bell"/></svg><span class="dot"></span></button>
    <span class="avatar">审</span>
  </div>
</header>"""


def sidebar(active: str = "") -> str:
    groups = [
        ("检测中心", [
            ("任务列表", "i-list", "tasks", "24"),
            ("进行中", "i-play", "running", "3", False),
            ("已完成", "i-check", "done", "18", True),
        ]),
        ("分析", [
            ("数据看板", "i-chart", "dashboard", None, True),
            ("历史报告", "i-doc", "reports", None, True),
        ]),
        ("工具", [
            ("元数据核验", "i-fingerprint", "metadata", "5", False),
            ("文档比对", "i-scale", "compare", None, True),
        ]),
    ]
    out = '<aside class="side-nav">'
    for gname, items in groups:
        out += f'<div class="grp-h">{gname}<svg class="ic"><use href="#i-chev-d"/></svg></div><ul>'
        for item in items:
            label, icon, key = item[0], item[1], item[2]
            badge = item[3] if len(item) > 3 else None
            neutral = item[4] if len(item) > 4 else False
            cls = ' class="on"' if key == active else ""
            b_cls = " neutral" if neutral else ""
            badge_html = f'<span class="n{b_cls}">{badge}</span>' if badge else ""
            out += f'<li><a{cls} href="#"><svg class="ic"><use href="#{icon}"/></svg>{label}{badge_html}</a></li>'
        out += '</ul>'
    out += '</aside>'
    return out


def page_wrap(title: str, content: str, nav: str = "") -> str:
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}</style></head><body>
{ICONS}
{header(title, nav)}
<div class="page"><main>
{content}
</main></div>
</body></html>"""


def page_wrap_sidebar(title: str, sidebar_active: str, nav_active: str, content: str) -> str:
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}</style></head><body>
{ICONS}
{header(title, nav_active)}
<div style="display:flex;position:relative">
{sidebar(sidebar_active)}
<div class="page" style="flex:1;max-width:none"><main>
{content}
</main></div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Page 1: 登录页
# ═══════════════════════════════════════════════════════════════════
def page01_login() -> str:
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 · 围标串标检测系统</title>
<style>{CSS}
.login-bg{{position:absolute;inset:0;z-index:0;
  background:radial-gradient(900px 400px at 20% -10%,var(--primary-a09),transparent 60%),
  radial-gradient(700px 350px at 80% 110%,var(--wash-cool),transparent 60%),
  radial-gradient(500px 300px at 90% 20%,var(--wash-warm),transparent 60%),#f8f9fc}}
.login-wrap{{position:relative;z-index:1;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px}}
.login-card{{width:400px;max-width:100%;background:#fff;border:1px solid var(--line);border-radius:var(--r-card);
  padding:36px 32px;box-shadow:var(--sh-pop)}}
.login-logo{{display:flex;align-items:center;gap:10px;justify-content:center;margin-bottom:6px}}
.login-logo svg{{width:32px;height:32px}}
.login-logo span{{font-size:18px;font-weight:700;color:var(--ink)}}
.login-sub{{text-align:center;font-size:13px;color:var(--sub);margin-bottom:28px}}
.field{{margin-bottom:16px}}
.field label{{display:block;font-size:13px;font-weight:600;color:var(--ink);margin-bottom:6px}}
.field input{{width:100%;height:40px;padding:0 14px;border:1px solid var(--line);border-radius:var(--r-field);
  font-size:14px;color:var(--ink);background:#fff;transition:border-color .15s}}
.field input:focus{{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-a10)}}
.login-btn{{width:100%;height:42px;border-radius:var(--r-btn);border:none;background:var(--primary);color:#fff;
  font-size:14px;font-weight:600;cursor:pointer;transition:background .15s}}
.login-btn:hover{{background:var(--primary-hover)}}
.login-foot{{margin-top:20px;text-align:center;font-size:12px;color:var(--faint)}}
.checkbox-row{{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--sub);margin-bottom:20px;cursor:pointer}}
.checkbox-row input{{width:16px;height:16px;accent-color:var(--primary)}}
.divider-text{{display:flex;align-items:center;gap:12px;margin:24px 0;font-size:12px;color:var(--faint)}}
.divider-text::before,.divider-text::after{{content:"";flex:1;height:1px;background:var(--line)}}
</style></head><body>
{ICONS}
<div class="login-bg"></div>
<div class="login-wrap">
  <div class="login-card">
    <div class="login-logo"><svg><use href="#i-logo"/></svg><span>围标串标检测系统</span></div>
    <div class="login-sub">招投标风险智能审查平台</div>
    <div class="field">
      <label>用户名</label>
      <input type="text" placeholder="请输入用户名" value="审计员张明" />
    </div>
    <div class="field">
      <label>密码</label>
      <input type="password" placeholder="请输入密码" value="••••••••••" />
    </div>
    <label class="checkbox-row"><input type="checkbox" checked />记住登录状态</label>
    <button class="login-btn">登 录</button>
    <div class="divider-text">安全提示</div>
    <div class="login-foot">本系统仅供授权审查人员使用 · 所有操作均有审计日志</div>
  </div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Page 2: 评审任务列表
# ═══════════════════════════════════════════════════════════════════
def page02_task_list() -> str:
    tasks = [
        ("RV20260807-001", "高新区智慧城市建设项目", "XX高新区管委会", "GXXQ-2026-001", "智慧城市平台建设", "completed", "completed", "2026-08-07 09:30"),
        ("RV20260807-002", "市政道路改造工程", "XX市交通运输局", "JT-2026-014", "道路施工总承包", "completed", "in_progress", "2026-08-07 10:15"),
        ("RV20260806-005", "医疗器械采购", "XX市卫健委", "WSJKW-2026-008", "医疗设备集中采购", "in_progress", "in_progress", "2026-08-06 14:00"),
        ("RV20260806-003", "校园安防系统", "XX市教育局", "JYJ-2026-005", "安防设备与安装", "failed", "failed", "2026-08-06 09:00"),
        ("RV20260805-012", "供水管网改造", "XX市水务集团", "SW-2026-003", "管道材料及施工", "completed", "completed", "2026-08-05 16:20"),
        ("RV20260805-008", "办公楼装修工程", "XX机关事务管理局", "JGSW-2026-006", "室内装修施工", "completed", "completed", "2026-08-05 11:00"),
    ]
    status_map = {
        "completed": ("s3", "已完成"),
        "in_progress": ("s4", "进行中"),
        "failed": ("s1", "失败"),
    }
    step_map = {"prepare": "准备资料", "detect": "检测中", "result": "查看结果", "completed": "已完成", "failed": "已失败", "in_progress": "检测中"}

    rows = ""
    for sn, name, org, code, sec_name, rev_status, step, time in tasks:
        s_cls, s_label = status_map[rev_status]
        step_label = "查看结果" if rev_status == "completed" else "检测中" if step == "in_progress" else "已失败"
        rows += f"""<tr>
<td style="font-weight:500">{name}</td>
<td>{org}</td>
<td><span class="code">{code}</span></td>
<td style="color:var(--sub)">{sec_name}</td>
<td><span class="stage {s_cls}">{s_label}</span></td>
<td style="color:var(--sub);font-size:12.5px">{step_label}</td>
<td class="num" style="color:var(--sub);font-size:12px">{time}</td>
<td>
  <div style="display:flex;gap:4px;justify-content:center">
    <button class="link-btn">进入</button>
    <button class="link-btn" style="color:var(--warn)">编辑</button>
    <button class="link-btn" style="color:var(--danger)">删除</button>
  </div>
</td></tr>"""

    content = f"""
<div class="sec-h"><svg class="ic"><use href="#i-list"/></svg><b>评审任务列表</b>
  <span class="count">共 24 个任务</span>
</div>
<div class="flex mb-4" style="justify-content:space-between">
  <div class="flex gap-2">
    <input style="height:36px;width:240px;padding:0 12px;border:1px solid var(--line);border-radius:var(--r-field);font-size:13px;background:#fff"
           placeholder="搜索任务名称 / 标段编号…" />
    <button class="ghost"><svg class="ic"><use href="#i-filter"/></svg>筛选</button>
  </div>
  <div class="flex gap-2">
    <button class="ghost"><svg class="ic"><use href="#i-download"/></svg>导出</button>
    <button class="primary-btn"><svg class="ic"><use href="#i-plus"/></svg>新增评审任务</button>
  </div>
</div>

<div class="kpi-panel mb-4">
  <div class="ph"><svg class="ic"><use href="#i-chart"/></svg><b>任务概览</b><span class="meta">本月数据</span></div>
  <div class="kgrid" style="grid-template-columns:repeat(4,1fr)">
    <div class="k"><div class="lbl">总任务数</div><div class="val">24</div><div class="dlt">较上月 +6</div></div>
    <div class="k"><div class="lbl">进行中</div><div class="val warn">3</div><div class="dlt">围串标检测中</div></div>
    <div class="k"><div class="lbl">已完成</div><div class="val ok">18</div><div class="dlt">检出异常 7 件</div></div>
    <div class="k"><div class="lbl">检出风险率</div><div class="val bad">38.9%</div><div class="dlt">高风险 3 件</div></div>
  </div>
</div>

<div class="card">
  <div class="card-h">
    <svg class="ic"><use href="#i-folder"/></svg><b>任务列表</b>
    <div class="right" style="display:flex;gap:8px;align-items:center">
      <select style="height:28px;padding:0 8px;border:1px solid var(--line);border-radius:var(--r-item);font-size:12px;background:#fff;color:var(--sub)">
        <option>全部状态</option><option>已完成</option><option>进行中</option><option>失败</option>
      </select>
    </div>
  </div>
  <div class="tbl-wrap" style="border:none;border-radius:0">
    <table>
      <thead><tr>
        <th>任务名称</th><th>招标人</th><th>标段编号</th><th>标段名称</th>
        <th style="text-align:center">评审状态</th><th style="text-align:center">当前步骤</th>
        <th>创建时间</th><th style="text-align:center;width:160px">操作</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div class="card-h" style="border-top:1px solid var(--line-soft);border-bottom:none;justify-content:space-between">
    <span style="font-size:12.5px;color:var(--sub)">显示 1–6 / 共 24 条</span>
    <div style="display:flex;gap:6px">
      <button class="icon-btn" style="width:28px;height:28px"><svg class="ic" style="width:12px"><use href="#i-chev-r"/></svg></button>
      <button class="ghost" style="background:var(--primary-weak-2);border-color:var(--primary-line-hover);color:var(--primary)">1</button>
      <button class="ghost">2</button>
      <button class="ghost">3</button>
      <button class="ghost">4</button>
      <button class="icon-btn" style="width:28px;height:28px"><svg class="ic" style="width:12px;transform:scaleX(-1)"><use href="#i-chev-r"/></svg></button>
    </div>
  </div>
</div>
"""
    return page_wrap("评审任务列表 · 围标串标检测系统", content, "tasks")


# ═══════════════════════════════════════════════════════════════════
# Page 3: 任务详情 - 准备阶段
# ═══════════════════════════════════════════════════════════════════
def page03_prepare() -> str:
    bidders = [
        ("01", "中铁建工集团有限公司", "商务标.pdf · 技术标.pdf · 报价标.pdf", True),
        ("02", "华西建设股份有限公司", "商务标.pdf · 技术标.pdf · 报价标.pdf", True),
        ("03", "宏达建设集团有限公司", "商务标.pdf · 技术标.pdf · 报价标.pdf", True),
        ("04", "正阳工程有限公司", "商务标.pdf · 技术标.pdf", True),
        ("05", "新兴建设开发总公司", "商务标.pdf · 技术标.pdf · 报价标.pdf", True),
    ]
    bidder_rows = ""
    for sn, name, files, ok in bidders:
        bidder_rows += f"""<div class="row">
  <div class="body">
    <div class="l1">
      <span class="code">{sn}</span>
      <span class="name">{name}</span>
      <span class="pill ok">已就绪</span>
    </div>
    <div class="l2">{files}</div>
  </div>
  <button class="ghost" style="flex:none"><svg class="ic"><use href="#i-file"/></svg>查看文件</button>
  <button class="ghost" style="flex:none;color:var(--danger);border-color:var(--danger-weak)">移除</button>
</div>"""

    content = f"""
<div class="sec-h" style="margin-top:0">
  <svg class="ic"><use href="#i-folder"/></svg>
  <b>高新区智慧城市建设项目</b>
  <span class="code">GXXQ-2026-001</span>
</div>

<div class="stepper mb-6">
  <div class="step active"><div class="dot">1</div><div class="label">准备资料</div></div>
  <div class="step-line"></div>
  <div class="step"><div class="dot">2</div><div class="label">围串标检测</div></div>
  <div class="step-line"></div>
  <div class="step"><div class="dot">3</div><div class="label">查看结果</div></div>
</div>

<div class="grid-2 mb-4">
  <div class="card">
    <div class="card-h">
      <svg class="ic"><use href="#i-doc"/></svg><b>招标文件</b>
      <span class="meta">· 招标人：XX高新区管委会</span>
    </div>
    <div style="padding:18px">
      <div class="flex" style="border:1.5px dashed var(--line);border-radius:var(--r-field);padding:24px;justify-content:center;flex-direction:column;text-align:center;cursor:pointer;transition:border-color .15s"
           onmouseover="this.style.borderColor='var(--primary-line-hover)'" onmouseout="this.style.borderColor='var(--line)'">
        <svg class="ic" style="width:32px;height:32px;color:var(--faint);margin-bottom:8px"><use href="#i-upload"/></svg>
        <span style="font-size:14px;font-weight:500;color:var(--sub)">拖放或点击上传招标文件</span>
        <span style="font-size:12px;color:var(--faint);margin-top:4px">支持 PDF / DOC / DOCX / XLSX</span>
      </div>
      <div class="row" style="border:1px solid var(--line);border-radius:var(--r-item);margin-top:12px;padding:10px 14px">
        <svg class="ic" style="color:var(--danger);flex:none"><use href="#i-pdf"/></svg>
        <div class="body">
          <div class="l1"><span class="name" style="font-size:13px">高新区智慧城市招标文件.pdf</span></div>
          <div class="l2" style="margin-top:2px">2.4 MB · 已解析完成</div>
        </div>
        <span class="pill ok">已上传</span>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-h">
      <svg class="ic"><use href="#i-users"/></svg><b>投标人列表</b>
      <span class="meta">· 5 家</span>
      <button class="ghost right-ml" style="height:26px"><svg class="ic" style="width:12px"><use href="#i-plus"/></svg>添加</button>
    </div>
    {bidder_rows}
  </div>
</div>

<div class="card">
  <div class="card-h">
    <svg class="ic"><use href="#i-settings"/></svg><b>检测选项</b>
    <span class="meta">· 选择本次需要执行的检测类型</span>
  </div>
  <div style="padding:18px;display:flex;gap:12px;flex-wrap:wrap">
    <div style="border:1.5px solid var(--primary);border-radius:var(--r-panel);padding:16px 20px;width:280px;background:var(--primary-weak-2);cursor:pointer">
      <div class="flex" style="justify-content:space-between"><b style="font-size:14px">围串标检测</b><svg class="ic" style="color:var(--primary)"><use href="#i-check"/></svg></div>
      <p style="font-size:12.5px;color:var(--sub);margin-top:6px">人员关联、IP/MAC、报价规律、文件模板等 6 项交叉分析</p>
    </div>
    <div style="border:1.5px solid var(--primary);border-radius:var(--r-panel);padding:16px 20px;width:280px;background:var(--primary-weak-2);cursor:pointer">
      <div class="flex" style="justify-content:space-between"><b style="font-size:14px">投标文件检测</b><svg class="ic" style="color:var(--primary)"><use href="#i-check"/></svg></div>
      <p style="font-size:12.5px;color:var(--sub);margin-top:6px">文档文本相似度、表格雷同、图片复用等深度比对</p>
    </div>
    <div style="border:1.5px dashed var(--line);border-radius:var(--r-panel);padding:16px 20px;width:280px;cursor:pointer">
      <div class="flex" style="justify-content:space-between"><b style="font-size:14px;color:var(--sub)">招标文件审查</b><svg class="ic" style="color:var(--faint)"><use href="#i-plus"/></svg></div>
      <p style="font-size:12.5px;color:var(--faint);margin-top:6px">AI 审查招标文件公平性、排他性条款</p>
    </div>
  </div>
</div>

<div class="flex mt-6" style="justify-content:flex-end;gap:8px">
  <button class="ghost" style="height:38px">保存草稿</button>
  <button class="primary-btn" style="height:38px">下一步：开始检测
    <svg class="ic"><use href="#i-arrow-r"/></svg></button>
</div>
"""
    return page_wrap("准备资料 · 高新区智慧城市建设项目", content, "tasks")


# ═══════════════════════════════════════════════════════════════════
# Page 4: 任务详情 - 检测中心
# ═══════════════════════════════════════════════════════════════════
def page04_detect() -> str:
    def detect_card(icon, title, desc, status, progress, items_done, color):
        status_map = {
            "running": ("s4", "检测中", "var(--primary)"),
            "completed": ("s3", "已完成", "var(--ok)"),
            "pending": ("s5", "待启动", "var(--violet)"),
        }
        s_cls, s_label, s_color = status_map[status]
        bar = f"""
        <div class="progress-track mt-3"><div class="progress-fill" style="width:{progress}%;background:{s_color}"></div></div>
        <div class="flex mt-2" style="justify-content:space-between">
          <span style="font-size:12px;color:var(--sub)">{items_done} 项已完成</span>
          <span style="font-size:12px;font-family:var(--mono);color:var(--sub)">{progress}%</span>
        </div>"""
        btn = ""
        if status == "running":
            btn = f'<button class="ghost" style="border-color:var(--danger-weak);color:var(--danger)"><svg class="ic"><use href="#i-stop"/></svg>停止</button>'
        elif status == "completed":
            btn = '<button class="ghost"><svg class="ic"><use href="#i-refresh"/></svg>重新检测</button>'
        else:
            btn = '<button class="primary-btn"><svg class="ic"><use href="#i-play"/></svg>启动检测</button>'

        return f"""<div class="card">
  <div class="card-h">
    <svg class="ic" style="color:{s_color}"><use href="#{icon}"/></svg>
    <b>{title}</b>
    <span class="stage {s_cls}">{s_label}</span>
    <div class="right">{btn}</div>
  </div>
  <div style="padding:16px 18px">
    <p style="font-size:13px;color:var(--sub)">{desc}</p>
    {bar}
  </div>
</div>"""

    content = f"""
<div class="sec-h" style="margin-top:0">
  <svg class="ic"><use href="#i-shield"/></svg>
  <b>高新区智慧城市建设项目</b>
  <span class="code">GXXQ-2026-001</span>
  <span class="stage s4 right-ml">检测进行中</span>
</div>

<div class="stepper mb-6">
  <div class="step done"><div class="dot"><svg class="ic" style="width:14px"><use href="#i-check"/></svg></div><div class="label">准备资料</div></div>
  <div class="step-line done"></div>
  <div class="step active"><div class="dot">2</div><div class="label">围串标检测</div></div>
  <div class="step-line"></div>
  <div class="step"><div class="dot">3</div><div class="label">查看结果</div></div>
</div>

<div class="status-bar mb-4">
  <span class="tag run"><svg class="ic" style="width:13px"><use href="#i-clock"/></svg>检测中</span>
  <span class="txt">围串标检测 <b>75%</b> · 投标文件检测 <b>40%</b> · 招标审查 <b>待启动</b></span>
  <span class="spacer"></span>
  <span class="num">已运行 12 分 30 秒</span>
</div>

<div class="grid-3">
  {detect_card("i-shield", "围串标检测", "人员关联分析、IP/MAC地址、报价规律、文件模板、时间戳、作者痕迹 6 项交叉检测", "running", 75, "5 / 6", "var(--primary)")}
  {detect_card("i-doc", "投标文件检测", "文档文本相似度、表格雷同、图片复用、错别字一致性等深度比对分析", "running", 40, "4 / 10", "var(--primary)")}
  {detect_card("i-scale", "招标文件审查", "AI 审查招标文件公平性、排他性条款、倾向性评分标准", "pending", 0, "0 / 15", "var(--violet)")}
</div>

<div class="sec-h"><svg class="ic"><use href="#i-list"/></svg><b>检测日志</b></div>
<div class="card">
  <div style="padding:14px 18px;font-family:var(--mono);font-size:12px;line-height:2;color:var(--sub);background:#fafbfd">
    <div><span style="color:var(--ok)">[完成]</span> CARD_01 人员关联分析 — 检出高风险 2 组</div>
    <div><span style="color:var(--ok)">[完成]</span> CARD_02 IP/MAC地址分析 — 检出中风险 1 组</div>
    <div><span style="color:var(--ok)">[完成]</span> CARD_03 报价规律检测 — 未发现异常</div>
    <div><span style="color:var(--ok)">[完成]</span> CARD_04 文件模板分析 — 检出高风险 1 组</div>
    <div><span style="color:var(--ok)">[完成]</span> CARD_05 时间戳异常 — 未发现异常</div>
    <div><span style="color:var(--primary)">[运行]</span> CARD_06 作者痕迹比对 — 分析中…</div>
    <div><span style="color:var(--primary)">[运行]</span> 投标文件相似度检测 — 文本对比阶段 (4/10)</div>
    <div style="color:var(--faint)">[等待] 招标文件审查 — 等待手动启动</div>
  </div>
</div>

<div class="flex mt-6" style="justify-content:space-between">
  <button class="ghost"><svg class="ic"><use href="#i-arrow-r"/></svg>返回准备页</button>
  <button class="ghost" style="opacity:.5;cursor:not-allowed" disabled>等待检测完成…</button>
</div>
"""
    return page_wrap("围串标检测 · 高新区智慧城市建设项目", content, "tasks")


# ═══════════════════════════════════════════════════════════════════
# Page 5: 围串标检测结果
# ═══════════════════════════════════════════════════════════════════
def page05_collusion_result() -> str:
    cards = [
        ("CARD_01", "人员关联分析", "检测跨投标人是否存在相同作者、修改者、批注者等人员痕迹", [
            ("01 中铁建工集团有限公司", "high", "作者「张明」与投标人03、04一致", 0.92),
            ("03 宏达建设集团有限公司", "high", "作者「张明」与投标人01一致", 0.92),
            ("04 正阳工程有限公司", "high", "作者「张明」与投标人01一致", 0.92),
            ("02 华西建设股份有限公司", "none", "未发现人员关联", None),
        ]),
        ("CARD_02", "IP/MAC地址分析", "检测投标文件创建/修改的硬件环境是否重合", [
            ("03 宏达建设集团有限公司", "medium", "MAC地址与投标人04部分匹配", 0.65),
            ("04 正阳工程有限公司", "medium", "MAC地址与投标人03部分匹配", 0.65),
        ]),
        ("CARD_04", "文件模板分析", "检测投标文件是否使用相同的文档模板创建", [
            ("03 宏达建设集团有限公司", "high", "技术标使用「通用投标模板V3.dotx」与投标人04一致", 0.88),
            ("04 正阳工程有限公司", "high", "技术标使用「通用投标模板V3.dotx」与投标人03一致", 0.88),
        ]),
    ]
    risk_tag = {
        "high": ("s1", "高风险"),
        "medium": ("s2", "中风险"),
        "low": ("s4", "低风险"),
        "none": ("s3", "无风险"),
    }

    sections = ""
    for code, title, desc, details in cards:
        detail_rows = ""
        for bidder, risk, summary, score in details:
            s_cls, s_label = risk_tag[risk]
            score_html = f'<span class="num">{score*100:.0f}%</span>' if score else '<span style="color:var(--faint)">—</span>'
            detail_rows += f"""<tr>
<td style="font-weight:500">{bidder}</td>
<td><span class="stage {s_cls}">{s_label}</span></td>
<td style="color:var(--sub)">{summary}</td>
<td style="text-align:center">{score_html}</td>
</tr>"""
        sections += f"""<div class="card mb-3">
  <div class="card-h">
    <span class="code">{code}</span>
    <b>{title}</b>
    <span class="meta">· {desc}</span>
  </div>
  <div class="tbl-wrap" style="border:none;border-radius:0">
    <table><thead><tr>
      <th>投标人</th><th style="text-align:center;width:80px">风险等级</th>
      <th>检测结果</th><th style="text-align:center;width:70px">相似度</th>
    </tr></thead><tbody>{detail_rows}</tbody></table>
  </div>
</div>"""

    content = f"""
<div class="flex" style="justify-content:space-between;align-items:flex-start;margin-top:0">
  <div>
    <div class="kicker"><b>高新区智慧城市建设项目</b> · <span class="code">GXXQ-2026-001</span></div>
    <h2 style="margin-top:4px">围串标检测结果</h2>
  </div>
  <div class="flex gap-2">
    <button class="ghost"><svg class="ic"><use href="#i-refresh"/></svg>刷新</button>
    <button class="primary-btn"><svg class="ic"><use href="#i-download"/></svg>一键导出评审结果</button>
  </div>
</div>

<div class="kpi-panel mt-4 mb-4">
  <div class="ph">
    <svg class="ic"><use href="#i-shield"/></svg>
    <b>围标串标风险概览</b>
    <span class="meta">基于文档元数据 · 文件内容 · 环境信息交叉比对</span>
  </div>
  <div class="kgrid" style="grid-template-columns:repeat(4,1fr)">
    <div class="k"><div class="lbl">高风险组</div><div class="val bad">2</div><div class="dlt">涉及 4 家投标人</div></div>
    <div class="k"><div class="lbl">中风险组</div><div class="val warn">1</div><div class="dlt">涉及 2 家投标人</div></div>
    <div class="k"><div class="lbl">无风险</div><div class="val ok">1</div><div class="dlt">华西建设</div></div>
    <div class="k"><div class="lbl">检测覆盖</div><div class="val">6/6</div><div class="dlt">全部检测项已完成</div></div>
  </div>
</div>

<div class="card mb-4" style="border-left:3px solid var(--danger)">
  <div class="card-h">
    <svg class="ic" style="color:var(--danger)"><use href="#i-alert"/></svg>
    <b style="color:var(--danger)">疑似围标组A</b>
    <span class="meta">· 投标人 01、03、04 — 作者「张明」</span>
    <span class="stage s1 right-ml">高风险</span>
  </div>
  <div style="padding:14px 18px">
    <p style="font-size:13.5px;color:var(--ink)">三家投标人的投标文件作者均为<b>「张明」</b>，修改者均为<b>「张明」</b>，技术标文档共用同一模板<b>「通用投标模板V3.dotx」</b>。投标人03与04的 MAC 地址存在部分匹配。</p>
    <div class="flex gap-2 mt-3">
      <span class="code">01 中铁建工集团</span>
      <span class="code">03 宏达建设集团</span>
      <span class="code">04 正阳工程</span>
      <span class="pill danger">作者一致</span>
      <span class="pill danger">模板一致</span>
    </div>
  </div>
</div>

{sections}
"""
    return page_wrap("围串标检测结果 · 高新区智慧城市建设项目", content, "tasks")


# ═══════════════════════════════════════════════════════════════════
# Page 6: 投标文件检测详情
# ═══════════════════════════════════════════════════════════════════
def page06_file_check() -> str:
    pairs = [
        ("03 宏达建设", "04 正阳工程", "技术标", "high", "施工组织设计文本相似度极高，含相同错别字「按装」", 0.917, "12 处雷同段落"),
        ("03 宏达建设", "04 正阳工程", "报价标", "medium", "报价表数据结构一致，部分单价接近", 0.72, "8 项相似"),
        ("01 中铁建工", "03 宏达建设", "商务标", "high", "营业执照扫描件像素级一致", 0.985, "同一图片文件"),
        ("01 中铁建工", "04 正阳工程", "商务标", "high", "资质证书为同一扫描件", 0.96, "同一图片文件"),
        ("02 华西建设", "05 新兴建设", "技术标", "low", "部分施工方案措辞相似（常见表述）", 0.31, "3 处类似"),
    ]
    risk_map = {"high": ("s1", "高"), "medium": ("s2", "中"), "low": ("s4", "低")}
    pair_rows = ""
    for a, b, doc_type, risk, summary, score, detail in pairs:
        s_cls, s_label = risk_map[risk]
        bar_color = "var(--danger)" if score > 0.85 else "var(--warn)" if score > 0.5 else "var(--ok)"
        pair_rows += f"""<tr>
<td><span class="code">{a}</span><br><span style="color:var(--faint);font-size:11px">vs</span><br><span class="code">{b}</span></td>
<td><span class="pill neutral">{doc_type}</span></td>
<td><span class="stage {s_cls}">{s_label}风险</span></td>
<td>{summary}<br><span style="font-size:11.5px;color:var(--faint)">{detail}</span></td>
<td style="text-align:center">
  <div style="display:flex;align-items:center;gap:8px;justify-content:center">
    <div class="progress-track" style="width:60px"><div class="progress-fill" style="width:{score*100:.0f}%;background:{bar_color}"></div></div>
    <span class="num" style="font-weight:600;color:{bar_color}">{score*100:.1f}%</span>
  </div>
</td>
<td style="text-align:center"><button class="link-btn">详情</button></td>
</tr>"""

    content = f"""
<div class="flex" style="justify-content:space-between;align-items:flex-start">
  <div>
    <div class="kicker"><b>高新区智慧城市建设项目</b> · <span class="code">GXXQ-2026-001</span></div>
    <h2 style="margin-top:4px">投标文件检测结果</h2>
  </div>
  <button class="ghost"><svg class="ic"><use href="#i-download"/></svg>导出报告</button>
</div>

<div class="grid-4 mt-4 mb-4">
  <div class="card" style="padding:18px">
    <div style="font-size:12px;color:var(--sub)">检测投标对数</div>
    <div style="font-family:var(--mono);font-size:26px;font-weight:700;margin-top:4px">10</div>
    <div style="font-size:11.5px;color:var(--faint);margin-top:2px">5 家投标人 × C(5,2)</div>
  </div>
  <div class="card" style="padding:18px;border-left:3px solid var(--danger)">
    <div style="font-size:12px;color:var(--sub)">高风险对</div>
    <div style="font-family:var(--mono);font-size:26px;font-weight:700;margin-top:4px;color:var(--danger)">3</div>
    <div style="font-size:11.5px;color:var(--faint);margin-top:2px">相似度 > 85%</div>
  </div>
  <div class="card" style="padding:18px;border-left:3px solid var(--warn)">
    <div style="font-size:12px;color:var(--sub)">中风险对</div>
    <div style="font-family:var(--mono);font-size:26px;font-weight:700;margin-top:4px;color:var(--warn)">1</div>
    <div style="font-size:11.5px;color:var(--faint);margin-top:2px">相似度 50–85%</div>
  </div>
  <div class="card" style="padding:18px;border-left:3px solid var(--ok)">
    <div style="font-size:12px;color:var(--sub)">低风险对</div>
    <div style="font-family:var(--mono);font-size:26px;font-weight:700;margin-top:4px;color:var(--ok)">1</div>
    <div style="font-size:11.5px;color:var(--faint);margin-top:2px">相似度 < 50%</div>
  </div>
</div>

<div class="sec-h">
  <svg class="ic"><use href="#i-scale"/></svg><b>相似度对比明细</b>
  <span class="count">共 10 组检测对 · 显示有风险的 5 组</span>
</div>
<div class="card">
  <div class="tbl-wrap" style="border:none;border-radius:0">
    <table>
      <thead><tr>
        <th style="width:140px">投标人对比</th>
        <th style="width:80px">文件类型</th>
        <th style="text-align:center;width:80px">风险</th>
        <th>检测结果</th>
        <th style="text-align:center;width:130px">相似度</th>
        <th style="text-align:center;width:70px">操作</th>
      </tr></thead>
      <tbody>{pair_rows}</tbody>
    </table>
  </div>
</div>

<div class="card mt-4">
  <div class="card-h">
    <svg class="ic"><use href="#i-file"/></svg><b>综合检测报告</b>
    <span class="meta">· 按投标人生成独立 PDF 报告</span>
    <span class="stage s3 right-ml">报告已生成</span>
  </div>
  <div style="padding:14px 18px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
""" + "\n".join(f"""<div style="display:flex;align-items:center;gap:10px;padding:12px;border:1px solid var(--line);border-radius:var(--r-item)">
  <svg class="ic" style="color:var(--danger)"><use href="#i-pdf"/></svg>
  <div style="flex:1;min-width:0">
    <div style="font-size:13px;font-weight:500">{n}</div>
    <div style="font-size:11.5px;color:var(--faint)">报告已生成 · 340 KB</div>
  </div>
  <button class="link-btn"><svg class="ic"><use href="#i-download"/></svg></button>
</div>""" for n in ["中铁建工集团","华西建设","宏达建设集团","正阳工程","新兴建设"]) + """
  </div>
</div>
"""
    return page_wrap("投标文件检测 · 高新区智慧城市建设项目", content, "tasks")


# ═══════════════════════════════════════════════════════════════════
# Page 7: 招标文件审查结果
# ═══════════════════════════════════════════════════════════════════
def page07_tender_check() -> str:
    cards_data = [
        ("一", "公平性审查", "审查招标文件是否存在歧视性、排他性条款", [
            ("1.1", "资质门槛审查", "medium", "要求投标人具备「智慧城市专项设计甲级」资质，该资质持证机构较少，存在排他性嫌疑", "偏高"),
            ("1.2", "业绩要求审查", "low", "要求近三年内承担过类似项目，业绩金额门槛合理", "合理"),
            ("1.3", "财务能力审查", "none", "财务指标设置符合行业常规，无排他性", "合理"),
        ]),
        ("二", "技术条款审查", "审查技术参数是否存在倾向性", [
            ("2.1", "品牌指定审查", "high", "技术参数中出现「华为」「海康威视」等特定品牌名称，未使用「或同等品牌」表述", "严重"),
            ("2.2", "技术规格审查", "medium", "部分接口协议要求超出项目实际需求，可能限制潜在投标人", "偏高"),
            ("2.3", "评分标准审查", "low", "主观评分项权重 15%，在合理范围内", "合理"),
        ]),
    ]
    risk_map = {"high": ("s1", "严重偏差"), "medium": ("s2", "需关注"), "low": ("s4", "轻微"), "none": ("s3", "合规")}

    sections = ""
    for card_no, title, desc, items in cards_data:
        item_rows = ""
        for sn, item_title, risk, finding, level in items:
            s_cls, s_label = risk_map[risk]
            item_rows += f"""<div class="row">
  <div class="body">
    <div class="l1">
      <span class="code">{sn}</span>
      <span class="name">{item_title}</span>
      <span class="stage {s_cls}">{s_label}</span>
    </div>
    <div class="l2">{finding}</div>
    <div class="l2 mt-1"><em>偏离程度：</em><b style="color:{'var(--danger)' if risk=='high' else 'var(--warn)' if risk=='medium' else 'var(--sub)'}">{level}</b></div>
  </div>
</div>"""
        sections += f"""<div class="card mb-3">
  <div class="card-h">
    <span class="code">{card_no}</span>
    <b>{title}</b>
    <span class="meta">· {desc}</span>
  </div>
  {item_rows}
</div>"""

    content = f"""
<div class="flex" style="justify-content:space-between;align-items:flex-start">
  <div>
    <div class="kicker"><b>高新区智慧城市建设项目</b> · <span class="code">GXXQ-2026-001</span></div>
    <h2 style="margin-top:4px">招标文件审查结果</h2>
    <p class="lede">基于 AI 大模型对招标文件逐条审查，检查公平性、排他性、倾向性等维度</p>
  </div>
  <button class="ghost"><svg class="ic"><use href="#i-download"/></svg>导出审查报告</button>
</div>

<div class="grid-3 mt-4 mb-4">
  <div class="card" style="padding:18px;border-left:3px solid var(--danger)">
    <div style="font-size:12px;color:var(--sub)">严重偏差</div>
    <div style="font-family:var(--mono);font-size:26px;font-weight:700;margin-top:4px;color:var(--danger)">1</div>
  </div>
  <div class="card" style="padding:18px;border-left:3px solid var(--warn)">
    <div style="font-size:12px;color:var(--sub)">需关注</div>
    <div style="font-family:var(--mono);font-size:26px;font-weight:700;margin-top:4px;color:var(--warn)">2</div>
  </div>
  <div class="card" style="padding:18px;border-left:3px solid var(--ok)">
    <div style="font-size:12px;color:var(--sub)">合规项</div>
    <div style="font-family:var(--mono);font-size:26px;font-weight:700;margin-top:4px;color:var(--ok)">2</div>
  </div>
</div>

<div class="card mb-4" style="border-left:3px solid var(--danger)">
  <div class="card-h">
    <svg class="ic" style="color:var(--danger)"><use href="#i-warn"/></svg>
    <b style="color:var(--danger)">审查结论</b>
    <span class="stage s1 right-ml">存在排他性条款</span>
  </div>
  <div style="padding:14px 18px">
    <p style="font-size:13.5px;color:var(--ink)">招标文件在技术参数中<b style="color:var(--danger)">指定了特定品牌</b>（华为、海康威视），且资质门槛设置偏高，建议修改为「或不低于同等品牌」的表述，并适当放宽资质要求。</p>
  </div>
</div>

{sections}
"""
    return page_wrap("招标文件审查 · 高新区智慧城市建设项目", content, "tasks")


# ═══════════════════════════════════════════════════════════════════
# Page 8: 文档元数据核验
# ═══════════════════════════════════════════════════════════════════
def page08_metadata() -> str:
    bidders = [
        (1, "中铁建工集团", "张明", "张明", "宏达建设集团", "Word 2019", "模板A.dotx", "2026-07-15 09:30", "2026-07-16 14:20", "danger", [3, 4]),
        (2, "华西建设", "李伟", "王芳", "华西建设", "WPS Office", "无", "2026-07-12 10:00", "2026-07-14 16:45", "ok", []),
        (3, "宏达建设集团", "张明", "张明", "宏达建设集团", "Word 2019", "模板A.dotx", "2026-07-15 09:30", "2026-07-16 14:20", "danger", [1, 4]),
        (4, "正阳工程", "张明", "刘洋", "正阳工程", "Word 2019", "模板A.dotx", "2026-07-15 09:30", "2026-07-17 11:00", "danger", [1, 3]),
        (5, "新兴建设", "赵强", "赵强", "新兴建设", "LibreOffice", "无", "2026-07-13 08:00", "2026-07-15 10:30", "ok", []),
    ]

    # Risk highlight cells
    def cell(val, danger_ids, current_id, field_label):
        is_danger = current_id in danger_ids
        if is_danger:
            return f'<td style="color:var(--danger);font-weight:600">{val}</td>'
        return f'<td>{val}</td>'

    meta_rows = ""
    for bid, name, author, lmb, org, app, template, created, modified, risk, linked in bidders:
        author_cls = ' style="color:var(--danger);font-weight:600;background:var(--danger-weak)"' if bid in [1,3,4] else ''
        template_cls = ' style="color:var(--danger);font-weight:600;background:var(--danger-weak)"' if bid in [1,3,4] else ''
        created_cls = ' style="color:var(--danger);font-weight:600;background:var(--danger-weak)"' if bid in [1,3,4] else ''
        risk_cls = {"danger": "s1", "ok": "s3"}
        risk_label = {"danger": "高风险", "ok": "无异常"}
        meta_rows += f"""<tr>
<td><span class="code">{bid:02d}</span></td>
<td style="font-weight:500">{name}</td>
<td{author_cls}>{author}</td>
<td{author_cls}>{lmb}</td>
<td>{org}</td>
<td>{app}</td>
<td{template_cls}>{template}</td>
<td class="num"{created_cls}>{created}</td>
<td class="num">{modified}</td>
<td><span class="stage {risk_cls[risk]}">{risk_label[risk]}</span></td>
</tr>"""

    content = f"""
<div class="flex" style="justify-content:space-between;align-items:flex-start">
  <div>
    <div class="kicker">离线文档元数据核验 · 三链解析（原生 / Tika / ExifTool）</div>
    <h2 style="margin-top:4px">元数据交叉比对</h2>
    <p class="lede">红色标记为跨投标人重合的人员痕迹或文件模板 — 同一投标人内部的重复不会标记</p>
  </div>
  <div class="flex gap-2">
    <button class="ghost"><svg class="ic"><use href="#i-folder"/></svg>选择目录</button>
    <button class="primary-btn"><svg class="ic"><use href="#i-play"/></svg>开始核验</button>
  </div>
</div>

<div class="status-bar mt-4 mb-4">
  <span class="tag ok"><svg class="ic" style="width:13px"><use href="#i-check"/></svg>核验完成</span>
  <span class="txt"><b>5</b> 家投标人 · <b>15</b> 文件 · <b>2,075</b> 条元数据</span>
  <span class="spacer"></span>
  <span class="num">2026-08-07 10:30</span>
</div>

<div class="kpi-panel mb-4">
  <div class="ph">
    <svg class="ic"><use href="#i-fingerprint"/></svg>
    <b>元数据风险摘要</b>
    <span class="meta">跨投标人痕迹比对</span>
  </div>
  <div class="kgrid" style="grid-template-columns:repeat(4,1fr)">
    <div class="k"><div class="lbl">人员痕迹重合</div><div class="val bad">3</div><div class="dlt">作者/修改者一致</div></div>
    <div class="k"><div class="lbl">模板复用</div><div class="val bad">3</div><div class="dlt">同一 .dotx 模板</div></div>
    <div class="k"><div class="lbl">创建时间重合</div><div class="val warn">3</div><div class="dlt">精确到分钟一致</div></div>
    <div class="k"><div class="lbl">无异常投标人</div><div class="val ok">2</div><div class="dlt">华西、新兴</div></div>
  </div>
</div>

<div class="card mb-4" style="border-left:3px solid var(--danger)">
  <div class="card-h">
    <svg class="ic" style="color:var(--danger)"><use href="#i-alert"/></svg>
    <b style="color:var(--danger)">疑似围标组</b>
    <span class="meta">· 投标人 01、03、04</span>
    <div class="right-ml flex gap-2">
      <span class="pill danger">作者一致</span>
      <span class="pill danger">模板一致</span>
      <span class="pill danger">时间一致</span>
    </div>
  </div>
  <div style="padding:14px 18px">
    <p style="font-size:13.5px">三家投标人的文档作者均为<b style="color:var(--danger)">「张明」</b>，创建时间均为 <b class="num">2026-07-15 09:30</b>，使用同一模板<b style="color:var(--danger)">「模板A.dotx」</b>。证据来自三条独立解析链。</p>
  </div>
</div>

<div class="sec-h"><svg class="ic"><use href="#i-grid"/></svg><b>元数据对比表</b><span class="count">红色 = 跨投标人重合</span></div>
<div class="card">
  <div class="tbl-wrap" style="border:none;border-radius:0;overflow-x:auto">
    <table>
      <thead><tr>
        <th>#</th><th>投标人</th>
        <th>作者</th><th>最后修改者</th>
        <th>公司</th><th>应用程序</th><th>模板</th>
        <th>创建时间</th><th>修改时间</th>
        <th style="text-align:center">风险</th>
      </tr></thead>
      <tbody>{meta_rows}</tbody>
    </table>
  </div>
</div>

<div class="sec-h"><svg class="ic"><use href="#i-info"/></svg><b>证据链详情 · 投标人01</b></div>
<div class="grid-3">
  <div class="card" style="padding:16px">
    <div style="font-size:12px;color:var(--sub);margin-bottom:8px;display:flex;align-items:center;gap:6px">
      <svg class="ic" style="width:13px;color:var(--primary)"><use href="#i-shield"/></svg><b>原生解析器</b>
    </div>
    <div style="font-size:12.5px;line-height:1.8;color:var(--sub)">
      <div>作者: <b style="color:var(--ink)">张明</b></div>
      <div>修改者: <b style="color:var(--ink)">张明</b></div>
      <div>模板: <b style="color:var(--ink)">模板A.dotx</b></div>
      <div>创建: <b class="num">2026-07-15 09:30</b></div>
    </div>
  </div>
  <div class="card" style="padding:16px">
    <div style="font-size:12px;color:var(--sub);margin-bottom:8px;display:flex;align-items:center;gap:6px">
      <svg class="ic" style="width:13px;color:var(--violet)"><use href="#i-doc"/></svg><b>Apache Tika</b>
    </div>
    <div style="font-size:12.5px;line-height:1.8;color:var(--sub)">
      <div>Author: <b style="color:var(--ink)">张明</b></div>
      <div>Last-Modified-By: <b style="color:var(--ink)">张明</b></div>
      <div>Template: <b style="color:var(--ink)">模板A.dotx</b></div>
      <div>Producer: <b style="color:var(--ink)">Word 2019</b></div>
    </div>
  </div>
  <div class="card" style="padding:16px">
    <div style="font-size:12px;color:var(--sub);margin-bottom:8px;display:flex;align-items:center;gap:6px">
      <svg class="ic" style="width:13px;color:var(--teal)"><use href="#i-fingerprint"/></svg><b>ExifTool 13.55</b>
    </div>
    <div style="font-size:12.5px;line-height:1.8;color:var(--sub)">
      <div>Creator: <b style="color:var(--ink)">张明</b></div>
      <div>ModifyDate: <b class="num">2026:07:16 14:20</b></div>
      <div>CreateDate: <b class="num">2026:07:15 09:30</b></div>
      <div>Software: <b style="color:var(--ink)">Word 2019</b></div>
    </div>
  </div>
</div>
"""
    return page_wrap("元数据核验 · 围标串标检测系统", content, "metadata")


# ═══════════════════════════════════════════════════════════════════
# Page 9: 数据看板/分析中心
# ═══════════════════════════════════════════════════════════════════
def page09_dashboard() -> str:
    # bar chart data
    months = ["2月","3月","4月","5月","6月","7月"]
    values = [8, 12, 6, 15, 10, 24]
    risk_values = [2, 4, 2, 6, 3, 9]
    max_val = max(values)
    bars = ""
    for m, v, rv in zip(months, values, risk_values):
        h = int(v / max_val * 100)
        rh = int(rv / max_val * 100)
        bars += f"""<div style="display:flex;flex-direction:column;align-items:center;gap:6px;flex:1">
  <div style="font-size:11px;font-family:var(--mono);color:var(--sub)">{v}</div>
  <div style="width:100%;max-width:40px;height:120px;display:flex;flex-direction:column;justify-content:flex-end;gap:2px;position:relative">
    <div style="width:100%;height:{rh}px;background:var(--danger);border-radius:3px 3px 0 0"></div>
    <div style="width:100%;height:{h-rh}px;background:var(--primary);opacity:.3;border-radius:0 0 3px 3px"></div>
  </div>
  <div style="font-size:12px;color:var(--sub)">{m}</div>
</div>"""

    content = f"""
<div class="sec-h" style="margin-top:0"><svg class="ic"><use href="#i-chart"/></svg><b>数据看板</b><span class="count">2026 年度统计 · 截止 2026-08-07</span></div>

<div class="kpi-panel mb-4">
  <div class="ph"><svg class="ic"><use href="#i-trend"/></svg><b>年度检测概览</b><span class="meta">实时数据</span></div>
  <div class="kgrid" style="grid-template-columns:repeat(4,1fr)">
    <div class="k"><div class="lbl">累计检测任务</div><div class="val">87</div><div class="dlt">本月 +24 ↑</div></div>
    <div class="k"><div class="lbl">累计投标人</div><div class="val">412</div><div class="dlt">平均 4.7 家/任务</div></div>
    <div class="k"><div class="lbl">检出风险率</div><div class="val bad">31.2%</div><div class="dlt">高风险 11 件</div></div>
    <div class="k"><div class="lbl">平均检测时长</div><div class="val ok">8.5<span style="font-size:14px">min</span></div><div class="dlt">较上月 -1.2min</div></div>
  </div>
</div>

<div class="grid-2 mb-4">
  <div class="card">
    <div class="card-h">
      <svg class="ic"><use href="#i-chart"/></svg><b>月度检测趋势</b>
      <span class="meta">· 蓝色=总数 · 红色=风险数</span>
    </div>
    <div style="padding:24px 18px;display:flex;align-items:flex-end;gap:16px;height:200px">
      {bars}
    </div>
  </div>

  <div class="card">
    <div class="card-h">
      <svg class="ic"><use href="#i-target"/></svg><b>风险类型分布</b>
      <span class="meta">· 本月检出</span>
    </div>
    <div style="padding:18px">
""" + "\n".join(f"""      <div class="mb-3">
        <div class="flex" style="justify-content:space-between;margin-bottom:4px">
          <span style="font-size:13px;font-weight:500">{label}</span>
          <span class="num" style="font-size:12px;color:var(--sub)">{count} 件 · {pct}%</span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:{pct}%;background:{color}"></div></div>
      </div>""" for label, count, pct, color in [
        ("人员痕迹重合（作者/修改者）", 4, 44, "var(--danger)"),
        ("文件模板复用", 2, 22, "var(--warn)"),
        ("文档文本高度相似", 2, 22, "var(--violet)"),
        ("IP/MAC 地址匹配", 1, 12, "var(--primary)"),
      ]) + f"""
    </div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="card-h">
      <svg class="ic"><use href="#i-list"/></svg><b>近期高风险任务</b>
      <span class="meta">· 最近 30 天</span>
    </div>
""" + "\n".join(f"""    <div class="row">
      <div class="body">
        <div class="l1"><span class="name">{name}</span><span class="stage s1">高风险</span></div>
        <div class="l2"><span class="code">{code}</span> <em>·</em> {detail}</div>
      </div>
      <span style="font-size:12px;color:var(--sub);font-family:var(--mono);flex:none">{date}</span>
    </div>""" for name, code, detail, date in [
      ("高新区智慧城市建设项目", "GXXQ-2026-001", "3家投标人作者一致", "08-07"),
      ("市政道路改造工程", "JT-2026-014", "2家MAC地址匹配", "08-07"),
      ("医疗器械采购", "WSJKW-2026-008", "报价规律异常", "08-06"),
      ("办公楼装修工程", "JGSW-2026-006", "同一图片文件", "08-05"),
    ]) + f"""
  </div>

  <div class="card">
    <div class="card-h">
      <svg class="ic"><use href="#i-clock"/></svg><b>系统状态</b>
      <span class="stage s3 right-ml">全部正常</span>
    </div>
    <div style="padding:14px 18px">
""" + "\n".join(f"""      <div class="flex mb-3" style="justify-content:space-between">
        <div class="flex gap-2">
          <i style="width:7px;height:7px;border-radius:50%;background:var(--ok);flex:none"></i>
          <span style="font-size:13px;font-weight:500">{name}</span>
        </div>
        <span style="font-size:12px;font-family:var(--mono);color:var(--ok);font-weight:600">{status}</span>
      </div>""" for name, status in [
        ("围串标检测引擎", "正常 · 7788"),
        ("文件检测服务", "正常 · 8000"),
        ("招标文件审查模型", "正常"),
        ("OCR 文字识别服务", "已关闭"),
        ("MySQL 数据库", "正常"),
        ("Redis 缓存", "正常"),
        ("MinIO 对象存储", "正常"),
      ]) + f"""
    </div>
  </div>
</div>
"""
    return page_wrap("数据看板 · 围标串标检测系统", content, "dashboard")


# ═══════════════════════════════════════════════════════════════════
# Page 10: 评审报告导出中心
# ═══════════════════════════════════════════════════════════════════
def page10_export() -> str:
    content = f"""
<div class="flex" style="justify-content:space-between;align-items:flex-start">
  <div>
    <div class="kicker"><b>高新区智慧城市建设项目</b> · <span class="code">GXXQ-2026-001</span></div>
    <h2 style="margin-top:4px">评审报告导出</h2>
    <p class="lede">检测完成后系统自动生成各投标人独立报告，导出为 ZIP 压缩包</p>
  </div>
  <span class="stage s3">报告已就绪</span>
</div>

<div class="status-bar mt-4 mb-4">
  <span class="tag ok"><svg class="ic" style="width:13px"><use href="#i-check"/></svg>全部检测完成</span>
  <span class="txt">围串标检测 ✓ · 投标文件检测 ✓ · 招标文件审查 ✓</span>
  <span class="spacer"></span>
  <span class="num">完成于 2026-08-07 10:30</span>
</div>

<div class="grid-2 mb-4">
  <div class="card" style="border-left:3px solid var(--ok);padding:24px">
    <div class="flex gap-3">
      <div style="width:48px;height:48px;border-radius:var(--r-panel);background:#e7f6f0;display:flex;align-items:center;justify-content:center;flex:none">
        <svg class="ic" style="width:24px;height:24px;color:var(--ok)"><use href="#i-check"/></svg>
      </div>
      <div class="flex-1">
        <b style="font-size:16px">自动生成的评审结果 ZIP</b>
        <p style="font-size:13px;color:var(--sub);margin-top:4px">包含 5 份投标人 PDF 报告 + 澄清 DOCX + 澄清 XLSX</p>
        <div class="flex gap-2 mt-3">
          <span class="pill ok">完整性校验通过</span>
          <span class="code">12.4 MB</span>
        </div>
      </div>
    </div>
    <button class="primary-btn mt-4" style="width:100%;justify-content:center"><svg class="ic"><use href="#i-download"/></svg>下载评审结果 ZIP</button>
  </div>

  <div class="card" style="padding:24px">
    <b style="font-size:16px">导出选项</b>
    <p style="font-size:13px;color:var(--sub);margin-top:4px">自定义导出内容</p>
    <div class="flex-col mt-3">
""" + "\n".join(f"""      <label class="checkbox-row" style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink);cursor:pointer;padding:6px 0">
        <input type="checkbox" {chk} style="width:16px;height:16px;accent-color:var(--primary)" />
        <span>{label}</span>
        <span style="margin-left:auto;font-size:11.5px;color:var(--faint)">{size}</span>
      </label>""" for label, size, chk in [
        ("围串标检测报告（汇总）", "1.2 MB", "checked"),
        ("投标人独立 PDF 报告 ×5", "8.5 MB", "checked"),
        ("发出澄清 DOCX", "0.8 MB", "checked"),
        ("相似度审查澄清表 XLSX", "1.9 MB", "checked"),
        ("招标文件审查报告", "0.6 MB", ""),
      ]) + f"""
    </div>
    <button class="ghost mt-4" style="width:100%;justify-content:center"><svg class="ic"><use href="#i-refresh"/></svg>重新生成导出包</button>
  </div>
</div>

<div class="sec-h"><svg class="ic"><use href="#i-doc"/></svg><b>报告内容预览</b><span class="count">点击文件名预览</span></div>
<div class="card">
""" + "\n".join(f"""  <div class="row">
    <svg class="ic" style="color:var(--danger);flex:none"><use href="#{icon}"/></svg>
    <div class="body">
      <div class="l1"><span class="name">{name}</span><span class="pill {pill_cls}">{pill}</span></div>
      <div class="l2">{detail}</div>
    </div>
    <span style="font-size:12px;color:var(--sub);font-family:var(--mono);flex:none">{size}</span>
    <button class="link-btn" style="flex:none"><svg class="ic"><use href="#i-download"/></svg>下载</button>
  </div>""" for icon, name, pill_cls, pill, detail, size in [
    ("i-pdf", "围串标检测汇总报告.pdf", "danger", "高风险", "3家投标人疑似围标 · 6项检测 · 2组高风险", "1.2 MB"),
    ("i-pdf", "中铁建工集团_检测报告.pdf", "danger", "高风险", "作者「张明」跨投标人一致 · 模板复用", "1.8 MB"),
    ("i-pdf", "宏达建设集团_检测报告.pdf", "danger", "高风险", "作者「张明」· MAC部分匹配 · 模板复用", "1.7 MB"),
    ("i-pdf", "正阳工程_检测报告.pdf", "danger", "高风险", "作者「张明」· 模板复用 · 文件相似度91.7%", "1.7 MB"),
    ("i-pdf", "华西建设_检测报告.pdf", "ok", "无异常", "未发现围标痕迹", "1.5 MB"),
    ("i-pdf", "新兴建设_检测报告.pdf", "ok", "无异常", "未发现围标痕迹", "1.6 MB"),
    ("i-file", "澄清通知_中铁建工集团.docx", "neutral", "DOCX", "需澄清：作者来源说明", "0.3 MB"),
    ("i-file", "相似度审查澄清表.xlsx", "neutral", "XLSX", "5组对比明细 · 含高亮标注", "1.9 MB"),
  ]) + f"""
</div>

<div class="card mt-4" style="border-left:3px solid var(--primary)">
  <div class="card-h">
    <svg class="ic" style="color:var(--primary)"><use href="#i-info"/></svg>
    <b>导出说明</b>
  </div>
  <div style="padding:14px 18px;font-size:13px;color:var(--sub);line-height:1.8">
    <p>• ZIP 包内含完整性清单 (SHA-256)，用于校验文件完整性</p>
    <p>• 投标人 PDF 报告独立生成，不含其他投标人信息</p>
    <p>• 澄清 DOCX 中的错别字/标点以黄底红字标记，不含建议修改</p>
    <p>• 评审结果仅供内部审查使用，请勿对外传播</p>
  </div>
</div>
"""
    return page_wrap("评审报告导出 · 高新区智慧城市建设项目", content, "tasks")


# ═══════════════════════════════════════════════════════════════════
# Index page
# ═══════════════════════════════════════════════════════════════════
def index_page(pages: list[tuple[str, str, str]]) -> str:
    items = ""
    for i, (fname, title, desc) in enumerate(pages, 1):
        items += f"""<a href="{fname}" class="idx-card">
  <div class="idx-no">{i:02d}</div>
  <div class="idx-body">
    <div class="idx-title">{title}</div>
    <div class="idx-desc">{desc}</div>
  </div>
  <svg class="ic" style="width:18px;color:var(--faint)"><use href="#i-arrow-r"/></svg>
</a>"""

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>围标串标检测 · 10套企业页面原型</title>
<style>{CSS}
.idx-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:20px}}
.idx-card{{display:flex;align-items:center;gap:14px;padding:18px 20px;background:#fff;border:1px solid var(--line);
  border-radius:var(--r-card);text-decoration:none;transition:border-color .15s,box-shadow .15s}}
.idx-card:hover{{border-color:var(--primary-line-hover);box-shadow:var(--sh-float)}}
.idx-no{{width:36px;height:36px;border-radius:var(--r-btn);background:var(--primary-weak);color:var(--primary);
  font-family:var(--mono);font-size:14px;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none}}
.idx-body{{flex:1;min-width:0}}
.idx-title{{font-size:15px;font-weight:600;color:var(--ink)}}
.idx-desc{{font-size:12.5px;color:var(--sub);margin-top:2px}}
</style></head><body>
{ICONS}
<div class="wash"></div>
<header class="hdr">
  <div class="brand"><svg><use href="#i-logo"/></svg>围标串标检测系统</div>
  <span class="sep">/</span><span class="sub-t">原型索引</span>
  <span class="ver">10 套页面</span>
</header>
<div class="page"><main style="padding:40px 0 80px">
  <div class="kicker">企业级 UI 原型</div>
  <h1 style="margin-top:8px">围标串标检测系统 · 页面原型</h1>
  <p class="lede">遵循<b>人机协同数智业务底座设计规范 v1.1</b> — 简约大气、企业可用。涵盖从登录到结果导出的完整业务闭环。</p>
  <div class="idx-grid">{items}</div>
</main></div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    pages: list[tuple[str, str, str]] = [
        ("01-登录页.html", "登录页", "用户身份认证 · 安全登录入口"),
        ("02-评审任务列表.html", "评审任务列表", "任务概览看板 · 搜索筛选 · 分页管理"),
        ("03-准备资料.html", "任务详情 · 准备阶段", "上传招标文件 · 管理投标人 · 选择检测项"),
        ("04-检测中心.html", "任务详情 · 检测中心", "三类检测实时进度 · 运行日志 · 启停控制"),
        ("05-围串标检测结果.html", "围串标检测结果", "风险概览 · 疑似围标组 · 6项检测明细"),
        ("06-投标文件检测.html", "投标文件检测详情", "相似度对比 · KPI统计 · 报告下载"),
        ("07-招标文件审查.html", "招标文件审查结果", "AI审查 · 公平性/技术条款 · 偏差分析"),
        ("08-文档元数据核验.html", "文档元数据核验", "三链交叉比对 · 跨投标人痕迹 · 证据链"),
        ("09-数据看板.html", "数据看板 / 分析中心", "年度统计 · 趋势图 · 风险分布 · 系统状态"),
        ("10-评审报告导出.html", "评审报告导出中心", "ZIP导出 · 报告预览 · 自定义选项"),
    ]

    generators = [
        page01_login, page02_task_list, page03_prepare, page04_detect,
        page05_collusion_result, page06_file_check, page07_tender_check,
        page08_metadata, page09_dashboard, page10_export,
    ]

    for (fname, _, _), gen in zip(pages, generators):
        html = gen()
        (OUTPUT / fname).write_text(html, encoding="utf-8")
        print(f"  ✓ {fname}")

    idx = index_page(pages)
    (OUTPUT / "index.html").write_text(idx, encoding="utf-8")
    print(f"  ✓ index.html")
    print(f"\n完成！输出目录: {OUTPUT}")


if __name__ == "__main__":
    main()

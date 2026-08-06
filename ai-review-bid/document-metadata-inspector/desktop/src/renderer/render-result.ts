import type {
  DocumentSummary,
  ReportTraceKind,
  ScanResult,
  TraceSummary,
} from "../shared/contracts";
import { element, formatBytes, testId } from "./dom";

// ════════════════════════════════════════════════════════════════
// Helpers: labels, formatting
// ════════════════════════════════════════════════════════════════

const LABELS: Record<string, string> = {
  author: "作者", title: "标题", subject: "主题", keywords: "关键词",
  creator: "创建程序", producer: "生成器", creationdate: "创建时间",
  moddate: "修改时间", created: "创建时间", modified: "修改时间",
  create_date: "创建时间", modify_date: "修改时间",
  lastmodifiedby: "最后修改者", last_modified_by: "最后修改者",
  lastsavedby: "最后保存者", last_saved_by: "最后保存者",
  revision: "修订版本", category: "分类", description: "描述",
  comments: "备注", comment: "备注", company: "公司", manager: "经理",
  application: "应用程序", applicationname: "应用程序名称",
  application_name: "应用程序名称", appversion: "应用版本",
  app_version: "应用版本", template: "模板", totaltime: "总编辑时间",
  total_time: "总编辑时间", pages: "页数", page_count: "页数",
  words: "字数", word_count: "字数", characters: "字符数",
  character_count: "字符数", characterswithspaces: "含空格字符数",
  character_count_with_spaces: "含空格字符数", paragraphs: "段落数",
  paragraph_count: "段落数", lines: "行数", line_count: "行数",
  slides: "幻灯片数", slide_count: "幻灯片数", language: "语言",
  version: "版本", contentstatus: "内容状态", content_status: "内容状态",
  identifier: "标识符", source: "来源", format: "格式", type: "类型",
  relation: "关联", coverage: "覆盖范围", rights: "权限",
  contributor: "贡献者", publisher: "发布者", date: "日期",
  trapped: "陷印标记", encryption: "加密", password: "密码",
};

function norm(raw: string): string {
  return raw.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function tField(raw: string): string {
  return LABELS[norm(raw)] ?? raw;
}

function fmtDate(v: string): string {
  const s = v.trim();
  if (!s) return "";
  const pdf = s.match(/^D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?/);
  if (pdf) {
    const [, y, mo, d, h, mi] = pdf;
    return h && mi ? `${y}-${mo}-${d} ${h}:${mi}` : `${y}-${mo}-${d}`;
  }
  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]} ${iso[4]}:${iso[5]}`;
  const d = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (d) return s;
  return s;
}

function showVal(v: string): string {
  if (!v) return "—";
  return fmtDate(v);
}

// ════════════════════════════════════════════════════════════════
// Connection tracks (kept for tests)
// ════════════════════════════════════════════════════════════════

export interface ConnectionTrack {
  traceIndex: number;
  fromGroupId: string;
  toGroupId: string;
  offset: number;
}

export function connectionTracks(traces: TraceSummary[]): ConnectionTrack[] {
  const gap = 10;
  const edges = traces.flatMap((trace, traceIndex) => {
    const from = trace.groupIds[0];
    if (from === undefined) return [];
    return trace.groupIds.slice(1).map((to) => {
      const [a, b] = from.localeCompare(to) <= 0 ? [from, to] : [to, from];
      return { traceIndex, fromGroupId: a, toGroupId: b, key: [a, b].sort().join("\0") };
    });
  });
  const totals = new Map<string, number>();
  for (const e of edges) totals.set(e.key, (totals.get(e.key) ?? 0) + 1);
  const pos = new Map<string, number>();
  return edges.map((e) => {
    const p = pos.get(e.key) ?? 0;
    pos.set(e.key, p + 1);
    const total = totals.get(e.key) ?? 1;
    return { traceIndex: e.traceIndex, fromGroupId: e.fromGroupId, toGroupId: e.toGroupId, offset: (p - (total - 1) / 2) * gap };
  });
}

// ════════════════════════════════════════════════════════════════
// Format helpers
// ════════════════════════════════════════════════════════════════

function fmtClass(family: string): string {
  if (family === "pdf") return "fmt--pdf";
  if (family === "word") return "fmt--word";
  if (family === "excel") return "fmt--excel";
  return "fmt--default";
}

function fileIcon(family: string): string {
  if (family === "pdf") {
    return '<svg viewBox="0 0 20 20" width="16" height="16"><rect x="3" y="2" width="14" height="16" rx="1.5" fill="#fee2e2" stroke="#ef4444" stroke-width="1"/><text x="10" y="14" font-size="6" font-weight="700" fill="#dc2626" text-anchor="middle" font-family="sans-serif">PDF</text></svg>';
  }
  if (family === "word") {
    return '<svg viewBox="0 0 20 20" width="16" height="16"><rect x="3" y="2" width="14" height="16" rx="1.5" fill="#dbeafe" stroke="#3b82f6" stroke-width="1"/><text x="10" y="14" font-size="6" font-weight="700" fill="#2563eb" text-anchor="middle" font-family="sans-serif">DOC</text></svg>';
  }
  if (family === "excel") {
    return '<svg viewBox="0 0 20 20" width="16" height="16"><rect x="3" y="2" width="14" height="16" rx="1.5" fill="#dcfce7" stroke="#22c55e" stroke-width="1"/><text x="10" y="14" font-size="6" font-weight="700" fill="#16a34a" text-anchor="middle" font-family="sans-serif">XLS</text></svg>';
  }
  return '<svg viewBox="0 0 20 20" width="16" height="16"><rect x="3" y="2" width="14" height="16" rx="1.5" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1"/></svg>';
}

// ════════════════════════════════════════════════════════════════
// Match context: pre-compute cross-bidder collision data
// ════════════════════════════════════════════════════════════════

/** Distinct colors for each collusion group, cycling through a palette. */
const TAG_COLORS = [
  "#dc2626", "#7c3aed", "#0891b2", "#c2410c",
  "#be123c", "#4338ca", "#0e7490", "#a16207",
];

interface MatchContext {
  /** docId → traces that involve this document */
  docTraces: Map<string, TraceSummary[]>;
  /** traceId → { num (1-based), color } */
  traceTags: Map<string, { num: number; color: string }>;
  /** docId → groupId */
  docGroupIds: Map<string, string>;
}

/** Key-field canonical patterns (normalized) for matching against trace fieldNames. */
const FIELD_PATTERNS: Record<string, string[]> = {
  author: ["author", "creator"].map(norm),
  lastModifiedBy: ["lastmodifiedby", "lastmodifiedby", "lastsavedby", "lastsavedby"].map(norm),
  created: ["creationdate", "created", "createdate", "createdat"].map(norm),
  modified: ["moddate", "modified", "modifydate", "modificationdate", "modifiedat"].map(norm),
  company: ["company"].map(norm),
  template: ["template"].map(norm),
};

function buildMatchContext(result: ScanResult): MatchContext {
  const allTraces = [...result.personTraces, ...result.cautionTraces];

  // docId → traces
  const docTraces = new Map<string, TraceSummary[]>();
  for (const t of allTraces) {
    for (const docId of t.documentIds) {
      const list = docTraces.get(docId) ?? [];
      list.push(t);
      docTraces.set(docId, list);
    }
  }

  // traceId → tag { num, color }
  const traceTags = new Map<string, { num: number; color: string }>();
  allTraces.forEach((t, i) => {
    traceTags.set(t.id, { num: i + 1, color: TAG_COLORS[i % TAG_COLORS.length] ?? TAG_COLORS[0]! });
  });

  // docId → groupId
  const docGroupIds = new Map<string, string>();
  for (const group of result.groups) {
    for (const doc of group.documents) {
      docGroupIds.set(doc.id, group.id);
    }
  }

  return { docTraces, traceTags, docGroupIds };
}

/** Check if a key field (by canonical key) is involved in any trace for this document. */
function findFieldTrace(docId: string, fieldKey: string, ctx: MatchContext): TraceSummary | undefined {
  const patterns = FIELD_PATTERNS[fieldKey];
  if (patterns === undefined) return undefined;
  const traces = ctx.docTraces.get(docId) ?? [];
  for (const trace of traces) {
    for (const fn of trace.fieldNames) {
      if (patterns.includes(norm(fn))) {
        return trace;
      }
    }
  }
  return undefined;
}

/** Get bidder labels that share a trace with the given document (excluding the doc's own group). */
function otherBidderLabels(trace: TraceSummary, docGroupId: string, groupNames: Map<string, string>): string[] {
  return trace.groupIds
    .filter((id) => id !== docGroupId)
    .map((id) => groupNames.get(id) ?? "未知");
}

// ════════════════════════════════════════════════════════════════
// Collision overview banner (at-a-glance summary)
// ════════════════════════════════════════════════════════════════

const TRACE_KIND_LABEL: Record<ReportTraceKind, string> = {
  person_trace: "人员身份",
  organization_trace: "组织信息",
  software_trace: "软件环境",
  document_environment_trace: "文档环境",
};

function makeLegendChip(
  t: TraceSummary,
  ctx: MatchContext,
  groupNames: Map<string, string>,
): HTMLElement {
  const tag = ctx.traceTags.get(t.id)!;
  const chip = element("div", "collision-chip");
  chip.style.setProperty("--tag-color", tag.color);

  const num = element("span", "collision-chip__num");
  num.textContent = String(tag.num);
  num.style.background = tag.color;
  chip.append(num);

  const fieldLabel = t.fieldNames.length > 0
    ? t.fieldNames.map((f) => tField(f)).join("/")
    : TRACE_KIND_LABEL[t.kind];
  chip.append(element("span", "collision-chip__field", fieldLabel));
  chip.append(element("span", "collision-chip__value", t.value));
  chip.append(element("span", "collision-chip__bidders",
    t.groupIds.map((id) => groupNames.get(id) ?? "未知").join(" · ")));
  return chip;
}

function collisionBanner(result: ScanResult, ctx: MatchContext, groupNames: Map<string, string>): HTMLElement {
  const wrap = element("div", "collision-wrap");

  // ── Section 1: Person / organization identity overlaps (strong collusion signal) ───
  if (result.personTraces.length > 0) {
    const danger = element("div", "collision-banner collision-banner--danger");
    danger.append(
      element("span", "collision-banner__icon", "⚠"),
      element("span", "collision-banner__text",
        `发现 ${result.personTraces.length} 处人员/组织身份重复 — 疑似围标串标`),
    );
    const legend = element("div", "collision-legend");
    for (const t of result.personTraces) {
      legend.append(makeLegendChip(t, ctx, groupNames));
    }
    danger.append(legend);
    wrap.append(danger);
  }

  // ── Section 2: Template / timestamp overlaps (needs manual review) ───
  if (result.cautionTraces.length > 0) {
    const caution = element("div", "collision-banner collision-banner--warn");
    caution.append(
      element("span", "collision-banner__icon", "⚠"),
      element("span", "collision-banner__text",
        `${result.cautionTraces.length} 处模板/时间戳一致 — 需人工复核`),
    );
    const legend = element("div", "collision-legend");
    for (const t of result.cautionTraces) {
      legend.append(makeLegendChip(t, ctx, groupNames));
    }
    caution.append(legend);
    wrap.append(caution);
  }

  // ── All clear ───
  if (result.personTraces.length === 0 && result.cautionTraces.length === 0) {
    const ok = element("div", "collision-banner collision-banner--ok");
    ok.append(
      element("span", "collision-banner__icon", "✓"),
      element("span", "collision-banner__text", "未发现跨投标人关键信息重复"),
    );
    return ok;
  }

  return wrap;
}

// ════════════════════════════════════════════════════════════════
// Summary strip
// ════════════════════════════════════════════════════════════════

function summaryStrip(result: ScanResult): HTMLElement {
  const strip = element("div", "summary-strip");
  const add = (num: string, label: string, alert?: boolean): void => {
    const item = element("div", alert ? "summary-item summary-item--alert" : "summary-item");
    item.append(element("div", "summary-item__num", num), element("div", "summary-item__label", label));
    strip.append(item);
  };
  add(`${result.completeDocumentCount}/${result.documentCount}`, "提取完成");
  add(result.observationCount.toLocaleString("zh-CN"), "条元数据");
  add(String(result.bidderCount), "个投标人");
  add(String(result.personTraces.length), "人员重复", result.personTraces.length > 0);
  add(String(result.cautionTraces.length), "待复核", result.cautionTraces.length > 0);
  return strip;
}

// ════════════════════════════════════════════════════════════════
// Document card (key info visible, full metadata hidden)
// ════════════════════════════════════════════════════════════════

function docCard(
  doc: DocumentSummary,
  ctx: MatchContext,
  groupNames: Map<string, string>,
): HTMLElement {
  const myTraces = ctx.docTraces.get(doc.id) ?? [];
  const docGroupId = ctx.docGroupIds.get(doc.id) ?? "";
  const hasDanger = myTraces.some((t) => t.tone === "danger");

  const card = element("div", `doc-card ${hasDanger ? "doc-card--flagged" : ""}`);

  // ── Left color bar (only for dangerous person matches) ───
  if (hasDanger) {
    const bar = element("div", "doc-card__bar");
    // Use the first (highest-priority) trace's color
    const firstTraceId = myTraces[0]?.id;
    const firstTag = firstTraceId !== undefined ? ctx.traceTags.get(firstTraceId) : undefined;
    if (firstTag) {
      bar.style.background = firstTag.color;
    }
    card.append(bar);
  }

  const body = element("div", "doc-card__body");

  // ── Header: icon + filename + format + match tags ───
  const header = element("div", "doc-card__header");
  const iconWrap = element("span", "doc-card__icon");
  iconWrap.innerHTML = fileIcon(doc.family);
  header.append(iconWrap);
  header.append(element("span", "doc-card__name", doc.name));
  header.append(element("span", `fmt ${fmtClass(doc.family)}`, doc.format.toUpperCase()));

  // Match tag badges
  for (const t of myTraces) {
    const tag = ctx.traceTags.get(t.id)!;
    const badge = element("span", "match-tag");
    badge.textContent = String(tag.num);
    badge.style.background = tag.color;
    badge.title = `${TRACE_KIND_LABEL[t.kind]}：${t.value}`;
    header.append(badge);
  }

  const isOk = doc.status === "complete";
  header.append(element("span", isOk ? "pill pill--ok" : "pill pill--warn", isOk ? "完整" : "复核"));
  body.append(header);

  // ── Collision warning — split danger traces from caution traces ───
  const personHits = myTraces.filter((t) => t.tone === "danger");
  const cautionHits = myTraces.filter((t) => t.tone === "caution");

  if (personHits.length > 0) {
    const warn = element("div", "doc-card__warn doc-card__warn--danger");
    warn.append(element("span", "doc-card__warn-icon", "⚠"));
    const warnItems = element("div", "doc-card__warn-items");
    for (const t of personHits) {
      const tag = ctx.traceTags.get(t.id)!;
      const others = otherBidderLabels(t, docGroupId, groupNames);
      const fieldLabel = t.fieldNames.length > 0
        ? t.fieldNames.map((f) => tField(f)).join("/")
        : "关键信息";
      const line = element("div", "doc-card__warn-line");
      const dot = element("span", "doc-card__warn-dot");
      dot.style.background = tag.color;
      line.append(
        dot,
        element("span", "doc-card__warn-field", `${fieldLabel}「${t.value}」`),
        element("span", "doc-card__warn-same", `与 ${others.join("、")} 相同`),
      );
      warnItems.append(line);
    }
    warn.append(warnItems);
    body.append(warn);
  }

  if (cautionHits.length > 0) {
    const cautionInfo = element("div", "doc-card__warn doc-card__warn--caution");
    cautionInfo.append(element("span", "doc-card__warn-icon", "⚠"));
    const cautionItems = element("div", "doc-card__warn-items");
    for (const t of cautionHits) {
      const tag = ctx.traceTags.get(t.id)!;
      const others = otherBidderLabels(t, docGroupId, groupNames);
      const fieldLabel = t.fieldNames.length > 0
        ? t.fieldNames.map((f) => tField(f)).join("/")
        : TRACE_KIND_LABEL[t.kind];
      const line = element("div", "doc-card__warn-line doc-card__warn-line--caution");
      const dot = element("span", "doc-card__warn-dot");
      dot.style.background = tag.color;
      line.append(
        dot,
        element("span", "doc-card__warn-field", `${fieldLabel}「${t.value}」`),
        element("span", "doc-card__warn-same", `与 ${others.join("、")} 相同`),
      );
      cautionItems.append(line);
    }
    cautionInfo.append(cautionItems);
    body.append(cautionInfo);
  }

  // ── Key fields grid ───
  const keyGrid = element("div", "kv-grid kv-grid--key");

  const fieldDefs: { key: string; label: string; value: string }[] = [
    { key: "author", label: "作者", value: doc.keyFields.author },
    { key: "lastModifiedBy", label: "最后修改者", value: doc.keyFields.lastModifiedBy },
    { key: "company", label: "公司", value: doc.keyFields.company },
    { key: "template", label: "模板", value: doc.keyFields.template },
    { key: "created", label: "创建时间", value: doc.keyFields.created },
    { key: "modified", label: "修改时间", value: doc.keyFields.modified },
  ];

  for (const fd of fieldDefs) {
    const matchedTrace = findFieldTrace(doc.id, fd.key, ctx);
    const tone = matchedTrace?.tone;
    const itemClass = `kv ${matchedTrace ? (tone === "caution" ? "kv--matched-caution" : "kv--matched") : ""}`;
    const item = element("div", itemClass);

    const labelEl = element("div", "kv__label", fd.label);

    const valueText = showVal(fd.value);
    const valueClass = `kv__value ${tone === "caution" ? "kv__value--caution" : tone === "danger" ? "kv__value--danger" : ""}`;
    const valueEl = element("div", valueClass, valueText);
    valueEl.title = valueText;

    item.append(labelEl, valueEl);

    // "Same as bidder X" badge under the matched value
    if (matchedTrace) {
      const others = otherBidderLabels(matchedTrace, docGroupId, groupNames);
      const tag = ctx.traceTags.get(matchedTrace.id)!;
      const sameBadge = element("div", `kv__same ${tone === "caution" ? "kv__same--caution" : ""}`);
      const dot = element("span", "kv__same-dot");
      dot.style.background = tag.color;
      sameBadge.append(
        dot,
        element("span", undefined, `同 ${others.join("、")}`),
      );
      item.append(sameBadge);
    }

    keyGrid.append(item);
  }

  // Secondary info
  const kv2 = (label: string, value: string): void => {
    const item = element("div", "kv");
    const valEl = element("div", "kv__value", value);
    valEl.title = value;
    item.append(element("div", "kv__label", label), valEl);
    keyGrid.append(item);
  };
  kv2("文件大小", formatBytes(doc.sizeBytes));
  kv2("文件指纹", doc.sha256Prefix);

  body.append(keyGrid);

  // ── Full metadata (hidden behind toggle) ───
  if (doc.observations.length > 0) {
    const obsSection = element("div", "obs-toggle");
    const obsLabel = element("span", undefined, "▸ 查看全部元数据");
    obsSection.append(obsLabel);
    obsSection.append(element("span", "obs-toggle__count", `${doc.observations.length} 条`));

    const obsGrid = element("div", "kv-grid kv-grid--hidden");
    for (const obs of doc.observations) {
      const item = element("div", "kv");
      item.append(
        element("div", "kv__label", tField(obs.label)),
        element("div", "kv__value", fmtDate(obs.value) || "—"),
      );
      obsGrid.append(item);
    }

    obsSection.addEventListener("click", (e) => {
      e.stopPropagation();
      const hidden = obsGrid.classList.toggle("kv-grid--hidden");
      obsLabel.textContent = hidden ? "▸ 查看全部元数据" : "▾ 收起全部元数据";
    });

    body.append(obsSection, obsGrid);
  }

  card.append(body);
  return card;
}

// ════════════════════════════════════════════════════════════════
// Bidder panel (icon + name on top, document cards below)
// ════════════════════════════════════════════════════════════════

function bidderPanel(
  groupIndex: number,
  group: ScanResult["groups"][number],
  ctx: MatchContext,
  groupNames: Map<string, string>,
): HTMLElement {
  const panel = element("div", "bidder-panel");

  // Check if any document in this group has a PERSON match (not just environment)
  const hasFlagged = group.documents.some((doc) => {
    const traces = ctx.docTraces.get(doc.id) ?? [];
    return traces.some((t) => t.tone === "danger");
  });

  // Collect unique authors across this bidder's files (for summary)
  const authors = new Set<string>();
  for (const doc of group.documents) {
    if (doc.keyFields.author) authors.add(doc.keyFields.author);
  }
  const authorSummary = authors.size > 0
    ? [...authors].join(" / ")
    : "—";

  // ── Header: folder icon + bidder name + file count + flag (click to expand) ───
  const header = element("div", `bidder-panel__header ${hasFlagged ? "bidder-panel__header--flagged" : ""}`);
  header.style.cursor = "pointer";

  const labelEl = group.kind === "bidder"
    ? String.fromCharCode(65 + groupIndex)
    : "根";

  const letter = element("span", "bidder-panel__letter");
  letter.textContent = labelEl;
  header.append(letter);

  const headerInfo = element("div", "bidder-panel__header-info");
  headerInfo.append(element("span", "bidder-panel__name", group.name));

  // Sub-line: author summary + file count
  const sub = element("div", "bidder-panel__sub");
  sub.append(
    element("span", undefined, `作者：${authorSummary}`),
    element("span", "bidder-panel__sep", "·"),
    element("span", undefined, `${group.documents.length} 个文件`),
  );
  headerInfo.append(sub);
  header.append(headerInfo);

  // Right side: flag + expand indicator
  const headerRight = element("div", "bidder-panel__header-right");
  if (hasFlagged) {
    const matchCount = group.documents.filter((d) => {
      const traces = ctx.docTraces.get(d.id) ?? [];
      return traces.some((t) => t.tone === "danger");
    }).length;
    headerRight.append(element("span", "bidder-panel__flag", `⚠ ${matchCount} 个文件存疑`));
  }
  const chevron = element("span", "bidder-panel__chevron", "▾");
  headerRight.append(chevron);
  header.append(headerRight);

  panel.append(header);

  // ── Body: document cards (collapsible) ───
  const body = element("div", "bidder-panel__body");
  for (const doc of group.documents) {
    body.append(docCard(doc, ctx, groupNames));
  }
  panel.append(body);

  // Click header to toggle
  header.addEventListener("click", () => {
    const isOpen = panel.classList.toggle("bidder-panel--collapsed");
    chevron.textContent = isOpen ? "▸" : "▾";
  });

  return panel;
}

// ════════════════════════════════════════════════════════════════
// Main render
// ════════════════════════════════════════════════════════════════

export function renderResult(result: ScanResult): HTMLElement {
  const main = element("div", "main-scroll");
  testId(main, "result-page");

  const groupNames = new Map(result.groups.map((g) => [g.id, g.name]));
  const ctx = buildMatchContext(result);

  // Summary strip
  main.append(summaryStrip(result));

  // Collision banner (at-a-glance overview with legend)
  main.append(collisionBanner(result, ctx, groupNames));

  // Bidder panels
  const panelsWrap = element("div", "panels-wrap");
  result.groups.forEach((group, i) => {
    panelsWrap.append(bidderPanel(i, group, ctx, groupNames));
  });
  main.append(panelsWrap);

  return main;
}

import type {
  ScanResult,
  TraceSummary,
} from "../shared/contracts";
import { element, testId } from "./dom";

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

/** Local-time "YYYY-MM-DD HH:MM" from an ISO string. */
function fmtScanTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Local-time "YYYY-MM-DD" from an ISO string. */
function fmtScanDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return new Date().toISOString().slice(0, 10);
  const p = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
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
// Report helpers
// ════════════════════════════════════════════════════════════════

const NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];

function numeral(n: number): string {
  return NUMERALS[n - 1] ?? String(n);
}

/** Map groupId → bidder letter label (A, B, C, …). */
function buildGroupLabels(result: ScanResult): Map<string, string> {
  const labels = new Map<string, string>();
  let idx = 0;
  for (const group of result.groups) {
    if (group.kind === "bidder") {
      labels.set(group.id, String.fromCharCode(65 + idx));
      idx++;
    } else {
      labels.set(group.id, "根");
    }
  }
  return labels;
}

function bidderLetters(trace: TraceSummary, labels: Map<string, string>): string {
  return trace.groupIds.map((id) => labels.get(id) ?? "?").join("、");
}

function traceFieldLabel(trace: TraceSummary): string {
  if (trace.fieldNames.length > 0) {
    return [...new Set(trace.fieldNames.map((f) => tField(f)))].join("/");
  }
  return trace.label;
}

/** "PDF 5 · DOCX 5 · XLSX 5" style breakdown. */
function formatBreakdown(result: ScanResult): string {
  const counts = new Map<string, number>();
  for (const group of result.groups) {
    for (const doc of group.documents) {
      const fam = doc.family || "other";
      counts.set(fam, (counts.get(fam) ?? 0) + 1);
    }
  }
  const parts: string[] = [];
  const order = ["pdf", "word", "excel"];
  for (const fam of order) {
    const c = counts.get(fam);
    if (c) parts.push(`${fam.toUpperCase()} ${c}`);
  }
  for (const [fam, c] of counts) {
    if (!order.includes(fam)) parts.push(`${fam.toUpperCase()} ${c}`);
  }
  return parts.length > 0 ? parts.join(" · ") : String(result.documentCount);
}

/** Unique parser run names joined by " · ". */
function parserChain(result: ScanResult): string {
  const names = new Set<string>();
  for (const group of result.groups) {
    for (const doc of group.documents) {
      for (const run of doc.parserRuns) {
        names.add(run.name);
      }
    }
  }
  return names.size > 0 ? [...names].join(" · ") : "原生解析器";
}

// ════════════════════════════════════════════════════════════════
// Report sections
// ════════════════════════════════════════════════════════════════

function reportBasicInfo(num: string, result: ScanResult): HTMLElement {
  const section = element("div", "r-section");
  section.append(element("h2", undefined, `${num}、基本信息`));

  const table = element("table", "r-table r-table--info");
  const row = (th: string, td: string): void => {
    const r = element("tr");
    r.append(element("th", undefined, th), element("td", undefined, td));
    table.append(r);
  };

  row("核验目录", result.rootName);
  row("投标人数", `${result.bidderCount} 家`);
  row("文件总数", `${result.documentCount} 个（${formatBreakdown(result)}）`);
  row("元数据条目", `${result.observationCount.toLocaleString("zh-CN")} 条`);
  const pct = result.documentCount > 0
    ? Math.round((result.completeDocumentCount / result.documentCount) * 100)
    : 0;
  row("提取完成", `${result.completeDocumentCount}/${result.documentCount}（${pct}%）`);
  row("解析链", parserChain(result));

  section.append(table);
  return section;
}

function reportConclusion(
  result: ScanResult,
  labels: Map<string, string>,
): HTMLElement {
  const hasDanger = result.personTraces.length > 0;
  const hasCaution = result.cautionTraces.length > 0;
  const tone = hasDanger ? "danger" : hasCaution ? "warn" : "ok";

  const box = element("div", `r-conclusion r-conclusion--${tone}`);

  const titleText = hasDanger
    ? "核验结论：存在围标串标重大嫌疑"
    : hasCaution
      ? "核验结论：存在模板/时间戳异常，建议人工复核"
      : "核验结论：未发现跨投标人关键信息重复";

  box.append(element("div", `r-conclusion__title r-conclusion__title--${tone}`, titleText));

  if (hasDanger || hasCaution) {
    const traces = [...result.personTraces, ...result.cautionTraces];
    box.append(element("p", "r-conclusion__intro", "以下投标人的投标文件存在关键信息重复："));

    const list = element("ol", "r-conclusion__list");
    for (const trace of traces) {
      list.append(element("li", undefined,
        `${traceFieldLabel(trace)}「${trace.value}」— 涉及投标人 ${bidderLetters(trace, labels)}`));
    }
    box.append(list);
  } else {
    box.append(element("p", "r-conclusion__intro",
      "所有投标文件的关键元数据均无交叉重复，未检测到围标串标痕迹。"));
  }

  box.append(element("p", "r-conclusion__parser",
    `以上结论由 ${parserChain(result)} ${hasDanger || hasCaution ? "交叉验证" : "独立验证"}。`));

  return box;
}

function reportTraceSection(
  num: string,
  title: string,
  traces: TraceSummary[],
  labels: Map<string, string>,
  tone: "danger" | "caution",
): HTMLElement | null {
  if (traces.length === 0) return null;

  const section = element("div", "r-section");
  section.append(element("h2", undefined, `${num}、${title}`));

  const table = element("table", "r-table");
  const thead = element("thead");
  const headRow = element("tr");
  headRow.append(
    element("th", undefined, "痕迹类型"),
    element("th", undefined, "重复值"),
    element("th", undefined, "涉及投标人"),
  );
  thead.append(headRow);
  table.append(thead);

  const tbody = element("tbody");
  const typeClass = tone === "danger" ? "r-td--danger" : "r-td--caution";
  const bgClass = tone === "danger" ? "r-td--danger-bg" : "r-td--caution-bg";
  for (const trace of traces) {
    const tr = element("tr");
    tr.append(
      element("td", typeClass, traceFieldLabel(trace)),
      element("td", bgClass, trace.value),
      element("td", bgClass, bidderLetters(trace, labels)),
    );
    tbody.append(tr);
  }
  table.append(tbody);
  section.append(table);

  return section;
}

function reportRecommendations(num: string, result: ScanResult): HTMLElement {
  const section = element("div", "r-section");
  section.append(element("h2", undefined, `${num}、建议`));

  const hasDanger = result.personTraces.length > 0;
  const hasCaution = result.cautionTraces.length > 0;

  const introText = hasDanger
    ? `鉴于检测到 ${result.personTraces.length} 处人员/组织身份重复，建议：`
    : hasCaution
      ? `鉴于检测到 ${result.cautionTraces.length} 处模板/时间戳一致，建议：`
      : "未发现异常痕迹，建议：";
  section.append(element("p", "r-section__p", introText));

  const list = element("ol", "r-conclusion__list");
  const items = hasDanger
    ? [
        "要求相关投标人分别说明文档编制过程",
        "核实重复身份信息对应人员的真实身份及与各投标人的关系",
        "结合报价文件和施工组织方案进一步审查",
      ]
    : hasCaution
      ? [
          "核实模板来源，确认是否为公开模板",
          "核查文档创建时间是否因合理原因一致",
          "结合其他信息综合判断是否需要进一步调查",
        ]
      : [
          "归档本次核验报告以备查",
          "如后续获得新线索可重新核验",
        ];
  for (const text of items) {
    list.append(element("li", undefined, text));
  }
  section.append(list);

  return section;
}

function reportSignature(result: ScanResult): HTMLElement {
  const sign = element("div", "r-sign");
  const dateStr = result.scannedAt ? fmtScanDate(result.scannedAt) : fmtScanDate(new Date().toISOString());
  const reportId = `RV-${dateStr.replace(/-/g, "")}-001`;

  sign.append(
    element("span", undefined, "核验人：审计员"),
    element("span", undefined, `核验日期：${dateStr}`),
    element("span", undefined, `报告编号：${reportId}`),
  );
  return sign;
}

// ════════════════════════════════════════════════════════════════
// Main render
// ════════════════════════════════════════════════════════════════

export function renderResult(result: ScanResult): HTMLElement {
  const main = element("div", "main-scroll report-scroll");
  testId(main, "result-page");

  const labels = buildGroupLabels(result);

  // Background wash
  const wash = element("div", "report-wash");

  // Report container
  const wrap = element("div", "report-wrap");
  const report = element("div", "report");

  // Title
  report.append(element("h1", "report__title", "文档元数据核验报告"));
  const scanTime = result.scannedAt ? fmtScanTime(result.scannedAt) : "";
  report.append(element("p", "report__sub",
    `${result.rootName} · 核验时间 ${scanTime} · 离线分析`));

  // Dynamic section numbering
  let n = 0;
  const next = (): string => numeral(++n);

  // 一、基本信息
  report.append(reportBasicInfo(next(), result));

  // Conclusion (unnumbered)
  report.append(reportConclusion(result, labels));

  // 人员/组织身份重复（高风险）
  const dangerSection = reportTraceSection(
    next(), "人员/组织身份重复（高风险）",
    result.personTraces, labels, "danger",
  );
  if (dangerSection) report.append(dangerSection);

  // 模板/时间戳重复（待复核）
  const cautionSection = reportTraceSection(
    next(), "模板/时间戳重复（待复核）",
    result.cautionTraces, labels, "caution",
  );
  if (cautionSection) report.append(cautionSection);

  // 建议
  report.append(reportRecommendations(next(), result));

  // Signature
  report.append(reportSignature(result));

  wrap.append(report);
  main.append(wash, wrap);

  return main;
}

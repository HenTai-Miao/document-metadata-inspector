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
  createdat: "创建时间", modifiedat: "修改时间", updatedat: "修改时间",
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
  filesize: "文件大小", mimetype: "MIME类型", contenttype: "内容类型",
  filepath: "文件路径", filename: "文件名", name: "文件名",
  sha256: "SHA256", hash: "哈希值", md5: "MD5",
  lastprinted: "最后打印", printdate: "打印日期",
  edittime: "编辑时长", editingduration: "编辑时长",
  sheets: "工作表数", sheet_count: "工作表数",
  cpg: "代码页", codepage: "代码页",
};

function norm(raw: string): string {
  return raw.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function tField(raw: string): string {
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

/** Map groupId → group name (company name). */
function buildGroupNames(result: ScanResult): Map<string, string> {
  const names = new Map<string, string>();
  for (const group of result.groups) {
    names.set(group.id, group.name);
  }
  return names;
}

/** Map docId → {companyId, file} for looking up which company/file a trace doc belongs to. */
function buildDocInfo(result: ScanResult, names: Map<string, string>): Map<string, { company: string; file: string }> {
  const map = new Map<string, { company: string; file: string }>();
  for (const group of result.groups) {
    for (const doc of group.documents) {
      map.set(doc.id, { company: names.get(group.id) ?? group.id, file: doc.name });
    }
  }
  return map;
}

function traceFieldLabel(trace: TraceSummary): string {
  if (trace.fieldNames.length > 0) {
    return [...new Set(trace.fieldNames.map((f) => tField(f)))].join("/");
  }
  return trace.label;
}

// ════════════════════════════════════════════════════════════════
// Report sections
// ════════════════════════════════════════════════════════════════

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

  const names = buildGroupNames(result);
  const docInfo = buildDocInfo(result, names);
  const hasDanger = result.personTraces.length > 0;
  const hasCaution = result.cautionTraces.length > 0;

  const wrap = element("div", "cf-wrap");

  // ── Centered header ──
  wrap.append(
    element("h1", "cf-title", "文档元数据核验报告"),
    element("p", "cf-sub",
      `${result.rootName} · 核验时间 ${result.scannedAt ? fmtScanTime(result.scannedAt) : ""} · 离线分析`),
  );

  // ── Stats pills ──
  const stats = element("div", "cf-stats");
  const addStat = (val: string, lbl: string, cls?: string): void => {
    const s = element("div", "cf-stat");
    if (cls) s.classList.add(cls);
    s.append(element("div", "cf-stat__val", val), element("div", "cf-stat__lbl", lbl));
    stats.append(s);
  };
  addStat(String(result.bidderCount), "投标人");
  addStat(String(result.documentCount), "文件");
  if (hasDanger) addStat(String(result.personTraces.length), "高风险", "cf-stat--danger");
  if (hasCaution) addStat(String(result.cautionTraces.length), "待复核", "cf-stat--caution");
  addStat(result.observationCount.toLocaleString("zh-CN"), "元数据条");
  wrap.append(stats);

  // ── Timeline sections ──
  if (hasDanger) {
    wrap.append(buildTimelineSection("高风险发现", `${result.personTraces.length} 处`, "danger", result.personTraces, docInfo));
  }
  if (hasCaution) {
    wrap.append(buildTimelineSection("待复核发现", `${result.cautionTraces.length} 处`, "caution", result.cautionTraces, docInfo));
  }
  if (!hasDanger && !hasCaution) {
    wrap.append(buildAllClear());
  }

  // ── Signature ──
  wrap.append(reportSignature(result));

  main.append(wrap);
  return main;
}

/** Build the "all clear" green checkmark state when no findings. */
function buildAllClear(): HTMLElement {
  const box = element("div", "cf-clear");

  const icon = element("div", "cf-clear__icon");
  icon.innerHTML =
    '<svg width="32" height="32" viewBox="0 0 32 32" fill="none"><path d="M7 16l6 6L25 10" stroke="var(--green)" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  box.append(icon);

  box.append(element("div", "cf-clear__title", "未发现异常"));

  box.append(element("p", "cf-clear__desc",
    "所有投标文件的关键元数据均无交叉重复，未检测到围标串标痕迹。"));

  const tags = element("div", "cf-clear__tags");
  for (const text of ["公司名无重复", "作者无重复", "模板无重复"]) {
    const tag = element("div", "cf-clear__tag");
    tag.append(element("span", "cf-clear__dot"), element("span", undefined, text));
    tags.append(tag);
  }
  box.append(tags);

  return box;
}

/** Build a timeline section with its own colored vertical line + circle node header. */
function buildTimelineSection(
  title: string,
  count: string,
  tone: "danger" | "caution",
  traces: TraceSummary[],
  docInfo: Map<string, { company: string; file: string }>,
): HTMLElement {
  const section = element("div", `tl-section tl-section--${tone}`);

  // Section header with circle node on the line
  const header = element("div", "tl-section__header");
  header.append(
    element("span", "tl-section__title", title),
    element("span", "tl-section__count", count),
  );
  section.append(header);

  // Finding items
  const tagClass = tone === "danger" ? "ctag ctag--danger" : "ctag ctag--caution";
  for (const trace of traces) {
    const item = element("div", "tl-item");
    const head = element("div", "tl-item__head");
    head.append(element("span", tagClass, traceFieldLabel(trace)));
    head.append(element("span", "tl-item__val", trace.value));
    item.append(head);

    // Company names line
    const companies = new Set<string>();
    for (const docId of trace.documentIds) {
      const info = docInfo.get(docId);
      if (info) companies.add(info.company);
    }
    item.append(element("div", "tl-item__cos", [...companies].join(" · ")));

    // File tags
    const files = element("div", "tl-item__files");
    for (const docId of trace.documentIds) {
      const info = docInfo.get(docId);
      const tag = element("span", "r-co-file");
      if (info) {
        tag.append(
          element("span", "r-co-file__co", info.company),
          element("span", "r-co-file__sep", "›"),
          element("span", "r-co-file__name", info.file),
        );
      } else {
        tag.append(element("span", "r-co-file__co", docId));
      }
      files.append(tag);
    }
    item.append(files);
    section.append(item);
  }

  return section;
}

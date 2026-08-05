import type {
  DocumentSummary,
  ScanResult,
  TraceSummary,
} from "../shared/contracts";
import { element, formatBytes, testId } from "./dom";

// ── Field labels ───

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

function tField(raw: string): string {
  const k = raw.toLowerCase().replace(/[^a-z0-9]/g, "");
  return LABELS[k] ?? raw;
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

// ── Connection tracks (kept for tests) ───

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

// ── Format badge ───

function fmtClass(family: string): string {
  if (family === "pdf") return "fmt--pdf";
  if (family === "word") return "fmt--word";
  if (family === "excel") return "fmt--excel";
  return "fmt--default";
}

// ── Trace banner ───

function traceBanner(result: ScanResult, groupNames: Map<string, string>): HTMLElement | null {
  const traces = [...result.personTraces, ...result.contextTraces];
  if (traces.length === 0) return null;

  const hasDanger = result.personTraces.length > 0;
  const banner = element("div", `trace-banner ${hasDanger ? "" : "trace-banner--ok"}`);
  banner.append(
    element("div", "trace-banner__title",
      hasDanger ? `发现 ${result.personTraces.length} 条跨投标人人员痕迹` : "未发现人员重复痕迹",
    ),
  );
  const list = element("div", "trace-list");
  for (const t of traces) {
    const row = element("div", "trace-row");
    const groups = t.groupIds.map((id) => groupNames.get(id) ?? "未知").join(" ↔ ");
    row.append(
      element("span", "trace-row__label", t.label),
      element("span", "trace-row__value", t.value),
      element("span", "trace-row__groups", `  ${groups}`),
    );
    list.append(row);
  }
  banner.append(list);
  return banner;
}

// ── Summary strip ───

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
  return strip;
}

// ── Document row ───

function docRow(doc: DocumentSummary, bidderLabel: string): HTMLElement {
  const row = element("div", "table-row");

  const summary = element("div", "table-row__summary");
  summary.append(
    element("span", "table-row__bidder", bidderLabel),
    element("span", "table-row__name", doc.name),
    element("span", undefined),
    element("span", "table-row__mono", showVal(doc.keyFields.author)),
    element("span", "table-row__mono", showVal(doc.keyFields.created)),
    element("span", "table-row__mono", showVal(doc.keyFields.modified)),
    element("span", undefined),
  );
  (summary.children[2] as HTMLElement).append(
    element("span", `fmt ${fmtClass(doc.family)}`, doc.format.toUpperCase()),
  );
  const isOk = doc.status === "complete";
  (summary.children[6] as HTMLElement).append(
    element("span", isOk ? "pill pill--ok" : "pill pill--warn", isOk ? "完整" : "复核"),
  );

  const detail = element("div", "table-row__detail");

  // Key info section
  const keySection = element("div", "detail-section");
  keySection.append(element("div", "detail-section__title", "关键信息"));
  const keyGrid = element("div", "kv-grid");
  const kv = (label: string, value: string): void => {
    const item = element("div", "kv");
    item.append(element("div", "kv__label", label), element("div", "kv__value", value));
    keyGrid.append(item);
  };
  kv("作者", showVal(doc.keyFields.author));
  kv("最后修改者", showVal(doc.keyFields.lastModifiedBy));
  kv("创建时间", showVal(doc.keyFields.created));
  kv("修改时间", showVal(doc.keyFields.modified));
  kv("格式", `${doc.format.toUpperCase()} · ${doc.family}`);
  kv("文件大小", formatBytes(doc.sizeBytes));
  kv("文件指纹", doc.sha256Prefix);
  kv("相对路径", doc.relativePath);
  kv("元数据条数", `${doc.observationCount} 条`);
  keySection.append(keyGrid);
  detail.append(keySection);

  // All observations
  if (doc.observations.length > 0) {
    const obsSection = element("div", "detail-section");
    obsSection.append(element("div", "detail-section__title", "全部元数据"));
    const obsGrid = element("div", "kv-grid");
    for (const obs of doc.observations) {
      const item = element("div", "kv");
      item.append(
        element("div", "kv__label", tField(obs.label)),
        element("div", "kv__value", fmtDate(obs.value) || "—"),
      );
      obsGrid.append(item);
    }
    obsSection.append(obsGrid);
    detail.append(obsSection);
  }

  summary.addEventListener("click", () => {
    row.classList.toggle("is-open");
  });

  row.append(summary, detail);
  return row;
}

// ── Main render ───

export function renderResult(result: ScanResult): HTMLElement {
  const main = element("div", "main-scroll");
  testId(main, "result-page");

  const groupNames = new Map(result.groups.map((g) => [g.id, g.name]));

  // Trace banner
  const banner = traceBanner(result, groupNames);
  if (banner !== null) main.append(banner);

  // Summary strip
  main.append(summaryStrip(result));

  // Document table
  const tableWrap = element("div", "table-wrap");
  const head = element("div", "table-head");
  for (const h of ["投标人", "文件名", "格式", "作者", "创建时间", "修改时间", "状态"]) {
    head.append(element("span", undefined, h));
  }
  tableWrap.append(head);

  for (const group of result.groups) {
    const label = group.kind === "bidder"
      ? String.fromCharCode(65 + result.groups.indexOf(group))
      : "根目录";
    for (const doc of group.documents) {
      tableWrap.append(docRow(doc, label));
    }
  }

  main.append(tableWrap);
  return main;
}

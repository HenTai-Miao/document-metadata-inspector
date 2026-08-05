import type { DocumentSummary, ObservationSummary, ResultGroup, ScanResult, TraceSummary } from "../shared/contracts";
import { actionButton, element, formatBytes, formatScanTime, testId } from "./dom";

export interface ResultActions {
  showSelection(): void;
  rescan(): Promise<void>;
}

const FIELD_LABELS: Record<string, string> = {
  author: "作者",
  title: "标题",
  subject: "主题",
  keywords: "关键词",
  creator: "创建程序",
  producer: "生成器",
  creationdate: "创建时间",
  moddate: "修改时间",
  created: "创建时间",
  modified: "修改时间",
  create_date: "创建时间",
  modify_date: "修改时间",
  lastmodifiedby: "最后修改者",
  last_modified_by: "最后修改者",
  lastsavedby: "最后保存者",
  last_saved_by: "最后保存者",
  revision: "修订版本",
  category: "分类",
  description: "描述",
  comments: "备注",
  comment: "备注",
  company: "公司",
  manager: "经理",
  application: "应用程序",
  applicationname: "应用程序名称",
  application_name: "应用程序名称",
  appversion: "应用版本",
  app_version: "应用版本",
  template: "模板",
  totaltime: "总编辑时间",
  total_time: "总编辑时间",
  pages: "页数",
  page_count: "页数",
  words: "字数",
  word_count: "字数",
  characters: "字符数",
  character_count: "字符数",
  characterswithspaces: "含空格字符数",
  character_count_with_spaces: "含空格字符数",
  paragraphs: "段落数",
  paragraph_count: "段落数",
  lines: "行数",
  line_count: "行数",
  slides: "幻灯片数",
  slide_count: "幻灯片数",
  notes: "备注数",
  note_count: "备注数",
  hiddenslides: "隐藏幻灯片数",
  language: "语言",
  version: "版本",
  contentstatus: "内容状态",
  content_status: "内容状态",
  identifier: "标识符",
  source: "来源",
  format: "格式",
  type: "类型",
  relation: "关联",
  coverage: "覆盖范围",
  rights: "权限",
  contributor: "贡献者",
  publisher: "发布者",
  date: "日期",
  trapped: "陷印标记",
  encryption: "加密",
  password: "密码",
};

function translateField(rawName: string): string {
  const key = rawName.toLowerCase().replace(/[^a-z0-9]/g, "");
  return FIELD_LABELS[key] ?? rawName;
}

function formatMetaValue(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return "—";
  }
  // PDF date format: D:YYYYMMDDHHmmSS+TZ
  const pdfDate = trimmed.match(/^D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([+-]\d{2}'?\d{2}'?)?/);
  if (pdfDate !== null) {
    const [, y, mo, d, h, mi, s] = pdfDate;
    const parts = [`${y}-${mo}-${d}`];
    if (h !== undefined && mi !== undefined) {
      parts.push(`${h}:${mi}`);
      if (s !== undefined) {
        parts[1] += `:${s}`;
      }
    }
    return parts.join(" ");
  }
  // ISO 8601
  const isoDate = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (isoDate !== null) {
    const [, y, mo, d, h, mi] = isoDate;
    return `${y}-${mo}-${d} ${h}:${mi}`;
  }
  // Full date only ISO
  const dateOnly = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly !== null) {
    return trimmed;
  }
  return trimmed;
}

function translatedObservation(observation: ObservationSummary): ObservationSummary {
  return {
    label: translateField(observation.label),
    value: formatMetaValue(observation.value),
  };
}

function summaryMetric(label: string, value: string, id?: string): HTMLElement {
  const metric = element("div", "result-metric");
  const valueNode = element("strong", "result-metric__value", value);
  if (id !== undefined) {
    testId(valueNode, id);
  }
  metric.append(valueNode, element("span", "result-metric__label", label));
  return metric;
}

function documentRow(document: DocumentSummary): HTMLElement {
  const row = element("li", "document-row");
  const details = element("details", "document-details");
  const summary = element("summary", "document-summary-row");
  const extension = element(
    "span",
    `format-badge format-badge--${document.family}`,
    document.format.toUpperCase(),
  );
  const copy = element("span", "document-row__copy");
  copy.append(
    element("strong", "document-row__name", document.name),
    element(
      "small",
      "document-row__evidence",
      `${document.observationCount} 条元数据 · ${formatBytes(document.sizeBytes)}`,
    ),
  );
  const status = element(
    "span",
    document.status === "complete" ? "document-status is-complete" : "document-status is-partial",
    document.status === "complete" ? "提取完整" : "需复核",
  );
  const toggle = element("span", "document-details__toggle", "查看证据");
  toggle.setAttribute("aria-hidden", "true");
  summary.append(extension, copy, status, toggle);

  const evidence = element("div", "document-evidence-panel");
  const table = element("dl", "meta-grid");

  const addRow = (label: string, value: string, emphasized = false): void => {
    const dt = element("dt", "meta-label", label);
    const dd = element("dd", emphasized ? "meta-value meta-value--accent" : "meta-value", value);
    table.append(dt, dd);
  };

  addRow("相对路径", document.relativePath);
  addRow("格式", `${document.format.toUpperCase()} · ${document.family}`);
  addRow("文件指纹", document.sha256Prefix);
  addRow("提取警告", `${document.warningCount} 条`);

  for (const observation of document.observations) {
    const translated = translatedObservation(observation);
    addRow(translated.label, translated.value, true);
  }

  evidence.append(table);
  details.append(summary, evidence);
  row.append(details);
  return row;
}

function bidderPanel(group: ResultGroup, index: number): HTMLElement {
  const panel = element("details", "bidder-panel");
  panel.dataset.groupId = group.id;
  testId(panel, "bidder-card");
  if (index === 0) {
    panel.open = true;
  }
  const summary = element("summary", "bidder-panel__summary");
  const icon = element(
    "span",
    "bidder-icon",
    group.kind === "bidder" ? String.fromCharCode(65 + index) : "根",
  );
  const title = element("div", "bidder-panel__title");
  title.append(
    element(
      "span",
      "bidder-card__eyebrow",
      group.kind === "bidder" ? `投标人 ${String.fromCharCode(65 + index)}` : "未分组文件",
    ),
    element("h2", "bidder-panel__name", group.name),
  );
  summary.append(
    icon,
    title,
    element("span", "bidder-panel__count", `${group.documents.length} 个文件`),
  );
  const documents = element("ul", "document-list");
  for (const document of group.documents) {
    documents.append(documentRow(document));
  }
  panel.append(summary, documents);
  return panel;
}

export interface ConnectionTrack {
  traceIndex: number;
  fromGroupId: string;
  toGroupId: string;
  offset: number;
}

const CONNECTION_TRACK_GAP = 10;

function pairKey(left: string, right: string): string {
  return [left, right].sort().join("\0");
}

export function connectionTracks(traces: TraceSummary[]): ConnectionTrack[] {
  const edges = traces.flatMap((trace, traceIndex) => {
    const fromGroupId = trace.groupIds[0];
    if (fromGroupId === undefined) {
      return [];
    }
    return trace.groupIds.slice(1).map((toGroupId) => {
      const [canonicalFrom, canonicalTo] =
        fromGroupId.localeCompare(toGroupId) <= 0
          ? [fromGroupId, toGroupId]
          : [toGroupId, fromGroupId];
      return {
        traceIndex,
        fromGroupId: canonicalFrom,
        toGroupId: canonicalTo,
        key: pairKey(canonicalFrom, canonicalTo),
      };
    });
  });
  const totals = new Map<string, number>();
  for (const edge of edges) {
    totals.set(edge.key, (totals.get(edge.key) ?? 0) + 1);
  }
  const positions = new Map<string, number>();
  return edges.map((edge) => {
    const position = positions.get(edge.key) ?? 0;
    positions.set(edge.key, position + 1);
    const total = totals.get(edge.key) ?? 1;
    return {
      traceIndex: edge.traceIndex,
      fromGroupId: edge.fromGroupId,
      toGroupId: edge.toGroupId,
      offset: (position - (total - 1) / 2) * CONNECTION_TRACK_GAP,
    };
  });
}

function traceConnection(trace: TraceSummary, groupNames: Map<string, string>): HTMLElement {
  const connection = element("div", `trace-connection trace-connection--${trace.tone}`);
  testId(connection, trace.tone === "danger" ? "trace-danger" : "trace-neutral");
  const involvedGroups = trace.groupIds.map((id) => groupNames.get(id) ?? "未知投标人");
  const left = element("span", "trace-endpoint", involvedGroups[0] ?? "投标人");
  const right = element("span", "trace-endpoint", involvedGroups.slice(1).join(" · ") || "投标人");
  const rail = element("span", "trace-rail");
  rail.append(
    element("i", "trace-rail__dot"),
    element("i", "trace-rail__line"),
    element("i", "trace-rail__dot"),
  );
  const copy = element("span", "trace-connection__copy");
  copy.append(
    element("span", "trace-connection__label", trace.label),
    element("strong", "trace-connection__value", trace.value),
    element("small", "trace-connection__evidence", `${trace.evidenceCount} 条原始证据`),
  );
  connection.append(left, rail, copy, rail.cloneNode(true), right);
  return connection;
}

function traceSection(result: ScanResult): HTMLElement {
  const section = element("section", "trace-section");
  const heading = element("div", "section-heading");
  heading.append(
    element("div", "section-heading__copy"),
    element("span", "section-heading__legend", "红色 = 跨投标人人员痕迹"),
  );
  const copy = heading.firstElementChild as HTMLElement;
  copy.append(
    element("p", "eyebrow", "跨投标人证据连接"),
    element("h2", "section-title", "相同痕迹一眼可见"),
  );
  const groupNames = new Map(result.groups.map((group) => [group.id, group.name]));
  const board = element("div", "trace-board");

  if (result.personTraces.length === 0) {
    const empty = element("div", "person-clear");
    empty.append(
      element("span", "person-clear__icon", "✓"),
      element("strong", "person-clear__title", "未发现跨投标人人员痕迹"),
      element(
        "span",
        "person-clear__copy",
        "没有作者、最后修改者、批注者等人员字段在不同投标人间完全相同。",
      ),
    );
    board.append(empty);
  } else {
    for (const trace of result.personTraces) {
      board.append(traceConnection(trace, groupNames));
    }
  }

  for (const trace of result.contextTraces) {
    board.append(traceConnection(trace, groupNames));
  }
  section.append(heading, board);
  return section;
}

export function renderResult(result: ScanResult, actions: ResultActions): HTMLElement {
  const page = element("main", "result-page");
  testId(page, "result-page");
  const hero = element("section", "result-hero");
  const heading = element("div", "result-hero__heading");
  heading.append(
    element("p", "eyebrow", "02 / 核验结果"),
    element("h1", "result-hero__title", result.rootName),
    element(
      "p",
      "result-hero__description",
      `${formatScanTime(result.scannedAt)}完成 · 所有判断均可回溯到原始元数据证据`,
    ),
  );
  const controls = element("div", "result-actions");
  controls.append(
    actionButton("返回选择", "secondary", "back-to-selection", actions.showSelection),
    actionButton("重新核验", "primary", "rescan", actions.rescan),
  );
  hero.append(heading, controls);

  const metrics = element("section", "result-metrics");
  metrics.append(
    summaryMetric(
      "提取完成",
      `${result.completeDocumentCount} / ${result.documentCount}`,
      "summary-complete",
    ),
    summaryMetric("元数据证据", result.observationCount.toLocaleString("zh-CN")),
    summaryMetric("解析记录", result.parserRunCount.toLocaleString("zh-CN")),
    summaryMetric("人员重复痕迹", String(result.personTraces.length)),
  );

  const biddersSection = element("section", "bidders-section");
  const biddersHeading = element("div", "section-heading");
  const biddersCopy = element("div", "section-heading__copy");
  biddersCopy.append(
    element("p", "eyebrow", "投标人文件"),
    element("h2", "section-title", "各投标人文档元数据"),
  );
  biddersHeading.append(
    biddersCopy,
    element(
      "span",
      "section-heading__legend",
      `${result.bidderCount} 个投标人 · ${result.documentCount} 个文档`,
    ),
  );
  const bidderList = element("div", "bidder-list");
  result.groups.forEach((group, index) => {
    bidderList.append(bidderPanel(group, index));
  });
  biddersSection.append(biddersHeading, bidderList);

  page.append(hero, metrics, traceSection(result), biddersSection);
  return page;
}

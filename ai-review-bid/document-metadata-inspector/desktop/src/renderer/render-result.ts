import type {
  DocumentSummary,
  ObservationSummary,
  ScanResult,
  TraceSummary,
} from "../shared/contracts";
import { element, formatBytes, testId } from "./dom";

export interface ResultUiState {
  selectedGroupId: string | null;
  selectedDocumentId: string | null;
  selectGroup(groupId: string | null): void;
  selectDocument(documentId: string | null): void;
  rescan(): Promise<void>;
}

// ── Field translation & formatting ───────────────────

const FIELD_LABELS: Record<string, string> = {
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

function translateField(rawName: string): string {
  const key = rawName.toLowerCase().replace(/[^a-z0-9]/g, "");
  return FIELD_LABELS[key] ?? rawName;
}

function formatDateValue(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length === 0) return "";
  const pdf = trimmed.match(/^D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?/);
  if (pdf) {
    const [, y, mo, d, h, mi] = pdf;
    return h !== undefined && mi !== undefined ? `${y}-${mo}-${d} ${h}:${mi}` : `${y}-${mo}-${d}`;
  }
  const iso = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]} ${iso[4]}:${iso[5]}`;
  const dateOnly = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) return trimmed;
  return trimmed;
}

function translatedObservation(obs: ObservationSummary): ObservationSummary {
  return { label: translateField(obs.label), value: formatDateValue(obs.value) || "—" };
}

function displayKeyField(value: string): string {
  if (value.length === 0) return "—";
  return formatDateValue(value);
}

// ── Connection tracks (kept for tests) ───────────────

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
    if (fromGroupId === undefined) return [];
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
  for (const edge of edges) totals.set(edge.key, (totals.get(edge.key) ?? 0) + 1);
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

// ── Helpers ──────────────────────────────────────────

function familyBadgeClass(family: string): string {
  if (family === "pdf") return "badge--pdf";
  if (family === "word") return "badge--word";
  if (family === "excel") return "badge--excel";
  return "badge--default";
}

// ── Sidebar ──────────────────────────────────────────

function sidebarSection(
  result: ScanResult,
  ui: ResultUiState,
  groupNames: Map<string, string>,
): HTMLElement {
  const sidebar = element("aside", "sidebar");

  // Bidders section
  const bidderSection = element("div", "sidebar__section");
  const bidderHeading = element("div", "sidebar__heading");
  bidderHeading.append(element("span", undefined, "投标人"));
  bidderSection.append(bidderHeading);
  const bidderList = element("ul", "sidebar__list");

  const allItem = element("li", "sidebar__item");
  if (ui.selectedGroupId === null) allItem.classList.add("is-active");
  allItem.append(
    element("span", "sidebar__item-icon", "全"),
    element("span", "sidebar__item-label", "全部文档"),
    element("span", "sidebar__item-count", String(result.documentCount)),
  );
  allItem.addEventListener("click", () => ui.selectGroup(null));
  bidderList.append(allItem);

  result.groups.forEach((group, index) => {
    const item = element("li", "sidebar__item");
    if (ui.selectedGroupId === group.id) item.classList.add("is-active");
    item.append(
      element(
        "span",
        "sidebar__item-icon",
        group.kind === "bidder" ? String.fromCharCode(65 + index) : "根",
      ),
      element("span", "sidebar__item-text"),
      element("span", "sidebar__item-count", String(group.documents.length)),
    );
    const text = item.querySelector(".sidebar__item-text");
    text?.append(
      element("span", "sidebar__item-label", group.name),
      element("span", "sidebar__item-sub", `${group.documents.length} 个文件`),
    );
    item.addEventListener("click", () => ui.selectGroup(group.id));
    bidderList.append(item);
  });

  bidderSection.append(bidderList);
  sidebar.append(bidderSection);

  // Traces section
  const allTraces = [...result.personTraces, ...result.contextTraces];
  if (allTraces.length > 0) {
    const traceSection = element("div", "sidebar__section");
    const traceHeading = element("div", "sidebar__heading");
    traceHeading.append(
      element("span", undefined, "跨投标人痕迹"),
      element("span", undefined, `${allTraces.length}`),
    );
    traceSection.append(traceHeading);

    const traceList = element("ul", "trace-list");
    for (const trace of allTraces) {
      const item = element("li", `trace-item trace-item--${trace.tone}`);
      const groupLabel = trace.groupIds
        .map((id) => groupNames.get(id) ?? "未知")
        .join(" ↔ ");
      item.append(
        element("span", "trace-item__dot"),
        element("span", "trace-item__body"),
      );
      const body = item.querySelector(".trace-item__body");
      body?.append(
        element("span", "trace-item__label", trace.label),
        element("span", "trace-item__value", trace.value),
        element("span", "trace-item__groups", groupLabel),
      );
      traceList.append(item);
    }
    traceSection.append(traceList);
    sidebar.append(traceSection);
  }

  return sidebar;
}

// ── Document table ───────────────────────────────────

function documentTable(
  result: ScanResult,
  ui: ResultUiState,
): { wrap: HTMLElement; selectedDoc: DocumentSummary | null } {
  const groups = result.groups;
  const visibleGroups =
    ui.selectedGroupId !== null
      ? groups.filter((g) => g.id === ui.selectedGroupId)
      : groups;
  const allDocs = visibleGroups.flatMap((g) => g.documents);
  const selectedDoc =
    allDocs.find((d) => d.id === ui.selectedDocumentId) ?? null;

  const wrap = element("div", "doc-table-wrap");

  const head = element("div", "doc-table-head");
  const groupLabel =
    ui.selectedGroupId !== null
      ? (groups.find((g) => g.id === ui.selectedGroupId)?.name ?? "投标人")
      : "全部文档";
  head.append(
    element("span", "doc-table-head__title", groupLabel),
    element("span", "doc-table-head__meta", `${allDocs.length} 个文档`),
  );
  wrap.append(head);

  const scroll = element("div", "doc-table-scroll");
  const table = element("table", "doc-table");

  // Header
  const thead = element("thead");
  const headerRow = element("tr");
  for (const label of ["文件名", "格式", "作者", "创建时间", "修改时间", "状态"]) {
    headerRow.append(element("th", undefined, label));
  }
  thead.append(headerRow);
  table.append(thead);

  // Body
  const tbody = element("tbody");
  if (allDocs.length === 0) {
    const emptyRow = element("tr");
    const emptyCell = element("td", "doc-table__empty", "该投标人目录下没有支持的文档");
    emptyCell.colSpan = 6;
    emptyCell.style.padding = "32px";
    emptyRow.append(emptyCell);
    tbody.append(emptyRow);
  } else {
    for (const doc of allDocs) {
      const row = element("tr");
      if (doc.id === ui.selectedDocumentId) row.classList.add("is-selected");
      row.addEventListener("click", () => ui.selectDocument(doc.id));

      row.append(
        element("td", "doc-table__name", doc.name),
        element("td", undefined),
        element("td", "doc-table__mono", displayKeyField(doc.keyFields.author)),
        element("td", "doc-table__mono", displayKeyField(doc.keyFields.created)),
        element("td", "doc-table__mono", displayKeyField(doc.keyFields.modified)),
        element("td", undefined),
      );
      const formatCell = row.children[1] as HTMLElement;
      formatCell.append(
        element("span", `badge ${familyBadgeClass(doc.family)}`, doc.format.toUpperCase()),
      );
      const statusCell = row.children[5] as HTMLElement;
      const isComplete = doc.status === "complete";
      statusCell.append(
        element(
          "span",
          isComplete ? "status-pill status-pill--ok" : "status-pill status-pill--warn",
          isComplete ? "完整" : "需复核",
        ),
      );
      tbody.append(row);
    }
  }
  table.append(tbody);
  scroll.append(table);
  wrap.append(scroll);

  return { wrap, selectedDoc };
}

// ── Detail panel ─────────────────────────────────────

function detailPanel(doc: DocumentSummary | null): HTMLElement {
  const panel = element("aside", "detail-panel");
  testId(panel, "detail-panel");

  if (doc === null) {
    panel.append(
      element("div", "detail-panel__empty", "选择文档查看元数据明细"),
    );
    return panel;
  }

  const head = element("div", "detail-panel__head");
  head.append(
    element("span", undefined),
    element("span", `badge ${familyBadgeClass(doc.family)}`, doc.format.toUpperCase()),
  );
  const nameWrap = head.firstElementChild;
  nameWrap?.append(
    element("div", "detail-panel__name", doc.name),
    element(
      "div",
      "detail-panel__sub",
      `${doc.relativePath} · ${formatBytes(doc.sizeBytes)}`,
    ),
  );
  panel.append(head);

  const body = element("div", "detail-panel__body");

  // Key fields section
  const kf = doc.keyFields;
  const keySection = element("div", "meta-section");
  keySection.append(element("div", "meta-section__title", "关键信息"));
  const keyItems: Array<[string, string]> = [
    ["作者", kf.author],
    ["最后修改者", kf.lastModifiedBy],
    ["创建时间", kf.created],
    ["修改时间", kf.modified],
    ["文件指纹", doc.sha256Prefix],
    ["元数据条数", `${doc.observationCount} 条`],
  ];
  for (const [label, rawValue] of keyItems) {
    const value = ["创建时间", "修改时间"].includes(label)
      ? displayKeyField(rawValue)
      : rawValue.length > 0 ? rawValue : "—";
    const row = element("div", "meta-row");
    row.append(
      element("span", "meta-row__label", label),
      element("span", "meta-row__value", value),
    );
    keySection.append(row);
  }
  body.append(keySection);

  // All observations
  if (doc.observations.length > 0) {
    const obsSection = element("div", "meta-section");
    obsSection.append(element("div", "meta-section__title", "全部元数据"));
    for (const obs of doc.observations) {
      const translated = translatedObservation(obs);
      const row = element("div", "meta-row");
      row.append(
        element("span", "meta-row__label", translated.label),
        element("span", "meta-row__value", translated.value),
      );
      obsSection.append(row);
    }
    body.append(obsSection);
  }

  panel.append(body);
  return panel;
}

// ── Main render ──────────────────────────────────────

export function renderResult(result: ScanResult, ui: ResultUiState): HTMLElement {
  const groupNames = new Map(result.groups.map((g) => [g.id, g.name]));
  const workspace = element("div", "workspace workspace--detail");
  const { wrap: tableWrap, selectedDoc } = documentTable(result, ui);

  workspace.append(
    sidebarSection(result, ui, groupNames),
    tableWrap,
    detailPanel(selectedDoc),
  );

  return workspace;
}

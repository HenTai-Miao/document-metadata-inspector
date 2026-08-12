import type { DocumentDetail, DocumentSummary, ScanResult } from "../shared/contracts";
import { bidderLabel, buildGroupNames, element, normFieldKey, testId } from "./dom";
import { tField } from "./render-result";

export interface MetadataActions {
  backToReport(): void;
  loadDocumentDetail(documentId: string): Promise<DocumentDetail>;
}

export function createDocumentDetailLoader(
  load: (documentId: string) => Promise<DocumentDetail>,
): (documentId: string) => Promise<DocumentDetail> {
  const requests = new Map<string, Promise<DocumentDetail>>();
  return (documentId) => {
    const existing = requests.get(documentId);
    if (existing !== undefined) {
      return existing;
    }
    const request = load(documentId);
    requests.set(documentId, request);
    return request;
  };
}

// ── Helpers ──────────────────────────────────────────────────────

interface DupRef {
  company: string;
  file: string;
}

/** A trace that involves a given document, keyed for observation matching. */
interface DupTrace {
  fieldKeys: Set<string>;
  value: string;
  refs: DupRef[];
}

/** Build doc-id → { groupId, docName } lookup. */
function buildDocInfo(result: ScanResult): Map<string, { groupId: string; name: string }> {
  const map = new Map<string, { groupId: string; name: string }>();
  for (const group of result.groups) {
    for (const doc of group.documents) {
      map.set(doc.id, { groupId: group.id, name: doc.name });
    }
  }
  return map;
}

/** Build doc-id → list of traces that reference this doc (with cross-refs).
 *  Keyed by doc-id only so matching survives differing raw values within a trace. */
function buildDupMap(
  result: ScanResult,
  groupNames: Map<string, string>,
  docInfo: Map<string, { groupId: string; name: string }>,
): Map<string, DupTrace[]> {
  const map = new Map<string, DupTrace[]>();
  const traces = [...result.personTraces, ...result.cautionTraces];
  for (const trace of traces) {
    const fieldKeys = new Set(trace.fieldNames.map(normFieldKey));
    for (const docId of trace.documentIds) {
      const refs: DupRef[] = [];
      for (const otherDocId of trace.documentIds) {
        if (otherDocId === docId) continue;
        const info = docInfo.get(otherDocId);
        if (info !== undefined) {
          refs.push({
            company: groupNames.get(info.groupId) ?? info.groupId,
            file: info.name,
          });
        }
      }
      if (refs.length > 0) {
        const list = map.get(docId);
        const entry: DupTrace = { fieldKeys, value: trace.value, refs };
        if (list !== undefined) {
          list.push(entry);
        } else {
          map.set(docId, [entry]);
        }
      }
    }
  }
  return map;
}

/** Check whether an observation matches a trace by field name or value. */
function matchesTrace(obs: { label: string; value: string }, trace: DupTrace): boolean {
  return trace.fieldKeys.has(normFieldKey(obs.label)) || obs.value === trace.value;
}

/** Format family → compact tag label + CSS class suffix. */
function familyTag(family: string): { label: string; cls: string } {
  switch (family) {
    case "pdf":
      return { label: "PDF", cls: "md-tag--pdf" };
    case "word":
      return { label: "DOC", cls: "md-tag--doc" };
    case "excel":
      return { label: "XLS", cls: "md-tag--xls" };
    default:
      return { label: family.slice(0, 3).toUpperCase() || "DOC", cls: "md-tag--other" };
  }
}

// ── Card builder ─────────────────────────────────────────────────

function documentCard(
  doc: DocumentSummary,
  dupMap: Map<string, DupTrace[]>,
  dupDocIds: Set<string>,
  loadDetail: (documentId: string) => Promise<DocumentDetail>,
): HTMLElement {
  const card = element("div", "md-doc");
  if (dupDocIds.has(doc.id)) card.classList.add("has-dup");

  // Header
  const header = element("div", "md-doc__header");
  const tag = familyTag(doc.family);
  header.append(element("span", `md-tag ${tag.cls}`, tag.label));
  header.append(element("span", "md-doc__name", doc.name));

  const docTraces = dupMap.get(doc.id);
  const summary = element(
    "span",
    docTraces === undefined ? "md-doc__summary" : "md-doc__dup",
    docTraces === undefined
      ? `${doc.observationCount.toLocaleString("zh-CN")} 个字段`
      : `含跨投标人重复 · ${doc.observationCount.toLocaleString("zh-CN")} 个字段`,
  );
  header.append(summary);

  const chevron = element("span", "md-doc__chevron");
  chevron.innerHTML =
    '<svg viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  header.append(chevron);
  card.append(header);

  const body = element("div", "md-doc__body");
  card.append(body);

  let requested = false;
  header.addEventListener("click", async () => {
    const opening = !card.classList.contains("is-open");
    card.classList.toggle("is-open", opening);
    if (!opening || requested) {
      return;
    }
    requested = true;
    body.replaceChildren(element("div", "md-detail-state", "正在读取文档元数据…"));
    try {
      const detail = await loadDetail(doc.id);
      const rows = detail.observations.map((observation) => {
        const row = element("div", "md-row");
        row.append(element("span", "md-row__label", tField(observation.label)));
        const valueCell = element("div", "md-row__cell");
        const matchingTrace = docTraces?.find((trace) => matchesTrace(observation, trace));
        if (matchingTrace === undefined) {
          valueCell.append(element("span", "md-row__value", observation.value));
        } else {
          valueCell.append(element("span", "md-row__value md-row__value--dup", observation.value));
          const duplicateDetail = element("div", "md-dup-detail");
          for (const ref of matchingTrace.refs) {
            const chip = element("span", "md-dup-chip");
            chip.append(
              element("span", "md-dup-chip__co", ref.company),
              element("span", "md-dup-chip__sep", "›"),
              element("span", "md-dup-chip__file", ref.file),
            );
            duplicateDetail.append(chip);
          }
          valueCell.append(duplicateDetail);
        }
        row.append(valueCell);
        return row;
      });
      const duplicateCount = detail.observations.filter((observation) =>
        docTraces?.some((trace) => matchesTrace(observation, trace)),
      ).length;
      if (duplicateCount > 0) {
        summary.className = "md-doc__dup";
        summary.textContent = `${duplicateCount.toLocaleString("zh-CN")} 处重复`;
      }
      if (doc.parserRuns.length > 0) {
        const parserRow = element("div", "md-row md-row--footer");
        const parserCell = element("div", "md-row__cell");
        parserCell.append(
          element("span", "md-row__value", doc.parserRuns.map((run) => run.name).join(" · ")),
        );
        parserRow.append(element("span", "md-row__label", "解析链"), parserCell);
        rows.push(parserRow);
      }
      body.replaceChildren(
        ...(rows.length > 0
          ? rows
          : [element("div", "md-detail-state", "该文档没有可展示的元数据字段")]),
      );
    } catch {
      body.replaceChildren(
        element(
          "div",
          "md-detail-state md-detail-state--error",
          "文档详情加载失败，请返回报告后重新打开",
        ),
      );
    }
  });
  header.style.cursor = "pointer";

  return card;
}

// ── Page renderer ────────────────────────────────────────────────

export function renderMetadata(result: ScanResult, actions: MetadataActions): HTMLElement {
  const main = element("div", "md-page");
  testId(main, "metadata-page");

  const groupNames = buildGroupNames(result);
  const docInfo = buildDocInfo(result);
  const dupMap = buildDupMap(result, groupNames, docInfo);
  const dupDocIds = new Set<string>(dupMap.keys());
  const loadDetail = createDocumentDetailLoader(actions.loadDocumentDetail);

  // ── Page header ──
  const header = element("div", "md-header");

  const backBtn = element("button", "md-back");
  backBtn.innerHTML =
    '<svg viewBox="0 0 16 16" width="16" height="16" fill="none"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  backBtn.addEventListener("click", () => actions.backToReport());

  const headerInfo = element("div", "md-header__info");
  headerInfo.append(
    element("div", "md-header__title", "元数据明细"),
    element(
      "div",
      "md-header__sub",
      `${result.documentCount} 个文件 · ${result.bidderCount} 个投标人 · ${result.observationCount.toLocaleString("zh-CN")} 条元数据`,
    ),
  );

  const legend = element("div", "md-legend");
  legend.innerHTML = '<span class="md-legend__dot"></span> 跨投标人重复';

  header.append(backBtn, headerInfo, element("div", "md-header__spacer"), legend);

  // ── Filter bar ──
  const filterBar = element("div", "md-filter");

  const allPill = element("button", "md-pill is-active");
  allPill.append(
    element("span", undefined, "全部"),
    element("span", "md-pill__count", String(result.documentCount)),
  );
  filterBar.append(allPill);

  let bidderIdx = 0;
  for (const group of result.groups) {
    if (group.kind !== "bidder") continue;
    const letter = bidderLabel(bidderIdx);
    bidderIdx++;
    const pill = element("button", "md-pill");
    pill.dataset.bidder = group.id;
    const badge = element("span", "md-pill__badge", letter);
    pill.append(
      badge,
      element("span", undefined, group.name),
      element("span", "md-pill__count", String(group.documents.length)),
    );
    filterBar.append(pill);
  }

  // ── Scroll area ──
  const scroll = element("div", "md-scroll");

  bidderIdx = 0;
  for (const group of result.groups) {
    if (group.kind !== "bidder") continue;
    const letter = bidderLabel(bidderIdx);
    bidderIdx++;

    const section = element("div", "md-bidder");
    section.dataset.bidder = group.id;

    const sectionHeader = element("div", "md-bidder__head");
    sectionHeader.append(
      element("span", "md-bidder__badge", letter),
      element("span", "md-bidder__name", group.name),
      element("span", "md-bidder__line"),
      element("span", "md-bidder__count", `${group.documents.length} 个文件`),
    );
    section.append(sectionHeader);

    for (const doc of group.documents) {
      section.append(documentCard(doc, dupMap, dupDocIds, loadDetail));
    }
    scroll.append(section);
  }

  // ── Filter pill handlers ──
  const pills = filterBar.querySelectorAll(".md-pill");
  pills.forEach((pill) => {
    pill.addEventListener("click", () => {
      pills.forEach((p) => {
        p.classList.remove("is-active");
      });
      pill.classList.add("is-active");
      const bidderId = (pill as HTMLElement).dataset.bidder;
      const sections = scroll.querySelectorAll<HTMLElement>(".md-bidder");
      sections.forEach((s) => {
        s.style.display = !bidderId || s.dataset.bidder === bidderId ? "" : "none";
      });
    });
  });

  main.append(header, filterBar, scroll);
  return main;
}

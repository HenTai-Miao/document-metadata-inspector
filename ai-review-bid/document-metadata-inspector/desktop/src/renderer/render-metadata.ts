import type { DocumentSummary, ScanResult } from "../shared/contracts";
import { element, testId } from "./dom";
import { tField } from "./render-result";

export interface MetadataActions {
  backToReport(): void;
}

// ── Helpers ──────────────────────────────────────────────────────

interface DupRef {
  company: string;
  file: string;
}

/** Map groupId → group name (company name). */
function buildGroupNames(result: ScanResult): Map<string, string> {
  const names = new Map<string, string>();
  for (const group of result.groups) {
    names.set(group.id, group.name);
  }
  return names;
}

/** Build doc-id → {groupId, docName} lookup. */
function buildDocInfo(result: ScanResult): Map<string, { groupId: string; name: string }> {
  const map = new Map<string, { groupId: string; name: string }>();
  for (const group of result.groups) {
    for (const doc of group.documents) {
      map.set(doc.id, { groupId: group.id, name: doc.name });
    }
  }
  return map;
}

/** Key → "docId\0value", value → list of {company, file} refs (excluding current doc). */
function buildDupMap(
  result: ScanResult,
  groupNames: Map<string, string>,
  docInfo: Map<string, { groupId: string; name: string }>,
): Map<string, DupRef[]> {
  const map = new Map<string, DupRef[]>();
  const traces = [...result.personTraces, ...result.cautionTraces];
  for (const trace of traces) {
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
        map.set(`${docId}\0${trace.value}`, refs);
      }
    }
  }
  return map;
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
  dupMap: Map<string, DupRef[]>,
  dupDocIds: Set<string>,
): HTMLElement {
  const card = element("div", "md-doc");
  if (dupDocIds.has(doc.id)) card.classList.add("has-dup");

  // Header
  const header = element("div", "md-doc__header");
  const tag = familyTag(doc.family);
  header.append(element("span", `md-tag ${tag.cls}`, tag.label));
  header.append(element("span", "md-doc__name", doc.name));

  const dupCount = doc.observations.filter((o) =>
    dupMap.has(`${doc.id}\0${o.value}`),
  ).length;
  if (dupCount > 0) {
    header.append(
      element("span", "md-doc__dup", `${dupCount} 处重复`),
    );
  } else {
    header.append(
      element("span", "md-doc__summary", `${doc.observations.length} 个字段`),
    );
  }

  const chevron = element("span", "md-doc__chevron");
  chevron.innerHTML =
    '<svg viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  header.append(chevron);
  card.append(header);

  const body = element("div", "md-doc__body");

  for (const obs of doc.observations) {
    const row = element("div", "md-row");
    row.append(element("span", "md-row__label", tField(obs.label)));

    const valueCell = element("div", "md-row__cell");
    const dupKey = `${doc.id}\0${obs.value}`;
    const refs = dupMap.get(dupKey);
    if (refs !== undefined) {
      valueCell.append(element("span", "md-row__value md-row__value--dup", obs.value));
      const detail = element("div", "md-dup-detail");
      for (const ref of refs) {
        const chip = element("span", "md-dup-chip");
        chip.append(
          element("span", "md-dup-chip__co", ref.company),
          element("span", "md-dup-chip__sep", "›"),
          element("span", "md-dup-chip__file", ref.file),
        );
        detail.append(chip);
      }
      valueCell.append(detail);
    } else {
      valueCell.append(element("span", "md-row__value", obs.value));
    }
    row.append(valueCell);
    body.append(row);
  }

  // Parser run info
  if (doc.parserRuns.length > 0) {
    const parserRow = element("div", "md-row md-row--footer");
    const parserCell = element("div", "md-row__cell");
    parserCell.append(
      element("span", "md-row__value",
        doc.parserRuns.map((p) => p.name).join(" · ")),
    );
    parserRow.append(element("span", "md-row__label", "解析链"), parserCell);
    body.append(parserRow);
  }

  card.append(body);

  // Toggle handler
  header.addEventListener("click", () => {
    card.classList.toggle("is-open");
  });
  header.style.cursor = "pointer";

  return card;
}

// ── Page renderer ────────────────────────────────────────────────

export function renderMetadata(
  result: ScanResult,
  actions: MetadataActions,
): HTMLElement {
  const main = element("div", "md-page");
  testId(main, "metadata-page");

  const groupNames = buildGroupNames(result);
  const docInfo = buildDocInfo(result);
  const dupMap = buildDupMap(result, groupNames, docInfo);
  const dupDocIds = new Set<string>(
    Array.from(dupMap.keys()).map((k) => k.split("\0")[0]!),
  );

  // ── Page header ──
  const header = element("div", "md-header");

  const backBtn = element("button", "md-back");
  backBtn.innerHTML =
    '<svg viewBox="0 0 16 16" width="16" height="16" fill="none"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  backBtn.addEventListener("click", () => actions.backToReport());

  const headerInfo = element("div", "md-header__info");
  headerInfo.append(
    element("div", "md-header__title", "元数据明细"),
    element("div", "md-header__sub",
      `${result.documentCount} 个文件 · ${result.bidderCount} 个投标人 · ${result.observationCount.toLocaleString("zh-CN")} 条元数据`),
  );

  const legend = element("div", "md-legend");
  legend.innerHTML =
    '<span class="md-legend__dot"></span> 跨投标人重复';

  header.append(backBtn, headerInfo, element("div", "md-header__spacer"), legend);

  // ── Filter bar ──
  const filterBar = element("div", "md-filter");

  const allPill = element("button", "md-pill is-active");
  allPill.append(element("span", undefined, "全部"), element("span", "md-pill__count", String(result.documentCount)));
  filterBar.append(allPill);

  let bidderIdx = 0;
  for (const group of result.groups) {
    if (group.kind !== "bidder") continue;
    const letter = String.fromCharCode(65 + bidderIdx);
    bidderIdx++;
    const pill = element("button", "md-pill");
    pill.dataset.bidder = group.id;
    const badge = element("span", "md-pill__badge", letter);
    pill.append(badge, element("span", undefined, group.name), element("span", "md-pill__count", String(group.documents.length)));
    filterBar.append(pill);
  }

  // ── Scroll area ──
  const scroll = element("div", "md-scroll");

  bidderIdx = 0;
  for (const group of result.groups) {
    if (group.kind !== "bidder") continue;
    const letter = String.fromCharCode(65 + bidderIdx);
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
      section.append(documentCard(doc, dupMap, dupDocIds));
    }
    scroll.append(section);
  }

  // ── Filter pill handlers ──
  const pills = filterBar.querySelectorAll(".md-pill");
  pills.forEach((pill) => {
    pill.addEventListener("click", () => {
      pills.forEach((p) => p.classList.remove("is-active"));
      pill.classList.add("is-active");
      const bidderId = (pill as HTMLElement).dataset.bidder;
      const sections = scroll.querySelectorAll<HTMLElement>(".md-bidder");
      sections.forEach((s) => {
        s.style.display =
          !bidderId || s.dataset.bidder === bidderId ? "" : "none";
      });
    });
  });

  main.append(header, filterBar, scroll);
  return main;
}

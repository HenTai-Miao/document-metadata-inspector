import type { DocumentSummary, ResultGroup, ScanResult, TraceSummary } from "../shared/contracts";
import { actionButton, element, formatBytes, formatScanTime, testId } from "./dom";

export interface ResultActions {
  showSelection(): void;
  rescan(): Promise<void>;
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
      `${document.observationCount} 条元数据 · ${document.parserRunCount} 个解析器 · ${formatBytes(document.sizeBytes)}`,
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
  const facts = element("dl", "document-detail-grid");
  const appendFact = (label: string, value: string): void => {
    facts.append(element("dt", "document-detail__label", label));
    facts.append(element("dd", "document-detail__value", value));
  };
  appendFact("相对路径", document.relativePath);
  appendFact("格式识别", `${document.format.toUpperCase()} · ${document.family}`);
  appendFact("文件指纹", `SHA-256 ${document.sha256Prefix}…`);
  appendFact("提取警告", `${document.warningCount} 条`);

  const parserHeading = element("strong", "parser-run-heading", "解析器运行明细");
  const parserList = element("ul", "parser-run-list");
  for (const parser of document.parserRuns) {
    const parserRow = element("li", "parser-run-row");
    const parserStatus = element(
      "span",
      parser.status === "succeeded" ? "parser-run-status is-succeeded" : "parser-run-status",
      parser.status === "succeeded" ? "成功" : parser.status,
    );
    parserRow.append(
      element("code", "parser-run-name", parser.name),
      parserStatus,
      element("span", "parser-run-warning", `${parser.warningCount} 条警告`),
    );
    parserList.append(parserRow);
  }
  if (document.parserRuns.length === 0) {
    parserList.append(element("li", "parser-run-empty", "未记录解析器运行明细"));
  }
  evidence.append(facts, parserHeading, parserList);
  details.append(summary, evidence);
  row.append(details);
  return row;
}

function bidderCard(group: ResultGroup, index: number): HTMLElement {
  const card = element("article", "bidder-card");
  card.dataset.groupId = group.id;
  testId(card, "bidder-card");
  const header = element("header", "bidder-card__header");
  const icon = element(
    "span",
    "bidder-icon",
    group.kind === "bidder" ? String.fromCharCode(65 + index) : "根",
  );
  const title = element("div", "bidder-card__title");
  title.append(
    element(
      "span",
      "bidder-card__eyebrow",
      group.kind === "bidder" ? `投标人 ${String.fromCharCode(65 + index)}` : "未分组文件",
    ),
    element("h2", "bidder-card__name", group.name),
  );
  header.append(
    icon,
    title,
    element("span", "bidder-card__count", `${group.documents.length} 个文件`),
  );
  const documents = element("ul", "document-list");
  for (const document of group.documents) {
    documents.append(documentRow(document));
  }
  card.append(header, documents);
  return card;
}

function svgElement<K extends keyof SVGElementTagNameMap>(
  tag: K,
  className?: string,
): SVGElementTagNameMap[K] {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  if (className !== undefined) {
    node.setAttribute("class", className);
  }
  return node;
}

function connectionPoint(from: DOMRect, to: DOMRect, stage: DOMRect): { x: number; y: number } {
  const fromCenterX = from.left + from.width / 2;
  const fromCenterY = from.top + Math.min(from.height / 2, 40);
  const toCenterX = to.left + to.width / 2;
  const toCenterY = to.top + Math.min(to.height / 2, 40);
  const horizontal = Math.abs(toCenterX - fromCenterX) >= Math.abs(toCenterY - fromCenterY);
  if (horizontal) {
    return {
      x: (toCenterX >= fromCenterX ? from.right : from.left) - stage.left,
      y: fromCenterY - stage.top,
    };
  }
  return {
    x: fromCenterX - stage.left,
    y: (toCenterY >= fromCenterY ? from.bottom : from.top) - stage.top,
  };
}

function pathData(from: { x: number; y: number }, to: { x: number; y: number }): string {
  if (Math.abs(to.x - from.x) >= Math.abs(to.y - from.y)) {
    const middleX = (from.x + to.x) / 2;
    return `M ${from.x} ${from.y} C ${middleX} ${from.y}, ${middleX} ${to.y}, ${to.x} ${to.y}`;
  }
  const middleY = (from.y + to.y) / 2;
  return `M ${from.x} ${from.y} C ${from.x} ${middleY}, ${to.x} ${middleY}, ${to.x} ${to.y}`;
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

function offsetConnection(
  from: { x: number; y: number },
  to: { x: number; y: number },
  offset: number,
): { from: { x: number; y: number }; to: { x: number; y: number } } {
  const deltaX = to.x - from.x;
  const deltaY = to.y - from.y;
  const length = Math.hypot(deltaX, deltaY);
  if (length === 0 || offset === 0) {
    return { from, to };
  }
  const offsetX = (-deltaY / length) * offset;
  const offsetY = (deltaX / length) * offset;
  return {
    from: { x: from.x + offsetX, y: from.y + offsetY },
    to: { x: to.x + offsetX, y: to.y + offsetY },
  };
}

function drawBidderConnections(
  stage: HTMLElement,
  overlay: SVGSVGElement,
  cards: Map<string, HTMLElement>,
  traces: TraceSummary[],
): void {
  if (!stage.isConnected) {
    return;
  }
  const stageBounds = stage.getBoundingClientRect();
  if (stageBounds.width === 0 || stageBounds.height === 0) {
    return;
  }
  overlay.setAttribute("viewBox", `0 0 ${stageBounds.width} ${stageBounds.height}`);
  overlay.replaceChildren();

  for (const track of connectionTracks(traces)) {
    const trace = traces[track.traceIndex];
    const originCard = cards.get(track.fromGroupId);
    const targetCard = cards.get(track.toGroupId);
    if (trace === undefined || originCard === undefined || targetCard === undefined) {
      continue;
    }
    const originBounds = originCard.getBoundingClientRect();
    const targetBounds = targetCard.getBoundingClientRect();
    const points = offsetConnection(
      connectionPoint(originBounds, targetBounds, stageBounds),
      connectionPoint(targetBounds, originBounds, stageBounds),
      track.offset,
    );
    const group = svgElement("g", `bidder-connection bidder-connection--${trace.tone}`);
    group.setAttribute("data-testid", "bidder-connection");
    group.setAttribute("data-from-group", track.fromGroupId);
    group.setAttribute("data-to-group", track.toGroupId);
    group.setAttribute("data-track-offset", String(track.offset));
    const title = svgElement("title");
    title.textContent = `${trace.label}：${trace.value}`;
    const path = svgElement("path", "bidder-connection__path");
    path.setAttribute("d", pathData(points.from, points.to));
    const fromDot = svgElement("circle", "bidder-connection__dot");
    fromDot.setAttribute("cx", String(points.from.x));
    fromDot.setAttribute("cy", String(points.from.y));
    fromDot.setAttribute("r", "5");
    const toDot = svgElement("circle", "bidder-connection__dot");
    toDot.setAttribute("cx", String(points.to.x));
    toDot.setAttribute("cy", String(points.to.y));
    toDot.setAttribute("r", "5");
    group.append(title, path, fromDot, toDot);
    overlay.append(group);
  }
}

function installBidderConnections(
  stage: HTMLElement,
  overlay: SVGSVGElement,
  cards: Map<string, HTMLElement>,
  traces: TraceSummary[],
): void {
  if (traces.length === 0) {
    return;
  }
  window.requestAnimationFrame(() => {
    drawBidderConnections(stage, overlay, cards, traces);
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => {
      if (!stage.isConnected) {
        observer.disconnect();
        return;
      }
      drawBidderConnections(stage, overlay, cards, traces);
    });
    observer.observe(stage);
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
    summaryMetric("解析器运行", result.parserRunCount.toLocaleString("zh-CN")),
    summaryMetric("人员重复痕迹", String(result.personTraces.length)),
  );

  const biddersSection = element("section", "bidders-section");
  const biddersHeading = element("div", "section-heading");
  const biddersCopy = element("div", "section-heading__copy");
  biddersCopy.append(
    element("p", "eyebrow", "投标人文件边界"),
    element("h2", "section-title", "每个投标人的文件只在组内归集"),
  );
  biddersHeading.append(
    biddersCopy,
    element(
      "span",
      "section-heading__legend",
      `${result.bidderCount} 个投标人 · ${result.documentCount} 个文档`,
    ),
  );
  const bidderMap = element("div", "bidder-map");
  const bidderGrid = element("div", "bidder-grid");
  const connections = svgElement("svg", "bidder-connections");
  connections.setAttribute("aria-hidden", "true");
  const bidderCards = new Map<string, HTMLElement>();
  result.groups.forEach((group, index) => {
    const card = bidderCard(group, index);
    bidderCards.set(group.id, card);
    bidderGrid.append(card);
  });
  bidderMap.append(bidderGrid, connections);
  biddersSection.append(biddersHeading, bidderMap);

  page.append(hero, metrics, traceSection(result), biddersSection);
  installBidderConnections(bidderMap, connections, bidderCards, [
    ...result.contextTraces,
    ...result.personTraces,
  ]);
  return page;
}

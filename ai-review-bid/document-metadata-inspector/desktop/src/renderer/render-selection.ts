import type { AppState } from "./state";
import { actionButton, element, formatBytes, testId } from "./dom";

export interface WorkspaceActions {
  chooseFolder(): Promise<void>;
  startScan(): Promise<void>;
  stopScan(): Promise<void>;
}

// ── Visual building blocks ───────────────────────────────────────

/** CSS-drawn folder icon — no raster assets needed. */
function folderGlyph(): HTMLElement {
  const glyph = element("div", "folder-glyph");
  glyph.setAttribute("aria-hidden", "true");
  glyph.append(element("span", "folder-glyph__tab"), element("span", "folder-glyph__body"));
  return glyph;
}

// ── States ───────────────────────────────────────────────────────

/** Document illustration: three overlapping docs + magnifier lens (pure CSS).
 *  When `scanning` is true, the lens is replaced by an animated scan beam. */
function docIllustration(scanning = false): HTMLElement {
  const wrap = element("div", `ws-empty__illust${scanning ? " ws-empty__illust--scanning" : ""}`);
  wrap.setAttribute("aria-hidden", "true");

  const docs: [string, string, string][] = [
    ["1", "pdf", "PDF"],
    ["2", "doc", "DOC"],
    ["3", "xls", "XLS"],
  ];
  for (const [idx, tagClass, tagText] of docs) {
    const doc = element("div", `ws-empty__doc ws-empty__doc--${idx}`);
    doc.append(
      element("span", `ws-empty__doc-tag ws-empty__doc-tag--${tagClass}`, tagText),
      element("span", "ws-empty__doc-line ws-empty__doc-line--mid"),
      element("span", "ws-empty__doc-line ws-empty__doc-line--short"),
    );
    wrap.append(doc);
  }

  if (scanning) {
    wrap.append(element("div", "ws-empty__illust-beam"));
  } else {
    const lens = element("div", "ws-empty__lens");
    lens.append(element("div", "ws-empty__lens-inner"));
    wrap.append(lens);
  }

  return wrap;
}

/** No folder selected — centered card with document illustration. */
function emptyState(actions: WorkspaceActions): HTMLElement {
  const main = element("div", "ws-empty");
  testId(main, "selection-page");

  const card = element("div", "ws-empty__card");
  card.append(
    docIllustration(),
    element("h2", "ws-empty__title", "选择投标文件目录"),
    element("p", "ws-empty__desc",
      "程序将自动识别投标人文件夹，提取 PDF / Word / Excel 文档的作者、修改者等元数据痕迹，全程离线运行，文件不会上传。"),
  );

  const btn = actionButton("选择文件夹", "primary", "choose-folder", actions.chooseFolder);
  btn.classList.add("btn--lg");
  const icon = element("span", "btn__icon");
  icon.innerHTML =
    '<svg viewBox="0 0 16 16" width="16" height="16" fill="none">' +
    '<path d="M2 5V3.5A1.5 1.5 0 0 1 3.5 2h2.586a1 1 0 0 1 .707.293l1.414 1.414a1 1 0 0 0 .707.293H12.5A1.5 1.5 0 0 1 14 5.5v6A1.5 1.5 0 0 1 12.5 13h-9A1.5 1.5 0 0 1 2 11.5V5z" stroke="currentColor" stroke-width="1.4"/></svg>';
  btn.prepend(icon);
  card.append(btn);

  const trust = element("div", "ws-empty__trust");
  for (const text of ["离线运行", "不上传文件", "本地解析"]) {
    const item = element("div", "ws-empty__trust-item");
    item.append(element("span", "ws-empty__trust-dot"), element("span", undefined, text));
    trust.append(item);
  }
  card.append(trust);

  main.append(card);
  return main;
}

/** Scanning / blocked — centered card with animated illustration + progress. */
function scanningState(state: AppState, actions: WorkspaceActions): HTMLElement {
  const main = element("div", "ws-scan");
  testId(main, "scan-progress");

  const card = element("div", "ws-scan__card");
  card.append(docIllustration(true));

  // Status badge
  const badge = element("div", "ws-scan__badge");
  badge.append(
    element("span", "ws-scan__badge-dot"),
    element("span", undefined, state.status === "blocked" ? "已暂停" : "正在核验"),
  );
  card.append(badge);

  // Folder name
  if (state.selection !== null) {
    card.append(element("div", "ws-scan__folder", state.selection.rootName));
  }

  // Progress message
  card.append(element("p", "ws-scan__msg", state.progress.message));

  // Error (if blocked)
  if (state.status === "blocked" && state.error !== null) {
    const err = element("div", "ws-scan__error", state.error);
    err.setAttribute("role", "alert");
    card.append(err);
  }

  // Progress bar
  const wrap = element("div", "ws-scan__progress");
  const row = element("div", "ws-scan__progress-row");
  row.append(
    element("span", "ws-scan__progress-detail",
      state.status === "blocked" ? "等待用户操作" : "离线解析中"),
    element("span", "ws-scan__progress-pct", `${state.progress.percent}%`),
  );
  const track = element("div", "ws-scan__progress-track");
  const fill = element("div", "ws-scan__progress-fill");
  fill.style.width = `${state.progress.percent}%`;
  track.append(fill);
  wrap.append(row, track);
  card.append(wrap);

  // Stop button
  const stopBtn = actionButton("停止核验", "danger", "stop-scan", actions.stopScan);
  stopBtn.classList.add("btn--lg");
  card.append(stopBtn);

  main.append(card);
  return main;
}

/** Folder selected — centered card with stats + scrollable bidder grid. */
function folderReadyState(state: AppState, actions: WorkspaceActions): HTMLElement {
  if (state.selection === null) {
    return emptyState(actions);
  }
  const sel = state.selection;
  const main = element("div", "ws-ready");
  testId(main, "selected-folder");

  const card = element("div", "ws-ready__card");

  // ── Header ──
  const header = element("div", "ws-ready__header");
  const headerInfo = element("div", "ws-ready__header-info");
  headerInfo.append(
    element("span", "ws-ready__header-label", "已选择目录"),
    element("div", "ws-ready__header-name", sel.rootName),
  );
  header.append(folderGlyph(), headerInfo);
  card.append(header);

  // ── Stats ──
  const stats = element("div", "ws-ready__stats");
  const addStat = (val: string, lbl: string, id?: string): void => {
    const s = element("div", "ws-ready__stat");
    const v = element("strong", "ws-ready__stat-val", val);
    if (id) testId(v, id);
    s.append(v, element("span", "ws-ready__stat-lbl", lbl));
    stats.append(s);
  };
  addStat(String(sel.bidderCount), "个投标人", "bidder-count");
  addStat(String(sel.supportedFileCount), "个支持文件", "file-count");
  addStat(formatBytes(sel.totalSizeBytes), "文件总量");
  card.append(stats);

  // ── Scrollable bidder chip grid ──
  const groupsArea = element("div", "ws-ready__groups-area");
  groupsArea.append(element("div", "ws-ready__groups-label", `识别到 ${sel.bidderCount} 个投标人`));

  const grid = element("div", "ws-ready__chip-grid");
  sel.groups.forEach((g, i) => {
    const chip = element("div", "ws-ready__chip");
    chip.append(
      element("span", "ws-ready__chip-badge",
        g.kind === "bidder" ? String.fromCharCode(65 + i) : "根"),
      element("span", "ws-ready__chip-name", g.name),
    );
    grid.append(chip);
  });

  if (sel.rootFileCount > 0) {
    const warn = element("div", "ws-boundary-warn",
      `根目录还有 ${sel.rootFileCount} 个文件未归属任何投标人；程序会提取其元数据，但不参与冲突判断。`);
    warn.setAttribute("role", "note");
    testId(warn, "root-files-warning");
    grid.append(warn);
  }
  groupsArea.append(grid);
  card.append(groupsArea);

  // ── Actions ──
  const actionsEl = element("div", "ws-ready__actions");
  const startBtn = actionButton("开始核验", "primary", "start-scan", actions.startScan);
  startBtn.classList.add("btn--lg");
  actionsEl.append(startBtn);
  actionsEl.append(actionButton("重新选择", "ghost", "choose-folder", actions.chooseFolder));
  card.append(actionsEl);

  // ── Status messages ──
  if (state.status === "stopped") {
    const msg = element("div", "ws-msg", "核验已停止，可以重新开始");
    card.append(msg);
  }
  if (state.error !== null) {
    const err = element("div", "ws-msg ws-msg--error", state.error);
    err.setAttribute("role", "alert");
    card.append(err);
  }

  main.append(card);
  return main;
}

// ── Entry point ──────────────────────────────────────────────────

export function renderWorkspaceContent(
  state: AppState,
  actions: WorkspaceActions,
): HTMLElement {
  if (state.selection === null && state.status !== "failed") {
    return emptyState(actions);
  }
  if (state.status === "scanning" || state.status === "blocked") {
    return scanningState(state, actions);
  }
  return folderReadyState(state, actions);
}

import type { AppState } from "./state";
import { actionButton, element, formatBytes, testId } from "./dom";

export interface WorkspaceActions {
  chooseFolder(): Promise<void>;
  startScan(): Promise<void>;
  stopScan(): Promise<void>;
}

function emptyState(actions: WorkspaceActions): HTMLElement {
  const wrap = element("div", "center-state");
  testId(wrap, "selection-page");
  const icon = element("div", "center-state__icon");
  icon.innerHTML =
    '<svg viewBox="0 0 48 48" fill="none"><rect x="8" y="6" width="24" height="32" rx="2" fill="#cbd5e1"/>' +
    '<rect x="14" y="14" width="14" height="2" rx="1" fill="#94a3b8"/><rect x="14" y="19" width="10" height="2" rx="1" fill="#94a3b8"/>' +
    '<circle cx="31" cy="31" r="10" fill="#fff" stroke="#94a3b8" stroke-width="2"/>' +
    '<line x1="38" y1="38" x2="44" y2="44" stroke="#94a3b8" stroke-width="2.5" stroke-linecap="round"/></svg>';
  wrap.append(
    icon,
    element("h2", "center-state__title", "选择投标文件目录"),
    element("p", "center-state__desc", "选择「4-投标文件」这一级目录，程序自动识别投标人文件夹和支持的文档，完全离线运行。"),
    actionButton("选择文件夹", "primary", "choose-folder", actions.chooseFolder),
  );
  return wrap;
}

function scanState(state: AppState): HTMLElement {
  const wrap = element("div", "scan-state");
  testId(wrap, "scan-progress");
  wrap.append(
    element("div", "scan-state__msg", state.progress.message),
    element("div", "scan-state__sub", "正在提取作者、修改者等元数据痕迹"),
  );
  const bar = element("progress", "scan-state__bar");
  bar.max = 100;
  bar.value = state.progress.percent;
  wrap.append(bar);
  return wrap;
}

function folderReady(state: AppState, actions: WorkspaceActions): HTMLElement {
  if (state.selection === null) {
    return emptyState(actions);
  }
  const sel = state.selection;
  const wrap = element("div", "main-scroll");
  const info = element("div", "folder-info");
  testId(info, "selected-folder");

  info.append(
    element("div", "folder-info__title", sel.rootName),
    element("div", "folder-info__path", sel.rootName),
  );

  const stats = element("div", "folder-info__stats");
  const addStat = (val: string, lbl: string, id?: string): void => {
    const s = element("div", "folder-info__stat");
    const v = element("div", "folder-info__stat-val", val);
    if (id) testId(v, id);
    s.append(v, element("div", "folder-info__stat-lbl", lbl));
    stats.append(s);
  };
  addStat(String(sel.bidderCount), "个投标人", "bidder-count");
  addStat(String(sel.supportedFileCount), "个支持文件", "file-count");
  addStat(formatBytes(sel.totalSizeBytes), "文件总量");
  info.append(stats);

  const groups = element("div", "folder-info__groups");
  sel.groups.forEach((g, i) => {
    const pill = element("div", "group-pill");
    pill.append(
      element("span", "group-pill__id", g.kind === "bidder" ? String.fromCharCode(65 + i) : "根"),
      element("span", undefined, g.name),
      element("span", undefined, `${g.fileCount}`),
    );
    groups.append(pill);
  });
  info.append(groups);

  if (sel.rootFileCount > 0) {
    const w = element("div", "boundary-warn", `根目录还有 ${sel.rootFileCount} 个文件未归属任何投标人；程序会提取其元数据，但不参与冲突判断。`);
    w.setAttribute("role", "note");
    testId(w, "root-files-warning");
    info.append(w);
  }

  const btns = element("div");
  btns.style.cssText = "display:flex;gap:8px";
  if (state.status === "stopped") {
    btns.append(element("div", "alert-box alert-box--info", "核验已停止，可以重新开始"));
  }
  btns.append(actionButton("开始核验", "primary", "start-scan", actions.startScan));
  btns.append(actionButton("重新选择", "ghost", "choose-folder", actions.chooseFolder));
  info.append(btns);

  if (state.error !== null) {
    const err = element("div", "alert-box alert-box--error", state.error);
    err.setAttribute("role", "alert");
    info.append(err);
  }

  wrap.append(info);
  return wrap;
}

export function renderWorkspaceContent(
  state: AppState,
  actions: WorkspaceActions,
): HTMLElement {
  const main = element("div", "main-scroll");
  main.style.flex = "1";
  main.style.display = "flex";
  main.style.flexDirection = "column";

  if (state.selection === null && state.status !== "failed") {
    main.append(emptyState(actions));
  } else if (state.status === "scanning" || state.status === "blocked") {
    main.append(scanState(state));
  } else {
    main.append(...folderReady(state, actions).childNodes);
  }
  return main;
}

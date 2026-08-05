import type { AppState } from "./state";
import { actionButton, element, formatBytes, testId } from "./dom";

export interface WorkspaceActions {
  chooseFolder(): Promise<void>;
  startScan(): Promise<void>;
  stopScan(): Promise<void>;
}

function emptyState(actions: WorkspaceActions): HTMLElement {
  const wrap = element("div", "content-empty");
  testId(wrap, "selection-page");
  const icon = element("div", "content-empty__icon");
  icon.innerHTML =
    '<svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<rect x="10" y="8" width="28" height="36" rx="2" fill="#dce0e5"/>' +
    '<rect x="16" y="16" width="16" height="2" rx="1" fill="#adb5bd"/>' +
    '<rect x="16" y="22" width="12" height="2" rx="1" fill="#adb5bd"/>' +
    '<circle cx="36" cy="36" r="12" fill="#fff" stroke="#868e96" stroke-width="2"/>' +
    '<line x1="45" y1="45" x2="52" y2="52" stroke="#868e96" stroke-width="2.5" stroke-linecap="round"/>' +
    "</svg>";
  wrap.append(
    icon,
    element("h2", "content-empty__title", "选择投标文件目录"),
    element(
      "p",
      "content-empty__desc",
      "选择「4-投标文件」这一级目录。程序会自动识别投标人文件夹和支持的文档，完全离线运行。",
    ),
    actionButton("选择文件夹", "primary", "choose-folder", actions.chooseFolder),
  );
  return wrap;
}

function scanProgress(state: AppState): HTMLElement {
  const wrap = element("div", "scan-progress");
  testId(wrap, "scan-progress");
  wrap.append(
    element("h2", "scan-progress__message", state.progress.message),
    element(
      "span",
      "scan-progress__detail",
      "正在提取作者、修改者等元数据痕迹",
    ),
  );
  const bar = element("progress", "scan-progress__bar");
  bar.max = 100;
  bar.value = state.progress.percent;
  bar.setAttribute("aria-label", "核验进度");
  wrap.append(bar);
  return wrap;
}

function folderReady(state: AppState, actions: WorkspaceActions): HTMLElement {
  if (state.selection === null) {
    return emptyState(actions);
  }
  const sel = state.selection;
  const wrap = element("div", "content");
  const inner = element("div", "folder-ready");
  testId(inner, "selected-folder");

  inner.append(
    element("h2", "folder-ready__title", sel.rootName),
    element("p", "folder-ready__path", sel.rootName),
  );

  const stats = element("div", "folder-ready__stats");
  const addStat = (value: string, label: string, id?: string): void => {
    const card = element("div", "stat-card");
    const valEl = element("div", "stat-card__value", value);
    if (id !== undefined) {
      testId(valEl, id);
    }
    card.append(valEl, element("div", "stat-card__label", label));
    stats.append(card);
  };
  addStat(String(sel.bidderCount), "个投标人", "bidder-count");
  addStat(String(sel.supportedFileCount), "个支持文件", "file-count");
  addStat(formatBytes(sel.totalSizeBytes), "文件总量");
  inner.append(stats);

  const groupsWrap = element("div", "folder-ready__groups");
  groupsWrap.append(element("div", "folder-ready__groups-heading", "投标人目录"));
  const groupList = element("div", "group-list");
  sel.groups.forEach((group, index) => {
    const tag = element("div", "group-tag");
    tag.append(
      element(
        "span",
        "group-tag__letter",
        group.kind === "bidder" ? String.fromCharCode(65 + index) : "根",
      ),
      element("span", undefined, group.name),
      element("span", "group-tag__count", `${group.fileCount}`),
    );
    groupList.append(tag);
  });
  groupsWrap.append(groupList);
  inner.append(groupsWrap);

  if (sel.rootFileCount > 0) {
    const note = element(
      "div",
      "boundary-note",
      `根目录还有 ${sel.rootFileCount} 个文件未归属任何投标人；程序会提取其元数据，但不参与投标人冲突判断。`,
    );
    note.setAttribute("role", "note");
    testId(note, "root-files-warning");
    inner.append(note);
  }

  const controls = element("div");
  controls.style.display = "flex";
  controls.style.gap = "8px";
  if (state.status === "stopped") {
    controls.append(
      element("div", "inline-msg inline-msg--info", "核验已停止，可以重新开始"),
    );
  }
  controls.append(
    actionButton("开始核验", "primary", "start-scan", actions.startScan),
    actionButton("重新选择", "ghost", "choose-folder", actions.chooseFolder),
  );
  inner.append(controls);

  if (state.error !== null) {
    const err = element("div", "inline-msg inline-msg--error", state.error);
    err.setAttribute("role", "alert");
    inner.append(err);
  }

  wrap.append(inner);
  return wrap;
}

export function renderWorkspaceContent(
  state: AppState,
  actions: WorkspaceActions,
): HTMLElement {
  if (state.selection === null && state.status !== "failed") {
    return emptyState(actions);
  }
  if (state.status === "scanning" || state.status === "blocked") {
    return scanProgress(state);
  }
  return folderReady(state, actions);
}

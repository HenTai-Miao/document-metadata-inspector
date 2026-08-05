import type { FolderGroup } from "../shared/contracts";
import { actionButton, element, formatBytes, testId } from "./dom";
import type { AppState } from "./state";

export interface SelectionActions {
  chooseFolder(): Promise<void>;
  startScan(): Promise<void>;
  stopScan(): Promise<void>;
}

function folderGlyph(): HTMLElement {
  const glyph = element("div", "folder-glyph");
  glyph.setAttribute("aria-hidden", "true");
  glyph.append(element("span", "folder-glyph__tab"), element("span", "folder-glyph__body"));
  return glyph;
}

function groupChip(group: FolderGroup, index: number): HTMLElement {
  const chip = element("div", "group-chip");
  const marker = element(
    "span",
    "group-chip__marker",
    group.kind === "bidder" ? String.fromCharCode(65 + index) : "根",
  );
  const copy = element("span", "group-chip__copy");
  copy.append(
    element("strong", "group-chip__name", group.name),
    element("small", "group-chip__count", `${group.fileCount} 个文件`),
  );
  chip.append(marker, copy);
  return chip;
}

function scanningVisual(state: AppState): HTMLElement {
  const visual = element("div", `scan-visual ${state.status === "scanning" ? "is-active" : ""}`);
  const topNote = element(
    "div",
    "scan-visual__note",
    state.status === "scanning" ? "本机离线读取中" : "等待开始",
  );
  const viewport = element("div", "scan-viewport");
  const stack = element("div", "document-stack");
  for (const [index, format] of ["PDF", "DOCX", "XLSX"].entries()) {
    const documentCard = element("div", `document-sheet document-sheet--${index + 1}`);
    documentCard.append(
      element("span", "document-sheet__format", format),
      element("span", "document-sheet__line"),
      element("span", "document-sheet__line document-sheet__line--short"),
    );
    stack.append(documentCard);
  }
  viewport.append(stack, element("div", "scan-beam"));
  const stage = element("div", "scan-stage-copy");
  stage.setAttribute("aria-live", "polite");
  stage.append(
    element("strong", "scan-stage-copy__message", state.progress.message),
    element(
      "span",
      "scan-stage-copy__detail",
      state.status === "scanning"
        ? "原始解析 · Apache 解析 · ExifTool 交叉核验"
        : "文件不会上传，也不会连接外部服务",
    ),
  );
  const progressTrack = element("progress", "progress-track");
  progressTrack.max = 100;
  progressTrack.value = state.status === "scanning" ? state.progress.percent : 0;
  progressTrack.setAttribute("aria-label", "核验进度");
  visual.append(topNote, viewport, stage, progressTrack);
  return visual;
}

export function renderSelection(state: AppState, actions: SelectionActions): HTMLElement {
  const page = element("main", "selection-page");
  testId(page, "selection-page");

  const introduction = element("section", "selection-intro");
  introduction.append(
    element("p", "eyebrow", "01 / 选择投标文件目录"),
    element("h1", "selection-intro__title", "先分清投标人，再核对文档痕迹"),
    element(
      "p",
      "selection-intro__description",
      "每个一级子文件夹视为一个投标人。同一投标人目录内的文件不会互相判定冲突。",
    ),
  );

  const workspace = element("section", "selection-workspace");
  const folderPanel = element("article", "folder-panel");
  const panelHeader = element("div", "panel-header");
  panelHeader.append(
    element("span", "panel-header__title", "待核验目录"),
    element("span", "offline-pill", "OFFLINE · 本机运行"),
  );
  folderPanel.append(panelHeader);

  if (state.selection === null) {
    const empty = element("div", "folder-empty");
    empty.append(
      folderGlyph(),
      element("h2", "folder-empty__title", "选择“4-投标文件”这一级目录"),
      element("p", "folder-empty__copy", "程序会自动识别下面的投标人文件夹和支持的文档。"),
      actionButton("选择文件夹", "primary", "choose-folder", actions.chooseFolder),
    );
    folderPanel.append(empty);
  } else {
    const selected = element("div", "selected-folder");
    testId(selected, "selected-folder");
    const selectedHeading = element("div", "selected-folder__heading");
    const folderCopy = element("div", "selected-folder__copy");
    folderCopy.append(
      element("span", "selected-folder__label", "已选择"),
      element("h2", "selected-folder__name", state.selection.rootName),
      element("p", "selected-folder__path", "目录权限仅保留在本机主进程"),
    );
    selectedHeading.append(folderGlyph(), folderCopy);

    const stats = element("div", "selection-stats");
    const bidderStat = element("div", "selection-stat");
    bidderStat.append(
      element("strong", "selection-stat__value", String(state.selection.bidderCount)),
    );
    testId(bidderStat.querySelector("strong") as HTMLElement, "bidder-count");
    bidderStat.append(element("span", "selection-stat__label", "个投标人"));
    const fileStat = element("div", "selection-stat");
    fileStat.append(
      element("strong", "selection-stat__value", String(state.selection.supportedFileCount)),
    );
    testId(fileStat.querySelector("strong") as HTMLElement, "file-count");
    fileStat.append(element("span", "selection-stat__label", "个支持文件"));
    const sizeStat = element("div", "selection-stat");
    sizeStat.append(
      element(
        "strong",
        "selection-stat__value selection-stat__value--small",
        formatBytes(state.selection.totalSizeBytes),
      ),
      element("span", "selection-stat__label", "文件总量"),
    );
    stats.append(bidderStat, fileStat, sizeStat);

    const groups = element("div", "group-chip-list");
    state.selection.groups.forEach((group, index) => {
      groups.append(groupChip(group, index));
    });
    if (state.selection.rootFileCount > 0) {
      const boundaryWarning = element(
        "div",
        "boundary-warning",
        `根目录还有 ${state.selection.rootFileCount} 个文件未归属任何投标人；程序会提取其元数据，但不会把它们作为投标人参与冲突判断。`,
      );
      boundaryWarning.setAttribute("role", "note");
      testId(boundaryWarning, "root-files-warning");
      groups.append(boundaryWarning);
    }

    const controls = element("div", "selection-controls");
    const chooseAgain = actionButton(
      "重新选择",
      "secondary",
      "choose-folder",
      actions.chooseFolder,
    );
    chooseAgain.disabled = state.status === "scanning" || state.status === "blocked";
    controls.append(chooseAgain);
    if (state.status === "scanning") {
      controls.append(actionButton("停止核验", "danger", "stop-scan", actions.stopScan));
    } else if (state.status === "blocked") {
      const cleanupBlocked = state.error?.includes("临时文件未能安全清理") ?? false;
      const blocked = actionButton(
        cleanupBlocked ? "请退出程序" : "重新尝试停止",
        "danger",
        "scan-blocked",
        actions.stopScan,
      );
      blocked.disabled = cleanupBlocked;
      controls.append(blocked);
    } else {
      controls.append(actionButton("开始核验", "primary", "start-scan", actions.startScan));
    }

    selected.append(selectedHeading, stats, groups, controls);
    if (state.error !== null) {
      const error = element("div", "inline-message inline-message--error", state.error);
      error.setAttribute("role", "alert");
      selected.append(error);
    } else if (state.status === "stopped") {
      const stopped = element("div", "inline-message", "核验已停止，可以重新开始");
      stopped.setAttribute("role", "status");
      selected.append(stopped);
    }
    folderPanel.append(selected);
  }

  workspace.append(folderPanel, scanningVisual(state));
  page.append(introduction, workspace);
  return page;
}

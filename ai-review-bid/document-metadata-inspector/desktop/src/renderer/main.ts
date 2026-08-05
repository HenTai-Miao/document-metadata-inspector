import "./styles.css";

import { getDocmetaBridge } from "./bridge";
import { actionButton, element, formatBytes } from "./dom";
import { renderResult } from "./render-result";
import { renderWorkspaceContent } from "./render-selection";
import { scanFailureAction } from "./scan-errors";
import { type AppAction, type AppState, initialAppState, reduceAppState } from "./state";

const locatedAppRoot = document.querySelector<HTMLDivElement>("#app");
if (locatedAppRoot === null) {
  throw new Error("应用挂载点缺失");
}
const appRoot: HTMLDivElement = locatedAppRoot;

const bridge = getDocmetaBridge();
let state: AppState = initialAppState;
let nextScanToken = 0;

let selectedGroupId: string | null = null;
let selectedDocumentId: string | null = null;

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message.replace(/^Error invoking remote method '[^']+': Error: /, "");
  }
  return "发生未知错误，请重新选择目录后再试";
}

function dispatch(action: AppAction): void {
  if (action.type === "folderSelected") {
    selectedGroupId = null;
    selectedDocumentId = null;
  }
  if (action.type === "scanStarted") {
    selectedGroupId = null;
    selectedDocumentId = null;
  }
  state = reduceAppState(state, action);
  render();
}

async function chooseFolder(): Promise<void> {
  try {
    const selection = await bridge.selectFolder();
    if (selection !== null) {
      dispatch({ type: "folderSelected", selection });
    }
  } catch (error) {
    dispatch({ type: "selectionFailed", error: errorMessage(error) });
  }
}

async function startScan(): Promise<void> {
  const selection = state.selection;
  if (selection === null) {
    return;
  }
  const token = ++nextScanToken;
  dispatch({ type: "scanStarted", token });
  try {
    const result = await bridge.startScan();
    dispatch({ type: "scanCompleted", token, result });
  } catch (error) {
    const message = errorMessage(error);
    dispatch(scanFailureAction(token, message));
  }
}

async function stopScan(): Promise<void> {
  const token = state.activeScanToken;
  if (token === null) {
    return;
  }
  try {
    await bridge.stopScan();
    dispatch({ type: "scanStopped", token });
  } catch (error) {
    dispatch(scanFailureAction(token, errorMessage(error)));
  }
}

function selectGroup(groupId: string | null): void {
  selectedGroupId = groupId;
  selectedDocumentId = null;
  render();
}

function selectDocument(documentId: string | null): void {
  selectedDocumentId = documentId;
  render();
}

function logo(): string {
  return (
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none">' +
    '<rect x="4" y="2.5" width="11" height="14" rx="1" fill="#fff" opacity="0.9"/>' +
    '<circle cx="14.5" cy="14.5" r="5.5" fill="none" stroke="#fff" stroke-width="1.8"/>' +
    '<line x1="18.5" y1="18.5" x2="21.5" y2="21.5" stroke="#fff" stroke-width="2" stroke-linecap="round"/>' +
    "</svg>"
  );
}

function toolbar(): HTMLElement {
  const bar = element("div", "toolbar");
  const brand = element("div", "toolbar__brand");
  const logoEl = element("span", "toolbar__logo");
  logoEl.innerHTML = logo();
  brand.append(logoEl, element("span", "toolbar__title", "文档元数据核验"));
  bar.append(brand);

  if (state.selection !== null) {
    bar.append(element("span", "toolbar__divider"));
    const folder = element("div", "toolbar__folder");
    folder.append(
      element("span", undefined, "📁"),
      element("span", "toolbar__folder-name", state.selection.rootName),
    );
    bar.append(folder);
  }

  bar.append(element("span", "toolbar__spacer"));

  const actions = element("div", "toolbar__actions");
  actions.style.display = "flex";
  actions.style.gap = "6px";

  const chooseBtn = actionButton("选择目录", "ghost", "choose-folder", chooseFolder);
  chooseBtn.disabled = state.status === "scanning" || state.status === "blocked";
  actions.append(chooseBtn);

  if (state.status === "scanning") {
    actions.append(actionButton("停止", "danger", "stop-scan", stopScan));
  } else if (state.status === "blocked") {
    const cleanupBlocked = state.error?.includes("临时文件未能安全清理") ?? false;
    const blockedBtn = actionButton(
      cleanupBlocked ? "请退出" : "重试停止",
      "danger",
      "scan-blocked",
      stopScan,
    );
    blockedBtn.disabled = cleanupBlocked;
    actions.append(blockedBtn);
  } else if (state.status === "result") {
    actions.append(actionButton("重新核验", "primary", "rescan", startScan));
  } else if (state.selection !== null) {
    actions.append(actionButton("开始核验", "primary", "start-scan", startScan));
  }

  bar.append(actions);
  bar.append(element("span", "toolbar__divider"));

  const statusEl = element("div", "toolbar__status");
  statusEl.append(
    element("span", "toolbar__status-dot"),
    element("span", undefined, "离线运行"),
  );
  bar.append(statusEl);

  return bar;
}

function statusbar(): HTMLElement {
  const bar = element("div", "statusbar");
  if (state.selection !== null) {
    bar.append(
      element("span", "statusbar__item", `${state.selection.bidderCount} 个投标人`),
      element(
        "span",
        "statusbar__item",
        `${state.selection.supportedFileCount} 个文件`,
      ),
    );
  }
  if (state.result !== null) {
    bar.append(
      element(
        "span",
        "statusbar__item",
        `${state.result.observationCount.toLocaleString("zh-CN")} 条元数据`,
      ),
    );
    if (state.result.personTraces.length > 0) {
      bar.append(
        element(
          "span",
          "statusbar__item statusbar__item--accent",
          `${state.result.personTraces.length} 条人员重复痕迹`,
        ),
      );
    }
  }
  bar.append(element("span", "statusbar__spacer"));
  if (state.selection !== null) {
    bar.append(
      element("span", "statusbar__item", formatBytes(state.selection.totalSizeBytes)),
    );
  }
  return bar;
}

function render(): void {
  const shell = element("div", "app-shell");
  shell.append(toolbar());

  if (state.page === "result" && state.result !== null) {
    const workspace = renderResult(
      state.result,
      {
        selectedGroupId,
        selectedDocumentId,
        selectGroup,
        selectDocument,
        rescan: startScan,
      },
    );
    shell.append(workspace);
  } else {
    const workspace = element("div", "workspace");
    const content = renderWorkspaceContent(state, {
      chooseFolder,
      startScan,
      stopScan,
    });
    workspace.append(content);
    shell.append(workspace);
  }

  shell.append(statusbar());
  appRoot.replaceChildren(shell);
}

bridge.onScanProgress((progress) => {
  const token = state.activeScanToken;
  if (token !== null) {
    dispatch(
      progress.stage === "blocked"
        ? { type: "scanStopFailed", token, error: progress.message }
        : { type: "scanProgressed", token, progress },
    );
  }
});

render();

import "./styles.css";

import type { WindowState } from "../shared/contracts";
import { getDocmetaBridge } from "./bridge";
import { actionButton, element, formatBytes } from "./dom";
import { renderMetadata } from "./render-metadata";
import { renderResult } from "./render-result";
import { renderWorkspaceContent } from "./render-selection";
import { scanFailureAction } from "./scan-errors";
import { type AppAction, type AppState, initialAppState, reduceAppState } from "./state";
import { renderWindowControls } from "./window-controls";

const locatedAppRoot = document.querySelector<HTMLDivElement>("#app");
if (locatedAppRoot === null) {
  throw new Error("应用挂载点缺失");
}
const appRoot: HTMLDivElement = locatedAppRoot;

const bridge = getDocmetaBridge();
let state: AppState = initialAppState;
let windowState: WindowState = { isMaximized: false };
let nextScanToken = 0;

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message.replace(/^Error invoking remote method '[^']+': Error: /, "");
  }
  return "发生未知错误，请重新选择目录后再试";
}

function dispatch(action: AppAction): void {
  state = reduceAppState(state, action);
  render();
}

function updateWindowState(next: WindowState): void {
  if (next.isMaximized === windowState.isMaximized) {
    return;
  }
  windowState = next;
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
    dispatch(scanFailureAction(token, errorMessage(error)));
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

function logoSvg(): string {
  return (
    '<svg viewBox="0 0 24 24" width="15" height="15" fill="none">' +
    '<rect x="4" y="2.5" width="11" height="14" rx="1" fill="#fff" opacity="0.9"/>' +
    '<circle cx="14.5" cy="14.5" r="5.5" fill="none" stroke="#fff" stroke-width="1.8"/>' +
    '<line x1="18.5" y1="18.5" x2="21.5" y2="21.5" stroke="#fff" stroke-width="2" stroke-linecap="round"/>' +
    "</svg>"
  );
}

function topbar(): HTMLElement {
  const bar = element("div", "topbar");
  const logoEl = element("span", "topbar__logo");
  logoEl.innerHTML = logoSvg();
  bar.append(
    logoEl,
    element("span", "topbar__title", "文档元数据核验"),
    element("span", "topbar__mode", "本地证据工作台"),
  );

  if (state.selection !== null) {
    bar.append(element("span", "topbar__sep"));
    const folder = element("div", "topbar__folder");
    folder.append(
      element("span", undefined, "📁"),
      element("span", "topbar__folder-name", state.selection.rootName),
    );
    bar.append(folder);
  }

  bar.append(element("span", "topbar__spacer"));

  const btns = element("div", "topbar__actions");

  btns.append(actionButton("选择目录", "ghost", "choose-folder", chooseFolder));

  if (state.status === "scanning") {
    const stopBtn = actionButton("停止", "danger", "stop-scan", stopScan);
    btns.append(stopBtn);
  } else if (state.status === "blocked") {
    const cleanupBlocked = state.error?.includes("临时文件未能安全清理") ?? false;
    const blockedBtn = actionButton(
      cleanupBlocked ? "请退出" : "重试",
      "danger",
      "scan-blocked",
      stopScan,
    );
    blockedBtn.disabled = cleanupBlocked;
    btns.append(blockedBtn);
  } else if (state.status === "result") {
    if (state.page === "metadata") {
      btns.append(
        actionButton("返回报告", "primary", "back-to-report", () =>
          dispatch({ type: "showResult" }),
        ),
      );
    } else {
      btns.append(
        actionButton("元数据明细", "ghost", "show-metadata", () =>
          dispatch({ type: "showMetadata" }),
        ),
      );
      btns.append(actionButton("重新核验", "primary", "rescan", startScan));
    }
  } else if (state.selection !== null) {
    btns.append(actionButton("开始核验", "primary", "start-scan", startScan));
  }

  const status = element("div", "topbar__status");
  status.append(element("span", "topbar__dot"), element("span", undefined, "离线运行"));
  bar.append(
    btns,
    status,
    element("span", "topbar__window-sep"),
    renderWindowControls({
      controls: bridge.windowControls,
      state: windowState,
      onStateChanged: updateWindowState,
    }),
  );

  return bar;
}

function statusbar(): HTMLElement {
  const bar = element("div", "statusbar");
  if (state.selection !== null) {
    bar.append(element("span", undefined, `${state.selection.bidderCount} 投标人`));
    bar.append(element("span", undefined, `${state.selection.supportedFileCount} 文件`));
  }
  if (state.result !== null) {
    bar.append(
      element(
        "span",
        undefined,
        `${state.result.observationCount.toLocaleString("zh-CN")} 条元数据`,
      ),
    );
    if (state.result.personTraces.length > 0) {
      bar.append(
        element("span", "statusbar__alert", `${state.result.personTraces.length} 条人员重复`),
      );
    }
    if (state.result.cautionTraces.length > 0) {
      bar.append(
        element("span", "statusbar__caution", `${state.result.cautionTraces.length} 条待复核`),
      );
    }
  }
  bar.append(element("span", "statusbar__spacer"));
  if (state.selection !== null) {
    bar.append(element("span", undefined, formatBytes(state.selection.totalSizeBytes)));
  }
  return bar;
}

function render(): void {
  const shell = element("div", "app-shell");
  shell.append(topbar());

  if (state.page === "result" && state.result !== null) {
    shell.append(renderResult(state.result));
  } else if (state.page === "metadata" && state.result !== null) {
    shell.append(
      renderMetadata(state.result, {
        backToReport: () => dispatch({ type: "showResult" }),
        loadDocumentDetail: (documentId) => bridge.getDocumentDetail(documentId),
      }),
    );
  } else {
    shell.append(renderWorkspaceContent(state, { chooseFolder, startScan, stopScan }));
  }

  if (state.page !== "result" || state.result === null) {
    shell.append(statusbar());
  }
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

const disposeWindowState = bridge.windowControls.onStateChanged(updateWindowState);
window.addEventListener("beforeunload", disposeWindowState, { once: true });
void bridge.windowControls
  .getState()
  .then(updateWindowState)
  .catch(() => undefined);

render();

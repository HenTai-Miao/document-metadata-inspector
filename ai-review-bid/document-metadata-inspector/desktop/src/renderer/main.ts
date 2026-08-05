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
  bar.append(logoEl, element("span", "topbar__title", "文档元数据核验"));

  if (state.selection !== null) {
    bar.append(element("span", "topbar__sep"));
    const folder = element("div", "topbar__folder");
    folder.append(element("span", undefined, "📁"), element("span", "topbar__folder-name", state.selection.rootName));
    bar.append(folder);
  }

  bar.append(element("span", "topbar__spacer"));

  const btns = element("div");
  btns.style.cssText = "display:flex;gap:6px";

  btns.append(actionButton("选择目录", "ghost", "choose-folder", chooseFolder));

  if (state.status === "scanning") {
    const stopBtn = actionButton("停止", "danger", "stop-scan", stopScan);
    btns.append(stopBtn);
  } else if (state.status === "blocked") {
    const cleanupBlocked = state.error?.includes("临时文件未能安全清理") ?? false;
    const blockedBtn = actionButton(cleanupBlocked ? "请退出" : "重试", "danger", "scan-blocked", stopScan);
    blockedBtn.disabled = cleanupBlocked;
    btns.append(blockedBtn);
  } else if (state.status === "result") {
    btns.append(actionButton("重新核验", "primary", "rescan", startScan));
  } else if (state.selection !== null) {
    btns.append(actionButton("开始核验", "primary", "start-scan", startScan));
  }

  bar.append(btns, element("span", "topbar__sep"));

  const status = element("div", "topbar__status");
  status.append(element("span", "topbar__dot"), element("span", undefined, "离线"));
  bar.append(status);

  return bar;
}

function statusbar(): HTMLElement {
  const bar = element("div", "statusbar");
  if (state.selection !== null) {
    bar.append(element("span", undefined, `${state.selection.bidderCount} 投标人`));
    bar.append(element("span", undefined, `${state.selection.supportedFileCount} 文件`));
  }
  if (state.result !== null) {
    bar.append(element("span", undefined, `${state.result.observationCount.toLocaleString("zh-CN")} 条元数据`));
    if (state.result.personTraces.length > 0) {
      bar.append(element("span", "statusbar__alert", `${state.result.personTraces.length} 条人员重复`));
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
  } else {
    shell.append(renderWorkspaceContent(state, { chooseFolder, startScan, stopScan }));
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

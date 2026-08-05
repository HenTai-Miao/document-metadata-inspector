import "./styles.css";

import { getDocmetaBridge } from "./bridge";
import { element } from "./dom";
import { renderResult } from "./render-result";
import { renderSelection } from "./render-selection";
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

function appHeader(): HTMLElement {
  const header = element("header", "app-header");
  const brand = element("div", "brand");
  const brandMark = element("span", "brand-mark", "鉴");
  const brandCopy = element("span", "brand-copy");
  brandCopy.append(
    element("strong", "brand-name", "文档元数据核验"),
    element("small", "brand-subtitle", "Document evidence workstation"),
  );
  brand.append(brandMark, brandCopy);
  const privacy = element("div", "privacy-status");
  privacy.append(
    element("span", "privacy-status__dot"),
    element("span", undefined, "离线运行 · 文件不离开本机"),
  );
  const step = element("div", "header-step");
  step.append(
    element(
      "span",
      state.page === "selection" ? "header-step__item is-active" : "header-step__item",
      "选择与扫描",
    ),
    element("i", "header-step__line"),
    element(
      "span",
      state.page === "result" ? "header-step__item is-active" : "header-step__item",
      "核验结果",
    ),
  );
  header.append(brand, step, privacy);
  return header;
}

function render(): void {
  const page =
    state.page === "result" && state.result !== null
      ? renderResult(state.result, {
          showSelection: () => dispatch({ type: "showSelection" }),
          rescan: startScan,
        })
      : renderSelection(state, { chooseFolder, startScan, stopScan });
  appRoot.replaceChildren(appHeader(), page);
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

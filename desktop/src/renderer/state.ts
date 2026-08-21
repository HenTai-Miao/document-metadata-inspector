import type { FolderSelection, ScanProgress, ScanResult } from "../shared/contracts";

export type AppStatus =
  | "empty"
  | "ready"
  | "scanning"
  | "stopped"
  | "failed"
  | "blocked"
  | "result";
export type AppPage = "selection" | "result" | "metadata";

export interface AppState {
  page: AppPage;
  status: AppStatus;
  selection: FolderSelection | null;
  result: ScanResult | null;
  progress: ScanProgress;
  error: string | null;
  activeScanToken: number | null;
  lastScanToken: number | null;
}

export type AppAction =
  | { type: "folderSelected"; selection: FolderSelection }
  | { type: "selectionFailed"; error: string }
  | { type: "selectionCleared" }
  | { type: "scanStarted"; token: number }
  | { type: "scanProgressed"; token: number; progress: ScanProgress }
  | { type: "scanCompleted"; token: number; result: ScanResult }
  | { type: "scanFailed"; token: number; error: string }
  | { type: "scanStopFailed"; token: number; error: string }
  | { type: "scanStopped"; token: number }
  | { type: "showSelection" }
  | { type: "showMetadata" }
  | { type: "showResult" };

const idleProgress: ScanProgress = {
  stage: "preparing",
  message: "等待开始核验",
  percent: 0,
};

export const initialAppState: AppState = {
  page: "selection",
  status: "empty",
  selection: null,
  result: null,
  progress: idleProgress,
  error: null,
  activeScanToken: null,
  lastScanToken: null,
};

function appliesToActiveScan(state: AppState, token: number): boolean {
  return state.status === "scanning" && state.activeScanToken === token;
}

export function reduceAppState(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "folderSelected":
      return {
        ...state,
        page: "selection",
        status: "ready",
        selection: action.selection,
        result: null,
        progress: idleProgress,
        error: null,
        activeScanToken: null,
        lastScanToken: null,
      };
    case "selectionFailed":
      return {
        ...state,
        page: "selection",
        status: "failed",
        error: action.error,
        activeScanToken: null,
      };
    case "selectionCleared":
      return initialAppState;
    case "scanStarted":
      if (state.selection === null) {
        return state;
      }
      return {
        ...state,
        status: "scanning",
        result: null,
        error: null,
        activeScanToken: action.token,
        lastScanToken: action.token,
        progress: {
          stage: "preparing",
          message: "正在准备核验",
          percent: 1,
        },
      };
    case "scanProgressed":
      return appliesToActiveScan(state, action.token)
        ? { ...state, progress: action.progress }
        : state;
    case "scanCompleted":
      if (!appliesToActiveScan(state, action.token)) {
        return state;
      }
      return {
        ...state,
        page: "result",
        status: "result",
        result: action.result,
        progress: { stage: "complete", message: "核验完成", percent: 100 },
        activeScanToken: null,
      };
    case "scanFailed":
      if (
        state.activeScanToken !== action.token ||
        (state.status !== "scanning" && state.status !== "blocked")
      ) {
        return state;
      }
      return {
        ...state,
        status: "failed",
        page: "selection",
        error: action.error,
        activeScanToken: null,
      };
    case "scanStopFailed":
      if (state.lastScanToken !== action.token) {
        return state;
      }
      return {
        ...state,
        status: "blocked",
        page: "selection",
        error: action.error,
        activeScanToken: action.token,
      };
    case "scanStopped":
      if (
        state.activeScanToken !== action.token ||
        (state.status !== "scanning" && state.status !== "blocked")
      ) {
        return state;
      }
      return {
        ...state,
        status: "stopped",
        page: "selection",
        progress: { stage: "stopped", message: "核验已停止，可以重新开始", percent: 0 },
        activeScanToken: null,
      };
    case "showSelection":
      return {
        ...state,
        page: "selection",
        status: state.selection === null ? "empty" : "ready",
        error: null,
      };
    case "showMetadata":
      if (state.result === null) return state;
      return { ...state, page: "metadata" };
    case "showResult":
      if (state.result === null) return state;
      return { ...state, page: "result" };
  }
}

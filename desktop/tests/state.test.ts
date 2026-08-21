import { describe, expect, test } from "vitest";
import { initialAppState, reduceAppState } from "../src/renderer/state";
import type { FolderSelection, ScanResult } from "../src/shared/contracts";

function selection(rootName: string): FolderSelection {
  return {
    rootName,
    supportedFileCount: 8,
    bidderCount: 2,
    rootFileCount: 0,
    ignoredFileCount: 0,
    totalSizeBytes: 1024,
    groups: [],
  };
}

function result(rootName: string): ScanResult {
  return {
    rootName,
    scannedAt: "2026-08-05T10:00:00.000Z",
    documentCount: 8,
    completeDocumentCount: 8,
    observationCount: 2075,
    parserRunCount: 24,
    warningCount: 0,
    bidderCount: 2,
    groups: [],
    personTraces: [],
    cautionTraces: [],
  };
}

describe("reduceAppState", () => {
  test("shows a folder selection error without losing the current page", () => {
    // A rejected native dialog or unreadable directory must be visible to the user.
    const failed = reduceAppState(initialAppState, {
      type: "selectionFailed",
      error: "目录无法读取",
    });

    expect(failed).toMatchObject({ status: "failed", page: "selection", error: "目录无法读取" });
  });

  test("moves from a selected folder through scanning to the result page", () => {
    // A completion that leaves the app on page one would hide the real report.
    const ready = reduceAppState(initialAppState, {
      type: "folderSelected",
      selection: selection("真实目录"),
    });
    const scanning = reduceAppState(ready, { type: "scanStarted", token: 7 });
    const progressing = reduceAppState(scanning, {
      type: "scanProgressed",
      token: 7,
      progress: { stage: "extracting", message: "正在提取", percent: 45 },
    });
    const completed = reduceAppState(progressing, {
      type: "scanCompleted",
      token: 7,
      result: result("真实目录"),
    });

    expect(ready.status).toBe("ready");
    expect(progressing.progress.percent).toBe(45);
    expect(completed).toMatchObject({ status: "result", page: "result", activeScanToken: null });
    expect(completed.result?.observationCount).toBe(2075);
  });

  test("returns a stopped scan to the same ready selection", () => {
    // Stop must not discard the folder and force the user to select it again.
    const ready = reduceAppState(initialAppState, {
      type: "folderSelected",
      selection: selection("真实目录"),
    });
    const scanning = reduceAppState(ready, { type: "scanStarted", token: 8 });
    const stopped = reduceAppState(scanning, { type: "scanStopped", token: 8 });
    const reset = reduceAppState(stopped, { type: "showSelection" });

    expect(stopped).toMatchObject({ status: "stopped", page: "selection" });
    expect(reset).toMatchObject({ status: "ready", page: "selection" });
    expect(reset.selection?.rootName).toBe("真实目录");
  });

  test("locks the selection page after an unsafe process-tree stop", () => {
    const ready = reduceAppState(initialAppState, {
      type: "folderSelected",
      selection: selection("真实目录"),
    });
    const scanning = reduceAppState(ready, { type: "scanStarted", token: 10 });
    const stopped = reduceAppState(scanning, { type: "scanStopped", token: 10 });
    const blocked = reduceAppState(stopped, {
      type: "scanStopFailed",
      token: 10,
      error: "核验进程未能安全停止，请关闭程序后重试",
    });

    expect(blocked).toMatchObject({
      status: "blocked",
      page: "selection",
      activeScanToken: 10,
    });
    const recoveredFailure = reduceAppState(blocked, {
      type: "scanFailed",
      token: 10,
      error: "核验时间超过安全时限，已自动停止",
    });
    expect(recoveredFailure).toMatchObject({ status: "failed", activeScanToken: null });
  });

  test("ignores a stale completion after the user selects a different folder", () => {
    // An old process finishing late must never overwrite a newer folder choice.
    const first = reduceAppState(initialAppState, {
      type: "folderSelected",
      selection: selection("旧目录"),
    });
    const scanning = reduceAppState(first, { type: "scanStarted", token: 9 });
    const newer = reduceAppState(scanning, {
      type: "folderSelected",
      selection: selection("新目录"),
    });
    const staleCompletion = reduceAppState(newer, {
      type: "scanCompleted",
      token: 9,
      result: result("旧目录"),
    });

    expect(staleCompletion.status).toBe("ready");
    expect(staleCompletion.selection?.rootName).toBe("新目录");
    expect(staleCompletion.result).toBeNull();
  });
});

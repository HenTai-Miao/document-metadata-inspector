import { describe, expect, test } from "vitest";

import { scanFailureAction } from "../src/renderer/scan-errors";

describe("scanFailureAction", () => {
  test("distinguishes a completed stop from an unsafe process-tree failure", () => {
    expect(scanFailureAction(1, "核验已停止")).toEqual({ type: "scanStopped", token: 1 });
    expect(scanFailureAction(2, "核验进程未能安全停止，请关闭程序后重试")).toEqual({
      type: "scanStopFailed",
      token: 2,
      error: "核验进程未能安全停止，请关闭程序后重试",
    });
  });
});

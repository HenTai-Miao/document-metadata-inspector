import { describe, expect, test } from "vitest";

import { windowControlPresentation } from "../src/renderer/window-controls";

describe("windowControlPresentation", () => {
  test("presents maximize affordance for a normal window", () => {
    expect(windowControlPresentation({ isMaximized: false })).toEqual({
      maximizeLabel: "最大化窗口",
      maximizeIcon: "maximize",
    });
  });

  test("presents restore affordance for a maximized window", () => {
    expect(windowControlPresentation({ isMaximized: true })).toEqual({
      maximizeLabel: "还原窗口",
      maximizeIcon: "restore",
    });
  });
});

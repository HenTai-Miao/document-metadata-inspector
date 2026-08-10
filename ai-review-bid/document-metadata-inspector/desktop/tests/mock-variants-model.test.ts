import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";
import { describe, expect, test } from "vitest";

function loadModel() {
  const window: Record<string, unknown> = {};
  const source = readFileSync(
    resolve(import.meta.dirname, "../mock/design-spec-variants/model.js"),
    "utf8",
  );
  vm.runInNewContext(source, { window, structuredClone });
  return (window.DocmetaPrototype as { model: Record<string, any> }).model;
}

describe("design-spec prototype model", () => {
  test("publishes the fixed demonstration totals", () => {
    const model = loadModel();
    expect(model.demoProject.groups).toHaveLength(4);
    expect(model.demoProject.documents).toHaveLength(16);
    expect(model.demoProject.observationCount).toBe(148);
    expect(model.demoProject.traces.filter((trace: any) => trace.tone === "danger")).toHaveLength(
      2,
    );
    expect(model.demoProject.traces.filter((trace: any) => trace.tone === "caution")).toHaveLength(
      3,
    );
  });

  test("switching variants preserves the current business view and filters", () => {
    const model = loadModel();
    const report = {
      ...model.createInitialState("#guided"),
      view: "report",
      reportFilter: "danger",
    };
    const next = model.reduce(report, { type: "SET_VARIANT", variant: "matrix" });
    expect(next.variant).toBe("matrix");
    expect(next.view).toBe("report");
    expect(next.reportFilter).toBe("danger");
  });

  test("only a completed scan may enter the report view", () => {
    const model = loadModel();
    const ready = {
      ...model.createInitialState("#guided"),
      view: "ready",
      selection: model.demoProject.selection,
    };
    expect(model.reduce(ready, { type: "SET_VIEW", view: "report" })).toBe(ready);
  });

  test("folder files are grouped by their first relative directory", () => {
    const model = loadModel();
    const selection = model.selectionFromFiles([
      {
        name: "技术方案.docx",
        webkitRelativePath: "演示项目/华远建设/技术方案.docx",
        size: 1200,
      },
      {
        name: "报价.xlsx",
        webkitRelativePath: "演示项目/启明工程/报价.xlsx",
        size: 800,
      },
      {
        name: "说明.txt",
        webkitRelativePath: "演示项目/启明工程/说明.txt",
        size: 20,
      },
    ]);
    expect(selection.rootName).toBe("演示项目");
    expect(selection.bidderCount).toBe(2);
    expect(selection.fileCount).toBe(2);
    expect(selection.ignoredCount).toBe(1);
    expect(selection.groups.map((group: { name: string }) => group.name)).toEqual([
      "华远建设",
      "启明工程",
    ]);
  });

  test("report and metadata filters compose deterministically", () => {
    const model = loadModel();
    const base = {
      ...model.createInitialState("#verdict"),
      selection: model.demoProject.selection,
    };
    expect(model.visibleTraces({ ...base, reportFilter: "danger" })).toHaveLength(2);
    expect(model.visibleTraces({ ...base, reportFilter: "caution" })).toHaveLength(3);
    const filtered = model.visibleDocuments({
      ...base,
      metadataFilters: {
        bidderId: "bidder-a",
        query: "技术方案",
        duplicatesOnly: true,
      },
    });
    expect(filtered.every((doc: any) => doc.bidderId === "bidder-a")).toBe(true);
    expect(filtered.every((doc: any) => doc.isDuplicate)).toBe(true);
  });
});

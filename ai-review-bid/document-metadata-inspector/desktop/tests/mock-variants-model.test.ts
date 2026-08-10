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
  test("static entry loads only local classic assets", () => {
    const html = readFileSync(
      resolve(import.meta.dirname, "../mock/design-spec-variants/index.html"),
      "utf8",
    );
    expect(html).toContain('data-testid="app-root"');
    expect(html).toContain('type="file"');
    expect(html).not.toMatch(/https?:\/\//u);
    expect(html).not.toContain('type="module"');
    expect(html).not.toMatch(/[😀-🙏]/u);
    for (const asset of [
      "styles.css",
      "guided.css",
      "verdict.css",
      "matrix.css",
      "model.js",
      "render-common.js",
      "render-guided.js",
      "render-verdict.js",
      "render-matrix.js",
      "app.js",
    ]) {
      expect(html).toContain(asset);
    }
  });

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

  test("direct scan-state navigation is an invalid transition", () => {
    const model = loadModel();
    const landing = model.createInitialState("#guided");
    expect(model.reduce(landing, { type: "SET_VIEW", view: "scanning" })).toBe(landing);
    expect(model.reduce(landing, { type: "SET_VIEW", view: "stopped" })).toBe(landing);
    expect(model.reduce(landing, { type: "SET_VIEW", view: "failed" })).toBe(landing);
  });

  test("scan stop and completion are distinct terminal transitions", () => {
    const model = loadModel();
    const ready = {
      ...model.createInitialState("#guided"),
      view: "ready",
      selection: model.demoProject.selection,
    };
    const scanning = model.reduce(ready, { type: "START_SCAN" });
    expect(scanning.view).toBe("scanning");
    const stopped = model.reduce(scanning, { type: "STOP_SCAN" });
    expect(stopped.view).toBe("stopped");
    expect(stopped.progress.percent).toBeLessThan(100);
    const failed = model.reduce(scanning, { type: "FAIL_SCAN", error: "演示解析器未响应" });
    expect(failed.view).toBe("failed");
    expect(failed.error).toBe("演示解析器未响应");
    const restarted = model.reduce(stopped, { type: "START_SCAN" });
    const complete = model.reduce(restarted, { type: "COMPLETE_SCAN" });
    expect(complete.view).toBe("report");
    expect(complete.progress.percent).toBe(100);
    expect(complete.progress.completedFiles).toBe(16);
  });

  test("scan progress accepts a scheduled stage only while the scan is active", () => {
    const model = loadModel();
    const ready = {
      ...model.createInitialState("#guided"),
      view: "ready",
      selection: model.demoProject.selection,
    };
    const scanning = model.reduce(ready, { type: "START_SCAN" });
    const progress = {
      percent: 8,
      completedFiles: 0,
      stage: "清单校验",
      message: "正在校验 16 份文档",
    };
    const progressed = model.reduce(scanning, { type: "SCAN_PROGRESS", progress });
    expect(progressed.progress).toEqual(progress);
    expect(model.reduce(ready, { type: "SCAN_PROGRESS", progress })).toBe(ready);
  });

  test("scan progress accepts only the next literal deterministic stage", () => {
    const model = loadModel();
    const ready = {
      ...model.createInitialState("#guided"),
      view: "ready",
      selection: model.demoProject.selection,
    };
    const stages = [
      { percent: 8, completedFiles: 0, stage: "清单校验", message: "正在校验 16 份文档" },
      { percent: 24, completedFiles: 3, stage: "容器识别", message: "识别 PDF、OLE 与 OPC 容器" },
      {
        percent: 58,
        completedFiles: 9,
        stage: "多引擎解析",
        message: "原生解析、Apache 与 ExifTool 交叉取证",
      },
      { percent: 84, completedFiles: 14, stage: "证据比较", message: "比较跨投标人身份与环境痕迹" },
      { percent: 100, completedFiles: 16, stage: "生成报告", message: "核验完成，正在呈现报告" },
    ];
    let scanning = model.reduce(ready, { type: "START_SCAN" });

    for (const invalidProgress of [
      { ...stages[0], percent: -1 },
      { ...stages[0], percent: 101 },
      { ...stages[0], completedFiles: -1 },
      { ...stages[0], completedFiles: 17 },
      { ...stages[0], stage: "虚构阶段" },
      { ...stages[0], message: "虚构消息" },
      stages[1],
    ]) {
      expect(model.reduce(scanning, { type: "SCAN_PROGRESS", progress: invalidProgress })).toBe(
        scanning,
      );
    }

    for (const stage of stages) {
      scanning = model.reduce(scanning, { type: "SCAN_PROGRESS", progress: stage });
      expect(scanning.progress).toEqual(stage);
    }
    expect(model.reduce(scanning, { type: "SCAN_PROGRESS", progress: stages.at(-1) })).toBe(
      scanning,
    );
    expect(model.SCAN_STAGES).toEqual(stages);
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

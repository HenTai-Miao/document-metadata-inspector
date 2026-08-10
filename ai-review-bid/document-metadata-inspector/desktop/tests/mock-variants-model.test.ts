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

  test("matrix presentation keeps one stable identity for each source trace", () => {
    const model = loadModel();
    const evidenceIds = model.demoProject.matrixEvidence.map(
      (evidence: { id: string }) => evidence.id,
    );
    expect(new Set(evidenceIds).size).toBe(evidenceIds.length);
    expect(evidenceIds).toContain("trace-matching-application-version");
    expect(evidenceIds).not.toContain("context-matching-application-version");
    const applicationEvidence = model.demoProject.matrixEvidence.find(
      (evidence: { id: string }) => evidence.id === "trace-matching-application-version",
    );
    expect(applicationEvidence).toMatchObject({
      tone: "neutral",
      field: "应用 / 版本",
    });
    const applicationRow = model.demoProject.matrixRows.find(
      (row: { id: string }) => row.id === "application-version",
    );
    expect(applicationRow.cells["bidder-b"].evidenceId).toBe("trace-matching-application-version");
    expect(applicationRow.cells["bidder-d"].evidenceId).toBe("trace-matching-application-version");
  });

  test("matrix evidence selection validates the exact evidence and bidder pair", () => {
    const model = loadModel();
    const report = {
      ...model.createInitialState("#matrix"),
      view: "report",
      selection: model.demoProject.selection,
    };
    const valid = model.reduce(report, {
      type: "SELECT_EVIDENCE",
      evidenceId: "trace-author-wang-lei",
      bidderId: "bidder-a",
    });
    expect(valid.matrixSelection).toEqual({
      evidenceId: "trace-author-wang-lei",
      bidderId: "bidder-a",
    });
    expect(
      model.reduce(report, {
        type: "SELECT_EVIDENCE",
        evidenceId: "trace-author-wang-lei",
        bidderId: "bidder-c",
      }),
    ).toBe(report);
  });

  test("trace metadata navigation replaces stale matrix selection and returns to its cell", () => {
    const model = loadModel();
    const report = {
      ...model.createInitialState("#verdict"),
      view: "report",
      selection: model.demoProject.selection,
      reportFilter: "caution",
      expandedTraceId: "trace-matching-application-version",
      matrixSelection: {
        evidenceId: "trace-author-wang-lei",
        bidderId: "bidder-a",
      },
    };
    const metadata = model.reduce(report, {
      type: "SHOW_METADATA_FOR_TRACE",
      traceId: "trace-matching-application-version",
    });
    expect(metadata.matrixSelection).toBeNull();
    const matrixMetadata = model.reduce(metadata, {
      type: "SET_VARIANT",
      variant: "matrix",
    });
    const returned = model.reduce(matrixMetadata, { type: "RETURN_TO_REPORT" });
    expect(returned.matrixSelection).toEqual({
      evidenceId: "trace-matching-application-version",
      bidderId: "bidder-b",
    });
    expect(returned.reportFilter).toBe("caution");
    expect(returned.expandedTraceId).toBe("trace-matching-application-version");
  });

  test("matrix metadata return cannot recreate an origin excluded by the report filter", () => {
    const model = loadModel();
    const metadata = {
      ...model.createInitialState("#matrix"),
      view: "metadata",
      selection: model.demoProject.selection,
      reportFilter: "danger",
      metadataOriginTraceId: "trace-matching-application-version",
      matrixSelection: null,
    };
    const returned = model.reduce(metadata, { type: "RETURN_TO_REPORT" });
    expect(returned.view).toBe("report");
    expect(returned.reportFilter).toBe("danger");
    expect(returned.matrixSelection).toBeNull();
  });

  test("changing report filter clears an open selection excluded by that filter", () => {
    const model = loadModel();
    const report = {
      ...model.createInitialState("#matrix"),
      view: "report",
      selection: model.demoProject.selection,
      matrixSelection: {
        evidenceId: "trace-author-wang-lei",
        bidderId: "bidder-a",
      },
    };
    const caution = model.reduce(report, {
      type: "SET_REPORT_FILTER",
      reportFilter: "caution",
    });
    expect(caution.matrixSelection).toBeNull();
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

  test("trace metadata navigation and report return are atomic state transitions", () => {
    const model = loadModel();
    const report = {
      ...model.createInitialState("#guided"),
      view: "report",
      selection: model.demoProject.selection,
      reportFilter: "danger",
      expandedTraceId: "trace-modifier-zhangmin",
    };
    const metadata = model.reduce(report, {
      type: "SHOW_METADATA_FOR_TRACE",
      traceId: "trace-modifier-zhangmin",
    });
    expect(metadata.view).toBe("metadata");
    expect(metadata.metadataFilters).toEqual({
      bidderId: "bidder-c",
      query: "报价.xlsx",
      duplicatesOnly: true,
    });
    expect(metadata.selectedEvidenceId).toBe("bidder-c-document-2");
    expect(metadata.metadataOriginTraceId).toBe("trace-modifier-zhangmin");

    const returned = model.reduce(metadata, { type: "RETURN_TO_REPORT" });
    expect(returned.view).toBe("report");
    expect(returned.reportFilter).toBe("danger");
    expect(returned.expandedTraceId).toBe("trace-modifier-zhangmin");
  });

  test("verdict trace navigation searches by evidence value without changing Guided", () => {
    const model = loadModel();
    const report = {
      ...model.createInitialState("#verdict"),
      view: "report",
      selection: model.demoProject.selection,
    };
    const metadata = model.reduce(report, {
      type: "SHOW_METADATA_FOR_TRACE",
      traceId: "trace-shared-template",
    });
    expect(metadata.view).toBe("metadata");
    expect(metadata.metadataFilters).toEqual({
      bidderId: "bidder-a",
      query: "SmartPark_Bid_v4.dotx",
      duplicatesOnly: true,
    });
    expect(metadata.selectedEvidenceId).toBe("bidder-a-document-1");

    const guidedMetadata = model.reduce(
      { ...report, variant: "guided" },
      {
        type: "SHOW_METADATA_FOR_TRACE",
        traceId: "trace-shared-template",
      },
    );
    expect(guidedMetadata.metadataFilters.query).toBe("技术方案.docx");
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
    expect(selection.source).toBe("local");
    expect(selection.rootFiles).toEqual([]);
    expect(selection.groups.map((group: { name: string }) => group.name)).toEqual([
      "华远建设",
      "启明工程",
    ]);
  });

  test("root-only local selection stays distinct from the demonstration tree", () => {
    const model = loadModel();
    const selection = model.selectionFromFiles([
      {
        name: "技术方案.docx",
        webkitRelativePath: "本机项目/技术方案.docx",
        size: 1200,
      },
      {
        name: "报价.xlsx",
        webkitRelativePath: "本机项目/报价.xlsx",
        size: 800,
      },
    ]);
    expect(model.demoProject.selection.source).toBe("demo");
    expect(selection).toMatchObject({
      source: "local",
      bidderCount: 0,
      fileCount: 2,
      groups: [],
      boundaryWarning: "所选根目录中包含文件，未发现投标人目录。",
    });
    expect(selection.rootFiles.map((file: { name: string }) => file.name)).toEqual([
      "技术方案.docx",
      "报价.xlsx",
    ]);
  });

  test("display progress scales canonical scan stages to the selected file count", () => {
    const model = loadModel();
    const localSelection = model.selectionFromFiles([
      {
        name: "技术方案.docx",
        webkitRelativePath: "本机项目/技术方案.docx",
      },
      {
        name: "报价.xlsx",
        webkitRelativePath: "本机项目/报价.xlsx",
      },
    ]);
    expect(model.progressForSelection(model.demoProject.selection, model.SCAN_STAGES[1])).toEqual(
      model.SCAN_STAGES[1],
    );
    expect(model.progressForSelection(localSelection, model.SCAN_STAGES[1])).toMatchObject({
      completedFiles: 0,
      message: "识别 PDF、OLE 与 OPC 容器",
    });
    expect(model.progressForSelection(localSelection, model.SCAN_STAGES[2]).completedFiles).toBe(1);
    expect(model.progressForSelection(localSelection, model.SCAN_STAGES.at(-1))).toMatchObject({
      completedFiles: 2,
      message: "核验完成，正在呈现报告",
    });
    expect(model.progressForSelection(localSelection, model.SCAN_STAGES[0]).message).toBe(
      "正在校验 2 份文档",
    );
  });

  test("local tree selection applies one global display budget across root and groups", () => {
    const model = loadModel();
    const files = Array.from({ length: 501 }, (_, index) => ({
      name: `文档-${index + 1}.docx`,
      webkitRelativePath:
        index < 250
          ? `超大项目/文档-${index + 1}.docx`
          : `超大项目/投标人甲/文档-${index + 1}.docx`,
    }));
    const selection = model.selectionFromFiles(files);
    expect(selection.fileCount).toBe(501);
    expect(selection.displayedFileCount).toBe(500);
    expect(selection.hiddenFileCount).toBe(1);
    expect(selection.files).toHaveLength(500);
    expect(selection.rootFiles).toHaveLength(250);
    expect(selection.groups).toHaveLength(1);
    expect(selection.groups[0].files).toHaveLength(250);
    expect(
      selection.rootFiles.length +
        selection.groups.reduce(
          (count: number, group: { files: unknown[] }) => count + group.files.length,
          0,
        ),
    ).toBe(500);
  });

  test("display progress clamps malformed counts to finite non-negative integers", () => {
    const model = loadModel();
    const local = {
      ...model.demoProject.selection,
      source: "local",
    };
    for (const fileCount of [-1, Number.NaN, Number.POSITIVE_INFINITY]) {
      const displayed = model.progressForSelection(
        { ...local, fileCount },
        { ...model.SCAN_STAGES[2], completedFiles: Number.POSITIVE_INFINITY },
      );
      expect(displayed.completedFiles).toBe(0);
      expect(Number.isFinite(displayed.completedFiles)).toBe(true);
    }
    expect(
      model.progressForSelection(local, {
        ...model.SCAN_STAGES[2],
        completedFiles: -7,
      }).completedFiles,
    ).toBe(0);
    expect(
      model.progressForSelection(model.demoProject.selection, {
        ...model.SCAN_STAGES[2],
        completedFiles: 99,
      }).completedFiles,
    ).toBe(16);
  });

  test("selection transition rejects malformed shapes and preserves state identity", () => {
    const model = loadModel();
    const landing = model.createInitialState("#matrix");
    const invalidSelections = [
      null,
      { fileCount: 1 },
      { ...model.demoProject.selection, source: "remote" },
      { ...model.demoProject.selection, fileCount: -1 },
      { ...model.demoProject.selection, fileCount: Number.NaN },
      { ...model.demoProject.selection, fileCount: Number.POSITIVE_INFINITY },
      { ...model.demoProject.selection, groups: null },
      { ...model.demoProject.selection, rootFiles: null },
      { ...model.demoProject.selection, files: null },
    ];
    for (const selection of invalidSelections) {
      expect(model.reduce(landing, { type: "SET_SELECTION", selection })).toBe(landing);
    }
    expect(
      model.reduce(landing, {
        type: "SET_SELECTION",
        selection: model.demoProject.selection,
      }).view,
    ).toBe("ready");
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

  test("duplicates-only returns the exact union of trace-bearing documents", () => {
    const model = loadModel();
    const state = {
      ...model.createInitialState("#guided"),
      selection: model.demoProject.selection,
      metadataFilters: { bidderId: "", query: "", duplicatesOnly: true },
    };
    expect(model.visibleDocuments(state).map((document: { id: string }) => document.id)).toEqual([
      "bidder-a-document-1",
      "bidder-a-document-2",
      "bidder-b-document-1",
      "bidder-b-document-2",
      "bidder-b-document-3",
      "bidder-c-document-1",
      "bidder-c-document-2",
      "bidder-d-document-2",
      "bidder-d-document-3",
    ]);
  });

  test("metadata text search finds documents by normalized evidence values", () => {
    const model = loadModel();
    const state = {
      ...model.createInitialState("#guided"),
      selection: model.demoProject.selection,
      metadataFilters: { bidderId: "", query: "王磊", duplicatesOnly: false },
    };
    expect(model.visibleDocuments(state).map((document: { id: string }) => document.id)).toEqual([
      "bidder-a-document-1",
      "bidder-b-document-1",
    ]);
  });
});

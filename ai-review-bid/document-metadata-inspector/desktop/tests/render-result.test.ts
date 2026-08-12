import { describe, expect, test } from "vitest";

import { createDocumentDetailLoader } from "../src/renderer/render-metadata";
import { buildProblemLabelReportModel, connectionTracks } from "../src/renderer/render-result";
import type {
  DocumentDetail,
  DocumentSummary,
  ResultGroup,
  ScanResult,
  TraceSummary,
} from "../src/shared/contracts";

function trace(
  id: string,
  tone: TraceSummary["tone"],
  groupIds: string[] = ["bidder-a", "bidder-b"],
): TraceSummary {
  return {
    id,
    tone,
    kind: tone === "danger" ? "person_trace" : "document_environment_trace",
    label: id,
    value: id,
    groupIds,
    documentIds: ["document-a", "document-b"],
    fieldNames: ["author"],
    evidenceCount: 2,
  };
}

function document(id: string, name: string): DocumentSummary {
  return {
    id,
    name,
    relativePath: name,
    format: "docx",
    family: "ooxml",
    status: "complete",
    observationCount: 1,
    parserRunCount: 1,
    warningCount: 0,
    sizeBytes: 128,
    sha256Prefix: id.slice(0, 12),
    parserRuns: [],
    keyFields: {
      author: "",
      created: "",
      modified: "",
      lastModifiedBy: "",
      company: "",
      template: "",
    },
  };
}

describe("createDocumentDetailLoader", () => {
  test("loads each document once across concurrent and repeated expansion", async () => {
    const calls: string[] = [];
    let release: ((detail: DocumentDetail) => void) | undefined;
    const pending = new Promise<DocumentDetail>((resolve) => {
      release = resolve;
    });
    const load = createDocumentDetailLoader((documentId) => {
      calls.push(documentId);
      return documentId === "document-a"
        ? pending
        : Promise.resolve({
            schema_version: "1.0",
            document_id: documentId,
            observations: [{ label: "author", value: "Alice" }],
          });
    });

    const first = load("document-a");
    const repeated = load("document-a");
    release?.({
      schema_version: "1.0",
      document_id: "document-a",
      observations: [{ label: "author", value: "Alice" }],
    });

    await expect(first).resolves.toMatchObject({ document_id: "document-a" });
    await expect(repeated).resolves.toMatchObject({ document_id: "document-a" });
    await expect(load("document-a")).resolves.toMatchObject({ document_id: "document-a" });
    await expect(load("document-b")).resolves.toMatchObject({ document_id: "document-b" });
    expect(calls).toEqual(["document-a", "document-b"]);
  });

  test("keeps one failed document isolated and does not refetch it", async () => {
    const calls: string[] = [];
    const load = createDocumentDetailLoader((documentId) => {
      calls.push(documentId);
      return documentId === "broken"
        ? Promise.reject(new Error("private path must not escape"))
        : Promise.resolve({
            schema_version: "1.0",
            document_id: documentId,
            observations: [],
          });
    });

    await expect(load("broken")).rejects.toThrow();
    await expect(load("broken")).rejects.toThrow();
    await expect(load("healthy")).resolves.toMatchObject({ document_id: "healthy" });
    expect(calls).toEqual(["broken", "healthy"]);
  });
});

function group(
  id: string,
  name: string,
  documents: DocumentSummary[],
  kind: ResultGroup["kind"] = "bidder",
): ResultGroup {
  return { id, kind, name, documents };
}

function scanResult(overrides: Partial<ScanResult> = {}): ScanResult {
  return {
    rootName: "4-投标文件",
    scannedAt: "2026-08-10T01:58:00.000Z",
    documentCount: 6,
    completeDocumentCount: 6,
    observationCount: 120,
    parserRunCount: 18,
    warningCount: 0,
    bidderCount: 4,
    groups: [],
    personTraces: [],
    cautionTraces: [],
    ...overrides,
  };
}

describe("connectionTracks", () => {
  test("assigns distinct stable tracks to traces joining the same bidder pair", () => {
    const tracks = connectionTracks([
      trace("template", "caution"),
      trace("timestamp", "caution", ["bidder-b", "bidder-a"]),
      trace("author", "danger"),
    ]);

    expect(tracks.map((track) => track.traceIndex)).toEqual([0, 1, 2]);
    expect(tracks.every((track) => track.fromGroupId === "bidder-a")).toBe(true);
    expect(tracks.every((track) => track.toGroupId === "bidder-b")).toBe(true);
    expect(new Set(tracks.map((track) => track.offset)).size).toBe(3);
    expect(tracks[2]?.offset).toBeGreaterThan(tracks[1]?.offset ?? 0);
  });
});

describe("buildProblemLabelReportModel", () => {
  test("returns retained labels and reuses a multi-field trace with stable company pairs", () => {
    const result = scanResult({
      groups: [
        group("root-files", "根目录文件", [document("root-doc", "说明.docx")], "root-files"),
        group("bidder-a", "公司 A", [document("a-author", "投标函.docx")]),
        group("bidder-b", "公司 B", [document("b-author", "报价清单.xlsx")]),
        group("bidder-c", "公司 C", [document("c-author", "技术标.pdf")]),
        group("bidder-safe", "无异常公司", [document("safe-doc", "附件.docx")]),
      ],
      personTraces: [
        {
          ...trace("person", "danger", ["bidder-a", "bidder-b", "bidder-c"]),
          value: "李建国",
          fieldNames: ["author", "last_modified_by", "manager"],
          documentIds: ["a-author", "missing-document", "b-author", "c-author", "a-author"],
        },
      ],
    });

    const model = buildProblemLabelReportModel(result);

    expect(model.sections.map((section) => section.label)).toEqual([
      "创建人检测",
      "修改人检测",
      "批注人检测",
      "修订人检测",
      "创建时间检测",
      "修改时间检测",
    ]);
    expect(model).toMatchObject({ riskCount: 2, safeCount: 4, relationCount: 6 });
    expect(model.sections[0]).toMatchObject({
      key: "author",
      label: "创建人检测",
      status: "risk",
      relationCount: 3,
    });
    expect(model.sections[0]?.hits[0]).toMatchObject({
      value: "李建国",
      relationCount: 3,
      missingEvidence: false,
      pairs: [
        {
          left: { companyId: "bidder-a", company: "公司 A", files: ["投标函.docx"] },
          right: { companyId: "bidder-b", company: "公司 B", files: ["报价清单.xlsx"] },
        },
        {
          left: { companyId: "bidder-a", company: "公司 A", files: ["投标函.docx"] },
          right: { companyId: "bidder-c", company: "公司 C", files: ["技术标.pdf"] },
        },
        {
          left: { companyId: "bidder-b", company: "公司 B", files: ["报价清单.xlsx"] },
          right: { companyId: "bidder-c", company: "公司 C", files: ["技术标.pdf"] },
        },
      ],
    });
    expect(model.sections[1]?.hits).toEqual(model.sections[0]?.hits);
    expect(model.sections[2]).toEqual({
      key: "comment_author",
      label: "批注人检测",
      status: "safe",
      hits: [],
      relationCount: 0,
    });
    expect(JSON.stringify(model)).not.toContain("missing-document");
    expect(JSON.stringify(model)).not.toContain("无异常公司");
    expect(JSON.stringify(model)).not.toContain("root-doc");
    expect(JSON.stringify(model)).not.toContain("附件.docx");
  });

  test("merges the same value without manufacturing a transitive company pair", () => {
    const model = buildProblemLabelReportModel(
      scanResult({
        groups: [
          group("bidder-a", "公司 A", [document("a", "投标函.docx")]),
          group("bidder-b", "公司 B", [document("b", "报价清单.xlsx")]),
          group("bidder-c", "公司 C", [document("c", "技术标.pdf")]),
        ],
        personTraces: [
          {
            ...trace("author-ab", "danger", ["bidder-a", "bidder-b"]),
            value: "李建国",
            documentIds: ["a", "b"],
          },
          {
            ...trace("author-bc", "danger", ["bidder-b", "bidder-c"]),
            value: "李建国",
            documentIds: ["b", "c"],
          },
        ],
      }),
    );

    expect(model.sections[0]?.hits).toHaveLength(1);
    expect(model.sections[0]?.hits[0]?.pairs.map((pair) => pair.id)).toEqual([
      "bidder-a\0bidder-b",
      "bidder-b\0bidder-c",
    ]);
    expect(model.sections[0]?.hits[0]?.relationCount).toBe(2);
  });

  test("shows all labels as safe when there are no cross-bidder traces", () => {
    const model = buildProblemLabelReportModel(
      scanResult({
        groups: [group("bidder-safe", "无异常公司", [document("safe", "报价.xlsx")])],
      }),
    );

    expect(model.sections).toHaveLength(6);
    expect(model.sections.every((section) => section.status === "safe")).toBe(true);
    expect(model).toMatchObject({ riskCount: 0, safeCount: 6, relationCount: 0 });
  });

  test("ignores retired historical traces while retaining supported aliases", () => {
    const model = buildProblemLabelReportModel(
      scanResult({
        groups: [
          group("bidder-a", "公司 A", [document("a", "投标函.docx")]),
          group("bidder-b", "公司 B", [document("b", "报价清单.xlsx")]),
        ],
        personTraces: [
          {
            ...trace("comment", "danger", ["historical-a", "historical-b"]),
            fieldNames: ["annotation_author"],
            value: "批注用户",
            documentIds: ["a", "b"],
          },
          {
            ...trace("signature-signer-name", "danger", ["historical-a", "historical-b"]),
            fieldNames: ["signature_signer_name"],
            value: "历史签名用户",
            documentIds: ["a", "b"],
          },
          {
            ...trace("signer-identity", "danger", ["historical-a", "historical-b"]),
            fieldNames: ["signer_identity"],
            value: "历史签名身份",
            documentIds: ["a", "b"],
          },
          {
            ...trace("manager", "danger", ["historical-a", "historical-b"]),
            fieldNames: ["manager"],
            value: "历史经理",
            documentIds: ["a", "b"],
          },
          {
            ...trace("company", "danger", ["historical-a", "historical-b"]),
            fieldNames: ["company"],
            value: "历史公司",
            documentIds: ["a", "b"],
          },
          {
            ...trace("username-path-trace", "danger", ["historical-a", "historical-b"]),
            fieldNames: ["username_path_trace"],
            value: "历史路径用户名",
            documentIds: ["a", "b"],
          },
          {
            ...trace("template", "danger", ["historical-a", "historical-b"]),
            fieldNames: ["template"],
            value: "历史模板",
            documentIds: ["a", "b"],
          },
        ],
      }),
    );

    expect(model.sections[2]).toMatchObject({
      key: "comment_author",
      status: "risk",
      hits: [{ value: "批注用户" }],
    });
    expect(model.sections).toHaveLength(6);
    expect(model).toMatchObject({ riskCount: 1, safeCount: 5 });
    const serialized = JSON.stringify(model);
    for (const retiredValue of [
      "历史签名用户",
      "历史签名身份",
      "历史经理",
      "历史公司",
      "历史路径用户名",
      "历史模板",
      "signature_signer_name",
      "signer_identity",
      "manager",
      "company",
      "username_path_trace",
      "template",
    ]) {
      expect(serialized).not.toContain(retiredValue);
    }
  });

  test("keeps an identified risk visible when bidder file evidence cannot be mapped", () => {
    const model = buildProblemLabelReportModel(
      scanResult({
        groups: [group("bidder-a", "公司 A", [document("a", "投标函.docx")])],
        personTraces: [
          {
            ...trace("unmapped", "danger", ["unknown-a", "unknown-b"]),
            value: "无法映射的用户",
            documentIds: ["secret-document-id"],
          },
        ],
      }),
    );

    expect(model.sections[0]).toMatchObject({
      status: "risk",
      hits: [
        {
          value: "无法映射的用户",
          pairs: [],
          relationCount: 0,
          missingEvidence: true,
        },
      ],
    });
    expect(model).toMatchObject({ riskCount: 1, safeCount: 5, relationCount: 0 });
    expect(JSON.stringify(model)).not.toContain("secret-document-id");
  });
});

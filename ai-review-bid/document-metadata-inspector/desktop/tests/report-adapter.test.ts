import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "vitest";

import { discoverFolder } from "../src/main/folder-discovery";
import {
  adaptComparisonReport,
  adaptDesktopBundleSummary,
  adaptReportDocumentDetail,
} from "../src/main/report-adapter";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

function documentReport(sourcePathSha256: string, sha256: string, observationCount: number) {
  return {
    display_name: "同名投标文件.pdf",
    source_path_sha256: sourcePathSha256,
    size_bytes: 1024,
    sha256,
    identity: {
      declared_format: "pdf",
      expected_container: "pdf",
      family: "pdf",
      observed_container: "pdf",
      status: "confirmed",
    },
    status: "complete",
    observations: Array.from({ length: observationCount }, (_, index) => ({
      canonical_name: `field_${index}`,
    })),
    parser_runs: [
      { parser_name: "native-pdf", status: "succeeded", warnings: [] },
      { parser_name: "apache-tika", status: "succeeded", warnings: [] },
      { parser_name: "exiftool", status: "succeeded", warnings: [] },
    ],
    embedded_documents: [{ warnings: ["embedded-warning"] }],
    encrypted: false,
    password_required: false,
    warnings: [],
  };
}

function match(traceKind: string, value: string, documentIds: string[]) {
  return {
    canonical_name: traceKind === "person_trace" ? "author" : "template",
    normalized_value: value.toLocaleLowerCase("zh-CN"),
    document_names: ["同名投标文件.pdf"],
    evidence_count: documentIds.length,
    trace_kind: traceKind,
    field_names: [traceKind === "person_trace" ? "author" : "template"],
    raw_values: documentIds.map(() => value),
    evidence: documentIds.map((documentId, index) => ({
      observation_id: `observation-${index}`,
      document_name: "同名投标文件.pdf",
      canonical_name: traceKind === "person_trace" ? "author" : "template",
      raw_value: value,
      parser_name: "exiftool",
      source_kind: "exiftool_grouped_tag",
      location: "PDF",
      document_id: documentId,
    })),
    document_ids: documentIds,
  };
}

describe("adaptComparisonReport", () => {
  test("maps duplicate names by path hash and excludes traces confined to one bidder", async () => {
    // Mapping by display name would put both same-name documents in the first bidder.
    const root = await mkdtemp(join(tmpdir(), "docmeta-adapter-test-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "投标人甲"), { recursive: true });
    await mkdir(join(root, "投标人乙"), { recursive: true });
    await writeFile(join(root, "投标人甲", "同名投标文件.pdf"), "a-one");
    await writeFile(join(root, "投标人甲", "附件.pdf"), "a-two");
    await writeFile(join(root, "投标人乙", "同名投标文件.pdf"), "b-one");
    const selection = await discoverFolder(root);
    const [groupA, groupB] = selection.groups;
    expect(groupA).toBeDefined();
    expect(groupB).toBeDefined();
    const aDocuments = groupA?.name === "投标人甲" ? groupA.files : groupB?.files;
    const bDocuments = groupA?.name === "投标人乙" ? groupA.files : groupB?.files;
    const aSameName = aDocuments?.find((document) => document.name === "同名投标文件.pdf");
    const aAttachment = aDocuments?.find((document) => document.name === "附件.pdf");
    const bSameName = bDocuments?.find((document) => document.name === "同名投标文件.pdf");
    expect(aSameName).toBeDefined();
    expect(aAttachment).toBeDefined();
    expect(bSameName).toBeDefined();

    const report = {
      schema_version: "1.0",
      warnings: [],
      documents: [
        documentReport(aSameName?.sourcePathSha256 ?? "", "sha-a-one", 2),
        documentReport(aAttachment?.sourcePathSha256 ?? "", "sha-a-two", 1),
        documentReport(bSameName?.sourcePathSha256 ?? "", "sha-b-one", 3),
      ],
      matches: [
        match("person_trace", "同组作者", [
          aSameName?.sourcePathSha256 ?? "",
          aAttachment?.sourcePathSha256 ?? "",
        ]),
        match("person_trace", "跨组作者", [
          aSameName?.sourcePathSha256 ?? "",
          bSameName?.sourcePathSha256 ?? "",
        ]),
        match("document_environment_trace", "Normal.dotm", [
          aAttachment?.sourcePathSha256 ?? "",
          bSameName?.sourcePathSha256 ?? "",
        ]),
      ],
    };

    const result = adaptComparisonReport(report, selection);

    expect(result.documentCount).toBe(3);
    expect(result.completeDocumentCount).toBe(3);
    expect(result.observationCount).toBe(6);
    expect(result.parserRunCount).toBe(9);
    expect(result.groups.map((group) => group.documents.length).sort()).toEqual([1, 2]);
    expect(result.groups[0]?.documents[0]?.parserRuns.map((run) => run.name)).toEqual([
      "native-pdf",
      "apache-tika",
      "exiftool",
    ]);
    expect(result.groups[0]?.documents[0]?.warningCount).toBe(1);
    expect(result.personTraces).toHaveLength(1);
    expect(result.personTraces[0]).toMatchObject({ value: "跨组作者", tone: "danger" });
    expect(result.cautionTraces).toHaveLength(1);
    expect(result.cautionTraces[0]).toMatchObject({ value: "Normal.dotm", tone: "caution" });
    expect(result.personTraces.some((trace) => trace.value === "同组作者")).toBe(false);
  });

  test("adapts compact bundle summaries without full observation arrays", async () => {
    const root = await mkdtemp(join(tmpdir(), "docmeta-compact-adapter-test-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "投标人甲"), { recursive: true });
    await mkdir(join(root, "投标人乙"), { recursive: true });
    await writeFile(join(root, "投标人甲", "甲.pdf"), "a");
    await writeFile(join(root, "投标人乙", "乙.pdf"), "b");
    const selection = await discoverFolder(root);
    const documentIds = selection.groups.flatMap((group) =>
      group.files.map((file) => file.sourcePathSha256),
    );
    const documents = selection.groups.flatMap((group) =>
      group.files.map((file) => ({
        source_path_sha256: file.sourcePathSha256,
        display_name: file.name,
        declared_format: "pdf",
        family: "pdf",
        status: "complete",
        observation_count: 80_000,
        parser_run_count: 3,
        warning_count: 2,
        size_bytes: file.sizeBytes,
        sha256_prefix: "0123456789ab",
        parser_runs: [{ name: "native-pdf", status: "succeeded", warning_count: 0 }],
        key_fields: {
          author: "Alice",
          created: "",
          modified: "",
          last_modified_by: "",
          company: "",
          template: "",
        },
      })),
    );

    const result = adaptDesktopBundleSummary(
      {
        schema_version: "1.0",
        document_count: 2,
        complete_document_count: 2,
        observation_count: 160_000,
        parser_run_count: 6,
        warning_count: 4,
        documents,
        matches: [
          {
            canonical_name: "author",
            normalized_value: "alice",
            trace_kind: "person_trace",
            field_names: ["author"],
            raw_values: ["Alice", "Alice"],
            evidence_count: 2,
            document_ids: documentIds,
          },
        ],
        warnings: [],
      },
      selection,
    );

    expect(result).toMatchObject({
      documentCount: 2,
      completeDocumentCount: 2,
      observationCount: 160_000,
      parserRunCount: 6,
      warningCount: 4,
    });
    expect(result.groups.flatMap((group) => group.documents)).toHaveLength(2);
    expect("observations" in (result.groups[0]?.documents[0] ?? {})).toBe(false);
    expect(result.groups[0]?.documents[0]?.keyFields.author).toBe("Alice");
    expect(result.personTraces).toHaveLength(1);
  });
});

describe("adaptReportDocumentDetail", () => {
  test("preserves retired metadata rows in source order", () => {
    const documentId = "document-with-retired-metadata";
    const report = {
      schema_version: "1.0",
      documents: [
        {
          display_name: "历史文档.docx",
          source_path_sha256: documentId,
          sha256: "a".repeat(64),
          status: "complete",
          observations: [
            { canonical_name: "manager", raw_name: "经理", raw_value: "王经理" },
            { canonical_name: "company", raw_name: "公司", raw_value: "示例公司" },
            {
              canonical_name: "signature_signer_name",
              raw_name: "签名人",
              raw_value: "张签名",
            },
            {
              canonical_name: "username_path_trace",
              raw_name: "路径用户名",
              raw_value: "review-user",
            },
            { canonical_name: "template", raw_name: "模板", raw_value: "Normal.dotm" },
          ],
        },
      ],
      matches: [],
    };

    expect(adaptReportDocumentDetail(report, documentId)).toMatchObject({
      document_id: documentId,
      observations: [
        { label: "经理", value: "王经理" },
        { label: "公司", value: "示例公司" },
        { label: "签名人", value: "张签名" },
        { label: "路径用户名", value: "review-user" },
        { label: "模板", value: "Normal.dotm" },
      ],
    });
  });
});

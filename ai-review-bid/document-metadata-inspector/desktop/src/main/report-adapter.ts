import { createHash } from "node:crypto";

import type {
  ComparisonReportJson,
  DocumentSummary,
  FolderSelection,
  ObservationSummary,
  ReportDocumentJson,
  ReportMatchJson,
  ReportObservationJson,
  ReportTraceKind,
  ResultGroup,
  ScanResult,
  TraceSummary,
} from "../shared/contracts";

const TRACE_KINDS = new Set<ReportTraceKind>([
  "person_trace",
  "organization_trace",
  "software_trace",
  "document_environment_trace",
]);

const TRACE_LABELS: Record<ReportTraceKind, string> = {
  person_trace: "人员身份痕迹",
  organization_trace: "组织信息痕迹",
  software_trace: "软件环境线索",
  document_environment_trace: "文档环境线索",
};

function traceKind(value: string | undefined): ReportTraceKind {
  if (value !== undefined && TRACE_KINDS.has(value as ReportTraceKind)) {
    return value as ReportTraceKind;
  }
  return "document_environment_trace";
}

function displayValue(match: ReportMatchJson): string {
  const raw = match.raw_values?.find(
    (value): value is string => typeof value === "string" && value.trim().length > 0,
  );
  if (raw !== undefined) {
    return raw;
  }
  if (typeof match.normalized_value === "string") {
    return match.normalized_value;
  }
  return JSON.stringify(match.normalized_value);
}

function observationValue(observation: ReportObservationJson): string {
  const raw = observation.raw_value;
  if (typeof raw === "string") {
    return raw;
  }
  if (raw === null || raw === undefined) {
    const normalized = observation.normalized_value;
    if (typeof normalized === "string") {
      return normalized;
    }
    if (normalized === null || normalized === undefined) {
      return "";
    }
    return JSON.stringify(normalized);
  }
  if (typeof raw === "number" || typeof raw === "boolean") {
    return String(raw);
  }
  return JSON.stringify(raw);
}

function observationLabel(observation: ReportObservationJson): string {
  return (observation.raw_name ?? observation.canonical_name ?? "未知字段").trim() || "未知字段";
}

function summarizeObservations(
  observations: ReportObservationJson[] | undefined,
): ObservationSummary[] {
  if (observations === undefined) {
    return [];
  }
  return observations
    .map((observation) => ({
      label: observationLabel(observation),
      value: observationValue(observation),
    }))
    .filter((observation) => observation.value.length > 0);
}

function documentSummary(
  report: ReportDocumentJson,
  relativePath: string,
  id: string,
): DocumentSummary {
  const parserRuns = report.parser_runs ?? [];
  const warningCount =
    (report.warnings?.length ?? 0) +
    parserRuns.reduce((total, run) => total + (run.warnings?.length ?? 0), 0) +
    (report.embedded_documents ?? []).reduce(
      (total, embedded) => total + (embedded.warnings?.length ?? 0),
      0,
    );
  return {
    id,
    name: report.display_name,
    relativePath,
    format: report.identity?.declared_format ?? "unknown",
    family: report.identity?.family ?? "unknown",
    status: report.status,
    observationCount: report.observations?.length ?? 0,
    parserRunCount: parserRuns.length,
    warningCount,
    sizeBytes: report.size_bytes ?? 0,
    sha256Prefix: report.sha256.slice(0, 12),
    parserRuns: parserRuns.map((run, index) => ({
      name: run.parser_name?.trim() || `解析器 ${index + 1}`,
      status: run.status?.trim() || "unknown",
      warningCount: run.warnings?.length ?? 0,
    })),
    observations: summarizeObservations(report.observations),
  };
}

function traceId(match: ReportMatchJson, kind: ReportTraceKind): string {
  return createHash("sha256")
    .update(`${kind}\0${match.canonical_name}\0${displayValue(match)}`, "utf8")
    .digest("hex")
    .slice(0, 16);
}

export function adaptComparisonReport(
  report: ComparisonReportJson,
  selection: FolderSelection,
): ScanResult {
  const selectedByPathHash = new Map(
    selection.groups.flatMap((group) =>
      group.files.map((file) => [file.sourcePathSha256, { file, group }] as const),
    ),
  );
  const reportByPathHash = new Map(
    report.documents.flatMap((document) =>
      document.source_path_sha256 === null || document.source_path_sha256 === undefined
        ? []
        : ([[document.source_path_sha256, document]] as const),
    ),
  );
  const documentGroupIds = new Map<string, string>();
  const bidderGroupIds = new Set(
    selection.groups.filter((group) => group.kind === "bidder").map((group) => group.id),
  );

  const groups: ResultGroup[] = selection.groups.map((group) => {
    const documents = group.files.flatMap((file) => {
      const document = reportByPathHash.get(file.sourcePathSha256);
      if (document === undefined) {
        return [];
      }
      documentGroupIds.set(file.sourcePathSha256, group.id);
      return [documentSummary(document, file.relativePath, file.sourcePathSha256)];
    });
    return { id: group.id, kind: group.kind, name: group.name, documents };
  });

  const traces = report.matches.flatMap((match): TraceSummary[] => {
    const documentIds = [...new Set(match.document_ids ?? [])].filter((documentId) =>
      selectedByPathHash.has(documentId),
    );
    const groupIds = [
      ...new Set(
        documentIds.flatMap((documentId) => {
          const groupId = documentGroupIds.get(documentId);
          return groupId === undefined ? [] : [groupId];
        }),
      ),
    ];
    const bidderIds = groupIds.filter((groupId) => bidderGroupIds.has(groupId));
    if (bidderIds.length < 2) {
      return [];
    }
    const kind = traceKind(match.trace_kind);
    return [
      {
        id: traceId(match, kind),
        kind,
        tone: kind === "person_trace" ? "danger" : "neutral",
        label: TRACE_LABELS[kind],
        value: displayValue(match),
        groupIds: bidderIds,
        documentIds,
        fieldNames: match.field_names ?? [match.canonical_name],
        evidenceCount: match.evidence_count ?? documentIds.length,
      },
    ];
  });

  const reportWarningCount = report.warnings?.length ?? 0;
  const documentWarningCount = groups
    .flatMap((group) => group.documents)
    .reduce((total, document) => total + document.warningCount, 0);

  return {
    rootName: selection.rootName,
    scannedAt: new Date().toISOString(),
    documentCount: report.documents.length,
    completeDocumentCount: report.documents.filter((document) => document.status === "complete")
      .length,
    observationCount: report.documents.reduce(
      (total, document) => total + (document.observations?.length ?? 0),
      0,
    ),
    parserRunCount: report.documents.reduce(
      (total, document) => total + (document.parser_runs?.length ?? 0),
      0,
    ),
    warningCount: reportWarningCount + documentWarningCount,
    bidderCount: selection.bidderCount,
    groups,
    personTraces: traces.filter((trace) => trace.kind === "person_trace"),
    contextTraces: traces.filter((trace) => trace.kind !== "person_trace"),
  };
}

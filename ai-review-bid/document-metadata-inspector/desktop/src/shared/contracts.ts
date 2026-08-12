import type { WindowControlsBridge } from "./window-controls";

export type { WindowControlsBridge, WindowState } from "./window-controls";

export const SUPPORTED_EXTENSIONS = new Set([
  ".pdf",
  ".doc",
  ".docx",
  ".docm",
  ".dot",
  ".dotx",
  ".dotm",
  ".xls",
  ".xlsx",
  ".xlsm",
  ".xlsb",
  ".xlt",
  ".xltx",
  ".xltm",
]);

export interface SelectedDocument {
  id: string;
  sourcePathSha256: string;
  groupId: string;
  name: string;
  relativePath: string;
  extension: string;
  sizeBytes: number;
}

export interface FolderGroup {
  id: string;
  kind: "bidder" | "root-files";
  name: string;
  relativePath: string;
  fileCount: number;
  files: SelectedDocument[];
}

export interface FolderSelection {
  rootName: string;
  bidderCount: number;
  rootFileCount: number;
  supportedFileCount: number;
  ignoredFileCount: number;
  totalSizeBytes: number;
  groups: FolderGroup[];
}

export interface SelectedFolderManifest extends FolderSelection {
  rootPath: string;
}

export type ScanStage =
  | "preparing"
  | "extracting"
  | "comparing"
  | "complete"
  | "stopped"
  | "blocked";

export interface ScanProgress {
  stage: ScanStage;
  message: string;
  percent: number;
}

export interface ReportParserRunJson {
  parser_name?: string;
  status?: string;
  warnings?: unknown[];
}

export interface ReportEmbeddedDocumentJson {
  warnings?: unknown[];
}

export interface ReportObservationJson {
  canonical_name?: string;
  raw_name?: string;
  raw_value?: unknown;
  normalized_value?: unknown;
  value_type?: string;
  source_kind?: string;
  location?: string;
  parser_name?: string;
  status?: string;
}

export interface ReportDocumentJson {
  display_name: string;
  source_path_sha256?: string | null;
  size_bytes?: number;
  sha256: string;
  identity?: {
    declared_format?: string;
    family?: string;
    status?: string;
  };
  status: string;
  observations?: ReportObservationJson[];
  parser_runs?: ReportParserRunJson[];
  warnings?: unknown[];
  embedded_documents?: ReportEmbeddedDocumentJson[];
}

export type ReportTraceKind =
  | "person_trace"
  | "organization_trace"
  | "software_trace"
  | "document_environment_trace";

export interface ReportMatchJson {
  canonical_name: string;
  normalized_value: unknown;
  trace_kind?: string;
  field_names?: string[];
  raw_values?: unknown[];
  evidence_count?: number;
  document_ids?: string[];
}

export interface ComparisonReportJson {
  schema_version: string;
  documents: ReportDocumentJson[];
  matches: ReportMatchJson[];
  warnings?: unknown[];
}

export interface DesktopBundleParserRunJson {
  name: string;
  status: string;
  warning_count: number;
}

export interface DesktopBundleKeyFieldsJson {
  author: string;
  created: string;
  modified: string;
  last_modified_by: string;
  company: string;
  template: string;
}

export interface DesktopBundleDocumentJson {
  source_path_sha256: string;
  display_name: string;
  declared_format: string;
  family: string;
  status: string;
  observation_count: number;
  parser_run_count: number;
  warning_count: number;
  size_bytes: number;
  sha256_prefix: string;
  parser_runs: DesktopBundleParserRunJson[];
  key_fields: DesktopBundleKeyFieldsJson;
}

export interface DesktopBundleTraceJson {
  canonical_name: string;
  normalized_value: unknown;
  trace_kind: ReportTraceKind;
  field_names: string[];
  raw_values: unknown[];
  evidence_count: number;
  document_ids: string[];
}

export interface DesktopBundleSummaryJson {
  schema_version: "1.0";
  document_count: number;
  complete_document_count: number;
  observation_count: number;
  parser_run_count: number;
  warning_count: number;
  documents: DesktopBundleDocumentJson[];
  matches: DesktopBundleTraceJson[];
  warnings: string[];
}

export interface ObservationSummary {
  label: string;
  value: string;
}

export interface DocumentDetail {
  schema_version: "1.0";
  document_id: string;
  observations: ObservationSummary[];
}

export interface DocumentKeyFields {
  author: string;
  created: string;
  modified: string;
  lastModifiedBy: string;
  company: string;
  template: string;
}

export interface DocumentSummary {
  id: string;
  name: string;
  relativePath: string;
  format: string;
  family: string;
  status: string;
  observationCount: number;
  parserRunCount: number;
  warningCount: number;
  sizeBytes: number;
  sha256Prefix: string;
  parserRuns: ParserRunSummary[];
  observations: ObservationSummary[];
  keyFields: DocumentKeyFields;
}

export interface ParserRunSummary {
  name: string;
  status: string;
  warningCount: number;
}

export interface ResultGroup {
  id: string;
  kind: "bidder" | "root-files";
  name: string;
  documents: DocumentSummary[];
}

export type TraceTone = "danger" | "caution";

export interface TraceSummary {
  id: string;
  kind: ReportTraceKind;
  tone: TraceTone;
  label: string;
  value: string;
  groupIds: string[];
  documentIds: string[];
  fieldNames: string[];
  evidenceCount: number;
}

export interface ScanResult {
  rootName: string;
  scannedAt: string;
  documentCount: number;
  completeDocumentCount: number;
  observationCount: number;
  parserRunCount: number;
  warningCount: number;
  bidderCount: number;
  groups: ResultGroup[];
  personTraces: TraceSummary[];
  cautionTraces: TraceSummary[];
}

export interface DocmetaBridge {
  readonly windowControls: WindowControlsBridge;
  selectFolder(): Promise<FolderSelection | null>;
  startScan(): Promise<ScanResult>;
  stopScan(): Promise<boolean>;
  getDocumentDetail(documentId: string): Promise<DocumentDetail>;
  onScanProgress(listener: (progress: ScanProgress) => void): () => void;
}

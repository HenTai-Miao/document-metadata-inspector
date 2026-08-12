import { type ChildProcess, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { lstat, mkdtemp, open, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { StringDecoder } from "node:string_decoder";

import type {
  DesktopBundleSummaryJson,
  DocumentDetail,
  ScanProgress,
  ScanResult,
  SelectedFolderManifest,
} from "../shared/contracts";
import { adaptDesktopBundleSummary } from "./report-adapter";
import { type ResolvedDocmetaCommand, RuntimeIntegrityError } from "./runtime-resolver";

const MAX_PROGRESS_LINE_BYTES = 128 * 1024;
const DEFAULT_TERMINATION_GRACE_MILLISECONDS = 3_000;
const DEFAULT_TERMINATION_FORCE_MILLISECONDS = 1_000;
const STOP_COMPLETION_BUFFER_MILLISECONDS = 2_000;

type ProgressListener = (progress: ScanProgress) => void;

interface ScanServiceOptions {
  temporaryRoot?: string;
  maxRunMilliseconds?: number;
  terminationGraceMilliseconds?: number;
  terminationForceMilliseconds?: number;
  platform?: NodeJS.Platform;
  windowsTreeKiller?: {
    command: string;
    argsPrefix: string[];
  };
  removeTemporaryDirectory?: (path: string) => Promise<void>;
  resolveRuntime: () => ResolvedDocmetaCommand | Promise<ResolvedDocmetaCommand>;
}

interface TerminationPolicy {
  graceMilliseconds: number;
  forceMilliseconds: number;
  platform: NodeJS.Platform;
  windowsTreeKiller: {
    command: string;
    argsPrefix: string[];
  };
}

interface ProcessOutcome {
  code: number | null;
  signal: NodeJS.Signals | null;
  timedOut: boolean;
  treeTerminated: boolean;
}

interface ActiveBundle {
  detailIdentities: ReadonlyMap<string, string>;
  documentIds: ReadonlySet<string>;
  resultDirectory: string;
  temporaryDirectory: string;
}

interface ProcessTerminationController {
  request(child: ChildProcess): Promise<boolean>;
  currentResult(): Promise<boolean>;
  reportFailure(): void;
}

type ScanErrorCode =
  | "already-running"
  | "input-changed"
  | "no-documents"
  | "output-invalid"
  | "process-failed"
  | "process-stop-failed"
  | "process-timeout"
  | "runtime-invalid"
  | "temporary-cleanup-failed";

export class ScanServiceError extends Error {
  readonly code: ScanErrorCode;

  constructor(code: ScanErrorCode, message: string) {
    super(message);
    this.name = "ScanServiceError";
    this.code = code;
  }
}

export class ScanStoppedError extends Error {
  constructor() {
    super("核验已停止");
    this.name = "ScanStoppedError";
  }
}

function progress(stage: ScanProgress["stage"], message: string, percent: number): ScanProgress {
  return { stage, message, percent };
}

function terminationPolicy(options: ScanServiceOptions): TerminationPolicy {
  return {
    graceMilliseconds: Math.max(
      1,
      options.terminationGraceMilliseconds ?? DEFAULT_TERMINATION_GRACE_MILLISECONDS,
    ),
    forceMilliseconds: Math.max(
      1,
      options.terminationForceMilliseconds ?? DEFAULT_TERMINATION_FORCE_MILLISECONDS,
    ),
    platform: options.platform ?? process.platform,
    windowsTreeKiller: options.windowsTreeKiller ?? {
      command: "taskkill",
      argsPrefix: [],
    },
  };
}

function runProcess(
  runtime: ResolvedDocmetaCommand,
  args: string[],
  cwd: string,
  onSpawn: (child: ChildProcess) => boolean,
  maxRunMilliseconds: number | undefined,
  policy: TerminationPolicy,
  termination: ProcessTerminationController,
  onProgressMessage: (completed: number, total: number) => void,
): Promise<ProcessOutcome> {
  return new Promise((resolve, reject) => {
    const child = spawn(runtime.command, [...runtime.argsPrefix, ...args], {
      cwd,
      env: { ...process.env, PYTHONPATH: "", PYTHONHOME: "" },
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
      windowsHide: true,
    });
    let timedOut = false;
    let settled = false;
    let terminationRequested = false;
    let terminationFailureReported = false;
    const beginTermination = (): Promise<boolean> => {
      terminationRequested = true;
      return termination.request(child).then((terminated) => {
        if (!terminated && !terminationFailureReported) {
          terminationFailureReported = true;
          termination.reportFailure();
        }
        return terminated;
      });
    };
    const decoder = new StringDecoder("utf8");
    let progressBuffer = "";
    let discardingOversizedLine = false;
    const consumeProgressLine = (line: string) => {
      if (Buffer.byteLength(line, "utf8") > MAX_PROGRESS_LINE_BYTES) {
        return;
      }
      try {
        const value = JSON.parse(line) as unknown;
        if (
          typeof value === "object" &&
          value !== null &&
          "type" in value &&
          value.type === "progress" &&
          "completed" in value &&
          Number.isSafeInteger(value.completed) &&
          "total" in value &&
          Number.isSafeInteger(value.total) &&
          typeof value.completed === "number" &&
          typeof value.total === "number" &&
          value.completed >= 0 &&
          value.total > 0 &&
          value.completed <= value.total
        ) {
          onProgressMessage(value.completed, value.total);
        }
      } catch {
        // Non-progress diagnostics are deliberately drained and ignored.
      }
    };
    child.stdout?.on("data", (chunk: Buffer) => {
      let decoded = decoder.write(chunk);
      while (decoded.length > 0) {
        const newline = decoded.indexOf("\n");
        if (newline === -1) {
          if (!discardingOversizedLine) {
            progressBuffer += decoded;
            if (Buffer.byteLength(progressBuffer, "utf8") > MAX_PROGRESS_LINE_BYTES) {
              progressBuffer = "";
              discardingOversizedLine = true;
            }
          }
          break;
        }
        if (!discardingOversizedLine) {
          consumeProgressLine(progressBuffer + decoded.slice(0, newline));
        }
        progressBuffer = "";
        discardingOversizedLine = false;
        decoded = decoded.slice(newline + 1);
      }
    });
    child.stderr?.on("data", () => {
      // Always drain diagnostics; batch size must not terminate a useful scan.
    });
    const deadline =
      maxRunMilliseconds === undefined
        ? null
        : setTimeout(() => {
            timedOut = true;
            void beginTermination();
          }, maxRunMilliseconds);
    if (onSpawn(child)) {
      void beginTermination();
    }
    const settleError = (error: Error) => {
      if (!settled) {
        settled = true;
        if (deadline !== null) {
          clearTimeout(deadline);
        }
        reject(error);
      }
    };
    child.once("error", settleError);
    child.once("close", (code, signal) => {
      if (!settled) {
        settled = true;
        if (deadline !== null) {
          clearTimeout(deadline);
        }
        void (async () => {
          const treeTerminated = terminationRequested
            ? await termination.currentResult()
            : policy.platform === "win32"
              ? true
              : await terminateOwnedProcessTree(child, policy);
          resolve({ code, signal, timedOut, treeTerminated });
        })();
      }
    });
  });
}

function waitForClose(child: ChildProcess, milliseconds: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve(true);
  }
  return new Promise((resolveWait) => {
    let settled = false;
    const settle = (closed: boolean) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      child.removeListener("close", onClose);
      resolveWait(closed);
    };
    const onClose = () => settle(true);
    const timer = setTimeout(() => settle(false), milliseconds);
    child.once("close", onClose);
  });
}

function signalUnixProcessGroup(child: ChildProcess, signal: NodeJS.Signals): void {
  if (child.pid === undefined) {
    child.kill(signal);
    return;
  }
  try {
    process.kill(-child.pid, signal);
  } catch {
    child.kill(signal);
  }
}

function unixProcessGroupExists(child: ChildProcess): boolean {
  if (child.pid === undefined) {
    return child.exitCode === null && child.signalCode === null;
  }
  try {
    process.kill(-child.pid, 0);
    return true;
  } catch (error) {
    return !(
      typeof error === "object" &&
      error !== null &&
      "code" in error &&
      error.code === "ESRCH"
    );
  }
}

async function waitForUnixProcessGroupExit(
  child: ChildProcess,
  milliseconds: number,
): Promise<boolean> {
  const deadline = Date.now() + milliseconds;
  while (unixProcessGroupExists(child) && Date.now() < deadline) {
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 25));
  }
  return !unixProcessGroupExists(child);
}

function requestWindowsTreeKill(child: ChildProcess, policy: TerminationPolicy): Promise<boolean> {
  if (child.pid === undefined) {
    return Promise.resolve(false);
  }
  return new Promise((resolveTermination) => {
    let settled = false;
    const settle = (terminated: boolean) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(deadline);
      resolveTermination(terminated);
    };
    const terminator = spawn(
      policy.windowsTreeKiller.command,
      [...policy.windowsTreeKiller.argsPrefix, "/PID", String(child.pid), "/T", "/F"],
      {
        shell: false,
        stdio: "ignore",
        windowsHide: true,
      },
    );
    const deadline = setTimeout(() => {
      terminator.kill("SIGKILL");
      settle(false);
    }, policy.forceMilliseconds);
    terminator.once("error", () => settle(false));
    terminator.once("close", (code) => {
      settle(code === 0);
    });
  });
}

async function terminateWindowsProcessTree(
  child: ChildProcess,
  policy: TerminationPolicy,
): Promise<boolean> {
  const treeKillSucceeded = await requestWindowsTreeKill(child, policy);
  if (!treeKillSucceeded) {
    return false;
  }
  return waitForClose(child, policy.forceMilliseconds);
}

async function terminateOwnedProcessTree(
  child: ChildProcess,
  policy: TerminationPolicy,
): Promise<boolean> {
  if (policy.platform === "win32") {
    if (child.exitCode !== null || child.signalCode !== null) {
      return true;
    }
    return terminateWindowsProcessTree(child, policy);
  }
  if (!unixProcessGroupExists(child)) {
    return true;
  }
  signalUnixProcessGroup(child, "SIGTERM");
  if (await waitForUnixProcessGroupExit(child, policy.graceMilliseconds)) {
    return true;
  }
  signalUnixProcessGroup(child, "SIGKILL");
  return waitForUnixProcessGroupExit(child, policy.forceMilliseconds);
}

async function waitForCompletion(
  completion: Promise<boolean>,
  milliseconds: number,
): Promise<boolean | null> {
  return new Promise((resolveWait) => {
    let settled = false;
    const settle = (cleanupSucceeded: boolean | null) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolveWait(cleanupSucceeded);
    };
    const timer = setTimeout(() => settle(null), milliseconds);
    void completion.then(
      (cleanupSucceeded) => settle(cleanupSucceeded),
      () => settle(false),
    );
  });
}

const DOCUMENT_ID_PATTERN = /^[0-9a-f]{64}$/u;
const TRACE_KINDS = new Set([
  "person_trace",
  "organization_trace",
  "software_trace",
  "document_environment_trace",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function isStringRecord(value: unknown, keys: readonly string[]): value is Record<string, string> {
  return (
    isRecord(value) &&
    hasExactKeys(value, keys) &&
    keys.every((key) => typeof value[key] === "string")
  );
}

function isBundleDocument(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "source_path_sha256",
      "display_name",
      "declared_format",
      "family",
      "status",
      "observation_count",
      "parser_run_count",
      "warning_count",
      "size_bytes",
      "sha256_prefix",
      "parser_runs",
      "key_fields",
    ]) ||
    typeof value.source_path_sha256 !== "string" ||
    !DOCUMENT_ID_PATTERN.test(value.source_path_sha256) ||
    typeof value.display_name !== "string" ||
    typeof value.declared_format !== "string" ||
    typeof value.family !== "string" ||
    typeof value.status !== "string" ||
    !isCount(value.observation_count) ||
    !isCount(value.parser_run_count) ||
    !isCount(value.warning_count) ||
    !isCount(value.size_bytes) ||
    typeof value.sha256_prefix !== "string" ||
    !Array.isArray(value.parser_runs) ||
    !value.parser_runs.every(
      (run) =>
        isRecord(run) &&
        hasExactKeys(run, ["name", "status", "warning_count"]) &&
        typeof run.name === "string" &&
        typeof run.status === "string" &&
        isCount(run.warning_count),
    )
  ) {
    return false;
  }
  return isStringRecord(value.key_fields, [
    "author",
    "created",
    "modified",
    "last_modified_by",
    "company",
    "template",
  ]);
}

function isBundleTrace(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "canonical_name",
      "normalized_value",
      "trace_kind",
      "field_names",
      "raw_values",
      "evidence_count",
      "document_ids",
    ]) &&
    typeof value.canonical_name === "string" &&
    typeof value.trace_kind === "string" &&
    TRACE_KINDS.has(value.trace_kind) &&
    Array.isArray(value.field_names) &&
    value.field_names.every((item) => typeof item === "string") &&
    Array.isArray(value.raw_values) &&
    isCount(value.evidence_count) &&
    Array.isArray(value.document_ids) &&
    value.document_ids.every((item) => typeof item === "string" && DOCUMENT_ID_PATTERN.test(item))
  );
}

function parseBundleSummary(raw: string): DesktopBundleSummaryJson {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new ScanServiceError("output-invalid", "离线核验组件返回的结果摘要无法读取");
  }
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "schema_version",
      "document_count",
      "complete_document_count",
      "observation_count",
      "parser_run_count",
      "warning_count",
      "documents",
      "matches",
      "warnings",
    ]) ||
    value.schema_version !== "1.0" ||
    !isCount(value.document_count) ||
    !isCount(value.complete_document_count) ||
    !isCount(value.observation_count) ||
    !isCount(value.parser_run_count) ||
    !isCount(value.warning_count) ||
    !Array.isArray(value.documents) ||
    !value.documents.every(isBundleDocument) ||
    !Array.isArray(value.matches) ||
    !value.matches.every(isBundleTrace) ||
    !Array.isArray(value.warnings) ||
    !value.warnings.every((warning) => typeof warning === "string") ||
    value.document_count !== value.documents.length ||
    value.complete_document_count > value.document_count
  ) {
    throw new ScanServiceError("output-invalid", "离线核验组件返回的结果摘要格式无效");
  }
  return value as unknown as DesktopBundleSummaryJson;
}

function parseDocumentDetail(raw: string, documentId: string): DocumentDetail {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new ScanServiceError("output-invalid", "文档详情无法安全读取");
  }
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["schema_version", "document_id", "observations"]) ||
    value.schema_version !== "1.0" ||
    value.document_id !== documentId ||
    !Array.isArray(value.observations) ||
    !value.observations.every(
      (observation) =>
        isRecord(observation) &&
        hasExactKeys(observation, ["label", "value"]) &&
        typeof observation.label === "string" &&
        typeof observation.value === "string",
    )
  ) {
    throw new ScanServiceError("output-invalid", "文档详情格式无效");
  }
  return value as unknown as DocumentDetail;
}

function stableFileIdentity(metadata: Awaited<ReturnType<typeof lstat>>): string {
  return [metadata.dev, metadata.ino, metadata.size, metadata.mtimeMs, metadata.ctimeMs].join(":");
}

function crossViewFileIdentity(metadata: Awaited<ReturnType<typeof lstat>>): string {
  return [metadata.dev, metadata.ino, metadata.size, metadata.mtimeMs].join(":");
}

async function readStableRegularFile(
  path: string,
  label: string,
  expectedIdentity?: string,
): Promise<string> {
  try {
    const pathBefore = await lstat(path);
    if (!pathBefore.isFile() || pathBefore.isSymbolicLink()) {
      throw new Error("unsafe file");
    }
    if (expectedIdentity !== undefined && stableFileIdentity(pathBefore) !== expectedIdentity) {
      throw new Error("replaced file");
    }
    const flags = fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0);
    const handle = await open(path, flags);
    try {
      const descriptorBefore = await handle.stat();
      if (
        !descriptorBefore.isFile() ||
        crossViewFileIdentity(pathBefore) !== crossViewFileIdentity(descriptorBefore)
      ) {
        throw new Error("changed file");
      }
      const raw = await handle.readFile("utf8");
      const descriptorAfter = await handle.stat();
      const pathAfter = await lstat(path);
      if (
        !pathAfter.isFile() ||
        pathAfter.isSymbolicLink() ||
        stableFileIdentity(pathBefore) !== stableFileIdentity(pathAfter) ||
        stableFileIdentity(descriptorBefore) !== stableFileIdentity(descriptorAfter) ||
        crossViewFileIdentity(descriptorAfter) !== crossViewFileIdentity(pathAfter)
      ) {
        throw new Error("changed file");
      }
      return raw;
    } finally {
      await handle.close();
    }
  } catch {
    throw new ScanServiceError("output-invalid", label);
  }
}

async function captureDetailIdentities(
  resultDirectory: string,
  documentIds: readonly string[],
): Promise<ReadonlyMap<string, string>> {
  try {
    const detailsDirectory = join(resultDirectory, "details");
    const directoryMetadata = await lstat(detailsDirectory);
    if (!directoryMetadata.isDirectory() || directoryMetadata.isSymbolicLink()) {
      throw new ScanServiceError("output-invalid", "离线核验组件没有生成安全的文档详情");
    }
    const identities = new Map<string, string>();
    for (const documentId of documentIds) {
      const metadata = await lstat(join(detailsDirectory, `${documentId}.json`));
      if (!metadata.isFile() || metadata.isSymbolicLink()) {
        throw new ScanServiceError("output-invalid", "离线核验组件没有生成安全的文档详情");
      }
      identities.set(documentId, stableFileIdentity(metadata));
    }
    return identities;
  } catch (error) {
    if (error instanceof ScanServiceError) {
      throw error;
    }
    throw new ScanServiceError("output-invalid", "离线核验组件没有生成安全的文档详情");
  }
}

interface SelectedInputDocument {
  path: string;
  source_path_sha256: string;
  group_id: string;
}

function* selectedInputDocuments(
  selection: SelectedFolderManifest,
): Generator<SelectedInputDocument> {
  const rootPath = resolve(selection.rootPath);
  for (const group of selection.groups) {
    for (const file of group.files) {
      const absolutePath = resolve(rootPath, file.relativePath);
      const relativeToRoot = relative(rootPath, absolutePath);
      if (
        relativeToRoot.length === 0 ||
        relativeToRoot === ".." ||
        relativeToRoot.startsWith(`..${sep}`) ||
        isAbsolute(relativeToRoot)
      ) {
        throw new ScanServiceError("input-changed", "所选文件清单无效，请重新选择目录");
      }
      const sourcePathSha256 = createHash("sha256").update(absolutePath, "utf8").digest("hex");
      if (sourcePathSha256 !== file.sourcePathSha256 || file.groupId !== group.id) {
        throw new ScanServiceError("input-changed", "所选文件清单无效，请重新选择目录");
      }
      yield {
        path: absolutePath,
        source_path_sha256: file.sourcePathSha256,
        group_id: group.id,
      };
    }
  }
}

async function writeInputManifest(
  path: string,
  selection: SelectedFolderManifest,
): Promise<number> {
  const handle = await open(path, "wx", 0o600);
  let documentCount = 0;
  try {
    await handle.writeFile(`${JSON.stringify({ schema_version: "2.0", type: "manifest" })}\n`);
    for (const document of selectedInputDocuments(selection)) {
      await handle.writeFile(`${JSON.stringify({ type: "document", ...document })}\n`);
      documentCount += 1;
    }
    await handle.sync();
  } finally {
    await handle.close();
  }
  return documentCount;
}

function validateReportBoundary(
  report: DesktopBundleSummaryJson,
  selection: SelectedFolderManifest,
): void {
  const expected = new Set(
    selection.groups.flatMap((group) => group.files.map((file) => file.sourcePathSha256)),
  );
  const actual = report.documents.map((document) => document.source_path_sha256);
  if (
    actual.length !== expected.size ||
    actual.some((documentId) => typeof documentId !== "string") ||
    new Set(actual).size !== actual.length ||
    actual.some((documentId) => typeof documentId === "string" && !expected.has(documentId))
  ) {
    throw new ScanServiceError(
      "input-changed",
      "所选目录内容在核验期间发生变化，请重新选择目录后再试",
    );
  }
}

export class ScanService {
  readonly #options: ScanServiceOptions;
  #activeBundle: ActiveBundle | null = null;
  #activeRun: symbol | null = null;
  #activeChild: ChildProcess | null = null;
  #activeFinished: Promise<boolean> | null = null;
  #finishActive: ((cleanupSucceeded: boolean) => void) | null = null;
  #activeTermination: Promise<boolean> | null = null;
  #terminationFailed = false;
  #blockedError: ScanServiceError | null = null;
  #stopRequested = false;

  constructor(options: ScanServiceOptions) {
    this.#options = options;
  }

  get isRunning(): boolean {
    return this.#activeRun !== null;
  }

  #block(error: ScanServiceError): void {
    if (
      this.#blockedError === null ||
      (error.code === "process-stop-failed" && this.#blockedError.code !== "process-stop-failed")
    ) {
      this.#blockedError = error;
    }
  }

  #recordTerminationResult(terminated: boolean): void {
    this.#terminationFailed = !terminated;
    if (terminated) {
      if (this.#blockedError?.code === "process-stop-failed") {
        this.#blockedError = null;
      }
      return;
    }
    this.#block(
      new ScanServiceError("process-stop-failed", "核验进程未能安全停止，请关闭程序后重试"),
    );
  }

  async #requestTermination(child: ChildProcess, policy: TerminationPolicy): Promise<boolean> {
    this.#activeTermination ??= terminateOwnedProcessTree(child, policy);
    const activeTermination = this.#activeTermination;
    const terminated = await activeTermination;
    this.#recordTerminationResult(terminated);
    if (!terminated && this.#activeTermination === activeTermination) {
      this.#activeTermination = null;
    }
    return terminated;
  }

  async #currentTerminationResult(): Promise<boolean> {
    if (this.#activeTermination !== null) {
      this.#recordTerminationResult(await this.#activeTermination);
    }
    return !this.#terminationFailed;
  }

  async start(
    selection: SelectedFolderManifest,
    onProgress: ProgressListener,
  ): Promise<ScanResult> {
    if (this.#blockedError !== null) {
      throw this.#blockedError;
    }
    if (this.#activeRun !== null) {
      throw new ScanServiceError("already-running", "已有核验任务正在运行");
    }
    const run = Symbol("scan-run");
    this.#activeRun = run;
    this.#activeFinished = new Promise((resolveFinished) => {
      this.#finishActive = resolveFinished;
    });
    this.#terminationFailed = false;
    this.#stopRequested = false;
    let temporaryDirectory: string | null = null;
    let completedResult: ScanResult | null = null;
    let pendingError: Error | null = null;
    let cleanupError: ScanServiceError | null = null;

    try {
      if (this.#activeBundle !== null) {
        await this.#discardActiveBundle();
      }
      onProgress(progress("preparing", "正在确认投标人目录和文件边界", 8));
      if (this.#stopRequested) {
        throw new ScanStoppedError();
      }

      const temporaryRoot = this.#options.temporaryRoot ?? tmpdir();
      temporaryDirectory = await mkdtemp(join(temporaryRoot, "docmeta-scan-"));
      const resultDirectory = join(temporaryDirectory, "result");
      const inputManifestPath = join(temporaryDirectory, "input-manifest.jsonl");
      const documentCount = await writeInputManifest(inputManifestPath, selection);
      if (documentCount === 0) {
        throw new ScanServiceError(
          "no-documents",
          "所选目录中没有可核验的 PDF、Word 或 Excel 文件",
        );
      }
      const runtime = await this.#options.resolveRuntime();
      const policy = terminationPolicy(this.#options);
      onProgress(progress("extracting", "三个离线解析引擎正在提取元数据", 34));
      let lastCompleted = 0;
      const outcome = await runProcess(
        runtime,
        [
          "desktop-compare",
          "--output",
          resultDirectory,
          "--max-concurrency",
          "4",
          inputManifestPath,
        ],
        runtime.workingDirectory,
        (child) => {
          this.#activeChild = child;
          return this.#stopRequested;
        },
        this.#options.maxRunMilliseconds,
        policy,
        {
          request: (child) => this.#requestTermination(child, policy),
          currentResult: () => this.#currentTerminationResult(),
          reportFailure: () => {
            try {
              onProgress(progress("blocked", "核验进程未能安全停止，请关闭程序后重试", 34));
            } catch {
              // Termination safety must not depend on a renderer listener.
            }
          },
        },
        (completed, total) => {
          if (completed <= lastCompleted) {
            return;
          }
          lastCompleted = completed;
          const percent = Math.min(80, 20 + Math.floor((completed / total) * 60));
          try {
            onProgress(progress("extracting", `已完成 ${completed}/${total} 个文档`, percent));
          } catch {
            // Child-process drainage and scan safety do not depend on renderer state.
          }
        },
      );
      this.#activeChild = null;
      if (this.#stopRequested && this.#activeTermination !== null) {
        this.#recordTerminationResult(await this.#activeTermination);
      }
      const requestedStopTerminated = !this.#terminationFailed;
      if (!outcome.treeTerminated || !requestedStopTerminated) {
        const error = new ScanServiceError(
          "process-stop-failed",
          "核验进程未能安全停止，请关闭程序后重试",
        );
        this.#block(error);
        throw error;
      }
      if (this.#stopRequested) {
        throw new ScanStoppedError();
      }
      if (outcome.timedOut) {
        throw new ScanServiceError("process-timeout", "核验时间超过安全时限，已自动停止");
      }
      if (outcome.code !== 0 && outcome.code !== 3) {
        throw new ScanServiceError(
          "process-failed",
          "离线核验组件运行失败，请确认文件可读取后重试",
        );
      }

      onProgress(progress("comparing", "正在核对不同投标人之间的身份痕迹", 82));
      const resultMetadata = await lstat(resultDirectory);
      if (!resultMetadata.isDirectory() || resultMetadata.isSymbolicLink()) {
        throw new ScanServiceError("output-invalid", "离线核验组件没有生成安全的结果目录");
      }
      const report = parseBundleSummary(
        await readStableRegularFile(
          join(resultDirectory, "summary.json"),
          "离线核验组件没有生成可用的结果摘要",
        ),
      );
      validateReportBoundary(report, selection);
      const result = adaptDesktopBundleSummary(report, selection);
      const documentIds = report.documents.map((document) => document.source_path_sha256);
      this.#activeBundle = {
        detailIdentities: await captureDetailIdentities(resultDirectory, documentIds),
        documentIds: new Set(documentIds),
        resultDirectory,
        temporaryDirectory,
      };
      temporaryDirectory = null;
      onProgress(progress("complete", "核验完成", 100));
      completedResult = result;
    } catch (error) {
      if (error instanceof ScanServiceError && error.code === "process-stop-failed") {
        pendingError = error;
      } else if (error instanceof ScanStoppedError || this.#stopRequested) {
        onProgress(progress("stopped", "核验已停止，可以重新开始", 0));
        pendingError = new ScanStoppedError();
      } else if (error instanceof ScanServiceError) {
        pendingError = error;
      } else if (error instanceof RuntimeIntegrityError) {
        pendingError = new ScanServiceError("runtime-invalid", error.message);
      } else {
        pendingError = new ScanServiceError(
          "process-failed",
          "离线核验组件运行失败，请确认文件可读取后重试",
        );
      }
    } finally {
      try {
        if (temporaryDirectory !== null) {
          try {
            await (this.#options.removeTemporaryDirectory ?? removeTemporaryDirectory)(
              temporaryDirectory,
            );
          } catch {
            cleanupError = new ScanServiceError(
              "temporary-cleanup-failed",
              "临时文件未能安全清理，请关闭程序后重试",
            );
            this.#block(cleanupError);
          }
        }
      } finally {
        if (this.#activeRun === run) {
          const finishActive = this.#finishActive;
          this.#activeRun = null;
          this.#activeChild = null;
          this.#activeFinished = null;
          this.#finishActive = null;
          this.#activeTermination = null;
          this.#terminationFailed = false;
          this.#stopRequested = false;
          finishActive?.(cleanupError === null);
        }
      }
    }
    if (cleanupError !== null) {
      throw cleanupError;
    }
    if (pendingError !== null) {
      throw pendingError;
    }
    if (completedResult === null) {
      throw new ScanServiceError("output-invalid", "离线核验组件没有生成可用结果");
    }
    return completedResult;
  }

  async documentDetail(documentId: string): Promise<DocumentDetail> {
    const bundle = this.#activeBundle;
    if (
      bundle === null ||
      !DOCUMENT_ID_PATTERN.test(documentId) ||
      !bundle.documentIds.has(documentId)
    ) {
      throw new ScanServiceError("output-invalid", "文档详情请求无效或结果已经失效");
    }
    try {
      const detailsDirectory = join(bundle.resultDirectory, "details");
      const directoryMetadata = await lstat(detailsDirectory);
      if (!directoryMetadata.isDirectory() || directoryMetadata.isSymbolicLink()) {
        throw new Error("unsafe detail directory");
      }
      return parseDocumentDetail(
        await readStableRegularFile(
          join(detailsDirectory, `${documentId}.json`),
          "文档详情无法安全读取",
          bundle.detailIdentities.get(documentId),
        ),
        documentId,
      );
    } catch (error) {
      if (error instanceof ScanServiceError) {
        throw error;
      }
      throw new ScanServiceError("output-invalid", "文档详情无法安全读取");
    }
  }

  async discardResult(): Promise<void> {
    if (this.#activeRun !== null) {
      throw new ScanServiceError("already-running", "已有核验任务正在运行");
    }
    await this.#discardActiveBundle();
  }

  async #discardActiveBundle(): Promise<void> {
    const bundle = this.#activeBundle;
    if (bundle === null) {
      return;
    }
    try {
      await (this.#options.removeTemporaryDirectory ?? removeTemporaryDirectory)(
        bundle.temporaryDirectory,
      );
      this.#activeBundle = null;
    } catch {
      const error = new ScanServiceError(
        "temporary-cleanup-failed",
        "临时文件未能安全清理，请关闭程序后重试",
      );
      this.#block(error);
      throw error;
    }
  }

  async dispose(): Promise<void> {
    if (this.#activeRun !== null) {
      await this.stop();
    }
    await this.discardResult();
  }

  async stop(): Promise<boolean> {
    const activeFinished = this.#activeFinished;
    if (this.#activeRun === null || activeFinished === null) {
      if (this.#blockedError !== null) {
        throw this.#blockedError;
      }
      return false;
    }
    this.#stopRequested = true;
    const policy = terminationPolicy(this.#options);
    let terminated = true;
    if (this.#activeChild !== null) {
      terminated = await this.#requestTermination(this.#activeChild, policy);
      if (!terminated) {
        throw this.#blockedError;
      }
    }
    const cleanupSucceeded = await waitForCompletion(
      activeFinished,
      policy.graceMilliseconds + policy.forceMilliseconds * 2 + STOP_COMPLETION_BUFFER_MILLISECONDS,
    );
    if (cleanupSucceeded === null) {
      const error = new ScanServiceError(
        "process-stop-failed",
        "核验进程未能安全停止，请关闭程序后重试",
      );
      this.#block(error);
      throw this.#blockedError ?? error;
    }
    if (!cleanupSucceeded) {
      throw (
        this.#blockedError ??
        new ScanServiceError("temporary-cleanup-failed", "临时文件未能安全清理，请关闭程序后重试")
      );
    }
    return true;
  }
}

async function removeTemporaryDirectory(path: string): Promise<void> {
  await rm(path, { recursive: true, force: true });
}

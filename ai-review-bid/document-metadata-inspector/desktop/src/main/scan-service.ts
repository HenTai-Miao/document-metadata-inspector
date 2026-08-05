import { type ChildProcess, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { lstat, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join, relative, resolve, sep } from "node:path";

import type {
  ComparisonReportJson,
  ScanProgress,
  ScanResult,
  SelectedFolderManifest,
} from "../shared/contracts";
import { adaptComparisonReport } from "./report-adapter";
import { type ResolvedDocmetaCommand, RuntimeIntegrityError } from "./runtime-resolver";

const MAX_REPORT_BYTES = 128 * 1024 * 1024;
const MAX_PROCESS_MESSAGE_BYTES = 1024 * 1024;
const DEFAULT_MAX_RUN_MILLISECONDS = 30 * 60 * 1_000;
const MAX_INPUT_MANIFEST_BYTES = 16 * 1024 * 1024;
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
  outputLimitExceeded: boolean;
  timedOut: boolean;
  treeTerminated: boolean;
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
  | "process-output-limit"
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
  maxRunMilliseconds: number,
  policy: TerminationPolicy,
  termination: ProcessTerminationController,
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
    let capturedBytes = 0;
    let outputLimitExceeded = false;
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
    const terminateForOutputLimit = () => {
      if (outputLimitExceeded) {
        return;
      }
      outputLimitExceeded = true;
      void beginTermination();
    };
    const capture = (chunk: Buffer) => {
      capturedBytes += chunk.byteLength;
      if (capturedBytes > MAX_PROCESS_MESSAGE_BYTES) {
        terminateForOutputLimit();
      }
    };
    child.stdout?.on("data", capture);
    child.stderr?.on("data", capture);
    const deadline = setTimeout(() => {
      timedOut = true;
      void beginTermination();
    }, maxRunMilliseconds);
    if (onSpawn(child)) {
      void beginTermination();
    }
    const settleError = (error: Error) => {
      if (!settled) {
        settled = true;
        clearTimeout(deadline);
        reject(error);
      }
    };
    child.once("error", settleError);
    child.once("close", (code, signal) => {
      if (!settled) {
        settled = true;
        clearTimeout(deadline);
        void (async () => {
          const treeTerminated = terminationRequested
            ? await termination.currentResult()
            : policy.platform === "win32"
              ? true
              : await terminateOwnedProcessTree(child, policy);
          resolve({ code, signal, outputLimitExceeded, timedOut, treeTerminated });
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

function parseComparisonReport(raw: string): ComparisonReportJson {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new ScanServiceError("output-invalid", "离线核验组件返回的报告无法读取");
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    !("documents" in parsed) ||
    !("matches" in parsed) ||
    !Array.isArray(parsed.documents) ||
    !Array.isArray(parsed.matches)
  ) {
    throw new ScanServiceError("output-invalid", "离线核验组件返回的报告格式无效");
  }
  return parsed as ComparisonReportJson;
}

interface SelectedInputDocument {
  path: string;
  source_path_sha256: string;
  group_id: string;
}

function selectedInputDocuments(selection: SelectedFolderManifest): SelectedInputDocument[] {
  const rootPath = resolve(selection.rootPath);
  return selection.groups.flatMap((group) =>
    group.files.map((file) => {
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
      return {
        path: absolutePath,
        source_path_sha256: file.sourcePathSha256,
        group_id: group.id,
      };
    }),
  );
}

async function writeInputManifest(path: string, documents: SelectedInputDocument[]): Promise<void> {
  const serialized = JSON.stringify({ schema_version: "1.0", documents });
  if (Buffer.byteLength(serialized, "utf8") > MAX_INPUT_MANIFEST_BYTES) {
    throw new ScanServiceError("input-changed", "所选文件清单超过安全大小上限");
  }
  await writeFile(path, serialized, { encoding: "utf8", flag: "wx", mode: 0o600 });
}

function validateReportBoundary(
  report: ComparisonReportJson,
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
      onProgress(progress("preparing", "正在确认投标人目录和文件边界", 8));
      const inputDocuments = selectedInputDocuments(selection);
      if (this.#stopRequested) {
        throw new ScanStoppedError();
      }
      if (inputDocuments.length === 0) {
        throw new ScanServiceError(
          "no-documents",
          "所选目录中没有可核验的 PDF、Word 或 Excel 文件",
        );
      }

      const temporaryRoot = this.#options.temporaryRoot ?? tmpdir();
      temporaryDirectory = await mkdtemp(join(temporaryRoot, "docmeta-scan-"));
      const outputPath = join(temporaryDirectory, "comparison.json");
      const inputManifestPath = join(temporaryDirectory, "input-manifest.json");
      await writeInputManifest(inputManifestPath, inputDocuments);
      const runtime = await this.#options.resolveRuntime();
      const policy = terminationPolicy(this.#options);
      onProgress(progress("extracting", "三个离线解析引擎正在提取元数据", 34));
      const outcome = await runProcess(
        runtime,
        ["compare", "--input-manifest", "--json", outputPath, inputManifestPath],
        runtime.workingDirectory,
        (child) => {
          this.#activeChild = child;
          return this.#stopRequested;
        },
        this.#options.maxRunMilliseconds ?? DEFAULT_MAX_RUN_MILLISECONDS,
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
      if (outcome.outputLimitExceeded) {
        throw new ScanServiceError("process-output-limit", "离线核验组件输出异常，已终止本次核验");
      }
      if (outcome.code !== 0 && outcome.code !== 3) {
        throw new ScanServiceError(
          "process-failed",
          "离线核验组件运行失败，请确认文件可读取后重试",
        );
      }

      onProgress(progress("comparing", "正在核对不同投标人之间的身份痕迹", 82));
      const metadata = await lstat(outputPath);
      if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size > MAX_REPORT_BYTES) {
        throw new ScanServiceError("output-invalid", "离线核验报告缺失或超过安全大小上限");
      }
      const report = parseComparisonReport(await readFile(outputPath, "utf8"));
      validateReportBoundary(report, selection);
      const result = adaptComparisonReport(report, selection);
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

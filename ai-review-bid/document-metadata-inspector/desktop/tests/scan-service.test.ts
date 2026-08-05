import { mkdir, mkdtemp, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, test } from "vitest";

import { discoverFolder } from "../src/main/folder-discovery";
import { RuntimeIntegrityError } from "../src/main/runtime-resolver";
import { ScanService, ScanStoppedError } from "../src/main/scan-service";

const temporaryDirectories: string[] = [];
const testDirectory = dirname(fileURLToPath(import.meta.url));
const fakeDocmeta = join(testDirectory, "fixtures", "fake-docmeta.mjs");
const stubbornTree = join(testDirectory, "fixtures", "stubborn-tree.mjs");
const hangingTreeKiller = join(testDirectory, "fixtures", "hanging-tree-killer.mjs");

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

async function scanFixture(delayMilliseconds: number, maxRunMilliseconds?: number) {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "docmeta-service-test-"));
  temporaryDirectories.push(temporaryRoot);
  const sourceRoot = join(temporaryRoot, "4-投标文件");
  await mkdir(join(sourceRoot, "投标人甲"), { recursive: true });
  await writeFile(join(sourceRoot, "投标人甲", "投标文件.pdf"), "public test fixture");
  const selection = await discoverFolder(sourceRoot);
  const selectedFile = selection.groups[0]?.files[0];
  if (selectedFile === undefined) {
    throw new Error("fixture discovery failed");
  }
  const reportPath = join(temporaryRoot, "source-report.json");
  await writeFile(
    reportPath,
    JSON.stringify({
      schema_version: "1.0",
      warnings: [],
      matches: [],
      documents: [
        {
          display_name: selectedFile.name,
          source_path_sha256: selectedFile.sourcePathSha256,
          size_bytes: selectedFile.sizeBytes,
          sha256: "0123456789abcdef",
          identity: { declared_format: "pdf", family: "pdf", status: "confirmed" },
          status: "complete",
          observations: [{ canonical_name: "author" }],
          parser_runs: [
            { parser_name: "native-pdf", status: "succeeded", warnings: [] },
            { parser_name: "apache-tika", status: "succeeded", warnings: [] },
            { parser_name: "exiftool", status: "succeeded", warnings: [] },
          ],
          warnings: [],
        },
      ],
    }),
    "utf8",
  );
  const scanTemporaryRoot = join(temporaryRoot, "scan-temporary");
  const argumentLogPath = join(temporaryRoot, "arguments.json");
  await mkdir(scanTemporaryRoot);
  let currentDelayMilliseconds = delayMilliseconds;
  const service = new ScanService({
    temporaryRoot: scanTemporaryRoot,
    maxRunMilliseconds,
    resolveRuntime: () => ({
      command: process.execPath,
      argsPrefix: [fakeDocmeta, reportPath, String(currentDelayMilliseconds), argumentLogPath],
      source: "test",
      workingDirectory: join(testDirectory, "..", ".."),
    }),
  });
  return {
    scanTemporaryRoot,
    argumentLogPath,
    service,
    selection,
    reportPath,
    sourceRoot,
    setDelay(milliseconds: number) {
      currentDelayMilliseconds = milliseconds;
    },
  };
}

async function forceKillRecordedProcess(pidPath: string): Promise<void> {
  let pid: number;
  try {
    pid = Number.parseInt(await readFile(pidPath, "utf8"), 10);
  } catch {
    return;
  }
  if (!Number.isInteger(pid) || pid <= 0) {
    return;
  }
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    // The normal path is that ScanService already terminated this owned process.
  }
}

async function bestEffortStop(service: ScanService): Promise<void> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      if (await service.stop()) {
        return;
      }
    } catch {
      // A simulated Windows tree-killer failure is expected on the first attempt.
    }
  }
}

describe("ScanService", () => {
  test("runs a real child process, adapts its report, and cleans temporary output", async () => {
    // Reading the CLI summary instead of the authoritative report would lose evidence counts.
    const { argumentLogPath, scanTemporaryRoot, selection, service } = await scanFixture(10);
    const stages: string[] = [];

    const result = await service.start(selection, (progress) => stages.push(progress.stage));

    expect(result).toMatchObject({
      documentCount: 1,
      completeDocumentCount: 1,
      observationCount: 1,
      parserRunCount: 3,
    });
    expect(stages).toEqual(["preparing", "extracting", "comparing", "complete"]);
    expect(await readdir(scanTemporaryRoot)).toEqual([]);
    const invocation = JSON.parse(await readFile(argumentLogPath, "utf8")) as {
      cliArguments: string[];
      inputManifest: {
        documents: Array<{ group_id: string; path: string; source_path_sha256: string }>;
      };
    };
    expect(invocation.cliArguments).toContain("--input-manifest");
    expect(invocation.cliArguments).not.toContain(selection.rootPath);
    expect(invocation.inputManifest.documents).toEqual([
      {
        group_id: selection.groups[0]?.id,
        path: join(selection.rootPath, "投标人甲", "投标文件.pdf"),
        source_path_sha256: selection.groups[0]?.files[0]?.sourcePathSha256,
      },
    ]);
  });

  test("rejects concurrent scans and stop terminates only the active child", async () => {
    // Starting twice could overwrite state; stopping must not target unrelated processes.
    const { selection, service, setDelay } = await scanFixture(5_000);
    const running = service.start(selection, () => undefined);

    await expect(service.start(selection, () => undefined)).rejects.toThrow("已有核验任务正在运行");
    const stoppedRun = expect(running).rejects.toBeInstanceOf(ScanStoppedError);
    await expect(service.stop()).resolves.toBe(true);
    await stoppedRun;
    setDelay(10);
    await expect(service.start(selection, () => undefined)).resolves.toMatchObject({
      documentCount: 1,
    });
    await expect(service.stop()).resolves.toBe(false);
  });

  test("enforces a wall-clock deadline and remains restart-safe", async () => {
    const { selection, service, setDelay } = await scanFixture(5_000, 40);

    await expect(service.start(selection, () => undefined)).rejects.toThrow("超过安全时限");
    setDelay(10);
    await expect(service.start(selection, () => undefined)).resolves.toMatchObject({
      documentCount: 1,
    });
  });

  test("does not expose raw subprocess errors or local paths", async () => {
    const { selection, reportPath, service } = await scanFixture(10);
    await rm(reportPath);

    const failure = service.start(selection, () => undefined);

    await expect(failure).rejects.toThrow("离线核验组件运行失败");
    await expect(failure).rejects.not.toThrow(reportPath);
  });

  test("preserves the safe reinstall message for a damaged packaged runtime", async () => {
    const { selection, scanTemporaryRoot } = await scanFixture(10);
    const service = new ScanService({
      temporaryRoot: scanTemporaryRoot,
      resolveRuntime: () => {
        throw new RuntimeIntegrityError();
      },
    });

    await expect(service.start(selection, () => undefined)).rejects.toThrow("请重新安装完整程序");
  });

  test.skipIf(process.platform === "win32")(
    "force-kills a signal-resistant descendant before stop resolves",
    async () => {
      const { selection, scanTemporaryRoot } = await scanFixture(10);
      const descendantPidPath = join(dirname(scanTemporaryRoot), "descendant.pid");
      const rootPidPath = join(dirname(scanTemporaryRoot), "root.pid");
      const service = new ScanService({
        temporaryRoot: scanTemporaryRoot,
        terminationGraceMilliseconds: 50,
        terminationForceMilliseconds: 500,
        resolveRuntime: () => ({
          command: process.execPath,
          argsPrefix: [
            stubbornTree,
            "--descendant-pid",
            descendantPidPath,
            "--root-pid",
            rootPidPath,
          ],
          source: "test",
          workingDirectory: join(testDirectory, "..", ".."),
        }),
      });
      const running = service.start(selection, () => undefined);
      let descendantPid: number | undefined;
      try {
        for (let attempt = 0; attempt < 100; attempt += 1) {
          try {
            descendantPid = Number.parseInt(await readFile(descendantPidPath, "utf8"), 10);
            break;
          } catch {
            await new Promise((resolveDelay) => setTimeout(resolveDelay, 10));
          }
        }
        expect(descendantPid).toBeTypeOf("number");
        const stoppedRun = expect(running).rejects.toBeInstanceOf(ScanStoppedError);

        await expect(service.stop()).resolves.toBe(true);
        await stoppedRun;
        expect(() => process.kill(descendantPid ?? 0, 0)).toThrow();
      } finally {
        if (descendantPid !== undefined) {
          try {
            process.kill(descendantPid, "SIGKILL");
          } catch {
            // The expected path: the owned process group is already empty.
          }
        }
        await service.stop().catch(() => false);
        await forceKillRecordedProcess(rootPidPath);
        await forceKillRecordedProcess(descendantPidPath);
      }
    },
  );

  test("bounds a hung Windows tree killer and blocks unsafe restart", async () => {
    const { selection, scanTemporaryRoot } = await scanFixture(10);
    const descendantPidPath = join(dirname(scanTemporaryRoot), "windows-descendant.pid");
    const rootPidPath = join(dirname(scanTemporaryRoot), "windows-root.pid");
    const treeKillerStatePath = join(dirname(scanTemporaryRoot), "tree-killer.state");
    const service = new ScanService({
      temporaryRoot: scanTemporaryRoot,
      platform: "win32",
      terminationGraceMilliseconds: 30,
      terminationForceMilliseconds: 80,
      windowsTreeKiller: {
        command: process.execPath,
        argsPrefix: [hangingTreeKiller, treeKillerStatePath],
      },
      resolveRuntime: () => ({
        command: process.execPath,
        argsPrefix: [
          stubbornTree,
          "--descendant-pid",
          descendantPidPath,
          "--root-pid",
          rootPidPath,
        ],
        source: "test",
        workingDirectory: join(testDirectory, "..", ".."),
      }),
    });
    const running = service.start(selection, () => undefined);
    const runningOutcome = running.then(
      () => new Error("scan unexpectedly completed"),
      (error: unknown) => error,
    );
    let descendantPid: number | undefined;
    try {
      for (let attempt = 0; attempt < 100; attempt += 1) {
        try {
          descendantPid = Number.parseInt(await readFile(descendantPidPath, "utf8"), 10);
          break;
        } catch {
          await new Promise((resolveDelay) => setTimeout(resolveDelay, 10));
        }
      }
      expect(descendantPid).toBeTypeOf("number");
      const startedAt = Date.now();

      await expect(service.stop()).rejects.toThrow("未能安全停止");
      expect(Date.now() - startedAt).toBeLessThan(1_000);
      expect(service.isRunning).toBe(true);
      await expect(service.start(selection, () => undefined)).rejects.toThrow("未能安全停止");
      await expect(service.stop()).resolves.toBe(true);
      expect(await runningOutcome).toBeInstanceOf(ScanStoppedError);
      expect(service.isRunning).toBe(false);
      expect(() => process.kill(descendantPid ?? 0, 0)).toThrow();
    } finally {
      await bestEffortStop(service);
      await forceKillRecordedProcess(rootPidPath);
      await forceKillRecordedProcess(descendantPidPath);
      await runningOutcome;
    }
  });

  test("surfaces a failed automatic Windows timeout and allows a bounded retry", async () => {
    const { selection, scanTemporaryRoot } = await scanFixture(10);
    const descendantPidPath = join(dirname(scanTemporaryRoot), "timeout-descendant.pid");
    const rootPidPath = join(dirname(scanTemporaryRoot), "timeout-root.pid");
    const treeKillerStatePath = join(dirname(scanTemporaryRoot), "timeout-tree-killer.state");
    const service = new ScanService({
      temporaryRoot: scanTemporaryRoot,
      platform: "win32",
      maxRunMilliseconds: 30,
      terminationGraceMilliseconds: 30,
      terminationForceMilliseconds: 80,
      windowsTreeKiller: {
        command: process.execPath,
        argsPrefix: [hangingTreeKiller, treeKillerStatePath],
      },
      resolveRuntime: () => ({
        command: process.execPath,
        argsPrefix: [
          stubbornTree,
          "--descendant-pid",
          descendantPidPath,
          "--root-pid",
          rootPidPath,
        ],
        source: "test",
        workingDirectory: join(testDirectory, "..", ".."),
      }),
    });
    let markBlocked: (() => void) | undefined;
    const blocked = new Promise<void>((resolveBlocked) => {
      markBlocked = resolveBlocked;
    });
    const running = service.start(selection, (scanProgress) => {
      if (scanProgress.stage === "blocked") {
        markBlocked?.();
      }
    });
    const runningOutcome = running.then(
      () => new Error("scan unexpectedly completed"),
      (error: unknown) => error,
    );
    try {
      await Promise.race([
        blocked,
        new Promise((_, rejectTimeout) => {
          setTimeout(() => rejectTimeout(new Error("blocked progress was not emitted")), 1_000);
        }),
      ]);
      expect(service.isRunning).toBe(true);
      await expect(service.stop()).resolves.toBe(true);
      expect(await runningOutcome).toBeInstanceOf(ScanStoppedError);
      expect(service.isRunning).toBe(false);
    } finally {
      await bestEffortStop(service);
      await forceKillRecordedProcess(rootPidPath);
      await forceKillRecordedProcess(descendantPidPath);
      await runningOutcome;
    }
  });

  test("surfaces cleanup failure on a stopped scan and blocks restart", async () => {
    const { selection, scanTemporaryRoot } = await scanFixture(10);
    const cleanupArgumentLog = join(dirname(scanTemporaryRoot), "cleanup-arguments.json");
    const service = new ScanService({
      temporaryRoot: scanTemporaryRoot,
      removeTemporaryDirectory: async () => {
        throw new Error("private path must not escape");
      },
      resolveRuntime: () => ({
        command: process.execPath,
        argsPrefix: [
          fakeDocmeta,
          join(dirname(scanTemporaryRoot), "source-report.json"),
          "5000",
          cleanupArgumentLog,
        ],
        source: "test",
        workingDirectory: join(testDirectory, "..", ".."),
      }),
    });
    const running = service.start(selection, () => undefined);
    const stoppedRun = expect(running).rejects.toThrow("临时文件未能安全清理");

    await expect(service.stop()).rejects.toThrow("临时文件未能安全清理");
    await stoppedRun;
    expect(service.isRunning).toBe(false);
    await expect(service.start(selection, () => undefined)).rejects.toThrow("临时文件未能安全清理");
  });
});

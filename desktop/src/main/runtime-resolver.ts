import { createHash } from "node:crypto";
import { createReadStream, lstatSync } from "node:fs";
import { lstat, readFile } from "node:fs/promises";
import { join } from "node:path";

import { expectedExecutableSha256 } from "../../checksum-manifest.mjs";

export interface ResolvedDocmetaCommand {
  command: string;
  argsPrefix: string[];
  source: "packaged" | "frozen-development" | "uv-development" | "test";
  workingDirectory: string;
}

interface ResolveOptions {
  isPackaged: boolean;
  resourcesPath: string;
  projectRoot: string;
  platform?: NodeJS.Platform;
  arch?: NodeJS.Architecture;
  expectedPackagedSha256?: string;
  isFile?: (path: string) => boolean;
  verifyPackaged?: (
    runtimeDirectory: string,
    executableName: string,
    expectedSha256: string,
  ) => Promise<void>;
}

const INTEGRITY_ERROR = "离线分析组件缺失或损坏，请重新安装完整程序";
const MAX_CHECKSUM_BYTES = 16 * 1024;

export class RuntimeIntegrityError extends Error {
  constructor() {
    super(INTEGRITY_ERROR);
    this.name = "RuntimeIntegrityError";
  }
}

function regularFile(path: string): boolean {
  try {
    const metadata = lstatSync(path);
    return metadata.isFile() && !metadata.isSymbolicLink();
  } catch {
    return false;
  }
}

function platformKey(platform: NodeJS.Platform, arch: NodeJS.Architecture): string {
  const systems: Partial<Record<NodeJS.Platform, string>> = {
    darwin: "darwin",
    linux: "linux",
    win32: "windows",
  };
  const architectures: Partial<Record<NodeJS.Architecture, string>> = {
    arm64: "arm64",
    x64: "x86_64",
  };
  const system = systems[platform];
  const architecture = architectures[arch];
  if (system === undefined || architecture === undefined) {
    throw new Error(`当前系统或处理器不受支持：${platform}-${arch}`);
  }
  return `${system}-${architecture}`;
}

interface PackagedLauncher {
  executableName: string;
  argsPrefix: string[];
  workingDirectory: string;
}

function packagedLauncher(
  runtimeDirectory: string,
  resourcesPath: string,
  platform: NodeJS.Platform,
  isFile: (path: string) => boolean,
): PackagedLauncher | undefined {
  const nativeExecutable = platform === "win32" ? "docmeta.exe" : "docmeta";
  const hasNativeExecutable = isFile(join(runtimeDirectory, nativeExecutable));
  const hasEmbeddedPython = platform === "win32" && isFile(join(runtimeDirectory, "python.exe"));
  if (Number(hasNativeExecutable) + Number(hasEmbeddedPython) !== 1) {
    return undefined;
  }
  if (hasNativeExecutable) {
    return {
      executableName: nativeExecutable,
      argsPrefix: [],
      workingDirectory: resourcesPath,
    };
  }
  const applicationEntryPoint = join(
    runtimeDirectory,
    "app",
    "src",
    "document_metadata_inspector",
    "cli.py",
  );
  if (!isFile(applicationEntryPoint)) {
    return undefined;
  }
  return {
    executableName: "python.exe",
    argsPrefix: ["-I", "-s", "-m", "document_metadata_inspector.cli"],
    workingDirectory: join(runtimeDirectory, "app"),
  };
}

async function sha256File(path: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    digest.update(chunk);
  }
  return digest.digest("hex");
}

export async function verifyPackagedRuntime(
  runtimeDirectory: string,
  executableName: string,
  expectedSha256: string,
): Promise<void> {
  try {
    if (!/^[0-9a-f]{64}$/u.test(expectedSha256)) {
      throw new RuntimeIntegrityError();
    }
    const executable = join(runtimeDirectory, executableName);
    const checksumPath = join(runtimeDirectory, "SHA256SUMS");
    const [executableMetadata, checksumMetadata] = await Promise.all([
      lstat(executable),
      lstat(checksumPath),
    ]);
    if (
      !executableMetadata.isFile() ||
      executableMetadata.isSymbolicLink() ||
      !checksumMetadata.isFile() ||
      checksumMetadata.isSymbolicLink() ||
      checksumMetadata.size === 0 ||
      checksumMetadata.size > MAX_CHECKSUM_BYTES
    ) {
      throw new RuntimeIntegrityError();
    }
    const checksumText = await readFile(checksumPath, "utf8");
    const manifestSha256 = expectedExecutableSha256(checksumText, executableName);
    if (manifestSha256 !== expectedSha256) {
      throw new RuntimeIntegrityError();
    }
    if ((await sha256File(executable)) !== manifestSha256) {
      throw new RuntimeIntegrityError();
    }
  } catch {
    throw new RuntimeIntegrityError();
  }
}

export async function resolveDocmetaCommand(
  options: ResolveOptions,
): Promise<ResolvedDocmetaCommand> {
  const platform = options.platform ?? process.platform;
  const arch = options.arch ?? process.arch;
  const executableName = platform === "win32" ? "docmeta.exe" : "docmeta";
  const isFile = options.isFile ?? regularFile;

  if (options.isPackaged) {
    const runtimeDirectory = join(options.resourcesPath, "docmeta-runtime");
    const launcher = packagedLauncher(runtimeDirectory, options.resourcesPath, platform, isFile);
    if (launcher === undefined) {
      throw new RuntimeIntegrityError();
    }
    await (options.verifyPackaged ?? verifyPackagedRuntime)(
      runtimeDirectory,
      launcher.executableName,
      options.expectedPackagedSha256 ?? "",
    );
    return {
      command: join(runtimeDirectory, launcher.executableName),
      argsPrefix: launcher.argsPrefix,
      source: "packaged",
      workingDirectory: launcher.workingDirectory,
    };
  }

  const frozenDevelopment = join(
    options.projectRoot,
    "dist",
    platformKey(platform, arch),
    "onefile",
    executableName,
  );
  if (isFile(frozenDevelopment)) {
    return {
      command: frozenDevelopment,
      argsPrefix: [],
      source: "frozen-development",
      workingDirectory: options.projectRoot,
    };
  }
  return {
    command: "uv",
    argsPrefix: ["run", "docmeta"],
    source: "uv-development",
    workingDirectory: options.projectRoot,
  };
}

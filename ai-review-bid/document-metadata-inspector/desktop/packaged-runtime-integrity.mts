import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { lstat, readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expectedExecutableSha256 } from "./checksum-manifest.mjs";

const INTEGRITY_ERROR = "Packaged offline core failed checksum verification";

async function sha256File(path: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    digest.update(chunk);
  }
  return digest.digest("hex");
}

function runtimeDirectory(applicationPath: string, platform: NodeJS.Platform): string {
  if (platform === "darwin") {
    return resolve(applicationPath, "Contents", "Resources", "docmeta-runtime");
  }
  return resolve(applicationPath, "resources", "docmeta-runtime");
}

async function regularFile(path: string): Promise<boolean> {
  try {
    const metadata = await lstat(path);
    return metadata.isFile() && !metadata.isSymbolicLink();
  } catch {
    return false;
  }
}

async function runtimeExecutableName(runtime: string, platform: NodeJS.Platform): Promise<string> {
  const nativeExecutable = platform === "win32" ? "docmeta.exe" : "docmeta";
  const native = await regularFile(resolve(runtime, nativeExecutable));
  const python = platform === "win32" && (await regularFile(resolve(runtime, "python.exe")));
  if (Number(native) + Number(python) !== 1) {
    throw new Error(INTEGRITY_ERROR);
  }
  if (native) {
    return nativeExecutable;
  }
  if (
    !(await regularFile(resolve(runtime, "app", "src", "document_metadata_inspector", "cli.py")))
  ) {
    throw new Error(INTEGRITY_ERROR);
  }
  return "python.exe";
}

export async function verifyPackagedRuntimeHash(
  applicationPath: string,
  platform: NodeJS.Platform,
): Promise<void> {
  try {
    const runtime = runtimeDirectory(applicationPath, platform);
    const executableName = await runtimeExecutableName(runtime, platform);
    const manifest = await readFile(resolve(runtime, "SHA256SUMS"), "utf8");
    const expected = expectedExecutableSha256(manifest, executableName);
    if ((await sha256File(resolve(runtime, executableName))) !== expected) {
      throw new Error(INTEGRITY_ERROR);
    }
  } catch {
    throw new Error(INTEGRITY_ERROR);
  }
}

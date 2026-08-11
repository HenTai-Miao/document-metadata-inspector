import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile } from "node:fs/promises";
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

export async function verifyPackagedRuntimeHash(
  applicationPath: string,
  platform: NodeJS.Platform,
): Promise<void> {
  try {
    const runtime = runtimeDirectory(applicationPath, platform);
    const executableName = platform === "win32" ? "docmeta.exe" : "docmeta";
    const manifest = await readFile(resolve(runtime, "SHA256SUMS"), "utf8");
    const expected = expectedExecutableSha256(manifest, executableName);
    if ((await sha256File(resolve(runtime, executableName))) !== expected) {
      throw new Error(INTEGRITY_ERROR);
    }
  } catch {
    throw new Error(INTEGRITY_ERROR);
  }
}

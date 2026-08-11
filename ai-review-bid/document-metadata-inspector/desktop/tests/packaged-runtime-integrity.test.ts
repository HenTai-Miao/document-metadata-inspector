import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { verifyPackagedRuntimeHash } from "../packaged-runtime-integrity.mts";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

async function applicationWithRuntime(
  platform: "darwin" | "win32",
  contents: string,
  launcher: "native" | "python" = "native",
): Promise<string> {
  const application = await mkdtemp(join(tmpdir(), "docmeta-packaged-runtime-"));
  temporaryDirectories.push(application);
  const resources =
    platform === "darwin"
      ? join(application, "Contents", "Resources")
      : join(application, "resources");
  const runtime = join(resources, "docmeta-runtime");
  await mkdir(runtime, { recursive: true });
  const executableName =
    platform === "win32" && launcher === "python"
      ? "python.exe"
      : platform === "win32"
        ? "docmeta.exe"
        : "docmeta";
  await writeFile(join(runtime, executableName), contents);
  if (launcher === "python") {
    const applicationPackage = join(runtime, "app", "src", "document_metadata_inspector");
    await mkdir(applicationPackage, { recursive: true });
    await writeFile(join(applicationPackage, "cli.py"), "def main(): pass\n", "utf8");
  }
  const digest = createHash("sha256").update(contents).digest("hex");
  await writeFile(join(runtime, "SHA256SUMS"), `${digest}  ${executableName}\n`, "utf8");
  return application;
}

describe("verifyPackagedRuntimeHash", () => {
  test("accepts the embedded Windows Python application layout", async () => {
    const application = await applicationWithRuntime("win32", "trusted Python", "python");
    await expect(verifyPackagedRuntimeHash(application, "win32")).resolves.toBeUndefined();
  });

  test("rejects embedded Windows Python without the packaged application", async () => {
    const application = await applicationWithRuntime("win32", "trusted Python", "python");
    await rm(
      join(
        application,
        "resources",
        "docmeta-runtime",
        "app",
        "src",
        "document_metadata_inspector",
        "cli.py",
      ),
    );
    await expect(verifyPackagedRuntimeHash(application, "win32")).rejects.toThrow(
      "Packaged offline core failed checksum verification",
    );
  });

  test.each(["darwin", "win32"] as const)(
    "accepts the %s packaged application layout",
    async (platform) => {
      const application = await applicationWithRuntime(platform, "trusted core");
      await expect(verifyPackagedRuntimeHash(application, platform)).resolves.toBeUndefined();
    },
  );

  test("rejects a modified Windows core", async () => {
    const application = await applicationWithRuntime("win32", "trusted core");
    await writeFile(
      join(application, "resources", "docmeta-runtime", "docmeta.exe"),
      "modified core",
    );
    await expect(verifyPackagedRuntimeHash(application, "win32")).rejects.toThrow(
      "Packaged offline core failed checksum verification",
    );
  });
});

import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { resolveDocmetaCommand, verifyPackagedRuntime } from "../src/main/runtime-resolver";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

describe("resolveDocmetaCommand", () => {
  test("uses the packaged runtime and never falls back on an end-user machine", async () => {
    // Falling back to uv in a packaged app would break offline use for ordinary users.
    const command = await resolveDocmetaCommand({
      isPackaged: true,
      resourcesPath: "/Applications/Docmeta.app/Contents/Resources",
      projectRoot: "/source/project",
      platform: "darwin",
      arch: "arm64",
      expectedPackagedSha256: "a".repeat(64),
      isFile: (path) => path.endsWith("/docmeta-runtime/docmeta"),
      verifyPackaged: async () => undefined,
    });

    expect(command).toEqual({
      command: "/Applications/Docmeta.app/Contents/Resources/docmeta-runtime/docmeta",
      argsPrefix: [],
      source: "packaged",
      workingDirectory: "/Applications/Docmeta.app/Contents/Resources",
    });

    await expect(
      resolveDocmetaCommand({
        isPackaged: true,
        resourcesPath: "/Applications/Broken.app/Contents/Resources",
        projectRoot: "/source/project",
        platform: "darwin",
        arch: "arm64",
        isFile: () => false,
      }),
    ).rejects.toThrow("离线分析组件缺失或损坏");
  });

  test("prefers the current platform frozen build before the development uv command", async () => {
    // Wrong platform aliases would silently miss a valid frozen runtime.
    const command = await resolveDocmetaCommand({
      isPackaged: false,
      resourcesPath: "/unused",
      projectRoot: "/source/project",
      platform: "win32",
      arch: "x64",
      isFile: (path) => path === "/source/project/dist/windows-x86_64/onefile/docmeta.exe",
    });

    expect(command).toEqual({
      command: "/source/project/dist/windows-x86_64/onefile/docmeta.exe",
      argsPrefix: [],
      source: "frozen-development",
      workingDirectory: "/source/project",
    });
    expect(
      await resolveDocmetaCommand({
        isPackaged: false,
        resourcesPath: "/unused",
        projectRoot: "/source/project",
        platform: "linux",
        arch: "arm64",
        isFile: () => false,
      }),
    ).toEqual({
      command: "uv",
      argsPrefix: ["run", "docmeta"],
      source: "uv-development",
      workingDirectory: "/source/project",
    });
  });

  test("rejects a packaged executable whose bytes do not match SHA256SUMS", async () => {
    const resources = await mkdtemp(join(tmpdir(), "docmeta-runtime-integrity-"));
    temporaryDirectories.push(resources);
    const runtimeDirectory = join(resources, "docmeta-runtime");
    await mkdir(runtimeDirectory);
    const executable = join(runtimeDirectory, "docmeta");
    await writeFile(executable, "trusted runtime", { mode: 0o755 });
    const expected = createHash("sha256").update("trusted runtime").digest("hex");
    await writeFile(join(runtimeDirectory, "SHA256SUMS"), `${expected}  docmeta\n`, "utf8");

    await expect(
      verifyPackagedRuntime(runtimeDirectory, "docmeta", expected),
    ).resolves.toBeUndefined();
    await writeFile(executable, "tampered runtime", { mode: 0o755 });
    const tampered = createHash("sha256").update("tampered runtime").digest("hex");
    await writeFile(join(runtimeDirectory, "SHA256SUMS"), `${tampered}  docmeta\n`, "utf8");
    await expect(verifyPackagedRuntime(runtimeDirectory, "docmeta", expected)).rejects.toThrow(
      "离线分析组件缺失或损坏",
    );
  });

  test("rejects a checksum manifest containing any malformed non-empty line", async () => {
    const resources = await mkdtemp(join(tmpdir(), "docmeta-runtime-manifest-"));
    temporaryDirectories.push(resources);
    const runtimeDirectory = join(resources, "docmeta-runtime");
    await mkdir(runtimeDirectory);
    const executable = join(runtimeDirectory, "docmeta");
    await writeFile(executable, "trusted runtime", { mode: 0o755 });
    const expected = createHash("sha256").update("trusted runtime").digest("hex");
    await writeFile(
      join(runtimeDirectory, "SHA256SUMS"),
      `${expected}  docmeta\nthis line must not be ignored\n`,
      "utf8",
    );

    await expect(verifyPackagedRuntime(runtimeDirectory, "docmeta", expected)).rejects.toThrow(
      "离线分析组件缺失或损坏",
    );
  });

  test("rejects an additional valid checksum record", async () => {
    const resources = await mkdtemp(join(tmpdir(), "docmeta-runtime-extra-record-"));
    temporaryDirectories.push(resources);
    const runtimeDirectory = join(resources, "docmeta-runtime");
    await mkdir(runtimeDirectory);
    const executable = join(runtimeDirectory, "docmeta");
    await writeFile(executable, "trusted runtime", { mode: 0o755 });
    const expected = createHash("sha256").update("trusted runtime").digest("hex");
    await writeFile(
      join(runtimeDirectory, "SHA256SUMS"),
      `${expected}  docmeta\n${"a".repeat(64)}  unrelated\n`,
      "utf8",
    );

    await expect(verifyPackagedRuntime(runtimeDirectory, "docmeta", expected)).rejects.toThrow(
      "离线分析组件缺失或损坏",
    );
  });
});

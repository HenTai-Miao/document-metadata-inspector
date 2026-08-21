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
  test("launches the Python runtime embedded in a packaged Windows application", async () => {
    // Removing embedded-Python discovery would make the installed application
    // incorrectly demand the legacy PyInstaller executable.
    const resources = await mkdtemp(join(tmpdir(), "docmeta-embedded-python-"));
    temporaryDirectories.push(resources);
    const runtimeDirectory = join(resources, "docmeta-runtime");
    const applicationPackage = join(runtimeDirectory, "app", "src", "document_metadata_inspector");
    await mkdir(applicationPackage, { recursive: true });
    await writeFile(join(applicationPackage, "cli.py"), "def main(): pass\n", "utf8");
    const executable = join(runtimeDirectory, "python.exe");
    await writeFile(executable, "controlled Windows Python");
    const expected = createHash("sha256").update("controlled Windows Python").digest("hex");
    await writeFile(join(runtimeDirectory, "SHA256SUMS"), `${expected}  python.exe\n`, "utf8");

    await expect(
      resolveDocmetaCommand({
        isPackaged: true,
        resourcesPath: resources,
        projectRoot: "/unused",
        platform: "win32",
        arch: "x64",
        expectedPackagedSha256: expected,
      }),
    ).resolves.toEqual({
      command: executable,
      argsPrefix: ["-I", "-s", "-m", "document_metadata_inspector.cli"],
      source: "packaged",
      workingDirectory: join(runtimeDirectory, "app"),
    });
  });

  test("rejects embedded Python when the packaged application entry point is missing", async () => {
    // Accepting only python.exe would ship an interpreter that cannot run the app.
    const resources = await mkdtemp(join(tmpdir(), "docmeta-embedded-python-missing-app-"));
    temporaryDirectories.push(resources);
    const runtimeDirectory = join(resources, "docmeta-runtime");
    await mkdir(runtimeDirectory, { recursive: true });
    await writeFile(join(runtimeDirectory, "python.exe"), "controlled Windows Python");
    const expected = createHash("sha256").update("controlled Windows Python").digest("hex");
    await writeFile(join(runtimeDirectory, "SHA256SUMS"), `${expected}  python.exe\n`, "utf8");

    await expect(
      resolveDocmetaCommand({
        isPackaged: true,
        resourcesPath: resources,
        projectRoot: "/unused",
        platform: "win32",
        arch: "x64",
        expectedPackagedSha256: expected,
      }),
    ).rejects.toThrow("离线分析组件缺失或损坏");
  });

  test("uses the packaged runtime and never falls back on an end-user machine", async () => {
    // Falling back to uv in a packaged app would break offline use for ordinary users.
    const resourcesPath = join(tmpdir(), "Applications", "Docmeta.app", "Contents", "Resources");
    const expectedExecutable = join(resourcesPath, "docmeta-runtime", "docmeta");
    const projectRoot = join(tmpdir(), "source", "project");
    const command = await resolveDocmetaCommand({
      isPackaged: true,
      resourcesPath,
      projectRoot,
      platform: "darwin",
      arch: "arm64",
      expectedPackagedSha256: "a".repeat(64),
      isFile: (path) => path === expectedExecutable,
      verifyPackaged: async () => undefined,
    });

    expect(command).toEqual({
      command: expectedExecutable,
      argsPrefix: [],
      source: "packaged",
      workingDirectory: resourcesPath,
    });

    const brokenResourcesPath = join(
      tmpdir(),
      "Applications",
      "Broken.app",
      "Contents",
      "Resources",
    );
    await expect(
      resolveDocmetaCommand({
        isPackaged: true,
        resourcesPath: brokenResourcesPath,
        projectRoot,
        platform: "darwin",
        arch: "arm64",
        isFile: () => false,
      }),
    ).rejects.toThrow("离线分析组件缺失或损坏");
  });

  test("prefers the current platform frozen build before the development uv command", async () => {
    // Wrong platform aliases would silently miss a valid frozen runtime.
    const projectRoot = join(tmpdir(), "source", "project");
    const expectedExecutable = join(
      projectRoot,
      "dist",
      "windows-x86_64",
      "onefile",
      "docmeta.exe",
    );
    const command = await resolveDocmetaCommand({
      isPackaged: false,
      resourcesPath: join(tmpdir(), "unused"),
      projectRoot,
      platform: "win32",
      arch: "x64",
      isFile: (path) => path === expectedExecutable,
    });

    expect(command).toEqual({
      command: expectedExecutable,
      argsPrefix: [],
      source: "frozen-development",
      workingDirectory: projectRoot,
    });
    expect(
      await resolveDocmetaCommand({
        isPackaged: false,
        resourcesPath: join(tmpdir(), "unused"),
        projectRoot,
        platform: "linux",
        arch: "arm64",
        isFile: () => false,
      }),
    ).toEqual({
      command: "uv",
      argsPrefix: ["run", "docmeta"],
      source: "uv-development",
      workingDirectory: projectRoot,
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

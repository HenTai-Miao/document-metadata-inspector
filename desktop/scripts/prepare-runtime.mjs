import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { constants, createReadStream } from "node:fs";
import { access, chmod, copyFile, mkdir, readFile, rm } from "node:fs/promises";
import { basename, resolve } from "node:path";

import { expectedExecutableSha256 as parseExecutableSha256 } from "../checksum-manifest.mjs";

const desktopRoot = resolve(import.meta.dirname, "..");
const projectRoot = resolve(desktopRoot, "..");
const systemNames = { darwin: "darwin", linux: "linux", win32: "windows" };
const architectureNames = { arm64: "arm64", x64: "x86_64" };
const systemName = systemNames[process.platform];
const architectureName = architectureNames[process.arch];

function buildCurrentRuntime() {
  return new Promise((resolveBuild, rejectBuild) => {
    const child = spawn("uv", ["run", "python", "scripts/build_release.py", "--mode", "onefile"], {
      cwd: projectRoot,
      env: { ...process.env, PYTHONPATH: "", PYTHONHOME: "" },
      shell: false,
      stdio: "inherit",
      windowsHide: true,
    });
    child.once("error", (error) => {
      rejectBuild(new Error(`Unable to start the offline core build: ${error.message}`));
    });
    child.once("close", (code) => {
      if (code === 0) {
        resolveBuild();
        return;
      }
      rejectBuild(new Error(`Offline core build failed with exit code ${String(code)}`));
    });
  });
}

async function sha256File(path) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    digest.update(chunk);
  }
  return digest.digest("hex");
}

async function expectedExecutableSha256(manifestPath, executableName) {
  const manifest = await readFile(manifestPath, "utf8");
  return parseExecutableSha256(manifest, executableName);
}

if (systemName === undefined || architectureName === undefined) {
  throw new Error(`Unsupported packaging platform: ${process.platform}-${process.arch}`);
}

await buildCurrentRuntime();

const executableName = process.platform === "win32" ? "docmeta.exe" : "docmeta";
const sourceDirectory = resolve(
  projectRoot,
  "dist",
  `${systemName}-${architectureName}`,
  "onefile",
);
const sourceExecutable = resolve(sourceDirectory, executableName);
const sourceChecksums = resolve(sourceDirectory, "SHA256SUMS");
await Promise.all([
  access(sourceExecutable, constants.R_OK),
  access(sourceChecksums, constants.R_OK),
]);
const expectedSha256 = await expectedExecutableSha256(sourceChecksums, executableName);
if ((await sha256File(sourceExecutable)) !== expectedSha256) {
  throw new Error("Offline core failed checksum verification before packaging");
}

const destination = resolve(desktopRoot, ".runtime", "docmeta-runtime");
await rm(destination, { recursive: true, force: true });
await mkdir(destination, { recursive: true });
await Promise.all([
  copyFile(sourceExecutable, resolve(destination, basename(sourceExecutable))),
  copyFile(sourceChecksums, resolve(destination, "SHA256SUMS")),
]);
if (process.platform !== "win32") {
  await chmod(resolve(destination, executableName), 0o755);
}
const copiedExpectedSha256 = await expectedExecutableSha256(
  resolve(destination, "SHA256SUMS"),
  executableName,
);
if (
  copiedExpectedSha256 !== expectedSha256 ||
  (await sha256File(resolve(destination, executableName))) !== copiedExpectedSha256
) {
  throw new Error("Copied offline core failed checksum verification");
}
process.stdout.write(`Prepared bundled runtime: ${systemName}-${architectureName}\n`);

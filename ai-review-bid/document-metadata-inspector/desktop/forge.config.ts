import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { promisify } from "node:util";

import type { ForgeConfig } from "@electron-forge/shared-types";
import { expectedExecutableSha256 } from "./checksum-manifest.mjs";

// Forge 7.11 invokes Vite's supported bundled config loader without exposing
// configLoader; direct Vite commands explicitly select the runner loader.
process.env.VITE_CONFIG_NATIVE_IGNORE_WARNING ??= "true";

const runtimeDirectory = resolve(__dirname, ".runtime", "docmeta-runtime");
const electronZipDirectory = process.env.DOCMETA_ELECTRON_ZIP_DIR;
const execFileAsync = promisify(execFile);

function preserveBundledRuntimeSignature(filePath: string): boolean {
  return filePath.split(/[\\/]/u).includes("docmeta-runtime");
}

async function sha256File(path: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    digest.update(chunk);
  }
  return digest.digest("hex");
}

async function verifyPackagedRuntimeHash(appBundle: string): Promise<void> {
  const runtimePath = resolve(appBundle, "Contents", "Resources", "docmeta-runtime");
  const executableName = "docmeta";
  const manifest = await readFile(resolve(runtimePath, "SHA256SUMS"), "utf8");
  const expected = expectedExecutableSha256(manifest, executableName);
  if ((await sha256File(resolve(runtimePath, executableName))) !== expected) {
    throw new Error("macOS signing changed the bundled offline core bytes");
  }
}

const config: ForgeConfig = {
  packagerConfig: {
    asar: true,
    executableName: "docmeta-review",
    extraResource: existsSync(runtimeDirectory) ? [runtimeDirectory] : [],
    osxSign: {
      identity: "-",
      identityValidation: false,
      ignore: preserveBundledRuntimeSignature,
      preAutoEntitlements: false,
      preEmbedProvisioningProfile: false,
    },
    ...(electronZipDirectory === undefined
      ? {}
      : { electronZipDir: resolve(electronZipDirectory) }),
  },
  rebuildConfig: {},
  hooks: {
    postPackage: async (_forgeConfig, result) => {
      if (result.platform !== "darwin") {
        return;
      }
      for (const outputPath of result.outputPaths) {
        const appBundles = (await readdir(outputPath, { withFileTypes: true }))
          .filter((entry) => entry.isDirectory() && entry.name.endsWith(".app"))
          .map((entry) => resolve(outputPath, entry.name));
        if (appBundles.length !== 1 || appBundles[0] === undefined) {
          throw new Error("macOS package output must contain exactly one application bundle");
        }
        await verifyPackagedRuntimeHash(appBundles[0]);
        await execFileAsync("codesign", ["--verify", "--deep", "--strict", appBundles[0]]);
      }
    },
  },
  makers: [
    {
      name: "@electron-forge/maker-squirrel",
      platforms: ["win32"],
      config: { name: "DocumentMetadataInspector" },
    },
    { name: "@electron-forge/maker-zip", platforms: ["darwin"], config: {} },
    { name: "@electron-forge/maker-dmg", platforms: ["darwin"], config: {} },
    { name: "@electron-forge/maker-deb", platforms: ["linux"], config: {} },
    { name: "@electron-forge/maker-rpm", platforms: ["linux"], config: {} },
  ],
  plugins: [
    {
      name: "@electron-forge/plugin-vite",
      config: {
        build: [
          { entry: "src/main/main.ts", config: "vite.main.config.mts" },
          { entry: "src/preload/preload.ts", config: "vite.preload.config.mts" },
        ],
        renderer: [{ name: "main_window", config: "vite.renderer.config.mts" }],
      },
    },
  ],
};

export default config;

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { readdir } from "node:fs/promises";
import { resolve } from "node:path";
import { promisify } from "node:util";

import type { ForgeConfig } from "@electron-forge/shared-types";
import { verifyPackagedRuntimeHash } from "./packaged-runtime-integrity.mts";

// Forge 7.11 invokes Vite's supported bundled config loader without exposing
// configLoader; direct Vite commands explicitly select the runner loader.
process.env.VITE_CONFIG_NATIVE_IGNORE_WARNING ??= "true";

const runtimeDirectory = resolve(__dirname, ".runtime", "docmeta-runtime");
const electronZipDirectory = process.env.DOCMETA_ELECTRON_ZIP_DIR;
const execFileAsync = promisify(execFile);

function preserveBundledRuntimeSignature(filePath: string): boolean {
  return filePath.split(/[\\/]/u).includes("docmeta-runtime");
}

function isSupportedPlatform(platform: string): platform is NodeJS.Platform {
  return platform === "darwin" || platform === "linux" || platform === "win32";
}

async function onlyMacApplication(outputPath: string): Promise<string> {
  const appBundles = (await readdir(outputPath, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory() && entry.name.endsWith(".app"))
    .map((entry) => resolve(outputPath, entry.name));
  if (appBundles.length !== 1 || appBundles[0] === undefined) {
    throw new Error("macOS package output must contain exactly one application bundle");
  }
  return appBundles[0];
}

const config: ForgeConfig = {
  packagerConfig: {
    asar: true,
    executableName: "docmeta-review",
    icon: resolve(__dirname, "build", "icons", "icon"),
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
      if (!isSupportedPlatform(result.platform)) {
        throw new Error(`Unsupported package platform: ${result.platform}`);
      }
      for (const outputPath of result.outputPaths) {
        const applicationPath =
          result.platform === "darwin" ? await onlyMacApplication(outputPath) : outputPath;
        await verifyPackagedRuntimeHash(applicationPath, result.platform);
        if (result.platform === "darwin") {
          await execFileAsync("codesign", ["--verify", "--deep", "--strict", applicationPath]);
        }
      }
    },
  },
  makers: [
    {
      name: "@electron-forge/maker-squirrel",
      platforms: ["win32"],
      config: { name: "DocumentMetadataInspector" },
    },
    { name: "@electron-forge/maker-zip", platforms: ["darwin", "win32"], config: {} },
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

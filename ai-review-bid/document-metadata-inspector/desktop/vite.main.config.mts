import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { defineConfig } from "vite";
import { expectedExecutableSha256 } from "./checksum-manifest.mjs";

function bundledRuntimeSha256(): string {
  const executableName = process.platform === "win32" ? "docmeta.exe" : "docmeta";
  try {
    const manifest = readFileSync(
      resolve(import.meta.dirname, ".runtime", "docmeta-runtime", "SHA256SUMS"),
      "utf8",
    );
    return expectedExecutableSha256(manifest, executableName);
  } catch {
    return "";
  }
}

export default defineConfig({
  define: {
    DOCMETA_RUNTIME_SHA256: JSON.stringify(bundledRuntimeSha256()),
  },
  build: {
    rollupOptions: {
      external: ["electron", "electron-squirrel-startup"],
    },
  },
});

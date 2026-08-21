import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { defineConfig } from "vite";
import { expectedExecutableSha256 } from "./checksum-manifest.mjs";

function bundledRuntimeSha256(): string {
  try {
    const runtime = resolve(import.meta.dirname, ".runtime", "docmeta-runtime");
    const executableNames = ["docmeta.exe", "docmeta", "python.exe"].filter((name) =>
      existsSync(resolve(runtime, name)),
    );
    if (executableNames.length !== 1 || executableNames[0] === undefined) {
      return "";
    }
    const manifest = readFileSync(resolve(runtime, "SHA256SUMS"), "utf8");
    return expectedExecutableSha256(manifest, executableNames[0]);
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
      external: ["electron"],
    },
  },
});

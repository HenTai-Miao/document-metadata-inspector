import { spawn } from "node:child_process";
import { lstat } from "node:fs/promises";
import { resolve } from "node:path";

const argumentsList = process.argv.slice(2).filter((argument) => argument !== "--");

function option(name) {
  const index = argumentsList.indexOf(name);
  return index === -1 ? undefined : argumentsList[index + 1];
}

const folderArgument = option("--folder");
const reportArgument = option("--report");
const port = option("--port") ?? "4175";

if (folderArgument === undefined || reportArgument === undefined || !/^\d{2,5}$/.test(port)) {
  process.stderr.write(
    "Usage: pnpm preview:real -- --folder DIR --report REPORT.json [--port 4175]\n",
  );
  process.exitCode = 2;
} else {
  const folder = resolve(folderArgument);
  const report = resolve(reportArgument);
  const [folderMetadata, reportMetadata] = await Promise.all([lstat(folder), lstat(report)]);
  if (!folderMetadata.isDirectory() || folderMetadata.isSymbolicLink()) {
    throw new Error("Preview folder must be a regular directory");
  }
  if (!reportMetadata.isFile() || reportMetadata.isSymbolicLink()) {
    throw new Error("Preview report must be a regular file");
  }
  const command = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
  const child = spawn(
    command,
    [
      "exec",
      "vite",
      "--config",
      "vite.renderer.config.mts",
      "--configLoader",
      "runner",
      "--host",
      "127.0.0.1",
      "--port",
      port,
    ],
    {
      cwd: resolve(import.meta.dirname, ".."),
      env: {
        ...process.env,
        DOCMETA_PREVIEW_FOLDER: folder,
        DOCMETA_PREVIEW_REPORT: report,
      },
      shell: false,
      stdio: "inherit",
    },
  );
  const stop = () => child.kill("SIGTERM");
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  child.once("exit", (code, signal) => {
    if (signal !== null) {
      process.kill(process.pid, signal);
      return;
    }
    process.exitCode = code ?? 1;
  });
}

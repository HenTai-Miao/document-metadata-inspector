import { spawn } from "node:child_process";
import { lstat, readdir } from "node:fs/promises";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

const desktopRoot = resolve(import.meta.dirname, "..");
const argumentsList = process.argv.slice(2).filter((argument) => argument !== "--");

function option(name) {
  const index = argumentsList.indexOf(name);
  return index === -1 ? undefined : argumentsList[index + 1];
}

const folderArgument = option("--folder");
const reportArgument = option("--report");
const runtimeArgument = option("--runtime");
const port = option("--port") ?? "4176";

if (
  folderArgument === undefined ||
  reportArgument === undefined ||
  runtimeArgument === undefined ||
  !/^\d{2,5}$/u.test(port)
) {
  process.stderr.write(
    "Usage: pnpm verify:real -- --folder DIR --report REPORT.json --runtime DOCMETA [--port 4176]\n",
  );
  process.exitCode = 2;
} else {
  const folder = resolve(folderArgument);
  const report = resolve(reportArgument);
  const runtime = resolve(runtimeArgument);
  const [folderMetadata, reportMetadata, runtimeMetadata] = await Promise.all([
    lstat(folder),
    lstat(report),
    lstat(runtime),
  ]);
  if (!folderMetadata.isDirectory() || folderMetadata.isSymbolicLink()) {
    throw new Error("Real verification folder must be a regular directory");
  }
  for (const [name, metadata] of [
    ["report", reportMetadata],
    ["runtime", runtimeMetadata],
  ]) {
    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error(`Real verification ${name} must be a regular file`);
    }
  }

  const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
  const uv = process.platform === "win32" ? "uv.exe" : "uv";

  function run(command, args, environment = {}) {
    return new Promise((resolveRun, rejectRun) => {
      const child = spawn(command, args, {
        cwd: desktopRoot,
        env: { ...process.env, ...environment },
        shell: false,
        stdio: "inherit",
        windowsHide: true,
      });
      child.once("error", rejectRun);
      child.once("close", (code, signal) => {
        if (code === 0) {
          resolveRun();
          return;
        }
        rejectRun(
          new Error(`${command} failed (${signal === null ? `exit ${String(code)}` : signal})`),
        );
      });
    });
  }

  async function findCachedChromium() {
    if (process.env.DOCMETA_CHROMIUM_EXECUTABLE !== undefined) {
      return process.env.DOCMETA_CHROMIUM_EXECUTABLE;
    }
    const cacheRoot =
      process.platform === "darwin"
        ? join(homedir(), "Library", "Caches", "ms-playwright")
        : process.platform === "win32"
          ? join(process.env.LOCALAPPDATA ?? homedir(), "ms-playwright")
          : join(process.env.XDG_CACHE_HOME ?? join(homedir(), ".cache"), "ms-playwright");
    let revisions;
    try {
      revisions = (await readdir(cacheRoot, { withFileTypes: true }))
        .filter((entry) => entry.isDirectory() && entry.name.startsWith("chromium_headless_shell-"))
        .map((entry) => entry.name)
        .sort()
        .reverse();
    } catch {
      return undefined;
    }
    const executableName =
      process.platform === "win32" ? "chrome-headless-shell.exe" : "chrome-headless-shell";
    for (const revision of revisions) {
      const revisionRoot = join(cacheRoot, revision);
      const platforms = await readdir(revisionRoot, { withFileTypes: true }).catch(() => []);
      for (const platformDirectory of platforms) {
        if (!platformDirectory.isDirectory()) {
          continue;
        }
        const executable = join(revisionRoot, platformDirectory.name, executableName);
        try {
          const metadata = await lstat(executable);
          if (metadata.isFile() && !metadata.isSymbolicLink()) {
            return executable;
          }
        } catch {
          // Try the next installed Chromium revision.
        }
      }
    }
    return undefined;
  }

  await run(pnpm, ["exec", "vitest", "run", "tests/real-runtime.integration.test.ts"], {
    DOCMETA_REAL_FOLDER: folder,
    DOCMETA_REAL_RUNTIME: runtime,
  });

  const preview = spawn(
    process.execPath,
    [
      resolve(desktopRoot, "scripts", "real-preview.mjs"),
      "--folder",
      folder,
      "--report",
      report,
      "--port",
      port,
    ],
    {
      cwd: desktopRoot,
      env: process.env,
      shell: false,
      stdio: "inherit",
      windowsHide: true,
      detached: process.platform !== "win32",
    },
  );
  let previewExit;
  preview.once("exit", (code, signal) => {
    previewExit = signal === null ? `exit ${String(code)}` : signal;
  });

  async function stopPreview() {
    if (preview.pid === undefined || previewExit !== undefined) {
      return;
    }
    if (process.platform === "win32") {
      await run("taskkill", ["/PID", String(preview.pid), "/T", "/F"]).catch(() => undefined);
      return;
    }
    try {
      process.kill(-preview.pid, "SIGTERM");
    } catch {
      preview.kill("SIGTERM");
    }
  }

  try {
    const previewUrl = `http://127.0.0.1:${port}`;
    let ready = false;
    for (let attempt = 0; attempt < 200; attempt += 1) {
      if (previewExit !== undefined) {
        throw new Error(`Real preview stopped before verification (${previewExit})`);
      }
      try {
        const response = await fetch(previewUrl);
        if (response.ok) {
          ready = true;
          break;
        }
      } catch {
        // The local Vite server is still starting.
      }
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
    }
    if (!ready) {
      throw new Error("Real preview did not become ready within 20 seconds");
    }
    let chromiumExecutable = await findCachedChromium();
    if (chromiumExecutable === undefined) {
      await run(uv, ["run", "--with", "playwright==1.62.0", "playwright", "install", "chromium"]);
      chromiumExecutable = await findCachedChromium();
    }
    await run(
      uv,
      ["run", "--with", "playwright==1.62.0", "python", "tests/e2e/renderer_real_data.py"],
      {
        DOCMETA_PREVIEW_URL: previewUrl,
        ...(chromiumExecutable === undefined
          ? {}
          : { DOCMETA_CHROMIUM_EXECUTABLE: chromiumExecutable }),
      },
    );
    process.stdout.write("Real runtime and renderer verification passed\n");
  } finally {
    await stopPreview();
  }
}

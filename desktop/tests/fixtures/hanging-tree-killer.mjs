import { spawnSync } from "node:child_process";
import { access, writeFile } from "node:fs/promises";

const [statePath, ...argumentsList] = process.argv.slice(2);
const pidIndex = argumentsList.indexOf("/PID");
const targetPid = Number.parseInt(argumentsList[pidIndex + 1] ?? "", 10);

if (statePath === undefined || !Number.isInteger(targetPid)) {
  process.exitCode = 2;
} else {
  try {
    await access(statePath);
    if (process.platform === "win32") {
      const result = spawnSync("taskkill", ["/PID", String(targetPid), "/T", "/F"], {
        shell: false,
        stdio: "ignore",
        timeout: 5_000,
        windowsHide: true,
      });
      if (result.error !== undefined || result.status === null || result.status !== 0) {
        process.exitCode = result.status !== null && result.status !== 0 ? result.status : 1;
      }
    } else {
      process.kill(-targetPid, "SIGKILL");
    }
  } catch {
    await writeFile(statePath, "retry\n", "utf8");
    process.on("SIGTERM", () => undefined);
    setInterval(() => undefined, 1_000);
  }
}

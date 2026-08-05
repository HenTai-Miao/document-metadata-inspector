import { access, writeFile } from "node:fs/promises";

const [statePath, ...argumentsList] = process.argv.slice(2);
const pidIndex = argumentsList.indexOf("/PID");
const targetPid = Number.parseInt(argumentsList[pidIndex + 1] ?? "", 10);

if (statePath === undefined || !Number.isInteger(targetPid)) {
  process.exitCode = 2;
} else {
  try {
    await access(statePath);
    process.kill(-targetPid, "SIGKILL");
  } catch {
    await writeFile(statePath, "retry\n", "utf8");
    process.on("SIGTERM", () => undefined);
    setInterval(() => undefined, 1_000);
  }
}

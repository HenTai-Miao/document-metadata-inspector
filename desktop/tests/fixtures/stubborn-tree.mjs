import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";

const argumentsList = process.argv.slice(2);
const option = (name) => {
  const index = argumentsList.indexOf(name);
  return index === -1 ? undefined : argumentsList[index + 1];
};
const pidPath = option("--descendant-pid");
const rootPidPath = option("--root-pid");

if (pidPath === undefined || rootPidPath === undefined) {
  process.exitCode = 2;
} else {
  await writeFile(rootPidPath, String(process.pid), "utf8");
  const descendant = spawn(
    process.execPath,
    ["-e", "process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],
    { shell: false, stdio: "ignore", windowsHide: true },
  );
  if (descendant.pid === undefined) {
    process.exitCode = 2;
  } else {
    await writeFile(pidPath, String(descendant.pid), "utf8");
    process.on("SIGTERM", () => undefined);
    setInterval(() => undefined, 1_000);
  }
}

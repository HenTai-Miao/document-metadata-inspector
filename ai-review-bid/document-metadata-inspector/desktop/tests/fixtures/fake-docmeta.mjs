import { copyFile, readFile, writeFile } from "node:fs/promises";

const [sourceReport, delayText, argumentLogPath, ...cliArguments] = process.argv.slice(2);
const outputIndex = cliArguments.indexOf("--json");
const outputPath = outputIndex === -1 ? undefined : cliArguments[outputIndex + 1];
const delay = Number.parseInt(delayText ?? "0", 10);

if (
  sourceReport === undefined ||
  argumentLogPath === undefined ||
  outputPath === undefined ||
  !Number.isFinite(delay)
) {
  process.exitCode = 2;
} else {
  const inputManifestPath = cliArguments.at(-1);
  if (inputManifestPath !== undefined) {
    await writeFile(
      argumentLogPath,
      JSON.stringify({
        cliArguments,
        inputManifest: JSON.parse(await readFile(inputManifestPath, "utf8")),
      }),
      "utf8",
    );
  }
  const timer = setTimeout(async () => {
    await copyFile(sourceReport, outputPath);
    process.stdout.write('{"complete":true}\n');
  }, delay);
  process.once("SIGTERM", () => {
    clearTimeout(timer);
    process.exit(143);
  });
}

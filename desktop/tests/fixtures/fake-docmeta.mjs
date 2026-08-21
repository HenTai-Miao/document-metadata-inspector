import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const [sourceReport, delayText, argumentLogPath, configPath, ...cliArguments] =
  process.argv.slice(2);
const outputIndex = cliArguments.indexOf("--output");
const outputPath = outputIndex === -1 ? undefined : cliArguments[outputIndex + 1];
const inputManifestPath = cliArguments.at(-1);
const delay = Number.parseInt(delayText ?? "0", 10);

function observationValue(observation) {
  const value = observation.raw_value ?? observation.normalized_value;
  if (value === null || value === undefined) {
    return "";
  }
  return typeof value === "string" ? value : JSON.stringify(value);
}

function warningCount(document) {
  return (
    (document.warnings?.length ?? 0) +
    (document.parser_runs ?? []).reduce((total, run) => total + (run.warnings?.length ?? 0), 0) +
    (document.embedded_documents ?? []).reduce(
      (total, child) => total + (child.warnings?.length ?? 0),
      0,
    )
  );
}

function compactDocument(document) {
  return {
    source_path_sha256: document.source_path_sha256,
    display_name: document.display_name,
    declared_format: document.identity?.declared_format ?? "unknown",
    family: document.identity?.family ?? "unknown",
    status: document.status,
    observation_count: document.observations?.length ?? 0,
    parser_run_count: document.parser_runs?.length ?? 0,
    warning_count: warningCount(document),
    size_bytes: document.size_bytes ?? 0,
    sha256_prefix: document.sha256.slice(0, 12),
    parser_runs: (document.parser_runs ?? []).map((run) => ({
      name: run.parser_name,
      status: run.status,
      warning_count: run.warnings?.length ?? 0,
    })),
    key_fields: {
      author: "",
      created: "",
      modified: "",
      last_modified_by: "",
      company: "",
      template: "",
    },
  };
}

function compactMatch(match) {
  return {
    canonical_name: match.canonical_name,
    normalized_value: match.normalized_value,
    trace_kind: match.trace_kind ?? "document_environment_trace",
    field_names: match.field_names ?? [],
    raw_values: match.raw_values ?? [],
    evidence_count: match.evidence_count ?? 0,
    document_ids: match.document_ids ?? [],
  };
}

async function publishBundle(report, directory) {
  await mkdir(join(directory, "details"), { recursive: true });
  await mkdir(join(directory, "evidence"), { recursive: true });
  for (const document of report.documents) {
    const documentId = document.source_path_sha256;
    const observations = (document.observations ?? [])
      .map((observation) => ({
        label: observation.raw_name ?? observation.canonical_name ?? "未知字段",
        value: observationValue(observation),
      }))
      .filter((observation) => observation.value.length > 0);
    await writeFile(
      join(directory, "details", `${documentId}.json`),
      JSON.stringify({ schema_version: "1.0", document_id: documentId, observations }),
      "utf8",
    );
    await writeFile(
      join(directory, "evidence", `${documentId}.json`),
      JSON.stringify(document),
      "utf8",
    );
  }
  const warnings = report.warnings ?? [];
  const documents = report.documents.map(compactDocument);
  await writeFile(
    join(directory, "summary.json"),
    JSON.stringify({
      schema_version: "1.0",
      document_count: documents.length,
      complete_document_count: report.documents.filter((document) => document.status === "complete")
        .length,
      observation_count: report.documents.reduce(
        (total, document) => total + (document.observations?.length ?? 0),
        0,
      ),
      parser_run_count: report.documents.reduce(
        (total, document) => total + (document.parser_runs?.length ?? 0),
        0,
      ),
      warning_count:
        warnings.length +
        report.documents.reduce((total, document) => total + warningCount(document), 0),
      documents,
      matches: (report.matches ?? []).map(compactMatch),
      warnings,
    }),
    "utf8",
  );
}

if (
  sourceReport === undefined ||
  argumentLogPath === undefined ||
  configPath === undefined ||
  outputPath === undefined ||
  inputManifestPath === undefined ||
  !Number.isFinite(delay)
) {
  process.exitCode = 2;
} else {
  const manifestLines = (await readFile(inputManifestPath, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  const inputManifest = {
    schema_version: manifestLines[0]?.schema_version,
    documents: manifestLines.slice(1).map(({ type: _type, ...document }) => document),
  };
  await writeFile(argumentLogPath, JSON.stringify({ cliArguments, inputManifest }), "utf8");
  const report = JSON.parse(await readFile(sourceReport, "utf8"));
  const config = JSON.parse(await readFile(configPath, "utf8"));
  const timer = setTimeout(async () => {
    await publishBundle(report, outputPath);
    for (let index = 0; index < report.documents.length; index += 1) {
      process.stdout.write(
        `${JSON.stringify({ type: "progress", completed: index + 1, total: report.documents.length })}\n`,
      );
    }
    if (config.stdoutBytes > 0) {
      process.stdout.write(`${"x".repeat(config.stdoutBytes)}\n`);
    }
    if (config.stderrBytes > 0) {
      process.stderr.write(`${"y".repeat(config.stderrBytes)}\n`);
    }
    process.stdout.write(
      `${JSON.stringify({ type: "result", document_count: report.documents.length })}\n`,
    );
    process.exitCode = config.exitCode;
  }, delay);
  process.once("SIGTERM", () => {
    clearTimeout(timer);
    process.exit(143);
  });
}

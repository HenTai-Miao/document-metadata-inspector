import { dirname } from "node:path";

import { describe, expect, test } from "vitest";
import { discoverFolder } from "../src/main/folder-discovery";
import { ScanService } from "../src/main/scan-service";

const realFolder = process.env.DOCMETA_REAL_FOLDER;
const realRuntime = process.env.DOCMETA_REAL_RUNTIME;

describe.skipIf(realFolder === undefined || realRuntime === undefined)(
  "packaged runtime with public documents",
  () => {
    test("stops and restarts the packaged runtime before producing the real result", async () => {
      if (realFolder === undefined || realRuntime === undefined) {
        throw new Error("real integration environment is incomplete");
      }
      const stages: string[] = [];
      const selection = await discoverFolder(realFolder);
      const service = new ScanService({
        resolveRuntime: () => ({
          command: realRuntime,
          argsPrefix: [],
          source: "test",
          workingDirectory: dirname(realRuntime),
        }),
      });
      let markExtracting: (() => void) | undefined;
      const extracting = new Promise<void>((resolveExtracting) => {
        markExtracting = resolveExtracting;
      });
      const stoppedScan = service.start(selection, (progress) => {
        if (progress.stage === "extracting") {
          markExtracting?.();
        }
      });
      await extracting;
      const stoppedResult = expect(stoppedScan).rejects.toBeInstanceOf(Error);
      await expect(service.stop()).resolves.toBe(true);
      await stoppedResult;

      const result = await service.start(selection, (progress) => {
        stages.push(progress.stage);
      });

      expect(result).toMatchObject({
        documentCount: 8,
        completeDocumentCount: 8,
        observationCount: 1886,
        parserRunCount: 24,
      });
      expect(result.groups).toHaveLength(2);
      expect(result.groups.map((group) => group.documents.length)).toEqual([4, 4]);
      expect(result.personTraces).toEqual([]);
      expect(result.cautionTraces.every((trace) => !trace.fieldNames.includes("application"))).toBe(
        true,
      );
      expect(stages).toEqual(["preparing", "extracting", "comparing", "complete"]);
    }, 60_000);
  },
);

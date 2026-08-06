import { describe, expect, test } from "vitest";

import { connectionTracks } from "../src/renderer/render-result";
import type { TraceSummary } from "../src/shared/contracts";

function trace(
  id: string,
  tone: TraceSummary["tone"],
  groupIds: string[] = ["bidder-a", "bidder-b"],
): TraceSummary {
  return {
    id,
    tone,
    kind: tone === "danger" ? "person_trace" : "document_environment_trace",
    label: id,
    value: id,
    groupIds,
    documentIds: ["document-a", "document-b"],
    fieldNames: ["author"],
    evidenceCount: 2,
  };
}

describe("connectionTracks", () => {
  test("assigns distinct stable tracks to traces joining the same bidder pair", () => {
    const tracks = connectionTracks([
      trace("template", "caution"),
      trace("timestamp", "caution", ["bidder-b", "bidder-a"]),
      trace("author", "danger"),
    ]);

    expect(tracks.map((track) => track.traceIndex)).toEqual([0, 1, 2]);
    expect(tracks.every((track) => track.fromGroupId === "bidder-a")).toBe(true);
    expect(tracks.every((track) => track.toGroupId === "bidder-b")).toBe(true);
    expect(new Set(tracks.map((track) => track.offset)).size).toBe(3);
    expect(tracks[2]?.offset).toBeGreaterThan(tracks[1]?.offset ?? 0);
  });
});

import { describe, expect, test } from "vitest";

import { expectedExecutableSha256 } from "../checksum-manifest.mjs";

const HASH = "a".repeat(64);

describe("expectedExecutableSha256", () => {
  test("accepts exactly one executable record", () => {
    expect(expectedExecutableSha256(`${HASH}  docmeta\n`, "docmeta")).toBe(HASH);
  });

  test.each([
    `${HASH}  docmeta\n${"b".repeat(64)}  unrelated\n`,
    `${HASH}  nested/docmeta\n`,
    `${HASH}  nested\\docmeta\n`,
    "malformed\n",
    "",
  ])("rejects inconsistent manifest %j", (manifest) => {
    expect(() => expectedExecutableSha256(manifest, "docmeta")).toThrow(
      "Checksum manifest is invalid",
    );
  });
});

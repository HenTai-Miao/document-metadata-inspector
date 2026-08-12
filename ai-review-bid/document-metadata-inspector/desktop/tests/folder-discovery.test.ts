import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, test } from "vitest";

import { discoverFolder } from "../src/main/folder-discovery";

const temporaryDirectories: string[] = [];
const testDirectory = dirname(fileURLToPath(import.meta.url));

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

describe("discoverFolder", () => {
  test("has no fixed discovered-entry cutoff", async () => {
    const implementation = await readFile(
      join(testDirectory, "..", "src", "main", "folder-discovery.ts"),
      "utf8",
    );

    expect(implementation).not.toContain("MAX_DISCOVERED_ENTRIES");
    expect(implementation).not.toContain("50000 项安全上限");
  });
  test("treats each first-level directory as one bidder and ignores unsupported files", async () => {
    // A regression that flattens the tree would make files from one bidder conflict.
    const root = await mkdtemp(join(tmpdir(), "docmeta-folder-test-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "投标人甲", "技术文件"), { recursive: true });
    await mkdir(join(root, "投标人乙"), { recursive: true });
    await writeFile(join(root, "投标人甲", "技术文件", "方案.docx"), "docx");
    await writeFile(join(root, "投标人甲", "报价.xlsx"), "xlsx");
    await writeFile(join(root, "投标人乙", "投标文件.pdf"), "pdf");
    await writeFile(join(root, "投标人乙", "说明.txt"), "ignored");

    const selection = await discoverFolder(root);

    expect(selection.rootPath).toBe(await realpath(root));
    expect(selection.supportedFileCount).toBe(3);
    expect(selection.bidderCount).toBe(2);
    expect(selection.rootFileCount).toBe(0);
    expect(selection.ignoredFileCount).toBe(1);
    expect(selection.groups.map((group) => group.name)).toEqual(["投标人甲", "投标人乙"]);
    expect(selection.groups.map((group) => group.fileCount)).toEqual([2, 1]);
    expect(
      selection.groups.flatMap((group) => group.files.map((file) => file.relativePath)),
    ).toEqual(["投标人甲/报价.xlsx", "投标人甲/技术文件/方案.docx", "投标人乙/投标文件.pdf"]);
    expect(
      selection.groups.every((group) => group.files.every((file) => file.groupId === group.id)),
    ).toBe(true);
  });

  test("keeps root files scannable without counting them as a bidder", async () => {
    const root = await mkdtemp(join(tmpdir(), "docmeta-root-files-test-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "投标人甲"));
    await writeFile(join(root, "投标人甲", "投标文件.pdf"), "bidder");
    await writeFile(join(root, "补充说明.docx"), "root file");

    const selection = await discoverFolder(root);

    expect(selection.bidderCount).toBe(1);
    expect(selection.rootFileCount).toBe(1);
    expect(selection.groups.map((group) => group.kind)).toEqual(["bidder", "root-files"]);
  });

  test("canonicalizes parent symlinks exactly like the Python core", async () => {
    const temporaryRoot = await mkdtemp(join(tmpdir(), "docmeta-realpath-test-"));
    temporaryDirectories.push(temporaryRoot);
    const actualParent = join(temporaryRoot, "actual-parent");
    const aliasParent = join(temporaryRoot, "alias-parent");
    const root = join(actualParent, "4-投标文件");
    const document = join(root, "投标人甲", "投标文件.pdf");
    await mkdir(join(root, "投标人甲"), { recursive: true });
    await writeFile(document, "pdf");
    try {
      await symlink(actualParent, aliasParent, "dir");
    } catch {
      return;
    }

    const selection = await discoverFolder(join(aliasParent, "4-投标文件"));
    const canonicalDocument = await realpath(document);

    expect(selection.rootPath).toBe(await realpath(root));
    expect(selection.groups[0]?.files[0]?.sourcePathSha256).toBe(
      createHash("sha256").update(canonicalDocument, "utf8").digest("hex"),
    );
  });
});

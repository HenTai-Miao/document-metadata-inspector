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

  test("skips the top-level price comparison summary and keeps nested supplier files", async () => {
    // Given: a quotation package with five suppliers and one procurement-side summary folder.
    const root = await mkdtemp(join(tmpdir(), "docmeta-quotation-folder-test-"));
    temporaryDirectories.push(root);
    const suppliers = [
      "北京天泽世纪广告有限责任公司",
      "北京悦动双成科技有限公司",
      "央广聚力文化传媒(北京)有限公司",
      "中晨基业（北京）建设工程有限公司",
      "中腾世合广告传媒（北京）有限公司",
    ];
    for (const supplier of suppliers) {
      await mkdir(join(root, supplier, "应答文件"), { recursive: true });
      await mkdir(join(root, supplier, "报价文件"), { recursive: true });
      await writeFile(join(root, supplier, "应答文件", `${supplier}-应答文件.pdf`), "response");
      await writeFile(join(root, supplier, "报价文件", "报价单.pdf"), "quotation");
    }
    await mkdir(join(root, "中晨基业（北京）建设工程有限公司", "报价附件"), {
      recursive: true,
    });
    await writeFile(
      join(root, "中晨基业（北京）建设工程有限公司", "报价附件", "报价表.xlsx"),
      "quotation attachment",
    );
    await writeFile(
      join(root, "中晨基业（北京）建设工程有限公司", "报价附件", "设备清单.xlsx"),
      "equipment list",
    );
    await mkdir(join(root, "比价分析表"));
    await writeFile(join(root, "比价分析表", "比价分析表.pdf"), "summary");
    await writeFile(join(root, ".DS_Store"), "ignored");

    // When: the quotation package root is selected.
    const selection = await discoverFolder(root);

    // Then: only supplier documents enter the scan and comparison manifest.
    expect(selection.bidderCount).toBe(5);
    expect(selection.supportedFileCount).toBe(12);
    expect(selection.ignoredFileCount).toBe(1);
    expect(selection.groups.map((group) => group.name)).toEqual([
      "北京天泽世纪广告有限责任公司",
      "北京悦动双成科技有限公司",
      "央广聚力文化传媒(北京)有限公司",
      "中晨基业（北京）建设工程有限公司",
      "中腾世合广告传媒（北京）有限公司",
    ]);
    expect(selection.groups.map((group) => group.fileCount)).toEqual([2, 2, 2, 4, 2]);
    expect(
      selection.groups.flatMap((group) => group.files.map((file) => file.relativePath)),
    ).not.toContain("比价分析表/比价分析表.pdf");
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

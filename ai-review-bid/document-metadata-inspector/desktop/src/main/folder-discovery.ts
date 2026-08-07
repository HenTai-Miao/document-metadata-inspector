import { createHash } from "node:crypto";
import { lstat, readdir, realpath } from "node:fs/promises";
import { basename, extname, relative, resolve, sep } from "node:path";

import {
  type FolderGroup,
  type FolderSelection,
  type SelectedDocument,
  type SelectedFolderManifest,
  SUPPORTED_EXTENSIONS,
} from "../shared/contracts";

const MAX_DISCOVERED_ENTRIES = 50_000;
const ROOT_GROUP_ID = "root-files";
const chineseCollator = new Intl.Collator("zh-CN", {
  numeric: true,
  sensitivity: "base",
});

interface WalkedFile {
  absolutePath: string;
  relativePath: string;
  sizeBytes: number;
  supported: boolean;
}

function sha256Text(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function portableRelativePath(value: string): string {
  return value.split(sep).join("/");
}

async function walkFiles(rootPath: string): Promise<WalkedFile[]> {
  const files: WalkedFile[] = [];
  const pending = [rootPath];
  let visitedEntries = 0;

  while (pending.length > 0) {
    const directory = pending.pop();
    if (directory === undefined) {
      break;
    }
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => chineseCollator.compare(right.name, left.name));
    for (const entry of entries) {
      visitedEntries += 1;
      if (visitedEntries > MAX_DISCOVERED_ENTRIES) {
        throw new Error("所选目录包含的项目过多，已超过 50000 项安全上限");
      }
      if (entry.isSymbolicLink()) {
        continue;
      }
      const absolutePath = resolve(directory, entry.name);
      if (entry.isDirectory()) {
        pending.push(absolutePath);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      const metadata = await lstat(absolutePath);
      const extension = extname(entry.name).toLocaleLowerCase("en-US");
      files.push({
        absolutePath,
        relativePath: portableRelativePath(relative(rootPath, absolutePath)),
        sizeBytes: metadata.size,
        supported: SUPPORTED_EXTENSIONS.has(extension),
      });
    }
  }
  return files.sort((left, right) =>
    chineseCollator.compare(left.relativePath, right.relativePath),
  );
}

function groupNameFor(
  relativePath: string,
): Pick<FolderGroup, "id" | "kind" | "name" | "relativePath"> {
  const [topLevel, ...rest] = relativePath.split("/");
  if (topLevel === undefined || rest.length === 0) {
    return { id: ROOT_GROUP_ID, kind: "root-files", name: "根目录文件", relativePath: "." };
  }
  return {
    id: `bidder-${sha256Text(topLevel).slice(0, 16)}`,
    kind: "bidder",
    name: topLevel,
    relativePath: topLevel,
  };
}

/**
 * Fuzzy-search for a subfolder whose name contains "投标" (bidding)
 * but NOT "投标人" (which would be a bidder folder, not a container).
 * Searches only direct children of the given directory (one level deep).
 * Returns the resolved path if found, otherwise returns the original directory.
 */
async function findBidSubfolder(dir: string): Promise<string> {
  try {
    const entries = await readdir(dir, { withFileTypes: true });
    const match = entries.find(
      (e) =>
        e.isDirectory() &&
        !e.isSymbolicLink() &&
        e.name.includes("投标") &&
        !e.name.includes("投标人"),
    );
    if (match !== undefined) {
      return resolve(dir, match.name);
    }
  } catch {
    // ignore errors, fall through to original directory
  }
  return dir;
}

export async function discoverFolder(requestedPath: string): Promise<SelectedFolderManifest> {
  const requestedRoot = resolve(requestedPath);
  const requestedMetadata = await lstat(requestedRoot);
  if (!requestedMetadata.isDirectory() || requestedMetadata.isSymbolicLink()) {
    throw new Error("请选择一个普通文件夹，不能选择文件或符号链接");
  }

  // If the selected folder contains a subfolder named with "投标",
  // drill into it automatically.
  const bidSubfolder = await findBidSubfolder(requestedRoot);
  const rootPath = await realpath(bidSubfolder);

  const walked = await walkFiles(rootPath);
  const groups = new Map<string, FolderGroup>();
  let totalSizeBytes = 0;
  let ignoredFileCount = 0;

  for (const file of walked) {
    if (!file.supported) {
      ignoredFileCount += 1;
      continue;
    }
    const groupIdentity = groupNameFor(file.relativePath);
    let group = groups.get(groupIdentity.id);
    if (group === undefined) {
      group = { ...groupIdentity, fileCount: 0, files: [] };
      groups.set(groupIdentity.id, group);
    }
    const extension = extname(file.absolutePath).toLocaleLowerCase("en-US");
    const sourcePathSha256 = sha256Text(file.absolutePath);
    const document: SelectedDocument = {
      id: sourcePathSha256,
      sourcePathSha256,
      groupId: group.id,
      name: basename(file.absolutePath),
      relativePath: file.relativePath,
      extension: extension.slice(1),
      sizeBytes: file.sizeBytes,
    };
    group.files.push(document);
    group.fileCount += 1;
    totalSizeBytes += file.sizeBytes;
  }

  const orderedGroups = [...groups.values()]
    .map((group) => ({
      ...group,
      files: group.files.sort((left, right) =>
        chineseCollator.compare(left.relativePath, right.relativePath),
      ),
    }))
    .sort((left, right) => {
      if (left.id === ROOT_GROUP_ID) {
        return 1;
      }
      if (right.id === ROOT_GROUP_ID) {
        return -1;
      }
      return chineseCollator.compare(left.name, right.name);
    });

  return {
    rootPath,
    rootName: basename(rootPath),
    bidderCount: orderedGroups.filter((group) => group.kind === "bidder").length,
    rootFileCount: orderedGroups.find((group) => group.kind === "root-files")?.fileCount ?? 0,
    supportedFileCount: orderedGroups.reduce((total, group) => total + group.fileCount, 0),
    ignoredFileCount,
    totalSizeBytes,
    groups: orderedGroups,
  };
}

export function publicFolderSelection(manifest: SelectedFolderManifest): FolderSelection {
  const { rootPath: _privateRootPath, ...selection } = manifest;
  return selection;
}

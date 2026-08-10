import type { ScanResult } from "../shared/contracts";

export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className !== undefined) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

export function testId(node: HTMLElement, value: string): void {
  node.dataset.testid = value;
}

export function actionButton(
  label: string,
  variant: "primary" | "secondary" | "danger" | "ghost",
  id: string,
  onClick: () => void | Promise<void>,
): HTMLButtonElement {
  const button = element("button", `btn btn--${variant}`, label);
  button.type = "button";
  testId(button, id);
  button.addEventListener("click", () => void onClick());
  return button;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

// ── Shared report helpers ─────────────────────────────────────────

/** Map groupId → group name (company name). */
export function buildGroupNames(result: ScanResult): Map<string, string> {
  const names = new Map<string, string>();
  for (const group of result.groups) {
    names.set(group.id, group.name);
  }
  return names;
}

/** Normalize a field name to a lowercase alphanumeric key. */
export function normFieldKey(raw: string): string {
  return raw.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Spreadsheet-style label: A, B, … Z, A1, B1, … for bidder indexing. */
export function bidderLabel(index: number): string {
  if (index < 26) {
    return String.fromCharCode(65 + index);
  }
  const letter = String.fromCharCode(65 + (index % 26));
  const round = Math.floor(index / 26);
  return `${letter}${round}`;
}

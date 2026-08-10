import type { ScanResult, TraceSummary } from "../shared/contracts";
import { element, normFieldKey, testId } from "./dom";

// ════════════════════════════════════════════════════════════════
// Helpers: labels, formatting
// ════════════════════════════════════════════════════════════════

const LABELS: Record<string, string> = {
  author: "作者",
  title: "标题",
  subject: "主题",
  keywords: "关键词",
  creator: "创建程序",
  producer: "生成器",
  creationdate: "创建时间",
  moddate: "修改时间",
  created: "创建时间",
  modified: "修改时间",
  create_date: "创建时间",
  modify_date: "修改时间",
  createdat: "创建时间",
  modifiedat: "修改时间",
  updatedat: "修改时间",
  lastmodifiedby: "最后修改者",
  last_modified_by: "最后修改者",
  lastsavedby: "最后保存者",
  last_saved_by: "最后保存者",
  revision: "修订版本",
  category: "分类",
  description: "描述",
  comments: "备注",
  comment: "备注",
  company: "公司",
  manager: "经理",
  application: "应用程序",
  applicationname: "应用程序名称",
  application_name: "应用程序名称",
  appversion: "应用版本",
  app_version: "应用版本",
  template: "模板",
  totaltime: "总编辑时间",
  total_time: "总编辑时间",
  pages: "页数",
  page_count: "页数",
  words: "字数",
  word_count: "字数",
  characters: "字符数",
  character_count: "字符数",
  characterswithspaces: "含空格字符数",
  character_count_with_spaces: "含空格字符数",
  paragraphs: "段落数",
  paragraph_count: "段落数",
  lines: "行数",
  line_count: "行数",
  slides: "幻灯片数",
  slide_count: "幻灯片数",
  language: "语言",
  version: "版本",
  contentstatus: "内容状态",
  content_status: "内容状态",
  identifier: "标识符",
  source: "来源",
  format: "格式",
  type: "类型",
  relation: "关联",
  coverage: "覆盖范围",
  rights: "权限",
  contributor: "贡献者",
  publisher: "发布者",
  date: "日期",
  trapped: "陷印标记",
  encryption: "加密",
  password: "密码",
  filesize: "文件大小",
  mimetype: "MIME类型",
  contenttype: "内容类型",
  filepath: "文件路径",
  filename: "文件名",
  name: "文件名",
  sha256: "SHA256",
  hash: "哈希值",
  md5: "MD5",
  lastprinted: "最后打印",
  printdate: "打印日期",
  edittime: "编辑时长",
  editingduration: "编辑时长",
  sheets: "工作表数",
  sheet_count: "工作表数",
  cpg: "代码页",
  codepage: "代码页",
};

export function tField(raw: string): string {
  return LABELS[normFieldKey(raw)] ?? raw;
}

/** Local-time "YYYY-MM-DD HH:MM" from an ISO string. */
function fmtScanTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Local-time "YYYY-MM-DD" from an ISO string. */
function fmtScanDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return new Date().toISOString().slice(0, 10);
  const p = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// ════════════════════════════════════════════════════════════════
// Connection tracks (kept for tests)
// ════════════════════════════════════════════════════════════════

export interface ConnectionTrack {
  traceIndex: number;
  fromGroupId: string;
  toGroupId: string;
  offset: number;
}

export function connectionTracks(traces: TraceSummary[]): ConnectionTrack[] {
  const gap = 10;
  const edges = traces.flatMap((trace, traceIndex) => {
    const from = trace.groupIds[0];
    if (from === undefined) return [];
    return trace.groupIds.slice(1).map((to) => {
      const [a, b] = from.localeCompare(to) <= 0 ? [from, to] : [to, from];
      return { traceIndex, fromGroupId: a, toGroupId: b, key: [a, b].sort().join("\0") };
    });
  });
  const totals = new Map<string, number>();
  for (const e of edges) totals.set(e.key, (totals.get(e.key) ?? 0) + 1);
  const pos = new Map<string, number>();
  return edges.map((e) => {
    const p = pos.get(e.key) ?? 0;
    pos.set(e.key, p + 1);
    const total = totals.get(e.key) ?? 1;
    return {
      traceIndex: e.traceIndex,
      fromGroupId: e.fromGroupId,
      toGroupId: e.toGroupId,
      offset: (p - (total - 1) / 2) * gap,
    };
  });
}

// ════════════════════════════════════════════════════════════════
// Report helpers
// ════════════════════════════════════════════════════════════════

const PROBLEM_LABEL_DEFINITIONS = [
  { key: "author", label: "创建人检测" },
  { key: "last_modified_by", label: "修改人检测" },
  { key: "comment_author", label: "批注人检测" },
  { key: "revision_author", label: "修订人检测" },
  { key: "manager", label: "经理检测" },
  { key: "company", label: "公司检测" },
  { key: "signer_identity", label: "签名人检测" },
  { key: "username_path_trace", label: "路径用户名检测" },
  { key: "template", label: "模板检测" },
  { key: "created_at", label: "创建时间检测" },
  { key: "modified_at", label: "修改时间检测" },
] as const;

const PROBLEM_LABEL_KEY_BY_FIELD = new Map<string, string>(
  PROBLEM_LABEL_DEFINITIONS.map((definition) => [normFieldKey(definition.key), definition.key]),
);

const PROBLEM_LABEL_ALIASES: Readonly<Record<string, string>> = {
  annotationauthor: "comment_author",
  signaturesignername: "signer_identity",
};

export type ProblemLabelStatus = "risk" | "safe";

export interface ProblemPairSide {
  companyId: string;
  company: string;
  files: string[];
}

export interface ProblemCompanyPair {
  id: string;
  left: ProblemPairSide;
  right: ProblemPairSide;
}

export interface ProblemHitValue {
  value: string;
  pairs: ProblemCompanyPair[];
  relationCount: number;
  missingEvidence: boolean;
}

export interface ProblemLabelSection {
  key: string;
  label: string;
  status: ProblemLabelStatus;
  hits: ProblemHitValue[];
  relationCount: number;
}

export interface ProblemLabelReportModel {
  sections: ProblemLabelSection[];
  riskCount: number;
  safeCount: number;
  relationCount: number;
}

interface MutableProblemHit {
  value: string;
  pairs: Map<string, ProblemCompanyPair>;
}

function problemLabelKey(raw: string): string | undefined {
  const normalized = normFieldKey(raw);
  return PROBLEM_LABEL_ALIASES[normalized] ?? PROBLEM_LABEL_KEY_BY_FIELD.get(normalized);
}

function mergeFiles(current: string[], incoming: string[]): string[] {
  const merged = [...current];
  const seen = new Set(current);
  for (const file of incoming) {
    if (!seen.has(file)) {
      seen.add(file);
      merged.push(file);
    }
  }
  return merged;
}

function mergeProblemPair(
  pairs: Map<string, ProblemCompanyPair>,
  incoming: ProblemCompanyPair,
): void {
  const current = pairs.get(incoming.id);
  if (current === undefined) {
    pairs.set(incoming.id, incoming);
    return;
  }
  current.left.files = mergeFiles(current.left.files, incoming.left.files);
  current.right.files = mergeFiles(current.right.files, incoming.right.files);
}

export function buildProblemLabelReportModel(result: ScanResult): ProblemLabelReportModel {
  const bidderGroups = result.groups.filter((group) => group.kind === "bidder");
  const hitsByLabel = new Map<string, Map<string, MutableProblemHit>>(
    PROBLEM_LABEL_DEFINITIONS.map((definition) => [definition.key, new Map()]),
  );

  for (const trace of [...result.personTraces, ...result.cautionTraces]) {
    const traceGroupIds = new Set(trace.groupIds);
    const traceDocumentIds = new Set(trace.documentIds);
    const involvedGroups = bidderGroups.filter((group) => traceGroupIds.has(group.id));
    const filesByGroup = new Map(
      involvedGroups.map((group) => [
        group.id,
        group.documents
          .filter((document) => traceDocumentIds.has(document.id))
          .map((document) => document.name),
      ]),
    );
    const tracePairs: ProblemCompanyPair[] = [];

    for (let leftIndex = 0; leftIndex < involvedGroups.length; leftIndex += 1) {
      const leftGroup = involvedGroups[leftIndex];
      if (leftGroup === undefined) {
        continue;
      }
      for (let rightIndex = leftIndex + 1; rightIndex < involvedGroups.length; rightIndex += 1) {
        const rightGroup = involvedGroups[rightIndex];
        if (rightGroup === undefined) {
          continue;
        }
        tracePairs.push({
          id: `${leftGroup.id}\0${rightGroup.id}`,
          left: {
            companyId: leftGroup.id,
            company: leftGroup.name,
            files: filesByGroup.get(leftGroup.id) ?? [],
          },
          right: {
            companyId: rightGroup.id,
            company: rightGroup.name,
            files: filesByGroup.get(rightGroup.id) ?? [],
          },
        });
      }
    }

    const labelKeys = [
      ...new Set(
        trace.fieldNames.flatMap((fieldName) => {
          const key = problemLabelKey(fieldName);
          return key === undefined ? [] : [key];
        }),
      ),
    ];

    for (const key of labelKeys) {
      const hits = hitsByLabel.get(key);
      if (hits === undefined) {
        continue;
      }
      let hit = hits.get(trace.value);
      if (hit === undefined) {
        hit = { value: trace.value, pairs: new Map() };
        hits.set(trace.value, hit);
      }
      for (const pair of tracePairs) {
        mergeProblemPair(hit.pairs, pair);
      }
    }
  }

  const sections = PROBLEM_LABEL_DEFINITIONS.map((definition): ProblemLabelSection => {
    const mutableHits = hitsByLabel.get(definition.key) ?? new Map();
    const hits = [...mutableHits.values()].map((hit): ProblemHitValue => {
      const pairs = [...hit.pairs.values()];
      return {
        value: hit.value,
        pairs,
        relationCount: pairs.length,
        missingEvidence: pairs.length === 0,
      };
    });
    return {
      key: definition.key,
      label: definition.label,
      status: hits.length > 0 ? "risk" : "safe",
      hits,
      relationCount: hits.reduce((total, hit) => total + hit.relationCount, 0),
    };
  });
  const riskCount = sections.filter((section) => section.status === "risk").length;

  return {
    sections,
    riskCount,
    safeCount: sections.length - riskCount,
    relationCount: sections.reduce((total, section) => total + section.relationCount, 0),
  };
}

// ════════════════════════════════════════════════════════════════
// Report sections
// ════════════════════════════════════════════════════════════════

function riskMeta(result: ScanResult): string {
  const time = result.scannedAt ? fmtScanTime(result.scannedAt) : "";
  return `${result.rootName} · 核验时间 ${time} · 离线分析`;
}

function buildProblemSummary(model: ProblemLabelReportModel): HTMLElement {
  const summary = element("div", "pl-badges");
  summary.append(
    element("span", "pl-badge pl-badge--risk", `有风险 ${model.riskCount}`),
    element("span", "pl-badge pl-badge--safe", `无风险 ${model.safeCount}`),
  );
  if (model.relationCount > 0) {
    summary.append(element("span", "pl-relation-note", `${model.relationCount} 组公司关系`));
  }
  return summary;
}

function buildProblemFileSide(side: ProblemPairSide): HTMLElement {
  const container = element("div", "pl-file-side");
  testId(container, "problem-company-files");
  container.append(element("span", "pl-company-name", `${side.company} 的文件`));
  const files = element("div", "pl-files");
  if (side.files.length === 0) {
    files.append(element("span", "pl-file-empty", "暂无可显示文件证据"));
  } else {
    for (const filename of side.files) {
      const file = element("span", "pl-file", filename);
      testId(file, "problem-evidence-file");
      files.append(file);
    }
  }
  container.append(files);
  return container;
}

function buildProblemPair(pair: ProblemCompanyPair): HTMLElement {
  const row = element("div", "pl-pair-row");
  testId(row, "problem-company-pair");
  row.append(
    element("span", "pl-pair-name", `${pair.left.company} ↔ ${pair.right.company}`),
    buildProblemFileSide(pair.left),
    buildProblemFileSide(pair.right),
  );
  return row;
}

function buildProblemHit(hit: ProblemHitValue): HTMLElement {
  const block = element("section", "pl-value-block");
  const heading = element("div", "pl-value-head");
  const valueGroup = element("div", "pl-hit-group");
  const value = element("span", "pl-hit-value", hit.value);
  testId(value, "problem-hit-value");
  valueGroup.append(element("span", "pl-hit-label", "命中值"), value);
  heading.append(valueGroup, element("span", "pl-value-count", `${hit.relationCount} 组公司关系`));
  block.append(heading);

  if (hit.pairs.length === 0 && hit.missingEvidence) {
    block.append(element("p", "pl-evidence-missing", "风险关系缺少可显示的投标人文件证据"));
  } else {
    for (const pair of hit.pairs) {
      block.append(buildProblemPair(pair));
    }
  }
  return block;
}

function buildProblemSection(section: ProblemLabelSection): HTMLElement {
  const article = element("article", `pl-section pl-section--${section.status}`);
  testId(article, "problem-label-section");

  const heading = element("header", "pl-section-head");
  const titleGroup = element("div", "pl-section-title-group");
  const title = element("h2", "pl-section-title", `问题标签：${section.label}`);
  testId(title, "problem-label-name");
  const status = element(
    "span",
    `pl-status pl-status--${section.status}`,
    section.status === "risk" ? "有风险" : "无风险",
  );
  testId(status, "problem-label-status");
  titleGroup.append(title, status);
  heading.append(
    titleGroup,
    element(
      "span",
      "pl-section-count",
      `${section.hits.length} 个命中值 · ${section.relationCount} 组公司关系`,
    ),
  );
  article.append(heading);

  if (section.status === "safe") {
    const safe = element("div", "pl-safe-result");
    testId(safe, "problem-safe-result");
    safe.append(
      element("span", "pl-safe-mark", "✓"),
      element("strong", "pl-safe-title", "无风险"),
      element("span", "pl-safe-copy", "未发现跨公司相同值"),
    );
    article.append(safe);
  } else {
    for (const hit of section.hits) {
      article.append(buildProblemHit(hit));
    }
  }
  return article;
}

function reportSignature(result: ScanResult): HTMLElement {
  const sign = element("div", "r-sign");
  const dateStr = result.scannedAt
    ? fmtScanDate(result.scannedAt)
    : fmtScanDate(new Date().toISOString());
  const reportId = `RV-${dateStr.replace(/-/g, "")}-001`;

  sign.append(
    element("span", undefined, "核验人：审计员"),
    element("span", undefined, `核验日期：${dateStr}`),
    element("span", undefined, `报告编号：${reportId}`),
  );
  return sign;
}

// ════════════════════════════════════════════════════════════════
// Main render
// ════════════════════════════════════════════════════════════════

export function renderResult(result: ScanResult): HTMLElement {
  const main = element("div", "main-scroll report-scroll");
  testId(main, "result-page");
  const wrap = element("div", "pl-wrap");
  const model = buildProblemLabelReportModel(result);
  const header = element("header", "pl-header");
  const summary = element("h1", "pl-summary", `${model.sections.length} 类问题标签`);
  testId(summary, "problem-label-summary");
  header.append(
    element("p", "pl-eyebrow", "核验结果 · 全部检查标签"),
    summary,
    element("p", "pl-meta", riskMeta(result)),
    buildProblemSummary(model),
  );

  const listHeading = element("div", "pl-list-heading");
  listHeading.append(
    element("h2", "pl-list-title", "全部检查标签"),
    element("span", "pl-list-note", "有风险展示完整证据 · 无风险展示核验结论"),
  );
  const list = element("div", "pl-list");
  for (const section of model.sections) {
    list.append(buildProblemSection(section));
  }

  wrap.append(header, listHeading, list, reportSignature(result));
  main.append(wrap);
  return main;
}

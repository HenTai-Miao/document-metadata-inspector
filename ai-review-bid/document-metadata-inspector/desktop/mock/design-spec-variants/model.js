(() => {
  /** @typedef {"guided" | "verdict" | "matrix"} Variant */
  /** @typedef {"landing" | "empty" | "ready" | "scanning" | "stopped" | "failed" | "report" | "metadata"} View */
  /** @typedef {"all" | "danger" | "caution"} ReportFilter */
  /**
   * @typedef {object} PrototypeState
   * @property {Variant} variant
   * @property {View} view
   * @property {object | null} selection
   * @property {{stage: string, message: string, percent: number, completedFiles: number}} progress
   * @property {ReportFilter} reportFilter
   * @property {{bidderId: string, query: string, duplicatesOnly: boolean}} metadataFilters
   * @property {string | null} expandedTraceId
   * @property {string | null} selectedEvidenceId
   * @property {string} primary
   * @property {string | null} error
   */

  const bidders = [
    { id: "bidder-a", name: "华远建设" },
    { id: "bidder-b", name: "启明工程" },
    { id: "bidder-c", name: "中筑科技" },
    { id: "bidder-d", name: "新科咨询" },
  ];

  const documentNames = ["技术方案.docx", "报价.xlsx", "施工组织.pdf", "授权书.docx"];
  const documents = bidders.flatMap((bidder) =>
    documentNames.map((name, index) => ({
      id: `${bidder.id}-document-${index + 1}`,
      bidderId: bidder.id,
      bidderName: bidder.name,
      name,
      format: name.split(".").at(-1).toUpperCase(),
      isDuplicate: index === 0 && bidder.id !== "bidder-d",
    })),
  );

  const groups = bidders.map((bidder) => ({
    id: bidder.id,
    name: bidder.name,
    documentIds: documents
      .filter((document) => document.bidderId === bidder.id)
      .map((document) => document.id),
  }));

  const traces = [
    {
      id: "trace-author-wang-lei",
      tone: "danger",
      title: "作者信息一致",
      summary: "华远建设与启明工程的技术方案作者均为王磊。",
      evidenceIds: ["bidder-a-document-1", "bidder-b-document-1"],
    },
    {
      id: "trace-modifier-zhangmin",
      tone: "danger",
      title: "最后修改人一致",
      summary: "中筑科技与新科咨询的文件最后修改人均为 zhangmin。",
      evidenceIds: ["bidder-c-document-2", "bidder-d-document-2"],
    },
    {
      id: "trace-shared-template",
      tone: "caution",
      title: "共用模板痕迹",
      summary: "多个技术方案保留相同模板标识。",
      evidenceIds: ["bidder-a-document-1", "bidder-c-document-1"],
    },
    {
      id: "trace-created-within-87-seconds",
      tone: "caution",
      title: "创建时间接近",
      summary: "两份报价文件的创建时间相差 87 秒。",
      evidenceIds: ["bidder-a-document-2", "bidder-b-document-2"],
    },
    {
      id: "trace-matching-application-version",
      tone: "caution",
      title: "应用程序版本相同",
      summary: "多个文件记录了匹配的应用程序和版本。",
      evidenceIds: ["bidder-b-document-3", "bidder-d-document-3"],
    },
  ];

  const selection = {
    rootName: "演示项目",
    bidderCount: 4,
    fileCount: 16,
    ignoredCount: 0,
    boundaryWarning: "",
    files: documents.map((document) => ({
      name: document.name,
      bidderId: document.bidderId,
      bidderName: document.bidderName,
    })),
  };

  const demoProject = deepFreeze({
    groups,
    documents,
    observationCount: 148,
    traces,
    selection,
  });

  const variants = new Set(["guided", "verdict", "matrix"]);
  const reportFilters = new Set(["all", "danger", "caution"]);
  const supportedExtensions = new Set([
    "pdf",
    "doc",
    "docx",
    "docm",
    "dot",
    "dotx",
    "dotm",
    "xls",
    "xlsx",
    "xlsm",
    "xlsb",
    "xlt",
    "xltx",
    "xltm",
  ]);

  /** @param {string} hash @returns {PrototypeState} */
  function createInitialState(hash) {
    const variant = String(hash || "").replace(/^#/, "");
    return {
      variant: variants.has(variant) ? variant : "guided",
      view: "landing",
      selection: null,
      progress: {
        stage: "",
        message: "",
        percent: 0,
        completedFiles: 0,
      },
      reportFilter: "all",
      metadataFilters: { bidderId: "", query: "", duplicatesOnly: false },
      expandedTraceId: null,
      selectedEvidenceId: null,
      primary: "select-folder",
      error: null,
    };
  }

  /** @param {object} state @param {object} action @returns {PrototypeState} */
  function reduce(state, action) {
    if (!state || !action || typeof action.type !== "string") return state;

    switch (action.type) {
      case "SET_VARIANT":
        return variants.has(action.variant) ? { ...state, variant: action.variant } : state;
      case "SET_VIEW":
        return action.view === "metadata" && state.view === "report"
          ? { ...state, view: action.view }
          : state;
      case "SET_SELECTION": {
        if (!action.selection || typeof action.selection.fileCount !== "number") {
          return state;
        }
        return action.selection.fileCount === 0
          ? {
              ...state,
              selection: action.selection,
              view: "empty",
              error: "未发现支持的 PDF、Word 或 Excel 文档",
            }
          : { ...state, selection: action.selection, view: "ready", error: null };
      }
      case "SET_REPORT_FILTER":
        return reportFilters.has(action.reportFilter)
          ? { ...state, reportFilter: action.reportFilter }
          : state;
      case "SET_METADATA_FILTERS": {
        const filters = action.metadataFilters;
        if (
          !filters ||
          typeof filters.bidderId !== "string" ||
          typeof filters.query !== "string" ||
          typeof filters.duplicatesOnly !== "boolean"
        ) {
          return state;
        }
        return { ...state, metadataFilters: { ...filters } };
      }
      case "SET_EXPANDED_TRACE":
        return typeof action.traceId === "string" || action.traceId === null
          ? { ...state, expandedTraceId: action.traceId }
          : state;
      case "SET_SELECTED_EVIDENCE":
        return typeof action.evidenceId === "string" || action.evidenceId === null
          ? { ...state, selectedEvidenceId: action.evidenceId }
          : state;
      case "START_SCAN":
        return startScan(state, ["ready", "stopped", "failed"]);
      case "RETRY_SCAN":
        return startScan(state, ["failed"]);
      case "SCAN_PROGRESS":
        return state.view === "scanning" && validProgress(action.progress)
          ? { ...state, progress: { ...action.progress } }
          : state;
      case "STOP_SCAN":
        return state.view === "scanning" ? { ...state, view: "stopped" } : state;
      case "COMPLETE_SCAN":
        return state.view === "scanning"
          ? {
              ...state,
              view: "report",
              progress: {
                stage: "complete",
                message: "扫描完成",
                percent: 100,
                completedFiles: state.selection.fileCount,
              },
            }
          : state;
      case "FAIL_SCAN":
        return state.view === "scanning" && typeof action.error === "string"
          ? { ...state, view: "failed", error: action.error }
          : state;
      default:
        return state;
    }
  }

  /** @param {ArrayLike<{name?: string, webkitRelativePath?: string, size?: number}>} files */
  function selectionFromFiles(files) {
    const allFiles = Array.from(files || []);
    const accepted = allFiles.filter((file) => supportedFile(file.name || ""));
    const rootName = rootFromFiles(allFiles);
    const bidderGroups = new Map();
    const rootFiles = [];
    const selectedFiles = accepted.map((file, index) => {
      const path = pathParts(file.webkitRelativePath || "");
      const bidderName = path.length > 2 ? path[1] : "";
      const selectedFile = {
        id: `selected-document-${index + 1}`,
        name: file.name || "",
        relativePath: file.webkitRelativePath || file.name || "",
        bidderName,
        size: Number(file.size) || 0,
      };
      if (bidderName) {
        const group = bidderGroups.get(bidderName) || {
          id: `bidder-${bidderGroups.size + 1}`,
          name: bidderName,
          files: [],
        };
        group.files.push(selectedFile);
        bidderGroups.set(bidderName, group);
      } else {
        rootFiles.push(selectedFile);
      }
      return selectedFile;
    });
    return {
      rootName,
      bidderCount: bidderGroups.size,
      fileCount: accepted.length,
      ignoredCount: allFiles.length - accepted.length,
      boundaryWarning:
        accepted.length > 0 && bidderGroups.size === 0 && rootFiles.length > 0
          ? "所选根目录中包含文件，未发现投标人目录。"
          : "",
      groups: Array.from(bidderGroups.values()),
      files: selectedFiles.slice(0, 500),
    };
  }

  /** @param {PrototypeState} state */
  function visibleTraces(state) {
    if (!state?.selection) return [];
    return state.reportFilter === "all"
      ? demoProject.traces
      : demoProject.traces.filter((trace) => trace.tone === state.reportFilter);
  }

  /** @param {PrototypeState} state */
  function visibleDocuments(state) {
    if (!state?.selection) return [];
    const filters = state.metadataFilters;
    if (!filters) return demoProject.documents;
    const query = filters.query.trim().toLocaleLowerCase();
    return demoProject.documents.filter((document) => {
      const matchesBidder = !filters.bidderId || document.bidderId === filters.bidderId;
      const matchesDuplicate = !filters.duplicatesOnly || document.isDuplicate;
      const matchesQuery =
        !query ||
        document.name.toLocaleLowerCase().includes(query) ||
        document.bidderName.toLocaleLowerCase().includes(query);
      return matchesBidder && matchesDuplicate && matchesQuery;
    });
  }

  function validProgress(progress) {
    return (
      progress &&
      typeof progress.stage === "string" &&
      typeof progress.message === "string" &&
      Number.isFinite(progress.percent) &&
      Number.isFinite(progress.completedFiles)
    );
  }

  function startScan(state, views) {
    return state.selection && views.includes(state.view)
      ? {
          ...state,
          view: "scanning",
          progress: {
            stage: "preparing",
            message: "正在准备扫描",
            percent: 0,
            completedFiles: 0,
          },
          error: null,
        }
      : state;
  }

  function supportedFile(name) {
    const extension = String(name).split(".").at(-1).toLocaleLowerCase();
    return supportedExtensions.has(extension);
  }

  function rootFromFiles(files) {
    for (const file of files) {
      const parts = pathParts(file.webkitRelativePath || "");
      if (parts.length) return parts[0];
    }
    return "";
  }

  function pathParts(relativePath) {
    return String(relativePath).split("/").filter(Boolean);
  }

  function deepFreeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
      Object.values(value).forEach(deepFreeze);
      Object.freeze(value);
    }
    return value;
  }

  window.DocmetaPrototype = Object.freeze({
    model: Object.freeze({
      createInitialState,
      reduce,
      selectionFromFiles,
      visibleTraces,
      visibleDocuments,
      demoProject,
    }),
  });
})();

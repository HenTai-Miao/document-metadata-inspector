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
   * @property {string | null} metadataOriginTraceId
   * @property {string} primary
   * @property {string | null} error
   */

  const bidders = [
    { id: "bidder-a", name: "华远建设" },
    { id: "bidder-b", name: "启明工程" },
    { id: "bidder-c", name: "中筑科技" },
    { id: "bidder-d", name: "新科咨询" },
  ];

  const traces = [
    {
      id: "trace-author-wang-lei",
      tone: "danger",
      title: "作者信息一致",
      summary: "华远建设与启明工程的技术方案作者均为王磊。",
      field: "作者",
      rawValue: "王磊",
      normalizedValue: "王磊",
      bidders: ["华远建设", "启明工程"],
      files: ["华远建设/技术方案.docx", "启明工程/技术方案.docx"],
      parsers: ["原生解析器", "Apache Tika", "ExifTool"],
      evidenceIds: ["bidder-a-document-1", "bidder-b-document-1"],
    },
    {
      id: "trace-modifier-zhangmin",
      tone: "danger",
      title: "最后修改人一致",
      summary: "中筑科技与新科咨询的文件最后修改人均为 zhangmin。",
      field: "最后修改者",
      rawValue: "zhangmin",
      normalizedValue: "zhangmin",
      bidders: ["中筑科技", "新科咨询"],
      files: ["中筑科技/报价.xlsx", "新科咨询/报价.xlsx"],
      parsers: ["原生解析器", "Apache Tika", "ExifTool"],
      evidenceIds: ["bidder-c-document-2", "bidder-d-document-2"],
    },
    {
      id: "trace-shared-template",
      tone: "caution",
      title: "共用模板痕迹",
      summary: "多个技术方案保留相同模板标识。",
      field: "模板",
      rawValue: "SmartPark_Bid_v4.dotx",
      normalizedValue: "smartpark_bid_v4.dotx",
      bidders: ["华远建设", "中筑科技"],
      files: ["华远建设/技术方案.docx", "中筑科技/技术方案.docx"],
      parsers: ["原生解析器", "Apache Tika"],
      evidenceIds: ["bidder-a-document-1", "bidder-c-document-1"],
    },
    {
      id: "trace-created-within-87-seconds",
      tone: "caution",
      title: "创建时间接近",
      summary: "两份报价文件的创建时间相差 87 秒。",
      field: "创建时间",
      rawValue: "2026-08-08 09:20:13+08:00 ↔ 09:21:40+08:00",
      normalizedValue: "2026-08-08T09:20:13+08:00 ↔ 2026-08-08T09:21:40+08:00",
      bidders: ["华远建设", "启明工程"],
      files: ["华远建设/报价.xlsx", "启明工程/报价.xlsx"],
      parsers: ["原生解析器", "Apache Tika", "ExifTool"],
      evidenceIds: ["bidder-a-document-2", "bidder-b-document-2"],
    },
    {
      id: "trace-matching-application-version",
      tone: "caution",
      title: "应用程序版本相同",
      summary: "多个文件记录了匹配的应用程序和版本。",
      field: "生成应用",
      rawValue: "Microsoft Word for Microsoft 365 / 16.0",
      normalizedValue: "microsoft word / 16.0",
      bidders: ["启明工程", "新科咨询"],
      files: ["启明工程/施工组织.pdf", "新科咨询/施工组织.pdf"],
      parsers: ["Apache Tika", "ExifTool"],
      evidenceIds: ["bidder-b-document-3", "bidder-d-document-3"],
    },
  ];

  const documentNames = ["技术方案.docx", "报价.xlsx", "施工组织.pdf", "授权书.docx"];
  const documents = bidders.flatMap((bidder) =>
    documentNames.map((name, index) => {
      const id = `${bidder.id}-document-${index + 1}`;
      return {
        id,
        bidderId: bidder.id,
        bidderName: bidder.name,
        name,
        format: name.split(".").at(-1).toUpperCase(),
        isDuplicate: traces.some((trace) => trace.evidenceIds.includes(id)),
        searchValues: traces
          .filter((trace) => trace.evidenceIds.includes(id))
          .flatMap((trace) => [trace.field, trace.rawValue, trace.normalizedValue]),
      };
    }),
  );

  const groups = bidders.map((bidder) => ({
    id: bidder.id,
    name: bidder.name,
    documentIds: documents
      .filter((document) => document.bidderId === bidder.id)
      .map((document) => document.id),
  }));

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

  const SCAN_STAGES = deepFreeze([
    { percent: 8, completedFiles: 0, stage: "清单校验", message: "正在校验 16 份文档" },
    { percent: 24, completedFiles: 3, stage: "容器识别", message: "识别 PDF、OLE 与 OPC 容器" },
    {
      percent: 58,
      completedFiles: 9,
      stage: "多引擎解析",
      message: "原生解析、Apache 与 ExifTool 交叉取证",
    },
    { percent: 84, completedFiles: 14, stage: "证据比较", message: "比较跨投标人身份与环境痕迹" },
    { percent: 100, completedFiles: 16, stage: "生成报告", message: "核验完成，正在呈现报告" },
  ]);

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
      metadataOriginTraceId: null,
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
      case "SHOW_METADATA_FOR_TRACE": {
        if (state.view !== "report" || typeof action.traceId !== "string") return state;
        const trace = demoProject.traces.find((candidate) => candidate.id === action.traceId);
        const document = demoProject.documents.find((candidate) =>
          trace?.evidenceIds.includes(candidate.id),
        );
        return trace && document
          ? {
              ...state,
              view: "metadata",
              metadataFilters: {
                bidderId: document.bidderId,
                query: document.name,
                duplicatesOnly: document.isDuplicate,
              },
              selectedEvidenceId: document.id,
              metadataOriginTraceId: trace.id,
            }
          : state;
      }
      case "RETURN_TO_REPORT":
        return state.view === "metadata" ? { ...state, view: "report" } : state;
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
        return state.view === "scanning" && isNextScanStage(state.progress, action.progress)
          ? { ...state, progress: { ...action.progress } }
          : state;
      case "STOP_SCAN":
        return state.view === "scanning" ? { ...state, view: "stopped" } : state;
      case "COMPLETE_SCAN":
        return state.view === "scanning"
          ? {
              ...state,
              view: "report",
              progress: { ...SCAN_STAGES.at(-1) },
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
        document.bidderName.toLocaleLowerCase().includes(query) ||
        document.searchValues.some((value) => value.toLocaleLowerCase().includes(query));
      return matchesBidder && matchesDuplicate && matchesQuery;
    });
  }

  function isNextScanStage(progress, candidate) {
    const currentIndex = SCAN_STAGES.findIndex((stage) => sameScanStage(stage, progress));
    const nextStage = SCAN_STAGES[currentIndex + 1];
    return Boolean(nextStage && sameScanStage(nextStage, candidate));
  }

  function sameScanStage(left, right) {
    return (
      left &&
      right &&
      left.percent === right.percent &&
      left.completedFiles === right.completedFiles &&
      left.stage === right.stage &&
      left.message === right.message
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
      SCAN_STAGES,
      demoProject,
    }),
  });
})();

(() => {
  const namespace = window.DocmetaPrototype;
  const { model, common, renderers } = namespace;
  const appRoot = document.querySelector("#app");
  const folderInput = document.querySelector("#folder-input");
  const variants = new Set(["guided", "verdict", "matrix"]);
  const SCAN_STAGES = Object.freeze([
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
  let state = model.createInitialState(window.location.hash);
  let showLauncher = !variantFromHash(window.location.hash);
  let scanIntervalId = null;
  let scanRunToken = 0;

  function variantFromHash(hash) {
    const variant = String(hash || "").replace(/^#/, "");
    return variants.has(variant) ? variant : "";
  }

  function dispatch(action) {
    const previousState = state;
    state = model.reduce(state, action);
    if (previousState.view === "scanning" && state.view !== "scanning") clearScanTimer();
    render();
  }

  function clearScanTimer() {
    scanRunToken += 1;
    if (scanIntervalId !== null) {
      window.clearInterval(scanIntervalId);
      scanIntervalId = null;
    }
  }

  function scanIntervalMs() {
    const configured = Number(window.__DOCMETA_MOCK_SCAN_INTERVAL_MS__);
    return Number.isFinite(configured) && configured > 0 ? configured : 1_200;
  }

  function startScan(actionType = "START_SCAN") {
    clearScanTimer();
    dispatch({ type: actionType });
    if (state.view !== "scanning") return;

    const token = scanRunToken;
    let stageIndex = 0;
    scanIntervalId = window.setInterval(() => {
      if (token !== scanRunToken || state.view !== "scanning") return;
      const stage = SCAN_STAGES[stageIndex];
      dispatch({ type: "SCAN_PROGRESS", progress: stage });
      stageIndex += 1;
      if (stageIndex === SCAN_STAGES.length) {
        dispatch({ type: "COMPLETE_SCAN" });
      }
    }, scanIntervalMs());
  }

  function render() {
    appRoot.innerHTML = showLauncher ? common.renderLauncher() : renderers[state.variant](state);
  }

  function selectVariant(variant) {
    if (!variants.has(variant)) return;
    showLauncher = false;
    dispatch({ type: "SET_VARIANT", variant });
    if (window.location.hash !== `#${variant}`) window.location.hash = variant;
  }

  function handleClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    if (action === "choose-variant" || action === "switch-variant") {
      selectVariant(target.dataset.variant);
      return;
    }
    if (action === "load-demo") {
      dispatch({ type: "SET_SELECTION", selection: model.demoProject.selection });
      return;
    }
    if (action === "choose-folder") {
      folderInput.click();
      return;
    }
    if (action === "start-scan") {
      startScan();
      return;
    }
    if (action === "stop-scan") {
      clearScanTimer();
      dispatch({ type: "STOP_SCAN" });
      return;
    }
    if (action === "simulate-scan-failure") {
      clearScanTimer();
      dispatch({ type: "FAIL_SCAN", error: "演示解析器未响应" });
      return;
    }
    if (action === "retry-scan") startScan("RETRY_SCAN");
  }

  function handleChange(event) {
    if (event.target !== folderInput || !folderInput.files?.length) return;
    dispatch({
      type: "SET_SELECTION",
      selection: model.selectionFromFiles(folderInput.files),
    });
    folderInput.value = "";
  }

  function handleHashChange() {
    const variant = variantFromHash(window.location.hash);
    if (!variant) {
      clearScanTimer();
      showLauncher = true;
      render();
      return;
    }
    showLauncher = false;
    dispatch({ type: "SET_VARIANT", variant });
  }

  document.addEventListener("click", handleClick);
  document.addEventListener("change", handleChange);
  window.addEventListener("hashchange", handleHashChange);
  window.addEventListener("beforeunload", clearScanTimer);

  namespace.app = Object.freeze({ render, SCAN_STAGES });
  render();
})();

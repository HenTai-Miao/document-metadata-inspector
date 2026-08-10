(() => {
  const namespace = window.DocmetaPrototype;
  const { model, common, renderers } = namespace;
  const appRoot = document.querySelector("#app");
  const folderInput = document.querySelector("#folder-input");
  const variants = new Set(["guided", "verdict", "matrix"]);
  const { SCAN_STAGES } = model;
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
    const focusKey = document.activeElement?.dataset?.focusKey;
    state = model.reduce(state, action);
    if (previousState.view === "scanning" && state.view !== "scanning") clearScanTimer();
    render();
    if (focusKey) {
      Array.from(appRoot.querySelectorAll("[data-focus-key]"))
        .find((element) => element.dataset.focusKey === focusKey)
        ?.focus();
    }
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
    if (action === "retry-scan") {
      startScan("RETRY_SCAN");
      return;
    }
    if (action === "set-report-filter") {
      dispatch({ type: "SET_REPORT_FILTER", reportFilter: target.dataset.filter });
      return;
    }
    if (action === "toggle-trace") {
      dispatch({
        type: "SET_EXPANDED_TRACE",
        traceId: state.expandedTraceId === target.dataset.traceId ? null : target.dataset.traceId,
      });
      return;
    }
    if (action === "show-metadata") {
      showMetadataForTrace(target.dataset.traceId);
      return;
    }
    if (action === "metadata-bidder") {
      dispatch({
        type: "SET_METADATA_FILTERS",
        metadataFilters: { ...state.metadataFilters, bidderId: target.dataset.bidderId || "" },
      });
      return;
    }
    if (action === "metadata-duplicates") {
      dispatch({
        type: "SET_METADATA_FILTERS",
        metadataFilters: {
          ...state.metadataFilters,
          duplicatesOnly: !state.metadataFilters.duplicatesOnly,
        },
      });
      return;
    }
    if (action === "metadata-back") dispatch({ type: "SET_VIEW", view: "report" });
  }

  function handleChange(event) {
    if (event.target === folderInput && folderInput.files?.length) {
      dispatch({
        type: "SET_SELECTION",
        selection: model.selectionFromFiles(folderInput.files),
      });
      folderInput.value = "";
      return;
    }
    if (event.target.dataset.action === "metadata-search") {
      dispatch({
        type: "SET_METADATA_FILTERS",
        metadataFilters: { ...state.metadataFilters, query: event.target.value },
      });
    }
  }

  function showMetadataForTrace(traceId) {
    const trace = model.demoProject.traces.find((candidate) => candidate.id === traceId);
    const document = model.demoProject.documents.find((candidate) =>
      trace?.evidenceIds.includes(candidate.id),
    );
    if (!trace || !document) return;
    dispatch({
      type: "SET_METADATA_FILTERS",
      metadataFilters: {
        bidderId: document.bidderId,
        query: document.name,
        duplicatesOnly: document.isDuplicate,
      },
    });
    dispatch({ type: "SET_SELECTED_EVIDENCE", evidenceId: document.id });
    dispatch({ type: "SET_VIEW", view: "metadata" });
  }

  function handleHashChange() {
    const variant = variantFromHash(window.location.hash);
    if (!variant) {
      clearScanTimer();
      if (state.view === "scanning") state = model.reduce(state, { type: "STOP_SCAN" });
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

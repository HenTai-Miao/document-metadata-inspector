(() => {
  const namespace = window.DocmetaPrototype;
  const { model, common, renderers } = namespace;
  const appRoot = document.querySelector("#app");
  const folderInput = document.querySelector("#folder-input");
  const variants = new Set(["guided", "verdict", "matrix"]);
  let state = model.createInitialState(window.location.hash);
  let showLauncher = !variantFromHash(window.location.hash);

  function variantFromHash(hash) {
    const variant = String(hash || "").replace(/^#/, "");
    return variants.has(variant) ? variant : "";
  }

  function dispatch(action) {
    state = model.reduce(state, action);
    render();
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
    if (action === "start-scan") dispatch({ type: "START_SCAN" });
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
    if (!variant) return;
    showLauncher = false;
    dispatch({ type: "SET_VARIANT", variant });
  }

  document.addEventListener("click", handleClick);
  document.addEventListener("change", handleChange);
  window.addEventListener("hashchange", handleHashChange);

  namespace.app = Object.freeze({ render });
  render();
})();

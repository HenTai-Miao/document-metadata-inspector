(() => {
  window.DocmetaPrototype.renderers.matrix = (state) =>
    `<div class="variant-shell matrix-shell" data-variant="matrix">${window.DocmetaPrototype.common.renderSetupState(state, "matrix")}</div>`;
})();

(() => {
  window.DocmetaPrototype.renderers.guided = (state) =>
    `<div class="variant-shell guided-shell" data-variant="guided">${window.DocmetaPrototype.common.renderSetupState(state, "guided")}</div>`;
})();

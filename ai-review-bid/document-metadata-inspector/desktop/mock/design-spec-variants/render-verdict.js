(() => {
  window.DocmetaPrototype.renderers.verdict = (state) =>
    `<div class="variant-shell verdict-shell" data-variant="verdict">${window.DocmetaPrototype.common.renderSetupState(state, "verdict")}</div>`;
})();

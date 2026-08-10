(() => {
  const namespace = {
    ...window.DocmetaPrototype,
    common: {},
    renderers: {},
  };
  window.DocmetaPrototype = namespace;

  const variantContent = {
    guided: {
      mark: "A",
      name: "引导式核验工作台",
      description: "沿五个真实核验步骤推进，始终明确当前进度与下一步。",
      signature: "五步核验轨道",
    },
    verdict: {
      mark: "B",
      name: "结论先行审查报告",
      description: "先回答发现了什么与为什么可信，再进入具体证据。",
      signature: "完整风险结论",
    },
    matrix: {
      mark: "C",
      name: "证据矩阵控制台",
      description: "以投标人与字段二维关系组织跨文件取证线索。",
      signature: "字段证据矩阵",
    },
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(
      /[&<>"']/gu,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[character],
    );
  }

  function icon(name, className = "") {
    return `<svg class="icon ${className}" aria-hidden="true"><use href="#${name}"></use></svg>`;
  }

  function actionButton({ action, label, style = "primary", iconName = "", testId = "" }) {
    const iconMarkup = iconName ? icon(iconName) : "";
    const testAttribute = testId ? ` data-testid="${escapeHtml(testId)}"` : "";
    return `<button class="button button--${escapeHtml(style)}" type="button" data-action="${escapeHtml(action)}"${testAttribute}>${iconMarkup}<span>${escapeHtml(label)}</span></button>`;
  }

  function renderLauncher() {
    const cards = Object.entries(variantContent)
      .map(
        ([variant, content]) => `
          <button class="variant-card" type="button" data-action="choose-variant" data-variant="${variant}" data-testid="variant-card">
            <span class="variant-card__mark">${content.mark}</span>
            <h2>${content.name}</h2>
            <p>${content.description}</p>
            <span class="variant-card__signature">${icon("i-chev-r", "icon--14")}${content.signature}</span>
          </button>`,
      )
      .join("");
    return `
      <div class="page-frame launcher-page">
        ${renderTopbar(null, true)}
        <header class="page-header">
          <p class="eyebrow">OFFLINE EVIDENCE REVIEW</p>
          <h1 class="page-title">选择一种方式，查看同一份核验结论</h1>
          <p class="page-lead">三套方案共用相同的 4 家投标人、16 份文档与风险证据，只改变信息组织与审查重心。</p>
        </header>
        <main class="page-main">
          <div class="launcher-grid">${cards}</div>
        </main>
      </div>`;
  }

  function renderTopbar(state, isLauncher = false) {
    const variant = state?.variant ?? "";
    const context = state?.selection?.rootName
      ? escapeHtml(state.selection.rootName)
      : isLauncher
        ? "三套完整交互方案"
        : "未选择项目";
    return `
      <header class="topbar">
        <div class="brand">${icon("i-logo", "icon--20")}<span>文档元数据核验</span></div>
        <span class="topbar__context">${context}</span>
        <div class="topbar__actions">
          ${
            isLauncher
              ? '<span class="chip">离线原型</span>'
              : `<nav class="version-switch" aria-label="切换设计方案">
                  ${renderVersionButton("guided", "A", variant)}
                  ${renderVersionButton("verdict", "B", variant)}
                  ${renderVersionButton("matrix", "C", variant)}
                </nav>`
          }
        </div>
      </header>`;
  }

  function renderVersionButton(variant, label, activeVariant) {
    return `<button class="version-switch__button" type="button" data-action="switch-variant" data-variant="${variant}" aria-label="切换到方案 ${label}" aria-current="${variant === activeVariant}">${label}</button>`;
  }

  function renderSetupState(state, variant) {
    const isReady = state.view === "ready" && state.selection;
    const title = isReady ? "确认目录识别结果" : "选择待核验目录";
    const lead = isReady
      ? "确认投标人边界与支持的文档数量，然后开始离线核验。"
      : "仅使用浏览器提供的文件名、相对路径、大小和扩展名，不读取文档正文。";
    return `
      <div class="page-frame" data-testid="selection-page">
        ${renderTopbar(state)}
        <header class="page-header">
          <p class="eyebrow">${escapeHtml(variantContent[variant].mark)} · DOCUMENT INTAKE</p>
          <h1 class="page-title">${title}</h1>
          <p class="page-lead">${lead}</p>
        </header>
        <main class="page-main">
          <div class="setup-layout">
            ${renderVariantAside(state, variant)}
            ${isReady ? renderReady(state, variant) : renderSelection(state, variant)}
          </div>
        </main>
      </div>`;
  }

  function renderVariantAside(state, variant) {
    if (variant === "guided") return renderGuidedRail(state);
    if (variant === "matrix") return renderMatrixTree(state);
    return "";
  }

  function renderGuidedRail(state) {
    const activeStep = state.selection ? 2 : 1;
    return `<aside class="guided-rail" aria-label="核验步骤">
      ${["选择目录", "文件识别", "离线扫描", "核验报告", "元数据"]
        .map(
          (
            label,
            index,
          ) => `<div class="guided-step"${index + 1 === activeStep ? ' aria-current="step"' : ""}>
            <span class="guided-step__number">${String(index + 1).padStart(2, "0")}</span><span>${label}</span>
          </div>`,
        )
        .join("")}
    </aside>`;
  }

  function renderMatrixTree(state) {
    const selection = state.selection;
    const groupNames = selection?.groups?.length
      ? selection.groups.map((group) => group.name)
      : ["投标人目录将在这里显示", "每个目录对应一个核验主体"];
    return `<aside class="matrix-tree" aria-label="投标人目录树">
      <div class="matrix-tree__title">${icon("i-node", "icon--15")}<span>投标人目录</span></div>
      ${groupNames
        .map(
          (name, index) =>
            `<div class="matrix-tree__node${index === 0 ? " matrix-tree__node--active" : ""}">${escapeHtml(name)}</div>`,
        )
        .join("")}
    </aside>`;
  }

  function renderSelection(state, variant) {
    const verdictOpening =
      variant === "verdict"
        ? `<div class="verdict-compact-stage" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div><p class="verdict-task-statement">选择一组投标文档，生成可追溯的元数据核验结论</p>`
        : "";
    const errorMarkup = state.error
      ? `<div class="setup-error" role="alert">${icon("i-alert", "icon--14")}<span>${escapeHtml(state.error)}</span></div>`
      : "";
    return `<section class="setup-card">
      <div class="setup-card__body">
        ${verdictOpening}
        <p class="setup-kicker">START REVIEW</p>
        <h2 class="setup-title">载入演示数据或选择本机目录</h2>
        <p class="setup-copy">演示项目固定包含 4 家投标人和 16 份 PDF、Word、Excel 文档，适合快速比较三套方案。</p>
        ${errorMarkup}
        <div class="button-row">
          ${actionButton({ action: "load-demo", label: "载入演示项目", iconName: "i-play", testId: "load-demo" })}
          ${actionButton({ action: "choose-folder", label: "选择本机目录", style: "secondary", iconName: "i-file", testId: "choose-folder" })}
        </div>
        <p class="privacy-note">${icon("i-shield", "icon--14")}<span>文件留在本机；原型不会上传、解析或读取文档正文。</span></p>
      </div>
    </section>`;
  }

  function renderReady(state, variant) {
    const selection = state.selection;
    const warningMarkup = selection.boundaryWarning
      ? `<div class="setup-warning">${icon("i-alert", "icon--14")}<span>${escapeHtml(selection.boundaryWarning)}</span></div>`
      : "";
    const ignoredMarkup = selection.ignoredCount
      ? `<span class="chip">已忽略 ${escapeHtml(selection.ignoredCount)} 个不支持文件</span>`
      : '<span class="chip">支持格式检查完成</span>';
    return `<section class="setup-card" data-testid="selected-folder">
      <div class="setup-card__body">
        <p class="setup-kicker">READY TO REVIEW</p>
        <h2 class="setup-title">目录边界已经识别</h2>
        <p class="setup-copy">核对以下范围。开始后将模拟三种解析器的离线交叉取证过程。</p>
        <div class="directory-summary">
          <div class="directory-summary__folder">
            <span class="directory-summary__label">已选目录</span>
            <strong title="${escapeHtml(selection.rootName)}">${escapeHtml(selection.rootName)}</strong>
          </div>
          <div class="directory-summary__metric">
            <span class="directory-summary__label">投标人</span>
            <strong data-testid="bidder-count">${escapeHtml(selection.bidderCount)}</strong>
          </div>
          <div class="directory-summary__metric">
            <span class="directory-summary__label">支持文档</span>
            <strong data-testid="file-count">${escapeHtml(selection.fileCount)}</strong>
          </div>
        </div>
        ${warningMarkup}
        <div class="button-row">
          ${actionButton({ action: "start-scan", label: "开始离线核验", iconName: "i-play", testId: "start-scan" })}
          ${actionButton({ action: "choose-folder", label: "更换目录", style: "secondary", iconName: "i-file", testId: "choose-folder" })}
          ${ignoredMarkup}
        </div>
        <p class="privacy-note">${icon("i-shield", "icon--14")}<span>${variantContent[variant].name} · 当前选择可在切换方案后继续使用。</span></p>
      </div>
    </section>`;
  }

  Object.assign(namespace.common, {
    escapeHtml,
    icon,
    actionButton,
    renderLauncher,
    renderSetupState,
  });
})();

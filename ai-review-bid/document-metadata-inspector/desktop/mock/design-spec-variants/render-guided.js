(() => {
  const namespace = window.DocmetaPrototype;
  const { common, model } = namespace;
  const { escapeHtml, icon } = common;

  const GUIDED_STEPS = Object.freeze([
    ["select", "选择目录"],
    ["identify", "文件识别"],
    ["scan", "离线扫描"],
    ["report", "核验报告"],
    ["metadata", "元数据明细"],
  ]);

  function activeStepForView(view) {
    if (view === "ready") return "identify";
    if (["scanning", "stopped", "failed"].includes(view)) return "scan";
    if (view === "report") return "report";
    if (view === "metadata") return "metadata";
    return "select";
  }

  function renderGuidedRail(state) {
    const activeStep = activeStepForView(state.view);
    const activeIndex = GUIDED_STEPS.findIndex(([step]) => step === activeStep);
    return `<aside class="guided-rail" aria-label="核验步骤">
      <p class="guided-rail__label">REVIEW FLOW</p>
      ${GUIDED_STEPS.map(([step, label], index) => {
        const current = step === activeStep ? ' aria-current="step"' : "";
        const complete = index < activeIndex ? " guided-step--complete" : "";
        return `<div class="guided-step${complete}" data-step="${step}" data-testid="workflow-step"${current}>
          <span class="guided-step__number">${String(index + 1).padStart(2, "0")}</span>
          <span class="guided-step__copy">${escapeHtml(label)}</span>
        </div>`;
      }).join("")}
    </aside>`;
  }

  function renderGuided(state) {
    const markup =
      state.view === "report"
        ? renderReportPage(state)
        : state.view === "metadata"
          ? renderMetadataPage(state)
          : common.renderSetupState(state, "guided");
    return `<div class="variant-shell guided-shell" data-variant="guided" data-testid="guided-shell">${markup}</div>`;
  }

  function renderReportPage(state) {
    const traces = model.visibleTraces(state);
    return `<div class="page-frame guided-page guided-page--report">
      ${common.renderTopbar(state)}
      <header class="page-header guided-page__header">
        <p class="eyebrow">A · GUIDED REVIEW / STEP 04</p>
        <h1 class="page-title">核验报告已生成</h1>
        <p class="page-lead">先确认核验是否完整，再按风险等级逐条核对可追溯证据。</p>
      </header>
      <main class="page-main" data-testid="report-page">
        <div class="guided-workspace">
          ${renderGuidedRail(state)}
          <div class="guided-workspace__content">
            ${renderCompletionPanel(state)}
            ${renderTaskCards(state)}
            ${renderTraceSection(state, traces)}
          </div>
        </div>
      </main>
    </div>`;
  }

  function renderCompletionPanel(state) {
    return `<section class="dark-panel guided-completion" aria-labelledby="guided-completion-title">
      <div class="guided-completion__intro">
        <p class="guided-completion__status">${icon("i-check", "icon--15")}<span>离线核验完成</span></p>
        <h2 id="guided-completion-title">16 / 16 份文档已完成交叉取证</h2>
        <p data-testid="scan-summary" data-complete="${escapeHtml(state.progress.completedFiles)}">报告覆盖固定演示项目的全部文档；高风险身份痕迹与待复核环境线索已分开呈现。</p>
      </div>
      <dl class="guided-completion__facts">
        <div><dt>解析器</dt><dd>3 / 3</dd></div>
        <div><dt>归一化元数据</dt><dd>148</dd></div>
        <div><dt>处理边界</dt><dd>仅本机</dd></div>
      </dl>
    </section>`;
  }

  function renderTaskCards(state) {
    const dangerCount = model.visibleTraces({ ...state, reportFilter: "danger" }).length;
    const cautionCount = model.visibleTraces({ ...state, reportFilter: "caution" }).length;
    const cards = [
      {
        tone: "danger",
        kicker: "高风险身份痕迹",
        value: `${dangerCount} 组`,
        copy: "优先核对跨投标人出现的作者和最后修改者。",
        iconName: "i-alert",
      },
      {
        tone: "caution",
        kicker: "待人工复核",
        value: `${cautionCount} 组`,
        copy: "模板、时间与软件组合仅作为复核线索，不代表已认定异常。",
        iconName: "i-clock",
      },
      {
        tone: "neutral",
        kicker: "证据覆盖",
        value: "16 / 16",
        copy: "三种解析器完成，148 条归一化元数据可回溯到文件。",
        iconName: "i-shield",
      },
      {
        tone: "neutral",
        kicker: "下一步",
        value: "逐条核验",
        copy: "展开证据查看原始值，再定位到对应元数据卡片。",
        iconName: "i-eye",
      },
    ];
    return `<section class="guided-task-grid" aria-label="报告任务摘要">
      ${cards
        .map(
          (card) => `<article class="guided-task-card" data-testid="guided-task-card">
            <div class="guided-task-card__heading guided-task-card__heading--${card.tone}">${icon(card.iconName, "icon--15")}<span>${card.kicker}</span></div>
            <strong class="guided-task-card__value guided-task-card__value--${card.tone}">${card.value}</strong>
            <p>${card.copy}</p>
          </article>`,
        )
        .join("")}
    </section>`;
  }

  function renderTraceSection(state, traces) {
    return `<section class="guided-evidence" aria-labelledby="guided-evidence-title">
      <div class="guided-evidence__heading">
        <div>
          <p class="guided-section-kicker">EVIDENCE QUEUE</p>
          <h2 id="guided-evidence-title">证据核验清单</h2>
        </div>
        <p><strong data-testid="trace-count">${escapeHtml(traces.length)}</strong> 条当前线索</p>
      </div>
      ${renderTraceFilters(state)}
      <div class="guided-trace-list">
        ${traces.length ? traces.map((trace) => renderTrace(state, trace)).join("") : renderEmptyTraces()}
      </div>
    </section>`;
  }

  function renderTraceFilters(state) {
    const filters = [
      ["all", "全部", "report-filter-all"],
      ["danger", "高风险", "report-filter-danger"],
      ["caution", "待复核", "report-filter-caution"],
    ];
    return `<div class="guided-filterbar" aria-label="报告筛选">
      ${icon("i-filter", "icon--14")}
      ${filters
        .map(
          ([filter, label, testId]) =>
            `<button class="guided-filter" type="button" data-action="set-report-filter" data-filter="${filter}" data-focus-key="report-filter-${filter}" data-testid="${testId}" aria-pressed="${filter === state.reportFilter}">${label}</button>`,
        )
        .join("")}
    </div>`;
  }

  function renderTrace(state, trace) {
    const expanded = state.expandedTraceId === trace.id;
    const evidence = trace;
    const label = trace.tone === "danger" ? "高风险" : "待复核";
    const detailId = `guided-trace-detail-${trace.id}`;
    return `<article class="guided-trace" data-testid="trace-row">
      <div class="guided-trace__summary">
        <span class="guided-tone-label guided-tone-label--${trace.tone}">${label}</span>
        <div class="guided-trace__copy">
          <h3>${escapeHtml(trace.title)}</h3>
          <p>${escapeHtml(trace.summary)}</p>
        </div>
        <div class="guided-trace__actions">
          <button class="button button--quiet guided-trace__toggle" type="button" data-action="toggle-trace" data-trace-id="${escapeHtml(trace.id)}" data-focus-key="trace-toggle-${escapeHtml(trace.id)}" data-testid="trace-toggle" aria-expanded="${expanded}" aria-controls="${detailId}">
            ${icon("i-chev-d", "icon--14")}<span>${expanded ? "收起证据" : "展开证据"}</span>
          </button>
          <button class="button button--secondary guided-trace__locate" type="button" data-action="show-metadata" data-trace-id="${escapeHtml(trace.id)}" data-testid="show-metadata">
            ${icon("i-eye", "icon--14")}<span>定位元数据</span>
          </button>
        </div>
      </div>
      ${expanded ? renderTraceDisclosure(trace, evidence, detailId) : ""}
    </article>`;
  }

  function renderTraceDisclosure(trace, evidence, detailId) {
    const items = [
      ["字段", evidence.field, true],
      ["原始值", evidence.rawValue, true],
      ["归一化值", evidence.normalizedValue, true],
      ["涉及投标人", evidence.bidders.join("、"), false],
      ["相对文件名", evidence.files.join("；"), false],
      ["解析器", evidence.parsers.join("、"), false],
    ];
    return `<div class="guided-trace__disclosure" id="${detailId}" data-testid="trace-disclosure">
      <dl>
        ${items
          .map(
            ([label, value, emphasize]) =>
              `<div><dt>${label}</dt><dd class="${emphasize ? `guided-evidence-value guided-evidence-value--${trace.tone}` : ""}">${escapeHtml(value)}</dd></div>`,
          )
          .join("")}
      </dl>
    </div>`;
  }

  function renderEmptyTraces() {
    return `<div class="guided-empty-state"><p>当前筛选下没有线索。</p></div>`;
  }

  function renderMetadataPage(state) {
    const documents = model.visibleDocuments(state);
    return `<div class="page-frame guided-page guided-page--metadata" data-testid="metadata-page">
      ${common.renderTopbar(state)}
      <header class="page-header guided-page__header">
        <p class="eyebrow">A · GUIDED REVIEW / STEP 05</p>
        <h1 class="page-title">元数据明细</h1>
        <p class="page-lead">筛选投标人和文件，核对字段原始值、归一化值与解析器来源。</p>
      </header>
      <main class="page-main">
        <div class="guided-workspace">
          ${renderGuidedRail(state)}
          <div class="guided-workspace__content guided-metadata">
            ${renderMetadataToolbar(state)}
            <div class="guided-document-list" aria-live="polite">
              ${
                documents.length
                  ? documents.map((document) => renderDocumentCard(state, document)).join("")
                  : '<div class="guided-empty-state"><p>没有符合当前筛选条件的文档。请调整投标人、文件名或重复项筛选。</p></div>'
              }
            </div>
          </div>
        </div>
      </main>
    </div>`;
  }

  function renderMetadataToolbar(state) {
    const filters = state.metadataFilters;
    const bidderOptions = [{ id: "", name: "全部投标人" }, ...model.demoProject.groups];
    return `<section class="guided-metadata-toolbar" aria-labelledby="metadata-filter-title">
      <div class="guided-metadata-toolbar__title">
        <div>
          <p class="guided-section-kicker">DOCUMENT BROWSER</p>
          <h2 id="metadata-filter-title">按文档核对证据</h2>
        </div>
        <button class="button button--quiet" type="button" data-action="metadata-back" data-testid="metadata-back">${icon("i-chev-l", "icon--14")}<span>返回核验报告</span></button>
      </div>
      <div class="guided-bidder-filters" aria-label="投标人筛选">
        ${bidderOptions
          .map(
            (bidder) =>
              `<button class="guided-bidder-filter" type="button" data-action="metadata-bidder" data-bidder-id="${escapeHtml(bidder.id)}" data-focus-key="metadata-bidder-${escapeHtml(bidder.id || "all")}" aria-pressed="${filters.bidderId === bidder.id}">${escapeHtml(bidder.name)}</button>`,
          )
          .join("")}
      </div>
      <div class="guided-metadata-controls">
        <label class="guided-search">
          <span>${icon("i-search", "icon--14")}<span>搜索文件名或投标人</span></span>
          <input type="search" value="${escapeHtml(filters.query)}" placeholder="例如：技术方案.docx" data-action="metadata-search" data-testid="metadata-search">
        </label>
        <button class="guided-duplicates-toggle" type="button" role="switch" data-action="metadata-duplicates" data-focus-key="metadata-duplicates" data-testid="metadata-duplicates-only" aria-checked="${filters.duplicatesOnly}">
          <span class="guided-switch" aria-hidden="true"><span></span></span><span>只看跨投标人重复</span>
        </button>
      </div>
    </section>`;
  }

  function renderDocumentCard(state, document) {
    const relatedTraces = model.demoProject.traces.filter((trace) =>
      trace.evidenceIds.includes(document.id),
    );
    const open = state.selectedEvidenceId === document.id ? " open" : "";
    return `<details class="guided-document-card" data-testid="metadata-document-card"${open}>
      <summary>
        <span class="guided-document-card__icon">${icon("i-file", "icon--15")}</span>
        <span class="guided-document-card__name"><strong class="guided-document-card__title">${escapeHtml(document.name)}</strong><span class="guided-document-card__path">${escapeHtml(document.bidderName)} / ${escapeHtml(document.name)}</span></span>
        <span class="guided-document-card__format">${escapeHtml(document.format)}</span>
        <span class="guided-document-card__count">${relatedTraces.length ? `${relatedTraces.length} 条关联线索` : "未命中跨投标人线索"}</span>
        ${icon("i-chev-d", "icon--14")}
      </summary>
      <div class="guided-document-card__body">
        ${
          relatedTraces.length
            ? relatedTraces.map((trace) => renderDocumentEvidence(trace)).join("")
            : '<p class="guided-document-card__empty">当前演示数据中没有与该文档关联的跨投标人重复字段。</p>'
        }
      </div>
    </details>`;
  }

  function renderDocumentEvidence(trace) {
    const evidence = trace;
    const label = trace.tone === "danger" ? "高风险" : "待复核";
    return `<article class="guided-document-evidence">
      <div class="guided-document-evidence__heading">
        <span class="guided-tone-label guided-tone-label--${trace.tone}">${label}</span>
        <strong class="guided-document-evidence__field">${escapeHtml(evidence.field)}</strong>
      </div>
      <dl>
        <div><dt>原始值</dt><dd class="guided-evidence-value guided-evidence-value--${trace.tone}">${escapeHtml(evidence.rawValue)}</dd></div>
        <div><dt>归一化值</dt><dd>${escapeHtml(evidence.normalizedValue)}</dd></div>
        <div><dt>解析器</dt><dd>${escapeHtml(evidence.parsers.join("、"))}</dd></div>
        <div><dt>关联文件</dt><dd>${escapeHtml(evidence.files.join("；"))}</dd></div>
      </dl>
    </article>`;
  }

  Object.assign(namespace.renderers, {
    guided: renderGuided,
    guidedRail: renderGuidedRail,
  });
})();

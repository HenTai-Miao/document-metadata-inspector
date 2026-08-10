(() => {
  const namespace = window.DocmetaPrototype;
  const { common, model } = namespace;
  const { escapeHtml, icon } = common;

  function renderVerdict(state) {
    const markup =
      state.view === "report"
        ? renderReportPage(state)
        : state.view === "metadata"
          ? renderMetadataPage(state)
          : common.renderSetupState(state, "verdict");
    return `<div class="variant-shell verdict-shell" data-variant="verdict" data-testid="verdict-shell">${markup}</div>`;
  }

  function renderReportPage(state) {
    const traces = model.visibleTraces(state);
    const entryClass = state.verdictEntryPending ? " verdict-enter" : "";
    return `<div class="page-frame verdict-page verdict-page--report">
      ${common.renderTopbar(state)}
      <main class="page-main verdict-report${entryClass}" data-testid="report-page">
        ${renderConclusion()}
        ${renderTimeline(state, traces)}
        ${renderTrustPanel(state)}
      </main>
    </div>`;
  }

  function renderConclusion() {
    const counts = [
      ["2", "高风险身份痕迹", "danger"],
      ["3", "待人工复核线索", "caution"],
      ["4", "投标主体", "neutral"],
      ["16", "纳入核验文档", "neutral"],
    ];
    return `<section class="verdict-conclusion" aria-labelledby="verdict-title">
      <div class="verdict-conclusion__context">
        <p class="eyebrow">B · CONCLUSION FIRST / REVIEW REPORT</p>
        <p class="verdict-report-meta"><span>某市智慧园区建设项目</span><span>报告日期 2026-08-10</span><span>离线核验</span></p>
      </div>
      <div class="verdict-conclusion__statement">
        <p class="verdict-recommendation">建议重点复核</p>
        <h1 id="verdict-title" data-testid="verdict-title">本次核验发现 2 处高风险身份痕迹</h1>
        <p>作者与最后修改者在不同投标主体间重复出现。该结论用于确定复核优先级，不替代人工认定。</p>
      </div>
      <dl class="verdict-counts" aria-label="报告范围摘要">
        ${counts
          .map(
            ([
              value,
              label,
              tone,
            ]) => `<div class="verdict-count verdict-count--${tone}" data-testid="verdict-count">
              <dd>${value}</dd><dt>${label}</dt>
            </div>`,
          )
          .join("")}
      </dl>
    </section>`;
  }

  function renderTimeline(state, traces) {
    return `<section class="verdict-timeline" data-testid="evidence-timeline" aria-labelledby="verdict-timeline-title">
      <div class="verdict-section-heading">
        <div>
          <p class="verdict-kicker">EVIDENCE SEQUENCE</p>
          <h2 id="verdict-timeline-title">证据核验时间线</h2>
          <p>按核验序列排列，高风险身份痕迹优先于环境线索。</p>
        </div>
        <p class="verdict-trace-total"><strong data-testid="trace-count">${escapeHtml(traces.length)}</strong><span>条当前线索</span></p>
      </div>
      ${renderTraceFilters(state)}
      <ol class="verdict-trace-list">
        ${traces.length ? traces.map((trace, index) => renderTrace(state, trace, index)).join("") : renderEmptyTraces()}
      </ol>
    </section>`;
  }

  function renderTraceFilters(state) {
    const filters = [
      ["all", "全部", "report-filter-all"],
      ["danger", "高风险", "report-filter-danger"],
      ["caution", "待复核", "report-filter-caution"],
    ];
    return `<div class="verdict-filterbar" aria-label="报告筛选">
      ${icon("i-filter", "icon--14")}
      ${filters
        .map(
          ([filter, label, testId]) =>
            `<button class="verdict-filter" type="button" data-action="set-report-filter" data-filter="${filter}" data-focus-key="report-filter-${filter}" data-testid="${testId}" aria-pressed="${filter === state.reportFilter}">${label}</button>`,
        )
        .join("")}
    </div>`;
  }

  function renderTrace(state, trace, index) {
    const expanded = state.expandedTraceId === trace.id;
    const label = trace.tone === "danger" ? "高风险" : "待复核";
    const detailId = `verdict-trace-detail-${trace.id}`;
    const sequence = String(index + 1).padStart(2, "0");
    return `<li class="verdict-trace" data-tone="${trace.tone}" data-testid="trace-row">
      <div class="verdict-trace__marker" aria-hidden="true"><span>${sequence}</span></div>
      <article class="verdict-trace__content">
        <div class="verdict-trace__heading">
          <span class="verdict-tone-label verdict-tone-label--${trace.tone}">${label}</span>
          <span class="verdict-trace__field">${escapeHtml(trace.field)}</span>
        </div>
        <h3>${escapeHtml(trace.title)}</h3>
        <p>${escapeHtml(trace.summary)}</p>
        <p class="verdict-trace__value verdict-trace__value--${trace.tone}">${escapeHtml(trace.rawValue)}</p>
        <div class="verdict-trace__actions">
          <button class="button button--quiet verdict-trace__toggle" type="button" data-action="toggle-trace" data-trace-id="${escapeHtml(trace.id)}" data-focus-key="trace-toggle-${escapeHtml(trace.id)}" data-testid="trace-toggle" aria-expanded="${expanded}" aria-controls="${detailId}">
            ${icon("i-chev-d", "icon--14")}<span>${expanded ? "收起证据" : "展开证据"}</span>
          </button>
          <button class="button button--secondary" type="button" data-action="show-metadata" data-trace-id="${escapeHtml(trace.id)}" data-focus-key="show-metadata-${escapeHtml(trace.id)}" data-testid="show-metadata">
            ${icon("i-eye", "icon--14")}<span>查看原始证据</span>
          </button>
        </div>
        ${expanded ? renderTraceDisclosure(trace, detailId) : ""}
      </article>
    </li>`;
  }

  function renderTraceDisclosure(trace, detailId) {
    const items = [
      ["字段", trace.field],
      ["原始值", trace.rawValue],
      ["归一化值", trace.normalizedValue],
      ["涉及投标人", trace.bidders.join("、")],
      ["相对文件名", trace.files.join("；")],
      ["解析器", trace.parsers.join("、")],
    ];
    return `<div class="verdict-trace__disclosure" id="${detailId}" data-testid="trace-disclosure">
      <dl>
        ${items
          .map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`)
          .join("")}
      </dl>
    </div>`;
  }

  function renderEmptyTraces() {
    return `<li class="verdict-empty-state"><p>当前筛选下没有线索。</p></li>`;
  }

  function renderTrustPanel(state) {
    return `<aside class="verdict-trust" data-testid="trust-panel" aria-labelledby="verdict-trust-title">
      <div class="verdict-trust__heading">
        <p class="verdict-trust__kicker">WHY THIS IS TRACEABLE</p>
        <h2 id="verdict-trust-title">结论可信度</h2>
        <p>每一项结论均可回到原始文件、字段值与解析器来源。</p>
      </div>
      <div class="verdict-trust__facts">
        <p><span class="verdict-trust__value">3 / 3</span> 解析器完成</p>
        <p><span class="verdict-trust__value">16 / 16</span> 文档可追溯</p>
        <p><span class="verdict-trust__value">148</span> 条归一化元数据</p>
      </div>
      <p class="verdict-trust__boundary">${icon("i-shield", "icon--15")}<span>离线处理 · 未上传文件</span></p>
      <p class="verdict-trust__complete" data-testid="scan-summary" data-complete="${escapeHtml(state.progress.completedFiles)}">报告范围完整，无部分核验结论。</p>
    </aside>`;
  }

  function renderMetadataPage(state) {
    const documents = model.visibleDocuments(state);
    const trace = model.demoProject.traces.find(
      (candidate) => candidate.id === state.metadataOriginTraceId,
    );
    return `<div class="page-frame verdict-page verdict-page--metadata" data-testid="metadata-page">
      ${common.renderTopbar(state)}
      <header class="page-header verdict-metadata-header">
        <p class="eyebrow">B · CONCLUSION TRACE / RAW EVIDENCE</p>
        <h1 class="page-title">原始证据定位</h1>
        <p class="page-lead">以触发报告结论的字段值为检索入口，直接核对文档、原始值与解析器。</p>
      </header>
      <main class="page-main verdict-metadata-layout">
        ${renderOriginContext(trace)}
        <section class="verdict-metadata-browser" aria-labelledby="verdict-browser-title">
          ${renderMetadataToolbar(state)}
          <div class="verdict-document-list" aria-live="polite">
            ${
              documents.length
                ? documents.map((document) => renderDocumentCard(state, document)).join("")
                : '<div class="verdict-empty-state"><p>没有符合当前证据筛选的文档。</p></div>'
            }
          </div>
        </section>
      </main>
    </div>`;
  }

  function renderOriginContext(trace) {
    if (!trace) return "";
    const label = trace.tone === "danger" ? "高风险" : "待复核";
    return `<aside class="verdict-origin" data-testid="verdict-metadata-context">
      <button class="button button--quiet" type="button" data-action="metadata-back" data-testid="metadata-back">${icon("i-chev-l", "icon--14")}<span>返回核验报告</span></button>
      <p class="verdict-kicker">CONCLUSION ORIGIN</p>
      <span class="verdict-tone-label verdict-tone-label--${trace.tone}">${label}</span>
      <h2>${escapeHtml(trace.title)}</h2>
      <p>${escapeHtml(trace.summary)}</p>
      <dl>
        <div><dt>定位字段</dt><dd>${escapeHtml(trace.field)}</dd></div>
        <div><dt>检索值</dt><dd class="verdict-origin__value verdict-origin__value--${trace.tone}">${escapeHtml(trace.rawValue)}</dd></div>
        <div><dt>涉及主体</dt><dd>${escapeHtml(trace.bidders.join("、"))}</dd></div>
      </dl>
    </aside>`;
  }

  function renderMetadataToolbar(state) {
    const filters = state.metadataFilters;
    const bidderOptions = [{ id: "", name: "全部投标人" }, ...model.demoProject.groups];
    return `<div class="verdict-metadata-toolbar">
      <div class="verdict-section-heading">
        <div>
          <p class="verdict-kicker">EVIDENCE DOCUMENTS</p>
          <h2 id="verdict-browser-title">关联文档</h2>
        </div>
      </div>
      <div class="verdict-bidder-filters" aria-label="投标人筛选">
        ${bidderOptions
          .map(
            (bidder) =>
              `<button class="verdict-bidder-filter" type="button" data-action="metadata-bidder" data-bidder-id="${escapeHtml(bidder.id)}" data-focus-key="metadata-bidder-${escapeHtml(bidder.id || "all")}" aria-pressed="${filters.bidderId === bidder.id}">${escapeHtml(bidder.name)}</button>`,
          )
          .join("")}
      </div>
      <div class="verdict-metadata-controls">
        <label class="verdict-search">
          <span>${icon("i-search", "icon--14")}<span>搜索原始证据值</span></span>
          <input type="search" value="${escapeHtml(filters.query)}" placeholder="例如：王磊" data-action="metadata-search" data-focus-key="metadata-search" data-testid="metadata-search">
        </label>
        <button class="verdict-duplicates-toggle" type="button" role="switch" data-action="metadata-duplicates" data-focus-key="metadata-duplicates" data-testid="metadata-duplicates-only" aria-checked="${filters.duplicatesOnly}">
          <span class="verdict-switch" aria-hidden="true"><span></span></span><span>只看跨投标人重复</span>
        </button>
      </div>
    </div>`;
  }

  function renderDocumentCard(state, document) {
    const relatedTraces = model.demoProject.traces.filter((trace) =>
      trace.evidenceIds.includes(document.id),
    );
    const open = state.selectedEvidenceId === document.id ? " open" : "";
    return `<details class="verdict-document" data-testid="metadata-document-card"${open}>
      <summary data-evidence-id="${escapeHtml(document.id)}" data-testid="metadata-document-summary">
        <span class="verdict-document__index">${icon("i-file", "icon--15")}</span>
        <span class="verdict-document__identity"><strong>${escapeHtml(document.name)}</strong><span>${escapeHtml(document.bidderName)} / ${escapeHtml(document.name)}</span></span>
        <span class="verdict-document__format">${escapeHtml(document.format)}</span>
        <span class="verdict-document__count">${relatedTraces.length} 条关联线索</span>
        ${icon("i-chev-d", "icon--14")}
      </summary>
      <div class="verdict-document__body">
        ${relatedTraces.map((trace) => renderDocumentEvidence(trace)).join("")}
      </div>
    </details>`;
  }

  function renderDocumentEvidence(trace) {
    const label = trace.tone === "danger" ? "高风险" : "待复核";
    return `<article class="verdict-document-evidence">
      <div class="verdict-document-evidence__heading">
        <span class="verdict-tone-label verdict-tone-label--${trace.tone}">${label}</span>
        <strong>${escapeHtml(trace.field)}</strong>
      </div>
      <dl>
        <div><dt>原始值</dt><dd class="verdict-origin__value verdict-origin__value--${trace.tone}">${escapeHtml(trace.rawValue)}</dd></div>
        <div><dt>归一化值</dt><dd>${escapeHtml(trace.normalizedValue)}</dd></div>
        <div><dt>解析器</dt><dd>${escapeHtml(trace.parsers.join("、"))}</dd></div>
        <div><dt>关联文件</dt><dd>${escapeHtml(trace.files.join("；"))}</dd></div>
      </dl>
    </article>`;
  }

  namespace.renderers.verdict = renderVerdict;
})();

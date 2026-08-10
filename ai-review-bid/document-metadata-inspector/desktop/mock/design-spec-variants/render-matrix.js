(() => {
  const namespace = window.DocmetaPrototype;
  const { common, model } = namespace;
  const { escapeHtml, icon } = common;

  function renderMatrix(state) {
    const content = ["report", "metadata"].includes(state.view)
      ? renderReportPage(state)
      : common.renderSetupState(state, "matrix");
    return `<div class="variant-shell matrix-shell" data-variant="matrix" data-testid="matrix-shell">${content}</div>`;
  }

  function renderMatrixTree(state) {
    const groups = treeGroups(state);
    const selectedEvidence = selectedMatrixEvidence(state);
    const relatedDocumentIds = new Set(selectedEvidence?.evidenceIds ?? []);
    let fileIndex = 0;
    const treeTitle = state.selection?.source === "local" ? "本机目录" : "投标人目录";
    return `<aside class="matrix-tree" aria-label="投标人和文档目录树" data-testid="bidder-tree">
      <div class="matrix-tree__heading">
        <div class="matrix-tree__title">${icon("i-node", "icon--15")}<span>${treeTitle}</span></div>
        <span>${state.selection ? `${escapeHtml(state.selection.fileCount)} 份` : "待载入"}</span>
      </div>
      <div class="matrix-tree__groups">
        ${groups
          .map((group) => {
            const fileMarkup = group.files
              .map((file) => {
                if (file.placeholder) {
                  return `<li class="matrix-tree__file matrix-tree__file--placeholder" aria-label="待载入文件位置" data-testid="file-placeholder"><span aria-hidden="true"></span></li>`;
                }
                const status = fileState(state, fileIndex);
                const related = relatedDocumentIds.has(file.id) ? " is-related" : "";
                fileIndex += 1;
                return `<li class="matrix-tree__file${related}" data-document-id="${escapeHtml(file.id)}" data-file-state="${status.id}" data-testid="file-node">
                  ${icon(status.icon, "icon--13")}
                  <span class="matrix-tree__file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
                  <span class="matrix-tree__file-state">${status.label}</span>
                </li>`;
              })
              .join("");
            return `<section class="matrix-tree__bidder" data-bidder-id="${escapeHtml(group.id)}" data-group-kind="${escapeHtml(group.kind)}" data-testid="bidder-node">
              <div class="matrix-tree__bidder-name">${icon("i-users", "icon--14")}<strong>${escapeHtml(group.name)}</strong><span>${group.files.length || 4}</span></div>
              <ul>${fileMarkup}</ul>
            </section>`;
          })
          .join("")}
      </div>
    </aside>`;
  }

  function treeGroups(state) {
    if (!state.selection) {
      return model.demoProject.groups.map((group) => ({
        ...group,
        kind: "placeholder",
        files: Array.from({ length: 4 }, () => ({ placeholder: true })),
      }));
    }
    if (state.selection.source === "demo") {
      return state.selection.groups.map((group) => ({
        id: group.id,
        name: group.name,
        kind: "bidder",
        files: group.files.map((file) => ({ id: file.id, name: file.name })),
      }));
    }
    const localGroups = state.selection.groups.map((group) => ({
      id: group.id,
      name: group.name,
      kind: "bidder",
      files: group.files.map((file) => ({ id: file.id, name: file.name })),
    }));
    return state.selection.rootFiles.length
      ? [
          {
            id: "root-files",
            name: "根目录文件",
            kind: "root",
            files: state.selection.rootFiles.map((file) => ({
              id: file.id,
              name: file.name,
            })),
          },
          ...localGroups,
        ]
      : localGroups;
  }

  function fileState(state, index) {
    const progress = model.progressForSelection(state.selection, state.progress);
    if (["report", "metadata"].includes(state.view)) {
      return { id: "completed", label: "完成", icon: "i-check" };
    }
    if (["scanning", "stopped", "failed"].includes(state.view)) {
      if (index < progress.completedFiles) {
        return { id: "completed", label: "完成", icon: "i-check" };
      }
      if (state.view === "scanning" && index === progress.completedFiles) {
        return { id: "parsing", label: "解析中", icon: "i-more" };
      }
      return { id: "waiting", label: "等待", icon: "i-clock" };
    }
    return { id: "ready", label: "已就绪", icon: "i-file" };
  }

  function renderReportPage(state) {
    const traces = model.visibleTraces(state);
    const metadataMode = state.view === "metadata";
    return `<div class="page-frame matrix-page${metadataMode ? " matrix-page--metadata" : ""}"${metadataMode ? ' data-testid="metadata-page"' : ""}>
      ${common.renderTopbar(state)}
      <header class="page-header matrix-header">
        <div>
          <p class="eyebrow">C · EVIDENCE MATRIX / FIELD × BIDDER</p>
          <h1 class="page-title">元数据证据矩阵</h1>
          <p class="page-lead">按字段横向比较四家投标主体；颜色只标记可追溯线索，不替代人工判断。</p>
        </div>
        <dl class="matrix-header__facts">
          <div><dt>高风险</dt><dd>2</dd></div>
          <div><dt>待复核</dt><dd>3</dd></div>
          <div><dt>覆盖</dt><dd>16 / 16</dd></div>
        </dl>
      </header>
      <main class="page-main matrix-workspace" data-testid="report-page">
        ${renderMatrixTree(state)}
        <div class="matrix-console">
          ${metadataMode ? renderMetadataReturn() : ""}
          ${renderSummary(state)}
          ${renderMatrixToolbar(state, traces)}
          ${renderEvidenceMatrix(state)}
          ${renderEvidenceDrawer(state, metadataMode)}
        </div>
      </main>
    </div>`;
  }

  function renderMetadataReturn() {
    return `<div class="matrix-metadata-return">
      <button class="button button--quiet" type="button" data-action="metadata-back" data-testid="metadata-back">${icon("i-chev-l", "icon--14")}<span>返回核验报告</span></button>
      <span>元数据：矩阵与证据抽屉联动</span>
    </div>`;
  }

  function renderSummary(state) {
    const progress = model.progressForSelection(state.selection, state.progress);
    return `<section class="dark-panel matrix-summary" aria-label="核验覆盖摘要">
      <div><span class="matrix-summary__label">证据控制台</span><strong>字段 × 投标主体</strong></div>
      <p>2 组身份痕迹优先核对；模板、时间与软件环境保持独立语义。</p>
      <p class="matrix-summary__complete" data-testid="scan-summary" data-complete="${escapeHtml(progress.completedFiles)}">3 / 3 解析器 · 148 条归一化元数据 · 全程离线</p>
    </section>`;
  }

  function renderMatrixToolbar(state, traces) {
    const filters = [
      ["all", "全部", "report-filter-all"],
      ["danger", "高风险", "report-filter-danger"],
      ["caution", "待复核", "report-filter-caution"],
    ];
    return `<section class="matrix-toolbar" aria-label="矩阵控制">
      <div>
        <p class="matrix-kicker">COMPARISON SURFACE</p>
        <h2>关键元数据字段</h2>
      </div>
      <div class="matrix-toolbar__filters" aria-label="报告筛选">
        ${icon("i-filter", "icon--14")}
        ${filters
          .map(
            ([filter, label, testId]) =>
              `<button type="button" data-action="set-report-filter" data-filter="${filter}" data-focus-key="report-filter-${filter}" data-testid="${testId}" aria-pressed="${filter === state.reportFilter}">${label}</button>`,
          )
          .join("")}
      </div>
      <p class="matrix-toolbar__count"><strong data-testid="trace-count">${escapeHtml(traces.length)}</strong><span>条当前线索</span></p>
    </section>`;
  }

  function renderEvidenceMatrix(state) {
    const selection = effectiveMatrixSelection(state);
    const activeEvidenceIds = activeMatrixEvidenceIds(state);
    return `<div class="matrix-table-viewport" tabindex="0" aria-label="横向滚动查看全部投标人字段">
      <table class="evidence-matrix" data-testid="evidence-matrix">
        <caption>某市智慧园区建设项目关键元数据字段与投标主体对照</caption>
        <thead>
          <tr>
            <th scope="col">元数据字段</th>
            ${model.demoProject.groups
              .map(
                (group) =>
                  `<th scope="col" data-bidder-id="${escapeHtml(group.id)}" class="${selection?.bidderId === group.id ? "is-column-focused" : ""}"><span>${escapeHtml(group.name)}</span><small>4 份文档</small></th>`,
              )
              .join("")}
          </tr>
        </thead>
        <tbody>
          ${model.demoProject.matrixRows
            .map((row) => renderMatrixRow(row, selection, activeEvidenceIds))
            .join("")}
        </tbody>
      </table>
    </div>`;
  }

  function renderMatrixRow(row, selection, activeEvidenceIds) {
    const rowFocused = Object.entries(row.cells).some(
      ([bidderId, cell]) =>
        selection?.evidenceId === cell.evidenceId && selection?.bidderId === bidderId,
    );
    return `<tr class="matrix-field-row${rowFocused ? " is-focused" : ""}" data-field-id="${escapeHtml(row.id)}" data-testid="matrix-field-row">
      <th scope="row"><span>${escapeHtml(row.label)}</span><small>${escapeHtml(row.id)}</small></th>
      ${model.demoProject.groups
        .map((group) => renderMatrixCell(row, group, selection, activeEvidenceIds))
        .join("")}
    </tr>`;
  }

  function renderMatrixCell(row, group, selection, activeEvidenceIds) {
    const cell = row.cells[group.id];
    const evidence = matrixEvidence(cell.evidenceId);
    const evidenceActive = evidence && activeEvidenceIds.has(evidence.id);
    const tone = evidence?.tone ?? "";
    const selected =
      evidence && selection?.evidenceId === evidence.id && selection?.bidderId === group.id;
    const linked = evidence && selection?.evidenceId === evidence.id;
    const columnFocused = selection?.bidderId === group.id;
    const cellClass = columnFocused ? ' class="is-column-focused"' : "";
    const classes = [
      tone ? `matrix-cell--${tone}` : "",
      selected ? "is-selected" : "",
      linked ? "is-evidence-linked" : "",
      columnFocused ? "is-focused" : "",
    ]
      .filter(Boolean)
      .join(" ");
    if (!evidenceActive) {
      const filteredAttribute = evidence
        ? ` data-filtered-evidence-id="${escapeHtml(evidence.id)}"`
        : "";
      return `<td data-bidder-id="${escapeHtml(group.id)}"${cellClass}><span class="matrix-cell__value"${filteredAttribute}>${escapeHtml(cell.value)}</span></td>`;
    }
    const label = toneLabel(tone);
    return `<td data-bidder-id="${escapeHtml(group.id)}"${cellClass}>
      <button class="matrix-cell ${classes}" type="button" data-action="select-evidence" data-evidence-id="${escapeHtml(evidence.id)}" data-bidder-id="${escapeHtml(group.id)}" data-focus-key="matrix-cell-${escapeHtml(evidence.id)}-${escapeHtml(group.id)}" data-tone="${escapeHtml(tone)}" data-testid="matrix-cell" aria-label="${escapeHtml(`${group.name}，${row.label}：${cell.value}，${label}`)}" aria-pressed="${selected}">
        <span class="matrix-cell__tone">${escapeHtml(label)}</span>
        <span class="matrix-cell__value">${escapeHtml(cell.value)}</span>
      </button>
    </td>`;
  }

  function renderEvidenceDrawer(state, metadataMode) {
    const selection = effectiveMatrixSelection(state);
    const evidence = matrixEvidence(selection?.evidenceId);
    if (!selection || !evidence) return "";
    const parserObservations = evidence.parsers
      .map(
        (parser) => `<li data-testid="parser-observation">
          <strong>${escapeHtml(parser)}</strong>
          <span>记录原始值“${escapeHtml(evidence.rawValue)}”，归一化为“${escapeHtml(evidence.normalizedValue)}”。</span>
        </li>`,
      )
      .join("");
    const closeButton = metadataMode
      ? ""
      : `<button class="button button--quiet" type="button" data-action="close-evidence" data-testid="close-evidence-drawer" aria-label="关闭证据抽屉">${icon("i-x", "icon--14")}<span>关闭证据抽屉</span></button>`;
    return `<section class="evidence-drawer evidence-drawer--${escapeHtml(evidence.tone)}" data-testid="evidence-drawer" aria-labelledby="evidence-drawer-title">
      <header class="evidence-drawer__heading">
        <div>
          <p class="matrix-kicker">SOURCE TRACE / ${escapeHtml(evidence.id)}</p>
          <h2 id="evidence-drawer-title">${escapeHtml(evidence.title)}</h2>
        </div>
        ${closeButton}
      </header>
      <div class="evidence-drawer__facts">
        <dl>
          <div><dt>字段</dt><dd>${escapeHtml(evidence.field)}</dd></div>
          <div><dt>语义</dt><dd><span class="matrix-tone-label matrix-tone-label--${escapeHtml(evidence.tone)}">${escapeHtml(toneLabel(evidence.tone))}</span></dd></div>
          <div><dt>原始值</dt><dd class="evidence-drawer__value">${escapeHtml(evidence.rawValue)}</dd></div>
          <div><dt>归一化值</dt><dd>${escapeHtml(evidence.normalizedValue)}</dd></div>
          <div><dt>涉及投标人</dt><dd>${escapeHtml(evidence.bidders.join("、"))}</dd></div>
          <div><dt>关联文件</dt><dd>${escapeHtml(evidence.files.join("；"))}</dd></div>
        </dl>
        <div class="evidence-drawer__parsers">
          <h3>原始解析证据</h3>
          <p>仅列出实际参与该条证据的解析器，共 ${escapeHtml(evidence.parsers.length)} 项。</p>
          <ul>${parserObservations}</ul>
        </div>
      </div>
    </section>`;
  }

  function effectiveMatrixSelection(state) {
    if (state.view === "metadata" && state.metadataOriginTraceId) {
      const evidence = matrixEvidence(state.metadataOriginTraceId);
      const document = model.demoProject.documents.find((candidate) =>
        evidence?.evidenceIds.includes(candidate.id),
      );
      return evidence && document && activeMatrixEvidenceIds(state).has(evidence.id)
        ? { evidenceId: evidence.id, bidderId: document.bidderId }
        : null;
    }
    if (
      state.matrixSelection &&
      activeMatrixEvidenceIds(state).has(state.matrixSelection.evidenceId)
    ) {
      return state.matrixSelection;
    }
    return null;
  }

  function selectedMatrixEvidence(state) {
    return matrixEvidence(effectiveMatrixSelection(state)?.evidenceId);
  }

  function matrixEvidence(evidenceId) {
    return model.demoProject.matrixEvidence.find((candidate) => candidate.id === evidenceId);
  }

  function activeMatrixEvidenceIds(state) {
    if (state.reportFilter === "all") {
      return new Set(model.demoProject.matrixEvidence.map((evidence) => evidence.id));
    }
    return new Set(model.visibleTraces(state).map((trace) => trace.id));
  }

  function toneLabel(tone) {
    if (tone === "danger") return "高风险";
    if (tone === "caution") return "待复核";
    return "中性上下文";
  }

  Object.assign(namespace.renderers, {
    matrix: renderMatrix,
    matrixTree: renderMatrixTree,
  });
})();

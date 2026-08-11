(function () {
  'use strict';

  // Production state crosses only the authenticated API. Localhost reads the
  // ignored builder artifact so browser QA never needs a live account or bucket.
  var IS_LOOPBACK = /^(localhost|127(?:\.\d{1,3}){3}|\[?::1\]?)$/i.test(window.location.hostname);
  var DATA_URL = IS_LOOPBACK
    ? '/data/fundamental_forensics/private/state.json.gz'
    : '/api/forensics/state';
  var ATTESTED_HISTORY_URL = '/api/forensics/v1/attested-history';
  var DESKTOP_QUERY = '(min-width: 1100px)';
  var state = {
    payload: null,
    // Which of the workbench's mutually exclusive surfaces is on screen.
    // 'pending'/'open' show the workbench; every other value shows the gate.
    access: 'pending',
    symbol: '',
    findingId: '',
    priority: 'all',
    topic: 'all',
    tab: 'radar',
    currentPeriod: 0,
    priorPeriod: 1,
    disclosureSection: 'all',
    disclosureFindingId: '',
    redlineId: '',
    evidenceKind: 'finding',
    searchMatches: [],
    searchIndex: -1,
    loadToken: 0,
    lastFocus: null,
    unknownRequestedSymbol: '',
    sourceMode: 'map',
    receipt: {
      phase: 'idle',
      requestToken: 0,
      latest: null,
      ownerCik: '',
      page: null,
      pageCursors: [null],
      pageIndex: 0,
      rootCellId: '',
      detail: null,
      detailPhase: 'idle',
      lastFocus: null
    }
  };

  var ui = {};
  var desktopMedia = window.matchMedia(DESKTOP_QUERY);
  var gateSigninHtml = '';

  var METRICS = [
    { key: 'revenue', en: 'Revenue', zh: '营收', format: 'currency' },
    { key: 'gross_profit', en: 'Gross profit', zh: '毛利润', format: 'currency' },
    { key: 'receivables', en: 'Receivables', zh: '应收账款', format: 'currency' },
    { key: 'inventory', en: 'Inventory', zh: '存货', format: 'currency' },
    { key: 'cfo', en: 'Cash from operations', zh: '经营现金流', format: 'currency' },
    { key: 'capex', en: 'Capital expenditure', zh: '资本开支', format: 'currency' },
    { key: 'op_income', en: 'Operating income', zh: '营业利润', format: 'currency' },
    { key: 'ni', en: 'Net income', zh: '净利润', format: 'currency' },
    { key: 'contract_liabilities', en: 'Contract liabilities', zh: '合同负债', format: 'currency' }
  ];

  var TOPIC_LABELS = {
    revenue: ['Revenue', '营收'],
    revenue_recognition: ['Revenue recognition', '收入确认'],
    receivables: ['Receivables', '应收账款'],
    receivables_vs_revenue: ['Receivables vs revenue', '应收账款与营收'],
    inventory: ['Inventory', '存货'],
    inventory_vs_revenue: ['Inventory vs revenue', '存货与营收'],
    cash_conversion: ['Cash conversion', '现金转化'],
    working_capital: ['Working capital', '营运资本'],
    capitalized_expenses: ['Capitalized expenses', '费用资本化'],
    capex: ['Capital expenditure', '资本开支'],
    capital_intensity: ['Capital intensity', '资本强度'],
    restructuring: ['Restructuring charges', '重组费用'],
    recurring_charges: ['Recurring charges', '重复性费用'],
    stock_compensation: ['Stock compensation', '股权激励'],
    dilution: ['Dilution', '稀释'],
    non_gaap: ['Non-GAAP adjustments', '非 GAAP 调整'],
    pensions: ['Pensions', '养老金'],
    tax: ['Tax', '税务'],
    customer_concentration: ['Customer concentration', '客户集中度'],
    supplier_concentration: ['Supplier concentration', '供应商集中度'],
    commitments: ['Commitments', '承诺事项'],
    leases: ['Lease obligations', '租赁义务'],
    debt: ['Debt', '债务'],
    debt_refinancing: ['Debt refinancing', '债务再融资'],
    covenants: ['Debt covenants', '债务契约'],
    going_concern: ['Going concern', '持续经营'],
    auditor: ['Auditor', '审计师'],
    auditor_report: ['Auditor report', '审计师报告'],
    material_weakness: ['Material weakness', '重大缺陷'],
    risk_factors: ['Risk factors', '风险因素'],
    business: ['Business', '业务'],
    mda: ['Management discussion', '管理层讨论'],
    financial_statements: ['Financial statements', '财务报表'],
    controls: ['Controls and procedures', '控制与程序'],
    accounting_policies: ['Accounting policies', '会计政策'],
    preamble: ['Filing preamble', '披露前言'],
    segments: ['Segments', '分部'],
    kpi_disappearance: ['Disappearing KPI', '消失的 KPI'],
    margin: ['Margins', '利润率'],
    margins: ['Margins', '利润率']
  };

  function byId(id) { return document.getElementById(id); }

  function cacheUi() {
    ui.workspace = byId('ff-workspace');
    ui.main = byId('ff-main');
    ui.asOf = byId('ff-as-of');
    ui.generatedAt = byId('ff-generated-at');
    ui.sourceLabel = byId('ff-source-label');
    ui.search = byId('ff-company-search');
    ui.searchClear = byId('ff-search-clear');
    ui.companyOptions = byId('ff-company-options');
    ui.companyIdentity = byId('ff-company-identity');
    ui.companyAction = byId('ff-company-action');
    ui.notice = byId('ff-data-notice');
    ui.overview = byId('ff-overview');
    ui.overviewStatus = byId('ff-overview-status');
    ui.quickSignal = byId('ff-quick-signal');
    ui.quickSignalLabel = byId('ff-quick-signal-label');
    ui.quickSignalTitle = byId('ff-quick-signal-title');
    ui.quickSignalSummary = byId('ff-quick-signal-summary');
    ui.statAttention = byId('ff-stat-attention');
    ui.statWatch = byId('ff-stat-watch');
    ui.statCoverage = byId('ff-stat-coverage');
    ui.statSources = byId('ff-stat-sources');
    ui.tabs = Array.prototype.slice.call(document.querySelectorAll('.ff-tab'));
    ui.viewStatus = byId('ff-view-status');
    ui.priorityFilters = byId('ff-priority-filters');
    ui.topic = byId('ff-topic-select');
    ui.filterSummary = byId('ff-filter-summary');
    ui.findings = byId('ff-findings');
    ui.statements = byId('ff-statements');
    ui.disclosureSection = byId('ff-disclosure-section');
    ui.disclosureSummary = byId('ff-disclosure-summary');
    ui.disclosureFeed = byId('ff-disclosure-feed');
    ui.redlineSummary = byId('ff-redline-summary');
    ui.redlineList = byId('ff-redline-list');
    ui.timeline = byId('ff-timeline');
    ui.currentPeriod = byId('ff-current-period');
    ui.priorPeriod = byId('ff-prior-period');
    ui.compareGrid = byId('ff-compare-grid');
    ui.trace = byId('ff-trace');
    ui.sourceTabs = Array.prototype.slice.call(document.querySelectorAll('.ff-source-tab'));
    ui.sourceMapPanel = byId('ff-source-panel-map');
    ui.receiptPanel = byId('ff-source-panel-receipt');
    ui.receipt = byId('ff-receipt');
    ui.evidence = byId('ff-evidence');
    ui.evidenceTitle = byId('ff-evidence-title');
    ui.evidenceBody = byId('ff-evidence-body');
    ui.evidenceClose = byId('ff-evidence-close');
    ui.receiptInspector = byId('ff-receipt-inspector');
    ui.receiptInspectorTitle = byId('ff-receipt-inspector-title');
    ui.receiptInspectorBody = byId('ff-receipt-inspector-body');
    ui.receiptInspectorClose = byId('ff-receipt-inspector-close');
    ui.scrim = byId('ff-scrim');
    ui.siteNav = document.querySelector('.site-nav');
    ui.gate = byId('ff-gate');
    ui.gateState = byId('ff-gate-state');
    ui.gatePreview = byId('ff-gate-preview');
    // The anonymous state is authored in the shell so a stranger and a crawler
    // read it without running JS. Stash it verbatim before any other state
    // overwrites the node: signing out mid-session has to restore exactly this
    // markup, and a second copy of the copy in JS would drift from the shell.
    if (ui.gateState && !gateSigninHtml) gateSigninHtml = ui.gateState.innerHTML;
  }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function pair(en, zh) {
    var safeEn = en == null || en === '' ? '—' : String(en);
    var safeZh = zh == null || zh === '' ? safeEn : String(zh);
    return '<span class="l-en">' + esc(safeEn) + '</span>' +
      '<span class="l-zh">' + esc(safeZh) + '</span>';
  }

  function lang() {
    return document.documentElement.getAttribute('data-lang') === 'zh' ? 'zh' : 'en';
  }

  function localized(value, preferred) {
    if (value == null) return '';
    if (typeof value !== 'object') return String(value);
    var wanted = preferred || lang();
    var alternate = wanted === 'zh' ? (value['zh-Hans'] || value.zh_hans || value.zh_CN) : '';
    return String(value[wanted] || alternate || value.en || value.zh || value.label || value.name || '');
  }

  function fieldPair(obj, stem, fallback) {
    obj = obj || {};
    var en = obj[stem + '_en'];
    var zh = obj[stem + '_zh'];
    if (en == null) en = obj[stem];
    if (en == null) en = fallback || '';
    if (zh == null) zh = en;
    return pair(en, zh);
  }

  function formatDate(value) {
    if (!value) return '—';
    var text = String(value);
    var match = text.match(/^\d{4}-\d{2}-\d{2}/);
    return match ? match[0] : text;
  }

  function translatedDataPhrase(value, preferred) {
    var text = String(value || '');
    if (preferred !== 'zh') return text;
    var known = {
      'SEC Company Facts normalized projection': 'SEC 公司事实标准化投影',
      'repository quarterly and annual EDGAR panels': '仓库内季度及年度 EDGAR 面板',
      'normalized_quarterly_projection': '标准化季度投影',
      'filing_index': '披露索引',
      'companyfacts_source': '公司事实来源'
    };
    return known[text] || text;
  }

  function basisPair(value) {
    var raw = value || 'Source basis unavailable';
    return pair(prettify(raw), translatedDataPhrase(raw, 'zh'));
  }

  function numberValue(value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() !== '') {
      var parsed = Number(value.replace(/,/g, ''));
      if (Number.isFinite(parsed)) return parsed;
    }
    return null;
  }

  function compactNumber(value, digits) {
    var numeric = numberValue(value);
    if (numeric == null) return value == null || value === '' ? '—' : String(value);
    var abs = Math.abs(numeric);
    var precision = digits == null ? 1 : digits;
    if (abs >= 1e12) return (numeric / 1e12).toFixed(precision).replace(/\.0$/, '') + 'T';
    if (abs >= 1e9) return (numeric / 1e9).toFixed(precision).replace(/\.0$/, '') + 'B';
    if (abs >= 1e6) return (numeric / 1e6).toFixed(precision).replace(/\.0$/, '') + 'M';
    if (abs >= 1e3) return (numeric / 1e3).toFixed(precision).replace(/\.0$/, '') + 'K';
    return numeric.toLocaleString('en-US', { maximumFractionDigits: 2 });
  }

  function formatMoney(value) {
    var numeric = numberValue(value);
    if (numeric == null) return value == null || value === '' ? '—' : String(value);
    var sign = numeric < 0 ? '−' : '';
    return sign + '$' + compactNumber(Math.abs(numeric), 1);
  }

  function formatPercent(value) {
    var numeric = numberValue(value);
    if (numeric == null) return value == null || value === '' ? '—' : String(value);
    // State-contract percentages are always decimal ratios, including values
    // above 1.0 (for example 1.869 means 186.9%, never 1.9%).
    var pct = numeric * 100;
    return pct.toLocaleString('en-US', { maximumFractionDigits: 1 }) + '%';
  }

  function formatValue(value, format) {
    var style = String(format || '').toLowerCase();
    if (value == null || value === '') return '—';
    if (/percent|percentage|pct/.test(style)) return formatPercent(value);
    if (/currency|money|usd|dollar/.test(style)) return formatMoney(value);
    if (/multiple|ratio_x|times/.test(style)) {
      var ratio = numberValue(value);
      return ratio == null ? String(value) : ratio.toLocaleString('en-US', { maximumFractionDigits: 2 }) + '×';
    }
    if (/integer|count/.test(style)) {
      var count = numberValue(value);
      return count == null ? String(value) : Math.round(count).toLocaleString('en-US');
    }
    return compactNumber(value, 1);
  }

  function formatSigned(value, format) {
    var numeric = numberValue(value);
    if (numeric == null) return formatValue(value, format);
    if (numeric === 0) return formatValue(numeric, format);
    var prefix = numeric > 0 ? '+' : '−';
    return prefix + formatValue(Math.abs(numeric), format);
  }

  function periodLabel(period) {
    if (!period) return '—';
    var year = period.fiscal_year == null ? '' : String(period.fiscal_year);
    var quarter = period.fiscal_quarter == null ? '' : String(period.fiscal_quarter);
    var label = year && quarter ? 'FY' + year + ' Q' + quarter : [year, quarter].filter(Boolean).join(' ');
    return label || formatDate(period.period_end);
  }

  function prettify(value) {
    var text = String(value || '').replace(/[_-]+/g, ' ').trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Other';
  }

  function topicPair(topic) {
    var key = String(topic || 'other').toLowerCase();
    var known = TOPIC_LABELS[key];
    if (known) return pair(known[0], known[1]);
    return pair(prettify(key), '其他：' + prettify(key));
  }

  function topicText(topic, preferred) {
    var key = String(topic || 'other').toLowerCase();
    var known = TOPIC_LABELS[key];
    if (known) return preferred === 'zh' ? known[1] : known[0];
    return preferred === 'zh' ? '其他：' + prettify(key) : prettify(key);
  }

  function priorityInfo(priority) {
    if (priority === 'high') return { icon: '!', en: 'Needs attention', zh: '需要关注' };
    return { icon: '○', en: 'Keep an eye on', zh: '持续观察' };
  }

  function safeUrl(value) {
    if (!value) return '';
    try {
      var parsed = new URL(String(value), window.location.href);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : '';
    } catch (error) {
      return '';
    }
  }

  function companies() {
    return state.payload && state.payload.companies && typeof state.payload.companies === 'object'
      ? state.payload.companies : {};
  }

  function company() {
    return state.symbol ? companies()[state.symbol] : null;
  }

  function orderedFindings(targetCompany) {
    var findings = targetCompany && Array.isArray(targetCompany.findings) ? targetCompany.findings.slice() : [];
    var ranked = state.payload && Array.isArray(state.payload.ranked_findings) ? state.payload.ranked_findings : [];
    var positions = {};
    ranked.forEach(function (entry, index) {
      if (String(entry.symbol || '').toUpperCase() === state.symbol) positions[String(entry.finding_id)] = index;
    });
    findings.sort(function (a, b) {
      var ai = Object.prototype.hasOwnProperty.call(positions, String(a.id)) ? positions[String(a.id)] : 100000;
      var bi = Object.prototype.hasOwnProperty.call(positions, String(b.id)) ? positions[String(b.id)] : 100000;
      if (ai !== bi) return ai - bi;
      if (a.priority === b.priority) return 0;
      return a.priority === 'high' ? -1 : 1;
    });
    return findings;
  }

  function selectedFinding() {
    var findings = orderedFindings(company());
    for (var index = 0; index < findings.length; index += 1) {
      if (String(findings[index].id) === String(state.findingId)) return findings[index];
    }
    return null;
  }

  function selectedFindingButton() {
    return Array.prototype.find.call(ui.findings.querySelectorAll('[data-finding-id]'), function (candidate) {
      return candidate.getAttribute('data-finding-id') === state.findingId;
    }) || null;
  }

  // Wave 2 disclosure state is deliberately optional. The filing-diff producer
  // is additive to the v1 normalized statement contract, so a company without
  // a comparable accession pair must render an honest empty state rather than a
  // synthetic redline or an inferred text result.
  function objectValue(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  }

  function disclosureBundle(target) {
    var candidates = target ? [
      target.disclosure_bundle,
      target.disclosures,
      target.filing_disclosures,
      target.filing_diff
    ] : [];
    for (var index = 0; index < candidates.length; index += 1) {
      var candidate = candidates[index];
      if (Array.isArray(candidate)) {
        for (var itemIndex = candidate.length - 1; itemIndex >= 0; itemIndex -= 1) {
          if (objectValue(candidate[itemIndex])) return candidate[itemIndex];
        }
      }
      if (objectValue(candidate)) return candidate;
    }
    return {};
  }

  function disclosureTracks(target) {
    var bundle = disclosureBundle(target || company());
    return (Array.isArray(bundle.tracks) ? bundle.tracks : []).filter(function (track) {
      return objectValue(track);
    });
  }

  function disclosureTrackClock(track) {
    var filing = objectValue(track && track.current_filing) || {};
    var clocks = objectValue(filing.clocks) || objectValue(track && track.clocks) || {};
    return String(clocks.accepted_at || filing.filed_at || filing.filed || track.as_of || '').replace(/[^0-9TZ:+-]/g, '');
  }

  function readyDisclosureTracks(target) {
    var ready = disclosureTracks(target).filter(function (track) {
      return objectValue(track.comparison) && String(track.status || 'ready').toLowerCase() === 'ready';
    });
    ready.sort(function (left, right) {
      var rightClock = disclosureTrackClock(right);
      var leftClock = disclosureTrackClock(left);
      if (rightClock !== leftClock) return rightClock.localeCompare(leftClock);
      return String(right.form || '').localeCompare(String(left.form || ''));
    });
    return ready;
  }

  function selectedDisclosureTrack(target) {
    return readyDisclosureTracks(target)[0] || null;
  }

  function disclosureComparison(target) {
    var bundle = disclosureBundle(target);
    var track = selectedDisclosureTrack(target);
    var candidates = [
      track && track.comparison,
      bundle.comparison,
      bundle.latest_comparison,
      bundle.disclosure_comparison,
      bundle
    ];
    for (var index = 0; index < candidates.length; index += 1) {
      var candidate = objectValue(candidates[index]);
      if (!candidate) continue;
      if (candidate.prior_document || candidate.current_document || candidate.redline_ops || candidate.redlines || candidate.findings) return candidate;
    }
    return {};
  }

  function disclosureFindings(target) {
    target = target || company();
    var tracks = readyDisclosureTracks(target);
    if (tracks.length) {
      var tracked = [];
      tracks.forEach(function (track) {
        var comparison = objectValue(track.comparison) || {};
        (Array.isArray(comparison.findings) ? comparison.findings : []).forEach(function (item) {
          if (!objectValue(item)) return;
          tracked.push(Object.assign({}, item, { _track_form: String(track.form || '') }));
        });
      });
      return tracked;
    }
    var comparison = disclosureComparison(target);
    var bundle = disclosureBundle(target);
    var values = Array.isArray(comparison.findings) ? comparison.findings :
      (Array.isArray(bundle.findings) ? bundle.findings : []);
    return values.filter(function (item) { return objectValue(item); });
  }

  function disclosureRedlines(target) {
    target = target || company();
    var tracks = readyDisclosureTracks(target);
    if (tracks.length) {
      var tracked = [];
      tracks.forEach(function (track) {
        var comparison = objectValue(track.comparison) || {};
        var values = Array.isArray(comparison.redline_ops) ? comparison.redline_ops :
          (Array.isArray(comparison.redlines) ? comparison.redlines : []);
        values.forEach(function (item) {
          if (!objectValue(item)) return;
          tracked.push(Object.assign({}, item, { _track_form: String(track.form || '') }));
        });
      });
      return tracked;
    }
    var comparison = disclosureComparison(target);
    var bundle = disclosureBundle(target);
    var values = Array.isArray(comparison.redline_ops) ? comparison.redline_ops :
      (Array.isArray(comparison.redlines) ? comparison.redlines :
        (Array.isArray(bundle.redline_ops) ? bundle.redline_ops :
          (Array.isArray(bundle.redlines) ? bundle.redlines : [])));
    return values.filter(function (item) { return objectValue(item); });
  }

  function disclosureDocuments(target) {
    target = target || company();
    var comparison = disclosureComparison(target);
    var bundle = disclosureBundle(target);
    var values = [];
    function appendDocument(item, form, role) {
      if (!objectValue(item)) return;
      var accession = String(item.accession || '');
      var duplicate = values.some(function (saved) {
        return saved === item || (accession && accession === String(saved.accession || ''));
      });
      if (!duplicate) values.push(Object.assign({}, item, { _track_form: form || item.form || '', _filing_role: role || '' }));
    }
    readyDisclosureTracks(target).forEach(function (track) {
      appendDocument(track.prior_filing, String(track.form || ''), 'prior');
      appendDocument(track.current_filing, String(track.form || ''), 'current');
    });
    [
      comparison.prior_document,
      comparison.current_document,
      bundle.prior_document,
      bundle.current_document
    ].forEach(function (item) {
      appendDocument(item, '', '');
    });
    if (Array.isArray(bundle.documents)) {
      bundle.documents.forEach(function (item) {
        appendDocument(item, '', '');
      });
    }
    return values;
  }

  function disclosureSectionById(sectionId) {
    if (!sectionId) return '';
    var comparisons = readyDisclosureTracks(company()).map(function (track) {
      return objectValue(track.comparison) || {};
    });
    if (!comparisons.length) comparisons.push(disclosureComparison(company()));
    var groups = [];
    comparisons.forEach(function (comparison) {
      var sectionGroups = comparison.sections || {};
      groups.push(sectionGroups.prior, sectionGroups.current, comparison.prior_sections, comparison.current_sections);
    });
    for (var index = 0; index < groups.length; index += 1) {
      var sections = Array.isArray(groups[index]) ? groups[index] : [];
      for (var sectionIndex = 0; sectionIndex < sections.length; sectionIndex += 1) {
        if (String(sections[sectionIndex].section_id || '') === String(sectionId)) return String(sections[sectionIndex].key || '');
      }
    }
    return '';
  }

  function disclosureFindingSection(finding) {
    if (!finding) return 'other';
    if (finding.section_key) return String(finding.section_key);
    var sectionIds = [];
    if (Array.isArray(finding.current_section_ids)) sectionIds = sectionIds.concat(finding.current_section_ids);
    if (Array.isArray(finding.prior_section_ids)) sectionIds = sectionIds.concat(finding.prior_section_ids);
    var receipts = Array.isArray(finding.evidence_receipts) ? finding.evidence_receipts : [];
    receipts.forEach(function (receipt) {
      if (receipt && receipt.section_id) sectionIds.push(receipt.section_id);
    });
    for (var index = 0; index < sectionIds.length; index += 1) {
      var section = disclosureSectionById(sectionIds[index]);
      if (section) return section;
    }
    return 'other';
  }

  function disclosureFindingId(finding) {
    return String((finding && (finding.finding_id || finding.id || finding.key)) || '');
  }

  function redlineId(redline) {
    return String((redline && (redline.op_id || redline.id || redline.key)) || '');
  }

  function selectedDisclosureFinding() {
    var wanted = String(state.disclosureFindingId || '');
    return disclosureFindings().find(function (finding) { return disclosureFindingId(finding) === wanted; }) || null;
  }

  function selectedRedline() {
    var wanted = String(state.redlineId || '');
    return disclosureRedlines().find(function (redline) { return redlineId(redline) === wanted; }) || null;
  }

  function selectedEvidenceButton() {
    var attribute = state.evidenceKind === 'disclosure-finding' ? 'data-disclosure-finding-id' :
      state.evidenceKind === 'redline' ? 'data-redline-id' : 'data-finding-id';
    var wanted = state.evidenceKind === 'disclosure-finding' ? state.disclosureFindingId :
      state.evidenceKind === 'redline' ? state.redlineId : state.findingId;
    return Array.prototype.find.call(document.querySelectorAll('[' + attribute + ']'), function (candidate) {
      return candidate.getAttribute(attribute) === String(wanted);
    }) || null;
  }

  function setLoading() {
    ui.viewStatus.innerHTML = pair('Loading filing data…', '正在载入财报数据…');
    var loading = '<div class="ff-loading" role="status"><span class="ff-loading-dot" aria-hidden="true"></span>' +
      pair('Loading filing review data…', '正在载入财报审阅数据…') + '</div>';
    ui.findings.innerHTML = loading;
    ui.statements.innerHTML = loading;
    ui.disclosureFeed.innerHTML = loading;
    ui.redlineList.innerHTML = loading;
    ui.timeline.innerHTML = loading;
    ui.compareGrid.innerHTML = loading;
    ui.trace.innerHTML = loading;
  }

  // Same shape as receiptFailurePhase() below, which already separates "you may
  // not read this" from "this is broken" for the private receipt pane. The main
  // loader used to collapse both into one 'Data unavailable' card, so a visitor
  // who simply was not signed in was told the product was broken and handed a
  // Retry button that could never work.
  //
  // The three denials are distinct products of app/forensics.py: 401 from the
  // authentication dependency, 403 from the site_full entitlement check, and 503
  // when the state object itself is missing. Anything without a status (offline,
  // a decode failure, a contract violation) is a genuine fault, so it takes the
  // temporary branch and keeps its Retry.
  function stateFailurePhase(error) {
    var status = error && error.status;
    if (status === 401) return 'signin';
    if (status === 403) return 'upgrade';
    return 'unavailable';
  }

  var GATE_COPY = {
    upgrade: {
      chip: ['Included in Essential', 'Essential 包含'],
      title: ['Not in your plan', '当前方案未包含'],
      stance: [
        'Essential opens the findings, the rules behind them, and the SEC sources.',
        'Essential 可查阅全部发现、触发它们的规则，以及对应的 SEC 来源。'
      ],
      primary: ['View Essential plans', '查看 Essential 方案'],
      primaryAction: 'plans'
    },
    unavailable: {
      chip: ['Temporary', '暂时'],
      title: ['Data is being refreshed', '数据正在更新'],
      stance: [
        'Nothing is wrong with your account. Try again in a few minutes.',
        '这与你的账户无关，请稍后几分钟再试。'
      ],
      primary: ['Retry', '重试'],
      primaryAction: 'retry'
    },
    empty: {
      chip: ['Coverage', '覆盖范围'],
      title: ['No companies this run', '本次更新没有公司'],
      stance: [
        'This is not an all-clear — the latest run added no companies to review.',
        '这不代表“没有问题”——本次更新未纳入可审阅的公司。'
      ],
      note: ['Check back after the next filing run.', '下次披露更新后再来查看。']
    }
  };

  function renderGateState(phase) {
    var copy = GATE_COPY[phase];
    if (!copy) return;
    var actions = '';
    if (copy.primary) {
      actions = '<div class="ff-gate-actions"><button class="ff-gate-primary" type="button" data-gate-action="' +
        copy.primaryAction + '">' + pair(copy.primary[0], copy.primary[1]) + '</button></div>';
    } else if (copy.note) {
      actions = '<p class="ff-gate-note">' + pair(copy.note[0], copy.note[1]) + '</p>';
    }
    ui.gateState.innerHTML = '<p class="ff-gate-chip"><span class="ff-gate-dot" aria-hidden="true"></span>' +
      pair(copy.chip[0], copy.chip[1]) + '</p>' +
      '<h2 id="ff-gate-title">' + pair(copy.title[0], copy.title[1]) + '</h2>' +
      '<p class="ff-gate-stance">' + pair(copy.stance[0], copy.stance[1]) + '</p>' + actions;
  }

  // One surface is on screen at a time: the workbench, or the gate. Routing both
  // through here is what keeps a half-populated workbench from sitting under an
  // error, which is how the old error path left the tab bar, the filter chrome
  // and the company picker live over seven panels of "Data unavailable".
  function setAccess(next) {
    ui.gate.removeAttribute('aria-busy');
    if (state.access === next) return;
    state.access = next;
    var gated = next !== 'pending' && next !== 'open';
    ui.workspace.setAttribute('data-access', next);
    ui.workspace.classList.toggle('ff-gated', gated);
    ui.gate.hidden = !gated;
    if (!gated) return;
    // The gate carries the whole message; a second copy in the notice strip
    // would be the stacked-disclaimer defect the copy law forbids.
    ui.notice.hidden = true;
    ui.notice.innerHTML = '';
    // Both funnel states get the product story; the two states behind the wall
    // do not. A Free member is the visitor closest to paying, so showing them
    // less than a stranger gets is backwards — and the preview holds no rows, so
    // there is nothing to withhold. A signed-in Essential member hitting a
    // refresh or an empty run already owns the desk: pitching it back to them is
    // noise over the one thing they came for, which is when to return.
    ui.gatePreview.hidden = next !== 'signin' && next !== 'upgrade';
    ui.gateState.setAttribute('data-state', next);
    if (next === 'signin') ui.gateState.innerHTML = gateSigninHtml;
    else renderGateState(next);
  }

  function openPlans() {
    if (window.MMOnboard && typeof window.MMOnboard.open === 'function') {
      window.MMOnboard.open('upgrade', { plan: 'essential', period: 'annual' });
      return;
    }
    window.location.href = '/plans.html';
  }

  function openSignin() {
    if (window.MMXAccessPreview && typeof window.MMXAccessPreview.openSignin === 'function') {
      window.MMXAccessPreview.openSignin();
      return;
    }
    if (window.MDXAuth && typeof window.MDXAuth.open === 'function') {
      window.MDXAuth.open('signin');
      return;
    }
    window.location.href = '/?signin=1';
  }

  function showLoadError(error) {
    var phase = stateFailurePhase(error);
    setAccess(phase);
    ui.viewStatus.innerHTML = phase === 'signin' ? pair('Sign in to read the desk', '登录后查阅') :
      phase === 'upgrade' ? pair('Included in Essential', 'Essential 包含') :
        pair('Data is being refreshed', '数据正在更新');
  }

  function withAuth(headers) {
    headers = headers || {};
    if (IS_LOOPBACK || !(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(headers);
    return window.MDXAuth.client()
      .then(function (client) { return client.auth.getSession(); })
      .then(function (result) {
        var token = result && result.data && result.data.session && result.data.session.access_token;
        if (token) headers.Authorization = 'Bearer ' + token;
        return headers;
      })
      .catch(function () { return headers; });
  }

  function loadData() {
    var token = state.loadToken + 1;
    state.loadToken = token;
    setLoading();
    ui.notice.hidden = true;
    ui.notice.className = 'ff-data-notice';
    // Deliberately does NOT reset access to 'pending'. A retry from the
    // refreshing state should keep showing that state until the answer changes;
    // dropping back to the skeleton would flash a loading state at a visitor who
    // is already being told to wait, and would flash it at every anonymous
    // visitor between init() and the 401.
    ui.gate.setAttribute('aria-busy', 'true');

    withAuth({ Accept: 'application/gzip' })
      .then(function (headers) {
        return fetch(DATA_URL, {
          headers: headers,
          credentials: 'same-origin',
          cache: 'no-store'
        });
      })
      .then(function (response) {
        if (!response.ok) {
          // Carry the status onto the error the way historyRequest() does: it is
          // the only thing that tells signed-out from unentitled from broken.
          var failure = new Error('State request failed');
          failure.status = response.status;
          throw failure;
        }
        // Inspect the received bytes instead of trusting Content-Encoding. Fetch
        // may already have decoded a proxy encoding; a literal private .gz object
        // still carries the gzip magic bytes. This also survives accidental outer
        // proxy compression without attempting to parse the inner gzip as JSON.
        return response.arrayBuffer().then(function (buffer) {
          var bytes = new Uint8Array(buffer);
          var isGzip = bytes.length > 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
          if (!isGzip) return new Response(buffer).json();
          if (typeof window.DecompressionStream !== 'function') {
            throw new Error('This browser cannot open the protected compressed state');
          }
          var stream = new Blob([buffer]).stream().pipeThrough(new window.DecompressionStream('gzip'));
          return new Response(stream).json();
        });
      })
      .then(function (payload) {
        if (token !== state.loadToken) return;
        if (!payload || !payload.companies || typeof payload.companies !== 'object') {
          throw new Error('Invalid state contract');
        }
        state.payload = payload;
        // A run that covers nobody is a fact about the run, not a failure and
        // not an all-clear, so it gets its own gate state rather than seven
        // panels of empty cards behind a live tab bar.
        setAccess(Object.keys(payload.companies).length ? 'open' : 'empty');
        if (state.access === 'empty') return;
        selectInitialCompany();
        renderAll();
      })
      .catch(function (error) {
        if (token !== state.loadToken) return;
        showLoadError(error);
      });
  }

  function requestedSymbol() {
    var params = new URLSearchParams(window.location.search);
    return String(params.get('symbol') || '').trim().toUpperCase();
  }

  function resolveSymbol(candidate) {
    var keys = Object.keys(companies());
    var wanted = String(candidate || '').toUpperCase();
    for (var index = 0; index < keys.length; index += 1) {
      if (keys[index].toUpperCase() === wanted) return keys[index];
    }
    return '';
  }

  function selectInitialCompany() {
    var keys = Object.keys(companies());
    var requested = requestedSymbol();
    var preferred = resolveSymbol(requested);
    var defaultSymbol = resolveSymbol(state.payload.default_symbol);
    state.unknownRequestedSymbol = requested && !preferred ? requested : '';
    setCompany(preferred || defaultSymbol || keys[0] || '', false);
  }

  function setCompany(symbol, updateUrl) {
    var resolved = resolveSymbol(symbol);
    if (!resolved) return;
    state.symbol = resolved;
    state.priority = 'all';
    state.topic = 'all';
    state.currentPeriod = 0;
    var periods = company() && Array.isArray(company().periods) ? company().periods : [];
    state.priorPeriod = periods.length > 1 ? 1 : 0;
    var findings = orderedFindings(company());
    state.findingId = findings.length ? String(findings[0].id) : '';
    state.disclosureSection = 'all';
    state.disclosureFindingId = '';
    state.redlineId = '';
    state.evidenceKind = 'finding';
    resetReceiptState();
    ui.search.value = resolved;
    ui.searchClear.hidden = false;
    closeSearch();
    closeEvidence(false);
    if (updateUrl) {
      var next = new URL(window.location.href);
      next.searchParams.set('symbol', resolved);
      window.history.pushState({ symbol: resolved }, '', next.pathname + next.search + next.hash);
      state.unknownRequestedSymbol = '';
    }
    renderCompany();
    if (state.sourceMode === 'receipt') ensureReceiptForCompany();
  }

  function renderAll() {
    renderRunMeta();
    renderCompany();
    setTab(state.tab, false);
  }

  function renderRunMeta() {
    var source = state.payload.source || {};
    ui.asOf.textContent = formatDate(state.payload.as_of);
    ui.generatedAt.textContent = formatDate(state.payload.generated_at);
    var sourceName = translatedDataPhrase(
      localized(source.label, lang()) || localized(source.basis, lang()), lang()
    ) || '—';
    ui.sourceLabel.textContent = sourceName;
  }

  function renderCompany() {
    var target = company();
    if (!target) {
      renderNoCompanies();
      return;
    }
    var symbol = target.symbol || state.symbol;
    var identityCore = [target.sector, target.latest_period].filter(Boolean).join(' · ');
    var identityDetailEn = [identityCore, target.latest_filed ? 'Filed ' + formatDate(target.latest_filed) : ''].filter(Boolean).join(' · ');
    var identityDetailZh = [identityCore, target.latest_filed ? '披露于 ' + formatDate(target.latest_filed) : ''].filter(Boolean).join(' · ');
    ui.companyIdentity.innerHTML = '<div class="ff-company-mark" aria-hidden="true">' + esc(String(symbol).slice(0, 5)) + '</div>' +
      '<div><div class="ff-company-name">' + esc(target.name || symbol) + '</div>' +
      '<div class="ff-company-detail">' + pair(identityDetailEn || '—', identityDetailZh || '—') + '</div></div>';

    var findings = orderedFindings(target);
    var highCount = findings.filter(function (item) { return item.priority === 'high'; }).length;
    var watchCount = findings.filter(function (item) { return item.priority === 'watch'; }).length;
    var action = target.action || {};
    var actionKey = action.key || (highCount ? 'high' : watchCount ? 'watch' : 'covered');
    var actionEn = actionKey === 'high'
      ? highCount + (highCount === 1 ? ' needs attention' : ' need attention')
      : actionKey === 'watch'
        ? watchCount + ' to watch'
        : actionKey === 'limited' ? 'Some checks could not run' : 'No unusual change in covered checks';
    var actionZh = actionKey === 'high'
      ? highCount + ' 项变化需要关注'
      : actionKey === 'watch'
        ? watchCount + ' 项变化值得持续观察'
        : actionKey === 'limited' ? '部分检查无法运行' : '已覆盖检查暂无异常变化';
    var actionIcon = actionKey === 'high' ? '!' : actionKey === 'watch' ? '○' : actionKey === 'limited' ? '?' : '✓';
    ui.companyAction.setAttribute('data-action', actionKey);
    ui.companyAction.innerHTML = '<span class="ff-action-glyph" aria-hidden="true">' + actionIcon + '</span>' +
      '<span class="ff-action-copy">' + pair(actionEn, actionZh) + '</span>';

    renderNotice(target);
    renderOverview(target, findings);
    renderTopicOptions(findings);
    renderFindings();
    renderStatements(target);
    renderDisclosureControls(target);
    renderDisclosureFeed(target);
    renderRedlines(target);
    renderTimeline(target);
    renderCompareControls(target);
    renderCompare(target);
    renderTrace(target);
    renderCurrentEvidence();
    updateViewStatus();
  }

  function renderOverview(target, findings) {
    findings = Array.isArray(findings) ? findings : [];
    var high = findings.filter(function (item) { return item.priority === 'high'; });
    var watch = findings.filter(function (item) { return item.priority === 'watch'; });
    var coverage = target.coverage || {};
    var coverageValue = numberValue(coverage.metrics_pct);
    var evidenceCount = findings.reduce(function (total, finding) {
      return total + (Array.isArray(finding.evidence) ? finding.evidence.length : 0);
    }, 0);
    var first = high[0] || watch[0] || findings[0] || null;

    ui.statAttention.textContent = String(high.length);
    ui.statWatch.textContent = String(watch.length);
    ui.statCoverage.textContent = coverageValue == null ? '—' : formatPercent(coverageValue);
    ui.statSources.textContent = String(evidenceCount);

    var statusKey = high.length ? 'attention' : watch.length ? 'watch' : first ? 'watch' : 'clear';
    ui.overviewStatus.setAttribute('data-state', statusKey);
    ui.overviewStatus.innerHTML = high.length
      ? pair(high.length + ' change' + (high.length === 1 ? '' : 's') + ' need attention', high.length + ' 项变化需要关注')
      : watch.length
        ? pair(watch.length + ' change' + (watch.length === 1 ? '' : 's') + ' to watch', watch.length + ' 项变化值得观察')
        : pair('No unusual change in covered checks', '已覆盖检查暂无异常变化');

    if (!first) {
      ui.quickSignal.setAttribute('data-priority', 'clear');
      ui.quickSignalLabel.innerHTML = pair('Latest covered comparison', '最新已覆盖对比');
      ui.quickSignalTitle.innerHTML = pair('No unusual change surfaced', '暂无异常变化');
      ui.quickSignalSummary.innerHTML = pair(
        'That is not a clean-company verdict. Check the coverage and source limitations before drawing a conclusion.',
        '这并不代表公司没有问题。得出结论前，请先查看覆盖范围和来源局限。'
      );
      var emptyTrigger = ui.quickSignal.querySelector('[data-open-primary-finding]');
      if (emptyTrigger) {
        emptyTrigger.setAttribute('data-go-tab', 'trace');
        emptyTrigger.removeAttribute('data-open-primary-finding');
        emptyTrigger.innerHTML = pair('Check coverage and sources', '查看覆盖范围和来源') + ' <span aria-hidden="true">→</span>';
      }
      return;
    }

    ui.quickSignal.setAttribute('data-priority', first.priority || 'watch');
    ui.quickSignalLabel.innerHTML = first.priority === 'high'
      ? pair('First thing to understand', '首先需要了解')
      : pair('Worth keeping an eye on', '值得持续观察');
    ui.quickSignalTitle.innerHTML = fieldPair(first, 'title', 'Filing change');
    ui.quickSignalSummary.innerHTML = fieldPair(first, 'summary', 'Open this signal to see the numbers and source.');
    var trigger = ui.quickSignal.querySelector('.ff-quick-signal-open');
    if (trigger) {
      trigger.setAttribute('data-open-primary-finding', '');
      trigger.removeAttribute('data-go-tab');
      trigger.innerHTML = pair('See why it matters', '查看为什么重要') + ' <span aria-hidden="true">→</span>';
    }
  }

  // Coverage-less runs are one product state, so they get one home. This used to
  // paint seven "The current state file contains no company records" cards —
  // machine vocabulary aimed at a reader who cannot act on it, under a live tab
  // bar that implied there was something behind the other six tabs.
  function renderNoCompanies() {
    setAccess('empty');
    ui.viewStatus.innerHTML = pair('No companies this run', '本次更新没有公司');
  }

  function renderNotice(target) {
    var coverage = target.coverage || {};
    var source = state.payload.source || {};
    var pct = numberValue(coverage.metrics_pct);
    var limitationsEn = Array.isArray(source.limitations_en) ? source.limitations_en : [];
    var limitationsZh = Array.isArray(source.limitations_zh) ? source.limitations_zh : [];
    var headline = '';
    var details = '';

    if (state.unknownRequestedSymbol) {
      headline = pair(state.unknownRequestedSymbol + ' is not covered yet, so we are showing ' + state.symbol + '.',
        '尚未覆盖 ' + state.unknownRequestedSymbol + '，现显示 ' + state.symbol + '。');
    } else if (pct != null && (pct <= 1 ? pct < 0.999 : pct < 99.9)) {
      headline = pair(
        'We could compare ' + formatPercent(pct) + ' of the expected metrics. Missing values were left blank.',
        '本次可对比 ' + formatPercent(pct) + ' 的预期指标；缺失值保持空白。'
      );
    }
    if (limitationsEn.length || limitationsZh.length) {
      details = '<details class="ff-coverage-details"><summary>' + pair('About this coverage', '关于本次覆盖') +
        '</summary><p>' + pair(limitationsEn[0] || limitationsZh[0], limitationsZh[0] || limitationsEn[0]) + '</p></details>';
    }
    if (!headline && !details) {
      ui.notice.hidden = true;
      ui.notice.innerHTML = '';
      return;
    }
    ui.notice.className = 'ff-data-notice';
    ui.notice.hidden = false;
    ui.notice.innerHTML = '<span class="ff-notice-icon" aria-hidden="true">i</span><div>' +
      (headline || pair('Coverage details are available.', '可查看覆盖范围详情。')) + details + '</div>';
  }

  function renderTopicOptions(findings) {
    var topics = [];
    findings.forEach(function (finding) {
      var topic = String(finding.topic || 'other');
      if (topics.indexOf(topic) === -1) topics.push(topic);
    });
    var current = topics.indexOf(state.topic) >= 0 ? state.topic : 'all';
    state.topic = current;
    var html = '<option value="all">' + (lang() === 'zh' ? '全部主题' : 'All topics') + '</option>';
    topics.sort().forEach(function (topic) {
      html += '<option value="' + esc(topic) + '">' + esc(topicText(topic, lang())) + '</option>';
    });
    ui.topic.innerHTML = html;
    ui.topic.value = current;
  }

  function filteredFindings() {
    return orderedFindings(company()).filter(function (finding) {
      var priorityMatch = state.priority === 'all' || finding.priority === state.priority;
      var topicMatch = state.topic === 'all' || String(finding.topic || 'other') === state.topic;
      return priorityMatch && topicMatch;
    });
  }

  function renderFindings() {
    var all = orderedFindings(company());
    var visible = filteredFindings();
    var counts = {
      all: all.length,
      high: all.filter(function (item) { return item.priority === 'high'; }).length,
      watch: all.filter(function (item) { return item.priority === 'watch'; }).length
    };
    Object.keys(counts).forEach(function (key) {
      var node = document.querySelector('[data-count-for="' + key + '"]');
      if (node) node.textContent = String(counts[key]);
    });
    Array.prototype.forEach.call(ui.priorityFilters.querySelectorAll('[data-priority]'), function (button) {
      var active = button.getAttribute('data-priority') === state.priority;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    ui.filterSummary.innerHTML = pair(visible.length + ' of ' + all.length + ' signals',
      '显示 ' + visible.length + ' / ' + all.length + ' 个信号');

    if (!visible.length) {
      var hasAny = all.length > 0;
      var target = company() || {};
      var coverage = target.coverage || {};
      var actionKey = (target.action || {}).key;
      var evaluable = numberValue(coverage.detectors_evaluable);
      var detectorTotal = numberValue(coverage.detectors_total);
      var coverageLimited = !hasAny && (
        actionKey === 'limited' || (evaluable != null && detectorTotal != null && evaluable < detectorTotal)
      );
      var coverageDetailEn = evaluable != null && detectorTotal != null
        ? 'Only ' + evaluable + ' of ' + detectorTotal + ' checks were evaluable; missing checks remain unknown.'
        : 'Some checks were not evaluable; missing checks remain unknown.';
      var coverageDetailZh = evaluable != null && detectorTotal != null
        ? '仅 ' + evaluable + ' / ' + detectorTotal + ' 项检查可评估；缺失检查仍为未知。'
        : '部分检查无法评估；缺失检查仍为未知。';
      ui.findings.innerHTML = emptyState(
        hasAny ? 'No findings match these filters' : coverageLimited ? 'Coverage incomplete' : 'No review prompt in covered checks',
        hasAny ? '没有符合筛选条件的发现' : coverageLimited ? '检查覆盖不完整' : '已覆盖检查暂无复核提示',
        hasAny ? 'Change the priority or topic filter.' : coverageLimited ? coverageDetailEn : 'This is not a clean-company verdict; inspect coverage and limitations in Sources.',
        hasAny ? '请调整优先级或主题筛选。' : coverageLimited ? coverageDetailZh : '这并非“公司无问题”的结论；请在证据链中查看覆盖范围与局限。',
        hasAny ? '↺' : coverageLimited ? '?' : '✓');
      if (!hasAny) {
        state.findingId = '';
        if (state.evidenceKind === 'finding') renderEvidence(null);
      }
      return;
    }

    var selectedVisible = visible.some(function (finding) { return String(finding.id) === String(state.findingId); });
    if (!selectedVisible) state.findingId = String(visible[0].id);

    ui.findings.innerHTML = visible.map(function (finding) {
      var priority = priorityInfo(finding.priority);
      var selected = String(finding.id) === String(state.findingId);
      var periods = [finding.period_current, finding.period_prior].filter(Boolean);
      var periodText = periods.length > 1 ? periods[0] + ' vs ' + periods[1] : periods[0] || '—';
      return '<div role="listitem"><button type="button" class="ff-finding' + (selected ? ' is-selected' : '') + '"' +
        ' data-finding-id="' + esc(finding.id) + '" data-priority="' + esc(finding.priority || 'watch') + '"' +
        ' aria-current="' + (selected ? 'true' : 'false') + '" aria-controls="ff-evidence">' +
        '<span class="ff-priority-mark" aria-hidden="true">' + priority.icon + '</span>' +
        '<span class="ff-finding-copy"><span class="ff-finding-overline"><span class="ff-priority-label">' +
        pair(priority.en, priority.zh) + '</span><span aria-hidden="true">·</span><span>' + topicPair(finding.topic) + '</span></span>' +
        '<h3>' + fieldPair(finding, 'title', 'Untitled finding') + '</h3>' +
        '<span class="ff-finding-summary">' + fieldPair(finding, 'summary', 'No summary supplied.') + '</span></span>' +
        '<span class="ff-finding-periods"><strong>' + esc(periodText) + '</strong>' +
        pair('Why this matters', '为什么重要') + ' <span aria-hidden="true">→</span></span></button></div>';
    }).join('');
    if (state.evidenceKind === 'finding') renderEvidence(selectedFinding());
  }

  function emptyState(titleEn, titleZh, copyEn, copyZh, mark) {
    return '<div class="ff-empty-state"><div><span class="ff-empty-mark" aria-hidden="true">' + esc(mark || '—') + '</span>' +
      '<h3>' + pair(titleEn, titleZh) + '</h3><p>' + pair(copyEn, copyZh) + '</p></div></div>';
  }

  function disclosureSectionPair(section) {
    var normalized = String(section || 'other').toLowerCase();
    if (normalized === 'other') return pair('Other disclosure', '其他披露');
    return topicPair(normalized);
  }

  function disclosureSectionText(section, preferred) {
    var normalized = String(section || 'other').toLowerCase();
    if (normalized === 'other') return preferred === 'zh' ? '其他披露' : 'Other disclosure';
    return topicText(normalized, preferred);
  }

  function documentDate(document) {
    if (!document) return '—';
    return formatDate(document.filed_at || document.filing_date || document.filed || document.report_date);
  }

  function documentSourceUrl(document) {
    return safeUrl(document && (document.source_url || document.url || document.filing_url));
  }

  function documentAccession(document) {
    return String((document && (document.accession || document.accession_number || document.id)) || '—');
  }

  function disclosureFindingState(finding) {
    var status = String((finding && (finding.state || finding.review_level || finding.status)) || '').toLowerCase();
    if (status === 'triggered' || status === 'manual_review' || status === 'review') {
      return { key: 'review', icon: '◇', en: 'Observed change', zh: '观察到变化' };
    }
    if (status === 'clear' || status === 'no_review') {
      return { key: 'clear', icon: '·', en: 'No review prompt', zh: '未出现复核提示' };
    }
    return { key: 'limited', icon: '?', en: 'Needs source review', zh: '需查看来源' };
  }

  function disclosureFindingLabel(finding) {
    var labels = finding && (finding.labels || finding.label);
    var en = localized(labels, 'en') || (finding && (finding.title_en || finding.title || finding.detector_id)) || 'Disclosure change';
    var zh = localized(labels, 'zh') || (finding && (finding.title_zh || finding.title || finding.detector_id)) || '披露变化';
    return pair(en, zh);
  }

  function readablePhraseList(raw, preferred) {
    var labels = {
      monthly_active_users: ['monthly active users', '月活跃用户'],
      daily_active_users: ['daily active users', '日活跃用户'],
      net_revenue_retention: ['net revenue retention', '净收入留存率'],
      active_customers: ['active customers', '活跃客户'],
      paying_customers: ['paying customers', '付费客户'],
      subscribers: ['subscribers', '订阅用户'],
      same_store_sales: ['same-store sales', '同店销售'],
      orders: ['orders', '订单']
    };
    return String(raw || '').split(',').filter(Boolean).map(function (item) {
      var value = labels[item];
      return value ? value[preferred === 'zh' ? 1 : 0] : prettify(item);
    }).join(preferred === 'zh' ? '、' : ', ');
  }

  function disclosureWhyPair(finding) {
    var why = objectValue(finding && finding.why_flagged) || {};
    var count = numberValue(why.changed_paragraph_count);
    if (count != null) return pair(
      count + ' matched passage' + (count === 1 ? ' was' : 's were') + ' textually changed.',
      '有 ' + count + ' 个匹配段落出现文本变化。'
    );
    count = numberValue(why.changed_policy_block_count);
    if (count != null) return pair(
      count + ' policy passage' + (count === 1 ? ' was' : 's were') + ' textually changed.',
      '有 ' + count + ' 个政策段落出现文本变化。'
    );
    if (why.missing_kpi_keys) {
      var enList = readablePhraseList(why.missing_kpi_keys, 'en');
      var zhList = readablePhraseList(why.missing_kpi_keys, 'zh');
      return pair(
        'A previously matched metric phrase was not found in the supplied current filing: ' + enList + '.',
        '在提供的本期财报中未找到此前匹配的指标词组：' + zhList + '。'
      );
    }
    if (why.reason === 'same_reporting_form_required') return pair(
      'The supplied filings are not the same reporting form, so this comparison is not evaluable.',
      '提供的财报不是同一类报表，因此无法直接比较。'
    );
    if (why.reason === 'risk_factor_section_missing') return pair(
      'The expected risk-factor section was not found in one supplied filing.',
      '在一份提供的财报中未找到预期的风险因素章节。'
    );
    if (why.reason === 'policy_disclosure_missing_in_one_filing') return pair(
      'The matched policy disclosure was not found in both supplied filings.',
      '在两份提供的财报中未同时找到匹配的政策披露。'
    );
    return pair(
      'The comparison engine found a reviewable lexical difference. Read the source excerpts before interpreting it.',
      '对比引擎发现了值得复核的文字差异；请先阅读来源摘录再作解读。'
    );
  }

  function disclosureFindingsForView(target) {
    return disclosureFindings(target).filter(function (finding) {
      var info = disclosureFindingState(finding);
      var section = disclosureFindingSection(finding);
      return info.key === 'review' && (state.disclosureSection === 'all' || section === state.disclosureSection);
    });
  }

  function activeRedlines(target) {
    return disclosureRedlines(target).filter(function (redline) {
      var operation = String(redline.operation || '').toLowerCase();
      if (redline.suppressed || operation === 'unchanged' || operation === 'moved' || operation === 'suppressed_boilerplate') return false;
      return operation === 'modified' || operation === 'added' || operation === 'removed' || operation === 'table_cell_changed' || !operation;
    });
  }

  function redlineOperationInfo(redline) {
    var operation = String((redline && redline.operation) || '').toLowerCase();
    if (operation === 'added') return { key: 'added', en: 'Text added', zh: '新增文本' };
    if (operation === 'removed') return { key: 'removed', en: 'Text removed', zh: '删除文本' };
    if (operation === 'table_cell_changed') return { key: 'table', en: 'Table cell changed', zh: '表格单元格变化' };
    return { key: 'modified', en: 'Wording changed', zh: '措辞变化' };
  }

  function redlineSection(redline) {
    return String((redline && redline.section_key) || 'other');
  }

  function editPreview(redline) {
    var edits = Array.isArray(redline && redline.inline_edits) ? redline.inline_edits : [];
    if (!edits.length) return pair('Open to read the supplied source excerpts.', '打开以阅读提供的来源摘录。');
    var edit = edits[0] || {};
    var before = String(edit.prior_text || '').trim();
    var after = String(edit.current_text || '').trim();
    var content = before || after || '';
    if (content.length > 132) content = content.slice(0, 131) + '…';
    return pair(content || 'Open to read the supplied source excerpts.', content || '打开以阅读提供的来源摘录。');
  }

  function renderDisclosureControls(target) {
    var sections = [];
    disclosureFindings(target).forEach(function (finding) {
      var key = disclosureFindingSection(finding);
      if (sections.indexOf(key) < 0) sections.push(key);
    });
    activeRedlines(target).forEach(function (redline) {
      var key = redlineSection(redline);
      if (sections.indexOf(key) < 0) sections.push(key);
    });
    if (sections.indexOf(state.disclosureSection) < 0) state.disclosureSection = 'all';
    var html = '<option value="all">' + esc(lang() === 'zh' ? '全部章节' : 'All sections') + '</option>';
    sections.sort().forEach(function (section) {
      html += '<option value="' + esc(section) + '">' + esc(disclosureSectionText(section, lang())) + '</option>';
    });
    ui.disclosureSection.innerHTML = html;
    ui.disclosureSection.value = state.disclosureSection;
    ui.disclosureSection.disabled = !sections.length;
  }

  function renderDisclosureFeed(target) {
    var documents = disclosureDocuments(target);
    var pairCount = readyDisclosureTracks(target).length;
    var allFindings = disclosureFindings(target);
    var visible = disclosureFindingsForView(target);
    var compared = pairCount > 0;
    ui.disclosureSummary.innerHTML = compared ? pair(
      visible.length + ' review prompt' + (visible.length === 1 ? '' : 's') + ' across ' + pairCount + ' filing pair' + (pairCount === 1 ? '' : 's'),
      pairCount + ' 组财报对比中有 ' + visible.length + ' 项复核提示'
    ) : pair('Comparable filing pair unavailable', '暂无可比财报组合');
    if (!compared && !allFindings.length) {
      if (state.evidenceKind === 'disclosure-finding') {
        state.disclosureFindingId = '';
        renderTabEvidenceEmpty('disclosures');
      }
      ui.disclosureFeed.innerHTML = emptyState(
        'No comparable filing pair yet', '尚无可比财报组合',
        'Disclosure comparison appears only after two compatible SEC filings are available. Nothing is inferred from missing text.',
        '只有在两份兼容的 SEC 财报可用后才会显示披露对比；不会从缺失文本推断结果。', '?'
      );
      return;
    }
    if (!visible.length) {
      if (state.evidenceKind === 'disclosure-finding') {
        state.disclosureFindingId = '';
        renderTabEvidenceEmpty('disclosures');
      }
      var filtered = allFindings.some(function (finding) { return disclosureFindingState(finding).key === 'review'; });
      ui.disclosureFeed.innerHTML = emptyState(
        filtered ? 'No observed changes in this section' : 'No review prompt in this comparison',
        filtered ? '该章节未见观察到的变化' : '本次对比暂无复核提示',
        filtered ? 'Choose another section to inspect the available observations.' : 'This is not a conclusion that every disclosure is unchanged; inspect the filing trail and source coverage.',
        filtered ? '请选择其他章节查看已有观察结果。' : '这不代表每项披露都没有变化；请查看披露轨迹和来源覆盖范围。', filtered ? '↺' : '✓'
      );
      return;
    }
    if (!selectedDisclosureFinding() || !visible.some(function (finding) { return disclosureFindingId(finding) === state.disclosureFindingId; })) {
      state.disclosureFindingId = disclosureFindingId(visible[0]);
    }
    ui.disclosureFeed.innerHTML = visible.map(function (finding) {
      var selected = disclosureFindingId(finding) === state.disclosureFindingId;
      var section = disclosureFindingSection(finding);
      var status = disclosureFindingState(finding);
      var form = String(finding._track_form || '');
      return '<div role="listitem"><button type="button" class="ff-disclosure-card' + (selected ? ' is-selected' : '') + '"' +
        ' data-disclosure-finding-id="' + esc(disclosureFindingId(finding)) + '" aria-current="' + (selected ? 'true' : 'false') + '" aria-controls="ff-evidence">' +
        '<span class="ff-disclosure-mark" aria-hidden="true">' + status.icon + '</span><span class="ff-disclosure-copy">' +
        '<span class="ff-finding-overline"><span class="ff-observed-label">' + pair(status.en, status.zh) + '</span>' +
        (form ? '<span aria-hidden="true">·</span><span>' + esc(form) + '</span>' : '') +
        '<span aria-hidden="true">·</span><span>' + disclosureSectionPair(section) + '</span></span>' +
        '<h3>' + disclosureFindingLabel(finding) + '</h3><span class="ff-finding-summary">' + disclosureWhyPair(finding) + '</span></span>' +
        '<span class="ff-finding-periods"><strong>' + esc(String(finding.current_accession || '—')) + '</strong>' + pair('Read excerpts', '阅读摘录') + '</span></button></div>';
    }).join('');
    if (state.evidenceKind === 'disclosure-finding') renderCurrentEvidence();
  }

  function renderRedlines(target) {
    var redlines = activeRedlines(target);
    var filtered = redlines.filter(function (redline) {
      return state.disclosureSection === 'all' || redlineSection(redline) === state.disclosureSection;
    });
    ui.redlineSummary.innerHTML = pair(
      filtered.length + ' visible text change' + (filtered.length === 1 ? '' : 's'),
      '显示 ' + filtered.length + ' 条文本变化'
    );
    if (!redlines.length) {
      if (state.evidenceKind === 'redline') {
        state.redlineId = '';
        renderTabEvidenceEmpty('redlines');
      }
      ui.redlineList.innerHTML = emptyState(
        'No source redlines available', '暂无来源逐字对照',
        'A redline appears only when the comparison engine has matched supplied filing text. Suppressed boilerplate is intentionally excluded.',
        '只有在对比引擎匹配到提供的财报文本时才会显示逐字对照；已抑制的模板文本会被有意排除。', '—'
      );
      return;
    }
    if (!filtered.length) {
      if (state.evidenceKind === 'redline') {
        state.redlineId = '';
        renderTabEvidenceEmpty('redlines');
      }
      ui.redlineList.innerHTML = emptyState(
        'No redlines in this section', '该章节暂无逐字对照',
        'Choose another section to inspect the available filing changes.',
        '请选择其他章节查看已有的财报变化。', '↺'
      );
      return;
    }
    if (!selectedRedline() || !filtered.some(function (redline) { return redlineId(redline) === state.redlineId; })) {
      state.redlineId = redlineId(filtered[0]);
    }
    ui.redlineList.innerHTML = filtered.map(function (redline) {
      var selected = redlineId(redline) === state.redlineId;
      var operation = redlineOperationInfo(redline);
      var form = String(redline._track_form || '');
      var count = numberValue(redline.changed_token_count);
      var countText = count == null ? '' : count + (count === 1 ? ' changed word' : ' changed words');
      var zhCountText = count == null ? '' : count + ' 个变化词';
      return '<div role="listitem"><button type="button" class="ff-redline-card' + (selected ? ' is-selected' : '') + '"' +
        ' data-redline-id="' + esc(redlineId(redline)) + '" aria-current="' + (selected ? 'true' : 'false') + '" aria-controls="ff-evidence">' +
        '<span class="ff-redline-operation" data-operation="' + esc(operation.key) + '">' + pair(operation.en, operation.zh) + '</span>' +
        '<span class="ff-redline-copy"><span class="ff-finding-overline">' + (form ? esc(form) + '<span aria-hidden="true">·</span>' : '') + disclosureSectionPair(redlineSection(redline)) +
        (countText ? '<span aria-hidden="true">·</span><span>' + pair(countText, zhCountText) + '</span>' : '') + '</span><p>' + editPreview(redline) + '</p></span>' +
        '<span class="ff-redline-open">' + pair('Inspect', '查看') + '<span aria-hidden="true">↗</span></span></button></div>';
    }).join('');
    if (state.evidenceKind === 'redline') renderCurrentEvidence();
  }

  function renderTimeline(target) {
    var documents = disclosureDocuments(target);
    if (!documents.length) {
      ui.timeline.innerHTML = emptyState(
        'No filing trail supplied', '未提供披露轨迹',
        'The disclosure layer has not supplied filing accessions for this company.',
        '该公司的披露层尚未提供财报文件编号。', '—'
      );
      return;
    }
    ui.timeline.innerHTML = '<div class="ff-timeline-rail" aria-hidden="true"></div><div class="ff-timeline-list">' + documents.map(function (document, index) {
      var href = documentSourceUrl(document);
      var form = String(document._track_form || document.form || document.form_type || 'SEC filing');
      var role = document._filing_role === 'current' ? pair('Current ' + form, '本期 ' + form) :
        (document._filing_role === 'prior' ? pair('Prior ' + form, '上期 ' + form) : pair('Source filing', '来源财报'));
      var reportDate = formatDate(document.report_date);
      var sourceAction = href ? '<a class="ff-source-link ff-timeline-link" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer"><span aria-hidden="true">↗</span>' + pair('Open SEC filing', '打开 SEC 财报') + '</a>' : '<span class="ff-timeline-unavailable">' + pair('SEC link not supplied', '未提供 SEC 链接') + '</span>';
      return '<article class="ff-timeline-card"><span class="ff-timeline-node" aria-hidden="true">' + (index + 1) + '</span><p class="ff-kicker">' + role + '</p><h3>' + esc(form) + '</h3><dl><div><dt>' + pair('Filed', '披露日') + '</dt><dd>' + esc(documentDate(document)) + '</dd></div><div><dt>' + pair('Report date', '报告期') + '</dt><dd>' + esc(reportDate) + '</dd></div><div><dt>' + pair('Accession', '文件编号') + '</dt><dd class="ff-accession">' + esc(documentAccession(document)) + '</dd></div></dl>' + sourceAction + '</article>';
    }).join('') + '</div>';
  }

  function renderStatements(target) {
    var periods = Array.isArray(target.periods) ? target.periods : [];
    if (!periods.length) {
      ui.statements.innerHTML = emptyState('No statement periods available', '暂无财务报表期间',
        'The source state has no normalized periods for this company.', '来源状态中没有该公司的标准化期间。', '—');
      return;
    }
    var header = '<th>' + pair('Period / filed', '期间 / 披露日') + '</th>' + METRICS.map(function (metric) {
      return '<th>' + pair(metric.en, metric.zh) + '</th>';
    }).join('');
    var rows = periods.map(function (period) {
      var first = '<td data-label-en="Period / filed" data-label-zh="期间 / 披露日">' + esc(periodLabel(period)) +
        '<span class="ff-period-filed">' + esc(formatDate(period.filed || period.period_end)) + '</span></td>';
      return '<tr>' + first + METRICS.map(function (metric) {
        return '<td data-label-en="' + esc(metric.en) + '" data-label-zh="' + esc(metric.zh) + '">' +
          esc(formatValue(period[metric.key], metric.format)) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    ui.statements.innerHTML = '<div class="ff-table-wrap"><table class="ff-table"><thead><tr>' + header +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function renderCompareControls(target) {
    var periods = Array.isArray(target.periods) ? target.periods : [];
    if (!periods.length) {
      ui.currentPeriod.innerHTML = '';
      ui.priorPeriod.innerHTML = '';
      ui.currentPeriod.disabled = true;
      ui.priorPeriod.disabled = true;
      return;
    }
    state.currentPeriod = Math.min(state.currentPeriod, periods.length - 1);
    state.priorPeriod = Math.min(state.priorPeriod, periods.length - 1);
    var options = periods.map(function (period, index) {
      var suffix = period.period_end ? ' · ' + formatDate(period.period_end) : '';
      return '<option value="' + index + '">' + esc(periodLabel(period) + suffix) + '</option>';
    }).join('');
    ui.currentPeriod.disabled = false;
    ui.priorPeriod.disabled = false;
    ui.currentPeriod.innerHTML = options;
    ui.priorPeriod.innerHTML = options;
    ui.currentPeriod.value = String(state.currentPeriod);
    ui.priorPeriod.value = String(state.priorPeriod);
  }

  function renderCompare(target) {
    var periods = Array.isArray(target.periods) ? target.periods : [];
    if (!periods.length) {
      ui.compareGrid.innerHTML = emptyState('No periods to compare', '暂无可对比期间',
        'At least one reported period is required.', '至少需要一个披露期间。', '—');
      return;
    }
    var current = periods[state.currentPeriod] || periods[0];
    var prior = periods[state.priorPeriod] || periods[0];
    ui.compareGrid.innerHTML = METRICS.map(function (metric) {
      var currentNumber = numberValue(current[metric.key]);
      var priorNumber = numberValue(prior[metric.key]);
      var delta = currentNumber != null && priorNumber != null ? currentNumber - priorNumber : null;
      var pct = delta != null && priorNumber !== 0 ? delta / Math.abs(priorNumber) : null;
      var deltaText = delta == null ? '—' : formatSigned(delta, metric.format);
      if (pct != null) deltaText += ' · ' + formatSigned(pct, 'percent');
      return '<article class="ff-compare-card"><h3>' + pair(metric.en, metric.zh) + '</h3>' +
        '<div class="ff-compare-values"><div class="ff-compare-value"><span>' + pair('Current · ' + periodLabel(current), '本期 · ' + periodLabel(current)) +
        '</span><strong>' + esc(formatValue(current[metric.key], metric.format)) + '</strong></div>' +
        '<div class="ff-compare-value"><span>' + pair('Prior · ' + periodLabel(prior), '上期 · ' + periodLabel(prior)) +
        '</span><strong>' + esc(formatValue(prior[metric.key], metric.format)) + '</strong></div></div>' +
        '<div class="ff-compare-delta">' + pair('Change ' + deltaText, '变化 ' + deltaText) + '</div></article>';
    }).join('');
  }

  function companyFactsUrl(target) {
    var source = state.payload.source || {};
    var pattern = String(source.companyfacts_url_pattern || '');
    if (!pattern) return '';
    var cikRaw = String(target.cik || '').replace(/\D/g, '');
    var cikPadded = cikRaw ? cikRaw.padStart(10, '0') : '';
    var expanded = pattern
      .replace(/\{cik_padded\}/gi, cikPadded)
      .replace(/\{cik10\}/gi, cikPadded)
      .replace(/\{cik\}/gi, cikRaw)
      .replace(/\{symbol\}/gi, encodeURIComponent(target.symbol || state.symbol));
    return safeUrl(expanded);
  }

  function normalizeDetectors() {
    var raw = state.payload.detectors || [];
    if (Array.isArray(raw)) {
      return raw.map(function (item, index) {
        return typeof item === 'object' ? Object.assign({ key: item.key || item.id || 'detector-' + (index + 1) }, item) : { key: String(item) };
      });
    }
    if (typeof raw === 'object') {
      return Object.keys(raw).map(function (key) {
        var item = raw[key];
        return typeof item === 'object' ? Object.assign({ key: key }, item) : { key: key, description: String(item) };
      });
    }
    return [];
  }

  function renderTrace(target) {
    var source = state.payload.source || {};
    var coverage = target.coverage || {};
    var findings = orderedFindings(target);
    var evidenceCount = findings.reduce(function (total, finding) {
      return total + (Array.isArray(finding.evidence) ? finding.evidence.length : 0);
    }, 0);
    var sourceEn = localized(source.label, 'en') || 'Source';
    var sourceZh = translatedDataPhrase(localized(source.label, 'zh') || sourceEn, 'zh');
    var basisEn = localized(source.basis, 'en') || localized(coverage.basis, 'en') || '—';
    var basisZh = translatedDataPhrase(
      localized(source.basis, 'zh') || localized(coverage.basis, 'zh') || basisEn, 'zh'
    );
    var sourceUrl = companyFactsUrl(target);
    var limitationsEn = Array.isArray(source.limitations_en) ? source.limitations_en : [];
    var limitationsZh = Array.isArray(source.limitations_zh) ? source.limitations_zh : [];
    var limitationCount = Math.max(limitationsEn.length, limitationsZh.length);
    var limitations = '';
    for (var limitIndex = 0; limitIndex < limitationCount; limitIndex += 1) {
      limitations += '<li>' + pair(limitationsEn[limitIndex] || limitationsZh[limitIndex], limitationsZh[limitIndex] || limitationsEn[limitIndex]) + '</li>';
    }
    if (!limitations) limitations = '<li>' + pair('No source-level limitation was supplied.', '未提供来源层面的局限说明。') + '</li>';

    var detectors = normalizeDetectors();
    var detectorHtml = detectors.length ? detectors.map(function (detector) {
      var nameEn = detector.label_en || detector.name_en || detector.title_en || prettify(detector.key);
      var nameZh = detector.label_zh || detector.name_zh || detector.title_zh || '规则：' + prettify(detector.key);
      var meta = [detector.key, detector.version, detector.status].filter(Boolean).join(' · ');
      return '<li class="ff-detector-item"><div class="ff-detector-name">' + pair(nameEn, nameZh) + '</div>' +
        '<div class="ff-detector-meta">' + esc(meta || '—') + '</div></li>';
    }).join('') : '<li class="ff-detector-item">' + pair('No detector registry supplied.', '未提供检测器清单。') + '</li>';

    var traceFindings = findings.length ? findings.map(function (finding) {
      var receipts = Array.isArray(finding.evidence) ? finding.evidence : [];
      var receiptLinks = receipts.length ? receipts.map(function (receipt) {
        var href = safeUrl(receipt.url);
        var label = fieldPair(receipt, 'label', 'SEC source');
        return href ? '<a class="ff-trace-receipt" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' +
          '<span aria-hidden="true">↗</span>' + label + '</a>' : '<span class="ff-trace-receipt">' + label + '</span>';
      }).join('') : '<span class="ff-trace-receipt">' + pair('No source link supplied', '未提供来源链接') + '</span>';
      return '<article class="ff-trace-finding"><div class="ff-trace-finding-head"><div><p class="ff-kicker">' +
        topicPair(finding.topic) + ' · ' + esc(finding.detector || '—') + '</p><h3>' + fieldPair(finding, 'title', 'Untitled finding') +
        '</h3></div><button class="ff-trace-open" type="button" data-open-finding="' + esc(finding.id) + '">' +
        pair('See details', '查看详情') + '</button></div><code class="ff-proof-code">' +
        fieldPair(finding, 'formula', 'Formula not supplied') + '</code><div class="ff-trace-receipts">' + receiptLinks + '</div></article>';
    }).join('') : emptyState('No source-map findings', '暂无来源映射发现',
      'There are no findings to map for this company.', '该公司暂无可映射来源的发现。', '—');

    var disclosureTrack = selectedDisclosureTrack(target);
    var disclosureDocs = disclosureDocuments(target);
    var disclosureFindingItems = disclosureFindings(target);
    var disclosureRedlineItems = activeRedlines(target);
    var disclosureLinks = disclosureDocs.map(function (document) {
      var href = documentSourceUrl(document);
      var label = [document.form || document.form_type || 'SEC filing', documentAccession(document)].filter(Boolean).join(' · ');
      return href ? '<a class="ff-trace-receipt" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer"><span aria-hidden="true">↗</span>' + esc(label) + '</a>' :
        '<span class="ff-trace-receipt">' + esc(label) + '</span>';
    }).join('');
    var disclosureTrace = disclosureTrack ? '<section class="ff-trace-card"><p class="ff-kicker">' +
      pair('Wording comparison', '措辞对比') + '</p><h3>' + pair('The two filings used here', '本次使用的两份财报') + '</h3><p>' + pair(
        disclosureFindingItems.length + ' results · ' + disclosureRedlineItems.length + ' wording changes',
        disclosureFindingItems.length + ' 项结果 · ' + disclosureRedlineItems.length + ' 条措辞变化'
      ) + '</p><div class="ff-trace-receipts">' + (disclosureLinks || '<span class="ff-trace-receipt">' + pair('No filing link supplied', '未提供财报链接') + '</span>') + '</div></section>' :
      '<section class="ff-trace-card"><p class="ff-kicker">' + pair('Wording comparison', '措辞对比') + '</p><h3>' + pair('Not available yet', '暂不可用') + '</h3><p>' + pair(
        'Wording changes appear when two matching SEC filings are available.',
        '当有两份匹配的 SEC 财报时，这里会显示措辞变化。'
      ) + '</p></section>';

    ui.trace.innerHTML = '<div class="ff-trace-grid"><div><section class="ff-trace-card"><p class="ff-kicker">' +
      pair('Data source', '数据来源') + '</p><h3>' + pair(sourceEn, sourceZh) + '</h3><p>' + pair(basisEn, basisZh) + '</p>' +
      '<div class="ff-coverage-grid"><div class="ff-coverage-stat"><small>' + pair('Periods', '期间数') + '</small><strong>' +
      esc(coverage.periods == null ? (Array.isArray(target.periods) ? target.periods.length : 0) : coverage.periods) + '</strong></div>' +
      '<div class="ff-coverage-stat"><small>' + pair('Metric coverage', '指标覆盖率') + '</small><strong>' +
      esc(coverage.metrics_pct == null ? '—' : formatPercent(coverage.metrics_pct)) + '</strong></div>' +
      '<div class="ff-coverage-stat"><small>' + pair('Signals', '信号数') + '</small><strong>' + findings.length + '</strong></div>' +
      '<div class="ff-coverage-stat"><small>' + pair('Source links', '来源链接') + '</small><strong>' + evidenceCount + '</strong></div></div>' +
      (sourceUrl ? '<a class="ff-source-link" href="' + esc(sourceUrl) + '" target="_blank" rel="noopener noreferrer"><span aria-hidden="true">↗</span>' +
        pair('Open Company Facts at the SEC', '在 SEC 打开公司事实数据') + '</a>' : '') +
      '<details class="ff-trace-details"><summary>' + pair('What to know about this data', '关于这些数据需要了解') + '</summary><div class="ff-proof-section"><ul class="ff-source-limitations">' + limitations + '</ul></div></details></section>' +
      '<section class="ff-trace-card"><details class="ff-trace-details"><summary>' + pair('How signals are detected', '信号如何识别') + '</summary><div><ul class="ff-detector-list">' + detectorHtml + '</ul></div></details></section>' + disclosureTrace + '</div>' +
      '<div class="ff-trace-findings">' + traceFindings + '</div></div>';
  }

  // The sealed history surface is deliberately a reading layer. It never
  // replays source material, produces a score, or turns a receipt into a
  // broader issuer conclusion. Keep all request-time data bounded to one root
  // page plus the one waterfall the analyst has explicitly opened.
  function normalizedCik(value) {
    var digits = String(value == null ? '' : value).trim();
    return /^\d{1,10}$/.test(digits) ? digits.padStart(10, '0') : '';
  }

  function isSnapshotId(value) {
    return /^ffqsv2_[a-f0-9]{64}$/.test(String(value || ''));
  }

  function isBaseSnapshotId(value) {
    return /^ffqs_[a-f0-9]{64}$/.test(String(value || ''));
  }

  function isRootCellId(value) {
    return /^metric_cell_[a-f0-9]{64}$/.test(String(value || ''));
  }

  function isReceiptObject(value) {
    return Object.prototype.toString.call(value) === '[object Object]';
  }

  function hasExactReceiptKeys(value, keys) {
    if (!isReceiptObject(value)) return false;
    var actual = Object.keys(value).sort();
    var expected = keys.slice().sort();
    return actual.length === expected.length && actual.every(function (key, index) {
      return key === expected[index];
    });
  }

  function isSafeReceiptInteger(value) {
    return Number.isSafeInteger(value) && value >= 0;
  }

  function isBoundedReceiptText(value, maximum) {
    return typeof value === 'string' && value.length > 0 && value.length <= maximum;
  }

  function receiptUtcOrderKey(value) {
    if (typeof value !== 'string' || value.length > 64) return null;
    var match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{6}))?Z$/.exec(value);
    if (!match) return null;
    var year = Number(match[1]);
    var month = Number(match[2]);
    var day = Number(match[3]);
    var hour = Number(match[4]);
    var minute = Number(match[5]);
    var second = Number(match[6]);
    if (year < 1 || month < 1 || month > 12 || day < 1 || day > 31 ||
        hour > 23 || minute > 59 || second > 59) return null;
    var calendar = new Date(0);
    calendar.setUTCHours(0, 0, 0, 0);
    calendar.setUTCFullYear(year, month - 1, day);
    calendar.setUTCHours(hour, minute, second, 0);
    if (calendar.getUTCFullYear() !== year || calendar.getUTCMonth() !== month - 1 ||
        calendar.getUTCDate() !== day || calendar.getUTCHours() !== hour ||
        calendar.getUTCMinutes() !== minute || calendar.getUTCSeconds() !== second) return null;
    return match.slice(1, 7).join('') + (match[7] || '000000');
  }

  function isReceiptDate(value, nullable) {
    if (value === null && nullable) return true;
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var parts = value.split('-').map(Number);
    if (parts[0] < 1 || parts[1] < 1 || parts[1] > 12 || parts[2] < 1 || parts[2] > 31) return false;
    var parsed = new Date(0);
    parsed.setUTCHours(0, 0, 0, 0);
    parsed.setUTCFullYear(parts[0], parts[1] - 1, parts[2]);
    return parsed.getUTCFullYear() === parts[0] && parsed.getUTCMonth() === parts[1] - 1 &&
      parsed.getUTCDate() === parts[2];
  }

  function receiptArraysEqual(left, right) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length &&
      left.every(function (value, index) { return value === right[index]; });
  }

  function receiptStringList(value, pattern) {
    if (!Array.isArray(value) || value.length > 1024) return null;
    var previous = null;
    for (var index = 0; index < value.length; index += 1) {
      var current = value[index];
      if (typeof current !== 'string' || !pattern.test(current) ||
          (previous !== null && current <= previous)) return null;
      previous = current;
    }
    return value.slice();
  }

  function receiptSubset(subset, superset) {
    var allowed = new Set(superset);
    return subset.every(function (value) { return allowed.has(value); });
  }

  function checkedReceiptRoot(value) {
    if (!hasExactReceiptKeys(value, [
      'root_cell_id', 'selected_leaf_occurrence_ids', 'eligible_leaf_occurrence_ids',
      'attested_occurrence_ids', 'status'
    ]) || !isRootCellId(value.root_cell_id)) return null;
    var occurrencePattern = /^rawfact_[a-f0-9]{64}$/;
    var selected = receiptStringList(value.selected_leaf_occurrence_ids, occurrencePattern);
    var eligible = receiptStringList(value.eligible_leaf_occurrence_ids, occurrencePattern);
    var attested = receiptStringList(value.attested_occurrence_ids, occurrencePattern);
    if (!selected || !eligible || !attested || selected.length + eligible.length + attested.length > 3072 ||
        !receiptSubset(eligible, selected) || !receiptSubset(attested, eligible)) return null;
    var expectedStatus;
    if (!selected.length || !eligible.length) expectedStatus = 'not_evaluable';
    else if (eligible.length === selected.length && attested.length === selected.length) expectedStatus = 'all_leaves_attested';
    else if (attested.length) expectedStatus = 'partially_attested';
    else expectedStatus = 'not_attested';
    if (value.status !== expectedStatus) return null;
    return {
      root_cell_id: value.root_cell_id,
      selected_leaf_occurrence_ids: selected,
      eligible_leaf_occurrence_ids: eligible,
      attested_occurrence_ids: attested,
      status: expectedStatus
    };
  }

  function checkedReceiptAuthority(value) {
    if (!hasExactReceiptKeys(value, [
      'positive_claim', 'coverage_scope', 'claim_basis', 'source_reverified_at_read',
      'match_body_replayed_at_read', 'nonclaims'
    ]) || value.positive_claim !== 'B3_selected_member_companyfacts_row_correspondence_only' ||
        value.coverage_scope !== 'selected_raw_fact_leaves_only' ||
        value.claim_basis !== 'sealed_publication_receipt' ||
        value.source_reverified_at_read !== false || value.match_body_replayed_at_read !== false ||
        !isReceiptObject(value.nonclaims)) return null;
    var nonclaimKeys = Object.keys(value.nonclaims);
    if (!nonclaimKeys.length || nonclaimKeys.some(function (key) { return value.nonclaims[key] !== false; }) ||
        value.nonclaims.filing_complete !== false || value.nonclaims.trading_authority !== false ||
        value.nonclaims.neural_web_authority !== false) return null;
    return value;
  }

  function sameReceiptAuthority(left, right) {
    var leftAuthority = checkedReceiptAuthority(left);
    var rightAuthority = checkedReceiptAuthority(right);
    if (!leftAuthority || !rightAuthority) return false;
    var leftKeys = Object.keys(leftAuthority.nonclaims).sort();
    var rightKeys = Object.keys(rightAuthority.nonclaims).sort();
    return receiptArraysEqual(leftKeys, rightKeys);
  }

  function checkedReceiptIdentity(value) {
    if (!isReceiptObject(value) || !isSnapshotId(value.snapshot_id) ||
        !isBaseSnapshotId(value.base_snapshot_id) || !/^[a-f0-9]{64}$/.test(String(value.query_hash || '')) ||
        receiptUtcOrderKey(value.published_at) === null) return null;
    return {
      snapshot_id: value.snapshot_id,
      base_snapshot_id: value.base_snapshot_id,
      query_hash: value.query_hash,
      published_at: value.published_at
    };
  }

  function sameReceiptIdentity(value, expected) {
    var actual = checkedReceiptIdentity(value);
    var wanted = checkedReceiptIdentity(expected);
    return !!actual && !!wanted && actual.snapshot_id === wanted.snapshot_id &&
      actual.base_snapshot_id === wanted.base_snapshot_id && actual.query_hash === wanted.query_hash &&
      actual.published_at === wanted.published_at;
  }

  function checkedSnapshotClocks(value, publishedAt) {
    var keys = [
      'query_source_snapshot_at', 'query_recorded_at', 'query_computed_at', 'query_published_at',
      'operator_verification_observed_at', 'published_at'
    ];
    if (!hasExactReceiptKeys(value, keys) || value.published_at !== publishedAt) return null;
    var clocks = {};
    for (var index = 0; index < keys.length; index += 1) {
      clocks[keys[index]] = receiptUtcOrderKey(value[keys[index]]);
      if (clocks[keys[index]] === null) return null;
    }
    var latestInput = clocks.query_source_snapshot_at > clocks.query_recorded_at ?
      clocks.query_source_snapshot_at : clocks.query_recorded_at;
    if (clocks.query_computed_at < latestInput ||
        clocks.query_published_at < clocks.query_computed_at ||
        clocks.operator_verification_observed_at < clocks.query_published_at ||
        clocks.published_at < clocks.operator_verification_observed_at) return null;
    return value;
  }

  function checkedCoverageSummary(value) {
    var countKeys = ['root_cell_count', 'all_leaves_attested', 'partially_attested', 'not_attested', 'not_evaluable'];
    if (!hasExactReceiptKeys(value, ['coverage_scope', 'positive_label'].concat(countKeys)) ||
        value.coverage_scope !== 'selected_raw_fact_leaves_only' ||
        value.positive_label !== 'B3_selected_member_companyfacts_row_correspondence_only' ||
        countKeys.some(function (key) { return !isSafeReceiptInteger(value[key]); })) return null;
    var statusTotal = value.all_leaves_attested + value.partially_attested + value.not_attested + value.not_evaluable;
    return value.root_cell_count === statusTotal && value.root_cell_count <= 100000 ? value : null;
  }

  function checkedConversionReceipt(value) {
    var keys = [
      'receipt_id', 'schema', 'adapter_version', 'capture_id', 'manifest_id', 'cik', 'clocks',
      'availability', 'occurrence_count', 'output_occurrence_count', 'pit_eligible_count'
    ];
    var clockKeys = [
      'acquisition_started_at', 'captured_at', 'recorded_at', 'source_snapshot_at', 'submissions_recorded_at'
    ];
    if (!hasExactReceiptKeys(value, keys) || !/^cffledger_[a-f0-9]{64}$/.test(String(value.receipt_id || '')) ||
        value.schema !== 'fundamental_forensics.companyfacts_ledger_receipt/v2' ||
        !isBoundedReceiptText(value.adapter_version, 128) ||
        !/^ffseccfc_[a-f0-9]{64}$/.test(String(value.capture_id || '')) ||
        !/^ffseccfm_[a-f0-9]{64}$/.test(String(value.manifest_id || '')) ||
        !/^\d{10}$/.test(String(value.cik || '')) ||
        !hasExactReceiptKeys(value.clocks, clockKeys) ||
        clockKeys.some(function (key) { return receiptUtcOrderKey(value.clocks[key]) === null; }) ||
        ['available', 'partial'].indexOf(value.availability) === -1 ||
        !isSafeReceiptInteger(value.occurrence_count) || !isSafeReceiptInteger(value.output_occurrence_count) ||
        !isSafeReceiptInteger(value.pit_eligible_count) || value.occurrence_count !== value.output_occurrence_count ||
        value.pit_eligible_count > value.output_occurrence_count) return null;
    return value;
  }

  function checkedLatestReceipt(value) {
    var keys = [
      'snapshot_id', 'base_snapshot_id', 'query_hash', 'published_at', 'policy', 'clocks',
      'coverage_summary', 'companyfacts_conversion_receipt', 'authority'
    ];
    var identity = checkedReceiptIdentity(value);
    if (!hasExactReceiptKeys(value, keys) || !identity ||
        !hasExactReceiptKeys(value.policy, ['version', 'fingerprint']) ||
        value.policy.version !== 'ffqsv2_exact_join/v1' ||
        value.policy.fingerprint !== '6e4ba04cf9c775ac280ba1426985246ffbdf730222b4521c4b26a41f5623871a' ||
        !checkedSnapshotClocks(value.clocks, value.published_at) ||
        !checkedCoverageSummary(value.coverage_summary) ||
        !checkedConversionReceipt(value.companyfacts_conversion_receipt) ||
        !checkedReceiptAuthority(value.authority)) return null;
    return value;
  }

  function shortTraceId(value) {
    var text = String(value || '');
    if (text.length <= 22) return text || '—';
    return text.slice(0, 14) + '…' + text.slice(-6);
  }

  function selectedReceiptRootButton() {
    var wanted = String(state.receipt.rootCellId || '');
    return Array.prototype.find.call(document.querySelectorAll('[data-root-cell-id]'), function (candidate) {
      return candidate.getAttribute('data-root-cell-id') === wanted;
    }) || null;
  }

  function receiptStatusInfo(status) {
    var known = {
      all_leaves_attested: {
        key: 'all',
        en: 'All selected leaves have correspondence',
        zh: '所有选定叶节点均有对应记录'
      },
      partially_attested: {
        key: 'partial',
        en: 'Some selected leaves have correspondence',
        zh: '部分选定叶节点有对应记录'
      },
      not_attested: {
        key: 'none',
        en: 'No selected leaf correspondence recorded',
        zh: '未记录选定叶节点对应关系'
      },
      not_evaluable: {
        key: 'not-evaluable',
        en: 'No eligible selected leaf',
        zh: '没有符合条件的选定叶节点'
      }
    };
    return known[String(status || '')] || {
      key: 'unknown',
      en: 'Receipt state unavailable',
      zh: '凭据状态不可用'
    };
  }

  function receiptCount(value) {
    return Array.isArray(value) ? value.length : 0;
  }

  function compactReceiptRoot(value) {
    var root = checkedReceiptRoot(value);
    if (!root) return null;
    return {
      root_cell_id: root.root_cell_id,
      status: root.status,
      selected: root.selected_leaf_occurrence_ids.length,
      eligible: root.eligible_leaf_occurrence_ids.length,
      attested: root.attested_occurrence_ids.length,
      selected_leaf_occurrence_ids: root.selected_leaf_occurrence_ids,
      eligible_leaf_occurrence_ids: root.eligible_leaf_occurrence_ids,
      attested_occurrence_ids: root.attested_occurrence_ids
    };
  }

  function receiptReadyPayload(value) {
    return !!checkedLatestReceipt(value);
  }

  function checkedReceiptPagePayload(value, latest, requestedCursor, pageIndex, previousTotal) {
    var keys = [
      'snapshot_id', 'base_snapshot_id', 'query_hash', 'published_at', 'authority', 'page', 'roots'
    ];
    var pageKeys = ['cursor', 'next_cursor', 'limit', 'returned', 'total'];
    var expectedCursor = requestedCursor || null;
    if (!hasExactReceiptKeys(value, keys) || !sameReceiptIdentity(value, latest) ||
        !sameReceiptAuthority(value.authority, latest.authority) ||
        !hasExactReceiptKeys(value.page, pageKeys) || !Array.isArray(value.roots) ||
        value.page.cursor !== expectedCursor || value.page.limit !== 25 ||
        !isSafeReceiptInteger(value.page.returned) || !isSafeReceiptInteger(value.page.total) ||
        value.page.returned !== value.roots.length || value.page.returned > value.page.limit ||
        value.page.total !== latest.coverage_summary.root_cell_count ||
        (previousTotal !== null && previousTotal !== value.page.total) ||
        (pageIndex === 0 && expectedCursor !== null) || (pageIndex > 0 && !isRootCellId(expectedCursor))) return null;
    var roots = [];
    var leafReferences = 0;
    var previousRootId = expectedCursor;
    for (var index = 0; index < value.roots.length; index += 1) {
      var root = checkedReceiptRoot(value.roots[index]);
      if (!root || (previousRootId !== null && root.root_cell_id <= previousRootId)) return null;
      leafReferences += root.selected_leaf_occurrence_ids.length + root.eligible_leaf_occurrence_ids.length +
        root.attested_occurrence_ids.length;
      if (leafReferences > 12288) return null;
      roots.push(compactReceiptRoot(root));
      previousRootId = root.root_cell_id;
    }
    var nextCursor = value.page.next_cursor;
    if (nextCursor !== null && (!isRootCellId(nextCursor) || !roots.length ||
        nextCursor !== roots[roots.length - 1].root_cell_id || roots.length !== value.page.limit)) return null;
    if (!roots.length && nextCursor !== null) return null;
    var consumed = pageIndex * value.page.limit + roots.length;
    if (consumed > value.page.total || (nextCursor === null && consumed !== value.page.total) ||
        (nextCursor !== null && consumed >= value.page.total)) return null;
    return {
      cursor: value.page.cursor,
      nextCursor: nextCursor,
      returned: value.page.returned,
      total: value.page.total,
      rows: roots
    };
  }

  function receiptDecimalText(value) {
    return typeof value === 'string' && value.length <= 4096 && value !== '-0' &&
      /^-?(?:0|[1-9]\d*)(?:\.\d*[1-9])?$/.test(value);
  }

  function checkedReceiptWaterfallRow(value, occurrenceId, eligible, attested, latest) {
    if (!isReceiptObject(value) || value.occurrence_id !== occurrenceId ||
        value.eligible !== eligible || value.attested !== attested) return null;
    if (!attested) {
      return hasExactReceiptKeys(value, ['occurrence_id', 'eligible', 'attested']) ? value : null;
    }
    var keys = [
      'occurrence_id', 'eligible', 'attested', 'attestation_id', 'match_id', 'companyfacts',
      'stored_b3_projection'
    ];
    var companyfactsKeys = ['cik', 'accession', 'taxonomy', 'concept', 'unit', 'period', 'value'];
    var projectionKeys = [
      'attestation_id', 'authority_snapshot_id', 'package_id', 'extraction_id', 'cik', 'accession',
      'companyfacts_capture_id', 'companyfacts_manifest_id', 'companyfacts_response_sha256',
      'companyfacts_match_count', 'attested_at'
    ];
    var companyfacts = value.companyfacts;
    var projection = value.stored_b3_projection;
    var conversion = latest.companyfacts_conversion_receipt;
    if (!eligible || !hasExactReceiptKeys(value, keys) ||
        !/^ffatt_[a-f0-9]{64}$/.test(String(value.attestation_id || '')) ||
        !/^ffatt_match_[a-f0-9]{64}$/.test(String(value.match_id || '')) ||
        !hasExactReceiptKeys(companyfacts, companyfactsKeys) ||
        !hasExactReceiptKeys(companyfacts.period, ['start', 'end']) ||
        companyfacts.cik !== conversion.cik || !/^\d{10}-\d{2}-\d{6}$/.test(String(companyfacts.accession || '')) ||
        !isBoundedReceiptText(companyfacts.taxonomy, 256) || !isBoundedReceiptText(companyfacts.concept, 256) ||
        !isBoundedReceiptText(companyfacts.unit, 256) || !isReceiptDate(companyfacts.period.start, true) ||
        !isReceiptDate(companyfacts.period.end, false) || !receiptDecimalText(companyfacts.value) ||
        !hasExactReceiptKeys(projection, projectionKeys) || projection.attestation_id !== value.attestation_id ||
        !/^ffsecsrc_[a-f0-9]{64}$/.test(String(projection.authority_snapshot_id || '')) ||
        !/^ffpkg_[a-f0-9]{64}$/.test(String(projection.package_id || '')) ||
        !/^ffxbrl_[a-f0-9]{64}$/.test(String(projection.extraction_id || '')) ||
        projection.cik !== companyfacts.cik || projection.accession !== companyfacts.accession ||
        projection.companyfacts_capture_id !== conversion.capture_id ||
        projection.companyfacts_manifest_id !== conversion.manifest_id ||
        !/^[a-f0-9]{64}$/.test(String(projection.companyfacts_response_sha256 || '')) ||
        !Number.isSafeInteger(projection.companyfacts_match_count) || projection.companyfacts_match_count <= 0 ||
        receiptUtcOrderKey(projection.attested_at) === null) return null;
    return value;
  }

  function checkedReceiptDetailPayload(value, latest, rootCellId, cachedRoot) {
    var keys = [
      'snapshot_id', 'base_snapshot_id', 'query_hash', 'published_at', 'authority', 'root', 'waterfall'
    ];
    if (!hasExactReceiptKeys(value, keys) || !sameReceiptIdentity(value, latest) ||
        !sameReceiptAuthority(value.authority, latest.authority) || !Array.isArray(value.waterfall) ||
        value.waterfall.length > 1024) return null;
    var root = checkedReceiptRoot(value.root);
    if (!root || root.root_cell_id !== rootCellId || !cachedRoot ||
        root.status !== cachedRoot.status ||
        !receiptArraysEqual(root.selected_leaf_occurrence_ids, cachedRoot.selected_leaf_occurrence_ids) ||
        !receiptArraysEqual(root.eligible_leaf_occurrence_ids, cachedRoot.eligible_leaf_occurrence_ids) ||
        !receiptArraysEqual(root.attested_occurrence_ids, cachedRoot.attested_occurrence_ids) ||
        value.waterfall.length !== root.selected_leaf_occurrence_ids.length) return null;
    var eligible = new Set(root.eligible_leaf_occurrence_ids);
    var attested = new Set(root.attested_occurrence_ids);
    var recordedPairs = new Set();
    var waterfall = [];
    for (var index = 0; index < root.selected_leaf_occurrence_ids.length; index += 1) {
      var occurrenceId = root.selected_leaf_occurrence_ids[index];
      var row = checkedReceiptWaterfallRow(
        value.waterfall[index], occurrenceId, eligible.has(occurrenceId), attested.has(occurrenceId), latest
      );
      if (!row) return null;
      if (row.attested) {
        var pairKey = row.attestation_id + ':' + row.match_id;
        if (recordedPairs.has(pairKey)) return null;
        recordedPairs.add(pairKey);
      }
      waterfall.push(row);
    }
    return {root: compactReceiptRoot(root), waterfall: waterfall};
  }

  function resetReceiptState() {
    var token = state.receipt.requestToken + 1;
    state.receipt = {
      phase: 'idle',
      requestToken: token,
      latest: null,
      ownerCik: '',
      page: null,
      pageCursors: [null],
      pageIndex: 0,
      rootCellId: '',
      detail: null,
      detailPhase: 'idle',
      lastFocus: null
    };
    closeReceiptInspector(false);
  }

  function historyRequest(path) {
    return withAuth({ Accept: 'application/json' })
      .then(function (headers) {
        return fetch(ATTESTED_HISTORY_URL + path, {
          headers: headers,
          credentials: 'same-origin',
          cache: 'no-store'
        });
      })
      .then(function (response) {
        if (!response.ok) {
          var failure = new Error('History request failed');
          failure.status = response.status;
          throw failure;
        }
        return response.json();
      });
  }

  function receiptOwnerMatches(target, receipt) {
    var selected = normalizedCik(target && target.cik);
    var conversion = receipt && receipt.companyfacts_conversion_receipt;
    return !!selected && !!conversion && selected === normalizedCik(conversion.cik);
  }

  function setSourceMode(mode, focusPanel) {
    var next = mode === 'receipt' ? 'receipt' : 'map';
    state.sourceMode = next;
    ui.workspace.setAttribute('data-source-mode', next);
    ui.sourceTabs.forEach(function (button) {
      var active = button.getAttribute('data-source-mode') === next;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;
    });
    ui.sourceMapPanel.hidden = next !== 'map';
    ui.receiptPanel.hidden = next !== 'receipt';
    // Do not retain or resume an in-flight private receipt read after the
    // analyst has returned to the public evidence map. A later receipt open
    // starts a fresh, CIK-gated request instead of stranding the UI in loading.
    if (next === 'receipt') {
      closeReceiptInspector(false);
      ensureReceiptForCompany();
    } else {
      resetReceiptState();
      renderReceiptInspector();
    }
    if (focusPanel) {
      (next === 'receipt' ? ui.receiptPanel : ui.sourceMapPanel).focus({ preventScroll: true });
    }
  }

  function receiptFailurePhase(error) {
    return error && (error.status === 401 || error.status === 403) ? 'access' : 'unavailable';
  }

  function ensureReceiptForCompany() {
    var target = company();
    if (!target || state.sourceMode !== 'receipt') return;
    var cik = normalizedCik(target.cik);
    if (!cik) {
      state.receipt.phase = 'mismatch';
      state.receipt.ownerCik = '';
      renderReceipt();
      return;
    }
    if (state.receipt.ownerCik === cik && (
      state.receipt.phase === 'loading' || state.receipt.phase === 'ready' || state.receipt.phase === 'mismatch'
    )) {
      renderReceipt();
      return;
    }
    resetReceiptState();
    state.receipt.ownerCik = cik;
    state.receipt.phase = 'loading';
    var token = state.receipt.requestToken + 1;
    state.receipt.requestToken = token;
    renderReceipt();
    historyRequest('/latest')
      .then(function (payload) {
        if (token !== state.receipt.requestToken || state.sourceMode !== 'receipt') return;
        if (!receiptReadyPayload(payload)) throw new Error('Receipt identity is malformed');
        if (!receiptOwnerMatches(company(), payload)) {
          state.receipt.latest = payload;
          state.receipt.phase = 'mismatch';
          renderReceipt();
          return;
        }
        state.receipt.latest = payload;
        loadReceiptRoots(null, 0);
      })
      .catch(function (error) {
        if (token !== state.receipt.requestToken || state.sourceMode !== 'receipt') return;
        state.receipt.phase = receiptFailurePhase(error);
        renderReceipt();
      });
  }

  function loadReceiptRoots(cursor, pageIndex) {
    var receipt = state.receipt;
    var latest = receipt.latest;
    if (!latest || !isSnapshotId(latest.snapshot_id) || state.sourceMode !== 'receipt') return;
    var previousTotal = receipt.page ? receipt.page.total : null;
    var token = receipt.requestToken + 1;
    receipt.requestToken = token;
    receipt.phase = 'loading';
    receipt.detail = null;
    receipt.rootCellId = '';
    receipt.detailPhase = 'idle';
    closeReceiptInspector(false);
    renderReceipt();
    var suffix = '/snapshots/' + encodeURIComponent(latest.snapshot_id) + '/roots?limit=25';
    if (cursor) suffix += '&cursor=' + encodeURIComponent(cursor);
    historyRequest(suffix)
      .then(function (payload) {
        if (token !== state.receipt.requestToken || state.sourceMode !== 'receipt') return;
        var page = checkedReceiptPagePayload(payload, latest, cursor || null, pageIndex, previousTotal);
        if (!page) throw new Error('Receipt page is malformed');
        receipt.page = page;
        receipt.pageIndex = pageIndex;
        receipt.phase = 'ready';
        renderReceipt();
      })
      .catch(function (error) {
        if (token !== state.receipt.requestToken || state.sourceMode !== 'receipt') return;
        receipt.phase = receiptFailurePhase(error);
        renderReceipt();
      });
  }

  function receiptPageNext() {
    var receipt = state.receipt;
    if (!receipt.page || !receipt.page.nextCursor) return;
    receipt.pageCursors = receipt.pageCursors.slice(0, receipt.pageIndex + 1);
    receipt.pageCursors.push(receipt.page.nextCursor);
    loadReceiptRoots(receipt.page.nextCursor, receipt.pageIndex + 1);
  }

  function receiptPagePrevious() {
    var receipt = state.receipt;
    if (receipt.pageIndex < 1) return;
    loadReceiptRoots(receipt.pageCursors[receipt.pageIndex - 1], receipt.pageIndex - 1);
  }

  function requestReceiptRoot(rootCellId, trigger) {
    var receipt = state.receipt;
    var latest = receipt.latest;
    if (!latest || !isSnapshotId(latest.snapshot_id) || !isRootCellId(rootCellId)) return;
    var cachedRoot = receipt.page && receipt.page.rows.find(function (row) {
      return row.root_cell_id === rootCellId;
    });
    if (!cachedRoot) return;
    receipt.rootCellId = rootCellId;
    receipt.detail = null;
    receipt.detailPhase = 'loading';
    receipt.lastFocus = trigger || document.activeElement;
    var token = receipt.requestToken + 1;
    receipt.requestToken = token;
    renderReceipt();
    receipt.lastFocus = selectedReceiptRootButton() || trigger || document.activeElement;
    renderReceiptInspector();
    openReceiptInspector();
    historyRequest('/snapshots/' + encodeURIComponent(latest.snapshot_id) + '/roots/' + encodeURIComponent(rootCellId))
      .then(function (payload) {
        if (token !== state.receipt.requestToken || state.sourceMode !== 'receipt') return;
        var detail = checkedReceiptDetailPayload(payload, latest, rootCellId, cachedRoot);
        if (!detail) throw new Error('Receipt detail is malformed');
        receipt.detail = detail;
        receipt.detailPhase = 'ready';
        renderReceiptInspector();
      })
      .catch(function () {
        if (token !== state.receipt.requestToken || state.sourceMode !== 'receipt') return;
        receipt.detail = null;
        receipt.detailPhase = 'unavailable';
        renderReceiptInspector();
      });
  }

  function receiptStatusBadge(status) {
    var info = receiptStatusInfo(status);
    return '<span class="ff-receipt-status is-' + esc(info.key) + '">' + pair(info.en, info.zh) + '</span>';
  }

  function receiptStat(labelEn, labelZh, value) {
    return '<div class="ff-receipt-stat"><small>' + pair(labelEn, labelZh) + '</small><strong>' + esc(value == null ? '—' : value) + '</strong></div>';
  }

  function receiptEmpty(titleEn, titleZh, bodyEn, bodyZh, action) {
    return '<div class="ff-receipt-empty"><span class="ff-empty-mark" aria-hidden="true">◇</span><div><h3>' + pair(titleEn, titleZh) + '</h3><p>' + pair(bodyEn, bodyZh) + '</p>' + (action || '') + '</div></div>';
  }

  function renderReceipt() {
    if (!ui.receipt) return;
    var receipt = state.receipt;
    if (receipt.phase === 'idle') {
      ui.receipt.innerHTML = receiptEmpty(
        'Run record', '运行记录',
        'Open this view to see the saved publication details for the selected company.',
        '打开此视图，查看所选公司的已保存发布详情。'
      );
      renderReceiptInspector();
      return;
    }
    if (receipt.phase === 'loading') {
      ui.receipt.innerHTML = '<div class="ff-loading" role="status"><span class="ff-loading-dot" aria-hidden="true"></span>' +
        pair('Loading run record…', '正在载入运行记录…') + '</div>';
      renderReceiptInspector();
      return;
    }
    if (receipt.phase === 'mismatch') {
      var mismatchEn = receipt.ownerCik ?
        'The available record belongs to a different company, so nothing was loaded.' :
        'This company has no SEC identifier in the dataset, so the record cannot be matched.';
      var mismatchZh = receipt.ownerCik ?
        '可用记录属于另一家公司，因此未载入内容。' :
        '数据集中没有该公司的 SEC 标识，因此无法匹配记录。';
      ui.receipt.innerHTML = receiptEmpty(
        'No run record for this company', '该公司暂无运行记录',
        mismatchEn, mismatchZh
      );
      renderReceiptInspector();
      return;
    }
    if (receipt.phase === 'access') {
      ui.receipt.innerHTML = receiptEmpty(
        'Run record unavailable in this session', '当前会话无法访问运行记录',
        'The source map still works. Sign in again, then retry.',
        '来源地图仍可使用。请重新登录后再试。',
        '<button class="ff-receipt-retry" type="button" data-receipt-action="retry">' + pair('Retry', '重试') + '</button>'
      );
      renderReceiptInspector();
      return;
    }
    if (receipt.phase !== 'ready' || !receipt.latest || !receipt.page) {
      ui.receipt.innerHTML = receiptEmpty(
        'Run record temporarily unavailable', '运行记录暂时不可用',
        'The source map still works. Try this view again in a moment.',
        '来源地图仍可使用。请稍后再试。',
        '<button class="ff-receipt-retry" type="button" data-receipt-action="retry">' + pair('Retry', '重试') + '</button>'
      );
      renderReceiptInspector();
      return;
    }

    var latest = receipt.latest;
    var coverage = latest.coverage_summary || {};
    var authority = latest.authority || {};
    var conversion = latest.companyfacts_conversion_receipt || {};
    var clocks = conversion.clocks || {};
    var policy = latest.policy || {};
    var rows = receipt.page.rows;
    var rootRows = rows.length ? rows.map(function (root) {
      var selected = receipt.rootCellId === root.root_cell_id;
      return '<button class="ff-receipt-root' + (selected ? ' is-selected' : '') + '" type="button" data-root-cell-id="' + esc(root.root_cell_id) + '"' +
        ' aria-controls="ff-receipt-inspector" aria-current="' + (selected ? 'true' : 'false') + '"><span class="ff-receipt-root-id"><code title="' + esc(root.root_cell_id) + '">' +
        esc(shortTraceId(root.root_cell_id)) + '</code><small>' + pair(root.selected + ' selected · ' + root.eligible + ' eligible · ' + root.attested + ' recorded', root.selected + ' 个选定 · ' + root.eligible + ' 个符合条件 · ' + root.attested + ' 个已记录') +
        '</small></span>' + receiptStatusBadge(root.status) + '<span class="ff-receipt-root-arrow" aria-hidden="true">›</span></button>';
    }).join('') : receiptEmpty(
      'No root coverage rows', '没有根覆盖行',
      'The sealed receipt contains no root coverage rows.',
      '该密封凭据不包含根覆盖行。'
    );
    var previousDisabled = receipt.pageIndex < 1 ? ' disabled' : '';
    var nextDisabled = !receipt.page.nextCursor ? ' disabled' : '';
    var nonclaims = authority.nonclaims || {};
    var limits = [];
    if (nonclaims.filing_complete === false) limits.push(pair('Does not establish filing completeness.', '不证明披露文件完整性。'));
    if (nonclaims.trading_authority === false) limits.push(pair('Does not grant trading authority.', '不授予交易决策权限。'));
    if (nonclaims.neural_web_authority === false) limits.push(pair('Does not grant Neural Web authority.', '不授予 Neural Web 权限。'));

    ui.receipt.innerHTML = '<div class="ff-receipt-intro"><div><p class="ff-kicker">' + pair('Sealed publication receipt', '密封发布凭据') +
      '</p><h3>' + pair('Recorded correspondence, read at its stated scope', '在声明范围内读取已记录的对应关系') + '</h3><p>' + pair(
        'This view reads a stored receipt. Source material is not reread while you inspect it.',
        '此视图读取存储的凭据；检查期间不会重新读取来源材料。'
      ) + '</p></div><span class="ff-receipt-live-mark" aria-hidden="true">◇</span></div>' +
      '<div class="ff-receipt-identity"><div class="ff-receipt-identity-main"><span>' + pair('Receipt snapshot', '凭据快照') + '</span><code title="' + esc(latest.snapshot_id) + '">' + esc(shortTraceId(latest.snapshot_id)) + '</code></div>' +
      '<div>' + receiptStat('Published', '发布时间', formatDate(latest.published_at)) + '</div>' +
      '<div>' + receiptStat('Issuer CIK', '发行人 CIK', normalizedCik(conversion.cik)) + '</div>' +
      '<div>' + receiptStat('Policy', '策略', policy.version || '—') + '</div></div>' +
      '<section class="ff-receipt-card ff-receipt-authority"><div class="ff-receipt-card-head"><div><p class="ff-kicker">' + pair('Scope', '范围') + '</p><h3>' + pair('What this receipt records', '此凭据记录的内容') + '</h3></div>' +
      '<span class="ff-receipt-scope-mark">' + pair('Scoped', '限定范围') + '</span></div><p>' + pair(
        'Selected Company Facts row correspondence only. The receipt is a sealed publication record, not a source reread.',
        '仅限选定的 Company Facts 行对应关系。该凭据是密封的发布记录，并非来源重读。'
      ) + '</p><ul class="ff-receipt-limits">' + (limits.join('') || '<li>' + pair('No broader authority is supplied.', '未提供更广泛的权限。') + '</li>') + '</ul></section>' +
      '<section class="ff-receipt-card"><div class="ff-receipt-card-head"><div><p class="ff-kicker">' + pair('Coverage control room', '覆盖控制室') + '</p><h3>' + pair('Selected-leaf correspondence states', '选定叶节点对应状态') + '</h3></div><span class="ff-receipt-micro">' + pair('Root cells ' + (coverage.root_cell_count == null ? receipt.page.total : coverage.root_cell_count), '根单元 ' + (coverage.root_cell_count == null ? receipt.page.total : coverage.root_cell_count)) + '</span></div>' +
      '<div class="ff-receipt-status-grid">' +
        '<div>' + receiptStatusBadge('all_leaves_attested') + '<strong>' + esc(coverage.all_leaves_attested == null ? '—' : coverage.all_leaves_attested) + '</strong></div>' +
        '<div>' + receiptStatusBadge('partially_attested') + '<strong>' + esc(coverage.partially_attested == null ? '—' : coverage.partially_attested) + '</strong></div>' +
        '<div>' + receiptStatusBadge('not_attested') + '<strong>' + esc(coverage.not_attested == null ? '—' : coverage.not_attested) + '</strong></div>' +
        '<div>' + receiptStatusBadge('not_evaluable') + '<strong>' + esc(coverage.not_evaluable == null ? '—' : coverage.not_evaluable) + '</strong></div></div></section>' +
      '<section class="ff-receipt-card"><div class="ff-receipt-card-head"><div><p class="ff-kicker">' + pair('Company Facts conversion', 'Company Facts 转换') + '</p><h3>' + pair('Recorded input window', '已记录的输入窗口') + '</h3></div><span class="ff-receipt-micro">' + esc(conversion.availability || '—') + '</span></div><div class="ff-receipt-stats">' +
        receiptStat('Occurrences', '事实条目', conversion.occurrence_count) + receiptStat('Output rows', '输出行', conversion.output_occurrence_count) + receiptStat('PIT eligible', 'PIT 符合条件', conversion.pit_eligible_count) + '</div>' +
        '<dl class="ff-receipt-clocks"><div><dt>' + pair('Captured', '捕获时间') + '</dt><dd>' + esc(formatDate(clocks.captured_at)) + '</dd></div><div><dt>' + pair('Source snapshot', '来源快照') + '</dt><dd>' + esc(formatDate(clocks.source_snapshot_at)) + '</dd></div><div><dt>' + pair('Recorded', '记录时间') + '</dt><dd>' + esc(formatDate(clocks.recorded_at)) + '</dd></div></dl></section>' +
      '<section class="ff-receipt-card ff-receipt-root-card"><div class="ff-receipt-card-head"><div><p class="ff-kicker">' + pair('Receipt cells', '凭据单元') + '</p><h3>' + pair('Open one recorded waterfall', '打开一个已记录的瀑布') + '</h3></div><span class="ff-receipt-micro">' + pair('Page ' + (receipt.pageIndex + 1), '第 ' + (receipt.pageIndex + 1) + ' 页') + '</span></div><p class="ff-receipt-root-note">' + pair(
        'Cell identifiers are trace keys. A user-facing metric label is not inferred where the receipt does not provide one.',
        '单元标识符是追踪键。凭据未提供时不会推断面向用户的指标标签。'
      ) + '</p><div class="ff-receipt-root-list" role="list">' + rootRows + '</div><div class="ff-receipt-pager"><button type="button" data-receipt-action="previous"' + previousDisabled + '>' + pair('Previous', '上一页') + '</button><span>' + pair(receipt.page.returned + ' of ' + receipt.page.total + ' cells', receipt.page.returned + ' / ' + receipt.page.total + ' 个单元') + '</span><button type="button" data-receipt-action="next"' + nextDisabled + '>' + pair('Next', '下一页') + '</button></div></section>';
    renderReceiptInspector();
  }

  function receiptDetailValue(labelEn, labelZh, value) {
    return '<div><dt>' + pair(labelEn, labelZh) + '</dt><dd><code>' + esc(value == null || value === '' ? '—' : value) + '</code></dd></div>';
  }

  function receiptWaterfallRow(row, index) {
    var item = row && typeof row === 'object' ? row : {};
    var attested = item.attested === true;
    var companyfacts = attested && item.companyfacts && typeof item.companyfacts === 'object' ? item.companyfacts : null;
    var trail = attested && item.stored_b3_projection && typeof item.stored_b3_projection === 'object' ? item.stored_b3_projection : null;
    var heading = attested ? pair('Recorded correspondence', '已记录的对应关系') : pair('No recorded correspondence', '没有已记录的对应关系');
    var contents = attested && companyfacts ? '<dl class="ff-receipt-waterfall-fields">' +
      receiptDetailValue('Concept', '概念', [companyfacts.taxonomy, companyfacts.concept].filter(Boolean).join(': ')) +
      receiptDetailValue('Period', '期间', companyfacts.period && [companyfacts.period.start, companyfacts.period.end].filter(Boolean).join(' → ')) +
      receiptDetailValue('Unit', '单位', companyfacts.unit) + receiptDetailValue('Exact value', '精确数值', companyfacts.value) +
      receiptDetailValue('Accession', '文件编号', companyfacts.accession) + '</dl>' +
      '<details class="ff-receipt-projection"><summary>' + pair('Stored provenance projection', '存储的溯源投影') + '</summary><dl class="ff-receipt-waterfall-fields">' +
      receiptDetailValue('Attestation ID', '证明 ID', item.attestation_id) + receiptDetailValue('Match ID', '匹配 ID', item.match_id) +
      receiptDetailValue('Package ID', '包 ID', trail && trail.package_id) + receiptDetailValue('Extraction ID', '提取 ID', trail && trail.extraction_id) +
      receiptDetailValue('Recorded at', '记录时间', trail && trail.attested_at) + '</dl></details>' :
      '<p class="ff-receipt-unmatched">' + pair(
        item.eligible === false ? 'No eligible selected leaf is recorded for this row.' : 'No selected correspondence is recorded in this receipt.',
        item.eligible === false ? '该行未记录符合条件的选定叶节点。' : '该凭据未记录选定对应关系。'
      ) + '</p>';
    return '<article class="ff-receipt-waterfall-row' + (attested ? ' is-recorded' : ' is-open') + '"><div class="ff-receipt-waterfall-head"><span class="ff-receipt-waterfall-index" aria-hidden="true">' + (index + 1) + '</span><div><strong>' + heading + '</strong><code title="' + esc(item.occurrence_id || '') + '">' + esc(shortTraceId(item.occurrence_id)) + '</code></div><span class="ff-receipt-leaf-state">' + pair(item.eligible === false ? 'Not eligible' : 'Eligible', item.eligible === false ? '不符合条件' : '符合条件') + '</span></div>' + contents + '</article>';
  }

  function renderReceiptInspector() {
    if (!ui.receiptInspectorBody) return;
    var receipt = state.receipt;
    if (!receipt.rootCellId) {
      ui.receiptInspectorTitle.innerHTML = pair('Choose a value', '选择一个数值');
      ui.receiptInspectorBody.innerHTML = '<div class="ff-evidence-empty"><span class="ff-empty-mark" aria-hidden="true">◇</span><p>' + pair(
        'Choose a value to see its recorded source path.',
        '选择一个数值，查看其记录的来源路径。'
      ) + '</p></div>';
      return;
    }
    ui.receiptInspectorTitle.innerHTML = pair('Receipt cell', '凭据单元') + '<code class="ff-receipt-inspector-id" title="' + esc(receipt.rootCellId) + '">' + esc(shortTraceId(receipt.rootCellId)) + '</code>';
    if (receipt.detailPhase === 'loading') {
      ui.receiptInspectorBody.innerHTML = '<div class="ff-loading" role="status"><span class="ff-loading-dot" aria-hidden="true"></span>' + pair('Loading recorded trail…', '正在载入已记录轨迹…') + '</div>';
      return;
    }
    if (receipt.detailPhase !== 'ready' || !receipt.detail) {
      ui.receiptInspectorBody.innerHTML = receiptEmpty(
        'Value details temporarily unavailable', '数值详情暂时不可用',
        'The source path is shown only when its recorded details can be read.',
        '仅在能够读取已记录详情时，才会显示来源路径。',
        '<button class="ff-receipt-retry" type="button" data-receipt-detail-retry="true">' + pair('Retry', '重试') + '</button>'
      );
      return;
    }
    var detail = receipt.detail;
    var root = detail.root;
    var waterfall = detail.waterfall;
    var summary = root.attested + ' of ' + root.selected + ' selected leaves have recorded correspondence';
    var waterfallHtml = waterfall.length ? waterfall.map(receiptWaterfallRow).join('') : receiptEmpty(
      'No selected leaves supplied', '未提供选定叶节点',
      'This receipt cell has no selected leaf rows to display.',
      '该凭据单元没有可显示的选定叶节点行。'
    );
    ui.receiptInspectorBody.innerHTML = '<div class="ff-receipt-inspector-summary">' + receiptStatusBadge(root.status) + '<p>' + pair(summary, root.attested + ' / ' + root.selected + ' 个选定叶节点有已记录的对应关系') + '</p><p class="ff-receipt-boundary">' + pair(
      'This waterfall preserves unmatched leaves and does not reread source material.',
      '此瀑布保留未匹配叶节点，且不重新读取来源材料。'
    ) + '</p></div><div class="ff-receipt-waterfall">' + waterfallHtml + '</div>';
  }

  function receiptUrl(receipt) {
    return safeUrl(receipt && (receipt.source_url || receipt.url || receipt.filing_url));
  }

  function receiptAccession(receipt) {
    return String((receipt && (receipt.accession || receipt.accession_number)) || '—');
  }

  function plainLimitationPair(value) {
    var raw = String(value || '').toLowerCase();
    var known = {
      phrase_based_label_matching: ['Phrase matching can miss a renamed metric.', '短语匹配可能遗漏改名后的指标。'],
      does_not_establish_management_motive: ['This comparison does not establish management motive.', '本次对比不能证明管理层动机。'],
      does_not_determine_legal_materiality: ['This comparison does not determine legal materiality.', '本次对比不判断法律重大性。'],
      section_heading_detection_is_pattern_based: ['Section matching depends on filing headings and may be incomplete.', '章节匹配依赖财报标题，可能不完整。'],
      does_not_quantify_economic_effect: ['The text comparison does not quantify an economic effect.', '文本对比不量化经济影响。'],
      does_not_classify_the_reason_for_change: ['The text comparison does not classify why wording changed.', '文本对比不判断措辞变化的原因。'],
      firm_extraction_is_pattern_based: ['Firm-name matching is pattern based and should be checked in the source.', '事务所名称匹配基于模式，应在原文中核验。'],
      engagement_change_requires_source_review: ['Confirm any engagement change in the original filing.', '请在原始财报中确认任何审计委聘变化。'],
      does_not_determine_remediation_status: ['The wording alone does not establish remediation status.', '单凭措辞无法确定整改状态。'],
      negation_handling_is_sentence_based: ['Context can extend beyond the matched sentence.', '上下文可能超出匹配句子。'],
      absence_is_measured_within_supplied_filing_text: ['Absence is measured only within the supplied filing text.', '“未出现”只在提供的财报文本范围内成立。'],
      cross_form_kpi_cadence_is_not_comparable: ['Different reporting forms may disclose a metric on different schedules.', '不同类型的报表可能按不同节奏披露指标。']
    };
    var knownPair = known[raw];
    return knownPair ? pair(knownPair[0], knownPair[1]) : pair(
      'Review the supplied filing scope and source excerpts before relying on this observation.',
      '在依赖此观察结果前，请核对提供的财报范围和来源摘录。'
    );
  }

  function benignExplanationPair(value) {
    var raw = String(value || '').trim();
    var known = {
      'A metric can be renamed, moved to earnings materials, or omitted in a shorter filing.': [
        'A metric can be renamed, moved to earnings materials, or omitted in a shorter filing.',
        '指标可能更名、移至业绩材料，或在较短财报中省略。'
      ],
      'This is a lexical change flag, not a legal-materiality conclusion.': [
        'This is a lexical change flag, not a legal-materiality conclusion.',
        '这是文字变化提示，并非对法律重大性的结论。'
      ],
      'Policy wording can change because of presentation, standard-adoption boilerplate, or relocation.': [
        'Policy wording can change because of presentation, standard-adoption boilerplate, or relocation.',
        '政策措辞可能因展示方式、准则采用模板文本或位置调整而变化。'
      ],
      'A firm-name change can reflect a legal-name update or audit-firm combination.': [
        'A firm-name change can reflect a legal-name update or audit-firm combination.',
        '事务所名称变化可能反映法定名称更新或审计机构合并。'
      ],
      'Control language can describe a remediated, historical, or acquired-business condition.': [
        'Control language can describe a remediated, historical, or acquired-business condition.',
        '控制相关措辞可能描述已整改、历史性或收购业务相关的情况。'
      ]
    };
    var translated = known[raw];
    return translated ? pair(translated[0], translated[1]) : pair(
      raw || 'The engine records a non-exclusive alternative explanation; source review is still needed.',
      '引擎记录了一个非排他的替代解释；仍需核对原始来源。'
    );
  }

  function receiptMarkup(receipt, index) {
    var href = receiptUrl(receipt);
    var form = String((receipt && receipt.form) || 'SEC filing');
    var accession = receiptAccession(receipt);
    var filingRole = String((receipt && receipt.filing_role) || '');
    var roleMarkup = filingRole === 'current' ? '<span class="ff-filing-role is-current">' + pair('Current', '本期') + '</span>' :
      (filingRole === 'prior' ? '<span class="ff-filing-role is-prior">' + pair('Prior', '上期') + '</span>' : '');
    // The projection keeps the exact raw source fragment for its hash/span
    // receipt, but supplies an inert presentation companion so Inline XBRL
    // attributes never flood the analyst-facing evidence pane.
    var excerpt = String((receipt && (receipt.display_excerpt || receipt.source_excerpt)) || '').trim();
    var sourceAction = href ? '<a class="ff-receipt-link" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' +
      pair('Open SEC filing', '打开 SEC 财报') + '<span aria-hidden="true">↗</span></a>' : '<span class="ff-receipt-basis">' +
      pair('SEC link not supplied', '未提供 SEC 链接') + '</span>';
    return '<article class="ff-disclosure-receipt"><div class="ff-disclosure-receipt-head"><span class="ff-receipt-icon" aria-hidden="true">' + (index + 1) + '</span><div><strong>' + esc(form) + roleMarkup + '</strong><span class="ff-disclosure-accession">' + esc(accession) + '</span></div>' + sourceAction + '</div>' +
      (excerpt ? '<blockquote class="ff-source-excerpt">' + esc(excerpt) + '</blockquote>' : '<p class="ff-receipt-basis">' + pair('No bounded source excerpt was supplied.', '未提供受限长度的来源摘录。') + '</p>') + '</article>';
  }

  function redlineMarkup(redline) {
    if (!redline) return '';
    var edits = Array.isArray(redline.inline_edits) ? redline.inline_edits : [];
    var lines = edits.length ? edits.slice(0, 8).map(function (edit) {
      var before = String(edit.prior_text || '').trim();
      var after = String(edit.current_text || '').trim();
      var beforeLine = before ? '<div class="ff-diff-line is-prior"><span aria-hidden="true">−</span><span>' + esc(before) + '</span></div>' : '';
      var afterLine = after ? '<div class="ff-diff-line is-current"><span aria-hidden="true">+</span><span>' + esc(after) + '</span></div>' : '';
      return '<div class="ff-diff-edit">' + beforeLine + afterLine + '</div>';
    }).join('') : '<p class="ff-redline-fallback">' + pair(
      'No inline token view was supplied; compare the bounded source excerpts below.',
      '未提供词级对照；请比较下方受限长度的来源摘录。'
    ) + '</p>';
    return '<div class="ff-diff-card"><div class="ff-diff-card-head"><span>' + disclosureSectionPair(redlineSection(redline)) + '</span><span class="ff-diff-machine-note">' +
      pair('Machine-matched text', '机器匹配文本') + '</span></div>' + lines + '</div>';
  }

  function redlinesForDisclosureFinding(finding) {
    if (!finding) return [];
    var prior = String(finding.prior_accession || '');
    var current = String(finding.current_accession || '');
    var section = disclosureFindingSection(finding);
    var evidenceBlockIds = (Array.isArray(finding.evidence_receipts) ? finding.evidence_receipts : []).map(function (receipt) {
      return String((receipt && receipt.block_id) || '');
    }).filter(Boolean);
    return activeRedlines().filter(function (redline) {
      var oldReceipt = redline.prior_receipt || {};
      var newReceipt = redline.current_receipt || {};
      var accessionMatches = (!prior || receiptAccession(oldReceipt) === prior) && (!current || receiptAccession(newReceipt) === current);
      var blockMatches = evidenceBlockIds.length && [oldReceipt, newReceipt].some(function (receipt) {
        return evidenceBlockIds.indexOf(String((receipt && receipt.block_id) || '')) >= 0;
      });
      // Section inheritance remains useful for exploration, but a detector's
      // exact evidence block IDs are the stronger source contract. This keeps
      // a Revenue Recognition prompt from opening an unrelated later lease
      // redline that happens to share an inherited note-section key.
      return accessionMatches && (blockMatches || (!evidenceBlockIds.length && (section === 'other' || redlineSection(redline) === section)));
    }).slice(0, 2);
  }

  function renderDisclosureEvidence(item, kind) {
    if (!item) {
      renderEvidence(null);
      return;
    }
    var isFinding = kind === 'disclosure-finding';
    var title = isFinding ? disclosureFindingLabel(item) : pair(redlineOperationInfo(item).en, redlineOperationInfo(item).zh);
    var receipts = isFinding ? (Array.isArray(item.evidence_receipts) ? item.evidence_receipts : []) : [item.prior_receipt, item.current_receipt].filter(Boolean);
    var relatedRedlines = isFinding ? redlinesForDisclosureFinding(item) : [item];
    var status = isFinding ? disclosureFindingState(item) : { icon: '◇', en: 'Observed text change', zh: '观察到文本变化' };
    var summary = isFinding ? disclosureWhyPair(item) : pair(
      'The comparison engine matched text from the supplied filings. Read both excerpts before interpreting the change.',
      '对比引擎匹配了提供财报中的文本；请先阅读两段摘录再解读变化。'
    );
    var limitations = isFinding ? (Array.isArray(item.limitations) ? item.limitations : []) : [];
    var limitationHtml = limitations.length ? limitations.map(function (value) { return '<li>' + plainLimitationPair(value) + '</li>'; }).join('') :
      '<li>' + pair('This is an observed lexical change, not an explanation of motive, materiality, or impact.', '这是观察到的文字变化，不代表对动机、重大性或影响的解释。') + '</li>';
    var alternative = isFinding && item.benign_explanation ? '<p class="ff-disclosure-alternative"><strong>' + pair('Alternative explanation: ', '其他可能解释：') + '</strong>' + benignExplanationPair(item.benign_explanation) + '</p>' : '';
    var redlineHtml = relatedRedlines.length ? relatedRedlines.map(redlineMarkup).join('') : '<p class="ff-redline-fallback">' + pair(
      'No matched redline was supplied for this review prompt. Use the source excerpts to inspect the filing language.',
      '该复核提示未提供匹配的逐字对照；请使用来源摘录核对财报措辞。'
    ) + '</p>';
    var receiptHtml = receipts.length ? receipts.slice(0, 6).map(receiptMarkup).join('') : '<div class="ff-empty-state"><div><p>' + pair(
      'No filing receipt was supplied for this comparison result.', '该对比结果未提供财报凭据。'
    ) + '</p></div></div>';
    ui.evidenceTitle.innerHTML = title;
    ui.evidenceBody.innerHTML = '<div class="ff-proof-badge ff-disclosure-proof-badge" data-priority="watch"><span aria-hidden="true">' + status.icon + '</span>' +
      pair(status.en, status.zh) + '</div><p class="ff-proof-summary">' + summary + '</p><p class="ff-disclosure-honesty">' + pair(
      'Observed language is not a motive claim. The source excerpts are the evidence.',
      '观察到的措辞不是动机主张；来源摘录才是证据。'
    ) + '</p>' + alternative +
      '<section class="ff-proof-section"><h3>' + pair('Matched wording', '匹配到的措辞') + '</h3>' + redlineHtml + '</section>' +
      '<section class="ff-proof-section"><h3>' + pair('SEC source excerpts', 'SEC 来源摘录') + '</h3><div class="ff-disclosure-receipts">' + receiptHtml + '</div></section>' +
      '<section class="ff-proof-section"><h3>' + pair('Reading boundaries', '阅读边界') + '</h3><ul class="ff-limitations">' + limitationHtml + '</ul></section>';
  }

  function renderTabEvidenceEmpty(tab) {
    var guides = {
      statements: {
        icon: '▥', title: ['How to read these financials', '如何阅读这些财务数据'],
        body: ['Start with the newest column, then scan left to see whether the move is new or part of a trend.', '先看最新一列，再向左回看，判断这次变化是新出现还是延续趋势。'],
        steps: [['Compare key periods', '对比关键期间', 'compare'], ['Return to key signals', '返回关键信号', 'radar'], ['Verify the source', '核对原始来源', 'trace']]
      },
      disclosures: {
        icon: '◫', title: ['Choose a filing change', '选择一项披露变化'],
        body: ['Open a change to read the current and prior SEC excerpts side by side. The comparison describes wording, not motive.', '打开一项变化，并列阅读本期与上期的 SEC 摘录。这里描述的是措辞变化，而非动机。'],
        steps: [['See exact redlines', '查看逐字差异', 'redlines'], ['View filing history', '查看披露历史', 'timeline'], ['Verify the source', '核对原始来源', 'trace']]
      },
      redlines: {
        icon: '≠', title: ['Choose an exact wording change', '选择一处逐字变化'],
        body: ['Open a matched change to see what was removed, added, or replaced in the source text.', '打开一处匹配变化，查看原文中删除、新增或替换的内容。'],
        steps: [['Read summarized changes', '阅读变化摘要', 'disclosures'], ['View filing history', '查看披露历史', 'timeline'], ['Verify the source', '核对原始来源', 'trace']]
      },
      timeline: {
        icon: '◷', title: ['Use the filing history as context', '用披露历史补充背景'],
        body: ['Confirm which forms and dates are being compared before interpreting any signal or wording change.', '解读任何信号或措辞变化前，请先确认对比的是哪些表格和日期。'],
        steps: [['Read wording changes', '阅读措辞变化', 'disclosures'], ['Compare key periods', '对比关键期间', 'compare'], ['Verify the source', '核对原始来源', 'trace']]
      },
      compare: {
        icon: '↔', title: ['Choose two periods to compare', '选择两个期间进行对比'],
        body: ['Use the selectors to compare reported values. Direction alone is not a verdict; open a signal for the rule and context.', '使用选择器对比披露数值。方向本身不是结论；请打开信号查看规则和背景。'],
        steps: [['Open key signals', '打开关键信号', 'radar'], ['Read wording changes', '阅读措辞变化', 'disclosures'], ['Verify the source', '核对原始来源', 'trace']]
      },
      trace: {
        icon: '✓', title: ['Your source and coverage guide', '来源与覆盖指南'],
        body: ['Use the source map for SEC links. Open the run record when you need the saved publication details.', '使用来源地图查看 SEC 链接。需要已保存的发布详情时，可打开运行记录。'],
        steps: [['Return to key signals', '返回关键信号', 'radar'], ['Compare key periods', '对比关键期间', 'compare'], ['Read filing history', '阅读披露历史', 'timeline']]
      }
    };
    var guide = guides[tab] || guides.trace;
    ui.evidenceTitle.innerHTML = pair(guide.title[0], guide.title[1]);
    ui.evidenceBody.innerHTML = '<div class="ff-view-guide"><span class="ff-view-guide-icon" aria-hidden="true">' + guide.icon + '</span><p>' +
      pair(guide.body[0], guide.body[1]) + '</p><div class="ff-view-guide-actions">' + guide.steps.map(function (step) {
        return '<button type="button" data-go-tab="' + esc(step[2]) + '">' + pair(step[0], step[1]) + '<span aria-hidden="true">→</span></button>';
      }).join('') + '</div></div>';
  }

  function renderCurrentEvidence() {
    if (state.evidenceKind === 'disclosure-finding') {
      renderDisclosureEvidence(selectedDisclosureFinding(), 'disclosure-finding');
      return;
    }
    if (state.evidenceKind === 'redline') {
      renderDisclosureEvidence(selectedRedline(), 'redline');
      return;
    }
    if (state.evidenceKind === 'view') {
      renderTabEvidenceEmpty(state.tab);
      return;
    }
    renderEvidence(selectedFinding());
  }

  function renderEvidence(finding) {
    if (!finding) {
      ui.evidenceTitle.innerHTML = pair('Choose a signal', '选择一个信号');
      ui.evidenceBody.innerHTML = '<div class="ff-evidence-empty"><span class="ff-empty-mark" aria-hidden="true">↳</span><p>' +
      pair('Choose a signal to understand what it means, compare the numbers, and verify the SEC source.', '选择一个信号，了解它的含义、对比关键数字并核对 SEC 来源。') + '</p></div>';
      return;
    }
    var priority = priorityInfo(finding.priority);
    ui.evidenceTitle.innerHTML = fieldPair(finding, 'title', 'Untitled finding');
    var values = Array.isArray(finding.values) ? finding.values : [];
    var valueRows = values.length ? values.map(function (value) {
      return '<div class="ff-value-row"><div class="ff-value-label">' + fieldPair(value, 'label', prettify(value.key)) + '</div>' +
        '<div class="ff-value-cell"><small>' + pair('Current', '本期') + '</small><strong>' + esc(formatValue(value.current, value.format)) + '</strong></div>' +
        '<div class="ff-value-cell"><small>' + pair('Prior', '上期') + '</small><strong>' + esc(formatValue(value.prior, value.format)) + '</strong></div>' +
        '<div class="ff-value-cell"><small>' + pair('Change', '变化') + '</small><strong>' + esc(formatSigned(value.delta, value.format)) + '</strong></div></div>';
    }).join('') : '<div class="ff-empty-state"><div><p>' + pair('No value bridge was supplied for this result.', '此结果未提供数值变化桥。') + '</p></div></div>';

    var receipts = Array.isArray(finding.evidence) ? finding.evidence : [];
    var receiptHtml = receipts.length ? receipts.map(function (receipt, index) {
      var href = safeUrl(receipt.url);
      var label = fieldPair(receipt, 'label', 'SEC source ' + (index + 1));
      var labelMarkup = href ? '<a class="ff-receipt-link" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>' : label;
      return '<li class="ff-receipt"><span class="ff-receipt-icon" aria-hidden="true">' + (index + 1) + '</span>' +
        '<div><div class="ff-receipt-label">' + labelMarkup + '</div><div class="ff-receipt-basis">' +
        basisPair(receipt.basis) + '</div></div><span class="ff-receipt-date">' + esc(formatDate(receipt.date)) + '</span></li>';
    }).join('') : '<li class="ff-receipt"><span class="ff-receipt-icon" aria-hidden="true">—</span><div><div class="ff-receipt-label">' +
      pair('No source link supplied', '未提供来源链接') + '</div><div class="ff-receipt-basis">' +
      pair('Treat this result as incomplete until its source is available.', '在来源可用前，请将此结果视为不完整。') + '</div></div></li>';

    var limitationsEn = Array.isArray(finding.limitations_en) ? finding.limitations_en : [];
    var limitationsZh = Array.isArray(finding.limitations_zh) ? finding.limitations_zh : [];
    var limitationCount = Math.max(limitationsEn.length, limitationsZh.length);
    var limitationHtml = '';
    for (var index = 0; index < limitationCount; index += 1) {
      limitationHtml += '<li>' + pair(limitationsEn[index] || limitationsZh[index], limitationsZh[index] || limitationsEn[index]) + '</li>';
    }
    if (!limitationHtml) limitationHtml = '<li>' + pair('No finding-specific limitation was supplied.', '未提供该发现的特定局限。') + '</li>';

    ui.evidenceBody.innerHTML = '<div class="ff-proof-badge" data-priority="' + esc(finding.priority || 'watch') + '"><span aria-hidden="true">' +
      priority.icon + '</span>' + pair(priority.en, priority.zh) + '</div>' +
      '<section class="ff-signal-meaning"><span>' + pair('Why this matters', '为什么重要') + '</span><p>' +
      fieldPair(finding, 'summary', 'No summary supplied.') + '</p></section><div class="ff-proof-basis">' +
      '<span><b>' + pair('Normalized inputs', '标准化输入') + '</b>' + esc([finding.period_current, finding.period_prior].filter(Boolean).join(' / ') || '—') + '</span>' +
      '<span><b>' + pair('Calculated', '规则计算') + '</b>' + pair('Deterministic rule', '确定性规则') + '</span>' +
      '<span><b>' + pair('Limits', '局限') + '</b>' + limitationCount + '</span></div>' +
      '<section class="ff-proof-section"><h3>' + pair('Numbers behind the signal', '信号背后的数字') + '</h3><div class="ff-value-grid">' + valueRows + '</div></section>' +
      '<section class="ff-proof-section ff-proof-actions"><h3>' + pair('Explore the full picture', '继续查看完整情况') + '</h3><div class="ff-proof-action-grid">' +
      '<button type="button" data-go-tab="compare">' + pair('Compare periods', '对比期间') + '<span aria-hidden="true">→</span></button>' +
      '<button type="button" data-go-tab="disclosures">' + pair('Read filing changes', '阅读披露变化') + '<span aria-hidden="true">→</span></button>' +
      '<button type="button" data-go-tab="trace">' + pair('Verify SEC sources', '核对 SEC 来源') + '<span aria-hidden="true">→</span></button>' +
      '</div></section>' +
      '<section class="ff-proof-section"><h3>' + pair('Verify with the SEC', '通过 SEC 核对') + '</h3><ol class="ff-receipts">' + receiptHtml + '</ol></section>' +
      '<details class="ff-proof-details"><summary>' + pair('How this signal was detected', '这个信号如何识别') + '</summary><div><code class="ff-proof-code">' +
      fieldPair(finding, 'formula', 'Formula not supplied') + '</code><p class="ff-threshold"><strong>' + pair('Signal appears when: ', '信号触发条件：') + '</strong>' +
      fieldPair(finding, 'threshold', 'Threshold not supplied') + '</p></div></details>' +
      '<details class="ff-proof-details"><summary>' + pair('What this signal cannot tell you', '这个信号无法说明什么') + '</summary><div><ul class="ff-limitations">' + limitationHtml + '</ul></div></details>';
  }

  function setTab(tab, focusPanel) {
    var allowed = ['radar', 'statements', 'disclosures', 'redlines', 'timeline', 'compare', 'trace'];
    if (allowed.indexOf(tab) === -1) tab = 'radar';
    var previousTab = state.tab;
    state.tab = tab;
    ui.workspace.setAttribute('data-tab', tab);
    ui.tabs.forEach(function (button) {
      var active = button.getAttribute('data-tab') === tab;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;
      var panel = byId(button.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
    });
    if (previousTab !== tab) {
      closeEvidence(false);
      closeReceiptInspector(false);
      if (previousTab === 'trace' && tab !== 'trace') resetReceiptState();
    }
    if (tab === 'radar') {
      state.evidenceKind = 'finding';
      renderEvidence(selectedFinding());
    } else if (tab === 'disclosures') {
      if (state.evidenceKind !== 'disclosure-finding' || !selectedDisclosureFinding()) {
        state.evidenceKind = 'view';
        renderTabEvidenceEmpty(tab);
      }
    } else if (tab === 'redlines') {
      if (state.evidenceKind !== 'redline' || !selectedRedline()) {
        state.evidenceKind = 'view';
        renderTabEvidenceEmpty(tab);
      }
    } else if (tab === 'trace') {
      state.evidenceKind = 'view';
      renderTabEvidenceEmpty(tab);
      setSourceMode(state.sourceMode, false);
    } else {
      state.evidenceKind = 'view';
      renderTabEvidenceEmpty(tab);
    }
    updateViewStatus();
    if (focusPanel) {
      var selectedTab = document.querySelector('.ff-tab[data-tab="' + tab + '"]');
      var targetPanel = selectedTab ? byId(selectedTab.getAttribute('aria-controls')) : null;
      if (targetPanel) targetPanel.focus({ preventScroll: true });
    }
  }

  function updateViewStatus() {
    var target = company();
    if (!target) return;
    var findings = orderedFindings(target);
    var periods = Array.isArray(target.periods) ? target.periods : [];
    var evidenceCount = findings.reduce(function (total, finding) {
      return total + (Array.isArray(finding.evidence) ? finding.evidence.length : 0);
    }, 0);
    if (state.tab === 'radar') {
      ui.viewStatus.innerHTML = pair(findings.length + ' signals · filed ' + formatDate(target.latest_filed),
        findings.length + ' 个信号 · 披露于 ' + formatDate(target.latest_filed));
    } else if (state.tab === 'statements') {
      ui.viewStatus.innerHTML = pair(periods.length + ' normalized periods', periods.length + ' 个标准化期间');
    } else if (state.tab === 'compare') {
      ui.viewStatus.innerHTML = pair('Neutral period bridge', '中性期间变化桥');
    } else if (state.tab === 'disclosures') {
      var disclosureCount = disclosureFindingsForView(target).length;
      ui.viewStatus.innerHTML = pair(
        disclosureCount + ' observed wording change' + (disclosureCount === 1 ? '' : 's'),
        disclosureCount + ' 项观察到的措辞变化'
      );
    } else if (state.tab === 'redlines') {
      var redlineCount = activeRedlines(target).length;
      ui.viewStatus.innerHTML = pair(
        redlineCount + ' matched text change' + (redlineCount === 1 ? '' : 's'),
        redlineCount + ' 条匹配文本变化'
      );
    } else if (state.tab === 'timeline') {
      var filingCount = disclosureDocuments(target).length;
      ui.viewStatus.innerHTML = pair(
        filingCount + ' filing' + (filingCount === 1 ? '' : 's') + ' in the source trail',
        '来源轨迹中有 ' + filingCount + ' 份财报'
      );
    } else if (state.sourceMode === 'receipt') {
      var receipt = state.receipt;
      if (receipt.phase === 'ready' && receipt.page) {
        ui.viewStatus.innerHTML = pair(receipt.page.total + ' receipt cells', receipt.page.total + ' 个凭据单元');
      } else if (receipt.phase === 'mismatch') {
        ui.viewStatus.innerHTML = pair('No issuer receipt', '无该发行人凭据');
      } else {
        ui.viewStatus.innerHTML = pair('Receipt on demand', '按需读取凭据');
      }
    } else {
      ui.viewStatus.innerHTML = pair(evidenceCount + ' source links', evidenceCount + ' 条来源链接');
    }
  }

  function searchCompanies(query) {
    var needle = String(query || '').trim().toLowerCase();
    var matches = Object.keys(companies()).map(function (key) {
      var item = companies()[key];
      return { key: key, company: item };
    }).filter(function (entry) {
      if (!needle) return true;
      var haystack = [entry.key, entry.company.symbol, entry.company.name, entry.company.sector].filter(Boolean).join(' ').toLowerCase();
      return haystack.indexOf(needle) >= 0;
    }).sort(function (a, b) {
      var aStarts = a.key.toLowerCase().indexOf(needle) === 0 ? 0 : 1;
      var bStarts = b.key.toLowerCase().indexOf(needle) === 0 ? 0 : 1;
      return aStarts - bStarts || a.key.localeCompare(b.key);
    }).slice(0, 10);
    state.searchMatches = matches;
    state.searchIndex = matches.length ? 0 : -1;
    renderSearchOptions();
  }

  function renderSearchOptions() {
    if (!state.searchMatches.length) {
      ui.companyOptions.innerHTML = '<div class="ff-search-empty">' + pair('No covered company matches.', '覆盖范围内无匹配公司。') + '</div>';
      ui.companyOptions.hidden = false;
      ui.search.setAttribute('aria-expanded', 'true');
      ui.search.setAttribute('aria-activedescendant', '');
      return;
    }
    ui.companyOptions.innerHTML = state.searchMatches.map(function (entry, index) {
      var target = entry.company;
      var optionId = 'ff-company-option-' + index;
      return '<button type="button" class="ff-company-option' + (index === state.searchIndex ? ' is-active' : '') + '" role="option"' +
        ' id="' + optionId + '" data-symbol="' + esc(entry.key) + '" aria-selected="' + (index === state.searchIndex ? 'true' : 'false') + '">' +
        '<span class="ff-option-symbol">' + esc(target.symbol || entry.key) + '</span><span><span class="ff-option-name">' +
        esc(target.name || entry.key) + '</span><span class="ff-option-sector">' + esc(target.sector || '—') + '</span></span></button>';
    }).join('');
    ui.companyOptions.hidden = false;
    ui.search.setAttribute('aria-expanded', 'true');
    ui.search.setAttribute('aria-activedescendant', 'ff-company-option-' + state.searchIndex);
  }

  function closeSearch() {
    ui.companyOptions.hidden = true;
    ui.search.setAttribute('aria-expanded', 'false');
    ui.search.setAttribute('aria-activedescendant', '');
    state.searchIndex = -1;
  }

  function moveSearchIndex(delta) {
    if (!state.searchMatches.length) return;
    state.searchIndex = (state.searchIndex + delta + state.searchMatches.length) % state.searchMatches.length;
    renderSearchOptions();
    var active = byId('ff-company-option-' + state.searchIndex);
    if (active) active.scrollIntoView({ block: 'nearest' });
  }

  function openEvidence() {
    var selected = state.evidenceKind === 'disclosure-finding' ? selectedDisclosureFinding() :
      state.evidenceKind === 'redline' ? selectedRedline() : selectedFinding();
    if (desktopMedia.matches || !selected) return;
    // renderFindings replaces the clicked button before the sheet opens. Resolve
    // its new DOM counterpart so closing the modal returns keyboard focus to the
    // finding that launched it instead of leaving focus on <body> or a hidden tab.
    state.lastFocus = selectedEvidenceButton() || document.activeElement;
    ui.evidence.classList.add('is-open');
    ui.evidence.setAttribute('role', 'dialog');
    ui.evidence.setAttribute('aria-modal', 'true');
    ui.scrim.hidden = false;
    document.body.classList.add('ff-modal-open');
    setInert(ui.main, true);
    setInert(ui.siteNav, true);
    window.requestAnimationFrame(function () { ui.evidenceClose.focus(); });
  }

  function closeEvidence(restoreFocus) {
    var wasOpen = ui.evidence.classList.contains('is-open');
    ui.evidence.classList.remove('is-open');
    ui.evidence.removeAttribute('role');
    ui.evidence.removeAttribute('aria-modal');
    ui.scrim.hidden = true;
    document.body.classList.remove('ff-modal-open');
    setInert(ui.main, false);
    setInert(ui.siteNav, false);
    if (wasOpen && restoreFocus !== false && state.lastFocus && typeof state.lastFocus.focus === 'function') {
      state.lastFocus.focus({ preventScroll: true });
    }
  }

  function openReceiptInspector() {
    if (desktopMedia.matches || !state.receipt.rootCellId) return;
    ui.receiptInspector.classList.add('is-open');
    ui.receiptInspector.setAttribute('role', 'dialog');
    ui.receiptInspector.setAttribute('aria-modal', 'true');
    ui.scrim.hidden = false;
    document.body.classList.add('ff-modal-open');
    setInert(ui.main, true);
    setInert(ui.siteNav, true);
    window.requestAnimationFrame(function () { ui.receiptInspectorClose.focus(); });
  }

  function closeReceiptInspector(restoreFocus) {
    if (!ui.receiptInspector) return;
    var wasOpen = ui.receiptInspector.classList.contains('is-open');
    ui.receiptInspector.classList.remove('is-open');
    ui.receiptInspector.removeAttribute('role');
    ui.receiptInspector.removeAttribute('aria-modal');
    if (!ui.evidence.classList.contains('is-open')) {
      ui.scrim.hidden = true;
      document.body.classList.remove('ff-modal-open');
      setInert(ui.main, false);
      setInert(ui.siteNav, false);
    }
    if (wasOpen && restoreFocus !== false && state.receipt.lastFocus && typeof state.receipt.lastFocus.focus === 'function') {
      state.receipt.lastFocus.focus({ preventScroll: true });
    }
  }

  function setInert(element, inert) {
    if (!element) return;
    if (inert) {
      element.setAttribute('inert', '');
      element.setAttribute('aria-hidden', 'true');
    } else {
      element.removeAttribute('inert');
      element.removeAttribute('aria-hidden');
    }
  }

  function focusableInEvidence() {
    return Array.prototype.slice.call(ui.evidence.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(function (node) { return node.offsetParent !== null; });
  }

  function focusableInReceiptInspector() {
    return Array.prototype.slice.call(ui.receiptInspector.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(function (node) { return node.offsetParent !== null; });
  }

  function handleEvidenceKeydown(event) {
    if (!ui.evidence.classList.contains('is-open')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeEvidence(true);
      return;
    }
    if (event.key !== 'Tab') return;
    var focusable = focusableInEvidence();
    if (!focusable.length) {
      event.preventDefault();
      ui.evidence.focus();
      return;
    }
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function handleReceiptInspectorKeydown(event) {
    if (!ui.receiptInspector.classList.contains('is-open')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeReceiptInspector(true);
      return;
    }
    if (event.key !== 'Tab') return;
    var focusable = focusableInReceiptInspector();
    if (!focusable.length) {
      event.preventDefault();
      ui.receiptInspector.focus();
      return;
    }
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function handleViewportChange() {
    if (desktopMedia.matches) {
      closeEvidence(false);
      closeReceiptInspector(false);
    }
  }

  function updateLocalizedAttributes() {
    var current = lang();
    if (ui.search) ui.search.placeholder = ui.search.getAttribute('data-placeholder-' + current) || '';
    Array.prototype.forEach.call(document.querySelectorAll('[data-label-en][data-label-zh]'), function (node) {
      var label = node.getAttribute('data-label-' + current);
      if (label) node.setAttribute('aria-label', label);
    });
    if (state.payload && company()) {
      renderTopicOptions(orderedFindings(company()));
      renderDisclosureControls(company());
      renderDisclosureFeed(company());
      renderRedlines(company());
      renderTimeline(company());
      renderCompareControls(company());
      renderCompare(company());
      renderRunMeta();
      renderCurrentEvidence();
      renderReceipt();
      renderReceiptInspector();
    }
  }

  function bindEvents() {
    // Delegated so the three runtime states can replace the gate's markup
    // without re-binding, the way the receipt pane's data-receipt-action works.
    ui.gate.addEventListener('click', function (event) {
      var trigger = event.target.closest('[data-gate-action]');
      if (!trigger) return;
      var action = trigger.getAttribute('data-gate-action');
      if (action === 'plans') openPlans();
      else if (action === 'signin') openSignin();
      else if (action === 'retry') loadData();
    });

    ui.workspace.addEventListener('click', function (event) {
      var destination = event.target.closest('[data-go-tab]');
      if (destination) {
        setTab(destination.getAttribute('data-go-tab'), false);
        var activeTab = document.querySelector('.ff-tab.is-active');
        if (activeTab) activeTab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        return;
      }
      var primary = event.target.closest('[data-open-primary-finding]');
      if (!primary || !state.payload) return;
      var findings = orderedFindings(company());
      if (!findings.length) {
        setTab('trace', false);
        return;
      }
      state.findingId = String(findings[0].id);
      state.priority = 'all';
      state.topic = 'all';
      state.evidenceKind = 'finding';
      setTab('radar', false);
      renderTopicOptions(findings);
      renderFindings();
      renderCurrentEvidence();
      if (desktopMedia.matches) {
        var selected = selectedFindingButton();
        if (selected) selected.focus({ preventScroll: true });
      } else {
        openEvidence();
      }
    });

    ui.tabs.forEach(function (button, index) {
      button.addEventListener('click', function () { setTab(button.getAttribute('data-tab'), false); });
      button.addEventListener('keydown', function (event) {
        var next = index;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % ui.tabs.length;
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + ui.tabs.length) % ui.tabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = ui.tabs.length - 1;
        else return;
        event.preventDefault();
        ui.tabs[next].focus();
        setTab(ui.tabs[next].getAttribute('data-tab'), false);
      });
    });

    ui.sourceTabs.forEach(function (button, index) {
      button.addEventListener('click', function () {
        setSourceMode(button.getAttribute('data-source-mode'), false);
        updateViewStatus();
      });
      button.addEventListener('keydown', function (event) {
        var next = index;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % ui.sourceTabs.length;
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + ui.sourceTabs.length) % ui.sourceTabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = ui.sourceTabs.length - 1;
        else return;
        event.preventDefault();
        ui.sourceTabs[next].focus();
        setSourceMode(ui.sourceTabs[next].getAttribute('data-source-mode'), false);
        updateViewStatus();
      });
    });

    ui.priorityFilters.addEventListener('click', function (event) {
      var button = event.target.closest('[data-priority]');
      if (!button || !state.payload) return;
      state.priority = button.getAttribute('data-priority');
      renderFindings();
      updateViewStatus();
    });

    ui.topic.addEventListener('change', function () {
      state.topic = ui.topic.value;
      renderFindings();
    });

    ui.findings.addEventListener('click', function (event) {
      var button = event.target.closest('[data-finding-id]');
      if (!button) return;
      state.findingId = button.getAttribute('data-finding-id');
      state.evidenceKind = 'finding';
      renderFindings();
      renderCurrentEvidence();
      openEvidence();
    });

    ui.disclosureSection.addEventListener('change', function () {
      state.disclosureSection = ui.disclosureSection.value || 'all';
      renderDisclosureFeed(company());
      renderRedlines(company());
      updateViewStatus();
    });

    ui.disclosureFeed.addEventListener('click', function (event) {
      var button = event.target.closest('[data-disclosure-finding-id]');
      if (!button) return;
      state.disclosureFindingId = button.getAttribute('data-disclosure-finding-id');
      state.evidenceKind = 'disclosure-finding';
      renderDisclosureFeed(company());
      renderCurrentEvidence();
      openEvidence();
    });

    ui.redlineList.addEventListener('click', function (event) {
      var button = event.target.closest('[data-redline-id]');
      if (!button) return;
      state.redlineId = button.getAttribute('data-redline-id');
      state.evidenceKind = 'redline';
      renderRedlines(company());
      renderCurrentEvidence();
      openEvidence();
    });

    ui.trace.addEventListener('click', function (event) {
      var button = event.target.closest('[data-open-finding]');
      if (!button) return;
      state.findingId = button.getAttribute('data-open-finding');
      state.priority = 'all';
      state.topic = 'all';
      state.evidenceKind = 'finding';
      setTab('radar', false);
      renderTopicOptions(orderedFindings(company()));
      renderFindings();
      renderCurrentEvidence();
      if (desktopMedia.matches) {
        var target = selectedFindingButton();
        if (target) target.focus({ preventScroll: false });
      } else {
        openEvidence();
      }
    });

    ui.receipt.addEventListener('click', function (event) {
      var root = event.target.closest('[data-root-cell-id]');
      if (root) {
        requestReceiptRoot(root.getAttribute('data-root-cell-id'), root);
        return;
      }
      var action = event.target.closest('[data-receipt-action]');
      if (action) {
        var name = action.getAttribute('data-receipt-action');
        if (name === 'retry') ensureReceiptForCompany();
        else if (name === 'next') receiptPageNext();
        else if (name === 'previous') receiptPagePrevious();
      }
    });

    ui.receiptInspectorBody.addEventListener('click', function (event) {
      if (!event.target.closest('[data-receipt-detail-retry]') || !state.receipt.rootCellId) return;
      requestReceiptRoot(state.receipt.rootCellId, state.receipt.lastFocus);
    });

    ui.currentPeriod.addEventListener('change', function () {
      state.currentPeriod = Number(ui.currentPeriod.value) || 0;
      renderCompare(company());
    });
    ui.priorPeriod.addEventListener('change', function () {
      state.priorPeriod = Number(ui.priorPeriod.value) || 0;
      renderCompare(company());
    });

    ui.search.addEventListener('focus', function () { if (state.payload) searchCompanies(ui.search.value); });
    ui.search.addEventListener('input', function () {
      ui.searchClear.hidden = !ui.search.value;
      searchCompanies(ui.search.value);
    });
    ui.search.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        if (ui.companyOptions.hidden) searchCompanies(ui.search.value);
        else moveSearchIndex(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        if (ui.companyOptions.hidden) searchCompanies(ui.search.value);
        else moveSearchIndex(-1);
      } else if (event.key === 'Enter' && !ui.companyOptions.hidden && state.searchIndex >= 0) {
        event.preventDefault();
        setCompany(state.searchMatches[state.searchIndex].key, true);
      } else if (event.key === 'Escape') {
        closeSearch();
        ui.search.value = state.symbol;
        ui.searchClear.hidden = false;
      }
    });

    ui.companyOptions.addEventListener('mousedown', function (event) { event.preventDefault(); });
    ui.companyOptions.addEventListener('click', function (event) {
      var option = event.target.closest('[data-symbol]');
      if (option) setCompany(option.getAttribute('data-symbol'), true);
    });
    ui.searchClear.addEventListener('click', function () {
      ui.search.value = '';
      ui.searchClear.hidden = true;
      ui.search.focus();
      searchCompanies('');
    });

    document.addEventListener('click', function (event) {
      if (!event.target.closest('.ff-combobox-wrap')) closeSearch();
    });
    document.addEventListener('langchange', updateLocalizedAttributes);

    ui.notice.addEventListener('click', function (event) {
      if (event.target.closest('#ff-retry')) loadData();
    });
    ui.evidenceClose.addEventListener('click', function () { closeEvidence(true); });
    ui.receiptInspectorClose.addEventListener('click', function () { closeReceiptInspector(true); });
    ui.scrim.addEventListener('click', function () {
      if (ui.receiptInspector.classList.contains('is-open')) closeReceiptInspector(true);
      else closeEvidence(true);
    });
    ui.evidence.addEventListener('keydown', handleEvidenceKeydown);
    ui.receiptInspector.addEventListener('keydown', handleReceiptInspectorKeydown);

    if (desktopMedia.addEventListener) desktopMedia.addEventListener('change', handleViewportChange);
    else desktopMedia.addListener(handleViewportChange);

    window.addEventListener('popstate', function () {
      if (!state.payload) return;
      var next = resolveSymbol(requestedSymbol());
      if (next) setCompany(next, false);
    });
  }

  function init() {
    cacheUi();
    bindEvents();
    updateLocalizedAttributes();
    // tier_preview.js resolves the visitor's tier from the session cookie before
    // any network call and stamps it on <html>; both scripts are deferred, so it
    // has already run. Showing the preview here rather than after the 401 is
    // what stops a stranger meeting a loading skeleton that resolves into a
    // wall. The fetch below remains the authority and corrects this if wrong.
    if (document.documentElement.getAttribute('data-access-tier') === 'anon') setAccess('signin');
    if (!IS_LOOPBACK) {
      var bindAuth = function () {
        if (window.MDXAuth && window.MDXAuth.onChange) {
          window.MDXAuth.onChange(function () {
            if (!state.payload) loadData();
          });
        }
      };
      if (window.MDXAuth) bindAuth();
      else window.addEventListener('load', bindAuth, { once: true });
    }
    loadData();
  }

  // A deliberately opt-in pure-function seam for the dependency-free Node
  // contract suite. Production never sets this sentinel and receives no test
  // surface; the browser runtime still consumes the exact same validators.
  if (window.__FF_RECEIPT_CONTRACT_TEST__ === true) {
    window.__FF_RECEIPT_CONTRACT_TEST__ = Object.freeze({
      normalizedCik: normalizedCik,
      checkedLatestReceipt: checkedLatestReceipt,
      checkedReceiptRoot: checkedReceiptRoot,
      checkedReceiptPagePayload: checkedReceiptPagePayload,
      checkedReceiptDetailPayload: checkedReceiptDetailPayload
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
}());

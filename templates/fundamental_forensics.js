(function () {
  'use strict';

  // Production state crosses only the authenticated API. Localhost reads the
  // ignored builder artifact so browser QA never needs a live account or bucket.
  var IS_LOOPBACK = /^(localhost|127(?:\.\d{1,3}){3}|\[?::1\]?)$/i.test(window.location.hostname);
  var DATA_URL = IS_LOOPBACK
    ? '/data/fundamental_forensics/private/state.json.gz'
    : '/api/forensics/state';
  var DESKTOP_QUERY = '(min-width: 1100px)';
  var state = {
    payload: null,
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
    unknownRequestedSymbol: ''
  };

  var ui = {};
  var desktopMedia = window.matchMedia(DESKTOP_QUERY);

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
    preamble: ['Filing preamble', '申报前言'],
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
    ui.evidence = byId('ff-evidence');
    ui.evidenceTitle = byId('ff-evidence-title');
    ui.evidenceBody = byId('ff-evidence-body');
    ui.evidenceClose = byId('ff-evidence-close');
    ui.scrim = byId('ff-scrim');
    ui.siteNav = document.querySelector('.site-nav');
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
      'filing_index': '申报索引',
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
    if (priority === 'high') return { icon: '!', en: 'Review now', zh: '立即审阅' };
    return { icon: '○', en: 'Watch', zh: '持续关注' };
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

  function showLoadError(error) {
    var detail = error && error.message ? error.message : 'Unknown response error';
    ui.notice.hidden = false;
    ui.notice.className = 'ff-data-notice is-error';
    ui.notice.innerHTML = '<span>' + pair('Filing data could not be loaded. ' + detail, '无法载入财报数据。' + detail) + '</span>' +
      '<button class="ff-retry" id="ff-retry" type="button">' + pair('Retry', '重试') + '</button>';
    ui.viewStatus.innerHTML = pair('Data unavailable', '数据不可用');
    var empty = emptyState('Data unavailable', '数据不可用',
      'Retry the data request. The interface will not infer results without its source state.',
      '请重试数据请求；缺少来源状态时，界面不会推断结果。', '×');
    ui.findings.innerHTML = empty;
    ui.statements.innerHTML = empty;
    ui.disclosureFeed.innerHTML = empty;
    ui.redlineList.innerHTML = empty;
    ui.timeline.innerHTML = empty;
    ui.compareGrid.innerHTML = empty;
    ui.trace.innerHTML = empty;
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

    withAuth({ Accept: 'application/gzip' })
      .then(function (headers) {
        return fetch(DATA_URL, {
          headers: headers,
          credentials: 'same-origin',
          cache: 'no-store'
        });
      })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
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
    var identityDetailZh = [identityCore, target.latest_filed ? '申报于 ' + formatDate(target.latest_filed) : ''].filter(Boolean).join(' · ');
    ui.companyIdentity.innerHTML = '<div class="ff-company-mark" aria-hidden="true">' + esc(String(symbol).slice(0, 5)) + '</div>' +
      '<div><div class="ff-company-name">' + esc(target.name || symbol) + '</div>' +
      '<div class="ff-company-detail">' + pair(identityDetailEn || '—', identityDetailZh || '—') + '</div></div>';

    var findings = orderedFindings(target);
    var highCount = findings.filter(function (item) { return item.priority === 'high'; }).length;
    var watchCount = findings.filter(function (item) { return item.priority === 'watch'; }).length;
    var action = target.action || {};
    var actionKey = action.key || (highCount ? 'high' : watchCount ? 'watch' : 'covered');
    var actionEn = action.en || (highCount ? 'Review now' : watchCount ? 'Worth a look' : 'No review needed in covered checks');
    var actionZh = action.zh || (highCount ? '立即审阅' : watchCount ? '值得查看' : '已覆盖检查暂不需审阅');
    var actionIcon = actionKey === 'high' ? '!' : actionKey === 'watch' ? '○' : actionKey === 'limited' ? '?' : '✓';
    ui.companyAction.setAttribute('data-action', actionKey);
    ui.companyAction.innerHTML = '<span class="ff-action-glyph" aria-hidden="true">' + actionIcon + '</span>' +
      '<span class="ff-action-copy">' + pair(actionEn, actionZh) + '</span>';

    renderNotice(target);
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

  function renderNoCompanies() {
    ui.companyIdentity.innerHTML = '<div class="ff-company-mark" aria-hidden="true">—</div><div><div class="ff-company-name">' +
      pair('No companies available', '暂无公司') + '</div><div class="ff-company-detail">—</div></div>';
    ui.companyAction.removeAttribute('data-action');
    ui.companyAction.innerHTML = '<span class="ff-action-glyph" aria-hidden="true">×</span>' + pair('No coverage', '暂无覆盖');
    var empty = emptyState('No coverage in this dataset', '此数据集暂无覆盖',
      'The current state file contains no company records.', '当前状态文件不含公司记录。', '—');
    ui.findings.innerHTML = empty;
    ui.statements.innerHTML = empty;
    ui.disclosureFeed.innerHTML = empty;
    ui.redlineList.innerHTML = empty;
    ui.timeline.innerHTML = empty;
    ui.compareGrid.innerHTML = empty;
    ui.trace.innerHTML = empty;
    ui.viewStatus.innerHTML = pair('0 companies', '0 家公司');
  }

  function renderNotice(target) {
    var coverage = target.coverage || {};
    var source = state.payload.source || {};
    var pct = numberValue(coverage.metrics_pct);
    var limitationsEn = Array.isArray(source.limitations_en) ? source.limitations_en : [];
    var limitationsZh = Array.isArray(source.limitations_zh) ? source.limitations_zh : [];
    var notices = [];

    if (state.unknownRequestedSymbol) {
      notices.push(pair(state.unknownRequestedSymbol + ' is not covered; showing ' + state.symbol + '.',
        '尚未覆盖 ' + state.unknownRequestedSymbol + '；现显示 ' + state.symbol + '。'));
    }
    if (pct != null && (pct <= 1 ? pct < 0.999 : pct < 99.9)) {
      notices.push(pair('Metric coverage is ' + formatPercent(pct) + '; missing facts remain missing and are not imputed.',
        '指标覆盖率为 ' + formatPercent(pct) + '；缺失事实保持缺失，不进行填补。'));
    }
    if (limitationsEn.length || limitationsZh.length) {
      notices.push(pair(limitationsEn[0] || limitationsZh[0], limitationsZh[0] || limitationsEn[0]));
    }
    if (!notices.length) {
      ui.notice.hidden = true;
      ui.notice.innerHTML = '';
      return;
    }
    ui.notice.className = 'ff-data-notice';
    ui.notice.hidden = false;
    ui.notice.innerHTML = notices.join('<span aria-hidden="true"> · </span>');
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

    ui.filterSummary.innerHTML = pair(visible.length + ' of ' + all.length + ' findings',
      '显示 ' + visible.length + ' / ' + all.length + ' 项发现');

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
        pair('Open evidence', '查看证据') + '</span></button></div>';
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
      '提供的财报不是同一申报表格，因此无法直接比较。'
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
        filtered ? '请选择其他章节查看已有观察结果。' : '这不代表每项披露都没有变化；请查看申报轨迹和来源覆盖范围。', filtered ? '↺' : '✓'
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
        'No filing trail supplied', '未提供申报轨迹',
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
      return '<article class="ff-timeline-card"><span class="ff-timeline-node" aria-hidden="true">' + (index + 1) + '</span><p class="ff-kicker">' + role + '</p><h3>' + esc(form) + '</h3><dl><div><dt>' + pair('Filed', '申报日') + '</dt><dd>' + esc(documentDate(document)) + '</dd></div><div><dt>' + pair('Report date', '报告期') + '</dt><dd>' + esc(reportDate) + '</dd></div><div><dt>' + pair('Accession', '文件编号') + '</dt><dd class="ff-accession">' + esc(documentAccession(document)) + '</dd></div></dl>' + sourceAction + '</article>';
    }).join('') + '</div>';
  }

  function renderStatements(target) {
    var periods = Array.isArray(target.periods) ? target.periods : [];
    if (!periods.length) {
      ui.statements.innerHTML = emptyState('No statement periods available', '暂无财务报表期间',
        'The source state has no normalized periods for this company.', '来源状态中没有该公司的标准化期间。', '—');
      return;
    }
    var header = '<th>' + pair('Period / filed', '期间 / 申报日') + '</th>' + METRICS.map(function (metric) {
      return '<th>' + pair(metric.en, metric.zh) + '</th>';
    }).join('');
    var rows = periods.map(function (period) {
      var first = '<td data-label-en="Period / filed" data-label-zh="期间 / 申报日">' + esc(periodLabel(period)) +
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
        pair('Inspect', '检查') + '</button></div><code class="ff-proof-code">' +
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
      pair('Disclosure comparison', '披露对比') + '</p><h3>' + pair('Accession-aware source pair', '基于文件编号的来源组合') + '</h3><p>' + pair(
        disclosureFindingItems.length + ' comparison outcomes · ' + disclosureRedlineItems.length + ' observable text changes',
        disclosureFindingItems.length + ' 个对比结果 · ' + disclosureRedlineItems.length + ' 条可观察文本变化'
      ) + '</p><div class="ff-trace-receipts">' + (disclosureLinks || '<span class="ff-trace-receipt">' + pair('No filing link supplied', '未提供财报链接') + '</span>') + '</div></section>' :
      '<section class="ff-trace-card"><p class="ff-kicker">' + pair('Disclosure comparison', '披露对比') + '</p><h3>' + pair('Not available yet', '暂不可用') + '</h3><p>' + pair(
        'A filing pair is required before disclosure redlines can be shown.',
        '在显示披露逐字对照前，需要一组财报文件。'
      ) + '</p></section>';

    ui.trace.innerHTML = '<div class="ff-trace-grid"><div><section class="ff-trace-card"><p class="ff-kicker">' +
      pair('Dataset', '数据集') + '</p><h3>' + pair(sourceEn, sourceZh) + '</h3><p>' + pair(basisEn, basisZh) + '</p>' +
      '<div class="ff-coverage-grid"><div class="ff-coverage-stat"><small>' + pair('Periods', '期间数') + '</small><strong>' +
      esc(coverage.periods == null ? (Array.isArray(target.periods) ? target.periods.length : 0) : coverage.periods) + '</strong></div>' +
      '<div class="ff-coverage-stat"><small>' + pair('Metric coverage', '指标覆盖率') + '</small><strong>' +
      esc(coverage.metrics_pct == null ? '—' : formatPercent(coverage.metrics_pct)) + '</strong></div>' +
      '<div class="ff-coverage-stat"><small>' + pair('Findings', '发现数') + '</small><strong>' + findings.length + '</strong></div>' +
      '<div class="ff-coverage-stat"><small>' + pair('Source links', '来源链接') + '</small><strong>' + evidenceCount + '</strong></div></div>' +
      (sourceUrl ? '<a class="ff-source-link" href="' + esc(sourceUrl) + '" target="_blank" rel="noopener noreferrer"><span aria-hidden="true">↗</span>' +
        pair('Open company facts source', '打开公司事实来源') + '</a>' : '') +
      '<div class="ff-proof-section"><h3>' + pair('Known limitations', '已知局限') + '</h3><ul class="ff-source-limitations">' + limitations + '</ul></div></section>' +
      '<section class="ff-trace-card"><p class="ff-kicker">' + pair('Detector registry', '检测器清单') + '</p><h3>' +
      pair('Rules in this build', '当前版本规则') + '</h3><ul class="ff-detector-list">' + detectorHtml + '</ul></section>' + disclosureTrace + '</div>' +
      '<div class="ff-trace-findings">' + traceFindings + '</div></div>';
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
      cross_form_kpi_cadence_is_not_comparable: ['Different reporting forms may disclose a metric on different schedules.', '不同申报表格可能按不同节奏披露指标。']
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
    var redline = tab === 'redlines';
    ui.evidenceTitle.innerHTML = redline ? pair('Select a source redline', '选择来源逐字对照') : pair('Select a filing change', '选择披露变化');
    ui.evidenceBody.innerHTML = '<div class="ff-evidence-empty"><span class="ff-empty-mark" aria-hidden="true">◇</span><p>' +
      (redline ? pair(
        'Choose a matched text change to read the prior and current SEC excerpts.',
        '选择一条匹配的文本变化，以阅读前后两段 SEC 摘录。'
      ) : pair(
        'Choose an observed filing change to see the source excerpts and its reading boundaries.',
        '选择一项观察到的财报变化，以查看来源摘录和阅读边界。'
      )) + '</p></div>';
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
      ui.evidenceTitle.innerHTML = pair('Select a finding', '选择一项发现');
      ui.evidenceBody.innerHTML = '<div class="ff-evidence-empty"><span class="ff-empty-mark" aria-hidden="true">↳</span><p>' +
      pair('Choose a result to inspect its values, formula, threshold, and SEC source links.', '选择一项结果，查看数值、公式、阈值和 SEC 来源链接。') + '</p></div>';
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
      priority.icon + '</span>' + pair(priority.en, priority.zh) + '</div><p class="ff-proof-summary">' +
      fieldPair(finding, 'summary', 'No summary supplied.') + '</p><div class="ff-proof-basis">' +
      '<span><b>' + pair('Normalized inputs', '标准化输入') + '</b>' + esc([finding.period_current, finding.period_prior].filter(Boolean).join(' / ') || '—') + '</span>' +
      '<span><b>' + pair('Calculated', '规则计算') + '</b>' + pair('Deterministic rule', '确定性规则') + '</span>' +
      '<span><b>' + pair('Limits', '局限') + '</b>' + limitationCount + '</span></div>' +
      '<section class="ff-proof-section"><h3>' + pair('What changed', '发生了什么变化') + '</h3><div class="ff-value-grid">' + valueRows + '</div></section>' +
      '<section class="ff-proof-section"><h3>' + pair('Formula and test', '公式与检验') + '</h3><code class="ff-proof-code">' +
      fieldPair(finding, 'formula', 'Formula not supplied') + '</code><p class="ff-threshold"><strong>' + pair('Threshold: ', '阈值：') + '</strong>' +
      fieldPair(finding, 'threshold', 'Threshold not supplied') + '</p></section>' +
      '<section class="ff-proof-section"><h3>' + pair('SEC source links', 'SEC 来源链接') + '</h3><ol class="ff-receipts">' + receiptHtml + '</ol></section>' +
      '<section class="ff-proof-section"><h3>' + pair('Limitations', '局限') + '</h3><ul class="ff-limitations">' + limitationHtml + '</ul></section>';
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
    if (previousTab !== tab) closeEvidence(false);
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
      ui.viewStatus.innerHTML = pair(findings.length + ' findings · filed ' + formatDate(target.latest_filed),
        findings.length + ' 项发现 · 申报于 ' + formatDate(target.latest_filed));
    } else if (state.tab === 'statements') {
      ui.viewStatus.innerHTML = pair(periods.length + ' normalized periods', periods.length + ' 个标准化期间');
    } else if (state.tab === 'compare') {
      ui.viewStatus.innerHTML = pair('Neutral period bridge', '中性期间变化桥');
    } else if (state.tab === 'disclosures') {
      var disclosureCount = disclosureFindingsForView(target).length;
      ui.viewStatus.innerHTML = pair(
        disclosureCount + ' observed review prompt' + (disclosureCount === 1 ? '' : 's'),
        disclosureCount + ' 项观察到的复核提示'
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

  function handleViewportChange() {
    if (desktopMedia.matches) closeEvidence(false);
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
    }
  }

  function bindEvents() {
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
    ui.scrim.addEventListener('click', function () { closeEvidence(true); });
    ui.evidence.addEventListener('keydown', handleEvidenceKeydown);

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

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
}());

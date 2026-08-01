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
    material_weakness: ['Material weakness', '重大缺陷'],
    risk_factors: ['Risk factors', '风险因素'],
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
    return String(value[wanted] || value.en || value.zh || value.label || value.name || '');
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

  function setLoading() {
    ui.viewStatus.innerHTML = pair('Loading filing data…', '正在载入财报数据…');
    var loading = '<div class="ff-loading" role="status"><span class="ff-loading-dot" aria-hidden="true"></span>' +
      pair('Loading filing review data…', '正在载入财报审阅数据…') + '</div>';
    ui.findings.innerHTML = loading;
    ui.statements.innerHTML = loading;
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
    renderCompareControls(target);
    renderCompare(target);
    renderTrace(target);
    renderEvidence(selectedFinding());
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
        renderEvidence(null);
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
    renderEvidence(selectedFinding());
  }

  function emptyState(titleEn, titleZh, copyEn, copyZh, mark) {
    return '<div class="ff-empty-state"><div><span class="ff-empty-mark" aria-hidden="true">' + esc(mark || '—') + '</span>' +
      '<h3>' + pair(titleEn, titleZh) + '</h3><p>' + pair(copyEn, copyZh) + '</p></div></div>';
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
      pair('Rules in this build', '当前版本规则') + '</h3><ul class="ff-detector-list">' + detectorHtml + '</ul></section></div>' +
      '<div class="ff-trace-findings">' + traceFindings + '</div></div>';
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
    var allowed = ['radar', 'statements', 'compare', 'trace'];
    if (allowed.indexOf(tab) === -1) tab = 'radar';
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
    if (tab !== 'radar') closeEvidence(false);
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
    if (desktopMedia.matches || !selectedFinding()) return;
    // renderFindings replaces the clicked button before the sheet opens. Resolve
    // its new DOM counterpart so closing the modal returns keyboard focus to the
    // finding that launched it instead of leaving focus on <body> or a hidden tab.
    state.lastFocus = selectedFindingButton() || document.activeElement;
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
      renderCompareControls(company());
      renderCompare(company());
      renderRunMeta();
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
      renderFindings();
      renderEvidence(selectedFinding());
      openEvidence();
    });

    ui.trace.addEventListener('click', function (event) {
      var button = event.target.closest('[data-open-finding]');
      if (!button) return;
      state.findingId = button.getAttribute('data-open-finding');
      state.priority = 'all';
      state.topic = 'all';
      setTab('radar', false);
      renderTopicOptions(orderedFindings(company()));
      renderFindings();
      renderEvidence(selectedFinding());
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

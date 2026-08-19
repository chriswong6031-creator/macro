/* Mastermind Company Intelligence dossier surface.
 *
 * Browser-visible data is a bounded projection from the source-backed public
 * Company Intelligence plane. It is context only: this module never computes
 * a score, recommendation, target, rank, or trading action.
 *
 * Fetch order (frozen law):
 *   1. GET /api/event-workspace/{ticker}  — current-event authority (v2)
 *      200 + valid schema                 → renderV2; v1 never requested
 *      404                                → fetchV1 (genuine no-coverage)
 *      503 / 429 / error / invalid schema → showV2Unavailable; v1 NEVER fallback
 *   2. GET /api/company-intelligence/{ticker}  — legacy v1 teaser (404 fallback only)
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-company-intelligence]');
  if (!root) return;

  var ticker = String(root.getAttribute('data-ticker') || '').trim().toUpperCase();
  if (ticker.indexOf('..') !== -1 || !/^[A-Z0-9](?:[A-Z0-9.\-]{0,14}[A-Z0-9])?$/.test(ticker)) return;

  var state = document.getElementById('ci-state');
  var loading = document.getElementById('ci-loading');
  var empty = document.getElementById('ci-empty');
  var emptyTitle = document.getElementById('ci-empty-title');
  var emptyCopy = document.getElementById('ci-empty-copy');
  var content = document.getElementById('ci-content');
  var period = document.getElementById('ci-period');
  var v2Host = document.getElementById('ci-v2-host');
  var summary = document.getElementById('ci-summary');
  var strength = document.getElementById('ci-strength');
  var pressure = document.getElementById('ci-pressure');
  var tags = document.getElementById('ci-tags');
  var metrics = document.getElementById('ci-metrics');
  var nextCopy = document.getElementById('ci-next-copy');
  var transcript = document.getElementById('ci-transcript');
  var earningsRecord = document.getElementById('ci-earnings-record');
  var history = document.getElementById('ci-history');
  var historyTabs = document.getElementById('ci-history-tabs');
  var receipt = document.getElementById('ci-receipt');
  var footNote = document.getElementById('ci-foot-note');
  var announcer = document.getElementById('ci-announcer');
  var terminalUpgrade = document.getElementById('ci-terminal-upgrade');
  var terminalUpgradeEmpty = document.getElementById('ci-terminal-upgrade-empty');
  var events = [];
  var payload = null;
  var routeCatalog = null;
  var selectedIndex = 0;

  var topicZh = {
    strong_demand: '需求强劲', supply_constraints: '供应受限', ai_everywhere: '人工智能应用',
    ai_strategy: '人工智能战略', ai_hardware: '人工智能硬件', memory_costs: '存储成本',
    rising_memory_costs: '存储成本上升', fx_headwinds: '汇率压力', record_quarter: '季度新高',
    strong_revenue_growth: '营收强劲增长', revenue_growth: '营收增长', margin_expansion: '利润率扩张',
    margin_pressure: '利润率压力', pricing_power: '定价能力', cost_reduction: '成本削减',
    capital_return: '资本回报', consumer_electronics: '消费电子', semiconductors: '半导体',
    cloud_services: '云服务', software_as_a_service: '软件服务', digital_advertising: '数字广告',
    streaming_services: '流媒体服务', digital_payments: '数字支付', international_growth: '海外增长',
    china_growth: '中国市场增长', india_expansion: '印度市场扩张', guidance_raise: '上调指引',
    guidance_cut: '下调指引', regulatory_risk: '监管风险', product_launch: '产品发布'
  };

  /* v2 closed map — no LLM, no dynamic lookup */
  var V2_ZH = {
    'Reported': '已公布',
    'Guidance': '指引',
    'Watch': '关注',
    'Coverage': '覆盖',
    'Verified event': '已核实事件',
    'Revenue': '营收',
    'Q4 revenue growth': '第四季度营收增长',
    'Supply constraint': '供应受限',
    'Memory cost/flood': '存储成本',
    'FX headwind': '汇率压力',
    'Consensus': '共识',
    'Unlicensed': '未授权',
    'unlicensed': '未授权',
    'Market reaction': '市场反应',
    'Not joined': '未接入',
    'not_joined': '未接入',
    'not joined': '未接入',
    'Analyst questions': '分析师提问',
    'Unavailable / unstructured': '暂无结构化计数',
    'unstructured': '暂无结构化计数',
    'Open full event in Terminal': '在终端打开完整事件',
    'Retry': '重试',
    'Verified event temporarily unavailable': '已核实事件暂时不可用'
  };

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function textNode(tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = value == null ? '' : String(value);
    return node;
  }

  function pair(parent, en, zh) {
    var enNode = textNode('span', 'l-en', en);
    var zhNode = textNode('span', 'l-zh', zh || en);
    parent.appendChild(enNode);
    parent.appendChild(zhNode);
  }

  function setPair(node, en, zh) {
    clear(node);
    pair(node, en, zh);
  }

  function setState(kind, en, zh) {
    state.className = 'ci-state ' + kind;
    setPair(state, en, zh);
  }

  function finite(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function oneDecimal(value) {
    if (!finite(value)) return '—';
    var rounded = Math.round(value * 10) / 10;
    return (Math.abs(rounded % 1) < 0.001 ? String(Math.round(rounded)) : rounded.toFixed(1));
  }

  function signed(value, suffix) {
    if (!finite(value)) return '';
    if (Math.abs(value) < 0.05) return '0' + suffix;
    return (value > 0 ? '+' : '−') + oneDecimal(Math.abs(value)) + suffix;
  }

  function eventLabel(event) {
    var year = Number(event && event.fiscal_year);
    var quarter = Number(event && event.fiscal_quarter);
    if (!Number.isInteger(year) || !Number.isInteger(quarter)) return ticker;
    return 'FY' + year + ' Q' + quarter;
  }

  function eventLabelZh(event) {
    var year = Number(event && event.fiscal_year);
    var quarter = Number(event && event.fiscal_quarter);
    if (!Number.isInteger(year) || !Number.isInteger(quarter)) return ticker;
    return year + '财年 第' + quarter + '季度';
  }

  function eventPeriodKey(event) {
    var year = Number(event && event.fiscal_year);
    var quarter = Number(event && event.fiscal_quarter);
    if (!Number.isInteger(year) || !Number.isInteger(quarter)) return '';
    return String(year) + 'Q' + String(quarter);
  }

  function eventIdentifiers(event) {
    var identifiers = [];
    ['event_id', 'transcript_id'].forEach(function (key) {
      var value = String(event && event[key] || '').trim();
      if (value) identifiers.push(value);
    });
    var periodKey = eventPeriodKey(event);
    if (periodKey) identifiers.push(periodKey);
    return identifiers;
  }

  function displayDate(value, locale) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return '';
    var parsed = new Date(String(value) + 'T12:00:00Z');
    if (!Number.isFinite(parsed.getTime())) return '';
    try {
      return new Intl.DateTimeFormat(locale, {year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC'}).format(parsed);
    } catch (ignore) {
      return String(value);
    }
  }

  function prettyTopic(value) {
    return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }

  function renderTags(event) {
    clear(tags);
    var selected = Array.isArray(event.tags) ? event.tags.slice(0, 5) : [];
    selected.forEach(function (topic) {
      var chip = document.createElement('span');
      chip.className = 'ci-tag';
      pair(chip, prettyTopic(topic), topicZh[topic] || prettyTopic(topic));
      tags.appendChild(chip);
    });
    tags.hidden = selected.length === 0;
  }

  function metricCard(definition, event) {
    var value = event.metrics && event.metrics[definition.key];
    if (!finite(value)) return null;
    var card = document.createElement('div');
    card.className = 'ci-metric';
    var label = document.createElement('span');
    pair(label, definition.en, definition.zh);
    card.appendChild(label);
    card.appendChild(textNode('strong', '', oneDecimal(value) + definition.suffix));
    var delta = event.previous_event_deltas && event.previous_event_deltas[definition.key];
    var change = document.createElement('small');
    if (finite(delta)) {
      change.className = delta > 0 ? 'up' : (delta < 0 ? 'down' : '');
      var deltaText = signed(delta, definition.deltaSuffix || definition.suffix);
      pair(change, deltaText + ' vs prior call', deltaText + '，较上次电话会');
    } else {
      pair(change, 'Latest record', '最新记录');
    }
    card.appendChild(change);
    var lineage = event.field_lineage && event.field_lineage.metrics && event.field_lineage.metrics[definition.key];
    var source = document.createElement('em');
    if (lineage === 'earnings_history') pair(source, 'Call record', '电话会记录');
    else if (lineage === 'score_overlay') pair(source, 'Model overlay', '模型叠加');
    else pair(source, 'Record field', '记录字段');
    card.appendChild(source);
    return card;
  }

  function renderMetrics(event) {
    clear(metrics);
    [
      {key: 'revenue_growth_pct', en: 'Revenue growth', zh: '营收增速', suffix: '%', deltaSuffix: 'pp'},
      {key: 'eps_growth_pct', en: 'EPS growth', zh: '每股收益增速', suffix: '%', deltaSuffix: 'pp'},
      {key: 'gross_margin_pct', en: 'Gross margin', zh: '毛利率', suffix: '%', deltaSuffix: 'pp'},
      {key: 'questions_count', en: 'Analyst questions', zh: '分析师提问数', suffix: '', deltaSuffix: ''}
    ].forEach(function (definition) {
      var card = metricCard(definition, event);
      if (card) metrics.appendChild(card);
    });
    if (!metrics.children.length) {
      var card = document.createElement('div');
      card.className = 'ci-metric';
      card.style.gridColumn = '1 / -1';
      pair(card, 'No comparable metric in this record', '本期记录暂无可比指标');
      metrics.appendChild(card);
    }
  }

  function transcriptUrl(event) {
    var url = new URL('https://app.mastermind-x.com/terminal');
    url.searchParams.set('sym', ticker);
    url.searchParams.set('pane', 'transcripts');
    var periodKey = eventPeriodKey(event);
    if (periodKey) url.searchParams.set('tx', periodKey);
    url.searchParams.set('from', 'company-intelligence');
    return url.toString();
  }

  function safeWireHref(value) {
    var href = String(value || '').trim();
    return /^[a-z0-9][a-z0-9-]*\.html$/.test(href) ? href : '';
  }

  function normalizedWireRoute(route) {
    if (typeof route === 'string') {
      route = {href: route};
    }
    if (!route || typeof route !== 'object') return null;
    var href = safeWireHref(route.href);
    return href ? {href: href, period: String(route.period || ''), transcriptId: String(route.transcript_id || '')} : null;
  }

  function wireRouteForEvent(event) {
    var routes = routeCatalog && routeCatalog.routes && routeCatalog.routes[ticker];
    if (!routes) return null;
    /* v1 used a ticker -> {href} shape. Keep it only when it proves the event match. */
    var legacy = normalizedWireRoute(routes);
    if (legacy && !routes.events && !routes.latest) {
      var legacyIdentifiers = eventIdentifiers(event);
      if ((legacy.period && legacy.period === eventPeriodKey(event)) ||
          (legacy.transcriptId && legacyIdentifiers.indexOf(legacy.transcriptId) !== -1)) return legacy;
      return null;
    }

    var eventRoutes = routes.events && typeof routes.events === 'object' ? routes.events : null;
    if (eventRoutes) {
      var identifiers = eventIdentifiers(event);
      for (var i = 0; i < identifiers.length; i += 1) {
        var exact = normalizedWireRoute(eventRoutes[identifiers[i]]);
        if (exact) return exact;
      }
    }
    /* The latest route is only exact when its recorded period/ID agrees. */
    var latest = normalizedWireRoute(routes.latest);
    if (!latest) return null;
    var eventPeriod = eventPeriodKey(event);
    if ((latest.period && latest.period === eventPeriod) ||
        (latest.transcriptId && eventIdentifiers(event).indexOf(latest.transcriptId) !== -1)) return latest;
    return null;
  }

  function updateEarningsRecord(event) {
    if (!earningsRecord) return;
    var route = wireRouteForEvent(event);
    if (route) {
      earningsRecord.href = 'earnings/' + route.href + '?from=company-intelligence&tx=' + encodeURIComponent(eventPeriodKey(event));
      earningsRecord.setAttribute('data-wire-state', 'exact');
      setPair(earningsRecord, 'Open this earnings record', '打开本期财报记录');
      return;
    }
    earningsRecord.href = 'earnings/';
    earningsRecord.setAttribute('data-wire-state', 'archive');
    setPair(earningsRecord, 'Browse earnings archive', '浏览财报档案');
  }

  function renderEvent(event, index) {
    if (!event) return;
    clear(period);
    var strongPeriod = textNode('strong', '', '');
    pair(strongPeriod, eventLabel(event), eventLabelZh(event));
    period.appendChild(strongPeriod);
    var enDate = displayDate(event.call_date, 'en-US');
    var zhDate = displayDate(event.call_date, 'zh-CN');
    if (enDate) {
      var dateNode = textNode('span', '', '');
      pair(dateNode, enDate, zhDate);
      period.appendChild(dateNode);
    }
    var language = textNode('span', 'ci-source-lang', '');
    pair(language, 'Synthesized record · English', '综合记录 · 英文');
    period.appendChild(language);

    var lead = String(event.summary || event.key_quote || '').trim();
    clear(summary);
    if (lead) {
      summary.classList.remove('is-empty');
      summary.setAttribute('lang', 'en');
      summary.textContent = lead;
    } else {
      summary.classList.add('is-empty');
      summary.removeAttribute('lang');
      pair(summary, 'No narrative summary is available for this call.', '本次电话会暂无叙述性摘要。');
    }

    var positive = Array.isArray(event.positive_highlights) && event.positive_highlights.length ? String(event.positive_highlights[0]) : '';
    var negative = Array.isArray(event.negative_highlights) && event.negative_highlights.length ? String(event.negative_highlights[0]) : '';
    if (positive) {
      strength.setAttribute('lang', 'en');
      strength.textContent = positive;
    } else {
      strength.removeAttribute('lang');
      setPair(strength, 'No positive change was isolated in the current record.', '当前记录未单列积极变化。');
    }
    if (negative) {
      pressure.setAttribute('lang', 'en');
      pressure.textContent = negative;
    } else {
      pressure.removeAttribute('lang');
      setPair(pressure, 'No pressure point was isolated in the current record.', '当前记录未单列压力因素。');
    }

    nextCopy.removeAttribute('lang');
    if (negative) {
      setPair(nextCopy,
        'Verify the source wording for the pressure point above, then compare it with the next call.',
        '先在原文中核对上方压力因素的准确措辞，再与下次电话会比较。');
    } else {
      setPair(nextCopy, 'Compare the next call with this baseline and verify any narrative change in the transcript.', '以下次电话会与本期基准对比，并在电话会原文中核对表述变化。');
    }

    renderTags(event);
    renderMetrics(event);
    transcript.href = transcriptUrl(event);
    selectedIndex = index;
    updateEarningsRecord(event);
    Array.prototype.forEach.call(historyTabs.children, function (button, buttonIndex) {
      button.setAttribute('aria-pressed', buttonIndex === index ? 'true' : 'false');
    });
    if (announcer) setPair(announcer, 'Showing ' + eventLabel(event), '正在显示' + eventLabelZh(event));
  }

  function renderHistory(activeIndex) {
    clear(historyTabs);
    events.slice(0, 8).forEach(function (event, index) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'ci-history-tab';
      button.setAttribute('aria-pressed', index === activeIndex ? 'true' : 'false');
      pair(button, eventLabel(event), eventLabelZh(event));
      button.addEventListener('click', function () { renderEvent(event, index); });
      button.addEventListener('keydown', function (eventKey) {
        if (eventKey.key !== 'ArrowRight' && eventKey.key !== 'ArrowLeft') return;
        eventKey.preventDefault();
        var next = eventKey.key === 'ArrowRight' ? index + 1 : index - 1;
        if (next < 0) next = Math.min(events.length, 8) - 1;
        if (next >= Math.min(events.length, 8)) next = 0;
        historyTabs.children[next].focus();
        historyTabs.children[next].click();
      });
      historyTabs.appendChild(button);
    });
    if (history) history.hidden = events.length <= 1;
  }

  function showEmpty(kind, titleEn, titleZh, copyEn, copyZh) {
    loading.hidden = true;
    content.hidden = true;
    empty.hidden = false;
    root.removeAttribute('aria-busy');
    setState(kind, titleEn, titleZh);
    setPair(emptyTitle, titleEn, titleZh);
    setPair(emptyCopy, copyEn, copyZh);
  }

  function generatedLabel(value) {
    var day = String(value || '').slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return '';
    return day;
  }

  function loadRouteCatalog() {
    if (!earningsRecord) return;
    fetch('earnings/route-catalog.json', {
      method: 'GET', credentials: 'same-origin', headers: {'Accept': 'application/json'}
    }).then(function (response) {
      if (!response.ok) return null;
      return response.json();
    }).then(function (catalog) {
      if (!catalog || catalog.schema !== 'earnings.public_wire_routes/v1' || !catalog.routes) return;
      routeCatalog = catalog;
      if (events[selectedIndex]) updateEarningsRecord(events[selectedIndex]);
    }).catch(function () {
      /* The generic archive handoff remains valid when the optional catalog is unavailable. */
    });
  }

  function showPayload(data) {
    payload = data;
    events = Array.isArray(data.history) ? data.history.filter(function (item) { return item && typeof item === 'object'; }) : [];
    if (!events.length && data.latest_event) events = [data.latest_event];
    if (!events.length) {
      showEmpty('unavailable', 'No fresh company event', '暂无新增公司事件',
        'Coverage is active, but no earnings-call source record is available for this ticker yet.',
        '覆盖系统已启用，但该股票暂时没有财报电话会来源记录。');
      return;
    }

    var latest = events[0];
    var incomplete = data.status !== 'ready' || latest.claim_citations_pending === true;
    setState(incomplete ? 'partial' : 'ready',
      incomplete ? 'Wording not yet checked' : 'Checked against the source',
      incomplete ? '措辞尚未核对' : '已核对来源记录');
    loading.hidden = true;
    empty.hidden = true;
    content.hidden = false;
    root.removeAttribute('aria-busy');
    var selected = 0;
    try {
      var requested = new URLSearchParams(window.location.search).get('tx');
      if (requested) {
        var match = events.findIndex(function (event) { return eventIdentifiers(event).indexOf(requested) !== -1; });
        if (match >= 0) selected = match;
      }
    } catch (ignore) {}
    renderHistory(selected);
    renderEvent(events[selected], selected);

    var generated = generatedLabel(data.generated_at);
    clear(receipt);
    pair(receipt, generated ? 'Record updated ' + generated : 'Current record', generated ? '记录更新于 ' + generated : '当前记录');
    clear(footNote);
    var selectedEvent = events[selected] || latest;
    var hasTranscript = Array.isArray(selectedEvent.sources) && selectedEvent.sources.some(function (source) {
      return source && source.kind === 'transcript' && source.status === 'present';
    });
    if (selectedEvent.claim_citations_pending === true) {
      pair(footNote,
        hasTranscript ? 'Transcript linked in Terminal; narrative claims still need line-level verification.' : 'No transcript is linked in this record; narrative claims need source verification.',
        hasTranscript ? '终端已关联电话会原文；叙述性内容仍需逐行核对。' : '本记录尚未关联电话会原文；叙述性内容仍需来源核对。');
    } else {
      pair(footNote, hasTranscript ? 'Transcript linked in Terminal.' : 'Source record available; transcript is not linked.', hasTranscript ? '终端已关联电话会原文。' : '来源记录可用；尚未关联电话会原文。');
    }

    try {
      window.dispatchEvent(new CustomEvent('mmx:company-intelligence-ready', {
        detail: {ticker: ticker, status: data.status, generation_id: data.generation_id}
      }));
    } catch (ignore) {}
  }

  /* ── v2 helpers ── */

  function v2SectionHead(enLabel) {
    var head = document.createElement('div');
    head.className = 'ci-v2-section';
    pair(head, enLabel, V2_ZH[enLabel] || enLabel);
    return head;
  }

  function v2Row(labelEn, valueText, valueZh) {
    var row = document.createElement('div');
    row.className = 'ci-v2-row';
    var k = document.createElement('span');
    k.className = 'ci-v2-key';
    pair(k, labelEn, V2_ZH[labelEn] || labelEn);
    var v = document.createElement('span');
    v.className = 'ci-v2-val';
    if (valueZh) {
      pair(v, String(valueText || ''), valueZh);
    } else {
      v.setAttribute('lang', 'en');
      v.textContent = String(valueText || '');
    }
    row.appendChild(k);
    row.appendChild(v);
    return row;
  }

  function coverageStatePair(state) {
    if (state === 'unlicensed') return {en: 'Unlicensed', zh: '未授权'};
    if (state === 'not_joined') return {en: 'Not joined', zh: '未接入'};
    if (state === 'unstructured') return {en: 'Unavailable / unstructured', zh: '暂无结构化计数'};
    var display = String(state || '').replace(/_/g, ' ');
    return {en: display, zh: V2_ZH[state] || display};
  }

  function v2PeriodPair(data) {
    var fp = data.fiscal_period || {};
    var q = Number(fp.quarter);
    var y = Number(fp.year);
    var dateEn = displayDate(data.event_date, 'en-US');
    var dateZh = displayDate(data.event_date, 'zh-CN');
    var enParts = [ticker];
    var zhParts = [ticker];
    if (q && y) {
      enParts.push('Q' + q + ' FY' + y);
      zhParts.push('Q' + q + ' 财年' + y);
    }
    if (dateEn) enParts.push(dateEn);
    if (dateZh) zhParts.push(dateZh);
    return {en: enParts.join(' · '), zh: zhParts.join(' · ')};
  }

  function analysisUrl() {
    return 'https://app.mastermind-x.com/analysis?symbol=' + encodeURIComponent(ticker) + '&page=intelligence';
  }

  /* Render the frozen v2 glance hierarchy.
   * v1 fetch is never requested on this path. */
  function renderV2(data) {
    root.setAttribute('data-ci-plane', 'event_workspace.v1');
    root.setAttribute('data-ci-event-id', String(data.event_id || ''));
    root.setAttribute('data-ci-generation-id', String(data.generation_id || ''));
    root.setAttribute('data-ci-mode', 'v2');

    /* Period: TICKER · Q3 FY2026 · Jul 30 / TICKER · Q3 财年2026 · 30 7月 */
    var pPair = v2PeriodPair(data);
    clear(period);
    pair(period, pPair.en, pPair.zh);

    /* State chip */
    setState('ready', 'Verified event', '已核实事件');

    /* Clear v1 narrative areas — CSS also hides them in v2 mode */
    if (summary) clear(summary);
    if (tags) { clear(tags); tags.hidden = true; }

    /* History is hidden in v2 mode */
    if (history) history.hidden = true;

    /* Build v2 rows into #ci-v2-host in the story column so the first
     * viewport is REPORTED / GUIDANCE / WATCH / COVERAGE. */
    var rows = document.createElement('div');
    rows.className = 'ci-v2-rows';

    /* REPORTED */
    var reported = Array.isArray(data.reported) ? data.reported : [];
    if (reported.length) {
      rows.appendChild(v2SectionHead('Reported'));
      reported.forEach(function (item) {
        rows.appendChild(v2Row(String(item.label || item.metric || ''), String(item.value || '')));
      });
    }

    /* GUIDANCE */
    var guidance = Array.isArray(data.guidance) ? data.guidance : [];
    if (guidance.length) {
      rows.appendChild(v2SectionHead('Guidance'));
      guidance.forEach(function (item) {
        rows.appendChild(v2Row(String(item.label || item.metric || ''), String(item.value || '')));
      });
    }

    /* WATCH — omit section entirely if empty; label + source-backed claim text */
    var watch = Array.isArray(data.watch) ? data.watch : [];
    if (watch.length) {
      rows.appendChild(v2SectionHead('Watch'));
      watch.forEach(function (item) {
        rows.appendChild(v2Row(String(item.label || ''), String(item.value || '')));
      });
    }

    /* COVERAGE — frozen as an array of {id, label, state} */
    var covStates = Array.isArray(data.coverage_states) ? data.coverage_states : [];
    if (covStates.length) {
      rows.appendChild(v2SectionHead('Coverage'));
      covStates.forEach(function (item) {
        if (!item || typeof item !== 'object') return;
        var statePair = coverageStatePair(String(item.state || ''));
        rows.appendChild(v2Row(String(item.label || item.id || ''), statePair.en, statePair.zh));
      });
    }

    if (v2Host) {
      v2Host.hidden = false;
      clear(v2Host);
      v2Host.appendChild(rows);
    } else if (metrics) {
      clear(metrics);
      metrics.appendChild(rows);
    }
    if (v2Host && metrics) clear(metrics);

    /* Primary CTA: analysis intelligence URL */
    var aUrl = analysisUrl();
    if (terminalUpgrade) {
      terminalUpgrade.href = aUrl;
      terminalUpgrade.rel = 'noopener noreferrer';
      terminalUpgrade.target = '_blank';
      setPair(terminalUpgrade, 'Open full event in Terminal', '在终端打开完整事件');
    }

    /* Secondary transcript — keep if event_alias resolves to a period key (AAPL/2026Q3 → tx=2026Q3) */
    if (transcript) {
      var alias = String(data.event_alias || '');
      var slashIdx = alias.indexOf('/');
      var periodKey = slashIdx >= 0 ? alias.slice(slashIdx + 1) : '';
      if (periodKey) {
        var txUrl = new URL('https://app.mastermind-x.com/terminal');
        txUrl.searchParams.set('sym', ticker);
        txUrl.searchParams.set('pane', 'transcripts');
        txUrl.searchParams.set('tx', periodKey);
        txUrl.searchParams.set('from', 'company-intelligence');
        transcript.href = txUrl.toString();
      }
    }

    loading.hidden = true;
    empty.hidden = true;
    content.hidden = false;
    root.removeAttribute('aria-busy');

    clear(receipt);
    var gen = generatedLabel(data.event_date);
    pair(receipt, gen ? 'Event date ' + gen : 'Current event', gen ? '事件日期 ' + gen : '当前事件');

    clear(footNote);
    pair(footNote, 'Source-backed current event', '来源核实的当期事件');

    if (announcer) setPair(announcer, pPair.en, pPair.zh);

    try {
      window.dispatchEvent(new CustomEvent('mmx:company-intelligence-ready', {
        detail: {ticker: ticker, status: 'v2', generation_id: data.generation_id, mode: 'v2'}
      }));
    } catch (ignore) {}
  }

  /* Show unavailable state for 503 / 429 / network error / invalid schema.
   * NEVER requests v1 — fallback law is frozen. */
  function showV2Unavailable() {
    var aUrl = analysisUrl();

    root.setAttribute('data-ci-mode', 'unavailable');
    loading.hidden = true;
    content.hidden = true;
    empty.hidden = false;
    root.removeAttribute('aria-busy');

    setState('unavailable', 'Verified event temporarily unavailable', '已核实事件暂时不可用');
    setPair(emptyTitle, 'Verified event temporarily unavailable', '已核实事件暂时不可用');
    setPair(emptyCopy, 'Verified event temporarily unavailable', '已核实事件暂时不可用');

    /* Open Terminal CTA → analysis URL */
    if (terminalUpgradeEmpty) {
      terminalUpgradeEmpty.href = aUrl;
      terminalUpgradeEmpty.rel = 'noopener noreferrer';
      terminalUpgradeEmpty.target = '_blank';
      setPair(terminalUpgradeEmpty, 'Open full event in Terminal', '在终端打开完整事件');
    }

    /* Retry button — re-runs only the v2 fetch; never duplicate */
    var existingRetry = document.getElementById('ci-retry');
    if (existingRetry && existingRetry.parentNode) existingRetry.parentNode.removeChild(existingRetry);
    var retryBtn = document.createElement('button');
    retryBtn.id = 'ci-retry';
    retryBtn.type = 'button';
    retryBtn.className = 'gbtn';
    pair(retryBtn, 'Retry', '重试');
    retryBtn.addEventListener('click', function () {
      var existing = document.getElementById('ci-retry');
      if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
      empty.hidden = true;
      loading.hidden = false;
      root.setAttribute('aria-busy', 'true');
      doV2Fetch();
    });
    empty.appendChild(retryBtn);
  }

  /* Primary fetch — /api/event-workspace/{ticker} is the current-event authority. */
  function doV2Fetch() {
    var v2Handled = false;
    var v2Controller = typeof AbortController === 'function' ? new AbortController() : null;
    var v2Timeout = window.setTimeout(function () { if (v2Controller) v2Controller.abort(); }, 10000);

    fetch('/api/event-workspace/' + encodeURIComponent(ticker), {
      method: 'GET',
      credentials: 'same-origin',
      headers: {'Accept': 'application/json'},
      signal: v2Controller ? v2Controller.signal : undefined
    }).then(function (response) {
      if (response.status === 404) {
        /* Genuine no-coverage: fall through to the v1 teaser. */
        v2Handled = true;
        window.clearTimeout(v2Timeout);
        fetchV1();
        return null;
      }
      if (!response.ok) {
        /* 503 / 429 / any other non-200 non-404: unavailable, never v1. */
        v2Handled = true;
        window.clearTimeout(v2Timeout);
        showV2Unavailable();
        return null;
      }
      return response.json();
    }).then(function (data) {
      if (v2Handled) return;
      window.clearTimeout(v2Timeout);
      /* Validate schema; an invalid payload is treated as unavailable, not as a v1 cue. */
      if (!data ||
          data.schema !== 'event_workspace_public_glance.v1' ||
          data.available !== true ||
          !data.event_id) {
        showV2Unavailable();
        return;
      }
      renderV2(data);
    }).catch(function () {
      window.clearTimeout(v2Timeout);
      if (!v2Handled) showV2Unavailable();
    });
  }

  /* Legacy v1 path — only reached via genuine 404 from /api/event-workspace/. */
  function fetchV1() {
    root.setAttribute('data-ci-mode', 'v1');
    root.setAttribute('data-ci-plane', 'company_intelligence.v1');

    var ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    var timeout = window.setTimeout(function () { if (ctrl) ctrl.abort(); }, 10000);
    fetch('/api/company-intelligence/' + encodeURIComponent(ticker), {
      method: 'GET',
      credentials: 'same-origin',
      headers: {'Accept': 'application/json'},
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (response) {
      if (response.status === 404) return null;
      if (!response.ok) throw new Error('company intelligence unavailable');
      return response.json();
    }).then(function (data) {
      window.clearTimeout(timeout);
      if (!data || data.available !== true) {
        showEmpty('unavailable', 'No company record yet', '暂无公司记录',
          'This ticker is not covered by the Company Intelligence source plane yet.',
          '该股票暂未纳入公司情报的来源记录覆盖范围。');
        return;
      }
      showPayload(data);
    }).catch(function () {
      window.clearTimeout(timeout);
      showEmpty('unavailable', 'Live record unavailable', '实时记录暂不可用',
        'The company source record could not be loaded. The rest of this dossier is unaffected; try again later or open Terminal.',
        '公司来源记录暂时无法加载。其余档案不受影响；请稍后重试或打开终端。');
    });
  }

  /* ── Init ── */
  empty.hidden = true;
  loading.hidden = false;
  root.setAttribute('aria-busy', 'true');
  loadRouteCatalog();
  doV2Fetch();
})();

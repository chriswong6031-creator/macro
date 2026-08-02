/* Mastermind Company Intelligence dossier surface.
 *
 * Browser-visible data is a bounded projection from the source-backed public
 * Company Intelligence plane. It is context only: this module never computes
 * a score, recommendation, target, rank, or trading action.
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
      setPair(nextCopy, 'Compare the next call with this baseline and verify any narrative change in the transcript.', '以下次电话会与本期基准对比，并在原文中核对表述变化。');
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
      incomplete ? 'Source record available · transcript check needed' : 'Source record available',
      incomplete ? '来源记录可用 · 需核对原文' : '来源记录可用');
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

  empty.hidden = true;
  loading.hidden = false;
  root.setAttribute('aria-busy', 'true');
  loadRouteCatalog();
  var controller = typeof AbortController === 'function' ? new AbortController() : null;
  var timeout = window.setTimeout(function () { if (controller) controller.abort(); }, 10000);
  fetch('/api/company-intelligence/' + encodeURIComponent(ticker), {
    method: 'GET',
    credentials: 'same-origin',
    headers: {'Accept': 'application/json'},
    signal: controller ? controller.signal : undefined
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
})();

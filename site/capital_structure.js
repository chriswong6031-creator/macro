(function () {
  'use strict';

  // This desk intentionally has no static-artifact fallback. Every browser read
  // stays on the authenticated, same-origin API boundary.
  var API = '/api/capital-structure/v1';
  var PAGE_SIZE = 100;
  var RECENT_WINDOW_DAYS = 30;
  var state = {
    coverage: null,
    overview: [],
    filter: 'all',
    query: '',
    selectedIssuerId: '',
    record: null,
    events: [],
    nextEventCursor: '',
    lastFocus: null,
    loadToken: 0
  };
  var ui = {};

  function esc(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function asArray(value) { return Array.isArray(value) ? value : []; }

  function firstDefined() {
    for (var i = 0; i < arguments.length; i += 1) {
      if (arguments[i] !== undefined && arguments[i] !== null && arguments[i] !== '') return arguments[i];
    }
    return null;
  }

  function formatTime(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ').replace('Z', ' UTC');
    return date.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'
    });
  }

  function shortTime(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 16).replace('T', ' ');
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function isZh() { return document.documentElement.getAttribute('data-lang') === 'zh'; }
  function copy(en, zh) { return isZh() ? (zh || en) : en; }

  // The event spine is deliberately machine-readable. Never title-case an
  // unrecognized token into the customer view: Chinese readers would receive
  // untranslated English, while English readers would mistake an internal enum
  // for a product claim. Known values get explicit twins; unknowns get a plain,
  // neutral observed-state fallback.
  var LABELS = {
    lifecycle: {
      filed: ['Filed', '已申报'],
      amended: ['Amended', '已修订'],
      effective: ['Effective', '已生效'],
      withdrawn: ['Withdrawn', '已撤回'],
      priced: ['Pricing filing observed', '已观察到定价申报'],
      closed: ['Closed', '已结束'],
      expired: ['Expired', '已到期'],
      unknown: ['Observed', '已观察']
    },
    subtype: {
      registration_statement: ['Registration statement', '注册说明书'],
      automatic_shelf_registration: ['Automatic shelf registration', '自动货架注册'],
      registration_amendment: ['Registration amendment', '注册说明书修订'],
      post_effective_amendment: ['Post-effective amendment', '生效后修订'],
      effectiveness_notice: ['SEC effectiveness notice', 'SEC 生效通知'],
      withdrawal_request: ['Withdrawal filing', '撤回申报'],
      automatic_shelf_withdrawal: ['Automatic shelf withdrawal', '自动货架撤回'],
      prospectus_event: ['Prospectus filing', '招股说明书申报'],
      charter_amendment_candidate: ['Charter amendment filing', '章程修订申报'],
      shareholder_vote_candidate: ['Shareholder vote filing', '股东投票申报'],
      unregistered_equity_sale_candidate: ['Equity sale filing', '股权出售申报'],
      financing_agreement_candidate: ['Financing agreement filing', '融资协议申报'],
      current_report_candidate: ['Current report filing', '临时报告申报'],
      authorization_or_vote_candidate: ['Authorization or vote filing', '授权或投票申报'],
      offering_statement: ['Regulation A statement', 'Regulation A 说明书'],
      offering_statement_amendment: ['Regulation A amendment', 'Regulation A 修订'],
      reg_a_event_candidate: ['Regulation A filing', 'Regulation A 申报'],
      periodic_reconciliation_source: ['Periodic filing source', '定期申报来源'],
      ownership_context_source: ['Ownership filing source', '持股申报来源'],
      unsupported_form: ['Observed SEC filing', '已观察 SEC 申报']
    },
    family: {
      shelf: ['Shelf registration', '货架注册'],
      atm: ['At-the-market filing', '按市价发行申报'],
      follow_on: ['Follow-on offering filing', '后续发行申报'],
      rdo: ['Registered direct filing', '注册直销申报'],
      pipe: ['Private investment filing', '私募投资申报'],
      eloc: ['Equity line filing', '股权额度申报'],
      sepa: ['Equity purchase filing', '股权购买申报'],
      warrant: ['Warrant filing', '认股权证申报'],
      convertible: ['Convertible filing', '可转换证券申报'],
      resale_registration: ['Resale registration', '转售注册'],
      rights_offering: ['Rights offering filing', '配股发行申报'],
      reg_a: ['Regulation A filing', 'Regulation A 申报'],
      corporate_action: ['Corporate action filing', '公司行动申报'],
      other: ['Observed SEC filing', '已观察 SEC 申报']
    },
    classification: {
      classified: ['Classified', '已分类'],
      deferred_missing_document: ['Document review pending', '待文件复核'],
      deferred_unsupported_media: ['Source review pending', '待来源复核'],
      deferred_ambiguous_content: ['Content review pending', '待内容复核'],
      deferred_conflict: ['Record review pending', '待记录复核'],
      deferred_linkage: ['Link review pending', '待关联复核'],
      not_applicable: ['Not applicable', '不适用']
    },
    change: {
      registration_observed: ['Registration statement observed', '已观察到注册说明书'],
      automatic_shelf_registration_observed: ['Automatic shelf registration observed', '已观察到自动货架注册'],
      registration_amendment_observed: ['Registration amendment observed', '已观察到注册说明书修订'],
      post_effective_amendment_observed: ['Post-effective amendment observed', '已观察到生效后修订'],
      effectiveness_notice_observed: ['SEC effectiveness notice observed', '已观察到 SEC 生效通知'],
      withdrawal_observed: ['Withdrawal filing observed', '已观察到撤回申报'],
      reg_a_statement_observed: ['Regulation A statement observed', '已观察到 Regulation A 说明书'],
      reg_a_amendment_observed: ['Regulation A amendment observed', '已观察到 Regulation A 修订'],
      classification_pending: ['Filing observed; review pending', '已观察到申报；待复核'],
      filing_state_observed: ['Filing state observed', '已观察到申报状态'],
      amendment_of_link_observed: ['Amendment link observed', '已观察到修订关联'],
      effectuates_link_observed: ['Effectiveness link observed', '已观察到生效关联'],
      withdraws_link_observed: ['Withdrawal link observed', '已观察到撤回关联'],
      supersedes_link_observed: ['Correction link observed', '已观察到修正关联']
    }
  };
  var LABEL_FALLBACKS = {
    lifecycle: ['Observed', '已观察'],
    subtype: ['Observed SEC filing', '已观察 SEC 申报'],
    family: ['Observed SEC filing', '已观察 SEC 申报'],
    classification: ['Review state not available', '复核状态暂不可用'],
    change: ['Observed filing update', '已观察到申报更新']
  };

  function normalizedKey(value) { return String(value || '').trim().toLowerCase(); }
  function labelPair(kind, value) {
    return (LABELS[kind] && LABELS[kind][normalizedKey(value)]) || LABEL_FALLBACKS[kind];
  }
  function labelFor(kind, value) {
    var pair = labelPair(kind, value);
    return copy(pair[0], pair[1]);
  }

  function withAuth(headers) {
    headers = headers || {};
    if (!(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(headers);
    return window.MDXAuth.client()
      .then(function (client) { return client.auth.getSession(); })
      .then(function (result) {
        var token = result && result.data && result.data.session && result.data.session.access_token;
        if (token) headers.Authorization = 'Bearer ' + token;
        return headers;
      })
      .catch(function () { return headers; });
  }

  function api(path) {
    return withAuth({ Accept: 'application/json' })
      .then(function (headers) {
        return fetch(API + path, {
          credentials: 'same-origin',
          cache: 'no-store',
          headers: headers
        });
      })
      .then(function (response) {
        if (!response.ok) {
          var error = new Error('HTTP ' + response.status);
          error.status = response.status;
          throw error;
        }
        return response.json();
      });
  }

  function listFrom(data) {
    if (Array.isArray(data)) return data;
    data = data || {};
    return asArray(firstDefined(data.items, data.records, data.issuers, data.events, data.timeline));
  }

  function recordFrom(data) { return (data && (data.record || data.issuer || data.item)) || data || null; }

  function identityFor(item) {
    var identity = (item && item.identity) || {};
    return {
      issuerId: firstDefined(item && item.issuer_id, item && item.issuerId, identity.issuer_id, ''),
      ticker: firstDefined(identity.ticker, item && item.ticker, identity.symbol, identity.observed_tickers && identity.observed_tickers[0], '—'),
      name: firstDefined(identity.name, identity.company_name, item && item.name, item && item.company_name, identity.aliases && identity.aliases[0], 'Unknown issuer'),
      cik: firstDefined(identity.cik, item && item.cik, ''),
      aliases: asArray(identity.aliases)
    };
  }

  function latestFor(item) { return (item && (item.latest_observed_event || item.latest || item.event)) || {}; }
  function observedAt(event) { return firstDefined(event && event.clocks && event.clocks.mastermind_observed_at, event && event.observed_at, event && event.filing_date, ''); }
  function acceptedAt(event) { return firstDefined(event && event.clocks && event.clocks.sec_accepted_at, event && event.sec_accepted_at, event && event.filing_date, ''); }
  function reviewState(item) {
    var review = (item && item.review) || (item && item.latest_observed_event && item.latest_observed_event.review) || {};
    return firstDefined(review.state, item && item.review_state, 'none');
  }

  function projectionAsOf() {
    return firstDefined(state.coverage && state.coverage.as_of, '');
  }

  function isRecentObserved(observedValue, asOfValue) {
    var observed = new Date(observedValue);
    var asOf = new Date(asOfValue);
    if (Number.isNaN(observed.getTime()) || Number.isNaN(asOf.getTime()) || observed > asOf) return false;
    return asOf.getTime() - observed.getTime() <= RECENT_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  }

  function coverageFrom(data) { return (data && (data.coverage || data)) || {}; }

  function setNotice(message, kind) {
    ui.coverageState.textContent = message;
    ui.status.classList.toggle('is-fresh', kind === 'fresh');
    ui.status.classList.toggle('is-degraded', kind === 'degraded');
  }

  function renderCoverage() {
    var raw = coverageFrom(state.coverage);
    var status = String(firstDefined(raw.freshness, raw.state, raw.source_status, 'loading')).toLowerCase();
    var message;
    if (status === 'fresh' || status === 'ok') message = copy('Observed filing coverage is current', '已观察申报覆盖范围为最新');
    else if (status === 'partial') message = copy('Observed filing coverage is partial', '已观察申报覆盖范围不完整');
    else if (status === 'degraded') message = copy('Observed filing coverage is temporarily limited', '已观察申报覆盖范围暂时受限');
    else message = copy('Observed filing coverage is loading', '正在加载已观察申报覆盖范围');
    setNotice(message, status === 'fresh' || status === 'ok' ? 'fresh' : status === 'degraded' ? 'degraded' : 'partial');
    ui.asOf.textContent = formatTime(firstDefined(raw.as_of, state.coverage && state.coverage.as_of));
    ui.generatedAt.textContent = formatTime(firstDefined(raw.generated_at, state.coverage && state.coverage.generated_at));
    ui.issuerCount.textContent = firstDefined(raw.issuer_count, raw.issuers, state.overview.length, '—');
  }

  function matchesQuery(item, query) {
    if (!query) return true;
    var identity = identityFor(item);
    var haystack = [identity.ticker, identity.name, identity.cik].concat(identity.aliases, asArray(item && item.identity && item.identity.observed_tickers)).join(' ').toLowerCase();
    return haystack.indexOf(query) !== -1;
  }

  function visibleOverview() {
    var query = state.query.trim().toLowerCase();
    return state.overview.filter(function (item) {
      if (!matchesQuery(item, query)) return false;
      if (state.filter === 'review') return reviewState(item) === 'pending';
      if (state.filter === 'recent') return isRecentObserved(observedAt(latestFor(item)), projectionAsOf());
      return true;
    });
  }

  function rowMarkup(item) {
    var identity = identityFor(item);
    var latest = latestFor(item);
    var selected = identity.issuerId && identity.issuerId === state.selectedIssuerId;
    var review = reviewState(item) === 'pending';
    var observed = observedAt(latest);
    return '<button class="cs-issuer-row" type="button" role="listitem" data-issuer-id="' + esc(identity.issuerId) + '" aria-current="' + (selected ? 'true' : 'false') + '">' +
      '<span class="cs-row-symbol">' + esc(identity.ticker || '—') + '</span>' +
      '<span><span class="cs-row-name">' + esc(identity.name) + '</span><span class="cs-row-meta">' + esc(latest.form || '—') + ' · ' + esc(shortTime(observed)) + '</span></span>' +
      '<span class="cs-row-review' + (review ? ' is-pending' : '') + '" aria-label="' + (review ? esc(copy('Needs review', '待复核')) : '') + '"></span>' +
      '</button>';
  }

  function renderOverview() {
    var items = visibleOverview();
    ui.railCount.textContent = String(items.length);
    if (!items.length) {
      ui.issuerList.innerHTML = '<div class="cs-issuer-empty">' + esc(copy('No observed issuer matches this view.', '没有符合当前视图的已观察发行人。')) + '</div>';
      return;
    }
    ui.issuerList.innerHTML = items.map(rowMarkup).join('');
  }

  function setStateChip(value) {
    ui.lifecycleState.textContent = labelFor('lifecycle', value);
    ui.lifecycleState.className = 'cs-state-chip';
    var normalized = String(value || '').toLowerCase();
    if (normalized === 'effective') ui.lifecycleState.classList.add('is-effective');
    else if (normalized === 'filed' || normalized === 'amended') ui.lifecycleState.classList.add('is-filed');
    else if (normalized === 'withdrawn') ui.lifecycleState.classList.add('is-withdrawn');
  }

  function eventTitle(event) {
    if (event && LABELS.subtype[normalizedKey(event.subtype)]) return labelFor('subtype', event.subtype);
    if (event && LABELS.family[normalizedKey(event.family)]) return labelFor('family', event.family);
    return labelFor('subtype', '');
  }

  function renderChanges(record) {
    var changes = asArray(record && record.what_changed);
    if (!changes.length) {
      ui.changeList.innerHTML = '<p class="cs-empty-inline">' + esc(copy('No additional lifecycle change is recorded for this issuer.', '该发行人尚无额外生命周期变化记录。')) + '</p>';
      return;
    }
    ui.changeList.innerHTML = changes.slice(0, 8).map(function (change) {
      return '<div class="cs-change"><span class="cs-change-dot" aria-hidden="true"></span><span class="cs-change-label">' + esc(labelFor('change', change.change_type)) + '</span><time class="cs-change-time">' + esc(shortTime(firstDefined(change.observed_at, change.at))) + '</time></div>';
    }).join('');
  }

  function eventMarkup(event) {
    var stateValue = firstDefined(event.lifecycle_state, event.state, 'observed');
    var detail = [labelFor('lifecycle', stateValue), labelFor('classification', event.classification_state)].filter(Boolean).join(' · ');
    return '<li class="cs-event">' +
      '<time class="cs-event-date">' + esc(shortTime(acceptedAt(event))) + '</time>' +
      '<span><strong class="cs-event-title">' + esc(eventTitle(event)) + '</strong><span class="cs-event-sub">' + esc(detail) + '</span></span>' +
      '<span class="cs-event-form">' + esc(event.form || '—') + '</span>' +
      '</li>';
  }

  function renderEvents() {
    if (!state.events.length) {
      ui.eventList.innerHTML = '<li class="cs-empty-inline">' + esc(copy('No observed events are available for this issuer.', '该发行人暂无可用的已观察事件。')) + '</li>';
    } else {
      ui.eventList.innerHTML = state.events.map(eventMarkup).join('');
    }
    ui.moreEvents.hidden = !state.nextEventCursor;
  }

  function renderScope(record) {
    var coverage = (record && record.coverage) || {};
    var rows = [
      [copy('Observed events', '已观察事件'), firstDefined(coverage.event_count, state.events.length, '—')],
      [copy('Classified', '已分类'), firstDefined(coverage.classified_event_count, '—')],
      [copy('Review items', '复核项目'), firstDefined(coverage.review_count, '—')]
    ];
    ui.scopeList.innerHTML = rows.map(function (row) {
      return '<div><dt>' + esc(row[0]) + '</dt><dd>' + esc(row[1]) + '</dd></div>';
    }).join('');
  }

  function safeSecUrl(value) {
    if (!value) return '';
    try {
      var parsed = new URL(value, window.location.origin);
      return parsed.protocol === 'https:' && (parsed.hostname === 'www.sec.gov' || parsed.hostname === 'sec.gov') ? parsed.href : '';
    } catch (error) { return ''; }
  }

  function renderEvidence() {
    var events = state.events.length ? state.events : asArray(state.record && state.record.timeline);
    var blocks = events.slice(0, 12).map(function (event) {
      var source = event.source || {};
      var url = safeSecUrl(firstDefined(source.filing_url, source.url));
      var evidence = asArray(source.evidence);
      var receipt = evidence[0] || {};
      var links = url ? '<a class="cs-evidence-link" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer"><span>' + esc(copy('Open SEC filing', '打开 SEC 申报')) + '</span><span aria-hidden="true">↗</span></a>' : '';
      var receiptText = [
        receipt.manifest_id ? 'manifest: ' + receipt.manifest_id : '',
        receipt.span_id ? 'span: ' + receipt.span_id : '',
        source.source_id ? 'source: ' + source.source_id : ''
      ].filter(Boolean).join('\n');
      return '<article class="cs-evidence-event"><h3>' + esc(event.form || '—') + ' · ' + esc(eventTitle(event)) + '</h3><p>' + esc(formatTime(acceptedAt(event))) + '</p><div class="cs-evidence-list">' + links + '</div>' + (receiptText ? '<pre class="cs-evidence-receipt">' + esc(receiptText) + '</pre>' : '') + '</article>';
    });
    ui.evidenceBody.innerHTML = blocks.length ? blocks.join('') : '<p class="cs-evidence-empty">' + esc(copy('No source receipt is available for this record yet.', '该记录暂时没有可用的来源凭据。')) + '</p>';
    ui.openEvidence.disabled = !blocks.length;
  }

  function renderRecord(record) {
    var identity = identityFor(record);
    var latest = latestFor(record);
    state.record = record;
    ui.emptyDossier.hidden = true;
    ui.dossierBody.hidden = false;
    ui.issuerSymbol.textContent = identity.ticker || '—';
    ui.issuerCik.textContent = identity.cik ? 'CIK ' + identity.cik : copy('SEC issuer record', 'SEC 发行人记录');
    ui.dossierTitleLive.textContent = identity.name;
    ui.issuerAlias.textContent = identity.aliases.filter(function (alias) { return alias !== identity.name; }).join(' · ') || copy('Observed issuer identity', '已观察发行人身份');
    ui.latestForm.textContent = latest.form || '—';
    ui.secAccepted.textContent = formatTime(acceptedAt(latest));
    ui.observedAt.textContent = formatTime(observedAt(latest));
    ui.classification.textContent = labelFor('classification', latest.classification_state);
    setStateChip(firstDefined(latest.lifecycle_state, latest.state, 'observed'));
    renderChanges(record);
    renderEvents();
    renderScope(record);
    renderEvidence();
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

  function focusableInDrawer() {
    return Array.prototype.slice.call(ui.evidenceDrawer.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(function (node) { return node.offsetParent !== null; });
  }

  function handleDrawerKeydown(event) {
    if (!ui.evidenceDrawer.classList.contains('is-open')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setDrawer(false);
      return;
    }
    if (event.key !== 'Tab') return;
    var focusable = focusableInDrawer();
    if (!focusable.length) {
      event.preventDefault();
      ui.evidenceDrawer.focus();
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

  function setDrawer(open) {
    var wasOpen = ui.evidenceDrawer.classList.contains('is-open');
    if (open) {
      state.lastFocus = document.activeElement;
      ui.evidenceDrawer.hidden = false;
      setInert(ui.evidenceDrawer, false);
      ui.evidenceDrawer.setAttribute('role', 'dialog');
      ui.evidenceDrawer.setAttribute('aria-modal', 'true');
      ui.evidenceDrawer.setAttribute('aria-hidden', 'false');
      ui.scrim.hidden = false;
      document.body.classList.add('cs-modal-open');
      setInert(ui.shell, true);
      setInert(ui.siteNav, true);
      window.requestAnimationFrame(function () {
        ui.evidenceDrawer.classList.add('is-open');
        ui.closeEvidence.focus();
      });
      return;
    }
    ui.evidenceDrawer.classList.remove('is-open');
    ui.evidenceDrawer.removeAttribute('role');
    ui.evidenceDrawer.removeAttribute('aria-modal');
    setInert(ui.evidenceDrawer, true);
    ui.evidenceDrawer.hidden = true;
    ui.scrim.hidden = true;
    document.body.classList.remove('cs-modal-open');
    setInert(ui.shell, false);
    setInert(ui.siteNav, false);
    if (wasOpen && state.lastFocus && typeof state.lastFocus.focus === 'function') {
      state.lastFocus.focus({ preventScroll: true });
    }
  }

  function eventResultFrom(data) {
    var events = listFrom(data);
    return {
      events: events,
      cursor: firstDefined(data && data.next_cursor, data && data.cursor_next, data && data.page && data.page.next_cursor, data && data.pagination && data.pagination.next_cursor, '')
    };
  }

  function overviewPages(cursor, accumulated) {
    var query = '?limit=' + PAGE_SIZE;
    if (cursor) query += '&cursor=' + encodeURIComponent(cursor);
    return api('/overview' + query).then(function (data) {
      var rows = accumulated.concat(listFrom(data));
      var next = firstDefined(data && data.page && data.page.next_cursor, data && data.next_cursor, '');
      return next ? overviewPages(next, rows) : { envelope: data, rows: rows };
    });
  }

  function issuerFromLocation() {
    try {
      return new URL(window.location.href).searchParams.get('issuer') || '';
    } catch (error) { return ''; }
  }

  function writeIssuerToLocation(issuerId, replace) {
    if (!(window.history && window.history.pushState)) return;
    var url;
    try { url = new URL(window.location.href); } catch (error) { return; }
    if (url.searchParams.get('issuer') === issuerId) return;
    url.searchParams.set('issuer', issuerId);
    window.history[replace ? 'replaceState' : 'pushState']({ issuer: issuerId }, '', url.href);
  }

  function selectIssuer(issuerId, options) {
    if (!issuerId) return Promise.resolve();
    options = options || {};
    var token = ++state.loadToken;
    state.selectedIssuerId = issuerId;
    if (options.updateUrl !== false) writeIssuerToLocation(issuerId, options.replaceUrl === true);
    renderOverview();
    ui.dossierBody.hidden = true;
    ui.emptyDossier.hidden = false;
    ui.emptyDossier.innerHTML = ui.loadingTemplate.innerHTML;
    var encoded = encodeURIComponent(issuerId);
    return Promise.all([
      api('/issuers/' + encoded),
      api('/issuers/' + encoded + '/events?limit=' + PAGE_SIZE)
    ]).then(function (responses) {
      if (token !== state.loadToken) return;
      var record = recordFrom(responses[0]);
      var page = eventResultFrom(responses[1]);
      state.events = page.events.length ? page.events : asArray(record && record.timeline);
      state.nextEventCursor = page.cursor;
      renderRecord(record);
      if (options.focus) ui.dossier.focus();
    }).catch(function (error) {
      if (token !== state.loadToken) return;
      state.events = [];
      state.nextEventCursor = '';
      ui.emptyDossier.hidden = false;
      ui.dossierBody.hidden = true;
      ui.emptyDossier.innerHTML = '<span class="cs-empty-glyph" aria-hidden="true">!</span><h2>' + esc(copy('Record unavailable', '记录暂不可用')) + '</h2><p>' + esc(error.status === 401 || error.status === 403 ? copy('Sign in with an eligible account to read this filing record.', '请使用符合条件的账户登录后读取此申报记录。') : copy('This issuer record is temporarily unavailable. Try again shortly.', '该发行人记录暂时不可用，请稍后重试。')) + '</p>';
    });
  }

  function loadMoreEvents() {
    if (!state.selectedIssuerId || !state.nextEventCursor) return;
    var encoded = encodeURIComponent(state.selectedIssuerId);
    var cursor = encodeURIComponent(state.nextEventCursor);
    ui.moreEvents.disabled = true;
    api('/issuers/' + encoded + '/events?cursor=' + cursor + '&limit=' + PAGE_SIZE)
      .then(function (data) {
        var page = eventResultFrom(data);
        state.events = state.events.concat(page.events);
        state.nextEventCursor = page.cursor;
        renderEvents();
        renderEvidence();
      })
      .catch(function () { state.nextEventCursor = ''; renderEvents(); })
      .finally(function () { ui.moreEvents.disabled = false; });
  }

  function resolveTicker() {
    var ticker = state.query.trim();
    if (!ticker) return;
    api('/issuers/resolve?ticker=' + encodeURIComponent(ticker)).then(function (data) {
      var issuerId = resolveIssuerId(data);
      if (issuerId) return selectIssuer(issuerId, { focus: true });
      setNotice(copy('No observed issuer matched that ticker', '没有已观察发行人匹配该代码'), 'partial');
      return null;
    }).catch(function () { setNotice(copy('Ticker lookup is temporarily unavailable', '代码查找暂时不可用'), 'degraded'); });
  }

  function resolveIssuerId(data) {
    // Resolver responses are an API envelope: the stable issuer ID lives under
    // `issuer`, never under the ticker query itself. Ambiguous lookups return a
    // 409 and are handled by the request catch, so this helper never guesses.
    var issuer = data && data.issuer;
    return issuer && typeof issuer.issuer_id === 'string' ? issuer.issuer_id : '';
  }

  function load() {
    ui.issuerList.innerHTML = ui.loadingTemplate.innerHTML;
    return Promise.all([
      api('/coverage'),
      overviewPages('', [])
    ]).then(function (responses) {
      state.coverage = responses[0];
      state.overview = responses[1].rows;
      renderCoverage();
      renderOverview();
      var requestedId = issuerFromLocation();
      var requested = requestedId && state.overview.some(function (item) {
        return identityFor(item).issuerId === requestedId;
      });
      if (requested) return selectIssuer(requestedId, { updateUrl: false });
      var first = state.overview[0];
      var firstId = first && identityFor(first).issuerId;
      if (firstId) return selectIssuer(firstId, { replaceUrl: true });
      return null;
    }).catch(function (error) {
      setNotice(error.status === 401 || error.status === 403 ? copy('Sign in to open observed filing state', '请登录后打开已观察申报状态') : copy('Observed filing state is temporarily unavailable', '已观察申报状态暂时不可用'), 'degraded');
      ui.railCount.textContent = '—';
      ui.issuerList.innerHTML = '<div class="cs-issuer-empty">' + esc(copy('The issuer browser could not load. Refresh to try again.', '发行人浏览器无法加载，请刷新后重试。')) + '</div>';
    });
  }

  function cacheUi() {
    ui.shell = document.getElementById('cs-shell');
    ui.siteNav = document.querySelector('.site-nav');
    ui.status = document.getElementById('cs-status');
    ui.coverageState = document.getElementById('cs-coverage-state');
    ui.asOf = document.getElementById('cs-as-of');
    ui.generatedAt = document.getElementById('cs-generated-at');
    ui.issuerCount = document.getElementById('cs-issuer-count');
    ui.search = document.getElementById('cs-search-input');
    ui.issuerList = document.getElementById('cs-issuer-list');
    ui.railCount = document.getElementById('cs-rail-count');
    ui.emptyDossier = document.getElementById('cs-empty-dossier');
    ui.dossier = document.getElementById('cs-dossier');
    ui.dossierBody = document.getElementById('cs-dossier-body');
    ui.issuerSymbol = document.getElementById('cs-issuer-symbol');
    ui.issuerCik = document.getElementById('cs-issuer-cik');
    ui.dossierTitleLive = document.getElementById('cs-dossier-title-live');
    ui.issuerAlias = document.getElementById('cs-issuer-alias');
    ui.latestForm = document.getElementById('cs-latest-form');
    ui.secAccepted = document.getElementById('cs-sec-accepted');
    ui.observedAt = document.getElementById('cs-observed-at');
    ui.classification = document.getElementById('cs-classification');
    ui.lifecycleState = document.getElementById('cs-lifecycle-state');
    ui.changeList = document.getElementById('cs-change-list');
    ui.eventList = document.getElementById('cs-event-list');
    ui.moreEvents = document.getElementById('cs-more-events');
    ui.scopeList = document.getElementById('cs-scope-list');
    ui.openEvidence = document.getElementById('cs-open-evidence');
    ui.evidenceDrawer = document.getElementById('cs-evidence-drawer');
    ui.evidenceBody = document.getElementById('cs-evidence-body');
    ui.closeEvidence = document.getElementById('cs-close-evidence');
    ui.scrim = document.getElementById('cs-scrim');
    ui.loadingTemplate = document.getElementById('cs-loading-template');
  }

  function updateLocalizedAttributes() {
    var input = ui.search;
    if (input) input.placeholder = isZh() ? input.getAttribute('data-placeholder-zh') : input.getAttribute('data-placeholder-en');
  }

  function relabelDynamicContent() {
    updateLocalizedAttributes();
    renderCoverage();
    if (state.record) renderRecord(state.record);
  }

  function bind() {
    ui.search.addEventListener('input', function () { state.query = ui.search.value; renderOverview(); });
    ui.search.addEventListener('keydown', function (event) { if (event.key === 'Enter') resolveTicker(); });
    document.querySelectorAll('.cs-filter').forEach(function (button) {
      button.addEventListener('click', function () {
        state.filter = button.getAttribute('data-filter') || 'all';
        document.querySelectorAll('.cs-filter').forEach(function (item) {
          var active = item === button;
          item.classList.toggle('is-active', active);
          item.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        renderOverview();
      });
    });
    ui.issuerList.addEventListener('click', function (event) {
      var row = event.target.closest('[data-issuer-id]');
      if (row) selectIssuer(row.getAttribute('data-issuer-id'), { focus: true });
    });
    ui.moreEvents.addEventListener('click', loadMoreEvents);
    ui.openEvidence.addEventListener('click', function () { setDrawer(true); });
    ui.closeEvidence.addEventListener('click', function () { setDrawer(false); });
    ui.scrim.addEventListener('click', function () { setDrawer(false); });
    ui.evidenceDrawer.addEventListener('keydown', handleDrawerKeydown);
    window.addEventListener('popstate', function () {
      var issuerId = issuerFromLocation();
      if (!issuerId || issuerId === state.selectedIssuerId) return;
      var known = state.overview.some(function (item) { return identityFor(item).issuerId === issuerId; });
      if (known) selectIssuer(issuerId, { updateUrl: false, focus: true });
    });
    // theme.js owns the site-wide language control and dispatches `langchange`
    // on document after updating <html data-lang>. API-rendered labels must use
    // that same contract as the static bilingual spans around them.
    document.addEventListener('langchange', relabelDynamicContent);
  }

  function init() {
    cacheUi();
    updateLocalizedAttributes();
    bind();
    load();
  }

  // A pure-function seam for the offline contract test. It exposes no records,
  // mutable desk state, or authority; the production page never creates it.
  if (window.__CAPITAL_STRUCTURE_DESK_TEST__) {
    window.__CAPITAL_STRUCTURE_DESK_TEST__.resolveIssuerId = resolveIssuerId;
    window.__CAPITAL_STRUCTURE_DESK_TEST__.isRecentObserved = isRecentObserved;
    window.__CAPITAL_STRUCTURE_DESK_TEST__.labelPair = labelPair;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());

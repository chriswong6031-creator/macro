(function () {
  'use strict';

  var MILESTONE_API = '/api/biocatalyst/v1/trials/milestones';
  var TRIAL_API = '/api/biocatalyst/v1/trials';
  var TRIAL_ID = /^NCT\d{8}$/;
  var DATE_PARTS = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/;
  var WINDOW_VALUES = { '30': true, '90': true, '180': true, all: true };
  var MILESTONE_WINDOWS = { '30': 'next_30d', '90': 'next_90d', '180': 'next_180d', all: 'all' };
  var FIELD_VALUES = { primary_completion: true, completion: true };
  var PAGE_LIMIT = 50;
  var state = {
    payload: null,
    rows: [],
    nextCursor: '',
    selectedId: '',
    selected: null,
    detail: null,
    listToken: 0,
    detailToken: 0,
    listController: null,
    detailController: null,
    generation: '',
    loading: false,
    pageLoading: false,
    restarted: false,
    hasLoaded: false,
    appendFailed: false,
    accessLocked: false,
    returnFocus: null,
    filters: { field: 'primary_completion', window: '90', q: '', phase: '', status: '', condition: '' }
  };
  var ui = {};

  function byId(id) { return document.getElementById(id); }
  function lang() { return document.documentElement.getAttribute('data-lang') === 'zh' ? 'zh' : 'en'; }
  function tr(en, zh) { return lang() === 'zh' ? zh : en; }
  function str(value) { return value == null ? '' : String(value); }
  function clean(value) { return str(value).replace(/\s+/g, ' ').trim(); }
  function arr(value) { return Array.isArray(value) ? value : []; }
  function valueAt(object, key) { return object && typeof object === 'object' ? object[key] : null; }
  function text(node, value) { node.textContent = str(value); return node; }
  function el(tag, className, value) { var node = document.createElement(tag); if (className) node.className = className; if (value != null) text(node, value); return node; }
  function clearChildren(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function isTrialId(value) { return TRIAL_ID.test(clean(value)); }
  function unique(values) { var seen = {}; return values.filter(function (value) { var key = clean(value); if (!key || seen[key]) return false; seen[key] = true; return true; }); }

  function cacheUi() {
    ui.workspace = byId('bci-workspace');
    ui.status = byId('bci-status-label');
    ui.statusDetail = byId('bci-status-detail');
    ui.runStatus = document.querySelector('.bci-run-status');
    ui.refresh = byId('bci-refresh');
    ui.windowControl = byId('bci-window-control');
    ui.windowButtons = Array.prototype.slice.call(document.querySelectorAll('.bci-window'));
    ui.field = byId('bci-field-filter');
    ui.search = byId('bci-search');
    ui.phase = byId('bci-phase-filter');
    ui.statusFilter = byId('bci-status-filter');
    ui.condition = byId('bci-condition-filter');
    ui.clear = byId('bci-clear');
    ui.brainLaunch = byId('bci-brain-launch');
    ui.subtitle = byId('bci-queue-subtitle');
    ui.asOf = byId('bci-asof');
    ui.notice = byId('bci-state-notice');
    ui.pageStatus = byId('bci-page-status');
    ui.queue = byId('bci-queue');
    ui.queueFooter = byId('bci-queue-footer');
    ui.loadMore = byId('bci-load-more');
    ui.inspector = byId('bci-inspector-pane');
    ui.inspectorTitle = byId('bci-inspector-title');
    ui.inspectorBody = byId('bci-inspector-body');
    ui.inspectorClose = byId('bci-inspector-close');
    ui.scrim = byId('bci-scrim');
  }

  function dateParts(value) {
    var raw = clean(value), match = DATE_PARTS.exec(raw);
    if (!match) return null;
    var year = Number(match[1]), month = match[2] ? Number(match[2]) : 0, day = match[3] ? Number(match[3]) : 0;
    if (!year || (month && (month < 1 || month > 12)) || (day && (day < 1 || day > 31))) return null;
    return { raw: raw, year: year, month: month, day: day };
  }
  function dateLabel(value, precision) {
    var parts = dateParts(value), monthNames = lang() === 'zh'
      ? ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
      : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    if (!parts) return clean(value) || tr('Not recorded', '未记录');
    if (precision === 'year' || !parts.month) return lang() === 'zh' ? parts.year + '年' : String(parts.year);
    if (precision === 'month' || !parts.day) return lang() === 'zh' ? parts.year + '年' + monthNames[parts.month - 1] : monthNames[parts.month - 1] + ' ' + parts.year;
    return lang() === 'zh'
      ? parts.year + '年' + monthNames[parts.month - 1] + parts.day + '日'
      : monthNames[parts.month - 1] + ' ' + parts.day + ', ' + parts.year;
  }
  function timestampLabel(value) {
    var raw = clean(value), date = raw.split('T')[0];
    return dateParts(date) ? dateLabel(date, 'day') : (raw || tr('Not recorded', '未记录'));
  }
  function precisionOf(milestone) {
    var precision = clean(valueAt(milestone, 'precision')).toLowerCase();
    if (precision === 'year' || precision === 'month' || precision === 'day') return precision;
    var parts = dateParts(valueAt(milestone, 'date'));
    return parts && parts.day ? 'day' : (parts && parts.month ? 'month' : 'year');
  }
  function dateTypeOf(milestone) {
    var type = clean(valueAt(milestone, 'type')).toUpperCase();
    return type === 'ACTUAL' || type === 'ESTIMATED' || type === 'UNKNOWN' ? type : 'UNKNOWN';
  }
  function milestoneKindOf(milestone) {
    var kind = clean(valueAt(milestone, 'kind'));
    return kind === 'primary_completion' || kind === 'completion' ? kind : '';
  }
  function milestoneKindLabel(kind) {
    return kind === 'primary_completion'
      ? tr('Primary completion', '主要完成')
      : tr('Completion', '完成');
  }
  function dateTypeLabel(type) {
    var labels = {
      ACTUAL: ['Actual', '实际'],
      ESTIMATED: ['Estimated', '预计'],
      UNKNOWN: ['Unknown', '未知']
    };
    var pair = labels[type] || labels.UNKNOWN;
    return tr(pair[0], pair[1]);
  }
  function titleOf(trial) { return clean(valueAt(trial, 'brief_title')) || clean(valueAt(trial, 'title')) || tr('Untitled trial', '未命名试验'); }
  function nctOf(trial) { return clean(valueAt(trial, 'nct_id')); }
  function phasesOf(trial) { return unique(arr(valueAt(trial, 'phases')).map(clean)); }
  function conditionsOf(trial) { return unique(arr(valueAt(trial, 'conditions')).map(clean)); }
  function sponsorOf(trial) { var sponsor = valueAt(trial, 'sponsor'); return clean(valueAt(sponsor, 'name')); }
  function statusOf(trial) { return clean(valueAt(trial, 'status')); }
  function studyTypeOf(trial) { return clean(valueAt(trial, 'study_type')); }
  function enrollmentOf(trial) { var enrollment = valueAt(trial, 'enrollment'), count = valueAt(enrollment, 'count'); return count === 0 || count ? String(count) : ''; }
  function dateOf(trial, key) { var dates = valueAt(trial, 'dates'), value = valueAt(dates, key); return value && typeof value === 'object' ? clean(valueAt(value, 'date')) : clean(value); }

  function officialStudyUrl(url, id) {
    var candidate = clean(url), expected = 'https://clinicaltrials.gov/study/' + encodeURIComponent(id);
    return candidate.indexOf(expected) === 0 ? candidate : expected;
  }
  function withAuth(headers) {
    headers = headers || {};
    if (!(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(headers);
    return window.MDXAuth.client().then(function (client) { return client.auth.getSession(); }).then(function (result) {
      var token = result && result.data && result.data.session && result.data.session.access_token;
      if (token) headers.Authorization = 'Bearer ' + token;
      return headers;
    }).catch(function () { return headers; });
  }
  function fetchJson(url, signal) {
    return withAuth({ Accept: 'application/json' }).then(function (headers) {
      return fetch(url, { headers: headers, credentials: 'same-origin', cache: 'no-store', signal: signal });
    }).then(function (response) {
      if (!response.ok) { var error = new Error('HTTP ' + response.status); error.status = response.status; throw error; }
      return response.json();
    });
  }
  function abort(name) {
    if (state[name]) state[name].abort();
    state[name] = null;
  }

  function validMeta(payload) {
    return !!payload && typeof payload === 'object' && payload.schema_version === 'biocatalyst_api.v1' &&
      payload.source && typeof payload.source === 'object' && payload.health && typeof payload.health === 'object' &&
      payload.coverage && typeof payload.coverage === 'object' && payload.authority &&
      payload.authority.classification === 'source_fact' && payload.authority.decision_authority === false;
  }
  function validTrial(trial) { return !!trial && typeof trial === 'object' && isTrialId(nctOf(trial)) && !!(clean(valueAt(trial, 'title')) || clean(valueAt(trial, 'brief_title'))); }
  function validMilestone(item) {
    var trial = valueAt(item, 'trial'), milestone = valueAt(item, 'registry_milestone'), evidence = valueAt(item, 'evidence');
    var kind = milestoneKindOf(milestone), type = clean(valueAt(milestone, 'type')).toUpperCase(), precision = clean(valueAt(milestone, 'precision')).toLowerCase();
    return !!item && typeof item === 'object' && validTrial(trial) && !!milestone && typeof milestone === 'object' &&
      kind === state.filters.field && partialDateMatchesPrecision(valueAt(milestone, 'date'), precision) &&
      (type === 'ACTUAL' || type === 'ESTIMATED' || type === 'UNKNOWN') &&
      !!evidence && typeof evidence === 'object' && clean(valueAt(evidence, 'provider')) === 'ClinicalTrials.gov' &&
      clean(valueAt(evidence, 'record_id')) === nctOf(trial) && clean(valueAt(evidence, 'coverage')) === 'current_only';
  }
  function validEnvelope(payload) {
    var pagination = valueAt(payload, 'pagination'), query = valueAt(payload, 'query'), window = valueAt(payload, 'effective_window');
    return validMeta(payload) && Array.isArray(payload.milestones) && pagination && typeof pagination === 'object' &&
      Number.isSafeInteger(pagination.limit) && pagination.limit === PAGE_LIMIT &&
      Number.isSafeInteger(pagination.total) && pagination.total >= 0 &&
      (pagination.next_cursor == null || (typeof pagination.next_cursor === 'string' && /^[A-Za-z0-9_-]{1,384}$/.test(pagination.next_cursor))) &&
      query && typeof query === 'object' && window && typeof window === 'object';
  }
  function normalizedQueryValue(value) { return clean(value).toLowerCase(); }
  function fullDate(value) {
    var parts = dateParts(value), monthDays;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(clean(value)) || !parts || !parts.month || !parts.day) return false;
    monthDays = [31, ((parts.year % 4 === 0 && parts.year % 100 !== 0) || parts.year % 400 === 0) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return parts.day <= monthDays[parts.month - 1];
  }
  function partialDateMatchesPrecision(value, precision) {
    var raw = clean(value), parts = dateParts(raw);
    if (!parts) return false;
    if (precision === 'year') return /^\d{4}$/.test(raw);
    if (precision === 'month') return /^\d{4}-\d{2}$/.test(raw);
    return precision === 'day' && fullDate(raw);
  }
  function queryMatchesCurrentFilters(query) {
    if (!query || typeof query !== 'object') return false;
    var expected = {
      milestone_kind: state.filters.field,
      window: MILESTONE_WINDOWS[state.filters.window],
      from_date: '',
      to_date: '',
      q: state.filters.q,
      phase: state.filters.phase,
      status: state.filters.status,
      condition: state.filters.condition
    };
    return Object.keys(expected).every(function (key) {
      var expectedValue = expected[key];
      var actualValue = valueAt(query, key);
      if (!expectedValue) return actualValue == null || clean(actualValue) === '';
      return normalizedQueryValue(actualValue) === normalizedQueryValue(expectedValue);
    });
  }
  function effectiveWindowIsSane(window, apiWindow) {
    if (!window || typeof window !== 'object') return false;
    var from = clean(valueAt(window, 'from_date')), to = clean(valueAt(window, 'to_date')), anchor = clean(valueAt(window, 'anchor_date'));
    if (apiWindow === 'all') {
      return !anchor && (!from || fullDate(from)) && (!to || fullDate(to)) && (!from || !to || from <= to);
    }
    return fullDate(from) && fullDate(to) && fullDate(anchor) && anchor === from && from <= to;
  }
  function validateMilestoneEnvelope(payload) {
    if (!validEnvelope(payload)) throw new Error('Invalid milestone list contract');
    var query = valueAt(payload, 'query');
    if (!queryMatchesCurrentFilters(query)) throw new Error('Milestone query binding mismatch');
    if (!effectiveWindowIsSane(valueAt(payload, 'effective_window'), clean(valueAt(query, 'window')))) throw new Error('Invalid effective registry window');
  }
  function milestoneIdentity(item) {
    return nctOf(valueAt(item, 'trial')) + '|' + milestoneKindOf(valueAt(item, 'registry_milestone')) + '|' + clean(valueAt(valueAt(item, 'registry_milestone'), 'date'));
  }
  function validateMilestonePage(items, existingRows) {
    if (!Array.isArray(items)) throw new Error('Invalid milestone page');
    var seen = {};
    arr(existingRows).forEach(function (item) { seen[milestoneIdentity(item)] = true; });
    return items.map(function (item) {
      if (!validMilestone(item)) throw new Error('Invalid milestone record');
      var identity = milestoneIdentity(item);
      if (seen[identity]) throw new Error('Duplicate milestone identity');
      seen[identity] = true;
      return item;
    });
  }
  function validateMilestonePagination(payload, existingRows, requestedCursor, previousPayload) {
    var pagination = valueAt(payload, 'pagination'), previous = valueAt(previousPayload, 'pagination');
    var pageSize = payload.milestones.length, loadedBefore = arr(existingRows).length, loadedAfter = loadedBefore + pageSize;
    var total = pagination.total, nextCursor = clean(pagination.next_cursor), previousTotal = valueAt(previous, 'total');
    if (pageSize > pagination.limit || loadedAfter > total) throw new Error('Invalid milestone page bounds');
    if (total > loadedBefore && pageSize === 0) throw new Error('Empty milestone page before total');
    if (nextCursor && loadedAfter >= total) throw new Error('Unexpected milestone cursor');
    if (!nextCursor && loadedAfter !== total) throw new Error('Incomplete milestone pagination');
    if (requestedCursor && nextCursor === requestedCursor) throw new Error('Repeated milestone cursor');
    if (loadedBefore && (!Number.isSafeInteger(previousTotal) || previousTotal !== total)) throw new Error('Milestone total changed during pagination');
  }
  function generationKey(payload) {
    var source = valueAt(payload, 'source') || {}, health = valueAt(payload, 'health') || {}, coverage = valueAt(payload, 'coverage') || {};
    return [clean(valueAt(payload, 'as_of')), clean(valueAt(source, 'dataset_timestamp_raw')), clean(valueAt(health, 'last_success_at')), clean(valueAt(coverage, 'class')), valueAt(coverage, 'configured'), valueAt(coverage, 'observed')].join('|');
  }

  function readUrl() {
    var params = new URLSearchParams(window.location.search), field = clean(params.get('field')), windowName = clean(params.get('window'));
    state.filters.field = FIELD_VALUES[field] ? field : 'primary_completion';
    state.filters.window = WINDOW_VALUES[windowName] ? windowName : '90';
    state.filters.q = clean(params.get('q')).slice(0, 100);
    state.filters.phase = clean(params.get('phase')).slice(0, 40);
    state.filters.status = clean(params.get('status')).slice(0, 40);
    state.filters.condition = clean(params.get('condition')).slice(0, 100);
    state.selectedId = isTrialId(params.get('trial')) ? clean(params.get('trial')) : '';
  }
  function writeUrl() {
    var url = new URL(window.location.href), params = url.searchParams;
    function assign(name, value, keepDefault) { if (value && (keepDefault || value !== '90')) params.set(name, value); else params.delete(name); }
    assign('trial', state.selectedId, true);
    assign('field', state.filters.field, true);
    assign('window', state.filters.window, true);
    assign('q', state.filters.q, true);
    assign('phase', state.filters.phase, true);
    assign('status', state.filters.status, true);
    assign('condition', state.filters.condition, true);
    window.history.replaceState(null, '', url.pathname + (params.toString() ? '?' + params.toString() : '') + url.hash);
  }
  function syncControls() {
    ui.field.value = state.filters.field;
    ui.search.value = state.filters.q;
    ui.phase.value = state.filters.phase;
    ui.statusFilter.value = state.filters.status;
    ui.condition.value = state.filters.condition;
    ui.windowButtons.forEach(function (button) {
      var active = button.getAttribute('data-window') === state.filters.window;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-checked', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;
    });
  }
  function localizeControls() {
    var labels = {
      'bci-phase-filter': { PHASE1: ['Phase 1', '一期'], PHASE2: ['Phase 2', '二期'], PHASE3: ['Phase 3', '三期'], PHASE4: ['Phase 4', '四期'] },
      'bci-status-filter': { RECRUITING: ['Recruiting', '招募中'], NOT_YET_RECRUITING: ['Not yet recruiting', '尚未招募'], ACTIVE_NOT_RECRUITING: ['Active, not recruiting', '进行中，未招募'], COMPLETED: ['Completed', '已完成'], TERMINATED: ['Terminated', '已终止'] }
    };
    [ui.field, ui.phase, ui.statusFilter].forEach(function (select) {
      if (!select) return;
      Array.prototype.slice.call(select.options).forEach(function (option) {
        var pair = labels[select.id] && labels[select.id][option.value];
        text(option, pair ? tr(pair[0], pair[1]) : (option.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || option.textContent));
      });
    });
    [ui.search, ui.condition].forEach(function (input) {
      if (input) input.placeholder = input.getAttribute(lang() === 'zh' ? 'data-placeholder-zh' : 'data-placeholder-en') || input.placeholder;
    });
    ui.windowButtons.forEach(function (button) { button.setAttribute('aria-label', button.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || button.textContent); });
    [ui.refresh, ui.inspectorClose, ui.brainLaunch].forEach(function (button) {
      if (button) button.setAttribute('aria-label', button.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || button.textContent);
    });
    ui.queue.setAttribute('aria-label', tr('Registry milestones', '登记里程碑'));
    setLoadMoreCopy();
  }
  function queryUrl(cursor) {
    var params = new URLSearchParams();
    params.set('limit', String(PAGE_LIMIT));
    params.set('window', MILESTONE_WINDOWS[state.filters.window]);
    params.set('milestone_kind', state.filters.field);
    if (state.filters.q) params.set('q', state.filters.q);
    if (state.filters.phase) params.set('phase', state.filters.phase);
    if (state.filters.status) params.set('status', state.filters.status);
    if (state.filters.condition) params.set('condition', state.filters.condition);
    if (cursor) params.set('cursor', cursor);
    return MILESTONE_API + '?' + params.toString();
  }

  function setStatus(kind, label, detail) {
    ui.runStatus.classList.toggle('is-stale', kind === 'stale' || kind === 'restarted');
    ui.runStatus.classList.toggle('is-unavailable', kind === 'unavailable' || kind === 'locked');
    text(ui.status, label); text(ui.statusDetail, detail);
  }
  function setNotice(kind, message) { ui.notice.hidden = !message; ui.notice.className = 'bci-state-notice' + (kind ? ' is-' + kind : ''); text(ui.notice, message || ''); }
  function announce(message) { text(ui.pageStatus, message || ''); }
  function emptyCard(title, copy, mark, retry) {
    var wrap = el('div', 'bci-empty'), inside = el('div');
    inside.appendChild(el('span', 'bci-empty-mark', mark || '⌁'));
    inside.appendChild(el('strong', '', title));
    inside.appendChild(el('p', '', copy));
    if (retry) { var button = el('button', '', tr('Try again', '重试')); button.type = 'button'; button.addEventListener('click', function () { loadMilestones({ replace: true }); }); inside.appendChild(button); }
    wrap.appendChild(inside); return wrap;
  }
  function setLoadMoreCopy() {
    if (!ui.loadMore) return;
    var label = state.pageLoading
      ? tr('Loading more registry milestones', '正在加载更多登记里程碑')
      : (state.appendFailed
        ? tr('Retry loading more registry milestones', '重试加载更多登记里程碑')
        : tr('Load more registry milestones', '加载更多登记里程碑'));
    ui.loadMore.disabled = state.pageLoading;
    ui.loadMore.setAttribute('aria-label', label);
    ui.loadMore.setAttribute('aria-busy', state.pageLoading ? 'true' : 'false');
    text(ui.loadMore.querySelector('.l-en'), state.pageLoading ? 'Loading more…' : (state.appendFailed ? 'Retry load more' : 'Load more'));
    text(ui.loadMore.querySelector('.l-zh'), state.pageLoading ? '正在加载更多…' : (state.appendFailed ? '重试加载更多' : '加载更多'));
  }
  function loadingQueue(append) {
    if (!append) {
      clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'true');
      for (var i = 0; i < 3; i += 1) { var row = el('div', 'bci-skeleton'); row.setAttribute('aria-hidden', 'true'); for (var j = 0; j < 3; j += 1) row.appendChild(el('span')); ui.queue.appendChild(row); }
      ui.queueFooter.hidden = true;
    } else {
      ui.queue.setAttribute('aria-busy', 'true');
      ui.queueFooter.hidden = !state.nextCursor;
      setLoadMoreCopy();
    }
  }
  function typeBadge(type) {
    var normalized = dateTypeOf({ type: type }), badge = el('span', 'bci-date-type is-' + normalized.toLowerCase(), dateTypeLabel(normalized));
    badge.setAttribute('data-date-type', normalized);
    badge.setAttribute('aria-label', tr('Registry date type: ', '登记日期类型：') + dateTypeLabel(normalized));
    return badge;
  }
  function makeMilestoneRow(item, index) {
    var trial = item.trial, milestone = item.registry_milestone, evidence = item.evidence, id = nctOf(trial), button = el('button', 'bci-trial' + (id === state.selectedId ? ' is-selected' : ''));
    button.type = 'button'; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', id === state.selectedId ? 'true' : 'false'); button.setAttribute('data-trial-id', id); button.tabIndex = index === 0 ? 0 : -1;
    var main = el('span', 'bci-trial-main'), line = el('span', 'bci-trial-topline'), kind = milestoneKindOf(milestone);
    line.appendChild(el('span', 'bci-trial-id', id));
    line.appendChild(el('span', 'bci-registry-kind', milestoneKindLabel(kind)));
    if (statusOf(trial)) line.appendChild(el('span', 'bci-status-chip', statusOf(trial)));
    main.appendChild(line); main.appendChild(el('span', 'bci-trial-title', titleOf(trial)));
    var meta = el('span', 'bci-trial-meta'), phaseText = phasesOf(trial).join(' · ');
    if (phaseText) meta.appendChild(el('span', '', phaseText));
    if (sponsorOf(trial)) meta.appendChild(el('span', '', sponsorOf(trial)));
    if (conditionsOf(trial).length) meta.appendChild(el('span', '', conditionsOf(trial).slice(0, 2).join(' · ')));
    main.appendChild(meta); button.appendChild(main);
    var date = el('span', 'bci-trial-date');
    date.appendChild(el('strong', '', dateLabel(valueAt(milestone, 'date'), precisionOf(milestone))));
    date.appendChild(typeBadge(dateTypeOf(milestone)));
    date.setAttribute('data-precision', precisionOf(milestone));
    button.appendChild(date);
    button.addEventListener('click', function () { selectTrial(id, trial, evidence, true, button); });
    return button;
  }
  function syncQueueSelection() {
    Array.prototype.slice.call(ui.queue.querySelectorAll('.bci-trial')).forEach(function (button) {
      var selected = button.getAttribute('data-trial-id') === state.selectedId;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
  }
  function renderQueue() {
    clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', state.loading ? 'true' : 'false');
    if (state.accessLocked) {
      ui.queue.appendChild(emptyCard(tr('Registry records are locked', '登记记录已锁定'), tr('Sign in with full access to read registry-recorded dates.', '请以完整访问权限登录，读取登记记录日期。'), '◌'));
      ui.queueFooter.hidden = true;
      setLoadMoreCopy();
      return;
    }
    if (!state.rows.length) {
      ui.queue.appendChild(emptyCard(tr('No recorded dates', '暂无已记录日期'), tr('No registry-recorded primary completion or completion date matches this window and filter set.', '在此窗口和筛选条件下，没有匹配的主要完成或完成登记日期。'), '○'));
    } else {
      state.rows.forEach(function (item, index) { ui.queue.appendChild(makeMilestoneRow(item, index)); });
    }
    ui.queueFooter.hidden = !state.nextCursor || state.accessLocked;
    setLoadMoreCopy();
  }
  function setSubtitle(payload) {
    var pagination = valueAt(payload, 'pagination') || {}, total = valueAt(pagination, 'total'), window = valueAt(payload, 'effective_window') || {};
    if (typeof total !== 'number') { text(ui.subtitle, tr('Registry-recorded primary completion and completion dates', '登记记录的主要完成和完成日期')); return; }
    var timeLabel = clean(valueAt(window, 'from_date')) && clean(valueAt(window, 'to_date'))
      ? tr('within the selected record window', '位于所选记录窗口内')
      : tr('across the available record range', '覆盖可用记录范围');
    text(ui.subtitle, total === 1 ? tr('1 registry-recorded date ' + timeLabel, '1项登记记录日期' + timeLabel) : tr(total + ' registry-recorded dates ' + timeLabel, total + '项登记记录日期' + timeLabel));
  }

  function fact(label, value) { if (!value) return null; var box = el('div', 'bci-detail-fact'); box.appendChild(el('span', '', label)); box.appendChild(el('strong', '', value)); return box; }
  function listSection(title, values, fallback) { var section = el('section', 'bci-detail-section'); section.appendChild(el('h3', '', title)); if (!values.length) section.appendChild(el('p', 'bci-detail-note', fallback)); else { var list = el('ul', 'bci-detail-list'); values.forEach(function (value) { list.appendChild(el('li', '', value)); }); section.appendChild(list); } return section; }
  function endpointSection(title, outcomes, fallback) {
    var section = el('section', 'bci-detail-section'); section.appendChild(el('h3', '', title));
    if (!outcomes.length) { section.appendChild(el('p', 'bci-detail-note', fallback)); return section; }
    var list = el('div', 'bci-endpoints'); outcomes.forEach(function (outcome) {
      if (!outcome || typeof outcome !== 'object') return; var measure = clean(valueAt(outcome, 'measure')); if (!measure) return;
      var card = el('article', 'bci-endpoint'); card.appendChild(el('strong', '', measure)); var frame = clean(valueAt(outcome, 'time_frame')); if (frame) card.appendChild(el('span', '', frame)); var description = clean(valueAt(outcome, 'description')); if (description) card.appendChild(el('p', '', description)); list.appendChild(card);
    });
    if (!list.childNodes.length) section.appendChild(el('p', 'bci-detail-note', fallback)); else section.appendChild(list); return section;
  }
  function historyValue(value, depth) {
    depth = depth || 0; if (depth > 4) return tr('Structured value', '结构化值');
    if (value === null || typeof value === 'undefined') return tr('Not recorded', '未记录');
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return clean(String(value)) || tr('Not recorded', '未记录');
    if (Array.isArray(value)) return value.slice(0, 12).map(function (item) { return historyValue(item, depth + 1); }).join(' · ') || tr('Empty', '空');
    if (typeof value === 'object') return Object.keys(value).slice(0, 12).map(function (key) { return clean(key) + ': ' + historyValue(value[key], depth + 1); }).join(' · ') || tr('Empty', '空');
    return tr('Not recorded', '未记录');
  }
  function historyUnavailableCopy(reason) {
    var copy = {
      disabled: ['Registry history is not enabled for this record.', '该记录的登记历史尚未启用。'],
      not_collected: ['No verified registry history has been collected for this record yet.', '该记录尚未收集到已核验的登记历史。'],
      incomplete_chain: ['The available registry version chain is incomplete, so no change rows are shown.', '可用的登记版本链不完整，因此不会显示变化行。'],
      source_shape_drift: ['The registry history response changed shape; no change rows are shown until it is verified.', '登记历史响应结构已变化；完成核验前不会显示变化行。'],
      last_good_unavailable: ['No last verified registry history is available for this record.', '该记录暂无最近一次已核验的登记历史。']
    };
    var pair = copy[clean(reason)] || copy.not_collected; return tr(pair[0], pair[1]);
  }
  function historyKindLabel(kind) {
    var labels = {
      endpoint_added: ['Endpoint added', '新增终点'], endpoint_removed: ['Endpoint removed', '移除终点'], endpoint_role_changed: ['Endpoint role updated', '终点角色更新'], endpoint_measure_changed: ['Endpoint measure updated', '终点指标更新'], endpoint_time_frame_changed: ['Endpoint timeframe updated', '终点时间范围更新'], endpoint_description_changed: ['Endpoint description updated', '终点说明更新'], enrollment_changed: ['Enrollment record updated', '入组记录更新'], registry_status_changed: ['Registry status updated', '登记状态更新'], study_date_changed: ['Study date record updated', '研究日期记录更新'], site_listing_changed: ['Site listing updated', '研究中心列表更新'], lead_sponsor_text_changed: ['Lead sponsor text updated', '牵头申办方文字更新'], intervention_added: ['Intervention added', '新增干预措施'], intervention_removed: ['Intervention removed', '移除干预措施'], intervention_changed: ['Intervention record updated', '干预措施记录更新']
    };
    var pair = labels[clean(kind)]; return pair ? tr(pair[0], pair[1]) : tr('Registry field updated', '登记字段更新');
  }
  function historySection(history) {
    var section = el('section', 'bci-detail-section'); section.appendChild(el('h3', '', tr('Registry record updates', '登记记录更新')));
    if (!history || typeof history !== 'object' || history.available !== true) { section.appendChild(el('p', 'bci-detail-note', historyUnavailableCopy(valueAt(history, 'reason')))); return section; }
    var changes = arr(valueAt(history, 'changes')), versions = arr(valueAt(history, 'versions')), versionByNumber = {};
    versions.forEach(function (version) { var number = valueAt(version, 'display_version'); if (typeof number === 'number') versionByNumber[number] = version; });
    if (!changes.length) { section.appendChild(el('p', 'bci-detail-note', tr('No registry record differences are listed in the verified version chain.', '已核验版本链中未列出登记记录差异。'))); return section; }
    var groups = {};
    changes.forEach(function (change) { var before = valueAt(change, 'before_display_version'), after = valueAt(change, 'after_display_version'); if (typeof before !== 'number' || typeof after !== 'number') return; var key = before + ':' + after; if (!groups[key]) groups[key] = { before: before, after: after, changes: [] }; groups[key].changes.push(change); });
    Object.keys(groups).sort(function (left, right) { return groups[right].after - groups[left].after || groups[right].before - groups[left].before; }).forEach(function (key) {
      var group = groups[key], card = el('article', 'bci-endpoint bci-history-group'), heading = el('strong', '', 'V' + group.before + ' → V' + group.after), version = versionByNumber[group.after]; card.appendChild(heading);
      if (version && clean(valueAt(version, 'url'))) { var link = el('a', 'bci-detail-link', tr('Submitted ', '提交日期 ') + timestampLabel(clean(valueAt(version, 'submitted_at'))) + ' · ClinicalTrials.gov ↗'); link.href = clean(valueAt(version, 'url')); link.target = '_blank'; link.rel = 'noopener noreferrer'; card.appendChild(link); }
      group.changes.forEach(function (change) { var delta = el('div', 'bci-history-delta'), kind = historyKindLabel(valueAt(change, 'kind')); delta.appendChild(el('span', 'bci-history-kind', kind)); delta.appendChild(el('p', '', tr('Before: ', '之前：') + historyValue(valueAt(change, 'before_value')))); delta.appendChild(el('p', '', tr('After: ', '之后：') + historyValue(valueAt(change, 'after_value')))); card.appendChild(delta); }); section.appendChild(card);
    });
    if (!section.querySelector('.bci-history-group')) section.appendChild(el('p', 'bci-detail-note', tr('No display-safe registry record differences are available.', '暂无可安全展示的登记记录差异。')));
    return section;
  }
  function evidenceSection(detail, queueEvidence) {
    var evidence = valueAt(detail, 'evidence') || {}, id = nctOf(detail), provider = clean(valueAt(evidence, 'provider')) || clean(valueAt(queueEvidence, 'provider')),
      url = officialStudyUrl(clean(valueAt(evidence, 'url')) || clean(valueAt(queueEvidence, 'url')), id), coverage = clean(valueAt(evidence, 'coverage')) || clean(valueAt(queueEvidence, 'coverage')),
      update = clean(valueAt(evidence, 'updated_at')), retrieved = clean(valueAt(evidence, 'retrieved_at')) || clean(valueAt(detail, 'retrieved_at')), asOf = clean(valueAt(state.payload, 'as_of'));
    var section = el('section', 'bci-detail-section bci-evidence-section'); section.appendChild(el('h3', '', tr('Evidence & trust', '证据与可信度')));
    if (!provider || !isTrialId(id)) { section.appendChild(el('p', 'bci-detail-note', tr('Evidence details are unavailable for this current record. The dossier does not fill missing source fields.', '当前记录的证据详情暂不可用。档案不会填补缺失的来源字段。'))); return section; }
    var strip = el('div', 'bci-evidence-strip');
    strip.appendChild(fact(tr('Provider', '提供方'), provider));
    var official = el('div', 'bci-detail-fact'); official.appendChild(el('span', '', tr('Official record', '官方记录'))); var link = el('a', 'bci-evidence-link', tr('Open ClinicalTrials.gov ↗', '打开 ClinicalTrials.gov ↗')); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; official.appendChild(link); strip.appendChild(official);
    strip.appendChild(fact(tr('Coverage', '覆盖范围'), coverage === 'current_only' ? tr('Current record only', '仅当前记录') : tr('Unavailable', '暂不可用')));
    strip.appendChild(fact(tr('Source update', '来源更新'), update ? timestampLabel(update) : tr('Not recorded', '未记录')));
    strip.appendChild(fact(tr('Retrieved / as of', '获取 / 截至'), retrieved ? timestampLabel(retrieved) : (asOf ? timestampLabel(asOf) : tr('Not recorded', '未记录'))));
    section.appendChild(strip); return section;
  }
  function showInspectorEmpty(title, copy) { text(ui.inspectorTitle, title); clearChildren(ui.inspectorBody); var empty = el('div', 'bci-inspector-empty'); empty.appendChild(el('span', 'bci-empty-orbit')); empty.appendChild(el('p', '', copy)); ui.inspectorBody.appendChild(empty); }
  function showDetail(detail, queueEvidence) {
    text(ui.inspectorTitle, tr('Trial dossier', '试验档案')); clearChildren(ui.inspectorBody);
    var id = nctOf(detail), header = el('div'); header.appendChild(el('h3', 'bci-detail-title', titleOf(detail))); header.appendChild(el('p', 'bci-detail-id', id)); ui.inspectorBody.appendChild(header);
    ui.inspectorBody.appendChild(evidenceSection(detail, queueEvidence));
    var facts = el('section', 'bci-detail-section'); facts.appendChild(el('h3', '', tr('Current record', '当前记录'))); var grid = el('div', 'bci-detail-grid'), siteCount = valueAt(detail, 'site_count');
    [fact(tr('Status', '状态'), statusOf(detail)), fact(tr('Study type', '研究类型'), studyTypeOf(detail)), fact(tr('Sponsor', '申办方'), sponsorOf(detail)), fact(tr('Enrollment', '入组人数'), enrollmentOf(detail)), fact(tr('Sites', '研究中心'), typeof siteCount === 'number' ? String(siteCount) : ''), fact(tr('Start', '开始'), dateLabel(dateOf(detail, 'start'))), fact(tr('Primary completion', '主要完成'), dateLabel(dateOf(detail, 'primary_completion'))), fact(tr('Completion', '完成'), dateLabel(dateOf(detail, 'completion'))), fact(tr('Last update', '最近更新'), timestampLabel(clean(valueAt(detail, 'updated_at'))))].forEach(function (item) { if (item) grid.appendChild(item); });
    facts.appendChild(grid); ui.inspectorBody.appendChild(facts);
    ui.inspectorBody.appendChild(listSection(tr('Phases', '阶段'), phasesOf(detail), tr('No phase is listed in the current record.', '当前记录未列出阶段。')));
    ui.inspectorBody.appendChild(listSection(tr('Conditions', '适应症'), conditionsOf(detail), tr('No condition is listed in the current record.', '当前记录未列出适应症。')));
    var countries = arr(valueAt(detail, 'countries')).map(clean).filter(Boolean); ui.inspectorBody.appendChild(listSection(tr('Countries', '国家与地区'), countries, tr('No trial-site country is listed in the current record.', '当前记录未列出研究中心所在国家或地区。')));
    var interventions = arr(valueAt(detail, 'interventions')).map(function (item) { return clean(valueAt(item, 'name')) || clean(item); }).filter(Boolean); ui.inspectorBody.appendChild(listSection(tr('Interventions', '干预措施'), interventions, tr('No intervention detail is available in this current view.', '当前视图暂无干预措施详情。')));
    var endpoints = valueAt(detail, 'endpoints') || {}; ui.inspectorBody.appendChild(endpointSection(tr('Primary endpoints', '主要终点'), arr(valueAt(endpoints, 'primary')), tr('No primary endpoint is listed in the current record.', '当前记录未列出主要终点。'))); ui.inspectorBody.appendChild(endpointSection(tr('Secondary endpoints', '次要终点'), arr(valueAt(endpoints, 'secondary')), tr('No secondary endpoint is listed in the current record.', '当前记录未列出次要终点。')));
    ui.inspectorBody.appendChild(historySection(valueAt(detail, 'history')));
  }
  function inspectorIsModal() { return ui.inspector.classList.contains('is-open') && window.matchMedia('(max-width: 1120px)').matches; }
  function syncInspectorDialog() {
    if (inspectorIsModal()) {
      ui.inspector.setAttribute('role', 'dialog');
      ui.inspector.setAttribute('aria-modal', 'true');
    } else {
      ui.inspector.removeAttribute('role');
      ui.inspector.removeAttribute('aria-modal');
    }
  }
  function inspectorFocusables() {
    return Array.prototype.slice.call(ui.inspector.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter(function (node) {
      return node.offsetParent !== null;
    });
  }
  function trapInspectorFocus(event) {
    if (event.key !== 'Tab' || !inspectorIsModal()) return;
    var focusables = inspectorFocusables();
    if (!focusables.length) { event.preventDefault(); ui.inspector.focus(); return; }
    var first = focusables[0], last = focusables[focusables.length - 1];
    if (document.activeElement === ui.inspector) { event.preventDefault(); (event.shiftKey ? last : first).focus(); return; }
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  function openInspector(focus, trigger) {
    var mobile = window.matchMedia('(max-width: 1120px)').matches;
    if (mobile && !state.returnFocus) state.returnFocus = trigger || document.activeElement;
    ui.inspector.classList.add('is-open'); document.body.classList.add('bci-inspector-open'); ui.scrim.hidden = false; syncInspectorDialog();
    if (focus) ui.inspector.focus({ preventScroll: true });
  }
  function closeInspector(options) {
    options = options || {};
    var returnFocus = state.returnFocus, returnTrialId = returnFocus && clean(returnFocus.getAttribute('data-trial-id'));
    ui.inspector.classList.remove('is-open'); document.body.classList.remove('bci-inspector-open'); ui.scrim.hidden = true; syncInspectorDialog();
    state.returnFocus = null; state.selectedId = ''; state.selected = null; state.detail = null; abort('detailController');
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a registry milestone to read the current trial record and its source receipt.', '选择一项登记里程碑，查看当前试验记录及其来源凭证。'));
    if (options.writeUrl !== false) writeUrl();
    if (options.render !== false) syncQueueSelection();
    if ((!returnFocus || !document.contains(returnFocus)) && isTrialId(returnTrialId)) returnFocus = ui.queue.querySelector('[data-trial-id="' + returnTrialId + '"]');
    if (options.restoreFocus !== false && returnFocus && document.contains(returnFocus) && typeof returnFocus.focus === 'function') returnFocus.focus({ preventScroll: true });
  }
  function detailLoading() { text(ui.inspectorTitle, tr('Loading dossier', '正在加载档案')); clearChildren(ui.inspectorBody); ui.inspectorBody.appendChild(el('div', 'bci-loading-detail', tr('Reading the current official record…', '正在读取当前官方记录…'))); }
  function selectTrial(id, trial, queueEvidence, update, trigger) {
    if (!isTrialId(id)) return;
    state.selectedId = id; state.selected = trial || { nct_id: id, title: id }; state.detail = null; if (update) writeUrl(); syncQueueSelection();
    trigger = trigger && document.contains(trigger) ? trigger : ui.queue.querySelector('[data-trial-id="' + id + '"]');
    openInspector(window.matchMedia('(max-width: 1120px)').matches, trigger); detailLoading();
    abort('detailController'); var controller = new AbortController(), token = state.detailToken + 1; state.detailToken = token; state.detailController = controller;
    fetchJson(TRIAL_API + '/' + encodeURIComponent(id), controller.signal).then(function (payload) {
      if (token !== state.detailToken) return; var detail = payload && valueAt(payload, 'trial'); if (!validTrial(detail) || nctOf(detail) !== id) throw new Error('Invalid trial detail contract'); state.detail = detail; showDetail(detail, queueEvidence);
    }).catch(function (error) {
      if (token !== state.detailToken || (error && error.name === 'AbortError')) return;
      if (error && error.status === 404) showInspectorEmpty(tr('Dossier unavailable', '档案暂不可用'), tr('This trial is no longer in the current verified record. No replacement record is inferred.', '该试验已不在当前已核验记录中。不会推断替代记录。'));
      else if (isAccessError(error)) { lockWorkspace(); showInspectorEmpty(tr('Dossier locked', '档案已锁定'), tr('Full access is required before the current trial record can be shown.', '显示当前试验记录前需要完整访问权限。')); }
      else showInspectorEmpty(tr('Dossier unavailable', '档案暂不可用'), tr('Retry later. The dossier does not fill fields absent from the official record.', '请稍后重试。档案不会填补官方记录中缺失的字段。'));
    }).finally(function () { if (state.detailController === controller) state.detailController = null; });
    if (trigger) trigger.setAttribute('aria-selected', 'true');
  }

  function updateMetadata(payload) {
    var health = valueAt(payload, 'health') || {}, source = valueAt(payload, 'source') || {}, stateName = clean(valueAt(health, 'state')).toLowerCase(), asOf = clean(valueAt(payload, 'as_of')) || clean(valueAt(source, 'dataset_timestamp_raw'));
    text(ui.asOf, asOf ? tr('As of ', '截至 ') + timestampLabel(asOf) : '');
    if (stateName === 'stale') { setStatus('stale', tr('Last verified page', '最近已核验页面'), tr('Registry update in progress', '登记库正在更新')); setNotice('stale', tr('The registry update is in progress. You are reading the last verified page; check its as-of date.', '登记库更新正在进行。当前展示最近一次已核验页面；请查看其截至日期。')); }
    else if (stateName === 'unavailable') { setStatus('unavailable', tr('Freshness status unavailable', '新鲜度状态暂不可用'), tr('Showing the current verified page', '正在显示当前已核验页面')); setNotice('error', tr('The freshness check is unavailable. Read the source and retrieval dates before relying on this page.', '新鲜度检查暂不可用。使用此页面前请查看来源和获取日期。')); }
    else if (state.restarted) { setStatus('restarted', tr('Registry page restarted', '登记页面已重启'), tr('Showing the refreshed verified page', '正在显示刷新后的已核验页面')); setNotice('restart', tr('The registry generation changed while another page was loading. The monitor restarted from the current filters.', '加载另一页时登记生成发生变化。监测器已按当前筛选条件重新开始。')); }
    else { setStatus('ready', tr('Verified registry page', '已核验登记页面'), clean(valueAt(source, 'name')) || tr('Official registry source', '官方登记来源')); setNotice('', ''); }
  }
  function isAccessError(error) { return !!error && (error.status === 401 || error.status === 402 || error.status === 403); }
  function restartableAppendError(error) { return !!error && (error.status === 400 || error.status === 409); }
  function paintLockedWorkspace() {
    ui.workspace.dataset.state = 'locked'; clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'false'); ui.queueFooter.hidden = true;
    setStatus('locked', tr('Full access required', '需要完整访问权限'), tr('Sign in with an entitled account', '请使用已授权账户登录'));
    setNotice('locked', tr('Registry Milestone Monitor is available with full access. No trial records are shown until access is confirmed.', '登记里程碑监测需要完整访问权限。访问确认前不会显示试验记录。'));
    ui.queue.appendChild(emptyCard(tr('Registry records are locked', '登记记录已锁定'), tr('Sign in with full access to read registry-recorded dates.', '请以完整访问权限登录，读取登记记录日期。'), '◌'));
    announce(tr('Registry records are locked.', '登记记录已锁定。'));
  }
  function lockWorkspace() {
    abort('listController'); state.listToken += 1; abort('detailController'); state.detailToken += 1; ui.refresh.classList.remove('is-spinning');
    state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = '';
    state.selectedId = ''; state.selected = null; state.detail = null; state.appendFailed = false; state.accessLocked = true;
    paintLockedWorkspace();
  }
  function paintAppendFailure() {
    ui.workspace.dataset.state = 'append-unavailable';
    setStatus('stale', tr('Last verified page', '最近已核验页面'), tr('The next registry page could not be loaded', '无法加载下一页登记记录'));
    setNotice('stale', tr('The next registry page is unavailable. Showing last verified rows; try Load more again.', '下一页登记记录暂不可用。正在显示最近已核验行；请再次加载更多。'));
    announce(tr('The next registry page is unavailable. Last verified rows remain visible.', '下一页登记记录暂不可用。最近已核验行保持可见。'));
    renderQueue();
    if (!ui.queueFooter.hidden && document.activeElement === ui.loadMore) ui.loadMore.focus({ preventScroll: true });
  }
  function preserveAppendFailure() {
    state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.appendFailed = true; state.accessLocked = false;
    paintAppendFailure();
  }
  function paintUnavailableWorkspace() {
    ui.workspace.dataset.state = 'unavailable'; clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'false'); ui.queueFooter.hidden = true;
    setStatus('unavailable', tr('Registry page unavailable', '登记页面暂不可用'), tr('No dates are inferred', '不会推断日期'));
    setNotice('error', tr('The verified registry page is temporarily unavailable. No trial records are shown.', '已核验登记页面暂不可用。不会显示试验记录。'));
    ui.queue.appendChild(emptyCard(tr('Registry page unavailable', '登记页面暂不可用'), tr('Retry the source request. This monitor does not estimate unrecorded dates.', '请重试来源请求。此监测器不会估计未记录日期。'), '×', true));
    announce(tr('Registry page unavailable.', '登记页面暂不可用。'));
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a registry milestone when the current page is available.', '当前页面可用后，请选择一项登记里程碑。'));
  }
  function handleUnavailable(error, options) {
    options = options || {};
    if (isAccessError(error)) {
      lockWorkspace();
      showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a registry milestone when full access is confirmed.', '完整访问权限确认后，请选择一项登记里程碑。'));
      return;
    }
    if (options.append && state.rows.length) { preserveAppendFailure(); return; }
    state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = ''; state.appendFailed = false; state.accessLocked = false;
    paintUnavailableWorkspace();
  }
  function loadMilestones(options) {
    options = options || {}; var append = options.append === true, cursor = append ? state.nextCursor : '';
    if (append && (!cursor || state.pageLoading)) return;
    abort('listController'); var controller = new AbortController(), token = state.listToken + 1; state.listToken = token; state.listController = controller;
    state.loading = !append; state.pageLoading = append;
    if (!append) {
      state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = ''; state.appendFailed = false; state.accessLocked = false; if (!options.restarted) state.restarted = false;
      ui.workspace.dataset.state = options.restarted ? 'generation-restarted' : (state.hasLoaded ? 'loading' : 'first-load'); loadingQueue(false);
      text(ui.subtitle, tr('Retrieving the verified registry page…', '正在获取已核验登记页面…')); setStatus('ready', tr('Retrieving registry records', '正在获取登记记录'), tr('No records are in this page shell', '此页面外壳不含记录'));
    } else {
      ui.workspace.dataset.state = 'page-loading'; loadingQueue(true); announce(tr('Loading more registry-recorded dates.', '正在加载更多登记记录日期。'));
    }
    ui.refresh.classList.add('is-spinning');
    fetchJson(queryUrl(cursor), controller.signal).then(function (payload) {
      if (token !== state.listToken) return; validateMilestoneEnvelope(payload);
      var incomingGeneration = generationKey(payload);
      if (append && state.generation && incomingGeneration !== state.generation) {
        state.restarted = true; announce(tr('The registry page changed. Reloading the selected filters.', '登记页面已变化。正在重新加载所选筛选条件。'));
        loadMilestones({ replace: true, restarted: true }); return;
      }
      var existingRows = append ? state.rows : [], rows = validateMilestonePage(payload.milestones, existingRows), pagination = payload.pagination;
      validateMilestonePagination(payload, existingRows, cursor, append ? state.payload : null);
      if (append) state.rows = state.rows.concat(rows); else state.rows = rows;
      state.payload = payload; state.generation = incomingGeneration; state.nextCursor = clean(valueAt(pagination, 'next_cursor')); state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.appendFailed = false; state.accessLocked = false;
      ui.workspace.dataset.state = state.restarted ? 'generation-restarted' : (state.rows.length ? 'ready' : 'empty'); updateMetadata(payload); setSubtitle(payload); renderQueue();
      announce(state.rows.length ? tr('Loaded ' + state.rows.length + ' registry-recorded dates.', '已加载' + state.rows.length + '项登记记录日期。') : tr('No registry-recorded dates match these filters.', '没有登记记录日期匹配这些筛选条件。'));
      if (!append && state.selectedId) {
        var selectedRow = state.rows.filter(function (item) { return nctOf(item.trial) === state.selectedId; })[0];
        selectTrial(state.selectedId, selectedRow && selectedRow.trial, selectedRow && selectedRow.evidence, false);
      }
    }).catch(function (error) {
      if (token !== state.listToken || (error && error.name === 'AbortError')) return;
      if (append && restartableAppendError(error)) {
        state.restarted = true;
        announce(tr('The registry page changed. Reloading the selected filters.', '登记页面已变化。正在重新加载所选筛选条件。'));
        loadMilestones({ replace: true, restarted: true });
        return;
      }
      handleUnavailable(error, { append: append });
    }).finally(function () {
      if (state.listController === controller) state.listController = null;
      if (token === state.listToken) { ui.refresh.classList.remove('is-spinning'); state.loading = false; state.pageLoading = false; if (state.rows.length && !state.accessLocked) renderQueue(); }
    });
  }
  function applyFilters() {
    state.filters.field = ui.field.value;
    state.filters.q = clean(ui.search.value).slice(0, 100);
    state.filters.phase = clean(ui.phase.value).slice(0, 40);
    state.filters.status = clean(ui.statusFilter.value).slice(0, 40);
    state.filters.condition = clean(ui.condition.value).slice(0, 100);
    closeInspector({ restoreFocus: false, writeUrl: false, render: false }); writeUrl(); loadMilestones({ replace: true });
  }
  function setWindow(value) {
    if (!WINDOW_VALUES[value] || state.filters.window === value) return;
    state.filters.window = value; syncControls(); applyFilters();
  }
  function openBrain() {
    if (window.MMBrain && typeof window.MMBrain.open === 'function') { window.MMBrain.open(); return; }
    setNotice('error', tr('Mastermind is unavailable right now. Your registry filters remain unchanged.', '操盘大脑暂不可用。你的登记筛选条件保持不变。'));
  }
  function bindEvents() {
    var debounceId = 0;
    ui.search.addEventListener('input', function () { window.clearTimeout(debounceId); debounceId = window.setTimeout(applyFilters, 260); });
    ui.condition.addEventListener('input', function () { window.clearTimeout(debounceId); debounceId = window.setTimeout(applyFilters, 260); });
    [ui.field, ui.phase, ui.statusFilter].forEach(function (node) { node.addEventListener('change', applyFilters); });
    ui.windowButtons.forEach(function (button) { button.addEventListener('click', function () { setWindow(button.getAttribute('data-window')); }); });
    ui.windowControl.addEventListener('keydown', function (event) {
      if (['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].indexOf(event.key) < 0) return;
      var active = ui.windowButtons.map(function (button) { return button.getAttribute('data-window'); }).indexOf(state.filters.window), direction = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : -1, target;
      if (event.key === 'Home') target = 0; else if (event.key === 'End') target = ui.windowButtons.length - 1; else target = (active + direction + ui.windowButtons.length) % ui.windowButtons.length;
      event.preventDefault(); ui.windowButtons[target].focus(); setWindow(ui.windowButtons[target].getAttribute('data-window'));
    });
    ui.clear.addEventListener('click', function () { state.filters = { field: 'primary_completion', window: '90', q: '', phase: '', status: '', condition: '' }; syncControls(); applyFilters(); ui.search.focus(); });
    ui.brainLaunch.addEventListener('click', openBrain);
    ui.refresh.addEventListener('click', function () { loadMilestones({ replace: true }); });
    ui.loadMore.addEventListener('click', function () { loadMilestones({ append: true }); });
    ui.inspectorClose.addEventListener('click', closeInspector); ui.scrim.addEventListener('click', closeInspector);
    ui.queue.addEventListener('keydown', function (event) { if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return; var rows = Array.prototype.slice.call(ui.queue.querySelectorAll('.bci-trial')), current = rows.indexOf(document.activeElement); if (!rows.length) return; event.preventDefault(); var next = current < 0 ? 0 : (current + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length; rows[next].focus(); });
    document.addEventListener('keydown', function (event) { trapInspectorFocus(event); if (event.key === 'Escape' && ui.inspector.classList.contains('is-open')) closeInspector(); });
    document.addEventListener('langchange', function () {
      localizeControls();
      if (state.accessLocked) { paintLockedWorkspace(); showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a registry milestone when full access is confirmed.', '完整访问权限确认后，请选择一项登记里程碑。')); return; }
      if (ui.workspace.dataset.state === 'unavailable') { paintUnavailableWorkspace(); return; }
      if (state.appendFailed) paintAppendFailure();
      else if (state.payload) { updateMetadata(state.payload); setSubtitle(state.payload); renderQueue(); }
      else if (state.loading) { text(ui.subtitle, tr('Retrieving the verified registry page…', '正在获取已核验登记页面…')); setStatus('ready', tr('Retrieving registry records', '正在获取登记记录'), tr('No records are in this page shell', '此页面外壳不含记录')); }
      if (state.detail) { var selectedRow = state.rows.filter(function (item) { return nctOf(item.trial) === state.selectedId; })[0]; showDetail(state.detail, selectedRow && selectedRow.evidence); }
      else if (state.detailController && ui.inspector.classList.contains('is-open')) detailLoading();
    });
    window.addEventListener('popstate', function () { abort('listController'); closeInspector({ restoreFocus: false, writeUrl: false, render: false }); readUrl(); syncControls(); loadMilestones({ replace: true }); });
    window.addEventListener('resize', syncInspectorDialog);
  }
  function init() {
    cacheUi(); readUrl(); localizeControls(); syncControls(); bindEvents();
    writeUrl();
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a registry milestone to read the current trial record and its source receipt.', '选择一项登记里程碑，查看当前试验记录及其来源凭证。'));
    loadMilestones({ replace: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

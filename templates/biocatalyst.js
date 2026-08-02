(function () {
  'use strict';

  var MILESTONE_API = '/api/biocatalyst/v1/trials/milestones';
  var CHANGE_API = '/api/biocatalyst/v1/trials/changes';
  var PROSPECTIVE_API = '/api/biocatalyst/v1/trials/prospective-changes';
  var TRIAL_API = '/api/biocatalyst/v1/trials';
  var TRIAL_ID = /^NCT\d{8}$/;
  var DATE_PARTS = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/;
  var WINDOW_VALUES = { '30': true, '90': true, '180': true, all: true };
  var MILESTONE_WINDOWS = { '30': 'next_30d', '90': 'next_90d', '180': 'next_180d', all: 'all' };
  var FIELD_VALUES = { primary_completion: true, completion: true };
  var CHANGE_KIND_VALUES = {
    endpoint_added: true, endpoint_removed: true, endpoint_role_changed: true,
    endpoint_measure_changed: true, endpoint_time_frame_changed: true,
    endpoint_description_changed: true, enrollment_changed: true,
    registry_status_changed: true, study_date_changed: true,
    site_listing_changed: true, lead_sponsor_text_changed: true,
    intervention_added: true, intervention_removed: true, intervention_changed: true
  };
  var PROSPECTIVE_CHANGE_KIND_VALUES = {
    registry_status: true, enrollment_target: true, enrollment_actual: true, enrollment_count: true,
    enrollment_type: true, primary_completion_date: true, completion_date: true, site_set: true, endpoint_record: true
  };
  var CHANGE_KIND_CATALOG = [
    { label: ['Endpoints', '终点'], items: [
      ['endpoint_added', 'Endpoint added', '新增终点'],
      ['endpoint_removed', 'Endpoint removed', '移除终点'],
      ['endpoint_role_changed', 'Endpoint role updated', '终点角色更新'],
      ['endpoint_measure_changed', 'Endpoint measure updated', '终点指标更新'],
      ['endpoint_time_frame_changed', 'Endpoint timeframe updated', '终点时间范围更新'],
      ['endpoint_description_changed', 'Endpoint description updated', '终点说明更新']
    ] },
    { label: ['Study record', '研究记录'], items: [
      ['enrollment_changed', 'Enrollment record updated', '入组记录更新'],
      ['registry_status_changed', 'Registry status updated', '登记状态更新'],
      ['study_date_changed', 'Study date record updated', '研究日期记录更新'],
      ['site_listing_changed', 'Site listing updated', '研究中心列表更新'],
      ['lead_sponsor_text_changed', 'Lead sponsor text updated', '牵头申办方文字更新'],
      ['intervention_added', 'Intervention added', '新增干预措施'],
      ['intervention_removed', 'Intervention removed', '移除干预措施'],
      ['intervention_changed', 'Intervention record updated', '干预措施记录更新']
    ] }
  ];
  var PROSPECTIVE_CHANGE_KIND_CATALOG = [
    { label: ['Observed record', '观测记录'], items: [
      ['registry_status', 'Registry status record', '登记状态记录'],
      ['enrollment_target', 'Enrollment target record', '入组目标记录'],
      ['enrollment_actual', 'Actual enrollment record', '实际入组记录'],
      ['enrollment_count', 'Enrollment count record', '入组数量记录'],
      ['enrollment_type', 'Enrollment type record', '入组类型记录'],
      ['primary_completion_date', 'Primary completion date record', '主要完成日期记录'],
      ['completion_date', 'Completion date record', '完成日期记录'],
      ['site_set', 'Study site record', '研究地点记录'],
      ['endpoint_record', 'Endpoint record', '终点记录']
    ] }
  ];
  var CHANGE_WINDOWS = { '30': 'last_30d', '90': 'last_90d', '180': 'last_180d', all: 'all' };
  var PROSPECTIVE_WINDOWS = { '30': 'last_30d', '90': 'last_90d', '180': 'last_180d', all: 'all' };
  var MODE_VALUES = { milestones: true, changes: true, prospective: true };
  var AUTHORITY_ALLOWED_USES = ['display', 'context', 'explain'];
  var AUTHORITY_FORBIDDEN_USES = ['originate_signal', 'rank_security', 'select_security', 'size_position', 'gate_decision', 'execute_trade', 'raise_authority'];
  var PAGE_LIMIT = 50;
  var state = {
    payload: null,
    rows: [],
    nextCursor: '',
    selectedId: '',
    selectedKey: '',
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
    mode: 'milestones',
    filters: { field: 'primary_completion', change_kind: '', prospective_change_kind: '', window: '90', q: '', phase: '', status: '', condition: '' }
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
    ui.windowLabel = byId('bci-window-label');
    ui.windowButtons = Array.prototype.slice.call(document.querySelectorAll('.bci-window'));
    ui.field = byId('bci-field-filter');
    ui.fieldControl = byId('bci-field-control');
    ui.changeKind = byId('bci-change-kind-filter');
    ui.changeKindControl = byId('bci-change-kind-control');
    ui.changeKindLabel = byId('bci-change-kind-label');
    ui.modeControl = byId('bci-mode-control');
    ui.modeButtons = Array.prototype.slice.call(document.querySelectorAll('.bci-mode'));
    ui.queuePane = byId('bci-queue-pane');
    ui.search = byId('bci-search');
    ui.phase = byId('bci-phase-filter');
    ui.statusFilter = byId('bci-status-filter');
    ui.condition = byId('bci-condition-filter');
    ui.clear = byId('bci-clear');
    ui.brainLaunch = byId('bci-brain-launch');
    ui.subtitle = byId('bci-queue-subtitle');
    ui.queueKicker = byId('bci-queue-kicker');
    ui.queueTitle = byId('bci-queue-title');
    ui.sourceNote = byId('bci-source-note-copy');
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
  function observationTimestampLabel(value) {
    var raw = clean(value);
    if (!fullTimestamp(raw) || raw.slice(-1) !== 'Z') return raw || tr('Not recorded', '未记录');
    return raw.slice(0, -1).replace('T', ' ') + ' UTC';
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
  function isChangeMode() { return state.mode === 'changes'; }
  function isProspectiveMode() { return state.mode === 'prospective'; }
  function activeChangeKind() { return isProspectiveMode() ? state.filters.prospective_change_kind : state.filters.change_kind; }
  function activeChangeKindValues() { return isProspectiveMode() ? PROSPECTIVE_CHANGE_KIND_VALUES : CHANGE_KIND_VALUES; }
  function activeChangeKindCatalog() { return isProspectiveMode() ? PROSPECTIVE_CHANGE_KIND_CATALOG : CHANGE_KIND_CATALOG; }
  function setActiveChangeKind(value) {
    value = clean(value);
    if (isProspectiveMode()) state.filters.prospective_change_kind = activeChangeKindValues()[value] ? value : '';
    else state.filters.change_kind = activeChangeKindValues()[value] ? value : '';
  }
  function activeApi() { return isProspectiveMode() ? PROSPECTIVE_API : (isChangeMode() ? CHANGE_API : MILESTONE_API); }
  function activeWindow() { return isProspectiveMode() ? PROSPECTIVE_WINDOWS[state.filters.window] : (isChangeMode() ? CHANGE_WINDOWS[state.filters.window] : MILESTONE_WINDOWS[state.filters.window]); }
  function activeNoun() {
    if (isProspectiveMode()) return tr('first-seen observations', '首次观测记录');
    return isChangeMode() ? tr('registry field updates', '登记字段更新') : tr('registry milestones', '登记里程碑');
  }
  function activeSingularNoun() {
    if (isProspectiveMode()) return tr('first-seen observation', '首次观测记录');
    return isChangeMode() ? tr('registry field update', '登记字段更新') : tr('registry milestone', '登记里程碑');
  }
  function modeTitle() {
    if (isProspectiveMode()) return tr('First-seen Tape', '首次观测记录');
    return isChangeMode() ? tr('Change Tape', '变更记录') : tr('Milestone monitor', '里程碑监测');
  }
  function modeKicker() {
    if (isProspectiveMode()) return tr('Observed between successful polls', '成功轮询之间的观测');
    return isChangeMode() ? tr('Exact registry updates', '精确登记更新') : tr('Registry-recorded dates', '登记记录日期');
  }
  function defaultFilters() { return { field: 'primary_completion', change_kind: '', prospective_change_kind: '', window: '90', q: '', phase: '', status: '', condition: '' }; }
  function validAuthority(authority) {
    return !!authority && typeof authority === 'object' && authority.classification === 'source_fact' && authority.decision_authority === false &&
      Object.keys(authority).sort().join('|') === 'allowed_uses|classification|decision_authority|forbidden_uses' &&
      JSON.stringify(authority.allowed_uses) === JSON.stringify(AUTHORITY_ALLOWED_USES) &&
      JSON.stringify(authority.forbidden_uses) === JSON.stringify(AUTHORITY_FORBIDDEN_USES);
  }
  function safeJson(value, depth) {
    depth = depth || 0;
    if (depth > 12 || value === null || typeof value === 'boolean') return depth <= 12;
    if (typeof value === 'number') return Number.isFinite(value);
    if (typeof value === 'string') return Array.from(value).length <= 12000;
    if (Array.isArray(value)) return value.length <= 200 && value.every(function (item) { return safeJson(item, depth + 1); });
    if (!value || typeof value !== 'object' || Object.keys(value).length > 100) return false;
    return Object.keys(value).every(function (key) { return Array.from(key).length <= 256 && safeJson(value[key], depth + 1); });
  }
  function fullTimestamp(value) { return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value)); }
  function exactHistoryUrl(value, id, version) {
    var expected = 'https://clinicaltrials.gov/study/' + encodeURIComponent(id) + '?a=' + String(version) + '&tab=history';
    return clean(value) === expected;
  }
  function exactHistoryRootUrl(value, id) { return clean(value) === 'https://clinicaltrials.gov/study/' + encodeURIComponent(id) + '?tab=history'; }

  function validMeta(payload) {
    return !!payload && typeof payload === 'object' && payload.schema_version === 'biocatalyst_api.v1' &&
      payload.source && typeof payload.source === 'object' && payload.health && typeof payload.health === 'object' &&
      payload.coverage && typeof payload.coverage === 'object' && validAuthority(payload.authority);
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
  function validChangeEvidence(evidence, id, afterVersion) {
    return !!evidence && typeof evidence === 'object' && clean(valueAt(evidence, 'provider')) === 'ClinicalTrials.gov' &&
      clean(valueAt(evidence, 'record_id')) === id && exactHistoryUrl(valueAt(evidence, 'version_url'), id, afterVersion) &&
      exactHistoryRootUrl(valueAt(evidence, 'history_url'), id) && fullTimestamp(valueAt(evidence, 'retrieved_at')) &&
      clean(valueAt(evidence, 'coverage')) === 'record_history_complete';
  }
  function validRegistryChange(change) {
    var before = valueAt(change, 'before_display_version'), after = valueAt(change, 'after_display_version'), changes = valueAt(change, 'changes'), shown = valueAt(change, 'shown_change_count'), total = valueAt(change, 'total_display_safe_changes');
    return !!change && typeof change === 'object' && Number.isSafeInteger(before) && before >= 1 && Number.isSafeInteger(after) && after > before &&
      fullDate(valueAt(change, 'source_submitted_at')) && clean(valueAt(change, 'interpretation')) === 'registry_record_changed' &&
      valueAt(change, 'protocol_change_asserted') === false && valueAt(change, 'materiality_assessed') === false &&
      Number.isSafeInteger(total) && total >= 1 && Number.isSafeInteger(shown) && shown >= 1 && shown <= total &&
      Array.isArray(changes) && changes.length === shown && changes.length <= 2000 && changes.every(function (item) {
        return !!item && typeof item === 'object' && CHANGE_KIND_VALUES[clean(valueAt(item, 'kind'))] === true && safeJson(valueAt(item, 'before_value')) && safeJson(valueAt(item, 'after_value'));
      });
  }
  function validChange(item) {
    var trial = valueAt(item, 'trial'), registryChange = valueAt(item, 'registry_change');
    return !!item && typeof item === 'object' && validTrial(trial) && validRegistryChange(registryChange) &&
      validChangeEvidence(valueAt(item, 'evidence'), nctOf(trial), valueAt(registryChange, 'after_display_version')) && validAuthority(valueAt(item, 'authority'));
  }
  function validateChangeEnvelope(payload) {
    var pagination = valueAt(payload, 'pagination'), query = valueAt(payload, 'query'), historyCoverage = valueAt(payload, 'history_coverage'), window = valueAt(payload, 'effective_window');
    if (!validMeta(payload) || !Array.isArray(payload.changes) || !pagination || typeof pagination !== 'object' || !query || typeof query !== 'object' || !window || typeof window !== 'object' || !historyCoverage || typeof historyCoverage !== 'object') throw new Error('Invalid change list contract');
    if (pagination.limit !== PAGE_LIMIT || !Number.isSafeInteger(pagination.total) || pagination.total < 0 || (pagination.next_cursor != null && (typeof pagination.next_cursor !== 'string' || !/^[A-Za-z0-9_-]{1,384}$/.test(pagination.next_cursor)))) throw new Error('Invalid change pagination contract');
    var knowledgeCutoff = valueAt(historyCoverage, 'knowledge_cutoff'), payloadAsOf = valueAt(payload, 'as_of');
    if (!fullTimestamp(payloadAsOf) || clean(valueAt(historyCoverage, 'class')) !== 'record_history_complete' || clean(valueAt(historyCoverage, 'selection_basis')) !== 'current_trial_record' || !Number.isSafeInteger(valueAt(historyCoverage, 'available_trials')) || valueAt(historyCoverage, 'available_trials') < 0 || !Number.isSafeInteger(valueAt(historyCoverage, 'unavailable_trials')) || valueAt(historyCoverage, 'unavailable_trials') < 0 || (knowledgeCutoff != null && (!fullTimestamp(knowledgeCutoff) || Date.parse(knowledgeCutoff) > Date.parse(payloadAsOf)))) throw new Error('Invalid change coverage contract');
    if (!changeQueryMatchesCurrentFilters(query) || !effectiveChangeWindowIsSane(window, clean(valueAt(query, 'window')))) throw new Error('Change query binding mismatch');
  }
  function validProspectiveEvidence(evidence, id, observedAt) {
    var expected = 'https://clinicaltrials.gov/study/' + encodeURIComponent(id);
    return !!evidence && typeof evidence === 'object' && clean(valueAt(evidence, 'provider')) === 'ClinicalTrials.gov' &&
      clean(valueAt(evidence, 'record_id')) === id && clean(valueAt(evidence, 'url')) === expected &&
      fullTimestamp(valueAt(evidence, 'retrieved_at')) && clean(valueAt(evidence, 'retrieved_at')) === observedAt && clean(valueAt(evidence, 'coverage')) === 'current_only';
  }
  function validObservedInterval(interval, observedAt) {
    var after = valueAt(interval, 'after'), atOrBefore = valueAt(interval, 'at_or_before');
    return !!interval && typeof interval === 'object' && Object.keys(interval).sort().join('|') === 'after|at_or_before' &&
      fullTimestamp(after) && fullTimestamp(atOrBefore) && clean(atOrBefore) === observedAt && Date.parse(after) < Date.parse(atOrBefore);
  }
  function validProspectiveChange(change) {
    var observedAt = clean(valueAt(change, 'first_observed_at')), interval = valueAt(change, 'observed_interval'), changes = valueAt(change, 'changes'), shown = valueAt(change, 'display_change_count'), total = valueAt(change, 'total_exact_operation_count'), omitted = valueAt(change, 'omitted_operation_count'), changeId = clean(valueAt(change, 'change_id'));
    return !!change && typeof change === 'object' && /^[A-Za-z0-9_-]{16,160}$/.test(changeId) && fullTimestamp(observedAt) && validObservedInterval(interval, observedAt) &&
      clean(valueAt(change, 'observation_basis')) === 'first_observed_between_successful_polls' && clean(valueAt(change, 'interpretation')) === 'registry_record_changed' && valueAt(change, 'protocol_change_asserted') === false && valueAt(change, 'materiality_assessed') === false &&
      Number.isSafeInteger(total) && total >= 1 && Number.isSafeInteger(shown) && shown >= 0 && shown <= total && Number.isSafeInteger(omitted) && omitted >= 0 &&
      total === shown + omitted && Array.isArray(changes) && changes.length === shown && changes.length <= 128 && changes.every(function (item) {
        var operation = clean(valueAt(item, 'op')), states = { add: ['missing', 'present'], remove: ['present', 'missing'], replace: ['present', 'present'] }[operation];
        return !!item && typeof item === 'object' && PROSPECTIVE_CHANGE_KIND_VALUES[clean(valueAt(item, 'kind'))] === true && !!states &&
          clean(valueAt(item, 'before_state')) === states[0] && clean(valueAt(item, 'after_state')) === states[1] &&
          (states[0] !== 'missing' || valueAt(item, 'before_value') === null) && (states[1] !== 'missing' || valueAt(item, 'after_value') === null) && safeJson(valueAt(item, 'before_value')) && safeJson(valueAt(item, 'after_value'));
      });
  }
  function validProspectiveChangeItem(item) {
    var trial = valueAt(item, 'trial'), prospectiveChange = valueAt(item, 'prospective_change');
    return !!item && typeof item === 'object' && validTrial(trial) && validProspectiveChange(prospectiveChange) &&
      validProspectiveEvidence(valueAt(item, 'evidence'), nctOf(trial), clean(valueAt(prospectiveChange, 'first_observed_at'))) &&
      new RegExp('^prospective_change_' + nctOf(trial) + '_[a-f0-9]{24}$').test(clean(valueAt(prospectiveChange, 'change_id'))) && validAuthority(valueAt(item, 'authority'));
  }
  function prospectiveQueryMatchesCurrentFilters(query) {
    if (!query || typeof query !== 'object') return false;
    var expected = { change_kind: activeChangeKind() || 'all', window: PROSPECTIVE_WINDOWS[state.filters.window], q: state.filters.q, phase: state.filters.phase, status: state.filters.status, condition: state.filters.condition };
    return Object.keys(expected).every(function (key) {
      var expectedValue = expected[key], actualValue = valueAt(query, key);
      if (!expectedValue) return actualValue == null || clean(actualValue) === '';
      return normalizedQueryValue(actualValue) === normalizedQueryValue(expectedValue);
    });
  }
  function effectiveProspectiveWindowIsSane(window, apiWindow) {
    if (!window || typeof window !== 'object') return false;
    var from = clean(valueAt(window, 'from_date')), to = clean(valueAt(window, 'to_date')), anchor = clean(valueAt(window, 'anchor_date')), anchorAt = clean(valueAt(window, 'anchor_at'));
    if (clean(valueAt(window, 'date_basis')) !== 'observation_at_or_before_utc') return false;
    if (!fullTimestamp(anchorAt)) return false;
    if (apiWindow === 'all') return fullDate(anchor) && (!from || fullDate(from)) && (!to || fullDate(to)) && (!from || !to || from <= to);
    return fullDate(from) && fullDate(to) && fullDate(anchor) && anchor === to && from <= to;
  }
  function validateProspectiveEnvelope(payload) {
    var pagination = valueAt(payload, 'pagination'), query = valueAt(payload, 'query'), coverage = valueAt(payload, 'prospective_coverage'), window = valueAt(payload, 'effective_window'), payloadAsOf = valueAt(payload, 'as_of');
    if (!validMeta(payload) || !Array.isArray(payload.prospective_changes) || !pagination || typeof pagination !== 'object' || !query || typeof query !== 'object' || !window || typeof window !== 'object' || !coverage || typeof coverage !== 'object') throw new Error('Invalid prospective list contract');
    if (pagination.limit !== PAGE_LIMIT || !Number.isSafeInteger(pagination.total) || pagination.total < 0 || (pagination.next_cursor != null && (typeof pagination.next_cursor !== 'string' || !/^[A-Za-z0-9_-]{1,384}$/.test(pagination.next_cursor)))) throw new Error('Invalid prospective pagination contract');
    var coverageState = clean(valueAt(coverage, 'coverage_state')), coverageStarted = valueAt(coverage, 'coverage_started_at'), lastObserved = valueAt(coverage, 'last_observed_at');
    if (!fullTimestamp(payloadAsOf) || clean(valueAt(coverage, 'class')) !== 'prospective_current_only' || clean(valueAt(coverage, 'selection_basis')) !== 'current_trial_record' || ['active', 'pre_baseline', 'unavailable'].indexOf(coverageState) < 0 || !Number.isSafeInteger(valueAt(coverage, 'active_trials')) || valueAt(coverage, 'active_trials') < 0 || !Number.isSafeInteger(valueAt(coverage, 'pre_baseline_trials')) || valueAt(coverage, 'pre_baseline_trials') < 0 || !Number.isSafeInteger(valueAt(coverage, 'unavailable_trials')) || valueAt(coverage, 'unavailable_trials') < 0 || ((coverageState === 'unavailable') ? ((coverageStarted != null && !fullTimestamp(coverageStarted)) || (lastObserved != null && !fullTimestamp(lastObserved))) : (!fullTimestamp(coverageStarted) || !fullTimestamp(lastObserved) || Date.parse(coverageStarted) > Date.parse(lastObserved)))) throw new Error('Invalid prospective coverage contract');
    if (!prospectiveQueryMatchesCurrentFilters(query) || !effectiveProspectiveWindowIsSane(window, clean(valueAt(query, 'window')))) throw new Error('Prospective query binding mismatch');
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
  function changeQueryMatchesCurrentFilters(query) {
    if (!query || typeof query !== 'object') return false;
    var expected = {
      change_kind: state.filters.change_kind || 'all',
      window: CHANGE_WINDOWS[state.filters.window],
      q: state.filters.q,
      phase: state.filters.phase,
      status: state.filters.status,
      condition: state.filters.condition
    };
    return Object.keys(expected).every(function (key) {
      var expectedValue = expected[key], actualValue = valueAt(query, key);
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
  function effectiveChangeWindowIsSane(window, apiWindow) {
    if (!window || typeof window !== 'object') return false;
    var from = clean(valueAt(window, 'from_date')), to = clean(valueAt(window, 'to_date')), anchor = clean(valueAt(window, 'anchor_date'));
    if (clean(valueAt(window, 'date_basis')) !== 'source_submitted_at') return false;
    if (apiWindow === 'all') return fullDate(anchor) && (!from || fullDate(from)) && (!to || fullDate(to)) && (!from || !to || from <= to);
    return fullDate(from) && fullDate(to) && fullDate(anchor) && anchor === to && from <= to;
  }
  function validateMilestoneEnvelope(payload) {
    if (!validEnvelope(payload)) throw new Error('Invalid milestone list contract');
    var query = valueAt(payload, 'query');
    if (!queryMatchesCurrentFilters(query)) throw new Error('Milestone query binding mismatch');
    if (!effectiveWindowIsSane(valueAt(payload, 'effective_window'), clean(valueAt(query, 'window')))) throw new Error('Invalid effective registry window');
  }
  function changeIdentity(item) {
    var registryChange = valueAt(item, 'registry_change');
    return nctOf(valueAt(item, 'trial')) + '|' + valueAt(registryChange, 'before_display_version') + '|' + valueAt(registryChange, 'after_display_version') + '|' + clean(valueAt(registryChange, 'source_submitted_at'));
  }
  function validateChangePage(items, existingRows) {
    if (!Array.isArray(items)) throw new Error('Invalid change page');
    var seen = {};
    arr(existingRows).forEach(function (item) { seen[changeIdentity(item)] = true; });
    return items.map(function (item) {
      if (!validChange(item)) throw new Error('Invalid registry change record');
      var identity = changeIdentity(item);
      if (seen[identity]) throw new Error('Duplicate registry change identity');
      seen[identity] = true;
      return item;
    });
  }
  function prospectiveIdentity(item) {
    var prospectiveChange = valueAt(item, 'prospective_change');
    return nctOf(valueAt(item, 'trial')) + '|' + clean(valueAt(prospectiveChange, 'change_id'));
  }
  function validateProspectivePage(items, existingRows) {
    if (!Array.isArray(items)) throw new Error('Invalid prospective page');
    var seen = {};
    arr(existingRows).forEach(function (item) { seen[prospectiveIdentity(item)] = true; });
    return items.map(function (item) {
      if (!validProspectiveChangeItem(item)) throw new Error('Invalid prospective observation record');
      var identity = prospectiveIdentity(item);
      if (seen[identity]) throw new Error('Duplicate prospective observation identity');
      seen[identity] = true;
      return item;
    });
  }
  function validateProspectivePagination(payload, existingRows, requestedCursor, previousPayload) {
    var pagination = valueAt(payload, 'pagination'), previous = valueAt(previousPayload, 'pagination');
    var pageSize = payload.prospective_changes.length, loadedBefore = arr(existingRows).length, loadedAfter = loadedBefore + pageSize;
    var total = pagination.total, nextCursor = clean(pagination.next_cursor), previousTotal = valueAt(previous, 'total');
    if (pageSize > pagination.limit || loadedAfter > total) throw new Error('Invalid prospective page bounds');
    if (total > loadedBefore && pageSize === 0) throw new Error('Empty prospective page before total');
    if (nextCursor && loadedAfter >= total) throw new Error('Unexpected prospective cursor');
    if (!nextCursor && loadedAfter !== total) throw new Error('Incomplete prospective pagination');
    if (requestedCursor && nextCursor === requestedCursor) throw new Error('Repeated prospective cursor');
    if (loadedBefore && (!Number.isSafeInteger(previousTotal) || previousTotal !== total)) throw new Error('Prospective total changed during pagination');
  }
  function milestoneIdentity(item) {
    return nctOf(valueAt(item, 'trial')) + '|' + milestoneKindOf(valueAt(item, 'registry_milestone')) + '|' + clean(valueAt(valueAt(item, 'registry_milestone'), 'date'));
  }
  function rowIdentity(item) { return isProspectiveMode() ? prospectiveIdentity(item) : (isChangeMode() ? changeIdentity(item) : milestoneIdentity(item)); }
  function selectedRow() {
    return state.rows.filter(function (item) { return state.selectedKey && rowIdentity(item) === state.selectedKey; })[0] ||
      state.rows.filter(function (item) { return nctOf(item.trial) === state.selectedId; })[0];
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
  function validateChangePagination(payload, existingRows, requestedCursor, previousPayload) {
    var pagination = valueAt(payload, 'pagination'), previous = valueAt(previousPayload, 'pagination');
    var pageSize = payload.changes.length, loadedBefore = arr(existingRows).length, loadedAfter = loadedBefore + pageSize;
    var total = pagination.total, nextCursor = clean(pagination.next_cursor), previousTotal = valueAt(previous, 'total');
    if (pageSize > pagination.limit || loadedAfter > total) throw new Error('Invalid registry change page bounds');
    if (total > loadedBefore && pageSize === 0) throw new Error('Empty registry change page before total');
    if (nextCursor && loadedAfter >= total) throw new Error('Unexpected registry change cursor');
    if (!nextCursor && loadedAfter !== total) throw new Error('Incomplete registry change pagination');
    if (requestedCursor && nextCursor === requestedCursor) throw new Error('Repeated registry change cursor');
    if (loadedBefore && (!Number.isSafeInteger(previousTotal) || previousTotal !== total)) throw new Error('Registry change total changed during pagination');
  }
  function generationKey(payload) {
    var source = valueAt(payload, 'source') || {}, health = valueAt(payload, 'health') || {}, coverage = valueAt(payload, 'coverage') || {};
    return [clean(valueAt(payload, 'as_of')), clean(valueAt(source, 'dataset_timestamp_raw')), clean(valueAt(health, 'last_success_at')), clean(valueAt(coverage, 'class')), valueAt(coverage, 'configured'), valueAt(coverage, 'observed')].join('|');
  }

  function readUrl() {
    var params = new URLSearchParams(window.location.search), field = clean(params.get('field')), windowName = clean(params.get('window')), changeKind = clean(params.get('change_kind')), mode = clean(params.get('mode'));
    state.mode = MODE_VALUES[mode] ? mode : 'milestones';
    state.filters.field = FIELD_VALUES[field] ? field : 'primary_completion';
    state.filters.change_kind = state.mode === 'changes' && CHANGE_KIND_VALUES[changeKind] ? changeKind : '';
    state.filters.prospective_change_kind = state.mode === 'prospective' && PROSPECTIVE_CHANGE_KIND_VALUES[changeKind] ? changeKind : '';
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
    assign('mode', state.mode === 'milestones' ? '' : state.mode, true);
    assign('field', state.filters.field, true);
    assign('change_kind', (isChangeMode() || isProspectiveMode()) ? activeChangeKind() : '', true);
    assign('window', state.filters.window, true);
    assign('q', state.filters.q, true);
    assign('phase', state.filters.phase, true);
    assign('status', state.filters.status, true);
    assign('condition', state.filters.condition, true);
    window.history.replaceState(null, '', url.pathname + (params.toString() ? '?' + params.toString() : '') + url.hash);
  }
  function paintChangeKindOptions() {
    var allLabel = isProspectiveMode() ? tr('All observed fields', '所有观测字段') : tr('All display-safe fields', '所有可展示字段');
    clearChildren(ui.changeKind);
    ui.changeKind.appendChild(el('option', '', allLabel));
    activeChangeKindCatalog().forEach(function (section) {
      var group = document.createElement('optgroup');
      group.label = tr(section.label[0], section.label[1]);
      section.items.forEach(function (item) {
        var option = el('option', '', tr(item[1], item[2]));
        option.value = item[0];
        group.appendChild(option);
      });
      ui.changeKind.appendChild(group);
    });
    ui.changeKind.value = activeChangeKind();
  }
  function syncControls() {
    ui.field.value = state.filters.field;
    paintChangeKindOptions();
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
    ui.modeButtons.forEach(function (button) {
      var active = button.getAttribute('data-mode') === state.mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;
      if (active) ui.queuePane.setAttribute('aria-labelledby', button.id);
    });
    ui.fieldControl.hidden = !(!isChangeMode() && !isProspectiveMode());
    ui.changeKindControl.hidden = !(isChangeMode() || isProspectiveMode());
    text(ui.changeKindLabel, isProspectiveMode() ? tr('Observed field', '观测字段') : tr('Updated field', '更新字段'));
    ui.changeKind.setAttribute('aria-label', isProspectiveMode() ? tr('Observed field', '观测字段') : tr('Updated field', '更新字段'));
    text(ui.windowLabel, isProspectiveMode() ? tr('Observation window', '观测窗口') : (isChangeMode() ? tr('Submission window', '提交窗口') : tr('Record window', '记录窗口')));
    ui.windowControl.querySelector('.bci-window-options').setAttribute('aria-label', isProspectiveMode() ? tr('First-observed window', '首次观测窗口') : (isChangeMode() ? tr('Registry submission window', '登记提交窗口') : tr('Registry date window', '登记日期窗口')));
    text(ui.queueKicker, modeKicker());
    text(ui.queueTitle, modeTitle());
    text(ui.sourceNote, isProspectiveMode()
      ? tr('First-seen observations show when our official registry collector observed a current record between two successful polls. They do not establish real-world timing, whether a protocol changed, business importance, catalyst status, a company link, an outcome estimate, or an action.', '首次观测记录显示官方登记采集器在两次成功轮询之间何时观测到当前记录。它不确定现实世界发生时间、方案是否变化、业务重要性、催化状态、公司关联、结果估计或行动。')
      : tr('Dates and field updates are recorded by ClinicalTrials.gov from study-sponsor and investigator submissions. A registry listing is not government validation. Review the source record—no trade call.', '日期和字段更新来自 ClinicalTrials.gov 所记录的研究申办方与研究者提交内容。登记收录不代表政府验证。请查看来源记录，不作交易判断。'));
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
    ui.windowButtons.forEach(function (button) {
      var value = button.getAttribute('data-window'), milestoneLabel = button.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || button.textContent;
      button.setAttribute('aria-label', isProspectiveMode()
        ? (value === 'all' ? tr('All available first-seen observations', '全部可用首次观测记录') : tr('First observed in the last ' + value + ' days', '最近' + value + '天首次观测'))
        : (isChangeMode()
        ? (value === 'all' ? tr('All available source submissions', '全部可用来源提交') : tr('Last ' + value + ' days of source submissions', '最近' + value + '天的来源提交'))
        : milestoneLabel));
    });
    [ui.refresh, ui.inspectorClose, ui.brainLaunch].forEach(function (button) {
      if (button) button.setAttribute('aria-label', button.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || button.textContent);
    });
    ui.queue.setAttribute('aria-label', activeNoun());
    ui.modeControl.setAttribute('aria-label', tr('Trial intelligence view', '试验智能视图'));
    ui.modeButtons.forEach(function (button) { button.setAttribute('aria-label', button.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || button.textContent); });
    setLoadMoreCopy();
  }
  function queryUrl(cursor) {
    var params = new URLSearchParams();
    params.set('limit', String(PAGE_LIMIT));
    params.set('window', activeWindow());
    if (isChangeMode() || isProspectiveMode()) {
      if (activeChangeKind()) params.set('change_kind', activeChangeKind());
    } else if (!isProspectiveMode()) params.set('milestone_kind', state.filters.field);
    if (state.filters.q) params.set('q', state.filters.q);
    if (state.filters.phase) params.set('phase', state.filters.phase);
    if (state.filters.status) params.set('status', state.filters.status);
    if (state.filters.condition) params.set('condition', state.filters.condition);
    if (cursor) params.set('cursor', cursor);
    return activeApi() + '?' + params.toString();
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
    var noun = activeNoun(), singular = activeSingularNoun();
    var label = state.pageLoading
      ? tr('Loading more ' + noun, '正在加载更多' + noun)
      : (state.appendFailed
        ? tr('Retry loading more ' + noun, '重试加载更多' + noun)
        : tr('Load more ' + noun, '加载更多' + noun));
    ui.loadMore.disabled = state.pageLoading;
    ui.loadMore.setAttribute('aria-label', label);
    ui.loadMore.setAttribute('aria-busy', state.pageLoading ? 'true' : 'false');
    text(ui.loadMore.querySelector('.l-en'), state.pageLoading ? 'Loading more…' : (state.appendFailed ? 'Retry load more' : 'Load more'));
    text(ui.loadMore.querySelector('.l-zh'), state.pageLoading ? '正在加载更多…' : (state.appendFailed ? '重试加载更多' : '加载更多'));
    ui.loadMore.dataset.kind = singular;
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
    var trial = item.trial, milestone = item.registry_milestone, evidence = item.evidence, id = nctOf(trial), rowKey = milestoneIdentity(item), selected = rowKey === state.selectedKey, button = el('button', 'bci-trial' + (selected ? ' is-selected' : ''));
    button.type = 'button'; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', selected ? 'true' : 'false'); button.setAttribute('data-trial-id', id); button.setAttribute('data-row-key', rowKey); button.tabIndex = index === 0 ? 0 : -1;
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
    button.addEventListener('click', function () { selectTrial(id, trial, evidence, true, button, rowKey); });
    return button;
  }
  function compactValue(value) {
    var rendered = historyValue(value);
    return rendered.length > 118 ? rendered.slice(0, 117).replace(/\s+$/, '') + '…' : rendered;
  }
  function prospectiveEmptyCopy() {
    var coverage = valueAt(state.payload, 'prospective_coverage') || {}, coverageState = clean(valueAt(coverage, 'coverage_state'));
    if (coverageState === 'pre_baseline') return tr('The collector has established a current-record baseline. It creates no event rows; a later successful poll must observe an exact record difference first.', '采集器已建立当前记录基线。此过程不会创建事件行；需要后续成功轮询先观测到精确记录差异。');
    if (coverageState === 'unavailable') return tr('Prospective current-record coverage is unavailable, so no observation rows are shown.', '仅面向未来的当前记录覆盖暂不可用，因此不显示观测行。');
    return tr('This prospective, current-record view has no observations in the selected window.', '此仅面向未来的当前记录视图在所选窗口内没有观测记录。');
  }
  function makeChangeRow(item, index) {
    var trial = item.trial, registryChange = item.registry_change, evidence = item.evidence, id = nctOf(trial), changes = registryChange.changes, rowKey = changeIdentity(item), selected = rowKey === state.selectedKey, button = el('button', 'bci-trial bci-change-card' + (selected ? ' is-selected' : ''));
    button.type = 'button'; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', selected ? 'true' : 'false'); button.setAttribute('data-trial-id', id); button.setAttribute('data-row-key', rowKey); button.tabIndex = index === 0 ? 0 : -1;
    var main = el('span', 'bci-trial-main'), line = el('span', 'bci-trial-topline');
    line.appendChild(el('span', 'bci-trial-id', id));
    var kindNames = [], seenKinds = {};
    changes.forEach(function (change) { var kind = clean(change.kind); if (!seenKinds[kind]) { seenKinds[kind] = true; kindNames.push(kind); } });
    kindNames.slice(0, 3).forEach(function (kind) { line.appendChild(el('span', 'bci-registry-kind', historyKindLabel(kind))); });
    if (kindNames.length > 3) line.appendChild(el('span', 'bci-registry-kind', '+' + (kindNames.length - 3)));
    if (statusOf(trial)) line.appendChild(el('span', 'bci-status-chip', statusOf(trial)));
    main.appendChild(line); main.appendChild(el('span', 'bci-trial-title', titleOf(trial)));
    var meta = el('span', 'bci-trial-meta'), phaseText = phasesOf(trial).join(' · ');
    if (phaseText) meta.appendChild(el('span', '', phaseText));
    if (sponsorOf(trial)) meta.appendChild(el('span', '', sponsorOf(trial)));
    main.appendChild(meta);
    var first = changes[0], preview = el('span', 'bci-change-preview');
    preview.setAttribute('aria-label', tr('Registry value preview; open the dossier for the full exact value', '登记值预览；打开档案查看完整精确值'));
    preview.appendChild(el('span', '', compactValue(first.before_value)));
    preview.appendChild(el('b', '', '→'));
    preview.appendChild(el('span', '', compactValue(first.after_value)));
    main.appendChild(preview); button.appendChild(main);
    var receipt = el('span', 'bci-change-receipt');
    receipt.appendChild(el('strong', '', tr('Submitted ', '提交日期 ') + timestampLabel(registryChange.source_submitted_at)));
    receipt.appendChild(el('span', 'bci-change-version', 'V' + registryChange.before_display_version + ' → V' + registryChange.after_display_version));
    if (registryChange.total_display_safe_changes > registryChange.shown_change_count) receipt.appendChild(el('span', '', tr(registryChange.shown_change_count + ' of ' + registryChange.total_display_safe_changes + ' fields', registryChange.shown_change_count + '/' + registryChange.total_display_safe_changes + '项字段')));
    button.appendChild(receipt);
    button.addEventListener('click', function () { selectTrial(id, trial, evidence, true, button, rowKey); });
    return button;
  }
  function makeProspectiveRow(item, index) {
    var trial = item.trial, prospectiveChange = item.prospective_change, evidence = item.evidence, id = nctOf(trial), changes = prospectiveChange.changes, interval = prospectiveChange.observed_interval, rowKey = prospectiveIdentity(item), selected = rowKey === state.selectedKey, button = el('button', 'bci-trial bci-prospective-card' + (selected ? ' is-selected' : ''));
    button.type = 'button'; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', selected ? 'true' : 'false'); button.setAttribute('data-trial-id', id); button.setAttribute('data-row-key', rowKey); button.tabIndex = index === 0 ? 0 : -1;
    var main = el('span', 'bci-trial-main'), line = el('span', 'bci-trial-topline');
    line.appendChild(el('span', 'bci-trial-id', id));
    line.appendChild(el('span', 'bci-observation-kind', tr('First observed', '首次观测')));
    if (statusOf(trial)) line.appendChild(el('span', 'bci-status-chip', statusOf(trial)));
    main.appendChild(line); main.appendChild(el('span', 'bci-trial-title', titleOf(trial)));
    var meta = el('span', 'bci-trial-meta'), phaseText = phasesOf(trial).join(' · ');
    if (phaseText) meta.appendChild(el('span', '', phaseText));
    if (sponsorOf(trial)) meta.appendChild(el('span', '', sponsorOf(trial)));
    main.appendChild(meta);
    var first = changes[0], preview = el('span', 'bci-observation-preview');
    if (first) {
      preview.setAttribute('aria-label', tr('Observation value preview; open the dossier for the bounded display values', '观测值预览；打开档案查看有界展示值'));
      preview.appendChild(el('span', '', compactValue(first.before_value)));
      preview.appendChild(el('b', '', '→'));
      preview.appendChild(el('span', '', compactValue(first.after_value)));
    } else {
      preview.classList.add('is-omitted');
      preview.setAttribute('aria-label', tr(prospectiveChange.total_exact_operation_count + ' exact changes omitted; no display-safe detail', prospectiveChange.total_exact_operation_count + '项精确变化已省略；没有可安全展示详情'));
      preview.appendChild(el('span', '', tr(prospectiveChange.total_exact_operation_count + ' exact changes omitted; no display-safe detail', prospectiveChange.total_exact_operation_count + '项精确变化已省略；没有可安全展示详情')));
    }
    main.appendChild(preview); button.appendChild(main);
    var receipt = el('span', 'bci-observation-receipt');
    receipt.appendChild(el('strong', '', tr('Observed ', '观测于 ') + observationTimestampLabel(prospectiveChange.first_observed_at)));
    receipt.appendChild(el('span', '', tr('After ', '晚于 ') + observationTimestampLabel(interval.after)));
    receipt.appendChild(el('span', '', tr('At / before ', '截至 / 不晚于 ') + observationTimestampLabel(interval.at_or_before)));
    if (prospectiveChange.display_change_count === 0) receipt.appendChild(el('span', '', tr(prospectiveChange.total_exact_operation_count + ' omitted', prospectiveChange.total_exact_operation_count + '项已省略')));
    else if (prospectiveChange.total_exact_operation_count > prospectiveChange.display_change_count) receipt.appendChild(el('span', '', tr(prospectiveChange.display_change_count + ' display-safe fields', prospectiveChange.display_change_count + '项可安全展示字段')));
    button.appendChild(receipt);
    button.addEventListener('click', function () { selectTrial(id, trial, evidence, true, button, rowKey); });
    return button;
  }
  function syncQueueSelection() {
    Array.prototype.slice.call(ui.queue.querySelectorAll('.bci-trial')).forEach(function (button) {
      var selected = button.getAttribute('data-row-key') === state.selectedKey;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
  }
  function renderQueue() {
    clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', state.loading ? 'true' : 'false');
    if (state.accessLocked) {
      ui.queue.appendChild(emptyCard(isProspectiveMode() ? tr('First-seen Tape is locked', '首次观测记录已锁定') : (isChangeMode() ? tr('Registry updates are locked', '登记更新已锁定') : tr('Registry records are locked', '登记记录已锁定')), tr('Sign in with full access to read ' + activeNoun() + '.', '请以完整访问权限登录，读取' + activeNoun() + '。'), '◌'));
      ui.queueFooter.hidden = true;
      setLoadMoreCopy();
      return;
    }
    if (!state.rows.length) {
      ui.queue.appendChild(emptyCard(
        isProspectiveMode() ? tr('No first-seen observations', '暂无首次观测记录') : (isChangeMode() ? tr('No registry field updates', '暂无登记字段更新') : tr('No recorded dates', '暂无已记录日期')),
        isProspectiveMode() ? prospectiveEmptyCopy() : (isChangeMode() ? tr('No exact registry field update matches this submission window and filter set.', '在此提交窗口和筛选条件下，没有匹配的精确登记字段更新。') : tr('No registry-recorded primary completion or completion date matches this window and filter set.', '在此窗口和筛选条件下，没有匹配的主要完成或完成登记日期。')),
        '○'
      ));
    } else {
      state.rows.forEach(function (item, index) { ui.queue.appendChild(isProspectiveMode() ? makeProspectiveRow(item, index) : (isChangeMode() ? makeChangeRow(item, index) : makeMilestoneRow(item, index))); });
    }
    ui.queueFooter.hidden = !state.nextCursor || state.accessLocked;
    setLoadMoreCopy();
  }
  function setSubtitle(payload) {
    var pagination = valueAt(payload, 'pagination') || {}, total = valueAt(pagination, 'total'), window = valueAt(payload, 'effective_window') || {}, historyCoverage = valueAt(payload, 'history_coverage') || {}, prospectiveCoverage = valueAt(payload, 'prospective_coverage') || {};
    if (typeof total !== 'number') { text(ui.subtitle, isProspectiveMode() ? tr('First observed by this current-record collector', '由当前记录采集器首次观测') : (isChangeMode() ? tr('Exact registry field updates from source submissions', '来源提交中的精确登记字段更新') : tr('Registry-recorded primary completion and completion dates', '登记记录的主要完成和完成日期'))); return; }
    var timeLabel = clean(valueAt(window, 'from_date')) && clean(valueAt(window, 'to_date'))
      ? (isProspectiveMode() ? tr('first observed in the selected window', '在所选窗口内首次观测') : (isChangeMode() ? tr('within the selected submission window', '位于所选提交窗口内') : tr('within the selected record window', '位于所选记录窗口内')))
      : (isProspectiveMode() ? tr('across the available observation range', '覆盖可用观测范围') : (isChangeMode() ? tr('across the available submission range', '覆盖可用提交范围') : tr('across the available record range', '覆盖可用记录范围')));
    if (isProspectiveMode()) {
      var active = valueAt(prospectiveCoverage, 'active_trials'), preBaseline = valueAt(prospectiveCoverage, 'pre_baseline_trials'), unavailable = valueAt(prospectiveCoverage, 'unavailable_trials');
      var prospectiveCoverageLabel = Number.isSafeInteger(active) && Number.isSafeInteger(preBaseline) && Number.isSafeInteger(unavailable)
        ? tr(' · Current-only coverage: ' + active + ' active, ' + preBaseline + ' baseline, ' + unavailable + ' unavailable', ' · 仅当前记录覆盖：' + active + '项活跃，' + preBaseline + '项基线，' + unavailable + '项不可用')
        : tr(' · Current-record coverage only', ' · 仅当前记录覆盖');
      text(ui.subtitle, (total === 1 ? tr('1 first-seen observation ' + timeLabel, '1项首次观测记录' + timeLabel) : tr(total + ' first-seen observations ' + timeLabel, total + '项首次观测记录' + timeLabel)) + prospectiveCoverageLabel);
    } else if (isChangeMode()) {
      var available = valueAt(historyCoverage, 'available_trials'), unavailable = valueAt(historyCoverage, 'unavailable_trials');
      var coverageLabel = Number.isSafeInteger(available) && Number.isSafeInteger(unavailable)
        ? tr(' · History coverage: ' + available + ' complete, ' + unavailable + ' unavailable', ' · 历史覆盖：' + available + '项完整，' + unavailable + '项不可用')
        : '';
      text(ui.subtitle, (total === 1 ? tr('1 exact registry field update ' + timeLabel, '1项精确登记字段更新' + timeLabel) : tr(total + ' exact registry field updates ' + timeLabel, total + '项精确登记字段更新' + timeLabel)) + coverageLabel);
    }
    else text(ui.subtitle, total === 1 ? tr('1 registry-recorded date ' + timeLabel, '1项登记记录日期' + timeLabel) : tr(total + ' registry-recorded dates ' + timeLabel, total + '项登记记录日期' + timeLabel));
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
  function historyValue(value) {
    if (typeof value === 'undefined') return tr('Not recorded', '未记录');
    try {
      var encoded = JSON.stringify(value);
      return typeof encoded === 'string' ? encoded : tr('Not recorded', '未记录');
    } catch (_error) {
      return tr('Value unavailable', '值暂不可用');
    }
  }
  function exactValue(value) {
    if (typeof value === 'undefined') return tr('Not recorded', '未记录');
    try {
      var encoded = JSON.stringify(value);
      return typeof encoded === 'string' ? encoded : tr('Not recorded', '未记录');
    } catch (_error) {
      return tr('Value unavailable', '值暂不可用');
    }
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
      endpoint_added: ['Endpoint added', '新增终点'], endpoint_removed: ['Endpoint removed', '移除终点'], endpoint_role_changed: ['Endpoint role updated', '终点角色更新'], endpoint_measure_changed: ['Endpoint measure updated', '终点指标更新'], endpoint_time_frame_changed: ['Endpoint timeframe updated', '终点时间范围更新'], endpoint_description_changed: ['Endpoint description updated', '终点说明更新'], enrollment_changed: ['Enrollment record updated', '入组记录更新'], registry_status_changed: ['Registry status updated', '登记状态更新'], study_date_changed: ['Study date record updated', '研究日期记录更新'], site_listing_changed: ['Site listing updated', '研究中心列表更新'], lead_sponsor_text_changed: ['Lead sponsor text updated', '牵头申办方文字更新'], intervention_added: ['Intervention added', '新增干预措施'], intervention_removed: ['Intervention removed', '移除干预措施'], intervention_changed: ['Intervention record updated', '干预措施记录更新'],
      registry_status: ['Registry status record', '登记状态记录'], enrollment_target: ['Enrollment target record', '入组目标记录'], enrollment_actual: ['Enrollment actual record', '实际入组记录'], enrollment_count: ['Enrollment count record', '入组人数记录'], enrollment_type: ['Enrollment type record', '入组类型记录'], primary_completion_date: ['Primary completion date record', '主要完成日期记录'], completion_date: ['Completion date record', '完成日期记录'], site_set: ['Trial-site record', '研究中心记录'], endpoint_record: ['Endpoint record', '终点记录']
    };
    var pair = labels[clean(kind)]; return pair ? tr(pair[0], pair[1]) : tr('Registry field updated', '登记字段更新');
  }
  function prospectiveKindLabel(kind) {
    var labels = {
      registry_status: ['Registry status record', '登记状态记录'], enrollment_target: ['Enrollment target record', '入组目标记录'], enrollment_actual: ['Enrollment actual record', '实际入组记录'], enrollment_count: ['Enrollment count record', '入组人数记录'], enrollment_type: ['Enrollment type record', '入组类型记录'], primary_completion_date: ['Primary completion date record', '主要完成日期记录'], completion_date: ['Completion date record', '完成日期记录'], site_set: ['Trial-site record', '研究中心记录'], endpoint_record: ['Endpoint record', '终点记录']
    };
    var pair = labels[clean(kind)]; return pair ? tr(pair[0], pair[1]) : tr('Observed field record', '观测字段记录');
  }
  function prospectiveObservationSection(prospectiveChange) {
    var section = el('section', 'bci-detail-section bci-observation-section'); section.appendChild(el('h3', '', tr('First-seen observation', '首次观测记录')));
    if (!validProspectiveChange(prospectiveChange)) { section.appendChild(el('p', 'bci-detail-note', tr('This first-seen observation receipt is unavailable. No replacement fact is inferred.', '此首次观测凭证暂不可用。不会推断替代事实。'))); return section; }
    var interval = prospectiveChange.observed_interval, receipt = el('div', 'bci-evidence-strip bci-observation-strip');
    [fact(tr('First observed', '首次观测'), observationTimestampLabel(prospectiveChange.first_observed_at)), fact(tr('Observed after', '观测晚于'), observationTimestampLabel(interval.after)), fact(tr('Observed at / before', '观测截至 / 不晚于'), observationTimestampLabel(interval.at_or_before)), fact(tr('Coverage', '覆盖范围'), tr('Current record only', '仅当前记录'))].forEach(function (item) { if (item) receipt.appendChild(item); });
    section.appendChild(receipt);
    section.appendChild(el('p', 'bci-detail-note bci-observation-note', tr('This interval is between successful collection observations. It does not establish real-world timing, whether a protocol changed, business importance, catalyst status, a company link, an outcome estimate, or an action.', '该区间位于成功采集观测之间。它不确定现实世界发生时间、方案是否变化、业务重要性、催化状态、公司关联、结果估计或行动。')));
    if (!prospectiveChange.changes.length) section.appendChild(el('p', 'bci-detail-note bci-observation-note', tr(prospectiveChange.total_exact_operation_count + ' exact changes were omitted; there is no display-safe detail for this observation.', prospectiveChange.total_exact_operation_count + '项精确变化已省略；此观测记录没有可安全展示详情。')));
    prospectiveChange.changes.forEach(function (change) {
      var delta = el('article', 'bci-endpoint bci-observation-delta');
      delta.appendChild(el('span', 'bci-observation-kind', prospectiveKindLabel(change.kind)));
      delta.appendChild(el('p', '', tr('Before: ', '之前：') + exactValue(change.before_value)));
      delta.appendChild(el('p', '', tr('After: ', '之后：') + exactValue(change.after_value)));
      section.appendChild(delta);
    });
    return section;
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
  function showDetail(detail, queueEvidence, queueItem) {
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
    if (isProspectiveMode()) ui.inspectorBody.appendChild(prospectiveObservationSection(valueAt(queueItem, 'prospective_change')));
    else ui.inspectorBody.appendChild(historySection(valueAt(detail, 'history')));
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
    var returnFocus = state.returnFocus, returnTrialId = returnFocus && clean(returnFocus.getAttribute('data-trial-id')), returnRowKey = returnFocus && str(returnFocus.getAttribute('data-row-key'));
    ui.inspector.classList.remove('is-open'); document.body.classList.remove('bci-inspector-open'); ui.scrim.hidden = true; syncInspectorDialog();
    state.returnFocus = null; state.selectedId = ''; state.selectedKey = ''; state.selected = null; state.detail = null; abort('detailController'); state.detailToken += 1;
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' to read the current trial record and its source receipt.', '选择一项' + activeSingularNoun() + '，查看当前试验记录及其来源凭证。'));
    if (options.writeUrl !== false) writeUrl();
    if (options.render !== false) syncQueueSelection();
    if ((!returnFocus || !document.contains(returnFocus)) && returnRowKey) returnFocus = Array.prototype.slice.call(ui.queue.querySelectorAll('[data-row-key]')).filter(function (row) { return row.getAttribute('data-row-key') === returnRowKey; })[0];
    if ((!returnFocus || !document.contains(returnFocus)) && isTrialId(returnTrialId)) returnFocus = ui.queue.querySelector('[data-trial-id="' + returnTrialId + '"]');
    if (options.restoreFocus !== false && returnFocus && document.contains(returnFocus) && typeof returnFocus.focus === 'function') returnFocus.focus({ preventScroll: true });
  }
  function detailLoading() { text(ui.inspectorTitle, tr('Loading dossier', '正在加载档案')); clearChildren(ui.inspectorBody); ui.inspectorBody.appendChild(el('div', 'bci-loading-detail', tr('Reading the current official record…', '正在读取当前官方记录…'))); }
  function selectTrial(id, trial, queueEvidence, update, trigger, rowKey) {
    if (!isTrialId(id)) return;
    state.selectedId = id; state.selectedKey = rowKey || (trigger && str(trigger.getAttribute('data-row-key'))) || ''; state.selected = trial || { nct_id: id, title: id }; state.detail = null; if (update) writeUrl(); syncQueueSelection();
    trigger = trigger && document.contains(trigger) ? trigger : ui.queue.querySelector('[data-trial-id="' + id + '"]');
    openInspector(window.matchMedia('(max-width: 1120px)').matches, trigger); detailLoading();
    abort('detailController'); var controller = new AbortController(), token = state.detailToken + 1; state.detailToken = token; state.detailController = controller;
    fetchJson(TRIAL_API + '/' + encodeURIComponent(id), controller.signal).then(function (payload) {
      if (token !== state.detailToken) return; var detail = payload && valueAt(payload, 'trial'); if (!validTrial(detail) || nctOf(detail) !== id) throw new Error('Invalid trial detail contract'); state.detail = detail; showDetail(detail, queueEvidence, selectedRow());
    }).catch(function (error) {
      if (token !== state.detailToken || (error && error.name === 'AbortError')) return;
      if (error && error.status === 404) showInspectorEmpty(tr('Dossier unavailable', '档案暂不可用'), tr('This trial is no longer in the current verified record. No replacement record is inferred.', '该试验已不在当前已核验记录中。不会推断替代记录。'));
      else if (isAccessError(error)) { lockWorkspace(); showInspectorEmpty(tr('Dossier locked', '档案已锁定'), tr('Full access is required before the current trial record can be shown.', '显示当前试验记录前需要完整访问权限。')); }
      else showInspectorEmpty(tr('Dossier unavailable', '档案暂不可用'), tr('Retry later. The dossier does not fill fields absent from the official record.', '请稍后重试。档案不会填补官方记录中缺失的字段。'));
    }).finally(function () { if (state.detailController === controller) state.detailController = null; });
    if (trigger) trigger.setAttribute('aria-selected', 'true');
  }

  function updateMetadata(payload) {
    var health = valueAt(payload, 'health') || {}, source = valueAt(payload, 'source') || {}, historyCoverage = valueAt(payload, 'history_coverage') || {}, prospectiveCoverage = valueAt(payload, 'prospective_coverage') || {}, stateName = clean(valueAt(health, 'state')).toLowerCase(), asOf = clean(valueAt(payload, 'as_of')) || clean(valueAt(source, 'dataset_timestamp_raw')), historyCutoff = clean(valueAt(historyCoverage, 'knowledge_cutoff')), lastObserved = clean(valueAt(prospectiveCoverage, 'last_observed_at'));
    text(ui.asOf, isProspectiveMode() && fullTimestamp(lastObserved)
      ? tr('Observed through ', '观测截至 ') + observationTimestampLabel(lastObserved)
      : (isChangeMode() && historyCutoff
        ? tr('History retrieved through ', '历史获取截至 ') + timestampLabel(historyCutoff)
        : (asOf ? tr('As of ', '截至 ') + timestampLabel(asOf) : '')));
    if (stateName === 'stale') { setStatus('stale', tr('Last verified page', '最近已核验页面'), tr('Registry update in progress', '登记库正在更新')); setNotice('stale', tr('The registry update is in progress. You are reading the last verified page; check its as-of date.', '登记库更新正在进行。当前展示最近一次已核验页面；请查看其截至日期。')); }
    else if (stateName === 'unavailable') { setStatus('unavailable', tr('Freshness status unavailable', '新鲜度状态暂不可用'), tr('Showing the current verified page', '正在显示当前已核验页面')); setNotice('error', tr('The freshness check is unavailable. Read the source and retrieval dates before relying on this page.', '新鲜度检查暂不可用。使用此页面前请查看来源和获取日期。')); }
    else if (state.restarted) { setStatus('restarted', tr('Registry page restarted', '登记页面已重启'), tr('Showing the refreshed verified page', '正在显示刷新后的已核验页面')); setNotice('restart', tr('The registry generation changed while another page was loading. The ' + modeTitle().toLowerCase() + ' restarted from the current filters.', '加载另一页时登记生成发生变化。' + modeTitle() + '已按当前筛选条件重新开始。')); }
    else { setStatus('ready', tr('Verified registry page', '已核验登记页面'), clean(valueAt(source, 'name')) || tr('Official registry source', '官方登记来源')); setNotice('', ''); }
  }
  function isAccessError(error) { return !!error && (error.status === 401 || error.status === 402 || error.status === 403); }
  function restartableAppendError(error) { return !!error && (error.status === 400 || error.status === 409); }
  function paintLockedWorkspace() {
    ui.workspace.dataset.state = 'locked'; clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'false'); ui.queueFooter.hidden = true;
    setStatus('locked', tr('Full access required', '需要完整访问权限'), tr('Sign in with an entitled account', '请使用已授权账户登录'));
    setNotice('locked', tr('BioCatalyst Intelligence is available with full access. No trial records are shown until access is confirmed.', 'BioCatalyst Intelligence 需要完整访问权限。访问确认前不会显示试验记录。'));
    ui.queue.appendChild(emptyCard(isProspectiveMode() ? tr('First-seen Tape is locked', '首次观测记录已锁定') : (isChangeMode() ? tr('Registry updates are locked', '登记更新已锁定') : tr('Registry records are locked', '登记记录已锁定')), tr('Sign in with full access to read ' + activeNoun() + '.', '请以完整访问权限登录，读取' + activeNoun() + '。'), '◌'));
    announce(tr(activeNoun() + ' are locked.', activeNoun() + '已锁定。'));
  }
  function lockWorkspace() {
    abort('listController'); state.listToken += 1; abort('detailController'); state.detailToken += 1; ui.refresh.classList.remove('is-spinning');
    state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = '';
    state.selectedId = ''; state.selectedKey = ''; state.selected = null; state.detail = null; state.appendFailed = false; state.accessLocked = true;
    paintLockedWorkspace();
  }
  function paintAppendFailure() {
    ui.workspace.dataset.state = 'append-unavailable';
    setStatus('stale', tr('Last verified page', '最近已核验页面'), tr('The next ' + activeNoun() + ' page could not be loaded', '无法加载下一页' + activeNoun()));
    setNotice('stale', tr('The next ' + activeNoun() + ' page is unavailable. Showing last verified rows; try Load more again.', '下一页' + activeNoun() + '暂不可用。正在显示最近已核验行；请再次加载更多。'));
    announce(tr('The next ' + activeNoun() + ' page is unavailable. Last verified rows remain visible.', '下一页' + activeNoun() + '暂不可用。最近已核验行保持可见。'));
    renderQueue();
    if (!ui.queueFooter.hidden && document.activeElement === ui.loadMore) ui.loadMore.focus({ preventScroll: true });
  }
  function preserveAppendFailure() {
    state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.appendFailed = true; state.accessLocked = false;
    paintAppendFailure();
  }
  function paintUnavailableWorkspace() {
    ui.workspace.dataset.state = 'unavailable'; clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'false'); ui.queueFooter.hidden = true;
    setStatus('unavailable', tr('Registry page unavailable', '登记页面暂不可用'), tr('No source fields are inferred', '不会推断来源字段'));
    setNotice('error', tr('The verified registry page is temporarily unavailable. No trial records are shown.', '已核验登记页面暂不可用。不会显示试验记录。'));
    ui.queue.appendChild(emptyCard(tr('Registry page unavailable', '登记页面暂不可用'), tr('Retry the source request. This workspace does not infer unrecorded fields.', '请重试来源请求。此工作台不会推断未记录字段。'), '×', true));
    announce(tr('Registry page unavailable.', '登记页面暂不可用。'));
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' when the current page is available.', '当前页面可用后，请选择一项' + activeSingularNoun() + '。'));
  }
  function handleUnavailable(error, options) {
    options = options || {};
    if (isAccessError(error)) {
      lockWorkspace();
      showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' when full access is confirmed.', '完整访问权限确认后，请选择一项' + activeSingularNoun() + '。'));
      return;
    }
    if (options.append && state.rows.length) { preserveAppendFailure(); return; }
    state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = ''; state.selectedKey = ''; state.appendFailed = false; state.accessLocked = false;
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
      text(ui.subtitle, tr('Retrieving the verified ' + activeNoun() + ' page…', '正在获取已核验' + activeNoun() + '页面…')); setStatus('ready', tr('Retrieving ' + activeNoun(), '正在获取' + activeNoun()), tr('No records are in this page shell', '此页面外壳不含记录'));
    } else {
      ui.workspace.dataset.state = 'page-loading'; loadingQueue(true); announce(tr('Loading more ' + activeNoun() + '.', '正在加载更多' + activeNoun() + '。'));
    }
    ui.refresh.classList.add('is-spinning');
    fetchJson(queryUrl(cursor), controller.signal).then(function (payload) {
      if (token !== state.listToken) return;
      if (isProspectiveMode()) validateProspectiveEnvelope(payload); else if (isChangeMode()) validateChangeEnvelope(payload); else validateMilestoneEnvelope(payload);
      var incomingGeneration = generationKey(payload);
      if (append && state.generation && incomingGeneration !== state.generation) {
        state.restarted = true; announce(tr('The registry page changed. Reloading the selected filters.', '登记页面已变化。正在重新加载所选筛选条件。'));
        loadMilestones({ replace: true, restarted: true }); return;
      }
      var existingRows = append ? state.rows : [], rows = isProspectiveMode() ? validateProspectivePage(payload.prospective_changes, existingRows) : (isChangeMode() ? validateChangePage(payload.changes, existingRows) : validateMilestonePage(payload.milestones, existingRows)), pagination = payload.pagination;
      if (isProspectiveMode()) validateProspectivePagination(payload, existingRows, cursor, append ? state.payload : null); else if (isChangeMode()) validateChangePagination(payload, existingRows, cursor, append ? state.payload : null); else validateMilestonePagination(payload, existingRows, cursor, append ? state.payload : null);
      if (append) state.rows = state.rows.concat(rows); else state.rows = rows;
      state.payload = payload; state.generation = incomingGeneration; state.nextCursor = clean(valueAt(pagination, 'next_cursor')); state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.appendFailed = false; state.accessLocked = false;
      ui.workspace.dataset.state = state.restarted ? 'generation-restarted' : (state.rows.length ? 'ready' : 'empty'); updateMetadata(payload); setSubtitle(payload); renderQueue();
      announce(state.rows.length ? tr('Loaded ' + state.rows.length + ' ' + activeNoun() + '.', '已加载' + state.rows.length + '项' + activeNoun() + '。') : tr('No ' + activeNoun() + ' match these filters.', '没有' + activeNoun() + '匹配这些筛选条件。'));
      if (!append && state.selectedId) {
        var activeRow = selectedRow();
        selectTrial(state.selectedId, activeRow && activeRow.trial, activeRow && activeRow.evidence, false, null, activeRow && rowIdentity(activeRow));
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
    setActiveChangeKind(ui.changeKind.value);
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
  function setMode(value, trigger) {
    if (!MODE_VALUES[value] || state.mode === value) return;
    abort('listController'); state.listToken += 1; abort('detailController'); state.detailToken += 1;
    state.mode = value; state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = ''; state.appendFailed = false; state.accessLocked = false; state.restarted = false;
    state.selectedId = ''; state.selectedKey = ''; state.selected = null; state.detail = null; state.returnFocus = null;
    ui.inspector.classList.remove('is-open'); document.body.classList.remove('bci-inspector-open'); ui.scrim.hidden = true; syncInspectorDialog();
    syncControls(); localizeControls(); writeUrl();
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' to read the current trial record and its source receipt.', '选择一项' + activeSingularNoun() + '，查看当前试验记录及其来源凭证。'));
    if (trigger && document.contains(trigger)) trigger.focus({ preventScroll: true });
    loadMilestones({ replace: true });
  }
  function openBrain() {
    if (window.MMBrain && typeof window.MMBrain.open === 'function') { window.MMBrain.open(); return; }
    setNotice('error', tr('Mastermind is unavailable right now. Your registry filters remain unchanged.', '操盘大脑暂不可用。你的登记筛选条件保持不变。'));
  }
  function bindEvents() {
    var debounceId = 0;
    ui.search.addEventListener('input', function () { window.clearTimeout(debounceId); debounceId = window.setTimeout(applyFilters, 260); });
    ui.condition.addEventListener('input', function () { window.clearTimeout(debounceId); debounceId = window.setTimeout(applyFilters, 260); });
    [ui.field, ui.changeKind, ui.phase, ui.statusFilter].forEach(function (node) { node.addEventListener('change', applyFilters); });
    ui.modeButtons.forEach(function (button) { button.addEventListener('click', function () { setMode(button.getAttribute('data-mode'), button); }); });
    ui.modeControl.addEventListener('keydown', function (event) {
      if (['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].indexOf(event.key) < 0) return;
      var active = ui.modeButtons.map(function (button) { return button.getAttribute('data-mode'); }).indexOf(state.mode), direction = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : -1, target;
      if (event.key === 'Home') target = 0; else if (event.key === 'End') target = ui.modeButtons.length - 1; else target = (active + direction + ui.modeButtons.length) % ui.modeButtons.length;
      event.preventDefault(); ui.modeButtons[target].focus(); setMode(ui.modeButtons[target].getAttribute('data-mode'), ui.modeButtons[target]);
    });
    ui.windowButtons.forEach(function (button) { button.addEventListener('click', function () { setWindow(button.getAttribute('data-window')); }); });
    ui.windowControl.addEventListener('keydown', function (event) {
      if (['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].indexOf(event.key) < 0) return;
      var active = ui.windowButtons.map(function (button) { return button.getAttribute('data-window'); }).indexOf(state.filters.window), direction = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : -1, target;
      if (event.key === 'Home') target = 0; else if (event.key === 'End') target = ui.windowButtons.length - 1; else target = (active + direction + ui.windowButtons.length) % ui.windowButtons.length;
      event.preventDefault(); ui.windowButtons[target].focus(); setWindow(ui.windowButtons[target].getAttribute('data-window'));
    });
    ui.clear.addEventListener('click', function () { state.filters = defaultFilters(); syncControls(); applyFilters(); ui.search.focus(); });
    ui.brainLaunch.addEventListener('click', openBrain);
    ui.refresh.addEventListener('click', function () { loadMilestones({ replace: true }); });
    ui.loadMore.addEventListener('click', function () { loadMilestones({ append: true }); });
    ui.inspectorClose.addEventListener('click', closeInspector); ui.scrim.addEventListener('click', closeInspector);
    ui.queue.addEventListener('keydown', function (event) { if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return; var rows = Array.prototype.slice.call(ui.queue.querySelectorAll('.bci-trial')), current = rows.indexOf(document.activeElement); if (!rows.length) return; event.preventDefault(); var next = current < 0 ? 0 : (current + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length; rows[next].focus(); });
    document.addEventListener('keydown', function (event) { trapInspectorFocus(event); if (event.key === 'Escape' && ui.inspector.classList.contains('is-open')) closeInspector(); });
    document.addEventListener('langchange', function () {
      syncControls(); localizeControls();
      if (state.accessLocked) { paintLockedWorkspace(); showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' when full access is confirmed.', '完整访问权限确认后，请选择一项' + activeSingularNoun() + '。')); return; }
      if (ui.workspace.dataset.state === 'unavailable') { paintUnavailableWorkspace(); return; }
      if (state.appendFailed) paintAppendFailure();
      else if (state.payload) { updateMetadata(state.payload); setSubtitle(state.payload); renderQueue(); announce(state.rows.length ? tr('Loaded ' + state.rows.length + ' ' + activeNoun() + '.', '已加载' + state.rows.length + '项' + activeNoun() + '。') : tr('No ' + activeNoun() + ' match these filters.', '没有' + activeNoun() + '匹配这些筛选条件。')); }
      else if (state.loading) { text(ui.subtitle, tr('Retrieving the verified ' + activeNoun() + ' page…', '正在获取已核验' + activeNoun() + '页面…')); setStatus('ready', tr('Retrieving ' + activeNoun(), '正在获取' + activeNoun()), tr('No records are in this page shell', '此页面外壳不含记录')); announce(tr('Retrieving ' + activeNoun() + '.', '正在获取' + activeNoun() + '。')); }
      if (state.detail) { var activeRow = selectedRow(); showDetail(state.detail, activeRow && activeRow.evidence, activeRow); }
      else if (state.detailController && ui.inspector.classList.contains('is-open')) detailLoading();
    });
    window.addEventListener('popstate', function () { abort('listController'); closeInspector({ restoreFocus: false, writeUrl: false, render: false }); readUrl(); syncControls(); loadMilestones({ replace: true }); });
    window.addEventListener('resize', syncInspectorDialog);
  }
  function init() {
    cacheUi(); readUrl(); localizeControls(); syncControls(); bindEvents();
    writeUrl();
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' to read the current trial record and its source receipt.', '选择一项' + activeSingularNoun() + '，查看当前试验记录及其来源凭证。'));
    loadMilestones({ replace: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

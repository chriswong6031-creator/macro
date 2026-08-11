(function () {
  'use strict';

  var MILESTONE_API = '/api/biocatalyst/v1/trials/milestones';
  var CHANGE_API = '/api/biocatalyst/v1/trials/change-tape';
  var PROSPECTIVE_API = '/api/biocatalyst/v1/trials/prospective-changes';
  var SCREEN_API = '/api/biocatalyst/v1/trials:screen';
  var FACETS_API = '/api/biocatalyst/v1/trials:screen/facets';
  var PEER_API = '/api/biocatalyst/v1/trial-peer-sets:resolve';
  var TRIAL_API = '/api/biocatalyst/v1/trials';
  var TRIAL_ID = /^NCT\d{8}$/;
  var DATE_PARTS = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/;
  var WINDOW_VALUES = { '30': true, '90': true, '180': true, all: true };
  var MILESTONE_WINDOWS = { '30': 'next_30d', '90': 'next_90d', '180': 'next_180d', all: 'all' };
  var FIELD_VALUES = { primary_completion: true, completion: true };
  // The replay-verified tape is keyed by registry field class, not by the
  // legacy derived change-kind vocabulary.
  var CHANGE_KIND_VALUES = {
    registry_status: true, enrollment: true, milestone_date_constraint: true,
    site_list: true, intervention: true, endpoint_record_delta: true
  };
  var TAPE_REVIEW_VALUES = { all: true, not_required: true, needs_review: true };
  var TAPE_OPS = { add: ['missing', 'present'], remove: ['present', 'missing'], replace: ['present', 'present'] };
  var STUDY_TYPE_VALUES = { INTERVENTIONAL: true, OBSERVATIONAL: true, EXPANDED_ACCESS: true };
  var FACET_DIMENSIONS = ['phase', 'status', 'study_type'];
  var MISSINGNESS_STATES = ['observed', 'source_null', 'source_missing', 'not_applicable', 'parser_degraded', 'license_restricted'];
  var PEER_FIELDS = ['status', 'phases', 'enrollment', 'dates', 'arm_groups', 'endpoints', 'site_count', 'countries'];
  var PEER_MIN_COHORT = 2;
  var PEER_MAX_COHORT = 100;
  // The twelve-rank deterministic state precedence of the D0a IA contract §4.
  // Lower rank wins the primary banner; ties break on earliest known_at, then
  // on the lexical state code.
  var STATE_PRECEDENCE = [
    ['locked', 1], ['integrity_block', 2], ['source_capability_absent', 3], ['ambiguous_identity', 4],
    ['contradiction', 5], ['correction', 6], ['source_outage', 7], ['stale', 8],
    ['historical', 9], ['partial', 10], ['empty', 11], ['normal', 12]
  ];
  // The six research stances minted by the D0a design ruling §2/D2. This is the
  // only stance vocabulary this product may speak.
  var RESEARCH_STANCE = {
    read: ['Read the record', '记录可直接看', ''],
    check: ['Check the source', '去核对来源', ''],
    wait: ['Wait for the record', '等记录更新', 'is-wait'],
    reconcile: ['Reconcile the conflict', '两处对不上', 'is-conflict'],
    historical: ['Treat as historical', '这是当时的记录', 'is-quiet'],
    none: ['Nothing here', '暂无内容', 'is-quiet']
  };
  var STATE_STANCE = {
    locked: 'none', integrity_block: 'none', source_capability_absent: 'wait', ambiguous_identity: 'check',
    contradiction: 'reconcile', correction: 'check', source_outage: 'wait', stale: 'wait',
    historical: 'historical', partial: 'check', empty: 'none', normal: 'read'
  };
  var PROSPECTIVE_CHANGE_KIND_VALUES = {
    registry_status: true, enrollment_target: true, enrollment_actual: true, enrollment_count: true,
    enrollment_type: true, primary_completion_date: true, completion_date: true, site_set: true, endpoint_record: true
  };
  var CHANGE_KIND_CATALOG = [
    { label: ['Registry field', '登记字段'], items: [
      ['registry_status', 'Recruitment status', '招募状态'],
      ['enrollment', 'Enrollment record', '入组记录'],
      ['milestone_date_constraint', 'Recorded date', '记录日期'],
      ['site_list', 'Trial-site list', '研究中心清单'],
      ['intervention', 'Intervention record', '干预措施记录'],
      ['endpoint_record_delta', 'Endpoint record', '终点记录']
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
  var PROSPECTIVE_WINDOWS = { '30': 'last_30d', '90': 'last_90d', '180': 'last_180d', all: 'all' };
  var MODE_VALUES = { milestones: true, screen: true, peers: true, changes: true, prospective: true };
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
    filters: { field: 'primary_completion', change_kind: '', prospective_change_kind: '', window: '90', q: '', phase: '', status: '', condition: '', sponsor: '', intervention: '', study_type: '', pc_from: '', pc_to: '', review_state: 'all' },
    facets: null,
    facetsToken: 0,
    facetsController: null,
    cohort: [],
    cohortText: '',
    peerNarrow: false,
    braid: [],
    stateCodes: [],
    contractFailed: false,
    workspaceDown: false,
    evidenceCell: null
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
    ui.decision = byId('bci-decision');
    ui.decisionStance = byId('bci-decision-stance');
    ui.decisionWhy = byId('bci-decision-why');
    ui.braid = byId('bci-braid');
    ui.braidPlot = byId('bci-braid-plot');
    ui.braidScale = byId('bci-braid-scale');
    ui.braidUnit = byId('bci-braid-unit');
    ui.braidReadout = byId('bci-braid-readout');
    ui.braidFoot = byId('bci-braid-foot');
    ui.braidList = byId('bci-braid-list');
    ui.chips = byId('bci-query-chips');
    ui.panelFoot = byId('bci-panel-foot');
    ui.screenControls = byId('bci-screen-controls');
    ui.sponsor = byId('bci-sponsor-filter');
    ui.intervention = byId('bci-intervention-filter');
    ui.studyType = byId('bci-study-type-filter');
    ui.pcFrom = byId('bci-pc-from');
    ui.pcTo = byId('bci-pc-to');
    ui.facets = byId('bci-facets');
    ui.cohort = byId('bci-cohort');
    ui.cohortInput = byId('bci-cohort-input');
    ui.cohortRun = byId('bci-cohort-run');
    ui.review = byId('bci-review-filter');
    ui.reviewControl = byId('bci-review-control');
    ui.searchControl = document.querySelector('label[for="bci-search"]');
    ui.searchLabel = ui.searchControl && ui.searchControl.querySelector('.bci-control-label');
    ui.conditionControl = document.querySelector('label[for="bci-condition-filter"]');
    ui.phaseControl = document.querySelector('label[for="bci-phase-filter"]');
    ui.statusControl = document.querySelector('label[for="bci-status-filter"]');
    ui.studyTypeControl = document.querySelector('label[for="bci-study-type-filter"]');
  }
  function setBiText(node, en, zh) {
    var english = node && node.querySelector('.l-en'), chinese = node && node.querySelector('.l-zh');
    if (english && chinese) { text(english, en); text(chinese, zh); return; }
    if (node) text(node, tr(en, zh));
  }
  function isScreenMode() { return state.mode === 'screen'; }
  function isPeerMode() { return state.mode === 'peers'; }
  function isListMode() { return !isPeerMode(); }

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
  function clockLabel(value) {
    var raw = clean(value);
    if (!fullTimestamp(raw)) return raw || tr('Not recorded', '未记录');
    return timestampLabel(raw.slice(0, 10)) + ' ' + raw.slice(11, 16) + ' UTC';
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
  function activeApi() {
    if (isProspectiveMode()) return PROSPECTIVE_API;
    if (isScreenMode()) return SCREEN_API;
    if (isPeerMode()) return PEER_API;
    return isChangeMode() ? CHANGE_API : MILESTONE_API;
  }
  function activeWindow() { return isProspectiveMode() ? PROSPECTIVE_WINDOWS[state.filters.window] : MILESTONE_WINDOWS[state.filters.window]; }
  function usesWindow() { return !isChangeMode() && !isScreenMode() && !isPeerMode(); }
  function activeNoun() {
    if (isProspectiveMode()) return tr('first-seen observations', '首次观测记录');
    if (isScreenMode()) return tr('matching trials', '匹配试验');
    if (isPeerMode()) return tr('compared trials', '对照试验');
    return isChangeMode() ? tr('recorded field changes', '已记录字段变更') : tr('registry milestones', '登记里程碑');
  }
  function activeSingularNoun() {
    if (isProspectiveMode()) return tr('first-seen observation', '首次观测记录');
    if (isScreenMode()) return tr('matching trial', '匹配试验');
    if (isPeerMode()) return tr('compared trial', '对照试验');
    return isChangeMode() ? tr('recorded field change', '已记录字段变更') : tr('registry milestone', '登记里程碑');
  }
  function modeTitle() {
    if (isProspectiveMode()) return tr('First-seen Tape', '首次观测记录');
    if (isScreenMode()) return tr('Trial Screen', '试验筛选');
    if (isPeerMode()) return tr('Peer Matrix', '方案对照');
    return isChangeMode() ? tr('Change Tape', '变更记录') : tr('Milestone monitor', '里程碑监测');
  }
  function modeKicker() {
    if (isProspectiveMode()) return tr('Observed between successful polls', '成功轮询之间的观测');
    if (isScreenMode()) return tr('Exactly the filters you set', '完全按你设定的条件');
    if (isPeerMode()) return tr('Exactly the trials you listed', '完全按你列出的试验');
    return isChangeMode() ? tr('Replayed from the record history', '按记录历史重放') : tr('Registry-recorded dates', '登记记录日期');
  }
  function defaultFilters() { return { field: 'primary_completion', change_kind: '', prospective_change_kind: '', window: '90', q: '', phase: '', status: '', condition: '', sponsor: '', intervention: '', study_type: '', pc_from: '', pc_to: '', review_state: 'all' }; }
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
  function historyVersionUrl(id, version) { return 'https://clinicaltrials.gov/study/' + encodeURIComponent(id) + '?a=' + String(version) + '&tab=history'; }
  // Every ceiling this product may not raise, checked on every page. The named
  // uses are pinned; the list may grow, but it may never shed one of these.
  var AUTHORITY_MUST_FORBID = ['originate_signal', 'rank_security', 'select_security', 'size_position', 'gate_decision', 'execute_trade', 'raise_authority'];
  function validCeilingAuthority(authority) {
    var ceiling = valueAt(authority, 'maximum_authority'), forbidden = valueAt(authority, 'forbidden_uses');
    if (!authority || typeof authority !== 'object' || authority.decision_authority !== false) return false;
    if (ceiling != null && clean(ceiling) !== 'A1_EXPLAIN') return false;
    if (JSON.stringify(valueAt(authority, 'allowed_uses')) !== JSON.stringify(AUTHORITY_ALLOWED_USES)) return false;
    if (!Array.isArray(forbidden)) return false;
    return AUTHORITY_MUST_FORBID.every(function (use) { return forbidden.indexOf(use) >= 0; });
  }
  function utf8Length(value) { return new TextEncoder().encode(value).length; }
  function validTapeValueEntry(entry) {
    if (!entry || typeof entry !== 'object' || Object.keys(entry).sort().join('|') !== 'state|unavailable_reason|value_byte_length|value_json|value_truncated') return false;
    var entryState = clean(valueAt(entry, 'state')), valueJson = valueAt(entry, 'value_json'), byteLength = valueAt(entry, 'value_byte_length'), truncated = valueAt(entry, 'value_truncated'), reason = valueAt(entry, 'unavailable_reason');
    if (!Number.isSafeInteger(byteLength) || byteLength < 0 || byteLength > 16777216 || typeof truncated !== 'boolean') return false;
    if (entryState === 'present') {
      if (typeof valueJson !== 'string' || !valueJson || reason !== null) return false;
      var shownBytes = utf8Length(valueJson);
      if (shownBytes > 4096) return false;
      return truncated ? byteLength > 4096 : byteLength === shownBytes;
    }
    if (entryState === 'missing') return valueJson === null && byteLength === 0 && truncated === false && reason === null;
    return entryState === 'unavailable' && valueJson === null && truncated === false && (reason === 'tape_value_budget_exhausted' || reason === 'value_bytes_not_representable');
  }
  function validTapeExtension(change, versions) {
    var exact = valueAt(change, 'exact_values'), lineage = valueAt(change, 'correction_lineage');
    if (typeof exact === 'undefined' && typeof lineage === 'undefined') return true;
    if (!exact || typeof exact !== 'object' || !lineage || typeof lineage !== 'object') return false;
    if (Object.keys(exact).sort().join('|') !== 'after|before|source_pointer' || Object.keys(lineage).sort().join('|') !== 'correction_assessed|predecessor_basis|predecessor_exact_operation_index|predecessor_source_version|relation') return false;
    var operation = clean(valueAt(change, 'op')), beforeState = clean(valueAt(change, 'before_state')), afterState = clean(valueAt(change, 'after_state'));
    var beforeValue = valueAt(exact, 'before'), afterValue = valueAt(exact, 'after'), pointer = valueAt(exact, 'source_pointer'), relation = clean(valueAt(lineage, 'relation')), basis = clean(valueAt(lineage, 'predecessor_basis')), predecessorVersion = valueAt(lineage, 'predecessor_source_version'), predecessorIndex = valueAt(lineage, 'predecessor_exact_operation_index'), beforeVersion = valueAt(versions, 'before');
    if (typeof pointer !== 'string' || utf8Length(pointer) > 512 || !/^(?:\/(?:[^~/]|~[01])*)+$/.test(pointer) || !validTapeValueEntry(beforeValue) || !validTapeValueEntry(afterValue) || clean(valueAt(beforeValue, 'state')) !== beforeState || clean(valueAt(afterValue, 'state')) !== afterState || valueAt(lineage, 'correction_assessed') !== false) return false;
    if (basis === 'none') return operation === 'add' && relation === 'no_prior_recorded_value' && predecessorVersion === null && predecessorIndex === null;
    if (!Number.isSafeInteger(predecessorVersion) || predecessorVersion < 1 || predecessorVersion > beforeVersion || relation !== (operation === 'remove' ? 'clears_prior_recorded_value' : 'supersedes_prior_recorded_value')) return false;
    if (basis === 'before_version_record') return operation !== 'add' && predecessorVersion === beforeVersion && predecessorIndex === null;
    return basis === 'prior_tape_row' && Number.isSafeInteger(predecessorIndex) && predecessorIndex >= 0 && predecessorIndex < 4096;
  }
  function validTapeChange(change) {
    var versions = valueAt(change, 'source_versions'), before = valueAt(versions, 'before'), after = valueAt(versions, 'after');
    var operation = clean(valueAt(change, 'op')), states = TAPE_OPS[operation], index = valueAt(change, 'exact_operation_index');
    var fieldClass = clean(valueAt(change, 'field_class')), reviewState = clean(valueAt(change, 'review_state')), resolution = clean(valueAt(change, 'semantic_resolution'));
    return !!change && typeof change === 'object' && CHANGE_KIND_VALUES[fieldClass] === true && !!states &&
      clean(valueAt(change, 'before_state')) === states[0] && clean(valueAt(change, 'after_state')) === states[1] &&
      (reviewState === 'not_required' || reviewState === 'needs_review') &&
      (fieldClass === 'endpoint_record_delta' ? (reviewState === 'needs_review' && resolution === 'unresolved') : (reviewState === 'not_required' && resolution === 'registry_field_class_only')) &&
      Number.isSafeInteger(index) && index >= 0 && index < 4096 &&
      !!versions && typeof versions === 'object' && Number.isSafeInteger(before) && before >= 1 && Number.isSafeInteger(after) && after === before + 1 &&
      fullTimestamp(valueAt(change, 'observed_at')) &&
      valueAt(change, 'protocol_change_asserted') === false && valueAt(change, 'materiality_assessed') === false && valueAt(change, 'correction_assessed') === false && validTapeExtension(change, versions);
  }
  function validTapeItem(item) {
    var trial = valueAt(item, 'trial');
    return !!item && typeof item === 'object' && validTrial(trial) && validTapeChange(valueAt(item, 'change')) && validCeilingAuthority(valueAt(item, 'authority'));
  }
  function validateChangeEnvelope(payload) {
    var pagination = valueAt(payload, 'pagination'), query = valueAt(payload, 'query'), coverage = valueAt(payload, 'change_tape_coverage'), payloadAsOf = valueAt(payload, 'as_of');
    if (!validMeta(payload) || !Array.isArray(payload.change_tape) || !pagination || typeof pagination !== 'object' || !query || typeof query !== 'object' || !coverage || typeof coverage !== 'object') throw new Error('Invalid change tape contract');
    if (pagination.limit !== PAGE_LIMIT || !Number.isSafeInteger(pagination.total) || pagination.total < 0 || (pagination.next_cursor != null && (typeof pagination.next_cursor !== 'string' || !/^[A-Za-z0-9_-]{1,384}$/.test(pagination.next_cursor)))) throw new Error('Invalid change tape pagination contract');
    if (!fullTimestamp(payloadAsOf) || clean(valueAt(coverage, 'class')) !== 'replay_verified_record_history' || clean(valueAt(coverage, 'selection_basis')) !== 'committed_trial_record' ||
      !Number.isSafeInteger(valueAt(coverage, 'available_trials')) || valueAt(coverage, 'available_trials') < 0 ||
      !Number.isSafeInteger(valueAt(coverage, 'unavailable_trials')) || valueAt(coverage, 'unavailable_trials') < 0 ||
      clean(valueAt(coverage, 'prospective_state')) !== 'unavailable_without_retained_activation_proofs') throw new Error('Invalid change tape coverage contract');
    if (!changeQueryMatchesCurrentFilters(query)) throw new Error('Change tape query binding mismatch');
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
  function tapeNctFilter() { return isTrialId(state.filters.q) ? clean(state.filters.q) : ''; }
  function changeQueryMatchesCurrentFilters(query) {
    if (!query || typeof query !== 'object') return false;
    var expected = {
      nct_id: tapeNctFilter(),
      field_class: state.filters.change_kind || 'all',
      review_state: state.filters.review_state || 'all'
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
  function validateMilestoneEnvelope(payload) {
    if (!validEnvelope(payload)) throw new Error('Invalid milestone list contract');
    var query = valueAt(payload, 'query');
    if (!queryMatchesCurrentFilters(query)) throw new Error('Milestone query binding mismatch');
    if (!effectiveWindowIsSane(valueAt(payload, 'effective_window'), clean(valueAt(query, 'window')))) throw new Error('Invalid effective registry window');
  }
  function changeIdentity(item) {
    var change = valueAt(item, 'change'), versions = valueAt(change, 'source_versions');
    return nctOf(valueAt(item, 'trial')) + '|' + valueAt(versions, 'before') + '|' + valueAt(versions, 'after') + '|' + valueAt(change, 'exact_operation_index');
  }
  function validateChangePage(items, existingRows) {
    if (!Array.isArray(items)) throw new Error('Invalid change page');
    var seen = {};
    arr(existingRows).forEach(function (item) { seen[changeIdentity(item)] = true; });
    return items.map(function (item) {
      if (!validTapeItem(item)) throw new Error('Invalid registry change record');
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
  function screenIdentity(item) { return clean(valueAt(item, 'nct_id')); }
  function rowIdentity(item) {
    if (isProspectiveMode()) return prospectiveIdentity(item);
    if (isScreenMode() || isPeerMode()) return screenIdentity(item);
    return isChangeMode() ? changeIdentity(item) : milestoneIdentity(item);
  }
  function rowTrial(item) { return (isScreenMode() || isPeerMode()) ? item : valueAt(item, 'trial'); }
  function selectedRow() {
    return state.rows.filter(function (item) { return state.selectedKey && rowIdentity(item) === state.selectedKey; })[0] ||
      state.rows.filter(function (item) { return nctOf(rowTrial(item)) === state.selectedId; })[0];
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
    var pageSize = payload.change_tape.length, loadedBefore = arr(existingRows).length, loadedAfter = loadedBefore + pageSize;
    var total = pagination.total, nextCursor = clean(pagination.next_cursor), previousTotal = valueAt(previous, 'total');
    if (pageSize > pagination.limit || loadedAfter > total) throw new Error('Invalid registry change page bounds');
    if (total > loadedBefore && pageSize === 0) throw new Error('Empty registry change page before total');
    if (nextCursor && loadedAfter >= total) throw new Error('Unexpected registry change cursor');
    if (!nextCursor && loadedAfter !== total) throw new Error('Incomplete registry change pagination');
    if (requestedCursor && nextCursor === requestedCursor) throw new Error('Repeated registry change cursor');
    if (loadedBefore && (!Number.isSafeInteger(previousTotal) || previousTotal !== total)) throw new Error('Registry change total changed during pagination');
  }
  /* ---- Trial Screen: literal filters, generation-bound pagination ---- */
  var SOURCE_LOCATOR = /^\/protocolSection\/[A-Za-z]+\/[A-Za-z]+$/;
  function factState(fact) { return clean(valueAt(fact, 'state')); }
  function knownState(fact) { return MISSINGNESS_STATES.indexOf(factState(fact)) >= 0; }
  function observed(fact) { return factState(fact) === 'observed'; }
  function validScreenRow(row) {
    var completion = valueAt(row, 'primary_completion'), source = valueAt(row, 'source'), id = clean(valueAt(row, 'nct_id'));
    if (!row || typeof row !== 'object' || !isTrialId(id)) return false;
    if (!['brief_title', 'official_title', 'overall_status', 'study_type', 'phases', 'sponsor', 'enrollment', 'conditions', 'interventions'].every(function (name) { return knownState(valueAt(row, name)); })) return false;
    if (!completion || typeof completion !== 'object' || !knownState(completion)) return false;
    if (observed(completion)) {
      var interval = valueAt(completion, 'interval');
      if (!clean(valueAt(completion, 'literal')) || !interval || typeof interval !== 'object' || !fullDate(valueAt(interval, 'start')) || !fullDate(valueAt(interval, 'end')) || clean(valueAt(interval, 'start')) > clean(valueAt(interval, 'end'))) return false;
      if (['year', 'month', 'day'].indexOf(clean(valueAt(completion, 'precision'))) < 0) return false;
    }
    return !!source && typeof source === 'object' && clean(valueAt(source, 'url')) === 'https://clinicaltrials.gov/study/' + encodeURIComponent(id) && fullTimestamp(valueAt(source, 'retrieved_at'));
  }
  function screenQueryMatchesCurrentFilters(query) {
    if (!query || typeof query !== 'object') return false;
    if (clean(valueAt(query, 'filter_composition')) !== 'literal_and' || clean(valueAt(query, 'primary_completion_matching')) !== 'full_interval_containment') return false;
    var expected = {
      sponsor: state.filters.sponsor, intervention: state.filters.intervention, study_type: state.filters.study_type,
      phase: state.filters.phase, status: state.filters.status, condition: state.filters.condition,
      primary_completion_from: state.filters.pc_from, primary_completion_to: state.filters.pc_to
    };
    return Object.keys(expected).every(function (key) {
      var expectedValue = expected[key], actualValue = valueAt(query, key);
      if (!expectedValue) return actualValue == null || clean(actualValue) === '';
      return normalizedQueryValue(actualValue) === normalizedQueryValue(expectedValue);
    });
  }
  function validateScreenEnvelope(payload) {
    var pagination = valueAt(payload, 'pagination'), coverage = valueAt(payload, 'coverage'), source = valueAt(payload, 'source'), rowCount = valueAt(payload, 'row_count');
    if (!payload || typeof payload !== 'object' || clean(payload.contract_id) !== 'trial_screen_read_model.v1' || clean(payload.schema_version) !== '1.0.0' || !fullTimestamp(payload.as_of)) throw new Error('Invalid trial screen contract');
    if (!Array.isArray(payload.rows) || !pagination || typeof pagination !== 'object' || !coverage || typeof coverage !== 'object' || !source || typeof source !== 'object') throw new Error('Invalid trial screen contract');
    if (clean(valueAt(source, 'name')) !== 'ClinicalTrials.gov' || clean(valueAt(coverage, 'class')) !== 'current_only') throw new Error('Invalid trial screen coverage contract');
    if (clean(payload.sort_order) !== 'primary_completion_interval_ascending_then_nct_id') throw new Error('Invalid trial screen sort contract');
    if (!Number.isSafeInteger(pagination.limit) || pagination.limit !== PAGE_LIMIT || !Number.isSafeInteger(pagination.offset) || pagination.offset < 0 ||
      !Number.isSafeInteger(pagination.total) || pagination.total < 0 || !Number.isSafeInteger(pagination.returned) || pagination.returned !== payload.rows.length ||
      !Number.isSafeInteger(rowCount) || rowCount !== payload.rows.length ||
      (pagination.next_cursor != null && (typeof pagination.next_cursor !== 'string' || !/^[A-Za-z0-9_-]{1,384}$/.test(pagination.next_cursor)))) throw new Error('Invalid trial screen pagination contract');
    if (!Number.isSafeInteger(valueAt(coverage, 'matched')) || valueAt(coverage, 'matched') !== pagination.total) throw new Error('Invalid trial screen coverage contract');
    if (!validCeilingAuthority(valueAt(payload, 'authority'))) throw new Error('Invalid trial screen authority contract');
    if (!screenQueryMatchesCurrentFilters(valueAt(payload, 'query'))) throw new Error('Trial screen query binding mismatch');
  }
  function validateScreenPage(items, existingRows) {
    if (!Array.isArray(items)) throw new Error('Invalid trial screen page');
    var seen = {};
    arr(existingRows).forEach(function (item) { seen[screenIdentity(item)] = true; });
    return items.map(function (item) {
      if (!validScreenRow(item)) throw new Error('Invalid trial screen row');
      var identity = screenIdentity(item);
      if (seen[identity]) throw new Error('Duplicate trial screen identity');
      seen[identity] = true;
      return item;
    });
  }
  function validateScreenPagination(payload, existingRows, requestedCursor, previousPayload) {
    var pagination = valueAt(payload, 'pagination'), previous = valueAt(previousPayload, 'pagination');
    var pageSize = payload.rows.length, loadedBefore = arr(existingRows).length, loadedAfter = loadedBefore + pageSize;
    var total = pagination.total, nextCursor = clean(pagination.next_cursor), previousTotal = valueAt(previous, 'total');
    if (pagination.offset !== loadedBefore) throw new Error('Invalid trial screen offset');
    if (pageSize > pagination.limit || loadedAfter > total) throw new Error('Invalid trial screen page bounds');
    if (total > loadedBefore && pageSize === 0) throw new Error('Empty trial screen page before total');
    if (nextCursor && loadedAfter >= total) throw new Error('Unexpected trial screen cursor');
    if (!nextCursor && loadedAfter !== total) throw new Error('Incomplete trial screen pagination');
    if (requestedCursor && nextCursor === requestedCursor) throw new Error('Repeated trial screen cursor');
    if (loadedBefore && (!Number.isSafeInteger(previousTotal) || previousTotal !== total)) throw new Error('Trial screen total changed during pagination');
  }
  function validateFacetsEnvelope(payload) {
    var semantics = valueAt(payload, 'facet_semantics'), facets = valueAt(payload, 'facets');
    if (!payload || typeof payload !== 'object' || clean(payload.contract_id) !== 'trial_screen_facets_read_model.v1' || clean(payload.scope) !== 'current_configured_snapshot_generation') throw new Error('Invalid facet contract');
    if (!semantics || typeof semantics !== 'object' || clean(valueAt(semantics, 'filter_composition')) !== 'literal_and_self_excluding_dimension' || clean(valueAt(semantics, 'counting_unit')) !== 'unique_trial' || valueAt(semantics, 'partial_results') !== false) throw new Error('Invalid facet semantics contract');
    if (!Array.isArray(facets) || facets.length !== FACET_DIMENSIONS.length) throw new Error('Invalid facet contract');
    facets.forEach(function (facet, index) {
      var buckets = valueAt(facet, 'buckets'), missingness = valueAt(facet, 'missingness');
      if (clean(valueAt(facet, 'dimension')) !== FACET_DIMENSIONS[index]) throw new Error('Invalid facet dimension order');
      if (['additive', 'non_additive'].indexOf(clean(valueAt(facet, 'additivity'))) < 0) throw new Error('Invalid facet additivity');
      if (!Number.isSafeInteger(valueAt(facet, 'base_matched')) || valueAt(facet, 'base_matched') < 0) throw new Error('Invalid facet base count');
      if (!missingness || typeof missingness !== 'object' || !MISSINGNESS_STATES.every(function (name) { return Number.isSafeInteger(valueAt(missingness, name)) && valueAt(missingness, name) >= 0; })) throw new Error('Invalid facet missingness contract');
      if (!Array.isArray(buckets) || !buckets.every(function (bucket) { return !!bucket && typeof bucket === 'object' && clean(valueAt(bucket, 'token')) && Number.isSafeInteger(valueAt(bucket, 'count')) && valueAt(bucket, 'count') >= 0; })) throw new Error('Invalid facet bucket contract');
    });
    if (!validCeilingAuthority(valueAt(payload, 'authority'))) throw new Error('Invalid facet authority contract');
    if (!screenQueryMatchesCurrentFilters(valueAt(payload, 'query'))) throw new Error('Facet query binding mismatch');
  }

  /* ---- Peer Matrix: the cohort is exactly what the user listed ---- */
  function validFieldEvidence(evidence) {
    var locators = valueAt(evidence, 'source_field_locators');
    return !!evidence && typeof evidence === 'object' && !!clean(valueAt(evidence, 'state')) && !!clean(valueAt(evidence, 'transform')) &&
      Array.isArray(locators) && locators.length > 0 && locators.length <= 8 && locators.every(function (path) { return SOURCE_LOCATOR.test(clean(path)); });
  }
  function validPeerRow(row) {
    var fieldEvidence = valueAt(row, 'field_evidence'), dates = valueAt(row, 'dates'), evidence = valueAt(row, 'evidence'), id = clean(valueAt(row, 'nct_id'));
    if (!row || typeof row !== 'object' || !isTrialId(id) || !fieldEvidence || typeof fieldEvidence !== 'object' || !dates || typeof dates !== 'object') return false;
    if (!evidence || typeof evidence !== 'object' || clean(valueAt(evidence, 'provider')) !== 'ClinicalTrials.gov' || clean(valueAt(evidence, 'record_id')) !== id) return false;
    return Object.keys(fieldEvidence).every(function (name) { return validFieldEvidence(valueAt(fieldEvidence, name)); });
  }
  function validatePeerEnvelope(payload) {
    var coverage = valueAt(payload, 'coverage'), pagination = valueAt(payload, 'pagination'), cohort = valueAt(payload, 'cohort_nct_ids'), uncovered = valueAt(payload, 'uncovered_nct_ids');
    if (!payload || typeof payload !== 'object' || clean(payload.contract_id) !== 'trial_peer_set.v1' || clean(payload.schema_version) !== '1.0.0' || !fullTimestamp(payload.as_of)) throw new Error('Invalid peer set contract');
    if (!Array.isArray(payload.trials) || !Array.isArray(cohort) || !Array.isArray(uncovered) || !pagination || typeof pagination !== 'object' || !coverage || typeof coverage !== 'object') throw new Error('Invalid peer set contract');
    if (clean(valueAt(coverage, 'class')) !== 'current_only' || clean(valueAt(coverage, 'selection_basis')) !== 'explicit_nct_id_cohort') throw new Error('Invalid peer set coverage contract');
    if (valueAt(coverage, 'requested_count') !== cohort.length || valueAt(coverage, 'uncovered_count') !== uncovered.length || !Number.isSafeInteger(valueAt(coverage, 'covered_count'))) throw new Error('Invalid peer set coverage contract');
    if (!Number.isSafeInteger(pagination.total) || pagination.total !== valueAt(coverage, 'covered_count')) throw new Error('Invalid peer set pagination contract');
    // The resolver may never widen, narrow, or reorder the cohort the user typed.
    if (cohort.join('|') !== state.cohort.slice().sort().join('|')) throw new Error('Peer cohort binding mismatch');
    if (!uncovered.every(function (id) { return cohort.indexOf(clean(id)) >= 0; })) throw new Error('Peer cohort binding mismatch');
    if (!validCeilingAuthority(valueAt(payload, 'authority'))) throw new Error('Invalid peer set authority contract');
  }
  function validatePeerPage(items, existingRows) {
    if (!Array.isArray(items)) throw new Error('Invalid peer set page');
    var seen = {};
    arr(existingRows).forEach(function (item) { seen[screenIdentity(item)] = true; });
    return items.map(function (item) {
      if (!validPeerRow(item)) throw new Error('Invalid peer set row');
      var identity = screenIdentity(item);
      if (seen[identity]) throw new Error('Duplicate peer set identity');
      if (state.cohort.indexOf(identity) < 0) throw new Error('Peer row outside the requested cohort');
      seen[identity] = true;
      return item;
    });
  }
  function validatePeerPagination(payload, existingRows, requestedCursor, previousPayload) {
    var pagination = valueAt(payload, 'pagination'), previous = valueAt(previousPayload, 'pagination');
    var pageSize = payload.trials.length, loadedBefore = arr(existingRows).length, loadedAfter = loadedBefore + pageSize;
    var total = pagination.total, nextCursor = clean(pagination.next_cursor), previousTotal = valueAt(previous, 'total');
    if (pageSize > pagination.limit || loadedAfter > total) throw new Error('Invalid peer set page bounds');
    if (total > loadedBefore && pageSize === 0) throw new Error('Empty peer set page before total');
    if (nextCursor && loadedAfter >= total) throw new Error('Unexpected peer set cursor');
    if (!nextCursor && loadedAfter !== total) throw new Error('Incomplete peer set pagination');
    if (requestedCursor && nextCursor === requestedCursor) throw new Error('Repeated peer set cursor');
    if (loadedBefore && (!Number.isSafeInteger(previousTotal) || previousTotal !== total)) throw new Error('Peer set total changed during pagination');
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
    state.filters.sponsor = clean(params.get('sponsor')).slice(0, 240);
    state.filters.intervention = clean(params.get('intervention')).slice(0, 240);
    state.filters.study_type = STUDY_TYPE_VALUES[clean(params.get('study_type')).toUpperCase()] ? clean(params.get('study_type')).toUpperCase() : '';
    state.filters.pc_from = fullDate(params.get('pc_from')) ? clean(params.get('pc_from')) : '';
    state.filters.pc_to = fullDate(params.get('pc_to')) ? clean(params.get('pc_to')) : '';
    state.filters.review_state = TAPE_REVIEW_VALUES[clean(params.get('review_state'))] ? clean(params.get('review_state')) : 'all';
    state.cohort = parseCohort(params.get('cohort'));
    state.cohortText = state.cohort.join('\n');
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
    assign('sponsor', state.filters.sponsor, true);
    assign('intervention', state.filters.intervention, true);
    assign('study_type', state.filters.study_type, true);
    assign('pc_from', state.filters.pc_from, true);
    assign('pc_to', state.filters.pc_to, true);
    assign('review_state', state.filters.review_state === 'all' ? '' : state.filters.review_state, true);
    assign('cohort', isPeerMode() ? state.cohort.join(',') : '', true);
    window.history.replaceState(null, '', url.pathname + (params.toString() ? '?' + params.toString() : '') + url.hash);
  }
  function paintChangeKindOptions() {
    var allLabel = isProspectiveMode() ? tr('All observed fields', '所有观测字段') : tr('All registry fields', '所有登记字段');
    clearChildren(ui.changeKind);
    var allOption = el('option', '', allLabel);
    allOption.value = '';
    ui.changeKind.appendChild(allOption);
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
    ui.sponsor.value = state.filters.sponsor;
    ui.intervention.value = state.filters.intervention;
    ui.studyType.value = state.filters.study_type;
    ui.pcFrom.value = state.filters.pc_from;
    ui.pcTo.value = state.filters.pc_to;
    ui.review.value = state.filters.review_state;
    ui.cohortInput.value = state.cohortText;
    ui.screenControls.hidden = !isScreenMode();
    ui.cohort.hidden = !isPeerMode();
    ui.reviewControl.hidden = !isChangeMode();
    ui.windowControl.hidden = !usesWindow();
    ui.searchControl.hidden = isPeerMode();
    ui.conditionControl.hidden = isPeerMode() || isChangeMode();
    ui.phaseControl.hidden = isPeerMode() || isChangeMode() || (isScreenMode() && !!state.facets);
    ui.statusControl.hidden = isPeerMode() || isChangeMode() || (isScreenMode() && !!state.facets);
    ui.studyTypeControl.hidden = isScreenMode() && !!state.facets;
    if (isChangeMode()) setBiText(ui.searchLabel, 'Find one trial', '查找单个试验'); else setBiText(ui.searchLabel, 'Find a trial', '查找试验');
    ui.search.placeholder = isChangeMode()
      ? tr('NCT ID only', '仅限 NCT 编号')
      : (ui.search.getAttribute(lang() === 'zh' ? 'data-placeholder-zh' : 'data-placeholder-en') || '');
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
    ui.fieldControl.hidden = state.mode !== 'milestones';
    ui.changeKindControl.hidden = !(isChangeMode() || isProspectiveMode());
    text(ui.changeKindLabel, isProspectiveMode() ? tr('Observed field', '观测字段') : tr('Registry field', '登记字段'));
    ui.changeKind.setAttribute('aria-label', isProspectiveMode() ? tr('Observed field', '观测字段') : tr('Registry field', '登记字段'));
    text(ui.windowLabel, isProspectiveMode() ? tr('Observation window', '观测窗口') : tr('Record window', '记录窗口'));
    ui.windowControl.querySelector('.bci-window-options').setAttribute('aria-label', isProspectiveMode() ? tr('First-observed window', '首次观测窗口') : tr('Registry date window', '登记日期窗口'));
    text(ui.queueKicker, modeKicker());
    text(ui.queueTitle, modeTitle());
    text(ui.sourceNote, sourceNoteCopy());
  }
  function sourceNoteCopy() {
    if (isProspectiveMode()) return tr('First-seen observations show when our official registry collector observed a current record between two successful polls. They do not establish real-world timing, whether a protocol changed, business importance, catalyst status, a company link, an outcome estimate, or an action.', '首次观测记录显示官方登记采集器在两次成功轮询之间何时观测到当前记录。它不确定现实世界发生时间、方案是否变化、业务重要性、催化状态、公司关联、结果估计或行动。');
    if (isScreenMode()) return tr('Every filter is matched literally against the recorded field, with no widening and no ranking. A trial that does not record a field is never counted as matching it.', '每个筛选条件都按字面匹配已记录字段，不扩展、不排序。未记录某字段的试验不会被计为匹配。');
    if (isPeerMode()) return tr('You choose the cohort. This workspace never discovers peers, never links a trial to a company or a security, and never says which trial is better.', '对照名单由你决定。本工作台不会发现同类试验，不会把试验关联到公司或证券，也不会判断哪项试验更好。');
    if (isChangeMode()) return tr('Each row is one registry field change replayed from the recorded version history. A registry edit is not a protocol change and not a business event.', '每一行都是从已记录版本历史中重放的一次登记字段变更。登记修改不等于方案变更，也不等于业务事件。');
    return tr('Dates and field updates are recorded by ClinicalTrials.gov from study-sponsor and investigator submissions. A registry listing is not government validation. Review the source record—no trade call.', '日期和字段更新来自 ClinicalTrials.gov 所记录的研究申办方与研究者提交内容。登记收录不代表政府验证。请查看来源记录，不作交易判断。');
  }
  function localizeControls() {
    var labels = {
      'bci-phase-filter': { PHASE1: ['Phase 1', '一期'], PHASE2: ['Phase 2', '二期'], PHASE3: ['Phase 3', '三期'], PHASE4: ['Phase 4', '四期'] },
      'bci-status-filter': { RECRUITING: ['Recruiting', '招募中'], NOT_YET_RECRUITING: ['Not yet recruiting', '尚未招募'], ACTIVE_NOT_RECRUITING: ['Active, not recruiting', '进行中，未招募'], COMPLETED: ['Completed', '已完成'], TERMINATED: ['Terminated', '已终止'] }
    };
    [ui.field, ui.phase, ui.statusFilter, ui.studyType, ui.review].forEach(function (select) {
      if (!select) return;
      Array.prototype.slice.call(select.options).forEach(function (option) {
        var pair = labels[select.id] && labels[select.id][option.value];
        text(option, pair ? tr(pair[0], pair[1]) : (option.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || option.textContent));
      });
    });
    [ui.search, ui.condition, ui.sponsor, ui.intervention].forEach(function (input) {
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
    [ui.refresh, ui.inspectorClose, ui.brainLaunch, ui.cohortRun].forEach(function (button) {
      if (button) button.setAttribute('aria-label', button.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || button.textContent);
    });
    ui.queue.setAttribute('aria-label', activeNoun());
    ui.modeControl.setAttribute('aria-label', tr('Trial intelligence view', '试验智能视图'));
    ui.modeButtons.forEach(function (button) { button.setAttribute('aria-label', button.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || button.textContent); });
    setLoadMoreCopy();
  }
  function screenParams() {
    var params = new URLSearchParams();
    if (state.filters.sponsor) params.set('sponsor', state.filters.sponsor);
    if (state.filters.intervention) params.set('intervention', state.filters.intervention);
    if (state.filters.study_type) params.set('study_type', state.filters.study_type);
    if (state.filters.phase) params.set('phase', state.filters.phase);
    if (state.filters.status) params.set('status', state.filters.status);
    if (state.filters.condition) params.set('condition', state.filters.condition);
    if (state.filters.pc_from) params.set('primary_completion_from', state.filters.pc_from);
    if (state.filters.pc_to) params.set('primary_completion_to', state.filters.pc_to);
    return params;
  }
  function facetQueryString() { var params = screenParams().toString(); return params ? '?' + params : ''; }
  function queryUrl(cursor) {
    var params;
    if (isScreenMode()) {
      params = screenParams();
      params.set('limit', String(PAGE_LIMIT));
      if (cursor) params.set('cursor', cursor);
      return SCREEN_API + '?' + params.toString();
    }
    params = new URLSearchParams();
    params.set('limit', String(PAGE_LIMIT));
    if (isChangeMode()) {
      if (tapeNctFilter()) params.set('nct_id', tapeNctFilter());
      if (state.filters.change_kind) params.set('field_class', state.filters.change_kind);
      if (state.filters.review_state && state.filters.review_state !== 'all') params.set('review_state', state.filters.review_state);
      if (cursor) params.set('cursor', cursor);
      return CHANGE_API + '?' + params.toString();
    }
    params.set('window', activeWindow());
    if (isProspectiveMode()) {
      if (activeChangeKind()) params.set('change_kind', activeChangeKind());
    } else params.set('milestone_kind', state.filters.field);
    if (state.filters.q) params.set('q', state.filters.q);
    if (state.filters.phase) params.set('phase', state.filters.phase);
    if (state.filters.status) params.set('status', state.filters.status);
    if (state.filters.condition) params.set('condition', state.filters.condition);
    if (cursor) params.set('cursor', cursor);
    return activeApi() + '?' + params.toString();
  }
  function parseCohort(raw) {
    return unique(str(raw).toUpperCase().split(/[^A-Z0-9]+/).filter(function (token) { return TRIAL_ID.test(token); })).slice(0, PEER_MAX_COHORT);
  }
  function postJson(url, body, signal) {
    return withAuth({ Accept: 'application/json', 'Content-Type': 'application/json' }).then(function (headers) {
      return fetch(url, { method: 'POST', headers: headers, credentials: 'same-origin', cache: 'no-store', signal: signal, body: JSON.stringify(body) });
    }).then(function (response) {
      if (!response.ok) { var error = new Error('HTTP ' + response.status); error.status = response.status; throw error; }
      return response.json();
    });
  }
  function requestPage(cursor, signal) {
    if (!isPeerMode()) return fetchJson(queryUrl(cursor), signal);
    var body = { nct_ids: state.cohort.slice(), limit: PAGE_LIMIT };
    if (cursor) body.cursor = cursor;
    return postJson(PEER_API, body, signal);
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
  function recordStateLabel(name) {
    var labels = { missing: ['not on the record', '不在记录中'], present: ['on the record', '在记录中'] };
    var pair = labels[clean(name)] || labels.missing; return tr(pair[0], pair[1]);
  }
  function tapeOpLabel(operation) {
    var labels = { add: ['Field added', '字段新增'], remove: ['Field removed', '字段移除'], replace: ['Field value replaced', '字段值被替换'] };
    var pair = labels[clean(operation)] || labels.replace; return tr(pair[0], pair[1]);
  }
  function tapeValueLabel(entry) {
    var entryState = clean(valueAt(entry, 'state'));
    if (entryState === 'missing') return tr('Not on the record', '记录中无此字段');
    if (entryState === 'unavailable') return tr('Not available to show', '暂不可展示');
    return valueAt(entry, 'value_json');
  }
  function tapeValueSide(label, entry) {
    var side = el('span', 'bci-tape-value is-' + clean(valueAt(entry, 'state')));
    side.appendChild(el('small', '', label));
    side.appendChild(el('code', '', tapeValueLabel(entry)));
    if (valueAt(entry, 'value_truncated') === true) side.appendChild(el('em', '', tr('Prefix shown · original ', '显示精确前缀 · 原值 ') + valueAt(entry, 'value_byte_length') + tr(' bytes', ' 字节')));
    return side;
  }
  function tapeExactDelta(exact, detail) {
    var delta = el('span', 'bci-tape-exact' + (detail ? ' is-detail' : ''));
    delta.appendChild(tapeValueSide(tr('Before', '之前'), valueAt(exact, 'before')));
    delta.appendChild(el('b', '', '\u2192'));
    delta.appendChild(tapeValueSide(tr('After', '之后'), valueAt(exact, 'after')));
    return delta;
  }
  function tapeLineageLabel(lineage) {
    var basis = clean(valueAt(lineage, 'predecessor_basis')), version = valueAt(lineage, 'predecessor_source_version'), index = valueAt(lineage, 'predecessor_exact_operation_index');
    if (basis === 'none') return tr('No earlier recorded value', '没有更早的记录值');
    if (basis === 'prior_tape_row') return lang() === 'zh' ? '接续 ' + 'V' + version + ' · 变更 ' + index : 'Supersedes V' + version + ' · change ' + index;
    return lang() === 'zh' ? '接续 ' + 'V' + version + ' 中的记录值' : 'Supersedes the value in V' + version;
  }
  function makeChangeRow(item, index) {
    var trial = item.trial, change = item.change, versions = change.source_versions, id = nctOf(trial);
    var rowKey = changeIdentity(item), selected = rowKey === state.selectedKey, button = el('button', 'bci-trial bci-tape-card' + (selected ? ' is-selected' : ''));
    button.type = 'button'; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', selected ? 'true' : 'false'); button.setAttribute('data-trial-id', id); button.setAttribute('data-row-key', rowKey); button.tabIndex = index === 0 ? 0 : -1;
    var main = el('span', 'bci-trial-main'), line = el('span', 'bci-trial-topline');
    line.appendChild(el('span', 'bci-trial-id', id));
    line.appendChild(el('span', 'bci-registry-kind', historyKindLabel(change.field_class)));
    if (change.review_state === 'needs_review') line.appendChild(el('span', 'bci-tape-review', tr('Not checked yet', '尚未核对')));
    main.appendChild(line);
    if (!index || nctOf(valueAt(state.rows[index - 1], 'trial')) !== id) main.appendChild(el('span', 'bci-trial-title', titleOf(trial)));
    if (valueAt(change, 'exact_values')) main.appendChild(tapeExactDelta(valueAt(change, 'exact_values'), false));
    else if (change.op !== 'replace') {
      var delta = el('span', 'bci-tape-delta');
      delta.setAttribute('aria-label', tapeOpLabel(change.op) + ' · ' + recordStateLabel(change.before_state) + ' \u2192 ' + recordStateLabel(change.after_state));
      delta.appendChild(el('span', '', recordStateLabel(change.before_state)));
      delta.appendChild(el('b', '', '\u2192'));
      delta.appendChild(el('span', '', recordStateLabel(change.after_state)));
      main.appendChild(delta);
    }
    main.appendChild(el('span', 'bci-tape-path', 'V' + versions.before + ' \u2192 V' + versions.after + ' \u00b7 ' + tapeOpLabel(change.op)));
    button.appendChild(main);
    var clocks = el('span', 'bci-tape-clocks');
    clocks.appendChild(el('b', '', tr('Posted ', '发布 ') + clockLabel(clean(valueAt(trial, 'updated_at')))));
    clocks.appendChild(el('i', '', tr('Verified ', '核验 ') + clockLabel(change.observed_at)));
    button.appendChild(clocks);
    button.addEventListener('click', function () { selectTrial(id, trial, valueAt(item, 'evidence'), true, button, rowKey); });
    return button;
  }
  function screenText(fact, fallback) { return observed(fact) ? clean(valueAt(fact, 'value')) : fallback; }
  function missingLabel(fact) {
    var labels = {
      source_null: ['left blank on the record', '记录中留空'], source_missing: ['not on the record', '不在记录中'],
      not_applicable: ['does not apply', '不适用'], parser_degraded: ['could not be read', '无法读取'],
      license_restricted: ['not available to show', '不可展示']
    };
    var pair = labels[factState(fact)]; return pair ? tr(pair[0], pair[1]) : tr('not on the record', '不在记录中');
  }
  function makeScreenRow(row, index) {
    var id = clean(row.nct_id), rowKey = screenIdentity(row), selected = rowKey === state.selectedKey;
    var button = el('button', 'bci-trial bci-screen-card' + (selected ? ' is-selected' : ''));
    button.type = 'button'; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', selected ? 'true' : 'false'); button.setAttribute('data-trial-id', id); button.setAttribute('data-row-key', rowKey); button.tabIndex = index === 0 ? 0 : -1;
    var main = el('span', 'bci-trial-main'), line = el('span', 'bci-trial-topline');
    line.appendChild(el('span', 'bci-trial-id', id));
    if (observed(row.phases) && arr(valueAt(row.phases, 'values')).length) line.appendChild(el('span', 'bci-registry-kind', arr(valueAt(row.phases, 'values')).map(phaseLabel).join(' · ')));
    if (observed(row.overall_status)) line.appendChild(el('span', 'bci-status-chip', statusLabel(clean(valueAt(row.overall_status, 'value')))));
    main.appendChild(line);
    main.appendChild(el('span', 'bci-trial-title', screenText(row.brief_title, '') || screenText(row.official_title, '') || tr('Untitled trial', '未命名试验')));
    // The five cues inline at tier one; full precision waits in the dossier.
    var cues = el('span', 'bci-cues'), sponsor = valueAt(row.sponsor, 'value'), enrollment = valueAt(row.enrollment, 'value');
    cues.appendChild(el('span', observed(row.sponsor) ? '' : 'is-missing', observed(row.sponsor) ? clean(valueAt(sponsor, 'name')) : tr('Sponsor ', '申办方') + missingLabel(row.sponsor)));
    cues.appendChild(el('span', observed(row.enrollment) ? '' : 'is-missing', observed(row.enrollment) ? tr(valueAt(enrollment, 'count') + ' enrolled', '入组 ' + valueAt(enrollment, 'count') + ' 人') : tr('Enrollment ', '入组') + missingLabel(row.enrollment)));
    if (observed(row.conditions) && arr(valueAt(row.conditions, 'values')).length) cues.appendChild(el('span', '', arr(valueAt(row.conditions, 'values')).slice(0, 2).join(' · ')));
    if (clean(valueAt(row.source, 'retrieved_at')).slice(0, 10) !== clean(valueAt(state.payload, 'as_of')).slice(0, 10)) cues.appendChild(el('span', '', tr('Read ', '读取于 ') + timestampLabel(clean(valueAt(row.source, 'retrieved_at')))));
    else if (clean(valueAt(row.source, 'last_update_posted_at'))) cues.appendChild(el('span', '', tr('Posted ', '发布于 ') + timestampLabel(clean(valueAt(row.source, 'last_update_posted_at')))));
    main.appendChild(cues);
    button.appendChild(main);
    var interval = el('span', 'bci-interval'), completion = row.primary_completion;
    if (observed(completion)) {
      interval.appendChild(el('strong', '', dateLabel(clean(valueAt(completion, 'literal')), clean(valueAt(completion, 'precision')))));
      interval.appendChild(typeBadge(clean(valueAt(completion, 'type'))));
      interval.setAttribute('data-precision', clean(valueAt(completion, 'precision')));
    } else {
      interval.appendChild(el('strong', '', tr('No date', '无日期')));
      interval.appendChild(el('span', '', missingLabel(completion)));
    }
    button.appendChild(interval);
    button.addEventListener('click', function () { selectTrial(id, null, valueAt(row, 'source'), true, button, rowKey); });
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
  /* ---- Peer Matrix: identity stays put, coverage stays visible ---- */
  function peerFieldLabel(name) {
    var labels = {
      status: ['Recruitment', '招募状态'], phases: ['Phase', '阶段'], enrollment: ['Enrollment', '入组人数'],
      dates: ['Primary completion', '主要完成'], arm_groups: ['Arms', '试验组'], endpoints: ['Primary endpoint', '主要终点'],
      site_count: ['Trial sites', '研究中心'], countries: ['Countries', '国家与地区']
    };
    var pair = labels[name] || labels.status; return tr(pair[0], pair[1]);
  }
  function peerFieldValue(row, name) {
    var evidence = valueAt(valueAt(row, 'field_evidence'), name), evidenceState = clean(valueAt(evidence, 'state'));
    var coverage = evidenceState === 'observed' ? 'covered' : (evidenceState === 'mixed' ? 'partial' : 'uncovered');
    var value = '';
    if (name === 'status') value = statusLabel(clean(valueAt(row, 'status')));
    else if (name === 'phases') value = arr(valueAt(row, 'phases')).map(phaseLabel).join(' · ');
    else if (name === 'enrollment') { var count = valueAt(valueAt(row, 'enrollment'), 'count'); value = Number.isSafeInteger(count) ? String(count) : ''; }
    else if (name === 'dates') value = dateLabel(dateOf(row, 'primary_completion'));
    else if (name === 'arm_groups') value = String(arr(valueAt(row, 'arm_groups')).length || '');
    else if (name === 'endpoints') { var primary = arr(valueAt(valueAt(row, 'endpoints'), 'primary')); value = primary.length ? clean(valueAt(primary[0], 'measure')) + (primary.length > 1 ? tr(' +' + (primary.length - 1) + ' more', ' 等 ' + primary.length + ' 项') : '') : ''; }
    else if (name === 'site_count') { var sites = valueAt(row, 'site_count'); value = Number.isSafeInteger(sites) ? String(sites) : ''; }
    else if (name === 'countries') value = arr(valueAt(row, 'countries')).map(clean).filter(Boolean).join(' · ');
    if (!clean(value) || clean(value) === tr('Not recorded', '未记录')) { coverage = 'uncovered'; value = tr('Not on the record', '不在记录中'); }
    return { text: clean(value), coverage: coverage, locators: arr(valueAt(evidence, 'source_field_locators')).map(clean) };
  }
  function locatorTail(locator) { var parts = clean(locator).split('/'); return parts[parts.length - 1] || clean(locator); }
  function peerCellNodes(row, name, into) {
    var cell = peerFieldValue(row, name), id = clean(valueAt(row, 'nct_id'));
    into.appendChild(el('span', 'bci-peer-val', cell.text));
    if (cell.coverage === 'partial') into.appendChild(el('span', 'bci-peer-val', tr('Part of this field is not on the record.', '此字段部分内容不在记录中。')));
    cell.locators.slice(0, 1).forEach(function (locator) {
      var source = el('button', 'bci-peer-src', '\u21b3 ' + locatorTail(locator));
      source.type = 'button';
      source.setAttribute('aria-label', peerFieldLabel(name) + ' · ' + id + ' · ' + tr('open the evidence thread at ', '打开证据线索：') + locator);
      source.addEventListener('click', function (event) { event.stopPropagation(); state.evidenceCell = { field: name, locator: locator }; selectTrial(id, row, valueAt(row, 'evidence'), true, source, id); });
      into.appendChild(source);
    });
    return cell.coverage;
  }
  function renderPeerMatrix() {
    var narrow = window.matchMedia('(max-width: 760px)').matches, wrap = el('div', narrow ? 'bci-peer-cards' : 'bci-peer');
    state.peerNarrow = narrow;
    if (narrow) {
      state.rows.forEach(function (row) {
        var card = el('article', 'bci-peer-card'), head = el('header'), list = el('dl');
        head.appendChild(el('span', 'bci-peer-nct', clean(row.nct_id)));
        head.appendChild(el('span', 'bci-peer-name', clean(valueAt(row, 'brief_title')) || clean(valueAt(row, 'title'))));
        card.appendChild(head);
        PEER_FIELDS.forEach(function (name) {
          var line = el('div', 'bci-peer-row'), label = el('dt', '', peerFieldLabel(name)), body = el('dd', 'bci-peer-cell');
          var coverage = peerCellNodes(row, name, body);
          body.classList.add(coverage === 'covered' ? 'is-covered' : (coverage === 'partial' ? 'is-partial' : 'is-uncovered'));
          line.appendChild(label); line.appendChild(body); list.appendChild(line);
        });
        card.appendChild(list); wrap.appendChild(card);
      });
    } else {
      var table = el('table'), head = el('thead'), headRow = el('tr'), body = el('tbody');
      var identity = el('th', 'bci-peer-id', tr('Trial', '试验')); identity.setAttribute('scope', 'col'); headRow.appendChild(identity);
      PEER_FIELDS.forEach(function (name) { var cell = el('th', '', peerFieldLabel(name)); cell.setAttribute('scope', 'col'); headRow.appendChild(cell); });
      head.appendChild(headRow); table.appendChild(head);
      state.rows.forEach(function (row) {
        var line = el('tr'), identityCell = el('th', 'bci-peer-id');
        identityCell.setAttribute('scope', 'row');
        identityCell.appendChild(el('span', 'bci-peer-nct', clean(row.nct_id)));
        identityCell.appendChild(el('span', 'bci-peer-name', clean(valueAt(row, 'brief_title')) || clean(valueAt(row, 'title'))));
        line.appendChild(identityCell);
        PEER_FIELDS.forEach(function (name) {
          var cell = el('td', 'bci-peer-cell'), coverage = peerCellNodes(row, name, cell);
          cell.classList.add(coverage === 'covered' ? 'is-covered' : (coverage === 'partial' ? 'is-partial' : 'is-uncovered'));
          line.appendChild(cell);
        });
        body.appendChild(line);
      });
      table.appendChild(body); wrap.appendChild(table);
    }
    ui.queue.appendChild(wrap);
    if (!narrow && wrap.scrollWidth > wrap.clientWidth + 4) ui.queue.appendChild(el('p', 'bci-peer-more', tr('The comparison continues to the right — scroll the table sideways. The trial column stays put.', '对照内容向右延伸——请横向滚动表格。试验列保持不动。')));
    var legend = el('div', 'bci-peer-legend');
    [['is-covered', tr('On the record', '已收录')], ['is-partial', tr('Partly on the record', '部分收录')], ['is-uncovered', tr('Not on the record', '未收录')]].forEach(function (pair) {
      var item = el('span'); item.appendChild(el('i', pair[0])); item.appendChild(document.createTextNode(pair[1])); legend.appendChild(item);
    });
    ui.queue.appendChild(legend);
    var uncovered = arr(valueAt(state.payload, 'uncovered_nct_ids')).map(clean).filter(Boolean);
    if (uncovered.length) ui.queue.appendChild(el('p', 'bci-facet-miss', tr('Not covered by this workspace: ' + uncovered.join(', ') + '.', '本工作台未收录：' + uncovered.join('、') + '。')));
  }
  function renderQueue() {
    clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', state.loading ? 'true' : 'false');
    if (state.accessLocked) {
      ui.queue.appendChild(emptyCard(isProspectiveMode() ? tr('First-seen Tape is locked', '首次观测记录已锁定') : (isChangeMode() ? tr('Registry updates are locked', '登记更新已锁定') : tr('Registry records are locked', '登记记录已锁定')), tr('Sign in with full access to read ' + activeNoun() + '.', '请以完整访问权限登录，读取' + activeNoun() + '。'), '◌'));
      ui.queueFooter.hidden = true;
      setLoadMoreCopy();
      return;
    }
    ui.queue.setAttribute('role', isPeerMode() ? 'group' : 'listbox');
    if (!state.rows.length) {
      ui.queue.appendChild(emptyCard(emptyTitle(), emptyCopy(), '○'));
    } else if (isPeerMode()) {
      renderPeerMatrix();
    } else {
      state.rows.forEach(function (item, index) {
        ui.queue.appendChild(isProspectiveMode() ? makeProspectiveRow(item, index)
          : (isScreenMode() ? makeScreenRow(item, index)
            : (isChangeMode() ? makeChangeRow(item, index) : makeMilestoneRow(item, index))));
      });
    }
    ui.queueFooter.hidden = !state.nextCursor || state.accessLocked;
    setLoadMoreCopy();
    paintFrame();
  }
  function emptyTitle() {
    if (isProspectiveMode()) return tr('No first-seen observations', '暂无首次观测记录');
    if (isScreenMode()) return tr('No matching trials', '没有匹配的试验');
    if (isPeerMode()) return state.cohort.length ? tr('None of these are covered', '这些试验均未收录') : tr('List the trials to compare', '请列出要对照的试验');
    if (isChangeMode()) return tr('No recorded field changes', '暂无已记录字段变更');
    return tr('No recorded dates', '暂无已记录日期');
  }
  function emptyCopy() {
    if (isProspectiveMode()) return prospectiveEmptyCopy();
    if (isScreenMode()) return tr('Nothing on the register matches every filter you set. Drop one filter to widen it.', '登记库中没有同时满足全部筛选条件的内容。可移除一个条件放宽范围。');
    if (isPeerMode()) return state.cohort.length
      ? tr('This workspace covers none of the trials you listed, so there is nothing to compare.', '本工作台未收录你列出的任何试验，因此无法对照。')
      : tr('Paste the NCT IDs you want side by side. This workspace never picks the comparison for you.', '粘贴你想并排查看的 NCT 编号。本工作台不会替你挑选对照对象。');
    if (isChangeMode()) return tr('No verified field change matches this filter set.', '在此筛选条件下没有已核验的字段变更。');
    return tr('No registry-recorded primary completion or completion date matches this window and filter set.', '在此窗口和筛选条件下，没有匹配的主要完成或完成登记日期。');
  }
  function paintFrame() { ui.workspace.dataset.surface = state.mode; paintDecision(); paintBraid(); paintChips(); paintPanelFoot(); }
  function setSubtitle(payload) {
    var pagination = valueAt(payload, 'pagination') || {}, total = valueAt(pagination, 'total'), window = valueAt(payload, 'effective_window') || {}, tapeCoverage = valueAt(payload, 'change_tape_coverage') || {}, prospectiveCoverage = valueAt(payload, 'prospective_coverage') || {};
    if (isScreenMode()) {
      var coverage = valueAt(payload, 'coverage') || {}, observedCount = valueAt(coverage, 'observed');
      text(ui.subtitle, Number.isSafeInteger(total) && Number.isSafeInteger(observedCount)
        ? tr(total + ' of ' + observedCount + ' covered trials match every filter', observedCount + ' 项已收录试验中，' + total + ' 项符合全部条件')
        : tr('Trials matching every filter you set', '符合你全部筛选条件的试验'));
      return;
    }
    if (isPeerMode()) {
      var peerCoverage = valueAt(payload, 'coverage') || {}, requested = valueAt(peerCoverage, 'requested_count'), covered = valueAt(peerCoverage, 'covered_count');
      text(ui.subtitle, Number.isSafeInteger(requested) && Number.isSafeInteger(covered)
        ? tr(covered + ' of the ' + requested + ' trials you listed are covered here', '你列出的 ' + requested + ' 项试验中，本处收录 ' + covered + ' 项')
        : tr('Exactly the trials you listed, side by side', '完全按你列出的试验并排显示'));
      return;
    }
    if (isChangeMode()) {
      var available = valueAt(tapeCoverage, 'available_trials'), unavailable = valueAt(tapeCoverage, 'unavailable_trials');
      text(ui.subtitle, (Number.isSafeInteger(total) ? tr(total + ' verified field changes', total + ' 项已核验字段变更') : tr('Verified registry field changes', '已核验登记字段变更')) +
        (Number.isSafeInteger(available) && Number.isSafeInteger(unavailable)
          ? tr(' · replayed for ' + available + ' trials, ' + unavailable + ' without a replayable record', ' · 已为 ' + available + ' 项试验重放，' + unavailable + ' 项无可重放记录')
          : ''));
      return;
    }
    if (typeof total !== 'number') { text(ui.subtitle, isProspectiveMode() ? tr('First observed by this current-record collector', '由当前记录采集器首次观测') : tr('Registry-recorded primary completion and completion dates', '登记记录的主要完成和完成日期')); return; }
    var timeLabel = clean(valueAt(window, 'from_date')) && clean(valueAt(window, 'to_date'))
      ? (isProspectiveMode() ? tr('first observed in the selected window', '在所选窗口内首次观测') : tr('within the selected record window', '位于所选记录窗口内'))
      : (isProspectiveMode() ? tr('across the available observation range', '覆盖可用观测范围') : tr('across the available record range', '覆盖可用记录范围'));
    if (isProspectiveMode()) {
      var active = valueAt(prospectiveCoverage, 'active_trials'), preBaseline = valueAt(prospectiveCoverage, 'pre_baseline_trials'), unavailable = valueAt(prospectiveCoverage, 'unavailable_trials');
      var prospectiveCoverageLabel = Number.isSafeInteger(active) && Number.isSafeInteger(preBaseline) && Number.isSafeInteger(unavailable)
        ? tr(' · Current-only coverage: ' + active + ' active, ' + preBaseline + ' baseline, ' + unavailable + ' unavailable', ' · 仅当前记录覆盖：' + active + '项活跃，' + preBaseline + '项基线，' + unavailable + '项不可用')
        : tr(' · Current-record coverage only', ' · 仅当前记录覆盖');
      text(ui.subtitle, (total === 1 ? tr('1 first-seen observation ' + timeLabel, '1项首次观测记录' + timeLabel) : tr(total + ' first-seen observations ' + timeLabel, total + '项首次观测记录' + timeLabel)) + prospectiveCoverageLabel);
    }
    else text(ui.subtitle, total === 1 ? tr('1 registry-recorded date ' + timeLabel, '1项登记记录日期' + timeLabel) : tr(total + ' registry-recorded dates ' + timeLabel, total + '项登记记录日期' + timeLabel));
  }

  /* ---- Deterministic state precedence (IA contract §4, twelve ranks) ---- */
  function stateRank(code) {
    for (var index = 0; index < STATE_PRECEDENCE.length; index += 1) if (STATE_PRECEDENCE[index][0] === code) return STATE_PRECEDENCE[index][1];
    return STATE_PRECEDENCE.length;
  }
  function noteState(list, code, knownAt, en, zh) { list.push({ code: code, rank: stateRank(code), known_at: clean(knownAt), en: en, zh: zh }); }
  function rowClocks(item) {
    var trial = rowTrial(item), source = valueAt(item, 'source'), evidence = valueAt(item, 'evidence');
    var posted = clean(valueAt(trial, 'updated_at')) || clean(valueAt(source, 'last_update_posted_at')) || clean(valueAt(evidence, 'updated_at'));
    var known = clean(valueAt(trial, 'retrieved_at')) || clean(valueAt(source, 'retrieved_at')) || clean(valueAt(evidence, 'retrieved_at'));
    return { posted: posted, known: known };
  }
  function tapeConflicts() {
    var byPair = {}, conflicts = 0;
    if (!isChangeMode()) return 0;
    state.rows.forEach(function (item) {
      var change = valueAt(item, 'change'), versions = valueAt(change, 'source_versions');
      var key = nctOf(valueAt(item, 'trial')) + '|' + valueAt(versions, 'before') + '|' + clean(valueAt(change, 'field_class'));
      var operation = clean(valueAt(change, 'op'));
      if (!byPair[key]) byPair[key] = {};
      byPair[key][operation] = true;
      if (byPair[key].add && byPair[key].remove) conflicts += 1;
    });
    return conflicts;
  }
  function degradedFactCount() {
    if (!isScreenMode()) return 0;
    return state.rows.filter(function (row) {
      return ['overall_status', 'study_type', 'phases', 'sponsor', 'enrollment', 'conditions', 'interventions', 'primary_completion'].some(function (name) {
        var fieldState = factState(valueAt(row, name));
        return fieldState === 'parser_degraded' || fieldState === 'license_restricted';
      });
    }).length;
  }
  function partialFactCount() {
    if (isScreenMode()) return state.rows.filter(function (row) { return ['overall_status', 'phases', 'sponsor', 'enrollment', 'primary_completion'].some(function (name) { return !observed(valueAt(row, name)); }); }).length;
    if (isPeerMode()) return arr(valueAt(state.payload, 'uncovered_nct_ids')).length;
    if (isChangeMode()) return valueAt(valueAt(state.payload, 'change_tape_coverage'), 'unavailable_trials') || 0;
    return 0;
  }
  function reviewPendingCount() {
    if (!isChangeMode()) return 0;
    return state.rows.filter(function (item) { return clean(valueAt(valueAt(item, 'change'), 'review_state')) === 'needs_review'; }).length;
  }
  function correctionCount() {
    if (!isChangeMode() && !isProspectiveMode()) return 0;
    return state.rows.filter(function (item) {
      if (isChangeMode()) return clean(valueAt(valueAt(item, 'change'), 'op')) === 'replace';
      return arr(valueAt(valueAt(item, 'prospective_change'), 'changes')).some(function (change) { return clean(valueAt(change, 'op')) === 'replace'; });
    }).length;
  }
  function resolveStates() {
    var list = [], health = valueAt(state.payload, 'health') || {}, healthState = clean(valueAt(health, 'state')).toLowerCase();
    var knownAt = clean(valueAt(state.payload, 'as_of')), degraded = degradedFactCount(), partial = partialFactCount();
    if (state.accessLocked) noteState(list, 'locked', knownAt, 'this view needs full access.', '此视图需要完整访问权限。');
    if (state.contractFailed) noteState(list, 'integrity_block', knownAt, 'this page did not match its published shape.', '此页面与已发布结构不一致。');
    if (state.workspaceDown) noteState(list, 'source_outage', knownAt, 'the register is not answering right now.', '登记库当前没有响应。');
    if (healthState === 'unavailable' || degraded) noteState(list, 'source_capability_absent', knownAt, 'some fields cannot be read from this source.', '部分字段无法从此来源读取。');
    if (reviewPendingCount()) noteState(list, 'ambiguous_identity', knownAt, 'endpoint edits are not matched to a named endpoint.', '终点改动尚未对应到具体终点。');
    if (tapeConflicts()) noteState(list, 'contradiction', knownAt, 'one field was both added and removed.', '同一字段既新增又移除。');
    if (correctionCount()) noteState(list, 'correction', knownAt, 'an earlier recorded value was replaced.', '先前记录的值已被替换。');
    if (healthState === 'stale' || state.restarted) noteState(list, 'stale', knownAt, 'the register moved while this page loaded.', '本页加载期间登记库已更新。');
    if (isChangeMode() && state.rows.length) noteState(list, 'historical', knownAt, 'these are superseded record versions.', '这些是已被取代的记录版本。');
    if (partial) noteState(list, 'partial', knownAt, 'part of this set is not on the record.', '其中一部分未收录在记录中。');
    if (state.hasLoaded && !state.rows.length && !state.accessLocked && !state.workspaceDown) noteState(list, 'empty', knownAt, 'nothing matches what you asked for.', '没有内容符合你的条件。');
    if (!list.length) noteState(list, 'normal', knownAt, 'current, complete, and uncontested.', '当前、完整、无争议。');
    // Equal ranks resolve on earliest known_at, then on the lexical state code.
    list.sort(function (left, right) { return left.rank - right.rank || (left.known_at < right.known_at ? -1 : left.known_at > right.known_at ? 1 : (left.code < right.code ? -1 : 1)); });
    return list;
  }
  function paintDecision() {
    var states = resolveStates(), primary = states[0], stance = RESEARCH_STANCE[STATE_STANCE[primary.code]] || RESEARCH_STANCE.none;
    state.stateCodes = states.map(function (item) { return item.code; });
    ui.decisionStance.className = 'bci-stamp-mark' + (stance[2] ? ' ' + stance[2] : '');
    text(ui.decisionStance, tr(stance[0], stance[1]));
    text(ui.decisionWhy, tr(primary.en, primary.zh));
    ui.decision.setAttribute('data-state', primary.code);
  }
  function paintPanelFoot() {
    var states = state.stateCodes || [], parts = [];
    parts.push(tr('Everything here is what ClinicalTrials.gov recorded from sponsor and investigator submissions — research context, no trade call.', '此处内容均为 ClinicalTrials.gov 记录的申办方与研究者提交材料，仅供研究参考，不作交易判断。'));
    if (isChangeMode()) parts.push(tr('Each row shows one registry field and its exact recorded before / after value when the verified chain carries them. Open a row for the source position and recorded lineage.', '每行显示一个登记字段，以及核验链中可用的精确前后取值。打开某行可查看来源位置与记录沿革。'));
    if (isScreenMode()) parts.push(tr('Filters combine literally, with no widening and no ranking.', '筛选条件按字面组合，不扩展、不排序。'));
    if (isPeerMode()) parts.push(tr('This compares exactly the trials you listed. No peer is discovered for you.', '此处仅对照你列出的试验，不会替你发现同类试验。'));
    if (states.length > 1) parts.push(tr('Also on this page: ' + states.slice(1).map(stateLabel).join(' · '), '本页还包括：' + states.slice(1).map(stateLabel).join(' · ')));
    clearChildren(ui.panelFoot);
    ui.panelFoot.appendChild(el('b', '', tr('One page, one receipt. ', '一页一凭证。')));
    ui.panelFoot.appendChild(document.createTextNode(parts.join(' ')));
    ui.panelFoot.hidden = false;
  }
  function stateLabel(code) {
    var labels = {
      locked: ['needs access', '需要权限'], integrity_block: ['shape check failed', '结构校验未通过'],
      source_capability_absent: ['fields unreadable', '字段无法读取'], ambiguous_identity: ['needs review', '待人工核对'],
      contradiction: ['sources disagree', '两处对不上'], correction: ['earlier value replaced', '旧值已替换'],
      source_outage: ['source not answering', '来源无响应'], stale: ['needs refresh', '需要刷新'],
      historical: ['past versions', '过往版本'], partial: ['partly on the record', '部分已收录'],
      empty: ['no match', '无匹配'], normal: ['complete', '完整']
    };
    var pair = labels[code] || labels.normal; return tr(pair[0], pair[1]);
  }

  /* ---- Temporal braid: two clocks, one scale, the bar is the gap ---- */
  function braidRecords() {
    var records = [];
    state.rows.forEach(function (item) {
      var clocks = rowClocks(item), posted = Date.parse(clocks.posted), known = Date.parse(clocks.known);
      if (!Number.isFinite(posted) || !Number.isFinite(known)) return;
      var change = valueAt(item, 'change');
      records.push({
        id: nctOf(rowTrial(item)) || screenIdentity(item),
        key: rowIdentity(item),
        posted: posted, known: known,
        postedText: clocks.posted, knownText: clocks.known,
        corrected: isChangeMode() && clean(valueAt(change, 'op')) === 'replace'
      });
    });
    return records.slice(0, 40);
  }
  function dayGap(fromMs, toMs) { return Math.round(Math.abs(toMs - fromMs) / 86400000); }
  function braidPhrase(record) {
    var days = dayGap(record.posted, record.known);
    var ahead = record.known < record.posted;
    return record.id + ' — ' + tr('posted ', '登记发布 ') + timestampLabel(record.postedText) + tr(', known ', '，我们得知 ') + timestampLabel(record.knownText) + ' · ' +
      (days === 0 ? tr('same day', '同一天') : (ahead ? tr(days + ' days before the record', days + '天早于记录') : tr(days + ' days later', '晚 ' + days + ' 天')));
  }
  function paintBraid() {
    var records = braidRecords(), plot = ui.braidPlot, low, high, span, reverse = false;
    state.braid = records;
    Array.prototype.slice.call(plot.querySelectorAll('.bci-braid-rec')).forEach(function (node) { plot.removeChild(node); });
    clearChildren(ui.braidScale); clearChildren(ui.braidList); text(ui.braidReadout, '');
    if (!records.length) { ui.braid.hidden = true; return; }
    low = records[0].posted; high = records[0].posted;
    records.forEach(function (record) {
      low = Math.min(low, record.posted, record.known);
      high = Math.max(high, record.posted, record.known);
      if (record.known < record.posted) reverse = true;
    });
    span = Math.max(high - low, 86400000);
    ui.braid.hidden = false;
    text(ui.braidUnit, tr(dayGap(low, high) + ' days across ' + records.length + ' records', dayGap(low, high) + ' 天 · ' + records.length + ' 条记录'));
    records.forEach(function (record, index) {
      var left = (record.posted - low) / span * 100, right = (record.known - low) / span * 100;
      var start = Math.min(left, right), end = Math.max(left, right);
      var mark = el('button', 'bci-braid-rec' + (record.corrected ? ' is-corrected' : ''));
      mark.type = 'button';
      mark.style.left = start + '%';
      mark.style.width = Math.max(end - start, 0.6) + '%';
      mark.setAttribute('data-record', record.key);
      mark.setAttribute('aria-label', braidPhrase(record));
      // Records that were read at nearly the same moment would otherwise print
      // one thick line; each strand gets its own lane so they stay countable.
      var lane = index % 4;
      var lag = el('span', 'bci-braid-lag' + (record.known < record.posted ? ' is-reverse' : ''));
      lag.style.left = '0'; lag.style.right = '0'; lag.style.top = (44 + lane * 4) + 'px';
      mark.appendChild(lag);
      var stem = el('span', 'bci-braid-stem'); stem.style.left = (left <= right ? '0' : '100%'); stem.style.height = (36 + lane * 4) + 'px'; mark.appendChild(stem);
      var effective = el('span', 'bci-braid-eff'); effective.style.left = (left <= right ? '0' : '100%'); mark.appendChild(effective);
      var recorded = el('span', 'bci-braid-known'); recorded.style.left = (left <= right ? '100%' : '0'); recorded.style.top = (41 + lane * 4) + 'px'; mark.appendChild(recorded);
      if (record.corrected) {
        var branch = el('span', 'bci-braid-branch'); branch.style.left = (left <= right ? '100%' : '0'); branch.style.top = (45 + lane * 4) + 'px'; mark.appendChild(branch);
        var correction = el('span', 'bci-braid-corr'); correction.style.left = (left <= right ? '100%' : '0'); correction.style.top = (54 + lane * 4) + 'px'; mark.appendChild(correction);
      }
      mark.addEventListener('focus', function () { text(ui.braidReadout, braidPhrase(record)); });
      mark.addEventListener('mouseenter', function () { text(ui.braidReadout, braidPhrase(record)); });
      mark.addEventListener('click', function () { focusRowByKey(record.key); });
      plot.appendChild(mark);
      var line = el('li', '', braidPhrase(record)); ui.braidList.appendChild(line);
    });
    [0, 0.5, 1].forEach(function (fraction) { ui.braidScale.appendChild(el('span', '', timestampLabel(isoDay(low + span * fraction)))); });
    ui.braidReadout.setAttribute('data-rest', ui.braidReadout.getAttribute(lang() === 'zh' ? 'data-rest-zh' : 'data-rest-en') || '');
    text(ui.braidFoot, tr('Each bar is the gap between the two clocks: the register posts, then we know it. A wide bar means we learned it late' + (reverse ? '; a bar drawn right to left is a record we knew before its posted date.' : '.'),
      '每条横杠就是两个时间之间的间隔：登记库先发布，我们再得知。横杠越长，说明我们得知得越晚' + (reverse ? '；从右往左的横杠表示我们在发布日期之前就已得知。' : '。')));
  }
  function pad(value, width) { var out = String(value); while (out.length < width) out = '0' + out; return out; }
  function isoDay(ms) {
    // Civil date from a UTC epoch offset without constructing a local clock.
    var z = Math.floor(ms / 86400000) + 719468, era = Math.floor(z / 146097), doe = z - era * 146097;
    var yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365);
    var year = yoe + era * 400, doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
    var mp = Math.floor((5 * doy + 2) / 153), day = doy - Math.floor((153 * mp + 2) / 5) + 1, month = mp + (mp < 10 ? 3 : -9);
    if (month <= 2) year += 1;
    return pad(year, 4) + '-' + pad(month, 2) + '-' + pad(day, 2);
  }
  function focusRowByKey(key) {
    var row = Array.prototype.slice.call(ui.queue.querySelectorAll('[data-row-key]')).filter(function (node) { return node.getAttribute('data-row-key') === key; })[0];
    if (row && typeof row.focus === 'function') { row.scrollIntoView({ block: 'nearest' }); row.focus({ preventScroll: true }); }
  }

  /* ---- The active query, as chips you can drop ---- */
  function activeChips() {
    var chips = [];
    function add(key, label, value) { if (clean(value)) chips.push({ key: key, label: label, value: clean(value) }); }
    if (isScreenMode()) {
      add('sponsor', tr('Sponsor', '申办方'), state.filters.sponsor);
      add('intervention', tr('Intervention', '干预措施'), state.filters.intervention);
      add('study_type', tr('Study type', '研究类型'), studyTypeLabel(state.filters.study_type));
      add('phase', tr('Phase', '阶段'), state.filters.phase);
      add('status', tr('Recruitment', '招募状态'), state.filters.status);
      add('condition', tr('Condition', '适应症'), state.filters.condition);
      add('pc_from', tr('Completion from', '完成起始'), state.filters.pc_from);
      add('pc_to', tr('Completion to', '完成截止'), state.filters.pc_to);
    } else if (isChangeMode()) {
      add('q', tr('Trial', '试验'), tapeNctFilter());
      add('change_kind', tr('Field', '字段'), state.filters.change_kind ? historyKindLabel(state.filters.change_kind) : '');
      add('review_state', tr('Review', '核对'), state.filters.review_state === 'all' ? '' : reviewStateLabel(state.filters.review_state));
    }
    return chips;
  }
  function paintChips() {
    var chips = activeChips();
    clearChildren(ui.chips);
    if (!isScreenMode() && !isChangeMode()) { ui.chips.hidden = true; return; }
    ui.chips.hidden = false;
    if (!chips.length) { ui.chips.appendChild(el('span', 'bci-chip-none', tr('No filter set — showing everything the register covers.', '未设置筛选条件，显示登记库覆盖的全部内容。'))); return; }
    chips.forEach(function (chip) {
      var node = el('span', 'bci-chip');
      node.appendChild(el('b', '', chip.label));
      node.appendChild(document.createTextNode(chip.value));
      var drop = el('button', 'bci-chip-drop', '×');
      drop.type = 'button';
      drop.setAttribute('aria-label', tr('Remove filter: ', '移除筛选：') + chip.label + ' ' + chip.value);
      drop.addEventListener('click', function () { dropChip(chip.key); });
      node.appendChild(drop);
      ui.chips.appendChild(node);
    });
  }
  function dropChip(key) {
    if (key === 'q') state.filters.q = '';
    else if (key === 'change_kind') state.filters.change_kind = '';
    else if (key === 'review_state') state.filters.review_state = 'all';
    else state.filters[key] = '';
    syncControls(); writeUrl(); loadMilestones({ replace: true });
  }
  function studyTypeLabel(value) {
    var labels = { INTERVENTIONAL: ['Interventional', '干预性'], OBSERVATIONAL: ['Observational', '观察性'], EXPANDED_ACCESS: ['Expanded access', '扩大可及'] };
    var pair = labels[clean(value)]; return pair ? tr(pair[0], pair[1]) : clean(value);
  }
  function reviewStateLabel(value) {
    var labels = { not_required: ['Checked', '已核对'], needs_review: ['Needs review', '待核对'], all: ['Any', '不限'] };
    var pair = labels[clean(value)] || labels.all; return tr(pair[0], pair[1]);
  }

  /* ---- Facet rail: counts, missingness, and what a count cannot mean ---- */
  function facetDimensionLabel(dimension) {
    var labels = { phase: ['Phase', '阶段'], status: ['Recruitment', '招募状态'], study_type: ['Study type', '研究类型'] };
    var pair = labels[dimension] || labels.phase; return tr(pair[0], pair[1]);
  }
  function facetFilterKey(dimension) { return dimension === 'study_type' ? 'study_type' : dimension; }
  function paintFacets() {
    clearChildren(ui.facets);
    if (!isScreenMode()) { ui.facets.hidden = true; return; }
    ui.facets.hidden = false;
    if (!state.facets) { ui.facets.appendChild(el('p', 'bci-facet-miss', tr('Counts are loading.', '计数加载中。'))); return; }
    arr(valueAt(state.facets, 'facets')).forEach(function (facet) {
      var dimension = clean(valueAt(facet, 'dimension')), group = el('section', 'bci-facet-group'), heading = el('h3');
      var missingness = valueAt(facet, 'missingness') || {}, unreadable = (valueAt(missingness, 'parser_degraded') || 0) + (valueAt(missingness, 'license_restricted') || 0);
      var absent = (valueAt(missingness, 'source_null') || 0) + (valueAt(missingness, 'source_missing') || 0) + (valueAt(missingness, 'not_applicable') || 0);
      heading.appendChild(el('span', '', facetDimensionLabel(dimension)));
      heading.appendChild(el('span', 'bci-facet-note', String(valueAt(facet, 'base_matched'))));
      group.appendChild(heading);
      arr(valueAt(facet, 'buckets')).slice(0, 12).forEach(function (bucket) {
        var token = clean(valueAt(bucket, 'token')), active = normalizedQueryValue(state.filters[facetFilterKey(dimension)]) === normalizedQueryValue(token);
        var button = el('button', 'bci-facet' + (active ? ' is-active' : ''));
        button.type = 'button';
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
        button.appendChild(el('span', 'bci-facet-name', bucketLabel(dimension, token)));
        button.appendChild(el('span', 'bci-facet-count', String(valueAt(bucket, 'count'))));
        button.addEventListener('click', function () { toggleFacet(dimension, token, active); });
        group.appendChild(button);
      });
      if (absent || unreadable) {
        var absentPhrase = absent + (absent === 1 ? ' trial does not record ' : ' trials do not record ');
        var unreadablePhrase = unreadable + (unreadable === 1 ? ' trial could not be read' : ' trials could not be read');
        group.appendChild(el('p', 'bci-facet-miss', absent && unreadable
          ? tr(absentPhrase + 'this, and ' + unreadable + ' could not be read.', absent + ' 项试验未记录此项，另有 ' + unreadable + ' 项无法读取。')
          : (unreadable ? tr(unreadablePhrase + ' for this field.', unreadable + ' 项试验的此字段无法读取。')
            : tr(absentPhrase + 'this field.', absent + ' 项试验未记录此字段。'))));
      }
      ui.facets.appendChild(group);
    });
    ui.facets.appendChild(el('p', 'bci-facet-miss', tr('Counts are whole trials, and each list ignores its own filter — so they do not add up to the total.', '计数以试验为单位，且每个清单不计入自身筛选，因此不会与总数相加吻合。')));
  }
  function bucketLabel(dimension, token) {
    if (dimension === 'study_type') return studyTypeLabel(token.toUpperCase());
    if (dimension === 'phase') return phaseLabel(token);
    return statusLabel(token);
  }
  function phaseLabel(token) {
    var labels = { phase1: ['Phase 1', '一期'], phase2: ['Phase 2', '二期'], phase3: ['Phase 3', '三期'], phase4: ['Phase 4', '四期'], na: ['Not applicable', '不适用'], early_phase1: ['Early phase 1', '早期一期'] };
    var pair = labels[clean(token).toLowerCase()]; return pair ? tr(pair[0], pair[1]) : clean(token);
  }
  function statusLabel(token) {
    var labels = {
      recruiting: ['Recruiting', '招募中'], not_yet_recruiting: ['Not yet recruiting', '尚未招募'],
      active_not_recruiting: ['Active, not recruiting', '进行中，未招募'], completed: ['Completed', '已完成'],
      terminated: ['Terminated', '已终止'], withdrawn: ['Withdrawn', '已撤回'], suspended: ['Suspended', '已暂停'],
      enrolling_by_invitation: ['Enrolling by invitation', '受邀入组'], unknown: ['Unknown', '状态未知']
    };
    var pair = labels[clean(token).toLowerCase()]; return pair ? tr(pair[0], pair[1]) : clean(token);
  }
  function toggleFacet(dimension, token, active) {
    var key = facetFilterKey(dimension);
    state.filters[key] = active ? '' : clean(token);
    syncControls(); writeUrl(); loadMilestones({ replace: true });
  }
  function loadFacets() {
    if (!isScreenMode()) { state.facets = null; paintFacets(); return; }
    abort('facetsController');
    var controller = new AbortController(), token = state.facetsToken + 1;
    state.facetsToken = token; state.facetsController = controller;
    fetchJson(FACETS_API + facetQueryString(), controller.signal).then(function (payload) {
      if (token !== state.facetsToken) return;
      validateFacetsEnvelope(payload);
      state.facets = payload; paintFacets(); syncControls();
    }).catch(function (error) {
      if (token !== state.facetsToken || (error && error.name === 'AbortError')) return;
      state.facets = null;
      syncControls();
      clearChildren(ui.facets);
      ui.facets.hidden = !isScreenMode();
      ui.facets.appendChild(el('p', 'bci-facet-miss', tr('Counts are unavailable for this query. The results below are unaffected.', '此查询的计数暂不可用，下方结果不受影响。')));
    }).finally(function () { if (state.facetsController === controller) state.facetsController = null; });
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
      enrollment: ['Enrollment record', '入组记录'], milestone_date_constraint: ['Recorded date', '记录日期'], site_list: ['Trial-site list', '研究中心清单'], intervention: ['Intervention record', '干预措施记录'], endpoint_record_delta: ['Endpoint record', '终点记录'],
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
    section.appendChild(strip);
    if (state.evidenceCell && state.evidenceCell.locator) {
      var opened = el('div', 'bci-detail-fact');
      opened.appendChild(el('span', '', tr('You opened', '你打开的') + ' · ' + peerFieldLabel(state.evidenceCell.field)));
      opened.appendChild(el('strong', 'bci-tape-path', state.evidenceCell.locator));
      section.appendChild(opened);
    }
    return section;
  }
  function locatorSection(fieldEvidence) {
    var section = el('section', 'bci-detail-section'); section.appendChild(el('h3', '', tr('Where each field comes from', '每个字段的来源位置')));
    PEER_FIELDS.forEach(function (name) {
      var evidence = valueAt(fieldEvidence, name);
      if (!evidence) return;
      var card = el('article', 'bci-endpoint');
      card.appendChild(el('strong', '', peerFieldLabel(name)));
      arr(valueAt(evidence, 'source_field_locators')).forEach(function (locator) { card.appendChild(el('span', '', clean(locator))); });
      section.appendChild(card);
    });
    section.appendChild(el('p', 'bci-detail-note', tr('Each line is the exact place in the source record this value was read from.', '每一行都是该值在来源记录中的确切读取位置。')));
    return section;
  }
  function tapeVersionSection(change, id) {
    var versions = valueAt(change, 'source_versions'), exact = valueAt(change, 'exact_values'), lineage = valueAt(change, 'correction_lineage'), section = el('section', 'bci-detail-section');
    section.appendChild(el('h3', '', tr('The change on this page', '本页的这次变更')));
    var card = el('article', 'bci-endpoint');
    card.appendChild(el('strong', '', historyKindLabel(valueAt(change, 'field_class')) + ' · ' + tapeOpLabel(valueAt(change, 'op'))));
    if (exact && lineage) {
      card.appendChild(tapeExactDelta(exact, true));
      var disclosure = el('details', 'bci-tape-disclosure'), summary = el('summary', '', tr('Source & lineage', '来源与沿革'));
      disclosure.appendChild(summary);
      var source = el('p', ''); source.appendChild(el('span', '', tr('Source position', '来源位置'))); source.appendChild(el('code', '', valueAt(exact, 'source_pointer'))); disclosure.appendChild(source);
      var predecessor = el('p', ''); predecessor.appendChild(el('span', '', tr('Recorded lineage', '记录沿革'))); predecessor.appendChild(el('strong', '', tapeLineageLabel(lineage))); disclosure.appendChild(predecessor);
      var correction = el('p', ''); correction.appendChild(el('span', '', tr('Correction status', '更正状态'))); correction.appendChild(el('strong', '', tr('Not assessed', '未评估'))); disclosure.appendChild(correction);
      card.appendChild(disclosure);
    } else {
      card.appendChild(el('p', '', tr('Before: ', '之前：') + recordStateLabel(valueAt(change, 'before_state'))));
      card.appendChild(el('p', '', tr('After: ', '之后：') + recordStateLabel(valueAt(change, 'after_state'))));
    }
    card.appendChild(el('p', '', tr('Verified at ', '核验于 ') + observationTimestampLabel(valueAt(change, 'observed_at'))));
    if (isTrialId(id) && Number.isSafeInteger(valueAt(versions, 'after'))) {
      var link = el('a', 'bci-detail-link', tr('Open submitted version ', '打开提交版本 ') + 'V' + valueAt(versions, 'after') + ' ↗');
      link.href = historyVersionUrl(id, valueAt(versions, 'after')); link.target = '_blank'; link.rel = 'noopener noreferrer';
      card.appendChild(link);
    }
    section.appendChild(card);
    section.appendChild(el('p', 'bci-detail-note', exact ? tr('These are the exact recorded JSON values. A registry edit is not a protocol change, business event, or assessed correction.', '这些是登记记录中的精确取值。登记修改不等于方案变更、业务事件或已评估的更正。') : tr('This older record does not carry exact value disclosure. No value is guessed.', '这条较早记录不含精确取值披露。不会猜测任何取值。')));
    return section;
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
    if (isPeerMode() && valueAt(queueItem, 'field_evidence')) ui.inspectorBody.appendChild(locatorSection(valueAt(queueItem, 'field_evidence')));
    if (isChangeMode() && valueAt(queueItem, 'change')) ui.inspectorBody.appendChild(tapeVersionSection(valueAt(queueItem, 'change'), id));
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
    state.returnFocus = null; state.selectedId = ''; state.selectedKey = ''; state.selected = null; state.detail = null; state.evidenceCell = null; abort('detailController'); state.detailToken += 1;
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
    paintFrame();
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
    paintFrame();
  }
  function handleUnavailable(error, options) {
    options = options || {};
    if (isAccessError(error)) {
      lockWorkspace();
      showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' when full access is confirmed.', '完整访问权限确认后，请选择一项' + activeSingularNoun() + '。'));
      return;
    }
    if (options.append && state.rows.length) { preserveAppendFailure(); return; }
    state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = ''; state.selectedKey = ''; state.appendFailed = false; state.accessLocked = false; state.workspaceDown = true;
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
    if (!append) loadFacets();
    if (isPeerMode() && state.cohort.length < PEER_MIN_COHORT) {
      state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = ''; state.loading = false; state.pageLoading = false;
      state.hasLoaded = true; state.appendFailed = false; state.accessLocked = false; state.contractFailed = false; state.workspaceDown = false;
      ui.refresh.classList.remove('is-spinning');
      ui.workspace.dataset.state = 'empty'; setStatus('ready', tr('Waiting for your list', '等待你的清单'), tr('Nothing is compared until you list it', '未列出前不会进行任何对照'));
      setNotice('', ''); text(ui.subtitle, tr('Exactly the trials you listed, side by side', '完全按你列出的试验并排显示')); text(ui.asOf, ''); renderQueue();
      return;
    }
    requestPage(cursor, controller.signal).then(function (payload) {
      if (token !== state.listToken) return;
      state.contractFailed = false;
      try {
        if (isProspectiveMode()) validateProspectiveEnvelope(payload);
        else if (isScreenMode()) validateScreenEnvelope(payload);
        else if (isPeerMode()) validatePeerEnvelope(payload);
        else if (isChangeMode()) validateChangeEnvelope(payload);
        else validateMilestoneEnvelope(payload);
      } catch (contractError) { state.contractFailed = true; throw contractError; }
      var incomingGeneration = generationKey(payload);
      if (append && state.generation && incomingGeneration !== state.generation) {
        state.restarted = true; announce(tr('The registry page changed. Reloading the selected filters.', '登记页面已变化。正在重新加载所选筛选条件。'));
        loadMilestones({ replace: true, restarted: true }); return;
      }
      var existingRows = append ? state.rows : [], pagination = payload.pagination, rows;
      if (isProspectiveMode()) { rows = validateProspectivePage(payload.prospective_changes, existingRows); validateProspectivePagination(payload, existingRows, cursor, append ? state.payload : null); }
      else if (isScreenMode()) { rows = validateScreenPage(payload.rows, existingRows); validateScreenPagination(payload, existingRows, cursor, append ? state.payload : null); }
      else if (isPeerMode()) { rows = validatePeerPage(payload.trials, existingRows); validatePeerPagination(payload, existingRows, cursor, append ? state.payload : null); }
      else if (isChangeMode()) { rows = validateChangePage(payload.change_tape, existingRows); validateChangePagination(payload, existingRows, cursor, append ? state.payload : null); }
      else { rows = validateMilestonePage(payload.milestones, existingRows); validateMilestonePagination(payload, existingRows, cursor, append ? state.payload : null); }
      if (append) state.rows = state.rows.concat(rows); else state.rows = rows;
      state.payload = payload; state.generation = incomingGeneration; state.nextCursor = clean(valueAt(pagination, 'next_cursor')); state.loading = false; state.pageLoading = false; state.hasLoaded = true; state.appendFailed = false; state.accessLocked = false; state.workspaceDown = false;
      ui.workspace.dataset.state = state.restarted ? 'generation-restarted' : (state.rows.length ? 'ready' : 'empty'); updateMetadata(payload); setSubtitle(payload); renderQueue();
      announce(state.rows.length ? tr('Loaded ' + state.rows.length + ' ' + activeNoun() + '.', '已加载' + state.rows.length + '项' + activeNoun() + '。') : tr('No ' + activeNoun() + ' match these filters.', '没有' + activeNoun() + '匹配这些筛选条件。'));
      if (!append && state.selectedId) {
        var activeRow = selectedRow();
        selectTrial(state.selectedId, activeRow && rowTrial(activeRow), activeRow && (valueAt(activeRow, 'evidence') || valueAt(activeRow, 'source')), false, null, activeRow && rowIdentity(activeRow));
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
    state.filters.sponsor = clean(ui.sponsor.value).slice(0, 240);
    state.filters.intervention = clean(ui.intervention.value).slice(0, 240);
    state.filters.study_type = STUDY_TYPE_VALUES[clean(ui.studyType.value)] ? clean(ui.studyType.value) : '';
    state.filters.pc_from = fullDate(ui.pcFrom.value) ? clean(ui.pcFrom.value) : '';
    state.filters.pc_to = fullDate(ui.pcTo.value) ? clean(ui.pcTo.value) : '';
    state.filters.review_state = TAPE_REVIEW_VALUES[clean(ui.review.value)] ? clean(ui.review.value) : 'all';
    closeInspector({ restoreFocus: false, writeUrl: false, render: false }); writeUrl(); loadMilestones({ replace: true });
  }
  function setWindow(value) {
    if (!WINDOW_VALUES[value] || state.filters.window === value) return;
    state.filters.window = value; syncControls(); applyFilters();
  }
  function resolveCohort() {
    var parsed = parseCohort(ui.cohortInput.value);
    state.cohort = parsed;
    state.cohortText = ui.cohortInput.value;
    if (parsed.length && parsed.length < PEER_MIN_COHORT) {
      setNotice('stale', tr('List at least two trials to compare. One trial on its own is a dossier, not a comparison.', '请至少列出两项试验进行对照。单项试验属于档案，不构成对照。'));
      return;
    }
    setNotice('', '');
    closeInspector({ restoreFocus: false, writeUrl: false, render: false });
    writeUrl();
    loadMilestones({ replace: true });
  }
  function setMode(value, trigger) {
    if (!MODE_VALUES[value] || state.mode === value) return;
    abort('listController'); state.listToken += 1; abort('detailController'); state.detailToken += 1; abort('facetsController'); state.facetsToken += 1;
    state.mode = value; state.rows = []; state.nextCursor = ''; state.payload = null; state.generation = ''; state.appendFailed = false; state.accessLocked = false; state.restarted = false;
    state.facets = null; state.contractFailed = false; state.workspaceDown = false;
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
    [ui.sponsor, ui.intervention].forEach(function (node) { node.addEventListener('input', function () { window.clearTimeout(debounceId); debounceId = window.setTimeout(applyFilters, 260); }); });
    [ui.field, ui.changeKind, ui.phase, ui.statusFilter, ui.studyType, ui.pcFrom, ui.pcTo, ui.review].forEach(function (node) { node.addEventListener('change', applyFilters); });
    ui.cohortRun.addEventListener('click', resolveCohort);
    ui.cohortInput.addEventListener('keydown', function (event) { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) resolveCohort(); });
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
    ui.clear.addEventListener('click', function () { state.filters = defaultFilters(); state.cohort = []; state.cohortText = ''; state.facets = null; syncControls(); applyFilters(); ui.search.focus(); });
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
      paintFacets(); paintFrame();
      if (state.detail) { var activeRow = selectedRow(); showDetail(state.detail, activeRow && (valueAt(activeRow, 'evidence') || valueAt(activeRow, 'source')), activeRow); }
      else if (state.detailController && ui.inspector.classList.contains('is-open')) detailLoading();
    });
    window.addEventListener('popstate', function () { abort('listController'); closeInspector({ restoreFocus: false, writeUrl: false, render: false }); readUrl(); syncControls(); loadMilestones({ replace: true }); });
    window.addEventListener('resize', function () {
      syncInspectorDialog();
      if (isPeerMode() && state.rows.length && state.peerNarrow !== window.matchMedia('(max-width: 760px)').matches) renderQueue();
    });
  }
  function init() {
    cacheUi(); readUrl(); localizeControls(); syncControls(); bindEvents();
    writeUrl(); paintFrame();
    showInspectorEmpty(tr('Trial dossier', '试验档案'), tr('Choose a ' + activeSingularNoun() + ' to read the current trial record and its source receipt.', '选择一项' + activeSingularNoun() + '，查看当前试验记录及其来源凭证。'));
    loadMilestones({ replace: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

(function () {
  'use strict';

  var API = '/api/biocatalyst/v1/trials';
  var TRIAL_ID = /^NCT\d{8}$/;
  var state = { payload: null, trials: [], visible: [], selectedId: '', selected: null, detail: null, detailToken: 0, listToken: 0, loading: false };
  var ui = {};

  function byId(id) { return document.getElementById(id); }
  function lang() { return document.documentElement.getAttribute('data-lang') === 'zh' ? 'zh' : 'en'; }
  function tr(en, zh) { return lang() === 'zh' ? zh : en; }
  function str(value) { return value == null ? '' : String(value); }
  function arr(value) { return Array.isArray(value) ? value : []; }
  function clean(value) { return str(value).replace(/\s+/g, ' ').trim(); }
  function valueAt(object, key) { return object && typeof object === 'object' ? object[key] : null; }
  function text(node, value) { node.textContent = str(value); return node; }
  function el(tag, className, value) { var node = document.createElement(tag); if (className) node.className = className; if (value != null) text(node, value); return node; }
  function isTrialId(value) { return TRIAL_ID.test(clean(value)); }
  function unique(values) { var seen = {}; return values.filter(function (value) { var key = clean(value); if (!key || seen[key]) return false; seen[key] = true; return true; }); }

  function cacheUi() {
    ui.workspace = byId('bci-workspace'); ui.status = byId('bci-status-label'); ui.statusDetail = byId('bci-status-detail'); ui.runStatus = document.querySelector('.bci-run-status'); ui.refresh = byId('bci-refresh');
    ui.search = byId('bci-search'); ui.phase = byId('bci-phase-filter'); ui.statusFilter = byId('bci-status-filter'); ui.condition = byId('bci-condition-filter'); ui.clear = byId('bci-clear');
    ui.subtitle = byId('bci-queue-subtitle'); ui.asOf = byId('bci-asof'); ui.notice = byId('bci-state-notice'); ui.queue = byId('bci-queue');
    ui.inspector = byId('bci-inspector-pane'); ui.inspectorTitle = byId('bci-inspector-title'); ui.inspectorBody = byId('bci-inspector-body'); ui.inspectorClose = byId('bci-inspector-close'); ui.scrim = byId('bci-scrim');
  }

  function dateLabel(value) {
    var raw = clean(value); if (!raw) return '';
    var date = new Date(raw); if (isNaN(date.getTime())) return raw;
    try { return new Intl.DateTimeFormat(lang() === 'zh' ? 'zh-CN' : 'en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(date); } catch (error) { return raw.slice(0, 10); }
  }
  function titleOf(trial) { return clean(valueAt(trial, 'brief_title')) || clean(valueAt(trial, 'title')) || tr('Untitled trial', '未命名试验'); }
  function phasesOf(trial) { return unique(arr(valueAt(trial, 'phases')).map(clean)); }
  function conditionsOf(trial) { return unique(arr(valueAt(trial, 'conditions')).map(clean)); }
  function sponsorOf(trial) { var sponsor = valueAt(trial, 'sponsor'); return clean(valueAt(sponsor, 'name')); }
  function statusOf(trial) { return clean(valueAt(trial, 'status')); }
  function nctOf(trial) { return clean(valueAt(trial, 'nct_id')); }
  function dateOf(trial, key) {
    var dates = valueAt(trial, 'dates'), value = valueAt(dates, key);
    if (value && typeof value === 'object') return clean(valueAt(value, 'date'));
    return typeof value === 'string' ? clean(value) : '';
  }
  function enrollmentOf(trial) { var enrollment = valueAt(trial, 'enrollment'); var count = valueAt(enrollment, 'count'); return count === 0 || count ? String(count) : ''; }
  function studyTypeOf(trial) { return clean(valueAt(trial, 'study_type')); }

  function validEnvelope(payload) {
    return !!payload && typeof payload === 'object' && payload.schema_version === 'biocatalyst_api.v1' && Array.isArray(payload.trials) &&
      payload.source && typeof payload.source === 'object' && payload.health && typeof payload.health === 'object' &&
      payload.coverage && typeof payload.coverage === 'object' && payload.pagination && typeof payload.pagination === 'object' &&
      Number.isInteger(payload.pagination.total) && payload.pagination.total >= 0 &&
      (payload.pagination.next_cursor == null || typeof payload.pagination.next_cursor === 'string') &&
      payload.authority && payload.authority.classification === 'source_fact' && payload.authority.decision_authority === false;
  }
  function trialSummaryIsValid(trial) {
    return !!trial && typeof trial === 'object' && isTrialId(nctOf(trial)) && !!(clean(valueAt(trial, 'title')) || clean(valueAt(trial, 'brief_title')));
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
  function fetchJson(url) {
    return withAuth({ Accept: 'application/json' }).then(function (headers) {
      return fetch(url, { headers: headers, credentials: 'same-origin', cache: 'no-store' });
    }).then(function (response) {
      if (!response.ok) { var error = new Error('HTTP ' + response.status); error.status = response.status; throw error; }
      return response.json();
    });
  }
  function sameGeneration(left, right) {
    var leftSource = valueAt(left, 'source') || {}, rightSource = valueAt(right, 'source') || {}, leftCoverage = valueAt(left, 'coverage') || {}, rightCoverage = valueAt(right, 'coverage') || {};
    return clean(valueAt(left, 'as_of')) === clean(valueAt(right, 'as_of')) &&
      clean(valueAt(leftSource, 'dataset_timestamp_raw')) === clean(valueAt(rightSource, 'dataset_timestamp_raw')) &&
      valueAt(leftCoverage, 'configured') === valueAt(rightCoverage, 'configured') &&
      valueAt(leftCoverage, 'observed') === valueAt(rightCoverage, 'observed');
  }
  function fetchTrialPages(url, first, collected, seen) {
    return fetchJson(url).then(function (payload) {
      if (!validEnvelope(payload)) throw new Error('Invalid trial list contract');
      if (first && (!sameGeneration(first, payload) || valueAt(first.pagination, 'total') !== valueAt(payload.pagination, 'total'))) throw new Error('Trial generation changed during pagination');
      first = first || payload; collected = collected.concat(payload.trials);
      var total = payload.pagination.total, next = clean(payload.pagination.next_cursor);
      if (collected.length > total || (!next && collected.length !== total) || (next && collected.length >= total)) throw new Error('Invalid trial pagination contract');
      if (!next) { var complete = Object.assign({}, first); complete.trials = collected; complete.pagination = Object.assign({}, first.pagination, { next_cursor: null, loaded: collected.length }); return complete; }
      if (seen[next]) throw new Error('Repeated trial pagination cursor'); seen[next] = true;
      return fetchTrialPages(API + '?limit=250&cursor=' + encodeURIComponent(next), first, collected, seen);
    });
  }
  function fetchTrialQueue() { return fetchTrialPages(API + '?limit=250', null, [], {}); }

  function setStatus(kind, label, detail) {
    ui.runStatus.classList.toggle('is-stale', kind === 'stale'); ui.runStatus.classList.toggle('is-unavailable', kind === 'unavailable' || kind === 'locked');
    text(ui.status, label); text(ui.statusDetail, detail);
  }
  function setNotice(kind, message) { ui.notice.hidden = !message; ui.notice.className = 'bci-state-notice' + (kind ? ' is-' + kind : ''); text(ui.notice, message || ''); }
  function clearChildren(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function emptyCard(title, copy, mark, retry) {
    var wrap = el('div', 'bci-empty'); var inside = el('div'); inside.appendChild(el('span', 'bci-empty-mark', mark || '⌁')); inside.appendChild(el('strong', '', title)); inside.appendChild(el('p', '', copy));
    if (retry) { var button = el('button', '', tr('Try again', '重试')); button.type = 'button'; button.addEventListener('click', loadTrials); inside.appendChild(button); }
    wrap.appendChild(inside); return wrap;
  }
  function loadingQueue() {
    clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'true');
    for (var i = 0; i < 3; i += 1) { var row = el('div', 'bci-skeleton'); row.setAttribute('aria-hidden', 'true'); for (var j = 0; j < 3; j += 1) row.appendChild(el('span')); ui.queue.appendChild(row); }
  }

  function fillSelect(select, values, allEn, allZh) {
    var current = select.value; clearChildren(select); var base = document.createElement('option'); base.value = ''; text(base, tr(allEn, allZh)); select.appendChild(base);
    values.forEach(function (value) { var option = document.createElement('option'); option.value = value; text(option, value); select.appendChild(option); });
    select.value = values.indexOf(current) >= 0 ? current : '';
  }
  function populateFilters() {
    fillSelect(ui.phase, unique([].concat.apply([], state.trials.map(phasesOf))).sort(), 'All phases', '全部阶段');
    fillSelect(ui.statusFilter, unique(state.trials.map(statusOf)).sort(), 'All statuses', '全部状态');
    fillSelect(ui.condition, unique([].concat.apply([], state.trials.map(conditionsOf))).sort(), 'All conditions', '全部适应症');
  }
  function localizeEmptyOptions() {
    [ui.phase, ui.statusFilter, ui.condition].forEach(function (select) {
      var option = select && select.querySelector('option[value=""]');
      if (!option) return;
      text(option, option.getAttribute(lang() === 'zh' ? 'data-label-zh' : 'data-label-en') || option.textContent);
    });
  }
  function filterTrials() {
    var q = clean(ui.search.value).toLowerCase(), phase = ui.phase.value, status = ui.statusFilter.value, condition = ui.condition.value;
    state.visible = state.trials.filter(function (trial) {
      var haystack = [nctOf(trial), titleOf(trial), sponsorOf(trial), conditionsOf(trial).join(' '), phasesOf(trial).join(' '), statusOf(trial)].join(' ').toLowerCase();
      return (!q || haystack.indexOf(q) >= 0) && (!phase || phasesOf(trial).indexOf(phase) >= 0) && (!status || statusOf(trial) === status) && (!condition || conditionsOf(trial).indexOf(condition) >= 0);
    });
  }
  function updateUrl(id) {
    var url = new URL(window.location.href); if (id && isTrialId(id)) url.searchParams.set('trial', id); else url.searchParams.delete('trial'); window.history.replaceState(null, '', url.pathname + (url.search || '') + url.hash);
  }
  function requestedTrial() { var requested = new URLSearchParams(window.location.search).get('trial') || ''; return isTrialId(requested) ? requested : ''; }
  function makeTrialRow(trial, index) {
    var id = nctOf(trial), button = el('button', 'bci-trial' + (id === state.selectedId ? ' is-selected' : ''));
    button.type = 'button'; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', id === state.selectedId ? 'true' : 'false'); button.setAttribute('data-trial-id', id); button.tabIndex = index === 0 ? 0 : -1;
    var main = el('span', 'bci-trial-main'), line = el('span', 'bci-trial-topline'); line.appendChild(el('span', 'bci-trial-id', id)); if (statusOf(trial)) line.appendChild(el('span', 'bci-status-chip', statusOf(trial))); main.appendChild(line); main.appendChild(el('span', 'bci-trial-title', titleOf(trial)));
    var meta = el('span', 'bci-trial-meta'); var phaseText = phasesOf(trial).join(' · '); if (phaseText) meta.appendChild(el('span', '', phaseText)); if (sponsorOf(trial)) meta.appendChild(el('span', '', sponsorOf(trial))); if (enrollmentOf(trial)) meta.appendChild(el('span', '', tr('Enrollment ', '入组人数 ') + enrollmentOf(trial))); main.appendChild(meta); button.appendChild(main);
    var completion = dateOf(trial, 'primary_completion') || dateOf(trial, 'completion'); if (completion) { var date = el('span', 'bci-trial-date'); date.appendChild(el('strong', '', tr('Milestone', '里程碑'))); date.appendChild(document.createTextNode(dateLabel(completion))); button.appendChild(date); }
    button.addEventListener('click', function () { selectTrial(id, true, button); }); return button;
  }
  function renderQueue() {
    clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'false');
    if (!state.visible.length) { ui.queue.appendChild(emptyCard(tr('No trials match', '没有匹配的试验'), tr('Try a broader search or clear a filter.', '请尝试扩大搜索范围或清除筛选。'), '○')); return; }
    state.visible.forEach(function (trial, index) { ui.queue.appendChild(makeTrialRow(trial, index)); });
  }
  function render() {
    filterTrials(); renderQueue();
    var total = state.trials.length, visible = state.visible.length;
    text(ui.subtitle, visible === total ? tr('Current verified records', '当前已核验记录') : tr(visible + ' matching current records', visible + ' 项匹配的当前记录'));
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
  function showInspectorEmpty(title, copy) { text(ui.inspectorTitle, title); clearChildren(ui.inspectorBody); var empty = el('div', 'bci-inspector-empty'); empty.appendChild(el('span', 'bci-empty-orbit')); empty.appendChild(el('p', '', copy)); ui.inspectorBody.appendChild(empty); }
  function showDetail(trial) {
    var detail = state.detail && nctOf(state.detail) === nctOf(trial) ? state.detail : trial, id = nctOf(trial); text(ui.inspectorTitle, tr('Trial detail', '试验详情')); clearChildren(ui.inspectorBody);
    var header = el('div'); header.appendChild(el('h3', 'bci-detail-title', titleOf(detail))); header.appendChild(el('p', 'bci-detail-id', id)); var link = el('a', 'bci-detail-link', tr('Open official registry ↗', '打开官方登记库 ↗')); link.href = 'https://clinicaltrials.gov/study/' + encodeURIComponent(id); link.target = '_blank'; link.rel = 'noopener noreferrer'; header.appendChild(link); ui.inspectorBody.appendChild(header);
    var facts = el('section', 'bci-detail-section'); facts.appendChild(el('h3', '', tr('Current record', '当前记录'))); var grid = el('div', 'bci-detail-grid'), siteCount = valueAt(detail, 'site_count'); [fact(tr('Status', '状态'), statusOf(detail)), fact(tr('Study type', '研究类型'), studyTypeOf(detail)), fact(tr('Sponsor', '申办方'), sponsorOf(detail)), fact(tr('Enrollment', '入组人数'), enrollmentOf(detail)), fact(tr('Sites', '研究中心'), typeof siteCount === 'number' ? String(siteCount) : ''), fact(tr('Start', '开始'), dateLabel(dateOf(detail, 'start'))), fact(tr('Primary completion', '主要完成'), dateLabel(dateOf(detail, 'primary_completion'))), fact(tr('Completion', '完成'), dateLabel(dateOf(detail, 'completion'))), fact(tr('Last update', '最近更新'), dateLabel(clean(valueAt(detail, 'updated_at'))))].forEach(function (item) { if (item) grid.appendChild(item); }); facts.appendChild(grid); ui.inspectorBody.appendChild(facts);
    ui.inspectorBody.appendChild(listSection(tr('Phases', '阶段'), phasesOf(detail), tr('No phase is listed in the current record.', '当前记录未列出阶段。'))); ui.inspectorBody.appendChild(listSection(tr('Conditions', '适应症'), conditionsOf(detail), tr('No condition is listed in the current record.', '当前记录未列出适应症。')));
    var countries = arr(valueAt(detail, 'countries')).map(clean).filter(Boolean); ui.inspectorBody.appendChild(listSection(tr('Countries', '国家与地区'), countries, tr('No trial-site country is listed in the current record.', '当前记录未列出研究中心所在国家或地区。')));
    var interventions = arr(valueAt(detail, 'interventions')).map(function (item) { return clean(valueAt(item, 'name')) || clean(item); }).filter(Boolean); ui.inspectorBody.appendChild(listSection(tr('Interventions', '干预措施'), interventions, tr('No intervention detail is available in this current view.', '当前视图暂无干预措施详情。')));
    var endpoints = valueAt(detail, 'endpoints') || {}; ui.inspectorBody.appendChild(endpointSection(tr('Primary endpoints', '主要终点'), arr(valueAt(endpoints, 'primary')), tr('No primary endpoint is listed in the current record.', '当前记录未列出主要终点。'))); ui.inspectorBody.appendChild(endpointSection(tr('Secondary endpoints', '次要终点'), arr(valueAt(endpoints, 'secondary')), tr('No secondary endpoint is listed in the current record.', '当前记录未列出次要终点。')));
    var history = arr(valueAt(detail, 'history')); if (!history.length) ui.inspectorBody.appendChild(listSection(tr('Change history', '变化历史'), [], tr('No earlier official version is available in this current view.', '当前视图中暂无更早的官方版本。')));
  }
  function openInspector(focus) { ui.inspector.classList.add('is-open'); document.body.classList.add('bci-inspector-open'); ui.scrim.hidden = false; if (focus) ui.inspector.focus({ preventScroll: true }); }
  function closeInspector() { ui.inspector.classList.remove('is-open'); document.body.classList.remove('bci-inspector-open'); ui.scrim.hidden = true; updateUrl(''); }
  function detailLoading() { text(ui.inspectorTitle, tr('Loading detail', '正在载入详情')); clearChildren(ui.inspectorBody); ui.inspectorBody.appendChild(el('div', 'bci-loading-detail', tr('Reading current official record…', '正在读取当前官方记录…'))); }
  function selectTrial(id, update, trigger) {
    var trial = state.trials.filter(function (item) { return nctOf(item) === id; })[0]; if (!trial) { state.selectedId = ''; state.selected = null; state.detail = null; showInspectorEmpty(tr('Trial not found', '未找到试验'), tr('This trial is not present in the current verified generation.', '该试验不在当前已核验生成中。')); return; }
    state.selectedId = id; state.selected = trial; state.detail = null; if (update) updateUrl(id); render(); openInspector(false); detailLoading();
    var token = state.detailToken + 1; state.detailToken = token;
    fetchJson(API + '/' + encodeURIComponent(id)).then(function (payload) {
      if (token !== state.detailToken) return; var detail = payload && (payload.trial || payload); if (!detail || typeof detail !== 'object' || nctOf(detail) !== id) throw new Error('Invalid trial detail contract'); state.detail = detail; showDetail(trial);
    }).catch(function (error) { if (token !== state.detailToken) return; if (error && error.status === 404) showInspectorEmpty(tr('Trial not found', '未找到试验'), tr('This trial is not present in the current verified generation.', '该试验不在当前已核验生成中。')); else showInspectorEmpty(tr('Detail unavailable', '详情暂不可用'), tr('Retry later. The workspace will not infer fields that are absent from the official record.', '请稍后重试。工作区不会推断官方记录中缺失的字段。')); });
    if (trigger) trigger.setAttribute('aria-selected', 'true');
  }
  function updateMetadata(payload) {
    var health = valueAt(payload, 'health') || {}, source = valueAt(payload, 'source') || {}, stateName = clean(valueAt(health, 'state')).toLowerCase(), asOf = clean(valueAt(payload, 'as_of')) || clean(valueAt(source, 'dataset_timestamp_raw'));
    text(ui.asOf, asOf ? tr('As of ', '截至 ') + dateLabel(asOf) : '');
    if (stateName === 'stale') { setStatus('stale', tr('Record being updated', '记录正在更新'), tr('Showing the last verified generation', '正在显示最近一次已核验生成')); setNotice('stale', tr('This registry record is being refreshed. Read the timestamp before relying on it.', '登记记录正在刷新。使用前请先查看时间戳。')); }
    else if (stateName === 'unavailable') { setStatus('unavailable', tr('Freshness status unavailable', '新鲜度状态暂不可用'), tr('Showing the current verified generation', '正在显示当前已核验生成')); setNotice('error', tr('The operational freshness check is unavailable. Read the timestamp before relying on this record.', '运行新鲜度检查暂不可用。使用此记录前请先查看时间戳。')); }
    else { setStatus('ready', tr('Verified registry record', '已核验登记记录'), clean(valueAt(source, 'name')) || tr('Official registry source', '官方登记来源')); setNotice('', ''); }
  }
  function loadTrials() {
    var listToken = state.listToken + 1; state.listToken = listToken;
    state.loading = true; ui.workspace.dataset.state = 'loading'; ui.refresh.classList.add('is-spinning'); loadingQueue(); text(ui.subtitle, tr('Retrieving the verified queue…', '正在获取已核验队列…')); setNotice('', ''); setStatus('ready', tr('Retrieving verified record', '正在获取已核验记录'), tr('Official registry source', '官方登记来源'));
    fetchTrialQueue().then(function (payload) {
      if (listToken !== state.listToken) return; state.payload = payload; state.trials = payload.trials.filter(trialSummaryIsValid); populateFilters(); updateMetadata(payload); state.loading = false; ui.workspace.dataset.state = 'ready'; render();
      var wanted = requestedTrial(); if (wanted) selectTrial(wanted, false);
    }).catch(function (error) {
      if (listToken !== state.listToken) return;
      state.loading = false; ui.workspace.dataset.state = 'unavailable'; clearChildren(ui.queue); ui.queue.setAttribute('aria-busy', 'false');
      if (error && (error.status === 401 || error.status === 403)) { setStatus('locked', tr('Full access required', '需要完整访问权限'), tr('Sign in with an entitled account', '请使用已授权账户登录')); setNotice('locked', tr('Clinical Trial Watch is available with full access. No trial data is shown until access is confirmed.', '临床试验观察需要完整访问权限。访问确认前不会显示试验数据。')); ui.queue.appendChild(emptyCard(tr('Trial data is locked', '试验数据已锁定'), tr('Sign in with full access to read the verified trial record.', '请以完整访问权限登录，读取已核验试验记录。'), '◌')); }
      else { setStatus('unavailable', tr('Record unavailable', '记录暂不可用'), tr('No trial data is inferred', '不会推断试验数据')); setNotice('error', tr('The verified registry record is temporarily unavailable. No trial data is shown.', '已核验登记记录暂不可用。不会显示试验数据。')); ui.queue.appendChild(emptyCard(tr('Trial record unavailable', '试验记录暂不可用'), tr('Retry the source request. This workspace does not fill gaps with estimates.', '请重试来源请求。工作区不会用估计填补空缺。'), '×', true)); }
      showInspectorEmpty(tr('Select a trial', '选择一项试验'), tr('Trial detail will appear here when the current record is available.', '当前记录可用后，试验详情会显示在这里。'));
    }).finally(function () { if (listToken === state.listToken) ui.refresh.classList.remove('is-spinning'); });
  }
  function bindEvents() {
    [ui.search, ui.phase, ui.statusFilter, ui.condition].forEach(function (node) { node.addEventListener(node === ui.search ? 'input' : 'change', function () { render(); }); });
    ui.clear.addEventListener('click', function () { ui.search.value = ''; ui.phase.value = ''; ui.statusFilter.value = ''; ui.condition.value = ''; render(); ui.search.focus(); }); ui.refresh.addEventListener('click', loadTrials);
    ui.inspectorClose.addEventListener('click', closeInspector); ui.scrim.addEventListener('click', closeInspector);
    ui.queue.addEventListener('keydown', function (event) { if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return; var rows = Array.prototype.slice.call(ui.queue.querySelectorAll('.bci-trial')), current = rows.indexOf(document.activeElement); if (!rows.length) return; event.preventDefault(); var next = current < 0 ? 0 : (current + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length; rows[next].focus(); });
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && ui.inspector.classList.contains('is-open')) closeInspector(); }); document.addEventListener('langchange', function () { if (state.payload) { populateFilters(); updateMetadata(state.payload); render(); if (state.selected) showDetail(state.selected); } else localizeEmptyOptions(); });
  }
  function init() { cacheUi(); localizeEmptyOptions(); bindEvents(); showInspectorEmpty(tr('Select a trial', '选择一项试验'), tr('Choose a trial to read its current status, milestones and official evidence.', '选择试验，查看其当前状态、里程碑与官方证据。')); loadTrials(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

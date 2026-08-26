/* portfolio_import_ui.js — A1B paste -> exact review -> one-save surface.

   Private holdings stay in this page. This module emits only privacy-safe lifecycle
   words and delegates persistence to WatchStore.portfolio.importBatch(); it never
   logs, publishes analytics, mutates Watchlists, or invents values for blank fields. */
(function () {
  'use strict';

  function el(id) { return document.getElementById(id); }
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function emit(state) {
    try { document.dispatchEvent(new CustomEvent('pf-import-state', { detail: { state: state } })); }
    catch (e) {}
  }

  var T = {
    en: {
      title: 'Import holdings', intro: 'Paste one holding per line. Blank shares, entry price, and entry date stay blank.',
      grammar: 'Accepted: TICKER · TICKER SHARES · TICKER SHARES ENTRY_PRICE · TICKER SHARES ENTRY_PRICE YYYY-MM-DD',
      placeholder: 'AAPL 10 185.50 2026-01-15\nBRK.B 4\n0700.HK',
      review: 'Review holdings', reviewing: 'Checking coverage…', back: 'Back to paste',
      save: 'Save Portfolio', saving: 'Saving once…', saved: 'Saved. Refreshing your Portfolio…',
      exact: 'Review every row before saving. Duplicate tickers and lots remain separate positions.',
      row: 'row', rows: 'rows', ticker: 'Ticker', shares: 'Shares', price: 'Entry price',
      date: 'Entry date', coverage: 'Coverage', remove: 'Remove',
      covered: 'Covered', uncovered: 'Not covered — kept', unknown: 'Coverage unknown — kept',
      duplicate_ticker: 'Duplicate ticker — kept as a separate lot',
      exact_duplicate: 'Exact duplicate lot — kept as a separate position',
      invalidDraft: 'Fix every visible error before saving.',
      empty: 'Paste at least one valid holding.',
      effectUnknown: 'We could not determine whether this batch saved. Do not try it again here. Reopen Portfolio and verify the rows first.',
      ambiguous: 'The save returned an ambiguous or partial result. Do not retry this batch here.',
      authChanged: 'Your account session changed while saving. This batch is stopped; verify Portfolio before doing anything else.',
      rereadFailed: 'The write was acknowledged, but the authoritative Portfolio reread could not be proven. Verify Portfolio before retrying.',
      rejected: 'Nothing was saved. You can retry this same reviewed draft.',
      localFailed: 'This browser could not save the complete book. Your previous Portfolio is unchanged.',
      localVerifyUnknown: 'This browser wrote the book, but could not verify the resulting Portfolio. Do not retry here. Reopen Portfolio and verify it before doing anything else.',
      unavailable: 'Portfolio is unavailable for writes right now. Nothing was saved.',
      failed: 'The batch was not confirmed. Nothing here will claim it was saved.'
    },
    zh: {
      title: '导入持仓', intro: '每行粘贴一笔持仓。股数、入场价和入场日期留空时会继续保持为空。',
      grammar: '支持：代码 · 代码 股数 · 代码 股数 入场价 · 代码 股数 入场价 YYYY-MM-DD',
      placeholder: 'AAPL 10 185.50 2026-01-15\nBRK.B 4\n0700.HK',
      review: '核对持仓', reviewing: '正在核对覆盖范围…', back: '返回粘贴',
      save: '保存持仓', saving: '正在一次性保存…', saved: '已保存。正在刷新你的持仓…',
      exact: '保存前逐行核对。重复代码与重复批次会保留为独立持仓。',
      row: '行', rows: '行', ticker: '代码', shares: '股数', price: '入场价',
      date: '入场日期', coverage: '覆盖', remove: '移除',
      covered: '已覆盖', uncovered: '未覆盖——仍保留', unknown: '覆盖未知——仍保留',
      duplicate_ticker: '重复代码——作为独立批次保留',
      exact_duplicate: '完全重复批次——作为独立持仓保留',
      invalidDraft: '请先修正所有可见错误，再保存。',
      empty: '请至少粘贴一笔有效持仓。',
      effectUnknown: '无法确认这批持仓是否已保存。请勿在此重试；先重新打开持仓并核对行记录。',
      ambiguous: '保存返回了含糊或部分结果。请勿在此重试这批记录。',
      authChanged: '保存时账户会话发生变化。本批次已停止；继续前请先核对持仓。',
      rereadFailed: '写入已获确认，但无法证明权威持仓重读成功。重试前请先核对持仓。',
      rejected: '没有保存任何记录。你可以用同一份已核对草稿重试。',
      localFailed: '本浏览器无法保存完整账簿。原有持仓保持不变。',
      localVerifyUnknown: '本浏览器已写入账簿，但无法核实保存后的持仓状态。请勿在此重试；先重新打开持仓并核对，再进行其他操作。',
      unavailable: '持仓目前不可写入。没有保存任何记录。',
      failed: '本批次未获确认。页面不会声称已经保存。'
    }
  };
  function L(key) { return (T[lang()] || T.en)[key]; }

  var ERROR = {
    unsupported_percentage: ['Percentage allocations are not supported.', '不支持百分比分配。'],
    unsupported_dollar_allocation: ['Dollar allocations are not supported.', '不支持按金额分配。'],
    unsupported_target_allocation: ['Target allocations are not supported.', '不支持目标权重。'],
    unsupported_cash: ['Cash lines are not supported.', '不支持现金行。'],
    too_many_fields: ['Too many fields.', '字段过多。'], invalid_ticker: ['Invalid ticker.', '代码无效。'],
    invalid_shares: ['Shares must be a finite number.', '股数必须是有限数值。'],
    invalid_price: ['Entry price must be a finite number.', '入场价必须是有限数值。'],
    invalid_date: ['Date must be a real YYYY-MM-DD date.', '日期必须是有效的 YYYY-MM-DD。'],
    uuid_unavailable: ['A secure row identity could not be created.', '无法建立安全的行标识。'],
    invalid_uuid: ['The row identity is invalid.', '行标识无效。'], row_not_found: ['The row no longer exists.', '该行已不存在。']
  };
  function errorText(err) {
    var pair = ERROR[err.code] || [L('failed'), L('failed')];
    return (err.line ? (lang() === 'zh' ? '第 ' + err.line + ' 行 — ' : 'Line ' + err.line + ' — ') : '') +
      pair[lang() === 'zh' ? 1 : 0];
  }

  var draft = { rows: [], errors: [] };
  var editErrors = [];
  var coverageMap = null;
  var step = 'paste';
  var saving = false;
  var completed = false;
  var hardBlocked = false;
  var previousFocus = null;

  function api() { return window.PortfolioImport || null; }
  function store() {
    return window.WatchStore && window.WatchStore.portfolio && window.WatchStore.portfolio.importBatch
      ? window.WatchStore.portfolio : null;
  }
  function coverage(ticker) {
    if (!coverageMap) return null;
    return Object.prototype.hasOwnProperty.call(coverageMap, ticker);
  }
  function setStatus(message, tone) {
    var host = el('pfi_status'); if (!host) return;
    host.textContent = message || '';
    host.className = 'pfi-status' + (tone ? ' is-' + tone : '');
    host.style.display = message ? 'block' : 'none';
  }
  function open() {
    var dlg = el('dlg-import'); if (!dlg || hardBlocked) return;
    previousFocus = document.activeElement;
    dlg.classList.add('open');
    document.documentElement.classList.add('mx5-dlg-lock');
    step = 'paste'; saving = false; completed = false; draft = { rows: [], errors: [] }; editErrors = [];
    render();
    var input = el('pfi_paste'); if (input) setTimeout(function () { input.focus(); }, 0);
  }
  function close() {
    if (saving) return;
    var dlg = el('dlg-import'); if (!dlg) return;
    dlg.classList.remove('open');
    document.documentElement.classList.remove('mx5-dlg-lock');
    if (previousFocus && previousFocus.focus) { try { previousFocus.focus(); } catch (e) {} }
    previousFocus = null;
  }

  function renderErrors() {
    var host = el('pfi_errors'); if (!host) return;
    var errors = (draft.errors || []).concat(editErrors || []);
    host.innerHTML = errors.length ? '<ul>' + errors.map(function (err) {
      return '<li>' + esc(errorText(err)) + '</li>';
    }).join('') + '</ul>' : '';
    host.style.display = errors.length ? 'block' : 'none';
  }
  function warningHtml(row) {
    return (row.warnings || []).map(function (warning) {
      return '<span class="pfi-warning">' + esc(L(warning)) + '</span>';
    }).join('');
  }
  function reviewRow(row) {
    var c = row.coverage || 'unknown';
    var locked = saving || completed || hardBlocked ? ' disabled aria-disabled="true"' : '';
    return '<div class="pfi-review-row" data-pfi-row="' + esc(row.id) + '">' +
      '<label><span>' + esc(L('ticker')) + '</span><input class="wl-in" data-pfi-field="ticker" value="' + esc(row.ticker) + '"' + locked + '></label>' +
      '<label><span>' + esc(L('shares')) + '</span><input class="wl-in fig" data-pfi-field="shares" inputmode="decimal" value="' + esc(row.shares == null ? '' : row.shares) + '"' + locked + '></label>' +
      '<label><span>' + esc(L('price')) + '</span><input class="wl-in fig" data-pfi-field="entry_price" inputmode="decimal" value="' + esc(row.entry_price == null ? '' : row.entry_price) + '"' + locked + '></label>' +
      '<label><span>' + esc(L('date')) + '</span><input class="wl-in fig" data-pfi-field="entry_date" type="date" value="' + esc(row.entry_date || '') + '"' + locked + '></label>' +
      '<div class="pfi-row-meta"><span class="pfi-coverage is-' + esc(c) + '">' + esc(L(c)) + '</span>' + warningHtml(row) + '</div>' +
      '<button class="gbtn gbtn-sm pfi-remove" type="button" data-pfi-remove="' + esc(row.id) + '"' + locked + '>' + esc(L('remove')) + '</button>' +
      '</div>';
  }
  function render() {
    var pasteView = el('pfi_paste_view'), reviewView = el('pfi_review_view');
    if (pasteView) pasteView.style.display = step === 'paste' ? 'block' : 'none';
    if (reviewView) reviewView.style.display = step === 'review' ? 'block' : 'none';
    var title = el('pfi_title'); if (title) title.textContent = L('title');
    var intro = el('pfi_intro'); if (intro) intro.textContent = L('intro');
    var grammar = el('pfi_grammar'); if (grammar) grammar.textContent = L('grammar');
    var paste = el('pfi_paste'); if (paste) paste.placeholder = L('placeholder');
    var reviewBtn = el('pfi_review'); if (reviewBtn) reviewBtn.textContent = L('review');
    var exact = el('pfi_exact'); if (exact) exact.textContent = L('exact');
    var back = el('pfi_back'); if (back) back.textContent = L('back');
    var list = el('pfi_rows'); if (list) list.innerHTML = draft.rows.map(reviewRow).join('');
    var count = el('pfi_count');
    if (count) count.textContent = draft.rows.length + ' ' + L(draft.rows.length === 1 ? 'row' : 'rows');
    var save = el('pfi_save');
    if (save) {
      save.textContent = saving ? L('saving') : L('save');
      save.disabled = saving || completed || hardBlocked || !draft.rows.length || !!draft.errors.length || !!editErrors.length;
    }
    renderErrors();
  }

  function parseReview() {
    var contract = api(), input = el('pfi_paste'), button = el('pfi_review');
    if (!contract || !input) { setStatus(L('failed'), 'bad'); return; }
    if (button) { button.disabled = true; button.textContent = L('reviewing'); }
    var load = window.SD && window.SD.loadIndexes
      ? window.SD.loadIndexes(['us', 'cn', 'hk', 'ca', 'intl'])
      : Promise.resolve(null);
    Promise.resolve(load).catch(function () { return null; }).then(function (index) {
      coverageMap = index && index.byTicker ? index.byTicker : null;
      draft = contract.parse(input.value, { isCovered: coverage });
      editErrors = [];
      step = 'review';
      if (button) button.disabled = false;
      setStatus(!draft.rows.length ? L('empty') : (draft.errors.length ? L('invalidDraft') : ''), draft.errors.length ? 'bad' : '');
      render();
      var first = el('pfi_rows') && el('pfi_rows').querySelector('input');
      if (first) first.focus();
    });
  }

  function editRow(target) {
    if (saving || completed || hardBlocked) return;
    var rowHost = target.closest('[data-pfi-row]');
    if (!rowHost || !api()) return;
    var patch = {}, field = target.getAttribute('data-pfi-field');
    patch[field] = target.value;
    var result = api().edit(draft.rows, rowHost.getAttribute('data-pfi-row'), patch, { isCovered: coverage });
    editErrors = result.errors || [];
    if (result.ok) draft.rows = result.rows;
    setStatus(editErrors.length ? L('invalidDraft') : '', editErrors.length ? 'bad' : '');
    render();
  }
  function removeRow(id) {
    if (saving || completed || hardBlocked) return;
    if (!api()) return;
    draft.rows = api().remove(draft.rows, id).rows;
    editErrors = [];
    setStatus(!draft.rows.length ? L('empty') : (draft.errors.length ? L('invalidDraft') : ''),
      draft.errors.length ? 'bad' : '');
    render();
  }
  function failureMessage(result) {
    if (!result) return L('failed');
    if (result.state === 'effect_unknown') return L('effectUnknown');
    if (result.state === 'some' || result.state === 'conflict' || result.state === 'owner_conflict' || result.state === 'ambiguous_receipt') return L('ambiguous');
    if (result.state === 'stale_auth') return L('authChanged');
    if (result.state === 'authoritative_reread_failed' || result.state === 'authoritative_reread_mismatch') return L('rereadFailed');
    if (result.state === 'rejected') return L('rejected');
    if (result.state === 'local_write_failed') return L('localFailed');
    if (result.state === 'local_verify_failed') return L('localVerifyUnknown');
    if (result.state === 'unavailable') return L('unavailable');
    return L('failed');
  }
  function isTerminal(result) {
    return !result || ['effect_unknown', 'some', 'conflict', 'owner_conflict', 'ambiguous_receipt',
      'stale_auth', 'authoritative_reread_failed', 'authoritative_reread_mismatch',
      'local_verify_failed'].indexOf(result.state) >= 0;
  }
  function save() {
    var contract = api(), persistence = store();
    if (saving || completed || hardBlocked || !contract || !persistence) return;
    var check = contract.validate(draft.rows);
    if (!check.ok || draft.errors.length || editErrors.length) { setStatus(L('invalidDraft'), 'bad'); render(); return; }
    var frozenRows = draft.rows.map(function (row) { return Object.assign({}, row); });
    saving = true; setStatus('', ''); emit('saving'); render();
    var pending;
    try { pending = persistence.importBatch(frozenRows); }
    catch (e) { pending = Promise.reject(e); }
    Promise.resolve(pending).then(function (result) {
      saving = false;
      if (result && result.ok) {
        completed = true;
        setStatus(L('saved'), 'good'); emit('saved'); render();
        setTimeout(close, 700);
        return;
      }
      hardBlocked = isTerminal(result);
      if (hardBlocked && el('pf_import')) {
        el('pf_import').disabled = true;
        el('pf_import').setAttribute('aria-disabled', 'true');
      }
      setStatus(failureMessage(result), 'bad'); emit('failed'); render();
    }).catch(function () {
      saving = false; hardBlocked = true;
      if (el('pf_import')) {
        el('pf_import').disabled = true;
        el('pf_import').setAttribute('aria-disabled', 'true');
      }
      setStatus(L('effectUnknown'), 'bad'); emit('failed'); render();
    });
  }

  function init() {
    var host = el('dlg-import'), launch = el('pf_import');
    if (!host || !launch) return;
    launch.addEventListener('click', open);
    host.addEventListener('click', function (e) {
      if (e.target && e.target.getAttribute('data-pfi-close') !== null) { close(); return; }
      var remove = e.target && e.target.closest ? e.target.closest('[data-pfi-remove]') : null;
      if (remove) removeRow(remove.getAttribute('data-pfi-remove'));
    });
    host.addEventListener('change', function (e) {
      if (e.target && e.target.getAttribute('data-pfi-field')) editRow(e.target);
    });
    var review = el('pfi_review'); if (review) review.addEventListener('click', parseReview);
    var back = el('pfi_back'); if (back) back.addEventListener('click', function () {
      if (saving || hardBlocked) return; step = 'paste'; setStatus('', ''); render();
    });
    var saveBtn = el('pfi_save'); if (saveBtn) saveBtn.addEventListener('click', save);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && host.classList.contains('open')) { close(); e.preventDefault(); }
    });
    document.addEventListener('langchange', function () { if (host.classList.contains('open')) render(); });
    render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

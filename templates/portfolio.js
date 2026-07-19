/* portfolio.js — Portfolio section module for the watchlist page.

   Owns #pf_section and all DOM within it. Inert on pages that lack the section.
   Auth state arrives via document 'wl-auth' events dispatched by watchstore.js.
   Price/signal data comes from window.SD (stockdata.js). Portfolio CRUD goes
   through window.WatchStore.portfolio (watchstore.js relational path).

   Factor wiring: after every render, pushes {ticker->dollarValue} weights to
   window.FX.setAutoWeights() so the factor exposure panel reflects the actual book.

   No localStorage, no engine/data writes, no network except WatchStore.portfolio
   and SD.loadTicker/loadIndex. */
(function () {
  'use strict';

  // ---- guard: only active when the section exists --------------------------
  function section() { return document.getElementById('pf_section'); }

  // ---- i18n ----------------------------------------------------------------
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  var T = {
    en: {
      signedOutPrompt: 'Sign in to track your portfolio positions.',
      signInBtn: 'Sign in',
      emptyHeading: 'No open positions yet.',
      emptyAdd: 'Add your first position',
      addBtn: '+ Add position',
      colTicker: 'Ticker',
      colName: 'Name',
      colSignal: 'Signal',
      colShares: 'Shares',
      colEntry: 'Entry $',
      colDate: 'Date',
      colLast: 'Last',
      colSince: 'Since entry',
      colEdit: '',
      editBtn: 'Edit',
      closedHeading: 'Closed positions',
      closedCount: function (n) { return n + ' closed'; },
      unavailable: 'Portfolio unavailable right now — your data is safe.',
      modalAddTitle: 'Add position',
      modalEditTitle: 'Edit position',
      tickerLabel: 'Ticker',
      sharesLabel: 'Shares',
      entryLabel: 'Entry price',
      dateLabel: 'Entry date',
      notesLabel: 'Notes',
      statusLabel: 'Status',
      statusOpen: 'Open',
      statusClosed: 'Closed',
      saveBtn: 'Save',
      tickerRequired: 'Ticker is required.',
      saveError: 'Could not save — please try again.',
      notCovered: 'Not in our coverage — price and signal will show —',
      asof: 'as of'
    },
    zh: {
      signedOutPrompt: '登录以追踪你的持仓。',
      signInBtn: '登录',
      emptyHeading: '暂无开仓持仓。',
      emptyAdd: '添加第一笔持仓',
      addBtn: '+ 添加持仓',
      colTicker: '代码',
      colName: '名称',
      colSignal: '信号',
      colShares: '份额',
      colEntry: '入场价',
      colDate: '日期',
      colLast: '最新价',
      colSince: '入场以来',
      colEdit: '',
      editBtn: '编辑',
      closedHeading: '已平仓',
      closedCount: function (n) { return n + ' 条已平仓'; },
      unavailable: '暂时无法加载持仓——你的数据安全无虞。',
      modalAddTitle: '添加持仓',
      modalEditTitle: '编辑持仓',
      tickerLabel: '代码',
      sharesLabel: '份额',
      entryLabel: '入场价',
      dateLabel: '入场日期',
      notesLabel: '备注',
      statusLabel: '状态',
      statusOpen: '开仓',
      statusClosed: '已平仓',
      saveBtn: '保存',
      tickerRequired: '代码不能为空。',
      saveError: '保存失败——请重试。',
      notCovered: '不在覆盖范围——价格与信号将显示 —',
      asof: '数据截至'
    }
  };
  function L(k) { return (T[lang()] || T.en)[k]; }

  // ---- tiny utils ----------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtNum(v, nd) {
    if (v === null || v === undefined || v === '' || isNaN(Number(v))) return '—';
    return Number(v).toFixed(nd != null ? nd : 2);
  }
  function fmtPct(num, denom) {
    if (!num || !denom || denom === 0) return '—';
    var pct = (num - denom) / denom * 100;
    return (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
  }

  // ---- state ---------------------------------------------------------------
  var rows = null;          // array of portfolio_positions rows, null until loaded
  var editingId = null;
  var priceCache = {};      // ticker -> {price, asof} from SD.loadTicker; null for uncovered
  var pricesLoaded = false; // prevent re-entrant lazy fill loops
  var lastListAt = 0;       // epoch ms of last successful list() call
  var sdIndex = null;       // {byTicker} from SD.loadIndex, loaded once
  var prevFocusEl = null;   // for focus restore on modal close

  // ---- view helpers --------------------------------------------------------
  function showEl(id) { var e = el(id); if (e) e.style.display = ''; }
  function hideEl(id) { var e = el(id); if (e) e.style.display = 'none'; }
  function setText(id, txt) { var e = el(id); if (e) e.textContent = txt; }

  function showSigned(user) {
    hideEl('pf_signedout');
    hideEl('pf_err_inline');
    // show desk or empty depending on rows
    refreshView();
  }

  function showSignedOut() {
    hideEl('pf_desk');
    hideEl('pf_empty');
    hideEl('pf_add');
    hideEl('pf_closed');
    hideEl('pf_err_inline');
    showEl('pf_signedout');
  }

  function showError() {
    hideEl('pf_desk');
    hideEl('pf_empty');
    hideEl('pf_add');
    hideEl('pf_closed');
    hideEl('pf_signedout');
    var errDiv = el('pf_err_inline');
    if (errDiv) {
      errDiv.textContent = L('unavailable');
      errDiv.style.display = 'block';
    }
  }

  // ---- index ---------------------------------------------------------------
  function ensureIndex() {
    if (sdIndex) return Promise.resolve(sdIndex);
    if (!window.SD || !window.SD.loadIndex) return Promise.resolve(null);
    return window.SD.loadIndex().then(function (r) {
      sdIndex = r;
      return r;
    }).catch(function () { return null; });
  }

  function tickerName(ticker) {
    if (!sdIndex) return '—';
    var rec = sdIndex.byTicker && sdIndex.byTicker[ticker];
    return rec ? rec.n || '—' : '—';
  }

  function tickerSt(ticker) {
    if (!sdIndex) return null;
    var rec = sdIndex.byTicker && sdIndex.byTicker[ticker];
    return rec ? rec.st || null : null;
  }

  function signalPill(ticker) {
    var st = tickerSt(ticker);
    if (!st || !window.SD) return '—';
    return '<span class="state ' + esc(window.SD.stClass(st)) + '">' + esc(window.SD.label(st)) + '</span>';
  }

  // ---- open/closed split ---------------------------------------------------
  function openRows() {
    if (!rows) return [];
    return rows.filter(function (r) { return r.status !== 'closed'; })
      .sort(function (a, b) { return (a.ticker || '').localeCompare(b.ticker || ''); });
  }

  function closedRows() {
    if (!rows) return [];
    return rows.filter(function (r) { return r.status === 'closed'; })
      .sort(function (a, b) { return (a.ticker || '').localeCompare(b.ticker || ''); });
  }

  // ---- factor weight wiring ------------------------------------------------
  function pushFxWeights() {
    if (!window.FX || !window.FX.setAutoWeights) return;
    var open = openRows();
    var w = {};
    open.forEach(function (r) {
      var t = r.ticker;
      var sh = r.shares != null ? Number(r.shares) : 0;
      var pc = priceCache[t];
      var price = (pc && pc.price > 0) ? pc.price : 0;
      if (sh > 0 && price > 0) w[t] = sh * price;
    });
    if (Object.keys(w).length >= 2) {
      window.FX.setAutoWeights(w);
    } else {
      window.FX.setAutoWeights(null);
    }
  }

  // ---- row HTML ------------------------------------------------------------
  function openRowHTML(r) {
    var t = esc(r.ticker || '');
    var rawT = r.ticker || '';
    var name = esc(tickerName(rawT));
    var pc = priceCache[rawT];
    var lastPrice = (pc && pc.price != null) ? ('~' + Number(pc.price).toFixed(2)) : '—';
    var entryP = (r.entry_price != null && r.entry_price !== '') ? Number(r.entry_price) : null;
    var curPrice = (pc && pc.price != null) ? Number(pc.price) : null;
    var sinceHtml = '—';
    if (entryP !== null && curPrice !== null && entryP !== 0) {
      var pct = (curPrice - entryP) / entryP * 100;
      var color = pct >= 0 ? 'var(--up, #22c55e)' : 'var(--down, #ef4444)';
      sinceHtml = '<span style="color:' + color + '">' +
        (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%</span>';
    }
    return '<tr>' +
      '<td><a href="stock.html#' + encodeURIComponent(rawT) + '">' + t + '</a></td>' +
      '<td>' + name + '</td>' +
      '<td>' + signalPill(rawT) + '</td>' +
      '<td class="tabnum">' + (r.shares != null ? esc(String(r.shares)) : '—') + '</td>' +
      '<td class="tabnum">' + (entryP !== null ? entryP.toFixed(2) : '—') + '</td>' +
      '<td>' + esc(r.entry_date || '—') + '</td>' +
      '<td class="tabnum">' + lastPrice + '</td>' +
      '<td class="tabnum">' + sinceHtml + '</td>' +
      '<td><button class="wl-btn" data-edit="' + esc(String(r.id)) + '">' + esc(L('editBtn')) + '</button></td>' +
      '</tr>';
  }

  function closedRowHTML(r) {
    var t = esc(r.ticker || '');
    var rawT = r.ticker || '';
    var name = esc(tickerName(rawT));
    var entryP = (r.entry_price != null && r.entry_price !== '') ? Number(r.entry_price) : null;
    return '<tr>' +
      '<td><a href="stock.html#' + encodeURIComponent(rawT) + '">' + t + '</a></td>' +
      '<td>' + name + '</td>' +
      '<td class="tabnum">' + (r.shares != null ? esc(String(r.shares)) : '—') + '</td>' +
      '<td class="tabnum">' + (entryP !== null ? entryP.toFixed(2) : '—') + '</td>' +
      '<td>' + esc(r.entry_date || '—') + '</td>' +
      '<td><button class="wl-btn" data-edit="' + esc(String(r.id)) + '">' + esc(L('editBtn')) + '</button></td>' +
      '</tr>';
  }

  // ---- render --------------------------------------------------------------
  function render() {
    if (!section()) return;
    var open = openRows();
    var closed = closedRows();

    // relabel static chrome
    relabelStatic();

    // empty vs table
    var addBtn = el('pf_add');
    if (open.length === 0 && closed.length === 0) {
      hideEl('pf_desk');
      showEl('pf_empty');
      if (addBtn) addBtn.style.display = 'none';
      hideEl('pf_closed');
    } else {
      hideEl('pf_empty');
      showEl('pf_desk');
      if (addBtn) addBtn.style.display = '';
      var tbody = el('pf_rows');
      if (tbody) tbody.innerHTML = open.map(openRowHTML).join('');

      // closed section
      var cl = el('pf_closed');
      if (cl) {
        if (closed.length > 0) {
          cl.style.display = '';
          var cn = el('pf_closed_n');
          if (cn) cn.textContent = L('closedCount')(closed.length);
          var ctbody = el('pf_closed_rows');
          if (ctbody) ctbody.innerHTML = closed.map(closedRowHTML).join('');
        } else {
          cl.style.display = 'none';
        }
      }
    }

    // as-of footnote: use latest asof from priceCache
    var asofEl = el('pf_asof');
    if (asofEl) {
      var asofVal = '';
      Object.keys(priceCache).forEach(function (t) {
        var pc = priceCache[t];
        if (pc && pc.asof && pc.asof > asofVal) asofVal = pc.asof;
      });
      asofEl.textContent = asofVal ? L('asof') + ' ' + asofVal : '';
    }

    // factor wiring
    pushFxWeights();

    // lazy price fill
    if (!pricesLoaded && rows && rows.length > 0) {
      pricesLoaded = true;
      var tickers = [];
      var seen = {};
      rows.forEach(function (r) {
        if (r.ticker && !seen[r.ticker]) { seen[r.ticker] = 1; tickers.push(r.ticker); }
      });
      if (tickers.length > 0 && window.SD && window.SD.loadTicker) {
        Promise.all(tickers.map(function (t) {
          return window.SD.loadTicker(t).then(function (j) {
            if (j && j.tech && j.tech.price != null) {
              priceCache[t] = { price: j.tech.price, asof: j.asof || '' };
            } else {
              priceCache[t] = null;
            }
          }).catch(function () { priceCache[t] = null; });
        })).then(function () {
          render(); // one re-render pass with prices filled
        });
      }
    }
  }

  // ---- refreshView after auth -------------------------------------------------
  function refreshView() {
    if (!rows) return;
    var open = openRows();
    var closed = closedRows();
    if (open.length === 0 && closed.length === 0) {
      showEl('pf_empty');
      hideEl('pf_desk');
      var ab = el('pf_add'); if (ab) ab.style.display = 'none';
    } else {
      showEl('pf_desk');
      hideEl('pf_empty');
      var ab2 = el('pf_add'); if (ab2) ab2.style.display = '';
    }
    render();
  }

  // ---- static label relabeling (bilingual) ---------------------------------
  function relabelStatic() {
    // thead columns
    var thIds = [
      ['pf_th_ticker', 'colTicker'],
      ['pf_th_name', 'colName'],
      ['pf_th_signal', 'colSignal'],
      ['pf_th_shares', 'colShares'],
      ['pf_th_entry', 'colEntry'],
      ['pf_th_date', 'colDate'],
      ['pf_th_last', 'colLast'],
      ['pf_th_since', 'colSince']
    ];
    thIds.forEach(function (pair) {
      var e = el(pair[0]); if (e) e.textContent = L(pair[1]);
    });
    // add button
    var addBtn = el('pf_add'); if (addBtn) addBtn.textContent = L('addBtn');
    // modal labels (relabeled in-place)
    var pfmlbl = [
      ['pfm_lbl_ticker', 'tickerLabel'],
      ['pfm_lbl_shares', 'sharesLabel'],
      ['pfm_lbl_entry', 'entryLabel'],
      ['pfm_lbl_date', 'dateLabel'],
      ['pfm_lbl_notes', 'notesLabel'],
      ['pfm_lbl_status', 'statusLabel'],
      ['pfm_save', 'saveBtn']
    ];
    pfmlbl.forEach(function (pair) {
      var e = el(pair[0]); if (e) e.textContent = L(pair[1]);
    });
    // status options
    var selEl = el('pfm_status');
    if (selEl && selEl.options) {
      if (selEl.options[0]) selEl.options[0].text = L('statusOpen');
      if (selEl.options[1]) selEl.options[1].text = L('statusClosed');
    }
    // signed-out prompt
    var sop = el('pf_signedout');
    if (sop) {
      var p = sop.querySelector('p');
      if (p) p.textContent = L('signedOutPrompt');
    }
    // empty heading
    var emph = el('pf_empty');
    if (emph) {
      var h = emph.querySelector('p');
      if (h) h.textContent = L('emptyHeading');
    }
    // closed heading
    var clSum = el('pf_closed');
    if (clSum) {
      var sumEl = clSum.querySelector('summary');
      if (sumEl) {
        var sumSpan = sumEl.querySelector('span:not(#pf_closed_n)');
        if (sumSpan) sumSpan.textContent = L('closedHeading');
      }
    }
  }

  // ---- modal ---------------------------------------------------------------
  function pfOpenDlg(id) {
    var dlg = el('dlg-holding'); if (!dlg) return;
    prevFocusEl = document.activeElement;
    dlg.classList.add('open');
    document.documentElement.classList.add('mx5-dlg-lock');
    var first = dlg.querySelector('input, select, textarea, button');
    if (first) setTimeout(function () { first.focus(); }, 0);
  }

  function pfCloseDlg() {
    var dlg = el('dlg-holding'); if (!dlg) return;
    dlg.classList.remove('open');
    document.documentElement.classList.remove('mx5-dlg-lock');
    if (prevFocusEl && prevFocusEl.focus) {
      try { prevFocusEl.focus(); } catch (e) {}
    }
    prevFocusEl = null;
  }

  function clearModal() {
    var fields = ['pfm_ticker', 'pfm_shares', 'pfm_price', 'pfm_date', 'pfm_notes'];
    fields.forEach(function (id) { var e = el(id); if (e) e.value = ''; });
    var statusRow = el('pfm_status_row');
    if (statusRow) statusRow.style.display = 'none';
    var statusSel = el('pfm_status');
    if (statusSel) statusSel.value = 'open';
    var errEl = el('pfm_err'); if (errEl) errEl.textContent = '';
    var hintEl = el('pfm_hint'); if (hintEl) hintEl.textContent = '';
    var suggEl = el('pfm_sugg'); if (suggEl) suggEl.innerHTML = '';
  }

  function openAddModal() {
    if (!section()) return;
    editingId = null;
    clearModal();
    setText('pfm_title', L('modalAddTitle'));
    pfOpenDlg();
  }

  function openEditModal(id) {
    if (!section() || !rows) return;
    var row = null;
    for (var i = 0; i < rows.length; i++) {
      if (String(rows[i].id) === String(id)) { row = rows[i]; break; }
    }
    if (!row) return;
    editingId = id;
    clearModal();
    setText('pfm_title', L('modalEditTitle'));
    var te = el('pfm_ticker'); if (te) te.value = row.ticker || '';
    var se = el('pfm_shares'); if (se) se.value = row.shares != null ? String(row.shares) : '';
    var pe = el('pfm_price'); if (pe) pe.value = row.entry_price != null ? String(row.entry_price) : '';
    var de = el('pfm_date'); if (de) de.value = row.entry_date || '';
    var ne = el('pfm_notes'); if (ne) ne.value = row.notes || '';
    var statusRow = el('pfm_status_row');
    if (statusRow) statusRow.style.display = '';
    var statusSel = el('pfm_status');
    if (statusSel) statusSel.value = row.status === 'closed' ? 'closed' : 'open';
    // show hint if ticker not covered
    updateTickerHint(row.ticker || '');
    pfOpenDlg();
  }

  // ---- ticker suggest in modal ---------------------------------------------
  function updateTickerHint(ticker) {
    var hintEl = el('pfm_hint'); if (!hintEl) return;
    if (!ticker) { hintEl.textContent = ''; return; }
    if (!sdIndex) { hintEl.textContent = ''; return; }
    var covered = sdIndex.byTicker && sdIndex.byTicker[ticker.toUpperCase()];
    hintEl.textContent = covered ? '' : L('notCovered');
  }

  function wireTickerSuggest() {
    var input = el('pfm_ticker'); if (!input) return;
    var suggEl = el('pfm_sugg'); if (!suggEl) return;

    input.addEventListener('input', function () {
      var v = input.value.trim();
      updateTickerHint(v.toUpperCase());
      if (!v || !sdIndex || !sdIndex.list) { suggEl.innerHTML = ''; return; }
      var vl = v.toLowerCase();
      var matches = sdIndex.list.filter(function (x) {
        return x.t.toLowerCase().indexOf(vl) === 0 ||
               (x.n && x.n.toLowerCase().indexOf(vl) >= 0);
      }).slice(0, 8);
      if (!matches.length) { suggEl.innerHTML = ''; return; }
      suggEl.innerHTML = matches.map(function (x) {
        return '<div data-sugg="' + esc(x.t) + '"><b>' + esc(x.t) + '</b> <small>' +
          esc(x.n || '') + '</small></div>';
      }).join('');
    });

    suggEl.addEventListener('mousedown', function (e) {
      var d = e.target.closest('[data-sugg]'); if (!d) return;
      var t = d.getAttribute('data-sugg');
      input.value = t;
      updateTickerHint(t);
      suggEl.innerHTML = '';
      e.preventDefault(); // prevent blur from firing before mousedown completes
    });

    // clear suggestions on blur
    input.addEventListener('blur', function () {
      setTimeout(function () { if (suggEl) suggEl.innerHTML = ''; }, 200);
    });
  }

  // ---- save ----------------------------------------------------------------
  function doSave() {
    if (!section()) return;
    var saveBtn = el('pfm_save'); if (!saveBtn) return;
    var errEl = el('pfm_err');

    var ticker = (el('pfm_ticker') ? el('pfm_ticker').value.trim().toUpperCase() : '');
    if (!ticker) {
      if (errEl) errEl.textContent = L('tickerRequired');
      return;
    }

    var shares = el('pfm_shares') ? el('pfm_shares').value.trim() : '';
    var entryPrice = el('pfm_price') ? el('pfm_price').value.trim() : '';
    var entryDate = el('pfm_date') ? el('pfm_date').value.trim() : '';
    var notes = el('pfm_notes') ? el('pfm_notes').value.trim() : '';
    var statusSel = el('pfm_status');
    var status = (statusSel && statusSel.value === 'closed') ? 'closed' : 'open';

    var pos = {
      ticker: ticker,
      shares: shares,
      entry_price: entryPrice,
      entry_date: entryDate || null,
      notes: notes,
      status: status
    };
    if (editingId) pos.id = editingId;

    if (errEl) errEl.textContent = '';
    saveBtn.disabled = true;

    if (!window.WatchStore || !window.WatchStore.portfolio) {
      if (errEl) errEl.textContent = L('saveError');
      saveBtn.disabled = false;
      return;
    }

    window.WatchStore.portfolio.upsert(pos).then(function (result) {
      saveBtn.disabled = false;
      if (!result) {
        if (errEl) errEl.textContent = L('saveError');
        return;
      }
      pfCloseDlg();
      pricesLoaded = false; // reset so prices are lazily re-filled
      window.WatchStore.portfolio.list().then(function (newRows) {
        rows = newRows || [];
        render();
      }).catch(function () {
        rows = rows || [];
        render();
      });
    }).catch(function () {
      saveBtn.disabled = false;
      if (errEl) errEl.textContent = L('saveError');
    });
  }

  // ---- visibility refetch --------------------------------------------------
  var lastRefetchAt = 0;
  document.addEventListener('visibilitychange', function () {
    if (!section()) return;
    if (document.hidden) return;
    var dlg = el('dlg-holding');
    if (dlg && dlg.classList.contains('open')) return;
    var now = Date.now();
    if (now - lastListAt < 60000) return;
    if (!window.WatchStore || !window.WatchStore.user || !window.WatchStore.user()) return;
    lastListAt = now;
    lastRefetchAt = now;
    window.WatchStore.portfolio.list().then(function (newRows) {
      rows = newRows || [];
      pricesLoaded = false;
      render();
    }).catch(function () {});
  });

  // ---- auth event ----------------------------------------------------------
  function onAuth(user) {
    if (!section()) return;
    if (!user) {
      rows = null;
      priceCache = {};
      pricesLoaded = false;
      if (window.FX && window.FX.setAutoWeights) window.FX.setAutoWeights(null);
      showSignedOut();
      return;
    }
    // signed in: load portfolio
    if (!window.WatchStore || !window.WatchStore.portfolio) {
      showError();
      return;
    }
    lastListAt = Date.now();
    window.WatchStore.portfolio.list().then(function (newRows) {
      rows = newRows || [];
      pricesLoaded = false;
      hideEl('pf_signedout');
      hideEl('pf_err_inline');
      showEl('pf_add');
      refreshView();
    }).catch(function () {
      showError();
    });
  }

  // ---- event wiring --------------------------------------------------------
  function wireEvents() {
    // modal Esc + backdrop close
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var dlg = el('dlg-holding');
        if (dlg && dlg.classList.contains('open')) { pfCloseDlg(); }
      }
    });

    // backdrop click
    var dlg = el('dlg-holding');
    if (dlg) {
      dlg.addEventListener('click', function (e) {
        if (e.target && e.target.getAttribute('data-close') !== null) pfCloseDlg();
      });
    }

    // add button
    var addBtn = el('pf_add'); if (addBtn) {
      addBtn.addEventListener('click', openAddModal);
    }
    var addFirst = el('pf_add_first'); if (addFirst) {
      addFirst.addEventListener('click', openAddModal);
    }

    // sign-in button in signed-out box
    var sinBtn = el('pf_signin_btn'); if (sinBtn) {
      sinBtn.addEventListener('click', function () {
        if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signin');
      });
    }

    // save button
    var saveBtn = el('pfm_save'); if (saveBtn) {
      saveBtn.addEventListener('click', doSave);
    }

    // event delegation for edit buttons in table rows
    var sec = section();
    if (sec) {
      sec.addEventListener('click', function (e) {
        var editBtn = e.target.closest('[data-edit]');
        if (editBtn) {
          openEditModal(editBtn.getAttribute('data-edit'));
          return;
        }
      });
    }

    // langchange: re-render + relabel
    document.addEventListener('langchange', function () {
      if (!section()) return;
      render();
    });

    // wl-auth event from watchstore.js
    document.addEventListener('wl-auth', function (e) {
      var user = e.detail && e.detail.user;
      onAuth(user || null);
    });

    // wire suggest
    wireTickerSuggest();
  }

  // ---- init ----------------------------------------------------------------
  function init() {
    if (!section()) return; // inert on pages without the section

    // load SD index once (needed for names + signals)
    ensureIndex();

    wireEvents();

    // check if already signed in (WatchStore initialized before us)
    if (window.WatchStore && window.WatchStore.user) {
      var u = window.WatchStore.user();
      if (u) {
        onAuth(u);
      } else {
        showSignedOut();
      }
    } else {
      // watchstore not yet ready; wl-auth event will fire when it is
      showSignedOut();
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

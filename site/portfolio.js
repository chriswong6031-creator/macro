/* portfolio.js — the Position Assessment desk for the watchlist page.

   Owns #pf_section and all DOM within it. Inert on pages that lack the section.
   Auth state arrives via document 'wl-auth' events dispatched by watchstore.js.
   Price/signal data comes from window.SD (stockdata.js, store-aware per market).
   Portfolio CRUD goes through window.WatchStore.portfolio — Supabase when signed in,
   the localStorage book when signed out (same API either way).

   Every row carries the desk's read: signal state, stage of rise, extension, role
   ladder — and opens into a per-name drawer built from the SAME laneRead engine the
   cards use (window.WRI, exported by watchlist_risk.js — never duplicated here).

   Books: rows partition by market (window.MB). Each book's totals stay in its OWN
   currency — there is no cross-currency sum anywhere in this file.

   Factor wiring: after every render, pushes {ticker->dollarValue} weights to
   window.FX.setAutoWeights() — filtered to the MODELED (US-store, USD) subset, so a
   HKD/CNY/CAD value can never enter a USD weight sum (A3 law 3).

   No engine/data writes, no network except WatchStore.portfolio, SD.loadTicker/
   loadIndexes, and ONE idle-deferred ctx fetch. Nothing position-derived is logged. */
(function () {
  'use strict';

  // ---- guard: only active when the section exists --------------------------
  function section() { return document.getElementById('pf_section'); }

  // ---- i18n ----------------------------------------------------------------
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  function isZh() { return lang() === 'zh'; }
  var T = {
    en: {
      emptyHeading: 'No open positions yet.',
      addBtn: '+ Add position',
      colPosition: 'Position',
      colValue: 'Value',
      colSince: 'Since entry',
      colAssess: 'Assessment',
      editBtn: 'Edit position',
      removeBtn: 'Remove',
      closedHeading: 'Closed positions',
      closedCount: function (n) { return n + ' closed'; },
      unavailable: 'Portfolio unavailable right now — your data is safe.',
      modalAddTitle: 'Add position',
      modalEditTitle: 'Edit position',
      tickerLabel: 'Ticker', sharesLabel: 'Shares', entryLabel: 'Entry price',
      dateLabel: 'Entry date', notesLabel: 'Notes', statusLabel: 'Status',
      statusOpen: 'Open', statusClosed: 'Closed', saveBtn: 'Save',
      tickerRequired: 'Ticker is required.',
      saveError: 'Could not save — please try again.',
      notCovered: 'Not in our coverage — price and signal will show —',
      asof: 'as of',
      atCost: 'at cost',
      localCcy: 'local currency',
      positions: function (n) { return n + (n === 1 ? ' position' : ' positions'); },
      book: 'book',
      signinKeep: 'Sign in to keep this book tracked across devices — free.',
      signIn: 'Sign in',
      noEntryRead: 'No entry read tonight',
      notInLibrary: "This name isn't in tonight's library — value shown at cost.",
      dossier: 'Full dossier →',
      terminal: 'Chart in Terminal →',
      lblStage: 'Stage', lblExtension: 'Extension'
    },
    zh: {
      emptyHeading: '暂无开仓持仓。',
      addBtn: '+ 添加持仓',
      colPosition: '持仓',
      colValue: '市值',
      colSince: '入场以来',
      colAssess: '系统评估',
      editBtn: '编辑持仓',
      removeBtn: '移除',
      closedHeading: '已平仓',
      closedCount: function (n) { return n + ' 条已平仓'; },
      unavailable: '暂时无法加载持仓——你的数据安全无虞。',
      modalAddTitle: '添加持仓',
      modalEditTitle: '编辑持仓',
      tickerLabel: '代码', sharesLabel: '股数', entryLabel: '入场价',
      dateLabel: '入场日期', notesLabel: '备注', statusLabel: '状态',
      statusOpen: '开仓', statusClosed: '已平仓', saveBtn: '保存',
      tickerRequired: '代码不能为空。',
      saveError: '保存失败——请重试。',
      notCovered: '不在覆盖范围——价格与信号将显示 —',
      asof: '数据截至',
      atCost: '按成本',
      localCcy: '本币',
      positions: function (n) { return n + ' 笔持仓'; },
      book: '账本',
      signinKeep: '登录即可跨设备保存并追踪——免费。',
      signIn: '登录',
      noEntryRead: '今晚无入场读数',
      notInLibrary: '该名称不在今晚的库中——数值按成本显示。',
      dossier: '完整档案 →',
      terminal: '在终端查看图表 →',
      lblStage: '阶段', lblExtension: '拉伸度'
    }
  };
  function L(k) { return (T[lang()] || T.en)[k]; }
  function te(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>';
  }

  // ---- tiny utils ----------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function num(v) {
    if (v === '' || v == null) return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }
  function group(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

  // ---- state ---------------------------------------------------------------
  var rows = null;          // portfolio rows; null until first load
  var editingId = null;
  var priceCache = {};      // ticker -> {price, asof} | null (uncovered)
  var jsonCache = {};       // ticker -> full per-ticker JSON | null
  var hydrated = false;     // per-ticker fetch pass already kicked off
  var lastListAt = 0;
  var sdIndex = null;       // merged {list, byTicker} across the markets in play
  var ctxMap = null;        // portfolio_ctx tickers map (US stage rows); null until loaded
  var ctxTried = false;
  var prevFocusEl = null;
  var openDrawers = {};     // row id -> true (survives re-render)

  // ---- market/book seam ----------------------------------------------------
  function MB() { return window.MB || null; }
  function marketOf(t) { var m = MB(); return m ? m.marketOf(t) : 'us'; }
  function isModeled(t) { var m = MB(); return m ? m.isModeled(t) : true; }
  function activeBook() { var m = MB(); return m ? m.getBook() : 'all'; }
  function bookMeta(b) { var m = MB(); return m && m.BOOKS[b] ? m.BOOKS[b] : null; }
  function bookOrder() { var m = MB(); return m ? m.BOOK_ORDER : ['us']; }

  // ---- view helpers --------------------------------------------------------
  function showEl(id) { var e = el(id); if (e) e.style.display = ''; }
  function hideEl(id) { var e = el(id); if (e) e.style.display = 'none'; }
  function setText(id, txt) { var e = el(id); if (e) e.textContent = txt; }

  function showError() {
    hideEl('pf_desk'); hideEl('pf_empty'); hideEl('pf_add'); hideEl('pf_closed');
    var errDiv = el('pf_err_inline');
    if (errDiv) { errDiv.textContent = L('unavailable'); errDiv.style.display = 'block'; }
  }

  // ---- index ---------------------------------------------------------------
  // Load the indexes for every market the user actually touches (watchlist ∪ rows),
  // so a .HK / .SS / .TO row resolves its name + signal state like any US name.
  function marketsInPlay() {
    var want = { us: 1 };
    (rows || []).forEach(function (r) { if (r && r.ticker) want[marketOf(r.ticker)] = 1; });
    var wl = (window.WL && window.WL.getBlob) ? window.WL.getBlob() : null;
    if (wl && wl.items) wl.items.forEach(function (it) { want[marketOf(it.t)] = 1; });
    return Object.keys(want);
  }
  function ensureIndex() {
    if (!window.SD || !window.SD.loadIndexes) return Promise.resolve(null);
    return window.SD.loadIndexes(marketsInPlay()).then(function (r) {
      sdIndex = r; return r;
    }).catch(function () { return null; });
  }
  function idxRec(t) {
    return (sdIndex && sdIndex.byTicker && sdIndex.byTicker[t]) || null;
  }
  function tickerName(t) { var r = idxRec(t); return r ? (r.n || '') : ''; }
  function tickerSt(t) { var r = idxRec(t); return r ? (r.st || null) : null; }

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

  // ---- value math (per row; never crosses a currency) ----------------------
  function priceOf(t) {
    var pc = priceCache[t];
    return (pc && isNum(pc.price)) ? pc.price : null;
  }
  /* {value, atCost} for a row — shares×price, else shares×entry ("at cost").
     null value when the row carries no shares (a watch-only holding). */
  function rowValue(r) {
    var sh = num(r.shares), px = priceOf(r.ticker), entry = num(r.entry_price);
    if (sh == null || sh <= 0) return { value: null, atCost: false };
    if (px != null && px > 0) return { value: sh * px, atCost: false };
    if (entry != null && entry > 0) return { value: sh * entry, atCost: true };
    return { value: null, atCost: false };
  }
  function fmtMoney(v, book) {
    var meta = bookMeta(book);
    var ccy = meta ? meta.ccy : '$';
    return (ccy || '') + group(Math.round(v));
  }

  // ---- factor weight wiring (FX-corruption guard) --------------------------
  // Only US-store names (us + crypto + macro — all USD) may enter the weight sum.
  // A .HK / .SS / .TO dollar value in here would silently corrupt every book
  // statistic downstream (betas, ENB, correlations, MCTR). A3 law 3.
  function pushFxWeights() {
    if (!window.FX || !window.FX.setAutoWeights) return;
    var w = {};
    openRows().forEach(function (r) {
      var t = r.ticker;
      if (!t || !isModeled(t)) return;          // <- the guard
      var sh = num(r.shares), px = priceOf(t);
      if (sh != null && sh > 0 && px != null && px > 0) w[t] = sh * px;
    });
    window.FX.setAutoWeights(Object.keys(w).length >= 2 ? w : null);
  }

  // =========================================================================
  //  Assessment cell — Tier-1 budget: 1 pill + at most 2 chips + 1 badge
  // =========================================================================
  var STAGE_WORDS = {
    1: { chipEn: 'Stage 1 · basing',    chipZh: '第1阶段 · 筑底',
         drawEn: 'Basing — stage 1 of 4',    drawZh: '筑底——第1阶段（共4段）' },
    2: { chipEn: 'Stage 2 · rising',    chipZh: '第2阶段 · 上行',
         drawEn: 'Rising — stage 2 of 4',    drawZh: '上行——第2阶段（共4段）' },
    3: { chipEn: 'Stage 3 · topping',   chipZh: '第3阶段 · 筑顶',
         drawEn: 'Topping — stage 3 of 4',   drawZh: '筑顶——第3阶段（共4段）' },
    4: { chipEn: 'Stage 4 · declining', chipZh: '第4阶段 · 下行',
         drawEn: 'Declining — stage 4 of 4', drawZh: '下行——第4阶段（共4段）' }
  };
  function ctxStage(t) {
    if (!ctxMap) return null;
    var e = ctxMap[t];
    var s = e && e.stage;
    if (!s) return null;
    var w = STAGE_WORDS[s.n];
    if (!w) {
      // n outside 1–4: fall back to the verbatim engine label, never an invented word
      if (!s.label) return null;
      return { chipEn: esc(s.label), chipZh: esc(s.label),
               drawEn: esc(s.label), drawZh: esc(s.label), weeks: s.weeks };
    }
    return { chipEn: w.chipEn, chipZh: w.chipZh, drawEn: w.drawEn, drawZh: w.drawZh,
             weeks: s.weeks };
  }

  /* Stretch read. US names carry the precise 4-grade `ext` block; every other market
     carries the universal `ladder.alignment.overextended` bool instead (the engine
     classifies the 4-grade extension for US listings only). */
  function stretchOf(t, j) {
    if (!j) return null;
    if (isModeled(t) && j.ext && j.ext.grade) {
      var g = j.ext.grade;
      if (g === 'parabolic') return { grade: g, hot: true, en: 'Parabolic', zh: '抛物线拉伸' };
      if (g === 'stretched') return { grade: g, hot: false, en: 'Stretched', zh: '过度拉伸' };
      return null;   // intrend / steady -> no chip
    }
    var al = j.ladder && j.ladder.alignment;
    if (al && al.overextended === true) {
      return { grade: 'stretched', hot: false, en: 'Stretched', zh: '过度拉伸' };
    }
    return null;
  }

  /* Extension sentence for the drawer. The number is `tech.pct_vs_200dma` — verified
     the same quantity `ext.ext` carries (engine/extension.py: ext = price/SMA200 − 1,
     emitted ×100), so the two can never disagree; the named field is used. */
  function extensionSentence(grade, pct) {
    if (!isNum(pct)) return null;
    var below = pct < 0, p = Math.abs(Math.round(pct * 10) / 10);
    var lineEn = below ? 'about ' + p + '% below its 200-day line'
                       : 'about ' + p + '% above its 200-day line';
    var lineZh = below ? '低于200日线约' + p + '%' : '高于200日线约' + p + '%';
    if (grade === 'parabolic') {
      return { en: 'Parabolic — extreme extension, ' + lineEn + '. Protect gains.',
               zh: '抛物线拉伸——极端偏离，' + lineZh + '。注意保护利润。' };
    }
    if (grade === 'stretched') {
      return { en: 'Stretched — ran hard, ' + lineEn + '. Entries here have chased before.',
               zh: '过度拉伸——涨势过快，' + lineZh + '。此位追入历史上多为追高。' };
    }
    if (grade === 'steady') {
      return { en: 'Steady — ' + lineEn + '.', zh: '平稳——' + lineZh + '。' };
    }
    return { en: 'In trend — ' + lineEn + ', not stretched.',
             zh: '趋势内——' + lineZh + '，未过度拉伸。' };
  }
  function extGradeOf(t, j) {
    if (isModeled(t) && j && j.ext && j.ext.grade) return j.ext.grade;
    var al = j && j.ladder && j.ladder.alignment;
    if (al && al.overextended === true) return 'stretched';
    return 'intrend';
  }

  function roleOf(t, j) {
    if (!j || !window.WRI || !window.WRI.laneRead || !window.WRI.roleBadge) return null;
    try { return window.WRI.roleBadge(window.WRI.laneRead(j)); } catch (e) { return null; }
  }

  function assessmentHTML(t) {
    var j = jsonCache[t];
    var out = '';
    var st = tickerSt(t);
    if (st && window.SD) {
      out += '<span class="state ' + esc(window.SD.stClass(st)) + '">' +
        esc(window.SD.label(st)) + '</span>';
    }
    var stg = ctxStage(t);
    if (stg) {
      var suffix = isNum(stg.weeks)
        ? { en: ' · ' + Math.round(stg.weeks) + ' wks in', zh: ' · 已' + Math.round(stg.weeks) + '周' }
        : { en: '', zh: '' };
      out += '<span class="wri-chip info">' +
        te(stg.chipEn + suffix.en, stg.chipZh + suffix.zh) + '</span>';
    }
    var str = stretchOf(t, j);
    if (str) {
      out += '<span class="wri-chip' + (str.hot ? ' hot' : '') + '">' +
        te(str.en, str.zh) + '</span>';
    }
    var role = roleOf(t, j);
    if (role) {
      out += '<span class="wri-role wri-role-' + esc(role.kind) + '">' +
        te(esc(role.en), esc(role.zh)) + '</span>';
    }
    return out || '<span class="muted pfx-dash">—</span>';
  }

  // =========================================================================
  //  Drawer
  // =========================================================================
  function lrow(labEn, labZh, stCls, stTok, readEn, readZh) {
    return '<div class="wri-lrow"><span class="ln">' + te(labEn, labZh) + '</span>' +
      (stCls ? '<span class="st ' + stCls + '">' + stTok + '</span>' : '') +
      '<span class="rs">' + te(readEn, readZh) + '</span></div>';
  }
  function terminalHref(t) {
    // verified route (charting-app origin/master terminal/app/terminal/page.tsx reads
    // ?symbol ?? ?sym); same construction the repo already uses in options.html.j2
    return 'https://app.mastermind-x.com/terminal?sym=' + encodeURIComponent(t) + '&from=macro';
  }

  function drawerHTML(r) {
    var t = r.ticker, j = jsonCache[t];
    var body = '';

    if (j === null || j === undefined) {
      // Truly uncovered: absent from its market's store. ONE honest line, no lanes.
      body += '<div class="wri-lrow"><span class="rs">' +
        te(esc(T.en.notInLibrary), esc(T.zh.notInLibrary)) + '</span></div>';
    } else {
      // 1) lead line — the entry read, verbatim (already the plain-word sentence)
      var es = j.entry_signal || {};
      var headEn = es.headline || '', headZh = es.headline_zh || es.headline || '';
      body += headEn
        ? '<div class="pfx-lead">' + te(esc(headEn), esc(headZh)) + '</div>'
        : '<div class="pfx-lead muted">' + te(esc(T.en.noEntryRead), esc(T.zh.noEntryRead)) + '</div>';

      // 2) stage (US only — the engine classifies US listings)
      var stg = ctxStage(t);
      if (stg) {
        var wEn = isNum(stg.weeks) ? ' · ' + Math.round(stg.weeks) + ' wks in' : '';
        var wZh = isNum(stg.weeks) ? ' · 已' + Math.round(stg.weeks) + '周' : '';
        body += lrow(T.en.lblStage, T.zh.lblStage, '', '', stg.drawEn + wEn, stg.drawZh + wZh);
      }

      // 3) extension
      var pct = j.tech && j.tech.pct_vs_200dma;
      var ext = extensionSentence(extGradeOf(t, j), num(pct));
      if (ext) body += lrow(T.en.lblExtension, T.zh.lblExtension, '', '', esc(ext.en), esc(ext.zh));

      // 4) the seven lane rows — the SAME engine the cards use, never duplicated
      if (window.WRI && window.WRI.laneRows) {
        try { body += window.WRI.laneRows(j); } catch (e) {}
      }
      // 5) chains
      if (window.WRI && window.WRI.chainRows) {
        try { body += window.WRI.chainRows(t); } catch (e) {}
      }
      if (j.asof) {
        body += '<div class="asof">' + te('signals as of ' + esc(j.asof),
          '信号截至 ' + esc(j.asof)) + '</div>';
      }
    }

    // 6) footer links + edit
    body += '<div class="pfx-foot">' +
      '<a href="stock.html#' + encodeURIComponent(t) + '">' + te(T.en.dossier, T.zh.dossier) + '</a>' +
      '<a href="' + esc(terminalHref(t)) + '" target="_blank" rel="noopener noreferrer">' +
        te(T.en.terminal, T.zh.terminal) + '</a>' +
      '<button class="wl-btn" type="button" data-edit="' + esc(String(r.id)) + '">' +
        te(T.en.editBtn, T.zh.editBtn) + '</button>' +
      '<button class="wl-btn pfx-rm" type="button" data-rm-pos="' + esc(String(r.id)) + '">' +
        te(T.en.removeBtn, T.zh.removeBtn) + '</button>' +
      '</div>';

    return '<tr class="pfx-drawer" data-drawer="' + esc(String(r.id)) + '"' +
      (openDrawers[r.id] ? '' : ' hidden') + '><td colspan="4">' +
      '<div class="wri-drawer open">' + body + '</div></td></tr>';
  }

  // =========================================================================
  //  Table
  // =========================================================================
  function bookValueTotals(list) {
    // {book -> {value, priced}} over the given rows; per book, never across books
    var out = {};
    list.forEach(function (r) {
      var b = marketOf(r.ticker), v = rowValue(r);
      var e = out[b] || (out[b] = { value: 0, priced: 0, n: 0, atCost: false });
      e.n++;
      if (v.value != null) { e.value += v.value; if (v.atCost) e.atCost = true; else e.priced++; }
    });
    return out;
  }

  function rowHTML(r, totals) {
    var t = r.ticker || '', b = marketOf(t);
    var name = tickerName(t);
    var v = rowValue(r);
    var tot = totals[b];

    // value cell + weight bar (share of THIS book's value; ≥2 priced positions only)
    var valHtml = '—';
    if (v.value != null) {
      valHtml = '<span class="num">' + esc(fmtMoney(v.value, b)) + '</span>';
      if (v.atCost) valHtml += ' <span class="bk-atcost">' + te(T.en.atCost, T.zh.atCost) + '</span>';
      if (b === 'intl') valHtml += ' <span class="bk-atcost">' + te(T.en.localCcy, T.zh.localCcy) + '</span>';
      if (tot && tot.priced >= 2 && tot.value > 0) {
        var w = Math.min(100, v.value / tot.value * 100);
        valHtml += '<span class="wri-rsbar"><i style="width:' + w.toFixed(0) + '%"></i></span>';
      }
    }

    // since entry
    var entryP = num(r.entry_price), cur = priceOf(t);
    var sinceHtml = '—';
    if (entryP != null && entryP !== 0 && cur != null) {
      var pct = (cur - entryP) / entryP * 100;
      sinceHtml = '<span class="num" style="color:' + (pct >= 0 ? 'var(--up)' : 'var(--down)') + '">' +
        (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%</span>';
    }

    var isOpen = !!openDrawers[r.id];
    return '<tr class="pfx-row" data-row="' + esc(String(r.id)) + '" tabindex="0" ' +
      'aria-expanded="' + (isOpen ? 'true' : 'false') + '">' +
      '<td class="pfx-pos" data-th="' + esc(L('colPosition')) + '">' +
        '<a href="stock.html#' + encodeURIComponent(t) + '"><b>' + esc(t) + '</b></a>' +
        (name ? '<span class="pfx-name muted">' + esc(name) + '</span>' : '') + '</td>' +
      '<td class="tabnum pfx-val" data-th="' + esc(L('colValue')) + '">' + valHtml + '</td>' +
      '<td class="tabnum" data-th="' + esc(L('colSince')) + '">' + sinceHtml + '</td>' +
      '<td class="pfx-assess" data-th="' + esc(L('colAssess')) + '">' +
        '<div class="pfx-assess-in">' + assessmentHTML(t) +
        '<span class="pfx-tgl" aria-hidden="true"></span></div></td>' +
      '</tr>' + drawerHTML(r);
  }

  function bookHeadHTML(b, tot) {
    var meta = bookMeta(b);
    if (!meta) return '';
    var valPart = '';
    if (tot && tot.value > 0) {
      valPart = ' · <span class="num">' + esc(fmtMoney(tot.value, b)) + '</span>' +
        (tot.atCost ? ' <span class="bk-atcost">' + te(T.en.atCost, T.zh.atCost) + '</span>' : '');
    }
    return '<tr class="pfx-bookhead"><td colspan="4">' +
      '<span class="bk-glyph">' + esc(meta.glyph) + '</span>' +
      '<b>' + te(esc(meta.en) + ' ' + T.en.book, esc(meta.zh)) + '</b>' + valPart +
      ' · ' + te(T.en.positions(tot ? tot.n : 0), T.zh.positions(tot ? tot.n : 0)) +
      '</td></tr>';
  }

  function renderTable() {
    var tbody = el('pf_rows');
    if (!tbody) return;
    var book = activeBook();
    var open = openRows();
    var shown = book === 'all' ? open : open.filter(function (r) { return marketOf(r.ticker) === book; });
    var totals = bookValueTotals(open);

    var html = '';
    if (book === 'all') {
      // grouped: one subtotal row per market, in the canonical book order
      var byBook = {};
      shown.forEach(function (r) { (byBook[marketOf(r.ticker)] || (byBook[marketOf(r.ticker)] = [])).push(r); });
      bookOrder().forEach(function (b) {
        var list = byBook[b];
        if (!list || !list.length) return;
        // a single-market book needs no group header (it would just repeat the page)
        if (Object.keys(byBook).length > 1) html += bookHeadHTML(b, totals[b]);
        list.forEach(function (r) { html += rowHTML(r, totals); });
      });
    } else {
      html += bookHeadHTML(book, totals[book]);
      shown.forEach(function (r) { html += rowHTML(r, totals); });
    }
    tbody.innerHTML = html;
  }

  // ---- the signed-out "keep this book" line --------------------------------
  function renderLocalNote() {
    var host = el('pf_localnote');
    if (!host) return;
    var isLocal = !!(window.WatchStore && window.WatchStore.portfolio &&
      window.WatchStore.portfolio.isLocal && window.WatchStore.portfolio.isLocal());
    if (!isLocal || !rows || !rows.length) { host.style.display = 'none'; host.innerHTML = ''; return; }
    host.style.display = '';
    host.innerHTML = '<span class="muted">' + te(T.en.signinKeep, T.zh.signinKeep) + '</span> ' +
      '<button class="wl-btn" type="button" id="pf_signin_inline">' +
      te(T.en.signIn, T.zh.signIn) + '</button>';
  }

  // ---- render --------------------------------------------------------------
  function render() {
    if (!section()) return;
    relabelStatic();
    if (rows === null) return;   // not loaded yet: leave the static shell alone

    var open = openRows(), closed = closedRows();
    var addBtn = el('pf_add');

    if (open.length === 0 && closed.length === 0) {
      hideEl('pf_desk'); showEl('pf_empty');
      if (addBtn) addBtn.style.display = 'none';
      hideEl('pf_closed');
    } else {
      hideEl('pf_empty'); showEl('pf_desk');
      if (addBtn) addBtn.style.display = '';
      renderTable();
      var cl = el('pf_closed');
      if (cl) {
        if (closed.length > 0) {
          cl.style.display = '';
          var cn = el('pf_closed_n'); if (cn) cn.textContent = L('closedCount')(closed.length);
          var ctbody = el('pf_closed_rows');
          if (ctbody) ctbody.innerHTML = closed.map(closedRowHTML).join('');
        } else { cl.style.display = 'none'; }
      }
    }

    renderLocalNote();

    // as-of footnote
    var asofEl = el('pf_asof');
    if (asofEl) {
      var asofVal = '';
      Object.keys(priceCache).forEach(function (t) {
        var pc = priceCache[t];
        if (pc && pc.asof && pc.asof > asofVal) asofVal = pc.asof;
      });
      asofEl.textContent = asofVal || '—';
    }

    // books strip + factor weights
    var wl = (window.WL && window.WL.getBlob) ? window.WL.getBlob() : null;
    var watchSyms = wl && wl.items ? wl.items.map(function (it) { return it.t; }) : [];
    if (MB()) MB().refresh(watchSyms, rows, priceOf);
    pushFxWeights();
    publishEarningsFact();

    hydrate();
  }

  function closedRowHTML(r) {
    var t = r.ticker || '';
    var entryP = num(r.entry_price);
    return '<tr>' +
      '<td><a href="stock.html#' + encodeURIComponent(t) + '">' + esc(t) + '</a></td>' +
      '<td>' + esc(tickerName(t)) + '</td>' +
      '<td class="tabnum">' + (r.shares != null ? esc(String(r.shares)) : '—') + '</td>' +
      '<td class="tabnum">' + (entryP != null ? entryP.toFixed(2) : '—') + '</td>' +
      '<td>' + esc(r.entry_date || '—') + '</td>' +
      '<td><button class="wl-btn" data-edit="' + esc(String(r.id)) + '">' +
        esc(L('editBtn')) + '</button></td>' +
      '</tr>';
  }

  // ---- lazy hydration: per-ticker JSON (price + signals) then ctx -----------
  function hydrate() {
    if (hydrated || !rows || !rows.length) return;
    hydrated = true;
    var tickers = [], seen = {};
    rows.forEach(function (r) {
      if (r.ticker && !seen[r.ticker]) { seen[r.ticker] = 1; tickers.push(r.ticker); }
    });
    if (!tickers.length || !window.SD || !window.SD.loadTicker) return;
    Promise.all(tickers.map(function (t) {
      return window.SD.loadTicker(t).then(function (j) {
        jsonCache[t] = j;
        priceCache[t] = (j && j.tech && j.tech.price != null)
          ? { price: j.tech.price, asof: j.asof || '' } : null;
        // feed the hero's condition counts (no extra fetch — this JSON is already here)
        if (j && window.WRI && window.WRI.noteJson) window.WRI.noteJson(t, j);
      }).catch(function () { jsonCache[t] = null; priceCache[t] = null; });
    })).then(function () {
      render();          // one re-render pass with prices + reads filled
      loadCtx();
    });
  }

  /* ctx (US stage rows) — deferred to idle, and only when a modeled position exists.
     Account-gated: a 401 resolves to null and the stage rows simply omit. */
  function loadCtx() {
    if (ctxTried) return;
    var anyModeled = openRows().some(function (r) { return isModeled(r.ticker); });
    if (!anyModeled) return;
    ctxTried = true;
    var go = function () {
      fetch('data/portfolio_ctx.json')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          ctxMap = (j && j.tickers) || null;
          if (ctxMap) render();
        })
        .catch(function () { ctxMap = null; });
    };
    if (window.requestIdleCallback) window.requestIdleCallback(go, { timeout: 3000 });
    else setTimeout(go, 1200);
  }

  // ---- today-strip fact: names reporting this week --------------------------
  function publishEarningsFact() {
    if (!MB() || !MB().setFact) return;
    var n = 0, seen = {};
    openRows().forEach(function (r) {
      var t = r.ticker, j = jsonCache[t];
      if (!t || seen[t] || !j) return;
      seen[t] = 1;
      var d = j.earnings && j.earnings.next_date;
      if (!d) return;
      var m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (!m) return;
      var days = Math.round((Date.UTC(+m[1], +m[2] - 1, +m[3]) - Date.now()) / 86400000);
      if (days >= 0 && days <= 7) n++;
    });
    MB().setFact('earn', n);
  }

  // ---- static label relabeling (bilingual) ---------------------------------
  function relabelStatic() {
    [['pf_th_position', 'colPosition'], ['pf_th_value', 'colValue'],
     ['pf_th_since', 'colSince'], ['pf_th_assess', 'colAssess']].forEach(function (p) {
      var e = el(p[0]); if (e) e.textContent = L(p[1]);
    });
    var addBtn = el('pf_add'); if (addBtn) addBtn.textContent = L('addBtn');
    [['pfm_lbl_ticker', 'tickerLabel'], ['pfm_lbl_shares', 'sharesLabel'],
     ['pfm_lbl_entry', 'entryLabel'], ['pfm_lbl_date', 'dateLabel'],
     ['pfm_lbl_notes', 'notesLabel'], ['pfm_lbl_status', 'statusLabel'],
     ['pfm_save', 'saveBtn']].forEach(function (p) {
      var e = el(p[0]); if (e) e.textContent = L(p[1]);
    });
    var selEl = el('pfm_status');
    if (selEl && selEl.options) {
      if (selEl.options[0]) selEl.options[0].text = L('statusOpen');
      if (selEl.options[1]) selEl.options[1].text = L('statusClosed');
    }
    var emph = el('pf_empty');
    if (emph) { var h = emph.querySelector('p'); if (h) h.textContent = L('emptyHeading'); }
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
  function pfOpenDlg() {
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
    if (prevFocusEl && prevFocusEl.focus) { try { prevFocusEl.focus(); } catch (e) {} }
    prevFocusEl = null;
  }
  function clearModal() {
    ['pfm_ticker', 'pfm_shares', 'pfm_price', 'pfm_date', 'pfm_notes'].forEach(function (id) {
      var e = el(id); if (e) e.value = '';
    });
    var statusRow = el('pfm_status_row'); if (statusRow) statusRow.style.display = 'none';
    var statusSel = el('pfm_status'); if (statusSel) statusSel.value = 'open';
    var errEl = el('pfm_err'); if (errEl) errEl.textContent = '';
    var hintEl = el('pfm_hint'); if (hintEl) hintEl.textContent = '';
    var suggEl = el('pfm_sugg'); if (suggEl) suggEl.innerHTML = '';
  }
  function openAddModal() {
    if (!section()) return;
    editingId = null; clearModal();
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
    editingId = id; clearModal();
    setText('pfm_title', L('modalEditTitle'));
    var te2 = el('pfm_ticker'); if (te2) te2.value = row.ticker || '';
    var se = el('pfm_shares'); if (se) se.value = row.shares != null ? String(row.shares) : '';
    var pe = el('pfm_price'); if (pe) pe.value = row.entry_price != null ? String(row.entry_price) : '';
    var de = el('pfm_date'); if (de) de.value = row.entry_date || '';
    var ne = el('pfm_notes'); if (ne) ne.value = row.notes || '';
    var statusRow = el('pfm_status_row'); if (statusRow) statusRow.style.display = '';
    var statusSel = el('pfm_status');
    if (statusSel) statusSel.value = row.status === 'closed' ? 'closed' : 'open';
    updateTickerHint(row.ticker || '');
    pfOpenDlg();
  }

  // ---- ticker suggest in modal (searches every loaded market index) ---------
  function updateTickerHint(ticker) {
    var hintEl = el('pfm_hint'); if (!hintEl) return;
    if (!ticker || !sdIndex) { hintEl.textContent = ''; hintEl.style.display = 'none'; return; }
    // "not covered" only when the name misses EVERY loaded index
    if (idxRec(ticker.toUpperCase())) { hintEl.textContent = ''; hintEl.style.display = 'none'; }
    else { hintEl.textContent = L('notCovered'); hintEl.style.display = 'block'; }
  }
  function wireTickerSuggest() {
    var input = el('pfm_ticker'); if (!input) return;
    var suggEl = el('pfm_sugg'); if (!suggEl) return;
    var retried = false;

    function paint(v) {
      var vl = v.toLowerCase();
      if (!sdIndex || !sdIndex.list) { suggEl.innerHTML = ''; return; }
      var matches = sdIndex.list.filter(function (x) {
        return x.t.toLowerCase().indexOf(vl) === 0 ||
               (x.n && x.n.toLowerCase().indexOf(vl) >= 0);
      }).slice(0, 8);
      // a suffixed query or a miss: pull the remaining market indexes once, then retry
      if ((!matches.length || v.indexOf('.') >= 0) && !retried && window.SD && window.SD.loadIndexes) {
        retried = true;
        window.SD.loadIndexes(['us', 'cn', 'hk', 'ca', 'intl']).then(function (r) {
          sdIndex = r; paint(v);
        });
      }
      if (!matches.length) { suggEl.innerHTML = ''; suggEl.style.display = 'none'; return; }
      suggEl.innerHTML = matches.map(function (x) {
        var mkt = marketOf(x.t), meta = bookMeta(mkt);
        var glyph = (mkt !== 'us' && meta)
          ? '<span class="bk-glyph pfm-mkt">' + esc(meta.glyph) + '</span>' : '';
        return '<div data-sugg="' + esc(x.t) + '"><b>' + esc(x.t) + '</b> ' + glyph +
          '<small>' + esc(x.n || '') + '</small></div>';
      }).join('');
      suggEl.style.display = 'block';
    }

    input.addEventListener('input', function () {
      var v = input.value.trim();
      updateTickerHint(v.toUpperCase());
      if (!v) { suggEl.innerHTML = ''; suggEl.style.display = 'none'; return; }
      paint(v);
    });
    suggEl.addEventListener('mousedown', function (e) {
      var d = e.target.closest('[data-sugg]'); if (!d) return;
      var t = d.getAttribute('data-sugg');
      input.value = t; updateTickerHint(t);
      suggEl.innerHTML = ''; suggEl.style.display = 'none';
      e.preventDefault();
    });
    input.addEventListener('blur', function () {
      setTimeout(function () {
        if (suggEl) { suggEl.innerHTML = ''; suggEl.style.display = 'none'; }
      }, 200);
    });
  }

  // ---- save / remove -------------------------------------------------------
  function reload() {
    if (!window.WatchStore || !window.WatchStore.portfolio) return;
    hydrated = false;
    window.WatchStore.portfolio.list().then(function (newRows) {
      rows = newRows || [];
      ensureIndex().then(render);
    }).catch(function () { rows = rows || []; render(); });
  }

  function doSave() {
    if (!section()) return;
    var saveBtn = el('pfm_save'); if (!saveBtn) return;
    var errEl = el('pfm_err');
    var ticker = (el('pfm_ticker') ? el('pfm_ticker').value.trim().toUpperCase() : '');
    if (!ticker) { if (errEl) errEl.textContent = L('tickerRequired'); return; }

    var pos = {
      ticker: ticker,
      shares: el('pfm_shares') ? el('pfm_shares').value.trim() : '',
      entry_price: el('pfm_price') ? el('pfm_price').value.trim() : '',
      entry_date: (el('pfm_date') ? el('pfm_date').value.trim() : '') || null,
      notes: el('pfm_notes') ? el('pfm_notes').value.trim() : '',
      status: (el('pfm_status') && el('pfm_status').value === 'closed') ? 'closed' : 'open'
    };
    if (editingId) pos.id = editingId;

    if (errEl) errEl.textContent = '';
    saveBtn.disabled = true;
    if (!window.WatchStore || !window.WatchStore.portfolio) {
      if (errEl) errEl.textContent = L('saveError');
      saveBtn.disabled = false; return;
    }
    window.WatchStore.portfolio.upsert(pos).then(function (result) {
      saveBtn.disabled = false;
      if (!result) { if (errEl) errEl.textContent = L('saveError'); return; }
      pfCloseDlg();
      reload();
    }).catch(function () {
      saveBtn.disabled = false;
      if (errEl) errEl.textContent = L('saveError');
    });
  }

  function doRemove(id) {
    if (!window.WatchStore || !window.WatchStore.portfolio ||
        !window.WatchStore.portfolio.remove) return;
    delete openDrawers[id];
    window.WatchStore.portfolio.remove(id).then(reload).catch(function () {});
  }

  // ---- drawer toggle -------------------------------------------------------
  function toggleDrawer(id) {
    var tr = document.querySelector('tr.pfx-drawer[data-drawer="' + CSS_escape(id) + '"]');
    var row = document.querySelector('tr.pfx-row[data-row="' + CSS_escape(id) + '"]');
    if (!tr) return;
    var willOpen = tr.hasAttribute('hidden');
    if (willOpen) { tr.removeAttribute('hidden'); openDrawers[id] = true; }
    else { tr.setAttribute('hidden', ''); delete openDrawers[id]; }
    if (row) row.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  }
  // attribute-selector safety for ids that came from Supabase (uuid) or 'loc-<n>'
  function CSS_escape(s) { return String(s).replace(/["\\]/g, '\\$&'); }

  // ---- visibility refetch --------------------------------------------------
  document.addEventListener('visibilitychange', function () {
    if (!section() || document.hidden) return;
    var dlg = el('dlg-holding');
    if (dlg && dlg.classList.contains('open')) return;
    var now = Date.now();
    if (now - lastListAt < 60000) return;
    if (!window.WatchStore || !window.WatchStore.user || !window.WatchStore.user()) return;
    lastListAt = now;
    reload();
  });

  // ---- auth event ----------------------------------------------------------
  function onAuth() {
    if (!section()) return;
    if (!window.WatchStore || !window.WatchStore.portfolio) { showError(); return; }
    lastListAt = Date.now();
    hydrated = false;
    window.WatchStore.portfolio.list().then(function (newRows) {
      rows = newRows || [];
      hideEl('pf_err_inline');
      showEl('pf_add');
      ensureIndex().then(render);
    }).catch(function () { showError(); });
  }

  // ---- event wiring --------------------------------------------------------
  function wireEvents() {
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var dlg = el('dlg-holding');
        if (dlg && dlg.classList.contains('open')) pfCloseDlg();
      }
    });
    var dlg = el('dlg-holding');
    if (dlg) dlg.addEventListener('click', function (e) {
      if (e.target && e.target.getAttribute('data-close') !== null) pfCloseDlg();
    });
    var addBtn = el('pf_add'); if (addBtn) addBtn.addEventListener('click', openAddModal);
    var addFirst = el('pf_add_first'); if (addFirst) addFirst.addEventListener('click', openAddModal);
    var saveBtn = el('pfm_save'); if (saveBtn) saveBtn.addEventListener('click', doSave);

    var sec = section();
    if (sec) {
      sec.addEventListener('click', function (e) {
        var tgt = e.target;
        var editBtn = tgt.closest ? tgt.closest('[data-edit]') : null;
        if (editBtn) { openEditModal(editBtn.getAttribute('data-edit')); return; }
        var rmBtn = tgt.closest ? tgt.closest('[data-rm-pos]') : null;
        if (rmBtn) { doRemove(rmBtn.getAttribute('data-rm-pos')); return; }
        if (tgt.closest && tgt.closest('#pf_signin_inline')) {
          if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signin');
          return;
        }
        // a click anywhere on the row (but not on a link/button) toggles the drawer
        if (tgt.closest && (tgt.closest('a') || tgt.closest('button'))) return;
        var row = tgt.closest ? tgt.closest('tr.pfx-row') : null;
        if (row) toggleDrawer(row.getAttribute('data-row'));
      });
      // keyboard: Enter/Space on a focused row toggles its drawer
      sec.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var row = e.target && e.target.closest ? e.target.closest('tr.pfx-row') : null;
        if (!row) return;
        e.preventDefault();
        toggleDrawer(row.getAttribute('data-row'));
      });
    }

    document.addEventListener('langchange', function () { if (section()) render(); });
    document.addEventListener('wl-auth', function () { onAuth(); });
    document.addEventListener('pf-folded', function () { reload(); });
    document.addEventListener('bk-change', function () { if (section() && rows) render(); });
    // the watchlist changed -> book membership may have changed
    document.addEventListener('wl-changed', function () {
      if (section() && rows) {
        var wl = (window.WL && window.WL.getBlob) ? window.WL.getBlob() : null;
        var syms = wl && wl.items ? wl.items.map(function (it) { return it.t; }) : [];
        if (MB()) MB().refresh(syms, rows, priceOf);
      }
    });
    wireTickerSuggest();
  }

  // ---- init ----------------------------------------------------------------
  function init() {
    if (!section()) return;
    wireEvents();
    // The book is real whether or not anyone is signed in: load it immediately.
    // watchstore.js resolves signed-out to the localStorage book behind the same API.
    onAuth();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

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
  // The workspace's holdings table is this file's host — #pf_section is gone with
  // the old IA. Inert on any page that does not carry it.
  function section() { return document.getElementById('ws_sec_hold'); }

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
      privLocal: 'Holdings stay in this browser until you sign in.',
      privAccount: 'Holdings are stored privately in your account.',
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
      privLocal: '持仓保存在本浏览器中，登录后同步。',
      privAccount: '持仓仅保存在你的账户中。',
      noEntryRead: '今晚无入场读数',
      notInLibrary: '该名称不在今晚的库中——数值按成本显示。',
      dossier: '完整档案 →',
      terminal: '在终端查看图表 →',
      // 偏离度, NOT 拉伸度: the existing Stretch lane already owns 拉伸度, and two
      // drawer rows carrying the same zh label with different readings is unreadable.
      // 偏离 is the house word for distance-from-a-norm (偏离200日均线 / 极端偏离).
      lblStage: '阶段', lblExtension: '偏离度'
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
  function bookName(b) { var m = MB(); return m ? m.bookName(b, false) : b; }
  function bookNameZh(b) { var m = MB(); return m ? m.bookName(b, true) : b; }

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
    var keys = Object.keys(w);
    /* W2 seeded `FX.update(keys)` here before announcing, because `FX.setAutoWeights`
       bailed on an empty `LAST` — so a full book with an EMPTY watchlist never reached
       RiskCore. W3 fixed that at the mechanism (factor_exposure.js: the auto path's
       universe is the weight map, never `LAST`), so the seeding call is retired rather
       than left as a second, silent guarantee of the same property. One owner for the
       auto path means the regression test pins the path production actually takes. */
    window.FX.setAutoWeights(keys.length >= 2 ? w : null);
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
    // No trailing "not stretched": the entry-signal headline directly above is a
    // DIFFERENT engine and may legitimately read "Extended — wait for a pullback" on
    // the same card. The grade word already carries the read; two engines measuring
    // different things must not textually contradict each other one line apart.
    return { en: 'In trend — ' + lineEn + '.',
             zh: '趋势内——' + lineZh + '。' };
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

  // =========================================================================
  //  Drawer — the per-name detail, and the ONE place a lane failure is spoken
  // =========================================================================
  function lrow(labEn, labZh, stCls, stTok, readEn, readZh) {
    return '<div class="wri-lrow"><span class="ln">' + te(labEn, labZh) + '</span>' +
      (stCls ? '<span class="st ' + stCls + '">' + stTok + '</span>' : '') +
      '<span class="rs">' + te(readEn, readZh) + '</span></div>';
  }
  function terminalHref(t) {
    // verified route (charting-app terminal/app/terminal/page.tsx reads ?symbol ?? ?sym)
    return 'https://app.mastermind-x.com/terminal?sym=' + encodeURIComponent(t) + '&from=macro';
  }

  /* The drawer is where the 390px demotions live (Day, Since entry, Risk share,
     Sector) AND where the per-name detail appears. Its honesty rule: when a lane the
     drawer would normally show cannot be read, the drawer SAYS SO on its own line —
     it never renders a shorter drawer and lets the reader assume there was nothing to
     say. An absent lane and a quiet lane look identical otherwise, and only one of
     them is information. */
  function drawerBody(r) {
    var t = r.ticker, j = jsonCache[t], out = '';
    var b = marketOf(t), v = rowValue(r);

    // the demoted columns, restated in full
    out += '<div class="drw">';
    out += '<div><span class="k">' + te('Day', '当日') + '</span>' + WS().dayCell() + '</div>';
    var entryP = num(r.entry_price), cur = priceOf(t);
    out += '<div><span class="k">' + te('Since entry', '持有以来') + '</span>' +
      (entryP != null && entryP !== 0 && cur != null
        ? '<span class="fig ' + (cur >= entryP ? 'pos' : 'neg') + '">' +
          ((cur - entryP) / entryP * 100 >= 0 ? '+' : '') +
          ((cur - entryP) / entryP * 100).toFixed(1) + '%</span>'
        : WS().dash('No entry price saved for this position, so there is nothing to measure from.',
                    '这笔持仓没有保存买入价，因此没有基准可比。')) + '</div>';
    var share = RISK_SHARES[t];
    out += '<div><span class="k">' + te('Risk share', '风险占比') + '</span>' +
      (isNum(share)
        ? '<span class="fig">' + Math.round(Math.abs(share) * 100) + '%</span>'
        : WS().dash('Not covered by the risk model, so there is no share to give.',
                    '不在风险模型覆盖范围内，因此没有占比可给。')) + '</div>';
    if (v.value != null) {
      out += '<div><span class="k">' + te('Position value', '仓位市值') + '</span><span class="fig">' +
        esc(fmtMoney(v.value, b)) + '</span>' +
        (v.atCost ? ' <span class="mut">' + te('at cost', '按成本') + '</span>' : '') + '</div>';
    }
    out += '</div>';

    if (j === null || j === undefined) {
      /* Truly uncovered, or not read yet — either way we have no lanes. One honest
         line, never an empty drawer that reads as "all clear". */
      out += '<div class="drw-honest">' + (j === null
        ? te(esc(T.en.notInLibrary), esc(T.zh.notInLibrary))
        : te('Reading this name&rsquo;s detail…', '正在读取该股详情…')) + '</div>';
    } else {
      var es = j.entry_signal || {};
      var headEn = es.headline || '', headZh = es.headline_zh || es.headline || '';
      out += headEn
        ? '<div class="pfx-lead">' + te(esc(headEn), esc(headZh)) + '</div>'
        : '<div class="drw-honest">' + te(esc(T.en.noEntryRead), esc(T.zh.noEntryRead)) + '</div>';

      var stg = ctxStage(t);
      if (stg) {
        var wEn = isNum(stg.weeks) ? ' · ' + Math.round(stg.weeks) + ' wks in' : '';
        var wZh = isNum(stg.weeks) ? ' · 已' + Math.round(stg.weeks) + '周' : '';
        out += lrow(T.en.lblStage, T.zh.lblStage, '', '', stg.drawEn + wEn, stg.drawZh + wZh);
      } else if (isModeled(t) && ctxTried && !ctxMap) {
        // the lane exists but its source did not answer — say it, do not just omit
        out += '<div class="drw-honest">' + te(
          'The stage read for this name is not available right now. Nothing else on this row depends on it.',
          '这只票的阶段判断暂时读不到。本行其余内容不依赖它。') + '</div>';
      }

      var pct = j.tech && j.tech.pct_vs_200dma;
      var ext = extensionSentence(extGradeOf(t, j), num(pct));
      if (ext) out += lrow(T.en.lblExtension, T.zh.lblExtension, '', '', esc(ext.en), esc(ext.zh));

      // the seven lane rows — the SAME engine the workspace uses, never duplicated
      var lanes = '';
      if (window.WRI && window.WRI.laneRows) {
        try { lanes = window.WRI.laneRows(j) || ''; } catch (e) { lanes = ''; }
      }
      if (lanes) out += lanes;
      else out += '<div class="drw-honest">' + te(
        'The per-lane checks for this name did not load. That is a gap in what we can show you, not a clean bill of health.',
        '这只票的各项检查没有加载出来。这是我们能展示的内容缺了一块，不代表它没问题。') + '</div>';

      if (window.WRI && window.WRI.chainRows) {
        try { out += window.WRI.chainRows(t) || ''; } catch (e) {}
      }
      if (j.asof) {
        out += '<div class="asof mut" style="font-size:11px;margin-top:7px">' +
          te('signals as of ' + esc(j.asof), '信号截至 ' + esc(j.asof)) + '</div>';
      }
    }

    out += '<div class="drw-act">' +
      '<a href="stock.html#' + encodeURIComponent(t) + '">' + te(T.en.dossier, T.zh.dossier) + '</a>' +
      '<a href="' + esc(terminalHref(t)) + '" target="_blank" rel="noopener noreferrer">' +
        te(T.en.terminal, T.zh.terminal) + '</a>' +
      '<button class="drw-rm" type="button" data-edit="' + esc(String(r.id)) + '">' +
        te(T.en.editBtn, T.zh.editBtn) + '</button>' +
      '<button class="drw-rm" type="button" data-rm-pos="' + esc(String(r.id)) + '">' +
        te(T.en.removeBtn, T.zh.removeBtn) + '</button></div>';
    return out;
  }

  // =========================================================================
  //  The dense holdings table
  // =========================================================================
  function WS() { return window.WS || {}; }
  var RISK_SHARES = {};    // ticker -> |mctr share| (0..1), published by watchlist_risk.js
  var RISK_COVERED = {};   // ticker -> true when the factor model covers it

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

  var HEAD =
    '<thead><tr>' +
      '<th class="srt" data-sort="sym">' + te('Symbol', '代码') + '<span class="ar">▴</span></th>' +
      '<th class="num srt" data-sort="value">' + te('Value / weight', '市值 / 占比') + '<span class="ar">▴</span></th>' +
      '<th class="num">' + te('Day', '当日') + '</th>' +
      '<th class="num srt" data-sort="since">' + te('Since entry', '持有以来') + '<span class="ar">▴</span></th>' +
      '<th>' + te('Signal', '信号阶段') + '</th>' +
      '<th class="num srt" data-sort="risk">' + te('Risk share', '风险占比') + '<span class="ar">▴</span></th>' +
      '<th>' + te('Attention', '留意') + '</th>' +
      '<th>' + te('Next event', '下一个事件') + '</th>' +
      '<th></th>' +
    '</tr></thead>';

  function holdRowHTML(r, totals) {
    var t = r.ticker || '', b = marketOf(t);
    var v = rowValue(r), tot = totals[b];
    var uncovered = !RISK_COVERED[t];

    var valHtml;
    if (v.value != null) {
      valHtml = '<span class="fig">' + esc(fmtMoney(v.value, b)) + '</span>';
      if (tot && tot.value > 0) {
        valHtml += '<span class="w fig">' + (v.value / tot.value * 100).toFixed(1) + '%' +
          (v.atCost ? ' ' + te('at cost', '按成本') : '') + '</span>';
      }
    } else {
      valHtml = WS().dash('This position has no share count saved, so there is no value to show.',
                          '这笔持仓没有保存股数，因此没有市值可显示。');
    }

    var entryP = num(r.entry_price), cur = priceOf(t), sinceHtml;
    if (entryP != null && entryP !== 0 && cur != null) {
      var pct = (cur - entryP) / entryP * 100;
      sinceHtml = '<span class="fig ' + (pct >= 0 ? 'pos' : 'neg') + '">' +
        (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%</span>';
    } else {
      sinceHtml = WS().dash('No entry price saved for this position, so there is nothing to measure from.',
                            '这笔持仓没有保存买入价，因此没有基准可比。');
    }

    /* Risk share on ONE shared scale: the bar is full at 30% of book risk and the
       printed number is the truth. No per-row rescaling, no fake magnitude. A name
       the model does not cover gets "—" and is left out of the denominator. */
    var share = RISK_SHARES[t];
    var rcHtml;
    if (uncovered || !isNum(share)) {
      rcHtml = WS().dash('Not covered by the risk model, so there is no share to give.',
                         '不在风险模型覆盖范围内，因此没有占比可给。');
    } else {
      var p = Math.round(Math.abs(share) * 100);
      rcHtml = '<span class="rc' + (p >= 13 ? ' is-big' : '') + '"><span class="bar"><span style="width:' +
        Math.min(100, Math.abs(share) * 100 / 30 * 100).toFixed(0) + '%"></span></span>' +
        '<span class="fig">' + p + '%</span></span>';
    }

    var j = jsonCache[t];
    var st = tickerSt(t);
    var sig = WS().stageCell ? WS().stageCell(WS().stageOf(st)) : '';
    var att = attentionFlag(r, j);
    var evt = eventCell(j);

    var isOpen = !!openDrawers[r.id];
    return '<tr class="pfx-row' + (uncovered ? ' is-uncovered' : '') + '" data-t="' + esc(t) +
      '" data-row="' + esc(String(r.id)) + '" tabindex="0" aria-expanded="' + (isOpen ? 'true' : 'false') + '">' +
      '<td class="c-sym"><b>' + esc(t) + '</b><span class="co">' + esc(tickerName(t)) + '</span></td>' +
      '<td class="c-val num">' + valHtml + '</td>' +
      '<td class="c-day num">' + WS().dayCell() + '</td>' +
      '<td class="c-since num">' + sinceHtml + '</td>' +
      '<td class="c-sig">' + sig + '</td>' +
      '<td class="c-rc num">' + rcHtml + '</td>' +
      '<td class="c-att">' + (att ? '<span class="flag ' + att[0] + '">' + te(att[1], att[2]) + '</span>'
                                  : '<span class="dash">—</span>') + '</td>' +
      '<td class="c-evt">' + evt + '</td>' +
      '<td class="c-exp"><button class="exp" type="button" data-row-exp="' + esc(String(r.id)) +
        '" aria-label="' + (isZh() ? '详情' : 'Details') + '"><span class="car">⌄</span></button></td>' +
      '</tr>' +
      (isOpen ? '<tr class="row-drawer" data-drawer="' + esc(String(r.id)) + '"><td colspan="9">' +
        drawerBody(r) + '</td></tr>' : '');
  }

  /* WHICH oracle produced a name's stretch grade — 'ext' | 'alignment' | null.

     `extGradeOf` answers in ONE vocabulary drawn from TWO sources that do not measure
     the same thing. US-store names carry `ext`, whose number is literally
     price/SMA200 − 1, z-scored against the name's own trailing year
     (engine/extension.py) — a distance-above-the-200-day read, always. Every other
     market falls back to `ladder.alignment.overextended`, which is a first-true-wins OR
     of three legs (engine/cycles.py `_overextended`): 3-day or daily StochRSI > 80,
     daily RSI14 > 62, or +30% over the 200-day. Only the third leg is a distance read,
     and it is by far the hardest to trip — a name at RSI 63 sitting 2% above its
     200-day line comes back `true` on the first leg it tests. So `true` here does not
     imply a statement about distance, and most of the time is not one.

     The distinction is load-bearing only where the COPY makes a claim about how the
     read was taken: a line that says "elevated" is honest either way, a line that says
     "measured against its own 200-day path" is honest only for 'ext'. Gate on this,
     not on the grade word, wherever the sentence promises the method. */
  function stretchBasis(t, j) {
    if (isModeled(t) && j && j.ext && j.ext.grade) return 'ext';
    var al = j && j.ladder && j.ladder.alignment;
    if (al && al.overextended === true) return 'alignment';
    return null;
  }

  /* The attention flag on a row is the SAME rule the attention stack sorts by, read
     for one name. Precedence is fixed and stated; there is no score anywhere. */
  function attentionFlag(r, j) {
    var t = r.ticker;
    var share = RISK_SHARES[t];
    var days = eventDays(j);
    if (isNum(share) && Math.abs(share) >= 0.20) return ['f-warn', 'Biggest risk share', '风险占比最大'];
    if (days != null && days >= 0 && days <= 5) return ['f-warn', 'Event window', '关键窗口'];
    /* `extGradeOf` speaks the engine's vocabulary (engine/extension.py GRADES:
       intrend / steady / stretched / parabolic / na) and has never returned anything
       else. This branch shipped comparing it against 'high' / 'extreme' — words no
       extension oracle in this repo produces — so from #5496 until now the flag was
       structurally unreachable and this column simply never said "stretched" about
       anything. The zh word is the one the chip lane already uses (过度拉伸, see
       `stretchOf`), NOT the 偏离过大 this branch was written with: the flag takes
       either oracle (see `stretchBasis` above) and only one of those always measures
       distance, so a 偏离 (deviation) word here would make a claim the alignment path
       cannot carry. One word, one column, and it must be true both ways. */
    var g = extGradeOf(t, j);
    if (g === 'parabolic') return ['f-warn', 'Parabolic', '抛物线拉伸'];
    if (g === 'stretched') return ['f-warn', 'Stretched', '过度拉伸'];
    if (!RISK_COVERED[t] && isModeled(t) === false) return ['f-info', 'Outside risk model', '不在风险模型内'];
    return null;
  }
  function eventDays(j) {
    var d = j && j.earnings && j.earnings.next_date;
    if (!d) return null;
    var m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return Math.round((Date.UTC(+m[1], +m[2] - 1, +m[3]) - Date.now()) / 86400000);
  }
  var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function eventCell(j) {
    var d = j && j.earnings && j.earnings.next_date;
    if (!d) return '<span class="dash">—</span>';
    var m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return '<span class="dash">—</span>';
    var dt = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    var days = eventDays(j);
    // the ZH date deliberately drops .fig — "8月27日" contains WORDS, and mono
    // numerals are for figures, never for words
    return '<span class="evt">' + te('Earnings', '财报') +
      ' <b class="fig l-en">' + MON[dt.getUTCMonth()] + ' ' + dt.getUTCDate() + '</b>' +
      '<b class="l-zh">' + (dt.getUTCMonth() + 1) + '月' + dt.getUTCDate() + '日</b>' +
      (days != null && days >= 0 && days <= 5
        ? ' <span class="soon">' + te('in ' + days + (days === 1 ? ' day' : ' days'), '还有 ' + days + ' 天') + '</span>'
        : '') + '</span>';
  }

  var sortKey = 'value', sortDir = -1;
  function sortRows(list, totals) {
    var d = sortDir;
    return list.slice().sort(function (a, b) {
      var r = 0;
      if (sortKey === 'sym') r = (a.ticker || '').localeCompare(b.ticker || '');
      else if (sortKey === 'risk') r = (RISK_SHARES[a.ticker] || 0) - (RISK_SHARES[b.ticker] || 0);
      else if (sortKey === 'since') r = sincePct(a) - sincePct(b);
      else r = (rowValue(a).value || 0) - (rowValue(b).value || 0);
      return (r || (a.ticker || '').localeCompare(b.ticker || '')) * d;
    });
  }
  function sincePct(r) {
    var e = num(r.entry_price), c = priceOf(r.ticker);
    return (e != null && e !== 0 && c != null) ? (c - e) / e * 100 : -1e9;
  }

  function renderTable() {
    var host = el('tbl_pf');
    if (!host) return;
    var open = openRows();
    var book = activeBook();
    var shown = book === 'all' ? open : open.filter(function (r) { return marketOf(r.ticker) === book; });
    var q = (el('pf_q') && el('pf_q').value || '').trim().toLowerCase();
    if (q) shown = shown.filter(function (r) {
      return (r.ticker || '').toLowerCase().indexOf(q) >= 0 ||
             (tickerName(r.ticker) || '').toLowerCase().indexOf(q) >= 0;
    });
    var totals = bookValueTotals(open);

    if (!open.length) {
      host.innerHTML = '<tbody><tr><td><div class="tbl-empty">' + te(
        'No positions yet. Add your first with the button above, or paste a book on the Portfolio tab.',
        '还没有持仓。用上方的按钮添加第一笔，或在「持仓」页贴入一份账簿。') + '</div></td></tr></tbody>';
    } else if (!shown.length) {
      host.innerHTML = '<tbody><tr><td><div class="tbl-empty">' + te(
        'No positions in this book yet.', '这个市场里还没有持仓。') + '</div></td></tr></tbody>';
    } else {
      host.innerHTML = HEAD + '<tbody>' +
        sortRows(shown, totals).map(function (r) { return holdRowHTML(r, totals); }).join('') + '</tbody>';
    }

    // the disclosure line — ALWAYS rendered, so a persisted book filter can never
    // silently shorten the list (packet §11)
    var scope = el('pf_scope');
    if (scope && WS().scopeLine) scope.innerHTML = WS().scopeLine(shown.length, open.length);
    var rc = el('pf_rowcount');
    if (rc) rc.innerHTML = te(shown.length + (shown.length === 1 ? ' row' : ' rows'), shown.length + ' 行');
  }

  // =========================================================================
  //  BOOK READ — the plain-language sentence the Book Seam is evidence for
  // =========================================================================
  var BOOK = null;   // published by watchlist_risk.js: {bets, cluster, coverage, ...}

  function renderBookRead() {
    var open = openRows();
    var totals = bookValueTotals(open);
    var say = el('ws_book_say'), because = el('ws_book_because'),
        meta = el('ws_book_meta'), stance = el('ws_book_stance'),
        cov = el('ws_book_coverage'), sub = el('ws_book_sub');
    if (!say) return;

    if (open.length < 2) {
      if (meta) meta.innerHTML = '';
      say.innerHTML = te('Add a second position and this reads what your book really is.',
                         '再添加一笔持仓，这里就会读出你的账簿到底是什么。');
      if (because) because.innerHTML = '';
      if (stance) stance.innerHTML = '';
      if (cov) cov.innerHTML = '';
      if (WS().seam) WS().seam(el('ws_seam'), null);
      return;
    }

    // money shares within the DOMINANT book only — we never add two currencies
    var byBook = {};
    open.forEach(function (r) { byBook[marketOf(r.ticker)] = (byBook[marketOf(r.ticker)] || 0) + 1; });
    var lead = Object.keys(byBook).sort(function (a, b) { return byBook[b] - byBook[a]; })[0] || 'us';
    var leadTot = totals[lead] ? totals[lead].value : 0;

    var items = open.filter(function (r) { return marketOf(r.ticker) === lead; })
      .map(function (r) {
        var v = rowValue(r).value;
        return {
          sym: r.ticker,
          money: (leadTot > 0 && v != null) ? v / leadTot * 100 : 100 / byBook[lead],
          risk: RISK_COVERED[r.ticker] && isNum(RISK_SHARES[r.ticker])
                  ? Math.abs(RISK_SHARES[r.ticker]) * 100 : null,
          role: ''
        };
      }).sort(function (a, b) { return b.money - a.money; });

    // the cluster is whatever the risk publisher named; absent one, the top half by money
    var clusterSet = (BOOK && BOOK.cluster) || null;
    items.forEach(function (x, i) {
      x.role = clusterSet ? (clusterSet[x.sym] ? 'cluster' : (BOOK.ballast && BOOK.ballast[x.sym] ? 'ballast' : ''))
                          : (i < Math.ceil(items.length / 2) ? 'cluster' : '');
    });

    var nUncovered = items.filter(function (x) { return x.risk == null; }).length;

    if (meta) {
      var parts = ['<span>' + te(open.length + (open.length === 1 ? ' position' : ' positions'),
                                 open.length + ' 只持仓') + '</span>'];
      if (leadTot > 0) {
        parts.push('<span class="sep">·</span><span class="fig">' + esc(fmtMoney(leadTot, lead)) + '</span>' +
          '<span>' + te('tracked', '在管') + '</span>');
      }
      meta.innerHTML = parts.join('');
    }
    if (sub) sub.innerHTML = (BOOK && BOOK.regime) ? BOOK.regime : '';

    /* "moves like about K bets" is FACTOR OUTPUT — it is printed only when the model
       actually produced it, and it names the MODELED subset rather than the user's
       list size whenever those differ. A book whose model read is missing gets the
       money-only sentence, never a bet count we did not compute. */
    if (BOOK && isNum(BOOK.bets) && BOOK.modeledN >= 2) {
      var n = BOOK.modeledN, all = open.length;
      say.innerHTML = (n === all)
        ? te('These <span class="fig">' + all + '</span> positions move like about <span class="fig">' +
             BOOK.bets + '</span> bets.',
             '<span class="fig">' + all + '</span> 只持仓，实际只相当于大约 <span class="fig">' +
             BOOK.bets + '</span> 个方向。')
        : te('The <span class="fig">' + n + '</span> positions our model covers move like about <span class="fig">' +
             BOOK.bets + '</span> bets.',
             '模型覆盖的这 <span class="fig">' + n + '</span> 只持仓，实际只相当于大约 <span class="fig">' +
             BOOK.bets + '</span> 个方向。');
    } else {
      var topShare = 0, topN = Math.max(1, Math.min(3, Math.ceil(items.length / 4)));
      items.slice(0, topN).forEach(function (x) { topShare += x.money; });
      say.innerHTML = te(
        'Most of this book — <span class="fig">' + Math.round(topShare) + '%</span> of the money — sits in <span class="fig">' +
          topN + '</span> ' + (topN === 1 ? 'position' : 'positions') + '.',
        '这本账簿的大部分 —— <span class="fig">' + Math.round(topShare) + '%</span> 的资金 —— 压在 <span class="fig">' +
          topN + '</span> 只持仓上。');
    }
    if (because) because.innerHTML = (BOOK && BOOK.because) ? BOOK.because : te(
      'The biggest weights are <b>' + esc(items.slice(0, 3).map(function (x) { return x.sym; }).join(' · ')) + '</b>.',
      '权重最大的是 <b>' + esc(items.slice(0, 3).map(function (x) { return x.sym; }).join(' · ')) + '</b>。');

    // Stance vocabulary on portfolio surfaces is DESCRIPTIVE ONLY (DESIGN_NOTES §7b):
    // Watch · Get ready · No action, plus this plain line when the answer is nothing.
    /* Descriptive only (DESIGN_NOTES §7b). "Worth a look" is claimed ONLY when a row
       actually carries Watch or Get ready — a stack of five No-action rows means the
       honest answer is still nothing, and Law 1 is satisfied by saying so. */
    if (stance) {
      var live = attentionStack().some(function (x) { return !!x.stance; });
      stance.innerHTML = live
        ? te('A few names are worth a look today.', '今天有几只票值得看一眼。')
        : te('Nothing here needs a decision today.', '今天没有需要决定的事。');
    }

    /* The caption's two figures come from the SAME distribution the two rails draw:
       the cluster's share of THIS money and of THIS modeled risk. Any other
       denominator produces a sentence that contradicts the bracket directly above it. */
    var moneyAll = 0, riskAll = 0, moneyCl = 0, riskCl = 0, nCl = 0;
    items.forEach(function (x) {
      moneyAll += x.money;
      if (x.risk != null) riskAll += x.risk;
      if (x.role === 'cluster') {
        nCl++; moneyCl += x.money;
        if (x.risk != null) riskCl += x.risk;
      }
    });
    var cap = '';
    if (nCl >= 2 && moneyAll > 0 && riskAll > 0) {
      var mp = Math.round(moneyCl / moneyAll * 100), rp = Math.round(riskCl / riskAll * 100);
      cap = te(
        nCl + ' names hold <b>' + mp + '% of the money</b> and <b>' + rp + '% of the risk</b>. ' +
          'That gap is the difference between how this book is sized and how it actually moves.',
        nCl + ' 只票占了 <b>' + mp + '% 的资金</b>，却占了 <b>' + rp + '% 的风险</b>。' +
          '这个差，就是「你怎么配的」和「它实际怎么动」之间的距离。');
    }
    if (WS().seam) {
      WS().seam(el('ws_seam'), {
        items: items,
        lockedRisk: !items.some(function (x) { return x.risk != null; }),
        cap: cap
      });
    }
    /* Two disclosures, and they must not blur into one. The seam draws ONE currency —
       adding two would be the law this page states in its own toolbar — so when the
       book spans markets the rails describe the LEAD book and the line says which.
       The coverage count is then over exactly the set the rails drew, never over the
       whole book, or the sentence contradicts the shape directly above it. */
    if (cov) {
      var lines = [];
      if (Object.keys(byBook).length > 1) {
        lines.push(te(
          'The two lines above read your <b>' + esc(bookName(lead)) + '</b> book — ' +
            items.length + ' of ' + open.length + ' positions. Each book totals in its own currency, ' +
            'so we never draw two of them on one line.',
          '上面两条读的是你的 <b>' + esc(bookNameZh(lead)) + '</b> 账本 —— ' + open.length +
            ' 只持仓中的 ' + items.length + ' 只。每个市场各自计价，因此我们不会把两个市场画在同一条线上。'));
      }
      if (nUncovered) {
        lines.push(te(
          '<b>' + nUncovered + ' of ' + (lines.length ? 'them' : 'your ' + items.length + ' positions') + ' ' +
            (nUncovered === 1 ? 'sits' : 'sit') + ' outside the risk model.</b> ' +
            (nUncovered === 1 ? 'It is' : 'They are') +
            ' shown on the money line above and in the table below, and left out of every risk figure — never quietly folded in.',
          '<b>其中有 ' + nUncovered + ' 只不在风险模型内。</b>' +
            '它们照常出现在上方的资金分布和下方的表格里，但不计入任何风险数字 —— 不会被悄悄算进去。'));
      }
      cov.innerHTML = lines.length
        ? '<span class="mark"></span><span>' + lines.join(' ') + '</span>' : '';
    }
  }

  // =========================================================================
  //  WHAT NEEDS ATTENTION — a fixed precedence, printed. Never a score.
  // =========================================================================
  /* The order is a RULE, in this order, and the hover on each row names which rule
     put it there:
       1  large risk contribution AND its own checks turned elevated
       2  an event inside its critical window
       3  an elevated check on a position large enough to matter
       4  a major status transition
       5  context — the names holding the book apart from its dominant idea
     At most five rows; the section header discloses "5 of N positions". */
  function attentionStack() {
    var open = openRows();
    if (!open.length) return [];
    var out = [], used = {};
    function push(r, rule, whatEn, whatZh, stance, tipEn, tipZh) {
      if (used[r.ticker] || out.length >= 5) return;
      used[r.ticker] = 1;
      out.push({ sym: r.ticker, rule: rule, en: whatEn, zh: whatZh,
                 stance: stance, tipEn: tipEn, tipZh: tipZh });
    }
    var byRisk = open.slice().sort(function (a, b) {
      return (RISK_SHARES[b.ticker] || 0) - (RISK_SHARES[a.ticker] || 0);
    });

    // rule 1
    byRisk.forEach(function (r) {
      var s = RISK_SHARES[r.ticker];
      if (!isNum(s) || s < 0.18) return;
      /* Elevated = the engine's two caution grades. Rule 1's copy says only "its
         checks turned elevated", which BOTH oracles behind `extGradeOf` can back, so
         this rule takes either one (rule 3 below is the one that cannot). */
      var g = extGradeOf(r.ticker, jsonCache[r.ticker]);
      if (g !== 'stretched' && g !== 'parabolic') return;
      push(r, 1, 'Your largest risk share, and its checks turned elevated.',
           '它占你账簿的风险最大，指标也转为偏高。', 's-watch',
           'Rule 1 — largest share of book risk, and its own checks are elevated. Source: last night&#39;s close.',
           '规则 1 —— 占本账簿风险最大，且其自身指标偏高。来源：昨夜收盘数据。');
    });
    // rule 2
    open.forEach(function (r) {
      var d = eventDays(jsonCache[r.ticker]);
      if (d == null || d < 0 || d > 5) return;
      push(r, 2, 'Reports in ' + d + (d === 1 ? ' day' : ' days') + '.',
           d + ' 天后发财报。', 's-ready',
           'Rule 2 — an event inside its critical window.',
           '规则 2 —— 事件进入关键窗口。');
    });
    // rule 3
    byRisk.forEach(function (r) {
      var j3 = jsonCache[r.ticker];
      var g = extGradeOf(r.ticker, j3);
      if (g !== 'stretched' && g !== 'parabolic') return;
      /* This rule's hover NAMES its method — "measured against its own 200-day path".
         Only the `ext` oracle takes the read that way, so an alignment-sourced grade
         may not raise THIS rule: it would print a sentence about a 200-day distance
         over a number that is not one. Such a name is not silently dropped from the
         desk — rule 1 above still speaks for it in the words both oracles support. */
      if (stretchBasis(r.ticker, j3) !== 'ext') return;
      var s = RISK_SHARES[r.ticker];
      if (!isNum(s) || s < 0.08) return;
      push(r, 3, 'Sitting far above its own trend after a long run up.',
           '在一轮长涨之后，已经远离自己的趋势线。', 's-watch',
           'Rule 3 — an elevated check on a position large enough to matter. Stretch is measured against its own 200-day path.',
           '规则 3 —— 一只体量足够大的持仓出现偏高指标。偏离度以其自身 200 日均线路径为基准。');
    });
    /* Rule 4 takes at most ONE row. Five names that all changed stage this week is a
       true statement and a useless stack — the reader learns nothing from the fifth
       identical sentence. The freshest transition stands for the rest. */
    var fresh = open.filter(function (r) {
      var stg = ctxStage(r.ticker);
      return stg && isNum(stg.weeks) && stg.weeks <= 2 && !used[r.ticker];
    }).sort(function (a, b) { return ctxStage(a.ticker).weeks - ctxStage(b.ticker).weeks; })[0];
    if (fresh) {
      push(fresh, 4, 'Changed status recently, after months in one place.',
           '在长期横盘之后，最近状态发生了变化。', '',
           'Rule 4 — a major status transition. This is the most recent one on your book.',
           '规则 4 —— 重要状态变化。这是你账簿上最近的一次。');
    }
    // rule 5 — context
    if (out.length < 5 && BOOK && BOOK.ballast) {
      var ball = Object.keys(BOOK.ballast).filter(function (t) { return !used[t]; });
      if (ball.length) {
        out.push({ sym: ball.slice(0, 2).join(' · '), rule: 5,
          en: 'The names holding this book apart from its dominant idea.',
          zh: '是这几只把整本账簿和主线拉开了距离。', stance: '',
          tipEn: 'Rule 5 — context. These are the reason the book is not a single position.',
          tipZh: '规则 5 —— 背景信息。正是它们让这本账簿没有变成一笔仓位。' });
      }
    }
    return out;
  }

  var STANCE = { 's-watch': ['Watch', '留意'], 's-ready': ['Get ready', '做好准备'],
                 '': ['No action', '暂不需要动作'] };
  function renderAttention() {
    var host = el('ws_att'); if (!host) return;
    var sec = el('ws_sec_att');
    var stack = attentionStack();
    var open = openRows();
    if (!stack.length) {
      if (sec) sec.style.display = open.length ? '' : 'none';
      host.innerHTML = '<div class="att-row"><span class="att-sym"></span>' +
        '<span class="att-what">' + te(
          'Nothing on this book crossed a line overnight.', '昨夜这本账簿没有出现越线。') + '</span>' +
        '<span class="att-stance">' + te('No action', '暂不需要动作') + '</span><span class="att-chev"></span></div>';
    } else {
      if (sec) sec.style.display = '';
      host.innerHTML = stack.map(function (x) {
        var s = STANCE[x.stance] || STANCE[''];
        return '<div class="att-row" data-t="' + esc(x.sym) + '" data-tip-en="' + esc(x.tipEn) +
          '" data-tip-zh="' + esc(x.tipZh) + '">' +
          '<span class="att-sym">' + esc(x.sym) + '</span>' +
          '<span class="att-what">' + te(esc(x.en), esc(x.zh)) + '</span>' +
          '<span class="att-stance ' + x.stance + '">' + te(s[0], s[1]) + '</span>' +
          '<span class="att-chev">›</span></div>';
      }).join('');
    }
    var scope = el('ws_att_scope');
    if (scope) {
      scope.innerHTML = te(stack.length + ' of ' + open.length + ' positions',
                           open.length + ' 只中的 ' + stack.length + ' 只');
    }
  }

  // ---- render --------------------------------------------------------------
  /* The workspace owns the page STATE; this file owns the signed-in composition of it.
     An anonymous visitor's book read and holdings table are drawn by watchlist.js from
     what they pasted, so painting here as soon as `rows` resolves would overwrite that
     read with an empty signed-in shell — which is exactly what it did: the anonymous
     analysis appeared for one frame and was then replaced by "No positions yet". */
  function wsState() {
    return document.documentElement.getAttribute('data-ws-state') || 'signed';
  }
  function render() {
    if (!section()) return;
    if (rows === null) return;   // not loaded yet: leave the static shell alone
    if (wsState().indexOf('anon') === 0) return;

    renderTable();
    renderBookRead();
    renderAttention();

    // books strip + factor weights
    var wl = (window.WL && window.WL.getBlob) ? window.WL.getBlob() : null;
    var watchSyms = wl && wl.items ? wl.items.map(function (it) { return it.t; }) : [];
    if (MB()) MB().refresh(watchSyms, rows, priceOf);
    pushFxWeights();
    publishEarningsFact();

    hydrate();
  }

  /* Progressive hydration through SD's bounded-concurrency batcher. Each name repaints
     its OWN row as it lands, so a 100-position book never blocks first paint and ONE
     failed ticker degrades exactly one row. */
  function hydrate() {
    if (hydrated || !rows || !rows.length) return;
    hydrated = true;
    var tickers = [], seen = {};
    rows.forEach(function (r) {
      if (r.ticker && !seen[r.ticker]) { seen[r.ticker] = 1; tickers.push(r.ticker); }
    });
    if (!tickers.length || !window.SD || !window.SD.loadTickers) return;
    window.SD.loadTickers(tickers, function (t, j) {
      jsonCache[t] = j;
      priceCache[t] = (j && j.tech && j.tech.price != null)
        ? { price: j.tech.price, asof: j.asof || '' } : null;
      if (j && window.WRI && window.WRI.noteJson) { try { window.WRI.noteJson(t, j); } catch (e) {} }
      repaintRow(t);
    }).then(function () {
      render();          // one settled pass with prices + reads filled
      loadCtx();
    });
  }

  var pending = {}, rafOn = false;
  function repaintRow(t) {
    pending[t] = 1;
    if (rafOn) return;
    rafOn = true;
    var run = function () {
      rafOn = false;
      var todo = Object.keys(pending); pending = {};
      var open = openRows(), totals = bookValueTotals(open);
      todo.forEach(function (tk) {
        var row = document.querySelector('#tbl_pf tr[data-t="' + CSS_escape(tk) + '"]');
        if (!row) return;
        var r = null;
        for (var i = 0; i < open.length; i++) if (open[i].ticker === tk) { r = open[i]; break; }
        if (!r) return;
        var frag = document.createElement('tbody');
        frag.innerHTML = holdRowHTML(r, totals);
        var drawer = row.nextElementSibling;
        if (drawer && drawer.classList.contains('row-drawer')) drawer.remove();
        var parent = row.parentNode, anchor = row.nextSibling;
        parent.removeChild(row);
        while (frag.firstElementChild) parent.insertBefore(frag.firstElementChild, anchor);
      });
    };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
    else setTimeout(run, 16);
  }

  /* ctx (US stage rows) — deferred to idle, and only when a modeled position exists.
     Account-gated: a 401 resolves to null and the stage rows simply omit (the drawer
     says so rather than rendering a shorter, quieter drawer). */
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
          render();
        })
        .catch(function () { ctxMap = null; render(); });
    };
    if (window.requestIdleCallback) window.requestIdleCallback(go, { timeout: 3000 });
    else setTimeout(go, 1200);
  }

  // ---- fact: names reporting this week --------------------------------------
  function publishEarningsFact() {
    if (!MB() || !MB().setFact) return;
    var n = 0, seen = {};
    openRows().forEach(function (r) {
      var t = r.ticker, j = jsonCache[t];
      if (!t || seen[t] || !j) return;
      seen[t] = 1;
      var d = eventDays(j);
      if (d != null && d >= 0 && d <= 7) n++;
    });
    MB().setFact('earn', n);
  }

  /* The risk publisher's landing pad (watchlist_risk.js computes, this file composes).
     Everything here is DISPLAY of a number the model produced — nothing is derived,
     re-scaled or re-ranked on the way in. */
  function setBookRisk(payload) {
    BOOK = payload || null;
    RISK_SHARES = (payload && payload.shares) || {};
    RISK_COVERED = (payload && payload.covered) || {};
    if (section() && rows && wsState().indexOf('anon') !== 0) {
      renderTable(); renderBookRead(); renderAttention();
    }
  }

  function relabelStatic() { /* every label on the workspace is a dual-emit span now */ }

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
    if (openDrawers[id]) delete openDrawers[id]; else openDrawers[id] = true;
    var row = document.querySelector('#tbl_pf tr.pfx-row[data-row="' + CSS_escape(id) + '"]');
    if (row) repaintRow(row.getAttribute('data-t'));
    else renderTable();
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

  /* The workspace seam. watchlist.js owns the page's render pass and calls in here
     for the Portfolio mode; watchlist_risk.js publishes the model read through
     setBookRisk. Nothing outside this file touches `rows`. */
  window.PF = {
    render: render,
    count: function () { return openRows().length; },
    repaintRow: repaintRow,
    setBookRisk: setBookRisk
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

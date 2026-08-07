/* market_books.js — market partitioning for the Watchlist / Portfolio Command Center.

   One page, partitioned into per-market BOOKS (US · CN · HK · CA · Crypto · Intl ·
   Macro). A book is a VIEW derived from the symbol by a pure `marketOf()` that mirrors
   the Terminal's suffix rules exactly (PSI masterplan §20 / A3 law 1) — no schema
   change, no market column, no per-market lists, so the one-store sync law is untouched
   and the Terminal keeps working unmodified.

   Owns:
     • marketOf(sym)  — the ONE derivation (vocabulary: us|cn|hk|ca|crypto|intl|macro)
     • storeOf(sym)   — suffix -> per-market data store dir (stockdata.js consumes this)
     • isModeled(sym) — FX-corruption guard: only US-store names (us+crypto+macro, all
                        USD) may enter a factor/risk weight sum. An HKD/CNY/CAD dollar
                        value must NEVER be added to a USD book total (A3 law 3).
     • per-book aggregation that NEVER sums across currencies (A3 law 2)
     • the books strip (#bk_strip), the today strip (#tod_strip), active-book state
       (localStorage `mdash.book.v1`) and the `bk-change` document event.

   Pure functions are exported under node for the unit tests (typeof module guard,
   the risk_core.js / watchlist_risk.js idiom). Load order: this file BEFORE
   stockdata.js and its consumers — they read the router off `window.MB`. */
(function () {
  'use strict';

  // =========================================================================
  //  Market derivation — the ONE function (mirror of terminal/lib/markets.ts)
  // =========================================================================
  function marketOf(sym) {
    var s = String(sym || '').toUpperCase();
    if (!s) return 'us';
    if (s === 'DX-Y.NYB') return 'macro';
    if (/^\^/.test(s) || /=F$/.test(s) || /=X$/.test(s)) return 'macro';
    if (/-USDT?$/.test(s)) return 'crypto';
    var m = s.match(/\.([A-Z]{1,3})$/);
    if (m) {
      var suf = m[1];
      if (suf === 'SS' || suf === 'SZ' || suf === 'BJ') return 'cn';
      if (suf === 'HK') return 'hk';
      if (suf === 'TO' || suf === 'V' || suf === 'NE') return 'ca';
      return 'intl';
    }
    return 'us';
  }

  // ---- store routing (mirrors mm_brain.js chartStore, *stockdata edition) --
  var STORE = {
    us: 'stockdata', crypto: 'stockdata', macro: 'stockdata',
    cn: 'chinastockdata', hk: 'hkstockdata', ca: 'canadastockdata',
    intl: 'intlstockdata'
  };
  function storeOf(sym) { return STORE[marketOf(sym)] || 'stockdata'; }

  // The 9-factor model (factor_betas.json) carries zero suffixed tickers, and every
  // non-US store prices in its own currency. So book math — factor weights, ENB,
  // correlations, MCTR — admits ONLY US-store names. This is the FX-corruption guard:
  // it is a MEMBERSHIP test, not a coverage test (a US name absent from factor_betas
  // still fails downstream on its own, as it does today).
  function isModeled(sym) { return storeOf(sym) === 'stockdata'; }
  function modeledOnly(list) {
    var out = [];
    (list || []).forEach(function (t) { if (t && isModeled(t)) out.push(t); });
    return out;
  }
  // filter a {ticker -> value} weight map to the modeled subset (same guard, map form)
  function modeledWeights(wmap) {
    var out = {};
    Object.keys(wmap || {}).forEach(function (t) { if (isModeled(t)) out[t] = wmap[t]; });
    return out;
  }

  // =========================================================================
  //  Book metadata
  // =========================================================================
  var BOOK_ORDER = ['us', 'crypto', 'cn', 'hk', 'ca', 'intl', 'macro'];
  var BOOKS = {
    us:     { glyph: 'US', en: 'US stocks',   zh: '美股', ccy: '$',   modeled: true },
    crypto: { glyph: 'CR', en: 'Crypto',      zh: '加密', ccy: '$',   modeled: true },
    cn:     { glyph: 'CN', en: 'China A-shares', zh: 'A股', ccy: '¥', modeled: false },
    hk:     { glyph: 'HK', en: 'Hong Kong',   zh: '港股', ccy: 'HK$', modeled: false },
    ca:     { glyph: 'CA', en: 'Canada',      zh: '加股', ccy: 'C$',  modeled: false },
    intl:   { glyph: 'IN', en: 'International', zh: '国际', ccy: '',  modeled: false },
    macro:  { glyph: 'MX', en: 'Indexes & commodities', zh: '指数与商品', ccy: '$', modeled: true }
  };

  // =========================================================================
  //  Aggregation — per book, in its OWN currency. NEVER a cross-book total.
  // =========================================================================
  function num(v) {
    if (v === '' || v == null) return null;
    var n = Number(v);
    return (typeof n === 'number' && isFinite(n)) ? n : null;
  }

  /* rows   : [{ticker, shares, entry_price, status}]  (open rows only are counted)
     priceOf: fn(ticker) -> last close number, or null/undefined when unresolved
     returns: { <book>: {book, n, value, priced, atCost, ccy} }  — one entry per book
              that holds ≥1 open position. `value` is ONLY ever compared/printed inside
              its own book; there is deliberately no cross-book sum in the return. */
  function aggregate(rows, priceOf) {
    var out = {};
    (rows || []).forEach(function (r) {
      if (!r || !r.ticker || r.status === 'closed') return;
      var bk = marketOf(r.ticker);
      var e = out[bk] || (out[bk] = {
        book: bk, n: 0, value: 0, priced: 0, atCost: false, ccy: BOOKS[bk].ccy
      });
      e.n++;
      var sh = num(r.shares);
      var px = priceOf ? num(priceOf(r.ticker)) : null;
      var entry = num(r.entry_price);
      if (sh != null && sh > 0 && px != null && px > 0) { e.value += sh * px; e.priced++; }
      else if (sh != null && sh > 0 && entry != null && entry > 0) { e.value += sh * entry; e.atCost = true; }
    });
    return out;
  }

  /* The full render model for the strip.
       watchSyms : watchlist symbols   rows: portfolio rows   priceOf: price resolver
     Members of a book = watchlist names ∪ OPEN positions in that market. */
  function buildModel(watchSyms, rows, priceOf) {
    var members = {};   // book -> {sym: 1}
    function addName(t) {
      if (!t) return;
      var bk = marketOf(t);
      (members[bk] || (members[bk] = {}))[t] = 1;
    }
    (watchSyms || []).forEach(addName);
    (rows || []).forEach(function (r) { if (r && r.status !== 'closed') addName(r.ticker); });

    var agg = aggregate(rows, priceOf);
    var present = BOOK_ORDER.filter(function (b) {
      return members[b] && Object.keys(members[b]).length > 0;
    });
    var allNames = {};
    Object.keys(members).forEach(function (b) {
      Object.keys(members[b]).forEach(function (t) { allNames[t] = 1; });
    });
    return {
      present: present,
      nAll: Object.keys(allNames).length,
      members: members,
      agg: agg,
      // the strip is a partition device: pointless with a single market present
      show: present.length > 1
    };
  }

  // =========================================================================
  //  Formatting
  // =========================================================================
  function group(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  function fmtValue(v, ccy) {
    var s = group(Math.round(v));
    return ccy ? ccy + s : s;
  }

  // =========================================================================
  //  i18n helpers (dual-span so a language flip needs no re-render)
  // =========================================================================
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function te(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>';
  }
  function bookName(b, zh) { var m = BOOKS[b]; return m ? (zh ? m.zh : m.en) : b; }

  // =========================================================================
  //  Active-book state
  // =========================================================================
  var BOOK_KEY = 'mdash.book.v1';
  var active = 'all';
  function readActive() {
    try {
      var v = localStorage.getItem(BOOK_KEY);
      if (v && (v === 'all' || BOOKS[v])) return v;
    } catch (e) {}
    return 'all';
  }
  function writeActive(b) { try { localStorage.setItem(BOOK_KEY, b); } catch (e) {} }
  function getBook() { return active; }
  function setBook(b, opts) {
    if (b !== 'all' && !BOOKS[b]) return;
    if (b === active) return;
    active = b;
    writeActive(b);
    paintStrip();
    if (!(opts && opts.silent) && typeof document !== 'undefined') {
      document.dispatchEvent(new CustomEvent('bk-change', { detail: { book: b } }));
    }
  }
  // does a symbol belong to the active view?
  function inActive(sym) { return active === 'all' || marketOf(sym) === active; }

  // =========================================================================
  //  Books strip (#bk_strip)
  // =========================================================================
  var MODEL = { present: [], nAll: 0, members: {}, agg: {}, show: false };

  function plateHTML(b) {
    var meta = BOOKS[b];
    var a = MODEL.agg[b];
    var nNames = MODEL.members[b] ? Object.keys(MODEL.members[b]).length : 0;
    var line1, line2;
    if (a && a.n > 0) {
      // ≥1 open position -> native-currency total for THIS book only
      var val = fmtValue(a.value, meta.ccy);
      line1 = '<span class="bk-line1 num">' + esc(val) + '</span>';
      var tags = '';
      if (a.atCost) tags += ' <span class="bk-atcost">' + te('at cost', '按成本') + '</span>';
      if (!meta.ccy) tags += ' <span class="bk-atcost">' + te('local currency', '本币') + '</span>';
      line1 += tags;
      line2 = '<span class="bk-line2">' + te(
        a.n + (a.n === 1 ? ' position' : ' positions'), a.n + ' 笔持仓') + '</span>';
    } else {
      // watchlist names only
      line1 = '<span class="bk-line1">' + te(esc(meta.en), esc(meta.zh)) + '</span>';
      line2 = '<span class="bk-line2 num">' + te(
        nNames + (nNames === 1 ? ' name' : ' names'), nNames + ' 只') + '</span>';
    }
    return '<button class="bk-plate" role="tab" type="button" aria-selected="' +
      (active === b ? 'true' : 'false') + '" data-bk="' + esc(b) + '">' +
      '<span class="bk-glyph">' + esc(meta.glyph) + '</span>' + line1 + line2 + '</button>';
  }

  function paintStrip() {
    if (typeof document === 'undefined') return;
    var host = document.getElementById('bk_strip');
    if (!host) return;
    if (!MODEL.show) { host.style.display = 'none'; host.innerHTML = ''; return; }
    host.style.display = '';
    var html = '<button class="bk-plate" role="tab" type="button" aria-selected="' +
      (active === 'all' ? 'true' : 'false') + '" data-bk="all">' +
      '<span class="bk-glyph">ALL</span>' +
      '<span class="bk-line1">' + te('All books', '全部账本') + '</span>' +
      '<span class="bk-line2 num">' + te(
        MODEL.nAll + (MODEL.nAll === 1 ? ' name' : ' names'), MODEL.nAll + ' 只') + '</span></button>';
    MODEL.present.forEach(function (b) { html += plateHTML(b); });
    host.innerHTML = '<div class="bk-strip wri" role="tablist" aria-label="' +
      (isZh() ? '账本' : 'Books') + '">' + html + '</div>';
  }
  function isZh() {
    return typeof document !== 'undefined' &&
      document.documentElement.getAttribute('data-lang') === 'zh';
  }

  /* Recompute + repaint. Callers: watchlist.js (list changed), portfolio.js (rows or
     prices changed). Cheap and idempotent — safe to call on every render. */
  function refresh(watchSyms, rows, priceOf) {
    MODEL = buildModel(watchSyms, rows, priceOf);
    // an active book that no longer has members falls back to All (never a dead view)
    if (active !== 'all' && MODEL.present.indexOf(active) < 0) {
      active = 'all'; writeActive('all');
    }
    paintStrip();
    paintToday();
  }

  // =========================================================================
  //  Today strip (#tod_strip) — one quiet line of fact chips
  // =========================================================================
  var FACTS = { earn: 0, changed: 0 };
  function setFact(k, v) {
    if (FACTS[k] === v) return;
    FACTS[k] = v;
    paintToday();
  }

  function paintToday() {
    if (typeof document === 'undefined') return;
    var host = document.getElementById('tod_strip');
    if (!host) return;
    var chips = [];
    if (FACTS.earn > 0) {
      chips.push('<button class="tod-chip" type="button" data-jump="pf_section">' +
        '<span class="dot"></span>' + te(
          FACTS.earn + (FACTS.earn === 1 ? ' name reports this week' : ' names report this week'),
          '本周 ' + FACTS.earn + ' 家发布财报') + '</button>');
    }
    if (FACTS.changed > 0) {
      chips.push('<button class="tod-chip" type="button" data-jump="wl_list">' +
        '<span class="dot"></span>' + te(
          FACTS.changed + (FACTS.changed === 1 ? ' signal changed since your last visit'
                                               : ' signals changed since your last visit'),
          '自上次访问 ' + FACTS.changed + ' 个信号变化') + '</button>');
    }
    if (!chips.length) { host.style.display = 'none'; host.innerHTML = ''; return; }
    host.style.display = '';
    host.innerHTML = '<div class="tod-strip wri">' + chips.join('') + '</div>';
  }

  // ---- "changed since your last visit" snapshot ---------------------------
  var SEEN_KEY = 'mdash.wl.seen.v1';
  /* stMap = {ticker: signalState} over the FULL set (never the filtered view).
     Counts only names present in BOTH snapshots whose state moved — a newly added
     name is not a "change". The new snapshot is written AFTER the diff, each load. */
  function seenDiff(stMap) {
    var prev = null;
    try { prev = JSON.parse(localStorage.getItem(SEEN_KEY) || 'null'); } catch (e) {}
    var n = 0;
    if (prev && typeof prev === 'object') {
      Object.keys(stMap || {}).forEach(function (t) {
        if (prev[t] != null && stMap[t] != null && prev[t] !== stMap[t]) n++;
      });
    }
    try { localStorage.setItem(SEEN_KEY, JSON.stringify(stMap || {})); } catch (e) {}
    return n;
  }

  // =========================================================================
  //  Wiring
  // =========================================================================
  function prefersReduced() {
    return typeof window !== 'undefined' && window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function wire() {
    document.addEventListener('click', function (e) {
      var plate = e.target && e.target.closest ? e.target.closest('.bk-plate[data-bk]') : null;
      if (plate) { setBook(plate.getAttribute('data-bk')); return; }
      var jump = e.target && e.target.closest ? e.target.closest('.tod-chip[data-jump]') : null;
      if (jump) {
        var el = document.getElementById(jump.getAttribute('data-jump'));
        if (!el) return;
        el.scrollIntoView({ behavior: prefersReduced() ? 'auto' : 'smooth', block: 'start' });
        if (prefersReduced()) return;
        el.classList.remove('bk-flash');
        void el.offsetWidth;              // restart the pulse if it is already running
        el.classList.add('bk-flash');
        setTimeout(function () { el.classList.remove('bk-flash'); }, 1300);
      }
    });
    // language flip: the plates are dual-span, but the aria-label + the "N names"
    // pluralisation live outside them, so a repaint keeps everything coherent.
    document.addEventListener('langchange', paintStrip);
  }

  if (typeof document !== 'undefined') {
    active = readActive();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { wire(); paintStrip(); });
    } else { wire(); paintStrip(); }
  }

  // ---- public seam --------------------------------------------------------
  var API = {
    marketOf: marketOf, storeOf: storeOf,
    isModeled: isModeled, modeledOnly: modeledOnly, modeledWeights: modeledWeights,
    BOOKS: BOOKS, BOOK_ORDER: BOOK_ORDER,
    aggregate: aggregate, buildModel: buildModel,
    fmtValue: fmtValue, bookName: bookName,
    getBook: getBook, setBook: setBook, inActive: inActive,
    presentBooks: function () { return MODEL.present.slice(); },
    refresh: refresh, setFact: setFact, seenDiff: seenDiff
  };
  if (typeof window !== 'undefined') window.MB = API;

  // Node-test surface: the pure derivation / aggregation core, DOM-free.
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
})();

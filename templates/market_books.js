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

  /* W2: the strip is the SECOND LINE OF THE HOLDINGS TOOLBAR, not a section of its
     own (DESIGN_NOTES §7d — a filter placed below the thing it filters is a usability
     defect). The chips filter the HOLDINGS TABLE VIEW only; the book read, the
     attention stack and the Risk Center always describe the WHOLE portfolio, and the
     label's hover is where that rule is stated. The never-mix-currencies law is the
     strip's trailing subline. A book with no positions renders DISABLED with an
     em dash — visible, and honest about being empty. */
  function chipHTML(b) {
    var meta = BOOKS[b];
    var a = MODEL.agg[b];
    var nNames = MODEL.members[b] ? Object.keys(MODEL.members[b]).length : 0;
    var n = (a && a.n > 0) ? a.n : nNames;
    return '<button class="bookchip" type="button" aria-pressed="' +
      (active === b ? 'true' : 'false') + '" data-bk="' + esc(b) + '">' +
      te(esc(meta.en), esc(meta.zh)) + '<span class="n">' + (n > 0 ? n : '—') + '</span></button>';
  }

  function paintStrip() {
    if (typeof document === 'undefined') return;
    var host = document.getElementById('bk_strip');
    if (!host) return;
    // one market (or none) means the chips would be a control with a single option —
    // the disclosure line already says "all N · all books", so the strip stays away
    if (!MODEL.show) { host.style.display = 'none'; host.innerHTML = ''; return; }
    host.style.display = '';
    var chips = '<button class="bookchip" type="button" aria-pressed="' +
      (active === 'all' ? 'true' : 'false') + '" data-bk="all">' +
      te('All', '全部') + '<span class="n">' + MODEL.nAll + '</span></button>';
    MODEL.present.forEach(function (b) { chips += chipHTML(b); });
    // every book we know about but the user holds nothing in — disabled, never hidden
    BOOK_ORDER.forEach(function (b) {
      if (MODEL.present.indexOf(b) >= 0) return;
      chips += '<button class="bookchip" type="button" disabled data-bk="' + esc(b) + '">' +
        te(esc(BOOKS[b].en), esc(BOOKS[b].zh)) + '<span class="n">—</span></button>';
    });
    host.innerHTML =
      '<span class="books-lbl"' +
        ' data-tip-en="Views of the same portfolio — never separate portfolios. Picking a book filters this table only; the read above, what needs attention, and the risk center always describe every position."' +
        ' data-tip-zh="同一个组合的不同视角 —— 不是另外几个组合。选择某个市场只筛选这张表；上方的解读、「需要留意」和「风险中心」始终描述全部持仓。">' +
        te('Books', '分市场') + '</span>' +
      '<div class="books-strip" role="group" aria-label="' + (isZh() ? '分市场' : 'Books') + '">' +
        chips + '</div>' +
      '<span class="books-law">' + te(
        'Each book totals in its own currency. We never add two currencies into one number.',
        '每个市场各自计价。我们绝不会把两种货币加成一个数字。') + '</span>';
  }
  function isZh() {
    return typeof document !== 'undefined' &&
      document.documentElement.getAttribute('data-lang') === 'zh';
  }

  /* Recompute + repaint. Callers: watchlist.js (list changed), portfolio.js (rows or
     prices changed). Cheap and idempotent — safe to call on every render. */
  function refresh(watchSyms, rows, priceOf) {
    MODEL = buildModel(watchSyms, rows, priceOf);
    /* An active book that no longer has members falls back to All (never a dead view).
       An EMPTY model is not that case: on first paint the positions have not loaded
       yet, so every book looks absent and this reset silently discarded the visitor's
       persisted choice — and PERSISTED the discard, so it never came back. "We don't
       know yet" and "that book is gone" have to be different answers. */
    if (active !== 'all' && MODEL.nAll > 0 && MODEL.present.indexOf(active) < 0) {
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
    return Object.keys(seenDiffRows(stMap)).length;
  }
  /* Same diff, per name: {ticker: {from, to}}. W2's Δ-since-visit column needs to know
     WHICH names moved, not just how many, and the header count and the column ink have
     to come from the SAME computation or the page contradicts itself ("4 changed" over
     three marked rows). The snapshot is still written exactly once, AFTER the diff, so
     the answer stays "since the last time you looked" rather than "since the last
     render" — which is also why the count call must not run this twice per load. */
  function seenDiffRows(stMap) {
    var prev = null;
    try { prev = JSON.parse(localStorage.getItem(SEEN_KEY) || 'null'); } catch (e) {}
    var out = {};
    if (prev && typeof prev === 'object') {
      Object.keys(stMap || {}).forEach(function (t) {
        // a name that was not on the list last visit has no "since your last visit"
        // story, so it is not a change — it is simply new, and stays blank
        if (prev[t] != null && stMap[t] != null && prev[t] !== stMap[t]) {
          out[t] = { from: prev[t], to: stMap[t] };
        }
      });
    }
    try { localStorage.setItem(SEEN_KEY, JSON.stringify(stMap || {})); } catch (e) {}
    return out;
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
      var plate = e.target && e.target.closest ? e.target.closest('.bookchip[data-bk]:not([disabled])') : null;
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
    refresh: refresh, setFact: setFact, seenDiff: seenDiff, seenDiffRows: seenDiffRows
  };
  if (typeof window !== 'undefined') window.MB = API;

  // Node-test surface: the pure derivation / aggregation core, DOM-free.
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
})();

/* stockdata.js — shared helpers for reading the nightly stock library
   (stockdata/index.json + stockdata/<TICKER>.json). Used by the Watchlist;
   available to any page that ships `window.STATE_DISPLAY` (the engine's
   STATE_DISPLAY map, injected by the build). Pure, dependency-free, and
   language-aware via the data-lang attribute — mirrors the helper logic that
   already lives inline in stock.html so the two pages cannot drift on
   filename-sanitization or state-label rules. */
(function () {
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  // pick the zh variant of a parallel-text field when in zh mode (the per-stock
  // JSON carries *_zh siblings from engine/cycles.py)
  function lz(en, zh) { return lang() === 'zh' && zh ? zh : (en || ''); }

  // engine state -> friendly display object {label, action, dir, *_zh}; the map
  // is injected per-page as window.STATE_DISPLAY (mirrors engine.cycles.STATE_DISPLAY)
  function disp(state) { return (window.STATE_DISPLAY || {})[state] || null; }
  // LIMITED is the engine's sentinel ladder state for listings below the cycle-history
  // floor (scripts/build_stock_library.py `_limited_rec`). It is emitted by four of the
  // five per-market indexes but carries NO STATE_DISPLAY entry, so the raw enum would
  // reach the user untranslated once non-US books render. Same bilingual copy the
  // sibling lookup pages already ship (china_lookup.html.j2, canada_stock.html.j2) —
  // house wording, not new copy. theme.css has no `.st-LIMITED` rule, so the pill
  // stays neutral-tinted, which is the honest read for "we can't classify this yet".
  var LIMITED_LABEL = { en: 'limited history', zh: '历史不足' };
  var LIMITED_ACTION = { en: 'new listing · limited history', zh: '新上市 · 历史不足' };
  function label(state) {
    var d = disp(state);
    if (!d) {
      if (state === 'LIMITED') return lang() === 'zh' ? LIMITED_LABEL.zh : LIMITED_LABEL.en;
      return state;   // unknown state: verbatim label, neutral tint — never invented copy
    }
    return lang() === 'zh' ? (d.label_zh || d.label) : d.label;
  }
  function action(state) {
    var d = disp(state);
    if (!d) {
      if (state === 'LIMITED') return lang() === 'zh' ? LIMITED_ACTION.zh : LIMITED_ACTION.en;
      return '';
    }
    return lang() === 'zh' ? (d.action_zh || d.action) : d.action;
  }
  function dir(state) { var d = disp(state); return d ? d.dir : 'neutral'; }
  // theme.css already tints any element carrying class `st-<STATE>` (spaces->_)
  function stClass(state) { return 'st-' + String(state).replace(/ /g, '_'); }

  // Yahoo-style tickers carry '=' / '^', which the Python builder maps to '_' in
  // the on-disk filename. GLOBAL replace (String.replace(str,..) would only hit
  // the first occurrence — fragile if a symbol ever carried two). Leave '.'/'-'
  // untouched: e.g. DX-Y.NYB ships as DX-Y.NYB.json.
  function safeTicker(t) { return String(t).replace(/[=^]/g, '_'); }

  // Per-market store routing. The per-ticker plane is FIVE parallel stores, one per
  // market, all with the same rich schema; `market_books.js` owns the suffix -> store
  // derivation and publishes it on window.MB. Absent (a page that doesn't ship
  // market_books.js), everything resolves to the US store — today's exact behavior.
  function storeOf(t) {
    return (window.MB && window.MB.storeOf) ? window.MB.storeOf(t) : 'stockdata';
  }
  // index.json lives under the same five dirs; crypto/macro names live in the US store
  var MKT_DIR = {
    us: 'stockdata', cn: 'chinastockdata', hk: 'hkstockdata',
    ca: 'canadastockdata', intl: 'intlstockdata'
  };
  function normMkt(m) { return (m === 'crypto' || m === 'macro') ? 'us' : m; }

  var _index = null, _indexBy = null, _tickerCache = {};
  var _mkt = {}, _mktLoading = {};   // market -> {list, byTicker} / in-flight promise

  // fetch + cache the full US search index once -> {list, byTicker}. Unchanged contract:
  // REJECTS when the index is unavailable (callers rely on the catch to still paint).
  function loadIndex() {
    if (_index) return Promise.resolve({ list: _index, byTicker: _indexBy });
    return fetch('stockdata/index.json').then(function (r) {
      if (!r.ok) throw new Error('index unavailable');
      return r.json();
    }).then(function (list) {
      _index = list; _indexBy = {};
      list.forEach(function (x) { x.mkt = x.mkt || 'us'; _indexBy[x.t] = x; });
      _mkt.us = { list: _index, byTicker: _indexBy };
      return { list: _index, byTicker: _indexBy };
    });
  }

  // one market's index, memoized. Fail-OPEN: a missing store contributes nothing
  // rather than breaking the merge (a market the user holds nothing in may 404).
  function loadMarketIndex(m) {
    m = normMkt(m);
    if (_mkt[m]) return Promise.resolve(_mkt[m]);
    if (_mktLoading[m]) return _mktLoading[m];
    var dir = MKT_DIR[m];
    if (!dir) return Promise.resolve({ list: [], byTicker: {} });
    var p = (m === 'us' ? loadIndex() : fetch(dir + '/index.json').then(function (r) {
      if (!r.ok) throw new Error('absent');
      return r.json();
    }).then(function (list) {
      var by = {};
      list.forEach(function (x) { x.mkt = m; by[x.t] = x; });
      _mkt[m] = { list: list, byTicker: by };
      return _mkt[m];
    })).catch(function () {
      _mkt[m] = { list: [], byTicker: {} };
      return _mkt[m];
    });
    _mktLoading[m] = p;
    return p;
  }

  // fetch + merge the named markets' indexes -> {list, byTicker}. Each entry carries
  // its own `.mkt`. Later markets never clobber an earlier ticker (US wins on collision).
  function loadIndexes(markets) {
    var want = [];
    (markets || ['us']).forEach(function (m) {
      m = normMkt(m);
      if (MKT_DIR[m] && want.indexOf(m) < 0) want.push(m);
    });
    if (!want.length) want = ['us'];
    return Promise.all(want.map(loadMarketIndex)).then(function (parts) {
      var list = [], by = {};
      parts.forEach(function (p) {
        if (!p) return;
        p.list.forEach(function (x) {
          if (Object.prototype.hasOwnProperty.call(by, x.t)) return;
          by[x.t] = x; list.push(x);
        });
      });
      return { list: list, byTicker: by };
    });
  }

  // fetch + cache one ticker's rich JSON from ITS market's store; resolves null on
  // 404/absent so callers can degrade gracefully (never throws). Cached either way.
  function loadTicker(t) {
    if (Object.prototype.hasOwnProperty.call(_tickerCache, t))
      return Promise.resolve(_tickerCache[t]);
    return fetch(storeOf(t) + '/' + safeTicker(t) + '.json').then(function (r) {
      if (!r.ok) throw new Error('absent');
      return r.json();
    }).then(function (j) { _tickerCache[t] = j; return j; })
      .catch(function () { _tickerCache[t] = null; return null; });
  }

  window.SD = {
    lang: lang, lz: lz, disp: disp, label: label, action: action, dir: dir,
    stClass: stClass, safeTicker: safeTicker, storeOf: storeOf,
    loadIndex: loadIndex, loadIndexes: loadIndexes, loadTicker: loadTicker
  };
})();

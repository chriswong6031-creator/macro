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
  function label(state) {
    var d = disp(state); if (!d) return state;
    return lang() === 'zh' ? (d.label_zh || d.label) : d.label;
  }
  function action(state) {
    var d = disp(state); if (!d) return '';
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

  var _index = null, _indexBy = null, _tickerCache = {};
  // fetch + cache the full search index once -> {list, byTicker}
  function loadIndex() {
    if (_index) return Promise.resolve({ list: _index, byTicker: _indexBy });
    return fetch('stockdata/index.json').then(function (r) {
      if (!r.ok) throw new Error('index unavailable');
      return r.json();
    }).then(function (list) {
      _index = list; _indexBy = {};
      list.forEach(function (x) { _indexBy[x.t] = x; });
      return { list: _index, byTicker: _indexBy };
    });
  }
  // fetch + cache one ticker's rich JSON; resolves null on 404/absent so callers
  // can degrade gracefully (never throws). Cached either way (incl. the miss).
  function loadTicker(t) {
    if (Object.prototype.hasOwnProperty.call(_tickerCache, t))
      return Promise.resolve(_tickerCache[t]);
    return fetch('stockdata/' + safeTicker(t) + '.json').then(function (r) {
      if (!r.ok) throw new Error('absent');
      return r.json();
    }).then(function (j) { _tickerCache[t] = j; return j; })
      .catch(function () { _tickerCache[t] = null; return null; });
  }

  window.SD = {
    lang: lang, lz: lz, disp: disp, label: label, action: action, dir: dir,
    stClass: stClass, safeTicker: safeTicker, loadIndex: loadIndex, loadTicker: loadTicker
  };
})();

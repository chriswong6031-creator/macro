/* factor_exposure.js — the Portfolio Factor Exposure panel on the watchlist.

   "You think you own 8 trades; you mostly own one." This reads the build-emitted
   factor_betas.json (engine/factor_exposure.py) and the user's holdings — pushed by
   watchlist.js via window.FX.update(tickers) on every render — weights the names the
   factor model covers, and shows the book's net factor betas, each factor's share of
   portfolio RISK, a concentration verdict, and scenario shocks.

   Weighting: equal by default; the user can set per-holding weights (stored locally in
   mdash.fx_weights.v1, relative + auto-normalized) so the read reflects their actual
   allocation. It is a faithful client port of the validated engine.factor_exposure.
   portfolio_exposure() (gate: reports/factor-exposure-phase0.md). Confidence styling is
   driven by the measured tiers in the JSON (factors[].tier/scope) — market/size/growth
   reliable, oil book-level, USD/BTC low-confidence — so the panel can't imply precision
   the data doesn't support. */
(function () {
  'use strict';

  var DATA = null, LOADING = null, LAST = [];
  var WKEY = 'mdash.fx_weights.v1';

  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function sgn(x, nd) {
    return (x == null || !isFinite(x)) ? '—' : (x >= 0 ? '+' : '') + Number(x).toFixed(nd);
  }
  function pct(x) { return (x == null || !isFinite(x)) ? '—' : Math.round(x * 100) + '%'; }

  function loadW() {
    try { return JSON.parse(localStorage.getItem(WKEY)) || {}; } catch (e) { return {}; }
  }
  function saveW(w) {
    try { localStorage.setItem(WKEY, JSON.stringify(w)); } catch (e) { /* private mode */ }
  }

  var ZH = {
    mkt: '市场', growth: '成长/科技', size: '小盘', rates: '利率(久期)',
    usd: '美元', oil: '石油/能源', china: '中国', btc: '比特币/加密', idiosyncratic: '个股特异'
  };
  var STR = {
    en: {
      title: '📉 Portfolio factor exposure',
      sub: 'Equal-weighted across your covered holdings — what you are really long.',
      subW: 'Weighted by your position sizes — what you are really long.',
      netb: 'net β', risk: 'share of risk', idio: 'Stock-specific (idiosyncratic)',
      modeled: function (n, m) { return n + ' of ' + m + ' holdings modeled'; },
      notmod: 'not in the factor model', booklvl: 'book',
      booktip: 'Reliable only at the book level — a single stock’s oil beta is noisy.',
      shocks: 'If this happens, your book moves about…',
      secondary: 'Secondary factors (low confidence — most equity books ≈ 0)',
      editw: '⚖ Edit position weights', wreset: 'Reset to equal',
      wnote: 'Relative weights — normalized automatically. Stored in this browser.',
      legend: 'Risk share = each factor’s contribution to your book’s variance. '
            + 'Measurement, not a forecast.'
    },
    zh: {
      title: '📉 投资组合因子敞口',
      sub: '对已覆盖持仓等权重——你真正做多的是什么。',
      subW: '按你的持仓规模加权——你真正做多的是什么。',
      netb: '净β', risk: '风险占比', idio: '个股特异风险',
      modeled: function (n, m) { return m + ' 个持仓中 ' + n + ' 个已建模'; },
      notmod: '不在因子模型中', booklvl: '组合',
      booktip: '仅在组合层面可靠——单只个股的石油贝塔噪声较大。',
      shocks: '若发生以下情况，组合大约变动…',
      secondary: '次要因子（低置信度——多数股票组合 ≈ 0）',
      editw: '⚖ 编辑持仓权重', wreset: '重置为等权',
      wnote: '相对权重——自动归一化。保存在本浏览器中。',
      legend: '风险占比 = 各因子对组合方差的贡献。为测量而非预测。'
    }
  };
  function S(k) { return (STR[lang()] || STR.en)[k]; }
  function flabel(f) { return lang() === 'zh' ? (ZH[f.key] || f.label) : f.label; }

  var SHOCKS = [
    { key: 'mkt', ret: -0.05, en: 'S&P 500 −5%', zh: '标普 −5%' },
    { key: 'rates', ret: -0.085, en: '10y yield +50bps', zh: '10年期收益率 +50bps' },
    { key: 'oil', ret: 0.10, en: 'Oil +10%', zh: '石油 +10%' }
  ];
  var SHOCKS_LO = [
    { key: 'china', ret: -0.10, en: 'China (FXI) −10%', zh: '中国 (FXI) −10%' },
    { key: 'usd', ret: 0.02, en: 'US dollar +2%', zh: '美元 +2%' },
    { key: 'btc', ret: -0.20, en: 'Bitcoin −20%', zh: '比特币 −20%' }
  ];

  function load() {
    if (DATA) return Promise.resolve(DATA);
    if (LOADING) return LOADING;
    LOADING = fetch('factor_betas.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { DATA = j; return j; })
      .catch(function () { return null; });
    return LOADING;
  }

  // --- the aggregation (port of portfolio_exposure, now weight-aware) ------
  function aggregate(tickers, data, wmap) {
    var keys = data.factors.map(function (f) { return f.key; });
    var betas = data.betas, cov = data.factor_cov;
    var held = tickers.filter(function (t) { return betas[t]; });
    var miss = tickers.filter(function (t) { return !betas[t]; });
    if (held.length < 2) return { ok: false, held: held, miss: miss };
    wmap = wmap || {};
    var n = held.length, eqPct = 100 / n;
    var raw = held.map(function (t) {
      var v = wmap[t]; return (v != null && isFinite(v) && v >= 0) ? v : eqPct;
    });
    var tot = raw.reduce(function (a, b) { return a + b; }, 0) || 1;
    var W = {}; held.forEach(function (t, i) { W[t] = raw[i] / tot; });
    var isCustom = held.some(function (t) { return wmap[t] != null; });

    var bp = {};
    keys.forEach(function (k) {
      var s = 0; held.forEach(function (t) { s += W[t] * (betas[t][k] || 0); });
      bp[k] = s;
    });
    var Sb = {};
    keys.forEach(function (k) {
      var s = 0; keys.forEach(function (j) { s += (cov[k][j] || 0) * bp[j]; }); Sb[k] = s;
    });
    var factorVar = 0; keys.forEach(function (k) { factorVar += bp[k] * Sb[k]; });
    var idioVar = 0; held.forEach(function (t) {
      var iv = betas[t].idio_vol || 0; idioVar += W[t] * W[t] * iv * iv;
    });
    var total = factorVar + idioVar;
    var rc = {};
    keys.forEach(function (k) { rc[k] = total > 0 ? (bp[k] * Sb[k]) / total : 0; });
    var rcIdio = total > 0 ? idioVar / total : 0;
    var ranked = keys.slice().sort(function (a, b) { return Math.abs(rc[b]) - Math.abs(rc[a]); });
    var top = ranked[0], share = rc[top];
    var verdict = share >= 0.50 ? 'C' : share >= 0.33 ? 'T' : 'B';
    return {
      ok: true, keys: keys, held: held, miss: miss, total: tickers.length, eqPct: eqPct,
      bp: bp, rc: rc, rcIdio: rcIdio, W: W, isCustom: isCustom,
      portVol: Math.sqrt(Math.max(total, 0)), top: top, share: share, verdict: verdict
    };
  }

  function shockRows(list, data, a) {
    var betas = data.betas;
    return list.map(function (sh) {
      var pnl = 0; a.held.forEach(function (t) {
        var rb = betas[t].raw || {}; pnl += a.W[t] * (rb[sh.key] || 0) * sh.ret;
      });
      return { name: lang() === 'zh' ? sh.zh : sh.en, pnl: pnl };
    });
  }

  // --- rendering -----------------------------------------------------------
  function bar(label, beta, share, opts) {
    opts = opts || {};
    var width = Math.min(100, Math.abs(share) * 100);
    var col = opts.neutral ? 'var(--muted)' : (beta >= 0 ? 'var(--up)' : 'var(--down)');
    var muted = opts.muted ? 'opacity:.62;' : '';
    var tag = opts.tag ? ' <span class="fx-tag"' + (opts.tagTitle ? ' title="' + esc(opts.tagTitle) + '"' : '')
      + '>' + esc(opts.tag) + '</span>' : '';
    return '<div class="fx-row" style="' + muted + '">'
      + '<div class="fx-lab">' + esc(label) + tag + '</div>'
      + '<div class="fx-beta">' + (opts.neutral ? '' : sgn(beta, 2)) + '</div>'
      + '<div class="fx-track"><span style="width:' + width.toFixed(0) + '%;background:' + col + '"></span></div>'
      + '<div class="fx-share">' + pct(share) + '</div></div>';
  }

  // the weight-dependent display (re-rendered alone on weight edits, so the editor
  // inputs keep focus)
  function resultsInner(a, data) {
    var fByKey = {}; data.factors.forEach(function (f) { fByKey[f.key] = f; });
    var vmap = {
      C: lang() === 'zh' ? '集中——多只个股，实为一注' : 'concentrated — several names, largely one bet',
      T: lang() === 'zh' ? '有明显的主要倾斜' : 'a clear primary tilt',
      B: lang() === 'zh' ? '风险分散于多个因子' : 'risk is spread across factors'
    };
    var topLabel = flabel(fByKey[a.top]).toUpperCase();
    var main = a.keys.filter(function (k) { return (fByKey[k].tier || '') !== 'low'; });
    var lo = a.keys.filter(function (k) { return (fByKey[k].tier || '') === 'low'; });

    var html = '<p class="fx-head"><b>' + pct(a.share) + '</b> '
      + (lang() === 'zh' ? '的组合因子风险来自 ' : 'of your book’s factor risk is ')
      + '<b style="color:' + (a.bp[a.top] >= 0 ? 'var(--up)' : 'var(--down)') + '">' + esc(topLabel) + '</b> '
      + '(' + S('netb') + ' ' + sgn(a.bp[a.top], 2) + ') — ' + esc(vmap[a.verdict]) + '.</p>'
      + '<p class="muted fx-sub">' + (a.isCustom ? S('subW') : S('sub')) + '</p>'
      + '<div class="fx-grid">';
    main.forEach(function (k) {
      var f = fByKey[k], book = (f.scope === 'book');
      html += bar(flabel(f), a.bp[k], a.rc[k],
        book ? { tag: S('booklvl'), tagTitle: S('booktip') } : {});
    });
    html += bar(S('idio'), 0, a.rcIdio, { muted: true, neutral: true });
    html += '</div>';

    var sr = shockRows(SHOCKS, data, a);
    html += '<div class="fx-shocks"><div class="fx-shock-h muted">' + S('shocks') + '</div>';
    sr.forEach(function (r) {
      html += '<div class="fx-srow"><span>' + esc(r.name) + '</span><b style="color:'
        + (r.pnl >= 0 ? 'var(--up)' : 'var(--down)') + '">' + sgn(r.pnl * 100, 1) + '%</b></div>';
    });
    html += '</div>';

    if (lo.length) {
      html += '<details class="fx-lo"><summary>' + esc(S('secondary')) + '</summary><div class="fx-grid">';
      lo.forEach(function (k) { html += bar(flabel(fByKey[k]), a.bp[k], a.rc[k], { muted: true }); });
      html += '</div>';
      shockRows(SHOCKS_LO, data, a).forEach(function (r) {
        html += '<div class="fx-srow" style="opacity:.7"><span>' + esc(r.name) + '</span><b style="color:'
          + (r.pnl >= 0 ? 'var(--up)' : 'var(--down)') + '">' + sgn(r.pnl * 100, 1) + '%</b></div>';
      });
      html += '</details>';
    }

    var cov = '<span>' + esc(S('modeled')(a.held.length, a.total)) + '</span>';
    if (a.miss.length) cov += ' · <span>' + a.miss.map(esc).join(', ') + ' ' + S('notmod') + '</span>';
    html += '<p class="muted fx-cov">' + cov + '</p><p class="muted fx-cov">' + S('legend') + '</p>';
    return html;
  }

  // the weight editor (stable across weight edits — depends only on the held set)
  function editorInner(a, data) {
    var wmap = loadW();
    var rows = a.held.map(function (t) {
      var name = (data.betas[t] && data.betas[t].name) || t;
      var v = wmap[t]; var val = (v != null && isFinite(v)) ? v : Math.round(a.eqPct * 10) / 10;
      return '<div class="fx-wrow"><span class="fx-wt" title="' + esc(name) + '">' + esc(t) + '</span>'
        + '<input class="fx-w" data-t="' + esc(t) + '" type="number" min="0" step="any" value="' + val + '">'
        + '<span class="muted">%</span></div>';
    }).join('');
    return '<details class="fx-wedit"><summary>' + S('editw') + '</summary>'
      + '<div class="fx-wgrid">' + rows + '</div>'
      + '<div class="fx-wfoot"><button type="button" class="fx-wreset">' + S('wreset') + '</button>'
      + '<span class="muted">' + S('wnote') + '</span></div></details>';
  }

  function bindEditor(panel) {
    panel.querySelectorAll('.fx-w').forEach(function (inp) {
      inp.addEventListener('input', function () {
        var w = loadW(); var t = inp.getAttribute('data-t');
        var v = parseFloat(inp.value);
        if (inp.value === '' || isNaN(v)) { delete w[t]; } else { w[t] = v; }
        saveW(w);
        var a = aggregate(LAST, DATA, w);
        var res = document.getElementById('fx_results');
        if (a.ok && res) res.innerHTML = resultsInner(a, DATA);  // editor untouched → focus kept
      });
    });
    var reset = panel.querySelector('.fx-wreset');
    if (reset) reset.addEventListener('click', function () { saveW({}); window.FX.refresh(); });
  }

  function render(panel, tickers, data) {
    if (!data || !data.factors) { panel.style.display = 'none'; return; }
    // AUTO_W (from portfolio.js dollar values) takes precedence over manual editor weights.
    // When AUTO_W is active, use its keys as the universe (not the watchlist tickers arg)
    // so off-watchlist holdings contribute their real weight and no eqPct fallback applies.
    var autoMode = AUTO_W !== null;
    var universe = autoMode ? Object.keys(AUTO_W) : tickers;
    var wmap = autoMode ? AUTO_W : loadW();
    var a = aggregate(universe, data, wmap);
    if (!a.ok) { panel.style.display = 'none'; return; }
    panel.style.display = 'block';
    // In auto mode: hide weight editor, show a one-line note instead.
    var editorOrNote = autoMode
      ? '<div id="fx_autonote"><span class="l-en">Weighted by your holdings</span>'
        + '<span class="l-zh">按持仓加权</span></div>'
      : editorInner(a, data);
    panel.innerHTML = '<h2>' + S('title') + '</h2>'
      + '<div id="fx_results">' + resultsInner(a, data) + '</div>'
      + editorOrNote;
    if (!autoMode) bindEditor(panel);
  }

  // --- public seam ---------------------------------------------------------
  var PANEL = null;
  var AUTO_W = null;  // {ticker->dollarValue} pushed by portfolio.js; null = equal-weight
  function panelEl() { if (!PANEL) PANEL = document.getElementById('fx_panel'); return PANEL; }
  window.FX = {
    update: function (tickers) {
      LAST = (tickers || []).slice();
      var p = panelEl(); if (!p) return;
      load().then(function (data) { render(p, LAST, data); });
    },
    refresh: function () { window.FX.update(LAST); },
    // Called by portfolio.js after every render.
    // w = {ticker: dollarValue} for open holdings with shares + price; null resets to equal-weight.
    setAutoWeights: function (w) {
      AUTO_W = w || null;
      var p = panelEl(); if (!p || !LAST.length) return;
      load().then(function (data) { render(p, LAST, data); });
    }
  };
  document.addEventListener('click', function (e) {
    if (e.target && e.target.classList && e.target.classList.contains('lang-btn')) {
      setTimeout(window.FX.refresh, 0);
    }
  });
})();

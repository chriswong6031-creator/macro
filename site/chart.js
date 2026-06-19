/* chart.js — bespoke single-stock chart (TradingView Lightweight Charts™ v5).

   Replaces the old TradingView iframe widget on stock detail pages with a fully
   self-hosted, theme-aware chart driven by OUR own price data
   (site/ohlc/<TICKER>.json, emitted by scripts/build_chart_data.py):

     • candlesticks where we have true OHLC (the ~110 deep-history names + ETFs),
       a clean gradient area chart from close elsewhere;
     • 1D / 3D / 1W timeframes — daily bars are resampled in the browser;
     • stacked indicator panes computed CLIENT-SIDE — RSI, Stoch, MACD, Stoch RSI
       (so switching timeframes gives you the multi-timeframe Stoch-RSI read you
       use for bottoms, with zero nightly-build cost);
     • EMA overlays, a crosshair OHLC + indicator legend, native pinch-zoom and
       touch scroll, and full dark/light + market (red=up) theming via CSS vars.

   Exposes window.StockChart.mount(container, ticker, {name, lang}). The chart is
   garnish — if the OHLC file is missing it fails quietly and the analysis above
   stands alone, exactly like the old TradingView loader did. */
(function () {
  'use strict';

  var LWC = window.LightweightCharts;
  var PREF_KEY = 'bchart.prefs';
  var IND_ORDER = ['vol', 'rsi', 'stoch', 'macd', 'stochrsi'];   // pane stacking order
  // crisp inline icons (unicode glyphs render inconsistently across mobile fonts)
  var FS_EXPAND = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>';
  var FS_COLLAPSE = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>';

  // ---- one-time scoped styles (injected like theme.js so the template stays lean)
  function injectCSS() {
    if (document.getElementById('bchart-css')) return;
    var s = document.createElement('style');
    s.id = 'bchart-css';
    s.textContent = [
      '.bchart{display:flex;flex-direction:column;gap:8px}',
      '.bchart-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px}',
      '.bchart-seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--panel2)}',
      '.bchart-seg button{appearance:none;border:0;background:transparent;color:var(--muted);font:600 12px/1 inherit;padding:7px 12px;cursor:pointer;-webkit-tap-highlight-color:transparent}',
      '.bchart-seg button+button{border-left:1px solid var(--line)}',
      '.bchart-seg button.on{background:color-mix(in srgb,var(--link) 18%,var(--panel2));color:var(--link)}',
      '.bchart-chips{display:inline-flex;flex-wrap:wrap;gap:6px;margin-left:auto}',
      '.bchart-chip{appearance:none;border:1px solid var(--line);background:var(--panel2);color:var(--muted);font:600 11.5px/1 inherit;padding:6px 10px;border-radius:8px;cursor:pointer;-webkit-tap-highlight-color:transparent;transition:border-color .12s,color .12s}',
      '.bchart-chip:hover{color:var(--text);border-color:color-mix(in srgb,var(--link) 50%,var(--line))}',
      '.bchart-chip.on{color:var(--link);border-color:color-mix(in srgb,var(--link) 60%,var(--line));background:color-mix(in srgb,var(--link) 12%,var(--panel2))}',
      '.bchart-canvas{position:relative;width:100%;height:var(--bchart-h,520px);border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel)}',
      '.bchart-plot{position:absolute;inset:0}',
      '.bchart-legend{position:absolute;top:9px;left:11px;z-index:3;pointer-events:none;font:600 11.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);text-shadow:0 1px 2px var(--panel);white-space:nowrap}',
      '.bchart-legend .t{color:var(--text);font-size:12.5px}',
      '.bchart-legend .up{color:var(--up)} .bchart-legend .dn{color:var(--down)}',
      '.bchart-legend .k{opacity:.75} .bchart-legend .v{color:var(--text)}',
      '.bchart-legend .row{margin-top:1px}',
      '.bchart-msg{display:flex;align-items:center;justify-content:center;height:var(--bchart-h,520px);color:var(--muted);font-size:13px;border:1px dashed var(--line);border-radius:12px;text-align:center;padding:0 20px}',
      // fullscreen control: a floating button (top-right of the chart) + a fixed overlay.
      // CSS overlay (NOT the Fullscreen API, which iOS Safari refuses on non-<video>) so
      // it works on every device; no CSS rotation, so touch pinch/pan stay pixel-accurate.
      '.bchart-fsbtn{position:absolute;top:8px;right:8px;z-index:4;appearance:none;width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--line);background:color-mix(in srgb,var(--panel) 82%,transparent);color:var(--muted);border-radius:8px;cursor:pointer;-webkit-tap-highlight-color:transparent}',
      '.bchart-fsbtn:hover{color:var(--text);border-color:color-mix(in srgb,var(--link) 55%,var(--line))}',
      '.bchart-full{position:fixed;inset:0;z-index:10000;margin:0;box-sizing:border-box;height:100vh;height:100dvh;background:var(--bg);padding:max(10px,env(safe-area-inset-top)) max(12px,env(safe-area-inset-right)) max(10px,env(safe-area-inset-bottom)) max(12px,env(safe-area-inset-left))}',
      '.bchart-full .bchart-canvas{flex:1 1 auto;height:auto;overscroll-behavior:contain}',
      'html.bchart-lock,html.bchart-lock body{overflow:hidden!important}',
      '@media (max-width:640px){.bchart-canvas{--bchart-h:430px}.bchart-msg{--bchart-h:430px}.bchart-chips{margin-left:0}}'
    ].join('');
    document.head.appendChild(s);
  }

  // ---- small helpers -------------------------------------------------------
  function cssVar(name, fb) {
    var v = getComputedStyle(document.body).getPropertyValue(name);
    return (v && v.trim()) || fb;
  }
  // Concrete rgba from a #hex theme token. Histogram bars take a PER-BAR color, and
  // LWC's per-point color path can't resolve a CSS color-mix() string the way it
  // does in static series options — feeding it one silently aborts the paint pass
  // and the whole chart renders blank. So histogram colors are pre-resolved here.
  function alpha(hex, a) {
    if (typeof hex !== 'string' || hex.charAt(0) !== '#') return hex;
    var h = hex.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    if (isNaN(n)) return hex;
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function lang() {
    // theme.js keeps the active language on <html data-lang>, with a localStorage
    // mirror; read the attribute first so labels match the rest of the page.
    return document.documentElement.getAttribute('data-lang') ||
           (localStorage.getItem('lang') === 'zh' ? 'zh' : 'en');
  }
  function tt(en, zh) { return lang() === 'zh' ? (zh || en) : en; }
  function loadPrefs() {
    try { return JSON.parse(localStorage.getItem(PREF_KEY)) || {}; } catch (e) { return {}; }
  }
  function savePrefs(p) { try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (e) {} }
  function safeName(t) { return String(t).replace('=', '_').replace('^', '_'); }

  // ---- indicator math (all client-side; arrays align 1:1 with the bar array) --
  function sma(a, p) {
    var out = new Array(a.length).fill(null), sum = 0, n = 0, q = [];
    for (var i = 0; i < a.length; i++) {
      var v = a[i];
      if (v == null) { q.push(null); continue; }
      q.push(v); sum += v; n++;
      while (q.length > p) { var old = q.shift(); if (old != null) { sum -= old; n--; } }
      if (q.length === p && n === p) out[i] = sum / p;
    }
    return out;
  }
  function ema(a, p) {
    var out = new Array(a.length).fill(null), k = 2 / (p + 1), prev = null, seed = 0, cnt = 0;
    for (var i = 0; i < a.length; i++) {
      var v = a[i];
      if (v == null) { out[i] = prev; continue; }
      if (prev == null) { seed += v; cnt++; if (cnt === p) { prev = seed / p; out[i] = prev; } }
      else { prev = v * k + prev * (1 - k); out[i] = prev; }
    }
    return out;
  }
  function rsi(cl, p) {
    p = p || 14;
    var out = new Array(cl.length).fill(null), g = 0, l = 0;
    for (var i = 1; i < cl.length; i++) {
      var ch = cl[i] - cl[i - 1], up = ch > 0 ? ch : 0, dn = ch < 0 ? -ch : 0;
      if (i <= p) {
        g += up; l += dn;
        if (i === p) { g /= p; l /= p; out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); }
      } else {
        g = (g * (p - 1) + up) / p; l = (l * (p - 1) + dn) / p;
        out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
      }
    }
    return out;
  }
  // rolling raw %K of `src` against its own high/low over `p` (src may carry nulls)
  function rawStoch(src, hi, lo, p) {
    var out = new Array(src.length).fill(null);
    for (var i = 0; i < src.length; i++) {
      if (src[i] == null) continue;
      var hh = -Infinity, ll = Infinity, ok = true;
      for (var j = i - p + 1; j <= i; j++) {
        if (j < 0 || hi[j] == null || lo[j] == null) { ok = false; break; }
        if (hi[j] > hh) hh = hi[j];
        if (lo[j] < ll) ll = lo[j];
      }
      if (ok) out[i] = hh === ll ? 100 : 100 * (src[i] - ll) / (hh - ll);
    }
    return out;
  }
  function stoch(hi, lo, cl, kP, kS, dP) {
    var raw = rawStoch(cl, hi, lo, kP || 14);
    var k = sma(raw, kS || 3);
    return { k: k, d: sma(k, dP || 3) };
  }
  function macd(cl, f, s, sig) {
    var ef = ema(cl, f || 12), es = ema(cl, s || 26);
    var line = cl.map(function (_, i) { return (ef[i] == null || es[i] == null) ? null : ef[i] - es[i]; });
    var signal = ema(line, sig || 9);
    var hist = line.map(function (_, i) { return (line[i] == null || signal[i] == null) ? null : line[i] - signal[i]; });
    return { line: line, signal: signal, hist: hist };
  }
  function stochRsi(cl, rsiP, stochP, kS, dS) {
    var r = rsi(cl, rsiP || 14);
    var raw = rawStoch(r, r, r, stochP || 14);   // stoch of the RSI series itself
    var k = sma(raw, kS || 3);
    return { k: k, d: sma(k, dS || 3) };
  }

  // ---- resampling: daily bars -> 3-bar buckets or ISO weeks -----------------
  // bars are [date, c, v] (close-only) or [date, o, h, l, c, v] (OHLC). The chart
  // normalises to {time,o,h,l,c,v} objects up front; resampling works on those.
  function normalise(data) {
    var ohlc = data.o === 1;
    return data.bars.map(function (b) {
      if (ohlc) return { time: b[0], o: b[1], h: b[2], l: b[3], c: b[4], v: b[5] };
      return { time: b[0], o: b[1], h: b[1], l: b[1], c: b[1], v: b[2] };  // flat OHLC from close
    });
  }
  function isoWeek(d) {                       // YYYY-Www key for weekly buckets
    var dt = new Date(d + 'T00:00:00Z');
    var day = (dt.getUTCDay() + 6) % 7;       // Mon=0
    dt.setUTCDate(dt.getUTCDate() - day + 3); // nearest Thursday
    var firstThu = new Date(Date.UTC(dt.getUTCFullYear(), 0, 4));
    var fday = (firstThu.getUTCDay() + 6) % 7;
    firstThu.setUTCDate(firstThu.getUTCDate() - fday + 3);
    var wk = 1 + Math.round((dt - firstThu) / 604800000);
    return dt.getUTCFullYear() + '-' + wk;
  }
  function resample(rows, tf) {
    if (tf === '1D' || rows.length === 0) return rows;
    var out = [], cur = null, key = null;
    function flush() { if (cur) out.push(cur); }
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], k;
      if (tf === '1W') k = isoWeek(r.time);
      else if (tf === '1M') k = r.time.slice(0, 7);   // calendar month: YYYY-MM
      else k = Math.floor(i / 3);             // 3D = chunks of 3 sessions
      if (k !== key) { flush(); key = k; cur = { time: r.time, o: r.o, h: r.h, l: r.l, c: r.c, v: r.v || 0 }; }
      else {
        cur.h = Math.max(cur.h, r.h); cur.l = Math.min(cur.l, r.l);
        cur.c = r.c; cur.time = r.time; cur.v += (r.v || 0);
      }
    }
    flush();
    return out;
  }

  // Intraday (hourly) bars from Polygon: [epochSec, o, h, l, c, v]. Time is a numeric
  // UTC timestamp — LWC renders it on a time-of-day axis — distinct from the daily
  // path's 'YYYY-MM-DD' strings, so a 4H render is never mixed with daily-stringed bars.
  function normaliseIntra(data) {
    return (data.bars || []).map(function (b) {
      return { time: b[0], o: b[1], h: b[2], l: b[3], c: b[4], v: b[5] };
    });
  }
  // 4-hour candles on a continuous UTC grid (TradingView-style, not session-reset):
  // bucket hourly bars by floor(epoch / 4h); each bar is stamped at its bucket start.
  function resample4H(rows) {
    var out = [], cur = null, key = null, B = 4 * 3600;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], k = Math.floor(r.time / B);
      if (k !== key) { if (cur) out.push(cur); key = k; cur = { time: k * B, o: r.o, h: r.h, l: r.l, c: r.c, v: r.v || 0 }; }
      else { cur.h = Math.max(cur.h, r.h); cur.l = Math.min(cur.l, r.l); cur.c = r.c; cur.v += (r.v || 0); }
    }
    if (cur) out.push(cur);
    return out;
  }

  function priceFmt(last) {
    var prec = last >= 1 ? 2 : (last >= 0.1 ? 3 : 5);
    return { type: 'price', precision: prec, minMove: Math.pow(10, -prec) };
  }
  function fnum(x, p) { return (x == null || !isFinite(x)) ? '—' : x.toFixed(p == null ? 2 : p); }
  function fmtTime(t) {   // daily bars carry 'YYYY-MM-DD' strings; intraday carries epoch seconds
    if (typeof t !== 'number') return t;
    var d = new Date(t * 1000), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate()) +
           ' ' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes());
  }

  // ---- the chart instance ---------------------------------------------------
  function Instance(host, ticker, opts) {
    this.host = host; this.ticker = ticker; this.opts = opts || {};
    // Per-market data location: US fetches ohlc/<T>.json; CN/CA/intl pass their own
    // dir (chinaohlc/…); HK passes opts.data inline (it already ships a close series).
    this.ohlcDir = this.opts.ohlcDir || 'ohlc';
    // opts.intraday (US names with a Polygon intraday file) unlocks the 4H button;
    // its hourly bars are lazy-fetched from intraday/<T>.json on first 4H select.
    this.intraday = !!this.opts.intraday;
    this.intradayRows = null;
    this.chart = null; this.S = {};            // series refs
    var pr = loadPrefs();
    this.tf = pr.tf || '1D';
    if (this.tf === '4H') this.tf = '1D';      // 4H loads on demand, not at mount
    this.inds = new Set(pr.inds || ['rsi', 'stochrsi']);   // default: RSI + Stoch RSI
    this.ema = pr.ema !== false;               // EMA overlays default on
    this.rows = null; this.data = null;
    this._onTheme = this.rerender.bind(this);
    this._onLang = this.rebuildUI.bind(this);
    var self = this;
    this._onKey = function (e) { if (e.key === 'Escape' || e.keyCode === 27) self.exitFull(); };
  }

  Instance.prototype.mount = function () {
    injectCSS();
    this.host.innerHTML = '';
    this.wrap = document.createElement('div'); this.wrap.className = 'bchart';
    this.host.appendChild(this.wrap);
    this.renderMsg(tt('Loading chart…', '正在加载图表…'));
    var self = this;
    function use(j) {
      if (!j || !j.bars || !j.bars.length) { self.renderMsg(tt(
        'Live chart unavailable for this name — the analysis above stands on its own.',
        '该标的暂无图表数据 —— 上方分析独立成立。')); return; }
      self.data = j;
      self.rows = normalise(j);
      self.hasVol = self.rows.some(function (r) { return r.v != null && r.v > 0; });
      self.buildUI();
      self.rerender();
      document.addEventListener('themechange', self._onTheme);
      document.addEventListener('langchange', self._onLang);
      document.addEventListener('keydown', self._onKey);
    }
    // Inline data (HK) renders without a round-trip; otherwise fetch the market's dir.
    if (this.opts.data) { use(this.opts.data); return this; }
    var url = this.ohlcDir + '/' + safeName(this.ticker) + '.json';
    fetch(url).then(function (r) { return r.ok ? r.json() : null; }).then(use)
      .catch(function () { self.renderMsg(tt('Chart failed to load.', '图表加载失败。')); });
    return this;
  };

  Instance.prototype.renderMsg = function (msg) {
    this.wrap.innerHTML = '<div class="bchart-msg">' + msg + '</div>';
  };

  Instance.prototype.buildUI = function () {
    var self = this;
    this.wrap.innerHTML = '';
    // toolbar
    var bar = document.createElement('div'); bar.className = 'bchart-bar';
    var seg = document.createElement('div'); seg.className = 'bchart-seg';
    var TFS = [['1D', '1D'], ['3D', '3D'], ['1W', tt('1W', '周')], ['1M', tt('1M', '月')]];
    if (this.intraday) TFS.unshift(['4H', '4H']);   // intraday only where a Polygon file exists
    TFS.forEach(function (tfp) {
      var b = document.createElement('button'); b.textContent = tfp[1]; b.dataset.tf = tfp[0];
      if (self.tf === tfp[0]) b.className = 'on';
      b.onclick = function () { self.setTimeframe(tfp[0]); };
      seg.appendChild(b);
    });
    bar.appendChild(seg);

    var chips = document.createElement('div'); chips.className = 'bchart-chips';
    var defs = [['ema', tt('EMA', '均线')], ['rsi', 'RSI'], ['stoch', tt('Stoch', '随机')],
                ['macd', 'MACD'], ['stochrsi', tt('Stoch RSI', '随机RSI')]];
    if (this.hasVol) defs.push(['vol', tt('Vol', '量')]);
    defs.forEach(function (d) {
      var b = document.createElement('button'); b.className = 'bchart-chip'; b.textContent = d[1];
      b.dataset.k = d[0];
      var on = d[0] === 'ema' ? self.ema : self.inds.has(d[0]);
      if (on) b.classList.add('on');
      b.onclick = function () {
        if (d[0] === 'ema') self.ema = !self.ema;
        else { if (self.inds.has(d[0])) self.inds.delete(d[0]); else self.inds.add(d[0]); }
        self.persist(); self.syncBar(); self.rerender();
      };
      chips.appendChild(b);
    });
    bar.appendChild(chips);
    this.bar = bar; this.wrap.appendChild(bar);

    // canvas + legend + fullscreen button
    var canvas = document.createElement('div'); canvas.className = 'bchart-canvas';
    this.legend = document.createElement('div'); this.legend.className = 'bchart-legend';
    this.plot = document.createElement('div'); this.plot.className = 'bchart-plot';
    this.fsbtn = document.createElement('button'); this.fsbtn.type = 'button';
    this.fsbtn.className = 'bchart-fsbtn';
    var isFull = this.wrap.classList.contains('bchart-full');
    this.fsbtn.innerHTML = isFull ? FS_COLLAPSE : FS_EXPAND;
    this.fsbtn.setAttribute('aria-label', tt('Full screen', '全屏'));
    this.fsbtn.onclick = function () { self.toggleFull(); };
    canvas.appendChild(this.legend); canvas.appendChild(this.plot); canvas.appendChild(this.fsbtn);
    this.wrap.appendChild(canvas);
  };

  // CSS-overlay fullscreen (works on iOS, unlike requestFullscreen). Resize + restore
  // the visible range after the box changes so bars never re-cram or reset zoom.
  Instance.prototype.toggleFull = function () {
    var full = this.wrap.classList.toggle('bchart-full');
    document.documentElement.classList.toggle('bchart-lock', full);
    if (this.fsbtn) {
      this.fsbtn.innerHTML = full ? FS_COLLAPSE : FS_EXPAND;
      this.fsbtn.setAttribute('aria-label', full ? tt('Exit full screen', '退出全屏') : tt('Full screen', '全屏'));
    }
    var self = this;
    requestAnimationFrame(function () {
      if (!self.chart) return;
      var keep = null; try { keep = self.chart.timeScale().getVisibleLogicalRange(); } catch (e) {}
      try { self.chart.resize(self.plot.clientWidth, self.plot.clientHeight); } catch (e) {}
      if (keep) { try { self.chart.timeScale().setVisibleLogicalRange(keep); } catch (e) {} }
    });
  };
  Instance.prototype.exitFull = function () {
    if (this.wrap && this.wrap.classList.contains('bchart-full')) this.toggleFull();
  };
  Instance.prototype.rebuildUI = function () { if (this.rows) { this.buildUI(); this.rerender(); } };
  // Timeframe switch. 4H lazy-loads its hourly intraday file once; daily-derived
  // frames (1D/3D/1W/1M) just re-render. A failed/empty 4H fetch leaves the current
  // frame in place (syncBar un-highlights 4H) — the button only shows for names we
  // expect to have data, so this is a rare graceful no-op.
  Instance.prototype.setTimeframe = function (tf) {
    var self = this;
    if (tf === '4H' && !this.intradayRows) {
      fetch('intraday/' + safeName(this.ticker) + '.json')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (j && j.bars && j.bars.length) {
            self.intradayRows = normaliseIntra(j);
            self.tf = '4H'; self.persist(); self.syncBar(); self.rerender();
          } else { self.syncBar(); }
        }).catch(function () { self.syncBar(); });
      return;
    }
    this.tf = tf; this.persist(); this.syncBar(); this.rerender();
  };
  Instance.prototype.syncBar = function () {
    if (!this.bar) return; var self = this;
    this.bar.querySelectorAll('[data-tf]').forEach(function (b) { b.className = (self.tf === b.dataset.tf) ? 'on' : ''; });
    this.bar.querySelectorAll('[data-k]').forEach(function (b) {
      var on = b.dataset.k === 'ema' ? self.ema : self.inds.has(b.dataset.k);
      b.classList.toggle('on', !!on);
    });
  };
  Instance.prototype.persist = function () {
    savePrefs({ tf: this.tf, inds: Array.from(this.inds), ema: this.ema });
  };

  // (re)build the whole chart — cheap (data already in memory) and avoids any
  // pane-index bookkeeping. The visible range is preserved across rebuilds.
  Instance.prototype.rerender = function () {
    if (!this.rows) return;
    // Preserve the user's zoom/pan ONLY across changes that keep the same x-axis
    // (toggling an indicator, theme/lang). A timeframe switch changes the bar
    // count, so a stale logical range would land in empty space past the series —
    // fit to content instead.
    var keepRange = null;
    if (this._ro) { try { this._ro.disconnect(); } catch (e) {} this._ro = null; }
    if (this._io) { try { this._io.disconnect(); } catch (e) {} this._io = null; }
    if (this.chart) {
      if (this.tf === this._lastTf) {
        try { keepRange = this.chart.timeScale().getVisibleLogicalRange(); } catch (e) {}
      }
      try { this.chart.remove(); } catch (e) {}
    }
    this._lastTf = this.tf;
    this.plot.innerHTML = '';
    var c = {
      up: cssVar('--up', '#45b873'), down: cssVar('--down', '#e06464'),
      text: cssVar('--text', '#d7dce3'), muted: cssVar('--muted', '#8b93a1'),
      line: cssVar('--line', '#2a2f3a'), panel: cssVar('--panel', '#181b21'),
      link: cssVar('--link', '#7aa7e0'), warn: cssVar('--warn', '#e0a030')
    };
    var grid = 'color-mix(in srgb,' + c.line + ' 55%,transparent)';
    // Size the chart EXPLICITLY from the container rather than autoSize: autoSize's
    // ResizeObserver fires asynchronously and on heavier (multi-pane) renders it
    // intermittently never applies, leaving the canvases stuck at the 300x150
    // default — a fully-built chart that paints nothing. Reading the real size now
    // makes the first paint deterministic; the ResizeObserver below handles reflow.
    var W = this.plot.clientWidth, H = this.plot.clientHeight;
    var chart = LWC.createChart(this.plot, {
      width: W || 300, height: H || 200,
      layout: { background: { type: 'solid', color: c.panel }, textColor: c.muted,
                fontFamily: 'inherit', fontSize: 11, attributionLogo: false,
                panes: { separatorColor: c.line, separatorHoverColor: 'color-mix(in srgb,' + c.link + ' 40%,transparent)' } },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      crosshair: { mode: LWC.CrosshairMode.Normal,
        vertLine: { color: c.muted, width: 1, style: 3, labelBackgroundColor: c.link },
        horzLine: { color: c.muted, width: 1, style: 3, labelBackgroundColor: c.link } },
      rightPriceScale: { borderColor: c.line, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: c.line, rightOffset: 4, barSpacing: 8, minBarSpacing: 1.2, fixLeftEdge: false,
        timeVisible: this.tf === '4H', secondsVisible: false },   // 4H needs a time-of-day axis
      handleScroll: { vertTouchDrag: false },   // let vertical swipes scroll the page
      handleScale: { axisPressedMouseMove: true }
    });
    this.chart = chart; this.S = {};
    var rows = (this.tf === '4H') ? resample4H(this.intradayRows || []) : resample(this.rows, this.tf);
    this.view = rows;
    if (!rows.length) { this.updateLegend(null); return; }   // safety: never build an empty chart
    var ohlc = (this.tf === '4H') ? true : (this.data.o === 1);   // intraday is always OHLC
    var closes = rows.map(function (r) { return r.c; });
    var highs = rows.map(function (r) { return r.h; });
    var lows = rows.map(function (r) { return r.l; });
    var last = closes[closes.length - 1] || 1;
    var pf = priceFmt(last);

    // ---- main price pane (0) ----
    if (ohlc) {
      var cs = chart.addSeries(LWC.CandlestickSeries, {
        upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down,
        wickUpColor: c.up, wickDownColor: c.down, priceFormat: pf
      }, 0);
      cs.setData(rows.map(function (r) { return { time: r.time, open: r.o, high: r.h, low: r.l, close: r.c }; }));
      this.S.price = cs;
    } else {
      var ar = chart.addSeries(LWC.AreaSeries, {
        lineColor: c.link, topColor: 'color-mix(in srgb,' + c.link + ' 38%,transparent)',
        bottomColor: 'color-mix(in srgb,' + c.link + ' 3%,transparent)', lineWidth: 2, priceFormat: pf
      }, 0);
      ar.setData(rows.map(function (r) { return { time: r.time, value: r.c }; }));
      this.S.price = ar;
    }

    // EMA overlays on the price pane
    if (this.ema) {
      var emaDefs = [[20, c.warn], [50, c.link], [200, c.muted]];
      this.S.ema = emaDefs.map(function (e) {
        var arr = ema(closes, e[0]);
        var ln = chart.addSeries(LWC.LineSeries, { color: e[1], lineWidth: 1.4,
          priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
          title: 'EMA' + e[0], priceFormat: pf }, 0);
        ln.setData(toLine(rows, arr));
        return { p: e[0], series: ln, arr: arr };
      });
    }

    // ---- indicator panes, stacked in canonical order ----
    var pane = 1;
    if (this.inds.has('vol') && this.hasVol) { this.addVol(rows, pane++, c); }
    if (this.inds.has('rsi')) { this.addRsi(rows, closes, pane++, c, pf); }
    if (this.inds.has('stoch')) { this.addStoch(rows, highs, lows, closes, ohlc, pane++, c); }
    if (this.inds.has('macd')) { this.addMacd(rows, closes, pane++, c); }
    if (this.inds.has('stochrsi')) { this.addStochRsi(rows, closes, pane++, c); }

    // give the price pane the dominant share of the height
    try {
      var panes = chart.panes();
      panes.forEach(function (pp, i) { pp.setStretchFactor(i === 0 ? 4.2 : 1.35); });
    } catch (e) {}

    var self = this, ts = chart.timeScale();
    function doFit() {
      if (keepRange) { try { ts.setVisibleLogicalRange(keepRange); } catch (e) {} }
      else { try { ts.fitContent(); } catch (e) {} }
      self._didFit = true;
    }
    this._didFit = false;
    if (W && H) doFit();           // canvas was sized at creation — fit immediately
    // The container drives the size. A create-at-zero-width (rare: a momentarily
    // collapsed or hidden panel) recovers on the first real measurement; later
    // width changes (window resize, phone rotation) preserve the visible bar range
    // so a resize never re-crams the chart or resets the user's zoom.
    this._ro = new ResizeObserver(function () {
      var w = self.plot.clientWidth, h = self.plot.clientHeight;
      if (!w || !h) return;
      var keep = self._didFit
        ? (function () { try { return ts.getVisibleLogicalRange(); } catch (e) { return null; } })()
        : null;
      try { chart.resize(w, h); } catch (e) {}
      if (!self._didFit) doFit();
      else if (keep) { try { ts.setVisibleLogicalRange(keep); } catch (e) {} }
    });
    this._ro.observe(this.plot);

    // Insurance for a chart built below the fold (the panel sits far down the stock
    // page): the size never changes, so the ResizeObserver won't fire, and some
    // engines defer the first canvas paint for far-offscreen elements. When the
    // panel first scrolls into view, nudge the size so LWC definitely repaints.
    if ('IntersectionObserver' in window) {
      this._io = new IntersectionObserver(function (ents) {
        if (!ents.some(function (e) { return e.isIntersecting; })) return;
        var w = self.plot.clientWidth, h = self.plot.clientHeight;
        if (w && h) { try { chart.resize(w - 1, h); chart.resize(w, h); if (!self._didFit) doFit(); } catch (e) {} }
        if (self._io) { self._io.disconnect(); self._io = null; }
      });
      this._io.observe(this.host);
    }
    this.wireLegend();
    this.updateLegend(null);
  };

  function toLine(rows, arr) {
    var out = [];
    for (var i = 0; i < rows.length; i++) if (arr[i] != null && isFinite(arr[i])) out.push({ time: rows[i].time, value: arr[i] });
    return out;
  }

  Instance.prototype.addVol = function (rows, idx, c) {
    var s = this.chart.addSeries(LWC.HistogramSeries, {
      priceFormat: { type: 'volume' }, priceScaleId: '',
      priceLineVisible: false, lastValueVisible: false
    }, idx);
    s.setData(rows.map(function (r) {
      return { time: r.time, value: r.v || 0, color: alpha(r.c >= r.o ? c.up : c.down, 0.5) };
    }));
    this.S.vol = s;
  };
  Instance.prototype.addRsi = function (rows, closes, idx, c, pf) {
    var arr = rsi(closes, 14);
    var s = this.chart.addSeries(LWC.LineSeries, { color: c.link, lineWidth: 1.6,
      priceLineVisible: false, lastValueVisible: true, title: 'RSI',
      priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }, idx);
    s.setData(toLine(rows, arr));
    [[70, c.down], [30, c.up], [50, c.muted]].forEach(function (g) {
      s.createPriceLine({ price: g[0], color: 'color-mix(in srgb,' + g[1] + ' 45%,transparent)',
        lineWidth: 1, lineStyle: g[0] === 50 ? 3 : 2, axisLabelVisible: false });
    });
    this.S.rsi = { k: s, arr: arr };
  };
  Instance.prototype.addStoch = function (rows, highs, lows, closes, ohlc, idx, c) {
    var st = stoch(ohlc ? highs : closes, ohlc ? lows : closes, closes, 14, 3, 3);
    var k = this.chart.addSeries(LWC.LineSeries, { color: c.link, lineWidth: 1.5,
      priceLineVisible: false, lastValueVisible: true, title: '%K',
      priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }, idx);
    var d = this.chart.addSeries(LWC.LineSeries, { color: c.warn, lineWidth: 1.2,
      priceLineVisible: false, lastValueVisible: false, title: '%D',
      priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }, idx);
    k.setData(toLine(rows, st.k)); d.setData(toLine(rows, st.d));
    [[80, c.down], [20, c.up]].forEach(function (g) {
      k.createPriceLine({ price: g[0], color: 'color-mix(in srgb,' + g[1] + ' 42%,transparent)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    });
    this.S.stoch = { k: k, d: d, ak: st.k, ad: st.d };
  };
  Instance.prototype.addMacd = function (rows, closes, idx, c) {
    var m = macd(closes, 12, 26, 9);
    var h = this.chart.addSeries(LWC.HistogramSeries, { priceLineVisible: false, lastValueVisible: false,
      priceFormat: { type: 'price', precision: 3, minMove: 0.001 } }, idx);
    var hd = [];
    rows.forEach(function (r, i) {
      if (m.hist[i] == null || !isFinite(m.hist[i])) return;   // drop leading warm-up, no whitespace
      hd.push({ time: r.time, value: m.hist[i], color: alpha(m.hist[i] >= 0 ? c.up : c.down, 0.55) });
    });
    h.setData(hd);
    var line = this.chart.addSeries(LWC.LineSeries, { color: c.link, lineWidth: 1.5, priceLineVisible: false,
      lastValueVisible: false, title: 'MACD', priceFormat: { type: 'price', precision: 3, minMove: 0.001 } }, idx);
    var sig = this.chart.addSeries(LWC.LineSeries, { color: c.warn, lineWidth: 1.2, priceLineVisible: false,
      lastValueVisible: false, title: 'signal', priceFormat: { type: 'price', precision: 3, minMove: 0.001 } }, idx);
    line.setData(toLine(rows, m.line)); sig.setData(toLine(rows, m.signal));
    this.S.macd = { line: line, sig: sig, hist: h, m: m };
  };
  Instance.prototype.addStochRsi = function (rows, closes, idx, c) {
    var sr = stochRsi(closes, 14, 14, 3, 3);
    var k = this.chart.addSeries(LWC.LineSeries, { color: c.link, lineWidth: 1.6, priceLineVisible: false,
      lastValueVisible: true, title: 'Stoch RSI %K', priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }, idx);
    var d = this.chart.addSeries(LWC.LineSeries, { color: c.warn, lineWidth: 1.2, priceLineVisible: false,
      lastValueVisible: false, title: '%D', priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }, idx);
    k.setData(toLine(rows, sr.k)); d.setData(toLine(rows, sr.d));
    [[80, c.down], [20, c.up]].forEach(function (g) {
      k.createPriceLine({ price: g[0], color: 'color-mix(in srgb,' + g[1] + ' 42%,transparent)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    });
    this.S.stochrsi = { k: k, d: d, ak: sr.k, ad: sr.d };
  };

  // ---- crosshair legend -----------------------------------------------------
  Instance.prototype.wireLegend = function () {
    var self = this;
    this.chart.subscribeCrosshairMove(function (param) {
      self.updateLegend(param && param.time ? param : null);
    });
  };
  Instance.prototype.updateLegend = function (param) {
    if (!this.view || !this.view.length) return;
    var i = this.view.length - 1;             // default to last bar
    if (param && param.time) {
      for (var j = 0; j < this.view.length; j++) if (this.view[j].time === param.time) { i = j; break; }
    }
    var r = this.view[i], prev = i > 0 ? this.view[i - 1].c : r.o;
    var up = r.c >= prev, sgn = up ? 'up' : 'dn';
    var ch = r.c - prev, chp = prev ? (ch / prev * 100) : 0;
    var pp = (this.data.o === 1) ? 2 : 2;
    var html = '<span class="t">' + this.ticker + '</span> <span class="k">' + fmtTime(r.time) + '</span>';
    if (this.tf === '4H' || this.data.o === 1) {
      html += '<div class="row">O<span class="v"> ' + fnum(r.o, pp) + '</span> H<span class="v"> ' + fnum(r.h, pp) +
              '</span> L<span class="v"> ' + fnum(r.l, pp) + '</span> C<span class="' + sgn + '"> ' + fnum(r.c, pp) + '</span> ' +
              '<span class="' + sgn + '">' + (up ? '+' : '') + fnum(chp, 2) + '%</span></div>';
    } else {
      html += '<div class="row"><span class="' + sgn + '">' + fnum(r.c, pp) + '  ' + (up ? '+' : '') + fnum(chp, 2) + '%</span></div>';
    }
    if (this.ema && this.S.ema) {
      var es = this.S.ema.map(function (e) { return 'EMA' + e.p + ' ' + fnum(e.arr[i], pp); }).join('  ');
      html += '<div class="row k">' + es + '</div>';
    }
    if (this.S.rsi) html += '<div class="row"><span class="k">RSI</span> <span class="v">' + fnum(this.S.rsi.arr[i], 1) + '</span></div>';
    if (this.S.stoch) html += '<div class="row"><span class="k">Stoch</span> <span class="v">%K ' + fnum(this.S.stoch.ak[i], 1) + ' · %D ' + fnum(this.S.stoch.ad[i], 1) + '</span></div>';
    if (this.S.macd) html += '<div class="row"><span class="k">MACD</span> <span class="v">' + fnum(this.S.macd.m.line[i], 3) + ' · sig ' + fnum(this.S.macd.m.signal[i], 3) + '</span></div>';
    if (this.S.stochrsi) html += '<div class="row"><span class="k">Stoch RSI</span> <span class="v">%K ' + fnum(this.S.stochrsi.ak[i], 1) + ' · %D ' + fnum(this.S.stochrsi.ad[i], 1) + '</span></div>';
    this.legend.innerHTML = html;
  };

  Instance.prototype.destroy = function () {
    document.removeEventListener('themechange', this._onTheme);
    document.removeEventListener('langchange', this._onLang);
    document.removeEventListener('keydown', this._onKey);
    // releasing the chart (e.g. navigating to another ticker) must not leave the
    // page scroll-locked if it was destroyed while fullscreen.
    document.documentElement.classList.remove('bchart-lock');
    if (this._ro) { try { this._ro.disconnect(); } catch (e) {} this._ro = null; }
    if (this._io) { try { this._io.disconnect(); } catch (e) {} this._io = null; }
    if (this.chart) { try { this.chart.remove(); } catch (e) {} this.chart = null; }
  };

  // ---- public API -----------------------------------------------------------
  window.StockChart = {
    _cur: null,
    mount: function (host, ticker, opts) {
      if (!LWC || !host || !ticker) return null;
      if (this._cur) this._cur.destroy();
      this._cur = new Instance(host, ticker, opts);
      return this._cur.mount();
    }
  };
})();

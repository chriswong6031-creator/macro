// tvfallback.js — China-safe charting.
//
// TradingView's embed (s3.tradingview.com + its data servers) is GFW-blocked in
// mainland China, so a plain `new TradingView.widget(...)` shows a blank box for
// China IPs. We keep the rich TradingView widget for everyone it reaches, but
// probe it once (non-blocking) and, when it's unreachable, draw the chart from
// OUR OWN stored EOD closes via the open-source Lightweight Charts library
// (vendored locally so nothing crosses the firewall). Same "the repo is the
// database" approach the HK pages already use.
(function () {
  'use strict';

  // ---- one-shot probe: is the TradingView embed reachable? ------------------
  // Resolves true if s3.tradingview.com/tv.js loads within the timeout, else
  // false. GFW reset -> onerror (fast); GFW null-route -> the timeout fires.
  // Injected async so a blocked/hanging domain never stalls page parsing (the
  // old synchronous <script src> tag could freeze the whole page in China).
  window.__tvReady = window.__tvReady || new Promise(function (resolve) {
    if (window.TradingView) { resolve(true); return; }
    var done = false;
    function fin(ok) { if (!done) { done = true; resolve(ok); } }
    var s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/tv.js';
    s.async = true;
    s.onload = function () { fin(!!window.TradingView); };
    s.onerror = function () { fin(false); };
    (document.head || document.documentElement).appendChild(s);
    setTimeout(function () { fin(!!window.TradingView); }, 3500);
  });

  // ---- lazy-load the vendored Lightweight Charts lib (fallback path only) ---
  // Same-origin asset, so it's always reachable in China. Loaded only when the
  // fallback actually fires, keeping ~160KB off the happy path for the (global)
  // majority who get the TradingView widget.
  var lwcP = null;
  function ensureLWC() {
    if (window.LightweightCharts) return Promise.resolve(true);
    if (lwcP) return lwcP;
    lwcP = new Promise(function (resolve) {
      var s = document.createElement('script');
      s.src = 'lightweight-charts.js';
      s.async = true;
      s.onload = function () { resolve(!!window.LightweightCharts); };
      s.onerror = function () { resolve(false); };
      (document.head || document.documentElement).appendChild(s);
    });
    return lwcP;
  }

  // ---- draw an area + 50/200-day SMA chart from stored closes ---------------
  // chart = { t:[ISO date strings], c:[closes] }; opts = { height }.
  // Mirrors hk_stock.html.j2's renderer so every page draws an identical chart.
  window.drawLocalChart = function (box, chart, opts) {
    opts = opts || {};
    if (!box) return;
    function nochart() {
      box.innerHTML = '<p class="muted" style="font-size:13px">' +
        (opts.nochart || 'Chart unavailable for this symbol.') + '</p>';
    }
    if (!chart || !chart.t || !chart.t.length) { nochart(); return; }
    ensureLWC().then(function (ok) {
      if (!ok || !window.LightweightCharts) { nochart(); return; }
      box.innerHTML = '';
      var holder = document.createElement('div');
      holder.style.height = (opts.height || 430) + 'px';
      holder.style.width = '100%';
      box.appendChild(holder);
      if (opts.caption) {
        var cap = document.createElement('p');
        cap.className = 'muted';
        cap.style.cssText = 'font-size:11.5px;margin:6px 0 0';
        cap.textContent = opts.caption;
        box.appendChild(cap);
      }
      var dark = (localStorage.getItem('theme') !== 'light');
      var txt = dark ? '#aeb6c4' : '#475569';
      var grid = dark ? 'rgba(128,138,160,0.12)' : 'rgba(128,138,160,0.18)';
      var bord = 'rgba(128,138,160,0.25)';
      var c0 = LightweightCharts.createChart(holder, {
        height: opts.height || 430, autoSize: true,
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: txt,
                  fontFamily: 'Inter, -apple-system, sans-serif' },
        grid: { vertLines: { color: grid }, horzLines: { color: grid } },
        rightPriceScale: { borderColor: bord },
        timeScale: { borderColor: bord, timeVisible: false },
        crosshair: { mode: (LightweightCharts.CrosshairMode ? LightweightCharts.CrosshairMode.Normal : 0) }
      });
      var t = chart.t, c = chart.c;
      var area = c0.addAreaSeries({ lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.28)',
        bottomColor: 'rgba(59,130,246,0.02)', lineWidth: 2, priceLineVisible: false });
      area.setData(t.map(function (x, i) { return { time: x, value: c[i] }; }));
      function sma(w) {
        var o = [], s = 0;
        for (var i = 0; i < c.length; i++) {
          s += c[i]; if (i >= w) s -= c[i - w];
          if (i >= w - 1) o.push({ time: t[i], value: +(s / w).toFixed(3) });
        }
        return o;
      }
      if (c.length >= 50) c0.addLineSeries({ color: '#f5a524', lineWidth: 1,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }).setData(sma(50));
      if (c.length >= 200) c0.addLineSeries({ color: '#ef5350', lineWidth: 1,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }).setData(sma(200));
      c0.timeScale().fitContent();
      box.__lwc = c0;
    });
  };

  // ---- render one chart into a box: TradingView when reachable, else local --
  // Reusable by the client-rendered single-stock pages (they call this inside
  // their per-ticker load()). symbol drives the TradingView widget; chart feeds
  // the local fallback.
  window.renderChart = function (box, symbol, chart, opts) {
    opts = opts || {};
    if (!box) return;
    window.__tvReady.then(function (ok) {
      if (ok && window.TradingView && symbol) {
        try {
          box.innerHTML = '<div id="' + (opts.tvId || 'tvchart') + '"></div>';
          new TradingView.widget({
            container_id: opts.tvId || 'tvchart', symbol: symbol,
            interval: 'D', theme: (localStorage.getItem('theme') === 'light' ? 'light' : 'dark'),
            style: '1', height: opts.height || 430, width: '100%',
            hide_side_toolbar: true, allow_symbol_change: true,
            studies: ['RSI@tv-basicstudies', 'MACD@tv-basicstudies']
          });
          return;
        } catch (e) { /* fall through to the local chart */ }
      }
      window.drawLocalChart(box, chart, opts);
    });
  };

  // ---- sector pages: declarative one-chart render ---------------------------
  // A server-rendered sector page sets window.__SECTOR_CHART = {symbol, chart,
  // height, studies, box?}; we pick TradingView when reachable, else the local
  // chart — no per-page glue code.
  function renderSector() {
    var cfg = window.__SECTOR_CHART;
    if (!cfg) return;
    var box = document.getElementById(cfg.box || 'tv_main');
    if (!box) return;
    window.renderChart(box, cfg.symbol, cfg.chart,
      { height: cfg.height || 440, tvId: box.id, caption: cfg.caption, nochart: cfg.nochart });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderSector);
  } else {
    renderSector();
  }
})();

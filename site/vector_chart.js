/* Bitcoin Vector — interactive "Risk Index vs Strategy" backtest chart.
 * Self-hosted TradingView Lightweight Charts v5 (the bespoke system from the stock
 * pages), purpose-built for the vector: BTC price (log) + strategy-equity overlay +
 * buy/sell markers, a two-tone Risk Index pane, and an allocation-regime pane —
 * with live variant switching, timeframe + log/linear toggles, and a crosshair
 * readout. Theme/lang-aware (rebuilds on themechange/langchange). Replaces the
 * server-rendered Plotly figure. window.VectorChart.mount(el, jsonUrl).
 */
(function () {
  "use strict";
  var LWC = window.LightweightCharts;
  if (!LWC) { console.error("vector_chart: LightweightCharts not loaded"); return; }

  // ---- injected CSS (minimal; the page owns the rest of the theme) ----------
  if (!document.getElementById("vchart-css")) {
    var s = document.createElement("style"); s.id = "vchart-css";
    s.textContent = [
      ".vchart-wrap{position:relative}",
      ".vchart-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}",
      ".vchart-chips{display:flex;gap:4px;background:var(--bg);border:1px solid var(--grid);border-radius:9px;padding:3px}",
      ".vchart-chip{font:inherit;font-size:12px;font-weight:600;cursor:pointer;border:none;background:transparent;color:var(--muted);padding:4px 10px;border-radius:7px;transition:background .15s,color .15s}",
      ".vchart-chip.on{background:var(--blue);color:#fff}",
      ".vchart-chip:hover:not(.on){color:var(--ink)}",
      ".vchart-canvas{width:100%;height:var(--vchart-h,480px)}",
      ".vchart-readout{display:flex;gap:8px 16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px;min-height:18px}",
      ".vchart-readout b{color:var(--ink);font-weight:700}",
      "@media(max-width:640px){.vchart-canvas{--vchart-h:420px}}"
    ].join("");
    document.head.appendChild(s);
  }

  function cssVar(n, fb) { var v = getComputedStyle(document.body).getPropertyValue(n); return (v && v.trim()) || fb; }
  function alpha(hex, a) {
    if (typeof hex !== "string" || hex.charAt(0) !== "#") return hex;
    var h = hex.slice(1); if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16); if (isNaN(n)) return hex;
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
  }
  function lang() {
    return document.documentElement.getAttribute("data-lang") || (localStorage.getItem("lang") === "zh" ? "zh" : "en");
  }
  function tt(en, zh) { return lang() === "zh" ? (zh || en) : en; }
  function palette() {
    return {
      bull: cssVar("--bull", "#285fff"), bear: cssVar("--bear", "#d14343"),
      blue: cssVar("--blue", "#285fff"), muted: cssVar("--muted", "#6f6f6f"),
      ink: cssVar("--ink", "#0b1733"), line: cssVar("--grid", "#eaecf0"),
      card: cssVar("--card", "#ffffff"), warn: cssVar("--warn", "#e0922e"),
      price: cssVar("--faint", "#9aa4b2"),
    };
  }
  var TF = { "1Y": 365, "2Y": 730, "5Y": 1825, "All": 1e9 };

  function Instance(el, data, opts) {
    this.el = el; this.data = data; this.opts = opts || {};
    this.variant = (data.variants && data.variants.indexOf("optimal") >= 0) ? "optimal" : (data.variants || ["optimal"])[0];
    this.tf = "2Y"; this.log = true;
    this.build();
    if (this.opts.onVariant) { try { this.opts.onVariant(this.variant); } catch (e) {} }
    var self = this;
    this._onTheme = function () { self.rebuild(true); };
    this._onLang = function () { self.rebuild(true); };
    window.addEventListener("themechange", this._onTheme);
    window.addEventListener("langchange", this._onLang);
  }

  Instance.prototype.slice = function () {
    // last N days for the active timeframe
    var d = this.data, n = d.dates.length, days = TF[this.tf] || 1e9;
    var start = Math.max(0, n - days);
    return { start: start, end: n };
  };

  Instance.prototype.build = function () {
    var d = this.data, v = this.variant, c = palette();
    this.el.innerHTML = "";
    // toolbar
    var bar = document.createElement("div"); bar.className = "vchart-bar";
    var self = this;
    function chipset(opts, active, on) {
      var box = document.createElement("div"); box.className = "vchart-chips";
      opts.forEach(function (o) {
        var b = document.createElement("button"); b.className = "vchart-chip" + (o[0] === active ? " on" : "");
        b.textContent = o[1]; b.onclick = function () { on(o[0]); };
        box.appendChild(b);
      });
      return box;
    }
    var vlabel = { conservative: tt("Conservative", "保守"), moderate: tt("Moderate", "稳健"),
                   aggressive: tt("Aggressive", "进取"), optimal: tt("Optimal", "最优") };
    bar.appendChild(chipset((d.variants || ["optimal"]).map(function (x) { return [x, vlabel[x] || x]; }),
      this.variant, function (x) { self.variant = x; if (self.opts.onVariant) { try { self.opts.onVariant(x); } catch (e) {} } self.rebuild(true); }));
    bar.appendChild(chipset(Object.keys(TF).map(function (x) { return [x, x]; }), this.tf,
      function (x) { self.tf = x; self.rebuild(false); }));   // timeframe changes the window -> refit
    bar.appendChild(chipset([["log", tt("Log", "对数")], ["lin", tt("Linear", "线性")]], this.log ? "log" : "lin",
      function (x) { self.log = (x === "log"); self.rebuild(true); }));   // rebuild refreshes the chip 'on' state + keeps the view
    this.el.appendChild(bar);
    this.bar = bar;

    var box = document.createElement("div"); box.className = "vchart-canvas";
    this.el.appendChild(box); this.plot = box;
    var read = document.createElement("div"); read.className = "vchart-readout"; read.textContent = tt("Hover the chart for point-in-time values.", "悬停查看实时数值。");
    this.el.appendChild(read); this.read = read;

    var W = box.clientWidth || 800, H = box.clientHeight || 480;
    var chart = LWC.createChart(box, {
      width: W, height: H,
      layout: { background: { type: "solid", color: c.card }, textColor: c.muted, fontFamily: "inherit", fontSize: 11, attributionLogo: false,
                panes: { separatorColor: c.line } },
      grid: { vertLines: { color: alpha(c.line, 0.6) }, horzLines: { color: alpha(c.line, 0.6) } },
      crosshair: { mode: LWC.CrosshairMode.Normal,
        vertLine: { color: c.muted, width: 1, style: 3, labelBackgroundColor: c.blue },
        horzLine: { color: c.muted, width: 1, style: 3, labelBackgroundColor: c.blue } },
      rightPriceScale: { borderColor: c.line, scaleMargins: { top: 0.06, bottom: 0.06 } },
      timeScale: { borderColor: c.line, rightOffset: 3, barSpacing: 6, minBarSpacing: 0.6 },
      handleScroll: { vertTouchDrag: false }
    });
    this.chart = chart; this.S = {};
    var sl = this.slice(), i0 = sl.start, i1 = sl.end;
    var dates = d.dates.slice(i0, i1);
    this.view = { dates: dates, i0: i0, i1: i1 };

    // ---- pane 0: BTC price (area) + strategy equity overlay + markers ----
    var price = chart.addSeries(LWC.AreaSeries, {
      lineColor: c.price, topColor: alpha(c.price, 0.22), bottomColor: alpha(c.price, 0.02),
      lineWidth: 2, priceFormat: { type: "price", precision: 0, minMove: 1 }, priceScaleId: "right"
    }, 0);
    price.setData(dates.map(function (t, k) { return { time: t, value: d.price[i0 + k] }; }));
    this.S.price = price;

    // strategy equity rescaled to the price axis at the window start (mirrors the Plotly overlay)
    var eq = (d.equity[v] || []);
    var scale = (eq[i0] ? d.price[i0] / eq[i0] : 1);
    var eqL = chart.addSeries(LWC.LineSeries, { color: c.blue, lineWidth: 2, priceLineVisible: false,
      lastValueVisible: false, priceScaleId: "right", crosshairMarkerVisible: true,
      priceFormat: { type: "price", precision: 0, minMove: 1 } }, 0);
    eqL.setData(dates.map(function (t, k) { return { time: t, value: +(eq[i0 + k] * scale).toFixed(2) }; }));
    this.S.eq = eqL; this.eqScale = scale;

    // buy/sell markers within the window
    var mk = (d.markers[v] || []).filter(function (m) { return m.t >= dates[0]; }).map(function (m) {
      return m.dir === "buy"
        ? { time: m.t, position: "belowBar", color: c.bull, shape: "arrowUp", text: "▲" }
        : { time: m.t, position: "aboveBar", color: c.bear, shape: "arrowDown", text: "▼" };
    });
    try { this.S.markers = LWC.createSeriesMarkers(price, mk); } catch (e) { /* markers optional */ }

    // ---- pane 1: Risk Index, two-tone split at 25 via a BaselineSeries (canonical v5
    // idiom — a single continuous line colored red above the 25 baseline, blue below;
    // no whitespace gaps at crossings the way two partitioned LineSeries would have) ----
    var risk = chart.addSeries(LWC.BaselineSeries, {
      baseValue: { type: "price", price: 25 },
      topLineColor: c.bear, topFillColor1: alpha(c.bear, 0.22), topFillColor2: alpha(c.bear, 0.04),
      bottomLineColor: c.blue, bottomFillColor1: alpha(c.blue, 0.04), bottomFillColor2: alpha(c.blue, 0.18),
      lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
      priceFormat: { type: "price", precision: 0, minMove: 1 }
    }, 1);
    risk.setData(dates.map(function (t, k) { var rv = d.risk[i0 + k]; return rv != null ? { time: t, value: rv } : { time: t }; }));
    try { risk.createPriceLine({ price: 25, color: c.muted, lineWidth: 1, lineStyle: 2, title: tt("risk 25", "风险 25") }); } catch (e) {}
    this.S.risk = risk;

    // ---- pane 2: allocation regime (stepped area, green) ----
    var alloc = (d.alloc[v] || []);
    var aS = chart.addSeries(LWC.AreaSeries, { lineColor: c.bull, topColor: alpha(c.bull, 0.35),
      bottomColor: alpha(c.bull, 0.04), lineWidth: 1.5, lineType: LWC.LineType.WithSteps,
      priceLineVisible: false, lastValueVisible: false,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 } }, 2);
    aS.setData(dates.map(function (t, k) { return { time: t, value: +(alloc[i0 + k]).toFixed(3) }; }));
    this.S.alloc = aS;

    try {
      var panes = chart.panes();
      panes.forEach(function (p, i) { p.setStretchFactor(i === 0 ? 4.6 : 1.2); });
    } catch (e) {}
    this.applyScale();
    // keep the user's pan/zoom across theme/lang/log/variant rebuilds; refit only when the
    // visible window changed (timeframe switch) or on first paint.
    var ts = chart.timeScale();
    if (this._keepRange) { try { ts.setVisibleLogicalRange(this._keepRange); } catch (e) {} this._keepRange = null; }
    else { try { ts.fitContent(); } catch (e) {} }

    // crosshair readout
    chart.subscribeCrosshairMove(function (param) { self.readout(param); });

    // SNAP to the container's real size. createChart may have run before layout settled
    // (so the canvas is at LWC's 300x150 default) and a ResizeObserver only fires on a
    // CHANGE — so we force a resize to the measured size on the next frame + a timeout
    // fallback (preview throttles rAF when the tab is hidden). Idempotent.
    function settle() {
      if (!self.chart) return;
      var w = box.clientWidth, h = box.clientHeight; if (!w || !h) return;
      try { self.chart.resize(w, h); void box.offsetWidth; } catch (e) {}   // resize + sync reflow
      try { self._keepRange ? null : self.chart.timeScale().fitContent(); } catch (e) {}
    }
    settle();
    try { requestAnimationFrame(settle); } catch (e) {}
    this._settleT = setTimeout(settle, 80);

    // responsive (later resizes) + below-the-fold first paint
    this._ro = new ResizeObserver(function () {
      var w = box.clientWidth, h = box.clientHeight; if (!w || !h) return;
      try { chart.resize(w, h); } catch (e) {}
    });
    this._ro.observe(box);
    this._io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting && self.chart) { settle(); } });
    });
    this._io.observe(box);
  };

  Instance.prototype.applyScale = function () {
    try { this.S.price.priceScale().applyOptions({ mode: this.log ? LWC.PriceScaleMode.Logarithmic : LWC.PriceScaleMode.Normal }); } catch (e) {}
  };
  Instance.prototype.readout = function (param) {
    if (!param || !param.time) { this.read.textContent = tt("Hover the chart for point-in-time values.", "悬停查看实时数值。"); return; }
    var d = this.data, v = this.variant, idx = -1, dt = param.time;
    for (var j = 0; j < this.view.dates.length; j++) { if (this.view.dates[j] === dt) { idx = this.view.i0 + j; break; } }
    if (idx < 0) return;
    var price = d.price[idx], risk = d.risk[idx], al = Math.round((d.alloc[v][idx] || 0) * 100);
    var eqx = (d.equity[v][idx] || 1), hodl = (d.hodl[idx] || 1), mult = hodl ? (eqx / hodl) : 1;
    this.read.innerHTML =
      "<span>" + (typeof dt === "string" ? dt : "") + "</span>" +
      "<span>" + tt("Price", "价格") + " <b>$" + (price || 0).toLocaleString() + "</b></span>" +
      "<span>" + tt("Risk", "风险") + " <b style='color:" + (risk >= 25 ? "var(--bear)" : "var(--blue)") + "'>" + (risk == null ? "—" : risk) + "</b></span>" +
      "<span>" + tt("Allocation", "仓位") + " <b style='color:" + (al >= 50 ? "var(--bull)" : "var(--bear)") + "'>" + al + "%</b></span>" +
      "<span>" + tt("vs HODL", "对比 HODL") + " <b style='color:" + (mult >= 1 ? "var(--bull)" : "var(--bear)") + "'>" + mult.toFixed(2) + "×</b></span>";
  };

  Instance.prototype.rebuild = function (keepView) {
    // preserve the user's pan/zoom when the visible window is unchanged (theme/lang/log/
    // variant); a timeframe switch passes keepView=false so build() refits.
    if (keepView && this.chart) {
      try { this._keepRange = this.chart.timeScale().getVisibleLogicalRange(); } catch (e) { this._keepRange = null; }
    } else { this._keepRange = null; }
    try { window.removeEventListener("themechange", this._onTheme); } catch (e) {}
    try { window.removeEventListener("langchange", this._onLang); } catch (e) {}
    if (this._ro) { try { this._ro.disconnect(); } catch (e) {} this._ro = null; }
    if (this._io) { try { this._io.disconnect(); } catch (e) {} this._io = null; }
    if (this._settleT) { clearTimeout(this._settleT); this._settleT = null; }
    if (this.chart) { try { this.chart.remove(); } catch (e) {} }
    this.build();
    var self = this;
    this._onTheme = function () { self.rebuild(true); };
    this._onLang = function () { self.rebuild(true); };
    window.addEventListener("themechange", this._onTheme);
    window.addEventListener("langchange", this._onLang);
  };

  window.VectorChart = {
    mount: function (el, jsonUrl, opts) {
      if (!el) return;
      fetch(jsonUrl).then(function (r) { return r.json(); }).then(function (data) {
        try { new Instance(el, data, opts); }
        catch (e) { console.error("vector_chart mount failed", e); el.innerHTML = "<div class='sub faint' style='padding:20px'>chart unavailable</div>"; }
      }).catch(function (e) { console.error("vector_chart fetch failed", e); });
    }
  };
})();

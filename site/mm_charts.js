/* ============================================================================
   mm_charts.js — Mastermind SVG charting engine (zero dependencies)
   ----------------------------------------------------------------------------
   A small, production-grade line/area/projection charting layer built to replace
   library-default charts with custom-grade visuals. Born for the Cycle
   Intelligence page; written as a reusable API any dashboard page can adopt.

       const chart = MMChart.create(el, spec);
       chart.focus('semis');   chart.update(spec);   chart.resize();   chart.destroy();

   Premium primitives baked in: eased path-draw on load, a tracking crosshair +
   rich tooltip, an explicit HISTORY (solid) vs PROJECTION (dashed + uncertainty
   cone) distinction, peak/trough/now glyphs, horizontal phase bands, smooth
   focus dim/highlight, responsive re-layout (ResizeObserver), and theme-reactivity
   (re-reads CSS vars + re-renders on `themechange` / `langchange`). Honors
   prefers-reduced-motion.

   SPEC
   ----
   {
     xDomain:[min,max], yDomain:[min,max],
     series:[{ id, color, label, hist:[{x,y,...}], proj:[{x,y}], cone:[{x,lo,hi}],
               markers:[{x,y,kind:'peak'|'trough'|'now', label, sub}],
               width, dim, focus, hidden }],
     bands:[{y0,y1,color,label}],           // horizontal phase shading
     guides:[{x,label,kind}],               // vertical lines (e.g. TODAY)
     xTicks:[..], yTicks:[{v,label}],
     padding:{t,r,b,l}, animate:true, crosshair:true,
     onHover:(series,pt)=>{}, onLeave:()=>{}, onPick:(id|null)=>{}, tip:(series,pt)=>html
                                            // onPick fires null on an empty-space click
                                            // while focused (a "miss") so callers can deselect
   }
   ========================================================================== */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var MONTHS_S = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function ymOf(x) { var y = Math.floor(x), m = Math.floor((x - y) * 12); return { y: y, m: m < 0 ? 0 : m > 11 ? 11 : m }; }

  function svg(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    return e;
  }
  function cssVar(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fb;
  }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function lerp(a, b, t) { return a + (b - a) * t; }

  function MMChart(container, spec) {
    this.el = container;
    this.spec = spec || {};
    this._focus = null;
    this._built = false;
    this._tip = null;
    this._ro = null;
    this._onTheme = this._render.bind(this, false);
    this._init();
  }

  MMChart.prototype._init = function () {
    var el = this.el;
    el.classList.add("mmc");
    el.style.position = el.style.position || "relative";
    this.svg = svg("svg", { class: "mmc-svg" });
    this.svg.style.display = "block";
    this.svg.style.width = "100%";
    el.appendChild(this.svg);

    // HTML tooltip (positioned over the svg)
    this._tip = document.createElement("div");
    this._tip.className = "mmc-tip";
    this._tip.style.cssText = "position:absolute;pointer-events:none;opacity:0;z-index:6;transition:opacity .14s ease;will-change:transform";
    el.appendChild(this._tip);

    var self = this;
    if (window.ResizeObserver) {
      this._ro = new ResizeObserver(function () { self._render(false); });
      this._ro.observe(el);
    } else {
      this._winResize = function () { self._render(false); };
      window.addEventListener("resize", this._winResize);
    }
    document.addEventListener("themechange", this._onTheme);
    document.addEventListener("langchange", this._onTheme);

    this._view = null;      // current x-domain (null = full spec.xDomain)
    this._fullX = null;     // the full / un-zoomed x-domain
    this._raf = null;       // rAF handle for batched re-render
    this._tw = null;        // rAF handle for the eased view tween
    this._dragging = false; // suppress hover while panning/brushing
    this._hidden = {};      // series id -> true (group filter)
    this._initZoom();
    this._render(true);
  };

  MMChart.prototype.update = function (spec) {
    if (spec) this.spec = spec;
    this._render(true);
    return this;
  };

  MMChart.prototype.resize = function () { this._render(false); return this; };

  MMChart.prototype.focus = function (id) {
    this._focus = id || null;
    // pure CSS opacity transition — no re-layout, so it stays buttery
    var groups = this.svg.querySelectorAll(".mmc-series");
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i], sid = g.getAttribute("data-id");
      if (!this._focus) { g.classList.remove("is-dim", "is-focus"); }
      else if (sid === this._focus) { g.classList.remove("is-dim"); g.classList.add("is-focus"); g.parentNode.appendChild(g); }
      else { g.classList.remove("is-focus"); g.classList.add("is-dim"); }
    }
    this.el.classList.toggle("mmc-has-focus", !!this._focus);
    return this;
  };

  MMChart.prototype.destroy = function () {
    if (this._ro) this._ro.disconnect();
    if (this._winResize) window.removeEventListener("resize", this._winResize);
    if (this._raf) cancelAnimationFrame(this._raf);
    if (this._tw) cancelAnimationFrame(this._tw);
    if (this._zoomCleanup) this._zoomCleanup();
    document.removeEventListener("themechange", this._onTheme);
    document.removeEventListener("langchange", this._onTheme);
    if (this.el) this.el.innerHTML = "";
  };

  MMChart.prototype._render = function (animate) {
    var s = this.spec, el = this.el;
    var W = el.clientWidth || 600;
    var H = el.clientHeight || (parseInt(el.getAttribute("data-h"), 10) || 360);
    if (!W) return;
    var dpr = Math.max(1, window.devicePixelRatio || 1);
    this.svg.setAttribute("width", W);
    this.svg.setAttribute("height", H);
    this.svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);

    var pad = s.padding || { t: 14, r: 16, b: 26, l: 30 };
    var x0 = pad.l, x1 = W - pad.r, y0 = pad.t, y1 = H - pad.b;
    this._fullX = s.xDomain || [0, 1];
    if (!this._view) this._view = this._fullX.slice();
    var xd = this._view, yd = s.yDomain || [0, 100];
    var SX = function (x) { return x0 + (x - xd[0]) / (xd[1] - xd[0]) * (x1 - x0); };
    var SY = function (y) { return y1 - (y - yd[0]) / (yd[1] - yd[0]) * (y1 - y0); };
    this._SX = SX; this._SY = SY; this._plot = { x0: x0, x1: x1, y0: y0, y1: y1 };
    this._invX = function (px) { return xd[0] + (clamp(px, x0, x1) - x0) / (x1 - x0) * (xd[1] - xd[0]); };

    var cText = cssVar("--muted", "#8b93a1");
    var cFaint = cssVar("--line", "#2a2f3a");
    var cInk = cssVar("--text", "#d7dce3");

    var defs = svg("defs"); this.svg.appendChild(defs);
    var doAnim = animate && !reduceMotion && s.animate !== false;

    // clip the plotting area so series reaching outside the calendar window
    // (e.g. 1970s turning points) never paint over the axis gutters
    this._clipId = this._clipId || ("mmc-clip-" + Math.round(SX(xd[1]) + (x1 - x0) + (y1 - y0)) + "-" + (s.series ? s.series.length : 0));
    var clip = svg("clipPath", { id: this._clipId });
    clip.appendChild(svg("rect", { x: x0, y: y0 - 2, width: x1 - x0, height: (y1 - y0) + 4 }));
    defs.appendChild(clip);

    /* ---- horizontal phase bands -------------------------------------------- */
    if (s.bands) {
      var bandsG = svg("g", { class: "mmc-bands" });
      s.bands.forEach(function (b) {
        var yA = SY(b.y1), yB = SY(b.y0);
        var r = svg("rect", { x: x0, y: yA, width: x1 - x0, height: Math.max(0, yB - yA), fill: b.color || cFaint, opacity: b.opacity != null ? b.opacity : 0.06 });
        bandsG.appendChild(r);
        if (b.label) {
          var tl = svg("text", { x: x1 - 6, y: (yA + yB) / 2 + 3, "text-anchor": "end", class: "mmc-band-lab", fill: cText, "font-size": 10 });
          tl.textContent = b.label; bandsG.appendChild(tl);
        }
      });
      this.svg.appendChild(bandsG);
    }

    /* ---- vertical convergence zones (projected synchronized turns) --------- */
    if (s.vbands && s.vbands.length) {
      var vbG = svg("g", { class: "mmc-vbands" });
      s.vbands.forEach(function (vb) {
        var ax = SX(vb.x0), bx = SX(vb.x1);
        if (bx < x0 || ax > x1) return;
        var ca = clamp(ax, x0, x1), cb = clamp(bx, x0, x1);
        vbG.appendChild(svg("rect", { x: ca, y: y0, width: Math.max(1.5, cb - ca), height: y1 - y0, fill: vb.color || cInk, opacity: vb.opacity != null ? vb.opacity : 0.09, class: "mmc-vband" }));
        if (vb.cx != null) { var cxp = SX(vb.cx); if (cxp >= x0 && cxp <= x1) vbG.appendChild(svg("line", { x1: cxp, y1: y0, x2: cxp, y2: y1, stroke: vb.color || cInk, "stroke-width": 1, "stroke-dasharray": "2 4", opacity: 0.5 })); }
      });
      this.svg.appendChild(vbG);
    }

    /* ---- y gridlines / ticks ----------------------------------------------- */
    var gridG = svg("g", { class: "mmc-grid" });
    (s.yTicks || []).forEach(function (t) {
      var yy = SY(t.v);
      gridG.appendChild(svg("line", { x1: x0, y1: yy, x2: x1, y2: yy, stroke: cFaint, "stroke-width": 1, opacity: 0.5 }));
      if (t.label) {
        var lab = svg("text", { x: x0 - 6, y: yy + 3, "text-anchor": "end", fill: cText, "font-size": 10 });
        lab.textContent = t.label; gridG.appendChild(lab);
      }
    });
    this.svg.appendChild(gridG);

    /* ---- x ticks (adaptive: densify to quarters as you zoom in) ------------- */
    var axG = svg("g", { class: "mmc-axis" });
    var xticks = (s.zoom !== false) ? this._timeTicks(xd)
      : (s.xTicks || []).map(function (n) { return { x: n, label: String(Math.round(n)) }; });
    xticks.forEach(function (t) {
      if (t.x < xd[0] - 1e-6 || t.x > xd[1] + 1e-6) return;
      var xx = SX(t.x);
      axG.appendChild(svg("line", { x1: xx, y1: y1, x2: xx, y2: y1 + (t.minor ? 3 : 4), stroke: cFaint, opacity: t.minor ? 0.55 : 1 }));
      var lab = svg("text", { x: xx, y: y1 + 16, "text-anchor": "middle", fill: cText, "font-size": t.minor ? 9 : 10, opacity: t.minor ? 0.68 : 1 });
      lab.textContent = t.label; axG.appendChild(lab);
    });
    this.svg.appendChild(axG);

    /* ---- vertical guides (TODAY) ------------------------------------------- */
    (s.guides || []).forEach(function (g) {
      var xx = SX(g.x);
      var gl = svg("line", { x1: xx, y1: y0, x2: xx, y2: y1, stroke: cInk, "stroke-width": 1, "stroke-dasharray": "2 4", opacity: 0.55, class: "mmc-guide" });
      this.svg.appendChild(gl);
      if (g.label) {
        var pill = svg("g", { class: "mmc-guide-lab" });
        var tx = svg("text", { x: xx, y: y0 - 3, "text-anchor": "middle", fill: cInk, "font-size": 9.5, "font-weight": 700, "letter-spacing": ".08em" });
        tx.textContent = g.label; pill.appendChild(tx);
        this.svg.appendChild(pill);
      }
    }, this);

    /* ---- series ------------------------------------------------------------ */
    var seriesG = svg("g", { class: "mmc-allseries", "clip-path": "url(#" + this._clipId + ")" });
    this.svg.appendChild(seriesG);
    var hiddenMap = this._hidden || {}, focusId = this._focus;
    // a focused series always renders, even if the group/phase filter hid it
    var series = (s.series || []).filter(function (d) { return (!d.hidden && !hiddenMap[d.id]) || d.id === focusId; });
    var self = this;

    function path(points) {
      if (!points.length) return "";
      // Catmull-Rom → cubic bezier for a smooth, faithful curve through the points
      var p = points, d = "M" + SX(p[0].x).toFixed(2) + "," + SY(p[0].y).toFixed(2);
      for (var i = 0; i < p.length - 1; i++) {
        var p0 = p[i - 1] || p[i], p1 = p[i], p2 = p[i + 1], p3 = p[i + 2] || p2;
        var c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6;
        var c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6;
        d += "C" + SX(c1x).toFixed(2) + "," + SY(c1y).toFixed(2) + " " +
             SX(c2x).toFixed(2) + "," + SY(c2y).toFixed(2) + " " +
             SX(p2.x).toFixed(2) + "," + SY(p2.y).toFixed(2);
      }
      return d;
    }

    series.forEach(function (d, idx) {
      var g = svg("g", { class: "mmc-series", "data-id": d.id });
      g.style.setProperty("--c", d.color || cInk);
      if (self._focus) { if (d.id === self._focus) g.classList.add("is-focus"); else g.classList.add("is-dim"); }
      var w = d.width || 2;

      // uncertainty cone (projection)
      if (d.cone && d.cone.length > 1) {
        var up = "M", dn = "";
        d.cone.forEach(function (c, i) { up += (i ? "L" : "") + SX(c.x).toFixed(2) + "," + SY(c.hi).toFixed(2) + " "; });
        for (var j = d.cone.length - 1; j >= 0; j--) { dn += "L" + SX(d.cone[j].x).toFixed(2) + "," + SY(d.cone[j].lo).toFixed(2) + " "; }
        var cone = svg("path", { d: up + dn + "Z", class: "mmc-cone", fill: d.color || cInk, opacity: 0.12, stroke: "none" });
        g.appendChild(cone);
      }

      // area fill under the historical line (additive; e.g. the Odds Desk price
      // chart). d.fill = paint under hist down to the plot floor; never stroked.
      if (d.fill && d.hist && d.hist.length > 1) {
        var fEnd = SX(d.hist[d.hist.length - 1].x).toFixed(2), fStart = SX(d.hist[0].x).toFixed(2);
        g.appendChild(svg("path", { d: path(d.hist) + "L" + fEnd + "," + y1 + "L" + fStart + "," + y1 + "Z",
          class: "mmc-area", fill: d.fill, stroke: "none", opacity: d.fillOpacity != null ? d.fillOpacity : 1 }));
      }

      // historical line (solid)
      if (d.hist && d.hist.length) {
        var hp = svg("path", { d: path(d.hist), class: "mmc-hist", fill: "none", stroke: d.color || cInk, "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round" });
        g.appendChild(hp);
        if (doAnim) {
          try {
            var len = hp.getTotalLength();
            hp.style.strokeDasharray = len; hp.style.strokeDashoffset = len;
            hp.style.transition = "stroke-dashoffset 1.05s cubic-bezier(.22,.61,.36,1) " + (idx * 0.035).toFixed(2) + "s";
            requestAnimationFrame(function () { requestAnimationFrame(function () { hp.style.strokeDashoffset = 0; }); });
          } catch (e) {}
        }
      }

      // projection line (dashed) — bridge from last hist point
      if (d.proj && d.proj.length) {
        var bridge = (d.hist && d.hist.length) ? [d.hist[d.hist.length - 1]].concat(d.proj) : d.proj;
        var pp = svg("path", { d: path(bridge), class: "mmc-proj", fill: "none", stroke: d.color || cInk, "stroke-width": w, "stroke-linecap": "round", "stroke-dasharray": "1 5", opacity: 0.85 });
        g.appendChild(pp);
        if (doAnim) { pp.style.opacity = 0; pp.style.transition = "opacity .5s ease " + (0.6 + idx * 0.02).toFixed(2) + "s"; requestAnimationFrame(function () { requestAnimationFrame(function () { pp.style.opacity = 0.85; }); }); }
      }

      // markers
      (d.markers || []).forEach(function (m) {
        var mx = SX(m.x), my = SY(m.y), mg = svg("g", { class: "mmc-mk mmc-mk-" + m.kind });
        if (m.kind === "now") {
          mg.appendChild(svg("circle", { cx: mx, cy: my, r: 7, fill: "none", stroke: d.color || cInk, "stroke-width": 1.5, opacity: 0.5, class: "mmc-now-ring" }));
          mg.appendChild(svg("circle", { cx: mx, cy: my, r: 3.6, fill: d.color || cInk, stroke: cssVar("--panel", "#181b21"), "stroke-width": 1.5 }));
        } else if (m.kind === "peak") {
          mg.appendChild(svg("path", { d: "M" + mx + "," + (my - 4.5) + "L" + (mx + 4) + "," + (my + 3.5) + "L" + (mx - 4) + "," + (my + 3.5) + "Z", fill: d.color || cInk, stroke: cssVar("--panel", "#181b21"), "stroke-width": 0.8 }));
        } else if (m.kind === "trough") {
          mg.appendChild(svg("path", { d: "M" + mx + "," + (my + 4.5) + "L" + (mx + 4) + "," + (my - 3.5) + "L" + (mx - 4) + "," + (my - 3.5) + "Z", fill: d.color || cInk, stroke: cssVar("--panel", "#181b21"), "stroke-width": 0.8 }));
        } else if (m.kind === "dot") {
          mg.appendChild(svg("circle", { cx: mx, cy: my, r: m.r || 3.5, fill: d.color || cInk, stroke: cssVar("--panel", "#181b21"), "stroke-width": 1 }));
        }
        // only inline-animate the "now" dot; peak/trough visibility is CSS-driven
        // (shown for the focused series) so the 15-line overlay stays clean.
        if (doAnim && m.kind === "now") { mg.style.opacity = 0; mg.style.transition = "opacity .4s ease " + (0.5 + idx * 0.03).toFixed(2) + "s"; requestAnimationFrame(function () { requestAnimationFrame(function () { mg.style.opacity = 1; }); }); }
        g.appendChild(mg);
      });

      seriesG.appendChild(g);
    });

    /* ---- hover layer (crosshair + nearest-series pick) --------------------- */
    if (s.crosshair !== false && series.length) {
      var hover = svg("g", { class: "mmc-hover", opacity: 0 });
      var cross = svg("line", { x1: 0, y1: y0, x2: 0, y2: y1, stroke: cInk, "stroke-width": 1, opacity: 0.25 });
      var dot = svg("circle", { r: 4.5, fill: "none", "stroke-width": 2 });
      // x-axis date pill — month/year, shown only while hovering
      var xlab = svg("g", { class: "mmc-xlabel" });
      var xlabBg = svg("rect", { rx: 4, height: 15, y: y1 + 4, fill: cssVar("--panel", "#181b21"), stroke: cFaint, "stroke-width": 1 });
      var xlabTx = svg("text", { y: y1 + 14.5, "text-anchor": "middle", "font-size": 10, "font-weight": 600, fill: cInk });
      xlab.appendChild(xlabBg); xlab.appendChild(xlabTx);
      hover.appendChild(cross); hover.appendChild(dot); hover.appendChild(xlab);
      this.svg.appendChild(hover);

      var capture = svg("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: "transparent", style: "cursor:crosshair" });
      this.svg.appendChild(capture);

      var interp = function (pts, x) {
        if (!pts || !pts.length) return null;
        if (x <= pts[0].x) return pts[0];
        for (var i = 0; i < pts.length - 1; i++) {
          if (x >= pts[i].x && x <= pts[i + 1].x) {
            var t = (x - pts[i].x) / (pts[i + 1].x - pts[i].x || 1);
            return { x: x, y: lerp(pts[i].y, pts[i + 1].y, t), a: pts[i], b: pts[i + 1] };
          }
        }
        return pts[pts.length - 1];
      };

      var onMove = function (ev) {
        if (self._dragging) return;   // suppress hover while panning / brushing
        if (ev.touches && ev.touches.length > 1) return;  // pinch, not a hover
        var rect = self.svg.getBoundingClientRect();
        var px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
        var py = (ev.touches ? ev.touches[0].clientY : ev.clientY) - rect.top;
        var xVal = xd[0] + (clamp(px, x0, x1) - x0) / (x1 - x0) * (xd[1] - xd[0]);
        // candidate series: focused one if set, else nearest by y
        var best = null, bestDist = 1e9;
        series.forEach(function (d) {
          if (self._focus && d.id !== self._focus) return;
          var full = (d.hist || []).concat(d.proj || []);
          var pt = interp(full, xVal);
          if (!pt) return;
          var sy = SY(pt.y), dist = Math.abs(sy - py);
          if (dist < bestDist) { bestDist = dist; best = { d: d, pt: pt }; }
        });
        if (!best) return;
        var cx = SX(xVal), cy = SY(best.pt.y);
        hover.setAttribute("opacity", 1);
        cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
        dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
        dot.setAttribute("stroke", best.d.color || cInk);
        dot.setAttribute("fill", cssVar("--panel", "#181b21"));
        // x-axis date pill (month precision; localized)
        var ym = ymOf(xVal);
        var ds = document.documentElement.getAttribute("data-lang") === "zh" ? (ym.y + "年" + (ym.m + 1) + "月") : (MONTHS_S[ym.m] + " " + ym.y);
        xlabTx.textContent = ds;
        var dcx = clamp(cx, x0 + 24, x1 - 24), dw = ds.length * 5.7 + 12;
        xlabTx.setAttribute("x", dcx);
        xlabBg.setAttribute("x", dcx - dw / 2); xlabBg.setAttribute("width", dw);
        if (s.onHover) s.onHover(best.d, best.pt, xVal);
        // tooltip
        var html = s.tip ? s.tip(best.d, best.pt, xVal) : (best.d.label || best.d.id);
        self._tip.innerHTML = html;
        self._tip.style.opacity = 1;
        var tw = self._tip.offsetWidth, th = self._tip.offsetHeight;
        var tx = clamp(cx + 14, 4, W - tw - 4), ty = clamp(cy - th - 12, 4, H - th - 4);
        self._tip.style.transform = "translate(" + tx + "px," + ty + "px)";
      };
      var onLeave = function () { hover.setAttribute("opacity", 0); self._tip.style.opacity = 0; if (s.onLeave) s.onLeave(); };
      capture.addEventListener("mousemove", onMove);
      capture.addEventListener("mouseleave", onLeave);
      capture.addEventListener("touchstart", onMove, { passive: true });
      capture.addEventListener("touchmove", onMove, { passive: true });
      capture.addEventListener("touchend", onLeave);
      if (s.onPick) capture.addEventListener("click", function (ev) {
        onMove(ev);
        // pick nearest series at click
        var rect = self.svg.getBoundingClientRect();
        var px = ev.clientX - rect.left, py = ev.clientY - rect.top;
        var xVal = xd[0] + (clamp(px, x0, x1) - x0) / (x1 - x0) * (xd[1] - xd[0]);
        var best = null, bestDist = 1e9;
        series.forEach(function (d) {
          var full = (d.hist || []).concat(d.proj || []);
          var pt = interp(full, xVal); if (!pt) return;
          var dist = Math.abs(SY(pt.y) - py);
          if (dist < bestDist) { bestDist = dist; best = d; }
        });
        if (best && bestDist < 40) s.onPick(best.id);
        // clicked empty space (no line within reach) while a series is focused →
        // signal a "miss" so the page can clear the focus and un-dim every line.
        else if (self._focus) s.onPick(null);
      });
    }

    /* ---- convergence-zone labels (drawn above the series) ----------------- */
    if (s.vbands && s.vbands.length) {
      var vlG = svg("g", { class: "mmc-vlabels" });
      s.vbands.forEach(function (vb) {
        if (!vb.label) return;
        var cxp = SX(vb.cx != null ? vb.cx : (vb.x0 + vb.x1) / 2);
        if (cxp < x0 - 4 || cxp > x1 + 4) return;
        cxp = clamp(cxp, x0 + 34, x1 - 34);
        var ww = 0, ll = String(vb.label);
        for (var ci = 0; ci < ll.length; ci++) ww += ll.charCodeAt(ci) > 0x2e80 ? 11 : 6.2;
        ww += 16;
        var ly = y0 + (vb.labelY != null ? vb.labelY : 11);
        var g = svg("g", { class: "mmc-vlabel", style: "cursor:help" });
        g.appendChild(svg("rect", { x: cxp - ww / 2, y: ly - 11, rx: 7, width: ww, height: 15, fill: cssVar("--panel", "#181b21"), stroke: vb.color || cInk, "stroke-width": 1, opacity: 0.97 }));
        var tx = svg("text", { x: cxp, y: ly, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: vb.color || cInk });
        tx.textContent = vb.label; g.appendChild(tx);
        if (vb.title) { var ti = svg("title"); ti.textContent = vb.title; g.appendChild(ti); }
        vlG.appendChild(g);
      });
      this.svg.appendChild(vlG);
    }

    this._built = true;
  };

  /* ---- zoom / pan -------------------------------------------------------- */
  // adaptive time ticks: years when wide, +quarters once you zoom past ~2.6yr
  MMChart.prototype._timeTicks = function (d) {
    var lo = d[0], hi = d[1], span = hi - lo, out = [];
    var yy = function (y) { return "’" + String(y).slice(2); };
    var push = function (x, label, minor) { out.push({ x: x, label: label, minor: !!minor }); };
    var a;
    if (span > 11) { for (a = Math.ceil(lo / 5) * 5; a <= hi; a += 5) push(a, String(a)); }
    else if (span > 5) { for (a = Math.ceil(lo / 2) * 2; a <= hi; a += 2) push(a, String(a)); }
    else if (span > 2.6) { for (a = Math.ceil(lo); a <= hi; a++) push(a, String(a)); }
    else if (span > 1.3) {
      for (var y = Math.floor(lo); y <= Math.ceil(hi); y++) {
        for (var q = 0; q < 4; q++) { var x = y + q * 0.25; if (q === 0) push(x, String(y)); else push(x, "Q" + (q + 1) + " " + yy(y), true); }
      }
    } else {
      var zhL = document.documentElement.getAttribute("data-lang") === "zh";
      for (var yr = Math.floor(lo); yr <= Math.ceil(hi); yr++) {
        for (var mo = 0; mo < 12; mo++) { var mx = yr + mo / 12; if (mo === 0) push(mx, String(yr)); else push(mx, zhL ? (mo + 1) + "月" : MONTHS_S[mo], true); }
      }
    }
    return out;
  };

  MMChart.prototype._requestRender = function () {
    var self = this;
    if (self._raf) return;
    self._raf = requestAnimationFrame(function () { self._raf = null; self._render(false); });
  };

  MMChart.prototype.getView = function () { return (this._view || this._fullX || this.spec.xDomain).slice(); };

  // hide/show a set of series by id (used by the group filter) without re-animating
  MMChart.prototype.setHidden = function (map) { this._hidden = map || {}; this._requestRender(); return this; };

  MMChart.prototype._emitZoom = function () {
    var full = this._fullX || this.spec.xDomain, v = this._view || full;
    var zoomed = !!(v && full && (v[0] > full[0] + 1e-3 || v[1] < full[1] - 1e-3));
    if (this.spec.onZoom) this.spec.onZoom(v.slice(), zoomed);
  };

  MMChart.prototype.setView = function (domain, animate) {
    var full = this._fullX || this.spec.xDomain || [0, 1];
    var minSpan = Math.min(0.5, (full[1] - full[0]) / 40);
    var lo = domain[0], hi = domain[1];
    if (hi - lo < minSpan) { var mid = (lo + hi) / 2; lo = mid - minSpan / 2; hi = mid + minSpan / 2; }
    if (lo < full[0]) { hi += full[0] - lo; lo = full[0]; }
    if (hi > full[1]) { lo -= hi - full[1]; hi = full[1]; }
    lo = Math.max(lo, full[0]); hi = Math.min(hi, full[1]);
    if (animate) { this._tweenView([lo, hi]); }
    else { this._view = [lo, hi]; this._requestRender(); this._emitZoom(); }
    return this;
  };

  MMChart.prototype.resetZoom = function () { this.setView((this._fullX || this.spec.xDomain).slice(), true); return this; };

  MMChart.prototype._tweenView = function (target) {
    var self = this, from = (this._view || this._fullX).slice(), t0 = performance.now(), dur = 360;
    var ease = function (t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
    if (self._tw) cancelAnimationFrame(self._tw);
    var step = function (now) {
      var k = Math.min(1, (now - t0) / dur), e = ease(k);
      self._view = [from[0] + (target[0] - from[0]) * e, from[1] + (target[1] - from[1]) * e];
      self._render(false); self._emitZoom();
      self._tw = k < 1 ? requestAnimationFrame(step) : null;
    };
    self._tw = requestAnimationFrame(step);
  };

  MMChart.prototype._initZoom = function () {
    if (this.spec.zoom === false) return;
    var self = this, sv = this.svg;
    // On phones, declare vertical-scroll intent: a vertical swipe over the chart now
    // scrolls the PAGE (was touch-action:none, which trapped the page scroll on a
    // 380px-tall chart). Horizontal-dominant drags still pan the chart; two-finger
    // pinch/pan is unaffected. Above 880px (desktop, US + China) the original
    // full-capture behaviour is kept verbatim.
    var mobilePanY = (typeof window !== "undefined" && window.innerWidth <= 880);
    sv.style.touchAction = mobilePanY ? "pan-y" : "none";
    var down = false, brush = false, startPx = 0, startView = null, brushRect = null;

    var onWheel = function (e) {
      e.preventDefault();
      var r = sv.getBoundingClientRect(), px = e.clientX - r.left;
      var v = self._view || self._fullX, span = v[1] - v[0], full = self._fullX;
      var cx = self._invX ? self._invX(px) : (v[0] + v[1]) / 2;
      var ratio = (cx - v[0]) / (span || 1);
      var f = Math.exp((e.deltaY || 0) * 0.0016);
      var minSpan = Math.min(0.5, (full[1] - full[0]) / 40);
      var ns = Math.max(minSpan, Math.min(full[1] - full[0], span * f));
      self.setView([cx - ratio * ns, cx - ratio * ns + ns], false);
    };
    var onDown = function (e) {
      if (e.button !== 0) return;
      down = true; self._dragging = true; startPx = e.clientX; startView = (self._view || self._fullX).slice();
      brush = e.shiftKey; sv.style.cursor = brush ? "ew-resize" : "grabbing"; e.preventDefault();
    };
    var onWinMove = function (e) {
      if (!down) return;
      var r = sv.getBoundingClientRect(), p = self._plot;
      if (brush) {
        var a = clamp(startPx - r.left, p.x0, p.x1), b = clamp(e.clientX - r.left, p.x0, p.x1);
        if (!brushRect) { brushRect = svg("rect", { class: "mmc-brush", fill: cssVar("--link", "#7aa7e0"), opacity: 0.16, y: p.y0, height: p.y1 - p.y0 }); sv.appendChild(brushRect); }
        brushRect.setAttribute("x", Math.min(a, b)); brushRect.setAttribute("width", Math.abs(b - a));
      } else {
        var span = startView[1] - startView[0];
        var dxUnits = (e.clientX - startPx) / (p.x1 - p.x0) * span;
        self.setView([startView[0] - dxUnits, startView[1] - dxUnits], false);
      }
    };
    var onWinUp = function (e) {
      if (!down) return; down = false; self._dragging = false; sv.style.cursor = "";
      if (brush && brushRect) {
        var r = sv.getBoundingClientRect();
        var a = self._invX(clamp(startPx - r.left, self._plot.x0, self._plot.x1));
        var b = self._invX(clamp(e.clientX - r.left, self._plot.x0, self._plot.x1));
        sv.removeChild(brushRect); brushRect = null;
        if (Math.abs(b - a) > 0.12) self.setView([Math.min(a, b), Math.max(a, b)], true);
      }
      brush = false;
    };
    var onDbl = function (e) { e.preventDefault(); self.resetZoom(); };

    // touch: 1-finger pan, 2-finger pinch
    var t = null;
    var onTStart = function (e) {
      if (e.touches.length === 1) t = { mode: "pan", px: e.touches[0].clientX, py: e.touches[0].clientY, axis: null, view: (self._view || self._fullX).slice() };
      else if (e.touches.length === 2) {
        var a = e.touches[0], b = e.touches[1];
        t = { mode: "pinch", dist: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY), midPx: (a.clientX + b.clientX) / 2, view: (self._view || self._fullX).slice() };
        // Claim the pinch from the browser immediately so iOS/Android don't
        // take it for viewport-zoom before the chart sees the first move event.
        // passive:false (see addEventListener below) is required to call this.
        if (e.cancelable) e.preventDefault();
      }
    };
    var onTMove = function (e) {
      if (!t) return; var r = sv.getBoundingClientRect(), p = self._plot;
      if (t.mode === "pan" && e.touches.length === 1) {
        // phone: a vertical-dominant swipe should scroll the PAGE, not pan the chart.
        // Lock the axis once the finger has moved far enough to disambiguate, then bail
        // (return) on vertical so the gesture bubbles to native scroll (listener is
        // passive:false but we deliberately skip preventDefault for vertical, so it
        // still bubbles to the browser's native scroll).
        if (window.innerWidth <= 880) {
          if (t.axis === null) {
            var adx = Math.abs(e.touches[0].clientX - t.px), ady = Math.abs(e.touches[0].clientY - t.py);
            if (adx < 6 && ady < 6) return;
            t.axis = ady > adx ? "v" : "h";
          }
          if (t.axis === "v") return; // let the page scroll — no preventDefault
          // Horizontal-locked: stop simultaneous micro-scroll so the pan tracks 1:1.
          if (e.cancelable) e.preventDefault();
        }
        var span = t.view[1] - t.view[0], dxUnits = (e.touches[0].clientX - t.px) / (p.x1 - p.x0) * span;
        self.setView([t.view[0] - dxUnits, t.view[1] - dxUnits], false);
      } else if (t.mode === "pinch" && e.touches.length === 2) {
        // Keep the pinch owned by the chart throughout; passive:false allows this.
        if (e.cancelable) e.preventDefault();
        var a = e.touches[0], b = e.touches[1], d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        var span0 = t.view[1] - t.view[0], full = self._fullX;
        var cx = t.view[0] + (clamp(t.midPx - r.left, p.x0, p.x1) - p.x0) / (p.x1 - p.x0) * span0;
        var ratio = (cx - t.view[0]) / (span0 || 1), minSpan = Math.min(0.5, (full[1] - full[0]) / 40);
        var ns = Math.max(minSpan, Math.min(full[1] - full[0], span0 * (t.dist / (d || 1))));
        self.setView([cx - ratio * ns, cx - ratio * ns + ns], false);
      }
    };
    var onTEnd = function (e) {
      if (e.touches.length === 0) { t = null; self._dragging = false; return; }
      // Pinch → pan handoff: lifting one finger after a pinch would otherwise
      // leave a dead gesture. Re-seed as a horizontal-locked pan from the
      // remaining finger so the user can slide without restarting the gesture.
      if (e.touches.length === 1 && t && t.mode === "pinch") {
        t = { mode: "pan", px: e.touches[0].clientX, py: e.touches[0].clientY, axis: "h", view: (self._view || self._fullX).slice() };
      }
    };
    // touchcancel: browser stole the gesture (e.g. notification centre, iOS
    // scroll takeover). Reset state so the next gesture starts clean.
    var onTCancel = function () { t = null; self._dragging = false; };

    sv.addEventListener("wheel", onWheel, { passive: false });
    sv.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onWinMove);
    window.addEventListener("mouseup", onWinUp);
    sv.addEventListener("dblclick", onDbl);
    // passive:false is required so preventDefault() inside handlers can claim
    // pinch and horizontal-pan gestures before the browser's scroll/zoom wins.
    sv.addEventListener("touchstart", onTStart, { passive: false });
    sv.addEventListener("touchmove", onTMove, { passive: false });
    sv.addEventListener("touchend", onTEnd);
    sv.addEventListener("touchcancel", onTCancel);
    this._zoomCleanup = function () { window.removeEventListener("mousemove", onWinMove); window.removeEventListener("mouseup", onWinUp); };
  };

  /* simple year-tick helper exposed for callers */
  MMChart.niceYearTicks = function (lo, hi, step) {
    step = step || 5; var out = [], start = Math.ceil(lo / step) * step;
    for (var y = start; y <= hi; y += step) out.push(y);
    return out;
  };

  window.MMChart = {
    create: function (el, spec) { return new MMChart(el, spec); },
    niceYearTicks: MMChart.niceYearTicks
  };
})();

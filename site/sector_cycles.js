/* ============================================================================
   sector_cycles.js — Sector Cycle Intelligence · orchestration
   ----------------------------------------------------------------------------
   Reads window.SECTOR_CYCLES (engine/sector_cycles.py output) + window.SECTOR_NARR
   (researched leg narratives) and composes mm_charts.js into:
     • a hero overlay of all 11 sector ETFs — REAL price (rebased, log/linear) or a
       0–100 cycle-position oscillator, toggled live;
     • per-sector focus with a clickable peak→trough LEG timeline whose narratives
       explain each move, plus narrative bands on the chart;
     • phase-filter chips (topping/expanding/rolling/bottoming/recovering), a
       leadership rail, and scorecards.
   Reuses cycle.css (.cyc-*) for the shared design language; net-new chrome is in
   sector_cycles.css (.sc-*).
   ========================================================================== */
(function () {
  "use strict";

  var DATA = window.SECTOR_CYCLES, NARR = window.SECTOR_NARR || {};
  if (!DATA || !DATA.sectors) return;
  var META = DATA.meta, PHASES = DATA.phases, SECTORS = DATA.sectors;
  var BASKETS = DATA.baskets || [];
  var ALL = SECTORS.concat(BASKETS);            // one chart space; baskets hidden until selected
  var basketShown = {};                          // basket id -> on the chart? (default false)
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /* ---- i18n (EN default, 中文 when <html data-lang="zh">) ----------------- */
  function curLang() { return document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"; }
  function L(en, zh) { return curLang() === "zh" ? (zh || en) : en; }

  var byId = {};
  ALL.forEach(function (s) { byId[s.id] = s; });

  /* ---- view state -------------------------------------------------------- */
  var state = { mode: "price", scale: "log", focus: null };

  /* ---- small helpers ----------------------------------------------------- */
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function log10(v) { return Math.log(v) / Math.LN10; }
  function fmtMon(t) {
    if (!t) return "—"; var p = String(t).split("-"), m = (+p[1] || 6), yy = String(p[0]).slice(2);
    return curLang() === "zh" ? (p[0] + "年" + m + "月") : (MONTHS[m - 1] + " ’" + yy);
  }
  function phaseHue(ph) { return (PHASES[ph] || {}).hue || "var(--muted)"; }
  function phaseLabel(s) { return s.now.phaseLabel || (PHASES[s.now.phase] || {}).short || s.now.phase; }

  // tilt presentation
  var TILT = {
    tailwind: { lab: ["Tailwind", "顺风"], ar: "↑", cls: "t-up" },
    headwind: { lab: ["Headwind", "逆风"], ar: "↓", cls: "t-down" },
    mixed: { lab: ["Mixed", "中性"], ar: "↔", cls: "t-mix" }
  };
  function tiltOf(s) { return TILT[(s.proj || {}).tilt] || TILT.mixed; }

  /* ---- y-scaling: price (rebased, log/linear) vs cycle position (0–100) --- */
  function yval(v) { return state.mode === "osc" ? v : (state.scale === "log" ? log10(v) : v); }

  // Price RE-ANCHORING: every line is rebased to 100 at the LEFT EDGE of the
  // visible window (TradingView "percent"), so a zoom shows clean relative
  // performance from that point — not a tangled 6-year fan. curView tracks the
  // visible x-range; the anchor factor scales each series' stored (window-start)
  // rebase to the current left edge.
  var curView = META.xDomain.slice();
  function priceAnchorFactor(s) {
    var pts = s.price, a = pts.length ? pts[0].v : 100;
    for (var i = 0; i < pts.length; i++) { if (pts[i].x <= curView[0]) a = pts[i].v; else break; }
    return a > 0 ? 100 / a : 1;
  }

  function priceExtent() {
    var lo = Infinity, hi = -Infinity, x0 = curView[0], x1 = curView[1];
    ALL.forEach(function (s) {
      if (chartHidden[s.id]) return;
      var f = priceAnchorFactor(s);
      s.price.forEach(function (p) {
        if (p.x < x0 - 0.02 || p.x > x1 + 0.02) return;
        var v = p.v * f; if (v < lo) lo = v; if (v > hi) hi = v;
      });
    });
    if (!isFinite(lo)) { lo = 80; hi = 120; }
    return [lo, hi];
  }

  function yDomain() {
    if (state.mode === "osc") return [0, 100];
    var ex = priceExtent();
    return state.scale === "log" ? [log10(ex[0] * 0.96), log10(ex[1] * 1.05)] : [ex[0] * 0.96, ex[1] * 1.05];
  }

  function yTicks() {
    if (state.mode === "osc") {
      return [{ v: 15, label: L("Low", "低") }, { v: 50, label: L("Mid", "中") }, { v: 85, label: L("High", "高") }];
    }
    var ex = priceExtent(), levels = [50, 60, 75, 100, 125, 150, 200, 250, 300, 400, 500, 700];
    return levels.filter(function (lv) { return lv >= ex[0] * 0.9 && lv <= ex[1] * 1.05; })
      .map(function (lv) { return { v: yval(lv), label: String(lv) }; });
  }

  function bands() {
    if (state.mode !== "osc") return null;
    return [
      { y0: 0, y1: 35, color: "var(--down)", opacity: 0.05, label: L("washed-out", "超卖") },
      { y0: 35, y1: 65, color: "var(--muted)", opacity: 0.04, label: L("mid-cycle", "中段") },
      { y0: 65, y1: 100, color: "var(--warn)", opacity: 0.055, label: L("euphoric", "狂热") }
    ];
  }

  /* ---- build one sector's mm_charts series for the current mode ----------- */
  function seriesFor(s) {
    var osc = state.mode === "osc";
    var f = osc ? 1 : priceAnchorFactor(s);
    var pts = osc ? s.osc : s.price;
    var hist = pts.map(function (p) { return { x: p.x, y: yval(osc ? p.v : p.v * f) }; });
    var markers = (s.turns || []).filter(function (t) { return !t.provisional; }).map(function (t) {
      var yv = osc ? (t.osc != null ? t.osc : 50) : yval(t.rebased * f);
      return { x: t.x, y: yv, kind: t.k === "peak" ? "peak" : "trough", label: fmtMon(t.t), sub: t.mag_pct ? ("±" + t.mag_pct + "%") : "" };
    });
    if (hist.length) markers.push({ x: hist[hist.length - 1].x, y: hist[hist.length - 1].y, kind: "now", label: "Now", sub: phaseLabel(s) });
    return { id: s.id, color: s.accent, label: s.name, width: 2, hist: hist, proj: [], markers: markers, c: s, hidden: !!chartHidden[s.id] };
  }

  /* ---- hero overlay ------------------------------------------------------ */
  var heroChart = null, chartHidden = {};

  function heroTip(d, pt, xVal) {
    var s = d.c, near = Math.abs(xVal - META.today) < 0.05;
    var fy = Math.floor(xVal), fmo = clamp(Math.floor((xVal - fy) * 12), 0, 11);
    var ds = near ? L("Now", "当前") : (curLang() === "zh" ? (fy + "年" + (fmo + 1) + "月") : (MONTHS[fmo] + " " + fy));
    var val;
    if (state.mode === "osc") {
      val = Math.round(pt.y) + " / 100 · " + zoneWord(pt.y);
    } else {
      var rv = Math.round(state.scale === "log" ? Math.pow(10, pt.y) : pt.y), pct = rv - 100;
      val = rv + " · " + (pct >= 0 ? "+" : "") + pct + "%";   // re-based to 100 at the visible left edge
    }
    var head = '<div class="mmc-tip-h"><span class="dot" style="background:' + d.color + '"></span>' + s.name + ' · ' + s.ticker + '</div>';
    var yr = '<div class="mmc-tip-yr">' + ds + '</div>';
    var z = '<div class="mmc-tip-z">' + val + '</div>';
    var ph = near ? '<div class="mmc-tip-ph">' + phaseLabel(s) + '</div>' : '';
    return head + yr + z + ph;
  }
  function zoneWord(y) {
    return y >= 82 ? L("euphoric · topping", "狂热 · 见顶") : y >= 62 ? L("late-cycle", "周期晚期") :
      y >= 42 ? L("mid-cycle", "周期中段") : y >= 22 ? L("recovering", "复苏") : L("washed-out", "超卖");
  }

  var HERO_PAD = { t: 16, r: 16, b: 28, l: 46 };
  function heroSpec() {
    return {
      xDomain: META.xDomain, yDomain: yDomain(),
      yTicks: yTicks(), bands: bands(),
      padding: HERO_PAD,
      guides: [{ x: META.today, label: L("TODAY", "当前"), kind: "today" }],
      animate: true, crosshair: true, zoom: true,
      series: ALL.map(seriesFor),
      vbands: focusBands(),
      tip: heroTip,
      onPick: function (id) { toggleFocus(id); },
      onZoom: function (domain, zoomed) {
        var z = document.getElementById("sc-zoom"); if (z) z.classList.toggle("zoomed", zoomed);
        scheduleReanchor(domain);
      }
    };
  }

  // re-anchor Price mode to the new visible left edge once the zoom/pan settles
  var reTimer = null;
  function scheduleReanchor(domain) {
    curView = domain.slice();
    if (state.mode !== "price" || !heroChart) return;
    if (reTimer) clearTimeout(reTimer);
    reTimer = setTimeout(function () { reTimer = null; rebuildHero(false); }, 130);
  }

  function rebuildHero(animate) {
    if (!heroChart) return;
    heroChart.spec = heroSpec();
    heroChart._hidden = chartHidden;
    if (animate) heroChart.update(heroChart.spec); else heroChart.resize();
  }

  function mountHero() {
    var node = document.getElementById("sc-chart");
    if (!node) return;
    heroChart = window.MMChart.create(node, heroSpec());
    heroChart.setHidden(chartHidden);
    buildZoom();
    // chart-click → if a sector is focused, open the leg under the cursor
    node.addEventListener("click", onChartClick);
  }

  function onChartClick(ev) {
    if (!state.focus) return;
    var s = byId[state.focus]; if (!s) return;
    var rect = document.getElementById("sc-chart").getBoundingClientRect();
    var view = heroChart.getView();
    var W = rect.width, x0 = HERO_PAD.l, x1 = W - HERO_PAD.r;
    var px = ev.clientX - rect.left;
    if (px < x0 || px > x1) return;
    var xv = view[0] + (px - x0) / (x1 - x0) * (view[1] - view[0]);
    var legs = legsOf(s), hit = null;
    legs.forEach(function (g, i) { if (xv >= g.x0 && xv <= g.x1) hit = i; });
    if (hit != null) openLeg(s, hit);
  }

  /* ---- narrative bands on the focused sector (price + osc) ---------------- */
  function focusBands() {
    if (!state.focus) return [];
    var s = byId[state.focus]; if (!s) return [];
    return legsOf(s).filter(function (g) { return g.narr; }).map(function (g) {
      var col = g.dir === "up" ? "var(--up)" : "var(--down)";
      return { x0: g.x0, x1: g.x1, cx: (g.x0 + g.x1) / 2, color: col, opacity: 0.06,
               label: g.narr.title ? trim(g.narr.title, 22) : null, labelY: 11, title: g.narr.title || "" };
    });
  }
  function trim(t, n) { return t.length > n ? t.slice(0, n - 1) + "…" : t; }

  /* ---- legs (peak→trough segments) + their narratives -------------------- */
  function legsOf(s) {
    var turns = (s.turns || []).slice();
    var legs = [];
    var nmap = (NARR[s.id] || {}).legs || {};
    for (var i = 0; i < turns.length - 1; i++) {
      var a = turns[i], b = turns[i + 1];
      var dir = b.k === "peak" ? "up" : "down";
      var mag = b.mag_pct;
      legs.push({ i: i, x0: a.x, x1: b.x, start: a, end: b, dir: dir, mag: mag,
                  narr: nmap[a.date] || nmap[a.t] || null });
    }
    return legs;
  }

  /* ---- zoom controls ----------------------------------------------------- */
  function buildZoom() {
    var z = document.getElementById("sc-zoom");
    if (!z) return;
    var lo = META.xDomain[0], hi = META.xDomain[1];
    var presets = [
      { label: L("6y", "6年"), d: META.xDomain },
      { label: L("3y", "3年"), d: [hi - 3.3, hi] },
      { label: L("1y", "1年"), d: [hi - 1.3, hi] },
      { label: L("6m", "6月"), d: [hi - 0.85, hi] }
    ];
    z.innerHTML = '<span class="cyc-zhint">' + L("scroll · drag", "滚动 · 拖拽") + '</span>' +
      presets.map(function (p, i) { return '<button class="cyc-zbtn" data-i="' + i + '">' + p.label + '</button>'; }).join("") +
      '<button class="cyc-zbtn cyc-zreset" id="sc-zreset">' + L("Reset ⤢", "重置 ⤢") + '</button>';
    presets.forEach(function (p, i) {
      z.querySelector('[data-i="' + i + '"]').addEventListener("click", function () { if (heroChart) heroChart.setView(p.d.slice(), true); });
    });
    z.querySelector("#sc-zreset").addEventListener("click", function () { if (heroChart) heroChart.resetZoom(); });
  }

  /* ---- mode + scale segmented controls ----------------------------------- */
  function wireControls() {
    var modes = document.getElementById("sc-modes"), scale = document.getElementById("sc-scale");
    if (modes) modes.querySelectorAll(".sc-mbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        var m = b.getAttribute("data-mode"); if (m === state.mode) return;
        state.mode = m;
        modes.querySelectorAll(".sc-mbtn").forEach(function (x) { x.classList.toggle("on", x === b); });
        scale.classList.toggle("disabled", m !== "price");
        rebuildHero(true); remountSparks();
      });
    });
    if (scale) scale.querySelectorAll(".sc-sbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        var sc = b.getAttribute("data-scale"); if (sc === state.scale) return;
        state.scale = sc;
        scale.querySelectorAll(".sc-sbtn").forEach(function (x) { x.classList.toggle("on", x === b); });
        rebuildHero(true); remountSparks();
      });
    });
  }

  /* ---- phase filter chips ------------------------------------------------- */
  var PHASE_FILTER = [
    { key: "Peak", label: ["Topping", "见顶"] },
    { key: "Expansion", label: ["Trending", "上行"] },
    { key: "Downturn", label: ["Rolling over", "回落中"] },
    { key: "Recovery", label: ["Prime entry", "入场良机"] },
    { key: "Trough", label: ["Bottoming", "筑底中"] }
  ];
  var phaseState = {};
  function buildGroups() {
    var host = document.getElementById("sc-groups");
    if (!host) return;
    var counts = {};
    SECTORS.forEach(function (s) { counts[s.now.phase] = (counts[s.now.phase] || 0) + 1; });
    PHASE_FILTER.forEach(function (p) { if (phaseState[p.key] == null) phaseState[p.key] = true; });
    host.innerHTML = '<span class="cyc-glabel">' + L("Where they stand", "所处阶段") + '</span>' +
      PHASE_FILTER.map(function (p) {
        return '<button class="cyc-gchip on" data-k="' + p.key + '" style="--ph:' + phaseHue(p.key) + '"><span class="gdot"></span>' + L(p.label[0], p.label[1]) + ' <i>' + (counts[p.key] || 0) + '</i></button>';
      }).join("") +
      '<button class="cyc-gall" id="sc-gall" title="' + L("Show all phases", "显示全部") + '"><span class="ga-dots">' +
        PHASE_FILTER.map(function (p) { return '<i style="background:' + phaseHue(p.key) + '"></i>'; }).join("") +
      '</span>' + L("Select all", "全选") + '</button>';
    host.querySelectorAll(".cyc-gchip").forEach(function (b) {
      b.addEventListener("click", function () {
        var k = b.getAttribute("data-k");
        var sole = phaseState[k] && PHASE_FILTER.every(function (p) { return (p.key === k) === !!phaseState[p.key]; });
        PHASE_FILTER.forEach(function (p) { phaseState[p.key] = sole ? true : (p.key === k); });
        syncGroups();
      });
    });
    host.querySelector("#sc-gall").addEventListener("click", function () {
      PHASE_FILTER.forEach(function (p) { phaseState[p.key] = true; });
      syncGroups();
    });
    syncGroups();
  }
  function syncGroups() {
    var allOn = PHASE_FILTER.every(function (p) { return phaseState[p.key]; });
    document.querySelectorAll("#sc-groups .cyc-gchip").forEach(function (b) {
      b.classList.toggle("on", !!phaseState[b.getAttribute("data-k")]);
    });
    var gall = document.getElementById("sc-gall");
    if (gall) gall.classList.toggle("active", !allOn);
    applyVisibility();
  }
  function applyVisibility() {
    var allOff = PHASE_FILTER.every(function (p) { return !phaseState[p.key]; });
    function phaseOK(s) { return allOff || phaseState[s.now.phase]; }
    // chart: sectors always on (subject to phase filter); baskets only if selected
    chartHidden = {};
    ALL.forEach(function (s) {
      var selected = s.kind === "basket" ? !!basketShown[s.id] : true;
      chartHidden[s.id] = !(phaseOK(s) && selected);
    });
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      var s = byId[cd.getAttribute("data-id")]; if (!s) return;
      var inF = phaseOK(s);
      cd.classList.toggle("gdim", !inF);
      cd.style.order = inF ? "0" : "1";
    });
    document.querySelectorAll(".cyc-chip, .sc-bchip").forEach(function (b) {
      var s = byId[b.getAttribute("data-id")]; if (!s) return;
      b.classList.toggle("gdim", !phaseOK(s));
    });
    if (heroChart) { heroChart.setHidden(chartHidden); rebuildHero(false); }
  }

  /* ---- sector toggle chips ----------------------------------------------- */
  function mountChips() {
    var wrap = document.getElementById("sc-chips");
    if (!wrap) return;
    wrap.innerHTML = "";
    SECTORS.forEach(function (s) {
      var b = el("button", "cyc-chip");
      b.setAttribute("data-id", s.id);
      b.style.setProperty("--c", s.accent);
      b.innerHTML = '<span class="dot"></span><span class="nm">' + s.short + '</span>';
      b.addEventListener("click", function () { toggleFocus(s.id); });
      wrap.appendChild(b);
    });
  }

  /* ---- thematic baskets: a collapsible, category-grouped rail; OFF by
     default — selecting a basket adds its line to the chart and focuses it ---- */
  function basketChipHTML(b) {
    return '<button class="sc-bchip' + (basketShown[b.id] ? " on" : "") + '" data-id="' + b.id + '" style="--c:' + b.accent + '">' +
      '<span class="dot"></span><span class="nm">' + b.short + '</span>' +
      '<span class="sc-bdot" style="background:' + phaseHue(b.now.phase) + '" title="' + phaseLabel(b) + '"></span></button>';
  }
  function mountBaskets() {
    var host = document.getElementById("sc-baskets");
    if (!host) return;
    if (!BASKETS.length) { host.style.display = "none"; return; }
    var byCat = {};
    BASKETS.forEach(function (b) { (byCat[b.group] = byCat[b.group] || []).push(b); });
    var cats = Object.keys(byCat).sort();
    host.innerHTML =
      '<button class="sc-bask-head" id="sc-bask-head" aria-expanded="false">' +
        '<span class="sc-bask-ic">🧺</span><span class="sc-bask-title">' + L("Thematic baskets", "主题篮子") + '</span>' +
        '<span class="sc-bask-n">' + BASKETS.length + '</span>' +
        '<span class="sc-bask-sel" id="sc-bask-sel"></span>' +
        '<span class="sc-bask-hint">' + L("select to overlay", "点选叠加到图表") + '</span>' +
        '<span class="sc-bask-caret">▾</span></button>' +
      '<div class="sc-bask-panel" id="sc-bask-panel">' +
        cats.map(function (c) {
          return '<div class="sc-bask-cat"><div class="sc-bask-cath">' + c + '</div>' +
            '<div class="sc-bask-chips">' + byCat[c].map(basketChipHTML).join("") + '</div></div>';
        }).join("") +
      '</div>';
    document.getElementById("sc-bask-head").addEventListener("click", function () {
      var open = host.classList.toggle("open");
      this.setAttribute("aria-expanded", open ? "true" : "false");
    });
    host.querySelectorAll(".sc-bchip").forEach(function (ch) {
      ch.addEventListener("click", function () { toggleBasket(ch.getAttribute("data-id")); });
    });
    updateBasketSel();
  }
  function updateBasketSel() {
    var n = BASKETS.filter(function (b) { return basketShown[b.id]; }).length;
    var el2 = document.getElementById("sc-bask-sel");
    if (el2) el2.textContent = n ? (n + " " + L("on chart", "在图中")) : "";
    document.querySelectorAll(".sc-bchip").forEach(function (ch) {
      ch.classList.toggle("on", !!basketShown[ch.getAttribute("data-id")]);
    });
  }
  function toggleBasket(id) {
    if (basketShown[id]) {
      basketShown[id] = false; updateBasketSel();
      if (state.focus === id) setFocus(null); else applyVisibility();
    } else {
      basketShown[id] = true; updateBasketSel();
      applyVisibility(); setFocus(id);
    }
  }

  /* ---- scorecards -------------------------------------------------------- */
  var sparks = {};
  function sparkSpec(s) {
    var pts = state.mode === "osc" ? s.osc : s.price;
    var hist = pts.map(function (p) { return { x: p.x, y: yval(p.v) }; });
    var lastY = hist.length ? hist[hist.length - 1].y : 0;
    var yd = state.mode === "osc" ? [0, 100]
      : (function () { var lo = Infinity, hi = -Infinity; pts.forEach(function (p) { if (p.v < lo) lo = p.v; if (p.v > hi) hi = p.v; });
          return state.scale === "log" ? [log10(lo * 0.97), log10(hi * 1.03)] : [lo * 0.97, hi * 1.03]; })();
    return {
      xDomain: [hist.length ? hist[0].x : META.xDomain[0], META.xDomain[1] - 0.25],
      yDomain: yd, padding: { t: 8, r: 6, b: 8, l: 6 },
      crosshair: false, animate: true, zoom: false,
      series: [{ id: s.id, color: s.accent, width: 2, hist: hist, markers: [{ x: hist.length ? hist[hist.length - 1].x : META.today, y: lastY, kind: "now" }] }]
    };
  }
  function remountSparks() {
    SECTORS.forEach(function (s) {
      if (sparks[s.id]) { try { sparks[s.id].update(sparkSpec(s)); } catch (e) {} }
    });
  }
  function mountCards() {
    var grid = document.getElementById("sc-cards");
    if (!grid) return;
    Object.keys(sparks).forEach(function (k) { try { sparks[k].destroy(); } catch (e) {} });
    sparks = {};
    grid.innerHTML = "";
    SECTORS.forEach(function (s) {
      var nw = s.now, tilt = tiltOf(s);
      var card = el("article", "cyc-card");
      card.setAttribute("data-id", s.id);
      card.style.setProperty("--c", s.accent);
      var rs = nw.rs_63d;
      var rsTxt = rs == null ? "" : ('<span class="cc-tilt ' + (rs >= 0 ? "t-up" : "t-down") + '">RS #' + (nw.rs_rank || "—") + '</span>');
      var nextTxt = s.proj ? (L("Next ", "下次") + (s.proj.nextTurn === "peak" ? "▲ " : "▼ ") + fmtMon(s.proj.central)) : L("—", "—");
      card.innerHTML =
        '<div class="cc-top">' +
          '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + s.name + '</div>' +
          '<div class="cc-px">' + s.ticker + ' · ' + L(s.group, s.group) + '</div></div></div>' +
          '<div class="cc-phase" style="--ph:' + phaseHue(nw.phase) + '">' + phaseLabel(s) + '</div>' +
        '</div>' +
        '<div class="cc-spark"></div>' +
        '<div class="cc-meta">' +
          '<div class="cc-leg"><div class="cc-leg-bar"><i style="width:' + Math.round(nw.pos) + '%"></i></div>' +
            '<div class="cc-leg-lab">' + L("Cycle position", "周期位置") + ' ' + Math.round(nw.pos) + '/100' + '</div></div>' +
          '<div class="cc-next"><span class="cc-arrow">' + (s.proj && s.proj.nextTurn === "peak" ? "▲" : "▼") + '</span>' +
            '<span>' + nextTxt + '</span>' +
            '<span class="cc-tilt ' + tilt.cls + '">' + tilt.ar + ' ' + L(tilt.lab[0], tilt.lab[1]) + '</span>' +
            rsTxt + '</div>' +
        '</div>';
      card.addEventListener("click", function () { toggleFocus(s.id); });
      grid.appendChild(card);
      var sp = card.querySelector(".cc-spark");
      sparks[s.id] = window.MMChart.create(sp, sparkSpec(s));
    });
  }

  /* ---- focus orchestration ----------------------------------------------- */
  function toggleFocus(id) { setFocus(state.focus === id ? null : id); }
  function setFocus(id) {
    // focusing a basket implies selecting it onto the chart
    if (id && byId[id] && byId[id].kind === "basket" && !basketShown[id]) {
      basketShown[id] = true; updateBasketSel(); applyVisibility();
    }
    state.focus = id;
    if (heroChart) { heroChart.focus(id); rebuildHero(false); }   // refresh narrative bands
    document.querySelectorAll(".cyc-chip").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-id") === id);
      b.classList.toggle("off", !!id && b.getAttribute("data-id") !== id);
    });
    document.querySelectorAll(".sc-bchip").forEach(function (b) {
      b.classList.toggle("foc", b.getAttribute("data-id") === id);
    });
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      cd.classList.toggle("lit", cd.getAttribute("data-id") === id);
      cd.classList.toggle("dim", !!id && cd.getAttribute("data-id") !== id);
    });
    renderPanel(id);
    if (id && window.innerWidth <= 880) expandSheet(true);
    try { history.replaceState(null, "", id ? "#" + id : location.pathname + location.search); } catch (e) {}
  }

  /* ---- detail panel ------------------------------------------------------ */
  function renderPanel(id) {
    var def = document.getElementById("sc-panel-default"), foc = document.getElementById("sc-panel-focus");
    if (!def || !foc) return;
    if (!id) { foc.classList.remove("show"); def.classList.add("show"); return; }
    foc.innerHTML = focusHTML(byId[id]);
    var back = foc.querySelector(".cyc-back");
    if (back) back.addEventListener("click", function () { setFocus(null); });
    foc.querySelectorAll(".sc-leg").forEach(function (row) {
      row.addEventListener("click", function () { openLeg(byId[id], +row.getAttribute("data-i"), row); });
    });
    def.classList.remove("show"); foc.classList.add("show");
  }

  function focusHTML(s) {
    var nw = s.now, ph = PHASES[nw.phase] || {}, tilt = tiltOf(s);
    function fact(k, v) { return '<div class="f"><div class="fk">' + k + '</div><div class="fv">' + v + '</div></div>'; }
    var posLab = Math.round(nw.pos) + "/100 · " + zoneWord(nw.pos);
    var lenVal = s.proj && s.proj.period_yrs ? (s.proj.period_yrs.median + L(" yr", " 年")) : "—";
    var rsVal = nw.rs_63d == null ? "—" : ((nw.rs_63d >= 0 ? "+" : "") + nw.rs_63d + "% · #" + (nw.rs_rank || "—"));
    var isB = s.kind === "basket", noun = isB ? "Basket" : "Sector", nounZh = isB ? "篮子" : "板块";
    var read = (NARR[s.id] || {}).now || nw.read;
    var readHTML = read ? ('<div class="cyc-read"><div class="cyc-lbl">' + L("The read", "解读") + '</div><p>' + read + '</p></div>')
      : ('<div class="cyc-read"><div class="cyc-lbl">' + L("The read", "解读") + '</div><p class="sc-leg-pending">' +
         L("This " + noun.toLowerCase() + " is " + phaseLabel(s).toLowerCase() + " — cycle position " + Math.round(nw.pos) + "/100, " +
           (nw.above200d ? "above" : "below") + " its 200-day. Narrative read pending research.",
           "该" + nounZh + phaseLabel(s) + " — 周期位置 " + Math.round(nw.pos) + "/100，" + (nw.above200d ? "位于" : "低于") + "200日均线。解读研究待补充。") + '</p></div>');
    var subtitle = isB
      ? (L("Basket", "篮子") + (s.n_members ? " · " + s.n_members + " " + L("names", "只成分") : "") + (s.etf_proxy ? " · " + L("proxy ", "对标 ") + s.etf_proxy : ""))
      : (s.ticker + " · " + L(s.group, s.group));

    return '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<button class="cyc-back">' + L("← All sectors", "← 全部板块") + '</button>' +
        '<div class="cyc-fhead" style="--c:' + s.accent + '">' +
          '<div class="cyc-ftitle">' + s.name + '</div>' +
          '<div class="cyc-fsub">' + subtitle + (nw.above200d ? L(" · above 200d", " · 200日上") : L(" · below 200d", " · 200日下")) + '</div>' +
          '<div class="cyc-fchips">' +
            '<span class="cyc-pchip" style="--ph:' + (ph.hue || "var(--muted)") + '">' + phaseLabel(s) + '</span>' +
            '<span class="cyc-tchip ' + tilt.cls + '">' + tilt.ar + ' ' + L(tilt.lab[0], tilt.lab[1]) + '</span>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Where it stands", "所处位置") + '</div>' +
        '<div class="sc-pos"><div class="sc-pos-bar"><div class="sc-pos-dot" style="--c:' + s.accent + ';left:' + clamp(nw.pos, 2, 98) + '%"></div></div></div>' +
        '<div class="sc-pos-lab">' + posLab + '</div>' +
        '<div class="cyc-facts" style="margin-top:12px">' +
          fact(L("Last trough", "上次底部"), fmtMon(nw.lastTrough)) +
          fact(L("Last peak", "上次顶部"), fmtMon(nw.lastPeak)) +
          fact(L("Next " + ((s.proj || {}).nextTurn || "turn"), "下次" + ((s.proj || {}).nextTurn === "peak" ? "顶部" : "底部")), s.proj ? fmtMon(s.proj.central) : "—") +
          fact(L("Typical ½-cycle", "典型半周期"), lenVal) +
          fact(L("RS vs SPY (63d)", "相对标普(63日)"), rsVal) +
          fact(L("6y change", "6年涨跌"), (nw.ret_win_pct >= 0 ? "+" : "") + nw.ret_win_pct + "%") +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        readHTML +
        ((s.proj && s.proj.central) ? ('<div class="cyc-regnote">' + L("Projected next " + s.proj.nextTurn + " ≈ " + fmtMon(s.proj.central) + " (" + fmtMon(s.proj.low) + "–" + fmtMon(s.proj.high) + "), from this sector’s own median half-cycle. A timing estimate, not a guarantee.",
          "预计下次" + (s.proj.nextTurn === "peak" ? "顶部" : "底部") + "约在 " + fmtMon(s.proj.central) + "（" + fmtMon(s.proj.low) + "–" + fmtMon(s.proj.high) + "），基于该板块自身的中位半周期。仅为时间估计。") + '</div>') : '') +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Cycle legs — tap for the story", "周期区段 — 点击查看故事") + '</div>' +
        '<div class="sc-legs">' + legsHTML(s) + '</div>' +
      '</div>';
  }

  function legsHTML(s) {
    var legs = legsOf(s);
    if (!legs.length) return '<div class="sc-leg-pending">' + L("No major turns in window.", "窗口内无重大拐点。") + '</div>';
    return legs.slice().reverse().map(function (g) {
      var lc = g.dir === "up" ? "var(--up)" : "var(--down)";
      var sign = g.dir === "up" ? "+" : "−";
      var verb = g.dir === "up" ? L("Rally", "上涨") : L("Selloff", "下跌");
      var dt = fmtMon(g.start.t) + " → " + fmtMon(g.end.t);
      var title = g.narr && g.narr.title ? g.narr.title : (verb + " " + (g.mag != null ? sign + g.mag + "%" : ""));
      return '<div class="sc-leg" data-i="' + g.i + '" style="--c:' + s.accent + ';--lc:' + lc + '">' +
        '<span class="sc-leg-k ' + g.dir + '">' + verb + '</span>' +
        '<span class="sc-leg-t">' + title + ' <span class="sc-leg-dt">· ' + dt + '</span></span>' +
        '<span class="sc-leg-m">' + (g.mag != null ? sign + g.mag + "%" : "") + '</span>' +
        '<div class="sc-leg-body" data-body="' + g.i + '" style="grid-column:1/-1">' + legBody(g) + '</div>' +
      '</div>';
    }).join("");
  }
  function legBody(g) {
    if (!g.narr) return '<span class="sc-leg-pending">' + L("What drove this move — research pending.", "推动这一走势的原因 — 研究待补充。") + '</span>';
    var drv = (g.narr.drivers || []).map(function (d) { return "<span>" + d + "</span>"; }).join("");
    return (g.narr.body || "") + (drv ? '<div class="sc-drv">' + drv + '</div>' : "");
  }
  function openLeg(s, i, rowEl) {
    var foc = document.getElementById("sc-panel-focus");
    if (!foc) return;
    var row = rowEl || foc.querySelector('.sc-leg[data-i="' + i + '"]');
    if (!row) return;
    var body = row.querySelector(".sc-leg-body"), wasOpen = body.classList.contains("show");
    foc.querySelectorAll(".sc-leg").forEach(function (r) { r.classList.remove("open"); r.querySelector(".sc-leg-body").classList.remove("show"); });
    if (!wasOpen) {
      row.classList.add("open"); body.classList.add("show");
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
      // zoom the chart to this leg for context
      var g = legsOf(s)[i];
      if (g && heroChart) heroChart.setView([Math.max(META.xDomain[0], g.x0 - 0.15), Math.min(META.xDomain[1], g.x1 + 0.15)], true);
    }
  }

  /* ---- default panel: cross-sector map + leadership + how-to -------------- */
  function buildDefaultPanel() {
    var def = document.getElementById("sc-panel-default");
    if (!def) return;
    var buckets = { Peak: [], Expansion: [], Downturn: [], Recovery: [], Trough: [] };
    SECTORS.forEach(function (s) { (buckets[s.now.phase] || (buckets[s.now.phase] = [])).push(s); });
    function row(title, list, note) {
      if (!list.length) return "";
      var chips = list.map(function (s) {
        return '<button class="mini-chip" data-id="' + s.id + '" style="--c:' + s.accent + '"><span class="dot"></span>' + s.short + '</button>';
      }).join("");
      return '<div class="xc-row"><div class="xc-rh">' + title + '<span>' + note + '</span></div><div class="xc-chips">' + chips + '</div></div>';
    }
    var lead = SECTORS.filter(function (s) { return s.now.rs_rank; }).sort(function (a, b) { return a.now.rs_rank - b.now.rs_rank; });
    var leadRows = lead.map(function (s) {
      var rs = s.now.rs_63d;
      return '<div class="sc-lead-row"><span class="sc-lead-rk">' + s.now.rs_rank + '</span>' +
        '<span class="sc-lead-nm" data-id="' + s.id + '" style="--c:' + s.accent + '"><span class="dot"></span>' + s.name + '</span>' +
        '<span class="sc-lead-rs ' + (rs >= 0 ? "pos" : "neg") + '">' + (rs >= 0 ? "+" : "") + rs + '%</span></div>';
    }).join("");

    def.innerHTML = '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<div class="cyc-lbl">' + L("Sector rotation · ", "板块轮动 · ") + META.asOf + '</div>' +
        '<p class="rg-headline">' + L("Real price on a log axis, every line rebased to 100 at the left edge of the visible window — so <b>zoom to any period</b> and the lines instantly show relative performance from there. Flip to <b>Cycle position</b> to compare sectors on a 0–100 clock. Tap a sector to see its turning points and the story behind each move.",
          "对数坐标下的真实价格，每条线在可见区间的左端再基准化为 100——<b>缩放到任意时段</b>，各线即刻显示自该点起的相对表现。切换到<b>周期位置</b>可在 0–100 的时钟上对比。点按某板块查看其拐点及每段走势背后的故事。") + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Where the sectors stand", "各板块所处位置") + '</div>' +
        '<div class="xc-map">' +
          row(L("Topping · late", "见顶 · 晚期"), buckets.Peak, L("thin cushion", "缓冲薄弱")) +
          row(L("Trending", "上行中"), buckets.Expansion, L("healthy up-trend", "健康上行")) +
          row(L("Rolling over", "回落中"), buckets.Downturn, L("declining", "下行中")) +
          row(L("Prime entry", "入场良机"), buckets.Recovery, L("bottomed · turning up", "已筑底 · 转强")) +
          row(L("Bottoming", "筑底中"), buckets.Trough, L("washed-out", "超卖")) +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Leadership · RS vs SPY (63d)", "领涨 · 相对标普(63日)") + '</div>' +
        '<div class="sc-lead">' + leadRows + '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("How to read", "如何解读") + '</div>' +
        '<ul class="cyc-how">' +
          '<li>' + L("<b>Price</b> shows the real tape (rebased, log); <b>Cycle position</b> shows a 0–100 oscillator — high = stretched/late, low = washed-out.", "<b>价格</b>显示真实走势（再基准化、对数）；<b>周期位置</b>显示 0–100 振荡器——高=拉伸/晚期，低=超卖。") + '</li>' +
          '<li>' + L("▲ peaks and ▼ troughs are auto-detected major turns; the <b>● dot</b> is where the sector is now.", "▲ 波峰与 ▼ 波谷为自动识别的重大拐点；<b>● 圆点</b>是该板块当前位置。") + '</li>' +
          '<li>' + L("<b>Tap a sector</b> (chip, card, or line), then tap a <b>leg</b> to read what drove that move.", "<b>点按某板块</b>（标签、卡片或曲线），再点按某<b>区段</b>了解推动该走势的原因。") + '</li>' +
        '</ul>' +
      '</div>';

    def.querySelectorAll(".mini-chip, .sc-lead-nm").forEach(function (b) {
      b.addEventListener("click", function () { setFocus(b.getAttribute("data-id")); });
    });
    def.classList.add("show");
  }

  /* ---- mobile bottom sheet ----------------------------------------------- */
  function expandSheet(on) { var s = document.getElementById("sc-detail"); if (s) s.classList.toggle("expanded", on !== false); }
  function initSheet() {
    var sheet = document.getElementById("sc-detail"), handle = document.getElementById("sc-handle");
    if (!sheet || !handle) return;
    handle.addEventListener("click", function () { sheet.classList.toggle("expanded"); });
    var startY = 0, dragging = false;
    handle.addEventListener("touchstart", function (e) { startY = e.touches[0].clientY; dragging = true; }, { passive: true });
    handle.addEventListener("touchmove", function (e) {
      if (!dragging) return; var dy = e.touches[0].clientY - startY;
      if (dy < -30) sheet.classList.add("expanded"); else if (dy > 40) sheet.classList.remove("expanded");
    }, { passive: true });
    handle.addEventListener("touchend", function () { dragging = false; });
  }

  /* ---- lang/theme re-render --------------------------------------------- */
  function rerender() {
    var savedFocus = state.focus, savedPhase = {};
    PHASE_FILTER.forEach(function (p) { savedPhase[p.key] = phaseState[p.key]; });
    mountChips(); mountBaskets(); mountCards(); buildDefaultPanel(); buildZoom(); buildGroups();
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = savedPhase[p.key]; });
    syncGroups();
    if (heroChart) rebuildHero(false);
    if (savedFocus) setFocus(savedFocus); else renderPanel(null);
  }

  /* ---- boot -------------------------------------------------------------- */
  function boot() {
    mountChips(); mountBaskets();
    BASKETS.forEach(function (b) { chartHidden[b.id] = true; });   // baskets off the chart until selected
    mountHero(); wireControls(); buildGroups(); buildDefaultPanel(); mountCards(); initSheet();
    document.addEventListener("langchange", rerender);
    var h = (location.hash || "").replace("#", "");
    if (h && byId[h]) setTimeout(function () { setFocus(h); }, 350);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

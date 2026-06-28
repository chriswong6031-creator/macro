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
  // benchmark label for the RS read — data-driven (US "SPY"; China "SHCOMP"/上证综指).
  // US emits no benchmark_zh, so keep its zh label "标普" (byte-identical to the pre-refactor page).
  function benchLabel() { var en = META.benchmark || "SPY"; return L(en, META.benchmark_zh || (en === "SPY" ? "标普" : en)); }
  // "YYYY-MM" -> decimal year (for the forecast band guides)
  function ymToX(t) { if (!t) return null; var p = String(t).split("-"); return (+p[0]) + ((+p[1] || 1) - 1) / 12; }

  var byId = {};
  ALL.forEach(function (s) { byId[s.id] = s; });

  /* ---- view state -------------------------------------------------------- */
  // family = which independent SECTION is active: the 11 sector ETFs (clean default)
  // or the 34 thematic baskets (their own space). Only one family is ever on screen.
  var state = { mode: "price", scale: "log", focus: null, family: "sectors" };
  function activeList() { return state.family === "baskets" ? BASKETS : SECTORS; }
  function isActive(s) { return (s.kind === "basket") === (state.family === "baskets"); }

  /* ---- small helpers ----------------------------------------------------- */
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function log10(v) { return Math.log(v) / Math.LN10; }
  function fmtMon(t) {
    if (!t) return "—"; var p = String(t).split("-"), m = (+p[1] || 6), yy = String(p[0]).slice(2);
    return curLang() === "zh" ? (p[0] + "年" + m + "月") : (MONTHS[m - 1] + " ’" + yy);
  }
  function phaseHue(ph) { return (PHASES[ph] || {}).hue || "var(--muted)"; }
  // bilingual phase label keyed by the phase bucket (engine sends English phaseLabel)
  var PHASE_LAB = {
    Peak: ["Topping", "见顶"], Expansion: ["Trending", "上行"], Downturn: ["Rolling over", "回落"],
    Recovery: ["Prime entry", "入场良机"], Trough: ["Bottoming", "筑底"]
  };
  function phaseLabel(s) { var p = PHASE_LAB[s.now.phase]; return p ? L(p[0], p[1]) : (s.now.phaseLabel || s.now.phase); }
  // bilingual name helpers — fall back to English when no zh provided
  function nm(s) { return curLang() === "zh" && s.name_zh ? s.name_zh : s.name; }
  function shortNm(s) { return curLang() === "zh" ? (s.short_zh || s.name_zh || s.short) : s.short; }
  function grpName(s) { return curLang() === "zh" && s.group_zh ? s.group_zh : s.group; }
  // narrative field with zh fallback (title/body/now/drivers get a _zh sibling once translated)
  function nz(o, f) { return (curLang() === "zh" && o && o[f + "_zh"]) ? o[f + "_zh"] : (o ? o[f] : ""); }

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
    var out = legsOf(s).filter(function (g) { return g.narr; }).map(function (g) {
      var col = g.dir === "up" ? "var(--up)" : "var(--down)";
      var t = nz(g.narr, "title");
      return { x0: g.x0, x1: g.x1, cx: (g.x0 + g.x1) / 2, color: col, opacity: 0.06,
               label: t ? trim(t, 22) : null, labelY: 11, title: t || "" };
    });
    // prominent projected next-turn band (the "forecast point") — drawn in the series accent
    // as a shaded IQR band + a dashed central line, only when it falls in the visible domain.
    // Gated on META.forecastPoint so US (no flag) is unaffected.
    if (META.forecastPoint && s.proj && s.proj.central_x != null) {
      var p = s.proj, ar = p.nextTurn === "peak" ? "▲" : "▼";
      var lo = ymToX(p.low), hi = ymToX(p.high), cx = p.central_x;
      if (cx <= META.xDomain[1] + 0.02) {
        out.push({ x0: (lo != null ? Math.max(lo, META.today) : cx),
                   x1: (hi != null ? Math.min(hi, META.xDomain[1]) : cx),
                   cx: cx, color: s.accent, opacity: 0.12, labelY: 11,
                   label: L("PROJ ", "推演 ") + ar + L(" · rhythm", " · 节奏"),
                   title: L("Projected next turn ~", "推演下一拐点 ~") + fmtMon(p.central) + L(" — typical rhythm, not a backtested forecast", " — 典型节奏，非回测预测") });
      }
    }
    return out;
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
    activeList().forEach(function (s) { counts[s.now.phase] = (counts[s.now.phase] || 0) + 1; });
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = true; });
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
    // An explicit user pick is never hidden by a facet: the focused item, or a basket
    // already overlaid on the chart. Without this carve-out a facet could strand a
    // selection behind display:none — no off-toggle, and a lying "N on chart" counter.
    function pinned(s) { return s.id === state.focus || (s.kind === "basket" && !!basketShown[s.id]); }
    function keepShown(s) { return phaseOK(s) || pinned(s); }
    // only the ACTIVE family is ever on the chart; sectors obey the phase facet, baskets
    // ride on the chart only when selected — and an explicit pick overrides the facet.
    chartHidden = {};
    ALL.forEach(function (s) {
      var sel = s.kind === "basket" ? !!basketShown[s.id] : true;
      chartHidden[s.id] = !(isActive(s) && sel && keepShown(s));
    });
    // When a "Where they stand" facet is active, off-phase sectors/baskets are
    // REMOVED from the selector (not just dimmed) — so the chip rail and card grid
    // show only the active facet's members, no horizontal hunting through greyed chips.
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      var s = byId[cd.getAttribute("data-id")]; if (!s) return;
      cd.classList.toggle("sc-hide", !keepShown(s));
    });
    document.querySelectorAll(".cyc-chip, .sc-bchip").forEach(function (b) {
      var s = byId[b.getAttribute("data-id")]; if (!s) return;
      b.classList.toggle("sc-hide", !keepShown(s));
    });
    // collapse any thematic-basket category group whose chips are now all filtered out
    document.querySelectorAll(".sc-bask-cat").forEach(function (cat) {
      var any = false;
      cat.querySelectorAll(".sc-bchip").forEach(function (b) { if (!b.classList.contains("sc-hide")) any = true; });
      cat.classList.toggle("sc-hide", !any);
    });
    // a11y: announce the filtered count for screen readers (silent for sighted users)
    var act = activeList(), shownN = act.filter(keepShown).length;
    srStatus(shownN < act.length ? L(shownN + " of " + act.length + " shown", "已显示 " + shownN + " / " + act.length + " 项") : "");
    updateChartHint();
    if (heroChart) { heroChart.setHidden(chartHidden); rebuildHero(false); }
  }
  // visually-hidden live region near the phase chips — created once, lazily
  function srStatus(msg) {
    var node = document.getElementById("sc-sr-status");
    if (!node) {
      var host = document.getElementById("sc-groups"); if (!host || !host.parentNode) return;
      node = el("span", "sc-sr-status"); node.id = "sc-sr-status";
      node.setAttribute("role", "status"); node.setAttribute("aria-live", "polite");
      host.parentNode.appendChild(node);
    }
    if (node.textContent !== msg) node.textContent = msg;
  }
  function updateChartHint() {
    var hint = document.getElementById("sc-chart-hint");
    if (!hint) return;
    var anyShown = ALL.some(function (s) { return isActive(s) && !chartHidden[s.id]; });
    if (state.family === "baskets" && !anyShown) {
      hint.hidden = false;
      hint.innerHTML = L("Tap a basket card or chip to chart it — overlay any you like to compare.",
                         "点击下方任一篮子卡片或标签即可绘制——可叠加多个进行对比。");
    } else { hint.hidden = true; }
  }
  /* ---- section family (Sector ETFs vs Thematic Baskets) ------------------ */
  function applyFamilyDisplay() {
    var chips = document.getElementById("sc-chips"), bask = document.getElementById("sc-baskets");
    if (chips) chips.style.display = state.family === "sectors" ? "" : "none";
    // baskets rail = a compact, collapsed quick-picker above the chart; the 34
    // scorecards below are the primary browse/selector, so the chart stays in view.
    if (bask) { bask.style.display = state.family === "baskets" ? "" : "none"; bask.classList.remove("open"); }
    document.querySelectorAll("#sc-tabs .sc-tab").forEach(function (t) { t.classList.toggle("on", t.getAttribute("data-fam") === state.family); });
    var ttl = document.getElementById("sc-hero-title");
    if (ttl) ttl.innerHTML = state.family === "baskets"
      ? '<span class="l-en">Thematic basket rotation</span><span class="l-zh">主题篮子轮动</span>'
      : '<span class="l-en">Sector rotation overlay</span><span class="l-zh">板块轮动叠加</span>';
  }
  function switchFamily(fam) {
    if (fam === state.family) return;
    state.family = fam; state.focus = null;
    if (heroChart) heroChart.focus(null);
    applyFamilyDisplay();
    mountCards();          // re-render the scorecards for the new family
    buildGroups();         // re-count phase chips + re-filter (calls applyVisibility)
    buildDefaultPanel();
    renderPanel(null);
  }
  function wireFamily() {
    document.querySelectorAll("#sc-tabs .sc-tab").forEach(function (t) {
      t.addEventListener("click", function () { switchFamily(t.getAttribute("data-fam")); });
    });
    var ns = document.getElementById("sc-tab-n-sec"), nb = document.getElementById("sc-tab-n-bsk");
    if (ns) ns.textContent = SECTORS.length;
    if (nb) nb.textContent = BASKETS.length;
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
      b.innerHTML = '<span class="dot"></span><span class="nm">' + shortNm(s) + '</span>';
      b.addEventListener("click", function () { toggleFocus(s.id); });
      wrap.appendChild(b);
    });
  }

  /* ---- thematic baskets: a collapsible, category-grouped rail; OFF by
     default — selecting a basket adds its line to the chart and focuses it ---- */
  function basketChipHTML(b) {
    return '<button class="sc-bchip' + (basketShown[b.id] ? " on" : "") + '" data-id="' + b.id + '" style="--c:' + b.accent + '">' +
      '<span class="dot"></span><span class="nm">' + shortNm(b) + '</span>' +
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
          return '<div class="sc-bask-cat"><div class="sc-bask-cath">' + grpName(byCat[c][0]) + '</div>' +
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
    // keep the basket scorecards' "on chart" state in sync with the chips
    document.querySelectorAll("#sc-cards .cyc-card").forEach(function (cd) {
      var id = cd.getAttribute("data-id"), it = byId[id];
      if (it && it.kind === "basket") cd.classList.toggle("sel", !!basketShown[id]);
    });
  }
  function toggleBasket(id) {
    if (basketShown[id]) {
      basketShown[id] = false; updateBasketSel();
      if (state.focus === id) setFocus(null);
      applyVisibility();                         // always recompute (setFocus(null) doesn't)
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
  // cards run the cycle order bottoming -> prime entry -> trending -> topping -> rolling over
  var PHASE_ORDER = { Trough: 0, Recovery: 1, Expansion: 2, Peak: 3, Downturn: 4 };
  function sortedActive() {
    return activeList().slice().sort(function (a, b) {
      var pa = PHASE_ORDER[a.now.phase], pb = PHASE_ORDER[b.now.phase];
      return pa !== pb ? pa - pb : a.now.pos - b.now.pos;
    });
  }
  function mountCards() {
    var grid = document.getElementById("sc-cards");
    if (!grid) return;
    Object.keys(sparks).forEach(function (k) { try { sparks[k].destroy(); } catch (e) {} });
    sparks = {};
    grid.innerHTML = "";
    sortedActive().forEach(function (s) {
      var nw = s.now, tilt = tiltOf(s);
      var card = el("article", "cyc-card");
      card.setAttribute("data-id", s.id);
      card.style.setProperty("--c", s.accent);           // ETF identity dot
      card.style.setProperty("--ph", phaseHue(nw.phase)); // card chrome reads by CYCLE PHASE
      if (s.kind === "basket" && basketShown[s.id]) card.classList.add("sel");
      var rs = nw.rs_63d;
      var rsTxt = rs == null ? "" : ('<span class="cc-tilt ' + (rs >= 0 ? "t-up" : "t-down") + '">RS #' + (nw.rs_rank || "—") + '</span>');
      var nextTxt = s.proj ? (L("Next ", "下次") + (s.proj.nextTurn === "peak" ? "▲ " : "▼ ") + fmtMon(s.proj.central)) : L("—", "—");
      var sigHTML = nw.signal === "BUY" ? '<span class="cc-sig buy">' + L("BUY", "买入") + '</span>'
        : nw.signal === "SELL" ? '<span class="cc-sig sell">' + L("SELL", "卖出") + '</span>' : "";
      var pxLine = s.kind === "basket"
        ? ((s.etf_proxy ? s.etf_proxy + " · " : "") + grpName(s))
        : (s.ticker + " · " + grpName(s));
      card.innerHTML =
        '<div class="cc-top">' +
          '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + nm(s) + '</div>' +
          '<div class="cc-px">' + pxLine + '</div></div></div>' +
          '<div class="cc-tags"><div class="cc-phase" style="--ph:' + phaseHue(nw.phase) + '">' + phaseLabel(s) + '</div>' + sigHTML + '</div>' +
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
      card.addEventListener("click", function () { s.kind === "basket" ? toggleBasket(s.id) : toggleFocus(s.id); });
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

  // washout↔euphoria state signature (the Phase-0-stable read) — rendered when present
  function signatureHTML(s) {
    var sig = s.now && s.now.signature;
    if (!sig || sig.score == null) return "";
    var sc2 = Math.round(sig.score);
    var col = sc2 <= 20 ? "var(--up)" : sc2 >= 80 ? "var(--down)" : "var(--muted)";
    var detail = [];
    if (sig.dist_200d_pct != null) detail.push(L("vs 200d ", "距200日 ") + (sig.dist_200d_pct >= 0 ? "+" : "") + sig.dist_200d_pct + "%");
    if (sig.drawdown_pct != null) detail.push(L("drawdown ", "回撤 ") + sig.drawdown_pct + "%");
    return '<div class="sc-sig">' +
      '<div class="sc-sig-row"><span class="sc-sig-k">' + L("Washout ↔ Euphoria", "超卖 ↔ 过热") + '</span>' +
        '<span class="sc-sig-v" style="color:' + col + '">' + sc2 + '/100 · ' + L(sig.label, sig.label_zh || sig.label) + '</span></div>' +
      '<div class="sc-sig-bar"><i style="width:' + clamp(sc2, 2, 100) + '%"></i></div>' +
      (detail.length ? '<div class="sc-sig-d">' + detail.join(" · ") + '</div>' : "") +
    '</div>';
  }

  // prominent projected next-turn card (the user-requested "best-guess point", honestly framed).
  // Gated on META.forecastPoint (China); without the flag (US) it renders the original compact
  // regnote unchanged, so the US page is byte-identical to before.
  function forecastCardHTML(s) {
    var p = s.proj; if (!p || !p.central) return "";
    if (!META.forecastPoint) {
      return '<div class="cyc-regnote">' + L("Projected next " + p.nextTurn + " ≈ " + fmtMon(p.central) + " (" + fmtMon(p.low) + "–" + fmtMon(p.high) + "), from this sector’s own median half-cycle. A timing estimate, not a guarantee.",
        "预计下次" + (p.nextTurn === "peak" ? "顶部" : "底部") + "约在 " + fmtMon(p.central) + "（" + fmtMon(p.low) + "–" + fmtMon(p.high) + "），基于该板块自身的中位半周期。仅为时间估计。") + '</div>';
    }
    var up = p.nextTurn === "peak", ar = up ? "▲" : "▼";
    var band = (p.low && p.high) ? (fmtMon(p.low) + " – " + fmtMon(p.high)) : "";
    var lenVal = p.period_yrs ? (p.period_yrs.median + L(" yr", " 年")) : "—";
    return '<div class="sc-fcast ' + (up ? "pk" : "tr") + '">' +
      '<div class="sc-fcast-hd"><span class="sc-fcast-ar">' + ar + '</span>' +
        '<span class="sc-fcast-k">' + L("Projected next " + (up ? "peak" : "trough"), "推演下一" + (up ? "顶部" : "底部")) + '</span></div>' +
      '<div class="sc-fcast-date">' + fmtMon(p.central) + '</div>' +
      (band ? '<div class="sc-fcast-band">' + L("typical range ", "典型区间 ") + band + '</div>' : "") +
      '<div class="sc-fcast-note">' + L("From this series’ own median half-cycle (" + lenVal + ") — a timing RHYTHM, not a backtested forecast.",
        "基于该序列自身的中位半周期（" + lenVal + "）——属时间节奏，并非回测预测。") + '</div>' +
    '</div>';
  }

  function _pwNarr(pw) { return curLang() === "zh" ? (pw.narrative_zh || pw.narrative_en || "") : (pw.narrative_en || ""); }
  function _pwCaveat(pw) { return curLang() === "zh" ? (pw.caveat_zh || pw.caveat_en || "") : (pw.caveat_en || ""); }
  // evidence-gated conditional forward odds (the 4 GS sectors only) — Wilson-CI conditioning,
  // never a buy signal. Rendered only when the record carries a `pathway` block.
  function pathwayHTML(s) {
    var pw = s.pathway; if (!pw) return "";
    var cond = pw.conditional || {}, h = cond.h6 || cond.h3 || null, setup = pw.setup || {};
    var legs = setup.legs || [];
    var odds = "";
    if (h) {
      var pr = Math.round(h.cond_rate * 100), base = Math.round(h.base_rate * 100), hz = h.h || 6;
      var ci = Math.round(h.ci_lo * 100) + "–" + Math.round(h.ci_hi * 100) + "%";
      var liftCls = h.lift > 0.03 ? "t-up" : h.lift < -0.03 ? "t-down" : "t-mix";
      odds = '<div class="sc-pw-odds"><div class="sc-pw-big ' + liftCls + '">' + pr + '%</div>' +
        '<div class="sc-pw-meta"><div class="sc-pw-line">' + L("forward-" + hz + "m positive", "未来" + hz + "个月上涨") + '</div>' +
        '<div class="sc-pw-sub">' + L("vs ", "基准 ") + base + L("% base", "%") + ' · ' + L("CI ", "置信 ") + ci + ' · n=' + h.n + '</div></div></div>';
    }
    var legChips = legs.slice(0, 4).map(function (lg) {
      var cls = lg.stance === "bullish" ? "pw-bull" : lg.stance === "bearish" ? "pw-bear" : "pw-neu";
      return '<span class="sc-pw-leg ' + cls + '">' + L(lg.label_en, lg.label_zh) + '</span>';
    }).join("");
    return '<div class="cyc-grp cyc-grp-3 sc-pathway">' +
      '<div class="cyc-lbl">' + L("Evidence-gated forward odds", "经证据门槛的前瞻概率") +
        ' <span class="sc-pw-badge" title="' + L("conditional · display-only", "条件化 · 仅展示") + '">⚗︎</span></div>' +
      odds +
      (legChips ? '<div class="sc-pw-legs"><span class="sc-pw-legk">' + L("Lead cluster now", "当前领先因子") + '</span>' + legChips + '</div>' : "") +
      (_pwNarr(pw) ? '<p class="sc-pw-narr">' + _pwNarr(pw) + '</p>' : "") +
      (_pwCaveat(pw) ? '<p class="sc-pw-caveat">' + _pwCaveat(pw) + '</p>' : "") +
    '</div>';
  }

  function focusHTML(s) {
    var nw = s.now, ph = PHASES[nw.phase] || {}, tilt = tiltOf(s);
    function fact(k, v) { return '<div class="f"><div class="fk">' + k + '</div><div class="fv">' + v + '</div></div>'; }
    var posLab = Math.round(nw.pos) + "/100 · " + zoneWord(nw.pos);
    var lenVal = s.proj && s.proj.period_yrs ? (s.proj.period_yrs.median + L(" yr", " 年")) : "—";
    var rsVal = nw.rs_63d == null ? "—" : ((nw.rs_63d >= 0 ? "+" : "") + nw.rs_63d + "% · #" + (nw.rs_rank || "—"));
    var isB = s.kind === "basket", noun = isB ? "Basket" : "Sector", nounZh = isB ? "篮子" : "板块";
    var read = nz(NARR[s.id], "now") || nw.read;
    var readHTML = read ? ('<div class="cyc-read"><div class="cyc-lbl">' + L("The read", "解读") + '</div><p>' + read + '</p></div>')
      : ('<div class="cyc-read"><div class="cyc-lbl">' + L("The read", "解读") + '</div><p class="sc-leg-pending">' +
         L("This " + noun.toLowerCase() + " is " + phaseLabel(s).toLowerCase() + " — cycle position " + Math.round(nw.pos) + "/100, " +
           (nw.above200d ? "above" : "below") + " its 200-day. Narrative read pending research.",
           "该" + nounZh + phaseLabel(s) + " — 周期位置 " + Math.round(nw.pos) + "/100，" + (nw.above200d ? "位于" : "低于") + "200日均线。解读研究待补充。") + '</p></div>');
    var subtitle = isB
      ? (L("Basket", "篮子") + (s.n_members ? " · " + s.n_members + " " + L("names", "只成分") : "") + (s.etf_proxy ? " · " + L("proxy ", "对标 ") + s.etf_proxy : ""))
      : (s.ticker + " · " + grpName(s));

    return '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<button class="cyc-back">' + (s.kind === "basket" ? L("← All baskets", "← 全部篮子") : L("← All sectors", "← 全部板块")) + '</button>' +
        '<div class="cyc-fhead" style="--c:' + s.accent + '">' +
          '<div class="cyc-ftitle">' + nm(s) + '</div>' +
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
        signatureHTML(s) +
        '<div class="cyc-facts" style="margin-top:12px">' +
          fact(L("Last trough", "上次底部"), fmtMon(nw.lastTrough)) +
          fact(L("Last peak", "上次顶部"), fmtMon(nw.lastPeak)) +
          fact(L("Next " + ((s.proj || {}).nextTurn || "turn"), "下次" + ((s.proj || {}).nextTurn === "peak" ? "顶部" : "底部")), s.proj ? fmtMon(s.proj.central) : "—") +
          fact(L("Typical ½-cycle", "典型半周期"), lenVal) +
          fact(L("RS vs ", "相对") + benchLabel() + L(" (63d)", "(63日)"), rsVal) +
          fact(L("6y change", "6年涨跌"), (nw.ret_win_pct >= 0 ? "+" : "") + nw.ret_win_pct + "%") +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        readHTML +
        forecastCardHTML(s) +
      '</div>' +
      pathwayHTML(s) +
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
      var title = g.narr && nz(g.narr, "title") ? nz(g.narr, "title") : (verb + " " + (g.mag != null ? sign + g.mag + "%" : ""));
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
    var drivers = (curLang() === "zh" && g.narr.drivers_zh) ? g.narr.drivers_zh : (g.narr.drivers || []);
    var drv = drivers.map(function (d) { return "<span>" + d + "</span>"; }).join("");
    return (nz(g.narr, "body") || "") + (drv ? '<div class="sc-drv">' + drv + '</div>' : "");
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
    var baskets = state.family === "baskets";
    var noun = baskets ? L("baskets", "篮子") : L("sectors", "板块");
    var buckets = { Peak: [], Expansion: [], Downturn: [], Recovery: [], Trough: [] };
    activeList().forEach(function (s) { (buckets[s.now.phase] || (buckets[s.now.phase] = [])).push(s); });
    function row(title, list, note, emptyMsg) {
      if (!list.length) {
        // an empty bucket is normally dropped; pass emptyMsg to keep the row with a
        // "none right now" note (Prime entry is always shown so its absence is explicit).
        if (!emptyMsg) return "";
        return '<div class="xc-row xc-row-empty"><div class="xc-rh">' + title + '<span>' + note + '</span></div>' +
          '<div class="xc-empty">' + emptyMsg + '</div></div>';
      }
      var chips = list.map(function (s) {
        return '<button class="mini-chip" data-id="' + s.id + '" style="--c:' + s.accent + '"><span class="dot"></span>' + shortNm(s) + '</button>';
      }).join("");
      return '<div class="xc-row"><div class="xc-rh">' + title + '<span>' + note + '</span></div><div class="xc-chips">' + chips + '</div></div>';
    }
    var lead = activeList().filter(function (s) { return s.now.rs_rank; }).sort(function (a, b) { return a.now.rs_rank - b.now.rs_rank; });
    var leadCap = baskets ? 12 : lead.length;
    var leadRows = lead.slice(0, leadCap).map(function (s) {
      var rs = s.now.rs_63d;
      return '<div class="sc-lead-row"><span class="sc-lead-rk">' + s.now.rs_rank + '</span>' +
        '<span class="sc-lead-nm" data-id="' + s.id + '" style="--c:' + s.accent + '"><span class="dot"></span>' + nm(s) + '</span>' +
        '<span class="sc-lead-rs ' + (rs >= 0 ? "pos" : "neg") + '">' + (rs >= 0 ? "+" : "") + rs + '%</span></div>';
    }).join("") + (lead.length > leadCap ? '<div class="sc-lead-more">+ ' + (lead.length - leadCap) + ' ' + L("more", "更多") + '</div>' : "");

    def.innerHTML = '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<div class="cyc-lbl">' + (baskets ? L("Thematic basket rotation · ", "主题篮子轮动 · ") : L("Sector rotation · ", "板块轮动 · ")) + META.asOf + '</div>' +
        '<p class="rg-headline">' + (baskets
          ? L("The 34 thematic baskets on the same cycle clock — each an equal-weight index of its members. The chart starts empty; <b>tap any basket</b> (card or chip) to overlay its real price, then read its turning points. Flip to <b>Cycle position</b> to compare them on a 0–100 clock.",
              "34 个主题篮子同处一张周期时钟——每个均为其成分股的等权指数。图表初始为空；<b>点击任一篮子</b>（卡片或标签）即可叠加其真实价格并查看拐点。切换到<b>周期位置</b>可在 0–100 的时钟上对比。")
          : L("Real price on a log axis, every line rebased to 100 at the left edge of the visible window — so <b>zoom to any period</b> and the lines instantly show relative performance from there. Flip to <b>Cycle position</b> to compare sectors on a 0–100 clock. Tap a sector to see its turning points and the story behind each move.",
              "对数坐标下的真实价格，每条线在可见区间的左端再基准化为 100——<b>缩放到任意时段</b>，各线即刻显示自该点起的相对表现。切换到<b>周期位置</b>可在 0–100 的时钟上对比。点按某板块查看其拐点及每段走势背后的故事。")) + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Where the ", "各") + noun + L(" stand", "所处位置") + '</div>' +
        '<div class="xc-map">' +
          row(L("Topping · late", "见顶 · 晚期"), buckets.Peak, L("thin cushion", "缓冲薄弱")) +
          row(L("Trending", "上行中"), buckets.Expansion, L("healthy up-trend", "健康上行")) +
          row(L("Rolling over", "回落中"), buckets.Downturn, L("declining", "下行中")) +
          row(L("Prime entry", "入场良机"), buckets.Recovery, L("bottomed · turning up", "已筑底 · 转强"),
              L("No " + (baskets ? "baskets" : "sectors") + " are at prime entry right now.",
                "目前没有处于入场良机的" + (baskets ? "篮子" : "板块") + "。")) +
          row(L("Bottoming", "筑底中"), buckets.Trough, L("washed-out", "超卖")) +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Leadership · RS vs ", "领涨 · 相对") + benchLabel() + L(" (63d)", "(63日)") + '</div>' +
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
    mountChips(); mountBaskets(); applyFamilyDisplay(); mountCards(); buildDefaultPanel(); buildZoom(); buildGroups();
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = savedPhase[p.key]; });
    syncGroups();
    if (heroChart) rebuildHero(false);
    if (savedFocus) setFocus(savedFocus); else renderPanel(null);
  }

  /* ---- boot -------------------------------------------------------------- */
  function boot() {
    mountChips(); mountBaskets();
    BASKETS.forEach(function (b) { chartHidden[b.id] = true; });   // baskets off the chart until selected
    wireFamily(); applyFamilyDisplay();                            // sectors section active; baskets hidden
    mountHero(); wireControls(); buildGroups(); buildDefaultPanel(); mountCards(); initSheet();
    document.addEventListener("langchange", rerender);
    var h = (location.hash || "").replace("#", "");
    if (h && byId[h]) setTimeout(function () {
      if (byId[h].kind === "basket") switchFamily("baskets");
      setFocus(h);
    }, 350);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

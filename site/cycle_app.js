/* ============================================================================
   cycle_app.js — Cycle Intelligence Dashboard · orchestration
   ----------------------------------------------------------------------------
   Synthesises each cycle's oscillator + regime-conditioned projection from
   cycle_data.js, composes mm_charts.js into the hero overlay and the scorecard
   sparklines (SAME synthesis → single source of truth), and wires the focus
   interaction, the default↔focused detail panel, scorecard light-up sync, and
   the mobile bottom sheet.
   ========================================================================== */
(function () {
  "use strict";

  var TROUGH = 6, PEAK = 94, MID = 50;
  var META = window.CYCLE_META, CYCLES = window.CYCLES, PHASES = window.CYCLE_PHASES;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /* ---- wall-clock TODAY (W0.1) -------------------------------------------
     Derive the current decimal year from the live system clock so the Now dot,
     history/projection split, and turn-elapsed detection are always accurate.
     META.today (a frozen literal) is kept only as a data-as-of fallback if
     Date() is somehow unavailable. */
  function yfNow(d) {
    var y = d.getFullYear();
    var start = new Date(y, 0, 1), end = new Date(y + 1, 0, 1);
    return y + (d - start) / (end - start);
  }
  var TODAY = (function () {
    try { var n = new Date(); if (isFinite(n.getTime())) return yfNow(n); } catch (e) {}
    return META.today;    // frozen fallback only
  }());

  /* ---- i18n: EN default, 中文 when <html data-lang="zh"> --------------------
     Short UI strings are inline L(en, zh) pairs; long per-cycle/regime prose is
     looked up from window.CYCLE_ZH (cycle_i18n.js) with graceful EN fallback. */
  function curLang() { return document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"; }
  function L(en, zh) { return curLang() === "zh" ? zh : en; }
  function zc(id, field, en) { if (curLang() !== "zh") return en; var z = (window.CYCLE_ZH && window.CYCLE_ZH.cycles || {})[id]; return z && z[field] != null && z[field] !== "" ? z[field] : en; }
  function zcArr(id, field, enArr) { if (curLang() !== "zh") return enArr; var z = (window.CYCLE_ZH && window.CYCLE_ZH.cycles || {})[id]; return z && z[field] && z[field].length ? z[field] : enArr; }
  function zr(field, en) { if (curLang() !== "zh") return en; var r = window.CYCLE_ZH && window.CYCLE_ZH.regime; return r && r[field] != null ? r[field] : en; }
  var PHASE_LAB = { Peak: ["Peak", "见顶"], Expansion: ["Expansion", "扩张"], Downturn: ["Downturn", "回落"], Recovery: ["Recovery", "复苏"], Trough: ["Trough", "筑底"] };
  function phaseChip(k) { var p = PHASE_LAB[k] || [k, k]; return L(p[0], p[1]); }
  function turnWord(nt, cap) { return nt === "peak" ? L(cap ? "Peak" : "peak", "见顶") : L(cap ? "Trough" : "trough", "筑底"); }

  /* ---- small helpers ----------------------------------------------------- */
  function yf(t) { var p = String(t).split("-"); return +p[0] + ((+p[1] || 6) - 0.5) / 12; }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function cos(x, xa, ya, xb, yb) {
    if (xb === xa) return yb;
    var t = clamp((x - xa) / (xb - xa), 0, 1);
    return ya + (yb - ya) * (0.5 - 0.5 * Math.cos(Math.PI * t));
  }
  function fmtMon(t) {
    if (!t) return ""; var p = String(t).split("-"), m = (+p[1] || 6), yy = String(p[0]).slice(2);
    return curLang() === "zh" ? (yy + "年" + m + "月") : (MONTHS[m - 1] + " ’" + yy);
  }
  function fmtY(t) { return String(t).split("-")[0]; }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function zone(y) {
    return y >= 82 ? L("Euphoric · topping", "狂热 · 见顶") : y >= 62 ? L("Late-cycle", "周期晚期") :
      y >= 42 ? L("Mid-cycle", "周期中段") : y >= 22 ? L("Recovery", "复苏") : L("Washed-out · stressed", "超卖 · 承压");
  }
  var TILT = {
    tailwind: { lab: "Tailwind", zh: "顺风", ar: "↑", cls: "t-up" },
    headwind: { lab: "Headwind", zh: "逆风", ar: "↓", cls: "t-down" },
    mixed: { lab: "Mixed", zh: "中性", ar: "↔", cls: "t-mix" },
    "n/a": { lab: "Event-driven", zh: "事件驱动", ar: "•", cls: "t-na" }
  };
  function tiltLab(t) { return L(t.lab, t.zh); }

  /* ---- oscillator + projection synthesis (the model) --------------------- */
  function build(c) {
    var turns = c.turns.map(function (tp) {
      return { x: yf(tp.t), y: tp.k === "peak" ? PEAK : TROUGH, k: tp.k, e: tp.e, v: tp.v, t: tp.t };
    });
    var n = turns.length, last = turns[n - 1];
    var nextY = c.proj.nextTurn === "peak" ? PEAK : TROUGH;

    // W0.1: use wall-clock TODAY (no frozen literal); META.today is now data as-of only.
    var today = TODAY;

    // W0.1: NO Math.max push-forward. Use the hand-typed central date as-is.
    // When tcRaw < today the projection window has elapsed; we render a dimmed
    // "window passed" state instead of silently shifting the turn into the future.
    var tcRaw = yf(c.proj.central);
    var elapsed = tcRaw < today;   // true = turn date is in the past

    // In the elapsed case keep tc/te/tl at the original hand-typed dates so the
    // projection leg draws to where the research said, then dims — not pushed right.
    // In the normal case guard against a non-positive (tt - today) denominator in
    // legVal by clamping tc to at least today + 0.001 (one day buffer is enough;
    // the elapsed branch already handles the tcRaw < today case separately).
    var tc, te, tl, projEnd, relax;
    relax = c.proj.nextTurn === "peak" ? 58 : 42;
    if (elapsed) {
      tc = tcRaw;
      te = yf(c.proj.low);
      tl = yf(c.proj.high);
      projEnd = Math.max(tc, tl) + 0.1;    // draw to last plausible turn then stop
    } else {
      tc = tcRaw;
      te = clamp(yf(c.proj.low), today + 0.05, tc);
      tl = Math.max(yf(c.proj.high), tc + 0.1);
      projEnd = Math.min(META.xDomain[1], tl + 0.35 * (tl - today));
    }

    // Anchor the curve to the research-grounded CURRENT position (now.pos) so the
    // line passes through it at TODAY — faithful amplitude, not just time-fraction.
    // The current leg is one cosine (last turn → next turn) reparametrised in time
    // on each side of TODAY so value(today) === now.pos and value(turn) === nextY.
    var nowPos = clamp(c.now.pos != null ? c.now.pos : (last.y + nextY) / 2, 4, 96);
    var ratio = clamp((nowPos - last.y) / (nextY - last.y), 0.02, 0.98);
    var uNow = Math.acos(1 - 2 * ratio) / Math.PI;          // cosine param where value === now.pos
    function legVal(x, tt) {
      if (x <= today) {
        var u = today <= last.x ? 1 : ((x - last.x) / (today - last.x)) * uNow;
        return last.y + (nextY - last.y) * (0.5 - 0.5 * Math.cos(Math.PI * clamp(u, 0, 1)));
      }
      // Guard: if tt <= today (elapsed branch), division by zero is avoided because
      // the elapsed case only calls legVal for x <= today (no proj/cone generated).
      // In the normal branch tt > today is guaranteed by the tc clamping above.
      var denom = tt - today;
      var u2 = denom > 0 ? uNow + ((x - today) / denom) * (1 - uNow) : 1;
      if (x <= tt) return last.y + (nextY - last.y) * (0.5 - 0.5 * Math.cos(Math.PI * clamp(u2, 0, 1)));
      return cos(x, tt, nextY, projEnd, relax);
    }
    var center = function (x) { return legVal(x, tc); };
    var withTurn = function (x, tt) { return legVal(x, tt); };

    // historical dense polyline through every dated turn
    var hist = [], step = 0.16;
    for (var i = 0; i < n - 1; i++) {
      var a = turns[i], b = turns[i + 1];
      for (var x = a.x; x < b.x - 1e-6; x += step) hist.push({ x: x, y: cos(x, a.x, a.y, b.x, b.y) });
    }
    hist.push({ x: last.x, y: last.y });
    // continue the CURRENT leg (last real turn → today) as solid history
    for (var xx = last.x + step; xx <= today; xx += step) hist.push({ x: xx, y: center(xx) });
    hist.push({ x: today, y: center(today) });

    // W0.1: elapsed-turn handling — projection leg/cone drawn to original hand-typed
    // dates but flagged as elapsed (rendered dimmed/greyed by the caller).
    // Normal case: full forward projection + cone.
    var proj = [], cone = [];
    if (elapsed) {
      // Draw the projection leg from last turn to the hand-typed tc (all in the past),
      // rendered dimmed so the reader sees "this was the projected window".
      for (var xpe = last.x; xpe <= projEnd + 1e-6; xpe += step) {
        proj.push({ x: xpe, y: cos(xpe, last.x, last.y, Math.max(tc, last.x + 0.01), nextY) });
      }
      // No cone in elapsed state — the window has passed.
    } else {
      for (var xp = today; xp <= projEnd + 1e-6; xp += step) proj.push({ x: xp, y: center(xp) });

      // uncertainty cone: timing spread (early/central/late) + amplitude growing with horizon
      var tlt = c.proj.tilt, hiW = tlt === "tailwind" ? 1.35 : tlt === "headwind" ? 0.7 : 1, loW = tlt === "headwind" ? 1.35 : tlt === "tailwind" ? 0.7 : 1;
      for (var xc = today; xc <= projEnd + 1e-6; xc += step) {
        var vs = [withTurn(xc, te), center(xc), withTurn(xc, tl)];
        var lo = Math.min(vs[0], vs[1], vs[2]), hi = Math.max(vs[0], vs[1], vs[2]);
        var amp = lerp(1.5, 13, clamp((xc - today) / (projEnd - today), 0, 1));
        cone.push({ x: xc, lo: clamp(lo - amp * loW, 2, 98), hi: clamp(hi + amp * hiW, 2, 98) });
      }
    }

    var markers = turns.filter(function (t) { return t.x >= META.xDomain[0] - 0.2; })
      .map(function (t) { return { x: t.x, y: t.y, kind: t.k, label: fmtMon(t.t), sub: t.e }; });
    var nowY = center(today);
    markers.push({ x: today, y: nowY, kind: "now", label: "Now", sub: c.now.phaseLabel });

    // legPct: clamp to [0,1]; if elapsed push to 1 (>100% is displayed as "window elapsed")
    var legPct = elapsed ? 1 : clamp((today - last.x) / Math.max(tc - last.x, 0.001), 0, 1);

    return {
      id: c.id, color: c.accent, label: c.name, width: 2,
      hist: hist, proj: proj, cone: cone, markers: markers,
      nowY: nowY, tc: tc, te: te, tl: tl, projEnd: projEnd,
      legPct: legPct, elapsed: elapsed, c: c
    };
  }

  var MODELS = {}, ORDER = [];
  CYCLES.forEach(function (c) { MODELS[c.id] = build(c); ORDER.push(c.id); });

  /* ---- hero overlay ------------------------------------------------------ */
  var heroChart = null, state = { focus: null };

  function heroSpec() {
    return {
      xDomain: META.xDomain, yDomain: [0, 100],
      xTicks: window.MMChart.niceYearTicks(META.xDomain[0] + 1, META.xDomain[1], 5),
      yTicks: [{ v: TROUGH, label: L("Trough", "底部") }, { v: MID, label: L("Mid", "中位") }, { v: PEAK, label: L("Peak", "顶部") }],
      padding: { t: 16, r: 16, b: 28, l: 46 },
      bands: [
        { y0: 0, y1: 35, color: "var(--down)", opacity: 0.05, label: L("washed-out", "超卖") },
        { y0: 35, y1: 65, color: "var(--muted)", opacity: 0.04, label: L("mid-cycle", "中段") },
        { y0: 65, y1: 100, color: "var(--warn)", opacity: 0.055, label: L("euphoric", "狂热") }
      ],
      guides: [{ x: META.today, label: L("TODAY", "当前"), kind: "today" }],
      animate: true, crosshair: true, zoom: true,
      series: ORDER.map(function (id) { return MODELS[id]; }),
      tip: heroTip,
      onPick: function (id) { toggleFocus(id); },
      onZoom: function (domain, zoomed) { var z = document.getElementById("cyc-zoom"); if (z) z.classList.toggle("zoomed", zoomed); }
    };
  }

  function heroTip(d, pt, xVal) {
    var c = d.c, rising = pt.b ? pt.b.y >= pt.a.y : true;
    var near = Math.abs(xVal - META.today) < 0.06;
    var fy = Math.floor(xVal), fmo = clamp(Math.floor((xVal - fy) * 12), 0, 11);
    var ds = near ? L("Now", "当前") : (curLang() === "zh" ? (fy + "年" + (fmo + 1) + "月") : (MONTHS[fmo] + " " + fy));
    var head = '<div class="mmc-tip-h"><span class="dot" style="background:' + d.color + '"></span>' + zc(c.id, "name", c.name) + '</div>';
    var yr = '<div class="mmc-tip-yr">' + ds + '</div>';
    var z = '<div class="mmc-tip-z">' + zone(pt.y) + ' · ' + (rising ? L("rising", "上行") : L("easing", "回落")) + '</div>';
    var ph = near ? '<div class="mmc-tip-ph">' + zc(c.id, "phaseLabel", c.now.phaseLabel) + '</div>' : '';
    return head + yr + z + ph;
  }

  function mountHero() {
    var node = document.getElementById("cyc-chart");
    if (!node) return;
    heroChart = window.MMChart.create(node, heroSpec());
    buildZoom();
    buildGroups();
  }

  /* ---- zoom controls (presets + reset; wheel/drag handled by the engine) -- */
  function buildZoom() {
    var z = document.getElementById("cyc-zoom");
    if (!z) return;
    var presets = [
      { label: L("Full", "全部"), d: META.xDomain },
      { label: L("15y", "15年"), d: [2016, 2031] },
      { label: L("8y", "8年"), d: [2021, 2030] },
      { label: L("Cycle", "本轮"), d: [2024, 2029] }
    ];
    z.innerHTML = '<span class="cyc-zhint">' + L("scroll · drag", "滚动 · 拖拽") + '</span>' +
      presets.map(function (p, i) { return '<button class="cyc-zbtn" data-i="' + i + '">' + p.label + '</button>'; }).join("") +
      '<button class="cyc-zbtn cyc-zreset" id="cyc-zreset">' + L("Reset ⤢", "重置 ⤢") + '</button>';
    presets.forEach(function (p, i) {
      z.querySelector('[data-i="' + i + '"]').addEventListener("click", function () { if (heroChart) heroChart.setView(p.d.slice(), true); });
    });
    z.querySelector("#cyc-zreset").addEventListener("click", function () { if (heroChart) heroChart.resetZoom(); });
  }

  /* ---- phase filter — group by WHERE each cycle stands (topping → bottoming)
     so co-phased (correlated) assets cluster together. It DIMS rather than hides,
     so the chip/card layout never collapses and the chart never shifts; filtered
     scorecards shuffle to the top, the rest dim (the same mechanic as focus). --- */
  var PHASE_FILTER = [
    { key: "Peak", label: "Topping", zh: "见顶" },
    { key: "Expansion", label: "Expanding", zh: "扩张中" },
    { key: "Downturn", label: "Rolling over", zh: "回落中" },
    { key: "Recovery", label: "Recovering", zh: "复苏中" },
    { key: "Trough", label: "Bottoming", zh: "筑底中" }
  ];
  var byId = {};
  CYCLES.forEach(function (c) { byId[c.id] = c; });
  var phaseState = {};
  function buildGroups() {
    var host = document.getElementById("cyc-groups");
    if (!host) return;
    var counts = {};
    CYCLES.forEach(function (c) { counts[c.now.phase] = (counts[c.now.phase] || 0) + 1; });
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = true; });
    host.innerHTML = '<span class="cyc-glabel">' + L("Where they stand", "所处阶段") + '</span>' +
      PHASE_FILTER.map(function (p) {
        var hue = (PHASES[p.key] || {}).hue || "var(--muted)";
        return '<button class="cyc-gchip on" data-k="' + p.key + '" style="--ph:' + hue + '"><span class="gdot"></span>' + L(p.label, p.zh) + ' <i>' + (counts[p.key] || 0) + '</i></button>';
      }).join("") +
      '<button class="cyc-gall" id="cyc-gall" title="' + L("Show all phases", "显示全部") + '"><span class="ga-dots">' +
        PHASE_FILTER.map(function (p) { return '<i style="background:' + ((PHASES[p.key] || {}).hue || "var(--muted)") + '"></i>'; }).join("") +
      '</span>' + L("Select all", "全选") + '</button>';
    // single-select: clicking a phase ISOLATES it (deselects the rest); clicking
    // the already-isolated phase, or the Select-all button, restores all.
    host.querySelectorAll(".cyc-gchip").forEach(function (b) {
      b.addEventListener("click", function () {
        var k = b.getAttribute("data-k");
        var sole = phaseState[k] && PHASE_FILTER.every(function (p) { return (p.key === k) === !!phaseState[p.key]; });
        PHASE_FILTER.forEach(function (p) { phaseState[p.key] = sole ? true : (p.key === k); });
        syncGroups();
      });
    });
    host.querySelector("#cyc-gall").addEventListener("click", function () {
      PHASE_FILTER.forEach(function (p) { phaseState[p.key] = true; });
      syncGroups();
    });
    syncGroups();
  }
  function syncGroups() {
    var allOn = PHASE_FILTER.every(function (p) { return phaseState[p.key]; });
    document.querySelectorAll(".cyc-gchip").forEach(function (b) {
      b.classList.toggle("on", !!phaseState[b.getAttribute("data-k")]);
    });
    var gall = document.getElementById("cyc-gall");
    if (gall) gall.classList.toggle("active", !allOn);   // glows when a filter is active
    applyGroupFilter();
  }
  function applyGroupFilter() {
    var allOff = PHASE_FILTER.every(function (p) { return !phaseState[p.key]; });
    var hidden = {};
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      var c = byId[cd.getAttribute("data-id")]; if (!c) return;
      var inF = allOff || phaseState[c.now.phase];   // empty selection == no filter
      cd.classList.toggle("gdim", !inF);
      cd.style.order = inF ? "0" : "1";              // shuffle filtered-in to the top
      if (!inF) hidden[c.id] = true;
    });
    document.querySelectorAll(".cyc-chip").forEach(function (b) {
      var c = byId[b.getAttribute("data-id")]; if (!c) return;
      b.classList.toggle("gdim", !(allOff || phaseState[c.now.phase]));
    });
    if (heroChart) heroChart.setHidden(hidden);
  }

  /* ---- toggle chips ------------------------------------------------------ */
  function mountChips() {
    var wrap = document.getElementById("cyc-chips");
    if (!wrap) return;
    wrap.innerHTML = "";
    CYCLES.forEach(function (c) {
      var b = el("button", "cyc-chip");
      b.setAttribute("data-id", c.id);
      b.style.setProperty("--c", c.accent);
      b.innerHTML = '<span class="dot"></span><span class="nm">' + zc(c.id, "short", c.short) + '</span>';
      b.addEventListener("click", function () { toggleFocus(c.id); });
      wrap.appendChild(b);
    });
  }

  /* ---- scorecards -------------------------------------------------------- */
  var sparks = {};
  function mountCards() {
    var grid = document.getElementById("cyc-cards");
    if (!grid) return;
    Object.keys(sparks).forEach(function (k) { try { sparks[k].destroy(); } catch (e) {} });
    sparks = {};
    grid.innerHTML = "";
    CYCLES.forEach(function (c) {
      var m = MODELS[c.id], ph = PHASES[c.now.phase] || {};
      var card = el("article", "cyc-card");
      card.setAttribute("data-id", c.id);
      card.style.setProperty("--c", c.accent);
      var tilt = TILT[c.proj.tilt] || TILT.mixed;
      var pct = Math.round(m.legPct * 100);
      var legLab = curLang() === "zh" ? ("距下次" + turnWord(c.proj.nextTurn, false) + " " + pct + "%") : (pct + "% to next " + c.proj.nextTurn);
      var elapsedChip = m.elapsed
        ? '<div class="cc-elapsed">' + L("Projection window passed — awaiting re-research", "投影窗口已过 — 待重新研究") + '</div>'
        : '';
      card.innerHTML =
        '<div class="cc-top">' +
          '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + zc(c.id, "name", c.name) + '</div>' +
          '<div class="cc-px">' + zc(c.id, "proxy", c.proxy) + '</div></div></div>' +
          '<div class="cc-phase" style="--ph:' + (ph.hue || "var(--muted)") + '">' + phaseChip(c.now.phase) + '</div>' +
        '</div>' +
        '<div class="cc-spark"></div>' +
        elapsedChip +
        '<div class="cc-meta">' +
          '<div class="cc-leg"><div class="cc-leg-bar"><i style="width:' + pct + '%"></i></div>' +
            '<div class="cc-leg-lab">' + legLab + '</div></div>' +
          '<div class="cc-next"><span class="cc-arrow">' + (c.proj.nextTurn === "peak" ? "▲" : "▼") + '</span>' +
            '<span>' + turnWord(c.proj.nextTurn, true) + ' ≈ ' + fmtMon(c.proj.central) + '</span>' +
            '<span class="cc-tilt ' + tilt.cls + '">' + tilt.ar + ' ' + tiltLab(tilt) + '</span></div>' +
        '</div>';
      card.addEventListener("click", function () { toggleFocus(c.id); });
      grid.appendChild(card);
      // sparkline — same model, no axes/bands/crosshair
      var sp = card.querySelector(".cc-spark");
      sparks[c.id] = window.MMChart.create(sp, {
        xDomain: [Math.max(META.xDomain[0], m.hist.length ? m.hist[0].x : 2004), m.projEnd],
        yDomain: [0, 100], padding: { t: 8, r: 6, b: 8, l: 6 },
        crosshair: false, animate: true, zoom: false,
        series: [{ id: c.id, color: c.accent, width: 2, hist: m.hist, proj: m.proj, cone: m.cone,
                   markers: [{ x: META.today, y: m.nowY, kind: "now" }] }]
      });
    });
  }

  /* ---- focus orchestration ----------------------------------------------- */
  function toggleFocus(id) { setFocus(state.focus === id ? null : id); }

  function setFocus(id) {
    state.focus = id;
    if (heroChart) heroChart.focus(id);
    // chips
    document.querySelectorAll(".cyc-chip").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-id") === id);
      b.classList.toggle("off", !!id && b.getAttribute("data-id") !== id);
    });
    // cards
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      cd.classList.toggle("lit", cd.getAttribute("data-id") === id);
      cd.classList.toggle("dim", !!id && cd.getAttribute("data-id") !== id);
    });
    // panel
    renderPanel(id);
    // mobile sheet auto-expand on focus (desktop underbar is always visible)
    if (id && window.innerWidth <= 880) expandSheet(true);
    // hash — note: deliberately NO auto-scroll, focusing must not move the viewport
    try { history.replaceState(null, "", id ? "#" + id : location.pathname + location.search); } catch (e) {}
  }

  /* ---- detail panel ------------------------------------------------------ */
  function renderPanel(id) {
    var def = document.getElementById("cyc-panel-default");
    var foc = document.getElementById("cyc-panel-focus");
    if (!def || !foc) return;
    if (!id) {
      foc.classList.remove("show"); def.classList.add("show");
      return;
    }
    foc.innerHTML = focusHTML(CYCLES.filter(function (c) { return c.id === id; })[0]);
    var back = foc.querySelector(".cyc-back");
    if (back) back.addEventListener("click", function () { setFocus(null); });
    def.classList.remove("show"); foc.classList.add("show");
  }

  function focusHTML(c) {
    var m = MODELS[c.id], ph = PHASES[c.now.phase] || {}, tilt = TILT[c.proj.tilt] || TILT.mixed;
    function fact(k, v) { return '<div class="f"><div class="fk">' + k + '</div><div class="fv">' + v + '</div></div>'; }
    var pct = Math.round(m.legPct * 100);
    var posVal = curLang() === "zh" ? ("距下一拐点 " + pct + "%") : (pct + "% to next turn");
    var lenVal = c.period.central + L(" yr (", " 年 (") + c.period.low + "–" + c.period.high + ")";
    var elapsedBanner = m.elapsed
      ? '<div class="cyc-elapsed-panel">' + L("Projection window passed — awaiting re-research", "投影窗口已过 — 待重新研究") + '</div>'
      : '';
    return '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<button class="cyc-back">' + L("← All cycles", "← 全部周期") + '</button>' +
        '<div class="cyc-fhead" style="--c:' + c.accent + '">' +
          '<div class="cyc-ftitle">' + zc(c.id, "name", c.name) + '</div>' +
          '<div class="cyc-fsub">' + zc(c.id, "proxy", c.proxy) + '</div>' +
          '<div class="cyc-fchips">' +
            '<span class="cyc-pchip" style="--ph:' + (ph.hue || "var(--muted)") + '">' + zc(c.id, "phaseLabel", c.now.phaseLabel) + '</span>' +
            '<span class="cyc-tchip ' + tilt.cls + '">' + tilt.ar + ' ' + tiltLab(tilt) + '</span>' +
          '</div>' +
        '</div>' +
        elapsedBanner +
        '<p class="cyc-arche">' + zc(c.id, "archetype", c.archetype) + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-facts">' +
          fact(L("Last trough", "上次底部"), fmtMon(c.now.lastTrough)) +
          fact(L("Last peak", "上次顶部"), fmtMon(c.now.lastPeak)) +
          fact(L("Next " + c.proj.nextTurn, "下次" + turnWord(c.proj.nextTurn, true)), fmtMon(c.proj.central)) +
          fact(L("Est. range", "预计区间"), fmtMon(c.proj.low) + " – " + fmtMon(c.proj.high)) +
          fact(L("Typical length", "典型周期"), lenVal) +
          fact(L("Position", "当前位置"), posVal) +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-read"><div class="cyc-lbl">' + L("The read", "解读") + '</div><p>' + zc(c.id, "read", c.now.read) + '</p></div>' +
        '<div class="cyc-fals"><div class="cyc-lbl">' + L("Falsifier", "证伪条件") + '</div><p>' + zc(c.id, "falsifier", c.proj.falsifier) + '</p></div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-drivers"><div class="cyc-lbl">' + L("Swing factors", "关键变量") + '</div><ul>' +
          zcArr(c.id, "drivers", c.proj.drivers).map(function (d) { return "<li>" + d + "</li>"; }).join("") + '</ul></div>' +
        '<div class="cyc-regnote">' + zc(c.id, "regimeNote", c.regimeNote) + '</div>' +
      '</div>';
  }

  /* ---- default panel content (regime + cross-cycle map) ------------------ */
  function buildDefaultPanel() {
    var def = document.getElementById("cyc-panel-default");
    if (!def) return;
    var R = META.regime;
    var zst = (window.CYCLE_ZH && window.CYCLE_ZH.regime && window.CYCLE_ZH.regime.stats) || [];
    var zh = curLang() === "zh";
    var stats = R.stats.map(function (s, i) {
      var k = zh && zst[i] ? zst[i].k : s.k, note = zh && zst[i] ? zst[i].note : s.note;
      return '<div class="rg-stat"><div class="rg-k">' + k + '</div><div class="rg-v">' + s.v + '</div><div class="rg-n">' + note + '</div></div>';
    }).join("");

    // cross-cycle buckets by direction-aware phase (a low cycle DESCENDING is
    // "declining", not "recovering" — level alone can't tell them apart)
    var buckets = { Peak: [], Expansion: [], Downturn: [], Recovery: [], Trough: [] };
    CYCLES.forEach(function (c) { (buckets[c.now.phase] || (buckets[c.now.phase] = [])).push(c); });
    function row(title, list, note) {
      if (!list.length) return "";
      var chips = list.map(function (c) {
        return '<button class="mini-chip" data-id="' + c.id + '" style="--c:' + c.accent + '"><span class="dot"></span>' + zc(c.id, "short", c.short) + '</button>';
      }).join("");
      return '<div class="xc-row"><div class="xc-rh">' + title + '<span>' + note + '</span></div><div class="xc-chips">' + chips + '</div></div>';
    }

    def.innerHTML = '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<div class="cyc-lbl">' + L("Macro regime · ", "宏观环境 · ") + META.asOf + '</div>' +
        '<div class="rg-head"><div class="rg-label">' + zr("label", R.label) + '</div><div class="rg-sub">' + zr("sub", R.sub) + '</div></div>' +
        '<p class="rg-headline">' + zr("headline", R.headline) + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Conditions", "环境指标") + '</div>' +
        '<div class="rg-stats">' + stats + '</div>' +
        '<p class="rg-tilt">' + zr("tilt", R.tilt) + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Where the cycles stand", "各周期所处位置") + '</div>' +
        '<div class="xc-map">' +
          row(L("Topping · late", "见顶 · 晚期"), buckets.Peak, L("thin cushion", "缓冲薄弱")) +
          row(L("Expanding", "扩张中"), buckets.Expansion, L("trending up", "上行趋势")) +
          row(L("Rolling over", "回落中"), buckets.Downturn, L("declining", "下行中")) +
          row(L("Recovering", "复苏中"), buckets.Recovery, L("early up-leg", "上行初段")) +
          row(L("Bottoming", "筑底中"), buckets.Trough, L("washed-out · cheap", "超卖 · 便宜")) +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("How to read", "如何解读") + '</div>' +
        '<ul class="cyc-how">' +
          '<li>' + L("<b>Solid</b> lines are observed history; <b>dashed + shaded cone</b> is the projected path and its uncertainty.", "<b>实线</b>为已观测历史；<b>虚线 + 阴影锥</b>为推演路径及其不确定性。") + '</li>' +
          '<li>' + L("Each <b>● dot</b> on the TODAY line is where that cycle sits right now — high = euphoric/late, low = washed-out/stressed.", "TODAY 线上的每个 <b>● 圆点</b>是该周期当下所处的位置——越高=狂热/晚期，越低=超卖/承压。") + '</li>' +
          '<li>' + L("<b>Tap a cycle</b> (chip, card, or its line) to focus it; tap again to return here.", "<b>点按某个周期</b>（标签、卡片或其曲线）以聚焦；再次点按返回此处。") + '</li>' +
        '</ul>' +
      '</div>';

    def.querySelectorAll(".mini-chip").forEach(function (b) {
      b.addEventListener("click", function () { setFocus(b.getAttribute("data-id")); });
    });
    def.classList.add("show");
  }

  /* ---- mobile bottom sheet ----------------------------------------------- */
  function expandSheet(on) {
    var sheet = document.getElementById("cyc-detail");
    if (sheet) sheet.classList.toggle("expanded", on !== false);
  }
  function initSheet() {
    var sheet = document.getElementById("cyc-detail");
    var handle = document.getElementById("cyc-handle");
    if (!sheet || !handle) return;
    handle.addEventListener("click", function () { sheet.classList.toggle("expanded"); });
    var startY = 0, startExpanded = false, dragging = false;
    handle.addEventListener("touchstart", function (e) { startY = e.touches[0].clientY; startExpanded = sheet.classList.contains("expanded"); dragging = true; }, { passive: true });
    handle.addEventListener("touchmove", function (e) {
      if (!dragging) return;
      var dy = e.touches[0].clientY - startY;
      if (dy < -30) sheet.classList.add("expanded");
      else if (dy > 40) sheet.classList.remove("expanded");
    }, { passive: true });
    handle.addEventListener("touchend", function () { dragging = false; });
  }

  /* ---- staleness banner (W0.1) -------------------------------------------
     When more than 14 days have passed since the dataset was last curated,
     show an amber (14–59 d) or red (≥ 60 d) banner near the page header.
     Uses L(en, zh) so no translated text appears in HTML attributes. */
  function renderStalenessBanner() {
    var host = document.getElementById("cyc-stale-banner");
    if (!host) return;
    var asOf = META.asOf || "";
    var asOfYear = asOf ? yf(asOf) : TODAY;
    var days = Math.round((TODAY - asOfYear) * 365.25);
    if (days < 14) { host.innerHTML = ""; return; }
    var cls = days >= 60 ? "stale-red" : "stale-amber";
    host.innerHTML = '<div class="stale-banner ' + cls + '">' +
      L("Curated dataset as of " + asOf + " — " + days + " days old",
        "精选数据截至 " + asOf + " — 已 " + days + " 天未更新") +
      '</div>';
  }

  /* ---- language switch: re-render the JS-drawn DOM, preserving filter + focus
     (the hero chart re-renders itself on `langchange`; its tooltip reads the
     language live). ------------------------------------------------------- */
  function rerender() {
    var savedFocus = state.focus, savedPhase = {};
    PHASE_FILTER.forEach(function (p) { savedPhase[p.key] = phaseState[p.key]; });
    mountChips();
    mountCards();
    buildDefaultPanel();
    buildZoom();
    buildGroups();                                              // resets phaseState
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = savedPhase[p.key]; });
    syncGroups();                                               // re-apply filter to fresh DOM
    renderStalenessBanner();
    if (heroChart) {                                            // refresh axis/band labels + keep zoom-reset chip in sync
      heroChart.spec = heroSpec();
      heroChart.resize();
      var v = heroChart.getView(), f = META.xDomain, z = document.getElementById("cyc-zoom");
      if (z) z.classList.toggle("zoomed", v[0] > f[0] + 1e-3 || v[1] < f[1] - 1e-3);
    }
    if (savedFocus) setFocus(savedFocus); else renderPanel(null);
  }

  /* ---- boot -------------------------------------------------------------- */
  function boot() {
    if (!META || !CYCLES) return;
    mountChips();
    mountHero();
    buildDefaultPanel();
    mountCards();
    renderStalenessBanner();
    initSheet();
    document.addEventListener("langchange", rerender);
    // deep-link focus
    var h = (location.hash || "").replace("#", "");
    if (h && MODELS[h]) setTimeout(function () { setFocus(h); }, 350);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

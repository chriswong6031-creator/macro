/* ============================================================================
   cycle_app.js — Cycle Intelligence Dashboard · orchestration (ENGINE-BACKED, D3-W3.2)
   ----------------------------------------------------------------------------
   The flagship no longer synthesises a cosine from hand-typed numbers.  Every
   MEASURED band's oscillator, turns and projection come from window.CYCLE_ENGINE
   (built by scripts/build_cycle.py over the proxy registry's live tapes); FRAME
   bands render the curated turning-point timeline + the A8 leg-length text with
   NOTHING resolving to a scalar position.  DUAL cards stack a MEASURED chart above
   a thin secular FRAME strip.  The hand-drawn cosine is retired for measured bands;
   the curated prose survives as a dated, clearly-labelled OPINION overlay.

   Two user-facing words only (ruling A3): MEASURED and FRAME.  proxy / monthly /
   basis / epoch / fitness live in a hover "how computed" line, never as chips.
   ========================================================================== */
(function () {
  "use strict";

  var ENGINE = window.CYCLE_ENGINE;
  if (!ENGINE) return;                                   // engine data is mandatory
  // legacy curated seed (phase hues + regime block still come from cycle_data.js)
  var SEED_META = window.CYCLE_META || {};
  var PHASES = window.CYCLE_PHASES || {};

  var XDOM = ENGINE.xDomain || [2004, 2031];
  var AS_OF = ENGINE.as_of || SEED_META.asOf || "";
  var ORDER = (ENGINE.order || []).slice();
  var CY = ENGINE.cycles || {};
  var REGIME = ENGINE.regime || (SEED_META.regime || {});
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /* ---- wall-clock TODAY (W0.1) -------------------------------------------- */
  function yfNow(d) {
    var y = d.getFullYear(), a = new Date(y, 0, 1), b = new Date(y + 1, 0, 1);
    return y + (d - a) / (b - a);
  }
  var TODAY = (function () {
    try { var n = new Date(); if (isFinite(n.getTime())) return yfNow(n); } catch (e) {}
    return SEED_META.today || (XDOM[0] + XDOM[1]) / 2;
  }());

  /* ---- i18n: EN default, 中文 when <html data-lang="zh"> ------------------- */
  function curLang() { return document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"; }
  function L(en, zh) { return curLang() === "zh" ? zh : en; }
  function zc(id, field, en) { if (curLang() !== "zh") return en; var z = (window.CYCLE_ZH && window.CYCLE_ZH.cycles || {})[id]; return z && z[field] != null && z[field] !== "" ? z[field] : en; }
  function zcArr(id, field, enArr) { if (curLang() !== "zh") return enArr; var z = (window.CYCLE_ZH && window.CYCLE_ZH.cycles || {})[id]; return z && z[field] && z[field].length ? z[field] : enArr; }
  function zr(field, en) { if (curLang() !== "zh") return en; var r = window.CYCLE_ZH && window.CYCLE_ZH.regime; return r && r[field] != null ? r[field] : en; }
  var PHASE_LAB = { Peak: ["Peak", "见顶"], Expansion: ["Expansion", "扩张"], Downturn: ["Downturn", "回落"], Recovery: ["Recovery", "复苏"], Trough: ["Trough", "筑底"] };
  function phaseChip(k) { var p = PHASE_LAB[k] || [k, k]; return L(p[0], p[1]); }
  function turnWord(nt, cap) { return nt === "peak" ? L(cap ? "Peak" : "peak", "见顶") : L(cap ? "Trough" : "trough", "筑底"); }

  /* ---- small helpers ----------------------------------------------------- */
  function yf(t) { if (t == null) return null; var p = String(t).split("-"); return +p[0] + ((+p[1] || 6) - 0.5) / 12; }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function fmtMon(t) {
    if (!t) return ""; var p = String(t).split("-"), m = (+p[1] || 6), yy = String(p[0]).slice(2);
    return curLang() === "zh" ? (yy + "年" + m + "月") : (MONTHS[m - 1] + " ’" + yy);
  }
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

  /* ---- tier vocabulary (ruling A3: exactly MEASURED / FRAME) --------------
     The tone-neutral chip is the ONLY user-facing tier word.  Everything else
     (proxy / monthly / basis / epoch / fitness) rides a hover "how computed"
     line — never a competing chip.  zh: 已测量 / 框架. */
  function tierChip(band) {
    if (band.tier === "measured") return { lab: L("MEASURED", "已测量"), cls: "tier-measured" };
    return { lab: L("FRAME", "框架"), cls: "tier-frame" };
  }
  // "how computed" hover text (dual-span-free: title attr is plain EN per house rule;
  // the visible micro-line uses L()). Carries proxy/basis/epoch/fitness detail.
  function measuredBasisLine(band) {
    var basisMap = {
      spot: L("spot price", "现货价"), futures_cont: L("continuous futures", "连续期货"),
      fred_level: L("FRED level series", "FRED 水平序列"), etf_tr: L("ETF, total-return basis", "ETF · 全收益口径"),
      etf_px: L("ETF, price basis", "ETF · 价格口径"), index_px: L("index, price basis", "指数 · 价格口径"),
      equity_px: L("equity proxy, price basis", "股票代理 · 价格口径")
    };
    var ref = band.ref ? band.ref.split(":").pop() : "";
    var basis = basisMap[band.basis] || band.basis || "";
    var s = ref + " · " + basis;
    if (band.invert) s += " · " + L("inverted (risk-on)", "已反向（风险偏好）");
    if (band.freq === "M") s += " · " + L("monthly", "月度");
    return s;
  }
  function howComputed(card, band) {
    // the full disclosure line under a MEASURED chart: series, basis, epoch, span, n_turns.
    var bits = [measuredBasisLine(band)];
    if (band.series_first && band.series_last) bits.push(band.series_first + " → " + band.series_last);
    if (band.n_turns_all != null) bits.push(band.n_turns_all + " " + L("turns", "拐点"));
    if (band.proxy && band.fitness) {
      var f = band.fitness;
      bits.push(L("proxy timing: " + f.matched + "/" + f.n_hand + " hand turns matched",
                  "代理择时：" + f.matched + "/" + f.n_hand + " 个人工拐点匹配")
                + (f.low_confidence ? L(" (low-n)", "（小样本）") : ""));
    }
    return bits.join(" · ");
  }

  /* ---- MODEL: build a hero series from an engine MEASURED band ------------
     The engine's `osc` is the 0-100 detrended-stochastic oscillator that IS the
     cross-cycle overlay axis — so the hero line is the engine's own read, not a
     synthesised cosine.  The projection draws from the engine's proj (anchored at
     the last CONFIRMED turn, W1.6): dashed toward the next-turn direction at
     central_x, with a timing cone (low→high).  Overdue → dimmed, no fresh cone. */
  var NEAR_PEAK = 92, NEAR_TROUGH = 8;
  function measuredBand(card) {
    var b = null;
    (card.bands || []).forEach(function (bd) { if (bd.tier === "measured" && !b) b = bd; });
    return b;
  }
  function frameBand(card) {
    var b = null;
    (card.bands || []).forEach(function (bd) { if (bd.tier === "frame") b = bd; });
    return b;
  }

  function buildMeasured(card) {
    var band = measuredBand(card);
    if (!band) return null;
    var osc = (band.osc || []).slice().sort(function (a, c) { return a.x - c.x; });
    // DISPLAY smoothing only: the raw detrended-STOCHASTIC oscillator is high-frequency
    // (jumps 0↔100 between weekly bars), which turns a 19-line overlay into a scribble.
    // A short trailing EMA gives a legible cycle line WITHOUT moving any turn / position /
    // projection (those are the engine's confirmed pivots, plotted as markers, untouched).
    var hist = emaSmooth(osc.map(function (p) { return { x: p.x, y: clamp(p.v, 0, 100) }; }), 0.28);
    // trim to points ≤ today (osc is causal but a monthly stamp can post one period ahead)
    hist = hist.filter(function (p) { return p.x <= TODAY + 0.02; });
    var lastPt = hist.length ? hist[hist.length - 1] : { x: TODAY, y: (band.now && band.now.pos) || 50 };
    var pj = band.proj || null;
    var nowPos = band.now && band.now.pos != null ? band.now.pos : lastPt.y;

    var proj = [], cone = [], elapsed = false, tc = null;
    if (pj) {
      var nextTrough = pj.nextTurn === "trough";
      var nextY = nextTrough ? NEAR_TROUGH : NEAR_PEAK;
      tc = yf(pj.central);
      var te = yf(pj.low), tl = yf(pj.high);
      elapsed = !!pj.overdue || (tc != null && tc < TODAY);
      var from = { x: lastPt.x, y: lastPt.y };
      if (elapsed) {
        // overdue: draw the projected leg to its ORIGINAL (engine) central date, dimmed —
        // never push it forward (W0.1 doctrine, enforced by W1.6's anchored projection).
        var end = Math.max(tc || from.x, from.x + 0.05);
        proj = rampTo(from, { x: end, y: nextY });
      } else {
        proj = rampTo(from, { x: tc, y: nextY });
        // timing cone: early (te) vs late (tl) turn dates → a spread band that widens with
        // horizon.  Amplitude of the engine's own IQR half-cycle, NOT a magic lerp.
        var lo = [], hi = [];
        var eLeg = rampTo(from, { x: Math.max(te || tc, from.x + 0.02), y: nextY });
        var lLeg = rampTo(from, { x: Math.max(tl || tc, from.x + 0.05), y: nextY });
        cone = coneBetween(eLeg, lLeg, proj);
      }
    }
    return {
      id: card.id, color: card.accent, label: card.name, width: 2,
      hist: hist, proj: proj, cone: cone,
      markers: turnMarkers(card, band, lastPt),
      nowY: lastPt.y, nowPos: nowPos, elapsed: elapsed, tc: tc,
      band: band, card: card
    };
  }

  // trailing EMA over {x,y} points — DISPLAY smoothing for the noisy stochastic osc line.
  // Purely cosmetic: the plotted turn markers + engine position/projection are unaffected.
  function emaSmooth(pts, alpha) {
    if (!pts.length) return pts;
    var out = [{ x: pts[0].x, y: pts[0].y }], prev = pts[0].y;
    for (var i = 1; i < pts.length; i++) { prev = alpha * pts[i].y + (1 - alpha) * prev; out.push({ x: pts[i].x, y: prev }); }
    return out;
  }

  // a monotone time-ramp from a→b using a cosine ease (keeps the familiar cycle-curve feel)
  function rampTo(a, b) {
    var out = [], step = 0.08;
    if (b.x <= a.x) return [{ x: a.x, y: a.y }, { x: a.x + 0.02, y: b.y }];
    for (var x = a.x; x < b.x - 1e-6; x += step) {
      var t = clamp((x - a.x) / (b.x - a.x), 0, 1);
      out.push({ x: x, y: a.y + (b.y - a.y) * (0.5 - 0.5 * Math.cos(Math.PI * t)) });
    }
    out.push({ x: b.x, y: b.y });
    return out;
  }
  // build a {x,lo,hi} cone enclosing the early/central/late projection legs
  function coneBetween(early, late, center) {
    var byX = {};
    function add(arr) { arr.forEach(function (p) { var k = p.x.toFixed(3); (byX[k] || (byX[k] = { x: p.x, v: [] })).v.push(p.y); }); }
    add(early); add(late); add(center);
    return Object.keys(byX).map(function (k) { return byX[k]; })
      .sort(function (a, b) { return a.x - b.x; })
      .map(function (o) {
        var lo = Math.min.apply(null, o.v), hi = Math.max.apply(null, o.v);
        var pad = clamp((o.x - center[0].x) * 6, 0.5, 10);          // widens with horizon
        return { x: o.x, lo: clamp(lo - pad, 2, 98), hi: clamp(hi + pad, 2, 98) };
      });
  }
  function turnMarkers(card, band, lastPt) {
    var ms = [];
    (band.turns || []).forEach(function (t) {
      if (t.x == null || t.osc == null) return;
      if (t.x < XDOM[0] - 0.2) return;
      if (t.provisional) return;                     // provisional pivots aren't confirmed turns
      ms.push({ x: t.x, y: clamp(t.osc, 0, 100), kind: t.k, label: fmtMon(t.t), sub: turnSub(card, t) });
    });
    ms.push({ x: lastPt.x, y: lastPt.y, kind: "now", label: L("Now", "当前"),
              sub: zc(card.id, "phaseLabel", (band.now && band.now.phaseLabel) || "") });
    return ms;
  }
  // marker tooltip subtitle: the coincident curated event if a hand turn sits nearby, else px
  function turnSub(card, t) {
    var seed = matchSeedTurn(card, t);
    if (seed && seed.e) return seed.e;
    return t.px != null ? (L("level ", "水平 ") + t.px) : "";
  }
  function matchSeedTurn(card, engineTurn) {
    // the OPINION overlay carries curated events; the frame band (if any) carries turns[].
    var fb = frameBand(card);
    var pool = (fb && fb.turns) || [];
    var ex = yf(engineTurn.t), best = null, bd = 99;
    pool.forEach(function (s) { if (s.k === engineTurn.k) { var d = Math.abs(yf(s.t) - ex); if (d < bd) { bd = d; best = s; } } });
    return bd <= 0.6 ? best : null;
  }

  // MODELS: only MEASURED / DUAL cards contribute an oscillator model to the hero.
  var MODELS = {};
  ORDER.forEach(function (id) {
    var card = CY[id];
    if (card && card.card_tier === "measured") MODELS[id] = buildMeasured(card);
  });
  var HERO_ORDER = ORDER.filter(function (id) { return MODELS[id] && MODELS[id].hist && MODELS[id].hist.length; });

  /* ---- hero overlay ------------------------------------------------------ */
  var heroChart = null, state = { focus: null };
  function heroSpec() {
    return {
      xDomain: XDOM, yDomain: [0, 100],
      xTicks: window.MMChart.niceYearTicks(XDOM[0] + 1, XDOM[1], 5),
      yTicks: [{ v: NEAR_TROUGH, label: L("Trough", "底部") }, { v: 50, label: L("Mid", "中位") }, { v: NEAR_PEAK, label: L("Peak", "顶部") }],
      padding: { t: 16, r: 16, b: 28, l: 46 },
      bands: [
        { y0: 0, y1: 35, color: "var(--down)", opacity: 0.05, label: L("washed-out", "超卖") },
        { y0: 35, y1: 65, color: "var(--muted)", opacity: 0.04, label: L("mid-cycle", "中段") },
        { y0: 65, y1: 100, color: "var(--warn)", opacity: 0.055, label: L("euphoric", "狂热") }
      ],
      guides: [{ x: TODAY, label: L("TODAY", "当前"), kind: "today" }],
      animate: true, crosshair: true, zoom: true,
      series: HERO_ORDER.map(function (id) { return MODELS[id]; }),
      tip: heroTip,
      onPick: function (id) { toggleFocus(id); },
      onZoom: function (domain, zoomed) { var z = document.getElementById("cyc-zoom"); if (z) z.classList.toggle("zoomed", zoomed); }
    };
  }
  function heroTip(d, pt, xVal) {
    var card = d.card, rising = pt.b ? pt.b.y >= pt.a.y : true;
    var near = Math.abs(xVal - TODAY) < 0.06;
    var fy = Math.floor(xVal), fmo = clamp(Math.floor((xVal - fy) * 12), 0, 11);
    var ds = near ? L("Now", "当前") : (curLang() === "zh" ? (fy + "年" + (fmo + 1) + "月") : (MONTHS[fmo] + " " + fy));
    var head = '<div class="mmc-tip-h"><span class="dot" style="background:' + d.color + '"></span>' + zc(card.id, "name", card.name) + '</div>';
    var yr = '<div class="mmc-tip-yr">' + ds + '</div>';
    var z = '<div class="mmc-tip-z">' + zone(pt.y) + ' · ' + (rising ? L("rising", "上行") : L("easing", "回落")) + '</div>';
    var ph = near ? '<div class="mmc-tip-ph">' + zc(card.id, "phaseLabel", (d.band.now && d.band.now.phaseLabel) || "") + '</div>' : '';
    return head + yr + z + ph;
  }
  function mountHero() {
    var node = document.getElementById("cyc-chart");
    if (!node) return;
    heroChart = window.MMChart.create(node, heroSpec());
    buildZoom();
    buildGroups();
  }

  /* ---- zoom controls ----------------------------------------------------- */
  function buildZoom() {
    var z = document.getElementById("cyc-zoom");
    if (!z) return;
    var presets = [
      { label: L("Full", "全部"), d: XDOM },
      { label: L("15y", "15年"), d: [XDOM[1] - 15, XDOM[1]] },
      { label: L("8y", "8年"), d: [XDOM[1] - 9, XDOM[1] - 1] },
      { label: L("Cycle", "本轮"), d: [Math.round(TODAY) - 2, Math.round(TODAY) + 3] }
    ];
    z.innerHTML = '<span class="cyc-zhint">' + L("scroll · drag", "滚动 · 拖拽") + '</span>' +
      presets.map(function (p, i) { return '<button class="cyc-zbtn" data-i="' + i + '">' + p.label + '</button>'; }).join("") +
      '<button class="cyc-zbtn cyc-zreset" id="cyc-zreset">' + L("Reset ⤢", "重置 ⤢") + '</button>';
    presets.forEach(function (p, i) {
      z.querySelector('[data-i="' + i + '"]').addEventListener("click", function () { if (heroChart) heroChart.setView(p.d.slice(), true); });
    });
    z.querySelector("#cyc-zreset").addEventListener("click", function () { if (heroChart) heroChart.resetZoom(); });
  }

  /* ---- phase filter — MEASURED cards bucket by engine phase; FRAME cards get
     their own bucket ("Frames — structural") so a curated frame NEVER shares a
     ranked position bucket with a measured read (audit A-1 root disease). ----- */
  var PHASE_FILTER = [
    { key: "Peak", label: "Topping", zh: "见顶" },
    { key: "Expansion", label: "Expanding", zh: "扩张中" },
    { key: "Downturn", label: "Rolling over", zh: "回落中" },
    { key: "Recovery", label: "Recovering", zh: "复苏中" },
    { key: "Trough", label: "Bottoming", zh: "筑底中" },
    { key: "Frame", label: "Frames", zh: "框架" }
  ];
  function cardPhase(card) {
    if (card.card_tier !== "measured") return "Frame";
    var mb = measuredBand(card);
    return (mb && mb.now && mb.now.phase) || "Frame";
  }
  var phaseState = {};
  function buildGroups() {
    var host = document.getElementById("cyc-groups");
    if (!host) return;
    var counts = {};
    ORDER.forEach(function (id) { var p = cardPhase(CY[id]); counts[p] = (counts[p] || 0) + 1; });
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = true; });
    host.innerHTML = '<span class="cyc-glabel">' + L("Where they stand", "所处阶段") + '</span>' +
      PHASE_FILTER.map(function (p) {
        var hue = p.key === "Frame" ? "var(--muted)" : ((PHASES[p.key] || {}).hue || "var(--muted)");
        return '<button class="cyc-gchip on" data-k="' + p.key + '" style="--ph:' + hue + '"><span class="gdot"></span>' + L(p.label, p.zh) + ' <i>' + (counts[p.key] || 0) + '</i></button>';
      }).join("") +
      '<button class="cyc-gall" id="cyc-gall" title="Show all phases"><span class="ga-dots">' +
        PHASE_FILTER.map(function (p) { return '<i style="background:' + (p.key === "Frame" ? "var(--muted)" : ((PHASES[p.key] || {}).hue || "var(--muted)")) + '"></i>'; }).join("") +
      '</span>' + L("Select all", "全选") + '</button>';
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
    if (gall) gall.classList.toggle("active", !allOn);
    applyGroupFilter();
  }
  function applyGroupFilter() {
    var allOff = PHASE_FILTER.every(function (p) { return !phaseState[p.key]; });
    var hidden = {};
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      var card = CY[cd.getAttribute("data-id")]; if (!card) return;
      var inF = allOff || phaseState[cardPhase(card)];
      cd.classList.toggle("gdim", !inF);
      cd.style.order = inF ? "0" : "1";
      if (!inF) hidden[card.id] = true;
    });
    document.querySelectorAll(".cyc-chip").forEach(function (b) {
      var card = CY[b.getAttribute("data-id")]; if (!card) return;
      b.classList.toggle("gdim", !(allOff || phaseState[cardPhase(card)]));
    });
    if (heroChart) heroChart.setHidden(hidden);
  }

  /* ---- toggle chips ------------------------------------------------------ */
  function mountChips() {
    var wrap = document.getElementById("cyc-chips");
    if (!wrap) return;
    wrap.innerHTML = "";
    ORDER.forEach(function (id) {
      var card = CY[id]; if (!card) return;
      var b = el("button", "cyc-chip");
      b.setAttribute("data-id", id);
      b.style.setProperty("--c", card.accent);
      if (card.card_tier !== "measured") b.classList.add("chip-frame");
      b.innerHTML = '<span class="dot"></span><span class="nm">' + zc(id, "short", card.short) + '</span>';
      b.addEventListener("click", function () { toggleFocus(id); });
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
    ORDER.forEach(function (id) {
      var card = CY[id]; if (!card) return;
      (card.card_tier === "measured" ? measuredCard : frameCard)(grid, card);
    });
  }

  function tierBadge(band, card) {
    var t = tierChip(band);
    var hint = band.tier === "measured"
      ? measuredBasisLine(band)
      : L("curated history — not a measured cycle", "人工整理的历史 — 非实测周期");
    // title attr is plain-English per house rule; the visible chip text is dual via L()
    var titleEn = band.tier === "measured"
      ? ("MEASURED · engine-computed from " + (band.ref || "") + " (" + (band.basis || "") + ")")
      : "FRAME · curated turning-point history, not a graded cycle";
    return '<span class="cyc-tier ' + t.cls + '" title="' + esc(titleEn) + '">' + t.lab +
      '<span class="cyc-tier-h">' + esc(hint) + '</span></span>';
  }

  function measuredCard(grid, card) {
    var m = MODELS[card.id];
    var band = measuredBand(card);
    // defensive: a measured card should always have a model + band + now; if the tape was
    // too short (record_series → None) and a frame band exists, render the frame instead.
    if (!m || !band || !band.now) { if (frameBand(card)) frameCard(grid, card); return; }
    var ph = PHASES[band.now.phase] || {};
    var carddiv = el("article", "cyc-card");
    carddiv.setAttribute("data-id", card.id);
    carddiv.style.setProperty("--c", card.accent);
    var pj = band.proj || {};
    var overdue = !!pj.overdue;
    var nextTW = pj.nextTurn ? turnWord(pj.nextTurn, false) : "";
    // leg progress = fraction of the median half-cycle elapsed since last confirmed turn.
    var legPct = overdue ? 100 : Math.round(clamp((pj.overdue_frac != null ? pj.overdue_frac : 0), 0, 1) * 100);
    var legLab = overdue
      ? L("turn window passed", "拐点窗口已过")
      : (curLang() === "zh" ? ("距下次" + nextTW + " " + legPct + "%") : (legPct + "% to next " + pj.nextTurn));
    var elapsedChip = overdue
      ? '<div class="cc-elapsed">' + L("Turn window elapsed — engine projection anchored at last confirmed turn", "拐点窗口已过 — 引擎投影锚定于上次确认拐点") + '</div>'
      : '';
    var tolNote = band.tolerance
      ? '<div class="cc-tol' + (band.tolerance.loud ? ' loud' : '') + '">' +
        L("engine " + band.tolerance.engine_pos + " vs opinion " + band.tolerance.hand_pos + " (Δ" + (band.tolerance.delta > 0 ? "+" : "") + band.tolerance.delta + ")",
          "引擎 " + band.tolerance.engine_pos + " vs 观点 " + band.tolerance.hand_pos + "（Δ" + (band.tolerance.delta > 0 ? "+" : "") + band.tolerance.delta + "）") +
        '</div>'
      : '';
    carddiv.innerHTML =
      firedBannerHTML(card) +
      '<div class="cc-top">' +
        '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + zc(card.id, "name", card.name) + '</div>' +
        '<div class="cc-px">' + esc(measuredBasisLine(band)) + '</div></div></div>' +
        '<div class="cc-badges">' + tierBadge(band, card) +
          '<div class="cc-phase" style="--ph:' + (ph.hue || "var(--muted)") + '">' + phaseChip(band.now.phase) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="cc-spark"></div>' +
      elapsedChip +
      '<div class="cc-meta">' +
        '<div class="cc-leg"><div class="cc-leg-bar"><i style="width:' + legPct + '%"></i></div>' +
          '<div class="cc-leg-lab">' + legLab + '</div></div>' +
        '<div class="cc-next"><span class="cc-arrow">' + (pj.nextTurn === "peak" ? "▲" : "▼") + '</span>' +
          '<span>' + turnWord(pj.nextTurn, true) + ' ≈ ' + fmtMon(pj.central) + '</span></div>' +
      '</div>' +
      tolNote +
      tripwireStripHTML(card);
    carddiv.addEventListener("click", function () { toggleFocus(card.id); });
    grid.appendChild(carddiv);
    // sparkline — the SAME engine model, no axes/bands/crosshair
    var sp = carddiv.querySelector(".cc-spark");
    var x0 = m.hist.length ? m.hist[0].x : XDOM[0];
    var xEnd = m.tc != null && !m.elapsed ? m.tc + 0.4 : (m.hist.length ? m.hist[m.hist.length - 1].x + 0.5 : XDOM[1]);
    // spark markers: the engine's CONFIRMED turns in-window (visible on the single-series
    // spark via the .cc-spark CSS override) + the Now dot.
    var sparkMarks = (m.markers || []).filter(function (mk) { return mk.kind !== "now" && mk.x >= x0 - 0.1; });
    sparkMarks.push({ x: m.hist.length ? m.hist[m.hist.length - 1].x : TODAY, y: m.nowY, kind: "now" });
    sparks[card.id] = window.MMChart.create(sp, {
      xDomain: [Math.max(XDOM[0], x0), xEnd],
      yDomain: [0, 100], padding: { t: 8, r: 6, b: 8, l: 6 },
      crosshair: false, animate: true, zoom: false,
      series: [{ id: card.id, color: card.accent, width: 2, hist: m.hist, proj: m.proj, cone: m.cone,
                 markers: sparkMarks }]
    });
  }

  function frameCard(grid, card) {
    var band = frameBand(card);
    if (!band) return;
    var carddiv = el("article", "cyc-card card-frame");
    carddiv.setAttribute("data-id", card.id);
    carddiv.style.setProperty("--c", card.accent);
    var a8 = a8Text(band);
    var mon = (band.monitors || []).map(function (r) { return r.split(":").pop(); });
    carddiv.innerHTML =
      firedBannerHTML(card) +
      '<div class="cc-top">' +
        '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + zc(card.id, "name", card.name) + '</div>' +
        '<div class="cc-px">' + esc(zc(card.id, "proxy", (card.opinion && card.opinion.proxy) || "")) + '</div></div></div>' +
        '<div class="cc-badges">' + tierBadge(band, card) + '</div>' +
      '</div>' +
      '<div class="cc-timeline"></div>' +
      '<div class="cc-frame-a8">' + a8 + '</div>' +
      tripwireStripHTML(card) +
      (mon.length ? '<div class="cc-monitors"><span>' + L("Monitors", "监测指标") + '</span> ' + esc(mon.join(" · ")) + '</div>' : '');
    carddiv.addEventListener("click", function () { toggleFocus(card.id); });
    grid.appendChild(carddiv);
    mountTimeline(carddiv.querySelector(".cc-timeline"), card, band);
  }

  // A8 pattern: "last major turn {date} ({N}y ago); prior up-legs ran {list}".  Pure text,
  // nothing resolves to a scalar position.
  function a8Text(band) {
    var lt = band.last_turn, ys = band.years_since_last;
    var ups = (band.leg_lengths && band.leg_lengths.ups) || [];
    var head = lt
      ? L("Last major " + lt.k + " " + fmtMon(lt.t) + (ys != null ? " (" + ys + "y ago)" : ""),
          "上一次重大" + turnWord(lt.k, true) + " " + fmtMon(lt.t) + (ys != null ? "（" + ys + " 年前）" : ""))
      : "";
    var legs = ups.length
      ? L("Prior up-legs ran " + ups.map(function (v) { return v + "y"; }).join(", "),
          "此前的上行段历时 " + ups.map(function (v) { return v + " 年"; }).join("、"))
      : L("Too few turns to list prior legs", "拐点过少，无法列出此前周期段");
    var win = band.typical_window
      ? L(" · typical window " + Math.floor(band.typical_window.lo) + "–" + Math.ceil(band.typical_window.hi),
          " · 典型窗口 " + Math.floor(band.typical_window.lo) + "–" + Math.ceil(band.typical_window.hi))
      : "";
    return '<b>' + head + '.</b> ' + legs + '<span class="cc-frame-note">' + win + '</span>';
  }

  // FRAME timeline: the curated turns[] as dots on a single horizontal band (no oscillator).
  // The curated turning-point HISTORY is the crown-jewel content — show it all (no window
  // clip): a FRAME clock's 1970s/1980s pivots ARE the point of the card (A8 "prior legs").
  function mountTimeline(node, card, band) {
    if (!node) return;
    var turns = (band.turns || []).slice();
    var xs = turns.map(function (t) { return yf(t.t); });
    var x0 = xs.length ? Math.min.apply(null, xs) : XDOM[0];
    var x1 = xs.length ? Math.max.apply(null, xs) : XDOM[1];
    // pad the window so the typical-turn hatch (if any) shows
    if (band.typical_window) x1 = Math.max(x1, band.typical_window.hi);
    x1 = Math.max(x1, TODAY);
    var series = [{
      id: card.id, color: card.accent, width: 0, hist: [{ x: x0, y: 50 }, { x: x1, y: 50 }],
      markers: turns.map(function (t) {
        return { x: yf(t.t), y: 50, kind: t.k, label: fmtMon(t.t), sub: t.e };
      }).concat([{ x: TODAY, y: 50, kind: "now", label: L("Now", "当前") }])
    }];
    window.MMChart.create(node, {
      xDomain: [x0 - 0.5, x1 + 0.5], yDomain: [0, 100],
      padding: { t: 4, r: 8, b: 16, l: 8 }, crosshair: false, animate: true, zoom: false,
      xTicks: window.MMChart.niceYearTicks(Math.ceil(x0), Math.floor(x1), 4),
      series: series
    });
  }

  /* ---- W3.3: falsifier tripwire strip ------------------------------------- */
  /* Ruling A17: FIRED is latched (sticky), but always shows current_leg status
     so a recovered thesis shows "fired {date}; condition no longer met".
     State colors use severity tokens, NOT up/down tokens — zh flip is bypassed.
       ARMED        → green-neutral (.tw-armed)
       FIRED        → red alert (.tw-fired)
       MANUAL       → amber (.tw-manual)
       DATA_MISSING → grey (.tw-missing)
       EXPIRED      → grey (.tw-expired)                                       */
  function tripwireStripHTML(card) {
    var tws = card.tripwires || [];
    if (!tws.length) return "";

    var items = tws.map(function (tw) {
      var cls = "tw-item tw-" + (tw.state || "armed").toLowerCase().replace(/_/g, "-");
      var label = "", dot = "";

      if (tw.state === "FIRED") {
        dot = '<span class="tw-dot tw-dot-fired"></span>';
        var dateStr = tw.fired_on ? tw.fired_on.slice(0, 7) : "";
        var noLonger = (tw.current_leg === false)
          ? " · " + L("condition no longer met", "条件已不再满足")
          : "";
        label = '<span class="l-en"><b>' + L("FIRED", "已触发") + '</b>' +
                (dateStr ? " " + dateStr : "") + noLonger + '</span>' +
                '<span class="l-zh"><b>已触发</b>' +
                (dateStr ? " " + dateStr : "") + (tw.current_leg === false ? " · 条件已不再满足" : "") + '</span>';
      } else if (tw.state === "ARMED") {
        dot = '<span class="tw-dot tw-dot-armed"></span>';
        label = '<span class="l-en">' + L("armed", "监控中") + '</span>' +
                '<span class="l-zh">监控中</span>';
      } else if (tw.state === "MANUAL") {
        dot = '<span class="tw-dot tw-dot-manual"></span>';
        var overdue = tw.overdue_days && tw.overdue_days > 0
          ? " · " + L("review overdue " + tw.overdue_days + "d", "超期 " + tw.overdue_days + " 天")
          : (tw.manual && tw.manual.last_reviewed
              ? " · " + L("reviewed " + tw.manual.last_reviewed, "已审阅 " + tw.manual.last_reviewed)
              : "");
        label = '<span class="l-en">' + L("manual", "人工") + esc(overdue) + '</span>' +
                '<span class="l-zh">人工' + (tw.overdue_days && tw.overdue_days > 0
                  ? ' · 超期 ' + tw.overdue_days + ' 天' : '') + '</span>';
      } else if (tw.state === "DATA_MISSING") {
        dot = '<span class="tw-dot tw-dot-missing"></span>';
        label = '<span class="l-en">' + L("data missing", "数据缺失") + '</span>' +
                '<span class="l-zh">数据缺失</span>';
      } else if (tw.state === "EXPIRED") {
        dot = '<span class="tw-dot tw-dot-expired"></span>';
        label = '<span class="l-en">' + L("expired", "已过期") + '</span>' +
                '<span class="l-zh">已过期</span>';
      } else {
        dot = '<span class="tw-dot"></span>';
        label = '<span class="l-en">' + esc(tw.state || "") + '</span>' +
                '<span class="l-zh">' + esc(tw.state || "") + '</span>';
      }

      // claim tooltip (plain EN per house rule — no t() in attributes)
      var titleStr = (tw.claim || "") + (tw.state === "FIRED" && tw.current_leg === false
        ? " (condition no longer met — latch remains until v" + ((tw.version || 1) + 1) + ")"
        : "");

      return '<span class="' + cls + '" title="' + esc(titleStr) + '">' + dot + label + '</span>';
    }).join("");

    // summary prefix: count FIRED
    var nFired = tws.filter(function (tw) { return tw.state === "FIRED"; }).length;
    var nArmed = tws.filter(function (tw) { return tw.state === "ARMED"; }).length;
    var summary = nFired
      ? '<span class="tw-summary tw-summary-fired">' +
          '<span class="l-en">' + L("⚠ " + nFired + " falsifier fired", "⚠ " + nFired + " 项证伪已触发") + '</span>' +
          '<span class="l-zh">⚠ ' + nFired + ' 项证伪已触发</span>' +
        '</span>'
      : '<span class="tw-summary">' +
          '<span class="l-en">' + L(nArmed + " conditions live", nArmed + " 项条件监控中") + '</span>' +
          '<span class="l-zh">' + nArmed + ' 项条件监控中</span>' +
        '</span>';

    return '<div class="cc-tripwire tw-strip">' + summary + ' ' + items + '</div>';
  }

  /* FIRED banner: shown above the card when any tripwire is latched FIRED */
  function firedBannerHTML(card) {
    var tws = card.tripwires || [];
    var fired = tws.filter(function (tw) { return tw.state === "FIRED" && tw.latched; });
    if (!fired.length) return "";
    var msgs = fired.map(function (tw) {
      return esc(tw.claim) + (tw.fired_on ? " (" + tw.fired_on.slice(0, 10) + ")" : "");
    });
    var msgEn = "⚠ Falsifier fired: " + msgs.join("; ") + " — thesis refuted.";
    var msgZh = "⚠ 证伪触发：" + msgs.join("；") + " — 论点已被否定。";
    return '<div class="cc-fired-banner">' +
      '<span class="l-en">' + msgEn + '</span>' +
      '<span class="l-zh">' + msgZh + '</span>' +
    '</div>';
  }

  /* focus panel tripwire detail block */
  function focusTripwireBlock(card) {
    var tws = card.tripwires || [];
    if (!tws.length) return "";
    var rows = tws.map(function (tw) {
      var stateTag = tw.state === "FIRED"
        ? '<span class="tw-tag tw-tag-fired">' + L("FIRED", "已触发") + '</span>'
        : tw.state === "MANUAL"
        ? '<span class="tw-tag tw-tag-manual">' + L("MANUAL", "人工") + '</span>'
        : tw.state === "DATA_MISSING"
        ? '<span class="tw-tag tw-tag-missing">' + L("DATA MISSING", "数据缺失") + '</span>'
        : tw.state === "EXPIRED"
        ? '<span class="tw-tag tw-tag-expired">' + L("EXPIRED", "已过期") + '</span>'
        : '<span class="tw-tag tw-tag-armed">' + L("ARMED", "监控中") + '</span>';

      var a17 = (tw.state === "FIRED" && tw.current_leg === false)
        ? '<div class="tw-a17">' +
            '<span class="l-en">Condition no longer met — latch stays until re-authored (v' + ((tw.version || 1) + 1) + ')</span>' +
            '<span class="l-zh">条件已不再满足 — 锁存至重新编写（v' + ((tw.version || 1) + 1) + '）</span>' +
          '</div>'
        : "";

      var manualNote = tw.state === "MANUAL" && tw.manual
        ? '<div class="tw-manual-note">' +
            '<span class="l-en">Manual falsifier: ' + esc(tw.manual.note || "") +
            (tw.overdue_days && tw.overdue_days > 0
              ? ' <b>Review overdue ' + tw.overdue_days + 'd</b>' : '') + '</span>' +
            '<span class="l-zh">人工证伪：' + esc(tw.manual.note || "") +
            (tw.overdue_days && tw.overdue_days > 0
              ? ' <b>超期 ' + tw.overdue_days + ' 天</b>' : '') + '</span>' +
          '</div>'
        : "";

      return '<div class="tw-focus-row">' +
        '<div class="tw-focus-head">' + stateTag + ' <span class="tw-claim">' + esc(tw.claim) + '</span>' +
        '<span class="tw-dir"> · ' + esc(tw.direction) + '</span></div>' +
        a17 + manualNote +
      '</div>';
    }).join("");

    return '<div class="cyc-grp cyc-grp-full">' +
      '<div class="cyc-lbl">' + L("Falsifier tripwires", "证伪条件监控") + ' ' +
        '<span class="cyc-tier tier-frame" title="W3.3 live-evaluated tripwires">' +
          L("LIVE", "实时") + '</span></div>' +
      '<div class="tw-focus-list">' + rows + '</div>' +
    '</div>';
  }

  /* ---- focus orchestration ----------------------------------------------- */
  function toggleFocus(id) { setFocus(state.focus === id ? null : id); }
  function setFocus(id) {
    state.focus = id;
    if (heroChart) heroChart.focus(MODELS[id] ? id : null);   // frame cards have no hero line
    document.querySelectorAll(".cyc-chip").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-id") === id);
      b.classList.toggle("off", !!id && b.getAttribute("data-id") !== id);
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
    var def = document.getElementById("cyc-panel-default");
    var foc = document.getElementById("cyc-panel-focus");
    if (!def || !foc) return;
    if (!id || !CY[id]) { foc.classList.remove("show"); def.classList.add("show"); return; }
    foc.innerHTML = focusHTML(CY[id]);
    var back = foc.querySelector(".cyc-back");
    if (back) back.addEventListener("click", function () { setFocus(null); });
    def.classList.remove("show"); foc.classList.add("show");
  }

  function factRow(k, v) { return '<div class="f"><div class="fk">' + k + '</div><div class="fv">' + v + '</div></div>'; }

  function focusHTML(card) {
    var measured = card.card_tier === "measured";
    var mb = measuredBand(card), fb = frameBand(card);
    var op = card.opinion || {};
    var ph = (measured && mb.now && PHASES[mb.now.phase]) || {};
    var head =
      '<div class="cyc-grp cyc-grp-full">' +
        '<button class="cyc-back">' + L("← All cycles", "← 全部周期") + '</button>' +
        '<div class="cyc-fhead" style="--c:' + card.accent + '">' +
          '<div class="cyc-ftitle">' + zc(card.id, "name", card.name) +
            ' ' + focusTierBadge(measured ? mb : fb, card) + (card.dual ? ' ' + dualHint() : '') + '</div>' +
          '<div class="cyc-fsub">' + esc(zc(card.id, "proxy", op.proxy || card.name)) + '</div>' +
          (measured
            ? '<div class="cyc-fchips">' +
                '<span class="cyc-pchip" style="--ph:' + (ph.hue || "var(--muted)") + '">' + zc(card.id, "phaseLabel", (mb.now && mb.now.phaseLabel) || "") + '</span>' +
              '</div>'
            : '') +
        '</div>' +
        '<p class="cyc-arche">' + zc(card.id, "archetype", op.archetype || "") + '</p>' +
      '</div>';

    var facts = measured ? measuredFacts(card, mb) : frameFacts(card, fb);
    var opinion = opinionBlock(card, op, mb);
    var secular = (measured && fb) ? secularStrip(card, fb) : "";
    var tripwires = focusTripwireBlock(card);
    return head + facts + secular + opinion + tripwires;
  }
  function focusTierBadge(band, card) { return tierBadge(band, card); }
  function dualHint() { return '<span class="cyc-dual-hint">' + L("dual", "双轨") + '</span>'; }

  /* ---- W4.3 / UI-HZ-1 turn-hazard rows (MEASURED cards only) --------------
     Renders the calibrated turn-hazard row set from band.now.hazard: P(turn ≤ h)
     for h = 1m / 3m / 6m, each cell carrying its VISIBLE evidence badge from the
     W4.2 gate ledger (PASS = calibrated model probability, validated vs the
     family-stratified KM baseline; PRIOR = KM base rate, shown muted with the
     KM-prior wording). No naked probabilities — every number is badged (UI-HZ-1).
     The hover (title attr) carries: cell verdict wording, epoch, BACKTEST-cohort
     note (ruling A6: these are backtest-validated, live cohort accruing).
     Renders nothing if hazard data is absent (non-MEASURED or scorer unavailable). */
  function hazardLine(band) {
    var hz = band.now && band.now.hazard;
    if (!hz) return '';
    var epoch = hz.epoch || '';
    var revOpt = hz.revision_optimistic ? ' · revision-optimistic (quad not PIT-vintaged)' : '';
    var dir = hz.direction || '';

    function cell(key, label, labelZh) {
      var c = hz[key];
      if (!c || c.p == null) return '';
      var pct = Math.round(c.p * 100);
      var pass = (c.cell_verdict === 'PASS') || (c.source === 'MODEL');
      var badge = pass
        ? '<span class="hz-badge hz-pass"><span class="l-en">PASS</span><span class="l-zh">通过</span></span>'
        : '<span class="hz-badge hz-prior"><span class="l-en">PRIOR</span><span class="l-zh">先验</span></span>';
      var tip = pass
        ? ('Calibrated model probability — the ' + dir + '/' + key + ' cell PASSED the W4.2 gate ' +
           'vs the family-stratified KM baseline (OOS Brier + month-block bootstrap CI + BH-FDR). ' +
           'Epoch: ' + epoch + revOpt +
           ' · backtest-validated OOS; live cohort accruing (come-back: n_matured≥40 per cell)')
        : ('KM base-rate prior — the ' + dir + '/' + key + ' cell did NOT pass the W4.2 gate; ' +
           'this is the historical family-stratified base rate, not a validated model output. ' +
           'Epoch: ' + epoch + revOpt);
      return '<span class="hz-cell' + (pass ? '' : ' hz-muted') + '" title="' + esc(tip) + '">' +
        '<span class="l-en">' + label + ' ' + pct + '%</span>' +
        '<span class="l-zh">' + labelZh + ' ' + pct + '%</span> ' + badge +
      '</span>';
    }

    var cells = [
      cell('1m', 'P(turn ≤ 1m)', 'P(转折≤1月)'),
      cell('3m', '≤3m',  '≤3月'),
      cell('6m', '≤6m',  '≤6月'),
    ].filter(Boolean);
    if (!cells.length) return '';

    return '<div class="cyc-hazard">' +
      '<span class="hz-label" title="' + esc(
        'P(next confirmed turn within horizon) for the open ' + (dir || '?') + '-leg. ' +
        'PASS cells: isotonic-calibrated discrete-time hazard model (validated vs KM, W4.2 gate). ' +
        'PRIOR cells: KM base rate, shown muted. Display-only context — never a signal.'
      ) + '"><span class="l-en">Turn hazard (calibrated)</span><span class="l-zh">转折风险（校准）</span></span>' +
      cells.join('<span class="hz-sep"> · </span>') +
      '</div>';
  }

  function measuredFacts(card, band) {
    var pj = band.proj || {};
    var h = band.health || {};
    var provisional = (band.turns || []).some(function (t) { return t.provisional; });
    return '<div class="cyc-grp cyc-grp-3"><div class="cyc-facts">' +
      factRow(L("Series", "序列"), esc((band.ref || "").split(":").pop()) + ' <span class="fv-sub">' + esc(measuredBasisLine(band).split(" · ").slice(1).join(" · ")) + '</span>') +
      factRow(L("History", "历史区间"), (band.series_first || "?") + " → " + (band.series_last || "?")) +
      factRow(L("Confirmed turns", "已确认拐点"), (band.n_turns_all != null ? band.n_turns_all : "—") + (provisional ? L(" · +1 provisional", " · +1 待确认") : "")) +
      factRow(L("Last turn", "上次拐点"), (function () {
        var lt = null; (band.turns || []).forEach(function (t) { if (!t.provisional) lt = t; });
        return lt ? (fmtMon(lt.t) + " " + turnWord(lt.k, false)) : "—";
      })()) +
      factRow(L("Next " + (pj.nextTurn || "turn"), "下次" + turnWord(pj.nextTurn, true)), fmtMon(pj.central) + (pj.overdue ? L(" · overdue", " · 已过期") : "")) +
      factRow(L("Est. window", "预计区间"), fmtMon(pj.low) + " – " + fmtMon(pj.high)) +
      factRow(L("Typical length", "典型周期"), (pj.period_yrs ? (pj.period_yrs.median + L(" yr (", " 年 (") + pj.period_yrs.lo + "–" + pj.period_yrs.hi + ")") : "—")) +
      factRow(L("Position", "当前位置"), '<b>' + (band.now && band.now.pos != null ? band.now.pos : "—") + '</b> ' + L("(engine)", "（引擎）")) +
      '</div>' +
      hazardLine(band) +
      '<div class="cyc-howline">' + L("How computed", "计算方式") + ': ' + esc(howComputed(card, band)) + '</div>' +
      '</div>';
  }

  function frameFacts(card, band) {
    var lt = band.last_turn;
    var ups = (band.leg_lengths && band.leg_lengths.ups) || [];
    var downs = (band.leg_lengths && band.leg_lengths.downs) || [];
    return '<div class="cyc-grp cyc-grp-3"><div class="cyc-facts">' +
      factRow(L("Tier", "层级"), L("FRAME — structural clock, not graded", "框架 — 结构性时钟，不评分")) +
      factRow(L("Curated turns", "整理拐点"), (band.turns || []).length) +
      factRow(L("Last major turn", "上次重大拐点"), lt ? (fmtMon(lt.t) + " " + turnWord(lt.k, false) + (band.years_since_last != null ? L(" · " + band.years_since_last + "y ago", " · " + band.years_since_last + " 年前") : "")) : "—") +
      factRow(L("Prior up-legs", "此前上行段"), ups.length ? ups.map(function (v) { return v + L("y", "年"); }).join(", ") : "—") +
      factRow(L("Prior down-legs", "此前下行段"), downs.length ? downs.map(function (v) { return v + L("y", "年"); }).join(", ") : "—") +
      factRow(L("Typical window", "典型窗口"), band.typical_window ? (Math.floor(band.typical_window.lo) + "–" + Math.ceil(band.typical_window.hi) + " " + turnWord(band.typical_window.next, false)) : "—") +
      '</div>' +
      '<div class="cyc-howline">' + L("FRAME cards show curated timing only — no oscillator, no position gauge, no forecast cone.",
        "框架卡片仅展示人工整理的时点 — 无振荡指标、无位置刻度、无预测锥。") + '</div>' +
      '</div>';
  }

  // secular strip on DUAL cards (compact condensed frame timeline beneath the measured chart)
  function secularStrip(card, fb) {
    var lt = fb.last_turn, ys = fb.years_since_last;
    var ups = (fb.leg_lengths && fb.leg_lengths.ups) || [];
    var txt = lt
      ? L("Secular frame: last major " + lt.k + " " + fmtMon(lt.t) + (ys != null ? " (" + ys + "y ago)" : "") + (ups.length ? "; prior up-legs " + ups.map(function (v) { return v + "y"; }).join(", ") : ""),
          "长周期框架：上一次重大" + turnWord(lt.k, true) + " " + fmtMon(lt.t) + (ys != null ? "（" + ys + " 年前）" : "") + (ups.length ? "；此前上行段 " + ups.map(function (v) { return v + " 年"; }).join("、") : ""))
      : "";
    return '<div class="cyc-grp cyc-grp-full cyc-secular">' +
      '<div class="cyc-lbl">' + L("Secular frame", "长周期框架") + ' <span class="cyc-tier tier-frame">' + L("FRAME", "框架") + '</span></div>' +
      '<div class="cyc-secular-strip"></div>' +
      '<p class="cyc-secular-txt">' + esc(txt) + '</p>' +
      '</div>';
  }

  function opinionBlock(card, op, mb) {
    var tolLine = "";
    if (mb && mb.tolerance) {
      var t = mb.tolerance;
      tolLine = '<div class="cyc-tol-line' + (t.loud ? ' loud' : '') + '">' +
        L("Engine reads position " + t.engine_pos + "; the dated opinion said " + t.hand_pos + " (Δ" + (t.delta > 0 ? "+" : "") + t.delta + "). The engine number is what's plotted.",
          "引擎读数为 " + t.engine_pos + "；该期观点为 " + t.hand_pos + "（Δ" + (t.delta > 0 ? "+" : "") + t.delta + "）。图中绘制的是引擎数值。") +
        '</div>';
    }
    var drivers = zcArr(card.id, "drivers", op.drivers || []);
    return '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-read"><div class="cyc-lbl">' + L("Analyst note", "分析师注记") +
          ' <span class="cyc-opinion-badge" title="Dated analyst opinion — not an engine output">' + L("OPINION", "观点") + '</span>' +
          '<span class="cyc-asof-mini"> · ' + L("as of ", "截至 ") + esc(op.as_of || AS_OF) + '</span></div>' +
          '<p>' + zc(card.id, "read", op.read || "") + '</p>' + tolLine + '</div>' +
        '<div class="cyc-fals"><div class="cyc-lbl">' + L("Falsifier", "证伪条件") +
          ' <span class="cyc-opinion-badge">' + L("OPINION", "观点") + '</span></div>' +
          '<p>' + zc(card.id, "falsifier", op.falsifier || "") + '</p></div>' +
      '</div>' +
      (drivers.length || op.regimeNote ?
        '<div class="cyc-grp cyc-grp-3">' +
          (drivers.length ? '<div class="cyc-drivers"><div class="cyc-lbl">' + L("Swing factors", "关键变量") + '</div><ul>' +
            drivers.map(function (d) { return "<li>" + esc(d) + "</li>"; }).join("") + '</ul></div>' : '') +
          (op.regimeNote ? '<div class="cyc-regnote">' + zc(card.id, "regimeNote", op.regimeNote) + '</div>' : '') +
        '</div>' : '');
  }

  /* ---- default panel content (regime + cross-cycle map) ------------------ */
  function buildDefaultPanel() {
    var def = document.getElementById("cyc-panel-default");
    if (!def) return;
    var R = REGIME || {};
    var zst = (window.CYCLE_ZH && window.CYCLE_ZH.regime && window.CYCLE_ZH.regime.stats) || [];
    var zh = curLang() === "zh";
    var stats = (R.stats || []).map(function (s, i) {
      var k = zh && zst[i] ? zst[i].k : s.k, note = zh && zst[i] ? zst[i].note : s.note;
      return '<div class="rg-stat"><div class="rg-k">' + esc(k) + '</div><div class="rg-v">' + esc(s.v) + '</div><div class="rg-n">' + esc(note) + '</div></div>';
    }).join("");

    var buckets = { Peak: [], Expansion: [], Downturn: [], Recovery: [], Trough: [], Frame: [] };
    ORDER.forEach(function (id) { var card = CY[id]; (buckets[cardPhase(card)] || (buckets[cardPhase(card)] = [])).push(card); });
    function row(title, list, note) {
      if (!list.length) return "";
      var chips = list.map(function (c) {
        return '<button class="mini-chip" data-id="' + c.id + '" style="--c:' + c.accent + '"><span class="dot"></span>' + zc(c.id, "short", c.short) + '</button>';
      }).join("");
      return '<div class="xc-row"><div class="xc-rh">' + title + '<span>' + note + '</span></div><div class="xc-chips">' + chips + '</div></div>';
    }

    def.innerHTML = '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<div class="cyc-lbl">' + L("Macro regime · ", "宏观环境 · ") + esc(AS_OF) + '</div>' +
        '<div class="rg-head"><div class="rg-label">' + zr("label", R.label || "") + '</div><div class="rg-sub">' + zr("sub", R.sub || "") + '</div></div>' +
        '<p class="rg-headline">' + zr("headline", R.headline || "") + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Conditions", "环境指标") + '</div>' +
        '<div class="rg-stats">' + stats + '</div>' +
        '<p class="rg-tilt">' + zr("tilt", R.tilt || "") + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Where the cycles stand", "各周期所处位置") + '</div>' +
        '<div class="xc-map">' +
          row(L("Topping · late", "见顶 · 晚期"), buckets.Peak, L("thin cushion", "缓冲薄弱")) +
          row(L("Expanding", "扩张中"), buckets.Expansion, L("trending up", "上行趋势")) +
          row(L("Rolling over", "回落中"), buckets.Downturn, L("declining", "下行中")) +
          row(L("Recovering", "复苏中"), buckets.Recovery, L("early up-leg", "上行初段")) +
          row(L("Bottoming", "筑底中"), buckets.Trough, L("washed-out · cheap", "超卖 · 便宜")) +
          row(L("Frames · structural", "框架 · 结构性"), buckets.Frame, L("curated, ungraded", "人工整理 · 不评分")) +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("How to read", "如何解读") + '</div>' +
        '<ul class="cyc-how">' +
          '<li>' + L("<b>MEASURED</b> cards plot the engine's own oscillator, turns and projection — computed live from the backing tape, not typed by hand.", "<b>已测量</b>卡片绘制引擎自身的振荡指标、拐点与投影 — 由底层数据实时计算，而非人工录入。") + '</li>' +
          '<li>' + L("<b>FRAME</b> cards show only the curated turning-point timeline and how long prior legs ran — no position, no forecast. They are structural clocks, not graded cycles.", "<b>框架</b>卡片仅展示人工整理的拐点时间线以及此前周期段的时长 — 无位置、无预测。它们是结构性时钟，而非评分周期。") + '</li>' +
          '<li>' + L("The dated <b>OPINION</b> note is analyst prose, clearly separated from the engine numbers; where they disagree, the card shows the delta.", "带日期的<b>观点</b>注记是分析师文字，与引擎数值明确分离；两者不一致时，卡片会标示差值。") + '</li>' +
        '</ul>' +
      '</div>';

    def.querySelectorAll(".mini-chip").forEach(function (b) {
      b.addEventListener("click", function () { setFocus(b.getAttribute("data-id")); });
    });
    def.classList.add("show");
  }

  /* ---- secular strip chart mount (DUAL focus panels) --------------------- */
  function mountSecularStrips() {
    document.querySelectorAll(".cyc-secular-strip").forEach(function (node) {
      var foc = node.closest(".cyc-panel");
      var id = state.focus;
      if (!id || !CY[id]) return;
      var fb = frameBand(CY[id]);
      if (fb) mountTimeline(node, CY[id], fb);
    });
  }

  /* ---- mobile bottom sheet ----------------------------------------------- */
  function expandSheet(on) { var s = document.getElementById("cyc-detail"); if (s) s.classList.toggle("expanded", on !== false); }
  function initSheet() {
    var sheet = document.getElementById("cyc-detail"), handle = document.getElementById("cyc-handle");
    if (!sheet || !handle) return;
    handle.addEventListener("click", function () { sheet.classList.toggle("expanded"); });
    var startY = 0, dragging = false;
    handle.addEventListener("touchstart", function (e) { startY = e.touches[0].clientY; dragging = true; }, { passive: true });
    handle.addEventListener("touchmove", function (e) {
      if (!dragging) return;
      var dy = e.touches[0].clientY - startY;
      if (dy < -30) sheet.classList.add("expanded"); else if (dy > 40) sheet.classList.remove("expanded");
    }, { passive: true });
    handle.addEventListener("touchend", function () { dragging = false; });
  }

  /* ---- staleness banner (W0.1) ------------------------------------------- */
  function renderStalenessBanner() {
    var host = document.getElementById("cyc-stale-banner");
    if (!host) return;
    var asOfYear = AS_OF ? yf(AS_OF) : TODAY;
    var days = Math.round((TODAY - asOfYear) * 365.25);
    if (days < 14) { host.innerHTML = ""; return; }
    var cls = days >= 60 ? "stale-red" : "stale-amber";
    host.innerHTML = '<div class="stale-banner ' + cls + '">' +
      L("Analyst notes as of " + AS_OF + " — " + days + " days old (engine reads are live)",
        "分析师注记截至 " + AS_OF + " — 已 " + days + " 天（引擎读数为实时）") + '</div>';
  }

  /* ---- language switch --------------------------------------------------- */
  function rerender() {
    var savedFocus = state.focus, savedPhase = {};
    PHASE_FILTER.forEach(function (p) { savedPhase[p.key] = phaseState[p.key]; });
    mountChips();
    mountCards();
    buildDefaultPanel();
    buildZoom();
    buildGroups();
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = savedPhase[p.key]; });
    syncGroups();
    renderStalenessBanner();
    if (heroChart) {
      heroChart.spec = heroSpec();
      heroChart.resize();
      var v = heroChart.getView(), z = document.getElementById("cyc-zoom");
      if (z) z.classList.toggle("zoomed", v[0] > XDOM[0] + 1e-3 || v[1] < XDOM[1] - 1e-3);
    }
    if (savedFocus) setFocus(savedFocus); else renderPanel(null);
    mountSecularStrips();
  }

  // re-mount the secular strip AFTER a focus render (the panel HTML is rebuilt each time)
  var _origRenderPanel = renderPanel;
  renderPanel = function (id) { _origRenderPanel(id); setTimeout(mountSecularStrips, 0); };

  /* ---- boot -------------------------------------------------------------- */
  function boot() {
    mountChips();
    mountHero();
    buildDefaultPanel();
    mountCards();
    renderStalenessBanner();
    initSheet();
    document.addEventListener("langchange", rerender);
    var h = (location.hash || "").replace("#", "");
    if (h && CY[h]) setTimeout(function () { setFocus(h); }, 350);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

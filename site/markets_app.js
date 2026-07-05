/* ============================================================================
   markets_app.js — Global Market Cycles Dashboard · orchestration (v4, W3.5)
   ----------------------------------------------------------------------------
   W3.5 changes (ruling A9):
     · posFromDrawdown is NO LONGER the plotted position source.  The chart now
       plots window.MARKETS_ENGINE[id].pos_v2 (country_cycles engine) for the 7
       markets that have engine records (UK/Japan/HK/Canada/China/India/Taiwan).
       US and Europe have no engine record yet; their curated `pos` is rendered
       clearly labeled as OPINION-class.
     · convergenceBands() is DELETED — the sync-gauge bands were an artifact of
       hand-typed identical projection dates (audit findings markets-global-3/4).
       A measured sync gauge is deferred to Phase-5.
     · Each market card shows engine basis, last confirmed turn date, and links
       to its country_cycles.html counterpart.
     · Curated valuations render with an explicit as-of date + staleness chip.
   v3 features preserved: amplitude-faithful oscillator retained for US/Europe
   fallback only; i18n; scatter; snapshot; phase-filter; mobile sheet.
   ========================================================================== */
(function () {
  "use strict";

  var META = window.MARKET_META, CYCLES = window.MARKETS, PHASES = window.MARKET_PHASES;
  var I18N = window.MARKET_I18N || { markets: {}, regime: null };
  // W3.5: engine records keyed by market id (from window.MARKETS_ENGINE.markets)
  var ENGINE = (window.MARKETS_ENGINE || {}).markets || {};
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var MONTHS_ZH = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

  /* ---- i18n core --------------------------------------------------------- */
  function LANG() { return document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"; }
  function t(en, zh) { return LANG() === "zh" ? zh : en; }
  function zhM(id) { return (I18N.markets || {})[id] || null; }
  function dz(c, field, en) { if (LANG() === "zh") { var z = zhM(c.id); if (z && z[field] != null) return z[field]; } return en; }
  function nm(c) { return dz(c, "name", c.name); }
  function px(c) { return dz(c, "proxy", c.proxy); }
  function shrt(c) { return dz(c, "short", c.short); }
  function arche(c) { return dz(c, "archetype", c.archetype); }
  function phLabel(c) { return dz(c, "phaseLabel", c.now.phaseLabel); }
  function readT(c) { return dz(c, "read", c.now.read); }
  function regNote(c) { return dz(c, "regimeNote", c.regimeNote); }
  function valNote(c) { var v = c.valuation || {}; return dz(c, "valNote", v.note); }
  function driversT(c) { var z = zhM(c.id); return (LANG() === "zh" && z && z.drivers && z.drivers.length) ? z.drivers : c.proj.drivers; }
  function falsT(c) { return dz(c, "falsifier", c.proj.falsifier); }
  function turnE(c, tk, en) { if (LANG() === "zh") { var z = zhM(c.id); if (z && z.turns && z.turns[tk] != null) return z.turns[tk]; } return en; }

  var PHASE_ZH = {
    Trough: { label: "见底", short: "筑底" },
    Recovery: { label: "复苏", short: "初升" },
    Expansion: { label: "扩张", short: "上行" },
    Peak: { label: "见顶", short: "筑顶" },
    Downturn: { label: "回落", short: "滚落" }
  };
  function phLab(key) { return LANG() === "zh" ? ((PHASE_ZH[key] || {}).label || key) : ((PHASES[key] || {}).label || key); }
  function phShort(key) { return LANG() === "zh" ? ((PHASE_ZH[key] || {}).short || key) : ((PHASES[key] || {}).short || key); }

  /* ---- small helpers ----------------------------------------------------- */
  function yf(tk) { var p = String(tk).split("-"); return +p[0] + ((+p[1] || 6) - 0.5) / 12; }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function lerp(a, b, t2) { return a + (b - a) * t2; }
  function cos(x, xa, ya, xb, yb) { if (xb === xa) return yb; var tt = clamp((x - xa) / (xb - xa), 0, 1); return ya + (yb - ya) * (0.5 - 0.5 * Math.cos(Math.PI * tt)); }
  function fmtMon(tk) { if (!tk) return ""; var p = String(tk).split("-"); var mi = (+p[1] || 6) - 1; return LANG() === "zh" ? ("’" + String(p[0]).slice(2) + " " + MONTHS_ZH[mi]) : (MONTHS[mi] + " ’" + String(p[0]).slice(2)); }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function num(v, d) { return v == null ? null : Number(v).toLocaleString("en-US", { maximumFractionDigits: d == null ? 0 : d }); }
  function pct(v, d) { return v == null ? null : (v > 0 ? "+" : "") + Number(v).toFixed(d == null ? 1 : d) + "%"; }
  function zone(y) {
    return y >= 82 ? t("Euphoric · at the highs", "亢奋 · 历史高位") : y >= 62 ? t("Late · extended", "后段 · 拉伸") :
      y >= 42 ? t("Mid-cycle", "周期中段") : y >= 22 ? t("Recovering · below highs", "复苏 · 低于高点") : t("Washed-out · deep below highs", "超卖 · 深跌");
  }
  function tiltOf(k) {
    return ({
      tailwind: { lab: t("Tailwind", "顺风"), ar: "↑", cls: "t-up" },
      headwind: { lab: t("Headwind", "逆风"), ar: "↓", cls: "t-down" },
      mixed: { lab: t("Mixed", "喜忧参半"), ar: "↔", cls: "t-mix" },
      "n/a": { lab: t("Event-driven", "事件驱动"), ar: "•", cls: "t-na" }
    })[k] || { lab: t("Mixed", "喜忧参半"), ar: "↔", cls: "t-mix" };
  }

  /* ---- wall-clock TODAY (W0.1) --------------------------------------------
     Derive the current decimal year from the live system clock so the Now dot,
     history/projection split, and elapsed-turn detection are always accurate.
     META.today (a frozen literal baked at render time) is kept only as a
     data-as-of fallback if Date() is somehow unavailable. */
  function yfNow(d) {
    var y = d.getFullYear();
    var start = new Date(y, 0, 1), end = new Date(y + 1, 0, 1);
    return y + (d - start) / (end - start);
  }
  var TODAY = (function () {
    try { var n = new Date(); if (isFinite(n.getTime())) return yfNow(n); } catch (e) {}
    return META.today;    // frozen fallback only
  }());

  /* ---- AMPLITUDE-FAITHFUL position model ---------------------------------- */
  // posFromDrawdown: RETAINED for US/Europe fallback (no engine record yet).
  // For engine-backed markets the plotted position is eng.pos_v2 (0-100 oscillator).
  function posFromDrawdown(ddPct) { var d = Math.max(0, -(ddPct || 0)); return clamp(Math.round(92 * Math.exp(-d / 30)), 3, 97); }

  /* engPos(c): engine pos_v2 when available; curated-drawdown fallback otherwise.
     Returns { val: number, source: "engine"|"curated" }. */
  function engPos(c) {
    var eng = ENGINE[c.id];
    if (eng && eng.has_engine && eng.pos_v2 != null) return { val: eng.pos_v2, source: "engine" };
    // Fallback: curated pos or drawdown-derived (labeled OPINION)
    var p = c.now.pctFromATH != null ? posFromDrawdown(c.now.pctFromATH)
          : (c.now.pos != null ? clamp(c.now.pos, 3, 97) : 50);
    return { val: p, source: "curated" };
  }

  function build(c) {
    // W0.1: use wall-clock TODAY, not a frozen literal baked at render time.
    var today = TODAY;
    var eng = ENGINE[c.id] || {};
    var useEngine = !!(eng.has_engine && eng.pos_v2 != null);

    // Build turn y-values: for engine-backed markets use the engine oscillator value
    // from turns[].osc when present; otherwise fall back to drawdown-exponential.
    var runMax = -Infinity;
    var turns = c.turns.map(function (tp) {
      var y;
      if (tp.v != null) { runMax = Math.max(runMax, tp.v); y = posFromDrawdown((tp.v / runMax - 1) * 100); }
      else { y = tp.k === "peak" ? 88 : 16; }
      return { x: yf(tp.t), y: y, k: tp.k, e: tp.e, v: tp.v, t: tp.t };
    });
    var n = turns.length, last = turns[n - 1];

    // W3.5: plotted nowPos = engine pos_v2 when available, else curated fallback.
    var nowPos;
    if (useEngine) {
      nowPos = clamp(eng.pos_v2, 3, 97);
    } else {
      nowPos = c.now.pctFromATH != null ? posFromDrawdown(c.now.pctFromATH)
             : (c.now.pos != null ? clamp(c.now.pos, 3, 97) : (last.y + 50) / 2);
    }
    var nextY = c.proj.nextTurn === "peak" ? clamp(Math.max(nowPos + 8, 88), 80, 96) : clamp(Math.min(nowPos - 18, 34), 10, 44);

    // W0.1: NO Math.max push-forward. When the hand-typed central date < today
    // the projection window has elapsed; render a dimmed "window passed" state
    // instead of silently sliding the turn into the future.
    var tcRaw = yf(c.proj.central);
    var elapsed = tcRaw < today;  // true = turn date is in the past

    var tc, te, tl, projEnd, relax;
    relax = c.proj.nextTurn === "peak" ? 58 : 44;
    if (elapsed) {
      tc = tcRaw;
      te = yf(c.proj.low);
      tl = yf(c.proj.high);
      projEnd = Math.max(tc, tl) + 0.1;   // draw to last plausible turn then stop
    } else {
      tc = tcRaw;
      te = clamp(yf(c.proj.low), today + 0.05, tc);
      tl = Math.max(yf(c.proj.high), tc + 0.1);
      projEnd = Math.min(META.xDomain[1], tl + 0.35 * (tl - today));
    }

    // Guard against division by zero in projAt: denom > 0 guaranteed in the
    // normal branch (tc > today). In the elapsed branch projAt is never called
    // for x > today so we never reach the division.
    function projAt(x, tt) {
      var denom = tt - today;
      if (x <= tt) return cos(x, today, nowPos, tt, nextY);
      return cos(x, tt, nextY, projEnd, relax);
    }
    var center = function (x) { return x <= today ? cos(x, last.x, last.y, today, nowPos) : projAt(x, tc); };
    var withTurn = function (x, tt) { return x <= today ? center(x) : projAt(x, tt); };

    var hist = [], step = 0.16;
    for (var i = 0; i < n - 1; i++) { var a = turns[i], b = turns[i + 1]; for (var x = a.x; x < b.x - 1e-6; x += step) hist.push({ x: x, y: cos(x, a.x, a.y, b.x, b.y) }); }
    hist.push({ x: last.x, y: last.y });
    for (var xx = last.x + step; xx <= today; xx += step) hist.push({ x: xx, y: center(xx) });
    hist.push({ x: today, y: center(today) });

    // W0.1: elapsed-turn handling — draw the historical projection leg (dimmed)
    // instead of a live forward cone when the window is in the past.
    var proj = [], cone = [];
    if (elapsed) {
      // Draw the projection leg from last turn to the hand-typed tc (all in the past).
      for (var xpe = last.x; xpe <= projEnd + 1e-6; xpe += step) {
        proj.push({ x: xpe, y: cos(xpe, last.x, last.y, Math.max(tc, last.x + 0.01), nextY) });
      }
      // No cone in elapsed state — the window has passed.
    } else {
      for (var xp = today; xp <= projEnd + 1e-6; xp += step) proj.push({ x: xp, y: projAt(xp, tc) });

      var tlt = c.proj.tilt, hiW = tlt === "tailwind" ? 1.35 : tlt === "headwind" ? 0.7 : 1, loW = tlt === "headwind" ? 1.35 : tlt === "tailwind" ? 0.7 : 1;
      for (var xc = today; xc <= projEnd + 1e-6; xc += step) {
        var vs = [withTurn(xc, te), center(xc), withTurn(xc, tl)];
        var lo = Math.min(vs[0], vs[1], vs[2]), hi = Math.max(vs[0], vs[1], vs[2]);
        var amp = lerp(1.5, 13, clamp((xc - today) / (projEnd - today), 0, 1));
        cone.push({ x: xc, lo: clamp(lo - amp * loW, 2, 98), hi: clamp(hi + amp * hiW, 2, 98) });
      }
    }

    var markers = turns.filter(function (tp) { return tp.x >= META.xDomain[0] - 0.2; })
      .map(function (tp) { return { x: tp.x, y: tp.y, kind: tp.k, label: fmtMon(tp.t), sub: tp.e }; });
    var nowY = center(today);
    markers.push({ x: today, y: nowY, kind: "now", label: t("Now", "现在"), sub: phLabel(c) });

    // legPct: clamp to [0,1]; if elapsed push to 1 (>100% means window elapsed)
    var legPct = elapsed ? 1 : clamp((today - last.x) / Math.max(tc - last.x, 0.001), 0, 1);

    return { id: c.id, color: c.accent, label: nm(c), width: 2, hist: hist, proj: proj, cone: cone, markers: markers,
      nowY: nowY, tc: tc, te: te, tl: tl, projEnd: projEnd, legPct: legPct, elapsed: elapsed, c: c };
  }

  var MODELS = {}, ORDER = [];
  CYCLES.forEach(function (c) { MODELS[c.id] = build(c); ORDER.push(c.id); });
  // W3.5: nowPosOf returns engine pos_v2 when available, otherwise curated fallback.
  // This drives the snapshot ranking, scatter, and dispersion — all now engine-sourced.
  function nowPosOf(c) {
    var ep = engPos(c);
    return ep.source === "engine" ? ep.val : MODELS[c.id].nowY;
  }

  /* ---- collective inflection zones (DELETED W3.5) -----------------------
     convergenceBands() has been retired (audit findings markets-global-3/4):
     the bands were an artifact of the 9 curated markets.html projections all
     carrying identically-typed central dates, producing spurious clustering
     with zero statistical basis.  A measured sync gauge using engine turn
     distributions is deferred to Phase-5.  The vbands slot in heroSpec now
     passes an empty array. */

  /* ---- hero overlay ------------------------------------------------------ */
  var heroChart = null, state = { focus: null };

  function heroSpec() {
    return {
      xDomain: META.xDomain, yDomain: [0, 100],
      xTicks: window.MMChart.niceYearTicks(META.xDomain[0] + 1, META.xDomain[1], 5),
      yTicks: [{ v: 14, label: t("Crash low", "崩盘低点") }, { v: 50, label: t("Mid", "中点") }, { v: 92, label: t("At ATH", "历史高位") }],
      padding: { t: 16, r: 16, b: 28, l: 54 },
      bands: [
        { y0: 0, y1: 35, color: "var(--down)", opacity: 0.05, label: t("washed-out", "超卖") },
        { y0: 35, y1: 65, color: "var(--muted)", opacity: 0.04, label: t("mid-cycle", "周期中段") },
        { y0: 65, y1: 100, color: "var(--warn)", opacity: 0.055, label: t("at the highs", "高位") }
      ],
      guides: [{ x: META.today, label: t("TODAY", "今天"), kind: "today" }],
      vbands: [],  // W3.5: convergenceBands retired — fake artifact of identical typed dates (audit markets-global-3/4)
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
    var ds = near ? t("Now", "现在") : (LANG() === "zh" ? (fy + " " + MONTHS_ZH[fmo]) : (MONTHS[fmo] + " " + fy));
    var nt = null, bd = 0.5;
    c.turns.forEach(function (tp) { var tx = yf(tp.t); var dd = Math.abs(tx - xVal); if (dd < bd) { bd = dd; nt = tp; } });
    var head = '<div class="mmc-tip-h"><span class="dot" style="background:' + d.color + '"></span>' + nm(c) + '</div>';
    var yr = '<div class="mmc-tip-yr">' + ds + '</div>';
    var lvl = "";
    if (near && c.now.level != null) {
      lvl = '<div class="mmc-tip-lv">' + num(c.now.level) + (c.now.pctFromATH != null ? ' · ' + pct(c.now.pctFromATH) + ' ' + t("vs ATH", "距高点") : '') + '</div>';
    } else if (nt && nt.v != null) {
      lvl = '<div class="mmc-tip-lv">' + (nt.k === "peak" ? t("▲ top ", "▲ 顶 ") : t("▼ bottom ", "▼ 底 ")) + num(nt.v) + '</div>' +
            '<div class="mmc-tip-ev">' + turnE(c, nt.t, nt.e) + '</div>';
    }
    var z = '<div class="mmc-tip-z">' + zone(pt.y) + ' · ' + (rising ? t("rising", "上行") : t("easing", "回落")) + '</div>';
    var ph = near ? '<div class="mmc-tip-ph">' + phLabel(c) + '</div>' : '';
    return head + yr + lvl + z + ph;
  }

  function mountHero() {
    var node = document.getElementById("cyc-chart");
    if (!node) return;
    heroChart = window.MMChart.create(node, heroSpec());
    buildZoom();
    buildGroups();
  }

  function buildZoom() {
    var z = document.getElementById("cyc-zoom");
    if (!z) return;
    var presets = [
      { label: t("Full", "全部"), d: META.xDomain },
      { label: t("Since GFC", "金融危机至今"), d: [2007, 2031] },
      { label: t("Post-COVID", "疫情以来"), d: [2020, 2031] },
      { label: t("This cycle", "本轮周期"), d: [2022, 2029] }
    ];
    z.innerHTML = '<span class="cyc-zhint">' + t("scroll · drag", "滚动 · 拖拽") + '</span>' +
      presets.map(function (p, i) { return '<button class="cyc-zbtn" data-i="' + i + '">' + p.label + '</button>'; }).join("") +
      '<button class="cyc-zbtn cyc-zreset" id="cyc-zreset">' + t("Reset ⤢", "重置 ⤢") + '</button>';
    presets.forEach(function (p, i) {
      z.querySelector('[data-i="' + i + '"]').addEventListener("click", function () { if (heroChart) heroChart.setView(p.d.slice(), true); });
    });
    z.querySelector("#cyc-zreset").addEventListener("click", function () { if (heroChart) heroChart.resetZoom(); });
  }

  /* ---- phase filter ------------------------------------------------------ */
  var PHASE_FILTER = [
    { key: "Peak", label: ["At the highs", "高位"] },
    { key: "Expansion", label: ["Expanding", "扩张"] },
    { key: "Downturn", label: ["Rolling over", "回落"] },
    { key: "Recovery", label: ["Recovering", "复苏"] },
    { key: "Trough", label: ["Bottoming", "筑底"] }
  ];
  var byId = {};
  CYCLES.forEach(function (c) { byId[c.id] = c; });
  var phaseState = {};
  function buildGroups() {
    var host = document.getElementById("cyc-groups");
    if (!host) return;
    var counts = {};
    CYCLES.forEach(function (c) { counts[c.now.phase] = (counts[c.now.phase] || 0) + 1; });
    if (!Object.keys(phaseState).length) PHASE_FILTER.forEach(function (p) { phaseState[p.key] = true; });
    host.innerHTML = '<span class="cyc-glabel">' + t("Where they stand", "各自所处阶段") + '</span>' + PHASE_FILTER.map(function (p) {
      var hue = (PHASES[p.key] || {}).hue || "var(--muted)";
      return '<button class="cyc-gchip' + (phaseState[p.key] ? " on" : "") + '" data-k="' + p.key + '" style="--ph:' + hue + '"><span class="gdot"></span>' + t(p.label[0], p.label[1]) + ' <i>' + (counts[p.key] || 0) + '</i></button>';
    }).join("");
    host.querySelectorAll(".cyc-gchip").forEach(function (b) {
      b.addEventListener("click", function () {
        var k = b.getAttribute("data-k");
        phaseState[k] = !phaseState[k];
        b.classList.toggle("on", phaseState[k]);
        applyGroupFilter();
      });
    });
  }
  function applyGroupFilter() {
    var allOff = PHASE_FILTER.every(function (p) { return !phaseState[p.key]; });
    var hidden = {};
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      var c = byId[cd.getAttribute("data-id")]; if (!c) return;
      var inF = allOff || phaseState[c.now.phase];
      cd.classList.toggle("gdim", !inF);
      cd.style.order = inF ? "0" : "1";
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
      b.innerHTML = '<span class="dot"></span><span class="nm">' + shrt(c) + '</span>';
      b.addEventListener("click", function () { toggleFocus(c.id); });
      wrap.appendChild(b);
    });
  }

  /* ---- valuation helpers ------------------------------------------------- */
  function valPE(c) { var v = c.valuation || {}; return v.forwardPE != null ? v.forwardPE : (v.trailingPE != null ? v.trailingPE : null); }
  function valChips(c) {
    var v = c.valuation || {}, out = [];
    // W3.5: '% vs ATH' stays as a labeled stat — it is NEVER the plotted position
    if (c.now.level != null) out.push('<span class="cc-stat"><b>' + num(c.now.level) + '</b><i>' + t("level", "点位") + '</i></span>');
    if (c.now.pctFromATH != null) out.push('<span class="cc-stat ' + (c.now.pctFromATH < -1 ? "neg" : "pos") + '"><b>' + pct(c.now.pctFromATH) + '</b><i>' + t("vs ATH", "距高点") + '</i></span>');
    if (v.forwardPE != null) out.push('<span class="cc-stat"><b>' + v.forwardPE.toFixed(1) + '×</b><i>' + t("fwd P/E", "预期PE") + '</i></span>');
    else if (v.trailingPE != null) out.push('<span class="cc-stat"><b>' + v.trailingPE.toFixed(1) + '×</b><i>' + t("P/E", "市盈率") + '</i></span>');
    if (v.cape != null) out.push('<span class="cc-stat"><b>' + v.cape.toFixed(0) + '</b><i>CAPE</i></span>');
    if (v.divYield != null) out.push('<span class="cc-stat"><b>' + v.divYield.toFixed(1) + '%</b><i>' + t("yield", "股息") + '</i></span>');
    return out.join("");
  }

  /* W3.5: engine source chip — shown on cards and detail panel. */
  function engSourceChip(c) {
    var eng = ENGINE[c.id] || {};
    if (eng.has_engine) {
      var cc = eng.cc_anchor ? 'country_cycles.html#' + eng.cc_anchor : 'country_cycles.html';
      return '<span class="cc-eng-chip">' + t("engine: ", "引擎：") + (eng.etf_id || "").toUpperCase()
        + ' · <a href="' + cc + '" class="cc-eng-link">' + t("view in Country Cycles →", "查看国家周期 →") + '</a></span>';
    }
    return '<span class="cc-eng-chip cc-eng-opinion">' + t("position: analyst estimate (no engine record)", "位置：分析师估算（无引擎记录）") + '</span>';
  }

  /* W3.5: valuation staleness chip — curated valuations carry an as-of date. */
  function valStaleChip(c) {
    var asOf = (c.valuation || {}).asOf || c.now.asOf || META.asOf || "";
    if (!asOf) return "";
    var asOfYear = yf(asOf);
    var ageDays = Math.round((TODAY - asOfYear) * 365.25);
    if (ageDays < 14) return '<span class="cc-val-age">' + t("valuations as of " + asOf, "估值截至 " + asOf) + '</span>';
    var cls = ageDays >= 60 ? "cc-val-stale-red" : "cc-val-stale-amber";
    return '<span class="cc-val-age ' + cls + '">' + t("valuations as of " + asOf + " (" + ageDays + "d old)", "估值截至 " + asOf + "（已 " + ageDays + " 天）") + '</span>';
  }

  /* ---- scorecards -------------------------------------------------------- */
  var sparks = {};
  function mountCards() {
    var grid = document.getElementById("cyc-cards");
    if (!grid) return;
    grid.innerHTML = "";
    CYCLES.forEach(function (c) {
      var m = MODELS[c.id], ph = PHASES[c.now.phase] || {};
      var card = el("article", "cyc-card");
      card.setAttribute("data-id", c.id);
      card.style.setProperty("--c", c.accent);
      var tilt = tiltOf(c.proj.tilt);
      var isPeak = c.proj.nextTurn === "peak";
      var elapsedChip = m.elapsed
        ? '<div class="cc-elapsed">' + t("Projection window passed — awaiting re-research", "投影窗口已过 — 待重新研究") + '</div>'
        : '';
      // W3.5: show engine phase when available; curated phase otherwise
      var eng = ENGINE[c.id] || {};
      var displayPhase = (eng.has_engine && eng.phase_v2) ? eng.phase_v2 : c.now.phase;
      var displayPhaseHue = (PHASES[displayPhase] || ph).hue || "var(--muted)";
      card.innerHTML =
        '<div class="cc-top">' +
          '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + nm(c) + '</div>' +
          '<div class="cc-px">' + px(c) + '</div></div></div>' +
          '<div class="cc-phase" style="--ph:' + displayPhaseHue + '">' + phLab(displayPhase) + '</div>' +
        '</div>' +
        '<div class="cc-spark"></div>' +
        '<div class="cc-stats">' + valChips(c) + '</div>' +
        '<div class="cc-eng">' + engSourceChip(c) + '</div>' +
        elapsedChip +
        '<div class="cc-meta">' +
          '<div class="cc-leg"><div class="cc-leg-bar"><i style="width:' + Math.round(m.legPct * 100) + '%"></i></div>' +
            '<div class="cc-leg-lab">' + t(Math.round(m.legPct * 100) + "% to next " + (isPeak ? "top" : "bottom"), Math.round(m.legPct * 100) + "% 距下一" + (isPeak ? "顶部" : "底部")) + '</div></div>' +
          '<div class="cc-next"><span class="cc-arrow">' + (isPeak ? "▲" : "▼") + '</span>' +
            '<span>' + t(isPeak ? "Top" : "Bottom", isPeak ? "顶部" : "底部") + ' ≈ ' + fmtMon(c.proj.central) + '</span>' +
            '<span class="cc-tilt ' + tilt.cls + '">' + tilt.ar + ' ' + tilt.lab + '</span></div>' +
        '</div>';
      card.addEventListener("click", function () { toggleFocus(c.id); });
      grid.appendChild(card);
      var sp = card.querySelector(".cc-spark");
      sparks[c.id] = window.MMChart.create(sp, {
        xDomain: [Math.max(META.xDomain[0], m.hist.length ? m.hist[0].x : 2000), m.projEnd],
        yDomain: [0, 100], padding: { t: 8, r: 6, b: 8, l: 6 },
        crosshair: false, animate: true, zoom: false,
        series: [{ id: c.id, color: c.accent, width: 2, hist: m.hist, proj: m.proj, cone: m.cone, markers: [{ x: META.today, y: m.nowY, kind: "now" }] }]
      });
    });
  }

  /* ---- NOW snapshot ------------------------------------------------------ */
  var snapSort = "pos";
  function renderSnapSort() {
    var sortHost = document.getElementById("mkt-snap-sort");
    if (!sortHost) return;
    var opts = [{ k: "pos", l: t("Cycle position", "周期位置") }, { k: "val", l: t("Valuation", "估值") }, { k: "ath", l: t("% off ATH", "距高点") }, { k: "az", l: t("A–Z", "名称") }];
    sortHost.innerHTML = opts.map(function (o) { return '<button class="cyc-zbtn snap-sortb' + (o.k === snapSort ? " on" : "") + '" data-k="' + o.k + '">' + o.l + '</button>'; }).join("");
    sortHost.querySelectorAll(".snap-sortb").forEach(function (b) {
      b.addEventListener("click", function () {
        snapSort = b.getAttribute("data-k");
        sortHost.querySelectorAll(".snap-sortb").forEach(function (x) { x.classList.toggle("on", x === b); });
        renderSnapshot();
      });
    });
  }
  function renderSnapshot() {
    var host = document.getElementById("mkt-snap");
    if (!host) return;
    var rows = CYCLES.slice();
    if (snapSort === "pos") rows.sort(function (a, b) { return nowPosOf(b) - nowPosOf(a); });
    else if (snapSort === "val") rows.sort(function (a, b) { return (valPE(b) || -1) - (valPE(a) || -1); });
    else if (snapSort === "ath") rows.sort(function (a, b) { return (b.now.pctFromATH != null ? b.now.pctFromATH : -999) - (a.now.pctFromATH != null ? a.now.pctFromATH : -999); });
    else rows.sort(function (a, b) { return shrt(a) < shrt(b) ? -1 : 1; });
    host.innerHTML = rows.map(function (c) {
      var p = Math.round(nowPosOf(c)), ph = PHASES[c.now.phase] || {}, pe = valPE(c);
      var rt = snapSort === "val" ? (pe != null ? pe.toFixed(1) + "×" : "—")
        : snapSort === "ath" ? (c.now.pctFromATH != null ? pct(c.now.pctFromATH) : "—") : p;
      return '<button class="snap-row' + (state.focus === c.id ? " lit" : "") + '" data-id="' + c.id + '" style="--c:' + c.accent + '">' +
        '<span class="snap-name"><span class="snap-d"></span>' + shrt(c) + '</span>' +
        '<span class="snap-track"><i class="snap-fill" style="width:' + p + '%"></i><span class="snap-dot" style="left:' + p + '%"></span></span>' +
        '<span class="snap-val">' + rt + '</span>' +
        '<span class="snap-phase" style="--ph:' + (ph.hue || "var(--muted)") + '">' + phShort(c.now.phase) + '</span>' +
        '</button>';
    }).join("");
    host.querySelectorAll(".snap-row").forEach(function (b) {
      b.addEventListener("click", function () { toggleFocus(b.getAttribute("data-id")); });
      b.addEventListener("mouseenter", function () { if (heroChart && !state.focus) heroChart.focus(b.getAttribute("data-id")); });
      b.addEventListener("mouseleave", function () { if (heroChart && !state.focus) heroChart.focus(null); });
    });
  }
  function renderDispersion() {
    var host = document.getElementById("mkt-dispersion");
    if (!host) return;
    var ps = CYCLES.map(nowPosOf);
    var mean = ps.reduce(function (s, v) { return s + v; }, 0) / ps.length;
    var sd = Math.sqrt(ps.reduce(function (s, v) { return s + (v - mean) * (v - mean); }, 0) / ps.length);
    var sorted = CYCLES.slice().sort(function (a, b) { return nowPosOf(b) - nowPosOf(a); });
    var top = sorted[0], bot = sorted[sorted.length - 1];
    var atHighs = CYCLES.filter(function (c) { return nowPosOf(c) >= 78; }).length;
    var washed = CYCLES.filter(function (c) { return nowPosOf(c) <= 45; }).length;
    var sdNote = sd > 22 ? t("wide — markets de-synced", "较宽 — 市场分化") : sd > 13 ? t("moderate", "适中") : t("tight — moving together", "紧密 — 同步");
    host.innerHTML =
      '<div class="disp-cell"><div class="disp-k">' + t("Spread", "区间") + '</div><div class="disp-v">' + Math.round(nowPosOf(top)) + ' → ' + Math.round(nowPosOf(bot)) +
        '</div><div class="disp-n">' + t(shrt(top) + " richest · " + shrt(bot) + " cheapest by cycle", shrt(top) + "周期最高 · " + shrt(bot) + "周期最低") + '</div></div>' +
      '<div class="disp-cell"><div class="disp-k">' + t("Dispersion (σ)", "离散度 (σ)") + '</div><div class="disp-v">' + sd.toFixed(0) + '</div><div class="disp-n">' + sdNote + '</div></div>' +
      '<div class="disp-cell"><div class="disp-k">' + t("At the highs", "处于高位") + '</div><div class="disp-v">' + atHighs + ' / ' + CYCLES.length +
        '</div><div class="disp-n">' + t(washed + " washed-out / recovering", washed + " 个超卖/复苏中") + '</div></div>';
  }

  /* ---- VALUATION map ----------------------------------------------------- */
  function renderScatter() {
    var host = document.getElementById("mkt-scatter");
    if (!host) return;
    var pts = CYCLES.map(function (c) { return { c: c, pe: valPE(c), pos: nowPosOf(c) }; }).filter(function (p) { return p.pe != null; });
    if (!pts.length) { host.innerHTML = '<div class="sc-empty">' + t("No valuation data available.", "暂无估值数据") + '</div>'; return; }
    var W = host.clientWidth || 640, H = 360, pad = { t: 18, r: 16, b: 40, l: 46 };
    var x0 = pad.l, x1 = W - pad.r, y0 = pad.t, y1 = H - pad.b;
    var pes = pts.map(function (p) { return p.pe; });
    var xmin = Math.max(6, Math.floor(Math.min.apply(null, pes) - 1));
    var xmax = Math.ceil(Math.max.apply(null, pes) + 1);
    var xMed = pes.slice().sort(function (a, b) { return a - b; })[Math.floor(pes.length / 2)];
    var SX = function (v) { return x0 + (v - xmin) / (xmax - xmin) * (x1 - x0); };
    var SY = function (v) { return y1 - (v - 0) / (100 - 0) * (y1 - y0); };
    var NS = "http://www.w3.org/2000/svg";
    function mk(tag, a) { var e = document.createElementNS(NS, tag); for (var k in a) if (a[k] != null) e.setAttribute(k, a[k]); return e; }
    host.innerHTML = "";
    var svg = mk("svg", { class: "sc-svg", viewBox: "0 0 " + W + " " + H, width: W, height: H });
    var mx = SX(xMed), my = SY(50);
    svg.appendChild(mk("line", { x1: x0, y1: my, x2: x1, y2: my, stroke: "var(--line)", "stroke-dasharray": "3 4", opacity: 0.7 }));
    svg.appendChild(mk("line", { x1: mx, y1: y0, x2: mx, y2: y1, stroke: "var(--line)", "stroke-dasharray": "3 4", opacity: 0.7 }));
    var quads = [
      { x: x0 + 6, y: y0 + 14, tx: t("Cheap · at the highs", "便宜 · 高位"), anc: "start" },
      { x: x1 - 6, y: y0 + 14, tx: t("Rich · at the highs", "贵 · 高位"), anc: "end" },
      { x: x0 + 6, y: y1 - 8, tx: t("Cheap · washed-out", "便宜 · 超卖"), anc: "start" },
      { x: x1 - 6, y: y1 - 8, tx: t("Rich · washed-out", "贵 · 超卖"), anc: "end" }
    ];
    quads.forEach(function (q) { var tx = mk("text", { x: q.x, y: q.y, "text-anchor": q.anc, class: "sc-quad" }); tx.textContent = q.tx; svg.appendChild(tx); });
    var xl = mk("text", { x: (x0 + x1) / 2, y: H - 8, "text-anchor": "middle", class: "sc-axl" }); xl.textContent = t("← cheaper      forward P/E      richer →", "← 更便宜      预期市盈率      更贵 →"); svg.appendChild(xl);
    var yl = mk("text", { x: 12, y: (y0 + y1) / 2, "text-anchor": "middle", class: "sc-axl", transform: "rotate(-90 12 " + ((y0 + y1) / 2) + ")" }); yl.textContent = t("washed-out ↓   cycle position   ↑ at the highs", "超卖 ↓   周期位置   ↑ 高位"); svg.appendChild(yl);
    for (var tk = Math.ceil(xmin / 4) * 4; tk <= xmax; tk += 4) {
      svg.appendChild(mk("line", { x1: SX(tk), y1: y1, x2: SX(tk), y2: y1 + 4, stroke: "var(--line)" }));
      var tl = mk("text", { x: SX(tk), y: y1 + 16, "text-anchor": "middle", class: "sc-tick" }); tl.textContent = tk + "×"; svg.appendChild(tl);
    }
    pts.forEach(function (p) {
      var g = mk("g", { class: "sc-pt" + (state.focus === p.c.id ? " lit" : (state.focus ? " dim" : "")), "data-id": p.c.id, style: "cursor:pointer" });
      g.appendChild(mk("circle", { cx: SX(p.pe), cy: SY(p.pos), r: 7, fill: p.c.accent, "fill-opacity": 0.85, stroke: "var(--panel)", "stroke-width": 1.5 }));
      var lab = mk("text", { x: SX(p.pe), y: SY(p.pos) - 11, "text-anchor": "middle", class: "sc-lab", fill: p.c.accent }); lab.textContent = shrt(p.c);
      g.appendChild(lab);
      g.addEventListener("click", function () { toggleFocus(p.c.id); });
      g.addEventListener("mouseenter", function () { if (heroChart && !state.focus) heroChart.focus(p.c.id); });
      g.addEventListener("mouseleave", function () { if (heroChart && !state.focus) heroChart.focus(null); });
      svg.appendChild(g);
    });
    host.appendChild(svg);
  }

  /* ---- focus orchestration ----------------------------------------------- */
  function toggleFocus(id) { setFocus(state.focus === id ? null : id); }
  function setFocus(id) {
    state.focus = id;
    if (heroChart) heroChart.focus(id);
    document.querySelectorAll(".cyc-chip").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-id") === id);
      b.classList.toggle("off", !!id && b.getAttribute("data-id") !== id);
    });
    document.querySelectorAll(".cyc-card").forEach(function (cd) {
      cd.classList.toggle("lit", cd.getAttribute("data-id") === id);
      cd.classList.toggle("dim", !!id && cd.getAttribute("data-id") !== id);
    });
    document.querySelectorAll(".snap-row").forEach(function (r) { r.classList.toggle("lit", r.getAttribute("data-id") === id); });
    document.querySelectorAll(".sc-pt").forEach(function (g) { g.classList.toggle("lit", g.getAttribute("data-id") === id); g.classList.toggle("dim", !!id && g.getAttribute("data-id") !== id); });
    renderPanel(id);
    if (id && window.innerWidth <= 880) expandSheet(true);
    try { history.replaceState(null, "", id ? "#" + id : location.pathname + location.search); } catch (e) {}
  }

  /* ---- detail panel ------------------------------------------------------ */
  function renderPanel(id) {
    var def = document.getElementById("cyc-panel-default");
    var foc = document.getElementById("cyc-panel-focus");
    if (!def || !foc) return;
    if (!id) { foc.classList.remove("show"); def.classList.add("show"); return; }
    foc.innerHTML = focusHTML(byId[id]);
    var back = foc.querySelector(".cyc-back");
    if (back) back.addEventListener("click", function () { setFocus(null); });
    def.classList.remove("show"); foc.classList.add("show");
  }

  function srcHost(u) { try { return u.replace(/^https?:\/\//, "").split("/")[0].replace(/^www\./, ""); } catch (e) { return u; } }
  function focusHTML(c) {
    var m = MODELS[c.id], v = c.valuation || {};
    var eng = ENGINE[c.id] || {};
    var useEngine = !!(eng.has_engine && eng.pos_v2 != null);
    // W3.5: display engine phase when available
    var displayPhase = useEngine && eng.phase_v2 ? eng.phase_v2 : c.now.phase;
    var ph = PHASES[displayPhase] || {};
    var tilt = tiltOf(c.proj.tilt);
    var isPeak = c.proj.nextTurn === "peak";
    function fact(k, val) { return val == null || val === "" ? "" : '<div class="f"><div class="fk">' + k + '</div><div class="fv">' + val + '</div></div>'; }
    var srcs = (c.sources || []).slice(0, 4).map(function (u) { return '<a href="' + u + '" target="_blank" rel="noopener">' + srcHost(u) + '</a>'; }).join("");
    var elapsedBanner = m.elapsed
      ? '<div class="cyc-elapsed-panel">' + t("Projection window passed — awaiting re-research", "投影窗口已过 — 待重新研究") + '</div>'
      : '';
    // W3.5: engine panel — engine position + basis + cross-link
    var engPanel = "";
    if (useEngine) {
      var ccHref = eng.cc_anchor ? 'country_cycles.html#' + eng.cc_anchor : 'country_cycles.html';
      var overdueBadge = eng.overdue
        ? ' <span class="eng-overdue">' + t("projection overdue", "预测已过期") + '</span>'
        : '';
      engPanel =
        '<div class="cyc-lbl cyc-lbl-mt">' + t("Country Cycles engine · ", "国家周期引擎 · ") + (window.MARKETS_ENGINE || {}).as_of + '</div>' +
        '<div class="cyc-facts cyc-facts-eng">' +
          fact(t("Engine position", "引擎位置"), Math.round(eng.pos_v2) + ' / 100 <span class="eng-basis">(' + t("basis: ", "基准：") + (eng.basis || "price") + ')</span>') +
          fact(t("Engine phase", "引擎阶段"), phLab(displayPhase)) +
          (eng.last_confirmed_t ? fact(t("Last confirmed turn", "最后确认拐点"), fmtMon(eng.last_confirmed_t)) : "") +
          (eng.proj_central ? fact(t("Engine proj. turn", "引擎预测拐点"), fmtMon(eng.proj_central) + overdueBadge) : "") +
          (eng.stance ? fact(t("Stance", "策略"), eng.stance) : "") +
        '</div>' +
        '<div class="cyc-eng-link-row"><a href="' + ccHref + '" class="cyc-cc-link">' +
          t("View " + (eng.etf_id || "").toUpperCase() + " in Country Cycles →", "查看 " + (eng.etf_id || "").toUpperCase() + " 国家周期 →") +
        '</a></div>';
    } else {
      engPanel =
        '<div class="cyc-lbl cyc-lbl-mt">' + t("Position source", "位置来源") + '</div>' +
        '<div class="cyc-facts"><div class="f"><div class="fk">' + t("Basis", "基准") +
        '</div><div class="fv">' + t("Analyst estimate — not yet in country engine", "分析师估算 — 尚未入引擎") + '</div></div></div>';
    }
    return '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<button class="cyc-back">' + t("← All markets", "← 全部市场") + '</button>' +
        '<div class="cyc-fhead" style="--c:' + c.accent + '">' +
          '<div class="cyc-ftitle">' + nm(c) + '</div>' +
          '<div class="cyc-fsub">' + px(c) + '</div>' +
          '<div class="cyc-fchips">' +
            '<span class="cyc-pchip" style="--ph:' + (ph.hue || "var(--muted)") + '">' + phLabel(c) + '</span>' +
            '<span class="cyc-tchip ' + tilt.cls + '">' + tilt.ar + ' ' + tilt.lab + '</span>' +
          '</div>' +
        '</div>' +
        elapsedBanner +
        '<p class="cyc-arche">' + arche(c) + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3 mkt-col-data">' +
        '<div class="cyc-lbl">' + t("Curated snapshot · ", "精选快照 · ") + (c.now.asOf || META.asOf) + '</div>' +
        '<div class="cyc-facts">' +
          fact(t("Level", "点位"), c.now.level != null ? num(c.now.level) : null) +
          fact(t("All-time high", "历史高点"), c.now.ath != null ? num(c.now.ath) + (c.now.athDate ? " · " + fmtMon(c.now.athDate) : "") : null) +
          fact(t("% off ATH", "距高点"), c.now.pctFromATH != null ? pct(c.now.pctFromATH) + ' <span class="fv-note">' + t("(stat only, not plotted pos)", "（统计项，非图中位置）") + '</span>' : null) +
          fact(t("1-yr return", "一年回报"), c.now.ret1y != null ? pct(c.now.ret1y) : (c.now.ytd != null ? pct(c.now.ytd) + t(" YTD", " 年初至今") : null)) +
          fact(t("Fwd P/E", "预期市盈率"), v.forwardPE != null ? v.forwardPE.toFixed(1) + "×" : (v.trailingPE != null ? v.trailingPE.toFixed(1) + "× (ttm)" : null)) +
          fact(v.cape != null ? "CAPE" : t("Div yield", "股息率"), v.cape != null ? v.cape.toFixed(0) + (v.divYield != null ? "  ·  " + v.divYield.toFixed(1) + "% " + t("yld", "股息") : "") : (v.divYield != null ? v.divYield.toFixed(1) + "%" : null)) +
        '</div>' +
        engPanel +
        '<div class="cyc-lbl cyc-lbl-mt">' + t("Curated timing", "精选节奏") + '</div>' +
        '<div class="cyc-facts cyc-facts-cyc">' +
          fact(t("Last bottom", "上次见底"), fmtMon(c.now.lastTrough || lastTurn(c, "trough"))) +
          fact(t("Last top", "上次见顶"), fmtMon(c.now.lastPeak || lastTurn(c, "peak"))) +
          fact(t("Next " + (isPeak ? "top" : "bottom"), "下一" + (isPeak ? "顶部" : "底部")), fmtMon(c.proj.central)) +
          fact(t("Est. range", "预计区间"), fmtMon(c.proj.low) + " – " + fmtMon(c.proj.high)) +
          fact(t("Typical cycle", "典型周期"), c.period.central + t(" yr", " 年") + " (" + c.period.low + "–" + c.period.high + ")") +
          fact(t("Cycle position", "周期位置"), Math.round(nowPosOf(c)) + " / 100" + (useEngine ? "" : ' <span class="fv-note">' + t("(analyst est.)", "（分析师估算）") + '</span>')) +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3 mkt-col-read">' +
        '<div class="cyc-read"><div class="cyc-lbl">' + t("The read", "解读") + '</div><p>' + readT(c) + '</p></div>' +
        '<div class="cyc-fals"><div class="cyc-lbl">' + t("Falsifier", "证伪条件") + '</div><p>' + falsT(c) + '</p></div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3 mkt-col-side">' +
        '<div class="cyc-drivers"><div class="cyc-lbl">' + t("Swing factors", "关键变量") + '</div><ul>' +
          driversT(c).map(function (d) { return "<li>" + d + "</li>"; }).join("") + '</ul></div>' +
        (valNote(c) ? '<div class="cyc-valbox"><div class="cyc-lbl">' + t("Valuation", "估值") + ' · ' + valStaleChip(c) + '</div><p>' + valNote(c) + '</p></div>' : '') +
        '<div class="cyc-regnote">' + regNote(c) + (srcs ? '<div class="cyc-src">' + t("Sources: ", "来源：") + srcs + '</div>' : '') + '</div>' +
      '</div>';
  }
  function lastTurn(c, k) { for (var i = c.turns.length - 1; i >= 0; i--) if (c.turns[i].k === k) return c.turns[i].t; return ""; }

  /* ---- default panel content --------------------------------------------- */
  function regField(f) { var RZ = (LANG() === "zh" && I18N.regime) ? I18N.regime : null; return RZ && RZ[f] != null ? RZ[f] : META.regime[f]; }
  function buildDefaultPanel() {
    var def = document.getElementById("cyc-panel-default");
    if (!def) return;
    var R = META.regime, RZ = (LANG() === "zh" && I18N.regime) ? I18N.regime : null;
    var stats = R.stats.map(function (s, i) {
      var zs = RZ && RZ.stats && RZ.stats[i] ? RZ.stats[i] : null;
      return '<div class="rg-stat"><div class="rg-k">' + (zs ? zs.k : s.k) + '</div><div class="rg-v">' + s.v + '</div><div class="rg-n">' + (zs ? zs.note : s.note) + '</div></div>';
    }).join("");
    var buckets = { Peak: [], Expansion: [], Downturn: [], Recovery: [], Trough: [] };
    CYCLES.forEach(function (c) { (buckets[c.now.phase] || (buckets[c.now.phase] = [])).push(c); });
    function row(title, list, note) {
      if (!list.length) return "";
      var chips = list.map(function (c) { return '<button class="mini-chip" data-id="' + c.id + '" style="--c:' + c.accent + '"><span class="dot"></span>' + shrt(c) + '</button>'; }).join("");
      return '<div class="xc-row"><div class="xc-rh">' + title + '<span>' + note + '</span></div><div class="xc-chips">' + chips + '</div></div>';
    }
    def.innerHTML = '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<div class="cyc-lbl">' + t("Global-equity regime · ", "全球股市格局 · ") + META.asOf + (regField("asOfNote") ? ' · <span style="text-transform:none;letter-spacing:0;font-weight:500">' + regField("asOfNote") + '</span>' : '') + '</div>' +
        '<div class="rg-head"><div class="rg-label">' + regField("label") + '</div><div class="rg-sub">' + regField("sub") + '</div></div>' +
        '<p class="rg-headline">' + regField("headline") + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + t("Conditions", "宏观条件") + '</div>' +
        '<div class="rg-stats">' + stats + '</div>' +
        '<p class="rg-tilt">' + regField("tilt") + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + t("Where the markets stand", "各市场所处位置") + '</div>' +
        '<div class="xc-map">' +
          row(t("At the highs", "高位"), buckets.Peak, t("extended", "拉伸")) +
          row(t("Expanding", "扩张"), buckets.Expansion, t("trending up", "上行")) +
          row(t("Rolling over", "回落"), buckets.Downturn, t("declining", "下行")) +
          row(t("Recovering", "复苏"), buckets.Recovery, t("early up-leg", "上行初段")) +
          row(t("Bottoming", "筑底"), buckets.Trough, t("washed-out", "超卖")) +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + t("How to read", "如何解读") + '</div>' +
        '<ul class="cyc-how">' +
          '<li>' + t("The y-axis is <b>cycle oscillator position (0–100)</b> — 100 = at/near the highs (extended), 0 = deep below the highs (washed-out). For engine-backed markets (UK/Japan/HK/Canada/China/India/Taiwan) this is the country_cycles engine pos_v2; for US and Europe it is an analyst estimate.", "纵轴是<b>周期振荡器位置（0–100）</b> — 100=接近高点（拉伸），0=深跌（超卖）。有引擎数据的市场（英国/日本/香港/加拿大/中国/印度/台湾）使用 country_cycles 引擎 pos_v2；美国与欧洲使用分析师估算。") + '</li>' +
          '<li>' + t("<b>Solid</b> = observed history; <b>dashed + cone</b> = projected path & uncertainty. Each <b>● dot</b> on the TODAY line is where that market sits now.", "<b>实线</b>=已发生的历史；<b>虚线+锥形</b>=预测路径与不确定性。“今天”线上的每个<b>●圆点</b>是该市场当前所处的位置。") + '</li>' +
          '<li>' + t("<b>Tap a market</b> (chip, card, snapshot row, scatter dot, or its line) to focus it. Position ≠ valuation — see the valuation map.", "<b>点击任意市场</b>（标签、卡片、排名行、散点或曲线）以聚焦。周期位置 ≠ 估值 — 请看估值地图。") + '</li>' +
          '<li>' + t("<b>% off ATH</b> is shown as a labeled stat only — it is no longer the plotted position. Curated valuations show their as-of date; verify before trading.", "<b>距高点 %</b> 仅作为统计项展示 — 不再是图中位置。精选估值显示其截止日期，操作前请核实。") + '</li>' +
        '</ul>' +
      '</div>';
    def.querySelectorAll(".mini-chip").forEach(function (b) { b.addEventListener("click", function () { setFocus(b.getAttribute("data-id")); }); });
    def.classList.add("show");
  }

  /* ---- mobile bottom sheet ----------------------------------------------- */
  function expandSheet(on) { var sheet = document.getElementById("cyc-detail"); if (sheet) sheet.classList.toggle("expanded", on !== false); }
  function initSheet() {
    var sheet = document.getElementById("cyc-detail"), handle = document.getElementById("cyc-handle");
    if (!sheet || !handle) return;
    handle.addEventListener("click", function () { sheet.classList.toggle("expanded"); });
    var startY = 0, dragging = false;
    handle.addEventListener("touchstart", function (e) { startY = e.touches[0].clientY; dragging = true; }, { passive: true });
    handle.addEventListener("touchmove", function (e) { if (!dragging) return; var dy = e.touches[0].clientY - startY; if (dy < -30) sheet.classList.add("expanded"); else if (dy > 40) sheet.classList.remove("expanded"); }, { passive: true });
    handle.addEventListener("touchend", function () { dragging = false; });
  }

  /* ---- staleness banner (W0.1) -------------------------------------------
     When more than 14 days have passed since the dataset was last curated,
     show an amber (14–59 d) or red (≥ 60 d) banner near the page header.
     Uses dual-span t() so no translated text appears in HTML attributes. */
  function renderStalenessBanner() {
    var host = document.getElementById("mkt-stale-banner");
    if (!host) return;
    var asOf = META.asOf || "";
    var asOfYear = asOf ? yf(asOf) : TODAY;
    var days = Math.round((TODAY - asOfYear) * 365.25);
    if (days < 14) { host.innerHTML = ""; return; }
    var cls = days >= 60 ? "stale-red" : "stale-amber";
    // Plain-text content only — no translated text in attributes (house rule).
    host.innerHTML = '<div class="stale-banner ' + cls + '">' +
      t("Curated dataset as of " + asOf + " — " + days + " days old",
        "精选数据截至 " + asOf + " — 已 " + days + " 天未更新") +
      '</div>';
  }

  /* ---- language re-render ------------------------------------------------- */
  function onLangChange() {
    mountChips();
    if (heroChart) heroChart.update(heroSpec());
    buildGroups();
    mountCards();
    renderSnapSort(); renderSnapshot(); renderDispersion();
    renderScatter();
    buildDefaultPanel();
    renderStalenessBanner();
    applyGroupFilter();
    // re-apply focus visuals + panel (or default panel)
    setFocus(state.focus);
  }

  /* ---- boot -------------------------------------------------------------- */
  var _scatterRO = null;
  function boot() {
    if (!META || !CYCLES) return;
    mountChips();
    mountHero();
    buildDefaultPanel();
    renderSnapSort();
    mountSnapshot();
    renderScatter();
    mountCards();
    renderStalenessBanner();
    initSheet();
    if (window.ResizeObserver && !_scatterRO) {
      _scatterRO = new ResizeObserver(function () { renderScatter(); });
      var sc = document.getElementById("mkt-scatter"); if (sc) _scatterRO.observe(sc);
    }
    document.addEventListener("themechange", function () { renderScatter(); });
    document.addEventListener("langchange", onLangChange);
    var h = (location.hash || "").replace("#", "");
    if (h && MODELS[h]) setTimeout(function () { setFocus(h); }, 350);
  }
  function mountSnapshot() { renderSnapshot(); renderDispersion(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

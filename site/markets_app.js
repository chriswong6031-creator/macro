/* ============================================================================
   markets_app.js — Global Market Cycles Dashboard · orchestration (v3, bilingual)
   ----------------------------------------------------------------------------
   v2 features (real web-sourced data, amplitude-faithful oscillator, valuation
   lens, now-snapshot + dispersion, scatter) + full EN/ZH i18n:
     · t(en, zh) for every app-generated string; PHASE_ZH for phase labels.
     · data prose (archetype/read/regimeNote/valuation/drivers/falsifier/turn
       events/name/proxy/short) read from window.MARKET_I18N when data-lang="zh",
       falling back to English.
     · re-renders the whole text layer on the shared `langchange` event.
   Reuses cycle.css + markets.css; static chrome is bilingual via .l-en/.l-zh spans.
   ========================================================================== */
(function () {
  "use strict";

  var META = window.MARKET_META, CYCLES = window.MARKETS, PHASES = window.MARKET_PHASES;
  var I18N = window.MARKET_I18N || { markets: {}, regime: null };
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

  /* ---- AMPLITUDE-FAITHFUL position model ---------------------------------- */
  function posFromDrawdown(ddPct) { var d = Math.max(0, -(ddPct || 0)); return clamp(Math.round(92 * Math.exp(-d / 30)), 3, 97); }

  function build(c) {
    var today = META.today;
    var runMax = -Infinity;
    var turns = c.turns.map(function (tp) {
      var y;
      if (tp.v != null) { runMax = Math.max(runMax, tp.v); y = posFromDrawdown((tp.v / runMax - 1) * 100); }
      else { y = tp.k === "peak" ? 88 : 16; }
      return { x: yf(tp.t), y: y, k: tp.k, e: tp.e, v: tp.v, t: tp.t };
    });
    var n = turns.length, last = turns[n - 1];
    var nowPos = c.now.pctFromATH != null ? posFromDrawdown(c.now.pctFromATH)
      : (c.now.pos != null ? clamp(c.now.pos, 3, 97) : (last.y + 50) / 2);
    var nextY = c.proj.nextTurn === "peak" ? clamp(Math.max(nowPos + 8, 88), 80, 96) : clamp(Math.min(nowPos - 18, 34), 10, 44);
    var tc = Math.max(yf(c.proj.central), today + 0.15);
    var te = clamp(yf(c.proj.low), today + 0.05, tc);
    var tl = Math.max(yf(c.proj.high), tc + 0.1);
    var relax = c.proj.nextTurn === "peak" ? 58 : 44;
    var projEnd = Math.min(META.xDomain[1], tl + 0.35 * (tl - today));

    function projAt(x, tt) { if (x <= tt) return cos(x, today, nowPos, tt, nextY); return cos(x, tt, nextY, projEnd, relax); }
    var center = function (x) { return x <= today ? cos(x, last.x, last.y, today, nowPos) : projAt(x, tc); };
    var withTurn = function (x, tt) { return x <= today ? center(x) : projAt(x, tt); };

    var hist = [], step = 0.16;
    for (var i = 0; i < n - 1; i++) { var a = turns[i], b = turns[i + 1]; for (var x = a.x; x < b.x - 1e-6; x += step) hist.push({ x: x, y: cos(x, a.x, a.y, b.x, b.y) }); }
    hist.push({ x: last.x, y: last.y });
    for (var xx = last.x + step; xx <= today; xx += step) hist.push({ x: xx, y: center(xx) });
    hist.push({ x: today, y: center(today) });

    var proj = [];
    for (var xp = today; xp <= projEnd + 1e-6; xp += step) proj.push({ x: xp, y: projAt(xp, tc) });

    var tlt = c.proj.tilt, hiW = tlt === "tailwind" ? 1.35 : tlt === "headwind" ? 0.7 : 1, loW = tlt === "headwind" ? 1.35 : tlt === "tailwind" ? 0.7 : 1;
    var cone = [];
    for (var xc = today; xc <= projEnd + 1e-6; xc += step) {
      var vs = [withTurn(xc, te), center(xc), withTurn(xc, tl)];
      var lo = Math.min(vs[0], vs[1], vs[2]), hi = Math.max(vs[0], vs[1], vs[2]);
      var amp = lerp(1.5, 13, clamp((xc - today) / (projEnd - today), 0, 1));
      cone.push({ x: xc, lo: clamp(lo - amp * loW, 2, 98), hi: clamp(hi + amp * hiW, 2, 98) });
    }

    var markers = turns.filter(function (tp) { return tp.x >= META.xDomain[0] - 0.2; })
      .map(function (tp) { return { x: tp.x, y: tp.y, kind: tp.k, label: fmtMon(tp.t), sub: tp.e }; });
    var nowY = center(today);
    markers.push({ x: today, y: nowY, kind: "now", label: t("Now", "现在"), sub: phLabel(c) });

    return { id: c.id, color: c.accent, label: nm(c), width: 2, hist: hist, proj: proj, cone: cone, markers: markers,
      nowY: nowY, tc: tc, te: te, tl: tl, projEnd: projEnd, legPct: clamp((today - last.x) / (tc - last.x), 0, 1), c: c };
  }

  var MODELS = {}, ORDER = [];
  CYCLES.forEach(function (c) { MODELS[c.id] = build(c); ORDER.push(c.id); });
  function nowPosOf(c) { return MODELS[c.id].nowY; }

  /* ---- collective inflection zones --------------------------------------
     Cluster each market's PROJECTED next turn by direction + timing: where ≥3
     markets are projected to top (amber) or bottom (green) within ~6 months of
     each other = a synchronized inflection window, drawn as a timeline vband. */
  function median(a) { var s = a.slice().sort(function (x, y) { return x - y; }); var m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }
  function dcMon(cx) { var y = Math.floor(cx); var m = clamp(Math.round((cx - y) * 12 + 0.5), 1, 12); return fmtMon(y + "-" + (m < 10 ? "0" + m : m)); }
  function convergenceBands() {
    var DIRS = [
      { dir: "peak", color: "var(--warn)", sym: "▲", lab: ["tops", "共振顶"], labelY: 12 },
      { dir: "trough", color: "var(--up)", sym: "▼", lab: ["bottoms", "共振底"], labelY: 30 }
    ];
    var out = [];
    DIRS.forEach(function (D) {
      var items = CYCLES.map(function (c) { return { short: shrt(c), cx: yf(c.proj.central), dir: c.proj.nextTurn }; })
        .filter(function (p) { return p.dir === D.dir && p.cx > META.today; })
        .sort(function (a, b) { return a.cx - b.cx; });
      var groups = [], cur = null;
      items.forEach(function (p) { if (cur && p.cx - cur[cur.length - 1].cx <= 0.5) cur.push(p); else { cur = [p]; groups.push(cur); } });
      groups.forEach(function (g) {
        if (g.length < 3) return;
        var cxs = g.map(function (p) { return p.cx; }), x0 = Math.min.apply(null, cxs), x1 = Math.max.apply(null, cxs), cx = median(cxs);
        if (x1 - x0 < 0.22) { var mid = (x0 + x1) / 2; x0 = mid - 0.11; x1 = mid + 0.11; }
        var names = g.map(function (p) { return p.short; }).join(t(", ", "、"));
        out.push({
          x0: x0, x1: x1, cx: cx, color: D.color, opacity: 0.1, labelY: D.labelY,
          label: D.sym + g.length + " " + t(D.lab[0], D.lab[1]),
          title: t(g.length + " markets project a " + (D.dir === "peak" ? "top" : "bottom") + " ≈ " + dcMon(cx) + ":  ", g.length + " 个市场预计于 " + dcMon(cx) + " 前后" + (D.dir === "peak" ? "见顶" : "见底") + "：") + names
        });
      });
    });
    return out;
  }

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
      vbands: convergenceBands(),
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
    if (c.now.level != null) out.push('<span class="cc-stat"><b>' + num(c.now.level) + '</b><i>' + t("level", "点位") + '</i></span>');
    if (c.now.pctFromATH != null) out.push('<span class="cc-stat ' + (c.now.pctFromATH < -1 ? "neg" : "pos") + '"><b>' + pct(c.now.pctFromATH) + '</b><i>' + t("vs ATH", "距高点") + '</i></span>');
    if (v.forwardPE != null) out.push('<span class="cc-stat"><b>' + v.forwardPE.toFixed(1) + '×</b><i>' + t("fwd P/E", "预期PE") + '</i></span>');
    else if (v.trailingPE != null) out.push('<span class="cc-stat"><b>' + v.trailingPE.toFixed(1) + '×</b><i>' + t("P/E", "市盈率") + '</i></span>');
    if (v.cape != null) out.push('<span class="cc-stat"><b>' + v.cape.toFixed(0) + '</b><i>CAPE</i></span>');
    if (v.divYield != null) out.push('<span class="cc-stat"><b>' + v.divYield.toFixed(1) + '%</b><i>' + t("yield", "股息") + '</i></span>');
    return out.join("");
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
      card.innerHTML =
        '<div class="cc-top">' +
          '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + nm(c) + '</div>' +
          '<div class="cc-px">' + px(c) + '</div></div></div>' +
          '<div class="cc-phase" style="--ph:' + (ph.hue || "var(--muted)") + '">' + phLab(c.now.phase) + '</div>' +
        '</div>' +
        '<div class="cc-spark"></div>' +
        '<div class="cc-stats">' + valChips(c) + '</div>' +
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
    var m = MODELS[c.id], ph = PHASES[c.now.phase] || {}, tilt = tiltOf(c.proj.tilt), v = c.valuation || {};
    var isPeak = c.proj.nextTurn === "peak";
    function fact(k, val) { return val == null || val === "" ? "" : '<div class="f"><div class="fk">' + k + '</div><div class="fv">' + val + '</div></div>'; }
    var srcs = (c.sources || []).slice(0, 4).map(function (u) { return '<a href="' + u + '" target="_blank" rel="noopener">' + srcHost(u) + '</a>'; }).join("");
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
        '<p class="cyc-arche">' + arche(c) + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3 mkt-col-data">' +
        '<div class="cyc-lbl">' + t("Live read · ", "实时数据 · ") + (c.now.asOf || META.asOf) + '</div>' +
        '<div class="cyc-facts">' +
          fact(t("Level", "点位"), c.now.level != null ? num(c.now.level) : null) +
          fact(t("All-time high", "历史高点"), c.now.ath != null ? num(c.now.ath) + (c.now.athDate ? " · " + fmtMon(c.now.athDate) : "") : null) +
          fact(t("% off ATH", "距高点"), c.now.pctFromATH != null ? pct(c.now.pctFromATH) : null) +
          fact(t("1-yr return", "一年回报"), c.now.ret1y != null ? pct(c.now.ret1y) : (c.now.ytd != null ? pct(c.now.ytd) + t(" YTD", " 年初至今") : null)) +
          fact(t("Fwd P/E", "预期市盈率"), v.forwardPE != null ? v.forwardPE.toFixed(1) + "×" : (v.trailingPE != null ? v.trailingPE.toFixed(1) + "× (ttm)" : null)) +
          fact(v.cape != null ? "CAPE" : t("Div yield", "股息率"), v.cape != null ? v.cape.toFixed(0) + (v.divYield != null ? "  ·  " + v.divYield.toFixed(1) + "% " + t("yld", "股息") : "") : (v.divYield != null ? v.divYield.toFixed(1) + "%" : null)) +
        '</div>' +
        '<div class="cyc-lbl cyc-lbl-mt">' + t("Cycle timing", "周期节奏") + '</div>' +
        '<div class="cyc-facts cyc-facts-cyc">' +
          fact(t("Last bottom", "上次见底"), fmtMon(c.now.lastTrough || lastTurn(c, "trough"))) +
          fact(t("Last top", "上次见顶"), fmtMon(c.now.lastPeak || lastTurn(c, "peak"))) +
          fact(t("Next " + (isPeak ? "top" : "bottom"), "下一" + (isPeak ? "顶部" : "底部")), fmtMon(c.proj.central)) +
          fact(t("Est. range", "预计区间"), fmtMon(c.proj.low) + " – " + fmtMon(c.proj.high)) +
          fact(t("Typical cycle", "典型周期"), c.period.central + t(" yr", " 年") + " (" + c.period.low + "–" + c.period.high + ")") +
          fact(t("Cycle position", "周期位置"), Math.round(m.nowY) + " / 100") +
        '</div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3 mkt-col-read">' +
        '<div class="cyc-read"><div class="cyc-lbl">' + t("The read", "解读") + '</div><p>' + readT(c) + '</p></div>' +
        '<div class="cyc-fals"><div class="cyc-lbl">' + t("Falsifier", "证伪条件") + '</div><p>' + falsT(c) + '</p></div>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3 mkt-col-side">' +
        '<div class="cyc-drivers"><div class="cyc-lbl">' + t("Swing factors", "关键变量") + '</div><ul>' +
          driversT(c).map(function (d) { return "<li>" + d + "</li>"; }).join("") + '</ul></div>' +
        (valNote(c) ? '<div class="cyc-valbox"><div class="cyc-lbl">' + t("Valuation", "估值") + '</div><p>' + valNote(c) + '</p></div>' : '') +
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
          '<li>' + t("The y-axis is <b>% retraced from the all-time high</b> — high = at/near the highs (extended), low = deep below the highs (washed-out). A −57% crash plunges near 0; a −12% dip only eases to ~55.", "纵轴是<b>距历史高点的回撤幅度</b> — 越高=越接近高点（拉伸），越低=深跌（超卖）。−57% 的崩盘会跌到接近 0；−12% 的小回调只回落到约 55。") + '</li>' +
          '<li>' + t("<b>Solid</b> = observed history; <b>dashed + cone</b> = projected path & uncertainty. Each <b>● dot</b> on the TODAY line is where that market sits now.", "<b>实线</b>=已发生的历史；<b>虚线+锥形</b>=预测路径与不确定性。“今天”线上的每个<b>●圆点</b>是该市场当前所处的位置。") + '</li>' +
          '<li>' + t("<b>Tap a market</b> (chip, card, snapshot row, scatter dot, or its line) to focus it. Position ≠ valuation — see the valuation map.", "<b>点击任意市场</b>（标签、卡片、排名行、散点或曲线）以聚焦。周期位置 ≠ 估值 — 请看估值地图。") + '</li>' +
          '<li>' + t("<b>Shaded vertical zones</b> on the timeline mark where ≥3 markets are projected to top (amber ▲) or bottom (green ▼) together — a possible synchronized inflection window. Hover the pill for the names.", "时间轴上的<b>竖向阴影带</b>标示≥3个市场预计同步见顶（琥珀色 ▲）或见底（绿色 ▼）的时间窗口 —— 潜在的共振拐点。将鼠标悬停在标签上可查看具体市场。") + '</li>' +
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

  /* ---- language re-render ------------------------------------------------- */
  function onLangChange() {
    mountChips();
    if (heroChart) heroChart.update(heroSpec());
    buildGroups();
    mountCards();
    renderSnapSort(); renderSnapshot(); renderDispersion();
    renderScatter();
    buildDefaultPanel();
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

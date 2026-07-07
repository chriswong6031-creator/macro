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

  /* FIX 1b — strip "(Equal-Weight)" / "（等权）" suffixes from all string values at boot */
  (function deepStrip(obj) {
    if (!obj || typeof obj !== 'object') return;
    var ewRe = /\s*[（(]\s*(?:equal[-\s]?weight(?:ed)?|等权(?:重)?)\s*[）)]/gi;
    var keys = Object.keys(obj);
    for (var _k = 0; _k < keys.length; _k++) {
      var _key = keys[_k], _val = obj[_key];
      if (typeof _val === 'string') { obj[_key] = _val.replace(ewRe, ''); }
      else if (_val && typeof _val === 'object') { deepStrip(_val); }
    }
  }(DATA));
  (function deepStrip(obj) {
    if (!obj || typeof obj !== 'object') return;
    var ewRe = /\s*[（(]\s*(?:equal[-\s]?weight(?:ed)?|等权(?:重)?)\s*[）)]/gi;
    var keys = Object.keys(obj);
    for (var _k = 0; _k < keys.length; _k++) {
      var _key = keys[_k], _val = obj[_key];
      if (typeof _val === 'string') { obj[_key] = _val.replace(ewRe, ''); }
      else if (_val && typeof _val === 'object') { deepStrip(_val); }
    }
  }(NARR));
  if (window.SECTOR_DNA) {
    (function deepStrip(obj) {
      if (!obj || typeof obj !== 'object') return;
      var ewRe = /\s*[（(]\s*(?:equal[-\s]?weight(?:ed)?|等权(?:重)?)\s*[）)]/gi;
      var keys = Object.keys(obj);
      for (var _k = 0; _k < keys.length; _k++) {
        var _key = keys[_k], _val = obj[_key];
        if (typeof _val === 'string') { obj[_key] = _val.replace(ewRe, ''); }
        else if (_val && typeof _val === 'object') { deepStrip(_val); }
      }
    }(window.SECTOR_DNA));
  }
  var META = DATA.meta, PHASES = DATA.phases, SECTORS = DATA.sectors;
  var BASKETS = DATA.baskets || [];
  var NASDAQ = DATA.nasdaq || [];
  var RUSSELL = DATA.russell || [];
  var ALL = SECTORS.concat(BASKETS, NASDAQ, RUSSELL);  // one chart space, shared by all families
  var basketShown = {};                          // basket id -> selected/on the chart? (boot selects all)

  /* ---- family registry: each non-sector family is "basket-like" ----------- */
  var FAM = {
    sectors: { list: function () { return SECTORS; }, kind: "sector" },
    baskets:  { list: function () { return BASKETS; },  kind: "basket"  },
    nasdaq:   { list: function () { return NASDAQ; },   kind: "nasdaq"  },
    russell:  { list: function () { return RUSSELL; },  kind: "russell" }
  };
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
  var state = { mode: "osc", scale: "log", focus: null, family: "sectors" };
  function activeList() { return FAM[state.family] ? FAM[state.family].list() : SECTORS; }
  function isActive(s) { return s.kind === (FAM[state.family] || FAM.sectors).kind; }
  // helpers to distinguish "basket-like" families (all non-sectors) from the sectors family
  function isBasketLike() { return state.family !== "sectors"; }
  function isBasketRec(s) { return s.kind !== "sector"; }

  /* ---- mobile (China) view model ---------------------------------------- */
  // The desktop layout (full overlay + always-on detail underbar) is forced onto a
  // phone. On <=880px China we instead show a legible FEW lines by default (the top
  // relative-strength leaders), let a focus / Series-pick / Show-all override it, and
  // drive the detail as a true hidden-at-rest bottom sheet. Everything here is gated on
  // isCnMobile() so desktop (US + China) and the shared US mobile page are untouched.
  var IS_CN = META.region === "china";
  var IS_INTL = META.region === "intl";
  // unit noun for one series in the default (non-basket) family: US/China = "sector",
  // intl = "market". For US/China these resolve to the original literals, so every
  // rendered string on those pages stays byte-identical to before.
  function unitE() { return IS_INTL ? "market" : "sector"; }    // lower-case English
  function unitEC() { return IS_INTL ? "Market" : "Sector"; }   // capitalised English
  function unitZ() { return IS_INTL ? "市场" : "板块"; }         // Chinese
  function isMobile() { return window.innerWidth <= 880; }
  function isCnMobile() { return IS_CN && isMobile(); }
  var mobileSel = null;        // explicit per-id chart selection (Series picker); null = leaders default
  var mobileShowAll = false;   // user opted into the full overlay
  function mobileLeaders() {   // top-5 of the ACTIVE family by relative strength
    var m = {};
    activeList().filter(function (s) { return s.now && s.now.rs_rank; })
      .sort(function (a, b) { return a.now.rs_rank - b.now.rs_rank; })
      .slice(0, 5).forEach(function (s) { m[s.id] = true; });
    return m;
  }
  function mobileShownCount() {   // how many of the active family are actually on the chart
    return activeList().filter(function (s) { return !chartHidden[s.id]; }).length;
  }

  /* ---- small helpers ----------------------------------------------------- */
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  // respect the OS "reduce motion" setting for the chart's draw/transition animations
  var REDUCE = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  // keyboard activation for role="button" elements that aren't native <button>s
  function keyActivate(node) { node.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); node.click(); } }); }
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

  /* ---- W3.6: ontology STANCE + DIVERGENCE rendering ----------------------
     The kernel (engine/cycle_ontology.resolve_state) stamps the resolved action
     into now.stance / now.stance_zh / now.tone and the "clocks disagree" flag into
     now.divergence / now.divergence_note{,_zh}.  JS renders those stamped outputs —
     it never recomputes a stance (D1 doctrine).  tone → an existing root color token
     so the zh up/down flip keeps working with zero new color logic (A18):
       bullish → --up  (flips red/green in zh)   bearish → --down (flips in zh)
       caution → --warn (no flip)   anticipatory → accent (no flip)   neutral → --muted (no flip)
     Only the bullish/bearish tones ride flip-sensitive tokens; the direction-less
     stances (WAIT / GET READY / TRIM / COUNTERTREND ONLY / HIGH-RISK BOUNCE) do not. */
  var TONE_CLS = {
    bullish: "st-bull", bearish: "st-bear", caution: "st-caut",
    anticipatory: "st-antic", neutral: "st-neu"
  };
  function stanceLabel(nw) { return curLang() === "zh" ? (nw.stance_zh || nw.stance) : nw.stance; }
  function stanceHTML(nw) {
    if (!nw || !nw.stance) return "";
    var cls = TONE_CLS[nw.tone] || "st-neu";
    return '<span class="cc-stance ' + cls + '" title="' +
      L("Resolved stance · engine", "综合策略 · 引擎") + '">' + stanceLabel(nw) + '</span>';
  }
  // amber "clocks disagree" chip — rendered ONLY when the cycle read and the timing
  // ladder disagree (D1 §2.3).  Replaces two contradictory action badges with one honest chip.
  function divergenceHTML(nw, opts) {
    if (!nw || !nw.divergence) return "";
    var full = opts && opts.full;
    var note = curLang() === "zh" ? (nw.divergence_note_zh || nw.divergence_note) : nw.divergence_note;
    var chip = '<span class="cc-diverge" title="' + (note ? esc(note) : "") + '">⚠︎ ' +
      L("Clocks disagree", "时钟分歧") + '</span>';
    if (!full) return chip;
    // focus panel: chip + the full explanatory note line
    return '<div class="cc-diverge-row">' + chip +
      (note ? '<span class="cc-diverge-note">' + esc(note) + '</span>' : "") + '</div>';
  }
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

  /* ---- W3.9: FX-decomposition UX (INTL/country page only) ----------------
     The country card's PRIMARY chart/position is now the LOCAL-currency equity
     cycle (the engine promotes the local record to the top-level fields, so the
     card renders it with zero structural change).  These helpers add, INTL-only:
       · a currency-glyph chip when the latest turn was currency-driven (fx_flag),
       · a "USD view" link chip (the USD ETF cycle lives in the drawer),
       · a per-turn currency glyph on the flagged cycle legs,
       · a per-country DRAWER: the FX cycle leg + the local-vs-USD divergence.
     Every string is bilingual via L(); nothing here runs on US/China (IS_INTL). */
  var CUR_GLYPH = "₵";   // generic currency glyph for a currency-driven turn badge
  function hasFx(s) { return IS_INTL && s && s.fx && s.fx.pair; }           // decomposed single-country
  function lcSourceLabel(s) {
    return s.lc_source === "native" ? L("native index", "本地指数")
      : s.lc_source === "synthetic" ? L("ETF ÷ FX", "ETF ÷ 汇率") : "";
  }
  // one-glance card chip: fires when the MOST RECENT local turn was >60% currency.
  function fxCardChip(s) {
    if (!hasFx(s) || !s.now || !s.now.fx_driven_last) return "";
    var pct = s.now.fx_share_last != null ? Math.round(s.now.fx_share_last * 100) : null;
    var tip = pct != null
      ? L("currency drove " + pct + "% of this USD move", "货币驱动了此美元波动的 " + pct + "%")
      : L("last turn was currency-driven", "上次拐点由货币驱动");
    return '<span class="cc-fx" title="' + esc(tip) + '">' + CUR_GLYPH + " " +
      L("FX-driven", "汇率驱动") + '</span>';
  }
  // small "USD view" pill in the detail head — the USD ETF cycle is disclosed in the drawer.
  function usdViewChip(s) {
    if (!hasFx(s) || !s.usd_record) return "";
    return '<span class="cc-usdview" title="' +
      esc(L("This card shows the LOCAL-currency equity cycle. See the FX drawer for the USD-ETF view.",
            "本卡显示本地货币股票周期。美元 ETF 视图见汇率抽屉。")) + '">' +
      L("Local · USD view ↓", "本地 · 美元视图 ↓") + '</span>';
  }
  // per-country FX drawer: currency-cycle leg + local-vs-USD honesty delta + peg note.
  function fxDrawerHTML(s) {
    if (!hasFx(s)) return "";
    var fx = s.fx, ur = s.usd_record, nw = s.now;
    var rows = [];
    // 1) basis line — which local tape this card runs on.
    rows.push('<div class="f"><div class="fk">' + L("Local basis", "本地基准") +
      '</div><div class="fv">' + lcSourceLabel(s) + '</div></div>');
    // 2) the FX currency-cycle read (same kernel on the FX pair).
    if (fx.cycle_pos != null) {
      var fxPhase = fx.cycle_phase ? (PHASE_LAB[fx.cycle_phase] ? L(PHASE_LAB[fx.cycle_phase][0], PHASE_LAB[fx.cycle_phase][1]) : fx.cycle_phase) : "";
      rows.push('<div class="f"><div class="fk">' + fx.pair + ' ' + L("cycle", "周期") +
        '</div><div class="fv">' + Math.round(fx.cycle_pos) + '/100' + (fxPhase ? ' · ' + fxPhase : '') + '</div></div>');
    }
    if (fx.leg_return_252d != null) {
      rows.push('<div class="f"><div class="fk">' + fx.pair + ' ' + L("1y", "1年") +
        '</div><div class="fv">' + (fx.leg_return_252d >= 0 ? "+" : "") + fx.leg_return_252d + '%</div></div>');
    }
    // 3) local-vs-USD divergence — the honesty delta.
    if (ur && ur.now && nw && nw.pos_v2 != null && ur.now.pos_v2 != null) {
      var d = Math.round((nw.pos_v2 - ur.now.pos_v2) * 10) / 10;
      rows.push('<div class="f"><div class="fk">' + L("Local vs USD position", "本地 vs 美元位置") +
        '</div><div class="fv">' + Math.round(nw.pos_v2) + ' vs ' + Math.round(ur.now.pos_v2) +
        ' (' + (d >= 0 ? "+" : "") + d + ')</div></div>');
    }
    // 4) peg annotation (HKD).
    var peg = fx.peg;
    var pegLine = peg ? ('<div class="cc-fx-peg">' +
      L("Hard peg " + peg.band + " · ", "硬挂钩 " + peg.band + " · ") +
      (peg.in_band ? L("in band", "在区间内") : L("OUT of band", "超出区间")) +
      ' (' + (peg.dist_bps >= 0 ? "+" : "") + peg.dist_bps + ' bps)</div>') : "";
    return '<div class="cyc-grp cyc-grp-3 cc-fx-drawer">' +
      '<div class="cyc-lbl">' + CUR_GLYPH + " " + L("Currency decomposition", "货币拆分") + '</div>' +
      '<p class="cc-fx-intro">' +
        L("This card runs on the LOCAL-currency equity cycle so the currency move doesn't masquerade as an equity turn. The USD-ETF cycle (a US investor's raw experience) and the currency's own cycle are broken out here.",
          "本卡基于本地货币股票周期，以免货币波动被误当作股票拐点。此处拆出美元 ETF 周期（美国投资者的原始体验）与货币自身的周期。") +
      '</p>' +
      '<div class="cyc-facts">' + rows.join("") + '</div>' +
      pegLine +
      '<p class="cc-fx-note">' + fxNote(s) + '</p>' +
    '</div>';
  }
  // an honest one-liner about the latest currency-driven turn, if any.
  function fxNote(s) {
    if (!s.now || !s.now.fx_driven_last) {
      return L("Recent turns were mostly equity-driven (currency < 60% of the USD move).",
               "近期拐点主要由股票驱动（货币占美元波动不足 60%）。");
    }
    var pct = s.now.fx_share_last != null ? Math.round(s.now.fx_share_last * 100) : null;
    return pct != null
      ? L("⚠ The latest turn was currency-driven: the currency drove " + pct + "% of the USD move.",
          "⚠ 最近一次拐点由货币驱动：货币占美元波动的 " + pct + "%。")
      : L("⚠ The latest turn was currency-driven.", "⚠ 最近一次拐点由货币驱动。");
  }

  /* ---- y-scaling: price (rebased, log/linear) vs cycle position (0–100) --- */
  function yval(v) { return state.mode === "osc" ? v : (state.scale === "log" ? log10(v) : v); }

  // Price RE-ANCHORING: every line is rebased to 100 at the LEFT EDGE of the
  // visible window (TradingView "percent"), so a zoom shows clean relative
  // performance from that point — not a tangled 6-year fan. curView tracks the
  // visible x-range; the anchor factor scales each series' stored (window-start)
  // rebase to the current left edge.
  // Full pannable extent is the 15y window; the chart OPENS on the ~7y default view and a
  // "Max" zoom-preset expands to the full history (data is 15y, but 15y of weekly turns is
  // dense, so the recent-but-deep 7y is the friendlier home view — Max for the long memory).
  var DEFAULT_VIEW = (META.xDomainDefault || META.xDomain);
  var WIN_Y = META.window_years || Math.round(META.xDomain[1] - META.xDomain[0]);
  var curView = DEFAULT_VIEW.slice();
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
    if (hist.length) markers.push({ x: hist[hist.length - 1].x, y: hist[hist.length - 1].y, kind: "now", label: L("Now", "当前"), sub: phaseLabel(s) });
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
      animate: !REDUCE, crosshair: true, zoom: true,
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
    if (META.xDomainDefault) heroChart.setView(DEFAULT_VIEW.slice(), false);   // open on the ~7y home view
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
    var maxYrs = Math.round(hi - lo);                 // ~15 (label adapts if the window changes)
    var presets = [
      { label: L("Max " + maxYrs + "y", "全部" + maxYrs + "年"), d: META.xDomain },   // full 15y history
      { label: L("7y", "7年"), d: DEFAULT_VIEW },     // the default home view
      { label: L("3y", "3年"), d: [hi - 3.3, hi] },
      { label: L("1y", "1年"), d: [hi - 1.3, hi] },
      { label: L("6m", "6月"), d: [hi - 0.85, hi] }
    ];
    z.innerHTML = '<span class="cyc-zhint">' + L("scroll · drag", "滚动 · 拖拽") + '</span>' +
      presets.map(function (p, i) { return '<button class="cyc-zbtn" data-i="' + i + '">' + p.label + '</button>'; }).join("") +
      '<button class="cyc-zbtn cyc-zreset" id="sc-zreset">' + L("Home ⤢", "首页 ⤢") + '</button>';
    presets.forEach(function (p, i) {
      z.querySelector('[data-i="' + i + '"]').addEventListener("click", function () { if (heroChart) heroChart.setView(p.d.slice(), true); });
    });
    // "Home" returns to the ~7y default view (not the full extent) — the intended landing window
    z.querySelector("#sc-zreset").addEventListener("click", function () { if (heroChart) heroChart.setView(DEFAULT_VIEW.slice(), true); });
  }

  /* ---- mode + scale segmented controls ----------------------------------- */
  function wireControls() {
    var modes = document.getElementById("sc-modes"), scale = document.getElementById("sc-scale");
    if (modes) modes.querySelectorAll(".sc-mbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        var m = b.getAttribute("data-mode"); if (m === state.mode) return;
        state.mode = m;
        syncHeroControls();
        rebuildHero(true); remountSparks();
      });
    });
    if (scale) scale.querySelectorAll(".sc-sbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        var sc = b.getAttribute("data-scale"); if (sc === state.scale) return;
        state.scale = sc;
        syncHeroControls();
        rebuildHero(true); remountSparks();
      });
    });
  }

  // reflect view state onto the segmented controls. Cycle position is the default view,
  // so Price is un-lit and the Log/Linear scale is meaningless → we hide it entirely
  // (no dead greyed row that reads as the user's first broken tap, esp. on mobile).
  // aria-pressed keeps the segmented buttons announced to assistive tech.
  function syncHeroControls() {
    var modes = document.getElementById("sc-modes"), scale = document.getElementById("sc-scale");
    if (modes) modes.querySelectorAll(".sc-mbtn").forEach(function (b) {
      var on = b.getAttribute("data-mode") === state.mode;
      b.classList.toggle("on", on); b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (scale) {
      scale.querySelectorAll(".sc-sbtn").forEach(function (b) {
        var on = b.getAttribute("data-scale") === state.scale;
        b.classList.toggle("on", on); b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      var locked = state.mode !== "price";
      scale.classList.toggle("disabled", locked);
      scale.hidden = locked;                       // reclaim the dead row in cycle-position mode
    }
    // the "low = washed-out · high = stretched" caption only describes the 0–100 oscillator
    var cap = document.querySelector(".sc-mode-cap"); if (cap) cap.hidden = state.mode !== "osc";
    syncLegend();
  }

  // mobile "Chart options" disclosure (scale + legend + zoom). Desktop shows them inline
  // (the toggle is display:none), so this is a no-op there.
  function wireAdvanced() {
    var t = document.getElementById("sc-adv-toggle"), w = document.getElementById("sc-advanced");
    if (!t || !w) return;
    t.addEventListener("click", function () {
      var open = w.classList.toggle("open");
      t.setAttribute("aria-expanded", open ? "true" : "false");
      if (heroChart) heroChart.resize();           // chart reflows as the panel grows/shrinks
    });
  }

  // mode-aware legend — in Cycle position there is NO price line, so don't claim one;
  // show the 0–100 band key (washed-out / mid / stretched) + a "tap a line" affordance.
  // In Price mode show the line + peak/trough glyphs. Re-localizes on language change.
  function syncLegend() {
    var leg = document.getElementById("sc-legend");
    if (!leg) return;
    if (state.mode === "osc") {
      leg.innerHTML =
        '<span><i class="lc" style="background:color-mix(in srgb,var(--down) 42%,transparent)"></i>' + L("washed-out", "超卖") + '</span>' +
        '<span><i class="lc" style="background:color-mix(in srgb,var(--muted) 32%,transparent)"></i>' + L("mid-cycle", "中段") + '</span>' +
        '<span><i class="lc" style="background:color-mix(in srgb,var(--warn) 46%,transparent)"></i>' + L("stretched", "拉伸") + '</span>' +
        '<span class="cyc-leg-hint">' + L("tap a line to focus", "点击曲线聚焦") + '</span>';
    } else {
      leg.innerHTML =
        '<span><i class="ls"></i> ' + L("Price", "价格") + '</span>' +
        '<span><i class="lm lm-pk"></i> ' + L("Peak", "波峰") + '</span>' +
        '<span><i class="lm lm-tr"></i> ' + L("Trough", "波谷") + '</span>';
    }
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
      '</span>' + L("All phases", "全部阶段") + '</button>';
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
    // Only the FOCUSED item overrides the facet — the "Where they stand" facet narrows
    // the (now all-selected-by-default) baskets the same way it narrows sectors, so the
    // facet stays a real filter. The facet is a reversible VIEW (basketShown persists
    // underneath), so an off-phase selected basket is never permanently stranded.
    function pinned(s) { return s.id === state.focus; }
    function keepShown(s) { return phaseOK(s) || pinned(s); }
    // only the ACTIVE family is ever on the chart; sectors obey the phase facet, basket-like
    // families ride on the chart only when selected — and an explicit pick overrides the facet.
    chartHidden = {};
    ALL.forEach(function (s) {
      var sel = isBasketRec(s) ? !!basketShown[s.id] : true;
      chartHidden[s.id] = !(isActive(s) && sel && keepShown(s));
    });
    // mobile (China): cap the overlay to a legible few — the top RS leaders by default,
    // or the user's explicit Series pick — so a 375px phone never gets 31-line spaghetti.
    // The phase facet still narrows first; a focused line and "Show all" both override.
    if (isCnMobile() && !mobileShowAll) {
      var _lead = mobileSel ? null : mobileLeaders();
      activeList().forEach(function (s) {
        if (chartHidden[s.id]) return;                 // already hidden by family / phase facet
        var show = mobileSel ? !!mobileSel[s.id] : !!_lead[s.id];
        if (s.id === state.focus) show = true;          // the focused line always stays drawn
        chartHidden[s.id] = !show;
      });
    }
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
    updateBasketSel();   // keep the "N on chart" counter honest as the facet narrows
    updateChartHint();
    updateSeriesCount();  // keep the mobile Series(n) trigger badge honest
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
    if (isBasketLike() && !anyShown) {
      hint.hidden = false;
      // basket-like families are selected by default; if some are still selected the empty
      // chart is the phase facet's doing (don't tell the user to tap one — that deselects it).
      var anySel = activeList().some(function (b) { return basketShown[b.id]; });
      hint.innerHTML = anySel
        ? L("No items match this phase — pick another phase or hit <b>All phases</b>.",
            "该阶段暂无条目——换一个阶段或点<b>全部阶段</b>。")
        : L("Nothing on the clock — tap an item or hit <b>Select all visible</b> to chart them.",
            "图中暂无条目——点击任一条目或点<b>全选可见</b>即可绘制。");
    } else { hint.hidden = true; }
  }
  /* ---- section family (Sector ETFs vs basket-like families) -------------- */
  function applyFamilyDisplay() {
    var chips = document.getElementById("sc-chips"), bask = document.getElementById("sc-baskets");
    if (chips) chips.style.display = state.family === "sectors" ? "" : "none";
    // basket-like families: re-mount the drawer for the active family's items, then show it.
    if (bask) {
      if (isBasketLike()) { mountBaskets(); bask.style.display = ""; bask.classList.remove("open"); }
      else { bask.style.display = "none"; bask.classList.remove("open"); }
    }
    document.querySelectorAll("#sc-tabs .sc-tab").forEach(function (t) { var on = t.getAttribute("data-fam") === state.family; t.classList.toggle("on", on); t.setAttribute("aria-selected", on ? "true" : "false"); });
    var ttl = document.getElementById("sc-hero-title");
    if (ttl) {
      if (state.family === "baskets") {
        ttl.innerHTML = '<span class="l-en">Thematic basket rotation</span><span class="l-zh">主题篮子轮动</span>';
      } else if (isBasketLike()) {
        var fmeta = (DATA.meta.families || []).filter(function (f) { return f.key === state.family; })[0];
        var lbl = fmeta ? fmeta.label : state.family;
        var lbl_zh = fmeta ? (fmeta.label_zh || lbl) : lbl;
        ttl.innerHTML = '<span class="l-en">' + lbl + ' rotation</span><span class="l-zh">' + lbl_zh + '轮动</span>';
      } else {
        ttl.innerHTML = '<span class="l-en">' + unitEC() + ' rotation overlay</span><span class="l-zh">' + unitZ() + '轮动叠加</span>';
      }
    }
  }
  function switchFamily(fam) {
    if (fam === state.family) return;
    state.family = fam; state.focus = null;
    mobileSel = null; mobileShowAll = false;   // each family opens on its own leaders default
    if (heroChart) heroChart.focus(null);
    // for basket-like families, initialise basketShown for the new active list — default-select
    // the top RS leaders so the chart opens on something sensible, not empty.
    if (isBasketLike()) {
      var ranked = activeList().slice().sort(function (a, b) { return (a.now.rs_rank || 999) - (b.now.rs_rank || 999); });
      // clear stale ids from all basket-like arrays (they share the same map)
      BASKETS.concat(NASDAQ, RUSSELL).forEach(function (b) { basketShown[b.id] = false; });
      ranked.slice(0, 6).forEach(function (b) { basketShown[b.id] = true; });
    }
    applyFamilyDisplay();
    mountCards();          // re-render the scorecards for the new family
    buildGroups();         // re-count phase chips + re-filter (calls applyVisibility)
    buildDefaultPanel();
    renderPanel(null);
    guideEntry();          // open the new family on one highlighted line, not a tangle
  }
  function wireFamily() {
    document.querySelectorAll("#sc-tabs .sc-tab").forEach(function (t) {
      t.addEventListener("click", function () { switchFamily(t.getAttribute("data-fam")); });
    });
    var ns = document.getElementById("sc-tab-n-sec"), nb = document.getElementById("sc-tab-n-bsk");
    var nn = document.getElementById("sc-tab-n-ndx"), nr = document.getElementById("sc-tab-n-rut");
    if (ns) ns.textContent = SECTORS.length;
    if (nb) nb.textContent = BASKETS.length;
    // hide Nasdaq/Russell tabs when the arrays are absent (e.g. China page)
    var tNdx = document.querySelector("#sc-tabs .sc-tab[data-fam='nasdaq']");
    var tRut = document.querySelector("#sc-tabs .sc-tab[data-fam='russell']");
    if (tNdx) { if (nn) nn.textContent = NASDAQ.length; tNdx.style.display = NASDAQ.length ? "" : "none"; }
    if (tRut) { if (nr) nr.textContent = RUSSELL.length; tRut.style.display = RUSSELL.length ? "" : "none"; }
  }

  /* ---- sector toggle chips ----------------------------------------------- */
  function mountChips() {
    var wrap = document.getElementById("sc-chips");
    if (!wrap) return;
    wrap.innerHTML = "";
    // a pinned "Select all visible" so every sector the facet shows can be re-lit in one tap.
    // (China mobile uses the upstream Series(n) picker for selection instead, so skip it there
    // to avoid two overlapping selection controls in one rail.)
    if (!isCnMobile()) {
      var all = el("button", "sc-chip-all");
      all.setAttribute("type", "button");
      all.setAttribute("title", L("Chart every " + unitE() + " the filter is showing", "绘制当前筛选下的全部" + unitZ()));
      all.innerHTML = '<span class="sca-ic" aria-hidden="true">✦</span>' + L("Select all visible", "全选可见");
      all.addEventListener("click", selectAllSectors);
      wrap.appendChild(all);
    }
    SECTORS.forEach(function (s) {
      var b = el("button", "cyc-chip");
      b.setAttribute("data-id", s.id);
      b.style.setProperty("--c", s.accent);
      b.innerHTML = '<span class="dot"></span><span class="nm">' + shortNm(s) + '</span>';
      b.addEventListener("click", function () { toggleFocus(s.id); });
      wrap.appendChild(b);
    });
    if (isCnMobile()) mountSeriesTrigger();   // mobile: a Series(n) picker replaces the chip rail
  }
  // "Select all visible" for the sector ETFs — sectors are always on the clock
  // (subject to the active "Where they stand" facet), so this just clears any focus
  // so every sector the facet is SHOWING reads at equal weight. It deliberately does
  // NOT widen the phase facet — that's the "All phases" button's job.
  function selectAllSectors() {
    // mobile (China): toggle the chart between the full visible overlay and the top-5
    // leaders. On desktop this stays a pure "re-light every visible sector" (it does NOT
    // widen the phase facet — that's the "All phases" button's job).
    if (isCnMobile()) { mobileShowAll = !mobileShowAll; mobileSel = null; }
    setFocus(null);
    syncGroups();
  }

  /* ---- thematic baskets: a collapsible, category-grouped rail; all baskets are
     selected by default — tapping one toggles it off, the "Where they stand" facet
     narrows the field, and "Select all visible" charts every basket the facet shows ---- */
  function basketChipHTML(b) {
    return '<button class="sc-bchip' + (basketShown[b.id] ? " on" : "") + '" data-id="' + b.id + '" style="--c:' + b.accent + '">' +
      '<span class="dot"></span><span class="nm">' + shortNm(b) + '</span>' +
      '<span class="sc-bdot" style="background:' + phaseHue(b.now.phase) + '" title="' + phaseLabel(b) + '"></span></button>';
  }
  function mountBaskets() {
    var host = document.getElementById("sc-baskets");
    if (!host) return;
    var list = activeList();
    if (!list.length) { host.style.display = "none"; return; }
    // pick a label/icon for the active basket-like family
    var fmeta = (DATA.meta.families || []).filter(function (f) { return f.key === state.family; })[0];
    var famLabel = state.family === "baskets"
      ? L("Thematic baskets", "主题篮子")
      : (fmeta ? L(fmeta.label, fmeta.label_zh || fmeta.label) : state.family);
    var famIcon = state.family === "baskets" ? "🧺" : state.family === "nasdaq" ? "💻" : "🔭";
    var byCat = {};
    list.forEach(function (b) { (byCat[b.group] = byCat[b.group] || []).push(b); });
    var cats = Object.keys(byCat).sort();
    host.innerHTML =
      '<div class="sc-bask-head" id="sc-bask-head">' +
        '<button class="sc-bask-toggle" id="sc-bask-toggle" type="button" aria-expanded="false">' +
          '<span class="sc-bask-ic" aria-hidden="true">' + famIcon + '</span><span class="sc-bask-title">' + famLabel + '</span>' +
          '<span class="sc-bask-n">' + list.length + '</span>' +
          '<span class="sc-bask-sel" id="sc-bask-sel"></span>' +
          '<span class="sc-bask-hint">' + L("tap to pick", "点选板块") + '</span>' +
          '<span class="sc-bask-caret" aria-hidden="true">▾</span>' +
        '</button>' +
        '<button class="sc-bask-all" id="sc-bask-all" type="button" title="' + L("Chart every item the filter is showing", "绘制当前筛选下的全部条目") + '">' +
          '<span class="sca-ic" aria-hidden="true">✦</span>' + L("Select all visible", "全选可见") + '</button>' +
      '</div>' +
      '<div class="sc-bask-panel" id="sc-bask-panel">' +
        cats.map(function (c) {
          return '<div class="sc-bask-cat"><div class="sc-bask-cath">' + grpName(byCat[c][0]) + '</div>' +
            '<div class="sc-bask-chips">' + byCat[c].map(basketChipHTML).join("") + '</div></div>';
        }).join("") +
      '</div>';
    document.getElementById("sc-bask-toggle").addEventListener("click", function () {
      var open = host.classList.toggle("open");
      this.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.getElementById("sc-bask-all").addEventListener("click", function (e) {
      e.stopPropagation(); selectAllBaskets();
    });
    host.querySelectorAll(".sc-bchip").forEach(function (ch) {
      ch.addEventListener("click", function () { toggleBasket(ch.getAttribute("data-id")); });
    });
    updateBasketSel();
  }
  // "Select all visible" for the thematic baskets — chart only the baskets the active
  // "Where they stand" facet is currently showing, and LEAVE the phase facet intact.
  // So when you've filtered to e.g. "Bottoming", this charts every bottoming basket at
  // once for a same-status cross-comparison — without dragging the other phases back in.
  function selectAllBaskets() {
    var allOff = PHASE_FILTER.every(function (p) { return !phaseState[p.key]; });
    activeList().forEach(function (b) { if (allOff || phaseState[b.now.phase]) basketShown[b.id] = true; });
    updateBasketSel();
    setFocus(null);
    syncGroups();
  }
  function updateBasketSel() {
    // honest counter: "N on chart" = selected items actually drawn (a "Where they
    // stand" facet can narrow the selected set; the focused item always counts).
    var allOff = PHASE_FILTER.every(function (p) { return !phaseState[p.key]; });
    var list = activeList();
    var sel = isBasketLike() ? list.filter(function (b) { return basketShown[b.id]; }) : [];
    var drawn = sel.filter(function (b) { return allOff || phaseState[b.now.phase] || b.id === state.focus; }).length;
    var el2 = document.getElementById("sc-bask-sel");
    if (el2) el2.textContent = !sel.length ? ""
      : (drawn < sel.length ? (drawn + " / " + sel.length + " " + L("on chart", "在图中"))
                            : (sel.length + " " + L("on chart", "在图中")));
    document.querySelectorAll(".sc-bchip").forEach(function (ch) {
      ch.classList.toggle("on", !!basketShown[ch.getAttribute("data-id")]);
    });
    // keep the scorecards' "on chart" state in sync with the chips for basket-like records
    document.querySelectorAll("#sc-cards .cyc-card").forEach(function (cd) {
      var id = cd.getAttribute("data-id"), it = byId[id];
      if (it && isBasketRec(it)) cd.classList.toggle("sel", !!basketShown[id]);
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
      crosshair: false, animate: !REDUCE, zoom: false,
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
      if (isBasketRec(s) && basketShown[s.id]) card.classList.add("sel");
      var rs = nw.rs_63d;
      var rsTxt = rs == null ? "" : ('<span class="cc-tilt ' + (rs >= 0 ? "t-up" : "t-down") + '">RS #' + (nw.rs_rank || "—") + '</span>');
      var nextTxt = s.proj ? (L("Next ", "下次") + (s.proj.nextTurn === "peak" ? "▲ " : "▼ ") + fmtMon(s.proj.central)) : L("—", "—");
      var sigHTML = nw.signal === "BUY" ? '<span class="cc-sig buy">' + L("BUY", "买入") + '</span>'
        : nw.signal === "SELL" ? '<span class="cc-sig sell">' + L("SELL", "卖出") + '</span>' : "";
      // W3.6: the resolved stance is the only action-toned text (D1 §2.2); the amber
      // "clocks disagree" chip replaces contradictory badge pairs when the clocks diverge.
      var stanceTag = stanceHTML(nw), divTag = divergenceHTML(nw);
      var pxLine = isBasketRec(s)
        ? ((s.etf_proxy ? s.etf_proxy + " · " : "") + grpName(s))
        : (s.ticker + " · " + grpName(s));
      card.innerHTML =
        '<div class="cc-top">' +
          '<div class="cc-id"><span class="cc-dot"></span><div><div class="cc-nm">' + nm(s) + '</div>' +
          '<div class="cc-px">' + pxLine + '</div></div></div>' +
          '<div class="cc-tags"><div class="cc-phase" style="--ph:' + phaseHue(nw.phase) + '">' + phaseLabel(s) + '</div>' + stanceTag + divTag + sigHTML + fxCardChip(s) + '</div>' +
        '</div>' +
        '<div class="cc-spark"></div>' +
        '<div class="cc-meta">' +
          '<div class="cc-leg"><div class="cc-leg-bar"><i style="width:' + Math.round(nw.pos) + '%"></i></div>' +
            '<div class="cc-leg-lab">' + L("Cycle position", "周期位置") + ' ' + Math.round(nw.pos) + '/100' + '</div></div>' +
          '<div class="cc-next"><span class="cc-arrow">' + (s.proj && s.proj.nextTurn === "peak" ? "▲" : "▼") + '</span>' +
            '<span>' + nextTxt + '</span>' +
            '<span class="cc-tilt ' + tilt.cls + '">' + tilt.ar + ' ' + L(tilt.lab[0], tilt.lab[1]) + '</span>' +
            rsTxt + '</div>' +
          hazardCardChip(s) +
        '</div>';
      card.addEventListener("click", function () { isBasketRec(s) ? toggleBasket(s.id) : toggleFocus(s.id); });
      grid.appendChild(card);
      var sp = card.querySelector(".cc-spark");
      sparks[s.id] = window.MMChart.create(sp, sparkSpec(s));
    });
  }

  /* ---- focus orchestration ----------------------------------------------- */
  function toggleFocus(id) { setFocus(state.focus === id ? null : id); }
  function setFocus(id) {
    clearFirstHint();                              // any focus change = the user has engaged
    // focusing a basket-like record implies selecting it onto the chart
    if (id && byId[id] && isBasketRec(byId[id]) && !basketShown[id]) {
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
    if (window.innerWidth <= 880) {
      if (isCnMobile()) { if (id) openSheet("half"); else closeSheet(); }   // hidden-at-rest detent sheet
      else if (id) expandSheet(true);                                       // US legacy peek sheet
    }
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
      keyActivate(row);
    });
    def.classList.remove("show"); foc.classList.add("show");
    _initDnaToggle(foc);
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

  /* ---- UI-HZ-1: calibrated turn-hazard surfaces --------------------------------
     Data path: s.now.hazard is stamped by engine/sector_cycles._stamp_hazard() —
     the SAME engine/hazard_score path build_cycle.py uses. We render the engine's
     own per-record stamp (family + direction already resolved per record) instead
     of re-joining the CPI live view here: no second entity mapping, no new lake
     reader in a page builder. Each cell carries its W4.2 gate verdict from the
     model ledger (cell_verdict), so every visible number gets an evidence badge:
     PASS = calibrated model probability (validated vs family-stratified KM);
     PRIOR = KM base rate, muted. No naked probabilities. Display-only context. */
  function _hzPass(c) { return !!c && c.p != null && (c.cell_verdict === "PASS" || c.source === "MODEL"); }
  function _hzTip(hz, key, pass) {
    var epoch = hz.epoch || "", dir = hz.direction || "";
    var revOpt = hz.revision_optimistic ? " · revision-optimistic (quad not PIT-vintaged)" : "";
    return pass
      ? ("Calibrated model probability — the " + dir + "/" + key + " cell PASSED the W4.2 gate " +
         "vs the family-stratified KM baseline (OOS Brier + month-block bootstrap CI + BH-FDR). " +
         "Epoch: " + epoch + revOpt + " · backtest-validated OOS; live cohort accruing")
      : ("KM base-rate prior — the " + dir + "/" + key + " cell did NOT pass the W4.2 gate; " +
         "this is the historical family-stratified base rate, not a validated model output. " +
         "Epoch: " + epoch + revOpt);
  }
  function _hzBadge(pass) {
    return pass ? '<span class="hz-badge hz-pass">' + L("PASS", "通过") + '</span>'
                : '<span class="hz-badge hz-prior">' + L("PRIOR", "先验") + '</span>';
  }
  // Full 1m/3m/6m row set for the detail sidebar (mirrors cycle.html's hazardLine).
  function hazardLineHTML(s) {
    var hz = s.now && s.now.hazard;
    if (!hz) return "";
    function cell(key, label, labelZh) {
      var c = hz[key];
      if (!c || c.p == null) return "";
      var pass = _hzPass(c);
      return '<span class="hz-cell' + (pass ? '' : ' hz-muted') + '" title="' + esc(_hzTip(hz, key, pass)) + '">' +
        L(label, labelZh) + ' ' + Math.round(c.p * 100) + '% ' + _hzBadge(pass) + '</span>';
    }
    var cells = [
      cell("1m", "P(turn ≤ 1m)", "P(转折≤1月)"),
      cell("3m", "≤3m", "≤3月"),
      cell("6m", "≤6m", "≤6月")
    ].filter(Boolean);
    if (!cells.length) return "";
    return '<div class="cyc-hazard sc-hazard">' +
      '<span class="hz-label" title="' + esc(L(
        "P(next confirmed turn within horizon) for the open " + (hz.direction || "?") + "-leg. " +
        "PASS cells: isotonic-calibrated hazard model (validated vs KM, W4.2 gate). " +
        "PRIOR cells: KM base rate, shown muted. Display-only context — never a signal.",
        "开放周期段在各时间窗内出现下一个已确认拐点的概率。PASS=经W4.2门槛校准的模型输出；PRIOR=KM基准率（弱化显示）。仅供展示，绝非信号。")) + '">' +
      L("Turn hazard (calibrated)", "转折风险（校准）") + '</span>' +
      cells.join('<span class="hz-sep"> · </span>') +
      '</div>';
  }
  // Compact card chip: the horizon/direction-appropriate probability. Prefer 3m when
  // its gate cell PASSED for this record's direction (down-legs: down/3m PASS); else
  // fall back to a passing 1m (up-legs: up/1m is the only PASS cell); else show the
  // 3m KM prior, PRIOR-badged and muted. The badge is never omitted.
  function _hzPick(hz) {
    if (_hzPass(hz["3m"])) return { key: "3m", c: hz["3m"], pass: true };
    if (_hzPass(hz["1m"])) return { key: "1m", c: hz["1m"], pass: true };
    if (hz["3m"] && hz["3m"].p != null) return { key: "3m", c: hz["3m"], pass: false };
    if (hz["1m"] && hz["1m"].p != null) return { key: "1m", c: hz["1m"], pass: false };
    return null;
  }
  function hazardCardChip(s) {
    var hz = s.now && s.now.hazard;
    if (!hz) return "";
    var pick = _hzPick(hz);
    if (!pick) return "";
    return '<div class="cc-hz' + (pick.pass ? '' : ' hz-muted') + '" title="' + esc(_hzTip(hz, pick.key, pick.pass)) + '">' +
      '<span class="cc-hz-k">' + L("Turn ≤" + pick.key, "转折≤" + (pick.key === "3m" ? "3月" : pick.key === "1m" ? "1月" : "6月")) + '</span> ' +
      '<b>' + Math.round(pick.c.p * 100) + '%</b> ' + _hzBadge(pick.pass) +
      '</div>';
  }

  // prominent projected next-turn card (the user-requested "best-guess point", honestly framed).
  // Gated on META.forecastPoint (China); without the flag (US) it renders the original compact
  // regnote unchanged, so the US page is byte-identical to before.
  function forecastCardHTML(s) {
    var p = s.proj; if (!p || !p.central) return "";
    if (!META.forecastPoint) {
      return '<div class="cyc-regnote">' + L("Projected next " + p.nextTurn + " ≈ " + fmtMon(p.central) + " (" + fmtMon(p.low) + "–" + fmtMon(p.high) + "), from this " + unitE() + "’s own median half-cycle. A timing estimate, not a guarantee.",
        "预计下次" + (p.nextTurn === "peak" ? "顶部" : "底部") + "约在 " + fmtMon(p.central) + "（" + fmtMon(p.low) + "–" + fmtMon(p.high) + "），基于该" + unitZ() + "自身的中位半周期。仅为时间估计。") + '</div>';
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
  // evidence-gated conditional forward odds (the 4 GS sectors only) — display-only
  // conditioning, never a buy signal. Rendered only when the record carries a `pathway` block.
  // W2.6: the CI is a DATE-BLOCKED bootstrap on the (conditional − base) lift; we report
  // n_months + n_eff (never the raw overlapping n) and disclose the fixed constituent set +
  // the month the composite becomes defined (era-stabilization, audit china-sector-cycles-1/2).
  function pathwayHTML(s) {
    var pw = s.pathway; if (!pw) return "";
    var cond = pw.conditional || {}, h = cond.h6 || cond.h3 || null, setup = pw.setup || {};
    var comp = pw.composition || {}, legs = setup.legs || [];
    var odds = "";
    if (h) {
      var pr = Math.round(h.cond_rate * 100), base = Math.round(h.base_rate * 100), hz = h.h || 6;
      // lift band from the block-bootstrap gap CI (in percentage points), honestly labeled.
      var loPP = (h.lift_ci_lo != null) ? Math.round(h.lift_ci_lo * 100) : null;
      var hiPP = (h.lift_ci_hi != null) ? Math.round(h.lift_ci_hi * 100) : null;
      var excl = (loPP != null && (loPP > 0 || hiPP < 0));
      var ci = (loPP != null) ? (loPP + "–" + hiPP + "pp") : L("n/a", "无");
      var liftCls = h.lift > 0.03 ? "t-up" : h.lift < -0.03 ? "t-down" : "t-mix";
      var nStr = "n=" + h.n_months + "mo" + (h.n_eff != null ? " (n_eff≈" + h.n_eff + ")" : "");
      var ciTag = (loPP != null)
        ? (L("lift ", "超额 ") + ci + (excl ? "" : L(" · CI ⊃ base", " · 含基准")))
        : "";
      odds = '<div class="sc-pw-odds"><div class="sc-pw-big ' + liftCls + '">' + pr + '%</div>' +
        '<div class="sc-pw-meta"><div class="sc-pw-line">' + L("forward-" + hz + "m positive", "未来" + hz + "个月上涨") + '</div>' +
        '<div class="sc-pw-sub">' + L("vs ", "基准 ") + base + L("% base", "%") + ' · ' + ciTag + ' · ' + nStr + '</div></div></div>';
    }
    // era-disclosure chip: which legs the composite averages + when it becomes defined.
    var compLine = comp.version
      ? '<div class="sc-pw-comp" title="' + L("fixed constituent set · block-bootstrap CI", "固定因子集合 · 分块自助置信区间") + '">' +
          L("composite: ", "复合口径：") + (comp.n_required_legs || (comp.required_legs || []).length) + L(" legs", " 项因子") +
          (comp.active_legs_now != null ? " (" + comp.active_legs_now + L(" live", " 齐备") + ")" : "") +
          (comp.first_all_legs_live ? " · " + L("from ", "起自 ") + comp.first_all_legs_live : "") +
        '</div>'
      : "";
    var legChips = legs.slice(0, 4).map(function (lg) {
      var cls = lg.stance === "bullish" ? "pw-bull" : lg.stance === "bearish" ? "pw-bear" : "pw-neu";
      return '<span class="sc-pw-leg ' + cls + '">' + L(lg.label_en, lg.label_zh) + '</span>';
    }).join("");
    return '<div class="cyc-grp cyc-grp-3 sc-pathway">' +
      '<div class="cyc-lbl">' + L("Evidence-gated forward odds", "经证据门槛的前瞻概率") +
        ' <span class="sc-pw-badge" title="' + L("conditional · display-only", "条件化 · 仅展示") + '">⚗︎</span></div>' +
      odds + compLine +
      (legChips ? '<div class="sc-pw-legs"><span class="sc-pw-legk">' + L("Lead cluster now", "当前领先因子") + '</span>' + legChips + '</div>' : "") +
      (_pwNarr(pw) ? '<p class="sc-pw-narr">' + _pwNarr(pw) + '</p>' : "") +
      (_pwCaveat(pw) ? '<p class="sc-pw-caveat">' + _pwCaveat(pw) + '</p>' : "") +
    '</div>';
  }

  // each US sector ETF has a dedicated equal-weight sector page under basket/; map by the
  // stable SECTOR_CYCLES `id` so the "open page" button lands on that page rather than the
  // ETF's single-stock analyzer (stock.html#TICKER).
  var US_SECTOR_PAGE = {
    xlk: "basket/us_sector_tech.html",
    xlc: "basket/us_sector_comm.html",
    xly: "basket/us_sector_discretionary.html",
    xlf: "basket/us_sector_financials.html",
    xli: "basket/us_sector_industrials.html",
    xlb: "basket/us_sector_materials.html",
    xle: "basket/us_sector_energy.html",
    xlv: "basket/us_sector_health.html",
    xlp: "basket/us_sector_staples.html",
    xlu: "basket/us_sector_utilities.html",
    xlre: "basket/us_sector_realestate.html"
  };

  // the "open this item's own page" target. US: each sector ETF opens its dedicated equal-weight
  // sector page (US_SECTOR_PAGE), and each thematic basket opens its dedicated theme page at
  // basket/<id>.html (the "b-" id prefix stripped) — NOT the proxy ETF's single-stock analyzer.
  // China (Shenwan indices / A-share baskets have no analyzer) routes to the China Sector Central
  // hub. Returns null when there's nothing to open (incl. when already embedded in that hub).
  function sectorPageHref(s) {
    if (META.region === "intl") return null;   // country/region ETFs have no dedicated drill page — the cycle card IS the page
    if (META.region === "china") {
      // when this same JS is embedded IN the China Sector Central hub, don't render a
      // button that merely reloads the page you're already on; from the standalone
      // cycles page, deep-link into the hub and let its boot() focus this item by #id.
      return /sector_central/.test(location.pathname) ? null : ("sector_central_china.html#" + s.id);
    }
    if (s.kind === "basket") return "basket/" + s.id.replace(/^b-/, "") + ".html";
    if (s.kind === "nasdaq" || s.kind === "russell") return null;   // no dedicated page for index sub-series
    if (US_SECTOR_PAGE[s.id]) return US_SECTOR_PAGE[s.id];
    return s.ticker ? ("stock.html#" + s.ticker) : null;
  }
  function sectorPageLabel(s) {
    if (META.region === "china") return L("Open in Sector Central", "在板块中枢查看");
    // both thematic baskets and US sector ETFs label by their own name → "Open <name> page".
    if (isBasketRec(s) || US_SECTOR_PAGE[s.id]) return L("Open ", "查看 ") + nm(s) + L(" page", " 页面");
    return L("Open ", "查看 ") + (s.ticker || "") + L(" page", " 页面");
  }

  // ---- Cycle DNA: the front-loaded "history rhymes" layer (window.SECTOR_DNA, keyed by id).
  // What STRUCTURALLY drives this series to cycle, what marks its tops vs troughs, and which
  // past leg today most rhymes with — researched against the 15y dated turns. Hidden if absent.
  function dnaHTML(s) {
    var DNA = window.SECTOR_DNA || {};
    var d = DNA[s.id]; if (!d) return "";
    var sum = curLang() === "zh" ? (d.summary_zh || d.summary) : d.summary;
    var drv = (curLang() === "zh" && d.drivers_zh) ? d.drivers_zh : (d.drivers || []);
    var tops = (curLang() === "zh" && d.top_signals_zh) ? d.top_signals_zh : (d.top_signals || []);
    var bots = (curLang() === "zh" && d.bottom_signals_zh) ? d.bottom_signals_zh : (d.bottom_signals || []);
    var analog = curLang() === "zh" ? (d.analog_zh || d.analog) : d.analog;
    var cyc = d.median_cycle_months ? Math.round(d.median_cycle_months) : null;
    var conf = d.confidence ? '<span class="sc-dna-conf ' + d.confidence + '">' + L("confidence ", "可信度 ") +
      L(d.confidence, d.confidence === "high" ? "高" : d.confidence === "medium" ? "中" : "低") + '</span>' : "";
    function ul(items) { return '<ul>' + items.map(function (x) { return '<li>' + x + '</li>'; }).join("") + '</ul>'; }
    return '<div class="cyc-grp cyc-grp-3 sc-dna">' +
      '<div class="cyc-lbl">' + L("Cycle DNA — why it rhymes", "周期基因 — 历史为何押韵") + conf + '</div>' +
      '<div class="sc-dna-body">' +
      (sum ? '<p class="sc-dna-sum">' + sum + '</p>' : "") +
      (drv.length ? '<div class="sc-dna-drv">' + drv.map(function (x) { return '<span>' + x + '</span>'; }).join("") + '</div>' : "") +
      ((bots.length || tops.length) ? '<div class="sc-dna-sig">' +
        (bots.length ? '<div class="sc-dna-col b"><div class="sc-dna-h">' + L("Troughs form when", "底部形成于") + '</div>' + ul(bots) + '</div>' : "") +
        (tops.length ? '<div class="sc-dna-col t"><div class="sc-dna-h">' + L("Peaks form when", "顶部形成于") + '</div>' + ul(tops) + '</div>' : "") +
      '</div>' : "") +
      (cyc ? '<div class="sc-dna-rhythm">' + L("Median full cycle ≈ ", "中位完整周期约 ") + cyc + L(" months", " 个月") + '</div>' : "") +
      (analog ? '<div class="sc-dna-analog"><span class="sc-dna-ana-k">' + L("Closest analog", "最相似的历史") + '</span> ' + analog + '</div>' : "") +
      '</div>' +
      '<button type="button" class="sc-dna-more"><span class="l-en">See more ▾</span><span class="l-zh">展开更多 ▾</span></button>' +
    '</div>';
  }

  // Wire up the sc-dna-body clamp + See more/less toggle after injection.
  // Called from renderPanel() after foc.innerHTML is set.
  // Delegates on container so it's payload-agnostic (works for all DNA sections).
  function _initDnaToggle(container) {
    container.querySelectorAll(".sc-dna-more").forEach(function (btn) {
      var body = btn.previousElementSibling;
      if (!body || !body.classList.contains("sc-dna-body")) return;
      if (body.scrollHeight <= body.clientHeight + 8) { btn.hidden = true; body.classList.add("open"); return; }
      btn.hidden = false;
      btn.addEventListener("click", function () {
        var open = body.classList.toggle("open");
        var enMore = btn.querySelector(".l-en"), zhMore = btn.querySelector(".l-zh");
        if (enMore) enMore.textContent = open ? "See less ▴" : "See more ▾";
        if (zhMore) zhMore.textContent = open ? "收起 ▴" : "展开更多 ▾";
      });
    });
  }

  // W3.4: Build the "Analyst note" block with TTL staleness badge, archetype check
  // failure chip, and revision provenance note.
  // ttlMeta = NARR[sid]._ttl or null (enriched by build scripts via _narrative_ttl.py).
  function _buildAnalystNoteHTML(analystNote, ttlMeta) {
    if (!analystNote) return "";
    var badgeHTML = "";
    var archHTML = "";
    var revHTML = "";

    if (ttlMeta) {
      var days = ttlMeta.staleness_days;
      var asOf = ttlMeta.as_of;

      // ── staleness badge ──────────────────────────────────────────────────────
      if (asOf && days != null) {
        var badgeCls = ttlMeta.stale_red ? "sc-narr-badge sc-narr-badge-red"
          : ttlMeta.stale_amber ? "sc-narr-badge sc-narr-badge-amber"
          : "sc-narr-badge";
        var ageStr = L("curated " + days + "d ago", "整理于 " + days + " 天前");
        // dual-span for i18n: en span + zh span
        badgeHTML = '<span class="' + badgeCls + '">' +
          '<span class="l-en">' + "curated " + days + "d ago" + '</span>' +
          '<span class="l-zh">' + "整理于 " + days + " 天前" + '</span>' +
          '</span>';
      }

      // ── archetype mechanism check failure ────────────────────────────────────
      var archState = ttlMeta.arch_state;
      if (archState === "fail" && ttlMeta.arch_fired_on) {
        archHTML = '<div class="sc-narr-arch-fail">' +
          '<span class="l-en">mechanism check failing since ' + ttlMeta.arch_fired_on + '</span>' +
          '<span class="l-zh">机制检验失效自 ' + ttlMeta.arch_fired_on + '</span>' +
          '</div>';
      } else if (archState === "manual") {
        archHTML = '<div class="sc-narr-arch-manual">' +
          '<span class="l-en">mechanism check: manual review required</span>' +
          '<span class="l-zh">机制检验：需人工审核</span>' +
          '</div>';
      }

      // ── revision provenance ──────────────────────────────────────────────────
      if (ttlMeta.revision_note) {
        revHTML = '<div class="sc-narr-revision">' + ttlMeta.revision_note + '</div>';
      }
    }

    return '<div class="cyc-analyst-note">' +
      '<div class="cyc-lbl cyc-lbl-note">' +
        L("Analyst note", "分析师注释") +
        (badgeHTML ? " " + badgeHTML : "") +
      '</div>' +
      archHTML +
      revHTML +
      '<p class="sc-analyst-note-text">' + analystNote + '</p>' +
    '</div>';
  }

  function focusHTML(s) {
    var nw = s.now, ph = PHASES[nw.phase] || {}, tilt = tiltOf(s);
    function fact(k, v) { return '<div class="f"><div class="fk">' + k + '</div><div class="fv">' + v + '</div></div>'; }
    var posLab = Math.round(nw.pos) + "/100 · " + zoneWord(nw.pos);
    var lenVal = s.proj && s.proj.period_yrs ? (s.proj.period_yrs.median + L(" yr", " 年")) : "—";
    var rsVal = nw.rs_63d == null ? "—" : ((nw.rs_63d >= 0 ? "+" : "") + nw.rs_63d + "% · #" + (nw.rs_rank || "—"));
    var isB = isBasketRec(s), noun = isB ? "Basket" : "Sector", nounZh = isB ? "篮子" : "板块";
    // W0.3: engine-owned read is primary (doctrine: engine owns every plotted number).
    // nw.read / nw.read_zh are generated by _set_engine_read() in sector_cycles.py.
    // The hand-authored NARR[s.id].now string is demoted to a dated "Analyst note" below.
    // W3.4: NARR entries now carry _ttl metadata (as_of, staleness, archetype_check, revision).
    var engineRead = curLang() === "zh" ? (nw.read_zh || nw.read) : nw.read;
    var analystNote = nz(NARR[s.id], "now");  // still displayed, but as a labeled annotation
    var _ttl = (NARR[s.id] || {})._ttl || null;
    var analystNoteHTML = _buildAnalystNoteHTML(analystNote, _ttl);
    var readHTML = (engineRead
      ? ('<div class="cyc-read"><div class="cyc-lbl">' + L("The read", "解读") + '</div><p>' + engineRead + '</p>' +
         analystNoteHTML +
         '</div>')
      : ('<div class="cyc-read"><div class="cyc-lbl">' + L("The read", "解读") + '</div><p class="sc-leg-pending">' +
         L("This " + noun.toLowerCase() + " is " + phaseLabel(s).toLowerCase() + " — cycle position " + Math.round(nw.pos) + "/100, " +
           (nw.above200d ? "above" : "below") + " its 200-day. Engine read generating.",
           "该" + nounZh + phaseLabel(s) + " — 周期位置 " + Math.round(nw.pos) + "/100，" + (nw.above200d ? "位于" : "低于") + "200日均线。引擎解读生成中。") + '</p>' +
         analystNoteHTML +
         '</div>'));
    var subtitle = isB
      ? (L("Basket", "篮子") + (s.n_members ? " · " + s.n_members + " " + L("names", "只成分") : "") + (s.etf_proxy ? " · " + L("proxy ", "对标 ") + s.etf_proxy : ""))
      : (s.ticker + " · " + grpName(s));

    var pageHref = sectorPageHref(s);
    var openBtn = pageHref ? ('<a class="sc-openpage" href="' + pageHref + '" style="--c:' + s.accent + '">' +
        '<span class="sc-op-ic" aria-hidden="true">📄</span><span class="sc-op-tx">' + sectorPageLabel(s) + '</span>' +
        '<span class="sc-op-ar" aria-hidden="true">↗</span></a>') : '';
    return '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<div class="sc-fhead-top">' +
          '<button class="cyc-back">' + (isBasketRec(s) ? L("← All baskets", "← 全部篮子") : L("← All " + unitE() + "s", "← 全部" + unitZ())) + '</button>' +
          openBtn +
        '</div>' +
        '<div class="cyc-fhead" style="--c:' + s.accent + '">' +
          '<div class="cyc-ftitle">' + nm(s) + '</div>' +
          '<div class="cyc-fsub">' + subtitle + (nw.above200d ? L(" · above 200d", " · 200日上") : L(" · below 200d", " · 200日下")) + '</div>' +
          '<div class="cyc-fchips">' +
            '<span class="cyc-pchip" style="--ph:' + (ph.hue || "var(--muted)") + '">' + phaseLabel(s) + '</span>' +
            stanceHTML(nw) +
            '<span class="cyc-tchip ' + tilt.cls + '">' + tilt.ar + ' ' + L(tilt.lab[0], tilt.lab[1]) + '</span>' +
            usdViewChip(s) +
          '</div>' +
          divergenceHTML(nw, { full: true }) +
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
          fact(L(WIN_Y + "y change", WIN_Y + "年涨跌"), (nw.ret_win_pct >= 0 ? "+" : "") + nw.ret_win_pct + "%") +
        '</div>' +
        hazardLineHTML(s) +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        readHTML +
        forecastCardHTML(s) +
      '</div>' +
      dnaHTML(s) +
      fxDrawerHTML(s) +
      pathwayHTML(s) +
      // full-width: the legs list is the panel footer. As a 1/3 grid cell it stranded itself
      // bottom-left with dead whitespace whenever the optional fx/pathway drawers were absent.
      '<div class="cyc-grp cyc-grp-full">' +
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
      // W3.9: a currency glyph on the leg whose END turn was >60% currency-driven — so a
      // yen-crash "trough" never reads as a Japanese-equity trough without the disclosure.
      var fxBadge = (hasFx(s) && g.end && g.end.fx_flag)
        ? ('<span class="sc-leg-fx" title="' +
            esc(L("currency drove " + Math.round((g.end.fx_share || 0) * 100) + "% of this USD move",
                  "货币占此美元波动的 " + Math.round((g.end.fx_share || 0) * 100) + "%")) + '">' + CUR_GLYPH + '</span>')
        : "";
      return '<div class="sc-leg" role="button" tabindex="0" data-i="' + g.i + '" style="--c:' + s.accent + ';--lc:' + lc + '">' +
        '<span class="sc-leg-k ' + g.dir + '">' + verb + fxBadge + '</span>' +
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
    var baskets = isBasketLike();
    var noun = baskets ? L("baskets", "篮子") : L(unitE() + "s", unitZ());
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
        '<span class="sc-lead-nm" role="button" tabindex="0" data-id="' + s.id + '" style="--c:' + s.accent + '"><span class="dot"></span>' + nm(s) + '</span>' +
        '<span class="sc-lead-rs ' + (rs >= 0 ? "pos" : "neg") + '">' + (rs >= 0 ? "+" : "") + rs + '%</span></div>';
    }).join("") + (lead.length > leadCap ? '<div class="sc-lead-more">+ ' + (lead.length - leadCap) + ' ' + L("more", "更多") + '</div>' : "");

    def.innerHTML = '' +
      '<div class="cyc-grp cyc-grp-full">' +
        '<div class="cyc-lbl">' + (baskets ? L("Thematic basket rotation · ", "主题篮子轮动 · ") : L(unitEC() + " rotation · ", unitZ() + "轮动 · ")) + META.asOf + '</div>' +
        '<p class="rg-headline">' + (baskets
          ? L("The <b>strongest items</b> are charted to start — each an equal-weight index of its members on a 0–100 <b>cycle-position</b> clock. Tap an item to add it, use <b>Where they stand</b> to narrow, or hit <b>Select all visible</b> for the whole field of " + activeList().length + ". Flip to <b>Price</b> for the real tape (rebased, log).",
              "已先绘制<b>最强的几个条目</b>——每个均为其成分股的等权指数，置于 0–100 <b>周期位置</b>时钟上。点击条目可加入，用<b>所处阶段</b>缩小范围，或点<b>全选可见</b>查看全部 " + activeList().length + " 个。切换到<b>价格</b>可查看真实走势（再基准化、对数）。")
          : L("Every " + unitE() + " on a 0–100 <b>cycle-position</b> clock — high = stretched/late, low = washed-out. Flip to <b>Price</b> for the real tape (rebased on a log axis, so every line shares an axis). Tap a " + unitE() + " to see its turning points and the story behind each move.",
              "每个" + unitZ() + "同处 0–100 <b>周期位置</b>时钟——高=拉伸/晚期，低=超卖。切换到<b>价格</b>可查看真实走势（对数坐标下再基准化，使每条线共用同一坐标轴）。点按某" + unitZ() + "查看其拐点及每段走势背后的故事。")) + '</p>' +
      '</div>' +
      '<div class="cyc-grp cyc-grp-3">' +
        '<div class="cyc-lbl">' + L("Where the ", "各") + noun + L(" stand", "所处位置") + '</div>' +
        '<div class="xc-map">' +
          row(L("Topping · late", "见顶 · 晚期"), buckets.Peak, L("thin cushion", "缓冲薄弱")) +
          row(L("Trending", "上行中"), buckets.Expansion, L("healthy up-trend", "健康上行")) +
          row(L("Rolling over", "回落中"), buckets.Downturn, L("declining", "下行中")) +
          row(L("Prime entry", "入场良机"), buckets.Recovery, L("bottomed · turning up", "已筑底 · 转强"),
              L("No " + (baskets ? "baskets" : (unitE() + "s")) + " are at prime entry right now.",
                "目前没有处于入场良机的" + (baskets ? "篮子" : unitZ()) + "。")) +
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
          '<li>' + L("▲ peaks and ▼ troughs are auto-detected major turns; the <b>● dot</b> is where the " + unitE() + " is now.", "▲ 波峰与 ▼ 波谷为自动识别的重大拐点；<b>● 圆点</b>是该" + unitZ() + "当前位置。") + '</li>' +
          '<li>' + L("<b>Tap a " + unitE() + "</b> (chip, card, or line), then tap a <b>leg</b> to read what drove that move.", "<b>点按某" + unitZ() + "</b>（标签、卡片或曲线），再点按某<b>区段</b>了解推动该走势的原因。") + '</li>' +
        '</ul>' +
      '</div>';

    def.querySelectorAll(".mini-chip, .sc-lead-nm").forEach(function (b) {
      b.addEventListener("click", function () { setFocus(b.getAttribute("data-id")); });
      if (b.classList.contains("sc-lead-nm")) keyActivate(b);   // mini-chip is a native <button>
    });
    def.classList.add("show");
  }

  /* ---- mobile bottom sheet ----------------------------------------------- */
  // US / desktop keep the original peek-and-expand underbar (untouched). China mobile
  // gets a true hidden-at-rest, multi-detent sheet (hidden → half → full) with 1:1
  // finger-follow drag, rubber-band, velocity flick, a scrim on the modal detent and a
  // visible ✕ — so the detail never permanently covers the scorecards.
  function expandSheet(on) { var s = document.getElementById("sc-detail"); if (s) s.classList.toggle("expanded", on !== false); }

  var sheetDetent = "hidden";
  function _scrim() {
    var s = document.getElementById("sc-scrim");
    if (!s) {
      s = el("div", "sc-scrim"); s.id = "sc-scrim";
      s.addEventListener("click", function () { setFocus(null); });
      document.body.appendChild(s);
    }
    return s;
  }
  function setDetent(d) {
    var sheet = document.getElementById("sc-detail"); if (!sheet) return;
    sheetDetent = d;
    sheet.classList.toggle("sc-sheet-half", d === "half");
    sheet.classList.toggle("sc-sheet-full", d === "full");
    var modal = d === "full", scrim = _scrim();
    scrim.style.opacity = modal ? "1" : "0";
    scrim.style.pointerEvents = modal ? "auto" : "none";
    document.body.style.overflow = modal ? "hidden" : "";   // lock the page only behind the modal detent
  }
  function openSheet(d) { setDetent(d || "half"); }
  function closeSheet() { setDetent("hidden"); }
  function detentPx() { var ih = window.innerHeight; return { full: 0, half: ih * 0.46, hidden: ih * 0.92 }; }

  function initSheet() {
    var sheet = document.getElementById("sc-detail"), handle = document.getElementById("sc-handle");
    if (!sheet || !handle) return;
    if (!IS_CN) {   // US / standalone Cycle page: original simple expand toggle, verbatim
      handle.addEventListener("click", function () { sheet.classList.toggle("expanded"); });
      var sY = 0, drag0 = false;
      handle.addEventListener("touchstart", function (e) { sY = e.touches[0].clientY; drag0 = true; }, { passive: true });
      handle.addEventListener("touchmove", function (e) {
        if (!drag0) return; var dy = e.touches[0].clientY - sY;
        if (dy < -30) sheet.classList.add("expanded"); else if (dy > 40) sheet.classList.remove("expanded");
      }, { passive: true });
      handle.addEventListener("touchend", function () { drag0 = false; });
      return;
    }
    // China: inject a visible ✕ close — the grabber alone is easy to miss (NN/g).
    if (!handle.querySelector(".sc-sheet-x")) {
      var x = el("button", "sc-sheet-x"); x.type = "button";
      x.setAttribute("aria-label", "Close"); x.innerHTML = "✕";
      x.addEventListener("click", function (e) { e.stopPropagation(); setFocus(null); });
      handle.appendChild(x);
    }
    // tap the grabber → toggle half / full
    handle.addEventListener("click", function (e) {
      if (e.target.closest(".sc-sheet-x")) return;
      setDetent(sheetDetent === "full" ? "half" : "full");
    });
    // 1:1 finger-follow drag with rubber-band past the bounds + velocity flick
    var startY = 0, baseTY = 0, lastY = 0, lastT = 0, prevY = 0, prevT = 0, dragging = false;
    function rubber(v, min, max) {
      var d = window.innerHeight;
      if (v < min) { var o = min - v; return min - (1 - 1 / ((o * 0.55 / d) + 1)) * d; }
      if (v > max) { var o2 = v - max; return max + (1 - 1 / ((o2 * 0.55 / d) + 1)) * d; }
      return v;
    }
    handle.addEventListener("touchstart", function (e) {
      dragging = true; startY = e.touches[0].clientY; baseTY = detentPx()[sheetDetent];
      prevY = lastY = startY; prevT = lastT = e.timeStamp;
      sheet.classList.add("sc-dragging");
    }, { passive: true });
    handle.addEventListener("touchmove", function (e) {
      if (!dragging) return;
      var y = e.touches[0].clientY, det = detentPx();
      sheet.style.transform = "translateY(" + rubber(baseTY + (y - startY), det.full, det.hidden) + "px)";
      prevY = lastY; prevT = lastT; lastY = y; lastT = e.timeStamp;
    }, { passive: true });
    handle.addEventListener("touchend", function () {
      if (!dragging) return; dragging = false;
      var det = detentPx(), pos = baseTY + (lastY - startY);
      var dt = lastT - prevT, vel = dt > 0 ? (lastY - prevY) / dt : 0;   // px/ms, +down
      var order = ["full", "half", "hidden"], target;
      if (Math.abs(vel) > 0.5) {                       // flick → one detent in the flick direction
        var ci = order.indexOf(sheetDetent); target = order[clamp(ci + (vel > 0 ? 1 : -1), 0, 2)];
      } else {                                         // settle → nearest detent by position
        var bd = Infinity; order.forEach(function (k) { var dd = Math.abs(det[k] - pos); if (dd < bd) { bd = dd; target = k; } });
      }
      sheet.classList.remove("sc-dragging");
      sheet.style.transform = "";                      // hand back to the CSS class transform (animates the settle)
      if (target === "hidden") setFocus(null); else setDetent(target);
    });
    // Esc closes the sheet
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && sheetDetent !== "hidden") setFocus(null);
    });
  }

  /* ---- mobile chrome: collapse the EXPERIMENTAL provenance into an accordion ---- */
  function initMobileChrome() {
    if (!isCnMobile()) return;   // desktop (US + China) keeps the full inline banner
    var prov = document.querySelector(".sc-provenance");
    if (!prov || prov.classList.contains("sc-prov-collapsible")) return;
    var chip = prov.querySelector(".sc-prov-chip"), txt = prov.querySelector(".sc-prov-text");
    if (!chip || !txt) return;
    var head = el("div", "sc-prov-head"), caret = el("span", "sc-prov-caret", "▾");
    caret.setAttribute("aria-hidden", "true");
    prov.insertBefore(head, chip);
    head.appendChild(chip); head.appendChild(caret);
    prov.classList.add("sc-prov-collapsible");
    prov.setAttribute("role", "button");
    prov.setAttribute("aria-expanded", "false");
    head.addEventListener("click", function () {
      var open = prov.classList.toggle("sc-prov-open");
      prov.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* ---- Series picker (China mobile): a searchable, phase-grouped multi-select sheet that
     curates exactly which sectors are drawn — replaces the 31-chip horizontal rail. It writes
     the same mobileSel map the focus-default / Show-all path already reads in applyVisibility. */
  function ensureMobileSel() {
    if (mobileSel) return;                         // seed from the current conceptual selection
    var base = mobileShowAll ? null : mobileLeaders();
    mobileSel = {};
    activeList().forEach(function (s) { mobileSel[s.id] = mobileShowAll ? true : !!(base && base[s.id]); });
    mobileShowAll = false;                          // explicit curation supersedes the all/leaders toggle
  }
  function mountSeriesTrigger() {
    var wrap = document.getElementById("sc-chips");
    if (!wrap || wrap.querySelector(".sc-series-btn")) return;
    var btn = el("button", "sc-series-btn"); btn.type = "button";
    btn.setAttribute("aria-haspopup", "dialog");
    btn.innerHTML = '<span aria-hidden="true">☰</span><span class="l-en">Series</span><span class="l-zh">' + unitZ() + '</span>' +
      '<span class="sc-series-n" id="sc-series-n"></span><span class="sc-series-car" aria-hidden="true">▾</span>';
    btn.addEventListener("click", openSeriesPicker);
    var allBtn = wrap.querySelector(".sc-chip-all");
    if (allBtn && allBtn.nextSibling) wrap.insertBefore(btn, allBtn.nextSibling); else wrap.appendChild(btn);
    updateSeriesCount();
  }
  function updateSeriesCount() {
    var n = document.getElementById("sc-series-n");
    if (n) n.textContent = mobileShownCount();
  }
  function buildSeriesOverlay() {
    var ov = document.getElementById("sc-series-ov");
    if (ov) return ov;
    ov = el("div", "sc-series-ov"); ov.id = "sc-series-ov";
    ov.innerHTML =
      '<div class="sc-series-back"></div>' +
      '<div class="sc-series-panel" role="dialog" aria-modal="true" aria-label="' + L("Choose " + unitE() + "s", "选择" + unitZ()) + '">' +
        '<div class="sc-series-hd"><span class="sc-series-ttl">' + L("Choose " + unitE() + "s", "选择" + unitZ()) + '</span>' +
          '<button class="sc-series-done" type="button">' + L("Done", "完成") + '</button></div>' +
        '<div class="sc-series-tools">' +
          '<input class="sc-series-search" type="search" placeholder="' + L("Search…", "搜索…") + '" aria-label="' + L("Search " + unitE() + "s", "搜索" + unitZ()) + '">' +
          '<button class="sc-series-act" data-act="all" type="button">' + L("All", "全选") + '</button>' +
          '<button class="sc-series-act" data-act="none" type="button">' + L("Clear", "清空") + '</button>' +
        '</div>' +
        '<div class="sc-series-list" id="sc-series-list"></div>' +
      '</div>';
    document.body.appendChild(ov);
    ov.querySelector(".sc-series-back").addEventListener("click", closeSeriesPicker);
    ov.querySelector(".sc-series-done").addEventListener("click", closeSeriesPicker);
    ov.querySelector(".sc-series-search").addEventListener("input", function () { filterSeriesList(this.value); });
    ov.querySelectorAll(".sc-series-act").forEach(function (b) {
      b.addEventListener("click", function () { seriesSelectAll(b.getAttribute("data-act") === "all"); });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && ov.classList.contains("open")) closeSeriesPicker();
    });
    return ov;
  }
  function renderSeriesList() {
    var host = document.getElementById("sc-series-list");
    if (!host) return;
    ensureMobileSel();
    var groups = {};
    activeList().forEach(function (s) { (groups[s.now.phase] = groups[s.now.phase] || []).push(s); });
    var order = ["Trough", "Recovery", "Expansion", "Peak", "Downturn"], html = "";
    order.forEach(function (ph) {
      var list = (groups[ph] || []).slice().sort(function (a, b) { return (a.now.rs_rank || 99) - (b.now.rs_rank || 99); });
      if (!list.length) return;
      html += '<div class="sc-series-grp">' + (PHASE_LAB[ph] ? L(PHASE_LAB[ph][0], PHASE_LAB[ph][1]) : ph) + '</div>';
      list.forEach(function (s) {
        html += '<button class="sc-series-row' + (mobileSel[s.id] ? " on" : "") + '" data-id="' + s.id + '" type="button" style="--c:' + s.accent + '">' +
          '<span class="sc-ck" aria-hidden="true">✓</span><span class="sc-sdot"></span>' +
          '<span class="sc-nm">' + nm(s) + '</span>' +
          (s.now.rs_rank ? '<span class="sc-rs">#' + s.now.rs_rank + '</span>' : '') + '</button>';
      });
    });
    host.innerHTML = html;
    host.querySelectorAll(".sc-series-row").forEach(function (row) {
      row.addEventListener("click", function () { toggleSeriesItem(row.getAttribute("data-id"), row); });
    });
  }
  function toggleSeriesItem(id, row) {
    ensureMobileSel();
    mobileSel[id] = !mobileSel[id];
    if (row) { row.classList.toggle("on", !!mobileSel[id]); row.setAttribute("aria-pressed", mobileSel[id] ? "true" : "false"); }
    applyVisibility();
  }
  function seriesSelectAll(on) {
    ensureMobileSel();
    activeList().forEach(function (s) { mobileSel[s.id] = on; });
    applyVisibility();
    renderSeriesList();
  }
  function filterSeriesList(q) {
    q = (q || "").trim().toLowerCase();
    var host = document.getElementById("sc-series-list");
    if (!host) return;
    host.querySelectorAll(".sc-series-row").forEach(function (row) {
      var s = byId[row.getAttribute("data-id")];
      var hay = ((s && (s.name + " " + (s.name_zh || "") + " " + (s.ticker || ""))) || "").toLowerCase();
      row.classList.toggle("sc-hidden", !!q && hay.indexOf(q) < 0);
    });
    host.querySelectorAll(".sc-series-grp").forEach(function (g) {
      var any = false, n = g.nextElementSibling;
      while (n && n.classList && n.classList.contains("sc-series-row")) { if (!n.classList.contains("sc-hidden")) any = true; n = n.nextElementSibling; }
      g.style.display = any ? "" : "none";
    });
  }
  function openSeriesPicker() {
    var ov = buildSeriesOverlay();
    renderSeriesList();
    var s = ov.querySelector(".sc-series-search"); if (s) s.value = "";
    document.body.style.overflow = "hidden";
    ov.classList.add("open");
  }
  function closeSeriesPicker() {
    var ov = document.getElementById("sc-series-ov");
    if (ov) ov.classList.remove("open");
    document.body.style.overflow = "";
  }

  /* ---- full-screen chart (China mobile): the inline chart is short and yields vertical
     scroll to the page; full-screen fills the viewport where there's no page to trap, so
     the chart reverts to rich one-finger panning (touch-action:none). ⤢ ⇄ ✕. */
  function mountChartFsBtn() {
    if (!isCnMobile()) return;
    var wrap = document.querySelector(".sc-chartwrap");
    if (!wrap || wrap.querySelector(".sc-chart-fs-btn")) return;
    var btn = el("button", "sc-chart-fs-btn"); btn.type = "button";
    btn.setAttribute("aria-label", "Toggle full-screen chart");   // icon is language-neutral; no bilingual text in attrs
    btn.innerHTML = "⤢";
    btn.addEventListener("click", function () { toggleChartFs(); });
    wrap.appendChild(btn);
  }
  function toggleChartFs(force) {
    var wrap = document.querySelector(".sc-chartwrap");
    if (!wrap) return;
    var on = typeof force === "boolean" ? force : !wrap.classList.contains("sc-fs");
    wrap.classList.toggle("sc-fs", on);
    var btn = wrap.querySelector(".sc-chart-fs-btn");
    if (btn) btn.innerHTML = on ? "✕" : "⤢";
    document.body.style.overflow = on ? "hidden" : "";
    var sv = document.querySelector("#sc-chart svg");
    if (sv) sv.style.touchAction = on ? "none" : "pan-y";   // full-screen: 1-finger pan; inline: yield to page scroll
    if (heroChart) heroChart.resize();                       // re-measure to the new clientHeight
  }

  /* ---- lang/theme re-render --------------------------------------------- */
  function rerender() {
    clearFirstHint();                              // drop the stale-language onboarding pill on a lang flip
    var savedFocus = state.focus, savedPhase = {};
    PHASE_FILTER.forEach(function (p) { savedPhase[p.key] = phaseState[p.key]; });
    var ovEl = document.getElementById("sc-series-ov"); if (ovEl) ovEl.remove();   // rebuild picker chrome in the new language
    mountChips(); mountBaskets(); applyFamilyDisplay(); mountCards(); buildDefaultPanel(); buildZoom(); buildGroups();
    PHASE_FILTER.forEach(function (p) { phaseState[p.key] = savedPhase[p.key]; });
    syncGroups(); syncHeroControls();              // re-localize the mode-aware legend on language flip
    if (heroChart) rebuildHero(false);
    if (savedFocus) setFocus(savedFocus); else renderPanel(null);
  }

  /* ---- guided first-load: highlight ONE line + a tap hint (novice entry) --- */
  // Pick the most interesting on-chart series: a sector at "prime entry" (Recovery),
  // else one that's "bottoming" (Trough), else the relative-strength leader.
  function bestPick() {
    var pool = activeList().filter(function (s) { return !chartHidden[s.id]; });
    if (!pool.length) pool = activeList().slice();
    var cand = pool.filter(function (s) { return s.now.phase === "Recovery"; });
    if (!cand.length) cand = pool.filter(function (s) { return s.now.phase === "Trough"; });
    if (!cand.length) cand = pool;
    cand = cand.slice().sort(function (a, b) { return (a.now.rs_rank || 999) - (b.now.rs_rank || 999); });
    return cand.length ? cand[0].id : null;
  }
  // highlight (dim the rest) WITHOUT opening the focus panel/sheet — keeps the full
  // comparison overlay but gives a novice a single clear entry point. Uses the chart's
  // own focus (persists across re-render) rather than setFocus (which opens the sheet).
  function guideEntry() {
    if (state.focus) return;
    var bp = bestPick();
    if (bp && heroChart) heroChart.focus(bp);
  }
  // one-shot onboarding pill over the chart — cleared on the first real interaction.
  var firstHintDone = false, firstHintTimer = null;
  function showFirstHint() {
    if (firstHintDone) return;
    var wrap = document.querySelector(".sc-chartwrap"); if (!wrap) return;
    firstHintDone = true;
    var n = el("div", "sc-chart-hint sc-hint-tap"); n.id = "sc-firsthint";
    n.innerHTML = L("High = stretched · low = washed-out — tap any line, chip or card for its story",
                    "高 = 拉伸 · 低 = 超卖 — 点按任意曲线、标签或卡片查看其走势");
    wrap.appendChild(n);
    firstHintTimer = setTimeout(clearFirstHint, 11000);
  }
  function clearFirstHint() {
    if (firstHintTimer) { clearTimeout(firstHintTimer); firstHintTimer = null; }
    var n = document.getElementById("sc-firsthint"); if (n && n.parentNode) n.parentNode.removeChild(n);
  }

  /* ---- boot -------------------------------------------------------------- */
  function boot() {
    // Basket-like families: chart only the STRONGEST few to start — overlaid lines are an
    // unreadable tangle. The whole field is one tap away via "Select all visible". (They're
    // off the chart for now anyway because Sector ETFs is the active family at load.)
    var bRanked = BASKETS.slice().sort(function (a, b) { return (a.now.rs_rank || 999) - (b.now.rs_rank || 999); });
    BASKETS.forEach(function (b) { basketShown[b.id] = false; chartHidden[b.id] = true; });
    bRanked.slice(0, 6).forEach(function (b) { basketShown[b.id] = true; });
    // NASDAQ / RUSSELL: initialise hidden; when their tab is activated switchFamily seeds them
    NASDAQ.concat(RUSSELL).forEach(function (b) { basketShown[b.id] = false; chartHidden[b.id] = true; });
    mountChips(); mountBaskets();
    wireFamily(); applyFamilyDisplay();                            // sectors section active; baskets hidden
    mountHero(); wireControls(); wireAdvanced(); syncHeroControls(); buildGroups(); buildDefaultPanel(); mountCards(); initSheet();
    initMobileChrome(); mountChartFsBtn();
    document.addEventListener("langchange", rerender);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { var w = document.querySelector(".sc-chartwrap.sc-fs"); if (w) toggleChartFs(false); }
    });
    var h = (location.hash || "").replace("#", "");
    if (h && byId[h]) setTimeout(function () {
      var hs = byId[h];
      if (isBasketRec(hs)) switchFamily(FAM[hs.kind] ? hs.kind : "baskets");
      setFocus(h);
    }, 350);
    else { guideEntry(); showFirstHint(); }   // novice entry: highlight one line + a tap hint
  }
  // public hook: let a host page (e.g. Sector Central) focus the embedded overlay on a
  // sector/basket by id, switching family + scrolling the chart into view. Returns false
  // if the id is unknown so the caller can fall back to a normal link.
  window.SectorCyclesFocus = function (id) {
    if (!id || !byId[id]) return false;
    var s = byId[id];
    switchFamily(isBasketRec(s) ? (FAM[s.kind] ? s.kind : "baskets") : "sectors");
    setFocus(id);
    var ch = document.getElementById("sc-chart");
    if (ch && ch.scrollIntoView) ch.scrollIntoView({ behavior: "smooth", block: "center" });
    return true;
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

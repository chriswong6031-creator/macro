/* stock_seasonality.js — Calendar Clock interaction (Lane 2).
   Paired plain-copy asset: templates/ is the source, site/ must byte-match
   (python -m scripts.check_template_site_sync --fix).

   Contract (design spec §9): the ONLY numbers this file may show are the ones
   the server shipped, or the ones exactly derivable from years[].cum by
   `calendar.window_convention`, verbatim — start_doy/end_doy are 1-based
   day-of-year, cum index = doy - 1, so
       window log return = (cum[end_doy - 1] - cum[start_doy - 1]) * cum_scale
       mean, median, share up, sd, |t| = |mean| / (sd / sqrt(n))
   It never builds a null distribution, never invents a p-value, and never prints
   a state it cannot support. Where a null is missing, it says so.

   The default symbol's payload is embedded in the page (#sx-data), so the gate is
   draggable with no network round-trip. Only a SYMBOL SWITCH fetches: index.json
   same-origin, entities from DATA_BASE (R2). */
(function () {
  "use strict";

  var root = document.getElementById("sx-root");
  var seed = document.getElementById("sx-data");
  if (!root || !seed) return;

  var E = null;
  try { E = JSON.parse(seed.textContent); } catch (e) { E = null; }
  if (!E || !E.years || !E.years.length) { note("sx-err", true); return; }

  /* ── geometry, identical to scripts/build_stock_seasonality.py ───────────── */
  var SLOTS = 365, X0 = 44, PX = 896 / 365, Y0 = 16, Y1 = 296, MAXP = 183;
  var SCALE = 1e-5;                       // overridden from calendar.cum_scale
  var FX0 = 10, FX1 = 450, FDOT = 454, FY0 = 10, FY1 = 180;
  var MIN_W = 5, MAX_W = 120;
  var MON_START = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
  var MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var SEASON_EN = ["Deep-winter", "Early-spring", "Early-summer", "Late-summer", "Autumn", "Year-end"];
  var SEASON_ZH = ["深冬", "早春", "初夏", "盛夏", "秋季", "年末"];

  function readScale() {
    var c = (E && E.calendar) || {};
    var v = parseFloat(c.cum_scale);
    SCALE = isFinite(v) && v > 0 ? v : 1e-5;
  }
  readScale();

  var state = {
    a: +root.dataset.a || 1,
    b: +root.dataset.b || 40,
    lookback: 0,          // 0 = Max
    panel: "raw",
    central: "median",
    dragged: false,
    symbol: E.symbol
  };
  var DEFAULT_A = state.a, DEFAULT_B = state.b;

  /* ── small helpers ──────────────────────────────────────────────────────── */
  function $(id) { return document.getElementById(id); }
  function zh() { return document.documentElement.getAttribute("data-lang") === "zh"; }
  function note(id, on) { var n = $(id); if (n) n.setAttribute("data-on", on ? "1" : "0"); }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function xpos(i) { return X0 + i * PX; }
  function fmtPct(x, dp) { return (x >= 0 ? "+" : "") + (x * 100).toFixed(dp == null ? 1 : dp) + "%"; }
  function thousands(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }

  function doyDate(d) { var t = new Date(Date.UTC(2001, 0, 1)); t.setUTCDate(clamp(d, 1, SLOTS)); return t; }
  function mdEn(d) { var t = doyDate(d); return MON_EN[t.getUTCMonth()] + " " + t.getUTCDate(); }
  function mdZh(d) { var t = doyDate(d); return (t.getUTCMonth() + 1) + "月" + t.getUTCDate() + "日"; }
  function mdIso(d) {
    var t = doyDate(d), m = t.getUTCMonth() + 1, dd = t.getUTCDate();
    return (m < 10 ? "0" : "") + m + "-" + (dd < 10 ? "0" : "") + dd;
  }

  /* Bilingual text goes into an existing l-en / l-zh pair — never a single
     language written straight into the DOM. */
  function setPair(el, en, zhs) {
    if (!el) return;
    var a = el.querySelector(".l-en"), b = el.querySelector(".l-zh");
    if (!a || !b) {
      el.textContent = "";
      a = document.createElement("span"); a.className = "l-en";
      b = document.createElement("span"); b.className = "l-zh";
      el.appendChild(a); el.appendChild(b);
    }
    a.textContent = en; b.textContent = zhs;
  }

  /* ── panels ─────────────────────────────────────────────────────────────── */
  function rawYears() { return E.years || []; }
  function neutralBlock() { return (E.neutral && E.neutral.market) || null; }
  function hasNeutral() { var m = neutralBlock(); return !!(m && m.years && m.years.length); }

  function detrend(cum) {
    var last = cum.length - 1, end = cum[last] - cum[0], out = new Array(cum.length), i;
    for (i = 0; i < cum.length; i++) out[i] = cum[i] - end * (i / (last || 1));
    return out;
  }

  /* {years:[{year,cum}], family, derived:bool} for the active lens + lookback */
  function activePanel() {
    var src, fam, derived = false;
    if (state.panel === "neutral" && hasNeutral()) {
      src = neutralBlock().years; fam = neutralBlock().family || null;
    } else {
      src = rawYears(); fam = E.family || null;
      if (state.panel === "detrended") {
        src = src.map(function (y) { return { year: y.year, cum: detrend(y.cum) }; });
        fam = null; derived = true;      // detrending has no shipped search accounting
      }
    }
    var n = state.lookback ? Math.min(state.lookback, src.length) : src.length;
    return { years: src.slice(src.length - n), family: fam, derived: derived };
  }

  /* The null computed on THIS year count, or nothing. Comparing a 10-year |t|
     against a 25-year null is the quiet dishonesty this page exists to avoid, so
     a lookback with no matching null gets no verdict. family.null.n_years is the
     producer's own statement of what it was run on. */
  function nullFor(fam, n) {
    if (!fam) return null;
    var by = fam.null_by_lookback;
    if (by && by[String(n)]) return by[String(n)];
    if (!fam.null) return null;
    var on = fam.null.n_years != null ? fam.null.n_years
      : ((E.coverage && E.coverage.n_years_complete) || null);
    return on == null || +on === n ? fam.null : null;
  }
  function q95(nul) {
    var q = nul && nul.max_abs_t_quantiles;
    return q && q["0.95"] != null ? +q["0.95"] : null;
  }

  /* ── the statistics (spec §9) ───────────────────────────────────────────── */
  function stats(years, a, b) {
    var r = years.map(function (y) { return (y.cum[b - 1] - y.cum[a - 1]) * SCALE; });
    var n = r.length, i, mean = 0, v = 0;
    for (i = 0; i < n; i++) mean += r[i];
    mean /= (n || 1);
    for (i = 0; i < n; i++) v += (r[i] - mean) * (r[i] - mean);
    var sd = n > 1 ? Math.sqrt(v / (n - 1)) : 0;
    var s = r.slice().sort(function (x, y) { return x - y; });
    return {
      r: r, n: n, mean: mean,
      median: n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : 0,
      up: r.filter(function (x) { return x > 0; }).length,
      sd: sd,
      absT: sd > 0 && n ? Math.abs(mean) / (sd / Math.sqrt(n)) : 0
    };
  }

  /* own / market / fails / thin / nonull — see spec §3 chip 4.
     `market` is only honest when the market leg genuinely leaves nothing behind:
     either there is no residual panel at all (the benchmark itself), or there is
     one and its window does not clear. A residual panel with NO usable null for
     this lookback is "we cannot say", not "the market's". */
  /* §16: the market benchmark's residual is empty BY CONSTRUCTION, so the honest
     `market` state produces circular copy. Override the WORDS, never the state. */
  function selfBenchmark() {
    return state.panel === "raw" && E.default_window &&
      E.default_window.neutral_basis === "self_benchmark";
  }

  function verdict(p, st) {
    if (st.n < 6) return "thin";
    var rawNull = nullFor(state.panel === "detrended" ? null : p.family, st.n);
    if (p.derived || !rawNull) return "nonull";
    var rq = q95(rawNull);
    if (rq == null) return "nonull";
    if (st.absT < rq) return "fails";
    if (state.panel === "neutral") return "own";      // already the residual panel
    if (!hasNeutral()) return "market";               // no residual: the benchmark
    var m = neutralBlock();
    var ny = m.years.slice(Math.max(0, m.years.length - st.n));
    var nNull = nullFor(m.family, ny.length), nq = q95(nNull);
    if (nq == null) return "nonull";      // a panel exists but no null for this n
    return stats(ny, state.a, state.b).absT >= nq ? "own" : "market";
  }

  /* (cdf, |t|) rungs — the producer's 101-rung ladder when shipped, else the three
     §9 quantiles. Nothing is interpolated into existence: every rung is a number
     the server computed. */
  function rungs(nul) {
    if (!nul) return [];
    var lad = nul.max_abs_t_quantile_ladder, out = [], k;
    if (lad && lad.length > 1) {
      for (var i = 0; i < lad.length; i++) out.push([i / (lad.length - 1), +lad[i]]);
      return out;
    }
    var q = nul.max_abs_t_quantiles || {};
    for (k in q) if (Object.prototype.hasOwnProperty.call(q, k)) out.push([+k, +q[k]]);
    return out.sort(function (x, y) { return x[0] - y[0]; });
  }

  function exceedance(absT, nul) {
    var grid = rungs(nul);
    if (!grid.length) return { form: "none" };
    if (absT >= grid[grid.length - 1][1]) return { form: "lt", pct: 1, cdf: grid[grid.length - 1][0] };
    if (absT < grid[0][1]) return { form: "gt", pct: Math.round(100 * (1 - grid[0][0])), cdf: grid[0][0] };
    for (var i = 0; i < grid.length - 1; i++) {
      if (absT >= grid[i][1] && absT < grid[i + 1][1]) {
        var f = grid[i + 1][1] > grid[i][1] ? (absT - grid[i][1]) / (grid[i + 1][1] - grid[i][1]) : 0;
        var p = grid[i][0] + f * (grid[i + 1][0] - grid[i][0]);
        var r = Math.round(100 * (1 - p));
        return r < 1 ? { form: "lt", pct: 1, cdf: p } : { form: "exact", pct: r, cdf: p };
      }
    }
    return { form: "none" };
  }

  /* A genuine season survives being nudged; a recurring DATE (earnings, expiry,
     a rebalance) does not. Spec §15 — sign unchanged at all four shifts AND the
     median shifted |t| at least 60% of the unshifted one. A shift that would run
     past either end of the year does not survive. */
  var SHIFTS = [-5, -2, 2, 5];
  function survives(years, a, b) {
    var base = stats(years, a, b);
    if (!base.n || !base.absT) return false;
    var ts = [], i, sh, st;
    for (i = 0; i < SHIFTS.length; i++) {
      sh = SHIFTS[i];
      if (a + sh < 1 || b + sh > SLOTS) return false;
      st = stats(years, a + sh, b + sh);
      if (st.mean === 0 || (st.mean > 0) !== (base.mean > 0)) return false;
      ts.push(st.absT);
    }
    ts.sort(function (x, y) { return x - y; });
    var med = ts.length % 2 ? ts[(ts.length - 1) / 2] : (ts[ts.length / 2 - 1] + ts[ts.length / 2]) / 2;
    return med >= 0.6 * base.absT;
  }

  /* ── year-field drawing ─────────────────────────────────────────────────── */
  /* Cum INDICES (doy - 1), <=183 of them, always carrying the gate edges. */
  function sampleIdx(a, b) {
    var last = SLOTS - 1, keep = {}, out = [], i;
    keep[0] = 1; keep[last] = 1;
    if (a != null) keep[clamp(a, 0, last)] = 1;
    if (b != null) keep[clamp(b, 0, last)] = 1;
    var must = {}; for (i in keep) must[i] = 1;
    for (i = 0; i < last; i += 2) keep[i] = 1;
    for (i in keep) if (Object.prototype.hasOwnProperty.call(keep, i)) out.push(+i);
    out.sort(function (x, y) { return x - y; });
    var j = 1;
    while (out.length > MAXP && j < out.length - 1) {
      if (must[out[j]]) j++; else out.splice(j, 1);
    }
    return out;
  }

  function yScale(years) {
    var lo = 0, hi = 0, n = years.length, i, col, k;
    for (i = 0; i < years[0].cum.length; i++) {
      col = [];
      for (k = 0; k < n; k++) col.push(years[k].cum[i] * SCALE);
      col.sort(function (x, y) { return x - y; });
      lo = Math.min(lo, col[Math.max(0, Math.floor(0.05 * (n - 1)))]);
      hi = Math.max(hi, col[Math.min(n - 1, Math.ceil(0.95 * (n - 1)))]);
    }
    var pad = 0.04 * Math.max(hi - lo, 1e-6);
    lo -= pad; hi += pad;
    return function (v) { return Y1 - (v - lo) / ((hi - lo) || 1) * (Y1 - Y0); };
  }

  function pathOf(cum, y, idx) {
    var s = "M", i;
    for (i = 0; i < idx.length; i++) {
      s += (i ? "L" : "") + xpos(idx[i]).toFixed(1) + "," + y(cum[idx[i]] * SCALE).toFixed(1);
    }
    return s;
  }

  function colStat(years, i, kind) {
    var col = years.map(function (y) { return y.cum[i] * SCALE; }).sort(function (x, y) { return x - y; });
    var n = col.length;
    if (kind === "median") return n % 2 ? col[(n - 1) / 2] : (col[n / 2 - 1] + col[n / 2]) / 2;
    if (kind === "mean") return col.reduce(function (s, v) { return s + v; }, 0) / n;
    if (kind === "p20") return col[Math.floor(0.2 * (n - 1))];
    return col[Math.ceil(0.8 * (n - 1))];
  }

  var SVGNS = "http://www.w3.org/2000/svg";
  function el(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag), k;
    for (k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) e.setAttribute(k, attrs[k]);
    return e;
  }

  function drawField(p) {
    var y = yScale(p.years), idx = sampleIdx(state.a - 1, state.b - 1), i;
    var g = $("sxf-strands");
    if (g) {
      g.textContent = "";
      for (i = 0; i < p.years.length; i++) {
        g.appendChild(el("path", {
          "class": "sxf-strand", d: pathOf(p.years[i].cum, y, idx),
          "vector-effect": "non-scaling-stroke", style: "animation:none"
        }));
      }
    }
    var top = "M", bot = "", j;
    for (j = 0; j < idx.length; j++) {
      top += (j ? "L" : "") + xpos(idx[j]).toFixed(1) + "," + y(colStat(p.years, idx[j], "p80")).toFixed(1);
    }
    for (j = idx.length - 1; j >= 0; j--) {
      bot += "L" + xpos(idx[j]).toFixed(1) + "," + y(colStat(p.years, idx[j], "p20")).toFixed(1);
    }
    var band = $("sxf-band"); if (band) { band.setAttribute("d", top + bot + "Z"); band.style.animation = "none"; }

    var med = "M";
    for (j = 0; j < idx.length; j++) {
      med += (j ? "L" : "") + xpos(idx[j]).toFixed(1) + "," + y(colStat(p.years, idx[j], state.central)).toFixed(1);
    }
    var mp = $("sxf-median");
    if (mp) { mp.setAttribute("d", med); mp.style.animation = "none"; mp.style.strokeDasharray = "none"; mp.style.strokeDashoffset = "0"; }

    var base = document.querySelector(".sxf-base");
    if (base) { base.setAttribute("y1", y(0).toFixed(1)); base.setAttribute("y2", y(0).toFixed(1)); }

    var cur = $("sxf-cur");
    if (cur) {
      if (state.panel === "raw" && E.current_year && E.current_year.cum && E.current_year.cum.length > 2) {
        var last = E.current_year.last_index != null ? E.current_year.last_index : E.current_year.cum.length - 1;
        last = clamp(last, 0, E.current_year.cum.length - 1);
        var ci = sampleIdx(0, last).filter(function (k) { return k <= last; });
        cur.setAttribute("d", pathOf(E.current_year.cum, y, ci));
        cur.style.display = "";
      } else { cur.style.display = "none"; }
    }
    moveGate();
  }

  function moveGate() {
    var x1 = xpos(state.a - 1), x2 = xpos(state.b - 1), w = Math.max(0, x2 - x1);
    var g1 = $("sxf-g1"), g2 = $("sxf-g2"), gf = $("sxf-gatefill"), dr = $("sxf-drag");
    if (g1) { g1.setAttribute("x1", x1.toFixed(1)); g1.setAttribute("x2", x1.toFixed(1)); g1.style.animation = "none"; }
    if (g2) { g2.setAttribute("x1", x2.toFixed(1)); g2.setAttribute("x2", x2.toFixed(1)); g2.style.animation = "none"; }
    if (gf) { gf.setAttribute("x", x1.toFixed(1)); gf.setAttribute("width", w.toFixed(1)); gf.style.animation = "none"; }
    if (dr) { dr.setAttribute("x", x1.toFixed(1)); dr.setAttribute("width", w.toFixed(1)); }
    [["sxf-h1", state.a, x1], ["sxf-h2", state.b, x2]].forEach(function (h) {
      var e = $(h[0]); if (!e) return;
      e.setAttribute("transform", "translate(" + h[2].toFixed(1) + ",0)");
      e.setAttribute("aria-valuenow", h[1]);
      e.setAttribute("aria-valuetext", mdIso(h[1]));
      e.style.animation = "none";
    });
  }

  /* ── the window fan (the signature) ─────────────────────────────────────── */
  function drawFan(p, st) {
    var svg = $("sx-fan"); if (!svg) return;
    var span = Math.max(1, state.b - state.a), step = (FX1 - FX0) / span;
    var rel = p.years.map(function (yr) {
      var out = [], i;
      for (i = state.a - 1; i <= state.b - 1; i++) out.push((yr.cum[i] - yr.cum[state.a - 1]) * SCALE);
      return out;
    });
    var hi = 0, lo = 0;
    rel.forEach(function (row) { row.forEach(function (v) { if (v > hi) hi = v; if (v < lo) lo = v; }); });
    hi *= 1.08; lo *= 1.08;
    var rng = (hi - lo) || 1;
    var yy = function (v) { return FY0 + (hi - v) / rng * (FY1 - FY0); };
    var d = function (row) {
      var s = "M", i;
      for (i = 0; i < row.length; i++) s += (i ? "L" : "") + (FX0 + i * step).toFixed(1) + "," + yy(row[i]).toFixed(1);
      return s;
    };
    var zero = svg.querySelector(".z");
    if (zero) { zero.setAttribute("y1", yy(0).toFixed(1)); zero.setAttribute("y2", yy(0).toFixed(1)); }

    var gp = $("sx-fan-paths"), gd = $("sx-fan-dots"), i, up, t;
    if (gp) gp.textContent = "";
    if (gd) gd.textContent = "";
    for (i = 0; i < rel.length; i++) {
      up = rel[i][rel[i].length - 1] > 0;
      if (gp) {
        var pe = el("path", { "class": "f " + (up ? "up" : "dn"), d: d(rel[i]), "vector-effect": "non-scaling-stroke" });
        t = document.createElementNS(SVGNS, "title");
        t.textContent = p.years[i].year + ": " + fmtPct(Math.expm1(rel[i][rel[i].length - 1]), 2);
        pe.appendChild(t);
        gp.appendChild(pe);
      }
      if (gd) gd.appendChild(el("circle", { "class": "e " + (up ? "up" : "dn"), cx: FDOT, cy: yy(rel[i][rel[i].length - 1]).toFixed(1), r: 2.1 }));
    }
    var med = [], j, col;
    for (j = 0; j <= span; j++) {
      col = rel.map(function (row) { return row[j]; }).sort(function (x, y) { return x - y; });
      med.push(col.length % 2 ? col[(col.length - 1) / 2] : (col[col.length / 2 - 1] + col[col.length / 2]) / 2);
    }
    var mp = $("sx-fan-med"); if (mp) mp.setAttribute("d", d(med));

    var above = rel.filter(function (row) { return row[row.length - 1] > 0; }).length;
    setPair($("sx-fancap").querySelector(".n") || $("sx-fancap"),
      "Each thread is one year, starting from zero on " + mdEn(state.a) + ". " + above + " of " + st.n + " finished above the line.",
      "每条线是一年，从 " + mdZh(state.a) + " 起算为零。" + st.n + " 年中 " + above + " 年收在零线之上。");
  }

  /* ── the reading ────────────────────────────────────────────────────────── */
  function seasonPhrase(rising) {
    var mid = doyDate(Math.floor((state.a + state.b) / 2)), k = Math.floor(mid.getUTCMonth() / 2);
    return {
      en: SEASON_EN[k] + (rising ? " strength" : " weakness"),
      zh: SEASON_ZH[k] + (rising ? "走强" : "走弱")
    };
  }

  function render() {
    var p = activePanel(), st = stats(p.years, state.a, state.b);
    var v = verdict(p, st);
    root.dataset.state = v;

    drawField(p);
    drawFan(p, st);

    var s = seasonPhrase(st.median >= 0);
    var vd = $("sx-verdict");
    var benchmark = selfBenchmark() && v === "market";
    if (benchmark) setPair(vd, s.en + " here holds up after counting every window tried. Get ready.", s.zh + "，在计入所有测试窗口后依然成立。做好准备。");
    else if (v === "own") setPair(vd, s.en + " here is this name's own, not the market's. Get ready.", s.zh + "源自该股自身，而非大盘。做好准备。");
    else if (v === "market") setPair(vd, s.en + " here is really the market's calendar. Watch, don't chase.", s.zh + "其实来自大盘日历，而非该股。观察，不要追。");
    else if (v === "thin") setPair(vd, "Only " + st.n + " years of history — too few to call. Watch, don't chase.", "仅 " + st.n + " 年历史，样本太少，暂无结论。观察，不要追。");
    else if (v === "nonull") setPair(vd, "This view carries no search accounting, so it shows no verdict.", "该视图没有搜索校正，因此不给出结论。");
    else setPair(vd, "Looks strong, but not after counting every window tried. Stand aside.", "看似强势，但计入所有测试窗口后并不成立。建议观望。");

    var chips = $("sx-chips").children;
    setPair(chips[0].querySelector(".n"), mdEn(state.a) + " → " + mdEn(state.b), mdZh(state.a) + " → " + mdZh(state.b));
    setPair(chips[2].querySelector(".n"), st.n + " years", st.n + " 年");
    setPair(chips[3].querySelector(".n"), st.up + " of " + st.n + " up", st.n + " 年中 " + st.up + " 年上涨");

    var c4 = $("sx-chip4"), lab = c4.querySelector(".sx-c4"), tip = c4.querySelector(".sx-help");
    if (!lab) { lab = document.createElement("span"); lab.className = "sx-c4"; c4.insertBefore(lab, c4.firstChild); }
    while (c4.firstChild !== lab) c4.removeChild(c4.firstChild);
    while (lab.nextSibling && lab.nextSibling !== tip) c4.removeChild(lab.nextSibling);
    c4.className = "sx-chip " + (benchmark ? "sx-chip-up"
      : ({ own: "sx-chip-up", market: "sx-chip-mkt", fails: "sx-chip-muted" }[v] || "sx-chip-thin"));
    if (benchmark) setPair(lab, "Its own pattern", "自身的规律");
    else if (v === "own") setPair(lab, "Its own pattern", "该股自身的规律");
    else if (v === "market") setPair(lab, "The market's pattern", "跟随大盘的规律");
    else if (v === "thin") setPair(lab, "Not enough years", "年数不足");
    else if (v === "nonull") setPair(lab, "No search accounting", "暂无搜索校正");
    else setPair(lab, "Doesn't hold up", "不成立");

    if (tip) {
      setPair(tip.querySelector(".sx-tip"),
        benchmark
          ? "This symbol is the market benchmark, so there is no separate market leg to remove — its calendar is the market's by definition."
          : "Its own pattern: the window survives after removing a market leg sized to this name. The market's pattern: it survives raw, but disappears once the market is removed — real, just not specific to this name. Doesn't hold up: it does not survive the count of every window tried.",
        benchmark
          ? "该标的就是市场基准，没有可剥离的大盘部分——它的日历规律即为大盘的规律。"
          : "该股自身的规律：按该股敏感度剔除大盘影响后，窗口依然成立。跟随大盘的规律：原始数据成立，但剔除大盘后消失 — 现象真实，只是并非该股特有。不成立：计入所有测试窗口后无法成立。");
    }

    var expl = $("sx-expl");
    state.dragged = !(state.a === DEFAULT_A && state.b === DEFAULT_B);
    if (expl) expl.hidden = !state.dragged;

    var med = Math.expm1(state.central === "mean" ? st.mean : st.median);
    var fig = $("sx-fig");
    fig.textContent = fmtPct(med);
    fig.className = "sx-fig " + (med > 0 ? "up" : "dn");
    setPair($("sx-figlab"), state.central === "mean" ? "average year" : "typical year",
      state.central === "mean" ? "平均年份" : "典型年份");

    /* after-search sentence + chance track — server-shipped numbers only */
    var nul = p.derived ? null : nullFor(p.family, st.n);
    var isDefault = !state.dragged && state.panel === "raw" &&
      p.years.length === ((E.coverage && E.coverage.n_years_complete) || 0);
    var exc = (isDefault && E.default_window && E.default_window.null_max_exceedance_pct != null)
      ? (Math.round(E.default_window.null_max_exceedance_pct) < 1
        ? { form: "lt", pct: 1, cdf: 0.99 }
        : { form: "exact", pct: Math.round(E.default_window.null_max_exceedance_pct), cdf: 1 - E.default_window.null_max_exceedance_pct / 100 })
      : exceedance(st.absT, nul);
    var after = $("sx-after"), tipEl = after.querySelector(".sx-help");
    while (after.firstChild && after.firstChild !== tipEl) after.removeChild(after.firstChild);
    var body = document.createElement("span");
    after.insertBefore(body, tipEl);
    if (v !== "thin" && v !== "nonull" && exc.form !== "none") {
      var B = thousands((nul && nul.B) || 2000);
      var pe = exc.form === "lt" ? "<1%" : exc.form === "gt" ? "more than " + exc.pct + "%" : exc.pct + "%";
      var pz = exc.form === "lt" ? "<1%" : exc.form === "gt" ? "超过 " + exc.pct + "%" : exc.pct + "%";
      var tail = v === "fails" ? " — often enough that this one doesn't stand out." : " — rare enough that this one does stand out.";
      var tailZ = v === "fails" ? "——出现得够频繁，因此这一个并不突出。" : "——出现得够罕见，因此这一个确实突出。";
      setPair(body, "We shuffled " + state.symbol + "'s history " + B + " times. A window this strong turned up by chance in " + pe + " of them" + tail,
        "我们把 " + state.symbol + " 的历史打乱了 " + B + " 次。像这样强的窗口在其中 " + pz + " 里纯属偶然出现" + tailZ);
    } else {
      setPair(body, "We haven't finished the search accounting for this view yet.", "该视图的搜索校正尚未完成。");
    }
    if (tipEl) {
      var qs = nul && nul.max_abs_t_quantiles, q = qs && qs["0.95"] != null ? (+qs["0.95"]).toFixed(2) : "—";
      var fam = p.family || {};
      setPair(tipEl.querySelector(".sx-tip"),
        "Family: " + (fam.n_candidates || "—") + " windows on this symbol. Your window: |t| " + st.absT.toFixed(2) +
        ". Chance-alone 95th percentile of the best window in the family: |t| " + q +
        ". Method: joint maxT, Westfall-Young style, dependence preserved by shifting whole years. Unit of evidence: one complete year, not one day.",
        "窗口族：该代码共 " + (fam.n_candidates || "—") + " 个窗口。本窗口：|t| " + st.absT.toFixed(2) +
        "。纯属偶然情况下族内最佳窗口的 95 分位：|t| " + q +
        "。方法：联合 maxT，Westfall–Young 式，通过整年平移保留相关结构。证据单位：一个完整年份，而非一个交易日。");
    }

    var track = $("sx-track");
    if (track) {
      var qq = nul && nul.max_abs_t_quantiles;
      if (!qq || qq["0.99"] == null) { track.style.display = "none"; }
      else {
        track.style.display = "";
        var xmax = Math.max(+qq["0.99"], st.absT) * 1.08 || 1;
        var stops = [["0.10", 20], ["0.25", 40], ["0.50", 55], ["0.75", 40], ["0.90", 18], ["0.99", 6]]
          .filter(function (k) { return qq[k[0]] != null; })
          .map(function (k) { return "color-mix(in srgb, var(--sx-ink) " + k[1] + "%, transparent) " + (100 * qq[k[0]] / xmax).toFixed(2) + "%"; });
        track.style.setProperty("--sx-stops", stops.join(","));
        track.querySelector("i").style.left = clamp(100 * st.absT / xmax, 0, 100).toFixed(2) + "%";
      }
    }

    var stab = $("sx-stab");
    if (stab) {
      var shipped = E.default_window && E.default_window.stability;
      var keeps = null;
      if (isDefault) { if (shipped && typeof shipped.survives === "boolean") keeps = shipped.survives; }
      else if (st.n) { keeps = survives(p.years, state.a, state.b); }
      if (keeps === null) { stab.hidden = true; }
      else {
        stab.hidden = false;
        if (keeps) setPair(stab, "Nudging the window a few days either way keeps this.", "把窗口前后挪几天，这个规律仍然成立。");
        else setPair(stab, "Nudging the window a few days either way loses it — the effect depends on these exact dates.", "把窗口前后挪几天就消失了——这个效应取决于这几个具体日期。");
      }
    }

    /* the years table */
    var tb = $("sx-tbody");
    if (tb) {
      var vmax = 0;
      st.r.forEach(function (x) { vmax = Math.max(vmax, Math.abs(x)); });
      vmax = vmax || 1;
      tb.textContent = "";
      p.years.forEach(function (yr, i) {
        var simple = Math.expm1(st.r[i]), up = simple > 0;
        var tr = document.createElement("tr"); tr.className = "sx-yrow";
        var td1 = document.createElement("td"); td1.className = "y"; td1.textContent = yr.year;
        var td2 = document.createElement("td"); td2.className = "r " + (up ? "up" : "dn"); td2.textContent = fmtPct(simple, 2);
        var td3 = document.createElement("td");
        td3.innerHTML = '<span class="sx-bar"><span class="zero" style="left:50%"></span><i class="' +
          (up ? "up" : "dn") + '" style="' + (up ? "left:50%" : "right:50%") + ';width:' +
          (Math.abs(st.r[i]) / vmax * 50).toFixed(1) + '%"></i></span>';
        tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3);
        tb.appendChild(tr);
      });
    }
  }

  /* ── gate interaction ───────────────────────────────────────────────────── */
  function setWindow(a, b) {
    a = clamp(Math.round(a), 1, SLOTS); b = clamp(Math.round(b), 1, SLOTS);
    if (b - a < MIN_W) b = a + MIN_W;
    if (b - a > MAX_W) b = a + MAX_W;
    if (b > SLOTS) { b = SLOTS; a = Math.max(1, b - Math.max(MIN_W, Math.min(MAX_W, b - a))); }
    state.a = a; state.b = b;
    render();
  }

  var svg = $("sxf");
  function dayAt(evt) {
    var r = svg.getBoundingClientRect();
    var cx = (evt.touches ? evt.touches[0].clientX : evt.clientX) - r.left;
    return (cx / r.width * 960 - X0) / PX + 1;      // -> 1-based day-of-year
  }

  var drag = null;
  function down(kind) {
    return function (e) {
      e.preventDefault();
      drag = { kind: kind, at: dayAt(e), a: state.a, b: state.b };
      window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
      window.addEventListener("touchmove", move, { passive: false }); window.addEventListener("touchend", up);
    };
  }
  function move(e) {
    if (!drag) return;
    e.preventDefault();
    var d = dayAt(e), delta = d - drag.at;
    if (drag.kind === "a") setWindow(Math.min(d, drag.b - MIN_W), drag.b);
    else if (drag.kind === "b") setWindow(drag.a, Math.max(d, drag.a + MIN_W));
    else setWindow(drag.a + delta, drag.b + delta);
  }
  function up() {
    drag = null;
    window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
    window.removeEventListener("touchmove", move); window.removeEventListener("touchend", up);
  }
  ["sxf-h1", "sxf-h2", "sxf-drag"].forEach(function (id, i) {
    var e = $(id); if (!e) return;
    var kind = i === 0 ? "a" : i === 1 ? "b" : "band";
    e.addEventListener("mousedown", down(kind));
    e.addEventListener("touchstart", down(kind), { passive: false });
  });

  function monthEdge(day, back) {
    var i, cur = 0;
    for (i = 0; i < 12; i++) if (MON_START[i] <= day) cur = i;
    return back ? MON_START[cur] : (cur < 11 ? MON_START[cur + 1] : SLOTS);
  }
  [["sxf-h1", "a"], ["sxf-h2", "b"]].forEach(function (h) {
    var e = $(h[0]); if (!e) return;
    e.addEventListener("keydown", function (ev) {
      var step = ev.shiftKey ? 7 : 1, k = ev.key, cur = state[h[1]], next = null;
      if (k === "ArrowLeft") next = cur - step;
      else if (k === "ArrowRight") next = cur + step;
      else if (k === "Home") next = monthEdge(cur, true);
      else if (k === "End") next = monthEdge(cur, false);
      if (next == null) return;
      ev.preventDefault();
      if (h[1] === "a") setWindow(Math.min(next, state.b - MIN_W), state.b);
      else setWindow(state.a, Math.max(next, state.a + MIN_W));
      e.focus();
    });
  });

  /* ── control rows ───────────────────────────────────────────────────────── */
  function segment(id, apply) {
    var g = $(id); if (!g) return;
    g.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-v]");
      if (!b || b.disabled) return;
      Array.prototype.forEach.call(g.querySelectorAll("button[data-v]"), function (x) {
        x.setAttribute("aria-pressed", x === b ? "true" : "false");
      });
      apply(b.dataset.v);
      render();
    });
  }
  segment("sx-central", function (v) { state.central = v; });
  segment("sx-panel", function (v) { state.panel = v; });
  segment("sx-lookback", function (v) { state.lookback = +v; });

  /* ── symbol switching (spec §6) ─────────────────────────────────────────── */
  var INDEX = null, cursor = -1, filtered = [];
  var input = $("sx-search"), pop = $("sx-results");

  /* DATA_BASE is the R2 public origin and carries NO trailing slash, so a bare
     concatenation yields "https://pub-….r2.devseasonalitydata/entities/MU.json"
     — a malformed host that fails every symbol switch. site/odds.js, the house
     precedent this program adopts (spec §14), normalizes it the same way. */
  function entityUrl(sym) {
    var base = window.DATA_BASE || "";
    if (base && base.slice(-1) !== "/") base += "/";
    return base + "seasonalitydata/entities/" + encodeURIComponent(sym) + ".json";
  }

  fetch("seasonalitydata/index.json", { credentials: "same-origin" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && j.entities) INDEX = j.entities; })
    .catch(function () { /* picker degrades to the shortcut strip; the page still works */ });

  function closePop() { if (pop) { pop.hidden = true; pop.textContent = ""; } input.setAttribute("aria-expanded", "false"); cursor = -1; }

  function openPop(q) {
    if (!pop) return;
    var list = INDEX || [];
    q = (q || "").trim().toUpperCase();
    filtered = list.filter(function (x) {
      return !q || (x.symbol || "").toUpperCase().indexOf(q) === 0 ||
        (x.name || "").toUpperCase().indexOf(q) >= 0;
    }).slice(0, 40);
    pop.textContent = "";
    if (!filtered.length) {
      var li = document.createElement("li"); li.className = "none";
      setPair(li, INDEX ? "No match." : "Symbol list unavailable.", INDEX ? "无匹配结果。" : "代码列表不可用。");
      pop.appendChild(li);
    } else {
      filtered.forEach(function (x, i) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", i === cursor ? "true" : "false");
        li.innerHTML = '<span class="sy"></span><span class="nm"></span><span class="ny"></span>';
        li.querySelector(".sy").textContent = x.symbol;
        li.querySelector(".nm").textContent = x.name || "";
        /* §16: n_years_panel is what the page will DRAW (capped at 25); advertising
           the fuller n_years would defeat the control's whole purpose. */
        var ny = li.querySelector(".ny");
        var depth = x.n_years_panel != null ? x.n_years_panel : x.n_years;
        setPair(ny, (depth || "—") + " years", (depth || "—") + " 年");
        li.addEventListener("mousedown", function (ev) { ev.preventDefault(); pick(x.symbol); });
        pop.appendChild(li);
      });
    }
    pop.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  if (input) {
    input.addEventListener("input", function () { cursor = -1; openPop(input.value); });
    input.addEventListener("focus", function () { openPop(input.value); });
    input.addEventListener("blur", function () { setTimeout(closePop, 120); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closePop(); return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (pop.hidden) openPop(input.value);
        cursor = clamp(cursor + (e.key === "ArrowDown" ? 1 : -1), 0, filtered.length - 1);
        Array.prototype.forEach.call(pop.querySelectorAll("li[role=option]"), function (li, i) {
          li.setAttribute("aria-selected", i === cursor ? "true" : "false");
          if (i === cursor) li.scrollIntoView({ block: "nearest" });
        });
      } else if (e.key === "Enter" && cursor >= 0 && filtered[cursor]) {
        e.preventDefault(); pick(filtered[cursor].symbol);
      }
    });
  }
  var quick = $("sx-quick");
  if (quick) {
    quick.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-sym]");
      if (b) pick(b.dataset.sym);
    });
  }

  function pick(sym) {
    if (!sym || sym === state.symbol) { closePop(); return; }
    note("sx-err", false); note("sx-nocov", false);
    fetch(entityUrl(sym), { credentials: "omit" })
      .then(function (r) {
        if (r.status === 404) { note("sx-nocov", true); return null; }
        if (!r.ok) throw new Error("http " + r.status);
        return r.json();
      })
      .then(function (j) {
        if (!j || !j.years || !j.years.length) return;
        adopt(j);
      })
      .catch(function () {
        /* Cross-origin fetch has more ways to fail than a same-origin one. Keep the
           symbol already on screen and say what happened — never blank the page. */
        note("sx-err", true);
      });
    closePop();
  }

  function adopt(j) {
    E = j;
    readScale();
    state.symbol = j.symbol;
    state.panel = "raw"; state.lookback = 0; state.dragged = false;
    var dw = j.default_window || {};
    DEFAULT_A = state.a = dw.start_doy || 1;
    DEFAULT_B = state.b = dw.end_doy || Math.min(SLOTS, state.a + 30);
    $("sx-name").textContent = j.name || j.symbol;
    $("sx-sym").textContent = j.symbol;
    var nb = document.querySelector('#sx-panel button[data-v="neutral"]');
    if (nb) nb.disabled = !hasNeutral();
    Array.prototype.forEach.call(document.querySelectorAll("#sx-panel button, #sx-lookback button"), function (b) {
      b.setAttribute("aria-pressed", (b.dataset.v === "raw" || b.dataset.v === "0") ? "true" : "false");
    });
    try {
      var u = new URL(window.location.href);
      u.searchParams.set("symbol", j.symbol);
      history.replaceState(null, "", u.toString());
    } catch (e) { /* deep link is a convenience, never a dependency */ }
    if (input) input.value = "";
    render();
  }

  /* Deep link: ?symbol=XBI */
  try {
    var want = new URL(window.location.href).searchParams.get("symbol");
    if (want && want.toUpperCase() !== String(E.symbol).toUpperCase()) pick(want.toUpperCase());
  } catch (e) { /* no-op */ }

  /* theme.js hard-codes the NAV search placeholder and has no generic data-ph-zh
     handler, so this input swaps its own. A placeholder is not a title= attribute,
     so bilingual copy is allowed here — same as the nav. */
  var PH_EN = input ? input.placeholder : "";
  function syncPlaceholder() {
    if (input) input.placeholder = zh() ? (input.dataset.phZh || PH_EN) : PH_EN;
  }
  syncPlaceholder();

  /* Small multiples collapse on mobile (spec §7.7) — open by default on desktop
     where there is room for them. Only the INITIAL state; the user owns it after. */
  try {
    var more = $("sx-more");
    if (more && window.matchMedia("(max-width: 720px)").matches) more.open = false;
  } catch (e) { /* no-op */ }

  document.addEventListener("langchange", function () { syncPlaceholder(); render(); });
  render();
})();

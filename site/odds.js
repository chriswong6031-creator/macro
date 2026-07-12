/* ============================================================================
   odds.js — Odds Desk client (historical base-rate analyzer + Factor Match)
   ----------------------------------------------------------------------------
   Data plane (all display-only, computed nightly by scripts/build_odds.py):
     oddsdata/catalog.json                    — odds_catalog.v1 (git/Pages)
     (window.DATA_BASE||'') + oddsmatrix/<T>.json — odds_matrix.v1 / v1.1
       (R2, columnar; v1.1 adds the display-only vol_rel column that feeds the
       volume substrip — both schemas are tolerated)
     oddsdata/factor_match.json               — odds_factor_match.v1 (git/Pages)

   Matching semantics (mirrors the tested Python engine):
     candidate day d (excluding today, within range) matches iff for every
     ACTIVE factor |bucket(d) − bucket(today)| ≤ tol; tol = 0 for categorical
     factors (ordered:false), = the global tolerance for ordered ones. Days
     with null active-factor buckets or a null outcome are excluded. Null
     never matches.

   Charts: the Matching Days price line uses the house SVG engine mm_charts.js
   (zoom / crosshair / theme reactivity come free; matched days render as
   outcome-colored peak/trough glyph series). Price Path and Returns are
   purpose-built flat SVG (mm_charts has no histogram / day-indexed primitives).
   Everything degrades quietly: a data failure shows an empty state, never a
   broken page.
   ========================================================================== */
(function () {
  "use strict";

  /* ---------------- tiny helpers ---------------- */
  var SVGNS = "http://www.w3.org/2000/svg";
  function $(sel) { return document.querySelector(sel); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function bi(en, zh) {
    var z = (zh == null || zh === "") ? en : zh;
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(z) + "</span>";
  }
  function biRaw(en, zh) {  // caller guarantees safe HTML
    var z = (zh == null || zh === "") ? en : zh;
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + z + "</span>";
  }
  function fetchJSON(url) {
    return fetch(url, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }
  function cssVar(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fb;
  }
  function isZh() { return document.documentElement.getAttribute("data-lang") === "zh"; }
  /* ?lang=zh|en — shareable language deep link (theme.js persists lang in
     localStorage only; this mirrors its attribute contract, guarded to the two
     known values, and runs before first render so no re-paint is needed). */
  try {
    var qlang = new URLSearchParams(location.search).get("lang");
    if (qlang === "zh" || qlang === "en") {
      document.documentElement.setAttribute("data-lang", qlang);
      document.documentElement.lang = qlang === "zh" ? "zh-CN" : "en";
      try { localStorage.setItem("lang", qlang); } catch (e) {}
    }
  } catch (e) {}
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function sv(tag, attrs, parent) {
    var e = document.createElementNS(SVGNS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function debounce(fn, ms) {
    var t = null;
    return function () { if (t) clearTimeout(t); t = setTimeout(fn, ms); };
  }
  function reduceMotion() {
    try { return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); }
    catch (e) { return false; }
  }
  function fmtSigned(v, dp) { return (v > 0 ? "+" : "") + v.toFixed(dp == null ? 1 : dp); }
  /* dates: matrices carry epoch DAYS (ascending) */
  var DAY = 86400000;
  function edDate(ed) { return new Date(ed * DAY); }
  function edISO(ed) { return edDate(ed).toISOString().slice(0, 10); }
  function edYF(ed) { return 1970 + ed / 365.2425; }
  var DOW_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var DOW_ZH = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  var MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  /* numbers */
  function fmtBpPct(bp, dp) {          // basis points -> signed percent string
    if (bp == null || bp !== bp) return "—";
    var v = bp / 100;
    return (v > 0 ? "+" : "") + v.toFixed(dp == null ? 2 : dp) + "%";
  }
  function fmtRate(p, dp) { return (p * 100).toFixed(dp == null ? 1 : dp) + "%"; }
  function fmtPx(v) {
    if (v == null || v !== v) return "—";
    return v >= 1000 ? Math.round(v).toLocaleString("en-US") : v.toFixed(2);
  }
  function quantile(sorted, q) {
    if (!sorted.length) return null;
    var pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }
  function wilson(wins, n) {
    if (!n) return null;
    var z = 1.959964, p = wins / n, d = 1 + z * z / n;
    var c = (p + z * z / (2 * n)) / d;
    var h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
    return [Math.max(0, c - h), Math.min(1, c + h)];
  }
  var LOGO_CDN = "https://cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/";
  function logoImg(t, cls) {
    return '<img class="' + cls + '" src="' + LOGO_CDN + esc(t) + '.png" alt="" loading="eager"' +
           ' onerror="this.style.display=\'none\'">';
  }

  /* ---------------- state ---------------- */
  var FWD_KEY = { "1d": "fwd1_bp", "5d": "fwd5_bp", "20d": "fwd20_bp" };
  var RANGE_Y = { "5y": 5, "10y": 10, "20y": 20 };
  var HORIZON_TXT = { "1d": ["the next day", "次日"], "5d": ["the next week (5 trading days)", "其后5个交易日"], "20d": ["the next month (20 trading days)", "其后20个交易日"] };
  var RANGE_TXT = { "5y": ["5 years", "5年"], "10y": ["10 years", "10年"], "20y": ["20 years", "20年"], "max": ["the full history", "全部历史"] };
  var HZN_SHORT = { "1d": ["1d", "1日"], "5d": ["5d", "5日"], "20d": ["20d", "20日"] };
  var GROUPS = { core: ["Core", "核心"], market: ["Market", "市场"], asset: ["Asset", "个股"] };

  var S = {
    cat: null, F: {}, factorOrder: [],
    fm: null, fmTried: false,
    matrix: null, ticker: null, loadSeq: 0,
    active: {}, tol: 0, range: "10y", horizon: "1d",
    matches: [], matchedSet: null, stats: null, base: null, total: 0,
    tab: "days",
    daysSort: { key: "date", dir: -1 },
    fmTpl: null, fmMinN: 10, fmSector: "", fmSort: { key: "1d:win", dir: -1 }
  };
  var priceChart = null;   // MMChart instance
  var prevRate = null;     // last shown win rate (hero count-up start value)
  var _lastMatchN = null;  // last match count (rail pulse trigger)

  /* ---------------- catalog access ---------------- */
  function fLabel(fid) {
    var f = S.F[fid];
    if (!f) return [fid, fid];
    return [f.label_en || fid, f.label_zh || f.label_en || fid];
  }
  function bktLabel(fid, v) {
    if (v == null || v !== v) return ["n/a", "无"];
    var f = S.F[fid], b = f && f.buckets && f.buckets[String(v)];
    if (!b) return [String(v), String(v)];
    return [b.label_en || String(v), b.label_zh || b.label_en || String(v)];
  }
  function isOrdered(fid) { var f = S.F[fid]; return !(f && f.ordered === false); }
  function activeIds() {
    return S.factorOrder.filter(function (fid) { return S.active[fid]; });
  }
  /* defensive probe into catalog.market for raw display values (key names are
     builder-owned and not pinned by the contract — degrade to bucket labels) */
  function mraw(keys) {
    var m = (S.cat && S.cat.market) || {};
    for (var i = 0; i < keys.length; i++) {
      var v = m[keys[i]];
      if (typeof v === "number" && v === v) return v;
      if (m.raw && typeof m.raw[keys[i]] === "number") return m.raw[keys[i]];
    }
    return null;
  }

  /* ---------------- matching engine ---------------- */
  function todayIdx() { return S.matrix ? S.matrix.dates.length - 1 : -1; }
  function rangeCutoff() {
    var y = RANGE_Y[S.range];
    if (!y || !S.matrix) return -Infinity;
    return S.matrix.dates[todayIdx()] - Math.round(y * 365.25);
  }
  function computeAll() {
    S.matches = []; S.matchedSet = new Set(); S.stats = null; S.base = null; S.total = 0;
    var m = S.matrix;
    if (!m) return;
    var n = m.dates.length, t = n - 1, cols = m.cols || {};
    var fwd = cols[FWD_KEY[S.horizon]] || [];
    var cutoff = rangeCutoff();
    var act = activeIds(), nf = act.length;
    var fcols = [], tvals = [], tols = [], ok = true, i, f;
    for (i = 0; i < nf; i++) {
      f = act[i];
      fcols.push(cols[f] || []);
      var tv = (cols[f] || [])[t];
      tvals.push(tv == null ? null : tv);
      tols.push(isOrdered(f) ? S.tol : 0);
      if (tv == null) ok = false;   // an active factor with no value today can never match
    }
    var wins = 0, bWins = 0, bN = 0, vals = [];
    for (var d = 0; d < t; d++) {
      if (m.dates[d] < cutoff) continue;
      var fv = fwd[d];
      if (fv == null) continue;
      bN++; if (fv > 0) bWins++;
      if (!ok) continue;
      var hit = true;
      for (i = 0; i < nf; i++) {
        var bv = fcols[i][d];
        if (bv == null || Math.abs(bv - tvals[i]) > tols[i]) { hit = false; break; }
      }
      if (!hit) continue;
      S.matches.push(d); S.matchedSet.add(d);
      vals.push(fv); if (fv > 0) wins++;
    }
    S.total = bN;
    S.base = bN ? { n: bN, wins: bWins, rate: bWins / bN } : null;
    if (vals.length) {
      var sorted = vals.slice().sort(function (a, b) { return a - b; });
      var sum = 0; for (i = 0; i < vals.length; i++) sum += vals[i];
      S.stats = {
        n: vals.length, wins: wins, rate: wins / vals.length,
        mean: sum / vals.length, med: quantile(sorted, 0.5),
        p25: quantile(sorted, 0.25), p75: quantile(sorted, 0.75),
        lo: sorted[0], hi: sorted[sorted.length - 1],
        ci: wilson(wins, vals.length)
      };
    }
  }

  /* ---------------- staleness ---------------- */
  function bizDaysSince(isoDate) {
    try {
      var d = new Date(isoDate + "T00:00:00Z"), now = new Date(), n = 0;
      if (!(d < now)) return 0;
      var cur = new Date(d);
      while (cur < now && n < 40) {
        cur.setUTCDate(cur.getUTCDate() + 1);
        var wd = cur.getUTCDay();
        if (wd !== 0 && wd !== 6) n++;
      }
      return n;
    } catch (e) { return 0; }
  }
  function staleCheck() {
    var el = $("#od-stale");
    if (!el || !S.cat || !S.cat.asof) return;
    var days = bizDaysSince(S.cat.asof);
    if (days > 3) {
      el.innerHTML = "⚠ " + biRaw(
        "Data as of <b>" + esc(S.cat.asof) + "</b> — the nightly build looks stale; odds below may lag the tape.",
        "数据截至 <b>" + esc(S.cat.asof) + "</b> — 夜间构建似乎滞后，以下概率可能落后于最新行情。");
      el.hidden = false;
    } else el.hidden = true;
  }

  /* ---------------- condition rail ---------------- */
  function todayBucket(fid) {
    var m = S.matrix;
    if (!m) return null;
    var col = m.cols && m.cols[fid];
    var v = col ? col[todayIdx()] : null;
    return v == null ? null : v;
  }
  function condValLine(fid) {
    var v = todayBucket(fid);
    if (v == null) return bi("no data today", "今日无数据");
    var lab = bktLabel(fid, v), extra = ["", ""];
    if (fid === "pct_move" && S.matrix) {
      var r = S.matrix.cols.ret_bp && S.matrix.cols.ret_bp[todayIdx()];
      if (r != null) extra = [" · " + fmtBpPct(r), " · " + fmtBpPct(r)];
    } else if (fid === "vix_level") {
      var vx = mraw(["vix", "vix_close", "vix_level_raw"]);
      if (vx != null) extra = [" · VIX " + vx.toFixed(1), " · VIX " + vx.toFixed(1)];
    } else if (fid === "vix_move") {
      var vc = mraw(["vix_chg_pct", "vix_chg", "vix_1d_chg_pct", "vix_move_raw"]);
      if (vc != null) extra = [" · " + (vc > 0 ? "+" : "") + vc.toFixed(1) + "%", " · " + (vc > 0 ? "+" : "") + vc.toFixed(1) + "%"];
    }
    return biRaw(esc(lab[0]) + esc(extra[0]), esc(lab[1]) + esc(extra[1]));
  }
  function renderRail() {
    var body = $("#od-rail-body");
    if (!body) return;
    var html = [], lastGroup = null;
    S.factorOrder.forEach(function (fid) {
      var f = S.F[fid], g = (f && f.group) || "asset";
      if (g !== lastGroup) {
        var gl = GROUPS[g] || [g, g];
        html.push('<div class="od-group">' + bi(gl[0], gl[1]) + "</div>");
        lastGroup = g;
      }
      var na = todayBucket(fid) == null;
      var on = !!S.active[fid] && !na;
      var lab = fLabel(fid);
      var info = (f && (f.desc_en || f.desc_zh))
        ? '<button class="od-info" type="button" data-f="' + esc(fid) + '" aria-label="' + esc(lab[0]) + '" tabindex="0">i</button>'
        : "";
      html.push(
        '<div class="od-cond' + (on ? " on" : "") + (na ? " off-na" : "") + '" data-f="' + esc(fid) + '" role="switch" aria-checked="' + on + '">' +
          '<div class="od-cond-main"><div class="od-cond-name">' + bi(lab[0], lab[1]) + info + "</div>" +
          '<div class="od-cond-val">' + condValLine(fid) + "</div></div>" +
          '<button class="od-switch" type="button" aria-label="' + esc(lab[0]) + '"' + (na ? " disabled" : "") + "></button>" +
        "</div>");
    });
    body.innerHTML = html.join("");
    body.querySelectorAll(".od-cond").forEach(function (row) {
      row.addEventListener("click", function (ev) {
        if (ev.target && ev.target.closest && ev.target.closest(".od-info")) return;
        var fid = row.getAttribute("data-f");
        if (todayBucket(fid) == null) return;
        S.active[fid] = !S.active[fid];
        row.classList.toggle("on", !!S.active[fid]);
        row.setAttribute("aria-checked", !!S.active[fid]);
        recompute();
      });
    });
    renderRailCounts();
  }
  function renderRailCounts() {
    var ac = $("#od-active-count"), mc = $("#od-match-count");
    var k = activeIds().length;
    if (ac) ac.innerHTML = biRaw(k + " active", k + " 项启用");
    if (mc) {
      if (!S.matrix) mc.innerHTML = bi("no history loaded", "未加载历史数据");
      else {
        mc.innerHTML = biRaw(
          "<b>" + S.matches.length + "</b> matching days · " + S.total + " in range",
          "<b>" + S.matches.length + "</b> 个匹配交易日 · 范围内共 " + S.total + " 日");
        /* live match-count pulse on change (motion-gated) */
        if (_lastMatchN != null && _lastMatchN !== S.matches.length && !reduceMotion()) {
          mc.classList.remove("pulse");
          void mc.offsetWidth;               // restart the animation
          mc.classList.add("pulse");
        }
      }
      _lastMatchN = S.matrix ? S.matches.length : null;
    }
  }

  /* ---------------- verdict hero ---------------- */
  function condSummary() {
    var en = [], zh = [];
    activeIds().forEach(function (fid) {
      var fl = fLabel(fid), bl = bktLabel(fid, todayBucket(fid));
      en.push(fl[0] + " " + bl[0]); zh.push(fl[1] + " " + bl[1]);
    });
    return [en.join(" · "), zh.join("、")];
  }
  function renderVerdict() {
    var v = $("#od-verdict");
    if (!v) return;
    if (!S.matrix) {
      prevRate = null;
      v.className = "od-verdict";
      v.innerHTML = '<div class="od-v-sent" style="border-top:0;padding-top:0;margin-top:0">' + bi(
        "No odds history for " + (S.ticker || "this name") + " yet — it may sit outside the v1 universe, or its nightly fetch failed. Pick another ticker above.",
        (S.ticker || "该标的") + " 暂无胜率历史——可能不在 v1 标的池内，或夜间数据抓取失败。请在上方选择其他标的。") + "</div>";
      return;
    }
    var st = S.stats, base = S.base, t = S.ticker;
    var ed = S.matrix.dates[todayIdx()], D = edDate(ed);
    var ret = S.matrix.cols.ret_bp ? S.matrix.cols.ret_bp[todayIdx()] : null;
    var conds = condSummary();
    var hz = HORIZON_TXT[S.horizon], rg = RANGE_TXT[S.range];
    var dateEn = DOW_EN[D.getUTCDay()] + " " + MON_EN[D.getUTCMonth()] + " " + D.getUTCDate();
    var dateZh = D.getUTCFullYear() + "年" + (D.getUTCMonth() + 1) + "月" + D.getUTCDate() + "日（" + DOW_ZH[D.getUTCDay()] + "）";

    /* n<5 → big muted em-dash, no color, no verdict (house honesty rule) */
    if (!st || st.n < 5) {
      var n0 = st ? st.n : 0;
      prevRate = null;
      v.className = "od-verdict";
      v.innerHTML =
        '<div class="od-v-head"><span class="od-eyebrow">' + bi("Historical pattern · insufficient sample", "历史形态 · 样本不足") + "</span></div>" +
        '<div class="od-v-grid"><div class="od-v-main">' +
          '<div class="od-v-rate mut">—</div>' +
          '<div class="od-v-what">' + biRaw("insufficient sample · n=" + n0, "样本不足 · n=" + n0) + "</div>" +
        "</div><div></div></div>" +
        '<p class="od-v-sent">' + bi(
          "Only " + n0 + " similar day(s) in " + rg[0] + " under the current conditions — too few to say anything honest. Loosen a condition, widen the match tolerance, or extend the range.",
          "当前条件下，" + rg[1] + "内仅有 " + n0 + " 个相似交易日——样本太少，无法得出诚实结论。请放宽条件、增大匹配容差或扩大数据范围。") + "</p>";
      return;
    }

    /* honest coloring: edge vs the unconditional base, never the raw rate */
    var edge = base ? (st.rate - base.rate) * 100 : 0;
    var tone = edge >= 5 ? "tone-up" : edge <= -5 ? "tone-down" : "";
    v.className = "od-verdict";

    /* head: eyebrow + low-sample chip + share button */
    var head = '<div class="od-v-head"><span class="od-eyebrow">' +
      bi("Historical pattern · " + st.n + " matching days", "历史形态 · " + st.n + " 个匹配交易日") + "</span>" +
      (st.n < 20 ? '<span class="od-vchip warn">' + bi("low sample · n < 20", "小样本 · n < 20") + "</span>" : "") +
      '<button id="od-share" class="od-share" type="button">⤓ ' + bi("Share card", "分享卡片") + "</button></div>";

    /* left: giant rate + what */
    var main = '<div class="od-v-main">' +
      '<div class="od-v-rate ' + tone + '" id="od-v-num">' + fmtRate(st.rate) + "</div>" +
      '<div class="od-v-what">' + biRaw("closed higher <b>" + esc(hz[0]) + "</b>", "<b>" + esc(hz[1]) + "</b>收高") + "</div>" +
    "</div>";

    /* right: Wilson CI band visual + metric chips */
    var side = "";
    if (st.ci) {
      var ciLo = st.ci[0] * 100, ciHi = st.ci[1] * 100, pt = st.rate * 100;
      var cl = function (p) { return clamp(p, 2, 98).toFixed(2); };
      side +=
        '<div class="od-ci">' +
          '<div class="od-ci-cap"><span class="od-eyebrow">' + bi("95% confidence (Wilson)", "95% 置信区间（Wilson）") + "</span>" +
          '<span class="od-eyebrow">' + (base ? bi("base rate " + fmtRate(base.rate), "基础概率 " + fmtRate(base.rate)) : "") + "</span></div>" +
          '<div class="od-ci-track">' +
            '<span class="od-ci-coin" style="left:50%">' + bi("50% · coin flip", "50% · 抛硬币") + "</span>" +
            '<span class="od-ci-seg ' + tone + '" style="left:' + ciLo.toFixed(2) + "%;width:" + (ciHi - ciLo).toFixed(2) + '%"></span>' +
            '<span class="od-ci-tick" style="left:50%"></span>' +
            '<span class="od-ci-mark ' + tone + '" style="left:' + pt.toFixed(2) + '%"></span>' +
          "</div>" +
          '<div class="od-ci-labs">' +
            '<span style="left:' + cl(ciLo) + '%">' + fmtRate(st.ci[0]) + "</span>" +
            '<span style="left:' + cl(ciHi) + '%">' + fmtRate(st.ci[1]) + "</span>" +
          "</div>" +
        "</div>";
    }
    side +=
      '<div class="od-v-stats">' +
        '<div class="od-v-stat"><span class="k">' + bi("median", "中位数") + '</span><span class="v">' + fmtBpPct(st.med) + "</span></div>" +
        '<div class="od-v-stat"><span class="k">' + bi("closed lower", "收低占比") + '</span><span class="v">' + fmtRate(1 - st.rate) + "</span></div>" +
        '<div class="od-v-stat"><span class="k">' + bi("mean", "均值") + '</span><span class="v">' + fmtBpPct(st.mean) + "</span></div>" +
        '<div class="od-v-stat"><span class="k">' + bi("edge vs base", "相对基础概率") + '</span><span class="v ' + tone + '">' +
          biRaw(esc(fmtSigned(edge)) + " pts", esc(fmtSigned(edge)) + " 点") + "</span></div>" +
      "</div>";

    /* plain-English verdict sentence with inline colored values */
    var toneB = tone === "tone-up" ? "pos" : tone === "tone-down" ? "neg" : "";
    var mvE = "", mvZ = "";
    if (ret != null) {
      var av = Math.abs(ret / 100).toFixed(2) + "%";
      if (ret > 0) { mvE = " rose <b class=\"pos\">" + av + "</b>"; mvZ = "上涨 <b class=\"pos\">" + av + "</b>"; }
      else if (ret < 0) { mvE = " fell <b class=\"neg\">" + av + "</b>"; mvZ = "下跌 <b class=\"neg\">" + av + "</b>"; }
      else { mvE = " closed flat"; mvZ = "持平"; }
    }
    var sentEn = "On " + esc(dateEn) + ", " + esc(t) + mvE + ". Conditions: " + esc(conds[0]) + ". Across <b>" + st.n +
      "</b> similar days in " + esc(rg[0]) + ", price closed higher <b class=\"" + toneB + "\">" + esc(fmtRate(st.rate)) +
      "</b> of the time " + esc(hz[0].replace("the ", "over the ")) + " (median <b>" + esc(fmtBpPct(st.med)) +
      "</b>, base rate " + esc(fmtRate(base ? base.rate : 0)) + ").";
    var sentZh = esc(dateZh) + "，" + esc(t) + " " + mvZ + "。条件：" + esc(conds[1]) + "。在" + esc(rg[1]) + "的 <b>" + st.n +
      "</b> 个相似交易日中，" + esc(hz[1]) + "收高概率为 <b class=\"" + toneB + "\">" + esc(fmtRate(st.rate)) +
      "</b>（中位数 <b>" + esc(fmtBpPct(st.med)) + "</b>，基础概率 " + esc(fmtRate(base ? base.rate : 0)) + "）。";

    v.innerHTML = head +
      '<div class="od-v-grid">' + main + '<div class="od-v-side">' + side + "</div></div>" +
      '<p class="od-v-sent">' + biRaw(sentEn, sentZh) + "</p>" +
      '<p class="od-v-foot">' + bi("Returns open-to-close (next open → horizon close). Descriptive statistics — not investment advice.",
                                    "收益按开盘至收盘计（次日开盘 → 期末收盘）。仅为描述性统计，不构成投资建议。") + "</p>";
    bindShare();
    animateRate($("#od-v-num"), prevRate, st.rate);
    prevRate = st.rate;
  }

  /* hero count-up: ~400ms ease-out from the previous value (motion-gated) */
  function animateRate(el, from, to) {
    if (!el || from == null || from === to) return;
    if (reduceMotion() || !window.requestAnimationFrame) return;
    var t0 = null, dur = 400;
    function frame(ts) {
      if (t0 == null) t0 = ts;
      var k = Math.min(1, (ts - t0) / dur);
      var e2 = 1 - Math.pow(1 - k, 3);
      el.textContent = fmtRate(from + (to - from) * e2);
      if (k < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  /* ---------------- price chart (mm_charts) ---------------- */
  function rangeStartIdx() {
    var m = S.matrix, cutoff = rangeCutoff();
    if (cutoff === -Infinity) return 0;
    var lo = 0, hi = m.dates.length - 1;
    while (lo < hi) { var mid = (lo + hi) >> 1; if (m.dates[mid] < cutoff) lo = mid + 1; else hi = mid; }
    return lo;
  }
  function renderPriceChart(first) {
    var el = $("#od-price-chart");
    if (!el) return;
    try {
      var m = S.matrix;
      if (!m || !window.MMChart) {
        if (priceChart) { priceChart.destroy(); priceChart = null; }
        el.innerHTML = '<div class="od-chart-empty">' + bi("No chart data.", "暂无图表数据。") + "</div>";
        renderVolStrip(null, null);
        return;
      }
      var i0 = rangeStartIdx(), t = todayIdx();
      if (t - i0 < 2) {
        if (priceChart) { priceChart.destroy(); priceChart = null; }
        el.innerHTML = '<div class="od-chart-empty">' + bi("Not enough bars in range.", "范围内数据不足。") + "</div>";
        renderVolStrip(null, null);
        return;
      }
      var pts = [], yfs = [], lo = Infinity, hi = -Infinity, i;
      for (i = i0; i <= t; i++) {
        var c = m.close[i];
        if (c == null) continue;
        var x = edYF(m.dates[i]);
        pts.push({ x: x, y: c, i: i }); yfs.push(x);
        if (c < lo) lo = c; if (c > hi) hi = c;
      }
      var fwd = m.cols[FWD_KEY[S.horizon]] || [];
      var winMk = [], lossMk = [];
      var list = S.matches, step = list.length > 2400 ? Math.ceil(list.length / 2400) : 1;
      for (i = 0; i < list.length; i += step) {
        var d = list[i], cc = m.close[d];
        if (cc == null) continue;
        var mk = { x: edYF(m.dates[d]), y: cc, kind: "dot" };
        (fwd[d] > 0 ? winMk : lossMk).push(mk);
      }
      var pad = (hi - lo) * 0.05 || 1;
      var cUp = cssVar("--od-up", cssVar("--up", "#45b873"));
      var cDn = cssVar("--od-down", cssVar("--down", "#e06464"));
      var spec = {
        xDomain: [pts[0].x, pts[pts.length - 1].x],
        yDomain: [lo - pad, hi + pad],
        series: [
          { id: "px", color: cssVar("--od-chart-line", "#3E4C63"), fill: cssVar("--od-chart-fill", "#131A24"),
            label: S.ticker, hist: pts, width: 1.8 },
          { id: "win", color: cUp, hist: [], markers: winMk },
          { id: "loss", color: cDn, hist: [], markers: lossMk }
        ],
        yTicks: ticksIn(lo - pad, hi + pad, 5).map(function (v) { return { v: v, label: fmtPx(v) }; }),
        padding: { t: 14, r: 14, b: 26, l: 54 },
        animate: !!first && !reduceMotion(),
        tip: function (dS, pt, xVal) {
          var idx = nearestBar(yfs, pts, xVal);
          if (idx == null) return "";
          var bi_ = pts[idx].i;
          var html = '<div class="mmc-tip-h">' + esc(edISO(m.dates[bi_])) + "</div>" +
            '<div class="mmc-tip-z">' + bi("Close", "收盘") + " " + fmtPx(m.close[bi_]) + "</div>";
          var f = fwd[bi_];
          if (f != null) {
            var isM = S.matchedSet && S.matchedSet.has(bi_);
            html += '<div class="mmc-tip-z" style="color:' + (f > 0 ? cUp : cDn) + '">' +
              bi((isM ? "matched · " : "") + "fwd " + HZN_SHORT[S.horizon][0] + " " + fmtBpPct(f),
                 (isM ? "匹配日 · " : "") + "前瞻 " + HZN_SHORT[S.horizon][1] + " " + fmtBpPct(f)) + "</div>";
          }
          var vr = m.cols.vol_rel ? m.cols.vol_rel[bi_] : null;   // v1.1 only
          if (vr != null) html += '<div class="mmc-tip-ph">' +
            bi("rel volume " + (vr / 100).toFixed(2) + "× 20d avg", "相对成交量 " + (vr / 100).toFixed(2) + "×（20日均量）") + "</div>";
          var act = activeIds();
          if (act.length) {
            var bhtml = "";
            for (var a = 0; a < act.length && a < 4; a++) {
              var bl = bktLabel(act[a], (m.cols[act[a]] || [])[bi_]);
              bhtml += '<span class="mmc-tip-bkt">' + bi(bl[0], bl[1]) + "</span>";
            }
            html += "<div>" + bhtml + "</div>";
          }
          return html;
        }
      };
      el.innerHTML = "";
      if (priceChart) { priceChart.destroy(); priceChart = null; }
      priceChart = window.MMChart.create(el, spec);
      renderVolStrip(i0, t);
      var note = $("#od-days-note");
      if (note) {
        var thinned = step > 1 ? bi(" · dots thinned for rendering (1 in " + step + ")", " · 为渲染性能抽样显示（每 " + step + " 个取 1）") : "";
        var dUp = '<span style="color:var(--od-up)">●</span> ', dDn = '<span style="color:var(--od-down)">●</span> ';
        note.innerHTML = biRaw(
          dUp + esc(String(countWins())) + " closed higher · " + dDn + esc(String(S.matches.length - countWins())) + " closed lower " +
            esc(HZN_SHORT[S.horizon][0]) + " forward",
          dUp + esc(String(countWins())) + " 随后收高 · " + dDn + esc(String(S.matches.length - countWins())) + " 随后收低（前瞻 " +
            esc(HZN_SHORT[S.horizon][1]) + "）") + thinned;
      }
    } catch (e) {
      try {
        el.innerHTML = '<div class="od-chart-empty">' + bi("Chart unavailable.", "图表暂不可用。") + "</div>";
        renderVolStrip(null, null);
      } catch (e2) {}
    }
  }

  /* volume substrip: thin rel-vol bars under the price chart, aligned to the
     same x-domain/padding. Reads the v1.1 vol_rel column (vol ÷ SMA20 thru t−1
     × 100); on a v1 matrix the strip simply stays hidden. */
  function renderVolStrip(i0, t) {
    var el = $("#od-vol-strip");
    if (!el) return;
    try {
      el.innerHTML = "";
      var m = S.matrix, vr = m && m.cols ? m.cols.vol_rel : null;
      if (i0 == null || t == null || !vr) { el.hidden = true; return; }
      // Un-hide BEFORE measuring: the template + renderSkeletons ship the strip
      // [hidden] → display:none → clientWidth 0 → 640px viewBox stretched onto a
      // ~1200px container (first-paint x-offset bug). Fallback: the sibling price
      // chart shares this panel's inner width.
      el.hidden = false;
      var pc = $("#od-price-chart");
      var W = el.clientWidth || (pc ? pc.clientWidth : 0) || 640, H = 46;
      var x0 = 54, x1 = W - 14, yTop = 5, yBot = H - 12;
      var X0 = edYF(m.dates[i0]), X1 = edYF(m.dates[t]);
      if (!(X1 > X0)) { el.hidden = true; return; }
      var CAP = 300;   // display cap at 3× the 20d average; tails clamp
      var colV = {}, any = false;
      for (var i = i0; i <= t; i++) {
        var v = vr[i];
        if (v == null) continue;
        var px = Math.round(x0 + (edYF(m.dates[i]) - X0) / (X1 - X0) * (x1 - x0));
        if (px < x0 || px > x1) continue;
        if (colV[px] == null || v > colV[px]) colV[px] = v;   // max per pixel column
        any = true;
      }
      if (!any) { el.hidden = true; return; }
      var svg2 = sv("svg", { viewBox: "0 0 " + W + " " + H }, el);
      var cBar = cssVar("--od-chart-line", "#3E4C63"), cMut = cssVar("--od-mut", "#5C6474");
      var y100 = yBot - 100 / CAP * (yBot - yTop);
      sv("line", { x1: x0, y1: y100, x2: x1, y2: y100, stroke: cMut, "stroke-width": 1, "stroke-dasharray": "2 4", opacity: 0.45 }, svg2);
      for (var k in colV) {
        var vv = Math.min(colV[k], CAP);
        var hgt = Math.max(1, vv / CAP * (yBot - yTop));
        var op = 0.26 + 0.52 * Math.min(1, colV[k] / 250);
        sv("rect", { x: +k, y: yBot - hgt, width: 1, height: hgt, fill: cBar, opacity: op.toFixed(2) }, svg2);
      }
      var lb = sv("text", { x: x0 - 7, y: y100 + 3, "text-anchor": "end", fill: cMut, "font-size": 9 }, svg2);
      lb.textContent = "1×";
      var cap = sv("text", { x: x1, y: H - 2, "text-anchor": "end", fill: cMut, "font-size": 9 }, svg2);
      cap.textContent = isZh() ? "成交量 ÷ 20日均量" : "volume ÷ 20d avg";
    } catch (e) { try { el.hidden = true; } catch (e2) {} }
  }
  function countWins() { return S.stats ? S.stats.wins : 0; }
  function nearestBar(yfs, pts, xVal) {
    if (!yfs.length) return null;
    var lo = 0, hi = yfs.length - 1;
    while (lo < hi) { var mid = (lo + hi) >> 1; if (yfs[mid] < xVal) lo = mid + 1; else hi = mid; }
    if (lo > 0 && Math.abs(yfs[lo - 1] - xVal) < Math.abs(yfs[lo] - xVal)) lo--;
    return lo;
  }
  function ticksIn(lo, hi, target) {
    var raw = (hi - lo) / Math.max(1, target);
    if (!(raw > 0)) return [lo];
    var p = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), mlt = raw / p;
    var step = (mlt <= 1 ? 1 : mlt <= 2 ? 2 : mlt <= 2.5 ? 2.5 : mlt <= 5 ? 5 : 10) * p;
    var out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(+v.toFixed(10));
    return out;
  }

  /* ---------------- matching-days table + CSV ---------------- */
  function renderDaysTable() {
    var tbl = $("#od-days-table");
    if (!tbl) return;
    var m = S.matrix;
    if (!m || !S.matches.length) {
      tbl.innerHTML = "<tbody><tr><td class='mut'>" + bi("No matching days under the current conditions.", "当前条件下没有匹配的交易日。") + "</td></tr></tbody>";
      return;
    }
    var fwd = m.cols[FWD_KEY[S.horizon]] || [];
    var act = activeIds();
    var rows = S.matches.slice();
    var key = S.daysSort.key, dir = S.daysSort.dir;
    rows.sort(function (a, b) {
      var va = key === "fwd" ? fwd[a] : m.dates[a];
      var vb = key === "fwd" ? fwd[b] : m.dates[b];
      return (va - vb) * dir;
    });
    var shown = rows.slice(0, 300);
    var arr = function (k) { return key === k ? '<span class="arr">' + (dir > 0 ? "▲" : "▼") + "</span>" : ""; };
    var html = ["<thead><tr>",
      '<th class="od-sort" data-k="date">' + bi("Date", "日期") + arr("date") + "</th>",
      "<th>" + bi("Conditions on that day", "当日条件") + "</th>",
      '<th class="num">' + bi("Close", "收盘") + "</th>",
      '<th class="num od-sort" data-k="fwd">' + bi("Fwd " + HZN_SHORT[S.horizon][0], "前瞻 " + HZN_SHORT[S.horizon][1]) + arr("fwd") + "</th>",
      "</tr></thead><tbody>"];
    shown.forEach(function (d) {
      var chips = act.map(function (fid) {
        var bl = bktLabel(fid, (m.cols[fid] || [])[d]);
        return '<span class="od-bkt">' + bi(bl[0], bl[1]) + "</span>";
      }).join("");
      var f = fwd[d];
      html.push("<tr><td class='dt mut'>" + esc(edISO(m.dates[d])) + "</td><td>" + (chips || "<span class='mut'>—</span>") + "</td>" +
        "<td class='num'>" + fmtPx(m.close[d]) + "</td>" +
        '<td class="num"><span class="od-fwd ' + (f > 0 ? "pos" : "neg") + '">' + fmtBpPct(f) + "</span></td></tr>");
    });
    html.push("</tbody>");
    tbl.innerHTML = html.join("");
    if (rows.length > shown.length) {
      var note = document.createElement("tfoot");
      note.innerHTML = "<tr><td colspan='4' class='mut' style='font-size:11px'>" +
        biRaw("Showing " + shown.length + " of " + rows.length + " — export CSV for the full set.",
              "显示 " + shown.length + " / " + rows.length + " — 完整数据请导出 CSV。") + "</td></tr>";
      tbl.appendChild(note);
    }
    tbl.querySelectorAll("th.od-sort").forEach(function (th) {
      th.addEventListener("click", function () {
        var k = th.getAttribute("data-k");
        if (S.daysSort.key === k) S.daysSort.dir *= -1;
        else S.daysSort = { key: k, dir: k === "date" ? -1 : -1 };
        renderDaysTable();
      });
    });
  }
  function csvCell(v) { return '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"'; }
  function downloadCSV() {
    try {
      var m = S.matrix;
      if (!m || !S.matches.length) return;
      var act = activeIds();
      var head = ["date", "close", "ret_pct", "gap_pct"];
      act.forEach(function (f) { head.push(f); head.push(f + "_label"); });
      head = head.concat(["fwd1_pct", "fwd5_pct", "fwd20_pct"]);
      var lines = [head.map(csvCell).join(",")];
      var bp = function (v) { return v == null ? "" : (v / 100).toFixed(4); };
      S.matches.forEach(function (d) {
        var row = [edISO(m.dates[d]), m.close[d] == null ? "" : m.close[d],
                   bp(m.cols.ret_bp && m.cols.ret_bp[d]), bp(m.cols.gap_bp && m.cols.gap_bp[d])];
        act.forEach(function (f) {
          var v = (m.cols[f] || [])[d];
          row.push(v == null ? "" : v);
          row.push(bktLabel(f, v)[0]);
        });
        row.push(bp(m.cols.fwd1_bp && m.cols.fwd1_bp[d]));
        row.push(bp(m.cols.fwd5_bp && m.cols.fwd5_bp[d]));
        row.push(bp(m.cols.fwd20_bp && m.cols.fwd20_bp[d]));
        lines.push(row.map(csvCell).join(","));
      });
      var bom = String.fromCharCode(0xFEFF);   // BOM keeps Excel happy with 中文 labels
      var blob = new Blob([bom + lines.join("\n")], { type: "text/csv;charset=utf-8" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "odds_" + S.ticker + "_" + S.horizon + "_" + S.range + ".csv";
      document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 400);
    } catch (e) {}
  }

  /* ---------------- price-path chart (hand-rolled SVG) ---------------- */
  var PATH_K = 20;
  function computePaths() {
    var m = S.matrix, n = m.dates.length;
    var ret = m.cols.ret_bp || [], gap = m.cols.gap_bp || [];
    var byK = []; for (var k = 0; k <= PATH_K; k++) byK.push([]);
    S.matches.forEach(function (d) {
      var g = gap[d + 1];
      if (d + 1 >= n || g == null) return;
      var denom = 1 + g / 1e4, acc = 1;
      byK[0].push(0);
      for (var k = 1; k <= PATH_K; k++) {
        var j = d + k;
        if (j >= n) break;
        var r = ret[j];
        if (r == null) break;
        acc *= (1 + r / 1e4);
        byK[k].push((acc / denom - 1) * 100);   // % vs open[d+1], per spec formula
      }
    });
    var med = [], p25 = [], p75 = [], cnt = [];
    for (var k2 = 0; k2 <= PATH_K; k2++) {
      var v = byK[k2]; cnt.push(v.length);
      if (v.length >= 2) {
        v.sort(function (a, b) { return a - b; });
        med.push(quantile(v, 0.5)); p25.push(quantile(v, 0.25)); p75.push(quantile(v, 0.75));
      } else { med.push(null); p25.push(null); p75.push(null); }
    }
    return { med: med, p25: p25, p75: p75, cnt: cnt };
  }
  function renderPathChart() {
    var el = $("#od-path-chart");
    if (!el) return;
    try {
      el.innerHTML = "";
      if (!S.matrix || S.matches.length < 3) {
        el.innerHTML = '<div class="od-chart-empty">' + bi("Not enough matching days to draw a path.", "匹配交易日不足，无法绘制路径。") + "</div>";
        return;
      }
      var d = computePaths();
      var K = 0; for (var k = 0; k <= PATH_K; k++) if (d.med[k] != null) K = k;
      if (K < 2) {
        el.innerHTML = '<div class="od-chart-empty">' + bi("Not enough forward bars yet.", "前瞻数据不足。") + "</div>";
        return;
      }
      var W = el.clientWidth || 640, H = el.clientHeight || 280;
      var x0 = 54, x1 = W - 14, y0t = 12, y1b = H - 26;
      var lo = 0, hi = 0, i;
      for (i = 0; i <= K; i++) {
        if (d.p25[i] != null && d.p25[i] < lo) lo = d.p25[i];
        if (d.p75[i] != null && d.p75[i] > hi) hi = d.p75[i];
      }
      var padY = (hi - lo) * 0.1 || 0.5; lo -= padY; hi += padY;
      var sx = function (k2) { return x0 + k2 / K * (x1 - x0); };
      var sy = function (v) { return y1b - (v - lo) / (hi - lo) * (y1b - y0t); };
      var svg = sv("svg", { viewBox: "0 0 " + W + " " + H }, el);
      var cLine = cssVar("--od-div", "#161C27"), cMut = cssVar("--od-mut", "#5C6474");
      var cLink = cssVar("--link", "#7aa7e0"), cText = cssVar("--od-text", "#E7EBF2");
      ticksIn(lo, hi, 5).forEach(function (v) {
        var yy = sy(v);
        sv("line", { x1: x0, y1: yy, x2: x1, y2: yy, stroke: cLine, "stroke-width": 1, opacity: 0.5 }, svg);
        var tx = sv("text", { x: x0 - 7, y: yy + 3, "text-anchor": "end", fill: cMut, "font-size": 10 }, svg);
        tx.textContent = (v > 0 ? "+" : "") + v.toFixed(Math.abs(hi - lo) < 3 ? 1 : 0) + "%";
      });
      for (i = 0; i <= K; i += 5) {
        var xx = sx(i);
        sv("line", { x1: xx, y1: y1b, x2: xx, y2: y1b + 4, stroke: cLine }, svg);
        var tl = sv("text", { x: xx, y: y1b + 16, "text-anchor": "middle", fill: cMut, "font-size": 10 }, svg);
        tl.textContent = "D+" + i;
      }
      var zy = sy(0);
      sv("line", { x1: x0, y1: zy, x2: x1, y2: zy, stroke: cMut, "stroke-width": 1, "stroke-dasharray": "2 4", opacity: 0.6 }, svg);
      /* p25–75 band */
      var up = "M", dn = "";
      for (i = 0; i <= K; i++) up += (i ? "L" : "") + sx(i).toFixed(1) + "," + sy(d.p75[i] == null ? 0 : d.p75[i]).toFixed(1) + " ";
      for (i = K; i >= 0; i--) dn += "L" + sx(i).toFixed(1) + "," + sy(d.p25[i] == null ? 0 : d.p25[i]).toFixed(1) + " ";
      sv("path", { d: up + dn + "Z", fill: cLink, opacity: 0.13, stroke: "none" }, svg);
      /* median line */
      var md = "M";
      for (i = 0; i <= K; i++) md += (i ? "L" : "") + sx(i).toFixed(1) + "," + sy(d.med[i]).toFixed(1) + " ";
      sv("path", { d: md, fill: "none", stroke: cLink, "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" }, svg);
      var endT = sv("text", { x: x1 - 2, y: sy(d.med[K]) - 7, "text-anchor": "end", fill: cText, "font-size": 11, "font-weight": 700 }, svg);
      endT.textContent = (d.med[K] > 0 ? "+" : "") + d.med[K].toFixed(2) + "%";
      /* hover */
      var tip = document.createElement("div"); tip.className = "od-ctip"; el.appendChild(tip);
      var guide = sv("line", { x1: 0, y1: y0t, x2: 0, y2: y1b, stroke: cText, "stroke-width": 1, opacity: 0 }, svg);
      var dot = sv("circle", { r: 3.6, fill: cLink, stroke: cssVar("--od-panel", "#0E1219"), "stroke-width": 1.5, opacity: 0 }, svg);
      var cap = sv("rect", { x: x0, y: y0t, width: x1 - x0, height: y1b - y0t, fill: "transparent", style: "cursor:crosshair" }, svg);
      cap.addEventListener("mousemove", function (ev) {
        var r = svg.getBoundingClientRect();
        var px = (ev.clientX - r.left) * (W / r.width);
        var k2 = clamp(Math.round((px - x0) / (x1 - x0) * K), 0, K);
        if (d.med[k2] == null) return;
        guide.setAttribute("x1", sx(k2)); guide.setAttribute("x2", sx(k2)); guide.setAttribute("opacity", 0.25);
        dot.setAttribute("cx", sx(k2)); dot.setAttribute("cy", sy(d.med[k2])); dot.setAttribute("opacity", 1);
        tip.innerHTML = '<div class="mmc-tip-h">D+' + k2 + "</div>" +
          '<div class="mmc-tip-z">' + bi("median ", "中位数 ") + (d.med[k2] > 0 ? "+" : "") + d.med[k2].toFixed(2) + "%</div>" +
          '<div class="mmc-tip-ph">p25 ' + d.p25[k2].toFixed(2) + "% · p75 " + d.p75[k2].toFixed(2) + "% · n=" + d.cnt[k2] + "</div>";
        tip.style.opacity = 1;
        var tw = tip.offsetWidth, sxpx = sx(k2) / (W / r.width);
        tip.style.transform = "translate(" + clamp(sxpx + 14, 4, r.width - tw - 4) + "px," + 18 + "px)";
      });
      cap.addEventListener("mouseleave", function () { tip.style.opacity = 0; guide.setAttribute("opacity", 0); dot.setAttribute("opacity", 0); });
      var note = $("#od-path-note");
      if (note) note.innerHTML = biRaw(
        "n=" + d.cnt[1] + " at D+1 → " + d.cnt[K] + " at D+" + K + " (recent matches have fewer forward bars). Paths rebuilt from daily returns vs the entry open.",
        "D+1 时 n=" + d.cnt[1] + " → D+" + K + " 时 n=" + d.cnt[K] + "（较新的匹配日前瞻数据较少）。路径按相对入场开盘价的日收益重建。");
    } catch (e) {
      try { el.innerHTML = '<div class="od-chart-empty">' + bi("Chart unavailable.", "图表暂不可用。") + "</div>"; } catch (e2) {}
    }
  }

  /* ---------------- returns histogram + strip ---------------- */
  function renderReturns() {
    var el = $("#od-hist-chart"), stripEl = $("#od-strip-chart");
    if (!el) return;
    try {
      el.innerHTML = ""; if (stripEl) stripEl.innerHTML = "";
      var m = S.matrix;
      if (!m || S.matches.length < 3) {
        el.innerHTML = '<div class="od-chart-empty">' + bi("Not enough matching days for a distribution.", "匹配交易日不足，无法绘制分布。") + "</div>";
        return;
      }
      var fwd = m.cols[FWD_KEY[S.horizon]] || [];
      var vals = S.matches.map(function (d) { return fwd[d] / 100; });
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
      if (lo === hi) { lo -= 0.5; hi += 0.5; }
      var rawStep = (hi - lo) / 18;
      var p = Math.pow(10, Math.floor(Math.log(rawStep) / Math.LN10)), mlt = rawStep / p;
      var step = (mlt <= 1 ? 1 : mlt <= 2 ? 2 : mlt <= 2.5 ? 2.5 : mlt <= 5 ? 5 : 10) * p;
      var b0 = Math.floor(lo / step) * step;
      var nb = Math.min(48, Math.max(1, Math.ceil((hi - b0) / step + 1e-9)));
      var counts = new Array(nb).fill(0);
      vals.forEach(function (v) { counts[clamp(Math.floor((v - b0) / step), 0, nb - 1)]++; });
      var maxC = Math.max.apply(null, counts);
      var W = el.clientWidth || 640, H = el.clientHeight || 250;
      var x0 = 44, x1 = W - 14, y0t = 12, y1b = H - 26;
      var sx = function (v) { return x0 + (v - b0) / (nb * step) * (x1 - x0); };
      var syC = function (c) { return y1b - c / maxC * (y1b - y0t - 8); };
      var svg = sv("svg", { viewBox: "0 0 " + W + " " + H }, el);
      var cLine = cssVar("--od-div", "#161C27"), cMut = cssVar("--od-mut", "#5C6474");
      var cUp = cssVar("--od-up", cssVar("--up", "#45b873")), cDn = cssVar("--od-down", cssVar("--down", "#e06464")), cText = cssVar("--od-text", "#E7EBF2");
      ticksIn(0, maxC, 4).forEach(function (c) {
        if (c === 0 || c !== Math.round(c)) return;
        var yy = syC(c);
        sv("line", { x1: x0, y1: yy, x2: x1, y2: yy, stroke: cLine, "stroke-width": 1, opacity: 0.5 }, svg);
        var tx = sv("text", { x: x0 - 7, y: yy + 3, "text-anchor": "end", fill: cMut, "font-size": 10 }, svg);
        tx.textContent = String(c);
      });
      for (var i = 0; i < nb; i++) {
        var bl = b0 + i * step, br = bl + step, cx = (bl + br) / 2;
        var xL = sx(bl), xR = sx(br), yT = syC(counts[i]);
        var bar = sv("rect", { x: xL + 1, y: yT, width: Math.max(1, xR - xL - 2), height: Math.max(0, y1b - yT),
          rx: 2, fill: cx < 0 ? cDn : cUp, opacity: 0.8 }, svg);
        var ti = sv("title", null, bar);
        ti.textContent = counts[i] + " × " + (bl > 0 ? "+" : "") + bl.toFixed(2) + "% … " + (br > 0 ? "+" : "") + br.toFixed(2) + "%";
      }
      ticksIn(b0, b0 + nb * step, 7).forEach(function (v) {
        var xx = sx(v);
        if (xx < x0 - 1 || xx > x1 + 1) return;
        sv("line", { x1: xx, y1: y1b, x2: xx, y2: y1b + 4, stroke: cLine }, svg);
        var tl = sv("text", { x: xx, y: y1b + 16, "text-anchor": "middle", fill: cMut, "font-size": 10 }, svg);
        tl.textContent = (v > 0 ? "+" : "") + v.toFixed(step < 0.5 ? 1 : 0) + "%";
      });
      /* zero + median markers */
      if (b0 < 0 && b0 + nb * step > 0)
        sv("line", { x1: sx(0), y1: y0t, x2: sx(0), y2: y1b, stroke: cMut, "stroke-width": 1, "stroke-dasharray": "2 4", opacity: 0.6 }, svg);
      var med = S.stats ? S.stats.med / 100 : null;
      if (med != null) {
        sv("line", { x1: sx(med), y1: y0t, x2: sx(med), y2: y1b, stroke: cText, "stroke-width": 1.4, opacity: 0.75 }, svg);
        var mt = sv("text", { x: sx(med) + 5, y: y0t + 9, fill: cText, "font-size": 10, "font-weight": 700 }, svg);
        mt.textContent = (med > 0 ? "+" : "") + med.toFixed(2) + "%";
      }
      /* per-instance tick strip */
      if (stripEl) {
        var Ws = stripEl.clientWidth || W, Hs = 26;
        var svg2 = sv("svg", { viewBox: "0 0 " + Ws + " " + Hs }, stripEl);
        var sxs = function (v) { return x0 / W * Ws + (v - b0) / (nb * step) * ((x1 - x0) / W * Ws); };
        vals.forEach(function (v) {
          sv("line", { x1: sxs(v), y1: 5, x2: sxs(v), y2: 21, stroke: v > 0 ? cUp : cDn, "stroke-width": 1, opacity: 0.4 }, svg2);
        });
      }
      var note = $("#od-ret-note");
      if (note && S.stats) note.innerHTML = biRaw(
        "n=" + S.stats.n + " · min " + esc(fmtBpPct(S.stats.lo)) + " · max " + esc(fmtBpPct(S.stats.hi)) +
          " · solid line = median, dashed = zero",
        "n=" + S.stats.n + " · 最小 " + esc(fmtBpPct(S.stats.lo)) + " · 最大 " + esc(fmtBpPct(S.stats.hi)) +
          " · 实线 = 中位数，虚线 = 零");
    } catch (e) {
      try { el.innerHTML = '<div class="od-chart-empty">' + bi("Chart unavailable.", "图表暂不可用。") + "</div>"; } catch (e2) {}
    }
  }

  /* ---------------- Factor Match tab ---------------- */
  function ensureFM() {
    if (S.fm) return Promise.resolve(S.fm);
    if (S.fmTried) return Promise.resolve(null);
    return fetchJSON("oddsdata/factor_match.json").then(function (j) {
      S.fmTried = true;
      if (!j || j.schema !== "odds_factor_match.v1" || !Array.isArray(j.rows)) return null;
      S.fm = j;
      S.fmMinN = j.min_n != null ? j.min_n : 10;
      S.fmTpl = (j.templates && j.templates.length) ? j.templates[0].id : null;
      var mn = $("#od-fm-minn"); if (mn) mn.value = S.fmMinN;
      var sel = $("#od-fm-sector");
      if (sel) {
        var secs = {};
        j.rows.forEach(function (r) { if (r.sec) secs[r.sec] = 1; });
        var opts = ['<option value="">' + (isZh() ? "全部板块" : "All sectors") + "</option>"];
        Object.keys(secs).sort().forEach(function (s2) { opts.push('<option value="' + esc(s2) + '">' + esc(s2) + "</option>"); });
        sel.innerHTML = opts.join("");
      }
      return j;
    });
  }
  function fmMetric(row, h, idx) {
    var res = row.res && row.res[S.fmTpl];
    var a = res && res[h];
    if (!a || a[0] == null) return null;
    return a[idx];
  }
  function fmWin(row, h) {
    var w = fmMetric(row, h, 1);
    if (w == null) return null;
    return w > 1.5 ? w / 100 : w;   // tolerate percent-encoded win rates
  }
  function renderFM() {
    var tbl = $("#od-fm-table"), tplBox = $("#od-fm-templates"), mkt = $("#od-fm-market"), note = $("#od-fm-note");
    if (!tbl) return;
    ensureFM().then(function (fm) {
      try {
        if (!fm) {
          tbl.innerHTML = "";
          if (mkt) mkt.innerHTML = "";
          if (note) note.innerHTML = "";
          if (tplBox) tplBox.innerHTML = "";
          tbl.innerHTML = "<tbody><tr><td class='mut'>" + bi("Screener data unavailable — the nightly build will refresh it.", "筛选数据暂不可用——夜间构建会自动刷新。") + "</td></tr></tbody>";
          return;
        }
        /* template chips */
        if (tplBox) {
          tplBox.innerHTML = (fm.templates || []).map(function (tp) {
            return '<button type="button" class="od-tplchip' + (tp.id === S.fmTpl ? " on" : "") + '" data-tpl="' + esc(tp.id) + '">' +
              bi(tp.label_en || tp.id, tp.label_zh || tp.label_en || tp.id) + "</button>";
          }).join("");
          tplBox.querySelectorAll(".od-tplchip").forEach(function (ch) {
            ch.addEventListener("click", function () { S.fmTpl = ch.getAttribute("data-tpl"); renderFM(); });
          });
        }
        /* shared market context line */
        if (mkt) {
          var bits_en = [], bits_zh = [];
          ["mkt_trend", "vix_level", "quad"].forEach(function (fid) {
            var v = fm.market && typeof fm.market[fid] === "number" ? fm.market[fid] : null;
            if (v == null) return;
            var fl = fLabel(fid), blb = bktLabel(fid, v);
            bits_en.push(fl[0] + " " + blb[0]); bits_zh.push(fl[1] + " " + blb[1]);
          });
          mkt.innerHTML = biRaw(
            esc("As of " + (fm.asof || "—") + (bits_en.length ? " · shared context: " + bits_en.join(" · ") : "") + " · range " + (fm.range || "20y")),
            esc("截至 " + (fm.asof || "—") + (bits_zh.length ? " · 共享市场环境：" + bits_zh.join("、") : "") + " · 范围 " + (fm.range || "20y")));
        }
        var horizons = fm.horizons && fm.horizons.length ? fm.horizons : ["1d", "5d", "20d"];
        var tpl = (fm.templates || []).filter(function (tp) { return tp.id === S.fmTpl; })[0] || null;
        /* rows: filter + sort */
        var rows = fm.rows.filter(function (r) { return !S.fmSector || r.sec === S.fmSector; });
        var key = S.fmSort.key, dir = S.fmSort.dir;
        function sortVal(r) {
          if (key === "t") return r.t || "";
          if (key === "sec") return r.sec || "";
          var kk = key.split(":"), h = kk[0], met = kk[1];
          var n = fmMetric(r, h, 0);
          if (n == null || n < S.fmMinN) return null;   // sink below-floor rows
          if (met === "n") return n;
          if (met === "win") return fmWin(r, h);
          return fmMetric(r, h, 2);
        }
        rows.sort(function (a, b) {
          var va = sortVal(a), vb = sortVal(b);
          if (va == null && vb == null) return 0;
          if (va == null) return 1;
          if (vb == null) return -1;
          if (typeof va === "string") return va < vb ? -dir : va > vb ? dir : 0;
          return (vb - va) * (dir > 0 ? -1 : 1);
        });
        /* header */
        var arr = function (k) { return key === k ? '<span class="arr">' + (dir > 0 ? "▲" : "▼") + "</span>" : ""; };
        var h1 = ['<thead><tr>',
          '<th rowspan="2" class="od-sort" data-k="t">' + bi("Symbol", "标的") + arr("t") + "</th>",
          '<th rowspan="2" class="od-sort" data-k="sec">' + bi("Sector", "板块") + arr("sec") + "</th>",
          '<th rowspan="2">' + bi("Today's conditions", "今日条件") + "</th>"];
        horizons.forEach(function (h) {
          h1.push('<th colspan="3" class="hgrp hsep">' + bi(HZN_SHORT[h] ? HZN_SHORT[h][0] : h, HZN_SHORT[h] ? HZN_SHORT[h][1] : h) + "</th>");
        });
        h1.push("</tr><tr>");
        horizons.forEach(function (h) {
          h1.push('<th class="num od-sort hsep" data-k="' + h + ':n">n' + arr(h + ":n") + "</th>");
          h1.push('<th class="num od-sort" data-k="' + h + ':win">' + bi("win", "胜率") + arr(h + ":win") + "</th>");
          h1.push('<th class="num od-sort" data-k="' + h + ':med">' + bi("med", "中位") + arr(h + ":med") + "</th>");
        });
        h1.push("</tr></thead><tbody>");
        /* body */
        rows.forEach(function (r) {
          var condEn = [], condZh = [];
          if (tpl && tpl.factors && r.cur) {
            tpl.factors.forEach(function (fid) {
              var v = r.cur[fid];
              if (v == null) return;
              var blb = bktLabel(fid, v);
              condEn.push(blb[0]); condZh.push(blb[1]);
            });
          }
          var cells = ['<tr data-t="' + esc(r.t) + '">',
            '<td><span class="od-fm-tk">' + logoImg(r.t, "od-logo") + esc(r.t) + "</span>" +
              (r.name ? ' <span class="mut" style="font-size:10.5px">' + esc(String(r.name).slice(0, 22)) + "</span>" : "") + "</td>",
            '<td class="mut">' + esc(r.sec || "—") + "</td>",
            '<td class="od-fm-cond">' + biRaw(esc(condEn.join(" · ") || "—"), esc(condZh.join("、") || "—")) + "</td>"];
          horizons.forEach(function (h) {
            var n = fmMetric(r, h, 0), w = fmWin(r, h), md = fmMetric(r, h, 2);
            if (n == null) { cells.push('<td class="num lown hsep">—</td><td class="num lown">—</td><td class="num lown">—</td>'); return; }
            var below = n < S.fmMinN;
            /* heat pill: tint scales with |edge vs 50|; neutral inset pill when
               |edge| < 2 pts or below the sample floor (honest coloring) */
            var pill = "—";
            if (w != null) {
              var edgePts = (w - 0.5) * 100, attr = "";
              if (!below && Math.abs(edgePts) >= 2) {
                var vn = edgePts > 0 ? "--od-up" : "--od-down";
                var mag = Math.min(30, 6 + Math.abs(edgePts) * 1.1).toFixed(0);
                attr = ' style="background:color-mix(in srgb, var(' + vn + ") " + mag + '%, var(--od-inset));color:var(' + vn + ')"';
              }
              pill = '<span class="od-heat"' + attr + ">" + (w * 100).toFixed(0) + "%</span>";
            }
            cells.push('<td class="num hsep' + (below ? " lown" : "") + '">' + n + "</td>");
            cells.push('<td class="num' + (below ? " lown" : "") + '">' + pill + "</td>");
            cells.push('<td class="num' + (below ? " lown" : "") + '">' + (md == null ? "—" : fmtBpPct(md)) + "</td>");
          });
          cells.push("</tr>");
          h1.push(cells.join(""));
        });
        h1.push("</tbody>");
        tbl.innerHTML = h1.join("");
        tbl.querySelectorAll("th.od-sort").forEach(function (th) {
          th.addEventListener("click", function () {
            var k = th.getAttribute("data-k");
            if (S.fmSort.key === k) S.fmSort.dir *= -1;
            else S.fmSort = { key: k, dir: (k === "t" || k === "sec") ? 1 : -1 };
            renderFM();
          });
        });
        tbl.querySelectorAll("tbody tr[data-t]").forEach(function (tr) {
          tr.addEventListener("click", function () {
            var t = tr.getAttribute("data-t");
            if (!t) return;
            setTab("days");
            loadTicker(t);
            var top = $("#od-top") || $(".od-top");
            if (top && top.scrollIntoView) top.scrollIntoView({ behavior: "smooth", block: "start" });
          });
        });
        if (note) note.innerHTML = biRaw(
          esc("Each symbol vs its own history under today's shared market context. Heat tint = win rate vs 50%, shown only when n ≥ " + S.fmMinN + "; grey = below the sample floor. Click a row to open it in the Analyzer."),
          esc("每个标的与其自身历史比较，共享今日市场环境。色块 = 胜率相对 50% 的偏离，仅在 n ≥ " + S.fmMinN + " 时显示；灰色 = 样本不足。点击任意行可在分析器中打开该标的。"));
      } catch (e) {
        try { tbl.innerHTML = "<tbody><tr><td class='mut'>" + bi("Screener unavailable.", "筛选暂不可用。") + "</td></tr></tbody>"; } catch (e2) {}
      }
    });
  }

  /* ---------------- typeahead ---------------- */
  function initTypeahead() {
    var inp = $("#od-tk-input"), box = $("#od-tk-sugg");
    if (!inp || !box) return;
    var sel = -1, items = [];
    function hide() { box.hidden = true; sel = -1; }
    function show(list) {
      items = list;
      if (!list.length) {
        box.innerHTML = '<div class="empty">' + bi("No match in the odds universe.", "胜率标的池中无匹配。") + "</div>";
        box.hidden = false; return;
      }
      box.innerHTML = list.map(function (u, i) {
        return '<div class="row' + (i === sel ? " sel" : "") + '" data-t="' + esc(u.t) + '">' +
          logoImg(u.t, "od-logo") + "<b>" + esc(u.t) + "</b><small>" + esc(u.name || "") + "</small>" +
          (u.sector ? '<span class="sec">' + esc(u.sector) + "</span>" : "") + "</div>";
      }).join("");
      box.hidden = false;
      box.querySelectorAll(".row").forEach(function (r) {
        r.addEventListener("mousedown", function (ev) {   // mousedown beats input blur
          ev.preventDefault();
          pick(r.getAttribute("data-t"));
        });
      });
    }
    function pick(t) {
      hide();
      inp.value = t;
      inp.blur();
      loadTicker(t);
    }
    function query() {
      var q = inp.value.trim().toUpperCase();
      var uni = (S.cat && S.cat.universe) || [];
      if (!q) { show(uni.slice(0, 12)); return; }
      var pre = [], sub = [];
      for (var i = 0; i < uni.length && pre.length + sub.length < 60; i++) {
        var u = uni[i], tt = String(u.t || "").toUpperCase();
        if (tt.indexOf(q) === 0) pre.push(u);
        else if (tt.indexOf(q) > 0 || String(u.name || "").toUpperCase().indexOf(q) >= 0) sub.push(u);
      }
      show(pre.concat(sub).slice(0, 12));
    }
    inp.addEventListener("input", function () { sel = -1; query(); });
    inp.addEventListener("focus", function () { inp.select(); query(); });
    inp.addEventListener("blur", function () {
      setTimeout(function () {
        hide();
        /* abandoned partial query — restore the loaded ticker so the box never lies */
        if (S.ticker && inp.value.trim().toUpperCase() !== S.ticker) inp.value = S.ticker;
      }, 140);
    });
    inp.addEventListener("keydown", function (ev) {
      if (box.hidden) return;
      var rows = box.querySelectorAll(".row");
      if (ev.key === "ArrowDown") { sel = Math.min(rows.length - 1, sel + 1); }
      else if (ev.key === "ArrowUp") { sel = Math.max(0, sel - 1); }
      else if (ev.key === "Enter") {
        var t = (rows[Math.max(0, sel)] || rows[0]);
        if (t) pick(t.getAttribute("data-t"));
        ev.preventDefault(); return;
      } else if (ev.key === "Escape") { hide(); return; }
      else return;
      ev.preventDefault();
      rows.forEach(function (r, i) { r.classList.toggle("sel", i === sel); });
      if (rows[sel] && rows[sel].scrollIntoView) rows[sel].scrollIntoView({ block: "nearest" });
    });
  }

  /* ---------------- ticker load ---------------- */
  function updateTopChrome() {
    var logo = $("#od-logo"), chip = $("#od-move-chip");
    var tkEl = $("#od-ident-tk"), nmEl = $("#od-ident-name"), subEl = $("#od-ident-sub");
    if (logo) {
      if (S.ticker) {
        logo.onerror = function () { logo.hidden = true; };
        logo.hidden = false;
        logo.src = LOGO_CDN + S.ticker + ".png";
      } else logo.hidden = true;
    }
    if (tkEl) tkEl.textContent = S.ticker || "—";
    if (nmEl) {
      var u = ((S.cat && S.cat.universe) || []).filter(function (x) { return x && x.t === S.ticker; })[0];
      nmEl.textContent = (u && u.name) ? u.name : "";
    }
    if (chip) {
      var r = S.matrix && S.matrix.cols.ret_bp ? S.matrix.cols.ret_bp[todayIdx()] : null;
      if (r == null) { chip.hidden = true; }
      else {
        chip.hidden = false;
        chip.className = "od-move " + (r > 0 ? "pos" : r < 0 ? "neg" : "");
        chip.textContent = fmtBpPct(r);
      }
    }
    if (subEl) {
      if (!S.matrix) subEl.innerHTML = "";
      else {
        var D = edDate(S.matrix.dates[todayIdx()]);
        var dEn = DOW_EN[D.getUTCDay()] + ", " + MON_EN[D.getUTCMonth()] + " " + D.getUTCDate() + " " + D.getUTCFullYear();
        var dZh = D.getUTCFullYear() + "年" + (D.getUTCMonth() + 1) + "月" + D.getUTCDate() + "日（" + DOW_ZH[D.getUTCDay()] + "）";
        var tb = todayBucket("mkt_trend");
        var rgm = tb == null ? null : bktLabel("mkt_trend", tb);
        subEl.innerHTML = biRaw(
          esc(dEn + " · close" + (rgm ? " · " + rgm[0] + " regime" : "")),
          esc(dZh + " · 收盘" + (rgm ? " · " + rgm[1] : "")));
      }
    }
  }
  /* skeleton loading blocks while a matrix fetches (pulse is motion-gated in CSS) */
  function renderSkeletons() {
    var v = $("#od-verdict");
    if (v) v.innerHTML =
      '<div class="od-v-head"><div class="od-skel-block" style="width:210px;height:12px"></div></div>' +
      '<div class="od-v-grid"><div class="od-v-main">' +
        '<div class="od-skel-block" style="width:190px;height:56px"></div>' +
        '<div class="od-skel-block" style="width:150px;height:12px;margin-top:12px"></div></div>' +
      '<div class="od-v-side"><div class="od-skel-block" style="height:8px;border-radius:99px;margin-top:14px"></div>' +
        '<div class="od-skel-row" style="margin-top:22px">' +
          '<div class="od-skel-block" style="width:62px;height:28px"></div>' +
          '<div class="od-skel-block" style="width:62px;height:28px"></div>' +
          '<div class="od-skel-block" style="width:62px;height:28px"></div>' +
          '<div class="od-skel-block" style="width:62px;height:28px"></div>' +
        "</div></div></div>" +
      '<div class="od-skel-block" style="height:12px;margin-top:18px"></div>';
    var pc = $("#od-price-chart");
    if (pc) {
      if (priceChart) { try { priceChart.destroy(); } catch (e) {} priceChart = null; }
      pc.innerHTML = '<div class="od-skel-block" style="position:absolute;left:0;right:0;top:6px;bottom:6px"></div>';
    }
    var vs = $("#od-vol-strip"); if (vs) vs.hidden = true;
    var tbl = $("#od-days-table");
    if (tbl) tbl.innerHTML = '<tbody><tr><td style="border-bottom:none">' +
      '<div class="od-skel-block" style="height:14px;margin:4px 0"></div>' +
      '<div class="od-skel-block" style="height:14px;margin:10px 0"></div>' +
      '<div class="od-skel-block" style="height:14px;margin:10px 0 4px"></div></td></tr></tbody>';
  }
  function loadTicker(t) {
    if (!t) return;
    S.ticker = t;
    var seq = ++S.loadSeq;
    var inp = $("#od-tk-input"); if (inp) inp.value = t;
    renderSkeletons();
    var base = (window.DATA_BASE || "");
    if (base && base.slice(-1) !== "/") base += "/";
    fetchJSON(base + "oddsmatrix/" + encodeURIComponent(t) + ".json").then(function (m) {
      if (seq !== S.loadSeq) return;   // a newer pick superseded this load
      var okShape = m && (m.schema === "odds_matrix.v1" || m.schema === "odds_matrix.v1.1") &&
        Array.isArray(m.dates) && m.dates.length > 1 &&
        Array.isArray(m.close) && m.close.length === m.dates.length && m.cols;
      S.matrix = okShape ? m : null;
      if (S.matrix) {
        /* deactivate conditions with no value today — null can never match */
        S.factorOrder.forEach(function (fid) {
          if (S.active[fid] && todayBucket(fid) == null) S.active[fid] = false;
        });
      }
      updateTopChrome();
      renderRail();
      recompute(true);
    });
  }

  /* ---------------- recompute + render router ---------------- */
  function recompute(firstChart) {
    try { computeAll(); } catch (e) { S.matches = []; S.stats = null; }
    renderRailCounts();
    renderVerdict();
    renderActivePane(firstChart);
  }
  function renderActivePane(firstChart) {
    try {
      if (S.tab === "days") { renderPriceChart(firstChart); renderDaysTable(); }
      else if (S.tab === "path") renderPathChart();
      else if (S.tab === "returns") renderReturns();
      else if (S.tab === "fm") renderFM();
    } catch (e) {}
  }

  /* ---------------- tabs + deep links ---------------- */
  var TABS = ["days", "path", "returns", "fm"];
  function syncTabInk() {
    var ink = $("#od-tab-ink");
    if (!ink) return;
    var on = document.querySelector("#od-tabs .tabbtn.on");
    if (!on) { ink.style.width = "0"; return; }
    ink.style.left = on.offsetLeft + "px";
    ink.style.width = on.offsetWidth + "px";
  }
  function setTab(tab, silent) {
    if (TABS.indexOf(tab) < 0) tab = "days";
    S.tab = tab;
    var layout = $("#od-layout");
    if (layout) layout.classList.toggle("fm-mode", tab === "fm");
    document.querySelectorAll("#od-tabs .tabbtn").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-tab") === tab);
    });
    TABS.forEach(function (tb) {
      var pane = $("#od-pane-" + tb);
      if (pane) pane.hidden = tb !== tab;
    });
    var csv = $("#od-csv");
    if (csv) csv.hidden = tab !== "days";   // CSV exports the matching-days set
    syncTabInk();
    if (!silent) { try { history.replaceState(null, "", "#" + tab); } catch (e) { location.hash = tab; } }
    renderActivePane();
  }
  function initTabs() {
    document.querySelectorAll("#od-tabs .tabbtn").forEach(function (b) {
      b.addEventListener("click", function () { setTab(b.getAttribute("data-tab")); });
    });
    window.addEventListener("hashchange", function () {
      var h = (location.hash || "").replace("#", "");
      if (TABS.indexOf(h) >= 0 && h !== S.tab) setTab(h, true);
    });
    window.addEventListener("resize", debounce(syncTabInk, 120));
    var h0 = (location.hash || "").replace("#", "");
    setTab(TABS.indexOf(h0) >= 0 ? h0 : "days", true);
    setTimeout(syncTabInk, 350);   // re-measure once webfonts settle
  }

  /* ---------------- controls: labelled chip + dropdown menu ---------------- */
  var _odMenus = [];
  function closeMenus() { _odMenus.forEach(function (fn) { fn(); }); }
  function initChipMenu(rootSel, get, set) {
    var root = $(rootSel);
    if (!root) return;
    var btn = root.querySelector(".od-chipbtn"), menu = root.querySelector(".od-menu"), val = root.querySelector(".od-ctrl-v");
    if (!btn || !menu) return;
    function paint() {
      var cur = String(get());
      menu.querySelectorAll(".od-opt").forEach(function (o) {
        var on = o.getAttribute("data-v") === cur;
        o.classList.toggle("on", on);
        if (on && val) val.innerHTML = o.innerHTML;   // paired l-en/l-zh spans ride along
      });
    }
    function close() { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); }
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var wasHidden = menu.hidden;
      closeMenus();
      if (wasHidden) { menu.hidden = false; btn.setAttribute("aria-expanded", "true"); }
    });
    menu.querySelectorAll(".od-opt").forEach(function (o) {
      o.addEventListener("click", function (ev) {
        ev.stopPropagation();
        set(o.getAttribute("data-v"));
        paint();
        close();
        recompute();
      });
    });
    paint();
    _odMenus.push(close);
  }
  function initControls() {
    initChipMenu("#od-ctl-horizon", function () { return S.horizon; }, function (v) { S.horizon = v; });
    initChipMenu("#od-ctl-range", function () { return S.range; }, function (v) { S.range = v; });
    initChipMenu("#od-ctl-tol", function () { return String(S.tol); }, function (v) { S.tol = parseInt(v, 10) || 0; });
    document.addEventListener("click", closeMenus);
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") closeMenus(); });
    var csv = $("#od-csv");
    if (csv) csv.addEventListener("click", downloadCSV);
    var mn = $("#od-fm-minn");
    if (mn) mn.addEventListener("change", function () {
      var v = parseInt(mn.value, 10);
      S.fmMinN = (v >= 0 ? v : 10);
      renderFM();
    });
    var sec = $("#od-fm-sector");
    if (sec) sec.addEventListener("change", function () { S.fmSector = sec.value; renderFM(); });
  }

  /* ---------------- theme / lang / resize reactivity ---------------- */
  function syncPlaceholders() {
    var zh = isZh();
    document.querySelectorAll("input[data-ph-zh]").forEach(function (el) {
      if (!el._phEn) el._phEn = el.getAttribute("placeholder") || "";
      var z = el.getAttribute("data-ph-zh");
      if (z) el.placeholder = zh ? z : el._phEn;
    });
  }
  function initReactivity() {
    var re = debounce(function () { renderActivePane(); syncTabInk(); }, 70);
    document.addEventListener("themechange", re);
    document.addEventListener("langchange", function () { syncPlaceholders(); re(); });
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(debounce(function () {
        if (S.tab === "days") renderPriceChart();
        else if (S.tab === "path") renderPathChart();
        else if (S.tab === "returns") renderReturns();
      }, 90));
      ["#od-price-chart", "#od-path-chart", "#od-hist-chart"].forEach(function (id) {
        var el = $(id); if (el) ro.observe(el);
      });
    }
    syncPlaceholders();
  }

  /* ---------------- onboarding (first visit, dismissible) ---------------- */
  var OB_KEY = "odds_onboarded_v1";
  function initOnboard() {
    var el = $("#od-onboard");
    if (!el) return;
    var seen = null;
    try { seen = localStorage.getItem(OB_KEY); } catch (e) {}
    if (seen) return;
    el.hidden = false;
    function dismiss() {
      el.hidden = true;
      try { localStorage.setItem(OB_KEY, "1"); } catch (e) {}
    }
    var x = $("#od-onboard-x"), ok = $("#od-onboard-ok");
    if (x) x.addEventListener("click", dismiss);
    if (ok) ok.addEventListener("click", dismiss);
  }

  /* ---------------- per-condition ⓘ tooltips (catalog desc_en/desc_zh) ------- */
  function initInfoTips() {
    var tip = document.createElement("div");
    tip.className = "od-tipbox";
    document.body.appendChild(tip);
    var curBtn = null;
    function show(btn) {
      var fid = btn.getAttribute("data-f");
      var f = S.F[fid];
      if (!f || !(f.desc_en || f.desc_zh)) return;
      var lab = fLabel(fid);
      tip.innerHTML = "<b>" + bi(lab[0], lab[1]) + "</b><br>" + bi(f.desc_en || "", f.desc_zh || f.desc_en || "");
      var r = btn.getBoundingClientRect();
      var maxL = (document.documentElement.clientWidth || 1200) - 262;
      tip.style.left = Math.max(6, Math.min(window.scrollX + r.left - 8, window.scrollX + maxL)) + "px";
      tip.style.top = (window.scrollY + r.bottom + 7) + "px";
      tip.classList.add("show");
      curBtn = btn;
    }
    function hide() { tip.classList.remove("show"); curBtn = null; }
    document.addEventListener("mouseover", function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest(".od-info") : null;
      if (b) show(b);
      else if (curBtn) hide();
    });
    document.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest(".od-info") : null;
      if (b) { ev.stopPropagation(); ev.preventDefault(); if (curBtn === b) hide(); else show(b); }
    }, true);   // capture: an ⓘ tap must never toggle the condition underneath
    document.addEventListener("focusin", function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest(".od-info") : null;
      if (b) show(b);
      else if (curBtn) hide();
    });
  }

  /* ---------------- share card (1200×630 canvas → PNG, no libs) ------------- */
  function bindShare() {
    var btn = $("#od-share");
    if (!btn) return;
    btn.addEventListener("click", function () { buildShareCard(btn); });
  }
  function rrect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function wrapText(ctx, text, x, y, maxW, lh, maxLines, zh) {
    var parts = zh ? text.split("") : text.split(" ");
    var joiner = zh ? "" : " ";
    var line = "", lines = 0;
    for (var i = 0; i < parts.length; i++) {
      var test = line ? line + joiner + parts[i] : parts[i];
      if (ctx.measureText(test).width > maxW && line) {
        if (lines >= maxLines - 1) {
          var rest = parts.slice(i).join(joiner);
          while (rest.length && ctx.measureText(line + joiner + "…").width > maxW) line = line.slice(0, -1);
          ctx.fillText(line + "…", x, y);
          return y;
        }
        ctx.fillText(line, x, y);
        y += lh; lines++;
        line = parts[i];
      } else line = test;
    }
    if (line) ctx.fillText(line, x, y);
    return y;
  }
  function buildShareCard(btn) {
    try {
      var st = S.stats, base = S.base, m = S.matrix;
      if (!st || !m || st.n < 5) return;
      var zh = isZh();
      var W = 1200, H = 630;
      var cv = document.createElement("canvas");
      cv.width = W; cv.height = H;
      var ctx = cv.getContext("2d");
      if (!ctx) { btn.disabled = true; return; }
      var edge = base ? (st.rate - base.rate) * 100 : 0;
      /* --od-up/--od-down resolve the zh red=up swap automatically */
      var cUp = cssVar("--od-up", "#34D399"), cDn = cssVar("--od-down", "#F87171");
      var tone = edge >= 5 ? cUp : edge <= -5 ? cDn : "#E7EBF2";
      var FF = ", Inter, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif";
      var hz = HORIZON_TXT[S.horizon], rg = RANGE_TXT[S.range];
      var conds = condSummary();
      var D = edDate(m.dates[todayIdx()]);
      var dateStr = zh
        ? D.getUTCFullYear() + "年" + (D.getUTCMonth() + 1) + "月" + D.getUTCDate() + "日"
        : DOW_EN[D.getUTCDay()] + ", " + MON_EN[D.getUTCMonth()] + " " + D.getUTCDate() + " " + D.getUTCFullYear();

      function finish(logoEl) {
        /* card chrome — always the dark brand card */
        ctx.fillStyle = "#0B0E14"; ctx.fillRect(0, 0, W, H);
        rrect(ctx, 36, 36, W - 72, H - 72, 24);
        ctx.fillStyle = "#0E1219"; ctx.fill();
        ctx.strokeStyle = "#1D2330"; ctx.lineWidth = 2; ctx.stroke();
        /* header: logo circle + ticker · name + date right */
        var hx = 76;
        ctx.beginPath(); ctx.arc(hx + 26, 104, 26, 0, Math.PI * 2);
        ctx.fillStyle = "#151A23"; ctx.fill();
        ctx.strokeStyle = "#1D2330"; ctx.lineWidth = 1.5; ctx.stroke();
        if (logoEl) {
          try {
            ctx.save();
            ctx.beginPath(); ctx.arc(hx + 26, 104, 17, 0, Math.PI * 2); ctx.clip();
            ctx.drawImage(logoEl, hx + 9, 87, 34, 34);
            ctx.restore();
          } catch (e) { try { ctx.restore(); } catch (e2) {} }
        }
        ctx.fillStyle = "#E7EBF2"; ctx.font = "700 30px" + FF; ctx.textBaseline = "middle";
        ctx.fillText(S.ticker, hx + 68, 96);
        ctx.fillStyle = "#8B93A3"; ctx.font = "400 17px" + FF;
        var u = ((S.cat && S.cat.universe) || []).filter(function (x) { return x && x.t === S.ticker; })[0];
        ctx.fillText((u && u.name ? String(u.name).slice(0, 40) : ""), hx + 68, 124);
        ctx.textAlign = "right"; ctx.fillStyle = "#5C6474"; ctx.font = "400 16px" + FF;
        ctx.fillText(dateStr + " · " + (zh ? "开盘→收盘" : "open-to-close"), W - 76, 104);
        ctx.textAlign = "left";
        /* eyebrow */
        ctx.fillStyle = "#5C6474"; ctx.font = "700 15px" + FF;
        ctx.fillText((zh ? "历史形态 · " + st.n + " 个匹配交易日" : ("HISTORICAL PATTERN · " + st.n + " MATCHING DAYS")), hx, 182);
        /* giant rate + what */
        ctx.fillStyle = tone; ctx.font = "600 124px" + FF; ctx.textBaseline = "alphabetic";
        ctx.fillText(fmtRate(st.rate), hx - 4, 322);
        ctx.fillStyle = "#8B93A3"; ctx.font = "500 24px" + FF;
        ctx.fillText(zh ? hz[1] + "收高" : "closed higher " + hz[0], hx, 366);
        /* CI band (right half) */
        if (st.ci) {
          var bx0 = 640, bx1 = W - 96, by = 262;
          var px = function (p) { return bx0 + p * (bx1 - bx0); };
          ctx.fillStyle = "#5C6474"; ctx.font = "700 13px" + FF;
          ctx.fillText(zh ? "95% 置信区间（WILSON）" : "95% CONFIDENCE (WILSON)", bx0, by - 44);
          rrect(ctx, bx0, by - 4, bx1 - bx0, 8, 4); ctx.fillStyle = "#161C27"; ctx.fill();
          rrect(ctx, px(st.ci[0]), by - 4, Math.max(4, px(st.ci[1]) - px(st.ci[0])), 8, 4);
          ctx.fillStyle = edge >= 5 ? "rgba(52,211,153,.38)" : edge <= -5 ? "rgba(248,113,113,.38)" : "rgba(139,147,163,.35)";
          ctx.fill();
          ctx.fillStyle = "#5C6474"; ctx.fillRect(px(0.5), by - 10, 1, 20);
          ctx.fillStyle = tone; ctx.fillRect(px(st.rate) - 1.5, by - 8, 3, 16);
          ctx.fillStyle = "#5C6474"; ctx.font = "400 14px" + FF; ctx.textAlign = "center";
          ctx.fillText(zh ? "50% · 抛硬币" : "50% · coin flip", px(0.5), by - 22);
          ctx.fillText(fmtRate(st.ci[0]), Math.max(bx0 + 24, px(st.ci[0])), by + 28);
          ctx.fillText(fmtRate(st.ci[1]), Math.min(bx1 - 24, px(st.ci[1])), by + 28);
          ctx.textAlign = "left";
          /* metric chips line */
          ctx.fillStyle = "#8B93A3"; ctx.font = "500 18px" + FF;
          var chips = zh
            ? "中位数 " + fmtBpPct(st.med) + "　均值 " + fmtBpPct(st.mean) + "　相对基础 " + fmtSigned(edge) + " 点　n=" + st.n
            : "median " + fmtBpPct(st.med) + "   mean " + fmtBpPct(st.mean) + "   edge vs base " + fmtSigned(edge) + " pts   n=" + st.n;
          ctx.fillText(chips, bx0, by + 74);
        }
        /* verdict sentence */
        ctx.fillStyle = "#8B93A3"; ctx.font = "400 20px" + FF;
        var sent = zh
          ? "条件：" + conds[1] + "。在" + rg[1] + "的 " + st.n + " 个相似交易日中，" + hz[1] + "收高概率为 " +
            fmtRate(st.rate) + "（中位数 " + fmtBpPct(st.med) + "，基础概率 " + fmtRate(base ? base.rate : 0) + "）。"
          : "Conditions: " + conds[0] + ". Across " + st.n + " similar days in " + rg[0] + ", price closed higher " +
            fmtRate(st.rate) + " of the time (median " + fmtBpPct(st.med) + ", base rate " + fmtRate(base ? base.rate : 0) + ").";
        wrapText(ctx, sent, hx, 448, W - 152 - hx + 76, 30, 3, zh);
        /* footer */
        ctx.strokeStyle = "#161C27"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(76, 548); ctx.lineTo(W - 76, 548); ctx.stroke();
        ctx.fillStyle = "#5C6474"; ctx.font = "700 15px" + FF;
        ctx.fillText("MASTERMIND-X · MACRO DASHBOARD — ODDS DESK", 76, 576);
        ctx.textAlign = "right"; ctx.font = "400 14px" + FF;
        ctx.fillText(zh ? "描述性统计 · 不构成投资建议" : "descriptive statistics · not investment advice", W - 76, 576);
        ctx.textAlign = "left";
        /* download */
        try {
          var a = document.createElement("a");
          a.href = cv.toDataURL("image/png");
          a.download = "odds_" + S.ticker + "_" + S.horizon + "_" + (m.asof || "latest") + ".png";
          document.body.appendChild(a); a.click();
          setTimeout(function () { a.remove(); }, 300);
        } catch (e) {   // tainted canvas or blocked download — degrade to disabled
          btn.disabled = true;
        }
      }
      /* logo: CORS attempt; on failure the card ships without it */
      var done = false;
      var img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = function () { if (!done) { done = true; finish(img); } };
      img.onerror = function () { if (!done) { done = true; finish(null); } };
      setTimeout(function () { if (!done) { done = true; finish(null); } }, 1500);
      img.src = LOGO_CDN + S.ticker + ".png";
    } catch (e) { try { btn.disabled = true; } catch (e2) {} }
  }

  /* ---------------- boot ---------------- */
  function showError() {
    var e = $("#od-error"), app = $("#od-app");
    if (e) e.hidden = false;
    if (app) app.hidden = true;
  }
  function init() {
    fetchJSON("oddsdata/catalog.json").then(function (cat) {
      try {
        if (!cat || cat.schema !== "odds_catalog.v1" || !Array.isArray(cat.factors) ||
            !Array.isArray(cat.universe) || !cat.universe.length) { showError(); return; }
        S.cat = cat;
        cat.factors.forEach(function (f) { if (f && f.id) { S.F[f.id] = f; S.factorOrder.push(f.id); } });
        var defs = cat.defaults || {};
        (defs.active || ["magnitude", "vix_level", "mkt_trend"]).forEach(function (fid) {
          if (S.F[fid]) S.active[fid] = true;
        });
        if (defs.range && RANGE_TXT[defs.range]) S.range = defs.range;
        if (defs.horizon && FWD_KEY[defs.horizon]) S.horizon = defs.horizon;
        var asof = $("#od-asof-chip");
        if (asof) asof.innerHTML = bi("As of " + (cat.asof || "—"), "截至 " + (cat.asof || "—"));
        var uni = $("#od-uni-chip");
        if (uni) { uni.innerHTML = biRaw(cat.universe.length + " symbols", cat.universe.length + " 个标的"); uni.hidden = false; }
        staleCheck();
        var app = $("#od-app");
        if (app) app.hidden = false;
        initControls();
        initTypeahead();
        initTabs();
        initReactivity();
        initOnboard();
        initInfoTips();
        renderRail();
        /* ?t=NVDA deep link — checked against the universe, else default SPY */
        var qt = "";
        try { qt = (new URLSearchParams(location.search).get("t") || "").trim().toUpperCase(); } catch (e) { qt = ""; }
        var inUni = qt && cat.universe.some(function (u) { return u.t === qt; });
        var hasSPY = cat.universe.some(function (u) { return u.t === "SPY"; });
        loadTicker(inUni ? qt : hasSPY ? "SPY" : cat.universe[0].t);
      } catch (e) { showError(); }
    }).catch(showError);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

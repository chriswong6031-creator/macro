/* risk_state_live.js — progressive enhancement: poll the intraday live risk-state
   (site/live/risk_state.json, written by scripts/build_risk_state.py every few minutes
   during market hours) and patch the Market State headline on macro.html.

   Additive + defensive: no-ops when the file or the target elements are absent (so it is
   safe on every page and on the static/no-live deploy). The CONTINUOUS 0-100 score moves
   every tick; the discrete band WORD is the server-debounced display.verdict (no whipsaw).
   Honest freshness: only lights the "live" pill when the feed is actually live (RTH + a
   fresh, non-stale quote); otherwise the page keeps the nightly server-rendered read. */
(function () {
  "use strict";
  var URL = "live/risk_state.json";
  var POLL = (window.LIVE_POLL_SEC && +window.LIVE_POLL_SEC) || 60;
  var COLOR = { RISK_ON: "green", MIXED: "yellow", RISK_OFF: "red" };

  /* Verdict-keyed Tier-1 copy. MUST mirror engine/market_state.py _HEADLINES and the
     dashboard.html.j2 sub-line / What-To-Do vocab (guarded by
     tests/test_risk_state_live_copy_sync.py). These exist so an intraday band flip can
     never leave render-time "Risk-on" prose sitting next to a live Mixed gauge. */
  var HEADLINE = {
    RISK_ON: ["Risk-on — the tape, breadth and cross-asset signals line up. Trend-following and adding on strength is supported.",
              "风险偏好 — 价格、广度与跨资产信号一致。顺势交易与逢强加仓得到支持。"],
    MIXED: ["Mixed / transition — the signals disagree. Trade smaller, favour quality, take profits faster; don't position aggressively.",
            "混合 / 转换 — 信号分歧。缩小仓位、偏好质量、更快获利了结；勿激进布局。"],
    RISK_OFF: ["Risk-off — stress is elevated; defend capital first.",
               "避险 — 压力升高；优先防守。"]
  };
  var SUBLINE = {
    RISK_ON: ["GREEN — Trend-following supported", "偏多 — 顺势而为受支撑"],
    MIXED: ["YELLOW — Trade with caution", "谨慎操作"],
    RISK_OFF: ["RED — Defend capital first", "优先保住本金"]
  };
  var ACTION = {
    RISK_ON: ["Follow the trend. Add on strength.", "顺势而为，强势中加仓。"],
    MIXED: ["Trade small. Stay selective.", "缩小仓位，精选标的。"],
    RISK_OFF: ["Reduce risk. Protect capital.", "降低风险，保护本金。"]
  };
  /* zh 红涨绿跌 (operator ruling 2026-07-21): the state colours are DIRECTION reads
     (risk-on=bullish), so they route through the zh-swapping --up/--warn/--down tokens
     instead of literal hex. These are CSS values, so every consumer below MUST write
     them via el.style.* (inline style resolves var()/color-mix; bare SVG presentation
     attributes do not) — which also means a lang toggle recolours instantly, no repaint. */
  var HEX = { green: "var(--up)", yellow: "var(--warn)", red: "var(--down)" };
  var GLOW = { green: "color-mix(in srgb,var(--up) 70%,transparent)", yellow: "color-mix(in srgb,var(--warn) 70%,transparent)", red: "color-mix(in srgb,var(--down) 70%,transparent)" };
  var SOFT = { green: "color-mix(in srgb,var(--up) 30%,transparent)", yellow: "color-mix(in srgb,var(--warn) 30%,transparent)", red: "color-mix(in srgb,var(--down) 30%,transparent)" };
  var HALO = { green: "color-mix(in srgb,var(--up) 14%,transparent)", yellow: "color-mix(in srgb,var(--warn) 14%,transparent)", red: "color-mix(in srgb,var(--down) 14%,transparent)" };
  var WTD_ICON = { green: "mx5-ai-green", yellow: "mx5-ai-yellow", red: "mx5-ai-gray" };
  var WTD_STROKE = { green: "var(--up)", yellow: "var(--warn)", red: "rgba(255,255,255,.38)" };
  var WTD_SHAPE = {
    green: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    yellow: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    red: '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
  };
  /* verdict word baked into the page at render time — captured on the first patch,
     BEFORE any live overwrite, so we can tell when the live band has moved off it. */
  var bakedLabelEn = null;

  /* ── Feed-behind-the-render floor ──────────────────────────────────────────
     The page is rendered from the nightly read; risk_state.json is a SEPARATE
     artifact published by the intraday VPS lane, and it can sit a whole session
     BEHIND the render (the lane does not publish on a closed session, so a
     Friday file is still what a Sunday visitor fetches). patchPath already
     refuses to move the chart backwards — "never rewrite history" — but the
     headline had no such floor, so a behind-the-render feed repainted the gauge
     with an OLDER session's score while the chart kept the newer one, and the
     same card shipped 44 / Mixed beside a Risk-on line ending Jul 31 (operator
     report 2026-08-02; 44 was Jul 30's graded score, the chart's Jul 31 was 66).
     Capture the RENDERED session once, before any patch touches the DOM, and
     skip the whole read when the feed cannot match it — which is what this
     file's header has always claimed: "otherwise the page keeps the nightly
     server-rendered read". */
  var DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
  var bakedSession;   /* undefined until first read; "" when the page carries none */

  /* The session the RENDER is showing: the chart's last graded row and the
     board's own as-of stamps, whichever is newest. Memoised on first call,
     which happens before this file writes anything, so a later live patch of
     #ms-date can never feed back into the floor. */
  function pageSession() {
    if (bakedSession !== undefined) return bakedSession;
    bakedSession = "";
    try {
      var best = "", i, el, t;
      var svg = document.querySelector(".mx5-sc-right .mx5-path-svg[data-points]");
      if (svg) {
        var pts = JSON.parse(svg.getAttribute("data-points") || "[]");
        t = pts.length ? String(pts[pts.length - 1].d || "") : "";
        if (DATE_RE.test(t)) best = t;
      }
      var ids = ["regime-asof", "ms-date"];
      for (i = 0; i < ids.length; i++) {
        el = document.getElementById(ids[i]);
        t = el ? (el.textContent || "").trim() : "";
        if (DATE_RE.test(t) && t > best) best = t;
      }
      bakedSession = best;
    } catch (e) { bakedSession = ""; }
    return bakedSession;
  }

  /* The session the FEED describes: its own build date while the intraday lane
     is live, else the nightly close it was built from. */
  function feedSession(d) {
    var s = d.live_active ? (d.built || "").slice(0, 10)
                          : (d.nightly_asof || (d.built || "").slice(0, 10));
    return DATE_RE.test(s) ? s : "";
  }

  /* True when the feed is at least as current as the rendered page. A feed whose
     own session cannot be read counts as behind: failing closed keeps the served
     render, which is always a real single-session snapshot. */
  function feedIsCurrent(d) {
    var floor = pageSession();
    if (!floor) return true;              /* page carries no as-of — nothing to hold */
    var s = feedSession(d);
    return !!s && s >= floor;
  }

  /* score-path chart vocab — mirrors the vz/v values build_site bakes into data-points
     (chart zone vocab, NOT the display labels: Mixed→中性 there, not 混合) */
  var PATH_V  = { RISK_ON: "Risk-on", MIXED: "Mixed", RISK_OFF: "Risk-off" };
  var PATH_VZ = { RISK_ON: "偏多", MIXED: "中性", RISK_OFF: "偏空" };
  var MONTH_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /* Live provisional point on the score-path chart. The baked chart is a view of the
     nightly forward ledger, so between renders the current session is missing (and a
     no-network re-render can even regress the bake to an older close). Trust the live
     feed instead: update the last point in place when the bake already has the session,
     else APPEND a provisional point — rescaling x from the svg's own data-* constants,
     re-seating the axis ticks/date labels, and recoloring line/fill/dot to the live
     verdict. data-points is rewritten and 'mx5pathlive' dispatched so the baked hover
     script re-reads it (tooltip stays truthful, incl. on the provisional point). */
  function patchPath(d, disp) {
    if (disp.score == null || !PATH_V[disp.verdict]) return;
    var svg = document.querySelector(".mx5-sc-right .mx5-path-svg[data-points]");
    if (!svg) return;
    var pts;
    try { pts = JSON.parse(svg.getAttribute("data-points") || "[]"); } catch (e) { return; }
    if (pts.length < 2) return;
    var sess = d.live_active ? (d.built || "").slice(0, 10)
                             : (d.nightly_asof || (d.built || "").slice(0, 10));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(sess)) return;
    var last = pts[pts.length - 1];
    if (sess < last.d) return;                    /* never rewrite history */
    var PX0 = +(svg.getAttribute("data-px0") || 44),  PXW = +(svg.getAttribute("data-pxw") || 944);
    var PY0 = +(svg.getAttribute("data-py0") || 10),  PYB = +(svg.getAttribute("data-pyb") || 194);
    var VBW = +(svg.getAttribute("data-vbw") || 1000), VBH = +(svg.getAttribute("data-vbh") || 224);
    var s = Math.max(0, Math.min(100, +disp.score));
    var y = Math.round((PYB - s / 100 * (PYB - PY0)) * 100) / 100;
    var col = HEX[COLOR[disp.verdict]];
    var appended = false, oldX = null, i;
    if (sess > last.d) {
      oldX = [];
      for (i = 0; i < pts.length; i++) oldX.push(pts[i].x);
      var mm = +sess.slice(5, 7), dd = +sess.slice(8, 10);
      pts.push({ d: sess, md: MONTH_EN[mm - 1] + " " + dd, mz: mm + "月" + dd,
                 s: s, v: PATH_V[disp.verdict], vz: PATH_VZ[disp.verdict], x: 0, y: y, live: 1 });
      for (i = 0; i < pts.length; i++)
        pts[i].x = Math.round((PX0 + i / (pts.length - 1) * PXW) * 100) / 100;
      appended = true;
    } else {
      if (last.s === s && last.v === PATH_V[disp.verdict]) return;   /* no change */
      last.s = s; last.y = y;
      last.v = PATH_V[disp.verdict]; last.vz = PATH_VZ[disp.verdict];
    }
    var lastP = pts[pts.length - 1];
    var lineStr = pts.map(function (p) { return p.x + "," + p.y; }).join(" ");
    var poly = svg.querySelector("polyline");
    if (poly) { poly.setAttribute("points", lineStr); poly.style.stroke = col; }
    var area = svg.querySelector('path[fill^="url("]');
    if (area)
      area.setAttribute("d", "M" + lineStr.replace(/ /g, " L") +
                             " L" + lastP.x + "," + PYB + " L" + PX0 + "," + PYB + " Z");
    var stops = svg.querySelectorAll("linearGradient stop");
    for (i = 0; i < stops.length; i++) stops[i].style.stopColor = col;
    var tdot = document.querySelector(".mx5-sc-right .mx5-pl-today");
    if (tdot) {
      tdot.style.left = (lastP.x / VBW * 100).toFixed(2) + "%";
      tdot.style.top = (lastP.y / VBH * 100).toFixed(3) + "%";
      tdot.style.color = col;
    }
    if (appended) {
      /* axis tick marks (inside the font-size <g>) — re-seat onto rescaled xs */
      var lines = svg.querySelectorAll("g line");
      for (i = 0; i < lines.length; i++) {
        if (+lines[i].getAttribute("y1") !== PYB) continue;
        var x1 = +lines[i].getAttribute("x1"), bi = -1, bd = 1e9, oi;
        for (oi = 0; oi < oldX.length; oi++) {
          var dx = Math.abs(oldX[oi] - x1);
          if (dx < bd) { bd = dx; bi = oi; }
        }
        if (bi >= 0 && bd < 1) {
          lines[i].setAttribute("x1", pts[bi].x);
          lines[i].setAttribute("x2", pts[bi].x);
        }
      }
      /* date labels (HTML overlay) — match by baked EN text, re-seat, and demote the
         old last tick's right-alignment to centered now that it is an interior tick */
      var xt = document.querySelectorAll(".mx5-sc-right .mx5-pl-x");
      for (i = 0; i < xt.length; i++) {
        var en = xt[i].querySelector(".l-en");
        var mdTxt = (en ? en.textContent : xt[i].textContent).trim();
        for (var pi = 0; pi < pts.length; pi++) {
          if (pts[pi].md === mdTxt) {
            xt[i].style.left = (pts[pi].x / VBW * 100).toFixed(2) + "%";
            if (pi > 0 && pi < pts.length - 1) xt[i].style.transform = "translate(-50%,-50%)";
            break;
          }
        }
      }
      var ttl = document.querySelector(".mx5-path-title");
      if (ttl) {
        var tEn = ttl.querySelector(".l-en"), tZh = ttl.querySelector(".l-zh");
        if (tEn) tEn.textContent = pts.length + "-session path";
        if (tZh) tZh.textContent = "近 " + pts.length + " 交易日走势";
      }
    }
    svg.setAttribute("aria-label", pts.length + "-session macro score path, " +
                                   pts[0].s + " to " + lastP.s);
    svg.setAttribute("data-points", JSON.stringify(pts));
    try { document.dispatchEvent(new CustomEvent("mx5pathlive")); } catch (e2) {}
  }

  function isZh() {
    try {
      // the site marks Chinese mode with html[data-lang="zh"] (theme.js); the older
      // documentElement.lang / body.lang-zh checks below are kept only as fallbacks.
      var el = document.documentElement;
      return (el.getAttribute("data-lang") || "").slice(0, 2) === "zh" ||
             (el.lang || "").slice(0, 2) === "zh" ||
             document.body.classList.contains("lang-zh");
    } catch (e) { return false; }
  }
  /* Render a bilingual verdict as the site's dual l-en/l-zh span pair so it follows
     the html[data-lang] CSS toggle — and keeps switching if the user changes language
     AFTER the live feed patches the node. A single-language text node would freeze in
     whatever language happened to be active at patch time. */
  function setBL(el, en, zh) {
    el.textContent = "";
    var sEn = document.createElement("span"); sEn.className = "l-en"; sEn.textContent = en;
    var sZh = document.createElement("span"); sZh.className = "l-zh"; sZh.textContent = zh;
    el.appendChild(sEn); el.appendChild(sZh);
  }
  function verdictBL(el, disp) {
    setBL(el, disp.label_en || disp.verdict, disp.label_zh || disp.label_en || disp.verdict);
  }

  /* macro.html — the Market State board */
  function patchMacro(d) {
    var word = document.getElementById("ms-word");
    if (!word) return;
    var disp = d.display || {};
    if (!disp.verdict) return;
    /* Feed behind the render: keep the served read WHOLE — gauge, copy, chart and
       freshness chip alike. Patching any one of them is what split the card. */
    if (!feedIsCurrent(d)) {
      var offPill = document.getElementById("ms-live-pill");
      if (offPill) offPill.classList.remove("on");
      return;
    }
    /* Stale-feed guard: display.verdict is the SERVER-debounced band word — it needs
       2 consecutive live ticks to flip, so after a nightly band flip it sits stale for
       a whole closed session (2026-07-16: green "Risk-on" painted over a correctly
       baked "Mixed" while live AND nightly both said MIXED). When the feed is not live
       and the debounced word disagrees with the nightly verdict, key the WORD / color /
       copy off the nightly read instead — the header invariant ("otherwise the page
       keeps the nightly server-rendered read") — while the score numeral and as-of
       dates below still patch. */
    if ((d.stale === true || !d.live_active) && d.nightly && d.nightly.verdict &&
        disp.verdict !== d.nightly.verdict) {
      var ntl = d.nightly;
      disp = { verdict: ntl.verdict, label_en: ntl.label_en, label_zh: ntl.label_zh,
               color: ntl.color, score: disp.score };
    }
    if (bakedLabelEn === null) {
      var b0 = document.querySelector(".mx5-verdict-word .l-en");
      bakedLabelEn = b0 ? b0.textContent.trim() : "";
    }
    var arr = word.querySelector(".arr");
    verdictBL(word, disp);
    if (arr) word.appendChild(arr);
    var sc = document.getElementById("ms-score");
    if (sc && disp.score != null) sc.textContent = disp.score;
    var tick = document.getElementById("ms-tick");
    if (tick && disp.score != null) tick.style.left = disp.score + "%";
    /* v5 gauge: update arc fill + needle + numeral on live score tick */
    if (disp.score != null) {
      var gsvg = document.querySelector(".mx5-gauge-svg");
      if (gsvg) {
        var arcLen = parseFloat(gsvg.getAttribute("data-gauge-arc-len") || "175.93");
        var filled = Math.round((disp.score / 100) * arcLen * 10) / 10;
        var gap    = Math.round((arcLen - filled) * 10) / 10;
        var needleDeg = Math.round((disp.score / 100 * 180 - 90) * 10) / 10;
        var arcEl = document.getElementById("mx5-gauge-arc-fill");
        if (arcEl) arcEl.setAttribute("stroke-dasharray", filled + " " + gap);
        var needleEl = document.getElementById("mx5-gauge-needle");
        var cx = gsvg.getAttribute("data-gauge-cx") || "70";
        var cy = gsvg.getAttribute("data-gauge-cy") || "75";
        if (needleEl) needleEl.setAttribute("transform", "rotate(" + needleDeg + " " + cx + " " + cy + ")");
        var numEl = document.getElementById("mx5-score-numeral");
        if (numEl) numEl.textContent = disp.score;
        /* v5 big-score text block (right of gauge) */
        var bigSc = document.querySelector(".mx5-big-score");
        if (bigSc) bigSc.textContent = disp.score;
        /* v5 verdict word next to big-score */
        var vw = document.querySelector(".mx5-verdict-word");
        if (vw) setBL(vw, disp.label_en || disp.verdict, disp.label_zh || disp.label_en || disp.verdict);
      }
    }
    /* VIS-04/COPY-02: also update progress fill width so bar matches live score */
    if (disp.score != null) {
      var fills = document.querySelectorAll(".mx2-prog-fill");
      for (var fi = 0; fi < fills.length; fi++) fills[fi].style.width = disp.score + "%";
    }
    /* v5: verdict-keyed copy + colors baked at render time — patch them all so an
       intraday band flip never leaves stale "Risk-on" prose beside a Mixed gauge.
       Every write is guarded; an unknown verdict leaves the baked page untouched. */
    var col = COLOR[disp.verdict];
    if (col && HEADLINE[disp.verdict]) {
      var th = document.querySelector(".mx5-thesis");
      if (th) setBL(th, HEADLINE[disp.verdict][0], HEADLINE[disp.verdict][1]);
      var sub = document.querySelector(".mx5-sub-line");
      if (sub) setBL(sub, SUBLINE[disp.verdict][0], SUBLINE[disp.verdict][1]);
      var gsvgA = document.querySelector(".mx5-gauge-svg");
      if (gsvgA && disp.score != null)
        gsvgA.setAttribute("aria-label", (disp.label_en || disp.verdict) + " — score " + disp.score);
      /* gauge cluster color scope — big-score color/glow are CSS keyed off this class */
      var grow = document.querySelector(".mx5-sc-gauge-row");
      if (grow) {
        grow.classList.remove("mx5-score-green", "mx5-score-yellow", "mx5-score-red");
        grow.classList.add("mx5-score-" + col);
      }
      /* inline-SVG accents carry the render-time color as attributes — repaint */
      var num = document.getElementById("mx5-score-numeral");
      if (num) {
        num.style.fill = HEX[col];
        num.style.filter = "drop-shadow(0 0 10px " + GLOW[col] + ")";
      }
      var ndl = document.getElementById("mx5-gauge-needle");
      if (ndl) {
        var nln = ndl.querySelector("line");
        if (nln) nln.style.stroke = SOFT[col];
        var ncs = ndl.querySelectorAll("circle");
        if (ncs.length >= 4) {
          ncs[0].style.fill = HALO[col];
          ncs[1].style.stroke = HEX[col];
          ncs[2].style.fill = HEX[col];
          ncs[3].style.fill = HEX[col];
          ncs[3].style.filter = "drop-shadow(0 0 4px " + HEX[col] + ")";
        }
      }
      /* What To Do primary row — concise action plus verdict/score context. */
      var wl = document.querySelector("[data-wtd-primary] .mx5-action-label");
      if (wl && ACTION[disp.verdict])
        setBL(wl, ACTION[disp.verdict][0], ACTION[disp.verdict][1]);
      var ws = document.querySelector("[data-wtd-primary] .mx5-action-sub");
      if (ws && disp.score != null)
        setBL(ws, (disp.label_en || disp.verdict) + " · " + disp.score + "/100",
                  (disp.label_zh || disp.label_en || disp.verdict) + " · " + disp.score + "/100");
      var wicon = document.querySelector("[data-wtd-primary] .mx5-action-icon");
      if (wicon) {
        wicon.classList.remove("mx5-ai-green", "mx5-ai-yellow", "mx5-ai-gray");
        wicon.classList.add(WTD_ICON[col]);
        var wsvg = wicon.querySelector("svg");
        if (wsvg) { wsvg.style.stroke = WTD_STROKE[col]; wsvg.innerHTML = WTD_SHAPE[col]; }
      }
      /* the flip-condition line belongs to the BAKED verdict — its trigger prose is
         stale (or already met) once the live band moves off it, so hide it then. */
      var flip = document.querySelector(".mx5-flip");
      if (flip && bakedLabelEn)
        flip.style.display = ((disp.label_en || "") === bakedLabelEn) ? "" : "none";
      /* regime pill (quad name) tracks the market-state color too (operator order
         2026-07-13): amber when Mixed, red when Risk-off, default green accent. */
      var rpill = document.querySelector(".mx5-regime-pill");
      if (rpill) {
        rpill.classList.remove("rp-yellow", "rp-red");
        if (col === "yellow") rpill.classList.add("rp-yellow");
        else if (col === "red") rpill.classList.add("rp-red");
      }
      /* aurora backdrop: the green ambient blobs follow the verdict color too
         (operator order 2026-07-14) — au-* variants defined in the page CSS. */
      var aur = document.querySelector(".mx5-aurora");
      if (aur) {
        aur.classList.remove("au-yellow", "au-red");
        if (col === "yellow") aur.classList.add("au-yellow");
        else if (col === "red") aur.classList.add("au-red");
      }
    }
    patchPath(d, disp);
    var front = word.closest(".ms-front") || word.closest(".ms");
    if (front) {
      front.classList.remove("ms-green", "ms-yellow", "ms-red");
      front.classList.add("ms-" + (COLOR[disp.verdict] || "yellow"));
    }
    // honest freshness: a 15-min-delayed feed (delayed_min>0 -> realtime:false) is NOT "live".
    var dt = document.getElementById("ms-date");
    if (dt && d.live_active) {
      var hhmm = (d.built || "").slice(11, 16);
      /* not `word` — that name already holds the #ms-word node in this scope */
      var fresh = d.realtime ? (isZh() ? "实时 " : "live ") : (isZh() ? "延迟 " : "delayed ");
      dt.textContent = "· " + fresh + hhmm + " UTC";
      dt.classList.toggle("ms-date-live", !!d.realtime);
    } else if (dt && d.nightly_asof) {
      // market closed / no fresh quote: still show the freshest available CLOSE (the
      // self-healed nightly as-of), not the possibly-staler date baked into the page at
      // render time — so a late-landing daily bar surfaces without waiting for a re-render.
      dt.textContent = "· " + d.nightly_asof;
      dt.classList.remove("ms-date-live");
    }
    // the "Current Macro Regime" hero eyebrow reads the SAME nightly as-of. The Quad is a slow
    // nowcast — it does not tick intraday — but its date must follow the latest close. Forward-
    // compatible: no-ops until a render bakes the #regime-asof id into the page.
    var rg = document.getElementById("regime-asof");
    if (rg && d.nightly_asof) rg.textContent = d.nightly_asof;
    var pill = document.getElementById("ms-live-pill");
    if (pill) pill.classList.toggle("on", !!(d.live_active && d.realtime));
  }

  function tick() {
    fetch(URL + "?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.schema !== "risk_state.v1") return;
        try { patchMacro(d); } catch (e) {}
      })
      .catch(function () {});
  }

  if (document.readyState !== "loading") tick();
  else document.addEventListener("DOMContentLoaded", tick);
  setInterval(tick, Math.max(15, POLL) * 1000);
})();

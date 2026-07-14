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
    RISK_ON: ["Trend-follow, add on strength.", "顺势而为，强势中加仓。"],
    MIXED: ["Trade with caution. Size small.", "谨慎操作，仓位缩小。"],
    RISK_OFF: ["Defend capital first. Reduce risk.", "优先保住本金，降低风险。"]
  };
  var HEX = { green: "#22d97a", yellow: "#f59e0b", red: "#ef4444" };
  var GLOW = { green: "rgba(34,217,122,.7)", yellow: "rgba(245,158,11,.7)", red: "rgba(239,68,68,.7)" };
  var SOFT = { green: "rgba(34,217,122,.30)", yellow: "rgba(245,158,11,.30)", red: "rgba(239,68,68,.30)" };
  var HALO = { green: "rgba(34,217,122,.14)", yellow: "rgba(245,158,11,.14)", red: "rgba(239,68,68,.14)" };
  var WTD_ICON = { green: "mx5-ai-green", yellow: "mx5-ai-yellow", red: "mx5-ai-gray" };
  var WTD_STROKE = { green: "#22d97a", yellow: "#f59e0b", red: "rgba(255,255,255,.38)" };
  var WTD_SHAPE = {
    green: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    yellow: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    red: '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
  };
  /* verdict word baked into the page at render time — captured on the first patch,
     BEFORE any live overwrite, so we can tell when the live band has moved off it. */
  var bakedLabelEn = null;

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
        num.setAttribute("fill", HEX[col]);
        num.style.filter = "drop-shadow(0 0 10px " + GLOW[col] + ")";
      }
      var ndl = document.getElementById("mx5-gauge-needle");
      if (ndl) {
        var nln = ndl.querySelector("line");
        if (nln) nln.setAttribute("stroke", SOFT[col]);
        var ncs = ndl.querySelectorAll("circle");
        if (ncs.length >= 4) {
          ncs[0].setAttribute("fill", HALO[col]);
          ncs[1].setAttribute("stroke", HEX[col]);
          ncs[2].setAttribute("fill", HEX[col]);
          ncs[3].setAttribute("fill", HEX[col]);
          ncs[3].style.filter = "drop-shadow(0 0 4px " + HEX[col] + ")";
        }
      }
      /* What To Do row 1 — regime action line + "Composite NN/100" sub.
         Sanity-check the EN span still opens with a verdict word so we never
         clobber a page where row 1 is not the regime row. */
      var wl = document.querySelector(".mx5-action-list .mx5-action-item .mx5-action-label");
      if (wl) {
        var wlEn = wl.querySelector(".l-en");
        if (wlEn && /^(Risk-on|Mixed|Risk-off)/.test(wlEn.textContent.trim()))
          setBL(wl, (disp.label_en || disp.verdict) + " — " + ACTION[disp.verdict][0],
                    (disp.label_zh || disp.label_en || disp.verdict) + " — " + ACTION[disp.verdict][1]);
      }
      var ws = document.querySelector(".mx5-action-list .mx5-action-item .mx5-action-sub");
      if (ws && disp.score != null) {
        var wspans = ws.querySelectorAll("span");
        for (var wi = 0; wi < wspans.length; wi++)
          wspans[wi].textContent = wspans[wi].textContent.replace(/\d+(?=\/100)/, disp.score);
      }
      var wicon = document.querySelector(".mx5-action-list .mx5-action-item .mx5-action-icon");
      if (wicon) {
        wicon.classList.remove("mx5-ai-green", "mx5-ai-yellow", "mx5-ai-gray");
        wicon.classList.add(WTD_ICON[col]);
        var wsvg = wicon.querySelector("svg");
        if (wsvg) { wsvg.setAttribute("stroke", WTD_STROKE[col]); wsvg.innerHTML = WTD_SHAPE[col]; }
      }
      /* the flip-condition line belongs to the BAKED verdict — its trigger prose is
         stale (or already met) once the live band moves off it, so hide it then. */
      var flip = document.querySelector(".mx5-flip");
      if (flip && bakedLabelEn)
        flip.style.display = ((disp.label_en || "") === bakedLabelEn) ? "" : "none";
    }
    var front = word.closest(".ms-front") || word.closest(".ms");
    if (front) {
      front.classList.remove("ms-green", "ms-yellow", "ms-red");
      front.classList.add("ms-" + (COLOR[disp.verdict] || "yellow"));
    }
    // honest freshness: a 15-min-delayed feed (delayed_min>0 -> realtime:false) is NOT "live".
    var dt = document.getElementById("ms-date");
    if (dt && d.live_active) {
      var hhmm = (d.built || "").slice(11, 16);
      var word = d.realtime ? (isZh() ? "实时 " : "live ") : (isZh() ? "延迟 " : "delayed ");
      dt.textContent = "· " + word + hhmm + " UTC";
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

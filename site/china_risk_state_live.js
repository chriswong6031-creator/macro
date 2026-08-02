/* china_risk_state_live.js — progressive enhancement: poll the intraday live China
   risk-state (site/live/china_risk_state.json, written by scripts/build_china_risk_state.py
   every ~30 min during HKEX RTH) and patch the China Market State board on china.html.

   Scoped to china.html only — lighter than risk_state_live.js. china.html's hero now
   carries the ported US mx5 semicircle gauge (id mx5-gauge-needle / mx5-gauge-arc-fill /
   mx5-score-numeral, geometry in the SVG's data-gauge-* attrs); we patch those in place.
   Ships as a PAIRED plain-copy asset: templates/china_risk_state_live.js must byte-match
   site/china_risk_state_live.js.

   Additive + defensive: no-ops when the file or the target elements are absent.
   Honest freshness: only lights the "live" pill when realtime:true (delayed_min==0);
   Yahoo spark is ~15-min delayed so the pill is off and the date shows "delayed/延迟".

   DOM targets (inside _market_state_board.html.j2, shared with macro.html):
     #ms-word      — verdict word + .arr glyph span (▲/▶/▼)
     #ms-score     — 0-100 score numeral
     #ms-tick      — progress tick left: <score>%
     #ms-date      — "· delayed HH:MM UTC" / "· live HH:MM UTC" / "· YYYY-MM-DD"
     #ms-live-pill — "live" badge toggled on live_active && realtime only
     .v-thesis     — headline_en/zh for the current verdict (bilingual l-en/l-zh)
     .v-flip       — "flip" condition line: hidden when live band moves off the baked verdict
     .ms-front / .ms  — wrapper: ms-green / ms-yellow / ms-red class swap */
(function () {
  "use strict";
  var URL = "live/china_risk_state.json";
  var POLL = (window.LIVE_POLL_SEC && +window.LIVE_POLL_SEC) || 60;
  var COLOR = { RISK_ON: "green", MIXED: "yellow", RISK_OFF: "red" };
  /* Glyph arrows keyed by color — green = up, yellow = hold, red = down */
  var GLYPH = { green: "▲", yellow: "▶", red: "▼" };

  /* verdict word baked into the page at render time — captured on the first patch,
     BEFORE any live overwrite, so we can detect when the live band moves off it. */
  var bakedLabelEn = null;

  /* ── Feed-behind-the-render floor (mirrors risk_state_live.js) ─────────────
     china_risk_state.json is published by the intraday VPS lane, NOT by the
     render, so it can sit a whole session behind the page it patches (the lane
     does not publish on a closed session — a Friday file is what a Sunday
     visitor fetches). This patcher owns the gauge but never touches the hero
     path chart, so a behind-the-render feed had no way to be caught: it
     repainted the score with an older session's number while the chart kept the
     rendered one, and the card shipped 37 beside a line whose Jul 31 point read
     38 (operator report 2026-08-02; 37 was Jul 30's close). Worse, it kept the
     "· delayed HH:MM UTC" chip on, so the STALER half was the half labelled
     live. Capture the rendered session once, before any DOM write, and keep the
     served read whole when the feed cannot match it. */
  var DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
  var bakedSession;   /* undefined until first read; "" when the page carries none */

  /* The session the RENDER is showing: the hero path chart's last graded row and
     the board's own as-of stamp, whichever is newer. Memoised on first call —
     which happens before this file writes anything, so the live overwrite of
     #ms-date can never feed back into the floor. */
  function pageSession() {
    if (bakedSession !== undefined) return bakedSession;
    bakedSession = "";
    try {
      var best = "", t;
      var svg = document.querySelector(".mx5-sc-right .mx5-path-svg[data-points]");
      if (svg) {
        var pts = JSON.parse(svg.getAttribute("data-points") || "[]");
        t = pts.length ? String(pts[pts.length - 1].d || "") : "";
        if (DATE_RE.test(t)) best = t;
      }
      var el = document.getElementById("ms-date");
      t = el ? (el.textContent || "").trim() : "";
      if (DATE_RE.test(t) && t > best) best = t;
      bakedSession = best;
    } catch (e) { bakedSession = ""; }
    return bakedSession;
  }

  /* The session the FEED describes: its build date while the intraday lane is
     live, else the nightly close it was built from. */
  function feedSession(d) {
    var s = d.live_active ? (d.built || "").slice(0, 10)
                          : (d.nightly_asof || (d.built || "").slice(0, 10));
    return DATE_RE.test(s) ? s : "";
  }

  /* True when the feed is at least as current as the rendered page. An unreadable
     feed session counts as behind: failing closed keeps the served render, which
     is always a real single-session snapshot. */
  function feedIsCurrent(d) {
    var floor = pageSession();
    if (!floor) return true;              /* page carries no as-of — nothing to hold */
    var s = feedSession(d);
    return !!s && s >= floor;
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

  /* Patch the China Market State board (#regime-radar panel on china.html). */
  function patchChina(d) {
    var word = document.getElementById("ms-word");
    if (!word) return;
    var disp = d.display || {};
    if (!disp.verdict) return;

    /* Feed behind the render: keep the served read WHOLE — score, gauge, thesis
       and freshness chip alike. Patching any one of them is what split the card. */
    if (!feedIsCurrent(d)) {
      var offPill = document.getElementById("ms-live-pill");
      if (offPill) offPill.classList.remove("on");
      return;
    }

    /* Capture the baked label on first patch before we overwrite anything. */
    if (bakedLabelEn === null) {
      var b0 = word.querySelector(".l-en");
      bakedLabelEn = b0 ? b0.textContent.trim() : "";
    }

    /* #ms-word: update verdict text + preserve / update .arr glyph */
    var arr = word.querySelector(".arr");
    verdictBL(word, disp);
    /* Update or create the .arr glyph — keyed by color to show direction */
    var col = COLOR[disp.verdict];
    if (!arr) {
      arr = document.createElement("span");
      arr.className = "arr";
    }
    if (col) arr.textContent = GLYPH[col] || "▶";
    word.appendChild(arr);

    /* #ms-score + in-gauge numeral */
    var sc = document.getElementById("ms-score");
    if (sc && disp.score != null) sc.textContent = disp.score;
    var scNum = document.getElementById("mx5-score-numeral");
    if (scNum && disp.score != null) scNum.textContent = disp.score;

    /* gauge needle + arc fill follow the live score (else the baked needle
       points at last night's number while #ms-score shows the live one).
       Geometry is read from the SVG's data-gauge-* attrs (US mx5 gauge idiom:
       centre cx,cy; arc-len = π·radius; needle rotate = score/100*180-90) so the
       contract lives in ONE place — the SVG — and never drifts from china.html.j2.
       These are GEOMETRY attrs (transform/dasharray), not colour, so setAttribute is
       correct here; colour stays CSS-driven (.ms-* → --ok/--warn/--act) and is untouched. */
    if (disp.score != null) {
      var g = document.getElementById("mx5-gauge-arc-fill");
      var svg = g ? g.ownerSVGElement : null;
      var cx = svg ? (+svg.getAttribute("data-gauge-cx") || 70) : 70;
      var cy = svg ? (+svg.getAttribute("data-gauge-cy") || 75) : 75;
      var arcLen = svg ? (+svg.getAttribute("data-gauge-arc-len") || 175.93) : 175.93;
      var deg = ((disp.score / 100 * 180) - 90).toFixed(1);
      var ndl = document.getElementById("mx5-gauge-needle");
      if (ndl) ndl.setAttribute("transform", "rotate(" + deg + " " + cx + " " + cy + ")");
      if (g) {
        var filled = (disp.score / 100 * arcLen).toFixed(1);
        var gap = (arcLen - filled).toFixed(1);
        g.setAttribute("stroke-dasharray", filled + " " + gap);
      }
    }

    /* #ms-tick left% */
    var tick = document.getElementById("ms-tick");
    if (tick && disp.score != null) tick.style.left = disp.score + "%";

    /* .v-thesis — headline_en / headline_zh from the feed.
       Use the live block's headline when live_active, else the nightly block's.
       Feed-driven: do NOT hardcode headline prose here. */
    var thesis = document.querySelector(".v-thesis");
    if (thesis && disp.verdict) {
      var blk = (d.live_active && d.live && d.live.verdict) ? d.live : (d.nightly || {});
      var hEn = blk.headline_en || "";
      var hZh = blk.headline_zh || "";
      if (hEn || hZh) setBL(thesis, hEn, hZh);
    }

    /* .v-flip — hide when the live band has moved off the render-baked verdict */
    var flip = document.querySelector(".v-flip");
    if (flip && bakedLabelEn)
      flip.style.display = ((disp.label_en || "") === bakedLabelEn) ? "" : "none";

    /* ms-green / ms-yellow / ms-red class on the .ms-front / .ms wrapper */
    var front = word.closest(".ms-front") || word.closest(".ms");
    if (front && col) {
      front.classList.remove("ms-green", "ms-yellow", "ms-red");
      front.classList.add("ms-" + col);
    }

    /* Aurora backdrop: swap state tint class to match live verdict.
       Default (no au-* class) = green blobs; au-yellow = Mixed; au-red = Risk-off.
       Mirrors the baked server-side class and the same logic in risk_state_live.js. */
    var aur = document.querySelector(".aurora");
    if (aur && col) {
      aur.classList.remove("au-yellow", "au-red");
      if (col === "yellow") aur.classList.add("au-yellow");
      else if (col === "red") aur.classList.add("au-red");
    }

    /* #ms-date — honest freshness wording.
       realtime:false (delayed_min > 0) keeps the "delayed / 延迟" label; the green
       "live" pill stays off. Only lights "live" + pill when realtime:true AND live_active. */
    var dt = document.getElementById("ms-date");
    if (dt && d.live_active) {
      var hhmm = (d.built || "").slice(11, 16);
      /* Bilingual (l-en/l-zh) so the freshness word follows the html[data-lang] CSS
         toggle even when the user switches language AFTER this live patch. A plain
         text node would freeze in whatever language was active at patch time — the
         exact leak setBL exists to prevent (see the doctrine on setBL above). */
      setBL(dt, "· " + (d.realtime ? "live " : "delayed ") + hhmm + " UTC",
                "· " + (d.realtime ? "实时 " : "延迟 ") + hhmm + " UTC");
      dt.classList.toggle("ms-date-live", !!d.realtime);
    } else if (dt && d.nightly_asof) {
      dt.textContent = "· " + d.nightly_asof;
      dt.classList.remove("ms-date-live");
    }

    /* #ms-live-pill — on only when live AND realtime (Yahoo spark is 15-min delayed,
       so realtime:false => pill off, matching the US build doctrine) */
    var pill = document.getElementById("ms-live-pill");
    if (pill) pill.classList.toggle("on", !!(d.live_active && d.realtime));
  }

  function tick() {
    fetch(URL + "?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.schema !== "china_risk_state.v1") return;
        try { patchChina(d); } catch (e) {}
      })
      .catch(function () {});
  }

  if (document.readyState !== "loading") tick();
  else document.addEventListener("DOMContentLoaded", tick);
  setInterval(tick, Math.max(15, POLL) * 1000);
})();

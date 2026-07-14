/* china_risk_state_live.js — progressive enhancement: poll the intraday live China
   risk-state (site/live/china_risk_state.json, written by scripts/build_china_risk_state.py
   every ~30 min during HKEX RTH) and patch the China Market State board on china.html.

   Scoped to china.html only — deliberately lighter than risk_state_live.js (no mx5-*
   v5 gauge/path code; china.html has none of that). Ships as a PAIRED plain-copy asset:
   templates/china_risk_state_live.js must byte-match site/china_risk_state_live.js.

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

  function isZh() {
    try {
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

  /* Patch the China Market State board (#regime-radar panel on china.html). */
  function patchChina(d) {
    var word = document.getElementById("ms-word");
    if (!word) return;
    var disp = d.display || {};
    if (!disp.verdict) return;

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

    /* #ms-score */
    var sc = document.getElementById("ms-score");
    if (sc && disp.score != null) sc.textContent = disp.score;

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

    /* #ms-date — honest freshness wording.
       realtime:false (delayed_min > 0) keeps the "delayed / 延迟" label; the green
       "live" pill stays off. Only lights "live" + pill when realtime:true AND live_active. */
    var dt = document.getElementById("ms-date");
    if (dt && d.live_active) {
      var hhmm = (d.built || "").slice(11, 16);
      var freshWord = d.realtime ? (isZh() ? "实时 " : "live ") : (isZh() ? "延迟 " : "delayed ");
      dt.textContent = "· " + freshWord + hhmm + " UTC";
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

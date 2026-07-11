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
    var arr = word.querySelector(".arr");
    verdictBL(word, disp);
    if (arr) word.appendChild(arr);
    var sc = document.getElementById("ms-score");
    if (sc && disp.score != null) sc.textContent = disp.score;
    var tick = document.getElementById("ms-tick");
    if (tick && disp.score != null) tick.style.left = disp.score + "%";
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

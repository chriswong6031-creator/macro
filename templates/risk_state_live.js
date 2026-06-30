/* risk_state_live.js — progressive enhancement: poll the intraday live risk-state
   (site/live/risk_state.json, written by scripts/build_risk_state.py every few minutes
   during market hours) and patch the Market State headline on macro.html + the Sector
   Central regime banner on sector_central.html.

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
      return (document.documentElement.lang || "").slice(0, 2) === "zh" ||
             document.body.classList.contains("lang-zh");
    } catch (e) { return false; }
  }
  function label(disp) {
    return isZh() ? (disp.label_zh || disp.label_en || disp.verdict)
                  : (disp.label_en || disp.verdict);
  }

  /* macro.html — the Market State board */
  function patchMacro(d) {
    var word = document.getElementById("ms-word");
    if (!word) return;
    var disp = d.display || {};
    if (!disp.verdict) return;
    var arr = word.querySelector(".arr");
    word.textContent = label(disp);
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
    var dt = document.getElementById("ms-date");
    if (dt && d.live_active) {
      dt.textContent = "· " + (isZh() ? "实时 " : "live ") + (d.built || "").slice(11, 16) + " UTC";
      dt.classList.add("ms-date-live");
    }
    var pill = document.getElementById("ms-live-pill");
    if (pill) pill.classList.toggle("on", !!d.live_active);
  }

  /* sector_central.html — the regime banner headline */
  function patchCentral(d) {
    var el = document.getElementById("scc-ms-verdict");
    if (!el) return;
    var disp = d.display || {};
    if (!disp.verdict) return;
    el.textContent = label(disp);
    var tone = { RISK_ON: "rg-on", MIXED: "rg-mix", RISK_OFF: "rg-off" }[disp.verdict] || "rg-mix";
    el.classList.remove("rg-on", "rg-mix", "rg-off");
    el.classList.add(tone);
    var bar = document.getElementById("scc-ms-bar");
    if (bar && disp.score != null) {
      bar.style.width = disp.score + "%";
      bar.style.background = tone === "rg-off" ? "var(--down)"
                          : tone === "rg-on" ? "var(--up)" : "var(--muted)";
    }
  }

  function tick() {
    fetch(URL + "?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.schema !== "risk_state.v1") return;
        try { patchMacro(d); } catch (e) {}
        try { patchCentral(d); } catch (e) {}
      })
      .catch(function () {});
  }

  if (document.readyState !== "loading") tick();
  else document.addEventListener("DOMContentLoaded", tick);
  setInterval(tick, Math.max(15, POLL) * 1000);
})();

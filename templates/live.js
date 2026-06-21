/* live.js — progressive enhancement that patches live prices + the nightly
 * divergence/invalidation signal into the static, nightly-built pages. PURE
 * DISPLAY: it refreshes the price text, a freshness dot, and a small divergence
 * chip; it never touches the scores/verdicts (those are the nightly slow brain).
 * If nothing is configured/served it cleanly no-ops and the page stays exactly as
 * the build rendered it.
 *
 * Two data sources, both optional:
 *   - the Worker /quotes endpoint (window.LIVE_QUOTES_URL) -> freshest prices.
 *   - the static live/overlay.json (written by build_live_overlay) -> the
 *     divergence flag + market sessions (+ a price fallback when no Worker).
 *
 * Cards carry <span class="nb-px" data-sym="600519.SS" data-mkt="cn">. data-sym is
 * the CANONICAL Yahoo/Polygon symbol the build already knows — the browser does NO
 * symbol re-derivation (the old JS heuristic double-suffixed CN/.BJ names). data-mkt
 * only decides the "$" prefix.
 */
(function () {
  if (!window.LIVE_ENABLED) return;                          // static-site no-op
  var URL = window.LIVE_QUOTES_URL || "";
  var POLL = (window.LIVE_POLL_SEC || 60) * 1000;
  var STALE_MIN = window.LIVE_STALE_MIN || 20;
  var OVERLAY = "live/overlay.json";
  var inflight = false, lastTs = 0;

  function nodes() { return [].slice.call(document.querySelectorAll(".nb-px[data-sym]")); }
  function rawSym(el) { return (el.getAttribute("data-sym") || "").trim().toUpperCase(); }
  function regionOf(s) {
    if (/\.HK$/.test(s)) return "hk";
    if (/\.(SS|SZ|BJ)$/.test(s)) return "cn";
    if (/\.(TO|V)$/.test(s)) return "ca";
    return "us";
  }

  function injectStyle() {
    if (document.getElementById("live-px-style")) return;
    var s = document.createElement("style");
    s.id = "live-px-style";
    s.textContent =
      ".nb-px[data-live]::after{content:'';display:inline-block;width:6px;height:6px;" +
      "border-radius:50%;margin-left:5px;vertical-align:middle;background:#16a34a;" +
      "box-shadow:0 0 0 0 rgba(22,163,74,.5);animation:livePulse 2s infinite}" +
      ".nb-px[data-live='stale']::after{background:#9ca3af;animation:none;box-shadow:none}" +
      ".nb-px[data-live='closed']::after{background:#6b7280;animation:none;box-shadow:none}" +
      ".nb-dvg{font-size:10px;font-weight:700;margin-left:5px;padding:0 4px;border-radius:4px;" +
      "vertical-align:middle;white-space:nowrap}" +
      ".nb-dvg.alert{background:#7f1d1d;color:#fecaca}.nb-dvg.watch{background:#78350f;color:#fde68a}" +
      "@media (forced-colors:active){.nb-px[data-live]::after{forced-color-adjust:none;border:1px solid currentColor}}" +
      "@keyframes livePulse{0%{box-shadow:0 0 0 0 rgba(22,163,74,.5)}" +
      "70%{box-shadow:0 0 0 5px rgba(22,163,74,0)}100%{box-shadow:0 0 0 0 rgba(22,163,74,0)}}";
    document.head.appendChild(s);
  }

  function setChip(el, dvg) {
    var sev = dvg && dvg.severity;
    var chip = el.parentNode && el.parentNode.querySelector(".nb-dvg");
    if (sev !== "alert" && sev !== "watch") { if (chip) chip.remove(); return; }
    if (!chip) { chip = document.createElement("span"); chip.className = "nb-dvg"; el.parentNode.appendChild(chip); }
    chip.className = "nb-dvg " + sev;
    chip.textContent = dvg.flag === "band_breach_up" ? "▲ breach"
      : dvg.flag === "band_breach_down" ? "▼ breach" : "⚠";
    chip.title = dvg.detail || "";
  }

  function apply(quotes, overlay) {
    var sessions = (overlay && overlay.sessions) || {};
    var ovT = (overlay && overlay.tickers) || {};
    var serverNow = Date.now();
    nodes().forEach(function (el) {
      var sym = rawSym(el);
      var mkt = el.getAttribute("data-mkt") || "us";
      var q = quotes[sym];
      var ov = ovT[sym];
      // price: prefer the (fresh) Worker quote, else a fresh overlay price.
      var price = null, src = null, stale = true, ageMin = null;
      if (q && q.price != null) {
        price = q.price; src = q.source;
        ageMin = Math.max(0, (serverNow - (q.ts || serverNow)) / 60000);
        stale = ageMin > STALE_MIN;
      } else if (ov && ov.price != null) {
        price = ov.price; src = ov.source; stale = !!ov.stale; ageMin = ov.age_min;
      }
      if (price != null) {
        el.textContent = (mkt === "us" ? "$" : "") + Number(price).toFixed(2);
        var sess = sessions[regionOf(sym)];
        var closed = sess && sess.open === false;
        el.setAttribute("data-live", stale ? (closed ? "closed" : "stale") : "1");
        el.title = (stale ? (closed ? "market closed" : "delayed") : "live") +
          " · " + (src || "?") + (ageMin != null ? " · " + Number(ageMin).toFixed(0) + "m ago" : "");
      }
      // divergence chip (only when fresh + not baseline-stale): the nightly
      // invalidation signal, surfaced to the human watching the same card.
      if (ov && ov.divergence && !ov.stale && !ov.baseline_stale) setChip(el, ov.divergence);
    });
  }

  function getJSON(url, opts) {
    var ctrl = ("AbortController" in window) ? new AbortController() : null;
    var t = ctrl && setTimeout(function () { ctrl.abort(); }, 10000);
    return fetch(url, Object.assign({ signal: ctrl && ctrl.signal }, opts || {}))
      .then(function (r) { if (t) clearTimeout(t); return r.ok ? r.json() : null; })
      .catch(function () { if (t) clearTimeout(t); return null; });
  }

  function tick() {
    if (document.hidden || inflight) return;                 // pause hidden / no overlap
    var ns = nodes();
    if (!ns.length) return;
    var syms = {};
    ns.forEach(function (el) { var s = rawSym(el); if (s) syms[s] = 1; });
    var list = Object.keys(syms);
    if (!list.length) return;
    inflight = true;
    var qP = URL ? getJSON(URL.replace(/\/$/, "") + "/quotes?symbols=" + encodeURIComponent(list.join(",")))
                 : Promise.resolve(null);
    Promise.all([qP, getJSON(OVERLAY)]).then(function (res) {
      inflight = false;
      var quotes = (res[0] && res[0].quotes) || {};
      var ts = (res[0] && res[0].ts) || 0;
      if (ts && ts < lastTs) return;                         // ignore out-of-order
      if (ts) lastTs = ts;
      if (Object.keys(quotes).length || res[1]) apply(quotes, res[1]);
    }, function () { inflight = false; });
  }

  function start() {
    injectStyle();
    tick();
    setInterval(tick, POLL);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) tick(); });
  }
  if (document.readyState !== "loading") start();
  else document.addEventListener("DOMContentLoaded", start);
})();

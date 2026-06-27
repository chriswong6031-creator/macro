/* live.js — progressive enhancement that patches live prices + the nightly
 * divergence/invalidation signal into the static, nightly-built pages. PURE
 * DISPLAY: it refreshes the price text, a freshness dot, and a small divergence
 * chip; it never touches the scores/verdicts (those are the nightly slow brain).
 * If nothing is configured/served it cleanly no-ops and the page stays exactly as
 * the build rendered it.
 *
 * HONESTY: on the current Polygon STANDARD plan (and Yahoo spark) the feed is
 * ~15-MIN DELAYED, not real-time. window.LIVE_DELAYED_MIN (=15) makes the chips show
 * an amber "delayed" dot + "≥15-min delayed" title and SUPPRESSES the green "live"
 * pulse. The green pulse returns automatically once a real-time/websocket plan sets
 * LIVE_DELAYED_MIN=0 (see research/LIVE_DATA_POLYGON.md).
 *
 * Three price sources, in priority order (all optional):
 *   - the Worker /quotes endpoint (window.LIVE_QUOTES_URL) -> freshest, per-page,
 *     lowest-latency US via Polygon (delayed on Standard; real-time after a WS upgrade).
 *   - a static full-universe snapshot JSON (window.LIVE_SNAPSHOT_URL, written by
 *     scripts/build_live_quotes on a GitHub Action, fetched from raw.githubusercontent
 *     CORS) -> keyless ~15-min delayed quotes with NO Worker deploy. Same {ts,quotes} shape.
 *   - the static live/overlay.json (written by build_live_overlay) -> the
 *     divergence flag + market sessions (+ a price fallback when neither above).
 *
 * Cards carry <span class="nb-px" data-sym="600519.SS" data-mkt="cn">. data-sym is
 * the CANONICAL Yahoo/Polygon symbol the build already knows — the browser does NO
 * symbol re-derivation (the old JS heuristic double-suffixed CN/.BJ names). data-mkt
 * decides the "$" prefix ("us") and decimal precision ("fx" -> 4dp). An adjacent
 * <span class="nb-chg" data-sym="..."> (optional) is painted with the % change
 * (green up / red down) computed from prevClose — used by the index/futures strips.
 */
(function () {
  if (!window.LIVE_ENABLED) return;                          // static-site no-op
  var URL = window.LIVE_QUOTES_URL || "";
  var SNAP = window.LIVE_SNAPSHOT_URL || "";                 // keyless no-Worker fallback
  var POLL = (window.LIVE_POLL_SEC || 60) * 1000;
  var STALE_MIN = window.LIVE_STALE_MIN || 20;
  // Vendor plan delay FLOOR (min). Polygon Standard + Yahoo spark are ~15-min delayed,
  // so the whole feed is delayed, never "real-time": when >0 we never show the green
  // "live" pulse — we show an amber "delayed" dot + an honest title. Set to 0 only once
  // a real-time/websocket plan is live (see research/LIVE_DATA_POLYGON.md).
  var DELAYED_MIN = window.LIVE_DELAYED_MIN || 0;
  var FEED_LABEL = window.LIVE_FEED_LABEL || "";   // honest caption for [data-live-label] nodes
  var OVERLAY = "live/overlay.json";
  var inflight = false, lastTs = 0, pendingRefresh = false;

  function nodes() { return [].slice.call(document.querySelectorAll(".nb-px[data-sym]")); }
  function chgNodes() { return [].slice.call(document.querySelectorAll(".nb-chg[data-sym]")); }
  function symNodes() { return [].slice.call(document.querySelectorAll(".nb-px[data-sym],.nb-chg[data-sym]")); }
  function rawSym(el) { return (el.getAttribute("data-sym") || "").trim().toUpperCase(); }
  function fmtPrice(price, mkt) {
    var dec = (mkt === "fx") ? 4 : 2;
    var s;
    try { s = Number(price).toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }); }
    catch (e) { s = Number(price).toFixed(dec); }
    return (mkt === "us" ? "$" : "") + s;
  }
  function paintChg(el, chg, stale) {
    var up = chg >= 0;
    el.textContent = (up ? "+" : "") + Number(chg).toFixed(2) + "%";
    el.classList.remove("up", "down", "stale");
    el.classList.add(up ? "up" : "down");
    if (stale) el.classList.add("stale");      // last-session move, not live
  }
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
      ".nb-px[data-live='delayed']::after{background:#d97706;animation:none;box-shadow:none}" +
      ".nb-dvg{font-size:10px;font-weight:700;margin-left:5px;padding:0 4px;border-radius:4px;" +
      "vertical-align:middle;white-space:nowrap}" +
      ".nb-dvg.alert{background:#7f1d1d;color:#fecaca}.nb-dvg.watch{background:#78350f;color:#fde68a}" +
      ".nb-chg{font-weight:600}.nb-chg.up{color:#16a34a}.nb-chg.down{color:#dc2626}" +
      ".nb-chg.stale{color:#9ca3af;font-weight:500}" +
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

    // Resolve one symbol to a normalised reading, preferring the (fresh) live
    // quote (Worker or snapshot) over a fresh overlay price.
    function pick(sym) {
      var q = quotes[sym], ov = ovT[sym];
      var r = { price: null, src: null, stale: true, ageMin: null, chg: null };
      if (q && q.price != null) {
        r.price = q.price; r.src = q.source;
        var prev = (q.prevClose != null) ? q.prevClose : null;
        r.chg = (q.changePct != null) ? q.changePct : (prev ? (q.price / prev - 1) * 100 : null);
        // never report an age below the vendor delay floor (a delayed quote IS old)
        r.ageMin = Math.max(DELAYED_MIN, Math.max(0, (serverNow - (q.ts || serverNow)) / 60000));
        r.stale = r.ageMin > STALE_MIN;
      } else if (ov && ov.price != null) {
        r.price = ov.price; r.src = ov.source; r.stale = !!ov.stale;
        r.ageMin = (ov.age_min != null) ? Math.max(DELAYED_MIN, ov.age_min) : ov.age_min;
        r.chg = (ov.chg_pct != null) ? ov.chg_pct : null;
      }
      return r;
    }

    nodes().forEach(function (el) {
      var sym = rawSym(el);
      var mkt = el.getAttribute("data-mkt") || "us";
      var p = pick(sym);
      if (p.price != null) {
        el.textContent = fmtPrice(p.price, mkt);
        var sess = sessions[regionOf(sym)];
        var closed = sess && sess.open === false;
        // when fresh: "delayed" (amber, no pulse) on a delayed plan, else "live" (green pulse)
        var state = p.stale ? (closed ? "closed" : "stale") : (DELAYED_MIN > 0 ? "delayed" : "1");
        el.setAttribute("data-live", state);
        var word = state === "closed" ? "market closed"
                 : state === "stale" ? "stale"
                 : state === "delayed" ? ("≥" + DELAYED_MIN + "-min delayed") : "live";
        el.title = word + " · " + (p.src || "?") +
          (p.ageMin != null ? " · " + Number(p.ageMin).toFixed(0) + "m ago" : "");
      }
      // divergence chip (only when fresh + not baseline-stale): the nightly
      // invalidation signal, surfaced to the human watching the same card.
      var ov = ovT[sym];
      if (ov && ov.divergence && !ov.stale && !ov.baseline_stale) setChip(el, ov.divergence);
    });

    // % change chips (index / futures / FX strips): green up, red down, muted stale.
    chgNodes().forEach(function (el) {
      var p = pick(rawSym(el));
      if (p.chg != null) paintChg(el, p.chg, p.stale);
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
    var ns = symNodes();
    if (!ns.length) return;
    var syms = {};
    ns.forEach(function (el) { var s = rawSym(el); if (s) syms[s] = 1; });
    var list = Object.keys(syms);
    if (!list.length) return;
    inflight = true;
    // Worker first (per-page symbol list, real-time US); else the full-universe
    // snapshot (one CDN-cached file, keyless, shared by every browser/page). If a
    // Worker IS set but fails/returns empty this tick, fall back to the snapshot
    // before degrading to the overlay — a transient Worker outage shouldn't blank.
    var qP;
    if (URL) {
      qP = getJSON(URL.replace(/\/$/, "") + "/quotes?symbols=" + encodeURIComponent(list.join(",")))
        .then(function (r) {
          if ((!r || !r.quotes || !Object.keys(r.quotes).length) && SNAP) return getJSON(SNAP);
          return r;
        });
    } else {
      qP = SNAP ? getJSON(SNAP) : Promise.resolve(null);
    }
    function done() {
      inflight = false;
      // a refresh() requested mid-flight (SPA navigated to a new symbol) runs now.
      if (pendingRefresh) { pendingRefresh = false; tick(); }
    }
    Promise.all([qP, getJSON(OVERLAY)]).then(function (res) {
      var quotes = (res[0] && res[0].quotes) || {};
      var ts = (res[0] && res[0].ts) || 0;
      if (!(ts && ts < lastTs)) {                            // ignore out-of-order
        if (ts) lastTs = ts;
        if (Object.keys(quotes).length || res[1]) apply(quotes, res[1]);
      }
      done();
    }, done);
  }

  // Stamp an honest feed caption into any [data-live-label] element the build placed
  // (e.g. "≈15-min delayed (Polygon Standard / Yahoo)"). No-op if none / no label.
  function paintLabel() {
    if (!FEED_LABEL) return;
    [].slice.call(document.querySelectorAll("[data-live-label]"))
      .forEach(function (el) { el.textContent = FEED_LABEL; el.title = FEED_LABEL; });
  }

  function start() {
    injectStyle();
    paintLabel();
    // Refresh hook for SPA pages (the single-stock view re-renders .nb-px nodes
    // client-side on hashchange) — they call this right after setting data-sym.
    // If a poll is in flight, defer so the new symbol isn't dropped.
    window.LiveQuotes = { refresh: function () { if (inflight) pendingRefresh = true; else tick(); } };
    tick();
    setInterval(tick, POLL);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) tick(); });
  }
  if (document.readyState !== "loading") start();
  else document.addEventListener("DOMContentLoaded", start);
})();

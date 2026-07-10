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
  if (window.__mmLiveInit) return; window.__mmLiveInit = true; // idempotency guard — second include is a no-op
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
  var _paused = false, _timer = null;

  function nodes() { return [].slice.call(document.querySelectorAll(".nb-px[data-sym]")); }
  function chgNodes() { return [].slice.call(document.querySelectorAll(".nb-chg[data-sym]")); }
  function symNodes() { return [].slice.call(document.querySelectorAll(".nb-px[data-sym],.nb-chg[data-sym]")); }
  function rawSym(el) { return (el.getAttribute("data-sym") || "").trim().toUpperCase(); }
  function fmtPrice(price, mkt) {
    if (mkt === "crypto") {                       // "$" + thousands, no decimals (matches the baked BTC header)
      try { return "$" + Number(price).toLocaleString(undefined, { maximumFractionDigits: 0 }); }
      catch (e) { return "$" + Math.round(Number(price)); }
    }
    var dec = (mkt === "fx") ? 4 : 2;
    var s;
    try { s = Number(price).toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }); }
    catch (e) { s = Number(price).toFixed(dec); }
    return (mkt === "us" ? "$" : "") + s;
  }
  // Crypto trades 24/7 and is refreshed on its own hourly cadence, so it goes stale
  // only when a scheduled refresh is actually MISSED (~65 min), not at the 20-min
  // equity threshold — otherwise a healthy hourly BTC quote would read grey for
  // most of every hour. ageMin already carries the DELAYED_MIN vendor floor.
  function isStale(mkt, ageMin, fallback) {
    if (ageMin == null) return !!fallback;
    var lim = (mkt === "crypto") ? (window.LIVE_CRYPTO_STALE_MIN || 65) : STALE_MIN;
    return ageMin > lim;
  }
  function paintChg(el, chg, stale) {
    var up = chg >= 0;
    el.textContent = (up ? "+" : "") + Number(chg).toFixed(2) + "%";
    el.classList.remove("up", "down", "stale");
    el.classList.add(up ? "up" : "down");
    if (stale) el.classList.add("stale");      // last-session move, not live
  }
  function regionOf(s) {
    if (/-USD$/.test(s)) return "crypto";      // 24/7 — no session table -> never "market closed"
    if (/\.HK$/.test(s)) return "hk";
    if (/\.(SS|SZ|BJ)$/.test(s)) return "cn";
    if (/\.(TO|V)$/.test(s)) return "ca";
    // Foreign index tickers (^-prefixed): map to their exchange region so the
    // staleness chip uses the right session clock.  For regions where the overlay
    // carries no session entry (jp/kr/tw/gb/eu) sessions[region] will be undefined
    // and closed=false — the staleness state falls back to "stale" never "closed",
    // which is the correct safe default (we simply don't know).
    if (s === "^HSI")      return "hk";
    if (s === "^GSPC")     return "us";
    if (s === "^GSPTSE")   return "ca";
    if (s === "^N225")     return "jp";
    if (s === "^KS11")     return "kr";
    if (s === "^TWII")     return "tw";
    if (s === "^FTSE")     return "gb";
    if (s === "^STOXX50E") return "eu";
    // 000001.SS / generic .SS / .SZ / .BJ already caught above; any remaining
    // ^-index without an explicit mapping falls through to "us" as before.
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
      "70%{box-shadow:0 0 0 5px rgba(22,163,74,0)}100%{box-shadow:0 0 0 0 rgba(22,163,74,0)}}" +
      "@media (prefers-reduced-motion:reduce){.nb-px[data-live]::after{animation:none}}" +
      "html.fx-min .nb-px[data-live]::after{animation:none}";
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
        var stale = isStale(mkt, p.ageMin, p.stale);
        // when fresh: "delayed" (amber, no pulse) on a delayed plan, else "live" (green pulse)
        var state = stale ? (closed ? "closed" : "stale") : (DELAYED_MIN > 0 ? "delayed" : "1");
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

    // % change chips (index / futures / FX / crypto strips): green up, red down, muted stale.
    chgNodes().forEach(function (el) {
      var mkt = el.getAttribute("data-mkt") || "us";
      var p = pick(rawSym(el));
      if (p.chg != null) paintChg(el, p.chg, isStale(mkt, p.ageMin, p.stale));
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
    if (_paused || document.hidden || inflight) return;      // pause: explicit / hidden / no overlap
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

  function _startTimer() {
    if (_timer) clearInterval(_timer);
    _timer = setInterval(tick, POLL);
  }

  function start() {
    injectStyle();
    paintLabel();
    // Pause/resume API for callers that want to suppress polling (e.g. a settings
    // toggle persisted in localStorage as liveOff=1).
    // .pause()  — stops the interval; marks _paused so tick() is a no-op even if called.
    // .resume() — clears the paused flag, restarts the interval, fires an immediate tick.
    // .refresh() — existing SPA hook; honours the paused flag (paused = refresh is a no-op).
    window.LiveQuotes = {
      refresh: function () {
        if (_paused) return;
        if (inflight) pendingRefresh = true; else tick();
      },
      pause: function () {
        _paused = true;
        if (_timer) { clearInterval(_timer); _timer = null; }
      },
      resume: function () {
        _paused = false;
        _startTimer();
        tick();                                              // immediate tick on resume
      }
    };
    // Boot gate: if the user previously chose to disable live quotes, start paused
    // (no initial tick, no interval) so we fire zero network requests.
    try { if (localStorage.getItem("liveOff") === "1") { _paused = true; } } catch (e) {}
    if (!_paused) {
      tick();
      _startTimer();
    }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !_paused) tick();
    });
  }
  if (document.readyState !== "loading") start();
  else document.addEventListener("DOMContentLoaded", start);
})();

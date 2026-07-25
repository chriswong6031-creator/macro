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
  // Live breadth (Phase 2, LIVE_TAPE_SCOREBOARD_MASTERPLAN §4): the intraday
  // adv/dec payload the breadth poller publishes beside quotes.json. Fetched on
  // the same 60s tick ONLY when the page carries the sbx scoreboard; absent or
  // stale payload -> the baked "last close" numbers stay untouched.
  var BREADTH = window.LIVE_BREADTH_URL ||
    (SNAP ? SNAP.replace(/quotes\.json(\?.*)?$/, "breadth.json") : "live/breadth.json");
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
  // ── Live Tape (/ws/tape) state ──
  // TAPE_SYMS: the six instruments the server relay fans out; the ws only opens
  // if the page actually carries one of these tiles. _wsSock: the socket (or
  // null). _wsLast[sym] = wall-clock (ms) we last applied a ws tick for `sym` —
  // used to make a ws quote win over the poller while the socket is live-feeding.
  var TAPE_SYMS = { "ES=F": 1, "NQ=F": 1, "YM=F": 1, "RTY=F": 1, "^TNX": 1, "DX-Y.NYB": 1 };
  var _wsSock = null, _wsLast = {}, _wsRetry = 0, _wsTimer = null, _wsClosed = false;
  var WS_FRESH_MS = 30000;   // a ws tick shields a symbol from the poller this long
  // Ops kill switch (config.yml live.ws_tape_enabled -> LIVE_WS_TAPE). Defaults
  // ON when the flag is absent (older live_config.js) so the tape works the moment
  // the relay is deployed, without a page rebuild.
  var WS_TAPE = (window.LIVE_WS_TAPE !== false);

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
  // ^TNX transform (Live Tape): Yahoo quotes the 10-year yield as yield×10
  // (42.5 => 4.25%). Price tiles with data-fmt="tnx" show price/10 + "%"; the
  // delta is shown in basis points (bps = price-delta × 10) rather than percent,
  // which is how rate moves are read. bpsDelta needs the absolute price delta;
  // prevClose (raw yield×10) is threaded through the reading for that.
  function isTnx(el) { return (el.getAttribute("data-fmt") || "") === "tnx"; }
  // SCALE-AWARE (go-live 2026-07-24): the feeds disagree on ^TNX units — the
  // relay's REST-fallback frames deliver percent directly (live-verified 4.679
  // while the 10Y was 4.68%), whereas the ×10 index convention (46.79) exists
  // on other paths. A 10Y above 15% or below 1.5-on-the-×10-scale hasn't traded
  // since 1981, so the threshold cleanly separates the two encodings.
  function tnxPct(v) { v = Number(v); return v > 15 ? v / 10 : v; }
  function fmtTnxPrice(price) { return tnxPct(price).toFixed(2) + "%"; }
  function tnxBps(price, prevClose) {
    // delta in yield POINTS (both sides scale-normalized) × 100 => bps
    if (prevClose == null) return null;
    return (tnxPct(price) - tnxPct(prevClose)) * 100;
  }
  function paintChg(el, chg, stale, reading) {
    // data-fmt="tnx": render the delta in bps (from the absolute price delta),
    // not percent. Falls back to percent if prevClose is unavailable.
    if (isTnx(el) && reading && reading.price != null) {
      var bps = tnxBps(reading.price, reading.prevClose);
      if (bps != null) {
        var upB = bps >= 0;
        el.textContent = (upB ? "+" : "") + Number(bps).toFixed(0) + " bps";
        el.classList.remove("up", "down", "dn", "stale");
        el.classList.add(upB ? "up" : "down");
        if (stale) el.classList.add("stale");
        return;
      }
    }
    var up = chg >= 0;
    el.textContent = (up ? "+" : "") + Number(chg).toFixed(2) + "%";
    // "dn" is the render-time twin of "down" on mx5 tiles — drop it too, or a tile
    // baked dn keeps its old down-colour rule after a live up-tick (green +x% in zh)
    el.classList.remove("up", "down", "dn", "stale");
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
      /* zh 红涨绿跌: swap up→red, down→green */
      'html[data-lang="zh"] .nb-chg.up{color:#dc2626}html[data-lang="zh"] .nb-chg.down{color:#16a34a}' +
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

  // ── Shared per-node patch (used by BOTH the poller and the /ws/tape socket) ──
  // reading = { price, src, stale, ageMin, chg, prevClose, basis } — a normalised
  // per-symbol quote. Keeping ONE patch path means the websocket tape and the
  // 60s poller paint tiles identically (spec §3: refactor, don't duplicate).
  function patchPriceNode(el, r, sessions) {
    if (r.price == null) return;
    var sym = rawSym(el);
    var mkt = el.getAttribute("data-mkt") || "us";
    // data-fmt="tnx": ^TNX quotes yield×10 -> show yield% (price/10).
    // data-bare: panel opts out of the "$" prefix (macro MARKETS tiles mix ETF
    // quotes with index levels — a $ on half the row reads as an error).
    el.textContent = isTnx(el)
      ? fmtTnxPrice(r.price)
      : (el.hasAttribute("data-bare")
          ? fmtPrice(r.price, mkt).replace(/^\$/, "")
          : fmtPrice(r.price, mkt));
    var sess = sessions && sessions[regionOf(sym)];
    var closed = sess && sess.open === false;
    var stale = isStale(mkt, r.ageMin, r.stale);
    // when fresh: "delayed" (amber, no pulse) on a delayed plan, else "live"
    // (green pulse). A websocket TRADE tick (basis "quote", DELAYED_MIN 0 path)
    // earns the live pulse; a "poll"-basis reading stays delayed/stale honest.
    var live = r.basis === "quote";
    var state = stale ? (closed ? "closed" : "stale")
                      : (live && DELAYED_MIN === 0 ? "1"
                         : (DELAYED_MIN > 0 ? "delayed" : "1"));
    el.setAttribute("data-live", state);
    var word = state === "closed" ? "market closed"
             : state === "stale" ? "stale"
             : state === "delayed" ? ("≥" + DELAYED_MIN + "-min delayed") : "live";
    el.title = word + " · " + (r.src || "?") +
      (r.ageMin != null ? " · " + Number(r.ageMin).toFixed(0) + "m ago" : "");
  }
  function patchChgNode(el, r) {
    var mkt = el.getAttribute("data-mkt") || "us";
    if (r.chg == null && !(isTnx(el) && r.price != null)) return;
    paintChg(el, r.chg, isStale(mkt, r.ageMin, r.stale), r);
  }
  // Patch every .nb-px / .nb-chg node bound to `sym` from one reading. Returns
  // true if it touched anything (so the ws layer knows a tape symbol landed).
  function patchSymbol(sym, r, sessions, ovT) {
    var touched = false;
    nodes().forEach(function (el) {
      if (rawSym(el) !== sym) return;
      patchPriceNode(el, r, sessions);
      touched = true;
      // divergence chip (only when fresh + not baseline-stale): the nightly
      // invalidation signal, surfaced to the human watching the same card.
      var ov = ovT && ovT[sym];
      if (ov && ov.divergence && !ov.stale && !ov.baseline_stale) setChip(el, ov.divergence);
    });
    chgNodes().forEach(function (el) {
      if (rawSym(el) !== sym) return;
      patchChgNode(el, r);
      touched = true;
    });
    return touched;
  }

  function apply(quotes, overlay) {
    var sessions = (overlay && overlay.sessions) || {};
    var ovT = (overlay && overlay.tickers) || {};
    var serverNow = Date.now();

    // Resolve one symbol to a normalised reading, preferring the (fresh) live
    // quote (Worker or snapshot) over a fresh overlay price.
    function pick(sym) {
      var q = quotes[sym], ov = ovT[sym];
      var r = { price: null, src: null, stale: true, ageMin: null, chg: null, prevClose: null, basis: null };
      if (q && q.price != null) {
        r.price = q.price; r.src = q.source; r.basis = "poll";
        var prev = (q.prevClose != null) ? q.prevClose : null;
        r.prevClose = prev;
        r.chg = (q.changePct != null) ? q.changePct : (prev ? (q.price / prev - 1) * 100 : null);
        // never report an age below the vendor delay floor (a delayed quote IS old)
        r.ageMin = Math.max(DELAYED_MIN, Math.max(0, (serverNow - (q.ts || serverNow)) / 60000));
        r.stale = r.ageMin > STALE_MIN;
      } else if (ov && ov.price != null) {
        r.price = ov.price; r.src = ov.source; r.stale = !!ov.stale; r.basis = "poll";
        r.prevClose = (ov.prev_close != null) ? ov.prev_close : null;
        r.ageMin = (ov.age_min != null) ? Math.max(DELAYED_MIN, ov.age_min) : ov.age_min;
        r.chg = (ov.chg_pct != null) ? ov.chg_pct : null;
      }
      return r;
    }

    // Union of every symbol on the page (price OR chg node) — patch each once
    // through the shared path.
    var seen = {};
    symNodes().forEach(function (el) {
      var sym = rawSym(el);
      if (!sym || seen[sym]) return;
      seen[sym] = 1;
      var r = pick(sym);
      // Freshness guard: don't let a poll reading overwrite a strictly-fresher
      // websocket tick already on this symbol.
      if (r.price != null && !_wsFresher(sym, serverNow)) patchSymbol(sym, r, sessions, ovT);
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
    var bP = document.getElementById("sbx-stamp") ? getJSON(BREADTH) : Promise.resolve(null);
    Promise.all([qP, getJSON(OVERLAY), bP]).then(function (res) {
      var quotes = (res[0] && res[0].quotes) || {};
      var ts = (res[0] && res[0].ts) || 0;
      if (!(ts && ts < lastTs)) {                            // ignore out-of-order
        if (ts) lastTs = ts;
        if (Object.keys(quotes).length || res[1]) apply(quotes, res[1]);
      }
      if (res[2]) applyBreadth(res[2]);
      done();
    }, done);
  }

  // ── Live breadth patch (sbx scoreboard, us_stocks) ─────────────────────────
  // Stance bands MIRROR scripts/build_site.py::_breadth_read exactly — if those
  // thresholds or words change, change these with them (render test pins baked).
  var SBX_STANCE = {
    broad: { l: ["broad", "广泛"], v: ["The advance is well-supported across the full 1,500", "上涨在整个 1500 只股票中获得良好支撑"], tone: "pos" },
    thin:  { l: ["thin", "稀薄"], v: ["Few names hold their trend — rallies here are fragile", "守住趋势的个股很少 — 此时的反弹较脆弱"], tone: "neg" },
    mixed: { l: ["mixed", "参差"], v: ["No clear breadth edge either way", "广度上没有明显的方向性优势"], tone: "muted" }
  };
  var SBX_WORDS = {
    w50hi: ["healthy participation", "参与度健康"], w50lo: ["below half — thin tape", "不足半数 — 盘面稀薄"], w50mid: ["middling", "中等水平"],
    w200ok: ["long-term trend intact", "长期趋势完好"], w200bad: ["long-term trend damaged", "长期趋势受损"],
    nnhup: ["more breakouts than breakdowns", "创新高多于创新低"], nnhdn: ["more stocks breaking down than out", "创新低多于创新高"]
  };
  function sbxBi(pair) {
    return '<span class="l-en">' + pair[0] + '</span><span class="l-zh">' + pair[1] + '</span>';
  }
  function sbxSet(id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; }
  function applyBreadth(b) {
    var c = b && b.comp;
    if (!c || typeof c.adv !== "number" || typeof c.dec !== "number") return;
    // freshness + session honesty: patch only a payload from an open/near session,
    // stamped within the last 25 min — otherwise the baked close numbers stand.
    var age = b.asof ? (Date.now() - new Date(b.asof).getTime()) / 60000 : 1e9;
    if (age > 25 || b.session === "closed") return;
    var n = c.n || (c.adv + c.dec + (c.unch || 0)) || 1;
    var unch = (typeof c.unch === "number") ? c.unch : Math.max(0, n - c.adv - c.dec);
    var den = (c.adv + c.dec + unch) || 1;
    sbxSet("sbx-adv", c.adv.toLocaleString("en-US"));
    sbxSet("sbx-dec", c.dec.toLocaleString("en-US"));
    var ba = document.getElementById("sbx-bar-a"), bu = document.getElementById("sbx-bar-u"), bd = document.getElementById("sbx-bar-d");
    if (ba) ba.style.width = (100 * c.adv / den).toFixed(1) + "%";
    if (bu) bu.style.width = (100 * unch / den).toFixed(1) + "%";
    if (bd) bd.style.width = (100 * c.dec / den).toFixed(1) + "%";
    if (typeof c.pa50 === "number") {
      sbxSet("sbx-v50", Math.round(c.pa50) + "%");
      var wl50 = document.getElementById("sbx-wl50");
      if (wl50) { wl50.classList.toggle("low", c.pa50 < 50); wl50.firstElementChild.style.width = Math.round(c.pa50) + "%"; }
      sbxSet("sbx-w50", sbxBi(c.pa50 >= 60 ? SBX_WORDS.w50hi : (c.pa50 <= 40 ? SBX_WORDS.w50lo : SBX_WORDS.w50mid)));
    }
    if (typeof c.pa200 === "number") {
      sbxSet("sbx-v200", Math.round(c.pa200) + "%");
      var wl2 = document.getElementById("sbx-wl200");
      if (wl2) { wl2.classList.toggle("low", c.pa200 < 50); wl2.firstElementChild.style.width = Math.round(c.pa200) + "%"; }
      sbxSet("sbx-w200", sbxBi(c.pa200 >= 50 ? SBX_WORDS.w200ok : SBX_WORDS.w200bad));
    }
    if (typeof c.net_nh === "number") {
      var nnh = document.getElementById("sbx-nnh");
      if (nnh) {
        nnh.textContent = (c.net_nh >= 0 ? "+" : "−") + Math.abs(c.net_nh);
        nnh.classList.toggle("pos", c.net_nh >= 0); nnh.classList.toggle("neg", c.net_nh < 0);
      }
      sbxSet("sbx-nnhw", sbxBi(c.net_nh >= 0 ? SBX_WORDS.nnhup : SBX_WORDS.nnhdn));
    }
    var st = (typeof c.pa50 === "number" && c.pa50 >= 60 && c.net_nh >= 0) ? SBX_STANCE.broad
           : ((typeof c.pa50 === "number" && c.pa50 <= 40) || c.net_nh < 0) ? SBX_STANCE.thin
           : SBX_STANCE.mixed;
    var sl = document.getElementById("sbx-stance-l");
    if (sl) { sl.innerHTML = sbxBi(st.l); sl.className = st.tone; }
    sbxSet("sbx-stance-v", sbxBi(st.v));
    var stamp = document.getElementById("sbx-stamp");
    if (stamp) {
      stamp.classList.add("live");
      var et = new Date(b.asof).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
      var dm = (typeof b.delay_min === "number") ? b.delay_min : 15;
      stamp.innerHTML = '<span class="sbx-dot"></span>' +
        sbxBi(["≈" + dm + "-min delayed · " + et + " ET", "约" + dm + "分钟延迟 · 美东 " + et]);
    }
  }

  // Stamp an honest feed caption into any [data-live-label] element the build placed
  // (e.g. "≈15-min delayed (Polygon Standard / Yahoo)"). No-op if none / no label.
  // Single-language render + langchange re-paint (an attribute/textContent can't hold
  // l-en/l-zh spans), same idiom as theme.js placeholders.
  function paintLabel() {
    var zh = document.documentElement.getAttribute("data-lang") === "zh";
    var lab = (zh && window.LIVE_FEED_LABEL_ZH) || FEED_LABEL;
    if (!lab) return;
    [].slice.call(document.querySelectorAll("[data-live-label]"))
      .forEach(function (el) { el.textContent = lab; el.title = lab; });
  }

  // ── Live Tape websocket (same-origin /ws/tape) ────────────────────────────
  // A server-fanout socket that ticks the six macro futures/index/yield tiles
  // sub-5s. It is a pure ENHANCEMENT over the poller: the poll path already
  // covers these tiles, so on ANY error/close we simply stop and let polling
  // carry the page (spec §3). A ws tick wins over a subsequent poll for the same
  // symbol for WS_FRESH_MS (freshness guard) so the fresher number stays put.
  function _wsFresher(sym, now) {
    var t = _wsLast[sym];
    return t != null && (now - t) < WS_FRESH_MS;
  }
  function _pageHasTapeSym() {
    var found = false;
    symNodes().forEach(function (el) { if (TAPE_SYMS[rawSym(el)]) found = true; });
    return found;
  }
  function _applyWsQuote(q) {
    // q = {sym, price, chgPct, ts, basis}. Build a reading and patch via the
    // SHARED path. Drop an out-of-order frame ONLY within the same basis (a late
    // "quote" can't clobber a fresher "quote"); a "poll" fallback refreshes even
    // with an older data ts (its quote_ts may be 15 min old) — mirrors the relay
    // guard, or a dead upstream would freeze the tile on an ever-staler number.
    if (!q || !q.sym || q.price == null) return;
    if (!TAPE_SYMS[q.sym]) return;
    var basis = q.basis || "quote";
    var prevTs = _wsLast[q.sym + "|ts"] || 0;
    var prevBasis = _wsLast[q.sym + "|basis"];
    if (q.ts && basis === prevBasis && q.ts < prevTs) return;   // same-basis out-of-order — drop
    var now = Date.now();
    _wsLast[q.sym] = now;
    if (q.ts) _wsLast[q.sym + "|ts"] = q.ts;
    _wsLast[q.sym + "|basis"] = basis;
    var ageMin = q.ts ? Math.max(0, (now - q.ts) / 60000) : 0;
    // A "poll"-basis relay reading is honestly downgraded (never the live pulse);
    // a "quote"-basis tick is a real trade print. ageMin drives the stale chip.
    var r = {
      price: q.price, src: "ws:" + (q.basis || "quote"),
      stale: ageMin > STALE_MIN, ageMin: ageMin,
      chg: (q.chgPct != null) ? q.chgPct : null,
      prevClose: (q.prevClose != null) ? q.prevClose : null,
      basis: q.basis || "quote"
    };
    patchSymbol(q.sym, r, null, null);
  }
  function _tapeWsUrl() {
    try {
      var proto = (location.protocol === "https:") ? "wss:" : "ws:";
      return proto + "//" + location.host + "/ws/tape";
    } catch (e) { return null; }
  }
  function startTape() {
    if (!WS_TAPE) return;                              // ops kill switch -> poll only
    if (_wsClosed || _wsSock) return;                  // one socket per page
    if (!("WebSocket" in window)) return;              // ancient browser -> poll only
    if (!_pageHasTapeSym()) return;                    // no tape tile here -> skip
    var url = _tapeWsUrl();
    if (!url) return;
    var sock;
    try { sock = new WebSocket(url); }
    catch (e) { return; }                              // blocked/refused -> poll covers it
    _wsSock = sock;
    sock.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (!msg || msg.type === "heartbeat") return;    // 20s server keepalive
      if (document.hidden) return;                     // don't paint a hidden tab
      _applyWsQuote(msg);
    };
    sock.onopen = function () { _wsRetry = 0; };
    sock.onclose = function () { _wsSock = null; _scheduleWsReconnect(); };
    sock.onerror = function () { try { sock.close(); } catch (e) {} };  // -> onclose -> reconnect
  }
  function _scheduleWsReconnect() {
    if (_wsClosed || _paused) return;                  // paused/torn-down -> stay on poller
    if (_wsTimer) clearTimeout(_wsTimer);
    // exponential backoff (1s..30s); the poller keeps the tiles live meanwhile.
    var delay = Math.min(30000, 1000 * Math.pow(2, _wsRetry++));
    _wsTimer = setTimeout(function () { if (!document.hidden) startTape(); }, delay);
  }
  function stopTape() {
    _wsClosed = true;
    if (_wsTimer) { clearTimeout(_wsTimer); _wsTimer = null; }
    if (_wsSock) { try { _wsSock.close(); } catch (e) {} _wsSock = null; }
  }

  function _startTimer() {
    if (_timer) clearInterval(_timer);
    _timer = setInterval(tick, POLL);
  }

  function start() {
    injectStyle();
    paintLabel();
    document.addEventListener("langchange", paintLabel);
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
        stopTape();                                          // drop the tape socket too
      },
      resume: function () {
        _paused = false;
        _wsClosed = false;
        _startTimer();
        tick();                                              // immediate tick on resume
        startTape();
      }
    };
    // Live prices are always on (the settings toggle was removed); clear any
    // previously stored pause so nobody stays stranded off.
    try { localStorage.removeItem("liveOff"); } catch (e) {}
    if (!_paused) {
      tick();
      _startTimer();
      startTape();                                           // open /ws/tape if a tape tile is present
    }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !_paused) { tick(); if (!_wsSock) { _wsClosed = false; startTape(); } }
    });
  }
  if (document.readyState !== "loading") start();
  else document.addEventListener("DOMContentLoaded", start);
})();

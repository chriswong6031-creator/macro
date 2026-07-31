/* Theme + language toggles, shared across pages. The no-flash init runs inline
   in <head> (sets data-theme AND data-lang before paint); this file wires the
   buttons and broadcasts change events. */
(function () {
  var docEl = document.documentElement;

  /* ---- custom scrollbars for self-contained pages -------------------------
     theme.css carries the site-wide themed scrollbar (see its --sb-* tokens),
     but a handful of self-contained pages (the vector / strategy-detail family,
     narrative_radar, validation_timeline) load this script WITHOUT theme.css.
     Mirror the same scrollbar here so "our own scrollbars" reach every page.
     Gated on theme.css being ABSENT to avoid a redundant re-declare on the pages
     that do link it; --muted falls back to the vector palette's --grid then a
     hard colour so it styles on every palette. Idempotent by id. */
  (function injectScrollbarCss() {
    if (document.querySelector('link[href*="theme.css"]')) return;
    if (document.getElementById('mdx-sb-css')) return;
    var rest = 'color-mix(in srgb, var(--muted, var(--grid, #8b93a1)) 34%, transparent)';
    var hov = 'color-mix(in srgb, var(--muted, var(--grid, #8b93a1)) 60%, transparent)';
    var s = document.createElement('style');
    s.id = 'mdx-sb-css';
    s.textContent =
        '*{scrollbar-width:thin;scrollbar-color:' + rest + ' transparent}'
      + '*::-webkit-scrollbar{width:11px;height:11px}'
      + '*::-webkit-scrollbar-track{background:transparent}'
      + '*::-webkit-scrollbar-thumb{background:' + rest + ';border-radius:999px;'
      +   'border:3px solid transparent;background-clip:padding-box}'
      + '*::-webkit-scrollbar-thumb:hover{background:' + hov + '}'
      + '*::-webkit-scrollbar-corner{background:transparent}';
    (document.head || docEl).appendChild(s);
  })();

  /* Supabase account config — BAKED IN at build time (scripts/build_site.py
     replaces the token below with the project URL + public publishable key, or
     `null` for a local-only build). A page that sets window.SUPABASE_CFG inline
     (e.g. watchlist.html) wins, so the value is identical either way. The
     publishable key is PUBLIC by design; per-user isolation is enforced by RLS. */
  window.SUPABASE_CFG = window.SUPABASE_CFG || /*__SUPABASE_CFG__*/null;

  /* ---- Google Analytics 4 (gtag.js) ---------------------------------------
     Injected once on EVERY page via this one shared script (every page loads
     theme.js), so there's no per-template tag to maintain. Loads gtag.js async
     and queues the first page_view via dataLayer. Skips localhost / file:// so
     local dev, previews and the admin tool never pollute the property. Set
     GA4_ID to '' to disable site-wide.

     GFW NOTE: www.googletagmanager.com is blocked in mainland China. The tag is
     async (never render-blocking), but a blocked request still hangs the socket
     until TCP timeout and spams the console with ERR_CONNECTION errors. To keep
     China page loads clean we (a) gate analytics behind an explicit opt-in flag
     so it stays dormant by default, (b) swallow the load error via onerror, and
     (c) defer injection to the idle window so it never competes with paint. */
  var GA4_ID = 'G-BZTZ9W1BBB';
  (function loadGA4() {
    // Off unless explicitly enabled (set window.ENABLE_GA4 = true on the
    // US-served origin only — never on the China mirror). Dormant by default.
    if (window.ENABLE_GA4 !== true) return;
    if (!GA4_ID || window.__ga4_loaded) return;
    var h = location.hostname;
    if (!h || h === 'localhost' || h === '127.0.0.1' || h === '[::1]') return;
    window.__ga4_loaded = true;
    window.dataLayer = window.dataLayer || [];
    function gtag() { dataLayer.push(arguments); }
    window.gtag = gtag;
    gtag('js', new Date());
    gtag('config', GA4_ID);
    var inject = function () {
      var s = document.createElement('script');
      s.async = true;
      s.referrerPolicy = 'no-referrer-when-downgrade';
      s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA4_ID;
      s.onerror = function () { /* blocked (e.g. GFW) — fail silently */ };
      (document.head || document.documentElement).appendChild(s);
    };
    // Wait for idle so a slow/blocked tag never delays interaction.
    if (window.requestIdleCallback) requestIdleCallback(inject, { timeout: 4000 });
    else setTimeout(inject, 1200);
  })();

  /* ---- Umami web analytics (cloud.umami.is) -------------------------------
     Privacy-first, cookieless pageview analytics for the whole site — loaded
     once here so every page is tracked with no per-template tag. Unlike GA4
     this is ON by default: Umami sets no cookies and collects no PII, so no
     consent banner is needed. Skips localhost / 127.0.0.1 / file:// (so local
     dev, previews and the admin console never pollute the stats) and skips the
     admin.* host itself. Loads async at idle and fails silently if the host is
     unreachable (e.g. a strict network / GFW), so it can never block paint or
     spam the console. The website id is PUBLIC — it ships in the page tag
     either way. View the data at https://cloud.umami.is (reading it back via
     API needs a paid plan; the admin Analytics tab degrades to a link-out). */
  var UMAMI_WEBSITE_ID = 'd7734c31-99fa-4949-bcde-bec41fbfb2cf';
  (function loadUmami() {
    if (!UMAMI_WEBSITE_ID || window.__umami_loaded) return;
    var h = location.hostname;
    if (!h || h === 'localhost' || h === '127.0.0.1' || h === '[::1]') return;
    if (h.split('.')[0] === 'admin') return;          // don't track the console
    window.__umami_loaded = true;
    var inject = function () {
      var s = document.createElement('script');
      s.async = true;
      s.defer = true;
      s.src = 'https://cloud.umami.is/script.js';
      s.setAttribute('data-website-id', UMAMI_WEBSITE_ID);
      s.onerror = function () { /* unreachable (e.g. GFW) — fail silently */ };
      (document.head || document.documentElement).appendChild(s);
    };
    if (window.requestIdleCallback) requestIdleCallback(inject, { timeout: 4000 });
    else setTimeout(inject, 1200);
  })();

  /* ---- first-party analytics beacon (self-hosted, granular, GFW-safe) ------
     Sends page views + in-page navigation + dwell + scroll + clicks + committed
     searches to the SAME-ORIGIN /api/collect (the macro FastAPI on :8000). Mirrors
     the Umami loader's guards (skip localhost + admin.*), and only fires on the
     canonical mastermind-x.com origin (the GitHub-Pages mirror has no /api/collect).
     Unlike GA4/Umami this is a first-party endpoint on our own VPS, so it reaches
     mainland China (no blocked third-party host) — but it still fails silently on any
     network error so it can never block paint or spam the console. The visitor id
     (mm_aid cookie), IP, and geolocation are stamped SERVER-side; this only makes a
     per-tab session id + a coarse device fingerprint and fires batched beacons.
     window.mmTrack is exposed so the nav-search + terminal-jump handlers can log
     intent before navigating away. */
  (function loadMMAnalytics() {
    try {
      var h = location.hostname;
      if (!h || h === 'localhost' || h === '127.0.0.1' || h === '[::1]') return;
      if (h.split('.')[0] === 'admin') return;              // never track the console
      if (!/mastermind-x\.com$/.test(h)) return;            // only the origin that serves /api/collect
      if (window.__mm_a) return; window.__mm_a = true;

      var EP = '/api/collect', SITE = 'macro';

      var _fp = '';
      function fingerprint() {
        if (_fp) return _fp;
        try {
          var n = navigator, s = screen, tz = '';
          try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) {}
          var cv = '';
          try {
            var c = document.createElement('canvas'); c.width = 200; c.height = 40; var g = c.getContext('2d');
            if (g) { g.textBaseline = 'top'; g.font = "14px 'Arial'"; g.fillStyle = '#f60'; g.fillRect(10, 5, 80, 20); g.fillStyle = '#069'; g.fillText('mm-fp-✨', 12, 8); cv = c.toDataURL().slice(-48); }
          } catch (e) {}
          var wg = '';
          try {
            var gl = document.createElement('canvas').getContext('webgl');
            if (gl) { var d = gl.getExtension('WEBGL_debug_renderer_info'); wg = String(d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER) || ''); }
          } catch (e) {}
          var p = [n.userAgent || '', (n.languages && n.languages.join(',')) || n.language || '', n.platform || '',
            String(n.hardwareConcurrency || ''), String(n.deviceMemory || ''), s.width + 'x' + s.height + 'x' + s.colorDepth,
            String(window.devicePixelRatio || ''), tz, String(n.maxTouchPoints || 0), wg, cv].join('|');
          var a = 0x811c9dc5; for (var i = 0; i < p.length; i++) { a ^= p.charCodeAt(i); a = Math.imul(a, 0x01000193); }
          var b = (0x811c9dc5 ^ a) >>> 0; for (var j = p.length - 1; j >= 0; j--) { b ^= p.charCodeAt(j); b = Math.imul(b, 0x01000193); }
          _fp = (a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0');
        } catch (e) { _fp = ''; }
        return _fp;
      }

      var sid = '', fresh = false;
      try {
        var now = Date.now(), ss = window.sessionStorage;
        sid = ss.getItem('mm.sid') || ''; var lastTs = +ss.getItem('mm.sid.ts') || 0;
        if (!sid || now - lastTs > 1800000) { sid = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : 's-' + now.toString(36) + Math.random().toString(36).slice(2, 10); fresh = true; }
        ss.setItem('mm.sid', sid); ss.setItem('mm.sid.ts', String(now));
      } catch (e) {}

      var q = [], timer = null;
      function flush() {
        if (timer) { clearTimeout(timer); timer = null; }
        if (!q.length) return;
        var evs = q; q = [];
        try {
          var body = JSON.stringify({ events: evs });
          if (navigator.sendBeacon) navigator.sendBeacon(EP, new Blob([body], { type: 'application/json' }));
          else fetch(EP, { method: 'POST', body: body, keepalive: true, credentials: 'same-origin', headers: { 'content-type': 'application/json' } }).catch(function () {});
        } catch (e) {}
      }
      function track(type, extra) {
        try {
          var e = { type: type, site: SITE, sid: sid, fp: fingerprint() || undefined, path: location.pathname + location.hash, t: Date.now() };
          if (extra) { for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) e[k] = extra[k]; }
          q.push(e);
          // flush immediately for events that precede a navigation (sendBeacon survives unload)
          if (type === 'search' || type === 'terminal_jump' || type === 'exit' || q.length >= 10) flush();
          else if (!timer) timer = setTimeout(flush, 4000);
        } catch (e2) {}
      }
      window.mmTrack = track;

      var enter = Date.now(), maxScroll = 0;
      if (fresh) track('session_start');
      track('pageview', { ref: document.referrer || undefined });

      // analyzer pages (stock.html#AAPL → #MSFT) change symbol via hashchange, no page load.
      // Elsewhere the hash is an in-page anchor/dialog slug (#regime-radar, #dlg-events) —
      // never log those as ticker views. Tickers are uppercase alnum (optionally . or digits,
      // e.g. AAPL, BRK.B, 9988.HK); reject slug shapes (lowercase / hyphen).
      window.addEventListener('hashchange', function () {
        var t = (location.hash || '').replace(/^#/, '');
        try { t = decodeURIComponent(t); } catch (e) {}
        if (!t || !/^[A-Z0-9][A-Z0-9.]{0,15}$/.test(t)) return;
        track('ticker_view', { ticker: t.slice(0, 64) });
      });

      window.addEventListener('scroll', function () {
        try { var d = document.documentElement, den = (d.scrollHeight - d.clientHeight) || 1, pc = Math.round(d.scrollTop / den * 100); if (pc > maxScroll) maxScroll = Math.max(0, Math.min(100, pc)); } catch (e) {}
      }, { passive: true });

      document.addEventListener('click', function (ev) {
        try {
          var el = ev.target && ev.target.closest && ev.target.closest('a,button,[data-track]');
          if (!el) return;
          var a = el.closest('a');
          track('click', { meta: { tag: el.tagName.toLowerCase(), text: (el.textContent || '').trim().slice(0, 80) || undefined, href: (a && a.getAttribute('href')) || undefined } });
        } catch (e) {}
      }, true);

      // exit fires at most once: leave() is bound to both pagehide and visibilitychange
      // (hidden), which both fire on a normal navigation — a latch prevents double-counting
      // the exit/dwell. flush() still runs on every hide to drain any queued events.
      var _exited = false;
      function leave() {
        if (!_exited) { _exited = true; try { track('exit', { dwell_ms: Date.now() - enter, scroll: maxScroll || undefined }); } catch (e) {} }
        flush();
      }
      window.addEventListener('pagehide', leave);
      document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') leave(); });
    } catch (e) { /* analytics must never break the page */ }
  })();

  /* ---- Mastermind Terminal workspace --------------------------------------
     Single-stock analysis opens in a native-feeling full-screen Terminal layer
     while Macro Dashboard remains mounted underneath. US (stock.html),
     China (china_lookup.html), HK (hk_lookup.html), Canada (canada_stock.html),
     and International (intl_stock.html) stock links all open
     app.mastermind-x.com/terminal?sym=TICKER inside the layer — their formats (e.g.
     600519.SS, 0002.HK, AAV.TO, 8035.T) already match the Terminal manifest
     exactly so no transformation is needed. The origin is pre-warmed (DNS + TLS);
     the overlay controller loads on idle/intent, and the iframe stays warm after
     close so subsequent ticker switches avoid a full Next.js reload.
     Flip window.MM_TERMINAL = false anywhere to restore in-page analyzers. */
  var _mmLocalHost = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  var MM_TERMINAL_BASE = window.MM_TERMINAL_BASE
    || (_mmLocalHost ? 'http://127.0.0.1:3100/terminal' : 'https://app.mastermind-x.com/terminal');
  var MM_TERMINAL_ORIGIN = (function () {
    try { return new URL(MM_TERMINAL_BASE, location.href).origin; }
    catch (e) { return 'https://app.mastermind-x.com'; }
  })();
  function mmTerminalOn() { return window.MM_TERMINAL !== false; }
  // from=macro lets the Terminal show its prominent "back to Dashboard" button reliably even when the
  // referrer is stripped (the Terminal also falls back to document.referrer when this param is absent).
  // ret=<full current dashboard URL, incl. hash> lets the Terminal's "← Dashboard" button return the user
  // to the EXACT page they came from: the macro→terminal hop is cross-origin, so document.referrer is
  // stripped to the bare origin and the precise path/anchor is otherwise unrecoverable Terminal-side.
  function terminalUrl(t) {
    return MM_TERMINAL_BASE + (t ? '?sym=' + encodeURIComponent(t) + '&' : '?') + 'from=macro'
      + '&ret=' + encodeURIComponent(location.href);
  }
  function terminalEmbedUrl(t) {
    return terminalUrl(t) + '&embed=dashboard';
  }
  // Existing Terminal CTAs may carry meaningful state such as `signin=1`,
  // `signup=1`, a plan, or a Tech Lab indicator set. Preserve every one of
  // those parameters when the destination is moved into the portal.
  function terminalExistingUrl(href, embedded) {
    var u = new URL(href, location.href);
    if (u.pathname === '/') u.pathname = new URL(MM_TERMINAL_BASE, location.href).pathname;
    u.searchParams.set('from', 'macro');
    u.searchParams.set('ret', location.href);
    if (embedded) u.searchParams.set('embed', 'dashboard');
    else u.searchParams.delete('embed');
    return u.href;
  }

  // The portal controller is maintained as a separate source file, then bundled
  // onto production theme.js by lib/site_assets.py so the access wall treats it
  // like every other public UI asset. This loader remains as a resilient fallback
  // for local/custom builds that serve the sources without the production bake.
  var _mmOverlayScript = null, _mmOverlayWaiters = [];
  var _mmThemeScript = document.currentScript ||
    document.querySelector('script[src$="theme.js"],script[src*="theme.js?"]');
  var _mmSharedAssetRoot = (function () {
    try {
      return new URL('.', _mmThemeScript && _mmThemeScript.src
        ? _mmThemeScript.src : location.href).href;
    } catch (e) { return ''; }
  })();
  var _mmOverlaySrc = (function () {
    try {
      return new URL('terminal_overlay.js', _mmThemeScript && _mmThemeScript.src
        ? _mmThemeScript.src : location.href).href;
    } catch (e) { return 'terminal_overlay.js'; }
  })();
  function loadTerminalOverlay(done) {
    if (window.MDXTerminalOverlay) { if (done) done(); return; }
    if (done) _mmOverlayWaiters.push(done);
    if (_mmOverlayScript) return;
    _mmOverlayScript = document.createElement('script');
    _mmOverlayScript.src = _mmOverlaySrc;
    _mmOverlayScript.async = true;
    _mmOverlayScript.onload = function () {
      var q = _mmOverlayWaiters.slice(); _mmOverlayWaiters.length = 0;
      q.forEach(function (fn) { try { fn(); } catch (e) {} });
    };
    _mmOverlayScript.onerror = function () {
      _mmOverlayScript = null;
      var q = _mmOverlayWaiters.slice(); _mmOverlayWaiters.length = 0;
      q.forEach(function (fn) { try { fn(false); } catch (e) {} });
    };
    document.head.appendChild(_mmOverlayScript);
  }
  function openTerminal(t, trigger, requestedUrl) {
    if (!mmTerminalOn()) return false;
    var directUrl = requestedUrl ? terminalExistingUrl(requestedUrl, false) : terminalUrl(t);
    var embedUrl = requestedUrl ? terminalExistingUrl(requestedUrl, true) : terminalEmbedUrl(t);
    loadTerminalOverlay(function (loaded) {
      if (loaded === false || !window.MDXTerminalOverlay) {
        location.href = directUrl;
        return;
      }
      window.MDXTerminalOverlay.open({
        symbol: t || '',
        url: embedUrl,
        directUrl: directUrl,
        targetOrigin: MM_TERMINAL_ORIGIN,
        trigger: trigger || null
      });
    });
    return true;
  }
  function closeTerminal() {
    if (window.MDXTerminalOverlay) window.MDXTerminalOverlay.close();
  }
  // Public handle for programmatic rows (stocktable.js) and feature-specific
  // Terminal CTAs. url() remains the resilient no-JS/new-tab destination.
  window.MDXTerminal = {
    url: terminalUrl,
    embedUrl: terminalEmbedUrl,
    on: mmTerminalOn,
    open: openTerminal,
    close: closeTerminal
  };
  (function prewarmTerminal() {
    if (!mmTerminalOn() || !document.head) return;
    ['preconnect', 'dns-prefetch'].forEach(function (rel) {
      var l = document.createElement('link');
      l.rel = rel; l.href = 'https://app.mastermind-x.com';
      if (rel === 'preconnect') l.crossOrigin = '';
      document.head.appendChild(l);
    });
    var idle = window.requestIdleCallback || function (fn) { return setTimeout(fn, 1200); };
    idle(function () { if (mmTerminalOn()) loadTerminalOverlay(); }, { timeout: 2400 });
  })();
  // Re-route Terminal-covered analyzer links anywhere on the site → Terminal
  // (capture phase so it runs before the browser follows the <a>). Leaves
  // new-tab / modified clicks alone.
  // null-prototype map so an href-derived key can't hit Object.prototype ('constructor', etc.)
  var TERMINAL_PAGES = Object.assign(Object.create(null), { 'stock.html': 1, 'china_lookup.html': 1, 'hk_lookup.html': 1, 'canada_stock.html': 1, 'intl_stock.html': 1 });
  // The ticker a Terminal-covered analyzer link points at (else null). Shared by the
  // hover-prefetch and the click-reroute below so the two can never drift.
  function terminalTarget(a) {
    if (!a || a.hasAttribute('download')) return null;
    var href = a.getAttribute('href') || '', h = href.indexOf('#');
    if (h >= 0) {
      var page = href.slice(0, h).replace(/[?].*$/, '').replace(/.*\//, '');
      if (TERMINAL_PAGES[page]) {
        var t = href.slice(h + 1);
        try { return t ? { ticker: decodeURIComponent(t), url: '' } : null; }
        catch (e) { return null; }
      }
    }
    // Product-door / feature CTAs already point at the live Terminal host. A
    // normal click stays inside the dashboard layer; modified clicks retain the
    // browser's native new-tab behavior.
    try {
      var u = new URL(href, location.href);
      if (u.origin !== MM_TERMINAL_ORIGIN) return null;
      if (u.pathname !== '/' && u.pathname !== '/terminal') return null;
      return {
        ticker: u.searchParams.get('symbol') || u.searchParams.get('sym') || '',
        url: u.href
      };
    } catch (e) { return null; }
  }
  // Warm the SPECIFIC destination on hover / touch intent so the click navigation lands
  // on an already-fetched document (the origin is pre-connected above; this adds the
  // ?sym= page itself). Deduped per ticker; a failed/uncacheable prefetch is a silent no-op.
  var _mmPrefetched = Object.create(null);
  function prefetchTerminal(t, requestedUrl) {
    if ((!t && !requestedUrl) || !document.head) return;
    var href = requestedUrl ? terminalExistingUrl(requestedUrl, false) : terminalUrl(t);
    if (_mmPrefetched[href]) return;
    _mmPrefetched[href] = 1;
    var l = document.createElement('link');
    l.rel = 'prefetch'; l.as = 'document'; l.href = href;
    document.head.appendChild(l);
  }
  ['pointerover', 'touchstart'].forEach(function (evt) {
    document.addEventListener(evt, function (e) {
      if (!mmTerminalOn()) return;
      var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
      var target = terminalTarget(a);
      if (target) {
        loadTerminalOverlay();
        prefetchTerminal(target.ticker, target.url);
      }
    }, { capture: true, passive: true });
  });
  document.addEventListener('click', function (e) {
    if (!mmTerminalOn() || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    var target = terminalTarget(a);
    if (!target) return;
    e.preventDefault(); e.stopPropagation();
    openTerminal(target.ticker, a, target.url);
  }, true);

  /* ---- nb-spot data-href handler -------------------------------------------
     The .nb-spot[data-href] spotlight chip carries a basket URL in data-href.
     Post div-restructure the outer anchor no longer wraps the chip, so we need
     an explicit delegated handler. stopPropagation prevents the card-body handler
     (dashboard.html.j2) from double-navigating. Mirrors the nb-cau pattern. */
  document.addEventListener('click', function (e) {
    var chip = e.target && e.target.closest ? e.target.closest('.nb-spot[data-href]') : null;
    if (!chip) return;
    e.preventDefault(); e.stopPropagation();
    var href = chip.getAttribute('data-href');
    if (href) { location.href = href; }
  }, true);

  /* ---- account / profile panel loader -------------------------------------
     Load the shared account component (account.js) on EVERY page and point it at
     the app API. It self-mounts a HIDDEN management panel (no avatar) and exposes
     window.MMAccount.open(), which the settings-gear signed-in row calls. Identity
     rides the shared .mastermind-x.com cookie (credentials:include) — so it never
     loads a Supabase SDK here (jsdelivr is GFW-blocked). Path-depth aware; idempotent. */
  (function loadAccount() {
    if (window.__mmAccountLoading) return;
    window.__mmAccountLoading = true;
    window.MM_API = window.MM_API || 'https://app.mastermind-x.com';
    /* Derive the shared-asset root from this script's own URL.  The previous
       pathname special-case only knew about /sectors/, so every other nested
       estate (/basket_canada/, /basket/, /rotation/, …) requested account.js
       from its page folder.  That 404 also prevented account.js from loading
       nav_market.js, leaving those pages on the legacy dropdown.  The rendered
       theme.js reference already carries the correct ../ depth, so reuse it as
       the single source of truth for every current and future nested page. */
    var pfx = _mmSharedAssetRoot;
    var s = document.createElement('script');
    // Keep the dynamic dependency cache-safe too. theme.js itself is
    // content-hashed in every page; this explicit release key prevents a
    // year-cached account.js from pinning an older navigation loader.
    s.src = pfx + 'account.js?v=20260730-exact8'; s.async = true;
    document.head.appendChild(s);
  })();

  /* ---- Plotly charts: re-theme to the active theme -------------------------
     Charts are built transparent with neutral-grey axes (build_site.py); here we
     relayout their font + gridlines crisply for light vs dark — on load and on
     every toggle. Trace colours stay as built. Only the primary x/y axis is
     addressed (covers the single-axis charts); secondary axes keep the neutral
     build-time grey. No-ops safely if Plotly or a chart isn't ready. */
  function themeCharts() {
    if (!window.Plotly) return;
    var light = (docEl.getAttribute('data-theme') || 'dark') === 'light';
    var font = light ? '#475569' : '#aeb6c4';
    var grid = light ? 'rgba(60,80,120,0.14)' : 'rgba(170,180,205,0.12)';
    var zero = light ? 'rgba(60,80,120,0.30)' : 'rgba(170,180,205,0.22)';
    document.querySelectorAll('.js-plotly-plot').forEach(function (p) {
      try {
        window.Plotly.relayout(p, {
          'font.color': font,
          'xaxis.gridcolor': grid, 'yaxis.gridcolor': grid,
          'xaxis.zerolinecolor': zero, 'yaxis.zerolinecolor': zero,
          'xaxis.linecolor': grid, 'yaxis.linecolor': grid
        });
      } catch (e) {}
    });
  }

  /* ---- theme (dark default) ------------------------------------------------ */
  function curTheme() { return docEl.getAttribute('data-theme') || 'dark'; }
  // Hour-derived theme for Auto mode: 7-19 local = light, else dark
  function _hourTheme() { var h = new Date().getHours(); return (h >= 7 && h < 19) ? 'light' : 'dark'; }
  function setTheme(tm) {
    docEl.setAttribute('data-theme', tm);
    // an explicit choice ends time-of-day auto mode (see each page's no-flash init)
    try { localStorage.setItem('theme', tm); localStorage.removeItem('themeAuto'); } catch (e) {}
    document.querySelectorAll('.theme-btn').forEach(function (b) {
      b.innerHTML = tm === 'light'
        ? '<span class="l-en">🌙 Dark</span><span class="l-zh">🌙 深色</span>'
        : '<span class="l-en">☀️ Light</span><span class="l-zh">☀️ 浅色</span>';
    });
    if (window.hydrateMTF) window.hydrateMTF();
    themeCharts();
    document.dispatchEvent(new CustomEvent('themechange', { detail: tm }));
    skyToggleFx(tm);
    _syncThemeSegment();
  }
  /* Sitewide theme-toggle flourish: a luminous sun (→ light) or a crescent moon
     (→ dark) blooms in the centre of the screen, then fades. The landing page runs
     its own richer sun/moon choreography, so it sets window.__skyDeck — bow out there. */
  function skyToggleFx(tm) {
    if (window.__skyDeck) return;
    try {
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      var prev = document.querySelector('.sky-fx');   // a rapid re-toggle replaces the in-flight one
      if (prev && prev.parentNode) prev.parentNode.removeChild(prev);
      var o = document.createElement('div');
      o.className = 'sky-fx ' + (tm === 'light' ? 'sun' : 'moon');
      o.setAttribute('aria-hidden', 'true');
      o.innerHTML = '<div class="orb"><span class="disc"></span><span class="ring"></span></div>';
      document.body.appendChild(o);
      setTimeout(function () { if (o.parentNode) o.parentNode.removeChild(o); }, 1100);
    } catch (e) {}
  }
  // Apply Auto mode: persist themeAuto + apply the hour-derived theme via same code
  // path as setTheme BUT WITHOUT removing themeAuto (so it survives page reloads).
  function setThemeAuto() {
    var tm = _hourTheme();
    docEl.setAttribute('data-theme', tm);
    try { localStorage.setItem('themeAuto', '1'); localStorage.setItem('theme', tm); } catch (e) {}
    document.querySelectorAll('.theme-btn').forEach(function (b) {
      b.innerHTML = tm === 'light'
        ? '<span class="l-en">🌙 Dark</span><span class="l-zh">🌙 深色</span>'
        : '<span class="l-en">☀️ Light</span><span class="l-zh">☀️ 浅色</span>';
    });
    if (window.hydrateMTF) window.hydrateMTF();
    themeCharts();
    document.dispatchEvent(new CustomEvent('themechange', { detail: tm }));
    skyToggleFx(tm);
    _syncThemeSegment();
  }
  // Placeholder — real implementation wired after initSettings builds the segment
  function _syncThemeSegment() {}
  // SITE-WIDE LIFT: at boot, if themeAuto==='1' re-derive the hour theme and apply
  // it (one-time flip so other pages' pre-paint head scripts pick it up immediately).
  (function () {
    try {
      if (localStorage.getItem('themeAuto') === '1') {
        var hourTm = _hourTheme();
        if (docEl.getAttribute('data-theme') !== hourTm) {
          docEl.setAttribute('data-theme', hourTm);
          localStorage.setItem('theme', hourTm);
        }
      }
    } catch (e) {}
  })();
  window.toggleTheme = function () { setTheme(curTheme() === 'light' ? 'dark' : 'light'); };
  window.setThemeAuto = setThemeAuto;

  /* ---- soft-contrast palette (default for everyone) ------------------------
     Injects a <style id="soft-contrast-css"> that adds html.soft-contrast
     overrides: warmer/softer bg + panels in light mode, lifted blacks in dark.
     Measured on the softened light backgrounds: body --text 9.6-10.6:1 (AAA);
     --muted 5.8-6.5:1 (comfortably above the 4.5:1 AA floor).
     Applied unconditionally at boot (no user toggle). theme.js loads end-of-
     body, so pages get one standard-palette paint first on cold load; the hub's
     <head> boot script also sets the class pre-paint (delta is subtle). */
  var SOFT_CONTRAST_CSS =
    'html.soft-contrast[data-theme="light"]{' +
      '--bg:#eceef1;--panel:#f5f5f7;--panel2:#e8eaed;--text:#2e3950;--muted:#4c5a6c;--line:#d0d4db;' +
      '--glass-bg:color-mix(in srgb,#f5f5f7 64%,transparent);' +
      '--glass-brd:color-mix(in srgb,#2e3950 9%,transparent);' +
      '--card-shadow:0 1px 3px rgba(20,30,50,.05)' +
    '}' +
    'html.soft-contrast[data-theme="dark"]{' +
      '--bg:#0d1018;--panel:#151820;--panel2:#1b1f28;--text:#c8d0dc;--line:#262c38' +
    '}';

  function _applySoftContrastCSS() {
    if (document.getElementById('soft-contrast-css')) return;
    var st = document.createElement('style');
    st.id = 'soft-contrast-css'; st.textContent = SOFT_CONTRAST_CSS;
    (document.head || document.documentElement).appendChild(st);
  }

  // Boot: apply soft contrast for everyone, ASAP (theme.js loads at end of
  // <body> but before DOMContentLoaded).
  (function () {
    _applySoftContrastCSS();
    docEl.classList.add('soft-contrast');
  })();

  /* ---- language (en default) ----------------------------------------------- */
  function curLang() { return docEl.getAttribute('data-lang') || 'en'; }
  function setLang(lg) {
    docEl.setAttribute('data-lang', lg);
    // WCAG 3.1.1: keep document.documentElement.lang in sync with the active language
    docEl.lang = lg === 'zh' ? 'zh-CN' : 'en';
    try { localStorage.setItem('lang', lg); } catch (e) {}
    document.querySelectorAll('.lang-btn').forEach(function (b) {
      // label advertises the OTHER language (what a click switches you to)
      b.textContent = lg === 'zh' ? 'EN' : '中文';
    });
    // the up/down + quadrant CSS vars change with language, so recolour the
    // JS-drawn widgets (gauges/sparklines) and the Plotly charts
    if (window.hydrateMTF) window.hydrateMTF();
    document.dispatchEvent(new CustomEvent('langchange', { detail: lg }));
  }
  // Apply documentElement.lang once at boot from the current data-lang attribute
  (function () {
    var bootLang = docEl.getAttribute('data-lang') || 'en';
    docEl.lang = bootLang === 'zh' ? 'zh-CN' : 'en';
  })();
  window.toggleLang = function () { setLang(curLang() === 'zh' ? 'en' : 'zh'); };
  window.setLang = setLang;
  window.setTheme = setTheme;

  /* ---- one unified global stock search -------------------------------------
     One central search box, every market in it. We merge each market's nightly
     library into a single searchable universe and route each pick to the analyzer
     that owns it — US→stock.html, China→china_lookup.html, HK→hk_lookup.html,
     Canada→canada_stock.html, Intl→intl_stock.html (each analyzer routes off the
     #TICKER hash). Per-entry routing means a page no longer scopes the box to its
     own market: the legacy data-lib / data-target attributes are ignored (a page
     that set data-lib is just relabelled, since it now searches the whole world).
     Path-depth aware so it works from /sectors/ too. No-ops without a .nav-search. */
  var STOCK_MARKETS = [
    { key: 'us',   lib: 'stockdata/index.json',       target: 'stock.html',        flag: '🇺🇸', mkt: 'US',     mktZh: '美国',   examples: ['NVDA', 'AAPL', 'MSFT'] },
    { key: 'cn',   lib: 'chinastockdata/index.json',  target: 'china_lookup.html', flag: '🇨🇳', mkt: 'China',  mktZh: '中国A股', examples: ['600519.SS', '000858.SZ'] },
    { key: 'hk',   lib: 'hkstockdata/index.json',     target: 'hk_lookup.html',    flag: '🇭🇰', mkt: 'HK',     mktZh: '香港',   examples: ['0700.HK', '9988.HK'] },
    { key: 'ca',   lib: 'canadastockdata/index.json', target: 'canada_stock.html', flag: '🇨🇦', mkt: 'Canada', mktZh: '加拿大', examples: ['SHOP.TO', 'SU.TO'] },
    { key: 'intl', lib: 'intlstockdata/index.json',   target: 'intl_stock.html',   flag: '🌐', mkt: 'Intl',   mktZh: '国际',   examples: ['7203.T', 'ASML.AS'] }
  ];

  function initNavDrills() {
    document.addEventListener('click', function (e) {
      var open = e.target && e.target.closest ? e.target.closest('[data-nav-drill-open]') : null;
      var back = e.target && e.target.closest ? e.target.closest('[data-nav-drill-back]') : null;
      if (!open && !back) return;
      var drill = (open || back).closest('[data-nav-drill], .nav-drill');
      if (!drill) return;
      e.preventDefault();
      e.stopPropagation();
      var panel = drill.querySelector(':scope > [data-nav-drill-panel], :scope > .nav-drill-panel');
      var isOpen = !!open;
      drill.classList.toggle('is-open', isOpen);
      var returnTrigger = drill.querySelector(':scope > [data-nav-drill-open]');
      if (open) open.setAttribute('aria-expanded', 'true');
      else {
        if (returnTrigger) returnTrigger.setAttribute('aria-expanded', 'false');
      }
      if (panel) panel.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
      if (isOpen && panel) {
        var first = panel.querySelector('[data-nav-drill-back], a, button');
        if (first) window.setTimeout(function () { first.focus(); }, 80);
      } else if (returnTrigger) {
        window.setTimeout(function () { returnTrigger.focus(); }, 40);
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var openPanel = document.querySelector('.nav-drill.is-open');
      if (!openPanel) return;
      var trigger = openPanel.querySelector(':scope > [data-nav-drill-open]');
      openPanel.classList.remove('is-open');
      if (trigger) { trigger.setAttribute('aria-expanded', 'false'); trigger.focus(); }
      var panel = openPanel.querySelector(':scope > [data-nav-drill-panel]');
      if (panel) panel.setAttribute('aria-hidden', 'true');
    });
  }

  /* A theme.js update reaches the VPS before the slow full-site renderer can
     rebake every HTML page. During that window an older page has .nav-search
     but no navigation-refresh.css / stock-logo scripts. Never upgrade that
     legacy search into the new SVG-rich DOM until its stylesheet is ready:
     otherwise the browser paints the raw <svg> at its 300×150 default (the
     giant black-circle regression). The fallback keeps the legacy search
     hidden only while the same-origin CSS is loading, then restores it intact
     if the asset cannot be loaded. */
  function navRefreshAssetUrl(name) {
    try {
      return new URL(name, _mmThemeScript && _mmThemeScript.src
        ? _mmThemeScript.src : location.href).href;
    } catch (e) { return name; }
  }

  function ensureNavSearchCss(box) {
    // Prefer the applied stylesheet over an earlier preload for the same URL.
    // Querying the preload first meant its (correctly absent) CSSStyleSheet
    // object could keep the enhanced search dormant.
    var link = document.querySelector('link[rel="stylesheet"][href*="navigation-refresh.css"]')
      || document.querySelector('link[href*="navigation-refresh.css"]');
    // A stylesheet emitted directly by the renderer is authoritative. Some
    // privacy-hardened browsers intentionally withhold link.sheet even after
    // the CSS has applied; treating that as "not loaded" left the new search
    // dormant on otherwise current pages. DOMContentLoaded follows deferred
    // theme.js and the page stylesheet, so an authored stylesheet link is safe
    // to trust. Only runtime-injected links need the load/error handshake below.
    if (link && link.rel === 'stylesheet' && !link.hasAttribute('data-nav-refresh-runtime')) return true;
    try { if (link && link.sheet) return true; } catch (e) {}
    if (box.getAttribute('data-nav-css-wait') === '1') return false;

    if (!link) {
      link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = navRefreshAssetUrl('navigation-refresh.css');
      link.setAttribute('data-nav-refresh-runtime', '1');
    }

    var settled = false;
    var priorVisibility = box.style.visibility;
    box.setAttribute('data-nav-css-wait', '1');
    box.style.visibility = 'hidden';

    function finish(loaded) {
      if (settled) return;
      settled = true;
      box.removeAttribute('data-nav-css-wait');
      box.style.visibility = priorVisibility;
      if (loaded) initNavSearch();
    }

    link.addEventListener('load', function () { finish(true); }, { once: true });
    link.addEventListener('error', function () { finish(false); }, { once: true });
    if (!link.parentNode) (document.head || docEl).appendChild(link);
    window.setTimeout(function () {
      var loaded = false;
      try { loaded = !!link.sheet; } catch (e) {}
      finish(loaded);
    }, 4000);
    return false;
  }

  function ensureNavScript(name, ready) {
    var script = document.querySelector('script[src*="' + name + '"]');
    if (script) {
      if (ready) script.addEventListener('load', ready, { once: true });
      return;
    }
    script = document.createElement('script');
    script.src = navRefreshAssetUrl(name);
    script.async = true;
    if (ready) script.addEventListener('load', ready, { once: true });
    (document.head || docEl).appendChild(script);
  }

  function ensureNavLogoAssets(box) {
    function enhance() {
      if (window.MMXStockLogo && window.MMXStockLogo.enhance) {
        window.MMXStockLogo.enhance(box);
      }
    }
    function loadLogoSystem() {
      if (window.MMXStockLogo) { enhance(); return; }
      ensureNavScript('stock-logos.js', enhance);
    }
    if (window.MMX_LOGO_DEV_TOKEN || document.querySelector('script[src*="logo_config.js"]')) {
      loadLogoSystem();
    } else {
      ensureNavScript('logo_config.js', loadLogoSystem);
    }
  }

  function initNavSearch() {
    var box = document.querySelector('.nav-search');
    if (!box) return;
    if (box.getAttribute('data-ticker-search-ready') === '1') return;
    if (!ensureNavSearchCss(box)) return;
    box.setAttribute('data-ticker-search-ready', '1');
    var pfx = _mmSharedAssetRoot;
    var initialCopy = curLang() === 'zh'
      ? { trigger: '搜索股票', input: '搜索股票代码或公司', close: '关闭股票搜索', closeShort: '关闭', results: '股票搜索结果' }
      : { trigger: 'Search tickers', input: 'Search stocks', close: 'Close ticker search', closeShort: 'Esc', results: 'Ticker search results' };
    var icon = '<svg class="search-glyph" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.7" cy="8.7" r="5.6"></circle><path d="m12.9 12.9 4 4"></path></svg>';
    box.className = 'nav-search ticker-search';
    box.innerHTML =
      '<button class="search-trigger" type="button" aria-label="' + initialCopy.trigger + '" aria-expanded="false" aria-controls="ticker-search-dropdown">' +
        icon + '<span class="idle-ticker" aria-hidden="true"></span>' +
      '</button>' +
      '<div class="search-expanded">' + icon +
        '<input class="ticker-input" type="text" inputmode="search" maxlength="80" autocomplete="off" spellcheck="false" aria-label="' + initialCopy.input + '" aria-autocomplete="list" aria-controls="ticker-search-dropdown">' +
        '<button class="search-esc" type="button" aria-label="' + initialCopy.close + '">' + initialCopy.closeShort + '</button>' +
      '</div>' +
      '<div class="ticker-dropdown" id="ticker-search-dropdown" role="listbox" aria-label="' + initialCopy.results + '"></div>';
    ensureNavLogoAssets(box);

    var trigger = box.querySelector('.search-trigger');
    var input = box.querySelector('.ticker-input');
    var closeButton = box.querySelector('.search-esc');
    var dropdown = box.querySelector('.ticker-dropdown');
    var idleTicker = box.querySelector('.idle-ticker');
    var lib = [], libsStarted = false, pending = 0, page = 0, selected = -1;
    var pageRows = [], idleTimer = 0, idleIndex = 0, idleChars = 0, deleting = false;
    var isComposing = false;

    function esc(value) {
      return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }

    function searchCopy() {
      if (curLang() === 'zh') {
        return {
          placeholder: '股票代码或公司名称',
          trigger: '搜索股票',
          input: '搜索股票代码或公司',
          close: '关闭股票搜索',
          closeShort: '关闭',
          results: '股票搜索结果',
          allMarkets: '全部市场',
          loadingTitle: '正在加载全球股票库',
          loadingSub: '正在准备热门股票和公司匹配…',
          loadingEmpty: '最新股票库正在加载。',
          popularTitle: '热门股票',
          popularSub: '上一交易时段成交量最高的股票',
          rankingTitle: '正在按成交量排序',
          rankingSub: '正在读取您所选市场的上一交易时段…',
          rankingEmpty: '正在准备成交量最高的股票。',
          selectTicker: '选择股票并在终端中打开',
          stillLoading: '仍在加载匹配市场…',
          noMatches: '没有匹配的股票代码或公司。',
          company: '公司',
          inLibrary: '已收录',
          logoAttribution: 'Logo 由 Logo.dev 提供'
        };
      }
      return {
        placeholder: 'Ticker or company',
        trigger: 'Search tickers',
        input: 'Search stocks',
        close: 'Close ticker search',
        closeShort: 'Esc',
        results: 'Ticker search results',
        allMarkets: 'All markets',
        loadingTitle: 'Loading your market universe',
        loadingSub: 'Preparing popular tickers and company matches…',
        loadingEmpty: 'The latest ticker libraries are loading.',
        popularTitle: 'Popular tickers',
        popularSub: 'Highest-volume names from the latest session',
        rankingTitle: 'Ranking today’s active names',
        rankingSub: 'Reading the latest completed session across your markets…',
        rankingEmpty: 'Preparing your highest-volume tickers.',
        selectTicker: 'Select a ticker to open Terminal',
        stillLoading: 'Still loading matching markets…',
        noMatches: 'No ticker or company matches this search.',
        company: 'Company',
        inLibrary: 'IN LIBRARY',
        logoAttribution: 'Logos by Logo.dev'
      };
    }

    function normalizeSearch(value) {
      var text = String(value == null ? '' : value);
      try { text = text.normalize('NFKC'); } catch (e) {}
      return text.trim().replace(/\s+/g, ' ').toUpperCase();
    }

    function nameEnglish(x) {
      var explicit = String(x.en || x.name_en || '').trim();
      var raw = explicit || String(x.n || '').trim();
      var split = raw.indexOf(' / ');
      return split > -1 ? (raw.slice(0, split).trim() || raw) : raw;
    }

    function nameChinese(x) {
      var explicit = String(x.z || x.zh || x.cn || x.name_zh || '').trim();
      if (explicit) return explicit;
      var raw = String(x.n || '').trim();
      var split = raw.lastIndexOf(' / ');
      var candidate = split > -1 ? raw.slice(split + 3).trim() : '';
      return /[\u3400-\u9fff]/.test(candidate) ? candidate : '';
    }

    function displayName(x) {
      var c = searchCopy(), en = nameEnglish(x), zh = nameChinese(x);
      return curLang() === 'zh' ? (zh || en || c.company) : (en || zh || c.company);
    }

    function marketPreference() {
      var p = window.MMXMarkets && window.MMXMarkets.current ? window.MMXMarkets.current() : null;
      var allowed = { us: 1, cn: 1, hk: 1, ca: 1, intl: 1 };
      var enabled = p && p.enabled && p.enabled.length
        ? p.enabled.filter(function (key) { return !!allowed[key]; })
        : [];
      if (!enabled.length) enabled = ['us', 'cn', 'hk', 'ca', 'intl'];
      return { home: p && p.home ? p.home : enabled[0], enabled: enabled };
    }

    function marketMeta(key) {
      for (var i = 0; i < STOCK_MARKETS.length; i++) if (STOCK_MARKETS[i].key === key) return STOCK_MARKETS[i];
      return STOCK_MARKETS[0];
    }

    function examplesForProfile() {
      var out = [], pref = marketPreference();
      for (var i = 0; i < pref.enabled.length; i++) {
        var m = marketMeta(pref.enabled[i]);
        if (m.examples && m.examples[0]) out.push(m.examples[0]);
      }
      return out.length ? out : ['NVDA'];
    }

    function profileLabel() {
      var zh = curLang() === 'zh';
      var names = marketPreference().enabled.map(function (key) {
        var meta = marketMeta(key);
        return zh ? (meta.mktZh || meta.mkt) : meta.mkt;
      });
      return names.join(' · ') || searchCopy().allMarkets;
    }

    function applySearchLocale() {
      var c = searchCopy();
      input.placeholder = c.placeholder;
      input.setAttribute('aria-label', c.input);
      trigger.setAttribute('aria-label', c.trigger);
      closeButton.setAttribute('aria-label', c.close);
      closeButton.textContent = c.closeShort;
      dropdown.setAttribute('aria-label', c.results);
      if (box.classList.contains('open')) render();
    }
    applySearchLocale();
    document.addEventListener('langchange', applySearchLocale);

    function loadLibs() {
      if (libsStarted) return;
      libsStarted = true;
      pending = STOCK_MARKETS.length;
      STOCK_MARKETS.forEach(function (m) {
        fetch(pfx + m.lib).then(function (r) { return r.ok ? r.json() : []; }).then(function (data) {
          (data || []).forEach(function (x, index) {
            x._tgt = m.target;
            x._fl = x.fl || m.flag;
            x._mk = x.mk || m.mkt;
            x._key = m.key;
            x._order = index;
          });
          lib = lib.concat(data || []);
        }).catch(function () {}).then(function () {
          pending -= 1;
          /* Popular rows are one composed snapshot. Repainting after each of
             five libraries arrives made cards repeatedly disappear, reorder
             and replay their entrance. Wait for the complete market set; a
             typed query can still progressively return early matches. */
          if (box.classList.contains('open') && (pending === 0 || input.value.trim())) render();
        });
      });
    }

    function go(x) {
      if (!x) return;
      try {
        if (window.mmTrack) window.mmTrack('search', {
          ticker: x.t,
          meta: { market: x._mk, source: 'animated_nav_search', to_terminal: !!(mmTerminalOn() && TERMINAL_PAGES[x._tgt]) }
        });
      } catch (e) {}
      if (mmTerminalOn() && TERMINAL_PAGES[x._tgt]) { openTerminal(x.t, box); return; }
      location.href = pfx + (x._tgt || 'stock.html') + '#' + encodeURIComponent(x.t);
    }

    function rank(x, value) {
      var ticker = normalizeSearch(x.t), en = normalizeSearch(nameEnglish(x));
      var zh = normalizeSearch(nameChinese(x)), raw = normalizeSearch(x.n);
      if (ticker === value) return 0;
      if (ticker.indexOf(value) === 0) return 1;
      if (en.indexOf(value) === 0 || zh.indexOf(value) === 0 || raw.indexOf(value) === 0) return 2;
      if (ticker.indexOf(value) > -1) return 3;
      if (en.indexOf(value) > -1 || zh.indexOf(value) > -1 || raw.indexOf(value) > -1) return 4;
      return 9;
    }

    function popularRows() {
      var pref = marketPreference(), groups = {}, result = [];
      pref.enabled.forEach(function (key) { groups[key] = []; });
      lib.forEach(function (x) {
        if (groups[x._key]) groups[x._key].push(x);
      });
      Object.keys(groups).forEach(function (key) {
        groups[key].sort(function (a, b) {
          var av = Number(a.v || a.vol || 0), bv = Number(b.v || b.vol || 0);
          return (bv - av) || (a._order - b._order);
        });
      });
      for (var depth = 0; result.length < 10 && depth < 20; depth++) {
        pref.enabled.forEach(function (key) {
          if (groups[key] && groups[key][depth] && result.length < 10) result.push(groups[key][depth]);
        });
      }
      if (!result.length) result = lib.slice(0, 10);
      return result;
    }

    function statusClass(status) {
      var s = String(status || '').toUpperCase();
      if (s === 'TURN SIGNALED') return 'status-turn';
      if (s === 'TOP WATCH') return 'status-watch';
      if (s === 'COUNTERTREND BOUNCE') return 'status-bounce';
      return 'status-neutral';
    }

    function logoMarkup(x) {
      return '<span data-stock-logo data-ticker="' + esc(x.t) + '" data-company="' + esc(nameEnglish(x)) +
        '" data-market="' + esc(x._mk || '') + '" data-flag="' + esc(x._fl || '') + '" data-logo-size="38"></span>';
    }

    function statusLabel(status) {
      var value = String(status || '').trim().toUpperCase();
      if (curLang() !== 'zh') return value || searchCopy().inLibrary;
      var labels = {
        'DECLINE': '下跌阶段',
        'BOTTOM WATCH': '底部观察',
        'TURN SIGNALED': '转折信号',
        'FRESH BUY': '新买点',
        'RALLY ON': '上涨延续',
        'TOP WATCH': '顶部观察',
        'ROLLING OVER': '开始转弱',
        'COUNTERTREND BOUNCE': '逆势反弹',
        'CONFIRMING TURN': '确认转折',
        'LIMITED': '数据积累中'
      };
      return labels[value] || value || searchCopy().inLibrary;
    }

    function marketLabel(x) {
      var meta = marketMeta(x._key);
      return curLang() === 'zh' ? (meta.mktZh || x._mk || '') : (meta.mkt || x._mk || '');
    }

    function resultMarkup(x, index, popular) {
      var c = searchCopy(), status = String(x.st || '').trim();
      var klass = popular ? 'fan-card' : 'result-row';
      var openLabel = curLang() === 'zh'
        ? '在终端中打开 ' + String(x.t || '')
        : 'Open ' + String(x.t || '') + ' in Terminal';
      return '<button class="' + klass + '" type="button" role="option" data-result-index="' + index +
        '" style="--i:' + index + '" aria-label="' + esc(openLabel) + '">' +
          logoMarkup(x) +
          '<span><span class="ticker-symbol">' + esc(x.t) + '</span><span class="ticker-name">' +
            esc(displayName(x)) + (popular ? '' : ' · ' + esc(marketLabel(x))) + '</span></span>' +
          (popular
            ? '<span class="market-code">' + esc(marketLabel(x)) + '</span>'
            : '<span class="signal-status ' + statusClass(status) + '">' + esc(statusLabel(status)) + '</span>') +
        '</button>';
    }

    function attribution() {
      return window.MMX_LOGO_DEV_TOKEN
        ? '<div class="logo-dev-attribution"><a href="https://logo.dev" target="_blank" rel="noopener">' +
          esc(searchCopy().logoAttribution) + '</a></div>'
        : '';
    }

    function enhanceLogos() {
      if (window.MMXStockLogo && window.MMXStockLogo.enhance) window.MMXStockLogo.enhance(dropdown);
    }

    function render() {
      var c = searchCopy();
      var queryDisplay = input.value.trim().replace(/\s+/g, ' ');
      var query = normalizeSearch(queryDisplay);
      selected = -1;
      if (!query) {
        if (pending > 0) {
          dropdown.innerHTML =
            '<div class="search-drop-head"><div><div class="search-drop-title">' + esc(c.rankingTitle) + '</div>' +
            '<div class="search-drop-sub">' + esc(c.rankingSub) + '</div></div>' +
            '<span class="market-profile">' + esc(profileLabel()) + '</span></div>' +
            '<div class="empty-search">' + esc(c.rankingEmpty) + '</div>';
          return;
        }
        pageRows = popularRows();
        if (!pageRows.length) {
          dropdown.innerHTML =
            '<div class="search-drop-head"><div><div class="search-drop-title">' + esc(c.loadingTitle) + '</div>' +
            '<div class="search-drop-sub">' + esc(c.loadingSub) + '</div></div>' +
            '<span class="market-profile">' + esc(profileLabel()) + '</span></div>' +
            '<div class="empty-search">' + esc(c.loadingEmpty) + '</div>';
          return;
        }
        dropdown.innerHTML =
          '<div class="search-drop-head"><div><div class="search-drop-title">' + esc(c.popularTitle) + '</div>' +
          '<div class="search-drop-sub">' + esc(c.popularSub) + '</div></div>' +
          '<span class="market-profile">' + esc(profileLabel()) + '</span></div>' +
          '<div class="fan-grid">' + pageRows.map(function (x, i) { return resultMarkup(x, i, true); }).join('') + '</div>' +
          attribution();
        enhanceLogos();
        return;
      }
      var matches = lib.map(function (x) { return { x: x, r: rank(x, query) }; })
        .filter(function (o) { return o.r < 9; })
        .sort(function (a, b) {
          return (a.r - b.r) || (Number(b.x.v || b.x.vol || 0) - Number(a.x.v || a.x.vol || 0)) ||
            String(a.x.t || '').localeCompare(String(b.x.t || ''));
        }).map(function (o) { return o.x; });
      var pageSize = 8, pageCount = Math.max(1, Math.ceil(matches.length / pageSize));
      page = Math.min(page, pageCount - 1);
      pageRows = matches.slice(page * pageSize, (page + 1) * pageSize);
      var pagination = '';
      if (pageCount > 1) {
        var start = Math.max(0, Math.min(page - 2, pageCount - 5));
        var end = Math.min(pageCount, start + 5);
        var buttons = [];
        for (var i = start; i < end; i++) {
          buttons.push('<button type="button" data-search-page="' + i + '" class="' + (i === page ? 'active' : '') +
            '" aria-label="' + (curLang() === 'zh' ? '结果第 ' + (i + 1) + ' 页' : 'Results page ' + (i + 1)) +
            '">' + (i + 1) + '</button>');
        }
        pagination = '<div class="search-pagination">' + buttons.join('') + '</div>';
      }
      var resultTitle = curLang() === 'zh'
        ? '“' + esc(queryDisplay) + '” 的匹配结果（' + matches.length + '）'
        : matches.length + ' match' + (matches.length === 1 ? '' : 'es') + ' for “' + esc(queryDisplay) + '”';
      dropdown.innerHTML =
        '<div class="search-drop-head"><div><div class="search-drop-title">' + resultTitle + '</div>' +
        '<div class="search-drop-sub">' + esc(c.selectTicker) + '</div></div>' +
        '<span class="market-profile">' + esc(c.allMarkets) + '</span></div>' +
        (pageRows.length
          ? '<div class="results-list">' + pageRows.map(function (x, i) { return resultMarkup(x, i, false); }).join('') + '</div>' + pagination
          : '<div class="empty-search">' + esc(pending > 0 ? c.stillLoading : c.noMatches) + '</div>') +
        attribution();
      enhanceLogos();
    }

    function paintSelection() {
      dropdown.querySelectorAll('[data-result-index]').forEach(function (row, index) {
        row.classList.toggle('sel', index === selected);
        row.setAttribute('aria-selected', index === selected ? 'true' : 'false');
      });
    }

    function openSearch() {
      box.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      loadLibs();
      page = 0;
      render();
      window.requestAnimationFrame(function () { input.focus(); });
    }

    function closeSearch() {
      box.classList.remove('open');
      trigger.setAttribute('aria-expanded', 'false');
      input.blur();
      selected = -1;
    }

    function idleTick() {
      var examples = examplesForProfile();
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        idleTicker.textContent = examples[0] || 'Ticker';
        return;
      }
      if (box.classList.contains('open')) {
        idleTimer = window.setTimeout(idleTick, 420);
        return;
      }
      var target = examples[idleIndex % examples.length] || 'Ticker';
      if (!deleting) {
        idleChars += 1;
        idleTicker.textContent = target.slice(0, idleChars);
        if (idleChars >= target.length) {
          deleting = true;
          idleTimer = window.setTimeout(idleTick, 1150);
          return;
        }
        idleTimer = window.setTimeout(idleTick, 110);
      } else {
        idleChars -= 1;
        idleTicker.textContent = target.slice(0, Math.max(0, idleChars));
        if (idleChars <= 0) {
          deleting = false;
          idleIndex = (idleIndex + 1) % examples.length;
          idleTimer = window.setTimeout(idleTick, 250);
          return;
        }
        idleTimer = window.setTimeout(idleTick, 52);
      }
    }

    trigger.addEventListener('click', openSearch);
    closeButton.addEventListener('click', closeSearch);
    input.addEventListener('compositionstart', function () { isComposing = true; });
    input.addEventListener('compositionend', function () {
      isComposing = false;
      page = 0;
      render();
    });
    input.addEventListener('input', function (e) {
      if (isComposing || e.isComposing) return;
      page = 0;
      render();
    });
    input.addEventListener('keydown', function (e) {
      if (isComposing || e.isComposing || e.key === 'Process' || e.keyCode === 229) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selected = Math.min(selected + 1, pageRows.length - 1);
        paintSelection();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selected = Math.max(selected - 1, 0);
        paintSelection();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        go(pageRows[selected >= 0 ? selected : 0]);
      } else if (e.key === 'Escape') {
        closeSearch();
      }
    });
    dropdown.addEventListener('mousedown', function (e) {
      var pageButton = e.target.closest('[data-search-page]');
      if (pageButton) {
        e.preventDefault();
        page = Number(pageButton.getAttribute('data-search-page')) || 0;
        render();
        return;
      }
      var row = e.target.closest('[data-result-index]');
      if (!row) return;
      e.preventDefault();
      go(pageRows[Number(row.getAttribute('data-result-index'))]);
    });
    document.addEventListener('click', function (e) {
      if (box.classList.contains('open') && !box.contains(e.target)) closeSearch();
    });
    document.addEventListener('mmx-markets-change', function () {
      idleIndex = idleChars = 0;
      deleting = false;
      if (box.classList.contains('open')) render();
    });
    idleTick();
  }

  /* ---- responsive mobile nav ----------------------------------------------
     The section nav (the .site-nav grid on the macro family; the .topbar flex
     on the vector / commodities / forex / bonds family) packs ~17 links plus
     the theme + language toggles onto one row. On a phone that wrapped into a
     wall of pills that ate half the viewport. We progressively enhance: inject
     a hamburger button + a scoped stylesheet that, below 901px, collapses the
     links into a tap-to-open dropdown while the toggles stay on one compact
     bar. With JS off the original wrapping nav remains (every link reachable).
     The CSS is injected here — not in theme.css — because the .topbar pages are
     self-contained and never load theme.css. Fallbacks (var(--x, var(--y)))
     bridge the macro palette (--line/--panel) and the vector palette
     (--grid/--card). */
  var NAV_MOBILE_CSS = [
    ".nav-toggle{display:none}",
    /* back-to-top — shared skin for the two homes of one action: a sticky chip
       in the open flyout's lower-right (all collapsed-menu widths) and a
       floating chip fixed at the screen's lower-right (phones, below). Hidden
       by default everywhere; each home opts in with display:flex. */
    ".nav-totop{display:none;align-items:center;justify-content:center;width:40px;height:40px;padding:0;border:0;border-radius:50%;cursor:pointer;color:#fff;background:linear-gradient(140deg,#5b9dff,#3b82f6 40%,#6366f1 72%,#7c5cff);box-shadow:0 8px 20px -6px rgba(99,102,241,.65),0 3px 8px rgba(16,24,40,.35),inset 0 1px 0 rgba(255,255,255,.38);-webkit-tap-highlight-color:transparent;transition:opacity .3s ease,filter .3s ease,transform .3s cubic-bezier(.34,1.56,.64,1),box-shadow .3s ease}",
    ".nav-totop::before{content:'';position:absolute;inset:0;border-radius:inherit;background:radial-gradient(120% 90% at 30% 12%,rgba(255,255,255,.4),rgba(255,255,255,0) 55%);pointer-events:none}",
    ".nav-totop svg{width:17px;height:17px;position:relative}",
    ".nav-totop.is-live svg{animation:nav-totop-bob 2.4s ease-in-out .8s infinite}",
    /* extra specificity so the tap-flight beats the idle bob above */
    "button.nav-totop.launch svg{animation:nav-totop-launch .5s cubic-bezier(.5,0,.6,1)}",
    "@media (max-width:900px){",
      ".nav-toggle{display:inline-flex;align-items:center;justify-content:center;width:42px;height:34px;padding:0;flex:none;cursor:pointer;border-radius:10px;border:1px solid var(--line,var(--grid));background:var(--panel2,var(--card));color:var(--text,var(--ink));-webkit-tap-highlight-color:transparent}",
      ".nav-toggle-bars,.nav-toggle-bars::before,.nav-toggle-bars::after{content:'';display:block;width:18px;height:2px;border-radius:2px;background:currentColor;transition:transform .22s ease,opacity .2s ease}",
      ".nav-toggle-bars{position:relative}",
      ".nav-toggle-bars::before{position:absolute;left:0;top:-6px}",
      ".nav-toggle-bars::after{position:absolute;left:0;top:6px}",
      ".nav-open .nav-toggle-bars{background:transparent}",
      ".nav-open .nav-toggle-bars::before{transform:translateY(6px) rotate(45deg)}",
      ".nav-open .nav-toggle-bars::after{transform:translateY(-6px) rotate(-45deg)}",
      /* .topbar family: keep the flex row, hamburger first, toggles pushed right.
         width:100% defeats the shrink-to-fit + margin:0 auto that would otherwise
         centre the compact bar as a floating group. The padding !important is the
         one place we must beat an inline style: forex/commodities/bonds set
         style="padding:0" on .wrap, which would jam the hamburger and toggles flush
         against the screen edges — normalise every topbar to a 16px gutter. */
      ".topbar.has-nav-toggle .wrap{width:100%;flex-wrap:wrap;gap:8px;padding-left:16px!important;padding-right:16px!important}",
      ".topbar.has-nav-toggle .nav-ctrls{margin-left:auto}",
      /* .site-nav family: flatten the 2-col grid into one flex bar */
      ".site-nav.has-nav-toggle{display:flex;flex-wrap:wrap;align-items:center;gap:8px;position:relative}",
      ".site-nav.has-nav-toggle .nav-toggle{order:1}",
      ".site-nav.has-nav-toggle .nav-ctrls{order:2;margin-left:auto;margin-top:0}",
      ".site-nav.has-nav-toggle .nav-search{order:3;width:100%;max-width:none}",
      /* keep the right-hand controls INSIDE the viewport: the Mastermind / Terminal
         pills + theme + language toggles together overflowed a phone row, clipping
         the language toggle off the right edge. Let the cluster wrap and right-align
         so it can never spill past the screen. */
      ".has-nav-toggle .nav-ctrls{flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:8px;min-width:0;max-width:100%}",
      ".has-nav-toggle .nav-ctrls>*{flex:none}",
      /* the collapsible link panel (shared by both families) */
      ".has-nav-toggle .nav-links{display:none;position:absolute;top:100%;left:8px;right:8px;z-index:1000;box-sizing:border-box;flex-direction:column;flex-wrap:nowrap;align-items:stretch;gap:1px;margin-top:8px;padding:8px;border-radius:14px;background:var(--panel,var(--card));border:1px solid var(--line,var(--grid));box-shadow:0 18px 44px rgba(16,24,40,.30);max-height:78vh;overflow-y:auto;overflow-x:hidden}",
      ".has-nav-toggle.nav-open .nav-links{display:flex}",
      /* the brand / home lockup is the first row of the open panel — present it as a
         titled menu header (wordmark shown even on phones, where the bar hides it)
         with a divider, instead of a lone floating glyph. */
      ".has-nav-toggle .nav-links .nav-brand{display:flex;width:100%;align-items:center;gap:9px;margin:0 0 4px;padding:4px 10px 12px;border-bottom:1px solid var(--line,var(--grid))}",
      ".has-nav-toggle .nav-links .nav-brand .brand-word{display:inline!important;font-size:14px}",
      ".has-nav-toggle .nav-links a.nav-link{display:block;width:100%;padding:11px 12px;font-size:15px;border-radius:9px;white-space:normal}",
      /* nested fly-outs: accordion on mobile (tap parent → toggle open class) */
      ".has-nav-toggle .nav-links .nav-dd{display:block;width:100%}",
      ".has-nav-toggle .nav-links .nav-dd>a.nav-link .caret{display:inline-block;transition:transform .2s}",
      ".has-nav-toggle .nav-links .nav-dd.open>a.nav-link .caret{transform:rotate(180deg)}",
      ".has-nav-toggle .nav-links .nav-dd::after{display:none}",
      ".has-nav-toggle .nav-links .nav-dd-menu{position:static;transform:none;min-width:0;margin:0;padding:0;border:none;box-shadow:none;background:transparent;max-height:0;overflow:hidden;opacity:0;visibility:visible;transition:max-height .28s ease,opacity .18s ease,padding .28s ease}",
      ".has-nav-toggle .nav-links .nav-dd.open>.nav-dd-menu{max-height:600px;opacity:1;padding:8px 0 6px 12px}",
      ".has-nav-toggle .nav-links .nav-dd-menu a{display:block;padding:9px 12px;font-size:14px;font-weight:500;white-space:normal}",
      ".has-nav-toggle .nav-links .nav-dd-menu a .d{display:block;font-size:11px;opacity:.65;font-weight:400}",
      /* 3rd-tier accordion (Other Assets ▸ Bitcoin Vector / Commodities ▸ …):
         the fly-out becomes a deeper-indented inline accordion; the ▸ caret
         rotates to point down when its branch is open. */
      ".has-nav-toggle .nav-links .nav-sub>a.nav-sub-trig{display:flex;align-items:center}",
      ".has-nav-toggle .nav-links .nav-sub>a.nav-sub-trig .caret-r{margin-left:auto;display:inline-block;transition:transform .2s}",
      ".has-nav-toggle .nav-links .nav-sub.open>a.nav-sub-trig .caret-r{transform:rotate(90deg)}",
      ".has-nav-toggle .nav-links .nav-sub::after{display:none}",
      /* back-to-top, flyout home: pinned (sticky) to the open menu's lower-right.
         Muted while the page is already at the top; lit + gently bobbing once
         there is somewhere to go. Lives inside .nav-links, so it only ever
         exists in the collapsed menu. */
      ".has-nav-toggle .nav-links .nav-totop{display:flex;position:sticky;bottom:6px;z-index:6;align-self:flex-end;flex:none;margin:10px 8px 2px 0;opacity:.45;filter:saturate(.35)}",
      ".has-nav-toggle .nav-links .nav-totop.is-live{opacity:1;filter:none}",
      ".has-nav-toggle .nav-links .nav-totop.is-live:hover{transform:translateY(-2px) scale(1.05);box-shadow:0 12px 26px -8px rgba(99,102,241,.8),0 4px 10px rgba(16,24,40,.4),inset 0 1px 0 rgba(255,255,255,.38)}",
      ".has-nav-toggle .nav-links .nav-totop.is-live:active{transform:scale(.86)}",
      ".has-nav-toggle.nav-open .nav-links .nav-totop{animation:nav-totop-pop .5s cubic-bezier(.22,1,.36,1)}",
    "}",
    /* (The floating phone-only back-to-top FAB was removed — it clashed with the
       Mastermind chat orb in the lower-right corner. The in-flyout chip below stays.) */
    "@keyframes nav-totop-pop{0%{transform:scale(.3) rotate(-90deg)}62%{transform:scale(1.09) rotate(5deg)}100%{transform:scale(1) rotate(0)}}",
    "@keyframes nav-totop-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-2.5px)}}",
    "@keyframes nav-totop-launch{0%{transform:translateY(0);opacity:1}45%{transform:translateY(-22px);opacity:0}55%{transform:translateY(22px);opacity:0}100%{transform:translateY(0);opacity:1}}",
    "@media (prefers-reduced-motion:reduce){.nav-totop,.nav-totop svg{animation:none!important}}",
    "@media (max-width:560px){",
      /* phone: KEEP the Mastermind / Terminal labels — the lone icons were cryptic,
         and the row has room to spare once the theme + language toggles collapse
         into the settings gear. Just tighten the pills a hair so the whole control
         row (hamburger + both labelled pills + gear) still rides on one tidy line. */
      ".has-nav-toggle .nav-ctrls .ai-brief-link{padding:8px 12px;font-size:12px;gap:5px}",
    "}",
    /* very narrow phones (≤360px): shave the pills + cluster gap a touch more so the
       labelled pills never wrap off the control row. */
    "@media (max-width:360px){",
      ".has-nav-toggle .nav-ctrls{gap:6px}",
      ".has-nav-toggle .nav-ctrls .ai-brief-link{padding:7px 10px;font-size:11.5px;gap:4px}",
    "}"
  ].join('');

  function initMobileNav() {
    var nav = document.querySelector('.site-nav, .topbar');
    if (!nav) return;
    var links = nav.querySelector('.nav-links');
    if (!links || nav.querySelector('.nav-toggle')) return;  // skip legacy navs / re-runs

    if (!document.getElementById('nav-mobile-css')) {
      var st = document.createElement('style');
      st.id = 'nav-mobile-css';
      st.textContent = NAV_MOBILE_CSS;
      document.head.appendChild(st);
    }

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nav-toggle';
    btn.setAttribute('aria-label', 'Toggle navigation menu');
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = '<span class="nav-toggle-bars" aria-hidden="true"></span>';

    // .topbar nests its flex row inside .wrap; .site-nav is the bar itself
    var bar = nav.classList.contains('topbar') ? (nav.querySelector('.wrap') || nav) : nav;
    bar.insertBefore(btn, bar.firstChild);
    nav.classList.add('has-nav-toggle');

    function closeNav() {
      nav.classList.remove('nav-open');
      btn.setAttribute('aria-expanded', 'false');
      links.querySelectorAll('.nav-dd.open').forEach(function(d) { d.classList.remove('open'); });
    }
    btn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      var open = nav.classList.toggle('nav-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    // accordion: tap a dropdown parent to toggle its submenu (mobile only).
    // Works at any depth (Other Assets ▸ Commodities ▸ …): tapping closes only
    // SIBLINGS at that level — never the ancestor branch containing the tap —
    // and collapsing a branch also collapses any descendants left open.
    links.querySelectorAll('.nav-dd').forEach(function(dd) {
      var trigger = dd.querySelector(':scope > a');   // .nav-link OR .nav-sub-trig
      if (!trigger) return;
      trigger.addEventListener('click', function(e) {
        if (window.innerWidth > 900) return;
        e.preventDefault(); e.stopPropagation();
        var wasOpen = dd.classList.contains('open');
        dd.parentElement.querySelectorAll(':scope > .nav-dd.open').forEach(function(d) {
          if (d !== dd) d.classList.remove('open');
        });
        if (wasOpen) {
          dd.querySelectorAll('.nav-dd.open').forEach(function(d) { d.classList.remove('open'); });
          dd.classList.remove('open');
        } else {
          dd.classList.add('open');
        }
      });
    });
    // back-to-top — a sticky chip pinned to the open flyout's lower-right (all
    // collapsed-menu widths, since the nav itself scrolls away with the page).
    // Tapping launches the arrow, glides the page home, and closes the menu.
    // (The floating phone twin was removed — it clashed with the chat orb.)
    function makeTotop(cls) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = cls;
      b.setAttribute('aria-label', 'Back to top');
      b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V6"/><path d="m5 12 7-7 7 7"/></svg>';
      b.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation();
        b.classList.remove('launch');
        void b.offsetWidth;                      // restart the flight animation
        b.classList.add('launch');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        links.scrollTop = 0;
        setTimeout(function () {
          b.classList.remove('launch');
          if (nav.classList.contains('nav-open')) closeNav();
        }, 260);
      });
      return b;
    }
    var menuTotop = makeTotop('nav-totop');
    links.appendChild(menuTotop);
    function paintTotop() {
      var y = window.scrollY || document.documentElement.scrollTop || 0;
      menuTotop.classList.toggle('is-live', y > 240);
    }
    window.addEventListener('scroll', paintTotop, { passive: true });
    paintTotop();
    // close after a destination link is picked, on Escape, on outside tap, on widen
    links.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (a && !a.closest('.nav-dd') || (a && a.closest('.nav-dd-menu'))) closeNav();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeNav(); });
    document.addEventListener('click', function (e) { if (!nav.contains(e.target)) closeNav(); });
    window.addEventListener('resize', function () { if (window.innerWidth > 900) closeNav(); });
  }

  /* ---- content-aware desktop nav ------------------------------------------
     The market rail is personalized after auth: one user may see only US while
     another keeps four country menus. Measuring the actual, post-fold DOM lets
     the same navigation choose one row when it fits and a composed second row
     when it does not. This is intentionally content-driven rather than a set of
     profile-specific breakpoints, so new menu entries inherit the behavior. */
  function initAdaptiveNav() {
    var nav = document.querySelector('.site-nav, .topbar');
    if (!nav || nav.getAttribute('data-adaptive-nav-ready') === '1') return;
    var links = nav.querySelector('.nav-links');
    if (!links) return;
    nav.setAttribute('data-adaptive-nav-ready', '1');

    // Mastermind is now a purpose-built Research-menu callout. Remove old pills
    // from both freshly rendered and still-cached pages before measuring.
    nav.querySelectorAll('.nav-ctrls .mastermind-link, .nav-ctrls a[href*="bot.mastermind-x.com"]').forEach(function (a) {
      a.remove();
    });

    var raf = 0;
    function directChildrenWidth() {
      var total = 0, count = 0;
      [].slice.call(links.children).forEach(function (node) {
        if (!node.getBoundingClientRect || node.classList.contains('nav-totop')) return;
        var style = window.getComputedStyle(node);
        if (style.display === 'none' || style.position === 'fixed') return;
        total += node.getBoundingClientRect().width;
        count += 1;
      });
      return total + Math.max(0, count - 1) * 3;
    }

    function paint() {
      raf = 0;
      if (window.innerWidth <= 900) {
        nav.removeAttribute('data-nav-layout');
        return;
      }
      var bar = nav.classList.contains('topbar') ? (nav.querySelector('.wrap') || nav) : nav;
      var search = nav.querySelector('.nav-search');
      var controls = nav.querySelector('.nav-ctrls');
      // Set stacked first so the link children receive their natural width
      // instead of being squeezed by a stale single-row grid.
      nav.setAttribute('data-nav-layout', 'stacked');
      var needed = directChildrenWidth()
        + (search ? 124 : 0)
        + (controls ? controls.getBoundingClientRect().width : 0)
        + 34;
      nav.setAttribute('data-nav-layout', needed <= bar.clientWidth ? 'single' : 'stacked');
    }

    function schedule() {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(paint);
    }

    window.addEventListener('resize', schedule, { passive: true });
    document.addEventListener('mmx-markets-change', schedule);
    document.addEventListener('langchange', schedule);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(schedule);
    schedule();
  }

  /* ---- settings modal (theme + language + future account) -----------------
     The nav used to carry the dark/light switch AND the EN/中文 toggle inline in
     .nav-ctrls; with the Mastermind + Terminal pills that overflowed the bar into
     a third row on narrower laptops. We consolidate both toggles behind ONE gear:
     the existing .theme-switch / .lang-toggle nodes are MOVED, unchanged, into a
     premium modal (their click-wiring — bound below in DOMContentLoaded — rides
     along on the elements, and their visuals are pure-CSS off data-theme/data-lang,
     so they keep working and reflecting state wherever they live). The gear takes
     their place, so the bar is a tidy two rows again on every page.

     CSS is injected here — NOT theme.css — because the vector / forex / bonds /
     commodities family never loads theme.css; var(--x,var(--y)) fallbacks bridge
     the macro palette (--panel2/--line/--link/--text) and the vector palette
     (--card/--grid/--blue/--ink). Built once, idempotent. Account rows are a
     styled placeholder for the coming sign-in / sync. */
  var SET_ICON = {
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    theme: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 3v18"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/></svg>',
    lang: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0z"/></svg>',
    // expand/maximize arrows — opens the full settings dashboard
    maximize: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>'
  };

  /* =======================================================================
     ACCOUNT SYSTEM — Supabase auth, shared by EVERY page (the gear's account
     section is the entry point). Strictly additive + fail-soft: with no baked
     config the account UI hides and not a single third-party byte is fetched.
     The Supabase SDK is self-hosted (templates/supabase.js -> site/supabase.js;
     a JS CDN is blocked behind the GFW) and loaded LAZILY — only when the user
     opens the modal or a prior session must be restored. Sign-in methods:
       • Google  (signInWithOAuth — needs the provider enabled in the dashboard)
       • Email + password (no email verification — disable "Confirm email")
       • WeChat  (no native Supabase provider yet — shown as "coming soon")
     The session is persisted in PERMANENT cookies (see COOKIE_STORAGE) so the
     user stays signed in across visits and across every page on the origin. */
  var GOOGLE_SVG = '<svg class="ob-g" viewBox="0 0 18 18" aria-hidden="true"><path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/><path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.02-3.7H.96v2.34A9 9 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.98 10.72a5.4 5.4 0 0 1 0-3.44V4.94H.96a9 9 0 0 0 0 8.12l3.02-2.34z"/><path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.47.89 11.43 0 9 0A9 9 0 0 0 .96 4.94l3.02 2.34C4.68 5.16 6.66 3.58 9 3.58z"/></svg>';
  var WECHAT_SVG = '<svg class="ob-wx" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8.7 3.3C4.9 3.3 1.8 6 1.8 9.3c0 1.9 1 3.5 2.6 4.7l-.7 2.1 2.4-1.3c.86.24 1.6.36 2.6.36.23 0 .46-.01.68-.03a5.2 5.2 0 0 1-.2-1.43c0-3 2.9-5.4 6.4-5.4l.6.02C15.7 5.5 12.6 3.3 8.7 3.3zM6.4 7.5a1 1 0 1 1 0 2 1 1 0 0 1 0-2zm4.6 0a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/><path d="M22.2 14.1c0-2.7-2.6-4.9-5.8-4.9s-5.8 2.2-5.8 4.9 2.6 4.9 5.8 4.9c.74 0 1.45-.13 2.1-.34l2 1.1-.55-1.85c1.3-.9 2.25-2.2 2.25-3.81zm-7.7-1.1a.8.8 0 1 1 0 1.6.8.8 0 0 1 0-1.6zm3.9 0a.8.8 0 1 1 0 1.6.8.8 0 0 1 0-1.6z"/></svg>';
  var X_SVG = '<svg class="ob-x" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24h-6.66l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zM17.083 19.77h1.833L7.084 4.126H5.117z"/></svg>';
  var EYE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg>';

  /* ---- session cookie storage — @supabase/ssr 0.12-COMPATIBLE ------------
     The login is SHARED across every *.mastermind-x.com app (this dashboard, the
     Terminal at app.mastermind-x.com, the bot at bot.mastermind-x.com), so the
     on-disk cookie must be byte-identical to what @supabase/ssr writes/reads and
     scoped to the parent domain. Format: value = "base64-" + base64url(JSON);
     when that exceeds 3180 chars it splits into `<key>.0`, `<key>.1`, … (no
     separate count cookie). Domain=.mastermind-x.com on a mastermind-x.com host
     (host-only elsewhere — *.github.io / localhost). ~390-day Max-Age, Path=/,
     SameSite=Lax, Secure on https. Verified byte-for-byte vs @supabase/ssr 0.12
     (read + write, both directions). One-time re-login for anyone holding the
     prior count-cookie format — _clearCookieKey wipes it on the next write. */
  var AUTH_COOKIE_DAYS = 390, AUTH_CHUNK = 3180, AUTH_MAXCHUNKS = 32, AUTH_B64 = 'base64-';
  function _cookieMap() {
    var out = {}, parts = (document.cookie || '').split(';');
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim(); if (!p) continue;
      var eq = p.indexOf('='); if (eq < 0) continue;
      out[p.slice(0, eq)] = p.slice(eq + 1);
    }
    return out;
  }
  // share the session across every mastermind-x.com subdomain (host-only otherwise)
  function _cookieDomain() {
    return /(^|\.)mastermind-x\.com$/i.test(location.hostname || '') ? '; Domain=.mastermind-x.com' : '';
  }
  function _setCookie(name, val, days) {
    var secure = location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = name + '=' + val + '; Path=/; Max-Age=' + (days * 86400) +
                      '; SameSite=Lax' + secure + _cookieDomain();
  }
  function _delCookie(name) {
    // clear the domain-scoped cookie AND any legacy host-only one of the same name
    document.cookie = name + '=; Path=/; Max-Age=0; SameSite=Lax' + _cookieDomain();
    if (_cookieDomain()) document.cookie = name + '=; Path=/; Max-Age=0; SameSite=Lax';
  }
  function _clearCookieKey(name, map) {
    map = map || _cookieMap();
    if (map[name] != null) _delCookie(name);
    for (var i = 0; i < AUTH_MAXCHUNKS; i++) {
      if (map[name + '.' + i] != null) _delCookie(name + '.' + i);
    }
  }
  // base64url of UTF-8 — matches @supabase/ssr stringToBase64URL / stringFromBase64URL
  function _b64uEnc(str) {
    return btoa(unescape(encodeURIComponent(str))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function _b64uDec(s) {
    var b = s.replace(/-/g, '+').replace(/_/g, '/');
    while (b.length % 4) b += '=';
    return decodeURIComponent(escape(atob(b)));
  }
  var COOKIE_STORAGE = {
    getItem: function (key) {
      var map = _cookieMap(), combined = null;
      if (map[key] != null) combined = map[key];               // single (unchunked) cookie
      else {                                                    // else join chunks .0,.1,…
        var vals = [], i = 0, c;
        for (; (c = map[key + '.' + i]) != null; i++) vals.push(c);
        if (vals.length) combined = vals.join('');
      }
      if (combined == null) return null;
      if (combined.indexOf(AUTH_B64) !== 0) return combined;    // raw (non-base64) value
      try { return _b64uDec(combined.slice(AUTH_B64.length)); } catch (e) { return null; }
    },
    setItem: function (key, value) {
      _clearCookieKey(key);
      var enc = AUTH_B64 + _b64uEnc(String(value == null ? '' : value));
      if (enc.length <= AUTH_CHUNK) { _setCookie(key, enc, AUTH_COOKIE_DAYS); return; }
      for (var i = 0, n = 0; i < enc.length; i += AUTH_CHUNK, n++) {
        _setCookie(key + '.' + n, enc.slice(i, i + AUTH_CHUNK), AUTH_COOKIE_DAYS);
      }
    },
    removeItem: function (key) { _clearCookieKey(key); }
  };

  /* ---- lazy Supabase client (self-hosted SDK) --------------------------- */
  var _sbCfg = window.SUPABASE_CFG;
  var _authEnabled = !!(_sbCfg && _sbCfg.url && _sbCfg.anonKey);
  var _sb = null, _sbLoading = null, _curUser = null, _authReady = false, _authBooted = false;
  var _SDK_URL = 'supabase.js';

  function _loadSDK() {
    if (window.supabase && window.supabase.createClient) return Promise.resolve();
    if (_sbLoading) return _sbLoading;
    _sbLoading = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = _SDK_URL; s.async = true;
      s.onload = resolve; s.onerror = function () { reject(new Error('sdk')); };
      (document.head || document.documentElement).appendChild(s);
    });
    return _sbLoading;
  }
  function getSupabaseClient() {
    if (!_authEnabled) return Promise.reject(new Error('auth-disabled'));
    if (_sb) return Promise.resolve(_sb);
    return _loadSDK().then(function () {
      if (_sb) return _sb;
      _sb = window.supabase.createClient(_sbCfg.url, _sbCfg.anonKey, {
        auth: {
          persistSession: true, autoRefreshToken: true, detectSessionInUrl: true,
          // PKCE (not implicit): the return carries a one-time ?code= (NOT tokens)
          // that's useless without the code_verifier we stashed in storage before
          // redirecting — so tokens never touch the URL/history, and a pasted
          // #access_token link can't seed a session (no login-CSRF / fixation).
          flowType: 'pkce',
          storage: COOKIE_STORAGE,         // permanent cookie session, shared cross-subdomain
          storageKey: _storageKey()        // sb-<ref>-auth-token — must match @supabase/ssr
        }
      });
      _sb.auth.onAuthStateChange(function (evt, session) { _onAuth(evt, session); });
      return _sb;
    });
  }
  window.getSupabaseClient = getSupabaseClient;

  function _hasSessionCookie() {
    var map = _cookieMap();
    // single cookie `sb-…-auth-token` OR a chunk `sb-…-auth-token.0` (chunked
    // sessions have no unchunked cookie). Excludes `…-auth-token-code-verifier`.
    for (var k in map) { if (map.hasOwnProperty(k) && /^sb-.*-auth-token(\.\d+)?$/.test(k)) return true; }
    return false;
  }
  function _storageKey() {
    try { return 'sb-' + new URL(_sbCfg.url).hostname.split('.')[0] + '-auth-token'; }
    catch (e) { return 'sb-auth-token'; }
  }
  function _isAuthReturn() {
    var h = location.hash || '', q = location.search || '';
    // PKCE returns the auth code in the query (?code=), never in the hash. Errors
    // can arrive in either the query (?error=) or the fragment (#error=), e.g. a
    // provider-side denial. We deliberately do NOT treat a bare #access_token=
    // hash as an auth return: under flowType:'pkce' (getSupabaseClient) the
    // vendored gotrue-js _getSessionFromURL throws "Not a valid PKCE flow url."
    // on any non-?code= URL, so hash tokens are never consumed and a pasted
    // #access_token= link cannot seed/fixate a session. (Verified against the
    // gotrue-js in supabase.js.) The old access_token= clause was dead legacy.
    return /[?&]code=/.test(q) || /[?&]error=/.test(q) || /[#&]error=/.test(h);
  }
  function _emitAuth(detail) {
    try { window.dispatchEvent(new CustomEvent('mdx-auth', { detail: detail })); }
    catch (e) {
      var ev = document.createEvent('CustomEvent');
      ev.initCustomEvent('mdx-auth', false, false, detail);
      window.dispatchEvent(ev);
    }
  }
  // supabase-js fires INITIAL_SESSION right after createClient; only SIGNED_OUT
  // clears the user. Broadcast every change so the gear's account section AND
  // the watchlist's cloud-sync (auth.js) react off one shared session.
  function _onAuth(evt, session) {
    _curUser = (session && session.user) ? session.user : (evt === 'SIGNED_OUT' ? null : _curUser);
    if (evt === 'SIGNED_OUT') _curUser = null;
    // Drop any cached entitlement when the account changes, so a stale plan never shows for the
    // wrong (or signed-out) user; the next dashboard render re-fetches for the current session.
    if (!_curUser || (_curUser.id && _curUser.id !== _sdPlanFor)) { _sdPlan = null; _sdPlanFor = null; }
    if (!_curUser || (_curUser.id && _curUser.id !== _sdUsageFor)) { _sdUsage = null; _sdUsageFor = null; _sdUsageErr = false; }
    _authReady = true;
    _emitAuth({ user: _curUser, event: evt });
    _renderAcct();
  }

  window.MDXAuth = {
    enabled: function () { return _authEnabled; },
    user: function () { return _curUser; },
    hasSession: function () { return _hasSessionCookie(); },
    client: getSupabaseClient,
    open: function (mode) { openAuthModal(mode || 'signin'); },
    signOut: function () {
      if (!_authEnabled) return Promise.resolve();
      // sb.auth.signOut() fires SIGNED_OUT via onAuthStateChange -> _onAuth, which
      // owns the UI reset. Only fall back to a manual emit if that path errors,
      // so a normal sign-out updates each subscriber exactly once.
      return getSupabaseClient().then(function (sb) { return sb.auth.signOut(); })
        .catch(function () { _curUser = null; _emitAuth({ user: null, event: 'SIGNED_OUT' }); _renderAcct(); });
    },
    onChange: function (cb) {
      window.addEventListener('mdx-auth', function (e) {
        cb(e.detail && e.detail.user, e.detail && e.detail.event);
      });
      if (_authReady) { try { cb(_curUser, 'INITIAL_SESSION'); } catch (e) {} }
    }
  };

  // Restore a prior session (or consume an OAuth/magic-link return) on load so
  // every page shows the signed-in state. No-op + zero network for anon users.
  // Always settle the auth state exactly once so every consumer (the gear's
  // account bar + the watchlist sync pill) resolves — even for an anonymous
  // visitor (no network) or when the self-hosted SDK fails to load (GFW).
  function _authResolveAnon(evt) {
    if (_authReady) return;            // a real session already resolved it
    _authReady = true;
    _emitAuth({ user: null, event: evt });
    _renderAcct();
  }
  function _authBoot() {
    if (_authBooted || !_authEnabled) return;
    _authBooted = true;
    if (_isAuthReturn() || _hasSessionCookie()) {
      // restore the session / exchange the ?code= return; on SDK-load failure
      // (e.g. supabase.js blocked) settle to signed-out so nothing hangs.
      getSupabaseClient().then(function (sb) { return sb.auth.getSession(); })
        .catch(function () { _authResolveAnon('SDK_FAILED'); });
    } else {
      _authResolveAnon('INITIAL_SESSION');   // anonymous — settle, no network
    }
  }

  /* ---- the frosted-glass auth modal (matches index.html .glass) --------- */
  var AUTH_L = {
    siTitle:   ['Welcome back', '欢迎回来'],
    siSub:     ['Sign in to sync across your devices', '登录以在各设备间同步'],
    suTitle:   ['Create your account', '创建账户'],
    suSub:     ['Free — sync watchlists, alerts & settings', '免费 — 同步自选、提醒与设置'],
    google:    ['Continue with Google', '使用 Google 继续'],
    x:         ['Continue with X', '使用 X 继续'],
    wechat:    ['Continue with WeChat', '使用微信继续'],
    soon:      ['Soon', '即将'],
    wechatSoon:['WeChat sign-in is coming soon.', '微信登录即将推出。'],
    or:        ['or', '或'],
    email:     ['Email address', '邮箱地址'],
    emailPh:   ['you@email.com', 'you@email.com'],
    pw:        ['Password', '密码'],
    pwPh:      ['At least 6 characters', '至少 6 个字符'],
    si:        ['Sign in', '登录'],
    su:        ['Create account', '注册'],
    working:   ['Working…', '处理中…'],
    redirect:  ['Redirecting to Google…', '正在跳转到 Google…'],
    redirectX: ['Redirecting to X…', '正在跳转到 X…'],
    toSignup:  ['New here? Create an account', '新用户？创建账户'],
    toSignin:  ['Already have an account? Sign in', '已有账户？登录'],
    okSignup:  ['Account created — you’re signed in!', '账户已创建——已登录！'],
    errEmail:  ['Enter a valid email address.', '请输入有效的邮箱地址。'],
    errPw:     ['Password must be at least 6 characters.', '密码至少 6 个字符。'],
    errCreds:  ['Wrong email or password.', '邮箱或密码错误。'],
    errDupe:   ['That email is already registered — try signing in.', '该邮箱已注册——请直接登录。'],
    errConfirm:['Check your inbox to confirm your email, then sign in.', '请查收邮箱完成验证后再登录。'],
    errSdk:    ['Could not load sign-in. Check your connection.', '无法加载登录组件，请检查网络。'],
    errGen:    ['Something went wrong — please try again.', '出错了，请重试。'],
    legal:     ['Research, not investment advice.', '本产品为研究工具，非投资建议。'],
    close:     ['Close', '关闭'],
    showpw:    ['Show password', '显示密码'],
    signedin:  ['Synced across your devices', '已在各设备间同步'],
    signout:   ['Sign out', '退出']
  };
  function _authL(k) { var p = AUTH_L[k]; return p ? p[curLang() === 'zh' ? 1 : 0] : ''; }
  function _setTxt(id, t) { var e = document.getElementById(id); if (e) e.textContent = t; }

  var AUTH_CSS = [
    '.auth-overlay{position:fixed;inset:0;z-index:100001;display:flex;align-items:center;justify-content:center;padding:20px;background:color-mix(in srgb,#04060c 72%,transparent);-webkit-backdrop-filter:blur(10px) saturate(1.05);backdrop-filter:blur(10px) saturate(1.05);opacity:0;visibility:hidden;pointer-events:none;transition:opacity .24s ease,visibility 0s linear .24s}',
    '.auth-overlay.open{opacity:1;visibility:visible;pointer-events:auto;transition:opacity .24s ease,visibility 0s}',
    'html.auth-lock{overflow:hidden}',
    '.auth-card{position:relative;width:min(420px,94vw);box-sizing:border-box;border-radius:20px;overflow:hidden;isolation:isolate;background:color-mix(in srgb,var(--panel,var(--card,#0e1320)) 86%,transparent);border:1px solid color-mix(in srgb,var(--text,#e7ecf6) 13%,var(--line,var(--grid,#283042)));-webkit-backdrop-filter:blur(16px) saturate(1.1);backdrop-filter:blur(16px) saturate(1.1);box-shadow:0 32px 90px -20px rgba(0,0,0,.82),inset 0 1px 0 color-mix(in srgb,#fff 8%,transparent);padding:26px 24px 20px;transform:translateY(12px) scale(.98);opacity:.4;transition:transform .3s cubic-bezier(.32,1.28,.5,1),opacity .22s ease;font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--text,var(--ink,#e7ecf6))}',
    'html[data-theme="light"] .auth-card{background:color-mix(in srgb,var(--panel,#fff) 92%,transparent);box-shadow:0 30px 80px -22px rgba(20,30,50,.4),inset 0 1px 0 rgba(255,255,255,.7)}',
    '.auth-overlay.open .auth-card{transform:none;opacity:1}',
    '@supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){.auth-card{background:var(--panel,var(--card,#0e1320))}}',
    '.auth-card::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--link,var(--blue,#4f8cff)),color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 18%,transparent))}',
    '.auth-x{position:absolute;top:14px;right:14px;width:30px;height:30px;border-radius:9px;border:1px solid transparent;background:transparent;color:var(--muted,var(--ink-3,#8b93a7));cursor:pointer;display:inline-flex;align-items:center;justify-content:center;transition:background .18s,color .18s}',
    '.auth-x:hover{background:color-mix(in srgb,var(--text,#fff) 8%,transparent);color:var(--text,var(--ink))}',
    '.auth-x svg{width:16px;height:16px}',
    '.auth-brand{display:flex;align-items:center;gap:11px;margin:0 0 17px}',
    '.auth-brand .ab-ic{width:38px;height:38px;border-radius:11px;display:inline-flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 16%,transparent);color:var(--link,var(--blue,#4f8cff));flex:none}',
    '.auth-brand .ab-ic svg{width:20px;height:20px}',
    '.auth-brand h2{margin:0;font-size:18px;font-weight:800;letter-spacing:.01em;line-height:1.15;color:var(--text,var(--ink))}',
    '.auth-brand .ab-sub{display:block;font-size:11.5px;font-weight:500;color:var(--muted,var(--ink-3));margin-top:2px}',
    '.auth-oauth{display:flex;flex-direction:column;gap:9px;margin:0 0 4px}',
    '.auth-ob{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;padding:11px 14px;border-radius:12px;font-size:13.5px;font-weight:700;cursor:pointer;border:1px solid var(--line,var(--grid,#283042));background:var(--panel2,var(--card,#141a28));color:var(--text,var(--ink));font-family:inherit;transition:border-color .18s,transform .12s ease,background .18s}',
    '.auth-ob:hover{border-color:color-mix(in srgb,var(--text,#fff) 26%,transparent);transform:translateY(-1px)}',
    '.auth-ob:active{transform:translateY(0)}',
    '.auth-ob:disabled{opacity:.6;cursor:default;transform:none}',
    '.auth-ob svg{width:18px;height:18px;flex:none}',
    '.auth-ob.wechat .ob-wx{color:#07C160}',
    '.auth-ob .ob-soon{font-size:9px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;padding:2px 6px;border-radius:999px;background:color-mix(in srgb,#07C160 18%,transparent);color:#07C160}',
    '.auth-div{display:flex;align-items:center;gap:12px;margin:14px 0 12px;color:var(--muted,var(--ink-3));font-size:11px;text-transform:uppercase;letter-spacing:.08em}',
    '.auth-div::before,.auth-div::after{content:"";flex:1;height:1px;background:var(--line,var(--grid,#283042))}',
    '.auth-f{display:flex;flex-direction:column;gap:11px}',
    '.auth-field{display:flex;flex-direction:column;gap:5px}',
    '.auth-field label{font-size:11px;font-weight:700;color:var(--muted,var(--ink-3));letter-spacing:.02em}',
    '.auth-in{width:100%;box-sizing:border-box;padding:11px 13px;border-radius:11px;border:1px solid var(--line,var(--grid,#283042));background:var(--bg,var(--card,#0b0f1a));color:var(--text,var(--ink));font-size:14px;font-family:inherit;outline:none;transition:border-color .18s,box-shadow .18s}',
    '.auth-in:focus{border-color:var(--link,var(--blue,#4f8cff));box-shadow:0 0 0 3px color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 22%,transparent)}',
    '.auth-pw-wrap{position:relative}',
    '.auth-pw-wrap .auth-in{padding-right:42px}',
    '.auth-reveal{position:absolute;top:50%;right:8px;transform:translateY(-50%);width:28px;height:28px;border:0;background:transparent;color:var(--muted,var(--ink-3));cursor:pointer;display:inline-flex;align-items:center;justify-content:center;border-radius:7px}',
    '.auth-reveal:hover{color:var(--text,var(--ink));background:color-mix(in srgb,var(--text,#fff) 8%,transparent)}',
    '.auth-reveal svg{width:16px;height:16px}',
    '.auth-submit{margin-top:4px;width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--link,var(--blue,#4f8cff));background:var(--link,var(--blue,#4f8cff));color:#fff;font-size:14px;font-weight:800;cursor:pointer;font-family:inherit;transition:filter .18s,transform .12s ease,opacity .18s}',
    '.auth-submit:hover{filter:brightness(1.06);transform:translateY(-1px)}',
    '.auth-submit:active{transform:translateY(0)}',
    '.auth-submit:disabled{opacity:.6;cursor:default;transform:none;filter:none}',
    '.auth-msg{font-size:12px;line-height:1.45;margin:11px 0 0;padding:9px 11px;border-radius:10px;display:none}',
    '.auth-msg.show{display:block}',
    '.auth-msg.err{background:color-mix(in srgb,var(--down,#ff5c6c) 14%,transparent);color:var(--down,#ff5c6c);border:1px solid color-mix(in srgb,var(--down,#ff5c6c) 30%,transparent)}',
    '.auth-msg.ok{background:color-mix(in srgb,var(--up,#23c08a) 14%,transparent);color:var(--up,#23c08a);border:1px solid color-mix(in srgb,var(--up,#23c08a) 30%,transparent)}',
    '.auth-foot{margin:15px 0 0;text-align:center}',
    '.auth-switch{background:none;border:0;color:var(--link,var(--blue,#4f8cff));font-size:12.5px;font-weight:700;cursor:pointer;font-family:inherit;padding:4px}',
    '.auth-switch:hover{text-decoration:underline}',
    '.auth-legal{margin:12px 0 0;font-size:10px;line-height:1.5;color:var(--muted,var(--ink-3));text-align:center}',
    '@media (max-width:520px){.auth-overlay{align-items:flex-end;padding:0}.auth-card{width:100%;border-radius:20px 20px 0 0;padding:24px 18px calc(18px + env(safe-area-inset-bottom));transform:translateY(100%);opacity:1}.auth-overlay.open .auth-card{transform:none}}',
    '@media (prefers-reduced-motion:reduce){.auth-overlay,.auth-card{transition:opacity .15s ease}.auth-card{transform:none}}'
  ].join('');

  var _authBuilt = false, _authMode = 'signin', _authLastFocus = null;
  // remember the CURRENT message + busy state by KEY so a mid-flow 'langchange'
  // re-localizes the visible status/error and the 'Working…' button.
  var _authMsgKey = null, _authMsgKind = null, _authBusyState = false;
  function _authInjectCSS() {
    if (document.getElementById('auth-css')) return;
    var st = document.createElement('style'); st.id = 'auth-css'; st.textContent = AUTH_CSS;
    document.head.appendChild(st);
  }
  function _buildAuthModal() {
    if (_authBuilt) return;
    _authInjectCSS();
    var ov = document.createElement('div');
    ov.className = 'auth-overlay'; ov.id = 'auth-overlay';
    ov.innerHTML =
      '<div class="auth-card" role="dialog" aria-modal="true" aria-labelledby="auth-title">' +
        '<button type="button" class="auth-x" id="auth-x" aria-label="Close">' + SET_ICON.x + '</button>' +
        '<div class="auth-brand"><span class="ab-ic">' + SET_ICON.user + '</span>' +
          '<div><h2 id="auth-title"></h2><span class="ab-sub" id="auth-sub"></span></div></div>' +
        '<div class="auth-oauth">' +
          '<button type="button" class="auth-ob" id="auth-google">' + GOOGLE_SVG + '<span id="auth-google-t"></span></button>' +
          '<button type="button" class="auth-ob xcom" id="auth-xbtn">' + X_SVG + '<span id="auth-xbtn-t"></span></button>' +
          '<button type="button" class="auth-ob wechat" id="auth-wechat">' + WECHAT_SVG + '<span id="auth-wechat-t"></span><span class="ob-soon" id="auth-wechat-soon"></span></button>' +
        '</div>' +
        '<div class="auth-div"><span id="auth-or"></span></div>' +
        '<form class="auth-f" id="auth-form" novalidate>' +
          '<div class="auth-field"><label for="auth-email" id="auth-email-l"></label>' +
            '<input class="auth-in" type="email" id="auth-email" autocomplete="email" autocapitalize="off" spellcheck="false"></div>' +
          '<div class="auth-field"><label for="auth-pw" id="auth-pw-l"></label>' +
            '<div class="auth-pw-wrap"><input class="auth-in" type="password" id="auth-pw" autocomplete="current-password">' +
              '<button type="button" class="auth-reveal" id="auth-reveal">' + EYE_SVG + '</button></div></div>' +
          '<button type="submit" class="auth-submit" id="auth-submit"></button>' +
        '</form>' +
        '<div class="auth-msg" id="auth-msg" role="alert"></div>' +
        '<div class="auth-foot"><button type="button" class="auth-switch" id="auth-switch"></button></div>' +
        '<p class="auth-legal" id="auth-legal"></p>' +
      '</div>';
    document.body.appendChild(ov);
    _authBuilt = true;
    _wireAuthModal(ov);
    _authRelabel();
    document.addEventListener('langchange', _authRelabel);
  }
  function _authRelabel() {
    if (!_authBuilt) return;
    var si = _authMode === 'signin';
    _setTxt('auth-title', _authL(si ? 'siTitle' : 'suTitle'));
    _setTxt('auth-sub', _authL(si ? 'siSub' : 'suSub'));
    _setTxt('auth-google-t', _authL('google'));
    _setTxt('auth-xbtn-t', _authL('x'));
    _setTxt('auth-wechat-t', _authL('wechat'));
    _setTxt('auth-wechat-soon', _authL('soon'));
    _setTxt('auth-or', _authL('or'));
    _setTxt('auth-email-l', _authL('email'));
    _setTxt('auth-pw-l', _authL('pw'));
    _setTxt('auth-submit', _authBusyState ? _authL('working') : _authL(si ? 'si' : 'su'));
    _setTxt('auth-switch', _authL(si ? 'toSignup' : 'toSignin'));
    _setTxt('auth-legal', _authL('legal'));
    var em = document.getElementById('auth-email'); if (em) em.placeholder = _authL('emailPh');
    var pw = document.getElementById('auth-pw');
    if (pw) { pw.placeholder = _authL('pwPh'); pw.setAttribute('autocomplete', si ? 'current-password' : 'new-password'); }
    var x = document.getElementById('auth-x'); if (x) x.setAttribute('aria-label', _authL('close'));
    var rv = document.getElementById('auth-reveal'); if (rv) rv.setAttribute('aria-label', _authL('showpw'));
    // re-localize a currently-visible status/error message
    if (_authMsgKey) {
      var mm = document.getElementById('auth-msg');
      if (mm && mm.className.indexOf('show') >= 0) mm.textContent = _authL(_authMsgKey);
    }
  }
  function _authMsg(text, kind) {
    var m = document.getElementById('auth-msg'); if (!m) return;
    if (!text) { m.className = 'auth-msg'; m.textContent = ''; _authMsgKey = null; _authMsgKind = null; return; }
    m.textContent = text; m.className = 'auth-msg show ' + (kind || 'err');
  }
  // show a message BY KEY so it can be re-localized on langchange
  function _authShow(key, kind) {
    _authMsgKey = key || null; _authMsgKind = kind || null;
    _authMsg(key ? _authL(key) : '', kind);
  }
  function _authBusy(b) {
    _authBusyState = b;
    var s = document.getElementById('auth-submit'), g = document.getElementById('auth-google'),
        x = document.getElementById('auth-xbtn');
    if (s) { s.disabled = b; s.textContent = b ? _authL('working') : _authL(_authMode === 'signin' ? 'si' : 'su'); }
    if (g) g.disabled = b;
    if (x) x.disabled = b;
  }
  function _wireAuthModal(ov) {
    var card = ov.querySelector('.auth-card');
    ov.addEventListener('mousedown', function (e) { if (e.target === ov) closeAuthModal(); });
    document.getElementById('auth-x').addEventListener('click', closeAuthModal);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && ov.classList.contains('open')) closeAuthModal();
    });
    document.getElementById('auth-switch').addEventListener('click', function () {
      _authMode = _authMode === 'signin' ? 'signup' : 'signin';
      _authMsg('', null); _authRelabel(); _authBusy(false);
      var em = document.getElementById('auth-email'); if (em) em.focus();
    });
    document.getElementById('auth-reveal').addEventListener('click', function () {
      var pw = document.getElementById('auth-pw'); if (!pw) return;
      pw.type = pw.type === 'password' ? 'text' : 'password';
    });
    document.getElementById('auth-google').addEventListener('click', _authGoogle);
    document.getElementById('auth-xbtn').addEventListener('click', _authX);
    document.getElementById('auth-wechat').addEventListener('click', function () { _authShow('wechatSoon', 'ok'); });
    document.getElementById('auth-form').addEventListener('submit', function (e) { e.preventDefault(); _authEmailSubmit(); });
    // light focus trap (true modal)
    card.addEventListener('keydown', function (e) {
      if (e.key !== 'Tab') return;
      var f = card.querySelectorAll('button:not([disabled]),input:not([disabled])');
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
  }
  function openAuthModal(mode) {
    if (!_authEnabled) return;
    _buildAuthModal();
    _authMode = (mode === 'signup') ? 'signup' : 'signin';
    _authRelabel(); _authMsg('', null); _authBusy(false);
    var ov = document.getElementById('auth-overlay');
    _authLastFocus = document.activeElement;
    document.documentElement.classList.add('auth-lock');
    ov.classList.add('open');
    getSupabaseClient().catch(function () {});   // warm the SDK so the first action is instant
    setTimeout(function () { var em = document.getElementById('auth-email'); if (em) em.focus(); }, 90);
  }
  function closeAuthModal() {
    var ov = document.getElementById('auth-overlay'); if (!ov) return;
    ov.classList.remove('open');
    document.documentElement.classList.remove('auth-lock');
    // don't leave credentials sitting in the fields on a shared browser
    var em = document.getElementById('auth-email'); if (em) em.value = '';
    var pw = document.getElementById('auth-pw'); if (pw) { pw.value = ''; pw.type = 'password'; }
    _authMsg('', null);
    if (_authLastFocus && _authLastFocus.focus) _authLastFocus.focus();
  }
  window.openAuthModal = openAuthModal;

  // shared OAuth kickoff for the provider buttons (Google, X/Twitter). On success
  // the browser navigates to the provider's consent screen; we only land back in
  // .then() if the SDK returns an error before redirecting.
  function _authOAuth(provider, redirectKey) {
    _authBusy(true); _authShow(redirectKey, 'ok');
    getSupabaseClient().then(function (sb) {
      return sb.auth.signInWithOAuth({ provider: provider, options: { redirectTo: location.href.split('#')[0] } });
    }).then(function (res) {
      if (res && res.error) { _authBusy(false); _authShow(_authErrKey(res.error), 'err'); }
    }).catch(function () { _authBusy(false); _authShow('errSdk', 'err'); });
  }
  function _authGoogle() { _authOAuth('google', 'redirect'); }
  function _authX() { _authOAuth('twitter', 'redirectX'); }   // Supabase provider id for X is 'twitter'
  function _authEmailSubmit() {
    var emEl = document.getElementById('auth-email'), pwEl = document.getElementById('auth-pw');
    var email = (emEl && emEl.value || '').trim(), pw = (pwEl && pwEl.value) || '';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { _authShow('errEmail', 'err'); return; }
    if (pw.length < 6) { _authShow('errPw', 'err'); return; }
    _authBusy(true); _authMsg('', null);
    var su = _authMode === 'signup';
    getSupabaseClient().then(function (sb) {
      if (su) {
        return sb.auth.signUp({ email: email, password: pw }).then(function (res) {
          if (res.error) throw res.error;
          // With "Confirm email" OFF, signUp returns a session immediately.
          if (res.data && res.data.session) return res;
          // gotrue's anti-enumeration shape for an ALREADY-registered email (no
          // error, no session, a user with an EMPTY identities array) — surface
          // "already registered" instead of silently trying their password.
          var u = res.data && res.data.user;
          if (u && Array.isArray(u.identities) && u.identities.length === 0) {
            throw new Error('user already registered');
          }
          // genuinely new user but confirmation is still ON -> a password sign-in
          // surfaces the right "confirm your email" message.
          return sb.auth.signInWithPassword({ email: email, password: pw });
        });
      }
      return sb.auth.signInWithPassword({ email: email, password: pw });
    }).then(function (res) {
      if (res && res.error) throw res.error;
      _authBusy(false);
      if (su) { _authShow('okSignup', 'ok'); setTimeout(closeAuthModal, 750); }
      else { closeAuthModal(); }
    }).catch(function (err) { _authBusy(false); _authShow(_authErrKey(err), 'err'); });
  }
  function _authErrKey(err) {
    var m = ((err && (err.message || err.error_description)) || '').toLowerCase();
    if (m.indexOf('already registered') >= 0 || m.indexOf('already exists') >= 0 || m.indexOf('user already') >= 0) return 'errDupe';
    if (m.indexOf('not confirmed') >= 0 || m.indexOf('confirm') >= 0) return 'errConfirm';
    if (m.indexOf('invalid login') >= 0 || m.indexOf('invalid credentials') >= 0) return 'errCreds';
    if (m.indexOf('failed to fetch') >= 0 || m.indexOf('networkerror') >= 0 || m.indexOf('load failed') >= 0) return 'errSdk';
    return 'errGen';
  }

  // settings-popover account section: swap signed-out <-> signed-in views
  function _renderAcct() {
    var out = document.getElementById('set-acct-out'), inn = document.getElementById('set-acct-in');
    if (!out || !inn) return;
    if (_curUser) {
      var email = _curUser.email || (_curUser.user_metadata && _curUser.user_metadata.email) || '';
      out.style.display = 'none'; inn.style.display = 'flex';
      _setTxt('set-email', email || '—');
      var av = document.getElementById('set-avatar');
      if (av) av.textContent = (email ? email.charAt(0) : 'U').toUpperCase();
    } else {
      out.style.display = 'block'; inn.style.display = 'none';
    }
  }

  /* ===========================================================================
     SETTINGS DASHBOARD (sd-*) — the large modal that replaces the gear
     popover's cramped "page 2" account panel. Ported verbatim from
     mockups/settings_dashboard/settings_dash.html (sd-* CSS + markup are the
     spec). A left rail (Account · Preferences · Sync) drives three sections
     inside one glass card; the popover's own theme/lang/live controls stay
     untouched and both stay in sync via the shared themechange event.

     Built lazily on first MMSettings.open(); re-rendered on 'mdx-auth' and
     'langchange' while built. Account data maps straight off the Supabase user
     object (_curUser) — ZERO new network calls. All colours ride the house vars
     with vector-palette fallbacks (var(--panel,var(--card)) etc.); #9b5cff is
     the existing house avatar-gradient endpoint. One-shot laser sweep + section
     rise only (mobile-perf law), both gated by prefers-reduced-motion.
     =========================================================================*/
  var SDASH_CSS = [
    '.sd-overlay{position:fixed;inset:0;z-index:100001;display:flex;align-items:center;justify-content:center;padding:24px;background:color-mix(in srgb,#04060c 66%,transparent);-webkit-backdrop-filter:blur(9px) saturate(1.05);backdrop-filter:blur(9px) saturate(1.05);opacity:0;visibility:hidden;pointer-events:none;transition:opacity .22s ease,visibility 0s linear .22s;font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif}',
    '.sd-overlay.open{opacity:1;visibility:visible;pointer-events:auto;transition:opacity .22s ease,visibility 0s}',
    /* 100vh line first = fallback for browsers without dvh (old iOS Safari drops
       the whole min(...dvh...) declaration); the dvh line wins where supported */
    '.sd-card{position:relative;display:flex;width:min(1140px,94vw);height:min(772px,calc(100vh - 40px));height:min(772px,calc(100dvh - 40px));box-sizing:border-box;border-radius:22px;overflow:hidden;isolation:isolate;background:color-mix(in srgb,var(--panel,var(--card,#0e1320)) 82%,transparent);border:1px solid color-mix(in srgb,var(--text,var(--ink,#e7ecf6)) 14%,transparent);-webkit-backdrop-filter:blur(24px) saturate(1.6);backdrop-filter:blur(24px) saturate(1.6);box-shadow:0 32px 90px -20px rgba(3,7,18,.8),0 10px 28px -12px rgba(3,7,18,.5),inset 0 1px 0 color-mix(in srgb,#fff 8%,transparent);transform:translateY(14px) scale(.985);opacity:.4;transition:transform .3s cubic-bezier(.32,1.28,.5,1),opacity .22s ease;color:var(--text,var(--ink,#e7ecf6))}',
    '.sd-overlay.open .sd-card{transform:none;opacity:1}',
    'html[data-theme="light"] .sd-card{box-shadow:0 30px 80px -22px rgba(20,30,50,.35),0 10px 26px -14px rgba(20,30,50,.22),inset 0 1px 0 rgba(255,255,255,.75)}',
    '@supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){.sd-card{background:var(--panel,var(--card,#0e1320))}}',
    /* laser hairline — brand-bar idiom; sweeps ONCE on open, then rests */
    '.sd-laser{position:absolute;top:0;left:0;right:0;height:2px;z-index:3;pointer-events:none;background:linear-gradient(90deg,transparent 0%,var(--link,var(--blue,#4f8cff)) 30%,#9b5cff 62%,transparent 100%);background-size:220% 100%;background-position:120% 0}',
    '.sd-overlay.open .sd-laser{animation:sdLaser .9s cubic-bezier(.4,.1,.2,1) .12s forwards}',
    '@keyframes sdLaser{from{background-position:120% 0}to{background-position:0% 0}}',
    '@media (prefers-reduced-motion:reduce){.sd-overlay,.sd-card{transition:opacity .15s ease}.sd-card{transform:none}.sd-overlay.open .sd-laser{animation:none;background-position:0% 0}}',
    /* left rail */
    '.sd-rail{flex:none;width:238px;box-sizing:border-box;display:flex;flex-direction:column;gap:4px;padding:20px 14px 16px;border-right:1px solid color-mix(in srgb,var(--line,var(--grid,#283042)) 70%,transparent);background:color-mix(in srgb,var(--panel2,var(--card,#141a28)) 44%,transparent)}',
    '.sd-me{display:flex;align-items:center;gap:9px;padding:4px 4px 12px}',
    '.sd-me-av{flex:none;width:32px;height:32px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--link,var(--blue,#4f8cff)),color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 55%,#9b5cff))}',
    '.sd-me-av.guestav{background:color-mix(in srgb,var(--muted,var(--ink-3,#8b93a7)) 30%,var(--panel2,var(--card)));color:var(--muted,var(--ink-3,#8b93a7))}',
    '.sd-me-main{flex:1;min-width:0}',
    '.sd-me-name{display:block;font-size:12.5px;font-weight:750;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sd-me-sub{display:block;font-size:10.5px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sd-nav{display:flex;flex-direction:column;gap:3px}',
    '.sd-nav-b{position:relative;display:flex;align-items:center;gap:9px;width:100%;box-sizing:border-box;padding:8px 10px;border:0;border-radius:9px;background:transparent;color:var(--muted,var(--ink-3,#8b93a7));font:650 12.5px/1.3 inherit;font-family:inherit;cursor:pointer;text-align:left;transition:background .16s,color .16s;-webkit-tap-highlight-color:transparent}',
    '.sd-nav-b svg{width:16px;height:16px;flex:none;stroke-width:1.8}',
    '.sd-nav-b:hover{background:color-mix(in srgb,var(--text,var(--ink,#fff)) 7%,transparent);color:var(--text,var(--ink))}',
    '.sd-nav-b.active{background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 13%,transparent);color:var(--link,var(--blue,#4f8cff))}',
    '.sd-nav-b.active::before{content:"";position:absolute;left:0;top:7px;bottom:7px;width:2px;border-radius:2px;background:linear-gradient(180deg,var(--link,var(--blue,#4f8cff)),#9b5cff)}',
    '.sd-nav-b:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    '.sd-rail-spacer{flex:1}',
    '.sd-signout{display:flex;align-items:center;gap:9px;width:100%;box-sizing:border-box;padding:8px 10px;border:0;border-radius:9px;background:transparent;color:var(--muted,var(--ink-3,#8b93a7));font:650 12.5px/1.3 inherit;font-family:inherit;cursor:pointer;text-align:left;transition:background .16s,color .16s}',
    '.sd-signout svg{width:16px;height:16px;flex:none}',
    '.sd-signout:hover{background:color-mix(in srgb,var(--down,#ff5c6c) 10%,transparent);color:var(--down,#ff5c6c)}',
    '.sd-signout:focus-visible{outline:2px solid var(--down,#ff5c6c);outline-offset:2px}',
    /* right pane */
    '.sd-pane{flex:1;min-width:0;display:flex;flex-direction:column}',
    '.sd-head{flex:none;display:flex;align-items:flex-start;gap:10px;padding:24px 26px 14px 30px}',
    '.sd-head-main{flex:1;min-width:0}',
    '.sd-head h2{margin:0;font-size:19px;font-weight:800;letter-spacing:-.01em;line-height:1.15;color:var(--text,var(--ink))}',
    '.sd-head .sd-sub{margin:4px 0 0;font-size:12.5px;line-height:1.45;color:var(--muted,var(--ink-3,#8b93a7))}',
    '.sd-x{flex:none;width:28px;height:28px;border-radius:9px;border:1px solid transparent;background:transparent;color:var(--muted,var(--ink-3,#8b93a7));cursor:pointer;display:inline-flex;align-items:center;justify-content:center;transition:background .16s,color .16s}',
    '.sd-x:hover{background:color-mix(in srgb,var(--text,var(--ink,#fff)) 8%,transparent);color:var(--text,var(--ink))}',
    '.sd-x svg{width:15px;height:15px}',
    '.sd-x:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    '.sd-body{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:4px 26px 26px 30px}',
    /* two-column content grid — fills the enlarged card on wide panes, collapses to one column when the card narrows */
    '.sd-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 22px;align-items:start}',
    '.sd-grid > .sd-group{margin-bottom:6px}',
    '.sd-span2{grid-column:1 / -1}',
    /* section switch: one-shot rise on entry */
    '.sd-sect{display:none}',
    /* flex column so the head stays fixed and ONLY .sd-body scrolls — a block here
       lets tall sections overflow the pane, which makes the overflow:hidden card
       silently scrollable and a focus() on open decapitates the header */
    '.sd-sect.on{display:flex;flex-direction:column;flex:1;min-height:0;animation:sdRise .18s ease}',
    '@keyframes sdRise{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}',
    '@media (prefers-reduced-motion:reduce){.sd-sect.on{animation:none}}',
    /* the aurora ID card (signature) */
    '.sd-id{position:relative;display:flex;align-items:center;gap:14px;padding:16px;margin:4px 0 14px;border-radius:14px;border:1px solid color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 22%,var(--line,var(--grid,#283042)));overflow:hidden;background:radial-gradient(120% 180% at 8% 0%,color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 13%,transparent) 0%,transparent 55%),radial-gradient(90% 160% at 55% -20%,color-mix(in srgb,#9b5cff 9%,transparent) 0%,transparent 60%),color-mix(in srgb,var(--panel2,var(--card,#141a28)) 72%,transparent)}',
    '.sd-id-av{position:relative;flex:none;width:54px;height:54px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:21px;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--link,var(--blue,#4f8cff)),color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 55%,#9b5cff))}',
    '.sd-id-av::after{content:"";position:absolute;inset:-4px;border-radius:50%;padding:2px;background:conic-gradient(from 210deg,var(--link,var(--blue,#4f8cff)),#9b5cff 40%,transparent 75%,var(--link,var(--blue,#4f8cff)));-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;opacity:.85}',
    '.sd-id-main{flex:1;min-width:0}',
    '.sd-id-name{display:block;font-size:17px;font-weight:800;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sd-id-mail{display:block;font-size:12.5px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sd-id-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}',
    '.sd-chip{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:700;color:var(--muted,var(--ink-3,#8b93a7));background:color-mix(in srgb,var(--panel,var(--card)) 65%,transparent);border:1px solid var(--line,var(--grid,#283042));border-radius:999px;padding:3px 9px}',
    '.sd-chip svg{width:11px;height:11px}',
    '.sd-chip .dot{width:6px;height:6px;border-radius:50%;background:var(--up,#23c08a)}',
    /* groups & rows */
    '.sd-group{margin:0 0 14px}',
    '.sd-group-t{display:block;font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--muted,var(--ink-3,#8b93a7));margin:0 2px 7px}',
    '.sd-row{box-sizing:border-box;background:color-mix(in srgb,var(--panel2,var(--card,#141a28)) 78%,transparent);border:1px solid var(--line,var(--grid,#283042));border-radius:11px;padding:11px 13px}',
    '.sd-row + .sd-row{margin-top:7px}',
    '.sd-row-line{display:flex;align-items:center;gap:11px;min-height:24px}',
    '.sd-row-main{flex:1;min-width:0}',
    '.sd-row-lbl{display:block;font-size:12.5px;font-weight:700;color:var(--text,var(--ink))}',
    '.sd-mailv{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sd-row-desc{display:block;font-size:11px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:2px;line-height:1.4}',
    '.sd-row-val{flex:none;max-width:45%;font-size:13px;color:var(--muted,var(--ink-3,#8b93a7));overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sd-row-val.strong{color:var(--text,var(--ink))}',
    '.sd-edit{flex:none;font-size:11.5px;font-weight:700;color:var(--link,var(--blue,#4f8cff));background:transparent;border:1px solid var(--line,var(--grid,#283042));border-radius:8px;padding:5px 11px;cursor:pointer;font-family:inherit;transition:border-color .15s,background .15s}',
    '.sd-edit:hover{border-color:var(--link,var(--blue,#4f8cff));background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 10%,transparent)}',
    '.sd-edit:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    /* inline edit expansion inside a row */
    '.sd-form{display:none;margin-top:10px}',
    '.sd-row.editing .sd-form{display:block}',
    '.sd-row.editing .sd-edit{display:none}',
    '.sd-in{width:100%;box-sizing:border-box;padding:9px 11px;border-radius:9px;border:1px solid var(--line,var(--grid,#283042));background:var(--bg,var(--card,#0b0f1a));color:var(--text,var(--ink));font-size:13.5px;font-family:inherit;outline:none;display:block;transition:border-color .15s,box-shadow .15s}',
    '.sd-in + .sd-in{margin-top:7px}',
    '.sd-in:focus{border-color:var(--link,var(--blue,#4f8cff));box-shadow:0 0 0 3px color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 20%,transparent)}',
    '.sd-note{font-size:11px;color:var(--muted,var(--ink-3,#8b93a7));line-height:1.45;margin:6px 0 0}',
    '.sd-msg{font-size:11.5px;line-height:1.4;margin-top:6px;display:none}',
    '.sd-msg.show{display:block}',
    '.sd-msg.ok{color:var(--up,#23c08a)}',
    '.sd-msg.err{color:var(--down,#ff5c6c)}',
    '.sd-btns{display:flex;gap:7px;margin-top:9px;justify-content:flex-end}',
    '.sd-btn{font-size:12.5px;font-weight:700;padding:8px 14px;border-radius:9px;cursor:pointer;border:1px solid var(--line,var(--grid,#283042));font-family:inherit;transition:all .15s}',
    '.sd-btn:disabled{opacity:.55;cursor:default}',
    '.sd-btn.primary{background:var(--link,var(--blue,#4f8cff));border-color:var(--link,var(--blue,#4f8cff));color:#fff}',
    '.sd-btn.primary:hover:not(:disabled){filter:brightness(1.07);transform:translateY(-1px)}',
    '.sd-btn.ghost{background:transparent;color:var(--text,var(--ink))}',
    '.sd-btn.ghost:hover:not(:disabled){border-color:var(--link,var(--blue,#4f8cff))}',
    '.sd-btn:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    /* small utility: copy button + provider chip in value slot */
    '.sd-mini{flex:none;font-size:10.5px;font-weight:700;color:var(--muted,var(--ink-3,#8b93a7));background:transparent;border:1px solid var(--line,var(--grid,#283042));border-radius:7px;padding:3px 9px;cursor:pointer;font-family:inherit;transition:border-color .15s,color .15s}',
    '.sd-mini:hover{border-color:var(--link,var(--blue,#4f8cff));color:var(--link,var(--blue,#4f8cff))}',
    '.sd-mini:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    '.sd-provider{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;font-weight:700;color:var(--text,var(--ink));background:color-mix(in srgb,var(--panel,var(--card)) 65%,transparent);border:1px solid var(--line,var(--grid,#283042));border-radius:999px;padding:4px 11px}',
    '.sd-provider svg{width:12px;height:12px}',
    /* controls (ported idioms: 3-way segment / pill toggle) */
    '.sd-seg{display:inline-flex;background:var(--bg,var(--card));border:1px solid var(--line,var(--grid,#283042));border-radius:999px;padding:3px;gap:2px;flex:none}',
    '.sd-seg-b{padding:4px 12px;border:none;border-radius:999px;font-size:11.5px;font-weight:650;cursor:pointer;font-family:inherit;background:transparent;color:var(--muted,var(--ink-3,#8b93a7));transition:background .2s,color .2s;white-space:nowrap}',
    '.sd-seg-b.active{background:var(--link,var(--blue,#4f8cff));color:#fff}',
    '.sd-seg-b:hover:not(.active){background:color-mix(in srgb,var(--text,var(--ink,#fff)) 9%,transparent);color:var(--text,var(--ink))}',
    '.sd-seg-b:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    /* multi-select preference chips (markets · what you trade). The check slot is
       ALWAYS in the layout so selecting one never reflows the row. */
    '.sd-pchips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}',
    '.sd-pchip{display:inline-flex;align-items:center;gap:7px;padding:7px 11px;border-radius:9px;border:1px solid var(--line,var(--grid,#283042));background:var(--bg,var(--card));color:var(--muted,var(--ink-3,#8b93a7));font:650 12px/1.2 inherit;font-family:inherit;cursor:pointer;transition:border-color .15s,background .15s,color .15s}',
    '.sd-pchip:hover{border-color:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 55%,var(--line,var(--grid,#283042)))}',
    '.sd-pchip[aria-pressed="true"]{border-color:var(--link,var(--blue,#4f8cff));background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 13%,transparent);color:var(--text,var(--ink))}',
    '.sd-pchip:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    '.sd-pchip .box{position:relative;flex:none;width:14px;height:14px;border-radius:50%;border:1.5px solid var(--line,var(--grid,#283042));display:grid;place-items:center;transition:border-color .15s,background .15s}',
    '.sd-pchip[aria-pressed="true"] .box{border-color:var(--link,var(--blue,#4f8cff));background:var(--link,var(--blue,#4f8cff))}',
    '.sd-pchip .box svg{width:8px;height:8px;stroke:#fff;stroke-width:3.4;fill:none;opacity:0;transform:scale(.5);transition:opacity .14s,transform .16s cubic-bezier(.3,1.4,.5,1)}',
    '.sd-pchip[aria-pressed="true"] .box svg{opacity:1;transform:none}',
    '.sd-toggle{position:relative;width:44px;height:24px;border-radius:999px;border:1px solid var(--line,var(--grid,#283042));background:var(--bg,var(--card));cursor:pointer;padding:0;flex:none;transition:background .25s,border-color .25s}',
    '.sd-toggle[aria-checked="true"]{background:var(--link,var(--blue,#4f8cff));border-color:var(--link,var(--blue,#4f8cff))}',
    '.sd-toggle .knob{position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.25);transition:transform .25s cubic-bezier(.34,1.4,.5,1)}',
    '.sd-toggle[aria-checked="true"] .knob{transform:translateX(20px)}',
    '.sd-toggle:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    /* sync status card */
    '.sd-sync{display:flex;align-items:center;gap:11px;padding:13px 14px;margin:4px 0 14px;border-radius:12px;border:1px solid color-mix(in srgb,var(--up,#23c08a) 26%,var(--line,var(--grid,#283042)));background:color-mix(in srgb,var(--up,#23c08a) 7%,transparent)}',
    '.sd-sync .dot{flex:none;width:9px;height:9px;border-radius:50%;background:var(--up,#23c08a);box-shadow:0 0 0 4px color-mix(in srgb,var(--up,#23c08a) 18%,transparent)}',
    '.sd-sync.off{border-color:var(--line,var(--grid,#283042));background:color-mix(in srgb,var(--panel2,var(--card,#141a28)) 78%,transparent)}',
    '.sd-sync.off .dot{background:var(--muted,var(--ink-3,#8b93a7));box-shadow:0 0 0 4px color-mix(in srgb,var(--muted,var(--ink-3,#8b93a7)) 14%,transparent)}',
    '.sd-sync-main{flex:1;min-width:0}',
    '.sd-sync-t{display:block;font-size:12.5px;font-weight:750;color:var(--text,var(--ink))}',
    '.sd-sync-s{display:block;font-size:11px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sd-link{flex:none;display:inline-flex;align-items:center;gap:4px;font-size:11.5px;font-weight:700;color:var(--link,var(--blue,#4f8cff));text-decoration:none;border:1px solid var(--line,var(--grid,#283042));border-radius:8px;padding:5px 11px;transition:border-color .15s,background .15s}',
    '.sd-link:hover{border-color:var(--link,var(--blue,#4f8cff));background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 10%,transparent)}',
    '.sd-link:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    /* signed-out / guest CTA card */
    '.sd-cta{text-align:center;padding:26px 18px;border-radius:14px;border:1px dashed color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 30%,var(--line,var(--grid,#283042)));background:radial-gradient(120% 160% at 50% -30%,color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 10%,transparent) 0%,transparent 60%),color-mix(in srgb,var(--panel2,var(--card,#141a28)) 55%,transparent);margin-top:4px}',
    '.sd-cta-av{width:46px;height:46px;border-radius:50%;margin:0 auto 10px;display:flex;align-items:center;justify-content:center;color:var(--link,var(--blue,#4f8cff));background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 14%,transparent)}',
    '.sd-cta-av svg{width:22px;height:22px}',
    '.sd-cta-t{font-size:15px;font-weight:800;margin:0 0 6px;color:var(--text,var(--ink))}',
    '.sd-cta-n{font-size:12px;color:var(--muted,var(--ink-3,#8b93a7));line-height:1.55;margin:0 auto 14px;max-width:300px}',
    '.sd-cta-btns{display:flex;gap:8px;justify-content:center}',
    '.sd-cta-btns .sd-btn{min-width:120px}',
    /* plan block — tier row + status chip + prorated-upgrade CTA */
    '.sd-plan-tier{font-weight:800}',
    '.sd-plan-chip{display:inline-flex;align-items:center;flex:none;margin-left:8px;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;line-height:1.5;white-space:nowrap;border:1px solid transparent}',
    '.sd-plan-chip.live{color:var(--link,var(--blue,#4f8cff));background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 12%,transparent);border-color:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 30%,transparent)}',
    '.sd-plan-chip.trial{color:var(--link,var(--blue,#4f8cff));background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 9%,transparent);border-color:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 22%,transparent)}',
    '.sd-plan-chip.warn{color:var(--warn,#e0a53d);background:color-mix(in srgb,var(--warn,#e0a53d) 12%,transparent);border-color:color-mix(in srgb,var(--warn,#e0a53d) 30%,transparent)}',
    '.sd-plan-cta{margin-top:10px}',
    '.sd-plan-cta .sd-btn{width:100%}',
    /* bilingual toggle SCOPED to the dashboard: _sdBl() emits .l-en/.l-zh spans, but
       the landing (index.html) has no site-wide .l-en/.l-zh rule, so both languages
       showed. Scoping to .sd-card keeps the dashboard single-language on every host
       without touching the page around it. */
    '.sd-card .l-zh{display:none}',
    'html[data-lang="zh"] .sd-card .l-en{display:none}',
    'html[data-lang="zh"] .sd-card .l-zh{display:inline}',
    '.sd-muted{color:var(--muted,var(--ink-3,#8b93a7))}',
    /* ---- Billing: plan hero (tier-gradient signature card) ---- */
    '.sd-plan-hero{position:relative;overflow:hidden;border-radius:16px;padding:18px 18px 16px;margin:4px 0 14px;border:1px solid color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 26%,var(--line,var(--grid,#283042)));background:radial-gradient(130% 190% at 6% 0%,color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 16%,transparent) 0%,transparent 55%),radial-gradient(95% 150% at 72% -12%,color-mix(in srgb,#9b5cff 13%,transparent) 0%,transparent 60%),color-mix(in srgb,var(--panel2,var(--card,#141a28)) 74%,transparent)}',
    '.sd-plan-hero.free{border-color:var(--line,var(--grid,#283042));background:color-mix(in srgb,var(--panel2,var(--card,#141a28)) 74%,transparent)}',
    '.sd-ph-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}',
    '.sd-ph-eyebrow{font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.09em;color:var(--muted,var(--ink-3,#8b93a7))}',
    '.sd-ph-name{display:flex;align-items:baseline;gap:9px;margin-top:6px;font-size:25px;font-weight:800;letter-spacing:-.02em;line-height:1.05;color:var(--text,var(--ink))}',
    '.sd-ph-int{font-size:12.5px;font-weight:700;color:var(--muted,var(--ink-3,#8b93a7))}',
    '.sd-ph-price{font-size:13px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:9px}',
    '.sd-ph-price b{color:var(--text,var(--ink));font-weight:800;font-variant-numeric:tabular-nums}',
    '.sd-ph-meta{font-size:12px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:3px}',
    '.sd-incl-row{display:flex;align-items:flex-start;gap:10px;padding:6px 3px;font-size:12.5px;line-height:1.35;color:var(--text,var(--ink))}',
    '.sd-incl-row svg{flex:none;width:15px;height:15px;margin-top:1px;color:var(--up,#23c08a)}',
    /* ---- Usage: capacity meters (draw-on-reveal instrument) ---- */
    '.sd-meter{position:relative;border-radius:14px;border:1px solid var(--line,var(--grid,#283042));background:color-mix(in srgb,var(--panel2,var(--card,#141a28)) 78%,transparent);padding:15px 16px}',
    '.sd-meter-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px}',
    '.sd-meter-lbl{font-size:13px;font-weight:750;color:var(--text,var(--ink))}',
    '.sd-meter-cap{font-size:10.5px;font-weight:700;color:var(--muted,var(--ink-3,#8b93a7));text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}',
    '.sd-meter-big{display:flex;align-items:baseline;gap:7px;margin:9px 0 11px}',
    '.sd-meter-num{font-size:32px;font-weight:800;letter-spacing:-.025em;line-height:.95;color:var(--text,var(--ink));font-variant-numeric:tabular-nums}',
    '.sd-meter-of{font-size:12px;color:var(--muted,var(--ink-3,#8b93a7))}',
    '.sd-meter-bar{position:relative;height:8px;border-radius:99px;background:color-mix(in srgb,var(--text,var(--ink,#fff)) 9%,transparent);overflow:hidden}',
    '.sd-meter-fill{position:absolute;top:0;bottom:0;left:0;border-radius:99px;background:linear-gradient(90deg,var(--link,var(--blue,#4f8cff)),#9b5cff);width:0;transition:width .95s cubic-bezier(.3,.75,.2,1)}',
    '.sd-meter.low .sd-meter-fill{background:linear-gradient(90deg,var(--warn,#e0a53d),#e0764a)}',
    '.sd-meter.low .sd-meter-num{color:var(--warn,#e0a53d)}',
    '.sd-meter.out .sd-meter-fill{background:linear-gradient(90deg,var(--down,#ff5c6c),#e0764a)}',
    '.sd-meter.out .sd-meter-num{color:var(--down,#ff5c6c)}',
    '.sd-meter.unl .sd-meter-num{color:var(--link,var(--blue,#4f8cff));font-size:26px}',
    '.sd-meter-foot{font-size:11px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:10px;line-height:1.4}',
    '@media (prefers-reduced-motion:reduce){.sd-meter-fill{transition:none}}',
    /* ---- Upgrade nudge (shown when a lane runs low / a tier can climb) ---- */
    '.sd-nudge{display:flex;align-items:center;gap:12px;border-radius:12px;padding:12px 14px;margin-top:12px;border:1px solid color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 28%,var(--line,var(--grid,#283042)));background:color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 8%,transparent)}',
    '.sd-nudge-main{flex:1;min-width:0}',
    '.sd-nudge-t{font-size:12.5px;font-weight:750;color:var(--text,var(--ink))}',
    '.sd-nudge-s{font-size:11px;color:var(--muted,var(--ink-3,#8b93a7));margin-top:1px;line-height:1.4}',
    '.sd-nudge .sd-btn{flex:none;white-space:nowrap}',
    /* usage skeleton + collapse the 2-col grid when the card narrows */
    '.sd-skel{height:96px;border-radius:14px;border:1px solid var(--line,var(--grid,#283042));background:linear-gradient(100deg,color-mix(in srgb,var(--panel2,var(--card,#141a28)) 78%,transparent) 30%,color-mix(in srgb,var(--text,var(--ink,#fff)) 6%,transparent) 50%,color-mix(in srgb,var(--panel2,var(--card,#141a28)) 78%,transparent) 70%);background-size:220% 100%;animation:sdShimmer 1.3s linear infinite}',
    '@keyframes sdShimmer{from{background-position:180% 0}to{background-position:-40% 0}}',
    '@media (max-width:1000px){.sd-grid{grid-template-columns:1fr}}',
    /* mobile sign-out (rail hidden -> row at the end of Account) */
    '.sd-signout-m{display:none}',
    /* desktop: hide the mobile close slot */
    '.sd-x-m{display:none}',
    /* MOBILE <=640px — full sheet, rail -> header + horizontal tabs */
    '@media (max-width:640px){',
    '.sd-overlay{padding:0;align-items:stretch}',
    '.sd-card{flex-direction:column;width:100%;height:100vh;height:100dvh;border-radius:0;border-left:0;border-right:0;transform:translateY(24px)}',
    '.sd-overlay.open .sd-card{transform:none}',
    '.sd-rail{width:auto;flex-direction:row;flex-wrap:wrap;align-items:center;gap:2px 8px;padding:12px 14px 8px;border-right:0;border-bottom:1px solid color-mix(in srgb,var(--line,var(--grid,#283042)) 70%,transparent)}',
    '.sd-me{flex:1;min-width:0;padding:0;order:1}',
    '.sd-x-m{order:2}',
    '.sd-nav{order:3;flex-direction:row;width:100%;overflow-x:auto;scrollbar-width:none;gap:4px;padding:8px 0 2px}',
    '.sd-nav::-webkit-scrollbar{display:none}',
    '.sd-nav-b{width:auto;flex:none;padding:6px 12px;border-radius:999px}',
    '.sd-nav-b.active::before{display:none}',
    '.sd-rail-spacer,.sd-signout{display:none}',
    '.sd-signout-m{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;box-sizing:border-box;margin-top:14px;padding:11px;border-radius:11px;border:1px solid color-mix(in srgb,var(--down,#ff5c6c) 40%,var(--line,var(--grid,#283042)));background:transparent;color:var(--down,#ff5c6c);font:700 13px/1 inherit;font-family:inherit;cursor:pointer}',
    '.sd-signout-m:hover{background:color-mix(in srgb,var(--down,#ff5c6c) 10%,transparent)}',
    '.sd-signout-m svg{width:15px;height:15px;flex:none}',
    '.sd-head{padding:14px 14px 10px 16px}',
    '.sd-head .sd-x{display:none}',
    '.sd-body{padding:2px 14px 20px 16px}',
    '.sd-row-val{max-width:38%}',
    '.sd-x-m{display:inline-flex;flex:none;width:30px;height:30px;border-radius:9px;border:1px solid transparent;background:transparent;color:var(--muted,var(--ink-3,#8b93a7));cursor:pointer;align-items:center;justify-content:center}',
    '.sd-x-m:hover{background:color-mix(in srgb,var(--text,var(--ink,#fff)) 8%,transparent);color:var(--text,var(--ink))}',
    '.sd-x-m svg{width:16px;height:16px}',
    '.sd-x-m:focus-visible{outline:2px solid var(--link,var(--blue,#4f8cff));outline-offset:2px}',
    '}'
  ].join('');

  /* ---- settings-dashboard labels (EN/ZH pairs; ZH copy is the mockup's final) */
  var SD_L = {
    // section heads
    acctTitle:  ['Account', '账户'],
    acctSub:    ['One identity across the dashboard and the Terminal.', '一个账户，通用于仪表盘与终端。'],
    prefsTitle: ['Preferences', '偏好'],
    prefsSub:   ['Which markets you follow, and how the dashboard looks.', '你关注哪些市场，以及仪表盘的外观。'],
    syncTitle:  ['Sync', '同步'],
    syncSub:    ['What follows your account across devices.', '跟随账户同步到各设备的内容。'],
    // rail me-card
    railSub:    ['Synced across devices', '已在各设备同步'],
    notSignedIn:['Not signed in', '未登录'],
    localOnly:  ['Local settings only', '仅保存在本设备'],
    accessSess: ['Access session', '访问会话'],
    signOut:    ['Sign out', '退出登录'],
    close:      ['Close', '关闭'],
    // ID card + chips
    memberSince:['Member since', '注册于'],
    provGoogle: ['Google', 'Google'],
    provX:      ['X', 'X'],
    provEmail:  ['Email', '邮箱'],
    // profile group
    profile:    ['Profile', '个人资料'],
    dispName:   ['Display name', '显示名称'],
    dispNamePh: ['Your name', '你的名字'],
    email:      ['Email', '邮箱'],
    emailPh:    ['new@email.com', 'new@email.com'],
    emailNote:  ['A confirmation link will be sent to both addresses.', '两个邮箱地址都会收到确认链接。'],
    sendConfirm:['Send confirmation', '发送确认'],
    emailSent:  ['Confirmation sent to both addresses.', '确认链接已发送至两个邮箱。'],
    password:   ['Password', '密码'],
    newPwPh:    ['At least 8 characters', '至少 8 个字符'],
    confirmPwPh:['Repeat new password', '再次输入新密码'],
    updatePw:   ['Update password', '更新密码'],
    pwOk:       ['Password updated.', '密码已更新。'],
    pwMismatch: ['Passwords don’t match.', '两次密码不一致。'],
    pwShort:    ['Use at least 8 characters.', '至少 8 个字符。'],
    edit:       ['Edit', '编辑'],
    cancel:     ['Cancel', '取消'],
    save:       ['Save', '保存'],
    saving:     ['Saving…', '保存中…'],
    // security group
    security:   ['Security', '安全'],
    loginMethod:['Login method', '登录方式'],
    lastSignin: ['Last sign-in', '上次登录'],
    userId:     ['User ID', '用户 ID'],
    userIdNote: ['Quote it if you ever contact support.', '联系支持时请提供此 ID。'],
    copy:       ['Copy', '复制'],
    copied:     ['Copied', '已复制'],
    // plan block
    plan:        ['Plan', '订阅'],
    planLoading: ['Loading your plan…', '正在加载订阅…'],
    tierFree:    ['Free', '免费版'],
    tierInsider: ['Insider', 'Insider'],
    tierPro:     ['Pro', 'Pro'],
    planTrialUntil: ['Trial until', '试用至'],
    planRenews:  ['Renews', '续订于'],
    planExpires: ['Expires', '到期于'],
    planExpired: ['Expired', '已过期'],
    planLifetime:['Lifetime', '永久'],
    upgradePro:  ['Upgrade to Pro', '升级到 Pro'],
    switchAnnual:['Switch to annual — save 30%', '切换年付 — 立省 30%'],
    upgradeAnnual:['Upgrade — save up to 30%', '升级 — 最高省 30%'],
    choosePlan:  ['Choose a plan', '选择套餐'],
    planErr:     ['Couldn’t update your plan — please try again.', '无法更新订阅，请重试。'],
    // signed-out CTA
    ctaTitle:   ['Sign in to Mastermind', '登录 Mastermind'],
    ctaNote:    ['Sync your watchlists, alerts and settings across devices — free.', '免费同步自选、提醒与设置到你的所有设备。'],
    signin:     ['Sign in', '登录'],
    createAcct: ['Create account', '注册'],
    // guest CTA
    guestNote:  ['You’re in with the site access password. Create a free account to manage email, password & sync preferences.', '你正通过站点访问密码登录。注册免费账户以管理邮箱、密码并同步偏好。'],
    createFree: ['Create free account', '注册免费账户'],
    // preferences
    appearance: ['Appearance', '外观'],
    appearNote: ['Auto follows your local time of day.', '「自动」跟随本地时间切换。'],
    themeLight: ['Light', '浅色'],
    themeAuto:  ['Auto', '自动'],
    themeDark:  ['Dark', '深色'],
    language:   ['Language', '语言'],
    langNote:   ['Applies to every page.', '应用于所有页面。'],
    // desk preferences — the answers given at signup, editable ever after
    deskGroup:  ['Your desk', '你的台席'],
    markets:    ['Markets you follow', '你关注的市场'],
    marketsNote:['The markets you actually watch. Carried with your account.', '你真正关注的市场，随账户同步。'],
    mktUs:      ['United States', '美国'],
    mktCn:      ['China', '中国'],
    mktHk:      ['Hong Kong', '香港'],
    mktCa:      ['Canada', '加拿大'],
    mktGlobal:  ['Global', '全球'],
    trades:     ['What you trade', '你交易什么'],
    tradesNote: ['Stocks, options, crypto — pick any.', '股票、期权、加密货币——可多选。'],
    trStocks:   ['Stocks', '股票'],
    trOptions:  ['Options', '期权'],
    trCrypto:   ['Crypto', '加密货币'],
    prefSaved:  ['Saved', '已保存'],
    prefLocal:  ['Saved on this device — sign in to sync.', '已保存在本设备——登录后同步。'],
    prefErr:    ['Couldn’t save — please try again.', '保存失败，请重试。'],
    // sync section
    syncOn:     ['Sync is on', '同步已开启'],
    syncOff:    ['Sync is off', '同步未开启'],
    signedInAs: ['Signed in as', '已登录：'],
    sections:   ['Settings sections', '设置分区'],
    signInToOn: ['Sign in to turn it on.', '登录后即可开启。'],
    themeLang:  ['Theme & language', '主题与语言'],
    themeLangN: ['Saved automatically as you change them.', '更改后自动保存。'],
    watchlists: ['Watchlists & portfolio', '自选与组合'],
    watchNote:  ['Live wherever you sign in.', '登录任意设备即可使用。'],
    openWatch:  ['Open watchlist', '打开自选'],
    errGen:     ['Something went wrong — please try again.', '出错了，请重试。'],
    validEmail: ['Enter a valid email address.', '请输入有效的邮箱地址。'],
    // billing section
    billingTitle:['Billing', '账单'],
    billingSub:  ['Your plan, payment and invoices.', '你的方案、付款与发票。'],
    currentPlan: ['Current plan', '当前方案'],
    billedAnnual:['billed annually', '按年结算'],
    billedMonthly:['billed monthly', '按月结算'],
    perMo:       ['/mo', '/月'],
    freePlanName:['Free', '免费版'],
    freePitch:   ['The US macro read, the Terminal and 3 signals per daily list. Visitors can preview 1 before signup.', '美国宏观研判、Terminal 与每个每日列表 3 条信号。访客注册前可预览 1 条。'],
    manageBilling:['Payment & invoices', '付款与发票'],
    manageBillingNote:['Update your card, download invoices, or cancel.', '更新银行卡、下载发票或取消订阅。'],
    openPortal:  ['Open', '打开'],
    portalErr:   ['Couldn’t open billing — please try again.', '无法打开账单页，请重试。'],
    // A comp / lifetime grant has no Stripe customer, so there is no portal to open. Say
    // that plainly instead of offering a button that 404s and then blaming the network:
    // "please try again" is a lie when retrying can never work.
    grantedPlan: ['Granted access', '已授予的权限'],
    grantedNote: ['This plan was granted directly — there’s no subscription or card to manage.', '此方案为直接授予——没有需要管理的订阅或银行卡。'],
    portalNone:  ['This account has no Stripe billing — nothing to open.', '此账号没有 Stripe 账单——无可打开。'],
    opening:     ['Opening…', '正在打开…'],
    onFreePlan:  ['You’re on the free plan.', '你正在使用免费版。'],
    planIncludes:['Your plan includes', '你的方案包含'],
    // usage section
    usageTitle:  ['Usage', '用量'],
    usageSub:    ['What you’ve used this cycle, and what’s left.', '本周期已用与剩余额度。'],
    chatLane:    ['Mastermind chat', 'Mastermind 对话'],
    chatLaneNote:['Questions to the market analyst.', '向市场分析师提问。'],
    deepLane:    ['Deep research', '深度研究'],
    deepLaneNote:['Longer, higher-effort answers.', '更长、更深入的回答。'],
    usageLeft:   ['left', '剩余'],
    usageOfMonth:['of __N__ this month', '本月共 __N__ 次'],
    usageOfWeek: ['of __N__ this week', '本周共 __N__ 次'],
    usageOfTrial:['of __N__ during your trial', '试用期内共 __N__ 次'],
    resetsOn:    ['Resets __D__', '__D__ 重置'],
    resetsMonthly:['Resets at the start of each month.', '每月月初重置。'],
    resetsWeekly:['Resets every Monday.', '每周一重置。'],
    unlimited:   ['Unlimited', '无限'],
    unlimitedNote:['No monthly cap on your plan.', '你的方案没有每月上限。'],
    deepLockedFree:['Included with Insider and Pro.', 'Insider 与 Pro 方案包含。'],
    usageErr:    ['Couldn’t load usage — please try again.', '无法加载用量，请重试。'],
    capMonth:    ['This month', '本月'],
    capWeek:     ['This week', '本周'],
    capTrial:    ['Trial', '试用期'],
    ofN:         ['of __N__', '共 __N__ 次'],
    // upgrade nudges
    nudgeLowT:   ['Running low', '额度不多了'],
    nudgeLowS:   ['Upgrade for more questions every month.', '升级即可每月获得更多提问额度。'],
    nudgeGetT:   ['Want deeper answers?', '想要更深入的回答？'],
    nudgeGetS:   ['Insider and Pro add deep research questions.', 'Insider 与 Pro 提供深度研究提问。'],
    upgrade:     ['Upgrade', '升级']
  };
  function _sdL(k) { var p = SD_L[k]; return p ? p[curLang() === 'zh' ? 1 : 0] : ''; }
  // bilingual dual-span (matches the site .l-en/.l-zh mechanism) for static labels
  function _sdBl(k) {
    var p = SD_L[k]; if (!p) return '';
    return '<span class="l-en">' + _escHtml(p[0]) + '</span><span class="l-zh">' + _escHtml(p[1]) + '</span>';
  }
  // bilingual dual-span with placeholder substitution (e.g. {'__N__': '300'}) applied to
  // BOTH languages — placeholders are ascii tokens that survive _escHtml unchanged.
  function _sdBlSub(k, subs) {
    var p = SD_L[k]; if (!p) return '';
    function rep(s) { for (var m in subs) if (subs.hasOwnProperty(m)) s = s.split(m).join(_escHtml(String(subs[m]))); return s; }
    return '<span class="l-en">' + rep(_escHtml(p[0])) + '</span><span class="l-zh">' + rep(_escHtml(p[1])) + '</span>';
  }

  /* ---- inline SVG icons used only by the dashboard ------------------------ */
  var SD_ICON = {
    account: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    prefs:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h10M18 8h2M4 16h2M10 16h10"/><circle cx="16" cy="8" r="2"/><circle cx="8" cy="16" r="2"/></svg>',
    sync:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 18.5a4.5 4.5 0 0 0 0-9 6 6 0 0 0-11.4 1.6A3.8 3.8 0 0 0 6.5 18.5z"/><path d="m10 14 2 2 2-2M12 16v-5"/></svg>',
    signout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/></svg>',
    user:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    lock:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
    ctaUser: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    extlink: '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M8 7h9v9"/></svg>',
    maximize:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>',
    billing: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3 10h18M6.5 15H11"/></svg>',
    usage:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 19a8 8 0 1 1 15 0"/><path d="m12 14.5 3.5-3.5"/><circle cx="12" cy="19" r="1.25" fill="currentColor" stroke="none"/></svg>',
    check:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 6.5"/></svg>'
  };
  // Per-month display price by tier+interval, mirroring config/plans.yml (and onboard.js
  // CENTS). Billing-hero decoration only — never a gate; the upgrade sheet owns real pricing.
  var SD_PRICE = {
    insider: { monthly: 69, annual: 49, annualYr: 588 },
    pro:     { monthly: 99, annual: 69, annualYr: 828 }
  };
  // Plain-word plan highlights for the Billing "what's included" summary. Kept in step
  // with plans.html.j2 / config/plans.yml; decorative only (never a gate).
  var SD_PLAN_FEATURES = {
    free:    [['US macro dashboard', '美国宏观仪表盘'], ['The Terminal — 3 indicators', 'Terminal — 3 个指标'], ['3 signals per daily list', '每个每日列表 3 条信号'], ['5 Mastermind questions a week', '每周 5 次 Mastermind 提问']],
    insider: [['Every dashboard & all research', '全部看板与研究'], ['Full Terminal + live options', '完整 Terminal + 实时期权'], ['300 Mastermind questions a month', '每月 300 次 Mastermind 提问'], ['10 deep research questions a month', '每月 10 次深度研究提问']],
    pro:     [['Everything in Insider', 'Insider 全部功能'], ['Unlimited Mastermind questions', '无限量 Mastermind 提问'], ['150 deep research questions a month', '每月 150 次深度研究提问'], ['Priority research answers', '研究问题优先解答']]
  };
  // provider mini-icon markup (Google keeps its brand colours; X/email use currentColor)
  function _sdProviderIcon(kind) {
    if (kind === 'google') return GOOGLE_SVG;
    if (kind === 'twitter') return X_SVG;
    return '';
  }

  /* ---- dashboard state ---------------------------------------------------- */
  var _sdBuilt = false, _sdOverlay = null, _sdSect = 'account', _sdLastFocus = null,
      _sdCopyTimer = null;
  // Entitlement payload from /api/me, cached by user id so the dashboard re-renders
  // (on 'mdx-auth' + 'langchange') paint the plan synchronously instead of re-fetching.
  // Reset to null on sign-out / user switch so a stale plan never shows for the wrong account.
  var _sdPlan = null, _sdPlanFor = null, _sdPlanBusy = false;

  function _sdInjectCSS() {
    if (document.getElementById('setdash-css')) return;
    var st = document.createElement('style'); st.id = 'setdash-css'; st.textContent = SDASH_CSS;
    (document.head || document.documentElement).appendChild(st);
  }

  // provider read off the Supabase user object (app_metadata.provider / providers[0])
  function _sdProvider(u) {
    var am = (u && u.app_metadata) || {};
    var p = am.provider || (Array.isArray(am.providers) && am.providers[0]) || 'email';
    return String(p).toLowerCase();
  }
  function _sdProviderLabel(p) {
    if (p === 'google') return _sdL('provGoogle');
    if (p === 'twitter') return _sdL('provX');
    if (p === 'email') return _sdL('provEmail');
    return p ? p.charAt(0).toUpperCase() + p.slice(1) : _sdL('provEmail');
  }
  // provider chip (for the ID-card) — brand icon when we have one, else plain label
  function _sdProviderChip(p) {
    var ic = _sdProviderIcon(p);
    return '<span class="sd-chip">' + ic + _escHtml(_sdProviderLabel(p)) + '</span>';
  }
  function _sdProviderPill(p) {
    var ic = _sdProviderIcon(p);
    return '<span class="sd-provider">' + ic + _escHtml(_sdProviderLabel(p)) + '</span>';
  }
  function _sdDate(iso) {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleDateString(curLang() === 'zh' ? 'zh-CN' : undefined,
        { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) { return ''; }
  }
  function _sdAuthState() {
    if (!_authEnabled) return 'out';
    if (!_curUser) return 'out';
    var email = _curUser.email || (_curUser.user_metadata && _curUser.user_metadata.email) || '';
    return email ? 'in' : 'guest';       // signed-in but no email = access-password guest
  }

  /* ---- build the dashboard shell once ------------------------------------- */
  function _buildSDash() {
    if (_sdBuilt) return;
    _sdInjectCSS();
    var ov = document.createElement('div');
    ov.className = 'sd-overlay'; ov.id = 'setdash';
    ov.innerHTML =
      '<div class="sd-card" role="dialog" aria-modal="true" id="setdash-card">' +
        '<span class="sd-laser" aria-hidden="true"></span>' +
        '<aside class="sd-rail">' +
          '<div class="sd-me" id="sd-me"></div>' +
          '<nav class="sd-nav" id="sd-nav" role="tablist" aria-label="Settings sections">' +
            '<button type="button" class="sd-nav-b" data-sect="account" role="tab" aria-selected="false" id="sd-tab-account">' +
              SD_ICON.account + _sdBl('acctTitle') + '</button>' +
            '<button type="button" class="sd-nav-b" data-sect="billing" role="tab" aria-selected="false" id="sd-tab-billing">' +
              SD_ICON.billing + _sdBl('billingTitle') + '</button>' +
            '<button type="button" class="sd-nav-b" data-sect="usage" role="tab" aria-selected="false" id="sd-tab-usage">' +
              SD_ICON.usage + _sdBl('usageTitle') + '</button>' +
            '<button type="button" class="sd-nav-b" data-sect="prefs" role="tab" aria-selected="false" id="sd-tab-prefs">' +
              SD_ICON.prefs + _sdBl('prefsTitle') + '</button>' +
            '<button type="button" class="sd-nav-b" data-sect="sync" role="tab" aria-selected="false" id="sd-tab-sync">' +
              SD_ICON.sync + _sdBl('syncTitle') + '</button>' +
          '</nav>' +
          '<span class="sd-rail-spacer"></span>' +
          '<button type="button" class="sd-signout" id="sd-signout-rail">' +
            SD_ICON.signout + _sdBl('signOut') + '</button>' +
          '<button type="button" class="sd-x-m" id="sd-x-m" aria-label="' + _escHtml(_sdL('close')) + '">' + SET_ICON.x + '</button>' +
        '</aside>' +
        '<section class="sd-pane">' +
          '<div class="sd-sect" id="sd-sect-account"></div>' +
          '<div class="sd-sect" id="sd-sect-billing"></div>' +
          '<div class="sd-sect" id="sd-sect-usage"></div>' +
          '<div class="sd-sect" id="sd-sect-prefs"></div>' +
          '<div class="sd-sect" id="sd-sect-sync"></div>' +
        '</section>' +
      '</div>';
    document.body.appendChild(ov);
    _sdOverlay = ov;
    _sdBuilt = true;
    _wireSDash(ov);
    // re-render + re-localize on auth change and language change while built
    window.addEventListener('mdx-auth', function () { if (_sdBuilt) _renderSDash(); });
    document.addEventListener('langchange', function () { if (_sdBuilt) { _sdRelabelAria(); _renderSDash(); } });
    // keep the Appearance segment's active state synced with the popover's
    document.addEventListener('themechange', function () { if (_sdBuilt) _sdSyncThemeSeg(); });
  }

  // localize the aria-labels that live in attributes (dialog + close buttons)
  function _sdRelabelAria() {
    if (!_sdOverlay) return;
    var card = _sdOverlay.querySelector('.sd-card');
    if (card) card.setAttribute('aria-label', _sdL(_sdSect === 'prefs' ? 'prefsTitle' : _sdSect === 'sync' ? 'syncTitle' : 'acctTitle'));
    var nav = _sdOverlay.querySelector('#sd-nav');
    if (nav) nav.setAttribute('aria-label', _sdL('sections'));
    _sdOverlay.querySelectorAll('.sd-x,.sd-x-m').forEach(function (b) { b.setAttribute('aria-label', _sdL('close')); });
  }

  function _wireSDash(ov) {
    var card = ov.querySelector('.sd-card');
    // overlay click-outside closes
    ov.addEventListener('mousedown', function (e) { if (e.target === ov) _closeSDash(); });
    // rail tabs
    ov.querySelector('#sd-nav').addEventListener('click', function (e) {
      var b = e.target && e.target.closest ? e.target.closest('.sd-nav-b') : null;
      if (b) _sdShow(b.getAttribute('data-sect'));
    });
    // sign-out (rail)
    var so = ov.querySelector('#sd-signout-rail');
    if (so) so.addEventListener('click', function () { if (window.MDXAuth) window.MDXAuth.signOut(); });
    // mobile close
    var xm = ov.querySelector('#sd-x-m');
    if (xm) xm.addEventListener('click', _closeSDash);
    // Esc closes the dash (and only the dash)
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && ov.classList.contains('open')) { e.stopPropagation(); _closeSDash(); }
    });
    // light focus trap (Tab cycle) — mirrors the auth modal
    card.addEventListener('keydown', function (e) {
      if (e.key !== 'Tab') return;
      var f = card.querySelectorAll('button:not([disabled]),input:not([disabled]),a[href],[tabindex="0"]');
      f = Array.prototype.filter.call(f, function (el) { return el.offsetParent !== null; });  // visible only
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
  }

  // switch the visible section + sync rail tab aria
  function _sdShow(sect) {
    if (!_sdOverlay) return;
    if (['account', 'billing', 'usage', 'prefs', 'sync'].indexOf(sect) < 0) sect = 'prefs';
    // account/billing/usage need an account — fall back to prefs when auth is off
    if ((sect === 'account' || sect === 'billing' || sect === 'usage') && !_authEnabled) sect = 'prefs';
    _sdSect = sect;
    _sdOverlay.querySelectorAll('.sd-nav-b').forEach(function (b) {
      var on = b.getAttribute('data-sect') === sect;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    ['account', 'billing', 'usage', 'prefs', 'sync'].forEach(function (s) {
      var el = document.getElementById('sd-sect-' + s);
      if (el) el.classList.toggle('on', s === sect);
    });
    if (sect === 'usage') _sdAnimateMeters();
    _sdRelabelAria();
  }

  /* ---- render the three section bodies from current state ----------------- */
  function _renderSDash() {
    if (!_sdBuilt) return;
    var state = _sdAuthState();     // 'in' | 'guest' | 'out'
    var u = _curUser || {};
    // rail me-card
    var me = document.getElementById('sd-me');
    if (me) {
      if (state === 'out') {
        me.innerHTML =
          '<span class="sd-me-av guestav">' + SD_ICON.user + '</span>' +
          '<span class="sd-me-main">' +
            '<span class="sd-me-name">' + _sdBl('notSignedIn') + '</span>' +
            '<span class="sd-me-sub">' + _sdBl('localOnly') + '</span>' +
          '</span>';
      } else {
        var email = u.email || (u.user_metadata && u.user_metadata.email) || '';
        var meta = u.user_metadata || {};
        var dn = meta.display_name || '';
        var avc = (dn ? dn.charAt(0) : (email ? email.charAt(0) : 'U')).toUpperCase();
        var nm = state === 'guest' ? _sdL('accessSess') : (dn || email || '—');
        me.innerHTML =
          '<span class="sd-me-av">' + _escHtml(avc) + '</span>' +
          '<span class="sd-me-main">' +
            '<span class="sd-me-name">' + _escHtml(nm) + '</span>' +
            '<span class="sd-me-sub">' + (state === 'guest' ? _sdBl('accessSess') : _sdBl('railSub')) + '</span>' +
          '</span>';
      }
    }
    // rail sign-out only when signed in with an email
    var railSo = document.getElementById('sd-signout-rail');
    if (railSo) railSo.style.display = (state === 'in') ? '' : 'none';
    // account / billing / usage tabs need an account — hidden entirely when auth off
    ['account', 'billing', 'usage'].forEach(function (s) {
      var tab = document.getElementById('sd-tab-' + s);
      if (tab) tab.style.display = _authEnabled ? '' : 'none';
    });

    _renderSDAccount(state, u);
    _renderSDBilling(state, u);
    _renderSDUsage(state, u);
    _renderSDPrefs();
    _renderSDSync(state, u);
    _sdSyncThemeSeg();
    // if the current section is now invalid (its tab hidden), route to prefs
    if ((_sdSect === 'account' || _sdSect === 'billing' || _sdSect === 'usage') && !_authEnabled) _sdShow('prefs');
  }

  function _sdHead(titleKey, subKey) {
    return '<header class="sd-head">' +
      '<div class="sd-head-main">' +
        '<h2>' + _sdBl(titleKey) + '</h2>' +
        '<p class="sd-sub">' + _sdBl(subKey) + '</p>' +
      '</div>' +
      '<button type="button" class="sd-x" aria-label="' + _escHtml(_sdL('close')) + '">' + SET_ICON.x + '</button>' +
    '</header>';
  }

  function _renderSDAccount(state, u) {
    var host = document.getElementById('sd-sect-account');
    if (!host) return;
    var html = _sdHead('acctTitle', 'acctSub') + '<div class="sd-body">';

    if (state === 'out') {
      html += '<div class="sd-cta">' +
          '<span class="sd-cta-av">' + SD_ICON.ctaUser + '</span>' +
          '<p class="sd-cta-t">' + _sdBl('ctaTitle') + '</p>' +
          '<p class="sd-cta-n">' + _sdBl('ctaNote') + '</p>' +
          '<div class="sd-cta-btns">' +
            '<button type="button" class="sd-btn ghost" data-sd-cta="signin">' + _sdBl('signin') + '</button>' +
            '<button type="button" class="sd-btn primary" data-sd-cta="signup">' + _sdBl('createAcct') + '</button>' +
          '</div>' +
        '</div>';
    } else if (state === 'guest') {
      html += '<div class="sd-cta">' +
          '<span class="sd-cta-av">' + SD_ICON.lock + '</span>' +
          '<p class="sd-cta-t">' + _sdBl('accessSess') + '</p>' +
          '<p class="sd-cta-n">' + _sdBl('guestNote') + '</p>' +
          '<div class="sd-cta-btns">' +
            '<button type="button" class="sd-btn primary" data-sd-cta="signup">' + _sdBl('createFree') + '</button>' +
          '</div>' +
        '</div>';
    } else {
      var email = u.email || (u.user_metadata && u.user_metadata.email) || '';
      var meta = u.user_metadata || {};
      var dn = meta.display_name || '';
      var prov = _sdProvider(u);
      var idName = dn || email;
      var avc = (dn ? dn.charAt(0) : (email ? email.charAt(0) : 'U')).toUpperCase();
      var since = _sdDate(u.created_at);
      var lastIn = _sdDate(u.last_sign_in_at);
      var uid = u.id || '';
      var uidShort = uid.length > 10 ? (uid.slice(0, 4) + '…' + uid.slice(-4)) : uid;

      // ID card (signature)
      html += '<div class="sd-id">' +
          '<span class="sd-id-av">' + _escHtml(avc) + '</span>' +
          '<span class="sd-id-main">' +
            '<span class="sd-id-name">' + _escHtml(idName) + '</span>' +
            (dn ? '<span class="sd-id-mail">' + _escHtml(email) + '</span>' : '') +
            '<span class="sd-id-chips">' +
              _sdProviderChip(prov) +
              (since ? '<span class="sd-chip">' + _sdL('memberSince') + ' ' + _escHtml(since) + '</span>' : '') +
            '</span>' +
          '</span>' +
        '</div>';

      // Plan/billing moved to the dedicated Billing tab. Profile + Security sit in a
      // two-column grid that fills the widened card and collapses to one column when narrow.
      html += '<div class="sd-grid">';

      // Profile group
      html += '<div class="sd-group">' +
          '<span class="sd-group-t">' + _sdBl('profile') + '</span>' +
          // display name
          '<div class="sd-row" id="sd-row-name">' +
            '<div class="sd-row-line">' +
              '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('dispName') + '</span></span>' +
              '<span class="sd-row-val' + (dn ? ' strong' : '') + '" id="sd-name-val">' + _escHtml(dn || '—') + '</span>' +
              '<button type="button" class="sd-edit" data-sd-edit="name">' + _sdBl('edit') + '</button>' +
            '</div>' +
            '<div class="sd-form">' +
              '<input class="sd-in" type="text" id="sd-name-in" placeholder="' + _escHtml(_sdL('dispNamePh')) + '" value="' + _escHtml(dn) + '">' +
              '<div class="sd-msg" id="sd-name-msg" role="alert"></div>' +
              '<div class="sd-btns">' +
                '<button type="button" class="sd-btn ghost" data-sd-cancel="name">' + _sdBl('cancel') + '</button>' +
                '<button type="button" class="sd-btn primary" id="sd-name-save">' + _sdBl('save') + '</button>' +
              '</div>' +
            '</div>' +
          '</div>' +
          // email — the address itself is the row's primary text (no redundant "Email" label)
          '<div class="sd-row" id="sd-row-email">' +
            '<div class="sd-row-line">' +
              '<span class="sd-row-main"><span class="sd-row-lbl sd-mailv">' + _escHtml(email) + '</span></span>' +
              '<button type="button" class="sd-edit" data-sd-edit="email">' + _sdBl('edit') + '</button>' +
            '</div>' +
            '<div class="sd-form">' +
              '<input class="sd-in" type="email" id="sd-email-in" placeholder="' + _escHtml(_sdL('emailPh')) + '" autocomplete="email" autocapitalize="off" spellcheck="false">' +
              '<p class="sd-note">' + _sdBl('emailNote') + '</p>' +
              '<div class="sd-msg" id="sd-email-msg" role="alert"></div>' +
              '<div class="sd-btns">' +
                '<button type="button" class="sd-btn ghost" data-sd-cancel="email">' + _sdBl('cancel') + '</button>' +
                '<button type="button" class="sd-btn primary" id="sd-email-save">' + _sdBl('sendConfirm') + '</button>' +
              '</div>' +
            '</div>' +
          '</div>' +
          // password
          '<div class="sd-row" id="sd-row-pw">' +
            '<div class="sd-row-line">' +
              '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('password') + '</span></span>' +
              '<span class="sd-row-val">••••••••</span>' +
              '<button type="button" class="sd-edit" data-sd-edit="pw">' + _sdBl('edit') + '</button>' +
            '</div>' +
            '<div class="sd-form">' +
              '<input class="sd-in" type="password" id="sd-pw-in" placeholder="' + _escHtml(_sdL('newPwPh')) + '" autocomplete="new-password">' +
              '<input class="sd-in" type="password" id="sd-pw2-in" placeholder="' + _escHtml(_sdL('confirmPwPh')) + '" autocomplete="new-password">' +
              '<div class="sd-msg" id="sd-pw-msg" role="alert"></div>' +
              '<div class="sd-btns">' +
                '<button type="button" class="sd-btn ghost" data-sd-cancel="pw">' + _sdBl('cancel') + '</button>' +
                '<button type="button" class="sd-btn primary" id="sd-pw-save">' + _sdBl('updatePw') + '</button>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</div>';

      // Security group
      html += '<div class="sd-group">' +
          '<span class="sd-group-t">' + _sdBl('security') + '</span>' +
          '<div class="sd-row"><div class="sd-row-line">' +
            '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('loginMethod') + '</span></span>' +
            _sdProviderPill(prov) +
          '</div></div>' +
          (lastIn ? '<div class="sd-row"><div class="sd-row-line">' +
            '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('lastSignin') + '</span></span>' +
            '<span class="sd-row-val">' + _escHtml(lastIn) + '</span>' +
          '</div></div>' : '') +
          '<div class="sd-row"><div class="sd-row-line">' +
            '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('userId') + '</span>' +
              '<span class="sd-row-desc">' + _sdBl('userIdNote') + '</span></span>' +
            '<span class="sd-row-val">' + _escHtml(uidShort) + '</span>' +
            '<button type="button" class="sd-mini" id="sd-copy-uid" data-uid="' + _escHtml(uid) + '">' + _sdBl('copy') + '</button>' +
          '</div></div>' +
        '</div>';

      html += '</div>';  // end .sd-grid (Profile | Security)

      // mobile sign-out row
      html += '<button type="button" class="sd-signout-m" id="sd-signout-m">' + SD_ICON.signout + _sdBl('signOut') + '</button>';
    }

    html += '</div>';  // end sd-body
    host.innerHTML = html;
    _wireSDAccount(host, state, u);
  }

  /* ---- desk preferences (markets · what you trade) ------------------------
     Signup asks these two questions and writes them to user_metadata
     (market_focus / trade_types) — the SAME shape templates/onboard.js persists,
     and the same localStorage key ('mm.pendingPrefs') it stashes into before a
     session exists. Until now there was nowhere to change the answers: the only
     way back to that screen was the signup wizard itself. These read from the
     account when there is one and from the pending stash when there isn't, so a
     preference set before sign-up is never lost and never asked for twice. */
  var SD_MARKETS = [['us', 'mktUs'], ['cn', 'mktCn'], ['hk', 'mktHk'], ['ca', 'mktCa'], ['global', 'mktGlobal']];
  var SD_TRADES = [['stocks', 'trStocks'], ['options', 'trOptions'], ['crypto', 'trCrypto']];
  var LS_PENDING_PREFS = 'mm.pendingPrefs';
  var _sdDesk = null;            // { market_focus:[], trade_types:[] } — live edit buffer
  var _sdDeskTimer = null;

  function _sdPendingPrefs() {
    try { var o = JSON.parse(localStorage.getItem(LS_PENDING_PREFS) || 'null'); return (o && typeof o === 'object') ? o : null; } catch (e) { return null; }
  }
  function _sdArr(v) {
    if (!v || Object.prototype.toString.call(v) !== '[object Array]') return [];
    var out = []; for (var i = 0; i < v.length; i++) if (typeof v[i] === 'string' && out.indexOf(v[i]) === -1) out.push(v[i]);
    return out;
  }
  // account first, then the pre-sign-up stash — a signed-in user's server answer wins
  function _sdLoadDesk() {
    var meta = (_curUser && _curUser.user_metadata) || {};
    var pend = _sdPendingPrefs() || {};
    var mf = _sdArr(meta.market_focus), tt = _sdArr(meta.trade_types);
    if (!mf.length) mf = _sdArr(pend.market_focus);
    if (!tt.length) tt = _sdArr(pend.trade_types);
    _sdDesk = { market_focus: mf, trade_types: tt };
    return _sdDesk;
  }
  // Local mirror always; the account too when there is one. The local write
  // MERGES into the existing stash so it never drops the name signup put there.
  /* Canonical market preference derived from the desk chips.

     The Terminal (charting-app terminal/lib/markets.ts) reads
     `user_metadata.markets = {home, enabled[], autoNarrowed}` and treats an
     explicit `markets` object as authoritative over `market_focus` — otherwise a
     preference narrowed in settings would be reverted on every load by the
     signup-time array. So writing ONLY market_focus here would be silently
     ignored by the Terminal for any user who has ever set their markets over
     there. One writer, one shape: every desk save emits both.

     `autoNarrowed` is false on this path by design. That flag exists to explain
     a narrowing WE chose for a US-only signup ("other markets start hidden");
     a choice the user just made by hand needs no explanation. */
  function _sdMarketsFromChips(mf) {
    var ALL = ['us', 'cn', 'hk', 'ca', 'intl', 'crypto'];
    var picks = [], global = false;
    for (var i = 0; i < (mf || []).length; i++) {
      if (mf[i] === 'global') { global = true; continue; }
      if (mf[i] === 'us' || mf[i] === 'cn' || mf[i] === 'hk' || mf[i] === 'ca') picks.push(mf[i]);
    }
    if (global || !picks.length) return { home: picks[0] || null, enabled: ALL.slice(), autoNarrowed: false };
    // Crypto rides along regardless: it is an asset class, not a country market,
    // and dropping BTC because someone follows only US equities would be a bug.
    var enabled = picks.slice(); enabled.push('crypto');
    var canon = [];
    for (var j = 0; j < ALL.length; j++) if (enabled.indexOf(ALL[j]) > -1) canon.push(ALL[j]);
    return { home: picks[0], enabled: canon, autoNarrowed: false };
  }

  function _sdSaveDesk(msgEl) {
    clearTimeout(_sdDeskTimer);
    var signedIn = !!(_curUser && _authEnabled && _curUser.email);
    _sdDeskTimer = setTimeout(function () {
      var payload = {
        market_focus: _sdDesk.market_focus,
        trade_types: _sdDesk.trade_types,
        markets: _sdMarketsFromChips(_sdDesk.market_focus)
      };
      try {
        var pend = _sdPendingPrefs() || {};
        pend.market_focus = payload.market_focus; pend.trade_types = payload.trade_types;
        localStorage.setItem(LS_PENDING_PREFS, JSON.stringify(pend));
      } catch (e) {}
      if (!signedIn) { _sdDeskMsg(msgEl, 'prefLocal', 'ok'); return; }
      getSupabaseClient().then(function (sb) {
        if (!sb || !_curUser) { _sdDeskMsg(msgEl, 'prefLocal', 'ok'); return null; }
        return sb.auth.updateUser({ data: payload }).then(function (r) {
          if (r && r.error) { _sdDeskMsg(msgEl, 'prefErr', 'err'); return; }
          // keep the in-memory user in step so a re-render shows the saved answer
          if (_curUser) {
            _curUser.user_metadata = _curUser.user_metadata || {};
            _curUser.user_metadata.market_focus = payload.market_focus;
            _curUser.user_metadata.trade_types = payload.trade_types;
            _curUser.user_metadata.markets = payload.markets;
          }
          // Re-fold the country menus without a reload — the home market may have
          // just changed, and a nav that still shows the old one reads as a bug.
          try { window.dispatchEvent(new CustomEvent('mdx-auth', { detail: { user: _curUser, event: 'PREFS_SAVED' } })); } catch (e) {}
          _sdDeskMsg(msgEl, 'prefSaved', 'ok');
        });
      }).catch(function () { _sdDeskMsg(msgEl, 'prefErr', 'err'); });
    }, 500);
  }
  var _sdDeskMsgTimer = null;
  function _sdDeskMsg(el, key, kind) {
    if (!el) return;
    el.className = 'sd-msg show ' + (kind === 'err' ? 'err' : 'ok');
    el.innerHTML = _sdBl(key);
    clearTimeout(_sdDeskMsgTimer);
    if (kind !== 'err') _sdDeskMsgTimer = setTimeout(function () { el.className = 'sd-msg'; }, 2600);
  }
  function _sdChipsHTML(list, sel, group) {
    var out = '<div class="sd-pchips" role="group" aria-label="' + _escHtml(_sdL(group === 'market_focus' ? 'markets' : 'trades')) + '">';
    for (var i = 0; i < list.length; i++) {
      var on = sel.indexOf(list[i][0]) !== -1;
      out += '<button type="button" class="sd-pchip" data-sd-pref="' + group + '" data-val="' + list[i][0] + '" aria-pressed="' + (on ? 'true' : 'false') + '">' +
             '<span class="box">' + SD_ICON.check + '</span>' + _sdBl(list[i][1]) + '</button>';
    }
    return out + '</div>';
  }

  function _renderSDPrefs() {
    var host = document.getElementById('sd-sect-prefs');
    if (!host) return;
    var desk = _sdLoadDesk();
    host.innerHTML = _sdHead('prefsTitle', 'prefsSub') + '<div class="sd-body">' +
      // ── your desk: the two questions signup asked, now changeable ──
      '<div class="sd-group" style="margin-top:4px">' +
        '<span class="sd-group-t">' + _sdBl('deskGroup') + '</span>' +
        '<div class="sd-row">' +
          '<div class="sd-row-line"><span class="sd-row-main">' +
            '<span class="sd-row-lbl">' + _sdBl('markets') + '</span>' +
            '<span class="sd-row-desc">' + _sdBl('marketsNote') + '</span></span></div>' +
          _sdChipsHTML(SD_MARKETS, desk.market_focus, 'market_focus') +
        '</div>' +
        '<div class="sd-row">' +
          '<div class="sd-row-line"><span class="sd-row-main">' +
            '<span class="sd-row-lbl">' + _sdBl('trades') + '</span>' +
            '<span class="sd-row-desc">' + _sdBl('tradesNote') + '</span></span></div>' +
          _sdChipsHTML(SD_TRADES, desk.trade_types, 'trade_types') +
          '<p class="sd-msg" id="sd-desk-msg"></p>' +
        '</div>' +
      '</div>' +
      '<div class="sd-group">' +
        '<span class="sd-group-t">' + _sdBl('themeLang') + '</span>' +
        // appearance
        '<div class="sd-row"><div class="sd-row-line">' +
          '<span class="sd-row-main">' +
            '<span class="sd-row-lbl">' + _sdBl('appearance') + '</span>' +
            '<span class="sd-row-desc">' + _sdBl('appearNote') + '</span></span>' +
          '<span class="sd-seg" id="sd-theme-seg" role="group" aria-label="' + _escHtml(_sdL('appearance')) + '">' +
            '<button type="button" class="sd-seg-b" data-sd-theme="light">' + _sdBl('themeLight') + '</button>' +
            '<button type="button" class="sd-seg-b" data-sd-theme="auto">' + _sdBl('themeAuto') + '</button>' +
            '<button type="button" class="sd-seg-b" data-sd-theme="dark">' + _sdBl('themeDark') + '</button>' +
          '</span>' +
        '</div></div>' +
        // language
        '<div class="sd-row"><div class="sd-row-line">' +
          '<span class="sd-row-main">' +
            '<span class="sd-row-lbl">' + _sdBl('language') + '</span>' +
            '<span class="sd-row-desc">' + _sdBl('langNote') + '</span></span>' +
          '<span class="sd-seg" id="sd-lang-seg" role="group" aria-label="' + _escHtml(_sdL('language')) + '">' +
            '<button type="button" class="sd-seg-b" data-sd-lang="en">EN</button>' +
            '<button type="button" class="sd-seg-b" data-sd-lang="zh">中文</button>' +
          '</span>' +
        '</div></div>' +
      '</div>' +
    '</div>';
    _wireSDPrefs(host);
  }

  function _renderSDSync(state, u) {
    var host = document.getElementById('sd-sect-sync');
    if (!host) return;
    var email = u.email || (u.user_metadata && u.user_metadata.email) || '';
    var signedIn = (state === 'in' || state === 'guest');
    // watchlist link target: derive the site-root prefix from theme.js's own
    // <script src>, which is correct at ANY page depth (blog/ learn/ tools/
    // sectors/ …) and under subpath hosting — a '/sectors/'-only check 404s
    // everywhere else one level deep.
    var pfx = '';
    var _ts = document.querySelector('script[src$="theme.js"],script[src*="theme.js?"]');
    if (_ts) pfx = (_ts.getAttribute('src') || '').replace(/theme\.js(\?.*)?$/, '');
    var syncCard = signedIn
      ? '<div class="sd-sync"><span class="dot"></span><span class="sd-sync-main">' +
          '<span class="sd-sync-t">' + _sdBl('syncOn') + '</span>' +
          // ZH lead ends in a full-width colon — no space after it
          '<span class="sd-sync-s">' + _sdL('signedInAs') + (/：$/.test(_sdL('signedInAs')) ? '' : ' ') + (state === 'in' ? _escHtml(email) : _escHtml(_sdL('accessSess'))) + '</span>' +
        '</span></div>'
      : '<div class="sd-sync off"><span class="dot"></span><span class="sd-sync-main">' +
          '<span class="sd-sync-t">' + _sdBl('syncOff') + '</span>' +
          '<span class="sd-sync-s">' + _sdBl('signInToOn') + '</span>' +
        '</span>' +
        // no sign-in CTA when auth is disabled — openAuthModal would no-op
        (_authEnabled ? '<button type="button" class="sd-btn primary" style="flex:none" data-sd-cta="signin">' + _sdBl('signin') + '</button>' : '') + '</div>';

    host.innerHTML = _sdHead('syncTitle', 'syncSub') + '<div class="sd-body">' +
      syncCard +
      '<div class="sd-group">' +
        '<div class="sd-row"><div class="sd-row-line"><span class="sd-row-main">' +
          '<span class="sd-row-lbl">' + _sdBl('themeLang') + '</span>' +
          '<span class="sd-row-desc">' + _sdBl('themeLangN') + '</span></span></div></div>' +
        '<div class="sd-row"><div class="sd-row-line"><span class="sd-row-main">' +
          '<span class="sd-row-lbl">' + _sdBl('watchlists') + '</span>' +
          '<span class="sd-row-desc">' + _sdBl('watchNote') + '</span></span>' +
          '<a class="sd-link" href="' + pfx + 'watchlist.html">' + _sdBl('openWatch') + SD_ICON.extlink + '</a>' +
        '</div></div>' +
      '</div>' +
    '</div>';
    _wireSDSync(host);
  }

  /* ---- Billing tab -------------------------------------------------------- */
  // shared signed-out / guest CTA reused by the account-less tabs (billing, usage)
  function _sdSignedOutCTA(state) {
    if (state === 'guest') {
      return '<div class="sd-cta"><span class="sd-cta-av">' + SD_ICON.lock + '</span>' +
          '<p class="sd-cta-t">' + _sdBl('accessSess') + '</p>' +
          '<p class="sd-cta-n">' + _sdBl('guestNote') + '</p>' +
          '<div class="sd-cta-btns"><button type="button" class="sd-btn primary" data-sd-cta="signup">' + _sdBl('createFree') + '</button></div></div>';
    }
    return '<div class="sd-cta"><span class="sd-cta-av">' + SD_ICON.ctaUser + '</span>' +
        '<p class="sd-cta-t">' + _sdBl('ctaTitle') + '</p>' +
        '<p class="sd-cta-n">' + _sdBl('ctaNote') + '</p>' +
        '<div class="sd-cta-btns">' +
          '<button type="button" class="sd-btn ghost" data-sd-cta="signin">' + _sdBl('signin') + '</button>' +
          '<button type="button" class="sd-btn primary" data-sd-cta="signup">' + _sdBl('createAcct') + '</button>' +
        '</div></div>';
  }

  function _sdPlanHeroHTML() {
    if (!_sdPlan) return '<div class="sd-skel" style="height:118px;margin:4px 0 14px"></div>';
    var p = _sdPlan;
    var tier = p.tier || 'free';
    var interval = p.interval || null;
    var paid = tier !== 'free';
    var chip = _sdPlanChip(p);
    var priceHtml = '';
    if (paid && SD_PRICE[tier] && interval) {
      var pr = SD_PRICE[tier];
      var mo = interval === 'annual' ? pr.annual : pr.monthly;
      var billed = interval === 'annual'
        ? (_sdBl('billedAnnual') + ' <span class="sd-muted">($' + pr.annualYr + '/yr)</span>')
        : _sdBl('billedMonthly');
      priceHtml = '<div class="sd-ph-price"><b>$' + mo + '</b>' + _sdBl('perMo') + ' · ' + billed + '</div>';
    }
    return '<div class="sd-plan-hero' + (paid ? '' : ' free') + '">' +
        '<div class="sd-ph-top">' +
          '<div><span class="sd-ph-eyebrow">' + _sdBl('currentPlan') + '</span>' +
            '<div class="sd-ph-name">' + _escHtml(_sdTierLabel(tier)) + '</div></div>' +
          (chip ? '<span style="flex:none">' + chip + '</span>' : '') +
        '</div>' +
        (paid ? priceHtml : '<div class="sd-ph-price">' + _sdBl('freePitch') + '</div>') +
      '</div>';
  }

  function _renderSDBilling(state, u) {
    var host = document.getElementById('sd-sect-billing');
    if (!host) return;
    var html = _sdHead('billingTitle', 'billingSub') + '<div class="sd-body">';
    if (state !== 'in') {
      host.innerHTML = html + _sdSignedOutCTA(state) + '</div>';
      _sdWireCta(host);
      return;
    }
    html += _sdPlanHeroHTML();
    var p = _sdPlan || {};
    var tier = p.tier || 'free';
    var interval = p.interval || null;
    var top = (tier === 'unlimited') || (tier === 'pro' && interval === 'annual');
    if (!top) {
      var lblKey = (tier === 'free') ? 'choosePlan' : (tier === 'insider') ? 'upgradePro' : 'switchAnnual';
      html += '<div class="sd-plan-cta" style="margin:0 0 14px">' +
        '<button type="button" class="sd-btn primary" data-sd-cta="upgrade" id="sd-bill-up">' + _sdBl(lblKey) + '</button></div>';
    }
    // what's included on the current plan (plain-word highlights)
    var feats = SD_PLAN_FEATURES[tier] || SD_PLAN_FEATURES.free;
    html += '<div class="sd-group"><span class="sd-group-t">' + _sdBl('planIncludes') + '</span>';
    for (var fi = 0; fi < feats.length; fi++) {
      html += '<div class="sd-incl-row">' + SD_ICON.check +
        '<span><span class="l-en">' + _escHtml(feats[fi][0]) + '</span><span class="l-zh">' + _escHtml(feats[fi][1]) + '</span></span></div>';
    }
    html += '</div>';
    // The Stripe portal only exists for a row Stripe actually owns. A comp / lifetime
    // grant (source 'comp', the same signal _sdPlanChip reads for its Lifetime chip) has
    // no stripe_customer_id, so /api/billing/portal 404s for it by design — offering the
    // button anyway produced a dead "Open" that failed every time.
    if (tier !== 'free' && (p.source || 'stripe') === 'stripe') {
      html += '<div class="sd-group">' +
          '<div class="sd-row"><div class="sd-row-line">' +
            '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('manageBilling') + '</span>' +
              '<span class="sd-row-desc">' + _sdBl('manageBillingNote') + '</span></span>' +
            '<button type="button" class="sd-link" id="sd-portal-btn">' + _sdBl('openPortal') + SD_ICON.extlink + '</button>' +
          '</div></div>' +
          '<div class="sd-msg" id="sd-bill-msg" role="alert"></div>' +
        '</div>';
    } else if (tier !== 'free') {
      html += '<div class="sd-group">' +
          '<div class="sd-row"><div class="sd-row-line">' +
            '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('grantedPlan') + '</span>' +
              '<span class="sd-row-desc">' + _sdBl('grantedNote') + '</span></span>' +
          '</div></div>' +
        '</div>';
    }
    host.innerHTML = html + '</div>';
    _sdWireCta(host);
    var pb = host.querySelector('#sd-portal-btn');
    if (pb) pb.addEventListener('click', function () { _sdOpenPortal(pb); });
  }

  // Stripe customer portal — self-serve invoices / payment method / cancellation.
  function _sdOpenPortal(btn) {
    _sdMsg('sd-bill-msg', '');
    _sdSetBusy(btn, true, _sdL('opening'));
    var base = /(^|\.)mastermind-x\.com$/i.test(location.hostname || '') ? '' : (window.MM_API || '');
    getSupabaseClient().then(function (sb) { return sb ? sb.auth.getSession() : null; })
      .then(function (res) {
        var tok = res && res.data && res.data.session && res.data.session.access_token;
        var h = {}; if (tok) h['Authorization'] = 'Bearer ' + tok;
        return fetch(base + '/api/billing/portal', { headers: h, credentials: 'include' });
      })
      .then(function (r) {
        // Keep the status: 404 means this account has no Stripe billing at all (a comp
        // that outlived its subscription, say), which retrying will never fix.
        if (r && r.ok) return r.json().then(function (j) { return { j: j }; });
        return { status: r ? r.status : 0 };
      })
      .then(function (res) {
        _sdSetBusy(btn, false);
        if (res && res.j && res.j.url) { location.href = res.j.url; return; }
        _sdMsg('sd-bill-msg', _sdL(res && res.status === 404 ? 'portalNone' : 'portalErr'), 'err');
      })
      .catch(function () { _sdSetBusy(btn, false); _sdMsg('sd-bill-msg', _sdL('portalErr'), 'err'); });
  }

  /* ---- Usage tab ---------------------------------------------------------- */
  // brain quota payload from GET /api/brain/me — {tier, quotas:{fast,pro:{remaining,limit,period}}}
  var _sdUsage = null, _sdUsageFor = null, _sdUsageBusy = false, _sdUsageErr = false;

  function _renderSDUsage(state, u) {
    var host = document.getElementById('sd-sect-usage');
    if (!host) return;
    var html = _sdHead('usageTitle', 'usageSub') + '<div class="sd-body">';
    if (state !== 'in') {
      host.innerHTML = html + _sdSignedOutCTA(state) + '</div>';
      _sdWireCta(host);
      return;
    }
    // canonical source is GET /api/brain/me; fall back to /api/me's chat_budget (already
    // fetched with the plan) so the meters paint instantly and survive a brain-endpoint miss.
    if (!_sdUsage && !_sdUsageErr) _sdLoadUsage(u);
    var q = (_sdUsage && _sdUsage.quotas) || (_sdPlan && _sdPlan.chat_budget) || null;
    var tier = (_sdUsage && _sdUsage.tier) || (_sdPlan && _sdPlan.tier) || 'free';
    if (!q) {
      html += _sdUsageErr
        ? '<div class="sd-note" style="text-align:center;padding:30px 10px">' + _escHtml(_sdL('usageErr')) + '</div>'
        : '<div class="sd-grid"><div class="sd-skel"></div><div class="sd-skel"></div></div>';
      host.innerHTML = html + '</div>';
      return;
    }
    html += '<div class="sd-grid">' + _sdMeterHTML('chat', q.fast, tier) + _sdMeterHTML('deep', q.pro, tier) + '</div>';
    html += _sdUsageNudge(q, tier);
    host.innerHTML = html + '</div>';
    _sdWireCta(host);
    _sdAnimateMeters();
  }

  function _sdMeterHTML(kind, lane, tier) {
    var isChat = kind === 'chat';
    var lbl = _sdBl(isChat ? 'chatLane' : 'deepLane');
    var note = _sdBl(isChat ? 'chatLaneNote' : 'deepLaneNote');
    lane = lane || {};
    var limit = (typeof lane.limit === 'number') ? lane.limit : 0;
    var remaining = (typeof lane.remaining === 'number') ? lane.remaining : 0;
    var period = lane.period || 'month';
    // uncapped tier
    if (limit < 0) {
      return '<div class="sd-meter unl">' +
          '<div class="sd-meter-h"><span class="sd-meter-lbl">' + lbl + '</span></div>' +
          '<div class="sd-meter-big"><span class="sd-meter-num">' + _sdBl('unlimited') + '</span></div>' +
          '<div class="sd-meter-foot">' + note + ' ' + _sdBl('unlimitedNote') + '</div>' +
        '</div>';
    }
    // lane not included on this tier (e.g. deep research on Free) -> plain upsell, no bar
    if (limit === 0) {
      return '<div class="sd-meter">' +
          '<div class="sd-meter-h"><span class="sd-meter-lbl">' + lbl + '</span></div>' +
          '<div class="sd-meter-foot" style="margin-top:12px">' + note + ' ' + _sdBl('deepLockedFree') + '</div>' +
        '</div>';
    }
    var pct = Math.max(0, Math.min(100, Math.round(remaining / limit * 100)));
    var ratio = remaining / limit;
    var cls = remaining <= 0 ? ' out' : (ratio <= 0.15 ? ' low' : '');
    var capKey = period === 'week' ? 'capWeek' : period === 'trial' ? 'capTrial' : 'capMonth';
    var reset = period === 'week' ? (' · ' + _sdBl('resetsWeekly')) : period === 'trial' ? '' : (' · ' + _sdBl('resetsMonthly'));
    return '<div class="sd-meter' + cls + '">' +
        '<div class="sd-meter-h"><span class="sd-meter-lbl">' + lbl + '</span><span class="sd-meter-cap">' + _sdBl(capKey) + '</span></div>' +
        '<div class="sd-meter-big"><span class="sd-meter-num">' + remaining + '</span><span class="sd-meter-of">' + _sdBl('usageLeft') + '</span></div>' +
        '<div class="sd-meter-bar"><span class="sd-meter-fill" data-pct="' + pct + '"></span></div>' +
        '<div class="sd-meter-foot">' + _sdBlSub('ofN', { '__N__': limit }) + reset + '</div>' +
      '</div>';
  }

  function _sdUsageNudge(q, tier) {
    // Pro/Unlimited already carry the most questions — the annual switch (if any) lives
    // on the Billing tab, so no "upgrade for more questions" nudge here.
    if (tier === 'unlimited' || tier === 'pro') return '';
    var low = ['fast', 'pro'].some(function (k) {
      var l = q[k] || {}; return typeof l.limit === 'number' && l.limit > 0 && (l.remaining / l.limit) <= 0.15;
    });
    var tKey, sKey;
    if (low) { tKey = 'nudgeLowT'; sKey = 'nudgeLowS'; }
    else if (tier === 'free') { tKey = 'nudgeGetT'; sKey = 'nudgeGetS'; }
    else return '';
    return '<div class="sd-nudge"><div class="sd-nudge-main">' +
        '<div class="sd-nudge-t">' + _sdBl(tKey) + '</div>' +
        '<div class="sd-nudge-s">' + _sdBl(sKey) + '</div></div>' +
        '<button type="button" class="sd-btn primary" data-sd-cta="upgrade">' + _sdBl('upgrade') + '</button>' +
      '</div>';
  }

  // draw-on-reveal: start every meter fill at 0, then paint targets next frame so the
  // width transition runs each time the Usage tab is shown.
  function _sdAnimateMeters() {
    if (!_sdOverlay) return;
    var fills = _sdOverlay.querySelectorAll('#sd-sect-usage .sd-meter-fill');
    if (!fills.length) return;
    fills.forEach(function (f) { f.style.width = '0'; });
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      fills.forEach(function (f) { f.style.width = (f.getAttribute('data-pct') || '0') + '%'; });
    }); });
  }

  // Fetch GET /api/brain/me (same-origin on mastermind-x.com, else MM_API), cache by uid,
  // re-render once on arrival. Mirrors _sdLoadPlan's auth + host logic.
  function _sdLoadUsage(u) {
    var uid = (u && u.id) || null;
    if (!uid) return;
    if (_sdUsage && _sdUsageFor === uid) return;
    if (_sdUsageBusy) return;
    _sdUsageBusy = true; _sdUsageErr = false;
    var base = /(^|\.)mastermind-x\.com$/i.test(location.hostname || '') ? '' : (window.MM_API || '');
    getSupabaseClient().then(function (sb) { return sb ? sb.auth.getSession() : null; })
      .then(function (res) {
        var tok = res && res.data && res.data.session && res.data.session.access_token;
        if (!tok) throw new Error('no-session');
        return fetch(base + '/api/brain/me', { headers: { Authorization: 'Bearer ' + tok } });
      })
      .then(function (r) { if (!r || !r.ok) throw new Error('usage-' + (r && r.status)); return r.json(); })
      .then(function (j) { _sdUsageBusy = false; _sdUsage = j || {}; _sdUsageFor = uid; if (_sdBuilt) _renderSDash(); })
      .catch(function () {
        _sdUsageBusy = false; _sdUsageErr = true;
        if (_sdBuilt && _sdSect === 'usage') _renderSDUsage(_sdAuthState(), _curUser || {});
      });
  }

  /* ---- section wiring ----------------------------------------------------- */
  function _sdMsg(id, text, kind) {
    var m = document.getElementById(id); if (!m) return;
    if (!text) { m.className = 'sd-msg'; m.textContent = ''; return; }
    m.textContent = text; m.className = 'sd-msg show ' + (kind || 'err');
  }
  function _sdSetBusy(btn, on, label) {
    if (!btn) return;
    if (on) { btn._sdLbl = btn.innerHTML; btn.disabled = true; if (label) btn.textContent = label; }
    else { btn.disabled = false; if (btn._sdLbl != null) btn.innerHTML = btn._sdLbl; }
  }
  // shared CTA + sign-out wiring across sections.
  // Sign-in / create-account open the LANDING-NATIVE onboarding sheet IN PLACE on
  // whatever www page the user is on (operator escalation 2026-07-23: auth must
  // exist on mastermind-x.com — never bounce to app.*). onboard.js is lazy-loaded
  // once and exposes window.MMOnboard; it self-provisions its CSS/fonts. Fallback
  // (script unreachable): navigate to the landing with the param — index.html
  // always carries the sheet.
  function _mmOpenOnboard(mode) {
    // whitelist: signin (default) · signup · upgrade (post-login monetization sheet)
    var m = (mode === 'signup') ? 'signup' : (mode === 'upgrade') ? 'upgrade' : 'signin';
    if (window.MMOnboard && window.MMOnboard.open) { window.MMOnboard.open(m); return; }
    var pfx = _mmSharedAssetRoot;
    if (window.__mmOnboardLoading) return;    // second click while loading — first one will open
    window.__mmOnboardLoading = true;
    var s = document.createElement('script');
    s.src = pfx + 'onboard.js'; s.defer = true;
    var fbQ = (m === 'signup') ? 'signup=1' : (m === 'upgrade') ? 'upgrade=1' : 'signin=1';
    var fallback = function () { location.href = pfx + 'index.html?' + fbQ; };
    var t = setTimeout(function () { if (!window.MMOnboard) fallback(); }, 4000);
    s.onload = function () {
      clearTimeout(t); window.__mmOnboardLoading = false;
      if (window.MMOnboard && window.MMOnboard.open) window.MMOnboard.open(m); else fallback();
    };
    s.onerror = function () { clearTimeout(t); window.__mmOnboardLoading = false; fallback(); };
    (document.head || document.documentElement).appendChild(s);
  }
  function _sdWireCta(host) {
    host.querySelectorAll('[data-sd-cta]').forEach(function (b) {
      b.addEventListener('click', function () {
        var mode = b.getAttribute('data-sd-cta');   // signup · signin · upgrade
        _closeSDash();
        _mmOpenOnboard(mode === 'signup' ? 'signup' : mode === 'upgrade' ? 'upgrade' : 'signin');
      });
    });
    var som = host.querySelector('#sd-signout-m');
    if (som) som.addEventListener('click', function () { if (window.MDXAuth) window.MDXAuth.signOut(); });
  }

  /* ---- plan block (tier + status chip + prorated upgrade) ----------------- */
  // The set of tiers that already have everything an upgrade would buy — no CTA shown.
  function _sdTierLabel(tier) {
    if (tier === 'pro' || tier === 'unlimited') return _sdL('tierPro');
    if (tier === 'insider') return _sdL('tierInsider');
    return _sdL('tierFree');
  }
  // status chip text for a plan payload; '' when nothing meaningful to show (free/none).
  function _sdPlanChip(p) {
    var status = p.status || 'none';
    var cpe = p.current_period_end || null;
    var when = cpe ? _sdDate(cpe) : '';
    // comp / uncapped grant with no period end = lifetime.
    if ((p.tier === 'unlimited' || p.source === 'comp') && !cpe && status !== 'canceled') {
      return '<span class="sd-plan-chip live">' + _escHtml(_sdL('planLifetime')) + '</span>';
    }
    if (status === 'trialing') {
      return '<span class="sd-plan-chip trial">' + _escHtml(_sdL('planTrialUntil')) +
        (when ? ' ' + _escHtml(when) : '') + '</span>';
    }
    if (status === 'active') {
      return '<span class="sd-plan-chip live">' + _escHtml(_sdL('planRenews')) +
        (when ? ' ' + _escHtml(when) : '') + '</span>';
    }
    if (status === 'canceled') {
      // A canceled row still inside its paid period shows the end date; past it, just "Expired".
      var future = cpe && (new Date(cpe).getTime() > Date.now());
      return '<span class="sd-plan-chip warn">' +
        _escHtml(future ? _sdL('planExpires') + (when ? ' ' + when : '') : _sdL('planExpired')) + '</span>';
    }
    return '';
  }
  function _sdPlanHTML() {
    // Cold cache → a quiet loading row; _wireSDAccount fills it in from /api/me.
    if (!_sdPlan) {
      return '<div class="sd-group sd-plan" id="sd-plan-grp">' +
          '<span class="sd-group-t">' + _sdBl('plan') + '</span>' +
          '<div class="sd-row"><div class="sd-row-line">' +
            '<span class="sd-row-main"><span class="sd-row-lbl sd-muted">' + _sdBl('planLoading') + '</span></span>' +
          '</div></div>' +
        '</div>';
    }
    var p = _sdPlan;
    var tier = p.tier || 'free';
    var paid = tier !== 'free';
    var chip = _sdPlanChip(p);
    var interval = p.interval || null;
    // Every upgrade lane lives in the one onboard sheet (MMOnboard 'upgrade'), which
    // reads /api/me and shows the tier-correct lanes + the trial/prorate confirm.
    // Nothing left to buy ONLY at the very top (Pro annual / unlimited). Everyone else
    // gets a button — including a Pro MONTHLY subscriber who can still switch to annual
    // for the ~30% discount, and trial-monthly users (their trial continues; billing
    // switches to annual when it ends). Label mirrors onboard.js savePct (locked pricing).
    var top = (tier === 'unlimited') || (tier === 'pro' && interval === 'annual');
    var cta = '';
    if (!top) {
      // Insider (any interval) → lead with the Pro upgrade (the recommended move);
      // Pro monthly → the annual switch. Free → choose a plan.
      var lblKey = !paid ? 'choosePlan'
                 : (tier === 'insider') ? 'upgradePro'
                 : 'switchAnnual';
      cta = '<div class="sd-plan-cta">' +
          '<button type="button" class="sd-btn primary" data-sd-cta="upgrade" id="sd-up-btn">' + _sdBl(lblKey) + '</button>' +
        '</div>';
    }
    return '<div class="sd-group sd-plan" id="sd-plan-grp">' +
        '<span class="sd-group-t">' + _sdBl('plan') + '</span>' +
        '<div class="sd-row"><div class="sd-row-line">' +
          '<span class="sd-row-main"><span class="sd-row-lbl">' + _sdBl('plan') + '</span></span>' +
          '<span class="sd-row-val strong sd-plan-tier">' + _escHtml(_sdTierLabel(tier)) + '</span>' +
          (chip || '') +
        '</div></div>' +
        cta +
      '</div>';
  }
  // Fetch /api/me with the Supabase bearer, cache by user id, re-render once on arrival.
  function _sdLoadPlan(u) {
    var uid = (u && u.id) || null;
    if (!uid) return;
    if (_sdPlan && _sdPlanFor === uid) return;   // already have this user's plan
    if (_sdPlanBusy) return;                       // a fetch is in flight
    _sdPlanBusy = true;
    // /api/me is served by the SAME origin (macro-api behind Caddy) on every
    // mastermind-x.com host. window.MM_API points cross-subdomain to app. for other
    // consumers, but app./api/me sends NO Access-Control-Allow-Origin → the browser
    // silently blocked this read and the plan hung forever on "Loading your plan…".
    // Talk same-origin here (guests/off-site keep the MM_API base).
    var base = /(^|\.)mastermind-x\.com$/i.test(location.hostname || '') ? '' : (window.MM_API || '');
    getSupabaseClient().then(function (sb) {
      return sb ? sb.auth.getSession() : null;
    }).then(function (res) {
      var tok = res && res.data && res.data.session && res.data.session.access_token;
      if (!tok) throw new Error('no-session');
      return fetch(base + '/api/me', { headers: { Authorization: 'Bearer ' + tok } });
    }).then(function (r) {
      if (!r || !r.ok) throw new Error('me-' + (r && r.status));
      return r.json();
    }).then(function (j) {
      _sdPlanBusy = false;
      _sdPlan = j || {}; _sdPlanFor = uid;
      if (_sdBuilt) _renderSDash();               // repaint with the real plan
    }).catch(function () {
      _sdPlanBusy = false;                          // leave the loading row; a later render retries
    });
  }
  // (Upgrade POST moved into the onboard 'upgrade' sheet — see onboard.js doUpgrade.
  //  The dashboard's plan CTA now opens that sheet via data-sd-cta="upgrade".)

  function _wireSDAccount(host, state, u) {
    _sdWireCta(host);
    if (state !== 'in') return;

    // ---- plan: load it if cold. The upgrade CTA (data-sd-cta="upgrade") is wired
    //      by _sdWireCta → _mmOpenOnboard('upgrade'); every lane lives in that sheet. ----
    _sdLoadPlan(u);

    // inline-edit open/cancel
    host.querySelectorAll('[data-sd-edit]').forEach(function (b) {
      b.addEventListener('click', function () {
        var row = b.closest('.sd-row'); if (!row) return;
        row.classList.add('editing');
        var inp = row.querySelector('input'); if (inp) inp.focus();
      });
    });
    host.querySelectorAll('[data-sd-cancel]').forEach(function (b) {
      b.addEventListener('click', function () {
        var row = b.closest('.sd-row'); if (!row) return;
        row.classList.remove('editing');
        var kind = b.getAttribute('data-sd-cancel');
        _sdMsg('sd-' + kind + '-msg', '');
        if (kind === 'pw') { var p1 = document.getElementById('sd-pw-in'), p2 = document.getElementById('sd-pw2-in'); if (p1) p1.value = ''; if (p2) p2.value = ''; }
        if (kind === 'email') { var e = document.getElementById('sd-email-in'); if (e) e.value = ''; }
      });
    });

    // ---- display name (updateUser data.display_name) ----
    var nameSave = document.getElementById('sd-name-save');
    if (nameSave) nameSave.addEventListener('click', function () {
      var inp = document.getElementById('sd-name-in');
      var val = (inp && inp.value || '').trim();
      _sdMsg('sd-name-msg', ''); _sdSetBusy(nameSave, true, _sdL('saving'));
      getSupabaseClient().then(function (sb) {
        if (!sb) throw new Error('no-client');
        return sb.auth.updateUser({ data: { display_name: val } });
      }).then(function (res) {
        _sdSetBusy(nameSave, false);
        if (res && res.error) throw res.error;
        if (_curUser) { _curUser.user_metadata = _curUser.user_metadata || {}; _curUser.user_metadata.display_name = val; }
        _renderSDash();   // reflect new name in ID card + rail
      }).catch(function (err) {
        _sdSetBusy(nameSave, false);
        _sdMsg('sd-name-msg', (err && err.message) || _sdL('errGen'), 'err');
      });
    });

    // ---- change email (updateUser email) ----
    var emailSave = document.getElementById('sd-email-save');
    if (emailSave) emailSave.addEventListener('click', function () {
      var inp = document.getElementById('sd-email-in');
      var val = (inp && inp.value || '').trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) { _sdMsg('sd-email-msg', _sdL('validEmail'), 'err'); return; }
      _sdMsg('sd-email-msg', ''); _sdSetBusy(emailSave, true, _sdL('saving'));
      getSupabaseClient().then(function (sb) {
        if (!sb) throw new Error('no-client');
        return sb.auth.updateUser({ email: val });
      }).then(function (res) {
        _sdSetBusy(emailSave, false);
        if (res && res.error) throw res.error;
        _sdMsg('sd-email-msg', _sdL('emailSent'), 'ok');
        if (inp) inp.value = '';
      }).catch(function (err) {
        _sdSetBusy(emailSave, false);
        _sdMsg('sd-email-msg', (err && err.message) || _sdL('errGen'), 'err');
      });
    });

    // ---- change password (>=8 + match) ----
    var pwSave = document.getElementById('sd-pw-save');
    if (pwSave) pwSave.addEventListener('click', function () {
      var p1El = document.getElementById('sd-pw-in'), p2El = document.getElementById('sd-pw2-in');
      var p1 = (p1El && p1El.value) || '', p2 = (p2El && p2El.value) || '';
      if (p1.length < 8) { _sdMsg('sd-pw-msg', _sdL('pwShort'), 'err'); return; }
      if (p1 !== p2) { _sdMsg('sd-pw-msg', _sdL('pwMismatch'), 'err'); return; }
      _sdMsg('sd-pw-msg', ''); _sdSetBusy(pwSave, true, _sdL('saving'));
      getSupabaseClient().then(function (sb) {
        if (!sb) throw new Error('no-client');
        return sb.auth.updateUser({ password: p1 });
      }).then(function (res) {
        _sdSetBusy(pwSave, false);
        if (res && res.error) throw res.error;
        _sdMsg('sd-pw-msg', _sdL('pwOk'), 'ok');
        if (p1El) p1El.value = ''; if (p2El) p2El.value = '';
        setTimeout(function () {
          var row = document.getElementById('sd-row-pw');
          if (row) row.classList.remove('editing');
          _sdMsg('sd-pw-msg', '');
        }, 1200);
      }).catch(function (err) {
        _sdSetBusy(pwSave, false);
        _sdMsg('sd-pw-msg', (err && err.message) || _sdL('errGen'), 'err');
      });
    });

    // ---- copy user ID (clipboard + execCommand fallback) ----
    var copyBtn = document.getElementById('sd-copy-uid');
    if (copyBtn) copyBtn.addEventListener('click', function () {
      var uid = copyBtn.getAttribute('data-uid') || '';
      var flip = function () {
        clearTimeout(_sdCopyTimer);
        copyBtn.innerHTML = _sdBl('copied');
        _sdCopyTimer = setTimeout(function () { copyBtn.innerHTML = _sdBl('copy'); }, 1200);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(uid).then(flip).catch(function () { _sdCopyExec(uid, flip); });
      } else { _sdCopyExec(uid, flip); }
    });
  }
  function _sdCopyExec(text, done) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.focus(); ta.select();
      document.execCommand('copy'); document.body.removeChild(ta);
      if (done) done();
    } catch (e) {}
  }

  function _wireSDPrefs(host) {
    host.querySelectorAll('[data-sd-theme]').forEach(function (b) {
      b.addEventListener('click', function () {
        var t = b.getAttribute('data-sd-theme');
        if (t === 'auto') setThemeAuto(); else setTheme(t);
        // active state syncs via the themechange listener (_sdSyncThemeSeg)
      });
    });
    host.querySelectorAll('[data-sd-lang]').forEach(function (b) {
      b.addEventListener('click', function () { setLang(b.getAttribute('data-sd-lang')); });
    });
    // desk chips — toggle in place (never re-render the section: that would
    // replay the entrance animation and drop the scroll position on every tap)
    var msg = host.querySelector('#sd-desk-msg');
    host.querySelectorAll('[data-sd-pref]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (!_sdDesk) _sdLoadDesk();
        var group = b.getAttribute('data-sd-pref'), val = b.getAttribute('data-val');
        var arr = _sdDesk[group] || (_sdDesk[group] = []);
        var i = arr.indexOf(val);
        if (i === -1) arr.push(val); else arr.splice(i, 1);
        b.setAttribute('aria-pressed', i === -1 ? 'true' : 'false');
        _sdSaveDesk(msg);
      });
    });
  }
  function _wireSDSync(host) { _sdWireCta(host); }

  // sync the Appearance segment active state (mirrors _syncThemeSegNow)
  function _sdSyncThemeSeg() {
    if (!_sdOverlay) return;
    var seg = _sdOverlay.querySelector('#sd-theme-seg'); if (!seg) return;
    var isAuto = false; try { isAuto = localStorage.getItem('themeAuto') === '1'; } catch (e) {}
    var cur = curTheme();
    seg.querySelectorAll('.sd-seg-b').forEach(function (b) {
      var t = b.getAttribute('data-sd-theme');
      var on = (t === 'auto') ? isAuto : (!isAuto && cur === t);
      b.classList.toggle('active', on);
    });
    // language segment reflects current lang too
    var lseg = _sdOverlay.querySelector('#sd-lang-seg');
    if (lseg) lseg.querySelectorAll('.sd-seg-b').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-sd-lang') === curLang());
    });
  }

  // Live prices are always on now (the toggle was removed); heal any stored pause.
  try { localStorage.removeItem('liveOff'); } catch (e) {}

  /* ---- open / close ------------------------------------------------------- */
  function _openSDash(section) {
    _buildSDash();
    _renderSDash();
    // pick the section: honour the request, but default account->prefs when auth off
    var want = section || (_curUser ? 'account' : 'prefs');
    if (want === 'account' && !_authEnabled) want = 'prefs';
    _sdShow(want);
    _sdLastFocus = document.activeElement;
    document.documentElement.classList.add('auth-lock');
    // re-toggle .open so the one-shot laser sweep re-runs each open
    _sdOverlay.classList.remove('open');
    // force reflow so removing+adding .open restarts the animation
    void _sdOverlay.offsetWidth;
    _sdOverlay.classList.add('open');
    _sdRelabelAria();
    // focus the active rail tab for keyboard users
    setTimeout(function () {
      var t = _sdOverlay.querySelector('.sd-nav-b.active') || _sdOverlay.querySelector('.sd-nav-b');
      if (t) { try { t.focus({ preventScroll: true }); } catch (e) { t.focus(); } }
    }, 90);
  }
  function _closeSDash() {
    if (!_sdOverlay) return;
    _sdOverlay.classList.remove('open');
    document.documentElement.classList.remove('auth-lock');
    clearTimeout(_sdCopyTimer);
    // restoring focus into .nav-settings would re-reveal the gear popover via
    // its :focus-within CSS — for those openers, skip the restore entirely
    if (_sdLastFocus && _sdLastFocus.focus &&
        !(_sdLastFocus.closest && _sdLastFocus.closest('.nav-settings'))) {
      try { _sdLastFocus.focus(); } catch (e) {}
    }
  }
  // public API — the gear popover's entry points drive this
  window.MMSettings = { open: function (section) { _openSDash(section); }, close: _closeSDash };

  /* ===========================================================================
     ACCOUNT PANEL — "page 2" inside the settings popover.
     Opens when a real Supabase signed-in user clicks "Manage account & sync ›".
     Uses supabase.auth.updateUser() directly; no external broker needed.
     =========================================================================*/

  /* ---- preference sync via user_metadata.prefs ----------------------------
     Fired on sign-in (apply server prefs) and on theme/lang change (save back).
     Guard: _prefSyncing flag prevents apply→save loops. */
  var _prefSyncing = false, _prefSaveTimer = null;

  function _applyServerPrefs(user) {
    if (!user) return;
    var meta = user.user_metadata || {};
    var prefs = meta.prefs;
    if (!prefs) return;
    _prefSyncing = true;
    try {
      if (prefs.theme && (prefs.theme === 'light' || prefs.theme === 'dark') && prefs.theme !== curTheme()) {
        setTheme(prefs.theme);
      }
      if (prefs.themeAuto && prefs.themeAuto === '1') {
        setThemeAuto();
      }
      var lg = docEl.getAttribute('data-lang') || 'en';
      if (prefs.lang && (prefs.lang === 'en' || prefs.lang === 'zh') && prefs.lang !== lg) {
        setLang(prefs.lang);
      }
    } catch (e) {}
    _prefSyncing = false;
  }

  function _savePrefToServer() {
    if (_prefSyncing || !_curUser || !_authEnabled) return;
    clearTimeout(_prefSaveTimer);
    _prefSaveTimer = setTimeout(function () {
      var prefs = {};
      try { prefs.theme = localStorage.getItem('theme') || curTheme(); } catch (e) { prefs.theme = curTheme(); }
      try { prefs.themeAuto = localStorage.getItem('themeAuto') || '0'; } catch (e) { prefs.themeAuto = '0'; }
      prefs.lang = curLang();
      getSupabaseClient().then(function (sb) {
        if (!sb || !_curUser) return;
        return sb.auth.updateUser({ data: { prefs: prefs } });
      }).catch(function () {});
    }, 800);
  }

  /* Hook into theme/lang events — wired once in initSettings() */
  var _prefHooked = false;
  function _hookPrefSync() {
    if (_prefHooked) return;
    _prefHooked = true;
    document.addEventListener('themechange', function () { _savePrefToServer(); });
    document.addEventListener('langchange', function () { _savePrefToServer(); });
  }

  /* (The old "page 2" account panel state + ACCT_L labels were removed — account
     management now lives in the settings dashboard (SD_L / _renderSDash above).) */
  function _escHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var SET_L = {
    title:   ['Settings', '设置'],
    sub:     ['Personalize your workspace', '个性化你的工作区'],
    prefs:   ['Preferences', '偏好设置'],
    theme:   ['Appearance', '外观'],
    lang:    ['Language', '语言'],
    account: ['Account', '账户'],
    soon:    ['Soon', '即将推出'],
    acctD:   ['Sign in to sync your watchlists, alerts and settings across devices.',
              '登录即可在各设备间同步自选、提醒与设置。'],
    signin:  ['Sign in', '登录'],
    signup:  ['Create account', '注册'],
    signedin:['Manage account & sync ›', '管理账户与同步 ›'],
    signout: ['Sign out', '退出'],
    close:   ['Close settings', '关闭设置'],
    expand:  ['Open full settings', '打开完整设置'],
    // Feature 5: three-way theme segment labels
    themeLight: ['Light', '浅色'],
    themeAuto:  ['Auto', '自动'],
    themeDark:  ['Dark', '深色'],
    fxOn:    ['On', '开'],
    fxOff:   ['Off', '关']
  };
  var SETTINGS_CSS = [
    /* two-row nav: the menu takes the whole first row on its own line; the global
       search + the Mastermind / Terminal / GEAR cluster sit together on the second
       row. Injected here — not only in theme.css — so the self-contained vector /
       forex / bonds / commodities family (which never loads theme.css) gets the
       exact same two-row bar live, no rebuild, same pattern as the mobile-nav CSS
       above. >=1260px only; the <=1259px collapse (flex + has-nav-toggle) overrides. */
    '.site-nav .nav-links{grid-column:1 / -1;grid-row:1}',
    '.site-nav .nav-search{grid-column:1;grid-row:2;max-width:480px}',
    '.site-nav .nav-ctrls{grid-column:2;grid-row:2;justify-self:end;align-self:center;margin-top:0}',
    /* the GEAR trigger + its anchored dropdown. The panel is position:absolute inside
       a relative .nav-settings wrapper (mirrors .nav-dd-menu), so it opens right under
       the gear — no trip to screen-centre — and follows it on scroll. No scrim;
       click-outside / Esc / a second click on the gear closes it. */
    '.nav-settings{position:relative;display:inline-flex;flex:none}',
    '.nav-settings-btn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;padding:0;flex:none;cursor:pointer;border-radius:50%;border:1px solid var(--line,var(--grid));background:var(--panel2,var(--card));color:var(--text,var(--ink));transition:border-color .2s,color .2s,background .2s,transform .16s ease,box-shadow .18s ease;-webkit-tap-highlight-color:transparent}',
    '.nav-settings-btn:hover{border-color:var(--link,var(--blue));color:var(--link,var(--blue));transform:translateY(-1px);box-shadow:0 5px 14px -6px color-mix(in srgb,var(--link,var(--blue)) 45%,transparent)}',
    '.nav-settings-btn:active{transform:translateY(0);box-shadow:none}',
    '.nav-settings-btn[aria-expanded="true"]{border-color:var(--link,var(--blue));color:var(--link,var(--blue));background:color-mix(in srgb,var(--link,var(--blue)) 13%,var(--panel2,var(--card)))}',
    '.nav-settings-btn svg{width:18px;height:18px;display:block;transition:transform .5s cubic-bezier(.34,1.3,.5,1)}',
    '.nav-settings-btn:hover svg,.nav-settings-btn[aria-expanded="true"] svg{transform:rotate(70deg)}',
    /* frosted glass — matches the --glass-* dropdown system in theme.css; written
       inline (with --x,--y fallbacks) so the self-contained vector family, which
       never loads theme.css, gets the identical glass on its gear popover too. */
    '.settings-pop{position:absolute;top:calc(100% + 9px);right:0;z-index:100000;width:min(340px,calc(100vw - 20px));box-sizing:border-box;background:color-mix(in srgb,var(--panel,var(--card)) 76%,transparent);-webkit-backdrop-filter:saturate(180%) blur(22px);backdrop-filter:saturate(180%) blur(22px);border:1px solid color-mix(in srgb,var(--text,#e7ecf6) 16%,transparent);border-radius:16px;box-shadow:0 24px 64px -18px rgba(3,7,18,.62),0 8px 22px -10px rgba(3,7,18,.4),inset 0 1px 0 color-mix(in srgb,var(--text,#fff) 9%,transparent);padding:13px;transform-origin:top right;opacity:0;visibility:hidden;pointer-events:none;transform:translateY(-8px) scale(.97);transition:opacity .16s ease,transform .2s cubic-bezier(.32,1.3,.5,1),visibility 0s linear .2s;font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif}',
    '.settings-pop.open{opacity:1;visibility:visible;pointer-events:auto;transform:none;transition:opacity .16s ease,transform .2s cubic-bezier(.32,1.3,.5,1),visibility 0s}',
    /* HOVER DROPDOWN (desktop): the gear now opens on hover like the top-nav .nav-dd
       menus — hovering it (or keyboard-focusing into the wrapper) reveals the panel
       with the SAME spring as the click path, and a transparent ::after bridges the
       9px gap so the cursor can travel gear->panel without it closing. hover/fine
       pointers only; touch keeps the JS click toggle (where the close x still shows). */
    '@media (hover:hover) and (pointer:fine){',
    '.nav-settings::after{content:"";position:absolute;top:100%;right:0;width:100%;height:11px}',
    '.nav-settings:hover .settings-pop,.nav-settings:focus-within .settings-pop{opacity:1;visibility:visible;pointer-events:auto;transform:none;transition:opacity .16s ease,transform .2s cubic-bezier(.32,1.3,.5,1),visibility 0s}',
    '.nav-settings:hover .nav-settings-btn,.nav-settings:focus-within .nav-settings-btn{border-color:var(--link,var(--blue));color:var(--link,var(--blue));background:color-mix(in srgb,var(--link,var(--blue)) 13%,var(--panel2,var(--card)))}',
    '.nav-settings:hover .nav-settings-btn svg,.nav-settings:focus-within .nav-settings-btn svg{transform:rotate(70deg)}',
    '.nav-settings .settings-close{display:none}',
    '}',
    '.settings-head{display:flex;align-items:center;gap:8px;margin:0;padding:0 2px 2px}',
    '.settings-head h2{margin:0;padding:0;border:0;font-size:10.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;line-height:1.2;color:var(--muted,var(--ink-3))}',
    '.settings-close{width:24px;height:24px;border-radius:7px;border:1px solid transparent;background:transparent;color:var(--muted,var(--ink-3));cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:none;transition:background .18s,color .18s}',
    '.settings-close:hover{background:var(--panel2,var(--card));color:var(--text,var(--ink))}',
    '.settings-close svg{width:15px;height:15px}',
    '.settings-close:focus-visible{outline:2px solid var(--link,var(--blue));outline-offset:2px}',
    /* expand-to-dashboard button: sits at the header end, pushed right with the close */
    '.settings-expand{margin-left:auto;width:24px;height:24px;border-radius:7px;border:1px solid transparent;background:transparent;color:var(--muted,var(--ink-3));cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:none;transition:background .18s,color .18s}',
    '.settings-expand:hover{background:var(--panel2,var(--card));color:var(--link,var(--blue))}',
    '.settings-expand svg{width:15px;height:15px}',
    '.settings-expand:focus-visible{outline:2px solid var(--link,var(--blue));outline-offset:2px}',
    '.settings-sec{margin-top:9px}',
    '.settings-sec-t{display:flex;align-items:center;gap:8px;font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--muted,var(--ink-3));margin:0 0 7px;padding:0 2px}',
    '.settings-row{display:flex;align-items:center;gap:11px;padding:9px 11px;border-radius:11px;background:var(--panel2,var(--card));border:1px solid var(--line,var(--grid))}',
    '.settings-row+.settings-row{margin-top:7px}',
    '.settings-row .sr-ic{flex:none;color:var(--muted,var(--ink-3));display:inline-flex}',
    '.settings-row .sr-ic svg{width:18px;height:18px;display:block}',
    '.settings-row .sr-main{flex:1;min-width:0}',
    '.settings-row .sr-lbl{display:block;font-size:13px;font-weight:700;color:var(--text,var(--ink))}',
    '.settings-row .sr-desc{display:block;font-size:11px;color:var(--muted,var(--ink-3));margin-top:1px}',
    '.settings-row .sr-ctrl{flex:none;display:inline-flex;align-items:center}',
    /* relocated toggles — full styling, scoped to the popover so it renders the SAME
       on macro pages (theme.css present) and vector pages (theme.css absent) */
    '.settings-pop .theme-switch{width:56px;height:27px;border-radius:999px;background:var(--bg,var(--card));border:1px solid var(--line,var(--grid));position:relative;cursor:pointer;padding:0;flex:none}',
    '.settings-pop .theme-switch .ic{position:absolute;top:50%;transform:translateY(-50%);font-size:10.5px;opacity:.5;line-height:1}',
    '.settings-pop .theme-switch .ic.sun{right:8px}.settings-pop .theme-switch .ic.moon{left:8px}',
    '.settings-pop .theme-switch .knob{position:absolute;top:2px;left:2px;width:22px;height:22px;border-radius:50%;background:#e8c15a;display:flex;align-items:center;justify-content:center;font-size:11px;box-shadow:0 2px 5px rgba(0,0,0,.3);transition:transform .34s cubic-bezier(.34,1.45,.5,1),background .3s}',
    '.settings-pop .theme-switch .knob::before{content:"🌙"}',
    'html[data-theme="light"] .settings-pop .theme-switch .knob{transform:translateX(29px);background:#285fff}',
    'html[data-theme="light"] .settings-pop .theme-switch .knob::before{content:"☀️"}',
    '.settings-pop .lang-toggle{display:inline-flex;position:relative;background:var(--bg,var(--card));border:1px solid var(--line,var(--grid));border-radius:999px;padding:3px;flex:none;cursor:pointer}',
    '.settings-pop .lang-toggle .pill{position:absolute;top:3px;left:3px;width:calc(50% - 3px);height:calc(100% - 6px);border-radius:999px;background:var(--link,var(--blue));transition:transform .34s cubic-bezier(.34,1.4,.5,1)}',
    'html[data-lang="zh"] .settings-pop .lang-toggle .pill{transform:translateX(100%)}',
    '.settings-pop .lang-toggle .opt{position:relative;z-index:1;min-width:30px;text-align:center;padding:3px 11px;font-size:11.5px;font-weight:600;color:var(--muted,var(--ink-3));transition:color .25s;user-select:none}',
    'html:not([data-lang="zh"]) .settings-pop .lang-toggle .en-opt{color:#fff}',
    'html[data-lang="zh"] .settings-pop .lang-toggle .zh-opt{color:#fff}',
    '.settings-soon{font-size:9px;font-weight:800;letter-spacing:.05em;padding:2px 7px;border-radius:999px;background:color-mix(in srgb,var(--link,var(--blue)) 16%,transparent);color:var(--link,var(--blue));text-transform:uppercase}',
    '.settings-acct{padding:11px;display:block}',
    '.settings-acct .sa-d{font-size:11.5px;color:var(--muted,var(--ink-3));line-height:1.5;margin:0 0 9px}',
    '.settings-acct .sa-btns{display:flex;gap:8px}',
    '.settings-acct .sa-btn{flex:1;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 10px;border-radius:10px;font-size:12.5px;font-weight:700;cursor:not-allowed;border:1px solid var(--line,var(--grid));font-family:inherit}',
    '.settings-acct .sa-btn .sr-ic{color:inherit}',
    '.settings-acct .sa-btn.ghost{background:transparent;color:var(--text,var(--ink))}',
    '.settings-acct .sa-btn.solid{background:var(--link,var(--blue));border-color:var(--link,var(--blue));color:#fff;opacity:.92}',
    /* account section is LIVE now (was a disabled placeholder): buttons click, and
       a signed-in row replaces them. */
    '.settings-acct .sa-btn{cursor:pointer}',
    '.settings-acct .sa-btn.ghost:hover{border-color:var(--link,var(--blue));color:var(--link,var(--blue))}',
    '.settings-acct .sa-btn.solid:hover{filter:brightness(1.07);opacity:1}',
    '.settings-acct-in{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:11px;background:var(--panel2,var(--card));border:1px solid var(--line,var(--grid))}',
    '.settings-acct-in .sa-avatar{flex:none;width:32px;height:32px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--link,var(--blue,#4f8cff)),color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 55%,#9b5cff))}',
    '.settings-acct-in .sr-main{flex:1;min-width:0}',
    '.settings-acct-in .sr-lbl{display:block;font-size:13px;font-weight:700;color:var(--text,var(--ink));overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.settings-acct-in .sr-desc{display:block;font-size:11px;color:var(--muted,var(--ink-3));margin-top:1px}',
    '.settings-acct-in .sa-signout{flex:none;padding:7px 11px;border-radius:9px;border:1px solid var(--line,var(--grid));background:transparent;color:var(--text,var(--ink));font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;transition:border-color .18s,color .18s}',
    '.settings-acct-in .sa-signout:hover{border-color:var(--down,#ff5c6c);color:var(--down,#ff5c6c)}',
    '@media (prefers-reduced-motion:reduce){.settings-pop{transition:opacity .14s ease,visibility 0s linear .14s}.settings-pop.open,.nav-settings:hover .settings-pop,.nav-settings:focus-within .settings-pop{transition:opacity .14s ease}.nav-settings-btn:hover svg,.nav-settings-btn[aria-expanded="true"] svg,.nav-settings:hover .nav-settings-btn svg,.nav-settings:focus-within .nav-settings-btn svg{transform:none}}',
    /* ---- three-way theme segment + on/off toggle (shared by fx and live-prices) */
    '.set-theme-seg{display:inline-flex;background:var(--bg,var(--card));border:1px solid var(--line,var(--grid));border-radius:999px;padding:3px;gap:2px;flex:none}',
    '.set-seg-btn{padding:3px 10px;border:none;border-radius:999px;font-size:11.5px;font-weight:600;cursor:pointer;font-family:inherit;background:transparent;color:var(--muted,var(--ink-3));transition:background .2s,color .2s;white-space:nowrap}',
    '.set-seg-btn.active{background:var(--link,var(--blue));color:#fff}',
    '.set-seg-btn:hover:not(.active){background:color-mix(in srgb,var(--text,#fff) 9%,transparent);color:var(--text,var(--ink))}',
    '.set-seg-btn:focus-visible{outline:2px solid var(--link,var(--blue));outline-offset:2px}',
    /* on/off toggle button */
    '.set-toggle-btn{position:relative;width:44px;height:24px;border-radius:999px;border:1px solid var(--line,var(--grid));background:var(--bg,var(--card));cursor:pointer;padding:0;transition:background .25s,border-color .25s}',
    '.set-toggle-btn[aria-checked="true"]{background:var(--link,var(--blue));border-color:var(--link,var(--blue))}',
    '.set-toggle-knob{position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.25);transition:transform .25s cubic-bezier(.34,1.4,.5,1)}',
    '.set-toggle-btn[aria-checked="true"] .set-toggle-knob{transform:translateX(20px)}',
    '.set-toggle-btn:focus-visible{outline:2px solid var(--link,var(--blue));outline-offset:2px}'
    /* NB: the old "page 2" account panel (.set-acct-panel/.sap-*) was removed —
       account management now lives in the full settings dashboard (SDASH_CSS,
       sd-*), opened from the signed-in row + the header expand button. */
  ].join('');

  function setLabels(root) {
    var lg = curLang() === 'zh' ? 1 : 0;
    root.querySelectorAll('[data-set]').forEach(function (el) {
      var pair = SET_L[el.getAttribute('data-set')];
      if (pair) el.textContent = pair[lg];
    });
  }

  function initSettings() {
    if (document.getElementById('settings-pop')) return true;   // once
    var ts = document.querySelector('.theme-switch'), lt = document.querySelector('.lang-toggle');
    if (!ts && !lt) return false;   // legacy .theme-btn pages keep their own text controls
    // Where the gear lands: the nav control cluster on dashboard pages; otherwise
    // the header cluster that holds the toggles today (the landing hub's .hub-top).
    var nav = document.querySelector('.site-nav, .topbar');
    var ctrls = (nav && nav.querySelector('.nav-ctrls')) || (ts && ts.parentElement) || (lt && lt.parentElement);
    if (!ctrls) return false;

    if (!document.getElementById('settings-css')) {
      var st = document.createElement('style');
      st.id = 'settings-css'; st.textContent = SETTINGS_CSS;
      document.head.appendChild(st);
    }

    // .nav-settings wraps the gear + its dropdown so the panel anchors right under
    // the gear (position:absolute), opening with no trip to screen-centre.
    var wrap = document.createElement('div');
    wrap.className = 'nav-settings';

    var gear = document.createElement('button');
    gear.type = 'button'; gear.className = 'nav-settings-btn'; gear.id = 'settings-open';
    gear.setAttribute('aria-label', 'Settings');
    gear.setAttribute('aria-haspopup', 'true');
    gear.setAttribute('aria-expanded', 'false');
    gear.setAttribute('aria-controls', 'settings-pop');
    gear.innerHTML = SET_ICON.gear;

    var pop = document.createElement('div');
    pop.className = 'settings-pop'; pop.id = 'settings-pop';
    pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', 'Settings');
    pop.setAttribute('tabindex', '-1');
    pop.innerHTML =
      '<div class="settings-head">' +
        '<h2 data-set="title"></h2>' +
        '<button type="button" class="settings-expand" id="settings-expand" aria-label="Open full settings">' + SET_ICON.maximize + '</button>' +
        '<button type="button" class="settings-close" aria-label="Close settings">' + SET_ICON.x + '</button>' +
      '</div>' +
      '<div class="settings-sec">' +
        '<div class="settings-sec-t" data-set="prefs"></div>' +
        // Theme row — three-way segment: Light / Auto / Dark
        '<div class="settings-row">' +
          '<span class="sr-ic">' + SET_ICON.theme + '</span>' +
          '<span class="sr-main"><span class="sr-lbl" data-set="theme"></span></span>' +
          '<span class="sr-ctrl" id="set-theme-slot">' +
            '<div class="set-theme-seg" id="set-theme-seg" role="group" aria-label="Appearance">' +
              '<button type="button" class="set-seg-btn" id="set-theme-light" data-set="themeLight"></button>' +
              '<button type="button" class="set-seg-btn" id="set-theme-auto" data-set="themeAuto"></button>' +
              '<button type="button" class="set-seg-btn" id="set-theme-dark" data-set="themeDark"></button>' +
            '</div>' +
          '</span>' +
        '</div>' +
        // Lang row — lang-toggle relocated here
        '<div class="settings-row">' +
          '<span class="sr-ic">' + SET_ICON.lang + '</span>' +
          '<span class="sr-main"><span class="sr-lbl" data-set="lang"></span></span>' +
          '<span class="sr-ctrl" id="set-lang-slot"></span>' +
        '</div>' +
      '</div>' +
      '<div class="settings-sec" id="set-acct-sec">' +
        '<div class="settings-sec-t"><span data-set="account"></span></div>' +
        '<div class="settings-row settings-acct" id="set-acct-out" style="display:block">' +
          '<p class="sa-d" data-set="acctD"></p>' +
          '<div class="sa-btns">' +
            '<button type="button" class="sa-btn ghost" id="set-signin"><span class="sr-ic" style="display:inline-flex">' + SET_ICON.user + '</span><span data-set="signin"></span></button>' +
            '<button type="button" class="sa-btn solid" id="set-signup" data-set="signup"></button>' +
          '</div>' +
        '</div>' +
        '<div class="settings-acct-in" id="set-acct-in" style="display:none">' +
          '<span class="sa-avatar" id="set-avatar"></span>' +
          '<span class="sr-main"><span class="sr-lbl" id="set-email"></span><span class="sr-desc" data-set="signedin"></span></span>' +
          '<button type="button" class="sa-signout" id="set-signout" data-set="signout"></button>' +
        '</div>' +
      '</div>';

    wrap.appendChild(gear);
    wrap.appendChild(pop);
    ctrls.appendChild(wrap);   // gear + dropdown, pinned at the cluster's end

    // relocate the live lang-toggle into the popover (theme-switch no longer relocated —
    // the three-way segment above replaces it; hide the original toggle from the nav)
    if (ts) ts.style.display = 'none';    // replaced by the 3-way segment in the pane
    if (lt) pop.querySelector('#set-lang-slot').appendChild(lt);

    // keep the gear/popover/close ARIA labels localized too (the visible text is
    // handled by setLabels; these attributes otherwise stay English).
    function relabelSetAria() {
      var lg = curLang() === 'zh' ? 1 : 0;
      gear.setAttribute('aria-label', SET_L.title[lg]);
      pop.setAttribute('aria-label', SET_L.title[lg]);
      var cb = pop.querySelector('.settings-close'); if (cb) cb.setAttribute('aria-label', SET_L.close[lg]);
      var xb = pop.querySelector('.settings-expand'); if (xb) xb.setAttribute('aria-label', SET_L.expand[lg]);
    }
    setLabels(pop); relabelSetAria();
    document.addEventListener('langchange', function () { setLabels(pop); relabelSetAria(); });
    // MutationObserver on data-lang attribute: catches any code that sets the attribute
    // directly without dispatching the langchange event (defensive hardening).
    // Deduped: skips the relabel when the event path already handled it (uses a flag).
    var _muLangBusy = false;
    if (window.MutationObserver) {
      new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
          if (mutations[i].attributeName === 'data-lang') {
            if (_muLangBusy) return;
            _muLangBusy = true;
            // sync the WCAG lang attribute too — this observer exists precisely for
            // code paths that set data-lang without going through setLang()
            try { docEl.lang = docEl.getAttribute('data-lang') === 'zh' ? 'zh-CN' : 'en'; } catch (e) {}
            try { setLabels(pop); relabelSetAria(); } catch (e) {}
            _muLangBusy = false;
          }
        }
      }).observe(docEl, { attributes: true, attributeFilter: ['data-lang'] });
    }

    function isOpen() { return pop.classList.contains('open'); }
    function open() {
      if (isOpen()) return;
      pop.classList.add('open');
      gear.setAttribute('aria-expanded', 'true');
      pop.focus();
    }
    function close() {
      if (!isOpen()) return;
      pop.classList.remove('open');
      gear.setAttribute('aria-expanded', 'false');
    }
    gear.addEventListener('click', function () { isOpen() ? close() : open(); });
    pop.querySelector('.settings-close').addEventListener('click', function () { close(); gear.focus(); });
    // expand → open the full settings dashboard (Account when signed in, else Preferences)
    var expandBtn = pop.querySelector('.settings-expand');
    if (expandBtn) expandBtn.addEventListener('click', function () {
      close(); if (window.MMSettings) window.MMSettings.open(_curUser ? 'account' : 'prefs');
    });
    // no scrim: a click anywhere outside the gear + its dropdown closes it
    document.addEventListener('mousedown', function (e) { if (isOpen() && !wrap.contains(e.target)) close(); });
    document.addEventListener('keydown', function (e) {
      if (!isOpen() || e.key !== 'Escape') return;
      // account management now lives in the full settings dashboard (its own Esc
      // handler owns closing it); here Escape simply closes the popover.
      close(); gear.focus();
    });
    // Desktop also opens the panel on hover (pure CSS above). If a stray click set
    // .open, make sure leaving the gear + panel always closes it so it never stays
    // pinned under the cursor; touch (no hover) keeps the click / outside / Esc path.
    if (window.matchMedia && window.matchMedia('(hover:hover) and (pointer:fine)').matches) {
      wrap.addEventListener('mouseleave', close);
    }
    // Pane ARIA/keyboard: on focusin inside .nav-settings open the panel + sync aria-expanded
    // (CSS :focus-within also reveals on desktop, but JS .open keeps close/Esc/focus-restore
    // correct). On focusout leaving the entire wrap, close.
    wrap.addEventListener('focusin', function () {
      if (!isOpen()) { open(); }
    });
    wrap.addEventListener('focusout', function () {
      // relatedTarget may be null on blur-to-outside; defer one tick so activeElement settles
      setTimeout(function () {
        if (!wrap.contains(document.activeElement)) { close(); }
      }, 0);
    });

    // account section — live when Supabase is configured, else hidden entirely.
    var bSignin = pop.querySelector('#set-signin'), bSignup = pop.querySelector('#set-signup'),
        bSignout = pop.querySelector('#set-signout');
    if (_authEnabled) {
      if (bSignin) bSignin.addEventListener('click', function () { close(); _mmOpenOnboard('signin'); });
      if (bSignup) bSignup.addEventListener('click', function () { close(); _mmOpenOnboard('signup'); });
      if (bSignout) bSignout.addEventListener('click', function () { window.MDXAuth.signOut(); });

      /* ---- account management → the full settings dashboard -------------- */
      // The old "page 2" account panel was replaced by MMSettings (the sd-* dash).
      // Here we only keep the pref-sync hooks + wire the signed-in row to open it.

      // Hook: apply server prefs on sign-in (SIGNED_OUT re-renders the dash itself
      // via its own 'mdx-auth' listener — no panel to close here anymore).
      window.addEventListener('mdx-auth', function (e) {
        var detail = e && e.detail;
        if (detail && detail.event === 'SIGNED_IN' && detail.user) {
          _applyServerPrefs(detail.user);
        }
      });

      // Wire pref sync hooks (once per page)
      _hookPrefSync();

      // clicking the signed-in row opens the full settings dashboard on Account
      var mMain = pop.querySelector('#set-acct-in .sr-main');
      if (mMain) {
        mMain.style.cursor = 'pointer';
        mMain.setAttribute('role', 'button'); mMain.setAttribute('tabindex', '0');
        var _openMgr = function () { close(); if (window.MMSettings) window.MMSettings.open('account'); };
        mMain.addEventListener('click', _openMgr);
        mMain.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _openMgr(); } });
      }

      window.addEventListener('mdx-auth', _renderAcct);
      _renderAcct();
    } else {
      var sec = pop.querySelector('#set-acct-sec'); if (sec) sec.style.display = 'none';
    }

    // ---- Feature 5: wire the three-way theme segment -----------------------
    var _tLight = pop.querySelector('#set-theme-light'),
        _tAuto  = pop.querySelector('#set-theme-auto'),
        _tDark  = pop.querySelector('#set-theme-dark');
    function _syncThemeSegNow() {
      var isAuto = false;
      try { isAuto = localStorage.getItem('themeAuto') === '1'; } catch (e) {}
      var cur = curTheme();
      function _seg(el, on) {
        if (!el) return;
        el.classList.toggle('active', on);
        el.setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      _seg(_tLight, !isAuto && cur === 'light');
      _seg(_tAuto, isAuto);
      _seg(_tDark, !isAuto && cur === 'dark');
    }
    // Replace the placeholder with the real function now that the DOM is built
    _syncThemeSegment = _syncThemeSegNow;
    _syncThemeSegNow();  // initialize to current state
    if (_tLight) _tLight.addEventListener('click', function () { setTheme('light'); });
    if (_tAuto)  _tAuto.addEventListener('click', function () { setThemeAuto(); });
    if (_tDark)  _tDark.addEventListener('click', function () { setTheme('dark'); });
    // keep the segment in sync when themechange fires (e.g. from legacy toggleTheme)
    document.addEventListener('themechange', function () { _syncThemeSegNow(); });


    // ---- Feature 9: sign-in link wiring (hub-only, hub-signin element) -------
    function _initHubSignin() {
      var signinLink = document.getElementById('hub-signin');
      if (!signinLink || typeof window.MDXAuth === 'undefined') return;
      function _updateSigninLink(user) {
        // Hide when signed in (gear handles account); show when signed out.
        // The element ships with the [hidden] attribute — the property must be
        // cleared too (inline display:'' does not override the UA hidden rule).
        signinLink.hidden = !!user;
        signinLink.style.display = user ? 'none' : '';
        if (!user) {
          // label: Sign in / 登录 bilingual via span children
          signinLink.textContent = '';
          var en = document.createElement('span'); en.className = 'l-en'; en.textContent = 'Sign in';
          var zh = document.createElement('span'); zh.className = 'l-zh'; zh.textContent = '登录';
          signinLink.appendChild(en); signinLink.appendChild(zh);
        }
      }
      // subscribe to auth changes
      if (window.MDXAuth && typeof window.MDXAuth.onChange === 'function') {
        window.MDXAuth.onChange(function (user) { _updateSigninLink(user); });
      }
      // click: open the landing-native onboarding sheet IN PLACE (never app.*).
      signinLink.addEventListener('click', function (e) {
        e.preventDefault();
        _mmOpenOnboard('signin');
      });
      // initial state
      _updateSigninLink(window.MDXAuth.user ? window.MDXAuth.user() : null);
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _initHubSignin);
    } else { _initHubSignin(); }

    window.openSettings = open;
    return true;
  }

  /* ---- highlight the current page in the nav ------------------------------
     The link list is now one shared partial with no per-page `active` class,
     so we mark the matching link (and every dropdown that contains it) here by
     comparing filenames. Consistent on every page, no build-time plumbing, and
     correct for nested items (e.g. on commodities.html the Commodities sub AND
     the Other Assets parent both light up). */
  function initActiveNav() {
    var links = document.querySelector('.site-nav .nav-links, .topbar .nav-links');
    if (!links) return;
    var here = (location.pathname.split('/').pop() || '').toLowerCase() || 'index.html';
    links.querySelectorAll('a[href]').forEach(function (a) {
      var file = (a.getAttribute('href') || '').split('?')[0].split('#')[0].split('/').pop().toLowerCase();
      if (!file || file !== here) return;
      a.classList.add('active');
      var p = a.parentElement;
      while (p && p !== links) {
        if (p.classList && p.classList.contains('nav-dd')) {
          var trig = p.querySelector(':scope > a');
          if (trig) trig.classList.add('active');
        }
        p = p.parentElement;
      }
    });
  }

  /* ---- collapsible action lists (.lst-more button / .lst-collapse wrapper) — see the
     "Show more" block in theme.css. Delegated on document so it also handles lists injected
     after load (renderActNow / renderEntries write innerHTML at boot). The 7-on-wide /
     5-on-narrow row limit is pure CSS; this only flips the collapsed state + aria. */
  function initListCollapse() {
    if (window.__lstMoreBound) return;            // bind once
    window.__lstMoreBound = true;
    document.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.lst-more') : null;
      if (!btn) return;
      var wrap = btn.closest('.lst-wrap');
      var list = wrap && wrap.querySelector('.lst-collapse');
      if (!list) return;
      var nowCollapsed = list.classList.toggle('is-collapsed');
      btn.setAttribute('aria-expanded', nowCollapsed ? 'false' : 'true');
    });
  }

  /* ---- list overlay (.lst-wrap → "View all N" pill → modal) ------------------------
     Supersedes the in-flow expansion above for every .lst-wrap list: the .lst-more
     button is restyled into a quiet "View all N" pill and a click MOVES the live
     .lst-collapse node into a centered modal (custom JS scrollbar) instead of
     unfolding 30+ rows in place. Capture-phase handler outruns the legacy
     initListCollapse toggle, which stays untouched as the no-JS / failure fallback.
     The list node is returned to a placeholder on close, so page JS that owns those
     nodes (renderActNow re-renders, langchange rebuilds) keeps working; langchange
     force-closes the overlay first because some pages rebuild the source DOM. */
  function initListOverlay() {
    if (window.__lstOvlBound) return;
    window.__lstOvlBound = true;
    var ovl = null, homeMark = null, movedList = null, lastTrigger = null;
    var carried = [];   // [{node, mark}] — caveat siblings moved along with the list
    // Siblings of the list that must travel into the modal so their caveat stays attached
    // to the expanded view (e.g. the china bottoming lane's "NOT a buy signal" disclaimer,
    // which ships on already-rendered pages — hence the literal class alongside the
    // generic opt-in attribute).
    var CARRY_SEL = ':scope > [data-ovl-carry], :scope > .anv2-bot-disc';

    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    }
    function bl(en, zh) {
      return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(zh) + '</span>';
    }

    // Title / subtitle / accent colour for the modal header. Templates can override via
    // data-ovl-title-en/-zh + data-ovl-accent on any ancestor; otherwise the nearest
    // heading is mined (dual-span aware) and its colour becomes the accent strip.
    function laneMeta(wrap) {
      var scope = wrap.closest('[data-ovl-title-en]');
      if (scope) {
        return { en: scope.getAttribute('data-ovl-title-en'),
                 zh: scope.getAttribute('data-ovl-title-zh') || scope.getAttribute('data-ovl-title-en'),
                 accent: scope.getAttribute('data-ovl-accent') || '', subEn: '', subZh: '' };
      }
      var lane = wrap.closest('.anv2-lane') || wrap.closest('.actcol') || wrap.closest('.panel') || wrap;
      var h = lane.querySelector('.anv2-lane-title, .acth-name, h2, h3, h4');
      var strip = function (s) { return (s || '').replace(/[（(]\d+[）)]/g, '').trim(); };
      var en = '', zh = '';
      if (h) {
        var eEn = h.querySelector('.l-en'), eZh = h.querySelector('.l-zh');
        en = strip(eEn ? eEn.textContent : h.textContent);
        zh = strip(eZh ? eZh.textContent : en);
      }
      var sub = lane.querySelector('.anv2-lane-sub, .acth-sub');
      var sEn = sub && sub.querySelector('.l-en'), sZh = sub && sub.querySelector('.l-zh');
      return { en: en || 'All items', zh: zh || '全部条目',
               accent: h ? window.getComputedStyle(h).color : '',
               subEn: sEn ? sEn.textContent.trim() : '', subZh: sZh ? sZh.textContent.trim() : '' };
    }

    function buildOverlay() {
      if (ovl) return ovl;
      ovl = document.createElement('div');
      ovl.className = 'lst-ovl';
      ovl.innerHTML =
        '<div class="lst-ovl-modal" role="dialog" aria-modal="true" tabindex="-1">'
        + '<div class="lst-ovl-hd"><div class="lst-ovl-title"><span class="lst-ovl-t"></span>'
        + '<span class="lst-ovl-count"></span><span class="lst-ovl-sub"></span></div>'
        + '<button type="button" class="lst-ovl-x" aria-label="Close">✕</button></div>'
        + '<div class="lst-ovl-bodywrap"><div class="lst-ovl-body"></div>'
        + '<div class="lst-ovl-sb" aria-hidden="true"><div class="lst-ovl-sb-thumb"></div></div></div>'
        + '<div class="lst-ovl-ft"><span class="lst-ovl-hint"></span><span class="lst-ovl-asof"></span></div>'
        + '</div>';
      document.body.appendChild(ovl);
      ovl.addEventListener('click', function (e) {
        if (e.target === ovl || (e.target.closest && e.target.closest('.lst-ovl-x'))) closeOverlay();
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && ovl.classList.contains('is-open')) closeOverlay();
      });
      // pages that rebuild their DOM on language toggle would strand the moved node
      document.addEventListener('langchange', function () {
        if (ovl.classList.contains('is-open')) closeOverlay();
      });
      wireScrollbar();
      return ovl;
    }

    function wireScrollbar() {
      var body = ovl.querySelector('.lst-ovl-body');
      var track = ovl.querySelector('.lst-ovl-sb');
      var thumb = ovl.querySelector('.lst-ovl-sb-thumb');
      var raf = 0;
      function sync() {
        raf = 0;
        var sh = body.scrollHeight, ch = body.clientHeight;
        if (sh <= ch + 1) { track.style.display = 'none'; return; }
        track.style.display = '';
        var h = Math.max(28, ch * ch / sh);
        thumb.style.height = h + 'px';
        thumb.style.transform =
          'translateY(' + (body.scrollTop / (sh - ch) * (track.clientHeight - h)) + 'px)';
      }
      function queue() { if (!raf) raf = requestAnimationFrame(sync); }
      body.addEventListener('scroll', queue, { passive: true });
      if (window.ResizeObserver) new ResizeObserver(queue).observe(body);
      thumb.addEventListener('pointerdown', function (e) {
        e.preventDefault();
        if (thumb.setPointerCapture) {
          try { thumb.setPointerCapture(e.pointerId); } catch (err) { /* stale id */ }
        }
        thumb.classList.add('is-drag');
        var startY = e.clientY, startTop = body.scrollTop;
        function mv(ev) {
          var span = track.clientHeight - thumb.clientHeight;
          if (span > 0) {
            body.scrollTop = startTop
              + (ev.clientY - startY) / span * (body.scrollHeight - body.clientHeight);
          }
        }
        function up() {
          thumb.classList.remove('is-drag');
          document.removeEventListener('pointermove', mv);
          document.removeEventListener('pointerup', up);
        }
        document.addEventListener('pointermove', mv);
        document.addEventListener('pointerup', up);
      });
      ovl.__syncSb = queue;
    }

    function openOverlay(wrap, list, trigger) {
      buildOverlay();
      if (movedList) closeOverlay();               // only one open at a time
      var meta = laneMeta(wrap);
      var n = list.children.length;
      ovl.querySelector('.lst-ovl-t').innerHTML = bl(meta.en, meta.zh);
      ovl.querySelector('.lst-ovl-count').textContent = n;
      ovl.querySelector('.lst-ovl-sub').innerHTML = bl(meta.subEn, meta.subZh);
      if (meta.accent) ovl.querySelector('.lst-ovl-hd').style.setProperty('--lane', meta.accent);
      else ovl.querySelector('.lst-ovl-hd').style.removeProperty('--lane');
      ovl.querySelector('.lst-ovl-hint').innerHTML =
        bl('Esc or click outside to close', '按 Esc 或点击外部关闭');
      homeMark = document.createComment('lst-ovl-home');
      list.parentNode.insertBefore(homeMark, list);
      var body = ovl.querySelector('.lst-ovl-body');
      carried = [];
      Array.prototype.forEach.call(wrap.querySelectorAll(CARRY_SEL), function (node) {
        var mark = document.createComment('lst-ovl-carry');
        node.parentNode.insertBefore(mark, node);
        body.appendChild(node);
        carried.push({ node: node, mark: mark });
      });
      body.appendChild(list);
      list.classList.remove('is-collapsed');
      movedList = list; lastTrigger = trigger;
      document.body.classList.add('lst-ovl-lock');
      ovl.classList.add('is-open');
      ovl.querySelector('.lst-ovl-body').scrollTop = 0;
      ovl.__syncSb();
      ovl.querySelector('.lst-ovl-modal').focus({ preventScroll: true });
    }

    function closeOverlay() {
      if (!ovl || !movedList) return;
      movedList.classList.add('is-collapsed');
      if (homeMark && homeMark.parentNode) {
        homeMark.parentNode.replaceChild(movedList, homeMark);
      } else {
        movedList.remove();  // home was rebuilt under us (langchange re-render) — drop the node
      }
      carried.forEach(function (c) {
        if (c.mark.parentNode) c.mark.parentNode.replaceChild(c.node, c.mark);
        else c.node.remove();
      });
      carried = [];
      movedList = null; homeMark = null;
      ovl.classList.remove('is-open');
      document.body.classList.remove('lst-ovl-lock');
      if (lastTrigger && lastTrigger.isConnected) {
        try { lastTrigger.focus({ preventScroll: true }); } catch (err) { /* detached */ }
      }
      lastTrigger = null;
    }

    // Restyle every .lst-more into the pill; recount on every pass so lists injected or
    // re-rendered after boot (renderActNow, langchange rebuilds) update their label.
    function upgrade() {
      document.querySelectorAll('.lst-wrap').forEach(function (wrap) {
        var btn = null, list = null, i;
        for (i = 0; i < wrap.children.length; i++) {
          if (wrap.children[i].classList.contains('lst-more')) btn = wrap.children[i];
        }
        list = wrap.querySelector('.lst-collapse');
        if (!btn || !list) return;
        var n = list.children.length;
        if (btn.dataset.ovlN === String(n)) return;   // idempotent per count
        btn.dataset.ovlN = String(n);
        btn.classList.add('lst-viewall');
        btn.setAttribute('aria-haspopup', 'dialog');
        btn.innerHTML = bl('View all ' + n, '查看全部 ' + n)
          + ' <span class="lst-va-arr" aria-hidden="true">↗</span>';
      });
    }

    // Capture-phase click: open the overlay INSTEAD of the legacy in-flow expansion.
    document.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.lst-more') : null;
      if (!btn) return;
      var wrap = btn.closest('.lst-wrap');
      var list = wrap && wrap.querySelector('.lst-collapse');
      if (!list) return;                            // malformed instance → legacy handler's problem
      e.preventDefault();
      e.stopImmediatePropagation();
      openOverlay(wrap, list, btn);
    }, true);

    upgrade();
    var mo = new MutationObserver(function () {
      if (mo.__raf) return;
      mo.__raf = requestAnimationFrame(function () { mo.__raf = 0; upgrade(); });
    });
    mo.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('langchange', upgrade);
  }

  /* ---- row conditions popover ([data-rpop] rows / hidden .rp-src payload) ----------
     Shared engine for the board-row hover cards (replaces the page-local .act-pop
     IIFE that shipped with the US action board). Fixes the four verified defects of
     that engine: the card is now itself hoverable (grace timers bridge the row→card
     gap), scrolling REPOSITIONS the card instead of dismissing it, height is measured
     from the in-document clone (dual-span content sized by the [data-lang] CSS, so
     the flip threshold is honest), and keyboard focus opens it. Touch is left alone:
     rows are links and the first tap must keep navigating. */
  function initRowPop() {
    if (window.__rowPopBound) return;
    window.__rowPopBound = true;
    var pop = document.createElement('div');
    pop.className = 'row-pop';
    pop.setAttribute('role', 'tooltip');
    pop.hidden = true;
    document.body.appendChild(pop);
    var cur = null, openT = 0, closeT = 0, lastScroll = 0;

    function place(row) {
      var r = row.getBoundingClientRect();
      var pw = pop.offsetWidth, ph = pop.offsetHeight;
      var vw = window.innerWidth, vh = window.innerHeight, m = 10, gap = 12;
      var x, y = r.top;
      if (r.right + gap + pw <= vw - m) x = r.right + gap;            // prefer right of row
      else if (r.left - gap - pw >= m) x = r.left - gap - pw;         // flip left
      else { x = Math.max(m, Math.min(r.left, vw - pw - m)); y = r.bottom + 8; }  // stack below
      if (y + ph > vh - m) y = Math.max(m, vh - ph - m);              // clamp vertically
      pop.style.left = x + 'px';
      pop.style.top = y + 'px';
    }

    function open(row) {
      var src = row.querySelector('.rp-src');
      if (!src) return;
      cur = row;
      pop.textContent = '';
      var clone = src.cloneNode(true);        // clone keeps l-en/l-zh spans live for CSS
      clone.classList.remove('rp-src');       // …but must shed the payload's display:none class
      clone.removeAttribute('hidden');        // …and its belt-and-braces hidden attribute
      pop.appendChild(clone);
      pop.hidden = false;
      pop.style.visibility = 'hidden';
      place(row);                             // measured AFTER content is in-document
      pop.style.visibility = '';
    }

    function close() { pop.hidden = true; cur = null; }
    function scheduleClose(ms) {
      clearTimeout(closeT);
      closeT = setTimeout(close, ms);
    }

    // touch devices have no hover — a tap TOGGLES the card (see the click handler below);
    // synthetic pointerover from a tap must not also trip the hover path.
    function coarse() { return !!(window.matchMedia && window.matchMedia('(hover: none)').matches); }
    document.addEventListener('pointerover', function (e) {
      if (e.pointerType === 'touch') return;
      if (!e.target || !e.target.closest) return;
      var row = e.target.closest('[data-rpop]');
      if (row) {
        clearTimeout(closeT); clearTimeout(openT);
        if (row !== cur) openT = setTimeout(function () { open(row); }, 32);   // snappy open, still debounces sweeps
        return;
      }
      if (!pop.hidden && e.target.closest('.row-pop')) { clearTimeout(closeT); return; }
      // a scroll shifts content under a stationary pointer, firing pointerover on whatever
      // slid beneath it — that must not count as the user leaving the row
      if (Date.now() - lastScroll < 250) return;
      if (cur || openT) { clearTimeout(openT); openT = 0; if (cur) scheduleClose(80); }
    });
    document.addEventListener('pointerout', function (e) {
      if (e.pointerType === 'touch') return;
      if (!e.relatedTarget && cur) scheduleClose(80);   // pointer left the window
    });
    // Touch: first tap on a row opens its card (previewing instead of navigating a link);
    // tapping the same row again, the card, or outside dismisses / lets the link through.
    document.addEventListener('click', function (e) {
      if (!coarse()) return;                            // desktop keeps hover + normal link clicks
      if (!e.target || !e.target.closest) return;
      if (e.target.closest('.row-pop')) return;         // taps inside the card act on the card
      var row = e.target.closest('[data-rpop]');
      if (row) {
        if (cur === row) { close(); return; }           // 2nd tap closes (a link then navigates on the next tap)
        if (row.matches('a[href], [href]') || row.closest('a[href]')) e.preventDefault();
        clearTimeout(closeT); clearTimeout(openT);
        open(row);
        return;
      }
      if (cur) close();                                 // tap elsewhere dismisses
    });
    // wheel fires BEFORE the resulting scroll/hover updates — stamp it too, or the
    // scroll-grace check below sees a stale timestamp on the first wheel tick
    document.addEventListener('wheel', function () { lastScroll = Date.now(); },
      { passive: true, capture: true });
    document.addEventListener('scroll', function () {
      lastScroll = Date.now();
      if (pop.hidden || !cur) return;
      var r = cur.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight || !cur.isConnected) { close(); return; }
      place(cur);                                        // follow the row, don't dismiss
    }, { passive: true, capture: true });
    window.addEventListener('resize', function () { if (cur) close(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    document.addEventListener('focusin', function (e) {
      if (coarse()) return;                             // touch: the click handler owns open/close
      var row = e.target && e.target.closest && e.target.closest('[data-rpop]');
      if (row) { clearTimeout(closeT); open(row); }
      else if (cur && !(e.target.closest && e.target.closest('.row-pop'))) scheduleClose(0);
    });
  }

  /* ---- progressive "show more" for card grids ------------------------------
     Two collapse modes on any grid, chosen by attribute:
       • [data-showmore="N"]      — show N cards, reveal N more per click (fixed count).
       • [data-showmore-rows="R"] — show R *rows*, reveal R more per click. The column
         count is read live from the grid's computed grid-template-columns, so "3 rows"
         means 3 on a wide 1-col layout, 6 on a 2-col phone, 9 on a 3-col desktop — and
         it re-clamps to whole rows on resize/orientation change. This keeps big, dense
         card lists (e.g. the Theme Rotation Desk) short on every width instead of
         scrolling on and on.
     Both reveal in staggered chunks, offer "Show all", and collapse back. Language-aware.
     Card mode no-ops when total <= N; row mode keeps the bar wired so a resize that drops
     a column can surface it. Safe to add the attribute unconditionally + idempotent. */
  function smBL(en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + zh + '</span>'; }
  function initShowMore() {
    document.querySelectorAll('[data-showmore],[data-showmore-rows]').forEach(function (grid) {
      if (grid.dataset.smInit) return;            // idempotent
      var rowMode = grid.hasAttribute('data-showmore-rows');
      var rowStep = Math.max(1, parseInt(grid.getAttribute('data-showmore-rows'), 10) || 3);
      var cardStep = Math.max(1, parseInt(grid.getAttribute('data-showmore'), 10) || 12);
      var items = [].filter.call(grid.children, function (el) { return el.nodeType === 1; });
      var total = items.length;
      // Live column count from the resolved grid tracks ("330px 330px 330px" → 3);
      // "none"/empty (not a grid / display:none, e.g. an inactive tab) falls back to 1.
      function colCount() {
        var tpl = (window.getComputedStyle(grid).getPropertyValue('grid-template-columns') || '').trim();
        if (!tpl || tpl === 'none') return 1;
        return Math.max(1, tpl.split(/\s+/).filter(Boolean).length);
      }
      function pageSize() { return rowMode ? rowStep * colCount() : cardStep; }
      if (!rowMode && total <= cardStep) { grid.dataset.smInit = '1'; return; }  // fixed mode: nothing to collapse
      grid.dataset.smInit = '1';
      // State is "how many pages are revealed" (a page = R rows in row mode) rather than a raw
      // card count, so a reflow to a new column count always resolves to a WHOLE number of rows
      // and preserves the number of rows the reader opened. showAll pins to the full list.
      var pages = 1, showAll = false, shown = 0;
      function target() { return showAll ? total : Math.min(pages * pageSize(), total); }

      var bar = document.createElement('div'); bar.className = 'sm-bar';
      var count = document.createElement('span'); count.className = 'sm-count';
      var btns = document.createElement('div'); btns.className = 'sm-btns';
      var more = document.createElement('button'); more.type = 'button'; more.className = 'sm-btn';
      var all = document.createElement('button'); all.type = 'button'; all.className = 'sm-btn sm-ghost';
      btns.appendChild(more); btns.appendChild(all);
      bar.appendChild(count); bar.appendChild(btns);
      grid.parentNode.insertBefore(bar, grid.nextSibling);

      function render(animateFrom) {
        shown = target();
        items.forEach(function (el, i) {
          var show = i < shown;
          if (show && el.classList.contains('sm-hidden')) {
            el.classList.remove('sm-hidden');
            if (animateFrom != null && i >= animateFrom) {
              el.classList.remove('sm-reveal'); void el.offsetWidth;   // restart animation
              el.style.animationDelay = Math.min((i - animateFrom) * 0.035, 0.45) + 's';
              el.classList.add('sm-reveal');
            }
          } else if (!show) {
            el.classList.add('sm-hidden'); el.classList.remove('sm-reveal'); el.style.animationDelay = '';
          }
        });
        count.innerHTML = smBL('Showing <b>' + shown + '</b> of <b>' + total + '</b>',
                               '已显示 <b>' + shown + '</b> / <b>' + total + '</b>');
        var remaining = total - shown;
        if (remaining > 0) {
          var next = Math.min(pageSize(), remaining);
          more.className = 'sm-btn';
          more.innerHTML = '<span class="sm-ic">▾</span>' + smBL('Show ' + next + ' more', '再显示 ' + next + ' 个');
          all.style.display = '';
          all.innerHTML = smBL('Show all ' + total, '全部显示 ' + total);
        } else {
          more.className = 'sm-btn sm-collapse';
          more.innerHTML = '<span class="sm-ic">▾</span>' + smBL('Show fewer', '收起');
          all.style.display = 'none';
        }
        // if one page already covers everything at this width, there's nothing to collapse
        bar.style.display = (total <= pageSize()) ? 'none' : '';
      }
      more.addEventListener('click', function () {
        if (shown >= total) {                      // collapse back to the first page
          pages = 1; showAll = false; render();
          grid.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          var from = shown; pages += 1; render(from);
        }
      });
      all.addEventListener('click', function () { var from = shown; showAll = true; render(from); });
      if (rowMode) {
        // Re-resolve only when the grid reflows to a NEW column count — so it always lands on a
        // whole number of rows. window 'resize' covers viewport/orientation changes; a
        // ResizeObserver additionally catches an inactive tab becoming visible (display:none →
        // grid) that a resize listener would miss. Both share one debounced, col-gated pass.
        var lastCols = colCount(), rz;
        var reflow = function () {
          clearTimeout(rz);
          rz = setTimeout(function () {
            var cols = colCount();
            if (cols === lastCols) return;         // ignore height-only changes (e.g. our own reveals)
            lastCols = cols; render();
          }, 140);
        };
        window.addEventListener('resize', reflow);
        if (window.ResizeObserver) { try { new ResizeObserver(reflow).observe(grid); } catch (e) {} }
      }
      render();
    });
  }
  window.initShowMore = initShowMore;             // exposed so client-rendered grids can re-trigger after populating

  // US-stocks board: relocate the pinned "Track record" toggle (rendered in-template so it
  // exists even when nothing overflows) into the board's show-more bar as its left-most
  // element, so it shares the row with "Showing X of Y" + the show-more controls. When the
  // board doesn't overflow, no .sm-bar is injected and the button simply stays where the
  // template put it (just above the collapsed panel). Idempotent.
  function pinBoardTrackToggle() {
    var toggle = document.getElementById('board-track-toggle');
    if (!toggle || toggle.dataset.pinned) return;
    var grid = document.querySelector('.nbgrid[data-showmore-rows]');
    if (!grid) return;
    var bar = grid.nextElementSibling;
    if (bar && bar.classList.contains('sm-bar')) {
      bar.insertBefore(toggle, bar.firstChild);   // left-most; CSS order:-1 keeps it pinned left
      toggle.dataset.pinned = '1';
    }
  }
  window.pinBoardTrackToggle = pinBoardTrackToggle;

  // Wrap wide data tables in a horizontal-scroll container so they scroll WITHIN their
  // card on narrow screens instead of bleeding past the viewport (mobile fix). Runs before
  // tablesort (theme.js loads first) so the filter box lands above the wrapper, and again on
  // load for any JS-rendered tables. Skips tooltip / nav tables and anything already wrapped.
  function wrapTables(root) {
    // The self-contained pages (.topbar / strategy-detail family) don't link
    // theme.css, so the .tbl-scroll wrapper added below would have NO scroll
    // styling and a wide table would bleed past the viewport on mobile. Inject the
    // rule from here (idempotent) so the wrapper this function creates always
    // scrolls, mirroring theme.css. --line falls back to the vector palette's
    // --grid, then a hard colour, so the scrollbar styles on every palette.
    if (!document.getElementById('tbl-scroll-css')) {
      var ts = document.createElement('style');
      ts.id = 'tbl-scroll-css';
      ts.textContent = '.tbl-scroll{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain}'
        + '.tbl-scroll::-webkit-scrollbar{height:6px}'
        + '.tbl-scroll::-webkit-scrollbar-thumb{background:var(--line,var(--grid,#2a2f3a));border-radius:6px}'
        // ── mobile-fit safety net ────────────────────────────────────────────
        // The dashboard's grid/column primitives collapse to one column on phones,
        // but their items default to min-width:auto, so nowrap content (long basket
        // names, allocation labels, AI reasoning) forced the single track far wider
        // than the screen → page-wide horizontal scroll. Let those items shrink
        // (min-width:0) and let the known nowrap leaves wrap. ≤700px only.
        + '@media (max-width:700px){'
        +   '.grid>*,.anwrap>*,.rotwrap>*,.rotwrap2>*,.twocol>*,.sm-2col>*,.sm-3col>*,.scm-2col>*,.scm-3col>*,.fl-cols>*,.sgrid>*,.sid-grid>*,.cmeta>*,.band>*,.board>*,.cards>*,.scards>*,.score>*,.s>*,.vgrid>*,.vcard>*,.vchip>*,.vchart-bar>*,.metric-row>*,.pdial>*{min-width:0}'
        +   '.ancol,.anrow,.anrow>*,.pcol,.prow,.prow>*,.sm-col,.scm-col,.vcard,.vchip{min-width:0}'
        +   '.anrow .rn,.cnt,.band .cnt,.b-fact{white-space:normal}'
        +   '.vchart-chips{flex-wrap:wrap}'
        + '}'
        // grids whose tracks carry a fixed minmax() floor wider than a phone can't be
        // fixed by min-width:0 on the items — collapse the track itself on small screens.
        +   '@media (max-width:560px){.score,.score .s{grid-template-columns:repeat(2,1fr)}.board{grid-template-columns:1fr}}';
      document.head.appendChild(ts);
    }
    (root || document).querySelectorAll('table').forEach(function (t) {
      if (t.closest('.tbl-scroll')) return;                       // already wrapped
      if (t.closest('.tip, .help, .site-nav, .topbar, .nav-links, .nav-dd-menu')) return;
      if (!t.parentNode) return;
      var w = document.createElement('div');
      w.className = 'tbl-scroll';
      t.parentNode.insertBefore(w, t);
      w.appendChild(t);
    });
  }

  // Build the settings modal as EARLY as possible. theme.js is the last script
  // before </body>, so the nav is already parsed — relocating the toggles now,
  // before first paint, swaps them for the gear with no visible flash. Idempotent,
  // with a DOMContentLoaded fallback for any page that loads theme.js in <head>.
  if (document.body) { try { initSettings(); } catch (e) {} }

  document.addEventListener('DOMContentLoaded', function () {
    wrapTables();
    // legacy text buttons (Bitcoin Vector / hub / China — untouched pages)
    document.querySelectorAll('.theme-btn').forEach(function (b) {
      b.addEventListener('click', window.toggleTheme);
      b.innerHTML = curTheme() === 'light'
        ? '<span class="l-en">🌙 Dark</span><span class="l-zh">🌙 深色</span>'
        : '<span class="l-en">☀️ Light</span><span class="l-zh">☀️ 浅色</span>';
    });
    document.querySelectorAll('.lang-btn').forEach(function (b) {
      b.addEventListener('click', window.toggleLang);
      b.textContent = curLang() === 'zh' ? 'EN' : '中文';
    });
    // new animated toggles (macro nav) — visuals are pure-CSS off data-theme/lang
    document.querySelectorAll('.theme-switch').forEach(function (b) {
      b.addEventListener('click', window.toggleTheme);
    });
    // Whole-control toggle: a click ANYWHERE on the language pill (either label, the
    // sliding pill, the padding) flips to the other language — no need to land on the
    // exact inactive side. Mirrors the theme switch, whose handler is on the whole
    // <button>. Bound on the container so descendant clicks bubble up to one handler.
    document.querySelectorAll('.lang-toggle').forEach(function (t) {
      t.addEventListener('click', function () { window.toggleLang(); });
      // Keyboard operability (WCAG 2.1 SC 2.1.1): make the lang-toggle reachable and
      // operable via keyboard without breaking existing CSS.
      if (!t.hasAttribute('tabindex')) t.setAttribute('tabindex', '0');
      if (!t.getAttribute('role')) t.setAttribute('role', 'switch');
      // aria-checked reflects zh = true / en = false; synced on langchange + immediately
      function _syncLangAria() {
        var zh = (docEl.getAttribute('data-lang') || 'en') === 'zh';
        t.setAttribute('aria-checked', zh ? 'true' : 'false');
        // bilingual aria-label without using title= (CI-guarded rule)
        t.setAttribute('aria-label', zh ? '语言 — 当前中文，切换为 English' : 'Language — current English, switch to 中文');
      }
      _syncLangAria();
      document.addEventListener('langchange', _syncLangAria);
      t.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); window.toggleLang(); }
      });
    });
    initSettings();   // fallback if the early call above could not run
    _authBoot();      // restore a prior cookie session / consume an OAuth return
    initNavDrills();
    initNavSearch();
    initActiveNav();
    initMobileNav();
    initAdaptiveNav();
    initShowMore();
    pinBoardTrackToggle();
    initListCollapse();
    initListOverlay();
    initRowPop();
    initChatLauncher();
    themeCharts();
  });
  // charts may finish drawing after DOMContentLoaded; re-theme once more on load
  window.addEventListener('load', function () { themeCharts(); wrapTables(); });

  /* ---- floating chat launcher ------------------------------------------------
     Bottom-right glass pill (above the back-to-top FAB at z-index:960). Hidden
     on chat.html itself, on admin.* subdomains, and on print. Carries ?symbol=
     when window.MDXActiveSymbol is set by the host page. Responds to langchange
     so the label switches without a page reload. */
  function initChatLauncher() {
    var h = location.hostname || '';
    // suppress on the admin subdomain, on the standalone chat.html, and in print.
    if (h.split('.')[0] === 'admin') return;
    if (/\/chat\.html([?#]|$)/.test(location.pathname + location.search + location.hash)) return;
    if (window.MMBrain || document.getElementById('mmb-root')) return;
    // The unified Mastermind Brain widget mounts its OWN bottom-right launcher + an
    // expandable overlay and wires the /api/brain gateway. Bridge the site's active
    // symbol global into the widget's page context.
    window.MM_BRAIN_CFG = window.MM_BRAIN_CFG || {
      anchor: 'br',
      symbol: function () {
        return (typeof window.MDXActiveSymbol === 'string' && window.MDXActiveSymbol)
            || (typeof window.ACTIVE_SYMBOL === 'string' && window.ACTIVE_SYMBOL) || '';
      }
    };
    var s = document.createElement('script');
    s.src = 'mm_brain.js'; s.defer = true;
    (document.body || document.documentElement).appendChild(s);
  }
})();

/* ---- LENS — the site-wide explainer popover ([data-tip-en]/[data-tip-zh] + rich tier)
   The overhauled container for every explainer on the site (design mockups/lens,
   merged #3102; operator order 2026-07-19 — concise plain words, illustrated,
   beautifully formatted). One body-appended glass card, two content tiers:
     · string tier — existing data-tip-en / data-tip-zh attributes render in the new
       card unchanged. An OPTIONAL data-tip-rc-en / data-tip-rc-zh pair renders as a
       mono "receipt" line under a dashed perforation — the sanctioned Tier-2 home
       for n= / windows / sources / study IDs, which are BANNED from the body.
     · rich tier — a trigger (.lens-q "?" button or .lens-term dotted span) plus a
       hidden .lens-src block (direct child or next sibling) carrying the
       illustrated anatomy: .lens-hd (.lens-ill disc + .lens-kick kicker +
       .lens-title) → .lens-body → .lens-receipt, with a data-lens-kind accent
       (define | read | record | source | caution).
   i18n rule unchanged: translated text NEVER goes in title= attributes — dual-span
   l-en/l-zh bodies follow the [data-lang] CSS live.
   Desktop: hover-intent (90ms open / 180ms close grace), the card itself is
   hoverable, and it FOLLOWS its trigger on scroll (hiding once the trigger leaves
   the viewport). Touch: tap-to-toggle (nested controls still win the tap — the old
   singleton's contract). ≤640px the card becomes a bottom sheet — scrim, drag
   handle, swipe-down dismiss, safe-area padded, pinned left/right:0 so it CANNOT
   bleed off-screen. Esc closes; focus opens; aria-describedby wired.
   The component CSS is INJECTED here rather than living in theme.css so vector-
   family pages (own token names, no theme.css) style it correctly through the
   --lens-* fallback chains — the settings-popover pattern. */
(function () {
  var OPEN_MS = 90, CLOSE_MS = 180;
  // NOTE: bare `data-lens` is NOT a trigger — the AI-Brief tab system already uses
  // data-lens="macro|china|btc" for its tabs + body wrapper, and a capture-phase
  // match here would swallow those taps on touch. Rich-tier triggers opt in via the
  // .lens-q / .lens-term classes only.
  var SEL = '[data-tip-en], .lens-q, .lens-term';
  var pop = null, scrim = null, cur = null, openTimer = 0, closeTimer = 0, scrollRaf = 0;

  var CSS =
    '.lens-src{display:none}' +
    '.lens-q{display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;' +
      'margin:0 2px;padding:0;vertical-align:middle;flex:none;font:600 10.5px/1 var(--font-ui,Inter,sans-serif);' +
      'color:var(--muted,var(--mut,#8b93a1));background:color-mix(in srgb,var(--muted,var(--mut,#8b93a1)) 9%,transparent);' +
      'border:1px solid color-mix(in srgb,var(--muted,var(--mut,#8b93a1)) 42%,transparent);cursor:help;user-select:none;' +
      '-webkit-tap-highlight-color:transparent;transition:color .18s,border-color .18s,background .18s,box-shadow .22s,transform .22s cubic-bezier(.34,1.26,.4,1)}' +
    '.lens-q:hover,.lens-q.lens-on,.lens-q:focus-visible{color:var(--info,var(--blue,#5b9bf0));' +
      'border-color:color-mix(in srgb,var(--info,var(--blue,#5b9bf0)) 55%,transparent);' +
      'background:color-mix(in srgb,var(--info,var(--blue,#5b9bf0)) 13%,transparent);' +
      'box-shadow:0 0 0 3px color-mix(in srgb,var(--info,var(--blue,#5b9bf0)) 12%,transparent);transform:scale(1.12);outline:none}' +
    '.lens-term{border-bottom:1px dotted color-mix(in srgb,var(--muted,var(--mut,#8b93a1)) 65%,transparent);cursor:help;' +
      'border-radius:3px 3px 0 0;transition:color .18s,border-color .18s,background .18s}' +
    '.lens-term:hover,.lens-term.lens-on,.lens-term:focus-visible{color:var(--info,var(--blue,#5b9bf0));' +
      'border-bottom:1px solid var(--info,var(--blue,#5b9bf0));background:color-mix(in srgb,var(--info,var(--blue,#5b9bf0)) 9%,transparent);outline:none}' +
    /* upgraded legacy "?" icons pick up the same live hover accent as .lens-q */
    'span.help.help-upgraded{cursor:help;transition:color .18s,border-color .18s,background .18s,box-shadow .22s}' +
    'span.help.help-upgraded:hover,span.help.help-upgraded.lens-on{color:var(--info,var(--blue,#5b9bf0));' +
      'border-color:color-mix(in srgb,var(--info,var(--blue,#5b9bf0)) 55%,transparent);' +
      'background:color-mix(in srgb,var(--info,var(--blue,#5b9bf0)) 13%,transparent);' +
      'box-shadow:0 0 0 3px color-mix(in srgb,var(--info,var(--blue,#5b9bf0)) 12%,transparent)}' +
    '.lens-pop{--lens-panel:var(--panel,var(--card,#181b21));--lens-text:var(--text,var(--ink,#d7dce3));' +
      '--lens-mut:var(--muted,var(--mut,#8b93a1));--lens-accent:var(--info,var(--blue,#5b9bf0));' +
      'position:fixed;left:0;top:0;z-index:12600;width:min(304px,calc(100vw - 24px));border-radius:16px;' +
      'background:linear-gradient(180deg,color-mix(in srgb,#fff 4%,transparent),transparent 46%),color-mix(in srgb,var(--lens-panel) 88%,transparent);' +
      '-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);' +
      'box-shadow:0 24px 64px -18px rgba(3,7,18,.72),0 8px 22px -10px rgba(3,7,18,.5);' +
      'opacity:0;pointer-events:none;transform:translateY(7px) scale(.96);transition:opacity .12s ease,transform .12s ease;' +
      'font-family:var(--font-ui,Inter,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif);' +
      'text-align:left;text-transform:none;letter-spacing:normal;white-space:normal}' +
    '@supports not (backdrop-filter:blur(1px)){.lens-pop{background:color-mix(in srgb,var(--panel,var(--card,#181b21)) 98%,#fff)}}' +
    '.lens-pop.open{opacity:1;pointer-events:auto;transform:none;transition:opacity .2s ease,transform .28s cubic-bezier(.34,1.26,.4,1)}' +
    '.lens-pop::before{content:"";position:absolute;inset:0;border-radius:inherit;padding:1px;' +
      'background:radial-gradient(140px 70px at 22% -4%,color-mix(in srgb,var(--lens-accent) 75%,transparent),transparent 72%),' +
      'linear-gradient(180deg,color-mix(in srgb,var(--lens-text) 17%,transparent),color-mix(in srgb,var(--lens-text) 7%,transparent));' +
      '-webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;' +
      'mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);mask-composite:exclude;pointer-events:none}' +
    '.lens-pop::after{content:"";position:absolute;inset:1px;border-radius:inherit;pointer-events:none;' +
      'background:linear-gradient(112deg,transparent 40%,rgba(255,255,255,.07) 50%,transparent 60%);' +
      'background-size:240% 100%;background-position:130% 0;opacity:0}' +
    '.lens-pop.open::after{animation:lensSheen .95s cubic-bezier(.4,.1,.2,1) .1s 1 both}' +
    '@keyframes lensSheen{0%{opacity:0;background-position:130% 0}18%{opacity:1}100%{opacity:0;background-position:-40% 0}}' +
    '.lens-pop[data-kind=define]{--lens-accent:var(--info,var(--blue,#5b9bf0))}' +
    '.lens-pop[data-kind=read]{--lens-accent:var(--q2,#d4a017)}' +
    '.lens-pop[data-kind=record]{--lens-accent:var(--ok,var(--up,#3da564))}' +
    '.lens-pop[data-kind=source]{--lens-accent:color-mix(in srgb,var(--lens-mut) 85%,var(--lens-text))}' +
    '.lens-pop[data-kind=caution]{--lens-accent:var(--warn,#e0a030)}' +
    '.lens-hd{display:flex;align-items:center;gap:11px;padding:15px 16px 0}' +
    '.lens-ill{flex:none;width:34px;height:34px;border-radius:11px;display:grid;place-items:center;color:var(--lens-accent);' +
      'background:radial-gradient(120% 120% at 30% 18%,color-mix(in srgb,var(--lens-accent) 24%,transparent),color-mix(in srgb,var(--lens-accent) 6%,transparent) 62%,transparent);' +
      'box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--lens-accent) 30%,transparent)}' +
    '.lens-ill svg{width:20px;height:20px;display:block}' +
    '.lens-hgroup{min-width:0}' +
    '.lens-kick{display:block;font:700 9.5px/1 var(--font-ui,Inter,sans-serif);letter-spacing:.15em;text-transform:uppercase;' +
      'color:color-mix(in srgb,var(--lens-accent) 80%,var(--lens-text))}' +
    '.lens-title{display:block;margin-top:4px;font:700 14px/1.3 var(--font-ui,Inter,sans-serif);letter-spacing:-.01em;color:var(--lens-text)}' +
    '.lens-body{padding:10px 16px 14px;font:450 12.5px/1.62 var(--font-ui,Inter,sans-serif);color:color-mix(in srgb,var(--lens-text) 88%,var(--lens-mut))}' +
    '.lens-body b,.lens-body strong{font-weight:650;color:var(--lens-text)}' +
    '.lens-receipt{display:flex;flex-wrap:wrap;gap:5px 14px;align-items:baseline;margin:0 16px;padding:10px 0 13px;' +
      'border-top:1px dashed color-mix(in srgb,var(--lens-text) 17%,transparent);' +
      'font:600 10px/1.5 var(--font-ui,Inter,sans-serif);letter-spacing:.02em;color:var(--lens-mut)}' +
    '.lens-receipt .r-i{display:inline-flex;align-items:baseline;gap:5px;white-space:nowrap}' +
    '.lens-receipt .r-k{font:700 8.5px/1 var(--font-ui,Inter,sans-serif);letter-spacing:.12em;text-transform:uppercase;' +
      'color:color-mix(in srgb,var(--lens-mut) 75%,transparent)}' +
    '.lens-pop.lens-plain{width:auto;max-width:min(300px,calc(100vw - 24px))}' +
    '.lens-pop.lens-plain .lens-body{padding:11px 14px 12px;font-size:12px}' +
    '.lens-pop.lens-plain .lens-receipt{margin:0 14px}' +
    '.lens-pop.open .lens-hd,.lens-pop.open .lens-body,.lens-pop.open .lens-receipt{animation:lensRise .34s cubic-bezier(.34,1.26,.4,1) both}' +
    '.lens-pop.open .lens-body{animation-delay:.045s}' +
    '.lens-pop.open .lens-receipt{animation-delay:.09s}' +
    '@keyframes lensRise{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}' +
    '.lens-grab,.lens-x{display:none}' +
    '.lens-scrim{position:fixed;inset:0;z-index:12595;background:rgba(4,7,13,.48);' +
      '-webkit-backdrop-filter:blur(5px);backdrop-filter:blur(5px);opacity:0;pointer-events:none;transition:opacity .24s ease}' +
    '.lens-scrim.open{opacity:1;pointer-events:auto}' +
    'html.lens-lock,html.lens-lock body{overflow:hidden}' +
    /* the Mastermind launcher stacks above the sheet — hide it while one is open */
    'html.lens-lock #mmb-root{visibility:hidden !important}' +
    '@media (max-width:640px){' +
      '.lens-pop{left:0 !important;right:0;top:auto !important;bottom:0 !important;width:100%;max-width:100%;' +
        'border-radius:20px 20px 0 0;padding-bottom:max(10px,env(safe-area-inset-bottom));' +
        'max-height:min(72vh,480px);overflow:auto;overscroll-behavior:contain;' +
        'transform:translateY(26px);transform-origin:50% 100% !important}' +
      '.lens-pop.lens-plain{max-width:100%}' +
      '.lens-pop.open{transform:none}' +
      '.lens-grab{display:block;width:38px;height:4px;border-radius:2px;margin:10px auto 2px;' +
        'background:color-mix(in srgb,var(--lens-text) 22%,transparent)}' +
      '.lens-x{display:grid;place-items:center;position:absolute;top:10px;right:12px;width:26px;height:26px;' +
        'border-radius:50%;border:0;padding:0;font:600 11px/1 var(--font-ui,Inter,sans-serif);' +
        'color:var(--lens-mut);background:color-mix(in srgb,var(--lens-mut) 14%,transparent);cursor:pointer}' +
      '.lens-hd{padding-top:8px}' +
      '.lens-ill{width:38px;height:38px}' +
      '.lens-pop.lens-plain .lens-body{font-size:13px;padding:12px 18px 6px}' +
      '.lens-pop.lens-plain .lens-receipt{margin:0 18px}' +
    '}' +
    '@media (prefers-reduced-motion:reduce){' +
      '.lens-pop,.lens-pop.open{transition:opacity .12s ease;transform:none}' +
      '.lens-pop.open::after{animation:none}' +
      '.lens-pop.open .lens-hd,.lens-pop.open .lens-body,.lens-pop.open .lens-receipt{animation:none}' +
    '}';

  function injectCss() {
    if (document.getElementById('lens-style')) return;
    var st = document.createElement('style');
    st.id = 'lens-style';
    st.textContent = CSS;
    (document.head || document.documentElement).appendChild(st);
  }
  injectCss();   // eager: trigger styles (.lens-q/.lens-term, upgraded ?) must apply at paint

  function isSheet() { return window.matchMedia && window.matchMedia('(max-width:640px)').matches; }
  function isOpen() { return !!(pop && pop.classList.contains('open')); }
  function touchMode() { return window.matchMedia && window.matchMedia('(hover: none)').matches; }

  function ensure() {
    if (pop) return;
    injectCss();
    scrim = document.createElement('div');
    scrim.className = 'lens-scrim';
    scrim.addEventListener('click', hide);
    document.body.appendChild(scrim);

    pop = document.createElement('div');
    pop.className = 'lens-pop';
    pop.id = 'lensPop';
    pop.setAttribute('role', 'tooltip');
    document.body.appendChild(pop);

    pop.addEventListener('pointerenter', function () { clearTimeout(closeTimer); });
    pop.addEventListener('pointerleave', function () { if (!touchMode()) scheduleClose(); });
    pop.addEventListener('click', function (e) {
      var x = e.target && e.target.closest && e.target.closest('.lens-x');
      if (x) { e.preventDefault(); e.stopPropagation(); hide(); }
    });
    /* swipe-down dismiss on the sheet */
    var y0 = null, dy = 0;
    pop.addEventListener('touchstart', function (e) {
      if (!isSheet() || pop.scrollTop > 0) return;
      y0 = e.touches[0].clientY; dy = 0; pop.style.transition = 'none';
    }, { passive: true });
    pop.addEventListener('touchmove', function (e) {
      if (y0 == null) return;
      dy = Math.max(0, e.touches[0].clientY - y0);
      pop.style.transform = 'translateY(' + dy + 'px)';
    }, { passive: true });
    pop.addEventListener('touchend', function () {
      if (y0 == null) return;
      pop.style.transition = ''; pop.style.transform = '';
      if (dy > 64) hide();
      y0 = null;
    });
  }

  function contentFor(t) {
    var src = null, i, kids = t.children;
    for (i = 0; i < kids.length; i++) {
      if (kids[i].classList && kids[i].classList.contains('lens-src')) { src = kids[i]; break; }
    }
    if (!src && t.nextElementSibling && t.nextElementSibling.classList &&
        t.nextElementSibling.classList.contains('lens-src')) src = t.nextElementSibling;
    if (src) {
      return { kind: t.getAttribute('data-lens-kind') || src.getAttribute('data-lens-kind') || 'define',
               rich: src.innerHTML };
    }
    var en = t.getAttribute('data-tip-en');
    if (!en) return null;
    var rcEn = t.getAttribute('data-tip-rc-en') || '';
    return { kind: t.getAttribute('data-lens-kind') || '',
             en: en, zh: t.getAttribute('data-tip-zh') || en,
             rcEn: rcEn, rcZh: t.getAttribute('data-tip-rc-zh') || rcEn };
  }

  function mkSpan(cls, txt) {
    var s = document.createElement('span'); s.className = cls; s.textContent = txt; return s;
  }

  function place(t) {
    var r = t.getBoundingClientRect();
    var pw = pop.offsetWidth, ph = pop.offsetHeight;
    var above = r.top - ph - 9 >= 8;
    var y = above ? r.top - ph - 9 : r.bottom + 9;
    if (!above && y + ph > window.innerHeight - 8) y = Math.max(8, window.innerHeight - ph - 8);
    var x = Math.round(Math.max(12, Math.min(r.left + r.width / 2 - pw / 2, window.innerWidth - pw - 12)));
    pop.style.left = x + 'px';
    pop.style.top = Math.round(y) + 'px';
    pop.style.transformOrigin = Math.round(r.left + r.width / 2 - x) + 'px ' + (above ? '100%' : '0%');
  }

  function show(t) {
    var c = contentFor(t);
    if (!c) return;
    ensure();
    clearTimeout(closeTimer);
    if (cur === t && isOpen()) return;
    if (cur) { cur.classList.remove('lens-on'); cur.removeAttribute('aria-describedby'); }
    cur = t;
    t.classList.add('lens-on');
    t.setAttribute('aria-describedby', 'lensPop');

    pop.textContent = '';
    var grab = document.createElement('div'); grab.className = 'lens-grab'; pop.appendChild(grab);
    var x = document.createElement('button'); x.type = 'button'; x.className = 'lens-x';
    x.setAttribute('aria-label', 'Close'); x.textContent = '✕'; pop.appendChild(x);
    if (c.rich) {
      pop.classList.remove('lens-plain');
      var wrap = document.createElement('div'); wrap.innerHTML = c.rich;
      while (wrap.firstChild) pop.appendChild(wrap.firstChild);
    } else {
      pop.classList.add('lens-plain');
      var body = document.createElement('div'); body.className = 'lens-body';
      body.appendChild(mkSpan('l-en', c.en)); body.appendChild(mkSpan('l-zh', c.zh));
      pop.appendChild(body);
      if (c.rcEn) {
        var rc = document.createElement('div'); rc.className = 'lens-receipt';
        rc.appendChild(mkSpan('l-en', c.rcEn)); rc.appendChild(mkSpan('l-zh', c.rcZh));
        pop.appendChild(rc);
      }
    }
    if (c.kind) pop.setAttribute('data-kind', c.kind); else pop.removeAttribute('data-kind');

    pop.classList.remove('open');
    void pop.offsetWidth;                       /* restart the entrance + sheen */
    pop.classList.add('open');

    if (isSheet()) {
      scrim.classList.add('open');
      document.documentElement.classList.add('lens-lock');
      return;
    }
    scrim.classList.remove('open');
    document.documentElement.classList.remove('lens-lock');
    place(t);
  }

  function hide() {
    clearTimeout(openTimer); clearTimeout(closeTimer);
    if (!pop) return;
    pop.classList.remove('open');
    if (scrim) scrim.classList.remove('open');
    document.documentElement.classList.remove('lens-lock');
    if (cur) { cur.classList.remove('lens-on'); cur.removeAttribute('aria-describedby'); cur = null; }
  }
  function scheduleClose() { clearTimeout(closeTimer); closeTimer = setTimeout(hide, CLOSE_MS); }

  document.addEventListener('pointerover', function (e) {
    // Touch devices: a tap fires pointerover BEFORE click, so pre-showing here would
    // let the click handler immediately toggle it back off (flash-and-vanish) and the
    // tip would never persist. On touch, let the click handler own show/hide entirely.
    if (touchMode()) return;
    if (e.pointerType && e.pointerType !== 'mouse' && e.pointerType !== 'pen') return;
    if (!e.target || !e.target.closest) return;
    var _h = e.target.closest('span.help:not([data-tip-en])'); if (_h) upgradeOne(_h);  // JIT-upgrade client-rendered icons
    var t = e.target.closest(SEL);
    if (t) {
      clearTimeout(closeTimer);
      if (cur === t && isOpen()) return;
      clearTimeout(openTimer);
      openTimer = setTimeout(function () { show(t); }, OPEN_MS);
      return;
    }
    if (pop && pop.contains(e.target)) { clearTimeout(closeTimer); return; }  // keep while over the pop
    clearTimeout(openTimer);
    if (isOpen()) scheduleClose();
  }, true);
  document.addEventListener('pointerout', function (e) {
    if (touchMode()) return;
    if (!e.relatedTarget) {                              // cursor left the window
      clearTimeout(openTimer);                           // don't flash a pending open
      if (isOpen()) scheduleClose();
    }
  }, true);
  document.addEventListener('focusin', function (e) {
    var t = e.target && e.target.closest && e.target.closest(SEL);
    if (t) show(t);
  }, true);
  document.addEventListener('focusout', function (e) {
    var t = e.target && e.target.closest && e.target.closest(SEL);
    if (t) scheduleClose();
  }, true);
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var _h = e.target.closest('span.help:not([data-tip-en])'); if (_h) upgradeOne(_h);  // JIT-upgrade client-rendered icons
    var t = e.target.closest(SEL);
    if (!t) {
      if (isOpen() && !(pop && pop.contains(e.target))) hide();
      return;
    }
    // If the tap landed on an interactive control NESTED INSIDE the tip container
    // (a button/link/field that is a descendant of t — e.g. the Grid/Table view
    // toggle, whose wrapper carries the data-tip), let the control activate instead
    // of hijacking the tap (the old singleton's load-bearing contract). A nested
    // .lens-q can never reach here as ctrl !== t: closest(SEL) resolves the .lens-q
    // itself as the trigger from inside it.
    var ctrl = e.target.closest('button, a, input, select, textarea, label, [role="button"]');
    if (ctrl && ctrl !== t && t.contains(ctrl)) {
      if (isOpen()) hide();
      return;
    }
    var dedicated = t.classList.contains('lens-q') || t.classList.contains('lens-term');
    if (touchMode()) {
      if (!contentFor(t)) return;               // no resolvable tip — never swallow the tap
      e.preventDefault(); e.stopPropagation();
      if (cur === t && isOpen()) hide(); else show(t);
      return;
    }
    if (dedicated) {                            // desktop pin-toggle on purpose-built triggers only
      if (cur === t && isOpen()) hide(); else show(t);
      return;
    }
    // bare data-tip chips: desktop clicks pass through (hover already shows the tip)
  }, true);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isOpen()) hide();
  });
  window.addEventListener('scroll', function () {
    // The floating card FOLLOWS its trigger; it hides only when the trigger leaves
    // the viewport. Sheet mode is scroll-locked (and the card's own inner scroll
    // must never dismiss it), so skip entirely there.
    if (!isOpen() || !cur || isSheet()) return;
    if (scrollRaf) return;
    scrollRaf = requestAnimationFrame(function () {
      scrollRaf = 0;
      if (!isOpen() || !cur) return;
      var r = cur.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight) { hide(); return; }
      place(cur);
    });
  }, true);
  window.addEventListener('resize', function () { if (isOpen()) hide(); });

  /* Upgrade the legacy help() icons site-wide to this same popover system.
     The old help() macro renders EXACTLY
       <span class="help">?<span class="tip"><span class="l-en">…</span><span class="l-zh">…</span></span></span>
     with a CSS :hover tooltip that (a) doesn't persist on tap, (b) bleeds off-screen
     on mobile, and (c) looks different from the Mag7 / Leadership icons. Rather than
     rewrite ~34 per-page macros + re-render every page, lift each icon's nested .tip
     text into data-tip-en / data-tip-zh so the delegated handler above drives it
     (viewport-clamped popover + tap-to-toggle), and mark it .help-upgraded so CSS can
     suppress the old nested tooltip and apply the new pill look.

     IMPORTANT: the bare `help` class is ALSO reused on non-icon CONTENT elements whose
     tooltips are RICH — market-state factor labels (`f-name help`), the seasonality
     cell (`help` with an SVG chart + table in its .tip), the anticipation index badge
     (`idxbadge … help`). Upgrading those would flatten/delete their content and paint a
     stray pill. So upgradeOne only touches a CANONICAL help() icon: class is EXACTLY
     "help" (single class) AND its direct .tip contains nothing but .l-en / .l-zh.
     Everything else is left completely untouched (keeps its own tooltip + styling). */
  function upgradeOne(el) {
    if (el.hasAttribute('data-tip-en')) return false;
    if (!(el.classList.length === 1 && el.classList.contains('help'))) return false;
    // A canonical help() icon is EXACTLY a "?" text node + a single .tip element child.
    // Content reuses (e.g. the seasonality value cell) carry an extra element child — a
    // value span — alongside their tip, so requiring exactly one element child filters
    // them out even when their tip is a plain l-en/l-zh pair (the low-history fallback).
    var tip = null, tkids, i, c, en = null, zh = null;
    if (el.children.length !== 1) return false;
    tip = el.children[0];
    if (!tip.classList.contains('tip')) return false;
    tkids = tip.children;
    if (tkids.length < 1 || tkids.length > 2) return false;   // canonical tip = l-en (+ l-zh), nothing else
    for (i = 0; i < tkids.length; i++) {
      c = tkids[i];
      // l-en / l-zh must be PLAIN TEXT. A few help() icons pack rich markup (tables, <b>
      // separators) inside their bilingual spans — the popover renders via textContent,
      // which would flatten that to an unreadable run-on, so leave those on their original
      // formatted :hover tooltip rather than upgrading.
      if (c.children.length) return false;
      if (c.classList.contains('l-en')) en = (c.textContent || '').trim();
      else if (c.classList.contains('l-zh')) zh = (c.textContent || '').trim();
      else return false;                                      // any other child → not an icon; leave it
    }
    if (!en) return false;
    el.setAttribute('data-tip-en', en);
    el.setAttribute('data-tip-zh', zh || en);
    el.classList.add('help-upgraded');
    return true;
  }
  function upgradeHelpIcons(root) {
    var icons = (root || document).querySelectorAll('span.help:not([data-tip-en])');
    for (var i = 0; i < icons.length; i++) upgradeOne(icons[i]);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { upgradeHelpIcons(); });
  } else {
    upgradeHelpIcons();
  }
  window.upgradeHelpIcons = upgradeHelpIcons;   // exposed for client-rendered content
  window._upgradeHelpIcon = upgradeOne;         // JIT hook used by the pointerover/click handlers
})();

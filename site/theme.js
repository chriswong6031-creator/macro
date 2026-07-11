/* Theme + language toggles, shared across pages. The no-flash init runs inline
   in <head> (sets data-theme AND data-lang before paint); this file wires the
   buttons and broadcasts change events. */
(function () {
  var docEl = document.documentElement;

  /* Supabase account config — BAKED IN at build time (scripts/build_site.py
     replaces the token below with the project URL + public publishable key, or
     `null` for a local-only build). A page that sets window.SUPABASE_CFG inline
     (e.g. watchlist.html) wins, so the value is identical either way. The
     publishable key is PUBLIC by design; per-user isolation is enforced by RLS. */
  window.SUPABASE_CFG = window.SUPABASE_CFG || {"url": "https://fsldfzlxyavsuwqbceod.supabase.co", "anonKey": "sb_publishable_f33VG8fZuyIZPl_lZIDX3w_RFuuZtpv"};

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

  /* ---- Mastermind Terminal jump -------------------------------------------
     Single-stock analysis now opens in the Terminal web app. US (stock.html),
     China (china_lookup.html), HK (hk_lookup.html), Canada (canada_stock.html),
     and International (intl_stock.html) stock links all route to
     app.mastermind-x.com/terminal?sym=TICKER — their ticker formats (e.g.
     600519.SS, 0002.HK, AAV.TO, 8035.T) already match the Terminal manifest
     exactly so no transformation is needed. The origin is pre-warmed (DNS + TLS)
     so the first navigation is instant.
     Flip window.MM_TERMINAL = false anywhere to restore in-page analyzers. */
  var MM_TERMINAL_BASE = 'https://app.mastermind-x.com/terminal';
  function mmTerminalOn() { return window.MM_TERMINAL !== false; }
  // from=macro lets the Terminal show its prominent "back to Dashboard" button reliably even when the
  // referrer is stripped (the Terminal also falls back to document.referrer when this param is absent).
  function terminalUrl(t) { return MM_TERMINAL_BASE + '?sym=' + encodeURIComponent(t) + '&from=macro'; }
  (function prewarmTerminal() {
    if (!mmTerminalOn() || !document.head) return;
    ['preconnect', 'dns-prefetch'].forEach(function (rel) {
      var l = document.createElement('link');
      l.rel = rel; l.href = 'https://app.mastermind-x.com';
      if (rel === 'preconnect') l.crossOrigin = '';
      document.head.appendChild(l);
    });
  })();
  // Re-route Terminal-covered analyzer links anywhere on the site → Terminal
  // (capture phase so it runs before the browser follows the <a>). Leaves
  // new-tab / modified clicks alone.
  // null-prototype map so an href-derived key can't hit Object.prototype ('constructor', etc.)
  var TERMINAL_PAGES = Object.assign(Object.create(null), { 'stock.html': 1, 'china_lookup.html': 1, 'hk_lookup.html': 1, 'canada_stock.html': 1, 'intl_stock.html': 1 });
  // The ticker a Terminal-covered analyzer link points at (else null). Shared by the
  // hover-prefetch and the click-reroute below so the two can never drift.
  function terminalTicker(a) {
    if (!a || a.target === '_blank') return null;
    var href = a.getAttribute('href') || '', h = href.indexOf('#');
    if (h < 0) return null;
    var page = href.slice(0, h).replace(/[?].*$/, '').replace(/.*\//, '');
    if (!TERMINAL_PAGES[page]) return null;       // only Terminal-covered analyzers
    var t = href.slice(h + 1);
    return t ? decodeURIComponent(t) : null;
  }
  // Warm the SPECIFIC destination on hover / touch intent so the click navigation lands
  // on an already-fetched document (the origin is pre-connected above; this adds the
  // ?sym= page itself). Deduped per ticker; a failed/uncacheable prefetch is a silent no-op.
  var _mmPrefetched = Object.create(null);
  function prefetchTerminal(t) {
    if (!t || _mmPrefetched[t] || !document.head) return;
    _mmPrefetched[t] = 1;
    var l = document.createElement('link');
    l.rel = 'prefetch'; l.as = 'document'; l.href = terminalUrl(t);
    document.head.appendChild(l);
  }
  ['pointerover', 'touchstart'].forEach(function (evt) {
    document.addEventListener(evt, function (e) {
      if (!mmTerminalOn()) return;
      var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
      prefetchTerminal(terminalTicker(a));
    }, { capture: true, passive: true });
  });
  document.addEventListener('click', function (e) {
    if (!mmTerminalOn() || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    var t = terminalTicker(a);
    if (!t) return;
    e.preventDefault();
    location.href = terminalUrl(t);
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
    var pfx = location.pathname.indexOf('/sectors/') > -1 ? '../' : '';
    var s = document.createElement('script');
    s.src = pfx + 'account.js'; s.async = true;
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

  /* ---- soft-contrast mode --------------------------------------------------
     Injects a <style id="soft-contrast-css"> that adds html.soft-contrast
     overrides: warmer/softer bg + panels in light mode, lifted blacks in dark.
     Measured on the softened light backgrounds: body --text 9.6-10.6:1 (AAA);
     --muted 5.8-6.5:1 (comfortably above the 4.5:1 AA floor).
     Boot: theme.js loads end-of-body, so soft-mode users can see one standard-
     palette paint first on cold load; the hub's <head> boot script also sets the
     class pre-paint, other pages accept the brief swap (delta is subtle). */
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

  function curContrast() {
    try { return localStorage.getItem('contrast') || 'standard'; } catch (e) { return 'standard'; }
  }

  function setContrast(mode) {
    // mode: 'standard' | 'soft'
    try { if (mode === 'soft') { localStorage.setItem('contrast', 'soft'); } else { localStorage.removeItem('contrast'); } } catch (e) {}
    if (mode === 'soft') {
      _applySoftContrastCSS();
      docEl.classList.add('soft-contrast');
    } else {
      docEl.classList.remove('soft-contrast');
    }
    _syncContrastSegment();
    document.dispatchEvent(new CustomEvent('contrastchange', { detail: mode }));
  }

  // Placeholder replaced after initSettings builds the segment
  function _syncContrastSegment() {}

  // Boot: apply class ASAP (theme.js loads at end of <body> but before DOMContentLoaded)
  (function () {
    try {
      if (localStorage.getItem('contrast') === 'soft') {
        _applySoftContrastCSS();
        docEl.classList.add('soft-contrast');
      }
    } catch (e) {}
  })();
  window.setContrast = setContrast;

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
    { lib: 'stockdata/index.json',       target: 'stock.html',        flag: '🇺🇸', mkt: 'US' },
    { lib: 'chinastockdata/index.json',  target: 'china_lookup.html', flag: '🇨🇳', mkt: 'China' },
    { lib: 'hkstockdata/index.json',     target: 'hk_lookup.html',    flag: '🇭🇰', mkt: 'HK' },
    { lib: 'canadastockdata/index.json', target: 'canada_stock.html', flag: '🇨🇦', mkt: 'Canada' },
    { lib: 'intlstockdata/index.json',   target: 'intl_stock.html',   flag: '🌐', mkt: 'Intl' }
  ];
  function initNavSearch() {
    var box = document.querySelector('.nav-search');
    if (!box) return;
    var input = box.querySelector('input'), sugg = box.querySelector('.nav-sugg');
    if (!input || !sugg) return;
    // lang-aware placeholder: English lives in the attribute, Chinese in data-ph-zh,
    // swapped on langchange (never put a dual-language <span> inside an attribute —
    // the class="" quote breaks it). A page that used to scope the box to one market
    // (data-lib set) now searches the whole world, so relabel it.
    var phEn = input.placeholder, phZh = input.getAttribute('data-ph-zh') || phEn;
    if (box.getAttribute('data-lib')) {
      phEn = 'Search any stock — US, China, HK, Canada & more…';
      phZh = '搜索任意股票 — 美股、A 股、港股、加股等…';
    }
    function setPh() { input.placeholder = document.documentElement.getAttribute('data-lang') === 'zh' ? phZh : phEn; }
    setPh();
    document.addEventListener('langchange', setPh);
    var pfx = location.pathname.indexOf('/sectors/') > -1 ? '../' : '';
    // merge every market's nightly library into one universe; tag each row with the
    // analyzer it routes to and a market flag (Intl rows carry their own per-country
    // flag + market name, so prefer those when present)
    var lib = [], rows = [], sel = -1, libsLoaded = false;
    // Lazy-load the (heavy) per-market search indexes only once the user engages
    // the search box, not on every page load — 'focus' fires before the first
    // keystroke, so the universe is usually ready by the time they finish typing.
    function loadLibs() {
      if (libsLoaded) return; libsLoaded = true;
      STOCK_MARKETS.forEach(function (m) {
        fetch(pfx + m.lib).then(function (r) { return r.json(); }).then(function (d) {
          (d || []).forEach(function (x) {
            x._tgt = m.target;
            x._fl = x.fl || m.flag;
            x._mk = x.mk || m.mkt;
          });
          lib = lib.concat(d || []);
          if (input.value.trim()) search();   // repaint if they've already typed
        }).catch(function () {});
      });
    }
    input.addEventListener('focus', loadLibs);
    function go(x) {
      if (!x) return;
      // US, China, HK, Canada, and Intl picks all open the Terminal
      if (mmTerminalOn() && TERMINAL_PAGES[x._tgt]) { location.href = terminalUrl(x.t); return; }
      location.href = pfx + (x._tgt || 'stock.html') + '#' + encodeURIComponent(x.t);
    }
    function close() { sugg.classList.remove('show'); sugg.innerHTML = ''; rows = []; sel = -1; }
    function paint() {
      [].forEach.call(sugg.querySelectorAll('.row'), function (r, i) { r.classList.toggle('sel', i === sel); });
    }
    // rank exact ticker > ticker-prefix > name-prefix > loose substring — matters now
    // that one query sweeps thousands of names across five markets
    function rank(x, v) {
      var t = x.t.toUpperCase(), n = (x.n || '').toUpperCase();
      if (t === v) return 0;
      if (t.indexOf(v) === 0) return 1;
      if (n.indexOf(v) === 0) return 2;
      if (t.indexOf(v) > -1) return 3;
      if (n.indexOf(v) > -1) return 4;
      return 9;
    }
    function search() {
      var v = input.value.trim().toUpperCase();
      if (!v) { close(); return; }
      rows = lib.map(function (x) { return { x: x, r: rank(x, v) }; })
        .filter(function (o) { return o.r < 9; })
        .sort(function (a, b) { return a.r - b.r; })
        .slice(0, 10).map(function (o) { return o.x; });
      sel = -1;
      if (!rows.length) { sugg.innerHTML = '<div class="empty">No match across the global library.</div>'; sugg.classList.add('show'); return; }
      sugg.innerHTML = rows.map(function (x, i) {
        var st = (x.st || '').replace(/ /g, '_');
        return '<div class="row" data-i="' + i + '">'
             + (x._fl ? '<span class="mkt" title="' + (x._mk || '') + '">' + x._fl + '</span>' : '')
             + '<b>' + x.t + '</b><small>' + (x.n || '') + '</small>'
             + (x.st ? '<span class="stt st-' + st + '">' + x.st + '</span>' : '') + '</div>';
      }).join('');
      sugg.classList.add('show');
    }
    input.addEventListener('input', search);
    input.addEventListener('focus', function () { if (input.value.trim()) search(); });
    input.addEventListener('keydown', function (e) {
      if (!sugg.classList.contains('show')) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, rows.length - 1); paint(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); paint(); }
      else if (e.key === 'Enter') { e.preventDefault(); go(rows[sel] || rows[0]); }
      else if (e.key === 'Escape') { close(); input.blur(); }
    });
    sugg.addEventListener('mousedown', function (e) {
      var r = e.target.closest('.row'); if (!r) return; e.preventDefault(); go(rows[+r.dataset.i]);
    });
    document.addEventListener('click', function (e) { if (!box.contains(e.target)) close(); });
  }

  /* ---- responsive mobile nav ----------------------------------------------
     The section nav (the .site-nav grid on the macro family; the .topbar flex
     on the vector / commodities / forex / bonds family) packs ~17 links plus
     the theme + language toggles onto one row. On a phone that wrapped into a
     wall of pills that ate half the viewport. We progressively enhance: inject
     a hamburger button + a scoped stylesheet that, below 1260px, collapses the
     links into a tap-to-open dropdown while the toggles stay on one compact
     bar. With JS off the original wrapping nav remains (every link reachable).
     The CSS is injected here — not in theme.css — because the .topbar pages are
     self-contained and never load theme.css. Fallbacks (var(--x, var(--y)))
     bridge the macro palette (--line/--panel) and the vector palette
     (--grid/--card). */
  var NAV_MOBILE_CSS = [
    ".nav-toggle{display:none}",
    "@media (max-width:1259px){",
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
      ".has-nav-toggle .nav-links .nav-dd-menu{position:static;transform:none;min-width:0;margin:0;padding:0;border:none;box-shadow:none;background:transparent;max-height:0;overflow:hidden;opacity:0;visibility:visible;transition:max-height .28s ease,opacity .18s ease}",
      ".has-nav-toggle .nav-links .nav-dd.open>.nav-dd-menu{max-height:600px;opacity:1;padding:0 0 6px 12px}",
      ".has-nav-toggle .nav-links .nav-dd-menu a{display:block;padding:9px 12px;font-size:14px;font-weight:500;white-space:normal}",
      ".has-nav-toggle .nav-links .nav-dd-menu a .d{display:block;font-size:11px;opacity:.65;font-weight:400}",
      /* 3rd-tier accordion (Other Assets ▸ Bitcoin Vector / Commodities ▸ …):
         the fly-out becomes a deeper-indented inline accordion; the ▸ caret
         rotates to point down when its branch is open. */
      ".has-nav-toggle .nav-links .nav-sub>a.nav-sub-trig{display:flex;align-items:center}",
      ".has-nav-toggle .nav-links .nav-sub>a.nav-sub-trig .caret-r{margin-left:auto;display:inline-block;transition:transform .2s}",
      ".has-nav-toggle .nav-links .nav-sub.open>a.nav-sub-trig .caret-r{transform:rotate(90deg)}",
      ".has-nav-toggle .nav-links .nav-sub::after{display:none}",
    "}",
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
        if (window.innerWidth > 1259) return;
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
    // close after a destination link is picked, on Escape, on outside tap, on widen
    links.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (a && !a.closest('.nav-dd') || (a && a.closest('.nav-dd-menu'))) closeNav();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeNav(); });
    document.addEventListener('click', function (e) { if (!nav.contains(e.target)) closeNav(); });
    window.addEventListener('resize', function () { if (window.innerWidth > 1259) closeNav(); });
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
    contrast: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none" opacity=".45"/><circle cx="12" cy="12" r="9"/></svg>'
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

  /* ---- account panel state ------------------------------------------------ */
  var _acctPanelOpen = false;
  var _acctPanelBuilt = false;
  var _acctBusyFlag = false;
  var _acctClosePanelFn = null;  // set by initSettings, called from outside

  /* ---- account panel labels ----------------------------------------------- */
  var ACCT_L = {
    back:       ['‹ Back', '‹ 返回'],
    myAcct:     ['My account', '我的账户'],
    memberSince:['Member since', '注册于'],
    dispName:   ['Display name', '显示名称'],
    dispNamePh: ['Your name', '你的名字'],
    saveBtn:    ['Save', '保存'],
    cancelBtn:  ['Cancel', '取消'],
    saving:     ['Saving…', '保存中…'],
    changeEmail:['Change email', '修改邮箱'],
    newEmail:   ['New email address', '新邮箱地址'],
    emailNote:  ['A confirmation link will be sent to both addresses.', '两个邮箱地址都会收到确认链接。'],
    sendConfirm:['Send confirmation', '发送确认'],
    emailSent:  ['Confirmation sent to both addresses.', '确认链接已发送至两个邮箱。'],
    changePw:   ['Change password', '修改密码'],
    newPw:      ['New password', '新密码'],
    newPwPh:    ['At least 8 characters', '至少 8 个字符'],
    confirmPw:  ['Confirm password', '确认密码'],
    confirmPwPh:['Repeat new password', '再次输入新密码'],
    updatePw:   ['Update password', '更新密码'],
    pwOk:       ['Password updated.', '密码已更新。'],
    pwMismatch: ['Passwords don’t match.', '两次密码不一致。'],
    pwShort:    ['Use at least 8 characters.', '至少 8 个字符。'],
    prefsSync:  ['Theme & language sync', '主题与语言同步'],
    prefsSaved: ['Preferences saved to your account.', '偏好已保存至账户。'],
    prefsNote:  ['Your theme and language follow you across devices.', '你的主题和语言会在所有设备间同步。'],
    signOut:    ['Sign out', '退出登录'],
    guestTitle: ['Access session', '访问会话'],
    guestNote:  ['You’re in with the site access password. Create a free account to manage email, password & sync preferences.', '你正通过站点访问密码登录。注册免费账户以管理邮箱、密码并同步偏好。'],
    createAcct: ['Create free account', '注册免费账户'],
    errGen:     ['Something went wrong — please try again.', '出错了，请重试。'],
    validEmail: ['Enter a valid email address.', '请输入有效的邮箱地址。']
  };
  function _AL(k) { var p = ACCT_L[k]; return p ? p[curLang() === 'zh' ? 1 : 0] : ''; }
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
    // Feature 5: three-way theme segment labels
    themeLight: ['Light', '浅色'],
    themeAuto:  ['Auto', '自动'],
    themeDark:  ['Dark', '深色'],
    fxOn:    ['On', '开'],
    fxOff:   ['Off', '关'],
    // Feature 7: live prices
    liveP:   ['Live prices', '实时报价'],
    // Soft-contrast row
    contrast:         ['Contrast', '对比度'],
    contrastStandard: ['Standard', '标准'],
    contrastSoft:     ['Soft', '柔和']
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
    '.settings-close{margin-left:auto;width:24px;height:24px;border-radius:7px;border:1px solid transparent;background:transparent;color:var(--muted,var(--ink-3));cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:none;transition:background .18s,color .18s}',
    '.settings-close:hover{background:var(--panel2,var(--card));color:var(--text,var(--ink))}',
    '.settings-close svg{width:15px;height:15px}',
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
    '.set-toggle-btn:focus-visible{outline:2px solid var(--link,var(--blue));outline-offset:2px}',
    /* ---- account panel ("page 2" inside the settings-pop) ------------------
       .set-acct-panel overlays the pane content when open: absolute fill inside
       the already-positioned .settings-pop, with its own scroll so content can
       overflow; slides in from the right using translateX. */
    '.settings-pop{overflow:hidden}',
    '.set-acct-panel{position:absolute;inset:0;z-index:10;background:color-mix(in srgb,var(--panel,var(--card)) 76%,transparent);-webkit-backdrop-filter:saturate(180%) blur(22px);backdrop-filter:saturate(180%) blur(22px);border-radius:16px;overflow-y:auto;overscroll-behavior:contain;transform:translateX(100%);transition:transform .22s cubic-bezier(.32,1.3,.5,1);display:flex;flex-direction:column}',
    '.set-acct-panel.open{transform:translateX(0)}',
    '@media (prefers-reduced-motion:reduce){.set-acct-panel{transition:transform .12s ease}}',
    '.sap-head{display:flex;align-items:center;gap:8px;padding:13px 13px 10px;flex:none;border-bottom:1px solid color-mix(in srgb,var(--line,var(--grid)) 60%,transparent)}',
    '.sap-back{display:inline-flex;align-items:center;gap:5px;background:transparent;border:0;color:var(--link,var(--blue,#4f8cff));font-size:12.5px;font-weight:700;cursor:pointer;padding:5px 6px;border-radius:8px;font-family:inherit;transition:background .15s}',
    '.sap-back:hover{background:color-mix(in srgb,var(--link,var(--blue)) 12%,transparent)}',
    '.sap-head-title{flex:1;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--muted,var(--ink-3));text-align:center}',
    '.sap-body{padding:13px;flex:1}',
    /* identity row */
    '.sap-id{display:flex;align-items:center;gap:10px;padding:11px;background:var(--panel2,var(--card));border:1px solid var(--line,var(--grid));border-radius:11px;margin-bottom:11px}',
    '.sap-avatar{flex:none;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--link,var(--blue,#4f8cff)),color-mix(in srgb,var(--link,var(--blue,#4f8cff)) 55%,#9b5cff))}',
    '.sap-id-main{flex:1;min-width:0}',
    '.sap-id-email{display:block;font-size:13px;font-weight:700;color:var(--text,var(--ink));overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sap-id-since{display:block;font-size:11px;color:var(--muted,var(--ink-3));margin-top:2px}',
    /* section rows */
    '.sap-sec{margin-bottom:9px}',
    '.sap-sec-t{font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--muted,var(--ink-3));margin:0 2px 6px;display:block}',
    '.sap-row{background:var(--panel2,var(--card));border:1px solid var(--line,var(--grid));border-radius:11px;padding:10px 11px}',
    '.sap-row+.sap-row{margin-top:7px}',
    '.sap-row-lbl{display:block;font-size:12px;font-weight:700;color:var(--muted,var(--ink-3));margin-bottom:6px}',
    /* inline edit */
    '.sap-inline{display:flex;align-items:center;gap:8px}',
    '.sap-inline-val{flex:1;font-size:13px;color:var(--text,var(--ink));min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.sap-edit-btn{flex:none;font-size:11.5px;font-weight:700;color:var(--link,var(--blue,#4f8cff));background:transparent;border:1px solid var(--line,var(--grid));border-radius:8px;padding:5px 10px;cursor:pointer;font-family:inherit;transition:border-color .15s,background .15s}',
    '.sap-edit-btn:hover{border-color:var(--link,var(--blue));background:color-mix(in srgb,var(--link,var(--blue)) 10%,transparent)}',
    /* input fields */
    '.sap-in{width:100%;box-sizing:border-box;padding:9px 11px;border-radius:9px;border:1px solid var(--line,var(--grid));background:var(--bg,var(--card,#0b0f1a));color:var(--text,var(--ink));font-size:13.5px;font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s;margin-top:7px;display:block}',
    '.sap-in:focus{border-color:var(--link,var(--blue));box-shadow:0 0 0 3px color-mix(in srgb,var(--link,var(--blue)) 20%,transparent)}',
    /* message / feedback */
    '.sap-msg{font-size:11.5px;line-height:1.4;margin-top:6px;display:none}',
    '.sap-msg.show{display:block}',
    '.sap-msg.ok{color:var(--up,#23c08a)}',
    '.sap-msg.err{color:var(--down,#ff5c6c)}',
    '.sap-note{font-size:11px;color:var(--muted,var(--ink-3));line-height:1.45;margin-top:5px}',
    /* action button row */
    '.sap-btns{display:flex;gap:7px;margin-top:9px;justify-content:flex-end}',
    '.sap-btn{font-size:12.5px;font-weight:700;padding:8px 14px;border-radius:9px;cursor:pointer;border:1px solid var(--line,var(--grid));font-family:inherit;transition:all .15s}',
    '.sap-btn:disabled{opacity:.55;cursor:default}',
    '.sap-btn.primary{background:var(--link,var(--blue));border-color:var(--link,var(--blue));color:#fff}',
    '.sap-btn.primary:hover:not(:disabled){filter:brightness(1.07);transform:translateY(-1px)}',
    '.sap-btn.ghost{background:transparent;color:var(--text,var(--ink))}',
    '.sap-btn.ghost:hover:not(:disabled){border-color:var(--link,var(--blue))}',
    '.sap-btn.danger{background:transparent;color:var(--down,#ff5c6c);border-color:var(--down,#ff5c6c)}',
    '.sap-btn.danger:hover:not(:disabled){background:color-mix(in srgb,var(--down,#ff5c6c) 10%,transparent)}',
    /* prefs-sync row */
    '.sap-prefs-row{display:flex;align-items:center;justify-content:space-between;gap:10px}',
    '.sap-prefs-row .sap-prefs-info{flex:1;min-width:0}',
    '.sap-prefs-row .sap-prefs-lbl{font-size:13px;font-weight:700;color:var(--text,var(--ink))}',
    '.sap-prefs-row .sap-prefs-note{font-size:11px;color:var(--muted,var(--ink-3));margin-top:2px}',
    /* sign-out row */
    '.sap-signout-row{margin-top:7px}',
    /* guest note */
    '.sap-guest{text-align:center;padding:14px 4px}',
    '.sap-guest-title{font-size:14px;font-weight:800;color:var(--text,var(--ink));margin-bottom:7px}',
    '.sap-guest-note{font-size:12px;color:var(--muted,var(--ink-3));line-height:1.55;margin-bottom:14px}',
    '.sap-guest-cta{width:100%;padding:11px;border-radius:11px;background:var(--link,var(--blue));border-color:var(--link,var(--blue));color:#fff;font-size:14px;font-weight:800;cursor:pointer;border:1px solid transparent;font-family:inherit;transition:filter .18s,transform .12s ease}',
    '.sap-guest-cta:hover{filter:brightness(1.07);transform:translateY(-1px)}'
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
        // Live prices row (hidden until LiveQuotes is available)
        '<div class="settings-row" id="set-live-row" style="display:none">' +
          '<span class="sr-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></span>' +
          '<span class="sr-main"><span class="sr-lbl" data-set="liveP"></span></span>' +
          '<span class="sr-ctrl"><button type="button" class="set-toggle-btn" id="set-live-toggle" role="switch" aria-checked="true"><span class="set-toggle-knob"></span></button></span>' +
        '</div>' +
        // Contrast row — Standard / Soft two-segment (label only, no description per operator ruling)
        '<div class="settings-row">' +
          '<span class="sr-ic">' + SET_ICON.contrast + '</span>' +
          '<span class="sr-main"><span class="sr-lbl" data-set="contrast"></span></span>' +
          '<span class="sr-ctrl">' +
            '<div class="set-theme-seg" id="set-contrast-seg" role="group" aria-label="Contrast">' +
              '<button type="button" class="set-seg-btn" id="set-contrast-standard" data-set="contrastStandard"></button>' +
              '<button type="button" class="set-seg-btn" id="set-contrast-soft" data-set="contrastSoft"></button>' +
            '</div>' +
          '</span>' +
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
    // no scrim: a click anywhere outside the gear + its dropdown closes it
    document.addEventListener('mousedown', function (e) { if (isOpen() && !wrap.contains(e.target)) close(); });
    document.addEventListener('keydown', function (e) {
      if (!isOpen() || e.key !== 'Escape') return;
      // account "page 2" open? Escape peels back one layer, not the whole pane
      if (_acctPanelOpen && typeof _acctClosePanelFn === 'function') { _acctClosePanelFn(); return; }
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
      if (bSignin) bSignin.addEventListener('click', function () { close(); openAuthModal('signin'); });
      if (bSignup) bSignup.addEventListener('click', function () { close(); openAuthModal('signup'); });
      if (bSignout) bSignout.addEventListener('click', function () { window.MDXAuth.signOut(); });

      /* ---- ACCOUNT PANEL ("page 2" inside the pane) ---------------------- */
      // Build the panel shell and inject it into the pane (hidden until opened).
      var acctPanel = document.createElement('div');
      acctPanel.className = 'set-acct-panel';
      acctPanel.setAttribute('role', 'region');
      acctPanel.setAttribute('aria-label', 'Account');
      pop.appendChild(acctPanel);

      // Keep a ref to the pane's close fn so the panel can close the whole pane
      _acctClosePanelFn = function () { _closeAcctPanelPanel(); };

      function _closeAcctPanelPanel() {
        acctPanel.classList.remove('open');
        _acctPanelOpen = false;
        // restore focus to the signed-in row
        var mMain2 = pop.querySelector('#set-acct-in .sr-main');
        if (mMain2) mMain2.focus();
      }

      // Helper: show/clear inline message inside the panel
      function _sapMsg(id, text, kind) {
        var m = document.getElementById(id); if (!m) return;
        if (!text) { m.className = 'sap-msg'; m.textContent = ''; return; }
        m.textContent = text;
        m.className = 'sap-msg show ' + (kind || 'err');
      }
      // Helper: busy-state on a button (stores original label)
      function _sapBusy(btn, on, label) {
        if (!btn) return;
        if (on) { btn._sapLbl = btn.textContent; btn.disabled = true; if (label) btn.textContent = label; }
        else { btn.disabled = false; if (btn._sapLbl != null) btn.textContent = btn._sapLbl; }
      }

      // Render the panel content based on current _curUser
      function _renderAcctPanel() {
        if (!acctPanel) return;
        var u = _curUser;
        if (!u) { acctPanel.innerHTML = ''; return; }

        var email = u.email || (u.user_metadata && u.user_metadata.email) || '';
        var meta  = u.user_metadata || {};
        var isGuest = !email;  // access-password sessions have no email in user object

        // Format member-since date
        var since = '';
        try {
          if (u.created_at) {
            since = new Date(u.created_at).toLocaleDateString(
              curLang() === 'zh' ? 'zh-CN' : undefined,
              { year: 'numeric', month: 'short', day: 'numeric' });
          }
        } catch (e) {}

        var initial = email ? email.charAt(0).toUpperCase() : (meta.display_name ? meta.display_name.charAt(0).toUpperCase() : 'U');

        var html = '<div class="sap-head">' +
          '<button type="button" class="sap-back" id="sap-back">' + _AL('back') + '</button>' +
          '<span class="sap-head-title" id="sap-title">' + _AL('myAcct') + '</span>' +
          '<span style="width:56px"></span>' +
        '</div>' +
        '<div class="sap-body">';

        if (isGuest) {
          // Access-password / anonymous session: show explainer + CTA
          html += '<div class="sap-guest">' +
            '<div class="sap-guest-title">' + _AL('guestTitle') + '</div>' +
            '<div class="sap-guest-note">' + _AL('guestNote') + '</div>' +
            '<button type="button" class="sap-guest-cta" id="sap-create-acct">' + _AL('createAcct') + '</button>' +
          '</div>';
        } else {
          // Real Supabase session — full account management
          // a) Identity row
          html += '<div class="sap-id">' +
            '<span class="sap-avatar" id="sap-avatar">' + initial + '</span>' +
            '<span class="sap-id-main">' +
              '<span class="sap-id-email" id="sap-id-email">' + _escHtml(email) + '</span>' +
              (since ? '<span class="sap-id-since">' + _AL('memberSince') + ' ' + _escHtml(since) + '</span>' : '') +
            '</span>' +
          '</div>';

          // b) Display name
          var dispName = meta.display_name || '';
          html += '<div class="sap-sec">' +
            '<div class="sap-row" id="sap-name-row">' +
              '<span class="sap-row-lbl">' + _AL('dispName') + '</span>' +
              '<div class="sap-inline">' +
                '<span class="sap-inline-val" id="sap-name-val">' + _escHtml(dispName || '—') + '</span>' +
                '<button type="button" class="sap-edit-btn" id="sap-name-edit">Edit</button>' +
              '</div>' +
              '<input type="text" class="sap-in" id="sap-name-in" placeholder="' + _AL('dispNamePh') + '" value="' + _escHtml(dispName) + '" style="display:none">' +
              '<div class="sap-msg" id="sap-name-msg"></div>' +
              '<div class="sap-btns" id="sap-name-btns" style="display:none">' +
                '<button type="button" class="sap-btn ghost" id="sap-name-cancel">' + _AL('cancelBtn') + '</button>' +
                '<button type="button" class="sap-btn primary" id="sap-name-save">' + _AL('saveBtn') + '</button>' +
              '</div>' +
            '</div>' +
          '</div>';

          // c) Change email
          html += '<div class="sap-sec">' +
            '<div class="sap-row" id="sap-email-row">' +
              '<span class="sap-row-lbl">' + _AL('changeEmail') + '</span>' +
              '<div class="sap-inline">' +
                '<span class="sap-inline-val">' + _escHtml(email) + '</span>' +
                '<button type="button" class="sap-edit-btn" id="sap-email-edit">Edit</button>' +
              '</div>' +
              '<input type="email" class="sap-in" id="sap-email-in" placeholder="' + _AL('newEmail') + '" style="display:none">' +
              '<div class="sap-msg" id="sap-email-msg"></div>' +
              '<p class="sap-note" id="sap-email-note" style="display:none">' + _AL('emailNote') + '</p>' +
              '<div class="sap-btns" id="sap-email-btns" style="display:none">' +
                '<button type="button" class="sap-btn ghost" id="sap-email-cancel">' + _AL('cancelBtn') + '</button>' +
                '<button type="button" class="sap-btn primary" id="sap-email-save">' + _AL('sendConfirm') + '</button>' +
              '</div>' +
            '</div>' +
          '</div>';

          // d) Change password
          html += '<div class="sap-sec">' +
            '<div class="sap-row" id="sap-pw-row">' +
              '<span class="sap-row-lbl">' + _AL('changePw') + '</span>' +
              '<div class="sap-inline">' +
                '<span class="sap-inline-val" style="color:var(--muted,var(--ink-3))">••••••••</span>' +
                '<button type="button" class="sap-edit-btn" id="sap-pw-edit">Edit</button>' +
              '</div>' +
              '<input type="password" class="sap-in" id="sap-pw-in" placeholder="' + _AL('newPwPh') + '" autocomplete="new-password" style="display:none">' +
              '<input type="password" class="sap-in" id="sap-pw2-in" placeholder="' + _AL('confirmPwPh') + '" autocomplete="new-password" style="display:none">' +
              '<div class="sap-msg" id="sap-pw-msg"></div>' +
              '<div class="sap-btns" id="sap-pw-btns" style="display:none">' +
                '<button type="button" class="sap-btn ghost" id="sap-pw-cancel">' + _AL('cancelBtn') + '</button>' +
                '<button type="button" class="sap-btn primary" id="sap-pw-save">' + _AL('updatePw') + '</button>' +
              '</div>' +
            '</div>' +
          '</div>';

          // e) Preference sync indicator
          html += '<div class="sap-sec">' +
            '<div class="sap-row">' +
              '<div class="sap-prefs-row">' +
                '<div class="sap-prefs-info">' +
                  '<div class="sap-prefs-lbl">' + _AL('prefsSync') + '</div>' +
                  '<div class="sap-prefs-note">' + _AL('prefsNote') + '</div>' +
                '</div>' +
              '</div>' +
              '<div class="sap-msg" id="sap-prefs-msg"></div>' +
            '</div>' +
          '</div>';

          // f) Sign out
          html += '<div class="sap-sec sap-signout-row">' +
            '<button type="button" class="sap-btn danger" id="sap-signout" style="width:100%">' + _AL('signOut') + '</button>' +
          '</div>';
        }

        html += '</div>';  // end sap-body
        acctPanel.innerHTML = html;

        // Wire back button
        var backBtn = document.getElementById('sap-back');
        if (backBtn) backBtn.addEventListener('click', function () { _closeAcctPanelPanel(); });

        if (isGuest) {
          // Wire create-account button
          var ctaBtn = document.getElementById('sap-create-acct');
          if (ctaBtn) ctaBtn.addEventListener('click', function () {
            _closeAcctPanelPanel(); close(); openAuthModal('signup');
          });
          return;
        }

        // Wire sign-out
        var soBtn = document.getElementById('sap-signout');
        if (soBtn) soBtn.addEventListener('click', function () { window.MDXAuth.signOut(); _closeAcctPanelPanel(); });

        // ---- Display name inline edit ----
        var nameEdit = document.getElementById('sap-name-edit');
        var nameIn   = document.getElementById('sap-name-in');
        var nameBtns = document.getElementById('sap-name-btns');
        var nameVal  = document.getElementById('sap-name-val');
        if (nameEdit && nameIn && nameBtns) {
          nameEdit.addEventListener('click', function () {
            nameIn.style.display = ''; nameBtns.style.display = '';
            nameEdit.style.display = 'none'; nameIn.focus();
          });
          var nameCancelBtn = document.getElementById('sap-name-cancel');
          if (nameCancelBtn) nameCancelBtn.addEventListener('click', function () {
            nameIn.style.display = 'none'; nameBtns.style.display = 'none';
            nameEdit.style.display = ''; _sapMsg('sap-name-msg', '');
          });
          var nameSaveBtn = document.getElementById('sap-name-save');
          if (nameSaveBtn) nameSaveBtn.addEventListener('click', function () {
            var val = (nameIn.value || '').trim();
            _sapMsg('sap-name-msg', '');
            _sapBusy(nameSaveBtn, true, _AL('saving'));
            getSupabaseClient().then(function (sb) {
              if (!sb) throw new Error('no-client');
              return sb.auth.updateUser({ data: { display_name: val } });
            }).then(function (res) {
              _sapBusy(nameSaveBtn, false);
              if (res && res.error) throw res.error;
              // optimistic UI update
              if (nameVal) nameVal.textContent = val || '—';
              // update _curUser metadata locally
              if (_curUser && _curUser.user_metadata) _curUser.user_metadata.display_name = val;
              var av = document.getElementById('sap-avatar');
              if (av && val) av.textContent = val.charAt(0).toUpperCase();
              nameIn.style.display = 'none'; nameBtns.style.display = 'none';
              nameEdit.style.display = '';
              _sapMsg('sap-name-msg', '');
            }).catch(function (err) {
              _sapBusy(nameSaveBtn, false);
              var m = (err && err.message) || _AL('errGen');
              _sapMsg('sap-name-msg', m, 'err');
            });
          });
        }

        // ---- Change email ----
        var emailEdit   = document.getElementById('sap-email-edit');
        var emailIn     = document.getElementById('sap-email-in');
        var emailBtns   = document.getElementById('sap-email-btns');
        var emailNote   = document.getElementById('sap-email-note');
        if (emailEdit && emailIn && emailBtns) {
          emailEdit.addEventListener('click', function () {
            emailIn.style.display = ''; emailBtns.style.display = '';
            if (emailNote) emailNote.style.display = '';
            emailEdit.style.display = 'none'; emailIn.focus();
          });
          var emailCancelBtn = document.getElementById('sap-email-cancel');
          if (emailCancelBtn) emailCancelBtn.addEventListener('click', function () {
            emailIn.style.display = 'none'; emailBtns.style.display = 'none';
            if (emailNote) emailNote.style.display = 'none';
            emailEdit.style.display = ''; _sapMsg('sap-email-msg', '');
          });
          var emailSaveBtn = document.getElementById('sap-email-save');
          if (emailSaveBtn) emailSaveBtn.addEventListener('click', function () {
            var val = (emailIn.value || '').trim();
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
              _sapMsg('sap-email-msg', _AL('validEmail'), 'err'); return;
            }
            _sapMsg('sap-email-msg', '');
            _sapBusy(emailSaveBtn, true, _AL('saving'));
            getSupabaseClient().then(function (sb) {
              if (!sb) throw new Error('no-client');
              return sb.auth.updateUser({ email: val });
            }).then(function (res) {
              _sapBusy(emailSaveBtn, false);
              if (res && res.error) throw res.error;
              _sapMsg('sap-email-msg', _AL('emailSent'), 'ok');
              emailIn.value = '';
            }).catch(function (err) {
              _sapBusy(emailSaveBtn, false);
              var m = (err && err.message) || _AL('errGen');
              _sapMsg('sap-email-msg', m, 'err');
            });
          });
        }

        // ---- Change password ----
        var pwEdit   = document.getElementById('sap-pw-edit');
        var pwIn     = document.getElementById('sap-pw-in');
        var pw2In    = document.getElementById('sap-pw2-in');
        var pwBtns   = document.getElementById('sap-pw-btns');
        if (pwEdit && pwIn && pw2In && pwBtns) {
          pwEdit.addEventListener('click', function () {
            pwIn.style.display = ''; pw2In.style.display = ''; pwBtns.style.display = '';
            pwEdit.style.display = 'none'; pwIn.focus();
          });
          var pwCancelBtn = document.getElementById('sap-pw-cancel');
          if (pwCancelBtn) pwCancelBtn.addEventListener('click', function () {
            pwIn.style.display = 'none'; pw2In.style.display = 'none'; pwBtns.style.display = 'none';
            pwEdit.style.display = ''; pwIn.value = ''; pw2In.value = ''; _sapMsg('sap-pw-msg', '');
          });
          var pwSaveBtn = document.getElementById('sap-pw-save');
          if (pwSaveBtn) pwSaveBtn.addEventListener('click', function () {
            var p1 = pwIn.value || '', p2 = pw2In.value || '';
            if (p1.length < 8) { _sapMsg('sap-pw-msg', _AL('pwShort'), 'err'); return; }
            if (p1 !== p2)     { _sapMsg('sap-pw-msg', _AL('pwMismatch'), 'err'); return; }
            _sapMsg('sap-pw-msg', '');
            _sapBusy(pwSaveBtn, true, _AL('saving'));
            getSupabaseClient().then(function (sb) {
              if (!sb) throw new Error('no-client');
              return sb.auth.updateUser({ password: p1 });
            }).then(function (res) {
              _sapBusy(pwSaveBtn, false);
              if (res && res.error) throw res.error;
              _sapMsg('sap-pw-msg', _AL('pwOk'), 'ok');
              pwIn.value = ''; pw2In.value = '';
              setTimeout(function () {
                pwIn.style.display = 'none'; pw2In.style.display = 'none'; pwBtns.style.display = 'none';
                pwEdit.style.display = ''; _sapMsg('sap-pw-msg', '');
              }, 1200);
            }).catch(function (err) {
              _sapBusy(pwSaveBtn, false);
              var m = (err && err.message) || _AL('errGen');
              _sapMsg('sap-pw-msg', m, 'err');
            });
          });
        }
      }  // end _renderAcctPanel

      // Open the account panel (slide in page 2)
      function _openAcctPanel() {
        if (!_authEnabled || !_curUser) return;
        _renderAcctPanel();
        acctPanel.classList.add('open');
        _acctPanelOpen = true;
        var backBtn2 = document.getElementById('sap-back');
        if (backBtn2) setTimeout(function () { backBtn2.focus(); }, 80);
      }

      // Hook: apply server prefs on sign-in, then show prefs-saved toast on change
      window.addEventListener('mdx-auth', function (e) {
        var detail = e && e.detail;
        if (detail && detail.event === 'SIGNED_IN' && detail.user) {
          _applyServerPrefs(detail.user);
        }
        // If panel is open and user signed out, close the panel
        if (detail && detail.event === 'SIGNED_OUT' && _acctPanelOpen) {
          _closeAcctPanelPanel();
        }
      });

      // Wire pref sync hooks (once per page)
      _hookPrefSync();

      // clicking the signed-in row opens the account panel (page 2)
      var mMain = pop.querySelector('#set-acct-in .sr-main');
      if (mMain) {
        mMain.style.cursor = 'pointer';
        mMain.setAttribute('role', 'button'); mMain.setAttribute('tabindex', '0');
        var _openMgr = function () { _openAcctPanel(); };
        mMain.addEventListener('click', _openMgr);
        mMain.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _openMgr(); } });
      }

      // (Escape handling for the panel lives in the pane's own keydown handler,
      // which peels the panel layer first — same-node listener order made a
      // separate handler here fire too late to stop the pane from closing.)

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

    // ---- Contrast segment: Standard / Soft ----------------------------------
    var _cStd = pop.querySelector('#set-contrast-standard'),
        _cSft = pop.querySelector('#set-contrast-soft');
    function _syncContrastSegNow() {
      var isSoft = curContrast() === 'soft';
      function _seg(el, on) {
        if (!el) return;
        el.classList.toggle('active', on);
        el.setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      _seg(_cStd, !isSoft);
      _seg(_cSft, isSoft);
    }
    _syncContrastSegment = _syncContrastSegNow;
    _syncContrastSegNow();
    if (_cStd) _cStd.addEventListener('click', function () { setContrast('standard'); });
    if (_cSft) _cSft.addEventListener('click', function () { setContrast('soft'); });
    document.addEventListener('contrastchange', function () { _syncContrastSegNow(); });

    // ---- Feature 7: wire the Live-prices toggle (hub-optional) ---------------
    var _liveRow = pop.querySelector('#set-live-row'), _liveToggle = pop.querySelector('#set-live-toggle');
    function _updateLiveRow() {
      if (!_liveRow) return;
      _liveRow.style.display = (typeof window.LiveQuotes !== 'undefined') ? '' : 'none';
    }
    // Check after DOM ready (LiveQuotes may not be set yet at initSettings time)
    document.addEventListener('DOMContentLoaded', function () { _updateLiveRow(); });
    _updateLiveRow();
    // Initial state from localStorage (liveOff='1' = paused)
    function _liveOff() { try { return localStorage.getItem('liveOff') === '1'; } catch (e) { return false; } }
    function _setLiveAria() {
      if (_liveToggle) _liveToggle.setAttribute('aria-checked', _liveOff() ? 'false' : 'true');
    }
    _setLiveAria();
    if (_liveToggle) _liveToggle.addEventListener('click', function () {
      if (_liveOff()) {
        try { localStorage.removeItem('liveOff'); } catch (e) {}
        if (window.LiveQuotes && typeof window.LiveQuotes.resume === 'function') window.LiveQuotes.resume();
      } else {
        try { localStorage.setItem('liveOff', '1'); } catch (e) {}
        if (window.LiveQuotes && typeof window.LiveQuotes.pause === 'function') window.LiveQuotes.pause();
      }
      _setLiveAria();
    });

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
      // click: open settings pane scrolled/focused to the ACCOUNT section
      signinLink.addEventListener('click', function (e) {
        e.preventDefault();
        open();
        var acctSec = pop.querySelector('#set-acct-sec');
        if (acctSec) { setTimeout(function () { acctSec.scrollIntoView({ block: 'nearest' }); var btn = acctSec.querySelector('button'); if (btn) btn.focus(); }, 60); }
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

    document.addEventListener('pointerover', function (e) {
      if (!e.target || !e.target.closest) return;
      var row = e.target.closest('[data-rpop]');
      if (row) {
        clearTimeout(closeT); clearTimeout(openT);
        if (row !== cur) openT = setTimeout(function () { open(row); }, 70);
        return;
      }
      if (!pop.hidden && e.target.closest('.row-pop')) { clearTimeout(closeT); return; }
      // a scroll shifts content under a stationary pointer, firing pointerover on whatever
      // slid beneath it — that must not count as the user leaving the row
      if (Date.now() - lastScroll < 250) return;
      if (cur || openT) { clearTimeout(openT); openT = 0; if (cur) scheduleClose(160); }
    });
    document.addEventListener('pointerout', function (e) {
      if (!e.relatedTarget && cur) scheduleClose(160);   // pointer left the window
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
    initNavSearch();
    initActiveNav();
    initMobileNav();
    initShowMore();
    pinBoardTrackToggle();
    initListCollapse();
    initListOverlay();
    initRowPop();
    themeCharts();
  });
  // charts may finish drawing after DOMContentLoaded; re-theme once more on load
  window.addEventListener('load', function () { themeCharts(); wrapTables(); });
})();

/* ---- i18n tooltip: [data-tip-en] / [data-tip-zh] ----------------------------------
   The replacement for bilingual title="EN · 中文" attributes. The i18n rule is that
   translated text NEVER goes in HTML attributes — the dual-span l-en/l-zh mechanism
   cannot operate inside an attribute, so a native tooltip always shows both languages
   mashed together. Instead, chips carry data-tip-en / data-tip-zh and this delegated
   handler shows ONE body-appended popover with a dual-span body, so the existing
   [data-lang] CSS picks the active language (and live-updates on toggle).
   Hover/focus on desktop; tap-to-toggle on touch (mirrors the #1061 .nb-cau pattern).
   Body-appended + position:fixed → immune to card overflow clipping on every page. */
(function () {
  var pop = null, cur = null;
  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement('div');
    pop.className = 'i18n-tip-pop';
    pop.setAttribute('role', 'tooltip');
    document.body.appendChild(pop);
    return pop;
  }
  function hide() {
    if (pop) { pop.style.display = 'none'; }
    cur = null;
  }
  function show(el) {
    var en = el.getAttribute('data-tip-en') || '';
    if (!en) return;
    var zh = el.getAttribute('data-tip-zh') || en;
    ensurePop();
    pop.textContent = '';
    var sEn = document.createElement('span'); sEn.className = 'l-en'; sEn.textContent = en;
    var sZh = document.createElement('span'); sZh.className = 'l-zh'; sZh.textContent = zh;
    pop.appendChild(sEn); pop.appendChild(sZh);
    // measure hidden, then place: above the trigger by default, below near the top,
    // clamped to the viewport horizontally
    pop.style.visibility = 'hidden'; pop.style.display = 'block';
    var r = el.getBoundingClientRect();
    var w = pop.offsetWidth, h = pop.offsetHeight;
    var left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
    var top = (r.top >= h + 12) ? (r.top - h - 6) : (r.bottom + 6);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    pop.style.visibility = 'visible';
    cur = el;
  }
  document.addEventListener('pointerover', function (e) {
    if (!e.target || !e.target.closest) return;
    var t = e.target.closest('[data-tip-en]');
    if (t) { if (t !== cur) show(t); return; }
    if (pop && pop.style.display === 'block' && pop.contains(e.target)) return; // keep while over the pop
    if (cur) hide();
  }, true);
  document.addEventListener('focusin', function (e) {
    var t = e.target && e.target.closest && e.target.closest('[data-tip-en]');
    if (t) show(t);
  }, true);
  document.addEventListener('focusout', function () { if (cur) hide(); }, true);
  // Touch: tap toggles the tip instead of following the parent card link (the chip is
  // a tiny target; the rest of the card still navigates). Desktop clicks pass through.
  document.addEventListener('click', function (e) {
    if (!window.matchMedia || !window.matchMedia('(hover: none)').matches) return;
    if (!e.target || !e.target.closest) return;
    var t = e.target.closest('[data-tip-en]');
    if (t) {
      e.preventDefault(); e.stopPropagation();
      if (cur === t) { hide(); } else { show(t); }
    } else if (!(pop && pop.contains(e.target))) {
      if (cur) hide();
    }
  }, true);
  window.addEventListener('scroll', function () { if (cur) hide(); }, true);
  window.addEventListener('resize', function () { if (cur) hide(); });
})();

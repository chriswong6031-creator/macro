/* Theme + language toggles, shared across pages. The no-flash init runs inline
   in <head> (sets data-theme AND data-lang before paint); this file wires the
   buttons and broadcasts change events. */
(function () {
  var docEl = document.documentElement;

  /* ---- Google Analytics 4 (gtag.js) ---------------------------------------
     Injected once on EVERY page via this one shared script (every page loads
     theme.js), so there's no per-template tag to maintain. Loads gtag.js async
     and queues the first page_view via dataLayer. Skips localhost / file:// so
     local dev, previews and the admin tool never pollute the property. Set
     GA4_ID to '' to disable site-wide. */
  var GA4_ID = 'G-BZTZ9W1BBB';
  (function loadGA4() {
    if (!GA4_ID || window.__ga4_loaded) return;
    var h = location.hostname;
    if (!h || h === 'localhost' || h === '127.0.0.1' || h === '[::1]') return;
    window.__ga4_loaded = true;
    window.dataLayer = window.dataLayer || [];
    function gtag() { dataLayer.push(arguments); }
    window.gtag = gtag;
    gtag('js', new Date());
    gtag('config', GA4_ID);
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA4_ID;
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
  window.toggleTheme = function () { setTheme(curTheme() === 'light' ? 'dark' : 'light'); };

  /* ---- language (en default) ----------------------------------------------- */
  function curLang() { return docEl.getAttribute('data-lang') || 'en'; }
  function setLang(lg) {
    docEl.setAttribute('data-lang', lg);
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
    var lib = [], rows = [], sel = -1;
    STOCK_MARKETS.forEach(function (m) {
      fetch(pfx + m.lib).then(function (r) { return r.json(); }).then(function (d) {
        (d || []).forEach(function (x) {
          x._tgt = m.target;
          x._fl = x.fl || m.flag;
          x._mk = x.mk || m.mkt;
        });
        lib = lib.concat(d || []);
      }).catch(function () {});
    });
    function go(x) { if (x) location.href = pfx + (x._tgt || 'stock.html') + '#' + encodeURIComponent(x.t); }
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
     a hamburger button + a scoped stylesheet that, below 700px, collapses the
     links into a tap-to-open dropdown while the toggles stay on one compact
     bar. With JS off the original wrapping nav remains (every link reachable).
     The CSS is injected here — not in theme.css — because the .topbar pages are
     self-contained and never load theme.css. Fallbacks (var(--x, var(--y)))
     bridge the macro palette (--line/--panel) and the vector palette
     (--grid/--card). */
  var NAV_MOBILE_CSS = [
    ".nav-toggle{display:none}",
    "@media (max-width:700px){",
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
        if (window.innerWidth > 700) return;
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
    window.addEventListener('resize', function () { if (window.innerWidth > 700) closeNav(); });
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
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0z"/></svg>'
  };
  var SET_L = {
    title:   ['Settings', '设置'],
    sub:     ['Personalize your workspace', '个性化你的工作区'],
    prefs:   ['Preferences', '偏好设置'],
    theme:   ['Appearance', '外观'],
    themeD:  ['Switch dark / light mode', '切换深色 / 浅色模式'],
    lang:    ['Language', '语言'],
    langD:   ['English · 中文', 'English · 中文'],
    account: ['Account', '账户'],
    soon:    ['Soon', '即将推出'],
    acctD:   ['Sign in to sync your watchlists, alerts and settings across devices.',
              '登录即可在各设备间同步自选、提醒与设置。'],
    signin:  ['Sign in', '登录'],
    signup:  ['Create account', '注册']
  };
  var SETTINGS_CSS = [
    /* two-row nav: the menu takes the whole first row on its own line; the global
       search + the Mastermind / Terminal / GEAR cluster sit together on the second
       row. Injected here — not only in theme.css — so the self-contained vector /
       forex / bonds / commodities family (which never loads theme.css) gets the
       exact same two-row bar live, no rebuild, same pattern as the mobile-nav CSS
       above. >700px only; the <=700px collapse (flex + has-nav-toggle) overrides. */
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
    '.settings-pop{position:absolute;top:calc(100% + 9px);right:0;z-index:100000;width:min(340px,calc(100vw - 20px));box-sizing:border-box;background:var(--panel,var(--card));border:1px solid color-mix(in srgb,var(--text,#e7ecf6) 14%,var(--line,var(--grid)));border-radius:15px;box-shadow:0 18px 50px -12px rgba(0,0,0,.62),0 4px 14px rgba(0,0,0,.3),inset 0 1px 0 color-mix(in srgb,var(--text,#fff) 6%,transparent);padding:13px;transform-origin:top right;opacity:0;visibility:hidden;pointer-events:none;transform:translateY(-8px) scale(.97);transition:opacity .16s ease,transform .2s cubic-bezier(.32,1.3,.5,1),visibility 0s linear .2s;font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif}',
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
    '@media (prefers-reduced-motion:reduce){.settings-pop{transition:opacity .14s ease,visibility 0s linear .14s}.settings-pop.open,.nav-settings:hover .settings-pop,.nav-settings:focus-within .settings-pop{transition:opacity .14s ease}.nav-settings-btn:hover svg,.nav-settings-btn[aria-expanded="true"] svg,.nav-settings:hover .nav-settings-btn svg,.nav-settings:focus-within .nav-settings-btn svg{transform:none}}'
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
        '<div class="settings-row">' +
          '<span class="sr-ic">' + SET_ICON.theme + '</span>' +
          '<span class="sr-main"><span class="sr-lbl" data-set="theme"></span><span class="sr-desc" data-set="themeD"></span></span>' +
          '<span class="sr-ctrl" id="set-theme-slot"></span>' +
        '</div>' +
        '<div class="settings-row">' +
          '<span class="sr-ic">' + SET_ICON.lang + '</span>' +
          '<span class="sr-main"><span class="sr-lbl" data-set="lang"></span><span class="sr-desc" data-set="langD"></span></span>' +
          '<span class="sr-ctrl" id="set-lang-slot"></span>' +
        '</div>' +
      '</div>' +
      '<div class="settings-sec">' +
        '<div class="settings-sec-t"><span data-set="account"></span><span class="settings-soon" data-set="soon"></span></div>' +
        '<div class="settings-row settings-acct" style="display:block">' +
          '<p class="sa-d" data-set="acctD"></p>' +
          '<div class="sa-btns">' +
            '<button type="button" class="sa-btn ghost" disabled><span class="sr-ic" style="display:inline-flex">' + SET_ICON.user + '</span><span data-set="signin"></span></button>' +
            '<button type="button" class="sa-btn solid" disabled data-set="signup"></button>' +
          '</div>' +
        '</div>' +
      '</div>';

    wrap.appendChild(gear);
    wrap.appendChild(pop);
    ctrls.appendChild(wrap);   // gear + dropdown, pinned at the cluster's end

    // relocate the live toggles into the popover (their listeners ride along)
    if (ts) pop.querySelector('#set-theme-slot').appendChild(ts);
    if (lt) pop.querySelector('#set-lang-slot').appendChild(lt);

    setLabels(pop);
    document.addEventListener('langchange', function () { setLabels(pop); });

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
    document.addEventListener('keydown', function (e) { if (isOpen() && e.key === 'Escape') { close(); gear.focus(); } });
    // Desktop also opens the panel on hover (pure CSS above). If a stray click set
    // .open, make sure leaving the gear + panel always closes it so it never stays
    // pinned under the cursor; touch (no hover) keeps the click / outside / Esc path.
    if (window.matchMedia && window.matchMedia('(hover:hover) and (pointer:fine)').matches) {
      wrap.addEventListener('mouseleave', close);
    }
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

  /* ---- progressive "show more" for standout-stock card grids ---------------
     Any element with [data-showmore="N"] shows its first N child cards and hides
     the rest behind a control bar that reveals them in chunks of N (staggered
     fade-in), or all at once, and can collapse back. Language-aware labels.
     No-ops when total <= N, so it's safe to add the attribute unconditionally. */
  function smBL(en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + zh + '</span>'; }
  function initShowMore() {
    document.querySelectorAll('[data-showmore]').forEach(function (grid) {
      if (grid.dataset.smInit) return;            // idempotent
      grid.dataset.smInit = '1';
      var step = parseInt(grid.getAttribute('data-showmore'), 10) || 12;
      var items = [].filter.call(grid.children, function (el) { return el.nodeType === 1; });
      var total = items.length;
      if (total <= step) return;                  // nothing to collapse
      var shown = step;
      items.forEach(function (el, i) { if (i >= shown) el.classList.add('sm-hidden'); });

      var bar = document.createElement('div'); bar.className = 'sm-bar';
      var count = document.createElement('span'); count.className = 'sm-count';
      var btns = document.createElement('div'); btns.className = 'sm-btns';
      var more = document.createElement('button'); more.type = 'button'; more.className = 'sm-btn';
      var all = document.createElement('button'); all.type = 'button'; all.className = 'sm-btn sm-ghost';
      btns.appendChild(more); btns.appendChild(all);
      bar.appendChild(count); bar.appendChild(btns);
      grid.parentNode.insertBefore(bar, grid.nextSibling);

      function render(animateFrom) {
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
          var next = Math.min(step, remaining);
          more.className = 'sm-btn';
          more.innerHTML = '<span class="sm-ic">▾</span>' + smBL('Show ' + next + ' more', '再显示 ' + next + ' 个');
          all.style.display = '';
          all.innerHTML = smBL('Show all ' + total, '全部显示 ' + total);
        } else {
          more.className = 'sm-btn sm-collapse';
          more.innerHTML = '<span class="sm-ic">▾</span>' + smBL('Show fewer', '收起');
          all.style.display = 'none';
        }
      }
      more.addEventListener('click', function () {
        if (shown >= total) {                      // collapse back to the first page
          shown = step; render();
          grid.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          var from = shown; shown = Math.min(shown + step, total); render(from);
        }
      });
      all.addEventListener('click', function () { var from = shown; shown = total; render(from); });
      render();
    });
  }

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
    });
    initSettings();   // fallback if the early call above could not run
    initNavSearch();
    initActiveNav();
    initMobileNav();
    initShowMore();
    initListCollapse();
    themeCharts();
  });
  // charts may finish drawing after DOMContentLoaded; re-theme once more on load
  window.addEventListener('load', function () { themeCharts(); wrapTables(); });
})();

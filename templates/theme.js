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
    try { localStorage.setItem('theme', tm); } catch (e) {}
    document.querySelectorAll('.theme-btn').forEach(function (b) {
      b.innerHTML = tm === 'light'
        ? '<span class="l-en">🌙 Dark</span><span class="l-zh">🌙 深色</span>'
        : '<span class="l-en">☀️ Light</span><span class="l-zh">☀️ 浅色</span>';
    });
    if (window.hydrateMTF) window.hydrateMTF();
    themeCharts();
    document.dispatchEvent(new CustomEvent('themechange', { detail: tm }));
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

  /* ---- global stock search (unified macro nav) ----------------------------
     The same autocomplete the analyzer uses, promoted into the nav bar: fetch
     the nightly library (stockdata/index.json), suggest, and on pick bounce to
     stock.html#TICKER (the analyzer routes off the hash). Path-depth aware so
     it works from /sectors/ too. No-ops on pages without a .nav-search. */
  function initNavSearch() {
    var box = document.querySelector('.nav-search');
    if (!box) return;
    var input = box.querySelector('input'), sugg = box.querySelector('.nav-sugg');
    // lang-aware placeholder: English lives in the attribute, Chinese in
    // data-ph-zh, swapped on langchange (never put dual-language <span> inside an
    // attribute — the class="" quote breaks it)
    var phEn = input.placeholder, phZh = input.getAttribute('data-ph-zh') || phEn;
    function setPh() { input.placeholder = document.documentElement.getAttribute('data-lang') === 'zh' ? phZh : phEn; }
    setPh();
    document.addEventListener('langchange', setPh);
    var pfx = location.pathname.indexOf('/sectors/') > -1 ? '../' : '';
    // a page can scope the search to its own library + analyzer via data attributes
    // (default = the global nightly library + stock.html, so macro is unchanged)
    var libUrl = box.getAttribute('data-lib') || 'stockdata/index.json';
    var target = box.getAttribute('data-target') || 'stock.html';
    var lib = [], rows = [], sel = -1;
    fetch(pfx + libUrl).then(function (r) { return r.json(); })
      .then(function (d) { lib = d || []; }).catch(function () {});
    function go(t) { location.href = pfx + target + '#' + encodeURIComponent(t); }
    function close() { sugg.classList.remove('show'); sugg.innerHTML = ''; rows = []; sel = -1; }
    function paint() {
      [].forEach.call(sugg.querySelectorAll('.row'), function (r, i) { r.classList.toggle('sel', i === sel); });
    }
    function search() {
      var v = input.value.trim().toUpperCase();
      if (!v) { close(); return; }
      rows = lib.filter(function (x) {
        return x.t.toUpperCase().indexOf(v) > -1 || (x.n || '').toUpperCase().indexOf(v) > -1;
      }).slice(0, 8);
      sel = -1;
      if (!rows.length) { sugg.innerHTML = '<div class="empty">No match in the nightly library.</div>'; sugg.classList.add('show'); return; }
      sugg.innerHTML = rows.map(function (x, i) {
        var st = (x.st || '').replace(/ /g, '_');
        return '<div class="row" data-i="' + i + '"><b>' + x.t + '</b><small>' + (x.n || '') + '</small>'
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
      else if (e.key === 'Enter') { e.preventDefault(); var pick = rows[sel] || rows[0]; if (pick) go(pick.t); }
      else if (e.key === 'Escape') { close(); input.blur(); }
    });
    sugg.addEventListener('mousedown', function (e) {
      var r = e.target.closest('.row'); if (!r) return; e.preventDefault(); go(rows[+r.dataset.i].t);
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
      /* the collapsible link panel (shared by both families) */
      ".has-nav-toggle .nav-links{display:none;position:absolute;top:100%;left:8px;right:8px;z-index:1000;box-sizing:border-box;flex-direction:column;flex-wrap:nowrap;align-items:stretch;gap:1px;margin-top:8px;padding:8px;border-radius:14px;background:var(--panel,var(--card));border:1px solid var(--line,var(--grid));box-shadow:0 18px 44px rgba(16,24,40,.30);max-height:78vh;overflow-y:auto;overflow-x:hidden}",
      ".has-nav-toggle.nav-open .nav-links{display:flex}",
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
    // accordion: tap dropdown parent to toggle submenu (mobile only)
    links.querySelectorAll('.nav-dd').forEach(function(dd) {
      var trigger = dd.querySelector(':scope > a.nav-link');
      if (!trigger) return;
      trigger.addEventListener('click', function(e) {
        if (window.innerWidth > 700) return;
        e.preventDefault(); e.stopPropagation();
        var wasOpen = dd.classList.contains('open');
        links.querySelectorAll('.nav-dd.open').forEach(function(d) { d.classList.remove('open'); });
        if (!wasOpen) dd.classList.add('open');
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
    document.querySelectorAll('.lang-toggle .opt').forEach(function (o) {
      o.addEventListener('click', function () { setLang(o.getAttribute('data-l')); });
    });
    initNavSearch();
    initMobileNav();
    initShowMore();
    themeCharts();
  });
  // charts may finish drawing after DOMContentLoaded; re-theme once more on load
  window.addEventListener('load', function () { themeCharts(); wrapTables(); });
})();

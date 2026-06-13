/* Theme + language toggles, shared across pages. The no-flash init runs inline
   in <head> (sets data-theme AND data-lang before paint); this file wires the
   buttons and broadcasts change events. */
(function () {
  var docEl = document.documentElement;

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
    var pfx = location.pathname.indexOf('/sectors/') > -1 ? '../' : '';
    var lib = [], rows = [], sel = -1;
    fetch(pfx + 'stockdata/index.json').then(function (r) { return r.json(); })
      .then(function (d) { lib = d || []; }).catch(function () {});
    function go(t) { location.href = pfx + 'stock.html#' + encodeURIComponent(t); }
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

  document.addEventListener('DOMContentLoaded', function () {
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
    themeCharts();
  });
  // charts may finish drawing after DOMContentLoaded; re-theme once more on load
  window.addEventListener('load', themeCharts);
})();

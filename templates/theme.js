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

  document.addEventListener('DOMContentLoaded', function () {
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
    themeCharts();
  });
  // charts may finish drawing after DOMContentLoaded; re-theme once more on load
  window.addEventListener('load', themeCharts);
})();

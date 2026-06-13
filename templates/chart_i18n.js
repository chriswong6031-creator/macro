/* Recolour + re-translate Plotly charts on language toggle, in place, with no
   rebuild and no second copy of the chart payload.

   Each page defines:
     window.__CHART_SWAP__ = {
       colors: { "#5fbf7f":"#e07070", "#e07070":"#5fbf7f", ... },  // SYMMETRIC pairs
       labels: { "growth":"增长", "net liquidity":"净流动性", ... }  // en -> zh
     };
   Charts are baked in English. On `langchange` we walk every Plotly graph div and
   Plotly.restyle / Plotly.relayout the matching trace colours, legend names, axis
   titles, shape fills and annotations. Colour pairs are symmetric (both
   directions present), so re-applying the same map flips back to English; label
   text uses an inverted map for zh -> en. */
(function () {
  function swap() { return window.__CHART_SWAP__ || { colors: {}, labels: {} }; }
  function curLang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  function invert(o) { var r = {}; for (var k in o) r[o[k]] = k; return r; }

  function applyToGraph(gd, toZh) {
    if (!gd || !gd.data) return;
    var sw = swap();
    var colors = sw.colors || {};
    var labels = toZh ? (sw.labels || {}) : invert(sw.labels || {});

    // ---- traces: line.color, marker.color (string or per-point array), name ----
    for (var i = 0; i < gd.data.length; i++) {
      var tr = gd.data[i], upd = {}, has = false;
      if (tr.line && colors[tr.line.color]) { upd['line.color'] = colors[tr.line.color]; has = true; }
      if (tr.marker && tr.marker.color != null) {
        var mc = tr.marker.color;
        if (Array.isArray(mc)) {
          upd['marker.color'] = [mc.map(function (c) { return colors[c] || c; })];
          has = true;
        } else if (colors[mc]) { upd['marker.color'] = colors[mc]; has = true; }
      }
      if (tr.name && labels[tr.name]) { upd['name'] = labels[tr.name]; has = true; }
      if (has) { try { Plotly.restyle(gd, upd, [i]); } catch (e) {} }
    }

    // ---- layout: figure title, axis titles, shape fills, annotations ----
    var lay = gd.layout || {}, rl = {};
    if (lay.title && lay.title.text && labels[lay.title.text]) rl['title.text'] = labels[lay.title.text];
    Object.keys(lay).forEach(function (k) {
      if (/^[xy]axis\d*$/.test(k) && lay[k] && lay[k].title) {
        var tx = lay[k].title.text;
        if (tx && labels[tx]) rl[k + '.title.text'] = labels[tx];
      }
    });
    if (Array.isArray(lay.shapes)) lay.shapes.forEach(function (sh, i) {
      if (sh && colors[sh.fillcolor]) rl['shapes[' + i + '].fillcolor'] = colors[sh.fillcolor];
      if (sh && sh.line && colors[sh.line.color]) rl['shapes[' + i + '].line.color'] = colors[sh.line.color];
    });
    if (Array.isArray(lay.annotations)) lay.annotations.forEach(function (an, i) {
      if (an && an.text && labels[an.text]) rl['annotations[' + i + '].text'] = labels[an.text];
    });
    if (Object.keys(rl).length) { try { Plotly.relayout(gd, rl); } catch (e) {} }
  }

  function applyAll(toZh) {
    if (!window.Plotly) return;
    document.querySelectorAll('.js-plotly-plot').forEach(function (gd) { applyToGraph(gd, toZh); });
  }

  // charts are baked English; if the page loads already in zh, flip them once
  function init() { if (curLang() === 'zh') applyAll(true); }
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);

  document.addEventListener('langchange', function (e) { applyAll(e.detail === 'zh'); });
})();

/* Make the Plotly range-selector buttons (1M…All, added in build_site.py) feel
   right: when the user zooms the x-axis, rescale the y-axis to the data actually
   in view. Without this, a 1-month slice of a trending series renders as a flat
   line stuck inside the full 3-year y-range.

   Axes given an explicit range at build time (e.g. the ±1 growth/inflation score
   chart) are left ALONE — their fixed scale is the point. Self-contained; pairs
   with the Plotly bundle already loaded on the page. */
(function () {
  function asNum(v) { v = +v; return isFinite(v) ? v : null; }
  function asMs(x) {
    var t = (x instanceof Date) ? x.getTime() : new Date(x).getTime();
    return isFinite(t) ? t : null;
  }

  // y-axes that carry a build-time range stay fixed (don't auto-rescale them)
  function fixedYAxes(gd) {
    var fixed = {};
    Object.keys(gd.layout || {}).forEach(function (k) {
      if (/^yaxis\d*$/.test(k)) {
        var ax = gd.layout[k];
        if (ax && ax.autorange === false && ax.range) fixed[k.replace('axis', '')] = true;
      }
    });
    return fixed;
  }

  // current [min,max] ms window of a trace's own x-axis ('x'→xaxis, 'x2'→xaxis2)
  function xWindow(gd, xLetter) {
    var key = (xLetter === 'x') ? 'xaxis' : 'xaxis' + xLetter.slice(1);
    var ax = gd.layout[key];
    if (!ax || !ax.range) return null;
    var a = asMs(ax.range[0]), b = asMs(ax.range[1]);
    return (a == null || b == null) ? null : [a, b];
  }

  // compute new y ranges from the points inside each trace's current x window.
  // Use _fullData, not data: Plotly binary-encodes typed arrays in gd.data
  // (y becomes a {dtype,bdata} object); _fullData holds the decoded arrays.
  function visibleYRanges(gd) {
    var bounds = {};
    (gd._fullData || gd.data || []).forEach(function (tr) {
      if (!tr.x || !tr.y) return;
      var ay = tr.yaxis || 'y';
      if (gd._tmFixedY && gd._tmFixedY[ay]) return;
      var win = xWindow(gd, tr.xaxis || 'x');
      if (!win) return;                       // axis at full range → nothing to do
      var x0 = win[0], x1 = win[1];
      for (var i = 0; i < tr.x.length; i++) {
        var t = asMs(tr.x[i]);
        if (t == null || t < x0 || t > x1) continue;
        var v = asNum(tr.y[i]);
        if (v == null) continue;
        if (!bounds[ay]) bounds[ay] = [v, v];
        if (v < bounds[ay][0]) bounds[ay][0] = v;
        if (v > bounds[ay][1]) bounds[ay][1] = v;
      }
    });

    var upd = {}, any = false;
    Object.keys(bounds).forEach(function (ay) {
      var lo = bounds[ay][0], hi = bounds[ay][1];
      var pad = (hi - lo) * 0.08;
      if (!(pad > 0)) pad = Math.abs(hi) * 0.08 || 1;
      var key = (ay === 'y' ? 'yaxis' : 'yaxis' + ay.slice(1)) + '.range';
      upd[key] = [lo - pad, hi + pad];
      any = true;
    });
    return any ? upd : null;
  }

  function attach(gd) {
    if (!gd || gd._tmRescale || typeof gd.on !== 'function') return;
    gd._tmRescale = true;
    gd._tmFixedY = fixedYAxes(gd);
    gd.on('plotly_relayout', function (ev) {
      if (gd._tmLock) return;
      var touchedX = Object.keys(ev).some(function (k) {
        return k.indexOf('xaxis') === 0 &&
               (k.indexOf('range') > -1 || k.indexOf('autorange') > -1);
      });
      if (!touchedX) return;
      var upd = visibleYRanges(gd);
      if (!upd) return;
      gd._tmLock = true;
      window.Plotly.relayout(gd, upd).then(
        function () { gd._tmLock = false; },
        function () { gd._tmLock = false; }
      );
    });
  }

  function init() {
    if (!window.Plotly) return;
    document.querySelectorAll('.js-plotly-plot').forEach(attach);
  }
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
  window.addEventListener('load', init); // plots can finish after DOMContentLoaded
})();

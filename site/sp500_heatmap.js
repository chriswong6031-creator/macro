/* S&P 500 sector treemap heatmap.
 *
 * Renders marketdata/sp500_heatmap.json as a nested squarified treemap
 * (Sector -> Sub-industry -> stock), sized by market cap and shaded by the
 * percent change over a selectable timeframe. Colours are computed in JS from
 * the live CSS theme tokens (--up / --down / --g-mid) so a theme or language
 * toggle recolours instantly (and honours the zh red=up convention).
 *
 * No build-time framework; depends only on theme.js (toggles) + live_config.js
 * (optional live polling). Degrades gracefully to the daily-close snapshot.
 */
(function () {
  'use strict';

  var DATA = null;          // parsed JSON payload
  var TF = '1D';            // active timeframe key
  var LAYOUT = null;        // last computed [{x,y,w,h,tile}] for re-colour
  var TILE_BY_ID = {};      // id -> tile (tooltip lookup)
  var SECTOR_LABEL = {};    // sector key -> {en, zh}

  var SEC_HD = 17, IND_HD = 12, GAP = 1.5;
  // Per-timeframe colour-scale floor (so a quiet day still shows contrast and a
  // 1Y view isn't all blown-out). Actual cap = max(floor, 85th pct of |move|).
  var FLOOR = {
    '5M': 0.5, '10M': 0.5, '15M': 0.6, '30M': 0.8, '1H': 1, '2H': 1.2, '4H': 1.5,
    'AH': 1, '1D': 1.5, '1W': 2.5, 'MTD': 3, '1M': 4, '3M': 7, '6M': 10, 'YTD': 12, '1Y': 15
  };

  function $(id) { return document.getElementById(id); }
  function L(en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>'; }
  function isZh() { return document.documentElement.getAttribute('data-lang') === 'zh'; }
  function fmtPc(v) {
    if (v == null || isNaN(v)) return '—';
    var a = Math.abs(v), d = a >= 100 ? 0 : (a >= 10 ? 1 : 2);
    return (v > 0 ? '+' : '') + v.toFixed(d) + '%';
  }

  /* ----- colour helpers ------------------------------------------------- */
  function hexToRgb(h) {
    h = (h || '').trim();
    if (h[0] === '#') h = h.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name);
  }
  function lerp(a, b, t) {
    return [Math.round(a[0] + (b[0] - a[0]) * t),
            Math.round(a[1] + (b[1] - a[1]) * t),
            Math.round(a[2] + (b[2] - a[2]) * t)];
  }
  function rgb(c) { return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'; }
  function fgFor(c) {
    var lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    return lum > 140 ? '#10141b' : '#f7f9fc';
  }
  function palette() {
    return {
      up: hexToRgb(cssVar('--up') || '#45b873'),
      down: hexToRgb(cssVar('--down') || '#e06464'),
      mid: hexToRgb(cssVar('--g-mid') || '#3a4150'),
      na: hexToRgb(cssVar('--panel2') || '#1e222a')
    };
  }
  function tileColor(pc, cap, pal) {
    if (pc == null || isNaN(pc)) return pal.na;
    var s = Math.min(1, Math.abs(pc) / cap);
    s = 0.12 + 0.88 * s;                       // keep a hint of hue even near 0
    return lerp(pal.mid, pc >= 0 ? pal.up : pal.down, s);
  }

  /* ----- squarified treemap (Bruls/van Wijk) ---------------------------- */
  function squarify(items, x, y, w, h) {
    var out = [];
    var nodes = items.filter(function (d) { return d.value > 0; })
                     .sort(function (a, b) { return b.value - a.value; });
    var total = 0; nodes.forEach(function (d) { total += d.value; });
    if (total <= 0 || w <= 0 || h <= 0) return out;
    var scale = (w * h) / total;
    nodes.forEach(function (d) { d._a = d.value * scale; });

    var rx = x, ry = y, rw = w, rh = h, row = [], i = 0;

    function worst(r, len) {
      if (!r.length) return Infinity;
      var sum = 0, mx = 0, mn = Infinity;
      r.forEach(function (d) { sum += d._a; if (d._a > mx) mx = d._a; if (d._a < mn) mn = d._a; });
      var s2 = sum * sum, l2 = len * len;
      return Math.max(l2 * mx / s2, s2 / (l2 * mn));
    }
    function place(r) {
      var sum = 0; r.forEach(function (d) { sum += d._a; });
      if (rw >= rh) {
        var colW = sum / rh, yy = ry;
        r.forEach(function (d) {
          var hh = d._a / colW;
          out.push({ x: rx, y: yy, w: colW, h: hh, ref: d.ref }); yy += hh;
        });
        rx += colW; rw -= colW;
      } else {
        var rowH = sum / rw, xx = rx;
        r.forEach(function (d) {
          var ww = d._a / rowH;
          out.push({ x: xx, y: ry, w: ww, h: rowH, ref: d.ref }); xx += ww;
        });
        ry += rowH; rh -= rowH;
      }
    }
    while (i < nodes.length) {
      var len = Math.min(rw, rh);
      if (!row.length || worst(row, len) >= worst(row.concat(nodes[i]), len)) {
        row.push(nodes[i]); i++;
      } else { place(row); row = []; }
    }
    if (row.length) place(row);
    return out;
  }

  /* ----- data shaping --------------------------------------------------- */
  function groupHierarchy() {
    // sector -> industry -> [tiles]
    var sectors = {};
    DATA.tiles.forEach(function (t) {
      var s = sectors[t.sector] || (sectors[t.sector] = { name: t.sector, value: 0, inds: {} });
      var ind = s.inds[t.industry] || (s.inds[t.industry] = { name: t.industry, value: 0, tiles: [] });
      ind.tiles.push(t); ind.value += (t.size || 0); s.value += (t.size || 0);
    });
    return sectors;
  }
  function computeCap() {
    var arr = [];
    DATA.tiles.forEach(function (t) {
      var v = t.perf[TF];
      if (v != null && !isNaN(v)) arr.push(Math.abs(v));
    });
    if (!arr.length) return FLOOR[TF] || 2;
    arr.sort(function (a, b) { return a - b; });
    var p85 = arr[Math.floor(arr.length * 0.85)] || arr[arr.length - 1];
    return Math.max(FLOOR[TF] || 1, p85);
  }
  function weightedPc(tiles) {
    var num = 0, den = 0;
    tiles.forEach(function (t) {
      var v = t.perf[TF];
      if (v != null && !isNaN(v)) { num += (t.size || 0) * v; den += (t.size || 0); }
    });
    return den > 0 ? num / den : null;
  }
  function medianPc(tiles) {
    var a = [];
    tiles.forEach(function (t) { var v = t.perf[TF]; if (v != null && !isNaN(v)) a.push(v); });
    if (!a.length) return null;
    a.sort(function (x, y) { return x - y; });
    var m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }
  // Real market caps -> a true cap-weighted sector mean (matches how the sector
  // index moved). With only the offline weight proxy, a handful of small-cap
  // outliers (+1000%) would distort the mean, so fall back to the robust median.
  function sectorAgg(tiles) {
    return DATA.size_basis === 'marketcap' ? weightedPc(tiles) : medianPc(tiles);
  }

  /* ----- render --------------------------------------------------------- */
  function render() {
    var wrap = $('tm-wrap'), tm = $('tm');
    if (!DATA || !DATA.tiles.length) {
      tm.innerHTML = '<div class="hm-empty">' + L('No heatmap data available.', '暂无热力图数据。') + '</div>';
      return;
    }
    // size the canvas to fill the viewport (Finviz-style), with sane bounds
    var top = wrap.getBoundingClientRect().top + window.scrollY;
    var H = Math.max(540, Math.min(window.innerHeight - 120, 1180));
    if (window.innerWidth < 760) H = Math.max(560, window.innerHeight - 90);
    wrap.style.height = H + 'px';
    var W = tm.clientWidth || wrap.clientWidth;
    tm.style.height = H + 'px';

    var pal = palette();
    var cap = computeCap();
    updateLegend(cap);

    var sectors = groupHierarchy();
    var secItems = Object.keys(sectors).map(function (k) {
      return { value: sectors[k].value, ref: sectors[k] };
    });
    var secRects = squarify(secItems, 0, 0, W, H);

    var html = [];
    var id = 0; TILE_BY_ID = {};

    secRects.forEach(function (sr) {
      var s = sr.ref;
      var x = sr.x + GAP, y = sr.y + GAP, w = sr.w - 2 * GAP, h = sr.h - 2 * GAP;
      if (w <= 1 || h <= 1) return;
      var lab = SECTOR_LABEL[s.name] || { en: s.name, zh: s.name };
      var spc = sectorAgg(flattenTiles(s));
      html.push('<div class="sec" style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px">');

      var hd = (h > 30 && w > 64) ? Math.min(SEC_HD, h * 0.5) : 0;
      if (hd) {
        var spcCls = spc == null ? '' : (spc >= 0 ? 'pos' : 'neg');
        html.push('<div class="sec-hd" style="height:' + hd + 'px;line-height:' + hd + 'px;font-size:'
          + Math.max(10, Math.min(13, hd - 4)) + 'px">'
          + '<span>' + L(lab.en, lab.zh) + '</span>'
          + (w > 150 ? '<span class="pc ' + spcCls + '">' + fmtPc(spc) + '</span>' : '') + '</div>');
      }

      var innerY = y + hd, innerH = h - hd;
      var indItems = Object.keys(s.inds).map(function (k) {
        return { value: s.inds[k].value, ref: s.inds[k] };
      });
      // industry rects are RELATIVE to the sector inner box
      var indRects = squarify(indItems, 0, 0, w, innerH);
      indRects.forEach(function (ir) {
        var ind = ir.ref;
        var ix = ir.x, iy = ir.y, iw = ir.w, ih = ir.h;
        var ihd = (ih > 34 && iw > 60) ? IND_HD : 0;
        if (ihd) {
          html.push('<div class="ind-hd" style="left:' + (ix + 2) + 'px;top:' + (innerY - y + iy + 1)
            + 'px;width:' + (iw - 4) + 'px;height:' + ihd + 'px;line-height:' + ihd + 'px">'
            + esc(ind.name) + '</div>');
        }
        var tileRects = squarify(
          ind.tiles.map(function (t) { return { value: (t.size || 0.0001), ref: t }; }),
          ix, iy + ihd, iw, ih - ihd);
        tileRects.forEach(function (tr) {
          var t = tr.ref, pc = t.perf[TF];
          var c = tileColor(pc, cap, pal), fg = fgFor(c);
          var tw = tr.w, th = tr.h;
          if (tw < 2 || th < 2) return;
          var cls = 'tile';
          if (tw < 30 || th < 17) cls += ' tiny';
          if (tw < 19 || th < 11) cls += ' micro';
          var symF = Math.max(7, Math.min(tw / 4.0, th * 0.5, 16));
          var pcF = Math.max(7, Math.min(tw / 5.2, th * 0.36, 12));
          TILE_BY_ID[id] = t;
          // tile top is relative to the (positioned) sector box: innerY - y + tr.y
          html.push('<div class="' + cls + '" data-i="' + id + '" style="left:' + tr.x + 'px;top:'
            + (innerY - y + tr.y) + 'px;width:' + tw + 'px;height:' + th + 'px;background:' + rgb(c)
            + ';color:' + fg + '">'
            + '<span class="sym" style="font-size:' + symF.toFixed(1) + 'px">' + esc(t.t) + '</span>'
            + '<span class="pc" style="font-size:' + pcF.toFixed(1) + 'px">' + fmtPc(pc) + '</span>'
            + '</div>');
          id++;
        });
      });
      html.push('</div>');
    });

    tm.innerHTML = html.join('');
    LAYOUT = true;
  }

  function flattenTiles(s) {
    var out = [];
    Object.keys(s.inds).forEach(function (k) { out = out.concat(s.inds[k].tiles); });
    return out;
  }
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ----- tabs / legend / status ----------------------------------------- */
  function buildTabs() {
    var box = $('tm-tabs'); if (!box) return;
    box.innerHTML = '';
    DATA.timeframes.forEach(function (tf) {
      var b = document.createElement('button');
      b.className = 'tf' + (tf.key === TF ? ' on' : '') + (tf.available ? '' : ' off');
      b.innerHTML = L(tf.en, tf.zh) + (tf.available ? '' : '<span class="soon">•</span>');
      b.setAttribute('data-tf', tf.key);
      if (!tf.available) {
        b.title = isZh() ? '接入实时/分钟级数据后启用' : 'Lights up with a live / intraday feed';
      }
      if (tf.available) {
        b.addEventListener('click', function () { setTf(tf.key); });
      }
      box.appendChild(b);
    });
  }
  function setTf(key) {
    if (key === TF) return;
    TF = key;
    Array.prototype.forEach.call($('tm-tabs').children, function (b) {
      b.classList.toggle('on', b.getAttribute('data-tf') === key);
    });
    render();
  }
  function updateLegend(cap) {
    var lo = $('lg-lo'), hi = $('lg-hi');
    var c = cap >= 10 ? Math.round(cap) : cap.toFixed(1);
    if (lo) lo.textContent = '−' + c + '%';
    if (hi) hi.textContent = '+' + c + '%';
  }
  function updateStatus() {
    var dot = $('hm-dot'), src = $('hm-src'), sb = $('hm-size-basis');
    var live = DATA.source === 'polygon-live';
    if (dot) dot.className = 'hm-dot' + (live ? ' live' : '');
    if (src) {
      var en = (live ? 'Live · 15-min delayed' : 'Daily close')
        + ' · as of ' + (DATA.asof || '—') + ' · ' + DATA.n_tiles + ' names';
      var zh = (live ? '实时 · 延迟15分钟' : '日线收盘')
        + ' · 截至 ' + (DATA.asof || '—') + ' · ' + DATA.n_tiles + ' 只';
      src.innerHTML = L(en, zh);
    }
    if (sb) sb.innerHTML = DATA.size_basis === 'marketcap'
      ? L('Market cap', '市值') : L('Cap weight (proxy)', '市值权重（代理）');
  }

  /* ----- tooltip -------------------------------------------------------- */
  function initTip() {
    var tm = $('tm'), tip = $('tm-tip');
    tm.addEventListener('mousemove', function (e) {
      var el = e.target.closest && e.target.closest('.tile');
      if (!el) { tip.style.display = 'none'; return; }
      var t = TILE_BY_ID[el.getAttribute('data-i')];
      if (!t) { tip.style.display = 'none'; return; }
      tip.innerHTML = tipHtml(t);
      tip.style.display = 'block';
      var pad = 14, tw = tip.offsetWidth, th = tip.offsetHeight;
      var x = e.clientX + pad, y = e.clientY + pad;
      if (x + tw > window.innerWidth - 6) x = e.clientX - tw - pad;
      if (y + th > window.innerHeight - 6) y = e.clientY - th - pad;
      tip.style.left = Math.max(6, x) + 'px';
      tip.style.top = Math.max(6, y) + 'px';
    });
    tm.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
    tm.addEventListener('click', function (e) {
      var el = e.target.closest && e.target.closest('.tile');
      if (!el) return;
      var t = TILE_BY_ID[el.getAttribute('data-i')];
      if (t) window.location.href = 'stock.html#' + t.t;
    });
  }
  function tipHtml(t) {
    var lab = SECTOR_LABEL[t.sector] || { en: t.sector, zh: t.sector };
    var cur = t.perf[TF];
    var curCls = cur == null ? '' : (cur >= 0 ? 'pos' : 'neg');
    var h = '<div class="tt-sym">' + esc(t.t) + '</div>'
      + '<div class="tt-nm">' + esc(t.name) + '</div>'
      + '<div class="tt-row"><span>' + L(lab.en, lab.zh) + '</span><b>' + esc(t.industry) + '</b></div>'
      + '<div class="tt-row"><span>' + tfLabel(TF) + '</span><b class="' + curCls + '">' + fmtPc(cur) + '</b></div>'
      + '<div class="tt-grid">';
    DATA.timeframes.forEach(function (tf) {
      var v = t.perf[tf.key];
      if (v == null) return;
      h += '<span>' + L(tf.en, tf.zh) + '</span><b class="' + (v >= 0 ? 'pos' : 'neg') + '">' + fmtPc(v) + '</b>';
    });
    h += '</div>';
    return h;
  }
  function tfLabel(key) {
    var tf = DATA.timeframes.filter(function (x) { return x.key === key; })[0];
    return tf ? L(tf.en, tf.zh) : key;
  }

  /* ----- optional live polling ------------------------------------------ */
  function maybeStartLive() {
    var url = window.LIVE_QUOTES_URL;
    if (!window.LIVE_ENABLED || !url) return;     // worker not configured -> static snapshot
    var poll = (window.LIVE_POLL_SEC || 60) * 1000;
    var syms = DATA.tiles.map(function (t) { return t.t; });
    var prevById = {};
    DATA.tiles.forEach(function (t) { prevById[t.t] = t; });

    function chunk(a, n) { var o = []; for (var i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o; }
    function tick() {
      var groups = chunk(syms, 180), got = 0, any = false;
      groups.forEach(function (g) {
        fetch(url + (url.indexOf('?') < 0 ? '?' : '&') + 'symbols=' + g.join(','))
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) {
            got++;
            var q = j && j.quotes;
            if (q) Object.keys(q).forEach(function (sym) {
              var t = prevById[sym]; if (!t) return;
              var price = q[sym].price, prev = q[sym].prevClose;
              if (price && prev) { t.perf['1D'] = +(((price / prev) - 1) * 100).toFixed(2); any = true; }
            });
            if (got === groups.length && any) {
              DATA.source = 'polygon-live'; updateStatus();
              if (TF === '1D') render();
            }
          })
          .catch(function () { got++; });
      });
    }
    tick();
    setInterval(tick, poll);
  }

  /* ----- boot ----------------------------------------------------------- */
  function boot() {
    DATA.sectors.forEach(function (s) { SECTOR_LABEL[s.key] = { en: s.en, zh: s.zh }; });
    TF = DATA.default_tf || '1D';
    if (!DATA.timeframes.some(function (tf) { return tf.key === TF && tf.available; })) {
      var first = DATA.timeframes.filter(function (tf) { return tf.available; })[0];
      if (first) TF = first.key;
    }
    buildTabs(); updateStatus(); initTip(); render(); maybeStartLive();

    var rt;
    window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(render, 160); });
    document.addEventListener('themechange', render);
    document.addEventListener('langchange', function () { buildTabs(); updateStatus(); render(); });
  }

  function init() {
    fetch('marketdata/sp500_heatmap.json', { cache: 'no-cache' })
      .then(function (r) { return r.json(); })
      .then(function (j) { DATA = j; boot(); })
      .catch(function (e) {
        var tm = $('tm');
        if (tm) tm.innerHTML = '<div class="hm-empty">' + L('Could not load heatmap data.', '无法加载热力图数据。') + '</div>';
        console.error('heatmap load failed', e);
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

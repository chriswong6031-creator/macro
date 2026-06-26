/* heatmap.js — the S&P 500 market heatmap, one shared renderer for three
 * surfaces:
 *   #heatmap-full       → the full squarified treemap (standalone page + the
 *                          expand overlay). Sector → industry → stock, sized by
 *                          market cap, coloured by discrete per-timeframe bins.
 *   #heatmap-scorecard  → a compact "market at a glance" card on the dashboard,
 *                          with an Expand button that opens the full map in an
 *                          in-page overlay.
 *   (mobile)            → under 560px the full view becomes a vertical,
 *                          sector-grouped list of large rows.
 *
 * Reads marketdata/sp500_heatmap.json (offline-safe daily-close snapshot;
 * splices a live 1D when a feed is connected). The rich hover card lazily
 * fetches stockdata/<T>.json — OUR conviction read (verdict, 0-100 score,
 * drivers/cautions, archetype, technicals) — and degrades gracefully when a
 * name has no nightly record. Colours are computed from the live CSS theme
 * tokens so a theme/language toggle (incl. the zh red=up convention) recolours
 * instantly. No framework; depends only on theme.js (toggles).
 *
 * window.MMHeatmap.openOverlay() opens the full map over the current page.
 */
(function () {
  'use strict';

  var JSON_URL = 'marketdata/sp500_heatmap.json';
  var _dataPromise = null;
  function loadData() {
    if (!_dataPromise) {
      _dataPromise = fetch(JSON_URL, { cache: 'no-cache' })
        .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); });
    }
    return _dataPromise;
  }

  /* ---- per-timeframe colour-scale floors (set the bin widths). 1D keeps the
     canonical ±1/2/3%; every other window scales by FLOOR[tf]/FLOOR['1D'] so a
     1Y / 3M map still has contrast instead of a wall of saturated colour. ---- */
  var FLOOR = {
    '5M': 0.5, '10M': 0.5, '15M': 0.6, '30M': 0.8, '1H': 1, '2H': 1.2, '4H': 1.5,
    'AH': 1, '1D': 1.5, '1W': 2.5, 'MTD': 3, '1M': 4, '3M': 7, '6M': 10, 'YTD': 12, '1Y': 15
  };
  var BASE_EDGES = [1, 2, 3];
  function edgesFor(tf) {
    var f = (FLOOR[tf] || 1.5) / FLOOR['1D'];
    return [BASE_EDGES[0] * f, BASE_EDGES[1] * f, BASE_EDGES[2] * f];
  }
  function edgeFmt(v) { return v >= 10 ? Math.round(v) : (v >= 1 ? +v.toFixed(1) : +v.toFixed(2)); }

  var SEC_HD = 19, IND_HD = 12, GAP = 3;

  /* ----- small helpers ----- */
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function isZh() { return document.documentElement.getAttribute('data-lang') === 'zh'; }
  function L(en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>'; }
  function lz(en, zh) { return isZh() && zh ? zh : (en || ''); }
  function fmtPc(v) {
    if (v == null || isNaN(v)) return '—';
    var a = Math.abs(v), d = a >= 100 ? 0 : (a >= 10 ? 1 : 2);
    return (v > 0 ? '+' : (v < 0 ? '−' : '')) + a.toFixed(d) + '%';
  }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function hexToRgb(h) {
    h = (h || '').trim(); if (h[0] === '#') h = h.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16) || 0;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mix(a, b, t) {   // t = weight of a
    return [Math.round(a[0] * t + b[0] * (1 - t)),
            Math.round(a[1] * t + b[1] * (1 - t)),
            Math.round(a[2] * t + b[2] * (1 - t))];
  }
  function rgb(c) { return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'; }
  function fgFor(c) {
    var lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    return lum > 142 ? '#0e1217' : '#f6f9fc';
  }
  function neutral() {
    // a desaturated slate between the gauge-mid track and the panel — distinct
    // from the page background so a flat ~0% tile still reads as a tile.
    return mix(hexToRgb(cssVar('--g-mid') || '#3a4150'), hexToRgb(cssVar('--panel') || '#181b21'), 0.58);
  }
  function binPalette() {
    var up = hexToRgb(cssVar('--hm-up-v') || '#1ec173');
    var dn = hexToRgb(cssVar('--hm-dn-v') || '#e8485f');
    var nu = neutral();
    var P = {};
    P[3] = up; P[2] = mix(up, nu, 0.76); P[1] = mix(up, nu, 0.36);
    P[0] = nu;
    P[-1] = mix(dn, nu, 0.36); P[-2] = mix(dn, nu, 0.76); P[-3] = dn;
    P.na = mix(hexToRgb(cssVar('--panel2') || '#1e222a'), nu, 0.5);
    return P;
  }
  function binIndex(pc, edges) {
    if (pc == null || isNaN(pc)) return 'na';
    var a = Math.abs(pc), s = pc < 0 ? -1 : 1;
    var lvl = a >= edges[2] ? 3 : a >= edges[1] ? 2 : a >= edges[0] ? 1 : 0;
    return s * lvl || 0;
  }

  /* ----- squarified treemap (Bruls/van Wijk) ----- */
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
        r.forEach(function (d) { var hh = d._a / colW; out.push({ x: rx, y: yy, w: colW, h: hh, ref: d.ref }); yy += hh; });
        rx += colW; rw -= colW;
      } else {
        var rowH = sum / rw, xx = rx;
        r.forEach(function (d) { var ww = d._a / rowH; out.push({ x: xx, y: ry, w: ww, h: rowH, ref: d.ref }); xx += ww; });
        ry += rowH; rh -= rowH;
      }
    }
    while (i < nodes.length) {
      var len = Math.min(rw, rh);
      if (!row.length || worst(row, len) >= worst(row.concat(nodes[i]), len)) { row.push(nodes[i]); i++; }
      else { place(row); row = []; }
    }
    if (row.length) place(row);
    return out;
  }

  /* ----- shared data shaping ----- */
  function groupHierarchy(data) {
    var sectors = {};
    data.tiles.forEach(function (t) {
      var s = sectors[t.sector] || (sectors[t.sector] = { name: t.sector, value: 0, inds: {}, tiles: [] });
      var ind = s.inds[t.industry] || (s.inds[t.industry] = { name: t.industry, value: 0, tiles: [] });
      ind.tiles.push(t); ind.value += (t.size || 0);
      s.tiles.push(t); s.value += (t.size || 0);
    });
    return sectors;
  }
  function medianPc(tiles, tf) {
    var a = []; tiles.forEach(function (t) { var v = t.perf[tf]; if (v != null && !isNaN(v)) a.push(v); });
    if (!a.length) return null;
    a.sort(function (x, y) { return x - y; });
    var m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }
  function weightedPc(tiles, tf) {
    var num = 0, den = 0;
    tiles.forEach(function (t) { var v = t.perf[tf]; if (v != null && !isNaN(v)) { num += (t.size || 0) * v; den += (t.size || 0); } });
    return den > 0 ? num / den : null;
  }
  function sectorAgg(data, tiles, tf) {
    return data.size_basis === 'marketcap' ? weightedPc(tiles, tf) : medianPc(tiles, tf);
  }
  function sectorLabels(data) {
    var m = {}; (data.sectors || []).forEach(function (s) { m[s.key] = { en: s.en, zh: s.zh }; }); return m;
  }
  var SHORT = {
    'Information Technology': ['Tech', '信息技术'], 'Health Care': ['Health', '医疗'],
    'Financials': ['Financials', '金融'], 'Consumer Discretionary': ['Cons Disc', '非必需消费'],
    'Communication Services': ['Comm Svcs', '通信'], 'Industrials': ['Industrials', '工业'],
    'Consumer Staples': ['Staples', '必需消费'], 'Energy': ['Energy', '能源'],
    'Utilities': ['Utilities', '公用事业'], 'Real Estate': ['Real Est', '房地产'], 'Materials': ['Materials', '材料']
  };
  function shortSec(name) { return SHORT[name] ? SHORT[name] : [name, name]; }

  /* ====================================================================== */
  /*  HOVER CARD — our conviction read, lazily fetched, degrades gracefully  */
  /* ====================================================================== */
  var _tickerCache = {};
  function fetchTicker(t) {
    if (window.SD && window.SD.loadTicker) return window.SD.loadTicker(t);
    if (Object.prototype.hasOwnProperty.call(_tickerCache, t)) return Promise.resolve(_tickerCache[t]);
    var safe = String(t).replace(/[=^]/g, '_');
    return fetch('stockdata/' + safe + '.json')
      .then(function (r) { if (!r.ok) throw new Error('absent'); return r.json(); })
      .then(function (j) { _tickerCache[t] = j; return j; })
      .catch(function () { _tickerCache[t] = null; return null; });
  }

  var _card = null, _cardFor = null, _cardTimer = null;
  function card() {
    if (_card) return _card;
    _card = document.createElement('div');
    _card.className = 'hm-card';
    _card.setAttribute('role', 'tooltip');
    document.body.appendChild(_card);
    return _card;
  }
  function bandClass(b) {
    return b === 'high' ? 'b-high' : b === 'constructive' ? 'b-con' : b === 'low' ? 'b-low' : 'b-neu';
  }
  function cardBaseHtml(data, t) {
    var labs = sectorLabels(data);
    var lab = labs[t.sector] || { en: t.sector, zh: t.sector };
    var cur = t.perf[data._tf];
    var cls = cur == null ? '' : (cur >= 0 ? 'up' : 'dn');
    var strip = '';
    (data.timeframes || []).forEach(function (tf) {
      var v = t.perf[tf.key];
      if (v == null || isNaN(v)) return;
      strip += '<div class="hm-c-m"><span class="k">' + L(tf.en, tf.zh) + '</span>'
        + '<span class="v ' + (v >= 0 ? 'up' : 'dn') + '">' + fmtPc(v) + '</span></div>';
    });
    return ''
      + '<div class="hm-c-hd">'
      +   '<div class="hm-c-id"><div class="hm-c-sym">' + esc(t.t) + '</div>'
      +     '<div class="hm-c-nm">' + esc(t.name) + ' · ' + L(lab.en, lab.zh) + '</div></div>'
      +   '<div class="hm-c-px"><div class="hm-c-pxv" data-px>—</div>'
      +     '<div class="hm-c-chg ' + cls + '">' + fmtPc(cur) + '</div></div>'
      + '</div>'
      + '<div class="hm-c-body" data-body><div class="hm-c-load"><span></span><span></span><span></span></div></div>'
      + '<div class="hm-c-strip">' + strip + '</div>'
      + '<div class="hm-c-foot">' + L('View full analysis', '查看完整分析') + ' →</div>';
  }
  function enrichCard(el, data, t, rec) {
    var pxEl = el.querySelector('[data-px]');
    var body = el.querySelector('[data-body]');
    if (!body) return;
    if (!rec) {
      body.innerHTML = '<div class="hm-c-stub">'
        + L('No nightly read for this name yet — open the analyzer for the full breakdown.',
            '该标的暂无每晚分析 — 点击打开分析器查看完整拆解。') + '</div>';
      return;
    }
    var tech = rec.tech || {}, conv = rec.conviction || {}, prof = rec.profile || {}, val = rec.valuation || {};
    if (pxEl && tech.price != null) {
      pxEl.textContent = '$' + (tech.price >= 100 ? Math.round(tech.price).toLocaleString()
        : (+tech.price).toFixed(2));
    }
    var h = '';
    if (conv.verdict || conv.score != null) {
      var verdict = lz(conv.verdict, conv.verdict_zh);
      var band = lz(conv.band_en || conv.band, conv.band_zh || conv.band);
      h += '<div class="hm-c-conv">';
      if (conv.band || conv.score != null) {
        h += '<span class="hm-c-band ' + bandClass(conv.band) + '">' + esc(band || '—') + '</span>';
        if (conv.score != null) h += '<span class="hm-c-score">' + Math.round(conv.score)
          + '<small>/100</small></span>';
      }
      h += '</div>';
      if (verdict) h += '<div class="hm-c-verdict">' + esc(verdict) + '</div>';
    }
    var chips = '';
    (conv.drivers || []).slice(0, 3).forEach(function (d) {
      chips += '<span class="hm-c-chip ok">✓ ' + esc(String(d)) + '</span>';
    });
    var cautions = isZh() && conv.cautions_zh ? conv.cautions_zh : conv.cautions;
    (cautions || []).slice(0, 2).forEach(function (c) {
      chips += '<span class="hm-c-chip warn">⚠ ' + esc(String(c)) + '</span>';
    });
    if (chips) h += '<div class="hm-c-chips">' + chips + '</div>';

    var meta = '';
    var arch = prof.archetype || {};
    if (arch.label) meta += '<span class="hm-c-tag">' + esc(lz(arch.label, arch.label_zh)) + '</span>';
    var cheap = (val.trailing_pe && val.trailing_pe.cheap != null) ? val.trailing_pe.cheap
      : (val.cheap != null ? val.cheap : null);
    if (cheap != null) {
      var cl = cheap >= 60 ? 'ok' : (cheap <= 35 ? 'warn' : '');
      meta += '<span class="hm-c-tag ' + cl + '">' + (cheap >= 50
        ? L('cheap vs sector', '相对板块便宜') : L('rich vs sector', '相对板块偏贵')) + '</span>';
    }
    if (tech.pct_vs_200dma != null) {
      var p2 = +tech.pct_vs_200dma;
      meta += '<span class="hm-c-tag">' + L('vs 200d', '相对200日') + ' '
        + '<b class="' + (p2 >= 0 ? 'up' : 'dn') + '">' + (p2 > 0 ? '+' : '') + p2.toFixed(0) + '%</b></span>';
    }
    if (tech.rsi14 != null) meta += '<span class="hm-c-tag">RSI <b>' + Math.round(tech.rsi14) + '</b></span>';
    if (meta) h += '<div class="hm-c-meta">' + meta + '</div>';

    var desc = lz(prof.description, prof.description_zh);
    if (desc) h += '<div class="hm-c-desc">' + esc(desc) + '</div>';

    body.innerHTML = h || '<div class="hm-c-stub">' + L('Open the analyzer for the full read.', '打开分析器查看完整解读。') + '</div>';
  }
  function positionCard(el, cx, cy) {
    var pad = 16, w = el.offsetWidth, h = el.offsetHeight;
    var x = cx + pad, y = cy + pad;
    if (x + w > window.innerWidth - 8) x = cx - w - pad;
    if (y + h > window.innerHeight - 8) y = cy - h - pad;
    el.style.left = Math.max(8, x) + 'px';
    el.style.top = Math.max(8, y) + 'px';
  }
  function showCard(data, t, cx, cy) {
    var el = card();
    if (_cardFor !== t.t) {
      _cardFor = t.t;
      el.innerHTML = cardBaseHtml(data, t);
      el.classList.add('on');
      positionCard(el, cx, cy);
      clearTimeout(_cardTimer);
      var want = t.t;
      _cardTimer = setTimeout(function () {
        fetchTicker(t.t).then(function (rec) {
          if (_cardFor !== want) return;
          enrichCard(el, data, t, rec);
          positionCard(el, cx, cy);
        });
      }, 120);
    } else {
      positionCard(el, cx, cy);
    }
  }
  function hideCard() {
    _cardFor = null; clearTimeout(_cardTimer);
    if (_card) _card.classList.remove('on');
  }

  /* ====================================================================== */
  /*  FULL VIEW — controls + treemap (desktop) / sector list (mobile)        */
  /* ====================================================================== */
  function createFullView(root, data) {
    root.classList.add('hm-scope', 'hm-view');
    root.innerHTML = ''
      + '<div class="hm-bar">'
      +   '<div class="hm-tfs" role="tablist" aria-label="Timeframe"></div>'
      +   '<div class="hm-legend"></div>'
      +   '<div class="hm-grow"></div>'
      +   '<div class="hm-read"></div>'
      + '</div>'
      + '<div class="hm-sort" role="group" aria-label="Sort"></div>'
      + '<div class="hm-tm-wrap"><div class="hm-tm"></div></div>';

    var tfsEl = root.querySelector('.hm-tfs');
    var legendEl = root.querySelector('.hm-legend');
    var readEl = root.querySelector('.hm-read');
    var sortEl = root.querySelector('.hm-sort');
    var wrap = root.querySelector('.hm-tm-wrap');
    var tm = root.querySelector('.hm-tm');
    var glare = document.createElement('div'); glare.className = 'hm-glare'; wrap.appendChild(glare);
    var firstLayout = true, glareRAF = 0;
    var REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var TF = data.default_tf || '1D';
    if (!(data.timeframes || []).some(function (tf) { return tf.key === TF && tf.available; })) {
      var first = (data.timeframes || []).filter(function (tf) { return tf.available; })[0];
      if (first) TF = first.key;
    }
    var SORT = 'cap';
    var tileEls = [];      // {el, pcEl, t}
    var secPc = [];        // {el, tiles}
    var mode = null;       // 'tree' | 'list'
    var labs = sectorLabels(data);

    function isMobile() { return window.matchMedia('(max-width: 560px)').matches; }

    function buildTabs() {
      tfsEl.innerHTML = '';
      (data.timeframes || []).forEach(function (tf) {
        var b = document.createElement('button');
        b.className = 'hm-tf' + (tf.key === TF ? ' on' : '') + (tf.available ? '' : ' off');
        b.type = 'button';
        b.innerHTML = L(tf.en, tf.zh);
        b.setAttribute('data-tf', tf.key);
        if (!tf.available) b.title = isZh() ? '接入实时/分钟级数据后启用' : 'Lights up with a live feed';
        else b.addEventListener('click', function () { setTf(tf.key); });
        tfsEl.appendChild(b);
      });
    }
    function buildSort() {
      var opts = [['cap', 'Market cap', '市值'], ['move', 'Biggest move', '涨跌幅'], ['az', 'A–Z', '字母']];
      sortEl.innerHTML = '<span class="hm-sort-lab">' + L('Sort', '排序') + '</span>';
      opts.forEach(function (o) {
        var b = document.createElement('button'); b.type = 'button';
        b.className = 'hm-sortb' + (o[0] === SORT ? ' on' : '');
        b.innerHTML = L(o[1], o[2]); b.setAttribute('data-s', o[0]);
        b.addEventListener('click', function () {
          if (SORT === o[0]) return; SORT = o[0];
          Array.prototype.forEach.call(sortEl.querySelectorAll('.hm-sortb'),
            function (x) { x.classList.toggle('on', x.getAttribute('data-s') === SORT); });
          layoutList();
        });
        sortEl.appendChild(b);
      });
    }
    function setTf(key) {
      if (key === TF) return; TF = key;
      Array.prototype.forEach.call(tfsEl.children, function (b) {
        b.classList.toggle('on', b.getAttribute('data-tf') === key);
      });
      data._tf = TF;
      if (mode === 'tree') recolor(); else layoutList();
      updateLegend();
    }
    function updateLegend() {
      var e = edgesFor(TF), pal = binPalette();
      var sw = '';
      [-3, -2, -1, 0, 1, 2, 3].forEach(function (b) {
        sw += '<span class="hm-lg-sw" style="background:' + rgb(pal[b]) + '"></span>';
      });
      legendEl.innerHTML = '<span class="hm-lg-end">−' + edgeFmt(e[2]) + '%</span>'
        + '<span class="hm-lg-sws">' + sw + '</span>'
        + '<span class="hm-lg-end">+' + edgeFmt(e[2]) + '%</span>'
        + '<span class="hm-lg-step">' + L('bins', '分档') + ' ±' + edgeFmt(e[0]) + '/' + edgeFmt(e[1]) + '/' + edgeFmt(e[2]) + '</span>';
    }
    function updateRead() {
      var adv = 0, dec = 0;
      data.tiles.forEach(function (t) { var v = t.perf['1D']; if (v > 0) adv++; else if (v < 0) dec++; });
      var live = data.source === 'polygon-live';
      var srcEn = (live ? 'Live · 15-min delayed' : 'Daily close') + ' · ' + (data.asof || '—');
      var srcZh = (live ? '实时 · 延迟15分钟' : '日线收盘') + ' · ' + (data.asof || '—');
      readEl.innerHTML = '<span class="hm-dot ' + (live ? 'live' : '') + '"></span>'
        + '<span class="hm-read-src">' + L(srcEn, srcZh) + '</span>'
        + '<span class="hm-read-br"><b class="up">' + adv + ' ▲</b> <b class="dn">' + dec + ' ▼</b></span>';
    }

    /* ----- treemap (desktop) ----- */
    function layoutTree() {
      mode = 'tree'; root.classList.remove('hm-mobile');
      var animate = firstLayout && !REDUCE; firstLayout = false;
      tileEls = []; secPc = [];
      var H = Math.max(540, Math.min(window.innerHeight - 150, 1220));
      wrap.style.height = H + 'px'; tm.style.height = H + 'px';
      var W = tm.clientWidth || wrap.clientWidth;
      if (W <= 0) { requestAnimationFrame(layoutTree); return; }

      var sectors = groupHierarchy(data);
      var secItems = Object.keys(sectors).map(function (k) { return { value: sectors[k].value, ref: sectors[k] }; });
      var secRects = squarify(secItems, 0, 0, W, H);
      var html = [], idx = 0;

      secRects.forEach(function (sr) {
        var s = sr.ref;
        var x = sr.x + GAP, y = sr.y + GAP, w = sr.w - 2 * GAP, h = sr.h - 2 * GAP;
        if (w <= 1 || h <= 1) return;
        var lab = labs[s.name] || { en: s.name, zh: s.name };
        html.push('<div class="hm-sec" style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px">');
        var hd = (h > 34 && w > 70) ? Math.min(SEC_HD, h * 0.5) : 0;
        if (hd) {
          html.push('<div class="hm-sec-hd" style="height:' + hd + 'px;line-height:' + hd + 'px">'
            + '<span class="nm">' + L(lab.en, lab.zh) + '</span>'
            + (w > 150 ? '<span class="pc" data-sec="' + idx + '"></span>' : '') + '</div>');
          secPc.push({ key: idx, tiles: s.tiles, show: w > 150 }); idx++;
        }
        var innerY = y + hd, innerH = h - hd;
        var indItems = Object.keys(s.inds).map(function (k) { return { value: s.inds[k].value, ref: s.inds[k] }; });
        var indRects = squarify(indItems, 0, 0, w, innerH);
        indRects.forEach(function (ir) {
          var ind = ir.ref, ix = ir.x, iy = ir.y, iw = ir.w, ih = ir.h;
          var ihd = (ih > 36 && iw > 64) ? IND_HD : 0;
          if (ihd) {
            html.push('<div class="hm-ind-hd" style="left:' + (ix + 2) + 'px;top:' + (innerY - y + iy + 1)
              + 'px;width:' + (iw - 4) + 'px;height:' + ihd + 'px;line-height:' + ihd + 'px">' + esc(ind.name) + '</div>');
          }
          var tRects = squarify(ind.tiles.map(function (t) { return { value: (t.size || 0.0001), ref: t }; }),
            ix, iy + ihd, iw, ih - ihd);
          tRects.forEach(function (tr) {
            var t = tr.ref, tw = tr.w, th = tr.h;
            if (tw < 2 || th < 2) return;
            var cls = 'hm-tile';
            if (tw < 32 || th < 18) cls += ' tiny';
            if (tw < 20 || th < 12) cls += ' micro';
            if (tw >= 108 && th >= 64) cls += ' big';
            if (tw >= 140 && th >= 108) cls += ' huge';
            if (animate) cls += ' hm-in';
            var symF = Math.max(7, Math.min(tw / 4.0, th * 0.5, 17));
            var pcF = Math.max(7, Math.min(tw / 5.2, th * 0.4, 12.5));
            var dly = animate ? ';animation-delay:' + Math.min(tileEls.length * 0.9, 520).toFixed(0) + 'ms' : '';
            html.push('<div class="' + cls + '" data-i="' + tileEls.length + '" style="left:' + tr.x + 'px;top:'
              + (innerY - y + tr.y) + 'px;width:' + tw + 'px;height:' + th + 'px' + dly + '">'
              + '<span class="sym" style="font-size:' + symF.toFixed(1) + 'px">' + esc(t.t) + '</span>'
              + '<span class="pc" style="font-size:' + pcF.toFixed(1) + 'px"></span></div>');
            tileEls.push({ t: t });
          });
        });
        html.push('</div>');
      });
      tm.innerHTML = html.join('');
      // bind element refs
      Array.prototype.forEach.call(tm.querySelectorAll('.hm-tile'), function (el) {
        var rec = tileEls[+el.getAttribute('data-i')];
        rec.el = el; rec.pcEl = el.querySelector('.pc');
      });
      secPc.forEach(function (sp) { sp.el = sp.show ? tm.querySelector('.pc[data-sec="' + sp.key + '"]') : null; });
      recolor();
    }
    function recolor() {
      var edges = edgesFor(TF), pal = binPalette();
      tileEls.forEach(function (rec) {
        var pc = rec.t.perf[TF], c = pal[binIndex(pc, edges)];
        rec.el.style.backgroundColor = rgb(c);
        rec.el.style.color = fgFor(c);
        rec.el.style.setProperty('--tg', 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',.7)');
        if (rec.pcEl) rec.pcEl.textContent = fmtPc(pc);
      });
      secPc.forEach(function (sp) {
        if (!sp.el) return;
        var v = sectorAgg(data, sp.tiles, TF);
        sp.el.textContent = fmtPc(v);
        sp.el.className = 'pc ' + (v == null ? '' : (v >= 0 ? 'up' : 'dn'));
      });
    }

    /* ----- mobile list ----- */
    function layoutList() {
      mode = 'list'; root.classList.add('hm-mobile');
      wrap.style.height = 'auto'; tm.style.height = 'auto';
      var edges = edgesFor(TF), pal = binPalette();
      var sectors = groupHierarchy(data);
      var secKeys = Object.keys(sectors).sort(function (a, b) { return sectors[b].value - sectors[a].value; });
      var html = [];
      secKeys.forEach(function (k) {
        var s = sectors[k], lab = labs[k] || { en: k, zh: k };
        var agg = sectorAgg(data, s.tiles, TF);
        var adv = 0, dec = 0;
        s.tiles.forEach(function (t) { var v = t.perf[TF]; if (v > 0) adv++; else if (v < 0) dec++; });
        var tot = Math.max(1, adv + dec);
        html.push('<div class="hm-mgrp">'
          + '<div class="hm-mhd"><span class="nm">' + L(lab.en, lab.zh) + '</span>'
          + '<span class="pc ' + (agg == null ? '' : agg >= 0 ? 'up' : 'dn') + '">' + fmtPc(agg) + '</span>'
          + '<span class="hm-mbr"><i class="up" style="width:' + (100 * adv / tot) + '%"></i>'
          + '<i class="dn" style="width:' + (100 * dec / tot) + '%"></i></span></div>');
        var rows = s.tiles.slice().sort(function (a, b) {
          if (SORT === 'az') return a.t < b.t ? -1 : a.t > b.t ? 1 : 0;
          if (SORT === 'move') {
            var av = a.perf[TF], bv = b.perf[TF];
            return (bv == null ? -1e9 : bv) - (av == null ? -1e9 : av);
          }
          return (b.size || 0) - (a.size || 0);
        });
        rows.forEach(function (t) {
          var pc = t.perf[TF], c = pal[binIndex(pc, edges)];
          html.push('<a class="hm-mrow" href="stock.html#' + encodeURIComponent(t.t) + '">'
            + '<span class="hm-mpc" style="background-color:' + rgb(c) + ';color:' + fgFor(c) + '">' + fmtPc(pc) + '</span>'
            + '<span class="hm-mid"><b>' + esc(t.t) + '</b><span>' + esc(t.name) + '</span></span>'
            + '<span class="hm-mgo">›</span></a>');
        });
        html.push('</div>');
      });
      tm.innerHTML = html.join('');
    }

    /* ----- hover / click on the treemap ----- */
    function onMapLight(e) {
      if (REDUCE) return;
      var r = wrap.getBoundingClientRect();
      var px = e.clientX - r.left, py = e.clientY - r.top;
      var nx = px / r.width - 0.5, ny = py / r.height - 0.5;
      if (glareRAF) return;
      glareRAF = requestAnimationFrame(function () {
        glareRAF = 0;
        glare.style.background = 'radial-gradient(280px circle at ' + px.toFixed(0) + 'px ' + py.toFixed(0)
          + 'px,rgba(255,255,255,.15),rgba(255,255,255,0) 60%)';
        glare.style.opacity = '1';
        tm.style.transform = 'perspective(1600px) rotateX(' + (-ny * 3.4).toFixed(2) + 'deg) rotateY('
          + (nx * 4.2).toFixed(2) + 'deg)';
      });
    }
    function resetMapLight() { glare.style.opacity = '0'; if (!REDUCE) tm.style.transform = ''; }
    function onMove(e) {
      if (mode !== 'tree') return;
      onMapLight(e);
      var el = e.target.closest && e.target.closest('.hm-tile');
      if (!el) { hideCard(); return; }
      var rec = tileEls[+el.getAttribute('data-i')];
      if (!rec) { hideCard(); return; }
      showCard(data, rec.t, e.clientX, e.clientY);
    }
    function onClick(e) {
      var el = e.target.closest && e.target.closest('.hm-tile');
      if (!el) return;
      var rec = tileEls[+el.getAttribute('data-i')];
      if (rec) window.location.href = 'stock.html#' + encodeURIComponent(rec.t.t);
    }
    tm.addEventListener('mousemove', onMove);
    tm.addEventListener('mouseleave', function () { hideCard(); resetMapLight(); });
    tm.addEventListener('click', onClick);

    function layout() { if (!REDUCE) tm.style.transform = ''; if (isMobile()) layoutList(); else layoutTree(); }

    var rt;
    function onResize() { clearTimeout(rt); rt = setTimeout(function () { hideCard(); layout(); }, 150); }
    function onTheme() { hideCard(); if (mode === 'tree') recolor(); else layoutList(); updateLegend(); updateRead(); }
    function onLang() { buildTabs(); buildSort(); updateLegend(); updateRead(); hideCard(); layout(); }
    window.addEventListener('resize', onResize);
    document.addEventListener('themechange', onTheme);
    document.addEventListener('langchange', onLang);

    data._tf = TF;
    buildTabs(); buildSort(); updateLegend(); updateRead(); layout();

    return {
      destroy: function () {
        window.removeEventListener('resize', onResize);
        document.removeEventListener('themechange', onTheme);
        document.removeEventListener('langchange', onLang);
        hideCard();
      }
    };
  }

  /* ====================================================================== */
  /*  COMPACT SCORECARD (dashboard)                                          */
  /* ====================================================================== */
  function renderScorecard(root, data) {
    root.classList.add('hm-scope', 'hm-sc');
    var labs = sectorLabels(data);
    var sectors = groupHierarchy(data);
    var live = data.source === 'polygon-live';

    var head = ''
      + '<div class="hm-sc-hd">'
      +   '<div class="hm-sc-tit">' + L('Market heatmap', '市场热力图') + '</div>'
      +   '<div class="hm-sc-meta"><span class="hm-dot ' + (live ? 'live' : '') + '"></span>'
      +     L((live ? 'Live' : 'Daily close') + ' · ' + (data.asof || '—') + ' · ' + data.n_tiles + ' names',
              (live ? '实时' : '日线收盘') + ' · ' + (data.asof || '—') + ' · ' + data.n_tiles + ' 只') + '</div>'
      +   '<button type="button" class="hm-sc-exp">⤢ ' + L('Expand', '展开') + '</button>'
      + '</div>';

    var stripWrap = '<div class="hm-sc-strip"></div>';
    var foot = '<div class="hm-sc-foot"><div class="hm-sc-breadth"><span class="lab">'
      + L('Breadth', '涨跌广度') + '</span><span class="hm-sc-bar"></span><span class="cnt"></span></div>'
      + '<div class="hm-sc-lead"></div></div>';
    root.innerHTML = head + stripWrap + foot;

    root.querySelector('.hm-sc-exp').addEventListener('click', openOverlay);

    function paintStrip() {
      var strip = root.querySelector('.hm-sc-strip');
      var W = strip.clientWidth, H = 96;
      if (W <= 0) { requestAnimationFrame(paintStrip); return; }
      strip.style.height = H + 'px';
      var pal = binPalette(), edges = edgesFor('1D');
      var items = Object.keys(sectors).map(function (k) { return { value: sectors[k].value, ref: sectors[k] }; });
      var rects = squarify(items, 0, 0, W, H);
      var html = [];
      rects.forEach(function (r) {
        var s = r.ref, agg = sectorAgg(data, s.tiles, '1D');
        var c = pal[binIndex(agg, edges)], fg = fgFor(c);
        var sl = shortSec(s.name), w = r.w - 3, h = r.h - 3;
        if (w < 2 || h < 2) return;
        var top = s.tiles.slice().sort(function (a, b) { return (b.size || 0) - (a.size || 0); })
          .slice(0, 3).map(function (t) { return t.t; }).join(' · ');
        html.push('<div class="hm-sc-tile" style="left:' + (r.x + 1.5) + 'px;top:' + (r.y + 1.5)
          + 'px;width:' + w + 'px;height:' + h + 'px;background-color:' + rgb(c) + ';color:' + fg + '">'
          + '<div class="t1">' + L(sl[0], sl[1]) + '</div>'
          + '<div class="t2">' + fmtPc(agg) + '</div>'
          + (w > 96 && h > 44 ? '<div class="t3">' + esc(top) + '</div>' : '') + '</div>');
      });
      strip.innerHTML = html.join('');
      Array.prototype.forEach.call(strip.querySelectorAll('.hm-sc-tile'),
        function (el) { el.addEventListener('click', openOverlay); });
    }
    function paintFoot() {
      var adv = 0, dec = 0;
      data.tiles.forEach(function (t) { var v = t.perf['1D']; if (v > 0) adv++; else if (v < 0) dec++; });
      var tot = Math.max(1, adv + dec);
      root.querySelector('.hm-sc-bar').innerHTML = '<i class="up" style="width:' + (100 * adv / tot)
        + '%"></i><i class="dn" style="width:' + (100 * dec / tot) + '%"></i>';
      root.querySelector('.hm-sc-breadth .cnt').innerHTML = '<b class="up">' + adv + '</b> / <b class="dn">' + dec + '</b>';
      var sorted = data.tiles.filter(function (t) { return t.perf['1D'] != null; })
        .sort(function (a, b) { return b.perf['1D'] - a.perf['1D']; });
      var lead = sorted.slice(0, 2), lag = sorted.slice(-2).reverse();
      function chip(t, up) {
        return '<a class="hm-sc-chip ' + (up ? 'up' : 'dn') + '" href="stock.html#' + encodeURIComponent(t.t) + '">'
          + esc(t.t) + ' ' + fmtPc(t.perf['1D']) + '</a>';
      }
      root.querySelector('.hm-sc-lead').innerHTML =
        '<span class="lab">' + L('Leaders', '领涨') + '</span>' + lead.map(function (t) { return chip(t, true); }).join('')
        + '<span class="lab lag">' + L('Laggards', '领跌') + '</span>' + lag.map(function (t) { return chip(t, false); }).join('');
    }
    function paint() { paintStrip(); paintFoot(); }
    paint();
    var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(paintStrip, 160); });
    document.addEventListener('themechange', paint);
    document.addEventListener('langchange', paint);
  }

  /* ====================================================================== */
  /*  OVERLAY                                                                */
  /* ====================================================================== */
  var _ov = null, _ovView = null;
  function openOverlay() {
    if (_ov) return;
    loadData().then(function (data) {
      _ov = document.createElement('div');
      _ov.className = 'hm-ov hm-scope';
      _ov.innerHTML = '<div class="hm-ov-scrim"></div>'
        + '<div class="hm-ov-panel" role="dialog" aria-modal="true" aria-label="Market heatmap">'
        +   '<div class="hm-ov-head"><span class="t">🔥 ' + L('S&amp;P 500 Heatmap', 'S&amp;P 500 热力图') + '</span>'
        +     '<button type="button" class="hm-ov-x" aria-label="Close">✕</button></div>'
        +   '<div class="hm-ov-body"><div class="hm-ov-full"></div></div>'
        + '</div>';
      document.body.appendChild(_ov);
      document.body.style.overflow = 'hidden';
      _ovView = createFullView(_ov.querySelector('.hm-ov-full'), data);
      requestAnimationFrame(function () { requestAnimationFrame(function () { if (_ov) _ov.classList.add('open'); }); });
      _ov.querySelector('.hm-ov-x').addEventListener('click', closeOverlay);
      _ov.querySelector('.hm-ov-scrim').addEventListener('click', closeOverlay);
      document.addEventListener('keydown', onKey);
    });
  }
  function onKey(e) { if (e.key === 'Escape') closeOverlay(); }
  function closeOverlay() {
    if (!_ov) return;
    var node = _ov, view = _ovView; _ov = null; _ovView = null;
    document.removeEventListener('keydown', onKey);
    node.classList.remove('open');
    var done = function () { if (view) view.destroy(); node.remove(); document.body.style.overflow = ''; };
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) done(); else setTimeout(done, 280);
  }

  /* ====================================================================== */
  /*  STYLES                                                                 */
  /* ====================================================================== */
  function injectStyle() {
    if (document.getElementById('mm-heatmap-style')) return;
    var css = ''
      + ':root{--hm-up-v:#16c784;--hm-dn-v:#ea3943;--hm-glass:color-mix(in srgb,var(--panel) 56%,transparent);--hm-edge:color-mix(in srgb,#ffffff 10%,var(--line));}'
      + 'html[data-theme="light"]{--hm-up-v:#0fae6e;--hm-dn-v:#e02d3c;--hm-glass:color-mix(in srgb,#ffffff 66%,transparent);--hm-edge:color-mix(in srgb,#0b1830 9%,var(--line));}'
      + 'html[data-lang="zh"]{--hm-up-v:#ea3943;--hm-dn-v:#16c784;}'
      + 'html[data-theme="light"][data-lang="zh"]{--hm-up-v:#e02d3c;--hm-dn-v:#0fae6e;}'
      + '.hm-scope{font-family:Inter,-apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;}'
      + '.hm-scope .up{color:var(--up);} .hm-scope .dn{color:var(--down);}'
      // control bar
      + '.hm-bar{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;margin-bottom:14px;padding:9px 13px;border-radius:15px;background:var(--hm-glass);backdrop-filter:blur(16px) saturate(1.3);-webkit-backdrop-filter:blur(16px) saturate(1.3);border:1px solid var(--hm-edge);box-shadow:0 8px 26px rgba(0,0,0,.16),inset 0 1px 0 rgba(255,255,255,.08);}'
      + '.hm-tfs{display:flex;flex-wrap:wrap;gap:2px;background:color-mix(in srgb,var(--panel2) 55%,transparent);border:1px solid var(--hm-edge);border-radius:12px;padding:3px;box-shadow:inset 0 1px 4px rgba(0,0,0,.22);}'
      + '.hm-tf{font:600 12px/1 Inter,sans-serif;color:var(--muted);background:transparent;border:0;padding:6px 11px;border-radius:9px;cursor:pointer;transition:background .18s,color .18s,box-shadow .18s,transform .1s;white-space:nowrap;}'
      + '.hm-tf:hover:not(.off){color:var(--text);background:color-mix(in srgb,#ffffff 7%,transparent);} .hm-tf:active:not(.off){transform:scale(.95);} .hm-tf.on{background:linear-gradient(180deg,color-mix(in srgb,var(--link) 76%,#ffffff),var(--link));color:#fff;box-shadow:0 3px 11px color-mix(in srgb,var(--link) 45%,transparent),inset 0 1px 0 rgba(255,255,255,.4);}'
      + '.hm-tf.off{opacity:.3;cursor:default;}'
      + '.hm-legend{display:flex;align-items:center;gap:7px;font-size:10.5px;color:var(--muted);}'
      + '.hm-lg-sws{display:inline-flex;border-radius:5px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.3),inset 0 0 0 1px rgba(255,255,255,.1);}'
      + '.hm-lg-sw{width:20px;height:13px;background-image:linear-gradient(180deg,rgba(255,255,255,.2),rgba(0,0,0,.16));} '
      + '.hm-lg-end{font-variant-numeric:tabular-nums;font-weight:700;color:var(--text);}'
      + '.hm-lg-step{color:var(--muted);}'
      + '.hm-grow{flex:1 1 8px;}'
      + '.hm-read{display:flex;align-items:center;gap:8px;font-size:11.5px;color:var(--muted);flex-wrap:wrap;}'
      + '.hm-read-br{font-variant-numeric:tabular-nums;font-weight:700;}'
      + '.hm-dot{width:7px;height:7px;border-radius:50%;background:var(--muted);display:inline-block;}'
      + '.hm-dot.live{background:var(--up);box-shadow:0 0 0 3px color-mix(in srgb,var(--up) 26%,transparent),0 0 12px color-mix(in srgb,var(--up) 70%,transparent);}'
      + '.hm-sort{display:none;align-items:center;gap:6px;margin:-4px 0 12px;font-size:11px;}'
      + '.hm-sort-lab{color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:700;font-size:10px;}'
      + '.hm-sortb{font:600 12px Inter,sans-serif;color:var(--muted);background:var(--panel2);border:1px solid var(--line);padding:5px 11px;border-radius:8px;cursor:pointer;}'
      + '.hm-sortb.on{background:var(--link);border-color:var(--link);color:#fff;}'
      // treemap
      + '.hm-tm-wrap{position:relative;width:100%;border-radius:18px;overflow:hidden;background:radial-gradient(135% 105% at 50% -12%,color-mix(in srgb,var(--panel2) 82%,transparent),var(--panel) 72%);border:1px solid var(--hm-edge);box-shadow:0 22px 60px rgba(0,0,0,.34),inset 0 1px 0 rgba(255,255,255,.05),inset 0 0 70px rgba(0,0,0,.2);}'
      + '.hm-tm{position:relative;width:100%;transform-style:preserve-3d;transition:transform .35s cubic-bezier(.2,.7,.3,1);will-change:transform;}'
      + '.hm-glare{position:absolute;inset:0;pointer-events:none;z-index:4;mix-blend-mode:soft-light;opacity:0;transition:opacity .3s;}'
      + '@media (prefers-reduced-motion:no-preference){.hm-tile.hm-in{animation:hmtilein .5s cubic-bezier(.2,.7,.3,1) both;}@keyframes hmtilein{from{opacity:0;transform:translateY(10px) scale(.94);}to{opacity:1;transform:none;}}}'
      + '.hm-sec{position:absolute;overflow:hidden;}'
      + '.hm-sec-hd{position:absolute;left:0;top:0;width:100%;display:flex;align-items:center;gap:7px;padding:0 8px;font-weight:800;letter-spacing:.01em;color:var(--text);white-space:nowrap;pointer-events:none;z-index:3;font-size:12px;text-shadow:0 1px 3px rgba(0,0,0,.4);}'
      + '.hm-sec-hd .pc{font-weight:700;font-variant-numeric:tabular-nums;opacity:.95;}'
      + '.hm-ind-hd{position:absolute;padding:0 4px;font-size:9.5px;font-weight:700;color:color-mix(in srgb,var(--text) 72%,transparent);white-space:nowrap;pointer-events:none;z-index:2;text-transform:uppercase;letter-spacing:.03em;overflow:hidden;text-overflow:ellipsis;}'
      + '.hm-tile{position:absolute;overflow:hidden;cursor:pointer;border-radius:6px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;line-height:1.07;background-image:linear-gradient(177deg,rgba(255,255,255,.18) 0%,rgba(255,255,255,.02) 45%,rgba(0,0,0,.18) 100%);box-shadow:inset 0 1px 0 rgba(255,255,255,.24),inset 0 -2px 5px rgba(0,0,0,.2),0 1px 2px rgba(0,0,0,.26);transition:background-color .5s cubic-bezier(.4,0,.2,1),color .5s,box-shadow .16s,transform .16s cubic-bezier(.2,.7,.3,1),filter .16s;}'
      + '.hm-tile.big{border-radius:8px;background-image:linear-gradient(172deg,rgba(255,255,255,.22) 0%,rgba(255,255,255,.03) 42%,rgba(0,0,0,.2) 100%);box-shadow:inset 0 1px 0 rgba(255,255,255,.3),inset 0 -3px 8px rgba(0,0,0,.24),0 4px 12px rgba(0,0,0,.34);}'
      + '.hm-tile.huge{border-radius:11px;background-image:linear-gradient(168deg,rgba(255,255,255,.26) 0%,rgba(255,255,255,.04) 40%,rgba(0,0,0,.22) 100%);box-shadow:inset 0 2px 0 rgba(255,255,255,.34),inset 0 -5px 14px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.46);}'
      + '.hm-tile:hover{transform:translateY(-3px) scale(1.06);z-index:6;filter:brightness(1.13) saturate(1.08);box-shadow:0 16px 40px rgba(0,0,0,.55),0 0 32px var(--tg,rgba(255,255,255,.32)),0 0 0 1.5px rgba(255,255,255,.95),inset 0 1px 0 rgba(255,255,255,.34);}'
      + '.hm-tile .sym{font-weight:800;letter-spacing:.2px;text-shadow:0 1px 2px rgba(0,0,0,.34);}'
      + '.hm-tile .pc{font-weight:600;font-variant-numeric:tabular-nums;opacity:.95;margin-top:2px;text-shadow:0 1px 2px rgba(0,0,0,.3);}'
      + '.hm-tile.tiny .pc{display:none;} .hm-tile.micro .sym{display:none;}'
      // hover card
      + '.hm-card{position:fixed;z-index:1200;left:0;top:0;width:300px;max-width:calc(100vw - 16px);'
      + 'background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid color-mix(in srgb,var(--text) 16%,var(--line));'
      + 'border-radius:14px;padding:13px 14px;box-shadow:0 18px 46px rgba(0,0,0,.5);backdrop-filter:blur(9px);-webkit-backdrop-filter:blur(9px);'
      + 'pointer-events:none;opacity:0;transform:translateY(5px);transition:opacity .14s,transform .14s;}'
      + '.hm-card.on{opacity:1;transform:none;}'
      + '.hm-card .up{color:var(--up);} .hm-card .dn{color:var(--down);}'
      + '.hm-c-hd{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}'
      + '.hm-c-sym{font-size:18px;font-weight:800;color:var(--text);line-height:1;}'
      + '.hm-c-nm{font-size:10.5px;color:var(--muted);margin-top:3px;line-height:1.3;}'
      + '.hm-c-px{text-align:right;white-space:nowrap;}'
      + '.hm-c-pxv{font-size:14px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--text);}'
      + '.hm-c-chg{font-size:11.5px;font-weight:800;font-variant-numeric:tabular-nums;}'
      + '.hm-c-body{margin:9px 0 2px;}'
      + '.hm-c-load{display:flex;gap:5px;padding:4px 0;} .hm-c-load span{width:7px;height:7px;border-radius:50%;background:var(--muted);opacity:.5;animation:hmpulse 1s infinite;}'
      + '.hm-c-load span:nth-child(2){animation-delay:.15s;} .hm-c-load span:nth-child(3){animation-delay:.3s;}'
      + '@keyframes hmpulse{0%,100%{opacity:.25;}50%{opacity:.8;}}'
      + '.hm-c-conv{display:flex;align-items:center;gap:9px;margin-bottom:7px;}'
      + '.hm-c-band{font-size:10.5px;font-weight:800;padding:2px 9px;border-radius:8px;letter-spacing:.01em;}'
      + '.hm-c-band.b-high{color:var(--up);background:color-mix(in srgb,var(--up) 16%,transparent);border:1px solid color-mix(in srgb,var(--up) 36%,transparent);}'
      + '.hm-c-band.b-con{color:var(--g-cold);background:color-mix(in srgb,var(--g-cold) 15%,transparent);border:1px solid color-mix(in srgb,var(--g-cold) 34%,transparent);}'
      + '.hm-c-band.b-neu{color:var(--muted);background:var(--panel2);border:1px solid var(--line);}'
      + '.hm-c-band.b-low{color:var(--down);background:color-mix(in srgb,var(--down) 15%,transparent);border:1px solid color-mix(in srgb,var(--down) 34%,transparent);}'
      + '.hm-c-score{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--text);} .hm-c-score small{font-size:10.5px;color:var(--muted);font-weight:600;}'
      + '.hm-c-verdict{font-size:12.5px;font-weight:600;line-height:1.45;color:var(--text);}'
      + '.hm-c-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px;}'
      + '.hm-c-chip{font-size:10px;font-weight:600;padding:2px 7px;border-radius:6px;background:var(--panel2);border:1px solid var(--line);color:var(--muted);}'
      + '.hm-c-chip.ok{color:var(--up);border-color:color-mix(in srgb,var(--up) 32%,var(--line));}'
      + '.hm-c-chip.warn{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 32%,var(--line));}'
      + '.hm-c-meta{display:flex;flex-wrap:wrap;gap:6px 10px;margin-top:9px;font-size:11px;color:var(--muted);align-items:center;}'
      + '.hm-c-tag{display:inline-flex;align-items:center;gap:4px;} .hm-c-tag b{font-variant-numeric:tabular-nums;color:var(--text);}'
      + '.hm-c-tag.ok b,.hm-c-tag.ok{color:var(--up);} .hm-c-tag.warn,.hm-c-tag.warn b{color:var(--warn);}'
      + '.hm-c-desc{font-size:11px;color:var(--muted);line-height:1.5;margin-top:9px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}'
      + '.hm-c-stub{font-size:11.5px;color:var(--muted);line-height:1.5;}'
      + '.hm-c-strip{display:flex;flex-wrap:wrap;gap:0;margin-top:11px;padding-top:9px;border-top:1px solid var(--line);}'
      + '.hm-c-m{flex:1 1 16.6%;text-align:center;min-width:34px;} .hm-c-m .k{display:block;font-size:8.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;} .hm-c-m .v{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;}'
      + '.hm-c-foot{margin-top:10px;font-size:11px;font-weight:700;color:var(--link);}'
      // scorecard
      + '.hm-sc-hd{display:flex;align-items:center;gap:10px;margin-bottom:11px;}'
      + '.hm-sc-tit{font-size:14px;font-weight:800;color:var(--text);}'
      + '.hm-sc-meta{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);}'
      + '.hm-sc-exp{margin-left:auto;font:700 12px Inter,sans-serif;color:var(--text);background:var(--panel2);border:1px solid var(--line);padding:6px 12px;border-radius:9px;cursor:pointer;transition:background .15s,border-color .15s;}'
      + '.hm-sc-exp:hover{border-color:color-mix(in srgb,var(--link) 55%,var(--line));background:color-mix(in srgb,var(--link) 10%,var(--panel2));}'
      + '.hm-sc-strip{position:relative;width:100%;border-radius:14px;overflow:hidden;margin-bottom:11px;background:radial-gradient(130% 120% at 50% -15%,color-mix(in srgb,var(--panel2) 80%,transparent),var(--panel) 75%);border:1px solid var(--hm-edge);box-shadow:inset 0 0 40px rgba(0,0,0,.2),inset 0 1px 0 rgba(255,255,255,.05);}'
      + '.hm-sc-tile{position:absolute;border-radius:9px;padding:7px 9px;overflow:hidden;cursor:pointer;display:flex;flex-direction:column;justify-content:space-between;background-image:linear-gradient(177deg,rgba(255,255,255,.18),rgba(255,255,255,.02) 45%,rgba(0,0,0,.16));box-shadow:inset 0 1px 0 rgba(255,255,255,.22),inset 0 -2px 4px rgba(0,0,0,.18),0 2px 5px rgba(0,0,0,.22);transition:transform .16s cubic-bezier(.2,.7,.3,1),box-shadow .16s,filter .16s;}'
      + '.hm-sc-tile:hover{transform:translateY(-2px) scale(1.03);filter:brightness(1.08);box-shadow:0 10px 24px rgba(0,0,0,.4),0 0 0 1.5px rgba(255,255,255,.85);}'
      + '.hm-sc-tile .t1{font-size:11.5px;font-weight:800;line-height:1.1;} .hm-sc-tile .t2{font-size:10px;font-weight:700;font-variant-numeric:tabular-nums;opacity:.92;} .hm-sc-tile .t3{font-size:9px;opacity:.82;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
      + '.hm-sc-foot{display:flex;align-items:center;gap:16px;flex-wrap:wrap;font-size:11px;}'
      + '.hm-sc-breadth{display:flex;align-items:center;gap:8px;flex:1;min-width:160px;}'
      + '.hm-sc-breadth .lab{color:var(--muted);text-transform:uppercase;letter-spacing:.05em;font-weight:700;font-size:10px;white-space:nowrap;}'
      + '.hm-sc-bar{flex:1;height:7px;border-radius:4px;overflow:hidden;display:flex;background:var(--panel2);min-width:60px;} .hm-sc-bar i{display:block;height:100%;} .hm-sc-bar i.up{background:var(--up);} .hm-sc-bar i.dn{background:var(--down);}'
      + '.hm-sc-breadth .cnt{font-variant-numeric:tabular-nums;color:var(--muted);} .hm-sc-breadth .cnt b.up{color:var(--up);} .hm-sc-breadth .cnt b.dn{color:var(--down);}'
      + '.hm-sc-lead{display:flex;align-items:center;gap:6px;flex-wrap:wrap;} .hm-sc-lead .lab{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:700;} .hm-sc-lead .lab.lag{margin-left:6px;}'
      + '.hm-sc-chip{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;padding:2px 8px;border-radius:7px;background:var(--panel2);border:1px solid var(--line);} .hm-sc-chip.up{color:var(--up);} .hm-sc-chip.dn{color:var(--down);}'
      // overlay
      + '.hm-ov{position:fixed;inset:0;z-index:1000;display:flex;align-items:stretch;justify-content:center;}'
      + '.hm-ov-scrim{position:absolute;inset:0;background:rgba(4,6,10,.66);backdrop-filter:blur(7px) saturate(1.1);-webkit-backdrop-filter:blur(7px) saturate(1.1);opacity:0;transition:opacity .3s;}'
      + '.hm-ov.open .hm-ov-scrim{opacity:1;}'
      + '.hm-ov-panel{position:relative;margin:auto;width:min(1680px,96vw);height:min(94vh,1280px);background:linear-gradient(180deg,color-mix(in srgb,var(--panel2) 50%,var(--bg)),var(--bg) 58%);border:1px solid var(--hm-edge);border-radius:20px;box-shadow:0 40px 120px rgba(0,0,0,.65),inset 0 1px 0 rgba(255,255,255,.06);display:flex;flex-direction:column;overflow:hidden;opacity:0;transform:translateY(12px) scale(.985);transition:opacity .3s,transform .3s cubic-bezier(.2,.7,.3,1);}'
      + '.hm-ov.open .hm-ov-panel{opacity:1;transform:none;}'
      + '.hm-ov-head{display:flex;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line);flex:none;}'
      + '.hm-ov-head .t{font-size:15px;font-weight:800;color:var(--text);}'
      + '.hm-ov-x{margin-left:auto;width:32px;height:32px;border-radius:9px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font-size:14px;cursor:pointer;transition:background .15s;} .hm-ov-x:hover{background:var(--panel);}'
      + '.hm-ov-body{flex:1;overflow:auto;padding:16px 18px 22px;}'
      // mobile
      + '.hm-mgrp{margin-bottom:14px;}'
      + '.hm-mhd{display:flex;align-items:center;gap:9px;padding:8px 11px;background:var(--panel2);border:1px solid var(--line);border-radius:10px 10px 0 0;border-bottom:0;}'
      + '.hm-mhd .nm{font-size:12.5px;font-weight:800;color:var(--text);} .hm-mhd .pc{font-size:11.5px;font-weight:700;font-variant-numeric:tabular-nums;} .hm-mhd .pc.up{color:var(--up);} .hm-mhd .pc.dn{color:var(--down);}'
      + '.hm-mbr{margin-left:auto;width:58px;height:7px;border-radius:4px;overflow:hidden;display:flex;background:var(--panel);} .hm-mbr i{display:block;height:100%;} .hm-mbr i.up{background:var(--up);} .hm-mbr i.dn{background:var(--down);}'
      + '.hm-mrow{display:flex;align-items:center;gap:11px;padding:11px 12px;border:1px solid var(--line);border-top:0;background:var(--panel);text-decoration:none;}'
      + '.hm-mgrp .hm-mrow:last-child{border-radius:0 0 10px 10px;}'
      + '.hm-mpc{font-size:13px;font-weight:800;font-variant-numeric:tabular-nums;padding:6px 9px;border-radius:9px;min-width:66px;text-align:center;flex:none;background-image:linear-gradient(177deg,rgba(255,255,255,.18),rgba(0,0,0,.16));box-shadow:inset 0 1px 0 rgba(255,255,255,.22),0 2px 6px rgba(0,0,0,.25);text-shadow:0 1px 2px rgba(0,0,0,.3);}'
      + '.hm-mid{flex:1;min-width:0;display:flex;flex-direction:column;} .hm-mid b{font-size:14px;font-weight:800;color:var(--text);} .hm-mid span{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
      + '.hm-mgo{color:var(--muted);font-size:20px;font-weight:700;flex:none;}'
      + '.hm-mobile .hm-legend,.hm-mobile .hm-read-src{display:none;} .hm-mobile .hm-sort{display:flex;}'
      // reduced motion
      + '@media (prefers-reduced-motion: reduce){.hm-tile,.hm-card,.hm-ov-scrim,.hm-ov-panel{transition:none !important;} .hm-c-load span{animation:none;}}'
      + '@media (max-width:560px){.hm-bar{gap:8px;} .hm-sc-foot{gap:10px;}}';
    var st = document.createElement('style');
    st.id = 'mm-heatmap-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  /* ====================================================================== */
  /*  BOOT                                                                   */
  /* ====================================================================== */
  function boot() {
    injectStyle();
    var full = document.getElementById('heatmap-full');
    var score = document.getElementById('heatmap-scorecard');
    if (!full && !score) return;   // page doesn't use the heatmap
    loadData().then(function (data) {
      if (full) {
        if (!data.tiles || !data.tiles.length) {
          full.innerHTML = '<div class="hm-empty" style="padding:48px;text-align:center;color:var(--muted)">'
            + L('No heatmap data available.', '暂无热力图数据。') + '</div>';
        } else createFullView(full, data);
      }
      if (score) {
        if (!data.tiles || !data.tiles.length) { score.style.display = 'none'; }
        else renderScorecard(score, data);
      }
    }).catch(function (e) {
      if (score) score.style.display = 'none';
      if (full) full.innerHTML = '<div class="hm-empty" style="padding:48px;text-align:center;color:var(--muted)">'
        + L('Could not load heatmap data.', '无法加载热力图数据。') + '</div>';
      if (window.console) console.error('heatmap load failed', e);
    });
  }

  window.MMHeatmap = { openOverlay: openOverlay };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

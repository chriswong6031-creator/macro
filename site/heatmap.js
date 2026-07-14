/* heatmap.js — the S&P 500 market heatmap, one shared renderer for three
 * surfaces:
 *   #heatmap-full       → the full squarified treemap (standalone page + the
 *                          expand overlay). Sector → subsector (Finviz industry)
 *                          → stock, sized by market cap, coloured by discrete
 *                          per-timeframe bins. Mirrors the Finviz / TradingView
 *                          institutional map: dense but legible, only the names
 *                          big enough to read carry a label, the rest are pure
 *                          colour. Hover a stock tile for OUR conviction read;
 *                          hover a subsector or sector header for its member
 *                          list; click a tile through to the analyzer.
 *   #heatmap-scorecard  → a compact "market at a glance" card on the dashboard,
 *                          with an Expand button that opens the full map in an
 *                          in-page overlay.
 *   (mobile)            → under 560px the full view becomes a vertical,
 *                          sector-grouped list of large rows.
 *
 * Reads marketdata/sp500_heatmap.json (offline-safe daily-close snapshot;
 * splices a live 1D when a feed is connected). Colours are computed from the
 * live CSS theme tokens so a theme/language toggle (incl. the zh red=up
 * convention) recolours instantly. No framework; depends only on theme.js.
 *
 * window.MMHeatmap.openOverlay() opens the full map over the current page.
 */
(function () {
  'use strict';

  var JSON_URL = 'marketdata/sp500_heatmap.json';
  var _dataPromises = {};               // url -> promise (one map per source)
  function loadData(url) {
    url = url || JSON_URL;
    if (!_dataPromises[url]) {
      _dataPromises[url] = fetch(url, { cache: 'no-cache' })
        .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (d) { d._url = url; return d; });
    }
    return _dataPromises[url];
  }
  // In-page freshness: the intraday lane recommits the feed every ~30 min during
  // US market hours, so an open dashboard re-pulls its map every 10 min (visible
  // tabs only) and repaints in place when generated_utc advances. The shared
  // data object is mutated so every mounted view of that url sees the update.
  var REFRESH_MS = 10 * 60 * 1000;
  var _refreshers = {};                 // url -> interval id
  function startAutoRefresh(url) {
    url = url || JSON_URL;
    if (_refreshers[url]) return;
    _refreshers[url] = setInterval(function () {
      if (document.hidden) return;
      fetch(url, { cache: 'no-cache' })
        .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (fresh) {
          return loadData(url).then(function (cur) {
            if (!fresh || !fresh.tiles || !fresh.tiles.length) return;
            if (!fresh.generated_utc || fresh.generated_utc === cur.generated_utc) return;
            Object.keys(fresh).forEach(function (k) { cur[k] = fresh[k]; });
            cur._url = url;
            try { document.dispatchEvent(new CustomEvent('hm-refresh', { detail: { url: url } })); } catch (e) { /* no-op */ }
          });
        })
        .catch(function () { /* transient — the committed payload keeps serving */ });
    }, REFRESH_MS);
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

  /* layout metrics (px) */
  var SEC_HD = 21, SUB_HD = 13, SEC_GAP = 5, SUB_GAP = 3, TILE_GAP = 1.5;

  /* ----- small helpers ----- */
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function isZh() { return document.documentElement.getAttribute('data-lang') === 'zh'; }
  function L(en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>'; }
  function lz(en, zh) { return isZh() && zh ? zh : (en || ''); }
  function fmtPc(v) {
    if (v == null || isNaN(v)) return '—';
    var a = Math.abs(v), d = a >= 100 ? 0 : (a >= 10 ? 1 : 2);
    return (v > 0 ? '+' : (v < 0 ? '−' : '')) + a.toFixed(d) + '%';
  }
  var CUR_SYM = { USD: '$', HKD: 'HK$', CAD: 'C$', CNY: '¥' };
  function fmtCap(v, cur) {            // v in absolute units of `cur` (default USD)
    if (v == null || !isFinite(v) || v <= 0) return '';
    cur = cur || 'USD';
    if (cur === 'CNY') {              // Chinese 亿 / 万亿 convention
      var yi = v / 1e8;
      if (yi >= 10000) return '¥' + (yi / 10000).toFixed(2) + '万亿';
      if (yi >= 100) return '¥' + Math.round(yi) + '亿';
      return '¥' + yi.toFixed(1) + '亿';
    }
    var sym = CUR_SYM[cur] || '$', bn = v / 1e9;
    if (bn >= 1000) return sym + (bn / 1000).toFixed(2) + 'T';
    if (bn >= 100) return sym + Math.round(bn) + 'B';
    if (bn >= 1) return sym + bn.toFixed(1) + 'B';
    return sym + Math.max(1, Math.round(v / 1e6)) + 'M';   // sub-billion (small-cap / turnover)
  }
  // Proxy-sized maps (the US map whenever the cap caches are absent) carry
  // unit-less tile sizes — never render those as a $ figure. Real-unit maps
  // either size by true market cap or declare their unit via size_label_en.
  function realSize(data) { return data.size_basis === 'marketcap' || !!data.size_label_en; }
  // tile display ticker: strip the exchange suffix so CN/HK/CA tiles read
  // "601398" / "0700" / "RY" not "601398.SS" (no-op for US tickers).
  function dispT(t) { return String(t).replace(/\.(SS|SZ|SH|HK|TO|V|TSX|NE|CN)$/i, ''); }
  // "updated 13:35 ET" from generated_utc ("YYYY-MM-DD HH:MM", UTC) — the honest
  // freshness read for a live-spliced payload, where `asof` still names the
  // close-cache date the multi-day windows are anchored to.
  function fmtUpdated(data) {
    var g = String(data.generated_utc || '');
    if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(g)) return '';
    var d = new Date(g.slice(0, 16).replace(' ', 'T') + ':00Z');
    if (isNaN(d.getTime())) return '';
    try {
      var hm = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false
      }).format(d);
      return (isZh() ? '更新于 ' : 'updated ') + hm + ' ET';
    } catch (e) { return ''; }
  }
  function fitTextFont(width, text, avgEm, minPx, maxPx) {
    var n = String(text || '').length || 1;
    var fit = (Math.max(0, width) - 6) / (n * (avgEm || 0.7));
    return Math.max(minPx, Math.min(maxPx, fit));
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
  function isLightTheme() { return document.documentElement.getAttribute('data-theme') === 'light'; }
  function relLum(c) {   // WCAG relative luminance (gamma-correct, unlike a flat rgb average)
    function f(v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  }
  function contrast(a, b) {   // WCAG contrast ratio between two rgb triples
    var la = relLum(a), lb = relLum(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }
  var FG_DARK = [16, 21, 28], FG_LIGHT = [244, 247, 251];   // #10151c / #f4f7fb
  function _relLum(c) {
    // WCAG relative luminance from an [r,g,b] 0–255 triple.
    var f = function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  }
  function fgFor(c) {
    // Institutional board look = white labels on saturated tiles — but the
    // brightest bins (pure green ~#1ec173) fail WCAG 4.5:1 against white text.
    // Pick whichever of white / near-black ink gives the higher contrast on
    // THIS fill, so every ticker/percent stays legible on any bin.
    var L = _relLum(c);
    var cW = 1.05 / (L + 0.05);              // contrast of #fff over the fill
    var cB = (L + 0.05) / (0.03 + 0.05);     // contrast of near-black (#0b0d10) over the fill
    return cB > cW ? '#0b0d10' : '#ffffff';
  }
  function neutral() {
    // flat ~0% tile: a dark slate in both themes so the white label stays legible
    // (light mode used to be a pale grey that white text vanished on).
    return isLightTheme() ? [104, 111, 124] : [41, 46, 57];
  }
  function binPalette() {
    var up = hexToRgb(cssVar('--hm-up-v') || '#1ec173');
    var dn = hexToRgb(cssVar('--hm-dn-v') || '#e8485f');
    var nu = neutral(), P = {};
    if (isLightTheme()) {
      // deep, saturated bins on the white board so every tile carries white text
      // (TradingView/Finviz light): even small moves stay dark enough to read.
      P[3] = up; P[2] = mix(up, nu, 0.74); P[1] = mix(up, nu, 0.46);
      P[0.5] = mix(up, nu, 0.26); P[0] = nu; P[-0.5] = mix(dn, nu, 0.26);
      P[-1] = mix(dn, nu, 0.46); P[-2] = mix(dn, nu, 0.74); P[-3] = dn;
      P.na = [150, 156, 166];
    } else {
      // deep, rich bins for the dark board; white labels throughout.
      P[3] = up; P[2] = mix(up, nu, 0.82); P[1] = mix(up, nu, 0.46);
      P[0.5] = mix(up, nu, 0.26); P[0] = nu; P[-0.5] = mix(dn, nu, 0.26);
      P[-1] = mix(dn, nu, 0.46); P[-2] = mix(dn, nu, 0.82); P[-3] = dn;
      P.na = mix(hexToRgb(cssVar('--panel2') || '#1e222a'), nu, 0.5);
    }
    return P;
  }
  function binIndex(pc, edges) {
    if (pc == null || isNaN(pc)) return 'na';
    if (pc === 0) return 0;
    var a = Math.abs(pc), s = pc < 0 ? -1 : 1;
    var lvl = a >= edges[2] ? 3 : a >= edges[1] ? 2 : a >= edges[0] ? 1 : 0;
    // Sub-threshold but non-flat moves keep a faint directional tint (a half-step,
    // ±0.5) instead of collapsing into the flat-grey neutral — a slightly-green
    // name must never read as "unchanged". These derive from the same up/dn
    // tokens, so the zh red=up palette inverts them too.
    return lvl === 0 ? s * 0.5 : s * lvl;
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
      // themes tiles have no sub-industry level — skip the inds bucket for them
      // (only the S&P treemap reads s.inds; everything else uses s.tiles).
      if (t.industry != null) {
        var ind = s.inds[t.industry] || (s.inds[t.industry] = { name: t.industry, value: 0, tiles: [] });
        ind.tiles.push(t); ind.value += (t.size || 0);
      }
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
  function breadth(tiles, tf) {
    var adv = 0, dec = 0;
    tiles.forEach(function (t) { var v = t.perf[tf]; if (v > 0) adv++; else if (v < 0) dec++; });
    return { adv: adv, dec: dec };
  }
  function sectorLabels(data) {
    var m = {}; (data.sectors || []).forEach(function (s) { m[s.key] = { en: s.en, zh: s.zh }; }); return m;
  }

  /* ====================================================================== */
  /*  STOCK HOVER CARD — our conviction read, lazily fetched, degrades gracefully */
  /* ====================================================================== */
  var _tickerCache = {};
  function fetchTicker(t, dir) {
    dir = dir || 'stockdata';
    // window.SD only knows the US stockdata/ dir; route other markets directly.
    if (dir === 'stockdata' && window.SD && window.SD.loadTicker) return window.SD.loadTicker(t);
    var key = dir + '/' + t;
    if (Object.prototype.hasOwnProperty.call(_tickerCache, key)) return Promise.resolve(_tickerCache[key]);
    var safe = String(t).replace(/[=^]/g, '_');
    return fetch(dir + '/' + safe + '.json')
      .then(function (r) { if (!r.ok) throw new Error('absent'); return r.json(); })
      .then(function (j) { _tickerCache[key] = j; return j; })
      .catch(function () { _tickerCache[key] = null; return null; });
  }

  function positionFloat(el, cx, cy) {
    // measure once per content change and cache (el._w/_h); a same-content
    // reposition (cursor sweeping within one tile) then avoids forcing a reflow
    // by reading offsetWidth/Height on every mousemove.
    if (!el._w) { el._w = el.offsetWidth; el._h = el.offsetHeight; }
    var pad = 15, w = el._w, h = el._h;
    var x = cx + pad, y = cy + pad;
    if (x + w > window.innerWidth - 8) x = cx - w - pad;
    if (y + h > window.innerHeight - 8) y = cy - h - pad;
    el.style.left = Math.max(8, x) + 'px';
    el.style.top = Math.max(8, y) + 'px';
  }

  var _card = null, _cardFor = null, _cardTimer = null;
  var _ptrX = null, _ptrY = null;   // latest pointer position (for async re-anchoring)
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
  // The bottom strip stays scannable: five canonical windows, not every
  // timeframe the feed carries (12 columns crammed unreadably at 300px).
  // Terse code labels so no column ever wraps ("Year to date" did).
  var CARD_TFS = ['1D', '1W', '1M', 'YTD', '1Y'];
  var CARD_TF_LAB = { '1D': ['1D', '1日'], '1W': ['1W', '1周'], '1M': ['1M', '1月'],
                      'YTD': ['YTD', '年初至今'], '1Y': ['1Y', '1年'] };
  function cardBaseHtml(data, t) {
    var labs = sectorLabels(data);
    var lab = labs[t.sector] || { en: t.sector, zh: t.sector };
    var cur = t.perf[data._tf];
    var cls = cur == null ? '' : (cur >= 0 ? 'up' : 'dn');
    var cap = realSize(data) ? fmtCap(t.size, data.currency) : '';
    var nm = (isZh() && t.name_zh) ? t.name_zh : t.name;
    var strip = '';
    (data.timeframes || []).forEach(function (tf) {
      if (CARD_TFS.indexOf(tf.key) === -1) return;
      var v = t.perf[tf.key];
      if (v == null || isNaN(v)) return;
      var kl = CARD_TF_LAB[tf.key] || [tf.en, tf.zh];
      strip += '<div class="hm-c-m"><span class="k">' + L(kl[0], kl[1]) + '</span>'
        + '<span class="v ' + (v >= 0 ? 'up' : 'dn') + '">' + fmtPc(v) + '</span></div>';
    });
    return ''
      + '<div class="hm-c-hd">'
      +   '<div class="hm-c-id"><div class="hm-c-sym">' + esc(dispT(t.t)) + '</div>'
      +     '<div class="hm-c-nm">' + esc(nm) + ' · ' + L(lab.en, lab.zh) + '</div></div>'
      +   '<div class="hm-c-px"><div class="hm-c-pxv" data-px>' + (cap || '—') + '</div>'
      +     '<div class="hm-c-chg ' + cls + '">' + fmtPc(cur) + '</div></div>'
      + '</div>'
      + '<div class="hm-c-body" data-body><div class="hm-c-load"><span></span><span></span><span></span></div></div>'
      + '<div class="hm-c-strip">' + strip + '</div>'
      + '<div class="hm-c-foot">' + L('View full analysis', '查看完整分析') + ' →</div>';
  }
  function enrichCard(el, data, t, rec) {
    el._w = 0;                         // card grows with the enriched body → re-measure
    var pxEl = el.querySelector('[data-px]');
    var body = el.querySelector('[data-body]');
    if (!body) return;
    if (!rec) {
      body.innerHTML = '<div class="hm-c-stub">'
        + L('No nightly read for this name yet — open the analyzer for the full breakdown.',
            '该标的暂无每晚分析 — 点击打开分析器查看完整拆解。') + '</div>';
      return;
    }
    // Deliberately spare: our band + score + one-line verdict, then two facts
    // (size, vs 200d). Everything else lives one click away in the analyzer —
    // a hover card that needs reading isn't a hover card.
    var tech = rec.tech || {}, conv = rec.conviction || {};
    if (pxEl && tech.price != null) {
      var pxSym = CUR_SYM[data.currency] || '$';
      pxEl.textContent = pxSym + (tech.price >= 100 ? Math.round(tech.price).toLocaleString()
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
    var meta = '';
    // Label the size value (e.g. "Mkt cap ¥2.54万亿", or "Avg turnover HK$14.8B"
    // for the HK map) so the number is never mistaken for something it isn't.
    var szLab = data.size_basis === 'equal' ? '' : lz(data.size_label_en, data.size_label_zh);
    var szVal = realSize(data) ? fmtCap(t.size, data.currency) : '';
    if (szLab && szVal) meta += '<span class="hm-c-tag">' + esc(szLab) + ' <b>' + szVal + '</b></span>';
    if (tech.pct_vs_200dma != null) {
      var p2 = +tech.pct_vs_200dma;
      meta += '<span class="hm-c-tag">' + L('vs 200d', '相对200日') + ' '
        + '<b class="' + (p2 >= 0 ? 'up' : 'dn') + '">' + (p2 > 0 ? '+' : '') + p2.toFixed(0) + '%</b></span>';
    }
    if (meta) h += '<div class="hm-c-meta">' + meta + '</div>';

    body.innerHTML = h || '<div class="hm-c-stub">' + L('Open the analyzer for the full read.', '打开分析器查看完整解读。') + '</div>';
  }
  function showCard(data, t, cx, cy) {
    hideMembers();
    var el = card();
    if (_cardFor !== t.t) {
      _cardFor = t.t;
      el.innerHTML = cardBaseHtml(data, t);
      el._w = 0;                       // content changed → re-measure
      el.classList.add('on');
      positionFloat(el, cx, cy);
      clearTimeout(_cardTimer);
      var want = t.t;
      _cardTimer = setTimeout(function () {
        fetchTicker(t.t, data.stockdata_dir).then(function (rec) {
          if (_cardFor !== want) return;
          enrichCard(el, data, t, rec);
          // re-anchor off the latest pointer position (the card grew), not the
          // stale coords captured when the hover began.
          positionFloat(el, _ptrX != null ? _ptrX : cx, _ptrY != null ? _ptrY : cy);
        });
      }, 110);
    } else {
      positionFloat(el, cx, cy);
    }
  }
  function hideCard() {
    _cardFor = null; clearTimeout(_cardTimer);
    if (_card) _card.classList.remove('on');
  }

  /* ====================================================================== */
  /*  GROUP HOVER POPUP — sector / subsector member list (Finviz style)      */
  /* ====================================================================== */
  var _mem = null, _memFor = null;
  function memEl() {
    if (_mem) return _mem;
    _mem = document.createElement('div');
    _mem.className = 'hm-mem';
    _mem.setAttribute('role', 'tooltip');
    document.body.appendChild(_mem);
    return _mem;
  }
  // shared shell: header (title + agg), breadth sub-line, scrollable row list.
  function memShellHtml(ttl, agg, count, br, unitEn, unitZh, rowsHtml, sizeLab) {
    var tot = Math.max(1, br.adv + br.dec);
    var aggCls = agg == null ? '' : (agg >= 0 ? 'up' : 'dn');
    // sizeLab (optional) names what the right-hand value column means (e.g. the
    // HK map's column is average turnover, not market cap) so it can never be misread.
    var ct = count + ' ' + L(unitEn, unitZh) + (sizeLab ? ' · ' + esc(sizeLab) : '');
    return ''
      + '<div class="hm-mem-hd">'
      +   '<div class="hm-mem-ttl">' + ttl + '</div>'
      +   '<div class="hm-mem-agg ' + aggCls + '">' + fmtPc(agg) + '</div>'
      + '</div>'
      + '<div class="hm-mem-sub">'
      +   '<span class="hm-mem-ct">' + ct + '</span>'
      +   '<span class="hm-mem-br"><i class="up" style="width:' + (100 * br.adv / tot) + '%"></i>'
      +     '<i class="dn" style="width:' + (100 * br.dec / tot) + '%"></i></span>'
      +   '<span class="hm-mem-bn"><b class="up">' + br.adv + '▲</b> <b class="dn">' + br.dec + '▼</b></span>'
      + '</div>'
      + '<div class="hm-mem-list">' + rowsHtml + '</div>';
  }
  function memShow(key, html, cx, cy) {
    hideCard();
    var el = memEl();
    if (_memFor !== key) { _memFor = key; el.innerHTML = html; el._w = 0; el.classList.add('on'); }
    positionFloat(el, cx, cy);
  }
  // S&P 500: sector / subsector → its member stocks (ticker · name · cap).
  function showMembers(data, sectorName, subName, tiles, cx, cy) {
    var key = sectorName + '||' + (subName || '');
    if (_memFor === key) { positionFloat(memEl(), cx, cy); return; }
    var labs = sectorLabels(data);
    var lab = labs[sectorName] || { en: sectorName, zh: sectorName };
    var tf = data._tf, edges = edgesFor(tf), pal = binPalette();
    var agg = sectorAgg(data, tiles, tf);
    var br = breadth(tiles, tf);
    var ttl = subName
      ? L(esc(lab.en) + ' <span class="sub">— ' + esc(subName) + '</span>', esc(lab.zh) + ' <span class="sub">— ' + esc(subName) + '</span>')
      : L(esc(lab.en), esc(lab.zh));
    var rows = tiles.slice().sort(function (a, b) { return (b.size || 0) - (a.size || 0); });
    var cap = 18, more = Math.max(0, rows.length - cap), body = '';
    rows.slice(0, cap).forEach(function (t) {
      var pc = t.perf[tf], c = pal[binIndex(pc, edges)];
      var rnm = (isZh() && t.name_zh) ? t.name_zh : t.name;
      body += '<div class="hm-mem-row">'
        + '<span class="hm-mem-pc" style="background-color:' + rgb(c) + ';color:' + fgFor(c) + '">' + fmtPc(pc) + '</span>'
        + '<span class="hm-mem-t">' + esc(dispT(t.t)) + '</span>'
        + '<span class="hm-mem-n">' + esc(rnm) + '</span>'
        + '<span class="hm-mem-cap">' + (realSize(data) ? fmtCap(t.size, data.currency) : '') + '</span></div>';
    });
    if (more) body += '<div class="hm-mem-more">+' + more + ' ' + L('more', '更多') + '</div>';
    var szLab = data.size_basis === 'equal' ? '' : lz(data.size_label_en, data.size_label_zh);
    memShow(key, memShellHtml(ttl, agg, tiles.length, br, 'names', '只', body, szLab), cx, cy);
  }
  // Themes: a subsector tile → its member tickers (ticker · move). The tile's
  // own Finviz move is the header agg (it's what colours the tile), not a
  // recomputed median of the members.
  function showSubMembers(data, tile, cx, cy) {
    var key = 'sub||' + tile.t;
    if (_memFor === key) { positionFloat(memEl(), cx, cy); return; }
    var labs = sectorLabels(data);
    var lab = labs[tile.sector] || { en: tile.sector, zh: tile.sector };
    var tf = data._tf, edges = edgesFor(tf), pal = binPalette();
    var members = (tile.members || []).map(function (m) { return { t: m.t, perf: m.perf || {} }; });
    var br = breadth(members, tf);
    var subLabel = tile.name + (tile.desc && tile.desc !== tile.name ? ' · ' + tile.desc : '');
    var ttl = L(esc(lab.en) + ' <span class="sub">— ' + esc(subLabel) + '</span>',
                esc(lab.zh) + ' <span class="sub">— ' + esc(subLabel) + '</span>');
    var rows = members.slice().sort(function (a, b) {
      var av = a.perf[tf], bv = b.perf[tf];
      return (bv == null ? -1e9 : bv) - (av == null ? -1e9 : av);
    });
    var cap = 22, more = Math.max(0, rows.length - cap), body = '';
    rows.slice(0, cap).forEach(function (m) {
      var pc = m.perf[tf], c = pal[binIndex(pc, edges)];
      body += '<div class="hm-mem-row">'
        + '<span class="hm-mem-pc" style="background-color:' + rgb(c) + ';color:' + fgFor(c) + '">' + fmtPc(pc) + '</span>'
        + '<span class="hm-mem-t">' + esc(m.t) + '</span></div>';
    });
    if (more) body += '<div class="hm-mem-more">+' + more + ' ' + L('more', '更多') + '</div>';
    memShow(key, memShellHtml(ttl, tile.perf[tf], members.length, br, 'members', '成员', body), cx, cy);
  }
  // Themes: a theme header → its subsectors (name · move · member count).
  function showThemeSubs(data, themeName, subTiles, cx, cy) {
    var key = 'theme||' + themeName;
    if (_memFor === key) { positionFloat(memEl(), cx, cy); return; }
    var labs = sectorLabels(data);
    var lab = labs[themeName] || { en: themeName, zh: themeName };
    var tf = data._tf, edges = edgesFor(tf), pal = binPalette();
    var agg = sectorAgg(data, subTiles, tf);
    var br = breadth(subTiles, tf);
    var rows = subTiles.slice().sort(function (a, b) {
      var av = a.perf[tf], bv = b.perf[tf];
      return (bv == null ? -1e9 : bv) - (av == null ? -1e9 : av);
    });
    var body = '';
    rows.forEach(function (t) {
      var pc = t.perf[tf], c = pal[binIndex(pc, edges)];
      body += '<div class="hm-mem-row">'
        + '<span class="hm-mem-pc" style="background-color:' + rgb(c) + ';color:' + fgFor(c) + '">' + fmtPc(pc) + '</span>'
        + '<span class="hm-mem-t">' + esc(t.name) + '</span>'
        + '<span class="hm-mem-cap">' + (t.members ? t.members.length : t.size) + '</span></div>';
    });
    memShow(key, memShellHtml(L(esc(lab.en), esc(lab.zh)), agg, subTiles.length, br, 'subsectors', '子板块', body), cx, cy);
  }
  function hideMembers() { _memFor = null; if (_mem) _mem.classList.remove('on'); }

  /* ====================================================================== */
  /*  FULL VIEW — controls + treemap (desktop) / sector list (mobile)        */
  /* ====================================================================== */
  function createFullView(root, data) {
    // Themes map: two levels (theme → subsector-leaf tile), tiles are subsectors
    // that carry a member list; hover shows members. Default (S&P) is unchanged.
    var IS_THEMES = data.map_type === 'themes';
    // Flat Sector → stock treemap (CN / HK / CA): no curated sub-industry level,
    // so one band per sector with stock tiles directly — TradingView's HSI/TSX look.
    var IS_STOCKS = data.map_type === 'stocks';
    var STOCK_URL = data.stock_url || 'stock.html#';
    root.classList.add('hm-scope', 'hm-view');
    if (IS_THEMES) root.classList.add('hm-themes');
    var hint = IS_THEMES
      ? L('Hover a subsector for its member tickers · hover a theme header for its subsectors · pick a timeframe above',
          '将鼠标悬停在子板块上查看成员个股 · 悬停主题标题查看其子板块 · 在上方选择周期')
      : IS_STOCKS
      ? L('Hover a sector header for its members · hover a tile for our read · click through to the analyzer',
          '将鼠标悬停在板块标题上查看成员 · 悬停方块查看研判 · 点击进入分析器')
      : L('Hover a sector or subsector header for its members · hover a tile for our read · click through to the analyzer',
          '将鼠标悬停在板块或子行业标题上查看成员 · 悬停方块查看研判 · 点击进入分析器');
    root.innerHTML = ''
      + '<div class="hm-bar">'
      +   '<div class="hm-tfs" role="tablist" aria-label="Timeframe"></div>'
      +   '<div class="hm-legend"></div>'
      +   '<div class="hm-grow"></div>'
      +   '<div class="hm-read"></div>'
      + '</div>'
      + '<div class="hm-sort" role="group" aria-label="Sort"></div>'
      + '<div class="hm-tm-wrap"><div class="hm-tm"></div></div>'
      + '<div class="hm-hint">' + hint + '</div>';

    var tfsEl = root.querySelector('.hm-tfs');
    var legendEl = root.querySelector('.hm-legend');
    var readEl = root.querySelector('.hm-read');
    var sortEl = root.querySelector('.hm-sort');
    var wrap = root.querySelector('.hm-tm-wrap');
    var tm = root.querySelector('.hm-tm');
    var firstLayout = true;
    var REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var IN_OV = !!(root.closest && root.closest('.hm-ov'));
    function mapHeight() {
      // In the full-page overlay the treemap fills the viewport — the map IS
      // the page (Finviz look, no scrolling). Standalone pages keep a bounded
      // band and scroll normally.
      if (IN_OV) {
        var top = wrap.getBoundingClientRect ? wrap.getBoundingClientRect().top : 0;
        return Math.max(420, window.innerHeight - top - 48);
      }
      return Math.max(560, Math.min(window.innerHeight - 140, 1280));
    }

    var TF = data.default_tf || '1D';
    if (!(data.timeframes || []).some(function (tf) { return tf.key === TF && tf.available; })) {
      var first = (data.timeframes || []).filter(function (tf) { return tf.available; })[0];
      if (first) TF = first.key;
    }
    var SORT = 'cap';
    var tileEls = [];      // {el, pcEl, t}
    var secPc = [];        // {el, tiles}
    var hier = {};         // sector -> {inds, tiles}
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
      if (key === TF) return; TF = key; data._tf = TF;
      Array.prototype.forEach.call(tfsEl.children, function (b) {
        b.classList.toggle('on', b.getAttribute('data-tf') === key);
      });
      hideCard(); hideMembers();
      if (mode === 'tree') recolor(); else layoutList();
      updateLegend();
      updateRead();
    }
    function updateLegend() {
      var e = edgesFor(TF), pal = binPalette();
      var sw = '';
      [-3, -2, -1, -0.5, 0, 0.5, 1, 2, 3].forEach(function (b) {
        sw += '<span class="hm-lg-sw" style="background:' + rgb(pal[b]) + '"></span>';
      });
      legendEl.innerHTML = '<span class="hm-lg-end">−' + edgeFmt(e[2]) + '%</span>'
        + '<span class="hm-lg-sws">' + sw + '</span>'
        + '<span class="hm-lg-end">+' + edgeFmt(e[2]) + '%</span>'
        + '<span class="hm-lg-step">' + L('bins', '分档') + ' ±' + edgeFmt(e[0]) + '/' + edgeFmt(e[1]) + '/' + edgeFmt(e[2]) + '</span>';
    }
    function updateRead() {
      var br = breadth(data.tiles, TF);
      var live = data.source === 'polygon-live';
      var when = live ? (fmtUpdated(data) || data.asof || '—') : (data.asof || '—');
      var srcEn, srcZh;
      if (IS_THEMES) {
        srcEn = 'Themes · ' + (data.asof || '—');
        srcZh = '主题 · ' + (data.asof || '—');
      } else {
        srcEn = (live ? 'Live · 15-min delayed' : 'Daily close') + ' · ' + when;
        srcZh = (live ? '实时 · 延迟15分钟' : '日线收盘') + ' · ' + when;
      }
      readEl.innerHTML = '<span class="hm-dot ' + (live ? 'live' : '') + '"></span>'
        + '<span class="hm-read-src">' + L(srcEn, srcZh) + '</span>'
        + '<span class="hm-read-br"><b class="up">' + br.adv + ' ▲</b> <b class="dn">' + br.dec + ' ▼</b></span>';
    }

    /* ----- treemap (desktop) ----- */
    function tileLabel(t, tw, th) {
      // Finviz rule: a tile carries a label ONLY when the full ticker fits at a
      // readable size — never clipped, never squeezed below legibility. Tiles
      // too small for that are pure colour (their name lives in the hover card
      // and the sector member list).
      var pc = t.perf[TF];
      // CN/HK maps opt into a company-name label (data.tile_label==='name') — a
      // bare 601398 / 0700 code is meaningless at a glance. Prefer the Chinese
      // name, fall back to the English name, then the ticker. US / Canada leave
      // tile_label unset and keep the recognizable ticker.
      var sym = data.tile_label === 'name' ? (t.name_zh || t.name || dispT(t.t)) : dispT(t.t);
      // CJK glyphs are ~full-em wide vs ~0.6em for latin/digits, so a 4-char name
      // needs a wider per-char budget than a 6-digit code to fit the same tile.
      var cjk = false; for (var _i = 0; _i < sym.length; _i++) { var _cc = sym.charCodeAt(_i); if (_cc >= 0x3400 && _cc <= 0x9fff) { cjk = true; break; } }
      var nch = sym.length || 1;
      var fitF = (tw - 6) / (nch * (cjk ? 1.06 : 0.78));
      var symF = Math.min(tw / 3.7, th * 0.52, fitF, 22);
      if (symF < (cjk ? 8 : 7) || th < 15) return '';
      var s = '<span class="sym' + (symF < 10 ? ' sm' : '') + '" style="font-size:' + symF.toFixed(1) + 'px">' + esc(sym) + '</span>';
      var pcText = fmtPc(pc);
      var pcF = Math.min(tw / 5.4, th * 0.34, fitTextFont(tw, pcText, 0.62, 5, 13), 13);
      if (tw >= 44 && th >= 32 && pcF >= 6.5) {
        s += '<span class="pc" style="font-size:' + pcF.toFixed(1) + 'px">' + pcText + '</span>';
      }
      return s;
    }
    function layoutTree() {
      mode = 'tree'; root.classList.remove('hm-mobile');
      var animate = firstLayout && !REDUCE; firstLayout = false;
      tileEls = []; secPc = [];
      var H = mapHeight();
      wrap.style.height = H + 'px'; tm.style.height = H + 'px';
      var W = tm.clientWidth || wrap.clientWidth;
      if (W <= 0) { requestAnimationFrame(layoutTree); return; }

      hier = groupHierarchy(data);
      var secItems = Object.keys(hier).map(function (k) { return { value: hier[k].value, ref: hier[k] }; });
      var secRects = squarify(secItems, 0, 0, W, H);
      var html = [], si = 0;

      secRects.forEach(function (sr) {
        var s = sr.ref;
        var x = sr.x + SEC_GAP / 2, y = sr.y + SEC_GAP / 2, w = sr.w - SEC_GAP, h = sr.h - SEC_GAP;
        if (w <= 2 || h <= 2) return;
        var lab = labs[s.name] || { en: s.name, zh: s.name };
        var hd = (h > 40 && w > 78) ? Math.min(SEC_HD, h * 0.42) : 0;
        html.push('<div class="hm-sec" style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px">');
        if (hd) {
          html.push('<div class="hm-sec-hd" data-sec-name="' + esc(s.name) + '" style="height:' + hd + 'px;line-height:' + hd + 'px">'
            + '<span class="nm">' + L(esc(lab.en), esc(lab.zh)) + '</span>'
            + (w > 132 ? '<span class="pc" data-secpc="' + si + '"></span>' : '')
            + '<span class="hm-sec-i">ⓘ</span></div>');
          secPc.push({ key: si, tiles: s.tiles, show: w > 132, sector: s.name });
        }
        var innerY = hd, innerH = h - hd;
        var indItems = Object.keys(s.inds).map(function (k) { return { value: s.inds[k].value, ref: s.inds[k] }; });
        var indRects = squarify(indItems, 0, 0, w, innerH);
        indRects.forEach(function (ir) {
          var ind = ir.ref;
          var ix = ir.x + SUB_GAP / 2, iy = innerY + ir.y + SUB_GAP / 2, iw = ir.w - SUB_GAP, ih = ir.h - SUB_GAP;
          if (iw <= 2 || ih <= 2) return;
          var shd = (ih > 26 && iw > 48) ? SUB_HD : 0;
          html.push('<div class="hm-sub" data-sub-sec="' + esc(s.name) + '" data-sub-ind="' + esc(ind.name)
            + '" style="left:' + ix + 'px;top:' + iy + 'px;width:' + iw + 'px;height:' + ih + 'px">');
          if (shd) {
            html.push('<div class="hm-sub-hd" style="height:' + shd + 'px;line-height:' + shd + 'px">'
              + '<span class="snm">' + esc(ind.name) + '</span></div>');
          }
          var tileTop = shd;
          var tRects = squarify(ind.tiles.map(function (t) { return { value: (t.size || 0.0001), ref: t }; }),
            0, 0, iw, ih - tileTop);
          tRects.forEach(function (tr) {
            var t = tr.ref;
            var tw = tr.w - TILE_GAP, th = tr.h - TILE_GAP;
            if (tw < 2 || th < 2) return;
            var cls = 'hm-tile';
            if (tw >= 96 && th >= 56) cls += ' big';
            if (tw >= 150 && th >= 104) cls += ' huge';
            if (animate) cls += ' hm-in';
            var dly = animate ? ';animation-delay:' + Math.min(tileEls.length * 0.8, 480).toFixed(0) + 'ms' : '';
            html.push('<div class="' + cls + '" data-i="' + tileEls.length + '" style="left:' + tr.x + 'px;top:'
              + (tileTop + tr.y) + 'px;width:' + tw + 'px;height:' + th + 'px' + dly + '">'
              + tileLabel(t, tw, th) + '</div>');
            tileEls.push({ t: t });
          });
          html.push('</div>');  // .hm-sub
        });
        html.push('</div>');    // .hm-sec
        si++;
      });
      tm.innerHTML = html.join('');
      Array.prototype.forEach.call(tm.querySelectorAll('.hm-tile'), function (el) {
        var rec = tileEls[+el.getAttribute('data-i')];
        rec.el = el; rec.pcEl = el.querySelector('.pc');
      });
      secPc.forEach(function (sp) { sp.el = sp.show ? tm.querySelector('.pc[data-secpc="' + sp.key + '"]') : null; });
      recolor();
    }

    /* ----- themes treemap (theme → subsector-leaf tile) ----- */
    function tileLabelThemes(t, tw, th) {
      var pc = t.perf[TF];
      var showName = tw >= 30 && th >= 16;
      if (!showName) return '';
      var nameF = Math.max(8.5, Math.min(tw / 6.2, th * 0.34, 15));
      // same Finviz rule as stock tiles: the % renders only when it fits at a
      // readable size — no forced floor pushing it past the tile edge.
      var pcText = fmtPc(pc);
      var pcF = Math.min(tw / 6.0, th * 0.30, fitTextFont(tw, pcText, 0.62, 5, 12.5), 12.5);
      var s = '<span class="thn" style="font-size:' + nameF.toFixed(1) + 'px">' + esc(t.name) + '</span>';
      if (tw >= 40 && th >= 28 && pcF >= 7) s += '<span class="pc" style="font-size:' + pcF.toFixed(1) + 'px">' + pcText + '</span>';
      return s;
    }
    function layoutThemes() {
      mode = 'tree'; root.classList.remove('hm-mobile');
      var animate = firstLayout && !REDUCE; firstLayout = false;
      tileEls = []; secPc = [];
      var H = mapHeight();
      wrap.style.height = H + 'px'; tm.style.height = H + 'px';
      var W = tm.clientWidth || wrap.clientWidth;
      if (W <= 0) { requestAnimationFrame(layoutThemes); return; }

      hier = {};
      data.tiles.forEach(function (t) {
        var s = hier[t.sector] || (hier[t.sector] = { name: t.sector, value: 0, tiles: [] });
        s.tiles.push(t); s.value += (t.size || 0);
      });
      var secItems = Object.keys(hier).map(function (k) { return { value: hier[k].value, ref: hier[k] }; });
      var secRects = squarify(secItems, 0, 0, W, H);
      var html = [], si = 0;

      secRects.forEach(function (sr) {
        var s = sr.ref;
        var x = sr.x + SEC_GAP / 2, y = sr.y + SEC_GAP / 2, w = sr.w - SEC_GAP, h = sr.h - SEC_GAP;
        if (w <= 2 || h <= 2) return;
        var lab = labs[s.name] || { en: s.name, zh: s.name };
        var hd = (h > 40 && w > 78) ? Math.min(SEC_HD, h * 0.42) : 0;
        html.push('<div class="hm-sec" style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px">');
        if (hd) {
          html.push('<div class="hm-sec-hd" data-sec-name="' + esc(s.name) + '" style="height:' + hd + 'px;line-height:' + hd + 'px">'
            + '<span class="nm">' + L(esc(lab.en), esc(lab.zh)) + '</span>'
            + (w > 132 ? '<span class="pc" data-secpc="' + si + '"></span>' : '')
            + '<span class="hm-sec-i">ⓘ</span></div>');
          secPc.push({ key: si, tiles: s.tiles, show: w > 132, sector: s.name });
        }
        var innerY = hd, innerH = h - hd;
        var tRects = squarify(s.tiles.map(function (t) { return { value: (t.size || 0.0001), ref: t }; }),
          0, 0, w, innerH);
        tRects.forEach(function (tr) {
          var t = tr.ref;
          var tw = tr.w - TILE_GAP, th = tr.h - TILE_GAP;
          if (tw < 2 || th < 2) return;
          var cls = 'hm-tile hm-thtile';
          if (tw >= 96 && th >= 56) cls += ' big';
          if (tw >= 150 && th >= 104) cls += ' huge';
          if (animate) cls += ' hm-in';
          var dly = animate ? ';animation-delay:' + Math.min(tileEls.length * 0.8, 480).toFixed(0) + 'ms' : '';
          html.push('<div class="' + cls + '" data-i="' + tileEls.length + '" style="left:' + tr.x + 'px;top:'
            + (innerY + tr.y) + 'px;width:' + tw + 'px;height:' + th + 'px' + dly + '">'
            + tileLabelThemes(t, tw, th) + '</div>');
          tileEls.push({ t: t });
        });
        html.push('</div>');    // .hm-sec
        si++;
      });
      tm.innerHTML = html.join('');
      Array.prototype.forEach.call(tm.querySelectorAll('.hm-tile'), function (el) {
        var rec = tileEls[+el.getAttribute('data-i')];
        rec.el = el; rec.pcEl = el.querySelector('.pc');
      });
      secPc.forEach(function (sp) { sp.el = sp.show ? tm.querySelector('.pc[data-secpc="' + sp.key + '"]') : null; });
      recolor();
    }

    /* ----- flat stocks treemap (sector → stock-leaf tile; CN / HK / CA) ----- */
    // Live-overlay: maps ticker -> tileEls index for O(1) recolor on live.js update.
    var _liveTickerIdx = {};   // ticker (e.g. "0700.HK") -> tileEls index
    var _liveObserver = null;  // MutationObserver watching .nb-chg[data-sym] mutations

    // Live market-id for each market key (matches live.js regionOf() logic).
    var _LIVE_MKT = { hk: 'hk', china: 'cn', canada: 'ca' };

    function _parsePc(text) {
      // Parse live.js chg% text like "+1.23%" or "-0.45%" -> float, or null.
      if (!text) return null;
      var s = String(text).replace(/[%\s]/g, '').replace(/−/g, '-').replace(/\+/, '');
      var v = parseFloat(s);
      return isFinite(v) ? v : null;
    }

    function _recolorTileByLive(idx, livePc) {
      // Recolor one tile from a live % change, using the same color scale as EOD.
      // Only fires when TF === '1D' (live data = intraday, not multi-day move).
      if (TF !== '1D') return;
      var rec = tileEls[idx];
      if (!rec || !rec.el) return;
      var edges = edgesFor('1D'), pal = binPalette();
      var c = pal[binIndex(livePc, edges)];
      rec.el.style.backgroundColor = rgb(c);
      rec.el.style.color = fgFor(c);
      // Update the visible % label on the tile too.
      if (rec.pcEl) rec.pcEl.textContent = fmtPc(livePc);
    }

    function _startLiveObserver() {
      // MutationObserver watching for live.js textContent writes to .nb-chg[data-sym].
      // Each mutation = live.js just painted a fresh chg% for that symbol.
      // Fail-open: if MutationObserver is unavailable (very old browser) we skip.
      if (_liveObserver || !window.MutationObserver) return;
      _liveObserver = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          var el = m.target;
          var sym = el.getAttribute && el.getAttribute('data-sym');
          if (!sym) return;
          var idx = _liveTickerIdx[sym.toUpperCase()];
          if (idx == null) return;
          var livePc = _parsePc(el.textContent);
          if (livePc != null) _recolorTileByLive(idx, livePc);
        });
      });
      // Observe the tile container — only childList+characterData mutations on
      // .nb-chg descendants (subtree). live.js writes textContent on the span
      // itself, which fires a characterData mutation on the Text node child.
      _liveObserver.observe(tm, { subtree: true, characterData: true, childList: false });
      // Also observe each .nb-chg span directly for characterData (covers both
      // el.textContent= and el.nodeValue= write paths live.js may use).
      Array.prototype.forEach.call(
        tm.querySelectorAll('.nb-chg[data-sym]'),
        function (span) { _liveObserver.observe(span, { subtree: true, characterData: true, childList: true }); }
      );
    }
    function _stopLiveObserver() {
      if (_liveObserver) { _liveObserver.disconnect(); _liveObserver = null; }
      _liveTickerIdx = {};
    }

    function layoutStocksFlat() {
      _stopLiveObserver();
      mode = 'tree'; root.classList.remove('hm-mobile');
      var animate = firstLayout && !REDUCE; firstLayout = false;
      tileEls = []; secPc = []; _liveTickerIdx = {};
      var H = mapHeight();
      wrap.style.height = H + 'px'; tm.style.height = H + 'px';
      var W = tm.clientWidth || wrap.clientWidth;
      if (W <= 0) { requestAnimationFrame(layoutStocksFlat); return; }

      hier = {};
      data.tiles.forEach(function (t) {
        var s = hier[t.sector] || (hier[t.sector] = { name: t.sector, value: 0, tiles: [] });
        s.tiles.push(t); s.value += (t.size || 0);
      });
      var secItems = Object.keys(hier).map(function (k) { return { value: hier[k].value, ref: hier[k] }; });
      var secRects = squarify(secItems, 0, 0, W, H);
      var html = [], si = 0;
      // live.js data-mkt for this market (e.g. "hk"); undefined markets get no live attrs.
      var liveMkt = _LIVE_MKT[data.market] || null;

      secRects.forEach(function (sr) {
        var s = sr.ref;
        var x = sr.x + SEC_GAP / 2, y = sr.y + SEC_GAP / 2, w = sr.w - SEC_GAP, h = sr.h - SEC_GAP;
        if (w <= 2 || h <= 2) return;
        var lab = labs[s.name] || { en: s.name, zh: s.name };
        var hd = (h > 40 && w > 78) ? Math.min(SEC_HD, h * 0.42) : 0;
        html.push('<div class="hm-sec" style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px">');
        if (hd) {
          html.push('<div class="hm-sec-hd" data-sec-name="' + esc(s.name) + '" style="height:' + hd + 'px;line-height:' + hd + 'px">'
            + '<span class="nm">' + L(esc(lab.en), esc(lab.zh)) + '</span>'
            + (w > 132 ? '<span class="pc" data-secpc="' + si + '"></span>' : '')
            + '<span class="hm-sec-i">ⓘ</span></div>');
          secPc.push({ key: si, tiles: s.tiles, show: w > 132, sector: s.name });
        }
        var innerY = hd, innerH = h - hd;
        var tRects = squarify(s.tiles.map(function (t) { return { value: (t.size || 0.0001), ref: t }; }),
          0, 0, w, innerH);
        tRects.forEach(function (tr) {
          var t = tr.ref;
          var tw = tr.w - TILE_GAP, th = tr.h - TILE_GAP;
          if (tw < 2 || th < 2) return;
          var cls = 'hm-tile';
          if (tw >= 96 && th >= 56) cls += ' big';
          if (tw >= 150 && th >= 104) cls += ' huge';
          if (animate) cls += ' hm-in';
          var dly = animate ? ';animation-delay:' + Math.min(tileEls.length * 0.8, 480).toFixed(0) + 'ms' : '';
          var idx = tileEls.length;
          // Wire live.js hooks: data-sym/data-mkt on the tile so live.js can paint
          // an nb-chg span; the hidden nb-chg span is what we observe for recolor.
          // Only wired when the market has a live feed (hk/cn/ca); benign no-op for
          // markets not in _LIVE_MKT (never breaks the non-live path).
          var liveAttrs = liveMkt
            ? ' data-sym="' + esc(t.t) + '" data-mkt="' + esc(liveMkt) + '"'
            : '';
          var liveSpan = liveMkt
            ? '<span class="nb-chg hm-live-chg" data-sym="' + esc(t.t) + '" aria-hidden="true" style="display:none"></span>'
            : '';
          if (liveMkt) { _liveTickerIdx[String(t.t).toUpperCase()] = idx; }
          html.push('<div class="' + cls + '" data-i="' + idx + '"' + liveAttrs + ' style="left:' + tr.x + 'px;top:'
            + (innerY + tr.y) + 'px;width:' + tw + 'px;height:' + th + 'px' + dly + '">'
            + tileLabel(t, tw, th) + liveSpan + '</div>');
          tileEls.push({ t: t });
        });
        html.push('</div>');    // .hm-sec
        si++;
      });
      tm.innerHTML = html.join('');
      Array.prototype.forEach.call(tm.querySelectorAll('.hm-tile'), function (el) {
        var rec = tileEls[+el.getAttribute('data-i')];
        rec.el = el; rec.pcEl = el.querySelector('.pc');
      });
      secPc.forEach(function (sp) { sp.el = sp.show ? tm.querySelector('.pc[data-secpc="' + sp.key + '"]') : null; });
      recolor();
      // Start the live observer AFTER the DOM is built.
      if (liveMkt) _startLiveObserver();
    }
    function recolor() {
      var edges = edgesFor(TF), pal = binPalette();
      tileEls.forEach(function (rec) {
        // On 1D, prefer the live chg% already painted by live.js (if any) over the
        // stale EOD value; other timeframes always use the EOD close data.
        var livePc = null;
        if (TF === '1D' && rec.el) {
          var chgSpan = rec.el.querySelector('.nb-chg.hm-live-chg[data-sym]');
          if (chgSpan && chgSpan.textContent) livePc = _parsePc(chgSpan.textContent);
        }
        var pc = (livePc != null) ? livePc : rec.t.perf[TF];
        var c = pal[binIndex(pc, edges)];
        rec.el.style.backgroundColor = rgb(c);
        rec.el.style.color = fgFor(c);
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
        var br = breadth(s.tiles, TF), tot = Math.max(1, br.adv + br.dec);
        html.push('<div class="hm-mgrp">'
          + '<div class="hm-mhd"><span class="nm">' + L(esc(lab.en), esc(lab.zh)) + '</span>'
          + '<span class="pc ' + (agg == null ? '' : agg >= 0 ? 'up' : 'dn') + '">' + fmtPc(agg) + '</span>'
          + '<span class="hm-mbr"><i class="up" style="width:' + (100 * br.adv / tot) + '%"></i>'
          + '<i class="dn" style="width:' + (100 * br.dec / tot) + '%"></i></span></div>');
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
          if (IS_THEMES) {
            // subsector row: name + a member count / description (no per-stock page)
            var det = t.members && t.members.length
              ? t.members.length + ' ' + lz('members', '成员')
              : esc(t.desc || '');
            html.push('<div class="hm-mrow hm-mrow-th">'
              + '<span class="hm-mpc" style="background-color:' + rgb(c) + ';color:' + fgFor(c) + '">' + fmtPc(pc) + '</span>'
              + '<span class="hm-mid"><b>' + esc(t.name) + '</b><span>' + det + '</span></span></div>');
            return;
          }
          // CN/HK (tile_label==='name'): lead the row with the company name and
          // drop the ticker to the sub-line. US/CA keep the ticker as the
          // headline with the name / sub-industry beneath (unchanged).
          var byName = data.tile_label === 'name';
          var nm = t.name_zh || t.name || '';
          var primary = (byName && nm) ? nm : dispT(t.t);
          var sub = (byName && nm)
            ? dispT(t.t)
            : (t.industry && t.industry !== t.sector ? t.industry
               : ((isZh() && t.name_zh) ? t.name_zh : t.name));
          html.push('<a class="hm-mrow" href="' + STOCK_URL + encodeURIComponent(t.t) + '">'
            + '<span class="hm-mpc" style="background-color:' + rgb(c) + ';color:' + fgFor(c) + '">' + fmtPc(pc) + '</span>'
            + '<span class="hm-mid"><b>' + esc(primary) + '</b><span>' + esc(sub) + '</span></span>'
            + '<span class="hm-mgo">›</span></a>');
        });
        html.push('</div>');
      });
      tm.innerHTML = html.join('');
    }

    /* ----- hover / click on the treemap ----- */
    // process the latest move; the sector lookup uses the sector NAME stored on
    // the header (not an index), so a sector that drops its header in a given
    // layout can never mis-map the popup to a neighbour.
    function processMove(e) {
      var tEl = e.target.closest && e.target.closest('.hm-tile');
      if (tEl) {
        var rec = tileEls[+tEl.getAttribute('data-i')];
        // S&P tile → our conviction card; themes tile (a subsector) → its members.
        if (rec) { IS_THEMES ? showSubMembers(data, rec.t, e.clientX, e.clientY)
                             : showCard(data, rec.t, e.clientX, e.clientY); return; }
      }
      if (!IS_THEMES) {
        var subEl = e.target.closest && e.target.closest('.hm-sub');
        if (subEl) {
          var sn = subEl.getAttribute('data-sub-sec'), inn = subEl.getAttribute('data-sub-ind');
          var grp = hier[sn] && hier[sn].inds[inn];
          if (grp) { showMembers(data, sn, inn, grp.tiles, e.clientX, e.clientY); return; }
        }
      }
      var secEl = e.target.closest && e.target.closest('.hm-sec-hd');
      if (secEl) {
        var name = secEl.getAttribute('data-sec-name');
        if (name && hier[name]) {
          IS_THEMES ? showThemeSubs(data, name, hier[name].tiles, e.clientX, e.clientY)
                    : showMembers(data, name, null, hier[name].tiles, e.clientX, e.clientY);
          return;
        }
      }
      hideCard(); hideMembers();
    }
    function onMove(e) {
      if (mode !== 'tree') return;
      _ptrX = e.clientX; _ptrY = e.clientY;
      processMove(e);
    }
    function onClick(e) {
      if (IS_THEMES) return;   // subsector tiles are hover-only (members in popup)
      var el = e.target.closest && e.target.closest('.hm-tile');
      if (!el) return;
      var rec = tileEls[+el.getAttribute('data-i')];
      if (rec) window.location.href = STOCK_URL + encodeURIComponent(rec.t.t);
    }
    function onLeave() { hideCard(); hideMembers(); }
    tm.addEventListener('mousemove', onMove);
    tm.addEventListener('mouseleave', onLeave);
    tm.addEventListener('click', onClick);

    function layout() { if (isMobile()) layoutList(); else if (IS_THEMES) layoutThemes(); else if (IS_STOCKS) layoutStocksFlat(); else layoutTree(); }

    var rt;
    function onResize() { clearTimeout(rt); rt = setTimeout(function () { hideCard(); hideMembers(); layout(); }, 150); }
    function onTheme() { hideCard(); hideMembers(); if (mode === 'tree') recolor(); else layoutList(); updateLegend(); updateRead(); }
    function onLang() { buildTabs(); buildSort(); updateLegend(); updateRead(); hideCard(); hideMembers(); layout(); }
    function onRefresh(e) {
      if (e.detail && e.detail.url !== (data._url || JSON_URL)) return;
      hideCard(); hideMembers();
      // a refresh can flip timeframe availability (e.g. intraday windows crossing
      // the coverage threshold) — never leave the selection on a dead tab.
      if (!(data.timeframes || []).some(function (tf) { return tf.key === TF && tf.available; })) {
        var first = (data.timeframes || []).filter(function (tf) { return tf.available; })[0];
        if (first) { TF = first.key; data._tf = TF; }
      }
      buildTabs(); updateLegend(); updateRead(); layout();
    }
    window.addEventListener('resize', onResize);
    document.addEventListener('themechange', onTheme);
    document.addEventListener('langchange', onLang);
    document.addEventListener('hm-refresh', onRefresh);

    data._tf = TF;
    buildTabs(); buildSort(); updateLegend(); updateRead(); layout();
    startAutoRefresh(data._url || JSON_URL);

    return {
      destroy: function () {
        window.removeEventListener('resize', onResize);
        document.removeEventListener('themechange', onTheme);
        document.removeEventListener('langchange', onLang);
        document.removeEventListener('hm-refresh', onRefresh);
        tm.removeEventListener('mousemove', onMove);
        tm.removeEventListener('mouseleave', onLeave);
        tm.removeEventListener('click', onClick);
        _stopLiveObserver();
        hideCard(); hideMembers();
      }
    };
  }

  /* ====================================================================== */
  /*  COMPACT SCORECARD (dashboard)                                          */
  /* ====================================================================== */
  // Minimized, Perplexity-style market map: a real stock-level treemap (sector →
  // stocks, sized by market cap, coloured by the 1D bin) — NOT a sector-summary
  // strip. Reuses the full map's .hm-sec / .hm-tile styling and the global hover
  // machinery. Desktop hovers a tile for our conviction card (and a sector header
  // for its members) and carries an Expand → full overlay; touch/mobile gets the
  // map with neither hover popups nor an Expand control (the standalone Sector
  // Heatmap page remains the deep view). One level shallower than the overlay —
  // no sub-industry headers — to stay legible at this height, mirroring Perplexity.
  function renderScorecard(root, data) {
    if (root.getAttribute('data-hm-init')) return;   // guard against double-init
    root.setAttribute('data-hm-init', '1');
    root.classList.add('hm-scope', 'hm-sc');
    var labs = sectorLabels(data);
    var TF = '1D';                                    // the dashboard map is a 1D snapshot
    var REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var head = ''
      + '<div class="hm-sc-hd">'
      +   '<div class="hm-sc-tit">' + L('S&amp;P 500 Heatmap', 'S&amp;P 500 热力图') + '</div>'
      +   '<div class="hm-sc-meta"></div>'
      +   '<button type="button" class="hm-sc-exp" aria-label="Expand heatmap">⤢ ' + L('Expand', '展开') + '</button>'
      + '</div>';
    var foot = ''
      + '<div class="hm-sc-foot">'
      +   '<div class="hm-sc-legend"></div>'
      +   '<div class="hm-sc-breadth"></div>'
      + '</div>';
    root.innerHTML = head + '<div class="hm-sc-map"><div class="hm-sc-tm"></div></div>' + foot;
    root.querySelector('.hm-sc-exp').addEventListener('click', openOverlay);

    function paintMeta() {
      var live = data.source === 'polygon-live';
      var when = live ? (fmtUpdated(data) || data.asof || '—') : (data.asof || '—');
      root.querySelector('.hm-sc-meta').innerHTML = '<span class="hm-dot ' + (live ? 'live' : '') + '"></span>'
        + L((live ? 'Live · 15-min delayed' : 'Daily close') + ' · ' + when + ' · ' + data.n_tiles + ' names',
            (live ? '实时 · 延迟15分钟' : '日线收盘') + ' · ' + when + ' · ' + data.n_tiles + ' 只');
    }

    var mapBox = root.querySelector('.hm-sc-map');
    var tm = root.querySelector('.hm-sc-tm');
    var tileEls = [];          // {el, t}
    var hier = {};             // sector name -> {name, value, tiles}  (rebuilt each paint)
    var firstPaint = true;

    function isMobile() { return window.matchMedia('(max-width: 560px)').matches; }
    function canHover() { return window.matchMedia('(hover: hover) and (pointer: fine)').matches; }
    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

    function tileLabel(t, tw, th) {
      // Finviz rule, compact edition: the preview map labels only the tiles
      // where the full ticker fits at a READABLE size — small tiles are pure
      // colour (fewer names, zero clipping; hover / Expand carry the detail).
      // House law: no text below 11px — a tile that can't fit an 11px ticker
      // drops the label entirely (demote to hover) rather than shrinking it.
      if (tw < 30 || th < 16) return '';
      var nch = (t.t || '').length || 1;
      var fitF = (tw - 6) / (nch * 0.78);
      var symF = Math.min(tw / 4.2, th * 0.5, fitF, 18);
      if (symF < 11) return '';
      var s = '<span class="sym" style="font-size:' + symF.toFixed(1) + 'px">' + esc(t.t) + '</span>';
      if (tw >= 46 && th >= 30) {
        var pcText = fmtPc(t.perf[TF]);
        var pcF = Math.min(tw / 5.6, th * 0.32, fitTextFont(tw, pcText, 0.62, 11, 12));
        if (pcF >= 11) s += '<span class="pc" style="font-size:' + pcF.toFixed(1) + 'px">' + pcText + '</span>';
      }
      return s;
    }
    function paintMap() {
      var W = tm.clientWidth;
      if (W <= 0) { requestAnimationFrame(paintMap); return; }
      var H = isMobile() ? Math.round(clamp(W * 1.15, 380, 560)) : Math.round(clamp(W * 0.36, 340, 520));
      mapBox.style.height = H + 'px'; tm.style.height = H + 'px';
      var animate = firstPaint && !REDUCE; firstPaint = false;
      tileEls = []; hier = {};
      var pal = binPalette(), edges = edgesFor(TF);
      var sectors = groupHierarchy(data);
      Object.keys(sectors).forEach(function (k) { hier[k] = sectors[k]; });
      var secItems = Object.keys(sectors).map(function (k) { return { value: sectors[k].value, ref: sectors[k] }; });
      var secRects = squarify(secItems, 0, 0, W, H);
      var html = [];
      secRects.forEach(function (sr) {
        var s = sr.ref;
        var x = sr.x + SEC_GAP / 2, y = sr.y + SEC_GAP / 2, w = sr.w - SEC_GAP, h = sr.h - SEC_GAP;
        if (w <= 2 || h <= 2) return;
        var lab = labs[s.name] || { en: s.name, zh: s.name };
        var hd = (h > 30 && w > 60) ? Math.min(17, h * 0.34) : 0;
        html.push('<div class="hm-sec" style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px">');
        if (hd) {
          var agg = sectorAgg(data, s.tiles, TF);
          var aggText = fmtPc(agg);
          var showAgg = w > 96;
          var aggBudget = showAgg ? Math.max(36, Math.min(58, aggText.length * 7.2 + 7)) : 0;
          var nmBudget = Math.max(24, w - 18 - aggBudget);
          var nmText = (isZh() && lab.zh) ? lab.zh : lab.en;
          var nmCjk = false; for (var _j = 0; _j < nmText.length; _j++) { var _jc = nmText.charCodeAt(_j); if (_jc >= 0x3400 && _jc <= 0x9fff) { nmCjk = true; break; } }
          // House law ≥11px: fit at 11–12px; if the section name can't reach 11px
          // in its width budget, drop it (hover on the tiles still carries the sector).
          var nmFit = fitTextFont(nmBudget, nmText, nmCjk ? 1.02 : 0.65, 6, 12);
          var nmF = clamp(nmFit, 11, 12);
          var showNm = nmFit >= 11;
          var aggFit = fitTextFont(aggBudget, aggText, 0.62, 6, 12);
          var aggF = clamp(aggFit, 11, 12);
          var showAggPc = showAgg && aggFit >= 11;
          html.push('<div class="hm-sec-hd hm-sc-sechd" data-sec-name="' + esc(s.name) + '" style="height:' + hd + 'px;line-height:' + hd + 'px">'
            + (showNm ? '<span class="nm" style="font-size:' + nmF.toFixed(1) + 'px">' + L(esc(lab.en), esc(lab.zh)) + '</span>' : '')
            + (showAggPc ? '<span class="pc ' + (agg == null ? '' : agg >= 0 ? 'up' : 'dn') + '" style="font-size:' + aggF.toFixed(1) + 'px">' + aggText + '</span>' : '')
            + '</div>');
        }
        var innerY = hd, innerH = h - hd;
        var tRects = squarify(s.tiles.map(function (t) { return { value: (t.size || 0.0001), ref: t }; }), 0, 0, w, innerH);
        tRects.forEach(function (tr) {
          var t = tr.ref;
          var tw = tr.w - TILE_GAP, th = tr.h - TILE_GAP;
          if (tw < 1.5 || th < 1.5) return;
          var c = pal[binIndex(t.perf[TF], edges)];
          var cls = 'hm-tile';
          if (tw >= 88 && th >= 50) cls += ' big';
          if (animate) cls += ' hm-in';
          var dly = animate ? ';animation-delay:' + Math.min(tileEls.length * 0.7, 360).toFixed(0) + 'ms' : '';
          html.push('<div class="' + cls + '" data-i="' + tileEls.length + '" style="left:' + tr.x + 'px;top:'
            + (innerY + tr.y) + 'px;width:' + tw + 'px;height:' + th + 'px;background-color:' + rgb(c) + ';color:' + fgFor(c)
            + dly + '">' + tileLabel(t, tw, th) + '</div>');
          tileEls.push({ t: t });
        });
        html.push('</div>');   // .hm-sec
      });
      tm.innerHTML = html.join('');
      Array.prototype.forEach.call(tm.querySelectorAll('.hm-tile'),
        function (el) { tileEls[+el.getAttribute('data-i')].el = el; });
    }
    function paintLegend() {
      var e = edgesFor(TF), pal = binPalette(), sw = '';
      [-3, -2, -1, -0.5, 0, 0.5, 1, 2, 3].forEach(function (b) { sw += '<span class="hm-lg-sw" style="background:' + rgb(pal[b]) + '"></span>'; });
      root.querySelector('.hm-sc-legend').innerHTML = '<span class="hm-lg-end">−' + edgeFmt(e[2]) + '%</span>'
        + '<span class="hm-lg-sws">' + sw + '</span>'
        + '<span class="hm-lg-end">+' + edgeFmt(e[2]) + '%</span>';
    }
    function paintBreadth() {
      var br = breadth(data.tiles, TF), tot = Math.max(1, br.adv + br.dec);
      root.querySelector('.hm-sc-breadth').innerHTML =
        '<span class="hm-sc-blab">' + L('Breadth', '涨跌广度') + '</span>'
        + '<span class="hm-sc-bar"><i class="up" style="width:' + (100 * br.adv / tot) + '%"></i>'
        + '<i class="dn" style="width:' + (100 * br.dec / tot) + '%"></i></span>'
        + '<span class="hm-sc-bn"><b class="up">' + br.adv + '▲</b> <b class="dn">' + br.dec + '▼</b></span>';
    }

    /* ----- hover (desktop only) / tap-through ----- */
    function onMove(e) {
      if (!canHover()) return;            // touch / no fine pointer → no popups
      data._tf = TF;
      var tEl = e.target.closest && e.target.closest('.hm-tile');
      if (tEl) {
        var rec = tileEls[+tEl.getAttribute('data-i')];
        if (rec) { showCard(data, rec.t, e.clientX, e.clientY); return; }
      }
      var sEl = e.target.closest && e.target.closest('.hm-sc-sechd');
      if (sEl) {
        var name = sEl.getAttribute('data-sec-name');
        if (name && hier[name]) { showMembers(data, name, null, hier[name].tiles, e.clientX, e.clientY); return; }
      }
      hideCard(); hideMembers();
    }
    function onLeave() { hideCard(); hideMembers(); }
    function onClick(e) {
      var el = e.target.closest && e.target.closest('.hm-tile');
      if (!el) return;
      var rec = tileEls[+el.getAttribute('data-i')];
      if (rec) window.location.href = 'stock.html#' + encodeURIComponent(rec.t.t);
    }
    tm.addEventListener('mousemove', onMove);
    tm.addEventListener('mouseleave', onLeave);
    tm.addEventListener('click', onClick);

    function paint() { paintMeta(); paintMap(); paintLegend(); paintBreadth(); }
    paint();
    var rt;
    window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { hideCard(); hideMembers(); paint(); }, 160); });
    document.addEventListener('themechange', function () { hideCard(); hideMembers(); paint(); });
    document.addEventListener('langchange', function () { hideCard(); hideMembers(); paint(); });
    document.addEventListener('hm-refresh', function (e) {
      if (e.detail && e.detail.url !== (data._url || JSON_URL)) return;
      hideCard(); hideMembers(); paint();
    });
    startAutoRefresh(data._url || JSON_URL);
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
        +   '<div class="hm-ov-head"><span class="t">' + L('S&amp;P 500 Heatmap', 'S&amp;P 500 热力图') + '</span>'
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
      + ':root{--hm-up-v:#14ad6c;--hm-dn-v:#e4435a;--hm-glass:color-mix(in srgb,var(--panel) 70%,transparent);--hm-edge:color-mix(in srgb,#ffffff 8%,var(--line));--hm-frame:var(--panel2);}'
      + 'html[data-theme="light"]{--hm-up-v:#1aa869;--hm-dn-v:#d83a48;--hm-glass:color-mix(in srgb,#ffffff 78%,transparent);--hm-edge:color-mix(in srgb,#0b1830 13%,var(--line));--hm-frame:#ffffff;}'
      + 'html[data-lang="zh"]{--hm-up-v:#e4435a;--hm-dn-v:#14ad6c;}'
      + 'html[data-theme="light"][data-lang="zh"]{--hm-up-v:#d83a48;--hm-dn-v:#1aa869;}'
      + '.hm-scope{font-family:Inter,-apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;}'
      + '.hm-scope .up{color:var(--up);} .hm-scope .dn{color:var(--down);}'
      // control bar
      + '.hm-bar{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;margin-bottom:12px;padding:8px 12px;border-radius:13px;background:var(--hm-glass);border:1px solid var(--hm-edge);}'
      + '.hm-tfs{display:flex;flex-wrap:wrap;gap:2px;background:color-mix(in srgb,var(--panel2) 60%,transparent);border:1px solid var(--hm-edge);border-radius:10px;padding:3px;}'
      + '.hm-tf{font:600 12px/1 Inter,sans-serif;color:var(--muted);background:transparent;border:0;padding:6px 10px;border-radius:8px;cursor:pointer;transition:background .15s,color .15s;white-space:nowrap;}'
      + '.hm-tf:hover:not(.off){color:var(--text);background:color-mix(in srgb,var(--text) 8%,transparent);} .hm-tf.on{background:var(--link);color:#fff;}'
      + '.hm-tf.off{opacity:.32;cursor:default;}'
      + '.hm-legend{display:flex;align-items:center;gap:7px;font-size:10.5px;color:var(--muted);}'
      + '.hm-lg-sws{display:inline-flex;border-radius:4px;overflow:hidden;box-shadow:0 0 0 1px rgba(0,0,0,.22);}'
      + '.hm-lg-sw{width:19px;height:12px;} '
      + '.hm-lg-end{font-variant-numeric:tabular-nums;font-weight:700;color:var(--text);}'
      + '.hm-lg-step{color:var(--muted);}'
      + '.hm-grow{flex:1 1 8px;}'
      + '.hm-read{display:flex;align-items:center;gap:8px;font-size:11.5px;color:var(--muted);flex-wrap:wrap;}'
      + '.hm-read-br{font-variant-numeric:tabular-nums;font-weight:700;}'
      + '.hm-dot{width:7px;height:7px;border-radius:50%;background:var(--muted);display:inline-block;}'
      + '.hm-dot.live{background:var(--up);box-shadow:0 0 0 3px color-mix(in srgb,var(--up) 24%,transparent);}'
      + '.hm-sort{display:none;align-items:center;gap:6px;margin:-2px 0 12px;font-size:11px;}'
      + '.hm-sort-lab{color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:700;font-size:10px;}'
      + '.hm-sortb{font:600 12px Inter,sans-serif;color:var(--muted);background:var(--panel2);border:1px solid var(--line);padding:5px 11px;border-radius:8px;cursor:pointer;}'
      + '.hm-sortb.on{background:var(--link);border-color:var(--link);color:#fff;}'
      + '.hm-hint{margin:9px 2px 0;font-size:11px;color:var(--muted);text-align:center;opacity:.85;}'
      // treemap — flat, crisp, institutional
      + '.hm-tm-wrap{position:relative;width:100%;border-radius:12px;overflow:hidden;background:var(--hm-frame);border:1px solid var(--hm-edge);}'
      + '.hm-tm{position:relative;width:100%;}'
      + '@media (prefers-reduced-motion:no-preference){.hm-tile.hm-in{animation:hmtilein .42s cubic-bezier(.2,.7,.3,1) both;}@keyframes hmtilein{from{opacity:0;transform:scale(.96);}to{opacity:1;transform:none;}}}'
      + '.hm-sec{position:absolute;overflow:hidden;border-radius:7px;background:var(--hm-frame);}'
      + '.hm-sec-hd{position:absolute;left:0;top:0;width:100%;display:flex;align-items:center;gap:7px;padding:0 9px;font-weight:800;letter-spacing:.01em;color:var(--text);white-space:nowrap;z-index:5;font-size:12.5px;cursor:help;background:transparent;}'
      + '.hm-sec-hd .nm{text-transform:uppercase;letter-spacing:.04em;font-size:11.5px;overflow:hidden;text-overflow:ellipsis;}'
      + '.hm-sec-hd .pc{font-weight:800;font-variant-numeric:tabular-nums;}'
      + '.hm-sec-hd .hm-sec-i{margin-left:auto;opacity:.4;font-size:11px;}'
      + '.hm-sec-hd:hover{background:color-mix(in srgb,var(--link) 22%,var(--panel2));} .hm-sec-hd:hover .hm-sec-i{opacity:.9;}'
      + '.hm-sub{position:absolute;overflow:hidden;border-radius:5px;}'
      + '.hm-sub-hd{position:absolute;left:0;top:0;width:100%;padding:0 5px;font-size:9px;font-weight:700;color:color-mix(in srgb,var(--text) 66%,transparent);white-space:nowrap;z-index:3;text-transform:uppercase;letter-spacing:.04em;overflow:hidden;text-overflow:ellipsis;cursor:help;background:color-mix(in srgb,#000000 24%,transparent);}'
      + '.hm-sub:hover>.hm-sub-hd{color:var(--text);background:color-mix(in srgb,var(--link) 30%,transparent);}'
      + '.hm-sub-hd .snm{pointer-events:none;}'
      + '.hm-tile{position:absolute;overflow:hidden;cursor:pointer;border-radius:2px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;line-height:1.05;transition:filter .1s,box-shadow .1s;}'
      + '.hm-tile.big{border-radius:3px;} .hm-tile.huge{border-radius:4px;}'
      + '.hm-tile:hover{z-index:8;filter:brightness(1.06);box-shadow:inset 0 0 0 2px color-mix(in srgb,var(--text) 78%,transparent);}'
      + '.hm-tile .sym,.hm-tile .pc{display:block;max-width:calc(100% - 3px);white-space:nowrap;overflow:hidden;text-overflow:clip;}'
      + '.hm-tile .sym{font-weight:800;letter-spacing:.2px;}'
      // small tiles read better without the heavy weight; tracking off too
      + '.hm-tile .sym.sm{font-weight:600;letter-spacing:0;}'
      + '.hm-tile .pc{font-weight:600;font-variant-numeric:tabular-nums;opacity:.95;margin-top:1px;}'
      // map-type switcher (multi-map host: S&P 500 ⇄ Themes …)
      + '.hm-maptype{display:inline-flex;gap:3px;margin:0 0 14px;padding:4px;border-radius:12px;background:color-mix(in srgb,var(--panel2) 60%,transparent);border:1px solid var(--hm-edge);}'
      + '.hm-mt{font:700 13px/1 Inter,sans-serif;color:var(--muted);background:transparent;border:0;padding:8px 16px;border-radius:9px;cursor:pointer;transition:background .15s,color .15s;white-space:nowrap;}'
      + '.hm-mt:hover{color:var(--text);background:color-mix(in srgb,var(--text) 7%,transparent);}'
      + '.hm-mt.on{background:var(--link);color:#fff;}'
      + '.hm-loading{padding:48px;text-align:center;color:var(--muted);}'
      // themes subsector-leaf tile: show the subsector name (not a ticker)
      + '.hm-thtile{padding:2px 4px;}'
      + '.hm-thtile .thn{font-weight:800;letter-spacing:.1px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:1.12;}'
      + '.hm-mrow-th{cursor:default;}'
      // stock hover card
      + '.hm-card{position:fixed;z-index:1200;left:0;top:0;width:300px;max-width:calc(100vw - 16px);'
      + 'background:color-mix(in srgb,var(--panel) 96%,transparent);border:1px solid color-mix(in srgb,var(--text) 16%,var(--line));'
      + 'border-radius:13px;padding:13px 14px;box-shadow:0 8px 24px rgba(0,0,0,.34);'
      + 'pointer-events:none;opacity:0;transform:translateY(4px);transition:opacity .13s,transform .13s;}'
      + '.hm-card.on{opacity:1;transform:none;}'
      + '.hm-card .up{color:var(--up);} .hm-card .dn{color:var(--down);}'
      + '.hm-c-hd{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}'
      + '.hm-c-sym{font-size:18px;font-weight:800;color:var(--text);line-height:1;}'
      + '.hm-c-nm{font-size:10.5px;color:var(--muted);margin-top:3px;line-height:1.3;}'
      + '.hm-c-px{text-align:right;white-space:nowrap;}'
      + '.hm-c-pxv{font-size:13px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--text);}'
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
      + '.hm-c-meta{display:flex;flex-wrap:wrap;gap:6px 12px;margin-top:9px;font-size:11px;color:var(--muted);align-items:center;}'
      + '.hm-c-tag{display:inline-flex;align-items:center;gap:4px;} .hm-c-tag b{font-variant-numeric:tabular-nums;color:var(--text);}'
      + '.hm-c-stub{font-size:11.5px;color:var(--muted);line-height:1.5;}'
      // five evenly-spread windows — room to breathe, never a 12-column cram
      + '.hm-c-strip{display:flex;justify-content:space-between;gap:6px;margin-top:12px;padding-top:10px;border-top:1px solid var(--line);}'
      + '.hm-c-m{flex:1;text-align:center;min-width:0;} .hm-c-m .k{display:block;font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px;} .hm-c-m .v{font-size:11.5px;font-weight:700;font-variant-numeric:tabular-nums;}'
      + '.hm-c-foot{margin-top:10px;font-size:11px;font-weight:700;color:var(--link);}'
      // member popup (sector / subsector)
      + '.hm-mem{position:fixed;z-index:1200;left:0;top:0;width:286px;max-width:calc(100vw - 16px);background:color-mix(in srgb,var(--panel) 97%,transparent);border:1px solid color-mix(in srgb,var(--text) 16%,var(--line));border-radius:13px;padding:0;box-shadow:0 8px 24px rgba(0,0,0,.34);pointer-events:none;opacity:0;transform:translateY(4px);transition:opacity .13s,transform .13s;overflow:hidden;}'
      + '.hm-mem.on{opacity:1;transform:none;}'
      + '.hm-mem .up{color:var(--up);} .hm-mem .dn{color:var(--down);}'
      + '.hm-mem-hd{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:11px 13px 4px;}'
      + '.hm-mem-ttl{font-size:13px;font-weight:800;color:var(--text);text-transform:uppercase;letter-spacing:.03em;line-height:1.25;} .hm-mem-ttl .sub{font-weight:700;color:var(--muted);text-transform:none;letter-spacing:0;}'
      + '.hm-mem-agg{font-size:14px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap;}'
      + '.hm-mem-sub{display:flex;align-items:center;gap:8px;padding:0 13px 9px;font-size:10.5px;color:var(--muted);border-bottom:1px solid var(--line);}'
      + '.hm-mem-ct{font-weight:700;white-space:nowrap;}'
      + '.hm-mem-br{flex:1;height:6px;border-radius:3px;overflow:hidden;display:flex;background:var(--panel2);min-width:40px;} .hm-mem-br i{display:block;height:100%;} .hm-mem-br i.up{background:var(--up);} .hm-mem-br i.dn{background:var(--down);}'
      + '.hm-mem-bn{font-variant-numeric:tabular-nums;white-space:nowrap;} .hm-mem-bn b.up{color:var(--up);} .hm-mem-bn b.dn{color:var(--down);}'
      + '.hm-mem-list{padding:6px;max-height:340px;overflow:hidden;}'
      + '.hm-mem-row{display:flex;align-items:center;gap:8px;padding:3px 6px;border-radius:6px;}'
      + '.hm-mem-row:nth-child(odd){background:color-mix(in srgb,var(--text) 3.5%,transparent);}'
      + '.hm-mem-pc{font-size:10.5px;font-weight:800;font-variant-numeric:tabular-nums;padding:2px 6px;border-radius:5px;min-width:54px;text-align:center;flex:none;}'
      + '.hm-mem-t{font-size:12px;font-weight:800;color:var(--text);flex:none;min-width:42px;}'
      + '.hm-mem-n{font-size:10.5px;color:var(--muted);flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
      + '.hm-mem-cap{font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums;flex:none;}'
      + '.hm-mem-more{font-size:10.5px;color:var(--muted);text-align:center;padding:5px 0 3px;font-weight:600;}'
      // scorecard — compact, Perplexity-style stock-level treemap
      + '.hm-sc-hd{display:flex;align-items:center;gap:10px;margin-bottom:11px;}'
      + '.hm-sc-tit{display:flex;align-items:center;gap:6px;font-size:14px;font-weight:800;color:var(--text);}'
      + '.hm-sc-meta{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;}'
      + '.hm-sc-exp{margin-left:auto;font:700 12px Inter,sans-serif;color:var(--text);background:var(--panel2);border:1px solid var(--line);padding:6px 12px;border-radius:9px;cursor:pointer;transition:background .15s,border-color .15s;white-space:nowrap;}'
      + '.hm-sc-exp:hover{border-color:color-mix(in srgb,var(--link) 55%,var(--line));background:color-mix(in srgb,var(--link) 10%,var(--panel2));}'
      + '.hm-scope.hm-sc.panel{border:0;}'
      + '.hm-sc-map{position:relative;width:100%;border-radius:12px;overflow:hidden;background:var(--hm-frame);}'
      + '.hm-sc-tm{position:relative;width:100%;}'
      + '.hm-sc-sechd{box-sizing:border-box;padding:0 7px;font-size:11px;} .hm-sc-sechd .nm{font-size:10.5px;min-width:0;overflow:hidden;text-overflow:ellipsis;text-transform:none;letter-spacing:0;} .hm-sc-sechd .pc{margin-left:auto;padding-left:5px;flex:none;}'
      + '.hm-sc-foot{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-top:11px;font-size:11px;}'
      + '.hm-sc-legend{display:flex;align-items:center;gap:7px;color:var(--muted);}'
      + '.hm-sc-breadth{display:flex;align-items:center;gap:8px;color:var(--muted);}'
      + '.hm-sc-blab{text-transform:uppercase;letter-spacing:.05em;font-weight:700;font-size:10px;white-space:nowrap;}'
      + '.hm-sc-bar{width:96px;height:7px;border-radius:4px;overflow:hidden;display:flex;background:var(--panel2);} .hm-sc-bar i{display:block;height:100%;} .hm-sc-bar i.up{background:var(--up);} .hm-sc-bar i.dn{background:var(--down);}'
      + '.hm-sc-bn{font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap;} .hm-sc-bn b.up{color:var(--up);} .hm-sc-bn b.dn{color:var(--down);}'
      // overlay — a full-page takeover, not a floating dialog: the map fills the
      // viewport edge to edge (Finviz look) under a slim header strip. The body
      // normally fits without scrolling (mapHeight sizes the treemap to the
      // viewport); when it does overflow, the scrollbar is the site's thin
      // themed one, never the OS default.
      + '.hm-ov{position:fixed;inset:0;z-index:1000;display:flex;}'
      + '.hm-ov-scrim{position:absolute;inset:0;background:rgba(4,6,10,.72);opacity:0;transition:opacity .28s;}'
      + '.hm-ov.open .hm-ov-scrim{opacity:1;}'
      + '.hm-ov-panel{position:relative;width:100vw;height:100vh;height:100dvh;background:var(--bg);display:flex;flex-direction:column;overflow:hidden;opacity:0;transform:scale(.985);transition:opacity .28s,transform .28s cubic-bezier(.2,.7,.3,1);}'
      + '.hm-ov.open .hm-ov-panel{opacity:1;transform:none;}'
      + '.hm-ov-head{display:flex;align-items:center;gap:10px;padding:11px 18px;border-bottom:1px solid var(--line);flex:none;}'
      + '.hm-ov-head .t{font-size:15px;font-weight:800;color:var(--text);letter-spacing:-.01em;}'
      + '.hm-ov-x{margin-left:auto;width:32px;height:32px;border-radius:9px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font-size:14px;cursor:pointer;transition:background .15s;} .hm-ov-x:hover{background:var(--panel);}'
      + '.hm-ov-body{flex:1;overflow:auto;padding:14px 18px 16px;scrollbar-width:thin;scrollbar-color:var(--line) transparent;}'
      + '.hm-ov-body::-webkit-scrollbar{width:10px;height:10px;}'
      + '.hm-ov-body::-webkit-scrollbar-track{background:transparent;}'
      + '.hm-ov-body::-webkit-scrollbar-thumb{background:var(--line);border-radius:8px;border:2px solid transparent;background-clip:content-box;}'
      + '.hm-ov-body::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--text) 30%,var(--line));border-radius:8px;border:2px solid transparent;background-clip:content-box;}'
      // mobile
      + '.hm-mgrp{margin-bottom:14px;}'
      + '.hm-mhd{display:flex;align-items:center;gap:9px;padding:8px 11px;background:var(--panel2);border:1px solid var(--line);border-radius:10px 10px 0 0;border-bottom:0;}'
      + '.hm-mhd .nm{font-size:12.5px;font-weight:800;color:var(--text);text-transform:uppercase;letter-spacing:.03em;} .hm-mhd .pc{font-size:11.5px;font-weight:700;font-variant-numeric:tabular-nums;} .hm-mhd .pc.up{color:var(--up);} .hm-mhd .pc.dn{color:var(--down);}'
      + '.hm-mbr{margin-left:auto;width:58px;height:7px;border-radius:4px;overflow:hidden;display:flex;background:var(--panel);} .hm-mbr i{display:block;height:100%;} .hm-mbr i.up{background:var(--up);} .hm-mbr i.dn{background:var(--down);}'
      + '.hm-mrow{display:flex;align-items:center;gap:11px;padding:11px 12px;border:1px solid var(--line);border-top:0;background:var(--panel);text-decoration:none;}'
      + '.hm-mgrp .hm-mrow:last-child{border-radius:0 0 10px 10px;}'
      + '.hm-mpc{font-size:13px;font-weight:800;font-variant-numeric:tabular-nums;padding:6px 9px;border-radius:9px;min-width:66px;text-align:center;flex:none;}'
      + '.hm-mid{flex:1;min-width:0;display:flex;flex-direction:column;} .hm-mid b{font-size:14px;font-weight:800;color:var(--text);} .hm-mid span{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
      + '.hm-mgo{color:var(--muted);font-size:20px;font-weight:700;flex:none;}'
      + '.hm-mobile .hm-legend,.hm-mobile .hm-read-src,.hm-mobile .hm-hint{display:none;} .hm-mobile .hm-sort{display:flex;}'
      // reduced motion
      + '@media (prefers-reduced-motion: reduce){.hm-tile,.hm-card,.hm-mem,.hm-ov-scrim,.hm-ov-panel{transition:none !important;} .hm-c-load span{animation:none;}}'
      + '@media (max-width:560px){.hm-bar{gap:8px;} .hm-sc-foot{gap:10px;} .hm-sc-meta{font-size:10px;}}'
      // hide the scorecard Expand on small screens OR any touch device (no hover) — the deep map stays reachable via the standalone Sector Heatmap page
      + '@media (max-width:560px),(any-hover:none){.hm-sc-exp{display:none;}}';
    var st = document.createElement('style');
    st.id = 'mm-heatmap-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  /* ====================================================================== */
  /*  BOOT                                                                   */
  /* ====================================================================== */
  function _emptyHtml(msg) {
    return '<div class="hm-empty" style="padding:48px;text-align:center;color:var(--muted)">' + msg + '</div>';
  }
  // Multi-map host: a #heatmap-full carrying data-hm-maps='[{key,label_en,
  // label_zh,icon,url},...]' gets a map-type switcher and mounts one map at a
  // time (S&P 500 ⇄ Themes …). Absent the attribute the page behaves exactly as
  // before (single S&P map), so the scorecard/other surfaces are untouched.
  function mountMulti(full) {
    var maps;
    try { maps = JSON.parse(full.getAttribute('data-hm-maps') || 'null'); } catch (e) { maps = null; }
    if (!maps || !maps.length) return false;
    full.classList.add('hm-multi');
    // single-map pages (CN / HK / CA) skip the switcher bar entirely; the US page
    // (S&P 500 ⇄ Themes) keeps it.
    var bar = null;
    if (maps.length > 1) {
      bar = document.createElement('div'); bar.className = 'hm-maptype'; bar.setAttribute('role', 'tablist');
      full.appendChild(bar);
    }
    var host = document.createElement('div'); host.className = 'hm-host';
    full.appendChild(host);
    var curView = null, curKey = null, btns = {};
    function select(m) {
      if (curKey === m.key) return;
      curKey = m.key;
      Object.keys(btns).forEach(function (k) {
        var on = k === m.key;
        btns[k].classList.toggle('on', on); btns[k].setAttribute('aria-selected', on ? 'true' : 'false');
      });
      if (curView && curView.destroy) { curView.destroy(); curView = null; }
      host.innerHTML = _emptyHtml('…');
      loadData(m.url).then(function (data) {
        if (curKey !== m.key) return;                 // a newer click superseded this
        if (!data.tiles || !data.tiles.length) { host.innerHTML = _emptyHtml(L('No heatmap data available.', '暂无热力图数据。')); return; }
        host.innerHTML = '';
        curView = createFullView(host, data);
      }).catch(function (e) {
        if (curKey !== m.key) return;
        host.innerHTML = _emptyHtml(L('Could not load heatmap data.', '无法加载热力图数据。'));
        if (window.console) console.error('heatmap load failed', e);
      });
    }
    if (bar) {
      maps.forEach(function (m) {
        var b = document.createElement('button'); b.type = 'button';
        b.className = 'hm-mt'; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', 'false');
        b.innerHTML = (m.icon ? m.icon + ' ' : '') + L(m.label_en || m.key, m.label_zh || m.label_en || m.key);
        b.addEventListener('click', function () { select(m); });
        btns[m.key] = b; bar.appendChild(b);
      });
    }
    select(maps[0]);
    return true;
  }
  function boot() {
    injectStyle();
    var full = document.getElementById('heatmap-full');
    var score = document.getElementById('heatmap-scorecard');
    if (!full && !score) return;   // page doesn't use the heatmap
    if (full && full.getAttribute('data-hm-maps')) {
      mountMulti(full);
    } else if (full) {
      loadData().then(function (data) {
        if (!data.tiles || !data.tiles.length) full.innerHTML = _emptyHtml(L('No heatmap data available.', '暂无热力图数据。'));
        else createFullView(full, data);
      }).catch(function (e) {
        full.innerHTML = _emptyHtml(L('Could not load heatmap data.', '无法加载热力图数据。'));
        if (window.console) console.error('heatmap load failed', e);
      });
    }
    if (score) {
      loadData().then(function (data) {
        if (!data.tiles || !data.tiles.length) score.style.display = 'none';
        else renderScorecard(score, data);
      }).catch(function () { score.style.display = 'none'; });
    }
  }

  window.MMHeatmap = { openOverlay: openOverlay };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

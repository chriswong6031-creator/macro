/* Shared multi-timeframe indicator visuals — one renderer for sector pages and
   stock search. Modern, compact gauges + a MACD histogram sparkline with the
   cross ETA. Pure SVG, theme-aware via CSS variables. */
(function () {
  function cssv(n, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    return v || fb;
  }
  // language-aware micro-labels (re-rendered on langchange via hydrateMTF)
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  var WORDS = {
    en: { oversold: 'oversold', overbought: 'overbought', neutral: 'neutral',
          bullish: 'bullish', bearish: 'bearish',
          cu: 'just crossed up', cd: 'just crossed down',
          etaUp: 'd to ↑cross', etaDn: 'd to ↓cross',
          DAILY: 'DAILY', '3D': '3-DAY', WEEKLY: 'WEEKLY' },
    zh: { oversold: '超卖', overbought: '超买', neutral: '中性',
          bullish: '看多', bearish: '看空',
          cu: '刚上穿', cd: '刚下穿',
          etaUp: '日后上穿', etaDn: '日后下穿',
          DAILY: '日线', '3D': '3 日', WEEKLY: '周线' } };
  function L(k) { return (WORDS[lang()] || WORDS.en)[k]; }
  // small helpers
  function spark(vals, w, h, color, lo, hi) {
    if (!vals || vals.length < 2) return '';
    lo = lo == null ? Math.min.apply(null, vals) : lo;
    hi = hi == null ? Math.max.apply(null, vals) : hi;
    var rng = (hi - lo) || 1, n = vals.length;
    var pts = vals.map(function (v, i) {
      var x = (i / (n - 1)) * w;
      var y = h - ((v - lo) / rng) * h;
      return x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');
    return '<polyline points="' + pts + '" fill="none" stroke="' + color +
           '" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>';
  }

  // an oscillator gauge: zoned track (oversold / neutral / overbought) + marker,
  // with a faint sparkline of the recent path drawn above it
  function gauge(label, val, vals, kind) {
    var W = 150, H = 30, barY = 20, barH = 7;
    if (val == null) return '';
    // zone colors: low end = "washed out / opportunity" (blue), high = "hot" (amber)
    var blue = cssv('--g-cold', '#3f78d8'), amber = cssv('--g-hot', '#d8923a'),
        mid = cssv('--g-mid', '#3a4150'), txt = cssv('--text', '#d7dce3'),
        muted = cssv('--muted', '#8b93a1');
    var loZ = kind === 'stoch' ? 20 : 30, hiZ = kind === 'stoch' ? 80 : 70;
    var mark = (val / 100) * W;
    var sparkColor = val <= loZ ? blue : val >= hiZ ? amber : muted;
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" preserveAspectRatio="none" style="max-width:170px">';
    // sparkline above the bar (RSI/Stoch are 0..100 so fix scale)
    s += '<g transform="translate(0,1)">' + spark(vals, W, 11, sparkColor, 0, 100) + '</g>';
    // zoned track
    s += '<rect x="0" y="' + barY + '" width="' + (loZ / 100 * W) + '" height="' + barH + '" rx="3" fill="' + blue + '" opacity="0.30"/>';
    s += '<rect x="' + (loZ / 100 * W) + '" y="' + barY + '" width="' + ((hiZ - loZ) / 100 * W) + '" height="' + barH + '" fill="' + mid + '" opacity="0.6"/>';
    s += '<rect x="' + (hiZ / 100 * W) + '" y="' + barY + '" width="' + ((100 - hiZ) / 100 * W) + '" height="' + barH + '" rx="3" fill="' + amber + '" opacity="0.30"/>';
    // marker
    s += '<rect x="' + (mark - 1.5) + '" y="' + (barY - 2) + '" width="3" height="' + (barH + 4) + '" rx="1.5" fill="' + txt + '"/>';
    s += '</svg>';
    var zoneWord = L(val <= loZ ? 'oversold' : val >= hiZ ? 'overbought' : 'neutral');
    return '<div class="mtf-row"><span class="mtf-k">' + label + '</span>' + s +
           '<span class="mtf-v">' + Math.round(val) + '<small>' + zoneWord + '</small></span></div>';
  }

  // MACD histogram sparkline with zero baseline + bull/bear + cross ETA
  function macd(m) {
    var W = 150, H = 34;
    var h = m.spark_hist || [];
    var pos = cssv('--up', '#3fae6a'), neg = cssv('--down', '#d35454'),
        muted = cssv('--muted', '#8b93a1'), txt = cssv('--text', '#d7dce3');
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" preserveAspectRatio="none" style="max-width:170px">';
    if (h.length > 1) {
      var amp = Math.max.apply(null, h.map(Math.abs)) || 1;
      var zeroY = H / 2, n = h.length, bw = W / n;
      for (var i = 0; i < n; i++) {
        var bh = (Math.abs(h[i]) / amp) * (H / 2 - 2);
        var y = h[i] >= 0 ? zeroY - bh : zeroY;
        s += '<rect x="' + (i * bw + 0.5).toFixed(1) + '" y="' + y.toFixed(1) +
             '" width="' + (bw - 1).toFixed(1) + '" height="' + Math.max(bh, 0.6).toFixed(1) +
             '" rx="0.5" fill="' + (h[i] >= 0 ? pos : neg) + '" opacity="0.85"/>';
      }
      s += '<line x1="0" y1="' + zeroY + '" x2="' + W + '" y2="' + zeroY +
           '" stroke="' + muted + '" stroke-width="0.6" stroke-dasharray="2 2"/>';
    }
    s += '</svg>';
    var state = L(m.macd_pos ? 'bullish' : 'bearish');
    var eta = '';
    if (m.macd_cross_up) eta = L('cu');
    else if (m.macd_cross_dn) eta = L('cd');
    else if (m.macd_approaching_up && m.macd_bars_to_cross) eta = '≈' + Math.round(m.macd_days_to_cross || m.macd_bars_to_cross) + L('etaUp');
    else if (m.macd_approaching_dn && m.macd_bars_to_cross) eta = '≈' + Math.round(m.macd_days_to_cross || m.macd_bars_to_cross) + L('etaDn');
    var dot = m.macd_pos ? pos : neg;
    return '<div class="mtf-row"><span class="mtf-k">MACD</span>' + s +
           '<span class="mtf-v" style="color:' + dot + '">' + (m.macd_pos ? '▲' : '▼') +
           '<small style="color:var(--muted)">' + (eta || state) + '</small></span></div>';
  }

  function card(tfLabel, m) {
    if (!m || m.rsi14 == null) return '';
    return '<div class="mtf-card"><div class="mtf-h">' + tfLabel + '</div>' +
           gauge('RSI', m.rsi14, m.spark_rsi, 'rsi') +
           gauge('Stoch', m.stoch, m.spark_stoch, 'stoch') +
           macd(m) + '</div>';
  }

  window.renderMTF = function (el, mtf) {
    if (!el || !mtf) return;
    el.innerHTML = '<div class="mtf-grid">' +
      card(L('DAILY'), mtf.D) + card(L('3D'), mtf['3D']) + card(L('WEEKLY'), mtf.W) + '</div>';
  };
  // hydrate any server-rendered placeholders that carry data-mtf JSON
  window.hydrateMTF = function (root) {
    (root || document).querySelectorAll('[data-mtf]').forEach(function (el) {
      try { window.renderMTF(el, JSON.parse(el.getAttribute('data-mtf'))); } catch (e) {}
    });
  };
  document.addEventListener('DOMContentLoaded', function () { window.hydrateMTF(); });
})();

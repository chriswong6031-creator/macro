/* Regime "Time Machine" — a client-side scrubber over the full classified regime
   history (regime_timeline.json, written by build_site.py). Drag the playhead /
   slider across ~28 years and the readout rewinds the regime CORE to that day:
   quad, growth/inflation scores, signal agreement, liquidity, business-cycle and
   the warning flags that were firing. Sector/holdings/playbook panels are NOT in
   history, so this panel deliberately only mirrors the header's regime block.

   Self-contained, no deps. Reacts to the shared theme/lang toggles (theme.js fires
   'themechange'/'langchange'): the quad ribbon re-reads the CSS quad colours (which
   swap green/red in zh mode) and the readout re-localises. */
(function () {
  var docEl = document.documentElement;
  var root = document.getElementById('time-machine');
  if (!root) return;

  // ---- bilingual labels (en default, zh swapped to match the rest of the site) --
  var QUAD = {
    Q1: { en: 'Goldilocks',   zh: '理想增长' },
    Q2: { en: 'Reflation',    zh: '再通胀' },
    Q3: { en: 'Stagflation',  zh: '滞胀' },
    Q4: { en: 'Growth-scare', zh: '增长恐慌' }
  };
  var TRANS = {
    STABLE:        { en: 'STABLE',        zh: '稳定' },
    WEAKENING:     { en: 'WEAKENING',     zh: '走弱' },
    TRANSITIONING: { en: 'TRANSITIONING', zh: '转换中' },
    NEW_REGIME:    { en: 'NEW REGIME',    zh: '新周期' }
  };
  var LIQ = {
    expanding:   { en: 'expanding',   zh: '扩张' },
    neutral:     { en: 'neutral',     zh: '中性' },
    contracting: { en: 'contracting', zh: '收缩' },
    unknown:     { en: 'unknown',     zh: '未知' }
  };
  var CYC = {
    early:   { en: 'early', zh: '早期' },
    mid:     { en: 'mid',   zh: '中期' },
    late:    { en: 'late',  zh: '晚期' },
    unknown: { en: 'unknown', zh: '未知' }
  };
  // warning flags, in the same order as flag_order in the JSON, with the tint each
  // should carry (matches the header's transition-radar language)
  var FLAGS = [
    { key: 'breadth_price',    c: '--warn',   en: 'thinning participation',   zh: '参与度变薄',
      den: 'Price is near its highs but FEWER stocks are joining the move — the rally rests on a shrinking handful of names. A classic late-stage warning.',
      dzh: '价格接近高点，但参与上涨的股票越来越少 — 涨势由越来越少的个股支撑。典型的晚段预警。' },
    { key: 'credit_equity',    c: '--orange', en: 'nervous credit',           zh: '信用紧张',
      den: 'Stocks are still rising but corporate bonds are getting nervous (credit spreads widening). Credit usually smells trouble before equities do.',
      dzh: '股票仍在上涨，但公司债开始紧张（信用利差走阔）。信用市场通常比股市更早嗅到麻烦。' },
    { key: 'ratio_inflection', c: '--warn',   en: 'risk-ratios turning',      zh: '风险比率反转',
      den: 'The leadership ratios that define this regime (cyclicals vs defensives, high-beta vs low-vol) are starting to roll over against the regime’s bias.',
      dzh: '定义此周期的领先比率（周期股对防御股、高贝塔对低波动）开始逆周期偏好反转。' },
    { key: 'inflation_basket', c: '--orange', en: 'inflation trades turning', zh: '通胀交易反转',
      den: 'Inflation-sensitive trades (energy, metals, breakevens) are moving against what this regime assumes — the inflation story may be shifting.',
      dzh: '通胀敏感交易（能源、金属、盈亏平衡通胀）正逆此周期的假设而动 — 通胀剧本可能正在改变。' },
    { key: 'confidence_decay', c: '--warn',   en: 'signal disagreement',      zh: '信号分歧',
      den: 'The underlying indicators agree with each other LESS than before — the regime’s evidence base is weakening even if the label hasn’t flipped yet.',
      dzh: '底层指标之间的一致性正在下降 — 即使标签尚未翻转，此周期的证据基础正在减弱。' },
    { key: 'gex',              c: '--down',   en: 'fragile options',          zh: '期权脆弱',
      den: 'Dealer options positioning (gamma) has turned fragile — hedging flows now AMPLIFY moves instead of dampening them, so shocks travel further.',
      dzh: '做市商期权仓位（gamma）转为脆弱 — 对冲流现在会放大而非抑制波动，冲击传导更远。' }
  ];
  var UI = {
    today:   { en: 'live · today',     zh: '实时 · 今日' },
    history: { en: 'viewing history',  zh: '回看历史' },
    nowarn:  { en: 'no warnings',      zh: '无预警' },
    of1:     { en: 'of ±1',            zh: '／±1' }
  };

  function lang() { return docEl.getAttribute('data-lang') === 'zh' ? 'zh' : 'en'; }
  function L(o) { return o ? (o[lang()] || o.en) : ''; }
  function cssVar(n) { return getComputedStyle(docEl).getPropertyValue(n).trim(); }
  function quadColor(q) { return cssVar('--' + (q || '').toLowerCase()) || '#888'; }
  // a warning chip with a hover definition (custom .tm-tip popover + native
  // title= as a universal fallback). def is plain text; escape for both sinks.
  function flagChip(cvar, label, def) {
    var esc = String(def || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var attr = esc.replace(/"/g, '&quot;');
    return '<span class="tm-flag" tabindex="0" style="--c:var(' + cvar + ')" title="' + attr +
      '">' + label + '<span class="tm-tip">' + esc + '</span></span>';
  }

  // ---- DOM refs --------------------------------------------------------------
  var canvas = document.getElementById('tm-canvas');
  var range  = document.getElementById('tm-range');
  var elDate = document.getElementById('tm-date');
  var elTag  = document.getElementById('tm-tag');
  var elQuad = document.getElementById('tm-quad');
  var elTr   = document.getElementById('tm-trans');
  var elConf = document.getElementById('tm-conf');
  var elCyc  = document.getElementById('tm-cyc');
  var elLiq  = document.getElementById('tm-liq');
  var elGi   = document.getElementById('tm-g-i');
  var elGv   = document.getElementById('tm-g-v');
  var elIi   = document.getElementById('tm-i-i');
  var elIv   = document.getElementById('tm-i-v');
  var elFlags = document.getElementById('tm-flags');
  var playBtn = document.getElementById('tm-play');
  var ctx = canvas ? canvas.getContext('2d') : null;

  var D = null;        // the loaded timeline
  var N = 0;
  var idx = 0;
  var playing = null;  // interval handle

  // ---- load ------------------------------------------------------------------
  // china (and any other market) can point at its own timeline via data-timeline;
  // the macro page omits it and keeps the original filename.
  fetch(root.getAttribute('data-timeline') || 'regime_timeline.json').then(function (r) {
    if (!r.ok) throw new Error('no timeline');
    return r.json();
  }).then(function (j) {
    D = j; N = j.dates.length;
    if (!N) { root.style.display = 'none'; return; }
    idx = N - 1;
    range.min = 0; range.max = N - 1; range.value = idx;
    wire();
    paint();
    render();
  }).catch(function () { root.style.display = 'none'; });

  // ---- canvas: quad ribbon + year ticks + playhead ---------------------------
  function paint() {
    if (!ctx || !N) return;
    var dpr = window.devicePixelRatio || 1;
    var W = canvas.clientWidth || canvas.parentNode.clientWidth || 600;
    var H = 56;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    var bandH = 38;
    // contiguous quad runs → one rect each (seam-free, cheap)
    var i = 0;
    while (i < N) {
      var q = D.quad[i], j = i;
      while (j + 1 < N && D.quad[j + 1] === q) j++;
      var x0 = i / (N - 1) * W, x1 = j / (N - 1) * W;
      ctx.fillStyle = quadColor(q);
      ctx.fillRect(Math.floor(x0), 0, Math.ceil(x1 - x0) + 1, bandH);
      i = j + 1;
    }

    // year ticks under the ribbon (skip labels that would crowd)
    ctx.font = '10px Inter, system-ui, sans-serif';
    ctx.textBaseline = 'top';
    var tickCol = cssVar('--muted') || '#888';
    var lastLabelX = -1e9, prevYear = null;
    for (var k = 0; k < N; k++) {
      var yr = D.dates[k].slice(0, 4);
      if (yr !== prevYear) {
        prevYear = yr;
        var x = k / (N - 1) * W;
        ctx.strokeStyle = 'rgba(128,128,128,0.22)';
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, bandH); ctx.stroke();
        if (x - lastLabelX > 48) {
          ctx.fillStyle = tickCol;
          ctx.fillText(yr, Math.min(x + 2, W - 26), bandH + 4);
          lastLabelX = x;
        }
      }
    }

    // playhead
    var px = idx / (N - 1) * W;
    px = Math.max(1, Math.min(W - 1, px));
    ctx.strokeStyle = cssVar('--text') || '#fff';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, bandH); ctx.stroke();
    ctx.fillStyle = cssVar('--text') || '#fff';
    ctx.beginPath();
    ctx.moveTo(px - 5, 0); ctx.lineTo(px + 5, 0); ctx.lineTo(px, 7); ctx.closePath();
    ctx.fill();
  }

  // ---- readout ---------------------------------------------------------------
  function badge(el, cls, text) { el.className = 'badge ' + cls; el.textContent = text; }

  function render() {
    if (!D) return;
    var q = D.quad[idx];
    elDate.textContent = D.dates[idx];
    var live = idx === N - 1;
    elTag.textContent = L(live ? UI.today : UI.history);
    elTag.className = 'tm-state-tag ' + (live ? 'is-live' : 'is-hist');

    badge(elQuad, 'quad-' + q, L(QUAD[q]) || q);
    badge(elTr, 'state-' + D.trans[idx], L(TRANS[D.trans[idx]]) || D.trans[idx]);
    elConf.textContent = Math.round((D.conf[idx] || 0) * 100) + '%';
    elCyc.textContent = L(CYC[D.cyc[idx]]) || D.cyc[idx];
    elLiq.textContent = L(LIQ[D.liq[idx]]) || D.liq[idx];

    var g = D.g[idx], inf = D.i[idx];
    elGi.style.left = clampPct(g) + '%';
    elGv.textContent = (g >= 0 ? '+' : '') + (g == null ? '—' : g.toFixed(2)) + ' ' + L(UI.of1);
    elIi.style.left = clampPct(inf) + '%';
    elIv.textContent = (inf >= 0 ? '+' : '') + (inf == null ? '—' : inf.toFixed(2)) + ' ' + L(UI.of1);

    // warning flags firing on this day (decode the bitmask). Each chip carries a
    // hover definition so the labels explain themselves (custom tip + title fallback).
    var mask = D.flags[idx] || 0, chips = '';
    for (var b = 0; b < FLAGS.length; b++) {
      if (mask & (1 << b)) {
        chips += flagChip(FLAGS[b].c, L(FLAGS[b]),
          (lang() === 'zh' ? FLAGS[b].dzh : FLAGS[b].den));
      }
    }
    if (D.rec[idx]) chips = flagChip('--down', lang() === 'zh' ? '衰退确认' : 'recession',
      lang() === 'zh' ? '该日已正式确认处于美国经济衰退（NBER）。'
        : 'This day was inside an officially-dated US recession (NBER).') + chips;
    if (D.shock[idx]) chips = flagChip('--orange', lang() === 'zh' ? '通胀冲击' : 'inflation shock',
      lang() === 'zh' ? '通胀数据出现极端单日意外，足以单独推动周期标签。'
        : 'An extreme one-day inflation surprise — large enough to move the regime label on its own.') + chips;
    elFlags.innerHTML = chips || '<span class="tm-nowarn">⚪ ' + L(UI.nowarn) + '</span>';
  }

  function clampPct(v) {
    if (v == null) return 50;
    return Math.max(0, Math.min(100, (v + 1) / 2 * 100));
  }

  // ---- navigation ------------------------------------------------------------
  function setIndex(i, fromRange) {
    idx = Math.max(0, Math.min(N - 1, Math.round(i)));
    if (!fromRange) range.value = idx;
    paint(); render();
  }
  function idxFromClientX(clientX) {
    var rct = canvas.getBoundingClientRect();
    var t = (clientX - rct.left) / rct.width;
    return t * (N - 1);
  }
  function nearest(target) {
    // dates are ISO + sorted, so lexical compare works; find closest
    var lo = 0, hi = N - 1;
    if (target >= D.dates[hi]) return hi;
    if (target <= D.dates[lo]) return lo;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (D.dates[mid] < target) lo = mid + 1; else hi = mid;
    }
    if (lo > 0 && (target - D.dates[lo - 1]) < (D.dates[lo] - target)) return lo - 1;
    return lo;
  }

  function stopPlay() {
    if (playing) { clearInterval(playing); playing = null; }
    if (playBtn) playBtn.classList.remove('is-playing');
  }
  function togglePlay() {
    if (playing) { stopPlay(); return; }
    if (idx >= N - 1) setIndex(0);           // restart from the beginning
    var stride = Math.max(1, Math.round(N / 220));
    playBtn.classList.add('is-playing');
    playing = setInterval(function () {
      if (idx >= N - 1) { setIndex(N - 1); stopPlay(); return; }
      setIndex(idx + stride);
    }, 40);
  }

  function wire() {
    range.addEventListener('input', function () { stopPlay(); setIndex(+range.value, true); });

    var dragging = false;
    canvas.addEventListener('pointerdown', function (e) {
      dragging = true; stopPlay(); canvas.setPointerCapture(e.pointerId);
      setIndex(idxFromClientX(e.clientX));
    });
    canvas.addEventListener('pointermove', function (e) {
      if (dragging) setIndex(idxFromClientX(e.clientX));
    });
    canvas.addEventListener('pointerup', function () { dragging = false; });
    canvas.addEventListener('pointercancel', function () { dragging = false; });

    if (playBtn) playBtn.addEventListener('click', togglePlay);

    root.querySelectorAll('[data-tm-jump]').forEach(function (b) {
      b.addEventListener('click', function () {
        stopPlay();
        var t = b.getAttribute('data-tm-jump');
        setIndex(t === 'now' ? N - 1 : nearest(t));
      });
    });

    // shared toggles: quad colours + labels change → repaint + re-localise
    document.addEventListener('themechange', function () { paint(); render(); });
    document.addEventListener('langchange', function () { paint(); render(); });
    window.addEventListener('resize', paint);
  }
})();

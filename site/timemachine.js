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
    { key: 'breadth_price',    c: '--warn',   en: 'thinning participation',   zh: '参与度变薄' },
    { key: 'credit_equity',    c: '--orange', en: 'nervous credit',           zh: '信用紧张' },
    { key: 'ratio_inflection', c: '--warn',   en: 'risk-ratios turning',      zh: '风险比率反转' },
    { key: 'inflation_basket', c: '--orange', en: 'inflation trades turning', zh: '通胀交易反转' },
    { key: 'confidence_decay', c: '--warn',   en: 'signal disagreement',      zh: '信号分歧' },
    { key: 'gex',              c: '--down',   en: 'fragile options',          zh: '期权脆弱' }
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
  fetch('regime_timeline.json').then(function (r) {
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

    // warning flags firing on this day (decode the bitmask)
    var mask = D.flags[idx] || 0, chips = '';
    for (var b = 0; b < FLAGS.length; b++) {
      if (mask & (1 << b)) {
        chips += '<span class="tm-flag" style="--c:var(' + FLAGS[b].c + ')">' + L(FLAGS[b]) + '</span>';
      }
    }
    if (D.rec[idx]) chips = '<span class="tm-flag" style="--c:var(--down)">' +
      (lang() === 'zh' ? '衰退确认' : 'recession') + '</span>' + chips;
    if (D.shock[idx]) chips = '<span class="tm-flag" style="--c:var(--orange)">' +
      (lang() === 'zh' ? '通胀冲击' : 'inflation shock') + '</span>' + chips;
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

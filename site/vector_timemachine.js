/* Bitcoin Vector "Cycle Time Machine" — a client-side scrubber over the full
   point-in-time signal history (vector_timeline.json, written by build_vector.py).
   Drag the playhead / slider across ~11 years and the readout rewinds the whole
   dashboard CORE to that day: cycle phase + stage, the ladder state and regime
   (backtested with no look-ahead), risk index, momentum, valuation, market extreme,
   composite stance, price and the model's BTC allocation. Many pieces move at once.

   Self-contained, no deps. The ribbon colours the 4 halving-cycle phases. Re-reads
   on theme/lang change (custom events OR an attribute observer, so it works on the
   Vector page regardless of how the toggles are wired). */
(function () {
  var docEl = document.documentElement;
  var root = document.getElementById('vtm');
  if (!root) return;

  // ---- fixed semantic ribbon palette (consistent across light/dark) ----------
  var PHASE = {
    accumulation: { c: '#3b6fe0', en: 'Accumulation', zh: '吸筹' },
    markup:       { c: '#1f9d57', en: 'Markup',       zh: '拉升' },
    recovery:     { c: '#e0a43a', en: 'Recovery',     zh: '修复' },
    markdown:     { c: '#cf4f4f', en: 'Markdown',     zh: '派发下行' }
  };
  var STAGE = [
    { en: 'Defensive', zh: '防御' }, { en: 'Fragile', zh: '脆弱' },
    { en: 'Recovery', zh: '修复' }, { en: 'Expansion', zh: '扩张' }
  ];
  var REGIME = {
    bull:    { c: 'var(--blue)',  en: 'Bull',    zh: '牛市' },
    neutral: { c: 'var(--muted)', en: 'Neutral', zh: '中性' },
    bear:    { c: 'var(--r3)',    en: 'Bear',    zh: '熊市' }
  };
  var MOM = {
    bull: { en: 'Bull', zh: '看多' }, bear: { en: 'Bear', zh: '看空' },
    neutral: { en: 'Neutral', zh: '中性' }
  };
  var VAL = {
    undervalued: { en: 'Undervalued', zh: '低估' }, fair: { en: 'Fair value', zh: '合理' },
    overvalued: { en: 'Overvalued', zh: '高估' }
  };
  var EXTREME = {
    normal: { en: '', zh: '' },
    capitulation: { c: 'var(--blue)', en: 'Capitulation', zh: '投降抛售' },
    euphoria: { c: 'var(--amber)', en: 'Euphoria', zh: '亢奋' }
  };
  var COMP = {
    'ACCUMULATE': { en: 'Accumulate', zh: '累积' }, 'RISK-ON': { en: 'Risk-on', zh: '风险偏好' },
    'NEUTRAL': { en: 'Neutral', zh: '中性' }, 'DISTRIBUTE': { en: 'Distribute', zh: '派发' },
    'RISK-OFF': { en: 'Risk-off', zh: '风险规避' }
  };
  // ladder states (engine.cycles) — map the common ones; fall back to the raw label
  var LADDER = {
    'FRESH BUY': { en: 'Fresh buy', zh: '新买点' }, 'TURN SIGNALED': { en: 'Turn signaled', zh: '转向信号' },
    'RALLY ON': { en: 'Rally on', zh: '上涨中' }, 'TOP WATCH': { en: 'Top watch', zh: '顶部观察' },
    'ROLLING OVER': { en: 'Rolling over', zh: '见顶回落' }, 'DECLINE': { en: 'Decline', zh: '下跌' },
    'BOTTOM WATCH': { en: 'Bottom watch', zh: '底部观察' },
    'COUNTERTREND BOUNCE': { en: 'Counter-trend bounce', zh: '逆势反弹' }
  };
  // bottom-anchored 1064/364 cycle phase (the chart's theory) — 2 states only
  var CPHASE = {
    markup: { en: 'Markup (1064d)', zh: '上涨腿 (1064天)' },
    markdown: { en: 'Markdown (364d)', zh: '下跌腿 (364天)' }
  };
  var UI = {
    today: { en: 'live · today', zh: '实时 · 今日' },
    history: { en: 'viewing history', zh: '回看历史' }
  };

  function lang() { return docEl.getAttribute('data-lang') === 'zh' ? 'zh' : 'en'; }
  function L(o) { return o ? (o[lang()] != null ? o[lang()] : o.en) : ''; }
  function cssVar(n) { return getComputedStyle(docEl).getPropertyValue(n).trim(); }

  // ---- DOM refs --------------------------------------------------------------
  var canvas = document.getElementById('vtm-canvas');
  var range  = document.getElementById('vtm-range');
  var el = function (id) { return document.getElementById(id); };
  var elDate = el('vtm-date'), elTag = el('vtm-tag'), elPhase = el('vtm-phase'),
      elCphase = el('vtm-cphase'),
      elStage = el('vtm-stage'), elRegime = el('vtm-regime'), elLadder = el('vtm-ladder'),
      elMom = el('vtm-mom'), elVal = el('vtm-val'), elExtreme = el('vtm-extreme'),
      elComp = el('vtm-composite'), elRiskI = el('vtm-risk-i'), elRiskV = el('vtm-risk-v'),
      elPrice = el('vtm-price'), elAlloc = el('vtm-alloc');
  var playBtn = el('vtm-play');
  var ctx = canvas ? canvas.getContext('2d') : null;

  var D = null, N = 0, idx = 0, playing = null;

  fetch(root.getAttribute('data-timeline') || 'vector_timeline.json').then(function (r) {
    if (!r.ok) throw new Error('no timeline');
    return r.json();
  }).then(function (j) {
    D = j; N = j.dates.length;
    if (!N) { root.style.display = 'none'; return; }
    idx = N - 1;
    range.min = 0; range.max = N - 1; range.value = idx;
    wire(); paint(); render();
  }).catch(function () { root.style.display = 'none'; });

  // ---- canvas: phase ribbon + year ticks + playhead --------------------------
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
    var i = 0;
    while (i < N) {
      var p = D.phase[i], j = i;
      while (j + 1 < N && D.phase[j + 1] === p) j++;
      var x0 = i / (N - 1) * W, x1 = j / (N - 1) * W;
      ctx.fillStyle = (PHASE[p] && PHASE[p].c) || '#888';
      ctx.fillRect(Math.floor(x0), 0, Math.ceil(x1 - x0) + 1, bandH);
      i = j + 1;
    }

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

    var px = idx / (N - 1) * W;
    px = Math.max(1, Math.min(W - 1, px));
    ctx.strokeStyle = cssVar('--ink') || '#111';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, bandH); ctx.stroke();
    ctx.fillStyle = cssVar('--ink') || '#111';
    ctx.beginPath();
    ctx.moveTo(px - 5, 0); ctx.lineTo(px + 5, 0); ctx.lineTo(px, 7); ctx.closePath();
    ctx.fill();
  }

  // ---- readout ---------------------------------------------------------------
  function tag(elm, color, text) {
    elm.textContent = text;
    elm.style.background = color ? 'color-mix(in srgb,' + color + ' 16%, transparent)' : 'transparent';
    elm.style.color = color || 'var(--muted)';
  }
  function money(v) {
    if (v == null) return '—';
    return '$' + Math.round(v).toLocaleString('en-US');
  }

  function render() {
    if (!D) return;
    var live = idx === N - 1;
    elDate.textContent = D.dates[idx];
    elTag.textContent = L(live ? UI.today : UI.history);
    elTag.className = 'vtm-tag ' + (live ? 'is-live' : 'is-hist');

    var ph = PHASE[D.phase[idx]];
    tag(elPhase, ph && ph.c, L(ph) || D.phase[idx]);
    elStage.textContent = L(STAGE[D.stage[idx]]) || '—';
    if (elCphase) elCphase.textContent = L(CPHASE[D.cphase && D.cphase[idx]]) || '—';
    var rg = REGIME[D.regime[idx]];
    tag(elRegime, rg && rg.c, L(rg) || D.regime[idx] || '—');
    elLadder.textContent = L(LADDER[D.ladder[idx]]) || D.ladder[idx] || '—';

    elMom.textContent = L(MOM[D.mom[idx]]) || D.mom[idx] || '—';
    elVal.textContent = L(VAL[D.val[idx]]) || D.val[idx] || '—';
    elComp.textContent = L(COMP[D.composite[idx]]) || D.composite[idx] || '—';

    var ex = EXTREME[D.extreme[idx]];
    if (ex && ex.c) { elExtreme.style.display = ''; tag(elExtreme, ex.c, L(ex)); }
    else { elExtreme.style.display = 'none'; }

    var ri = D.risk[idx];
    if (elRiskI) elRiskI.style.left = Math.max(0, Math.min(100, ri == null ? 50 : ri)) + '%';
    if (elRiskV) elRiskV.textContent = (ri == null ? '—' : Math.round(ri));
    elPrice.textContent = money(D.price[idx]);
    if (elAlloc) elAlloc.textContent = (D.alloc[idx] == null ? '—' : D.alloc[idx] + '% BTC');
  }

  // ---- navigation ------------------------------------------------------------
  function setIndex(i, fromRange) {
    idx = Math.max(0, Math.min(N - 1, Math.round(i)));
    if (!fromRange) range.value = idx;
    paint(); render();
  }
  function idxFromClientX(clientX) {
    var rct = canvas.getBoundingClientRect();
    return ((clientX - rct.left) / rct.width) * (N - 1);
  }
  function nearest(target) {
    var lo = 0, hi = N - 1;
    if (target >= D.dates[hi]) return hi;
    if (target <= D.dates[lo]) return lo;
    while (lo < hi) { var mid = (lo + hi) >> 1; if (D.dates[mid] < target) lo = mid + 1; else hi = mid; }
    if (lo > 0 && (target - D.dates[lo - 1]) < (D.dates[lo] - target)) return lo - 1;
    return lo;
  }

  function stopPlay() {
    if (playing) { clearInterval(playing); playing = null; }
    if (playBtn) playBtn.classList.remove('is-playing');
  }
  function togglePlay() {
    if (playing) { stopPlay(); return; }
    if (idx >= N - 1) setIndex(0);
    var stride = Math.max(1, Math.round(N / 240));
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
    canvas.addEventListener('pointermove', function (e) { if (dragging) setIndex(idxFromClientX(e.clientX)); });
    canvas.addEventListener('pointerup', function () { dragging = false; });
    canvas.addEventListener('pointercancel', function () { dragging = false; });
    if (playBtn) playBtn.addEventListener('click', togglePlay);
    root.querySelectorAll('[data-vtm-jump]').forEach(function (b) {
      b.addEventListener('click', function () {
        stopPlay();
        var t = b.getAttribute('data-vtm-jump');
        setIndex(t === 'now' ? N - 1 : nearest(t));
      });
    });
    document.addEventListener('themechange', function () { paint(); render(); });
    document.addEventListener('langchange', function () { paint(); render(); });
    window.addEventListener('resize', paint);
    // robust fallback: re-render when data-lang / data-theme flip on <html>
    new MutationObserver(function () { paint(); render(); })
      .observe(docEl, { attributes: true, attributeFilter: ['data-lang', 'data-theme'] });
  }
})();

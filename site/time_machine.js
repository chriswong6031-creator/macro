/* time_machine.js — the Rotation Time Machine.
 *
 * Extracted from the retired subsector_rotation.html.j2 (#tm-section markup + its
 * inline engine) for the merged sector_central.html (Sector Intelligence
 * consolidation, masterplan §6.2b: "Time Machine → EXPLORE, collapsed + lazy").
 *
 * SVG rendering via the shared window.SRR renderer exported by subsector_rotation.js
 * (which MUST load first), year-based lazy chunk loading, incremental trail buffers
 * (O(nodes) per frame), stable per-(unit,year) domain, keyboard navigation,
 * bilingual. No new JS dependencies.
 *
 * LAZY: the module mounts only a <details> shell at load. The markup build, the
 * manifest/episode fetches and every frame render happen on FIRST details-open —
 * nothing is fetched and no map DOM is built until the user asks for it.
 *
 * No predictive claim — this replays measured history.
 */
(function () {
  'use strict';

  var BASE = 'oracledata/';
  var MANI = BASE + 'tm_manifest.json';
  var EP   = BASE + 'tm_episodes.json';

  /* ── state ── */
  var _inited    = false;
  var _built     = false;
  var _manifest  = null;
  var _epFeed    = null;
  var _unit      = 'sectors';   // 'sectors' | 'subsectors' | 'themes' | 'factors'
  var _year      = null;        // currently selected year string e.g. '2024'
  // Per-unit/year derived data
  var _registry  = [];          // filtered registry for current unit
  var _chunkMeta = [];          // manifest chunk list for current tier
  var _chunks    = {};          // cache: key -> chunk data; global across year switches
  var _yearDates = [];          // all dates for the selected year (plus prev-chunk boundary)
  var _yearChunkKeys = [];      // chunk keys needed for selected year (+ prev boundary)
  var _pos       = 0;           // index into _yearDates
  var _playing   = false;
  var _playTimer = null;
  // Per-node trail buffer: _trailBuf[nodeId] = [[rs,az], ...] last 6 frames
  var _trailBuf  = {};
  var TRAIL_LEN  = 6;   // short, readable path (was 15 — too long to trace)
  // Stable domain for the current (unit, year) combination
  var _domain    = null;        // {xMin,xMax,yMin,yMax} or null (auto first frame)
  var _domainSet = false;
  // Tooltip for TM map
  var _tmTip     = null;
  // Section focus tracking for keyboard
  var _tmHasFocus = false;

  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function isZh(){return document.documentElement.getAttribute('data-lang')==='zh';}
  function L(en,zh){return '<span class="l-en">'+en+'</span><span class="l-zh">'+(zh==null?en:zh)+'</span>';}

  /* ── styles (injected once, guarded by element id — subsector_rotation.js model).
     .tm-* / .sr-tip-score* carried over from the retired page's head <style>;
     .tm-details / summary is new chrome for the collapsed-by-default wrapper. ── */
  function injectStyle(){
    if(document.getElementById('time-machine-style')) return;
    var c=''
      /* ── collapsed wrapper ── */
      +'.tm-details { margin:22px 2px 0; border:1px solid var(--line); border-radius:14px;'
      +'  background:var(--panel); overflow:hidden; }'
      +'.tm-details > summary { list-style:none; cursor:pointer; padding:12px 15px;'
      +'  font-size:14px; font-weight:800; letter-spacing:-.01em; color:var(--text);'
      +'  display:flex; align-items:center; gap:8px; user-select:none;'
      +'  transition:background .14s; }'
      +'.tm-details > summary::-webkit-details-marker { display:none; }'
      +'.tm-details > summary::after { content:"▾"; margin-left:auto; font-size:11px; color:var(--muted);'
      +'  transition:transform .16s; }'
      +'.tm-details[open] > summary::after { transform:rotate(180deg); }'
      +'.tm-details > summary:hover { background:var(--panel2); }'
      +'.tm-details > summary:focus-visible { outline:2px solid var(--link); outline-offset:-2px; }'
      +'.tm-details .tm-body { padding:0 15px 15px; }'
      /* ── Time Machine ── */
      +'.tm-section { margin:0; }'
      +'.tm-sub { color:var(--muted); font-size:12.5px; margin:0 0 16px; max-width:82ch; line-height:1.55; }'
      +'.oracle-shock-note { margin:8px 0 0; padding:8px 12px; border-radius:8px;'
      +'  background:color-mix(in srgb, var(--warn) 10%, var(--panel2));'
      +'  border-left:3px solid var(--warn); font-size:12px; color:var(--muted); }'
      /* Unit toggle — segmented control */
      +'.tm-unit-row { margin-bottom:11px; }'
      +'.tm-tier-btns { display:inline-flex; gap:3px; background:var(--panel2); border:1px solid var(--line); border-radius:11px; padding:3px; }'
      +'.tm-tier-btn { padding:5px 13px; border-radius:8px; border:1px solid transparent; background:transparent;'
      +'  color:var(--muted); font:inherit; font-size:12px; font-weight:600; cursor:pointer; white-space:nowrap;'
      +'  transition:background .16s,color .16s,box-shadow .16s; }'
      +'.tm-tier-btn:hover { color:var(--text); }'
      +'.tm-tier-btn.active { background:var(--panel); color:var(--text); box-shadow:0 1px 3px rgba(0,0,0,.18); }'
      /* Year chip row */
      +'.tm-year-row { margin-bottom:12px; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:thin; }'
      +'.tm-year-chips { display:flex; gap:4px; padding-bottom:3px; min-width:max-content; }'
      +'.tm-year-chip { padding:3px 11px; border-radius:8px; border:1px solid var(--line); background:transparent;'
      +'  color:var(--muted); font:inherit; font-size:11.5px; font-variant-numeric:tabular-nums; cursor:pointer; white-space:nowrap;'
      +'  transition:background .12s,color .12s,border-color .12s; }'
      +'.tm-year-chip:hover { background:var(--panel2); color:var(--text); border-color:color-mix(in srgb,var(--text) 20%,var(--line)); }'
      +'.tm-year-chip.active { background:var(--link); color:#fff; border-color:var(--link); box-shadow:0 2px 8px color-mix(in srgb,var(--link) 38%,transparent); }'
      +'.tm-year-now { font-style:italic; }'
      /* Playback controls — a compact media bar */
      +'.tm-controls { display:flex; flex-wrap:wrap; align-items:center; gap:10px 12px; margin-bottom:10px;'
      +'  padding:7px 11px; background:var(--panel2); border:1px solid var(--line); border-radius:12px; }'
      +'.tm-play-btn { width:34px; height:34px; border-radius:50%; border:none; background:var(--link);'
      +'  color:#fff; font:inherit; font-size:14px; cursor:pointer; display:flex; align-items:center; justify-content:center;'
      +'  box-shadow:0 2px 10px color-mix(in srgb,var(--link) 45%,transparent); transition:transform .12s,filter .16s; }'
      +'.tm-play-btn:hover { transform:scale(1.08); filter:brightness(1.07); }'
      +'.tm-play-btn:active { transform:scale(.95); }'
      +'.tm-speed-sel { background:var(--panel); color:var(--text); border:1px solid var(--line); border-radius:8px;'
      +'  padding:5px 26px 5px 10px; font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-appearance:none; appearance:none;'
      +'  background-image:linear-gradient(45deg,transparent 50%,var(--muted) 50%),linear-gradient(135deg,var(--muted) 50%,transparent 50%);'
      +'  background-position:calc(100% - 14px) 52%,calc(100% - 9px) 52%; background-size:5px 5px,5px 5px; background-repeat:no-repeat; }'
      +'.tm-speed-sel:hover { border-color:color-mix(in srgb,var(--text) 24%,var(--line)); }'
      +'.tm-date-lbl { font-size:14px; font-weight:700; min-width:96px; font-variant-numeric:tabular-nums; letter-spacing:.01em; color:var(--text); }'
      +'.tm-kb-hint { font-size:10.5px; color:var(--muted); margin-left:auto; }'
      +'.tm-slider-wrap { width:100%; margin:2px 0 10px; }'
      +'.tm-slider { width:100%; height:20px; -webkit-appearance:none; appearance:none; background:transparent; cursor:pointer; }'
      +'.tm-slider::-webkit-slider-runnable-track { height:5px; border-radius:3px; background:var(--panel2); border:1px solid var(--line); }'
      +'.tm-slider::-moz-range-track { height:5px; border-radius:3px; background:var(--panel2); border:1px solid var(--line); }'
      +'.tm-slider::-webkit-slider-thumb { -webkit-appearance:none; appearance:none; width:16px; height:16px; margin-top:-6.5px; border-radius:50%;'
      +'  background:var(--link); border:2px solid var(--panel); box-shadow:0 1px 5px rgba(0,0,0,.3); transition:transform .1s; }'
      +'.tm-slider::-moz-range-thumb { width:16px; height:16px; border-radius:50%; background:var(--link); border:2px solid var(--panel); box-shadow:0 1px 5px rgba(0,0,0,.3); }'
      +'.tm-slider:hover::-webkit-slider-thumb { transform:scale(1.14); }'
      +'.tm-slider:focus-visible { outline:none; }'
      +'.tm-slider:focus-visible::-webkit-slider-thumb { box-shadow:0 0 0 4px color-mix(in srgb,var(--link) 35%,transparent); }'
      /* Map + episodes layout */
      +'.tm-scatter-wrap { display:flex; flex-wrap:wrap; gap:14px; }'
      +'.tm-map-box { flex:1 1 360px; min-width:280px; min-height:300px; position:relative;'
      +'  border-radius:16px; border:1px solid var(--line); overflow:hidden;'
      +'  background:radial-gradient(120% 120% at 50% 0%, color-mix(in srgb,var(--text) 4%,var(--panel)) 0%, var(--panel) 62%);'
      +'  box-shadow:inset 0 1px 0 color-mix(in srgb,var(--text) 8%,transparent), 0 4px 18px rgba(0,0,0,.10); }'
      +'.tm-map-box .sr-map { border-radius:0; border:none; }'
      +'.tm-episodes-panel { flex:0 0 244px; min-width:220px; max-height:440px; overflow-y:auto; scrollbar-width:thin;'
      +'  border-radius:14px; border:1px solid var(--line); background:var(--panel); padding:12px; }'
      +'.tm-ep-hd { font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:.07em;'
      +'  color:var(--muted); margin:0 0 9px; }'
      +'.tm-ep-item { margin-bottom:7px; padding:8px 11px; border-radius:9px; background:var(--panel2);'
      +'  border:1px solid var(--line); font-size:12px; line-height:1.5; transition:border-color .12s; }'
      +'.tm-ep-item:hover { border-color:color-mix(in srgb,var(--text) 18%,var(--line)); }'
      +'.tm-ep-dir-in  { border-left:3px solid var(--up); }'
      +'.tm-ep-dir-out { border-left:3px solid var(--down); }'
      +'.tm-ep-node { font-weight:700; }'
      +'.tm-ep-badge { display:inline-block; font-size:9.5px; font-weight:700; text-transform:uppercase;'
      +'  padding:1px 6px; border-radius:5px; margin-left:4px; vertical-align:middle; letter-spacing:.03em;'
      +'  background:color-mix(in srgb, var(--muted) 15%, transparent); color:var(--muted); }'
      +'.tm-ep-badge.onset     { background:color-mix(in srgb, var(--warn) 18%, transparent); color:var(--warn); }'
      +'.tm-ep-badge.confirmed { background:color-mix(in srgb, var(--up) 18%, transparent); color:var(--up); }'
      +'.tm-ep-badge.undeniable{ background:color-mix(in srgb, var(--up) 30%, transparent); color:var(--up); }'
      +'.tm-ep-pair { font-size:11px; color:var(--muted); margin-top:2px; }'
      +'.tm-ep-empty { color:var(--muted); font-size:12px; }'
      +'.tm-presets { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:14px; align-items:center; }'
      +'.tm-preset-btn { padding:5px 12px; border-radius:9px; border:1px solid var(--line); background:var(--panel);'
      +'  color:var(--muted); font:inherit; font-size:11.5px; font-weight:600; cursor:pointer; transition:background .15s,color .15s,border-color .15s; }'
      +'.tm-preset-btn:hover { background:var(--panel2); color:var(--text); border-color:color-mix(in srgb,var(--link) 45%,var(--line)); }'
      +'.tm-watermark { font-size:11px; color:var(--muted); margin-top:8px; margin-bottom:4px; }'
      +'.tm-loading { color:var(--muted); font-size:13px; padding:40px 0; text-align:center; }'
      /* Strength gauge (shown in the hover tooltip) */
      +'.sr-tip-score { margin-top:8px; padding-top:8px; border-top:1px solid var(--line); }'
      +'.sr-tip-score-hd { display:flex; align-items:baseline; gap:5px; font-size:10.5px; color:var(--muted);'
      +'  text-transform:uppercase; letter-spacing:.05em; font-weight:700; }'
      +'.sr-tip-score-hd b { margin-left:auto; font-size:15px; color:var(--text); font-variant-numeric:tabular-nums; }'
      +'.sr-tip-score-hd i { font-style:normal; font-size:10px; color:var(--muted); }'
      +'.sr-tip-gauge { margin-top:4px; height:6px; border-radius:4px; background:var(--panel2); border:1px solid var(--line); overflow:hidden; }'
      +'.sr-tip-gauge span { display:block; height:100%; border-radius:4px; transition:width .2s; }'
      +'.sr-tip-cap { margin-top:5px; font-size:9.5px; color:var(--muted); font-style:italic; }'
      +'@media (max-width:520px) {'
      +'  .tm-scatter-wrap { flex-direction:column; }'
      +'  .tm-episodes-panel { max-height:220px; flex:none; width:100%; }'
      +'  .tm-map-box { min-height:240px; }'
      +'  .tm-kb-hint { display:none; }'
      +'}';
    var s=document.createElement('style');
    s.id='time-machine-style';
    s.textContent=c;
    document.head.appendChild(s);
  }

  /* ── mount: the collapsed shell only — no fetching, no map DOM until opened ── */
  function mount(){
    var host=document.getElementById('tm-mount');
    if(!host) return null;
    var d=document.getElementById('tm-details');
    if(d) return d;
    host.innerHTML=''
      +'<details class="tm-details" id="tm-details">'
      +'<summary>⏱ '+L('Rotation Time Machine — replay 25 years of rotation','轮动时光机 — 回放25年轮动史')+'</summary>'
      +'<div class="tm-body" id="tm-body"></div>'
      +'</details>';
    return document.getElementById('tm-details');
  }

  /* ── the heavy markup — built on FIRST open only ── */
  function buildBody(){
    if(_built) return;
    var body=document.getElementById('tm-body');
    if(!body) return;
    _built=true;
    body.innerHTML=''
      +'<section class="tm-section" id="tm-section" aria-label="Time Machine">'
      +'<p class="tm-sub">'+L(
          'Replay the full measured history of sector &amp; subsector relative rotation. Each dot is a sector or subsector; horizontal axis = relative strength (right = stronger vs peers), vertical = whether that strength is heating up or cooling (up = gaining momentum). Short trails show the last 6 dates so each path stays readable. Episode annotations mark measured rotation events from the catalog. No predictive claim — this replays measured history.',
          '回放板块与子行业相对轮动的完整实测历史。每个点代表一个板块或子行业；横轴 = 相对强度（越靠右越强），纵轴 = 该强度是在升温还是降温（越靠上越热）。短轨迹显示近6个交易日，令每条路径清晰可辨。情节注释标记了来自数据库的实际轮动事件。无预测性主张——仅回放实测历史。')
      +'</p>'
      // Oracle panel shock staleness note (PS-W2-E / PS-R3) — absent file = no note.
      +'<div id="oracle-shock-note"></div>'
      // Preset playlist
      +'<div class="tm-presets" id="tm-presets">'
      +'<span class="tm-ep-hd l-en">Famous episodes</span>'
      +'<span class="tm-ep-hd l-zh">经典轮动片段</span>'
      +'</div>'
      // Unit toggle: Sectors / Subsectors / Themes / Factors
      +'<div class="tm-unit-row" id="tm-unit-row">'
      +'<div class="tm-tier-btns" role="group">'
      +'<button class="tm-tier-btn active" data-tmunit="sectors" id="tm-btn-sectors">'
      +'<span class="l-en">Sectors 1998→</span><span class="l-zh">板块 1998→</span></button>'
      +'<button class="tm-tier-btn" data-tmunit="subsectors" id="tm-btn-subsectors">'
      +'<span class="l-en">Subsectors 2021→</span><span class="l-zh">子行业 2021→</span></button>'
      +'<button class="tm-tier-btn" data-tmunit="themes" id="tm-btn-themes">'
      +'<span class="l-en">Themes 2021→</span><span class="l-zh">主题 2021→</span></button>'
      +'<button class="tm-tier-btn" data-tmunit="factors" id="tm-btn-factors">'
      +'<span class="l-en">Factors 2013→</span><span class="l-zh">因子 2013→</span></button>'
      +'</div></div>'
      // Year selector chip row (built by JS from manifest)
      +'<div class="tm-year-row" id="tm-year-row" aria-label="Year selector">'
      +'<div class="tm-year-chips" id="tm-year-chips"></div></div>'
      // Playback controls
      +'<div class="tm-controls">'
      +'<button class="tm-play-btn" id="tm-play" aria-label="Play / Pause">▶</button>'
      +'<select class="tm-speed-sel" id="tm-speed" aria-label="Playback speed">'
      +'<option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select>'
      +'<span class="tm-date-lbl" id="tm-date-lbl">—</span>'
      +'<div class="tm-kb-hint"><span class="l-en">← → step</span><span class="l-zh">← → 逐日</span></div>'
      +'</div>'
      // Slider
      +'<div class="tm-slider-wrap">'
      +'<input type="range" class="tm-slider" id="tm-slider" min="0" max="0" value="0" aria-label="Date scrubber">'
      +'</div>'
      // Survivorship watermark (Subsectors/Themes only)
      +'<p class="tm-watermark" id="tm-watermark" style="display:none">'
      +'<span class="l-en">Membership as of 2026-06 — historical composition approximated</span>'
      +'<span class="l-zh">成员截至2026年6月 — 历史成份为近似估算</span></p>'
      // Map + episodes panel
      +'<div class="tm-scatter-wrap">'
      +'<div class="tm-map-box" id="tm-map-box">'
      +'<div class="tm-loading" id="tm-loading">'
      +'<span class="l-en">Loading Time Machine…</span><span class="l-zh">正在加载时光机…</span></div>'
      +'</div>'
      +'<div class="tm-episodes-panel" id="tm-ep-panel">'
      +'<div class="tm-ep-hd"><span class="l-en">Active episodes</span><span class="l-zh">当前活跃情节</span></div>'
      +'<div id="tm-ep-list"><span class="tm-ep-empty">'
      +'<span class="l-en">—</span><span class="l-zh">—</span></span></div>'
      +'</div></div>'
      +'</section>';

    // Focus tracking for keyboard navigation
    var sec = document.getElementById('tm-section');
    if(sec){
      sec.addEventListener('focusin',  function(){ _tmHasFocus = true; });
      sec.addEventListener('focusout', function(){ _tmHasFocus = false; });
      sec.addEventListener('mouseenter', function(){ _tmHasFocus = true; });
      sec.addEventListener('mouseleave', function(){ _tmHasFocus = false; });
    }
    _loadShockNote();
  }

  /* ── Oracle panel shock staleness note — fetched live; absent file = no note ── */
  function _loadShockNote(){
    fetch('live/shock_state.json',{cache:'no-cache'})
      .then(function(r){if(!r.ok)throw 0;return r.json();})
      .then(function(d){
        if(!d||!d.active)return;
        var el=document.getElementById('oracle-shock-note');
        if(!el)return;
        var msg=isZh()?
          ('注意：冲击降级协议激活（至 '+esc(d.expires)+'）——数据依据冲击前基准，仅供参考。'):
          ('Note: Shock de-escalation active (until '+esc(d.expires)+') — data reflects pre-shock baseline; interpret with caution.');
        el.innerHTML='<p class="oracle-shock-note">'+msg+'</p>';
      }).catch(function(){/* absent file → no note */});
  }

  // Sector ETF tickers → plain sector names (matches the live rotation map above).
  // Keyed on the manifest node id (the ticker); the ticker stays the node key,
  // only the DISPLAYED label changes, so episodes/tooltips keep working.
  var TM_SEC_NAMES = {
    XLB:{en:'Materials',zh:'材料'},          XLC:{en:'Comm Services',zh:'通信'},
    XLE:{en:'Energy',zh:'能源'},              XLF:{en:'Financials',zh:'金融'},
    XLI:{en:'Industrials',zh:'工业'},         XLK:{en:'Technology',zh:'科技'},
    XLP:{en:'Cons Staples',zh:'必需消费'},    XLRE:{en:'Real Estate',zh:'房地产'},
    XLU:{en:'Utilities',zh:'公用事业'},       XLV:{en:'Health Care',zh:'医疗保健'},
    XLY:{en:'Cons Discretionary',zh:'可选消费'}
  };
  function _tmName(name, name_zh){
    var m = TM_SEC_NAMES[name];
    if(m) return isZh() ? m.zh : m.en;
    return (isZh() && name_zh) ? name_zh : name;
  }
  // Strength = where a dot sits on the grid, combining X (relative strength) and
  // Y (momentum) with equal weight → 0 (deep Lagging) · 50 (centre) · 100 (deep
  // Leading). It reads the SAME per-year domain the chart is drawn with, so the
  // two very-different-scale axes are already normalised. Display-only: a readout
  // of on-screen position, NOT a trade signal.
  function _posScore(rs, az){
    var d = _domain;
    if(!d) return null;
    var xw = (d.xMax - d.xMin) || 1, yw = (d.yMax - d.yMin) || 1;
    var xf = (rs - d.xMin) / xw, yf = (az - d.yMin) / yw;
    xf = xf < 0 ? 0 : xf > 1 ? 1 : xf;
    yf = yf < 0 ? 0 : yf > 1 ? 1 : yf;
    return Math.round(100 * (xf + yf) / 2);
  }

  /* ── keyboard: ArrowLeft/ArrowRight when section has pointer focus ── */
  document.addEventListener('keydown', function(e){
    if(!_tmHasFocus) return;
    if(e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if(!_yearDates.length) return;
    e.preventDefault();
    _stopPlay();
    if(e.key === 'ArrowLeft')  _pos = Math.max(0, _pos - 1);
    if(e.key === 'ArrowRight') _pos = Math.min(_yearDates.length - 1, _pos + 1);
    _syncSlider();
    _updateDateLabel();
    _ensureChunksForPos(_pos, function(){
      // Any arrow-key seek can jump non-incrementally; rebuild trail from
      // actual history so the drawn path reflects where the node came from.
      _rebuildTrailBuf(_pos);
      _renderFrame(); _updateEpPanel();
    });
  });

  function _init(){
    if(_inited) return;
    _inited = true;
    Promise.all([
      fetch(MANI, {cache:'no-cache'}).then(function(r){if(!r.ok)throw 0;return r.json();}),
      fetch(EP,   {cache:'no-cache'}).then(function(r){if(!r.ok)throw 0;return r.json();})
    ]).then(function(res){
      _manifest = res[0];
      _epFeed   = res[1];
      _buildPresets();
      _wireControls();
      // Build year chips from manifest (no chunk fetches needed)
      _buildYearChips('s');
      // Default: newest year, sectors unit
      _setUnit('sectors', function(){});
    }).catch(function(){
      var ld = document.getElementById('tm-loading');
      if(ld) ld.innerHTML = '<span class="l-en">Could not load Time Machine data.</span><span class="l-zh">无法加载时光机数据。</span>';
    });
  }

  /* ── unit management ── */
  // Map unit name to manifest tier
  function _tierForUnit(u){ if(u === 'sectors') return 's'; if(u === 'factors') return 'f'; return 'm'; }
  // Filter registry for current unit from tier-m
  function _registryForUnit(u){
    if(u === 'sectors') return _manifest.registry['s'] || [];
    if(u === 'factors') return _manifest.registry['f'] || [];
    var all = _manifest.registry['m'] || [];
    if(u === 'subsectors') return all.filter(function(r){ return r.tier === 'subsector'; });
    if(u === 'themes')     return all.filter(function(r){ return r.tier === 'theme'; });
    return all.filter(function(r){ return r.tier === 'subsector'; });
  }

  function _setUnit(unit, cb){
    _unit = unit;
    var tier = _tierForUnit(unit);
    _registry  = _registryForUnit(unit);
    _chunkMeta = (_manifest.tiers[tier] || {}).chunks || [];
    _domain    = null;
    _domainSet = false;
    _trailBuf  = {};

    // Update unit toggle buttons
    document.querySelectorAll('.tm-tier-btn[data-tmunit]').forEach(function(b){
      b.classList.toggle('active', b.getAttribute('data-tmunit') === unit);
    });
    // Rebuild year chips for new tier
    _buildYearChips(tier);
    // Show/hide survivorship watermark
    var wm = document.getElementById('tm-watermark');
    if(wm){
      if(wm._orig === undefined) wm._orig = wm.innerHTML;
      if(unit === 'factors'){
        wm.style.display = '';
        // D-11: plainify watermark — remove "6 style sleeves", "collinear", "SPY-excess replay"
        wm.innerHTML = '<span class="l-en">Style groups, replayed vs the market — a picture of the past, not a forecast.</span>'
                     + '<span class="l-zh">风格分组相对大盘的历史回放——是过去的画面，而非预测。</span>';
      } else {
        wm.innerHTML = wm._orig;
        wm.style.display = (unit !== 'sectors') ? '' : 'none';
      }
    }

    // Activate most recent year
    var chips = document.querySelectorAll('#tm-year-chips .tm-year-chip');
    var lastChip = chips[chips.length - 1];
    if(lastChip) {
      _selectYearChip(lastChip, cb);
    } else {
      if(cb) cb();
    }
  }

  /* ── year chip building ── */
  function _buildYearChips(tier){
    var chips = document.getElementById('tm-year-chips');
    if(!chips || !_manifest) return;
    var chunkList = (_manifest.tiers[tier] || {}).chunks || [];
    // Derive unique years from chunk metadata
    var years = [];
    var seen  = {};
    chunkList.forEach(function(c){
      var y = c.key.slice(0,4);
      if(!seen[y]){ seen[y] = true; years.push(y); }
    });
    chips.innerHTML = '';
    years.forEach(function(y){
      var btn = document.createElement('button');
      btn.className = 'tm-year-chip';
      btn.setAttribute('data-year', y);
      btn.textContent = y;
      btn.addEventListener('click', function(){
        _stopPlay();
        _selectYearChip(btn, function(){});
      });
      chips.appendChild(btn);
    });
    // Also add a "Now" chip at the end
    var nowBtn = document.createElement('button');
    nowBtn.className = 'tm-year-chip tm-year-now';
    nowBtn.setAttribute('data-year', 'now');
    nowBtn.innerHTML = '<span class="l-en">Now</span><span class="l-zh">当下</span>';
    nowBtn.addEventListener('click', function(){
      _stopPlay();
      _selectYearChip(nowBtn, function(){});
    });
    chips.appendChild(nowBtn);
  }

  function _selectYearChip(chip, cb){
    // Mark active
    document.querySelectorAll('#tm-year-chips .tm-year-chip').forEach(function(c){
      c.classList.remove('active');
    });
    chip.classList.add('active');
    var y = chip.getAttribute('data-year');
    // "Now" = most recent year
    if(y === 'now'){
      var allChips = document.querySelectorAll('#tm-year-chips .tm-year-chip:not(.tm-year-now)');
      var lastReal = allChips[allChips.length - 1];
      y = lastReal ? lastReal.getAttribute('data-year') : null;
    }
    _year = y;
    _loadYear(y, cb);
  }

  /* ── year loading: fetch only the selected year's chunks + preceding boundary ── */
  function _loadYear(year, cb){
    if(!year || !_manifest) return;
    var tier = _tierForUnit(_unit);
    var allChunks = (_manifest.tiers[tier] || {}).chunks || [];
    _chunkMeta = allChunks;

    // Chunks for the selected year
    var yearChunks = allChunks.filter(function(c){ return c.key.slice(0,4) === year; });
    // Preceding chunk for trail continuity
    var firstYearIdx = allChunks.indexOf(yearChunks[0]);
    var prevChunk = firstYearIdx > 0 ? allChunks[firstYearIdx - 1] : null;

    _yearChunkKeys = (prevChunk ? [prevChunk.key] : []).concat(yearChunks.map(function(c){ return c.key; }));

    // Show loading
    var ld = document.getElementById('tm-loading');
    if(ld){ ld.textContent = ''; ld.style.display = ''; }

    // Fetch all needed chunks in parallel (cached after first fetch)
    var pending = _yearChunkKeys.length;
    if(!pending){ _afterYearLoaded(year, cb); return; }
    _yearChunkKeys.forEach(function(key){
      _getChunk(key, function(){ if(--pending === 0) _afterYearLoaded(year, cb); });
    });
  }

  function _afterYearLoaded(year, cb){
    // Build date list from year's own chunks (not prev boundary)
    var tier = _tierForUnit(_unit);
    var allChunks = (_manifest.tiers[tier] || {}).chunks || [];
    var yearChunks = allChunks.filter(function(c){ return c.key.slice(0,4) === year; });
    _yearDates = [];
    yearChunks.forEach(function(c){
      var chunk = _chunks[c.key];
      if(chunk && chunk.dates) _yearDates = _yearDates.concat(chunk.dates);
    });
    _yearDates.sort();

    _pos = _yearDates.length - 1;  // default: last date (most recent)
    _domain    = null;
    _domainSet = false;
    _trailBuf  = {};

    // Seed trail from prev-boundary chunk's last TRAIL_LEN-1 dates so the
    // first frame of this year already has a historical tail (not empty).
    var firstYearIdx = allChunks.indexOf(yearChunks[0]);
    var prevChunkMeta = firstYearIdx > 0 ? allChunks[firstYearIdx - 1] : null;
    if(prevChunkMeta){
      var prevChunk = _chunks[prevChunkMeta.key];
      if(prevChunk && prevChunk.dates && prevChunk.dates.length){
        var boundaryDates = prevChunk.dates.slice(-(TRAIL_LEN - 1));
        boundaryDates.forEach(function(d){
          var pts = _getNodePoints(d);
          if(pts.length) _updateTrailBuf(pts);
        });
      }
    }

    // Compute stable domain from all frames in the year (2nd-98th percentile)
    _computeStableDomain(year);

    var slider = document.getElementById('tm-slider');
    if(slider){
      slider.min = 0;
      slider.max = Math.max(0, _yearDates.length - 1);
      slider.value = _pos;
    }
    _updateDateLabel();
    _renderFrame();
    _updateEpPanel();
    var ld = document.getElementById('tm-loading');
    if(ld) ld.style.display = 'none';
    if(cb) cb();
  }

  /* ── stable domain from 2nd-98th percentile of all frames in year ── */
  function _computeStableDomain(year){
    var tier = _tierForUnit(_unit);
    var allChunks = (_manifest.tiers[tier] || {}).chunks || [];
    var yearChunks = allChunks.filter(function(c){ return c.key.slice(0,4) === year; });
    var allRs = [], allAz = [];
    yearChunks.forEach(function(c){
      var chunk = _chunks[c.key];
      if(!chunk || !chunk.dates) return;
      chunk.dates.forEach(function(_, di){
        _registry.forEach(function(reg){
          var arr = chunk.data && chunk.data[String(reg.id)];
          if(!arr || di >= arr.length) return;
          var v = arr[di];
          if(!v || v[0] == null || v[1] == null) return;
          allRs.push(v[0]);
          allAz.push(v[1]);
        });
      });
    });
    if(!allRs.length){ _domain = null; return; }
    allRs.sort(function(a,b){return a-b;});
    allAz.sort(function(a,b){return a-b;});
    function pct(arr, p){ var i = Math.max(0, Math.min(arr.length-1, Math.round(p*(arr.length-1)))); return arr[i]; }
    var xMin = pct(allRs, 0.02), xMax = pct(allRs, 0.98);
    var yMin = pct(allAz, 0.02), yMax = pct(allAz, 0.98);
    // Pad 15%
    var xp = (xMax-xMin||1)*0.15, yp = (yMax-yMin||1)*0.15;
    _domain = {xMin:xMin-xp, xMax:xMax+xp, yMin:yMin-yp, yMax:yMax+yp};
  }

  /* ── chunk loader ── */
  function _getChunk(key, cb){
    if(_chunks[key]){ if(cb) cb(_chunks[key]); return; }
    var meta = _chunkMeta.filter(function(c){ return c.key === key; })[0];
    if(!meta){ _chunks[key] = {}; if(cb) cb({}); return; }
    fetch(BASE + meta.file, {cache:'no-cache'})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(d){ _chunks[key] = d || {}; if(cb) cb(_chunks[key]); })
      .catch(function(){ _chunks[key] = {}; if(cb) cb({}); });
  }

  function _ensureChunksForPos(pos, cb){
    var dateStr = _yearDates[pos];
    if(!dateStr){ if(cb) cb(); return; }
    var meta = _chunkMeta.filter(function(c){ return c.date_from <= dateStr && dateStr <= c.date_to; })[0];
    if(!meta){ if(cb) cb(); return; }
    _getChunk(meta.key, cb);
  }

  /* ── get node points for a single date ── */
  function _getNodePoints(dateStr){
    if(!_registry || !dateStr) return [];
    var meta = _chunkMeta.filter(function(c){ return c.date_from <= dateStr && dateStr <= c.date_to; })[0];
    if(!meta) return [];
    var chunk = _chunks[meta.key];
    if(!chunk || !chunk.dates) return [];
    var di = chunk.dates.indexOf(dateStr);
    if(di < 0) return [];
    var pts = [];
    _registry.forEach(function(reg){
      var arr = chunk.data && chunk.data[String(reg.id)];
      if(!arr || di >= arr.length) return;
      var v = arr[di];
      if(!v || v[0] == null || v[1] == null) return;
      pts.push({id:reg.id, name:reg.name, name_zh:reg.name_zh, tier:reg.tier, theme:reg.theme, rs:v[0], az:v[1]});
    });
    return pts;
  }

  /* ── rebuild trail buffer from scratch for a given position (non-incremental seek) ── */
  // Replays _getNodePoints over the preceding min(TRAIL_LEN-1, pos) dates so
  // that when _renderFrame subsequently calls _updateTrailBuf for pos itself,
  // the buffer contains the correct historical path rather than a spurious line
  // from wherever the view last was.
  function _rebuildTrailBuf(pos){
    _trailBuf = {};
    var start = Math.max(0, pos - TRAIL_LEN + 1);
    // Replay up to (but not including) pos — _renderFrame will append pos
    for(var i = start; i < pos; i++){
      var pts = _getNodePoints(_yearDates[i]);
      if(pts.length) _updateTrailBuf(pts);
    }
  }

  /* ── incremental trail buffer update ── */
  function _updateTrailBuf(pts){
    var seen = {};
    pts.forEach(function(pt){
      seen[pt.id] = true;
      var buf = _trailBuf[pt.id] || [];
      buf.push([pt.rs, pt.az]);
      if(buf.length > TRAIL_LEN) buf.shift();
      _trailBuf[pt.id] = buf;
    });
    // Prune nodes that vanished
    Object.keys(_trailBuf).forEach(function(id){
      if(!seen[id]) delete _trailBuf[id];
    });
  }

  /* ── determine quadrant from rs, az ── */
  function _quadrant(rs, az){
    if(rs >= 0 && az >= 0) return 'leading';
    if(rs >= 0 && az <  0) return 'weakening';
    if(rs <  0 && az >= 0) return 'improving';
    return 'lagging';
  }

  /* ── render a single frame ── */
  function _renderFrame(){
    var box = document.getElementById('tm-map-box');
    if(!box) return;
    var dateStr = _yearDates[_pos];
    var pts = _getNodePoints(dateStr);
    _updateTrailBuf(pts);

    if(!pts.length){
      box.innerHTML = '<div class="tm-loading"><span class="l-en">No data for this date</span><span class="l-zh">此日期无数据</span></div>';
      return;
    }

    // Build active episodes index
    var activeEpNodes = {};
    if(_epFeed && _epFeed.episodes){
      _epFeed.episodes.forEach(function(ep){
        if(!ep.onset_date || ep.onset_date > dateStr) return;
        var end = ep.exhausted_date || ep.confirmed_date;
        if(end && end < dateStr) return;
        var stage = 'onset';
        if(ep.undeniable_date && ep.undeniable_date <= dateStr) stage = 'undeniable';
        else if(ep.confirmed_date && ep.confirmed_date <= dateStr) stage = 'confirmed';
        // Only show episodes relevant to the current unit/tier
        var epTier = ep.tier || 's';
        var ourTier = _tierForUnit(_unit);
        if(epTier !== ourTier) return;
        if(!activeEpNodes[ep.node] || stage === 'undeniable'){
          activeEpNodes[ep.node] = {dir:ep.direction, stage:stage};
        }
      });
    }

    // Determine which nodes to label & which need speed calculation
    var showAll = (_unit === 'sectors' || _unit === 'factors');  // label all sector/factor nodes
    // For m-tier: label top ~12 by trail speed + any node with episode ring
    var speedMap = {};
    if(!showAll){
      pts.forEach(function(pt){
        var buf = _trailBuf[pt.id] || [];
        if(buf.length < 2){ speedMap[pt.id] = 0; return; }
        var first = buf[0], last = buf[buf.length-1];
        speedMap[pt.id] = Math.sqrt(Math.pow(last[0]-first[0],2)+Math.pow(last[1]-first[1],2));
      });
    }

    // Build spec.points
    var ptsForSpec = pts.map(function(pt){
      var q = _quadrant(pt.rs, pt.az);
      var buf = _trailBuf[pt.id] || [];
      // Trail = buf[0..n-2] (exclude current, which is p.x/p.y themselves)
      var trailPts = buf.length > 1 ? buf.slice(0, buf.length-1).map(function(b){ return [b[0], b[1]]; }) : null;
      var ep = activeEpNodes[pt.name];
      var ring = ep ? ep.dir : null;
      var ringWeight = ep ? (ep.stage==='undeniable'?2.5:ep.stage==='confirmed'?1.8:1.2) : 1.5;
      var name = _tmName(pt.name, pt.name_zh);
      var showLabel;
      if(showAll){ showLabel = true; }
      else if(ep){ showLabel = true; }
      else {
        // Top ~12 by trail speed; when fewer than 12 nodes exist show all,
        // but when the 12th-fastest speed is 0 (trail not yet built) suppress
        // labels for nodes with no trail movement to avoid first-frame hairball.
        var speeds = Object.values ? Object.values(speedMap) : Object.keys(speedMap).map(function(k){return speedMap[k];});
        speeds.sort(function(a,b){return b-a;});
        var thresh12 = speeds[11];
        var thresh = (thresh12 !== undefined && thresh12 > 0) ? thresh12 : null;
        showLabel = thresh === null ? (speeds.length <= 12) : (speedMap[pt.id] >= thresh);
      }
      return {
        key:      pt.name,
        label:    name,
        quadrant: q,
        x:        pt.rs,
        y:        pt.az,
        r:        6,
        trail:    trailPts,
        ring:     ring,
        ringWeight: ringWeight,
        showLabel: showLabel,
        hot:      ep && ep.stage === 'undeniable'
      };
    });

    // Resolve axis strings
    var axisSpec = {
      xLo: isZh()?'弱于大盘':'WEAKER',
      xHi: isZh()?'强于大盘':'STRONGER',
      yHi: isZh()?'升温':'HEATING UP',
      yLo: isZh()?'降温':'COOLING'
    };

    var nLabel = pts.length + ' ' + (_unit==='sectors'?'sectors':_unit==='factors'?'factors':_unit==='themes'?'themes':'subsectors');
    var srrSpec = {
      points:       ptsForSpec,
      domain:       _domain || null,
      axis:         axisSpec,
      zoomQuadrant: null,
      ariaLabel:    'Rotation map — '+nLabel+', '+(_unit==='sectors'?'Sector ETFs, ':'')+(dateStr||''),
      onHover: function(key, cx, cy){
        if(!key){ _hideTmTip(); return; }
        _showTmTip(key, pts, cx, cy);
      },
      onClick: function(key){ /* no navigation in TM */ }
    };

    if(window.SRR && window.SRR.render){
      window.SRR.render(box, srrSpec);
    }
  }

  /* ── TM tooltip ── */
  function _getTmTipEl(){
    if(_tmTip) return _tmTip;
    _tmTip = document.createElement('div');
    _tmTip.className = 'sr-tip';
    document.body.appendChild(_tmTip);
    return _tmTip;
  }
  function _showTmTip(key, pts, cx, cy){
    var pt = pts.filter(function(p){ return p.name === key; })[0];
    if(!pt){ _hideTmTip(); return; }
    var q = _quadrant(pt.rs, pt.az);
    var QMAP = {leading:{en:'Leading',zh:'领先',cls:'q-lead'},weakening:{en:'Weakening',zh:'走弱',cls:'q-weak'},improving:{en:'Improving',zh:'改善',cls:'q-impr'},lagging:{en:'Lagging',zh:'落后',cls:'q-lag'}};
    var qd = QMAP[q] || QMAP.lagging;
    var name = _tmName(pt.name, pt.name_zh);
    // Check for active episode
    var dateStr = _yearDates[_pos];
    var ep = null;
    if(_epFeed && _epFeed.episodes){
      _epFeed.episodes.forEach(function(e){
        if(e.node !== pt.name) return;
        if(!e.onset_date || e.onset_date > dateStr) return;
        var end = e.exhausted_date || e.confirmed_date;
        if(end && end < dateStr) return;
        var stage = 'onset';
        if(e.undeniable_date && e.undeniable_date <= dateStr) stage = 'undeniable';
        else if(e.confirmed_date && e.confirmed_date <= dateStr) stage = 'confirmed';
        ep = {dir:e.direction, stage:stage};
      });
    }
    var el = _getTmTipEl();
    var rsStr = (pt.rs>0?'+':'')+pt.rs.toFixed(2);
    var azStr = (pt.az>0?'+':'')+pt.az.toFixed(2);
    var TIP_STAGE = {
      onset:      '<span class="l-en">onset</span><span class="l-zh">初现</span>',
      confirmed:  '<span class="l-en">confirmed</span><span class="l-zh">确认</span>',
      undeniable: '<span class="l-en">undeniable</span><span class="l-zh">确立</span>'
    };
    var epLine = ep ? '<div class="sr-tip-mt">'
      +(ep.dir==='in'?'<span class="l-en">Rotating in</span><span class="l-zh">轮入</span>':'<span class="l-en">Rotating out</span><span class="l-zh">轮出</span>')
      +' <b class="'+(ep.stage==='undeniable'?'up':ep.stage==='confirmed'?'up':'')+'">'+( TIP_STAGE[ep.stage]||esc(ep.stage) )+'</b></div>' : '';
    // Strength = combined X+Y position on the grid (display-only readout, not a signal)
    var scoreV = _posScore(pt.rs, pt.az);
    var qCol = {leading:'--up',weakening:'--warn',improving:'--link',lagging:'--down'}[q] || '--muted';
    var scoreRow = scoreV==null ? '' : '<div class="sr-tip-score">'
      +'<div class="sr-tip-score-hd"><span class="l-en">Strength</span><span class="l-zh">强度</span>'
      +'<b>'+scoreV+'</b><i>/100</i></div>'
      +'<div class="sr-tip-gauge"><span style="width:'+scoreV+'%;background:var('+qCol+')"></span></div>'
      +'<div class="sr-tip-cap"><span class="l-en">position on the grid (X+Y) · not a trade signal</span><span class="l-zh">图上位置（X+Y）· 非交易信号</span></div>'
      +'</div>';
    var thLine = _unit==='sectors'
      ? '<span class="l-en">Sector ETF · </span><span class="l-zh">行业ETF · </span>'+esc(pt.name)
      : _unit==='factors'
        ? '<span class="l-en">Factor · context</span><span class="l-zh">因子 · 参考</span>'
        : esc(pt.theme||'');
    el.innerHTML = '<div class="sr-tip-hd"><b>'+esc(name)+'</b><span class="sr-q '+qd.cls+'">'+(isZh()?qd.zh:qd.en)+'</span></div>'
      +'<div class="sr-tip-th">'+thLine+'</div>'
      +'<div class="sr-tip-mt"><span class="l-en">RS</span><span class="l-zh">相对强度</span> <b>'+rsStr+'</b> · <span class="l-en">Mom</span><span class="l-zh">动量</span> <b class="'+(pt.az>=0?'up':'dn')+'">'+azStr+'</b></div>'
      +scoreRow
      +epLine;
    el.classList.add('on');
    var w=el.offsetWidth, h=el.offsetHeight, x=cx+14, y=cy+14;
    if(x+w>window.innerWidth-8) x=cx-w-14;
    if(y+h>window.innerHeight-8) y=cy-h-14;
    el.style.left = Math.max(8,x)+'px';
    el.style.top  = Math.max(8,y)+'px';
  }
  function _hideTmTip(){
    if(_tmTip) _tmTip.classList.remove('on');
  }

  /* ── episode side panel ── */
  function _updateEpPanel(){
    var el = document.getElementById('tm-ep-list');
    if(!el || !_epFeed) return;
    var dateStr = _yearDates[_pos];
    if(!dateStr){ el.innerHTML='<span class="tm-ep-empty"><span class="l-en">—</span><span class="l-zh">—</span></span>'; return; }
    var ourTier = _tierForUnit(_unit);
    // Build a set of node names visible on the current map to avoid listing
    // episodes for nodes of the other m-tier kind (e.g. theme episodes on the
    // subsectors map where their dot ring would never appear).
    var registryNames = {};
    (_registry || []).forEach(function(r){ registryNames[r.name] = true; });
    var active = (_epFeed.episodes||[]).filter(function(ep){
      if(!ep.onset_date || ep.onset_date > dateStr) return false;
      var end = ep.exhausted_date || ep.confirmed_date;
      if(end && end < dateStr) return false;
      if((ep.tier||'s') !== ourTier) return false;
      // For m-tier units, also require the episode node to be in the current
      // unit's registry so panel and dot-ring set stay consistent.
      if((ourTier === 'm' || ourTier === 'f') && !registryNames[ep.node]) return false;
      return true;
    });
    if(!active.length){
      el.innerHTML='<span class="tm-ep-empty"><span class="l-en">No episodes on this date</span><span class="l-zh">此日期暂无情节</span></span>';
      return;
    }
    active.sort(function(a,b){ return (a.direction==='in'?0:1)-(b.direction==='in'?0:1)||(b.onset_date||'').localeCompare(a.onset_date||''); });
    active = active.slice(0,20);
    var STAGE_HTML = {
      onset:      '<span class="l-en">onset</span><span class="l-zh">初现</span>',
      confirmed:  '<span class="l-en">confirmed</span><span class="l-zh">确认</span>',
      undeniable: '<span class="l-en">undeniable</span><span class="l-zh">确立</span>'
    };
    el.innerHTML = active.map(function(ep){
      var stage = 'onset';
      if(ep.undeniable_date && ep.undeniable_date <= dateStr) stage='undeniable';
      else if(ep.confirmed_date && ep.confirmed_date <= dateStr) stage='confirmed';
      var dirClass = ep.direction==='in'?'tm-ep-dir-in':'tm-ep-dir-out';
      var dirLabel = ep.direction==='in'
        ? '<span class="l-en">Rotating in</span><span class="l-zh">轮入</span>'
        : '<span class="l-en">Rotating out</span><span class="l-zh">轮出</span>';
      return '<div class="tm-ep-item '+dirClass+'">'
        +'<div class="tm-ep-node">'+esc(_tmName(ep.node))+'</div>'
        +'<div>'+dirLabel+' <span class="tm-ep-badge '+stage+'">'+(STAGE_HTML[stage]||stage)+'</span></div>'
        +(ep.paired_episode_id?'<div class="tm-ep-pair"><span class="l-en">Pair: </span><span class="l-zh">配对：</span>'+esc(ep.paired_episode_id)+'</div>':'')
        +'</div>';
    }).join('');
  }

  /* ── preset playlist ── */
  function _buildPresets(){
    var strip = document.getElementById('tm-presets');
    if(!strip || !_epFeed || !(_epFeed.presets||[]).length) return;
    strip.innerHTML = '<span class="tm-ep-hd l-en">Famous episodes</span><span class="tm-ep-hd l-zh">经典轮动片段</span>';
    _epFeed.presets.forEach(function(preset){
      var btn = document.createElement('button');
      btn.className = 'tm-preset-btn';
      btn.innerHTML = '<span class="l-en">'+esc(preset.label_en)+'</span><span class="l-zh">'+esc(preset.label_zh)+'</span>';
      btn.addEventListener('click', function(){ _activatePreset(preset); });
      strip.appendChild(btn);
    });
  }

  function _activatePreset(preset){
    _stopPlay();
    var tier = preset.tier || 's';
    var targetUnit = tier==='s'?'sectors':tier==='f'?'factors':'subsectors';
    var targetYear = (preset.date_from||'').slice(0,4);
    function _seekAfterLoad(){
      if(!targetYear || !_yearDates.length){ return; }
      var target = preset.date_from;
      var idx = _yearDates.indexOf(target);
      if(idx < 0){
        idx = _yearDates.length - 1;
        for(var i=0; i<_yearDates.length; i++){
          if(_yearDates[i] >= target){ idx = i; break; }
        }
      }
      _pos = idx;
      _syncSlider();
      _updateDateLabel();
      _ensureChunksForPos(_pos, function(){ _rebuildTrailBuf(_pos); _renderFrame(); _updateEpPanel(); });
      // Also click the matching year chip
      _activateYearChipForYear(targetYear);
    }
    if(targetUnit !== _unit){
      _setUnit(targetUnit, function(){
        // _setUnit loads the newest year; we need to switch to target year
        _activateYearChipForYear(targetYear, _seekAfterLoad);
      });
    } else {
      _activateYearChipForYear(targetYear, _seekAfterLoad);
    }
  }

  function _activateYearChipForYear(year, cb){
    var chips = document.querySelectorAll('#tm-year-chips .tm-year-chip');
    var found = null;
    chips.forEach(function(c){ if(c.getAttribute('data-year') === year) found = c; });
    if(found){
      _stopPlay();
      _selectYearChip(found, cb || function(){});
    } else {
      if(cb) cb();
    }
  }

  /* ── playback controls ── */
  function _stopPlay(){
    if(_playTimer){ clearTimeout(_playTimer); _playTimer = null; }
    _playing = false;
    var p = document.getElementById('tm-play');
    if(p) p.textContent = '▶';
  }

  function _syncSlider(){
    var slider = document.getElementById('tm-slider');
    if(slider) slider.value = _pos;
  }

  function _updateDateLabel(){
    var el = document.getElementById('tm-date-lbl');
    if(el) el.textContent = _yearDates[_pos] || '—';
  }

  function _wireControls(){
    // Unit buttons
    document.querySelectorAll('.tm-tier-btn[data-tmunit]').forEach(function(btn){
      btn.addEventListener('click', function(){
        _stopPlay();
        _setUnit(btn.getAttribute('data-tmunit'), function(){});
      });
    });

    // Play/pause
    var playBtn = document.getElementById('tm-play');
    if(playBtn){
      playBtn.addEventListener('click', function(){
        _playing = !_playing;
        playBtn.textContent = _playing ? '⏸' : '▶';
        if(_playing){
          // Clear any previously queued timer before starting a new chain
          if(_playTimer){ clearTimeout(_playTimer); _playTimer = null; }
          _tick();
        }
      });
    }

    // Slider
    var slider = document.getElementById('tm-slider');
    if(slider){
      slider.addEventListener('input', function(){
        _stopPlay();
        _pos = parseInt(slider.value, 10);
        _updateDateLabel();
        _ensureChunksForPos(_pos, function(){ _rebuildTrailBuf(_pos); _renderFrame(); _updateEpPanel(); });
      });
    }
  }

  function _tick(){
    if(!_playing) return;
    // Recalibrated 4× slower and smoother: advance ONE date per tick (every date
    // is rendered, no skipping) and vary the delay by speed instead of the step.
    // 1× = 800ms/date (0.25× the old pace) · 2× = 400ms · 4× = 200ms (old 1×).
    var speed = parseInt((document.getElementById('tm-speed')||{}).value||1, 10);
    _pos = Math.min(_yearDates.length - 1, _pos + 1);
    if(_pos >= _yearDates.length - 1){
      _playing = false;
      var p = document.getElementById('tm-play'); if(p) p.textContent = '▶';
    }
    _syncSlider();
    _updateDateLabel();
    _ensureChunksForPos(_pos, function(){ _renderFrame(); _updateEpPanel(); });
    if(_playing) _playTimer = setTimeout(_tick, Math.round(800 / speed));
  }

  /* ── theme/lang change: re-render current frame (no-op until opened) ── */
  var _themeObs = new MutationObserver(function(){ if(_inited) _renderFrame(); });
  _themeObs.observe(document.documentElement, {attributes:true, attributeFilter:['data-theme','data-lang']});

  /* ── boot: mount the collapsed shell; the heavy path waits for first open.
     (The retired page booted on an IntersectionObserver at 200px rootMargin —
     the collapsed <details> replaces that trigger.) ── */
  function boot(){
    injectStyle();
    var d = mount();
    if(!d) return;
    d.addEventListener('toggle', function(){
      if(!d.open) return;
      buildBody();
      _init();
    });
    // Already open (e.g. a browser restoring state) → build immediately
    if(d.open){ buildBody(); _init(); }
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot);
  else boot();
})();

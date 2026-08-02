
/* ══════════════════════════════════════════════════════════════════════════
   OPTIONS WORKSPACE — mode switching + the lazy payload fetches.
   PAYLOAD LAW: the chrome and the Brief are baked above and need no network.
   Scanner / Ticker / Leaders fetch their JSON with plain fetch() on first
   activation and cache it for the session. NEVER inject a <script> loader —
   that bypasses asset stamping (#3372).
   STATIC code only — marked data-externalize so the post-render sweep
   (scripts/externalize_css.py) lifts it to a cached assets/js/<hash>.js; any
   render-time value must go through the data script above or it will freeze
   behind an immutable, max-age=1y URL and replay a stale nightly bake.
   ══════════════════════════════════════════════════════════════════════════ */
(function(){
'use strict';
var MODES = ['brief','flow','scanner','ticker','leaders'];
var loaded = { brief: true };
var cache  = {};
var tabs = Array.prototype.slice.call(document.querySelectorAll('.oew-tab'));
var DEFAULT_TICKER = window.OEW_DEFAULT_TICKER || 'SPY';
var curTicker = DEFAULT_TICKER;

function esc(s){
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function bi(en, zh){ return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(zh || en) + '</span>'; }
function num(v){ var n = parseFloat(v); return (v === null || v === undefined || isNaN(n)) ? null : n; }
function money(mn){
  var v = num(mn); if(v === null) return '—';
  var s = v < 0 ? '−' : '', a = Math.abs(v);
  if(a >= 1000) return s + '$' + (a/1000).toFixed(1) + 'B';
  if(a >= 1)    return s + '$' + a.toFixed(0) + 'M';
  return s + '$' + (a*1000).toFixed(0) + 'K';
}
function smoney(mn){ var v = num(mn); if(v === null) return '—'; return (v > 0 ? '+' : '') + money(v); }
function lvl(v){ var n = num(v); if(n === null) return '—';
  return (n % 1 === 0) ? n.toLocaleString('en-US') : n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function px(v){ var n = num(v); return n === null ? '—' : n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function pctv(v, d){ var n = num(v); return n === null ? '—' : n.toFixed(d === undefined ? 1 : d) + '%'; }

/* ---- skeleton + honest empty state ---- */
function skeleton(en, zh){
  return '<div class="oew-panel"><div class="oew-skel">'
    + '<div class="oew-skel-bar" style="width:32%"></div>'
    + '<div class="oew-skel-bar" style="width:88%"></div>'
    + '<div class="oew-skel-bar" style="width:76%"></div>'
    + '<div class="oew-skel-bar" style="width:81%"></div>'
    + '<div class="oew-skel-note">' + bi(en, zh) + '</div>'
    + '</div></div>';
}
function emptyPanel(en, zh){
  return '<div class="oew-panel"><div class="oew-pbody"><p class="oew-empty">' + bi(en, zh) + '</p></div></div>';
}
var SKEL = {
  flow:    ['Loading the flow desk for this close…', '正在加载本次收盘的资金流台…'],
  scanner: ['Loading the screener table for this close…', '正在加载本次收盘的筛选表…'],
  ticker:  ["Loading this name's options structure…", '正在加载该标的的期权结构…'],
  leaders: ['Loading the leader boards…', '正在加载领头股榜单…']
};

/* The Terminal destination, through the house helper.
   theme.js is the LAST body script, so window.MDXTerminal does NOT exist while
   this IIFE runs — every caller here is a render or a DOM-ready callback, by
   which time it does. The literal stays as the no-JS/helper-absent fallback:
   it reaches the Terminal, it just loses the &from=macro/&ret= stamp the
   Terminal reads to draw its "← Dashboard" button. gex.js already routes its
   own CTA this way (site/gex.js:528). The spelling this CTA used before was a
   parameter name the Terminal never read at all — its readers take `sym`
   (EmbeddedTerminalBridge.tsx:42, api/intraday/route.ts:60), which is what the
   helper emits. */
function terminalUrl(sym){
  try{
    if(window.MDXTerminal && window.MDXTerminal.url) return window.MDXTerminal.url(sym || '');
  }catch(e){}
  /* Fallback mirrors the helper's own shape (MM_TERMINAL_BASE is /terminal —
     theme.js:243) so a helper-absent visitor still lands on the workspace app,
     not the bare marketing origin. */
  return 'https://app.mastermind-x.com/terminal' + (sym ? '?sym=' + encodeURIComponent(sym) + '&from=macro' : '');
}

function getJSON(url){
  if(cache[url]) return Promise.resolve(cache[url]);
  return fetch(url, { credentials:'same-origin' }).then(function(r){
    if(!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(j){ cache[url] = j; return j; });
}

/* ══════════════════════════════════════════════════════════════════════════
   FLOW  (OIP W1.6-A · ONE_DOOR_RULING_AND_SPEC §2.1)
   The US Options Flow desk, absorbed. Four panels, in this order: the full
   sector desk · theme groups · sector-ETF money · the tide.

   ZERO STANCE CHIPS IN THIS MODE. Every panel closes with a caveat SENTENCE
   instead: Ticker mode's name header carries the page's one decision element
   (OIP_MASTERPLAN §3 verdict law), and a second verdict on a mode a reader
   reaches from the same tab strip is exactly the stacking that law exists to
   stop. Panels here state facts about where money went.

   Payload: flow_desk.json + flowdata/cohorts.json, both lazy (the same stores
   the Brief bake already reads — no new embeds). The tide's intraday overlay
   comes from the R2 tape store through window.DATA_BASE, the fetch discipline
   flow_desk.html.j2 already ships: null URL when the store is unset, .ok check,
   .catch(→ null), and an honest labelled absence on every failure path.
   ══════════════════════════════════════════════════════════════════════════ */
var flDesk = null, flTide = null;

function r2Url(path){
  var base = String((window && window.DATA_BASE) || '').replace(/\/+$/, '');
  return base ? base + '/' + path : null;
}
/* Canvas cannot resolve var(--up) — a colour has to be a resolved string at
   putImageData time — so the tide curves READ the tokens at draw time and
   redraw on 'langchange'. --up/--down swap to 红涨绿跌 in Chinese, and a cached
   colour would leave the curve encoding the wrong direction after the toggle.
   (The raw shelf below has the opposite problem and the better answer: SVG
   takes var() in an inline style, so it flips with no redraw at all.) */
function cssVar(name, fallback){
  try{
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v || '').trim() || fallback;
  }catch(e){ return fallback; }
}
function flMoney(mn){ return money(mn); }
function flSoft(mn){ var v = num(mn); return v === null ? '—' : '~' + smoney(v); }

/* ── panel 1 · every covered sector, shared scale, unusual days flagged ── */
function flSectorPanel(desk){
  var rows = ((desk && desk.sector_heatmap) || []).filter(function(r){
    return r && num(r.gross_premium_mn) !== null;
  }).sort(function(a,b){ return (num(b.gross_premium_mn)||0) - (num(a.gross_premium_mn)||0); });
  var head = '<div class="oew-phead">'
    + '<h2 class="oew-ph-title">' + bi('Premium by sector — the full desk','按板块的权利金 — 完整视图') + '</h2>'
    + '<span class="oew-ph-sub">' + bi('every covered sector, shared scale, unusual days flagged',
        '覆盖的全部板块，同一比例，异常日标旗') + '</span>'
    + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
      + ' data-tip-en="Every sector we cover, sorted by the options premium it drew today. Bars share one scale, so lengths compare directly. The tone chip is the buy/sell lean from the tape and is approximate; size is a solid read."'
      + ' data-tip-zh="我们覆盖的每个板块，按今日吸引的期权权利金排序。所有柱状图共用同一刻度，长度可直接比较。倾向标签为盘面推断的买卖方向，为近似值；规模数据可靠。">?</span></div>'
  + '</div>';
  if(!rows.length){
    return '<div class="oew-panel">' + head + '<div class="oew-pbody"><p class="oew-empty">'
      + bi('Sector premium did not report for this close. It returns with the next options tape.',
           '本次收盘没有板块权利金数据。下一次期权盘面数据到位后会恢复。') + '</p></div></div>';
  }
  var top = num(rows[0].gross_premium_mn) || 0;
  var body = rows.map(function(r){
    var g = num(r.gross_premium_mn) || 0;
    var w = top > 0 ? (g / top * 100) : 0;
    var tone = r.tone;
    var cls = tone === 'pos~' ? 'buy' : (tone === 'neg~' ? 'sell' : 'mix');
    var toneEn = tone === 'pos~' ? 'buying ~' : (tone === 'neg~' ? 'selling ~' : 'mixed');
    var toneZh = tone === 'pos~' ? '买入 ~' : (tone === 'neg~' ? '卖出 ~' : '混合');
    var z = num(r.premium_z);
    /* The ⚑ is a MARK, not a chip: the row already carries size and tone, and a
       filled pill here would read as a third reading on one line. */
    var flag = (z !== null && Math.abs(z) >= 1) ? '<span class="oew-fl-flag" role="img"'
      + ' data-tip-en="Today’s premium in this sector sits well outside its own recent range — an unusual day for it, not a direction call."'
      + ' data-tip-zh="该板块今日权利金明显偏离自身近期区间 — 对它而言是不寻常的一天，并非方向判断。">⚑</span>' : '';
    var n = num(r.n_names);
    var tipEn = flMoney(g) + ' of premium' + (n !== null ? ' across ' + n.toFixed(0) + ' names' : '')
      + '. Net ' + flSoft(r.net_premium_mn) + ' — size is a solid read, direction is approximate.';
    var tipZh = '权利金 ' + flMoney(g) + (n !== null ? '，覆盖 ' + n.toFixed(0) + ' 个标的' : '')
      + '。净额 ' + flSoft(r.net_premium_mn) + ' — 规模数据可靠，方向为近似值。';
    return '<div class="oew-sr" data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh) + '">'
      /* MA-2: the baked Brief translates the SAME rows through td(); a lazy
         mode must not flip the estate back to EN one tab away. Same-degrade
         contract: an unglossed name shows its English form in both languages.
         bi() escapes both halves itself. */
      + '<span class="oew-sr-name">' + flag
        + bi(r.sector || '—', (window.OEW_SECTOR_ZH || {})[r.sector] || r.sector || '—') + '</span>'
      + '<span class="oew-sr-track"><i class="oew-sr-fill ' + cls + '" style="width:' + w.toFixed(1) + '%"></i></span>'
      + '<span class="oew-sr-val mono">' + flMoney(g) + '</span>'
      + '<span class="tone ' + (cls === 'mix' ? '' : cls) + '">' + bi(toneEn, toneZh) + '</span>'
    + '</div>';
  }).join('');
  return '<div class="oew-panel">' + head
    + '<div class="oew-pbody"><div class="oew-sect">' + body + '</div></div>'
    + '<div class="oew-pfoot"><span>'
      + bi('A record of where options money went today — not a forecast of where it goes next.',
           '这是今日期权资金去向的记录，而非对后续走向的预测。') + '</span>'
      + (rows[0].asof ? '<span class="oew-asof mono">' + esc(rows[0].asof) + '</span>' : '')
    + '</div>'
  + '</div>';
}

/* ── panel 2 · theme groups (the four cohorts that cross sector lines) ── */
function flThemePanel(desk, cohorts){
  var rows = (cohorts && cohorts.cohorts) || (desk && desk.cohorts) || [];
  var head = '<div class="oew-phead">'
    + '<h2 class="oew-ph-title">' + bi('Theme groups','主题组合') + '</h2>'
    + '<span class="oew-ph-sub">' + bi('how the big themes traded as groups','大主题作为整体的交易情况') + '</span>'
    + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
      + ' data-tip-en="Four themes that cross sector lines. Premium size and the call/put tilt are solid reads; the net buy/sell mark is approximate. Watch for a group leaning the opposite way to the rest — that divergence is what these groups exist to surface."'
      + ' data-tip-zh="四个跨越行业边界的主题。权利金规模与看涨/看跌倾向为可靠读数；净买卖标记为近似值。留意与其余部分反向的组合 — 这种背离正是设立这些组合的意义所在。">?</span></div>'
  + '</div>';
  var covered = rows.filter(function(c){ return num(c.n_members_covered); }).length;
  if(!rows.length || !covered){
    return '<div class="oew-panel">' + head + '<div class="oew-pbody"><p class="oew-empty">'
      + bi('No theme-group data for this close. It returns with the next options tape.',
           '本次收盘没有主题组合数据。下一次期权盘面数据到位后会恢复。') + '</p></div></div>';
  }
  var tiles = rows.map(function(c){
    var net = num(c.net_premium_mn);
    var chips = '';
    if(c.pc_ratio !== null && c.pc_ratio !== undefined){
      chips += '<span class="tone ' + (c.pc_tone === 'call-tilted' ? 'buy' : (c.pc_tone === 'put-tilted' ? 'sell' : '')) + '">'
        + (c.pc_tone === 'call-tilted' ? bi('calls','偏看涨')
           : c.pc_tone === 'put-tilted' ? bi('puts','偏看跌') : bi('balanced','均衡')) + '</span>';
    }
    if(net !== null){
      chips += '<span class="tone ' + (c.net_tone === 'pos~' ? 'buy' : (c.net_tone === 'neg~' ? 'sell' : '')) + '">'
        + (c.net_tone === 'pos~' ? bi('net buy ~','净买 ~')
           : c.net_tone === 'neg~' ? bi('net sell ~','净卖 ~') : bi('flat ~','持平 ~')) + '</span>';
    }
    var cov = num(c.n_members_covered), tot = num(c.n_members);
    var sub = cov ? bi(cov.toFixed(0) + ' of ' + (tot === null ? '—' : tot.toFixed(0)) + ' covered',
                       '已覆盖 ' + cov.toFixed(0) + '/' + (tot === null ? '—' : tot.toFixed(0)))
                  : bi('no data today','今日无数据');
    return '<div class="oew-fl-tile">'
      + '<div class="nm">' + bi(c.name_en || c.key || '—', c.name_zh || c.name_en || c.key || '—') + '</div>'
      + '<div class="v ' + (net === null ? '' : (net >= 0 ? 'pos' : 'neg')) + ' mono">' + flSoft(net) + '</div>'
      + '<div class="chips">' + chips + '</div>'
      + '<div class="sub">' + sub + '</div>'
    + '</div>';
  }).join('');
  return '<div class="oew-panel">' + head
    + '<div class="oew-pbody"><div class="oew-fl-tiles">' + tiles + '</div></div>'
    + '<div class="oew-pfoot"><span>'
      + bi('Size is a solid read. Direction comes from tick-rule signing and is not reliable enough to read on its own.',
           '规模数据可靠。方向数据来自 tick 规则签署，其本身不足以作为方向依据。') + '</span>'
      + ((cohorts && cohorts.asof) ? '<span class="oew-asof mono">' + esc(cohorts.asof) + '</span>' : '')
    + '</div>'
  + '</div>';
}

/* ── panel 3 · the passive tape: 11 sector-ETF creation/redemption estimates ── */
function flEtfPanel(desk){
  var tile = (desk && desk.etf_tile) || null;
  var funds = (tile && tile.funds) || [];
  var head = '<div class="oew-phead">'
    + '<h2 class="oew-ph-title">' + bi('Sector ETF money','板块ETF资金') + '</h2>'
    + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
      + ' data-tip-en="Money moving in and out of the 11 sector SPDR funds, estimated from the daily change in shares outstanding times net asset value. The 5D and 21D figures are rolling sums over the same estimate."'
      + ' data-tip-zh="11只板块SPDR基金的资金进出，按流通份额日变化乘以净值估算。5D与21D为同一估算的滚动合计。">?</span></div>'
  + '</div>';
  if(!funds.length){
    return '<div class="oew-panel">' + head + '<div class="oew-pbody"><p class="oew-empty">'
      + bi('The sector-ETF estimate did not report for this close. It returns with the next fund update.',
           '本次收盘没有板块ETF估算数据。下一次基金数据更新后会恢复。') + '</p></div></div>';
  }
  var cards = funds.slice().sort(function(a,b){ return (num(b.flow_1d)||0) - (num(a.flow_1d)||0); })
    .map(function(f){
      var v = num(f.flow_1d);
      return '<div class="oew-etfc">'
        + '<div class="sym">' + esc(f.ticker || '—') + '</div>'
        + '<div class="v ' + (v === null ? '' : (v >= 0 ? 'pos' : 'neg')) + ' mono">' + flSoft(v) + '</div>'
        + '<div class="oew-fl-etfh mono">5D ' + flSoft(f.flow_5d) + ' · 21D ' + flSoft(f.flow_21d) + '</div>'
      + '</div>';
    }).join('');
  return '<div class="oew-panel">' + head
    + '<div class="oew-pbody"><div class="oew-etf oew-fl-etf">' + cards + '</div></div>'
    + '<div class="oew-pfoot"><span>'
      + bi('Estimates from share-count changes, not reported fund flows — a background check, not a signal.',
           '根据份额变动推算的估算值，而非公布的基金流量 — 可作背景参考，不构成信号。') + '</span>'
      + (tile.asof ? '<span class="oew-asof mono">' + esc(tile.asof) + '</span>' : '')
    + '</div>'
  + '</div>';
}

/* ── panel 4 · the tide: 30 sessions of net premium + how today unfolded ── */
function flTidePanel(desk){
  var spark = ((desk && desk.market_tide) || {}).spark || [];
  var head = '<div class="oew-phead">'
    + '<h2 class="oew-ph-title">' + bi('The tide','资金潮汐') + '</h2>'
    + '<span class="oew-ph-sub">' + bi('thirty sessions of net premium, and how today unfolded',
        '三十个交易日的净权利金，以及今日的展开过程') + '</span>'
    + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
      + ' data-tip-en="Left: each session’s net options premium — call premium bought minus put premium bought — against a zero line. Right: the same measure minute by minute through the completed session, from the live tape store. Read the shape, not the level; direction is approximate."'
      + ' data-tip-zh="左：各交易日的净期权权利金（买入看涨减买入看跌），以零轴为基准。右：同一指标在已收盘交易时段内的逐分钟走势，数据来自实时盘面存储。请看形态而非绝对水平；方向为近似值。">?</span></div>'
  + '</div>';
  /* MI-1: fewer than two REAL observations cannot draw a curve — the canvas
     guard would leave a blank rectangle under an aria-label promising thirty
     sessions. Nulls are no-observation slots, so they don't count. */
  var realN = spark.filter(function(d){ return num(d.net_premium_mn) !== null; }).length;
  if(realN < 2){
    return '<div class="oew-panel">' + head + '<div class="oew-pbody"><p class="oew-empty">'
      + bi('No session history on file yet for the tide. It fills in as closes accrue.',
           '资金潮汐暂无历史场次记录。随着收盘场次积累会逐步填充。') + '</p></div></div>';
  }
  return '<div class="oew-panel">' + head
    + '<div class="oew-pbody"><div class="oew-fl-tide">'
      + '<div>'
        + '<div class="oew-fl-cvh">' + bi('Thirty sessions','近三十个交易日') + '</div>'
        + '<div class="oew-fl-cv"><canvas id="oew-fl-spark" role="img"'
          + ' aria-label="Net options premium over the last thirty sessions"></canvas></div>'
      + '</div>'
      + '<div>'
        + '<div class="oew-fl-cvh">' + bi('Today, minute by minute','今日逐分钟') + '</div>'
        + '<div id="oew-fl-unfold"><div class="oew-fl-null">'
          + bi('No intraday record for this session.','本场次暂无盘中记录。') + '</div></div>'
        + '<div class="oew-fl-read" id="oew-fl-read"></div>'
      + '</div>'
    + '</div></div>'
    + '<div class="oew-pfoot"><span>'
      + bi('Shape only. Direction is approximate ~ and this is never a buy or sell signal.',
           '仅供观察形态。方向为近似值 ~，从不构成买卖信号。') + '</span>'
      + (((desk && desk.market_tide) || {}).asof
          ? '<span class="oew-asof mono">' + esc(desk.market_tide.asof) + '</span>' : '')
    + '</div>'
  + '</div>';
}

/* Both curves are ZERO-ANCHORED: the baseline is 0, never the series minimum,
   because the SIGN is the read. Drawn once per paint — no animation, no loop. */
function flDrawSpark(){
  var cv = document.getElementById('oew-fl-spark');
  var spark = ((flDesk && flDesk.market_tide) || {}).spark || [];
  if(!cv || !cv.getContext || spark.length < 2) return;
  var W = cv.offsetWidth, H = cv.offsetHeight;
  if(!W || !H) return;
  var dpr = window.devicePixelRatio || 1, ctx = cv.getContext('2d');
  cv.width = W * dpr; cv.height = H * dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,W,H);
  var up = cssVar('--up','#45b873'), dn = cssVar('--down','#e06464'), line = cssVar('--line','#2a2f3a');
  /* null = the store has NO observation for that session (pre-history, or a gap).
     Those slots draw as absences — the 30-slot x-axis keeps its width so the
     window stays honest, but no line, fill or dot is invented across them. A
     real measured 0.0 is an observation and draws on the zero line. */
  var vals = spark.map(function(d){ return num(d.net_premium_mn); });
  var real = vals.filter(function(v){ return v !== null; });
  if(real.length < 2) return;                    // the labelled flat track stays
  var mx = Math.max.apply(null, real), mn = Math.min.apply(null, real);
  var top = Math.max(mx, 0), bot = Math.min(mn, 0), rng = (top - bot) || 1, pad = 5;
  function X(i){ return (i / (vals.length - 1)) * W; }
  function Y(v){ return H - pad - ((v - bot) / rng) * (H - pad * 2); }
  var zeroY = Y(0);
  /* contiguous non-null runs; each ≥2-point run gets its own fills + stroke */
  var runs = [], cur = null;
  vals.forEach(function(v, i){
    if(v === null){ cur = null; return; }
    if(!cur){ cur = { s:i, e:i }; runs.push(cur); } else { cur.e = i; }
  });
  ctx.beginPath(); ctx.moveTo(0, zeroY); ctx.lineTo(W, zeroY);
  ctx.strokeStyle = line; ctx.lineWidth = 1; ctx.setLineDash([3,3]); ctx.stroke(); ctx.setLineDash([]);
  runs.forEach(function(run){
    if(run.e === run.s){                          // singleton observation → dot only
      ctx.beginPath(); ctx.arc(X(run.s), Y(vals[run.s]), 2.2, 0, Math.PI*2);
      ctx.fillStyle = vals[run.s] >= 0 ? up : dn; ctx.fill();
      return;
    }
    [true,false].forEach(function(above){
      ctx.save(); ctx.beginPath();
      if(above) ctx.rect(0,0,W,zeroY); else ctx.rect(0,zeroY,W,H-zeroY);
      ctx.clip(); ctx.beginPath(); ctx.moveTo(X(run.s), zeroY);
      for(var i=run.s; i<=run.e; i++) ctx.lineTo(X(i), Y(vals[i]));
      ctx.lineTo(X(run.e), zeroY); ctx.closePath();
      ctx.globalAlpha = .20; ctx.fillStyle = above ? up : dn; ctx.fill(); ctx.restore();
    });
    ctx.beginPath();
    for(var i=run.s; i<=run.e; i++) i === run.s ? ctx.moveTo(X(i), Y(vals[i])) : ctx.lineTo(X(i), Y(vals[i]));
    ctx.strokeStyle = vals[run.e] >= 0 ? up : dn; ctx.lineWidth = 1.6; ctx.lineJoin = 'round'; ctx.stroke();
  });
  var lastRun = runs[runs.length - 1];
  if(lastRun){
    var li = lastRun.e;
    ctx.beginPath(); ctx.arc(X(li), Y(vals[li]), 2.6, 0, Math.PI*2);
    ctx.fillStyle = vals[li] >= 0 ? up : dn; ctx.fill();
  }
}
function flDrawUnfold(){
  var cv = document.getElementById('oew-fl-curve');
  var mins = (flTide && flTide.minutes) || [];
  if(!cv || !cv.getContext || mins.length < 2) return;
  var W = cv.offsetWidth, H = cv.offsetHeight;
  if(!W || !H) return;
  var dpr = window.devicePixelRatio || 1, ctx = cv.getContext('2d');
  cv.width = W * dpr; cv.height = H * dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,W,H);
  var up = cssVar('--up','#45b873'), dn = cssVar('--down','#e06464'), line = cssVar('--line','#2a2f3a');
  /* minutes[] carries CUMULATIVE ncp/npp, so the lean at each minute is ncp − npp. */
  var vals = mins.map(function(m){ return (num(m.ncp) || 0) - (num(m.npp) || 0); });
  var mx = Math.max.apply(null, vals), mn = Math.min.apply(null, vals);
  var top = Math.max(mx, 0), bot = Math.min(mn, 0), rng = (top - bot) || 1, pad = 5;
  function X(i){ return (i / (vals.length - 1)) * W; }
  function Y(v){ return H - pad - ((v - bot) / rng) * (H - pad * 2); }
  var zeroY = Y(0);
  [true,false].forEach(function(above){
    ctx.save(); ctx.beginPath();
    if(above) ctx.rect(0,0,W,zeroY); else ctx.rect(0,zeroY,W,H-zeroY);
    ctx.clip(); ctx.beginPath(); ctx.moveTo(X(0), zeroY);
    vals.forEach(function(v,i){ ctx.lineTo(X(i), Y(v)); });
    ctx.lineTo(X(vals.length-1), zeroY); ctx.closePath();
    ctx.globalAlpha = .20; ctx.fillStyle = above ? up : dn; ctx.fill(); ctx.restore();
  });
  ctx.beginPath(); ctx.moveTo(0, zeroY); ctx.lineTo(W, zeroY);
  ctx.strokeStyle = line; ctx.lineWidth = 1; ctx.setLineDash([3,3]); ctx.stroke(); ctx.setLineDash([]);
  var last = vals[vals.length-1];
  ctx.beginPath();
  vals.forEach(function(v,i){ i === 0 ? ctx.moveTo(X(i), Y(v)) : ctx.lineTo(X(i), Y(v)); });
  ctx.strokeStyle = last >= 0 ? up : dn; ctx.lineWidth = 1.7; ctx.lineJoin = 'round'; ctx.stroke();
  ctx.beginPath(); ctx.arc(X(vals.length-1), Y(last), 2.8, 0, Math.PI*2);
  ctx.fillStyle = last >= 0 ? up : dn; ctx.fill();
}
/* The intraday overlay. Absent store, unreachable file, or fewer than two
   minutes on record all land in the SAME place: the labelled flat track the
   panel already renders stays, and nothing else on the page changes. */
function flApplyTide(tide){
  var host = document.getElementById('oew-fl-unfold');
  var readEl = document.getElementById('oew-fl-read');
  var mins = (tide && tide.minutes) || [];
  if(!host || mins.length < 2) return;
  flTide = tide;
  var grossSum = 0, vals = mins.map(function(m){
    grossSum += Math.abs(num(m.gross) || 0);
    return (num(m.ncp) || 0) - (num(m.npp) || 0);
  });
  var last = vals[vals.length-1], peak = 0;
  vals.forEach(function(v){ if(Math.abs(v) > Math.abs(peak)) peak = v; });
  var peakAbs = Math.abs(peak);
  /* "Two-way" is an honest state, not a rounding artefact: a close inside 2% of
     the day's gross premium is noise, not a lean. (flow_desk's own rule.) */
  var flat = grossSum > 0 && Math.abs(last) < grossSum * 0.02;
  host.innerHTML = '<div class="oew-fl-cv"><canvas id="oew-fl-curve" role="img"'
    + ' aria-label="Net options premium through the completed session"></canvas></div>';
  if(readEl){
    var lean = flat ? bi('Two-way','多空均衡') : (last > 0 ? bi('Calls led','看涨主导') : bi('Puts led','看跌主导'));
    var shape;
    if(peakAbs > 0 && !flat && (last > 0) !== (peak > 0)) shape = bi('turned the other way during the day','盘中方向反转');
    else if(peakAbs > 0 && Math.abs(last) >= peakAbs * 0.95) shape = bi('the lean built right into the close','倾向持续加强至收盘');
    else if(peakAbs > 0 && Math.abs(last) < peakAbs * 0.6) shape = bi('it faded well off the day’s peak','较当日峰值明显回落');
    else shape = bi('it held one side most of the day','全天基本维持单边');
    readEl.innerHTML = '<span class="net ' + (flat ? '' : (last > 0 ? 'pos' : 'neg')) + ' mono">'
      + '~' + smoney(last / 1e6) + '</span><span>' + lean + '</span><span>· ' + shape + '</span>';
  }
  flDrawUnfold();
}
function renderFlow(host, desk, cohorts){
  if(!desk || !desk.sector_heatmap){
    host.innerHTML = emptyPanel('The flow desk did not report for this close. It returns with the next options tape.',
      '本次收盘没有资金流台数据。下一次期权盘面数据到位后会恢复。');
    return;
  }
  flDesk = desk;
  /* Section bands use the same .oew-sec-h idiom as Brief's baked sections —
     uppercase tracking in EN, dropped in zh by the existing CSS rule. */
  var flSecH = function(en, zh){ return '<div class="oew-sec-h"><h2>' + bi(en, zh) + '</h2></div>'; };
  host.innerHTML = flSecH('Where the money went', '资金去向') + flSectorPanel(desk)
    + flSecH('Who moved together', '谁在同步移动') + flThemePanel(desk, cohorts)
    + flSecH('The passive tape', '被动资金') + flEtfPanel(desk)
    + flSecH("The day's arc", '当日轨迹') + flTidePanel(desk);
  flDrawSpark();
  var url = r2Url('live_flow/tide_current.json');
  if(!url) return;                                   // no store configured — stay flat
  fetch(url, { cache:'no-cache' })
    .then(function(r){ return r.ok ? r.json() : null; })
    .catch(function(){ return null; })
    .then(function(t){ if(t){ try{ flApplyTide(t); }catch(e){} } });
}

/* ══════════ SCANNER ══════════ */
/* Column tuple: [view class, extra class, EN, ZH, sort key]. The sort key is the
   payload field the header sorts on — the same field the cell renders, so a
   column can never sort by something other than what it shows. */
var SC_COLS = [
  ['c-ovr','',       'Spot','现价','spot'],
  ['c-ovr','',       'IV 30d','30日隐波','iv30'],
  ['c-ovr','hide-sm','IV rank','隐波分位','iv_rank'],
  ['c-ovr','',       'Expected move','预期波幅','implied_move_30d'],
  ['c-ovr','hide-sm','Put/call OI','认沽认购持仓比','pc_oi'],
  ['c-ovr','hide-sm','Volume','成交量','volume'],
  ['c-ovr','',       'Premium','权利金','gross_premium_mn'],
  ['c-flow','',      'Net premium','净权利金','net_prem_mn'],
  ['c-flow','',      'Same-day share','当日到期占比','zerodte_share'],
  ['c-flow','hide-sm','Volume','成交量','volume'],
  ['c-flow','',      'Premium','权利金','gross_premium_mn'],
  ['c-pos','',       'Spot','现价','spot'],
  ['c-pos','',       'From flip','距翻转位','dist_to_flip_pct'],
  ['c-pos','hide-sm','Ceiling','上方墙','wall_up'],
  ['c-pos','hide-sm','Floor','下方墙','wall_down'],
  ['c-pos','',       'Behaviour','表现','gamma_regime'],
  ['','',            'Tone','方向','net_prem_tone'],
  ['','',            'Data age','数据新鲜度','asof']
];
/* Preset values are the options_screener page's OWN shipped thresholds — reused,
   never reinvented (templates/options_screener.html.j2 applyPreset). The seventh,
   put-heavy open interest, comes over with the same page's own predicate. */
var SC_PRESETS = [
  ['premium',  'Premium leaders','权利金居前'],
  ['volsurge', 'Volume surge','成交激增'],
  ['highrank', 'Expensive options','期权偏贵'],
  ['zerodte',  'Same-day heavy','当日到期为主'],
  ['putskew',  'Downside cover bid','下行保护受追捧'],
  ['nearflip', 'Near a flip level','接近翻转位'],
  ['putheavy', 'Put-heavy OI','认沽持仓偏重']
];
/* The range filters, ported from options_screener.html.j2:279-394. Labels are the
   COLUMN's own words wherever the field has a column (so the control reads like
   the thing it filters); the three fields with no column keep the screener's own
   shipped pair. `flip` is max-only and absolute, exactly as the screener has it. */
var SC_RANGES = [
  ['iv30',   'iv30',             'IV 30d','30日隐波'],
  ['ivrank', 'iv_rank',          'IV rank','隐波分位'],
  ['impl',   'implied_move_30d', 'Expected move','预期波幅'],
  ['pc',     'pc_oi',            'Put/call OI','认沽认购持仓比'],
  ['vol',    'volume',           'Volume','成交量'],
  ['prem',   'gross_premium_mn', 'Premium','权利金'],
  ['dte',    'zerodte_share',    'Same-day share','当日到期占比'],
  ['relvol', 'rel_volume',       'Rel vol ×','相对成交量×'],
  ['skew',   'skew_pp',          'Put-skew pp','认沽溢价pp'],
  ['ivsp',   'ivspread_pp',      'IV-spread pp','IV价差pp']
];
var SC_TONE_ORDER = { 'call-leaning':1, 'neutral':0, 'put-leaning':-1 };
var scRows = [], scPreset = 'premium', scSkew75 = null, scAsof = null;
/* idx is the header POSITION, not the key: three fields appear in two views
   each, and aria-sort must mark exactly one header, never both copies. */
function scSortDefault(){ return { key:'gross_premium_mn', dir:'desc', idx:7 }; }
var scSort = scSortDefault();

function ageCell(rowAsof, freshest){
  var d = 0;
  if(rowAsof && freshest && rowAsof !== freshest){
    d = Math.round((Date.parse(freshest) - Date.parse(rowAsof)) / 86400000);
    if(!(d > 0)) d = 1;
  }
  var on = d === 0 ? 3 : (d <= 3 ? 2 : 1);
  var tipEn = d === 0 ? 'From the latest close.'
    : 'The last complete options chain for this name is ' + d + ' day' + (d === 1 ? '' : 's') + ' old. Treat its levels as stale.';
  var tipZh = d === 0 ? '来自最新一次收盘。'
    : '该标的最近一次完整期权链已过去 ' + d + ' 天，其水位应视为陈旧。';
  var s = '<span class="oew-age"><span class="oew-pips sm" role="img" data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh) + '">';
  for(var i = 0; i < 3; i++) s += '<i class="oew-pip' + (i < on ? ' on' : '') + '"></i>';
  return s + '</span><span class="d' + (d > 3 ? ' stale' : '') + ' mono">' + d + 'd</span></span>';
}
function scPresetFilter(rows){
  if(scPreset === 'volsurge') return rows.filter(function(r){ return num(r.rel_volume) !== null && num(r.rel_volume) >= 2; });
  if(scPreset === 'highrank') return rows.filter(function(r){ return num(r.iv_rank) !== null && num(r.iv_rank) >= 80; });
  if(scPreset === 'zerodte')  return rows.filter(function(r){ return num(r.zerodte_share) !== null && num(r.zerodte_share) >= 60; });
  if(scPreset === 'nearflip') return rows.filter(function(r){ var d = num(r.dist_to_flip_pct); return d !== null && Math.abs(d) <= 1; });
  if(scPreset === 'putheavy') return rows.filter(function(r){ return num(r.pc_oi) !== null && num(r.pc_oi) >= 1.5; });
  if(scPreset === 'putskew'){
    if(scSkew75 === null){
      var vals = rows.map(function(r){ return num(r.skew_pp); }).filter(function(v){ return v !== null; }).sort(function(a,b){ return a-b; });
      /* the screener writes skew75.toFixed(1) into its input and compares
         against THAT — round the same way so both pages admit identical rows */
      scSkew75 = vals.length ? Math.round(vals[Math.floor(vals.length * 0.75)] * 10) / 10 : 0;
    }
    return rows.filter(function(r){ return num(r.skew_pp) !== null && num(r.skew_pp) >= scSkew75; });
  }
  return rows.slice();
}
/* A range input reads NaN when empty or unparseable, and NaN comparisons are all
   false — which is exactly the "no bound set" behaviour, and why every check
   below is guarded by !isNaN rather than by a truthiness test (0 is a real
   bound). A row missing the field fails an ACTIVE bound: a null is not a zero
   and must not slip through a filter the reader set. */
function scInputNum(id){
  var el = document.getElementById(id);
  return el ? parseFloat(el.value) : NaN;
}
function scInputStr(id){
  var el = document.getElementById(id);
  return el ? String(el.value || '').trim() : '';
}
function scRangeFilter(rows){
  var q = scInputStr('oew-f-q').toUpperCase();
  var sector = scInputStr('oew-f-sector');
  var flipMax = scInputNum('oew-f-flip-max');
  var bounds = SC_RANGES.map(function(R){
    return [R[1], scInputNum('oew-f-' + R[0] + '-min'), scInputNum('oew-f-' + R[0] + '-max')];
  });
  return rows.filter(function(r){
    if(q && String(r.ticker || '').toUpperCase().indexOf(q) === -1
         && String(r.sector || '').toUpperCase().indexOf(q) === -1) return false;
    if(sector && r.sector !== sector) return false;
    for(var i = 0; i < bounds.length; i++){
      var key = bounds[i][0], lo = bounds[i][1], hi = bounds[i][2];
      if(isNaN(lo) && isNaN(hi)) continue;
      var v = num(r[key]);
      if(v === null) return false;
      if(!isNaN(lo) && v < lo) return false;
      if(!isNaN(hi) && v > hi) return false;
    }
    if(!isNaN(flipMax)){
      var d = num(r.dist_to_flip_pct);
      if(d === null || Math.abs(d) > flipMax) return false;
    }
    return true;
  });
}
/* Preset FIRST, then the ranges — the composition the spec pins, and the order a
   reader expects: the chip picks the population, the ranges narrow it. */
function scFilter(rows){ return scRangeFilter(scPresetFilter(rows)); }
function scSortRows(rows){
  var col = scSort.key, dir = scSort.dir;
  return rows.slice().sort(function(a, b){
    var av = a[col], bv = b[col];
    if(av === null || av === undefined){ return (bv === null || bv === undefined) ? 0 : 1; }
    if(bv === null || bv === undefined) return -1;
    if(col === 'net_prem_tone'){
      var ao = SC_TONE_ORDER[av] === undefined ? 0 : SC_TONE_ORDER[av];
      var bo = SC_TONE_ORDER[bv] === undefined ? 0 : SC_TONE_ORDER[bv];
      return dir === 'desc' ? bo - ao : ao - bo;
    }
    if(num(av) === null || num(bv) === null){
      return dir === 'desc' ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv));
    }
    return dir === 'desc' ? num(bv) - num(av) : num(av) - num(bv);
  });
}
function scVisibleRows(){ return scSortRows(scFilter(scRows)); }
function scBody(){
  /* NO SLICE. Every screened name on file renders — the cap this line used to
     carry is what the subtitle now declares away ("All N screened names"), and a
     truncation a reader cannot see is the exact defect the declared-cap sentence
     existed to work around. */
  var rows = scVisibleRows();
  if(!rows.length) return '<tr><td colspan="19" class="left"><span class="oew-empty">'
    + bi('No name in this close matched that view. Pick another chip, or clear the filters below.',
         '本次收盘没有符合该视图的标的。可选择其他标签，或清除下方筛选。')
    + '</span></td></tr>';
  return rows.map(function(r){
    var toneCall = String(r.net_prem_tone || '').indexOf('call') === 0;
    var toneZh = toneCall ? '偏看涨' : (String(r.net_prem_tone||'').indexOf('put') === 0 ? '偏看跌' : '双向');
    var toneEn = toneCall ? 'call-leaning' : (String(r.net_prem_tone||'').indexOf('put') === 0 ? 'put-leaning' : 'two-sided');
    var jumpy = r.gamma_regime === 'short';
    var vol = num(r.volume);
    var volS = vol === null ? '—' : (vol >= 1e6 ? (vol/1e6).toFixed(1) + 'M' : (vol/1e3).toFixed(0) + 'K');
    function td(cls, k, kz, v){ return '<td class="' + cls + '" data-k="' + esc(k) + '" data-k-zh="' + esc(kz) + '">' + v + '</td>'; }
    return '<tr>'
      + '<td class="left"><button class="oew-sc-tk mono" type="button" data-goto="' + esc(r.ticker) + '">'
        + esc(r.ticker) + '<span class="go">→</span></button>'
        + '<span class="oew-sec"> ' + esc(r.sector || '') + '</span></td>'
      + td('c-ovr mono','Spot','现价', '$' + px(r.spot))
      + td('c-ovr mono','IV 30d','30日隐波', pctv(r.iv30))
      + td('c-ovr mono hide-sm','IV rank','隐波分位', num(r.iv_rank) === null ? '—' : num(r.iv_rank).toFixed(0))
      + td('c-ovr mono','Expected move','预期波幅', num(r.implied_move_30d) === null ? '—' : '±' + pctv(r.implied_move_30d))
      + td('c-ovr mono hide-sm','Put/call OI','认沽认购持仓比', num(r.pc_oi) === null ? '—' : num(r.pc_oi).toFixed(2) + 'x')
      + td('c-ovr mono hide-sm','Volume','成交量', volS)
      + td('c-ovr mono','Premium','权利金', money(r.gross_premium_mn))
      + td('c-flow mono','Net premium','净权利金', smoney(r.net_prem_mn))
      + td('c-flow mono','Same-day share','当日到期占比', num(r.zerodte_share) === null ? '—' : num(r.zerodte_share).toFixed(0) + '%')
      + td('c-flow mono hide-sm','Volume','成交量', volS)
      + td('c-flow mono','Premium','权利金', money(r.gross_premium_mn))
      + td('c-pos mono','Spot','现价', '$' + px(r.spot))
      + td('c-pos mono','From flip','距翻转位', num(r.dist_to_flip_pct) === null ? '—' : pctv(r.dist_to_flip_pct))
      + td('c-pos mono hide-sm','Ceiling','上方墙', lvl(r.wall_up))
      + td('c-pos mono hide-sm','Floor','下方墙', lvl(r.wall_down))
      + td('c-pos','Behaviour','表现', r.gamma_regime ? bi(jumpy ? 'jumpy' : 'calm', jumpy ? '剧烈' : '平静') : '—')
      + td('','Tone','方向', '<span class="tone ' + (toneCall ? 'buy' : (toneEn === 'put-leaning' ? 'sell' : '')) + '">' + bi(toneEn, toneZh) + '</span>')
      + td('','Data age','数据新鲜度', ageCell(r.asof, scAsof))
      + '</tr>';
  }).join('');
}
/* MI-5: sort identity is the KEY, not the header position — three fields
   render a header in two views each, and position-keyed aria lost the arrow
   (and announced "none") the moment the reader switched views while sorted.
   Key-marking lights both copies, of which exactly one is visible per view. */
function scAria(key){
  return ' aria-sort="' + (scSort.key === key ? (scSort.dir === 'asc' ? 'ascending' : 'descending') : 'none') + '"';
}
function scHead(){
  var h = '<th class="left" data-sort="ticker" data-i="0" tabindex="0"' + scAria('ticker') + '>' + bi('Name','标的') + '</th>';
  SC_COLS.forEach(function(c, i){
    h += '<th class="' + c[0] + (c[1] ? ' ' + c[1] : '') + '" data-sort="' + c[4] + '" data-i="' + (i + 1) + '"'
      + ' tabindex="0"' + scAria(c[4]) + '>' + bi(c[2], c[3]) + '</th>';
  });
  return h;
}
/* The collapsed "More filters" disclosure. Operates on the rows ALREADY fetched —
   no second request, no server round trip. */
function scFiltersHTML(rows){
  var sectors = {}, opts = '';
  rows.forEach(function(r){ if(r.sector) sectors[r.sector] = 1; });
  Object.keys(sectors).sort().forEach(function(s){
    opts += '<option value="' + esc(s) + '">' + esc(s) + '</option>';
  });
  var ranges = SC_RANGES.map(function(R){
    return '<label class="oew-sc-f">' + bi(R[2], R[3]) + '<span class="oew-sc-pair">'
      + '<input type="number" id="oew-f-' + R[0] + '-min" step="any" aria-label="' + esc(R[2]) + ' minimum">'
      + '<span class="sep">–</span>'
      + '<input type="number" id="oew-f-' + R[0] + '-max" step="any" aria-label="' + esc(R[2]) + ' maximum">'
      + '</span></label>';
  }).join('');
  return '<details class="oew-sc-more" id="oew-sc-more">'
    + '<summary>' + bi('More filters — ranges, sector, text','更多筛选 — 数值区间、板块、文本') + '</summary>'
    + '<div class="oew-sc-fgrid">'
      + '<label class="oew-sc-f wide">' + bi('Name or sector','标的或板块')
        + '<input type="text" id="oew-f-q" autocomplete="off" spellcheck="false"'
        + ' placeholder="Filter ticker or sector…" data-ph-zh="按代码或板块筛选…"></label>'
      + '<label class="oew-sc-f">' + bi('Sector','板块')
        + '<select id="oew-f-sector"><option value="" data-en="All sectors" data-zh="全部板块">All sectors</option>'
        + opts + '</select></label>'
      + ranges
      + '<label class="oew-sc-f">' + bi('From flip','距翻转位') + '<span class="oew-sc-pair">'
        + '<input type="number" id="oew-f-flip-max" step="any" min="0" aria-label="Distance from flip, maximum">'
        + '</span></label>'
    + '</div>'
    + '<div class="oew-sc-fbar">'
      + '<button class="oew-sc-clear" type="button" id="oew-f-clear">' + bi('Clear all','清除全部') + '</button>'
    + '</div>'
  + '</details>';
}
/* Repaint after a preset, a filter or a sort. The thead is re-rendered too: the
   sort arrow is drawn from aria-sort, so the two can never disagree. */
/* The subtitle in both of its honest states: untouched board → the population;
   any preset/range narrowing → shown-of-total plus the way back. */
function scSubHTML(shown, total){
  if(shown >= total){
    return '<span class="l-en">All <b class="mono">' + total + '</b> screened names — sort any column, filter below.</span>'
         + '<span class="l-zh">全部 <b class="mono">' + total + '</b> 个筛选标的 — 可按列排序、下方筛选。</span>';
  }
  return '<span class="l-en"><b class="mono">' + shown + '</b> of <b class="mono">' + total + '</b> shown — clear filters to see all.</span>'
       + '<span class="l-zh">显示 <b class="mono">' + shown + '</b> / <b class="mono">' + total + '</b> — 清除筛选可查看全部。</span>';
}
function scRepaint(){
  var body = document.getElementById('oew-sc-body');
  if(body) body.innerHTML = scBody();
  var head = document.getElementById('oew-sc-head');
  if(head) head.innerHTML = scHead();
  var sub = document.getElementById('oew-sc-sub');
  if(sub) sub.innerHTML = scSubHTML(scVisibleRows().length, scRows.length);
}
/* CSV of what is on screen — the filtered, sorted rows, every field the payload
   carries. Same Blob pattern the screener page ships. */
function scExportCSV(){
  var rows = scVisibleRows();
  if(!rows.length) return;
  var keys = Object.keys(rows[0]);
  var lines = [keys.join(',')];
  rows.forEach(function(r){
    lines.push(keys.map(function(k){
      var v = r[k];
      if(v === null || v === undefined) return '';
      var s = String(v);
      if(s.indexOf(',') > -1 || s.indexOf('"') > -1 || s.indexOf('\n') > -1) s = '"' + s.replace(/"/g,'""') + '"';
      return s;
    }).join(','));
  });
  var url = URL.createObjectURL(new Blob([lines.join('\n')], { type:'text/csv' }));
  var a = document.createElement('a');
  a.href = url;
  a.download = 'options_scanner_' + (scAsof || new Date().toISOString().slice(0,10)) + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}
/* <option> and placeholder cannot hold the l-en/l-zh dual span, so they are
   single-language markup relabelled on theme.js's own 'langchange' event — the
   options_screener page's shipped pattern. */
function scApplyLang(){
  var zh = document.documentElement && document.documentElement.getAttribute('data-lang') === 'zh';
  var q = document.getElementById('oew-f-q');
  if(q) q.placeholder = zh ? (q.getAttribute('data-ph-zh') || q.placeholder) : 'Filter ticker or sector…';
  var opts = document.querySelectorAll('#oew-f-sector option[data-zh]');
  Array.prototype.forEach.call(opts, function(o){
    o.textContent = zh ? o.getAttribute('data-zh') : (o.getAttribute('data-en') || o.textContent);
  });
}
function renderScanner(host, payload){
  var rows = (payload && payload.rows) || [];
  if(!rows.length){
    host.innerHTML = emptyPanel('The screener export is empty for this close. It returns with the next options snapshot.',
      '本次收盘的筛选导出为空。下一次期权快照到位后会恢复。');
    return;
  }
  scRows = rows; scSkew75 = null;
  scAsof = rows.map(function(r){ return r.asof; }).filter(Boolean).sort().pop() || null;
  var presets = SC_PRESETS.map(function(p){
    return '<button class="oew-preset" type="button" data-preset="' + p[0] + '" aria-pressed="' + (p[0] === scPreset) + '">'
      + bi(p[1], p[2]) + '</button>';
  }).join('');
  host.innerHTML = ''
    + '<div class="oew-sc-bar">' + presets + '</div>'
    + '<div class="oew-panel">'
      + '<div class="oew-phead">'
        + '<h2 class="oew-ph-title">' + bi('Screener','筛选台') + '</h2>'
        // The cap is GONE (scBody no longer slices), so the subtitle no longer
        // has to declare one — it states the population and the two controls
        // that work on it. The old conditional "Top 200" wording, and the
        // "open the full screener" link that existed to escape that cap, retire
        // with the truncation itself: nothing is withheld here any more.
        // BL-2: the count is LIVE (scRepaint rewrites it) — a preset or range
        // narrows the table, and a static "All 403" over 27 visible rows would
        // misdescribe both the board and the CSV the button exports.
        + '<span class="oew-ph-sub" id="oew-sc-sub">' + scSubHTML(rows.length, rows.length) + '</span>'
        + '<span class="oew-help" tabindex="0" role="button"'
          + ' data-tip-en="Chains are snapshots taken after the close. Implied volatility, walls and max-pain come from those snapshots; volume and premium come from the day’s tape. IV rank compares today with the history we hold for that name, so a name we have tracked only briefly has a short history behind its number. Direction is approximate; size is reliable."'
          + ' data-tip-zh="期权链为收盘后的快照。隐含波动率、墙位与最大痛点来自这些快照；成交量与权利金来自当日逐笔。隐波分位将今日与我们持有的该标的历史比较，因此跟踪时间较短的标的，其数字背后的历史也较短。方向为近似值，规模数据可靠。">?</span>'
        + '<div class="oew-ph-right"><span class="oew-seg">'
          + '<button type="button" data-view="ovr" aria-pressed="true">' + bi('Overview','总览') + '</button>'
          + '<button type="button" data-view="flow" aria-pressed="false">' + bi('Flow','资金') + '</button>'
          + '<button type="button" data-view="pos" aria-pressed="false">' + bi('Positioning','持仓结构') + '</button>'
        + '</span>'
        + '<button class="oew-sc-csv" type="button" id="oew-sc-csv">' + bi('Export CSV','导出CSV') + '</button>'
        + '</div>'
      + '</div>'
      + scFiltersHTML(rows)
      + '<div class="tbl-scroll oew-tblwrap"><table class="oew-tbl" data-view="ovr">'
        + '<thead><tr id="oew-sc-head">' + scHead() + '</tr></thead><tbody id="oew-sc-body">' + scBody() + '</tbody>'
      + '</table></div>'
      + '<div class="oew-pfoot">'
        + '<span class="oew-stance st-aside">' + bi('Stand aside','暂时观望') + '</span>'
        + '<span>' + bi('A screen is a starting list, not a ranking. Nothing here is scored or ordered by expected return.',
            '筛选结果是起始清单，而非排名。此处没有任何内容按预期收益评分或排序。') + '</span>'
        + (scAsof ? '<span class="oew-asof mono">' + esc(scAsof) + '</span>' : '')
      + '</div>'
    + '</div>';
  scApplyLang();
}

/* ══════════ TICKER ══════════ */
var REGIME_HEAD = {
  'long':  ['Calm — moves get damped', '平静 — 波动被抑制'],
  'short': ['Jumpy — moves get amplified', '剧烈 — 波动被放大']
};
var REGIME_SAY = {
  'long':  ['Dealer hedging is trading against the market today, so dips tend to get bought back and swings stay contained.',
            '今日做市商对冲与市场反向，因此回调通常被买回，波动幅度受限。'],
  'short': ['Dealer hedging is trading with the market today, so swings run larger and sell-offs can pick up speed. Do not assume dips get bought back the way they do on calm days.',
            '今日做市商对冲与市场同向，因此波动更大，抛售可能加速。不要想当然地认为回调会像平静日那样被买回。']
};
function pipRow(strength){
  var on = strength === null ? 0 : Math.max(1, Math.min(5, Math.round(strength / 20)));
  var tipEn = strength === null ? 'Wall strength did not report for this level.'
    : 'Wall strength ' + on + ' of 5 — how much dealer gamma sits at this strike relative to the others on the board.';
  var tipZh = strength === null ? '该水位的墙位强度无数据。'
    : '墙位强度 5 格中第 ' + on + ' 格 — 该行权价的做市商 Gamma 相对板上其他水位的大小。';
  var s = '<span class="oew-pips sm" role="img" data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh) + '">';
  for(var i = 0; i < 5; i++) s += '<i class="oew-pip' + (i < on ? ' on' : '') + '"></i>';
  return s + '</span>';
}
function lvRow(color, en, zh, sEn, sZh, strength, spot, value, wcheck){
  var v = num(value), sp = num(spot);
  var d = (v !== null && sp) ? ((v - sp) / sp * 100) : null;
  return '<div class="oew-lvrow">'
    + '<span class="oew-lv-sw" style="background:' + color + '"></span>'
    + '<span class="oew-lv-main"><span class="n">' + bi(en, zh) + pipRow(strength) + (wcheck || '') + '</span>'
      + '<span class="s">' + bi(sEn, sZh) + '</span></span>'
    + '<span class="oew-lv-pct mono">' + (d === null ? '—' : (d >= 0 ? '+' : '−') + Math.abs(d).toFixed(1) + '% ')
      + bi('from close', '距收盘') + '</span>'
    + '<span class="oew-lv-px mono">' + lvl(value) + '</span>'
  + '</div>';
}
/* OIP W1 §4: the wall-persistence cross-check chip — a calm confirm/disagree/no-data
   mark, NOT a stance and not a pip (§0.6). Silent (returns '') when the block is
   absent (coverage gap, PR #3976) or matches_board_wall is null (either side
   unreadable) — no chip at all on that row, never a "no data" placeholder. Flip and
   Magnet have no open-interest-wall equivalent, so callers only pass this for the
   Ceiling/Floor rows. */
function wcheckChip(gx, side, ownValue){
  var wp = gx && gx.wall_persistence; if(!wp) return '';
  var block = side === 'call' ? wp.call_side : wp.put_side;
  if(!block || block.matches_board_wall === null || block.matches_board_wall === undefined) return '';
  if(block.matches_board_wall){
    return '<span class="oew-wcheck oew-wcheck-yes"'
      + ' data-tip-en="The open-interest wall (a signing-free count of contracts, independent of the dealer-gamma model) sits at the same strike as this dealer-gamma wall — two different measurements agree."'
      + ' data-tip-zh="未平仓量墙位（合约数量统计，不依赖做市商模型的独立测算）与该做市商Gamma墙位落在同一行权价 — 两种独立测算结果一致。">'
      + '✓ <span class="l-en">confirmed by open interest</span><span class="l-zh">未平仓量印证</span></span>';
  }
  // B2 fix: block.board_wall is the SAME dealer-gamma wall as ownValue (it exists
  // only as the comparison operand matches_board_wall was computed against —
  // engine/gex_state.py's _wall_persistence sets it from the model's own
  // call_wall/put_wall, the identical value this row already shows). The
  // independent open-interest wall this chip exists to surface is block.level.
  var oiw = '$' + lvl(block.level), own = '$' + lvl(ownValue);
  return '<span class="oew-wcheck oew-wcheck-no"'
    + ' data-tip-en="The open-interest wall sits at a different strike (' + oiw + ') than this dealer-gamma wall (' + own + '). Two independent measurements, two different answers — worth knowing, not a contradiction to resolve."'
    + ' data-tip-zh="未平仓量墙位（' + oiw + '）与该做市商Gamma墙位（' + own + '）不在同一行权价 — 两种独立测算给出不同答案，值得留意，但并非需要解决的矛盾。">'
    + '<span class="l-en">open interest disagrees</span><span class="l-zh">未平仓量不一致</span></span>';
}
function rdCard(hEn, hZh, vEn, vZh, sEn, sZh){
  return '<div class="oew-panel"><div class="oew-pbody">'
    + '<div class="oew-eyebrow">' + bi(hEn, hZh) + '</div>'
    + '<div class="oew-rd-v">' + bi(vEn, vZh) + '</div>'
    + '<div class="oew-rd-s">' + bi(sEn, sZh) + '</div>'
  + '</div></div>';
}
function mt(kEn, kZh, v){
  return '<span class="oew-mt"><span class="k">' + bi(kEn, kZh) + '</span><span class="v mono">' + esc(v) + '</span></span>';
}
/* ── OIP W1 §3.5: the session filmstrip panel — "How the day traded" ──
   The <figure> itself is an SSR fragment lib/illus.py baked into
   site/session/<T>.json's filmstrip_html field at nightly build time (§3.1: never
   re-derive the geometry client-side). sess is null when the fetch 404s or hasn't
   resolved (a name outside the digest's coverage, or before the first nightly run
   populates the store) — that degrades to the SAME honest-null figure the server
   emits for coverage.minutes===0, composed here only because there is no record at
   all to read a pre-rendered field from. NO stance chip (§0.13 ruling) — this is
   not the verdict surface; the Name-header panel above carries the page's one
   verdict-marker decision element (OIP_MASTERPLAN §3 verdict law). */
var FILM_NULL_HTML = '<figure class="ilx oew-film oew-film-null" role="img" '
  + 'aria-label="No intraday record for this session" style="color:var(--oew-accent);--ilx-h:64px">'
  + '<svg viewBox="0 0 560 64" preserveAspectRatio="none" aria-hidden="true">'
  + '<line class="oew-film-track" x1="0" y1="32" x2="560" y2="32"/>'
  + '<line class="oew-film-closecap" x1="560" y1="14" x2="560" y2="50"/></svg>'
  + '<span class="oew-film-empty"><span class="l-en">No intraday record for this session</span>'
  + '<span class="l-zh">本交易日没有盘中记录</span></span></figure>';
function filmCount(n){
  if(n === 1) return ['once','一次'];
  if(n === 2) return ['twice','两次'];
  return [n + ' times', n + '次'];
}
function filmstripSentence(sess){
  var cov = (sess && sess.coverage) || null;
  if(!cov) return bi('No intraday record for this session', '本交易日没有盘中记录');
  var minutes = num(cov.minutes) || 0;
  if(minutes === 0) return bi(cov.quality_en || 'No intraday record for this session', cov.quality_zh || '本交易日没有盘中记录');
  var expected = num(cov.expected);
  var ratio = expected ? minutes / expected : null;
  var shapeEn = sess.arc_shape_en || '', shapeZh = sess.arc_shape_zh || '';
  if(ratio !== null && ratio < 0.70){
    return bi((cov.quality_en || '') + (shapeEn ? ' — Premium ' + shapeEn + '.' : ''),
               (cov.quality_zh || '') + (shapeZh ? '——权利金' + shapeZh + '。' : ''));
  }
  var flip = sess.flip || {}, crosses = num(flip.crosses) || 0, flipEn = '', flipZh = '';
  var side = flip.last_side === 'above' ? ['above','上方'] : flip.last_side === 'below' ? ['below','下方'] : null;
  if(crosses > 0 && side){
    var c = filmCount(crosses);
    flipEn = ' Crossed the flip ' + c[0] + ', closed ' + side[0] + ' it.';
    // NOT a leading '，' — shapeZh below already ends its own sentence in '。'
    // (worked example, W1_DESIGN_SPEC.md §3.4: "...并维持。穿越翻转位两次...",
    // period then directly 穿越, never '。，' — a leading comma there would
    // collide with that full stop).
    flipZh = '穿越翻转位' + c[1] + '，收于其' + side[1] + '。';
  }
  return bi((shapeEn ? 'Premium ' + shapeEn + '.' : '') + flipEn,
             (shapeZh ? '权利金' + shapeZh + '。' : '') + flipZh);
}
function filmstripPanelHTML(sess){
  var fig = (sess && sess.filmstrip_html) ? sess.filmstrip_html : FILM_NULL_HTML;
  // M1 fix: the null figure (client FILM_NULL_HTML above, or the server's own
  // honest-null filmstrip_html) already embeds this exact disclosure in its own
  // .oew-film-empty span (§3.3's markup contract). filmstripSentence() returns
  // the SAME text for the same condition (!cov or minutes===0), so printing it
  // again in the footer doubled it. Suppress the footer sentence for that one
  // condition only — every other state keeps it (the figure carries no prose
  // there). The as-of stamp is independent of this and still prints whenever a
  // real record (any coverage) is on hand.
  var cov = (sess && sess.coverage) || null;
  // Minor fix (PR #4123 adversarial review round 2): must use the exact same
  // numeric-safe predicate as filmstripSentence()'s own `minutes === 0` check
  // just above, never a bare truthiness read of cov.minutes — a future string
  // "0" is truthy in JS ("0" would NOT satisfy !cov.minutes) and would silently
  // re-open the M1 duplication this suppression exists to prevent.
  var isNull = !cov || (num(cov.minutes) || 0) === 0;
  var footBits = (isNull ? '' : '<span>' + filmstripSentence(sess) + '</span>')
    + (sess && sess.session_date ? '<span class="oew-asof mono">' + esc(sess.session_date) + '</span>' : '');
  return '<div class="oew-panel">'
    + '<div class="oew-phead"><h2 class="oew-ph-title">' + bi('How the day traded','今日如何交易') + '</h2></div>'
    + '<div class="oew-pbody" id="oew-film-body">' + fig + '</div>'
    + (footBits ? '<div class="oew-pfoot">' + footBits + '</div>' : '')
  + '</div>';
}

/* ── OIP W1 §5.2: "Rich or cheap?" — real read, young-window honesty ──
   Band WORDS reused VERBATIM from gex.js's own IVRANK map (site/gex.js:76-80) —
   never invented here. The COLORS are deliberately NOT verbatim: gex.js resolves
   its own cls ("down"/"up"/"warn"/"neu") to var(--down)/var(--up) downstream
   (moodReadHTML), which is itself a §0.5 violation on that page (pre-existing,
   out of scope for this file) — a non-directional vol level must never reach
   --up/--down, since site/theme.css flips that pair under ZH and the same
   reading would render red in EN and green in ZH. IV rank is not one of the
   two sanctioned direction instruments (tape_flow, ΔOI — masterplan §0.8), so
   every band below stays in the warn/accent/muted family.

   Minor, intentional (PR #4123 adversarial review round 2): `normal` and
   `cheap` both resolve to var(--muted) — this is a deliberate 4-WEIGHT visual
   ladder (warn > orange > muted > accent), not a bug in a would-be 5-color
   one. The two middle bands share a word (gex.js's own verbatim mapping keeps
   them textually distinct) but not a color, because neither "unremarkably
   normal" nor "somewhat cheap" is worth a dedicated visual weight next to the
   two bands that actually call for attention (rich, and genuinely very
   cheap) — and the constraint above already rules out reaching for --up/--down
   to manufacture a fifth one. If a future pass wants 5 distinct weights,
   pick a new non-directional color for one of these two explicitly; do not
   read the shared var(--muted) as an oversight. */
var IVR_BAND = {
  rich:      ['Vol rich','波动偏贵','var(--warn)'],
  elevated:  ['Elevated','偏高','var(--orange)'],
  normal:    ['Normal','正常','var(--muted)'],
  cheap:     ['Cheap','偏低','var(--muted)'],
  very_cheap:['Very cheap','便宜','var(--oew-accent)']
};
function filmOrdinal(n){
  var s = ['th','st','nd','rd'], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
function richOrCheapHTML(tk, gx){
  var ivr = (gx.summary || {}).iv_rank;
  var head = '<div class="oew-phead"><h2 class="oew-ph-title">' + bi('Rich or cheap?','偏贵还是偏便宜？') + '</h2>'
    + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
      + ' data-tip-en="Where today’s 30-day implied volatility sits versus this name’s own recent daily readings. This is a SHORT window (about 40 trading days) — not a full-year IV rank. A young or thin window is flagged, not hidden."'
      + ' data-tip-zh="今日30日隐含波动率相对该标的近期每日读数的位置。这是一个较短窗口（约40个交易日）— 并非完整一年的隐波分位。窗口较短或较薄时会明确标注，而非隐藏。">?</span></div>'
  + '</div>';
  if(!ivr){
    return '<div class="oew-panel">' + head
      + '<div class="oew-pbody"><div class="oew-notyet"><p class="oew-notyet-say">' + bi(
          "Not enough price history on file yet for this name to place today's cost against its own past.",
          '该标的历史价格记录不足，暂无法将今日成本与自身历史比较。') + '</p></div></div>'
      + '<div class="oew-pfoot"><span>' + bi('Not measured yet — nothing here to act on.', '尚未测量 — 此处暂无可据以行动的内容。') + '</span></div>'
    + '</div>';
  }
  var rankPct = num(ivr.rank_pct), nDays = ivr.n_days;
  var body;
  if(ivr.low_confidence){
    body = '<div class="oew-rich-track" role="img">'
      + '<span class="oew-rich-building">' + bi('history building — ' + (nDays || '?') + 'd', '历史积累中 — ' + (nDays || '?') + '天') + '</span>'
    + '</div>';
  } else {
    var on = rankPct === null ? 0 : Math.max(0, Math.min(5, Math.round(rankPct / 100 * 5)));
    var pips = '';
    for(var i = 0; i < 5; i++) pips += '<i class="oew-rich-pip' + (i < on ? ' on' : '') + '"></i>';
    var band = IVR_BAND[ivr.band];
    var tipEn = (rankPct !== null && nDays) ? filmOrdinal(Math.round(rankPct)) + ' percentile of the last ' + nDays + ' trading sessions on file for this name.' : '';
    var tipZh = (rankPct !== null && nDays) ? '该标的近' + nDays + '个交易日记录中的第' + Math.round(rankPct) + '百分位。' : '';
    body = '<div class="oew-rich-track" role="img" tabindex="0" data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh) + '">' + pips
      + (band ? '<span class="oew-rich-band" style="color:' + band[2] + '">' + bi(band[0], band[1]) + '</span>' : '')
    + '</div>';
  }
  var say = '';
  // Minor fix: low_confidence already replaces the pip track with the plain
  // "history building — Nd" chip above (n_days < 20) — printing the full
  // percentile sentence here too claims a settled reading the chip next to
  // it just disclaimed. Suppress the sentence in that state; keep the chip.
  if(!ivr.low_confidence && rankPct !== null && nDays){
    var pctTxt = Math.round(rankPct) + '%';
    say = '<p class="oew-tk-say"><span class="l-en">Options on ' + esc(tk) + ' cost more than <b class="mono">' + pctTxt
      + '</b> of the last <b class="mono">' + nDays + '</b> sessions we have on file.</span>'
      + '<span class="l-zh">' + esc(tk) + ' 期权价格高于我们记录的近 <b class="mono">' + nDays + '</b> 个交易日中的 <b class="mono">' + pctTxt + '</b>。</span></p>';
  }
  return '<div class="oew-panel">' + head
    + '<div class="oew-pbody">' + body + say + '</div>'
    + '<div class="oew-pfoot">'
      + '<span>' + bi('Still building toward a full year of history — read this as a rough placement, not a settled rank.',
          '仍在积累完整一年的历史 — 请视为粗略定位，而非确定分位。') + '</span>'
      + (gx.meta && gx.meta.asof ? '<span class="oew-asof mono">' + esc(gx.meta.asof) + '</span>' : '')
    + '</div>'
  + '</div>';
}

/* ── OIP W1 §5.2/§4.4: "Where positions built" — top-3 build/unwind, diverging bars ── */
function pbStrikeLabel(K, right){
  var n = num(K);
  var k = n === null ? '—' : (n % 1 === 0 ? n.toFixed(0) : n.toFixed(1));
  return k + String(right || '').charAt(0).toUpperCase();
}
function pbDelta(v){
  var n = num(v); if(n === null) return '—';
  return (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString('en-US');
}
/* MAJOR-2 fix (PR #4123 adversarial review round 2): `sharedMax` is now the
   caller's responsibility (one value computed across BOTH columns' rendered
   rows — see wherePositionsBuiltHTML) rather than each call normalizing to its
   own rows' own max. Two independently-scaled columns drew a smaller unwind
   at the same length as a larger build (or vice versa) whenever the two
   columns' own maxima differed — the spec's own §0.10 length-encoding idiom
   requires one shared maximum across the whole panel, not per-column. */
function pbCol(rows, unwind, sharedMax){
  return rows.map(function(r){
    var a = Math.abs(num(r.oi_delta) || 0);
    var w = sharedMax > 0 ? Math.round(a / sharedMax * 100) : 0;
    return '<div class="oew-pb-row"><span class="k mono">' + esc(pbStrikeLabel(r.K, r.right)) + '</span>'
      + '<span class="bar-track"><span class="bar' + (unwind ? ' unwind' : '') + '" style="width:' + w + '%"></span></span>'
      + '<span class="v' + (unwind ? '' : ' build') + ' mono">' + pbDelta(r.oi_delta) + '</span></div>';
  }).join('');
}
function wherePositionsBuiltHTML(gx){
  var od = gx.oi_delta_clusters;
  var newOi = (od && od.new_oi) || [], exitOi = (od && od.exit_oi) || [];
  var helpTip = (od && od.spot_note_en)
    ? '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
      + ' data-tip-en="' + esc(od.spot_note_en) + '" data-tip-zh="' + esc(od.spot_note_zh || od.spot_note_en) + '">?</span></div>'
    : '';
  var head = '<div class="oew-phead">'
    + '<h2 class="oew-ph-title">' + bi('Where positions built','仓位在何处建立') + '</h2>'
    + '<span class="oew-ph-sub">' + bi('open-interest change between the last two chain snapshots','最近两次期权链快照之间的未平仓量变化') + '</span>'
    + helpTip
  + '</div>';
  var body;
  // §0.18 payload check, verbatim: `if ('oi_delta_clusters' in gx && gx.oi_delta_clusters.new_oi.length)`.
  if(newOi.length){
    var pbBuilt = newOi.slice(0, 3), pbUnwound = exitOi.slice(0, 3);
    // Shared maximum across BOTH columns' rendered rows — bar length must stay
    // comparable across the whole panel, never reset per column (MAJOR-2 fix).
    var pbMax = 0;
    pbBuilt.concat(pbUnwound).forEach(function(r){
      var a = Math.abs(num(r.oi_delta) || 0); if(a > pbMax) pbMax = a;
    });
    body = '<div class="oew-pb">'
      + '<div class="oew-pb-col"><div class="oew-pb-h">' + bi('Built','新增') + '</div>' + pbCol(pbBuilt, false, pbMax) + '</div>'
      + '<div class="oew-pb-col"><div class="oew-pb-h">' + bi('Unwound','平仓') + '</div>' + pbCol(pbUnwound, true, pbMax) + '</div>'
    + '</div>';
  } else {
    var noteEn = (od && od.note_en) || 'This name has no matched open-interest change on file for this close.';
    var noteZh = (od && od.note_zh) || '该标的本次收盘暂无匹配的未平仓量变化记录。';
    body = '<p class="oew-pb-note">' + bi(noteEn, noteZh) + '</p>';
  }
  var pctile = (gx.net_gex_pctile && gx.net_gex_pctile.note_en)
    ? '<div class="oew-pb-pctile"><span>' + bi('Also on file:','另有记录：') + '</span> ' + bi(gx.net_gex_pctile.note_en, gx.net_gex_pctile.note_zh) + '</div>'
    : '';
  return '<div class="oew-panel">' + head
    + '<div class="oew-pbody">' + body + pctile + '</div>'
    + '<div class="oew-pfoot">'
      + '<span>' + bi('A count of contracts opened or closed, not a direction call.', '合约新增或平仓的计数，并非方向判断。') + '</span>'
      + (od && od.latest_snapshot ? '<span class="oew-asof mono">' + esc(od.latest_snapshot) + '</span>' : '')
    + '</div>'
  + '</div>';
}

/* ── OIP W1 §5.3: the two full empty-state panels — E4/E7, not built yet ──
   Both use the shared .oew-notyet shell; neither carries a stance chip (§0.13). */
function whatMoveWorthHTML(){
  return '<div class="oew-panel">'
    + '<div class="oew-phead"><h2 class="oew-ph-title">' + bi('What the move is worth','本次波幅是否值得') + '</h2></div>'
    + '<div class="oew-pbody"><div class="oew-notyet">'
      + '<div class="oew-notyet-ghost oew-notyet-cone" aria-hidden="true"></div>'
      + '<p class="oew-notyet-say"><span class="l-en">The expected move itself is in the header above. '
        + 'What we don’t yet track is whether that number is usually <em>right</em> — we’re building a nightly '
        + 'record that grades each session’s implied move against what actually happened.</span>'
        + '<span class="l-zh">预期波幅本身已显示在上方页头。我们尚未跟踪的是这个数字是否<em>通常准确</em> — '
        + '正在建立一份每夜记录，用以对照隐含波幅与实际结果。</span></p>'
    + '</div></div>'
    + '<div class="oew-pfoot"><span>' + bi('Not measured yet — nothing here to act on.', '尚未测量 — 此处暂无可据以行动的内容。') + '</span></div>'
  + '</div>';
}
function expirationPressureHTML(){
  return '<div class="oew-panel">'
    + '<div class="oew-phead"><h2 class="oew-ph-title">' + bi('Expiration pressure','到期压力') + '</h2></div>'
    + '<div class="oew-pbody"><div class="oew-notyet">'
      + '<div class="oew-notyet-ghost oew-notyet-bar" aria-hidden="true"></div>'
      + '<p class="oew-notyet-say">' + bi(
          "Not measured yet. The idea: how much of this name's open interest rolls off in the next few days, and whether that concentration tends to feed on itself into expiry.",
          '尚未测量。设想中的内容：该标的近几日到期的未平仓量占比，以及该集中度在到期前是否会自我强化。') + '</p>'
    + '</div></div>'
    + '<div class="oew-pfoot"><span>' + bi('Not measured yet — nothing here to act on.', '尚未测量 — 此处暂无可据以行动的内容。') + '</span></div>'
  + '</div>';
}

/* ══════════════════════════════════════════════════════════════════════════
   THE RAW-STRUCTURE SHELF  (OIP W1.6-A · ONE_DOOR_RULING_AND_SPEC §2.2)
   gex.html's six charts, re-homed inside the "Under the hood" <details> this
   page already ships. Three rules make the port safe:

   1. ZERO extra network. Every figure below is read off the gex/<T>.json
      renderTicker already fetched — the shelf adds charts, never a request.
   2. Drawn on FIRST OPEN, not on render: a closed shelf costs nothing, and a
      reader who never opens it never pays for 300 heatmap cells.
   3. Colour is `style="fill:var(--up)"`, never a resolved hex. SVG resolves
      CSS variables live, so the zh 红涨绿跌 flip repaints these charts with no
      redraw and no listener — the failure mode gex.js has (it re-renders the
      whole detail view on 'langchange') simply cannot occur here.

   Each sub-chart owns its own honest empty slot: a name whose payload lacks the
   block says so in that slot and the other five still draw.
   ══════════════════════════════════════════════════════════════════════════ */
function rawEmpty(en, zh){ return '<p class="oew-raw-empty">' + bi(en, zh) + '</p>'; }
function cnum(v){
  var n = num(v); if(n === null) return '—';
  var a = Math.abs(n), s = n < 0 ? '−' : '';
  if(a >= 1e9) return s + (a/1e9).toFixed(2) + 'B';
  if(a >= 1e6) return s + (a/1e6).toFixed(2) + 'M';
  if(a >= 1e3) return s + (a/1e3).toFixed(1) + 'k';
  return s + a.toFixed(0);
}
function rawItem(hEn, hZh, sEn, sZh, body){
  return '<div class="oew-raw-item"><h3 class="oew-raw-h">' + bi(hEn, hZh) + '</h3>'
    + '<p class="oew-raw-sub">' + bi(sEn, sZh) + '</p>' + body + '</div>';
}

/* ── dealer gamma by strike — diverging bars, strikes down the y axis ── */
function rawGammaBarsSVG(gx){
  var rows = ((gx.walls || {}).by_strike || []).filter(function(r){ return num(r.K) !== null; });
  if(!rows.length) return rawEmpty('No per-strike record on file for this name in this close.',
    '本次收盘没有该标的的逐行权价记录。');
  var s = gx.summary || {};
  var W = 540, H = 400, mL = 52, mR = 78, mT = 12, mB = 20;
  var ks = rows.map(function(r){ return num(r.K); });
  var loK = Math.min.apply(null, ks), hiK = Math.max.apply(null, ks);
  var spot = num(s.spot);
  if(spot !== null){ loK = Math.min(loK, spot); hiK = Math.max(hiK, spot); }
  var padK = (hiK - loK) * 0.04 || 1; loK -= padK; hiK += padK;
  function Y(v){ return mT + (hiK - v) / (hiK - loK) * (H - mT - mB); }
  var plotW = W - mL - mR, x0 = mL + plotW / 2, maxAbs = 0;
  rows.forEach(function(r){ maxAbs = Math.max(maxAbs, Math.abs(num(r.net_mn) || 0)); });
  maxAbs = maxAbs || 1;
  var sc = (plotW / 2 - 4) / maxAbs;
  var bh = Math.max(2, Math.min(13, (H - mT - mB) / rows.length * 0.78));
  var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Dealer gamma by strike">';
  svg += '<line x1="' + x0 + '" y1="' + mT + '" x2="' + x0 + '" y2="' + (H - mB)
    + '" style="stroke:var(--line)" stroke-width="1"/>';
  for(var i = 0; i <= 5; i++){
    var pv = loK + (hiK - loK) * i / 5, yy = Y(pv);
    svg += '<text x="' + (mL - 6) + '" y="' + (yy + 3).toFixed(1) + '" text-anchor="end" font-size="10"'
      + ' style="fill:var(--muted)">' + esc(lvl(pv)) + '</text>';
    svg += '<line x1="' + mL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - mR) + '" y2="' + yy.toFixed(1)
      + '" style="stroke:var(--line)" stroke-width="0.5" opacity="0.4"/>';
  }
  rows.forEach(function(r){
    var v = num(r.net_mn) || 0, yy = Y(num(r.K)), w = Math.abs(v) * sc;
    if(!w) return;
    var x = v >= 0 ? x0 : x0 - w;
    svg += '<rect x="' + x.toFixed(1) + '" y="' + (yy - bh/2).toFixed(1) + '" width="' + w.toFixed(1)
      + '" height="' + bh.toFixed(1) + '" style="fill:var(' + (v >= 0 ? '--up' : '--down') + ')" opacity="0.82"/>';
  });
  /* Level lines sit at their true y; their LABELS are dodged apart and joined
     back by a leader line. Ported from gex.js because the collision is real and
     common: flip and last close are often within a few cents of each other (SPY
     closed 747.03 against a 747.16 flip), and two labels printed at the same y
     overlap into an unreadable smear. */
  var levels = [['--up', s.call_wall, 'call wall', '看涨墙'], ['--text', s.spot, 'last close', '最新收盘'],
                ['--oew-accent', s.gamma_flip, 'flip', '翻转位'], ['--down', s.put_wall, 'put wall', '看跌墙']]
    .filter(function(L){ return num(L[1]) !== null; })
    .map(function(L){ return { tok: L[0], y: Y(num(L[1])), en: L[2], zh: L[3] }; });
  levels.forEach(function(L){
    svg += '<line x1="' + mL + '" y1="' + L.y.toFixed(1) + '" x2="' + (W - mR) + '" y2="' + L.y.toFixed(1)
      + '" style="stroke:var(' + L.tok + ')" stroke-width="1.2" stroke-dasharray="4 3"/>';
  });
  var sorted = levels.slice().sort(function(a, b){ return a.y - b.y; }), gap = 13, prev = -1e9;
  sorted.forEach(function(L){ L.ly = Math.max(L.y, prev + gap); prev = L.ly; });
  var overflow = sorted.length ? sorted[sorted.length - 1].ly - (H - 4) : 0;
  if(overflow > 0) sorted.forEach(function(L){ L.ly -= overflow; });
  sorted.forEach(function(L){
    if(Math.abs(L.ly - L.y) > 2){
      svg += '<line x1="' + (W - mR) + '" y1="' + L.y.toFixed(1) + '" x2="' + (W - mR + 4) + '" y2="'
        + L.ly.toFixed(1) + '" style="stroke:var(' + L.tok + ')" stroke-width="0.7" opacity="0.55"/>';
    }
    svg += '<text x="' + (W - mR + 5) + '" y="' + (L.ly + 3).toFixed(1) + '" font-size="10" style="fill:var('
      + L.tok + ')" class="l-en">' + esc(L.en) + '</text>';
    svg += '<text x="' + (W - mR + 5) + '" y="' + (L.ly + 3).toFixed(1) + '" font-size="10" style="fill:var('
      + L.tok + ')" class="l-zh">' + esc(L.zh) + '</text>';
  });
  svg += '</svg>';
  return '<div class="oew-raw-box">' + svg + '</div>'
    + '<div class="oew-raw-leg"><span><i style="background:var(--up)"></i>' + bi('call gamma','看涨 Gamma')
    + '</span><span><i style="background:var(--down)"></i>' + bi('put gamma','看跌 Gamma') + '</span></div>';
}

/* ── net-gamma profile — the curve re-evaluated across spot ── */
function rawProfileSVG(gx){
  var p = gx.profile || {};
  var xs = p.spots || [], ys = p.gamma_bn || [];
  if(xs.length < 2 || ys.length !== xs.length) return rawEmpty(
    'No profile curve on file for this name in this close.', '本次收盘没有该标的的曲线记录。');
  var W = 540, H = 300, mL = 46, mR = 26, mT = 14, mB = 26;
  var xlo = Math.min.apply(null, xs), xhi = Math.max.apply(null, xs);
  var ylo = Math.min.apply(null, ys), yhi = Math.max.apply(null, ys);
  if(ylo > 0) ylo = 0; if(yhi < 0) yhi = 0;
  var ypad = (yhi - ylo) * 0.08 || 1; ylo -= ypad; yhi += ypad;
  function X(v){ return mL + (v - xlo) / ((xhi - xlo) || 1) * (W - mL - mR); }
  function Y(v){ return mT + (yhi - v) / ((yhi - ylo) || 1) * (H - mT - mB); }
  var zeroY = Y(0);
  var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Net dealer gamma against spot">';
  for(var i = 0; i <= 4; i++){
    var gv = ylo + (yhi - ylo) * i / 4, yy = Y(gv);
    svg += '<line x1="' + mL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - mR) + '" y2="' + yy.toFixed(1)
      + '" style="stroke:var(--line)" stroke-width="0.5" opacity="0.4"/>';
    svg += '<text x="' + (mL - 5) + '" y="' + (yy + 3).toFixed(1) + '" text-anchor="end" font-size="10"'
      + ' style="fill:var(--muted)">' + gv.toFixed(1) + '</text>';
  }
  for(var k = 0; k < xs.length - 1; k++){
    var xA = X(xs[k]), xB = X(xs[k+1]), yA = ys[k], yB = ys[k+1];
    var col = ((yA + yB) / 2 >= 0) ? '--up' : '--down';
    svg += '<path d="M' + xA.toFixed(1) + ' ' + zeroY.toFixed(1) + ' L' + xA.toFixed(1) + ' ' + Y(yA).toFixed(1)
      + ' L' + xB.toFixed(1) + ' ' + Y(yB).toFixed(1) + ' L' + xB.toFixed(1) + ' ' + zeroY.toFixed(1)
      + 'Z" style="fill:var(' + col + ')" opacity="0.16"/>';
  }
  svg += '<line x1="' + mL + '" y1="' + zeroY.toFixed(1) + '" x2="' + (W - mR) + '" y2="' + zeroY.toFixed(1)
    + '" style="stroke:var(--muted)" stroke-width="1"/>';
  svg += '<path d="' + xs.map(function(v,i2){ return (i2 ? 'L' : 'M') + X(v).toFixed(1) + ' ' + Y(ys[i2]).toFixed(1); }).join(' ')
    + '" fill="none" style="stroke:var(--text)" stroke-width="1.6"/>';
  var sp = num(p.spot), fp = num(p.flip);
  if(sp !== null) svg += '<line x1="' + X(sp).toFixed(1) + '" y1="' + mT + '" x2="' + X(sp).toFixed(1)
    + '" y2="' + (H - mB) + '" style="stroke:var(--text)" stroke-width="1" stroke-dasharray="3 3"/>';
  if(fp !== null) svg += '<line x1="' + X(fp).toFixed(1) + '" y1="' + mT + '" x2="' + X(fp).toFixed(1)
    + '" y2="' + (H - mB) + '" style="stroke:var(--oew-accent)" stroke-width="1.2" stroke-dasharray="4 3"/>';
  for(var j = 0; j <= 4; j++){
    var xv = xlo + (xhi - xlo) * j / 4;
    svg += '<text x="' + X(xv).toFixed(1) + '" y="' + (H - mB + 14) + '" text-anchor="middle" font-size="9.5"'
      + ' style="fill:var(--muted)">' + esc(lvl(xv)) + '</text>';
  }
  svg += '</svg>';
  return '<div class="oew-raw-box">' + svg + '</div>'
    + '<div class="oew-raw-leg"><span><i style="background:var(--text)"></i>' + bi('last close','最新收盘')
    + '</span><span><i style="background:var(--oew-accent)"></i>' + bi('flip','翻转位') + '</span></div>';
}

/* ── strike × expiry surface ── */
function rawHeatHTML(gx){
  var sf = gx.surface || {}, s = gx.summary || {};
  var strikes = sf.strikes || [], exps = sf.expiries || [], z = sf.z_gex || [];
  if(!strikes.length || !exps.length || !z.length) return rawEmpty(
    'No expiry surface on file for this name in this close.', '本次收盘没有该标的的到期曲面记录。');
  var mx = num(sf.gex_max) || 1, spot = num(s.spot);
  var nearest = null, best = Infinity;
  strikes.forEach(function(k){
    if(spot === null) return;
    var d = Math.abs(k - spot); if(d < best){ best = d; nearest = k; }
  });
  var h = '<table class="oew-raw-heat"><thead><tr><th></th>';
  exps.forEach(function(e, i){
    h += '<th>' + esc(e) + '<br><span class="mono">' + esc(String((sf.days || [])[i] == null ? '' : sf.days[i] + 'd')) + '</span></th>';
  });
  h += '</tr></thead><tbody>';
  strikes.forEach(function(k, ri){
    h += '<tr' + (k === nearest ? ' class="spotrow"' : '') + '><td class="kk">' + esc(lvl(k)) + '</td>';
    exps.forEach(function(e, ci){
      var v = (z[ri] || [])[ci];
      if(v === null || v === undefined){ h += '<td style="background:color-mix(in srgb,var(--text) 4%,transparent)"></td>'; return; }
      var a = Math.round((0.12 + 0.8 * Math.min(1, Math.abs(v) / mx)) * 100);
      h += '<td class="mono" style="background:color-mix(in srgb,var(' + (v >= 0 ? '--up' : '--down') + ') ' + a
        + '%,transparent)">' + (Math.abs(v) >= 1 ? Math.round(v) : '') + '</td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table>';
  return '<div class="oew-raw-scroll">' + h + '</div>'
    + '<div class="oew-raw-leg"><span><i style="background:var(--up)"></i>' + bi('call gamma','看涨 Gamma')
    + '</span><span><i style="background:var(--down)"></i>' + bi('put gamma','看跌 Gamma')
    + '</span><span>' + bi('outlined row = the strike nearest the close','加框行 = 最接近收盘价的行权价') + '</span></div>';
}

/* ── volatility smile / skew (front expiry) ── */
function rawSmileSVG(gx){
  var sm = gx.smile || {}, s = gx.summary || {};
  var ks = sm.strikes || [], cIV = sm.call_iv || [], pIV = sm.put_iv || [];
  if(ks.length < 3) return rawEmpty('Not enough strikes on file to draw the smile for this name.',
    '该标的行权价记录不足，暂无法绘制波动率微笑。');
  var W = 540, H = 280, mL = 40, mR = 26, mT = 26, mB = 26;
  var all = cIV.concat(pIV).filter(function(v){ return num(v) !== null; });
  if(all.length < 3) return rawEmpty('Not enough implied-volatility points on file for this name.',
    '该标的隐含波动率记录点不足。');
  var ylo = Math.min.apply(null, all), yhi = Math.max.apply(null, all);
  var yp = (yhi - ylo) * 0.12 || 1; ylo -= yp; yhi += yp; if(ylo < 0) ylo = 0;
  var xlo = ks[0], xhi = ks[ks.length - 1];
  function X(v){ return mL + (v - xlo) / ((xhi - xlo) || 1) * (W - mL - mR); }
  function Y(v){ return mT + (yhi - v) / ((yhi - ylo) || 1) * (H - mT - mB); }
  function poly(vals, tok){
    var d = '', started = false;
    for(var i = 0; i < ks.length; i++){
      if(num(vals[i]) === null){ started = false; continue; }
      d += (started ? 'L' : 'M') + X(ks[i]).toFixed(1) + ' ' + Y(vals[i]).toFixed(1) + ' ';
      started = true;
    }
    return '<path d="' + d + '" fill="none" style="stroke:var(' + tok + ')" stroke-width="1.6" stroke-linejoin="round"/>';
  }
  var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Implied volatility by strike">';
  for(var i = 0; i <= 4; i++){
    var gv = ylo + (yhi - ylo) * i / 4, yy = Y(gv);
    svg += '<line x1="' + mL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - mR) + '" y2="' + yy.toFixed(1)
      + '" style="stroke:var(--line)" stroke-width="0.5" opacity="0.4"/>';
    svg += '<text x="' + (mL - 5) + '" y="' + (yy + 3).toFixed(1) + '" text-anchor="end" font-size="10"'
      + ' style="fill:var(--muted)">' + gv.toFixed(0) + '%</text>';
  }
  svg += poly(pIV, '--down') + poly(cIV, '--up');
  var sp = num(s.spot);
  if(sp !== null && sp >= xlo && sp <= xhi){
    svg += '<line x1="' + X(sp).toFixed(1) + '" y1="' + mT + '" x2="' + X(sp).toFixed(1) + '" y2="' + (H - mB)
      + '" style="stroke:var(--text)" stroke-width="1" stroke-dasharray="3 3"/>';
  }
  for(var j = 0; j <= 4; j++){
    var xv = xlo + (xhi - xlo) * j / 4;
    svg += '<text x="' + X(xv).toFixed(1) + '" y="' + (H - mB + 14) + '" text-anchor="middle" font-size="9.5"'
      + ' style="fill:var(--muted)">' + esc(lvl(xv)) + '</text>';
  }
  svg += '</svg>';
  return '<div class="oew-raw-box">' + svg + '</div>'
    + '<div class="oew-raw-leg"><span><i style="background:var(--up)"></i>' + bi('call side','看涨一侧')
    + '</span><span><i style="background:var(--down)"></i>' + bi('put side','看跌一侧') + '</span>'
    + (sm.expiry ? '<span class="mono">' + esc(sm.expiry) + (sm.days != null ? ' · ' + sm.days + 'd' : '') + '</span>' : '')
    + '</div>';
}

/* ── implied-volatility term structure ── */
function rawTermSVG(gx){
  var tm = (gx.term || []).filter(function(r){ return num(r.days) !== null && num(r.atm_iv) !== null; });
  if(tm.length < 2) return rawEmpty('Not enough expiries on file to draw the term structure for this name.',
    '该标的到期日记录不足，暂无法绘制期限结构。');
  var W = 540, H = 280, mL = 40, mR = 26, mT = 16, mB = 26;
  var xs = tm.map(function(r){ return num(r.days); }), ys = tm.map(function(r){ return num(r.atm_iv); });
  var xlo = Math.min.apply(null, xs), xhi = Math.max.apply(null, xs);
  var ylo = Math.min.apply(null, ys), yhi = Math.max.apply(null, ys);
  var yp = (yhi - ylo) * 0.15 || 1; ylo -= yp; yhi += yp; if(ylo < 0) ylo = 0;
  function X(v){ return mL + (v - xlo) / ((xhi - xlo) || 1) * (W - mL - mR); }
  function Y(v){ return mT + (yhi - v) / ((yhi - ylo) || 1) * (H - mT - mB); }
  var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="At-the-money implied volatility by expiry">';
  for(var i = 0; i <= 4; i++){
    var gv = ylo + (yhi - ylo) * i / 4, yy = Y(gv);
    svg += '<line x1="' + mL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - mR) + '" y2="' + yy.toFixed(1)
      + '" style="stroke:var(--line)" stroke-width="0.5" opacity="0.4"/>';
    svg += '<text x="' + (mL - 5) + '" y="' + (yy + 3).toFixed(1) + '" text-anchor="end" font-size="10"'
      + ' style="fill:var(--muted)">' + gv.toFixed(0) + '%</text>';
  }
  svg += '<path d="' + xs.map(function(v,i2){ return (i2 ? 'L' : 'M') + X(v).toFixed(1) + ' ' + Y(ys[i2]).toFixed(1); }).join(' ')
    + '" fill="none" style="stroke:var(--oew-accent)" stroke-width="1.8" stroke-linejoin="round"/>';
  xs.forEach(function(v, i3){
    svg += '<circle cx="' + X(v).toFixed(1) + '" cy="' + Y(ys[i3]).toFixed(1) + '" r="2.6" style="fill:var(--oew-accent)"/>';
  });
  var step = Math.ceil(tm.length / 6);
  xs.forEach(function(v, i4){
    if(i4 % step !== 0 && i4 !== xs.length - 1) return;
    svg += '<text x="' + X(v).toFixed(1) + '" y="' + (H - mB + 14) + '" text-anchor="middle" font-size="9.5"'
      + ' style="fill:var(--muted)">' + v.toFixed(0) + 'd</text>';
  });
  svg += '</svg>';
  return '<div class="oew-raw-box">' + svg + '</div>';
}

/* ── the expiry ladder — the full record behind the levels above ── */
function rawLadderHTML(gx){
  var tm = gx.term || [];
  if(!tm.length) return rawEmpty('No expiry record on file for this name in this close.',
    '本次收盘没有该标的的到期日记录。');
  var head = '<tr><th>' + bi('Expiry','到期') + '</th><th>' + bi('Days','天数') + '</th><th>'
    + bi('At-the-money IV','平值隐波') + '</th><th>' + bi('Implied move','隐含波幅') + '</th><th>'
    + bi('Straddle','跨式') + '</th><th>' + bi('Magnet','磁吸位') + '</th></tr>';
  var body = tm.map(function(r){
    return '<tr><td>' + esc(r.expiry || '—') + '</td>'
      + '<td class="mono">' + (num(r.days) === null ? '—' : num(r.days).toFixed(0)) + '</td>'
      + '<td class="mono">' + pctv(r.atm_iv) + '</td>'
      + '<td class="mono">' + (num(r.move_pct) === null ? '—' : '±' + pctv(r.move_pct)) + '</td>'
      + '<td class="mono">' + (num(r.straddle_pct) === null ? '—' : '±' + pctv(r.straddle_pct)) + '</td>'
      + '<td class="mono">' + lvl(r.max_pain) + '</td></tr>';
  }).join('');
  return '<div class="oew-raw-scroll"><table class="oew-raw-tbl"><thead>' + head + '</thead><tbody>'
    + body + '</tbody></table></div>';
}

/* ── the positioning greeks row ── */
function rawGreeksHTML(gx){
  var s = gx.summary || {};
  function g(kEn, kZh, v, sEn, sZh){
    return '<div class="g"><span class="k">' + bi(kEn, kZh) + '</span><span class="v mono">' + v + '</span>'
      + (sEn ? '<span class="s">' + bi(sEn, sZh) + '</span>' : '') + '</div>';
  }
  var charm = num(s.charm_net_sign);
  var cells = g('Net delta','净 Delta', num(s.net_delta_bn) === null ? '—' : smoney(num(s.net_delta_bn) * 1000))
    + g('Net vanna','净 Vanna', cnum(s.net_vex))
    + g('Charm bias','Charm 偏向', charm === null || charm === 0 ? '—' : (charm > 0 ? '↑' : '↓'),
        charm === null || charm === 0 ? '' : (charm > 0 ? 'drifts up' : 'drifts down'),
        charm === null || charm === 0 ? '' : (charm > 0 ? '向上漂移' : '向下漂移'))
    + g('Put/call OI','认沽认购持仓比', num(s.put_call_oi_ratio) === null ? '—' : num(s.put_call_oi_ratio).toFixed(2) + 'x')
    + g('Put/call volume','认沽认购成交比', num(s.put_call_vol_ratio) === null ? '—' : num(s.put_call_vol_ratio).toFixed(2) + 'x')
    /* `largest_oi` is a STRIKE, not a contract count — gex.js prints it through
       its own price formatter. Labelling it "largest open interest" beside a
       bare 750 would read as 750 contracts, so the label names what the number
       actually is. */
    + g('Busiest strike','持仓最大行权价', lvl(s.largest_oi))
    + g('Strikes','行权价数', s.n_strikes == null ? '—' : String(s.n_strikes),
        s.tier === 'full' ? 'deep chain' : 'thin chain', s.tier === 'full' ? '期权链较深' : '期权链较薄');
  return '<div class="oew-raw-greeks">' + cells + '</div>';
}

/* The whole shelf body, as one string. Pure — no DOM, no fetch — so it can be
   driven straight from a test with a fixture payload. */
function rawShelfBody(gx){
  if(!gx) return rawEmpty('No options structure on file for this name in this close.',
    '本次收盘没有该标的的期权结构记录。');
  return rawItem('Dealer gamma by strike','按行权价的做市商 Gamma',
      'Net dealer gamma summed at each strike. The long bars are the walls the levels above are read from.',
      '每个行权价上汇总的做市商净 Gamma。较长的柱状即上方水位所依据的墙位。',
      rawGammaBarsSVG(gx))
    + rawItem('Net gamma against price','净 Gamma 对价格',
        'The same measure re-evaluated as price moves. Where the curve crosses zero is the flip.',
        '同一指标随价格变动重新计算。曲线穿越零点之处即翻转位。',
        rawProfileSVG(gx))
    + rawItem('The surface — strikes by expiry','曲面 — 行权价与到期日',
        'Rows are strikes, columns are expiries. The bright cells are where positioning concentrates.',
        '行为行权价，列为到期日。颜色越深处即仓位集中之处。',
        rawHeatHTML(gx))
    + '<div class="oew-raw-grid">'
      + rawItem('What cover costs by strike','各行权价的保护成本',
          'Implied volatility by strike for the front expiry. A steeper put side means downside cover is pricier.',
          '近月到期各行权价的隐含波动率。看跌一侧越陡，下行保护越贵。',
          rawSmileSVG(gx))
      + rawItem('What cover costs by date','各到期日的保护成本',
          'At-the-money implied volatility by expiry. Rising with time is the calm default; the reverse flags an event.',
          '各到期日的平值隐含波动率。随时间上行为平静常态；反向倒挂则预示事件。',
          rawTermSVG(gx))
    + '</div>'
    + rawItem('Every expiry on file','全部到期日记录',
        'The full record behind the levels above, one row per expiry.',
        '上方水位背后的完整记录，每个到期日一行。',
        rawLadderHTML(gx))
    + rawItem('Positioning greeks','持仓希腊字母',
        'The chain-wide sensitivities the model reconstructs. Reference material, not a read.',
        '模型重构的全链敏感度。仅为参考资料，并非解读。',
        rawGreeksHTML(gx));
}

function renderTicker(host, tk, gx, fl, sess){
  if(!gx || !gx.summary){
    host.innerHTML = emptyPanel('We have no options structure for ' + tk + ' in this close. Pick a name from the Scanner or the Brief.',
      '本次收盘没有 ' + tk + ' 的期权结构数据。请从筛选或简报中选择标的。');
    return;
  }
  var s = gx.summary, meta = gx.meta || {}, em = gx.expected_move || {};
  var reg = s.regime, head = REGIME_HEAD[reg] || ['—','—'], say = REGIME_SAY[reg] || ['',''];
  var spot = num(s.spot);
  var lo = num(s.put_wall), hi = num(s.call_wall), flip = num(s.gamma_flip), mag = num(s.max_pain);
  var vals = [lo, hi, flip, mag, spot].filter(function(v){ return v !== null; });
  var band = '';
  if(vals.length > 1){
    var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals), pad = (mx - mn) * 0.12 || 1;
    var a = mn - pad, b = mx + pad;
    var pos = function(v){ return ((v - a) / (b - a) * 100).toFixed(1) + '%'; };
    var mark = function(cls, v){ return v === null ? '' : '<span class="oew-lad-mk ' + cls + '" style="left:' + pos(v) + '"></span>'; };
    var lab = function(v, en, zh){ return v === null ? '' :
      '<span class="oew-lad-lbl" style="left:' + pos(v) + '"><span class="v mono">' + lvl(v) + '</span><span class="k">' + bi(en, zh) + '</span></span>'; };
    band = '<div class="oew-lad" aria-hidden="true"><div class="oew-lad-band"></div>'
      + mark('floor', lo) + mark('magnet', mag) + mark('flip', flip) + mark('ceil', hi)
      + (spot === null ? '' : '<span class="oew-lad-dot" style="left:' + pos(spot) + '"></span>'
          + '<span class="oew-lad-spot" style="left:' + pos(spot) + '"><span class="v mono">' + px(spot) + '</span>'
          + '<span class="k">' + bi('last close','最新收盘') + '</span></span>')
      + lab(lo, 'floor', '下方墙') + lab(mag, 'magnet', '磁吸位')
      + lab(flip, 'flip', '翻转位') + lab(hi, 'ceiling', '上方墙')
      + '</div>';
  }
  var dailyPct = num(em.daily_pct);
  var rangeTxt = (spot !== null && dailyPct !== null)
    ? px(spot * (1 - dailyPct/100)) + '–' + px(spot * (1 + dailyPct/100)) : '';

  host.innerHTML = ''
  + '<div class="oew-panel"><div class="oew-pbody">'
    + '<div class="oew-tk-head">'
      + '<div><div class="oew-tk-sym mono">' + esc(tk) + '</div>'
        + '<div class="oew-tk-name">' + bi(meta.en || tk, meta.zh || meta.en || tk) + '</div></div>'
      + '<div class="oew-tk-px"><span class="k">' + bi('Last close','最新收盘') + '</span>'
        + '<span class="v mono">' + px(spot) + '</span></div>'
    + '</div>'
    + '<h3 class="oew-tk-regime">' + bi(head[0], head[1]) + '</h3>'
    + '<p class="oew-tk-say">' + bi(say[0], say[1]) + '</p>'
    /* The read's ONE decision element (OIP_MASTERPLAN §3 verdict law; marker placement
       pinned by W1_DESIGN_SPEC §5.1). Bare boolean attribute — CI greps for duplicates. */
    + '<div class="oew-ic-foot" data-verdict-surface style="margin-top:12px">'
      + (reg === 'short'
          ? '<span class="oew-stance st-protect">' + bi('Protect gains','保护利润') + '</span>'
          : '<span class="oew-stance st-watch">' + bi("Watch — don't chase",'观察—勿追高') + '</span>')
      + (rangeTxt ? '<span class="oew-ic-em">' + bi('expected tomorrow','明日预期区间')
          + ' <b class="mono">' + rangeTxt + '</b> <span class="mono">±' + dailyPct.toFixed(2) + '%</span></span>' : '')
    + '</div>'
  + '</div></div>'

  + filmstripPanelHTML(sess)

  + '<div class="oew-panel">'
    + '<div class="oew-phead">'
      + '<h2 class="oew-ph-title">' + bi('The map — where dealer hedging sits','地图 — 做市商对冲所在位置') + '</h2>'
      + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
        + ' data-tip-en="Walls are the strikes carrying the most dealer gamma above and below price. The flip is where hedging changes character. The magnet is the strike where the most option value expires worthless. All measured from this close, and all model estimates: real dealer books are unobservable."'
        + ' data-tip-zh="墙位是价格上下方做市商 Gamma 最集中的行权价。翻转位是对冲性质改变之处。磁吸位是最多期权价值到期归零的行权价。均以本次收盘计算，且均为模型估算：真实做市商持仓不可观测。">?</span></div>'
    + '</div>'
    + '<div class="oew-pbody">' + band
      + '<div class="oew-lvl">'
        + lvRow('var(--up)', 'Ceiling — call wall', '上方墙 — 看涨墙',
            'Rallies tend to stall into this wall. Only a daily close above it opens the upside.',
            '涨势往往在此墙位停滞。只有日线收于其上方才会打开上行空间。',
            num(s.call_wall_strength), spot, s.call_wall, wcheckChip(gx, 'call', s.call_wall))
        + lvRow('var(--oew-accent)', 'Flip — the regime line', '翻转位 — 状态分界',
            'Calm above this line, jumpy below.',
            '此线上方平静，下方剧烈。',
            num(s.flip_strength), spot, s.gamma_flip)
        + lvRow('var(--orange)', 'Magnet — max pain', '磁吸位 — 最大痛点',
            'On quiet days price tends to drift toward this level into expiry. The pull is weak while the tape is jumpy.',
            '在平静的日子里，价格临近到期时倾向于向此水位漂移。盘面剧烈时该拉力较弱。',
            num(s.magnet_strength), spot, s.max_pain)
        + lvRow('var(--down)', 'Floor — put wall', '下方墙 — 看跌墙',
            'Sell-offs tend to slow into this wall. A daily close below it pulls that cushion away.',
            '抛售往往在此墙位放缓。日线收于其下方将使该缓冲消失。',
            num(s.put_wall_strength), spot, s.put_wall, wcheckChip(gx, 'put', s.put_wall))
      + '</div>'
    + '</div>'
    + '<div class="oew-pfoot">'
      + '<span>' + bi('Walls are measured from this close, so price always starts inside the band. Only a full day’s close beyond a level counts — an intraday poke does not.',
          '墙位以本次收盘计算，因此价格始终从区间内开始。只有整日收盘突破某一水位才算数 — 盘中触及不算。') + '</span>'
      + (meta.asof ? '<span class="oew-asof mono">' + esc(meta.asof) + '</span>' : '')
    + '</div>'
  + '</div>'

  + richOrCheapHTML(tk, gx)
  + wherePositionsBuiltHTML(gx)

  + '<div class="oew-reads">'
    + rdCard('The tape — calm or jumpy?', '盘面 — 平静还是剧烈？',
        reg === 'short' ? 'Jumpy' : 'Calm', reg === 'short' ? '剧烈' : '平静',
        reg === 'short' ? 'Dealer hedging adds to moves — swings and air-pockets run bigger than usual.'
                        : 'Dealer hedging works against moves — swings stay smaller than usual.',
        reg === 'short' ? '做市商对冲会加剧波动 — 摆动与急跌幅度大于平常。'
                        : '做市商对冲会抑制波动 — 摆动幅度小于平常。')
    + rdCard('The mood — what options cost', '情绪 — 期权价格',
        num(s.iv30) === null ? '—' : pctv(s.iv30) + ' IV', num(s.iv30) === null ? '—' : pctv(s.iv30) + ' 隐波',
        'What the options market charges for 30-day cover on this name.',
        '期权市场对该标的 30 天保护的定价。')
    + rdCard('The lean — direction by time window', '倾向 — 分时间窗口的方向',
        num(s.put_call_oi_ratio) === null ? 'Two-sided' : (num(s.put_call_oi_ratio) > 1 ? 'Put-heavy' : 'Call-heavy'),
        num(s.put_call_oi_ratio) === null ? '双向' : (num(s.put_call_oi_ratio) > 1 ? '认沽偏重' : '认购偏重'),
        'Weaker evidence than the tape read — treat this as context, not a signal.',
        '证据强度弱于盘面读数 — 应作为背景参考，而非信号。')
  + '</div>'

  + whatMoveWorthHTML()
  + expirationPressureHTML()

  + (fl && fl.available !== false ? '<div class="oew-panel">'
    + '<div class="oew-phead">'
      + '<h2 class="oew-ph-title">' + bi('Today’s measured flow','今日实测资金') + '</h2>'
      + '<span class="oew-ph-sub">' + bi('what actually traded, before any interpretation','实际成交数据，未经任何解读') + '</span>'
    + '</div>'
    + '<div class="oew-pbody"><div class="oew-metrics">'
      + mt('Premium','权利金', money(fl.premium_mn))
      + mt('Same-day','当日到期', num(fl.zerodte_share) === null ? '—' : (num(fl.zerodte_share)*100).toFixed(0) + '%')
      + mt('Put/call','认沽认购比', num(fl.pc_ratio) === null ? '—' : num(fl.pc_ratio).toFixed(2) + 'x')
      + mt('Net premium','净权利金', smoney(fl.net_premium_mn))
    + '</div></div>'
    /* NO stance chip: this footer states how far the measured numbers can be trusted —
       a fact about the reading, not a second verdict on it. The name header above is
       this read's one decision element. Sentence + as-of stay verbatim (§0.13 follow-up). */
    + '<div class="oew-pfoot">'
      + '<span>' + bi('Size is a solid read. Direction comes from tick-rule signing and is not reliable enough to read on its own.',
          '规模数据可靠。方向数据来自 tick 规则签署，其本身不足以作为方向依据。') + '</span>'
      + (fl.asof ? '<span class="oew-asof mono">' + esc(fl.asof) + '</span>' : '')
    + '</div>'
  + '</div>' : '')

  + '<details class="oew-panel oew-shelf" id="oew-shelf">'
    + '<summary>' + bi('Under the hood — the raw options structure','底层数据 — 原始期权结构')
      + ' <span class="oew-ph-sub">· '
      + bi('charts and the full strike record — for readers who want the plumbing',
           '图表与完整行权价记录 — 供想看底层结构的读者') + '</span></summary>'
    + '<div class="oew-pbody" style="border-top:1px solid var(--hair)">'
      + '<div class="oew-metrics">'
        + mt('Net gamma','净 Gamma', num(s.net_gex_bn) === null ? '—' : num(s.net_gex_bn).toFixed(2) + 'B')
        + mt('Strikes','行权价数', s.n_strikes == null ? '—' : String(s.n_strikes))
        + mt('Put/call OI','认沽认购持仓比', num(s.put_call_oi_ratio) === null ? '—' : num(s.put_call_oi_ratio).toFixed(2) + 'x')
        + mt('Max pain','最大痛点', lvl(s.max_pain))
        + mt('Chain depth','期权链深度', esc(s.tier || '—'))
      + '</div>'
      + '<p class="oew-tk-say" style="margin:12px 0 0">' + bi('This shelf is closed by default because it is reference material, not a read. Every figure here is reconstructed from the options chain: real dealer books are unobservable.',
          '该抽屉默认折叠，因为它是参考资料而非解读。此处每一个数字均由期权链重构而来：真实做市商持仓不可观测。') + '</p>'
      /* filled by rawShelfBody() on the FIRST open only — see the toggle wiring
         below. Empty until then: a closed shelf costs the reader nothing. */
      + '<div id="oew-raw-slot"></div>'
    + '</div>'
  + '</details>'

  + '<div class="oew-handoff">'
    + '<div><div class="oew-ho-t">' + bi('These levels are frozen until tomorrow','这些水位在明日前保持不变') + '</div>'
      + '<div class="oew-ho-s">' + bi('Walls move during the session as positions change. To watch this name’s structure update live, open it in the Terminal.',
          '墙位会随持仓变化在盘中移动。若要实时观察该标的结构的更新，请在交易终端中打开。')
        + ' ' + bi('Same subscription, two clocks — the Terminal is the live desk (tape, replay, alerts); this workspace is the settled record.',
          '同一订阅，两种时钟 — 交易终端是盘中实时台（逐笔、回放、警报）；本工作台是收盘后的定格记录。') + '</div></div>'
    + '<a class="oew-cta" href="' + esc(terminalUrl(tk)) + '" target="_blank" rel="noopener">'
      + bi('Open ' + tk + ' live in Terminal', '在交易终端打开 ' + tk + ' 实时行情') + ' ↗</a>'
  + '</div>';

  /* The shelf's charts are drawn on first open, from the gx payload already in
     hand. Bound HERE rather than delegated: renderTicker replaces this subtree on
     every ticker change, so the listener dies with the node it was bound to and
     can never fire against a previous name's payload. */
  if(host.querySelector){
    var shelf = host.querySelector('#oew-shelf');
    if(shelf) shelf.addEventListener('toggle', function(){
      var slot = shelf.querySelector('#oew-raw-slot');
      if(!shelf.open || !slot || slot.innerHTML) return;
      slot.innerHTML = rawShelfBody(gx);
    });
  }
  // illus.js's IntersectionObserver already scanned the page before this innerHTML
  // write landed the filmstrip's .ilx figure, so the reveal must be requested
  // explicitly (W1_DESIGN_SPEC.md §0.17 — the same pattern dialogs already use).
  if(window.ilxReveal) window.ilxReveal(host);
}

/* ══════════ LEADERS ══════════ */
/* Leg names are the EXISTING plain-word copy from templates/flow_leaders.html.j2
   (A_LEGS / B_LEGS, shipped in #3224). Nothing new is written here. */
var A_LEGS = [
  ['A1_flow_recur','Money keeps showing up','资金反复出现'],
  ['A2_flow_z_hot','Unusually heavy premium','权利金异常放大'],
  ['A3_oi_confirmed','New positions opened','建立新仓位'],
  ['A4_ts_breadth','Spread across expirations','多个到期日铺开'],
  ['A5_price_leader','Price is leading','价格领先'],
  ['A6_near_high','Near 52-week high','接近52周高点'],
  ['A7_vol_confirm','Volume confirms','成交量确认'],
  ['A8_not_trap','Not a failed breakout','非假突破']
];
var B_LEGS = [
  ['B1_washout_recent','Recently washed out','近期洗盘'],
  ['B2_oversold_osc','Oversold','超卖'],
  ['B3_turn_organ','Turn signal is on','拐点信号已亮'],
  ['B5_flow_inflect','Money flipped positive','资金转为流入'],
  ['B6_oi_confirmed','New positions opened','建立新仓位'],
  ['B7_vol_confirm','Volume confirms','成交量确认'],
  ['B8_not_trap','Not a failed breakout','非假突破']
];
/* Hover is PER-LADDER, not per-dot: composed exactly as the #3224 macro does. */
function ladder(row, legs){
  var segs = '', litEn = [], litZh = [], missEn = [], missZh = [], nOn = 0, nAvail = 0;
  legs.forEach(function(L){
    var v = row[L[0]];
    if(v === null || v === undefined){ segs += '<i class="oew-lseg nul"></i>'; return; }
    if(v){ segs += '<i class="oew-lseg on"></i>'; litEn.push(L[1]); litZh.push(L[2]); nOn++; nAvail++; }
    else  { segs += '<i class="oew-lseg off"></i>'; missEn.push(L[1]); missZh.push(L[2]); nAvail++; }
  });
  var tEn = nOn + ' of ' + nAvail + ' signs confirming'
    + (litEn.length ? '  ·  ' + litEn.join(' · ') : '')
    + (missEn.length ? '.  Not yet — ' + missEn.join(' · ') : '');
  var tZh = nAvail + ' 项信号中 ' + nOn + ' 项确认'
    + (litZh.length ? '：' + litZh.join('、') : '')
    + (missZh.length ? '。尚缺：' + missZh.join('、') : '');
  return '<span class="oew-ladder" role="img" aria-label="' + esc(tEn) + '" data-tip-en="' + esc(tEn)
    + '" data-tip-zh="' + esc(tZh) + '">' + segs + '</span><span class="oew-ld-kn">' + nOn + '/' + nAvail + '</span>';
}
var CAU = {
  earnings_window: ['Earnings soon','临近财报', true,
    'Within about two weeks of earnings — options flow around earnings is often an event bet, not a conviction position.',
    '距财报约两周内 — 财报前后的期权资金常是押注事件，而非坚定持仓。'],
  vol_trade: ['Both sides','双向押注', false,
    'Calls and puts both heavy the same day — may be a volatility bet, not a directional one.',
    '同日看涨与看跌均放量 — 可能是波动率押注，而非方向性押注。'],
  protective_put: ['Looks hedged','疑似对冲', false,
    'Far-out-of-the-money put flow dominant — this looks more like hedging than a bullish position.',
    '远价外看跌期权资金主导 — 更像对冲，而非看多布局。'],
  gamma_caution: ['Fragile tape','盘面脆弱', false,
    'Short-gamma regime around this name — price can whip around, so the flow read is less stable.',
    '该标的处于负Gamma环境 — 价格易剧烈波动，资金解读稳定性较低。']
};
/* Client-side twin of build_options_command.py's _ZERODTE_TIP_EN/_ZERODTE_TIP_ZH
   — same wording verbatim.  Plain words only: the acronym this tip used to
   carry is banned on the glance tier AND the hover tier of this workspace.
   These bytes ship to the browser, so the comment does not name it either. */
var ZDTE = ['Same-day heavy','当日到期为主', false,
  'Same-day contracts are usually day-trading, not positioning for a move.',
  '当日到期合约通常用于日内交易，而非布局趋势。'];
function cauChip(c){
  return '<span class="cau' + (c[2] ? ' cau-warn' : '') + '" data-tip-en="' + esc(c[3]) + '" data-tip-zh="' + esc(c[4]) + '">'
    + bi(c[0], c[1]) + '</span>';
}
/* State chip rule reused verbatim from templates/flow_leaders.html.j2:343-345. */
function ldState(row, fireKey){
  var rc = num(row.recurrence_count);
  if(row[fireKey]) return ['ld-lining','Lining up','信号齐备'];
  if(rc !== null && rc >= 4) return ['ld-crowd','Crowding in','资金涌入'];
  return ['ld-radar','On the radar','雷达关注'];
}
/* Rows past `shown` ship HIDDEN, not withheld: the payload is already in hand
   (the builder no longer caps the boards), so the expander is a class toggle —
   no second fetch, no re-render, and the count in its label is the real length
   of the array behind it. */
function ldRows(rows, legs, fireKey, ctx, shown){
  return rows.map(function(r, i){
    var st = ldState(r, fireKey);
    var de = r.de_escalation || {};
    var caus = '';
    Object.keys(CAU).forEach(function(k){ if(de[k]) caus += cauChip(CAU[k]); });
    if(r.zerodte_dominated) caus += cauChip(ZDTE);
    var c = ctx(r);
    return '<div class="oew-ldrow' + ((shown && i >= shown) ? ' oew-ld-more' : '') + '">'
      + '<span class="oew-ld-rank">' + ('0' + (i+1)).slice(-2) + '</span>'
      + '<span class="oew-ld-tk"><span class="sym">' + esc(r.ticker) + '</span>'
        + '<span class="sec">' + esc(r.sector || '') + '</span></span>'
      + '<span class="oew-ld-state ' + st[0] + '">' + bi(st[1], st[2]) + '</span>'
      + '<span>' + ladder(r, legs) + '</span>'
      + '<span class="oew-ld-right"><span class="oew-ld-ctx">' + bi(c[0], c[1]) + '</span>' + caus + '</span>'
    + '</div>';
  }).join('');
}
function renderLeaders(host, L){
  if(!L){ host.innerHTML = emptyPanel('The leader boards did not report for this close.',
    '本次收盘没有领头股榜单数据。'); return; }
  var boardAAll = L.board_a || [];
  var LD_SHOWN = 12;
  /* Board B admission mirrors the builder's own corrected rule (#3496): B5, the
     washout-flip verdict — NOT days_since_inflection, which stays populated for
     stale flips so the freshness column can tell the truth about them. */
  var boardBFiltered = (L.board_b || []).filter(function(r){ return r.B5_flow_inflect; });
  /* MAJOR-1 fix (PR #4123 adversarial review round 2): the denominator must equal
     what site/flow_leaders.html actually renders — never the payload's own
     pre-cap "board_a_total"/"board_b_total" fields. Both are computed by
     scripts/build_flow_leaders.py BEFORE its top-25 slice (measured:
     board_a_total 130 while board_a itself ships 25 rows), and board_b_total is
     additionally unfiltered by B5_flow_inflect while this panel's own numerator
     (and flow_leaders.html.j2's) is filtered. templates/flow_leaders.html.j2
     iterates `board_a` (fl.board_a, this SAME post-cap array) and the
     B5_flow_inflect-filtered `board_b` in full, with no further slice — so each
     array's own pre-slice(0,12) length IS the true "of N" by construction, and
     can never drift from the linked page the way a separately-tracked total can.

     W1.6-A keeps this derivation unchanged and it now has a second job: with the
     builder's own top-25 cap gone, these lengths ARE the full boards, so they are
     both the "of N" in the subtitle and the N in the expander's label — one
     number, two places, no way for them to disagree. */
  var aTotal = boardAAll.length;
  var bTotal = boardBFiltered.length;
  /* The expander: hidden rows are already rendered, so this is a class toggle.
     Withheld when there is nothing to expand — a button that opens nothing is a
     worse lie than no button. */
  function ldExpander(id, total){
    if(total <= LD_SHOWN) return '';
    return '<button class="oew-ld-exp" type="button" data-expand="' + id + '" data-total="' + total + '"'
      + ' aria-expanded="false"><span class="l-en">Show all ' + total + '</span>'
      + '<span class="l-zh">显示全部 ' + total + ' 项</span></button>';
  }
  var etf = L.etf_strip || [];
  var asof = (L.as_of || '').slice(0, 10);
  var stamp = asof ? '<span class="oew-asof mono">' + esc(asof) + '</span>' : '';
  var stale = L.stale ? '<div class="oew-banner"><span class="ico">!</span><span>'
    + bi('These boards are from an earlier session. Showing them anyway — treat the names as stale.',
         '这些榜单来自更早的场次。仍予显示 — 请将标的视为陈旧。') + '</span></div>' : '';

  host.innerHTML = stale
  + '<div class="oew-panel">'
    + '<div class="oew-phead">'
      + '<h2 class="oew-ph-title">' + bi('Money keeps showing up','资金反复出现') + '</h2>'
      + '<span class="oew-ph-sub">' + bi('top 12 of ' + aTotal + ', by recurrence', '按出现频率排序，前12（共 ' + aTotal + '）') + '</span>'
      + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
        + ' data-tip-en="Each bar in the row is one sign we check. A filled bar means that sign is confirming right now; an empty bar means it is not; a dotted bar means the data for it has not arrived. Hover the bars to see which is which. More filled bars means more agreement — it does not mean a stronger expected return."'
        + ' data-tip-zh="每行中的每个方块代表我们检查的一项信号。实心表示该信号当前确认，空心表示尚未确认，虚线边框表示数据尚未到位。将鼠标悬停在方块上可查看具体项目。实心越多表示信号越一致 — 但并不代表预期收益更高。">?</span></div>'
    + '</div>'
    + (aTotal ? '<div class="oew-pbody" style="padding:0"><div class="oew-ld" id="oew-ld-a">'
        + ldRows(boardAAll, A_LEGS, 'fire_a', function(r){
            var rc = num(r.recurrence_count);
            return rc === null ? ['building history','积累历史中']
                               : [rc.toFixed(0) + ' of the last 10 days', '近10日中有' + rc.toFixed(0) + '日'];
          }, LD_SHOWN)
        + '</div>' + ldExpander('oew-ld-a', aTotal) + '</div>'
      : '<div class="oew-pbody"><p class="oew-empty">' + bi('No names yet — options-flow sessions are still accruing.',
          '暂无标的 — 期权资金流场次仍在积累。') + '</p></div>')
    + '<div class="oew-pfoot">'
      + '<span class="oew-stance st-watch">' + bi("Watch — don't chase",'观察—勿追高') + '</span>'
      + '<span>' + bi('Repeated buying marks where attention is, not where the edge is. Names here are a place to start reading, not a queue to buy.',
          '反复买入标记的是关注度所在，而非优势所在。此处的标的是研究的起点，而非买入队列。') + '</span>'
      + stamp
    + '</div>'
  + '</div>'

  + '<div class="oew-panel">'
    + '<div class="oew-phead">'
      + '<h2 class="oew-ph-title">' + bi('Turned back up after a washout','洗盘后重新转强') + '</h2>'
      + '<span class="oew-ph-sub">' + bi('top 12 of ' + bTotal + ', most recent first', '最新转向在前，前12（共 ' + bTotal + '）') + '</span>'
    + '</div>'
    + (bTotal ? '<div class="oew-pbody" style="padding:0"><div class="oew-ld" id="oew-ld-b">'
        + ldRows(boardBFiltered, B_LEGS, 'fire_b', function(r){
            var d = num(r.days_since_inflection);
            if(d === null) return ['turned up recently','近期转强'];
            return d === 0 ? ['turned up today','今日转强']
                           : [d.toFixed(0) + ' day' + (d === 1 ? '' : 's') + ' ago', d.toFixed(0) + '日前转强'];
          }, LD_SHOWN)
        + '</div>' + ldExpander('oew-ld-b', bTotal) + '</div>'
      : '<div class="oew-pbody"><p class="oew-empty">' + bi('No fresh turns in this close.',
          '本次收盘没有新的转向。') + '</p></div>')
    + '<div class="oew-pfoot">'
      + '<span class="oew-stance st-ready">' + bi('Get ready','做好准备') + '</span>'
      + '<span>' + bi('A turn this fresh can fail. Wait for it to hold rather than buying the first green day.',
          '如此新近的转向可能失败。应等待其站稳，而非在第一个上涨日买入。') + '</span>'
      + stamp
    + '</div>'
  + '</div>'

  + (etf.length ? '<div class="oew-panel">'
    + '<div class="oew-phead">'
      + '<h2 class="oew-ph-title">' + bi('Sector ETF flows','板块 ETF 资金') + '</h2>'
      + '<span class="oew-ph-sub">' + bi('creation / redemption estimate','申购赎回估算') + '</span>'
    + '</div>'
    + '<div class="oew-pbody"><div class="oew-etf">'
      + etf.map(function(e){
          var v = num(e.net_premium_mn);
          return '<div class="oew-etfc"><div class="sym">' + esc(e.ticker) + '</div>'
            + '<div class="v ' + ((v || 0) >= 0 ? 'pos' : 'neg') + ' mono">' + smoney(v) + '</div>'
            + '<div class="n">' + bi('net premium','净权利金') + '</div></div>';
        }).join('')
    + '</div></div>'
    + '<div class="oew-pfoot">'
      + '<span class="oew-stance st-ignore">' + bi('Ignore','忽略') + '</span>'
      + '<span>' + bi('These are estimates, not reported fund flows. Useful as a background check, not as a signal.',
          '这些是估算值，而非公布的基金流量。可作背景参考，不构成信号。') + '</span>'
      + stamp
    + '</div>'
  + '</div>' : '');
}

/* ══════════ mode switching + routing ══════════ */
function loadMode(mode){
  var host = document.getElementById('mode-' + mode);
  if(!host) return;
  // OIP W1 §0.15: Ticker mode's render target is #oew-tk-body, a sibling of the
  // static search toolbar — NEVER #mode-ticker itself, which would wipe the
  // toolbar (and re-trigger its "/" focus race) on every skeleton paint and every
  // ticker change.
  var tgt = (mode === 'ticker') ? (document.getElementById('oew-tk-body') || host) : host;
  tgt.innerHTML = skeleton(SKEL[mode][0], SKEL[mode][1]);
  var fail = function(){
    tgt.innerHTML = emptyPanel('That data did not load. Reload the page to try again — nothing above depends on it.',
      '该数据未能加载。请重新加载页面重试 — 上方内容不依赖于它。');
  };
  if(mode === 'flow'){
    /* Both stores are lazy and BOTH are optional: cohorts.json missing costs the
       theme-group panel and nothing else (renderFlow falls back to flow_desk's
       own cohorts array), while flow_desk.json missing is what `fail` is for. */
    Promise.all([
      getJSON('flow_desk.json'),
      getJSON('flowdata/cohorts.json').catch(function(){ return null; })
    ]).then(function(res){ renderFlow(tgt, res[0], res[1]); loaded.flow = true; }).catch(fail);
  } else if(mode === 'scanner'){
    getJSON('screenerdata/rows.json').then(function(j){ renderScanner(tgt, j); loaded.scanner = true; }).catch(fail);
  } else if(mode === 'leaders'){
    getJSON('flowleaders/leaders.json').then(function(j){ renderLeaders(tgt, j); loaded.leaders = true; }).catch(fail);
  } else if(mode === 'ticker'){
    var tk = curTicker;
    Promise.all([
      getJSON('gex/' + encodeURIComponent(tk) + '.json').catch(function(){ return null; }),
      getJSON('flow/' + encodeURIComponent(tk) + '.json').catch(function(){ return null; }),
      // OIP W1 §3.5/§7: additive third fetch, same .catch(() => null) pattern as
      // the flow fetch above — a 404 (outside the digest's coverage, or before the
      // first nightly populates the store) degrades the filmstrip to its honest-
      // null variant and changes nothing else on the page.
      getJSON('session/' + encodeURIComponent(tk) + '.json').catch(function(){ return null; })
    ]).then(function(res){
      renderTicker(tgt, tk, res[0], res[1], res[2]);
      loaded.ticker = tk;
      var c = document.getElementById('oew-tk-cnt'); if(c) c.textContent = tk;
    }).catch(fail);
  }
}
function activate(mode, opts){
  if(MODES.indexOf(mode) < 0) mode = 'brief';
  tabs.forEach(function(t){ t.setAttribute('aria-selected', String(t.getAttribute('data-mode') === mode)); });
  MODES.forEach(function(m){
    var s = document.getElementById('mode-' + m);
    if(s) s.classList.toggle('active', m === mode);
  });
  var need = (mode === 'ticker') ? (loaded.ticker !== curTicker) : !loaded[mode];
  if(need) loadMode(mode);
  /* BL-1: a langchange/themechange that fired while Flow was display:none hit
     the canvases' zero-size guard and drew nothing — returning to the tab then
     showed the OLD palette (a rising tide stayed green under zh). Canvas draws
     are one-shot and cheap, so re-entering an already-loaded Flow always
     repaints; the draw functions no-op when the canvases are absent. */
  if(mode === 'flow' && !need) { flDrawSpark(); flDrawUnfold(); }
  if(!opts || !opts.silent){
    try{ history.replaceState(null, '', '#' + mode + (mode === 'ticker' ? '?t=' + curTicker : '')); }catch(e){}
  }
}
tabs.forEach(function(t){
  t.addEventListener('click', function(){ activate(t.getAttribute('data-mode')); });
});
/* ticker deep-links from the Brief rail and the Scanner table */
document.addEventListener('click', function(e){
  var b = e.target.closest && e.target.closest('[data-goto]');
  if(!b) return;
  e.preventDefault();
  curTicker = b.getAttribute('data-goto') || curTicker;
  activate('ticker');
  window.scrollTo({ top: 0, behavior: 'smooth' });
});
/* scanner controls (delegated — the table is rendered after this binds) */
document.addEventListener('click', function(e){
  var seg = e.target.closest && e.target.closest('.oew-seg button[data-view]');
  if(seg){
    seg.parentNode.querySelectorAll('button').forEach(function(x){ x.setAttribute('aria-pressed', String(x === seg)); });
    var tbl = document.querySelector('.oew-tbl');
    if(tbl) tbl.setAttribute('data-view', seg.getAttribute('data-view'));
    return;
  }
  var p = e.target.closest && e.target.closest('.oew-preset');
  if(p){
    p.parentNode.querySelectorAll('.oew-preset').forEach(function(x){ x.setAttribute('aria-pressed', String(x === p)); });
    scPreset = p.getAttribute('data-preset');
    /* "Premium leaders" IS an ordering (the screener's own applyPreset sets
       sortCol=gross_premium_mn desc for it) — without this reset the chip
       lights up over whatever column the reader last sorted, a no-op that
       mislabels the board. The other presets are filters and keep the sort. */
    if(scPreset === 'premium') scSort = scSortDefault();
    scRepaint();
    return;
  }
  /* per-column sort. First click on a new column sorts DESCENDING (the useful
     end of a screen is the top of the range), then toggles. */
  var th = e.target.closest && e.target.closest('.oew-tbl thead th[data-sort]');
  if(th){
    var key = th.getAttribute('data-sort'), idx = parseInt(th.getAttribute('data-i'), 10);
    /* toggle on the KEY: the same field's header in another view is the same
       sort, and treating it as fresh reset the direction instead of flipping */
    if(scSort.key === key) scSort.dir = (scSort.dir === 'desc') ? 'asc' : 'desc';
    else { scSort.key = key; scSort.idx = idx; scSort.dir = 'desc'; }
    scRepaint();
    return;
  }
  if(e.target.closest && e.target.closest('#oew-sc-csv')){ scExportCSV(); return; }
  if(e.target.closest && e.target.closest('#oew-f-clear')){
    var more = document.getElementById('oew-sc-more');
    if(more){
      more.querySelectorAll('input').forEach(function(el){ el.value = ''; });
      more.querySelectorAll('select').forEach(function(el){ el.value = ''; });
    }
    /* MI-4: "Clear all" means the full board — a preset left armed kept
       silently filtering after the inputs blanked, with no lit control
       explaining why. Reset to the default ordering preset and relight it. */
    scPreset = 'premium'; scSort = scSortDefault();
    document.querySelectorAll('.oew-preset').forEach(function(x){
      x.setAttribute('aria-pressed', String(x.getAttribute('data-preset') === 'premium'));
    });
    scRepaint();
    return;
  }
  /* Leaders "show all N" — a class toggle over rows already in the DOM. */
  var ex = e.target.closest && e.target.closest('[data-expand]');
  if(ex){
    var list = document.getElementById(ex.getAttribute('data-expand'));
    if(!list) return;
    var open = !list.classList.contains('on');
    list.classList.toggle('on', open);
    ex.setAttribute('aria-expanded', String(open));
    ex.innerHTML = open
      ? '<span class="l-en">Fold back</span><span class="l-zh">收起</span>'
      : '<span class="l-en">Show all ' + esc(ex.getAttribute('data-total')) + '</span>'
        + '<span class="l-zh">显示全部 ' + esc(ex.getAttribute('data-total')) + ' 项</span>';
  }
});
/* Filter inputs are live: typing or stepping a range repaints the table. Bound
   on the document because the disclosure is rendered after this runs. */
document.addEventListener('input', function(e){
  var t = e.target;
  if(!t || !t.id || t.id.indexOf('oew-f-') !== 0) return;
  scRepaint();
});
document.addEventListener('change', function(e){
  var t = e.target;
  if(!t || t.id !== 'oew-f-sector') return;
  scRepaint();
});
/* Keyboard parity for the sort headers: they are <th> elements with tabindex,
   so Enter/Space must do what a click does. */
document.addEventListener('keydown', function(e){
  if(e.key !== 'Enter' && e.key !== ' ') return;
  var th = e.target && e.target.closest && e.target.closest('.oew-tbl thead th[data-sort]');
  if(!th) return;
  e.preventDefault();
  th.click();
});

/* OIP W1 §2: Ticker-mode search/typeahead — exact parity with gex.html's #gx-q
   (site/gex.js setupSearch, ~line 282) — same match predicate, same 12-row cap,
   same keyboard model, same mousedown-not-click row selection (survives the
   input's own blur handler), same 150ms blur-close delay. #oew-tk-q is STATIC
   markup present from first paint (§0.15's toolbar-as-sibling fix), so this binds
   ONCE here — never inside renderTicker(), which would re-bind on every ticker
   change exactly the class of bug that fix exists to avoid. */
function setupTickerSearch(){
  var inp = document.getElementById('oew-tk-q'), sg = document.getElementById('oew-tk-sugg');
  if(!inp || !sg) return;
  var M = window.OEW_TICKER_MANIFEST || [];
  var hl = -1, shown = [];
  function close(){ sg.classList.remove('on'); inp.setAttribute('aria-expanded', 'false'); hl = -1; }
  function render(q){
    q = q.trim().toUpperCase();
    shown = M.filter(function(m){
      return !q || m.key.indexOf(q) === 0 || m.key.indexOf(q) >= 0 || (m.en || '').toUpperCase().indexOf(q) >= 0;
    }).slice(0, 12);
    if(!shown.length){ close(); return; }
    sg.innerHTML = shown.map(function(m, i){
      return '<div class="row' + (i === hl ? ' hl' : '') + '" data-key="' + esc(m.key) + '" role="option">'
        + '<span><b>' + esc(m.key) + '</b> <span class="g">' + bi(m.en || m.key, m.zh || m.en || m.key) + '</span></span>'
      + '</div>';
    }).join('');
    sg.classList.add('on'); inp.setAttribute('aria-expanded', 'true');
    sg.querySelectorAll('.row').forEach(function(r){
      r.addEventListener('mousedown', function(e){
        e.preventDefault();
        curTicker = r.getAttribute('data-key') || curTicker;
        activate('ticker');
        inp.value = ''; close();
      });
    });
  }
  inp.addEventListener('input', function(){ hl = -1; render(inp.value); });
  inp.addEventListener('focus', function(){ render(inp.value); });
  inp.addEventListener('blur', function(){ setTimeout(close, 150); });
  inp.addEventListener('keydown', function(e){
    if(!sg.classList.contains('on')) return;
    if(e.key === 'ArrowDown'){ hl = Math.min(shown.length - 1, hl + 1); render(inp.value); e.preventDefault(); }
    else if(e.key === 'ArrowUp'){ hl = Math.max(0, hl - 1); render(inp.value); e.preventDefault(); }
    else if(e.key === 'Enter'){
      var pick = shown[hl < 0 ? 0 : hl];
      if(pick){ curTicker = pick.key; activate('ticker'); inp.value = ''; close(); }
    }
    else if(e.key === 'Escape'){ close(); }
  });
  // §0.16: gex.html's sitewide .nav-search has zero "/" bindings (verified by
  // grep), so this cannot collide with it — but it must still fire ONLY while
  // Ticker mode's panel is active, or an unconditional binding would silently
  // focus an off-screen, inactive tab's input.
  document.addEventListener('keydown', function(e){
    if(e.key !== '/') return;
    if(/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || '')) return;
    var section = document.getElementById('mode-ticker');
    if(!section || !section.classList.contains('active')) return;
    inp.focus(); e.preventDefault();
  });
}
setupTickerSearch();

/* The Brief's Terminal CTA, re-pointed through the house helper.
   It CANNOT be done inline above: theme.js is the last body script, so
   window.MDXTerminal does not exist while this IIFE runs. DOMContentLoaded fires
   after every synchronous body script has executed, which is exactly the moment
   the helper becomes available. The baked href stays a working destination the
   whole time — this only adds the &from=macro/&ret= stamp. */
function wireBriefCta(){
  var a = document.getElementById('oew-brief-cta');
  if(a) a.href = terminalUrl('');
  scApplyLang();
}
if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireBriefCta);
else wireBriefCta();

/* Canvas cannot resolve a CSS variable, so the two tide curves are the only
   things on this page that must be REDRAWN when the language flips (--up/--down
   swap to 红涨绿跌) or the box is resized. Not animation — one repaint per
   event, and only while Flow mode has already rendered. */
var flRsz;
window.addEventListener('resize', function(){
  clearTimeout(flRsz);
  flRsz = setTimeout(function(){ flDrawSpark(); flDrawUnfold(); }, 120);
});
document.addEventListener('langchange', function(){
  setTimeout(function(){ flDrawSpark(); flDrawUnfold(); scApplyLang(); }, 0);
});
/* Dark↔light re-tunes --up/--down/--line, and canvases hold resolved pixels —
   same repaint contract as langchange (theme.js dispatches both). */
document.addEventListener('themechange', function(){
  setTimeout(function(){ flDrawSpark(); flDrawUnfold(); }, 0);
});

/* Terminal handoff clock — computed at READ time, never baked. A countdown
   frozen into static HTML is wrong by morning. */
(function(){
  var el = document.getElementById('oew-clock');
  if(!el) return;
  var now = new Date();
  var etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  var open = new Date(etNow); open.setHours(9, 30, 0, 0);
  while(open <= etNow || open.getDay() === 0 || open.getDay() === 6){
    open.setDate(open.getDate() + 1); open.setHours(9, 30, 0, 0);
  }
  var mins = Math.max(0, Math.round((open - etNow) / 60000));
  var h = Math.floor(mins / 60), m = mins % 60;
  el.innerHTML = '<span class="l-en">closed 16:00 ET · next open in ' + h + 'h ' + m + 'm</span>'
    + '<span class="l-zh">美东 16:00 收盘 · 距下次开盘 ' + h + ' 小时 ' + m + ' 分</span>';
})();

/* hash routing: #brief / #scanner / #ticker?t=SYM / #leaders */
(function(){
  var h = (location.hash || '').replace('#', '');
  var mode = h.split('?')[0];
  var q = h.indexOf('?t=');
  if(q > -1) curTicker = decodeURIComponent(h.slice(q + 3)).toUpperCase() || curTicker;
  var qs = new URLSearchParams(location.search);
  if(qs.get('t')) curTicker = qs.get('t').toUpperCase();
  if(MODES.indexOf(mode) >= 0 && mode !== 'brief') activate(mode, { silent: true });
})();
})();

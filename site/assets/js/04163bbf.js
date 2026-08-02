
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
var MODES = ['brief','scanner','ticker','leaders'];
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
  scanner: ['Loading the screener table for this close…', '正在加载本次收盘的筛选表…'],
  ticker:  ["Loading this name's options structure…", '正在加载该标的的期权结构…'],
  leaders: ['Loading the leader boards…', '正在加载领头股榜单…']
};

function getJSON(url){
  if(cache[url]) return Promise.resolve(cache[url]);
  return fetch(url, { credentials:'same-origin' }).then(function(r){
    if(!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(j){ cache[url] = j; return j; });
}

/* ══════════ SCANNER ══════════ */
var SC_COLS = [
  ['c-ovr','',       'Spot','现价'],
  ['c-ovr','',       'IV 30d','30日隐波'],
  ['c-ovr','hide-sm','IV rank','隐波分位'],
  ['c-ovr','',       'Expected move','预期波幅'],
  ['c-ovr','hide-sm','Put/call OI','认沽认购持仓比'],
  ['c-ovr','hide-sm','Volume','成交量'],
  ['c-ovr','',       'Premium','权利金'],
  ['c-flow','',      'Net premium','净权利金'],
  ['c-flow','',      'Same-day share','当日到期占比'],
  ['c-flow','hide-sm','Volume','成交量'],
  ['c-flow','',      'Premium','权利金'],
  ['c-pos','',       'Spot','现价'],
  ['c-pos','',       'From flip','距翻转位'],
  ['c-pos','hide-sm','Ceiling','上方墙'],
  ['c-pos','hide-sm','Floor','下方墙'],
  ['c-pos','',       'Behaviour','表现'],
  ['','',            'Tone','方向'],
  ['','',            'Data age','数据新鲜度']
];
/* Preset values are the options_screener page's OWN shipped thresholds — reused,
   never reinvented (templates/options_screener.html.j2 applyPreset). */
var SC_PRESETS = [
  ['premium',  'Premium leaders','权利金居前'],
  ['volsurge', 'Volume surge','成交激增'],
  ['highrank', 'Expensive options','期权偏贵'],
  ['zerodte',  'Same-day heavy','当日到期为主'],
  ['putskew',  'Downside cover bid','下行保护受追捧'],
  ['nearflip', 'Near a flip level','接近翻转位']
];
var scRows = [], scPreset = 'premium', scSkew75 = null, scAsof = null;

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
function scFilter(rows){
  if(scPreset === 'volsurge') return rows.filter(function(r){ return num(r.rel_volume) !== null && num(r.rel_volume) >= 2; });
  if(scPreset === 'highrank') return rows.filter(function(r){ return num(r.iv_rank) !== null && num(r.iv_rank) >= 80; });
  if(scPreset === 'zerodte')  return rows.filter(function(r){ return num(r.zerodte_share) !== null && num(r.zerodte_share) >= 60; });
  if(scPreset === 'nearflip') return rows.filter(function(r){ var d = num(r.dist_to_flip_pct); return d !== null && Math.abs(d) <= 1; });
  if(scPreset === 'putskew'){
    if(scSkew75 === null){
      var vals = rows.map(function(r){ return num(r.skew_pp); }).filter(function(v){ return v !== null; }).sort(function(a,b){ return a-b; });
      scSkew75 = vals.length ? vals[Math.floor(vals.length * 0.75)] : 0;
    }
    return rows.filter(function(r){ return num(r.skew_pp) !== null && num(r.skew_pp) >= scSkew75; });
  }
  return rows.slice();
}
function scBody(){
  var rows = scFilter(scRows).sort(function(a,b){ return (num(b.gross_premium_mn)||0) - (num(a.gross_premium_mn)||0); }).slice(0, 200);
  if(!rows.length) return '<tr><td colspan="19" class="left"><span class="oew-empty">'
    + bi('No name in this close matched that view. Pick another chip to widen the list.',
         '本次收盘没有符合该视图的标的。选择其他标签可扩大范围。')
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
function scHead(){
  var h = '<th class="left">' + bi('Name','标的') + '</th>';
  SC_COLS.forEach(function(c){
    h += '<th class="' + c[0] + (c[1] ? ' ' + c[1] : '') + '">' + bi(c[2], c[3]) + '</th>';
  });
  return h;
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
        // §0.20 fix: "Top 200" is only true when the table's own .slice(0, 200)
        // (scBody(), above) actually truncates something — otherwise every row
        // on file is already shown, and the cap language is the exact
        // undeclared-cap-shaped lie this sentence exists to prevent.
        + '<span class="oew-ph-sub">' + (rows.length > 200
            ? bi('Top 200 by premium, sorted', '按权利金排序，前200')
            : bi(rows.length + ' names, sorted by premium', rows.length + ' 个标的，按权利金排序')) + '</span>'
        + '<a class="oew-ph-more" href="options_screener.html">' + bi('Open the full screener for all ' + rows.length, '打开完整筛选台，查看全部 ' + rows.length) + ' ↗</a>'
        + '<span class="oew-help" tabindex="0" role="button"'
          + ' data-tip-en="Chains are snapshots taken after the close. Implied volatility, walls and max-pain come from those snapshots; volume and premium come from the day’s tape. IV rank compares today with the history we hold for that name, so a name we have tracked only briefly has a short history behind its number. Direction is approximate; size is reliable."'
          + ' data-tip-zh="期权链为收盘后的快照。隐含波动率、墙位与最大痛点来自这些快照；成交量与权利金来自当日逐笔。隐波分位将今日与我们持有的该标的历史比较，因此跟踪时间较短的标的，其数字背后的历史也较短。方向为近似值，规模数据可靠。">?</span>'
        + '<div class="oew-ph-right"><span class="oew-seg">'
          + '<button type="button" data-view="ovr" aria-pressed="true">' + bi('Overview','总览') + '</button>'
          + '<button type="button" data-view="flow" aria-pressed="false">' + bi('Flow','资金') + '</button>'
          + '<button type="button" data-view="pos" aria-pressed="false">' + bi('Positioning','持仓结构') + '</button>'
        + '</span></div>'
      + '</div>'
      + '<div class="tbl-scroll oew-tblwrap"><table class="oew-tbl" data-view="ovr">'
        + '<thead><tr>' + scHead() + '</tr></thead><tbody id="oew-sc-body">' + scBody() + '</tbody>'
      + '</table></div>'
      + '<div class="oew-pfoot">'
        + '<span class="oew-stance st-aside">' + bi('Stand aside','暂时观望') + '</span>'
        + '<span>' + bi('A screen is a starting list, not a ranking. Nothing here is scored or ordered by expected return.',
            '筛选结果是起始清单，而非排名。此处没有任何内容按预期收益评分或排序。') + '</span>'
        + (scAsof ? '<span class="oew-asof mono">' + esc(scAsof) + '</span>' : '')
      + '</div>'
    + '</div>';
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

  + '<details class="oew-panel oew-shelf">'
    + '<summary>' + bi('Under the hood — the raw options structure','底层数据 — 原始期权结构') + '</summary>'
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
    + '</div>'
  + '</details>'

  + '<div class="oew-handoff">'
    + '<div><div class="oew-ho-t">' + bi('These levels are frozen until tomorrow','这些水位在明日前保持不变') + '</div>'
      + '<div class="oew-ho-s">' + bi('Walls move during the session as positions change. To watch this name’s structure update live, open it in the Terminal.',
          '墙位会随持仓变化在盘中移动。若要实时观察该标的结构的更新，请在交易终端中打开。') + '</div></div>'
    + '<a class="oew-cta" href="https://app.mastermind-x.com/?symbol=' + encodeURIComponent(tk) + '" target="_blank" rel="noopener">'
      + bi('Open ' + tk + ' live in Terminal', '在交易终端打开 ' + tk + ' 实时行情') + ' ↗</a>'
  + '</div>';
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
function ldRows(rows, legs, fireKey, ctx){
  return rows.map(function(r, i){
    var st = ldState(r, fireKey);
    var de = r.de_escalation || {};
    var caus = '';
    Object.keys(CAU).forEach(function(k){ if(de[k]) caus += cauChip(CAU[k]); });
    if(r.zerodte_dominated) caus += cauChip(ZDTE);
    var c = ctx(r);
    return '<div class="oew-ldrow">'
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
  var A = boardAAll.slice(0, 12);
  /* Board B admission mirrors the builder's own corrected rule (#3496): B5, the
     washout-flip verdict — NOT days_since_inflection, which stays populated for
     stale flips so the freshness column can tell the truth about them. */
  var boardBFiltered = (L.board_b || []).filter(function(r){ return r.B5_flow_inflect; });
  var B = boardBFiltered.slice(0, 12);
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
     can never drift from the linked page the way a separately-tracked total can. */
  var aTotal = boardAAll.length;
  var bTotal = boardBFiltered.length;
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
      + '<a class="oew-ph-more" href="flow_leaders.html">' + bi('Open the full boards', '打开完整榜单') + ' ↗</a>'
      + '<div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"'
        + ' data-tip-en="Each bar in the row is one sign we check. A filled bar means that sign is confirming right now; an empty bar means it is not; a dotted bar means the data for it has not arrived. Hover the bars to see which is which. More filled bars means more agreement — it does not mean a stronger expected return."'
        + ' data-tip-zh="每行中的每个方块代表我们检查的一项信号。实心表示该信号当前确认，空心表示尚未确认，虚线边框表示数据尚未到位。将鼠标悬停在方块上可查看具体项目。实心越多表示信号越一致 — 但并不代表预期收益更高。">?</span></div>'
    + '</div>'
    + (A.length ? '<div class="oew-pbody" style="padding:0"><div class="oew-ld">'
        + ldRows(A, A_LEGS, 'fire_a', function(r){
            var rc = num(r.recurrence_count);
            return rc === null ? ['building history','积累历史中']
                               : [rc.toFixed(0) + ' of the last 10 days', '近10日中有' + rc.toFixed(0) + '日'];
          })
        + '</div></div>'
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
      + '<a class="oew-ph-more" href="flow_leaders.html">' + bi('Open the full boards', '打开完整榜单') + ' ↗</a>'
    + '</div>'
    + (B.length ? '<div class="oew-pbody" style="padding:0"><div class="oew-ld">'
        + ldRows(B, B_LEGS, 'fire_b', function(r){
            var d = num(r.days_since_inflection);
            if(d === null) return ['turned up recently','近期转强'];
            return d === 0 ? ['turned up today','今日转强']
                           : [d.toFixed(0) + ' day' + (d === 1 ? '' : 's') + ' ago', d.toFixed(0) + '日前转强'];
          })
        + '</div></div>'
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
  if(mode === 'scanner'){
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
    var body = document.getElementById('oew-sc-body');
    if(body) body.innerHTML = scBody();
  }
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

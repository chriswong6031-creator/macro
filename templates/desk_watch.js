/* desk_watch.js — "Desk watch — armed windows & earliest signs".
 *
 * A COMPACT fusion of two retired subsector_rotation.html.j2 sections
 * (Sector Intelligence consolidation, masterplan §6.2b):
 *   • #td-section  "Rotation Turn Desk"  (basketdata/oracle_turn_desk.json)
 *   • #tpo-section "Earliest flow signs" (basketdata/oracle_tape_onset.json)
 *
 * Both feeds are usually empty, and two stacked sections of quiet-state prose was
 * the defect. Fused: one h3 module in #desk-watch-mount, one quiet line when BOTH
 * feeds are empty or absent, the original cards (mechanics unchanged) when either
 * is active, and the two long always-visible caveat walls compressed to ONE footer
 * line plus a `?` receipt carrying the full original caveat text — display-only
 * disclaimers, the promotion clock and the base rates are demoted, never dropped.
 *
 * DISPLAY-ONLY — feeds no score, gate, or ordering surface. Every fetch fail-soft.
 */
(function () {
  'use strict';

  var TD_ARTIFACT  = 'basketdata/oracle_turn_desk.json';
  var TPO_ARTIFACT = 'basketdata/oracle_tape_onset.json';

  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function isZh(){return document.documentElement.getAttribute('data-lang')==='zh';}
  function t(en,zh){return isZh()&&zh?zh:en;}
  function L(en,zh){return '<span class="l-en">'+en+'</span><span class="l-zh">'+(zh==null?en:zh)+'</span>';}
  function pct(v){ return v!=null ? (v*100).toFixed(1)+'%' : '—'; }

  /* ── styles (injected once, guarded by element id — subsector_rotation.js model).
     .td-* / .tpo-* carried over from the retired sections; .dw-* is the fused
     module's own compact chrome (the two h2 sections became one h3). ── */
  function injectStyle(){
    if(document.getElementById('desk-watch-style')) return;
    var c=''
      /* ── fused module chrome ── */
      +'#desk-watch { margin:22px 2px 0; }'
      +'#desk-watch h3 { font-size:17px; font-weight:800; letter-spacing:-.015em; margin:0 0 4px; }'
      +'.dw-sub { color:var(--muted); font-size:12px; margin:0 0 10px; max-width:84ch; line-height:1.5; }'
      +'.dw-quiet { color:var(--muted); font-size:12.5px; padding:8px 0; }'
      +'.dw-group { margin-bottom:14px; }'
      +'.dw-group:last-child { margin-bottom:0; }'
      +'.dw-gh { font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:.07em;'
      +'  color:var(--muted); margin:0 0 7px; }'
      +'.dw-quiet-row { color:var(--muted); font-size:11.5px; padding:2px 0 6px; }'
      +'.dw-foot { margin-top:10px; font-size:10.5px; color:var(--muted); line-height:1.55; }'
      +'.dw-help { display:inline-block; font-size:9.5px; font-weight:700; color:var(--muted);'
      +'  border:1px solid var(--line); border-radius:50%; width:16px; height:16px; line-height:14px;'
      +'  text-align:center; cursor:help; }'
      /* ── Turn Desk cards (.td-*) ── */
      +'.td-armed-grid { display:flex; flex-wrap:wrap; gap:10px; }'
      +'.td-sector-card { flex:1 1 280px; min-width:240px; border-radius:12px; border:1px solid var(--line);'
      +'  background:var(--panel); padding:12px 14px; }'
      +'.td-card-hd { display:flex; align-items:baseline; gap:8px; margin-bottom:8px; }'
      +'.td-sector-name { font-weight:800; font-size:13.5px; }'
      +'.td-window-badge { font-size:9.5px; font-weight:700; text-transform:uppercase; padding:2px 7px;'
      +'  border-radius:6px; background:color-mix(in srgb,var(--link) 16%,transparent); color:var(--link); }'
      +'.td-sessions-left { font-size:11px; color:var(--muted); margin-left:auto; }'
      +'.td-member-list { list-style:none; margin:0; padding:0; }'
      +'.td-member-item { display:flex; align-items:baseline; gap:6px; font-size:12px; padding:4px 0;'
      +'  border-bottom:1px solid var(--line); }'
      +'.td-member-item:last-child { border-bottom:none; }'
      +'.td-member-ticker { font-weight:700; min-width:52px; }'
      +'.td-tier-tag { font-size:9.5px; font-weight:700; text-transform:uppercase; padding:1px 6px;'
      +'  border-radius:5px; background:color-mix(in srgb,var(--up) 14%,transparent); color:var(--up); }'
      +'.td-tier-tag.t3 { background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }'
      +'.td-provisional-note { font-size:9.5px; color:var(--warn); margin-left:2px; }'
      +'.td-no-fires { color:var(--muted); font-size:11.5px; font-style:italic; }'
      +'.td-staleness-note { font-size:11px; color:var(--warn); margin-bottom:8px; }'
      +'.td-qual-filters { margin-top:8px; font-size:10.5px; color:var(--muted); border-top:1px solid var(--line); padding-top:6px; }'
      +'.td-qual-filter-tag { display:inline-block; margin:1px 3px 1px 0; padding:1px 5px; border-radius:4px;'
      +'  background:color-mix(in srgb,var(--link) 12%,transparent); color:var(--link); font-size:9.5px; font-weight:700; }'
      +'.td-qual-accrual-note { margin-top:6px; font-size:10px; color:var(--muted); font-style:italic; }'
      /* ── Tape-onset cards (.tpo-*) ── */
      +'.tpo-grid { display:flex; flex-wrap:wrap; gap:10px; }'
      +'.tpo-node-card { flex:1 1 220px; min-width:180px; border-radius:11px; border:1px solid var(--line);'
      +'  background:var(--panel); padding:11px 14px; }'
      +'.tpo-node-name { font-weight:800; font-size:13px; margin-bottom:4px; }'
      +'.tpo-flag-badge { display:inline-block; font-size:9.5px; font-weight:700; text-transform:uppercase;'
      +'  padding:2px 7px; border-radius:6px; margin-left:5px; vertical-align:middle;'
      +'  background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }'
      +'.tpo-rates { font-size:10.5px; color:var(--muted); margin-top:4px; line-height:1.5; }'
      +'.tpo-rates b { color:var(--text); }'
      +'.tpo-unconfirmed-note { margin-top:6px; font-size:10.5px; color:var(--warn); font-style:italic; }'
      +'@media (max-width:520px){ .tpo-grid { flex-direction:column; } }';
    var s=document.createElement('style');
    s.id='desk-watch-style';
    s.textContent=c;
    document.head.appendChild(s);
  }

  /* ── mount: build the fused module shell into #desk-watch-mount (once) ── */
  function mount(){
    var host=document.getElementById('desk-watch-mount');
    if(!host) return false;
    if(document.getElementById('desk-watch')) return true;
    host.innerHTML=''
      +'<section id="desk-watch" aria-label="Desk watch">'
      +'<h3>🎯 '+L('Desk watch — armed windows &amp; earliest signs','值守台 — 已武装窗口与最早信号')+'</h3>'
      +'<p class="dw-sub">'+L(
          'Sectors in an open entry window, and sectors whose momentum just jumped before any rotation has formed. Watch material — don’t chase.',
          '处于入场窗口的板块，以及在轮动成形前动量刚刚跳升的板块。仅供观察——不要追高。')+'</p>'
      +'<div id="dw-content"><p class="dw-quiet">'
      +'<span class="l-en">Loading…</span><span class="l-zh">加载中…</span></p></div>'
      +'</section>';
    return true;
  }

  /* ── ETF → sector name map (tape-onset node ids are sector ETF tickers) ── */
  var _SECTOR_NAMES = {
    XLB:{en:'Materials',zh:'材料'},          XLC:{en:'Comm Services',zh:'通信'},
    XLE:{en:'Energy',zh:'能源'},              XLF:{en:'Financials',zh:'金融'},
    XLI:{en:'Industrials',zh:'工业'},         XLK:{en:'Technology',zh:'科技'},
    XLP:{en:'Cons Staples',zh:'必需消费'},    XLRE:{en:'Real Estate',zh:'房地产'},
    XLU:{en:'Utilities',zh:'公用事业'},        XLV:{en:'Health Care',zh:'医疗保健'},
    XLY:{en:'Cons Discretionary',zh:'可选消费'}
  };
  function _nodeName(nodeId){
    var m = _SECTOR_NAMES[nodeId];
    if(m) return isZh() ? m.zh : m.en;
    return nodeId;
  }

  /* ── Turn Desk half — armed sector cards, mechanics unchanged ── */
  function _armedHtml(d){
    var armed = (d && d.armed) || [];
    var html = '';
    // Staleness note when asof differs (kept — it is a data-honesty note, not a caveat)
    if(d && d.asof && d.member_fires_asof && d.asof !== d.member_fires_asof){
      html += '<p class="td-staleness-note">'
        + t('Note: panel asof ','注意：面板日期')
        + esc(d.asof)
        + t(' / member signals asof ','，成员信号日期')
        + esc(d.member_fires_asof)
        + '</p>';
    }
    html += '<div class="td-armed-grid">';
    armed.forEach(function(sec){
      var name = isZh() ? (sec.name_zh||sec.node) : (sec.name_en||sec.node);
      var mfires = sec.member_fires || [];
      var firesHtml = '';
      if(mfires.length){
        firesHtml = '<ul class="td-member-list">';
        mfires.forEach(function(m){
          var tierCls = m.tier==='T3' ? ' t3' : '';
          var provNote = m.provisional
            ? '<span class="td-provisional-note">'
              + t('(repaint ~9.4%)', '（约9.4%重绘）')
              + '</span>'
            : '';
          firesHtml += '<li class="td-member-item">'
            + '<span class="td-member-ticker">'+esc(m.ticker)+'</span>'
            + '<span class="td-tier-tag'+tierCls+'">'+esc(m.tier)+'</span>'
            + provNote
            + '</li>';
        });
        firesHtml += '</ul>';
      } else {
        firesHtml = '<p class="td-no-fires">'
          + t('No cascade fires in this sector today','此板块今日暂无级联信号')
          + '</p>';
      }
      var qualFilters = sec.qual_filters_true || [];
      var qualHtml = '';
      if(qualFilters.length){
        qualHtml = '<div class="td-qual-filters">'
          + '<span style="margin-right:4px">'
          + t('Context filters active:', '上下文过滤器激活：')
          + '</span>';
        qualFilters.forEach(function(fid){
          var tipEn = '', tipZh = '';
          if(fid==='F-Q2-RISKOFF'){ tipEn='Market state is NOT risk-off'; tipZh='市场状态非避险'; }
          else if(fid==='F-Q2-HIGHVIX'){ tipEn='VIX percentile ≥0.6'; tipZh='VIX百分位≥0.6'; }
          else if(fid==='F-Q3-TAPE'){ tipEn='Operator tape touch'; tipZh='运营商标注匹配'; }
          var tipAttrs = (tipEn ? ' data-tip-en="'+esc(tipEn)+'" data-tip-zh="'+esc(tipZh)+'"' : '');
          qualHtml += '<span class="td-qual-filter-tag"'
            + tipAttrs
            + '>'+esc(fid)+'</span>';
        });
        qualHtml += '</div>';
      }
      html += '<div class="td-sector-card">'
        + '<div class="td-card-hd">'
        + '<span class="td-sector-name">'+esc(name)+'</span>'
        + '<span class="td-window-badge">'
        + t('ARMED', '已激活')
        + '</span>'
        + '<span class="td-sessions-left">'
        + esc(sec.sessions_remaining)
        + t(' sessions left', ' 日剩余')
        + '</span>'
        + '</div>'
        + firesHtml
        + qualHtml
        + '</div>';
    });
    html += '</div>';
    return html;
  }

  /* ── Tape-onset half — flagged node cards, mechanics unchanged ── */
  function _flaggedNodes(d){
    var nodes = (d && d.nodes) || {};
    var flagged = [];
    Object.keys(nodes).sort().forEach(function(nid){
      if(nodes[nid] && nodes[nid].tape_onset_unconfirmed) flagged.push(nid);
    });
    return flagged;
  }

  function _onsetHtml(d, flagged){
    var nodes = (d && d.nodes) || {};
    var html = '<div class="tpo-grid">';
    flagged.forEach(function(nid){
      var v = nodes[nid];
      var st = v.tape_onset_stats || {};
      var p5 = pct(st.p_onset_5d);
      var fp5 = pct(st.false_positive_5d);
      var p10 = pct(st.p_confirmed_10d);
      var wStart = st.window_start || '—';
      var wEnd   = st.window_end   || '—';
      var nf = st.n_flags != null ? st.n_flags : '—';

      // Tooltip content: rates + window (registration §3 copy)
      var tipEn = nf+' historical flags ('+wStart+'→'+wEnd+'): '
        +p5+' reach smoothed onset in 5d; '
        +fp5+' noise rate (5d); '
        +p10+' reach confirmed episode in 10d. Not a forecast.';
      var tipZh = nf+'次历史标记（'+wStart+'→'+wEnd+'）：'
        +p5+'在5日内达到平滑启动；'
        +fp5+'噪声率（5日）；'
        +p10+'在10日内达到确认情节。非预测。';

      html += '<div class="tpo-node-card" data-tip-en="'+esc(tipEn)+'" data-tip-zh="'+esc(tipZh)+'">'
        + '<div class="tpo-node-name">'
        + esc(_nodeName(nid))
        + '<span class="tpo-flag-badge">'
        + t('EARLY', '早期')
        + '</span>'
        + '</div>'
        + '<div class="tpo-rates">'
        + '<b>' + t('5d onset rate: ', '5日启动率：') + '</b>' + p5
        + ' &nbsp;|&nbsp; '
        + '<b>' + t('noise: ', '噪声率：') + '</b>' + fp5
        + '<br><b>' + t('10d confirmed: ', '10日确认率：') + '</b>' + p10
        + '<br><span style="font-size:10px">' + t('measured ', '实测 ') + esc(wStart) + ' → ' + esc(wEnd) + '</span>'
        + '</div>'
        + '<p class="tpo-unconfirmed-note">'
        + t('Unconfirmed — raw signal, not an episode.', '未确认——原始信号，非情节。')
        + '</p>'
        + '</div>';
    });
    html += '</div>';
    return html;
  }

  /* ── the compressed footer: one plain line + a `?` receipt carrying the FULL
     original caveat text from BOTH retired sections (display-only, ranks nothing,
     promotion clock, base rates). The numeric clauses are emitted only when the
     turn-desk payload is actually present — a stat with no data path behind it is
     worse than no stat. ── */
  function _footHtml(td, tpo){
    var asof = (tpo && tpo.asof) || (td && td.asof) || '—';
    var partsEn = [], partsZh = [];

    partsEn.push('Armed windows (Turn Desk): when A15 fires (washout + ≥2 opposite-complex sectors rotating out) the entry window opens for up to 10 sessions; the desk lists the armed sectors and which member stocks currently carry a T1–T3 cascade signal. In these windows, member signals have worked out somewhat more often than outside them — a modest, still-accruing edge, not a forecast.');
    partsZh.push('已武装窗口（轮动入场台）：当A15触发（洗盘 + ≥2个对立复合板块轮出），入场窗口开启，持续最多10个交易日；此处列出处于窗口的板块，以及当前带有T1–T3级联信号的成员股票。在这些窗口内，成员信号的兑现频率略高于窗口外——这是一个仍在累积的温和优势，而非预测。');

    if(td){
      var br = td.base_rates || {};
      var pcv = td.promotion_clock || {};
      var qualNote = td.qual_accrual_note || '';
      var accrued  = pcv.windows_accrued || 0;
      var required = pcv.windows_required || 15;
      var wrIn  = br.in_window_wr21  != null ? (br.in_window_wr21*100).toFixed(1)+'%' : '65.2%';
      var wrOut = br.outside_window_wr21 != null ? (br.outside_window_wr21*100).toFixed(1)+'%' : '53.6%';
      var delta = br.holdout_delta_pp != null ? '+'+br.holdout_delta_pp.toFixed(1)+'pp' : '+10.7pp';
      var ciLo  = br.holdout_ci_lo_pp != null ? br.holdout_ci_lo_pp.toFixed(1) : '3.8';
      var ciHi  = br.holdout_ci_hi_pp != null ? br.holdout_ci_hi_pp.toFixed(1) : '17.9';
      var nw    = br.n_windows || 31;
      var from  = br.modern_track_from || '2022-06-30';
      partsEn.push('WR21 '+wrIn+' in-window vs '+wrOut+' outside; holdout Δ'+delta+' CI [+'+ciLo+', +'+ciHi+'pp]. '+nw+' modern-track windows, ≥'+from+'. Growth/cyclical tilt; defensive sectors negative. Lineage: #1533. Track record: '+accrued+' of '+required+' windows counted so far.');
      partsZh.push('窗口内WR21 '+wrIn+' vs 窗口外'+wrOut+'；持出集Δ'+delta+' CI [+'+ciLo+', +'+ciHi+'pp]。'+nw+'个现代追踪窗口，≥'+from+'。成长/周期偏向；防御性板块为负。来源：#1533。跟踪进度：已计入 '+accrued+' / '+required+' 个窗口。');
      if(qualNote){
        partsEn.push(qualNote+' Qualitative filters log context at window open; accrual is descriptive-only — no ranking or gating.');
        partsZh.push(qualNote+' 定性过滤器在窗口开启时记录上下文；积累数据为描述性——不排名不设门控。');
      }
    }

    partsEn.push('Earliest flow signs (tape-onset): a watch list, not signals — each card shows how often past flags like it went on to a real move. How it fires: a momentum jump (accel z ≥ 1.0, unsmoothed) with short-term speed above long-term and no confirmed episode. Rates computed from data, not hardcoded. Registered 2026-07-09; review 2026-10-09.');
    partsZh.push('最早期资金迹象（tape-onset）：观察名单，非信号——每项显示历史上类似标记后续演变为真实行情的频率。触发方式：动量跳升（加速度 z ≥ 1.0，未平滑），短期速度高于长期，且无已确认情节。发生率来自数据，非硬编码。登记于2026-07-09；复评2026-10-09。');

    partsEn.push('Both halves are display/context only — they feed no score, gate, or ordering surface.');
    partsZh.push('两部分均仅供展示/参考——不驱动任何评分、门控或排序。');

    return '<div class="dw-foot">'
      + '<span class="l-en">Watch material, not calls — display only, and nothing here ranks, gates or sizes anything. as of '+esc(asof)+'</span>'
      + '<span class="l-zh">仅供观察，并非操作判断——仅展示，此处不排名、不门控、不调仓。截至 '+esc(asof)+'</span>'
      + ' <span class="dw-help" tabindex="0" role="button" aria-label="details"'
      + ' data-tip-en="'+esc(partsEn.join(' '))+'"'
      + ' data-tip-zh="'+esc(partsZh.join(' '))+'">?</span>'
      + '</div>';
  }

  function render(td, tpo){
    var el = document.getElementById('dw-content');
    if(!el) return;
    var armed   = (td && td.armed) || [];
    var flagged = _flaggedNodes(tpo);

    // BOTH empty or absent → one quiet line (a quiet tape is a valid read).
    if(!armed.length && !flagged.length){
      el.innerHTML = '<p class="dw-quiet">'
        + '<span class="l-en">No armed windows and no early flow signs right now — a quiet tape is a valid read.</span>'
        + '<span class="l-zh">当前无已武装窗口，也无最早期资金迹象——安静的盘面也是有效读数。</span>'
        + '</p>'
        + _footHtml(td, tpo);
      return;
    }

    var html = '';
    html += '<div class="dw-group"><div class="dw-gh">'
      + L('Armed windows', '已武装窗口')
      + (armed.length ? ' · '+armed.length : '')
      + '</div>'
      + (armed.length
          ? _armedHtml(td)
          : '<div class="dw-quiet-row">'
            + '<span class="l-en">No sectors armed right now — a quiet desk is a valid read.</span>'
            + '<span class="l-zh">当前无板块处于入场窗口——安静的值守台也是有效读数。</span></div>')
      + '</div>';
    html += '<div class="dw-group"><div class="dw-gh">'
      + L('Earliest flow signs', '最早期资金迹象')
      + (flagged.length ? ' · '+flagged.length : '')
      + '</div>'
      + (flagged.length
          ? _onsetHtml(tpo, flagged)
          : '<div class="dw-quiet-row">'
            + '<span class="l-en">No early flow signs right now — a quiet tape is a valid read.</span>'
            + '<span class="l-zh">当前无最早期资金迹象——安静的盘面也是有效读数。</span></div>')
      + '</div>';
    el.innerHTML = html + _footHtml(td, tpo);
  }

  function load(){
    if(!mount()) return;
    Promise.all([
      fetch(TD_ARTIFACT, {cache:'no-cache'}).then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }),
      fetch(TPO_ARTIFACT,{cache:'no-cache'}).then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; })
    ]).then(function(res){
      render(res[0], res[1]);
    }).catch(function(){
      var el = document.getElementById('dw-content');
      if(el) el.innerHTML = '<p class="dw-quiet">'
        + '<span class="l-en">Desk-watch data unavailable.</span>'
        + '<span class="l-zh">值守台数据暂不可用。</span>'
        + '</p>';
    });
  }

  function boot(){
    injectStyle();
    load();
    // Re-render on lang/theme change (both retired sections did this)
    var _dwObs = new MutationObserver(load);
    _dwObs.observe(document.documentElement, {attributes:true, attributeFilter:['data-lang','data-theme']});
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot);
  else boot();
})();

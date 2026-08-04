/* rotation_events.js — the Rotation Events rail (Rotation Command W1 — RC-R1/R3/R6).
 *
 * Extracted verbatim from the retired subsector_rotation.html.j2 section #rc-events
 * (Sector Intelligence consolidation). Mounts into #rc-events-mount inside the merged
 * sector_central.html #si-movement section, so the section heading is an h3 (it now
 * lives INSIDE a section rather than being one).
 *
 * Reads marketdata/rotation_events.json + marketdata/sector_fragmentation.json.
 * Absent/failed fetch = graceful quiet note. DISPLAY-ONLY — ranks nothing, gates
 * nothing, sizes nothing.
 *
 * Three renderers, unchanged mechanics:
 *   • renderFlowLanes — the donor ➜ receiver flow-lane hero (#rc-flowmap-content)
 *   • renderClosures  — the "closed recently" strip so nothing vanishes silently
 *   • render          — the event cards + fragmented-sector chips (#rc-events-content)
 */
(function () {
  'use strict';

  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function isZh(){return document.documentElement.getAttribute('data-lang')==='zh';}
  function t(en,zh){return isZh()&&zh?zh:en;}
  function L(en,zh){return '<span class="l-en">'+en+'</span><span class="l-zh">'+(zh==null?en:zh)+'</span>';}
  function pc(v,dp){return v==null?'—':((v>0?'+':'')+(v*100).toFixed(dp==null?1:dp)+'%');}

  /* ── styles (injected once, guarded by element id — subsector_rotation.js model).
     Carried over from the retired page's own <style> block; `#rc-events h2` becomes
     `#rc-events h3` because the heading demoted when the section moved inside
     #si-movement. ── */
  function injectStyle(){
    if(document.getElementById('rc-events-style')) return;
    var c=''
      +'#rc-events { margin:0 2px 22px; }'
      +'#rc-events h3 { font-size:17px; font-weight:800; letter-spacing:-.015em; margin:0 0 4px; }'
      +'.rc-sub { color:var(--muted); font-size:12px; margin:0 0 10px; max-width:84ch; line-height:1.5; }'
      +'.rc-grid { display:flex; flex-wrap:wrap; gap:10px; }'
      +'.rc-card { flex:1 1 300px; min-width:260px; border-radius:12px; border:1px solid var(--line);'
      +'  background:var(--panel); padding:12px 14px; }'
      +'.rc-card.rc-major { border-left:4px solid var(--warn); }'
      +'.rc-hd { display:flex; align-items:baseline; gap:7px; margin-bottom:5px; flex-wrap:wrap; }'
      +'.rc-title { font-weight:800; font-size:13.5px; }'
      +'.rc-sev { font-size:9.5px; font-weight:700; text-transform:uppercase; padding:2px 7px; border-radius:6px;'
      +'  background:color-mix(in srgb,var(--muted) 15%,transparent); color:var(--muted); letter-spacing:.04em; }'
      +'.rc-sev.major { background:color-mix(in srgb,var(--warn) 20%,transparent); color:var(--warn); }'
      +'.rc-sev.notable { background:color-mix(in srgb,var(--link) 16%,transparent); color:var(--link); }'
      +'.rc-day { font-size:11px; color:var(--muted); margin-left:auto; font-variant-numeric:tabular-nums; }'
      +'.rc-copy { font-size:12.5px; line-height:1.55; }'
      +'.rc-receipts { margin-top:6px; font-size:10.5px; color:var(--muted); font-variant-numeric:tabular-nums; }'
      +'.rc-stale { font-style:italic; }'
      +'.rc-quiet { color:var(--muted); font-size:12.5px; padding:8px 0; }'
      +'.rc-frag { margin-top:12px; }'
      +'.rc-frag-hd { font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:.07em;'
      +'  color:var(--muted); margin:0 0 7px; }'
      +'.rc-frag-chips { display:flex; flex-wrap:wrap; gap:6px; }'
      +'.rc-frag-chip { font-size:11px; padding:4px 10px; border-radius:8px; border:1px solid var(--line);'
      +'  background:color-mix(in srgb,var(--warn) 9%,var(--panel2)); line-height:1.45; }'
      +'.rc-frag-chip b { font-weight:800; }'
      +'.rc-caveat { margin-top:10px; font-size:10.5px; color:var(--muted); line-height:1.55; }'
      /* ── Flow-lanes hero (.rcf-*) ── */
      +'#rc-flowmap-content { margin-bottom:14px; }'
      +'.rcf-empty { color:var(--muted); font-size:12.5px; padding:8px 0; }'
      +'.rcf-lane { display:flex; flex-wrap:wrap; align-items:center; gap:8px 12px;'
      +'  padding:10px 13px; border-radius:11px; border:1px solid var(--line);'
      +'  background:var(--panel2); margin-bottom:8px; position:relative; }'
      +'.rcf-lane.rcf-handoff    { border-left:4px solid var(--link); }'
      +'.rcf-lane.rcf-into_strength { border-left:4px solid var(--up); }'
      +'.rcf-lane.rcf-contagion_break { border-left:4px solid var(--warn); }'
      +'.rcf-lane.rcf-faltering  { border-left:4px solid var(--muted); }'
      +'.rcf-pill { font-size:11.5px; font-weight:700; padding:3px 10px; border-radius:8px;'
      +'  background:color-mix(in srgb,var(--text) 8%,var(--panel)); border:1px solid var(--line);'
      +'  white-space:nowrap; }'
      +'.rcf-arrow { font-size:13px; color:var(--muted); flex:none; }'
      +'.rcf-state { font-size:12.5px; font-weight:600; flex:1 1 160px; min-width:120px; }'
      +'.rcf-stance { font-size:10.5px; font-weight:700; padding:2px 8px; border-radius:6px;'
      +'  white-space:nowrap; }'
      +'.rcf-stance.rcf-watch { background:color-mix(in srgb,var(--link) 14%,transparent); color:var(--link); }'
      +'.rcf-stance.rcf-favour { background:color-mix(in srgb,var(--up) 14%,transparent); color:var(--up); }'
      +'.rcf-stance.rcf-aside  { background:color-mix(in srgb,var(--warn) 14%,transparent); color:var(--warn); }'
      +'.rcf-stance.rcf-weak   { background:color-mix(in srgb,var(--muted) 14%,transparent); color:var(--muted); }'
      +'.rcf-decay { width:100%; height:5px; border-radius:3px;'
      +'  background:var(--panel2); border:1px solid var(--line); overflow:hidden; margin-top:4px; }'
      +'.rcf-decay-bar { height:100%; border-radius:3px; background:var(--warn); transition:width .3s; }'
      +'.rcf-decay-cap { font-size:10px; color:var(--warn); margin-top:3px; }'
      +'.rcf-help { display:inline-block; font-size:9.5px; font-weight:700; color:var(--muted);'
      +'  border:1px solid var(--line); border-radius:50%; width:16px; height:16px; line-height:14px;'
      +'  text-align:center; cursor:help; flex:none; }'
      +'.rcf-footer { font-size:10.5px; color:var(--muted); margin-top:4px; line-height:1.5; }'
      +'.rcf-coldstart-note { font-size:10px; color:var(--muted); margin-left:6px; }'
      /* ── Closures strip (.rcx-*) ── */
      +'#rc-closures { margin-bottom:10px; }'
      +'.rcx-strip { font-size:11.5px; color:var(--muted); border:1px solid var(--line);'
      +'  border-radius:9px; padding:7px 12px; background:var(--panel2); }'
      +'.rcx-toggle { cursor:pointer; font-weight:700; user-select:none; }'
      +'.rcx-toggle:hover { color:var(--text); }'
      +'.rcx-list { margin-top:7px; display:flex; flex-direction:column; gap:4px; }'
      +'.rcx-row { font-size:11px; color:var(--muted); }'
      +'.rcx-foot { margin-top:5px; font-size:10px; color:var(--muted); font-style:italic; }'
      +'@media (max-width:520px) {'
      +'  .rcf-lane { gap:6px 8px; }'
      +'  .rcf-state { flex-basis:100%; }'
      +'  .rcf-decay { margin-top:3px; }'
      +'}';
    var s=document.createElement('style');
    s.id='rc-events-style';
    s.textContent=c;
    document.head.appendChild(s);
  }

  /* ── mount: build the section shell into #rc-events-mount (once). Static copy uses
     dual l-en/l-zh spans so a language switch needs no rebuild. ── */
  function mount(){
    var host=document.getElementById('rc-events-mount');
    if(!host) return false;
    if(document.getElementById('rc-events')) return true;
    host.innerHTML=''
      +'<section id="rc-events" aria-label="Rotation events">'
      +'<h3>⟲ '+L('Rotation Events','轮动事件')+'</h3>'
      +'<p class="rc-sub">'+L(
          'Where money is moving between sectors — leaving one, turning up in another. A heads-up on shifting leadership, not a buy list.',
          '资金在板块之间的流向——从一处撤出、在另一处转强。这是领导权变化的提示，并非买入清单。')+'</p>'
      +'<div id="rc-flowmap-content"></div>'
      +'<div id="rc-closures"></div>'
      +'<div id="rc-events-content"><p class="rc-quiet">'
      +'<span class="l-en">Loading…</span><span class="l-zh">加载中…</span></p></div>'
      +'</section>';
    return true;
  }

  /* ── Part 5A: renderFlowLanes — builds the #rc-flowmap-content hero ── */
  function renderFlowLanes(ev){
    var el=document.getElementById('rc-flowmap-content');
    if(!el) return;
    // graceful degrade: no velocity_board → entire section hidden already (we just render lanes)
    var active=(ev&&ev.active)||[];
    if(!active.length){
      el.innerHTML='<p class="rcf-empty">'
        +t('No money-flow events right now — a quiet tape is a valid read. Nothing to do.',
           '当前无资金流向事件——安静的盘面也是有效读数。无需操作。')
        +'</p>';
      return;
    }
    var html='';
    var sevRank={major:0,notable:1,standard:2};
    var sorted=active.slice().sort(function(a,b){
      var d=(sevRank[a.severity]!=null?sevRank[a.severity]:9)-(sevRank[b.severity]!=null?sevRank[b.severity]:9);
      return d!==0?d:String(b.started||'').localeCompare(String(a.started||''));
    });
    sorted.forEach(function(e){
      // Determine event_type — default to handoff for v1 payload without event_type (graceful degrade)
      var etype=e.event_type||'handoff';
      /* Donor/receiver labels. Both languages are resolved, not just the active one:
         the hover card writes an EN and a ZH attribute at the same time, and a card
         built from only the active language leaves the other half in English until
         the next re-render. */
      var donorEn,donorZh,recvEn,recvZh;
      if(etype==='correlation_break'||etype==='contagion_break'){
        // contagion — use a+b from contagion field or from the event itself
        donorEn=esc(e.from_leg&&(e.from_leg.name_en||e.from_leg.key)||'—');
        donorZh=esc(e.from_leg&&(e.from_leg.name_zh||e.from_leg.name_en||e.from_leg.key)||'—');
        recvEn=esc(e.to_leg&&(e.to_leg.name_en||e.to_leg.key)||'—');
        recvZh=esc(e.to_leg&&(e.to_leg.name_zh||e.to_leg.name_en||e.to_leg.key)||'—');
      } else {
        donorEn=esc(e.from_leg&&(e.from_leg.name_en||e.from_leg.key)||e.donor||'—');
        donorZh=esc(e.from_leg&&(e.from_leg.name_zh||e.from_leg.name_en)||e.donor||'—');
        recvEn=esc(e.to_leg&&(e.to_leg.name_en||e.to_leg.key)||e.receiver||'—');
        recvZh=esc(e.to_leg&&(e.to_leg.name_zh||e.to_leg.name_en)||e.receiver||'—');
      }
      // Mag-7 basket pill: never show "MAGS"
      if((e.to_leg&&(e.to_leg.key==='mag7'||e.to_leg.key==='mag7_basket'))||e.receiver==='mag7_basket'){
        recvEn='Mag-7 basket'; recvZh='七巨头等权篮子';
      }
      var donorName=isZh()?donorZh:donorEn, receiverName=isZh()?recvZh:recvEn;
      // Health / faltering
      var h=e.health||null;
      var isFaltering=!!(h&&(h.weakening||h.lapse_count>=2||h.neg_run>=2));
      var effectiveType=isFaltering?'faltering':etype;

      // State line and stance per type. The state line doubles as the hover card's
      // headline, so it is kept in both languages.
      var stateLineEn,stateLineZh,stanceText,stanceCls;
      if(effectiveType==='into_strength'){
        stateLineEn='Strength rotating toward '+recvEn;
        stateLineZh='强势正在轮向'+recvZh;
        stanceText=t('In favour — watch for entry','处于优势——留意入场');
        stanceCls='rcf-favour';
      } else if(effectiveType==='contagion_break'||effectiveType==='correlation_break'){
        stateLineEn=donorEn+' and '+recvEn+' no longer offsetting — falling together';
        stateLineZh=donorZh+'与'+recvZh+'不再互相对冲——同步下跌';
        stanceText=t('Stand aside — diversification fading','暂避——分散效果减弱');
        stanceCls='rcf-aside';
      } else if(effectiveType==='faltering'){
        stateLineEn=donorEn+'→'+recvEn+' rotation weakening';
        stateLineZh=donorZh+'→'+recvZh+'轮动转弱';
        stanceText=t('Rotation weakening — may close','轮动转弱——或将关闭');
        stanceCls='rcf-weak';
      } else {
        // handoff (default for unknown types — cautious fallback per spec)
        stateLineEn='Money leaving '+donorEn+', turning up in '+recvEn;
        stateLineZh='资金撤出'+donorZh+'，在'+recvZh+'转强';
        stanceText=t('Watch — don\'t chase','观望，不要追高');
        stanceCls='rcf-watch';
      }
      var stateLine=isZh()?stateLineZh:stateLineEn;

      /* Hover card (Tier-2). Rewritten 2026-08-04 with the popup overhaul: the old
         tip was one run-on chain of eight machine fragments — "Out: X −30% from
         peak · In: Y +12.6% off low · Ratio: +6.3%/10s · Historical: about half
         reach +7.8% in ~9 sessions (n=8) · Heads-up…" — with the English suffixes
         hardcoded, so the Chinese card read half in English. It is now a headline,
         two plain sentences, and a receipt line for the base rate. Both languages
         are built separately rather than sharing one pre-resolved string. */
      var r=e.receipts||{};
      var bodyEn=[],bodyZh=[];
      if(r.blowoff&&r.blowoff.drawdown_pct!=null){
        var dd=(r.blowoff.drawdown_pct*100).toFixed(0);
        bodyEn.push(donorEn+' sits '+dd+'% below its peak.');
        bodyZh.push(donorZh+'较峰值低 '+dd+'%。');
      }
      if(r.turn&&r.turn.off_low_pct!=null){
        var ol=(r.turn.off_low_pct*100).toFixed(1);
        bodyEn.push(recvEn+' is '+ol+'% up off its low.');
        bodyZh.push(recvZh+'自低点回升 '+ol+'%。');
      }
      if(r.ratio&&r.ratio.ratio_chg_10s!=null){
        var rc=Math.abs(r.ratio.ratio_chg_10s*100).toFixed(1);
        bodyEn.push('The two have moved '+rc+'% apart over the last ten sessions'
          +(r.ratio.ratio_20s_high?', the widest gap in a month.':'.'));
        bodyZh.push('近十个交易日两者差距扩大 '+rc+'%'+(r.ratio.ratio_20s_high?'，为一个月来最大。':'。'));
      }
      bodyEn.push('A heads-up on shifting leadership, not a buy signal.');
      bodyZh.push('这是领导权变化的提示，并非买入信号。');
      /* The receipt strip — base rates, sample sizes and money flow. Sanctioned
         Tier-2 home for the machine facts the body must not carry. */
      var rcEn=[],rcZh=[];
      var ru=(ev&&ev.ruler&&ev.ruler.modern&&ev.ruler.modern.run_pct)?ev.ruler.modern:null;
      if(ru&&ru.n>=5){
        rcEn.push('past handoffs: half ran +'+ru.run_pct.median+'% within ~'+ru.sessions_to_peak.median+' sessions (n='+ru.n+')');
        rcZh.push('历史同类轮动：半数在约'+ru.sessions_to_peak.median+'个交易日内录得 +'+ru.run_pct.median+'%（n='+ru.n+'）');
      }
      var fr=e.flow_receipts||null;
      if(fr&&fr.receiver&&fr.receiver.flow_5d_mn!=null){
        var fm='$'+(fr.receiver.flow_5d_mn/1e6).toFixed(0)+'M';
        rcEn.push('ETF flow 5d '+fm+(fr.receiver.flow_asof?' · as of '+esc(fr.receiver.flow_asof):''));
        rcZh.push('ETF 5日资金 '+fm+(fr.receiver.flow_asof?' · 截至 '+esc(fr.receiver.flow_asof):''));
      }

      var laneClass='rcf-lane rcf-'+esc(etype.replace('correlation_break','contagion_break'));
      html+='<div class="'+laneClass+'"'
        +' data-tip-t-en="'+esc(stateLineEn)+'" data-tip-t-zh="'+esc(stateLineZh)+'"'
        +' data-tip-en="'+esc(bodyEn.join(' '))+'" data-tip-zh="'+esc(bodyZh.join(''))+'"'
        +(rcEn.length?' data-tip-rc-en="'+esc(rcEn.join(' · '))+'" data-tip-rc-zh="'+esc(rcZh.join(' · '))+'"':'')
        +'>'
        +'<span class="rcf-pill">'+donorName+'</span>'
        +'<span class="rcf-arrow">&#x279C;</span>'
        +'<span class="rcf-pill">'+receiverName+'</span>'
        +'<span class="rcf-state">'+stateLine+'</span>'
        +'<span class="rcf-stance '+stanceCls+'">'+stanceText+'</span>';
      // Decay meter for faltering events
      if(effectiveType==='faltering'&&h){
        var stc=h.sessions_to_close!=null?h.sessions_to_close:(h.sessions_to_close_bound||null);
        var lapse=h.lapse_count||0;
        var bound=(stc!=null?stc:5);
        var barPct=Math.max(0,Math.min(100,100*(1-lapse/Math.max(bound,1))));
        html+='<div style="width:100%">'
          +'<div class="rcf-decay"><div class="rcf-decay-bar" style="width:'+barPct.toFixed(0)+'%"></div></div>'
          +(stc!=null?'<div class="rcf-decay-cap">'+t('may close in '+stc+' sessions','或于'+stc+'个交易日内关闭')+'</div>':'')
          +'</div>';
      }
      html+='</div>';
    });
    // Footer
    var asof=(ev&&ev.as_of)||'—';
    var coldstarNote=(ev&&ev.coldstart)?
      '<span class="rcf-coldstart-note"><span class="rcf-help"'
      +' data-tip-t-en="Counts look reset" data-tip-t-zh="计数看似重置"'
      +' data-tip-en="History was rebuilt last night, so the day counts start over. The events themselves are unchanged."'
      +' data-tip-zh="昨夜重建了历史，因此天数从头计起。事件本身没有变化。">?</span></span>'
      :'';
    html+='<div class="rcf-footer">'
      +'<span class="l-en">A heads-up on shifting leadership — not a buy list. as of '+esc(asof)+'</span>'
      +'<span class="l-zh">领导权变化的提示——非买入清单。截至 '+esc(asof)+'</span>'
      +' <span class="rcf-help" tabindex="0" role="button" aria-label="details"'
      +' data-tip-t-en="How these are tracked" data-tip-t-zh="这些事件如何被跟踪"'
      +' data-tip-en="Every event is logged and its outcome followed. Most are still being measured, so nothing here ranks, gates or sizes anything."'
      +' data-tip-zh="每个事件都会记录并跟踪结果。多数仍在观察中，因此此处不排名、不门控、不调仓。"'
      +' data-tip-rc-en="each series measured on its own history · Mag-7 = equal-weight basket, not the MAGS ETF · logging began 2026-06-25"'
      +' data-tip-rc-zh="各序列以自身历史衡量 · 七巨头为等权篮子，非 MAGS ETF · 自 2026-06-25 起记录">?</span>'
      +coldstarNote
      +'</div>';
    el.innerHTML=html;
  }

  /* ── Part 5A: renderClosures — builds the #rc-closures strip ── */
  function renderClosures(ev){
    var el=document.getElementById('rc-closures');
    if(!el) return;
    // graceful degrade: no closures data → hide entirely
    var closures=(ev&&(ev.closures||ev.closed_recent||ev.closed_tonight))||[];
    if(!closures.length){ el.innerHTML=''; return; }
    var REASON={
      ratio_slope_flipped:{en:'the move reversed',zh:'走势反转'},
      conditions_lapsed  :{en:'signals faded',    zh:'信号消退'},
      ttl                :{en:'ran its course',    zh:'自然结束'}
    };
    var N=closures.length;
    var listHtml='';
    closures.forEach(function(c){
      var donor=esc(c.from_leg||c.from_sector||c.donor||'—');
      var recv=esc(c.to_leg||c.to_sector||c.receiver||'—');
      var rkey=c.reason||c.close_reason||'';
      var rmap=REASON[rkey]||{en:esc(rkey),zh:esc(rkey)};
      var reasonPlain=isZh()?rmap.zh:rmap.en;
      var dayN=c.day_n!=null?c.day_n:'—';
      listHtml+='<div class="rcx-row">'
        +donor+' → '+recv+' · '
        +t('ended: ','结束：')+reasonPlain+' · '
        +t('lasted ','持续 ')+dayN+t(' sessions','个交易日')
        +'</div>';
    });
    var expanded=false;
    var id='rcx-list-'+Math.random().toString(36).slice(2,7);
    el.innerHTML='<div class="rcx-strip">'
      +'<span class="rcx-toggle" id="rcx-tog-'+id+'">'
      +'<span class="l-en">Closed recently: '+N+' ▾</span>'
      +'<span class="l-zh">近期关闭：'+N+' ▾</span>'
      +'</span>'
      +'<div class="rcx-list" id="'+id+'" style="display:none">'+listHtml
      +'<div class="rcx-foot">'
      +t('Shown so nothing disappears silently.','列出以避免事件悄然消失。')
      +'</div></div></div>';
    var tog=el.querySelector('#rcx-tog-'+id);
    var lst=el.querySelector('#'+id);
    if(tog&&lst){
      tog.addEventListener('click',function(){
        expanded=!expanded;
        lst.style.display=expanded?'':'none';
      });
    }
  }

  function render(ev, frag){
    var el=document.getElementById('rc-events-content');
    if(!el) return;
    var html='';
    var active=(ev&&ev.active)||[];
    if(!active.length){
      html+='<p class="rc-quiet">'+t('No active rotation events — quiet state is a valid state.',
        '当前无活跃轮动事件——安静状态是有效状态。')+'</p>';
    }else{
      var sevRank={major:0,notable:1,standard:2};
      active=active.slice().sort(function(a,b){
        var d=(sevRank[a.severity]!=null?sevRank[a.severity]:9)-(sevRank[b.severity]!=null?sevRank[b.severity]:9);
        return d!==0?d:String(b.started||'').localeCompare(String(a.started||''));
      });
      html+='<div class="lst-wrap"><div class="rc-grid lst-collapse lst-cap4 is-collapsed">';
      active.forEach(function(e){
        var sev=e.severity||'standard';
        var title=isZh()
          ? esc(e.from_leg.name_zh)+' → '+esc(e.to_leg.name_zh)+'（'+esc(e.sector_name_zh)+'）'
          : esc(e.from_leg.name_en)+' → '+esc(e.to_leg.name_en)+' ('+esc(e.sector_name_en)+')';
        var r=e.receipts||{};
        var rec='';
        if(r.blowoff&&r.turn&&r.ratio){
          rec=t('blowoff ','冲顶回落 ')+'−'+(r.blowoff.drawdown_pct*100).toFixed(0)+'%'
            +' · '+t('off low ','低点回升 ')+pc(r.turn.off_low_pct)
            +' · '+t('ratio ','比值 ')+pc(r.ratio.ratio_chg_10s)+'/10s';
          // D-9: health state replaces the old (as of last confirmation) italic
          var h=e.health||null;
          if(h&&(h.weakening||h.lapse_count>=2||h.neg_run>=2)){
            var stc=h.sessions_to_close!=null?h.sessions_to_close:(h.sessions_to_close_bound||null);
            rec+=' <span style="color:var(--warn);font-weight:600;">'
              +t('Weakening — may close'+(stc!=null?' in '+stc+' sessions':''),
                 '转弱——'+(stc!=null?'或于'+stc+'个交易日内关闭':'或将关闭'))+'</span>';
          } else if(h&&h.lapse_count>0&&!e.confirmed_tonight){
            rec+=' <span style="color:var(--muted);font-style:italic;">'
              +t('Cooling — last confirmed '+esc(e.asof||''),'降温——最近确认 '+esc(e.asof||''))+'</span>';
          }
          // RC-R10 honest late-ruler: the measured census distribution instead of a
          // binary "late" instinct. Descriptive only, never a gate.
          var ru=(ev&&ev.ruler&&ev.ruler.modern&&ev.ruler.modern.run_pct)?ev.ruler.modern:null;
          if(ru&&ru.n>=5){
            rec+='<br>'+t('vs modern-era handoffs: median run ','对照现代样本：中位行情 ')
              +'+'+ru.run_pct.median+'% ('+t('p75 ','75分位 ')+'+'+ru.run_pct.p75+'%), '
              +t('peaking ~','约 ')+ru.sessions_to_peak.median
              +t(' sessions in (n='+ru.n+', descriptive only)',' 个交易日见顶（n='+ru.n+'，仅描述性）');
          }
        }
        html+='<div class="rc-card rc-'+esc(sev)+'">'
          +'<div class="rc-hd"><span class="rc-sev '+esc(sev)+'">'+esc(sev)+'</span>'
          +'<span class="rc-title">'+title+'</span>'
          +'<span class="rc-day">'+t('day ','第')+esc(e.day_n)+t('',' 天')+' · '+esc(e.started)+'</span></div>'
          +'<div class="rc-copy">'+esc(isZh()?e.copy_zh:e.copy_en)+'</div>'
          +(rec?'<div class="rc-receipts">'+rec+'</div>':'')
          +'</div>';
      });
      html+='</div>';
      if(active.length>4){
        html+='<button class="lst-more" type="button" aria-expanded="false"><span class="lm-show">'
          +t('Show more','显示更多')+' ▾</span><span class="lm-hide">'+t('Show less','收起')+' ▴</span></button>';
      }
      html+='</div>';
    }
    var rows=(frag&&frag.sectors)||[];
    var flagged=rows.filter(function(r){return r.fragmented;});
    if(flagged.length){
      html+='<div class="rc-frag"><div class="rc-frag-hd">'
        +t('Fragmented sectors — aggregate reads not representative',
           '内部分化板块——聚合读数或失真')+'</div><div class="rc-frag-chips">';
      flagged.forEach(function(r){
        html+='<span class="rc-frag-chip"><b>'+esc(isZh()?r.name_zh:r.name_en)+' ('+esc(r.etf)+')</b> — '
          +esc(isZh()?r.copy_zh:r.copy_en)+'</span>';
      });
      // D-8: stance for fragmentation section
      html+='</div><div style="font-size:10.5px;color:var(--muted);margin-top:6px;">'
        +t('Judge the pieces, not the sector average.','看内部分支，别看板块平均。')
        +'</div></div>';
    }
    // Dead-end #9: cross-sector callout when an into_strength event is active
    if(ev){
      var xsActive=(ev.active||[]).filter(function(e){
        return (e.event_type==='into_strength'||e.event_type==='cross_handoff')&&(e.to_sector||e.to_leg);
      });
      if(xsActive.length){
        xsActive.forEach(function(e){
          var toSec=isZh()
            ?(e.to_sector_zh||e.sector_name_zh||(e.to_leg&&(e.to_leg.name_zh||e.to_leg.name_en))||'')
            :(e.to_sector_en||e.sector_name_en||(e.to_leg&&(e.to_leg.name_en||e.to_leg.key))||'');
          if(toSec){
            html+='<div style="font-size:11px;color:var(--link);margin-top:8px;">'
              +t('Money is rotating toward '+esc(toSec)+' — see it in the flow map above.',
                 '资金正在轮向'+esc(toSec)+'——见上方资金流向图。')
              +'</div>';
          }
        });
      }
    }
    html+='<div class="rc-caveat">'
      +t('A heads-up, not a buy signal — these events don\'t rank, gate, or size anything, and most are still being measured. as of ',
         '仅为提示，非买入信号——这些事件不排名、不设门控、不调仓位，且多数仍在观察中。截至 ')
      +esc((ev&&ev.as_of)||'—')+'</div>';
    el.innerHTML=html;
  }

  function load(){
    if(!mount()) return;
    Promise.all([
      fetch('marketdata/rotation_events.json',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}),
      fetch('marketdata/sector_fragmentation.json',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;})
    ]).then(function(res){
      if(!res[0]&&!res[1]){
        var el=document.getElementById('rc-events-content');
        if(el) el.innerHTML='<p class="rc-quiet"><span class="l-en">Rotation-event data unavailable.</span><span class="l-zh">轮动事件数据暂不可用。</span></p>';
        return;
      }
      renderFlowLanes(res[0]);
      renderClosures(res[0]);
      render(res[0],res[1]);
    }).catch(function(){/* fail-soft: leave the loading/quiet note in place */});
  }

  function boot(){
    injectStyle();
    load();
    var _rcObs=new MutationObserver(load);
    _rcObs.observe(document.documentElement,{attributes:true,attributeFilter:['data-lang','data-theme']});
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot);
  else boot();
})();

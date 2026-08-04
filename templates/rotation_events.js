/* rotation_events.js — the sector-handoff rail (Rotation Command W1 — RC-R1/R3/R6).
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
 *   • renderFlowLanes — the donor ➜ receiver flow lane, ONE row per event, with the
 *                       full receipt on hover (#rc-flowmap-content)
 *   • renderClosures  — the "closed recently" control (in the footer above) and the
 *                       panel it opens, so nothing vanishes silently (#rc-closures)
 *   • render          — the split-sector chips (#rc-events-content)
 *
 * 2026-08-04 cut (operator: "way too much text… needs a lot of cutting"): every
 * active event used to be drawn TWICE — once as a flow lane, once as a card whose
 * prose restated the lane and whose receipt lines repeated figures the lane's own
 * hover already carried — under three separate copies of "a heads-up, not a buy
 * signal" and two as-of stamps. The cards are gone; nothing they carried is. See
 * the note above render().
 */
(function () {
  'use strict';

  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function isZh(){return document.documentElement.getAttribute('data-lang')==='zh';}
  function t(en,zh){return isZh()&&zh?zh:en;}
  function L(en,zh){return '<span class="l-en">'+en+'</span><span class="l-zh">'+(zh==null?en:zh)+'</span>';}
  /* pc() went with the event-card receipts line — its only caller. */

  /* ── Leg display names ──────────────────────────────────────────────────────
     ACTIVE events carry full leg objects ({key, name_en, name_zh}); CLOSURE rows
     carry BARE KEYS ("memory", "ai_software", "mag7") and the strip printed them
     raw, in both languages — the raw-machine-slug leak house design law bans on a
     glance surface. The same payload already knows most of these names, so harvest
     them from the active legs, keep the Mag-7 special case the lane renderer uses,
     and fall back to a prettified slug: a name we have never seen degrades to
     "AI software", it never blocks the render. ── */
  var LEGNAMES={mag7:{en:'Mag-7 basket',zh:'七巨头等权篮子'},
                mag7_basket:{en:'Mag-7 basket',zh:'七巨头等权篮子'}};
  function harvestLegNames(ev){
    (((ev||{}).active)||[]).forEach(function(e){
      [e&&e.from_leg,e&&e.to_leg].forEach(function(l){
        if(l&&typeof l==='object'&&l.key&&(l.name_en||l.name_zh))
          LEGNAMES[l.key]={en:l.name_en||l.key,zh:l.name_zh||l.name_en||l.key};
      });
    });
  }
  function prettySlug(k){
    return String(k==null?'':k).replace(/_/g,' ')
      .replace(/\b(ai|hbm|etf|reit|us|uk|it|pc|ev|gpu|cpu|5g|3d)\b/gi,function(m){return m.toUpperCase();})
      .replace(/^([a-z])/,function(c){return c.toUpperCase();});
  }
  /* `zh` is explicit rather than read from isZh(): the closures panel emits BOTH
     languages as l-en/l-zh twins, so it needs each name in each language at once. */
  function legName(v,zh){
    if(zh==null) zh=isZh();
    if(v&&typeof v==='object')
      return zh?(v.name_zh||v.name_en||prettySlug(v.key)):(v.name_en||prettySlug(v.key));
    var m=LEGNAMES[v];
    if(m) return zh?m.zh:m.en;
    return prettySlug(v);
  }

  /* ── styles (injected once, guarded by element id — subsector_rotation.js model).
     Carried over from the retired page's own <style> block; `#rc-events h2` becomes
     `#rc-events h3` because the heading demoted when the section moved inside
     #si-movement. ── */
  function injectStyle(){
    if(document.getElementById('rc-events-style')) return;
    var c=''
      /* The .rc-grid / .rc-card / .rc-sev / .rc-day / .rc-copy / .rc-receipts / .rc-sub
         / .rc-caveat rules are gone with the markup they dressed — see render(). */
      +'#rc-events { margin:0 2px 22px; }'
      +'#rc-events h3 { font-size:15px; font-weight:800; letter-spacing:-.015em; margin:0 0 9px; }'
      +'.rc-quiet { color:var(--muted); font-size:12.5px; padding:8px 0; }'
      +'.rc-frag { margin-top:12px; }'
      /* sentence case, not tracked caps: this line is a STANCE ("judge the pieces"),
         and an all-caps banner of it wrapped to two shouting lines on mobile while
         reading like a category label for the chips underneath */
      +'.rc-frag-hd { font-size:11.5px; font-weight:700; color:var(--muted); margin:0 0 7px;'
      +'  line-height:1.45; }'
      +'.rc-frag-chips { display:flex; flex-wrap:wrap; gap:6px; }'
      +'.rc-frag-chip { font-size:11px; padding:4px 10px; border-radius:8px; border:1px solid var(--line);'
      +'  background:color-mix(in srgb,var(--warn) 9%,var(--panel2)); line-height:1.45; }'
      +'.rc-frag-chip b { font-weight:800; }'
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
      /* severity + age, the lane\'s quiet tail — the only two things the deleted
         event card carried at rest that the lane did not already say */
      +'.rcf-meta { font-size:10.5px; color:var(--muted); white-space:nowrap; flex:none;'
      +'  font-variant-numeric:tabular-nums; }'
      +'.rcf-meta b { font-weight:800; color:var(--warn); letter-spacing:.03em; }'
      /* one footer line carrying the as-of, the receipt and the closures control */
      +'.rcf-footer { font-size:10.5px; color:var(--muted); margin-top:6px; line-height:1.5;'
      +'  display:flex; flex-wrap:wrap; align-items:center; gap:4px 14px; }'
      +'.rcf-coldstart-note { font-size:10px; color:var(--muted); margin-left:6px; }'
      /* ── Closures (.rcx-*): the control rides in the footer above, the panel it
         opens lives in #rc-closures and is empty until asked for. ── */
      +'.rcx-toggle { font:inherit; color:var(--muted); background:none; border:0; padding:0;'
      +'  cursor:pointer; font-weight:700; user-select:none; }'
      +'.rcx-toggle:hover { color:var(--text); text-decoration:underline; }'
      +'.rcx-toggle:focus-visible { outline:2px solid var(--link); outline-offset:3px; border-radius:3px; }'
      +'.rcx-panel { margin-top:8px; display:flex; flex-direction:column; gap:4px;'
      +'  border:1px solid var(--line); border-radius:9px; padding:8px 12px; background:var(--panel2); }'
      +'.rcx-panel[hidden] { display:none; }'
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
    // The heading absorbs the description it used to sit above: "Rotation Events" was
    // the ledger's own word for its rows, and the two-line .rc-sub under it restated
    // both the section heading above AND the disclaimer that now lives once, in the
    // section sub. "Sector handoffs" is the estate's existing plain word for this
    // (the hero's own handoff card uses it), so the sub earns no line of its own.
    host.innerHTML=''
      +'<section id="rc-events" aria-label="Sector handoffs">'
      +'<h3>⟲ '+L('Sector handoffs','板块交棒')+'</h3>'
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
    // The quiet state used to return EARLY, which since the footer merge would take
    // the as-of stamp and the ? receipt down with it — and leave renderClosures with
    // no footer to mount its control in. Fall through instead: the note replaces the
    // lanes, the footer below is unconditional.
    var html='';
    if(!active.length){
      html+='<p class="rcf-empty">'
        +L('No money-flow events right now — a quiet tape is a valid read. Nothing to do.',
           '当前无资金流向事件——安静的盘面也是有效读数。无需操作。')
        +'</p>';
    } else {
    var sevRank={major:0,notable:1,standard:2};
    var sorted=active.slice().sort(function(a,b){
      var d=(sevRank[a.severity]!=null?sevRank[a.severity]:9)-(sevRank[b.severity]!=null?sevRank[b.severity]:9);
      return d!==0?d:String(b.started||'').localeCompare(String(a.started||''));
    });
    sorted.forEach(function(e){
      // Determine event_type — default to handoff for v1 payload without event_type (graceful degrade)
      var etype=e.event_type||'handoff';
      // Donor/receiver labels
      var donorName,receiverName;
      if(etype==='correlation_break'||etype==='contagion_break'){
        // contagion — use a+b from contagion field or from the event itself
        donorName=isZh()
          ?esc(e.from_leg&&(e.from_leg.name_zh||e.from_leg.name_en)||esc(e.from_leg&&e.from_leg.key)||'—')
          :esc(e.from_leg&&(e.from_leg.name_en||e.from_leg.key)||'—');
        receiverName=isZh()
          ?esc(e.to_leg&&(e.to_leg.name_zh||e.to_leg.name_en)||'—')
          :esc(e.to_leg&&(e.to_leg.name_en||e.to_leg.key)||'—');
      } else {
        donorName=isZh()
          ?esc(e.from_leg&&(e.from_leg.name_zh||e.from_leg.name_en)||e.donor||'—')
          :esc(e.from_leg&&(e.from_leg.name_en||e.from_leg.key)||e.donor||'—');
        receiverName=isZh()
          ?esc(e.to_leg&&(e.to_leg.name_zh||e.to_leg.name_en)||e.receiver||'—')
          :esc(e.to_leg&&(e.to_leg.name_en||e.to_leg.key)||e.receiver||'—');
      }
      // Mag-7 basket pill: never show "MAGS"
      if((e.to_leg&&(e.to_leg.key==='mag7'||e.to_leg.key==='mag7_basket'))||e.receiver==='mag7_basket'){
        receiverName=isZh()?'七巨头等权篮子':'Mag-7 basket';
      }
      // Health / faltering
      var h=e.health||null;
      var isFaltering=!!(h&&(h.weakening||h.lapse_count>=2||h.neg_run>=2));
      var effectiveType=isFaltering?'faltering':etype;

      // State line and stance per type
      var stateLine,stanceText,stanceCls;
      if(effectiveType==='into_strength'){
        stateLine=t('Strength rotating toward '+receiverName,'强势正在轮向'+receiverName);
        stanceText=t('In favour — watch for entry','处于优势——留意入场');
        stanceCls='rcf-favour';
      } else if(effectiveType==='contagion_break'||effectiveType==='correlation_break'){
        stateLine=t(donorName+' and '+receiverName+' no longer offsetting — falling together',
                    donorName+'与'+receiverName+'不再互相对冲——同步下跌');
        stanceText=t('Stand aside — diversification fading','暂避——分散效果减弱');
        stanceCls='rcf-aside';
      } else if(effectiveType==='faltering'){
        stateLine=t(donorName+'→'+receiverName+' rotation weakening',donorName+'→'+receiverName+'轮动转弱');
        stanceText=t('Rotation weakening — may close','轮动转弱——或将关闭');
        stanceCls='rcf-weak';
      } else {
        // handoff (default for unknown types — cautious fallback per spec)
        stateLine=t('Money leaving '+donorName+', turning up in '+receiverName,
                    '资金撤出'+donorName+'，在'+receiverName+'转强');
        stanceText=t('Watch — don\'t chase','观望，不要追高');
        stanceCls='rcf-watch';
      }

      /* ── Tier-2 receipt. This hover is now the ONLY home for the mechanics.
         The event card that used to repeat every one of these figures BELOW the
         lane — same event, same blowoff / off-low / ratio numbers, same handoff
         census, wrapped in a prose restatement of the state line — was deleted,
         so everything it carried is folded in here: severity, day count, the
         nightly's own copy, and the census.
         Both languages are built separately on purpose: the old code joined ONE
         t()-resolved array into BOTH attributes, so data-tip-zh carried English
         whenever the page happened to render in EN. ── */
      var r=e.receipts||{};
      var tEn=[], tZh=[];
      var push=function(en,zh){ tEn.push(en); tZh.push(zh); };
      var SEVW={major:{en:'Major',zh:'重大'},notable:{en:'Notable',zh:'值得注意'},
                standard:{en:'Standard',zh:'一般'}}[e.severity||'standard']
                ||{en:String(e.severity||''),zh:String(e.severity||'')};
      push(SEVW.en+(e.day_n!=null?' · day '+e.day_n:'')+(e.started?' · started '+e.started:''),
           SEVW.zh+(e.day_n!=null?' · 第'+e.day_n+'天':'')+(e.started?' · 起于'+e.started:''));
      if(e.copy_en||e.copy_zh)
        push(String(e.copy_en||e.copy_zh||''), String(e.copy_zh||e.copy_en||''));
      if(r.blowoff&&r.blowoff.drawdown_pct!=null)
        push('Out: '+donorName+' −'+(r.blowoff.drawdown_pct*100).toFixed(0)+'% from peak',
             '流出：'+donorName+' 较高点 −'+(r.blowoff.drawdown_pct*100).toFixed(0)+'%');
      if(r.turn&&r.turn.off_low_pct!=null)
        push('In: '+receiverName+' +'+(r.turn.off_low_pct*100).toFixed(1)+'% off its low',
             '流入：'+receiverName+' 自低点 +'+(r.turn.off_low_pct*100).toFixed(1)+'%');
      if(r.ratio&&r.ratio.ratio_chg_10s!=null)
        push('Their ratio: '+(r.ratio.ratio_chg_10s>0?'+':'')+(r.ratio.ratio_chg_10s*100).toFixed(1)
               +'% over 10 sessions'+(r.ratio.ratio_20s_high?', a 20-session high':''),
             '两者比值：10个交易日 '+(r.ratio.ratio_chg_10s>0?'+':'')+(r.ratio.ratio_chg_10s*100).toFixed(1)
               +'%'+(r.ratio.ratio_20s_high?'，为20个交易日新高':''));
      // Flow receipt — only if flow_receipts present (v2)
      var fr=e.flow_receipts||null;
      if(fr&&fr.receiver&&fr.receiver.flow_5d_mn!=null)
        push('ETF flow: $'+(fr.receiver.flow_5d_mn/1e6).toFixed(0)+'M'+(fr.receiver.flow_asof?' (as of '+fr.receiver.flow_asof+')':''),
             'ETF资金：$'+(fr.receiver.flow_5d_mn/1e6).toFixed(0)+'M'+(fr.receiver.flow_asof?'（截至'+fr.receiver.flow_asof+'）':''));
      // Ruler — the measured census of past handoffs, descriptive only
      var ru=(ev&&ev.ruler&&ev.ruler.modern&&ev.ruler.modern.run_pct)?ev.ruler.modern:null;
      if(ru&&ru.n>=5)
        push('Past handoffs: about half ran to +'+ru.run_pct.median+'% and peaked around '
               +ru.sessions_to_peak.median+' sessions in ('+ru.n+' past cases, descriptive only)',
             '历史交棒：约半数上涨约 +'+ru.run_pct.median+'%，并在约'+ru.sessions_to_peak.median
               +'个交易日见顶（'+ru.n+'次历史样本，仅描述性）');
      push('A heads-up, not a buy signal — nothing here ranks, gates or sizes anything.',
           '仅为提示，非买入信号——此处不排名、不门控、不调仓。');
      var tipEn=tEn.join(' · ');
      var tipZh=tZh.join(' · ');

      var laneClass='rcf-lane rcf-'+esc(etype.replace('correlation_break','contagion_break'));
      html+='<div class="'+laneClass+'" data-tip-en="'+esc(tipEn)+'" data-tip-zh="'+esc(tipZh)+'">'
        +'<span class="rcf-pill">'+donorName+'</span>'
        +'<span class="rcf-arrow">&#x279C;</span>'
        +'<span class="rcf-pill">'+receiverName+'</span>'
        +'<span class="rcf-state">'+stateLine+'</span>'
        +'<span class="rcf-stance '+stanceCls+'">'+stanceText+'</span>'
        // severity + age, the only two things the deleted card carried at rest.
        // "Major" is called out because it changes how much attention the row is
        // worth; "standard" and "notable" get no badge — a label on every row is
        // a constant, and a constant belongs nowhere on the row.
        +'<span class="rcf-meta">'
        +((e.severity==='major')?'<b>'+t('Major','重大')+'</b> · ':'')
        +(e.day_n!=null?t('day '+esc(e.day_n),'第'+esc(e.day_n)+'天'):'')
        +'</span>';
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
    }  // /else — lanes rendered
    // Footer — unconditional: one as-of, one receipt, and the mount point
    // renderClosures appends its control to.
    var asof=(ev&&ev.as_of)||'—';
    var coldstarNote=(ev&&ev.coldstart)?
      '<span class="rcf-coldstart-note"><span class="rcf-help" data-tip-en="History was rebuilt tonight — counts may look reset." data-tip-zh="今晚重建了历史——计数可能看似重置。">?</span></span>'
      :'';
    // ONE footer line for the whole rail: one as-of, one receipt, and (appended by
    // renderClosures) the closures toggle. The disclaimer it used to repeat here now
    // lives once, in the section sub above.
    html+='<div class="rcf-footer">'
      +'<span class="l-en">as of '+esc(asof)+'</span>'
      +'<span class="l-zh">截至 '+esc(asof)+'</span>'
      +' <span class="rcf-help" tabindex="0" role="button" aria-label="details"'
      +' data-tip-en="Events are logged and their outcomes tracked; most are still being measured, so nothing here ranks, gates, or sizes anything. Cross-sector and into-strength reads use each series\' own history (the Mag-7 line is an equal-weight basket, not the MAGS ETF). Started from the 2026-06-25 semis→Mag-7 miss."'
      +' data-tip-zh="事件会被记录、结果会被跟踪；多数仍在观察中，因此此处不排名、不门控、不调仓。跨板块与「轮向强势」读数使用各自序列的历史（七巨头用等权篮子，而非MAGS ETF）。源自2026-06-25存储→七巨头轮动漏报的复盘。">?</span>'
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
      var dKey=c.from_leg||c.from_sector||c.donor, rKey=c.to_leg||c.to_sector||c.receiver;
      var rkey=c.reason||c.close_reason||'';
      var rmap=REASON[rkey]||{en:rkey,zh:rkey};
      var dayN=c.day_n!=null?c.day_n:'—';
      // Dual l-en/l-zh twins, not a t() snapshot: the panel is built once and the
      // module only re-renders on the language MutationObserver's async fetch, so a
      // single-language row showed the PREVIOUS language until that round-trip landed.
      listHtml+='<div class="rcx-row">'+L(
          esc(dKey?legName(dKey,false):'—')+' → '+esc(rKey?legName(rKey,false):'—')
            +' · ended: '+esc(rmap.en)+' · lasted '+dayN+' sessions',
          esc(dKey?legName(dKey,true):'—')+' → '+esc(rKey?legName(rKey,true):'—')
            +' · 结束：'+esc(rmap.zh)+' · 持续 '+dayN+'个交易日'
        )+'</div>';
    });
    /* The strip used to be a bordered row of its own, sitting between the lanes and
       the (now deleted) cards and costing a full band for a control nobody expands
       most days. The CONTROL now rides in the flow-map footer beside the as-of — one
       line instead of two — and only the PANEL it opens lives down here, empty until
       asked for. Falls back to rendering the control inline when there is no footer
       to ride in (the no-active-events path). */
    var expanded=false;
    var id='rcx-list-'+Math.random().toString(36).slice(2,7);
    var togHtml='<button class="rcx-toggle" type="button" id="rcx-tog-'+id+'" aria-expanded="false" aria-controls="'+id+'">'
      +'<span class="l-en">Closed recently: '+N+' ▾</span>'
      +'<span class="l-zh">近期关闭：'+N+' ▾</span>'
      +'</button>';
    var panelHtml='<div class="rcx-panel" id="'+id+'" hidden>'+listHtml
      +'<div class="rcx-foot">'
      +L('Listed so nothing disappears silently.','列出以避免事件悄然消失。')
      +'</div></div>';
    var foot=document.querySelector('#rc-flowmap-content .rcf-footer');
    if(foot){ foot.insertAdjacentHTML('beforeend',' '+togHtml); el.innerHTML=panelHtml; }
    else { el.innerHTML=togHtml+panelHtml; }
    var tog=document.getElementById('rcx-tog-'+id);
    var lst=document.getElementById(id);
    if(tog&&lst){
      tog.addEventListener('click',function(){
        expanded=!expanded;
        lst.hidden=!expanded;
        tog.setAttribute('aria-expanded',expanded?'true':'false');
      });
    }
  }

  /* ── render — the split-sector strip.
     WHAT WAS DELETED HERE, and why nothing was lost:

     1. The event-card grid. It re-rendered `ev.active` — the SAME list the flow
        lanes above already draw — as cards whose prose restated the lane's own
        state line, under receipt lines that repeated blowoff / off-low / ratio and
        the handoff census that the lane's hover tip ALSO carried. One event, three
        tellings, ~250px. Severity and day count moved onto the lane; the prose and
        every figure moved into the lane's Tier-2 hover (see renderFlowLanes).
     2. The empty-state note. renderFlowLanes already prints one for the same
        condition, four lines higher.
     3. The cross-sector callout ("Money is rotating toward X — see it in the flow
        map above"), which pointed at a lane roughly 200px above that says exactly
        that, in those words.
     4. The closing caveat — the THIRD "a heads-up, not a buy signal" before the
        reader reached the map, and the second as-of stamp in one panel. The
        disclaimer is now stated once in the section sub; the receipt behind it
        lives in the flow-map footer's ? tip. ── */
  function render(ev, frag){
    var el=document.getElementById('rc-events-content');
    if(!el) return;
    var html='';
    var rows=(frag&&frag.sectors)||[];
    var flagged=rows.filter(function(r){return r.fragmented;});
    if(flagged.length){
      // the stance IS the label: the old header ("Fragmented sectors — aggregate
      // reads not representative") and the caption under the chips ("Judge the
      // pieces, not the sector average") said the same thing on either side of
      // chips that say it a third time. One line, and it tells you what to do.
      html+='<div class="rc-frag"><div class="rc-frag-hd">'
        +t('Split inside — judge the pieces, not the average',
           '内部分化——看内部分支，别看平均')+'</div><div class="rc-frag-chips">';
      // …and the chip's own leading clause said it a third time. Strip ONLY that
      // exact engine prefix, so a copy change upstream fails soft into showing the
      // whole sentence rather than swallowing the evidence behind it.
      var FRAG_PFX=/^(?:Aggregate read may not be representative|板块聚合读数或失真)\s*[—–-]\s*/;
      flagged.forEach(function(r){
        var body=String((isZh()?r.copy_zh:r.copy_en)||'').replace(FRAG_PFX,'');
        html+='<span class="rc-frag-chip"><b>'+esc(isZh()?r.name_zh:r.name_en)+' ('+esc(r.etf)+')</b> — '
          +esc(body)+'</span>';
      });
      html+='</div></div>';
    }
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
      harvestLegNames(res[0]);   // must precede renderClosures — it names the slugs
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

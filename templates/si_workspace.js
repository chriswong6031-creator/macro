/* ══════════════════════════════════════════════════════════════════════════════
   SI WORKSPACE V2 — hash router · lazy mount · per-view reads · rail provenance
   Masterplan: research/SI_WORKSPACE_V2_MASTERPLAN_BY_FABLE.md §1 / §1b.

   Display tier only. Nothing here originates a signal, a score, a rank or a gate
   (constitution A7): every line it writes is a re-phrasing of a field the nightly
   payload already carries, and any absent input drops its clause rather than
   inventing one.
   ══════════════════════════════════════════════════════════════════════════════ */
(function(){
'use strict';
var VIEWS=['overview','map','moving','money','explore'];
var TITLES={overview:['Overview','总览'],map:['The Map','全景图谱'],
  moving:["What's Moving",'正在轮动'],money:['Money & Breadth','资金与广度'],
  explore:['Explore','深入探索']};
/* View glyphs = the estate's hand-drawn masked-icon family (product-nav-icons /
   dashboard-icons — the same set the nav mega-menus draw), tinted via currentColor.
   Never raw emoji beside the wordmark. */
var GLYPH={
  overview:'dash-icon submenu-icon-intelligence',
  map:'dash-icon dash-icon-compass',
  moving:'dash-icon submenu-icon-rotation',
  money:'dash-icon submenu-icon-flow',
  explore:'dash-icon dash-icon-search'};

/* ── LEGACY_ANCHORS (§2b) ───────────────────────────────────────────────────────
   Every pre-V2 deep link on the estate — the two redirect stubs, chat citations,
   dashboard cards, detail back-links, alert links — resolves here to
   [view, intra-view scroll target]. The ids on the right are the ORIGINAL section
   ids, preserved through the wrap precisely so this table can still reach them.
   Pinned by tests/test_si_workspace_shell.py; unknown hash → overview.
   `#theme-<id>` is NOT in this table on purpose: resolveThemeHash() owns it and
   navigates away to the basket page, so the router must not touch that hash. */
var LEGACY_ANCHORS={
  'actnow-section':['overview','actnow-section'],
  'regime':['overview','regime'],
  'grader':['overview','grader'],
  'si-map':['map','si-map'],
  'rotmap-section':['map','rotmap-section'],
  'sc-cyclemap':['map','sc-cyclemap'],
  'board':['map','board'],
  'si-movement':['moving','si-movement'],
  'rc-events-mount':['moving','rc-events-mount'],
  'rotation-app':['moving','rotation-app'],
  'si-money':['money','si-money'],
  'internals-section':['money','internals-section'],
  'scc-leadership':['money','scc-leadership'],
  'explore-section':['explore','explore-section'],
  'table-section':['explore','table-section'],
  'chart-section':['explore','chart-section'],
  'forming-narratives':['explore','forming-narratives'],
  'tm-mount':['explore','tm-mount']
};

/* ── lazy mount (gate 8) ────────────────────────────────────────────────────────
   Each organ script self-boots on load (readyState is already past 'loading' by
   the time we inject), so appending the tag IS the mount — and it mounts with the
   view ALREADY visible. That ordering is load-bearing, not just a weight saving:
   heatmap.js sizes its treemap from `tm.clientWidth || wrap.clientWidth` and
   subsector_rotation.js from `container.clientWidth`, both of which read 0 inside a
   display:none section and render blank/wrong-width forever.
   Order inside a list is preserved (async=false). time_machine.js draws its map
   through window.SRR, exported by subsector_rotation.js, so explore declares that
   dependency explicitly — `loaded` is global, so it is fetched at most once. */
var LAZY={
  map:['@cycles'],
  moving:['subsector_rotation.js','rotation_events.js','desk_watch.js'],
  money:['heatmap.js'],
  explore:['subsector_rotation.js','time_machine.js']
};
var loaded={}, mounted={}, pendingTrace=null;

/* reuse the optimizer's ?v= immutable URL from the head's preload/prefetch link */
function vUrl(name){
  try{
    var l=document.querySelector('link[rel="preload"][href^="'+name+'"],link[rel="prefetch"][href^="'+name+'"]');
    if(l){ var h=l.getAttribute('href'); if(h) return h; }
  }catch(e){}
  return name;
}
function inject(src,onload){
  var s=document.createElement('script'); s.async=false; s.src=vUrl(src);
  if(onload) s.addEventListener('load',onload);
  document.head.appendChild(s);
}
function loadCycles(){
  if(loaded['@cycles']) return; loaded['@cycles']=true;
  window.SC_LAZY_EXTRAS=true;                       // narr+dna wait for first sector focus
  window.SC_EXTRA_DATA=['sector_cycles_narr_data.js','sector_cycles_dna_data.js'];
  window.SC_SERIES_DATA='sector_cycles_series_data.js';
  var files=['sector_cycles_data.js','mm_charts.js','sector_cycles.js'];
  files.forEach(function(f,i){
    inject(f, i===0?function(){ document.dispatchEvent(new CustomEvent('sc:cycles-data')); }:null);
  });
}
function loadAssets(view){
  var list=LAZY[view]||[];
  for(var i=0;i<list.length;i++){
    var f=list[i];
    if(f==='@cycles'){ loadCycles(); continue; }
    if(loaded[f]) continue;
    loaded[f]=true; inject(f);
  }
}

/* ── helpers ─────────────────────────────────────────────────────────────────── */
function isZh(){ return document.documentElement.getAttribute('data-lang')==='zh'; }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]; }); }
function L(en,zh){ return '<span class="l-en">'+en+'</span><span class="l-zh">'+(zh==null?en:zh)+'</span>'; }
function P(){ return window.BASKETS||null; }
function TI(){ var p=P(); return (p&&p.theme_intel)||null; }

/* ── the composer: __siViewReads(payload) ────────────────────────────────────────
   Composition rules (§1b), enforced by hand because they are copy rules:
     · plain words only — no internal state names, no study names, no raw slugs,
       no untranslated statistics;
     · ≤18 words per line, EN and ZH authored together (never machine-flipped);
     · every clause fail-soft — an absent input drops that clause, and a line with
       no surviving clause stays hidden. Absence is never dressed as a reading;
     · display-tier composition ONLY: counts and names already in the payload, no
       new score, rank, threshold or gate is computed here (A7).
   Each line carries a ? receipt naming the inputs it was composed from. */
function readOverview(el){
  var ti=TI(); if(!ti) return null;
  var from=el.getAttribute('data-from-en'), to=el.getAttribute('data-to-en');
  var fromZh=el.getAttribute('data-from-zh')||from, toZh=el.getAttribute('data-to-zh')||to;
  var n=(((ti.act_now||{}).buy)||[]).length;
  var en=[], zh=[];
  if(from&&to){
    en.push(esc(from)+' is handing leadership to '+esc(to)+'.');
    zh.push(esc(fromZh)+'正把领先交给'+esc(toZh)+'。');
  }
  if(n>0){
    en.push(n+(n===1?' name sits':' names sit')+' in the Buy lane.');
    zh.push(n+' 个标的在「立即买入」清单。');
  }else{
    en.push('Nothing is in the Buy lane today.');
    zh.push('今日「立即买入」清单为空。');
  }
  if(!en.length) return null;
  return [en.join(' '), zh.join('')];
}
function readMap(){
  /* __siRvxData is hoisted onto window by __siInitPage — rvxData() itself is declared
     INSIDE that function, so this separate script cannot see the bare name. Reaching
     for `rvxData` directly here fails silently (typeof → 'undefined', catch swallows,
     read stays hidden) and looks exactly like "no data yet". */
  var d=null;
  try{ d=(typeof window.__siRvxData==='function')?window.__siRvxData():null; }catch(e){}
  if(!d||!d.length) return null;
  var lead=d.filter(function(x){ return x.q==='lead'; });   // strong AND still rising
  if(!lead.length) return ['No group is both strong and still rising right now.',
                           '当前没有既强势又仍在上行的板块。'];
  var top=lead[0], n=lead.length;                            // rvxData sorts by score desc
  return [n+(n===1?' group sits':' groups sit')+' top-right — strong and still rising. '
          +esc(top.name)+' is furthest along.',
          n+' 个板块位于右上 — 强势且仍在上行。'+esc(top.name_zh||top.name)+'走得最远。'];
}
function readMoving(){
  var ti=TI(); if(!ti||!ti.themes||!ti.themes.length) return null;
  var up=0, dn=0, seen=0;
  ti.themes.forEach(function(t){
    var v=t&&t.pulse_rank_delta_5d; if(v==null) return;
    seen++; if(v>0) up++; else if(v<0) dn++;
  });
  if(!seen) return null;
  if(!up&&!dn) return ['A quiet tape — no group moved up or down the ranking this week.',
                       '行情平静 — 本周没有板块排名上升或下降。'];
  return [up+(up===1?' group':' groups')+' moved up the ranking this week, '+dn+' slipped.',
          '本周 '+up+' 个板块排名上升，'+dn+' 个下滑。'];
}
function readMoney(el){
  var r=el.getAttribute('data-regime'); if(!r) return null;
  /* display phrasing lifted verbatim from the money-flow card so the two agree */
  var EN={concentrated:'Money is crowding into a few groups — be selective here.',
          broad:'Money is spread across many groups — a broad tide, not a narrow few.',
          mixed:'No single group is leading the money right now.'};
  var ZH={concentrated:'资金正向少数板块集中 — 此时应精挑细选。',
          broad:'资金广泛分布于多个板块 — 全面上涨，而非少数领涨。',
          mixed:'当前没有单一板块主导资金流向。'};
  if(!EN[r]) return null;
  return [EN[r], ZH[r]];
}
function readExplore(){
  var p=P(), n=((p&&p.baskets)||[]).length;
  if(!n) return null;
  return [n+' baskets — every member, every record.', n+' 个篮子 — 全部成分，全部记录。'];
}
var RECEIPTS={
  overview:['Composed from tonight’s leadership handoff and the Buy lane count. Display only — it restates the reads below, it does not add one.',
            '由今晚的领涨交棒与「立即买入」清单数量组成。仅为展示 — 复述下方研判，不新增判断。'],
  map:['Counts the groups sitting strong and still rising on the map below, named by the same ranking the map draws. Display only.',
       '统计下方图中既强势又仍在上行的板块，命名沿用图表所用排序。仅为展示。'],
  moving:['Counts how many groups moved up or down this week’s ranking in the payload. A context lens — it ranks nothing and gates nothing.',
          '统计本周排名上升或下降的板块数量。仅为背景视角 — 不排序、不门控。'],
  money:['Restates the money-flow reading shown on the breadth card below, in plain words. Display only.',
         '以平实措辞复述下方广度卡片的资金流向读数。仅为展示。'],
  explore:['Counts the baskets carried in tonight’s payload — the same set the table below lists.',
           '统计今晚数据中的篮子数量 — 与下方表格所列相同。']
};
function paint(view,pair){
  var el=document.getElementById('si-read-'+view); if(!el) return;
  if(!pair){ el.hidden=true; el.innerHTML=''; return; }
  var r=RECEIPTS[view]||['',''];
  el.innerHTML='<span class="si-vr-g '+GLYPH[view]+'" aria-hidden="true"></span>'
    +'<span class="si-vr-t">'+L(pair[0],pair[1])+'</span>'
    +'<span class="si-vr-q" data-tip-en="'+esc(r[0])+'" data-tip-zh="'+esc(r[1])+'">?</span>';
  el.hidden=false;
}
function reads(){
  var o=document.getElementById('si-read-overview');
  if(o) paint('overview',readOverview(o));
  paint('map',readMap());
  paint('moving',readMoving());
  var m=document.getElementById('si-read-money');
  if(m) paint('money',readMoney(m));
  paint('explore',readExplore());
  if(pendingTrace) openTrace(pendingTrace);
}

/* `#read-<id>` (gate 4) — land on overview and open that lane row's trace expand.
   The board is filled asynchronously, so the request is held until it exists. */
function openTrace(id){
  var lanes=document.getElementById('actnow'); if(!lanes||!window.__siTrace) return;
  var row=null, rows=lanes.querySelectorAll('.rvx-trow[data-mlc-bid]');
  for(var i=0;i<rows.length;i++){ if(rows[i].getAttribute('data-mlc-bid')===id){ row=rows[i]; break; } }
  if(!row) return;
  pendingTrace=null;
  row.click();
  try{ row.scrollIntoView({block:'center'}); }catch(e){ row.scrollIntoView(); }
}

/* ── activation ──────────────────────────────────────────────────────────────── */
var BASE_TITLE=(document.title||'').split(' · ')[0];
var current=null;
function activate(view,target){
  if(VIEWS.indexOf(view)<0) view='overview';
  var i, secs=document.querySelectorAll('.si-view'), btns=document.querySelectorAll('.si-view-btn');
  for(i=0;i<secs.length;i++) secs[i].classList.toggle('on',secs[i].getAttribute('data-view')===view);
  for(i=0;i<btns.length;i++){
    var on=btns[i].getAttribute('data-view')===view;
    btns[i].classList.toggle('on',on);
    if(on) btns[i].setAttribute('aria-current','page'); else btns[i].removeAttribute('aria-current');
  }
  try{ document.title=BASE_TITLE+' · '+TITLES[view][isZh()?1:0]; }catch(e){}
  current=view;
  /* First activation mounts the heavy organs. The view must be laid out first so the
     width-measuring renderers see a real box — but do NOT wait for a frame to get
     that: requestAnimationFrame never fires while the tab is hidden, so a background
     tab (or a restored session) would activate the view, set mounted[view]=true, and
     then never load a single organ — a permanently blank panel with no error anywhere.
     Reading offsetHeight forces a synchronous reflow instead: deterministic, and it
     does not care whether anyone is looking. */
  if(!mounted[view]){
    mounted[view]=true;
    var sec=document.querySelector('.si-view[data-view="'+view+'"]');
    if(sec) void sec.offsetHeight;
    loadAssets(view);
    try{ window.dispatchEvent(new Event('resize')); }catch(e){}     // nudge autoSize charts
  }
  reads();
  if(target){
    var el=document.getElementById(target);
    if(el){ try{ el.scrollIntoView({block:'start'}); }catch(e){ el.scrollIntoView(); } }
    else if(history.replaceState) history.replaceState(null,'','#'+view);
  }
}
function route(){
  var h=(location.hash||'').replace(/^#/,'');
  try{ h=decodeURIComponent(h); }catch(e){}
  if(h.indexOf('theme-')===0){ activate('overview',null); return; }  // resolver owns it
  if(h.indexOf('read-')===0){ pendingTrace=h.slice(5); activate('overview',null); return; }
  if(VIEWS.indexOf(h)>=0){ activate(h,null); return; }
  if(LEGACY_ANCHORS[h]){ activate(LEGACY_ANCHORS[h][0],LEGACY_ANCHORS[h][1]); return; }
  activate('overview',null);                                        // unknown → overview
  if(!h&&history.replaceState) history.replaceState(null,'','#overview');
}

window.__siViewReads=reads;
window.__siRoute=route;
window.addEventListener('hashchange',route);
document.addEventListener('langchange',function(){
  try{ document.title=BASE_TITLE+' · '+TITLES[current||'overview'][isZh()?1:0]; }catch(e){}
});
route();
})();

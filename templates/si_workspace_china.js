/* ══════════════════════════════════════════════════════════════════════════════
   SI WORKSPACE (CHINA) — hash router · lazy mount · per-view reads · rail provenance

   China sibling of si_workspace.js. Deliberately a SEPARATE file, not a shared one
   with a config object: the two pages differ in view count, asset manifest, anchor
   table and read composers, and the US router's tables are pinned line-by-line by
   tests/test_si_workspace_shell.py. Two small files with a guard each beats one
   file with four conditionals. tests/test_china_si_workspace_shell.py pins this one.

   Display tier only. Nothing here originates a signal, a score, a rank or a gate
   (constitution A7): every line it writes is a re-phrasing of a field the nightly
   payload already carries, and any absent input drops its clause rather than
   inventing one.
   ══════════════════════════════════════════════════════════════════════════════ */
(function(){
'use strict';
/* Four views, not the US five: this desk carries no Money & Breadth organ. An empty
   fifth tab would be a promise the payload cannot keep. */
var VIEWS=['overview','map','moving','explore'];
var TITLES={overview:['Overview','总览'],map:['The Map','全景图谱'],
  moving:["What's Moving",'正在轮动'],explore:['Explore','深入探索']};
/* View glyphs = the estate's hand-drawn masked-icon family (product-nav-icons /
   dashboard-icons — the same set the nav mega-menus draw), tinted via currentColor.
   Never raw emoji beside the wordmark. */
var GLYPH={
  overview:'dash-icon submenu-icon-intelligence',
  map:'dash-icon dash-icon-compass',
  moving:'dash-icon submenu-icon-rotation',
  explore:'dash-icon dash-icon-search'};

/* ── LEGACY_ANCHORS ─────────────────────────────────────────────────────────────
   Every pre-workspace deep link into this page — the two redirect stubs
   (baskets_china.html → #si-explore, subsector_rotation_china.html → #si-movement),
   chat citations, dashboard cards, basket detail back-links — resolves here to
   [view, intra-view scroll target]. The ids on the right are the ORIGINAL section
   ids, preserved through the wrap precisely so this table can still reach them.
   An id dropped from here does not 404: it silently lands on overview, and nobody
   ever finds that panel again. Pinned by tests/test_china_si_workspace_shell.py.
   `#b-<id>` and `#theme-<id>` are NOT in this table on purpose — openBasket() and
   openTheme() own those, so the router routes to their view and touches nothing. */
var LEGACY_ANCHORS={
  'actnow-section':['overview','actnow-section'],
  'sc-board':['overview','sc-board'],
  'board':['overview','board'],
  'regime':['overview','regime'],
  'grader':['overview','grader'],
  'si-map':['map','si-map'],
  'sc-cyclemap':['map','sc-cyclemap'],
  'sc-desk-table':['map','sc-desk-table'],
  'si-movement':['moving','si-movement'],
  'rc-events-cn':['moving','rc-events-cn'],
  'rotation-app':['moving','rotation-app'],
  'si-explore':['explore','si-explore'],
  'table-section':['explore','table-section'],
  'chart-section':['explore','chart-section'],
  'categories':['explore','categories'],
  'entry-radar':['explore','entry-radar'],
  'forming-narratives':['explore','forming-narratives'],
  'reversal-sleeve-card':['explore','reversal-sleeve-card']
};

/* ── lazy mount ─────────────────────────────────────────────────────────────────
   Each organ script self-boots on load (readyState is already past 'loading' by the
   time we inject), so appending the tag IS the mount — and it mounts with the view
   ALREADY visible. That ordering is load-bearing, not just a weight saving:
   sector_cycles.js sizes its chart from the container's clientWidth and
   subsector_rotation.js from `container.clientWidth`, both of which read 0 inside a
   display:none section and render blank/wrong-width forever.

   '@cycles' is listed on overview as well as map, and that is deliberate: the
   conviction cards on the overview board each draw a mini cycle-position sparkline
   from window.SECTOR_CYCLES. Overview is the default view, so the trio still loads
   at first paint exactly as it did before the workspace — `loaded` is global, so
   opening The Map afterwards reuses it rather than fetching a second copy. */
var LAZY={
  overview:['@cycles'],
  map:['@cycles'],
  moving:['subsector_rotation.js']
};
var loaded={}, mounted={};

/* reuse the optimizer's ?v= immutable URL from the head's preload/prefetch link.
   Injected names bypass the optimizer's src rewriting, so without this every lazy
   asset would load unversioned — a second cache key for identical bytes. */
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
  window.SC_EXTRA_DATA=['sector_cycles_china_narr_data.js','sector_cycles_china_dna_data.js'];
  window.SC_SERIES_DATA='sector_cycles_china_series_data.js';   // heavy arrays, after first paint
  var files=['sector_cycles_china_data.js','mm_charts.js','sector_cycles.js'];
  files.forEach(function(f,i){
    /* the board's mini sparklines listen for sc:cycles-data — fire it as soon as the
       DATA file lands, not after the whole trio, so the cards fill without waiting
       on the charting engine */
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
function SC(){ return window.SECTOR_CENTRAL||null; }

/* ── the composer: one plain-word line per view ─────────────────────────────────
   Composition rules, enforced by hand because they are copy rules:
     · plain words only — no internal state names, no study names, no raw slugs,
       no untranslated statistics;
     · short lines, EN and ZH authored together (never machine-flipped);
     · every clause fail-soft — an absent input drops that clause, and a line with
       no surviving clause stays hidden. Absence is never dressed as a reading;
     · display-tier composition ONLY: counts and names already in the payload, no
       new score, rank, threshold or gate is computed here (A7).
   Each line carries a ? receipt naming the inputs it was composed from. */
function readMap(){
  var d=SC(); if(!d) return null;
  var list=(d.sectors||[]);
  if(!list.length) return null;
  var early=0, name=null, nameZh=null;
  for(var i=0;i<list.length;i++){
    var cy=list[i].cycle||{};
    /* "Prime entry" is the engine's own phase label for the washed-out end of the
       clock — counted, never re-derived */
    if(cy.phaseLabel==='Prime entry'||cy.phase==='Recovery'){
      early++;
      if(name===null){ name=list[i].name; nameZh=list[i].name_zh||list[i].name; }
    }
  }
  if(!early) return ['No sector is sitting at the washed-out end of its cycle right now.',
                     '当前没有板块处于自身周期的超跌端。'];
  return [early+(early===1?' sector sits':' sectors sit')+' at the washed-out end of the cycle — '
          +esc(name)+' among them.',
          early+' 个板块处于周期超跌端 — 其中包括'+esc(nameZh)+'。'];
}
function readMoving(){
  var ti=(P()&&P().theme_intel)||null;
  var themes=(ti&&ti.themes)||null;
  if(!themes||!themes.length) return null;
  var up=0, dn=0, seen=0;
  themes.forEach(function(t){
    var v=t&&t.pulse_rank_delta_5d; if(v==null) return;
    seen++; if(v>0) up++; else if(v<0) dn++;
  });
  if(!seen) return null;
  if(!up&&!dn) return ['A quiet tape — no theme moved up or down the ranking this week.',
                       '行情平静 — 本周没有主题排名上升或下降。'];
  return [up+(up===1?' theme':' themes')+' moved up the ranking this week, '+dn+' slipped.',
          '本周 '+up+' 个主题排名上升，'+dn+' 个下滑。'];
}
function readExplore(){
  var p=P(), n=((p&&p.baskets)||[]).length;
  if(!n) return null;
  return [n+' baskets — every member, every record.', n+' 个篮子 — 全部成分，全部记录。'];
}
var RECEIPTS={
  map:['Counts the sectors the nightly cycle read already places at the washed-out end of their own clock, named by that same read. Display only — it adds no call.',
       '统计今晚周期读数已判定处于自身周期超跌端的板块，命名沿用同一读数。仅为展示 — 不新增判断。'],
  moving:['Counts how many themes moved up or down this week’s ranking in the payload. A context lens — it ranks nothing and gates nothing.',
          '统计本周排名上升或下降的主题数量。仅为背景视角 — 不排序、不门控。'],
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
/* the rail footer: the workspace's provenance lives with its navigation */
function paintFoot(){
  var d=SC(), p=P();
  var asof=(d&&d.as_of)||(p&&p.as_of)||null;
  /* Operator 2026-08-04: the rail's "as of <date>" + "Self-grader: N% hit · n=M"
     stamp is removed. Provenance is NOT lost — the desk header still prints
     "… · as of {{ desk.as_of }}", and the measured-accuracy read keeps its own
     card (the #grader panel), so the rail was showing the same two facts a third
     time in the smallest type on the page.
     The slots themselves stay in the markup: tests/test_china_si_workspace_shell.py
     asserts id="si-side-asof" and id="si-side-grade" exist. Left empty, they
     collapse — remove the ids and that test goes red for the wrong reason. */
  var a=document.getElementById('si-side-asof');
  if(a) a.innerHTML='';
  var g=document.getElementById('si-side-grade');
  if(g) g.innerHTML='';
}
function reads(){
  paint('map',readMap());
  paint('moving',readMoving());
  paint('explore',readExplore());
  paintFoot();
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
  /* Announce the switch on every activation, not just the first mount. Organs the page
     itself builds (the basket overlay chart) cannot be created while their view is
     display:none — lightweight-charts binds autoSize at creation and a chart born
     zero-wide never recovers — so they wait for this event to draw with a real box. */
  try{ document.dispatchEvent(new CustomEvent('si:view',{detail:view})); }catch(e){}
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
  /* Both deep-link families the redirect stubs forward belong to the page's own
     resolvers (openBasket / openTheme, which expand a row inside Explore). Route to
     their view and then get out of the way — rewriting the hash here would eat the
     link before the resolver ever read it. */
  if(h.indexOf('b-')===0){ activate('explore',null); return; }
  if(h.indexOf('theme-')===0){ activate('explore',null); return; }
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
  reads();
});
/* The basket payload arrives by fetch, long after this file runs; re-compose the
   reads when it lands rather than baking "no data yet" into the panels. */
document.addEventListener('csi:payload',reads);
route();
})();

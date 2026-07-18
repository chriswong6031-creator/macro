/* subsector_rotation.js — the Subsector Rotation desk.
 *
 * Reads marketdata/subsector_rotation.json (built from a broad-universe
 * theme→subsector performance) and renders three linked views:
 *   • a Relative-Rotation map (RS-Ratio × RS-Momentum) with the four rotation
 *     quadrants — Leading / Weakening / Improving / Lagging;
 *   • "Emerging now" + "Fading" rails — the accelerating early-entry list and
 *     the leaders rolling over;
 *   • a sortable leadership/velocity table.
 * Toggle Subsectors ⇄ Themes ⇄ Sector ETFs. No framework; colours come from the
 * live theme tokens so a theme/lang switch recolours instantly.
 *
 * window.SRR is exported at the top level: a shared renderer used by both
 * the live rotation desk and the Time Machine.
 */

/* ────────────────────────────────────────────────────────────────────────────
 * PART 1 — Shared Rotation Renderer (window.SRR)
 * SRR.render(container, spec) draws an SVG RRG scatter into `container`.
 *
 * spec: {
 *   points: [{key, label, quadrant, x, y, r, trail:[[x,y]...]|null,
 *             ring:'in'|'out'|null, ringWeight:number, showLabel:bool, hot:bool}],
 *   domain: {xMin,xMax,yMin,yMax} | null  (auto from points),
 *   axis:   {xLo,xHi,yLo,yHi}            (bilingual end-label strings),
 *   zoomQuadrant: 'leading'|'weakening'|'improving'|'lagging'|null,
 *   onHover: function(key, clientX, clientY)|null,
 *   onClick: function(key)|null,
 *   ariaLabel: string
 * }
 * ──────────────────────────────────────────────────────────────────────────── */
(function (global) {
  'use strict';

  // ---- shared helpers (duplicated in the desk scope below for closure safety) ----
  function _esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function _isZh(){return typeof document!=='undefined'&&document.documentElement.getAttribute('data-lang')==='zh';}

  var QCOL_SRR={leading:'--up',weakening:'--warn',improving:'--link',lagging:'--down'};
  var QUAD_SRR={
    leading:  {en:'Leading',   zh:'领先', cls:'q-lead'},
    weakening:{en:'Weakening', zh:'走弱', cls:'q-weak'},
    improving:{en:'Improving', zh:'改善', cls:'q-impr'},
    lagging:  {en:'Lagging',   zh:'落后', cls:'q-lag'}
  };
  var QUADX_SRR={
    leading:  {en:'strong & rising',    zh:'强且上行'},
    weakening:{en:'strong but fading',  zh:'强但转弱'},
    improving:{en:'turning up',         zh:'触底回升'},
    lagging:  {en:'weak & falling',     zh:'弱且下行'}
  };
  function _qFill(q,a){return 'color-mix(in srgb, var('+(QCOL_SRR[q]||'--muted')+') '+a+'%, transparent)';}

  function SRR_render(container, spec) {
    var pts     = spec.points || [];
    var zoom    = spec.zoomQuadrant || null;
    var axs     = spec.axis || {};
    var onHov   = spec.onHover || null;
    var onClk   = spec.onClick || null;

    var W = Math.max(320, container.clientWidth || 820);
    var H = Math.max(470, Math.min(W * 0.54, 720));
    // If container is taller (e.g. TM fixed-size box), use the taller dimension
    if (container._tmHeight) H = container._tmHeight;
    var pad = {l:56, r:24, t:30, b:52};
    var plotX=pad.l, plotY=pad.t, plotW=W-pad.l-pad.r, plotH=H-pad.t-pad.b;

    // --- domain ---
    var xMin, xMax, yMin, yMax;
    if (spec.domain) {
      xMin=spec.domain.xMin; xMax=spec.domain.xMax;
      yMin=spec.domain.yMin; yMax=spec.domain.yMax;
    } else if (zoom) {
      var zpts = pts.filter(function(p){return p.quadrant===zoom;});
      if (zpts.length) {
        var xa=[], ya=[];
        zpts.forEach(function(p){
          xa.push(p.x); ya.push(p.y);
          (p.trail||[]).forEach(function(t){xa.push(t[0]);ya.push(t[1]);});
        });
        xMin=Math.min.apply(null,xa); xMax=Math.max.apply(null,xa);
        yMin=Math.min.apply(null,ya); yMax=Math.max.apply(null,ya);
        var px=(xMax-xMin||1)*0.16, py=(yMax-yMin||1)*0.16;
        xMin-=px; xMax+=px; yMin-=py; yMax+=py;
        if(zoom==='leading'||zoom==='weakening') xMin=Math.min(xMin,-0.05); else xMax=Math.max(xMax,0.05);
        if(zoom==='leading'||zoom==='improving') yMin=Math.min(yMin,-0.05); else yMax=Math.max(yMax,0.05);
      } else {
        xMin=-1.2; xMax=1.2; yMin=-1.2; yMax=1.2;
      }
    } else {
      var xs=pts.map(function(p){return p.x;}), ys=pts.map(function(p){return p.y;});
      var xm=Math.max(0.6,Math.max.apply(null,xs.map(Math.abs)))*1.12,
          ym=Math.max(0.6,Math.max.apply(null,ys.map(Math.abs)))*1.12;
      xMin=-xm; xMax=xm; yMin=-ym; yMax=ym;
    }
    function X(v){return plotX+(v-xMin)/((xMax-xMin)||1)*plotW;}
    function Y(v){return plotY+(yMax-v)/((yMax-yMin)||1)*plotH;}
    var cx=X(0), cy=Y(0);

    // --- filter to visible points ---
    var visPts = zoom ? pts.filter(function(p){return p.quadrant===zoom;}) : pts;

    // --- backgrounds ---
    var bg;
    if (zoom) {
      bg='<rect x="'+plotX+'" y="'+plotY+'" width="'+plotW+'" height="'+plotH+'" fill="'+_qFill(zoom,8)+'"></rect>';
    } else {
      bg=''
        +'<rect x="'+cx+'" y="'+plotY+'" width="'+(plotX+plotW-cx)+'" height="'+(cy-plotY)+'" fill="'+_qFill('leading',7)+'" class="sr-qz" data-q="leading"></rect>'
        +'<rect x="'+plotX+'" y="'+plotY+'" width="'+(cx-plotX)+'" height="'+(cy-plotY)+'" fill="'+_qFill('improving',7)+'" class="sr-qz" data-q="improving"></rect>'
        +'<rect x="'+cx+'" y="'+cy+'" width="'+(plotX+plotW-cx)+'" height="'+(plotY+plotH-cy)+'" fill="'+_qFill('weakening',7)+'" class="sr-qz" data-q="weakening"></rect>'
        +'<rect x="'+plotX+'" y="'+cy+'" width="'+(cx-plotX)+'" height="'+(plotY+plotH-cy)+'" fill="'+_qFill('lagging',7)+'" class="sr-qz" data-q="lagging"></rect>';
    }

    // --- center cross ---
    var lines='';
    if(cx>=plotX-0.5&&cx<=plotX+plotW+0.5) lines+='<line x1="'+cx.toFixed(1)+'" y1="'+plotY+'" x2="'+cx.toFixed(1)+'" y2="'+(plotY+plotH)+'" stroke="var(--line)"></line>';
    if(cy>=plotY-0.5&&cy<=plotY+plotH+0.5) lines+='<line x1="'+plotX+'" y1="'+cy.toFixed(1)+'" x2="'+(plotX+plotW)+'" y2="'+cy.toFixed(1)+'" stroke="var(--line)"></line>';

    // --- trails + dots ---
    var defs='', tails='', dots='', cands=[], gi=0;
    visPts.forEach(function(p) {
      var q=p.quadrant, col='var('+(QCOL_SRR[q]||'--muted')+')';
      var r=p.r||6;
      var px=X(p.x), py=Y(p.y);
      // trail
      var trail = p.trail||[];
      if (trail.length > 0) {
        var gid='srg'+(gi++);
        var allTPs = trail.concat([[p.x,p.y]]);
        var s0=[X(allTPs[0][0]),Y(allTPs[0][1])];
        var s1=allTPs.length>1?[X(allTPs[Math.floor(allTPs.length/2)][0]),Y(allTPs[Math.floor(allTPs.length/2)][1])]:s0;
        var s2=[px,py];
        // direction from last trail segment to now
        var prevTP = allTPs[allTPs.length-2];
        var ddx=s2[0]-(prevTP?X(prevTP[0]):s1[0]), ddy=s2[1]-(prevTP?Y(prevTP[1]):s1[1]);
        var dl=Math.sqrt(ddx*ddx+ddy*ddy);
        if(dl<0.5){ddx=s2[0]-s0[0];ddy=s2[1]-s0[1];dl=Math.sqrt(ddx*ddx+ddy*ddy)||1;}
        ddx/=dl; ddy/=dl;
        var tip=[s2[0]-(r+2)*ddx, s2[1]-(r+2)*ddy];
        // Build gradient from oldest to tip
        defs+='<linearGradient id="'+gid+'" gradientUnits="userSpaceOnUse" x1="'+s0[0].toFixed(1)+'" y1="'+s0[1].toFixed(1)+'" x2="'+tip[0].toFixed(1)+'" y2="'+tip[1].toFixed(1)+'">'
          +'<stop offset="0" stop-color="'+col+'" stop-opacity="0"></stop>'
          +'<stop offset="0.45" stop-color="'+col+'" stop-opacity="0.20"></stop>'
          +'<stop offset="0.8" stop-color="'+col+'" stop-opacity="0.62"></stop>'
          +'<stop offset="1" stop-color="'+col+'" stop-opacity="1"></stop></linearGradient>';
        // Build path from all trail points to tip
        var pathD = 'M'+s0[0].toFixed(1)+' '+s0[1].toFixed(1);
        for(var ti=1;ti<allTPs.length-1;ti++){
          pathD+=' L'+X(allTPs[ti][0]).toFixed(1)+' '+Y(allTPs[ti][1]).toFixed(1);
        }
        pathD+=' L'+tip[0].toFixed(1)+' '+tip[1].toFixed(1);
        // soft under-halo for a gentle glow, then the crisp fading trail on top
        tails+='<path d="'+pathD+'" stroke="'+col+'" stroke-opacity="0.09" stroke-width="5.4" fill="none" stroke-linecap="round" stroke-linejoin="round"></path>';
        tails+='<path d="'+pathD+'" stroke="url(#'+gid+')" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"></path>';
        var ang=Math.atan2(ddy,ddx), al=14, aw=0.44;
        tails+='<path d="M'+tip[0].toFixed(1)+' '+tip[1].toFixed(1)
          +' L'+(tip[0]-al*Math.cos(ang-aw)).toFixed(1)+' '+(tip[1]-al*Math.sin(ang-aw)).toFixed(1)
          +' L'+(tip[0]-al*Math.cos(ang+aw)).toFixed(1)+' '+(tip[1]-al*Math.sin(ang+aw)).toFixed(1)
          +' Z" fill="'+col+'" fill-opacity="1"></path>';
      }
      // ring (episode)
      if (p.ring) {
        var ringCol = p.ring==='in'?'var(--up)':'var(--down)';
        var rw = p.ringWeight||1.5;
        dots+='<circle cx="'+px.toFixed(1)+'" cy="'+py.toFixed(1)+'" r="'+(r+4.5).toFixed(1)+'" fill="none" stroke="'+ringCol+'" stroke-width="'+rw+'" stroke-opacity=".9"></circle>';
      }
      dots+='<circle cx="'+px.toFixed(1)+'" cy="'+py.toFixed(1)+'" r="'+(r+2.6).toFixed(1)+'" fill="'+_qFill(q,p.hot?26:15)+'" stroke="none"></circle>';
      dots+='<circle class="sr-dot" cx="'+px.toFixed(1)+'" cy="'+py.toFixed(1)+'" r="'+r.toFixed(1)+'" fill="'+_qFill(q,p.hot?90:64)+'" stroke="'+col+'" stroke-opacity=".9" stroke-width="1.4" data-k="'+_esc(p.key)+'"></circle>';
      if (p.showLabel) {
        cands.push({key:p.key, x:px, y:py, r:r, txt:p.label||p.key, hot:!!p.hot});
      }
    });

    // --- greedy label placement with collision drop ---
    var labels='', placed=[];
    cands.slice().sort(function(a,b){return (a.hot?0:1)-(b.hot?0:1);}).forEach(function(c){
      var left=c.x>plotX+plotW*0.66, lw=c.txt.length*6.7+5;
      var lx=left?(c.x-c.r-4-lw):(c.x+c.r+4), ly=c.y+3.6;
      var box=[lx,ly-11,lx+lw,ly+4];
      for(var i=0;i<placed.length;i++){var b=placed[i];if(box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1])return;}
      placed.push(box);
      labels+='<text class="sr-dlab'+(c.hot?' sr-dlab-hot':'')+'" x="'+(left?(c.x-c.r-4):(c.x+c.r+4)).toFixed(1)+'" y="'+ly.toFixed(1)+'" text-anchor="'+(left?'end':'start')+'">'+_esc(c.txt)+'</text>';
    });

    // --- quadrant corner labels ---
    var qlab='';
    function corner(q,x,y,anc){
      var qd=QUAD_SRR[q], qx=QUADX_SRR[q];
      return '<text class="sr-qlab '+qd.cls+'" x="'+x+'" y="'+y+'" text-anchor="'+anc+'">'+_esc((_isZh()?qd.zh:qd.en).toUpperCase())+'</text>'
        +'<text class="sr-qsub '+qd.cls+'" x="'+x+'" y="'+(y+16)+'" text-anchor="'+anc+'">'+_esc(_isZh()?qx.zh:qx.en)+'</text>';
    }
    if (zoom) {
      qlab=corner(zoom,plotX+8,plotY+18,'start');
    } else {
      qlab=corner('leading',plotX+plotW-8,plotY+18,'end')
        +corner('improving',plotX+8,plotY+18,'start')
        +corner('weakening',plotX+plotW-8,plotY+plotH-26,'end')
        +corner('lagging',plotX+8,plotY+plotH-26,'start');
    }

    // --- axis rails + end labels ---
    var xLo=axs.xLo||(_isZh()?'弱于大盘':'WEAKER');
    var xHi=axs.xHi||(_isZh()?'强于大盘':'STRONGER');
    var yHi=axs.yHi||(_isZh()?'升温':'HEATING UP');
    var yLo=axs.yLo||(_isZh()?'降温':'COOLING');
    var axDefs='<linearGradient id="sr-xg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="var(--down)" stop-opacity="0.6"></stop><stop offset="0.5" stop-color="var(--muted)" stop-opacity="0.18"></stop><stop offset="1" stop-color="var(--up)" stop-opacity="0.75"></stop></linearGradient>'
      +'<linearGradient id="sr-yg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--up)" stop-opacity="0.75"></stop><stop offset="0.5" stop-color="var(--muted)" stop-opacity="0.18"></stop><stop offset="1" stop-color="var(--down)" stop-opacity="0.6"></stop></linearGradient>';
    var axBars='<rect x="'+plotX+'" y="'+(plotY+plotH+9).toFixed(1)+'" width="'+plotW.toFixed(1)+'" height="5" rx="2.5" fill="url(#sr-xg)"></rect>'
      +'<rect x="'+(plotX-17)+'" y="'+plotY+'" width="5" height="'+plotH.toFixed(1)+'" rx="2.5" fill="url(#sr-yg)"></rect>';
    var axis=axBars
      +'<text class="sr-axc sr-ax-dn" x="'+plotX+'" y="'+(H-11)+'" text-anchor="start">◀ '+_esc(xLo)+'</text>'
      +'<text class="sr-axc sr-ax-up" x="'+(plotX+plotW)+'" y="'+(H-11)+'" text-anchor="end">'+_esc(xHi)+' ▶</text>'
      +'<text class="sr-axc sr-ax-up" x="16" y="'+(plotY+4)+'" text-anchor="end" transform="rotate(-90 16 '+(plotY+4)+')">'+_esc(yHi)+' ▲</text>'
      +'<text class="sr-axc sr-ax-dn" x="16" y="'+(plotY+plotH-4)+'" text-anchor="start" transform="rotate(-90 16 '+(plotY+plotH-4)+')">▼ '+_esc(yLo)+'</text>';

    var empty=zoom&&!visPts.length?'<text class="sr-axc" x="'+(plotX+plotW/2)+'" y="'+(plotY+plotH/2)+'" text-anchor="middle">'+_esc(_isZh()?'该象限暂无成分':'nothing in this quadrant')+'</text>':'';
    var org={leading:'right top',improving:'left top',weakening:'right bottom',lagging:'left bottom'}[zoom]||'center center';

    var aria = spec.ariaLabel || ('Rotation map, '+visPts.length+' items');
    var svg='<svg class="sr-map'+( zoom?' sr-zoomed':'')+'" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet" role="img" aria-label="'+_esc(aria)+'" style="transform-origin:'+org+'">'
      +'<defs>'+defs+axDefs+'</defs>'+bg+lines+qlab+axis+tails+dots+labels+empty+'</svg>';

    container.innerHTML=svg;

    var sv=container.querySelector('svg');
    if (sv) {
      sv.addEventListener('mousemove',function(e){
        var t=e.target.closest('.sr-dot');
        if(!t){if(onHov)onHov(null,e.clientX,e.clientY);return;}
        if(onHov)onHov(t.getAttribute('data-k'),e.clientX,e.clientY);
      });
      sv.addEventListener('mouseleave',function(){if(onHov)onHov(null,0,0);});
      sv.addEventListener('click',function(e){
        var t=e.target.closest('.sr-dot');
        if(t&&onClk){onClk(t.getAttribute('data-k'));return;}
        // Return quadrant info to caller via data-q attribute click
        var z=e.target.closest('.sr-qz');
        if(z&&onClk){onClk('@quadrant:'+z.getAttribute('data-q'));}
      });
    }
  }

  // Export the shared renderer
  if (typeof global !== 'undefined') {
    global.SRR = { render: SRR_render };
  }

})(typeof window !== 'undefined' ? window : this);

/* ────────────────────────────────────────────────────────────────────────────
 * PART 2 — The Rotation Desk
 * ──────────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  // Per-region config (US default). A China/other page sets window.SR_CFG before this
  // script loads to point at its own feed + detail dir + rotation page, so ONE renderer
  // serves every market.
  var CFG = (typeof window !== 'undefined' && window.SR_CFG) || {};
  var JSON_URL = CFG.json || 'marketdata/subsector_rotation.json';
  var DETAIL_DIR = CFG.detailDir || 'rotation/';
  var PAGE_HREF = CFG.pageHref || 'subsector_rotation.html';

  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function isZh(){return document.documentElement.getAttribute('data-lang')==='zh';}
  function L(en,zh){return '<span class="l-en">'+en+'</span><span class="l-zh">'+(zh||en)+'</span>';}
  function fmtPc(v){if(v==null||isNaN(v))return '—';var a=Math.abs(v),d=a>=100?0:(a>=10?1:1);return (v>0?'+':(v<0?'−':''))+a.toFixed(d)+'%';}
  function cssVar(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}

  var QUAD = {
    leading:    {en:'Leading',   zh:'领先', cls:'q-lead'},
    weakening:  {en:'Weakening', zh:'走弱', cls:'q-weak'},
    improving:  {en:'Improving', zh:'改善', cls:'q-impr'},
    lagging:    {en:'Lagging',   zh:'落后', cls:'q-lag'}
  };
  function pcCls(v){return v==null?'':(v>=0?'up':'dn');}

  // _unit: 'subsectors' | 'themes' | 'sectors'
  var _data=null, _unit='subsectors', _sortKey='emerging_score', _sortDir=-1, _zoom=null, _fs=false, _vsMore=false;

  function boot(){
    injectStyle();
    document.addEventListener('keydown',function(e){
      if(e.key!=='Escape')return;
      var card=document.querySelector('.sr-map-card'); if(!card)return;
      if(_fs){ _fs=false; card.classList.remove('sr-fs'); document.body.classList.remove('sr-fs-lock');
        requestAnimationFrame(function(){var w=card.querySelector('.sr-map-wrap'); if(w)drawMap(w);}); return; }
      if(_zoom){ _zoom=null; drawMapCard(card); }
    });
    var full=document.getElementById('rotation-app');
    var strip=document.getElementById('rotation-strip');
    if(!full && !strip) return;
    fetch(JSON_URL,{cache:'no-cache'}).then(function(r){if(!r.ok)throw 0;return r.json();})
      .then(function(d){_data=d; if(full)render(full); if(strip)drawStrip(strip);})
      .catch(function(){ if(full)full.innerHTML='<div class="sr-empty">'+L('Could not load rotation data.','无法加载轮动数据。')+'</div>'; if(strip)strip.style.display='none'; });
  }

  /* ---------- compact strip (embedded on the heatmap page) ---------- */
  function drawStrip(el){
    el.className='sr-scope sr-strip';
    var m={}; _data.subsectors.forEach(function(s){m[s.key]=s;});
    function dual(en,zh){return '<span class="l-en">'+esc(en)+'</span><span class="l-zh">'+esc(zh||en)+'</span>';}
    function chip(s){var v=s.perf&&s.perf['1W'];var q=QUAD[s.quadrant];
      return '<a class="srx-chip" href="'+PAGE_HREF+'"><span class="srx-q '+q.cls+'"></span>'
        +'<b>'+dual(s.name,s.name_zh)+'</b><span class="srx-th">'+dual(s.theme,s.theme_zh)+'</span>'
        +'<span class="srx-pc '+pcCls(v)+'">'+fmtPc(v)+'</span></a>';}
    var em=(_data.highlights.emerging||[]).map(function(k){return m[k];}).filter(Boolean).slice(0,5);
    var fa=(_data.highlights.fading||[]).map(function(k){return m[k];}).filter(Boolean).slice(0,4);
    el.innerHTML='<div class="srx-hd"><span>🌀 '+L('Subsector rotation','子行业轮动')
      +'<i>'+L('Whole market · speed of relative strength','全市场 · 相对强度的变化速度')+'</i></span>'
      +'<a class="srx-more" href="'+PAGE_HREF+'">'+L('full rotation map','完整轮动图')+' →</a></div>'
      +'<div class="srx-cols">'
      +'<div class="srx-col"><span class="srx-lab up">▲ '+L('Emerging','升温')+'</span>'+em.map(chip).join('')+'</div>'
      +'<div class="srx-col"><span class="srx-lab dn">▼ '+L('Fading','退潮')+'</span>'+fa.map(chip).join('')+'</div>'
      +'</div>';
  }

  /* ---------- track record / calibration (does the read actually work?) ---------- */
  function drawTrackRecord(el){
    var tr=_data.track_record;
    if(!tr){el.style.display='none';return;}
    function fpct(v){return v==null?'—':(v*100).toFixed(0)+'%';}
    function fic(v){return v==null?'—':(v>0?'+':'')+(+v).toFixed(3);}
    function ft(v){return v==null?'—':(+v).toFixed(1);}
    // D-7a: verdict display label map — key stays 'validated' (data); display → "Clears the bar"
    var V={accruing:['Accruing','记录累积中','--muted'],measuring:['Still measuring','测量中','--warn'],validated:['Clears the bar','已达标','--up']};
    var vb=V[tr.verdict]||V.accruing;
    var hs=tr.horizons||{};
    var rows=Object.keys(hs).map(function(h){
      var e=hs[h], bs=e.by_stage||{}, em=bs.emerging||{}, fa=bs.fading||{};
      var prov=(tr.proven||{})[h];
      return '<tr><td>'+h+'d</td><td class="num">'+(e.n_matured||0)+'</td>'
        +'<td class="num">'+fpct(em.hit_rate)+'</td><td class="num">'+fpct(fa.hit_rate)+'</td>'
        +'<td class="num">'+fic(e.score_ic)+'</td><td class="num">'+ft(e.score_ic_t_hac)
        +(prov?' <span class="sr-ok">✓</span>':'')+'</td></tr>';
    }).join('');
    // D-10: replace title= with data-tip-en/zh per house law
    var misses=(tr.recent_misses||[]).slice(0,8).map(function(mi){
      return '<span class="sr-miss" data-tip-en="'+_esc(mi.theme_en||mi.theme||'')+'" data-tip-zh="'+_esc(mi.theme_zh||mi.theme||'')+'"><b>'+_esc(mi.name)+'</b> '
        +'<i class="'+(mi.stage==='emerging'?'dn':'up')+'">'+(mi.fwd_rel>0?'+':'')+(mi.fwd_rel*100).toFixed(1)+'%</i></span>';
    }).join('');
    el.innerHTML=''
      +'<div class="sr-tr-hd">📊 '+L('Track record','跟踪记录')
        +'<span class="sr-tr-q" style="color:var('+vb[2]+');border-color:var('+vb[2]+')">'+L(vb[0],vb[1])+'</span>'
        +'<span class="sr-tr-meta">'+(tr.n_days||0)+' '+L('days logged','天')+' · '+(tr.n_snapshots||0)+' '+L('calls logged','次记录')+'</span></div>'
      +'<div class="sr-tr-note">'+L(esc(tr.note||''),esc(tr.note_zh||tr.note||''))+'</div>'
      // D-6: plainify column headers; move jargon behind ? receipt on table caption
      +'<div class="sr-tr-body"><table class="sr-tr-tbl"><caption style="text-align:left;padding:4px 8px;font-size:10px;color:var(--muted);">'
        +'<span class="rcf-help" tabindex="0" role="button" style="cursor:help;"'
        +' data-tip-en="Rank fit = information coefficient (how well the ranking lines up with what happened next). Reliability = HAC t-stat (higher = less likely to be noise; &#10003; = clears the bar for that horizon)."'
        +' data-tip-zh="排序吻合 = 信息系数（排序与后续实际走势的吻合程度）。可靠度 = HAC t 统计量（越高越不像噪声；&#10003; = 该周期已达标）。"'
        +'>?</span></caption><thead><tr>'
        +'<th>'+L('Horizon','周期')+'</th><th class="num">'+L('Matured','已到期')+'</th>'
        +'<th class="num">'+L('Emerging hit','升温命中')+'</th><th class="num">'+L('Fading hit','退潮命中')+'</th>'
        +'<th class="num">'+L('Rank fit','排序吻合')+'</th><th class="num">'+L('Reliability','可靠度')+'</th></tr></thead>'
        +'<tbody>'+rows+'</tbody></table></div>'
      +(misses?'<div class="sr-tr-misses"><span class="sr-tr-mlab">'+L('Recently wrong (logged)','近期误判（已记录）')+'</span>'+misses+'</div>':'')
      // D-7b: plain at-rest sentence; raw disclaimer demoted to ? tip
      +'<div class="sr-tr-disc">'
        +L('A scorecard of this page\'s own calls, checked against what happened next. Until a time-window has enough history, it\'s still measuring — read it as "measuring", not proof.',
           '本页自身判断的记分卡，对照后续实际走势检验。在某一周期积累足够历史前仍为「测量中」——请视为「测量」，而非定论。')
        +' <span class="rcf-help" tabindex="0" role="button" style="cursor:help;"'
        +' data-tip-en="'+_esc(tr.disclaimer||'')+'"'
        +' data-tip-zh="'+_esc(tr.disclaimer_zh||tr.disclaimer||'')+'"'
        +'>?</span>'
        +'</div>';
  }

  // items() returns the active unit's array
  function items(){
    if(_unit==='sectors') return (_data.sectors||[]);
    if(_unit==='themes')  return _data.themes;
    return _data.subsectors;
  }
  function themeOf(it){return isZh()?(it.theme_zh||it.theme):it.theme;}
  function nameOf(it){
    if(_unit==='themes') return themeOf(it);
    return isZh()?(it.name_zh||it.name):it.name;
  }
  function keyOf(it){
    if(_unit==='themes') return it.theme;
    if(_unit==='sectors') return it.key;
    return it.key;
  }
  // per-subsector detail page (themes + sectors have none). Relative to the rotation page.
  function detailHref(k){return DETAIL_DIR+encodeURIComponent(k)+'.html';}
  function hasDetail(){return _unit==='subsectors';}

  function render(root){
    root.className='sr-scope';
    // Build toggle buttons — sectors only when _data.sectors exists
    var hasSectors = _data && Array.isArray(_data.sectors) && _data.sectors.length > 0;
    var sectorBtn = hasSectors
      ? '<button type="button" data-u="sectors" class="'+(_unit==='sectors'?'on':'')+'">'+L('Sector ETFs','行业ETF')+' <b>'+(_data.n_sectors||_data.sectors.length)+'</b></button>'
      : '';
    root.innerHTML=''
      +'<div class="sr-bar">'
        +'<div class="sr-toggle" role="group">'
          +'<button type="button" data-u="subsectors" class="'+(_unit==='subsectors'?'on':'')+'">'+L('Subsectors','子行业')+' <b>'+_data.n_subsectors+'</b></button>'
          +'<button type="button" data-u="themes" class="'+(_unit==='themes'?'on':'')+'">'+L('Themes','主题')+' <b>'+_data.n_themes+'</b></button>'
          +sectorBtn
        +'</div>'
        +'<div class="sr-grow"></div>'
        +'<div class="sr-meta">'+L('Whole market · speed of relative strength','全市场 · 相对强度的变化速度')+'</div>'
      +'</div>'
      +'<div class="sr-map-card"></div>'
      +'<div class="sr-versus-wrap"></div>'
      +'<div class="sr-table-wrap"></div>'
      +'<div class="sr-vb-container"></div>'
      +'<div class="sr-tr-wrap"></div>';

    Array.prototype.forEach.call(root.querySelectorAll('.sr-toggle button'),function(b){
      b.addEventListener('click',function(){_unit=b.getAttribute('data-u'); _sortKey='emerging_score'; _sortDir=-1; _zoom=null; render(root);});
    });
    drawMapCard(root.querySelector('.sr-map-card'));
    drawVersus(root.querySelector('.sr-versus-wrap'));
    drawTable(root.querySelector('.sr-table-wrap'));
    drawVelocityBoard(root.querySelector('.sr-vb-container'));
    drawTrackRecord(root.querySelector('.sr-tr-wrap'));

    document.removeEventListener('themechange',_rerender); document.removeEventListener('langchange',_rerender);
    _rerenderRoot=root;
    document.addEventListener('themechange',_rerender); document.addEventListener('langchange',_rerender);
  }
  var _rerenderRoot=null;
  function _rerender(){ if(_rerenderRoot) render(_rerenderRoot); }

  /* ---------- rotation map (RRG-style scatter with rotation tails) ---------- */
  var QCOL={leading:'--up',weakening:'--warn',improving:'--link',lagging:'--down'};
  // plain-language subtitle for each quadrant (the four corners, in layman terms).
  var QUADX={
    leading:  {en:'strong & rising',    zh:'强且上行'},
    weakening:{en:'strong but fading',  zh:'强但转弱'},
    improving:{en:'turning up',         zh:'触底回升'},
    lagging:  {en:'weak & falling',     zh:'弱且下行'}
  };
  function qFill(q,a){return 'color-mix(in srgb, var('+(QCOL[q]||'--muted')+') '+a+'%, transparent)';}

  // cross-sectional z-score of a {key:value} map (mirrors engine _zscore).
  function _zmap(vals){
    var ks=[],k,o={}; for(k in vals){var v=vals[k]; if(v!=null&&isFinite(v))ks.push(k);}
    if(ks.length<2){for(k in vals)o[k]=0;return o;}
    var m=0,i; for(i=0;i<ks.length;i++)m+=vals[ks[i]]; m/=ks.length;
    var s=0; for(i=0;i<ks.length;i++){var dd=vals[ks[i]]-m;s+=dd*dd;} s=Math.sqrt(s/ks.length);
    for(k in vals){var vv=vals[k];o[k]=(vv!=null&&isFinite(vv)&&s>1e-9)?(vv-m)/s:0;} return o;
  }
  // Reconstruct each item's rotation TRAIL (p0 oldest → p2 now) from its own
  // multi-horizon relative strength.
  function _trails(its){
    var H=['1W','1M','3M','6M','1Y'],z={};
    H.forEach(function(h){var col={};its.forEach(function(d){col[keyOf(d)]=(d.rs&&d.rs[h]!=null)?d.rs[h]:null;});z[h]=_zmap(col);});
    function mn(a,b){if(a==null&&b==null)return 0;if(a==null)return b;if(b==null)return a;return (a+b)/2;}
    var out={};
    its.forEach(function(d){var k=keyOf(d),
      a=z['1W'][k],b=z['1M'][k],c=z['3M'][k],e=z['6M'][k],f=z['1Y'][k];
      var p2=[d.rs_ratio,d.rs_mom],
          p1=[mn(c,e), mn(b,c)-mn(e,f)],
          p0=[mn(e,f), mn(c,e)-(f==null?0:f)];
      out[k]={p0:p0,p1:p1,p2:p2,speed:Math.sqrt(Math.pow(p2[0]-p0[0],2)+Math.pow(p2[1]-p0[1],2))};
    });
    return out;
  }

  // The map card: zoom chips + legend + the plot.
  function drawMapCard(card){
    var zq=_zoom||'all';
    var qorder=['leading','improving','weakening','lagging'];
    function chip(q,en,zh,inner){var on=zq===q?' on':'';
      return '<button class="sr-zc'+on+'" data-q="'+q+'" aria-pressed="'+(zq===q?'true':'false')+'"'+(q!=='all'?' style="--zc:var('+QCOL[q]+')"':'')+'>'+inner+'</button>';}
    var chips=chip('all','','',L('All','全部'))
      +qorder.map(function(q){return chip(q,q,q,'<span class="sr-zc-dot"></span><span class="sr-zc-tx">'+L(QUAD[q].en,QUAD[q].zh)+'<i>'+L(QUADX[q].en,QUADX[q].zh)+'</i></span>');}).join('');
    var hint=_zoom?L('click the background, press Esc, or "All" to zoom out','点击空白处、按 Esc 或"全部"退出放大'):L('tip: click a quadrant to zoom in','提示：点击象限可放大');
    var legend='<div class="sr-legend">'
      +'<span class="sr-lg"><span class="sr-lg-tail"></span>'+L('trail = where it came from','轨迹 = 来路')+'</span>'
      +'<span class="sr-lg"><span class="sr-lg-arw">➜</span>'+L('arrow = where it\'s heading','箭头 = 去向')+'</span>'
      +(_unit==='subsectors'?'<span class="sr-lg"><span class="sr-lg-dot"></span>'+L('bigger dot = more stocks','越大 = 成分股越多')+'</span>':'')
      +'<span class="sr-lg sr-lg-hint">'+hint+'</span></div>';
    card.innerHTML='<div class="sr-map-hd">'
        +'<span class="sr-map-ti">🌀 '+L('Rotation map','轮动图')+'</span>'
        +'<div class="sr-zc-row">'+chips+'</div>'
        +'<button class="sr-expand" aria-label="toggle fullscreen map">⤢</button>'
      +'</div>'
      +legend
      +'<div class="sr-map-wrap"></div>';
    card.classList.toggle('sr-fs',_fs); document.body.classList.toggle('sr-fs-lock',_fs);
    Array.prototype.forEach.call(card.querySelectorAll('.sr-zc'),function(b){
      b.addEventListener('click',function(){var q=b.getAttribute('data-q');_zoom=(q==='all')?null:q;drawMapCard(card);});
    });
    card.querySelector('.sr-expand').addEventListener('click',function(){
      _fs=!_fs; card.classList.toggle('sr-fs',_fs); document.body.classList.toggle('sr-fs-lock',_fs);
      requestAnimationFrame(function(){drawMap(card.querySelector('.sr-map-wrap'));});
    });
    drawMap(card.querySelector('.sr-map-wrap'));
  }

  function drawMap(wrap){
    var card=wrap.closest('.sr-map-card'), fs=card&&card.classList.contains('sr-fs');
    var allIts=items().filter(function(d){return d.rs_ratio!=null&&d.rs_mom!=null;});
    var tl=_trails(allIts);
    var its=_zoom?allIts.filter(function(d){return d.quadrant===_zoom;}):allIts;
    var W=Math.max(320,wrap.clientWidth||820);
    var H=fs?Math.max(360,window.innerHeight-172):Math.max(470,Math.min(W*0.54,720));
    var pad={l:56,r:24,t:30,b:52};
    var plotX=pad.l,plotY=pad.t,plotW=W-pad.l-pad.r,plotH=H-pad.t-pad.b;
    // domain
    var xMin,xMax,yMin,yMax;
    if(_zoom&&its.length){
      var xa=[],ya=[]; its.forEach(function(d){var t=tl[keyOf(d)];[t.p0,t.p1,t.p2].forEach(function(p){xa.push(p[0]);ya.push(p[1]);});});
      xMin=Math.min.apply(null,xa);xMax=Math.max.apply(null,xa);yMin=Math.min.apply(null,ya);yMax=Math.max.apply(null,ya);
      var px=(xMax-xMin||1)*0.16,py=(yMax-yMin||1)*0.16; xMin-=px;xMax+=px;yMin-=py;yMax+=py;
      if(_zoom==='leading'||_zoom==='weakening')xMin=Math.min(xMin,-0.05);else xMax=Math.max(xMax,0.05);
      if(_zoom==='leading'||_zoom==='improving')yMin=Math.min(yMin,-0.05);else yMax=Math.max(yMax,0.05);
    } else {
      var xs=allIts.map(function(d){return d.rs_ratio;}),ys=allIts.map(function(d){return d.rs_mom;});
      var xm=Math.max(0.6,Math.max.apply(null,xs.map(Math.abs)))*1.12, ym=Math.max(0.6,Math.max.apply(null,ys.map(Math.abs)))*1.12;
      xMin=-xm;xMax=xm;yMin=-ym;yMax=ym;
    }
    function X(v){return plotX+(v-xMin)/((xMax-xMin)||1)*plotW;}
    function Y(v){return plotY+(yMax-v)/((yMax-yMin)||1)*plotH;}
    var cx=X(0),cy=Y(0);
    // backgrounds
    var bg;
    if(_zoom){ bg='<rect x="'+plotX+'" y="'+plotY+'" width="'+plotW+'" height="'+plotH+'" fill="'+qFill(_zoom,8)+'"></rect>'; }
    else { bg=''
      +'<rect x="'+cx+'" y="'+plotY+'" width="'+(plotX+plotW-cx)+'" height="'+(cy-plotY)+'" fill="'+qFill('leading',7)+'" class="sr-qz" data-q="leading"></rect>'
      +'<rect x="'+plotX+'" y="'+plotY+'" width="'+(cx-plotX)+'" height="'+(cy-plotY)+'" fill="'+qFill('improving',7)+'" class="sr-qz" data-q="improving"></rect>'
      +'<rect x="'+cx+'" y="'+cy+'" width="'+(plotX+plotW-cx)+'" height="'+(plotY+plotH-cy)+'" fill="'+qFill('weakening',7)+'" class="sr-qz" data-q="weakening"></rect>'
      +'<rect x="'+plotX+'" y="'+cy+'" width="'+(cx-plotX)+'" height="'+(plotY+plotH-cy)+'" fill="'+qFill('lagging',7)+'" class="sr-qz" data-q="lagging"></rect>'; }
    var lines='';
    if(cx>=plotX-0.5&&cx<=plotX+plotW+0.5)lines+='<line x1="'+cx.toFixed(1)+'" y1="'+plotY+'" x2="'+cx.toFixed(1)+'" y2="'+(plotY+plotH)+'" stroke="var(--line)"></line>';
    if(cy>=plotY-0.5&&cy<=plotY+plotH+0.5)lines+='<line x1="'+plotX+'" y1="'+cy.toFixed(1)+'" x2="'+(plotX+plotW)+'" y2="'+cy.toFixed(1)+'" stroke="var(--line)"></line>';
    // which items get a label / a tail
    var lab={};
    if(_zoom){ its.forEach(function(d){lab[keyOf(d)]=1;}); }
    else if(_unit==='themes'){ its.forEach(function(d){lab[keyOf(d)]=1;}); }
    else if(_unit==='sectors'){ its.forEach(function(d){lab[keyOf(d)]=1;}); }  // label all 11
    else {['emerging','fading','leaders'].forEach(function(b){(_data.highlights[b]||[]).slice(0,10).forEach(function(k){lab[k]=1;});});}
    var fast={};
    if(_zoom){ its.slice().sort(function(a,b){return tl[keyOf(b)].speed-tl[keyOf(a)].speed;}).slice(0,3).forEach(function(d,i){fast[keyOf(d)]=i+1;}); }
    var TAILMIN=_zoom?0.30:0.65;
    var tailKeys={};
    (function(){
      var cand=its.filter(function(d){var tt=tl[keyOf(d)];return lab[keyOf(d)]&&tt&&tt.speed>=TAILMIN;})
        .sort(function(a,b){return tl[keyOf(b)].speed-tl[keyOf(a)].speed;});
      cand.slice(0,_zoom?15:12).forEach(function(d){tailKeys[keyOf(d)]=1;});
    })();
    var defs='',tails='',dots='',cands=[],gi=0;
    its.forEach(function(d){
      var k=keyOf(d),x=X(d.rs_ratio),y=Y(d.rs_mom),q=d.quadrant,col='var('+QCOL[q]+')';
      var base;
      if(_unit==='themes'||_unit==='sectors') base=7;
      else base=(4+Math.min(9,(d.n_members||4)*0.55));
      var r=_zoom?base+1.8:base, hot=d.emerging_score>0, t=tl[k];
      if(tailKeys[k]&&t){
        var gid='srg'+(gi++);
        var s0=[X(t.p0[0]),Y(t.p0[1])],s1=[X(t.p1[0]),Y(t.p1[1])],s2=[x,y];
        var ddx=s2[0]-s1[0],ddy=s2[1]-s1[1],dl=Math.sqrt(ddx*ddx+ddy*ddy);
        if(dl<0.5){ddx=s2[0]-s0[0];ddy=s2[1]-s0[1];dl=Math.sqrt(ddx*ddx+ddy*ddy)||1;}
        ddx/=dl;ddy/=dl;
        var tip=[s2[0]-(r+2)*ddx, s2[1]-(r+2)*ddy];
        defs+='<linearGradient id="'+gid+'" gradientUnits="userSpaceOnUse" x1="'+s0[0].toFixed(1)+'" y1="'+s0[1].toFixed(1)+'" x2="'+tip[0].toFixed(1)+'" y2="'+tip[1].toFixed(1)+'">'
          +'<stop offset="0" stop-color="'+col+'" stop-opacity="0.06"></stop><stop offset="0.5" stop-color="'+col+'" stop-opacity="0.38"></stop><stop offset="1" stop-color="'+col+'" stop-opacity="0.95"></stop></linearGradient>';
        tails+='<path d="M'+s0[0].toFixed(1)+' '+s0[1].toFixed(1)+' L'+s1[0].toFixed(1)+' '+s1[1].toFixed(1)+' L'+tip[0].toFixed(1)+' '+tip[1].toFixed(1)+'" stroke="url(#'+gid+')" stroke-width="2.8" fill="none" stroke-linecap="round" stroke-linejoin="round"></path>';
        var ang=Math.atan2(ddy,ddx),al=13,aw=0.46;
        tails+='<path d="M'+tip[0].toFixed(1)+' '+tip[1].toFixed(1)+' L'+(tip[0]-al*Math.cos(ang-aw)).toFixed(1)+' '+(tip[1]-al*Math.sin(ang-aw)).toFixed(1)
          +' L'+(tip[0]-al*Math.cos(ang+aw)).toFixed(1)+' '+(tip[1]-al*Math.sin(ang+aw)).toFixed(1)+' Z" fill="'+col+'" fill-opacity="0.95"></path>';
      }
      if(fast[k])dots+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(r+4.5).toFixed(1)+'" fill="none" stroke="'+col+'" stroke-width="1.8" stroke-opacity=".9"></circle>';
      dots+='<circle class="sr-dot" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+r.toFixed(1)+'" fill="'+qFill(q,hot?84:58)+'" stroke="'+col+'" stroke-opacity=".82" stroke-width="1.3" data-k="'+esc(k)+'"></circle>';
      if(lab[k])cands.push({x:x,y:y,r:r,txt:(fast[k]?('#'+fast[k]+' '):'')+nameOf(d),hot:!!fast[k],rank:fast[k]||99,spd:(t||{}).speed||0});
    });
    var labels='',placed=[];
    cands.slice().sort(function(a,b){return (a.rank-b.rank)||(b.spd-a.spd);}).forEach(function(c){
      var left=c.x>plotX+plotW*0.66, lw=c.txt.length*6.7+5;
      var lx=left?(c.x-c.r-4-lw):(c.x+c.r+4), ly=c.y+3.6;
      var box=[lx,ly-11,lx+lw,ly+4];
      for(var i=0;i<placed.length;i++){var b=placed[i];
        if(box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1])return;}
      placed.push(box);
      labels+='<text class="sr-dlab'+(c.hot?' sr-dlab-hot':'')+'" x="'+(left?(c.x-c.r-4):(c.x+c.r+4)).toFixed(1)+'" y="'+ly.toFixed(1)+'" text-anchor="'+(left?'end':'start')+'">'+esc(c.txt)+'</text>';
    });
    // quadrant corner labels
    var QUAD_L={leading:{en:'Leading',zh:'领先',cls:'q-lead'},weakening:{en:'Weakening',zh:'走弱',cls:'q-weak'},improving:{en:'Improving',zh:'改善',cls:'q-impr'},lagging:{en:'Lagging',zh:'落后',cls:'q-lag'}};
    var QUADX_L={leading:{en:'strong & rising',zh:'强且上行'},weakening:{en:'strong but fading',zh:'强但转弱'},improving:{en:'turning up',zh:'触底回升'},lagging:{en:'weak & falling',zh:'弱且下行'}};
    var qlab='';
    function corner(q,x,y,anc){var qd=QUAD_L[q],qx=QUADX_L[q];
      return '<text class="sr-qlab '+qd.cls+'" x="'+x+'" y="'+y+'" text-anchor="'+anc+'">'+esc((isZh()?qd.zh:qd.en).toUpperCase())+'</text>'
        +'<text class="sr-qsub '+qd.cls+'" x="'+x+'" y="'+(y+16)+'" text-anchor="'+anc+'">'+esc(isZh()?qx.zh:qx.en)+'</text>';}
    if(_zoom){ qlab=corner(_zoom,plotX+8,plotY+18,'start'); }
    else { qlab=corner('leading',plotX+plotW-8,plotY+18,'end')+corner('improving',plotX+8,plotY+18,'start')
        +corner('weakening',plotX+plotW-8,plotY+plotH-26,'end')+corner('lagging',plotX+8,plotY+plotH-26,'start'); }
    var axDefs='<linearGradient id="sr-xg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="var(--down)" stop-opacity="0.6"></stop><stop offset="0.5" stop-color="var(--muted)" stop-opacity="0.18"></stop><stop offset="1" stop-color="var(--up)" stop-opacity="0.75"></stop></linearGradient>'
      +'<linearGradient id="sr-yg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--up)" stop-opacity="0.75"></stop><stop offset="0.5" stop-color="var(--muted)" stop-opacity="0.18"></stop><stop offset="1" stop-color="var(--down)" stop-opacity="0.6"></stop></linearGradient>';
    var axBars='<rect x="'+plotX+'" y="'+(plotY+plotH+9).toFixed(1)+'" width="'+plotW.toFixed(1)+'" height="5" rx="2.5" fill="url(#sr-xg)"></rect>'
      +'<rect x="'+(plotX-17)+'" y="'+plotY+'" width="5" height="'+plotH.toFixed(1)+'" rx="2.5" fill="url(#sr-yg)"></rect>';
    var xLo=isZh()?'弱于大盘':'WEAKER', xHi=isZh()?'强于大盘':'STRONGER';
    var yHi=isZh()?'升温':'HEATING UP', yLo=isZh()?'降温':'COOLING';
    var axis=axBars
      +'<text class="sr-axc sr-ax-dn" x="'+plotX+'" y="'+(H-11)+'" text-anchor="start">◀ '+esc(xLo)+'</text>'
      +'<text class="sr-axc sr-ax-up" x="'+(plotX+plotW)+'" y="'+(H-11)+'" text-anchor="end">'+esc(xHi)+' ▶</text>'
      +'<text class="sr-axc sr-ax-up" x="16" y="'+(plotY+4)+'" text-anchor="end" transform="rotate(-90 16 '+(plotY+4)+')">'+esc(yHi)+' ▲</text>'
      +'<text class="sr-axc sr-ax-dn" x="16" y="'+(plotY+plotH-4)+'" text-anchor="start" transform="rotate(-90 16 '+(plotY+plotH-4)+')">▼ '+esc(yLo)+'</text>';
    var empty=_zoom&&!its.length?'<text class="sr-axc" x="'+(plotX+plotW/2)+'" y="'+(plotY+plotH/2)+'" text-anchor="middle">'+esc(isZh()?'该象限暂无成分':'nothing in this quadrant')+'</text>':'';
    var aria='Rotation map — '+its.length+' '+(_unit==='themes'?'themes':_unit==='sectors'?'sectors':'subsectors')+(_zoom?(' in the '+_zoom+' quadrant'):'')
      +'. Horizontal axis strength vs market, vertical axis heating vs cooling.';
    var org={leading:'right top',improving:'left top',weakening:'right bottom',lagging:'left bottom'}[_zoom]||'center center';
    var svg='<svg class="sr-map'+(_zoom?' sr-zoomed':'')+'" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet" role="img" aria-label="'+esc(aria)+'" style="transform-origin:'+org+'">'
      +'<defs>'+defs+axDefs+'</defs>'+bg+lines+qlab+axis+tails+dots+labels+empty+'</svg>';
    wrap.innerHTML=svg;
    var sv=wrap.querySelector('svg');
    sv.addEventListener('mousemove',function(e){var t=e.target.closest('.sr-dot');if(!t){hideTip();return;}showTip(t.getAttribute('data-k'),e.clientX,e.clientY);});
    sv.addEventListener('mouseleave',hideTip);
    sv.addEventListener('click',function(e){
      var t=e.target.closest('.sr-dot'); if(t){var k=t.getAttribute('data-k'); if(hasDetail())location.href=detailHref(k); else if(!fs)flashRow(k); return;}
      if(!_zoom){var z=e.target.closest('.sr-qz'); if(z&&card){_zoom=z.getAttribute('data-q');drawMapCard(card);}}
      else if(card){_zoom=null;drawMapCard(card);}   // zoomed: click the empty background (anything but a dot) to zoom out
    });
  }

  /* ---------- head-to-head: rotating IN vs rotating OUT ---------- */
  function drawVersus(el){
    function itemByKey(k){var a=items(),i;for(i=0;i<a.length;i++)if(keyOf(a[i])===k)return a[i];return null;}
    var em,fa,MAX=12,N=_vsMore?MAX:6;
    if(_unit==='themes'||_unit==='sectors'){ var ts=items().slice();
      em=ts.filter(function(d){return d.rs_mom>0;}).sort(function(a,b){return b.emerging_score-a.emerging_score;}).slice(0,MAX);
      fa=ts.filter(function(d){return d.rs_ratio>0&&d.rs_mom<0;}).sort(function(a,b){return a.rs_mom-b.rs_mom;}).slice(0,MAX);
    } else {
      em=(_data.highlights.emerging||[]).map(itemByKey).filter(Boolean).slice(0,MAX);
      fa=(_data.highlights.fading||[]).map(itemByKey).filter(Boolean).slice(0,MAX);
    }
    function row(d,i){
      var q=QUAD[d.quadrant], w1=d.perf?d.perf['1W']:null, m1=d.perf?d.perf['1M']:null;
      var key=d.rs_mom, kt=(key==null?'—':(key>0?'+':(key<0?'−':''))+Math.abs(+key).toFixed(1));
      return '<div class="sr-vs-row" data-k="'+esc(keyOf(d))+'">'
        +'<span class="sr-vs-rk">'+(i+1)+'</span>'
        +'<span class="sr-vs-q '+q.cls+'"></span>'
        +'<span class="sr-vs-main">'+(hasDetail()?'<a class="sr-vs-nm" href="'+detailHref(keyOf(d))+'">'+esc(nameOf(d))+'</a>':'<span class="sr-vs-nm">'+esc(nameOf(d))+'</span>')
          +(_unit==='subsectors'?'<span class="sr-vs-th">'+esc(themeOf(d))+'</span>':'')+'</span>'
        +'<b class="'+pcCls(w1)+'">'+fmtPc(w1)+'</b>'
        +'<b class="'+pcCls(m1)+'">'+fmtPc(m1)+'</b>'
        +'<b class="sr-vs-k '+pcCls(key)+'">'+kt+'</b>'
      +'</div>';
    }
    // each side owns its header so it stays glued to its own list — on mobile the
    // columns stack as [in header + list] · VS · [out header + list], not a shared
    // header banner sitting above two orphaned lists.
    function sideHd(side){
      return side==='in'
        ? '<div class="sr-vs-side in"><span class="sr-vs-ttl">▲ '+L('Rotating in','正在轮入')+'</span><span class="sr-vs-sub">'+L('money accelerating in','资金加速流入')+'</span></div>'
        : '<div class="sr-vs-side out"><span class="sr-vs-ttl">'+L('Rotating out','正在轮出')+' ▼</span><span class="sr-vs-sub">'+L('leaders rolling over','龙头走弱')+'</span></div>';
    }
    function col(list,side){
      var head='<div class="sr-vs-chd"><span></span><span></span><span></span>'
        +'<span>1W</span><span>1M</span><span>'+L('trend','趋势')+'</span></div>';
      var body=list.length?list.map(function(d,i){return row(d,i);}).join('')
        :'<div class="sr-vs-empty">'+(side==='in'?L('nothing rotating in right now','暂无轮入'):L('nothing rotating out right now','暂无轮出'))+'</div>';
      return '<div class="sr-vs-col '+side+'">'+sideHd(side)+head+body+'</div>';
    }
    el.innerHTML='<div class="sr-versus">'
      +'<div class="sr-vs-key">'+L('1W · 1M = return · trend = heating (+) or cooling (−), the map\'s vertical axis',
                                    '1周 · 1月 = 涨跌 · 趋势 = 升温(+)/降温(−)，即图中纵轴')+'</div>'
      +'<div class="sr-vs-body">'+col(em.slice(0,N),'in')
        +'<div class="sr-vs-mid"><span class="sr-vs-vs">'+L('vs','对决')+'</span></div>'
        +col(fa.slice(0,N),'out')+'</div>'
      +((em.length>6||fa.length>6)?'<button type="button" class="sr-vs-more">'+(_vsMore?L('See less','收起')+' ↑':L('See more','查看更多')+' ↓')+'</button>':'')
    +'</div>';
    Array.prototype.forEach.call(el.querySelectorAll('.sr-vs-row'),function(c){
      c.addEventListener('mousemove',function(e){showTip(c.getAttribute('data-k'),e.clientX,e.clientY);});
      c.addEventListener('mouseleave',hideTip);
      c.addEventListener('click',function(e){if(e.target.closest('a'))return;var k=c.getAttribute('data-k');if(hasDetail())location.href=detailHref(k);else flashRow(k);});
    });
    var mb=el.querySelector('.sr-vs-more');
    if(mb)mb.addEventListener('click',function(){_vsMore=!_vsMore;drawVersus(el);});
  }

  /* ---------- table ---------- */
  var COLS=[
    {k:'name',en:'Subsector',zh:'子行业',num:false},
    {k:'theme',en:'Theme',zh:'主题',num:false},
    {k:'quadrant',en:'Quadrant',zh:'象限',num:false},
    {k:'1W',en:'1W',zh:'1周',num:true,perf:true},
    {k:'1M',en:'1M',zh:'1月',num:true,perf:true},
    {k:'3M',en:'3M',zh:'3月',num:true,perf:true},
    {k:'accel',en:'Accel',zh:'加速',num:true},
    {k:'rs_ratio',en:'RS',zh:'相对强度',num:true},
    {k:'rs_mom',en:'Mom',zh:'动量',num:true},
    {k:'emerging_score',en:'Heat',zh:'热度',num:true}
  ];
  function cellVal(d,c){ if(c.perf) return d.perf?d.perf[c.k]:null; if(c.k==='name') return nameOf(d); if(c.k==='theme') return themeOf(d); return d[c.k]; }
  function drawTable(el){
    if(_unit==='themes') COLS[0].en='Theme'; else if(_unit==='sectors') COLS[0].en='Sector'; else COLS[0].en='Subsector';
    // For sectors: hide the theme column (it's redundant — all are "Sector ETFs")
    var hideTCol = (_unit==='themes'||_unit==='sectors');
    var its=items().slice().sort(function(a,b){
      var va=sortVal(a),vb=sortVal(b);
      if(va==null)va=-1e9; if(vb==null)vb=-1e9;
      if(typeof va==='string')return _sortDir*va.localeCompare(vb);
      return _sortDir*(va-vb);
    });
    // Dead-end #2: prepend non-sortable # rank column
    var rankHead='<th class="num" style="cursor:default;min-width:28px;">#</th>';
    var head=rankHead+COLS.filter(function(c){return !(hideTCol&&c.k==='theme');}).map(function(c){
      var on=c.k===_sortKey?(' on '+(_sortDir<0?'desc':'asc')):'';
      return '<th class="'+(c.num?'num':'')+on+'" data-k="'+c.k+'">'+L(c.en,c.zh)+'</th>';
    }).join('');
    var rows=its.map(function(d,ri){
      var rankTd='<td class="num" style="color:var(--muted);font-variant-numeric:tabular-nums;">'+(ri+1)+'</td>';
      var tds=rankTd+COLS.filter(function(c){return !(hideTCol&&c.k==='theme');}).map(function(c){
        if(c.k==='quadrant'){var q=QUAD[d.quadrant];return '<td><span class="sr-q '+q.cls+'">'+(isZh()?q.zh:q.en)+'</span></td>';}
        var v=cellVal(d,c);
        if(c.perf)return '<td class="num '+pcCls(v)+'">'+fmtPc(v)+'</td>';
        if(c.num){var s=v==null?'—':(c.k==='emerging_score'||c.k==='rs_ratio'||c.k==='rs_mom'?(v>0?'+':'')+(+v).toFixed(2):(v>0?'+':'')+(+v).toFixed(1));
          return '<td class="num '+(['accel','rs_mom','emerging_score','rs_ratio'].indexOf(c.k)>=0?pcCls(v):'')+'">'+s+'</td>';}
        if(c.k==='name'&&hasDetail())return '<td><a class="sr-t-link" href="'+detailHref(keyOf(d))+'">'+esc(v)+'</a></td>';
        return '<td>'+esc(v)+'</td>';
      }).join('');
      return '<tr data-k="'+esc(keyOf(d))+'">'+tds+'</tr>';
    }).join('');
    el.innerHTML='<table class="sr-table"><thead><tr>'+head+'</tr></thead><tbody>'+rows+'</tbody></table>';
    Array.prototype.forEach.call(el.querySelectorAll('th'),function(th){
      th.addEventListener('click',function(){var k=th.getAttribute('data-k');
        if(!k) return; // non-sortable column (e.g. rank #)
        if(k===_sortKey)_sortDir=-_sortDir; else {_sortKey=k; _sortDir=(k==='name'||k==='theme'||k==='quadrant')?1:-1;}
        drawTable(el);});
    });
    Array.prototype.forEach.call(el.querySelectorAll('tbody tr'),function(tr){
      tr.addEventListener('mousemove',function(e){showTip(tr.getAttribute('data-k'),e.clientX,e.clientY);});
      tr.addEventListener('mouseleave',hideTip);
    });
  }
  function sortVal(d){ var c=COLS.filter(function(x){return x.k===_sortKey;})[0]; if(!c)return d.emerging_score; return cellVal(d,c); }

  /* ---------- velocity board (dead-end #1 wired, collapsed <details>) ---------- */
  function drawVelocityBoard(el){
    // graceful degrade: no velocity_board → hide
    var vb=_data&&_data.velocity_board;
    if(!vb||!Array.isArray(vb.rows)||!vb.rows.length){el.style.display='none';return;}
    el.style.display='';
    var rows=vb.rows;
    function pc2(v){return v==null?'—':((v>0?'+':'')+(v*100).toFixed(1)+'%');}
    function fz(v){return v==null?'—':((v>0?'+':'')+v.toFixed(1)+'σ');}
    var trs=rows.map(function(r){
      var rs=r.rs||{};
      /* Engine emits rs.d5/d10/d20 and accel_sign 'pos'/'neg'/'flat' (R-M2 fix) */
      var accelCls=r.accel_sign==='pos'?'up':(r.accel_sign==='neg'?'dn':'');
      /* flow_5d_mn is already in $millions from engine (do NOT divide by 1e6) */
      var flowCell=r.flow&&r.flow.flow_5d_mn!=null
        ?'$'+(r.flow.flow_5d_mn).toFixed(0)+'M'+(r.flow.flow_asof?' <span style="font-size:9px;color:var(--muted);">('+_esc(r.flow.flow_asof)+')</span>':'')
        :'—';
      return '<tr>'
        +'<td>'+_esc(isZh()?(r.label_zh||r.series):r.label_en||r.series)+'</td>'
        +'<td class="num '+pcCls(rs.d5)+'">'+pc2(rs.d5)+'</td>'
        +'<td class="num '+pcCls(rs.d10)+'">'+pc2(rs.d10)+'</td>'
        +'<td class="num '+pcCls(rs.d20)+'">'+pc2(rs.d20)+'</td>'
        +'<td class="num '+accelCls+'">'+fz(r.accel10)+'</td>'
        +'<td class="num" style="color:var(--muted);">'+flowCell+'</td>'
        +'</tr>';
    }).join('');
    var asof=vb.asof||(_data&&_data.as_of)||'';
    el.innerHTML='<details class="sr-vb-wrap">'
      +'<summary class="sr-vb-sum">'
        +L('Momentum & flow board','动量与资金流速板')
        +' <span style="font-size:10px;color:var(--muted);">'+L('context, not signals','参考，非信号')+'</span>'
      +'</summary>'
      +'<div class="sr-vb-inner">'
        +(asof?'<div style="font-size:10px;color:var(--muted);margin-bottom:6px;">as of '+_esc(asof)+'</div>':'')
        +'<div style="overflow-x:auto;">'
        +'<table class="sr-table" style="font-size:11px;">'
        +'<thead><tr>'
        +'<th>'+L('Series','序列')+'</th>'
        +'<th class="num">5d RS</th>'
        +'<th class="num">10d RS</th>'
        +'<th class="num">20d RS</th>'
        +'<th class="num">'+L('Accel (vs peers)','加速（对比同类）')+'</th>'
        +'<th class="num">'+L('Flow 5d','5日资金')+'</th>'
        +'</tr></thead>'
        +'<tbody>'+trs+'</tbody>'
        +'</table>'
        +'</div>'
        +'<div style="font-size:10px;color:var(--muted);margin-top:6px;">'
          +L('Speed of money, per series — context, not signals.','各序列的资金速度——参考，非信号。')
          +' '+L('Flow and options context: receipts only, not triggers.','资金与期权背景：仅为依据，非触发条件。')
        +'</div>'
      +'</div>'
      +'</details>';
  }

  /* ---------- tooltip ---------- */
  var _tip=null;
  function tipEl(){if(_tip)return _tip;_tip=document.createElement('div');_tip.className='sr-tip';document.body.appendChild(_tip);return _tip;}
  function showTip(k,cx,cy){
    var d=items().filter(function(x){return keyOf(x)===k;})[0]; if(!d){hideTip();return;}
    var q=QUAD[d.quadrant];
    var sp=(_data.timeframes||['1W','1M','3M','6M','1Y']).filter(function(h){return ['1W','1M','3M','6M','1Y','YTD'].indexOf(h)>=0;})
      .map(function(h){var v=d.perf?d.perf[h]:null;return '<div class="sr-tsp"><span>'+h+'</span><b class="'+pcCls(v)+'">'+fmtPc(v)+'</b></div>';}).join('');
    var mem=(d.members||[]).slice(0,8).map(function(m){return '<span class="sr-chip '+pcCls(m['1M'])+'">'+esc(m.t)+' '+fmtPc(m['1M'])+'</span>';}).join('');
    var el=tipEl();
    // Build secondary info line depending on unit
    var secLine;
    if(_unit==='subsectors') secLine='<div class="sr-tip-th">'+esc(themeOf(d))+' · '+d.n_members+' '+L('names','只')+'</div>';
    else if(_unit==='sectors') secLine='<div class="sr-tip-th">'+L('Sector ETF','行业ETF')+'</div>';
    else secLine='<div class="sr-tip-th">'+d.n_subs+' '+L('subsectors','子行业')+'</div>';
    // Dead-end #2: rank shown in tip
    var rankLine=d.rank!=null
      ?'<div class="sr-tip-th" style="font-variant-numeric:tabular-nums;">#'+d.rank+' '+L('of','of')+' '+(d.rank_total||'?')+' · '+L('vs peers','对比同类')+'</div>'
      :'';
    // Dead-end #3: multi-horizon RS row
    var rs=d.rs||{};
    var rsTf=['1W','1M','3M','6M','1Y'];
    var rsRow=rsTf.map(function(h){var v=rs[h];return '<div class="sr-tsp"><span>'+h+'</span><b class="'+pcCls(v)+'">'+(v==null?'—':(v>0?'+':'')+v.toFixed(2))+'</b></div>';}).join('');
    var rsLine=rsRow?'<div style="font-size:9.5px;color:var(--muted);margin:4px 0 1px;">'+L('relative strength','相对强度')+'</div><div class="sr-tsp-row">'+rsRow+'</div>':'';
    // Dead-end #1: z_accel
    var zAccelLine=d.z_accel!=null
      ?'<span style="margin-left:8px;">'+L('accel vs peers','对比同类加速度')+' <b class="'+pcCls(d.z_accel)+'">'+(d.z_accel>0?'+':'')+d.z_accel.toFixed(1)+'σ</b></span>'
      :'';
    el.innerHTML='<div class="sr-tip-hd"><b>'+esc(nameOf(d))+'</b><span class="sr-q '+q.cls+'">'+(isZh()?q.zh:q.en)+'</span></div>'
      +rankLine
      +secLine
      +'<div class="sr-tsp-row">'+sp+'</div>'
      +rsLine
      +'<div class="sr-tip-mt">'+L('accel','加速')+' <b class="'+pcCls(d.accel)+'">'+(d.accel==null?'—':(d.accel>0?'+':'')+d.accel.toFixed(1))+'</b>'
        +zAccelLine
        +' · '+L('RS','相对强度')+' <b>'+(d.rs_ratio>0?'+':'')+d.rs_ratio.toFixed(2)+'</b> · '+L('mom','动量')+' <b class="'+pcCls(d.rs_mom)+'">'+(d.rs_mom>0?'+':'')+d.rs_mom.toFixed(2)+'</b></div>'
      +(mem?'<div class="sr-tip-mem">'+mem+'</div>':'')
      +(hasDetail()?'<div class="sr-tip-open">'+L('click to open →','点击查看详情 →')+'</div>':'');
    el.classList.add('on');
    var w=el.offsetWidth,h=el.offsetHeight,x=cx+14,y=cy+14;
    if(x+w>window.innerWidth-8)x=cx-w-14; if(y+h>window.innerHeight-8)y=cy-h-14;
    el.style.left=Math.max(8,x)+'px'; el.style.top=Math.max(8,y)+'px';
  }
  function hideTip(){if(_tip)_tip.classList.remove('on');}
  function flashRow(k){var tr=document.querySelector('.sr-table tbody tr[data-k="'+(window.CSS&&CSS.escape?CSS.escape(k):k)+'"]');
    if(tr){tr.scrollIntoView({block:'center',behavior:'smooth'});tr.classList.add('flash');setTimeout(function(){tr.classList.remove('flash');},1200);}}

  /* ---------- styles ---------- */
  function injectStyle(){
    if(document.getElementById('sr-style'))return;
    var c=''
    +'.sr-scope{font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;} .sr-scope .up{color:var(--up);} .sr-scope .dn{color:var(--down);}'
    +'.sr-empty{padding:48px;text-align:center;color:var(--muted);}'
    +'.sr-bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px;}'
    +'.sr-toggle{display:inline-flex;gap:2px;background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:3px;}'
    +'.sr-toggle button{font:700 12.5px Inter,sans-serif;color:var(--muted);background:transparent;border:0;padding:7px 14px;border-radius:8px;cursor:pointer;} .sr-toggle button b{font-weight:800;opacity:.7;margin-left:3px;} .sr-toggle button.on{background:var(--link);color:#fff;}'
    +'.sr-grow{flex:1;} .sr-meta{font-size:11.5px;color:var(--muted);}'
    // ---- map card (full-width hero) ----
    +'.sr-map-card,.sr-table-wrap,.sr-versus{background:var(--panel);border:1px solid var(--line);border-radius:16px;}'
    +'.sr-map-card{padding:11px 14px 12px;}'
    +'.sr-map-card.sr-fs{position:fixed;inset:12px;z-index:1400;margin:0;overflow:auto;box-shadow:0 30px 90px rgba(0,0,0,.55);}'
    +'body.sr-fs-lock{overflow:hidden;}'
    +'.sr-map-hd{display:flex;align-items:center;gap:8px 14px;flex-wrap:wrap;margin-bottom:6px;} .sr-map-ti{font-weight:800;font-size:15px;color:var(--text);}'
    +'.sr-zc-row{display:flex;gap:5px;flex-wrap:wrap;} .sr-expand{margin-left:auto;font-size:15px;line-height:1;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:5px 10px;cursor:pointer;color:var(--muted);} .sr-expand:hover{color:var(--text);}'
    +'.sr-zc{display:inline-flex;align-items:center;gap:6px;font:700 12px Inter,sans-serif;color:var(--muted);background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:4px 9px;cursor:pointer;} .sr-zc:hover{color:var(--text);}'
    +'.sr-zc-dot{width:8px;height:8px;border-radius:50%;background:var(--zc,var(--muted));flex:none;} .sr-zc-tx{display:inline-flex;flex-direction:column;line-height:1.12;text-align:left;} .sr-zc-tx i{font-style:normal;font-size:8.5px;font-weight:600;opacity:.7;text-transform:uppercase;letter-spacing:.02em;}'
    +'.sr-zc.on{color:var(--text);border-color:var(--zc,var(--link));box-shadow:inset 0 0 0 1px var(--zc,var(--link));background:color-mix(in srgb,var(--zc,var(--link)) 9%,var(--panel2));}'
    +'.sr-legend{display:flex;flex-wrap:wrap;gap:5px 15px;margin:0 0 6px;font-size:10.5px;color:var(--muted);} .sr-lg{display:inline-flex;align-items:center;gap:5px;} .sr-lg-hint{margin-left:auto;font-style:italic;opacity:.85;}'
    +'.sr-lg-tail{width:22px;height:0;border-top:2.5px solid color-mix(in srgb,var(--text) 42%,transparent);border-radius:2px;} .sr-lg-arw{color:color-mix(in srgb,var(--text) 55%,transparent);font-size:12px;line-height:1;} .sr-lg-dot{width:10px;height:10px;border-radius:50%;background:color-mix(in srgb,var(--text) 28%,transparent);}'
    +'.sr-map-wrap{width:100%;} .sr-map{width:100%;height:auto;display:block;overflow:hidden;animation:sr-mapin .4s cubic-bezier(.2,.7,.25,1);} .sr-map.sr-zoomed{animation:sr-zoomin .5s cubic-bezier(.2,.7,.25,1);cursor:zoom-out;} .sr-map.sr-zoomed .sr-dot{cursor:pointer;} .sr-map .sr-qz{cursor:zoom-in;} .sr-map path{pointer-events:none;}'
    +'@keyframes sr-mapin{from{opacity:0;transform:scale(.985)}to{opacity:1;transform:scale(1)}} @keyframes sr-zoomin{from{opacity:0;transform:scale(1.14)}to{opacity:1;transform:scale(1)}}'
    +'.sr-dot{cursor:pointer;transition:r .12s,fill-opacity .12s;} .sr-dot:hover{stroke-width:2.8;}'
    +'.sr-dlab{font:600 11px Inter,sans-serif;fill:color-mix(in srgb,var(--text) 82%,transparent);pointer-events:none;} .sr-dlab-hot{font-weight:800;font-size:12.5px;fill:var(--text);}'
    +'.sr-qlab{font:800 15px Inter,sans-serif;letter-spacing:.05em;opacity:.5;pointer-events:none;} .sr-qsub{font:700 8.5px Inter,sans-serif;opacity:.62;letter-spacing:.02em;pointer-events:none;}'
    +'.sr-qlab.q-lead,.sr-qsub.q-lead{fill:var(--up);} .sr-qlab.q-weak,.sr-qsub.q-weak{fill:var(--warn);} .sr-qlab.q-impr,.sr-qsub.q-impr{fill:var(--link);} .sr-qlab.q-lag,.sr-qsub.q-lag{fill:var(--down);}'
    +'.sr-axc{font:700 11px Inter,sans-serif;fill:color-mix(in srgb,var(--text) 52%,transparent);letter-spacing:.02em;pointer-events:none;} .sr-ax-up{font:800 12.5px Inter,sans-serif;fill:var(--up);letter-spacing:.06em;} .sr-ax-dn{font:800 12.5px Inter,sans-serif;fill:var(--down);letter-spacing:.06em;}'
    // ---- head-to-head scorecard ----
    +'.sr-versus{margin-top:14px;padding:12px 15px 14px;}'
    +'.sr-vs-key{font-size:10px;color:var(--muted);text-align:center;margin:0 0 10px;line-height:1.4;}'
    +'.sr-vs-side{display:flex;flex-direction:column;min-width:0;padding-bottom:8px;margin-bottom:3px;border-bottom:1px solid var(--line);} .sr-vs-ttl{font-weight:800;font-size:13.5px;white-space:nowrap;} .sr-vs-side.in .sr-vs-ttl{color:var(--up);} .sr-vs-side.out .sr-vs-ttl{color:var(--down);} .sr-vs-sub{font-size:10.5px;color:var(--muted);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;}'
    +'.sr-vs-body{display:grid;grid-template-columns:1fr auto 1fr;gap:0 14px;}'
    +'.sr-vs-mid{position:relative;display:flex;align-items:center;justify-content:center;min-width:34px;} .sr-vs-mid::before{content:"";position:absolute;top:6px;bottom:6px;left:50%;transform:translateX(-50%);width:1px;background:var(--line);}'
    +'.sr-vs-vs{position:relative;z-index:1;font-weight:900;font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:20px;padding:3px 10px;background:var(--panel2);text-transform:uppercase;letter-spacing:.05em;}'
    +'.sr-vs-empty{padding:16px 6px;text-align:center;font-size:11px;color:var(--muted);}'
    +'.sr-vs-more{display:block;margin:12px auto 0;font:700 12px Inter,sans-serif;color:var(--link);background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:7px 18px;cursor:pointer;} .sr-vs-more:hover{border-color:color-mix(in srgb,var(--link) 55%,var(--line));background:color-mix(in srgb,var(--link) 8%,transparent);}'
    +'.sr-vs-col{min-width:0;}'
    +'.sr-vs-chd,.sr-vs-row{display:grid;grid-template-columns:18px 10px minmax(0,1fr) 54px 54px 50px;gap:9px;align-items:center;}'
    +'.sr-vs-chd{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);padding:1px 6px 5px;} .sr-vs-chd>span:nth-child(n+4){text-align:right;}'
    +'.sr-vs-row{padding:6px;border-radius:8px;cursor:pointer;} .sr-vs-row:hover{background:color-mix(in srgb,var(--text) 4%,transparent);}'
    +'.sr-vs-rk{font-size:10px;font-weight:800;color:var(--muted);text-align:center;} .sr-vs-q{width:8px;height:8px;border-radius:50%;flex:none;}'
    +'.sr-vs-q.q-lead{background:var(--up);} .sr-vs-q.q-weak{background:var(--warn);} .sr-vs-q.q-impr{background:var(--link);} .sr-vs-q.q-lag{background:var(--down);}'
    +'.sr-vs-main{min-width:0;display:flex;flex-direction:column;line-height:1.14;} .sr-vs-nm{font-weight:700;font-size:12.5px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block;} a.sr-vs-nm:hover{color:var(--link);text-decoration:underline;} .sr-vs-th{font-size:9.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    +'.sr-t-link{color:var(--text);} .sr-t-link:hover{color:var(--link);text-decoration:underline;}'
    +'.sr-vs-row>b{font-size:11px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;} .sr-vs-k{font-weight:800;}'
    +'@media (max-width:640px){.sr-vs-body{grid-template-columns:1fr;gap:0;} .sr-vs-mid{min-width:0;padding:14px 0;} .sr-vs-mid::before{top:50%;bottom:auto;left:0;right:0;transform:translateY(-50%);width:auto;height:1px;} .sr-vs-chd,.sr-vs-row{grid-template-columns:16px 9px minmax(0,1fr) 48px 48px 44px;gap:7px;}}'
    +'.sr-q{font-size:10px;font-weight:800;padding:1px 7px;border-radius:6px;white-space:nowrap;}'
    +'.sr-q.q-lead{color:var(--up);background:color-mix(in srgb,var(--up) 15%,transparent);} .sr-q.q-weak{color:var(--warn);background:color-mix(in srgb,var(--warn) 15%,transparent);} .sr-q.q-impr{color:var(--link);background:color-mix(in srgb,var(--link) 15%,transparent);} .sr-q.q-lag{color:var(--down);background:color-mix(in srgb,var(--down) 15%,transparent);}'
    +'.sr-table-wrap{margin-top:14px;overflow:auto;max-height:640px;}'
    +'.sr-table{width:100%;border-collapse:collapse;font-size:12px;} .sr-table th{position:sticky;top:0;background:var(--panel);text-align:left;padding:9px 10px;font-weight:700;color:var(--muted);border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;z-index:1;user-select:none;} .sr-table th.num{text-align:right;} .sr-table th.on{color:var(--text);} .sr-table th.on::after{content:" ▾";} .sr-table th.on.asc::after{content:" ▴";}'
    +'.sr-table td{padding:7px 10px;border-bottom:1px solid color-mix(in srgb,var(--line) 60%,transparent);} .sr-table td.num{text-align:right;font-variant-numeric:tabular-nums;} .sr-table tbody tr:hover{background:color-mix(in srgb,var(--text) 4%,transparent);} .sr-table tr.flash{background:color-mix(in srgb,var(--link) 18%,transparent);}'
    +'.sr-tip{position:fixed;z-index:1200;left:0;top:0;width:260px;max-width:calc(100vw - 16px);background:color-mix(in srgb,var(--panel) 97%,transparent);border:1px solid color-mix(in srgb,var(--text) 16%,var(--line));border-radius:12px;padding:11px 12px;box-shadow:0 16px 44px rgba(0,0,0,.5);backdrop-filter:blur(7px);pointer-events:none;opacity:0;transform:translateY(4px);transition:opacity .12s,transform .12s;}'
    +'.sr-tip.on{opacity:1;transform:none;} .sr-tip-hd{display:flex;align-items:center;justify-content:space-between;gap:8px;} .sr-tip-hd b{font-size:13.5px;color:var(--text);} .sr-tip-th{font-size:10.5px;color:var(--muted);margin-top:2px;}'
    +'.sr-tsp-row{display:flex;gap:8px;margin:8px 0 2px;flex-wrap:wrap;} .sr-tsp{display:flex;flex-direction:column;line-height:1.15;} .sr-tsp span{font-size:8.5px;color:var(--muted);} .sr-tsp b{font-size:11px;font-variant-numeric:tabular-nums;}'
    +'.sr-tip-mt{font-size:10.5px;color:var(--muted);margin-top:6px;border-top:1px solid var(--line);padding-top:6px;} .sr-tip-mt b{color:var(--text);font-variant-numeric:tabular-nums;}'
    +'.sr-tip-mem{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px;} .sr-chip{font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:5px;background:var(--panel2);border:1px solid var(--line);font-variant-numeric:tabular-nums;}'
    +'.sr-tip-open{margin-top:7px;font-size:10.5px;font-weight:700;color:var(--link);}'
    +'.sr-tr-wrap{margin-top:14px;padding:12px 14px;background:var(--panel);border:1px solid var(--line);border-radius:14px;}'
    +'.sr-tr-hd{display:flex;align-items:center;gap:10px;font-weight:800;font-size:13px;color:var(--text);flex-wrap:wrap;} .sr-tr-q{font-size:10px;font-weight:800;padding:1px 8px;border-radius:6px;border:1px solid;text-transform:uppercase;letter-spacing:.04em;} .sr-tr-meta{margin-left:auto;font-size:11px;color:var(--muted);font-weight:600;}'
    +'.sr-tr-note{font-size:11.5px;color:var(--muted);margin:6px 0 10px;line-height:1.5;}'
    +'.sr-tr-body{overflow-x:auto;}'
    +'.sr-tr-tbl{width:100%;border-collapse:collapse;font-size:12px;} .sr-tr-tbl th{text-align:left;padding:6px 8px;font-weight:700;color:var(--muted);border-bottom:1px solid var(--line);white-space:nowrap;} .sr-tr-tbl th.num,.sr-tr-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;} .sr-tr-tbl td{padding:6px 8px;border-bottom:1px solid color-mix(in srgb,var(--line) 55%,transparent);} .sr-ok{color:var(--up);font-weight:800;}'
    +'.sr-tr-misses{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:11px;} .sr-tr-mlab{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);} .sr-miss{font-size:11px;padding:2px 7px;border:1px solid var(--line);border-radius:7px;background:var(--panel2);} .sr-miss b{color:var(--text);} .sr-miss i{font-style:normal;font-variant-numeric:tabular-nums;} .sr-miss i.up{color:var(--up);} .sr-miss i.dn{color:var(--down);}'
    +'.sr-tr-disc{font-size:10px;color:var(--muted);margin-top:11px;line-height:1.5;opacity:.85;}'
    +'.sr-strip{margin:14px 0 0;padding:11px 13px;background:var(--panel);border:1px solid var(--line);border-radius:14px;}'
    +'.srx-hd{display:flex;align-items:baseline;justify-content:space-between;gap:10px;font-weight:800;font-size:13px;color:var(--text);margin-bottom:9px;} .srx-hd i{font-style:normal;font-weight:600;font-size:10.5px;color:var(--muted);margin-left:8px;} .srx-more{font-size:11.5px;font-weight:700;color:var(--link);white-space:nowrap;}'
    +'.srx-cols{display:grid;grid-template-columns:1fr 1fr;gap:10px;} @media (max-width:680px){.srx-cols{grid-template-columns:1fr;}}'
    +'.srx-col{display:flex;flex-wrap:wrap;align-items:center;gap:6px;} .srx-lab{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;margin-right:2px;} .srx-lab.up{color:var(--up);} .srx-lab.dn{color:var(--down);}'
    +'.srx-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);} .srx-chip:hover{border-color:color-mix(in srgb,var(--link) 50%,var(--line));} .srx-chip b{font-size:12px;color:var(--text);} .srx-th{font-size:9.5px;color:var(--muted);} .srx-pc{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;}'
    +'.srx-q{width:7px;height:7px;border-radius:50%;flex:none;} .srx-q.q-lead{background:var(--up);} .srx-q.q-weak{background:var(--warn);} .srx-q.q-impr{background:var(--link);} .srx-q.q-lag{background:var(--down);}'
    +'@media (prefers-reduced-motion:reduce){.sr-tip,.sr-dot{transition:none;} .sr-map,.sr-map.sr-zoomed{animation:none;}}'
    // Velocity board
    +'.sr-vb-container{margin-top:14px;}'
    +'.sr-vb-wrap{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;}'
    +'.sr-vb-sum{display:flex;align-items:center;gap:10px;padding:10px 14px;font-weight:700;font-size:13px;cursor:pointer;list-style:none;} .sr-vb-sum::-webkit-details-marker{display:none;} .sr-vb-sum::before{content:"▾";margin-right:4px;font-size:10px;color:var(--muted);} details[open] .sr-vb-sum::before{content:"▴";}'
    +'.sr-vb-inner{padding:0 14px 12px;}'
    // rcf-help utility (also used in .j2 inline, but OK to re-declare here — idempotent)
    +'.rcf-help{display:inline-flex;align-items:center;justify-content:center;font-size:9.5px;font-weight:700;color:var(--muted);border:1px solid var(--line);border-radius:50%;width:16px;height:16px;cursor:help;flex:none;}';
    var st=document.createElement('style'); st.id='sr-style'; st.textContent=c; document.head.appendChild(st);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot); else boot();
})();

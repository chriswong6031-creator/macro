/* subsector_rotation.js — the Subsector Rotation desk.
 *
 * Reads marketdata/subsector_rotation.json (built from Finviz's broad-universe
 * theme→subsector performance) and renders three linked views:
 *   • a Relative-Rotation map (RS-Ratio × RS-Momentum) with the four rotation
 *     quadrants — Leading / Weakening / Improving / Lagging;
 *   • "Emerging now" + "Fading" rails — the accelerating early-entry list and
 *     the leaders rolling over;
 *   • a sortable leadership/velocity table.
 * Toggle Subsectors ⇄ Themes. No framework; colours come from the live theme
 * tokens so a theme/lang switch recolours instantly.
 */
(function () {
  'use strict';
  var JSON_URL = 'marketdata/subsector_rotation.json';

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

  var _data=null, _unit='subsectors', _sortKey='emerging_score', _sortDir=-1;

  function boot(){
    injectStyle();
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
    function chip(s){var v=s.perf&&s.perf['1W'];var q=QUAD[s.quadrant];
      return '<a class="srx-chip" href="subsector_rotation.html"><span class="srx-q '+q.cls+'"></span>'
        +'<b>'+esc(s.name)+'</b><span class="srx-th">'+esc(s.theme)+'</span>'
        +'<span class="srx-pc '+pcCls(v)+'">'+fmtPc(v)+'</span></a>';}
    var em=(_data.highlights.emerging||[]).map(function(k){return m[k];}).filter(Boolean).slice(0,5);
    var fa=(_data.highlights.fading||[]).map(function(k){return m[k];}).filter(Boolean).slice(0,4);
    el.innerHTML='<div class="srx-hd"><span>🌀 '+L('Subsector rotation','子行业轮动')
      +'<i>'+L('Finviz broad-universe · velocity','Finviz 全市场 · 速度')+'</i></span>'
      +'<a class="srx-more" href="subsector_rotation.html">'+L('full rotation map','完整轮动图')+' →</a></div>'
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
    var V={accruing:['Accruing','子样本累积中','--muted'],measuring:['Measuring','测量中','--warn'],validated:['Validated','已验证','--up']};
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
    var misses=(tr.recent_misses||[]).slice(0,8).map(function(mi){
      return '<span class="sr-miss" title="'+esc(mi.theme||'')+'"><b>'+esc(mi.name)+'</b> '
        +'<i class="'+(mi.stage==='emerging'?'dn':'up')+'">'+(mi.fwd_rel>0?'+':'')+(mi.fwd_rel*100).toFixed(1)+'%</i></span>';
    }).join('');
    el.innerHTML=''
      +'<div class="sr-tr-hd">📊 '+L('Track record','跟踪记录')
        +'<span class="sr-tr-q" style="color:var('+vb[2]+');border-color:var('+vb[2]+')">'+L(vb[0],vb[1])+'</span>'
        +'<span class="sr-tr-meta">'+(tr.n_days||0)+' '+L('days logged','天')+' · '+(tr.n_snapshots||0)+' '+L('calls logged','次记录')+'</span></div>'
      +'<div class="sr-tr-note">'+esc(tr.note||'')+'</div>'
      +'<div class="sr-tr-body"><table class="sr-tr-tbl"><thead><tr>'
        +'<th>'+L('Horizon','周期')+'</th><th class="num">'+L('Matured','已到期')+'</th>'
        +'<th class="num">'+L('Emerging hit','升温命中')+'</th><th class="num">'+L('Fading hit','退潮命中')+'</th>'
        +'<th class="num">'+L('Score IC','评分IC')+'</th><th class="num">'+L('HAC t','HAC t')+'</th></tr></thead>'
        +'<tbody>'+rows+'</tbody></table></div>'
      +(misses?'<div class="sr-tr-misses"><span class="sr-tr-mlab">'+L('Recently wrong (logged)','近期误判（已记录）')+'</span>'+misses+'</div>':'')
      +'<div class="sr-tr-disc">'+esc(tr.disclaimer||'')+'</div>';
  }

  function items(){return _unit==='themes'?_data.themes:_data.subsectors;}
  function nameOf(it){return _unit==='themes'?it.theme:it.name;}
  function keyOf(it){return _unit==='themes'?it.theme:it.key;}

  function render(root){
    root.className='sr-scope';
    root.innerHTML=''
      +'<div class="sr-bar">'
        +'<div class="sr-toggle" role="group">'
          +'<button type="button" data-u="subsectors" class="'+(_unit==='subsectors'?'on':'')+'">'+L('Subsectors','子行业')+' <b>'+_data.n_subsectors+'</b></button>'
          +'<button type="button" data-u="themes" class="'+(_unit==='themes'?'on':'')+'">'+L('Themes','主题')+' <b>'+_data.n_themes+'</b></button>'
        +'</div>'
        +'<div class="sr-grow"></div>'
        +'<div class="sr-meta">'+L('Finviz broad-universe · multi-horizon','Finviz 全市场 · 多周期')+'</div>'
      +'</div>'
      +'<div class="sr-grid">'
        +'<div class="sr-map-card"><div class="sr-map-hd">'+L('Rotation map','轮动图')
          +'<span class="sr-axhint">'+L('→ relative strength · ↑ momentum','→ 相对强度 · ↑ 动量')+'</span></div>'
          +'<div class="sr-map-wrap"></div></div>'
        +'<div class="sr-rails"></div>'
      +'</div>'
      +'<div class="sr-tr-wrap"></div>'
      +'<div class="sr-table-wrap"></div>';

    Array.prototype.forEach.call(root.querySelectorAll('.sr-toggle button'),function(b){
      b.addEventListener('click',function(){_unit=b.getAttribute('data-u'); _sortKey='emerging_score'; _sortDir=-1; render(root);});
    });
    drawMap(root.querySelector('.sr-map-wrap'));
    drawRails(root.querySelector('.sr-rails'));
    drawTrackRecord(root.querySelector('.sr-tr-wrap'));
    drawTable(root.querySelector('.sr-table-wrap'));

    document.removeEventListener('themechange',_rerender); document.removeEventListener('langchange',_rerender);
    _rerenderRoot=root;
    document.addEventListener('themechange',_rerender); document.addEventListener('langchange',_rerender);
  }
  var _rerenderRoot=null;
  function _rerender(){ if(_rerenderRoot) render(_rerenderRoot); }

  /* ---------- rotation map (RRG-style scatter) ---------- */
  function qFill(q,a){var map={leading:'--up',weakening:'--warn',improving:'--link',lagging:'--down'};
    return 'color-mix(in srgb, var('+(map[q]||'--muted')+') '+a+'%, transparent)';}
  function drawMap(wrap){
    var its=items().filter(function(d){return d.rs_ratio!=null&&d.rs_mom!=null;});
    var W=wrap.clientWidth||820, H=Math.max(440,Math.min(W*0.62,640));
    var pad={l:46,r:18,t:18,b:34};
    var xs=its.map(function(d){return d.rs_ratio;}), ys=its.map(function(d){return d.rs_mom;});
    var xm=Math.max(0.6,Math.max.apply(null,xs.map(Math.abs))), ym=Math.max(0.6,Math.max.apply(null,ys.map(Math.abs)));
    xm*=1.12; ym*=1.12;
    function X(v){return pad.l+(v+xm)/(2*xm)*(W-pad.l-pad.r);}
    function Y(v){return pad.t+(ym-v)/(2*ym)*(H-pad.t-pad.b);}
    var cx=X(0), cy=Y(0);
    // notable labels: the highlight sets (keep the map readable).
    var lab={}; if(_unit==='subsectors'){['emerging','fading','leaders'].forEach(function(b){(_data.highlights[b]||[]).slice(0,10).forEach(function(k){lab[k]=1;});});}
    var dots='', labels='';
    its.forEach(function(d){
      var x=X(d.rs_ratio), y=Y(d.rs_mom), q=d.quadrant;
      var r=_unit==='themes'?6:(4+Math.min(4,Math.sqrt((d.n_members||4))/2));
      var hot=d.emerging_score>0;
      dots+='<circle class="sr-dot" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+r.toFixed(1)+'" '
        +'fill="'+qFill(q,hot?78:52)+'" stroke="var('+({leading:'--up',weakening:'--warn',improving:'--link',lagging:'--down'}[q])+')" stroke-opacity=".7" '
        +'data-k="'+esc(keyOf(d))+'"></circle>';
      if(_unit==='themes'||lab[keyOf(d)]){
        labels+='<text class="sr-dlab" x="'+(x+r+3).toFixed(1)+'" y="'+(y+3).toFixed(1)+'">'+esc(nameOf(d))+'</text>';
      }
    });
    var qlab=[
      ['leading',W-pad.r-6,pad.t+14,'end'],['improving',pad.l+6,pad.t+14,'start'],
      ['weakening',W-pad.r-6,H-pad.b-6,'end'],['lagging',pad.l+6,H-pad.b-6,'start']
    ].map(function(a){var q=QUAD[a[0]];return '<text class="sr-qlab '+q.cls+'" x="'+a[1]+'" y="'+a[2]+'" text-anchor="'+a[3]+'">'+(isZh()?q.zh:q.en).toUpperCase()+'</text>';}).join('');
    var svg='<svg class="sr-map" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet">'
      +'<rect x="'+cx+'" y="'+pad.t+'" width="'+(W-pad.r-cx)+'" height="'+(cy-pad.t)+'" fill="'+qFill('leading',7)+'"></rect>'
      +'<rect x="'+pad.l+'" y="'+pad.t+'" width="'+(cx-pad.l)+'" height="'+(cy-pad.t)+'" fill="'+qFill('improving',7)+'"></rect>'
      +'<rect x="'+cx+'" y="'+cy+'" width="'+(W-pad.r-cx)+'" height="'+(H-pad.b-cy)+'" fill="'+qFill('weakening',7)+'"></rect>'
      +'<rect x="'+pad.l+'" y="'+cy+'" width="'+(cx-pad.l)+'" height="'+(H-pad.b-cy)+'" fill="'+qFill('lagging',7)+'"></rect>'
      +'<line x1="'+cx+'" y1="'+pad.t+'" x2="'+cx+'" y2="'+(H-pad.b)+'" stroke="var(--line)"></line>'
      +'<line x1="'+pad.l+'" y1="'+cy+'" x2="'+(W-pad.r)+'" y2="'+cy+'" stroke="var(--line)"></line>'
      +qlab+dots+labels+'</svg>';
    wrap.innerHTML=svg;
    var sv=wrap.querySelector('svg');
    sv.addEventListener('mousemove',function(e){var t=e.target.closest('.sr-dot'); if(!t){hideTip();return;} showTip(t.getAttribute('data-k'),e.clientX,e.clientY);});
    sv.addEventListener('mouseleave',hideTip);
    sv.addEventListener('click',function(e){var t=e.target.closest('.sr-dot'); if(t)flashRow(t.getAttribute('data-k'));});
  }

  /* ---------- emerging / fading rails ---------- */
  function lookup(){var m={}; items().forEach(function(d){m[keyOf(d)]=d;}); return m;}
  function railCard(d){
    var q=QUAD[d.quadrant];
    var sp=['1W','1M','3M','6M'].map(function(h){var v=d.perf?d.perf[h]:null;return '<span class="sr-sp"><i>'+h+'</i><b class="'+pcCls(v)+'">'+fmtPc(v)+'</b></span>';}).join('');
    return '<div class="sr-card" data-k="'+esc(keyOf(d))+'">'
      +'<div class="sr-card-hd"><span class="sr-nm">'+esc(nameOf(d))+'</span>'
        +'<span class="sr-q '+q.cls+'">'+(isZh()?q.zh:q.en)+'</span></div>'
      +(_unit==='subsectors'?'<div class="sr-card-th">'+esc(d.theme)+'</div>':'')
      +'<div class="sr-card-sp">'+sp+'</div>'
      +'<div class="sr-card-mt">'+L('accel','加速')+' <b class="'+pcCls(d.accel)+'">'+(d.accel==null?'—':(d.accel>0?'+':'')+d.accel.toFixed(1))+'</b>'
        +' · '+L('mom','动量')+' <b class="'+pcCls(d.rs_mom)+'">'+(d.rs_mom>0?'+':'')+d.rs_mom.toFixed(2)+'</b></div></div>';
  }
  function drawRails(el){
    var m=lookup();
    function pick(keys){return (keys||[]).map(function(k){return m[_unit==='themes'?undefined:k]||itemByKey(k);}).filter(Boolean);}
    function itemByKey(k){return items().filter(function(d){return keyOf(d)===k;})[0];}
    var em, fa;
    if(_unit==='themes'){ var ts=items().slice(); em=ts.filter(function(d){return d.rs_mom>0;}).slice(0,8); fa=ts.filter(function(d){return d.rs_ratio>0&&d.rs_mom<0;}).sort(function(a,b){return a.rs_mom-b.rs_mom;}).slice(0,8); }
    else { em=(_data.highlights.emerging||[]).map(itemByKey).filter(Boolean).slice(0,8); fa=(_data.highlights.fading||[]).map(itemByKey).filter(Boolean).slice(0,8); }
    el.innerHTML=''
      +'<div class="sr-rail"><div class="sr-rail-hd up">▲ '+L('Emerging now','正在升温')
        +'<span class="sr-rail-sub">'+L('accelerating · rotate in','加速中 · 轮入')+'</span></div>'+em.map(railCard).join('')+'</div>'
      +'<div class="sr-rail"><div class="sr-rail-hd dn">▼ '+L('Fading','正在退潮')
        +'<span class="sr-rail-sub">'+L('leaders rolling over · rotate out','龙头走弱 · 轮出')+'</span></div>'+fa.map(railCard).join('')+'</div>';
    Array.prototype.forEach.call(el.querySelectorAll('.sr-card'),function(c){
      c.addEventListener('mousemove',function(e){showTip(c.getAttribute('data-k'),e.clientX,e.clientY);});
      c.addEventListener('mouseleave',hideTip);
      c.addEventListener('click',function(){flashRow(c.getAttribute('data-k'));});
    });
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
  function cellVal(d,c){ if(c.perf) return d.perf?d.perf[c.k]:null; if(c.k==='name') return nameOf(d); return d[c.k]; }
  function drawTable(el){
    if(_unit==='themes') COLS[0].en='Theme';else COLS[0].en='Subsector';
    var its=items().slice().sort(function(a,b){
      var va=sortVal(a),vb=sortVal(b);
      if(va==null)va=-1e9; if(vb==null)vb=-1e9;
      if(typeof va==='string')return _sortDir*va.localeCompare(vb);
      return _sortDir*(va-vb);
    });
    var head=COLS.filter(function(c){return !(_unit==='themes'&&c.k==='theme');}).map(function(c){
      var on=c.k===_sortKey?(' on '+(_sortDir<0?'desc':'asc')):'';
      return '<th class="'+(c.num?'num':'')+on+'" data-k="'+c.k+'">'+L(c.en,c.zh)+'</th>';
    }).join('');
    var rows=its.map(function(d){
      var tds=COLS.filter(function(c){return !(_unit==='themes'&&c.k==='theme');}).map(function(c){
        if(c.k==='quadrant'){var q=QUAD[d.quadrant];return '<td><span class="sr-q '+q.cls+'">'+(isZh()?q.zh:q.en)+'</span></td>';}
        var v=cellVal(d,c);
        if(c.perf)return '<td class="num '+pcCls(v)+'">'+fmtPc(v)+'</td>';
        if(c.num){var s=v==null?'—':(c.k==='emerging_score'||c.k==='rs_ratio'||c.k==='rs_mom'?(v>0?'+':'')+(+v).toFixed(2):(v>0?'+':'')+(+v).toFixed(1));
          return '<td class="num '+(['accel','rs_mom','emerging_score','rs_ratio'].indexOf(c.k)>=0?pcCls(v):'')+'">'+s+'</td>';}
        return '<td>'+esc(v)+'</td>';
      }).join('');
      return '<tr data-k="'+esc(keyOf(d))+'">'+tds+'</tr>';
    }).join('');
    el.innerHTML='<table class="sr-table"><thead><tr>'+head+'</tr></thead><tbody>'+rows+'</tbody></table>';
    Array.prototype.forEach.call(el.querySelectorAll('th'),function(th){
      th.addEventListener('click',function(){var k=th.getAttribute('data-k');
        if(k===_sortKey)_sortDir=-_sortDir; else {_sortKey=k; _sortDir=(k==='name'||k==='theme'||k==='quadrant')?1:-1;}
        drawTable(el);});
    });
    Array.prototype.forEach.call(el.querySelectorAll('tbody tr'),function(tr){
      tr.addEventListener('mousemove',function(e){showTip(tr.getAttribute('data-k'),e.clientX,e.clientY);});
      tr.addEventListener('mouseleave',hideTip);
    });
  }
  function sortVal(d){ var c=COLS.filter(function(x){return x.k===_sortKey;})[0]; if(!c)return d.emerging_score; return cellVal(d,c); }

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
    el.innerHTML='<div class="sr-tip-hd"><b>'+esc(nameOf(d))+'</b><span class="sr-q '+q.cls+'">'+(isZh()?q.zh:q.en)+'</span></div>'
      +(_unit==='subsectors'?'<div class="sr-tip-th">'+esc(d.theme)+' · '+d.n_members+' '+L('names','只')+'</div>':'<div class="sr-tip-th">'+d.n_subs+' '+L('subsectors','子行业')+'</div>')
      +'<div class="sr-tsp-row">'+sp+'</div>'
      +'<div class="sr-tip-mt">'+L('accel','加速')+' <b class="'+pcCls(d.accel)+'">'+(d.accel==null?'—':(d.accel>0?'+':'')+d.accel.toFixed(1))+'</b> · '
        +L('RS','相对强度')+' <b>'+(d.rs_ratio>0?'+':'')+d.rs_ratio.toFixed(2)+'</b> · '+L('mom','动量')+' <b class="'+pcCls(d.rs_mom)+'">'+(d.rs_mom>0?'+':'')+d.rs_mom.toFixed(2)+'</b></div>'
      +(mem?'<div class="sr-tip-mem">'+mem+'</div>':'');
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
    +'.sr-grid{display:grid;grid-template-columns:minmax(0,1.85fr) minmax(260px,1fr);gap:14px;align-items:start;}'
    +'@media (max-width:880px){.sr-grid{grid-template-columns:1fr;}}'
    +'.sr-map-card,.sr-table-wrap,.sr-rail{background:var(--panel);border:1px solid var(--line);border-radius:14px;}'
    +'.sr-map-card{padding:10px 12px 4px;} .sr-map-hd{display:flex;align-items:baseline;gap:10px;font-weight:800;font-size:13px;color:var(--text);} .sr-axhint{font-weight:600;font-size:10.5px;color:var(--muted);margin-left:auto;}'
    +'.sr-map-wrap{width:100%;} .sr-map{width:100%;height:auto;display:block;}'
    +'.sr-dot{cursor:pointer;transition:r .1s,fill-opacity .1s;} .sr-dot:hover{stroke-width:2.5;}'
    +'.sr-dlab{font:600 9.5px Inter,sans-serif;fill:color-mix(in srgb,var(--text) 80%,transparent);pointer-events:none;}'
    +'.sr-qlab{font:800 11px Inter,sans-serif;letter-spacing:.06em;opacity:.55;} .sr-qlab.q-lead{fill:var(--up);} .sr-qlab.q-weak{fill:var(--warn);} .sr-qlab.q-impr{fill:var(--link);} .sr-qlab.q-lag{fill:var(--down);}'
    +'.sr-rails{display:flex;flex-direction:column;gap:12px;}'
    +'.sr-rail{padding:10px 11px;} .sr-rail-hd{font-weight:800;font-size:12.5px;display:flex;align-items:center;gap:8px;margin-bottom:8px;} .sr-rail-hd.up{color:var(--up);} .sr-rail-hd.dn{color:var(--down);} .sr-rail-sub{font-weight:600;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;}'
    +'.sr-card{padding:8px 9px;border:1px solid var(--line);border-radius:10px;margin-bottom:7px;cursor:pointer;transition:border-color .12s,background .12s;} .sr-card:hover{border-color:color-mix(in srgb,var(--link) 50%,var(--line));background:color-mix(in srgb,var(--link) 5%,transparent);}'
    +'.sr-card-hd{display:flex;align-items:center;justify-content:space-between;gap:8px;} .sr-nm{font-weight:800;font-size:12.5px;color:var(--text);} .sr-card-th{font-size:10.5px;color:var(--muted);margin-top:1px;}'
    +'.sr-card-sp{display:flex;gap:9px;margin-top:6px;} .sr-sp{display:flex;flex-direction:column;line-height:1.15;} .sr-sp i{font-style:normal;font-size:8.5px;color:var(--muted);text-transform:uppercase;} .sr-sp b{font-size:11.5px;font-variant-numeric:tabular-nums;}'
    +'.sr-card-mt{font-size:10.5px;color:var(--muted);margin-top:5px;} .sr-card-mt b{font-variant-numeric:tabular-nums;}'
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
    +'.sr-tr-wrap{margin-top:14px;padding:12px 14px;background:var(--panel);border:1px solid var(--line);border-radius:14px;}'
    +'.sr-tr-hd{display:flex;align-items:center;gap:10px;font-weight:800;font-size:13px;color:var(--text);flex-wrap:wrap;} .sr-tr-q{font-size:10px;font-weight:800;padding:1px 8px;border-radius:6px;border:1px solid;text-transform:uppercase;letter-spacing:.04em;} .sr-tr-meta{margin-left:auto;font-size:11px;color:var(--muted);font-weight:600;}'
    +'.sr-tr-note{font-size:11.5px;color:var(--muted);margin:6px 0 10px;line-height:1.5;}'
    +'.sr-tr-tbl{width:100%;border-collapse:collapse;font-size:12px;} .sr-tr-tbl th{text-align:left;padding:6px 8px;font-weight:700;color:var(--muted);border-bottom:1px solid var(--line);white-space:nowrap;} .sr-tr-tbl th.num,.sr-tr-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;} .sr-tr-tbl td{padding:6px 8px;border-bottom:1px solid color-mix(in srgb,var(--line) 55%,transparent);} .sr-ok{color:var(--up);font-weight:800;}'
    +'.sr-tr-misses{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:11px;} .sr-tr-mlab{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);} .sr-miss{font-size:11px;padding:2px 7px;border:1px solid var(--line);border-radius:7px;background:var(--panel2);} .sr-miss b{color:var(--text);} .sr-miss i{font-style:normal;font-variant-numeric:tabular-nums;} .sr-miss i.up{color:var(--up);} .sr-miss i.dn{color:var(--down);}'
    +'.sr-tr-disc{font-size:10px;color:var(--muted);margin-top:11px;line-height:1.5;opacity:.85;}'
    +'.sr-strip{margin:14px 0 0;padding:11px 13px;background:var(--panel);border:1px solid var(--line);border-radius:14px;}'
    +'.srx-hd{display:flex;align-items:baseline;justify-content:space-between;gap:10px;font-weight:800;font-size:13px;color:var(--text);margin-bottom:9px;} .srx-hd i{font-style:normal;font-weight:600;font-size:10.5px;color:var(--muted);margin-left:8px;} .srx-more{font-size:11.5px;font-weight:700;color:var(--link);white-space:nowrap;}'
    +'.srx-cols{display:grid;grid-template-columns:1fr 1fr;gap:10px;} @media (max-width:680px){.srx-cols{grid-template-columns:1fr;}}'
    +'.srx-col{display:flex;flex-wrap:wrap;align-items:center;gap:6px;} .srx-lab{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;margin-right:2px;} .srx-lab.up{color:var(--up);} .srx-lab.dn{color:var(--down);}'
    +'.srx-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);} .srx-chip:hover{border-color:color-mix(in srgb,var(--link) 50%,var(--line));} .srx-chip b{font-size:12px;color:var(--text);} .srx-th{font-size:9.5px;color:var(--muted);} .srx-pc{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;}'
    +'.srx-q{width:7px;height:7px;border-radius:50%;flex:none;} .srx-q.q-lead{background:var(--up);} .srx-q.q-weak{background:var(--warn);} .srx-q.q-impr{background:var(--link);} .srx-q.q-lag{background:var(--down);}'
    +'@media (prefers-reduced-motion:reduce){.sr-tip,.sr-dot{transition:none;}}';
    var st=document.createElement('style'); st.id='sr-style'; st.textContent=c; document.head.appendChild(st);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot); else boot();
})();

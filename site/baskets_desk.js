// Shared Theme Rotation Desk renderer — used by every baskets page (US/CN/HK/CA/Intl).
// Relies on per-page globals: BASKETS, CHART, THEME, THEME_ALERTS + helpers esc/cssv/
// fmtPct/cls/sparkSvg/ratio/sparkTail. Call deskBoot() after those are defined.
const L = (en,zh)=>`<span class="l-en">${en}</span><span class="l-zh">${zh==null?en:zh}</span>`;
// ---- Theme Rotation Desk --------------------------------------------------
const LABEL_COLOR = {
  dominant:      ['rgba(250,204,21,.16)','rgba(250,204,21,.55)','#eab308'],
  emerging:      ['rgba(74,222,128,.15)','rgba(74,222,128,.5)','#22c55e'],
  fading:        ['rgba(251,146,60,.15)','rgba(251,146,60,.5)','#f97316'],
  deteriorating: ['rgba(248,113,113,.15)','rgba(248,113,113,.5)','#ef4444'],
  neutral:       ['var(--panel2)','var(--line)','var(--muted)'],
};
const RECO_COLOR = {
  enter:      ['rgba(34,197,94,.20)','rgba(34,197,94,.65)','#16a34a'],
  accumulate: ['rgba(74,222,128,.14)','rgba(74,222,128,.5)','#22c55e'],
  hold:       ['var(--panel2)','var(--line)','var(--muted)'],
  trim:       ['rgba(251,146,60,.15)','rgba(251,146,60,.55)','#f97316'],
  avoid:      ['rgba(248,113,113,.16)','rgba(248,113,113,.6)','#ef4444'],
};
const badge = (cls,c,en,zh)=>`<span class="${cls}" style="background:${c[0]};border:1px solid ${c[1]};color:${c[2]}">${L(en,zh)}</span>`;
const COMP_COLOR = {trend:'#5aa7ff',breadth:'#4ade80',impulse:'#a78bfa',macro:'#2dd4bf',crowding:'#fb7185'};
const COMP_LBL = {trend:['trend','趋势'],breadth:['breadth','广度'],impulse:['impulse','脉冲'],macro:['macro','宏观'],crowding:['crowd','拥挤']};

function compBar(c,w){
  const parts=['trend','breadth','impulse','macro'].map(k=>({k,v:Math.max(0,(c[k]||0))*w[k]}));
  parts.push({k:'crowding',v:(c.crowding||0)*w.crowding});
  const tot=parts.reduce((a,p)=>a+Math.abs(p.v),0)||1;
  const segs=parts.filter(p=>Math.abs(p.v)>0.001).map(p=>`<i style="width:${(Math.abs(p.v)/tot*100).toFixed(1)}%;background:${COMP_COLOR[p.k]};${p.k==='crowding'?'opacity:.55':''}"></i>`).join('');
  return `<div class="cbar" title="contribution to the score">${segs}</div>`;
}
function compLegend(c){
  return `<div class="clegend">`+['trend','breadth','impulse','macro','crowding'].map(k=>{
    const v=c[k]; const s=(v==null)?'—':((k==='crowding'?'−':(v>=0?'+':''))+Math.abs(v).toFixed(2));
    return `<span><span class="sw" style="background:${COMP_COLOR[k]}"></span>${L(COMP_LBL[k][0],COMP_LBL[k][1])} <b>${s}</b></span>`;
  }).join('')+`</div>`;
}
function themeCard(t){
  const lc=LABEL_COLOR[t.label]||LABEL_COLOR.neutral, rc=RECO_COLOR[t.reco]||RECO_COLOR.hold;
  const r20=t.perf&&t.perf['20d']?t.perf['20d'].rel:null;
  const spk=sparkTail(ratio(CHART.baskets[t.id]||[]),40);
  const b=t.breadth||{}, im=t.impulse||{}, tx=t.textures||{};
  const ba=tx.bull_age||{}, ob=tx.overbought||{}, ce=tx.clean_entry||{}, rr=tx.rollover_risk||{};
  const top=(t.leadership&&t.leadership.top)||[];
  const obc = ob.value>=0.6?'neg':ob.value>=0.35?'warn':'';
  const flags=[];
  if(ce.flag) flags.push(`<span class="tflag up">✦ ${L('clean entry','干净入场')}</span>`);
  if(rr.band==='high'||rr.band==='elevated') flags.push(`<span class="tflag ${rr.band==='high'?'dn':'wn'}">⚠ ${L('roll-over','回落风险')}</span>`);
  const bullPill = ba.in_bull
    ? `🐂 ${ba.approx_months!=null?ba.approx_months+'mo':''} ${L(ba.stage||'','')||esc(ba.stage_zh||'')}`
    : `🐻 ${L('downtrend','下行')}`;
  return `<div class="tcard" id="theme-${t.id}" style="--tc:${lc[2]}">
    <div class="top">
      ${badge('tlabel',lc,t.label_en,t.label_zh)}
      <a class="nm" href="${(window.BASKET_BASE||'basket/')}${t.id}.html" title="open full theme detail">${L(esc(t.name),esc(t.name_zh))}</a>
      <span class="sc">${t.score}<small>/100</small></span>
    </div>
    <div class="subrow">
      <span>#${t.rank}</span>
      ${badge('treco',rc,t.reco_en,t.reco_zh)}
      <span class="${cls(r20)}">${fmtPct(r20)} 20d</span>
      <span class="spark">${sparkSvg(spk,{w:84,h:24,color:lc[2]})}</span>
    </div>
    ${compBar(t.components,(THEME&&THEME.weights)||{trend:.34,breadth:.22,impulse:.10,macro:.20,crowding:.14})}
    <div class="txrow">
      <span class="tpill" title="bull-market age">${bullPill}</span>
      <span class="tpill ${obc}" title="overbought / extension">${L('OB','超买')} ${esc(ob.band||'—')}</span>
      ${flags.join('')}
    </div>
    <div class="treason">${esc((t.reasons||[]).join(' · '))}</div>
    <div class="tstats">
      <span class="tpill">${L('above 50d','站上50日')} <b>${b.pct50==null?'—':Math.round(b.pct50*100)+'%'}</b></span>
      <span class="tpill">${L('+3% / −3%','+3% / −3%')} <b class="pos">${im.up3||0}</b>/<b class="neg">${im.down3||0}</b></span>
      <span class="tpill">${L('adv/dec','涨/跌')} <b class="pos">${t.adv||0}</b>/<b class="neg">${t.dec||0}</b></span>
    </div>
    <details><summary>${L('why &amp; components','理由与分项')}</summary>
      <div class="why">${L(esc(t.reco_why_en),esc(t.reco_why_zh))}</div>
      ${compLegend(t.components)}
      ${top.length?`<div class="why">${L('leaders','领涨')}: ${top.map(x=>esc(x.ticker)).join(', ')}${t.leadership.breadth==='narrow'?' ⚠':''}</div>`:''}
    </details>
    <a class="detail-link" href="${(window.BASKET_BASE||'basket/')}${t.id}.html">${L('Full detail · holdings buy/avoid →','完整详情 · 成分可买/回避 →')}</a>
  </div>`;
}
function renderThemeDesk(){
  const sec=document.getElementById('theme-desk-section');
  if(!THEME||!(THEME.themes||[]).length){ if(sec) sec.style.display='none'; return; }
  document.getElementById('theme-desk').innerHTML=(THEME.themes||[]).map(themeCard).join('');
  const d=THEME.disclaimer||{}; document.getElementById('theme-disclaimer').innerHTML=L(esc(d.en||''),esc(d.zh||''));
}
function renderMacroCtx(){
  if(!THEME) return;
  const m=THEME.macro_context||{};
  const item=(en,zh,v)=>`<span><span class="mc-k">${L(en,zh)}:</span> <b>${esc(v==null?'—':v)}</b></span>`;
  document.getElementById('macro-ctx').innerHTML=
    `<span>${L('Macro backdrop','宏观背景')}: <b>${esc(m.quad_name||m.quad||'—')}</b></span>`
    +item('cycle','周期',m.cycle)+item('Fed','美联储',m.fed_dir)
    +item('NFCI','NFCI',(m.nfci_state||'—')+(m.nfci_trend?(' / '+m.nfci_trend):''))
    +item('USD','美元',m.dollar_regime)+item('bonds','债券',m.bond_cycle);
}
function renderRotation(){
  const sec=document.getElementById('rotation-section');
  if(!THEME||!THEME.rotation_5d){ if(sec) sec.style.display='none'; return; }
  const rot=THEME.rotation_5d;
  const row=t=>{const ar=t.rank_5d>0?'▲':t.rank_5d<0?'▼':'·'; const ac=t.rank_5d>0?'pos':t.rank_5d<0?'neg':'muted';
    return `<div class="rotrow"><span class="rn"><a href="${(window.BASKET_BASE||'basket/')}${encodeURIComponent(t.id)}.html">${L(esc(t.name),esc(t.name_zh))}</a></span>
      <span class="rv ${cls(t.delta_5d)}">${fmtPct(t.delta_5d)}</span>
      <span class="rk ${ac}" title="20d RS rank change">${ar}${t.rank_5d?Math.abs(t.rank_5d):''}</span></div>`;};
  const col=(en,zh,emo,arr)=>`<div class="rotcol"><h4>${emo} ${L(en,zh)}</h4>${arr.length?arr.map(row).join(''):`<div class="muted sm" style="padding:6px 0">${L('none','无')}</div>`}</div>`;
  document.getElementById('rotation').innerHTML=col('Weekly climbers','本周上升','▲',rot.climbers||[])+col('Weekly fallers','本周下降','▽',rot.fallers||[]);
}
function renderActNow(){
  const sec=document.getElementById('actnow-section'); if(!THEME||!THEME.act_now){ if(sec) sec.style.display='none'; return; }
  const a=THEME.act_now;
  const ACT={enter:['ENTER','建仓','#16a34a'],accumulate:['ACCUMULATE','加仓','#22c55e'],trim:['TRIM','减仓','#f97316'],avoid:['AVOID','回避','#ef4444']};
  const row=x=>{const ac=ACT[x.action]||['','',cssv('--muted')];
    return `<a class="anrow" href="${(window.BASKET_BASE||'basket/')}${x.id}.html">
      <span class="anverb" style="color:${ac[2]};border-color:${ac[2]}">${L(ac[0],ac[1])}</span>
      <span class="rn">${L(esc(x.name),esc(x.name_zh))}</span>
      <span class="anwhy muted sm">${esc((x.reasons||[]).join(' · '))}</span>
      <span class="ansc">${x.score}</span></a>`;};
  const buys=a.buy||[], red=a.reduce||[];
  document.getElementById('actnow').innerHTML=`<div class="anwrap">
    <div class="ancol"><h4 class="anh buy">✅ ${L('Buy / add now','现在买入 / 加仓')} <span class="muted sm">(${buys.length})</span></h4>${buys.length?buys.map(row).join(''):`<div class="muted sm" style="padding:10px 2px">${L('Nothing has a clean entry right now — patience.','当前无干净入场点 — 耐心等待。')}</div>`}</div>
    <div class="ancol"><h4 class="anh red">🔻 ${L('Reduce / avoid','减仓 / 回避')} <span class="muted sm">(${red.length})</span></h4>${red.length?red.map(row).join(''):`<div class="muted sm" style="padding:10px 2px">${L('none','无')}</div>`}</div>
  </div>`;
}
function renderConcentration(){
  const sec=document.getElementById('concentration-section'); if(!THEME){ if(sec) sec.style.display='none'; return; }
  const mc=THEME.market_concentration||{};
  const vmap={narrow:['var(--down)','narrow','狭窄'],broad:['var(--up)','broad','广泛'],mixed:['var(--warn)','mixed','中性']};
  const vv=vmap[mc.verdict]||vmap.mixed;
  const adc=(en,zh,v)=>`<div class="adc"><div class="k">${L(en,zh)}</div><div class="v ${v==null?'muted':(v<1?'neg':'pos')}">${v==null?'—':(+v).toFixed(2)}</div></div>`;
  const narrow=`<div class="panel pad" style="border-left:3px solid ${vv[0]}">
    <div style="display:flex;flex-wrap:wrap;gap:18px;align-items:center">
      <div><span class="muted sm">${L('S&P breadth','标普广度')}</span><div style="font-size:18px;font-weight:740;color:${vv[0]}">${L(vv[1],vv[2])}</div></div>
      <div class="adgrid">${adc('A/D today','今日',mc.ad_ratio)}${adc('3-day','3日',mc.ad_3d)}${adc('weekly','周',mc.ad_w)}${adc('monthly','月',mc.ad_m)}</div>
      <div class="muted sm">${L('above 50d','站上50日')} <b>${mc.pct_above_50!=null?mc.pct_above_50+'%':'—'}</b> · ${L('above 200d','站上200日')} <b>${mc.pct_above_200!=null?mc.pct_above_200+'%':'—'}</b> · ${L('new hi/lo','新高/低')} <b class="pos">${mc.nh}</b>/<b class="neg">${mc.nl}</b></div>
    </div></div>`;
  const lead=(arr,en,zh,sign)=>`<div class="rotcol"><h4>${sign} ${L(en,zh)}</h4>${(arr||[]).map(x=>`<div class="rotrow"><span class="rn"><a href="${(window.BASKET_BASE||'basket/')}${x.id}.html">${L(esc(x.name),esc(x.name_zh))}</a></span><span class="rv ${x.net_ad>=0?'pos':'neg'}">${x.net_ad>=0?'+':''}${x.net_ad}</span><span class="rk muted">${x.adv}/${x.dec}</span></div>`).join('')}</div>`;
  const tlist=(arr,en,zh,kind)=>`<div class="rotcol"><h4>${kind==='entry'?'✦':'⚠'} ${L(en,zh)}</h4>${(arr||[]).length?arr.map(x=>`<div class="rotrow"><span class="rn"><a href="${(window.BASKET_BASE||'basket/')}${x.id}.html">${L(esc(x.name),esc(x.name_zh))}</a></span><span class="rv">${kind==='entry'?Math.round(x.quality*100)+'%':esc(x.band)}</span></div>`).join(''):`<div class="muted sm" style="padding:6px 0">${L('none right now','暂无')}</div>`}</div>`;
  document.getElementById('concentration').innerHTML = narrow
    + `<div class="rotwrap" style="margin-top:12px">${lead(THEME.breadth_leaders,'Owns the advance','主导上涨','▲')}${lead(THEME.breadth_laggards,'In the decline','处于下跌','▽')}</div>`
    + `<div class="rotwrap" style="margin-top:12px">${tlist(THEME.entries,'Clean entries (emerging)','干净入场（新兴）','entry')}${tlist(THEME.rollover,'Roll-over watch','回落观察','roll')}</div>`;
}
function renderScorecards(){
  const sec=document.getElementById('impulse-section');
  if(!THEME||!THEME.impulse_scorecard){ if(sec) sec.style.display='none'; return; }
  const s=THEME.impulse_scorecard, rc=THEME.recommendations||{};
  const duo=(a,b)=>{const t=(a+b)||1;return `<div class="duo"><i style="width:${a/t*100}%;background:var(--up)"></i><i style="width:${b/t*100}%;background:var(--down)"></i></div>`;};
  const cnt=k=>(rc[k]||[]).length;
  const c1=`<div class="scard"><div class="sk">${L('±3% daily impulse','±3% 当日脉冲')}</div>
    <div class="bigrow"><div><div class="big up">${s.up3}</div><div class="sublbl">${L('up ≥3%','涨≥3%')}</div></div>
    <div><div class="big dn">${s.down3}</div><div class="sublbl">${L('down ≥3%','跌≥3%')}</div></div></div>
    ${duo(s.up3,s.down3)}<div class="net">${L('net','净')} <b class="${cls(s.net)}">${s.net>=0?'+':''}${s.net}</b> ${L('of '+s.n+' names',' ／共 '+s.n+' 只')}</div></div>`;
  const c2=`<div class="scard"><div class="sk">${L('52-week extremes','52周极值')}</div>
    <div class="bigrow"><div><div class="big up">${s.nh}</div><div class="sublbl">${L('new highs','新高')}</div></div>
    <div><div class="big dn">${s.nl}</div><div class="sublbl">${L('new lows','新低')}</div></div></div>
    ${duo(s.nh,s.nl)}<div class="net">${L('net','净')} <b class="${cls(s.net_hl)}">${s.net_hl>=0?'+':''}${s.net_hl}</b></div></div>`;
  const c3=`<div class="scard"><div class="sk">${L('recommendation tally','建议统计')}</div>
    <div class="bigrow" style="gap:12px;flex-wrap:wrap">
      <div><div class="big up">${cnt('enter')+cnt('accumulate')}</div><div class="sublbl">${L('enter / add','建仓／加仓')}</div></div>
      <div><div class="big" style="color:var(--muted)">${cnt('hold')}</div><div class="sublbl">${L('hold','持有')}</div></div>
      <div><div class="big dn">${cnt('trim')+cnt('avoid')}</div><div class="sublbl">${L('trim / avoid','减仓／回避')}</div></div>
    </div></div>`;
  document.getElementById('scorecards').innerHTML=c1+c2+c3;
}
function openTheme(id){const d=document.getElementById('theme-'+id);if(!d)return;const det=d.querySelector('details');if(det)det.open=true;
  d.scrollIntoView({behavior:'smooth',block:'center'});d.style.transition='box-shadow .3s';d.style.boxShadow='0 0 0 2px var(--link)';setTimeout(()=>{d.style.boxShadow='';},1200);}

function renderBell(){
  const wrap=document.getElementById('theme-bell'); if(!wrap) return;
  const btn=document.getElementById('bell-btn'), menu=document.getElementById('bell-menu'), badgeEl=document.getElementById('bell-badge');
  const evs=(THEME_ALERTS||[]).slice(0,12);
  const SEEN='fw-theme-bell-seen', lastSeen=localStorage.getItem(SEEN)||'';
  const unread=evs.filter(e=>e.ts>lastSeen).length;
  if(unread>0){ badgeEl.textContent=unread>9?'9+':String(unread); badgeEl.classList.add('on'); }
  const ago=ts=>{const dd=Math.floor((Date.now()-new Date(ts).getTime())/86400000);return dd<=0?L('today','今日'):dd===1?L('1d ago','1天前'):L(dd+'d ago',dd+'天前');};
  menu.innerHTML=`<div class="bhd">🧺 ${L('Theme rotation alerts','主题轮动警报')}<span style="flex:1"></span><a href="alerts.html" class="muted" style="font-size:11px;text-decoration:underline">${L('Alert Center →','警报中心 →')}</a></div>`+
    (evs.length?evs.map(e=>`<div class="bell-item" data-id="${esc(e.asset)}">
      <div class="bi-hl">${L(esc(e.headline),esc(e.headline_zh||e.headline))}</div>
      <div class="bi-dt">${ago(e.ts)}</div></div>`).join(''):`<div class="bell-empty">${L('No recent theme changes — recommendations are steady.','近期无主题变化 — 建议保持稳定。')}</div>`);
  btn.onclick=ev=>{ev.stopPropagation();const open=menu.classList.toggle('open');
    if(open){badgeEl.classList.remove('on'); if(evs.length) localStorage.setItem(SEEN,evs[0].ts);}};
  menu.querySelectorAll('.bell-item').forEach(it=>it.onclick=()=>{menu.classList.remove('open');openTheme(it.dataset.id);});
  document.addEventListener('click',e=>{ if(!wrap.contains(e.target)) menu.classList.remove('open'); });
}

function deskBoot(){ try{ renderActNow(); }catch(e){} try{ renderMacroCtx(); }catch(e){}
  try{ renderThemeDesk(); }catch(e){} try{ renderConcentration(); }catch(e){}
  try{ renderRotation(); }catch(e){} try{ renderScorecards(); }catch(e){} try{ renderBell(); }catch(e){} }

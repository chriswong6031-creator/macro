// Shared Theme Rotation Desk renderer — used by every baskets page (US/CN/HK/CA/Intl).
// Relies on per-page globals: BASKETS, CHART, THEME, THEME_ALERTS + helpers esc/cssv/
// fmtPct/cls/sparkSvg/ratio/sparkTail. Call deskBoot() after those are defined.
const L = (en,zh)=>`<span class="l-en">${en}</span><span class="l-zh">${zh==null?en:zh}</span>`;
// ---- Velocity / Heat helpers (W4 rotation-scorecard upgrade) ------------------
// All labels are DESCRIPTIVE — they characterise current rank/score trajectory; no
// forward-return forecast is implied (house rule: honest framing).
const HEAT_PILL = {
  heating: ['heat-pill heating', '▲', 'heating', '加热'],
  hot:     ['heat-pill hot',     '★', 'hot',     '强势'],
  cooling: ['heat-pill cooling', '▽', 'cooling', '降温'],
  broken:  ['heat-pill broken',  '✕', 'broken',  '破位'],
};
// heatDot(t) — minimal inline dot (no text) for use in compact rotrow/leadrow contexts.
function heatDot(t){
  const h = t && t.pulse_heat;
  if(!h || h==='idle') return '';
  const p = HEAT_PILL[h];
  if(!p) return '';
  return `<span class="${p[0]} heat-dot" data-tip-en="${esc(p[2])} — descriptive" data-tip-zh="${esc(p[3])} — 描述性"></span>`;
}
// rankTrajectory(t) — "▲4 · 20d ▲7" context string for rotation rows; returns '' when
// rank delta data is absent (history accruing).
function rankTrajectory(t){
  const r5 = t && t.pulse_rank_delta_5d;
  const r20 = t && t.pulse_rank_delta_20d;
  if(r5 == null) return '';
  const fmt5 = (r5>0?'▲':'▼')+Math.abs(r5);
  const fmt20 = r20!=null ? ' · 20d '+(r20>0?'▲':'▼')+Math.abs(r20) : '';
  return fmt5 + fmt20;
}
// actNowPulseBar(themes) — merged pulse strip: [sizing pill]? [🔥 Heating: A,B,C]? [❄ Cooling: D,E]?
// Sizing pill logic lives here (renderRegimeSizing returns the pill HTML string).
// Returns '' when nothing to show (no sizing, no heating, no cooling).
function actNowPulseBar(themes){
  const sizePill = renderRegimeSizing();
  const byHeat = h => (themes||[]).filter(t=>t.pulse_heat===h).sort((a,b)=>(a.rank||999)-(b.rank||999)).slice(0,3);
  const heating = byHeat('heating'), cooling = byHeat('cooling');
  if(!sizePill && !heating.length && !cooling.length) return '';
  const BASE = window.BASKET_BASE||'basket/';
  const links = arr => arr.map(t=>`<a href="${BASE}${encodeURIComponent(t.id)}.html">${L(esc(t.name),esc(t.name_zh))}</a>`).join(', ');
  const parts = [];
  if(sizePill) parts.push(sizePill);
  if(heating.length) parts.push(`<span class="pulse-grp">🔥 ${L('Heating','加热')}: ${links(heating)}</span>`);
  if(cooling.length) parts.push(`<span class="pulse-grp">❄ ${L('Cooling','降温')}: ${links(cooling)}</span>`);
  return `<div class="pulse-bar">${parts.join('')}</div>`;
}
// ---- W8-R5 CN basket turn-state chips (display-tier, expected-NULL; FT-R9) ----
// Tape-state chips are PURELY DESCRIPTIVE — no forward verbs, no entry signal.
// FT-R1: fast-vs-slow disagreement is DISPLAYED, never auto-resolved or merged.

const TAPE_STATE_LABEL = {
  TURNING:   ['TURNING',  '拐头中'],
  CONFIRMED: ['CONFIRMED','已确认'],
  WASHED_OUT:['WASHED OUT','深度洗盘'],
  BASING:    ['BASING',   '筑底中'],
  FALLING:   ['FALLING',  '仍在下跌'],
};
const TAPE_TOOLTIP_EN = 'CN basket turn-watch (W8-R5): washout-lifecycle state — descriptive, not an entry signal. Expected-NULL forward meter (FT-R9).';
const TAPE_TOOLTIP_ZH = 'CN篮子拐点观察（W8-R5）：洗盘生命周期状态 — 描述性，非入场信号。预期零值前瞻计量器（FT-R9）。';
// tapeChip(t): returns a tape-state chip HTML string for the basket row t.
// Returns '' when state is NONE/null/undefined.
function tapeChip(t){
  const ts = t && t.turn_state;
  if(!ts || ts==='NONE') return '';
  const lbl = TAPE_STATE_LABEL[ts];
  if(!lbl) return '';
  return `<span class="tape-chip ${ts}" data-tip-en="${esc(TAPE_TOOLTIP_EN)}" data-tip-zh="${esc(TAPE_TOOLTIP_ZH)}">${L(lbl[0],lbl[1])}</span>`;
}
// tapeChipOnRow(t): returns a tape-chip for use in act-now rows (same logic).
function tapeChipOnRow(t){ return tapeChip(t); }

// dualChip(t): returns the dual-read chip when reco is avoid/trim AND tape is
// TURNING or CONFIRMED (FT-R1: disagreement displayed, NEVER merged/auto-resolved).
// "AVOID (trend) · TURNING (tape)" — side-by-side, never fused.
const DISAGREE_TAPE_STATES = new Set(['TURNING','CONFIRMED']);
const DISAGREE_RECOS = new Set(['trim','avoid']);
function dualChip(t){
  if(!t || !DISAGREE_RECOS.has(t.reco) || !DISAGREE_TAPE_STATES.has(t.turn_state)) return '';
  const recoLbl = t.reco==='avoid'?['AVOID','回避']:['TRIM','减仓'];
  const tapeLbl = TAPE_STATE_LABEL[t.turn_state]||[t.turn_state,t.turn_state];
  const tipEn = `FT-R1: trend reco (${t.reco}) disagrees with tape state (${t.turn_state}). Displayed side-by-side — NOT merged, NOT re-ranked. Washout turning = NOT an entry signal; trend is the primary read.`;
  const tipZh = `FT-R1：趋势建议（${t.reco}）与带状态（${t.turn_state}）相悖。并排显示 — 不合并，不重排。洗盘拐头 ≠ 入场信号；趋势为主。`;
  return `<span class="dual-chip" data-tip-en="${esc(tipEn)}" data-tip-zh="${esc(tipZh)}"><span class="dc-trend">${L(recoLbl[0],recoLbl[1])}</span><span class="dc-sep">·</span><span class="dc-tape">${L(tapeLbl[0],tapeLbl[1])}</span></span>`;
}

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
// A1 — display-only verb demotion: never render a green ACCUMULATE/ENTER chip when the
// theme's own clean_entry texture is false (the act_now board already refuses these).
// The payload reco is NOT mutated (alerts + downstream readers keep continuity) — only
// what the chip says changes. Amber, descriptive, no forward verb.
const RECO_NOENTRY = ['rgba(245,158,11,.16)','rgba(245,158,11,.55)','#d97706'];
const recoNoEntry = t => (t.reco==='accumulate'||t.reco==='enter') && !(((t.textures||{}).clean_entry)||{}).flag;
const recoChip = t => recoNoEntry(t)
  ? `<span class="treco" style="background:${RECO_NOENTRY[0]};border:1px solid ${RECO_NOENTRY[1]};color:${RECO_NOENTRY[2]}" title="In favour, but no member has a clean entry — do not chase; wait for a setup.">${L('IN FAVOUR — NO ENTRY','看好但无干净入场')}</span>`
  : badge('treco',RECO_COLOR[t.reco]||RECO_COLOR.hold,t.reco_en,t.reco_zh);
const RECO_NOENTRY_WHY = () => L('In favour, but no member has a clean entry — do not chase; wait for a setup.','看好，但无成分股具备干净入场点 — 勿追，等待入场时机。');
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
// ---- Leadership Health (display-only, deterministic — a shape/fragility read, not a forecast)
function _basketOf(id){ try{ return (((typeof BASKETS!=='undefined'&&BASKETS)||{}).baskets||[]).find(b=>b&&b.id===id)||null; }catch(e){ return null; } }
// "early cracks": rollover band still low but reasons exist AND the theme is very extended.
function earlyCracks(t){
  const rr=(t.textures||{}).rollover_risk||{};
  return rr.band==='low' && (rr.reasons||[]).length>0 && t.rs_pctile!=null && t.rs_pctile>=0.9;
}
// A4 — absolute-drawdown "cracks" (descriptive): the fading guard is RELATIVE-only, so an
// all-boats selloff can leave a constructive label on a basket that is falling hard in
// absolute terms. This pill states the absolute tape; it complements (never replaces)
// the relative early-cracks pill. Two legs: 5d abs return ≤ −3%, or the ±3% impulse
// tape ≥6 down-movers outnumbering up-movers ≥3×. No forward verbs.
function absCracks(t){
  if(t.label!=='dominant'&&t.label!=='emerging') return null;
  const p5=(((t.perf||{})['5d'])||{}).ret, im=t.impulse||{};
  const leg5d=(p5!=null&&p5<=-0.03);
  const legImp=((im.down3||0)>=6&&(im.down3||0)>=3*(im.up3||0));
  return (leg5d||legImp)?{p5:p5,leg5d:leg5d,legImp:legImp,up3:im.up3||0,down3:im.down3||0}:null;
}
// The faster counter-textures that DISAGREE with a constructive label. Each entry is
// [en, zh] — purely descriptive, computed from already-published payload fields.
function contestedTextures(t, cyc){
  const rr=(t.textures||{}).rollover_risk||{};
  const list=[];
  if(cyc && (((cyc.turns||[]).some(x=>x&&x.provisional&&x.k==='peak')) || ((cyc.proj||{}).nextTurn==='trough')))
    list.push(['cycle clock at a provisional peak / projecting a trough next','周期时钟处于临时顶部 / 推演下一拐点为底部']);
  if(t.rs_pctile!=null && t.rs_pctile>=0.95)
    list.push(['very extended (RS ≥95%ile)','相对强度极端延展（≥95分位）']);
  if(rr.band==='elevated'||rr.band==='high')
    list.push(['roll-over risk '+rr.band+(rr.reasons&&rr.reasons.length?': '+rr.reasons.join(' · '):''),'回落风险'+(rr.band_zh||rr.band)+(rr.reasons&&rr.reasons.length?'：'+rr.reasons.join(' · '):'')]);
  else if(earlyCracks(t))
    list.push(['early cracks: '+(rr.reasons||[]).join(' · '),'初现裂痕：'+(rr.reasons||[]).join(' · ')]);
  if(t.delta_5d!=null && t.delta_5d<0)
    list.push(['negative 5-day relative return ('+fmtPct(t.delta_5d)+')','5日相对收益为负（'+fmtPct(t.delta_5d)+'）']);
  return list;
}
function isContested(t){
  return (t.label==='dominant'||t.label==='emerging')
    && contestedTextures(t,(_basketOf(t.id)||{}).cycle).length>=2;
}
// flip-distance micro-caption (engine-computed, same literals as the label logic)
function flipCaption(t){
  const fd=t.flip_distance||null;
  if(!fd||!(t.label==='dominant'||t.label==='emerging')) return '';
  if(fd.route_a_bps==null||fd.route_a_bps<=0) return '';
  const bps=Math.round(fd.route_a_bps), s=fd.route_a_sessions_est;
  return `<div class="flipcap" title="${esc(fd.note_en||'')}">${
    L(`${bps} bps from FADING${s!=null?` (~${s} bad session${s!==1?'s':''})`:''}`,
      `距「退潮」仅${bps}个基点${s!=null?`（约${s}个坏交易日）`:''}`)} <span class="tstag">${L('descriptive','描述性')}</span></div>`;
}
// momentum term-structure strip: 5d/20d/60d relative return + a deterministic pattern name.
function termStrip(t){
  const hz=['5d','20d','60d'];
  const v=hz.map(h=>(((t.perf||{})[h])||{}).rel);
  if(v.every(x=>x==null)) return '';
  const cells=hz.map((h,i)=>`<span class="tsc ${cls(v[i])}">${h} <b>${fmtPct(v[i])}</b></span>`).join('');
  const [a,b2,c]=v; let pat='mixed', patZh='震荡';
  if(a!=null&&b2!=null&&c!=null&&a>0&&b2>0&&c>0){ pat='aligned up'; patZh='同向向上'; }
  else if(a!=null&&c!=null&&a<0&&c>0){ pat='rolling from the front'; patZh='前端回落'; }
  else if(a!=null&&b2!=null&&c!=null&&a<0&&b2<0&&c<0){ pat='aligned down'; patZh='同向向下'; }
  return `<div class="termstrip" title="descriptive — a shape/fragility read, not a forecast">${cells}
    <span class="tspat">${L(pat,patZh)}</span><span class="tstag">${L('shape read, not a signal','形态读数，非信号')}</span></div>`;
}
function themeCard(t){
  const lc=LABEL_COLOR[t.label]||LABEL_COLOR.neutral;
  const r20=t.perf&&t.perf['20d']?t.perf['20d'].rel:null;
  const spk=sparkTail(ratio(CHART.baskets[t.id]||[]),40);
  const b=t.breadth||{}, im=t.impulse||{}, tx=t.textures||{};
  const ba=tx.bull_age||{}, ob=tx.overbought||{}, ce=tx.clean_entry||{}, rr=tx.rollover_risk||{};
  const top=(t.leadership&&t.leadership.top)||[];
  const ss=t.signal_strength||null;
  const obc = ob.value>=0.6?'neg':ob.value>=0.35?'warn':'';
  // Build full flags list (used in expander txrow)
  const flags=[];
  if(ce.flag) flags.push(`<span class="tflag up">✦ ${L('clean entry','干净入场')}</span>`);
  if(rr.band==='high'||rr.band==='elevated') flags.push(`<span class="tflag ${rr.band==='high'?'dn':'wn'}">⚠ ${L('roll-over','回落风险')}</span>`);
  else if(earlyCracks(t)) flags.push(`<span class="tflag mut" title="descriptive — a shape/fragility read, not a forecast: ${esc((rr.reasons||[]).join(' · '))}">◌ ${L('early cracks','初现裂痕')}</span>`);
  const ck=absCracks(t);
  if(ck) flags.push(`<span class="tflag wn" style="opacity:.88" title="descriptive — the absolute tape, not a forecast: 5d ${ck.p5!=null?fmtPct(ck.p5):'—'} abs${ck.legImp?` · ±3% impulse ${ck.up3} up / ${ck.down3} down`:''}">▾ ${L('CRACKS — falling in absolute terms','裂痕 — 绝对价格下行')}</span>`);
  if(ss&&ss.grade==='backtested') flags.push(`<span class="tflag dn" title="${esc(ss.en||'')} (HAC t ${ss.t_hac}, n ${ss.n})">🔬 ${L('backtested risk','已回测风险')}</span>`);
  // Row 3: single highest-priority glyph only (no text label), with data-tip-en/zh
  var glyphRow='';
  if(ck){
    const tipEn=`CRACKS — falling in absolute terms: 5d ${ck.p5!=null?fmtPct(ck.p5):'—'} abs${ck.legImp?' · ±3% impulse '+ck.up3+' up / '+ck.down3+' down':''}`;
    const tipZh=`裂痕 — 绝对价格下行：5日${ck.p5!=null?fmtPct(ck.p5):'—'}${ck.legImp?' · ±3%脉冲 '+ck.up3+'升 / '+ck.down3+'降':''}`;
    glyphRow=`<div class="tglyph"><span class="tflag wn" style="opacity:.88" data-tip-en="${esc(tipEn)}" data-tip-zh="${esc(tipZh)}">▾</span></div>`;
  } else if(rr.band==='high'||rr.band==='elevated'){
    const tipEn=`Roll-over risk ${rr.band}${rr.reasons&&rr.reasons.length?': '+rr.reasons.join(' · '):''}`;
    const tipZh=`回落风险${rr.band_zh||rr.band}${rr.reasons&&rr.reasons.length?'：'+rr.reasons.join(' · '):''}`;
    glyphRow=`<div class="tglyph"><span class="tflag ${rr.band==='high'?'dn':'wn'}" data-tip-en="${esc(tipEn)}" data-tip-zh="${esc(tipZh)}">⚠</span></div>`;
  } else if(ss&&ss.grade==='backtested'){
    const tipEn=`${ss.en||''} (HAC t ${ss.t_hac}, n ${ss.n})`;
    glyphRow=`<div class="tglyph"><span class="tflag dn" data-tip-en="${esc(tipEn)}" data-tip-zh="${esc(ss.zh||ss.en||'')}">🔬</span></div>`;
  } else if(earlyCracks(t)){
    const tipEn=`Early cracks: ${(rr.reasons||[]).join(' · ')} — descriptive, a shape/fragility read`;
    const tipZh=`初现裂痕：${(rr.reasons||[]).join(' · ')} — 描述性，形态读数`;
    glyphRow=`<div class="tglyph"><span class="tflag mut" data-tip-en="${esc(tipEn)}" data-tip-zh="${esc(tipZh)}">◌</span></div>`;
  } else if(ce.flag){
    const tipEn='Clean entry — member setups align with the theme direction';
    const tipZh='干净入场 — 成分股入场信号与主题方向一致';
    glyphRow=`<div class="tglyph"><span class="tflag up" data-tip-en="${esc(tipEn)}" data-tip-zh="${esc(tipZh)}">✦</span></div>`;
  }
  const bullPill = ba.in_bull
    ? `🐂 ${ba.approx_months!=null?ba.approx_months+'mo':''} ${L(ba.stage||'','')||esc(ba.stage_zh||'')}`
    : `🐻 ${L('downtrend','下行')}`;
  const contested=isContested(t);
  const cTex=contested?contestedTextures(t,(_basketOf(t.id)||{}).cycle):[];
  const labelChip = contested
    ? `<span class="tlabel" style="background:${lc[0]};border:1px solid ${lc[1]};color:${lc[2]}" title="contested — faster descriptive textures disagree with the validated label: ${esc(cTex.map(x=>x[0]).join(' | '))}. A shape/fragility read, not a forecast.">${L(t.label_en+' · contested',(t.label_zh||t.label_en)+' · 存在分歧')}</span>`
    : badge('tlabel',lc,t.label_en,t.label_zh);
  const W=(THEME&&THEME.weights)||{trend:.34,breadth:.22,impulse:.10,macro:.20,crowding:.14};
  // W8-R5: tape-state chip for CN baskets (read turn_state field from payload).
  // dualChip shown when trend reco (avoid/trim) disagrees with tape turning state.
  const tc = tapeChip(t);
  const dc = dualChip(t);
  return `<div class="tcard" id="theme-${t.id}" style="--tc:${lc[2]}">
    <div class="top">
      ${labelChip}${heatDot(t)}${tc}
      <a class="nm" href="${(window.BASKET_BASE||'basket/')}${t.id}.html" title="open full theme detail">${L(esc(t.name),esc(t.name_zh))}</a>
      <span class="sc">${t.score}<small>/100</small></span>
    </div>
    ${dc?`<div class="txrow" style="margin:2px 0 4px">${dc}</div>`:''}
    <div class="subrow">
      <span>#${t.rank}</span>
      ${recoChip(t)}
      <span class="${cls(r20)}">${fmtPct(r20)} 20d</span>
      <span class="spark">${sparkSvg(spk,{w:84,h:24,color:lc[2]})}</span>
    </div>
    ${glyphRow}
    <details class="tmore"><summary>${L('More','更多')}</summary>
      ${flipCaption(t)}
      ${compBar(t.components,W)}
      ${compLegend(t.components)}
      ${termStrip(t)}
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
      <div class="why">${recoNoEntry(t)?RECO_NOENTRY_WHY():L(esc(t.reco_why_en),esc(t.reco_why_zh))}</div>
      ${contested?`<div class="why" style="opacity:.9">${L('Contested — faster textures disagreeing with the label (descriptive, not a forecast)','存在分歧 — 与标签相悖的更快纹理（描述性，非预测）')}: ${cTex.map(x=>L(esc(x[0]),esc(x[1]))).join(' · ')}</div>`:''}
      ${ss?`<div class="why" style="opacity:.82">${L('Signal grade','信号评级')}: <b>${esc(ss.grade)}</b> — ${L(esc(ss.en||''),esc(ss.zh||''))}</div>`:''}
      ${top.length?`<div class="why">${L('leaders','领涨')}: ${top.map(x=>esc(x.ticker)).join(', ')}${t.leadership.breadth==='narrow'?' ⚠':''}</div>`:''}
      <a class="detail-link" href="${(window.BASKET_BASE||'basket/')}${t.id}.html">${L('Full detail · holdings buy/avoid →','完整详情 · 成分可买/回避 →')}</a>
    </details>
  </div>`;
}
function renderThemeDesk(){
  const sec=document.getElementById('theme-desk-section');
  if(!THEME||!(THEME.themes||[]).length){ if(sec) sec.style.display='none'; return; }
  document.getElementById('theme-desk').innerHTML=(THEME.themes||[]).map(themeCard).join('');
  const d=THEME.disclaimer||{}; document.getElementById('theme-disclaimer').innerHTML=L(esc(d.en||''),esc(d.zh||''));
  // cap the freshly-built desk at 3 rows behind a "show more" (theme.js, idempotent).
  try{ if(window.initShowMore) window.initShowMore(); }catch(e){}
}
function renderMacroCtx(){
  if(!THEME) return;
  const m=THEME.macro_context||{};
  const el=document.getElementById('macro-ctx');
  // markets without a single macro-regime snapshot (e.g. the cross-country Intl book) carry no
  // backdrop — hide the row rather than show a line of em-dashes.
  const empty=!m.quad_name&&!m.quad&&(!m.fed_dir||m.fed_dir==='unknown')&&!m.nfci_state&&!m.cycle&&!m.dollar_regime&&!m.bond_cycle;
  if(empty){ if(el) el.style.display='none'; return; }
  if(el) el.style.display='';
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
  // Build a pulse lookup keyed by theme id so we can decorate climber/faller rows with
  // velocity context (heat dot, 20d rank trajectory) — undefined-safe for pre-W4 payloads.
  const pulseById = {};
  (THEME.themes||[]).forEach(t=>{ if(t&&t.id) pulseById[t.id]=t; });
  const row=t=>{
    const ar=t.rank_5d>0?'▲':t.rank_5d<0?'▼':'·'; const ac=t.rank_5d>0?'pos':t.rank_5d<0?'neg':'muted';
    const pt = pulseById[t.id] || t;                          // pulse fields merged into themes
    const traj = rankTrajectory(pt);
    const dot = heatDot(pt);
    return `<div class="rotrow">${dot}<span class="rn"><a href="${(window.BASKET_BASE||'basket/')}${encodeURIComponent(t.id)}.html">${L(esc(t.name),esc(t.name_zh))}</a></span>
      <span class="rv ${cls(t.delta_5d)}">${fmtPct(t.delta_5d)}</span>
      <span class="rk ${ac}" title="5d rank change${traj?' · '+traj:''}">${ar}${t.rank_5d?Math.abs(t.rank_5d):''}${traj?`<span class="rk20"> · ${traj}</span>`:''}</span></div>`;};
  const subtitle=`<p class="rot-sub">${L('Rank changes across themes; descriptive only.','主题排名变化；仅作描述。')}</p>`;
  const col=(en,zh,emo,arr)=>`<div class="rotcol"><h4>${emo} ${L(en,zh)}</h4>${arr.length?arr.map(row).join(''):`<div class="muted sm" style="padding:6px 0">${L('none','无')}</div>`}</div>`;
  const rotEl=document.getElementById('rotation');
  rotEl.innerHTML=subtitle+`<div class="rotwrap" style="margin-top:6px">${col('Weekly climbers','本周上升','▲',rot.climbers||[])}${col('Weekly fallers','本周下降','▽',rot.fallers||[])}</div>`;
}
function renderActNow(){
  const sec=document.getElementById('actnow-section');
  if(!THEME||!THEME.act_now){
    const pulseOnly=actNowPulseBar(THEME&&THEME.themes||[]);
    if(!pulseOnly){ if(sec) sec.style.display='none'; return; }
    const el=document.getElementById('actnow'); if(el) el.innerHTML=pulseOnly;
    return;
  }
  const a=THEME.act_now;
  const ACT={enter:['ENTER','建仓','#16a34a'],accumulate:['ACCUMULATE','加仓','#22c55e'],trim:['TRIM','减仓','#f97316'],avoid:['AVOID','回避','#ef4444']};
  // W8-R5: build turn_state lookup from BASKETS payload (basket-level) and THEME.themes.
  // Both sources carry the turn_state field after the build script annotates them.
  const _turnById = {};
  try{
    (((typeof BASKETS!=='undefined'&&BASKETS)||{}).baskets||[]).forEach(b=>{ if(b&&b.id) _turnById[b.id]=b.turn_state||null; });
    (THEME.themes||[]).forEach(t=>{ if(t&&t.id&&t.turn_state) _turnById[t.id]=t.turn_state; });
  }catch(e){}
  const row=x=>{const ac=ACT[x.action]||['','',cssv('--muted')];
    return `<a class="anrow" href="${(window.BASKET_BASE||'basket/')}${x.id}.html">
      <span class="anverb" style="color:${ac[2]};border-color:${ac[2]}">${L(ac[0],ac[1])}</span>
      <span class="rn">${L(esc(x.name),esc(x.name_zh))}</span>
      <span class="anwhy muted sm">${esc((x.reasons||[]).join(' · '))}</span>
      <span class="ansc">${x.score}</span></a>`;};
  // wait-for-a-pullback rows: same reco verb (muted) + the honest per-theme reason.
  const rowWait=x=>{const ac=ACT[x.action]||['','',cssv('--muted')];
    return `<a class="anrow" href="${(window.BASKET_BASE||'basket/')}${x.id}.html">
      <span class="anverb" style="color:${ac[2]};border-color:${ac[2]};opacity:.72">${L(ac[0],ac[1])}</span>
      <span class="rn">${L(esc(x.name),esc(x.name_zh))}</span>
      <span class="anwhy muted sm">${x.reason_en?L(esc(x.reason_en),esc(x.reason_zh||x.reason_en)):esc((x.reasons||[]).join(' · '))}</span>
      <span class="ansc">${x.score}</span></a>`;};
  // W8-R5: reduce/avoid rows get dual-chip when tape is TURNING/CONFIRMED (FT-R1).
  const rowReduce=x=>{const ac=ACT[x.action]||['','',cssv('--muted')];
    const ts = _turnById[x.id]||null;
    const hasDual = ts && DISAGREE_TAPE_STATES.has(ts);
    const dc = hasDual ? dualChip({reco:x.action||'avoid',turn_state:ts}) : '';
    const tc = (!hasDual && ts && ts!=='NONE') ? tapeChipOnRow({turn_state:ts}) : '';
    return `<a class="anrow" href="${(window.BASKET_BASE||'basket/')}${x.id}.html">
      <span class="anverb" style="color:${ac[2]};border-color:${ac[2]}">${L(ac[0],ac[1])}</span>
      <span class="rn">${L(esc(x.name),esc(x.name_zh))}</span>
      ${dc||tc}
      <span class="anwhy muted sm">${esc((x.reasons||[]).join(' · '))}</span>
      <span class="ansc">${x.score}</span></a>`;};
  const buys=a.buy||[], wait=a.add_on_pullback||[], red=a.reduce||[];
  const moreBtn=n=>n>5?`<button class="lst-more" type="button" aria-expanded="false"><span class="lm-show">${L('Show more','显示更多')} ▾</span><span class="lm-hide">${L('Show less','收起')} ▴</span></button>`:'';
  const anCol=(cls,head,arr,empty,rowFn)=>`<div class="ancol lst-wrap"><h4 class="anh ${cls}">${head} <span class="muted sm">(${arr.length})</span></h4>${arr.length?`<div class="anlist lst-collapse is-collapsed">${arr.map(rowFn||row).join('')}</div>${moreBtn(arr.length)}`:`<div class="muted sm" style="padding:10px 2px">${empty}</div>`}</div>`;
  const pulseBar = actNowPulseBar(THEME.themes||[]);
  document.getElementById('actnow').innerHTML=pulseBar+`<div class="anwrap three">
    ${anCol('buy',`✅ ${L('Buy now (clean entry)','立即买入（干净入场）')}`,buys,L('Nothing has a clean entry right now — patience.','当前无干净入场点 — 耐心等待。'))}
    ${anCol('wait',`⏳ ${L('In favour — no clean entry, wait for a pullback','看好 — 无干净入场点，等待回调')}`,wait,L('none','无'),rowWait)}
    ${anCol('red',`🔻 ${L('Reduce / avoid','减仓 / 回避')}`,red,L('none','无'),rowReduce)}
  </div>`;
}
// sleeve-size chip (validated drawdown-control channel; payload-gated so only markets that
// publish BASKETS.sleeve_chip — e.g. the curated China overview — render anything).
function renderSleeveChip(){
  const host=document.getElementById('sleeve-chip'); if(!host) return;
  const sc=(typeof BASKETS!=='undefined'&&BASKETS)?BASKETS.sleeve_chip:null;
  if(!sc||sc.sleeve_factor==null){ host.innerHTML=''; return; }
  const st=String(sc.radar_state||'').toLowerCase();
  const sev=/stress|risk_off|riskoff|high/.test(st)?'var(--down)':/caution|elevated|warn/.test(st)?'var(--warn)':'var(--muted)';
  host.innerHTML=`<div class="sleeve-chip" style="border-left:3px solid ${sev}" title="${esc((sc.passport&&sc.passport.note)||'')}">
    <span class="sl-main">🛰️ <b>${L(esc(sc.label_en||''),esc(sc.label_zh||sc.label_en||''))}</b></span>
    ${sc.dominant_driver_en?`<span class="muted sm">· ${L(esc(sc.dominant_driver_en),esc(sc.dominant_driver_zh||sc.dominant_driver_en))}</span>`:''}
    <span class="sl-tag muted">${L('Drawdown-control sizing; not a return forecast.','回撤控制仓位；并非收益预测。')}</span>
  </div>`;
}
// renderRegimeSizing() — returns the sizing pill HTML string ('' when calm / inactive).
// Called from actNowPulseBar(); no longer writes to a standalone DOM element.
function renderRegimeSizing(){
  const rs=THEME&&THEME.regime_sizing;
  if(!rs||!rs.active||(rs.gross_scalar||1)>=1.0) return '';   // inert when calm
  const pct=Math.round((rs.gross_scalar||1)*100);
  const mech=Math.round((rs.mech_scalar||1)*100), reg=Math.round((rs.regime_caution||1)*100), sc=Math.round((rs.scored_cut||1)*100);
  const demoted=(THEME.themes||[]).filter(t=>t&&t.regime_demoted).length;
  const factorsEn=[`volatility target ${mech}%`];
  if(reg<100) factorsEn.push(`risk regime ${reg}%`);
  if(sc<100) factorsEn.push(`signal mix ${sc}%`);
  const factorsZh=[`波动率目标 ${mech}%`];
  if(reg<100) factorsZh.push(`风险状态 ${reg}%`);
  if(sc<100) factorsZh.push(`信号组合 ${sc}%`);
  const tipEn=`How it's set: ${factorsEn.join(' · ')} → ${pct}%`
    +(demoted?` · ${demoted} theme(s) eased to hold-only`:'')
    +` · Volatile markets get smaller position sizes. This does not change the basket ranking.`;
  const tipZh=`计算方式：${factorsZh.join(' · ')} → ${pct}%`
    +(demoted?` · ${demoted}个主题降为仅持有`:'')
    +` · 波动加大时降低仓位；不改变篮子排序。`;
  return `<span class="pulse-size" data-tip-en="${esc(tipEn)}" data-tip-zh="${esc(tipZh)}">⚠ ${L('positions sized to '+pct+'%','仓位缩至 '+pct+'%')}</span>`;
}
function renderConcentration(){
  const sec=document.getElementById('concentration-section'); if(!THEME){ if(sec) sec.style.display='none'; return; }
  const mc=THEME.market_concentration||{};
  const vmap={narrow:['var(--down)','narrow','狭窄'],broad:['var(--up)','broad','广泛'],mixed:['var(--warn)','mixed','中性']};
  const vv=vmap[mc.verdict]||vmap.mixed;
  const adc=(en,zh,v)=>`<div class="adc"><div class="k">${L(en,zh)}</div><div class="v ${v==null?'muted':(v<1?'neg':'pos')}">${v==null?'—':(+v).toFixed(2)}</div></div>`;
  const narrow=`<div class="panel pad" style="border-left:3px solid ${vv[0]}">
    <div style="display:flex;flex-wrap:wrap;gap:18px;align-items:center">
      <div><span class="muted sm">${L((THEME.bench_label||'S&P')+' breadth',(THEME.bench_label_zh||'标普')+'广度')}</span><div style="font-size:18px;font-weight:740;color:${vv[0]}">${L(vv[1],vv[2])}</div></div>
      <div class="adgrid">${adc('A/D today','今日',mc.ad_ratio)}${adc('3-day','3日',mc.ad_3d)}${adc('weekly','周',mc.ad_w)}${adc('monthly','月',mc.ad_m)}</div>
      <div class="muted sm">${L('above 50d','站上50日')} <b>${mc.pct_above_50!=null?mc.pct_above_50+'%':'—'}</b> · ${L('above 200d','站上200日')} <b>${mc.pct_above_200!=null?mc.pct_above_200+'%':'—'}</b> · ${L('new hi/lo','新高/低')} <b class="pos">${mc.nh}</b>/<b class="neg">${mc.nl}</b></div>
    </div></div>`;
  // pulse lookup for heat dots on breadth leaders/laggards
  const cPulseById = {};
  (THEME.themes||[]).forEach(t=>{ if(t&&t.id) cPulseById[t.id]=t; });
  const lead=(arr,en,zh,sign)=>`<div class="rotcol"><h4>${sign} ${L(en,zh)}</h4>${(arr||[]).map(x=>{const pt=cPulseById[x.id]||x;return `<div class="rotrow">${heatDot(pt)}<span class="rn"><a href="${(window.BASKET_BASE||'basket/')}${x.id}.html">${L(esc(x.name),esc(x.name_zh))}</a></span><span class="rv ${x.net_ad>=0?'pos':'neg'}">${x.net_ad>=0?'+':''}${x.net_ad}</span><span class="rk muted">${x.adv}/${x.dec}</span></div>`}).join('')}</div>`;
  const tlist=(arr,en,zh,kind)=>`<div class="rotcol"><h4>${kind==='entry'?'✦':'⚠'} ${L(en,zh)}</h4>${(arr||[]).length?arr.map(x=>`<div class="rotrow"><span class="rn"><a href="${(window.BASKET_BASE||'basket/')}${x.id}.html">${L(esc(x.name),esc(x.name_zh))}</a></span><span class="rv">${kind==='entry'?Math.round(x.quality*100)+'%':esc(x.band)}</span></div>`).join(''):`<div class="muted sm" style="padding:6px 0">${L('none right now','暂无')}</div>`}</div>`;
  document.getElementById('concentration').innerHTML = narrow
    + `<div class="rotwrap" style="margin-top:12px">${lead(THEME.breadth_leaders,'Owns the advance','主导上涨','▲')}${lead(THEME.breadth_laggards,'In the decline','处于下跌','▽')}</div>`
    + `<div class="rotwrap" style="margin-top:12px">${tlist(THEME.entries,'Clean entries (emerging)','干净入场（新兴）','entry')}${tlist(THEME.rollover,'Roll-over watch','回落观察','roll')}</div>`;
}
// ---- scorecard detail popups (click a scorecard → floating list of names) ---
function _bbase(){ return window.BASKET_BASE||'basket/'; }
function _scOverlay(){
  let ov=document.getElementById('sc-modal');
  if(!ov){
    ov=document.createElement('div'); ov.id='sc-modal'; ov.className='scmodal';
    ov.innerHTML='<div class="scm-card" role="dialog" aria-modal="true"><button class="scm-x" aria-label="close">✕</button><div class="scm-hd"></div><div class="scm-sub"></div><div class="scm-bd"></div></div>';
    document.body.appendChild(ov);
    ov.addEventListener('click',e=>{ if(e.target===ov) scClose(); });
    ov.querySelector('.scm-x').onclick=scClose;
    document.addEventListener('keydown',e=>{ if(e.key==='Escape') scClose(); });
  }
  return ov;
}
function scClose(){ const ov=document.getElementById('sc-modal'); if(ov) ov.classList.remove('open'); }
function _nmRow(x,withRet){
  // name shows the human name where we have one, else the ticker; the ticker sub-label
  // appears only in the language that actually has a name (else it would duplicate the ticker).
  const nm=`<span class="l-en">${esc(x.n||x.t)}</span><span class="l-zh">${esc(x.n_zh||x.n||x.t)}</span>`;
  const tk=`<span class="l-en">${x.n?`<span class="scm-tk">${esc(x.t)}</span>`:''}</span><span class="l-zh">${x.n_zh?`<span class="scm-tk">${esc(x.t)}</span>`:''}</span>`;
  const th=x.tid?`<a class="scm-th" href="${_bbase()}${esc(x.tid)}.html" title="${esc(x.th||'')}">${L(esc(x.th||''),esc(x.th_zh||x.th||''))}</a>`:'';
  const ret=withRet?`<span class="scm-r ${cls(x.r)}">${fmtPct(x.r)}</span>`:'';
  return `<div class="scm-row"><span class="scm-nm">${nm}${tk}</span>${th}${ret}</div>`;
}
function _scCol(title,arr,withRet,tone){
  const rows=(arr&&arr.length)?arr.map(x=>_nmRow(x,withRet)).join(''):`<div class="scm-empty">${L('none','无')}</div>`;
  return `<div class="scm-col"><div class="scm-colh ${tone||''}">${title} <b>${(arr||[]).length}</b></div>${rows}</div>`;
}
function openSc(kind){
  if(!THEME) return;
  const s=THEME.impulse_scorecard||{}, rc=THEME.recommendations||{};
  const ov=_scOverlay(); let hd='',sub='',bd='';
  if(kind==='impulse'){
    hd=L('±3% daily impulse','±3% 当日脉冲');
    sub=L('Basket members that moved at least 3% today.','今日涨跌幅至少 3% 的篮子成分。');
    bd=`<div class="scm-2col">${_scCol(L('Surged ≥3%','涨≥3%'),s.up_names,true,'up')}${_scCol(L('Dropped ≥3%','跌≥3%'),s.down_names,true,'dn')}</div>`;
  } else if(kind==='extremes'){
    hd=L('52-week extremes','52周极值');
    sub=L('Members printing a fresh 52-week high or low today.','今日创出52周新高或新低的成分。');
    bd=`<div class="scm-2col">${_scCol(L('New 52-wk highs','创52周新高'),s.nh_names,false,'up')}${_scCol(L('New 52-wk lows','创52周新低'),s.nl_names,false,'dn')}</div>`;
  } else if(kind==='reco'){
    hd=L('Recommendation tally','建议统计');
    sub=L('Action buckets for every theme. Click a theme to open it.','所有主题的操作分组。点击主题打开详情。');
    const grp=(en,zh,keys,tone)=>{ const arr=[].concat(...keys.map(k=>rc[k]||[]));
      const rows=arr.length?arr.map(t=>`<a class="scm-row" href="${_bbase()}${esc(t.id)}.html"><span class="scm-nm">${L(esc(t.name),esc(t.name_zh||t.name))}</span><span class="scm-th">${esc((t.label||'').toUpperCase())}</span><span class="scm-r">${t.score}</span></a>`).join(''):`<div class="scm-empty">${L('none','无')}</div>`;
      return `<div class="scm-col"><div class="scm-colh ${tone}">${L(en,zh)} <b>${arr.length}</b></div>${rows}</div>`; };
    bd=`<div class="scm-3col">${grp('Enter / add','建仓／加仓',['enter','accumulate'],'up')}${grp('Hold','持有',['hold'],'')}${grp('Trim / avoid','减仓／回避',['trim','avoid'],'dn')}</div>`;
  } else return;
  ov.querySelector('.scm-hd').innerHTML=hd;
  ov.querySelector('.scm-sub').innerHTML=sub;
  ov.querySelector('.scm-bd').innerHTML=bd;
  ov.classList.add('open');
}
function renderScorecards(){
  const sec=document.getElementById('impulse-section');
  if(!THEME||!THEME.impulse_scorecard){ if(sec) sec.style.display='none'; return; }
  const s=THEME.impulse_scorecard, rc=THEME.recommendations||{};
  const duo=(a,b)=>{const t=(a+b)||1;return `<div class="duo"><i style="width:${a/t*100}%;background:var(--up)"></i><i style="width:${b/t*100}%;background:var(--down)"></i></div>`;};
  const cnt=k=>(rc[k]||[]).length;
  const hint=`<div class="scm-hint">${L('Click for the names →','点击查看个股 →')}</div>`;
  const c1=`<div class="scard clk" data-sc="impulse"><div class="sk">${L('±3% daily impulse','±3% 当日脉冲')}</div>
    <div class="bigrow"><div><div class="big up">${s.up3}</div><div class="sublbl">${L('up ≥3%','涨≥3%')}</div></div>
    <div><div class="big dn">${s.down3}</div><div class="sublbl">${L('down ≥3%','跌≥3%')}</div></div></div>
    ${duo(s.up3,s.down3)}<div class="net">${L('net','净')} <b class="${cls(s.net)}">${s.net>=0?'+':''}${s.net}</b> ${L('of '+s.n+' names',' ／共 '+s.n+' 只')}</div>${hint}</div>`;
  const c2=`<div class="scard clk" data-sc="extremes"><div class="sk">${L('52-week extremes','52周极值')}</div>
    <div class="bigrow"><div><div class="big up">${s.nh}</div><div class="sublbl">${L('new highs','新高')}</div></div>
    <div><div class="big dn">${s.nl}</div><div class="sublbl">${L('new lows','新低')}</div></div></div>
    ${duo(s.nh,s.nl)}<div class="net">${L('net','净')} <b class="${cls(s.net_hl)}">${s.net_hl>=0?'+':''}${s.net_hl}</b></div>${hint}</div>`;
  const c3=`<div class="scard clk" data-sc="reco"><div class="sk">${L('recommendation tally','建议统计')}</div>
    <div class="bigrow" style="gap:12px;flex-wrap:wrap">
      <div><div class="big up">${cnt('enter')+cnt('accumulate')}</div><div class="sublbl">${L('enter / add','建仓／加仓')}</div></div>
      <div><div class="big" style="color:var(--muted)">${cnt('hold')}</div><div class="sublbl">${L('hold','持有')}</div></div>
      <div><div class="big dn">${cnt('trim')+cnt('avoid')}</div><div class="sublbl">${L('trim / avoid','减仓／回避')}</div></div>
    </div>${hint}</div>`;
  const box=document.getElementById('scorecards');
  box.innerHTML=c1+c2+c3;
  box.querySelectorAll('.scard.clk').forEach(c=>c.onclick=()=>openSc(c.dataset.sc));
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

function deskBoot(){ try{ renderSleeveChip(); }catch(e){} try{ renderActNow(); }catch(e){}
  try{ renderMacroCtx(); }catch(e){}
  try{ renderThemeDesk(); }catch(e){} try{ renderConcentration(); }catch(e){}
  try{ renderRotation(); }catch(e){} try{ renderScorecards(); }catch(e){} try{ renderBell(); }catch(e){} }

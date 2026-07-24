/* Subsector Confluence desk — an answer-first rotation & entry-timing board rendered from the
   precomputed engine JSON. Four datasets share one render path:
     subsectors — S&P-500 Finviz sub-industries  (marketdata/subsector_confluence.json)
     baskets    — curated thematic baskets        (marketdata/basket_confluence.json)
     nasdaq     — Nasdaq-100 sub-industries        (marketdata/subsector_confluence_nasdaq.json)
     russell    — Russell-2000 sub-industries      (marketdata/subsector_confluence_russell.json)
   Layout is three altitudes: VERDICT (hero — rotation backdrop + confluence ribbon + best entry),
   ACT (buy-ready | avoid board + double-confluence picks) and EXPLORE (leadership, sector backdrop,
   nasdaq internals, full searchable table). Universe-level rotation context comes from
   marketdata/index_leadership.json. Display-tier only — a timing map, not a buy list.
   Vanilla JS, no deps. Bilingual via .l-en/.l-zh spans (theme.js toggles by html[data-lang]). */
(function () {
  'use strict';
  var L = function (en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh == null ? en : zh) + '</span>'; };

  var DS = {
    subsectors: { url: 'marketdata/subsector_confluence.json', dir: 'subsector/', prefix: '', groupsKey: 'subsectors', noun: ['subsectors', '子行业'], rollup: ['Sector backdrop', '板块背景'], rollupDesc: ['Each sector as one equal-weight basket — the backdrop the subsectors live inside.', '每个板块作为一个等权篮子——子行业所处的大背景。'] },
    baskets: { url: 'marketdata/basket_confluence.json', dir: 'subsector/', prefix: 'b-', groupsKey: 'baskets', noun: ['baskets', '篮子'], rollup: null },
    nasdaq: { url: 'marketdata/subsector_confluence_nasdaq.json', dir: 'subsector_nasdaq/', prefix: '', groupsKey: 'subsectors', noun: ['subsectors', '子行业'], rollup: ['Amalgamated complexes', '汇聚综合体'], rollupDesc: ['Higher-level complexes (semis, software, internet, the ex-tech bucket) — watch whether leadership rotates among them or bleeds out of tech. RS is vs QQQ (within-index).', '高层级综合体（半导体、软件、互联网、非科技桶）——观察领导地位是在它们之间轮动还是流出科技。相对强弱基准为 QQQ（指数内）。'] },
    russell: { url: 'marketdata/subsector_confluence_russell.json', dir: 'subsector_russell/', prefix: '', groupsKey: 'subsectors', noun: ['subsectors', '子行业'], rollup: ['Sector amalgamations', '板块汇聚'], rollupDesc: ['The 11 sectors as equal-weight baskets — the natural small-cap rotation buckets. RS is vs IWM (within-index).', '11 个板块作为等权篮子——小盘股自然的轮动桶。相对强弱基准为 IWM（指数内）。'] }
  };
  var DATA = {};
  var TAB = 'subsectors';
  var NIDATA = null;
  var LEAD = null;
  var SORT = {};   // per-tab full-table sort {col, dir}
  var FILTER = {}; // per-tab full-table search text

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function num(x, d) { return (x == null || isNaN(x)) ? '–' : Number(x).toFixed(d == null ? 0 : d); }
  function signed(x, d) { if (x == null || isNaN(x)) return '<span class="num">–</span>'; var v = Number(x); return '<span class="num ' + (v >= 0 ? 'pos' : 'neg') + '">' + (v >= 0 ? '+' : '') + v.toFixed(d == null ? 1 : d) + '</span>'; }
  function tierBadge(t) { return '<span class="tier ' + (t || 'none') + '">' + (t || '—') + '</span>'; }
  function regimePill(r) { var side = (r && r.side) || 'neutral'; return '<span class="pill ' + side + '">' + esc((r && r.label) || (r && r.state) || '—') + '</span>'; }
  // compact data-confidence dot (title EN-only — no translated text in title= per house law)
  function relDot(rel) { var r = (rel || '').toLowerCase(); if (r !== 'high' && r !== 'med' && r !== 'low') return ''; var lab = { high: 'High confidence — deep live coverage', med: 'Medium confidence', low: 'Thin data — read with caution' }[r]; return '<span class="rel ' + r + '" title="' + lab + '"><i></i></span>'; }
  function freshTxt(e) {
    if (!e) return '';
    if (e.tier === 'T3' || e.tier === 'T4') { var b = e.bars_to_cross; return b != null ? L('~' + b + ' bars to cross', '约' + b + ' 根后交叉') : L('about to cross', '即将交叉'); }
    if (e.ticks != null) return e.ticks === 0 ? L('crossed this bar', '本根交叉') : L(e.ticks + ' tick' + (e.ticks > 1 ? 's' : '') + ' ago', e.ticks + ' 格前');
    return '';
  }
  function detailHref(ds, key) { var d = DS[ds]; return d.dir + d.prefix + key + '.html'; }
  function stockHref(tk) { return 'stock.html#' + encodeURIComponent(tk); }
  function groupsOf(ds) { return (DATA[ds] || {})[DS[ds].groupsKey] || []; }
  function wrapTbls(root) {
    if (!root) return;
    root.querySelectorAll('table').forEach(function (t) {
      if (t.closest('.tbl-scroll') || !t.parentNode) return;
      var w = document.createElement('div'); w.className = 'tbl-scroll';
      t.parentNode.insertBefore(w, t); w.appendChild(t);
    });
  }

  /* ══ VERDICT — the answer-first hero ═════════════════════════════════════════
     Rotation backdrop (macro regime + risk score) · confluence ribbon (whole
     universe split buy→avoid) · the single best-timed entry · honest coverage. */

  var CLASS_META = {
    entry_now: { seg: 'entry',    label: ['Entry now', '现可入场'],  col: 'var(--up)' },
    tailwind:  { seg: 'tailwind', label: ['Tailwind', '顺风'],       col: 'color-mix(in srgb,var(--up) 55%,var(--info))' },
    neutral:   { seg: 'neutral',  label: ['Neutral', '中性'],        col: 'var(--g-mid)' },
    late:      { seg: 'late',     label: ['Late', '偏晚'],           col: 'var(--orange)' },
    headwind:  { seg: 'headwind', label: ['Headwind', '逆风'],       col: 'var(--down)' }
  };
  var RIBBON_ORDER = ['entry_now', 'tailwind', 'neutral', 'late', 'headwind'];

  function universeStats(payload, ds) {
    var groups = groupsOf(ds);
    var counts = { entry_now: 0, tailwind: 0, neutral: 0, late: 0, headwind: 0 };
    groups.forEach(function (g) { var c = g['class']; if (counts[c] != null) counts[c]++; else counts.neutral++; });
    var entry = groups.filter(function (g) { return g['class'] === 'entry_now'; });
    var forming = (payload.forming || []);
    // best-timed entry: freshest / highest-weight entry_now, else the strongest tailwind by rs_60d.
    var best = entry.slice().sort(function (a, b) {
      var ta = (a.entry || {}).tier || 'Z', tb = (b.entry || {}).tier || 'Z';
      if (ta !== tb) return ta < tb ? -1 : 1;
      return ((b.entry || {}).weight || 0) - ((a.entry || {}).weight || 0);
    })[0];
    if (!best) {
      best = groups.filter(function (g) { return g['class'] === 'tailwind'; })
        .sort(function (a, b) { return ((b.regime || {}).rs_60d || -999) - ((a.regime || {}).rs_60d || -999); })[0];
    }
    var cov = payload.coverage || {};
    return { counts: counts, total: groups.length, entry: entry, forming: forming, best: best, bestIsEntry: !!(best && best['class'] === 'entry_now'), cov: cov };
  }

  // macro backdrop chips — shared across tabs (index_leadership macro + regime)
  function backdropChips() {
    if (!LEAD || !LEAD.ok) return '';
    var out = [];
    var reg = LEAD.regime;
    if (reg && (reg.name_en || reg.name_zh)) {
      var axes = reg.axes_en ? ' · <span style="color:var(--muted);font-weight:600">' + esc(reg.axes_en) + '</span>' : '';
      var axesZh = reg.axes_zh ? ' · <span style="color:var(--muted);font-weight:600">' + esc(reg.axes_zh) + '</span>' : '';
      out.push('<span class="bd-chip" title="' + esc((reg.tilt_en || '')) + '"><span class="bd-ic">◇</span>'
        + '<span class="l-en"><b>' + esc(reg.name_en || reg.name_zh) + '</b>' + axes + '</span>'
        + '<span class="l-zh"><b>' + esc(reg.name_zh || reg.name_en) + '</b>' + axesZh + '</span></span>');
    }
    var m = LEAD.macro;
    if (m && (m.label_en || m.verdict)) {
      var sev = (m.severity || '').indexOf('off') >= 0 ? 'bd-riskoff' : (m.severity === 'risk_on' || m.severity === 'risk-on') ? 'bd-riskon' : 'bd-mixed';
      var sc = m.score != null ? ' <span class="num">' + m.score + '</span>' : '';
      out.push('<span class="bd-chip ' + sev + '"><span class="bd-ic">●</span><b>' + L(esc(m.label_en || m.verdict), esc(m.label_zh || m.label_en || m.verdict)) + '</b>' + sc + '</span>');
    }
    return out.join('');
  }

  // breadth-of-leadership read for the prose — S&P uses the drivers.breadth ratio;
  // other tabs synthesise from the per-tab participation z-score.
  function breadthRead(ds) {
    if (LEAD && LEAD.drivers && Array.isArray(LEAD.drivers.ratios)) {
      var b = LEAD.drivers.ratios.filter(function (r) { return r.key === 'breadth'; })[0];
      if (ds === 'subsectors' && b && (b.read_en || b.read_zh)) return { en: b.read_en, zh: b.read_zh || b.read_en, up: !!b.rising };
    }
    var t = LEAD && LEAD.tabs && LEAD.tabs[ds];
    if (t && t.z_participation != null) {
      var up = t.z_participation >= 0;
      return { en: up ? 'participation is broadening — more members are joining the move' : 'participation is narrowing — fewer members carry the move',
        zh: up ? '参与度在扩散——更多成分加入行情' : '参与度在收窄——由更少成分支撑行情', up: up };
    }
    return null;
  }

  function verdictProse(stats, ds) {
    var m = LEAD && LEAD.macro, en = [], zh = [];
    // 1) backdrop
    if (m && (m.severity === 'risk_on' || m.severity === 'risk-on')) { en.push('<span class="accent-up">Risk-on backdrop</span>'); zh.push('<span class="accent-up">风险偏好背景</span>'); }
    else if (m && (m.severity || '').indexOf('off') >= 0) { en.push('<span class="accent-down">Risk-off backdrop</span>'); zh.push('<span class="accent-down">避险背景</span>'); }
    else if (m) { en.push('<b>Mixed backdrop</b>'); zh.push('<b>混合背景</b>'); }
    // 2) breadth
    var br = breadthRead(ds);
    if (br) { en.push(br.en); zh.push(br.zh); }
    var lead = en.length ? (en.join(' · ') + '. ') : '';
    var leadZh = zh.length ? (zh.join(' · ') + '。') : '';
    // 3) count + stance
    var c = stats.counts, tail = c.tailwind, e = c.entry_now, head = c.headwind + c.late;
    var body, bodyZh;
    if (e > 0) {
      body = '<b>' + e + '</b> group' + (e > 1 ? 's' : '') + ' just turned <span class="accent-up">buyable</span>' + (tail ? ' and <b>' + tail + '</b> more carry a tailwind' : '') + '. Entries have the wind at their back — confirm the group before chasing.';
      bodyZh = '<b>' + e + '</b> 个子行业刚转为<span class="accent-up">可买</span>' + (tail ? '，另有 <b>' + tail + '</b> 个处于顺风' : '') + '。入场有顺风——追涨前请先确认该组。';
    } else if (tail > 0) {
      body = 'No group is firing a <span class="accent-up">fresh entry</span> right now, but <b>' + tail + '</b> carry a tailwind — watch for the cross, don\'t force it.';
      bodyZh = '当前无子行业触发<span class="accent-up">新入场</span>，但有 <b>' + tail + '</b> 个处于顺风——等待交叉，不要勉强。';
    } else {
      body = 'No fresh entries and no tailwind groups — this is a <b>patience</b> tape' + (head ? ', with <span class="accent-down">' + head + '</span> group' + (head > 1 ? 's' : '') + ' late or fading' : '') + '. Wait for rotation to set up.';
      bodyZh = '既无新入场也无顺风组——这是需要<b>耐心</b>的行情' + (head ? '，其中 <span class="accent-down">' + head + '</span> 个偏晚或转弱' : '') + '。等待轮动成形。';
    }
    return '<div class="sc-hero-verdict">' + L(lead + body, leadZh + bodyZh) + '</div>';
  }

  function ribbonHTML(stats) {
    var c = stats.counts, total = 0;
    RIBBON_ORDER.forEach(function (k) { total += c[k]; });
    if (!total) return '';
    var segs = RIBBON_ORDER.map(function (k) {
      var n = c[k]; if (!n) return '';
      var meta = CLASS_META[k], pct = Math.max(n / total * 100, 5.5);
      var cls = 'sc-seg ' + meta.seg + (pct < 11 ? ' narrow' : '') + (pct < 8 ? ' tiny' : '');
      var idx = RIBBON_ORDER.indexOf(k);
      return '<div class="' + cls + '" style="flex:' + n + ' 1 0;animation-delay:' + (0.08 + idx * 0.09).toFixed(2) + 's" '
        + 'title="' + n + ' ' + meta.label[0] + '"><span class="sc-seg-n">' + n + '</span><span class="sc-seg-t">' + L(meta.label[0], meta.label[1]) + '</span></div>';
    }).join('');
    var legend = RIBBON_ORDER.filter(function (k) { return c[k]; }).map(function (k) {
      var meta = CLASS_META[k];
      return '<span><i style="background:' + meta.col + '"></i>' + L(meta.label[0], meta.label[1]) + ' <span class="num" style="color:var(--text)">' + c[k] + '</span></span>';
    }).join('');
    return '<div class="sc-ribbon-wrap">'
      + '<div class="sc-ribbon-label"><span class="t">' + L('Confluence spread', '汇聚分布') + '</span><span class="h">' + L(total + ' timed groups', total + ' 个已计时组') + '</span></div>'
      + '<div class="sc-ribbon">' + segs + '</div>'
      + '<div class="sc-ribbon-legend">' + legend + '</div></div>';
  }

  function bestEntryHTML(stats, ds) {
    var g = stats.best;
    if (!g) return '<div class="sc-best none"><span class="ar">◦</span><div class="bd"><span class="nm">' + L('No group is buyable right now', '当前无可买子行业') + '</span> <span class="why">— ' + L('the cleanest setups are still forming; watch the board below.', '最干净的形态仍在构筑；关注下方看板。') + '</span></div></div>';
    var r = g.regime || {}, e = g.entry || {};
    var avoid = r.side === 'avoid';
    var good = stats.bestIsEntry && !avoid;   // green beacon only when the freshest entry is also clean
    var why = r.signal_line ? esc(r.signal_line) : (r.action ? esc(r.action) : '');
    var href = g.chart_key ? detailHref(ds, g.key) : null;
    var nm = href ? '<a class="nm" href="' + href + '">' + esc(g.label) + '</a>' : '<span class="nm">' + esc(g.label) + '</span>';
    var tag = !stats.bestIsEntry ? L('Closest to buyable', '最接近可买')
      : avoid ? L('Freshest cross — but extended, confirm', '最新交叉——但已伸展，请确认')
      : L('Best-timed entry now', '当前最佳择时入场');
    var fresh = freshTxt(e);
    return '<div class="sc-best' + (good ? '' : ' none') + '"><span class="ar">▸</span><div class="bd">'
      + '<span style="font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)">' + tag + '</span><br>'
      + nm + ' ' + tierBadge(e.tier) + ' ' + regimePill(r)
      + (why ? '<br><span class="why">' + why + (fresh ? ' · ' : '') + '</span>' + (fresh ? '<span class="why">' + fresh + '</span>' : '') : '')
      + '</div></div>';
  }

  function heroSection(payload, ds) {
    var stats = universeStats(payload, ds);
    var e = stats.counts.entry_now;
    var cov = stats.cov;
    var honest = cov.n_gateable != null
      ? L('<span class="num">' + cov.n_gateable + '</span> of <span class="num">' + cov.n_subsectors + '</span> ' + DS[ds].noun[0] + ' have enough live data to time' + (cov.n_thin ? ' · <span class="num">' + cov.n_thin + '</span> thin (listed in the table, not timed)' : ''),
        '<span class="num">' + cov.n_gateable + '</span>/<span class="num">' + cov.n_subsectors + '</span> 个' + DS[ds].noun[1] + '有足够实时数据可计时' + (cov.n_thin ? ' · <span class="num">' + cov.n_thin + '</span> 个数据稀疏（列于表内，不计时）' : ''))
      : '';
    return '<div class="isle sc-hero">'
      + '<div class="sc-eyebrow"><span class="dot"></span><span class="lbl">' + L('Rotation read', '轮动读数') + '</span>'
      + '<span class="backdrop">' + backdropChips() + '</span></div>'
      + '<div class="sc-hero-grid">'
      + '<div class="sc-headline"><div class="big' + (e ? '' : ' zero') + '">' + e + '</div><div class="cap">' + L('Buyable now', '现可买') + '</div></div>'
      + ribbonHTML(stats)
      + '</div>'
      + verdictProse(stats, ds)
      + bestEntryHTML(stats, ds)
      + (honest ? '<div class="sc-honesty"><span>ℹ</span><span>' + honest + '</span></div>' : '')
      + '</div>';
  }

  /* ══ ACT — buy-ready | avoid board + double-confluence picks ══════════════════ */

  function behavesAsChip(g) {
    var bid = g.basket_id;
    var out = (g.members || []).filter(function (m) { var b = m.behaves_as; return b && b.conflict && b.home_id && b.home_id !== bid; });
    if (!out.length) return '';
    var title = out.map(function (m) { var b = m.behaves_as, h = (b.homes || []).filter(function (x) { return x.id === b.home_id; })[0]; return m.ticker + ' → ' + (b.home_label || b.home_id) + (h && h.corr20 != null ? ' (r20 ' + h.corr20.toFixed(2) + ')' : ''); }).join('; ');
    var en, zh;
    if (out.length === 1) { var b = out[0].behaves_as; en = esc(out[0].ticker) + ' behaves-as ' + esc(b.home_label || b.home_id); zh = esc(out[0].ticker) + ' 表现类同 ' + esc(b.home_label_zh || b.home_label || b.home_id); }
    else { en = out.length + ' names behave-as a peer basket'; zh = out.length + ' 只成分表现类同对应篮子'; }
    return '<span class="pill behavesas" title="' + esc(title) + '">↔ ' + L(en, zh) + '</span>';
  }

  // bilingual "why it's on the buy side" — synthesised from the entry state (entry.reason is
  // EN-only, so we build our own translated framing and keep the regime action for context).
  function entryRead(g) {
    var tier = (g.entry || {}).tier || '';
    if (g['class'] === 'entry_now') return L('Fresh ' + tier + ' entry — just crossed', '刚触发 ' + tier + ' 入场交叉');
    if (g['class'] === 'forming') return L('Forming — ' + tier + ', earliest & weakest', '构筑中——' + tier + '，最早最弱');
    return '';
  }
  function regimeAction(r) { return (r && (r.action || r.action_zh)) ? L(esc(r.action || r.action_zh), esc(r.action_zh || r.action)) : ''; }

  // a rich, "so-what"-first group card. Buy cards lead with the ENTRY read (why it's buy-ready)
  // and demote the regime action to context — flagged ⚠ when the group is extended / below trend,
  // so a fresh cross on an over-extended group reads honestly instead of contradicting the column.
  function gcardHTML(g, ds, side) {
    var e = g.entry || {}, r = g.regime || {};
    var col = side === 'avoid' ? (g['class'] === 'headwind' ? 'var(--down)' : 'var(--orange)')
      : (g['class'] === 'entry_now' ? 'var(--up)' : g['class'] === 'forming' ? 'var(--info)' : 'color-mix(in srgb,var(--up) 55%,var(--info))');
    var href = g.chart_key ? detailHref(ds, g.key) : '#';
    var avoid = r.side === 'avoid';
    var action = regimeAction(r);
    var sig = r.signal_line ? esc(r.signal_line) : '';
    var pills = regimePill(r) + (e.tier && g['class'] === 'entry_now' ? ' <span class="pill entry">' + L('ENTRY', '入场') + '</span>' : '') + behavesAsChip(g);
    var body;
    if (side === 'avoid') {
      body = action ? '<div class="g-act"><span class="lead">' + action + '</span></div>' : '';
    } else {
      var er = entryRead(g);
      body = (er ? '<div class="g-act"><span class="lead">' + er + '</span></div>' : '')
        + (action ? '<div class="g-act" style="margin-top:5px' + (avoid ? ';color:var(--orange)' : ';color:var(--muted)') + '">' + (avoid ? '⚠ ' : '') + action + '</div>' : '');
    }
    return '<a class="gcard" style="border-left-color:' + col + '" href="' + href + '">'
      + '<div class="g-top"><div><div class="g-nm">' + esc(g.label) + '</div>'
      + '<div class="g-sct">' + esc(g.sector) + ' · ' + (g.n_priced || g.n_members) + ' ' + L('names', '只') + '</div></div>' + tierBadge(e.tier) + '</div>'
      + '<div class="g-row">' + pills + ' <span class="g-fresh">' + freshTxt(e) + '</span></div>'
      + body
      + (sig ? '<div class="g-sig">' + sig + '</div>' : '')
      + '</a>';
  }

  function boardSection(payload, ds) {
    var groups = groupsOf(ds);
    var noun = DS[ds].noun;
    var buy = groups.filter(function (g) { return g['class'] === 'entry_now'; });
    var forming = (payload.forming || []);
    var avoid = groups.filter(function (g) { return g['class'] === 'headwind' || g['class'] === 'late'; })
      .sort(function (a, b) { return (a['class'] === 'headwind' ? 0 : 1) - (b['class'] === 'headwind' ? 0 : 1); });

    var buyCol = '<div class="sc-col"><div class="sc-colhead"><span class="pip buy"></span>' + L('Buy-ready — just turned', '可买——刚转向') + ' <span class="n">' + buy.length + '</span></div>';
    buyCol += buy.length ? '<div class="gcards">' + buy.map(function (g) { return gcardHTML(g, ds, 'buy'); }).join('') + '</div>'
      : '<div class="empty">' + L('No ' + noun[0] + ' is firing a fresh entry tier right now. When one crosses, it lands here first.', '当前无' + noun[1] + '触发新的入场层级。一旦有交叉，将最先显示于此。') + '</div>';
    if (forming.length) {
      buyCol += '<div style="margin-top:11px;font-size:11px;color:var(--muted)">' + L('Also forming (T4 — earliest, weakest)', '构筑中（T4 — 最早、最弱）') + ' <span class="num">' + forming.length + '</span></div>'
        + '<div class="gcards" style="margin-top:6px">' + forming.slice(0, 4).map(function (g) { return gcardHTML(g, ds, 'buy'); }).join('') + '</div>';
    }
    buyCol += '</div>';

    var avoidCol = '<div class="sc-col"><div class="sc-colhead"><span class="pip avoid"></span>' + L('Don\'t chase — late or fading', '勿追——偏晚或转弱') + ' <span class="n">' + avoid.length + '</span></div>';
    avoidCol += avoid.length ? '<div class="gcards">' + avoid.slice(0, 8).map(function (g) { return gcardHTML(g, ds, 'avoid'); }).join('') + '</div>'
      + (avoid.length > 8 ? '<div style="margin-top:8px;font-size:11px;color:var(--muted)">' + L('+ ' + (avoid.length - 8) + ' more in the full table below', '+ 另有 ' + (avoid.length - 8) + ' 个见下方完整表格') + '</div>' : '')
      : '<div class="empty">' + L('Nothing extended or in a downtrend right now — no obvious groups to avoid.', '当前无过热或下行趋势的组——暂无明显应回避者。') + '</div>';
    avoidCol += '</div>';

    return '<div class="sec sc-stagger sc-s1"><div class="sec-head"><h2>🎯 ' + L('What to do now', '当下操作') + '</h2></div>'
      + '<div class="desc">' + L('Fresh T1–T3 confluence crosses on the left (buy-ready); groups that are overbought or below trend on the right (don\'t chase). The detail page shows each group\'s chart and which members are firing.',
        '左侧为新触发的 T1–T3 汇聚交叉（可买）；右侧为超买或跌破趋势的组（勿追）。详情页展示各组图表与触发成分。') + '</div>'
      + '<div class="sc-board">' + buyCol + avoidCol + '</div></div>';
  }

  var PICKS_CAP = 12;
  function picksSection(payload, ds) {
    var dg = payload.double_gated || {};
    var buys = (dg.double_buy || []).slice().sort(function (a, b) { return (b.combined_score || 0) - (a.combined_score || 0); });
    var maxs = Math.max.apply(null, [0.01].concat(buys.map(function (r) { return r.combined_score || 0; })));
    var rows = buys.map(function (r, i) {
      var w = Math.round(54 * (r.combined_score || 0) / maxs);
      return '<tr' + (i >= PICKS_CAP ? ' class="sc-xtra"' : '') + '><td class="tk"><a href="' + stockHref(r.ticker) + '">' + esc(r.ticker) + '</a></td>'
        + '<td>' + tierBadge(r.stock_tier) + '</td>'
        + '<td><a href="' + detailHref(ds, r.subsector_key) + '" style="color:var(--link)">' + esc(r.subsector) + '</a> <span class="pill ' + (r.subsector_side || 'neutral') + '">' + esc(r.subsector_state) + '</span></td>'
        + '<td class="num">' + (r.combined_score == null ? '–' : r.combined_score.toFixed(2)) + '<span class="scbar" style="width:' + w + 'px"></span></td>'
        + '<td>' + signed(r.vs_subsector_20d) + '</td></tr>';
    }).join('');
    var table = '<table class="sc-tbl"><thead><tr><th>' + L('Stock', '个股') + '</th><th>' + L('Its tier', '个股层级') + '</th><th>' + L('Inside subsector', '所在子行业') + '</th><th>' + L('Conviction', '综合把握') + '</th><th>' + L('vs sub 20d', '相对子行业20日') + '</th></tr></thead><tbody>' + rows + '</tbody></table>';
    var body;
    if (!buys.length) body = '<div class="empty">' + L('No double-confluence buys right now — no stock is firing its own entry inside a tailwind subsector.', '当前无双重汇聚买入——无个股在顺风子行业内触发自身入场。') + '</div>';
    else if (buys.length <= PICKS_CAP) body = table;
    else body = '<div class="sc-collapse sc-collapsed" data-n="' + buys.length + '" data-cap="' + PICKS_CAP + '">' + table
      + '<button class="sc-more" type="button"><span class="l-en">Show all ' + buys.length + ' picks ▾</span><span class="l-zh">展开全部 ' + buys.length + ' 个 ▾</span></button></div>';
    return '<div class="sec sc-stagger sc-s2"><div class="sec-head"><h2>💠 ' + L('Double-confluence picks', '双重汇聚精选') + ' <span class="n">' + buys.length + '</span></h2></div>'
      + '<div class="desc">' + L('Stocks whose own T1–T4 cascade is buyable <b>and</b> whose subsector has a tailwind — the two gates agree. Ranked by conviction = stock weight × subsector buyability (T1×T1 = 1.0)' + (buys.length > PICKS_CAP ? '. Top ' + PICKS_CAP + ' shown.' : '.'),
        '自身 T1–T4 级联可买<b>且</b>所在子行业顺风的个股——两道闸门一致。按把握度排序 = 个股权重 × 子行业可买系数（T1×T1 = 1.0）' + (buys.length > PICKS_CAP ? '，默认显示前 ' + PICKS_CAP + ' 个。' : '。')) + '</div>'
      + '<div class="sc-tablecard">' + body + '</div></div>';
  }

  /* ══ EXPLORE — leadership, sector backdrop, internals, full table ═════════════ */

  function quadInfo(q) { return ({ leading: ['Leading', '领先', 'var(--up)'], improving: ['Improving', '改善', 'var(--info)'], weakening: ['Weakening', '走弱', 'var(--orange)'], lagging: ['Lagging', '落后', 'var(--down)'] })[q] || ['—', '—', 'var(--muted)']; }
  function quadPill(q) { var i = quadInfo(q); return '<span class="qp" style="color:' + i[2] + ';border-color:' + i[2] + '">' + L(i[0], i[1]) + '</span>'; }
  function stageBadge(st) { var m = ({ primed: ['Primed', '就绪', 'var(--up)'], coiling: ['Coiling', '蓄势', 'var(--info)'], watch: ['Watch', '观察', 'var(--muted)'], knife: ['Knife', '刀口', 'var(--down)'] })[st] || ['—', '—', 'var(--muted)']; return '<span class="qp" style="color:' + m[2] + ';border-color:' + m[2] + '">' + L(m[0], m[1]) + '</span>'; }
  function tfChip(lbl, dir) { var c = dir === 'up' ? 'var(--up)' : dir === 'down' ? 'var(--down)' : 'var(--muted)'; var a = dir === 'up' ? '▲' : dir === 'down' ? '▼' : dir === 'flat' ? '–' : '·'; return '<span class="tfc" style="color:' + c + '">' + lbl + ' ' + a + '</span>'; }

  function leadCard(e) {
    var qi = quadInfo(e.quadrant), co = e.coil;
    var head = '<div class="lc-top"><span class="lc-nm">' + esc(e.label) + '</span>' + (e.entry_tier ? tierBadge(e.entry_tier) : '') + '</div><div class="lc-sub">' + esc(e.sector || '') + '</div>';
    if (co) {
      var tf = co.tf || {};
      var chips = ['W', '2W', 'M'].map(function (k) { return tfChip(k, tf[k]); }).join(' ');
      return '<div class="lcard" style="border-left-color:' + qi[2] + '">' + head
        + '<div class="lc-row">' + stageBadge(co.stage) + ' <span class="pill ' + (e.regime_side || 'neutral') + '">' + esc(e.regime_state || '—') + '</span></div>'
        + '<div class="lc-tf">' + L('higher TF', '更高周期') + ': ' + chips + (co.htf_turning ? ' <span style="color:var(--up)">' + L('confirming', '确认中') + '</span>' : '') + '</div>'
        + '<div class="lc-meta">' + L('coil', '蓄势') + ' ' + num(co.coil_score, 0) + '/100' + (e.rs_60d != null ? ' · RS60 ' + signed(e.rs_60d, 1) : '') + '</div>'
        + (co.macro_caution ? '<div class="lc-macro">⚠ ' + L('macro risk-off — confirm the tape', '宏观避险——请确认大盘') + '</div>' : '') + '</div>';
    }
    return '<div class="lcard" style="border-left-color:' + qi[2] + '">' + head
      + '<div class="lc-row">' + quadPill(e.quadrant) + ' <span class="pill ' + (e.regime_side || 'neutral') + '">' + esc(e.regime_state || '—') + '</span></div>'
      + '<div class="lc-meta">' + L('accel', '加速') + ' ' + signed(e.emerging_score, 2) + (e.rs_60d != null ? ' · RS60 ' + signed(e.rs_60d, 1) : '') + '</div></div>';
  }

  function leadershipSection(ds) {
    if (!LEAD || !LEAD.ok || !LEAD.tabs[ds]) return '';
    var t = LEAD.tabs[ds], run = t.rising || [], coil = t.coiling || [];
    if (!run.length && !coil.length) return '';
    var col = function (icon, ten, tzh, den, dzh, list, een, ezh, note) {
      return '<div class="lead-col"><div class="sc-colhead" style="margin-bottom:6px">' + icon + ' ' + L(ten, tzh) + ' <span class="n">' + list.length + '</span></div>'
        + '<div class="desc" style="margin-bottom:8px">' + L(den, dzh) + '</div>'
        + (list.length ? '<div class="lcards">' + list.map(leadCard).join('') + '</div>' : '<div class="empty">' + L(een, ezh) + '</div>') + (note || '') + '</div>';
    };
    var filtered = t.coil_filtered || 0;
    var coilNote = filtered ? '<div class="lc-filtered">⛔ ' + L(filtered + ' more dropped by the weekly / 2-week / monthly downtrend veto (a bounce inside a higher-timeframe bear — not a durable coil).', filtered + ' 个被周/双周/月线下跌否决过滤（更高周期熊市中的反弹——非可持续蓄势）。') + '</div>' : '';
    return '<div class="sec sc-stagger sc-s3"><div class="sec-head"><h2>🌀 ' + L('Leadership — running & coiling', '领导地位——领跑与蓄势') + '</h2></div>'
      + '<div class="lead-cols">'
      + col('🏃', 'Running — rising leaders', '领跑——上升领导',
        'Already leading their peers and still accelerating (RRG leading quadrant, not topping). Ranked by acceleration, not level.',
        '已领先同侪且仍在加速（RRG 领先象限，未见顶）。按加速度而非水平排序。',
        run, 'None accelerating cleanly in the leading quadrant.', '领先象限中暂无干净加速者。')
      + col('🌱', 'Coiling — about to run', '蓄势——即将启动',
        'Laggards turning up that pass a coil confirmation (RSI divergence, multi-timeframe turn, volatility contraction, RS-hold) and survive a weekly / 2-week / monthly downtrend veto. W/2W/M chips show the higher-timeframe trend.',
        '开始转强的落后组，通过蓄势确认（RSI 背离、多周期转向、波动收缩、相对强弱守稳）并通过周/双周/月线下跌否决。W/2W/M 标签显示更高周期趋势。',
        coil, 'No laggards passed higher-timeframe coil confirmation.', '暂无落后组通过更高周期蓄势确认。', coilNote)
      + '</div></div>';
  }

  function sectorStrip(payload, ds) {
    var meta = DS[ds].rollup;
    if (!meta) return '';
    var secs = payload.sectors || [];
    if (!secs.length) return '';
    var cells = secs.map(function (g) {
      var r = g.regime || {};
      var href = g.chart_key ? detailHref(ds, g.key) : null;
      var inner = '<div class="snm">' + esc(g.label) + '</div><div style="margin-top:5px">' + regimePill(r) + (g.entry && g.entry.tier ? ' ' + tierBadge(g.entry.tier) : '') + '</div>'
        + (r.rs_60d != null ? '<div style="color:var(--muted);font-size:10.5px;margin-top:4px" class="num">RS60 ' + signed(r.rs_60d) + '</div>' : '');
      return href ? '<a class="s" href="' + href + '">' + inner + '</a>' : '<div class="s">' + inner + '</div>';
    }).join('');
    return '<div class="sec sc-stagger sc-s4"><div class="sec-head"><h2>🗺️ ' + L(meta[0], meta[1]) + '</h2></div><div class="desc">' + L(DS[ds].rollupDesc[0], DS[ds].rollupDesc[1]) + '</div><div class="secstrip">' + cells + '</div></div>';
  }

  /* nasdaq internals archetype panel (TI-R4) — display-only, fail-open. */
  var NI_STATE_COLORS = { leading: 'var(--up)', improving: 'var(--info)', weakening: 'var(--orange)', lagging: 'var(--down)' };
  var NI_STATE_LABELS = { leading: ['Leading', '领先'], improving: ['Improving', '改善'], weakening: ['Weakening', '走弱'], lagging: ['Lagging', '落后'] };
  function niStateBadge(state, days) {
    var info = NI_STATE_LABELS[state];
    if (!info) return '<span class="qp" style="color:var(--muted);border-color:var(--muted)">—</span>';
    var col = NI_STATE_COLORS[state] || 'var(--muted)';
    var dayTxt = (days != null && days > 0) ? ' <span style="color:var(--muted);font-size:10px" class="num">' + days + 'd</span>' : '';
    return '<span class="qp" style="color:' + col + ';border-color:' + col + '">' + L(info[0], info[1]) + '</span>' + dayTxt;
  }
  function niVal(x, d, suffix) { if (x == null || (typeof x === 'number' && isNaN(x))) return '–'; return Number(x).toFixed(d == null ? 1 : d) + (suffix || ''); }
  function nasdaqInternalsPanel() {
    try {
      var d = NIDATA;
      if (!d || typeof d !== 'object' || d.schema !== 'nasdaq_internals.v1') return '';
      var groups = d.groups, ewqqq = d.ew_vs_qqq || {}, divs = d.divergences || [];
      function spreadSpan(v) { if (v == null || isNaN(v)) return '<span class="num">–</span>'; var n = Number(v); return '<span class="num ' + (n >= 0 ? 'pos' : 'neg') + '">' + (n >= 0 ? '+' : '') + n.toFixed(2) + 'pp</span>'; }
      var ewHtml = '<div class="ni-ew-chip"><span style="font-weight:700">' + L('EW vs QQQ', '等权 vs QQQ') + '</span> &nbsp;20d ' + spreadSpan(ewqqq.spread_20d) + ' &nbsp;60d ' + spreadSpan(ewqqq.spread_60d)
        + (ewqqq.pctile_1y != null ? ' &nbsp;<span style="color:var(--muted);font-size:11px">' + L('1y %ile', '1年百分位') + ' ' + niVal(ewqqq.pctile_1y, 0, '%') + '</span>' : '')
        + (ewqqq.n_members ? ' &nbsp;<span style="color:var(--muted);font-size:10.5px">n=' + ewqqq.n_members + '</span>' : '') + '</div>';
      var groupCells = Array.isArray(groups) ? groups.map(function (g) {
        return '<div class="s"><div class="snm">' + L(esc(g.label_en || g.id), esc(g.label_zh || g.id)) + '</div>'
          + '<div style="margin-top:5px">' + niStateBadge(g.state, g.state_days) + '</div>'
          + '<div style="color:var(--muted);font-size:10.5px;margin-top:4px" class="num">RS20 ' + signed(g.rs_20d, 1) + ' &nbsp;RS60 ' + signed(g.rs_60d, 1) + '</div>'
          + '<div style="color:var(--muted);font-size:10px;margin-top:2px" class="num">' + L('Breadth', '宽度') + ' ' + (g.breadth_above_50dma != null ? niVal(g.breadth_above_50dma, 0, '%') : '–') + ' &nbsp;' + L('Disp', '离散') + ' ' + (g.dispersion_20d != null ? niVal(g.dispersion_20d, 1) : '–') + '</div>'
          + '<div style="color:var(--muted);font-size:10px;margin-top:2px" class="num">' + L('Accel', '加速') + ' ' + (g.accel != null ? signed(g.accel, 2) : '–') + ' &nbsp;n=' + (g.n != null ? g.n : '–') + '</div></div>';
      }).join('') : '';
      var groupStrip = groupCells ? '<div class="secstrip" style="margin-top:8px">' + groupCells + '</div>' : '<div class="empty">' + L('Group data unavailable.', '组数据暂不可用。') + '</div>';
      var divHtml = '';
      if (divs.length) {
        var divRows = divs.map(function (dv) {
          var pair = Array.isArray(dv.pair) ? dv.pair.join(' / ') : '—';
          return '<tr><td style="color:var(--muted);white-space:normal">' + esc(pair) + '</td><td>' + (dv.gap_accel_z != null ? signed(dv.gap_accel_z, 2) : '<span class="num">–</span>') + '</td><td style="color:var(--muted);white-space:normal">' + L(esc(dv.note_en || ''), esc(dv.note_zh || '')) + '</td></tr>';
        }).join('');
        divHtml = '<div style="margin-top:14px"><div style="font-weight:700;font-size:12.5px;margin-bottom:6px">' + L('Divergences', '背离对') + '</div><table class="sc-tbl"><thead><tr><th>' + L('Pair', '组合') + '</th><th>' + L('Gap Accel Z', '差距加速Z') + '</th><th>' + L('Note', '说明') + '</th></tr></thead><tbody>' + divRows + '</tbody></table></div>';
      }
      var wm = L(esc(d.watermark_en || ''), esc(d.watermark_zh || ''));
      var footHtml = '<div style="color:var(--muted);font-size:11px;margin-top:10px;line-height:1.5">' + (d.watermark_en ? wm + ' &nbsp;·&nbsp; ' : '') + L('Descriptive, display-only — no forward claim.', '描述性，仅供展示——不构成前瞻性主张。') + '</div>';
      return '<div class="sec sc-stagger sc-s5"><div class="sec-head"><h2>📊 ' + L('Nasdaq internals', '纳斯达克内部结构') + '</h2></div>'
        + '<div class="desc">' + L('Archetype group breadth and momentum vs QQQ. Descriptive only — no forward claim.', '各原型组相对 QQQ 的宽度与动量。仅描述性，不构成前瞻性主张。') + '</div>'
        + ewHtml + groupStrip + divHtml + footHtml + '</div>';
    } catch (e) { console.debug('[ni-panel] render error (artifact may be absent):', e && e.message); return ''; }
  }

  /* full searchable + sortable table of every group. */
  var FULL_COLS = [
    { k: 'label', t: ['Subsector', '子行业'], num: false },
    { k: 'sector', t: ['Sector', '板块'], num: false },
    { k: 'tier', t: ['Entry', '入场'], num: false },
    { k: 'state', t: ['Regime', '状态'], num: false },
    { k: 'fresh', t: ['Freshness', '新鲜度'], num: false },
    { k: 'rs60', t: ['RS60', 'RS60'], num: true },
    { k: 'n', t: ['N', '数'], num: true }
  ];
  function fullRowVals(g) {
    var e = g.entry || {}, r = g.regime || {};
    return { label: g.label || '', sector: g.sector || '', tier: e.tier || '', state: r.label || r.state || '', fresh: e.ticks != null ? e.ticks : (e.bars_to_cross != null ? 100 + e.bars_to_cross : 999), rs60: r.rs_60d, n: g.n_priced || g.n_members || 0, _g: g, _e: e, _r: r };
  }
  function fullTableSection(payload, ds) {
    var groups = groupsOf(ds).slice();
    var noun = DS[ds].noun;
    var s = SORT[ds] || { col: 'tier', dir: 1 };
    var q = (FILTER[ds] || '').toLowerCase();
    var rowsData = groups.map(fullRowVals);
    if (q) rowsData = rowsData.filter(function (v) { return (v.label + ' ' + v.sector).toLowerCase().indexOf(q) >= 0; });
    rowsData.sort(function (a, b) {
      var col = s.col, av = a[col], bv = b[col];
      if (col === 'tier') { av = av || 'Z'; bv = bv || 'Z'; }
      if (av == null) av = s.dir === 1 ? Infinity : -Infinity;
      if (bv == null) bv = s.dir === 1 ? Infinity : -Infinity;
      if (typeof av === 'string') { av = av.toLowerCase(); bv = (bv || '').toString().toLowerCase(); return av < bv ? -s.dir : av > bv ? s.dir : 0; }
      return (av - bv) * s.dir;
    });
    var thead = '<tr>' + FULL_COLS.map(function (c) {
      var on = s.col === c.k;
      return '<th class="sortable' + (on ? ' sorted' : '') + '" data-col="' + c.k + '">' + L(c.t[0], c.t[1]) + ' <span class="arr">' + (on ? (s.dir === 1 ? '▲' : '▼') : '⇅') + '</span></th>';
    }).join('') + '</tr>';
    var body = rowsData.map(function (v) {
      var g = v._g, e = v._e, r = v._r;
      return '<tr><td><a href="' + (g.chart_key ? detailHref(ds, g.key) : '#') + '" style="color:var(--link)">' + esc(g.label) + '</a> ' + relDot(g.reliability) + '</td>'
        + '<td style="color:var(--muted)">' + esc(g.sector) + '</td>'
        + '<td>' + tierBadge(e.tier) + '</td>'
        + '<td>' + regimePill(r) + '</td>'
        + '<td style="color:var(--muted);font-size:11px">' + (freshTxt(e) || '') + '</td>'
        + '<td>' + signed(r.rs_60d) + '</td>'
        + '<td class="num">' + (g.n_priced || g.n_members) + '</td></tr>';
    }).join('');
    return '<div class="sec sc-stagger sc-s6"><div class="sec-head"><h2>📋 ' + L('All ' + noun[0], '全部' + noun[1]) + ' <span class="n">' + groups.length + '</span></h2></div>'
      + '<div class="sc-tablecard"><div class="sc-search"><span style="color:var(--muted)">🔎</span>'
      + '<input type="text" id="sc-fulltable-q" placeholder="' + (document.documentElement.getAttribute('data-lang') === 'zh' ? '筛选子行业或板块…' : 'Filter subsector or sector…') + '" value="' + esc(FILTER[ds] || '') + '">'
      + '<span class="cnt">' + rowsData.length + ' / ' + groups.length + '</span></div>'
      + '<div class="tbl-scroll"><table class="sc-tbl" id="sc-fulltable"><thead>' + thead + '</thead><tbody>' + body + '</tbody></table></div></div></div>';
  }

  /* ══ render + wiring ═════════════════════════════════════════════════════════ */

  function render() {
    var app = document.getElementById('sc-app');
    var ds = TAB;
    var payload = DATA[ds];
    if (!payload || !payload.ok) { app.innerHTML = '<div class="empty">' + L('No data yet — run the nightly build.', '暂无数据——请运行夜间构建。') + '</div>'; return; }
    var cov = payload.coverage || {};
    document.getElementById('sc-asof').innerHTML = L('as of ' + (payload.as_of || '—'), '截至 ' + (payload.as_of || '—'));
    var niSection = (ds === 'nasdaq') ? nasdaqInternalsPanel() : '';
    app.innerHTML = heroSection(payload, ds)
      + boardSection(payload, ds)
      + picksSection(payload, ds)
      + leadershipSection(ds)
      + sectorStrip(payload, ds)
      + niSection
      + fullTableSection(payload, ds);
    wrapTbls(app);
  }

  function setTab(tab) {
    TAB = tab;
    Array.prototype.forEach.call(document.querySelectorAll('.sc-tab'), function (el) { el.classList.toggle('on', el.getAttribute('data-tab') === tab); });
    render();
  }

  // delegated handlers on #sc-app: "show all" toggle, sort headers + live table filter.
  function onAppClick(e) {
    var more = e.target.closest ? e.target.closest('.sc-more') : null;
    if (more) {
      var box = more.closest('.sc-collapse');
      if (box) {
        var open = box.classList.toggle('sc-collapsed') === false;
        more.innerHTML = open ? '<span class="l-en">Show fewer ▴</span><span class="l-zh">收起 ▴</span>'
          : '<span class="l-en">Show all ' + box.getAttribute('data-n') + ' picks ▾</span><span class="l-zh">展开全部 ' + box.getAttribute('data-n') + ' 个 ▾</span>';
      }
      return;
    }
    var th = e.target.closest ? e.target.closest('th.sortable') : null;
    if (!th) return;
    var col = th.getAttribute('data-col'), s = SORT[TAB] || { col: 'tier', dir: 1 };
    SORT[TAB] = { col: col, dir: s.col === col ? -s.dir : (col === 'label' || col === 'sector' ? 1 : (col === 'rs60' || col === 'n') ? -1 : 1) };
    render();
  }
  function onAppInput(e) {
    if (!e.target || e.target.id !== 'sc-fulltable-q') return;
    FILTER[TAB] = e.target.value || '';
    var pos = e.target.selectionStart;
    render();
    var again = document.getElementById('sc-fulltable-q');
    if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (x) {} }
  }

  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll('.sc-tab'), function (el) {
      el.addEventListener('click', function () { setTab(el.getAttribute('data-tab')); });
    });
    var appEl = document.getElementById('sc-app');
    if (appEl) { appEl.addEventListener('click', onAppClick); appEl.addEventListener('input', onAppInput); }
    var keys = Object.keys(DS);
    Promise.all(keys.map(function (k) {
      return fetch(DS[k].url, { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    })).then(function (res) {
      keys.forEach(function (k, i) { DATA[k] = res[i]; });
      var cnt = function (k) { var p = DATA[k]; return p ? (p[DS[k].groupsKey] || []).length : 0; };
      var set = function (id, v) { var el = document.getElementById(id); if (el) el.textContent = v; };
      set('tabn-sub', cnt('subsectors')); set('tabn-bas', cnt('baskets'));
      set('tabn-ndx', cnt('nasdaq')); set('tabn-rut', cnt('russell'));
      return fetch('marketdata/index_leadership.json', { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    }).then(function (lead) {
      LEAD = lead;
      if (LEAD && LEAD.ok && LEAD.rising_star) {
        var el = document.querySelector('.sc-tab[data-tab="' + LEAD.rising_star.tab + '"]');
        if (el && !el.querySelector('.star-badge')) { var b = document.createElement('span'); b.className = 'star-badge'; b.textContent = '⭐'; b.title = 'Rising star — leadership accelerating fastest'; el.appendChild(b); }
      }
      return fetch('marketdata/nasdaq_internals.json', { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    }).then(function (ni) {
      try { if (ni && ni.schema === 'nasdaq_internals.v1') NIDATA = ni; } catch (e) {}
      render();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();

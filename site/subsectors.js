/* Subsector Confluence desk — renders the ENTRY-NOW board + double-gated funnel from the
   precomputed engine JSON. Four datasets share one render path:
     subsectors — S&P-500 Finviz sub-industries  (marketdata/subsector_confluence.json)
     baskets    — curated thematic baskets        (marketdata/basket_confluence.json)
     nasdaq     — Nasdaq-100 sub-industries        (marketdata/subsector_confluence_nasdaq.json)
     russell    — Russell-2000 sub-industries      (marketdata/subsector_confluence_russell.json)
   Vanilla JS, no deps. Bilingual via .l-en/.l-zh spans (theme.js toggles by html[data-lang]). */
(function () {
  'use strict';
  var L = function (en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh == null ? en : zh) + '</span>'; };

  // dataset registry — url, detail-page dir + key prefix, the group array key, and whether the
  // dataset carries an amalgamation/sector rollup strip + what to call it.
  var DS = {
    subsectors: { url: 'marketdata/subsector_confluence.json', dir: 'subsector/', prefix: '', groupsKey: 'subsectors', noun: ['subsectors', '子行业'], rollup: ['Sector rollup', '板块汇总'], rollupDesc: ['Each sector as one equal-weight basket — the backdrop the subsectors live inside.', '每个 板块作为一个等权篮子——子行业所处的大背景。'] },
    baskets: { url: 'marketdata/basket_confluence.json', dir: 'subsector/', prefix: 'b-', groupsKey: 'baskets', noun: ['baskets', '篮子'], rollup: null },
    nasdaq: { url: 'marketdata/subsector_confluence_nasdaq.json', dir: 'subsector_nasdaq/', prefix: '', groupsKey: 'subsectors', noun: ['subsectors', '子行业'], rollup: ['Amalgamated complexes', '汇聚综合体'], rollupDesc: ['Higher-level complexes (semis, software, internet, the ex-tech bucket) — watch whether leadership rotates among them or bleeds out of tech. RS is vs QQQ (within-index).', '高层级综合体（半导体、软件、互联网、非科技桶）——观察领导地位是在它们之间轮动还是流出科技。相对强弱基准为 QQQ（指数内）。'] },
    russell: { url: 'marketdata/subsector_confluence_russell.json', dir: 'subsector_russell/', prefix: '', groupsKey: 'subsectors', noun: ['subsectors', '子行业'], rollup: ['Sector amalgamations', '板块汇聚'], rollupDesc: ['The 11 sectors as equal-weight baskets — the natural small-cap rotation buckets. RS is vs IWM (within-index).', '11 个 板块作为等权篮子——小盘股自然的轮动桶。相对强弱基准为 IWM（指数内）。'] }
  };
  var DATA = {};
  var TAB = 'subsectors';
  var NIDATA = null;  // nasdaq_internals.v1 payload (may be null when artifact not yet built)

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function num(x, d) { return (x == null || isNaN(x)) ? '–' : Number(x).toFixed(d == null ? 0 : d); }
  function signed(x, d) { if (x == null || isNaN(x)) return '<span class="num">–</span>'; var v = Number(x); return '<span class="num ' + (v >= 0 ? 'pos' : 'neg') + '">' + (v >= 0 ? '+' : '') + v.toFixed(d == null ? 1 : d) + '</span>'; }
  function tierBadge(t) { return '<span class="tier ' + (t || 'none') + '">' + (t || '—') + '</span>'; }
  function regimePill(r) { var side = (r && r.side) || 'neutral'; return '<span class="pill ' + side + '">' + esc((r && r.label) || (r && r.state) || '—') + '</span>'; }
  function freshTxt(e) {
    if (!e) return '';
    if (e.tier === 'T3' || e.tier === 'T4') { var b = e.bars_to_cross; return b != null ? L('~' + b + ' bars to cross', '约' + b + ' 根后交叉') : L('about to cross', '即将交叉'); }
    if (e.ticks != null) return e.ticks === 0 ? L('crossed this bar', '本根交叉') : L(e.ticks + ' tick' + (e.ticks > 1 ? 's' : '') + ' ago', e.ticks + ' 格前'); // 1 tick = 3 days on 3D
    return '';
  }
  // `key` is the RAW group slug (g.key / row.subsector_key); detailHref applies the dataset's
  // detail dir + key prefix (the curated baskets carry the 'b-' namespace). Never pass
  // g.chart_key here — it is already the namespaced detail key.
  function detailHref(ds, key) { var d = DS[ds]; return d.dir + d.prefix + key + '.html'; }
  function stockHref(tk) { return 'stock.html#' + encodeURIComponent(tk); }
  function groupsOf(ds) { return (DATA[ds] || {})[DS[ds].groupsKey] || []; }

  /* ----- index leadership data — per-tab running / coiling + the rising-star tab badge
     (the full leadership-rotation scorecard was moved to sector_central.html) ----- */
  var LEAD = null;
  function quadInfo(q) { return ({ leading: ['Leading', '领先', 'var(--up)'], improving: ['Improving', '改善', 'var(--info)'], weakening: ['Weakening', '走弱', 'var(--orange)'], lagging: ['Lagging', '落后', 'var(--down)'] })[q] || ['—', '—', 'var(--muted)']; }
  function quadPill(q) { var i = quadInfo(q); return '<span class="qp" style="color:' + i[2] + ';border-color:' + i[2] + '">' + L(i[0], i[1]) + '</span>'; }
  function stageBadge(st) { var m = ({ primed: ['Primed', '就绪', 'var(--up)'], coiling: ['Coiling', '蓄势', 'var(--info)'], watch: ['Watch', '观察', 'var(--muted)'], knife: ['Knife', '刀口', 'var(--down)'] })[st] || ['—', '—', 'var(--muted)']; return '<span class="qp" style="color:' + m[2] + ';border-color:' + m[2] + '">' + L(m[0], m[1]) + '</span>'; }
  function tfChip(lbl, dir) { var c = dir === 'up' ? 'var(--up)' : dir === 'down' ? 'var(--down)' : 'var(--muted)'; var a = dir === 'up' ? '▲' : dir === 'down' ? '▼' : dir === 'flat' ? '–' : '·'; return '<span class="tfc" style="color:' + c + '">' + lbl + ' ' + a + '</span>'; }
  // theme.js wrapTables() runs on DOMContentLoaded, BEFORE this file async-injects its tables,
  // so our tables never get the .tbl-scroll wrapper and bleed past the viewport on mobile.
  // Re-apply the house wrap (theme.css styles .tbl-scroll) to any table we render.
  function wrapTbls(root) {
    if (!root) return;
    root.querySelectorAll('table').forEach(function (t) {
      if (t.closest('.tbl-scroll') || !t.parentNode) return;
      var w = document.createElement('div'); w.className = 'tbl-scroll';
      t.parentNode.insertBefore(w, t); w.appendChild(t);
    });
  }

  function leadCard(e) {
    var qi = quadInfo(e.quadrant), co = e.coil;
    var head = '<div class="lc-top"><span class="lc-nm">' + esc(e.label) + '</span>' + (e.entry_tier ? tierBadge(e.entry_tier) : '') + '</div>'
      + '<div class="lc-sub">' + esc(e.sector || '') + '</div>';
    if (co) {  // COILING card — show coil stage + the higher-timeframe (W/2W/M) trend the veto reads
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

  function tabLeadership(ds) {
    if (!LEAD || !LEAD.ok || !LEAD.tabs[ds]) return '';
    var t = LEAD.tabs[ds], run = t.rising || [], coil = t.coiling || [];
    var col = function (icon, ten, tzh, den, dzh, list, een, ezh, note) {
      return '<div class="lead-col"><h2>' + icon + ' ' + L(ten, tzh) + ' <span class="n" style="color:var(--muted);font-weight:500">' + list.length + '</span></h2>'
        + '<div class="desc">' + L(den, dzh) + '</div>'
        + (list.length ? '<div class="lcards">' + list.map(leadCard).join('') + '</div>' : '<div class="empty">' + L(een, ezh) + '</div>')
        + (note || '') + '</div>';
    };
    var filtered = t.coil_filtered || 0;
    var coilNote = filtered ? '<div class="lc-filtered">⛔ ' + L(filtered + ' more dropped by the weekly / 2-week / monthly downtrend veto (a bounce inside a higher-timeframe bear — not a durable coil).', filtered + ' 个被周/双周/月线下跌否决过滤（更高周期熊市中的反弹——非可持续蓄势）。') + '</div>' : '';
    return '<div class="sec"><div class="lead-cols">'
      + col('🏃', 'Running — rising leaders', '领跑——上升领导',
        "This tab's subsectors already LEADING their peers and still accelerating (RRG leading quadrant, not topping). Ranked by acceleration, not level — the runners.",
        '本标签中已领先同侪且仍在加速的子行业（RRG 领先象限，未见顶）。按加速度而非水平排序——领跑者。',
        run, 'None accelerating cleanly in the leading quadrant.', '领先象限中暂无干净加速者。')
      + col('🌱', 'Coiling — about to run', '蓄势——即将启动',
        'Laggards turning UP (RRG improving) that PASS a coil confirmation — graded RSI divergence, multi-timeframe turn, volatility contraction, RS-hold — and SURVIVE a weekly / 2-week / monthly downtrend veto. The W/2W/M chips show that higher-timeframe trend. "Primed" = turning up above a rising trend with the higher TF confirming.',
        '落后但开始转强（RRG 改善象限）且通过蓄势确认的子行业——分级 RSI 背离、多周期转向、波动收缩、相对强弱守稳——并通过周/双周/月线下跌否决。W/2W/M 标签显示更高周期趋势。“就绪”=在上升趋势之上转强且更高周期确认。',
        coil, 'No laggards passed higher-timeframe coil confirmation.', '暂无落后子行业通过更高周期蓄势确认。', coilNote)
      + '</div></div>';
  }

  // a table that shows the first `limit` rows and tucks the rest behind a "Show all" toggle.
  // `rowsArr` is an array of <tr> strings; the rest are tagged .sc-xtra (hidden while .sc-collapsed).
  var _ctId = 0;
  function collapsibleTable(theadHTML, rowsArr, limit) {
    if (rowsArr.length <= limit) return '<table class="tbl"><thead>' + theadHTML + '</thead><tbody>' + rowsArr.join('') + '</tbody></table>';
    var id = 'sc-ct-' + (++_ctId);
    var body = rowsArr.map(function (r, i) { return i < limit ? r : r.replace(/^<tr/, '<tr class="sc-xtra"'); }).join('');
    var n = rowsArr.length;
    return '<div class="sc-collapse sc-collapsed" id="' + id + '" data-n="' + n + '" data-shown="' + limit + '">'
      + '<table class="tbl"><thead>' + theadHTML + '</thead><tbody>' + body + '</tbody></table>'
      + '<button class="sc-more" data-tgt="' + id + '" type="button">'
      + '<span class="l-en">Show all ' + n + ' ▾</span><span class="l-zh">展开全部 ' + n + ' ▾</span></button></div>';
  }
  // one delegated handler toggles a collapse wrapper between first-N and all rows.
  function onMoreClick(e) {
    var btn = e.target.closest ? e.target.closest('.sc-more') : null;
    if (!btn) return;
    var box = document.getElementById(btn.getAttribute('data-tgt'));
    if (!box) return;
    var open = box.classList.toggle('sc-collapsed') === false;
    var n = box.getAttribute('data-n'), shown = box.getAttribute('data-shown');
    btn.innerHTML = open
      ? '<span class="l-en">Show fewer ▴</span><span class="l-zh">收起 ▴</span>'
      : '<span class="l-en">Show all ' + n + ' ▾</span><span class="l-zh">展开全部 ' + n + ' ▾</span>';
  }

  /* ----- sections ----- */
  function cardHTML(g, ds) {
    var e = g.entry || {}, r = g.regime || {};
    var col = (g['class'] === 'headwind') ? 'var(--down)' : (g['class'] === 'entry_now') ? 'var(--up)' : (g['class'] === 'forming') ? 'var(--info)' : (g['class'] === 'tailwind') ? 'var(--ok)' : (g['class'] === 'late') ? 'var(--orange)' : 'var(--line)';
    return '<a class="card" style="border-left-color:' + col + '" href="' + (g.chart_key ? detailHref(ds, g.key) : '#') + '">'
      + '<div class="top"><div><div class="nm">' + esc(g.label) + '</div><div class="sct">' + esc(g.sector) + ' · ' + (g.n_priced || g.n_members) + ' ' + L('names', '只') + '</div></div>' + tierBadge(e.tier) + '</div>'
      + '<div class="row2">' + regimePill(r) + (e.tier ? '<span class="pill buy">' + L('ENTRY', '入场') + '</span>' : '') + '<span style="color:var(--muted);font-size:11px">' + freshTxt(e) + '</span></div>'
      + '<div class="meta">' + (r.rsi_3d != null ? '3D RSI ' + num(r.rsi_3d) + ' · StochRSI ' + num(r.stoch_3d) : '') + (r.rs_60d != null ? ' · RS60 ' + signed(r.rs_60d) : '') + '</div>'
      + '</a>';
  }

  function entryNowSection(payload, ds) {
    var noun = DS[ds].noun;
    var groups = groupsOf(ds);
    var entry = groups.filter(function (g) { return g['class'] === 'entry_now'; });
    var forming = groups.filter(function (g) { return g['class'] === 'forming'; });
    var h = '<div class="sec"><h2>🟢 ' + L('Entry-now ' + noun[0], '现可入场' + noun[1]) + ' <span class="n" style="color:var(--muted);font-weight:500">' + entry.length + '</span></h2>'
      + '<div class="desc">' + L('Fresh T1/T2 confluence cross (just fired) or T3 (3D StochRSI crossed &amp; 2D MACD about to cross). The headline — these are buy-ready now; the detail page shows the index chart &amp; which members are firing.',
        'T1/T2 汇聚刚触发，或 T3（3D StochRSI 已穿且 2D MACD 即将上穿）。头条——当前可买；详情页含指数图与触发成分。') + '</div>';
    h += entry.length ? '<div class="cards">' + entry.map(function (g) { return cardHTML(g, ds); }).join('') + '</div>' : '<div class="empty">' + L('No ' + noun[0] + ' is firing a fresh entry tier right now.', '当前没有' + noun[1] + '触发新的入场层级。') + '</div>';
    if (forming.length) h += '<h2 style="margin-top:18px">🔵 ' + L('Forming (T4 — earliest)', '构筑中（T4 — 最早）') + ' <span class="n" style="color:var(--muted);font-weight:500">' + forming.length + '</span></h2><div class="cards">' + forming.map(function (g) { return cardHTML(g, ds); }).join('') + '</div>';
    return h + '</div>';
  }

  function funnelSection(payload, ds) {
    var dg = payload.double_gated || {};
    dg.double_buy = dg.double_buy || [];  // tolerate a partial payload
    var maxs = Math.max.apply(null, [0.01].concat(dg.double_buy.map(function (r) { return r.combined_score || 0; })));
    var rows = dg.double_buy.map(function (r) {
      var w = Math.round(60 * (r.combined_score || 0) / maxs);
      return '<tr><td class="tk"><a href="' + stockHref(r.ticker) + '">' + esc(r.ticker) + '</a></td>'
        + '<td>' + tierBadge(r.stock_tier) + '</td>'
        + '<td><a href="' + detailHref(ds, r.subsector_key) + '">' + esc(r.subsector) + '</a></td>'
        + '<td>' + tierBadge(r.subsector_tier) + ' <span class="pill ' + (r.subsector_side || 'neutral') + '">' + esc(r.subsector_state) + '</span></td>'
        + '<td class="num">' + (r.combined_score == null ? '–' : r.combined_score.toFixed(2)) + ' <span class="scbar" style="width:' + w + 'px"></span></td>'
        + '<td>' + signed(r.vs_subsector_20d) + '</td></tr>';
    }).join('');
    var h = '<div class="sec"><h2>🎯 ' + L('Double-confluence buys', '双重汇聚买入') + ' <span class="n" style="color:var(--muted);font-weight:500">' + dg.double_buy.length + '</span></h2>'
      + '<div class="desc">' + L('Stocks whose OWN T1-T4 cascade is buyable AND whose subsector has a tailwind. Ranked by combined conviction = stock weight × subsector buyability factor (T1×T1 = 1.0).',
        '自身 T1-T4 级联可买且所在子行业顺风的个股。按综合把握度排序 = 个股权重 × 子行业可买系数（T1×T1 = 1.0）。') + '</div>';
    h += dg.double_buy.length ? '<table class="tbl"><thead><tr><th>' + L('Stock', '个股') + '</th><th>' + L('Stock tier', '个股层级') + '</th><th>' + L('Subsector', '子行业') + '</th><th>' + L('Subsector', '子行业') + '</th><th>' + L('Conviction', '综合把握') + '</th><th>' + L('vs sub 20d', '相对子行业20日') + '</th></tr></thead><tbody>' + rows + '</tbody></table>' : '<div class="empty">' + L('No double-confluence buys right now.', '当前无双重汇聚买入。') + '</div>';
    return h + '</div>';
  }

  function allGroupsSection(payload, ds) {
    var noun = DS[ds].noun;
    var groups = groupsOf(ds).slice();
    var rows = groups.map(function (g) {
      var e = g.entry || {}, r = g.regime || {};
      return '<tr><td><a href="' + (g.chart_key ? detailHref(ds, g.key) : '#') + '">' + esc(g.label) + '</a></td>'
        + '<td style="color:var(--muted)">' + esc(g.sector) + '</td>'
        + '<td>' + tierBadge(e.tier) + '</td>'
        + '<td>' + regimePill(r) + '</td>'
        + '<td style="color:var(--muted);font-size:11px">' + (freshTxt(e) || '') + '</td>'
        + '<td>' + signed(r.rs_60d) + '</td>'
        + '<td class="num">' + (g.n_priced || g.n_members) + '</td></tr>';
    });
    return '<div class="sec"><h2>📋 ' + L('All ' + noun[0], '全部' + noun[1]) + ' <span class="n" style="color:var(--muted);font-weight:500">' + groups.length + '</span></h2>'
      + collapsibleTable('<tr><th>' + L('Subsector', '子行业') + '</th><th>' + L('Sector', '板块') + '</th><th>' + L('Entry', '入场') + '</th><th>' + L('Regime', '状态') + '</th><th>' + L('Freshness', '新鲜度') + '</th><th>RS60</th><th>' + L('N', '数') + '</th></tr>', rows, 10) + '</div>';
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
        + (r.rs_60d != null ? '<div style="color:var(--muted);font-size:10.5px;margin-top:4px">RS60 ' + signed(r.rs_60d) + '</div>' : '');
      return href ? '<a class="s" href="' + href + '">' + inner + '</a>' : '<div class="s">' + inner + '</div>';
    }).join('');
    return '<div class="sec"><h2>🗺️ ' + L(meta[0], meta[1]) + '</h2><div class="desc">' + L(DS[ds].rollupDesc[0], DS[ds].rollupDesc[1]) + '</div><div class="secstrip">' + cells + '</div></div>';
  }

  /* ----- Nasdaq Internals archetype panel (TI-R4) -----
     Renders a display-only breadth/archetype read from nasdaq_internals.v1 artifact.
     If the artifact is absent, invalid JSON, or any field missing — the section stays hidden.
     Descriptive only, no forward claim. */
  var NI_STATE_COLORS = { leading: 'var(--up)', improving: 'var(--info)', weakening: 'var(--orange)', lagging: 'var(--down)' };
  var NI_STATE_LABELS = {
    leading:   ['Leading',   '领先'],
    improving: ['Improving', '改善'],
    weakening: ['Weakening', '走弱'],
    lagging:   ['Lagging',   '落后']
  };

  function niStateBadge(state, days) {
    var info = NI_STATE_LABELS[state];
    if (!info) return '<span class="qp" style="color:var(--muted);border-color:var(--muted)">—</span>';
    var col = NI_STATE_COLORS[state] || 'var(--muted)';
    var lbl = '<span class="l-en">' + info[0] + '</span><span class="l-zh">' + info[1] + '</span>';
    var dayTxt = (days != null && days > 0) ? ' <span style="color:var(--muted);font-size:10px">' + days + 'd</span>' : '';
    return '<span class="qp" style="color:' + col + ';border-color:' + col + '">' + lbl + '</span>' + dayTxt;
  }

  function niVal(x, d, suffix) {
    // renders a numeric value; null/undefined → em-dash
    if (x == null || (typeof x === 'number' && isNaN(x))) return '–';
    var v = Number(x);
    return v.toFixed(d == null ? 1 : d) + (suffix || '');
  }

  function nasdaqInternalsPanel() {
    // fail-open: any problem → return '' (section hidden, no error spam)
    try {
      var d = NIDATA;
      if (!d || typeof d !== 'object') return '';
      if (d.schema !== 'nasdaq_internals.v1') return '';

      var groups = d.groups;
      var ewqqq  = d.ew_vs_qqq || {};
      var divs   = d.divergences || [];

      // ---- a) Equal-weight vs QQQ chip ----
      var sp20 = ewqqq.spread_20d, sp60 = ewqqq.spread_60d, pct = ewqqq.pctile_1y;
      function spreadSpan(v) {
        if (v == null || isNaN(v)) return '<span class="num">–</span>';
        var n = Number(v);
        return '<span class="num ' + (n >= 0 ? 'pos' : 'neg') + '">' + (n >= 0 ? '+' : '') + n.toFixed(2) + 'pp</span>';
      }
      var ewHtml = '<div class="ni-ew-chip">'
        + '<span style="font-weight:700">' + L('EW vs QQQ', '等权 vs QQQ') + '</span>'
        + ' &nbsp;20d ' + spreadSpan(sp20)
        + ' &nbsp;60d ' + spreadSpan(sp60)
        + (pct != null ? ' &nbsp;<span style="color:var(--muted);font-size:11px">' + L('1y %ile', '1年百分位') + ' ' + niVal(pct, 0, '%') + '</span>' : '')
        + (ewqqq.n_members ? ' &nbsp;<span style="color:var(--muted);font-size:10.5px">n=' + ewqqq.n_members + '</span>' : '')
        + '</div>';

      // ---- b) Group archetype strip ----
      var groupCells = '';
      if (Array.isArray(groups)) {
        groupCells = groups.map(function (g) {
          var lbl = L(esc(g.label_en || g.id), esc(g.label_zh || g.id));
          var stateBadge = niStateBadge(g.state, g.state_days);
          var rs20  = signed(g.rs_20d,  1);
          var rs60  = signed(g.rs_60d,  1);
          var brd   = g.breadth_above_50dma != null ? niVal(g.breadth_above_50dma, 0, '%') : '–';
          var disp  = g.dispersion_20d  != null ? niVal(g.dispersion_20d, 1)  : '–';
          var accel = g.accel           != null ? signed(g.accel, 2) : '<span class="num">–</span>';
          return '<div class="s">'
            + '<div class="snm">' + lbl + '</div>'
            + '<div style="margin-top:5px;display:flex;gap:5px;flex-wrap:wrap;align-items:center">' + stateBadge + '</div>'
            + '<div style="color:var(--muted);font-size:10.5px;margin-top:4px;font-variant-numeric:tabular-nums">'
            + 'RS20 ' + rs20 + ' &nbsp;RS60 ' + rs60
            + '</div>'
            + '<div style="color:var(--muted);font-size:10px;margin-top:2px;font-variant-numeric:tabular-nums">'
            + L('Breadth', '宽度') + ' ' + brd + ' &nbsp;' + L('Disp', '离散') + ' ' + disp
            + '</div>'
            + '<div style="color:var(--muted);font-size:10px;margin-top:2px">'
            + L('Accel', '加速') + ' ' + accel + ' &nbsp;n=' + (g.n != null ? g.n : '–')
            + '</div>'
            + '</div>';
        }).join('');
      }
      var groupStrip = groupCells
        ? '<div class="secstrip" style="margin-top:8px">' + groupCells + '</div>'
        : '<div class="empty">' + L('Group data unavailable.', '组数据暂不可用。') + '</div>';

      // ---- c) Divergence rows ----
      var divHtml = '';
      if (divs.length) {
        var divRows = divs.map(function (dv) {
          var pair = Array.isArray(dv.pair) ? dv.pair.join(' / ') : '—';
          var gz = dv.gap_accel_z != null ? signed(dv.gap_accel_z, 2) : '<span class="num">–</span>';
          var note = L(esc(dv.note_en || ''), esc(dv.note_zh || ''));
          return '<tr>'
            + '<td style="color:var(--muted);white-space:normal">' + esc(pair) + '</td>'
            + '<td>' + gz + '</td>'
            + '<td style="color:var(--muted);white-space:normal">' + note + '</td>'
            + '</tr>';
        }).join('');
        divHtml = '<div style="margin-top:14px">'
          + '<div style="font-weight:700;font-size:12.5px;margin-bottom:6px">'
          + L('Divergences', '背离对') + '</div>'
          + '<table class="tbl"><thead><tr>'
          + '<th>' + L('Pair', '组合') + '</th>'
          + '<th>' + L('Gap Accel Z', '差距加速Z') + '</th>'
          + '<th>' + L('Note', '说明') + '</th>'
          + '</tr></thead><tbody>' + divRows + '</tbody></table>'
          + '</div>';
      }

      // ---- d) Watermark + disclaimer ----
      var wm = L(esc(d.watermark_en || ''), esc(d.watermark_zh || ''));
      var disc = L('Descriptive, display-only — no forward claim.', '描述性，仅供展示——不构成前瞻性主张。');
      var footHtml = '<div style="color:var(--muted);font-size:11px;margin-top:10px;line-height:1.5">'
        + (d.watermark_en ? wm + ' &nbsp;·&nbsp; ' : '') + disc + '</div>';

      // ---- assemble ----
      return '<div class="sec ni-panel">'
        + '<h2>📊 ' + L('Nasdaq Internals', '纳斯达克内部结构') + '</h2>'
        + '<div class="desc">' + L('Archetype group breadth and momentum reads vs QQQ. Descriptive only — no forward claim.',
            '各原型组相对 QQQ 的宽度与动量读数。仅描述性，不构成前瞻性主张。') + '</div>'
        + ewHtml
        + groupStrip
        + divHtml
        + footHtml
        + '</div>';
    } catch (e) {
      // fail-open: any error → section hidden, single debug line
      console.debug('[ni-panel] render error (artifact may be absent):', e && e.message);
      return '';
    }
  }

  function render() {
    var app = document.getElementById('sc-app');
    var ds = TAB;
    var payload = DATA[ds];
    if (!payload || !payload.ok) { app.innerHTML = '<div class="empty">' + L('No data yet — run the nightly build.', '暂无数据——请运行夜间构建。') + '</div>'; return; }
    var cov = payload.coverage || {};
    document.getElementById('sc-asof').innerHTML = L('as of ' + (payload.as_of || '—'), '截至 ' + (payload.as_of || '—')) + (cov.n_gateable != null ? ' · ' + cov.n_gateable + '/' + cov.n_subsectors + ' ' + L('covered', '覆盖') : '');
    var niSection = (ds === 'nasdaq') ? nasdaqInternalsPanel() : '';
    var h = entryNowSection(payload, ds) + tabLeadership(ds) + funnelSection(payload, ds) + sectorStrip(payload, ds) + niSection + allGroupsSection(payload, ds);
    app.innerHTML = h;
    wrapTbls(app);
  }

  function setTab(tab) {
    TAB = tab;
    Array.prototype.forEach.call(document.querySelectorAll('.sc-tab'), function (el) { el.classList.toggle('on', el.getAttribute('data-tab') === tab); });
    render();
  }

  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll('.sc-tab'), function (el) {
      el.addEventListener('click', function () { setTab(el.getAttribute('data-tab')); });
    });
    var appEl = document.getElementById('sc-app');
    if (appEl) appEl.addEventListener('click', onMoreClick);   // delegated "Show all / fewer" toggle
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
        if (el && !el.querySelector('.star-badge')) { var b = document.createElement('span'); b.className = 'star-badge'; b.textContent = ' ⭐'; b.title = 'Rising star — leadership accelerating fastest'; el.appendChild(b); }
      }
      // nasdaq_internals.v1 — fail-open: 404 or invalid JSON → NIDATA stays null, section hidden
      return fetch('marketdata/nasdaq_internals.json', { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    }).then(function (ni) {
      try { if (ni && ni.schema === 'nasdaq_internals.v1') NIDATA = ni; } catch (e) { /* ignore */ }
      render();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();

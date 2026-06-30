/* Subsector Confluence · China — renders the 同花顺 (THS) concept ENTRY-NOW board + double-gated
   A-share funnel from the precomputed engine JSON (marketdata/subsector_confluence_china.json).
   Vanilla JS, no deps. Bilingual via .l-en/.l-zh spans (theme.js toggles by html[data-lang]). */
(function () {
  'use strict';
  var L = function (en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh == null ? en : zh) + '</span>'; };
  var DATA = null;

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function num(x, d) { return (x == null || isNaN(x)) ? '–' : Number(x).toFixed(d == null ? 0 : d); }
  function signed(x, d) { if (x == null || isNaN(x)) return '<span class="num">–</span>'; var v = Number(x); return '<span class="num ' + (v >= 0 ? 'pos' : 'neg') + '">' + (v >= 0 ? '+' : '') + v.toFixed(d == null ? 1 : d) + '</span>'; }
  function tierBadge(t) { return '<span class="tier ' + (t || 'none') + '">' + (t || '—') + '</span>'; }
  function regimePill(r) { var side = (r && r.side) || 'neutral'; return '<span class="pill ' + side + '">' + L(esc((r && r.label) || (r && r.state) || '—'), esc((r && r.label_zh) || (r && r.state) || '—')) + '</span>'; }
  function freshTxt(e) {
    if (!e) return '';
    if (e.tier === 'T3' || e.tier === 'T4') { var b = e.bars_to_cross; return b != null ? L('~' + b + ' bars to cross', '约' + b + ' 根后交叉') : L('about to cross', '即将交叉'); }
    if (e.ticks != null) return e.ticks === 0 ? L('crossed this bar', '本根交叉') : L(e.ticks + ' tick' + (e.ticks > 1 ? 's' : '') + ' ago', e.ticks + ' 格前');
    return '';
  }
  function nameCell(label, labelZh) { return L(esc(label), esc(labelZh || label)); }
  function detailHref(g) { return 'subsector_china/' + g.key + '.html'; }
  function detailHrefKey(key) { return 'subsector_china/' + key + '.html'; }
  function stockHref(tk) { return 'china_lookup.html#' + encodeURIComponent(tk); }

  function cardHTML(g) {
    var e = g.entry || {}, r = g.regime || {};
    var col = (g['class'] === 'headwind') ? 'var(--down)' : (g['class'] === 'entry_now') ? 'var(--up)' : (g['class'] === 'forming') ? 'var(--info)' : (g['class'] === 'tailwind') ? 'var(--ok)' : (g['class'] === 'late') ? 'var(--orange)' : 'var(--line)';
    return '<a class="card" style="border-left-color:' + col + '" href="' + (g.chart_key ? detailHref(g) : '#') + '">'
      + '<div class="top"><div><div class="nm">' + nameCell(g.label, g.label_zh) + '</div><div class="sct">' + nameCell(g.sector, g.sector_zh) + ' · ' + (g.n_priced || g.n_members) + ' ' + L('names', '只') + '</div></div>' + tierBadge(e.tier) + '</div>'
      + '<div class="row2">' + regimePill(r) + (e.tier ? '<span class="pill buy">' + L('ENTRY', '入场') + '</span>' : '') + '<span style="color:var(--muted);font-size:11px">' + freshTxt(e) + '</span></div>'
      + '<div class="meta">' + (r.rsi_3d != null ? '3D RSI ' + num(r.rsi_3d) + ' · StochRSI ' + num(r.stoch_3d) : '') + (r.rs_60d != null ? ' · ' + L('RS60 vs CSI300', 'RS60 对沪深300') + ' ' + signed(r.rs_60d) : '') + '</div>'
      + '</a>';
  }

  function entryNowSection(p) {
    var entry = (p.baskets || []).filter(function (g) { return g['class'] === 'entry_now'; });
    var forming = (p.baskets || []).filter(function (g) { return g['class'] === 'forming'; });
    var h = '<div class="sec"><h2>🟢 ' + L('Entry-now concepts', '现可入场概念') + ' <span style="color:var(--muted);font-weight:500">' + entry.length + '</span></h2>'
      + '<div class="desc">' + L('Fresh T1/T2 confluence cross (just fired) or T3 (3D StochRSI crossed &amp; 2D MACD about to cross). The headline — buy-ready now; the detail page shows the index chart &amp; which members are firing.',
        'T1/T2 汇聚刚触发，或 T3（3D StochRSI 已穿且 2D MACD 即将上穿）。头条——当前可买；详情页含指数图与触发成分。') + '</div>';
    h += entry.length ? '<div class="cards">' + entry.map(cardHTML).join('') + '</div>' : '<div class="empty">' + L('No concept is firing a fresh entry tier right now.', '当前没有概念触发新的入场层级。') + '</div>';
    if (forming.length) h += '<h2 style="margin-top:18px">🔵 ' + L('Forming (T4 — earliest)', '构筑中（T4 — 最早）') + ' <span style="color:var(--muted);font-weight:500">' + forming.length + '</span></h2><div class="cards">' + forming.map(cardHTML).join('') + '</div>';
    return h + '</div>';
  }

  function funnelSection(p) {
    var dg = p.double_gated || {};
    var db = dg.double_buy || [], hw = dg.headwind_warn || [];
    var maxs = Math.max.apply(null, [0.01].concat(db.map(function (r) { return r.combined_score || 0; })));
    var rows = db.map(function (r) {
      var w = Math.round(60 * (r.combined_score || 0) / maxs);
      return '<tr><td class="tk"><a href="' + stockHref(r.ticker) + '">' + esc(r.ticker) + '</a>' + (r.name_zh ? ' <span style="color:var(--muted);font-weight:400;font-size:.9em">' + esc(r.name_zh) + '</span>' : '') + '</td>'
        + '<td>' + tierBadge(r.stock_tier) + '</td>'
        + '<td><a href="' + detailHrefKey(r.subsector_key) + '">' + nameCell(r.subsector, r.subsector_zh) + '</a></td>'
        + '<td>' + tierBadge(r.subsector_tier) + ' <span class="pill ' + (r.subsector_side || 'neutral') + '">' + esc(r.subsector_state) + '</span></td>'
        + '<td class="num">' + (r.combined_score == null ? '–' : r.combined_score.toFixed(2)) + ' <span class="scbar" style="width:' + w + 'px"></span></td>'
        + '<td>' + signed(r.vs_subsector_20d) + '</td></tr>';
    }).join('');
    var warn = hw.map(function (r) {
      return '<tr><td class="tk"><a href="' + stockHref(r.ticker) + '">' + esc(r.ticker) + '</a>' + (r.name_zh ? ' <span style="color:var(--muted);font-weight:400;font-size:.9em">' + esc(r.name_zh) + '</span>' : '') + '</td>'
        + '<td>' + tierBadge(r.stock_tier) + '</td>'
        + '<td><a href="' + detailHrefKey(r.subsector_key) + '">' + nameCell(r.subsector, r.subsector_zh) + '</a></td>'
        + '<td><span class="pill avoid">' + esc(r.subsector_state) + '</span></td></tr>';
    }).join('');
    var h = '<div class="sec"><h2>🎯 ' + L('Double-confluence buys', '双重汇聚买入') + ' <span style="color:var(--muted);font-weight:500">' + db.length + '</span></h2>'
      + '<div class="desc">' + L('A-shares whose OWN T1-T4 cascade is buyable AND whose concept has a tailwind. Ranked by combined conviction = stock weight × concept buyability factor (T1×T1 = 1.0).',
        '自身 T1-T4 级联可买且所在概念顺风的A股。按综合把握度排序 = 个股权重 × 概念可买系数（T1×T1 = 1.0）。') + '</div>';
    h += db.length ? '<table class="tbl"><thead><tr><th>' + L('Stock', '个股') + '</th><th>' + L('Stock tier', '个股层级') + '</th><th>' + L('Concept', '概念') + '</th><th>' + L('Concept', '概念') + '</th><th>' + L('Conviction', '综合把握') + '</th><th>' + L('vs concept 20d', '相对概念20日') + '</th></tr></thead><tbody>' + rows + '</tbody></table>' : '<div class="empty">' + L('No double-confluence buys right now.', '当前无双重汇聚买入。') + '</div>';
    if (warn) h += '<h2 style="margin-top:20px">⚠️ ' + L('Headwind warnings', '逆风警示') + ' <span style="color:var(--muted);font-weight:500">' + hw.length + '</span></h2>'
      + '<div class="desc">' + L('A strong-looking A-share (its own cascade fires) but its concept is TOPPING / SELLING — the "don\'t chase the leadership being distributed" flag. Not a buy.',
        '个股看似强势（自身级联触发），但所在概念正见顶/派发——“别去追正在派发的领涨股”信号。非买入。') + '</div>'
      + '<table class="tbl"><thead><tr><th>' + L('Stock', '个股') + '</th><th>' + L('Stock tier', '个股层级') + '</th><th>' + L('Concept', '概念') + '</th><th>' + L('Concept regime', '概念状态') + '</th></tr></thead><tbody>' + warn + '</tbody></table>';
    return h + '</div>';
  }

  function allSection(p) {
    var rows = (p.baskets || []).map(function (g) {
      var e = g.entry || {}, r = g.regime || {};
      return '<tr><td><a href="' + (g.chart_key ? detailHref(g) : '#') + '">' + nameCell(g.label, g.label_zh) + '</a></td>'
        + '<td style="color:var(--muted)">' + nameCell(g.sector, g.sector_zh) + '</td>'
        + '<td>' + tierBadge(e.tier) + '</td>'
        + '<td>' + regimePill(r) + '</td>'
        + '<td style="color:var(--muted);font-size:11px">' + (freshTxt(e) || '') + '</td>'
        + '<td>' + signed(r.rs_60d) + '</td>'
        + '<td class="num">' + (g.n_priced || g.n_members) + '</td></tr>';
    }).join('');
    return '<div class="sec"><h2>📋 ' + L('All gateable concepts', '全部可评概念') + ' <span style="color:var(--muted);font-weight:500">' + (p.baskets || []).length + '</span></h2>'
      + '<table class="tbl"><thead><tr><th>' + L('Concept', '概念') + '</th><th>' + L('Category', '类别') + '</th><th>' + L('Entry', '入场') + '</th><th>' + L('Regime', '状态') + '</th><th>' + L('Freshness', '新鲜度') + '</th><th>RS60</th><th>' + L('N', '数') + '</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function render() {
    var app = document.getElementById('sc-app');
    if (!DATA || !DATA.ok) { app.innerHTML = '<div class="empty">' + L('No data yet — run the nightly build.', '暂无数据——请运行夜间构建。') + '</div>'; return; }
    var cov = DATA.coverage || {};
    document.getElementById('sc-asof').innerHTML = L('as of ' + (DATA.as_of || '—'), '截至 ' + (DATA.as_of || '—')) + (cov.n_baskets != null ? ' · ' + cov.n_baskets + ' ' + L('concepts', '概念') : '');
    app.innerHTML = entryNowSection(DATA) + funnelSection(DATA) + allSection(DATA);
  }

  function boot() {
    fetch('marketdata/subsector_confluence_china.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { DATA = d; render(); })
      .catch(function () { DATA = null; render(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();

/* Subsector Confluence desk — renders the ENTRY-NOW board + double-gated funnel from the
   precomputed engine JSON (marketdata/subsector_confluence.json + basket_confluence.json).
   Vanilla JS, no deps. Bilingual via .l-en/.l-zh spans (theme.js toggles by html[data-lang]). */
(function () {
  'use strict';
  var L = function (en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh == null ? en : zh) + '</span>'; };
  var DATA = { subsectors: null, baskets: null };
  var TAB = 'subsectors';

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
  // `key` is the RAW group slug (g.key / row.subsector_key); detailHref applies the basket 'b-'
  // namespace ONCE. Never pass g.chart_key here — it is already the namespaced detail key.
  function detailHref(ds, key) { return 'subsector/' + (ds === 'baskets' ? 'b-' + key : key) + '.html'; }
  function stockHref(tk) { return 'stock.html#' + encodeURIComponent(tk); }

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
    var keyset = {}; (payload.entry_now || []).forEach(function (k) { keyset[k] = 1; });
    var groups = (payload[ds === 'baskets' ? 'baskets' : 'subsectors'] || []);
    var entry = groups.filter(function (g) { return g['class'] === 'entry_now'; });
    var forming = groups.filter(function (g) { return g['class'] === 'forming'; });
    var h = '<div class="sec"><h2>🟢 ' + L('Entry-now ' + (ds === 'baskets' ? 'baskets' : 'subsectors'), '现可入场' + (ds === 'baskets' ? '篮子' : '子行业')) + ' <span class="n" style="color:var(--muted);font-weight:500">' + entry.length + '</span></h2>'
      + '<div class="desc">' + L('Fresh T1/T2 confluence cross (just fired) or T3 (3D StochRSI crossed &amp; 2D MACD about to cross). The headline — these are buy-ready now; the detail page shows the index chart &amp; which members are firing.',
        'T1/T2 汇聚刚触发，或 T3（3D StochRSI 已穿且 2D MACD 即将上穿）。头条——当前可买；详情页含指数图与触发成分。') + '</div>';
    h += entry.length ? '<div class="cards">' + entry.map(function (g) { return cardHTML(g, ds); }).join('') + '</div>' : '<div class="empty">' + L('No subsector is firing a fresh entry tier right now.', '当前没有子行业触发新的入场层级。') + '</div>';
    if (forming.length) h += '<h2 style="margin-top:18px">🔵 ' + L('Forming (T4 — earliest)', '构筑中（T4 — 最早）') + ' <span class="n" style="color:var(--muted);font-weight:500">' + forming.length + '</span></h2><div class="cards">' + forming.map(function (g) { return cardHTML(g, ds); }).join('') + '</div>';
    return h + '</div>';
  }

  function funnelSection(payload, ds) {
    var dg = payload.double_gated || {};
    dg.double_buy = dg.double_buy || []; dg.headwind_warn = dg.headwind_warn || [];  // tolerate a partial payload
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
    var warn = dg.headwind_warn.map(function (r) {
      return '<tr><td class="tk"><a href="' + stockHref(r.ticker) + '">' + esc(r.ticker) + '</a></td>'
        + '<td>' + tierBadge(r.stock_tier) + '</td>'
        + '<td><a href="' + detailHref(ds, r.subsector_key) + '">' + esc(r.subsector) + '</a></td>'
        + '<td><span class="pill avoid">' + esc(r.subsector_state) + '</span></td></tr>';
    }).join('');
    var h = '<div class="sec"><h2>🎯 ' + L('Double-confluence buys', '双重汇聚买入') + ' <span class="n" style="color:var(--muted);font-weight:500">' + dg.double_buy.length + '</span></h2>'
      + '<div class="desc">' + L('Stocks whose OWN T1-T4 cascade is buyable AND whose subsector has a tailwind. Ranked by combined conviction = stock weight × subsector buyability factor (T1×T1 = 1.0).',
        '自身 T1-T4 级联可买且所在子行业顺风的个股。按综合把握度排序 = 个股权重 × 子行业可买系数（T1×T1 = 1.0）。') + '</div>';
    h += dg.double_buy.length ? '<table class="tbl"><thead><tr><th>' + L('Stock', '个股') + '</th><th>' + L('Stock tier', '个股层级') + '</th><th>' + L('Subsector', '子行业') + '</th><th>' + L('Subsector', '子行业') + '</th><th>' + L('Conviction', '综合把握') + '</th><th>' + L('vs sub 20d', '相对子行业20日') + '</th></tr></thead><tbody>' + rows + '</tbody></table>' : '<div class="empty">' + L('No double-confluence buys right now.', '当前无双重汇聚买入。') + '</div>';
    if (warn) h += '<h2 style="margin-top:20px">⚠️ ' + L('Headwind warnings', '逆风警示') + ' <span class="n" style="color:var(--muted);font-weight:500">' + dg.headwind_warn.length + '</span></h2>'
      + '<div class="desc">' + L('A great-looking stock (its own cascade fires) but its subsector is TOPPING / SELLING — the validated "don\'t chase the leadership institutions are distributing into" flag. Not a buy.',
        '个股看似强势（自身级联触发），但所在子行业正见顶/派发——已验证的“别去追机构正在派发的领涨股”信号。非买入。') + '</div>'
      + '<table class="tbl"><thead><tr><th>' + L('Stock', '个股') + '</th><th>' + L('Stock tier', '个股层级') + '</th><th>' + L('Subsector', '子行业') + '</th><th>' + L('Subsector regime', '子行业状态') + '</th></tr></thead><tbody>' + warn + '</tbody></table>';
    return h + '</div>';
  }

  function allGroupsSection(payload, ds) {
    var groups = (payload[ds === 'baskets' ? 'baskets' : 'subsectors'] || []).slice();
    var rows = groups.map(function (g) {
      var e = g.entry || {}, r = g.regime || {};
      return '<tr><td><a href="' + (g.chart_key ? detailHref(ds, g.key) : '#') + '">' + esc(g.label) + '</a></td>'
        + '<td style="color:var(--muted)">' + esc(g.sector) + '</td>'
        + '<td>' + tierBadge(e.tier) + '</td>'
        + '<td>' + regimePill(r) + '</td>'
        + '<td style="color:var(--muted);font-size:11px">' + (freshTxt(e) || '') + '</td>'
        + '<td>' + signed(r.rs_60d) + '</td>'
        + '<td class="num">' + (g.n_priced || g.n_members) + '</td></tr>';
    }).join('');
    return '<div class="sec"><h2>📋 ' + L('All gateable ' + (ds === 'baskets' ? 'baskets' : 'subsectors'), '全部可评' + (ds === 'baskets' ? '篮子' : '子行业')) + ' <span class="n" style="color:var(--muted);font-weight:500">' + groups.length + '</span></h2>'
      + '<table class="tbl"><thead><tr><th>' + L('Subsector', '子行业') + '</th><th>' + L('Sector', '板块') + '</th><th>' + L('Entry', '入场') + '</th><th>' + L('Regime', '状态') + '</th><th>' + L('Freshness', '新鲜度') + '</th><th>RS60</th><th>' + L('N', '数') + '</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function sectorStrip(payload) {
    var secs = payload.sectors || [];
    if (!secs.length) return '';
    var cells = secs.map(function (g) {
      var r = g.regime || {};
      return '<div class="s"><div class="snm">' + esc(g.label) + '</div><div style="margin-top:5px">' + regimePill(r) + (g.entry && g.entry.tier ? ' ' + tierBadge(g.entry.tier) : '') + '</div></div>';
    }).join('');
    return '<div class="sec"><h2>🗺️ ' + L('Sector rollup', '板块汇总') + '</h2><div class="desc">' + L('Each Finviz sector as one equal-weight basket — the backdrop the subsectors live inside.', '每个 Finviz 板块作为一个等权篮子——子行业所处的大背景。') + '</div><div class="secstrip">' + cells + '</div></div>';
  }

  function render() {
    var app = document.getElementById('sc-app');
    var ds = TAB;
    var payload = DATA[ds === 'baskets' ? 'baskets' : 'subsectors'];
    if (!payload || !payload.ok) { app.innerHTML = '<div class="empty">' + L('No data yet — run the nightly build.', '暂无数据——请运行夜间构建。') + '</div>'; return; }
    var cov = payload.coverage || {};
    document.getElementById('sc-asof').innerHTML = L('as of ' + (payload.as_of || '—'), '截至 ' + (payload.as_of || '—')) + (cov.n_gateable != null ? ' · ' + cov.n_gateable + '/' + cov.n_subsectors + ' ' + L('gateable', '可评') : '');
    var h = entryNowSection(payload, ds) + funnelSection(payload, ds) + (ds === 'subsectors' ? sectorStrip(payload) : '') + allGroupsSection(payload, ds);
    app.innerHTML = h;
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
    Promise.all([
      fetch('marketdata/subsector_confluence.json', { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      fetch('marketdata/basket_confluence.json', { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
    ]).then(function (res) {
      DATA.subsectors = res[0]; DATA.baskets = res[1];
      var s = res[0] && res[0].subsectors ? res[0].subsectors.length : 0;
      var b = res[1] && res[1].baskets ? res[1].baskets.length : 0;
      var ns = document.getElementById('tabn-sub'); if (ns) ns.textContent = s;
      var nb = document.getElementById('tabn-bas'); if (nb) nb.textContent = b;
      render();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();

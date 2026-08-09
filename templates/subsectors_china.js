/* Subsector Confluence · China — renders the 同花顺 (THS) concept ENTRY-NOW board + double-gated
   A-share funnel from the precomputed engine JSON (marketdata/subsector_confluence_china.json).
   Vanilla JS, no deps. Bilingual via .l-en/.l-zh spans (theme.js toggles by html[data-lang]). */
(function () {
  'use strict';
  var L = function (en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh == null ? en : zh) + '</span>'; };
  var DATA = null;
  var collapseSeq = 0;

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function num(x, d) { return (x == null || isNaN(x)) ? '–' : Number(x).toFixed(d == null ? 0 : d); }
  function signed(x, d) { if (x == null || isNaN(x)) return '<span class="num">–</span>'; var v = Number(x); return '<span class="num ' + (v >= 0 ? 'pos' : 'neg') + '">' + (v >= 0 ? '+' : '') + v.toFixed(d == null ? 1 : d) + '</span>'; }
  function tierBadge(t) { return '<span class="tier ' + (t || 'none') + '">' + (t || '—') + '</span>'; }
  function shortState(en, zh) {
    var raw = String(en || '').replace(/[_-]+/g, ' ').trim();
    var key = raw.toLowerCase();
    var m = {
      buy: ['Buy', '买'],
      'buy partial': ['Part', '轻买'],
      setup: ['Setup', '预备'],
      'setup buy': ['Setup', '预备'],
      riding: ['Ride', '顺势'],
      extended: ['Ext', '过热'],
      neutral: ['Neut', '中性'],
      'below trend': ['Below', '破势'],
      topping: ['Top', '见顶'],
      sell: ['Sell', '卖']
    };
    var hit = m[key];
    return hit ? { en: hit[0], zh: hit[1] } : { en: raw || '—', zh: zh || raw || '—' };
  }
  function regimePill(r) { var side = (r && r.side) || 'neutral'; var s = shortState((r && (r.state || r.label)) || '—', r && r.label_zh); return '<span class="pill ' + side + '">' + L(esc(s.en), esc(s.zh)) + '</span>'; }
  function statePill(state, side) { var s = shortState(state, state); return '<span class="pill ' + (side || 'neutral') + '">' + L(esc(s.en), esc(s.zh)) + '</span>'; }
  function freshTxt(e) {
    if (!e) return '';
    if (e.tier === 'T3' || e.tier === 'T4') return L('about to fire', '即将触发');
    if (e.ticks != null) return e.ticks === 0 ? L('just fired', '刚刚触发') : L('fired ' + e.ticks + ' bar' + (e.ticks > 1 ? 's' : '') + ' ago', e.ticks + ' 根K线前触发');
    return '';
  }
  function nameCell(label, labelZh) { return L(esc(label), esc(labelZh || label)); }
  function detailHref(g) { return 'subsector_china/' + g.key + '.html'; }
  function detailHrefKey(key) { return 'subsector_china/' + key + '.html'; }
  function stockHref(tk) { return 'china_lookup.html#' + encodeURIComponent(tk); }

  // breadth-reliability of a concept's synthetic index: an equal-weight index on <6 PRICED members
  // is dominated by 1–2 names (high-variance tier/regime read), so the board flags it LOW and
  // collapses it out of the headline lists. high>=12, med 6–11, low<6 (matches the engine).
  function relTierN(n) { n = n || 0; return n >= 12 ? 'high' : n >= 6 ? 'med' : 'low'; }
  function relTier(g) { return (g && g.reliability) || relTierN(g && (g.n_priced != null ? g.n_priced : g.n_members)); }
  function isThinG(g) { return relTier(g) === 'low'; }
  function isThinRow(r) { return (r.subsector_reliability || relTierN(r.subsector_n_priced)) === 'low'; }
  function thinBadge(n) { return '<span class="relb rel-low" title="' + esc(n) + ' stocks — too few for a steady read">⚠ ' + L('thin', '偏薄') + '</span>'; }
  function relBadge(g) { return isThinG(g) ? ' ' + thinBadge(g.n_priced != null ? g.n_priced : g.n_members) : ''; }

  function cardHTML(g) {
    var e = g.entry || {}, r = g.regime || {};
    var col = (g['class'] === 'headwind') ? 'var(--down)' : (g['class'] === 'entry_now') ? 'var(--up)' : (g['class'] === 'forming') ? 'var(--info)' : (g['class'] === 'tailwind') ? 'var(--ok)' : (g['class'] === 'late') ? 'var(--orange)' : 'var(--line)';
    return '<a class="card" style="border-left-color:' + col + '" href="' + (g.chart_key ? detailHref(g) : '#') + '">'
      + '<div class="top"><div><div class="nm">' + nameCell(g.label, g.label_zh) + '</div><div class="sct">' + nameCell(g.sector, g.sector_zh) + ' · ' + (g.n_priced || g.n_members) + ' ' + L('names', '只') + relBadge(g) + '</div></div>' + tierBadge(e.tier) + '</div>'
      + '<div class="row2">' + regimePill(r) + (e.tier ? '<span class="pill buy">' + L('ENTRY', '入场') + '</span>' : '') + '<span style="color:var(--muted);font-size:11px">' + freshTxt(e) + '</span></div>'
      + '<div class="meta">' + (r.rs_60d != null ? L('vs CSI 300, 60d', '近60日 对沪深300') + ' ' + signed(r.rs_60d) : '') + '</div>'
      + '</a>';
  }
  function cardDeck(items) {
    if (items.length <= 10) return '<div class="cards">' + items.map(cardHTML).join('') + '</div>';
    var regionId = 'sc-card-region-' + (++collapseSeq);
    return '<div class="sc-card-collapse sc-card-collapsed" data-mobile-limit="10" data-desktop-rows="3" data-total="' + items.length + '">'
      + '<div class="cards" id="' + regionId + '">' + items.map(cardHTML).join('') + '</div>'
      + '<button class="sc-more sc-card-more" type="button" aria-expanded="false" aria-controls="' + regionId + '"></button></div>';
  }
  function gridCols(grid) {
    if (!grid) return 1;
    var cs = window.getComputedStyle ? window.getComputedStyle(grid) : null;
    var cols = cs ? cs.gridTemplateColumns.split(' ').filter(Boolean).length : 0;
    return Math.max(1, cols || 1);
  }
  function updateCardCollapse(box) {
    var cards = Array.prototype.slice.call(box.querySelectorAll('.card'));
    var btn = box.querySelector('.sc-card-more');
    if (!btn) return;
    var mobile = window.matchMedia && window.matchMedia('(max-width:720px)').matches;
    var limit = mobile ? Number(box.getAttribute('data-mobile-limit') || 10) : gridCols(box.querySelector('.cards')) * Number(box.getAttribute('data-desktop-rows') || 3);
    var open = !box.classList.contains('sc-card-collapsed');
    cards.forEach(function (card, i) { card.classList.toggle('sc-card-hidden', !open && i >= limit); });
    btn.style.display = cards.length > limit ? '' : 'none';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.innerHTML = open
      ? '<span class="l-en">See fewer ▴</span><span class="l-zh">收起 ▴</span>'
      : '<span class="l-en">See more (' + (cards.length - limit) + ') ▾</span><span class="l-zh">展开更多 (' + (cards.length - limit) + ') ▾</span>';
  }
  function updateCardCollapses(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.sc-card-collapse'), updateCardCollapse);
  }
  /* Long TABLES collapse the same way the card decks do. Before this the funnel
     capped its list at DB_CAP and printed a dead "+ N more" line, so the rows past
     the cap were not hidden — they were never rendered, and the reader was told
     about names they had no way to reach. */
  function rowCollapse(tableHTML, total, cap) {
    if (total <= cap) return tableHTML;
    var regionId = 'sc-row-region-' + (++collapseSeq);
    var controlledTable = tableHTML.replace('<table ', '<table id="' + regionId + '" ');
    return '<div class="sc-row-collapse sc-rows-collapsed" data-cap="' + cap + '">' + controlledTable
      + '<button class="sc-more sc-row-more" type="button" aria-expanded="false" aria-controls="' + regionId + '"></button></div>';
  }
  function updateRowCollapse(box) {
    var rows = Array.prototype.slice.call(box.querySelectorAll('tbody tr'));
    var btn = box.querySelector('.sc-row-more');
    if (!btn) return;
    var cap = Number(box.getAttribute('data-cap') || 30);
    var open = !box.classList.contains('sc-rows-collapsed');
    // Only DATA rows count toward the cap and the button's total. The all-concepts
    // table interleaves category header rows, so counting every <tr> would put 254
    // on a button whose section heading says 237 — and could leave a collapsed
    // table ending on a bare category heading with nothing under it.
    var shown = 0, total = 0, cats = [];
    rows.forEach(function (tr) {
      if (tr.querySelector('td.cat-row')) { cats.push({ tr: tr, n: 0 }); return; }
      total++;
      var hide = !open && shown >= cap;
      if (!hide) { shown++; if (cats.length) cats[cats.length - 1].n++; }
      tr.classList.toggle('sc-card-hidden', hide);
    });
    cats.forEach(function (g) { g.tr.classList.toggle('sc-card-hidden', g.n === 0); });
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.innerHTML = open
      ? '<span class="l-en">See fewer ▴</span><span class="l-zh">收起 ▴</span>'
      : '<span class="l-en">See all ' + total + ' ▾</span><span class="l-zh">展开全部 ' + total + ' ▾</span>';
  }
  function updateRowCollapses(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.sc-row-collapse'), updateRowCollapse);
  }
  function onMoreClick(e) {
    var rowBtn = e.target.closest ? e.target.closest('.sc-row-more') : null;
    if (rowBtn) {
      var rbox = rowBtn.closest('.sc-row-collapse');
      if (rbox) { rbox.classList.toggle('sc-rows-collapsed'); updateRowCollapse(rbox); }
      return;
    }
    var btn = e.target.closest ? e.target.closest('.sc-card-more') : null;
    if (!btn) return;
    var box = btn.closest('.sc-card-collapse');
    if (!box) return;
    box.classList.toggle('sc-card-collapsed');
    updateCardCollapse(box);
  }
  function wrapTbls(root) {
    if (!root) return;
    root.querySelectorAll('table').forEach(function (t) {
      if (t.closest('.tbl-scroll') || !t.parentNode) return;
      var w = document.createElement('div'); w.className = 'tbl-scroll';
      t.parentNode.insertBefore(w, t); w.appendChild(t);
    });
  }

  function entryNowSection(p) {
    var all = (p.baskets || []);
    var entry = all.filter(function (g) { return g['class'] === 'entry_now' && !isThinG(g); });
    var forming = all.filter(function (g) { return g['class'] === 'forming' && !isThinG(g); });
    // thin concepts that WOULD be actionable (entry-now / forming) but rest on <6 priced members —
    // kept, but collapsed out of the headline so a 3-stock "index" never sits beside a 25-name one.
    var thinAct = all.filter(function (g) { return (g['class'] === 'entry_now' || g['class'] === 'forming') && isThinG(g); });
    var h = '<div class="sec"><h2>🟢 ' + L('Entry-now concepts', '现可入场概念') + ' <span style="color:var(--muted);font-weight:500">' + entry.length + '</span></h2>'
      + '<div class="desc">' + L('Themes where a buy signal just fired, or is one step away. Open one to see its chart and which of its stocks are moving.',
        '刚出现买入信号、或只差一步的概念。点开可以看走势图，以及概念里哪些股票在动。') + '</div>';
    h += entry.length ? cardDeck(entry) : '<div class="empty">' + L('No theme is firing a fresh buy signal right now.', '目前没有概念出现新的买入信号。') + '</div>';
    if (forming.length) h += '<h2 style="margin-top:18px">🔵 ' + L('Forming (T4 — earliest)', '构筑中（T4 — 最早）') + ' <span style="color:var(--muted);font-weight:500">' + forming.length + '</span></h2><div class="cards">' + forming.map(cardHTML).join('') + '</div>';
    if (thinAct.length) {
      h += '<details class="thin"><summary>⚠ ' + L('Low-confidence · thin concepts', '低可信 · 过薄概念') + ' <span style="color:var(--muted);font-weight:500">' + thinAct.length + '</span></summary>'
        + '<div class="desc">' + L('Same signal, but the theme holds too few stocks for the read to be steady — one or two names can swing the whole thing. Listed for completeness; treat it as weak.',
          '信号一样，但这个概念里的股票太少，读数不稳——一两只股就能带偏整体。列在这里只为完整，当作偏弱看待。') + '</div>'
        + '<div class="cards">' + thinAct.map(cardHTML).join('') + '</div></details>';
    }
    return h + '</div>';
  }

  var DB_CAP = 30, ALL_CAP = 25;
  function conceptCell(r) {
    var np = r.subsector_n_priced;
    return '<a href="' + detailHrefKey(r.subsector_key) + '">' + nameCell(r.subsector, r.subsector_zh) + '</a>'
      + (np != null ? ' <span class="npc">·' + esc(np) + '</span>' : '') + (isThinRow(r) ? ' ' + thinBadge(np) : '');
  }
  function dbRowHTML(r, maxs) {
    var w = Math.round(60 * (r.combined_score || 0) / maxs);
    return '<tr><td class="tk col-stock"><a href="' + stockHref(r.ticker) + '">' + esc(r.ticker) + '</a>' + (r.name_zh ? ' <span class="stock-name" style="color:var(--muted);font-weight:400;font-size:.9em">' + esc(r.name_zh) + '</span>' : '') + '</td>'
      + '<td class="col-tier">' + tierBadge(r.stock_tier) + '</td>'
      + '<td class="col-concept">' + conceptCell(r) + '</td>'
      + '<td class="col-concept-state">' + tierBadge(r.subsector_tier) + ' ' + statePill(r.subsector_state, r.subsector_side) + '</td>'
      + '<td class="num col-conviction">' + (r.combined_score == null ? '–' : r.combined_score.toFixed(2)) + ' <span class="scbar" style="width:' + w + 'px"></span></td>'
      + '<td class="col-vs20">' + signed(r.vs_subsector_20d) + '</td></tr>';
  }
  function dbTable(list, maxs) {
    return '<table class="tbl db-table"><thead><tr><th class="col-stock">' + L('Stock', '个股') + '</th><th class="col-tier">' + L('Stock tier', '个股层级') + '</th><th class="col-concept">' + L('Concept', '概念') + '</th><th class="col-concept-state">' + L('Concept state', '概念状态') + '</th><th class="col-conviction">' + L('Conviction', '综合把握') + '</th><th class="col-vs20">' + L('vs concept 20d', '相对概念20日') + '</th></tr></thead><tbody>'
      + list.map(function (r) { return dbRowHTML(r, maxs); }).join('') + '</tbody></table>';
  }
  function funnelSection(p) {
    var dg = p.double_gated || {};
    var dbAll = dg.double_buy || [], hw = dg.headwind_warn || [];
    // split by concept breadth: reliable picks headline; thin-concept picks collapse (kept, flagged)
    var dbRel = dbAll.filter(function (r) { return !isThinRow(r); });
    var dbThin = dbAll.filter(isThinRow);
    var maxs = Math.max.apply(null, [0.01].concat(dbAll.map(function (r) { return r.combined_score || 0; })));
    var warn = hw.map(function (r) {
      return '<tr><td class="tk col-stock"><a href="' + stockHref(r.ticker) + '">' + esc(r.ticker) + '</a>' + (r.name_zh ? ' <span class="stock-name" style="color:var(--muted);font-weight:400;font-size:.9em">' + esc(r.name_zh) + '</span>' : '') + '</td>'
        + '<td class="col-tier">' + tierBadge(r.stock_tier) + '</td>'
        + '<td class="col-concept">' + conceptCell(r) + '</td>'
        + '<td class="col-regime">' + statePill(r.subsector_state, 'avoid') + '</td></tr>';
    }).join('');
    var h = '<div class="sec"><h2>🎯 ' + L('Buys with the theme behind them', '概念顺风的买入') + ' <span style="color:var(--muted);font-weight:500">' + dbRel.length + '</span></h2>'
      + '<div class="desc">' + L('A-shares that are a buy on their own, and whose theme is working too. The strongest agreement sits at the top.',
        '本身就是买点、所在概念也在走强的A股。两边一致程度最高的排在最前面。') + '</div>';
    h += dbRel.length ? rowCollapse(dbTable(dbRel, maxs), dbRel.length, DB_CAP)
      : '<div class="empty">' + L('Nothing right now has both the stock and its theme working.', '目前没有个股和概念同时走强的标的。') + '</div>';
    if (dbThin.length) {
      h += '<details class="thin"><summary>⚠ ' + L('Theme too small to lean on', '概念太小，不足为凭') + ' <span style="color:var(--muted);font-weight:500">' + dbThin.length + '</span></summary>'
        + '<div class="desc">' + L('The stock is a buy, but the only theme supporting it holds too few names to trust. Judge these on the stock alone.',
          '个股是买点，但唯一支持它的概念里股票太少，不足为凭。这些只看个股本身来判断。') + '</div>'
        + rowCollapse(dbTable(dbThin, maxs), dbThin.length, DB_CAP) + '</details>';
    }
    if (warn) h += '<details class="thin" style="margin-top:20px"><summary>⚠️ ' + L('Strong stock, weak theme', '个股强、概念弱') + ' <span style="color:var(--muted);font-weight:500">' + hw.length + '</span></summary>'
      + '<div class="desc">' + L('The stock looks strong, but its theme is topping out — the classic case of chasing something that is being sold into. Not a buy.',
        '个股看着强，但所在概念已经在见顶——典型的追在出货方向上。不是买点。') + '</div>'
      + rowCollapse('<table class="tbl hw-table"><thead><tr><th class="col-stock">' + L('Stock', '个股') + '</th><th class="col-tier">' + L('Stock tier', '个股层级') + '</th><th class="col-concept">' + L('Theme', '概念') + '</th><th class="col-regime">' + L('Theme state', '概念状态') + '</th></tr></thead><tbody>' + warn + '</tbody></table>', hw.length, DB_CAP) + '</details>';
    return h + '</div>';
  }

  var CLS_ORDER = { entry_now: 0, forming: 1, tailwind: 2, neutral: 3, late: 4, headwind: 5 };
  function conceptRow(g) {
    var e = g.entry || {}, r = g.regime || {};
    return '<tr><td class="col-concept"><a href="' + (g.chart_key ? detailHref(g) : '#') + '">' + nameCell(g.label, g.label_zh) + '</a></td>'
      + '<td class="col-entry">' + tierBadge(e.tier) + '</td>'
      + '<td class="col-regime">' + regimePill(r) + '</td>'
      + '<td class="col-fresh" style="color:var(--muted);font-size:11px">' + (freshTxt(e) || '') + '</td>'
      + '<td class="col-rs">' + signed(r.rs_60d) + '</td>'
      + '<td class="num col-n">' + (g.n_priced || g.n_members) + relBadge(g) + '</td></tr>';
  }
  function relRank(g) { var t = relTier(g); return t === 'high' ? 0 : t === 'med' ? 1 : 2; }
  function allSection(p) {
    var bs = (p.baskets || []);
    var groups = {};
    bs.forEach(function (g) { var c = g.sector || 'Other'; (groups[c] = groups[c] || []).push(g); });
    var cats = Object.keys(groups);
    // categories with the most entry-now concepts float to the top
    cats.sort(function (a, b) {
      var ea = groups[a].filter(function (g) { return g['class'] === 'entry_now'; }).length;
      var eb = groups[b].filter(function (g) { return g['class'] === 'entry_now'; }).length;
      return eb - ea || groups[b].length - groups[a].length || a.localeCompare(b);
    });
    var body = '';
    cats.forEach(function (c) {
      var gs = groups[c].slice().sort(function (x, y) {
        return (CLS_ORDER[x['class']] || 9) - (CLS_ORDER[y['class']] || 9) || relRank(x) - relRank(y) || (((y.entry || {}).weight) || 0) - (((x.entry || {}).weight) || 0);
      });
      var en = gs.filter(function (g) { return g['class'] === 'entry_now'; }).length;
      var zh = (gs[0] || {}).sector_zh || c;
      body += '<tr><td class="cat-row" colspan="6" style="font-weight:700;background:var(--panel);padding-top:13px;border-bottom:1px solid var(--line)">' + nameCell(c, zh)
        + ' <span style="color:var(--muted);font-weight:400;font-size:11px">· ' + gs.length + (en ? ' · ' + en + ' ' + L('entry-now', '现可入场') : '') + '</span></td></tr>';
      body += gs.map(conceptRow).join('');
    });
    return '<div class="sec"><h2>📋 ' + L('All concepts · by category', '全部概念 · 按类别') + ' <span style="color:var(--muted);font-weight:500">' + bs.length + '</span></h2>'
      + rowCollapse('<table class="tbl all-table"><thead><tr><th class="col-concept">' + L('Concept', '概念') + '</th><th class="col-entry">' + L('Entry', '入场') + '</th><th class="col-regime">' + L('State', '状态') + '</th><th class="col-fresh">' + L('How fresh', '新鲜度') + '</th><th class="col-rs">' + L('vs CSI 300', '对沪深300') + '</th><th class="col-n">' + L('Stocks', '只数') + '</th></tr></thead><tbody>' + body + '</tbody></table>', bs.length, ALL_CAP) + '</div>';
  }

  function render() {
    var app = document.getElementById('sc-app');
    if (!DATA || !DATA.ok) { app.innerHTML = '<div class="empty">' + L('No data yet — run the nightly build.', '暂无数据——请运行夜间构建。') + '</div>'; return; }
    var cov = DATA.coverage || {};
    var reliable = (cov.n_high || 0) + (cov.n_med || 0);
    var thinTxt = (cov.n_low_conf != null && cov.n_baskets)
      ? ' · <span class="rel-low">' + cov.n_low_conf + ' ' + L('thin', '过薄') + '</span> / ' + reliable + ' ' + L('reliable', '可信')
      : '';
    document.getElementById('sc-asof').innerHTML = L('as of ' + (DATA.as_of || '—'), '截至 ' + (DATA.as_of || '—')) + (cov.n_baskets != null ? ' · ' + cov.n_baskets + ' ' + L('concepts', '概念') : '') + thinTxt;
    app.innerHTML = entryNowSection(DATA) + funnelSection(DATA) + allSection(DATA);
    wrapTbls(app);
    updateCardCollapses(app);
    updateRowCollapses(app);
  }

  function boot() {
    var appEl = document.getElementById('sc-app');
    if (appEl) appEl.addEventListener('click', onMoreClick);
    if (window.addEventListener) window.addEventListener('resize', function () { updateCardCollapses(document.getElementById('sc-app')); });
    fetch('marketdata/subsector_confluence_china.board.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { DATA = d; render(); })
      .catch(function () { DATA = null; render(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();

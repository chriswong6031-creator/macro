/* Prevailing-narrative scorecard for the Thematic Baskets pages — surfaces the live
   Narrative-Rotation read (current best place to allocate, suggested book, regime breadth,
   rotation/handoff) right where themes are browsed, with a button into the full playbook.
   Self-contained: injects its own <style>, fetches allocationdata/<data-alloc>, degrades
   silently if the artifact is absent. Display-only; the allocation page owns the detail. */
(function () {
  var el = document.getElementById('nr-scorecard');
  if (!el) return;
  var alloc = el.getAttribute('data-alloc') || 'allocation.json';
  var page = el.getAttribute('data-page') || 'allocation.html';
  var esc = function (s) { return (s == null ? '' : String(s)).replace(/[&<>"]/g, function (c) {
    return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); };
  var L = function (en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>'; };
  var pct = function (x) { return x == null ? '—' : Math.round(x * 100) + '%'; };
  var leanColor = function (l) {
    return l === 'overweight' ? 'var(--up)' : (l === 'avoid' || l === 'underweight' ? 'var(--down)' : 'var(--muted)'); };

  var st = document.createElement('style');
  st.textContent =
    '#nr-scorecard{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent,#7c5cff);' +
      'border-radius:12px;padding:14px 16px;margin:14px 0;display:flex;flex-wrap:wrap;gap:18px;align-items:stretch}' +
    '#nr-scorecard .nrc-main{flex:1 1 380px;min-width:280px}' +
    '#nr-scorecard .nrc-lead{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}' +
    '#nr-scorecard .nrc-name{font-size:23px;font-weight:700;margin:2px 0 4px}' +
    '#nr-scorecard .nrc-sub{font-size:13px}#nr-scorecard .nrc-sub b{font-size:17px}' +
    '#nr-scorecard .nrc-chips{margin:8px 0 6px}' +
    '#nr-scorecard .nrc-chip{display:inline-block;font-size:11px;padding:1px 7px;margin:0 4px 4px 0;border-radius:7px;' +
      'background:var(--panel2);border:1px solid var(--line);color:var(--muted)}' +
    '#nr-scorecard .nrc-chip.ok{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.4);color:var(--up)}' +
    '#nr-scorecard .nrc-chip.hot{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.4);color:var(--down)}' +
    '#nr-scorecard .nrc-chip.dom{background:rgba(124,92,255,.12);border-color:rgba(124,92,255,.4)}' +
    '#nr-scorecard .nrc-read{font-size:12.5px;color:var(--muted);line-height:1.5;margin:6px 0 0;max-width:70ch}' +
    '#nr-scorecard .nrc-read b{color:var(--text);font-weight:650}' +
    '#nr-scorecard .nrc-book{margin-top:8px;display:grid;gap:4px;max-width:380px}' +
    '#nr-scorecard .nrc-row{display:flex;align-items:center;gap:8px;font-size:12px}' +
    '#nr-scorecard .nrc-row .nm{flex:0 0 150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '#nr-scorecard .nrc-row .bar{flex:1;height:9px;background:var(--grid,var(--panel2));border-radius:5px;overflow:hidden}' +
    '#nr-scorecard .nrc-row .fill{display:block;height:100%;background:linear-gradient(90deg,var(--accent,#5aa7ff),#7c5cff)}' +
    '#nr-scorecard .nrc-row .wv{flex:0 0 36px;text-align:right;font-variant-numeric:tabular-nums}' +
    '#nr-scorecard .nrc-side{flex:0 0 210px;display:flex;flex-direction:column;gap:8px}' +
    '#nr-scorecard .nrc-g{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:7px 10px;display:flex;justify-content:space-between;align-items:baseline;gap:8px}' +
    '#nr-scorecard .nrc-g .k{font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}' +
    '#nr-scorecard .nrc-g .v{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}' +
    '#nr-scorecard .nrc-btn{display:block;text-align:center;background:var(--accent,#5aa7ff);color:#fff;font-weight:650;' +
      'font-size:13px;padding:9px 12px;border-radius:9px;margin-top:auto}' +
    '#nr-scorecard .nrc-btn:hover{filter:brightness(1.08)}' +
    '#nr-scorecard .nrc-honest{font-size:10.5px;color:var(--muted);margin-top:6px;text-align:center}' +
    '#nr-scorecard .nrc-falter{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;' +
      'padding:2px 8px;margin:4px 0 2px;border-radius:7px;background:rgba(239,68,68,.12);' +
      'border:1px solid rgba(245,158,11,.6);color:var(--down,#ef4444)}' +
    '#nr-scorecard .nrc-exp{font-size:10.5px;margin-top:8px;padding:2px 8px;display:inline-block;' +
      'border-radius:7px;background:rgba(245,158,11,.10);border:1px solid rgba(245,158,11,.45);color:#d97706}';
  document.head.appendChild(st);

  fetch('allocationdata/' + alloc + '?cb=' + Date.now())
    .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
    .then(function (d) {
      if (!d || !d.headline) { el.style.display = 'none'; return; }
      var h = d.headline, a = d.allocation || {}, r = d.rotation || {};
      var bov = r.breadth_of_rotation || {};
      var dbar = h.durability_bar;
      var hurstZh = { trend: '趋势', 'mean-revert': '均值回归', mixed: '混合' };
      var viewZh = { broad: '广泛', narrowing: '收窄', narrow: '狭窄' };

      // ---- A2: leader-health gate (display-only). The rank skips the most recent ~21
      // sessions by construction (momentum lookbacks, skip_d=21), so the named "best place
      // to allocate" can be breaking down short-term while still ranking #1.
      //
      // Two-tier check, most-to-least data-rich:
      //   Tier 1 (basket detail pages): use the co-embedded THEME (const defined in
      //     baskets.html / baskets_*.html.j2 inline script), which carries MTF ladder_state
      //     and per-theme reco from the full theme_intel object. `const` at script-tag top
      //     level IS accessible as a global name but NOT via window.THEME — read by name.
      //   Tier 2 (allocation.html or any page without THEME): fall back to the allocation
      //     payload itself (d.ranks, d.rotation.breadth_laggards) — enough to show the chip
      //     when the leader has poor breadth or low durability without relying on THEME.
      //
      // This fixes the silent-degradation on allocation.html where THEME is absent.
      var faltering = null;
      try {
        var i, thm = null, lag = false, ladder = '', reco = '';
        // Tier 1: basket-page THEME (const in inline script, NOT on window)
        var TI = (typeof THEME !== 'undefined') ? THEME : null;
        if (TI && (h.id || h.name)) {
          var themes = TI.themes || [];
          for (i = 0; i < themes.length; i++) {
            if (themes[i] && (themes[i].id === h.id || themes[i].name === h.name)) { thm = themes[i]; break; }
          }
          var lags = TI.breadth_laggards || [];
          for (i = 0; i < lags.length; i++) {
            if (lags[i] && (lags[i].id === h.id || lags[i].name === h.name)) { lag = true; break; }
          }
          ladder = (thm && thm.mtf) ? String(thm.mtf.ladder_state || '').toUpperCase() : '';
          reco = thm ? String(thm.reco || '').toLowerCase() : '';
          if (lag || ladder === 'ROLLING OVER' || reco === 'hold' || reco === 'trim' || reco === 'avoid')
            faltering = { lag: lag, ladder: ladder, reco: reco, source: 'theme' };
        } else if (h.id || h.name) {
          // Tier 2: derive from the allocation payload's own data (available on ALL pages
          // including allocation.html, since this script already fetched the alloc JSON).
          var ranks = d.ranks || [];
          var leaderRank = null;
          for (i = 0; i < ranks.length; i++) {
            if (ranks[i] && (ranks[i].id === h.id || ranks[i].name === h.name)) { leaderRank = ranks[i]; break; }
          }
          // Check breadth_laggards from the rotation object (allocation payload carries this)
          var rotLags = (d.rotation && d.rotation.breadth_laggards) ? d.rotation.breadth_laggards : [];
          for (i = 0; i < rotLags.length; i++) {
            if (rotLags[i] && (rotLags[i].id === h.id || rotLags[i].name === h.name)) { lag = true; break; }
          }
          // Use headline.durability_bar as a proxy: < 0.35 = breaking down
          var durLow = (h.durability_bar != null && h.durability_bar < 0.35);
          if (lag || durLow)
            faltering = { lag: lag, ladder: '', reco: '', source: 'payload' };
        }
      } catch (e) { faltering = null; }
      var faltPill = faltering
        ? '<div class="nrc-falter">' + L('LEADER FALTERING SHORT-TERM', '领涨主题短期走弱') + '</div>'
        : '';
      // narration append — descriptive, no forward verbs; the breadth parenthetical only
      // when the leader really is on today's breadth-laggard board.
      var narEn = (d.narration && d.narration.en) || '';
      var narZh = (d.narration && d.narration.zh) || narEn;
      if (faltering && narEn) {
        narEn += ' Leader by trailing momentum — this rank excludes the most recent ~3 weeks by construction. Short-term it is breaking down' + (faltering.lag ? ' (worst breadth today)' : '') + '. Not an entry signal.';
        narZh += ' 该排名基于跳过最近约3周的长期动量。短期正在走弱' + (faltering.lag ? '（今日广度最差）' : '') + '。非入场信号。';
      }
      // ---- A3: the payload's own backtest verdict — rendered, not buried. Only when the
      // verdict says the absolute-trend gate did NOT validate on this market's history;
      // degrades silently on older payloads without the field.
      var expTag = '';
      try {
        var atg = d.backtest && d.backtest.verdict && d.backtest.verdict.absolute_trend_gate;
        if (atg && /did_not_hold/i.test(String(atg))) {
          expTag = '<div class="nrc-exp" title="' + esc(String(atg)) + '">' +
            L('EXPERIMENTAL — the trend gate did not validate on this market’s history; display-only.',
              '实验性 — 趋势闸门在本市场历史上未获验证；仅供展示。') + '</div>';
        }
      } catch (e2) { expTag = ''; }

      var chips = '';
      if (dbar != null) chips += '<span class="nrc-chip ' + (dbar >= 0.66 ? 'ok' : '') + '">' +
        L('durability', '持续性') + ' ' + Math.round(dbar * 100) + '/100</span>';
      if (h.hurst_tag) chips += '<span class="nrc-chip">' + L('trend', '趋势') + ': ' +
        L(h.hurst_tag, hurstZh[h.hurst_tag] || h.hurst_tag) + '</span>';
      if (h.crowded) chips += '<span class="nrc-chip hot">' + L('crowded → sized down', '拥挤 → 降仓') + '</span>';
      if (h.one_narrative) chips += '<span class="nrc-chip dom">' + L('one narrative dominates', '单一叙事主导') + '</span>';

      var book = (a.weights || []).slice(0, 3).map(function (w) {
        return '<div class="nrc-row"><span class="nm">' + esc(w.name) + '</span>' +
          '<span class="bar"><span class="fill" style="width:' + Math.min(100, (w.weight / 0.35 * 100)) + '%"></span></span>' +
          '<span class="wv">' + pct(w.weight) + '</span></div>'; }).join('');

      var handoff = (r.leader && r.challenger && r.challenger.name)
        ? (L('Leadership', '领跑') + ' <b>' + L(bov.view || '—', viewZh[bov.view] || bov.view || '—') + '</b> · ' +
           esc(r.leader.name) + ' ' + L('over', '领先') + ' ' + esc(r.challenger.name) +
           (r.margin != null ? ' (' + (+r.margin).toFixed(1) + ')' : ''))
        : '';

      el.innerHTML =
        '<div class="nrc-main">' +
          '<div class="nrc-lead">🔄 ' + L('Prevailing narrative — current best place to allocate',
                                          '主导叙事 — 当前最佳配置去向') + '</div>' +
          faltPill +
          '<div class="nrc-name">' + esc(h.name) + '</div>' +
          '<div class="nrc-sub">' + L('Suggested', '建议') + ' <b>' + pct(h.weight) + '</b> · ' +
            L('cash', '现金') + ' ' + pct(a.cash != null ? a.cash : h.cash) + '</div>' +
          '<div class="nrc-chips">' + chips + '</div>' +
          (narEn ? '<p class="nrc-read"><span class="l-en">' + narEn + '</span>' +
            '<span class="l-zh">' + narZh + '</span></p>' : '') +
          (book ? '<div class="nrc-book">' + book + '</div>' : '') +
          (handoff ? '<p class="nrc-read" style="margin-top:8px">' + handoff + '</p>' : '') +
          expTag +
        '</div>' +
        '<div class="nrc-side">' +
          '<div class="nrc-g"><span class="k">' + L('Themes in uptrend', '上行趋势') + '</span>' +
            '<span class="v">' + (bov.eligible != null ? bov.eligible + '/' + bov.total : '—') + '</span></div>' +
          '<div class="nrc-g"><span class="k">' + L('Suggested cash', '建议现金') + '</span>' +
            '<span class="v">' + pct(a.cash) + '</span></div>' +
          '<div class="nrc-g"><span class="k">' + L('One-narrative', '单一叙事度') + '</span>' +
            '<span class="v">' + (r.absorption != null ? pct(r.absorption) : '—') + '</span></div>' +
          '<a class="nrc-btn" href="' + page + '">' + L('Open the Rotation playbook →', '打开轮动策略 →') + '</a>' +
          '<div class="nrc-honest">' + L('Discipline, not a prediction · validated edge = drawdown control',
                                         '纪律而非预测 · 验证过的优势=回撤控制') + '</div>' +
        '</div>';
    });
})();

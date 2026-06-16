/* AI Desk for Thematic Investing — render the live, falsifiable per-theme leans on
   allocation*.html from site/allocationdata/ai_desk_<region>.json (+ ai_desk_track.json).
   Display-only: these are the desk's graded hypotheses, never a buy list or a size. Degrades
   silently to the static handoff contract above when the brief is absent (LLM off / pre-build). */
(function () {
  var root = document.getElementById('thematic-desk');
  if (!root) return;
  var region = root.getAttribute('data-region') || 'us';
  var BASE = 'allocationdata/';
  var esc = function (s) { return (s == null ? '' : String(s)).replace(/[&<>"]/g, function (c) {
    return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); };
  // bilingual chrome label — matches the page's l-en/l-zh toggle (theme.css hides one)
  var L = function (en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>'; };
  var leanColor = function (l) {
    return l === 'overweight' ? 'var(--up)' : (l === 'avoid' || l === 'underweight' ? 'var(--down)' : 'var(--muted)'); };
  var leanZh = { overweight: '超配', underweight: '低配', avoid: '回避' };
  var convZh = { low: '低', medium: '中', high: '高' };

  function getJSON(name) {
    return fetch(BASE + name + '?cb=' + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  Promise.all([getJSON('ai_desk_' + region + '.json'), getJSON('ai_desk_track.json')])
    .then(function (res) {
      var brief = res[0], track = res[1];
      var cardsEl = document.getElementById('td-cards');
      var emptyEl = document.getElementById('td-empty');
      var regimeEl = document.getElementById('td-regime');
      var watchEl = document.getElementById('td-watch');
      var theses = (brief && Array.isArray(brief.theses)) ? brief.theses : [];

      // track-record badge (by-market when available)
      if (track) {
        var ov = (track.by_market && track.by_market[region] && track.by_market[region].n)
          ? track.by_market[region] : (track.overall || {});
        var tb = document.getElementById('td-track');
        if (tb) {
          tb.innerHTML = ov.n
            ? L('track record: ' + Math.round((ov.hit_rate || 0) * 100) + '% not-falsified · n=' + ov.n,
                '战绩：' + Math.round((ov.hit_rate || 0) * 100) + '% 未被证伪 · n=' + ov.n)
            : L('track record: building (n=0)', '战绩：积累中（n=0）');
          tb.style.display = 'inline-block';
          tb.title = (track.calibration_note || '');
        }
      }

      if (brief && brief.regime_context && regimeEl) {
        regimeEl.innerHTML = '<b>' + L('Read', '解读') + ':</b> ' + esc(brief.regime_context);
        regimeEl.style.display = 'block';
      }

      if (!brief || !theses.length) {
        if (emptyEl) emptyEl.style.display = 'block';
        return;
      }

      cardsEl.innerHTML = theses.map(function (t) {
        var c = (t.falsifier && t.falsifier.check) || {};
        var scorable = c.kind === 'theme_rel_return';
        var col = leanColor(t.lean);
        var by = t.check_by ? ' <span class="cby">(' + L('by', '至') + ' ' + esc(t.check_by) + ')</span>' : '';
        var falsTxt = (t.falsifier && t.falsifier.text) ? esc(t.falsifier.text) : '';
        var unscored = scorable ? '' :
          ' <span class="chip" style="margin:0" title="no clean proxy ETF — logged, not graded">' +
          L('unscored', '不计分') + '</span>';
        return '<div class="tcard" style="--c:' + col + '">' +
          '<div class="lean"><span class="dir" style="color:' + col + ';border-color:' + col + '">' +
            esc(t.lean) + '<span class="l-zh"> / ' + (leanZh[t.lean] || '') + '</span></span>' +
            esc(t.subject) +
            '<span class="conv"> · ' + L(esc(t.conviction) + ' conviction', (convZh[t.conviction] || esc(t.conviction)) + ' 信心') + '</span>' +
            unscored + '</div>' +
          (t.thesis ? '<div class="body">' + esc(t.thesis) + '</div>' : '') +
          ((t.evidence && t.evidence.length) ? '<div class="ev">' + t.evidence.map(esc).join(' · ') + '</div>' : '') +
          (t.dissent ? '<div class="dis">' + L('Dissent', '异议') + ': ' + esc(t.dissent) + '</div>' : '') +
          (falsTxt ? '<div class="fals"><b>' + L('Falsified if', '证伪条件') + ':</b> ' + falsTxt + by + '</div>'
                   : (by ? '<div class="fals"><b>' + L('Check', '检验') + '</b>' + by + '</div>' : '')) +
          '</div>';
      }).join('');

      if (brief.emerging_watch && watchEl) {
        watchEl.innerHTML = '<b>🔭 ' + L('Emerging-narrative watch', '新兴叙事观察') + ':</b> ' + esc(brief.emerging_watch);
        watchEl.style.display = 'block';
      }
    });
})();

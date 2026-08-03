/* AI Desk for Thematic Investing — render the live, checkable per-theme leans on
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
  /* Display de-registration (operator ruling 2026-07-27, #3821): emerging_watch is LLM prose
     printed verbatim and used to arrive framed as "Kill criterion: <cond>". The scout prompt
     no longer asks for one (engine/thematic_desk.py), but this brief is regenerated on the
     gated desk lane, so an old-vintage ai_desk_<region>.json keeps the old wording until it
     re-runs — normalize the LABEL here too. The condition text itself is never touched. */
  var WATCH_LABEL = /\bkill[\s\-_]?criteri(?:on|a)\s*[:：]\s*|\bkill\s*[:：]\s*/gi;
  var WATCH_NOUN = /\bkill[\s\-_]?criteri(?:on|a)\b/gi;
  var watchEn = function (s) { return (s == null ? '' : String(s))
    .replace(WATCH_LABEL, 'Watching for: ').replace(WATCH_NOUN, 'watch condition'); };
  // one EN string on the payload (no zh field) — translate the label only, keep the read
  var watchZh = function (s) { return watchEn(s).replace(/Watching for:\s*/g, '关注条件：'); };
  var leanColor = function (l) {
    return l === 'overweight' ? 'var(--up)' : (l === 'avoid' || l === 'underweight' ? 'var(--down)' : 'var(--muted)'); };
  var leanZh = { overweight: '超配', underweight: '低配', avoid: '回避' };
  var convZh = { low: '低', medium: '中', high: '高' };

  function getJSON(name) {
    return fetch(BASE + name + '?cb=' + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  // theme-discovery radar (US only — the #td-candidates element exists only on that page)
  var candEl = document.getElementById('td-candidates');
  if (candEl) {
    getJSON('theme_candidates.json').then(function (d) {
      var cands = (d && Array.isArray(d.candidates)) ? d.candidates : [];
      if (!cands.length) { candEl.innerHTML = L('No candidate themes flagged today.', '今日无候选主题。'); return; }
      candEl.classList.remove('muted', 'sm');
      candEl.innerHTML = cands.map(function (c) {
        var names = (c.constituents || []).map(function (m) { return esc(m.ticker); }).join(', ');
        var ipo = c.ipo_wave ? ' <span class="chip warn" style="margin:0">' + L('IPO wave', 'IPO 潮') + '</span>' : '';
        return '<div class="pstance" style="margin:6px 0"><b>' + esc(c.label) + '</b> · ' +
          esc(c.n) + ' ' + L('names', '只') + ' · ' + L('cohesion', '凝聚度') + ' ' + esc(c.cohesion) +
          ' (↑' + esc(c.cohesion_chg) + ')' + ipo +
          '<div class="muted" style="font-size:11.5px">' + names + '</div></div>';
      }).join('') +
        '<div class="muted" style="font-size:11px;margin-top:6px">' +
        esc((d.phase0 && d.phase0.verdict) || d.verdict || '') + '</div>';
    });
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
            ? L('track record: ' + Math.round((ov.hit_rate || 0) * 100) + '% holding · n=' + ov.n,
                '战绩：' + Math.round((ov.hit_rate || 0) * 100) + '% 仍成立 · n=' + ov.n)
            : L('track record: building (n=0)', '战绩：积累中（n=0）');
          tb.style.display = 'inline-block';
          tb.title = (track.calibration_note || '');
        }
      }

      // macro-narrative backdrop (coincident market-level GDELT flow — not per-theme)
      var mn = brief && brief.macro_narrative;
      var bdEl = document.getElementById('td-backdrop');
      if (mn && mn.dominant_themes && mn.dominant_themes.length && bdEl) {
        var themes = mn.dominant_themes.map(function (t) { return esc(t.theme) + ' (' + t.n + ')'; }).join(', ');
        var us = (mn.unscheduled_share != null)
          ? ' · ' + Math.round(mn.unscheduled_share * 100) + '% ' + L('unscheduled', '非预定') : '';
        bdEl.innerHTML = '<b>🗞 ' + L('Macro backdrop', '宏观背景') + ':</b> ' + themes + us +
          ' <span class="muted">' + L('(coincident market-level news flow, not per-theme)', '（同步的市场级新闻流，非个别主题）') + '</span>';
        bdEl.style.display = 'block';
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
          (falsTxt ? '<div class="fals"><b>' + L('Changes this read', '改判条件') + ':</b> ' + falsTxt + by + '</div>'
                   : (by ? '<div class="fals"><b>' + L('Check', '检验') + '</b>' + by + '</div>' : '')) +
          '</div>';
      }).join('');

      if (brief.emerging_watch && watchEl) {
        watchEl.innerHTML = '<b>🔭 ' + L('Emerging-narrative watch', '新兴叙事观察') + ':</b> ' +
          L(esc(watchEn(brief.emerging_watch)), esc(watchZh(brief.emerging_watch)));
        watchEl.style.display = 'block';
      }

      // adversarial panel transparency — what each analyst argued (collapsed)
      var panel = brief.panel || {};
      var roles = Object.keys(panel);
      var panelEl = document.getElementById('td-panel');
      var panelWrap = document.getElementById('td-panel-wrap');
      if (roles.length && panelEl && panelWrap) {
        var ROLE = { trend_rider: ['Trend-rider', '趋势跟随'], crowding_skeptic: ['Crowding-skeptic', '拥挤质疑'],
                     narrative_scout: ['Narrative scout', '叙事侦察'], macro_regime: ['Macro regime', '宏观环境'] };
        panelEl.innerHTML = roles.map(function (k) {
          var p = panel[k] || {}; var lab = ROLE[k] || [k, k];
          var leans = (p.leans || []).filter(function (l) { return l && l.subject; })
            .map(function (l) { return esc(l.lean) + ' ' + esc(l.subject); }).join(', ');
          return '<div class="pstance"><b>' + L(lab[0], lab[1]) + ':</b> ' + esc(p.stance || '') +
            (leans ? ' <span class="muted">[' + leans + ']</span>' : '') + '</div>';
        }).join('');
        panelWrap.style.display = 'block';
      }
    });
})();

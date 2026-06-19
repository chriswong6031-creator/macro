/* Forming Narratives panel — renders engine/narrative_emergence.py output.
   Shared across all baskets pages (us / china / hk / canada / intl). Self-contained:
   injects its own scoped styles, renders nothing (display:none) when the JSON is absent,
   so it is always safe to include. Bilingual via l-en/l-zh spans (theme.js toggles them).

   DROP-IN: `{% include "_forming_narratives.html.j2" %}` in a baskets template, then copy
   site/forming_narratives.js into site/ in the builder (like lightweight-charts.js). Reads
   <base>/narrative_emergence.json (base defaults to "basketdata/"). DISPLAY-ONLY: a noisy
   watchlist / avoid-the-peak lens, never a buy list. */
(function () {
  const L = (en, zh) => `<span class="l-en">${en}</span><span class="l-zh">${zh == null ? en : zh}</span>`;
  const esc = s => (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const pct = x => x == null ? '—' : (x >= 0 ? '+' : '') + (x).toFixed(1) + '%';

  // entry grade → chip color role. GREEN = clean entry (good place to look), RED = chase.
  const GRADE_COLOR = { intrend: 'var(--up)', steady: 'var(--up)', na: 'var(--muted)',
                        stretched: 'var(--warn,#f59e0b)', parabolic: 'var(--down)' };
  const SCORE_COLOR = { 'ne-hot': 'var(--up)', 'ne-warm': 'var(--link,#5aa7ff)',
                        'ne-early': 'var(--muted)', 'ne-faint': 'var(--muted)' };

  function injectStyles() {
    if (document.getElementById('ne-styles')) return;
    const css = `
    #forming-narratives{margin-top:6px}
    #forming-narratives .ne-sub{color:var(--muted);font-size:13px;margin:2px 0 10px;max-width:80ch;line-height:1.5}
    #forming-narratives .ne-watch{border-left:3px solid var(--link,#5aa7ff);background:color-mix(in srgb,var(--link,#5aa7ff) 8%,transparent);
      padding:8px 11px;border-radius:6px;margin:0 0 10px;font-size:13px}
    #forming-narratives .ne-attn{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 12px;font-size:12px;color:var(--muted)}
    #forming-narratives .ne-attn .ne-tag{background:var(--card2,rgba(127,127,127,.12));border:1px solid var(--border,rgba(127,127,127,.25));
      border-radius:999px;padding:2px 9px;white-space:nowrap}
    #forming-narratives .ne-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:11px}
    #forming-narratives .ne-card{border:1px solid var(--border,rgba(127,127,127,.25));border-radius:10px;padding:13px 14px;
      background:var(--card,rgba(127,127,127,.04));scroll-margin-top:80px}
    #forming-narratives .ne-card.ne-flash{box-shadow:0 0 0 2px var(--link,#5aa7ff);transition:box-shadow .3s}
    #forming-narratives .ne-hd{display:flex;align-items:flex-start;gap:10px;justify-content:space-between}
    #forming-narratives .ne-name{font-weight:650;font-size:14.5px;line-height:1.25}
    #forming-narratives .ne-badge{flex:none;text-align:center;min-width:54px}
    #forming-narratives .ne-score{font-variant-numeric:tabular-nums;font-weight:700;font-size:20px;line-height:1}
    #forming-narratives .ne-lab{font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
    #forming-narratives .ne-why{font-size:12.5px;color:var(--fg,inherit);opacity:.92;margin:8px 0 9px;line-height:1.5}
    #forming-narratives .ne-legs{display:flex;gap:3px;margin:0 0 10px}
    #forming-narratives .ne-leg{flex:1;height:5px;border-radius:3px;background:var(--card2,rgba(127,127,127,.18));overflow:hidden}
    #forming-narratives .ne-leg>i{display:block;height:100%;background:var(--link,#5aa7ff)}
    #forming-narratives .ne-rec-h{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:0 0 5px}
    #forming-narratives .ne-recs{display:flex;flex-wrap:wrap;gap:6px}
    #forming-narratives .ne-tk{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border,rgba(127,127,127,.25));
      border-radius:7px;padding:3px 8px;font-size:12px;font-variant-numeric:tabular-nums}
    #forming-narratives .ne-tk .ne-dot{width:7px;height:7px;border-radius:50%}
    #forming-narratives .ne-tk b{font-weight:650}
    #forming-narratives .ne-tk small{color:var(--muted)}
    #forming-narratives .ne-caution{margin-top:9px;font-size:11.5px;color:var(--warn,#f59e0b)}
    #forming-narratives details.ne-cav{margin-top:9px;font-size:11.5px;color:var(--muted)}
    #forming-narratives details.ne-cav summary{cursor:pointer;user-select:none}
    #forming-narratives details.ne-cav ul{margin:6px 0 0;padding-left:18px;line-height:1.5}
    #forming-narratives .ne-note{font-size:11px;color:var(--muted);margin-top:12px;line-height:1.5;max-width:90ch}`;
    const st = document.createElement('style'); st.id = 'ne-styles'; st.textContent = css;
    document.head.appendChild(st);
  }

  function legBar(legs) {
    const order = ['tighten', 'cohesion', 'momentum', 'novelty', 'size'];
    const lab = { tighten: ['Tightening', '收紧'], cohesion: ['Co-movement', '共动'],
                  momentum: ['Momentum', '动能'], novelty: ['Novelty', '新颖'], size: ['Size', '规模'] };
    return `<div class="ne-legs" title="${order.map(k => lab[k][0] + ' ' + Math.round((legs[k] || 0) * 100) + '%').join(' · ')}">`
      + order.map(k => `<div class="ne-leg"><i style="width:${Math.round((legs[k] || 0) * 100)}%"></i></div>`).join('') + `</div>`;
  }

  function tickerChip(r) {
    const col = GRADE_COLOR[r.grade] || 'var(--muted)';
    const ext = r.ext == null ? '' : ` <small>${pct(r.ext)}</small>`;
    const tip = esc((r.name || r.ticker) + (r.sector ? ' · ' + r.sector : '')) + ' — ' +
      esc(r.grade_en || r.grade) + ' entry';
    return `<span class="ne-tk" title="${tip}"><span class="ne-dot" style="background:${col}"></span><b>${esc(r.ticker)}</b>${ext}</span>`;
  }

  function card(nv) {
    const sc = SCORE_COLOR[(nv.score_label || {}).css] || 'var(--muted)';
    const recs = (nv.recommended || []).map(tickerChip).join('');
    let caution = '';
    if (nv.hype && nv.hype.ipo_wave)
      caution += `🪧 ${L('Recent-IPO wave — hype tends to mark late, not early.', '近期 IPO 潮 — 炒作往往标志偏晚而非偏早。')}<br>`;
    if (nv.hype && nv.hype.stretched_share >= 0.4)
      caution += `⚠ ${L(Math.round(nv.hype.stretched_share * 100) + '% of the cohort is already stretched/parabolic.',
        '已有 ' + Math.round(nv.hype.stretched_share * 100) + '% 的组合处于拉伸／抛物状态。')}<br>`;
    if (nv.attention_aligned)
      caution += `🔭 ${L('Sits under a currently-hot macro narrative — elevated attention raises the bar.',
        '处于当前热门宏观叙事之下 — 关注升温抬高门槛。')}`;
    const cav = `<details class="ne-cav"><summary>${L('Why this is a watchlist, not a buy list', '为何这是观察清单而非买入清单')}</summary>`
      + `<ul>` + (nv.caveats_en || []).map((c, i) =>
        `<li>${L(esc(c), esc((nv.caveats_zh || [])[i] || c))}</li>`).join('') + `</ul></details>`;
    return `<div class="ne-card" id="ne-${esc(nv.signature)}">
      <div class="ne-hd">
        <div class="ne-name">${L(esc(nv.name_en), esc(nv.name_zh))}</div>
        <div class="ne-badge"><div class="ne-score" style="color:${sc}">${nv.score}</div>
          <div class="ne-lab">${L(esc((nv.score_label || {}).en), esc((nv.score_label || {}).zh))}</div></div>
      </div>
      ${legBar(nv.legs || {})}
      <div class="ne-why">${L(esc(nv.why_en), esc(nv.why_zh))}</div>
      <div class="ne-rec-h">${L('Where to look — clean entry first', '该看哪里 — 干净入场优先')}</div>
      <div class="ne-recs">${recs || '<small style="color:var(--muted)">' + L('no clean read', '无清晰读数') + '</small>'}</div>
      ${caution ? `<div class="ne-caution">${caution}</div>` : ''}
      ${cav}
    </div>`;
  }

  function attnBar(d) {
    let html = '';
    if (d.ai_watch && d.ai_watch.text) {
      const conf = d.ai_watch.confidence ? ` <small>(${esc(d.ai_watch.confidence)} ${L('confidence', '信心')})</small>` : '';
      html += `<div class="ne-watch">🧭 <b>${L('AI scout watch', 'AI 侦察观察')}</b>${conf}: ${L(esc(d.ai_watch.text), esc(d.ai_watch.text))}</div>`;
    }
    if (d.attention && (d.attention.dominant || []).length) {
      const tags = d.attention.dominant.map(t =>
        `<span class="ne-tag">${esc(t.theme)} · ${t.n}</span>`).join('');
      html += `<div class="ne-attn">${L('Macro attention now:', '当前宏观关注：')} ${tags}
        <span style="flex-basis:100%;height:0"></span>
        <span>${L(esc(d.attention.note_en), esc(d.attention.note_zh))}</span></div>`;
    }
    return html;
  }

  window.renderFormingNarratives = function (opts) {
    const base = (opts && opts.base) || 'basketdata/';
    const sec = document.getElementById('forming-narratives');
    if (!sec) return;
    fetch(base + 'narrative_emergence.json', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d || !(d.narratives || []).length) { sec.style.display = 'none'; return; }
        injectStyles();
        sec.innerHTML = `<h2><span class="idx">★</span>🔥 ${L('Forming Narratives', '成形叙事')}
            <span class="sect-tag">${L('emerging themes our models see · ' + esc(d.market_en),
              '模型识别的新兴主题 · ' + esc(d.market_zh))}</span></h2>
          <p class="ne-sub">${L(esc(d.note_en), esc(d.note_zh))}</p>
          ${attnBar(d)}
          <div class="ne-grid">${d.narratives.map(card).join('')}</div>
          <p class="ne-note">${L(
            'Scanned ' + (d.n_universe || '—') + ' names as of ' + esc(d.as_of) + '. The 0–100 score ranks how clearly a narrative is FORMING (tightening co-movement), not how much it will pay — early-entry return edge is ~0 and negatively skewed. Promote a confirmed candidate to a curated basket with scripts/promote_candidate.py.',
            '截至 ' + esc(d.as_of) + ' 扫描了 ' + (d.n_universe || '—') + ' 只个股。0–100 分衡量叙事成形的清晰度（共动收紧），而非回报 — 早期入场优势≈0 且负偏。可用 scripts/promote_candidate.py 将确认的候选提升为人工策选篮子。')}</p>`;
        // deep-link flash from an alert anchor (#ne-<sig>)
        if (location.hash.startsWith('#ne-')) {
          const el = document.getElementById(location.hash.slice(1));
          if (el) { el.classList.add('ne-flash'); el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => el.classList.remove('ne-flash'), 1400); }
        }
      })
      .catch(() => { sec.style.display = 'none'; });
  };
})();

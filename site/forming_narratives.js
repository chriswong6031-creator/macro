/* Forming Narratives panel — renders engine/narrative_emergence.py output.
   Shared across all baskets pages (us / china / hk / canada / intl). Self-contained:
   injects its own scoped styles, renders nothing (display:none) when the JSON is absent,
   so it is always safe to include. Bilingual via l-en/l-zh spans (theme.js toggles them).

   DROP-IN: `{% include "_forming_narratives.html.j2" %}` in a baskets template, then copy
   site/forming_narratives.js into site/ in the builder (like lightweight-charts.js). Reads
   <base>/narrative_emergence.json (base defaults to "basketdata/"). DISPLAY-ONLY: a noisy
   watchlist lens, never a buy list. */
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
    #forming-narratives .ne-tk{position:relative;display:inline-flex;align-items:center;gap:6px;
      border:1px solid var(--border,rgba(127,127,127,.25));border-radius:7px;padding:3px 9px;font-size:12px;
      cursor:pointer;outline:none;transition:border-color .15s ease,background .15s ease}
    #forming-narratives .ne-tk:hover,#forming-narratives .ne-tk:focus-visible,#forming-narratives .ne-tk.ne-open{
      border-color:var(--link,#5aa7ff);background:color-mix(in srgb,var(--link,#5aa7ff) 7%,transparent)}
    #forming-narratives .ne-tk .ne-dot{flex:none;width:7px;height:7px;border-radius:50%}
    #forming-narratives .ne-tk-nm{font-weight:650;line-height:1.2}
    #forming-narratives .ne-tk small{color:var(--muted);font-variant-numeric:tabular-nums}
    /* crafted code popover — revealed on hover/focus (mouse, keyboard) or pinned on tap (touch) */
    #forming-narratives .ne-pop{position:absolute;left:50%;bottom:calc(100% + 10px);z-index:50;
      transform:translateX(-50%) translateY(5px) scale(.96);transform-origin:bottom center;
      display:flex;flex-direction:column;align-items:center;gap:3px;min-width:96px;max-width:220px;
      padding:9px 13px;border-radius:10px;text-align:center;
      background:var(--panel2,#1e222a);border:1px solid var(--line,rgba(127,127,127,.3));
      box-shadow:0 12px 30px rgba(0,0,0,.32),0 3px 9px rgba(0,0,0,.2);
      opacity:0;visibility:hidden;pointer-events:none;transition:opacity .17s ease,transform .17s ease}
    #forming-narratives .ne-tk:hover .ne-pop,#forming-narratives .ne-tk:focus-within .ne-pop,#forming-narratives .ne-tk.ne-open .ne-pop{
      opacity:1;visibility:visible;transform:translateX(-50%) translateY(0) scale(1)}
    #forming-narratives .ne-pop::before,#forming-narratives .ne-pop::after{content:"";position:absolute;top:100%;left:50%;width:0;height:0}
    #forming-narratives .ne-pop::before{transform:translateX(-50%);border:7px solid transparent;border-top-color:var(--line,rgba(127,127,127,.3))}
    #forming-narratives .ne-pop::after{transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--panel2,#1e222a)}
    #forming-narratives .ne-pop-lab{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
    #forming-narratives .ne-pop-code{font-size:15.5px;font-weight:700;letter-spacing:.02em;line-height:1.15;color:var(--text,inherit);
      font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:nowrap}
    #forming-narratives .ne-pop-sub{font-size:10.5px;color:var(--muted);line-height:1.4}
    #forming-narratives .ne-flags{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0 8px}
    #forming-narratives .ne-flag{font-size:11px;color:var(--warn,#f59e0b);background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:6px;padding:1px 7px}`;
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
    // the chip reads as the company name (full native name in 中文 where the market has one,
    // e.g. A-shares; English elsewhere) — with the stock code in a tap/hover popover.
    const nm_en = r.name || r.ticker;
    const nm_zh = r.name_zh || r.name || r.ticker;
    const label = L(esc(nm_en), esc(nm_zh));
    const code = esc(r.ticker);
    const grade = L(esc(r.grade_en || r.grade) + ' entry', esc(r.grade_zh || r.grade) + ' 入场');
    const sect = r.sector ? esc(r.sector) + ' · ' : '';
    const aria = esc(nm_en + ' (' + r.ticker + ')');
    return `<span class="ne-tk" tabindex="0" role="button" aria-label="${aria}">`
      + `<span class="ne-dot" style="background:${col}"></span>`
      + `<b class="ne-tk-nm">${label}</b>${ext}`
      + `<span class="ne-pop" role="tooltip">`
        + `<span class="ne-pop-lab">${L('Code', '代码')}</span>`
        + `<span class="ne-pop-code">${code}</span>`
        + `<span class="ne-pop-sub">${sect}${grade}</span>`
      + `</span></span>`;
  }

  function card(nv) {
    const sc = SCORE_COLOR[(nv.score_label || {}).css] || 'var(--muted)';
    const recs = (nv.recommended || []).map(tickerChip).join('');
    // Hype flags — kept as compact inline chips
    let flags = '';
    if (nv.hype && nv.hype.ipo_wave) flags += `<span class="ne-flag">🪧 ${L('IPO wave', 'IPO潮')}</span>`;
    if (nv.hype && nv.hype.stretched_share >= 0.4)
      flags += `<span class="ne-flag">⚠ ${Math.round(nv.hype.stretched_share * 100)}% ${L('stretched', '超伸')}</span>`;
    if (nv.attention_aligned) flags += `<span class="ne-flag">🔭 ${L('hot narrative', '热门叙事')}</span>`;
    // why_en/why_zh promoted to data-tip on the score pill
    const scoreTipEn = esc(nv.why_en || '');
    const scoreTipZh = esc(nv.why_zh || nv.why_en || '');
    return `<div class="ne-card" id="ne-${esc(nv.signature)}">
      <div class="ne-hd">
        <div class="ne-name">${L(esc(nv.name_en), esc(nv.name_zh))}</div>
        <div class="ne-badge" data-tip-en="${scoreTipEn}" data-tip-zh="${scoreTipZh}" style="cursor:default">
          <div class="ne-score" style="color:${sc}">${nv.score}</div>
          <div class="ne-lab">${L(esc((nv.score_label || {}).en), esc((nv.score_label || {}).zh))}</div>
        </div>
      </div>
      ${flags ? `<div class="ne-flags">${flags}</div>` : ''}
      <div class="ne-recs">${recs || '<small style="color:var(--muted)">' + L('no clean read', '无清晰读数') + '</small>'}</div>
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
        const scanNote = L(
          'Scanned ' + (d.n_universe || '—') + ' names as of ' + esc(d.as_of) + '. Scores rank narrative formation, not expected return. A noisy watchlist lens — not a buy list.',
          '截至 ' + esc(d.as_of) + ' 扫描了 ' + (d.n_universe || '—') + ' 只个股。分数衡量叙事成形程度，并非预期回报。这是嘈杂的观察清单，并非买入清单。'
        );
        sec.innerHTML = `<h2><span class="idx">★</span>🔥 ${L('Forming Narratives', '成形叙事')}
            <span class="sect-tag">${L('emerging themes our models see · ' + esc(d.market_en),
              '模型识别的新兴主题 · ' + esc(d.market_zh))}</span>
            <span style="cursor:default;color:var(--muted);font-size:13px;font-weight:400" data-tip-en="${esc(scanNote.replace(/<[^>]+>/g,''))}" data-tip-zh="${esc(scanNote.replace(/<[^>]+>/g,''))}">?</span></h2>
          <p class="ne-sub">${L(esc(d.note_en), esc(d.note_zh))}</p>
          ${attnBar(d)}
          <div class="ne-grid">${d.narratives.map(card).join('')}</div>`;
        // hover/focus reveals the code popover via CSS; a tap pins it (touch, where hover is
        // unreliable). Close on outside tap or Escape; only one pinned at a time.
        sec.querySelectorAll('.ne-tk').forEach(chip => {
          chip.addEventListener('click', e => {
            const open = chip.classList.contains('ne-open');
            sec.querySelectorAll('.ne-tk.ne-open').forEach(c => c.classList.remove('ne-open'));
            if (!open) chip.classList.add('ne-open');
            e.stopPropagation();
          });
        });
        if (!window.__neTkBound) {
          window.__neTkBound = true;
          document.addEventListener('click', () =>
            document.querySelectorAll('#forming-narratives .ne-tk.ne-open').forEach(c => c.classList.remove('ne-open')));
          document.addEventListener('keydown', e => {
            if (e.key === 'Escape')
              document.querySelectorAll('#forming-narratives .ne-tk.ne-open').forEach(c => c.classList.remove('ne-open'));
          });
        }
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

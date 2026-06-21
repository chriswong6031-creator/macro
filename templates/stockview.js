/* stockview.js — the ONE shared renderer for every market's single-stock analyzer.
 *
 * It renders `rec.view` (engine/stock_view.build_view) into the decision-first layout:
 *   Layer 1 GLANCE   — verdict band · timing sub-line · 4-axis fingerprint · honesty row
 *   Layer 2 EVIDENCE — one read per dimension · the country evidence slot
 * The deep layer (financials, chart, calibration) stays in each page's own panels.
 *
 * Self-contained: bilingual is baked as <span class="l-en"/><span class="l-zh"/> (theme.css
 * toggles on html[data-lang]), so NO re-render on language switch. No framework, no deps.
 * Every field is guarded — a missing leg is simply omitted, never a blank placeholder.
 *
 * Anti-drift contract: all five templates call window.SV.mount(rec); the layout is a literal
 * projection of view's field order, and per-market truth (CN mean-reversion, HK no-alpha,
 * valuation neutrality, A/H inversion) arrives as DATA in the model — never decided here.
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  // bilingual span pair (baked; CSS shows the active language)
  function B(en, zh) {
    return '<span class="l-en">' + esc(en) + '</span>' +
           '<span class="l-zh">' + esc(zh == null ? en : zh) + '</span>';
  }
  function el(id) { return document.getElementById(id); }
  function set(id, html) { var e = el(id); if (e) { e.innerHTML = html; e.style.display = html ? '' : 'none'; } }
  function toneClass(t) { return 'sv-t-' + (t || 'neutral'); }

  // ---- Layer 1a: the ONE verdict band ----------------------------------------
  function renderDecision(view) {
    var d = view.decision || {};
    if (!d.headline) return '';
    var band = d.band || 'neutral';
    var score = (d.score == null) ? '' : d.score;
    var gauge = '<div class="sv-gauge sv-band-' + esc(band) + '">' +
      '<span class="sv-band-word">' + B(d.band_en || '', d.band_zh || '') + '</span>' +
      (score !== '' ? '<span class="sv-score">' + esc(score) + '<small>/100</small></span>' : '') +
      '</div>';

    var trust = d.trust || {};
    // a SHORT badge word (full explanation in the tooltip) so it never reads as a paragraph
    var TRUST_SHORT = {
      'event-edge': ['Validated edge', '已验证优势'], 'validated': ['Validated edge', '已验证优势'],
      'go': ['Validated edge', '已验证优势'], 'context': ['Context only', '仅供参考'],
      'reversal': ['Reversal · CN', '均值回归 · A股'], 'screen': ['Screen only', '仅筛选']
    };
    var ts = TRUST_SHORT[trust.tier] || (trust.en ? [trust.en, trust.zh] : null);
    var trustChip = ts ? '<span class="sv-trust ' + esc(trust.css || '') +
      '" title="' + esc(trust.en || '') + '">' + B('🛈 ' + ts[0], '🛈 ' + ts[1]) + '</span>' : '';

    var headline = '<div class="sv-headline">' + B(d.headline, d.headline_zh) + '</div>';
    var gloss = (d.gloss) ? '<div class="sv-gloss">' + B(d.gloss, d.gloss_zh) + '</div>' : '';

    // timing sub-line (cycle + entry tag) — quiet, UNDER the verb, never a 2nd verb
    var t = d.timing || {};
    var timingBits = [];
    if (t.state_label) timingBits.push(B(t.state_label, t.state_label));
    if (t.tag) timingBits.push('<span class="sv-tag sv-urg-' + esc(t.urgency || '') + '">' + B(t.tag, t.tag_zh) + '</span>');
    // entry-quality grade is already shown by the header eq badge — not restated here.
    if (t.bc_score != null) timingBits.push(B('bottom-confidence ' + t.bc_score, '底部信心 ' + t.bc_score));
    var timing = timingBits.length
      ? '<div class="sv-timing"><span class="sv-timing-lbl">' + B('Timing', '时机') + ':</span> ' +
        timingBits.join(' <span class="sv-dot">·</span> ') +
        (t.capped_by_entry ? ' <span class="sv-cap">' + B('(size held to entry conviction)', '（仓位受入场信心限制）') + '</span>' : '') +
        '</div>'
      : '';

    // suggested size
    var size = d.size || {};
    var sizeLine = (size.pct != null)
      ? '<div class="sv-size"><span class="sv-size-lbl">' + B('Suggested size', '建议仓位') + '</span>' +
        '<span class="sv-size-pct sv-size-' + esc(size.bucket || '') + '">' + esc(size.pct) + '%</span>' +
        (size.bucket ? '<span class="sv-size-bk">' + B(size.bucket, size.bucket) + '</span>' : '') +
        '</div>'
      : '';

    // regime tilt (US calm/stress) — one quiet chip
    var rg = d.regime;
    var regime = (rg && rg.en) ? '<div class="sv-regime ' + esc(rg.css || '') + '">' + B(rg.en, rg.zh) + '</div>' : '';

    return '<div class="sv-decision sv-state-' + esc(d.state || 'ok') + '">' +
      '<div class="sv-verdict-band">' + gauge +
        '<div class="sv-verdict-text">' + headline + gloss + '</div>' +
        trustChip +
      '</div>' + timing + sizeLine + regime + '</div>';
  }

  // ---- Layer 1b: 4-axis fingerprint ------------------------------------------
  function renderFingerprint(view) {
    var axes = (view.fingerprint || {}).axes || [];
    if (!axes.length) return '';
    var bars = axes.map(function (a) {
      var pct = (a.pct == null) ? null : Math.max(0, Math.min(100, a.pct));
      var fill = (pct == null) ? '' :
        '<span class="sv-axis-fill" style="width:' + pct + '%"></span>';
      var warn = (a.flags && a.flags.accounting === 'warn') ? ' sv-axis-warn' : '';
      return '<div class="sv-axis' + warn + '">' +
        '<div class="sv-axis-top"><span class="sv-axis-lbl">' + B(a.label, a.label_zh) + '</span>' +
        (pct == null ? '<span class="sv-axis-na">' + B('n/a', '无') + '</span>'
                     : '<span class="sv-axis-pct">' + pct + '</span>') + '</div>' +
        '<div class="sv-axis-bar">' + fill + '</div></div>';
    }).join('');
    return '<div class="sv-fingerprint">' + bars + '</div>';
  }

  // ---- Layer 1c: honesty row (why it works · what would flip it) --------------
  function renderHonesty(view) {
    var d = view.decision || {};
    var why = d.why || [];
    var flips = view.falsifiers || [];
    if (!why.length && !flips.length && d.state !== 'conflict') return '';

    var conflict = '';
    if (d.state === 'conflict') {
      var pills = (d.conflict_pillars || []).map(function (p) { return B(p.en, p.zh); }).join(', ');
      conflict = '<div class="sv-conflict">⚠ ' + B('Conflict', '信号冲突') +
        (pills ? ': <span class="sv-conflict-p">' + pills + '</span>' : '') + '</div>';
    }

    var bulls = why.length
      ? '<ul class="sv-list">' + why.map(function (w) { return '<li>' + B(w.en, w.zh) + '</li>'; }).join('') + '</ul>'
      : '<p class="sv-empty">' + B('—', '—') + '</p>';
    var bears = flips.length
      ? '<ul class="sv-list">' + flips.map(function (f) {
          return '<li class="sv-fl-' + esc(f.severity || 'med') + '">' + B(f.en, f.zh) + '</li>';
        }).join('') + '</ul>'
      : '<p class="sv-empty">' + B('No active red flags', '暂无风险信号') + '</p>';

    return conflict + '<div class="sv-honesty">' +
      '<div class="sv-col sv-why"><div class="sv-col-h">' + B('Why it could work', '看多理由') + '</div>' + bulls + '</div>' +
      '<div class="sv-col sv-flip"><div class="sv-col-h">' + B('What would flip this', '何为反转信号') + '</div>' + bears + '</div>' +
      '</div>';
  }

  // ---- Layer 2a: evidence lanes (one read per dimension) ----------------------
  var EV_ORDER = ['trend', 'momentum', 'extension', 'squeeze', 'rel_strength', 'valuation',
                  'quality', 'positioning', 'volatility', 'ownership', 'macro', 'catalyst'];
  function renderEvidence(view) {
    var ev = view.evidence || {};
    var cells = EV_ORDER.filter(function (k) { return ev[k]; }).map(function (k) {
      var c = ev[k];
      var gloss = c.gloss ? ' title="' + esc(c.gloss) + '"' : '';
      return '<div class="sv-dim ' + toneClass(c.tone) + '"' + gloss + '>' +
        '<div class="sv-dim-lbl">' + B(c.label, c.label_zh) + '</div>' +
        '<div class="sv-dim-val">' + B(c.value, c.value_zh) + '</div>' +
        (c.gloss ? '<div class="sv-dim-gloss">' + B(c.gloss, c.gloss_zh) + '</div>' : '') +
        '</div>';
    }).join('');
    if (!cells) return '';
    return '<div class="sv-evidence-wrap"><div class="sv-sec-h">' +
      B('The evidence', '依据') + '</div><div class="sv-evidence">' + cells + '</div></div>';
  }

  // ---- Layer 2b: country evidence slot (cards[] union) ------------------------
  function renderCountrySlot(view) {
    var cards = ((view.country_slot || {}).cards) || [];
    if (!cards.length) return '';
    var html = cards.map(function (card) {
      var rows = (card.rows || []).map(function (r) {
        var col = r.color ? ' sv-c-' + esc(r.color) : '';
        return '<div class="sv-crow"><span class="sv-ck">' + B(r.k, r.k_zh) + '</span>' +
          '<span class="sv-cv' + col + '">' + B(r.v, r.v_zh) + '</span></div>';
      }).join('');
      var foot = card.footnote ? '<div class="sv-cfoot">' + B(card.footnote, card.footnote_zh || card.footnote) + '</div>' : '';
      return '<div class="sv-card sv-card-' + esc(card.kind) + '">' +
        '<div class="sv-card-h">' + B(card.title, card.title_zh) + '</div>' + rows + foot + '</div>';
    }).join('');
    return '<div class="sv-country">' + html + '</div>';
  }

  // ---- mount: fill the page's view slots from rec.view -----------------------
  function mount(rec) {
    var view = rec && rec.view;
    if (!view) return false;                       // caller falls back to legacy render
    set('sv-decision', renderDecision(view));
    set('sv-fingerprint', renderFingerprint(view));
    set('sv-honesty', renderHonesty(view));
    set('sv-evidence', renderEvidence(view));
    set('sv-country', renderCountrySlot(view));
    return true;
  }

  window.SV = { mount: mount, renderDecision: renderDecision,
                renderFingerprint: renderFingerprint, renderHonesty: renderHonesty,
                renderEvidence: renderEvidence, renderCountrySlot: renderCountrySlot };
})();

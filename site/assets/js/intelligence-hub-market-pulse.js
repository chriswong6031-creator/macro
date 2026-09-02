/* R1A-M Intelligence Hub Market Pulse — route-scoped browser controller.
 *
 * Consumes ONLY /api/intelligence-hub/market-pulse (the deliberately public,
 * bounded batch projection — app/intelligence_hub_market_pulse.py). It owns
 * every [data-ihmp-symbol] node on this page; generic templates/live.js is
 * excluded from these rows on purpose (the rendered markup carries zero
 * .nb-px[data-sym] nodes — see templates/intelligence_hub.html.j2's `ihmp`
 * macro), so this controller is the ONLY writer of a Market Pulse price on
 * intelligence_hub.html.
 *
 * Contract with the page
 * -----------------------
 *   [data-ihmp-root]          the page-level instrument (state axes + status)
 *   [data-ihmp-availability]  \
 *   [data-ihmp-freshness]      | set on the root element itself
 *   [data-ihmp-session]        |
 *   [data-ihmp-coverage]      /
 *   [data-ihmp-baseline-at]   nightly baseline timestamp (never overwritten)
 *   [data-ihmp-status]        the one bilingual status line (aria-live owner)
 *   [data-ihmp-symbol]        one roster-row quote cluster (may repeat)
 *   [data-ihmp-price]         \
 *   [data-ihmp-abs]            | children of a [data-ihmp-symbol] cluster
 *   [data-ihmp-pct]           /
 *
 * Honesty / atomicity law
 * ------------------------
 * One batch request per refresh, one Terminal `view=regular` call behind it.
 * A response is fully checked (schema/projection/source_view/state axes/
 * arithmetic/forbidden fields) into an IMMUTABLE candidate model before any
 * DOM write. Every accepted symbol's every occurrence is written together,
 * inside ONE requestAnimationFrame — no panel ever shows a newer price than
 * a sibling panel showing the same symbol. A row this refresh could not
 * honestly update (suppressed by generation/ordering, or simply absent from
 * the response) keeps exactly the value it already had — baked, or the last
 * accepted quote — never blanked.
 */
(function () {
  'use strict';

  var ROOT = document.querySelector('[data-ihmp-root]');
  if (!ROOT) return;  // this route did not render the instrument; nothing to do

  var STATUS_EL = ROOT.querySelector('[data-ihmp-status]');

  var ENDPOINT = '/api/intelligence-hub/market-pulse';
  var REFRESH_MS = 60000;
  var TIMEOUT_MS = 8000;
  var MAX_ROSTER = 58;             // controller-side refusal, even though the route caps at 60

  /* IHMP-CONTRACT-BEGIN
   * The pure envelope-validation / candidate-ordering / coverage-arithmetic
   * contract — deliberately DOM-free so it can be lifted verbatim and
   * executed under plain node (see tests/test_intelligence_hub_market_pulse_client.py),
   * proving behavior by EXECUTION rather than by reading the source. Nothing
   * in this block may reference `document`, `window`, `fetch` or any other
   * browser global.
   */
  var SCHEMA = 'intelligence_hub.market_pulse.v1';
  var PROJECTION = 'intelligence_hub.market_pulse';
  var SOURCE_VIEW = 'regular';
  var FORBIDDEN_KEY_RE = /^(ext|source$|basis$|anchor_source$|provider)/i;

  var LABELS = {
    baked: ['Prices from the latest settled build', '价格来自最近一次结算构建'],
    loading: ['Checking current prices', '正在查询当前价格'],
    liveComplete: ['Live market pulse', '实时行情脉搏'],
    livePartial: ['Live prices for', '部分实时价格'],
    delayedComplete: ['Delayed market pulse', '延迟行情脉搏'],
    delayedPartial: ['Delayed prices', '部分延迟价格'],
    settledComplete: ['Settled close', '已收盘结算价'],
    stopped: ['Market pulse has stopped updating', '行情脉搏已停止更新'],
    unavailable: ['Current prices temporarily unavailable', '当前价格暂时不可用'],
  };

  function isFiniteNumber(v) { return typeof v === 'number' && isFinite(v); }

  function parseObservedAtMs(iso) {
    if (typeof iso !== 'string' || !iso) return null;
    var ms = Date.parse(iso);
    return isFinite(ms) ? ms : null;
  }

  function validEnvelopeShape(body) {
    if (!body || typeof body !== 'object') return false;
    if (body.schema !== SCHEMA) return false;
    if (body.projection !== PROJECTION) return false;
    if (body.source_view !== SOURCE_VIEW) return false;
    var state = body.state;
    if (!state || typeof state !== 'object') return false;
    if (['available', 'unavailable'].indexOf(state.availability) === -1) return false;
    if (['live', 'delayed', 'stale'].indexOf(state.freshness) === -1) return false;
    if (['complete', 'partial'].indexOf(state.coverage) === -1) return false;
    var cov = body.coverage;
    if (!cov || typeof cov !== 'object') return false;
    if (!isFiniteNumber(cov.requested) || !isFiniteNumber(cov.resolved) || !isFiniteNumber(cov.missing)) return false;
    if (cov.resolved + cov.missing !== cov.requested) return false;
    if ((cov.live || 0) + (cov.delayed || 0) + (cov.stale || 0) !== cov.resolved) return false;
    if (!Array.isArray(body.items)) return false;
    return true;
  }

  function hasForbiddenKey(obj) {
    for (var k in obj) {
      if (Object.prototype.hasOwnProperty.call(obj, k) && FORBIDDEN_KEY_RE.test(k)) return true;
    }
    return false;
  }

  function validItem(item, requestedSet) {
    if (!item || typeof item !== 'object') return false;
    if (hasForbiddenKey(item)) return false;
    var sym = String(item.symbol || '').toUpperCase();
    if (!sym || !requestedSet.has(sym)) return false;   // unrequested symbol invalidates
    if (!isFiniteNumber(item.price) || item.price <= 0) return false;
    if (item.change_abs !== null && !isFiniteNumber(item.change_abs)) return false;
    if (item.change_pct !== null && !isFiniteNumber(item.change_pct)) return false;
    if (['live', 'delayed', 'stale'].indexOf(item.freshness) === -1) return false;
    if (['regular', 'pre', 'post', 'closed'].indexOf(item.session) === -1) return false;
    if (typeof item.revision !== 'string' || !item.revision) return false;
    return true;
  }

  // Build the immutable candidate model: {accepted: Map<sym,candidate>, suppressed: n}.
  // `orderedSymbols` and `lastGood` are explicit parameters (not closures) so
  // this function is callable standalone under node with synthetic inputs.
  function buildCandidateModel(body, orderedSymbols, lastGood) {
    var requestedSet = new Set(orderedSymbols);
    var seenSymbols = new Set();
    var accepted = new Map();
    var suppressed = 0;

    for (var i = 0; i < body.items.length; i++) {
      var item = body.items[i];
      if (!validItem(item, requestedSet)) continue;
      var sym = String(item.symbol).toUpperCase();
      if (seenSymbols.has(sym)) continue;  // a duplicate response symbol invalidates the extra copy
      seenSymbols.add(sym);

      var observedAtMs = parseObservedAtMs(item.observed_at);
      var prior = lastGood.get(sym);

      // (7)/(8) ordering law: newer source time wins; equal time + equal
      // revision is idempotent (repaint is harmless); equal time + changed
      // revision is a correction (accept); older source time is suppressed.
      // `snapshot_id` never participates in this comparison — identity only.
      var accept = true;
      if (prior && observedAtMs !== null && prior.observedAtMs !== null) {
        if (observedAtMs < prior.observedAtMs) accept = false;
      }
      if (!accept) { suppressed++; continue; }

      accepted.set(sym, {
        price: item.price,
        abs: item.change_abs,
        pct: item.change_pct,
        currency: item.currency,
        session: item.session,
        freshness: item.freshness,
        observedAtMs: observedAtMs,
        revision: item.revision,
      });
    }

    return { accepted: accepted, suppressed: suppressed };
  }

  function worstFreshness(accepted) {
    var rank = { live: 0, delayed: 1, stale: 2 };
    var worst = null;
    accepted.forEach(function (c) {
      if (worst === null || rank[c.freshness] > rank[worst]) worst = c.freshness;
    });
    return worst;
  }

  function pageSession(accepted) {
    var sessions = new Set();
    accepted.forEach(function (c) { sessions.add(c.session); });
    if (sessions.size === 1 && sessions.has('regular')) return 'regular';
    if (sessions.size === 1 && sessions.has('closed')) return 'closed';
    return sessions.size ? 'mixed' : null;
  }

  function composeStatus(acceptedCount, totalCount, freshness, session) {
    var n = acceptedCount + '/' + totalCount;
    var complete = acceptedCount === totalCount;
    if (freshness === 'live' && session === 'regular') {
      return complete
        ? [LABELS.liveComplete[0] + ' · ' + n + ' names', LABELS.liveComplete[1] + ' · ' + n]
        : [LABELS.livePartial[0] + ' ' + n + ' names', LABELS.livePartial[1] + ' ' + n];
    }
    if (freshness === 'delayed') {
      return complete
        ? [LABELS.delayedComplete[0] + ' · ' + n + ' names', LABELS.delayedComplete[1] + ' · ' + n]
        : [LABELS.delayedPartial[0] + ' · ' + n + ' names', LABELS.delayedPartial[1] + ' · ' + n];
    }
    // stale/settled: closed regular print
    return [LABELS.settledComplete[0] + ' · ' + n + ' names', LABELS.settledComplete[1] + ' · ' + n];
  }
  /* IHMP-CONTRACT-END */

  function fmtPrice(v) { return '$' + Number(v).toFixed(2); }
  function fmtAbs(v) {
    var n = Number(v);
    return (n < 0 ? '-' : '+') + '$' + Math.abs(n).toFixed(2);
  }
  function fmtPct(v) {
    var n = Number(v);
    return (n < 0 ? '-' : '+') + Math.abs(n).toFixed(2) + '%';
  }

  // ── (1)-(3) target discovery ────────────────────────────────────────────
  var targetsBySymbol = new Map();
  var orderedSymbols = [];
  (function discoverTargets() {
    var nodes = document.querySelectorAll('[data-ihmp-symbol]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var sym = String(el.getAttribute('data-ihmp-symbol') || '').trim().toUpperCase();
      if (!sym) continue;
      if (!targetsBySymbol.has(sym)) {
        targetsBySymbol.set(sym, []);
        orderedSymbols.push(sym);
      }
      targetsBySymbol.get(sym).push(el);
    }
  })();

  var ACTIVE = orderedSymbols.length > 0 && orderedSymbols.length <= MAX_ROSTER;
  if (orderedSymbols.length > MAX_ROSTER) {
    // Refuse to activate at all rather than silently truncate the roster —
    // an over-cap page is a build defect, not something to paper over client-side.
    ACTIVE = false;
  }

  // ── page-lifetime last-good state (never persisted) ─────────────────────
  var lastGood = new Map();   // symbol -> {price,abs,pct,currency,session,freshness,observedAtMs,revision}
  var generation = 0;
  var inFlight = false;
  var abortCtrl = null;
  var timer = null;
  var liveDisabled = false;
  try { liveDisabled = !!window.localStorage && !!localStorage.getItem('liveOff'); } catch (e) { /* ignore */ }

  // ── (10) atomic multi-target paint (one RAF, every occurrence together) ─
  function paintNode(el, candidate) {
    var priceNode = el.querySelector('[data-ihmp-price]');
    var absNode = el.querySelector('[data-ihmp-abs]');
    var pctNode = el.querySelector('[data-ihmp-pct]');
    if (priceNode) priceNode.textContent = fmtPrice(candidate.price);
    if (absNode) {
      if (isFiniteNumber(candidate.abs)) {
        absNode.textContent = fmtAbs(candidate.abs);
        absNode.hidden = false;
        absNode.classList.toggle('pos', candidate.abs >= 0);
        absNode.classList.toggle('neg', candidate.abs < 0);
      } else {
        absNode.hidden = true;
      }
    }
    if (pctNode) {
      if (isFiniteNumber(candidate.pct)) {
        pctNode.textContent = fmtPct(candidate.pct);
        pctNode.hidden = false;
        pctNode.classList.toggle('pos', candidate.pct >= 0);
        pctNode.classList.toggle('neg', candidate.pct < 0);
      } else {
        pctNode.hidden = true;
      }
    }
  }

  function setStatus(en, zh) {
    if (!STATUS_EL) return;
    var enNode = STATUS_EL.querySelector('.l-en');
    var zhNode = STATUS_EL.querySelector('.l-zh');
    if (enNode) enNode.textContent = en; else STATUS_EL.textContent = en;
    if (zhNode) zhNode.textContent = zh;
  }

  function commit(body, model) {
    var accepted = model.accepted;
    // merge into page-lifetime last-good BEFORE paint, so a later refresh's
    // ordering comparison sees this refresh's values.
    accepted.forEach(function (c, sym) { lastGood.set(sym, c); });

    window.requestAnimationFrame(function () {
      accepted.forEach(function (candidate, sym) {
        var nodes = targetsBySymbol.get(sym) || [];
        for (var i = 0; i < nodes.length; i++) paintNode(nodes[i], candidate);
      });
      // (9) truthful coverage recomputed from what THIS controller actually
      // accepted (server coverage plus any local ordering suppression), not
      // blindly copied from the response.
      var totalCount = orderedSymbols.length;
      var acceptedCount = accepted.size;
      var freshness = worstFreshness(accepted) || 'stale';
      var session = pageSession(accepted) || 'mixed';
      var availability = acceptedCount > 0 ? 'available' : 'unavailable';
      var coverage = acceptedCount === totalCount ? 'complete' : 'partial';

      ROOT.setAttribute('data-ihmp-availability', availability);
      ROOT.setAttribute('data-ihmp-freshness', freshness);
      ROOT.setAttribute('data-ihmp-session', session);
      ROOT.setAttribute('data-ihmp-coverage', coverage);

      if (acceptedCount === 0) {
        setStatus(LABELS.unavailable[0], LABELS.unavailable[1]);
      } else {
        var pair = composeStatus(acceptedCount, totalCount, freshness, session);
        setStatus(pair[0], pair[1]);
      }
    });
  }

  // ── (4)/(6)/(7) one batch request, generation-guarded ───────────────────
  function doFetch() {
    if (!ACTIVE || liveDisabled) return;
    if (inFlight) return;
    if (document.hidden) return;

    inFlight = true;
    var myGeneration = generation;
    if (abortCtrl) { try { abortCtrl.abort(); } catch (e) { /* already gone */ } }
    abortCtrl = window.AbortController ? new AbortController() : null;

    var settled = false;
    var killer = setTimeout(function () {
      if (settled) return;
      settled = true;
      if (abortCtrl) { try { abortCtrl.abort(); } catch (e) { /* ignore */ } }
      inFlight = false;
    }, TIMEOUT_MS);

    function done() {
      if (settled) return true;
      settled = true;
      clearTimeout(killer);
      inFlight = false;
      return false;
    }

    if (STATUS_EL && !lastGood.size) setStatus(LABELS.loading[0], LABELS.loading[1]);

    var url = ENDPOINT + '?symbols=' + encodeURIComponent(orderedSymbols.join(','));
    fetch(url, {
      signal: abortCtrl ? abortCtrl.signal : undefined,
      credentials: 'omit',
      headers: { Accept: 'application/json' },
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (body) {
        if (done()) return;
        // (7) a response answering a STALE local generation is discarded —
        // never partially applied, never used to judge freshness.
        if (myGeneration !== generation) return;
        if (!body || !validEnvelopeShape(body)) return;  // malformed -> zero DOM mutation
        var model = buildCandidateModel(body, orderedSymbols, lastGood);
        commit(body, model);
      })
      .catch(function () { done(); });
  }

  function schedule() {
    if (timer) return;
    timer = setInterval(doFetch, REFRESH_MS);
  }

  function unschedule() {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
  }

  // ── (12) visibility pause/resume ────────────────────────────────────────
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      unschedule();
    } else {
      generation++;   // resume issues one immediate, freshly-generationed refresh
      schedule();
      doFetch();
    }
  });

  // ── public surface ───────────────────────────────────────────────────────
  window.IntelligenceHubMarketPulse = {
    refresh: function () {
      if (!ACTIVE || liveDisabled) return;
      generation++;
      doFetch();
    },
    pause: function () { unschedule(); },
    resume: function () {
      if (!ACTIVE || liveDisabled) return;
      generation++;
      schedule();
      doFetch();
    },
    state: function () {
      return {
        active: ACTIVE,
        liveDisabled: liveDisabled,
        symbolCount: orderedSymbols.length,
        generation: generation,
        inFlight: inFlight,
      };
    },
  };

  if (ACTIVE && !liveDisabled) {
    schedule();
    doFetch();
  }
})();

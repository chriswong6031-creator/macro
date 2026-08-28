/* Mastermind stock-dossier live quote binding.
 *
 * The dossier is nightly-rendered static HTML. Before this module the hero
 * price, the sticky-strip price and the day move were all baked at build time
 * while a green "Live" pip sat beside them, keyed off the BUILD's date rather
 * than any quote. Measured 2026-08-27: NVDA served $209.66 with a static
 * "-$3.39 · -1.59%" and a pulsing "Live" chip, while the measured
 * regular-session close was $227.98 (+8.74%) — the page showed the PREVIOUS
 * close and the PREVIOUS day's move, and called it live.
 *
 * Contract with the page
 * ----------------------
 *   [data-dq-sym]     price nodes (hero + sticky). Deliberately NOT .nb-px:
 *                     the shared live.js poller owns .nb-px, and two owners
 *                     writing one node is a race decided by fetch order.
 *   [data-dq-chg]     the move row (carries .pos/.neg)
 *   [data-dq-abs]     absolute move   [data-dq-pct] percent move
 *   [data-dq-stamp]   freshness stamp, data-dq-state = baked|live|delayed|closed
 *
 * Honesty law
 * -----------
 * Price and move are written TOGETHER from ONE quote, or not at all — a
 * half-applied repaint would leave a current price beside a stale move, which
 * is the same lie in a subtler form. "Live" requires the server to report a
 * measured realtime feed AND an open regular session; anything else is named
 * for what it is. Any failure, or a quote the server itself marks stale,
 * leaves the baked HTML exactly as rendered.
 */
(function () {
  'use strict';

  var priceNodes = document.querySelectorAll('[data-dq-sym]');
  if (!priceNodes.length) return;

  var ticker = String(priceNodes[0].getAttribute('data-dq-sym') || '').trim().toUpperCase();
  if (ticker.indexOf('..') !== -1 || !/^[A-Z0-9](?:[A-Z0-9.\-]{0,14}[A-Z0-9])?$/.test(ticker)) return;

  // No fetch (or no Promise) means no quote — stand down and leave the baked
  // page exactly as rendered. Checked BEFORE first use, because calling a
  // missing `fetch` throws synchronously, ahead of any promise chain, so the
  // `.catch` below would never see it: the page would keep its correct baked
  // values but log an uncaught error on every tick.
  if (typeof window.fetch !== 'function' || typeof window.Promise !== 'function') return;

  var chgRow = document.querySelector('[data-dq-chg]');
  var absNode = document.querySelector('[data-dq-abs]');
  var pctNode = document.querySelector('[data-dq-pct]');
  var stamp = document.querySelector('[data-dq-stamp]');

  var POLL_MS = 15000;      // comfortably inside the hub's own snapshot cadence
  var TIMEOUT_MS = 6000;
  var timer = null;
  var inflight = false;

  // Bilingual pairs. The page ships both strings and CSS reveals one, so a
  // JS-written label must set BOTH or the other language silently keeps the
  // previous text.
  var LABELS = {
    live: ['Live', '实时'],
    delayed: ['Delayed', '延迟'],
    pre: ['Pre-market', '盘前'],
    post: ['After hours', '盘后'],
    closed: ['Closed', '已收盘'],
    // Currency LAPSED after we had it. Plain words, no internal state name.
    lapsed: ['Not updating', '暂停更新']
  };

  // Whether this page has ever painted a measured quote. A stale reading is
  // handled differently before and after that: before, the baked stamp already
  // names its own build date and is honest as-is; after, the stamp is making a
  // live-or-delayed claim that has since lapsed and MUST be demoted.
  var painted = false;

  function fmtPrice(v) { return Number(v).toFixed(2); }

  function fmtAbs(v) {
    var n = Number(v);
    return (n < 0 ? '-' : '+') + '$' + Math.abs(n).toFixed(2);
  }

  function fmtPct(v) {
    var n = Number(v);
    return (n < 0 ? '-' : '+') + Math.abs(n).toFixed(2) + '%';
  }

  function setBilingual(el, en, zh) {
    if (!el) return;
    var enNode = el.querySelector('.l-en');
    var zhNode = el.querySelector('.l-zh');
    if (enNode) enNode.textContent = en;
    if (zhNode) zhNode.textContent = zh;
    // A stamp rendered without the bilingual spans still gets an honest label
    // rather than keeping a stale one.
    if (!enNode && !zhNode) el.textContent = en;
  }

  function isFiniteNumber(v) { return typeof v === 'number' && isFinite(v); }

  // Which of the five labels this quote earns, and which CSS state paints it.
  // "live" is the only branch that yields a green pulsing pip, and it needs
  // BOTH a measured realtime feed and an open regular session.
  function readingOf(q) {
    if (q.freshness === 'live' && q.session === 'regular') {
      return { state: 'live', label: LABELS.live };
    }
    if (q.session === 'regular') return { state: 'delayed', label: LABELS.delayed };
    if (q.session === 'pre') return { state: 'closed', label: LABELS.pre };
    if (q.session === 'post') return { state: 'closed', label: LABELS.post };
    return { state: 'closed', label: LABELS.closed };
  }

  function paint(q) {
    // Fail closed on anything we cannot fully render. A partial paint is worse
    // than no paint: it desynchronises the price from the move.
    if (!q || q.ticker !== ticker) return;
    if (q.freshness === 'stale') {
      // Keep the numbers — the last measured quote still beats a day-old baked
      // one — but never keep a currency claim we can no longer support. A tab
      // left open while the feed dies used to hold a pulsing green "Live"
      // indefinitely, which is this project's original defect wearing a
      // different hat.
      if (painted && stamp) {
        stamp.setAttribute('data-dq-state', 'closed');
        setBilingual(stamp, LABELS.lapsed[0], LABELS.lapsed[1]);
      }
      return;
    }
    if (!isFiniteNumber(q.price) || q.price <= 0) return;
    if (!isFiniteNumber(q.change_abs) || !isFiniteNumber(q.change_pct)) return;

    var i;
    painted = true;
    for (i = 0; i < priceNodes.length; i++) priceNodes[i].textContent = fmtPrice(q.price);

    if (absNode) absNode.textContent = fmtAbs(q.change_abs);
    if (pctNode) pctNode.textContent = fmtPct(q.change_pct);
    if (chgRow) {
      var up = q.change_abs >= 0;
      chgRow.classList.toggle('pos', up);
      chgRow.classList.toggle('neg', !up);
    }

    if (stamp) {
      var reading = readingOf(q);
      var en = reading.label[0];
      var zh = reading.label[1];
      // Outside an open regular session the move belongs to a NAMED past
      // session — upstream can even hand back the previous session's move
      // before an open — so the reader is told which date they are reading.
      if (reading.state !== 'live' && q.session !== 'regular' && q.regular_session_date) {
        en += ' · ' + q.regular_session_date;
        zh += ' · ' + q.regular_session_date;
      }
      stamp.setAttribute('data-dq-state', reading.state);
      setBilingual(stamp, en, zh);
    }
  }

  function poll() {
    if (inflight || document.hidden) return;
    inflight = true;

    var ctrl = window.AbortController ? new AbortController() : null;
    var killer = ctrl ? setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS) : null;

    fetch('/api/dossier-quote/' + encodeURIComponent(ticker), {
      signal: ctrl ? ctrl.signal : undefined,
      credentials: 'omit',
      headers: { Accept: 'application/json' }
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (q) { if (q) paint(q); })
      .catch(function () { /* keep the baked values; say nothing false */ })
      .then(function () {
        if (killer) clearTimeout(killer);
        inflight = false;
      });
  }

  // Always attempt an immediate read, then ensure the interval exists. The
  // earlier `if (timer) return` shape stranded one real case: a dossier opened
  // in a BACKGROUND tab installs the timer while hidden, every tick no-ops on
  // the hidden check, and the reveal then found the timer already set and
  // returned — leaving the baked price on screen for up to a full poll period
  // at the exact moment the reader first looked at it. poll() is itself
  // guarded on `inflight` and `document.hidden`, so calling it here is cheap
  // and safe.
  function start() {
    poll();
    if (!timer) timer = setInterval(poll, POLL_MS);
  }

  function stop() {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stop(); else start();
  });

  start();
})();

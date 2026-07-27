/* adtest.js — Ad Central, Plane O: split tests on our own pages.
   research/AD_CENTRAL_MASTERPLAN.md §2. Engine side: engine/marketing/ad_arena.py.

   What this does, in order, synchronously:
     1. reads an inline arena config (no fetch — a round trip before paint is a
        flash of the control copy, which biases the metric being measured)
     2. derives a stable per-browser id
     3. picks an arm with the SAME hash the engine uses
     4. rewrites the marked slots
     5. reports the exposure through the existing analytics beacon

   PARITY IS LOAD-BEARING. `hashUnit` below must agree bit-for-bit with
   `_unit_hash` in engine/marketing/ad_arena.py. If they drift, visitors are
   counted in one arm and shown another, and the test reads as noise while
   looking perfectly healthy. tests/test_marketing_ad_plane_o.py executes THIS
   FILE under node and compares against Python. Change both sides or neither.

   The client picks the arm; it cannot pick its own identity. The unit id below
   is only a local assignment seed — the join key is the server-stamped mm_aid
   visitor cookie (httpOnly, unreadable here), so a tampered id cannot stuff the
   denominator. See ad_ingest.py.

   Inert by design: no inline config, or an arena that is not running-and-live,
   means the page keeps the copy already in its HTML and nothing is reported. */
(function () {
  'use strict';

  var CONFIG_ID = 'mm-adtest';
  var STORE_KEY = 'mm.adtest.u';
  var HOLDOUT = '__holdout__';

  /* ---- hash: FNV-1a 32-bit, forward then backward -------------------------
     Mirrors engine/marketing/ad_arena.py::_unit_hash. Math.imul keeps the
     multiply in int32 so it matches Python's masked arithmetic exactly;
     charCodeAt walks UTF-16 code units, which the Python side reproduces by
     unpacking UTF-16-LE. Returns a uniform draw in [0, 1). */
  function hashUnit(arenaId, unitKey, salt) {
    var p = String(arenaId) + '\x1f' + String(unitKey) + '\x1f' + String(salt || '');
    var i, a = 0x811c9dc5;
    for (i = 0; i < p.length; i++) { a ^= p.charCodeAt(i); a = Math.imul(a, 0x01000193); }
    var b = (0x811c9dc5 ^ a) >>> 0;
    for (i = p.length - 1; i >= 0; i--) { b ^= p.charCodeAt(i); b = Math.imul(b, 0x01000193); }
    return (b >>> 0) / 4294967296;
  }

  /* ---- assignment: mirrors ad_arena.assign() ------------------------------
     `arms` is an ORDERED array, not an object: the cumulative walk below has to
     visit arms in the same order the engine does, and object key order is a
     weaker promise than a list's. */
  function assign(cfg, unitKey) {
    var arms = cfg.arms || [];
    if (!arms.length) return null;

    var holdout = +cfg.holdout || 0;
    if (holdout > 0 && hashUnit(cfg.arena_id, unitKey, 'holdout') < holdout) return HOLDOUT;

    var i, total = 0, weights = [];
    for (i = 0; i < arms.length; i++) {
      var w = +arms[i].w;
      weights.push(w > 0 ? w : 0);
      total += weights[i];
    }
    if (total <= 0) {
      for (i = 0; i < arms.length; i++) weights[i] = 1;
      total = arms.length;
    }

    var draw = hashUnit(cfg.arena_id, unitKey, 'arm') * total;
    var cumulative = 0;
    for (i = 0; i < arms.length; i++) {
      cumulative += weights[i];
      if (draw < cumulative) return arms[i].id;
    }
    return arms[arms.length - 1].id;
  }

  /* ---- stable local id ----------------------------------------------------
     localStorage, then a first-party cookie, then a per-page fallback. The
     fallback is deliberately NOT persisted anywhere: a browser that blocks both
     stores would otherwise get a fresh arm on every page view, and those rows
     land as conflicting_assignment anomalies rather than silent contamination
     (ad_arena.tally keeps the first assignment and counts the rest). */
  function unitId() {
    var v = '';
    try { v = window.localStorage.getItem(STORE_KEY) || ''; } catch (e) {}
    if (!v) {
      try {
        var m = document.cookie.match(/(?:^|;\s*)mm_ab=([^;]+)/);
        if (m) v = decodeURIComponent(m[1]);
      } catch (e2) {}
    }
    if (!v) {
      v = (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : 'u-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      try { window.localStorage.setItem(STORE_KEY, v); } catch (e3) {}
      try {
        document.cookie = 'mm_ab=' + encodeURIComponent(v)
          + ';path=/;max-age=63072000;samesite=lax'
          + (location.protocol === 'https:' ? ';secure' : '');
      } catch (e4) {}
    }
    return v;
  }

  /* ---- apply --------------------------------------------------------------
     Only rewrites slots the chosen arm actually supplies. A missing key leaves
     the authored HTML alone, so a half-specified variant degrades to the
     control instead of blanking the hero.

     A slot value is either a plain string (set as text) or {html, zh}. The
     second form exists because real hero copy is not a bare string: the landing
     h1 carries <br> and a <span class="dim">, and setting textContent would
     strip both — changing the TYPOGRAPHY as well as the words, so the test would
     no longer be measuring copy alone.

     `zh` is not optional politeness. The landing's switcher rewrites every
     [data-zh] element from that attribute, so a variant that updates only the
     English leaves every Chinese visitor reading the control while counted in
     the variant's arm — a silent confound across a whole audience. */
  function applyCopy(copy) {
    if (!copy) return 0;
    var n = 0;
    var nodes = document.querySelectorAll('[data-adtest-slot]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var slot = el.getAttribute('data-adtest-slot');
      if (!slot || !Object.prototype.hasOwnProperty.call(copy, slot)) continue;
      var v = copy[slot];

      if (typeof v === 'string') {
        if (!v) continue;
        el.textContent = v;
      } else if (v && typeof v === 'object' && typeof v.html === 'string' && v.html) {
        el.innerHTML = v.html;
        if (typeof v.zh === 'string' && v.zh) el.setAttribute('data-zh', v.zh);
        /* The switcher caches the English original in el.__en the FIRST time it
           runs. If it ran before us that cache holds the CONTROL copy, and the
           next toggle to zh and back restores it — putting the visitor on an arm
           they are not counted in, with nothing anywhere going red. Drop the
           cache so the switcher re-captures the variant. */
        el.__en = null;
      } else {
        continue;
      }
      n++;
    }
    return n;
  }

  /* ---- report -------------------------------------------------------------
     window.mmTrack is defined by theme.js, which may not have run yet. Retry a
     few times on a short timer rather than racing it; if it never appears the
     exposure is simply not reported, and an unreported exposure is a missing
     row, never a wrong one. */
  function report(payload, tries) {
    if (typeof window.mmTrack === 'function') {
      try { window.mmTrack('ad_exposure', { meta: payload }); } catch (e) {}
      return;
    }
    if ((tries || 0) >= 20) return;
    setTimeout(function () { report(payload, (tries || 0) + 1); }, 250);
  }

  /* ---- run ---------------------------------------------------------------- */
  function run() {
    var node = document.getElementById(CONFIG_ID);
    if (!node) return;                       // no test on this page

    var cfg;
    try { cfg = JSON.parse(node.textContent || '{}'); } catch (e) { return; }
    if (!cfg || !cfg.arena_id || !cfg.arms || !cfg.arms.length) return;

    // Only a running, live arena touches a real visitor. A planned or shadow
    // arena is a pre-registration, not an experiment.
    if (cfg.status !== 'running' || cfg.mode !== 'live') return;

    var unit = unitId();
    if (!unit) return;

    var chosen = assign(cfg, unit);
    if (!chosen) return;

    var shown = 0;
    if (chosen !== HOLDOUT) {
      for (var i = 0; i < cfg.arms.length; i++) {
        if (cfg.arms[i].id === chosen) { shown = applyCopy(cfg.arms[i].copy); break; }
      }
    }

    window.mmAdtest = { arena: cfg.arena_id, creative: chosen, slots: shown };
    report({ arena: cfg.arena_id, creative: chosen, slots: shown });
  }

  // Exported for the parity test; harmless in a browser.
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { hashUnit: hashUnit, assign: assign, HOLDOUT: HOLDOUT };
  }

  /* Scheduling. This file is loaded by a plain <script> placed immediately after
     the block it rewrites, so the slots are already parsed and `run()` can
     rewrite them synchronously — before first paint, with no flash of the
     control copy. (Waiting for DOMContentLoaded would paint the control first;
     a visitor who sees the control for 200ms and then the variant is a visitor
     whose measured behaviour belongs to neither.)

     DOMContentLoaded is kept only as a fallback for a page that loads this
     earlier than its slots. `ran` makes the two paths mutually exclusive. */
  var ran = false;
  function once() {
    if (ran) return;
    ran = true;
    run();
  }

  try {
    if (document.getElementById(CONFIG_ID) && document.querySelectorAll('[data-adtest-slot]').length) {
      once();
    } else if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', once);
    } else {
      once();
    }
  } catch (e) {}
})();

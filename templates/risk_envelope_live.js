/* risk_envelope_live.js — GD-3: paint a live-provisional overlay on the settled Risk
   Envelope band (macro.html #risk-envelope-band), polling site/live/risk_envelope.json
   (written by scripts/build_live_risk_envelope.py during market hours). Modeled closely
   on risk_state_live.js: same poll-interval idiom, cache:"no-store", every fetch/parse
   error swallowed silently (an anonymous 401 on a tier-gated live artifact must stay
   quiet — the settled band underneath is always a complete, correct read on its own).

   Display/advisory only. The overlay paints ONLY when every identity + freshness check
   below holds; otherwise the pre-baked hidden hooks stay hidden and the settled band is
   the whole story. No falsifier/refutation vocabulary; stage vocabulary (NONE/FRAGILE/
   TRANSMITTING/BREAKDOWN) is written ONLY into the drawer's machine receipt, never into
   the glance-tier chip/pending copy. */
(function () {
  "use strict";
  var FEED_URL = "live/risk_envelope.json";
  var POLL = (window.LIVE_POLL_SEC && +window.LIVE_POLL_SEC) || 60;

  function unpaint() {
    var chip = document.getElementById("gde-live-chip");
    var pending = document.getElementById("gde-pending-chip");
    var receipt = document.getElementById("gde-live-receipt");
    if (chip) chip.hidden = true;
    if (pending) pending.hidden = true;
    if (receipt) { receipt.hidden = true; receipt.textContent = ""; }
  }

  /* Healthy live overlay. Every call re-asserts the chip's baked copy — never
     relies on the DOM still holding it from a render or a prior tick, since
     paintDegraded() below overwrites it and a paint()->degraded->paint() cycle
     must not leave the degraded copy stuck (adjudication #4). */
  function paint(d, band) {
    var chip = document.getElementById("gde-live-chip");
    var pending = document.getElementById("gde-pending-chip");
    var receipt = document.getElementById("gde-live-receipt");

    if (chip) {
      var enEl = chip.querySelector(".l-en"), zhEl = chip.querySelector(".l-zh");
      if (enEl) enEl.textContent = "Live · provisional";
      if (zhEl) zhEl.textContent = "实时 · 临时";
      var t = chip.querySelector(".gde-live-time");
      if (t) t.textContent = "· " + (d.built || "").slice(11, 16) + " UTC";
      chip.hidden = false;
    }

    var trans = d.live_transition || {};
    if (pending) {
      if (trans.pending && trans.pending.stage) {
        var needs = trans.pending.needs || "?";
        var ticks = trans.pending.ticks || 0;
        var en = pending.querySelector(".l-en"), zh = pending.querySelector(".l-zh");
        if (en) en.textContent = "· live read shifting · confirming " + ticks + "/" + needs;
        if (zh) zh.textContent = "· 实时读数变化 · 确认中 " + ticks + "/" + needs;
        pending.hidden = false;
      } else {
        pending.hidden = true;
      }
    }

    if (receipt) {
      var bundle = (d.bundle_id || "").slice(0, 8);
      var line = "live: candidate " + (trans.candidate_stage == null ? "null" : trans.candidate_stage) +
                  " · stable " + (trans.stable_stage == null ? "null" : trans.stable_stage) +
                  " · pending " + (trans.pending ? (trans.pending.ticks + "/" + trans.pending.needs) : "0/0") +
                  " · built " + (d.built || "—") +
                  " · bundle " + (bundle || "—");
      receipt.textContent = line;
      receipt.hidden = false;
    }
  }

  /* DEGRADED live state (outage / null candidate): chip stays visible with a
     "not enough to say" plain-word read; pending never shows on a null candidate
     (freeze §GD-3: a null candidate never ticks in any direction). The receipt
     must never keep showing a stale HEALTHY line beside degraded chip copy
     (adjudication #4), so it is overwritten with a matching degraded receipt
     rather than left as whatever paint() last wrote. */
  function paintDegraded(d) {
    var chip = document.getElementById("gde-live-chip");
    var pending = document.getElementById("gde-pending-chip");
    var receipt = document.getElementById("gde-live-receipt");
    if (chip) {
      var enEl = chip.querySelector(".l-en"), zhEl = chip.querySelector(".l-zh");
      if (enEl) enEl.textContent = "Live · not enough to say";
      if (zhEl) zhEl.textContent = "实时 · 暂无法判断";
      var t = chip.querySelector(".gde-live-time");
      if (t) t.textContent = "";
      chip.hidden = false;
    }
    if (pending) pending.hidden = true;
    if (receipt) {
      var trans = d.live_transition || {};
      var bundle = (d.bundle_id || "").slice(0, 8);
      receipt.textContent = "live: candidate null · stable " +
        (trans.stable_stage == null ? "null" : trans.stable_stage) +
        " · degraded (" + (d.data_state || "unknown") + ") · built " + (d.built || "—") +
        " · bundle " + (bundle || "—");
      receipt.hidden = false;
    }
  }

  function active(d, band) {
    if (!d || d.schema !== "mastermind.risk_envelope/v1") return false;
    if (d.revision !== "live_provisional") return false;
    if (d.precedence !== "live") return false;
    var wantBundle = band.getAttribute("data-bundle-id");
    var overlays = d.overlays || {};
    if (!wantBundle || overlays.settled_bundle_id !== wantBundle) return false;
    if (!d.live_active) return false;
    var built = d.built ? Date.parse(d.built.replace(" UTC", "Z").replace(" ", "T")) : NaN;
    var horizonMin = (typeof d.stale_after_min === "number") ? d.stale_after_min : 5;
    if (!isFinite(built) || (Date.now() - built) > horizonMin * 60 * 1000) return false;
    /* Feed-behind-the-render floor (same law as risk_state_live.js): a live read
       older than the page's baked settled session must never paint — that would
       look fresher/looser than a stale read actually is. */
    var floor = band.getAttribute("data-settled-session") || "";
    if (floor && d.source_session && d.source_session < floor) return false;
    return true;
  }

  /* The one entry point that decides paint vs. degraded vs. unpaint for a
     PARSED feed object — factored out of tick()'s fetch chain so the shipped
     module is directly testable (tests/test_risk_state_live_session_floor.py
     drives risk_state_live.js the same way: strip the auto-run tail, call the
     entry function with a fixture feed, read the DOM back). No behavior change
     from inlining it in tick() — same band lookup, same try/catch-to-unpaint. */
  function applyFeed(d) {
    var band = document.getElementById("risk-envelope-band");
    if (!band) return;
    try {
      if (!d) { unpaint(); return; }
      if (active(d, band)) {
        /* Route on the ENVELOPE's own hazard stage alone (adjudication #8):
           a null stage means "not enough to say" regardless of what
           data_state happens to read (FRESH-but-null is exactly the shape a
           laundered empty live block used to produce) — never gate degraded
           copy on data_state, which is a coverage grade, not a knowability
           verdict. */
        var stage = ((d.hazard_summary || {}).stage);
        if (stage == null) {
          paintDegraded(d);
        } else {
          paint(d, band);
        }
      } else {
        unpaint();
      }
    } catch (e) { unpaint(); }
  }

  function tick() {
    if (!document.getElementById("risk-envelope-band")) return;   // no wasted fetch
    fetch(FEED_URL + "?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(applyFeed)
      .catch(function () {});
  }

  if (document.readyState !== "loading") tick();
  else document.addEventListener("DOMContentLoaded", tick);
  setInterval(tick, Math.max(15, POLL) * 1000);
})();

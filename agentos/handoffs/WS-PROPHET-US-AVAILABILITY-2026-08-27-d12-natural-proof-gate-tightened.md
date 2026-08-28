---
workstream: "WS:PROPHET-US-AVAILABILITY"
session: "sol/prophet-us-d12-natural-proof-reconcile-20260827"
model: sol
ended_because: blocked
mission: >
  Reconcile D12 after the merged producer repair and the 2026-08-27 fresh-but-empty
  production discovery, preserve the one-carrier/no-manufactured-proof law, and freeze
  the exact natural production evidence still owed before D12 can leave BUILT_NOT_PROVEN.
state_before: >
  PR #6554 had merged D12's US-owner quarantine before both pack-tip selection and gate
  execution, and cleanup PR #6565 had removed the temporary red workflow. The canonical
  force-majeure handoff correctly kept D12 BUILT_NOT_PROVEN pending a natural pack plus
  evaluator/dead-man proof, but it did not yet encode the later production discovery that
  a lane can publish fresh timestamps while serving an empty states map all session.
changed:
  - path: "GitHub PR #6569 / scripts/freshness_sentinel.py"
    what: >
      Production on 2026-08-27 proved a fresh-but-empty Prophet Live failure: at 19:12Z
      the served artifact was fresh by pass_ts but carried n_states=0 because the evaluator
      refused a poisoned armed pack as stale_pack. #6569 added the grader-side fresh-empty
      streak fence and an asof_never_ahead fence for prophet_live_armed. This continuation
      therefore tightens D12 acceptance: fresh clocks plus pack_ok are not sufficient;
      the live consumer must also demonstrate a non-empty states map in the natural session.
  - path: "GitHub PR #6565"
    what: >
      The temporary D12 red workflow cleanup is already merged at
      53956e7074346cc2c8d34ac8431d6b93fa2dbc3d. No duplicate merge or replacement carrier
      is authorized or needed.
  - path: ".github/workflows/daily.yml"
    what: >
      Build B remains the sole authoritative nightly and is anchored at 18:30 ET via the
      EDT/EST cron pair. The EDT firing is 30 22 * * *. The workflow explicitly allows a
      real firing to sit queued for hours and still proceed; proof must come from that
      ordinary scheduled carrier, not workflow_dispatch.
  - path: ".github/workflows/nightly-liveness.yml / scripts/check_nightly_liveness.py"
    what: >
      The independent GitHub-hosted watchdog produced a positive 2026-08-27 receipt that
      no Build-B run had been created after the fire boundary yet. That receipt is now
      part of the D12 external-gate evidence, not a reason to create a manual substitute.
      Its own delayed 20:00Z scheduling means the early page is not by itself proof of a
      scheduler incident; the watchdog's documented first deliberate post-bake look is 08:00Z.
verified:
  - claim: "Current protected Sol procedure is compatible and pinned before this record effect."
    command: >
      Read protected mastermindx-market-intelligence/Mastermind master and
      docs/sol_skills/INDEX.md plus COLD_START.md, REVIEW_RETURN.md,
      RECONCILE_STATE.md, and CLOSEOUT.md from the same commit.
    result: >
      Protected Mastermind is b901dee0272a99b8a1d60385848b99b7273e8261;
      mastermind.sol_skillpack.v1 version 1.0.0 remains compatible with bootstrap_major 1.
  - claim: "The D12 producer repair is on main and remains BUILT_NOT_PROVEN rather than accepted."
    command: >
      Read PR #6554 / merge 43e07debafd3c95c027fc027b53a137ff06e6767,
      current scripts/build_prophet_live_pack.py, and the canonical force-majeure handoff.
    result: >
      The US pack owner rejects malformed, non-session, and not-yet-completed series tips
      before both global tip selection and gate execution; invalid names are explicit
      invalid_series_tip non-verdicts. The durable handoff still requires natural production proof.
  - claim: "2026-08-27 production falsified fresh-timestamp-only health."
    command: >
      Read PR #6569 / merge 06d68455e55808a9a328d41e03f50f7a76b5021e.
    result: >
      At 19:12Z prophet_live was graded fresh while n_states=0; the evaluator was refusing
      a D12-poisoned pack as stale_pack and publishing fresh empty passes. #6569 now breaches
      persistent in-window empty states and armed packs ahead of the canonical session calendar.
  - claim: "The independent nightly watchdog positively observed no Build-B run after the 2026-08-27 fire boundary."
    command: >
      Read GitHub Actions nightly-liveness run #38 / run 33126181894 and job 98704781286 logs.
    result: >
      At 2026-08-27T23:25:01Z the watchdog emitted NO RUN: daily.yml created no run since
      2026-08-27T22:00:00Z, with runs_since=0, source_asof=2026-08-26 and behind=1 for the
      2026-08-27 session. It also independently emitted INTAKE INTEGRITY because
      site/prophet/index.json carried intake.eligible_after_skips=25 and intake.originated=0.
      Those are positive production observations; they do not authorize a manual nightly.
  - claim: "The watchdog page can be early relative to its own documented first post-bake adjudication."
    command: >
      Read .github/workflows/nightly-liveness.yml and scripts/check_nightly_liveness.py at current main.
    result: >
      The watchdog schedules 00:00/08:00/14:00/20:00Z and documents 08:00Z as the first
      look comfortably past the 22:30Z bake. Run 33126181894 was created at 23:24:45Z,
      consistent with a delayed 20:00Z watchdog firing that crossed the 22:00Z FIRE_BOUNDARY.
      Its runs_since=0 fact is valid, but that one early page alone does not prove the nightly
      scheduler is broken; the D12 gate remains external until the ordinary carrier appears or
      the designed liveness window positively fails.
  - claim: "The temporary D12 red workflow is gone from current main."
    command: >
      Read current main and request .github/workflows/prophet-d12-price-red.yml.
    result: >
      PR #6565 merged at 53956e7074346cc2c8d34ac8431d6b93fa2dbc3d and the path is absent on main.
unverified:
  - claim: "The first natural post-#6554 Build-B arms a lawful D12 pack."
    what_would_verify: >
      An ordinary daily 30 22 * * * run whose own immutable run identity is accepted for
      this carrier, with the real build_prophet_live_pack step showing completed_through
      equal to the canonical last completed NYSE session, pack as_of a real session at or
      before that bound, explicit invalid_series_tip counts/non-verdicts when present, and
      successful publication of live_flow/prophet_live_armed.json. Do not infer this from
      a later checkout alone when the run identity is ambiguous.
  - claim: "D12 is PROVEN_LIVE end to end."
    what_would_verify: >
      After the lawful natural pack exists, a subsequent natural NYSE live session in which
      the VPS evaluator consumes that pack without global stale_pack darkness, publishes an
      advancing served/R2 artifact with a non-empty states map, and the external health plane
      reports the pack basis healthy. #6569's fresh-empty fence must not be in breach.
danger_areas:
  - "Fresh pass_ts or pack_ok=True alone is not D12 acceptance. #6569 proved a fresh artifact can still serve states={} while the evaluator refuses a stale_pack."
  - "Do not replace delayed natural Build-B admission with workflow_dispatch. The ordinary scheduled run identity and its actual build_prophet_live_pack step are part of the evidence contract."
  - "Do not manually dispatch prophet-live.yml while the VPS timer is primary; that bypasses the single-writer production ownership boundary and can create two writers on live/prophet_live.json."
  - "The #6569 sentinel fences are detection evidence, not producer acceptance by themselves. An ahead-of-calendar/fresh-empty fence going green does not prove that #6554's producer path executed naturally."
  - "Nightly-liveness run 33126181894 is a real NO-RUN observation but appears to be the 20:00Z watchdog slot delayed across the 22:00Z fire boundary. Treat the factual absence as evidence; do not widen D12 into a watchdog timing repair or call a scheduler incident from that early page alone."
  - "The same liveness receipt observed intake.eligible_after_skips=25 with intake.originated=0. That is a separate Prophet production-integrity signal; do not silently reinterpret it as D12 causality or repair it inside this carrier."
  - "Current GitHub main may advance on unrelated work while this external gate waits. Reconcile exact run/head and material Prophet source paths before interpreting any later nightly as the D12 acceptance carrier."
unresolved:
  - "D12 production acceptance remains BUILT_NOT_PROVEN. The producer implementation and cleanup are merged; natural arming proof and subsequent live-consumer proof are still owed."
  - "As of nightly-liveness run 33126181894 at 2026-08-27T23:25Z, no ordinary Build-B run had been created after the 22:00Z fire boundary. The external gate remains unresolved."
  - "The historical source/operator of the D12 contamination remains unreproduced/unattributed; do not manufacture a contaminated production store merely to make that provenance easier to demonstrate."
  - "The 2026-08-26T07:43:28Z R2 credential seeding remains separately unattributed and is not a D12 acceptance gate."
do_not_redo:
  - "Do NOT manually dispatch daily.yml or prophet-live.yml to manufacture D12 acceptance while the ordinary scheduler/VPS lane owns production cadence."
  - "Do NOT call a fresh pass_ts healthy when states is empty during the live window; #6569 proved that exact false-green in production."
  - "Do NOT promote D12 from a pack-only receipt. The next natural live session still owes evaluator, publication, non-empty-state, and health proof."
  - "Do NOT create another D12 implementation carrier or restore the temporary red workflow; #6554 and #6565 are the canonical merged effects."
  - "Do NOT manufacture a poisoned close store or replay a Class-D session to force the negative case."
next_actions:
  - >
      PRIMARY EXTERNAL GATE: wait only for the ordinary EDT Build-B schedule carrier
      (daily 30 22 * * *). When GitHub creates it, bind the exact run id/head and inspect
      the actual build_prophet_live_pack step/log. Reject pre-#6554 or ambiguous evidence.
  - >
      If no natural Build-B is created by the watchdog's documented post-bake liveness
      window, treat the nightly scheduler/liveness problem as a separate production incident;
      do not manufacture D12 evidence or fold that repair into this carrier.
  - >
      If the pack receipt is lawful, record the arming half as proven but keep overall D12
      BUILT_NOT_PROVEN until the next natural NYSE session.
  - >
      In that session require evaluator consumption without global stale_pack darkness,
      advancing served/R2 publication, states non-empty, healthy pack basis, and no #6569
      fresh-empty breach. Only then may Sol consider D12 PROVEN_LIVE.
  - >
      Keep the unrelated intake-integrity, credential-attribution, watchdog-timing, and
      2026-07-30 partial-tail investigations separate from this acceptance carrier.
---

# D12 natural-proof gate — 2026-08-27 continuation

The implementation is merged. The temporary proof workflow is gone. The missing item
is production evidence, not more code.

The important new falsifier is #6569: a current pass timestamp is not enough. On
2026-08-27 the lane wrote fresh artifacts all session while serving an empty state map
because its armed pack was unusable. D12 is therefore not accepted until the ordinary
post-merge pack is followed by a real session where the evaluator serves non-empty
states from that lawful pack and the health surfaces remain green.

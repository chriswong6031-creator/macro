---
workstream: "WS:GREY-DEER-RISK-INTELLIGENCE"
session: "worktrees grey-deer-closeout-3a152c -> gd3-acceptance-records (Fable COO, GD-3 + GD-4A.1 wave)"
model: fable
ended_because: complete
mission: >
  Sol next-wave authorization 2026-08-20: build GD-3 (live provisional Risk
  Envelope) under the frozen commission plus seven Sol clarifications; in
  parallel GD-4A.1 (CN/HK forward-ledger freshness in the existing
  GitHub-hosted liveness system). Production acceptance = Gate-8 equivalent
  (real live source change, four-clock receipt, authenticated browser overlay,
  data/ + ledgers unchanged); REAL event only — no fixture/simulation/manual
  mutation (Sol 2026-08-21). No GD-8/9 from this seat.
state_before: >
  GD-2/GD-2R1/GD-4A/GD-1C closed per GREY-DEER-RISK-INTELLIGENCE-2026-08-20.md.
  GD-3 commissioned, build not started. No ledger-stall heartbeat (named
  unresolved). Settled envelope live at bundle fd9ccdbe47f7f008 (2026-08-19
  session), superseded during this wave by the 2026-08-20 settle
  (df843770aee6003c).
changed:
  - path: research/grey_deer/commissions/GD-3_LIVE_PROVISIONAL_ENVELOPE_COMMISSION_2026-08-20.md
    what: >
      Added §0b — Sol's seven binding clarifications (no stage-ceiling
      promotion; one source-adapter authority; raw reads only / no
      double-debounce; observed stage vs dwell state via live_transition;
      four truthful clocks + settled-bundle binding; stale/future/older
      evidence loses precedence and never votes calm; no new quote
      owner/timer/scheduler/boundary/ledger/policy authority).
  - path: research/grey_deer/commissions/GD-4A1_LEDGER_FRESHNESS_LIVENESS_COMMISSION_2026-08-20.md
    what: >
      New GD-4A.1 commission (recorded retroactively in the records PR; the
      build PR #6140 shipped against it), including the post-review budget-1
      adjudication and the crash/max-asof/laziness gates, plus the outcome
      block.
  - path: agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md
    what: >
      GD-3 -> in_progress (pr 6144; merged+deployed; acceptance
      WAITING_FOR_PRODUCTION_EVENT with the witness gap named); new GD-4A1
      wave entry (done, pr 6140, full receipts); next_action rewritten to the
      single remaining step.
  - path: agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-21.md
    what: This handoff.
  - path: research/grey_deer/README.md
    what: Current-next-action rewritten for the 2026-08-21 state.
verified:
  - claim: >
      GD-3 shipped as PR #6144, squash-merged 55d7ea02ce3e on concluded green
      (only non-green check = the by-design ci-authority/codex/merge-queue-pilot
      X). Two build rounds: initial build, then 11 adjudicated amendments from
      an opus adversarial review that returned DO-NOT-MERGE with two REPRODUCED
      blockers — (1) an empty "live" block in risk_state.json (the real
      build_risk_state.py:233-239 exception path) was laundered into
      present=True/FRESH/stage NONE and PAINTED as a calm live read; (2) the
      dwell ticked during outages and de-escalated to calm (stable_stage
      FRAGILE->NONE in 3 fires with live_active false). Also repaired:
      future-clock half-refusal (future built no longer becomes
      source_session/as_of/event_time; L=None, precedence settled,
      stale_reason refused_future), sticky degraded chip copy, dwell ticks
      keyed to DISTINCT source observations (risk_state "built" changes, not
      wall fires), stage-null routes to degraded copy regardless of
      data_state, produced_at uses the injected clock, session-floor law
      pinned for the new consumer in tests/test_risk_state_live_session_floor.py.
    command: >
      gh pr view 6144; git merge-base --is-ancestor 55d7ea02ce3e origin/main;
      review packet (opus reviewer) + builder evidence: 111 passed across
      tests/test_live_risk_envelope.py + test_risk_envelope.py +
      test_risk_state_live_session_floor.py; check_contract_delta 0 introduced
    result: merged 2026-08-21T01:4xZ; all amendments verified in the diff
  - claim: >
      Sol clarification 2 (one adapter authority) is enforced structurally:
      the live builder imports the settled adapters from
      scripts/build_risk_envelope.py with a pure stale_override pass-through
      that leaves settled behavior byte-identical
      (test_gd1_settled_bundle_id_is_unchanged_by_the_refactor), and an AST
      test forbids any state->stage mapping literal in the live module.
      Clarification 1 (no ceiling promotion) holds: no stage_ceiling set
      anywhere live; SourceRead default caps at FRAGILE, so
      TRANSMITTING/BREAKDOWN remain unreachable in both lanes. Clarification
      3 (raw reads): test_module_source_never_accesses_the_display_key +
      upstream trace (the "live" block comes from _verdict_block untouched by
      _debounce, which feeds only "display").
    command: reviewer packet clauses 1-4 (attack angles found nothing); builder test evidence
    result: all clauses hold on the merged head
  - claim: >
      GD-3 deployed to production: live https://www.mastermind-x.com/macro.html
      carries #gde-live-chip, #gde-pending-chip, #gde-live-receipt,
      data-bundle-id="df843770aee6003c", data-settled-session="2026-08-20",
      and risk_envelope_live.js?v=bbe5e528 (rebaked by the nightly's own
      render; the dedicated covering render 32437358718 at the merge SHA also
      ran). Anonymous GET /risk_envelope_live.js returns 401 — the consumer
      script is tier-gated like the payload (@reg_asset default-deny; it is
      NOT on the public allowlist). This is the CORRECT current posture: the
      public-boundary decision was deliberately not taken; the builder's
      PR-body claim that the script is public was wrong (reviewer right);
      anonymous visitors get one rejected request and no overlay.
    command: >
      curl -sL https://www.mastermind-x.com/macro.html | grep -o
      'gde-live-chip|data-bundle-id="..."|risk_envelope_live.js?v=...';
      curl -s -o /dev/null -w "%{http_code}"
      https://www.mastermind-x.com/risk_envelope_live.js
    result: hooks present (1 each), 401 on the script, 2026-08-21 ~04:35Z
  - claim: >
      GD-4A.1 shipped as PR #6140 (2 commits: build + review repairs),
      squash-merged e4f18b53e9d0 on concluded green, and LIVE-VERIFIED:
      workflow_dispatch of nightly-liveness.yml on main (run 32435846087)
      concluded SUCCESS with "market boards | ... cn_ledger=2026-08-20(0)
      hk_ledger=2026-08-20(0)" — the new checks grading the real committed
      ledgers, healthy. Post-review semantics: max_sessions_behind=1 (a
      sustained stall on session D alarms at D+1's 20:00Z look — within the
      next expected market session per Sol's wording; a one-session
      self-healing hiccup stays quiet BY DESIGN); UnicodeDecodeError degrades
      one check instead of crashing the whole watchdog (executed end-to-end
      with real 0xff bytes); newest row = max(asof) over a 50-line tail scan;
      the board path's calendar laziness restored (35-fixture differential vs
      origin/main: zero board behavior change).
    command: >
      gh pr view 6140; gh run view 32435846087 --log | grep "market boards";
      71 passed in tests/test_nightly_liveness.py; --selftest PASS
    result: merged + live-verified 2026-08-21T01:1xZ
  - claim: >
      Next-day organic confirmation of the whole GD-4A family: the settled
      Asia-close lane advanced each ledger exactly once for 2026-08-21
      (commit 927fb6a78046, CN 14 rows / HK 13 rows, tails
      [..., 2026-08-20, 2026-08-21], zero duplicate asofs) — second
      consecutive settled session with correct single-advance behavior under
      the healed gate.
    command: git show origin/main:data/risk_radar_intl/{cn,hk}_forward_log.jsonl | row census
    result: CN 14 / HK 13, one new row each, dups 0
  - claim: >
      GD-3 production acceptance did NOT complete: recorded
      WAITING_FOR_PRODUCTION_EVENT per Sol's explicit fallback. The receipt
      requires an authenticated browser witness (the live payload AND the
      consumer script are Supabase-cookie-gated; app/regwall.py has no ops
      bypass; no VPS shell exists from the fleet host — app/deploy/*.sh run
      ON the box; ~/.ssh/config has no VPS host). The operator's Chrome
      (claude-in-chrome) was unreachable for the ENTIRE 2026-08-21
      11:00-22:00Z live window — 14 connection attempts ~45 min apart, every
      one "extension not connected". No fixture, simulation, or manual
      artifact mutation was substituted (Sol's law). The live plane itself
      ran normally all window (public /live/quotes.json family fresh), so the
      qualifying event is presumed to have occurred UNWITNESSED.
    command: tabs_context_mcp retry log 11:05Z..21:43Z; curl live/staleness.json
    result: witness unavailable; wave held open on the receipt only
unverified:
  - >
    Whether scripts/vps_live_orchestrator.py's new risk_envelope_live module
    executed cleanly on the box during the window (site/live/risk_envelope.json
    exists with lawful content): NOT observable without an authenticated
    fetch or VPS shell. The acceptance re-run proves or falsifies this first.
unresolved:
  - >
    GD-3 wave closure = the four-clock production receipt. Run during any US
    live window (11:00-22:00Z weekday) WITH an authenticated browser:
    in-page fetch('live/risk_envelope.json',{credentials:'same-origin'}) +
    live/risk_state.json on macro.html; verify revision live_provisional,
    settled-bundle binding, precedence, authority all false, truthful clocks,
    live_transition shape; catch the first real live-source change
    (risk_state "built"/live-block change), confirm the envelope reflects it
    within <=2 fast fires; screenshot the painted overlay; scope the
    data/-unchanged proof to the observation interval.
  - >
    The tier-gated consumer script (anonymous 401 on /risk_envelope_live.js on
    a public page) is a deliberate posture, not a defect — but if product ever
    wants the overlay visible pre-auth, that is a separate operator
    public-boundary decision (config/site_access.yml + Caddyfile allowlists).
do_not_redo:
  - "Do not simulate/manufacture the acceptance event (Sol 2026-08-21) — no fixture, local harness, or manual mutation of site/live/ counts."
  - "Do not re-litigate the GD-4A.1 budget: max_sessions_behind=1 was adjudicated against three measured false-page classes; budget 0 violates the module's own measured-budget law."
  - "Do not add risk_envelope_live.js or live/risk_envelope.json to any public allowlist as part of acceptance — boundary unchanged is an acceptance GATE."
  - "Do not start GD-8A/8B/9A before GD-3 production acceptance (Sol gate)."
danger_areas:
  - "site/riskdata/ shared with market-regime-risk; Grey Deer owns only risk_envelope.json inside it."
  - "The live dwell state persists in site/live/risk_envelope.json on the box (gitignored) — a manual delete resets stable_stage baseline; leave it alone."
next_actions:
  - "GD-3 acceptance re-run (any session with claude-in-chrome connected during a live window) per unresolved[0]; on PASS, flip GD-3 to done with the four clocks in the WS record."
  - "GD-8A / GD-8B / GD-9A: commission only after that receipt."
  - "GD-4B / GD-4C remain open, unblocked, uncommissioned."
---

# Grey Deer GD-3 + GD-4A.1 wave — 2026-08-21

Both builds shipped through full adversarial review with real defects found and
repaired pre-merge; GD-4A.1 is live-verified and organically confirmed the next
session. GD-3 is merged and deployed; its wave stays open solely on the
four-clock production receipt, blocked all window by authenticated-witness
availability, recorded exactly as WAITING_FOR_PRODUCTION_EVENT per Sol's
fallback. No GD-8/9 work was started.

---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad1-intel-brief-runtime
model: fable
ended_because: complete
mission: >
  AD-1 runtime implementation: build the Daily EOD Options Intelligence Brief vertical
  slice (engine, producer, receipt-backed artifact, Workspace consumer, flagship board,
  daily wiring, CI ownership, real-data/browser proof) exactly per the frozen
  intel_brief_heuristic/v1.2, open the implementation PR, and STOP for Sol adversarial
  review without merging. AD-2 not started.
state_before: >
  AD-0 (#5830/#5838/#5849) and AD-1P0 (#5860, merge fb23542a) merged and live; v1.2
  frozen in the AD-1 handoff §5.3; no runtime existed. main_at_start 3163c39903c6
  (fb23542a confirmed ancestor); no overlapping open PR on the flagship paths.
changed:
  - path: contracts/options/OPTIONS_INTEL_BRIEF_V1.md
    what: NEW — code-facing executable contract (constants, settled/pending source-clock law, schema, authority table, writer contract).
  - path: engine/options_intel_brief.py
    what: NEW — pure deterministic v1.2 engine (CONFIG-pinned; direction = Q_oi AND Q_skew AND salience only; Prophet zero rank authority; closed bilingual vocabularies).
  - path: scripts/build_options_intel_brief.py
    what: NEW — producer CLI (lawful settled-pair discovery via lib/nyse_calendar, atomic write + semantic no-op, receipt digests, zero network).
  - path: scripts/build_options_command.py
    what: AMENDED — fail-soft pass-through adapter (load_intel_brief sibling of the pinned load_stores; presentation-only helpers; no recompute/reorder).
  - path: templates/options.html.j2
    what: AMENDED — AD-1 board first in Daily Brief (oew-aib-* family, existing tokens only, five states, two-leg glyph, pip meter, Prophet chip, LENS tips).
  - path: site/options.html
    what: REGENERATED via the canonical builder (render-form preserved).
  - path: site/options_intel_brief.json
    what: NEW — real-data artifact; honestly reports STALE_SOURCE on the committed store (latest chains 2026-08-13); nightly self-heals.
  - path: tests/test_options_intel_brief.py
    what: NEW — 51 tests, items 1-33 (contract, direction anti-vacuity, GEX authority, forecast honesty, event semantics, Prophet boundary, temporal/PIT, receipts).
  - path: tests/test_options_intel_brief_ui.py
    what: NEW — 20 tests, items 34-40 (fail-soft, pass-through, parity, board-first ordering, legacy-scope snapshots, no client-side scoring).
  - path: .github/workflows/daily.yml
    what: AMENDED — one producer step post-band immediately before build_options_command; closing-bell deliberately NOT wired (source-clock law).
  - path: config/dag.yml
    what: AMENDED — build_options_intel_brief node (conformance green).
  - path: config/synapse.yml
    what: AMENDED — options-intel-brief registration (display tier, sole consumer = Workspace; 643->644 pin updated; docs/SIGNAL_BUS.md regenerated).
  - path: .github/ci/legacy-jobs.yml
    what: AMENDED — new paths + both suites joined to the exclusive options-workspace job's pytest step (no new job).
  - path: verify_shots/adib_*.png
    what: NEW — 7 crops (OK desktop light/dark, mobile light/dark, zh; degraded light + dark-zh); zero horizontal overflow.
verified:
  - claim: full owning CI step + render guards green locally
    command: "python3 -m pytest tests/test_build_options_command.py tests/test_options_intel_brief.py tests/test_options_intel_brief_ui.py tests/test_render_options_workspace_scope.py tests/test_options_command_close_scope.py -q; check_template_site_sync; check_validated_claims; test_i18n_attribute_guard; test_dag_conformance; test_signal_bus_doc; check_ci_trigger_closure; audit_unrun_tests; check_skip_only_suites; run_ci_pack --validate-only"
    result: 223 passed on the suites; sync OK (89 pairs); validated-claims OK; i18n 6/6; dag 48/48; signal-bus 4/4; closure OK; unrun audit clean; manifest validates (194 jobs)
  - claim: real-data run obeys the source-clock law and reproduces the v1.2 distribution
    command: "python3 -m scripts.build_options_intel_brief [--ignore-staleness diagnostic]"
    result: settled S=2026-08-12, oi_counted_date=2026-08-13, pending 2026-08-13 OI_NOT_YET_SETTLED; eligibility 356/372 (15 insufficient_history, 1 insufficient_coverage); 588 adjusted-contract identity exclusions; ranked 58 (6 shown + 52 overflow), event board 4, risk 4, no_signal_exemplar MU (algorithm-selected); committed artifact honestly STALE_SOURCE (store ends 08-13); receipt_id e5bd3f47..., config_hash dfdf2dfe...
  - claim: browser proof at all required breakpoints/themes/languages with zero overflow
    command: "playwright crops (verify_shots/adib_*.png) + per-page scrollWidth check"
    result: 7/7 shots overflow=False; board renders before What-changed; degraded and pending scenes intentional
unverified:
  - claim: production acceptance (deployed SHA, served page, live artifact advancement)
    what_would_verify: the post-merge continuation (runtime handoff §19) after Sol PASS — merge, nightly advance, browser proof on the served production page
unresolved:
  - "PR CI: all AD-1-attributable reds healed on the second run (import-closure scope, delivery-plane census re-stamp, import pin, owner-disposition + system-map pin — commit 79a8aafb9dac); the remaining ci-gate red is base-inherited contract-drift (main's own baseline run 32110254994 fails the identical step) plus merge-ref transients (chat-nav/wrongway — green locally and on main's baseline). Healing main's drift is outside this PR's authorized paths (runtime handoff §17). Receipts in the PR comment on #5872."
  - risk_warnings[]/event_board[] are not rendered as separate board sections in AD-1 UI (adapter may not invent a cross-board order); Sol to rule whether a follow-up adds dedicated sections.
  - board-level INSUFFICIENT_COVERAGE reuses ELIGIBILITY_GATE=0.60 (contract had no separate constant) — flagged for review, documented in code.
  - committed store's chains end 2026-08-13 (Fri 08-14 + Mon 08-17 sessions absent from git) — upstream collection/commit lag, NOT an AD-1 defect; the artifact correctly reports STALE_SOURCE until the nightly advances the store.
next_actions:
  - Sol adversarial review of the implementation PR (NOT merged by this session, per the AD-1 runtime handoff PR policy).
  - On PASS - merge normally, let daily.yml advance the artifact, browser-proof the served production page, reconcile deployed SHA/receipt, append the production-acceptance record, return to Sol. AD-2 does not begin.
do_not_redo:
  - The v1.2 method or its constants (CONFIG-pinned, test 14) — any change is a model_version bump + review.
  - The settled/pending source-clock law (tests 23-29) — closing-bell wiring remains forbidden.
  - The two-builder packet split (engine/producer/tests then consumer/UI) — both landed green; subagent reports in the session transcript.
danger_areas:
  - Uncommitted wiring in a worktree shared with builder subagents can be reverted by a builder cleaning its diff (happened once this session; wiring re-applied and committed immediately). Commit orchestrator-owned edits before spawning builders.
  - site/options.html committed form is the RENDER-LANE form (extracted hashed CSS + ?v= stamps); a raw local build_options_command bake inlines CSS — never commit the raw form.
  - The artifact's semantic no-op keeps bytes unchanged on same-receipt reruns — do not "fix" mtime churn by removing it.
---

## Summary

AD-1 is implemented end-to-end and review-ready: 4,900+ new lines across engine,
producer, contract, adapter, board, wiring, and 71 new tests (223 green with the
neighbouring suites), with real-data and browser proof captured in verify_shots/.
The implementation PR is open and deliberately NOT merged — Sol owns the adversarial
review; production acceptance is a separate continuation after PASS.

## Sol correction round (same day, same PR)

Sol REQUEST_CHANGES (B1-B5) executed as a commissioned orchestration: census (scout) →
core build B1-B4 (builder, `f6c4c01a`) → design packet (designer, accepted with Fable
rulings) → consumer build B5 (builder, `d5869b31`) → debugger root-cause of a crowding
percentile defect (tie-block top-rank × 0DTE mass-zeros; 14/18 sessions fired c1
universe-wide) → Fable ruling (midrank + zero-guard, `9f7ef5ca`) → Opus adversarial
review E1 (1 blocker + 6 major + 8 minor, ALL surviving green suites) → adjudicated
repair packet (`1fbf6af5` + `bf8a8d33`): receipt closes over ALL consumed chains +
resolved universe; fail-closed UNIVERSE_RESOLUTION_FAILED; evidence-derived freshness
on both attack paths; c1 cross-section coverage predicate (0.50, structural); truthful
4-entry no-signal vocabulary; event-horizon implied move on the event rail; four
theater tests rewritten to bite; Prophet group precedence by ruled order; §9 known-limit
disclosures (universe/earnings as-of-now vintage, c3-dominated risk rail pending v1.3
d1 revisit, forward-compat projection fields, FRESH_PENALTY unreachability,
verify_shots provenance). Final suites 297 green ×3 runs (one unreproduced transient
failure observed once, disclosed). Frozen v1.2 thresholds/authority untouched
throughout. PR still NOT merged; AD-2 not started.

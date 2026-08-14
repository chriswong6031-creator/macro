---
workstream: WS:LIVE-ENTRY-RADAR
session: live-entry-radar-w2-pr2-26fe57
model: fable
ended_because: complete
amends: >
  Same-day second handoff — amends the W1 handoff of 2026-08-14 in place
  (latest-wins ranking; suffixed filenames are dropped). W1's durable facts:
  merged as PR #5625 (000732bd80d594a62f9923466e5be1cbe9b86ec7, 17:31Z), 93
  tests, three ratified deviations in contract §18 A3, do_not_redo items now
  carried in the workstream record.

mission: >
  W2 / PR-2: detector framework + exact G0 Grey Dot champion consumption/parity
  under the frozen contract. Artifact consumption + parity, never a second
  implementation; F6 first; Expert Preservation adapter into the append-only
  mastermind.entry_event.v1 store; family enums minted from emitter receipts;
  Prophet untouched; no W3 roll-in.

state_before: >
  W1 merged (#5625) but recorded in_progress in the workstream (reconciled here
  from merged evidence). Shared deep store: git-canonical CURRENT (feed_end
  2026-08-13); the census's "5-week staleness" was the primary checkout's
  unpulled working tree. charting-app origin/master @ 82cb8cbf fetched read-only
  for spec + staged emitter runs.

changed:
  - path: engine/entry_radar/ (entry_events, indicator_ingest, g0_adapter, detectors)
    what: "The W2 package: append-only entry_event.v1 store (typed edges, per-field
      field_origin, authority all-false at construction, anchor_ts discriminator in
      the address per A4.6, family_first_available as {kind,value} struct +
      pre_channel_reconstruction per A4.7); governed indicator/v1 ingestion
      (freshness/identity/pre-fence gates fail-closed, two-phase commit, verbatim
      preservation, SELL/warnings excluded-and-counted with cap disclosure); exact
      G0 adapter (A1.1 union, promoted_by/dedup_suppressed_by ts-join edges,
      cap-window honesty, conservative finality per A4.1/F6c); detector framework
      (G0_GREY_DOT@1 registered with stable spec_hash 9be89a8acc8b905c, C1-C5/F1
      reserved-by-name, §13 lifecycle types)."
  - path: tests/ (test_entry_radar_g0_parity, test_entry_radar_events, test_entry_radar_w2_guards) + tests/fixtures/entry_radar/
    what: "F1-F6 parity suites over 5 committed real indicator/v1 slices (fresh
      feed 2026-08-13 + the F6c truncation pair) with full 40-dot side-channel
      tables as the label-join tripwire; append-only/no-flattening/mutation
      guards; AST-level protected-import guard; CI-wired in legacy-jobs.yml."
  - path: research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md
    what: "§18 A4 (append-only): F6 operationalization corrected against the
      measured emitter (frozen wording falsified by 20/28 lawful provisional
      fires; F6a′/F6b/F6c with the 4 enumerated retro-materialization sites and
      the one-session settle law); as_of≠feed_end; family enums minted; de-dup
      known-lossy narrowed to the cap window; A4.5 known_ts honesty; A4.6
      discriminator; A4.7 first-availability struct."
  - path: research/live_entry_radar/ (W2_G0_PARITY_RECEIPTS.md + 4 JSON receipts)
    what: "Full session receipts: freshness verdicts, F6 falsification + corrected
      law family + detection-power honesty (39-date pre/post footprint; truncation
      probes do NOT fire on the pre-#392 map), exact parity tables both vintages,
      family census, reconstructability classification."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W1 reconciled to done from merged evidence; W2 in_progress → PR number
      at ship."

prs: [PENDING]

verified:
  - claim: "Parity EXACT: Track A §2.6 tables reproduce byte-for-byte at the census
      vintage (8/11/10 dots, 4 NFLX watches) and are invariant under 26 sessions of
      real extension."
    command: "scratchpad gen_fixtures.py (staged origin/master signal_layer @82cb8cbf
      on git vintages 4f68f8d95030 / 9ea1bcb6844c) → research/live_entry_radar/W2_PARITY_REPORT.json verdicts"
    result: "track_a_exact_at_vintage true ×3; final_dots_invariant_under_extension true ×3"
  - claim: "F6 ran FIRST and falsified the frozen wording; corrected laws measured
      (F6b 0/337; F6a′ 333/337 with 4 enumerated settle sites; 9 unprobeable
      disclosed); pre-#392 caught by known-answer footprint (39 dates), NOT by
      truncation probes."
    command: "f6_first.py / f6_laws.py / f6_power2.py receipts in research/live_entry_radar/W2_F6_*.json"
    result: "as recorded in contract A4.1 + receipts §2"
  - claim: "All five entry_radar suites green after two adversarial rounds."
    command: "python3 -m pytest tests/test_entry_radar_g0_parity.py tests/test_entry_radar_events.py tests/test_entry_radar_w2_guards.py tests/test_entry_radar_w1.py tests/test_entry_radar_producers.py -q"
    result: "263 passed, 2 skipped (W1 git-diff guards arm on commit)"
  - claim: "Prophet non-interference mechanical and clean."
    command: "git diff --stat origin/main -- engine/entry_signal.py engine/signal_gate.py engine/confluence_tiers.py engine/signal_quality.py 'engine/prophet_*.py' engine/washout_turn.py engine/mtf_upturn.py engine/technicals.py"
    result: "empty; AST import guard pins it in CI"
  - claim: "Adversarial review (opus) ran twice: round 1 = builder discrepancy
      (event_id collision, adjudicated → A4.6); round 2 = 1 BLOCKER (cap-window
      vintage-varying context breaking cross-vintage append-only) + 5 MATERIAL + 12
      MINOR, all resolved or receipted; 11 mutation probes injected/caught/reverted."
    command: "review transcripts; per-finding tests named in the suites"
    result: "263 passed after fixes"

unverified:
  - claim: "The PRODUCTION Terminal slice writer (VPS) runs origin/master-equivalent
      code on canonical feeds."
    what_would_verify: "First real slice read on the VPS lane (PR-4); the in-code
      (source_hash, signal_era) identity pin + freshness gate refuse a mismatch
      until then."

unresolved:
  - "tests/test_prophet_lifecycle_state.py reds the armed unrun-suite gate on the
    base (inherited from merged #5506); heal owned by PR #5682 (armed) — this PR
    sequences behind it, do NOT duplicate the wiring."
  - "stop_sweep_reclaim first-availability is {unrecorded, None} — its lane commit
    was never dated with a receipt; date it if a consumer ever needs the bound."
  - "Side-channel grey dots carry signal_known_ts=None (artifact_absent) by A4.5
    law; the deep-history (pre-40-cap) grey record needs the §3.2 locked-spec
    fallback, deliberately NOT built in W2."

next_actions:
  - "W3 (PR-3): 1D/4H challenger family + PIT mutation tests per contract §4/§5;
    C1-C5 specs lock there against the RESERVED ids; EOD-mutation test is the
    acceptance gate."
  - "At W3 start: re-check feed_end + whether PR #5682 landed (unrun-gate heal);
    re-read contract §18 A4 (the F6 law family and finality semantics bind every
    later PIT test)."

do_not_redo:
  - "Do not re-run the W2 review cycles — findings and fixes are receipted in the
    suites (per-finding test names) and contract A4; the F6 frozen-wording
    falsification is adjudicated, do not 'restore' the truncate-at-ts assertion."
  - "Do not recompute known_ts for side-channel dots (A4.5) — artifact_absent is
    the correct final state, not a gap to fill."
  - "Do not read charting-app's working checkout for spec (month-stale); spec reads
    pin origin/master (@82cb8cbf for W2 receipts)."
  - "Do not treat as_of as feed_end (A4.2): it is the last 3D bar OPEN, a lower
    bound with ≤2 sessions slack."

danger_areas:
  - "Sparse worktree: data/, site/ absent — parity fixtures are committed under
    tests/fixtures/entry_radar/; never add a test needing materialized data/."
  - "Protected paths (contract §16) untouched and guard-pinned; engine/technicals
    import is forbidden in Radar modules (indicator-core law §4)."
  - "The entry_event store has NO durable writer in W2 — any data/ write before
    PR-5's reconciler violates the single-writer law."
---

---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: prophet-conditional-fusion-pr1b (worktree prophet-conditional-fusion-pr1b-ae0bf4, branch claude/prophet-fusion-pr1b)
model: fable
ended_because: ci_handoff
prs:
  - "#5593"
  - "#5602"
  - "#5604"
  - "#5667"
mission: >
  PR-1b: the frozen, counterfactual-replay-labelled, NON-promotion-bearing baseline
  race — G0/G0'/G1/G2/G3/G4 + C1 on the graded-board frame with the frozen O1-O6
  rulers and the PR-1a harness — answering the six commissioned architectural-triage
  questions, plus the still-open PR-1a §13.0 live-closure check. This file is the
  DAY's canonical handoff: the PR-0 and PR-1a session records are absorbed below
  (same-day handoffs amend in place; a suffixed second file is dropped by
  latest-wins ranking).
state_before: >
  PR-0 (#5593) and PR-1a (#5604) both merged 2026-08-14 (10:03Z / 11:33Z). No
  post-PR-1a-merge nightly had completed: daily.yml runs of 08-13T23:20Z and
  08-14T00:06Z still queued/pending with pre-merge heads. Candidates store: last
  CURATED stamp 2026-08-07 (79 scored rows); the 08-12 stamp is scan-tier-heal only
  (commit 071017a3). #5578 and #5583 PR-0s merged the same morning. The graded
  frame: retro_grades.parquet, 24 dates 06-15..07-31, H in {5,10,21}, 442 H=21 rows.
changed:
  - path: research/prophet_fusion/families.yml
    what: "graded-frame members homed (off_high->F2, sue_fresh->F4, news_burst->F8
      with a scoped forward_only->pit rescope for the ledger wiring only,
      smartmoney_add->F5 as a NEW smart_money_board_chip member — the registry's
      smart_money_13f stays wired:false by PR-1a's own pin, two wirings one family
      one vote, insider_cluster->F5, gex_confirm_verdict->F5); wired_from dating
      added (the PR-1a review advisory); altdata_conv_gte2 -> excluded_columns
      (unhomed cross-desk count); no existing membership moved; authority all-false"
  - path: scripts/prophet_fusion_race.py
    what: "the race runner — snapshot adapter over frozen published payloads, G0
      replay through engine/us_board_rank's OWN leg functions with a hard
      byte-exact validation gate, G3/G4 edge-leg variants via the same machinery,
      G2 from the published conviction.potential.score, C1 four-family glass-box
      vote with REGISTERED_SIGNS (a-priori sources named), deployed-composition
      metrics, date-blocked paired bootstrap, permutation floor, tie-sensitivity,
      BH-FDR on secondaries, the §8.7 power block written before outcome cells"
  - path: research/prophet_fusion/pr1b_baseline_race/report.json
    what: "committed machine table; counterfactual_replay:true,
      non_promotion_bearing:true, horizons_available:[5,10,21]; byte-identical
      reproducible from the CLI (no wall-clock stamp)"
  - path: research/prophet_fusion/PR1B_BASELINE_RACE.md
    what: "the race doc §0-§16 + the main-loop Adjudication (six answers + the
      shadow-accrual recommendation: G3, G4, C1, C1-minus-F2 into PR-3 prereg)"
  - path: tests/test_prophet_fusion_race.py
    what: "37 tests: determinism, identical candidate sets, family-vote law,
      sign law (structural: rung builders never see outcome columns), composite
      fence, fold-refusal presence, wording fence, G3 inversion, G4 algebra,
      replay-gate refusal, deployed-cell NA-stage fix pin"
  - path: tests/test_prophet_fusion_families.py
    what: "wired_from-resolved phantom check; as_of availability vocabulary; two
      new fences; existing pins preserved"
  - path: .github/ci/legacy-jobs.yml
    what: "race suite registered in the PR-1a fusion step pattern; audit_unrun_tests
      exit 0"
  - path: agentos (this file, WS record, 2 discoveries)
    what: "WS w1 done / w1b awaiting_ci / w2 rebased onto w1b; next_action carries
      the still-open §13.0 closure; DSC-NAME-SCORE-HAS-TWO-DISAGREEING-MEMORIES;
      DSC-COVERAGE-FLOOR-MEASURES-PRESENCE-NOT-VARIANCE; suffixed -pr1a handoff
      absorbed here and removed"
verified:
  - claim: replay validation gate passed before any race number was read
    command: scripts/prophet_fusion_race.py replay_validation stage
    result: "08-12 and 08-13 byte-exact (max|Δ|=0.0, 70/71 rows); 08-07 diverges
      16.3 pts ALL in the entry leg = §6.6's v1->v2 entry re-valuation reproduced;
      0 stage mismatches, 0 percentile mismatches"
  - claim: the race is deterministic and committed-report-reproducible
    command: run CLI twice; TestDeterminism
    result: byte-identical report.json both times
  - claim: no lawful fold exists on this frame and none was manufactured
    command: folds_for_labels strict via the race runner
    result: "0 usable folds; §9.2 refusal embedded verbatim in report + doc §10"
  - claim: headline race read (H=10, deployed, 15 common dates)
    command: report.json results + doc §4
    result: "G3 P@5 0.568 / G4 0.560 / G0 0.493 / G2 0.477 / C1 0.453 / G0' 0.440 /
      G1 0.440; EVERY primary delta CI includes zero; MDE ~17.4pp vs the +3pp
      registered increment; G0' permutation floor p=0.974; G3 p=0.067"
  - claim: C1 family accounting is honest
    command: doc §9; c1_analysis
    result: "4 families voted (F1 dropped at 25% coverage; F3/F7 absent; F6
      structurally excluded); F2 partial|G0 -0.083 CI excl. zero NEGATIVE; F5
      +0.074 CI excl. zero; F4 ~0; F8 vote-inert (19/1493 fires); LOFO F2 removal
      +4.0pp"
  - claim: fusion suites + neighbors green
    command: pytest race/families/arena/labels suites; test_us_board_rank.py
    result: "177 passed (fusion) + 324 passed (board rank); audit_unrun_tests exit 0"
  - claim: mutation receipts bite
    command: sign flip / leg weight 30->31 / fold-embed delete
    result: "C1 moves + sign-law test green / ReplayValidationRefusal, no report /
      TestFoldRefusal red — all restored"
  - claim: independent adversarial review ran before the PR opened
    command: opus reviewer over the branch diff (10-attack commission + CI/registry checks)
    result: "see PR body review disposition — blockers resolved pre-push"
unverified:
  - claim: PR-1a §13.0 live closure — the post-merge nightly stamps a fresh curated date
    what_would_verify: "first post-#5604 daily.yml completion: fresh curated
      stamp_date in data/us_prophet_rank/candidates, staleness/no-advance warnings
      quiet, prior rows immutable, Aug 8-13 gap NOT backfilled. Not observable this
      session (runs queued pre-merge heads); deliberately NOT dispatched — left to
      the owning lanes per the recovery etiquette"
  - claim: CI packs green on the full PR-1b diff
    what_would_verify: PR checks concluding (merge-on-green armed; session owns to merge)
unresolved:
  - "PR-1a advisories filed not fixed here (A3 _safe_out_dir scope, A4 dummy stamping,
    A5 disclosed_gaps fail-open, A7 sparse-tree vacuity, min_train/min_test kwargs) —
    A1 mdd_basis WAS fixed in this PR (doc §6 names mae_close_excess_spy)"
  - "name_score two-memories divergence -> DSC + chipped to the owning lane; G2 is
    pinned to the published value meanwhile"
  - "coverage-floor variance gap -> DSC; floor law revision belongs to PR-2's registry
    pass, deliberately not patched into a race PR"
  - "insider panel (2026q1 stall) unchanged; short_int PIT LANDED mid-session (#5602
    MERGED — historical dates resolve pit_settlement; the follow-up it sequences:
    flip families.yml short_int pit_status -> pit_settlement now that BOTH PR-1a and
    #5602 are merged, and re-run scripts/backfill_finra_short_interest.py before any
    deep historical short_int join — panel parquet absent on the primary checkout,
    committed history 3 settlements, first knowable 2026-07-10); F1 coverage
    on the graded frame is 25% (tier_cascade) so F1 sat out C1"
next_actions:
  - "Verify the §13.0 closure on the first post-merge nightly (see unverified) and
    flip the WS next_action when it lands"
  - "PR-2 (wave w2): C2 regularized stack + redundancy matrices + incremental
    harness; inherits C1's weights question and the §9 family table"
  - "PR-3 prereg BEFORE first stamped shadow night: G3, G4, C1-as-raced, C1-minus-F2
    vs G0/G0' — registered now in the Adjudication so C1-minus-F2 cannot be called
    outcome-selected later"
  - "Watch ~2026-08-24: first H=10 grade maturation for v1-era stamps (PR-0 note)"
do_not_redo:
  - "Do not re-run the race to 'improve' a rung — the report is frozen; a new rung is
    a new registration (arena §8.2)"
  - "Do not quote any PR-1b number without its CI and the counterfactual_replay label;
    §8.1's increment is met by NOTHING on this frame"
  - "Do not read data/name_score/us_calls.parquet as 'name_score' for board questions
    — two disagreeing memories (DSC); the published value is the G2 quantity"
  - "Do not fix the F8/news_burst floor gap by hand-tuning C1 — it is C2's registered
    weights question"
  - "(inherited) PR-0/PR-1a do_not_redo lists remain binding — absorbed below"
danger_areas:
  - "The G0 'champion' on 06-15..07-31 is a REPLAY of today's constants over boards
    that ranked by legacy keys — never describe it as what the champion did live"
  - "G4's table position leans on a tie-break (distinct-score ratio 0.422; P@5 spans
    [0.520,0.613] under 200 random tie-breaks) — carry the band, not the point"
  - "The 7 payload-less dates (06-15..06-24) leave the DEPLOYED cell by name; pooling
    them back in under a deployed label re-introduces the defect commit 36f0742a
    fixed and test-pinned"
  - "(inherited) graded-frame era boundaries + gh-quota + families.yml-is-law notes
    from the absorbed records below"
---

Cold-stranger summary: PR-0 froze the arena, PR-1a restored the sensory spine and
built the harness, PR-1b ran the first race. The race's one strengthened hypothesis:
the champion's 25-pt edge leg points the wrong way at H=10 on the only graded frame —
four independent constructions agree (G3 leads everything, G4 second, G1 last, C1's
F2 is the only CI-excluding-zero family and it is negative) — but every primary CI
includes zero on a frame whose minimum detectable effect (~17.4pp) dwarfs the
registered +3pp increment, so nothing here authorizes a production change. Next real
evidence arrives from forward accrual: the §13.0 closure, then PR-3's prospective
shadow race (G3/G4/C1/C1−F2, prereg'd in the Adjudication).

---

## Absorbed record — session 2 of 2026-08-14: PR-1a (prophet-fusion-pr1a, #5604)

The full PR-1a handoff, previously at PROPHET-CONDITIONAL-FUSION-2026-08-14-pr1a.md
(removed: suffixed same-day files are dropped by latest-wins ranking):

```yaml
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: prophet-fusion-pr1a (same worktree as PR-0, branch claude/prophet-fusion-pr1a)
model: fable
ended_because: ci_handoff
prs: ["#5604"]  # (the original file mistakenly listed #5593)
mission: >
  PR-1a of the fusion program: root-cause and fix the stalled US Context Vector
  accrual, ship the §13 telemetry columns, the canonical evidence-family registry
  (families.yml), and the arena harness skeleton with the frozen O1-O6 rulers and
  §9 validation law — all zero-authority, nothing touching Prophet's live rank path.
state_before: >
  PR-0 (#5593) merged 2026-08-14T10:03Z. Context-vector store had 4 stamped days
  (07-31, 08-05/06/07), nothing since — the nightly board ran while the store's
  fail-soft writer silently threw every night from 08-08.
changed:
  - engine/neuralweb/context_api.py — _regime_dim merge path emits SCALARS ONLY
    (dict-valued regime__live/regime__history was the root cause of every failed
    append since 08-08)
  - engine/us_context_vector.py — object-column NaN->None sweep; runtime containment
    quarantine with line-start ::warning; loud append-failure + quiet-append
    warnings; §13 telemetry columns (16, zero authority); §13.7 buy-lane
    reconciliation receipt
  - engine/confluence_tiers.py + engine/signal_gate.py — stoch_ob/stoch_bear/
    macd_bear per-leg null-state surfaced; gate DECISION byte-identity pinned by
    sha256 goldens from pre-edit HEAD
  - scripts/grade_us_prophet_candidates.py — nightly staleness tripwire
  - scripts/build_stock_library.py — telemetry load wiring (read-off only)
  - research/prophet_fusion/families.yml + tests — 8 families / 54 members / 180
    store columns homed exactly once; 34/34 mutation catches
  - scripts/prophet_fusion_arena.py + scripts/prophet_fusion_labels.py + tests —
    harness skeleton: labels O1/O2/O3/O5 (entry+confidence DEFERRED, never proxied),
    walk-forward folds with §9.2 refusal, PIT/contamination refusals, fold-scoped
    normalizer, coverage null!=zero, dummy end-to-end selftest; 82 tests
  - tests/test_us_prophet_grades.py — zero-authority fence allowlist +
    prophet_fusion_labels with rationale; label_only_stores declaration
  - .github/ci/legacy-jobs.yml — five suites registered
  - data/us_prophet_rank/README.md — new columns + regime__basis boundary
verified:
  - root cause reproduced empirically (dict-valued regime merge, not inferred)
  - producer can append a new nightly PIT row (scratch e2e: new stamp 3 rows; 7,759
    prior rows x 180 cols value-identical; keep-first idempotent; repo data/ untouched)
  - 285 tests green post-review; gate decisions byte-identical (mutation receipt)
  - audit_unrun_tests exit 0
  - opus adversarial review: 1 BLOCKER + 4 MAJOR resolved (sue_z de-listing; three
    silent no-advance paths -> line-start warnings; label_only_stores + red-on-rot
    test; disclosed_gaps.json store-scoped; hub/attention outage warnings); goldens
    independently reproduced 16/16
unresolved (still true after PR-1b):
  - catalyst_class / psq_stage / day3_mark_class SKIPPED (no same-night producer)
  - gex_state shipped as gex_confirm_verdict (three-vocabulary split risk)
  - live-ONLY regime path returns kitchen-sink dict (quarantined loudly if it fires)
  - insider panel + short-interest PIT chipped separately
  - review advisories A1/A3/A4/A5/A7 + registry wired_from + fold kwargs ->
    A1 and wired_from LANDED in PR-1b; the rest still open
do_not_redo:
  - do not re-diagnose the accrual stall (pinned by test) 
  - do not backfill the Aug 8-13 store hole (honest history)
  - do not add a catch-all pytest collector (suites are named by design)
danger_areas:
  - zero-authority fence allowlist now 5 entries; new importers need adjudication
  - regime__basis flips recomputed_history->pit_live at the 08-14 boundary
  - arena selftest synthetic metrics are fixture properties (dummy:true) — never findings
```

Cold-stranger summary (PR-1a): the store stalled because a context-dimension producer
began emitting nested dicts the parquet schema-union could not absorb, and the
writer's fail-soft caught the explosion silently every night. The fix makes the
producer scalar-only, quarantines unknown non-scalars loudly, and makes silence
itself alarm. Everything else is measurement scaffolding under frozen law.

---

## Absorbed record — session 1 of 2026-08-14: PR-0 (prophet-us-conditional-fusion-pr0, #5593)

*Plus the same-day si-pit chip session's in-place addendum (#5602, MERGED): the
`_short_int_dim` snapshot_not_pit landmine is FIXED for historical dates —
`engine/neuralweb/context_api.py` resolves them PIT against the history+panel union
gated on knowable_date (settlement + 10d), basis `pit_settlement`; current dates keep
`snapshot_not_pit`. Its sequenced follow-ups for this program: flip the families.yml
short_int member's `pit_status` → `pit_settlement` (deliberately not touched by
#5602), and re-run `scripts/backfill_finra_short_interest.py` before any deep
historical short_int join (committed history: 3 settlements, first knowable
2026-07-10).*

```yaml
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: prophet-us-conditional-fusion-pr0 (worktree prophet-us-conditional-fusion-a4e2ae)
model: fable
ended_because: ci_handoff
prs: ["#5593"]
decisions: [DEC:PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY]
mission: >
  PR-0: record the ruling superseding blanket zero-authority, census the estate,
  freeze the champion/challenger arena + outcomes + validation protocol, define the
  four-layer architecture and interop with #5578/#5583, run the required independent
  adversarial review, ship docs-only.
changed:
  - research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md — NEW, 13 deliverables,
    §17 review disposition (11 blockers resolved in-doc)
  - agentos WS + DEC records — NEW
  - research/DO_NOT_REBUILD.md — KILL-FUSED-COMPOSITE Amendment 3 +
    KILL-POSITIONING-FUSION Amendment 1 + compiled blocklists (same PR by law)
verified:
  - agentos validate 39 records clean; 124 agentos tests green; blocklist drift OK;
    validated-claims exit 0
  - context-vector store stalled at 08-07 (4 stamped days ever)
  - live prophet score never graded (grades/ absent; scorecard available:false)
do_not_redo:
  - do not re-run the estate census (§2-§6 carry it with receipts)
  - do not re-litigate the 11 review blockers (attack the RESOLUTIONS if attacking)
  - do not amend further DNR rows for this program
  - do not proxy the Entry head with grades-store MDD/MFE orderings (withdrawn)
danger_areas:
  - families.yml is the law when it lands; keep its tests in the same PR
  - era boundaries make naive pooling silently wrong
  - gh quota: future waves must not poll CI
  - build_prophet.py stale 'us_prophet_v1' literal (fix rode PR-1a)
next (as written then):
  - PR-1a (landed, #5604) -> PR-1b (this file's session) -> watch ~08-24 first H=10
    maturation -> add sibling WS deps when #5578/#5583 merge (BOTH MERGED 08-14;
    prose refs can graduate to depends_on in the next WS touch)
```

Cold-stranger summary (PR-0): read the masterplan top-to-bottom (§0 ruling → §17
review); it is self-contained. The one live operational fact to check before building
anything: has the context-vector store stamped a night since 2026-08-07? If not,
§13.0 outranks everything else in PR-1a. (PR-1a fixed it; PR-1b left the closure
check open pending the first post-merge nightly.)

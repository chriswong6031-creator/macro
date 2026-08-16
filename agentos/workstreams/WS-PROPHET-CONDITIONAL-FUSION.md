---
key: PROPHET-CONDITIONAL-FUSION
title: Prophet US Conditional Intelligence Fusion (VNext meta-ranking)
objective: >
  Replace the blanket zero-authority doctrine on Prophet US intelligence lobes with
  earned conditional authority: a frozen champion/challenger arena (G0-G2, C1-C5),
  typed evidence families with anti-double-count lineage, a contextual router under
  the Stock Identity method law, multi-head outcomes (selection/asymmetry/entry/
  fragility/confidence), and a promotion gate for every rung above C1.
  SUPERSEDED CLAUSE, kept as record: this objective read "and a promotion gate that the
  current us_prophet_v2 champion must lose before any live ranking change ships" until
  the Chairman override of 2026-08-15 (DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER),
  which made C1 the canonical US ranker (us_prophet_v3) without that gate. The gate is
  NARROWED, not repealed: it still governs C2-C5 and every claim of predictive alpha.
status: active
program: prophet-us
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: fable
class: research
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - engine/us_prophet_fusion.py
  - scripts/us_prophet_fusion_compare.py
  - research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md
  - research/prophet_fusion/
  - scripts/prophet_fusion_arena.py
  - scripts/prophet_fusion_labels.py
  - scripts/prophet_fusion_race.py
  - scripts/prophet_fusion_c2.py
decisions:
  - DEC:PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY
  - DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER
  - DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW
  - DEC:FUSION-FAMILY-NEAR-CONSTANCY-IS-A-REGISTRY-QUESTION
landmines:
  - "A NIGHTLY CAN PUBLISH TO THE SITE AND NOT TO GIT. On 2026-08-16 run 31913143619
    the `publish` job deployed a canonical us_prophet_v3 board (Pages, 06:12:24Z) while
    `engine` concluded FAILURE on push contention, so main kept the pre-override v2
    artifact (as_of 2026-08-13). The first v3 board was never committed. Anything that
    reads the repo to learn 'what shipped' is wrong on such a night — in either
    direction. Acceptance evidence for the override is the Pages artifact + that run's
    engine log, NOT site/factordata/us_standouts.json on main."
  - "Five per-leg store columns go NULL from the first us_prophet_v3 night —
    us_context_vector.py:899-901/:1070-1071 and us_candidate_lanes.py:481-482 read
    components/points off `prophet`, but on a v3 row the legs live on prophet_shadow.
    Null-not-zero (so no gate breaks) and no US test pins them, so it is silent. Chipped
    task_8c904665; leaving them null is a defensible answer."
  - "Context-vector store accrual STOPPED 2026-08-07 (4 stamped days total) while the
    board runs nightly — chipped for diagnosis; PR-1 verifies the fix. Masterplan §4.0."
  - "short_int historical leakage FIXED in #5602: pit_settlement via knowable_date
    (= settlement + 10d), historical dates never fall back to the snapshot. Residual:
    committed history depth is 3 settlements (first knowable 2026-07-10) and the 2018+
    panel parquet is absent on the primary checkout — re-run
    scripts/backfill_finra_short_interest.py before deep historical joins; flip
    families.yml pit_status only after PR-1a and #5602 both merge."
  - "insider panel collector stopped at 2026q1 — insider__absent is 100% on Aug rows;
    the first-named lobe of the CEO ruling cannot be evaluated until repaired."
  - "data/edgar/sue_phase0.json records a shallow-panel WIRE verdict that the deep
    survivorship-clean panel later reversed — never cite it as a live GO."
  - "The two 'memories of the board' disagree: candidates store vs snapshots.jsonl buy
    lanes differ by 5 names on 2026-08-07 — arena joins key on the snapshot."
do_not_redo:
  - "Do not re-litigate C1's adoption against the w7 gate — DEC:PROPHET-FUSION-IS-THE-
    CANONICAL-US-RANKER settled it on 2026-08-15. The gate still governs C2-C5."
  - "Do not bump SELECTION_ERA for a ranking change. It names the SELECTION regime; the
    override moved BOARD_DEFINITION only, and resetting the era restarts the H=63
    episode clock the era's own revision ruling exists to protect."
  - "Do not re-tune the variance floor because F8/F4 read near-constant on a live pool.
    A sparse-but-variable event flag passing IS the registered acceptance test, the
    floor is feature-only, and tuning it against an observed ordering is the same act
    the PR-2 do_not_redo forbids against outcomes. Change the REGISTRY if the vote is
    wrong."
  - "Do not let a degraded night publish under us_prophet_v3. The fallback stamp
    (us_prophet_v2_fallback) and the row-derived published_definition() exist so a
    forward ledger can never pool a fusion-ranked night with a fallback one."
  - "Do not restore the additive potential_score, a confirming-desk-count score, or any
    unconditional composite — the CEO ruling explicitly does not authorize them."
  - "The two DNR row amendments LANDED in PR-0 (#5593):
    DNR:KILL-FUSED-COMPOSITE Amendment 3 and DNR:KILL-POSITIONING-FUSION Amendment 1,
    with compiled blocklists regenerated per masterplan §12 and §17 attack 13; do not
    re-defer or re-litigate absent new evidence."
  - "Do not register anything inside Live Entry Radar's detector arena — entry-detector
    fusion is its reserved F1_FUSION slot; this program fuses cross-family only."
  - "Do not build a rival fingerprint/epoch/personality stack — consume
    stock_identity.* interfaces (#5583) and adopt its Method Law channels A/B/C."
artifacts:
  - research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md
waves:
  - id: w0
    title: "PR-0 — architecture, census, frozen arena, adversarial review"
    status: done
    pr: "#5593"
  - id: w1
    depends_on: [w0]
    title: "PR-1a — accrual restoration + telemetry columns + families.yml + arena harness skeleton"
    status: done
    pr: "#5604"
  - id: w1b
    depends_on: [w1]
    title: "PR-1b — frozen baseline race G0/G0'/G1/G2/G3/G4+C1, counterfactual_replay, non-promotion-bearing"
    status: done
    pr: "#5667"
  - id: w2
    depends_on: [w1b]
    title: "PR-2 — C2 regularized family stack + redundancy matrices + incremental harness"
    status: in_progress
  - id: w2b
    depends_on: [w2]
    title: "PR-2b — CHAIRMAN OVERRIDE: C1 canonical (us_prophet_v3), v2 frozen to
      us_prophet_v2_shadow, as-of-night presence+variance floors, board comparison.
      LIVE-ACCEPTED 2026-08-16: the first post-merge nightly (run 31913143619) published
      a canonical v3 board over 71 rows passing all 14 acceptance items — read from the
      Pages deployment, because that run's engine job failed to PUSH (see landmines).
      Order comparison re-run on the new pool. Receipts:
      agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-16-ACCEPTANCE.md"
    status: done
  - id: w3
    depends_on: [w2b]
    title: "PR-3 — forward race instrumentation, RE-CUT 2026-08-15 against the live
      prophet_shadow lane rather than a replayed G0 (the second scorer is deleted, not
      deferred — production stamps the champion side nightly). Three lanes: forward race
      (accrue now, read later, pre-registered, no promotion arm), family discrimination
      via LOFO, coverage drift. Contract:
      research/prophet_fusion/W3_SHADOW_RACE_RECUT.md"
    status: todo
  - id: w4
    depends_on: [w3]
    title: "PR-4 — C3 date-grouped ranker (depth-gated)"
    status: todo
  - id: w5
    depends_on: [w4]
    title: "PR-5 — C4 router on Stock Identity interfaces (estimability-gated)"
    status: todo
  - id: w6
    depends_on: [w5]
    title: "PR-6 — C5 multi-head + utility study + explanation-contract prototype"
    status: todo
  - id: w7
    depends_on: [w6]
    title: "PR-7 — promotion prereg + DNR amendments + operator/CEO adjudication for
      the rungs ABOVE C1 (C1's adoption was taken by the 2026-08-15 override)"
    status: todo
next_action: >
  w2b DONE — the Chairman override shipped: C1 is the canonical US ranker as
  `us_prophet_v3` (engine/us_prophet_fusion.py, byte-parity-pinned against the raced
  build_c1), the exact v2 scorer is frozen into `us_prophet_v2_shadow` (byte-parity
  pinned against 69 published scores), the as-of-night presence+variance floors #5700
  left unimplemented are in production, and
  research/prophet_fusion/FUSION_BOARD_COMPARISON.md is the operator acceptance surface.
  LIVE ACCEPTANCE CLOSED 2026-08-16 (handoff
  PROPHET-CONDITIONAL-FUSION-2026-08-16-ACCEPTANCE.md): run 31913143619 published a
  canonical `us_prophet_v3` board over 71 rows — 14 of 14 acceptance items PASS, order
  comparison re-run on the new pool. Read from the PAGES DEPLOYMENT: that run's engine
  job failed to push, so main still carries the pre-override v2 artifact and the ledger
  day was lost (infrastructure, #5742 — not fusion). Both CEO adjudications recorded
  (DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW, DEC:FUSION-FAMILY-NEAR-CONSTANCY-IS-A-
  REGISTRY-QUESTION) and w3 re-cut (research/prophet_fusion/W3_SHADOW_RACE_RECUT.md).
  NEXT: w3 Lane A — build the forward-race accrual and PRE-REGISTER before any read; it
  has no promotion arm and cannot "win". Lane B — lofo_displacement(), already
  computable via aggregate(family_keys=...). Lane C — the OPEN question: LOFO reproduced
  the same family ordering on the live pool (F1 6.28 > F2 5.66 > F5 2.54 >> F4 0.62 >
  F8 0.11), but that pool overlaps the previous one 92% at the SAME as_of, so honest-N
  is ONE session and whether F4/F8 near-constancy persists is unanswered. Note the
  method finding: tie-share MISRANKS ordering contribution (F1 sits at 48% ties vs F2's
  3% yet moves the order most), so the published separation table is a proxy, not the
  measure. STILL OPEN from w1: the §13.0 live closure (first post-#5604 nightly with a
  fresh curated stamp).
---

## Context

CEO ruling 2026-08-14: the blanket zero-score-authority doctrine in
`engine/us_board_rank.py` is superseded by "unvalidated at birth, earned conditional
authority". The deployed `us_prophet_v2` stays champion until a challenger clears the
frozen promotion gate. This workstream owns cross-family conditional fusion and the US
board meta-ranking arena — the consumer role both sibling programs' contracts point at
(#5578 reserves F1_FUSION; #5583 §12.4 defers "any Prophet-consuming routing influence"
to exactly this program's gate).

## Scope boundary

Consumes: Live Entry Radar entry events (entry experts + Entry head outcomes), Stock
Identity fingerprints/epochs/fit interfaces (router substrate), the US context vector
(sensory spine), the grades stores (rulers). Never duplicates: entry detection, identity
stacks, hub logic, any producer engine.

**The live rank path is C1 as of 2026-08-15** (`us_prophet_v3`). This line previously
read "Live rank path untouched until w7's adjudication" — superseded by the Chairman
override, preserved here as record. Forward arena work (w3-w7) continues as MEASUREMENT
and is no longer the production blocker for C1; `us_prophet_v2_shadow` supplies the
champion side of that race prospectively from the first night this ships.

Sibling dependencies: `WS:LIVE-ENTRY-RADAR` (#5578) and `WS:STOCK-IDENTITY` (#5583) —
both armed/unmerged as of 2026-08-14, so their records are not yet joinable here; add
them to `depends_on:` once their PR-0s merge. w5 is additionally contingent on Stock
Identity's Q1 blind-arm outcome (masterplan §11.2). Future stores this program will
create at PR-1+ (not yet in-repo, so not in `owns_paths:` yet):
`research/prophet_fusion/`, `data/us_prophet_rank/shadow/`.

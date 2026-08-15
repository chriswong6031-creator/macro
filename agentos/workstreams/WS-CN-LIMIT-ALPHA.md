---
key: CN-LIMIT-ALPHA
title: China limit-up alpha research
objective: >
  Establish whether mainland limit-up mechanics carry tradeable, gauntlet-survivable
  signal. Done = a promotion-grade verdict, or a recorded kill.
status: active
program: china-system
repos: [macro]
owner: chairman
class: research
blast_radius: reversible
owns_paths:
  - research/cn_prophet_audit/
  - research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md
ambiguity: open
waves:
  - id: W-P0
    title: Washout-onset charter + first lawful measurement (#5364)
    status: done
  - id: P-A1
    title: Descriptive Prophet-panel read (#5438, merged 2026-08-12)
    status: done
  - id: P-B
    title: Winners-only case decomposition, no comparison arm (#5521, merged 2026-08-14)
    status: done
  - id: P-B2
    title: Matched precursor discrimination (the preregistered comparison arm)
    status: done
    next_action: >-
      SHIPPED (PR #5615): prereg frozen before outcomes; 17/17 checks + probes;
      byte-identical runs. Verdict = NO DISCRIMINATOR at the preregistered bar:
      11 of 31 gated cells cleared every gate but the placebo calibration failed
      3/4 families — a calibration-governed null, mechanism = persistent-state
      placebo reproducibility (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT);
      MA200/QB/VZ placebo-clean with strong holdout-consistent structure;
      nothing rescued, frozen consequence applied unchanged. Do not rerun.
      Do not move its gates. Reopen path is P-B3, not a P-B2 rewrite.
  - id: P-B2-ACCRUAL
    title: Prospective PIT accrual for remaining class-C China Intelligence feeds
    status: done
    next_action: >-
      SHIPPED: separate keep-first hist stores for broker 金股, per-name margin,
      block trades, buybacks. report_rc already fixed by #5614 (not redone).
      Display snapshots unchanged. Zero scoring/Prophet authority.
      DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE. Evidence-start = first live
      asia-close refresh after merge (floor 2026-08-15); hist files do not
      exist until that run.
  - id: P-B3
    title: Persistence-robust certification (prereg freeze)
    status: in_progress
    depends_on: [P-B2]
    next_action: >-
      PREREG FROZEN (PR #5729, freeze-only):
      research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md
      (DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE). A = primary within-name
      transition contrast; B = corroborative persistence-preserving null.
      Scope = 20 cells (DD20/DD35/MA200/QB/VZ × main/chinext20 × H10/H5).
      P-B2 verdict is not rewritten.       Independent adversarial review
      posted 2026-08-15: FREEZE AMEND
      (research/cn_prophet_audit/PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md).
      A1–A8 are now in the prereg as numbered pre-outcome amendments
      (§16). Cheap re-review next. Do not run the certification until
      that re-review accepts the amended text. Do not auto-roll into
      the run or into P-D.
  - id: P-A2
    title: Prophet-panel inference battery
    status: todo
    depends_on: [P-A1]
    next_action: >-
      Accrual-gated by its own preregistration: >=120 distinct sessions AND >=2
      own_market_regime segments per stream before any inference row (earliest ~2027-02
      via v3). Partial peeks forbidden.
  - id: P-C
    title: Intraday / chip / auction footprints
    status: todo
    next_action: >-
      Blocked on lawful data depth: minute-bar backfill + chips (cyq) accrual + the
      full-A TuShare spine authority decision. Charter only after its gates open.
  - id: P-D
    title: Conjunction stacking + scorer preregistration
    status: todo
    next_action: >-
      Last, by design. Requires a pre-registered ablation arena over Prophet incumbent
      + surviving families; every family must show INCREMENTAL information over Prophet
      and over the structural carrier AND name propensity. P-B3 TIMING-stamped
      cells are eligible timing-family inputs; occupancy-stamped cells are
      named occupancy covariates only; a CARRIER_SERIES cell is not
      incremental to the washout carrier. A P-B3 NULL is not re-shopped.
      Gauntlet at promotion; forward verification only via the
      exact-plane ledger chain.
landmines:
  - >-
    The STOP-SHIP (operator, 2026-08-10; DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT) covers
    the PRE-CHARTER research waves the program called W1-W3. They are NOT waves of this
    record — this record starts at W-P0 (charter + P0 scope), and no wave here carries
    those ids. That is deliberate: the ids are unresolvable inside this store on
    purpose, because the results behind them must never be cited as evidence, including
    in passing. If you found this landmine while hunting for a wave called W1, stop
    hunting — there is nothing here to read.
  - >-
    P-B is WINNERS-ONLY anatomy: its presence/order/lead numbers carry no comparison
    arm and must never be quoted as selection skill or conditional probability. The
    preregistered comparison arm is P-B2. P-B3 certifies what P-B2 left unresolved;
    it does not rewrite P-B2.
  - >-
    Long-horizon feature shifting (P-B2 §6.3, S in {250, 500, 1000}) is not a
    valid certification null for persistent states
    (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT). P-B3's corroborative null
    is a duration/prevalence-preserving within-split spell permutation.
do_not_redo:
  - >-
    Do not restore, re-grade, or cite any adjusted-plane W1-W3 artifact, ledger, model
    or picks page (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT). The reopen path is the
    exact-plane chain in research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md
    §5 — full-A spine backfill, eligibility overlay, F3 exact re-measurement, fresh
    preregistration — and nothing short of it.
  - >-
    Do not build a per-ticker best-expert/outcome-audition selector in this workstream
    (DNR:KILL-OUTCOME-AUDITION; Stock Identity owns per-security routing; Live Entry
    Radar owns the entry-event store).
  - >-
    Do not import the RAW China Intelligence Hub composite (china_intel_hub
    opportunity_score / conviction) or any Hub board-derived term (board_row direction,
    board label edge, board-absent bonus, board's leading-vs-lagging gap contribution)
    into a Prophet-facing construction — those carry the board's own output back into
    itself. AMENDED 2026-08-15 (operator, "Handoff B"): the rule is PROVENANCE, not the
    word "composite". Any displayed CN Prophet score/rank must trace to
    engine/china_board_rank.py; that scorer may consume registered board-INDEPENDENT
    evidence, including the board-independent intelligence-interest composite
    engine/china_intel_interest.py (intel_interest_score), which is live in
    cn_prophet_v4 as ORDERING authority. Nothing under research/cn_prophet_audit/ may
    own Prophet rank. Any FURTHER authority (gate/size/score) still re-earns its value
    under its own preregistration.
  - >-
    Do not reconstruct evidence history from current snapshots (broker.parquet,
    margin.parquet, china_block_trades/detail.parquet, china_buyback/buyback.parquet).
    Studies read the hist/events stores. Do not stamp historical broker months as
    PIT-known (DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE). Do not redo the
    report_rc overwrite fix (#5614).
  - >-
    Do not reuse P-B2's long-horizon feature-shift placebo as a certification null
    (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT). Do not add a P-B3 runner or
    result table to the freeze PR. Do not auto-roll from the freeze into the run.
decisions: ["DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE", "DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE"]
discoveries: ["DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT"]
artifacts:
  - research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md
  - research/cn_prophet_audit/PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md
  - research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md
next_action: >-
  P-B3 A1–A8 are in the prereg (PR #5729). Next: cheap re-review of
  the amended text
  (research/cn_prophet_audit/PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md
  tick list). Do not run the certification until that re-review
  accepts. After acceptance, a later session runs P-B3. Parallel:
  (1) P-B2-ACCRUAL shipped on main (#5730) — record live
  min(first_seen) after the first asia-close write; do not seed hist
  from snapshots; (2) P-C when its data gates
  open; (3) full-A exact-plane re-measurement; (4) P-D last, and only
  as an ablation arena that may take P-B3 TIMING-stamped cells as
  timing-family input and occupancy-stamped cells as named covariates
  (CARRIER_SERIES is not incremental to the washout carrier).
  No production scoring change from P-B2 or from this freeze.
---

## Context

The 2026-08-10 STOP-SHIP ruling stands in full force as a citation/restoration ban on
the withdrawn adjusted-plane artifacts (see landmines) — but the RESEARCH workstream is
ACTIVE on lawful substrate, not blocked: the v2 program home
(`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md`) re-homed the thesis on the
pattern-tier washout-onset lane, and W-P0 (#5364), P-A1 (#5438), P-B (#5521) and
P-B2 (#5615) have all merged under it. P-B2's verdict — NO DISCRIMINATOR at the
preregistered bar — closes that construction only. P-B3 is the persistence-robust
reopen of the unresolved DD / MA200 / QB / VZ structure; its prereg is frozen
before any P-B3 instrument or outcome. P-B2-ACCRUAL (#5730) shipped the
prospective keep-first PIT hist stores; that wave is done and is not a P-B3 input.

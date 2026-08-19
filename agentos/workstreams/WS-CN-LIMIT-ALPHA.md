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
  - research/cn_limit/
ambiguity: scoped
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
    title: Persistence-robust certification
    status: done
    depends_on: [P-B2]
    next_action: >-
      SHIPPED (PR #5729): prereg sha256 prefix 75fb38e1e6b5aefe; freeze
      commit 6419ca5ed5744d562b7c22093b52065502f802f3; run head
      b473cad20da08a274a3c7914b2edec1827433783; receipts
      PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.{md,json}. Verify 19/19
      checks + 19/19 probes. Verdict = NULL=12, UNINFORMATIVE=8; zero
      CERTIFIED TIMING; zero CERTIFIED OCCUPANCY
      (DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE). P-B2 remains NO
      DISCRIMINATOR AT THE PREREGISTERED BAR. P-D is not opened and
      has no input from this construction. Do not re-run. Do not shop
      gates, floors, strata, cells, or headlines.
  - id: P-A2
    title: Prophet-panel inference battery
    status: todo
    depends_on: [P-A1]
    next_action: >-
      Accrual-gated by its own preregistration: >=120 distinct sessions AND >=2
      own_market_regime segments per stream before any inference row (earliest ~2027-02
      via v3). Partial peeks forbidden. R6 note (2026-08-19): runs under the R6
      freeze's authority precedence; a standout-panel research battery, never a
      substitute for the exact-plane R4 battery (wave M2-R4-BATTERY).
  - id: P-C
    title: Intraday / chip / auction footprints
    status: todo
    next_action: >-
      Reconciled under R6 (2026-08-19): intraday families
      (AUCTION_DEMAND_QUALITY, SEAL_CONTINUATION_STATE) live in the D-INTRADAY
      dormant branch of the R6 freeze §13.3 and unlock only on licensed
      auction/minute/order data plus a fresh P-C charter of its own era, behind
      DEP-EXACT. Seal anatomy never predicts the same first-board target
      (continuation/access only). Do not charter from this row alone.
  - id: P-D
    title: Conjunction stacking + scorer preregistration
    status: dropped
    next_action: >-
      SUPERSEDED 2026-08-19 by the R6 measurement architecture: conjunction and
      stacking evaluation happens only inside M2-R4-BATTERY → I1C-G6 under the
      frozen R4 preregistration (DEC:CNLI-MEASUREMENT-BEFORE-ORDERING,
      DEC:CNLI-NO-OUTCOME-AUDITION). No separate P-D scorer prereg may be
      chartered. P-B3 gave it no input; R6 closes the row.
  - id: R6-0
    title: Durable R6 final-freeze landing (records only)
    status: done
    next_action: >-
      SHIPPED with this record's PR: R6 canonical package landed byte-faithfully
      under research/cn_limit/ (architecture freeze, machine registry, Fable
      command packet, Grok bounded commissions, executive handoff index,
      artifact manifest — SHA-256s match the manifest); 13 DEC:CNLI-* rulings
      and 3 discoveries minted. Per the R6 proof matrix the required proof is
      merged-records discoverability on origin/main; no runtime diff shipped,
      no runtime proof claimed. R1-R5 source artifacts were not delivered as
      bytes to the landing session; they remain pinned by SHA-256 in the freeze
      Appendix C and the manifest.
  - id: P0-ST
    title: 2026 main-board risk-warning rule parity and replay (program P0)
    status: todo
    depends_on: [R6-0]
    next_action: >-
      Commission as its own session after R6-0 merges: effective-dated
      main-board risk-warning band ±5%→±10% from 2026-07-06 in
      config/cn_limit_rules.yml + engine/china_microstructure.py, with
      official-source effective-date receipt, boundary tests both venues,
      affected-row census, bounded replay, correction receipts, and a real
      asia-close proof (packet §P0-ST;
      DSC:CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06). Affected rows stay
      quarantined until then.
  - id: DEP-CAI
    title: China Alpha Intelligence PR-0B telemetry + rights/identity closure
    status: todo
    depends_on: [R6-0]
    next_action: >-
      State moved after the R6 packet was prepared: the architecture chain
      (#5953/#5933/#5943/#5955) all MERGED 2026-08-19 16:05-18:13Z, so the
      open-PR half is resolved. Remaining gate = execute PR-0B from
      research/china_alpha_intelligence/commissions/PR-0B_v4_telemetry.md
      inside WS:CHINA-ALPHA-INTELLIGENCE and prove full intel_ anatomy on real
      asia-close candidate rows (DSC:CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE).
      CN-Limit candidate-plane work stays blocked until PROVEN_LIVE, not merely
      merged.
  - id: DEP-EXACT
    title: Exact-plane authorization, live canary, range campaign, completeness
    status: todo
    depends_on: [R6-0]
    next_action: >-
      BLOCKED_RIGHTS_AND_AUTHORITY: close written authorization/trust-root
      governance, run licensed exact-schema canaries, promote the range
      campaign only through reviewed gates, produce the sanitized completeness
      manifest (packet §DEP-EXACT). No self-authored authorization; no gate
      constant edits; the fail-closed spine stays fail-closed until the
      operator-level authority decision recorded in this workstream's 08-13
      state is taken.
  - id: DEP-ID-ELIG
    title: Canonical China identity, PIT membership, eligibility overlay
    status: todo
    depends_on: [DEP-EXACT, DEP-CAI]
    next_action: >-
      Point-in-time eligible security-session population + time-valid
      sector/theme edges via Data OS/GMI/eligibility owners; no CN-Limit
      identity or membership plane; no ticker-only keys; no current-membership
      backfill (packet §DEP-ID-ELIG).
  - id: I1A-T1
    title: "First candidate-anatomy vertical: CNLI.TRANS.DOWN_IMPACT_ASYMMETRY"
    status: todo
    depends_on: [P0-ST, DEP-CAI, DEP-ID-ELIG]
    next_action: >-
      One frozen deterministic feature projected prospectively onto canonical
      candidate rows + real audit consumer; no probability/rank/gate fields
      (packet §I1A-T1; freeze Appendix A contract).
  - id: I1A-T2
    title: Bad-day resilience vertical
    status: todo
    depends_on: [I1A-T1]
  - id: I1A-T3
    title: Constructive-volume asymmetry vertical
    status: todo
    depends_on: [I1A-T1]
  - id: I1A-T4
    title: Reclaim-and-hold quality vertical
    status: todo
    depends_on: [I1A-T1]
  - id: I1B-MEASURE
    title: Exact target + first immutable prediction/grade sidecar vertical
    status: todo
    depends_on: [DEP-ID-ELIG, I1A-T1]
    next_action: >-
      Referential sidecar china_prophet_rank.cn_limit_research.v1 with one real
      feature + R4 H10 exact target + access dispositions; never an empty
      generic foundation (packet §I1B-MEASURE).
  - id: M2-R4-BATTERY
    title: Frozen historical/rolling-origin R4 active-family battery
    status: todo
    depends_on: [I1B-MEASURE, I1A-T2, I1A-T3, I1A-T4]
    next_action: >-
      Freeze formulas/populations/baselines/controls/nulls/folds/metrics
      before opening exact outcomes; run once; advance/kill/accrue verdicts.
      A NULL or kill verdict is complete (packet §M2-R4-BATTERY).
  - id: I1C-G6
    title: Prospective G6 measurement shadow
    status: todo
    depends_on: [M2-R4-BATTERY]
    next_action: >-
      One preregistered challenger accrued prospectively to the G6 floors
      (>=120 candidate sessions, >=2 regimes, >=60 exact first-board events,
      no retuning). Highest verdict = ELIGIBLE_FOR_SHADOW_IMPLEMENTATION_COMMISSION,
      which is not live authority.
  - id: I2A-ORDER
    title: Fixed-candidate off-path ordering shadow
    status: todo
    depends_on: [I1C-G6]
    next_action: >-
      Coverage-atomic challenger order on frozen U3 with same-rule/same-cap
      shelf replay; production bytes must remain identical
      (DEC:CNLI-COVERAGE-ATOMIC-CHALLENGER, DEC:CNLI-ERA-IS-EFFECTIVE-AUTHORITY).
  - id: A5-DECISION
    title: Potential bounded live ordering decision (Sol/Chairman)
    status: todo
    depends_on: [I2A-ORDER]
    next_action: >-
      NOT_AUTHORIZED. A decision record, not a build wave; R6 grants no A5
      authority and no automatic promotion
      (DEC:CNLI-AUTHORITY-DOES-NOT-CASCADE).
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
  - >-
    Main-board risk-warning event labels from 2026-07-06 onward are rule-stale
    and QUARANTINED until P0-ST closes: the repo still applies ±5% where the
    official 2026 rules require ±10%
    (DSC:CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06). Note
    engine/china_microstructure.py's ST_STORE_COVERAGE_DATE is coincidentally
    also 2026-07-06 — that constant is store coverage, not the missing rule-era
    switch.
  - >-
    The R6 packet statuses (DORMANT_*/BLOCKED_*) are encoded here as todo +
    gates in next_action because the wave schema has no blocked status. The
    packet and freeze under research/cn_limit/ are the authority on gate
    wording; this record is the authority on current state.
do_not_redo:
  - >-
    Do not restore, re-grade, or cite any adjusted-plane W1-W3 artifact, ledger, model
    or picks page (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT). The reopen path is the
    exact-plane chain in research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md
    §5 — full-A spine backfill, eligibility overlay, F3 exact re-measurement, fresh
    preregistration — and nothing short of it. R6 restates this as
    DEC:CNLI-EXACT-CENT-PRIMARY.
  - >-
    Do not build a per-ticker best-expert/outcome-audition selector in this workstream
    (DNR:KILL-OUTCOME-AUDITION; Stock Identity owns per-security routing; Live Entry
    Radar owns the entry-event store). R6 extends this to the challenger lane:
    exactly one preregistered challenger per prospective race
    (DEC:CNLI-NO-OUTCOME-AUDITION).
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
    (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT). Do not re-run P-B3 or shop
    its gates, floors, strata, cells, or headlines
    (DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE). Do not open P-D from this
    construction. Do not flip MA200 to onset or DD to exit after seeing the
    A_B_CONTRADICT rows.
  - >-
    Do not create a second candidate population, grader, identity plane,
    company-event store, intelligence composite, or lifecycle for CN-Limit
    (DEC:CNLI-ONE-CANONICAL-PROPHET-CHAIN). Do not edit the candidate writer
    for CN-Limit before PR-0B is PROVEN_LIVE
    (DSC:CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE). Do not use the Prophet
    Operator Lab as a CN-Limit store, grader, or ontology
    (DEC:CNLI-PROPHET-LAB-FENCED-ADJACENCY).
  - >-
    Do not implement any live rank, score, gate, size, or public probability
    from R6 records — authority does not cascade
    (DEC:CNLI-AUTHORITY-DOES-NOT-CASCADE); A5 is a Sol/Chairman decision wave,
    never a build default. Do not label tape features with actor/intent claims
    (DEC:CNLI-ACTOR-NEUTRAL-TAPE-LANGUAGE).
decisions:
  - "DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE"
  - "DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE"
  - "DEC:CNLI-HAZARD-NOT-MAGIC-INDICATOR"
  - "DEC:CNLI-CARRIER-CONTEXT-NOT-SELECTOR"
  - "DEC:CNLI-SEQUENCE-OVER-COUNT"
  - "DEC:CNLI-ACTOR-NEUTRAL-TAPE-LANGUAGE"
  - "DEC:CNLI-OUTCOME-VECTOR"
  - "DEC:CNLI-EXACT-CENT-PRIMARY"
  - "DEC:CNLI-ONE-CANONICAL-PROPHET-CHAIN"
  - "DEC:CNLI-MEASUREMENT-BEFORE-ORDERING"
  - "DEC:CNLI-COVERAGE-ATOMIC-CHALLENGER"
  - "DEC:CNLI-ERA-IS-EFFECTIVE-AUTHORITY"
  - "DEC:CNLI-NO-OUTCOME-AUDITION"
  - "DEC:CNLI-AUTHORITY-DOES-NOT-CASCADE"
  - "DEC:CNLI-PROPHET-LAB-FENCED-ADJACENCY"
discoveries:
  - "DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT"
  - "DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE"
  - "DSC:CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06"
  - "DSC:PROPHET-LAB-OWNS-NO-CN-LIMIT-PATHS"
  - "DSC:CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE"
artifacts:
  - research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md
  - research/cn_prophet_audit/PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md
  - research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.md
  - research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.json
  - research/cn_prophet_audit/pb3_persistence_robust_cert.py
  - research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md
  - research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_REGISTRY_V1_2026-08-19.json
  - research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_GROK_BOUNDED_COMMISSIONS_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_EXECUTIVE_HANDOFF_INDEX_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_ARTIFACT_MANIFEST_2026-08-19.json
next_action: >-
  R6-0 lands with this PR (records only). Then commission P0-ST, DEP-CAI, and
  DEP-EXACT as separate sessions per
  research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md —
  P0-ST first (program P0). No CN-Limit runtime feature wave starts before its
  named dependency gates close; no live rank, score, gate, size, or public
  probability is authorized by any R6 record.
---

## Context

The 2026-08-10 STOP-SHIP ruling stands in full force as a citation/restoration ban on
the withdrawn adjusted-plane artifacts (see landmines) — but the RESEARCH workstream is
ACTIVE on lawful substrate, not blocked: the v2 program home
(`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md`) re-homed the thesis on the
pattern-tier washout-onset lane, and W-P0 (#5364), P-A1 (#5438), P-B (#5521) and
P-B2 (#5615) have all merged under it. P-B2's verdict — NO DISCRIMINATOR at the
preregistered bar — closes that construction only. P-B3 (PR #5729) ran the
persistence-robust reopen and closed it: NULL=12, UNINFORMATIVE=8; no timing
or occupancy input for P-D. P-B2-ACCRUAL (#5730) shipped the prospective
keep-first PIT hist stores; that wave is done and is not a P-B3 input.

**R6 (2026-08-19):** Sol's final research and integration architecture freeze
landed under `research/cn_limit/` — read order and precedence in
`CN_LIMIT_R6_EXECUTIVE_HANDOFF_INDEX_2026-08-19.md`. CN-Limit is now chartered
as a mechanism-aware rerating-hazard system: structural washout is the carrier,
lawful professional/corporate/sector/supply evidence supplies mechanism context,
transition features identify release, Prophet owns actionability, and access is
modeled separately from event probability. The program reuses the canonical
candidate and grade planes, adds prospective anatomy only after China Alpha
PR-0B is proven live, and writes immutable predictions/grades/corrections to a
referential sidecar. No live rank, score, gate, size, or public probability is
authorized. The R6 wave graph above (R6-0 → P0-ST + DEP-* → I1A → I1B → M2 →
I1C → I2A → A5) is the frozen execution plan; the 2026-08-19 handoff records
the landing session's reconciliations, including the post-packet merge of the
China Alpha architecture chain.

---
key: TOP-ANATOMY
title: Top Anatomy — OOT Completion & Winner Health
objective: >
  Finish Top Anatomy as an evidence-grounded winner-maturation capability: restore the existing
  Winner Health consumer on the current canonical Massive Stock Day store, preserve W2/Phase-1/
  AM-v2 same-tape verdicts, execute the only remaining untouched out-of-time question when its
  preregistered maturity gates naturally clear, adjudicate tier-local libraries/provenance, and
  leave a real production product plus durable learning loop with zero unauthorized action authority.
status: active
program: top-anatomy
repos: [macro]
owner: coo-fable
class: research
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - engine/top_anatomy.py
  - engine/top_maturation.py
  - scripts/research_top_anatomy_
  - scripts/build_top_maturation.py
  - scripts/build_winner_health_page.py
  - scripts/export_top_anatomy_library.py
  - scripts/research_top_anatomy_oot_receipt.py
  - research/top_anatomy/
  - reports/top-anatomy-
  - data/top_anatomy/
  - data/top_maturation/
  - templates/winner_health.html.j2
  - site/winner_health.html
decisions:
  - DEC:TOPA-OOT-COMPLETION-ARCHITECTURE
waves:
  - id: R0
    title: Current-store read restoration + roster/exemplar census + OOT prereg/maturity receipt
    status: done
    next_action: >
      DONE 2026-09-02, executed as successor child topa-r0b-winner-health-restore-20260901-coo-001
      after the original START-bound Claude5 child (topa-r0-refresh-winner-health-20260828-sol-001,
      native session af9f1807, effect=NONE) lost its runtime unrecoverably; the sticky-binding vs
      direct-override conflict was adjudicated by the live Chairman on 2026-09-02 (direct session
      edge: holds void, continue autonomously; receipted on the carrier at ts 1788342873.906109).
      Delivered on Macro PR #6723, squash-merged as 708e87866005 on all-green concluded checks plus
      a SUCCESS main-descendant ci.yml baseline (run 33588307186): the engine-band ordering fix
      (guarded massive_stock_day restore hoisted above any cluster launch in
      scripts/ci/daily_engine_regional_desk_builders.sh, RED->GREEN pinned by
      tests/test_daily_engine_massive_restore_order.py), the frozen OOT prereg
      (research/top_anatomy/TOPA_OOT_PREREG.md, post-adversarial-review, seed 20260901), the
      roster/exemplar census (research/top_anatomy/TOPA_R0B_ROSTER_CENSUS_2026-09-01.md; local
      vertical proof: null_state=false, 223/203/387 on board, 2.3MB real page), the deterministic
      receipt emitter (scripts/research_top_anatomy_oot_receipt.py, 28 tests), and the first
      committed receipt (data/research/top_anatomy_oot_receipt_2026-09-02.json =
      OOT_ACCRUING_NO_VERDICT, 0/18 cells eligible). Production evidence: the first scheduled
      daily.yml run containing the merge (Sep-2 evening cron), reported on the carrier as evidence.
  - id: R1
    title: Minimal prospective OOT accrual rail, only if existing daily evidence is insufficient
    status: dropped
    depends_on: [R0]
    next_action: >
      RULED NOT NEEDED 2026-09-02 (COO ruling under the Chairman continuation edge): the merged
      deterministic receipt emitter is itself the answerability instrument — any session can emit a
      current maturity receipt on demand, the earliest possible cell eligibility is ~2027-07 (the
      >=12 distinct-peak-month span binds, prereg §4), and matcher/era-block activation is a
      declared prereg-§8 event for the wave that approaches the floors. A daily-lane change before
      then would be make-work; nothing about answerability is lost by its absence.
  - id: R2
    title: Frozen out-of-time statistical adjudication
    status: todo
    depends_on: [R0]
    next_action: >
      Execute only when a maturity receipt prints final_verdict_eligible true for a registered cell
      under the frozen prereg's single-look rule (research/top_anatomy/TOPA_OOT_PREREG.md §5 —
      first eligible receipt pins the pool; §6 matrix computed once per cell). Earliest possible
      ~2027-07. Activation prerequisites (matcher + era blocks in the receipt path) are harness
      work recorded append-only in prereg §8 before any confirmatory number. If floors do not
      clear, remain OOT_ACCRUING_NO_VERDICT rather than changing the ruler.
  - id: R3
    title: Per-tier library and research-provenance adjudication
    status: todo
    depends_on: [R2]
    next_action: >
      Sol/Chairman rule retain/version/downgrade per primary/R63/ATRZ tier without cross-tier
      thresholds or contaminating untouched validation evidence.
  - id: R4
    title: Winner Health final research-product integration
    status: todo
    depends_on: [R3]
    next_action: >
      The product-restoration half shipped in R0 (board live on the current canonical store with
      tier-local analog memory, provenance and honest freshness). The research-integration half —
      per-leg evidence classes and OOT-informed provenance copy — waits on R2/R3 by design.
  - id: R5
    title: Existing Brain/Neural Web context adoption only if independently useful
    status: todo
    depends_on: [R4]
    next_action: >
      Skip unless an existing context consumer gains a concrete user/machine capability from the
      same display/context artifact; never create a vanity score/ranker consumer.
  - id: R6
    title: Final production/research proof and durable closeout
    status: todo
    depends_on: [R4]
    next_action: >
      Final acceptance only after real canonical-store->artifact->Winner Health browser proof, the
      final research/maturity verdict (or the truthful natural-evidence wait explicitly recorded),
      authority-fence review and watcher/session teardown.
landmines:
  - "W2, Phase-1 and AM-v2 already ran; do not rerun them as new research merely because the store is fresher."
  - "AM-v2 closed the F1/F3/B3 cluster claim on the 2026-07-02 tape at the registered grain; only untouched OOT evidence may reopen it."
  - "B2 survives the clean ATRZ match at reduced magnitude; do not overstate it as a probability, top call, exit rule or universal cross-tier effect."
  - "The OOT prereg is FROZEN (research/top_anatomy/TOPA_OOT_PREREG.md, freeze commit 0f35a5e4): registered quantities are immutable, floors tighten-only, single-look rule per cell, pre-gate computation ban. OOT_ACCRUING_NO_VERDICT is the exact state until a cell's receipt prints eligible (~2027-07 earliest) and no authority may upgrade it."
  - "The inherited outcome ruler can require up to 250 sessions and the inferential floors include distinct peak-month/matched-episode protection. Several weeks of new tape cannot support a fabricated final verdict."
  - "Winner Health's dark-board root cause is FIXED (merge 708e87866005): the engine band restores massive_stock_day before any cluster launches. The proven receipt (run 33232322255/job 99066153702: panel 0 files at 12:10Z, 21,452 restored 12:56Z) stays the canonical history; the later price_pressure restore leg remains untouched as backstop."
  - "Massive Stock Day is R2-canonical and separately owned. A Top Anatomy read defect may be fixed; a publication/atomicity owner defect must be returned to WS:MASSIVE-STOCK-DAY-R2-COHERENCE."
  - "The primary/R63/ATRZ libraries are intentionally tier-local; never borrow thresholds across tiers."
  - "Current canonical Worker Presence/Turn-Watcher is not yet PROVEN_LIVE; session watchers are attention-only, cannot fire while their session is busy, and are never a substitute for a fresh carrier read before an irreversible act."
do_not_redo:
  - "Do not create another market-history/OHLCV store."
  - "Do not rebuild Winner Health as a separate dashboard; fix/extend the existing product."
  - "Do not merge Top Anatomy into Prophet graded-board population (DNR:KILL-PROPHET-POP-MERGE)."
  - "Do not create directional short/sell/trim/exit authority (DNR:KILL-DIRECTIONAL-SHORTING)."
  - "Do not shorten or change a registered outcome horizon to produce a verdict (DNR:KILL-OFFHORIZON-VERDICTS)."
  - "Do not turn descriptive legs into a fused score/composite or create a second ranker/gauntlet plane."
  - "Do not absorb Massive Stock Day publisher/coherence work into this workstream."
  - "Do not attempt to restore or rebind the lost R0 Claude5 runtime (af9f1807) — its worktree is gone, resume fails cwd_not_found, and the child is closed under the 2026-09-02 Chairman adjudication."
artifacts:
  - research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md
  - reports/top-anatomy-w2.md
  - reports/top-anatomy-phase1.md
  - reports/top-anatomy-amv2.md
  - research/top_anatomy/TOPA_OOT_COMPLETION_MASTERPLAN_2026-08-28.md
  - research/top_anatomy/TOPA_OOT_PREREG.md
  - research/top_anatomy/TOPA_R0B_ROSTER_CENSUS_2026-09-01.md
  - data/research/top_anatomy_oot_receipt_2026-09-02.json
  - data/top_maturation/latest.json
next_action: >
  Observe the first scheduled daily.yml run containing merge 708e87866005 and report its production
  evidence on the exact carrier (pre-band restore ordering in the engine log, non-zero panel,
  truthful non-null winner_health.v2, live page) — evidence, with acceptance resting on
  Chairman/Sol per the 2026-09-02 carrier record. Then park the natural-time OOT wait per
  masterplan §10: no polling sessions; the frozen prereg, the receipt emitter and committed
  receipts own the wait; R2 activates only through a final_verdict_eligible receipt under the
  single-look rule (~2027-07 earliest). R4's research-integration half follows R2/R3.
---

## Program boundary

This workstream does not replace `research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md`; it is the durable
current organizational owner for completing the program after W2, Phase-1 and AM-v2. Historical
research chronology remains in the original masterplan and reports. This record owns current wave
state, exact next action, collision boundaries and final completion accountability.

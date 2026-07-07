# Research Factory Batch A — Paper Promotion and Duplicate Kills

**Source:** PR #1629 (W6 of the RF program). Primary doc: `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` (§0 status log). **Status:** canonical (RUL-SUCC-8).

## What was asked

After the Research Factory (W0–W7) shipped its orchestration and audit layer, Batch A presented 8 Oracle compounds for human-gate review. Five had been adopted from the promotion queue; five had been challenged by Opus reviewers (advisory-only, outcome-blind per RF-7). Fable was asked to rule on each candidate's fate: promote to `paper`, keep `screened`, `reject`, or `defer`.

## What was decided (the holding)

- **A15_WASHOUT_OPP_OUT_2NODE → paper** (RF ruling, Batch A). Half-life prior 250 trading days (domain default per RF-9). Two challenger majors converted to paper tripwires: beta-attribution vs a size-matched null required; cluster-adjusted SE required before `promote_eligible`. The honest headline is the +1.14% increment, not the WR=0.737 surface number.
- **A9 → rejected** (kill_class=duplicate). Basin representative already tracked in the Oracle registry; the factory dedup rule 1 (RF-14) triggered; n_at_kill recorded; steelman in challenge file; respin possible under RF-15 with fresh registration.
- **A16 → rejected** (kill_class=duplicate). Directionality-stripped variant of a tracked compound; no independent mechanism.
- **C6 → rejected** (kill_class=duplicate). NULL-pooled endpoint re-run; adds zero information beyond the existing screen.
- **TERM_PREMIUM_02 → rejected** (kill_class=falsified). Failed its own pre-registered floor; the A4–A26+TLT-leg family's declared budget counted this as a trial; no respin without a material column-set change declaring a new `rf.*` family (RF-6/RF-15).
- A17, A24, A46: remain `screened`, queued for a future batch.
- Challenger role throughout: advisory-only; Opus reviewers were outcome-blind; kills were human-authored (Fable), not LLM-authored (RF-7).
- The factory authority ceiling remains A0–A2; `paper` = display-only accrual, explicitly NOT a gauntlet registration or a board signal (RF-1).
- Factory wrote zero new trial-ledger rows and zero domain-registry entries during the challenge phase (RF-12; RF-13 Oracle seam).

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| A15 → paper | RF human-gate transition | **T0** (ROUTINE) | Opus alone, with `packet_ref` (RUL-SUCC-7) |
| A9/A16/C6/TERM_PREMIUM_02 → rejected | RF human-gate kill | **T0** (ROUTINE) | Opus alone, with kill_evidence block (RF-10) |
| A17/A24/A46 → remain screened | No state transition | **T0** (ROUTINE) | No packet required; action is deferral by inaction |
| Challenger advisory verdict | LLM finding only | Advisory (no tier) | Opus reviewer spawned as `agentType='reviewer'`; never decides |

The `packet_ref` requirement on Opus-actor RF human-gate transitions (RUL-SUCC-7) applies: each `paper`/`rejected` transition needs a minimal packet with `actor_ref` and `packet_ref`. Missing either → transition refused by the state machine.

## Lenses that did the work

- **Case law:** RF-14 dedup law caught A9/A16/C6 immediately against the Oracle registry and domain-homed duplicate table. The NW_QUANT_SYNTHESIS §3 duplicate table (embedded as text in the challenger prompt) provided the lookup.
- **Statistics:** Challenger flagged A15's WR=0.737 as the wrong headline — the cluster-adjusted beta-attribution increment (+1.14%) is the honest estimand; RF-10 mde_at_n was computed and recorded. TERM_PREMIUM_02 failed its own pre-registered floor — the statistics lens triggered the kill.
- **Authority:** `paper` state explicitly reconfirmed as display-only accrual, not a gauntlet or authority rung; `promote_eligible` requires a separate program ruling, not a factory output (RF-1/RF-5).
- **Build feasibility:** Advisory-only challenger design verified to be inert to board/rank/size; no factory output touches Article-2 surfaces (RF-11).

## Citable holding

The Research Factory's challenger is advisory-only and outcome-blind; kills at the `paper`/`rejected` human-gate states are human-authored (Fable or Opus with a packet), never LLM-authored; a duplicate kill at n_at_kill is scientific output equal in standing to a promotion, and must be recorded with a steelman and a respin condition.

## Ruling IDs

RF-1, RF-2, RF-5, RF-6, RF-7, RF-9, RF-10, RF-12, RF-13, RF-14, RF-15

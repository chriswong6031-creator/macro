# OTA — Member-Transmission Formal Pre-Registration (P3-style)

**Program:** Oracle Turn Asymmetry. Authored by Fable 2026-07-06. **This registration merges BEFORE any registered statistic is computed** (Oracle constitution §I.3: one registered gauntlet shot; nothing auto-promotes). It confirms-or-retracts the W2 CONDITION-LIFT ([#1509](https://github.com/chriswong6031-creator/macro/pull/1509), descriptive class) under corrected machinery and a temporal split, and pre-binds the forward promotion rule that the W6 Turn Desk ledger will accrue against.

## 1. Question
Does the a15 armed-window condition (sector weekly washout × ≥2 opposite-complex outflow-onset nodes; K=10 sessions) add member-entry quality to production T1–T3 fires — confirmed under machinery that fixes every defect found in W2 review, and with a temporal holdout?

## 2. Population & machinery (frozen)
Identical to `W2_SPEC.md` §1–§2 as amended and countersigned, with the THREE mandated corrections applied (each was verified no-flip or inert in the W2 re-audit; they are corrections, not new choices):
1. **Symmetric placebo:** placebo OUT-arm excludes real armed-window fires (matches the observed contrast exactly).
2. **Cluster-bootstrap CI on the delta itself** (window-level resample, 2,000 draws, 90% CI) reported next to every headline delta.
3. **MDE alpha = 0.05** (not BH_Q) in any power statement.
Join key pre-committed: replay GICS sector string → node via `GICS_TO_NODE` (ratified amendment). Population: verdict-grade PIT fires per the P0 memo v1.1; a15-raw fires ≥ 2022-06-30 (phantom-window law); seed 20260706 for the registered run.

## 3. Registered endpoints (3 reads; BH q=0.10; nothing else may be quoted as a finding)
- **R1 (confirmation):** full-window pooled ΔWR21 (IN − OUT) > symmetric-placebo p95 (500 draws, regime-matched, real windows excluded from placement AND from placebo-OUT).
- **R2 (confirmation):** full-window pooled Δ mean `fwd_ret_21` > symmetric-placebo p95.
- **R3 (temporal holdout — the only genuinely new evidence):** split armed windows by start date at **2024-06-30** (dev ≤, holdout >). Holdout ΔWR21 > 0 **AND** the holdout delta's cluster-bootstrap 90% CI lower bound > 0. Expected holdout size ~13–17 windows — thin; the UNDERPOWERED outcome is pre-bound below, and MDE@80% (alpha 0.05, window-level design effect from the observed ICC) is printed regardless of verdict.

## 4. Pre-bound verdict vocabulary (exhaustive)
- **CONFIRMED — DISPLAY-WITH-EDGE:** R1 ∧ R2 ∧ R3 pass. Ceiling unchanged (display-with-edge is the maximum for this class per constitution §III; "validated" remains unavailable to this study design — modern-track, single regime arc). Consequence: the W6 desk may print the lift WITH this class stamp; shadow-tier bus consumption becomes eligible; the forward rule (§5) becomes the promotion clock.
- **PARTIAL — DISPLAY-WITH-EDGE (holdout-underpowered):** R1 ∧ R2 pass; R3 fails ONLY by CI width (holdout point estimate > 0 but LB ≤ 0). Consequence: W2's descriptive lift keeps its class; desk prints the holdout point + CI honestly; §5 forward rule carries the promotion question.
- **RETRACTED:** R1 or R2 fails under corrected machinery. Consequence: the W2 CONDITION-LIFT verdict is retracted in the masterplan status log; desk base-rate panels are removed; a retraction note lands in `W2_REPORT.md`.
- A negative holdout point estimate with R1 ∧ R2 passing = **PARTIAL-DIVERGENT**: reported verbatim, desk prints the divergence, forward rule becomes decisive. No post-hoc categories.

## 5. Forward promotion rule (pre-registered; the W6 ledger accrues against it)
The W6 Turn Desk ledger (nightly-advanced, keep-first, PIT) records every armed window and its member-fire outcomes from desk go-live. **Re-evaluation event:** when **≥15 new armed windows** (post go-live) have matured at h=21, compute the forward ΔWR21 (same estimator, same symmetric placebo machinery on the accrued period). Promotion request to **confirmer tier** (a Neural Web Article-2/authority event requiring operator sign-off) requires: forward Δ point estimate > 0 AND cluster-aware Wilson/bootstrap LB > 0. Failure → remains display-with-edge; a second consecutive failing re-evaluation → demote to descriptive. Projected first re-evaluation at ~9 windows/year: **mid-to-late 2027**. No peeking between events; the desk may display accruing counts.

## 6. Prohibitions
No per-sector claims (own registration required). No K/killer-feature sweeps inside the registered run (K=10 frozen; the W2 K-sensitivity appendix remains appendix). No new columns, no label changes. The registered run's code diff vs the W2 script must contain ONLY the §2 corrections + the R3 split + seed; the diff is part of the deliverable and is audited against this list.

## 7. Deliverables
`scripts/oracle_member_transmission_w2.py --registered-run` (flagged mode implementing §2 corrections + R3; default mode byte-identical to W2), `research/oracle_asymmetry/W2_FORMAL_RESULTS.md` (all three reads + verdict from §4 vocabulary + MDE + diff audit note), adjudication appended here.

## Amendment log
- (none)

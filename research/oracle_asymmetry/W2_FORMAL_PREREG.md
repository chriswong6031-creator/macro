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

## Counter-sign (Fable, 2026-07-06) — REGISTERED WITH CONDITIONS

Adjudication after a two-lens Opus red-team (house-law + statistics; independent numeric recompute against `W2_arm_node_aggregates.csv` and the harness code). The registration STANDS; the CONFIRMED — DISPLAY-WITH-EDGE verdict on the registered run STANDS; the following conditions are binding corrections and caveats of record:

- **C1 (fdr_family).** §3's "3 reads; BH q=0.10" is corrected to: "2 BH-corrected placebo reads (R1, R2; fdr_family=`ota_w2_member_transmission_confirm`, budget=2) + 1 independent CI-gated out-of-time read (R3; not BH-pooled, no p-value)." The harness BH-corrects only R1/R2 (`bh_correct([pval_wr21, pval_ret21])`, script line ~1489) — that is the intended family.
- **C2 (secondary).** `ep_onset_in` is DEMOTED to appendix-descriptive: not a registered read, no placebo, no inference; it must not be quoted as a finding. Any future `ep_onset_in` claim requires its own registration.
- **C3 (R3 baseline honesty).** R3's holdout OUT arm is the FULL-HISTORY OUT baseline (script lines ~1550-1551), not a holdout-period OUT. "The only genuinely new evidence" is softened to "IN-side out-of-time persistence against a fixed OUT baseline." A holdout-period-matched OUT (or holdout-vs-own-placebo) is REQUIRED before any future promotion request treats R3 as decisive.
- **C4 (power honesty).** Standing caveat of record: R3 passed on a bootstrap CI lower bound at n=15 holdout windows while MDE@80% = 39.3pp for an ~11pp effect — CI-suggestive, not adequately powered. The §5 forward ledger, not R3, is the decisive out-of-time arbiter. Status-log phrasing "the lift held out-of-time" is amended accordingly.
- **C5 (class vs authority).** §5's "promotion to confirmer tier" targets Neural Web bus authority (initiator→confirmer, Article-2 operator-signed event), NOT an Oracle confidence class. The Oracle class ceiling remains display_with_edge for this modern-track single-regime-arc design.
- **C6 (derived-from-seen-surface).** R1/R2 re-test the identical positive estimand seen in W2 (#1509) under a corrected, stricter placebo — confirmatory-of-a-seen-surface, not independent discovery. R3 is the only fresh test and is underpowered per C4. Noted here as the registration's honesty handicap.
- **C7 (MDE provenance).** §3's "design effect from the observed ICC" is corrected to "assumed cluster design effect 1.5× (ICC not computed; RESULTS disclosed-limitation #7); MDE is order-of-magnitude only."
- **C8 (factual fix).** W2_REPORT.md adjudication "6 of 9 nodes positive" corrected to **7 of 9** (XLB/XLE/XLF/XLI/XLK/XLRE/XLV positive; XLP/XLU negative), matching Appendix C and the independent recompute.
- **C9 (window accounting).** 4 of 35 armed windows (ids 4, 9, 10, 17) had zero qualifying member fires → effective independent n = 31 windows (the declared clustering unit). Pooled Δ is leveraged by two high-WR windows; LOO drop-best Δ = 0.1040, still above the corrected placebo p95 = 0.1013 — a ~1.5pp cushion, stated honestly (the corrected symmetric placebo nearly doubled the bar from the W2-era 5.65pp).

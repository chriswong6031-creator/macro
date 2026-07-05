# P1 PREREG Cross-Doc Red-Team

**Reviewer:** Opus subagent (PREREG red-team, EI §7 delegation).
**Date:** 2026-07-04.
**Scope:** the five P1 PREREG drafts in `research/entry_intel/` — P1.1 Separability, P1.2 Gate P&L, P1.3 Trio Ablation, P1.4 Recall Audit, P1.5 Continuation Partition.
**Reference law:** EI masterplan (`research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` on main, PR #1302) §2 R1–R10, §3 inherited law, §5; Setup Species constitution (`research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md` §1).
**Verified against source:** `engine/grading.py:REJECTION_TAXONOMY` (main) — 10-member closed set confirmed.

Finding tags: **[BLOCKING]** = must be fixed before Fable approves the PREREG; **[ADVISORY]** = should fix but does not by itself poison the study.

---

## Cross-doc verdict summary

| Draft | Verdict |
|---|---|
| P1.1 Separability | **APPROVE-WITH-EDITS** (2 advisory) |
| P1.2 Gate P&L | **REWRITE** (2 blocking: garbled FLIP rule, m/BH-family contradiction) |
| P1.3 Trio Ablation | **APPROVE-WITH-EDITS** (1 blocking on BH-count consistency, 2 advisory) |
| P1.4 Recall Audit | **APPROVE-WITH-EDITS** (1 blocking: NEVER-TRIGGERED computability/leak; 2 advisory) |
| P1.5 Continuation | **APPROVE-WITH-EDITS** (1 blocking: K3 era-fallback contradicts sibling drafts + R8 spirit; 1 advisory) |

**Set-level checks that PASS:**
- **BH families disjoint:** five distinct family IDs — `p1_1_separability`, `ei_gate_pnl`, `P1_3_trio_ablation`, `p1_4_recall_audit`, `p15_continuation`. No shared trials across families. ✔
- **DRAFT status header** present verbatim on all five (R8 line at top of each). ✔
- **Replay-artifact-only data clause** present in all five; all name `data/replay/standout_replay.parquet`, cite R9 (never committed), and forbid live/JSON/store fetches. ✔
- **Era/stamp clause** present in all five; all cite the P0 Measurement Memo era table and route survivor-stamped rows to a labeled context appendix excluded from primary stats + BH. ✔ (P1.5 K3 handling is the one exception flagged below.)
- **Kill conditions stated** in all five. ✔
- **Rejection taxonomy** in P1.2 matches `grading.py` exactly (10 members, `hygiene_screen` correctly excluded from grading). ✔

**Set-level issues (detailed in Cross-doc section at end):** trial-grid stamp inconsistency (P1.2), survivor-stamp column-name drift across drafts (`survivor_stamp` / `survivor_biased` / `survivor_bias_stamp` / `survivor_priced`), and era-handling divergence when the memo is absent (four HALT, one falls back).

---

## P1.1 — Separability — APPROVE-WITH-EDITS

**R1 pre-gate pool check: PASS.** §2 explicitly defines the population as every replay row with verdict ∈ {FIRE, NEAR_MISS, REJECTION}, quotes the restriction-of-range rationale, excludes the shipped board from the primary dataset, and repeats the prohibition in §9. No survivor-only leak. This is the single most important check for P1.1 and it is clean.

**Leakage hunt: PASS.** Every feature in §5 is a signal-time replay column; outcomes are terminal-state grades at fixed horizons; the report contract (§10) requires an explicit leak-audit confirming feature values are PIT signal-date observations and that no feature is a transformation of the outcome label. Fill rule (first close strictly after signal date) inherited from the grader. Clean.

**BH / trial grid: PASS.** m = 22 (11×2), one family, enumerated, capped; any addition declared a new trial.

### [ADVISORY] P1.1-A1 — one-tailed Spearman + AUC-in-preregistered-direction is a directional escape hatch if a survivor's sign is "wrong."
§6.1 fixes each feature's test as **one-tailed in the pre-registered direction**. That is defensible (directions are hypothesized in §5), but it means a feature that separates strongly in the *opposite* direction returns a non-significant one-tailed p and is scored NO-SIGNAL. If the intent is purely confirmatory that is fine — but state explicitly that a strong reversed-sign association is **reported as a flagged anomaly**, not silently dropped, so the one-tailed choice can't later be swapped to two-tailed after seeing a wrong-sign result. Mechanical edit: add one sentence to §6.1 — "A feature whose observed association is significant in the direction OPPOSITE its §5 hypothesis is printed with an INVERTED-SIGN flag and referred to Fable; the one-tailed direction is never re-chosen post-hoc."

### [ADVISORY] P1.1-A2 — `weekly_phase` Kruskal–Wallis substitution changes the test statistic but is not reflected in the both-halves sign-stability gate.
§6.1 allows a Kruskal–Wallis H-test to replace Spearman for `weekly_phase` if it is non-ordinal. But §6.4 (both-halves stability) is defined only in terms of "the sign of ρ." Kruskal–Wallis has no signed ρ. Specify how sign-stability is evaluated for the KW case (e.g. sign of the rank-mean difference between the best and worst bucket, fixed at registration), or exclude `weekly_phase` from the survivor list when the KW branch fires. Mechanical: one clause in §6.4.

---

## P1.2 — Gate P&L — REWRITE

Matching design is otherwise sound (see below), but two blocking defects make the decision machinery non-executable-as-written.

### [BLOCKING] P1.2-B1 — the FLIP verdict rule is internally garbled and self-contradicting.
§ "Pre-registered verdict thresholds," FLIP bullet (draft lines ~180–181) reads:

> "Δ_stop_out > 0 at both horizons AND Δ_cushion < 0 at both horizons AND Δ_clean_lift < 0 at both horizons (rejected cohort stops out more AND cushions less AND lifts off less — gate is correctly protective; wait, this is KEEP) — NOTE: a FLIP verdict requires the OPPOSITE: Δ_stop_out < 0 …"

The rule literally contains "wait, this is KEEP" and then negates itself in prose. A pre-registered decision rule cannot contain a mid-sentence self-correction — it is ambiguous which condition binds, and an implementer could code either branch. **Rewrite the FLIP criterion as a single clean predicate** with no negated draft text. The intended (correct) predicate is evidently:
- BH q ≤ 0.10 on all four axes at both horizons, AND
- Δ_stop_out < 0 at both horizons (rejected cohort stops out LESS), AND
- (Δ_cushion > 0 OR Δ_clean_lift > 0) at both horizons (rejected cohort cushions/lifts more), AND
- rejection cohort n ≥ 50 at both horizons, AND
- both-halves sign stability on Δ_stop_out and Δ_cushion.

Delete the "wait, this is KEEP" clause entirely. Until this is a single unambiguous predicate the study cannot run.

### [BLOCKING] P1.2-B2 — m is declared as 18 but the BH correction operates over 72 tests. The family size is understated at the ledger line.
The trial-grid section says "**m = 18 trials. BH family size = 18.**" But § "Primary statistics" says "BH correction applied across all **18 × 4 = 72 raw p-values**, with q-threshold ≤ 0.10." These are inconsistent. The actual multiplicity is 72 (each of 18 reason×horizon cells produces four axis p-values, all tested against q ≤ 0.10). Declaring m = 18 while BH-correcting 72 p-values **understates the family and inflates the effective FDR** — a direct violation of species §1.2 rule (3) ("m taken from the trial ledger so it cannot be understated"). Fix: state m = 72 at the ledger line (18 reason×horizon cells × 4 safety-net axes), and reconcile every "family size" reference. If the intent is instead that only a subset of axes enters BH per verdict, that must be spelled out — but as written the two numbers contradict and the ledger stamp is the wrong one.

### [ADVISORY] P1.2-A1 — matching design is sound; one covariate-timing note.
Matching keys (§ "Matching algorithm") are `episode_cluster_id` (a function of signal_date only), `gics_sector` (signal-time), and `alignment_tier` (signal-time). All three are pre-signal / at-signal — **no conditioning on outcome.** The union-cohort construction (Step 4) is defensible and the precision note correctly explains why caliper matching is avoided. This is clean. One caveat to state explicitly: `gics_sector` is a **point-in-time-at-signal** attribute and GICS reclassifications are historically non-PIT in many stores — add a one-line disclosure in the leak-audit section that the sector label is the replay-frozen signal-time sector (already implied by "features frozen to replay columns," but the matching key deserves the explicit call-out since a look-ahead sector reassignment would silently re-pool cohorts).

### [ADVISORY] P1.2-A2 — n-floor asymmetry between DEMOTE (n≥25) and INCONCLUSIVE (n<10) leaves a 10–24 gray band with no stated verdict.
KEEP §(a) covers n<10 as INCONCLUSIVE-logged-as-KEEP. DEMOTE requires n≥25, FLIP requires n≥50. A reason with 10 ≤ n < 25 that passes BH on the DEMOTE axes falls through: it is not n<10, so not auto-KEEP by clause (a); it cannot DEMOTE (n<25). State the default explicitly — presumably KEEP-with-note — so the 10–24 band is not an undefined branch.

---

## P1.3 — Trio Ablation — APPROVE-WITH-EDITS

**R3 (production-trigger-only) PASS:** §1 restricts the population to `verdict == 'fire'`, no near-miss/rejection, and the plain-English + §7 both quarantine the weekly-trigger backtest as "HYPOTHESIS — DIFFERENT TRIGGER — NOT VALIDATION." **R4 (both gate AND weight) PASS:** every factor F1/F2/F3 encodes Mode A (hard gate) and Mode B (rank weight); §3 defines both. **R7 fire-rate table PASS:** §5.3 mandates the fire-rate impact table as a standalone deliverable regardless of BH outcome, with `gate_fire_rate_impact_pct = 0.0` for Mode B by construction. All three R-rulings this draft must satisfy are satisfied.

**Leakage hunt: PASS.** §8 freezes features to signal-time replay columns, forbids re-computation, and requires the leak-audit to confirm next-bar fill and PIT feature freeze. Mode-B "moved up vs moved down" partition (§3 Mode B) is fully deterministic from replay columns (bonus formula applied to frozen rank score) — no outcome conditioning.

### [BLOCKING] P1.3-B1 — the BH family size m=30 conflicts with the Mode-B dead-money exclusion; the enumerated trial table and the exclusion note disagree on which trials exist.
§4 states "**m = 30 pre-registered trials**" and the table T01–T30 lists exactly 30. But the paragraph immediately after says "**Mode-B rows T07-T10 and T17-T20 and T27-T30 omit dead-money.**" Inspect the table: the Mode-B rows (T07–T10, T17–T20, T27–T30) already only carry stop-out and cushioned terminal states — there is **no dead-money Mode-B trial in the table to omit.** So either (a) the "omit dead-money" note is describing a non-existent row (harmless but confusing), or (b) the note implies dead-money Mode-B trials were mentally counted and then removed, in which case m=30 is correct but the note is dead text. This is a consistency defect in the *authoritative trial-count section* and must be resolved cleanly because m feeds BH directly. Fix: delete the "omit dead-money" sentence (the table already excludes those rows), OR if dead-money Mode-A vs Mode-B asymmetry needs documenting, move it to a design-rationale footnote that does not sit inside the m-declaration. The family count must be unambiguous at the point m is stated.

### [ADVISORY] P1.3-A1 — F2 RS-inflection operationalization (Q2∪Q3 favorable) is a non-monotone recode not previously validated; state that the recode itself is the registered hypothesis.
The backtest evidence (masterplan §1) was "RS inflection," but §2 F2 operationalizes it as "middle two quartiles favorable, Q1 and Q4 unfavorable" — a non-monotone bucket. That is a legitimate pre-registration, but it differs from a monotone "higher RS better" reading and from P1.1's `rs_vs_sector_quartile` direction hypothesis ("higher → better"). The two studies therefore encode *contradictory* directional hypotheses on the same column across disjoint families — acceptable (different questions, different populations) but worth a one-line cross-reference so a reader does not think one is a typo. Add to §2 F2: "Note: P1.1 tests this column monotonically; P1.3 tests the non-monotone inflection recode. Both are registered; they are different hypotheses on disjoint families."

### [ADVISORY] P1.3-A2 — the +0.10 fractional-rank-bonus magnitude is asserted, not grounded against the `blend_sorted` 0..1 scale.
Species §1.4 warns new bonuses must be sized against the `blend_sorted` scale (one cascade tier ≈ `tier_frac`) "or they silently dominate/vanish." §2 fixes the RW bonus at +0.10 fractional rank points for all three factors but does not tie +0.10 to `tier_frac`. Since Mode-B's verdict is derived from rank-movement direction, a mis-scaled bonus could make every fire move or no fire move, degenerating the partition. Add a sentence pinning +0.10 to the measured `tier_frac` magnitude (or stating it is deliberately ≈ one tier), logged in the pre-run preamble.

---

## P1.4 — Recall Audit — APPROVE-WITH-EDITS

**Definitions frozen: PASS.** Denominator A (durable-low) and B (+20%/60d) are fully specified with frozen parameters (60-bar min, 0.95 undercut floor cited to `bottom_signal_backtest/metrics.py:57`, 1.0×ATR depth, 5-bar dedup). Descriptive-census framing is correct; no significance machinery, Wilson CIs only — consistent with masterplan §5/P1.4. Trial grid T1–T5 enumerated and capped.

**No-hindsight-denominator: mostly PASS with one blocking gap (below).** Both denominators are explicitly built from point-in-time price columns with forward windows drawn from actual available history (no forward-fill beyond data; delisting excludes the event). The +20%/60d and durable-low definitions use `close_{t+60}` — that is a *forward outcome label on the denominator*, which is correct and intended here (the denominator IS the set of objectively-significant future events; recall is measured against it). This is not leakage because the denominator is the ground-truth event set, not a funnel feature. Clean.

### [BLOCKING] P1.4-B1 — NEVER-TRIGGERED is defined as "no replay row exists for (ticker,date)," but the denominators require price history for names on dates the replay may not contain. The denominator is not computable from the replay artifact alone as written — and the clause silently mixes two universes.
The draft insists (Data source, Inherited law) that **every field, including the prices used to build Denominators A and B, must already be a column in the replay artifact** — "fields not in the artifact are not added during this study." But the masterplan P0.1 design contract says the replay logs rows for **candidate (prefilter-passed) (ticker,date) pairs only** (a vectorized cross-detector marks candidates; the full cascade runs only on candidates). A NEVER-TRIGGERED durable-low or +20% event, by the draft's own definition (funnel-verdict partition, category 4), is precisely a (ticker,date) with **no replay row**. Therefore its price history — needed to (a) detect it as a durable-low/large-move event and (b) confirm in-universe — **cannot come from the replay artifact**, because there is no replay row there. As written, the study either (i) cannot detect any NEVER-TRIGGERED event (the denominator collapses to candidate rows, making recall trivially near-1 and defeating the entire coverage purpose), or (ii) must read prices from outside `data/replay/`, violating the replay-only clause it repeats three times.

This is the central design contradiction of P1.4 and must be resolved before approval. Options for Fable/author (any one, stated explicitly):
- **Require the replay artifact to log a per-(ticker,date) universe price panel** (candidate or not) as an explicit P0.1 deliverable, and add a startup HALT if that panel column is absent (mirror P1.5 K2 style). This keeps the replay-only clause honest.
- **OR** carve an explicit, narrow exception: durable-low/large-move *detection* and in-universe membership read the canonical PIT price panel (`data/...` by absolute path) while all *verdict* lookups read the replay — and rewrite the "no fields added" clause to permit that one price source, with a leak-audit note that the price panel is PIT.

Either is fine; the current text asserting "replay columns only" while defining events that have no replay row is self-contradictory and blocks execution.

### [ADVISORY] P1.4-A1 — NEAR-MISSED / REJECTED sub-count reason lists omit two taxonomy members.
The funnel-verdict partition table lists sub-count reasons as `freshness_expired, not_topped_veto, tier_cutoff, extension_demote, knife_demote, sector_cap_displaced, board_rank_cutoff` — **7 reasons.** The closed `REJECTION_TAXONOMY` (verified in `engine/grading.py`) has 10 members; the list omits `event_blackout`, `cohort_null`, and (correctly, for grading) `hygiene_screen`. For a census whose whole point is coverage completeness, silently dropping `event_blackout` and `cohort_null` from the sub-breakdown will misclassify or under-count those rejections. Fix: enumerate all 9 gradeable reasons (or state a fold-to-`other` rule) in T3/T4; decide `hygiene_screen`'s treatment explicitly (P1.2 excludes it from grading — P1.4 should either bucket it as a non-alpha rejection or footnote its exclusion, but must not leave it undefined).

### [ADVISORY] P1.4-A2 — the ATR-waiver escape softens Denominator A silently.
§Denominator A condition 3 waives the depth floor "if ATR columns are not available in the replay artifact" and merely discloses the waiver. Waiving condition 3 materially widens Denominator A (flat series now qualify as durable lows), which mechanically *lowers* recall_fired and could spuriously trip the "precision-stacked to irrelevance" escalation. Recommend: make ATR-column presence a **pre-run gate** (HALT-and-report if absent, like P1.5 K2) rather than a silent-widen waiver, OR pre-register that the waived-vs-unwaived denominator sizes are BOTH printed so the widening is visible. A frozen definition should not have a branch that changes the denominator by whether an optional column shipped.

---

## P1.5 — Continuation — APPROVE-WITH-EDITS

**Decision rule total: PASS.** §6 covers all outcome combinations: H-EXCLUDE (Δ<−5pp), H-MISLABEL (|Δ|<5pp or Δ>0), H-UNDERRANK (Δ>+5pp), H-NULL (|Δ|<5pp & q>0.10), AMBIGUOUS (sign conflict / per-name disagreement). Every (sign, magnitude, significance, stability) region maps to exactly one action. **ARMED-tier separation: PASS.** §3 and §9 explicitly split ARMED by `weekly_phase == 'rising'` (ARMED-continuation, primary arm) vs the bottoming phases, never pooled; this operationalizes the masterplan §1 ARMED nuance precisely, which is the specific thing this draft had to get right.

**Leakage hunt: PASS.** §1 lists all consumed columns as signal-time replay features; §10 leak-audit requires confirming `weekly_phase` and `rs_vs_sector_quartile` are logged-at-signal, not look-ahead; K2 HALTs if those columns are >20% null. Good defensive posture.

### [BLOCKING] P1.5-B1 — K3 lets the study run on a provisional era when the Measurement Memo is absent; the other four drafts HALT, and the masterplan makes the memo the authoritative era source. This is a cross-doc inconsistency and a soft escape hatch.
K3: "if `P0_MEASUREMENT_MEMO.md` does not exist at execution time — **use provisional era 2015-01-01 → last full month in replay** and stamp all verdict rows `era_table_provisional = True`. Do not halt." Every other P1 draft (P1.1 §11, P1.2 era clause, P1.3 §8, P1.4 era clause) **HALTs and returns a blocker if the memo is absent** — because the memo's bias-bound era table is what makes claims verdict-grade (masterplan P0.2 / §5: "the era table every P1 PREREG must cite"). Letting P1.5 self-select 2015-01-01 is exactly the "does not self-select an era" prohibition P1.2 states in its own era clause. Producing verdict-grade continuation claims (that feed H-UNDERRANK → P3 re-rank inputs, a money-path change) on a self-chosen era violates R8's spirit and the survivorship-honesty law. Fix: change K3 to HALT-and-blocker (align with the sibling drafts), OR — if a provisional dry-run is genuinely wanted — restrict the provisional-era path to **context-only, non-verdict output** (no H-UNDERRANK/H-EXCLUDE ruling issued, no P3 hand-off) and rename the branch so it cannot emit a promotion-feeding verdict. As written it can emit a verdict-grade ruling on an unaudited era.

### [ADVISORY] P1.5-A1 — H-MISLABEL condition overlaps H-UNDERRANK at Δ>0 without BH-stability guards, creating a precedence ambiguity.
§6 H-MISLABEL fires on "|Δ| < 5pp (not materially different) **OR Δ > 0 AND BH q ≤ 0.10**." H-UNDERRANK fires on "Δ > +5pp AND BH q ≤ 0.10 AND both-halves sign stable." A result with Δ = +7pp, q ≤ 0.10, sign-stable satisfies **both** the H-MISLABEL disjunct (Δ>0 & q≤0.10) and the H-UNDERRANK predicate. The table is read top-to-bottom so H-EXCLUDE→H-MISLABEL→H-UNDERRANK ordering would resolve it to H-MISLABEL, swallowing every genuine underrank. Fix: tighten H-MISLABEL's second disjunct to "0 < Δ ≤ +5pp" (or "Δ>0 AND Δ<+5pp") so the three magnitude bands are disjoint. Mechanical one-token edit; without it the H-UNDERRANK branch is unreachable for the exact case it exists to catch.

---

## Cross-doc section

### CD-1 [ADVISORY] Survivor-stamp column name drifts across the five drafts.
Four different names appear for the same PIT stamp: `survivor_stamp` (P1.1, P1.2, P1.4), `survivor_biased` (P1.5 §1), `survivor_bias_stamp` (P1.3). P1.2 additionally uses the *value* `survivor_priced`. Since all five read the same artifact, the column name must be one string or the startup schema check fails for four of five studies. Fix: pin the canonical replay column name (recommend matching what P0.1 actually emits — resolve at the P0.1 schema, not here) and update all five to reference it, or add the name-mapping-preamble discipline P1.3 §1 already uses to the other four. This is advisory only because P1.3 already establishes a name-mapping-logged-before-run pattern that, if adopted set-wide, dissolves the issue.

### CD-2 [ADVISORY] Era-absent behavior is inconsistent set-wide (see P1.5-B1).
Four drafts HALT if the memo is absent; P1.5 falls back. Beyond the P1.5 blocking fix, Fable should confirm the *intended* set-wide policy is HALT (it should be, per §5) and that no other draft quietly softened it. Verified: P1.1/P1.2/P1.3/P1.4 all HALT. Only P1.5 deviates.

### CD-3 [ADVISORY] `episode_cluster_id` window length is defined inconsistently (21d vs "≥21d block").
P1.2 defines episode clusters as **non-overlapping 21-trading-day** calendar windows AND uses them as the matching key. P1.1/P1.3/P1.5 use **week-cluster or "block ≥ 21 trading days"** for the bootstrap. These are different granularities. Within each study the choice is internally consistent and pre-registered, so no study is individually wrong — but note that P1.2 uses the 21d cluster as a *matching covariate* (structural) whereas the others use it only for *variance estimation* (bootstrap block). Flag for Fable: confirm the P0.1 artifact ships a single canonical `episode_cluster_id` and that P1.2's matching semantics (21d bucket) are what that column encodes; if the artifact's `episode_cluster_id` is week-based, P1.2's Step 1 fallback ("computed here from signal_date") diverges from the shared column and the matching key silently differs from the other studies' clustering. Recommend one canonical cluster definition in P0.1, referenced by all five.

### CD-4 [PASS, noted] Column overlap across disjoint families is benign.
`ext_z`, `rs_vs_sector_quartile`, and `cohort_washout_proximity` appear in P1.1 (as separability features), P1.3 (as trio factors), and P1.5 (`ext_z`/RS as context). Because the BH families are disjoint and the populations differ (P1.1 = pre-gate pool; P1.3/P1.5 = fires only), reusing the same columns across studies is NOT double-counting and does not require joint correction. No action — recorded so Fable doesn't mistake it for a shared-family leak. The one directional-hypothesis conflict (P1.1 monotone vs P1.3 non-monotone on `rs_vs_sector_quartile`) is covered by P1.3-A1.

### CD-5 [PASS, noted] No post-hoc escape hatches found other than the two flagged.
Every draft states "any post-hoc variation = new recorded trial" and "PREREG immutable; results go to the REPORT only." The only soft hatches are P1.1-A1 (one-tailed direction) and P1.5-B1/A1 (era fallback + band overlap), all addressed above. No draft contains a "if underpowered, widen the grid" or "re-choose horizon after seeing results" clause.

---

## What Fable must decide

1. **P1.2 REWRITE** — the FLIP predicate (B1) and m=18-vs-72 family size (B2) are both blocking; the study is non-executable until reworded. These are mechanical rewrites, not redesigns.
2. **P1.4 NEVER-TRIGGERED source (B1)** — needs an explicit ruling: either P0.1 must ship a universe price panel, or P1.4 gets a narrow PIT-price exception to the replay-only clause. This is a real design decision, not just wording.
3. **P1.5 K3 (B1)** — align to HALT or demote the provisional-era branch to context-only.
4. **P1.3 m-declaration (B1)** — delete/relocate the dead "omit dead-money" note so m=30 is unambiguous at the ledger line.
5. **Set-wide:** pin one survivor-stamp column name and one `episode_cluster_id` definition at the P0.1 schema (CD-1, CD-3); confirm HALT-on-missing-memo is the intended universal policy (CD-2).

All advisory items are one-to-two-sentence edits. With the four blocking rewrites applied, P1.1/P1.3/P1.4/P1.5 clear to APPROVE and P1.2 clears to APPROVE-WITH-EDITS.

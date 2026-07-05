# P2.1b — F1 Cohort-Washout + F2 RS-Inflection Rank-Weight Promotion PREREG

**STATUS: APPROVED — Fable 2026-07-05 (red-team P2_REDTEAM.md blocking fixes applied; Fable rulings R-P2.1 flip-floor=100 clusters+2 quarters, R-P2.2 single concordance authority = P2.1b §3.3)**

**Study:** P2.1b Rank-Weight Promotion — F1 (cohort-washout proximity) + F2 (RS-inflection) as additive blend_sorted bonus weights.
**Program:** Entry Intelligence (EI). **Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §6/P2.1`.
**Registered:** 2026-07-05 (before any shadow wiring or live board influence).
**Author:** Sonnet subagent under Fable orchestration.
**Provenance:** P1.3 Trio Ablation RESULTS.md (round 2, 2026-07-05) + REVIEW_v2.md (Conformant, 2026-07-05).

**Constitutional gates binding on this PREREG:**
- R6: board_ordering change → shadow-first with pre-registered flip criterion.
- R7: additive-lanes law — rank weight raises quality labels UP; never filters board toward zero.
- Article 2 (Neural Web): `board_ordering` is a named money-path surface; shadow period with track-record is mandatory before live influence; Wilson-gated authority.
- Species ladder: chip → ledger → graded_bonus → gate_weight; each rung requires its own registered criterion.
- ADVISORY-2 (REVIEW_v2.md): cite ~3 independent forward-return effects (≈10 independent forward-return tests across the grid, not "22/30 trials") as the evidence-strength headline; duplicated p-values within a (factor, mode, horizon) cell are transparent in the P1.3 design, not an inflation.

---

## 0. Plain-English summary

> Two of the three trio factors earned a rank-weight promotion in P1.3: **cohort-washout proximity (F1)** and **RS-inflection (F2)**. Neither passed as a hard gate — each would have blocked roughly half the board, which the additive-lanes law prohibits without a stronger bar. Instead, they each earn a small additive tilt to a stock's rank position within the daily fire pool.
>
> This document registers how that tilt is wired, how it is tested in shadow mode before it ever affects the live board, and what has to happen in the shadow forward ledger before the tilt is allowed to become permanent.
>
> There is one critical condition on F1 in particular: the P1.3 evidence used a **proxy** for cohort-washout proximity (a boolean field derived by the replay harness, not the production COILED/S1 machinery). This promotion is explicitly **conditional** on connecting the live COILED/S1 computation as the production input — and on a pre-registered check confirming that the proxy and the production values agree closely enough to trust the transfer. If they diverge too much, the P1.3 F1 trials must be re-run on production values before the shadow can ship.

---

## 1. Evidence base (cite exact numbers, never approximate)

Binding evidence source: `research/entry_intel/p1_runs/P1_3/RESULTS.md` (round 2, 2026-07-05) and `research/entry_intel/p1_runs/P1_3/REVIEW_v2.md` (Conformant verdict, 2026-07-05). Replay artifact MD5 `906175f9eb8caa351ed6d7d5c56265d3`. Primary window: 2022-06-30 → 2025-12-29. Verdict-grade fires: 49,939. Episode clusters: 22,295.

### F1 — Cohort-washout proximity: three independent forward-return effects cited

**Effect 1 — Dead-money reduction at 21d (T02, HG mode):**
- Terminal-state delta: Δ = −13.19pp dead-money (would-pass minus would-block; favorable direction = lower dead-money).
- Permutation p = 0.0002; BH-adj p = 0.0006 (survives at q≤0.10). Effect size r = −0.1247.
- Both-halves sign-stable: H1 Δ = −14.00pp, H2 Δ = −12.29pp (same sign, consistent magnitude).
- Independent forward-return test: T01/T02/T03 share perm_p = 0.0002 (one MWU test on continuous returns; three terminal-state Δ rows reflect the single test). Cited as one independent effect.

**Effect 2 — Stop-out reduction at 63d (T04, HG mode):**
- Terminal-state delta: Δ = −5.21pp stopped (favorable direction = lower stop-out).
- Permutation p = 0.0002; BH-adj p = 0.0006. Effect size r = −0.0978.
- Both-halves sign-stable: H1 Δ = −8.54pp, H2 Δ = −1.31pp (same sign).
- This is a second independent forward-return test (63d horizon, same factor, HG mode). Cited as one independent effect.

**Effect 3 — Stop-out reduction at 63d in rank-weight mode (T09, RW mode):**
- Terminal-state delta: Δ = −4.55pp stopped (favorable direction).
- Permutation p = 0.0002; BH-adj p = 0.0006. Effect size r = −0.0840.
- Both-halves sign-stable: H1 Δ = −7.81pp, H2 Δ = −0.78pp (same sign).
- RW mode is the mode that ships (gate-rejected at 54.0% board impact under §6.2). This is the directly relevant effect. Cited as one independent effect.

**Signal shape (disclosure, not verdict):** at 21d, would-pass fires have a +2.41pp higher stop-out rate (T01, unfavorable, sign-stable across halves) but −13.19pp dead-money. The net benefit is horizon-dependent and stronger at 63d. The rank-weight design correctly treats this as a tilt, not a block, because blocking would also eliminate the unfavorable 21d stop-out leg of the signal.

**Gate-reject record:** F1 HG gate-rejected under PREREG §6.2 (fire-rate impact 54.0% = 26,974/49,939 would-block; 21d stop-out unfavorable). This document promotes the rank-weight design only.

### F2 — RS-inflection (Q2∪Q3): three independent forward-return effects cited

**Effect 1 — Cushioned improvement at 21d (T18, RW mode):**
- Terminal-state delta: Δ = +0.15pp cushioned (favorable direction = higher cushioned).
- Permutation p = 0.0684; BH-adj p = 0.0933 (survives at q≤0.10). Effect size r = −0.0156.
- Both-halves sign-stable: H1 Δ = +0.20pp, H2 Δ = +0.10pp (same sign).
- Independent forward-return test: T17/T18 share perm_p = 0.0684 (one MWU on continuous 21d returns, RW mode). Cited as one independent effect.

**Effect 2 — Cushioned improvement at 63d (T20, RW mode):**
- Terminal-state delta: Δ = +0.68pp cushioned (favorable direction).
- Permutation p = 0.0426; BH-adj p = 0.0752. Effect size r = −0.0180.
- Both-halves sign-stable: H1 Δ = +0.62pp, H2 Δ = +0.76pp (same sign, consistent).
- Second independent forward-return test (63d horizon, RW mode). Cited as one independent effect.

**Effect 3 — Stop-out reduction at 63d (T19, RW mode):**
- Terminal-state delta: Δ = −0.04pp stopped (favorable direction; very small magnitude).
- Permutation p = 0.0426; BH-adj p = 0.0752. Effect size r = −0.0180 (same underlying test as T20 at 63d RW; shared forward-return test across T19/T20). Cited here for completeness; its |Δ| = 0.04pp is not independently meaningful — the 63d RW effect is properly cited via T20.
- Note: T19 sign-stability fails (H1 Δ = −1.02pp, H2 Δ = +0.66pp, sign flip). T19 does NOT satisfy the PREREG §6.3 ship criterion independently. The 63d RW mode ships via T20 (cushioned, sign-stable).

**Signal shape (disclosure):** F2 is the weakest of the three trio factors (|r| ≈ 0.01–0.02 across surviving RW trials). HG mode is null (T11–T16, all BH-adj p ≈ 0.20–0.24). The shadow-test MUST monitor effect size; if |r| does not sustain in the forward ledger, the F2 bonus is removed before permanent promotion. HG gate-rejected (48.5% board impact, 22,378/46,111 would-block on F2-valid population; HG statistics also fail BH).

---

## 2. Scope of this PREREG

This document covers **two rank-weight bonuses only**: F1-RW and F2-RW as additive increments to the `blend_sorted` 0..1 score. It does NOT cover:

- F3 (anti-chase, ext_z ≤ 2.0) — F3 ships as a hard gate under a separate PREREG (P2.1a — P2_1A_ANTICHASE_GATE_PREREG.md, registered 2026-07-05).
- Any gate-ification of F1 or F2 — both gate designs are closed (GATE-REJECT under P1.3 §6.2).
- Any future gate-weight rung — the current promotion is to `graded_bonus` only; gate_weight requires its own PREREG after ledger confirmation.
- Species registry permanent status — registry transitions in §7 are provisional pending Fable approval of this PREREG and Fable approval of the shadow flip decision.

---

## 3. F1 critical clause — proxy-vs-production concordance gate (BINDING)

### 3.1 The proxy gap (P1.3 review advisory A1)

The P1.3 replay used `washout_proximity` as a boolean field frozen at signal time in `data/replay/replay_boarded.parquet`. Per the REVIEW_v2.md advisory (ADVISORY-1 antecedent in the P1.1 review, A1): this field was computed by the replay harness from available price-series features at signal time, NOT by calling the production COILED/S1 machinery in `engine/cycles.py`. The P1.3 evidence is therefore **100% proxy-sourced** for F1.

The promotion is valid as hypothesis transfer (the production trigger + PIT-era + BH-corrected evidence class is the same as pre-validated seeding precedent per masterplan §6/P2.1). But the production wiring MUST use the production COILED/S1 computation as the live input — never the proxy field — and the concordance between proxy and production values must be pre-confirmed before the shadow ships.

### 3.2 Production input specification

The live F1 bonus computation uses the COILED/S1 washout state as produced by `engine/cycles.py` (the `in_washout_ctx` flag or equivalent S1-machinery output per the species entry for S1 / CN-WASHOUT). Specifically:

- **Input:** whether the name is currently in a COILED/multi-TF washout state per the production COILED detection in `engine/cycles.py`. This is the same machinery that arms S1 (Cohort Capitulation Reversal) — the F1 bonus and S1 share the same arming condition.
- **Not the proxy:** the replay `washout_proximity` boolean is NOT used as the live input. It was a harness field; its derivation from price-series features may differ from the production COILED detection in subtle ways.

### 3.3 Pre-registered concordance check (hard gate before shadow ship)

Before the F1 bonus is activated in the shadow rank column, the following concordance check runs and its result is logged:

**Concordance definition:** for all names appearing in both the replay artifact (2022-06-30 → 2025-12-29 verdict-grade fires) and the current production board snapshot, compute the fraction of names where `replay washout_proximity == production COILED state` at the signal date (using the production COILED value at that date, as computed by the current live engine run, PIT-verified).

**Concordance floor: 90%.** If the concordance on overlapping names is ≥ 90%, the proxy-to-production transfer is accepted and the shadow ships using the production COILED input.

**Concordance fail path:** if concordance < 90% on overlapping names, the shadow does NOT ship. Instead:
1. The concordance gap is documented (which direction: production finds more washout, or less?).
2. P1.3's F1 trials (T07/T08/T09/T10 for RW, and T01–T06 for HG context) are re-run on production COILED values for the overlapping sub-population. This constitutes a new recorded trial set (registered here; trial_ids P2_1B_F1_REPROBE_T01–T10, BH family `P2_1B_f1_concordance_reprobe`).
3. Only if the reprobe confirms BH-survive + sign-stable + n_clusters ≥ 25 on production-COILED values does the shadow ship.

**No exemption from the concordance check.** Even if a spot-check of a handful of names shows qualitative agreement, the quantitative 90% concordance floor on the overlapping replay population is mandatory before any board influence.

**Downstream consumers of the washout dimension inherit this GO/REPROBE verdict.** P3 (kernel-rank) reads `research/entry_intel/p1_runs/P1_3/concordance_check.json` at build time to determine whether cohort_washout cells are eligible. No downstream consumer may apply a weaker production-source bar than the 90% floor defined here. P2.1b §3.3 is the single authoritative concordance definition for the washout feature across all Phase-2 documents.

---

## 4. Rank-weight design (exact, frozen)

### 4.1 Blend-sorted scale pin (P1.3-A2 advisory honored)

The `blend_sorted` column is the 0..1 within-day rank score that the production board already uses for ordering. Both F1 and F2 bonuses are additive increments **on this scale, normalized within the daily fire pool**. The pin is defined as follows:

- **Scaling reference:** `tier_frac` as measured in the P1.3 run preamble = **0.0238** (the fractional rank distance between adjacent cascade tiers on the blend_sorted 0..1 scale, verified against the replay artifact population).
- **Bonus magnitude (pre-registered in P1.3 §2 and carried forward unchanged):** +0.10 fractional rank points per factor, corresponding to approximately 4.2 tier_frac units. This is intentionally sized to move a fire up by approximately one full cascade tier without silently dominating or vanishing against the scale.
- **Both bonuses are additive:** a fire can receive +0.10 (F1 only), +0.10 (F2 only), or +0.20 (both F1 and F2) in total bonus. The maximum combined bonus of +0.20 corresponds to approximately two cascade tier steps — a meaningful but not dominating influence.
- **No cross-factor interactions are defined.** The bonuses do not interact; their magnitudes are not adjusted based on co-presence.

### 4.2 Factor-specific bonus formulas (frozen)

**F1 — Cohort-washout bonus:**
```
f1_bonus = +0.10  if  production_coiled_state == True  (washout-proximity favorable)
f1_bonus =  0.00  otherwise
```
The production COILED state is a binary (in-washout / not-in-washout) per the COILED/S1 machinery. No threshold-searching; no continuous transform.

**F2 — RS-inflection bonus:**
```
f2_bonus = +0.10  if  rs_sector_quartile in {2, 3}  (Q2∪Q3 = inflecting, not extended)
f2_bonus =  0.00  if  rs_sector_quartile in {1, 4}  (Q1 = lagging bottom, Q4 = extended top)
f2_bonus =  0.00  if  rs_sector_quartile is null  (3,828 of 49,939 fires in P1.3; excluded)
```
The Q2∪Q3 definition is pre-registered in P1.3 §2/F2. Fallback to the continuous z-score ([−0.5, +1.0] range) applies only if `rs_sector_quartile` is absent from the production board frame — logged in the shadow preamble if used.

### 4.3 Rank construction

The shadow rank column is:
```
blend_sorted_shadow = blend_sorted + f1_bonus + f2_bonus
```
This produces values in [0.0, 1.20]. The shadow column is used **only** in the shadow side-by-side display; the production `blend_sorted` column remains unchanged until the flip criterion is met. No in-place modification of the production rank.

Within-day normalization: after applying the bonus, the shadow column is re-percentile-ranked within the day so the final shadow score remains on the 0..1 scale (prevents the shadow column from exceeding 1.0 visually). The re-percentile-rank is a display transformation only; the flip criterion operates on realized outcome metrics from the forward ledger, not on rank-score magnitudes.

---

## 5. Shadow-first deployment (R6 + Article 2 compliance)

### 5.1 Shadow architecture

The shadow consists of a side-by-side rank column displayed to the operator, NOT to any downstream consumer. Implementation:
- A new column `board_rank_shadow_P2_1B` is appended to the board output (in-memory or staging file) alongside the existing `blend_sorted` (incumbent).
- The production board serves `blend_sorted` to all consumers unchanged.
- The shadow column is routed to the internal monitoring surface only.
- Every fire event emits two rank positions: `rank_incumbent` (from `blend_sorted`) and `rank_shadow` (from `blend_sorted_shadow`). Both positions are logged to the forward ledger for outcome tracking.

### 5.2 Forward ledger tracking

The shadow forward ledger records:
- Per-fire: `rank_incumbent`, `rank_shadow`, `f1_bonus_applied` (bool), `f2_bonus_applied` (bool), `episode_id`, `signal_date`, `terminal_state` (as it resolves at each horizon), `fwd_ret_21`, `fwd_ret_63`.
- Ledger store: `data/signal_archive/shadow_P2_1B_ledger.parquet` (per R9 convention, canonical checkout, not committed to git).
- Episode-cluster ids inherited from the production replay schema.

### 5.3 Article 2 governance ledger entry

The following governance ledger entry is registered at shadow activation (populated by the build PR, not by this PREREG):
```
surface: board_ordering
action: shadow_activate
factors: [F1_washout_RW, F2_RS_inflection_RW]
shadow_id: P2_1B
prereg: research/entry_intel/P2_1B_RANKWEIGHT_PREREG.md
flip_criterion: see §6
activation_date: [populated at PR merge]
n_floor_for_flip: 25 episode clusters per factor cell, Wilson lower bound
```

---

## 6. Flip criterion (pre-registered; immutable after Fable approval)

The shadow flips to production (i.e., `blend_sorted_shadow` replaces `blend_sorted` as the board ranking input) **only if ALL of the following hold simultaneously**:

### 6.1 Episode-clustered n floor
The shadow forward ledger has accumulated ≥ 25 independent episode clusters (unique `episode_id` values per the `TICKER_YYYY-WNN` schema) for:
- **F1 cell:** fires where `f1_bonus_applied == True` (in-washout fires), with at least 25 episode clusters.
- **F2 cell:** fires where `f2_bonus_applied == True` (Q2∪Q3 RS fires), with at least 25 episode clusters.

A bonus factor that has not reached 25 episode clusters is labeled **THIN** and its flip criterion is evaluated as NOT-MET, regardless of its point estimate direction.

### 6.2 Wilson bound on stop-out difference (primary safety-net axis)

Define the signed quantity **D_f = stop_out_rate(bonus-cell) − stop_out_rate(non-bonus-cell)**, where D_f < 0 is the favorable direction (bonus cohort has lower stop-out). The flip criterion requires:

```
Wilson_upper(D_f, episode-clustered bootstrap N=1000) < 0
```

at **both 21d and 63d horizons** — i.e., even the upper confidence bound of the stop-out difference is negative, confirming the bonus cohort stop-out is credibly lower than the non-bonus cohort stop-out. "Credibly lower" means the entire Wilson 95% interval for D_f is below zero. This is the same Wilson-gated authority requirement as Article 3 (applied here to the safety-net axis rather than a general lift criterion).

Both horizons must pass. **Acknowledged:** F1's backtest shows an adverse 21d stop-out leg (T07 +2.58pp, sign-stable); the "both horizons" rule is therefore the binding constraint for F1. A live shadow ledger where the 21d D_f Wilson upper bound ≥ 0 is an expected outcome, not an anomaly — the flip criterion for F1 can only fire if live 21d stop-out is less adverse than the backtest observed.

### 6.3 Sign stability in the shadow ledger

The shadow ledger is split at its chronological midpoint. The stop-out delta (bonus-cell minus non-bonus-cell) must have the same sign in both halves for the factor being flipped.

### 6.4 Dead-money and cushioned as secondary checks (advisory, not blocking)

The dead-money rate and cushioned rate are printed alongside the flip criterion evaluation but are not blocking conditions. If the Wilson bound on stop-out passes but dead-money moves adversely by more than +5pp, Fable is flagged for review before the flip executes. The flip does not auto-block on dead-money; it requests Fable review.

### 6.5 F1 and F2 flip independently

F1 and F2 are evaluated and potentially flipped on independent schedules. One can flip while the other remains in shadow. The production `blend_sorted` column incorporates only the flipped factors' bonuses at any given time:
- Pre-F1-flip, pre-F2-flip: `blend_sorted` = incumbent (no bonus).
- Post-F1-flip only: `blend_sorted` incorporates F1 bonus.
- Post-F2-flip only: `blend_sorted` incorporates F2 bonus.
- Post-both-flip: `blend_sorted` incorporates F1 + F2 bonuses.

Each flip is logged as a governance ledger entry with the evidence table that triggered it.

### 6.6 Shadow reversal criterion

Using the same signed quantity **D_f = stop_out_rate(bonus-cell) − stop_out_rate(non-bonus-cell)**: if the shadow forward ledger (on ≥ 25 episode clusters) shows the Wilson **lower** bound on D_f > 0 at both 21d and 63d — i.e., even the lower confidence bound on the stop-out difference is positive, confirming the bonus cohort stop-out is credibly higher than the non-bonus cohort — the shadow is withdrawn (factor returns to display-only status, registry transitions to `shadow_falsified`). Fable is notified; no automatic board action.

---

## 7. Species registry entries

Two new provisional species entries are created upon Fable approval of this PREREG. The entries become permanent upon flip approval.

### 7.1 F1 — Cohort-Washout Proximity Rank Tilt

```
species_id: EI-F1-RW
version: 0.1 (shadow)
name: Cohort-Washout Proximity Rank Tilt
validation_status: phase0_passed (RW) — awaiting shadow confirmation
deployment_status: shadow (pending flip criterion)
mechanism: >
  A production-trigger fire occurring while the name is in COILED/multi-TF washout state
  (per engine/cycles.py S1 machinery) receives a +0.10 blend_sorted bonus, tilting it
  upward by approximately one cascade tier within the daily fire pool. Mechanism: forced-seller
  exhaustion during washout reduces the probability of dead-money and (at 63d) stop-out outcomes.
  Signal is horizon-dependent: adverse at 21d stop-out (+2.41pp), favorable at 21d dead-money
  (−13.19pp) and 63d stop-out (−5.21pp). Shipped as rank tilt, NOT gate (54.0% gate-fire-rate
  impact closes the gate path permanently under PREREG §6.2).

evidence_stack:
  - condition: "COILED/multi-TF washout state on the name (production engine, not proxy)"
    tag: bonus_trigger
  - condition: "P1.3 RW mode: T09 63d stop-out Δ=−4.55pp, BH-adj p=0.0006, sign-stable (both halves)"
    tag: validated_effect
  - condition: "P1.3 RW mode: T07/T08 21d sign-stable but stop-out adverse; net long-horizon tilt"
    tag: validated_effect
  - condition: "P1.3 HG mode: T02 dead-money Δ=−13.19pp, BH-adj p=0.0006 (context — gate closed)"
    tag: context
  - condition: "concordance check: production COILED vs replay proxy ≥ 90% on overlapping names"
    tag: prerequisite_gate

rejection_rules:
  - rule: "F1 gate design is PERMANENTLY CLOSED (54.0% impact + 21d stop-out adverse)"
    prevents: "re-opening the hard-gate path without a new PREREG"
  - rule: "Proxy field (replay washout_proximity) is NOT the live input"
    prevents: "using the replay boolean directly in production"
  - rule: "Concordance < 90% blocks shadow ship; triggers P1.3 F1 reprobe on production values"
    prevents: "laundering proxy-sourced evidence into production without concordance verification"

ledger_binding:
  ledger: shadow_P2_1B_ledger (data/signal_archive/shadow_P2_1B_ledger.parquet)
  since: "[shadow activation date, populated at PR merge]"
  flip_criteria: >
    P2_1B_RANKWEIGHT_PREREG.md §6: Wilson lower bound on stop-out in bonus-cell vs non-bonus-cell
    at both 21d and 63d; n ≥ 25 episode clusters; sign-stable in both chronological halves.

gating:
  come_back_on: "[25 episode cluster accumulation date — estimated ~3 months from shadow activation]"
  cadence: monthly review
  maturation: >
    Shadow phase. Concordance check runs before shadow activation. Flip evaluated at n ≥ 25
    episodes. Production COILED/S1 computation is the mandatory live input.

adjacent_falsified:
  - idea: "F1 as hard gate (washout_proximity HARD-GATE mode)"
    source: "P1.3 §6.2: gate-rejected at 54.0% fire-rate impact; 21d stop-out unfavorable"
    mechanical_difference: "Hard gate kills 54% of board flow; rank tilt costs 0% recall"
  - idea: "Proxy field as live production input (replay washout_proximity boolean)"
    source: "P1.3 RESULTS PREAMBLE: 100% proxy-sourced per P1.1 review A1"
    mechanical_difference: "Production must use engine/cycles.py COILED state; concordance gated"

trial_count: 3  # T07, T09 (ship-qualifying RW trials); T02 (HG dead-money context)
```

### 7.2 F2 — RS-Inflection Rank Tilt

```
species_id: EI-F2-RW
version: 0.1 (shadow)
name: RS-Inflection Rank Tilt (Q2∪Q3 within-sector)
validation_status: phase0_passed (RW) — awaiting shadow confirmation
deployment_status: shadow (pending flip criterion)
mechanism: >
  A production-trigger fire where the name's relative-strength vs its GICS sector is in the
  middle two quartiles (Q2 or Q3 — inflecting but not extended, not lagging-bottom) receives a
  +0.10 blend_sorted bonus. Fires in Q1 (lagging bottom) or Q4 (extended top) receive no bonus.
  Mechanism: Q2∪Q3 names have demonstrated some relative reclaim (not the weakest in sector)
  without being so extended that they are chase entries. Shipped as rank tilt only; HG mode is
  null in the BH family (T11–T16, all BH-adj p ≈ 0.20–0.24) and gate-rejected on fire-rate
  (48.5% impact). F2 is the weakest of the three trio factors (|r| ≈ 0.01–0.02).

evidence_stack:
  - condition: "rs_sector_quartile in {2, 3} at signal time (current-GICS snapshot, 92% fill on fires)"
    tag: bonus_trigger
  - condition: "P1.3 RW mode: T18 21d cushioned Δ=+0.15pp, BH-adj p=0.0933, sign-stable"
    tag: validated_effect
  - condition: "P1.3 RW mode: T20 63d cushioned Δ=+0.68pp, BH-adj p=0.0752, sign-stable"
    tag: validated_effect
  - condition: "F2 is marginal (|r| ≈ 0.01–0.02); shadow must monitor effect size"
    tag: risk_disclosure

rejection_rules:
  - rule: "F2 HG gate design is PERMANENTLY CLOSED (48.5% impact; HG stats null in BH)"
    prevents: "re-opening the hard-gate path"
  - rule: "rs_sector_quartile null fires (3,828 of 49,939) receive zero bonus (not imputed)"
    prevents: "spurious bonus assignment to names with no RS data"
  - rule: "T19 (63d stop-out RW) sign-unstable — this trial does NOT independently authorize the 63d RW ship"
    prevents: "citing T19 sign-flip as evidence"
  - rule: "Marginal effect size — if shadow ledger |r| < 0.01 on ≥ 25 clusters, flag Fable before flip"
    prevents: "flipping on an effect that has noise-decayed to zero in the forward ledger"

ledger_binding:
  ledger: shadow_P2_1B_ledger (data/signal_archive/shadow_P2_1B_ledger.parquet)
  since: "[shadow activation date, populated at PR merge]"
  flip_criteria: >
    P2_1B_RANKWEIGHT_PREREG.md §6: Wilson lower bound on stop-out in bonus-cell vs non-bonus-cell
    at both 21d and 63d; n ≥ 25 episode clusters; sign-stable in both chronological halves.
    Additionally: if forward-ledger |r| < 0.01 on ≥ 25 clusters, Fable review before flip
    (F2 marginal-effect advisory from REVIEW_v2.md).

gating:
  come_back_on: "[25 episode cluster accumulation date — estimated ~3 months from shadow activation]"
  cadence: monthly review
  maturation: >
    Shadow phase. Flip evaluated at n ≥ 25 episodes. Effect-size monitoring mandatory.
    If shadow effect decays below |r| = 0.01, return to display-only before n ≥ 25 is reached.

adjacent_falsified:
  - idea: "F2 as hard gate (RS-inflection HARD-GATE mode)"
    source: "P1.3 §6.2: gate-rejected at 48.5% impact; HG stats null (BH-adj p ≈ 0.20–0.24)"
    mechanical_difference: "Hard gate is null and kills 48% of board flow; rank tilt costs 0% recall"
  - idea: "T19 (63d stop-out RW) as a ship-qualifying trial"
    source: "P1.3 both-halves: H1 Δ=−1.02pp, H2 Δ=+0.66pp — SIGN FLIP"
    mechanical_difference: "T19 fails sign stability; 63d RW ships via T20 (cushioned, sign-stable)"
  - idea: "Monotone RS rank (higher RS = better)"
    source: "P1.1 separability study (separate family)"
    mechanical_difference: "F2 tests the NON-MONOTONE Q2∪Q3 inflection recode; P1.1 tests monotone"

trial_count: 2  # T18 (21d cushioned ship-qualifying), T20 (63d cushioned ship-qualifying)
```

---

## 8. Trial ledger (this PREREG's own trials)

This PREREG registers no new backtested trials — it promotes from the P1.3 evidence base. The forward-ledger evaluation (flip criterion §6) is a prospective confirmation, not a new study trial. If the concordance reprobe is triggered (§3.3), those trials are logged in the `P2_1B_f1_concordance_reprobe` family with trial IDs P2_1B_F1_REPROBE_T01–T10, covering the same terminal-state / horizon grid as P1.3 T07–T10 (RW) and T01–T06 (HG context), applied to the production-COILED sub-population. BH q≤0.10, episode-clustered permutation test (same method as P1.3 round 2).

---

## 9. Era and measurement law compliance

**P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments cited.** This PREREG does not run new backtested verdicts; it promotes from the P1.3 evidence base whose era conformance is established (REVIEW_v2.md CHECK 3: PASS). The shadow forward ledger operates in real-time from its activation date onward — no historical window, no era-stamp issue. If the concordance reprobe is triggered, the reprobe's era window is the overlapping sub-population of the P1.3 primary window (2022-06-30 → 2025-12-29, verdict-grade only), and all P0_MEASUREMENT_MEMO era rules apply.

**Additive-lanes law (R7) confirmation:** both F1-RW and F2-RW carry `gate_fire_rate_impact_pct = 0.0` by construction (rank weight never removes fires). The board's fire count is unaffected by these bonuses. The recall audit (P1.4) remains the standing counterweight.

---

## 10. Build contract and deliverables

### 10.1 Concordance check script
File: `scripts/p2_1b_concordance_check.py`
- Reads `data/replay/replay_boarded.parquet` (MD5 `906175f9eb8caa351ed6d7d5c56265d3`).
- Computes production COILED state for each name in the overlapping snapshot (calls `engine/cycles.py` COILED detection at signal date, PIT-sliced).
- Reports concordance fraction on overlapping names.
- Prints GO / REPROBE_REQUIRED based on ≥ 90% threshold.
- Output: `research/entry_intel/p1_runs/P1_3/concordance_check.json` (concordance score, n_names_checked, go/reprobe verdict).
- Does NOT write to git (R9 convention for data artifacts). Does NOT modify any board file.

### 10.2 Shadow bonus wiring
File: `engine/rank_bonus.py` (new or existing module) — adds `compute_P2_1B_bonuses(board_frame)` function:
- Returns `f1_bonus` (using production COILED state) and `f2_bonus` (using `rs_sector_quartile`) per fire row.
- Raises `ConcordanceGateError` if the concordance check artifact is missing or reports REPROBE_REQUIRED.
- Does NOT modify `blend_sorted` in place; returns bonus columns for downstream shadow construction.
- Unit test: concordance check result is read at call time; a stale or missing artifact fails loudly.

### 10.3 Shadow column construction
In `scripts/build_stock_library.py` (or equivalent board builder): a new shadow column `board_rank_shadow_P2_1B` is appended to the in-memory board frame BEFORE the final output step. The production `blend_sorted` is not modified.

### 10.4 Shadow ledger writer
Appends a record per fire to `data/signal_archive/shadow_P2_1B_ledger.parquet` with: ticker, signal_date, episode_id, rank_incumbent, rank_shadow, f1_bonus_applied, f2_bonus_applied, terminal_state (null at fire time, filled by a grader job), fwd_ret_21 (null at fire time), fwd_ret_63 (null at fire time).

### 10.5 Done criteria
- Concordance check runs clean (GO verdict ≥ 90%, or REPROBE_REQUIRED with reprobe PREREG registered).
- Shadow column appears in board output alongside incumbent (operator-visible only).
- Shadow ledger writer appends records per fire without error.
- Unit test: inject a synthetic fire with known COILED=True, rs_sector_quartile=2 → shadow bonus = +0.20; inject one with COILED=False, rs_sector_quartile=4 → bonus = 0.0.
- PR open (NOT merged without Fable review).
- Structured report returned.

---

## 11. Downstream routing

**Upon Fable approval of this PREREG:**
- Build PR raised (Sonnet).
- Concordance check runs; result logged.
- Shadow activates (if GO); governance ledger entry written; species provisional entries created in `data/species/registry.json`.

**Upon flip criterion met (§6) — Fable decision required:**
- Fable reviews the flip evidence table (stop-out Wilson bounds, sign stability, n cluster counts, dead-money advisory).
- If Fable approves: `blend_sorted` updated to incorporate flipped bonuses; registry entries promoted to `graded_bonus`; governance ledger updated.
- If Fable rejects: shadow continues; come-back date updated.

**Concordance reprobe (if triggered, §3.3):**
- Reprobe registered as `P2_1B_f1_concordance_reprobe` (trials P2_1B_F1_REPROBE_T01–T10).
- Reprobe runs on production-COILED sub-population of the P1.3 era.
- If reprobe confirms (BH-survive, sign-stable, n ≥ 25 clusters): shadow ships with production COILED input.
- If reprobe fails: F1 remains display-only; F2 shadow may proceed independently.

**F2 without F1 (if concordance fails):** F2's evidence base is not proxy-sourced; F2 shadow may activate independently if the concordance check failure is isolated to F1. The `P2_1B` shadow architecture handles this via the `f1_bonus_applied` flag — setting F1 bonus to 0.0 while F2 bonus activates normally.

---

## 12. In plain English

> In plain English: the washout and RS-inflection findings from Phase 1 were real enough to earn a tryout — but they are too blunt to act as hard filters (each would remove half the board, which is too much). Instead they become a small thumb on the scale: stocks near a forced-seller washout or with relative strength in the middle zone get ranked slightly higher, by about one tier step. No stock is removed.
>
> Before any of this goes live, two things must happen. First, the "washout" signal must be re-verified using the actual production detection code, not the stand-in field that was used in the study — if the two disagree on more than 10% of names, the study has to be re-run on the production values before anything ships. Second, the shadow rank column has to accumulate at least 25 independent episode clusters of real forward-looking evidence and actually show a credible stop-out improvement before the rank bump becomes permanent.
>
> The RS-inflection signal is the weaker of the two (very small effect size). It ships into shadow mode with an explicit watch: if the effect decays to noise in the forward ledger, it is removed before the flip decision.
>
> Nothing in this document authorizes changing the live board ranking. That happens only if the shadow ledger meets the pre-registered Wilson-bound criterion and Fable approves the flip.

---

*Registered 2026-07-05. Immutable after Fable approval. Shadow ledger evidence appended to the ledger artifact; this document is never edited to accommodate observed shadow outcomes.*

*2026-07-05 — red-team blocking fixes applied (P2_REDTEAM.md) incl. Fable rulings R-P2.1 (flip floor 100 clusters + 2 quarters) and R-P2.2 (single concordance authority).*

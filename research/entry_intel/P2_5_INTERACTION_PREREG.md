# P2.5 — Washout Depth × Interaction Study PREREG

**STATUS: APPROVED — Fable 2026-07-05, conditional on P2_5_REDTEAM.md edits (this revision); run authorized on ei-p2-5-study workflow.**

**Study:** P2.5 Washout Depth/Interaction — depth-stratified rank-weight configs using the production COILED washout signal.
**Program:** Entry Intelligence (EI). **Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §6`.
**Registered:** 2026-07-05 (before any run; diagnostic in-sample results are sealed by this registration).
**Author:** Sonnet subagent under Fable orchestration.
**Provenance:** F1 Reprobe `P2_1B_F1_REPROBE/RESULTS.md` (PROMOTION_DIES_PROXY_ONLY verdict, 2026-07-05) + P2_5 Diagnostic `p1_runs/P2_5_DIAGNOSTIC/RESULTS.md` (IN-SAMPLE, 2026-07-05).
**Replay MD5:** `906175f9eb8caa351ed6d7d5c56265d3` (matches reprobe artifact; must be confirmed again at run time).

**Constitutional gates binding on this PREREG:**
- R4: RW mode only — hard-gate paths stay closed per P1.3 §6.2; no gate-ification without a new PREREG.
- R6: any board-ordering influence requires shadow-first with pre-registered flip criterion.
- R7: additive-lanes law — rank weight raises quality labels UP; never filters the board toward zero rows.
- R8: no execution before Fable approval of this PREREG.
- Species constitution (Setup Species Masterplan §1): PREREG before run; capped config grid; any post-hoc variation = new recorded trial; BH q≤0.10; both-halves sign stability; episode-clustered n floors; fills strictly after signal bar.
- P0_MEASUREMENT_MEMO.md v1.1 §6 era law: primary window 2022-06-30 → 2026-07-02; survivor_bias=false rows only for verdict-grade statistics.

---

## 0. In plain English

> The F1 reprobe (P2_1B_F1_REPROBE) found that the production washout signal — as a flat binary flag — is not a favorable rank-weight input at the 63-day horizon. The moved-up cohort was stopped out +3.34 percentage points *more* often than the not-moved-up cohort, reversing the proxy's −4.55pp effect. The promotion was killed.
>
> But the diagnostic (P2_5_DIAGNOSTIC) revealed that the binary flag hides a strong gradient. Shallow washouts (stocks down 15–25% from their peak) are the most common (about 44% of all washout fires) and are the most harmful at 63 days (+1.96pp stop-out above baseline). Deep washouts (>40% drawdown) are rarer (~15% of washout fires) and are the most favorable at 63 days (−3.57pp stop-out vs baseline). The mechanism is simple: the fixed-percentage stop (8% at 21 days, 15% at 126 days) is not wide enough for a deep-washout name that needs more time to rebuild — so it stops out in the short term but resolves cleanly in the long term if the stop is wider.
>
> The combined signal — deep washout (>25% drawdown) filtered to names that also pass the anti-chase screen and show favorable relative strength — shows the largest favorable 63-day stop-out delta of any adequately-powered cell tested (−3.30pp, n=11,371 fires).
>
> This study asks: does that gradient hold up under pre-registered statistical testing, with both-halves sign stability and BH correction? If so, which depth tier and which combination earns a rank-weight tilt? If no combination passes, the washout-as-rank-input line is closed program-wide.
>
> One critical honesty point: the depth threshold (>25%) and the combination choices (deep-trio, below-200) were selected by looking at this same dataset. The protections against that are (a) episode-clustered permutation inference rather than formula p-values, (b) both-halves sign stability, (c) a pre-declared kill criterion if no combination survives, and (d) the acknowledgment that live shadow accrual and cross-market passports (CN/HK/CA phase-0s) are the only true out-of-sample confirmation. A pass here authorizes shadow rung only — never direct enforcement.

---

## 1. Study scope and population

**Population:** rows in `data/replay/replay_boarded.parquet` where `verdict == 'fire'` AND production washout is defined (2,757 `None`-washout rows excluded; `washout_proximity = None` → excluded per reprobe protocol). Valid defined-washout population: n=47,182 fires. Verdict-grade fires with `survivor_bias = false`: 49,939 total fires, 47,182 with washout defined.

**Era (primary window):** per `P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05)`, effective primary verdict window = **2022-06-30 → 2026-07-02** (250-bar Massive warmup; P0_MEASUREMENT_MEMO §6). Rows with `survivor_bias_stamp == True` are excluded from all primary verdict computations and routed to a labeled context appendix only (PRE-2022 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE). If `P0_MEASUREMENT_MEMO.md` is absent at execution time the study HALTS.

**§5 conformance checklist** (P0_MEASUREMENT_MEMO.md §5/§6):
- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05)` in preamble.
- [ ] Primary window = 2022-06-30 → 2026-07-02.
- [ ] Verdict-grade statistics on `survivor_bias = false` rows only.
- [ ] Confirms via per-row source stamp that unstamped rows are Massive-sourced.
- [ ] All pre-2022 rows stamped, routed to labeled context appendix, excluded from BH family, sign-stability, n-floors, and all GO/NO-GO decisions.
- [ ] `horizon_censored` rows excluded per-horizon, tracked separately.
- [ ] Mandatory stamp text printed with era census missing-fraction.
- [ ] Returns INSUFFICIENT-POWER (honest null) if unstamped n floor not met.

**Data source (strict):** `data/replay/replay_boarded.parquet` ONLY. No live price queries, no re-computation of signals. All features must be columns already frozen in the replay artifact. The depth feature `dd_pct` must be present as a replay column (drawdown from peak, PIT-frozen at signal time). If `dd_pct` is absent the study HALTS and returns a blocker report.

**Required replay columns (must exist before execution; halt if absent):**
- `ticker`, `signal_date`, `verdict`, `entry_date`, `entry_price`
- `washout_proximity` (production COILED binary, None-able)
- `dd_pct` (drawdown-from-peak at signal time, expressed as a positive fraction, e.g. 0.264 for 26.4% drawdown)
- `ext_z` (anti-chase proxy: extension z-score)
- `rs_vs_sector_quartile` (RS-vs-sector quartile, 1–4)
- `above_200dma` (bool: price ≥ 200DMA at signal time)
- `episode_cluster_id`
- `terminal_state` ∈ {stopped, dead_money, cushioned, clean_liftoff}
- `fwd_21d`, `fwd_63d` (forward returns)
- `survivor_bias_stamp` (bool)

**Episode-cluster n floor:** any verdict cell with fewer than 25 independent episode clusters (unique `episode_cluster_id` values) is labeled THIN and excluded from the registered grid entirely — not run and excused, but excluded before any computation. The diagnostic confirmed all registered cells exceed this floor (see §2.1).

---

## 2. Diagnostic provenance and the in-sample honesty clause

### 2.1 What the diagnostic found (sealed, not verdicts)

The P2_5_DIAGNOSTIC (RESULTS.md, 2026-07-05, labelled IN-SAMPLE throughout) found the following depth gradient on the full 47,182-fire defined-washout population:

**Depth gradient — stop-out delta vs unconditioned baseline (38.48% at 21d; 62.31% at 63d [ADVISORY A: corrected from 62.67% cited in diagnostic RESULTS.md — see correction note below]):**

| Bucket | n fires | n episodes | 21d stop-out delta (pp) | 63d stop-out delta (pp) | 21d dead-money delta (pp) |
|---|---|---|---|---|---|
| d15_25 (15–25% drawdown) | 16,326 | 7,305 | −1.44 | +1.96 | +4.08 |
| d25_40 (25–40%) | 14,710 | 6,362 | +1.59 | −1.27 | −7.43 |
| d40plus (>40%) | 5,698 | 2,503 | +6.94 | −3.57 | −14.09 |
| proxy-equiv (washout_proximity=True, n=21,099) | 21,099 | 8,765 | +1.58 | −3.06 | −7.04 |

Median washout fire = 26.4% drawdown (p50); the d15_25 bucket holds approximately 44% of all washout-True fires (p25=20.4%, p75=34.6%).

**Combination cells (all adequately powered, n≥1,000 episodes):**

| Cell | n fires | n episodes | 21d stop Δpp | 21d dead-money Δpp | 21d liftoff Δpp | 63d stop Δpp | 63d liftoff Δpp |
|---|---|---|---|---|---|---|---|
| trio (washout + ac_pass + rs_Q1Q2) | 20,146 | 8,882 | +0.02 | −2.93 | +3.18 | −1.10 | +2.11 |
| deep-trio (dd>25% + ac_pass + rs_Q1Q2) | 11,371 | 4,946 | +2.00 | −8.84 | +2.21 | −3.30 | +3.28 |
| washout_true_below_200 | 23,780 | 10,266 | +0.87 | −4.60 | — | −2.23 | — |
| d40plus solo | 5,698 | 2,503 | +6.94 | −14.09 | — | −3.57 | — |

F1 reprobe cross-reference (sealed, production values):
- T09 (RW 63d stop): production Δ = **+3.34pp** (unfavorable, sign-reversed from proxy's −4.55pp). BH-survive=Y, sign-stable=Y (unfavorable direction: H1 +1.92pp, H2 +4.99pp). Verdict: PROMOTION_DIES_PROXY_ONLY.
- T02 (HG 21d dead-money): production Δ = **−15.11pp** (favorable, stronger than proxy's −13.19pp). BH-survive=Y, sign-stable=Y (H1 −18.15pp, H2 −12.98pp). Context note: HG path permanently closed per P1.3 §6.2.

**[BLOCKING-1 annotation — sc63 bug in diagnostic; Fable 2026-07-05]**

The diagnostic's `sign_consistent()` function (`run_P2_5_diagnostic.py`, line ~470) computes 63-day sign-consistency by testing both halves' 63d stop-out rate against the **21d baseline (0.3848)** instead of the 63d baseline (0.6231). Because every cell's 63d stop-out rate (~0.53–0.66) lies above 0.3848 in both halves, `sc63` returns `True` mechanically for every cell. The `sc63=Y` labels in the diagnostic RESULTS.md ranking table are therefore NOT evidence of genuine 63d half-stability.

**Recomputed against the correct 63d baseline (0.6231):**

| Cell | H1 63d stop | H2 63d stop | H1 Δ vs 63d baseline | H2 Δ vs 63d baseline | Corrected sc63 |
|---|---|---|---|---|---|
| C6 deep-trio (deep_washout_ac_pass_rs_fav) | 0.5411 | 0.6321 | −8.2pp (favorable) | +0.9pp (unfavorable) | **False** |
| C5 trio (washout_ac_pass_rs_fav) | 0.5555 | 0.6634 | −6.8pp (favorable) | +4.0pp (unfavorable) | **False** |
| C3 below200 (washout_true_below_200) | 0.5416 | 0.6561 | −8.2pp (favorable) | +3.3pp (unfavorable) | **False** |
| proxy_equiv | 0.5287 | 0.6523 | −9.4pp (favorable) | +2.9pp (unfavorable) | **False** |
| **C2 d40plus** | **0.5928** | **0.5824** | **−3.0pp (favorable)** | **−4.1pp (favorable)** | **True** |

**Only C2 (d40plus) is genuinely 63d sign-stable pre-registration** (both halves favorable vs the 63d baseline: H1 −3.0pp, H2 −4.1pp). **C3 (below200), C5 (trio), and C6 (deep-trio) have explicitly uncertain 63d half-stability**: their H1 effects are strongly favorable but H2 reverses sign. These three configs remain registered as genuine open hypotheses — the §5.2 gate (once correctly specified per BLOCKING-2 below) will settle their half-stability at run time. C2 (d40plus) is named the **lead hypothesis** for 63d half-stability. The phrase "the deep-trio... sign-consistent 63d (Y)" from the diagnostic narrative must not be read as a pre-registered finding; it reflects the bugged `sc63` computation.

### 2.2 The in-sample honesty clause (mandatory §)

**The depth threshold (>25% drawdown as the deep/shallow split) and the eight grid configs below were selected by examining the same 47,182-fire panel used in the diagnostic.** This is not pretend-prospective pre-registration. It is genuine post-diagnostic registration.

Protections declared and binding:

1. **Episode-clustered permutation inference** — the primary p-value for every trial is generated by `run_P1_3_v2.py`'s calibrated episode-label-permutation machinery (N_PERM=5,000, Phipson-Smyth +1 correction, two-sided), reused verbatim. Parametric p-values are secondary diagnostics only.

2. **Both calibration controls must be run before the grid** (mandatory, same requirement as reprobe):
   - Negative control: ≥200 permuted-label draws on the washout_proximity encoding; rejection rate must be ≤0.12; KS-uniformity p must be large (≥0.05). Grid is invalid without this passing.
   - Positive control: inject a +0.05 shift to the forward-return distribution; perm_p must be ≪0.05 (reject the null cleanly). Grid is invalid without this passing.

3. **Both-halves sign stability** — the primary era is split at its midpoint by date. Every trial is computed independently on each half. A trial that survives BH but shows opposite signs in H1 and H2 is labeled UNSTABLE and cannot promote.

4. **Kill criterion §6** — if no config produces a favorable-direction, BH-surviving, sign-stable stop-out effect at either horizon, the washout-as-rank-input line is **CLOSED program-wide** (binary AND conditioned). A dead-money-only benefit in a cell that has unfavorable or null stop-out at both horizons does not rescue the line.

5. **Live shadow + cross-market passports are the true OOS** — a pass here authorizes SHADOW rung only. Shadow forward ledger (pre-registered flip criterion at §5) and CN/HK/CA phase-0 cross-market passports are the only out-of-sample tests. No live enforcement before the flip criterion fires on the forward ledger.

6. **No data mining exemption** — any variation beyond the 8 × 2 grid declared in §3 is a new recorded trial (new trial_id prefix, new BH family, registered before run). Exploring a ninth config after observing results from the eight is not permitted within this family.

---

## 3. Registered config grid (RANK-WEIGHT MODE ONLY; hard-gate paths closed)

The following 8 configs are the complete registered grid. All are tested at both the 21d and 63d horizons (m = 16 total trials, declared exactly). No further configs may be added within this family.

**Config selection rationale (from diagnostic ranking, §2.1):** configs chosen by: (a) adequately-powered cells from the diagnostic (n≥1,000 episodes confirmed), (b) at least one directionally favorable signal at a 63d horizon, (c) mechanistic coherence with the reprobe's mechanism hypothesis (depth as discriminator, trend-broken vs intact-trend washout), (d) RW mode operationalizability. The d15_25 bucket (shallow washouts) is not registered as a standalone config: its 63d delta is unfavorable (+1.96pp) and it represents the harmful sub-population identified in the diagnostic.

**[BLOCKING-1 annotation — sc63 in diagnostic ranking does not carry into this rationale]** The diagnostic ranking table's `sc63=Y` labels (used to rank C6 deep-trio and others) are computed against the wrong baseline (see §2.1 BLOCKING-1 note). The rationale here relies on (a)–(d) above, not on `sc63`. For 63d half-stability, C2 (d40plus) is the only pre-registered config with confirmed favorable-direction halves; C3/C5/C6 are registered as genuinely open hypotheses whose half-stability is explicitly in doubt and will be adjudicated by the §5.2 gate at run time.

**Rank-weight bonus design (ALL configs — not hard gates, additive blend_sorted tilt):**
- **Solo configs (C1–C3):** bonus = +0.10 fractional rank points for fires in the cell; zero otherwise. Pre-registered magnitude; no search across values.
- **Interaction configs (C4–C8):** bonus = +0.10 fractional rank points for fires satisfying all interaction conditions; zero otherwise. Conditions are AND-combined (all must hold); no partial credit.
- Rank bonus is applied within-day on the `blend_sorted` 0..1 scale (same normalization as P1.3 §3/Mode-B). The formula is logged in the run preamble before any computation.
- **Moved-up vs not-moved-up comparison** (Mode-B construction per P1.3 §3): within each calendar day, apply the bonus and re-rank. "Moved up" = rank improved by ≥1 position within day. Terminal-state distribution compared between moved-up and not-moved-up groups.

### Config table

| Config ID | Name | Condition for bonus | Diagnostic n fires | Diagnostic n episodes | Diagnostic 63d stop Δpp | Power status |
|---|---|---|---|---|---|---|
| C1 | deep_washout_solo | dd_pct > 0.25 AND washout_proximity=True | 20,408 | ~8,865 | −2.34 (estimate, non-reconstructable; computed fresh at run time — fire-weighted blend of d25_40 + d40plus components gives −1.92pp) | PASS |
| C2 | d40plus_solo | dd_pct > 0.40 AND washout_proximity=True | 5,698 | 2,503 | −3.57 | PASS |
| C3 | below200_washout | washout_proximity=True AND above_200dma=False | 23,780 | 10,266 | −2.23 | PASS |
| C4 | washout_ac_pass | washout_proximity=True AND ext_z ≤ 2.0 | 35,079 | 15,431 | −0.50 | PASS |
| C5 | trio (washout × ac_pass × rs_fav) | washout_proximity=True AND ext_z ≤ 2.0 AND rs_vs_sector_quartile IN (1,2) | 20,146 | 8,882 | −1.10 | PASS |
| C6 | deep_trio (dd>25% × ac_pass × rs_fav) | dd_pct > 0.25 AND washout_proximity=True AND ext_z ≤ 2.0 AND rs_vs_sector_quartile IN (1,2) | 11,371 | 4,946 | −3.30 | PASS |
| C7 | d40plus_trio (dd>40% × ac_pass × rs_fav) | dd_pct > 0.40 AND washout_proximity=True AND ext_z ≤ 2.0 AND rs_vs_sector_quartile IN (1,2) | ~3,100 | ~1,380 | directional (see note) | CHECK AT RUN |
| C8 | below200_deep (below_200 × dd>25%) | washout_proximity=True AND above_200dma=False AND dd_pct > 0.25 | ~15,800 | ~6,900 | directional (see note) | CHECK AT RUN |

**C7 and C8 power notes:** the diagnostic did not report C7 and C8 as named cells; the episode counts above are estimated from the component cells. At run start, the runner MUST compute episode counts for C7 and C8 and compare against the 25-cluster floor. If either cell is THIN (n_episodes < 25), it is excluded from the registered grid before the permutation machinery runs. The BH m is decremented accordingly (to m=14 or m=12 if one or both are thin), and the adjusted m is logged in the preamble before any computation. If both are thin, m=12 (C1–C6 × 2 horizons).

**[ADVISORY F — Fable ruling 2026-07-05]** C7 and C8 occupy 4 of the 16 family degrees of freedom on directional guesses (estimated episode counts, not diagnostic-confirmed effects). This estimated-slot risk is **accepted** under the thin-check-at-run-start decrement rule above: the slots will either pass the n_episode floor and earn their BH family positions, or be excused before computation with m decremented accordingly. No additional guard is required; the thin-check mechanism is adequate.

**Definition of rs_fav:** `rs_vs_sector_quartile IN (1, 2)` — top two quartiles of RS vs sector at signal time. This is the Q1/Q2 definition from the diagnostic partition (c2), where Q1Q2 produced 63d stop Δ = −1.10pp vs Q3Q4 = +0.91pp.

**Definition of ac_pass:** `ext_z ≤ 2.0` — not price-extended above 2 z-scores (inherited from P1.3 F3 / P2.1a threshold; registered fallback: if `ext_z` is absent but an equivalent extension column is present, the runner resolves by name mapping logged before computation).

---

## 4. Trial ledger (capped; family `P2_5_depth_interaction`)

One BH family, m declared exactly. The following trials constitute the complete family. Any variation explored after observing data = new recorded trial in `engine/trial_ledger` with a new trial_id prefix, never within this family.

**Primary terminal state for each trial: stop-out** (favorable direction = moved-up has LOWER stop-out than not-moved-up). Dead-money and liftoff are secondary context outputs, not BH-family members, per the ship-qualifying criterion §6.

| trial_id | config | horizon | primary target | BH family slot |
|---|---|---|---|---|
| P25_T01 | C1 (deep_washout_solo) | 21d | stop-out | yes |
| P25_T02 | C1 (deep_washout_solo) | 63d | stop-out | yes |
| P25_T03 | C2 (d40plus_solo) | 21d | stop-out | yes |
| P25_T04 | C2 (d40plus_solo) | 63d | stop-out | yes |
| P25_T05 | C3 (below200_washout) | 21d | stop-out | yes |
| P25_T06 | C3 (below200_washout) | 63d | stop-out | yes |
| P25_T07 | C4 (washout_ac_pass) | 21d | stop-out | yes |
| P25_T08 | C4 (washout_ac_pass) | 63d | stop-out | yes |
| P25_T09 | C5 (trio) | 21d | stop-out | yes |
| P25_T10 | C5 (trio) | 63d | stop-out | yes |
| P25_T11 | C6 (deep_trio) | 21d | stop-out | yes |
| P25_T12 | C6 (deep_trio) | 63d | stop-out | yes |
| P25_T13 | C7 (d40plus_trio) | 21d | stop-out | yes (if n_ep≥25) |
| P25_T14 | C7 (d40plus_trio) | 63d | stop-out | yes (if n_ep≥25) |
| P25_T15 | C8 (below200_deep) | 21d | stop-out | yes (if n_ep≥25) |
| P25_T16 | C8 (below200_deep) | 63d | stop-out | yes (if n_ep≥25) |

**m = 16 (full grid) or m = 14 (one thin cell excluded) or m = 12 (both C7/C8 thin) — declared at run start from n_episode check; logged in preamble.** BH correction applied across all m simultaneously at q≤0.10.

**Dead-money and clean-liftoff outputs (context only, not BH-family):** computed and printed per trial as descriptive complements to the primary stop-out test. These are the secondary outputs from the diagnostic: dead-money Δpp and liftoff Δpp at both horizons. They are not counted in m; they do not enter the BH correction; they cannot rescue a trial that fails on stop-out; they can only add color to a trial that passes on stop-out.

---

## 5. Primary verdict statistics (exact, frozen)

### 5.1 Terminal-state delta (primary)

For each trial P25_Txx:
- **Statistic:** delta in stopped-out incidence rate between moved-up group and not-moved-up group, expressed in percentage points (pp). Δ = stopped_rate(moved_up) − stopped_rate(not_moved_up).
- **Favorable direction:** Δ < 0 (moved-up fires are stopped out LESS often).
- **Test:** Mann-Whitney U on the continuous `fwd_{h}d` forward return distribution (moved-up vs not-moved-up). This is the same MWU test as `run_P1_3_v2.py` — reuse verbatim.
- **Episode-cluster bootstrap:** resample `episode_cluster_id` with replacement, N_PERM=5,000. Phipson-Smyth +1 correction, two-sided. The bootstrap p-value is the primary p-value fed into BH.
- **Effect size:** rank-biserial correlation r (from Mann-Whitney U) printed alongside each p-value.
- **BH correction:** q=0.10 across all m trials simultaneously.

### 5.2 Both-halves sign stability

Split the primary era at its calendar midpoint by date. Each trial computed independently on H1 and H2. Sign stability = Δ(H1) and Δ(H2) have the same sign (both negative = favorable, or both positive = unfavorable). A trial that survives BH but fails sign stability is labeled UNSTABLE and cannot promote.

**[BLOCKING-2 — pinned convention; Fable 2026-07-05]**

The half-delta convention is pinned explicitly as follows: **per-half Δ = stop_out(moved_up) − stop_out(not_moved_up) computed within that half, no external baseline.** This is the baseline-free within-half contrast that matches §5.1's primary statistic (Mode-B moved-up vs not-moved-up). The sign of this Δ is determined entirely by the two within-half groups; no full-population or cross-horizon baseline is used or needed. This convention forecloses the diagnostic's error (where `sign_consistent()` tested both halves' 63d stop-out against the 21d full-population baseline, causing `sc63` to be mechanically True for all cells).

**Mandatory run-preamble assertion (execution halts if this fails):** before any trial in the grid executes, the runner MUST emit and verify the following assertion in the preamble log:

```
ASSERT sign_stability_convention:
  - half_delta = stop_out(moved_up_in_half) - stop_out(not_moved_up_in_half)
  - horizon: horizon-matched to the trial's own horizon (21d for 21d trials, 63d for 63d trials)
  - baseline: NONE — within-half group contrast only
  - verification: H1 and H2 deltas computed independently with no shared full-population rate
  If any external baseline is used in sign_consistent(), HALT with error: SIGN_STABILITY_BASELINE_ERROR
```

If the assertion cannot be verified (e.g., because the sign-stability function inherits `cell_report`/`sign_consistent` verbatim from the diagnostic without modification), the grid is INVALID and the run HALTS before any permutation computation.

### 5.3 Dead-money co-benefit requirement (ship-qualifying, §6.3)

A trial that survives BH + sign-stable on stop-out MUST also show dead-money Δ ≤ 0 at the same horizon in the same cell (the dead-money effect from the reprobe's T02 must not be reversed). If stop-out passes but dead-money *increases* (Δ > 0 at both horizons), the config cannot promote — it has traded one harm for another. Dead-money Δ is reported for every trial as a secondary output and checked post-hoc against this criterion.

**[ADVISORY E — Fable ruling 2026-07-05]** The **binding dead-money co-benefit check is the 21d dead-money Δ** (dead-money Δ at 63d is ~0.08% for all cells in the diagnostic — see results.json — making the 63d check vacuous: a near-zero 63d dead-money rate satisfies Δ≤0 trivially). Ship-qualifying requires **21d dead-money Δ ≤ 0** regardless of which horizon the stop-out effect passes at. The 63d dead-money check is retained as a reported secondary output but cannot be the sole dead-money gate. A config that shows favorable 63d stop-out but adverse 21d dead-money (Δ > 0 at 21d) cannot promote.

### 5.4 Fire-rate impact table (mandatory, R7)

For each config C1–C8:
- `n_fires_total`: total defined-washout fires in primary era.
- `n_in_bonus_cell`: fires that would receive the rank bonus.
- `bonus_cell_pct`: n_in_bonus_cell / n_fires_total as a percentage.
- `n_ep_bonus_cell`: episode clusters in the bonus cell (THIN check).
- `n_ep_not_moved_up`: episode clusters in the not-moved-up group (must be ≥25).

This table is printed regardless of study outcome. RW mode does not remove fires from the board (R7 additive-lanes law). `gate_fire_rate_impact_pct = 0.0` for all configs by construction.

---

## 6. Kill and ship criteria (checked in order after BH)

### 6.1 What kills individual configs

A config (C1–C8) is marked DEAD if ANY of the following hold:
- No trial for that config (at either horizon) has BH-adj p ≤ 0.10 in the favorable direction (stop-out Δ < 0).
- The one surviving trial(s) fail both-halves sign stability (UNSTABLE).
- The cell is THIN (n_episodes < 25 — excluded before run per §3).

### 6.2 Whole-study kill (program-wide closure)

**If no config (C1–C8) produces a favorable-direction, BH-surviving, sign-stable stop-out effect at either horizon, the washout-as-rank-input line is CLOSED program-wide (binary AND conditioned).** This is the kill criterion binding from P2.1B §3.3 (reprobe path). Specifically:

- The `washout_proximity` boolean may not be used as a rank-weight input in any form, at any depth cut or interaction, without a new PREREG starting from new data (e.g., a future cross-market passport that introduces genuinely out-of-sample fires).
- The dead-money-context clade note survives: the reprobe's T02 finding (−15.11pp dead-money in HG context) is recorded as a display-only context note. It does not authorize any rank or gate influence because the HG path is permanently closed (P1.3 §6.2) and the dead-money benefit at 21d does not address the stop-out reversal at 63d.
- F2 (RS-inflection) is unaffected by this kill — F2's evidence base is not washout-sourced.

### 6.3 What ships (positive criterion)

A config earns the right to proceed to shadow deployment if ALL of the following hold:
1. At least one of P25_T{2k-1} or P25_T{2k} (the two horizon trials for that config) has BH-adj p ≤ 0.10 for stop-out Δ in the favorable direction.
2. Both-halves sign-stable on the surviving trial(s).
3. n_episodes ≥ 25 in the moved-up group (not THIN).
4. Dead-money Δ ≤ 0 at the surviving horizon in the same cell (no harm trade).

**Ship design:** the surviving config ships as a rank-weight bonus (additive tilt on `blend_sorted` 0..1 scale, +0.10 magnitude, logged formula). If multiple configs survive, Fable selects the one to shadow-deploy first (preference: the narrowest condition set that survives, to minimize interaction complexity).

**If two configs that share a subset relationship both survive** (e.g. C6 deep-trio and C1 deep-washout-solo both pass), Fable decides whether to combine them or deploy only the narrower one. This study does not authorize automatic combination.

---

## 7. Calibration-control requirement (blocking)

Both controls must pass before the grid runs. Results logged in the run preamble. Grid is declared INVALID if either fails.

### 7.1 Negative calibration control

200 permuted-label draws on the production `washout_proximity` encoding (same machinery as reprobe):
- Rejection rate at α=0.05: must be ≤0.12.
- p-value mean / median: must be near 0.5 (within 0.1).
- KS-uniformity p: must be ≥0.05.
- Sanity gate (param/perm divergence, the P1.3 round-1 defect signature): must not trip.

Reference: reprobe calibration control passed with rej rate=0.085, KS p=0.458 (200 draws, seed 777); reviewer seed=9999, 60 draws: rej=0.067, KS-p=0.876.

### 7.2 Positive calibration control

Inject a +0.05 shift to the forward-return distribution; the permutation test must reject (perm_p ≪ 0.05). Reference: reprobe positive control perm_p=2.0e-4. This confirms the instrument has power to detect the magnitudes of interest.

---

## 8. Species registry entry (on pass)

If any config ships per §6.3, a new species registry entry is created:

**Registry ID:** `EI-F1D-RW` (Entry Intelligence — F1 Depth — Rank Weight)

**Entry fields:**
- `species_id`: EI-F1D-RW
- `family`: entry_intelligence
- `factor`: washout_depth_rank_weight
- `config`: the surviving config ID from C1–C8 (e.g., EI-F1D-RW-C6 for deep-trio)
- `validation_status`: shadow (promoted from phase-0 on pass; not yet live)
- `evidence_source`: P2_5_depth_interaction study (this PREREG), P2_5_DIAGNOSTIC (in-sample), P2_1B_F1_REPROBE (production-values reprobe)
- `activation_condition`: `dd_pct > {threshold}` AND `washout_proximity=True` AND [any additional interaction conditions from the surviving config]
- `rank_mechanism`: additive bonus +0.10 on `blend_sorted` 0..1 scale, within-day normalization
- `safety_net_axes`: stop-out (primary, favorable: Δ<0), dead-money (co-benefit required: Δ≤0)
- `flip_criterion`: mirrors P2.1b §6.2's `D_f` machinery — corrected for production values:
  - Shadow flip condition: after ≥25 independent episode clusters have accrued in the forward ledger, Wilson_upper(D_f) < 0, where D_f = stop_out(moved_up) − stop_out(not_moved_up) in the forward ledger. `Wilson_upper` at z=1.645 (one-sided 95% upper bound on the effect). If Wilson_upper(D_f) ≥ 0 at n=25 clusters, the shadow is falsified and the species entry transitions to `falsified`.
  - Flip requires BOTH: Wilson_upper(D_f) < 0 AND the forward ledger covers ≥2 calendar quarters of shadow accrual.
  - Fable approval required before any live board influence (R6 shadow period).
- `shadow_falsification_signature`: production D_f ≥ +3.34pp at 63d (the reprobe's unfavorable T09 value) in the forward ledger = falsification. Any single-quarter snapshot showing D_f > +3.34pp at 63d triggers an immediate Fable review.
- `cross_market_passport`: CN/HK/CA phase-0 studies are the out-of-sample confirmation path; they run independently under their own PREREGs and do not alter this entry's flip criterion.

---

## 9. Downstream routing

**If any config ships (§6.3):**
- Create species registry entry per §8.
- Open shadow rank column in the board pipeline using the surviving config's condition.
- Forward ledger begins accruing episode clusters immediately.
- Shadow track-record report filed at 25 clusters and at 50 clusters.
- Species registry transitions to `validated` only after forward-ledger flip criterion fires AND Fable approves.
- CN/HK/CA cross-market passports are independent PREREGs; they do not inherit this entry automatically.

**If whole-study kill (§6.2):**
- Registry: all EI-F1D-RW entries (if any were opened in shadow) close as `falsified`.
- §8 masterplan entry: washout-as-rank-input line closed; washout factors remain display-only indefinitely.
- Dead-money context note (T02 reprobe: −15.11pp, HG, production) is preserved in the display layer as a context annotation; it does not authorize rank or gate power.
- F2 (RS-inflection, P2.1b) and F3 (anti-chase gate, P2.1a) are unaffected.

---

## 10. Report contract

Report file: `research/entry_intel/p1_runs/P2_5/RESULTS.md` (+ `results.json`)

Required sections (report fails gate if any are absent):
1. **Preamble:** exact artifact path + MD5, column-name mapping log, era table citation (P0_MEASUREMENT_MEMO version + date), n fires total, n fires with washout defined, n episode clusters, survivor-stamped row count, calibration control outcomes (both), m declared.
2. **Calibration controls table:** negative control (rejection rate, KS p, sanity gate) and positive control (perm_p), both labeled PASS or FAIL.
3. **Per-config results table (all 8 configs × 2 horizons):** stop-out Δpp, raw perm_p, BH-adj p, effect size r, sign-stability flag (H1/H2 Δpp shown), n_episodes moved-up, THIN flag. Secondary: dead-money Δpp and liftoff Δpp (context, not BH).
4. **Fire-rate impact table** (all 8 configs — mandatory per R7 regardless of BH outcome).
5. **Both-halves sign stability table** (H1 and H2 stop-out Δpp for every surviving trial).
6. **Dead-money co-benefit check** (per §5.3 — printed for every trial that passes BH; explicit PASS/FAIL against Δ≤0 criterion).
7. **Verdict per config** (DEAD / SHIPS, with explicit BH threshold + sign-stability + dead-money citations).
8. **Whole-study verdict** (any config ships → proceed to shadow; all dead → washout line closed).
9. **In-sample honesty statement** (printed verbatim in the results: "depth threshold and config selection are in-sample-derived; out-of-sample confirmation is the forward ledger and cross-market passports only; this pass authorizes shadow rung only").
10. **Context appendix:** survivor-stamped rows (labeled PRE-2022 / SURVIVOR-STAMPED — CONTEXT ONLY); reprobe cross-reference (T09 +3.34pp production, T02 −15.11pp production — labeled as sealed prior-study numbers, not re-run here).
11. **Plain-English box** (one paragraph per plain-language law; accessible to a non-technical reader).
12. **Leak audit section:** fill rule confirmation (next-bar, not same-bar), feature freeze confirmation (PIT), era boundary, any survivor-bias bound re-statement.

---

## 11. Inherited rulings binding on this study

| Ruling | Application to P2.5 |
|---|---|
| R4 | RW mode only — hard-gate paths stay closed per P1.3 §6.2; C1–C8 are all rank-weight conditions |
| R6 | Shadow-first with pre-registered flip criterion (§8); no live board influence until forward-ledger criterion fires and Fable approves |
| R7 | Additive-lanes law — rank bonus never removes fires; fire-rate impact table is mandatory regardless of outcome |
| R8 | No execution before this PREREG is approved by Fable |
| R9 | Replay outputs live in `data/replay/`; this study reads only, never writes new replay rows |
| Species §1 | PREREG before run; capped grid (8 configs declared); post-hoc variation = new trial_id; BH q≤0.10; both-halves stability; episode-cluster n floors; fills strictly after signal bar |
| P0_MEASUREMENT_MEMO §6 | Primary window 2022-06-30 → 2026-07-02; survivor_bias=false rows only for verdicts |
| Plain-language law | §11 plain-English box required in report |

---

*Registered 2026-07-05. Immutable after Fable approval. Results are added to the RESULTS.md file only; this document is never edited to accommodate observed outcomes (species README convention).*

---

## Revision history

| Revision | Date | Author | Changes |
|---|---|---|---|
| R0 (initial) | 2026-07-05 | Sonnet subagent | Original PREREG filed |
| R1 (conditional approval) | 2026-07-05 | Fable orchestration (applying P2_5_REDTEAM.md) | BLOCKING-1: annotated sc63 bug in §2.1 and §3; corrected half-stability status (only C2 confirmed; C3/C5/C6 explicitly in doubt). BLOCKING-2: pinned §5.2 baseline-free convention + mandatory run-preamble assertion. ADVISORY A: 63d baseline corrected 62.67%→62.31% in §2.1 header. ADVISORY D: C1 63d Δ −2.34pp labeled estimate/non-reconstructable; fire-weighted −1.92pp noted. ADVISORY E (Fable ruling): §5.3 binding dead-money check pinned to 21d; 63d dead-money check retained as secondary only. ADVISORY F (Fable ruling): C7/C8 estimated-slot risk explicitly accepted under thin-check decrement rule. Status changed to APPROVED. |

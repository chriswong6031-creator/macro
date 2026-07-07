# OTA W2 — Member Transmission — Formal Registered Results

> **REGISTERED CONFIRMATION RUN — W2_FORMAL_PREREG.md (merged before computation).**
> The word 'validated' does not appear in this document (Oracle Constitution §II).
> Pre-registration: research/oracle_asymmetry/W2_FORMAL_PREREG.md.
> Base spec: research/oracle_asymmetry/W2_SPEC.md (frozen).

> **RE-CHECK NOTE (2026-07-07, RC-RUL-2 — research/TIME_CONFOUND_RECHECK_ADJUDICATION.md).**
> OTA-RC-1 (PR #1855, `W2_TC_RECHECK.md`) re-computed the delta CIs with the 35 armed
> windows merged into 9 macro-episodes and the R3 baseline period-matched. **The
> CONFIRMED verdict stands:** ΔWR21 90% CI [0.0399, 0.1901], Δmean_ret21 [0.0107,
> 0.0493], period-matched R3 [0.0207, 0.1692] — all lower bounds above zero, margins
> narrowed vs the window-cluster CIs. Caveats: 7 in-arm episodes is a thin resampling
> base; the episode-joint placebo remains unbuilt (optional accrual item); the §5
> forward ledger stays the decisive arbiter.
> Seed: 20260706 (registered). Bootstrap draws: 2,000. Placebo draws: 500.
> Registered corrections applied: (a) symmetric placebo OUT-arm;
> (b) cluster-bootstrap CI on delta; (c) MDE alpha=0.05;
> (d) R3 temporal split at 2024-06-30; (e) seed=20260706.

## Disclosed Limitations

1. **Basket membership is a static 2023-05-09 snapshot** — contains hindsight bias for the 2022–2023 sub-window.
2. **No PIT GICS-sector map exists** — sector-drift between Oracle node and member basket is uncontrolled.
   Replay `sector` field (GICS string) is used to assign member fires to Oracle nodes via GICS_TO_NODE,
   rather than the spec's `etf_proxy` field (which replay does not carry). The mapping is functionally
   equivalent as long as a ticker's GICS sector has not drifted; sector-drift risk is uncontrolled.
3. **SP500 PIT intervals** are used for member eligibility (sp500 src rows from sp1500_pit_membership.parquet).
4. **BRK-B filename artifact** — BRK-B may appear as BRK-B.parquet or BRK.B.parquet; ablation (c)
   tries both variants via _load_massive_ticker() and counts absent tickers out explicitly.
5. **Effective verdict window ≈ 2022-06-30 → last replay date** (P0 memo v1.1 §6 Amendment 1: 250-bar MTF warmup consumes ~11 months of the 2021-07-06 nominal start).
6. **Cluster bootstrap** resamples window IDs with replacement; within-window member co-movement inflates naive CIs.
7. **MDE@80% is an approximation** — uses a normal-approximation formula with the number of IN-arm cluster
   windows as effective n (treating each window as one independent observation). The true design effect
   depends on within-window ICC and cluster size, which are not computed here. Treat MDE as order-of-magnitude.
8. **W2_member_trades.csv includes non-PIT rows** — IN and OUT arms contain both pit_member==True and
   pit_member==False rows. Headline aggregates require filtering pit_member==True before recomputation.

## Preamble — Fidelity Gate

- Replay rows total: 961,656
- survivor_bias==False: 961,656
- verdict_grade==True: 834,267
- horizon_censored==True (excluded): 127,389
- Golden test PASSED: prod_fire_count=62, replay_fire_count=62, exact_match=True
- W0 a15-all: 5128, a15-raw: 4734, a15-unique(node,date): 2367
- W0 ep_onset_in: 714

## Armed Windows (K=10, primary: a15-raw)

Total windows: 35

| Node | Windows |
|------|---------|
| XLB | 5 |
| XLE | 6 |
| XLF | 7 |
| XLI | 6 |
| XLK | 5 |
| XLP | 1 |
| XLRE | 2 |
| XLU | 1 |
| XLV | 2 |

## Arms Table (Primary: a15-raw, K=10)

Effective n (window count, unit of independence): IN=31, OUT=n/a (no window structure)

| Metric | IN (n windows=31) | OUT | Δ (IN−OUT) |
|--------|-------------------|-----|-----------|
| WR21 | 0.6522 | 0.5359 | 0.1163 |
| Mean fwd_ret_21 | 0.0385 | 0.0086 | 0.0299 |
| Median fwd_ret_21 | 0.0328 | 0.0067 | 0.0261 |
| Mean fwd_mfe_21 | 0.0774 | 0.0579 | 0.0195 |
| Mean fwd_mdd_21 | -0.0416 | -0.0493 | 0.0077 |
| Stop-5 rate | 0.1105 | 0.1084 | 0.0021 |

IN arm rows: 31268 | OUT arm rows: 369475

### IN arm clean8_21 terminal state distribution

| State | Count |
|-------|-------|
| CLEAN_LIFTOFF | 11180 |
| CUSHIONED | 4445 |
| DEAD_MONEY | 5872 |
| STOPPED | 9771 |

## Cluster Bootstrap CIs (IN arm, 2,000 draws, 90% CI)

| Metric | Point | CI Lo | CI Hi | n windows | n rows |
|--------|-------|-------|-------|-----------|--------|
| WR21 | 0.6522 | 0.5915 | 0.7097 | 31 | 31268 |
| Mean fwd_ret_21 | 0.0385 | 0.0244 | 0.0525 | 31 | 31268 |

## Regime-Matched Placebo (500 draws)

Placebo runtime: 3.4s | Draws producing valid delta: 500/500

| Metric | Observed Δ | Placebo p95 | p-value (placebo) | BH-corrected (q=0.10) |
|--------|-----------|-------------|-------------------|----------------------|
| ΔWR21 | 0.1163 | 0.1013 | 0.008 | True |
| Δ mean fwd_ret_21 | 0.0299 | 0.0229 | 0.000 | True |

## Cluster-Bootstrap CI on Delta (IN−OUT, 2,000 draws, 90% CI — prereg §2b)

*OUT arm fixed; IN arm window-level resample.*

| Metric | ΔPoint | CI Lo | CI Hi | n IN-windows |
|--------|--------|-------|-------|-------------|
| ΔWR21 | 0.1163 | 0.0537 | 0.1757 | 31 |
| Δmean_ret21 | 0.0299 | 0.0153 | 0.0444 | 31 |

## Gate Verdicts

**Pre-bound vocabulary (prereg §4, exhaustive):**
CONFIRMED — DISPLAY-WITH-EDGE / PARTIAL — DISPLAY-WITH-EDGE (holdout-underpowered) / PARTIAL-DIVERGENT / RETRACTED

- **R1** (ΔWR21 > symmetric-placebo p95, BH q=0.10): PASS
  - IN WR21=0.6522  OUT WR21=0.5359  Δ=0.1163
  - Placebo p95=0.1013  p-value=0.008  BH-rejected=True
  - IN n_windows=31  IN n_rows=31268  OUT n_rows=369475

- **R2** (Δmean_ret21 > symmetric-placebo p95, BH q=0.10): PASS
  - IN mean fwd_ret_21=0.0385  OUT mean fwd_ret_21=0.0086  Δ=0.0299
  - Placebo p95=0.0229  p-value=0.000  BH-rejected=True

- **R3** (holdout ΔWR21 > 0 AND 90% CI LB > 0, split at 2024-06-30): PASS
  - Dev windows (≤ 2024-06-30): 16  |  Holdout windows (> 2024-06-30): 15
  - Holdout ΔWR21=0.1073  90% CI=[0.0380, 0.1786]
  - R3 delta>0: True  CI LB>0: True
  - MDE@80% alpha=0.05 (holdout, 15 windows): 0.3931

### VERDICT: **CONFIRMED — DISPLAY-WITH-EDGE**

> R1 (ΔWR21 > symmetric-placebo p95, BH q=0.10) PASS; R2 (Δmean_ret21 > symmetric-placebo p95, BH q=0.10) PASS; R3 (holdout ΔWR21 > 0 AND 90% CI LB > 0) PASS. Ceiling unchanged: display-with-edge (constitution §III; 'validated' unavailable). W6 desk forward rule (§5) becomes the promotion clock.

---

## Appendices

*The following appendices are supplemental. K-sensitivity, per-sector, and ablation (c) are labeled*
*and MUST NOT be cited as findings. Secondary condition (ep_onset_in) is reported with the same*
*pre-bound vocabulary.*

### Appendix A: Secondary Condition (ep_onset_in) — registered

| Metric | IN (n windows=54) | OUT | Δ |
|--------|------|-----|---|
| WR21 | 0.6273 | 0.5395 | 0.0878 |
| Mean fwd_ret_21 | 0.0243 | 0.0101 | 0.0142 |

Secondary verdict (pre-bound, same vocabulary): **UNDERPOWERED-ACCRUING (placebo not run for secondary; point estimate positive)**

> Secondary condition has 54 IN-arm windows. No formal placebo run for the secondary read (only 2 gate reads registered). Secondary results are descriptive only.

### Appendix B: K-Sensitivity (appendix-only — MUST NOT be cited as findings)

| K | IN windows | IN WR21 | OUT WR21 | Δ WR21 |
|---|-----------|---------|---------|--------|
| 5 | 36 | 0.6607 | 0.5378 | 0.1229 |
| 21 | 34 | 0.6399 | 0.5321 | 0.1078 |

### Appendix C: Per-Sector Split (appendix-only — MUST NOT be cited as findings)

| Node | IN windows | IN rows | IN WR21 | OUT rows | OUT WR21 | Δ WR21 |
|------|-----------|---------|---------|---------|---------|--------|
| XLB | 4 | 2587 | 0.6997 | 18277 | 0.4975 | 0.2021 |
| XLC | 0 | 0 | n/a | 16706 | 0.5716 | n/a |
| XLE | 4 | 1210 | 0.5992 | 15669 | 0.5353 | 0.0639 |
| XLF | 6 | 9454 | 0.6629 | 47790 | 0.5517 | 0.1112 |
| XLI | 6 | 8146 | 0.6778 | 56475 | 0.5507 | 0.1271 |
| XLK | 5 | 5256 | 0.7578 | 47627 | 0.5413 | 0.2165 |
| XLP | 1 | 403 | 0.0645 | 27055 | 0.4987 | -0.4342 |
| XLRE | 2 | 1457 | 0.5916 | 25361 | 0.4933 | 0.0983 |
| XLU | 1 | 540 | 0.0852 | 26000 | 0.5562 | -0.4710 |
| XLV | 2 | 2215 | 0.5210 | 47830 | 0.5175 | 0.0035 |
| XLY | 0 | 0 | n/a | 40685 | 0.5530 | n/a |

### Appendix D: Ablation (c) — Member-Trigger Value

> Measures what the member trigger adds BEYOND the sector condition alone.
> Entry: window_start+1 session for ALL PIT-eligible sector members.
> Graded via _load_massive_ticker() (BRK-B artifact handled) + engine/grading.py.
> No formal gate applied (registered as appendix-only).

Ablation entries: 1717 | Windows with ablation data: 35
Ticker skips: pit_fail=167 not_found=0 read_error=0 no_close_col=0

| Metric | Ablation (c) |
|--------|-------------|
| WR21 | 0.6016 |
| Mean fwd_ret_21 | 0.0302 |
| Mean fwd_mfe_21 | 0.0779 |
| Mean fwd_mdd_21 | -0.0449 |
| Stop-5 rate | 0.1097 |

**Trigger lift** (IN arm WR21 vs ablation WR21): 0.0507
> Positive = member trigger selects better entries than blind entry at sector fire.

---

## DIFF AUDIT (prereg §6 allow-list)

The registered-run code diff vs the W2 script is audited against the §6 exhaustive list.
Every changed hunk is mapped here. No other changes exist.

| Prereg §6 item | Implementation | Location |
|---------------|---------------|----------|
| (a) Symmetric placebo: placebo OUT-arm excludes real IN fires | `_placebo_draw_both_metrics` gains `real_in_mask_ns` param; in registered mode, real IN-arm fire positions are forced to placebo-IN (excluded from placebo OUT pool) | `_placebo_draw_both_metrics` function + `run_main` placebo loop |
| (b) Cluster-bootstrap CI on delta (2,000 draws, 90% CI) | New `cluster_bootstrap_delta_ci` function: resamples IN-arm window ids, OUT fixed, computes delta per draw; called for ΔWR21 and Δmean_ret21 | New function + `run_main` registered-run block |
| (c) MDE alpha=0.05 | `MDE_ALPHA_REGISTERED = 0.05` constant; `mde_at_power` called with `alpha=MDE_ALPHA_REGISTERED` in registered verdict block | Constants + verdict block |
| (d) R3 temporal split at 2024-06-30 | Armed windows split by `window_start <= 2024-06-30` (dev) vs `> 2024-06-30` (holdout); holdout ΔWR21 + cluster-bootstrap 90% CI computed; R3 pass = delta>0 AND CI LB>0 | `run_main` registered-run block |
| (e) seed 20260706 | `SEED_REGISTERED = 20260706`; all RNG initializations in registered mode use `active_seed = SEED_REGISTERED` | Constants + `run_main` |
| No other changes | Default (non-flag) mode code paths unchanged; seed/rng/verdict/report all conditional on `registered_run` flag | All edits gated on `if registered_run:` |

**Default-mode byte-identity:** all branching is `if registered_run: ... else: <original code>` or `active_seed` substitution. The default path produces the same numerical outputs as the pre-registered W2 run.

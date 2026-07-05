# OTA W1 — Onset-Quality Discriminator — Build Spec (pre-registered)

**Program:** Oracle Turn Asymmetry ([masterplan](../ORACLE_TURN_ASYMMETRY_MASTERPLAN_BY_FABLE.md) §W1). Authored by Fable 2026-07-05. Committed BEFORE any model is fit; gates, features, folds, and labels below are frozen (amendments logged + countersigned). RESEARCH-ONLY: no nightly wiring, no oracle_state.json changes, no site surface — a separate W1.2 PR wires the score only if the gates pass and Fable adjudicates. "validated" banned; every table carries n + base rate.

## 0. The question
Tier-S onsets carry the program's only FDR-surviving edge, but 34–38% are 5-day false starts and 47–65% end as dead money. Can onset-day, PIT-clean features separate the onsets that convert into asymmetric wins from the rest — better than trivial conditioning would?

## 1. Population & labels (frozen — the vintage re-pin)
- **Population:** `ep_onset_in` rows of the COMMITTED `research/oracle_asymmetry/W0_2_events_graded.csv` (dedup structural; parameterization `pos63`), matured rows only. Expected n ≈ 350; assert family counts against the committed CSV exactly (357 total ep_onset_in rows) — abort loudly on mismatch. Labels come from the committed CSV and can never drift with panel accrual.
- **Primary label:** intraday terminal state ∈ {CUSHIONED, CLEAN_LIFTOFF} (the W0.2 good-set at pos63). Base rate ≈ 0.46–0.49 (print exact).
- **Secondary labels (reported, never gate-bearing):** rot21 good-set; false-start-5d (direction-adjusted 5d outcome < 0 from the episodes catalog).
- OUT-direction onsets are OUT OF SCOPE (short side failed W0 at fixed horizons; noted, not modeled).

## 2. Features (PIT at trigger date t; FULL-HISTORY columns only)
All features computed strictly as-of t (causal windows ending at t). The 2021+ columns (breadth_50, cohesion, cohesion_chg, turnover_z, cohesion_rebuild) are FENCED OUT of this model (coverage law; a modern/Tier-M model is deferred). Episode-catalog fields computed over the whole episode (duration, peak_accel_z, exhausted_date) are LEAKAGE and prohibited as features.
Frozen feature list (panel_s + episodes catalog + W0 CSV):
1. `accel_z` at t; 2. `accel_z_5d` (causal rolling-5 mean, recomputed); 3. `accel` (vel_1w − vel_3m) at t; 4. causal 252d percentile of `rs` at t; 5. `persistence` at t; 6. `washout_w` at t; 7. `stochrsi_w_k` at t (scale 0–100); 8. `stochrsi_w_k − stochrsi_w_d` at t; 9. `vix_pctile` at t; 10. `spy_above_200d` at t; 11. `tlt_ret_10d` at t; 12. opposite-complex OUT-onset count within 20 sessions ≤ t (flow displacement, from the episodes catalog + rotation_groups); 13. same-complex OUT-onset count within 20 sessions ≤ t; 14. count of concurrently active IN episodes across all nodes at t (crowdedness); 15. previous same-node episode's good/bad outcome (most recent episode fully matured ≥63 sessions before t; 0 if none — leakage-lawful); 16. `sigma20` from the W0 CSV row.
No additions without a logged amendment. Missing values: NaN→column median computed on TRAIN folds only.

## 3. Models (all deterministic, seed 20260705)
- **M0 baseline (the bar):** logistic regression on {accel_z_5d, vix_pctile} only.
- **M1:** L2 logistic on all 16 (λ by inner time-ordered CV). If sklearn is unavailable, implement via numpy/scipy IRLS — no new dependencies.
- **M2:** shallow gradient boosting (depth ≤ 2, ≤ 150 trees, learning rate ≤ 0.1), monotone constraints where sign is mechanism-implied (e.g. +flow-displacement, −stochrsi level); skip with a logged note if no library supports it.
Chosen model = higher mean OOS AUC between M1/M2 under §4; chosen BEFORE reading §5 gates (no peeking at operating tables to pick).

## 4. Evaluation protocol (frozen)
- **Outer folds: leave-one-era-out** over the four `_ERA_CUTS` eras (import from scripts.oracle_screen). Train on 3 eras, test on the held-out era. Never random folds (cross-sectional + temporal correlation).
- **Embargo/purge:** drop any training event whose 63-session outcome window overlaps the test era's span (63-session purge at both boundaries).
- **Shuffled-label null:** 200 within-era label permutations through the IDENTICAL pipeline → null AUC distribution; p = fraction ≥ observed mean AUC.
- Report per-era AUC, mean AUC, calibration (reliability table, 5 bins), and the same for M0.

## 5. Skeptic's gates (pre-registered; verdicts pre-bound)
- **G-A (signal exists):** mean LOEO AUC > 0.5 AND shuffled-null p < 0.05. Fail → verdict "NO ONSET-QUALITY SIGNAL AT n=350 — printed null", ship nothing.
- **G-B (beats trivial):** chosen model mean AUC ≥ M0 mean AUC + 0.03. Fail while G-A passes → **the deliverable IS M0** (ship the 2-feature score, honestly labeled).
- **G-C (usefulness, reported not gating):** at a keep-top-40% score threshold (threshold fit on train folds only), report held-out good-rate vs base rate with Wilson 95% LB, per era and pooled; same for keep-top-60%.
- No other cuts may be quoted as findings. Secondary-label results are appendix-only.

## 6. Deliverables
1. `scripts/oracle_onset_quality_w1.py` — build features, run protocol, emit `research/oracle_asymmetry/W1_features.csv` (committed; one row per event, features + labels + fold ids) and `research/oracle_asymmetry/W1_REPORT.md` (protocol printout, per-era tables, gates verdicts, calibration, coefficient/importance table with mechanism-sign commentary).
2. `tests/test_oracle_onset_quality_w1.py` — synthetic fixtures: purge correctness (train event overlapping test window is dropped); as-of feature tripwire (feature built from t+1 data ≠ feature at t on a crafted series); fold-integrity (no test event in train); shuffled-null machinery sanity (null AUC ≈ 0.5 on random labels); M0-vs-M1 gate arithmetic.
3. Data resolution: features from MAIN `--data-dir` panel_s/episodes_s (read-only, split-checkout law); population/labels from the committed worktree CSVs.

## 7. Prohibitions
No modification of existing engine/scripts files; no trial-ledger writes (this is not a compound screen — it is a measurement of a registered detection layer; the 5 pre-registered gate reads are the entire claimed test count); no hyperparameter search beyond §3's inner CV; no post-hoc feature additions; no quoting G-C lifts without their Wilson LBs.

## Amendment log
- (none)

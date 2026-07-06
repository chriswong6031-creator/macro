# Pre-registration — roster family F3: `long_hold.expect_drift` (m = 7)

**Registered:** 2026-07-06 (operator + Fable). Criteria do not move after merge; an edit after data contact voids the gate (OBJECTIVE §7 lock semantics).
**Family id:** `long_hold.expect_drift` (sub-family of `fdr_family='long_hold'`).
**Mechanism claim:** business inflection + expectation underreaction. A tactical-entry candidate whose most recent earnings evidence shows positive standardized surprise, surprise persistence, positive post-event drift, absorbed bad news, or held good news is likelier to be a `compounder` (and likelier to avoid `cheap_trap`) than one without such evidence.
**Coordination (LH-R10):** species S9 (post-event absorption) owns entry-horizon claims on event absorption; this family is the hold-ruler analog. No S9 claim is re-registered here.
**Provenance (LH-R11.3 / B2):** features use EDGAR event dates, EDGAR EPS, and the same price stores as the label panel. No feature re-expresses the daily washout-proximity selection variable. `feature_provenance = {edgar_8k_202, edgar_eps_quarterly, label_panel_price_stores}`. Human review gate acknowledged.

## 1. Population and substrate

- Population: fires from `data/research/gate_fires_baskets.parquet` carrying labels in `data/research/long_hold_labels.parquet` (schema `long_hold_labels.v1`).
- Event source: `data/edgar/earnings_8k_dates.parquet` (8-K item 2.02; PIT by SEC acceptance datetime).
- EPS source: `data/edgar/eps_quarterly.parquet` (`eps_q`, `period_end`, `asof_date`); visibility rule: rows with `asof_date ≤ fire_date` only.
- Prices/benchmarks: identical store resolution and sector-basket benchmarks as `scripts/research/long_hold_label_panel.py`; where a sector benchmark is unavailable, SPY with `benchmark='market'` stamp.
- **Reference event E(f):** the latest 8-K 2.02 with `filing_date ≤ fire_date − 1 trading session` and within 120 calendar days of fire_date. No qualifying event → event-anchored features (ED-3/4/5/7) are missing for that fire.
- **Seasonal surprise at a quarter q:** `d_q = eps_q − eps_{q−4}` (calendar-matched ±50d); **SUE_q** = `d_q / σ(last 8 seasonal diffs, min 4)` — the `engine/sue.py` construction, evaluated PIT.

## 2. Registered hypotheses (m = 7; expected signs frozen)

| id | Feature | Type | Definition (PIT as of fire_date) | Expected sign | Test |
|---|---|---|---|---|---|
| ED-1 | `sue_latest` | cont | Most recent SUE_q visible at fire_date | + | MWU / RBC |
| ED-2 | `sue_streak` | int | Consecutive quarters with `d_q > 0` ending at the most recent visible quarter (cap 8) | + | MWU / RBC |
| ED-3 | `pead_drift` | cont | Cumulative stock-minus-benchmark return over sessions E(f)+1 … min(E(f)+20, fire_date−1); requires ≥5 elapsed sessions, else missing | + | MWU / RBC |
| ED-4 | `bad_news_absorption` | bin | Most recent visible `d_q < 0` at E(f) AND no close in the 10 sessions after E(f) below the minimum close of the 63 sessions before E(f) AND stock-minus-benchmark return over sessions E(f)+1…E(f)+5 ≥ 0 | + | Fisher |
| ED-5 | `good_news_hold` | bin | Most recent visible `d_q > 0` at E(f) AND close(E(f)+1)/close(E(f)) − 1 ≥ +2% AND close(E(f)+10) ≥ close(E(f)+1) | + | Fisher |
| ED-6 | `sue_accel` | cont | SUE_latest − SUE_prev (two most recent visible quarters; else missing) | + | MWU / RBC |
| ED-7 | `confirmed_absorption` | bin | (ED-4 OR ED-5) AND ED-3 > 0 | + | Fisher |

Coverage rule: OBJECTIVE §5's 20% retention rule on labeled fires; dropped features remain in the Σ denominator (LH-R11.2).

## 3. Rulers (LH-R14)

- **Ruler-P (powered, display-ceiling):** `cheap_trap` vs `tactical_only` at 252d, fires with fire_date ≤ 2023-12-31 only. Temporal cells: fit 2014-2019 / OOS-biased 2020-2023, each survivorship-stamped "UPPER BOUND". Pre-registered descriptive era breakout: 2014-2019 / 2020-2021 / 2022-2023. Within-family BH q=0.10 descriptive; per-feature within-regime reshuffle null (1,000 perms, seed 42) required for any display claim. Authority ceiling: display block ships regardless of result; a feature quoted as "evidence" in display copy must pass both descriptive gates. No SURVIVE/KILL vocabulary.
- **Ruler-H (honest, ratifying):** `missed_hold` vs `tactical_only` on OOS-2 per `AMENDMENT_A2_G1_RETEST.md`; program-wide HLZ q=0.10; evaluated at the ≥25-cluster trigger (~2027-H2).

## 4. Floors, stamps, and ledger

- n-floor: ≥25 episode-clusters per arm per cell (LH-R4); episode-clustering name × macro-regime ±10d.
- Every output row carries `survivorship_biased`, `coverage_frac`, `benchmark`, `horizon_role='hold_thesis'`, `_display_only=True`.
- TrialLedger: `log_declared_budget(7, family='long_hold.expect_drift')` before any p-value computation; registered in `data/experiments/registry_seed.json` with come-back dates (Ruler-P: on study completion; Ruler-H: 2027-07-01 checkpoint).
- Nulls are printed. The word "validated" is never used (CI-enforced).

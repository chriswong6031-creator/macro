# S7 Phase-0 + Triple-Lock — Frozen Pre-Registration (Fable, 2026-07-03)

Setup-Species program wave (masterplan: `research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md`).
S7 phase-0 brought FORWARD from W3 on external-evidence grounds. This spec is frozen
before any code runs; deviations must be logged in REPORT.md §Deviations.

## 1. Provenance & why now

An external Codex backtest (`research/bottom_signal_backtest/`, triaged 2026-07-03) found
that on 1W-MACD × 2W-StochRSI bottom fires, three context legs — cohort washout breadth,
**RS repair** (stock/sector RS 20d slope > 0, RS higher-low), and anti-chase location
(near the 60d low) — jointly cut stop-outs roughly in half. Triage verdicts: tuned numbers
test-leaked; universe hindsight-biased; cohort leg = convergent with our validated COILED
(S1); **RS repair is the one leg absent from our US entry stack** and is direct evidence
for S7's *repair* sign. S7's registration is TWO-SIDED: WAVE1 `rs_low` weakly favored the
opposite sign (low RS cleaned more). Both signs remain admissible outcomes here. The
promotion bar is beating the rs_low stratum on the same panels — not beating zero.

## 2. Panels

- **P1 (breadth, survivorship-honest-ish):** `data/massive_stock_day/` (20,177 tickers,
  2021-07-06 → 2026-07-02, split-adjusted Polygon daily; includes names that later
  delisted within the window). Liquidity floor evaluated AT FIRE DATE: trailing-63d median
  dollar volume ≥ $2M AND close ≥ $2. Benchmarks (SPY + XL* sector ETFs) read from the
  SAME store — never mix with `data/yahoo` (total-return adjusted).
- **P1-PIT stratum:** fires where ticker ∈ S&P 1500 as of fire date per
  `data/breadth/sp1500_pit_membership.parquet`. This is the honest-membership stratum;
  cohort features get a PIT-restricted variant here.
- **P2 (era depth):** `data/stocks/` deep panel (~224 names, long history). Context arm —
  no selection decisions on it, monthly-timeframe features live here only.
- Sector assignment: current GICS map (known limitation — dated SPDR holdings have no
  history; log in report). Sector→ETF map: standard GICS→XL* mapping.

## 3. Fires

- **F1 (primary):** the incumbent `base3d` confluence-gate fire, definitions REUSED from
  `research/signal_engine/` (CHARTER.md is binding; see HARNESS_USAGE.md + confluence.py).
  Fill = next close after fire (charter). Per-ticker cooldown per harness convention.
  Report the honest usable-fire window per panel after indicator warm-up (~200 trading
  days for the 3D grid on P1 → fires usable from ~mid-2022).
- **F2 (secondary, settle-it arm):** the Codex trigger — completed 1W MACD bull cross
  within 10 td of a completed 2W StochRSI bull cross from sub-20 oversold (fix their
  `recent_os.shift(1)` quirk: oversold window includes the cross bar), 21-bar cooldown.
  One pass, identical metrics, so the two trigger families are finally comparable on one
  harness. No overlay tuning on F2.

## 4. Features (computed at fire close t; fill at close t+1 — EOD-causal)

| key | definition | subset |
|---|---|---|
| `rs_spy_slope20` | (close/SPY) 20d change > 0 | all names (headline — no mapping confound) |
| `rs_sect_slope20` | (close/sector-ETF) 20d change > 0 | GICS-mapped only |
| `rs_sect_hl` | min(RS[t-19..t]) > min(RS[t-39..t-20]), RS vs sector ETF | mapped only |
| `rs_cohort_rank_slope20` | within-sector RS-rank percentile (vs liquid peers), 20d change > 0 — the masterplan's S7 definition | mapped only |
| `rs_low` | RS-vs-SPY level in bottom tercile of its trailing 252d range — the WAVE1 baseline stratum S7 must beat | all names |
| `cohort_frac_w` | % of same-sector liquid peers with weekly StochRSI D < 30 (reuse `engine/coiled.py` math); tiers ≥40%, ≥50%; variants: (a) current-map full universe, (b) PIT-restricted | mapped only |
| `loc60_12` / `loc60_15` | close within 12% / 15% of trailing 60d low | all names |
| `above_10w` | close > 10-week MA | all names |
| `monthly_dwell` | consecutive completed monthly StochRSI-D<20 bars; fresh (1–3) vs stale (≥6) | P2 only |

Every stratum's delta is measured against the SAME-COMPUTABLE-SUBSET baseline (the
Codex report's mapped-subset confound must not be reproduced).

## 5. Metrics (charter definitions — no substitutions)

Primary: **race stop-out** = fill → close −5% before close +5%. Co-primary: clean-liftoff
`clean15_126` (+15% before −5% within 126 td; positional, matches S7 horizon_class) and
`clean8_21` where the P1 tail truncates 126-td maturity. Secondary: median 20d forward,
MFE/MAE-20d (intraday H/L over close-fill), time-to-fail, 60d-undercut rate (fire-date
60d-low broken within 60 td). Report n, episode count, and maturity coverage per cell.

## 6. Frozen hypotheses & thresholds

- **H-A (S7 core, two-sided):** On F1/P1, does `rs_spy_slope20` (and the vs-cohort
  variants) stratify fire quality? GO for the *repair* sign requires: stop-out reduction
  vs subset baseline with episode-block bootstrap 90% CI excluding 0, AND repair stratum
  beats the `rs_low` stratum on stop-out and clean-liftoff. GO for the *deterioration*
  sign requires the mirror. Neither → NO-GO logged; S7 stays unpromoted.
- **H-B (triple lock):** `cohort_frac_w≥40 ∩ rs_repair ∩ loc60_15` tier: stop-out ≥8pp
  below subset baseline AND ≥3pp below the best pairwise combo, liftoff not below
  baseline. Also verify the pairwise failure signature (location-only worsens 60d-undercut;
  cohort-only weaker median; RS-only more extended entries) — if the signature fails, the
  interaction story is not supported even if the point estimate passes.
- **H-C (deep-tier regime robustness, reported not gating):** cohort ≥50% fires during
  SPY-below-falling-200D: stop-out ≤ subset baseline (the external bear-robustness claim).
- **Guardrails:** a stratum yields NO VERDICT below 8 episodes (episodes = fire dates
  greedy-clustered at gap >10 td). Episode-block bootstrap = resample episodes with
  replacement, 2,000 draws. All CIs 90%.

## 7. Protocol

P1 dev = fires ≤ 2024-12-31. P1 holdout = 2025-01-01 → 2026-06 — touched ONCE, after the
dev tables and frozen tier definitions are written into REPORT.md. P2 = all-sample context
arm. No parameter search beyond the enumerated features/tiers above; anything exploratory
goes in an appendix marked non-registered.

## 8. Deliverables

1. Package here: `loader.py` (incl. split-sanity pre-flight: flag |1d ret|>40% w/ normal
   volume; verify store adjustment semantics before anything else), `fires.py`,
   `features.py`, `harness.py`, `analyze.py`, `REPORT.md`, summary CSVs (committed);
   per-fire parquet gitignored if >20MB.
2. `data/species/registry.json`: ADD S7 entry per `species_registry.v1` schema, mechanism
   text conformant to masterplan §4 (two-sided), `validation_status: "phase0"`,
   adjacent_falsified citing WAVE1 rs_low + residual-momentum + BOTTOM_CONFIDENCE R4,
   evidence noting `research/bottom_signal_backtest` (external, discounted) + this package.
3. NOT in scope: engine wiring, China port, any citation of the Codex `tuned_*` CSVs as
   evidence (test-leaked), masterplan/CHARTER edits (Fable-only).

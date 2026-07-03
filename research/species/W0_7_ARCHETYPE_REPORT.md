# W0.7 Stock Archetype v2 — Phase-0 Conditional Outcome Report

> **Status: MEASUREMENT REPORT — no gate proposals.** This report characterizes
> archetype-conditional outcomes on the existing grade ledger. Archetypes gate
> nothing in W0.7 (display/research only). Per §1.2 of the masterplan: per-fire
> count-fair, no round-trip returns.
>
> **Generated: 2026-07-03**

---

## 1. Methodology

### 1.1 Archetype assignment

Each ticker in the US board grade ledger is assigned its **latest available**
archetype from `data/archetypes/history.parquet` (FY 2009–2025, annual steps).
This is a static cross-sectional join — not PIT at the fire date — because we
have only one snapshot of factor betas and one snapshot of factor z-scores.
The join is on `ticker`; where a ticker has multiple FY rows the latest is used.

This is the **strongest source of bias in this report**: archetypes assigned
from 2025 FY data are joined to fires that occurred in June 2026. For names
that changed archetype between filing and fire, the assignment may be stale.
All findings should be treated as preliminary until a PIT-stamped ledger
accumulates enough rows.

### 1.2 Outcome variables

From `data/us_board_ledger/retro_grades.parquet`:

| column | meaning |
|---|---|
| `ret` | Raw return over the hold window (entry to grading date) |
| `excess_spy` | `ret − spy_ret` (alpha vs SPY) |
| `mae_close_excess_spy` | Max adverse excursion vs SPY (≤0 by construction; 0 = never underwater) |

**No `clean15` or `stop5` in the absolute-return sense** — the hold window
ranges from a few days to ~17 calendar days (entries 2026-06-16 to 2026-06-25,
graded as of 2026-07-03). 15% absolute return is unreachable at these horizons.
We substitute:

- **stop5_pct**: share of fires where `mae_close_excess_spy ≤ −5%` (worst
  intra-hold drawdown exceeded −5pp vs SPY)
- **ret_pos_pct**: share of fires with positive raw return
- **excess_spy_pos_pct**: share of fires with positive alpha vs SPY

### 1.3 Fire ledger description

- **Grade date range:** 2026-06-16 to 2026-06-25 (17 calendar days)
- **Total fires:** 950 rows (2 entries per unique ticker/date pair from two
  rank_by channels: `conviction` n=721, `bottoming-alignment` n=229)
- **Unique tickers:** 359
- **Archetype coverage:** 791/950 fires (83%) matched to a latest-FY archetype;
  159 fires (17%) unmatched (tickers absent from the EDGAR fundamentals panel)

### 1.4 The constitution axes per the masterplan

§1.2 specifies: stop5, clean15, dead-money, MAE. Mapping to available data:

| spec axis | available proxy | coverage |
|---|---|---|
| stop5 | mae_close_excess_spy ≤ −5pp | full (950 rows) |
| clean15 | UNAVAILABLE at 17-day horizon | 0 |
| dead-money | ret in (−5%, +5%) band | partial proxy |
| MAE | mae_close_excess_spy | full |

`clean15` cannot be computed from a 17-day window. This is a structural gap
that will close as the ledger matures (~12 weeks of graded fires needed).

---

## 2. Headline results

### 2.1 Archetype distribution in the grade ledger

| archetype | fires | uniq tickers |
|---|---|---|
| financial | 174 | 66 |
| mixed | 131 | 53 |
| cyclical | 103 | 40 |
| distressed | 103 | 35 |
| rate_sensitive | 101 | 37 |
| speculative_unprofitable | 80 | 27 |
| high_beta_momentum | 32 | 13 |
| secular_growth | 29 | 11 |
| broken_growth | 18 | 9 |
| quality_compounder | 11 | 7 |
| dividend_defensive | 5 | 4 |
| deep_value | 4 | 3 |

Note: `financial` is the largest bucket. This reflects the composition of the
S&P 1500 universe from which the board draws — Financials is a large GICS
sector. The bucket fires on sector key, not ratios, so it captures all banks,
insurers, REITs, and brokerages.

### 2.2 Conditional outcome table

All results from fires with matched archetypes (n=791). **Warning: small n for
quality_compounder (11), dividend_defensive (5), deep_value (4) — treat those
as directional only.**

| archetype | n_fires | mean_ret | mean_excess_spy | mean_MAE | stop5_pct | ret_pos_pct | excess_spy_pos_pct |
|---|---|---|---|---|---|---|---|
| financial | 174 | +3.2% | +3.2% | −1.6% | 9.8% | 82.8% | 74.1% |
| mixed | 131 | +2.7% | +2.6% | −2.0% | 16.0% | 77.1% | 75.6% |
| rate_sensitive | 101 | +3.5% | +3.3% | −2.1% | 12.9% | 67.3% | 64.4% |
| broken_growth | 18 | +3.3% | +3.6% | −2.2% | 11.1% | 66.7% | 72.2% |
| quality_compounder | 11 | +2.8% | +2.6% | −1.1% | 0.0% | 72.7% | 72.7% |
| dividend_defensive | 5 | +3.0% | +1.3% | −0.5% | 0.0% | 100.0% | 80.0% |
| deep_value | 4 | +3.5% | +2.9% | −0.2% | 0.0% | 100.0% | 75.0% |
| secular_growth | 29 | +0.6% | +0.8% | −3.7% | 31.0% | 58.6% | 55.2% |
| cyclical | 103 | 0.0% | −0.3% | −2.5% | 17.5% | 57.3% | 53.4% |
| distressed | 103 | +0.9% | +0.9% | −3.2% | 20.4% | 57.3% | 51.5% |
| commodity_sensitive | 0 | — | — | — | — | — | — |
| speculative_unprofitable | 80 | −1.8% | −1.9% | −4.6% | 42.5% | 38.8% | 37.5% |
| high_beta_momentum | 32 | −1.5% | −1.3% | −6.1% | 46.9% | 43.8% | 43.8% |

*Errata: the original table contained a duplicate `broken_growth` row (rows 4 and 11
were identical) and was missing `commodity_sensitive`. The duplicate was removed. The
`commodity_sensitive` row above (n=0) reflects that zero fires in this ledger
(2026-06-16 to 2026-06-25) matched that archetype in the latest-FY snapshot — confirmed
by recomputing all rows using the §1.1 methodology (latest FY archetype joined on ticker);
spot-checks for `financial`, `cyclical`, and `distressed` reproduce the original values
exactly.*

### 2.3 Both-halves sign check

Only n≥20 archetypes are checked; sub-20 counts are directional only.

| archetype | n | first_half_excess_spy | second_half_excess_spy | consistent_sign? |
|---|---|---|---|---|
| financial | 174 | see note | see note | — |
| mixed | 131 | — | — | — |
| rate_sensitive | 101 | — | — | — |
| speculative_unprofitable | 80 | — | — | — |
| cyclical | 103 | — | — | — |
| distressed | 103 | — | — | — |
| high_beta_momentum | 32 | — | — | — |

**The 17-day window is too narrow for a meaningful both-halves time split.**
A calendar-based split (first 9 days vs second 8 days) would reflect mostly
market-level variation, not archetype signal. The both-halves check is
deferred to when the ledger spans ≥6 months of graded fires.

---

## 3. Directional findings (preliminary, not promoted)

These patterns are visible in the data. They are NOT gateable on this sample.

**F1: speculative_unprofitable and high_beta_momentum show the strongest negative
mean excess and highest stop5_pct.**
- speculative_unprofitable: mean excess −1.9%, stop5 42.5%
- high_beta_momentum: mean excess −1.3%, stop5 46.9%
- This is consistent with the board's existing rejection heuristic for money-losers.
  NOT a new finding — confirms the existing veto behavior.

**F2: financial, rate_sensitive, broken_growth show positive mean excess (+3.2%,
+3.3%, +3.6%) with moderate stop5 (10–13%).**
- These are the three largest absolute performers at short horizons.
- Interpretation: the board's entry signals may be particularly effective for
  rate-sensitive and financial names in a rate-relief environment (June 2026 =
  post-tariff-shock recovery). **Regime confound is severe** — all fires happened
  in the same 17-day window.

**F3: secular_growth shows the worst MAE (−3.7%) despite positive mean excess (+0.8%).**
- High-momentum growth names show wide intra-hold swings.
- Stop5_pct = 31% is the third highest after speculative_unprofitable and
  high_beta_momentum.
- Direction: secular_growth may need a tighter entry gate (narrower spread or
  lower-vol filter) rather than a size filter.

**F4: cyclical and distressed both show near-zero or slightly negative mean excess
(−0.3%, +0.9%) and elevated MAE (−2.5%, −3.2%).**
- These are the two riskiest "value" recovery buckets on this sample.
- Distressed in particular: Altman Z < 1.81 names in the board are getting picked
  up on technical signals but underperforming on a market-adjusted basis.

---

## 4. Honest caveat block

**Survivorship-priced panel:** The EDGAR fundamentals panel covers names that
were still filing as of the collection date. Bankrupt/delisted names prior to
2026 are NOT in the panel and NOT in the grade ledger. Both the archetype
distribution and the outcome table are biased toward survivors.

**17-day horizon:** All fires occurred within a single 17-calendar-day window
(2026-06-16 to 2026-06-25). Market conditions in this window (post-Liberation-Day
tariff shock recovery, rate-relief regime) may dominate any archetype-level
signal. The regime confound cannot be estimated with one regime.

**Non-PIT archetype assignment:** Archetypes are assigned from the latest FY
filing (FY2025) for each ticker, not from the archetype at the fire date. For
any ticker that changed archetype since FY2025 filing, the assignment is stale.

**Historical archetype labels are non-PIT for beta/sector-driven buckets:**
`data/archetypes/history.parquet` contains genuinely PIT inputs only for Altman
Z ratio components and rev/EPS CAGRs (statements filtered to `fy <= row fy`).
Sector, rates_beta, oil_beta_raw, and factor z-scores are CURRENT-SNAPSHOT values
(single 2026 read from `site/factor_betas.json` and `site/factordata/factors.json`)
used identically for every historical row. Empirically 0/1331 tickers vary their
sector/rates_beta/oil_beta across years in this parquet, confirming the labels for
rate_sensitive, commodity_sensitive, financial, and cyclical buckets reflect 2026
cross-section, not true historical state. Per masterplan §3.4: these labels may
seed **display-only** hypothesis priors and never learned multipliers or
species scope-gates.

**Distressed bucket silent gap pre-~2020:** Altman Z inputs are NaN for most
pre-~2020 rows (EDGAR XBRL coverage is sparse before 2018-2020). Early-year rows
for which Altman inputs are absent are classified entirely by current-day inputs
(sector, betas, factor z-scores). The distressed bucket should be treated as
unreliable before FY2020.

**Small n for 5 buckets:** quality_compounder (11), dividend_defensive (5),
deep_value (4), broken_growth (18), secular_growth (29). No significance test
is reported because the effective n is too small and the regime confound is
uncontrolled.

**No promotion from this report.** Per the masterplan: archetypes enter species
scope only where the conditional spread is real AND both-halves checked. This
report is a measurement baseline, not a demotion or promotion trigger.

**_GROWTH_ARCH compatibility note (engine/stock_macro_sensitivity.py):** `secular_growth`
and `broken_growth` have been added to `_GROWTH_ARCH` so that names reclassified
from `quality_compounder`/`high_beta_momentum` into these v2 buckets retain their
negative inflation-beta read. `rate_sensitive`, `cyclical`, `financial`,
`commodity_sensitive`, and `distressed` are deliberately excluded — those
reclassifications change the macro nature of the name.

---

## 5. Data paths

| file | description |
|---|---|
| `data/archetypes/history.parquet` | annual archetype series — fundamentals PIT, sector/betas/factor-z CURRENT-SNAPSHOT (non-PIT labels for beta/sector-driven buckets) (19,487 rows, FY2009–2025) |
| `data/us_board_ledger/retro_grades.parquet` | Grade ledger used for phase-0 (950 fires) |
| `engine/stock_fundamentals.py` | `_archetype()` v2, `archetypes_history()` |
| `scripts/build_archetype_history.py` | Rebuild entrypoint — rebuilt on demand; not on the nightly path; frozen between rebuilds |
| `research/species/W0_7_ARCHETYPE_REPORT.md` | This file |

---

## 6. Required next steps (not this wave)

1. **Ledger maturity gate:** run this analysis again after ≥200 fires per archetype
   for the top-5 buckets (financial, mixed, cyclical, distressed, rate_sensitive).
   Estimated: ~Q3 2026 if the board grades weekly.
2. **Both-halves time split:** once the ledger spans ≥6 months.
3. **Regime-stratified table:** VIX-percentile-stratified within-archetype spreads
   (as specified in §3.5 of the masterplan) — requires regime_vector stamps on
   each fire row (W0.5 deliverable).
4. **PIT-stamped archetype at fire date:** requires a daily archetype snapshot or
   a PIT fundamentals panel with same-day factor_betas. Current betas are a
   single cross-sectional snapshot.

# Stock Personality Field Guide — Measured Behavioral Reference

**Date:** 2026-07-07
**Status:** DESCRIPTIVE REFERENCE — printed distributions only; no edge claims, no significance tests, no forecast language
**Provenance:** workflow wf_b08c6af3 | 223-name deep corpus | survivorship-flagged (see §7)
**Companion:** research/STOCK_PERSONALITY_OPERATOR_PLAYBOOK_BY_FABLE.md

---

## How to Read This Document

This document is a compilation of six descriptive study lanes run against the 223-name "deep corpus" — names with full OHLCV price history in `data/stocks/`. Every number here is a measured distribution from that corpus. Nothing here is a signal, a recommendation, or a forward-looking claim. The lanes describe what the data contains; the companion operator playbook translates selected patterns into operating guidance.

Three standing warnings apply throughout:

1. **Label trust differs by type.** Return dispersion within archetype-year varies by more than 3x across types (speculative_unprofitable median cross-name std 0.544 vs financial 0.162). For low-dispersion types, the archetype label explains much of the name's year; for high-dispersion types, the label explains very little of the specific name's outcome. Treat summary statistics for high-dispersion types as distribution-of-distributions, not as type-level characterizations.
2. **Survivorship watermark.** The 223-name deep corpus is a biased subset of the 1,722-name production label universe. Names appear in the deep corpus because they have extended price history and were included in the deep-name program. Micro-cap, younger, and historically distressed names are underrepresented. All metrics should be treated as describing larger, more-established names.
3. **Deep-corpus-only caveat.** Statistics here do not generalize to the full 1,722-name production universe without verifying representativeness. The commodity_sensitive archetype has zero overlap with the deep corpus and is absent from most tables.

---

## Section 1 — Archetype Behavioral Fingerprints

> **In plain English:** Each of the 12 fundamental archetypes has a distinct risk profile measurable in volatility, drawdown depth, and how quickly prices recover. The biggest practical dividing line is not average volatility but within-archetype dispersion: knowing a name is "speculative_unprofitable" tells you almost nothing about what that specific name will do in a given year, while knowing a name is "financial" is far more predictive of its year-to-year range.

### Lane summary

The 12 archetypes divide into three broad behavioral tiers by volatility and market sensitivity. The high-energy tier — speculative_unprofitable (vol 0.378, beta 1.258) and high_beta_momentum (vol 0.392, beta 1.230) — runs roughly 75% more volatility than the low-energy tier and draws down 27% in a median label-year. They are also the hardest animals to own through a drawdown: 52–61% of label-year windows never see a full price recovery within 12 months. The mid-energy tier (cyclical, rate_sensitive, financial, secular_growth) clusters around vol 0.25–0.30 and beta 1.05–1.14, with drawdowns in the 18–23% range — meaningfully worse than their calm-appearing moderate betas would suggest. The low-energy defensive tier — dividend_defensive (vol 0.218, beta 0.621), quality_compounder (vol 0.248, beta 0.680), distressed (vol 0.242, beta 0.676) — is the relative safe harbor on paper, but distressed has paradoxically low beta because it moves idiosyncratically, not because it is truly defensive.

Return dispersion (cross-name standard deviation within archetype-year) is the sharpest separating signal between types. Speculative_unprofitable dispersion (0.544 median) is more than 3x financial (0.162) and quality_compounder (0.175). This means the archetype label gives very different information per type: owning "a speculative_unprofitable name" tells you almost nothing about the specific name's year, while owning "a financial name" is far more predictable from the archetype alone. The skew column confirms the macro narrative: speculative_unprofitable (+0.116) and secular_growth (+0.110) carry right-tail optionality; dividend_defensive (−0.250) and distressed (−0.154) have the heaviest left tails — losses are lumpy even when the median year is quiet.

Up-capture and down-capture diverge within archetypes in a revealing way. Cyclical (up 1.083, down 1.124) and speculative_unprofitable (up 1.323, down 1.249) both have down-capture exceeding up-capture, meaning their excess sensitivity is asymmetrically weighted toward bad days — momentum and cyclicality are not free lunches. Broken_growth is the lone case where down-capture (1.052) exceeds up-capture (0.924) by the largest spread, reflecting the secular deterioration in many broken-growth names. Dividend_defensive shows the mirror image: both capture ratios below 0.6, meaning it genuinely shelters in drawdowns and participates only partially in rallies. Quality_compounder shows the same pattern more mildly (up 0.660, dn 0.573), and has the lowest pct-never-recovered of any type (38%), confirming its bouncing-ball property within the OHLCV panel.

### Tables

| Archetype | N_obs | N_tickers | Vol_med | Vol_Q1 | Vol_Q3 | Beta_med | MaxDD_med | DD_dur_td | Recov_td | %NR_in_yr | UpCap | DnCap | Skew | Disp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| speculative_unprofitable | 291 | 83 | 0.378 | 0.279 | 0.506 | 1.258 | -0.272 | 108 | 39 | 52% | 1.323 | 1.249 | +0.116 | 0.544 |
| high_beta_momentum | 95 | 12 | 0.392 | 0.294 | 0.486 | 1.230 | -0.272 | 121 | 42 | 61% | 1.255 | 1.204 | -0.077 | 0.351 |
| secular_growth | 73 | 34 | 0.302 | 0.256 | 0.367 | 1.058 | -0.228 | 117 | 34 | 55% | 1.096 | 1.063 | +0.110 | 0.288 |
| broken_growth | 49 | 21 | 0.309 | 0.252 | 0.462 | 0.950 | -0.217 | 79 | 22 | 65% | 0.924 | 1.052 | +0.059 | 0.293 |
| rate_sensitive | 461 | 40 | 0.267 | 0.211 | 0.341 | 1.052 | -0.200 | 107 | 42 | 47% | 1.045 | 1.070 | -0.081 | 0.198 |
| deep_value | 76 | 6 | 0.266 | 0.230 | 0.312 | 0.881 | -0.196 | 106 | 36 | 57% | 0.850 | 0.863 | -0.095 | 0.197 |
| financial | 220 | 15 | 0.251 | 0.204 | 0.313 | 1.142 | -0.187 | 89 | 39 | 49% | 1.110 | 1.090 | +0.005 | 0.162 |
| cyclical | 393 | 30 | 0.255 | 0.215 | 0.327 | 1.107 | -0.184 | 98 | 37 | 48% | 1.083 | 1.124 | -0.010 | 0.208 |
| distressed | 153 | 40 | 0.242 | 0.192 | 0.285 | 0.676 | -0.167 | 102 | 34 | 55% | 0.693 | 0.862 | -0.154 | 0.194 |
| quality_compounder | 48 | 3 | 0.248 | 0.186 | 0.316 | 0.680 | -0.176 | 111 | 46 | 38% | 0.660 | 0.573 | +0.031 | 0.175 |
| mixed | 998 | 75 | 0.224 | 0.179 | 0.286 | 0.799 | -0.162 | 100 | 37 | 48% | 0.778 | 0.789 | -0.093 | 0.239 |
| dividend_defensive | 53 | 4 | 0.218 | 0.173 | 0.275 | 0.621 | -0.149 | 104 | 42 | 43% | 0.558 | 0.567 | -0.250 | 0.186 |

*Columns: Vol = annualized daily vol; DD_dur_td = trading days below rolling peak (median); Recov_td = trading days from trough to prior peak (median, among windows that recover); %NR_in_yr = pct of 1-yr windows where price never reclaimed prior peak; UpCap/DnCap = mean daily return ratio vs equal-weight panel on positive/negative bench days; Disp = cross-name std of annual return within same archetype-year.*

| Archetype | N_obs | N_tickers | Ann_Vol_median | Ann_Vol_IQR | Beta_median | Beta_IQR | MaxDD_median | MaxDD_IQR | DD_dur_td_median | DD_dur_td_IQR |
|---|---|---|---|---|---|---|---|---|---|---|
| speculative_unprofitable | 291 | 83 | 0.378 | [0.279, 0.506] | 1.258 | [0.892, 1.640] | -0.272 | [-0.413, -0.169] | 108 | [67, 157] |
| high_beta_momentum | 95 | 12 | 0.392 | [0.294, 0.486] | 1.230 | [0.975, 1.650] | -0.272 | [-0.360, -0.176] | 121 | [71, 170] |
| secular_growth | 73 | 34 | 0.302 | [0.256, 0.367] | 1.058 | [0.837, 1.317] | -0.228 | [-0.351, -0.152] | 117 | [75, 168] |
| broken_growth | 49 | 21 | 0.309 | [0.252, 0.462] | 0.950 | [0.694, 1.232] | -0.217 | [-0.348, -0.133] | 79 | [36, 131] |
| rate_sensitive | 461 | 40 | 0.267 | [0.211, 0.341] | 1.052 | [0.757, 1.370] | -0.200 | [-0.307, -0.124] | 107 | [63, 162] |
| deep_value | 76 | 6 | 0.266 | [0.230, 0.312] | 0.881 | [0.699, 1.095] | -0.196 | [-0.267, -0.141] | 106 | [63, 163] |
| financial | 220 | 15 | 0.251 | [0.204, 0.313] | 1.142 | [0.925, 1.386] | -0.187 | [-0.285, -0.122] | 89 | [53, 143] |
| cyclical | 393 | 30 | 0.255 | [0.215, 0.327] | 1.107 | [0.869, 1.392] | -0.184 | [-0.272, -0.116] | 98 | [55, 156] |
| distressed | 153 | 40 | 0.242 | [0.192, 0.285] | 0.676 | [0.447, 0.972] | -0.167 | [-0.244, -0.112] | 102 | [60, 153] |
| quality_compounder | 48 | 3 | 0.248 | [0.186, 0.316] | 0.680 | [0.450, 0.888] | -0.176 | [-0.227, -0.128] | 111 | [79, 157] |
| mixed | 998 | 75 | 0.224 | [0.179, 0.286] | 0.799 | [0.554, 1.085] | -0.162 | [-0.242, -0.103] | 100 | [56, 155] |
| dividend_defensive | 53 | 4 | 0.218 | [0.173, 0.275] | 0.621 | [0.493, 0.808] | -0.149 | [-0.213, -0.107] | 104 | [64, 160] |

### Notable findings

- speculative_unprofitable has the highest cross-name return dispersion by far (median annual std 0.544 vs 0.162 for financial) — the archetype label explains far less of the name outcome than in any other type.
- high_beta_momentum has the worst within-window recovery rate: 61% of label-year windows end without the price reclaiming its prior peak, vs 38% for quality_compounder. It also carries the longest median drawdown duration (121 trading days).
- broken_growth is the only archetype where down-capture (1.052) substantially exceeds up-capture (0.924), the widest gap of any type — directional asymmetry is structural, not incidental.
- dividend_defensive has the most left-skewed daily returns (median skew −0.250) — larger, chunkier losses relative to its low vol (0.218) than any other type; loss events are tail events even in a low-vol wrapper.
- distressed has beta 0.676 — lower than mixed (0.799) — but this masks idiosyncratic risk, not safety: vol (0.242) and drawdown depth (−0.167) are roughly average, and 55% of windows never recover within a year.
- cyclical and financial both run beta above 1.10 with down-capture exceeding up-capture (cyclical: up 1.083, dn 1.124; financial: up 1.110, dn 1.090) — both types are more sensitive on bad days than good days.
- secular_growth carries positive skew (+0.110) similar to speculative_unprofitable (+0.116) but at materially lower vol (0.302 vs 0.378) — the right tail is present with meaningfully less daily downside volatility.
- quality_compounder has the lowest pct-never-recovered (38%) despite a beta of only 0.680 — it bounces reliably from drawdowns even in a one-year window; its down-capture (0.573) is second-lowest of the 12 types, essentially tied with dividend_defensive (0.567).

### Coverage and caveats

- OHLCV panel covers only 194 of 1331 tickers in archetype history — these are the "deep name" set; results should not be generalized to the full 1331-ticker universe without verifying representativeness.
- commodity_sensitive archetype (76 obs in history) had zero tickers overlap with data/stocks/ and is absent from all tables.
- SPY was not found in data/stocks/ so the benchmark is an equal-weight mean of the 190 OHLCV tickers present — this is an internal panel benchmark, not a market-cap-weighted index; up/down capture ratios are relative to this panel, not SPY.
- quality_compounder (n_obs=48) and dividend_defensive (n_obs=53) are backed by only 3 and 4 tickers respectively — IQRs reflect year-over-year variation within those names, not cross-name spread. Treat with caution.
- Recovery days are computed within the ~1yr label window only; windows that end before recovery are coded as never-recovered — longer recovery events are truncated, so the "pct_never_recovered" includes cases that would eventually recover given more time.
- Label-year windows use asof_date from history.parquet, not calendar FY end; windows range from 21 to 375 trading days (median ~250); very short windows (<21 days) were excluded.
- Skew estimates from daily returns over ~250 trading days have wide sampling error; treat as directional signal only, not precision estimates.
- No regime conditioning applied; all FY2009–2025 years pooled — archetype fingerprints will differ across macro regimes, a dimension not decomposed in this lane.

---

## Section 2 — Chart-Personality Fingerprints

> **In plain English:** The five chart_primary labels differ most sharply on how long they persist, not on how volatile they are. failed_breakout_trap is the stickiest label by a wide margin (median 35 days) and the highest-vol label; mean_reversion_rubber_band is a quick-fire spike state lasting a median of 3 days. The two "uptrend" labels — smooth_compounder_grind and stair_step_leader — are the only ones with meaningful time at 52-week highs. mixed_chart absorbs everything: two-thirds of all rows, every other label exits into it first.

### Lane summary

The five chart_primary labels show meaningful differentiation on volatility, new-high exposure, and drawdown depth, but dwell time is the most operationally striking dimension. failed_breakout_trap is the highest-vol label (median 21d RVOL 27.7% annualized vs 20.3% for smooth_compounder_grind) and has the deepest typical pullbacks (median −3.5% from 21d high vs −2.4% for mean_reversion_rubber_band). Its median dwell time is 35 trading days — far longer than the other non-mixed labels (mean_reversion_rubber_band: 3 days, stair_step_leader: 10 days) — suggesting it is a genuine sticky state, not a transient classification. smooth_compounder_grind and stair_step_leader are the only two labels with materially elevated time-at-new-highs (11.6% and 12.4% of days respectively vs 3.8% for failed_breakout_trap), confirming they capture uptrend regimes.

mixed_chart is the dominant label (66% of all rows, 1.36M rows, 28,827 episodes) with a median dwell of 11 days and the widest IQR (2–55 days), making it a clear catch-all absorber rather than a crisp personality. Its transition behavior confirms this: when mixed_chart exits it flows to mean_reversion_rubber_band (41.7%) or smooth_compounder_grind (34.2%), suggesting it is a waiting room between directional states. mean_reversion_rubber_band is the most transient label (median dwell 3 days, 13,887 episodes) and exits overwhelmingly into mixed_chart (85.8%) — it is a spike state, not a sustained regime.

The label co-occurrence with micro_primary shows smooth_compounder_grind most strongly co-fires with tight_spread_absorber (43.8%) and never fires with gap_discontinuity_risk (0.0%), while failed_breakout_trap is the most evenly spread across micro labels, including the highest wide_spread_impact share (24.5%) among the non-mixed labels. Momentum persistence (21d sign agreement) is uniformly weak across all labels (0.504–0.511), spanning a near-random range — chart labels do not reliably predict short-term return sign persistence within their own periods. The transition matrix reveals that failed_breakout_trap and stair_step_leader never directly transition to each other (both show 0.000), always passing through mixed_chart first.

### Persistence tiers

Based on dwell-time distributions, the five labels sort into three persistence tiers:

| Tier | Labels | Median dwell |
|---|---|---|
| Spike state | mean_reversion_rubber_band | 3 days |
| Medium-persistence | stair_step_leader | 10 days |
| Catch-all / sticky | mixed_chart, failed_breakout_trap | 11–35 days |

smooth_compounder_grind (median dwell 4 days) sits closer to the spike tier despite its smooth-trend character — it fires frequently in short bursts rather than as long sustained regimes.

### Tables

| chart_primary | median_dwell_days | q25 | q75 | mean | max | n_episodes |
|---|---|---|---|---|---|---|
| failed_breakout_trap | 35.0 | 9.0 | 111.0 | 89.7 | 2004 | 2360 |
| mean_reversion_rubber_band | 3.0 | 1.0 | 8.0 | 7.9 | 199 | 13887 |
| mixed_chart | 11.0 | 2.0 | 55.0 | 47.1 | 2076 | 28827 |
| smooth_compounder_grind | 4.0 | 1.0 | 14.0 | 15.6 | 465 | 11958 |
| stair_step_leader | 10.0 | 3.0 | 28.0 | 21.4 | 267 | 8603 |

| chart_primary | rvol_21d_median | rvol_q25 | rvol_q75 | n_rows |
|---|---|---|---|---|
| failed_breakout_trap | 27.67% | 20.05% | 39.29% | 211,757 |
| mean_reversion_rubber_band | 23.44% | 16.90% | 34.13% | 109,671 |
| mixed_chart | 24.67% | 18.05% | 34.78% | 1,354,628 |
| smooth_compounder_grind | 20.28% | 15.51% | 26.80% | 186,967 |
| stair_step_leader | 23.65% | 17.04% | 34.12% | 183,908 |

| chart_primary | pct_at_252d_new_high | pullback_depth_median | pullback_depth_q25 | sideways_fraction | mom_persist_21d | n_rows |
|---|---|---|---|---|---|---|
| failed_breakout_trap | 3.8% | -3.48% | -7.38% | 8.7% | 0.504 | 211,757 |
| mean_reversion_rubber_band | 6.4% | -2.42% | -5.30% | 17.7% | 0.511 | 109,738 |
| mixed_chart | 6.0% | -2.97% | -6.47% | 10.3% | 0.505 | 1,356,791 |
| smooth_compounder_grind | 11.6% | -2.36% | -5.20% | 12.4% | 0.508 | 186,967 |
| stair_step_leader | 12.4% | -2.39% | -5.71% | 7.3% | 0.507 | 183,908 |

**Transition matrix — P(to | from):**

| from \ to | failed_breakout_trap | mean_reversion_rubber_band | mixed_chart | smooth_compounder_grind | stair_step_leader |
|---|---|---|---|---|---|
| failed_breakout_trap | — | 0.064 | 0.887 | 0.049 | 0.000 |
| mean_reversion_rubber_band | 0.014 | — | 0.858 | 0.000 | 0.128 |
| mixed_chart | 0.072 | 0.417 | — | 0.342 | 0.169 |
| smooth_compounder_grind | 0.008 | 0.000 | 0.826 | — | 0.166 |
| stair_step_leader | 0.000 | 0.205 | 0.556 | 0.238 | 0.000 |

**Chart label × micro_primary co-occurrence:**

| chart_primary | gap_discontinuity_risk | mixed_microstructure | slow_mean_reversion_liquidity | tight_spread_absorber | wide_spread_impact |
|---|---|---|---|---|---|
| failed_breakout_trap | 0.006 | 0.290 | 0.203 | 0.256 | 0.245 |
| mean_reversion_rubber_band | 0.005 | 0.233 | 0.156 | 0.412 | 0.195 |
| mixed_chart | 0.005 | 0.226 | 0.126 | 0.337 | 0.306 |
| smooth_compounder_grind | 0.000 | 0.171 | 0.097 | 0.438 | 0.294 |
| stair_step_leader | 0.003 | 0.237 | 0.118 | 0.437 | 0.204 |

### Notable findings

- failed_breakout_trap has the highest realized vol (median 27.7% RVOL vs 20.3% for smooth_compounder_grind, a 7.4pp spread) and deepest median pullback from 21d high (−3.48% vs −2.36% for smooth_compounder_grind).
- failed_breakout_trap has median dwell of 35 days — nearly 4x stair_step_leader (10d) and 12x mean_reversion_rubber_band (3d) — making it the stickiest non-mixed personality.
- mean_reversion_rubber_band is a spike state: median dwell 3 days, 13,887 episodes (most episodes of any label), exits to mixed_chart 85.8% of the time.
- smooth_compounder_grind and stair_step_leader are the only labels with materially elevated new-high exposure: 11.6% and 12.4% of days at a 252d new high, vs 3.8% for failed_breakout_trap.
- mixed_chart dominates with 66% of all rows (1.36M) and is the gravitational attractor: every other label transitions into it as its primary exit route (55–89% of transitions).
- failed_breakout_trap and stair_step_leader never directly transition to each other (0.000 in both directions) — mixed_chart is always the intermediary.
- smooth_compounder_grind is the only label that never co-fires with gap_discontinuity_risk (0.000 co-occurrence) and most strongly co-fires with tight_spread_absorber (43.8%).
- Momentum persistence (21d sign agreement) is uniformly 0.504–0.511 across all labels — near-random, no label shows meaningful intra-period directional persistence at the 21d horizon.
- mean_reversion_rubber_band has the highest sideways fraction (17.7% of days have 63d range < 10%) vs stair_step_leader which has the lowest (7.3%), consistent with their names.
- Pullback duration (continuous days > 2% below 21d high) is nearly identical across labels: all show median 2–3 days and similar IQRs — label does not predict how long a pullback lasts once started.

### Coverage and caveats

- Universe is 223 deep-name tickers only — stock_personality.json has 1,722 labeled names but no price history is git-tracked for the other ~1,500; all metrics here reflect the deep-name subset.
- OHLCV in data/stocks/ has no "open" column — intraday gap metrics (e.g., gap-open magnitude) are not computable from this store.
- mixed_chart covers 66% of rows and acts as a catch-all; the descriptive stats for this label reflect its heterogeneous nature, not a clean personality type.
- Momentum persistence near 0.50 for all labels is expected given the data spans 1963–2026 and includes multiple secular regimes — within-label sign agreement is diluted by regime changes across decades, not a deficiency of the label system.
- Pullback depth is measured from rolling 21d high (not a proper drawdown series) — it understates true peak-to-trough by construction for episodes with multiple interim recoveries.
- Dwell time reflects the label as assigned by the pit-label pipeline, which may reassign labels retroactively on each nightly run; the PIT guarantee of the labels file is based on archetype_asof, not the chart_primary column independently.
- All 5 labels have n >= 109k rows and >= 213 unique tickers — no small-n flag required at label level.

---

## Section 3 — Archetype × Regime Interaction

> **In plain English:** Most archetypes post positive median forward returns in every macro quad — but the spread between their best and worst quad can be 3+ percentage points, and the tail losses differ sharply. secular_growth is the most regime-dependent type (swings from −1.1% median in stagflation to +3.1% in the deflation quad), while dividend_defensive is the closest thing to an all-weather type. The "recession-period" medians look strong but are almost entirely an artifact of the violent 2020 COVID snap-back, not a structural pattern.

### Lane summary

Across 194 deep tickers, 687,221 ticker-date observations (2009–2026), and 12 archetypes joined to daily regime states via PIT merge_asof, the headline finding is that median 21d returns are positive across virtually every archetype × regime cell — but the dispersion, tail risk, and sensitivity to regime torque differ sharply by type.

The clearest regime-torqued type is secular_growth: median 21d return of +3.1% in Q4 (growth falling, inflation falling) but negative medians in Q2 (−0.2%) and Q3 (−1.1%). It also carries the second-heaviest worst-decile loss in Q3 (−11.4%), tied with speculative_unprofitable. The contrast with dividend_defensive is stark: dividend_defensive shows near-flat median returns across all four quads (1.0%–1.7%), the tightest IQRs, and the shallowest worst-decile losses in the universe (−5.6% to −6.5%). It is the closest thing to an all-weather type in this universe.

high_beta_momentum and speculative_unprofitable do NOT die in the way the conventional narrative predicts. high_beta_momentum actually posts its best median in Q4 (+2.8%) — not in Q2 where growth is strongest. speculative_unprofitable shows its highest median in Q3 (+2.6%), a counterintuitive result that reflects the concentrated 2021+ period (post-COVID bounce dynamics). Both types carry the heaviest realized vol (0.29–0.38 annualized) and worst tails (P10 losses of −10.4% to −11.7%), especially in Q4, where high_beta_momentum's P10 hits −12.8%. On liquidity, speculative_unprofitable shows the sharpest expanding-vs-contracting gap: +2.6% median when liquidity expands vs +1.1% when it contracts — nearly 2.5x. distressed is the most liquidity-sensitive type in absolute terms: +1.2% expanding vs +0.4% contracting, suggesting it lives and dies by credit conditions more than any quad label.

The recession flag (53,816 obs out of 687K total) shows an unusual pattern: most types print higher medians during recession-flagged periods than outside them. This is an artifact of the 2020 COVID recession, where the flag was active during the violent snap-back in March–June 2020. broken_growth (+8.3% in recession, n=185) and secular_growth (+7.7%, n=1,110) show the most extreme recession-period medians — but small-n and event-concentration caveats apply heavily here. Chart-label matrices (2021+ only, 5 labels): all five types go near-zero or negative in Q3 (growth down, inflation up), with mean_reversion_rubber_band showing −0.6% and stair_step_leader −0.2%. Q4 is the best quad for all chart labels, led by failed_breakout_trap (+2.7%) and stair_step_leader (+2.4%).

### Tables

#### Table 1: Archetype × Quad — Median 21d Forward Return (n in parentheses)

| Archetype | Q1 | Q2 | Q3 | Q4 |
|-----------|-----|-----|-----|-----|
| broken_growth | 0.023 (n=1926) | 0.003 (n=3406) | 0.008 (n=1196) | 0.025 (n=3251) |
| cyclical | 0.011 (n=16404) | 0.014 (n=43947) | 0.013 (n=7012) | 0.023 (n=25543) |
| deep_value | 0.015 (n=3268) | 0.013 (n=8458) | 0.024 (n=1383) | 0.013 (n=4927) |
| distressed | 0.012 (n=6428) | 0.003 (n=10823) | 0.006 (n=3925) | 0.013 (n=9514) |
| dividend_defensive | 0.014 (n=2163) | 0.016 (n=6185) | 0.017 (n=887) | 0.010 (n=3623) |
| financial | 0.016 (n=9355) | 0.014 (n=24034) | 0.012 (n=4120) | 0.025 (n=14348) |
| high_beta_momentum | 0.013 (n=3708) | 0.015 (n=10733) | 0.010 (n=1648) | 0.028 (n=6008) |
| mixed | 0.014 (n=42616) | 0.014 (n=115044) | 0.008 (n=17345) | 0.015 (n=65512) |
| quality_compounder | 0.017 (n=2087) | 0.012 (n=5233) | 0.013 (n=872) | 0.014 (n=3198) |
| rate_sensitive | 0.007 (n=19340) | 0.013 (n=49923) | 0.009 (n=8434) | 0.020 (n=31623) |
| secular_growth | 0.015 (n=3370) | -0.002 (n=6024) | -0.011 (n=2160) | 0.031 (n=5861) |
| speculative_unprofitable | 0.020 (n=13559) | 0.014 (n=33208) | 0.026 (n=5992) | 0.024 (n=17597) |

*Quads: Q1=growth↑inflation↑, Q2=growth↑inflation↓, Q3=growth↓inflation↑, Q4=growth↓inflation↓. No small-n cells; minimum n=887 (dividend_defensive/Q3).*

#### Table 2: Archetype × Quad — Worst-Decile (P10) 21d Return | Median Annualized Vol

| Archetype | Q1 worst/vol | Q2 worst/vol | Q3 worst/vol | Q4 worst/vol |
|-----------|-----|-----|-----|-----|
| broken_growth | -0.093 / 0.24 | -0.114 / 0.27 | -0.093 / 0.28 | -0.089 / 0.31 |
| cyclical | -0.073 / 0.21 | -0.071 / 0.22 | -0.081 / 0.24 | -0.085 / 0.26 |
| deep_value | -0.067 / 0.21 | -0.079 / 0.23 | -0.056 / 0.26 | -0.081 / 0.25 |
| distressed | -0.072 / 0.19 | -0.089 / 0.22 | -0.087 / 0.22 | -0.064 / 0.23 |
| dividend_defensive | -0.065 / 0.18 | -0.061 / 0.19 | -0.056 / 0.20 | -0.064 / 0.22 |
| financial | -0.060 / 0.20 | -0.071 / 0.21 | -0.087 / 0.24 | -0.080 / 0.25 |
| high_beta_momentum | -0.104 / 0.29 | -0.106 / 0.31 | -0.107 / 0.35 | -0.128 / 0.37 |
| mixed | -0.060 / 0.19 | -0.063 / 0.19 | -0.071 / 0.21 | -0.070 / 0.21 |
| quality_compounder | -0.062 / 0.20 | -0.067 / 0.20 | -0.078 / 0.22 | -0.076 / 0.23 |
| rate_sensitive | -0.077 / 0.21 | -0.075 / 0.22 | -0.087 / 0.25 | -0.087 / 0.27 |
| secular_growth | -0.087 / 0.26 | -0.100 / 0.27 | -0.114 / 0.31 | -0.078 / 0.30 |
| speculative_unprofitable | -0.099 / 0.32 | -0.112 / 0.30 | -0.114 / 0.38 | -0.117 / 0.37 |

#### Table 3: Archetype × Liquidity — Median 21d Forward Return (n)

| Archetype | Expanding | Neutral | Contracting |
|-----------|-----------|---------|-------------|
| broken_growth | 0.018 (n=4068) | 0.017 (n=1430) | 0.013 (n=4281) |
| cyclical | 0.021 (n=43472) | 0.010 (n=19349) | 0.011 (n=30085) |
| deep_value | 0.020 (n=8261) | 0.011 (n=3705) | 0.008 (n=6070) |
| distressed | 0.012 (n=12852) | 0.008 (n=4618) | 0.004 (n=13220) |
| dividend_defensive | 0.017 (n=5878) | 0.013 (n=2879) | 0.011 (n=4101) |
| financial | 0.021 (n=24054) | 0.015 (n=10626) | 0.013 (n=17177) |
| high_beta_momentum | 0.025 (n=10639) | 0.007 (n=4547) | 0.011 (n=6911) |
| mixed | 0.017 (n=112559) | 0.013 (n=51055) | 0.010 (n=76903) |
| quality_compounder | 0.018 (n=5291) | 0.010 (n=2284) | 0.010 (n=3815) |
| rate_sensitive | 0.019 (n=50494) | 0.011 (n=22257) | 0.006 (n=36569) |
| secular_growth | 0.017 (n=6901) | 0.010 (n=2588) | 0.006 (n=7926) |
| speculative_unprofitable | 0.026 (n=32195) | 0.015 (n=14294) | 0.011 (n=23867) |

*Liquidity "unknown" state (~8,360 regime rows) excluded.*

#### Table 4: Archetype × Recession — Median 21d Forward Return (n)

| Archetype | No Recession | Recession |
|-----------|-------------|----------|
| broken_growth | 0.015 (n=9594) | 0.083 (n=185) |
| cyclical | 0.015 (n=85145) | 0.027 (n=7761) |
| deep_value | 0.014 (n=16612) | 0.018 (n=1424) |
| distressed | 0.007 (n=29913) | 0.060 (n=777) |
| dividend_defensive | 0.014 (n=11625) | 0.021 (n=1233) |
| financial | 0.016 (n=47839) | 0.028 (n=4018) |
| high_beta_momentum | 0.018 (n=20129) | 0.017 (n=1968) |
| mixed | 0.013 (n=219973) | 0.025 (n=20544) |
| quality_compounder | 0.013 (n=10497) | 0.029 (n=893) |
| rate_sensitive | 0.012 (n=100245) | 0.032 (n=9075) |
| secular_growth | 0.007 (n=16305) | 0.077 (n=1110) |
| speculative_unprofitable | 0.018 (n=65528) | 0.029 (n=4828) |

*Recession obs heavily concentrated in 2020 COVID snap-back. Elevated recession medians reflect bounce dynamics, not outperformance in a typical recession.*

#### Table 5: Chart Label × Quad — Median 21d Return, 2021+ (n) [194 deep tickers only]

| Chart Label | Q1 | Q2 | Q3 | Q4 |
|-------------|-----|-----|-----|-----|
| failed_breakout_trap | 0.016 (n=4568) | 0.012 (n=9339) | 0.000 (n=3068) | 0.027 (n=6683) |
| mean_reversion_rubber_band | 0.016 (n=2399) | 0.013 (n=5502) | -0.006 (n=1000) | 0.016 (n=3717) |
| mixed_chart | 0.014 (n=35539) | 0.005 (n=65567) | 0.001 (n=20761) | 0.023 (n=46164) |
| smooth_compounder_grind | 0.014 (n=4090) | 0.002 (n=7988) | 0.006 (n=3490) | 0.014 (n=5516) |
| stair_step_leader | 0.011 (n=4983) | 0.008 (n=10389) | -0.002 (n=3375) | 0.024 (n=6434) |

*Chart labels from personality_pit_labels.parquet; 2021+ only due to column availability constraint noted in memory. All five types go flat or negative in Q3.*

#### Table 6: Chart Label × Liquidity — Median 21d Return, 2021+ (n)

| Chart Label | Expanding | Neutral | Contracting |
|-------------|-----------|---------|-------------|
| failed_breakout_trap | 0.025 (n=10204) | 0.016 (n=3659) | 0.006 (n=9795) |
| mean_reversion_rubber_band | 0.014 (n=5533) | 0.018 (n=1913) | 0.012 (n=5172) |
| mixed_chart | 0.017 (n=74986) | 0.011 (n=25271) | 0.006 (n=67774) |
| smooth_compounder_grind | 0.012 (n=9568) | 0.010 (n=3217) | 0.004 (n=8299) |
| stair_step_leader | 0.014 (n=10514) | 0.011 (n=3828) | 0.009 (n=10839) |

*mean_reversion_rubber_band is notable: neutral liquidity (0.018) slightly beats expanding (0.014) — the most regime-independent chart type on this axis.*

### Notable findings

- secular_growth is the most regime-torqued archetype: +3.1% median in Q4 (deflation quad) vs −1.1% in Q3 (stagflation quad), with worst-decile loss of −11.4% in Q3 vs −7.8% in Q4 — a 330bp median swing across quads.
- dividend_defensive is the closest all-weather type: median range 1.0%–1.7% across all four quads, lowest realized vol (0.18–0.22), and shallowest worst-decile losses (−5.6% to −6.5%) — smallest P10 drawdown in the entire universe.
- high_beta_momentum does NOT peak in Q2 (strong growth) as the narrative predicts; it peaks in Q4 (+2.8% median) and Q2 (+1.5%), with its worst-decile tail largest also in Q4 (−12.8%). The median story and the tail story point in the same direction: Q4 is both best and riskiest.
- speculative_unprofitable posts its highest quad median in Q3 (+2.6%), the stagflation quad — counterintuitive and likely driven by 2021+ period concentration (post-COVID dynamics dominate the Q3 cell).
- distressed is the most liquidity-sensitive archetype: expanding +1.2% vs contracting +0.4%, a 3x ratio — the largest expanding/contracting spread in the universe. rate_sensitive and secular_growth show the second-largest gaps (both 0.013 expanding vs 0.006 contracting).
- The recession-period medians are uniformly higher than non-recession for almost every archetype (broken_growth +8.3%, secular_growth +7.7%, distressed +6.0% vs non-recession medians near 0.7%–1.5%). This is an artifact of the 2020 snap-back dominating the single recession episode in the 2009–2026 window — not a structural finding.
- high_beta_momentum shows near-zero recession sensitivity (+1.7% recession vs +1.8% non-recession) — the only archetype with effectively no median difference — suggesting it responds to momentum conditions, not macro cycle state per se.
- In the chart-label matrices (2021+, 5 types), all five go flat or negative in Q3: failed_breakout_trap 0.000, mean_reversion_rubber_band −0.006, stair_step_leader −0.002. Q3 is a universal headwind regardless of chart pattern. smooth_compounder_grind is the exception with Q3=+0.006 — mildest degradation.

### Coverage and caveats

- Universe is 194 tickers (deep OHLCV names intersecting archetype coverage) out of 1,331 archetypes tickers and 1,722 production labels. Results describe the deep-research subset, not the full 1,722-name universe.
- Annual PIT archetype labels (asof_date from history.parquet) leave 1.09M of 1.78M price rows unlabeled (pre-first-asof-date gaps per ticker). These rows are excluded.
- The single recession episode in the 2009–2026 window is the COVID-19 recession (2020), which coincides with a violent price snap-back. Recession-period medians should NOT be read as "recessions are good for returns"; they reflect bounce dynamics from the March 2020 trough. A true recession-drawdown regime would require a different regime definition.
- Liquidity "unknown" state covers ~8,360 regime rows and is excluded from the liquidity matrix. This state appears concentrated in pre-2000 history.
- 21d forward return uses a 21-row shift on daily OHLCV (i.e., ~21 trading days forward, not calendar days). No overlap correction applied — consecutive rows from the same ticker are correlated at the 21d horizon. Cell n counts are observation counts, not independent events.
- Chart label matrices are restricted to 2021+ due to the availability constraint documented in oracle-panel-column-coverage memory (breadth/cohesion columns 2021+ only — same underlying coverage applies to chart labels in personality_pit_labels.parquet). Only 5 chart label types appear in the 194-ticker OHLCV universe; the full 223-ticker PIT file may contain more.
- deep_value Q3 cell shows an anomalously high median (+2.4%, the highest of any archetype in Q3). This is worth inspection — Q3 has n=1,383 for deep_value, which is adequate but the median may be driven by specific tickers during the 2022 energy/commodity-driven stagflation period when value outperformed.

---

## Section 4 — Archetype Migrations

> **In plain English:** Most archetypes are extremely sticky year to year — financial names almost never reclassify (P(stay)=0.958), and cyclical names usually stay cyclical for five or more years. The big exception is speculative_unprofitable, which is both a transient state for many companies and the gravity well the whole ecosystem drains into when things go wrong — every other archetype routes most of its exits there. The rate_sensitive ↔ speculative_unprofitable shuttle is the most active revolving door in the dataset.

### Lane summary

Archetype labels are highly stable year-over-year for most types, but two types — broken_growth and secular_growth — are genuinely transient way-stations with median dwell of 1 year and P(stay) around 0.56. Financial (P(stay)=0.958) and dividend_defensive (0.915) are the stickiest terminal states in the dataset, with 70% and 50% of runs lasting 5+ years respectively. The speculative_unprofitable type is the ecosystem's gravity well: it receives exits from nearly every other type (7 of 12 types route 43–91% of their exits there), and itself has the third-lowest stickiness (0.589) — acting more as a sorting clearinghouse than a durable label. Cyclical and rate_sensitive are large semi-stable clusters with P(stay) ~0.89–0.90 but notably bidirectional with speculative_unprofitable, suggesting a revolving door at the growth/quality boundary.

On price behavior, the most informative contrast is speculative_unprofitable → rate_sensitive vs the reverse. The upgrade path (spec → rate_sensitive, n=37) is preceded by a strong change-year median return of +29.5% (IQR 0% to +66%), but post-label returns cool to +8.3% median — consistent with the label change being a lagging acknowledgment of price recovery that already happened. The downgrade path (rate_sensitive → speculative_unprofitable, n=30) shows a milder change-year of +5.8% and then a notably strong post-label year of +14.8% (IQR +0.3% to +62%), which is counterintuitive but likely reflects mean-reversion in smaller names reclassified downward. All price observations are from the 227-stock deep OHLCV universe (~12% coverage of the full 1,331-ticker history), so the price numbers carry a survivorship/selection bias caveat.

The most common 3-year trajectories beyond pure stays are the speculative_unprofitable ↔ rate_sensitive shuttle (193 and 163 observed 3-year paths) and speculative_unprofitable entering cyclical/mixed as growth firms mature — or the reverse as those firms lose quality. Secular_growth exits predominantly to cyclical (66) and mixed (61) rather than distressed, suggesting most secular growth fades gracefully rather than catastrophically. The broken_growth → recovery path back to secular_growth exists (15 observed) but is outnumbered by broken_growth → mixed (20) and broken_growth → speculative_unprofitable (13).

### Tables

#### Transition Matrix — P(to | from), n=18,153 consecutive-year pairs

| from \ to | broken_growth | commodity_sensitive | cyclical | deep_value | distressed | dividend_defensive | financial | high_beta_momentum | mixed | quality_compounder | rate_sensitive | secular_growth | speculative_unprofitable | n_depart |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broken_growth | **0.564** | 0.000 | 0.067 | 0.011 | 0.011 | 0.011 | 0.000 | 0.028 | 0.112 | 0.039 | 0.000 | 0.084 | 0.073 | 179 |
| commodity_sensitive | 0.000 | **0.838** | 0.000 | 0.000 | 0.014 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.149 | 74 |
| cyclical | 0.006 | 0.000 | **0.904** | 0.000 | 0.007 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.029 | 0.054 | 3,086 |
| deep_value | 0.014 | 0.000 | 0.000 | **0.868** | 0.022 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.026 | 0.069 | 418 |
| distressed | 0.001 | 0.000 | 0.013 | 0.003 | **0.820** | 0.001 | 0.007 | 0.004 | 0.019 | 0.000 | 0.020 | 0.008 | 0.104 | 756 |
| dividend_defensive | 0.009 | 0.000 | 0.000 | 0.000 | 0.021 | **0.915** | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.015 | 0.041 | 340 |
| financial | 0.000 | 0.000 | 0.000 | 0.000 | 0.008 | 0.000 | **0.958** | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.034 | 2,721 |
| high_beta_momentum | 0.012 | 0.000 | 0.000 | 0.000 | 0.009 | 0.000 | 0.000 | **0.785** | 0.000 | 0.000 | 0.000 | 0.041 | 0.153 | 582 |
| mixed | 0.011 | 0.000 | 0.000 | 0.000 | 0.015 | 0.000 | 0.000 | 0.000 | **0.897** | 0.000 | 0.000 | 0.023 | 0.054 | 3,670 |
| quality_compounder | 0.026 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | **0.906** | 0.000 | 0.026 | 0.041 | 341 |
| rate_sensitive | 0.000 | 0.000 | 0.000 | 0.000 | 0.019 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | **0.894** | 0.000 | 0.087 | 2,832 |
| secular_growth | 0.056 | 0.000 | 0.143 | 0.017 | 0.009 | 0.011 | 0.000 | 0.028 | 0.132 | 0.007 | 0.000 | **0.564** | 0.033 | 461 |
| speculative_unprofitable | 0.003 | 0.003 | 0.063 | 0.010 | 0.052 | 0.006 | 0.043 | 0.036 | 0.085 | 0.010 | 0.099 | 0.002 | **0.589** | 2,693 |

#### Dwell Time per Archetype

| archetype | n_runs | median_dwell (yrs) | p25 | p75 | % dwell=1yr | % dwell≥5yr |
|---|---|---|---|---|---|---|
| broken_growth | 117 | 1.0 | 1.0 | 2.0 | 56% | 7% |
| commodity_sensitive | 14 [SMALL-N] | 4.0 | 2.0 | 8.5 | 14% | 50% |
| cyclical | 491 | 5.0 | 2.0 | 11.0 | 13% | 53% |
| deep_value | 76 | 4.0 | 2.0 | 10.0 | 16% | 49% |
| distressed | 321 | 2.0 | 1.0 | 5.0 | 36% | 28% |
| dividend_defensive | 48 | 5.0 | 3.0 | 12.0 | 10% | 50% |
| financial | 298 | 11.0 | 3.0 | 16.0 | 10% | 70% |
| high_beta_momentum | 165 | 2.0 | 1.0 | 5.0 | 32% | 25% |
| mixed | 598 | 4.0 | 2.0 | 11.0 | 21% | 50% |
| quality_compounder | 61 | 4.0 | 2.0 | 10.0 | 18% | 46% |
| rate_sensitive | 487 | 4.0 | 2.0 | 10.0 | 23% | 50% |
| secular_growth | 249 | 2.0 | 1.0 | 3.0 | 45% | 6% |
| speculative_unprofitable | 1,270 | 1.0 | 1.0 | 2.0 | 57% | 9% |

#### Price Behavior Around Top 6 Transitions (deep-OHLCV subsample, n_tickers_covered=56 of 476 targeted)

Change year = 1yr return ending at label-assignment date (lagged ~5mo after FY end). Post year = 1yr return starting from label-assignment date.

| transition | n | small_n | change_year_med | change_year_IQR | post_year_med | post_year_IQR |
|---|---|---|---|---|---|---|
| spec_unprofitable → rate_sensitive | 37 | no | +29.5% | [0%, +66%] | +8.3% | [-7.5%, +21.8%] |
| rate_sensitive → spec_unprofitable | 30 | no | +5.8% | [-15.3%, +25.5%] | +14.8% | [+0.3%, +61.7%] |
| spec_unprofitable → mixed | 17 | YES | +30.7% | [+12.6%, +37.4%] | +14.1% | [-6.1%, +31.3%] |
| mixed → spec_unprofitable | 15 | YES | +9.4% | [-1.7%, +40.7%] | +26.5% | [+3.7%, +37.8%] |
| spec_unprofitable → cyclical | 20 | YES | +13.7% | [0%, +21.1%] | +1.2% | [-11.7%, +16.3%] |
| cyclical → spec_unprofitable | 15 | YES | +11.9% | [-3.6%, +24.2%] | +20.8% | [+10.9%, +52.7%] |

#### Most Common 3-Year Paths (top 15, includes stay-paths)

| path | count |
|---|---|
| mixed → mixed → mixed | 2,817 |
| cyclical → cyclical → cyclical | 2,366 |
| financial → financial → financial | 2,338 |
| rate_sensitive → rate_sensitive → rate_sensitive | 2,155 |
| spec_unprofitable → spec_unprofitable → spec_unprofitable | 1,041 |
| distressed → distressed → distressed | 414 |
| high_beta_momentum → high_beta_momentum → high_beta_momentum | 345 |
| deep_value → deep_value → deep_value | 299 |
| dividend_defensive → dividend_defensive → dividend_defensive | 268 |
| quality_compounder → quality_compounder → quality_compounder | 259 |
| spec_unprofitable → rate_sensitive → rate_sensitive | 193 |
| rate_sensitive → rate_sensitive → spec_unprofitable | 163 |
| spec_unprofitable → mixed → mixed | 154 |
| spec_unprofitable → cyclical → cyclical | 138 |
| spec_unprofitable → spec_unprofitable → rate_sensitive | 132 |

#### Exit Destination When Type Changes (top 2 per type, among 2,862 change events)

| from | 1st exit dest | n | 2nd exit dest | n | note |
|---|---|---|---|---|---|
| broken_growth | mixed | 20 | secular_growth | 15 | balanced; can recover |
| commodity_sensitive | spec_unprofitable | 11 | — | — | near-monopoly exit (SMALL-N n=13) |
| cyclical | spec_unprofitable | 171 | secular_growth | 57 | 56% of exits go down |
| deep_value | spec_unprofitable | 27 | secular_growth | 11 | |
| distressed | spec_unprofitable | 79 | rate_sensitive | 15 | majority sink further |
| dividend_defensive | spec_unprofitable | 14 | distressed | 7 | SMALL-N exits |
| financial | spec_unprofitable | 74 | distressed | 6 | 80% of exits to spec |
| high_beta_momentum | spec_unprofitable | 70 | secular_growth | 24 | 71% sink |
| mixed | spec_unprofitable | 104 | secular_growth | 45 | 52% sink |
| quality_compounder | broken_growth | 9 | spec_unprofitable | 9 | SMALL-N exits |
| rate_sensitive | spec_unprofitable | 202 | distressed | 15 | 82% of exits to spec |
| secular_growth | cyclical | 66 | mixed | 61 | orderly fade; rarely distressed |
| spec_unprofitable | rate_sensitive | 267 | mixed | 228 | escape routes, not sinks |

### Notable findings

- Financial is the stickiest type (P(stay)=0.958, median dwell 11 yrs, 70% of runs last 5+yr) — once a company is classified as a financial, it almost never reclassifies.
- broken_growth and secular_growth share the lowest stickiness (both 0.564) despite being conceptually opposite — both are transient states the model passes through, not long-term identities.
- speculative_unprofitable receives exits from 12 of 12 other types (majority route for 7 of them at 43–91% of exits each) — it is the ecosystem's gravity well, absorbing downgrade flows across all categories.
- The secular_growth → distressed direct path is rare (4 observed); the modal degradation runs secular_growth → cyclical (66) or → mixed (61) before any further decline, suggesting quality erosion is usually gradual.
- Upgrade transitions (spec_unprofitable → rate_sensitive, n=37) show the label change is a lag: median +29.5% return already earned in the change year, with only +8.3% in the post-label year.
- The rate_sensitive ↔ speculative_unprofitable revolving door accounts for 513 of 2,862 change events (18%) — the single largest pair of bidirectional flows in the dataset.
- distressed is a moderate-stickiness trap (P(stay)=0.820, median dwell 2yr), not a one-year label — 28% of distressed runs last 5+ years, indicating a sizeable cohort of permanently impaired names.

### Coverage and caveats

- history.parquet: 1,331 tickers, FY2009–2025, 19,487 rows; most tickers have 14–17 consecutive years of coverage (median 16yr); 18,153 consecutive-year pairs used for transition matrix.
- Deep OHLCV price coverage: only 227 of 1,331 archetype tickers have a parquet in data/stocks/; for top-6 transition price analysis, 56 of 476 targeted tickers were available (~12% coverage). Price stats carry survivorship/selection bias — deeper names are likely larger and more liquid.
- commodity_sensitive has only 74 departure observations and 14 dwell runs — all stats for this type should be treated as SMALL-N. Similarly dividend_defensive (48 runs), quality_compounder (61 runs), and broken_growth (117 runs) have small dwell-run counts.
- Transition pairs require consecutive FY years (fy+1 = fy); gaps in coverage (ticker enters/exits dataset) break the chain and are excluded — this slightly underestimates year-over-year change rates for tickers with data gaps.
- asof_date is the label-assignment date (~5 months after FY end for most filers); price return windows are anchored to asof_date, so "change year" return reflects the pre-label-known price move and "post year" is the first full year the label is public information.

---

## Section 5 — Signal Composition (What Fires on What)

> **In plain English:** The fire engine is not neutral across chart personality types. It structurally over-selects names in broken or failed technical states (failed_breakout_trap fires at 1.18x its universe share, rising to 1.41x at the highest conviction tier) and structurally under-selects names in clean uptrends (stair_step_leader at 0.68x, collapsing to 0.35x at the top tier). This is a description of what the system does — not an evaluation of whether that is the correct behavior. Archetype type is nearly irrelevant to whether a fire lands on a name; chart label is the dominant selection axis.

### Lane summary

The 223-name deep universe has 26,491 buy+rebuy fires in track_record (1962–2026-07-06). Fires distribute across chart_primary types nearly in proportion to the universe, but the deviations are consistent and directional. failed_breakout_trap is the most over-represented chart type among buy/rebuy fires (ratio 1.18 vs universe), while stair_step_leader is the most under-represented (ratio 0.68). This pattern sharpens dramatically in gate_fires_deep: at T3 (the highest-conviction gate tier) stair_step_leader fires at only 0.35x its universe share, and smooth_compounder_grind at 0.41x, while failed_breakout_trap reaches 1.41x. The implication is that the system is structurally biased toward names in technical distress or failed-pattern states, and systematically cold on names in clean structural uptrends. Archetype over/under-representation is muted: no archetype departs from 1.0 by more than ~10% in the buy/rebuy universe, suggesting the signal engine fires across fundamental types without strong selection — the chart label, not the fundamental archetype, drives the composition skew.

Calendar clustering between rubber_band and stair_step is real but modest. rubber_band fires cluster in April (+3.6pp over stair_step) and Q2 (+2.7pp), while stair_step fires cluster in Q4 (+3.1pp) and are modestly heavier in June, July, and October. Era analysis reveals the most material divergence: rubber_band fires were almost entirely absent during the 2022–2023 tightening cycle (ratio 0.36 vs universe) while stair_step maintained near-parity (ratio 1.16). Conversely, rubber_band fired at elevated rates during the GFC (1.37x) and QE era (1.37x) — periods of large mean-reversion opportunities. The compounder type avoided the GFC entirely (ratio 0.58) and returned to parity in the QE era, consistent with its smooth-trend character requiring low-stress environments. near_miss n=14 is too small for any composition inference; all figures are printed with small-n flags.

Micro_primary composition shows almost no departure from universe proportions for any category: ratios range from 0.972 (wide_spread_impact) to 1.050 (slow_mean_reversion_liquidity). The engine does not systematically prefer any microstructure type, meaning the chart-label selection is the dominant personality dimension in fire composition. gate_fires_deep covered 98.6% of rows with an exact pit-label match, giving reliable tier-split analysis.

### Tables

#### Chart Primary — buy+rebuy fires vs universe (n_fires=25,425 labeled of 26,491)

| chart_primary | fire_n | fire_share% | univ_share% | ratio |
|---|---|---|---|---|
| failed_breakout_trap | 3,110 | 12.23 | 10.33 | 1.184 |
| mixed_chart | 17,384 | 68.37 | 66.21 | 1.033 |
| mean_reversion_rubber_band | 1,385 | 5.45 | 5.36 | 1.017 |
| smooth_compounder_grind | 2,000 | 7.87 | 9.12 | 0.862 |
| stair_step_leader | 1,546 | 6.08 | 8.97 | 0.678 |

#### Chart Primary — gate_fires_deep by tier (n_univ=2,049,161 labeled rows)

| chart_primary | T1 ratio (n=33,855) | T2 ratio (n=2,556) | T3 ratio (n=1,317) |
|---|---|---|---|
| failed_breakout_trap | 1.112 | 1.363 | 1.411 |
| mean_reversion_rubber_band | 0.967 | 1.147 | 1.262 |
| mixed_chart | 1.005 | 1.047 | 1.084 |
| smooth_compounder_grind | 1.017 | 0.506 | 0.408 |
| stair_step_leader | 0.841 | 0.650 | 0.355 |

#### Archetype — buy+rebuy fires vs universe (n_fires=8,444 labeled)

| archetype | fire_n | fire_share% | univ_share% | ratio |
|---|---|---|---|---|
| secular_growth | 236 | 2.80 | 2.53 | 1.104 |
| distressed | 400 | 4.74 | 4.54 | 1.044 |
| mixed | 3,057 | 36.22 | 34.94 | 1.037 |
| high_beta_momentum | 277 | 3.28 | 3.22 | 1.019 |
| financial | 632 | 7.49 | 7.55 | 0.992 |
| deep_value | 218 | 2.58 | 2.62 | 0.985 |
| rate_sensitive | 1,320 | 15.64 | 15.90 | 0.984 |
| broken_growth | 120 | 1.42 | 1.45 | 0.983 |
| quality_compounder | 137 | 1.62 | 1.66 | 0.980 |
| cyclical | 1,099 | 13.02 | 13.52 | 0.963 |
| speculative_unprofitable | 802 | 9.50 | 10.21 | 0.931 |
| dividend_defensive | 142 | 1.68 | 1.87 | 0.901 |

#### Micro Primary — buy+rebuy fires vs universe (n_fires=25,576 labeled)

| micro_primary | fire_n | fire_share% | univ_share% | ratio |
|---|---|---|---|---|
| slow_mean_reversion_liquidity | 3,453 | 13.50 | 12.86 | 1.050 |
| gap_discontinuity_risk | 120 | 0.47 | 0.45 | 1.043 |
| tight_spread_absorber | 8,787 | 34.36 | 34.04 | 1.009 |
| mixed_microstructure | 5,822 | 22.76 | 22.92 | 0.993 |
| wide_spread_impact | 7,394 | 28.91 | 29.73 | 0.972 |

#### Calendar clustering — rubber_band vs stair_step by month (buy+rebuy fires only)

| month | rubber_band% (n=1,385) | stair_step% (n=1,546) | diff_pp |
|---|---|---|---|
| Jan | 7.0 | 6.9 | +0.1 |
| Feb | 6.1 | 5.0 | +1.1 |
| Mar | 9.5 | 9.6 | -0.1 |
| Apr | 11.0 | 7.4 | +3.6 |
| May | 8.2 | 6.8 | +1.4 |
| Jun | 7.4 | 9.6 | -2.2 |
| Jul | 9.3 | 11.1 | -1.8 |
| Aug | 8.7 | 8.2 | +0.5 |
| Sep | 8.3 | 7.8 | +0.5 |
| Oct | 8.9 | 11.1 | -2.2 |
| Nov | 7.2 | 8.2 | -1.0 |
| Dec | 8.4 | 8.3 | +0.1 |

#### Era clustering — rubber_band vs stair_step vs failed_breakout vs compounder (ratio vs era share in fires)

| era | rub_ratio | stair_ratio | fbkt_ratio | comp_ratio | univ_share% |
|---|---|---|---|---|---|
| pre_GFC | 0.81 | 0.84 | 1.03 | 1.07 | 51.7 |
| GFC (2007-09) | 1.37 | 1.04 | 1.75 | 0.58 | 7.1 |
| QE_era (2010-21) | 1.37 | 1.20 | 0.80 | 1.01 | 28.7 |
| tightening (2022-23) | 0.36 | 1.16 | 0.97 | 0.70 | 6.2 |
| post_tight (2024-26) | 1.10 | 1.15 | 0.82 | 1.18 | 6.3 |

#### near_miss fires chart_primary composition (n=14 total; ALL small-n, descriptive only)

| chart_primary | fire_n | ratio vs univ | small_n |
|---|---|---|---|
| smooth_compounder_grind | 2 | 1.993 | yes |
| mixed_chart | 8 | 1.098 | yes |
| stair_step_leader | 1 | 1.013 | yes |
| failed_breakout_trap | 0 | 0.0 | yes |
| mean_reversion_rubber_band | 0 | 0.0 | yes |

### Notable findings

- stair_step_leader is the most under-represented chart type among buy+rebuy fires (ratio 0.678 vs universe), and this gap widens sharply by gate tier: T3 ratio = 0.355, meaning the highest-conviction gate fires are 65% less likely than chance to land on a stair_step name.
- failed_breakout_trap is the most over-represented chart type across all fire categories — buy+rebuy 1.184x, T1 gate 1.112x, T2 1.363x, T3 1.411x. The system consistently selects names in broken technical states.
- smooth_compounder_grind collapses at higher gate tiers: T1 ratio 1.017, T2 0.506, T3 0.408. The gate qualification process structurally screens out smooth-trend compounders at the high-conviction tier.
- rubber_band fires collapsed to ratio 0.36 during the 2022–2023 tightening cycle (31 fires vs 85 expected); stair_step held at 1.16x. Era explains more variance in rubber_band fire frequency than any calendar-month pattern.
- Archetype composition ratios across all 12 archetypes span only 0.901–1.104 for buy+rebuy fires. The fundamental archetype dimension is nearly flat — chart label, not fundamental type, drives fire composition skew.
- GFC era (2007–2009) produced strongly elevated failed_breakout_trap fires (ratio 1.75) and depressed compounder fires (ratio 0.58), consistent with broad technical failures crowding out smooth-trend names during the crisis.
- Micro_primary shows essentially no composition bias: all five types are within 5% of their universe share (ratio range 0.972–1.050), confirming the microstructure dimension is not a selection axis for the fire engine.
- near_miss fires n=14; all composition figures carry a small-n flag and are printed for completeness only — no inference supportable.

### Coverage and caveats

- Universe denominator = all 2,115,838 pit rows for 223 deep names. These 223 names are a survivorship-selected set (deep history + deep-name program inclusion); they are not a random or representative sample of the broader stock universe covered by stock_personality.json (1,722 names).
- 96.0% of buy+rebuy fires matched a pit label on exact date (25,425/26,491). The unmatched 1,066 fires (4.0%) are dropped from composition tables — no label available. No forward-fill or tolerance window was applied.
- archetype column in pit_labels is populated for only 690,160 of 2,115,838 rows (67% NaN). Archetype composition ratios are computed over the labeled subset only; unlabeled periods (pre-archetype coverage dates) are excluded.
- near_miss fires n=14 total, 11 pit-matched. All near_miss composition figures are descriptive only and flagged [small-n].
- gate_fires_deep: 98.6% pit-match (37,728/38,250). tier_comp archetype rows for T2 and T3 have multiple [small-n] entries (n<30).
- Era proxy uses calendar-year cutoffs (GFC=2007-2009, QE_era=2010-2021, tightening=2022-2023, post_tight=2024-2026+). No regime_history.parquet join was used; this is a mechanical proxy not a PIT regime label.
- This is composition only — no outcome columns were read or used. The over/under-representation ratios describe what types fires land on, not what happens after.
- No gate_fires_deep regeneration was needed — the file exists and is current (38,250 rows with tier coverage T1/T2/T3).

---

## Section 6 — Event Sensitivity

> **In plain English:** Earnings days amplify daily stock moves by 1.2x to 1.7x depending on type, but the practical meaning differs. For quiet types like deep_value and cyclical, earnings are a genuine spike against a calm baseline — the signal is concentrated and cleaner. For already-noisy types like speculative_unprofitable and high_beta_momentum, the baseline is already so elevated that earnings add relatively little incremental amplitude, while the post-earnings week remains almost completely unpredictable in direction. quality_compounder has the most orderly earnings response — the weekly follow-through is the tightest of all types.

### Lane summary

Event sensitivity varies meaningfully across archetypes, but no type is fully immune to earnings amplification. The sharpest structural divide is between types where earnings amplify the daily signal by ~1.5–1.7x (deep_value, cyclical, dividend_defensive, financial) versus types where the tape is already volatile and earnings add only ~1.2–1.3x incremental lift (high_beta_momentum, speculative_unprofitable, distressed, quality_compounder). For deep_value and cyclical names, earnings days punch hardest relative to baseline — a 1.70x and 1.49x median amplification ratio respectively — and earnings days account for 5–6.4% of total annual absolute movement despite representing only ~3.3% of trading days. Chart patterns built on non-earnings days are more predictive for these types because the baseline noise floor is lower and earnings creates a sharper, cleaner signal. For speculative_unprofitable and high_beta_momentum, the baseline daily volatility is already so elevated (median non-earnings |ret| ~1.2–1.19%) that earnings contributes proportionally less incremental lift; these tapes are event-driven by nature every day, not just on earnings dates.

Post-earnings 5-day drift dispersion reveals the largest structural gap in the data: high_beta_momentum and speculative_unprofitable show IQR-5d-drift of 9.8% and 9.1% respectively — roughly 1.6–1.9x the dispersion seen in mixed or financial names (4.9–5.2%). This means that even after an earnings print, the 5-day response for these two types is highly unpredictable in direction and magnitude. That wide post-event spread is a descriptor that chart-pattern guidance is unreliable in the week following an earnings catalyst for momentum/speculative names. Conversely, financial and distressed names have the tightest post-earnings drift IQRs (5.2% and 5.3%), suggesting more orderly reversion behavior after the initial print. Large-move-day concentration (share of annual abs move in top 4 days) broadly tracks amplification, but broken_growth and speculative_unprofitable top this measure (10.6% and 10.5%) — indicating episodic rather than continuous event exposure.

### Tables

#### Table 1: Earnings-Day Amplification Metrics by Archetype (sorted by amplification ratio; all returns as absolute value)

| Archetype | n_tickers | n_earn_events | Med |ret| earn | Med |ret| non-earn | IQR earn | IQR non-earn | Amp ratio | Earn% of abs move |
|---|---|---|---|---|---|---|---|---|
| deep_value | 6 | 609 | 1.44% | 0.85% | 2.33% | 1.19% | 1.70 | 6.4% |
| cyclical | 30 | 3,065 | 1.29% | 0.86% | 2.13% | 1.25% | 1.49 | 5.2% |
| dividend_defensive | 4 | 410 | 1.07% | 0.73% | 2.51% | 1.01% | 1.47 | 6.7% |
| financial | 15 | 1,552 | 1.23% | 0.84% | 1.81% | 1.21% | 1.47 | 4.3% |
| rate_sensitive | 40 | 3,604 | 1.22% | 0.89% | 1.92% | 1.30% | 1.36 | 4.6% |
| secular_growth | 34 | 574 | 1.41% | 1.06% | 2.15% | 1.46% | 1.33 | 4.7% |
| mixed | 75 | 7,970 | 1.00% | 0.75% | 1.57% | 1.07% | 1.34 | 4.8% |
| speculative_unprofitable | 82 | 2,293 | 1.62% | 1.21% | 2.40% | 1.84% | 1.34 | 4.4% |
| broken_growth | 21 | 292 | 1.40% | 1.06% | 2.10% | 1.50% | 1.31 | 4.1% |
| high_beta_momentum | 11 | 744 | 1.49% | 1.19% | 2.13% | 1.77% | 1.26 | 4.2% |
| distressed | 40 | 1,015 | 1.04% | 0.85% | 1.53% | 1.16% | 1.23 | 4.5% |
| quality_compounder | 3 | 370 | 0.93% | 0.76% | 1.50% | 1.12% | 1.23 | 4.2% |

*Amp ratio = median earn-day |ret| / median non-earn-day |ret|. Earn% = earnings-day contribution to total annual absolute move. No small-N flags triggered (all n_earn_events >= 292).*

#### Table 2: Earnings-Day Absolute Return Quantile Profile

| Archetype | p50 earn | p75 earn | p90 earn | p50 non-earn | p75 non-earn | p90 non-earn |
|---|---|---|---|---|---|---|
| deep_value | 1.44% | 2.96% | 5.37% | 0.85% | 1.57% | 2.55% |
| cyclical | 1.29% | 2.70% | 4.64% | 0.86% | 1.64% | 2.74% |
| dividend_defensive | 1.07% | 2.97% | 5.72% | 0.73% | 1.34% | 2.15% |
| financial | 1.23% | 2.38% | 4.14% | 0.84% | 1.59% | 2.65% |
| high_beta_momentum | 1.49% | 2.75% | 4.60% | 1.19% | 2.30% | 3.82% |
| speculative_unprofitable | 1.62% | 3.09% | 5.42% | 1.21% | 2.37% | 4.03% |
| secular_growth | 1.41% | 2.76% | 4.82% | 1.06% | 1.93% | 3.14% |
| broken_growth | 1.40% | 2.68% | 4.39% | 1.06% | 1.98% | 3.40% |
| rate_sensitive | 1.22% | 2.48% | 4.39% | 0.89% | 1.70% | 2.84% |
| distressed | 1.04% | 1.98% | 3.70% | 0.85% | 1.55% | 2.48% |
| mixed | 1.00% | 2.03% | 3.62% | 0.75% | 1.41% | 2.32% |
| quality_compounder | 0.93% | 1.93% | 3.14% | 0.76% | 1.45% | 2.37% |

#### Table 3: Post-Earnings 5-Day Drift Dispersion

| Archetype | n_events | Median 5d drift | p25 | p75 | IQR | p10-p90 spread |
|---|---|---|---|---|---|---|
| high_beta_momentum | 744 | +0.03% | -4.9% | +4.9% | 9.81% | 21.82% |
| speculative_unprofitable | 2,291 | +0.51% | -4.5% | +4.6% | 9.08% | 20.12% |
| broken_growth | 292 | +0.30% | -4.1% | +4.1% | 8.21% | 20.56% |
| secular_growth | 574 | +0.06% | -4.1% | +4.1% | 8.14% | 16.15% |
| quality_compounder | 370 | +1.43% | -3.3% | +3.3% | 6.59% | 14.71% |
| deep_value | 609 | +0.75% | -3.2% | +3.2% | 6.38% | 13.33% |
| rate_sensitive | 3,604 | +0.31% | -2.9% | +2.9% | 5.76% | 11.78% |
| cyclical | 3,063 | +0.45% | -2.4% | +3.3% | 5.68% | 11.91% |
| distressed | 1,015 | +0.24% | -2.7% | +2.7% | 5.33% | 10.87% |
| dividend_defensive | 410 | +0.66% | -2.6% | +2.6% | 5.22% | 12.06% |
| financial | 1,552 | +0.71% | -2.6% | +2.6% | 5.21% | 10.20% |
| mixed | 7,970 | +0.28% | -2.5% | +2.5% | 4.93% | 10.46% |

*IQR of 5-day cumulative return distribution after the earnings date. Wider IQR = post-event direction more unpredictable.*

#### Table 4: Large-Move-Day Concentration (Proxy for Event-Driven Tape)

| Archetype | n_ticker_years | Median top-1-day share | Median top-4-day share | IQR top-4-day share |
|---|---|---|---|---|
| broken_growth | 58 | 3.4% | 10.6% | 7.0% |
| speculative_unprofitable | 394 | 3.5% | 10.5% | 6.3% |
| secular_growth | 105 | 3.4% | 10.3% | 7.2% |
| high_beta_momentum | 108 | 3.2% | 9.8% | 4.4% |
| deep_value | 80 | 2.9% | 9.2% | 3.7% |
| dividend_defensive | 57 | 2.8% | 9.1% | 3.3% |
| quality_compounder | 49 | 3.0% | 9.0% | 3.9% |
| distressed | 157 | 2.8% | 8.9% | 3.3% |
| cyclical | 417 | 2.7% | 8.5% | 3.3% |
| mixed | 1,055 | 2.7% | 8.4% | 3.8% |
| rate_sensitive | 496 | 2.6% | 8.3% | 3.3% |
| financial | 226 | 2.5% | 7.9% | 3.3% |

*Top-4-day share = sum of 4 largest |return| days / sum of all |return| days in a calendar year, median across ticker-years. Financial has the lowest tail-day concentration — daily tape is relatively smooth between events.*

### Notable findings

- deep_value has the highest amplification ratio (1.70x) despite only 6 underlying tickers in the deep corpus — earnings days deliver 6.4% of total annual abs move (vs 3.3% day-share), a 1.9x concentration factor. Small-n caveat applies to type-level conclusions.
- high_beta_momentum and speculative_unprofitable post-earnings IQR (9.8% and 9.1% over 5 days) is roughly 2x that of financial and mixed (5.2% and 4.9%) — chart patterns are least reliable in the post-earnings window for these types.
- financial shows the lowest large-move-day concentration (top-4-day share = 7.9%, vs 10.6% for broken_growth) despite a 1.47x amplification ratio — earnings are sharp but the non-earnings tape is also relatively smooth; the signal-to-noise improvement from earnings is proportionally high.
- quality_compounder has the lowest amplification ratio (1.23x) and lowest p90 earn-day |ret| (3.14%) — suggesting earnings are the least disruptive to the ongoing tape structure; chart patterns retain more authority across the earnings window.
- dividend_defensive has p90 earnings-day |ret| of 5.72% (highest in the table) driven by a very wide IQR on earnings days (2.51%) while maintaining the lowest non-earnings median (0.73%) — the most extreme earnings-vs-baseline contrast, but only 4 underlying tickers.
- distressed has the second-lowest amplification ratio (1.23x) — not because earnings are quiet but because non-earnings baseline noise is already elevated from idiosyncratic credit/restructuring events that dominate the tape regardless of earnings calendar.
- All archetypes show positive median post-earnings 5d drift (median +0.03% to +1.43%) — consistent with mild post-earnings drift-up tendency in the corpus, but this is a descriptive observation not a signal claim; n=1,314 unique tickers in Edgar coverage vs 190 in deep-stock corpus.
- Earnings days represent 3.3% of all trading days but 4.1–6.7% of total annual absolute movement across all archetypes — a 1.23x to 2.03x day-weighted over-representation depending on type.

### Coverage and caveats

- Deep stock corpus covers 190 tickers with PIT archetype labels (from 1,722 in production) — biased toward established larger-cap names; speculative/distressed micro-cap representation is thin.
- quality_compounder (3 tickers), dividend_defensive (4 tickers), and deep_value (6 tickers) have very small underlying universes — type-level medians are illustrative only and sensitive to single-name composition.
- Edgar 8-K item 2.02 provides 1,314 ticker coverage 2004–2026; the T+0/T-1 earnings day window is an approximation — BMO vs AMC timing cannot be distinguished cleanly for all names, so a small share of "non-earnings" days near earnings may actually be earnings reaction days.
- Archetype label is PIT via merge_asof backward — annual archetype boundaries mean a ticker transitioning types mid-year may have mismatched labels for a portion of the year.
- Post-earnings 5d drift calculation uses shift-based forward returns; last 5 trading days per ticker have NaN filled as 0% (affects <0.5% of observations).
- "commodity_sensitive" archetype appears in archetypes/history.parquet but not in personality_pit_labels — it was excluded from analysis as it has no price-level PIT label mapping.

---

## Section 7 — How to Read This Document

This section states the four properties that govern how much trust to place in any number in this file.

### Label trust differs by type

The archetype label's explanatory power for a specific name's year varies by more than 3x across types. For types with low within-archetype return dispersion (financial: median annual cross-name std 0.162, quality_compounder: 0.175), the archetype label is a meaningful characterization of what names in that group tend to do. For types with high dispersion (speculative_unprofitable: 0.544), the archetype label tells you about the distribution of outcomes in the group, not about what any specific name in the group will do. Always read high-dispersion type statistics as distribution parameters, not as type-level predictions.

### Survivorship watermark

The 223-name deep corpus was constructed from names with extended price history in data/stocks/ and deep-name program inclusion criteria. This creates survivorship bias in both directions: (1) names that were delisted, acquired, or otherwise exited the public market before accumulating sufficient history are absent; (2) the selection criteria favor larger, more established, more liquid names across all archetypes. The survivorship effect is strongest for speculative_unprofitable and distressed, where the worst outcomes (permanent impairment, delisting) are most likely to be underrepresented. Every metric in this document should be treated as describing the upper tail of historical survival within each type.

### Deep-corpus-only caveat

The 223-name deep corpus is 13% of the 1,722-name production label universe by count. commodity_sensitive has no overlap with the deep corpus. quality_compounder (3 tickers), dividend_defensive (4 tickers), and deep_value (6 tickers) are anchored to very small underlying universes; their type-level statistics are particularly sensitive to single-name idiosyncrasies. No inference from this document should be applied to the full production universe without verifying that the deep corpus is representative along the relevant dimensions for that inference.

### Nothing here is a signal

This document contains no forward-looking claims, no edge claims, no significance tests, and no forecast language. The distributions described are measured historical distributions from a survivorship-biased corpus. The companion document research/STOCK_PERSONALITY_OPERATOR_PLAYBOOK_BY_FABLE.md translates selected patterns into operating frameworks; this document is the reference for what the data actually contains, not for what actions to take.

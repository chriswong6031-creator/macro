# PSS-SR1 preregistration — stress-matched second-test elasticity

Status: **FROZEN BEFORE FINAL-CONSTRUCTION OUTCOMES** (2026-07-27).

Program home: `research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md`
W-SIG/W-FOUNDRY. The operator explicitly approved moving the post-F1–F4
brainstorm into a build on 2026-07-27.

Canonical identifier: **PSS-SR1** (`pss_sr1_stress_elasticity`). The brainstorm
used the temporary label “G1,” but `research/DO_NOT_REBUILD.md` already assigns
`G1` to an unrelated deferred long-hold proposal. SR1 prevents a registry and
trial-ledger collision.

## 0. Prior information and trial budget

The following information was already visible before this freeze and therefore
cannot count as confirmation:

- the completed PSS-F1 through PSS-F4 reports;
- the F4 repair and hazard reports;
- a feasibility-only census showing that roughly 46%–62% of incumbent-watch
  events encounter two separate trailing-15th-percentile sector/market stress
  clusters within 15 sessions;
- one exploratory one-shock diagnostic that required a non-negative
  beta-stripped response;
- one exploratory two-shock diagnostic that required two non-negative
  beta-stripped responses.

Those naïve diagnostics were too late and did not show stable development-era
tail behavior. SR1 is materially different: it compares the **price damage per
unit of stress** between two completed, stress-matched pulses around a fresh-low
episode. It does not use the sign of two daily residuals.

The family trial budget is conservatively declared as **6**: the two feasibility
definitions, the two naïve response diagnostics, this final construction, and
one reserved implementation-equivalence check. There is no outcome-selected
grid and no per-name parameter selection.

## 1. One mechanism hypothesis

A durable reset is more likely when a second independent bout of comparable
sector selling produces materially less stock-price damage than the first bout.
The first pulse identifies the stock’s stress elasticity while forced selling
is still effective. An intervening rebound transfers inventory. If a second
sector shock then fails to penetrate the reference low and the stock’s downside
elasticity falls by at least half, the tape has demonstrated absorption under
new adverse information rather than merely surviving quiet time.

This is a reset-confirmation / terminality study. It never “calls bottoms” and
it cannot change entry, rank, or size without a separate promotion ruling.

## 2. Wrong-ruler check

SR1 makes an **entry-timing and forward-risk** claim:

> Does a stress-matched second test identify a shallower-risk action closer to a
> durable reset than the same retest geometry without elasticity collapse?

It is not a long-hold-return claim. The primary house ruler remains MAE63 and
proximity to the ±31-trading-day low. A fixed-horizon competing-risk outcome is
added because SR1 explicitly claims that a rebound should occur before the
tested low fails. Forward returns alone are not a verdict metric.

## 3. Data and universe

- Name OHLCV: `data/baskets/ohlcv/{sym}.parquet`.
- Sector ETF close: `data/yahoo/{ETF}.parquet`.
- Sector assignment: `data/breadth/ticker_sectors.parquet`.
- Universe spine: `data/research/ptt_w1_panel.parquet`.
- The eleven fixed GICS-to-SPDR mappings are copied from
  `scripts/research/pss_f4_repair.py`.
- Names without a sector mapping, an ETF series, sufficient trailing history,
  or a complete 63-session outcome horizon are excluded with reasons printed.
- No name defaults to SPY. A market fallback would change the mechanism.
- Current-listed-name and current-sector mappings are acknowledged survivor and
  classification biases. Historical results can qualify only a prospective
  shadow.

Study eras:

- DEV: 2020-07-01 through 2022-12-31;
- VAL: 2023-01-01 through 2024-12-31;
- FWD descriptive: 2025-01-01 onward.

All rolling inputs are point-in-time and shifted one session before use.

## 4. Frozen construction

### 4.1 Fresh-low anchor and systemic route

An anchor is the first daily close at or below the minimum of the **prior**
60 closes. After accepting an anchor, later fresh lows in the next 21 trading
sessions cannot create another anchor.

At the anchor, estimate on the 126 prior common sessions:

- OLS beta of stock log return on sector-ETF log return;
- OLS R²;
- 63-session sector-return standard deviation;
- 14-session stock ATR.

The anchor is systemic-route eligible only when:

- beta is positive;
- R² is at least **0.35**; and
- the sector ETF’s trailing 20-session return is negative.

These are fixed route conditions, not a score.

### 4.2 Sector stress pulses

For each sector ETF, a shock day is:

`sector_return <= shifted trailing 15th percentile of sector_return`

using a 252-session window with 126 observations minimum, and the return must be
negative. Consecutive shock days form one pulse. A pulse is observable as
complete only at the close of the first following non-shock session.

Pulse A is the first pulse whose **start** lies from the anchor through three
sessions after the anchor. Its stock/sector cumulative log returns are measured
over the completed pulse.

With beta and sector volatility frozen at the anchor:

`stress_k = -sector_cumret_k / (sector_sigma_anchor * sqrt(pulse_days_k))`

`elasticity_k = max(0, -stock_cumret_k) / (beta_anchor * max(1e-6, -sector_cumret_k))`

Pulse A must have elasticity of at least **0.75**, proving that the reference
episode contained meaningful stock damage rather than an already-immune tape.

### 4.3 Rebound and pulse B

After pulse A completes, the stock must close at least **one frozen ATR** above
the minimum intraday low printed during pulse A.

Pulse B is the first later completed sector pulse that:

- starts after that rebound has been observed;
- starts no more than 15 sessions after pulse A’s confirmation; and
- has normalized stress at least **0.80 × pulse-A stress**.

No later pulse may replace the first pulse that meets these conditions.

The tested-low geometry holds when:

`minimum_low_B >= minimum_low_A - 0.50 * ATR_anchor`

### 4.4 Treatment and controls

Every action is stamped at pulse B’s confirmation close. Execution diagnostics
use the following session’s open, but the house timing ruler uses the observable
confirmation close for comparability with PSS-F1–F4.

- **SR1 treatment:** the tested-low geometry holds and
  `elasticity_B <= 0.50 * elasticity_A`.
- **Geometry control:** the identical anchor, systemic route, pulse-A damage,
  rebound, comparable pulse-B stress, and tested-low geometry hold, but
  `elasticity_B > 0.50 * elasticity_A`.
- **Stress-path control:** the identical path through comparable pulse B,
  regardless of tested-low hold or elasticity.

The treatment and geometry control are disjoint. The geometry control is the
primary falsifier because it holds stress, sequence, rebound, timing, and price
geometry constant while removing only the elasticity-collapse condition.

There is one final construction. The constants above are not a grid.

## 5. Outcomes

House metrics, copied from the corrected PSS machinery:

- `MAE63`: worst close-to-close excursion during the next 63 sessions;
- `prox`: distance from the minimum close in ±31 sessions;
- `W5`: within 5% of that low;
- `called`: trough offset from −2 through +5 sessions;
- `tail10`: MAE63 at or below −10%;
- `tdt`: signed trading-day distance to the ±31-session trough.

Binary rates are collapsed per name before cross-name summaries. A median of
per-event binary-minus-baseline rows is forbidden.

Competing-risk diagnostic over the same fixed 63-session horizon:

- rebound event: close reaches **+8%** from the action close;
- breach event: intraday low falls below
  `pulse_A_low - 0.50 * ATR_anchor`;
- if both occur on one session, breach wins conservatively;
- `rebound8_first = 1` only when rebound occurs first;
- unresolved at day 63 remains in the denominator with
  `rebound8_first = 0`; unresolved share is printed.

This prevents outcome-dependent resolution from deleting slow losers.

## 6. Inference and nulls

The primary comparison is SR1 treatment minus the disjoint geometry control.
Positive is normalized to mean “better” for every metric:

- MAE: treatment minus control;
- W5/called/rebound-first: treatment minus control;
- tail10/breach-first: control minus treatment.

Primary p-values use **within-pulse label permutation**:

- pulse unit = sector ETF × pulse-B start date;
- only pulses containing both treatment and geometry-control names inform the
  primary statistic;
- treatment counts are preserved within each pulse;
- labels are permuted only among names exposed to that same pulse;
- pulse-level effects are equal-weighted;
- 2,000 permutations, seed **20260802**.

This is stricter than month control because every comparison shares the same
realized sector shock. It avoids treating hundreds of names in one market event
as hundreds of independent time observations.

A calendar-month block bootstrap, with entire pulse units assigned to pulse
B’s start month, supplies 95% CI diagnostics:

- 1,000 resamples, seed **20260803**;
- never the primary p-value;
- no pulse may straddle resampled blocks.

All nulls and point estimates print regardless of direction. DEV and VAL are
adjudicated separately; a pooled-only effect is disqualified. FWD is
descriptive because all available history has already been inspected.

## 7. Coverage and 2022 containment

The report must print:

- anchors, stress paths, geometry controls, treatments, names, and sector-pulse
  counts by era;
- names with at least three treatment events;
- informative pulses containing both treatment and geometry controls;
- exclusions by reason;
- action-delay distribution;
- H1-2022 monthly action density versus September–November 2022 density.

A tiny or single-fire-per-name result is not promotable.

## 8. Decision law

Historical evidence can qualify SR1 only for a frozen prospective shadow, never
for authority.

Qualification requires all of:

1. in both DEV and VAL, SR1 beats the geometry control in the expected direction
   on MAE and tail10, with positive 95% CI lower bounds and pulse-permutation
   `p <= 0.05`;
2. W5 or called timing and `rebound8_first` improve in both eras without a
   degenerate binary-rate sample;
3. at least 500 names fire across the full OOS sample, at least 100 names have
   three or more fires, and at least 30 informative pulse-B clusters exist in
   each of DEV and VAL;
4. H1-2022 action density is below the September–November 2022 density; and
5. no primary effect reverses sign in the descriptive FWD era.

If any requirement fails, the exact SR1 construction is killed and recorded in
`research/DO_NOT_REBUILD.md`. The stress-response search space remains open, but
threshold retiming or adding F4 does not constitute a new species.

If every requirement passes, the only permitted next step is a deterministic,
display-only prospective ledger with:

- no entry/rank/size authority;
- nightly as sole advancer;
- frozen construction and model identifier;
- 63-session maturity before grading; and
- a separate future promotion ruling.

## 9. Outputs and reproducibility

Planned implementation:

- `scripts/research/pss_sr1_stress_elasticity.py`
- `tests/test_pss_sr1_stress_elasticity.py`
- `reports/pss_sr1_stress_elasticity.md`
- `data/research/pss_sr1_stress_elasticity_events.parquet`
- `data/research/pss_sr1_stress_elasticity_panel.parquet`

The study stays off render/nightly paths. A rerun with unchanged inputs and
seeds must reproduce the report and parquet content.

# W6 — Do deep weekly washout turns on defensive names pay better when short rates roll over?

**Frozen-frame measurement packet · 2026-08-06 · display tier only.**
Nothing here is promoted, ranked, sized, or gated. No ledger was written and no engine, script, or
template was touched. Raw numbers: `research/signal_episode_atlas/w6_results.json`.

**Hypothesis under test (operator's, tested not assumed).** Deep weekly washout-turn crosses on
DEFENSIVE names perform better when short rates are rolling over than when rising — and that
differential exceeds the same differential on a GROWTH/momentum cohort. The claim is an
*interaction*, so the interaction term is what gets measured, not just the conditional.

**Headline, in one paragraph.** The defensive-side conditional is a null: defensive washout turns
returned a median +0.93% excess over 13 weeks when the primary rate flag read FALLING versus +0.29%
when it read RISING, a difference of **+0.63%** whose 90% block-bootstrap interval is
**[-1.20%, +2.59%]** — it spans zero at both horizons, under both regime definitions, and it changes
sign between the pre-2005 and post-2005 halves in all four horizon × measure combinations. The
interaction runs **opposite** the hypothesis: the falling-rate premium was larger on the GROWTH
cohort (**+3.99%**, 90% CI [+0.93%, +6.73%]) than on the DEFENSIVE cohort, giving an interaction of
**-3.36%** (90% CI [-6.57%, +0.39%]). That inversion is direction-stable across regime definitions,
clustering choices, both halves at 13 weeks, and a wider-universe variant — but it does not survive to
the 26-week horizon. **A separate finding outranks all of the above and is stated in §7: the primary
regime flag does not measure what the hypothesis means by "rolling over."** At its FALLING bars the
1-year yield's trailing 26-week change averaged **+0.086pp** — up, not down — and the flag's agreement
with the 26-week direction is **below chance** (Cohen's κ = -0.071).

---

## 0. Verdicts

| # | Question | Verdict |
|---|---|---|
| **(a)** | Do defensive washouts perform better under falling rates? | **NULL.** DEF_diff = +0.63% median excess at 13w, 90% CI [-1.20%, +2.59%]; the interval spans zero at every horizon, both measures, and both regime definitions, and the sign flips across the 2005 halves in 4 of 4 combinations. |
| **(b)** | Is the differential defensive-specific (the interaction)? | **NOT SUPPORTED, and the point estimate runs the other way.** Interaction = -3.36% at 13w excess (90% CI [-6.57%, +0.39%]); the falling-rate premium sits on the GROWTH cohort, not the defensive one. Direction reproduces under R2, under name-clustering, in both halves at 13w, and in the wider-universe variant — but it decays to -0.15% (CI [-6.17%, +4.94%]) at 26 weeks. |
| **(c)** | Is any of it stable? | **UNSTABLE.** The conditional flips sign across halves in every combination. The interaction is direction-stable at 13w but its magnitude decays 4.3× from pre-2005 (-8.01%) to post-2005 (-1.85%), and it flips sign at 26w excess (-17.53% → +1.50%). |

No cell tripped the pre-declared thinness rule (n < 15 or fewer than 8 distinct quarters); the
thinnest primary cell is GROWTH_RISING at n = 155 over 56 quarters. **The binding limitation is not
sample size — it is construct validity in the regime flag (§7) and in the cohorts (§6).**

---

## 1. Methods, exactly

Run with `python3` from the worktree root; all paths repo-relative.

**Event construction (frozen; the house construction reused verbatim).**

```python
sys.path.insert(0, '.')
from engine import canon
weekly = close.resample("W-FRI").last().dropna()      # trailing PARTIAL bar dropped
line, sig = canon.rsi_macd(weekly)                    # canon.RSI_LEN=14, FAST=14, BASE=60, SIG=5
xo = canon.crossover(line, sig)                       # (a > b) & (a.shift(1) <= b.shift(1))
```

An EVENT is a `True` in `xo` on a completed weekly bar whose `line` value sits at or below the 15th
percentile of the trailing 10 years:

- window = the 520 weekly `line` values ending at and including the event bar (never any future bar);
- at least 100 finite observations required in that window;
- rank = (count of window values **strictly less than** `line[t]`) / (count of finite window values);
- admitted iff rank ≤ 0.15.

No full-sample percentile is used anywhere. The partial-bar rule is `label > last daily date`, applied
to every series including SPY and DGS1.

**Prices.** Preference `data/stocks/<SYM>.parquet` → `data/baskets/ohlcv/<SYM>.parquet` →
`data/yahoo/<SYM>.parquet`, column `close`. All three carry the **same dividend-and-split-adjusted**
series — verified on LLY 2010-01-04 (raw `close_price` 35.82 vs `close` 23.41, a 35% haircut far
exceeding any split, LLY having had none since 1997) and on KO 2020-03-23 (37.56 raw vs 31.10
adjusted). Returns are therefore total-return and the two cohorts are compared on the same basis.
`data/baskets/ohlcv` reproduces `data/stocks` to 7 decimal places on overlapping dates.

**History gate.** ≥ 780 completed weekly bars (~15 years) so a name spans at least one rate cycle.

**Rates regime.** `data/fred/DGS1.parquet` (column `us1y`, 1962-01-02 → 2026-07-30), resampled W-FRI
last, `ffill(limit=2)`, trailing partial bar dropped by DGS1's own last daily date.

- **R1 (primary):** `line, sig = canon.rsi_macd(DGS1_weekly)`; FALLING iff `line < sig` on the last
  completed weekly bar at or before the event date, RISING otherwise.
- **R2 (robustness):** the 26-week change of the DGS1 weekly *level* at that same anchor bar;
  FALLING iff the change is negative.

**Outcomes.** Forward 13-week and 26-week simple returns from the event bar's weekly close.
EXCESS = stock return − SPY return over the **identical weekly labels** (SPY reindexed onto the
stock's weekly index). Matured events only: horizon `h` requires bar `i+h` to exist in the completed
weekly series.

**Inference.** Block bootstrap clustered by event QUARTER, 2,000 replications, seed 20260806. Each
replication draws `len(quarters)` quarters with replacement and pools every event in the drawn
quarters — **one shared draw feeds all four cells**, which is what propagates the within-quarter
cross-sectional dependence into the interaction rather than treating the four cells as independent.
90% CI = 5th/95th percentile of the replication distribution. Zero replications were discarded for an
empty cell in any primary configuration.

---

## 2. Cohorts (frozen before any outcome was computed)

**Basket ids actually used**, by the spec's substring rule over `data/baskets/membership.json`
(48 baskets):

- `'staple'` or `'health'` → **`us_sector_staples`** (35 members), **`us_sector_health`** (59 members).
- `'software'` or `'semi'` → **`ai_software`** (17), **`non_ai_software`** (14),
  **`ai_semiconductors`** (12), **`semicap_equipment`** (16).

Note the basket id **`defensives` was NOT included** — it contains neither substring, and the frozen
rule is the substring rule.

**Archetype leg.** `data/us_prophet_rank/candidates/2026-07.parquet`, column `archetype__archetype`.
DEFENSIVE ← `quality_compounder` ∪ `dividend_defensive` (46 tickers). GROWTH ←
`high_beta_momentum` ∪ `secular_growth` ∪ `speculative_unprofitable` (247 tickers).

**Force-include (disclosed).** MCD, KO, PEP, PG, JNJ, WMT were added to DEFENSIVE. Only **MCD** was
genuinely new — its `archetype__archetype` is null and it sits in Consumer Discretionary, so it
reaches the cohort by the force-include alone. The other five were already in `us_sector_staples`.

**Overlap dropped: 12 names** — ADBE, BAX, CNC, CRL, DDOG, DOCU, KHC, MRNA, PODD, SJM, TAP, VEEV.

**Resolution.** Pre-resolution unions were 133 DEFENSIVE and 281 GROWTH. After price resolution and
the 780-week gate:

| Cohort | Kept | Dropped: short history | Dropped: no price source |
|---|---|---|---|
| DEFENSIVE | **40** | 74 | 7 |
| GROWTH | **26** | 207 | 36 |

Every kept name resolved to `data/stocks`. That is a mechanical consequence of the gate:
`data/baskets/ohlcv` universally starts 2014-01-02 (657 weekly bars), so any name absent from
`data/stocks` fails 780 automatically. **32 of the short-history drops had a series in `data/yahoo`
— a lower-preference source — that did clear 780 bars** (BSX 1,785; CAG 2,420; IDXX 1,833; LH 1,897;
STZ 1,794; COHU/FMC/MTRN/POWL 2,420; and 23 others). The frozen preference order picked the shorter
series. §5 re-runs everything on a longest-available-source loader to measure what that cost.

---

## 3. The 2×2×horizon table

Primary regime definition R1. `n` = matured events, `q` = distinct event quarters, `names` = distinct
symbols contributing. Win rate = share of events with a positive outcome.

### 13-week, EXCESS vs SPY — the spec's headline measure (N = 1,215 events, 127 quarters)

| Cell | n | q | names | median | mean | win |
|---|---:|---:|---:|---:|---:|---:|
| DEFENSIVE · FALLING | 418 | 84 | 40 | **+0.93%** | +0.79% | 55.3% |
| DEFENSIVE · RISING | 339 | 82 | 40 | **+0.29%** | +0.63% | 51.9% |
| GROWTH · FALLING | 303 | 74 | 26 | **+2.43%** | +3.55% | 57.4% |
| GROWTH · RISING | 155 | 56 | 26 | **-1.56%** | +1.03% | 43.9% |

| Statistic (median excess) | Point | 90% CI | P(> 0) |
|---|---:|---|---:|
| DEF_diff = DEF_fall − DEF_rise | +0.63% | **[-1.20%, +2.59%]** | 0.718 |
| GRO_diff = GRO_fall − GRO_rise | +3.99% | **[+0.93%, +6.73%]** | 0.979 |
| **INTERACTION = DEF_diff − GRO_diff** | **-3.36%** | **[-6.57%, +0.39%]** | 0.065 |

### 26-week, EXCESS vs SPY (N = 1,209 events, 126 quarters)

| Cell | n | q | names | median | mean | win |
|---|---:|---:|---:|---:|---:|---:|
| DEFENSIVE · FALLING | 418 | 84 | 40 | +0.81% | +2.21% | 51.0% |
| DEFENSIVE · RISING | 339 | 82 | 40 | +0.20% | +1.23% | 51.0% |
| GROWTH · FALLING | 302 | 73 | 26 | +3.25% | +5.80% | 57.3% |
| GROWTH · RISING | 150 | 55 | 26 | +2.49% | +5.75% | 54.7% |

| Statistic | Point | 90% CI | P(> 0) |
|---|---:|---|---:|
| DEF_diff | +0.61% | [-2.59%, +3.48%] | 0.584 |
| GRO_diff | +0.77% | [-3.34%, +5.91%] | 0.660 |
| **INTERACTION** | **-0.15%** | **[-6.17%, +4.94%]** | 0.419 |

### 13-week, RAW (N = 1,597 events, 201 quarters)

| Cell | n | q | names | median | mean | win |
|---|---:|---:|---:|---:|---:|---:|
| DEFENSIVE · FALLING | 582 | 127 | 40 | +4.61% | +4.51% | 63.6% |
| DEFENSIVE · RISING | 464 | 119 | 40 | +4.22% | +3.86% | 63.6% |
| GROWTH · FALLING | 360 | 104 | 26 | +5.83% | +6.22% | 61.1% |
| GROWTH · RISING | 191 | 76 | 26 | +1.87% | +3.44% | 53.9% |

| Statistic | Point | 90% CI | P(> 0) |
|---|---:|---|---:|
| DEF_diff | +0.39% | [-1.91%, +2.36%] | 0.608 |
| GRO_diff | +3.96% | [+0.13%, +8.70%] | 0.953 |
| **INTERACTION** | **-3.57%** | **[-8.38%, -0.02%]** | 0.050 |

### 26-week, RAW (N = 1,591 events, 200 quarters)

| Cell | n | q | names | median | mean | win |
|---|---:|---:|---:|---:|---:|---:|
| DEFENSIVE · FALLING | 582 | 127 | 40 | +6.83% | +8.61% | 67.9% |
| DEFENSIVE · RISING | 464 | 119 | 40 | +6.41% | +6.88% | 68.5% |
| GROWTH · FALLING | 359 | 103 | 26 | +10.30% | +12.05% | 65.5% |
| GROWTH · RISING | 186 | 75 | 26 | +8.64% | +9.42% | 58.1% |

| Statistic | Point | 90% CI | P(> 0) |
|---|---:|---|---:|
| DEF_diff | +0.42% | [-2.31%, +3.09%] | 0.614 |
| GRO_diff | +1.67% | [-3.11%, +10.59%] | 0.774 |
| **INTERACTION** | **-1.24%** | **[-9.68%, +3.16%]** | 0.267 |

### Median versus mean

The frozen headline statistic is the median. The mean disagrees materially, and at 26 weeks it
disagrees in sign:

| Combination | INTERACTION (median) | INTERACTION (mean) |
|---|---:|---:|
| 13w excess | -3.36% | -2.36% |
| 26w excess | **-0.15%** | **+0.92%** |
| 13w raw | -3.57% | -2.14% |
| 26w raw | -1.24% | -0.89% |

The 13-week defensive conditional is likewise weaker on means than on medians (DEF_diff mean +0.17%
versus median +0.63%), i.e. essentially zero. A statistic that changes sign between two ordinary
central-tendency estimators at the same horizon is not a finding.

---

## 4. Halves split (events before / on-or-after 2005-01-01)

Sign flip across halves = report as unstable, claim nothing. Applied literally:

| Combination | Statistic | Full | Pre-2005 | Post-2005 | Sign flip |
|---|---|---:|---:|---:|:--:|
| 13w raw | DEF_diff | +0.39% | -0.05% | +0.87% | **YES** |
| | GRO_diff | +3.96% | +10.17% | +1.84% | no |
| | INTERACTION | -3.57% | -10.22% | -0.97% | no |
| 13w excess | DEF_diff | +0.63% | -0.21% | +0.84% | **YES** |
| | GRO_diff | +3.99% | +7.80% | +2.69% | no |
| | INTERACTION | -3.36% | -8.01% | -1.85% | no |
| 26w raw | DEF_diff | +0.42% | -1.13% | +1.89% | **YES** |
| | GRO_diff | +1.67% | +2.85% | +2.37% | no |
| | INTERACTION | -1.24% | -3.98% | -0.48% | no |
| 26w excess | DEF_diff | +0.61% | -3.35% | +1.98% | **YES** |
| | GRO_diff | +0.77% | +14.18% | +0.48% | no |
| | INTERACTION | -0.15% | -17.53% | +1.50% | **YES** |

**The operator's conditional flips sign in 4 of 4 combinations.** Per the frozen rule that is
unstable, and nothing is claimed from it.

The interaction holds its sign at 13 weeks in both halves but its magnitude decays by a factor of
4.3× (excess) to 10.5× (raw) — most of the apparent effect is a pre-2005 phenomenon. Half-cells are
not thin by the pre-declared rule, though the pre-2005 GROWTH_RISING cell (n = 35, q = 16) is the
thinnest anywhere in the study and is what makes the pre-2005 interaction large.

---

## 5. Robustness

### R2 — 26-week rate direction instead of the RSI-MACD flag

| Combination | DEF_diff [90% CI] | GRO_diff | INTERACTION [90% CI] |
|---|---|---:|---|
| 13w raw | +1.47% [-0.84%, +3.48%] | +5.73% | -4.25% [-9.65%, -0.05%] |
| 13w excess | +0.54% [-1.51%, +2.32%] | +3.54% | -3.00% [-8.14%, +1.89%] |
| 26w raw | +2.92% [-0.06%, +6.11%] | +6.71% | -3.79% [-10.33%, +2.59%] |
| 26w excess | -0.01% [-3.31%, +2.87%] | +2.28% | -2.28% [-10.29%, +3.56%] |

R2 reverses R1's cell balance entirely (DEFENSIVE_FALLING n = 358 versus 418; GROWTH_RISING n = 251
versus 155) yet reproduces the same qualitative picture: the defensive conditional straddles zero in
all four, and the interaction is negative in all four. The direction of the inversion does not depend
on which rate definition is used — which is notable precisely because the two definitions barely
agree with each other (§7).

### Longest-available-source loader (recovers the 32 names the preference order dropped)

Selecting, per name, whichever of the three sources yields the longest completed weekly series lifts
the study to **52 DEFENSIVE + 46 GROWTH names, 2,104 events**:

| Combination | DEF_diff [90% CI] | GRO_diff | INTERACTION [90% CI] |
|---|---|---:|---|
| 13w excess | +0.59% [-1.04%, +2.05%] | +4.21% | **-3.62% [-6.27%, -0.96%]** |
| 26w excess | **-0.72%** [-3.25%, +2.05%] | +2.02% | -2.74% [-8.12%, +2.18%] |
| 13w raw | **-0.17%** [-2.22%, +2.06%] | +4.62% | **-4.79% [-8.80%, -1.21%]** |
| 26w raw | **-0.13%** [-2.93%, +2.44%] | +4.24% | -4.36% [-12.00%, +1.46%] |

Widening the universe moves both results **against** the hypothesis: the defensive conditional turns
negative in 3 of 4 combinations, and the interaction strengthens enough that its 13-week intervals
exclude zero. The primary result is not an artifact of the narrow 66-name sample.

### Alternative clustering

- **Name-clustered bootstrap** (blocks = symbol, 66 blocks): 13w excess DEF_diff CI [-0.95%, +2.37%]
  — still spans zero; INTERACTION CI [-6.29%, -0.16%], P(> 0) = 0.039. 26w excess INTERACTION CI
  [-4.77%, +2.85%] — spans zero.
- **Semester blocks for the 26-week horizon** (supplementary, not in the frozen spec): a 26-week
  window straddles two quarters, so quarter blocks do not fully absorb the serial overlap. Widening
  the block to a half-year moves the 26w excess interaction CI from [-6.17%, +4.94%] to
  [-6.87%, +5.02%] and the raw from [-9.68%, +3.16%] to [-10.04%, +3.04%]. No verdict changes; the
  quarter-clustered 26w intervals are modestly optimistic.

### Leave-one-name-out on the interaction (excess)

| Horizon | Full | LOO range | Sign always the same? | Most influential |
|---|---:|---|:--:|---|
| 13w | -3.36% | [-4.68%, -2.98%] | **yes** | IP, ORCL, AMD |
| 26w | -0.15% | [-1.12%, +0.54%] | **no** | CI, DHR, ABT |

No single name drives the 13-week interaction. The 26-week interaction is indistinguishable from zero
and its sign is decided by whichever name is dropped.

### The driver cell

The entire result lives in GROWTH · RISING (median -1.56% excess at 13w). It is not a single episode:
155 events across 56 quarters and 26 names, spread 16/34/59/46 across the 1990s/2000s/2010s/2020s; the
largest single quarter is 9.7% of the cell and the largest single name 8.4%; 13 of 26 names have a
negative median. The weakness of growth-cohort washouts under a RISING rate flag is broad rather than
concentrated — but see §6 and §7 before reading anything macro into it.

---

## 6. Cohort validity — read this before the tables

**Survivorship is total, and it is worse than "today's membership backfilled."** Three separate
backfills stack:

1. `data/baskets/membership.json` carries **zero removed members** across all six baskets used
   (`n_removed = 0`). There is no removal history at all — the basket leg is pure August-2026
   membership projected back to 1965.
2. The archetype leg is a **fiscal-2025 label** (`archetype__fy = 2025.0`, `archetype__as_of` mostly
   2026-04-30) applied to events as far back as 1965 — a sixty-year anachronism, not a mild one.
3. The ≥780-week gate keeps only names still listed after 15+ years, then price resolution kept only
   names present in `data/stocks`, a 235-name curated panel.

Every cell is conditioned on the name being alive, listed, and *still classified in that bucket* in
August 2026. Nothing here estimates what a contemporaneous observer could have selected.

**The GROWTH cohort is not a growth cohort.** Of its 26 names, **14 — contributing 300 of 554 events
(54%) — are admitted by the FY2025 archetype label alone**, and several are not growth in any
ordinary sense:

| Name | Events | FY2025 archetype | Admitted via |
|---|---:|---|---|
| IP (International Paper) | 55 | speculative_unprofitable | archetype only |
| OMC (Omnicom) | 32 | speculative_unprofitable | archetype only |
| INTC | 32 | speculative_unprofitable | archetype only |
| ADI | 27 | speculative_unprofitable | archetype only |
| NEM (Newmont) | 22 | high_beta_momentum | archetype only |
| TJX | 21 | secular_growth | archetype only |
| NRG | 14 | secular_growth | archetype only |
| PWR (Quanta) | 13 | speculative_unprofitable | archetype only |

A paper company, an ad holding company, and a gold miner together contribute 109 of 554 GROWTH events
(19.7%). Meanwhile several *basket*-admitted names carry archetypes that contradict the growth
framing outright — KLAC is `rate_sensitive`, LRCX and NVDA are `broken_growth`, MSFT and MRVL are
`mixed`, AVGO is `rate_sensitive`. And 13 of the 26 names (50%) are semiconductors or storage, so the
cohort is closer to a semis-plus-leftovers bucket than a style bucket. An exploratory split (post-hoc,
not pre-registered, no claim attached) puts the 13-week excess interaction at **-5.58%** for
semis-only versus **-1.60%** for growth-ex-semis — consistent with the "growth" leg largely measuring
semiconductor cyclicality.

**The DEFENSIVE cohort is cleaner but not clean.** ISRG (`broken_growth`), VRTX, GILD, DHR and MCK
(`deep_value`) enter through the healthcare basket; EA — a video-game publisher in Communication
Services — is the one name admitted by the archetype leg alone (`quality_compounder`, 17 events).

**One suspect series.** `data/stocks/ECHO.parquet` runs continuously from 2008-01-02 to 2026-07-31
with no calendar gap, is labeled Communication Services, and carries a single +70.2% one-day move on
2025-08-26. Echo Global Logistics was taken private in 2021 at $48.25 while this series prints
$26-30 in late 2021. The identity of the ticker across that span is not established here. It
contributes 10 GROWTH events; the leave-one-name-out range in §5 shows it is not load-bearing, but
the series should not be treated as one company's history.

**One second-order asymmetry between the cohorts.** The RSI-MACD is computed on the retroactively
dividend-adjusted series, not the price series a contemporaneous observer would have charted. That
adjustment is larger for high-yield names, so it perturbs the defensive cohort's indicator slightly
more than the growth cohort's — in a study whose whole point is the difference between those two
cohorts.

**Distinct-quarter clustering caveat.** Cells report 55-127 distinct quarters against 150-582 events,
so events are roughly 3-5 deep per quarter; the quarter block bootstrap absorbs that. It does **not**
absorb the serial overlap between adjacent quarters, which matters at 26 weeks — hence the
supplementary semester-block run in §5. Nor does it absorb repeated sampling of the same name (IP
alone supplies 10% of GROWTH events); the name-clustered bootstrap in §5 addresses that leg
separately. No single bootstrap here handles both dimensions at once.

**Multiplicity.** 24 nominal 90% intervals are reported as primary (4 horizon × measure combinations
× 3 statistics × 2 regime definitions). Four exclude zero; roughly 2.4 would be expected to do so by
chance under a global null. No multiplicity correction was pre-registered and none is applied. The
intervals are nominal and should be read as such.

---

## 7. The regime flag does not measure what the hypothesis means

This is the finding that constrains every number above, and it is a property of the frozen
specification rather than of the data.

R1 and R2 both carry the labels FALLING and RISING, but they agree on only **45.7%** of events —
**below the 49.3% expected by chance** given their own marginals. Cohen's **κ = -0.071**: the two
definitions of "short rates are rolling over" are very slightly *negatively* associated.

| | R2 = FALLING | R2 = RISING |
|---|---:|---:|
| **R1 = FALLING** | 406 | 536 |
| **R1 = RISING** | 336 | 329 |

Measured directly against the yield itself, over the 3,343 weekly DGS1 bars from 1962 that carry a
full trailing window (of 3,369 total):

| R1 reads | n | mean trailing 26w change | median | share with a *positive* 26w change | mean trailing 13w change |
|---|---:|---:|---:|---:|---:|
| FALLING | 1,672 | +0.001pp | **+0.04pp** | **51.9%** | -0.267pp |
| RISING | 1,671 | +0.009pp | 0.00pp | 49.1% | +0.270pp |

And at the 1,607 events specifically, the trailing 26-week change in the 1-year yield averaged
**+0.086pp (median +0.09pp) where R1 read FALLING** and **-0.059pp (median -0.01pp) where R1 read
RISING** — the sign of the actual rate move is, on average, the opposite of the label.

R1 is an RSI-MACD oscillator on the *level* of DGS1: `EMA14(RSI14) − EMA60(RSI14)` against its
5-period signal. It tracks roughly **one quarter** of rate momentum (mean trailing 13-week change
-0.267pp when FALLING versus +0.270pp when RISING — that leg works cleanly) and it flips frequently
inside multi-year trends. It is a short-horizon rate-deceleration flag. It is not a cycle-turn
detector, and "rolling over" in the operator's sense — a sustained downtrend in short rates — is
closer to R2.

Practical consequence: the §3 tables are an honest measurement of *the specified construction*, but
the FALLING/RISING column headers should be read as "1-year-yield RSI momentum below/above its
signal," not as "rate cycle down/up." That the interaction's sign is negative under **both**
definitions despite their near-zero association is the one piece of evidence here that travels; the
magnitudes do not.

---

## 8. Sanity gates

| Gate | Outcome |
|---|---|
| MCD in DEFENSIVE with a 2026-07-31 event | **PASS.** Detected: `MCD, 2026-07-31, 2026Q3, trailing-520 rank 0.0942, R1 = RISING, R2 = RISING, source data/stocks`. Unmatured at both horizons, so it is excluded from every outcome cell — detection only. MCD contributes 33 events overall. |
| DEFENSIVE washout count O(hundreds), not O(tens of thousands) | **PASS with note.** 1,053 events — ~1.0 × 10³, one order above "hundreds" and three below "tens of thousands". Mean 26.3 events per name across a median ~55-year history ≈ one event per name every 2.1 years, which is the arithmetically expected rate for a weekly RSI-MACD crossover restricted to the bottom 15% of a 10-year trailing window. |
| SPY span vs 1993 | **No shortfall.** `data/yahoo/SPY.parquet` runs 1993-01-29 → 2026-08-04; first completed weekly bar 1993-01-29. Consequence disclosed: excess cells cover 1993+ only — 1,215 of 1,597 matured 13-week events (76.1%). The 1965-1992 rate cycles, including the entire Volcker era, appear in the RAW table only and in no excess cell. |

**Detection totals.** 1,607 events over 1965-04-30 → 2026-07-31; 1,053 DEFENSIVE / 554 GROWTH.
R1: 942 FALLING / 665 RISING. R2: 742 FALLING / 865 RISING. Matured: 1,597 at 13w and 1,591 at 26w
raw; 1,215 and 1,209 with excess.

**Unconditional baselines** (all events, no regime split), median: DEFENSIVE +4.38% raw / +0.79%
excess at 13w and +6.73% / +0.38% at 26w; GROWTH +3.66% / +1.07% at 13w and +9.61% / +3.11% at 26w.

---

## 9. What would move this

Not more replications — the intervals are wide because the underlying differences are small relative
to dispersion, and no amount of resampling narrows that. Three things would change what this measures:

1. **A rate-regime definition that survives its own validity check.** Any candidate should be scored
   against the realized trailing and forward path of the yield *before* being used to condition
   returns, which R1 was not. R2 is the closer proxy to the operator's meaning and it is currently
   demoted to robustness.
2. **Point-in-time cohort membership.** A style label as of the event date, not FY2025 — without it,
   §6 caps what any DEF-versus-GRO comparison can mean, whatever the sample size.
3. **A pre-1993 market benchmark on a total-return basis** to bring the 1965-1992 rate cycles into
   the excess tables. `data/yahoo/_GSPC.parquet` reaches further back but is price-only, which would
   bias excess upward against dividend-adjusted stock closes; it was not used.

---

*Measurement packet for an operator ratification decision. Display tier. No promotion, no rank, no
size, no gate. Nulls printed rather than hidden, per the epistemics law.*

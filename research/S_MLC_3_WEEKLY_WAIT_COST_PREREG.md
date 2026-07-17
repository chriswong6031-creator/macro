# S-MLC-3 — Weekly-Wait Entry Cost on Leaders · PRE-REGISTRATION

**Battery:** S-MLC-3 (MLC masterplan §W6, study 3 of 3).
**Program:** Megacap & Leadership Coherence (MLC, chartered 2026-07-14).
**Author:** research agent (Sonnet). **Adjudicated 2026-07-16** — all freeze-review markers resolved; see freeze record at end of document.
**Pre-reg committed:** before any measurement run. No harness code in this PR.
**Wiring:** NONE. This pre-reg gates AUTHORITY only. The display surface ships freely regardless of verdict (MLC-R2; house law §Epistemics).

---

## 0. Question and honest prior

**Question.** For SPDR sector ETFs at RS rank #1 or #2 (of 11 sectors) AND within 2% of their 52-week high, what is the average cost of a half-size-now / half-on-weekly-confirm entry construction vs. full immediate entry, measured over the 10-40d forward SPY-excess horizon?

This directly interrogates the XLF construction from the 07-14 postmortem: the operator sized half into XLF at the close, intending to add the second half after a weekly-close confirmation. The question is whether that "weekly wait" systematically costs return in leader-continuation regimes, and if so, whether the magnitude justifies a "leaders exception" (enter full-size on leaders without the weekly-wait filter).

**Scope of the question: two possible outcomes.** The masterplan §W6 explicitly names both:
1. **Leaders-exception justified:** the weekly wait demonstrably costs statistically significant return in the leader-within-2%-of-52wh population. A GO verdict here justifies a leaders-exception pre-reg (a separate construction, not a wiring action here).
2. **Null — close and print:** the half-size / weekly-wait construction does not cost statistically significant return vs. full entry. Print the null honestly and close the question with this study.

This study decides WHICH outcome applies. It does not pre-judge the outcome.

**Mechanism hypothesis.** Sectors at the top of RS rankings within striking distance of 52-week highs are in high-momentum, low-fade environments. Waiting one week for "weekly confirmation" in such regimes risks missing the follow-through move: by the time the weekly close confirms, the first 4-5 trading days of the extension are already in the rearview. The hypothesis is that the delayed half-position enters at higher prices on average, costing a statistically significant fraction of the near-term excess return.

**Competing hypothesis.** The weekly wait reduces exposure to failed breakouts — cases where the sector reverses at the high rather than extending. In those cases, the half-size construction limits downside. If the population of failed breakouts is large enough, the weekly wait is beneficial (negative cost = positive risk-adjusted benefit). The study must measure both the return cost and the downside-miss rate.

**Honest prior.** SPDR sector ETFs have a deep history (XLK/XLF/XLV etc. from 1998-12-22) and the RS-rank + 52wh filter defines a specific sub-population. Historical sector-momentum studies suggest that near-high RS leaders tend to continue modestly (consistent with cross-sectional momentum), but the specific weekly-wait *cost* at *this filter* is not pre-known. Prior lean: **uncertain with slight lean toward a positive but small cost** — enough to check but not enough to pre-commit the direction of the outcome.

**Data verified:** `data/yahoo/` stores confirmed via a pre-reg read:
- XLK, XLF, XLV, XLE, XLY, XLU, XLI, XLB, XLP: 1998-12-22 → 2026-07-15 (6,931 rows each)
- XLRE: 2015-10-08 → 2026-07-15 (2,706 rows)
- XLC: 2018-06-19 → 2026-07-15 (2,028 rows)
- RSP: 2003-05-01 → 2026-07-15 (5,838 rows)
- SPY: 1993-01-29 → 2026-07-15 (8,421 rows)

The study uses the 9 ETFs with history from 1998-12-22 for the primary analysis. XLRE and XLC are included only for post-inception analysis (secondary context, not the primary ruler). All closes are dividend-adjusted (confirmed from parquet column structure matching SPY/XLF in the yahoo store).

**Standing kills honored.** No kill in `research/DO_NOT_REBUILD.md` directly implicates this construction. Adjacent entries reviewed:
- `rs-based member-dispersion gates` (§1, R-4): S-MLC-3 uses RS *rank* to define a population (top-2 of 11), not a dispersion gate. The RS rank defines which ETFs are *studied*, not a new gate on existing signals. Consistent with precedent from S-MLC-2 §0 analysis.
- `Signal-engine verdicts at non-pre-declared horizons` (§3): fully honored — the `horizon_role` is pre-declared in §2.3 of this document; the ladder is descriptive only.
- `Rotation × cycle-position entry-confluence` (§1, MLC-R3): not implicated — this study does not incorporate cycle position.
- `FRESH BUY as a buy edge on the Act-Now board` (§2): not implicated — this study tests entry timing construction cost, not the board's BUY signal itself.
- The sector_rotation_schedule.v1 kill (§1): S-MLC-3 does not produce a rotation schedule; it produces a decision about entry sizing. Not implicated.
No kill is triggered by this pre-registration.

---

## 1. Data construction

### 1.1 Sector ETF universe and history

**Full ETF roster (time-varying universe — adjudicated 2026-07-16):**
- 9 ETFs 1998-12-22→: XLK, XLF, XLV, XLE, XLY, XLU, XLI, XLB, XLP
- XLRE added at inception 2015-10-08 (10-ETF universe from that date)
- XLC added at inception 2018-06-19 (11-ETF universe from that date)
- Source: `data/yahoo/{ticker}.parquet` (dividend-adjusted close)
- Benchmark: `data/yahoo/SPY.parquet` (dividend-adjusted close)

XLRE and XLC are included in the primary analysis from their respective inception dates. The RS rank #1–2 threshold is computed over the universe available at each date. The pre-2015 analysis is 9-ETF only; 2015–2018 is 10-ETF; 2018→ is 11-ETF.

### 1.2 RS-rank construction (PIT, no look-ahead)

**60-session relative strength (RS) vs SPY:** for each ETF `s` and day `t`, RS_60d[s,t] = cumulative return of `s` over the 60 trading days ending day `t-1` (i.e., `close[t-1]/close[t-61] - 1`) divided by the corresponding SPY return. The rank is computed cross-sectionally over the time-varying ETF universe on day `t-1`.

**FROZEN (2026-07-16, adjudicated — Ruling 1):** The RS window is **60-session** (not 20d). The Leadership Board's sector momentum rank, which is the surface the operator actually reads, uses 60d RS. The study must interrogate the construction as the operator experiences it. The 20d RS is reported as a robustness sensitivity (§5, not a verdict cell).

considered and rejected: 20d RS as primary (captures recent momentum but is NOT the construction the operator experiences on the Leadership Board; dismissed).

**FROZEN (2026-07-16, adjudicated — Ruling 2):** The RS rank universe is **time-varying**: absolute rank #1–2 among the SPDRs listed at each date. The universe expands as XLRE (inception 2015-10-08) and XLC (2018-06-19) are added, so the effective universe is 9 ETFs (1998–2015), 10 ETFs (2015–2018), and 11 ETFs (2018→). No fixed-panel exclusion applies — the study must use the universe that was actually available to the operator on each date.

considered and rejected: 9-ETF fixed panel for all dates (clean but evaluates the construction as if XLRE/XLC never existed; dismissed); 11-ETF fixed panel with pre-inception exclusion (standard approach but changes the rank distribution in inconsistent ways; dismissed).

### 1.3 52-week-high proximity (PIT)

**52wh proximity:** on day `t-1`, compute `close[t-1] / max(close[t-252:t-1]) - 1`. The sector is "within 2% of 52-week high" if this value >= -0.02 (i.e., within 2% below the rolling 252-trading-day high, inclusive of the high itself).

**FROZEN (2026-07-16, adjudicated):** The 252-day window uses **trading days** (not calendar days). This is the correct PIT implementation — no forward-fill required, and the window is aligned with the operator's "52-week high" concept as rendered from daily close data.

### 1.4 Population definition — "leader-at-high" events

An event on day `t` for sector ETF `s` requires ALL of:
- **L1 — RS top-2:** `rank_60d[s,t-1]` ∈ {1, 2} (among the time-varying SPDR universe at day `t-1`: 9 ETFs pre-2015-10-08, 10 ETFs 2015-10-08–2018-06-19, 11 ETFs 2018-06-19→; measured end-of-day `t-1`)
- **L2 — Near 52wh:** `close[s,t-1] / max(close[s,t-252:t-1]) - 1 >= -0.02`
- **L3 — Not already counted:** minimum 21 trading-day separation from the prior event for the same ETF `s` (event-recycling exclusion to avoid clustering of overlapping windows)

These are the events at which the operator's half-size / weekly-wait decision point arises.

### 1.5 Entry construction definitions

**FROZEN (2026-07-16, adjudicated — Ruling 5):** Entry fill = **t+1 close** for BOTH legs. Forward windows are measured from that same t+1 close (no overlap double-count — the t+1 open-to-close return is included once in the measurement window, not counted in both the entry and the forward window). This is stated explicitly here to prevent double-count error in the harness.

**Full immediate entry (baseline):**
- Position: 1.0 × size at `close[t+1]`.
- Forward excess return: `(close[s,t+1+h] / close[s,t+1]) / (close[SPY,t+1+h] / close[SPY,t+1]) - 1` over horizon h.

**Half-size / half-on-weekly-confirm (treatment):**
- Position at day `t+1`: 0.5 × size at `close[t+1]`.
- Weekly confirmation: the "add" trigger fires if `close[s]` on the next Friday (the first Friday >= day `t+5`) is >= `close[s,t]` × (1 - δ) for some drawdown tolerance δ.

**FROZEN (2026-07-16, adjudicated — Ruling 3):** δ = **0 PRIMARY** (strict: weekly close ≥ entry close; no drawdown tolerance). The weekly confirmation means the ETF's weekly close is AT or ABOVE the t+1 entry close. δ = 1% (tolerates up to 1% weekly drawdown) is printed as a **sensitivity** check and is explicitly **NON-PROMOTABLE** — the sensitivity result cannot override the primary δ=0 verdict or authorize any wiring action.

considered and rejected: δ = 0.01 as primary (arbitrary tolerance; dismissed); δ = -0.03 stop form (changes the economic meaning of the construction from confirm to stop; dismissed).

- If the weekly confirm fires: add 0.5 × size at the Friday close (the first Friday ≥ t+5).
- If the weekly confirm does NOT fire (ETF weekly close has fallen below `close[t+1]`): the second half is NEVER added. The position remains at 0.5 × size.
- **Blended return:** weighted average of the two legs:
  - If confirm fires: `0.5 * r_from_t+1 + 0.5 * r_from_friday`
  - If confirm does not fire: `0.5 * r_from_t+1 + 0.5 * r_SPY_from_t+1` (non-confirmed half earns SPY total-return from t+1 to t+1+h; excess contribution of this leg = 0 by construction)

**FROZEN (2026-07-16, adjudicated — Ruling 4):** If the weekly confirm does NOT fire, the non-confirmed second half **parks in SPY** (earns SPY total-return from t+1 to t+1+h). This keeps the comparison fully SPY-excess-based: the non-confirmed half's excess contribution is **0 by construction**, which isolates the sector-timing question purely. The cash-parking alternative is printed descriptively (§5 robustness) for transparency but is NON-PROMOTABLE.

considered and rejected: truly hold as cash (0% return on non-confirmed half; not excess-ruler-consistent; dismissed).

### 1.6 The cost metric

**Entry cost** per event = `r_full_immediate_excess[s,t,h] - r_half_weekly_wait_excess[s,t,h]`

where both are measured vs. SPY over the same horizon h.

- A **positive cost** means full immediate entry outperformed the half-wait construction (the wait cost return).
- A **negative cost** means the half-wait construction outperformed (the wait was protective — failed breakout avoided).

The study reports the mean cost across all leader-at-high events, its confidence interval, and the distribution of individual event costs (to separate the "large positive cost in right tail" from the "small mean cost with high variance" scenarios).

---

## 2. Pre-registered gates and sample requirements

### 2.1 Sample requirements

The time-varying universe (adjudicated 2026-07-16) uses 9 ETFs from 1998-12-22, expanding to 10 at XLRE inception (2015-10-08) and 11 at XLC inception (2018-06-19). Over the 9-ETF window (~27 years), an estimated 2-4 leader-at-high events per ETF per year after the 21d separation filter yields roughly 9 × 27 × 2 = ~486 non-overlapping events. The XLRE/XLC windows add a smaller increment. Total effective-N across the full time-varying universe is expected to exceed 486. This is strong power for a 21d analysis.

**Effective-N floor:** >= 100 non-overlapping 21d events across the full time-varying universe (9-ETF panel 1998-12-22→2015-10-07, 10-ETF 2015-10-08→2018-06-18, 11-ETF 2018-06-19→). The original 9-ETF estimate (~486 events) is a lower bound; the time-varying universe adds events from XLRE and XLC during post-inception periods. If fewer than 100 non-overlapping 21d events are found, this is a data-quality failure to be reported honestly, not an inference failure.

### 2.2 Statistical gates

| Gate | Rule | Required for COST-IS-REAL verdict |
|---|---|---|
| **Primary test** | Within-month event-label permutation (DT-R14): permute the event labels within calendar month, 10,000 draws; null hypothesis = zero mean cost | p < 0.05 (two-sided), consistent with a non-zero cost |
| **HAC t-statistic** | Newey-West HAC on cost series, lags = floor(n_events^(1/3)) | `|t| >= 2.0` |
| **Era split** | Split by 2010 regime break (per DT-R16 era-split law — pooling across the 2010 break without an era split is forbidden by DO_NOT_REBUILD.md §3) | Same sign in both pre-2010 and post-2010 eras; report separately |
| **Episode-first-month blocking** | Block by calendar month; report within-block cost distribution | Same sign as pooled |
| **BH-FDR** | BH across the test matrix: 4 horizons × 3 cells (pooled, pre-2010, post-2010) = 12 cells; `alpha = 0.10` | Primary cell (pooled 21d) survives FDR |
| **Split-half sign-stability** | Divide events by calendar median date; both halves must have the same sign of mean cost | Required for COST-IS-REAL verdict |
| **Magnitude floor** | Economic significance | Mean cost >= 0.3% at 21d — **FROZEN 2026-07-16: confirmed**. Below this floor, no leaders-exception authorization regardless of p-value (the cost is immaterial from a portfolio management perspective). |
| **Confirm-miss rate** | Report fraction of events where the weekly confirm does NOT fire (the sector fails to re-confirm). This is the denominator insight: if confirm fails rarely, the wait cost is almost always realized; if it fails often, the wait saves capital in frequent failures | Reported as context, not a gate |

**Time-preserving null law (DT-R14 enforcement):** Cross-sector correlation among the 9 ETFs is substantial (all subject to SPY index moves). Standard errors must cluster at the date level (all events on the same date are treated as one cluster). The within-month permutation preserves the date-clustering structure by permuting the label assignment within month, not individual events. Naïve i.i.d. bootstrap is forbidden.

**Era-split law (DT-R16):** Era-pooled inference across the 2010 regime break without an era split is a wrong-ruler error per DO_NOT_REBUILD.md §3. The 1998→ history spans the pre-2010 and post-2010 regimes. Both eras must be reported separately. If the sign differs across eras, the verdict is at most ACCRUE (no pooled GO from conflicting eras).

**Overlap correction:** the event separation filter (L3: 21d minimum gap) largely prevents overlap at the 21d horizon. At the 40d and 63d horizons, events within 21d of each other may still overlap — standard Hodrick/Newey-West overlap correction must be applied at those horizons.

### 2.3 Pre-declared horizon_role ruler

**FROZEN (2026-07-16, adjudicated):** `horizon_role` = **21d** (trading days), consistent with S-MLC-1 and S-MLC-2 and with the battery's swing 2–4 week ruler. The cost of a ~5-session wait is most visible at 21d. Descriptive ladder includes 10d/40d/63d but verdicts at non-declared horizons are forbidden per DO_NOT_REBUILD.md §3.

**`horizon_role`: 21d (trading days).**

---

## 3. Verdict mapping (pre-committed)

This study has a pre-committed two-outcome structure (as stated in masterplan §W6):

**Outcome A — Leaders exception pre-reg is justified (COST-IS-REAL):**
All gates in §2.2 pass. The mean cost is positive (full entry outperforms), sign-stable across eras and halves, and statistically significant. **What this earns:** authorization to write a new pre-reg for a "leaders exception" entry sizing rule (a separate pre-reg, not an immediate wiring action). The leaders exception would propose: for sectors at RS #1-2 within 2% of 52wh, use full-size immediate entry rather than the half-size/weekly-wait filter. That construction requires its own pre-registered gate before wiring.

**Outcome B — Null, close the question:**
The mean cost is not statistically significant (|t| < 2.0, or fails FDR, or fails sign-stability, or does not clear the magnitude floor). **What this means:** the weekly-wait construction does not demonstrably cost return at the leader-at-high filter. Print the null honestly in the report. Close the leaders-exception question for this specific construction. The half-size/weekly-wait entry rule is retained as-is (no wiring change; the evidence doesn't justify a change).

**Outcome C — Negative cost (wait is protective):**
The mean cost is negative AND sign-stable AND |t| >= 2.0 (the weekly-wait construction outperforms full immediate entry). **What this means:** the weekly-wait provides statistically significant downside protection in the leader-at-high population. This is the "failed-breakout-avoided" regime. Print this as an honest finding. No wiring action — this finding strengthens the existing half-size/weekly-wait design but does not require a new pre-reg. Report the confirm-miss rate to characterize how often the protection fires.

---

## 4. What a leaders-exception GO buys (if Outcome A)

A COST-IS-REAL verdict (Outcome A) enables ONLY:

1. Authoring a new separate pre-reg: "Leaders-exception sizing rule — full-size immediate entry for RS #1-2 ETFs within 2% of 52wh." That pre-reg must specify: the exact entry rule, the lookback for RS computation, the 52wh threshold, any additional filters, and the gauntlet gates.
2. A display chip on the Leadership Board (W1): "This sector is a current leader near its 52-week high — historical wait costs apply." (Display-tier disclosure, not an entry gate.)

It does NOT:
- Change any engine entry-size logic.
- Gate, suppress, or modify the half-size/weekly-wait construct in any code path.
- Constitute a wiring action for any display or scoring surface.

---

## 5. Robustness checks (secondary, not verdict-determining)

The following are reported as context but excluded from the multiple-testing family for verdict purposes:

1. **20d RS rank (vs. 60d primary):** re-run with 20d RS rank as a sensitivity check. Results are diagnostic and NON-PROMOTABLE.
2. **δ = 0.01 tolerance:** re-run with 1% weekly-drawdown tolerance. Diagnostic only.
3. **XLRE/XLC inclusion for post-2015/2019 period:** diagnostic context.
4. **Sector sub-group analysis:** cyclicals (XLY, XLF, XLI, XLK, XLB) vs. defensives (XLU, XLV, XLP, XLE) separately. Diagnostic only.
5. **SPY investment vs. cash for non-confirmed second half:** sensitivity on the §1.5 assumption. Diagnostic.

None of these robustness checks can flip or override the primary verdict. They are printed in the report's "robustness" section.

---

## 6. What this pre-reg deliberately does NOT claim

- It does not claim the leader-at-high filter itself generates alpha (the filter defines a population; its absolute return is not the question here).
- It does not test the continuation of RS leadership (S-MLC-1).
- It does not test suction conditionality (S-MLC-2).
- It does not claim that a null validates the half-size/weekly-wait construct as optimal — it only says the specific cost measured here is below the detection threshold.
- A null does not prevent the operator from maintaining the half-size rule on other grounds (risk management, psychological, drawdown-minimization). The study tests empirical return cost, not the full decision rationale.
- It does not use LLM-originated signals or verdicts at any step (house law §1).
- It does not close any family of entry-timing questions beyond the specific half-size/weekly-wait construction tested at the RS #1-2 + 52wh filter on SPDR sector ETFs.

---

## 7. Deliverables

1. `scripts/s_mlc_3_weekly_wait_cost.py` — harness (PIT-clean; confirms at exact next-Friday; within-month permutation primary; HAC secondary; era-split mandatory; date-clustered SEs).
2. `reports/s-mlc-3-weekly-wait-cost.md` — **bold verdict** (Outcome A/B/C) first, gates table, confirm-miss rate, era-split table, cost distribution plot data, "what this does NOT show."
3. Registry append to `data/experiments/registry_seed.json` — entry `s-mlc-3-weekly-wait-cost`, `kind: phase0_backtest`, `registered_on: 2026-07-16`, `come_back_on: 2026-09-01` (first read — sufficient history already exists, run after harness is built), `prereg: research/S_MLC_3_WEEKLY_WAIT_COST_PREREG.md`.
4. If Outcome A: separate leaders-exception pre-reg (new document, new PR). No wiring in this PR.
5. NO engine wiring in the pre-reg or results PR.

---

Registered 2026-07-16. FROZEN 2026-07-16 (adjudicated freeze record below). Any amendment requires a dated APPEND section, never edits to frozen sections.

```yaml
# machine-checkable frontmatter
study_id: s-mlc-3-weekly-wait-cost
program: mlc
wave: W6
battery: S-MLC-3
registered_on: "2026-07-16"
frozen_on: "2026-07-16"
status: frozen
horizon_role: 21d  # FROZEN 2026-07-16: confirmed (swing 2-4w ruler)
rs_window: 60d  # FROZEN 2026-07-16: 60-session RS (Leadership Board construction)
rs_universe: time-varying  # FROZEN 2026-07-16: 9 ETFs pre-2015, 10 ETFs 2015-2018, 11 ETFs 2018+
effective_n_floor: 100  # non-overlapping 21d events (time-varying universe)
primary_test: within-month-event-label-permutation  # DT-R14, cluster at date
test_direction: two-sided  # cost may be positive or negative
confirm_threshold_delta: 0.0  # FROZEN 2026-07-16: delta=0 PRIMARY (strict weekly close >= entry close)
confirm_threshold_delta_sensitivity: 0.01  # NON-PROMOTABLE sensitivity only
nonconfirm_second_half: spy  # FROZEN 2026-07-16: non-confirmed half earns SPY return (excess=0 by construction)
entry_fill: t+1_close  # FROZEN 2026-07-16: t+1 close; forward windows from t+1 close
magnitude_floor_pct: 0.3  # FROZEN 2026-07-16: 0.3% at 21d confirmed
era_split: "2010"  # DT-R16 mandatory
data_source: data/yahoo/  # XLK etc. 1998-12-22->
authority_target: leaders_exception_prereg_authorization  # on Outcome A
prereg_file: research/S_MLC_3_WEEKLY_WAIT_COST_PREREG.md
```

---

## Freeze record

*All rulings applied 2026-07-16.*

| # | Item | Ruling | Rationale |
|---|---|---|---|
| 1 | RS window | 60-session RS (not 20d) | Leadership Board surface uses 60d RS; study must interrogate the construction as the operator experiences it |
| 2 | Rank universe | Absolute rank #1–2 among SPDRs listed at each date (time-varying 9→10→11 across XLRE/XLC inceptions) | No fixed-panel exclusion; universe must match what was available to the operator on each date |
| 3 | Confirmation tolerance δ | δ = 0 PRIMARY (strict: weekly close ≥ entry close); δ = 1% printed as sensitivity, explicitly NON-PROMOTABLE | Strict δ=0 is the mechanically cleanest "confirm" definition; sensitivity cannot override or authorize wiring |
| 4 | Non-confirmed half parking | Parks in SPY (earns SPY total-return from t+1 to t+1+h); excess contribution = 0 by construction | Isolates the sector-timing question; keeps comparison fully SPY-excess-based |
| 5 | Entry fill | t+1 close; forward windows measured from that same t+1 close (no overlap double-count) | Earliest non-look-ahead fill; stated explicitly to prevent double-count in harness |
| 6 | Magnitude floor | 0.3% excess at 21d — confirmed; below it, no leaders-exception authorization regardless of p-value | Below 0.3% the cost is immaterial from a portfolio management perspective |
| — | 252d window for 52wh | Trading days confirmed (not calendar days) | Standard PIT implementation for daily close data |

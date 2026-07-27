# PSS-SR3 preregistration — synchronized participation recovery

Status: **FROZEN BEFORE FORWARD OUTCOMES** (2026-07-27).

Program home: `research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md`
W-SIG/W-FOUNDRY. This is the next genuinely distinct species after PSS-F1
through PSS-F4, PSS-SR1, and PSS-SR2 failed.

Canonical identifier: **PSS-SR3** (`pss_sr3_participation_recovery`).

## 0. Prior information and trial budget

The following information was visible before this freeze and cannot count as
confirmation:

- the completed PSS-F1 through PSS-F4, F4R/F4H, PSS-SR1, and PSS-SR2 results;
- SR2's central mechanism inversion: after peers stopped making new lows, a
  subject that alone returned to its reference low was an idiosyncratic
  laggard, not a terminal-supply opportunity;
- construction-only feasibility from
  `scripts/research/pss_sr3_participation_feasibility.py`, which contains no
  outcome loader or forward metric:
  - 6,294 complete held-recovery paths across all 799 mapped names;
  - nine passive level-recovery shapes: peer distance 0.25/0.50/0.75 frozen
    ATR crossed with breadth floor 0.50/0.60/0.70;
  - six affirmative joint-recovery shapes: fixed +0.50 ATR level, 3/5-session
    trend lookback, and breadth floor 0.40/0.50/0.60;
  - one nested-control census holding passive peer level recovery constant;
  - the exact final nested tape has 4,981 primary-comparison paths: 2,065
    treatments across 733 names, 2,916 level-recovered controls, 380 treatment
    names with at least three paths, and 1,313 weak-level paths retained only
    as a diagnostic;
  - after keep-first name-month de-duplication, exact sector × action-month ×
    anchor-severity × delay strata with at least two rows per label number 91
    DEV, 55 VAL, and 53 FWD;
  - equal-weight within-stratum treatment-control action-close distance is
    -0.018 ATR in DEV, +0.020 ATR in VAL, and -0.020 ATR in FWD; and
  - conditional active-participation share among passive-level-qualified
    opportunities is 35.9% in H1-2022 versus 67.9% in Sep-Nov 2022.

No MAE, tail, proximity, trough, competing-risk, forward-return, or later price
value was read during feasibility. Outcome completeness was checked only as
`action_position + 63 < panel_length`.

The family budget is conservatively declared as **17**: sixteen
construction-only feasibility shapes plus this one outcome-bearing trial.
There is one final outcome construction and no outcome-selected threshold grid.

## 1. First-principles mechanism

The failed SR2 construction inferred terminality from an absence: peers were no
longer making new lows. Absence of weakness is not demand. It can coexist with
passive drift, threshold censoring, or a subject-specific laggard.

SR3 requires an affirmative state transition. After a systemic fresh-low
anchor:

1. the subject itself must recover from and hold above its frozen stress low;
2. a majority of peers must also be materially above their own same-anchor
   lows; and
3. that majority must be actively advancing over the latest trading week on
   all three action-window closes.

The primary control holds points 1 and 2 constant and lacks only point 3.
Therefore the comparison asks whether synchronized current participation adds
information beyond equivalent subject geometry and equivalent passive peer
distance from the stress low.

Second-order support:

1. broad active peer demand reduces correlation-one deleveraging and passive
   basket drag rather than merely observing that forced selling paused;
2. requiring the subject to recover and hold removes SR2's idiosyncratic
   laggard selection; and
3. three completed sessions prevent a one-day breadth thrust from manufacturing
   the label.

Third-order support:

1. peer-specific frozen ATR and formation lows normalize different stock
   personalities without outcome fitting;
2. a five-session positive trend demands current capital participation instead
   of giving credit for an old rebound; and
3. the nested level-recovered control isolates active participation from safe
   lateness, while exact calendar/severity/delay strata prevent one broad rally
   from masquerading as thousands of independent observations.

This is a reset-confirmation / forward-risk gate. It never calls a bottom and
cannot change entry, rank, size, alerts, or authority without a later ruling.

## 2. Distinction from killed constructions

SR3 is not a reversal or retiming of SR2:

- SR2 acted at the first subject retest near the formation low after a rebound;
- SR3 has no retest and never conditions on the subject returning alone toward
  a low after peers recover;
- SR2 labeled paths by contraction in ex-self peer new-low breadth relative to
  its formation peak;
- SR3 labels paths by affirmative peer recovery from peer-specific lows plus
  positive five-session price participation;
- SR3's primary control already has a majority of peers recovered in level, so
  the only treatment distinction is current active participation; and
- the subject itself must be in a three-session held-recovery state.

SR3 is also not a breadth thrust, F2's overnight/intraday decomposition, F3
residualization, an F4 wrapper, or the killed subject-elasticity response in
SR1. It is a peer-specific challenge/recovery participation state observed at
an independently fixed subject recovery action.

## 3. Wrong-ruler check

The claim is:

> Given the same systemic anchor, held subject recovery, passive majority peer
> recovery, calendar, severity, and delay, does active majority peer
> participation reduce the next 63 sessions' drawdown/tail risk and identify a
> durable reset more reliably?

This is an entry-timing and forward-risk claim, not a long-hold-return claim.
MAE63 and tail risk are primary. Proximity to the local low is co-primary
context. Forward returns alone cannot pass.

## 4. Data, universe, eras, and point-in-time law

- Name OHLCV: `data/baskets/ohlcv/{sym}.parquet`.
- Sector assignment: `data/breadth/ticker_sectors.parquet`.
- Universe spine: eligible names in
  `data/research/ptt_w1_panel.parquet`.
- Only the eleven standard GICS sectors are admitted.
- A subject needs at least 15 other peers with valid data on every breadth or
  recovery observation used.
- Missing names, sector mappings, histories, peer counts, or complete
  63-session outcomes are excluded with reason counts.
- There is no SPY or sector-ETF fallback.

Current-listed-name and current-sector membership introduce survivor and
classification bias. Historical evidence can qualify only a prospective
shadow on a frozen live membership snapshot.

Study eras:

- DEV: 2020-07-01 through 2022-12-31;
- VAL: 2023-01-01 through 2024-12-31;
- FWD descriptive: 2025-01-01 onward.

Every rolling threshold is shifted one session. A future print never fills a
past missing value.

## 5. Frozen construction

### 5.1 Ex-self systemic stress anchor

For name `i` on session `t`:

`new_low[i,t] = close[i,t] <= min(close[i,t-60:t-1])`

Among valid W1-panel names currently mapped to the same GICS sector:

`peer_new_low_breadth[-i,t] = sum(new_low[j,t], j != i) / n_valid[-i,t]`

The subject is removed from both numerator and denominator. At least 15 peers
must be valid. The point-in-time breadth-extreme threshold is the shifted
trailing 126-session 80th percentile with 63 observations minimum.

An anchor candidate occurs when:

- the subject closes at or below its prior 60-session close low;
- ex-self peer new-low breadth is at least 15%; and
- that breadth is at or above its shifted trailing 80th percentile.

The first candidate is accepted. The following 21 sessions cannot create
another anchor for that name; the next admissible anchor is `a + 22`.

### 5.2 Four-session formation and frozen scales

The formation window is anchor `a` through `a + 3`, inclusive. It is observable
only at the `a + 3` close.

Frozen for the subject:

- `ATR_i,A`: 14-session mean true range using data through `a - 1`;
- `reference_low_i,A`: minimum subject intraday low over `a:a+3`; and
- anchor and formation-peak ex-self new-low breadth.

Frozen separately for every peer `j`:

- `ATR_j,A`: the same prior-only ATR14 at `a`; and
- `reference_low_j,A`: peer `j`'s minimum intraday low over `a:a+3`.

Peers with invalid scales are absent from recovery numerators and denominators.
At least 15 valid ex-self peers remain.

### 5.3 Subject held-recovery action

Search through 30 sessions after formation confirmation. Action `B` is the
first close for which all are true:

- on every session `B-2:B`, subject close is at least
  `reference_low_i,A + 0.50 * ATR_i,A`;
- on every session `B-2:B`, subject intraday low is no lower than
  `reference_low_i,A - 0.50 * ATR_i,A`; and
- at `B`, subject close is between
  `reference_low_i,A + 1.00 * ATR_i,A` and
  `reference_low_i,A + 1.75 * ATR_i,A`, inclusive.

The action is stamped at B's close. No later recovery may replace the first.
Every treatment and control shares this exact subject path.

### 5.4 Passive and active peer recovery

For each valid peer `j` and each session `t` in `B-2:B`:

`level_recovered[j,t] =
 close[j,t] >= reference_low_j,A + 0.50 * ATR_j,A`

`actively_recovered[j,t] =
 level_recovered[j,t] AND close[j,t] > close[j,t-5]`

The subject is excluded. Define equal-weight ex-self breadth for each state and
take the minimum across the three completed action-window sessions:

`level_min = min_t mean(level_recovered[j,t])`

`active_min = min_t mean(actively_recovered[j,t])`

At least 15 peers must be valid on every session.

### 5.5 Treatment and disjoint controls

- **SR3 treatment:** `level_min >= 0.50` and `active_min >= 0.50`.
- **Level-recovered primary control:** `level_min >= 0.50` and
  `active_min < 0.50`.
- **Weak-level diagnostic:** `level_min < 0.50`; printed but excluded from
  primary promotion inference.

Thus every primary-comparison path already has a passive majority off its
formation low. Treatment cannot win merely because peers are farther from
their lows.

There is one threshold set. The five-session lookback, three-session
persistence, +0.50 ATR peer distance, and 50% breadth floors cannot be retuned
after outcomes.

## 6. Outcomes

All outcomes begin after the observable B close:

- `MAE63`: worst close-to-close excursion over the next 63 sessions;
- `prox`: percentage distance from the minimum close in +/-31 sessions;
- `W5`: within 5% of that low;
- `called`: trough offset from -2 through +5 sessions;
- `tail10`: MAE63 at or below -10%; and
- `tdt`: signed trading-day distance to the +/-31-session trough.

Binary outcomes are reduced to rates, never medians of binary-minus-baseline
rows.

Competing risk over the same fixed 63 sessions:

- rebound: close reaches +8% from B close;
- breach: intraday low falls below
  `reference_low_i,A - 0.50 * ATR_i,A`;
- if both first occur on one session, breach wins;
- `rebound8_first = 1` only when rebound occurs first; and
- unresolved paths stay in the denominator as failures.

Action diagnostics include delay, normalized close distance, anchor breadth,
passive/active peer breadth, and next-open gap.

## 7. Primary inference

To prevent repeated events and calendar regimes from masquerading as
independent names:

1. keep only the first primary-comparison action for each name in each calendar
   month;
2. assign fixed bands:
   - anchor severity: `[0.15,0.30)`, `[0.30,0.50)`, `[0.50,1.01]`;
   - delay from formation confirmation: `[1,10]`, `[11,20]`, `[21,30]`;
3. define a stratum as sector × B calendar month × severity band × delay band;
4. require at least two treatments and two level-recovered controls;
5. compute continuous label values as the median across events and binary label
   values as the mean; and
6. equal-weight the resulting stratum effects.

Positive always means treatment is better:

- MAE: treatment minus control;
- W5/called/rebound-first: treatment minus control; and
- tail10/breach-first: control minus treatment.

The primary one-sided p-value is a within-stratum label permutation:

- treatment counts are preserved in every stratum;
- labels move only among paths with the same sector, month, anchor-severity
  band, and delay band;
- 2,000 permutations, seed **20260806**.

A three-calendar-month circular moving-block bootstrap supplies diagnostic 95%
confidence intervals:

- all strata in a month move together;
- block length matches the overlapping 63-session horizon;
- 1,000 resamples, seed **20260807**; and
- the bootstrap is never used as a primary p-value.

DEV and VAL are adjudicated separately. FWD is descriptive. All estimates,
including adverse ones, print.

## 8. Confound and robustness checks

The report must print:

- treatment/control subject action delay, close distance, anchor breadth,
  passive breadth, active breadth, and next-open gap by era;
- the treatment-control action-close-distance difference within primary
  strata;
- weak-level diagnostic results;
- the nested mechanism comparison against the level-recovered control;
- leave-one-sector-out primary effects;
- treatment and control counts by sector, month, era, and name;
- informative-stratum counts and retained/dropped events;
- names with at least three treatment paths;
- H1-2022 versus Sep-Nov 2022 primary opportunity density, treatment density,
  and conditional treatment share; and
- exclusions by reason.

If treatment is more than 0.25 frozen ATR farther above the reference low than
control after primary stratification, any apparent timing improvement is
disqualified as safe-late selection.

## 9. Decision law

Historical evidence can qualify SR3 only for a frozen prospective display
shadow. Qualification requires all of:

1. in both DEV and VAL, treatment beats the level-recovered primary control on
   MAE and tail10 with positive moving-block 95% lower bounds and primary
   permutation `p <= 0.05`;
2. in both eras, `rebound8_first` improves and at least one of W5 or called
   improves, with no binary denominator degeneracy;
3. at least 500 names receive treatment, at least 100 have three or more
   treatments, and at least 40 informative primary strata exist in each of DEV
   and VAL;
4. H1-2022 conditional treatment share among primary opportunities is at least
   15 percentage points below Sep-Nov 2022, while raw opportunity density is
   disclosed;
5. treatment's primary-stratified action-close distance is no more than 0.25
   ATR farther above the reference low than control in DEV or VAL;
6. leave-one-sector-out MAE and tail effects remain positive in both eras and
   no single sector supplies more than 25% of treatments; and
7. neither MAE nor tail reverses sign in descriptive FWD.

If any requirement fails, the exact SR3 construction is killed and added to
`research/DO_NOT_REBUILD.md`. Threshold retiming, removing the nested
level-recovered control, shortening persistence, or replacing affirmative
trend with new-low non-propagation is not a new species.

If every requirement passes, the only permitted next step is a deterministic,
display-only prospective ledger:

- no entry/rank/size/gate/alert authority;
- nightly as sole advancer;
- frozen membership snapshot and construction hash;
- no historical backfill;
- 63-session maturity before grading; and
- a separate future promotion ruling.

## 10. Planned outputs

- `scripts/research/pss_sr3_participation_recovery.py`
- `tests/test_pss_sr3_participation_recovery.py`
- `reports/pss_sr3_participation_recovery.md`
- `data/research/pss_sr3_participation_recovery_events.parquet`
- `data/research/pss_sr3_participation_recovery_panel.parquet`
- `data/research/pss_sr3_participation_recovery_census.parquet`

The study stays off render and nightly paths. Unchanged inputs and seeds must
produce byte-equivalent logical content.

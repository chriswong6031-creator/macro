# PSS-SR2 preregistration — persistent ex-self peer diffusion

Status: **FROZEN BEFORE FORWARD OUTCOMES** (2026-07-27).

Program home: `research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md`
W-SIG/W-FOUNDRY. This is the operator-approved next species after PSS-F1
through PSS-F4 and PSS-SR1 failed.

Canonical identifier: **PSS-SR2** (`pss_sr2_peer_diffusion`).

## 0. Prior information and trial budget

The following information was visible before this freeze and cannot count as
confirmation:

- the completed PSS-F1 through PSS-F4, F4R/F4H, and PSS-SR1 results;
- SR1's central failure: the stock-level elasticity treatment selected names
  already farther above their reference low, while two-shock conditioning left
  only 13 informative validation pulses;
- construction-only feasibility counts from fifteen variants that read no
  forward outcome:
  - a sector-event version produced only 62 complete retests;
  - broadening the sector anchor produced 65–137 retests but still only 8–20
    treatment events in VAL;
  - moving the action clock to each name's own retest produced 5,846 complete
    paths in the exact final construction;
  - the exact final tape has 798 names, 3,586 treatment paths across 791 names,
    2,260 disjoint controls across 750 names, and 659 names with at least three
    treatments;
  - after keep-first name-month de-duplication, the exact inference strata
    (sector × month × anchor-severity band × delay band, at least two rows per
    label) number 69 DEV, 55 VAL, and 37 FWD;
  - treatment share is 56.8% in H1-2022 versus 68.9% in Sep–Nov 2022. Raw
    action density remains higher in H1 because the bear market creates many
    more fresh-low opportunities; the frozen containment test therefore grades
    the conditional treatment share, not an opportunity-confounded raw count.

No MAE, tail, proximity, trough, competing-risk, or forward-return value was
read during feasibility.

The family budget is conservatively declared as **16**: fifteen
construction-only feasibility shapes plus this one outcome-bearing trial.
There is one final construction and no outcome-selected threshold grid.

## 1. First-principles mechanism

A durable low is not just one stock refusing to fall. It is a failure of
weakness to keep propagating through the stock's peer network.

The anchor proves that the name and a material share of its sector peers were
being liquidated together. The name then rebounds and returns to its own
reference low. If, during all three sessions ending at that retest, no more than
half of the anchor's peer new-low breadth remains, the same price challenge is
now occurring after the cross-sectional supply cascade has stopped spreading.

The construction deliberately excludes the subject name from peer breadth.
Therefore a stock's own rebound, low hold, rejection bar, or distance from the
low cannot manufacture its treatment label.

Second-order support:

1. fewer simultaneous peer failures reduce correlation-one deleveraging and
   passive-basket feedback;
2. persistence for three completed sessions distinguishes a durable
   propagation failure from a one-day quiet patch; and
3. the individual retest supplies adverse price pressure while the external
   breadth state identifies whether that pressure is isolated or systemic.

Third-order support:

1. the cap-weighted sector ETF can hide broad member weakness, so the mechanism
   reads equal-weight member failures directly; and
2. name-specific retests preserve personality timing while shared peer state
   creates repeat coverage far beyond SR1's sparse synchronized-pulse design.

This is a reset-confirmation / forward-risk gate. It never calls a bottom and
cannot change entry, rank, size, alerts, or authority without a later ruling.

## 2. Distinction from killed constructions

SR2 is not a threshold retiming of SR1:

- SR1 required two sector-shock pulses and labeled the stock by its own
  price-damage elasticity;
- SR2 requires no second sector shock, beta, R², sector ETF retest, or
  stock-return elasticity;
- SR2 labels the action exclusively with ex-self sector-member breadth; and
- SR2 holds the name's complete anchor → rebound → retest geometry identical in
  treatment and control.

SR2 is also not PSS-F3 residualization, a sector-state gate on an A-share
reversal, a breadth thrust, or a breadth-only entry. It asks whether
cross-sectional new-low propagation persists during an already-qualified
individual retest.

## 3. Wrong-ruler check

The claim is:

> Given the same observable fresh-low, rebound, and retest geometry, does
> persistent contraction in ex-self peer failures reduce the next 63 sessions'
> drawdown/tail risk and locate a durable reset more reliably?

This is an entry-timing and forward-risk claim, not a long-hold-return claim.
The primary house ruler remains MAE63 and the competing tail event. Proximity to
the ±31-session low is co-primary context. Forward returns alone cannot pass
the gate.

## 4. Data, universe, eras, and point-in-time law

- Name OHLCV: `data/baskets/ohlcv/{sym}.parquet`.
- Sector assignment: `data/breadth/ticker_sectors.parquet`.
- Universe spine: eligible names in
  `data/research/ptt_w1_panel.parquet`.
- Only the eleven standard GICS sectors are admitted.
- A subject needs at least 15 other peers with valid close and trailing-low
  history on every breadth observation used.
- Missing names, sector mappings, peer counts, histories, or complete
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

### 5.1 Ex-self peer new-low breadth

For name `i` on session `t`:

`new_low[i,t] = close[i,t] <= min(close[i,t-60:t-1])`

Among valid W1-panel names currently mapped to the same GICS sector:

`peer_breadth[-i,t] = sum(new_low[j,t], j != i) / n_valid_peers[-i,t]`

The subject is removed from both numerator and denominator. At least 15 peers
must be valid.

The point-in-time breadth-extreme threshold is the shifted trailing 126-session
80th percentile with 63 observations minimum.

### 5.2 Anchor and four-session formation

An anchor candidate occurs when:

- the subject closes at or below its prior 60-session close low;
- ex-self peer breadth is at least **15%**; and
- ex-self peer breadth is at or above its shifted trailing 80th percentile.

The first candidate is accepted. The following 21 sessions cannot create
another anchor for that name; the next admissible anchor is session `a + 22`.

The formation window is anchor `a` through `a + 3`, inclusive. It is known only
at the `a + 3` close.

Frozen at the anchor:

- `ATR_A`: 14-session mean true range using data through `a - 1`;
- `reference_low_A`: minimum subject intraday low over `a:a+3`; and
- `peer_peak_A`: maximum ex-self peer breadth over `a:a+3`.

### 5.3 Rebound and tested-low geometry

Within 40 sessions after formation confirmation, the first subject close at
least `reference_low_A + 1.00 * ATR_A` establishes the rebound.

The retest search begins two sessions after that rebound so three fully
observed peer-breadth sessions can end at the action. The action `B` is the
first session, no later than formation-confirmation + 40, satisfying:

- `low_B >= reference_low_A - 0.50 * ATR_A`;
- `low_B <= reference_low_A + 0.75 * ATR_A`; and
- `close_B <= reference_low_A + 1.50 * ATR_A`.

Every treatment and control shares this exact past-price geometry. The action
is stamped at B's close; next-session open gap is diagnostic only.

### 5.4 Treatment and disjoint controls

Define:

`diffusion_ratio = max(peer_breadth[-i,B-2:B]) / peer_peak_A`

- **SR2 treatment:** `diffusion_ratio <= 0.50`.
- **Geometry control:** the identical complete path with
  `diffusion_ratio > 0.50`.
- **Transient-contraction diagnostic:** a geometry-control path whose breadth
  at B alone is at most half the anchor peak but whose three-session maximum is
  above half. This is reported to show whether persistence adds information
  beyond a one-day snapshot; it is not a separate promotion trial.

There is one threshold set. No later valid retest may replace the first.

## 6. Outcomes

All outcomes begin after the observable B close:

- `MAE63`: worst close-to-close excursion over the next 63 sessions;
- `prox`: percentage distance from the minimum close in ±31 sessions;
- `W5`: within 5% of that low;
- `called`: trough offset from −2 through +5 sessions;
- `tail10`: MAE63 at or below −10%; and
- `tdt`: signed trading-day distance to the ±31-session trough.

Binary outcomes are reduced to rates, never medians of binary-minus-baseline
rows.

Competing risk over the same fixed 63 sessions:

- rebound: close reaches +8% from B close;
- breach: intraday low falls below
  `reference_low_A - 0.50 * ATR_A`;
- if both first occur on one session, breach wins;
- `rebound8_first = 1` only when rebound occurs first; and
- unresolved paths stay in the denominator as failures.

Action geometry diagnostics include delay, normalized low depth, normalized
close distance, anchor breadth, current breadth, three-session breadth, and
next-open gap.

## 7. Primary inference

To prevent repeated events and calendar regimes from masquerading as
independent names:

1. keep only the first action for each name in each calendar month on the
   inference tape;
2. assign each action to fixed bands:
   - anchor severity: `[0.15,0.30)`, `[0.30,0.50)`, `[0.50,1.01]`;
   - delay from formation confirmation: `[1,15]`, `[16,27]`, `[28,40]`;
3. define a stratum as sector × B calendar month × severity band × delay band;
4. require at least two treatments and two controls in a stratum;
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
- 2,000 permutations, seed **20260804**.

This is the time- and severity-preserving primary. It does not treat thousands
of names in one selloff as independent calendar evidence.

A three-calendar-month circular moving-block bootstrap supplies diagnostic 95%
confidence intervals:

- all strata in a month move together;
- the block length matches the overlapping 63-session outcome horizon;
- 1,000 resamples, seed **20260805**; and
- the bootstrap is never used as a primary p-value.

DEV and VAL are adjudicated separately. FWD is descriptive. All estimates,
including adverse ones, print.

## 8. Confound and robustness checks

The report must print:

- treatment/control delay, anchor breadth, normalized retest low, normalized
  action-close distance, and next-open gap by era;
- the treatment-control action-close-distance difference within primary
  strata;
- transient-contraction results;
- leave-one-sector-out primary effects;
- treatment and control counts by sector, month, era, and name;
- informative-stratum counts and events retained/dropped;
- names with at least three treatment paths;
- H1-2022 versus Sep–Nov 2022 total opportunity density, treatment density, and
  conditional treatment share; and
- exclusions by reason.

The action-close distance is a direct SR1 failure guard. If treatment is more
than 0.25 frozen ATR farther above the reference low than control after primary
stratification, any apparent “timing” improvement is disqualified as safe-late
selection.

## 9. Decision law

Historical evidence can qualify SR2 only for a frozen prospective display
shadow. Qualification requires all of:

1. in both DEV and VAL, treatment beats geometry control on MAE and tail10 with
   positive moving-block 95% lower bounds and primary permutation `p <= 0.05`;
2. in both eras, `rebound8_first` improves and at least one of W5 or called
   improves, with no binary denominator degeneracy;
3. at least 500 names receive treatment, at least 100 have three or more
   treatments, and at least 40 informative primary strata exist in each of DEV
   and VAL;
4. H1-2022 conditional treatment share is at least 10 percentage points below
   Sep–Nov 2022, while raw opportunity density is disclosed;
5. treatment's primary-stratified action-close distance is no more than 0.25
   ATR farther above the reference low than control in DEV or VAL;
6. leave-one-sector-out MAE and tail effects remain positive in both eras and no
   single sector supplies more than 25% of treatments; and
7. neither MAE nor tail reverses sign in descriptive FWD.

If any requirement fails, the exact SR2 construction is killed and added to
`research/DO_NOT_REBUILD.md`. Threshold retiming, including changing the
three-session persistence or 0.50 ratio, is not a new species.

If every requirement passes, the only permitted next step is a deterministic,
display-only prospective ledger:

- no entry/rank/size/gate/alert authority;
- nightly as sole advancer;
- frozen membership snapshot and construction hash;
- no historical backfill;
- 63-session maturity before grading; and
- a separate future promotion ruling.

## 10. Planned outputs

- `scripts/research/pss_sr2_peer_diffusion.py`
- `tests/test_pss_sr2_peer_diffusion.py`
- `reports/pss_sr2_peer_diffusion.md`
- `data/research/pss_sr2_peer_diffusion_events.parquet`
- `data/research/pss_sr2_peer_diffusion_panel.parquet`
- `data/research/pss_sr2_peer_diffusion_census.parquet`

The study stays off render and nightly paths. Unchanged inputs and seeds must
produce byte-equivalent logical content.

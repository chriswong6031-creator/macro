# PSS-RH1 prospective charter — synchronized relief-rally hazard

Status: **FROZEN BEFORE THE FIRST ELIGIBLE ACTION** (2026-07-27).

Canonical identifier: **PSS-RH1**
(`pss_rh1_relief_hazard_prospective`).

This charter specifies how to use the strongest useful information produced by
the failed PSS-SR3 trial without pretending that an outcome-selected sign flip
is already validated.

## 0. The result being utilized

PSS-SR3 asked whether synchronized active sector participation improved the
terminality of a held subject recovery. It did not. Relative to a nested control
with the same subject recovery and passive peer distance, the active-majority
label worsened:

- DEV MAE by 1.39 percentage points and rebound-first by 10.76 points;
- VAL MAE by 1.28 points and rebound-first by 13.20 points; and
- FWD MAE by 2.17 points and tail incidence by 7.42 points.

The result survived a close-distance audit, exact calendar/sector/severity/delay
controls, and independent era signs. That makes it a serious mechanism clue:
after systemic stress, broad five-session sector participation may identify a
correlation-one relief rally near a local crest, not durable absorption.

It does **not** make the inverse use valid on the same inspected history. The
historical SR3 paths selected this hypothesis and therefore supply zero RH1
confirmations.

## 1. First-principles claim

The adverse mechanism is plausible for three linked reasons.

First order: a common stress event compresses sector correlations. Once the
subject and most peers rebound together, their recent positive returns can
measure beta re-risking rather than information about remaining supply.

Second order: synchronized buying rapidly removes the most obvious tactical
upside. Mean-reversion sellers, trapped holders, and systematic de-grossing can
then meet a crowded cohort whose entries have nearly the same timestamp.

Third order: when the rally stalls, common ownership and common factor exposure
turn apparent diversification into one exit. The same breadth that looked like
confirmation can amplify the next drawdown and reduce the chance that +8% is
reached before the frozen stress low is breached.

The primary control is essential. It already requires the subject to hold a
recovery and a majority of peers to sit at least +0.50 frozen ATR above their
own formation lows. RH1 isolates only the incremental effect of persistent,
current five-session participation.

## 2. Exact frozen construction

RH1 reuses the exact PSS-SR3 construction. This is intentional: changing a
lookback, persistence rule, threshold, action geometry, or control after seeing
SR3 would create a new unregistered hypothesis.

The machine-readable source of truth is
`data/personality_timing/relief_hazard_manifest_v1.json`. Its canonical
construction hash is frozen by the registration utility and runtime.

### 2.1 Anchor and formation

- Subject close is at or below its prior 60-session close low.
- Ex-self same-sector new-low breadth is at least 15% and at or above its
  shifted trailing-126-session 80th percentile (63 observations minimum).
- At least 15 valid peers are required.
- Greedy anchor cooldown is 21 sessions.
- Formation is anchor through anchor +3.
- Subject and peer ATR14 values use information only through anchor -1.
- Every name's reference low is its own minimum intraday low during formation.

### 2.2 Observable subject action

Search no more than 30 sessions after formation. The first action close must:

- complete a three-session run with every close at least +0.50 frozen ATR above
  the subject reference low;
- complete the same run with no intraday low below -0.50 ATR; and
- finish between +1.00 and +1.75 ATR above the reference low, inclusive.

The action is stamped only at that completed close. It is never backdated.

### 2.3 Peer labels

On each of the three action-window sessions, for every valid ex-self peer:

- `level_recovered` means close at least +0.50 own frozen ATR above own
  formation low; and
- `actively_recovered` additionally means close strictly above its close five
  sessions earlier.

Take the minimum equal-weight breadth over those three completed sessions.

- **relief_hazard:** `level_min >= 0.50` and `active_min >= 0.50`;
- **level_control:** `level_min >= 0.50` and `active_min < 0.50`; and
- **weak_level_diagnostic:** `level_min < 0.50`, excluded from primary
  inference.

## 3. Prospective firewall

The frozen membership contains 799 eligible names across the eleven standard
GICS sectors. It is a snapshot, not a dynamically changing survivor universe.

The latest available session at registration is **2026-07-24**. An RH1 event is
eligible only when its action date is **strictly later than 2026-07-24**.
Anchors may begin earlier because their values were already observable, but a
historical action can never be imported.

The production ledger launches with zero event rows. Nightly is the sole
advancer. Non-nightly runs may report audit state but cannot enroll or grade.
Rows are keep-first and immutable except for the one transition from ungraded
to a 63-session grade.

No historical PSS-SR3 event, report row, outcome, parameter comparison, or
retimed label may enter the RH1 ledger.

## 4. Outcome ruler

All outcomes start after the action close and mature only when 63 later trading
sessions exist:

- MAE63: worst close return over action +1 through action +63;
- tail10: MAE63 at or below -10%;
- proximity: action close's percentage distance above the minimum close in
  action -31 through action +31;
- W5: proximity no greater than 5%;
- called: local trough offset from -2 through +5 sessions;
- tdt: signed trading-session offset to that local trough; and
- competing risk: +8% close rebound before intraday breach below the frozen
  reference low -0.50 ATR. Same-session ties go to breach and unresolved paths
  remain failures.

## 5. One-read decision law

No interim outcome analysis is permitted. The first and only formal read occurs
when all of these are true:

- at least 500 matured primary rows;
- at least 250 unique names;
- at least 100 relief-hazard and 100 level-control rows;
- at least 12 distinct action months spanning at least 365 calendar days; and
- at least 30 exact informative strata with two rows per label.

Primary inference keeps the first primary action per name-month and matches
sector × action month × frozen anchor-severity band × frozen delay band.
Stratum effects receive equal weight. Labels permute only inside strata:
10,000 draws, seed 20260808, one-sided alpha 0.05. A three-calendar-month
moving-block bootstrap supplies 95% diagnostic intervals: 5,000 draws, seed
20260809.

Positive harm is defined before accrual:

- MAE: level-control MAE minus relief-hazard MAE;
- tail10: relief-hazard rate minus level-control rate;
- W5: level-control rate minus relief-hazard rate; and
- rebound-first: level-control rate minus relief-hazard rate.

Qualification requires every condition below:

1. MAE harm is positive, has permutation p <= 0.05, and its block-CI lower
   bound is above zero.
2. Tail10 harm is positive, has permutation p <= 0.05, and its block-CI lower
   bound is above zero.
3. W5 and rebound-first harm are both positive.
4. MAE and tail harm remain positive independently in chronological early and
   late halves.
5. Leave-one-sector-out MAE and tail harm remain positive.
6. No sector supplies more than 25% of hazard rows.
7. Absolute stratified action-close-distance difference is at most 0.25 ATR.

Failure of any condition kills RH1 at its sole read. The sample clock,
thresholds, groups, ruler, or control cannot be retimed afterward.

## 6. Authority and possible eventual use

RH1 is an operator-research accrual lane only:

- no entry authority;
- no ranking or sizing authority;
- no gate authority;
- no alert authority;
- no user-facing display authority; and
- no automatic promotion.

Even a full qualification would authorize only a separate preregistered review
of a de-escalation shadow. That later review would have to specify how an
otherwise-valid reset confirmation is softened or deferred during an RH1
hazard state and prove that the operational intervention improves decisions.

This two-step boundary matters. RH1 first proves that the state is a hazard.
Only a separate untouched test may prove that acting on that knowledge helps.

## 7. Trial accounting and immutable inputs

The prospective family spends exactly one configuration. There is no grid.
PSS-SR3 and the earlier PSS sequence are disclosed as hypothesis-generating
prior information, not counted as prospective evidence.

The membership file binds:

- the frozen eligible W1 panel hash;
- the frozen ticker-sector map hash;
- every admitted symbol and sector;
- the registration cutoff; and
- the source commit.

The manifest binds the construction, grade ruler, decision law, authority
fences, ledger path, state path, and membership-file hash. Runtime must fail
inert if those hashes drift.

## 8. Copy law

Until the sole prospective read passes and a separate intervention study is
approved, the only lawful description is:

> “Prospective research is measuring whether synchronized relief participation
> marks elevated post-recovery drawdown risk.”

It may not be described as a validated sell signal, failed-rally detector,
avoid gate, bull trap, top call, or proven de-escalation rule.

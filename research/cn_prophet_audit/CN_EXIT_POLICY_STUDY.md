# CN exit-policy horse race — early-review families vs the H=10 incumbent

Frozen 2026-08-04 · era `cn_standout_v1` (`board_definition='legacy'`), 12 graded entry dates 2026-06-30 → 2026-07-17 · instrument `research/cn_prophet_audit/cn_exit_policy_study.py` · raw `cn_exit_policy_results.json`

## DECISION-RELEVANT SUMMARY

1. **No challenger beats the incumbent on the CN desk's own headline stats.** 0/11 beat its 68.6% win rate and 0/11 beat its 4.44% median excess — every single rule tested lowers both. What some of them buy instead is MEAN excess, profit factor (11/11 beat 1.82) and a thinner left tail.
2. **The day-3 review family — the rule this study was commissioned to test — does not pay.** Its best member `R3x5` (day-3 review, exit if mark <= -5%) moves mean excess +0.20 pp [-0.18, 0.57] — indistinguishable from zero — while cutting win rate -3.5 pp and median excess -0.27 pp.
3. **Why: the day-3 tell is not sharper than the day-1 tell.** P(eventual loser | mark ≤ −3%) is 0.71 at bar 1, 0.68 at bar 3, and only reaches 0.92 by bar 10. At bar 3 roughly one flagged name in three still ends a winner (103 flagged, 32% of them winners) — and every one of those is a winner the rule forfeits.
4. **What does separate from zero: the plain hard stop.** On CSI300 excess, `S8`, `S10` have a date-blocked CI excluding 0; on absolute P&L so do `R3x5`, `S8`, `S10`. Best uncensored challenger `S10` (hard stop -10% (first close through)): +0.64 pp mean excess [0.165, 1.145]. `S8` clears zero by 0.004 pp — a hair, and the overlap caveat below is larger than that margin.
5. **On the operator's cut-losers-not-winners criterion the STOP family wins and the REVIEW family loses.** `S10` improves 54 of the audit's 128 losers for 6 of its 279 winners degraded (9.00:1); `R3x5` manages 36 for 14 (2.57:1).
6. **Not one CUT rule improved a single incumbent WINNER** (0 of 279, all nine review/stop rules; the extension family is the only one that ever helps a winner). A winner that was under water at the review or stop bar is by construction a recovery, and exiting into the hole always realized less than holding did. The winner column is pure cost — there is no upside leg to trade off against it.
7. **Tail damage is the one place the stops clearly earn.** Incumbent MAE-p10 -16.88%; `S6` cuts it to -8.70% (+8.18 pp). If the objective is surviving the fat left tail rather than maximising the median, that is the trade on offer.
8. **A-share execution eats part of it, and part of it is unexecutable.** Pooling the 4 stop-carrying rules (406 resting-stop exits in total, the same episode counted once per rule, 19 of them no-ops on bar 10), a stop filled a weighted mean -2.39 pp BELOW its own trigger level (worst single fill -11.51 pp), and 43 of those exits fired on a session already at the daily price limit — where a seller could not reliably transact at any price. Read every stop delta above as an UPPER bound on what the rule would have realized.
9. **The winners-run half is CENSORED, not measured.** Only 150/407 episodes have 21 forward bars in the committed caches, so 103 of `EXT`'s 141 extended rows are MARKED at 2026-08-03, not realized. `EXT` and `R3x3_EXT` are position reports, never returns, and they are excluded from the "best challenger" line above for exactly that reason.
10. **Epistemic status: hypothesis generator, nothing more.** In-sample, ONE era of 12 entry dates on a FALLING tape (CSI300's forward window negative on 10/12), 11 rules in 5 families with NO multiplicity correction, and only 2 pairwise-disjoint windows behind 12 nominal blocks — so every CI here is too narrow. It can motivate a pre-registration; it cannot change the track record, the board, or any weight, and no rule shipped from this file.

## What this is / what it is not

Two different jobs, two instruments, never one blended number (`research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` §1):

1. **The track record measures SIGNAL QUALITY** — comparable, forced-verdict, fixed-H episodes, policy-free so eras and desks compare. The incumbent's 68.6% is a statement about the BOARD, not about a trading plan, and it stays the public headline.
2. **This study measures TRADE MANAGEMENT** — on IDENTICAL entries, what a holder-with-rules captures. "Cut losers short / let winners run" is tested here and only here.
3. **Longer-term pick quality enters selection only through evidence** — the horizon ladder plus postmortem cohorts feed candidate features into the promotion pipeline, never directly into live weights.

Conflating the two would be the single most misleading number this program could print: an exit policy's win rate is not the board's win rate, and improving the former says nothing about the latter. Every verdict below is DESCRIPTIVE — "shows", "in this sample". No promotion, no recommendation, no weight change.

## P0 gate — the cohort reproduces the shipped prior record

Asserted BEFORE any policy number is computed; the study raises and writes nothing on drift.

| Gate | Reproduced | Shipped |
|---|---|---|
| matured episodes | 407 | 407 |
| win rate (excess > 0) | 0.6855 | 0.6855 |
| losers | 128 | 128 |
| median excess | 4.44% | 4.44% |

Frame: 1082 `legacy` board rows over 18 board days → 584 contiguous-run episodes → 407 matured on 12 entry dates. Exclusions (all by data coverage, fill legality, or age — none can know which way a trade went): `immature` 176, `locked_limit_fill` 1.

## Method pins

- **Bar numbering.** `include_fill_bar=True`, so forward **bar 1 IS the fill bar's own close** (the fill is the T+1 open/(H+L)/2 proxy, so that session's close is a legitimate day-one exit). `held == 10` exits on bar 10. "Close of forward session k" means `prices[k-1]`.
- **The loser audit's `first3` is bar 4 here**, not bar 3 — it indexes position 3 of an 11-bar array whose position 0 is the fill bar. The review families are run at the bar they name, and the conditional-loser table below is printed for EVERY bar so the choice of review bar is grounded rather than inherited.
- **Triggers are ABSOLUTE marks from fill; outcomes are scored in CSI300 EXCESS.** A rule must be executable without knowing the index; the CN headline metric is relative because in A-shares beta dominates. A rule can therefore cut an absolute loss that was not an excess loss, and the excess column prices that.
- **Exits are CLOSE-ONLY.** A rule reads the close of session k and exits AT that close. No walker touches an intraday low. Conservative in one direction (never fires on a session that pierced and recovered), optimistic in another (assumes the close is transactable — see the A-share section).
- **Same-bar ordering.** The hard stop is tested before the scheduled review. On the one bar where both can fire the review level is the looser of the two, so both resolve at the same close; the pin makes the exit REASON deterministic.
- **Every trigger is INCLUSIVE** — a review fires on `mark <= −X`, a stop on `mark <= −Y`, the extension arms on `mark >= +5`. These are levels a desk would publish, and trading at a published level is trading through the thesis, so a touch counts. A WIN stays the ledger's strict `> 0` with no dead band, so a "loser" is `excess <= 0` — the same cut that produces the audit's 128.
- **MAE/MFE are measured over the policy's OWN held window** (`prices[:held]`), for every row including the incumbent's. The incumbent never exits early, so its window is the full 10 bars and its MAE equals the grader's.
- **MAE/MFE are CLOSE-PATH** (the caches carry no intraday path for the walk), so both UNDERSTATE the true excursion.

## Headline — every policy on the same 407 episodes, scored in CSI300 excess

| Policy | win% | median | mean | PF | avg win | avg loss | MAE p10 | med hold | mean hold | abs win% | abs median | censored |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `P0` incumbent — fixed H=10 forced verdict | 68.6 | 4.44 | 2.68 | 1.82 | 8.65 | -10.34 | -16.88 | 10 | 10.0 | 61.7 | 2.60 | 0 |
| `R3x2` day-3 review, exit if mark <= -2% | 59.5 | 3.19 | 2.69 | 2.06 | 8.79 | -6.26 | -10.95 | 10 | 7.8 | 54.5 | 1.18 | 0 |
| `R3x3` day-3 review, exit if mark <= -3% | 61.4 | 3.57 | 2.73 | 2.02 | 8.81 | -6.95 | -11.73 | 10 | 8.2 | 57.2 | 1.67 | 0 |
| `R3x5` day-3 review, exit if mark <= -5% | 65.1 | 4.17 | 2.88 | 2.02 | 8.74 | -8.07 | -12.64 | 10 | 8.8 | 60.0 | 2.08 | 0 |
| `R5x3` day-5 review, exit if mark <= -3% | 62.2 | 3.53 | 2.75 | 1.99 | 8.89 | -7.34 | -12.44 | 10 | 8.4 | 56.0 | 1.51 | 0 |
| `R5x5` day-5 review, exit if mark <= -5% | 66.3 | 4.24 | 3.13 | 2.17 | 8.74 | -7.93 | -12.60 | 10 | 8.9 | 60.2 | 2.14 | 0 |
| `S6` hard stop -6% (first close through) | 61.9 | 3.71 | 3.09 | 2.32 | 8.78 | -6.15 | -8.70 | 10 | 8.0 | 57.0 | 1.68 | 0 |
| `S8` hard stop -8% (first close through) | 65.6 | 4.17 | 3.22 | 2.30 | 8.71 | -7.24 | -10.58 | 10 | 8.5 | 59.7 | 2.07 | 0 |
| `S10` hard stop -10% (first close through) | 67.1 | 4.35 | 3.32 | 2.31 | 8.73 | -7.71 | -12.02 | 10 | 8.9 | 60.9 | 2.42 | 0 |
| `R3x3_S8` day-3 review -3% PLUS hard stop -8% | 61.2 | 3.54 | 2.95 | 2.21 | 8.82 | -6.30 | -9.68 | 10 | 7.9 | 57.0 | 1.65 | 0 |
| `EXT` extend to bar 21 if bar-10 mark >= +5% | 66.6 | 3.99 | 3.41 | 2.02 | 10.14 | -9.99 | -17.30 | 10 | 12.2 | 59.0 | 1.88 | **103** |
| `R3x3_EXT` day-3 review -3% PLUS extend to bar 21 if bar-10 mark >= +5% | 60.0 | 3.22 | 3.52 | 2.29 | 10.43 | -6.82 | -12.05 | 10 | 10.3 | 55.0 | 1.13 | **97** |

All percentage columns are points. `win%`/`median`/`mean`/`PF`/`avg win`/`avg loss` are CSI300 excess; `abs win%`/`abs median` are absolute P&L. `MAE p10` is the 10th percentile of maximum adverse excursion over the policy's held window (more negative = fatter left tail). `censored` counts rows MARKED at the last available close rather than exited — any non-zero entry means that row is a position report, not a return.

MEDIAN hold is 10 for every policy because no rule fires on more than half the cohort; the MEAN hold column is where the rules are visible. Read the median-hold column as "the typical episode is untouched", not as "the rule does nothing".

## Delta vs the incumbent

| Policy | Δ win% | Δ median | Δ PF | Δ avg loss | Δ MAE p10 | Δ mean hold | Δ mean excess, paired (95% blocked CI) |
|---|---|---|---|---|---|---|---|
| `R3x2` | -9.1 | -1.25 | +0.24 | +4.08 | +5.93 | -2.2 | +0.01 pp [-0.883, 0.809] |
| `R3x3` | -7.2 | -0.87 | +0.20 | +3.39 | +5.15 | -1.8 | +0.06 pp [-0.579, 0.676] |
| `R3x5` | -3.5 | -0.27 | +0.20 | +2.27 | +4.24 | -1.2 | +0.20 pp [-0.178, 0.572] |
| `R5x3` | -6.4 | -0.91 | +0.17 | +3.00 | +4.44 | -1.6 | +0.07 pp [-0.697, 0.937] |
| `R5x5` | -2.3 | -0.20 | +0.35 | +2.41 | +4.28 | -1.1 | +0.45 pp [-0.127, 1.167] |
| `S6` | -6.7 | -0.73 | +0.50 | +4.19 | +8.18 | -2.0 | +0.42 pp [-0.408, 1.134] |
| `S8` | -3.0 | -0.27 | +0.48 | +3.10 | +6.30 | -1.5 | +0.55 pp [0.004, 1.098]  **excludes 0** |
| `S10` | -1.5 | -0.09 | +0.49 | +2.63 | +4.86 | -1.1 | +0.64 pp [0.165, 1.145]  **excludes 0** |
| `R3x3_S8` | -7.4 | -0.90 | +0.39 | +4.04 | +7.20 | -2.1 | +0.28 pp [-0.502, 1.027] |
| `EXT` | -2.0 | -0.45 | +0.20 | +0.35 | -0.42 | +2.2 | +0.73 pp [-0.153, 1.663] |
| `R3x3_EXT` | -8.6 | -1.22 | +0.47 | +3.52 | +4.83 | +0.3 | +0.85 pp [-0.275, 1.847] |

The last column IS the mean-excess delta — mean of per-episode differences equals difference of means, and all 407 episodes carry an excess under every policy, so there is one number and it is printed once, unrounded until display. (A separate "Δ mean" column computed from the two 2-dp headline means would differ from it in the third decimal purely by double rounding; that column is deliberately not shown, and the identity is asserted in code.)

Paired = the SAME entry on the SAME date in both legs, so the difference isolates the exit rule and removes the entry cohort's variance. The CI resamples whole board days. A bolded "excludes 0" is a WEAKER statement than it looks — see the overlap section.

## Cut the losers, don't cut the winners (the operator's criterion, priced)

Partitioned on how the INCUMBENT called each episode: 128 losers, 279 winners. "Improved" = the policy's excess is strictly higher than the incumbent's on that episode; "flipped" = it crossed the 0 line.

| Policy | losers improved | losers flipped to win | winners degraded | winners flipped to loss | improved / degraded | net on losers half | net on winners half |
|---|---|---|---|---|---|---|---|
| `R3x2` | 58/128 | 1 | 45/279 | 38 | 1.29 | +1.07 pp | -1.05 pp |
| `R3x3` | 47/128 | 0 | 33/279 | 29 | 1.42 | +0.88 pp | -0.82 pp |
| `R3x5` | 36/128 | 0 | 14/279 | 14 | 2.57 | +0.63 pp | -0.43 pp |
| `R5x3` | 63/128 | 5 | 32/279 | 31 | 1.97 | +0.82 pp | -0.75 pp |
| `R5x5` | 52/128 | 0 | 9/279 | 9 | 5.78 | +0.74 pp | -0.28 pp |
| `S6` | 71/128 | 0 | 27/279 | 27 | 2.63 | +1.31 pp | -0.90 pp |
| `S8` | 60/128 | 0 | 12/279 | 12 | 5.00 | +0.96 pp | -0.41 pp |
| `S10` | 54/128 | 0 | 6/279 | 6 | 9.00 | +0.86 pp | -0.22 pp |
| `R3x3_S8` | 61/128 | 0 | 34/279 | 30 | 1.79 | +1.14 pp | -0.87 pp |
| `EXT` | 0/128 | 0 | 39/279 | 8 | 0.00 | +0.00 pp | +0.73 pp |
| `R3x3_EXT` | 47/128 | 0 | 68/279 | 35 | 0.69 | +0.88 pp | -0.03 pp |

The two net columns sum to the paired mean delta by construction (asserted in code); each is `sum(delta over that half) / 407`, so they are contributions to the overall mean, not within-half averages. Signs are literal — a POSITIVE winners-half number means the policy helped winners on net (only the extension family does). A policy whose left column is large and whose right column is near zero is doing the job the operator asked for; a policy that buys its mean by hurting more winners than it saves losers is buying it in the wrong currency.

**The winners column has no upside leg.** Across all 9 CUT rules, exactly 0 of 279 incumbent winners was improved by exiting early — every winner a cut rule touched, it hurt. The mechanism is visible in the pairing: an episode that ends an EXCESS winner despite being under water at the review bar is by construction a recovery, i.e. it out-ran CSI300 from the review bar to bar 10, so selling into the hole realized less than holding. This is a MEASURED property of this cohort, not an identity — but it means the winner-forfeiture column is pure cost with nothing to net it against.

## When the tell actually appears (grounding the review bar)

P(this episode ends an incumbent LOSER | its mark at bar k is at or below the threshold), over all 407 matured episodes.

**Threshold: mark ≤ −2%**

| bar | n hit | % of cohort | P(loser) | median final excess | median final abs P&L |
|---|---|---|---|---|---|
| 1 | 97 | 23.8 | 0.649 | -3.71 | -6.04 |
| 2 | 126 | 31.0 | 0.587 | -2.73 | -4.40 |
| 3 | 127 | 31.2 | 0.646 | -5.61 | -7.62 |
| 4 | 148 | 36.4 | 0.649 | -3.65 | -6.66 |
| 5 | 148 | 36.4 | 0.689 | -4.78 | -7.48 |
| 6 | 143 | 35.1 | 0.699 | -5.26 | -7.72 |
| 7 | 139 | 34.2 | 0.727 | -5.81 | -8.46 |
| 8 | 134 | 32.9 | 0.784 | -6.98 | -9.11 |
| 9 | 130 | 31.9 | 0.854 | -8.63 | -10.62 |
| 10 | 127 | 31.2 | 0.906 | -8.85 | -10.94 |

**Threshold: mark ≤ −3%**

| bar | n hit | % of cohort | P(loser) | median final excess | median final abs P&L |
|---|---|---|---|---|---|
| 1 | 73 | 17.9 | 0.712 | -8.56 | -9.46 |
| 2 | 94 | 23.1 | 0.691 | -6.54 | -9.22 |
| 3 | 103 | 25.3 | 0.680 | -7.97 | -9.46 |
| 4 | 121 | 29.7 | 0.702 | -6.43 | -8.83 |
| 5 | 128 | 31.4 | 0.750 | -6.98 | -8.88 |
| 6 | 124 | 30.5 | 0.766 | -8.00 | -9.62 |
| 7 | 124 | 30.5 | 0.750 | -7.76 | -9.62 |
| 8 | 118 | 29.0 | 0.847 | -8.76 | -11.29 |
| 9 | 120 | 29.5 | 0.883 | -9.79 | -12.12 |
| 10 | 121 | 29.7 | 0.917 | -9.68 | -11.92 |

**Threshold: mark ≤ −5%**

| bar | n hit | % of cohort | P(loser) | median final excess | median final abs P&L |
|---|---|---|---|---|---|
| 1 | 43 | 10.6 | 0.837 | -12.97 | -15.80 |
| 2 | 59 | 14.5 | 0.797 | -12.15 | -13.16 |
| 3 | 70 | 17.2 | 0.800 | -10.34 | -12.69 |
| 4 | 83 | 20.4 | 0.807 | -11.84 | -13.61 |
| 5 | 88 | 21.6 | 0.898 | -12.37 | -14.61 |
| 6 | 99 | 24.3 | 0.879 | -11.41 | -12.75 |
| 7 | 95 | 23.3 | 0.884 | -12.15 | -14.59 |
| 8 | 95 | 23.3 | 0.926 | -12.34 | -14.59 |
| 9 | 97 | 23.8 | 0.969 | -12.39 | -14.63 |
| 10 | 96 | 23.6 | 1.000 | -12.42 | -14.65 |

Base rate for reference: 128/407 = 31.4% of episodes end losers.

**This is why the review families fail, and it is the study's most transferable finding.** The loser audit's early-mark tell is REAL — a name marked at ≤ −3% is a 0.68 loser against a 0.31 base rate — but it does not SHARPEN at bar 3. It is already there at bar 1 (0.71) and only becomes decisive around bars 8–10 (0.85, 0.88, 0.92) — by which point the forced verdict has already arrived and there is nothing left to cut. A conditional loser rate near 0.7 means ~30% of everything the rule fires on is a winner, and the winners column above shows that all of those are forfeited outright. A DEPTH threshold does better than a DATE threshold precisely because it waits for a bigger move rather than a later calendar bar — which is exactly what the hard-stop family is.

## A-share execution reality (the close-only convention, costed)

`exit_mark − trigger_level` is the same arithmetic for both trigger kinds and it does NOT mean the same thing, so it is reported SPLIT, never pooled:

- **resting stop** (`hard_stop`) — the level sits in the market on every bar. A real order fills near it intraday; this study fills at the close, which is by construction at or through it. **This gap is the execution cost of the close-only convention** and it is a LOWER bound (no queue model, and a real stop would additionally fire on sessions this study holds through).
- **scheduled review** (`review`) — the threshold is read ONCE, at a scheduled bar. Nothing was resting; the position is simply already deeper than the trigger when the calendar reaches the review. **That is a property of the cohort, not an execution cost** — reading it as slippage would roughly double the review families' apparent penalty.

| Policy | trigger kind | n | of which no-op on bar 10 | mean | median | p10 | worst | ≤ −2pp | bar at daily limit |
|---|---|---|---|---|---|---|---|---|---|
| `R3x2` | scheduled_review | 127 | 0 | -4.84 | -3.24 | -10.93 | -20.34 | 82 | 2 |
| `R3x3` | scheduled_review | 103 | 0 | -4.85 | -3.67 | -11.92 | -19.34 | 70 | 2 |
| `R3x5` | scheduled_review | 70 | 0 | -4.75 | -3.70 | -11.51 | -17.34 | 46 | 2 |
| `R5x3` | scheduled_review | 128 | 0 | -5.95 | -5.18 | -12.40 | -23.83 | 88 | 3 |
| `R5x5` | scheduled_review | 88 | 0 | -6.34 | -5.27 | -13.23 | -21.83 | 74 | 3 |
| `S6` | resting_stop | 134 | 2 | -2.17 | -1.65 | -4.85 | -11.51 | 56 | 14 |
| `S8` | resting_stop | 108 | 6 | -2.53 | -1.91 | -5.15 | -9.51 | 51 | 10 |
| `S10` | resting_stop | 89 | 6 | -2.31 | -1.96 | -5.21 | -7.71 | 43 | 11 |
| `R3x3_S8` | resting_stop | 75 | 5 | -2.67 | -1.91 | -6.06 | -9.51 | 36 | 8 |
| `R3x3_S8` | scheduled_review | 60 | 0 | -1.92 | -1.58 | -3.90 | -4.83 | 28 | 0 |
| `R3x3_EXT` | scheduled_review | 103 | 0 | -4.85 | -3.67 | -11.92 | -19.34 | 70 | 2 |

All figures in points of entry; negative = past the trigger. A trigger bar "at the daily limit" is a session whose own move was at or through the board's price limit (±10% main board, ±20% STAR/ChiNext) — a seller could not reliably transact there at any price, so those exits are priced at a level nobody could have hit.

**Not every trigger is a trade.** A resting stop is in the market on EVERY bar including bar 10, and a trigger there exits at the SAME close the forced verdict would have — the rule fired, the position is identical to the incumbent's, and the paired delta is exactly 0. The `no-op on bar 10` column separates those out, so a stop's trigger count is never read as its trade count (e.g. `S10` fires 89 times but only 83 of those changed anything). Scheduled reviews sit at bars 3 and 5 and cannot be no-ops.

Separately, exactly 1 exit in the cohort lands on a LOCKED bar (`high == low == close` — the session never traded away from its limit), and it does so under EVERY policy including the incumbent, because it is a plain horizon exit. That is a property of the tape, not of any rule.

## Censoring (the extension family only)

The review and stop families resolve inside the 10-bar forced-verdict window, so they are uncensored by construction. The extension family holds to bar 21, and only 150/407 episodes have 21 forward bars in the committed caches (last session 2026-08-03; forward-bar availability 11…24, median 18).

| Policy | extended rows | of which MARKED at data end | censored % of cohort |
|---|---|---|---|
| `EXT` | 141 | 103 | 25.3 |
| `R3x3_EXT` | 130 | 97 | 23.8 |

Censored rows are NOT dropped — dropping them would delete exactly the positions still running, which is the outcome-conditioned denominator `track_scoring`'s rule 1 forbids. They are marked at the last available close and flagged. A data_end row is a MARK, not a realized exit, and its hold length is a LOWER BOUND. Read those rows as "what the rule was holding on 2026-08-03", never as "what the rule returned".

## Regime — the tape this was measured on

CSI300's own 10-session forward window from each graded entry date: negative on **10 of 12** dates, median -2.87% (range -5.89% … 1.39%).

| board date | CSI300 fwd-10 |
|---|---|
| 2026-06-30 | -3.20% |
| 2026-07-01 | -2.00% |
| 2026-07-02 | -5.89% |
| 2026-07-03 | -4.65% |
| 2026-07-07 | -0.69% |
| 2026-07-08 | -2.62% |
| 2026-07-10 | 0.19% |
| 2026-07-13 | -4.34% |
| 2026-07-14 | -3.74% |
| 2026-07-15 | -3.11% |
| 2026-07-16 | 1.39% |
| 2026-07-17 | -1.10% |

An exit rule that cuts losses is FLATTERED by a falling tape almost by construction. This is the single largest reason to treat the deltas above as in-sample only.

Convention note: this column is the loser audit's own `csi300_fwd10` (`bench[T+1 … T+11]`), kept byte-comparable so the two documents cross-reference. It spans ONE session more than the benchmark leg inside `excess`, which runs fill bar → exit bar (bars 1…10). Do not reconcile the two arithmetically.

## Limitations (read before citing any number above)

1. **In-sample, one era, one regime.** 12 graded entry dates, 10/12 with a negative index window. No out-of-sample period exists for this closed book — the era ENDED when the board definition changed on 2026-07-30.
2. **No multiplicity correction.** 11 challengers across combined (1), day3_review (3), day5_review (2), extension (2), hard_stop (3). Thresholds were chosen from the loser audit's own descriptive statistics on THIS cohort, so the search is not independent of the sample either.
3. **The blocks overlap and the CI does not know it.** 12 board days, neighbour-window overlap median 90.0% (max 90.0%), 11 of 11 neighbour pairs sharing ≥50% of their window, 23 distinct sessions covering 120 window bars, and only **2 pairwise-disjoint windows** in the whole sample. Every interval printed is too narrow and a bolded "excludes 0" is a weaker statement than it looks. No correction is applied — it would need a covariance model this sample cannot support.
4. **Close-only exits + A-share price limits.** The resting-stop overshoot is a LOWER bound on the convention's cost (no queue model), a real stop would also fire intraday on sessions this study holds through, and limit-day exits are priced at a level nobody could have transacted. The scheduled-review overshoot is NOT an execution cost and must not be added to it.
5. **The extension family is censored** — see above. Its rows are position reports, not returns.
6. **Absolute triggers, relative scoring.** The rules fire on absolute marks and are scored in CSI300 excess. In a falling tape an absolute stop cuts positions that were beating the index; that cost is IN the excess columns, but it means the same rule would behave differently under a flat or rising index.
7. **No promotion path is opened by this file.** Any rule that eventually displaces the incumbent needs its own pre-registration, shadow accrual, and out-of-sample window first. The track record's headline stays the fixed-horizon forced verdict.

Instrument: `research/cn_prophet_audit/cn_exit_policy_study.py` · raw results `research/cn_prophet_audit/cn_exit_policy_results.json` · cohort forensics `research/cn_prophet_audit/RESULTS_2026-08-04.md` · doctrine `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` §1 · US sibling `scripts/exit_policy_study.py`.

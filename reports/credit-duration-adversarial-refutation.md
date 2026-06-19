# Adversarial refutation — Credit Carry & Duration Timing (claimed "confirmer")

Re-ran `scripts/credit_duration_verify_phase0.py` (numbers reproduce EXACTLY) plus
six targeted attacks. The validation agent's two specific gate failures are real
(Credit fails beat-baseline; Duration fails DSR), and NEITHER is scored — agreed.
The fight is **confirmer vs display**. Verdict: **DISPLAY for Credit Carry,
confirmer (barely) for Duration.**

## (1) LOOKAHEAD — CLEAN
Adding an extra +1d / +5d position lag does NOT improve results (Credit Sharpe
0.745→0.746→0.707; DD ~unchanged). A look-ahead leak would make extra lag hurt
sharply. Legs are `.shift(lag)`'d in the engine, `glide_path` is causal,
`backtest_core` shifts pos by 1. No leak. Not the kill.

## (2) SURVIVORSHIP — N/A
Single liquid ETF each (HYG/TLT), no cross-sectional universe. Not applicable.

## (3) MULTIPLE-TESTING — DSR n_trials is NOT honest; gate is moot anyway
DSR collapses fast with trial count:
| n_trials | Credit DSR | Duration DSR |
|---|--:|--:|
| 4 | 0.986 | 0.914 |
| 8 (used) | **0.963** | **0.831** |
| 12 | 0.942 | 0.774 |
| 27 (full suite) | 0.887 | 0.651 |

n_trials=8 counts only the 4 glide variants ×2 — it ignores the chosen leg SETS,
leg WEIGHTS (1.0/0.5), and lag windows, AND the fact that this is 1 of a **27-strategy
suite** built by identical `glide_path(score)` machinery (any of which is cherry-able).
At an honest family count Credit fails even the 0.90 bar and Duration is ~0.65.
Neither is scored regardless — but this kills any "DSR survives" comfort for Credit.

## (4) REDUNDANCY vs the DUMB baseline — KILLS Credit Carry
Credit Carry's entire confirmer thesis is "validated drawdown control." A dumb SMA
on HY does it BETTER and simpler:

| HY timer | Sharpe | MaxDD |
|---|--:|--:|
| **Credit macro strat** | **0.745** | **-14.7** |
| 125dma | 0.771 | -15.7 |
| 150dma | 0.871 | -9.1 |
| 200dma | 0.822 | -9.2 |
| 250dma | 0.842 | -11.2 |

The macro overlay loses to a plain moving average at every sensible window (125–250d)
on BOTH Sharpe AND drawdown. Bootstrap: strat-vs-200dma dd-reduction CI = [-10.2,
**-0.8**, 7.6] → strat is if anything DEEPER than the dumb baseline. The HY-OAS /
recession / VRP legs add NOTHING over a trend filter — they subtract. This is a
textbook redundancy kill: the candidate does not beat the right dumb baseline on its
OWN headline metric. → **DISPLAY, not confirmer.**

Duration is the opposite: 200dma is a disaster on TLT (Sharpe 0.124, MaxDD -40.3 —
long bonds whipsaw a trend filter). Duration's value+carry+trend blend genuinely
beats every dumb baseline here. Redundancy attack does NOT land on Duration.

## (5) HONEST-N — both are ~1-crisis stories; excess return is NEGATIVE
Both have NEGATIVE total log-excess vs B&H (Credit -0.198, Duration -0.199), and the
positive part is hyper-concentrated:
- **Credit:** GFC window = +0.102; **ex-GFC cumulative excess = -0.300** (deeply
  negative). The strat's full-sample -14.7 MaxDD literally IS its GFC drawdown.
- **Duration:** 2022-23 = +0.253 (127% of total); **ex-2022/23 excess = -0.452**.
  Drop 2022-23 and the headline drawdown edge collapses -30.2pp → -8.5pp (below the
  +10pp gate). Its own worst drawdown (-18.1) is 2008, unaffected by the timer.

The agent's "~5-6 independent crises" is generous: for the drawdown HEADLINE, Credit
≈ GFC-only, Duration ≈ 2022-only. Honest-N ≈ 1 dominant event each.

## (6) REGIME-DEPENDENCE — leans on one era (consistent with #5)
Duration ex-2022/23 Sharpe edge shrinks to +0.097; Credit ex-GFC actively loses to
B&H with no dd-edge the 200dma doesn't beat. Split-half "same-sign" holds but the
post-half magnitudes are tiny (Duration post S 0.30 / BH 0.11).

## Bottom line
- **Credit Carry → DISPLAY (downgrade from confirmer).** Dies on redundancy: a dumb
  150–250d SMA dominates it on Sharpe AND drawdown; the macro legs subtract value;
  ex-GFC excess is negative. No validated edge over the right dumb baseline → no
  confirmer.
- **Duration Timing → confirmer (held, barely).** Genuinely beats every dumb baseline
  (200dma is -40% DD on TLT), survives leave-one-crisis-out, dd-CI excludes 0. But
  it is a one-crisis (2022) drawdown story with negative ex-event excess and DSR ~0.83
  → confirmer is the ceiling, never scored.

Because the parent row bundles BOTH under one name and the headline ("validated
drawdown-context timers") is FALSE for the Credit half, the safest single tier for
the combined row is **display** with a note that the Duration half alone merits
confirmer.

# Turn-of-Month Equity Timing Overlay — Phase-0

READ-ONLY research. Holds the index ONLY on turn-of-month days (last N trading days of the month + first M of the next), else flat in T-bills. Tests whether the TOM seasonal is a real risk-adjusted edge or just less-time-in-market / data-mining / a pre-2000 artifact.


## _GSPC  (1927-12-30 → 2026-06-12, 98.5y, 24729 days)

| strat | CAGR% | Sharpe | MaxDD% | vol% | frac_in |
|---|---|---|---|---|---|
| **TOM (L1F3)** | 7.79 | 0.926 | -32.1 | 8.5 | 0.1912 |
| Buy&Hold | 6.33 | 0.42 | -86.2 | 18.9 | 1.0 |
| 200dma long/flat | 7.77 | 0.681 | -51.7 | 12.1 | 0.6736 |
| random-placebo (x1000, frac=0.1912) | 2.95 | 0.394 (p95 0.553, max 0.7) | -52.7 | — | 0.1912 |

**DSR** = 1.0  (SURVIVES multiple-testing (DSR≥0.95))  | sr_ann 0.93 vs sr0_ann 0.15 | n_trials 8 | T 24729 | skew 1.832 kurt 111.729
**Split-half**: first Sh 0.944 (BH 0.274), second Sh 0.913 (BH 0.591) | same_sign=True | both_beat_BH=True
**Leave-one-crisis-out** (TOM Sharpe must stay > BH): all_pass=True
  - drop 1929: TOM 0.69 vs BH 0.451 → PASS (dropped 1002d)
  - drop 1973: TOM 0.799 vs BH 0.423 → PASS (dropped 505d)
  - drop 2000: TOM 0.826 vs BH 0.429 → PASS (dropped 752d)
  - drop 2008: TOM 0.933 vs BH 0.435 → PASS (dropped 756d)
  - drop 2020: TOM 0.924 vs BH 0.426 → PASS (dropped 253d)
  - drop 2022: TOM 0.888 vs BH 0.423 → PASS (dropped 251d)
**Window grid** (DSR trials): L1F2 Sh=1.024 | L1F3 Sh=0.926 | L2F3 Sh=0.948 | L1F4 Sh=0.8 | L1F1 Sh=1.022 | L2F4 Sh=0.835 | L0F3 Sh=0.872 | L1F5 Sh=0.731
**Beats**: BH-Sharpe=True  200dma-Sharpe=True

## SPY  (1993-01-29 → 2026-06-17, 33.4y, 8403 days)

| strat | CAGR% | Sharpe | MaxDD% | vol% | frac_in |
|---|---|---|---|---|---|
| **TOM (L1F3)** | 6.17 | 0.769 | -27.8 | 8.2 | 0.1909 |
| Buy&Hold | 10.8 | 0.646 | -55.2 | 18.6 | 1.0 |
| 200dma long/flat | 8.94 | 0.776 | -22.8 | 12.0 | 0.7532 |
| random-placebo (x1000, frac=0.1909) | 3.22 | 0.431 (p95 0.676, max 0.911) | -30.8 | — | 0.1909 |

**DSR** = 0.9977  (SURVIVES multiple-testing (DSR≥0.95))  | sr_ann 0.77 vs sr0_ann 0.26 | n_trials 8 | T 8403 | skew -1.006 kurt 41.282
**Split-half**: first Sh 0.831 (BH 0.447), second Sh 0.703 (BH 0.881) | same_sign=True | both_beat_BH=False
**Leave-one-crisis-out** (TOM Sharpe must stay > BH): all_pass=False
  - drop 1929: TOM 0.769 vs BH 0.646 → PASS (dropped 0d)
  - drop 1973: TOM 0.769 vs BH 0.646 → PASS (dropped 0d)
  - drop 2000: TOM 0.537 vs BH 0.691 → FAIL (dropped 752d)
  - drop 2008: TOM 0.829 vs BH 0.74 → PASS (dropped 756d)
  - drop 2020: TOM 0.755 vs BH 0.673 → PASS (dropped 253d)
  - drop 2022: TOM 0.675 vs BH 0.661 → PASS (dropped 251d)
**Window grid** (DSR trials): L1F2 Sh=0.866 | L1F3 Sh=0.769 | L2F3 Sh=0.629 | L1F4 Sh=0.752 | L1F1 Sh=0.93 | L2F4 Sh=0.628 | L0F3 Sh=0.556 | L1F5 Sh=0.65
**Beats**: BH-Sharpe=True  200dma-Sharpe=False

## Tougher null — BLOCK placebo (contiguous 4-day blocks, x1000)

| market | TOM Sharpe | block-placebo p50 | p95 | p99 | max | TOM > max? |
|---|---|---|---|---|---|---|
| _GSPC | 0.926 | 0.479 | 0.63 | 0.704 | 0.781 | True |
| SPY | 0.769 | 0.51 | 0.779 | 0.872 | 1.016 | False |

The block placebo matches TOM's clustered 4-day exposure, a tougher null than iid days. _GSPC TOM still beats the placebo max; SPY does NOT — on the tradeable era the TOM-specific edge is inside the noise.


## OOS decay — same rule, post-publication eras

| market | era | TOM Sharpe | BH Sharpe | TOM CAGR | BH CAGR | TOM MaxDD | TOM>BH Sharpe? |
|---|---|---|---|---|---|---|---|
| _GSPC | >=2000 | 0.485 | 0.417 | 3.88 | 6.36 | -28.9 | True |
| _GSPC | >=2010 | 0.592 | 0.751 | 4.42 | 12.12 | -15.0 | False |
| SPY | >=2000 | 0.551 | 0.507 | 4.45 | 8.23 | -27.8 | True |
| SPY | >=2010 | 0.648 | 0.857 | 4.85 | 14.09 | -14.7 | False |

This is the decisive read: the full-sample DSR=1.0 is carried by the deep PRE-2000 history. Post-2000 the Sharpe edge is razor-thin (and CAGR is materially WORSE than B&H); post-2010 SPY TOM LOSES on Sharpe. The surviving effect is drawdown/vol reduction from being flat ~81% of the time, NOT a forward return edge — a confirmer/display profile, not a scored timing leg.


## Honest-N ( _GSPC )

TOM events (independent month-boundary clusters) = 1183 | months = 1183 | decades = 11 | days = 24729

The ~1100 month-boundary events are NOT 1100 independent bets: the anomaly is one repeated calendar effect, and the cross-decade picture (below, in split-half / LOCO) is the honest independence count.

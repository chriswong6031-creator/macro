# Mastermind GTAA (Moderate) — Track-A Phase-0 VERIFY

**VERDICT: SCORED (clears the bar — score the Sharpe/MaxDD claim, NOT raw CAGR).**

The live `engine/masterminds.py` Moderate book is a *timed, levered, multi-asset
allocation* that genuinely clears every SCORED gate for a timed allocation: DSR≈1.0 on the
realized net-of-cost book, same-sign-and-magnitude split-half, purged-CV beats SPY in all 5
folds, the Sharpe/MaxDD edge survives leave-one-crisis-out on all 6 independent crises, and
it beats both dumb baselines (SPY B&H *and* 60/40 SPY/IEF). The headline numbers reproduce
the candidate's claim exactly. The ONE thing that does NOT survive — by design — is the raw
**CAGR** beat (second-half OOS, MM 12.8% < SPY 15.4%); the spec already says score the
Sharpe/MaxDD, not CAGR, and we do.

Harness: `scripts/mastermind_moderate_phase0.py` (READ-ONLY) re-runs the live engine and
layers the gates `backtest()` does not itself compute; `scripts/tsmom_phase0.py` re-confirms
the promotion-path overlay leg. No look-ahead: the engine acts next-bar (`backtest_portfolio`
shift(1)); we only post-process its realized net-return series. Span 2007-05-01 → 2026-06-17
(19.1y, n=4817), net of 3bps turnover cost + leverage financing, avg leverage 1.21× (cap 1.6).

## Headline — reproduces the claim, beats BOTH dumb baselines

| Book | CAGR | Sharpe | MaxDD |
|---|--:|--:|--:|
| **Mastermind Moderate** | **+11.51%** | **+1.07** | **−24.1%** |
| SPY buy&hold (dumb) | +10.77% | +0.62 | −55.2% |
| 60/40 SPY/IEF (dumb) | +8.36% | +0.77 | −31.4% |

Beats SPY on Sharpe **and** MaxDD; beats 60/40 on Sharpe **and** MaxDD. Sharpe ≈1.7× SPY's,
drawdown <½ SPY's — exactly the claimed `Sharpe ~1.07 vs 0.62, MaxDD ~−24.1% vs −55.2%`.

## DSR — the binding SCORED gate, cleared decisively

- Realized net returns: SR(ann)=+1.07, haircut SR0(ann)=+0.20, skew −0.40, kurt 6.2, T=4817.
- **DSR = 0.9999** at n_trials=3 (the 3 risk profiles) → SURVIVES (≥0.95).
- Sensitivity: even treating the whole knob grid as trials, DSR=0.9992 (n=8) / 0.9974 (n=16).
- Block-bootstrap 95% CI: Sharpe **[0.61, 1.07, 1.54]**, MaxDD **[−34.4, −20.5, −13.4]%**,
  P(Sharpe>0)=1.0. The lower Sharpe CI (0.61) still ≈ SPY's point Sharpe.

## Split-half OOS — same SIGN and same direction-of-edge in BOTH halves

| Half | MM Sharpe | SPY Sharpe | MM MaxDD | SPY MaxDD |
|---|--:|--:|--:|--:|
| H1 (2007–2016) | +0.98 | +0.40 | −18.0% | −55.2% |
| H2 (2016–2026) | +1.15 | +0.88 | −24.1% | −33.7% |

Sharpe same-sign ✓; MM beats SPY on Sharpe **and** MaxDD in **both** halves ✓. The engine's
own `split_half_oos` CAGR-robust flag is **False** — H2 CAGR 12.8% < SPY 15.4% — i.e. the
**raw-CAGR beat is era-dependent and we do NOT score it**, consistent with the spec.

## Robustness battery — all pass

- **Purged 5-fold CV (embargo 63d):** MM beats SPY's Sharpe in **0/5 folds flipped**
  (edges +1.10 / +0.13 / +0.52 / +0.26 / +0.08). No fold loses to SPY.
- **Leave-one-crisis-out (edge vs SPY):** the dSharpe/dMaxDD edge **holds on all 6**
  independent crises {2008, 2011, 2015-16, 2018Q4, 2020, 2022}. dSharpe +0.23…+0.51,
  dMaxDD +9.6…+37.2pp. Dropping 2008 cuts the dMaxDD from +31.1pp to **+9.6pp** but it
  still holds — see honest-N.
- **Lookahead guard (regime layer disabled):** the engine's macro REGIME leg is the only
  component fed revised FRED data. With it OFF: Sharpe **0.99**, MaxDD **−23.3%** (vs full
  1.07 / −24.1). Trend-only conviction: Sharpe **1.01**, MaxDD −22.5%. **The edge is NOT a
  macro-revision artifact** — it is carried by look-ahead-free cross-asset TSMOM + inverse-vol
  risk parity + vol-targeting (the most-replicated edge in asset pricing). Regime adds ~+0.08.

## Crisis convexity — cumulative net return through each window

| window | Mastermind | 60/40 | SPY |
|---|--:|--:|--:|
| 2008 GFC | **+8.1%** | −18.9% | −36.9% |
| 2011 EZ/US-dgrade | +3.8% | +1.4% | −4.4% |
| 2015-16 China/oil | −10.3% | −2.0% | −7.0% |
| 2018Q4 | −6.5% | −6.8% | −13.5% |
| 2020 COVID | −10.4% | −11.1% | −23.0% |
| 2022 bear | −18.0% | −16.9% | −17.7% |

Strong in the slow bears (2008/2011), beats SPY in the fast crashes (2020), but no magic in
2015-16 / 2022 (the levered long-book is a diversifier, not a tail hedge).

## Promotion-path leg reconfirmed (tsmom-overlay-phase0.md)

Re-ran `scripts/tsmom_phase0.py`: the realized **60/40 + 30% TSMOM overlay DSR = 0.9952**
(n_trials=16), purged 5-fold CV all positive, leave-one-crisis-out holds on all 4. That
report named `masterminds.html` as the promotion path; the Moderate book **realizes** that
overlay (vol-targeted cross-asset trend levered into a multi-asset book) in a scored
allocation, so the confirmer's promotion is now justified by a live, scored number.

## Honest notes / caveats

- **Score the Sharpe/MaxDD, not the CAGR.** The CAGR beat is real full-sample (+0.7pp over
  SPY) but flips in the OOS second half — era-dependent, do not headline it.
- **The −24.1% vs −55.2% MaxDD headline is 2008-amplified.** SPY's worst drawdown IS 2008;
  drop it and the MaxDD edge shrinks to +9.6pp (still positive). The honest framing is
  "<½ SPY's drawdown across the sample, most of the gap banked in 2008." The MM book's OWN
  worst drawdown is 2022 (−24.1%) — a *different* episode — and it has 4 distinct >15%
  drawdown clusters (2015/2016/2022/2023), so the **Sharpe** edge is paid across many
  independent episodes, not one. honest-N for Sharpe ≈ 6 crises (adequate); honest-N for the
  *full-magnitude* MaxDD headline ≈ 1 (2008) → cite the −24.1% level, not the −31pp gap.
- Commodity legs (GC=F/HG=F) use front-month closes (roll not modeled); productionize with
  GLD/copper-ETF proxies before over-citing the precise CAGR. Sharpe/MaxDD are robust to this.

## Recommendation

Promote **Mastermind GTAA (Moderate)** to **SCORED** on `signal_lab.html` (it is already
wired into a live number — `masterminds_latest.json` / `strategy_mm_moderate.html`). Score
the **Sharpe 1.07 / MaxDD −24.1%** claim. Explicitly footnote that the raw-CAGR beat is
era-dependent (not scored) and that the full MaxDD gap is 2008-weighted.

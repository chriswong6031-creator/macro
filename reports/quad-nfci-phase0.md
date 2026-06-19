# Regime quad × NFCI-direction scenario odds — Phase-0 verdict

**VERDICT: CONFIRMER (scenario-odds panel).** The conditional-odds split is real,
reproduces the prior, and is split-half robust — but as a *tradeable* de-risk overlay it
fires on ~2 pre-2012 crises (zero post-2012), so its effective-N is too thin to score as a
high-confidence standalone. It is already half-wired as the engine's "NFCI tight-and-
tightening → −1" dial rule; this ships the explicit odds table as a confirmer.

Harness: `scripts/quad_nfci_phase0.py` (READ-ONLY). Quad from
`data/regime/regime_history.parquet`; NFCI direction reproduced from `conditions.py:762`
— `tightening = (nfci_chg>0) & (nfci>0)`, `nfci_chg = nfci − nfci.shift(65)`. SPY 63d
forward, 1993→2026. No look-ahead.

## Conditional odds by quad × NFCI direction (SPY 63d forward)

| Quad | NFCI | n | hit | mean fwd | p10 drawdown |
|---|---|--:|--:|--:|--:|
| Q1 | loosening | 2250 | 73.1% | +2.68% | −9.4% |
| Q1 | tightening | 79 | 29.1% | −9.60% | −40.2% |
| Q2 | loosening | 3450 | 75.9% | +3.50% | −9.2% |
| Q2 | tightening | 49 | 53.1% | +0.62% | −10.0% |
| Q3 | loosening | 916 | 59.3% | +1.29% | −17.0% |
| Q3 | tightening | 65 | 56.9% | +1.39% | −11.5% |
| Q4 | loosening | 1635 | 75.7% | +3.77% | −12.2% |
| Q4 | tightening | 202 | 30.7% | −4.82% | −30.7% |

**Headline (Q1/Q2 expansion quads):** loosening 74.8% hit / +3.18% (n=5700) vs tightening
38.3% / −5.69% (n=128) → **+36.5pp** split. HAC mean(loosening) +0.0318, **t=+7.0**;
tightening mean −0.0569, t=−0.84 (n=128, weak). NFCI tightening is bearish in *every* quad
(Q1 and Q4 tightening both ~30% hit, p10 drawdowns −40%/−31%).

## Split-half

- 1993–2011: loose 71.6% (n=3308) vs tight 38.3% (n=128) → +33.3pp
- 2012–2026: loose 79.3% (n=2392) vs tight **n=0** → split undefined

**The catch:** NFCI tight-and-tightening fires on only ~5% of days and **zero times after
2012** — NFCI has been at/below its zero line for most of the post-GFC era. The entire
de-risk benefit comes from ~2 pre-2012 episodes (2000–02, 2008).

## Tradeable overlay (long SPY, de-risk when NFCI tight-and-tightening, bill carry)

| Strategy | CAGR | Sharpe | MaxDD |
|---|--:|--:|--:|
| SPY buy&hold | +10.39% | 0.63 | −55.2% |
| 200dma long/flat | +8.08% | 0.72 | −27.8% |
| NFCI flat-when-tight | +10.84% | 0.72 | −48.8% |
| NFCI half-when-tight | +10.71% | 0.69 | −48.1% |

Best overlay DSR 0.9991, split-half Sharpe +0.57 / +0.92 (same-sign). **But the DSR is
computed on the full daily series and massively overstates the true evidence** — the signal
only *acts* in ~2 clustered crises (the honest-N≈4 trap). It beats B&H on CAGR *and* MaxDD,
but on a handful of decisions.

## Verdict / wiring

Confirmer. The descriptive odds are a clean, honest decision aid (already half-wired into
the dial). Do **not** promote to a scored standalone — effective-N is ~2 fires. Surface the
odds table on `signal_lab.html` (and optionally a macro.html panel). Per the prior, do NOT
build the full 24-cell quad × recession-band × NFCI grid (only ~8 of 24 cells exceed N=50).

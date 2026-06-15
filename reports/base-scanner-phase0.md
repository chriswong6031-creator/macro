# Base-scanner Phase-0

**Verdict: NO-GO.** A constructive-base / breakout-proximity signal does **not** add
validated predictive value here — and the scanner's own "buy near the pivot" signal
is, if anything, **anti-predictive** on this universe. Don't build the IBD pattern
zoo. (Confirms the gap-analysis call and is consistent with the setups-engine timing
leg already measuring IC<0 / cosmetic, [[us-standout-setup-score]].)

## The question

The competitor's "Base Scanner" flags tight consolidations near a breakout pivot
(IBD / Minervini). Two honest, decision-relevant tests:
1. **Standalone** — does a "constructive base" score predict forward returns?
2. **Confirmer** — does *conditioning a price/momentum signal* on being in a tight
   base near the pivot sharpen it? (the only version worth shipping, as a chip)

## Harness (`scripts/base_scanner_phase0.py`)

Price-only (no volume → not data-blocked like RVOL), on `data/stocks` (110 deep
names; survivorship-biased curated survivors). Signals: `tight` = −(40d realized
vol), `pivot_prox` = close / 60d-high, `base` = z(tight)+z(pivot_prox),
`mom` = 12-1. Gates = the shared `engine/validation.py`: rank IC + Newey-West t,
Benjamini-Hochberg FDR, Deflated Sharpe (n_trials=14) + block-bootstrap. 4 harness
tests (power + specificity of the confirmer, signal definitions).

## Why NO-GO — three independent grounds

1. **The scanner's own signal is significantly NEGATIVE.** `base`, `tight` and
   `pivot_prox` all have negative IC that *survives* FDR (e.g. pivot_prox −0.028
   t=−2.6 @21d, −0.044 t=−3.0 @63d; base −0.032 / −0.058). Being tight-and-near-the-
   pivot predicted **lower** forward returns — the well-known short-term reversal /
   "extended" effect, the **opposite** of the IBD thesis. A scanner that flags these
   as buys would have been anti-predictive.

2. **The clean (size-controlled) confirmer is sub-significant.** Conditioning
   momentum on the base condition: `mom|pivot_prox` uplift +0.021 (t≈1.4–1.6, fails
   FDR), `mom|tight` uplift *negative*. No FDR-surviving uplift at either horizon.

3. **The one positive-looking result is confounded.** The base-confirmed momentum
   L/S (Sharpe 0.49 vs plain 0.22, cum +1083%) is **not** trustworthy: the long leg
   is a concentrated subset of the momentum quintile (mechanical Sharpe lift), the
   universe is 110 survivors (inflates every momentum strategy — see
   [[residual-alpha-momentum]]), and with an honest `n_trials=14` its Deflated
   Sharpe is **0.86 (<0.90)** — it does not clear the multiple-testing haircut. It is
   supporting colour, never a GO gate.

## Conclusion

Do **not** build a base scanner — not the IBD cup/flat/flag pattern zoo, and not
even a lightweight base/pivot confirmer chip: on this data the base concept is
wrong-signed and the only positive interaction (momentum slightly sharper among
near-pivot leaders) is sub-significant and survivorship-suspect. The last open
"Trac" gap item is closed as a documented dead-end. If ever revisited, it needs a
broad point-in-time universe with residual-alpha as the base (where the timing
overlay might behave differently) — but the prior is now firmly negative.

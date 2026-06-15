# Cross-asset lead/lag — Phase-0 honesty gate

*Ordered lead/lag links across 6 keyless markets (US, Crypto, China, HK, Commodities, Dollar), 2014-09-18..2026-06-12 (2688 aligned days), lags [1, 2, 3, 5, 10]. prod_t = z_follower(t)·z_leader(t−k); Newey-West (HAC, 10-lag) t-stat; Benjamini-Hochberg FDR across all 150 ordered pairs×lags. Split-half = same sign AND |t|>=2 in BOTH halves of history.*

**Full-sample FDR survivors:** 7 of 150 · **split-half stable:** 5

| leader → follower | lag | r | HAC t (full) | q_FDR | t (½1) | t (½2) | split-half stable |
|---|--:|--:|--:|--:|--:|--:|:--:|
| US → HK | 1d | +0.27 | +7.67 | 0.0 | +6.37 | +4.98 | ✅ |
| Commodities → HK | 1d | +0.13 | +5.29 | 0.0 | +3.54 | +4.02 | ✅ |
| Dollar → HK | 1d | +0.14 | +5.16 | 0.0 | +2.72 | +4.46 | ✅ |
| US → China | 1d | +0.15 | +4.49 | 0.0 | +2.81 | +4.29 | ✅ |
| Crypto → HK | 1d | +0.09 | +4.04 | 0.003 | +1.13 | +4.56 | ✗ |
| Commodities → China | 1d | +0.09 | +3.54 | 0.01 | +2.66 | +2.41 | ✅ |
| Crypto → China | 1d | +0.05 | +2.84 | 0.0964 | +0.89 | +3.57 | ✗ |

### Verdict: DISPLAY / transmission-regime gauge — the surviving links are the mechanical timezone ones (lag-1 into the Asia session); cross-asset lead/lag is regime-dependent, so it is shown as a transmission read, never a hedge ratio.

## Honesty notes

- Every link is HAC-corrected (overlapping-window autocorrelation) and FDR-gated (many pairs screened) — the same kernel the factor scorecard uses.
- All surviving links are lag-1: consistent with timezone transmission (the US/global close precedes the next Asia open) rather than a forecastable macro lead.
- Split-half failure ≠ fake: a link can be real now and absent a year ago. That is exactly why the live gauge stamps each top link with a prior-window stability flag and defaults to "contemporaneous".
- This validates DIRECTION/transmission only; magnitudes are standardized correlations, not hedge ratios or tradeable signals.

*Run: `python -m scripts.cross_asset_leadlag_phase0`*
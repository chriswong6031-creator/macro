# BTC Midterm Gate Attribution — Phase 0

> Generated: 2026-07-01  
> n=3 path shapes; illustrative, not calibrated

---

## Part A: Per-cycle attribution

The midterm gate window runs **Jan 1 → election day** for years where `year % 4 == 2`.
Election dates: 2014-11-04, 2018-11-06, 2022-11-08, 2026-11-03.

| Year | BTC window return | Engine raw return | Max DD avoided | Recovery +180d | Gate P&L vs engine | Status |
|------|-------------------|-------------------|----------------|----------------|--------------------|--------|
| 2014 | -27.7% | +4.4% | -29.9% | -27.3% | -4.2% | ✓ Complete |
| 2018 | -52.2% | -19.9% | -56.6% | -11.4% | +24.8% | ✓ Complete |
| 2022 | -61.1% | -15.2% | -61.3% | +53.5% | +17.9% | ✓ Complete |
| 2026 | — | — | — | — | — | **PENDING** |

**Column definitions:**
- **BTC window return**: BTC price return from Jan 1 to election day.
- **Engine raw return**: alloc_optimal_raw equity return over the same window (raw engine WITH drawdown brake, no midterm gate).
- **Max DD avoided**: worst intra-window drawdown vs Jan 1 close (depth the gate sidestepped).
- **Recovery +180d**: BTC return from election day to +180 calendar days (context for post-gate environment).
- **Gate P&L vs engine**: `(1.0_gated - engine_equity) / engine_equity × 100` — positive = gate beat the raw engine.

---

## Part B: Block-bootstrap breakeven fan

Method: linear regression on n=3 historical observations (engine_return = a + b × BTC_return),
then residual bootstrap (N=2,000 draws) for confidence intervals.
Positive gate P&L = gate beat the brake-only raw engine; negative = gate was worse.

**n=3 path shapes; illustrative, not calibrated**

| BTC depth | P5 gate P&L | P50 gate P&L | P95 gate P&L | Point est. |
|-----------|-------------|--------------|--------------|------------|
| -20% | -11.5% | -7.9% | -4.3% | -7.9% |
| -30% | -4.8% | -1.2% | +2.4% | -1.2% |
| -40% | +1.9% | +5.5% | +9.1% | +5.5% |
| -50% | +8.7% | +12.2% | +15.8% | +12.2% |
| -60% | +15.4% | +18.9% | +22.5% | +18.9% |
| -70% | +22.1% | +25.6% | +29.2% | +25.6% |
| -80% | +28.8% | +32.3% | +35.9% | +32.3% |

---

## Caveats

1. **n=3**: Three prior midterm years are the entire historical sample. Every
   statistical conclusion from this analysis is illustrative, not calibrated.
   The fan and CIs should be read as 'plausible range given the 3 observed shapes',
   not frequentist confidence intervals.

2. **Brake-only is not passive**: `alloc_optimal_raw` already includes an enforced
   drawdown brake that cuts exposure when the strategy goes underwater. The gate
   competes against this active defense, not against buy-and-hold.

3. **No D* breakeven trigger**: This report deliberately does not headline a
   breakeven depth. With n=3, any such threshold would be spuriously precise.
   The fan shows the directional story; the threshold question should be
   revisited after 2026 adds a fourth observation.

4. **Residual bootstrap with n=3**: The residual bootstrap resamples 3 residuals
   with replacement, producing only 4 distinct bootstrap samples per draw.
   CIs are rough order-of-magnitude guides, not tight bounds.

5. **2026 status**: PENDING. Do not fill in projected outcomes.

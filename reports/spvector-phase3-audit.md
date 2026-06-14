# S&P / Macro Vector — Phase 3 confidence audit

*Canonical strategy `vector_alloc` (de-risk glide + Fed-put-gated 42d re-deploy), SPY 1993-2026, cash@DTB3, 3.0bps. The final honesty gate before the dashboard ships.*

## Headline

| | strategy | buy & hold |
|---|--:|--:|
| CAGR | 13.01 | 10.82 |
| Sharpe | 0.92 | 0.65 |
| MaxDD | -33.2 | -55.2 |

## Block-bootstrap 95% CI (B=5000, 21d blocks)

- Sharpe CI [0.61, 0.93, 1.25], P(Sharpe>0)=1.0
- MaxDD% CI [-44.5, -28.2, -17.7]

## QE-era (2020-2021) exclusion

- ex-QE Sharpe 0.94 (B&H 0.62); ex-QE MaxDD -33.2 (B&H -55.2) — edge HOLDS without QE

## Year-jackknife (Sharpe edge vs B&H, drop each year)

- positive in 34/34 drop-one-year runs (sign consistency); range [0.18, 0.32]

## AQR-style permutation null (circular-block-shuffle the allocation, B=2000)

- real Sharpe 0.92 vs null p95 0.72 -> skill p=0.0 (PASS)
- real MaxDD -33.2 vs null shallowest-5% -41.9 -> skill p=0.0 (PASS)

## Deflated Sharpe (honest trial count)

- DSR 0.9994 at n_trials=30 (SR0_annual 0.36)

## GATE

- PASS Sharpe CI lower bound > 0
- PASS edge holds ex-QE
- PASS year-jackknife sign-consistent (>=90%)
- PASS permutation-null MaxDD skill p<0.05
- PASS DSR > 0.90

## Honest framing (must appear on the dashboard)
- This is a DRAWDOWN / SHARPE engine, not a CAGR-beater. The CAGR figure includes T-bill carry on the de-risked sleeve; net of carry it ~matches buy & hold. It WILL lag the index in prolonged bulls — that give-up is the premium paid for ~40% shallower drawdowns, banked when the cycle breaks.
- Effective-N is ~4 independent >=20% SPY bears; the permutation-null + leave-one-crisis-out are the binding tests, not the daily-obs DSR. Macro legs are revised (PIT-lagged per-leg); ALFRED vintages remain the last honesty upgrade.
- After-tax in a TAXABLE account, frequent switching realizes short-term gains — best run in a tax-advantaged account (the low ~1.5x/yr turnover helps).

### Verdict: PASS — ship the dashboard

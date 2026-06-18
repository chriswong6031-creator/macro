# SUE deep-history re-validation — Phase-0 follow-up

**VERDICT: SUE STAYS SCORED (re-confirmed on the deepest-available window). The deep-history
(2008+) re-validation the docs call for is BLOCKED by PRICE depth — not EPS depth.**

`DATA_SIGNAL_EXPANSION_2026.md #5` flagged that SUE shipped "validated on the 2023-2025
price window because the price-universe cache is shallow there … a deep-history +
PIT-survivorship re-validation is the honest follow-up." This run characterizes that block
precisely and re-confirms SUE on the full available window.

## Re-run (`scripts/validate_sue.py --start 2008`)

The grid still resolves to **2023-06-30 … 2025-12-31, 11 rebalances, ~842 SUE names** — the
`--start 2008` request is silently capped because the *price* panel doesn't go back further.

| factor | meanIC | IC-IR(ann) | t_HAC | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|
| **SUE** | **0.0380** | **1.24** | **2.85** | **0.047** | 0.82 | 22 |
| value | 0.0307 | 0.61 | 1.03 | 0.47 | 0.64 | 11 |
| composite | 0.0152 | 0.52 | 1.04 | 0.47 | 0.73 | 11 |
| … | | | | | | |
| accruals | −0.0209 | −1.00 | −2.02 | 0.24 | 0.36 | 11 |

SUE quintile L/S Sharpe (ann) **1.45**. **Survive BH-FDR(10%): SUE only.** This re-confirms
the scored status (slightly stronger than the committed IC 0.035) — but on the *same ~3y
window*, so it is **not** the deep test.

## The block (measured, not asserted)

| component | depth | status |
|---|---|---|
| EPS panel (`data/edgar/eps_quarterly.parquet`) | 2008-03 → 2026-05, 65,208 rows, 1,317 tickers | **deep ✓** |
| PIT membership (`data/breadth/sp1500_pit_membership.parquet`) | present | **available ✓** |
| Broad-universe prices (`engine.equity_factors._closes()`) | **2023-05-09 → 2026-06-17, 780 days, 1,506 tickers** | **shallow ✗ — the binding constraint** |

The EPS history and survivorship-clean membership are both there; only the broad-universe
**daily-close panel** is shallow (~3y, a rolling breadth cache). You cannot compute a
forward 63d return before mid-2023 for the cross-section, so the IC grid cannot extend back.

## Path to a genuine deep test (a CI/data job, not an ad-hoc session step)

1. Backfill deep daily closes for the **union of historical S&P1500 members**
   (`sp1500_pit_membership.parquet` gives the roster per date) — ~1,500–2,000 tickers via the
   existing `collectors/breadth.py` / yahoo machinery into the `data/breadth` close store.
   This is a large, rate-limited network job → run it in `daily.yml` / CI, not inline.
2. Re-run `scripts/validate_sue.py --start 2011` for a true **2011-2026 PIT + survivorship**
   IC grid (the EPS panel already supports it), and refresh `ic_scorecard.json`.

## Conclusion

SUE remains the one scored cross-sectional factor that survives BH-FDR — re-confirmed here
on the deepest data available. The deep-history strengthening is a **price-backfill data
dependency**, now precisely scoped, not a modelling question. No change to the scored
status; the `signal_lab` SUE row is annotated with this dependency.

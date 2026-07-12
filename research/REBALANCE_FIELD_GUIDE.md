# Rebalance Field Guide

> **Descriptive census — no signal claims; verdicts only via pre-registered rulers.**
> SPY fwd-21d return is DESCRIPTIVE ONLY (not pre-registered; printed for context).
> Authority: display/context. may_rank=false, may_gate=false, may_size=false.

Generated: 2026-07-12

---

## Quarter-End Windows (2023-06 → present)

| Date | Market Vol Ratio | Up-Share | N Mega-Cap RVOL≥2× | SPY Fwd-21d (CONTEXT) |
| ---- | ---------------- | -------- | ------------------- | --------------------- |
| 2023-03-31 | n/a | n/a | n/a | n/a |
| 2023-06-30 | 1.03× | n/a | 0 | n/a |
| 2023-09-29 | 0.93× | n/a | 0 | n/a |
| 2023-12-29 | 0.62× | n/a | 0 | n/a |
| 2024-03-28 | 0.89× | n/a | 0 | n/a |
| 2024-06-28 | 1.72× | n/a | 0 | n/a |
| 2024-09-30 | 0.83× | n/a | 0 | n/a |
| 2024-12-31 | 0.62× | n/a | 0 | n/a |
| 2025-03-31 | 0.91× | n/a | 0 | n/a |
| 2025-06-30 | 0.76× | n/a | 0 | n/a |
| 2025-09-30 | 0.83× | n/a | 0 | n/a |
| 2025-12-31 | 0.71× | n/a | 0 | n/a |
| 2026-03-31 | 0.88× | n/a | 0 | n/a |
| 2026-06-30 | 1.08× | 0.43 | 1 | n/a |

---

## Russell Reconstitution Days (2023-06 → present)

| Date | Source | Market Vol Ratio | Up-Share | N Mega-Cap RVOL≥2× | SPY Fwd-21d (CONTEXT) |
| ---- | ------ | ---------------- | -------- | ------------------- | --------------------- |
| 2023-06-23 | override | 0.84× | n/a | 0 | n/a |
| 2024-06-28 | override | 1.72× | n/a | 0 | n/a |
| 2025-06-27 | override | 1.02× | n/a | 0 | n/a |
| 2026-06-26 | override | 1.65× | 0.61 | 11 | n/a |

---

## Notes

- **Market Vol Ratio**: total market volume on the day ÷ 20-day median.
- **Up-Share**: up-volume / (up-volume + down-volume) from `data/breadth/updown.parquet`
  (available from 2026-05-19 only; earlier dates show `n/a`).
- **N Mega-Cap RVOL≥2×**: count of top-30 names with RVOL20 ≥ 2× on the day.
- **SPY Fwd-21d**: SPY close-to-close return over the 21 sessions starting the day after.
  NOT a signal claim — descriptive context only, from a single non-overlapping window.
- All 'n/a' entries = data absent from the local store.
- This census was produced by `scripts/census_rebalance_days.py` from local parquet stores.
  Production stores on the Mac Studio runner may have more history.

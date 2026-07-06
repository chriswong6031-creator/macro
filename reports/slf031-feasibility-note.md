# SLF-031 Lazy Prices — Feasibility Note

**Date:** 2026-07-06
**Lane:** L9 — feasibility spike only. No signal claims. No trial-ledger writes.
**Status:** SPIKE COMPLETE — design doc and pilot numbers delivered.

## What was done

1. **Pilot (Part A):** Fetched two consecutive 10-K primary documents for 19/20 S&P 500 tickers
   from EDGAR (1 ticker skipped due to pagination). Measured fetch time, doc size, parse time,
   and computed three similarity metrics (cosine TF-IDF, Jaccard 3-gram, normalized length delta)
   for each consecutive 10-K pair. Item 1A (Risk Factors) extraction attempted; succeeded for 2/19
   due to regex parser limitations.

2. **Cost model (Part B):** Extrapolated to S&P 1500 × (10-K + 10-Q) × 2015–2026 (~66k filings).
   Full backfill = 4.6h fetch at 8 req/s + ~68 GB stripped text on R2 + 1.3h similarity compute.
   Quarterly refresh = ~7 minutes total.

3. **Design doc (Part C):** See `research/SLF031_LAZY_PRICES_FEASIBILITY.md` for full architecture,
   pilot numbers, metric distributions, and draft pre-registration.

## Key numbers

| | |
|---|---|
| Tickers piloted | 19/20 (1 skipped: JPM pagination) |
| Cosine TF-IDF (median) | 0.9524 (range 0.91–0.97) |
| Jaccard 3-gram (median) | 0.5933 (range 0.53–0.71) |
| Length delta (median) | 0.0252 (range 0.003–0.112) |
| Median fetch time (2 docs) | 3,802 ms |
| Median doc size (2 docs) | 7.07 MB |
| Similarity compute (median) | 83 ms |
| Item 1A parse success | 2/19 (10%) — BLOCKING for item-level study |

## Blockers before phase-0

1. Item 1A parser failure rate (10% success) — needs XBRL-based extraction.
2. CIK mapping table bug (AMAT CIK returned ADBE filings).
3. R2 write credentials for text store.
4. Trial-ledger registration (must precede any data examination).

## Files produced

- `scripts/slf031_edgar_pilot.py` — the pilot script
- `tests/test_slf031.py` — 23 unit tests (all pass)
- `reports/slf031_pilot_raw.json` — raw pilot results (JSON)
- `research/SLF031_LAZY_PRICES_FEASIBILITY.md` — full design doc (primary deliverable)

## Verdict

Feasibility: **GO with pre-conditions.** EDGAR access is reliable and free. The backfill is a
one-time ~5-hour Mac Studio job. The confirmer ceiling (TEXT ≤ 50) is appropriate. Pre-conditions:
fix CIK mapping, resolve Item 1A parser, confirm R2 credentials, register pre-reg before any
data examination.

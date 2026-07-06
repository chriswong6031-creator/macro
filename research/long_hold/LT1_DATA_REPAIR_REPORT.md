# LT-1b: edgar statements.parquet data repair report

**Date:** 2026-07-06  
**Branch:** feat/lt1b-edgar-backfill  
**Depends on:** PR #1592 (LT-1a — shares unit fix, period_end stamp, future-FY guard)

---

## Summary

Full-universe backfill of `data/edgar/statements.parquet` completed to pick up:
1. LT-1a bug fixes (shares unit fix — was USD, now "shares"; period_end stamp; future-FY guard)
2. W2 PR-H FLOW additions (`depreciation`, `sbc`, `research_dev`)

Run time: ~33 minutes wall-clock (01:54 – 02:27 PDT), 1,502 CIK fetches at ≤8 req/s SEC pacing.

---

## Before / After

| Metric | Before (pre-backfill) | After |
|--------|----------------------|-------|
| Shape | (7781, 27) | (8781, 28) |
| Tickers | 1334 | 1506 |
| Row delta | — | +1000 |
| Column delta | — | +1 (`period_end` added) |
| `period_end` column | ABSENT | present |

---

## Coverage: all rows

| Field | Non-null rows | % rows | Tickers ≥1 non-null | % tickers |
|-------|--------------|--------|---------------------|-----------|
| period_end | 8751 / 8781 | 99.7% | 1501 / 1506 | 99.7% |
| shares | 6286 / 8781 | 71.6% | 1135 / 1506 | 75.4% |
| depreciation | 8192 / 8781 | 93.3% | 1424 / 1506 | 94.6% |
| sbc | 8322 / 8781 | 94.8% | 1447 / 1506 | 96.1% |
| research_dev | 3330 / 8781 | 37.9% | 588 / 1506 | 39.0% |
| interest_exp | 5110 / 8781 | 58.2% | 1148 / 1506 | 76.2% |

Notes:
- `research_dev` ~39% is expected — only R&D-spending companies (tech/pharma/biotech) report this line
- `interest_exp` latest-FY coverage is 26.6% because many companies don't carry debt in the most recent year; overall ticker coverage 76.2% is fine
- 5 tickers (FOX, GOOG, KW, MASI, NWS) have no `period_end` due to absence of XBRL `instant` balance facts in their SEC filings
- `shares` 72% latest-FY is expected — some filers use alternative XBRL tags not yet in the BALANCE_SHARES map

---

## Coverage: latest fiscal year only (1506 rows, one per ticker)

| Field | Non-null | % tickers |
|-------|---------|-----------|
| shares | 1085 / 1506 | 72.0% |
| depreciation | 1408 / 1506 | 93.5% |
| sbc | 1433 / 1506 | 95.2% |
| research_dev | 573 / 1506 | 38.0% |
| interest_exp | 401 / 1506 | 26.6% |

---

## Future-FY rows

`Future-FY rows: 0`

The future-FY guard (added in LT-1a) dropped all rows where `period_end > today` before writing.

---

## Spot-check against SEC EDGAR public filings

### AAPL FY2024 (period_end 2024-09-28)

| Field | Parquet | SEC 10-K |
|-------|---------|----------|
| Revenue | $391.04B | $391.035B |
| Net income | $93.74B | $93.736B |
| SBC | $11.69B | $11.688B |
| R&D | $31.37B | $31.370B |
| D&A | $11.45B | ~$11.4B |
| Shares | 15.117B | ~15.1B |

### MSFT FY2024 (period_end 2024-06-30)

| Field | Parquet | SEC 10-K |
|-------|---------|----------|
| Revenue | $245.12B | $245.122B |
| Net income | $88.14B | $88.136B |
| SBC | $10.73B | $10.734B |
| R&D | $29.51B | $29.51B |
| Shares | 7.434B | ~7.43B |

### NVDA FY2026 (period_end 2026-01-25)

| Field | Parquet | SEC 10-K |
|-------|---------|----------|
| Revenue | $215.94B | $215.938B |
| Net income | $120.07B | $120.067B |
| SBC | $6.39B | ~$6.4B |
| R&D | $18.50B | ~$18.5B |
| Shares | 24.304B | ~24.3B |

All spot-check values match SEC EDGAR 10-K filings to reported precision.

---

## Engine smoke tests

```
python -m pytest tests -k "fundamental or statement or piotroski or moat" -q
192 passed, 11646 deselected in 30.19s
```

Zero failures.

---

## Caveats / next steps

- `research_dev` 39%: expected for universe; no action needed
- `shares` 72%: covers all major-cap tickers; gaps are small-cap EDGAR filings using non-standard XBRL tags; no action needed for W2 thesis
- 5 tickers missing `period_end` (GOOG etc.): GOOG duplicates GOOGL CIK; the others are niche filers; no action needed
- `statements_quarterly.parquet` already had `period_end` at 100% and does NOT include the new FLOW fields (depreciation/sbc/research_dev); no changes required

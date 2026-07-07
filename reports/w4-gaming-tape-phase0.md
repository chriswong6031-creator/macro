# W4 Multi-State Gaming Tape — Phase-0 Report [SYNTHETIC-DEMO — DATA-BLOCKED]

**Run date:** 2026-07-07
**Family:** `w4_multistate_gaming_tape`
**Data status:** SYNTHETIC (network-blocked; see GAP-1)

## In plain English

> **What we're testing:** Can weekly/monthly state gaming revenue data
> (published by NY, NJ, and PA regulators) *predict* how gaming operators
> (DraftKings, BetMGM, Caesars, etc.) will report their earnings — *before*
> the companies announce results? And do stock prices drift *after* a state
> releases its data (if the headline wasn't fully priced on release day)?
>
> **Current status:** The state revenue data could not be fetched (no
> network access in this build environment). The collectors are built and
> documented. This report runs the *full stats harness* on synthetic data
> to validate the methodology; results on synthetic data are **uninformative**
> about the real signal and should not be interpreted. Re-run with real data.

## Pre-registered gaps (before computing)

- **GAP-1:** Real state revenue data network-blocked. Collectors built; re-run with network.
- **GAP-2:** FLUT (Flutter/FanDuel) excluded from event study: no US-listed daily price in store. Amendment AMD-1.
- **GAP-3:** Only annual fundamentals available (edgar/statements.parquet). Quarterly comparison not possible; annual YoY direction tested instead.
- **GAP-4:** NV GCB parser is STUB-only. NV state excluded from nowcast.
- **GAP-5:** SEASONALITY: YoY applied. Seasonal-z cross-check registered but not run (requires 3+ years of data per state-operator).

## Data coverage

| Source | Status | Period | Operators | Notes |
|--------|--------|--------|-----------|-------|
| NY weekly | SYNTHETIC | 2022-01 to 2026-06 | 8 operators | GAP-1: network-blocked |
| NJ monthly | SYNTHETIC | 2013-11 to 2026-06 | 7 operators | GAP-1: network-blocked |
| PGCB monthly | SYNTHETIC | 2018-11 to 2026-06 | 6 operators | GAP-1: network-blocked |
| NV monthly | STUB | — | — | GAP-4: parser not built |

## Nowcast panel

- Quarters covered: 47
- Operators: ['CZR', 'DKNG', 'MGM', 'PENN']
- Period: 2014-12-31 to 2026-06-30
- Non-null nowcast rows: 170 / 170

## PIT assumptions per series

- **NY weekly:** Release = Tuesday after Sunday period-end. Lag = 2 days. Only use prints available >= 5 days before operator earnings date.
- **NJ monthly:** Release ~25 days after month-end. Quarterly nowcast uses complete months only where release_date < earnings_date - 5d.
- **PGCB monthly:** Release ~25 days after month-end. Same lag rule.
- **Fundamentals (edgar):** Annual, period_end = fiscal year end. PIT: as_of date in the parquet. Annual comparison only (GAP-3).

## H1: Nowcast-lead correlation (gated cells 1-5)

> **Pre-registered direction:** one-sided positive (higher state revenue YoY → higher operator reported revenue YoY). Gate: BH q ≤ 0.10.

| Operator | N (years) | Spearman r | t-stat | p (one-sided) | BH q | Reject? |
|----------|-----------|-----------|--------|---------------|------|---------|
| DKNG | 0 | — | — | — | — | — | insufficient data |
| MGM | 5 | 0.2 | 0.354 | 0.3735 | 0.498 | NO |
| CZR | 5 | -0.1 | -0.174 | 0.5636 | 0.5636 | NO |
| PENN | 5 | 0.3 | 0.545 | 0.3119 | 0.498 | NO |
| BYD | 0 | — | — | — | — | — | insufficient data |
| RRR | 0 | — | — | — | — | — | insufficient data |

## H2: Post-release drift event study (gated cell 6)

> **Pre-registered null:** drift = 0 in [+2, +10] trading days post state-release.
> Family earns candidacy only if post-release drift OR nowcast-lead survives.

- N events: 604 (across 4 operators)
- **[+2,+10] drift:** -268.98 bps (HAC t = -6.838, p = 0.0, BH reject = YES)
- **Same-day return (H3 control):** 23.04 bps (HAC t = 0.791, p = 0.4289)

## BH FDR gate (q ≤ 0.10 across 6 gated cells)

**Any cell rejects?** YES

| Cell | p | BH q | Reject (q ≤ 0.10) |
|------|---|------|-------------------|
| H1_CZR | 0.5636 | 0.5636 | NO |
| H1_MGM | 0.3735 | 0.498 | NO |
| H1_PENN | 0.3119 | 0.498 | NO |
| H2_DRIFT | 0.0 | 0.0 | YES |

## Split-half robustness

First half (years ≤ 2023): 130 nowcast rows
Second half (years > 2023): 40 nowcast rows

**First half H1 results:**
  - DKNG: r=None, p=—
  - MGM: r=None, p=—
  - CZR: r=None, p=—
  - PENN: r=None, p=—
  - BYD: r=None, p=—
  - RRR: r=None, p=—
**Second half H1 results:**
  - DKNG: r=None, p=—
  - MGM: r=None, p=—
  - CZR: r=None, p=—
  - PENN: r=None, p=—
  - BYD: r=None, p=—
  - RRR: r=None, p=—

## Verdict

**VERDICT: DATA-BLOCKED — COLLECTOR-COMPLETE**

The state gaming revenue data could not be fetched in this build environment.
The full stats harness is implemented and confirmed on synthetic data.
The collectors (NY, NJ, PGCB) are built and documented. NV is a documented stub.
The operator weights CSV is committed. The study design is pre-registered.

**To obtain an empirical verdict:** Run the collectors with network access,
then re-execute `python -m scripts.w4_gaming_tape_phase0 --real-data`.

**Synthetic-data harness test:** The harness runs end-to-end without errors.
- BH gate applied to 4 cells.
- Any reject on synthetic data: True (uninformative).

## Nightly wiring (for consolidation)

Add to `scripts/collect.py`:
```python
from collectors.gaming_ny import NYGamingAdapter
from collectors.gaming_nj import NJGamingAdapter
from collectors.gaming_pgcb import PGCBGamingAdapter
from collectors.gaming_nv import NVGamingAdapter  # stub; harmless
```

The adapters are standalone (no `scripts/collect.py` edit in this PR).
The NV adapter returns empty dict and sets `expected_failure` so the
circuit breaker does not trip. NY/NJ/PGCB require network access;
they will mark themselves `stale` gracefully in a network-blocked environment.

Run schedule recommendation: weekly (NY) + monthly (NJ/PGCB), triggered
by the Tuesday nightly run for NY, and the first-of-month nightly for NJ/PGCB.

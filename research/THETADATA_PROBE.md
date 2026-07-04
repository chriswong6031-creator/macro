# ThetaData Entitlement Probe — Measured Facts

_Pattern: research/OPTIONS_FLOW_DATA.md (measured facts, not vendor marketing).
This document is a SKELETON populated from the --probe run after subscription activates.
Sections marked [PENDING] require the --probe output to be pasted here._

---

## §0 Context

ThetaData Options Pro ($160/mo) was acquired on 2026-07-04.  This document records
entitlement facts, API behavior, and signing calibration results as MEASURED against
the live system — not as the vendor documents them.

The Phase-A plumbing PR (`feat/thetadata-plumbing`) built all collectors and drivers
before the subscription was active (INERT pattern; no live API calls in CI).  This doc
is the first place post-subscription probe output lands.

---

## §1 Entitlement Probe Results

[PENDING — run after subscription activates:]

```
python -m scripts.backfill_thetadata_eod --probe
```

Paste the output here verbatim.

### 1.1 EOD chains
- Endpoint: `/v2/bulk_hist/option/eod`
- Root tested: SPY, date range: [PENDING]
- Row count: [PENDING]
- Latency: [PENDING] seconds
- Columns confirmed: [PENDING]
- Error codes encountered: [PENDING]

### 1.2 Open interest
- Endpoint: `/v2/hist/option/open_interest` (per-contract)
- Ambiguity note: a bulk OI endpoint (`/v2/bulk_hist/option/open_interest`) was NOT
  confirmed in the v2 docs as of 2026-07-04.  The collector iterates contracts from
  the EOD pull.  Confirm at probe time whether a true bulk OI endpoint exists and
  update `collectors/thetadata.bulk_open_interest()` accordingly.
- Row count: [PENDING]
- Latency: [PENDING] seconds

### 1.3 Greeks + implied volatility
- Endpoint: `/v2/bulk_hist/option/greeks` (first-order)
- IV included in greeks response (field index 9 in the tick array): [CONFIRM]
- Second-order endpoint path (`/v2/bulk_hist/option/second_order_greeks`): [CONFIRM/DENY]
- Third-order endpoint path (`/v2/bulk_hist/option/third_order_greeks`): [CONFIRM/DENY]
- Field layout for order=2/3: [PENDING — formalize after probe; currently stored as raw_fields]
- IV separate endpoint (`/v2/hist/option/implied_volatility`): [CONFIRM needed/not needed]

### 1.4 Trade+NBBO (trade_quote)
- Endpoint: `/v2/hist/option/trade_quote`
- Per-contract (root, exp, strike, right required): confirmed in docs
- Row count for SPY 1 week: [PENDING]
- Latency: [PENDING] seconds

### 1.5 Index roots
- SPX (AM-settled): does root "SPX" return data? [PENDING]
- SPXW (PM-settled weekly): does root "SPXW" return data? [PENDING]
  — If yes, add SPXW to INDEX_ROOTS in `scripts/backfill_thetadata_eod.py`
- Probe command: `curl "http://127.0.0.1:25510/v2/list/expirations?root=SPXW"`

---

## §2 Measured Latency & Throughput

[PENDING — from --probe output]

| Endpoint | Root | Date range | Rows | Elapsed (s) | Rows/s |
|---|---|---|---|---|---|
| bulk_eod | SPY | 1 week | [P] | [P] | [P] |
| open_interest | SPY | 1 week | [P] | [P] | [P] |
| bulk_greeks | SPY | 1 week | [P] | [P] | [P] |
| trade_quote | SPY/C/580 | 1 week | [P] | [P] | [P] |

Estimated full backfill time (2012→ present, ~400 roots):
- [PENDING — compute from single-root throughput × universe size × year range]

---

## §3 Strike & Date Format Verification

### 3.1 Strike format
- Documented: 1/10th-cent integer (e.g. $170.00 → 170000). Source:
  https://http-docs.thetadata.us/operations/get-hist-option-trade_quote.html
- Verified against actual response: [PENDING — check that 170000 in response = $170.00]
- Divisor used in `collectors/thetadata.py`: `STRIKE_DIVISOR = 1000.0`

### 3.2 Date format
- Documented: YYYYMMDD integer for parameters; date field in response array is also YYYYMMDD.
- Verified: [PENDING]

### 3.3 OI update timing
- Documented: "Open Interest is normally reported once per day by OPRA at approximately
  06:30 ET and represents end-of-previous-day figures."
- Source: https://http-docs.thetadata.us/operations/get-hist-option-open_interest.html
- This means: OI returned for date T is end-of-EOD T-1.
- Signal construction rule (enforced by §8.1 of LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md):
  for day-t signals, use OI[t-1] (i.e. the OI row dated T-1). Same-day OI in any
  day-t signal = data leak = bug.

---

## §4 Signing Re-calibration (F7 Re-test)

### 4.1 Acceptance criteria (§7.1 of LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md)

A pass requires BOTH:
- Per-trade quote-rule agreement ≥ **0.75**
- Minute/daily net-sign recovery ≥ **0.75**

Current Databento truth (the bar baseline, 2026-06-21):
- Per-trade agreement: 0.777 (size-weighted 0.808)
- Minute net-sign recovery: **0.41** (BELOW a coin flip — F7 ruling)

The tape-sourced calibration should demonstrate that ThetaData trade+NBBO signing
achieves per-trade agreement ≥0.75 (expected: yes, by construction — quote-rule on
actual NBBO is the gold standard) AND, critically, that minute/daily net-sign recovery
≥0.75 (this was the failing metric: bar data gives 0.41 because tick-rule on minute
bars is dominated by delta drift, not flow direction).

### 4.2 Calibration run command

After probe confirms entitlement:
```
python -m scripts.calibrate_flow_signing --source thetadata --start 2026-06-18T14:30 --end 2026-06-18T14:50
```

This uses the SAME date/window as the cached Databento truth slice for direct comparison.

### 4.3 Results [PENDING]

| Metric | Databento truth | ThetaData tape | Bar (old bar=0.7) | Status |
|---|---|---|---|---|
| Per-trade agreement | 0.777 | [P] | ≥0.75 | [P] |
| Per-trade size-wtd | 0.808 | [P] | — | [P] |
| Minute net-sign recovery | 0.41 | [P] | ≥0.75 | [P] |
| Gate PASS/FAIL | — | — | BOTH ≥ bar | [P] |

### 4.4 Adjudication trigger

If BOTH bars pass (agreement ≥0.75 AND recovery ≥0.75):
→ Fable adjudicates the flip of `direction_reliable: true` in `signing_gate.json`
  FOR TAPE-SOURCED FEATURES ONLY.  Bar-sourced features (massive.com tick-rule)
  remain soft regardless.

If either bar fails:
→ Record the gap vs bar and note the limiting factor (bid-ask bounce? quote staleness?
  contract illiquidity?).  The gate stays at false; bar-derived features stay soft.

---

## §5 API Contract Ambiguities

The following were unresolvable from public docs alone as of 2026-07-04.  Each has a
probe check command.  Resolve at first probe run and update `collectors/thetadata.py`.

| # | Ambiguity | Check command | Impact |
|---|---|---|---|
| A1 | Bulk OI endpoint existence (`/v2/bulk_hist/option/open_interest`) | `curl "http://127.0.0.1:25510/v2/bulk_hist/option/open_interest?root=SPY&exp=0&start_date=20260101&end_date=20260110"` | If exists, replace the per-contract iteration in `bulk_open_interest()` |
| A2 | SPX vs SPXW root for weekly PM-settled options | `curl "http://127.0.0.1:25510/v2/list/expirations?root=SPXW"` | If SPXW returns data, add to `INDEX_ROOTS` in backfill driver |
| A3 | Second-order Greeks exact endpoint path | `curl "http://127.0.0.1:25510/v2/bulk_hist/option/second_order_greeks?root=SPY&exp=0&start_date=20260101&end_date=20260107"` | If path differs, update `_GREEKS_ENDPOINTS[2]` in thetadata.py |
| A4 | Third-order Greeks exact endpoint path | `curl "http://127.0.0.1:25510/v2/bulk_hist/option/third_order_greeks?root=SPY&exp=0&start_date=20260101&end_date=20260107"` | Same |
| A5 | Second/third-order Greeks response field layout | Examine first response | Formalize `raw_fields` into named columns in `bulk_greeks()` |
| A6 | IV via separate endpoint vs greeks | `curl "http://127.0.0.1:25510/v2/hist/option/implied_volatility?root=SPY&exp=...&strike=...&right=C&start_date=...&end_date=..."` | If separate IV endpoint provides additional fields, add `hist_iv()` method |
| A7 | exp=0 behavior for bulk endpoints (day-by-day vs all-at-once) | Measure timing of `bulk_eod(root, 0, start, end)` vs per-expiry calls | Performance tuning of the backfill driver |
| A8 | History depth: does Pro actually go to 2012? | `curl ".../bulk_hist/option/eod?root=SPY&exp=0&start_date=20120101&end_date=20120110"` | Sets realistic `DEFAULT_START` in backfill |
| A9 | Password in JVM argv (security): `ThetaTerminal.jar` currently receives credentials as positional argv (`java -jar ThetaTerminal.jar <user> <pass>`), making the password visible in `ps aux`. | Verify at probe whether ThetaTerminal.jar supports a credentials file (e.g. a config JSON or `-Dtheta.creds=path`) instead of argv. If supported, update `scripts/run_theta_terminal.sh` to use the file path. | Removes password from process listing |

---

## §6 IV Cross-validation Design (W1.1 handoff)

W1.1 (in flight) builds a BS-inversion IV series from massive.com aggregates.  Once
ThetaData Pro is active, the acceptance test is:

- For each overlap date (where both W1.1 and ThetaData have data, ~2024-07→):
  compute cross-sectional Spearman rank-corr between the two IV series per name per day
- Acceptance: median rank-corr ≥ 0.90 across the overlap window (the A5 test from
  OPTIONS_ALPHA_MASTERPLAN.md with a real benchmark instead of the 18-day proxy)
- If accepted: W1.1 stays as the fallback/audit series; ThetaData IV becomes the primary
  for depth (12y vs 2y)
- If rejected: investigate the largest divergences and report (possible causes: bid/ask
  mid vs transaction price for inversion, American vs European BS model, q handling)

---

## §7 Status Log

| Date | Event |
|---|---|
| 2026-07-04 | Probe doc skeleton created. Phase-A PR opened (`feat/thetadata-plumbing`). Subscription not yet active. All API contracts from docs; ambiguities A1–A8 documented. Probe run pending subscription activation. |

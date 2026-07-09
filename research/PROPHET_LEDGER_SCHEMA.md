# Prophet Forward Outcome Ledger — Row Schema

**File:** `data/prophet/ledger.jsonl`
**Schema version:** `prophet.ledger/v1`
**Authority:** display (no gate has passed; display-only until forward ledger adjudication)

> **NIGHTLY IS THE SOLE FUTURE ADVANCER OF THIS LEDGER.**
> `scripts/build_prophet.py` initializes the file and the header comment on first run.
> Only the nightly pipeline may append rows (outcome events).
> No intraday or ad-hoc process may write outcome rows.

---

## Row fields

| Field | Type | Description |
|---|---|---|
| `schema` | string | `"prophet.ledger/v1"` — always present |
| `id` | string | Plan ID (`<TICKER>-<DIRECTION>-<signal_date>`) — matches `prophet.trade_plan/v1.id` |
| `asset` | string | Ticker symbol |
| `direction` | string | `"BULL"` or `"BEAR"` |
| `signal_date` | string | ISO-8601 date the plan was originated |
| `close_date` | string | ISO-8601 date the plan was closed |
| `outcome` | string | Enum: `T1_HIT` / `T2_HIT` / `INVALIDATED` / `EXPIRED` / `CLOSED_EARLY` |
| `stock_result_pct` | float \| null | Underlying % return from entry to close (signed) |
| `option_result_pct` | float \| null | Option % return from entry_premium to close mark; null when no option rec existed |
| `days_held` | int | Calendar days from signal_date to close_date |
| `plan_adherence` | string | Descriptive note on adherence to plan geometry (free text) |
| `asof` | string | ISO-8601 date the row was written by the nightly pipeline |

---

## Outcome enum definitions

| Value | Definition |
|---|---|
| `T1_HIT` | Price reached or exceeded T1 before invalidation or horizon expiry |
| `T2_HIT` | Price reached or exceeded T2 (terminal target) **without a prior close >= T1** — see first-trigger note below |
| `INVALIDATED` | Price crossed the `invalidation` level |
| `EXPIRED` | Plan reached `horizon_days` without hitting T1 or invalidation |
| `CLOSED_EARLY` | Operator manually closed the plan before horizon expiry |

> **First-trigger design:** the outcome scanner closes the plan on the *first* close
> that crosses any trigger and records that outcome permanently.  A plan that touches
> T1 then later T2 is recorded as `T1_HIT` only.  `T2_HIT` fires only when a close
> clears T2 without any prior close >= T1 (typically a gap day that skips T1 entirely).
> **Do not read `T2_HIT` frequency as "ever reached T2"** — it is "cleared T2 in a
> single close jump, bypassing T1."  This is intentional: the ledger records the
> first-observable-close outcome, not the eventual maximum reach of the move.

---

## Example row (display-tier placeholder)

```json
{
  "schema": "prophet.ledger/v1",
  "id": "BA-BULL-20260702",
  "asset": "BA",
  "direction": "BULL",
  "signal_date": "2026-07-02",
  "close_date": null,
  "outcome": null,
  "stock_result_pct": null,
  "option_result_pct": null,
  "days_held": null,
  "plan_adherence": null,
  "asof": "2026-07-07"
}
```

---

## Notes

1. The ledger file begins with comment lines (prefixed `#`) documenting the schema.
   These are not JSON and must be skipped by readers (`jsonlines` with `skiprows` or
   a filter on lines starting with `#`).
2. `option_result_pct` is null whenever `option_contract` was null in the originating
   plan (symbol not in ThetaData store at plan creation time).
3. Rows are append-only; updates are forbidden. If a close is corrected, a new row
   with `outcome=CLOSED_EARLY` and a note in `plan_adherence` is appended.
4. This ledger is a **forward ledger** — it accumulates outcomes as they occur nightly.
   No historical backfill is performed. The first real rows will appear after the first
   plan expires or hits a target level.
5. Pre-registration of the row schema (this document) satisfies the house law
   requiring schema-before-authority for any forward-accruing artifact.

---

# Prophet Live Marks — Payload Schema

**R2 key:** `live_flow/prophet_marks.json`
**Schema version:** `prophet.live_marks/v1`
**Producer:** `scripts/build_prophet_marks.py`
**Consumer:** Item C Terminal overlay (fallback when R2 file is absent or stale, EOD mode)
**Authority:** display-tier only; no signal, score, or escalation originates here.
**Publish cadence:** every 5 min during NYSE RTH (09:30–16:00 ET) via launchd
  `com.mastermind.prophetmarks` job; not published outside RTH.

## Payload fields (top-level)

| Field | Type | Description |
|---|---|---|
| `schema` | string | Always `"prophet.live_marks/v1"` |
| `asof_utc` | string | ISO-8601 UTC timestamp when the payload was assembled by the publisher |
| `session_date` | string | ISO-8601 date of the current trading session (ET date at publish time) |
| `marks` | object | Map from OCC option symbol string → mark object (see below); may be empty `{}` |

## Mark object (values in `marks`)

| Field | Type | Description |
|---|---|---|
| `bid` | float \| null | Best bid from ThetaData trade_quote, rounded to 4 decimal places |
| `ask` | float \| null | Best ask from ThetaData trade_quote, rounded to 4 decimal places |
| `mid` | float \| null | `(bid + ask) / 2`, rounded to 4 dp; `null` when either leg is absent (one-sided quote) |
| `last` | float \| null | Last trade price (`price` column), rounded to 4 dp |
| `ts_utc` | string | ISO-8601 UTC timestamp of the **trade** that supplied the mark (from ThetaData `trade_timestamp`, which carries fractional seconds ET-naive, e.g. `'2026-07-02T06:30:16.218'`); falls back to publish-time with a WARNING log if parsing fails |

## OCC symbol key format

`{root:6s}{YYMMDD}{C|P}{strike_millis:08d}`

Example: `BA    260918C00220000` = BA 220.00-strike call expiring 2026-09-18.

## Consumer contract

- `mid` may be `null` (one-sided quote) — consumers must handle gracefully.
- `ts_utc` is always present and parseable as ISO-8601 UTC.
- When the R2 file is absent, >30 min stale, or `asof_utc` is outside RTH, the
  Item C overlay must fall back to EOD marks and display a staleness indicator.
- The `marks` dict may be empty `{}` (no active plans with option contracts).
- Keys are OCC symbols, not plan IDs; consumers must maintain plan→OCC mapping.

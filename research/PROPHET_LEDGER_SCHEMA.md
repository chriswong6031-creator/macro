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
| `id` | string | Plan ID (`<TICKER>-<DIRECTION>-<formation_date>`; historically called the signal-date component) — matches `prophet.trade_plan/v1.id` |
| `asset` | string | Ticker symbol |
| `direction` | string | `"BULL"` or `"BEAR"` |
| `formation_date` | string \| null | Explicit base-formation date used by newly originated plans as the ID date component. Null on legacy rows; no historical row is rewritten to populate it. |
| `signal_date` | string \| null | Causal tier event close on tier-aware plans: the marker knowability close for T1 or the native 2D cascade-cross close for T2. Null for projected T3 because no event has fired. Legacy rows may contain the old formation-date alias, disclosed by `signal_date_basis`. |
| `confirmed_date` | string \| null | T1 marker buy-filter confirmation close, when proven. Never borrowed for T2 and null for provisional T1/T3. |
| `observed_date` | string \| null | Session whose close produced the tier verdict. For T3 this is the honest observation/vintage while `signal_date` remains null. |
| `signal_tier` | string \| null | Creation-vintage admission tier (`T1`–`T4`) when proven. New actionable plans admit T1–T3 only; an audited legacy T4 is quarantined. |
| `signal_date_basis` | string \| null | Provenance label: `tier_event_date`, `tier_observation`, or `legacy_formation_alias`. |
| `signal_provisional` | boolean \| null | True for forming T1 and projected T3 observations; false for confirmed T1/T2 events. |
| `source_marker_date` | string \| null | Immutable legacy §7 marker bucket-open label, retained separately so it cannot be mistaken for the causal event close. |
| `price_basis_date` | string \| null | NYSE session whose close supplied the plan's `entry`. Explicit on newly originated plans; null on legacy rows where that provenance was not recorded. |
| `entry_date` | string \| null | Date from which the plan's horizon/outcome clock ran. For new plans it equals `price_basis_date`; older rows may contain a legacy fallback. |
| `recorded_at` | string \| null | Run/publication date of the originating plan. It may be a weekend recovery date and therefore must never be used as a price-session substitute. |
| `close_date` | string | ISO-8601 date the plan was closed |
| `outcome` | string | Enum: `T1_HIT` / `T2_HIT` / `INVALIDATED` / `EXPIRED` / `CLOSED_EARLY` |
| `stock_result_pct` | float \| null | Underlying % return from entry to close (signed) |
| `option_result_pct` | float \| null | Option % return from entry_premium to close mark; null when no option rec existed |
| `days_held` | int | Calendar days from `entry_date` to `close_date` |
| `plan_adherence` | string | Descriptive note on adherence to plan geometry (free text) |
| `asof` | string | ISO-8601 date the close row was written by the nightly pipeline |

### Temporal clock contract

The clocks are deliberately separate:

- `formation_date` is the technical-base anchor and stable ID basis.
- `signal_date` is the tier-native fired-event close for T1/T2; T3 has no fired
  event, so it carries `signal_date=null` and a real `observed_date` instead.
- Historical/pre-contract rows can retain the former formation-date alias, but must
  identify it as `signal_date_basis=legacy_formation_alias` when newly projected.
- `price_basis_date` and `entry_date` identify the actual NYSE session whose close
  produced `entry` and starts grading.
- Plan `asof`/`recorded_at` identify when the artifact was run or published.
- Ledger `asof` identifies when the close event was recorded.

A weekend recovery run may therefore carry `recorded_at=2026-08-08` and
`price_basis_date=entry_date=2026-08-07`. The bridge rejects a weekend, holiday,
malformed, or future `price_basis_date`; it never rounds one backward and silently
attaches Friday to an unproven price.

This contract is prospective. Existing plan files and ledger rows are append-only and
are not rewritten or re-keyed by the clock repair. Proven historical facts are exposed
through `data/prophet/plan_corrections.jsonl` and
`data/prophet/ledger_corrections.jsonl`; authoritative readers use the shared effective
projection. A missing field on a legacy row is an honest era boundary, not permission
for a reader to infer a date.

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
  "formation_date": "2026-07-02",
  "signal_date": "2026-07-02",
  "confirmed_date": "2026-07-06",
  "observed_date": "2026-07-06",
  "signal_tier": "T1",
  "signal_date_basis": "tier_event_date",
  "signal_provisional": false,
  "source_marker_date": "2026-06-30",
  "price_basis_date": "2026-07-02",
  "entry_date": "2026-07-02",
  "recorded_at": "2026-07-02",
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
3. Rows are append-only; updates are forbidden. `CLOSED_EARLY` records a real operator
   close and must not be repurposed as a correction mechanism. Historical corrections
   use the versioned, append-only `prophet.ledger_correction/v1` envelope, which records
   the original row, old value, new value, evidence basis, and correction time. The raw
   row remains immutable; the shared effective reader applies the overlay and excludes
   quarantined outcomes from aggregate claims.
4. This ledger is a **forward ledger** — it accumulates outcomes as they occur nightly.
   No historical backfill is performed. The first real rows will appear after the first
   plan expires or hits a target level.
5. Pre-registration of the row schema (this document) satisfies the house law
   requiring schema-before-authority for any forward-accruing artifact.

---

## Addendum 2026-08-11 — force-majeure exception, `recorded_at=2026-08-09` ONLY

**The no-backfill law in Note 4 above stands, unchanged, for every date except one.**
This addendum records a single operator-ordered exception; it is a carve-out with a
name, a date and an enumerated row set, not a repeal, and nothing in it authorises a
second one.

**Authority.** Operator order 2026-08-11 ~00:05Z, an explicit force-majeure override
after a multi-day origination outage. Design of record:
`research/PROPHET_OUTAGE_BACKFILL_2026_08.md` (§0 acceptance gates).

**Scope — exactly one event.** The 2026-08-09 22:59Z Sunday bake RAN the current
intake end to end and refused all 30 eligible candidates at `clock_provenance`,
because the board it read carried a poisoned
`staleness.inputs.panel.mixed_vintage=true`. PR #5241 healed the derivation; the same
board, re-derived, reports `mixed_vintage: false`. The exception permits replaying
that ONE refusal against that ONE pinned board, at `recorded_at=2026-08-09`. It does
not permit any other date:

* **2026-08-03 → 2026-08-06 stay refused.** Standing ruling
  `us-board-frozen-alpha-2026-08` (`data/us_board_ledger/disclosed_gaps.json`, decided
  2026-08-07 by the operator) records those boards as ranked on a factor panel frozen
  at 2026-07-31 — `gradeable: false, backfillable: false`. A vintage-correct replay
  needs a point-in-time board harness that does not exist. Reconstructing from the
  frozen boards would mint picks a correct engine would never have picked, which is
  the exact corruption the no-backfill law exists to prevent.
* **2026-08-10 forward belongs to the live nightly.** Where a live bake has already
  originated a name, the LIVE plan wins; the weekend counterfactual is disclosed
  display-only and never minted (one active plan per candidate episode).

**What the exception does NOT touch.** The backfill lane never writes
`data/prophet/ledger.jsonl`: the nightly remains the sole advancer of the forward
ledger, and it advances a backfilled plan organically from the plan file, exactly as
it does a live one. `site/prophet/index.json` and `site/prophet/states/` are still
rendered only by the nightly. No origination gate was modified — `originate_plans`,
`_resolve_origination_clocks`, `select_candidates` and the #5071 integrity layer run
on their own terms, and every candidate they refuse at execution time is RECORDED in
the disclosure rather than overridden in code (the five chronology-refused candidates
from the R6 audit stay refused).

**How a reader tells a replayed row from a live one.** Every minted plan carries
`origination_mode: "outage_backfill_2026_08_09"` and `backfill_executed_at` (the real
wall date of the write), alongside its normal era stamps — `selection_era` is
UNCHANGED, because the selection rule did not change, only the moment of writing did.
The stamp is carried onto three surfaces, and it needs all three: the per-plan file,
the `site/prophet/index.json` row, and — at close — the **forward-ledger row itself**.
The ledger one is the load-bearing one. It is the substrate every rate, calibration
number and Prophet-training input is ultimately computed over, and a consumer reading
`ledger.jsonl` directly never sees an index row, so a stamp that stopped at the index
would leave the cohort unsplittable exactly where splitting matters most. On all three
surfaces the key is ABSENT on a live row rather than present-and-null: absent means
live, which keeps today's artifacts byte-identical while nothing is reconstructed. A
plan minted by this lane WITHOUT the stamp is a defect.

**What the published record does with them.** `record_summary` does NOT drop these
rows from `win_rate`/`avg_result_pct`. They were graded by the nightly on their own
real bars, so the honest treatment is an ADDITIVE split, not a fourth exclusion: the
record gains `n_reconstructed`, `reconstructed_ids` and a bilingual note naming the
cohort, and the headline numbers are unchanged. Ratified 2026-08-11; shipped in
#5301. The exclusions are elsewhere and are narrower on purpose:

* **Marketing surfaces hard-exclude them** (`engine/marketing/receipt_source.py`,
  `allies.py`, `content_studio.py`). A reconstructed pick may never be presented as a
  live historical call under any framing — that would be a claim about the past that
  is not true, regardless of how the row graded.
* **`prophet_stage_shadow`'s tilt cohort excludes them.** That block is read BACK into
  live geometry (`_stage_tilt_demoted` → `plan_horizon_days`), which is the one place a
  reconstructed row would stop being display-tier and start steering live picks.

**Where the exception is enumerated.** `data/prophet/backfill_disclosures.json` — the
window, the authority, the pinned input SHAs (board commit + plans baseline), the
executing commit, and the full counterfactual set: every plan minted, every collision
that the live lane won, every candidate a gate still refused with its reason, and the
dates that were deliberately NOT reconstructed.

**What keeps the carve-out from widening.**
`tests/test_prophet_outage_backfill.py` asserts a both-directions set equality: every
plan stamped `origination_mode` starting `outage_backfill` appears in the disclosure
artifact, and every disclosed id exists as a plan. It further pins that the only
authorised mode string is `outage_backfill_2026_08_09` and the only authorised
`recorded_at` is `2026-08-09`. A future backfill of any other date therefore turns
the suite red on arrival, and needs its own operator authority, its own disclosure
row and its own dated addendum here — deleting the test is not the remedy.

**Producer.** `scripts/backfill_prophet_outage.py`, a one-off that refuses to run
twice: the disclosure artifact as committed on HEAD is its idempotence lock (reading
the working tree would let an uncommitted delete quietly unlock the lane). Before
merging, `--verify-collisions` re-derives the collision set against fresh
`origin/main` and exits nonzero on any name that went live in the meantime — §0.4's
window closes at MERGE, not at execution.

**Execution marker.** When the replay has actually run and its artifacts are
committed, add a line to this addendum that begins at column 0 with
`executed_window:` followed by the window id.
`tests/test_prophet_outage_backfill.py` keys on exactly that shape — unindented, so
that this paragraph describing the convention cannot itself be mistaken for the
claim. Once the marker is present the suite REQUIRES
`data/prophet/backfill_disclosures.json` to exist, closing the direction where the
docs assert an execution that left nothing behind. The marker is NOT yet set: as of
this commit the replay has been dry-run only.

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

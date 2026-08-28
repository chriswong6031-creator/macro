# OA-1T-Macro Measured Options Microstructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve measured ThetaData trade+NBBO microstructure on the existing live-flow event path and flatten the same point-in-time facts into the existing Flow ML ledger, without changing event identity, selection, direction authority, scoring enablement, episode/campaign contracts, collectors, schedulers, or runtime ownership.

**Architecture:** Reuse the current `collectors.thetadata.bulk_trade_quote` rows and the existing `scripts/live_flow_poller.py -> engine/live_flow.py -> live_flow.event_stage/v1 -> collectors/flow_signals.py` path. Compute direct trade-vs-NBBO measurements from source-valid rows **before** `_sign_batch()` drops unusable quotes, attach one zero-authority `options.trade_nbbo_microstructure/v1` block to qualifying existing events, preserve `options.signal_episode/v1` unchanged, and flatten only measured fields into the existing keep-first `data/flow_signals/ledger.parquet`. No new store, collector, event ID, campaign identity, model family, score, or issuer is created.

**Tech Stack:** Python 3, pandas/numpy, existing ThetaData v3 `trade_quote` collector, JSONL event-stage receipts, Parquet Flow ML ledger, pytest, existing Macro CI/fence pack.

**Spec:** Chairman-approved OA-0 architecture at Macro PR #6573, exact approved spec head `1c5e395e1c0025bec76d75d4ddc6e4f69024c3d1`, file `docs/superpowers/specs/2026-08-27-options-alpha-intelligence-recovery-design.md`. Execution may begin only after that OA-0 source law is merged and the implementation carrier is re-pinned to a descendant of the accepted merge.

## Global Constraints

- **No implementation before OA-0 lands.** This plan may be authored while #6573 validates, but no code task below begins until #6573 is accepted/merged and the implementation branch is based on a current descendant.
- **One canonical intraday source plane.** Reuse `collectors.thetadata.bulk_trade_quote` and the accepted `com.mastermind.liveflow`/M1/R2 path. Do not add a ThetaData process, websocket, poller, launchd unit, store, R2 prefix, queue, or retry plane.
- **Event identity is frozen.** `_event_id(session_date, root, exp, strike, right, seq_max)` and existing premium-floor selection remain byte/behavior compatible. Missing NBBO data may reduce measured coverage; it may not silently create a new event identity or selection rule.
- **Direction remains soft.** Existing `side`, `signing_source`, and the suspended Theta-tape/tick-rule authority are not promoted. `at_ask_share`/`at_bid_share` are execution-location measurements, not buyer identity, institutional intent, opening intent, or bullish/bearish probability.
- **No synthetic ask-share.** The Chain Heat `~buy -> 0.80`, `~sell -> 0.20`, `mixed -> 0.50` proxy must never enter this path.
- **Episode/campaign source law remains frozen.** Do not modify `options.signal_episode/v1`, `options.signal_campaign/v2`, their identity functions, or their historical rows in this wave.
- **No predictive positioning fusion.** `vol_gt_oi_ratio` is a native descriptive event-time fact only. This wave does not authorize it, OI, GEX, skew, or any positioning key in a predictive score/ranker. `DNR:KILL-POSITIONING-FUSION` remains binding.
- **No score promotion.** `config/flow_score.yml` must remain `scoring.enabled: false`; `flow_signals.gate/v2.scored` remains false. Do not run FS-5 or publish calibrated probability.
- **Historical rows stay historical.** Existing Flow ML rows receive null new columns through Parquet schema evolution; never reconstruct later NBBO/OI into old `live_feed` rows as if known at event time.
- **Null law:** missing/invalid quote evidence is null/uncovered, never zero and never neutral. Locked/crossed or causally impossible quote rows do not count as valid NBBO coverage.
- **Production proof must be natural.** Do not use historical `--once --date` to manufacture an RTH event; the live-flow runbook explicitly forbids that as a smoke/proof path.
- **Stop on a hard consumer incompatibility.** If the consumer census proves a current `live_flow.event_stage/v1` consumer hard-enumerates nested event keys and rejects an additive `microstructure` object, stop and return to Sol for a v2 contract decision. Do not weaken the consumer or silently alter v1.

---

## Frozen microstructure semantics for this wave

The worker implements exactly these semantics unless a source-field fact on current `main` disproves feasibility, in which case stop before coding and return the evidence to Sol.

### Source row admission for the measurement denominator

Start from rows that have already passed the current `process_batch()` source-identity, RTH, canonical price/size/strike/sequence, and overlap-sequence dedup checks. Capture that frame **before** `_sign_batch()` filters unusable NBBO rows.

For each exact `(expiration, strike, right)` contract in that source-valid frame:

```text
row_premium_usd = price * size * 100
source_premium_usd = sum(row_premium_usd over all source-valid rows)
```

A row has a **valid measured NBBO** iff all are true:

```text
price > 0
size > 0
bid > 0
ask > bid                 # locked/crossed is uncovered for execution-location purposes
trade_timestamp parseable
quote_timestamp parseable
quote_timestamp <= trade_timestamp
```

Do not add an arbitrary quote-age cutoff in this wave. The ThetaData endpoint supplies the last NBBO at trade time; preserve `quote_age_ms` so a later governed consumer can set a freshness rule if research warrants one.

### Exact execution-location categories

For NBBO-valid rows, classify using direct `price` vs `bid`/`ask`, never `sign`:

```text
AT_ASK:  price is equal to ask under rtol=0, atol=1e-9
AT_BID:  price is equal to bid under rtol=0, atol=1e-9
INSIDE:  bid < price < ask and neither edge equality holds
OUTSIDE: price > ask or price < bid
```

The four categories must be mutually exclusive and collectively exhaustive over NBBO-valid premium.

### Event microstructure object

Each qualifying live event receives:

```json
{
  "microstructure": {
    "schema": "options.trade_nbbo_microstructure/v1",
    "source_print_count": 0,
    "nbbo_valid_print_count": 0,
    "source_premium_usd": 0.0,
    "nbbo_covered_premium_usd": 0.0,
    "nbbo_print_coverage": null,
    "nbbo_premium_coverage": null,
    "at_ask_share": null,
    "at_bid_share": null,
    "inside_share": null,
    "outside_share": null,
    "aggression_share": null,
    "aggression_balance": null,
    "spread_median_usd": null,
    "spread_median_pct": null,
    "quote_age_median_ms": null,
    "quote_age_max_ms": null,
    "bid_size_median": null,
    "ask_size_median": null
  }
}
```

Definitions:

```text
nbbo_print_coverage       = nbbo_valid_print_count / source_print_count
nbbo_premium_coverage     = nbbo_covered_premium_usd / source_premium_usd
at_ask_share              = AT_ASK premium / nbbo_covered_premium_usd
at_bid_share              = AT_BID premium / nbbo_covered_premium_usd
inside_share              = INSIDE premium / nbbo_covered_premium_usd
outside_share             = OUTSIDE premium / nbbo_covered_premium_usd
aggression_share          = at_ask_share + at_bid_share
aggression_balance        = at_ask_share - at_bid_share
spread_usd                = ask - bid
spread_pct                = (ask - bid) / ((ask + bid) / 2)
quote_age_ms              = trade_timestamp - quote_timestamp
```

Share fields use the **covered-premium denominator**, not total source premium. Coverage fields disclose how much source premium/print count supports those shares. Ratios are rounded only at the published event boundary (6 decimals for shares/percent ratios; 2 decimals for premium dollars; 3 decimals for millisecond/size/spread summaries is sufficient). Arithmetic tests, not comments, are the authority.

`bid_size_median` and `ask_size_median` use finite non-negative vendor size rows among NBBO-valid observations; null if no finite size exists.

### `vol_gt_oi_ratio`

Extend the existing `_enrich_contract_row()` result with:

```text
vol_gt_oi_ratio = cumulative_day_contract_volume / exact matched prior OI
```

only when the matched prior OI is finite and strictly positive. OI absent, malformed, negative, or zero => `vol_gt_oi_ratio = null`. Existing `vol_gt_oi` semantics remain unchanged, and `oi_vintage` remains required provenance when the boolean/ratio is populated.

---

## Task 0: Re-pin, collision-check, and prove additive-event compatibility before writing code

**Files:** read-only census first; no file mutation in this task.

- [ ] Re-fetch protected Skillpack and current Macro `main`; record exact SHA in the implementation PR body.
- [ ] Confirm the implementation base contains the accepted OA-0 spec/decision/workstream from #6573.
- [ ] Re-run open-PR/path collision census for these expected paths:

```text
engine/live_flow.py
collectors/flow_signals.py
scripts/live_flow_poller.py
tests/test_live_flow.py
tests/test_flow_signals.py
tests/test_options_signal_episode.py
scripts/ops_train_flow_score.py
tests/test_fs4_flow_scorer.py
ops/LIVE_FLOW_RUNBOOK.md
```

- [ ] Search every event-stage consumer and exact-event-shape validator:

```bash
rg -n 'live_flow\.event_stage/v1|EVENT_STAGE_SCHEMA|_prepare_event_stage_batch|_parse_event_stage_bytes|source_event_id|episode_from_live_event' \
  scripts engine collectors tests
rg -n 'set\(.*event|event\.keys\(|set\(record\)|root_not_object|unexpected.*event|additionalProperties' \
  scripts engine collectors contracts tests
```

- [ ] Explicitly inspect at least:

```text
scripts/live_flow_poller.py
scripts/build_options_signal_episode.py
engine/options_signal_episode.py
engine/neuralweb/market_memory_options_episode_capture.py
collectors/flow_signals.py
```

- [ ] Confirm current `collectors/thetadata.py::bulk_trade_quote` still exposes `trade_timestamp`, `quote_timestamp`, `price`, `size`, `bid`, `ask`, `bid_size`, and `ask_size` on the existing paid v3 path. Do not add a new vendor request.
- [ ] Confirm current `engine/live_flow.py` still filters source identity/RTH/sequence before `_sign_batch()` and that `_sign_batch()` can drop quote-unusable rows. This distinction is load-bearing because coverage must be measured before the latter filter.

**Stop condition:** if any current accepted consumer rejects an additive nested event field, or a concurrent PR owns the same engine/collector paths, do not start Task 1. Return exact path/PR/validator evidence to Sol.

**No commit for Task 0.** Record the census in the eventual PR body and handoff.

---

## Task 1: TDD the direct trade-vs-NBBO measurement helper

**Files:**
- Modify: `engine/live_flow.py`
- Modify: `tests/test_live_flow.py`

### Step 1.1 — Write RED tests for the four execution locations

- [ ] Add a fixture helper that can independently set `price`, `bid`, `ask`, `trade_timestamp`, `quote_timestamp`, `bid_size`, `ask_size`, `size`, and `sequence` while preserving current source-valid identity fields.
- [ ] Add `test_nbbo_microstructure_uses_direct_execution_location_not_sign_fallback`.

Use one exact contract with equal size and three causal quote rows:

```python
rows = [
    # at ask: premium = 4 * 1 * 100 = 400
    trade(price=4.0, bid=2.0, ask=4.0, sequence=1,
          trade_timestamp="2026-08-28 10:00:00.100",
          quote_timestamp="2026-08-28 10:00:00.000"),
    # at bid: premium = 2 * 1 * 100 = 200
    trade(price=2.0, bid=2.0, ask=4.0, sequence=2,
          trade_timestamp="2026-08-28 10:00:01.100",
          quote_timestamp="2026-08-28 10:00:01.000"),
    # inside/mid: premium = 3 * 1 * 100 = 300
    # Existing quote-rule/tick fallback may assign a sign; measurement must still say INSIDE.
    trade(price=3.0, bid=2.0, ask=4.0, sequence=3,
          trade_timestamp="2026-08-28 10:00:02.100",
          quote_timestamp="2026-08-28 10:00:02.000"),
]
```

Expected covered-premium shares:

```python
assert micro["at_ask_share"] == pytest.approx(400 / 900)
assert micro["at_bid_share"] == pytest.approx(200 / 900)
assert micro["inside_share"] == pytest.approx(300 / 900)
assert micro["outside_share"] == 0.0
assert micro["aggression_share"] == pytest.approx(600 / 900)
assert micro["aggression_balance"] == pytest.approx(200 / 900)
```

- [ ] Add `test_nbbo_microstructure_classifies_outside_without_calling_it_aggression` with one `price > ask` and one `price < bid`; expected `outside_share == 1.0`, edge shares zero.
- [ ] Run only the new tests and capture RED:

```bash
python3 -m pytest tests/test_live_flow.py -q -k 'nbbo_microstructure'
```

Expected RED: helper/field absent, not an unrelated fixture error.

### Step 1.2 — Write RED tests for coverage, causal quote clocks, and locked/crossed quotes

- [ ] Add `test_nbbo_microstructure_coverage_denominator_includes_source_valid_quote_gaps`:
  - one valid-NBBO row;
  - one source-valid row with missing bid/ask;
  - verify `source_premium_usd` includes both while covered premium includes only the first.
- [ ] Add `test_nbbo_microstructure_future_quote_is_uncovered` (`quote_timestamp > trade_timestamp`).
- [ ] Add `test_nbbo_microstructure_locked_and_crossed_quotes_are_uncovered` (`ask <= bid`).
- [ ] Add `test_nbbo_microstructure_preserves_quote_age_spread_and_sizes` with known ages/spreads/sizes and exact medians.
- [ ] Run RED:

```bash
python3 -m pytest tests/test_live_flow.py -q -k 'nbbo_microstructure'
```

### Step 1.3 — Implement the smallest pure helper in `engine/live_flow.py`

- [ ] Add constants near the existing signing/coalescing constants:

```python
MICROSTRUCTURE_SCHEMA = "options.trade_nbbo_microstructure/v1"
_EXECUTION_LOCATION_ATOL = 1e-9
```

- [ ] Add a pure helper with no clock reads and no state mutation, e.g.:

```python
def _coalesce_nbbo_microstructure(df: pd.DataFrame) -> dict[tuple[str, float, str], dict]:
    """Measure direct trade-vs-NBBO facts on source-valid, sequence-deduped rows.

    This is independent of soft/tick/quote signing. It never asserts initiator identity.
    """
```

Implementation requirements:

1. Return `{}` on empty frame.
2. Normalize exact contract key to `(YYYY-MM-DD expiration, float strike, C|P)`.
3. Compute source premium before any NBBO-valid filtering.
4. Parse trade and quote clocks using existing ThetaData/source-time helpers; never `datetime.now()`.
5. Require strict positive spread (`ask > bid`) for covered execution-location evidence.
6. Classify direct price location with `np.isclose(..., rtol=0, atol=1e-9)` only for exact edge equality.
7. Derive all shares from covered premium.
8. Set every unsupported field to `None`; never NaN/Infinity.
9. Return strict finite JSON-compatible values.

- [ ] Run GREEN:

```bash
python3 -m pytest tests/test_live_flow.py -q -k 'nbbo_microstructure'
```

- [ ] Run the existing signing/coalescing regressions so the new direct measurement did not change `side`:

```bash
python3 -m pytest tests/test_live_flow.py -q -k 'sign or coalesc or side or sequence'
```

### Step 1.4 — Commit Task 1

```bash
git add engine/live_flow.py tests/test_live_flow.py
git commit -m "feat(options): measure direct trade NBBO microstructure"
```

---

## Task 2: Attach measured microstructure and PIT vol/OI ratio without changing event selection or identity

**Files:**
- Modify: `engine/live_flow.py`
- Modify: `tests/test_live_flow.py`

### Step 2.1 — RED: prove invalid NBBO affects coverage but not the existing event-selection basis

- [ ] Add `test_event_microstructure_uses_pre_sign_source_rows_without_changing_event_floor`.

Construct one contract with:
- valid NBBO premium sufficient to cross the current single-name floor;
- a second source-valid row with missing/invalid NBBO;
- expected event still forms under the **existing** filtered/signable selection behavior;
- expected `nbbo_premium_coverage < 1.0` because the raw source-valid denominator sees both rows.

This test discriminates the implementation location: computing microstructure after `_sign_batch()` would incorrectly produce 100% coverage and must fail.

- [ ] Add `test_event_id_is_unchanged_by_microstructure_attachment` that recomputes the expected current `_event_id(...)` and proves the added block does not participate in identity.
- [ ] Add `test_existing_side_and_signing_source_remain_soft_and_unchanged`.
- [ ] Run RED:

```bash
python3 -m pytest tests/test_live_flow.py -q -k 'event_microstructure or unchanged_by_microstructure or signing_source_remain'
```

### Step 2.2 — Implement pre-sign measurement join

- [ ] In `process_batch()`, after source/RTH/sequence filtering has finished and **immediately before**:

```python
combined = _sign_batch(combined)
```

capture the source-valid frame and derive the contract map:

```python
microstructure_by_contract = _coalesce_nbbo_microstructure(combined)
combined = _sign_batch(combined)
```

Do not move existing `seen_sequences` advancement or selection logic.

- [ ] During event construction, look up the exact `(exp_str, strike, right)` key and attach:

```python
"microstructure": microstructure_by_contract.get(contract_key_for_measurement)
```

Every emitted event should have the block when source rows existed. If lookup fails despite an emitted event, fail closed in the pure engine (raise) rather than publish a plausible empty block; that mismatch is an internal identity defect.

### Step 2.3 — RED/GREEN `vol_gt_oi_ratio`

- [ ] Add tests:

```text
test_vol_gt_oi_ratio_uses_cumulative_day_volume_and_exact_prior_oi
test_vol_gt_oi_ratio_null_when_oi_missing
test_vol_gt_oi_ratio_null_when_prior_oi_zero
test_vol_gt_oi_ratio_does_not_change_vol_gt_oi_boolean
```

For `prior_oi=100` and cumulative day volume `150`, expect ratio `1.5` and `vol_gt_oi is True`.

- [ ] Extend `_enrich_contract_row()` with `vol_gt_oi_ratio` using the same exact matched contract and cumulative day volume already used by `vol_gt_oi`.
- [ ] Attach top-level event field:

```python
"vol_gt_oi_ratio": enrich["vol_gt_oi_ratio"],
```

Keep `oi_vintage` untouched.

- [ ] Run targeted GREEN:

```bash
python3 -m pytest tests/test_live_flow.py -q -k 'microstructure or vol_gt_oi'
```

- [ ] Run full live-flow tests:

```bash
python3 -m pytest tests/test_live_flow.py -q
```

### Step 2.4 — Commit Task 2

```bash
git add engine/live_flow.py tests/test_live_flow.py
git commit -m "feat(options): bind NBBO evidence to live flow events"
```

---

## Task 3: Prove the durable event stage accepts the additive block while `options.signal_episode/v1` stays frozen

**Files:**
- Modify: `tests/test_options_signal_episode.py`
- Modify only if a genuine compatibility bug is found: `scripts/live_flow_poller.py`
- **Do not modify:** `contracts/options/options.signal_episode.v1.schema.json`, episode/campaign identity code, or historical ledgers.

### Step 3.1 — RED/compatibility test for event-stage round trip

- [ ] Extend the test `_event()` fixture with an optional `microstructure` block matching the frozen schema and a top-level `vol_gt_oi_ratio`.
- [ ] Add a test that sends an event with those fields through the poller's existing preparation/staging parser and proves the decision receipt preserves the nested object byte-for-semantic-value while availability remains a separate receipt.

The assertion should prove:

```python
assert staged_event["microstructure"] == source_event["microstructure"]
assert staged_event["vol_gt_oi_ratio"] == source_event["vol_gt_oi_ratio"]
assert staged_event["id"] == source_event["id"]
assert staged_event["available_at"] == sampled_availability
```

- [ ] Prove replay idempotency: same event ID + same causal payload + later processing clock may reuse the first durable clocks, but changing a microstructure value behind the same staged event ID must trigger the existing `staged event drift` failure.

Run:

```bash
python3 -m pytest tests/test_options_signal_episode.py -q -k 'event_stage and microstructure'
```

If the current consumer rejects additive nested fields, **STOP THE WAVE** per Task 0. Do not patch around it.

### Step 3.2 — Prove v1 episode identity/schema remain unchanged

- [ ] Add `test_episode_v1_ignores_additive_source_microstructure_without_identity_drift`:

```python
base = _event(microstructure=None, vol_gt_oi_ratio=None)
rich = _event(microstructure=MICRO_FIXTURE, vol_gt_oi_ratio=1.5)
base_episode = episode_from_live_event(base, source_snapshot_asof=base["available_at"])
rich_episode = episode_from_live_event(rich, source_snapshot_asof=rich["available_at"])
assert rich_episode["episode_id"] == base_episode["episode_id"]
assert rich_episode["schema"] == "options.signal_episode/v1"
validate_episode(rich_episode)
assert "microstructure" not in rich_episode["feature_snapshot"]
assert "vol_gt_oi_ratio" not in rich_episode["feature_snapshot"]
```

If current `episode_from_live_event()` derives another source digest that legitimately changes because the full upstream event bytes are committed, assert **stable episode ID + unchanged v1 field contract** instead of whole-row equality. Do not change the v1 identity function.

- [ ] Run the full episode/campaign suite:

```bash
python3 -m pytest tests/test_options_signal_episode.py -q
```

### Step 3.3 — Commit Task 3 tests (and only narrowly necessary staging compatibility code)

```bash
git add tests/test_options_signal_episode.py scripts/live_flow_poller.py
git commit -m "test(options): prove microstructure PIT stage compatibility"
```

If `scripts/live_flow_poller.py` did not require a code change, omit it from `git add`.

---

## Task 4: Flatten measured fields into the existing keep-first Flow ML ledger

**Files:**
- Modify: `collectors/flow_signals.py`
- Modify: `tests/test_flow_signals.py`

### Step 4.1 — RED: define the additive ledger contract

- [ ] Extend `_make_event()` in `tests/test_flow_signals.py` to optionally include:

```python
"vol_gt_oi_ratio": 1.5,
"microstructure": {
    "schema": "options.trade_nbbo_microstructure/v1",
    "source_print_count": 4,
    "nbbo_valid_print_count": 3,
    "source_premium_usd": 1_000_000.0,
    "nbbo_covered_premium_usd": 900_000.0,
    "nbbo_print_coverage": 0.75,
    "nbbo_premium_coverage": 0.9,
    "at_ask_share": 0.6,
    "at_bid_share": 0.2,
    "inside_share": 0.15,
    "outside_share": 0.05,
    "aggression_share": 0.8,
    "aggression_balance": 0.4,
    "spread_median_usd": 0.05,
    "spread_median_pct": 0.02,
    "quote_age_median_ms": 110.0,
    "quote_age_max_ms": 250.0,
    "bid_size_median": 40.0,
    "ask_size_median": 45.0,
}
```

- [ ] Add `test_event_microstructure_flattens_into_flow_ml_ledger_row` asserting exact flat values.
- [ ] Add `test_legacy_event_without_microstructure_yields_null_additive_columns`.
- [ ] Add `test_unknown_microstructure_schema_is_not_trusted` — wrong schema yields null measured fields rather than parsing values under an unreviewed contract.
- [ ] Run RED:

```bash
python3 -m pytest tests/test_flow_signals.py -q -k 'microstructure or additive_columns'
```

### Step 4.2 — Implement additive columns

- [ ] Add these columns to `_EVENT_COLS` without removing/reordering legacy semantic names unnecessarily:

```text
vol_gt_oi_ratio
microstructure_schema
source_print_count
nbbo_valid_print_count
source_premium_usd
nbbo_covered_premium_usd
nbbo_print_coverage
nbbo_premium_coverage
at_ask_share
at_bid_share
inside_share
outside_share
aggression_share
aggression_balance
spread_median_usd
spread_median_pct
quote_age_median_ms
quote_age_max_ms
bid_size_median
ask_size_median
```

- [ ] In `_events_from_blob()`, trust the nested object only when:

```python
isinstance(micro, dict) and micro.get("schema") == "options.trade_nbbo_microstructure/v1"
```

otherwise flatten nulls.

- [ ] Use existing `_coerce_float/_coerce_int`; never turn missing into `0`.
- [ ] Persist top-level `vol_gt_oi_ratio` separately.

### Step 4.3 — RED/GREEN schema-evolution and keep-first tests

- [ ] Add `test_existing_parquet_rows_receive_null_new_columns_on_append`:
  1. write a legacy-format DataFrame without the new columns;
  2. append one rich new row;
  3. assert old event row remains first and new columns are null for old row;
  4. assert rich row has measured values.

- [ ] Add `test_reharvest_cannot_mutate_first_microstructure_values`:
  1. ingest `event_id=X` with `at_ask_share=0.60`;
  2. reharvest same event ID with `0.99`;
  3. ledger must still contain one row with `0.60`.

- [ ] Run:

```bash
python3 -m pytest tests/test_flow_signals.py -q -k 'microstructure or keep_first or existing_parquet'
python3 -m pytest tests/test_flow_signals.py -q
```

### Step 4.4 — Commit Task 4

```bash
git add collectors/flow_signals.py tests/test_flow_signals.py
git commit -m "feat(options): persist measured microstructure in flow ML ledger"
```

---

## Task 5: Prevent FS-4 from mistaking an all-null live measured feature set for a valid serving cohort

**Files:**
- Modify: `scripts/ops_train_flow_score.py`
- Modify: `tests/test_fs4_flow_scorer.py`
- **Do not modify:** `config/flow_score.yml` scoring kill switch or model target/hyperparameters.

### Step 5.1 — RED: all-null live measured features must halt the ops trainer

The current feature builder deliberately fills missing columns with NaN. That is useful for sparse observations but dangerous if an entire serving cohort lacks the very measurements this wave is meant to supply.

- [ ] Add a small pure preflight helper test for current configured measured fields:

```python
MEASURED_LIVE_FIELDS = (
    "at_ask_share",
    "at_bid_share",
    "aggression_share",
    "vol_gt_oi_ratio",
)
```

- [ ] Add `test_live_feed_preflight_rejects_all_null_measured_features`.
- [ ] Add `test_live_feed_preflight_accepts_mixed_historical_nulls_once_real_measured_rows_exist` — old rows may remain null; at least one real `live_feed` row per required field is enough for this structural preflight. **Do not invent an N/pct promotion threshold in OA-1T.** FS-5 owns adequacy.
- [ ] Add `test_tape_recon_only_training_is_not_redefined_by_live_feed_schema_guard` so this wave does not silently change the legal role of other registered cohorts.

Run RED:

```bash
python3 -m pytest tests/test_fs4_flow_scorer.py -q -k 'measured_feature or preflight'
```

### Step 5.2 — Implement a structural, not statistical, preflight

- [ ] Add a helper such as:

```python
def _assert_live_feed_measured_features(df: pd.DataFrame, feature_cols: list[str]) -> None:
    live = df[df["source"] == "live_feed"] if "source" in df.columns else pd.DataFrame()
    if live.empty:
        return
    required = [name for name in MEASURED_LIVE_FIELDS if name in feature_cols]
    missing = [name for name in required if name not in live.columns]
    all_null = [name for name in required if name in live.columns and live[name].notna().sum() == 0]
    if missing or all_null:
        raise ValueError(
            "ops_train: live_feed measured feature preflight failed "
            f"missing={missing} all_null={all_null}"
        )
```

- [ ] Call it after serving-cohort loading/population filtering and before model feature construction.
- [ ] Do **not** require a minimum percentage, AUC, ECE, sample N, or performance threshold here. This is only a truth-presence guard.
- [ ] Do **not** enable scoring or produce a gate verdict.

- [ ] Run GREEN plus current scorer suite:

```bash
python3 -m pytest tests/test_fs4_flow_scorer.py -q
```

- [ ] Prove the kill switch remains off:

```bash
python3 - <<'PY'
import yaml
cfg = yaml.safe_load(open('config/flow_score.yml'))
assert cfg['scoring']['enabled'] is False
print('scoring.enabled=false')
PY
```

### Step 5.3 — Commit Task 5

```bash
git add scripts/ops_train_flow_score.py tests/test_fs4_flow_scorer.py
git commit -m "guard(options): require real measured live flow features"
```

---

## Task 6: Add operator proof instructions without creating a new runtime or proof store

**Files:**
- Modify: `ops/LIVE_FLOW_RUNBOOK.md`

### Step 6.1 — Document the OA-1T natural-RTH proof packet

- [ ] Add one bounded section titled `OA-1T measured microstructure production proof` that explicitly says:
  - run only on a normal current NYSE session;
  - do not use historical `--once --date`;
  - do not re-arm the retired Studio fleet;
  - inspect the existing date-keyed event stage/R2 output and existing Flow ML ledger;
  - the proof is observational except for the already-scheduled canonical writers.

- [ ] Require the proof packet to capture:

```text
production checkout SHA / running producer identity
session date
one untouched natural event_id
event ts / observed_at / decision_at / available_at
microstructure.schema
source_print_count / nbbo_valid_print_count
nbbo_print_coverage / nbbo_premium_coverage
at_ask / at_bid / inside / outside shares
aggression_share / aggression_balance
spread and quote-age summaries
vol_gt_oi / vol_gt_oi_ratio / oi_vintage
matching Flow ML ledger event_id and flattened values
matching options.signal_episode/v1 source_event_id after normal nightly advance, if the event is eligible
flow_score.yml scoring.enabled=false
flow_signals.gate/v2 scored=false and scoring.enabled=false
```

- [ ] Explicitly state that a missing natural notable event is **not a failure and must not be manufactured**. The production proof remains pending until a normal event occurs.

### Step 6.2 — Commit runbook

```bash
git add ops/LIVE_FLOW_RUNBOOK.md
git commit -m "docs(options): define natural RTH microstructure proof"
```

---

## Task 7: Full verification and worker return — stop before merge/deploy/proof manufacturing

**Files:** no new scope.

### Step 7.1 — Run focused suites

- [ ] Run:

```bash
python3 -m pytest tests/test_live_flow.py -q
python3 -m pytest tests/test_flow_signals.py -q
python3 -m pytest tests/test_options_signal_episode.py -q
python3 -m pytest tests/test_fs4_flow_scorer.py -q
```

- [ ] Run import/compile smoke:

```bash
python3 -m py_compile \
  engine/live_flow.py \
  collectors/flow_signals.py \
  scripts/live_flow_poller.py \
  scripts/ops_train_flow_score.py
```

- [ ] Run event-stage/poller import smoke only; **never historical production mutation**:

```bash
python3 -m scripts.live_flow_poller --help >/dev/null
```

- [ ] Run Agent OS validation if the implementation PR touches any Agent OS record during reconciliation; otherwise do not add an Agent OS mutation merely to make the PR look complete.

### Step 7.2 — Required invariants scan

- [ ] Prove no new collector/scheduler/store/authority path entered the diff:

```bash
git diff --name-only <CURRENT_BASE>...HEAD
rg -n 'scoring:\s*\n\s*enabled:\s*true|may_trade.:\s*true|may_rank.:\s*true|may_gate.:\s*true|may_size.:\s*true' \
  config engine collectors scripts tests ops || true
```

- [ ] Inspect diff specifically for:

```text
_event_id unchanged
selection_rule remains premium_floor/v1
EVENT_STAGE_SCHEMA remains live_flow.event_stage/v1
EPISODE_SCHEMA remains options.signal_episode/v1
no episode/campaign schema file edit
no DNR edit
no launchd/workflow edit
no R2 key/prefix addition
no model artifact or score ledger write
```

### Step 7.3 — Exact-head hosted CI

- [ ] Push the implementation branch and open **one** PR for OA-1T-Macro only.
- [ ] Keep later OA-1T-Terminal/OA-1C/OA-2/OA-3/OA-4/OA-5 out of the PR.
- [ ] Obtain exact-head fences/CI. If current CI requires a trusted self-hosted pack, wait for the exact-head result; do not cite an older green run.

### Step 7.4 — Return to Sol before merge

The worker stops and returns this exact packet:

```text
implementation base SHA
final head SHA
PR number
changed files
focused test commands + results
exact-head fences/CI run IDs + conclusions
consumer census and any hard-enumeration findings
proof that event identity/selection/episode v1/scoring kill switch are unchanged
all new microstructure field semantics
any source rows/edge cases discovered that differ from the plan
production proof status: NOT YET RUN / naturally observed receipt
remaining gate: Sol adversarial PR review, merge, then natural RTH proof
```

**Stop condition:** do not merge the PR, restart services, run a historical flow replay, manually append a Flow ML row, enable scoring, create a Terminal UI change, create a candidate feed, or begin OA-1C/OA-2. Those are outside this plan.

---

## Post-merge acceptance owned by Sol/operator, not the implementation worker

After Sol accepts and merges OA-1T-Macro, implementation state is **BUILT_NOT_PROVEN** until the natural current-session packet from Task 6 exists.

OA-1T-Macro becomes `PROVEN_LIVE` only when one untouched RTH event proves the real chain:

```text
canonical ThetaData trade_quote
-> existing live-flow producer
-> stable existing event_id
-> options.trade_nbbo_microstructure/v1 in the durable date-keyed event stage
-> same event_id flattened into the normal Flow ML ledger advance
-> existing episode v1 consumer continues without contract drift
-> scoring remains disabled / no authority promotion
```

If no notable event occurs during the first post-merge session, remain `BUILT_NOT_PROVEN`; do not lower the premium floor or manufacture a fixture in production merely to close the proof.

## Explicit continuation boundary

Only after OA-1T-Macro is accepted/proven may Sol independently commission:

- **OA-1T-Terminal** — render measured evidence and rename the browser heuristic to Attention/Salience; or
- **OA-1C-Macro** — only after its additional AD-1T2 + formation-preregistration gates clear.

This plan grants neither commission automatically.
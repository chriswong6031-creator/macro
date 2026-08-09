# CN limit-move alpha — Wave-2 band-progress substrate receipt

**Date:** 2026-08-08
**Authority:** none_research_display_context_only
**Status:** `BLOCKED_SUBSTRATE`
**Verdict:** `BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT`

## Outcome

The construction grammar is frozen, but no strategy measurement is admissible yet. The historical Yahoo plane remains split-adjusted and cannot reconstruct legal CNY 0.01 limit prices. The adapter now binds to the canonical full-A v1 event plane and manifest, but it does not invent missing rule/lifecycle fields. No transition, return, fill, or strategy metric appears in this receipt.

Exact blocker: the b2548fdc095 v1 contract is a schema-shape snapshot only and is pending a remediated promoted spine authority; the selected spine partitions, references, coverage, or pinned-schema complete manifest are absent/incomplete; event_daily lacks frozen measurement eligibility/rule fields: corporate_action_reference_known, ipo_no_limit_state_known, no_limit, rule_cohort, session_eligible, st_membership_state, st_provenance; snapshot v1 cannot prove that every input hash belongs to one promoted generation; consumer-side row re-attestation has not run.

## Pre-measurement contract corrections

These corrections were recorded before any Wave-2 outcome, transition, return, fill, or strategy measurement. They bind the packet to the canonical v1 store and replace defensive comparisons with exact bounded integer-cent event predicates; no return-led threshold tuning occurred.

- Strict legal seal: `close_cents == up_limit_cents` after full OHLC bound validation.
- Exact upper touch: `high_cents == up_limit_cents` after full OHLC bound validation.
- Any event-eligible OHLC outside `[down_limit_cents, up_limit_cents]` is quarantined without a signal classification.

## Authoritative input gates

| Plane | Exists | Schema pass | Missing columns / contract |
|---|---:|---:|---|
| `tushare_unadjusted_daily` | false | false | board, close_cents, exchange, high_cents, low_cents, market_session_position, open_cents, positive_volume, pre_close_cents, price_source_basis, security_id, source_ts_code, ticker, trade_date, volume_lots |
| `tushare_vendor_stk_limit` | false | false | board, down_limit_cents, exchange, limit_price_source, market_session_position, pre_close_cents, security_id, source_limits_present, source_ts_code, ticker, trade_date, up_limit_cents |
| `canonical_event_daily` | false | false | board, calculated_limit_role, close_cents, down_limit_cents, event_eligible, event_price_authority, exchange, high_cents, limit_pre_close_cents, low_cents, market_session_position, open_cents, positive_volume, pre_close_cents, sealed_down, sealed_up, security_id, source_limits_present, source_ts_code, ticker, touched_down, touched_up, trade_date, up_limit_cents, volume_lots |
| `attested_market_sessions` | false | false | bse_calendar_provenance, calendar_provenance, market_session_position, trade_date |
| `effective_dated_security_master` | false | false | board, delist_date, effective_from, effective_to, exchange, list_date, list_status, security_id, source_ts_code, ticker |
| `exact_daily_stock_st_from_2016` | false | false | is_st, security_id, st_provenance, ticker, trade_date |
| `daily_security_coverage` | false | false | daily_n, eligible_n, positive_volume_n, suspended_n, trade_date, unexpected_daily_n, unexplained_missing_n |

## Manifest and measurement overlay

- Spine shape-snapshot commit: `b2548fdc095`
- Snapshot status: `SHAPE_ONLY_NO_READINESS_AUTHORITY_PENDING_REMEDIATION`
- Snapshot has readiness authority: **false**
- Partition contract: `{daily,stk_limit,event_daily}/year=YYYY/month=MM/part.parquet`
- One-root layout binding passes: **true**
- Manifest exists / schema-valid / identity-valid / passes: **false / false / false / false**
- Canonical schemas pass: **false**
- Measurement-overlay pass: **false**
- Missing overlay fields: **corporate_action_reference_known, ipo_no_limit_state_known, no_limit, rule_cohort, session_eligible, st_membership_state, st_provenance**
- Single promoted-generation binding passes: **false**
- Contract ready for row re-attestation / measurement ready: **false / false**

Row-level uniqueness, join, exact-cent equality, OHLC bound, corporate-action, and exact-exit-clock gates remain pending even if the file schemas appear.

## Frozen definitions

- Strict seal: integer-cent close equals vendor `stk_limit.up_limit_cents` exactly.
- Tolerant-only close: inside the 0.2% cushion but below the legal ceiling; sensitivity only.
- Exact-touch failure: integer-cent daily high equals the vendor ceiling and close finishes below it.
- Partial no-touch: high remains below the ceiling, with parallel fixed high-progress and close-progress buckets at 0.40/0.60/0.80/0.95.
- Entry: D-close information to D+1 reported-open `daily_tradability_proxy`; upper queue and missing rows remain cash zero.
- Earliest exit: D+2 under A-share T+1; daily bars cannot claim intraday sequence or fill.

## Legacy-plane diagnostic

Status: `audited_invalid_plane`; authority: `SUBSTRATE_INVALID_DIAGNOSTIC_ONLY`.

- Files read / discovered: **1,841 / 1,842**
- Stored rows: **6,760,225**
- Prior closes checked: **6,758,384**
- Eligible prior closes not exactly cent-valued at CNY 1e-9: **6,254,390 / 6,480,328**
- Eligible prior closes materially off tick by more than CNY 1e-05: **2,732,956**
- Half-up versus legacy upper-price differences: **23,322**
- Strict-seal key additions/removals under half-up: **0 / 161**
- Exact-touch key additions/removals under half-up: **0 / 263**

These are detector-engineering counts on an invalid substrate, not market findings.

## UNTESTED VARIANTS

- first-touch, first-seal, last-seal, break/reseal, sealed duration, and path order
- wall growth, depletion, replenishment, cancellation, queue rank, partial fills, and signed flow
- opening-auction imbalance and post-09:25 decisions with true 09:30 execution
- early failed-seal absorption versus late demand exhaustion
- closing-auction-only seals and post-close fixed-price execution
- upper-then-lower versus lower-then-upper intraday traversal
- multi-step cadence words and flexible 3/5/10-session first-passage paths
- T+1 inventory vintages, volume-at-price, free float, unlocks, and queue elasticity
- PIT theme topology, spectator substitution, and failed-leader redistribution
- ladder topology, hysteresis, and regime interactions
- availability-safe LHB, block sponsorship, and catalyst classes
- full-universe delisted-name, historical ST, IPO, suspension, and corporate-action truth
- board-local nonlinear models, threshold/cash portfolios, and nested confirmation
- live fees, slippage, rejection, capacity, sector caps, and mark-to-market drawdown
- at least ten prospective graded sessions and every authority-promotion gauntlet

## Next action

land a remediated full-A TuShare spine contract with one promoted-generation identity, materialize the missing rule/lifecycle eligibility overlay without inference, pin the new schema/commit, re-attest every row-level gate, then execute the deterministic measurement.

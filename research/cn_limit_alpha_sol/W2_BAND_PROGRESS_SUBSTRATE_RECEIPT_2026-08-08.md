# CN limit-move alpha — Wave-2 band-progress substrate receipt

**Date:** 2026-08-08
**Authority:** none_research_display_context_only
**Status:** `BLOCKED_SUBSTRATE`
**Verdict:** `BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT`

## Outcome

The construction grammar is frozen, but no strategy measurement is admissible yet. The historical Yahoo plane remains split-adjusted and cannot reconstruct legal CNY 0.01 limit prices. No transition, return, fill, or strategy metric appears in this receipt.

Exact blocker: authoritative TuShare daily + stk_limit + calendar + security-session inputs are absent or incomplete.

## Authoritative input gates

| Plane | Exists | Schema pass | Missing columns / contract |
|---|---:|---:|---|
| `tushare_unadjusted_daily` | false | false | close, high, low, open, pre_close, trade_date, ts_code, vol |
| `tushare_vendor_stk_limit` | false | false | down_limit, trade_date, ts_code, up_limit |
| `official_trade_calendar` | false | false | — |
| `effective_dated_security_sessions` | false | false | board, corporate_action_reference_known, no_limit, rule_cohort, rule_known, session_eligible |

Row-level uniqueness, join, tick, limit-ordering, corporate-action, and exact-exit-clock gates remain pending even if the file schemas appear.

## Frozen definitions

- Strict seal: close at or above vendor `stk_limit.up_limit`.
- Tolerant-only close: inside the 0.2% cushion but below the legal ceiling; sensitivity only.
- Exact-touch failure: daily high reaches the vendor ceiling and close finishes below it.
- Partial no-touch: high remains below the ceiling, with parallel fixed high-progress and close-progress buckets at 0.40/0.60/0.80/0.95.
- Entry: D-close information to D+1 official-open `daily_tradability_proxy`; upper queue and missing rows remain cash zero.
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

bind this frozen taxonomy to the committed full-A TuShare daily/stk_limit/security-session spine, run every row-level gate, then implement and execute the deterministic measurement.

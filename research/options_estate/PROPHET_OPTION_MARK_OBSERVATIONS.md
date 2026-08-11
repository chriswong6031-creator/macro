# Prophet exact-option mark observations

Status: prospective evidence only. First publication is the start of the clock; no history is reconstructed.

## Claim boundary

The existing Prophet plan stores an exact OCC contract and an EOD entry mark. During NYSE regular hours, the marks publisher can observe a bounded-age ThetaData `trade_quote` vendor snapshot for that same identity. The lawful measurement is therefore a **mark change from the plan's EOD mid to the observed vendor-snapshot mid**.

It is not trade P&L. No position or fill is assumed, including when a plan is still pre-trigger. The source does not provide the size, venue, or condition receipt needed to claim NBBO, live, current, executable, or capacity semantics. Every authority flag is false; the artifact cannot rank, gate, size, issue, train, trade, or steer Prophet or Neural Web.

## Frozen construction

- Contract identity: exact OCC root, expiry, right, and millistrike from the canonical published `prophet.index/v1` plan.
- Entry basis: `option_contract.entry_premium` only when the plan explicitly labels
  `freshness="EOD mark"`; an absent or different basis abstains from mark change.
- Observation basis: midpoint of a same-session vendor-snapshot bid/ask, observed no more than 30 minutes after its source timestamp.
- Coverage: every open plan carrying `option_contract` produces one row. Invalid identity, expired contract, missing source, malformed quote, future quote, wrong-session quote, and over-age quote are explicit abstentions.
- Lifecycle: `pre_trigger` is `watch_only_pre_trigger`; all other open phases are `display_plan_active`. Both state `position_assumed=false` and `trade_pnl_claim=false`.
- Durability: each observation is canonical JSON, content-addressed, immutable in R2, and linked to the verified predecessor. The mutable live-marks object advances only after the immutable observation reads back byte-for-byte.

Schema: `contracts/options/prophet.option_mark_observation.v1.schema.json`.

R2 discovery head: `live_flow/prophet_marks.json` → `evidence`.

Immutable prefix: `prophet/option_mark_observations/v1/<session>/<observation_id>.json`.

## Promotion fence

This observation chain may support future option-lifecycle measurement after prospective sample accrual. It does not populate `prophet.ledger/v1.option_result_pct`, and no sample-size, return, hit-rate, selector, or promotion claim is authorized by this slice.

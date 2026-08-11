# Prophet exact-option mark observations

Status: host-private prerequisite evidence only. The first admitted publication starts
the clock; no history is reconstructed.

## Claim boundary

The canonical Prophet plan stores an exact OCC contract and an EOD entry mark. During
NYSE regular hours, the marks publisher can request the licensed history feed's
`trade_quote` row for that identity. The row pairs bid/ask with a trade, but it is not
an executable quote or an NBBO receipt. The lawful measurement is only a **mark change
from the plan's EOD mid to the trade-paired bid/ask mid**.

It is not trade P&L or a lifecycle outcome. No position, provider-observed entry,
provider-observed exit, or fill is present, including when a plan is past its trigger.
The upstream row carries size, exchange/venue, and condition fields; this bounded
artifact intentionally does not retain them. Every authority flag is false, so the
artifact cannot rank, gate, size, issue, train, trade, or steer Prophet or Neural Web.

## Frozen construction

- Contract identity: exact OCC root, expiry, right, and millistrike from the canonical
  published `prophet.index/v1` plan.
- Entry basis: `option_contract.entry_premium` only when the plan explicitly labels
  `freshness="EOD mark"`; an absent or different basis abstains from mark change.
- Observation basis: midpoint of the latest deterministic trade-paired bid/ask. Latest
  is maximum quote timestamp, then trade timestamp, then source sequence. A conflicting
  complete key or an unorderable source row abstains instead of inheriting frame order.
- Clock fence: retain quote and trade timestamps separately, age bid/ask from the quote
  clock, and retain the exact signed source sequence used for ordering. Require both
  clocks to be causal and on the session date, require the quote clock inside
  09:30–16:00 ET, and require quote age at most 30 minutes.
- Coverage: every open plan carrying `option_contract` produces one row. Invalid
  identity, expired contract, missing source, malformed quote, non-causal clocks,
  wrong-session clocks, an out-of-RTH quote, and an over-age quote are explicit
  abstentions.
- Plan state context: `pre_trigger` is `watch_only_pre_trigger`; all other open phases
  are `display_plan_active`. Both state only that `position_assumed=false`; neither is
  a lifecycle or trade receipt.
- Runtime contract: the complete observation is schema-checked before any immutable
  file or public current-marks write. A missing or invalid schema fails closed.

Schema: `contracts/options/prophet.option_mark_observation.v1.schema.json`.

## Private durability and public boundary

Each observation is canonical JSON, content-addressed, backwards-linked, and stored on
the publisher host below a caller-owned `0700` root outside the repository. Observation
and head files are caller-owned `0600`; observations use exclusive creation and the
head advances through an fsynced atomic replace. A lock serializes publishers, and the
prior bytes, digest, schema, and content identity are rechecked before the next link.

The default private root is
`~/.mastermind_private/prophet_option_mark_observations_v1`; operators may override it
with `PROPHET_OPTION_EVIDENCE_STATE_ROOT`. The public mutable
`live_flow/prophet_marks.json` contains the latest admitted display-tier marks and
coverage only. It does not expose an evidence pointer, observation history, provider
brand, or private path. There is no public immutable quote archive in this slice.

## Promotion fence

This chain is only the prerequisite mark path for future exact-option lifecycle work.
It does not populate `prophet.ledger/v1.option_result_pct`, establish a
provider-observed entry or exit, or authorize sample-size, return, hit-rate, selector,
or promotion claims.

# Prospective options episode context capture

This lane turns only future eligible SPY live-flow decisions into exact W1A
contexts. It does not backfill an event, change the options episode/campaign
ledgers, or participate in selection, ranking, forecasting, training, promotion,
or execution.

## Causal path

1. The M1 live-flow poller fsyncs the existing `kind=decision` owner receipt.
2. It samples `available_at` and writes a private non-sendable precommit, then
   fsyncs the existing `kind=availability` receipt with either the exact
   request ID/SHA binding or an explicit abstention. A separate publication
   proof distinguishes a proven precommit from a link left visible by a failed
   parent fsync. Only proven bytes can move into the transport outbox; an
   ambiguous precommit after availability permanently abstains.
3. The request preserves the unequal clocks: owner `ts` is `event_time`, while
   the durable receipt clock is `as_known_at` and `knowledge_cutoff`.
4. A bounded local outbox drains all currently eligible work in eight-request
   batches, independent of the next slow live-data cycle. Before SSH starts it
   fsyncs one ordered batch intent binding every request ID/SHA and the forced
   target. A crash in the unavoidable durable-intent/spawn seam or a lost
   acknowledgement becomes
   `outcome_unknown_after_durable_transport_intent`; an explicit pre-exec
   spawn error remains `pretransport_spawn_error`. A partial, unproven intent
   never implies launch.
5. A forced-command SSH key admits the exact request to the production W1A
   generation. The remote writer captures the whole bounded batch first, then
   projects every response from one final authenticated active HEAD pin. The
   existing hourly context projector later binds that exact query when the
   nightly owner publishes the episode.

The session identity/calendar anchor is created and publication-proven before
the regular-session open and is valid only for that NYSE session. A restart can
reuse the exact proven anchor. An anchor link without its causal proof can be
repaired only before open; afterward it permanently abstains.

## Fixed limits

- SPY canary only; every other ticker abstains before an outbox write.
- 8 requests and 1 MiB per SSH batch; at most 8 batches drain the fixed
  64-request outbox per owner boundary.
- 64 pending requests, 4,096 lifetime receipts, and 64 session anchors.
- 256 KiB per request; 30 seconds per ordered batch transport.
- Transport starts only through 13 minutes after the owner cutoff, leaving
  validation margin inside W1A's frozen 15-minute admission window.
- All roots and files are private (`0700` directories, `0600` files).

## One-time forced-command key

Create the dedicated key on the M1 ops host while the poller is idle:

```bash
umask 077
ssh-keygen -t ed25519 \
  -f /Users/chriswong/.ssh/market_memory_options_context_capture \
  -N '' -C market-memory-options-context-capture
```

Add only its public key to root's VPS `authorized_keys` with this restriction
(the key text follows the options and command):

```text
restrict,command="cd /opt/macro && exec /opt/macro-api/.venv/bin/python -m scripts.capture_market_memory_context --options-request-jsonl --store /var/lib/macro-market-memory/public" ssh-ed25519 AAAA... market-memory-options-context-capture
```

The reviewed launchd plist already supplies the non-secret target and key path.
Never reuse the general deploy key for the live lane.

## Deployment and proof

Deploy the M1 poller only through the standalone-clone swap procedure in
`ops/LIVE_FLOW_RUNBOOK.md`; never copy individual source files into the live
tree. Install/reload the reviewed plist after the swap.

Before the next open, verify an anchor exists and is private. After the first
new SPY decision, require all of the following:

- the M1 outbox has an authenticated `status=captured` transport receipt (or,
  after a lost acknowledgement, honestly reports
  `outcome_unknown_after_durable_transport_intent` and relies on the
  independent W1A/projector proof);
- the W1A HEAD authenticates the response `query_id`, `context_id`, and packet
  digest;
- packet `event_time` equals the future episode's owner event clock and packet
  `as_known_at` equals its durable `available_at` clock;
- every W1A feature remains explicit missingness and every authority flag is
  false; and
- after the nightly episode commit and the hourly projector, the private
  options receipt changes that episode from
  `exact_requested_as_of_context_absent` to `bound` without altering its owner
  record.

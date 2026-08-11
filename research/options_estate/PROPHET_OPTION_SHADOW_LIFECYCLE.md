# Prophet exact-option shadow lifecycle receipts

Status: host-private prospective research evidence
Event schema: `prophet.option_shadow_lifecycle_event/v1`
Producer: `scripts/build_prophet_option_shadow_lifecycle.py`
Scheduler: `com.mastermind.prophetmarks`, after each admitted marks attempt

## Claim boundary

This chain measures a shadow option mid from the first fresh post-trigger mark to a
same-session shadow terminal mid when the canonical Prophet ledger closes the plan.
It does not observe a fill, entry execution, exit execution, NBBO, position, or trade
P&L. It never writes `data/prophet/ledger.jsonl`, never populates
`prophet.ledger/v1.option_result_pct`, never publishes to R2, and has no rank, gate,
sizing, issue, Prophet, Neural Web, training, trade, or execution authority.

The input bid/ask remains the debranded, trade-paired history-feed projection governed
by `prophet.option_mark_observation/v1`. Upstream size, venue, and condition are not
retained. Lifecycle events are host-private and may not be publicly discovered or
redistributed.

## Prospective boundary

The first successful invocation writes one immutable `activation_boundary` event and
sets both cursors to facts already present:

- the exact private mark-chain head; and
- the exact `refs/heads/main` commit plus repository path, byte length, SHA-256, and
  parsed-row count of the canonical forward ledger.

Nothing at or before either cursor is eligible. A pre-existing fresh quote cannot be
turned into a retrospective enrollment. The ledger must continue byte-for-byte from
the stored prefix; rewrite, truncation, duplicate plan ID, malformed row, or a non-null
source `option_result_pct` blocks advancement.

## Enrollment

An open plan enrolls exactly once on the first later mark observation for which:

1. the private predecessor chain reaches the stored cursor without a gap;
2. `quote_status=available`, which already proves a causal same-session RTH quote no
   more than 1,800 seconds old;
3. the canonical state is explicitly post-trigger (`triggered_pre_t1`, `at_t1`,
   `between_t1_t2`, `post_t1_failed_hold`, `at_t2`, `post_t2`, or `overtime`); and
4. the exact OCC contract is valid and has not drifted.

Enrollment also freezes stable plan identity: `id`, `asset`, `plan_asof`,
`recorded_at`, and `entry_date`. `phase` may evolve through the post-trigger states,
but any later row that mutates a stable field permanently marks the lifecycle as
identity-drifted and can never supply a terminal mark or return.

`pre_trigger`, stale, malformed, wrong-session, outside-RTH, source-unavailable, and
already-closed rows abstain. The enrollment mark is labeled
`first_fresh_post_trigger_trade_paired_mid`; `position_assumed=false` and
`provider_observed_entry=false` are permanent.

Ledger advancement is evaluated before mark eligibility. If a plan's canonical close
is first observed in the same source delta as its first otherwise-eligible mark, that
plan never enrolls; the processor will not infer that the mark preceded the close.
Only enrollments already durable in the prior lifecycle state may consume a new close
row and terminalize.

## Terminal receipt

Only a new append-only `prophet.ledger/v1` row is canonical close authority. For an
enrolled plan, the processor appends exactly one immutable `terminal` event carrying
the canonical row's semantic digest, ordinal, close date, outcome, ledger receipt,
and enrollment pointer.

The terminal mark is the latest admitted fresh mark for the same OCC contract and the
same `close_date` session. If it exists, the private research statistic is:

`((terminal shadow mid / enrollment shadow mid) - 1) * 100`

rounded deterministically to four decimals. Its basis is
`shadow_mid_to_mid_research_only`; `trade_pnl=false` and
`provider_observed_exit=false`.

If no lawful terminal mark exists, the terminal event is still complete and immutable,
with a null return and one explicit reason:

- `NO_SAME_SESSION_ADMITTED_MARK`
- `PLAN_IDENTITY_DRIFT`
- `CONTRACT_DRIFT`
- `CANONICAL_NO_ENTRY`
- `CANONICAL_CLOSE_PREDATES_ENROLLMENT`

No later-session quote may repair an unavailable terminal receipt, and there is no
backfill lane.

## Durability and privacy

Default root:
`~/.mastermind_private/prophet_option_shadow_lifecycle_v1`

The processor never trusts the mixed-vintage deploy checkout's tracked
`data/prophet/ledger.jsonl`. Before every CLI advancement it resolves the official
repository's exact current `refs/heads/main` commit, downloads that commit-pinned
ledger path, validates every row, and atomically installs these caller-owned `0600`
siblings:

- `canonical_ledger/ledger.jsonl`
- `canonical_ledger/receipt.json`

The receipt is canonical JSON under
`prophet.canonical_ledger_snapshot_receipt/v1` and binds repository, ref, exact
commit, tracked path, byte count, SHA-256, and row count. The runner explicitly sets
`PROPHET_LEDGER_PATH` and `PROPHET_LEDGER_RECEIPT_PATH` to those host-private files.
A failed ref lookup, commit-pinned download, validation, receipt match, or atomic
readback blocks the lifecycle; the stale checkout copy is never a fallback.

- root and event directories: caller-owned `0700`;
- lock, current state, and event files: caller-owned regular `0600` files;
- events: schema-checked, content-addressed, `O_EXCL`, fsynced, read back, and linked
  backwards before the current state advances atomically;
- `activation_boundary.json`: a private immutable transaction marker that freezes the
  first source cursors across a crash, even if either source advances before retry;
- `advance_boundaries/<base_state_id>.json`: a private immutable per-state transaction
  marker written only after the candidate validates and before its first event write;
  it pins the exact mark head and ledger receipt so a crash retry adopts byte-identical
  enrollment/terminal events even after either source advances. It also binds the
  candidate state ID, lifecycle head, and ordered event pointers, so a code change
  cannot reinterpret pinned sources into a parallel valid history on retry;
- current state: content-identified and cross-checked against the complete event chain;
- retries: source-derived event bytes are deterministic, so an event written before a
  failed state swap is safely adopted on retry rather than duplicated.

The current state holds only private cursors and references. Public
`live_flow/prophet_marks.json` retains no lifecycle pointer, event ID, private path,
provider label, return, or append-only history.

## Operational order

`ops/launchd/run_prophet_marks_loop.sh` runs:

1. `scripts.build_prophet_marks --publish`; then
2. `scripts.build_prophet_option_shadow_lifecycle --sync-current-main-ledger
   --advance`.

The second step runs even when no new RTH mark was admitted, allowing the 09:25 ET
cycle to consume a canonical close written after the prior session. Either non-zero
exit keeps the launchd cycle red. Deployment must install the event schema and
lifecycle module before replacing the runner.

## Falsifiers

Advancement must fail closed, without moving either cursor, when any of these occurs:

- mark head, predecessor, digest, content identity, schema, or private mode is invalid;
- stored mark cursor is not an ancestor of the current head;
- event/state identity, event predecessor, enrollment pointer, or permissions fail;
- a post-enrollment mark mutates stable plan identity but remains return-eligible;
- canonical ledger no longer extends the exact stored prefix;
- canonical snapshot/receipt source, exact-main commit, path, digest, mode, or
  readback is invalid;
- a same-advance close is allowed to create and immediately terminalize a hindsight
  enrollment;
- a new canonical row is malformed, duplicated, future-reversed, or already claims an
  option result;
- a pending per-state source boundary is not an ancestor/prefix of current sources or
  does not reproduce the exact candidate transaction;
- runtime event-schema validation fails; or
- an immutable event path collides with different bytes.

Ordinary evidence insufficiency is not a process error: pre-trigger/stale marks simply
do not enroll, and missing same-session terminal evidence produces a terminal receipt
with an explicit unavailable reason.

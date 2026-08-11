# Options signal campaigns v1 — frozen preregistration

Status: registered before the first `campaigns.jsonl` publication, but after the
durable 2026-08-10 episode corpus was inspected. The rule freeze is exactly
`2026-08-11T08:22:28Z`.

The initial backfill is therefore in-sample retrospective discovery, not forward
evidence and not validation. All eight preserved rows are labeled
`evidence_phase=retrospective_discovery`. The former pre-retirement phase
vocabulary remains part of the frozen schema, but no future v1 row may be emitted
or counted as prospective evidence.

Retirement amendment (2026-08-11): publication stopped after the preserved
eight-row retrospective cohort. The writer and publisher described below are
historical initial-publication mechanics, not current authority. No active job
may append this v1 ledger; canonical revisions use the separately preregistered
v2 namespace.

## Purpose and authority

`options.signal_campaign/v1` is an immutable research-cohort ledger over the
existing point-in-time option-flow episodes. It answers one narrow question:
when did repeated premium first cross a fixed threshold for one exact contract?

Every row is an abstention. It cannot select, originate, score, rank, gate, size,
trade, publish a pick, compute option P&L, or train a model. It has no public or
private product consumer. A row is evidence for later research, never a call.

## Frozen membership rule

1. Validate every source row as `options.signal_episode/v1`.
2. Require `feature_snapshot.premium_usd` to be a positive, finite, exact
   rounded-dollar amount. Fractional dollars fail the build; they are not rounded.
3. Group exactly by:
   `(session_date, ticker, expiration, strike, right)`.
4. Preserve numeric strike identity without IEEE-754 coercion. Exact integer
   strikes above `2^53` must remain distinct.
5. Sort each group by `(available_at, episode_id)`.
6. Accumulate the ordered prefix. The first prefix with both
   `event_count >= 2` and `cumulative_premium_usd >= 3_000_000` forms the row.
7. Emit every qualifying group. Do not rank or truncate qualifying groups.
8. Events after the first crossing do not alter the row.

One event worth $3,000,000 does not qualify. Two events totaling $2,999,999 do
not qualify. Two events totaling exactly $3,000,000 do qualify.

## H+60 reference gate

Membership is fully determined before outcomes are inspected. Before a campaign
can persist, its crossing episode must have exactly one valid
`options.signal_episode_outcome/v1` row at horizon 60. The campaign copies only
the outcome schema, outcome id, episode id, and horizon. Outcome completion
state, timestamps beyond the stable reference, prices, returns, MFE, MAE, option
fields, and provenance cannot affect membership or campaign bytes.

A qualifying prefix without its H+60 row remains pending and emits nothing. It
is not an orphan and is retried on a later nightly run. A malformed, duplicated,
misidentified, wrong-horizon, or orphan outcome fails the run.

## Identity and immutable payload

The stable id is:

`ocam_<sha256(schema, full frozen rule, normalized group key)[:24]>`

The id deliberately excludes the crossing episode. A retroactively inserted
earlier episode therefore keeps the same campaign id but changes the payload;
the append-only store must reject that conflict rather than rewrite history.

The crossing block stores ordered episode ids, exact event count, exact
cumulative premium dollars, and SHA-256 over canonical bytes of every complete
episode row in the crossing prefix. It does not embed source episode rows.
`formed_at` is the crossing episode's `available_at`, normalized to canonical
UTC. `evidence_phase` is deterministically recomputed from `formed_at` and the
frozen rule clock; callers cannot relabel an earlier row as prospective.

## Sole writer and checkpoint order

`scripts/build_options_signal_episode.py` is the only writer and reuses the
existing nightly-only locked JSONL append machinery. The build order is:

1. episodes;
2. H+60 outcomes;
3. session outcomes;
4. campaigns, after reloading persisted H+60 bytes; and
5. source-prefix checkpoint last.

A campaign validation or append failure blocks checkpoint advancement. The
immediate metadata replay owns exactly five files: checkpoint, episodes, H+60
outcomes, session outcomes, and campaigns.

## Required falsifiers

- Threshold boundary: $3,000,000 in one event fails; $2,999,999 over two fails;
  exactly $3,000,000 over two passes.
- Ordering: equal `available_at` values break ties by `episode_id`; shuffled
  inputs and outcomes produce byte-identical rows.
- Immutability: later events do not change a row; an earlier insertion conflicts.
- Dimensions: session, ticker, expiration, strike, and right never coalesce.
- Numeric identity: exact strikes `2^53` and `2^53 + 1` stay distinct.
- H+60 gate: a missing anchor remains pending; malformed, duplicate, orphan,
  wrong-horizon, and forged-id anchors fail.
- Outcome blindness: complete versus terminal-incomplete anchors, reordered
  outcomes, and later valid `computed_at` values cannot change campaign bytes.
- Authority: `training_eligible` and every `may_*` capability remain false.
- Hindsight: before-freeze rows are retrospective, the exact boundary and later
  rows are prospective-after-freeze, and any mismatched phase label fails.
- Premium: fractional, non-finite, or unsafe rounded-dollar totals fail closed.
- Concurrency: duplicate appends produce one row; conflicting appends fail.
- Corpus: the retired ledger is pinned to exactly 8 rows, 10,492 bytes, and
  SHA-256 `db326f5c772ab417c43b8579ad50abb0434916922bda3a13c2da5b8303813910`.
  Each preserved row must still replay from its historical qualifying source
  prefix. Later episodes may create additional qualifying v1-shaped groups in a
  diagnostic recomputation, but they must neither append to the frozen ledger nor
  make its exact-byte audit compare against the growing source census.

## Explicit exclusions

This version adds no API, R2 object, UI, alert, trade plan, model input, new daily
node, new test file, new legacy CI job, or separate downstream artifact. It does
not copy tape-side heuristics or directional labels, and it creates no outcome
aggregation.

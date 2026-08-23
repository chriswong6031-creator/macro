# SRC-A1

Owner: existing revisions source owner
Type: implementation wave after K3E-0 acceptance

## Observable mission

After one natural collection run, future K3E work can reconstruct lawful
multi-horizon expectation trajectories instead of only reading today's latest
snapshot.

## Scope

- extend the existing revisions owner lane only;
- preserve raw provider-native records and clocks;
- capture all horizons returned, not just one preferred year;
- preserve enough lineage to detect freshness, staleness, and corrections later.
- keep legacy latest/history consumers working; any new raw table or parquet is
  additive and owned by the revisions lane, not by a separate K3E store.

## Do

- record provider, metric, basis, horizon, value, units, currency where present;
- preserve issued / available / collected / known clocks where the provider or
  collector can distinguish them;
- preserve coverage counts and any provider-native freshness markers;
- preserve raw payload identity / source references sufficient for replay.
- record collection attempt identity, source accessor/endpoint, input ticker,
  provider degradation, raw horizon label, normalized fiscal period when safe,
  and `known_at`.
- include revenue expectation rows where the current provider exposes them, or a
  typed absence where it does not.

## Do not

- compute a phase label;
- compute K3E scores;
- build a third analyst-history store detached from the revisions owner lane;
- backfill history from current snapshots.
- touch residuals, options, identity, event systems, Prophet, Market OS, or
  product publication.

## Proof

- one natural run writes lawful raw records for multiple horizons;
- replay on the same input is stable;
- a cold reader can derive freshness and stale-share from the preserved fields.
- legacy revision-breadth outputs remain byte- or field-compatible for existing
  consumers, or the PR explicitly proves the compatible migration.

## Stop condition

Return after the source lane can accrue raw prospective all-horizon EPS/revenue
expectation observations with idempotent replay. Do not build `EXP-1` surfaces
or coupling states in the same PR.

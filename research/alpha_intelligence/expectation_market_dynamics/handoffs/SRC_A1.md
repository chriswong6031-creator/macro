# SRC-A1

Owner: `collectors/equity_revisions.py` in the existing revisions source owner lane
Type: implementation wave after K3E-0 acceptance

## Observable mission

After prospective scheduled collections begin, a cold reader can reconstruct
lawful multi-horizon EPS/revenue expectation trajectories from the revisions
owner’s immutable raw observations and attempt receipts, instead of mistaking
today's revision-breadth snapshots for historical consensus truth.

## Scope

- extend only `collectors/equity_revisions.py`; `collectors/yf_analyst.py` stays
  the price-target/rating lane;
- add only `data/revisions/expectation_observations.parquet` and
  `data/revisions/expectation_attempts.parquet` as the raw prospective artifacts;
- preserve every provider-returned horizon and the separate source effective,
  source published, provider observed, and system observed clocks;
- preserve the `DATA_CLOCK_RIGHTS_MATRIX.md` observation, attempt, missingness,
  idempotency, correction, rights, and rate-limit contract exactly;
- preserve `latest.parquet`, `history.parquet`, and `engine/theme_revisions.py`
  semantics for existing consumers.

## Do

- implement the full long-form observation contract and exact attempt-status enum
  in `DATA_CLOCK_RIGHTS_MATRIX.md` rather than choosing alternative schemas;
- include EPS and revenue where exposed; write a typed missingness result, never
  a fabricated zero or a current-snapshot backfill, where a field is unavailable;
- retain immutable as-known records and explicit supersession linkage; a
  same-session same-payload retry is idempotent while a later scheduled session
  is still receipted;
- instrument attempts/success/null/401/403/429/latency/names by hour-cycle and
  coverage by day before altering freshness, cadence, batch size, or universe.

## Do not

- compute a phase label;
- compute K3E scores;
- build a third analyst-history store detached from the revisions owner lane;
- backfill history from current snapshots.
- touch residuals, options, identity, event systems, Prophet, Market OS, or
  product publication.
- infer vendor contributor identity, substitute reviser counts for coverage, or
  turn `http_429` into neutral data;
- change legacy revision outputs, build an evaluation/ranker/fair-value/gate/
  size/trade authority, contact a vendor, procure a feed, or deploy production.

## Proof

- focused schema/behavior tests prove every named mutation gate in
  `DATA_CLOCK_RIGHTS_MATRIX.md`;
- a scheduled collection writes a lawful, all-returned-horizon EPS/revenue (or
  typed-missingness) receipt plus a linked attempt receipt;
- same-session/same-payload replay produces no duplicate observations, while a
  later unchanged scheduled session retains its new receipt;
- changed payloads append/supersede, and failed/partial/null paths cannot replace
  good prior data;
- hourly rate-limit and daily coverage receipts derive from attempts before any
  cadence widening;
- legacy revision-breadth outputs remain field-compatible for existing consumers
  or the PR proves a compatible migration.

## Stop condition

Return after the source lane can prospectively accrue the specified all-horizon
EPS/revenue observation and attempt receipts with idempotent replay, immutable
correction lineage, and the required operating evidence. Do not build `EXP-1`,
coupling states, a vendor adapter, evaluation, or any product/runtime surface in
the same PR.

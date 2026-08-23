# Data, Clock, And Rights Matrix

| plane | native object | primary time fields to preserve | correction behavior | rights / degradation law |
|---|---|---|---|---|
| expectation observations | provider-native revision / estimate records | provider-issued-at, source-available-at, collected-at, known-at, superseded-at | append / supersede only; no hindsight overwrite | `UNLICENSED`, `UNAVAILABLE`, `STALE`, `LOW_COVERAGE` are lawful outputs |
| event facts | owner-native event / workspace objects | event time, publication / acceptance time, first tradable implication where owner defines it | owner-native correction lineage only | K3E cannot widen event rights |
| financial semantics | FIF packets / revisions / statements | cutoff, filing acceptance, packet generation, known-at | owner-native packet and revision lineage | if not production admitted, surface that limit honestly |
| raw price path | canonical market data owners | trade / close timestamps, corporate-action adjustment basis | vendor-native revisions only | no synthetic intraday reconstruction here |
| residual path | existing residual owners | residual as-of, window definition, universe version | owner-native recompute lineage only | do not recompute or widen authority |
| options uncertainty | existing options owners | quote / surface times, source coverage, maturity basis | owner-native refresh / expiry only | uncovered names fail closed for options outputs |
| identity joins | current identity owners | identity version / validity windows where present | owner-native alias / mapping updates only | no guessed joins |

## K3E clock law

1. Every emitted K3E object carries both the owner-native observation clocks and
   the K3E composition time.
2. `known_at` is required for any historical replay or backtest consumer.
3. If owner clocks cannot support point-in-time honesty, the K3E emission is
   typed absent or degraded; it is not inferred from current state.
4. Fiscal-period clocks and market-session clocks remain separate. A fiscal
   rollover, earnings date movement, or calendar-year mapping correction is a
   lineage event, not a license to rewrite old expectation history.
5. Provider-issued time, provider-available time, collector-observed time, and
   system-known time must not be collapsed unless the source truly cannot
   distinguish them; when collapsed, the emitted object prints that limitation.
6. Rights limitations are part of the result. If analyst/provider-native detail
   is visible to a vendor sample but not licensed for storage or redistribution,
   K3E records the blocked capability rather than inventing a coarser synthetic
   substitute.

## Correction and deletion law

- Corrections supersede prior records; they do not mutate historical as-known
  values in place.
- Deleted or withdrawn source records remain as withdrawn observations where
  rights allow, with withdrawal clocks; otherwise the gap is `RIGHTS_BLOCKED`.
- A current provider snapshot may seed current state only. It may not be spread
  backward to create fake historical analyst coverage, estimate dispersion, or
  revision chronology.

## SRC-A1 physical source contract (K3E-0R)

This section is the implementation contract for the existing revisions source
owner. It deliberately freezes the physical artifacts, clocks, attempts,
idempotency, correction treatment, and rate-limit evidence before any runtime
work begins.

### Physical owner and artifacts

`collectors/equity_revisions.py` is the sole SRC-A1 raw prospective EPS/revenue
collector. `collectors/yf_analyst.py` remains the price-target/rating lane.
SRC-A1 adds, and only adds, these canonical source-owner artifacts under
`data/revisions/`:

| artifact | grain / purpose | non-effect |
|---|---|---|
| `expectation_observations.parquet` | one long-form provider observation for one ticker, metric, horizon, field, and collection session | does not replace `latest.parquet` or `history.parquet` |
| `expectation_attempts.parquet` | one receipted provider/ticker collection attempt, including a null or failure | does not turn a failed attempt into source data |

Existing `latest.parquet`, `history.parquet`, and `engine/theme_revisions.py`
keep their established revision-breadth / live-score semantics. These new files
are additive and are not a new K3E, Market-Belief, identity, residual, event,
lifecycle, evaluation, ranker, or publication store.

### Observation schema and grain

`collection_session_id` is the stable identity of one scheduled provider/ticker
collection. `attempt_id` is the stable identity of the provider/ticker attempt
inside that session. Both are deterministic IDs retained on a replay, rather
than new wall-clock UUIDs. `observation_id` is the deterministic SHA-256 of the
canonical tuple `(collection_session_id, provider, provider_record_class,
provider_payload_hash, ticker_compat, metric, horizon_label_raw,
observation_type)`. Thus `expectation_observations.parquet` has one row per
`(collection_session_id, ticker_compat, metric, horizon_label_raw,
observation_type, provider_record_class, provider_payload_hash)` observation.
It carries the following fields; nullable means genuinely unavailable, never a
silently substituted value:

| field | contract |
|---|---|
| `observation_id` | stable identity for this immutable captured observation |
| `collection_session_id`, `attempt_id` | bind the row to its scheduled collection and the exact attempt that produced it |
| `provider`, `provider_record_class`, `provider_payload_hash` | provider/protocol identity and the exact payload identity used for idempotency and correction lineage |
| `ticker_compat`, `issuer_ref`, `security_ref` | input ticker is required; canonical issuer/security references are optional only when an existing owner supplies them |
| `metric` | enum `{EPS, revenue}` |
| `horizon_label_raw`, `period_end`, `fiscal_period`, `fiscal_year` | raw provider horizon is required; fiscal mapping is nullable and never guessed |
| `observation_type` | enum `{average, median, high, low, covering_analyst_count, growth, year_ago}` |
| `value`, `unit`, `currency`, `basis` | value is nullable only with the typed missingness below; unit/currency/basis are optional provider facts and cannot be changed in place |
| `aggregation_level`, `contributor_id` | literal `consensus_snapshot` and literal null, respectively; no raw-vendor contributor identity is promised in this wave |
| `source_effective_at`, `source_published_at`, `provider_observed_at`, `system_observed_at`, `market_session` | distinct clocks defined below; `market_session` is the collector’s market-session classification, not a fiscal mapping |
| `missingness_reason` | typed state, including `UNESTIMABLE`, `UNAVAILABLE`, `RIGHTS_BLOCKED`, `NOT_APPLICABLE`, and `MALFORMED`; null only when a value is present and interpretable |
| `correction_state`, `supersedes_observation_id`, `rights_class`, `provenance_note` | append-only lineage, rights, and safe source context |

No contributor-level analyst identity, contributor count inference, or current
snapshot backfill is authorized. `UNESTIMABLE` and every typed missingness state
are first-class outcomes.

### Clock vocabulary

The following columns are never aliases for one another:

| clock | meaning | nullable rule |
|---|---|---|
| `source_effective_at` | time the source says the estimate/value became effective, if supplied | null when the source supplies no effective time |
| `source_published_at` | time the source says it published/issued the record, if supplied | null when publication time is absent or different but unknowable |
| `provider_observed_at` | time the provider response/snapshot was observed by the collector/provider adapter | always recorded for a completed response; never copied into source clocks |
| `system_observed_at` | time Macro durably recorded this attempt/observation | always recorded by the writer; never copied backward into provider/source clocks |
| `market_session` | market-session label at `system_observed_at` under the current market-calendar rule | nullable only if the calendar classification is unavailable |

Fiscal period mapping and market session are independent. A fiscal rollover,
calendar mapping correction, or later provider correction creates append-only
lineage; it never rewrites an earlier as-known observation.

### Attempt schema and idempotency

`expectation_attempts.parquet` has one row per `attempt_id` and contains
`collection_session_id`, `provider`, `ticker_compat`, `attempted_at`,
`completed_at`, `status`, `http_status`, `latency_ms`, `response_payload_hash`,
`safe_error_class`, `safe_error_detail`, and `observation_count`. The status enum
is exactly `{success, partial, null, http_401, http_403, http_429, malformed,
error}`. HTTP, latency, hash, and safe error fields are nullable when they do not
apply; errors must be bounded/safe diagnostics, not response bodies or secrets.

For the same logical `collection_session_id` and the same payload hash, replay
is idempotent: retain/reuse the same deterministic attempt receipt and do not
append duplicate observations. A later scheduled collection receives a new
session and attempt receipt even when all values are unchanged. A changed
payload appends a new observation lineage with `correction_state` /
`supersedes_observation_id` as applicable; previously recorded as-known bytes
are immutable. A failed, partial, or null attempt never overwrites a previously
good observation.

### Rate-limit and mutation gates

Before widening `_FRESH_DAYS`, batch size, cadence, or universe coverage, derive
operating evidence from `expectation_attempts.parquet` rather than changing the
cadence blind. The required hourly-cycle receipt reports attempts, successes,
nulls, `http_401`, `http_403`, `http_429`, latency, and distinct attempted
`ticker_compat` names. The required daily coverage receipt reports the frozen
target-universe denominator plus distinct attempted, successful-observation,
null, and blocked/error names. A 429 is an operational result, never neutral
source data or evidence of coverage.

The SRC-A1 implementation must carry discriminating mutation gates for:

1. missing value becoming `0`;
2. reviser-count substitution for `covering_analyst_count`;
3. fiscal rollover being treated as a revision;
4. duplicate rows from a same-session replay;
5. a failure overwriting good state;
6. `http_429` being emitted as neutral data;
7. collapsing provider horizons;
8. an in-place unit/currency/basis change;
9. drift in the legacy `latest.parquet`/`history.parquet` semantics; and
10. copying current values backward to historical sessions.

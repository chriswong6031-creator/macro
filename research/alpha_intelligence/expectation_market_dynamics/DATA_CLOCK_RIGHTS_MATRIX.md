# K3E-0 Data, Clock and Rights Matrix

## Required clock vocabulary

Every observation carries the fields that are knowable and leaves the rest
typed absent:

| Field | Meaning |
|---|---|
| `source_effective_at` | Time/date the source says the estimate applies, if supplied |
| `source_published_at` | Source publication timestamp, if supplied |
| `provider_observed_at` | Provider timestamp for the returned snapshot, if supplied |
| `system_observed_at` | UTC time K3E successfully observed the payload |
| `attempted_at` | UTC time of every success or failed attempt |
| `market_session` | Canonical session identity used for alignment |
| `fiscal_period_end` | Fiscal period the estimate targets, not collection date |
| `horizon_label_raw` | Provider's unmodified horizon label |
| `horizon_ordinal` | Deterministic within-payload order only when mapping is provable |
| `supersedes_observation_id` | Correction/supersession link; never in-place rewrite |

`system_observed_at` does not become `source_published_at`. A daily snapshot
proves only that the value was observable no later than collection time. Same-
day price alignment must use a preregistered availability rule; missing source
time normally moves the first lawful reaction session forward rather than
fabricating an intraday cutoff.

## Source and rights matrix

| Source family | Intended fields | Clock quality at birth | History/correction | Rights posture | K3E ruling |
|---|---|---|---|---|---|
| yfinance analyst tables | EPS/revenue averages, lows, highs, analyst counts, growth; all provider horizons | Current payload plus system observation time; provider time must be preserved if present | No trusted pre-collection history; prospective append can detect later changes | Free wrapper/source terms require review; provenance and non-redistribution boundary mandatory | `SRC-A1` may collect raw prospective observations; no backfill claim |
| Existing target/rating collector | price targets, recommendation key, analyst count | Daily `as_of`; current `.info` snapshot | Dated house accrual exists, but only for current target/rating fields | Existing owner contract | Reuse, do not conflate with EPS/revenue |
| Licensed estimates vendors | detailed consensus, contributors, PIT vintages, actuals depending product | Vendor-specific; must be demonstrated in sample payload | Vendor-specific revision/restatement delivery | Contract, redistribution, derived-data and retention rights decisive | `VEND-0` tests identical sample and rights; no marketing-only winner |
| Earnings/event owner | event identity, publication/observation clocks, documents | Owner-native | Owner-native correction lifecycle | Existing source-specific rights | Join by reference |
| Market bars/calendar | raw/adjusted returns, session identity | Canonical exchange/session clocks | Owner-native corrections | Existing owner contract | Read through owner adapters |
| DRL/residual-alpha | expected/relative response outputs and estimability | Method/version-specific | Owner-native | Internal governed artifact | Reference exact output; no reimplementation |
| Options plane | implied distribution/volatility/skew where prerequisites pass | Quote/trade snapshot clocks | Owner-native | Vendor/exchange-specific | Optional leg; output-specific fail closed |

## Required long-form raw expectation contract for SRC-A1

One physical/logical row represents one raw provider field for one ticker,
metric, horizon and collection session. This long-form contract is the only
SRC-A1 representation; a wide mean/low/high row is not an alternative. At
minimum, each row preserves:

```text
observation_id
provider
provider_record_class
provider_payload_hash
ticker_compat
economic_issuer_ref (nullable; only through current identity seam)
security_ref (nullable; only through current identity seam)
metric in {eps, revenue}
horizon_label_raw
period_end (nullable if provider does not supply it)
fiscal_year (nullable)
fiscal_quarter (nullable)
observation_type in {average, median, high, low, covering_analyst_count, growth, year_ago}
value
unit (nullable; never invented)
currency (nullable; never invented)
basis (nullable; never invented)
aggregation_level = consensus_snapshot
contributor_id = null
source_effective_at (nullable)
source_published_at (nullable)
provider_observed_at (nullable)
system_observed_at
market_session
attempt_id
missing_reason (nullable; absent fields do not become numeric rows)
correction_state
supersedes_observation_id (nullable)
rights_class
provenance_note
```

`observation_id` includes provider, ticker, metric, raw horizon, observation
type, lawful collection session and payload identity. The corresponding attempt
row uses `attempted_at`. `mastermind_recorded_at` and
`provider_effective_at` are not alternate field names: implementations use
`system_observed_at` and `source_effective_at` exactly.

The companion attempt artifact has one row per ticker fetch and uses exactly:

```text
attempt_id
provider
ticker_compat
attempted_at
completed_at
attempt_status in {success, partial, null, http_401, http_403, http_429, malformed, error}
http_status (nullable)
latency_ms
observation_count
provider_payload_hash (nullable)
error_class (nullable)
error_detail_safe (nullable)
```

Attempt rows contain no credential, token, raw confidential payload or fabricated
observation. `partial` and `null` remain visible in denominators.

No derived phase, rank, price gap, implied upside, fair value or recommendation
is allowed in the raw artifact.

## Failure and correction law

- 401/403/429, malformed payload, missing table, empty horizon, identity
  ambiguity and write failure are distinct durable attempt outcomes.
- An all-null success-looking row is forbidden; absence is typed and counts in
  the denominator receipt.
- Observation identity includes the lawful collection session/date. A repeated
  run of the same logical collection session and payload is idempotent; a later
  scheduled session remains observable evidence even when values are unchanged
  (either as a new session observation or an explicit attempt-to-prior-value
  reference under the frozen schema).
- A changed payload appends a new observation and links its predecessor. It
  never rewrites what the system knew at the earlier clock.
- Collection gaps remain gaps. Current values may not be copied backward to
  manufacture a historical series.

# SRC-A1 Commission — Raw Prospective Estimate Observation Accrual

## ROUTE

`build` — one source-history PR, then stop and return evidence.

## Mission

Extend the existing revisions source lane so Mastermind prospectively preserves
raw multi-horizon EPS and revenue expectation observations with explicit clocks,
missingness and correction-safe append behavior, without changing existing
downstream semantics or building expectation-surface, phase, model or product
logic.

## Why this is useful alone

Every day not collected is irrecoverable PIT history. A raw, honest observation
tape makes later 1d/5d/21d trajectories possible even if no model is ever built.

## Required bootstrap

Before editing, re-pin current protected Skillpack, Macro `main`,
`WS:ALPHA-INTELLIGENCE-INTEGRATION`, current revisions-related PRs/worktrees and
these source/consumer paths:

```text
collectors/equity_revisions.py
data/revisions/latest.parquet
data/revisions/history.parquet
engine/theme_revisions.py
tests/test_equity_revisions_w2a.py
collectors/yf_analyst.py
data/narrative/analyst_snapshots.parquet
```

If another current session owns the revisions collector or `data/revisions/`,
stop with collision evidence. Do not reuse a stale `feat/analyst-revisions`
branch and do not create a second Yahoo collector.

## In scope

1. Preserve **every horizon returned** by yfinance `earnings_estimate` and
   `revenue_estimate`, not only the current `+1y`/`0y` selection.
2. Preserve raw provider columns where available: average, low, high,
   `numberOfAnalysts`, growth/year-ago fields, raw horizon label and metric.
3. Record one long-form observation per ticker/metric/horizon/field/value and
   collection clock, with raw provider basis and missing reason.
4. Keep the artifact inside the canonical revisions store, recommended:

```text
data/revisions/expectation_observations.parquet
data/revisions/expectation_attempts.parquet
```

These are typed sub-artifacts of the existing revisions owner, not a third
generic analyst-history store. If current main has since accepted an equivalent
path, extend it rather than minting these names.
5. Record durable per-ticker attempts with success/null/401/429/other failure,
   latency and observation count.
6. Append idempotently. Repeated same-session/same-payload collection does not
   duplicate. A later scheduled session preserves sequential observation even
   when values are unchanged (directly or by an explicit reference to the prior
   value); a changed payload appends a new observation and preserves earlier
   bytes.
7. Preserve legacy `latest.parquet`, `history.parquet` schema/meaning and
   `engine/theme_revisions.py` behavior byte-for-byte unless a narrow mechanical
   addition is unavoidable and parity-proven.
8. Add a deterministic small golden cohort/config only if source measurement
   shows the current drip cadence cannot safely cover the initial run.

## Raw contract

Minimum logical fields:

```text
provider = yfinance
provider_record_class in {earnings_estimate,revenue_estimate}
provider_payload_hash
ticker_compat
economic_issuer_ref? / security_ref? only through current identity seam
metric in {eps,revenue}
horizon_label_raw
period_end? / fiscal_year? / fiscal_quarter? only if provider proves them
observation_type in {average,median,high,low,covering_analyst_count,growth,year_ago}
value
unit? / currency? / basis? (never invented)
aggregation_level = consensus_snapshot
contributor_id = null
source_effective_at? / source_published_at? / provider_observed_at?
system_observed_at
market_session
attempt_id
missing_reason?
correction_state
rights_class / provenance_note
supersedes_observation_id?
```

The attempt artifact uses the exact companion schema in
`../DATA_CLOCK_RIGHTS_MATRIX.md`: `attempt_id`, provider/ticker, attempted and
completed clocks, typed status, optional HTTP status, latency, observation
count, optional payload hash, and safe error class/detail. Do not improvise a
second clock or status vocabulary.

Do not label provider horizon strings as fiscal periods unless the mapping is
proved. Do not turn provider growth into an internally derived revision. Yahoo
does not supply historical revenue revision fields; later deltas will be derived
from retained snapshots.

## Clock, null and correction law

- Collection time is `system_observed_at`, not provider publication time.
- Date-only availability cannot support intraday alignment.
- Missing is never zero; reviser count never substitutes for covering analyst
  count.
- A failed fetch appends an attempt and cannot overwrite last good state.
- 401/429 is a source failure reason, never a neutral observation.
- Fiscal rollover or provider basis change produces a new raw observation and
  must not masquerade as like-for-like revision.
- Same logical collection session and payload is idempotent; a later scheduled
  session remains receipted, and a changed payload appends and may link its
  predecessor.

## Rate-limit law

Do not change `_FRESH_DAYS`, `max_new` or full-universe cadence blindly. First
instrument attempts, successes, nulls, 401, 429, latency, names/hour, cycle
duration and coverage/day. Begin with the current drip or a deterministic golden
cohort. Broaden only from measured behavior and source terms.

## Mutation tests that must fail under corruption

- missing becomes zero;
- reviser count substitutes for coverage;
- horizons collapse;
- fiscal rollover looks like a comparable revision;
- same payload/session duplicates;
- failed fetch overwrites good state;
- 429 becomes neutral;
- provider basis changes in place;
- legacy consumer fields change meaning; or
- raw current values are copied backward as history.

## Acceptance

- Targeted unit/mutation tests pass with no network escape.
- Existing revisions and theme-revisions tests pass.
- A bounded live source probe reports exact attempts and raw returned horizons;
  do not commit incidental data unless the repository's existing data delivery
  contract requires it and the source run was intentional.
- Diff contains only the source vertical, its tests/config and required paired
  owner artifacts.
- Capability reports no higher than `BUILT_NOT_PROVEN` unless a separate natural
  scheduled SRC-A1P receipt exists.
- PR is committed, pushed, checked, merged and verified on current `main` under
  ordinary delivery law.

## Out of scope / stop

No expectation surface, revision-wave detector, change-point/latent model,
market response, coupling, phase, Market OS, Terminal, rank, fair value, Prophet
or production-proof claim. Stop after one source-history PR and return:

```text
STATUS
RESULT
EXACT BASE/HEAD/PR/MERGE
FILES
TESTS
LIVE SOURCE PROBE (if lawful)
ATTEMPT/RATE-LIMIT RECEIPT
CAPABILITY STATE
GAPS
DEVIATIONS
NEXT NATURAL PROOF
```

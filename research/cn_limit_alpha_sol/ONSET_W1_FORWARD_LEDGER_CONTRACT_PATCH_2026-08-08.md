# ONSET Wave-1 forward-ledger contract patch (apply after integration)

This is a narrow documentation patch suggestion. The frozen research receipt
is not rewritten by the production ledger and remains the parameter/seed
authority.

Change these `forward_ledger_contract` fields when the engine commit is
integrated:

| Field | Integrated value |
|---|---|
| `implementation_status` | `PRODUCTION_FORWARD_ONLY_CONTEXT_DISPLAY_LEDGER_BUILT` |
| `storage_mode` | `IMMUTABLE_DAILY_PARQUET_PARTS_GROUPED_BY_MONTH` |
| `normalized_monthly_parquet_partitions` | `BUILT:data/cn_limit_alpha/forward/{probabilities,grades}/YYYY-MM/YYYY-MM-DD.parquet` |
| `future_entry_calendar` | `OFFICIAL_SSE_SZSE_2026_TRACKED_FAIL_CLOSED_OUTSIDE_ATTESTED_YEAR` |
| `grade_calendar` | `official_exact_session_clock_plus_latest_complete_nominal_raw_support` |
| `grader_integration` | `BUILT:event_all_probabilities;execution_selected_only_H1_H3_H5` |
| `production_runner_contract` | `BUILT:receipt_parameters_only_dynamic_latest_complete_no_refit_no_research_import` |
| `recurring_nightly_advancer` | `BUILT:scripts.advance_cn_limit_alpha_ledger` |
| `required_caller_lane` | `CN_LANE=asia_via_engine.ledger_lane.asia_advance_enabled` |

Extend both `event_grade_required` and `execution_grade_required` with these
production evidence fields:

- `ledger_schema_version`
- `grade_observed_session`
- `source_hash`

`graded_at` is the actual processing-session close, including a delayed first
grade; `fill_decided_at` remains the entry-session decision clock. `source_hash`
binds the probability identity/source, calendar artifact and exact entry,
intermediate, carry and exit raw observations used by the grade. Revisions are
keep-first contradictions even when the terminal return is unchanged.

Remove exactly these four now-built strings from `UNTESTED_VARIANTS`:

- `recurring nightly probability advancement and grading integration; only contract helpers and one honest seed are built`
- `authoritative annual SSE/SZSE future-session calendar for recurring ledger advancement`
- `normalized monthly Parquet probability/grade partitions beyond the capped ten-session JSONL bridge`
- `a production forward runner that loads frozen fitted parameters, discovers the dynamic latest-complete observed session, and never refits nightly or imports the frozen research panel/calendar path`

Replace them with these bounded limitations:

- The tracked official future-session authority covers 2026 only; advancement
  deliberately stops before any 2027 prediction or grade needs a 2027 session.
- A new probability snapshot fails closed unless the ST/risk-warning membership
  artifact is attested for the exact signal session. The existing frozen seed
  may bootstrap without reopening that already-stamped population.
- Fillability, limit events, and exits remain end-of-day/open daily-bar proxies;
  auction queue position, partial fills, intraday wall dynamics, and capacity
  remain untested.

The engine accepts the receipt-declared model-version list, so the corrected v2
receipt/JSONL seed bootstraps without hard-coded v1 names. It validates the
config hash, each frozen model hash, the receipt hash, the three-model full
population, and exact official Aug-07 to Aug-10 clock. The research receipt
does not need to claim ownership of production files for bootstrap to work; it
only needs to declare the frozen model/config/version/hash contract that the
engine validates.

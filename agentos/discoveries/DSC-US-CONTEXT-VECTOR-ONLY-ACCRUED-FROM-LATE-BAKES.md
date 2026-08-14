---
key: US-CONTEXT-VECTOR-ONLY-ACCRUED-FROM-LATE-BAKES
claim: >
  Until 2026-08-14 the US Context Vector store (data/us_prophet_rank/candidates/)
  could only accrue from LATE bakes: context_api._regime_dim returns a nested
  {"history","live"} value whenever the bake runs within 1 day of as_of
  (is_current), embedding the whole data/regime/latest.json as a struct column
  that pyarrow cannot write ("cannot mix struct and non-struct" — its lists mix
  dicts and scalars), so append_candidates swallowed the exception and returned
  0 for BOTH tiers on every on-time night. All four pre-fix stamped days
  (2026-07-31, 08-05..07) came from ≥2-day-late recovery bakes — a timing
  selection bias any study joining pre-fix rows inherits — and 08-10..08-13 are
  a permanent hole (no-backfill charter).
falsifier: >
  An on-time nightly (bake within 1 day of as_of) committing new stamp_date rows
  to data/us_prophet_rank/candidates/ with the pre-#5595-era code; or the engine
  job log of run 31671422158 NOT containing "us_context_vector append failed:
  ('cannot mix struct and non-struct…' at 2026-08-13T12:29:57Z.
so_what: >
  (1) Studies over pre-2026-08-14 candidates rows must treat the sample as
  conditioned on "the nightly was broken that week", not as normal accrual — and
  regime__ columns as history-basis only. (2) The 08-10..08-13 gap is disclosed,
  never repaired (same-night-only stamping charter). (3) When a fail-soft
  telemetry writer shares an assembly path across two lanes, a simultaneous
  silent zero in both lanes means a SHARED INPUT SHAPE changed, not two lane
  failures — check what the healthy era's timing was actually selecting for.
kind: landmine
verified_at: 2026-08-14
verified_by: >
  Engine job 94437305309/run 31671422158 log line 2026-08-13T12:29:57Z (append
  failed, column regime__live); empirical repro + fix verification against
  origin/main blobs (data/regime/latest.json at 44c90f8f547c embedded as a
  struct refuses to_parquet; flat projection writes); store census: 2026-08
  part max stamp_date=2026-08-07 while us_board_ledger/snapshots.jsonl
  as_of=2026-08-13; fix PR "fix(us-context-vector): stamp from on-time bakes".
scope: [macro, data/us_prophet_rank, engine/us_context_vector.py, engine/neuralweb/context_api.py]
confidence: verified
---

## Detail

The store's fail-soft contract ("research telemetry never breaks the build") plus a
logger-prefixed WARNING (invisible to the Actions summary per the annotation law)
made the failure structurally silent: boards, ledgers and every sibling artifact
advanced nightly while both the curated stamp (engine job, build_stock_library) and
the scan stamp (us_scan_tier job) returned 0 through the same
`append_candidates → to_parquet` path. Detection now exists at two altitudes after
#5604 absorbed the writer-side seam: the producer emits scalars only
(`context_api._regime_dim` merge path) and the store quarantines unclassified
non-scalars / announces quiet-append and grader-vs-asof staleness; AND
`scripts/check_surface_freshness.py::check_candidates_freshness` alarms (annotation
+ ops alert) when the newest stamp_date trails the board ledger's own as_of by
>2 sessions — the differential that distinguishes a silent sibling from a
whole-nightly outage, which the grader tripwire (vs graded_asof) does not own.

Related: DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET (mid-run checkpoints make
run conclusions ≈ zero info about delivery), DSC:PROPHET-ASOF-IS-WALL-CLOCK (the
is_current gate keys off wall clock, which is what tied store health to bake TIMING).

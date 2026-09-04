---
key: CNLI-BAK-BASIC-PIT-ROWS-ABSENT-FROM-STOCK-BASIC-WITNESS
claim: >
  TuShare's `stock_basic` lifecycle witness does not cover every `bak_basic` PIT
  row, so the exact plane's `pit_universe` stage cannot reach a terminal unit on
  real vendor data. Measured 2026-08-26 on the first `pit_universe` execution
  ever made against the live vendor (run 32950379014, trade_date 2024-01-02):
  source_row_count 5,344 = landed_A 5,342 + known_excluded 0 +
  quarantined_unknown 2, `source_accounting_complete` true, unit status `failed`
  with reason `quarantined_unknown_source_rows`. Both quarantined rows carry
  classification_source `bak_basic_absent_from_stock_basic_A_witness` and fall
  into TWO DISTINCT classes:
  (1) `603361.SS` 浙江国祥 — `list_date` "0" with float_share, total_share,
  holder_num, bvps and eps all 0: an approved-but-never-listed name. TuShare
  returns ZERO rows for stock_basic list_status G on every exchange
  (SSE_G/SZSE_G/BSE_G partitions are all empty), so no approved-unlisted
  universe is available from that endpoint at all.
  (2) `300114.SZ` 中航电测 — a demonstrably TRADED security on that session
  (eps 0.17, pe 197.95, holder_num 44,237, list_date 20100827) that is absent
  from the CURRENT stock_basic snapshot across all four list_status values and
  from `identity_aliases`. The reference generation holds only L (5,550) and D
  (338); the 中航 group appears consolidated under `600372.SS` 中航机载.
  Class 2 is the serious one: the witness is a CURRENT snapshot being used to
  classify a HISTORICAL session, so a security the vendor later stops publishing
  becomes unclassifiable on every past date it traded.
falsifier: >
  Re-run one bounded canary window over a post-2016 session and read the unit:
  `python3 -c "import json,pathlib,sys; sys.path.insert(0,'.');
  from collectors import china_tushare_spine as sp;
  S=pathlib.Path.home()/'.local/share/macro-dashboard/china_tushare_spine';
  st=json.loads((S/'collection_state.json').read_text());
  print(st['units']['bak_basic'])"`, and read the retained payloads at
  `source_row_classification/quarantined_unknown/bak_basic/year=YYYY/month=MM/part.parquet`.
  Falsified if `quarantined_unknown_row_count` is 0 for a real trading session,
  or if either code is found in a raw `source_stock_basic/*.parquet` partition or
  in `identity_aliases.parquet` of a fresh reference generation — which would mean
  the gap was a stale or partial reference refresh rather than vendor coverage.
so_what: >
  This is a coverage-AUTHORITY question, not an implementation defect, and the
  spine contract already anticipated it rather than being surprised by it:
  research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md states that
  "`bak_basic` corroborates rather than replaces lifecycle eligibility. The shard
  and coverage universe is the frozen `lifecycle ∪ PIT` set. Any post-2016
  lifecycle/PIT difference is receipted with samples and blocks completeness."
  The block is therefore the designed alarm firing on real data, and the sample
  receipts it demands are exactly the two retained payloads above. But the
  contract names the universe as the UNION while the collector can only mint an
  identity from the lifecycle master, so a PIT-only row has nowhere to land and
  quarantine blocks `_unit_done` permanently. Every repair redefines what the
  eligible A-share universe IS — admit PIT-only rows on code-range-derived
  identity with `pit_witness_only` provenance, exclude never-listed pipeline
  names as a named `known_excluded` family, or change the witness — and that
  choice sets the denominator for every eligibility rate, target and access class
  downstream. Relaxing the quarantine gate instead would be fail-open in exactly
  the way the program already refused for the `trade_cal` exact-range check.
  Escalated to Sol under `DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION` return-gate 10.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-26
verified_by: >
  Canary run 32950379014 (mode=canary, max_requests=12, 2024-01-02, ref
  claude/cn-limit-canary-rebuild) returned stage `pit_universe_incomplete` with
  requests_made 1 and capped false; the private store's collection_state records
  bak_basic unit 20240102 as status failed / reason
  quarantined_unknown_source_rows with 5344 = 5342 + 0 + 2; the two retained raw
  payloads name 300114.SZ and 603361.SS; and searching every
  `source_stock_basic/*.parquet` partition of generation
  ref-20260826T002451670234Z-1b644e5d5e2c (5,889 rows, G and P partitions empty)
  plus `identity_aliases.parquet` (6,136 rows) returned zero matches for either code.
---

# The PIT witness outruns the lifecycle witness

Found driving Sol's post-epoch rebuild to a `stage=complete` canary under
`DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`. `pit_universe` had never once
executed against the live vendor before this run, which is why a contract clause
written in August only fired now.

Reaching it at all required first fixing
[[CNLI-BAK-BASIC-ZERO-LIST-DATE-SENTINEL]] — the same 603361 row killed the
whole unit with a hard parse error before it could ever be classified. Sibling
epoch findings: [[CNLI-MAINLAND-CALENDAR-EPOCH-1992-JOINT-COMPLETE]],
[[CNLI-SESSION-CLOCK-AXIS-IGNORES-REQUESTED-RANGE]].

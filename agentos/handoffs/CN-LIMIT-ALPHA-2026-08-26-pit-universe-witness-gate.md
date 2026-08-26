---
workstream: WS:CN-LIMIT-ALPHA
session: claude/cn-limit-canary-rebuild
model: fable
ended_because: blocked
mission: >
  Complete Sol's post-ruling sequence: clean-rebuild the private spine under the
  frozen 1992 epoch, then drive exactly one bounded canary to `stage=complete`
  across the previously unvisited pit_universe, name_history and daily stages.
state_before: >
  Epoch merged and live on main (19df24573e72): MAINLAND_CALENDAR_EPOCH
  1992-01-01 under definition mainland-joint-complete-v1, pre-epoch typed
  PRE_EPOCH_SOURCE_UNSUPPORTED, BULK_HISTORICAL_BACKFILL_READY False. Private
  store still carried the repaired-in-place trade_cal plane, including two units
  marked complete with no artifact.
changed:
  - {path: collectors/china_tushare_spine.py, what: "_iso recognises TuShare's all-zero date sentinel as a null date (fail-closed: a null list_date narrows eligibility, an invented one would widen it). Malformed dates still raise."}
  - {path: tests/test_china_tushare_spine.py, what: "4 tests pinning both directions of the sentinel plus a real normalise_bak_basic row with list_date '0' landing with identity, session position, null list_date, zero quarantine and a balanced source-row equation."}
  - {path: agentos/discoveries/DSC-CNLI-BAK-BASIC-ZERO-LIST-DATE-SENTINEL.md, what: "the defect."}
  - {path: agentos/discoveries/DSC-CNLI-BAK-BASIC-PIT-ROWS-ABSENT-FROM-STOCK-BASIC-WITNESS.md, what: "the gate underneath it."}
verified:
  - claim: The trade_cal plane was rebuilt cleanly, not repaired in place
    command: "rebuild_prep --apply, then six bounded canary windows at ref=main"
    result: "PASS — deleted 33 partitions / 68 receipt dirs / 67 ledger units, preserving the identity generation and all other endpoint units so no identity call was re-bought; rebuilt to 66/66 terminal trade_cal units with ZERO 1991 units and year-pure partitions."
  - claim: The epoch holds on the rebuilt store
    command: "compile_market_sessions(store, CALENDAR_HISTORY_START, 2024-01-02)"
    result: "PASS — 7,807 sessions, first 1992-01-02, last 2024-01-02."
  - claim: The zero-sentinel fix works against the REAL vendor, not only in tests
    command: "gh workflow run tushare-spine-backfill.yml --ref claude/cn-limit-canary-rebuild -f mode=canary -f max_requests=12 -f start=2024-01-02 -f end=2024-01-02"
    result: "PASS — run 32950379014 concluded success and advanced past the crash to stage pit_universe_incomplete; the four prior runs on the same window died with SpineError: invalid date '0'."
  - claim: The canary envelope was never widened
    command: "Every dispatch used mode=canary, max_requests=12, a 1-day window, ref pinned."
    result: "PASS — every result reported bulk_historical_backfill_ready false; calendar windows reported capped true with stage calendar_request_cap; allow_bulk never passed; mode=backfill never dispatched."
  - claim: The two unclassifiable rows are vendor coverage, not a stale reference generation
    command: "Searched every source_stock_basic/*.parquet partition and identity_aliases.parquet of generation ref-20260826T002451670234Z-1b644e5d5e2c."
    result: "PASS — 5,889 raw rows (L 5,550 / D 338; all G and P partitions EMPTY), 6,136 aliases, zero matches for 300114.SZ or 603361.SS."
unresolved:
  - >
    THE GATE (Sol, return-gate 10). `pit_universe` cannot reach a terminal unit:
    5,344 = 5,342 + 0 + 2 with two quarantined rows, and quarantine must be zero
    for `_unit_done`. `collect_spine` stops at pit_universe, so `stage=complete`
    is UNREACHABLE until this is ruled. Two distinct classes, and they may not
    deserve the same answer: (1) 603361.SS, approved-but-never-listed, zero
    list_date and zero shares — arguably a named `known_excluded` family, and
    note TuShare returns ZERO stock_basic G rows on every exchange, so no
    approved-unlisted universe exists from that endpoint; (2) 300114.SZ, a
    genuinely TRADED security on that session that the CURRENT stock_basic
    snapshot no longer publishes — excluding it would silently shrink the PIT
    universe and bias every downstream denominator, which is the opposite of
    what the contract's `lifecycle ∪ PIT` union says.
  - >
    Whether a PIT-only row may take an identity minted from the official
    code-range rules (300xxx -> ChiNext etc., which the contract already
    specifies) tagged `pit_witness_only`, rather than requiring a lifecycle
    master hit. That is the smallest repair consistent with the union, but it
    changes what the eligible universe IS and therefore every eligibility rate,
    target and access class — which is why it is not being taken unilaterally.
unverified:
  - >
    Whether the quarantine rate stays at 2 rows per session or grows on older
    dates. Only ONE session (2024-01-02) has ever been collected. A rate that
    rises going back in time would make this structural rather than marginal.
  - >
    name_history and all five daily endpoints STILL have never executed against
    the vendor — pit_universe blocks them.
next_actions: >
  1. SOL: rule the pit_universe witness-coverage question above. Fable has NOT
     chosen among the options and has NOT relaxed the quarantine gate.
  2. After the ruling: implement it, then resume bounded windows to
     `stage=complete` (the calendar is already rebuilt, so the acceptance canary
     is a single window: pit 1 + name <=5 + daily 5 = <=11 against the cap of 12).
  3. Only then the SEPARATE technical-readiness PR for the bulk gate, then the
     resumable range campaign, then the completeness manifest.
do_not_redo:
  - >
    Do NOT relax the quarantined_unknown gate in `_unit_done` to reach
    stage=complete. Fail-open, and the spine contract explicitly requires that a
    post-2016 lifecycle/PIT difference "is receipted with samples and blocks
    completeness" — the block is the designed alarm, working.
  - >
    Do NOT re-derive the epoch or re-run the census. Frozen at 1992-01-01,
    definition mainland-joint-complete-v1, merged at 19df24573e72.
  - >
    Do NOT widen `_iso`'s sentinel branch beyond an ALL-ZERO run. Substring or
    try/except spellings would swallow genuinely malformed dates.
  - >
    Do NOT promote BULK_HISTORICAL_BACKFILL_READY or dispatch mode=backfill.
danger_areas:
  - >
    The lifecycle witness is a CURRENT snapshot used to classify HISTORICAL
    sessions. Any security the vendor stops publishing becomes unclassifiable on
    every past date it traded, so this gate is time-asymmetric: it can only get
    worse the further back the campaign reaches.
  - >
    A per-field parse failure could discard a whole unit's 5,344-row source
    accounting. The zero-sentinel fix removes one instance; the shape remains
    wherever a shared coercer meets an endpoint whose null vocabulary it was
    never taught.
  - >
    A pre-rebuild backup of the private store sits at
    ~/.local/share/macro-dashboard/china_tushare_spine.prerebuild-20260826. It
    holds the OLD 1991-anchored trade_cal plane and must never be promoted; keep
    it only as the evidence archive for the superseded era.
---

# The canary reached pit_universe and stopped there

Sol's rebuild instruction was executed exactly: the trade_cal plane was deleted
and re-collected under the frozen epoch rather than repaired in place, and the
identity generation was preserved so no identity call was re-bought.

The acceptance canary did NOT reach `stage=complete`, and this handoff does not
claim otherwise. It got one stage further than any run before it, which is how
the gate below was found at all: fixing the zero-sentinel crash
(`DSC:CNLI-BAK-BASIC-ZERO-LIST-DATE-SENTINEL`) did not unblock `pit_universe` —
it revealed `DSC:CNLI-BAK-BASIC-PIT-ROWS-ABSENT-FROM-STOCK-BASIC-WITNESS`
underneath, which is an authority question the spine contract anticipated in
writing and deliberately left blocking.

Predecessor: `agentos/handoffs/CN-LIMIT-ALPHA-2026-08-26-calendar-epoch-execution.md`.

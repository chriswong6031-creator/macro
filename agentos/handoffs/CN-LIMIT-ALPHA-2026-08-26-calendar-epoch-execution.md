---
workstream: WS:CN-LIMIT-ALPHA
session: claude/cn-limit-alpha-coo-handoff-3cb8e8
model: fable
ended_because: complete
mission: >
  Execute Sol's DEP-EXACT calendar-epoch architecture ruling: run the required
  outcome-blind source census, audit every `market_session_position` consumer for
  absolute-magnitude dependence, and — only if both stop conditions clear —
  re-anchor the mainland session axis to a frozen, definition-versioned epoch with
  pre-epoch history typed `PRE_EPOCH_SOURCE_UNSUPPORTED`.
state_before: >
  DEP-EXACT was parked on a hard executive gate. The full-A spine contract fixed a
  1991-01-01 calendar anchor requiring exact SSE/SZSE calendar-day equality, but
  TuShare returns 182 of 365 days for SZSE 1991, so `collect_calendars` could never
  reach ready and every downstream stage was blocked. 67 of 68 exchange-year units
  were terminal. No session clock had ever been compiled. `BULK_HISTORICAL_BACKFILL_READY`
  False; bounded canary envelope intact.
changed:
  - {path: collectors/china_tushare_spine.py, what: "frozen definition-versioned epoch (MAINLAND_CALENDAR_EPOCH 1992-01-01, definition mainland-joint-complete-v1, PRE_EPOCH_SOURCE_STATE); compile_market_sessions now enforces the epoch where the AXIS is built, refuses a pre-epoch start with the typed state, and stamps calendar_epoch/calendar_epoch_definition onto compiled sessions."}
  - {path: scripts/research/cn_limit_calendar_epoch_census.py, what: "new network-free outcome-blind census computing the six ruling criteria per year; prints the full table before applying its trailing decision rule; epoch is an OUTPUT, never a constant."}
  - {path: tests/test_cn_limit_calendar_epoch_census.py, what: "17 tests over synthetic fixture stores (CI has no private store)."}
  - {path: tests/test_china_tushare_spine.py, what: "6 new epoch tests, including one isolating the epoch filter on CONTIGUOUS history so the pretrade-adjacency guard cannot explain the result."}
  - {path: research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md, what: "canonical-clock section re-stated on the frozen epoch; supersedes the 1991-01-01 anchor."}
  - {path: research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md, what: "same re-statement, plus a standing constraint that window/horizon boundaries be expressed as session-position DIFFERENCES."}
  - {path: research/cn_limit_alpha_sol/DEP_EXACT_CALENDAR_EPOCH_CENSUS_2026-08-26.md, what: "generated census receipt (json sibling alongside)."}
  - {path: agentos/discoveries/DSC-CNLI-MAINLAND-CALENDAR-EPOCH-1992-JOINT-COMPLETE.md, what: "the census result."}
  - {path: agentos/discoveries/DSC-CNLI-SESSION-CLOCK-AXIS-IGNORES-REQUESTED-RANGE.md, what: "why re-anchoring is not a constant edit."}
  - {path: agentos/discoveries/DSC-CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS.md, what: "measured contamination in the repaired-in-place store."}
verified:
  - claim: 1992 satisfies all six of the ruling's census criteria and is the earliest year that does
    command: "python3 -m scripts.research.cn_limit_calendar_epoch_census"
    result: "PASS — SSE 366/366 and SZSE 366/366 unique civil dates for 1992, 366 shared dates, parity_mismatch 0; every year 1992..2023 jointly complete with parity 0; both exchanges pretrade_violations=0 and missing_civil_dates=0; final line EARLIEST_JOINTLY_COMPLETE_EPOCH: 1992. 1991 fails only because SZSE contributes 0 rows."
  - claim: No consumer of market_session_position depends on absolute ordinal magnitude
    command: "Routed opus consumer audit over every reference plus alias sweep (session_position, session_ordinal, H3/H5/H10/H21, 21-session, reset, eligibility, grading, band_progress)."
    result: "PASS — MAGNITUDE_DEPENDENCY: NONE. All 19 references are difference-only, schema-name, or fixture-local. The `% n`/`// n` bucketing in engine/session_anchor.py is a DISJOINT symbol bound to data/china/000001.SS.parquet, never to reference/market_sessions.parquet."
  - claim: The frozen R4 evaluation requires no authority-grade pre-epoch outcome
    command: "Read the adopted split in research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md:333-336."
    result: "PASS — PRE_EPOCH_R4_DEPENDENCY: NONE. Train begins 2011; the deepest lookback is the 21-session reset reaching late 2010, nineteen years after the epoch."
  - claim: Nothing anywhere carries an ordinal stamped on the old axis, so no restamp is owed
    command: "find <private store> -type d; find <private store> -name '*.parquet'; git ls-files | grep market_sessions"
    result: "PASS — reference/market_sessions.parquet ABSENT (no clock was ever compiled); daily, event_daily, stk_limit, daily_basic, bak_basic, name_history, pit_universe all absent; no committed artifact holds a numeric ordinal."
  - claim: The epoch is enforced where the axis is built, not by the absence of a pre-epoch file
    command: "compile_market_sessions against the real store with reference/trade_calendar/year=1991.parquet still on disk."
    result: "PASS — compiles 7806 sessions, position 0 = 1992-01-02, position 7805 = 2023-12-29, monotonic and contiguous, zero pre-epoch dates on the axis, 365 SSE-1991 rows excluded and REPORTED. A pre-epoch start raises PRE_EPOCH_SOURCE_UNSUPPORTED."
  - claim: The new epoch tests fail without the fix rather than passing vacuously
    command: "Neutralised MAINLAND_CALENDAR_EPOCH to 1900-01-01 and recompiled the fixture."
    result: "PASS with a caveat that drove a second test — under the 1991-vs-2024 fixture the compile fails on pretrade adjacency, NOT on ordinal shift, so that fixture proves the outcome but not the cause. test_pre_epoch_exclusion_is_the_sole_cause_on_contiguous_history moves the epoch onto contiguous data so only the epoch filter can explain the result."
  - claim: No regression in the collector or the exact-plane consumer
    command: "python3 -m pytest tests/test_china_tushare_spine.py tests/test_cn_limit_calendar_epoch_census.py tests/test_cn_limit_band_progress_w2.py -q"
    result: "PASS — 129 passed."
  - claim: Agent OS records validate
    command: "python3 scripts/agentos.py validate"
    result: "PASS — 0 errors, 43 warnings all pre-existing and unrelated (Prophet US, Stock Identity, CS-V2 review dates)."
unresolved:
  - >
    The two 2024 `trade_cal` units carry `status: complete` with no artifact. The
    clean rebuild drops them, so this resolves as a side effect — but if a future
    rebuild path preserves state, they must be explicitly reopened rather than
    trusted.
  - >
    Whether the ruling's "exactly one bounded real-vendor canary" forbids the
    several bounded windows the rebuild itself needs. Read as referring to the
    ACCEPTANCE canary that must reach `stage=complete`, because a single
    12-request window cannot rebuild 64 calendar units and a reading that makes
    the instruction physically unsatisfiable is the wrong reading. Flagged to Sol
    in the milestone return rather than settled unilaterally.
unverified:
  - >
    The census measured the REPAIRED store, not a cleanly rebuilt one. Partition
    purity and duplicate counts both came back clean, and every count is backed by
    per-unit request receipts, so the epoch answer is not expected to move — but
    the clean rebuild is the first chance to confirm it against freshly collected
    bytes. Re-run the census after the rebuild and compare.
  - >
    No canary has yet reached `stage=complete`. pit_universe, name_history and all
    five daily endpoints have still never executed against the vendor, so the
    epoch's effect on those stages is unobserved.
  - >
    `market_session_position` has never been consumed by a built downstream
    construction — eligibility, access classes and the grade adapter are all
    NOT_BUILT. Constant-offset invariance is therefore proven against the code
    that exists today, not against a future consumer.
next_actions: >
  1. Clean-rebuild the calendar partitions under the new definition — do NOT
     promote the repaired-in-place store (see
     DSC:CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS). Drop
     reference/trade_calendar plus the trade_cal units and re-collect from
     1992-01-01 through bounded canary windows.
  2. Run exactly ONE bounded canary that reaches `stage=complete`, covering the
     previously unvisited pit_universe, name_history and daily stages, with
     BULK_HISTORICAL_BACKFILL_READY still False.
  3. Only then commission the SEPARATE technical-readiness PR for the bulk gate,
     citing request/schema/source-row/accounting/cap/refusal/throughput receipts.
  4. Then the resumable range campaign, closing DEP-EXACT on the sanitized
     completeness manifest.
do_not_redo:
  - >
    Do NOT relax the `trade_cal` exact-range binding check to unblock a
    truncated vendor response. It is fail-open: a truncated response would then
    prove its own truncation legitimate anywhere in the range. Sol's ruling is
    explicit — "Do not relax the exact calendar completeness predicate."
  - >
    Do NOT re-run the epoch census hoping for a different answer, and do NOT
    make the epoch runtime-selected. Sol forbade a dynamic epoch; it is frozen in
    source and moves only by minting a new definition string.
  - >
    Do NOT re-audit market_session_position consumers for magnitude dependence.
    Answered NONE with file:line evidence over an exhaustive census; the one
    literal ordinal assertion is fixture-relative and epoch-invariant.
  - >
    Do NOT impute the missing SZSE 1991 civil dates as closed sessions, and do
    NOT borrow SSE history as exact SZSE history. Both are named prohibitions in
    the ruling.
  - >
    Do NOT promote BULK_HISTORICAL_BACKFILL_READY or dispatch mode=backfill as
    part of the rebuild. The rebuild runs through bounded canary windows.
danger_areas:
  - >
    `compile_market_sessions` derives coverage and open-session sets from EVERY
    landed partition, not from its requested range. The requested range gates
    only the completeness raise. Anything that lands a pre-epoch partition for
    BOTH exchanges would previously have shifted every ordinal silently; the
    epoch filter is now the only thing preventing that, so do not move it out of
    the compile path.
  - >
    A unit's `status: complete` is NOT evidence it landed — the repaired store
    carries two such units whose artifact is gone. Always read `_unit_done`,
    which recomputes artifact receipts and fails closed.
  - >
    The calendar stage needs ~64 requests (2 exchanges x 32 years) against a
    12-request canary cap, so the rebuild takes roughly six resumable windows.
    That is the envelope working as designed, not a defect, and it is not a
    reason to widen the cap.
---

# Calendar epoch executed: the mainland axis is frozen at 1992-01-01

Sol's ruling was executed as written. Both of its named stop conditions were
tested BEFORE implementation and both cleared, so the work proceeded rather than
returning to Sol: no consumer depends on absolute ordinal magnitude, and the
frozen R4 evaluation requires no authority-grade pre-epoch outcome.

Two findings shaped the implementation beyond the literal instruction. First,
moving the anchor constant alone would NOT have re-anchored anything — the axis is
built from all landed partitions, so the epoch had to be enforced at the compile
site (`DSC:CNLI-SESSION-CLOCK-AXIS-IGNORES-REQUESTED-RANGE`). Second, the store
carried measured contamination from the earlier in-place repair, which is the
concrete reason the rebuild instruction is not optional
(`DSC:CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS`).

Preceded by `agentos/handoffs/CN-LIMIT-ALPHA-2026-08-26-exact-truth-canary-clock-gate.md`,
which escalated the gate this handoff closes.

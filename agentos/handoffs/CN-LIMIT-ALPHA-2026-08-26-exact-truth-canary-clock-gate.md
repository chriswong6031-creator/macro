---
workstream: WS:CN-LIMIT-ALPHA
session: claude/cn-limit-alpha-coo-handoff-3cb8e8
model: fable
ended_because: blocked
mission: >
  Fable COO pickup of the CN-Limit remainder program under
  DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION: reconcile and close PR #6207 on its
  existing carrier, then drive Exact Truth Release (DEP-EXACT) through the frozen
  plan -> bounded canary -> reviewed technical gate -> resumable range campaign ->
  completeness manifest sequence.
state_before: >
  PR #6207 open, DRAFT, HOLD-FOR-SOL, head 0520059493c2, exact-head CI red.
  DEP-EXACT had no live canary receipt of any kind. WS DEP-EXACT already
  reconciled to TECHNICAL_CANARY_REQUIRED on the #6207 branch. No CN-Limit
  code had ever executed against the real TuShare endpoints.
changed:
  - {path: collectors/china_tushare_spine.py, what: "three defect classes found by first real vendor contact: non-canonical identity classification (#6431), full 13-site sweep of that class (#6438), trade_cal partition-year leak (#6446)."}
  - {path: tests/test_china_tushare_spine.py, what: "19 new discriminating tests across the three fixes; 73 passing total."}
  - {path: agentos/discoveries/DSC-CNLI-TUSHARE-DELISTED-DUMP-CARRIES-NONCANONICAL-LEGACY-CODES.md, what: "vendor delisted universe carries non-canonical legacy codes."}
  - {path: agentos/discoveries/DSC-CNLI-CALENDAR-PARTITION-YEAR-LEAKED-ACROSS-LOOPS.md, what: "leaked loop variable wrote every trade_cal unit to one wrong year partition; real store corruption measured and repaired."}
  - {path: agentos/discoveries/DSC-CNLI-TUSHARE-SZSE-CALENDAR-STARTS-MID-1991.md, what: "the gate below: vendor SZSE calendar cannot meet the contract's fixed 1991-01-01 anchor."}
verified:
  - claim: PR #6207 merged to main with the Chairman compliance ruling and canary envelope intact
    command: "gh pr view 6207 --json state,mergeCommit"
    result: "PASS — MERGED, squash 76407bce899afa6c7e8939e702f93d2bd9045310. Exact-head ci + fences green on linear head 7daecb2cfde2."
  - claim: The linearized head was semantically identical to the adversarially reviewed head
    command: "git merge-tree --write-tree origin/main 0520059493c2 vs git rev-parse cnli-linear^{tree}"
    result: "PASS — both trees 997f3dbd00a7fdc1a8043ee1fd34d894f82207ee, byte-identical; interim main commits touched none of the PR's 37 files."
  - claim: WS:CN-LIMIT-ALPHA is reconciled on main under the new DEC
    command: "git show origin/main:agentos/workstreams/WS-CN-LIMIT-ALPHA.md"
    result: "PASS — owner: fable; DEP-EXACT is TECHNICAL_CANARY_REQUIRED with CHAIRMAN_VERIFIED_PRIVATE / SATISFIED; no vendor-letter prerequisite anywhere on main."
  - claim: The bounded canary envelope was never widened or bypassed
    command: "Every dispatch used mode=canary max_requests=12 start=2024-01-02 end=2024-01-02; result JSON read per run."
    result: "PASS — every run reported bulk_historical_backfill_ready: false; cap-hits reported capped: true with failures: []; no allow_bulk; mode=backfill never dispatched."
  - claim: The trade_cal partition-year fix is proven live, not only in tests
    command: "Read every reference/trade_calendar/year=*.parquet after the repair and compare each file's cal_date years to its filename year."
    result: "PASS — all rebuilt partitions year-pure across SSE+SZSE, 730 rows per ordinary year and 732 for leap-year 2020."
  - claim: Real production request receipts exist and bind to their requests
    command: "Read receipts/requests/*/*/*.json from the private store."
    result: "PASS — 84 receipts: 76 accepted, 7 accepted_empty, 1 rejected_contract (the gate below). 32,932 source rows. Each carries request_contract_sha256, response_semantic_sha256, exact returned columns."
  - claim: Non-canonical identity classification works against real vendor payloads
    command: "Inspect receipt non_canonical_identity_row_count / known_excluded_noncanonical_row_count and unit accounting."
    result: "PASS — stock_basic SSE:D recorded 1 non-canonical row classified known_excluded (the T-prefixed legacy code), unit equation balanced 147 = 146 + 1 + 0 with quarantined 0; fund_basic D recorded 18 non-canonical rows left unclassified rather than force-fitted."
  - claim: Measured request throughput for campaign feasibility
    command: "Compare observed_at timestamps across receipts within one run."
    result: "PASS — 12 stock_basic calls in 16s (~1.3 s/request); 68 trade_cal calls to build the 1991-2024 reference calendar."
unverified:
  - claim: DEP-EXACT is complete
    what_would_verify: "It is NOT. The canary has never reached stage=complete. pit_universe, name_history and the daily endpoints have never executed against the vendor, no completeness manifest exists, and BULK_HISTORICAL_BACKFILL_READY remains False and unpromoted."
  - claim: The full-A exact spine can complete within acceptable runner budget
    what_would_verify: "Only the real resumable campaign proves this. The one hard datum so far is ~1.3 s/request and 68 requests for the reference calendar alone."
  - claim: SZSE trade_cal coverage begins 1991-07-03
    what_would_verify: "The 182-of-365 shortfall is measured; the specific start date is INFERRED from row-count arithmetic and was never observed, because the response was rejected before storage. Landing the raw frame, or enriching the receipt with min/max cal_date, would settle it."
unresolved:
  - "HARD GATE FOR SOL (return-gate 10): the vendor cannot satisfy the full-A contract's canonical market clock. See the ruling request below. The DEP-EXACT lane is stopped pending it; nothing downstream can proceed because calendar readiness gates every later stage."
next_actions:
  - "SOL: rule on the calendar anchor / coverage-authority question below. Fable has NOT chosen among the options and has NOT modified the validator."
  - "After the ruling: implement it, resume bounded canary windows to stage=complete, then open the separate reviewed BULK_HISTORICAL_BACKFILL_READY promotion PR citing the canary receipts, then the resumable full-A campaign and the sanitized completeness manifest."
do_not_redo:
  - "Do not relax `_validate_response_binding`'s trade_cal exact-range check to unblock the canary. That is fail-open: a truncated response anywhere in the range would then prove its own truncation legitimate."
  - "Do not re-dispatch mode=backfill or flip BULK_HISTORICAL_BACKFILL_READY to escape the block. The gate is technical and its evidence is not yet complete."
  - "Do not re-run the three merged fixes' investigations; their mechanisms are recorded as DSC records with falsifiers."
  - "Do not treat 1991-07-03 as an established fact. It is an inference from a row count."
danger_areas:
  - "`market_session_position` is described by the contract as ONE IMMUTABLE ordinal anchored at 1991-01-01. Whatever resolves this gate defines that ordinal's origin, and every downstream horizon (including the frozen FIRST_SEALED_UP_H10 target), eligibility denominator and exact-event join inherits it. This is why it was not self-authorized."
  - "A fail-closed artifact check catches a bad write only AFTER it happens: the partition-year leak was caught by `_set_unit`, but `_upsert_partition` had already merged 365 foreign-year rows into the wrong file. After any 'partition path disagrees' failure the STORE needs repair, not just a code fix."
  - "Each of the five canary windows exposed a different latent defect invisible to the test suite, because this was the first execution against the real vendor. Absence of recent failures is not proof; only stage=complete is."
prs: [6207, 6431, 6438, 6446]
decisions:
  - DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION
  - DEC:CNLI-EXACT-CENT-PRIMARY
  - DEC:CNLI-ERA-IS-EFFECTIVE-AUTHORITY
  - DEC:CNLI-COVERAGE-ATOMIC-CHALLENGER
discoveries:
  - DSC:CNLI-TUSHARE-DELISTED-DUMP-CARRIES-NONCANONICAL-LEGACY-CODES
  - DSC:CNLI-CALENDAR-PARTITION-YEAR-LEAKED-ACROSS-LOOPS
  - DSC:CNLI-TUSHARE-SZSE-CALENDAR-STARTS-MID-1991
---

# Bounded ruling request — the canonical market clock cannot be built as specified

## 1. The gate in one paragraph

`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` defines the canonical
market clock: it "begins at the fixed 1991-01-01 calendar anchor, requires exact
SSE/SZSE calendar-day and open-session equality", assigns "one immutable
`market_session_position`", and requires of `trade_cal` "every requested calendar
day". TuShare returns all 365 days for SSE 1991 and exactly **182** for SZSE 1991.
The clock as specified therefore cannot be constructed from the licensed source.
Because `collect_calendars` computes `ready = all(_unit_done(...))` over every
exchange-year, this single unit blocks the calendar stage permanently, and with it
`pit_universe`, `name_history` and every daily endpoint. 67 of 68 exchange-year
units are terminal; SZSE 1991 is the only gap.

## 2. Why Fable did not decide this

Return-gate 10 of `DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION` reserves "unresolved
company-level ambiguity in point-in-time clocks ... null/coverage authority ...
that no current owner contract resolves". The current owner contract does not
resolve it — it *asserts* the condition the vendor cannot meet. Every available
repair changes the origin of an immutable session ordinal that the frozen
`FIRST_SEALED_UP_H10` target, every eligibility denominator and every exact-event
join inherit. That is architecture, not implementation.

The contract does contain an analogous rule for a venue *absent* from `trade_cal`:
"TuShare does not publish BSE in the documented `trade_cal` venue list, so BSE
explicitly inherits that consensus from launch." Extending that to a venue that IS
published but starts late is a plausible reading — and precisely the kind of
extension that must be ruled, not assumed.

## 3. Options, with their costs

**A — Per-venue calendar anchor.** SSE from 1991-01-01, SZSE from its observed
coverage start. Honest to the source. Cost: "exact SSE/SZSE calendar-day equality"
becomes per-venue, and `market_session_position` needs a stated rule for the window
where only one venue exists.

**B — Move the common anchor forward** to the first date both venues cover. Keeps a
single unambiguous clock and exact equality intact. Cost: discards roughly half of
1991 for SSE, which is real data the vendor does supply.

**C — Explicit not-covered state for the SZSE pre-coverage window.** SZSE inherits
the SSE consensus for 1991-01-01..coverage-start, marked `not_covered` rather than
measured — the BSE pattern applied to a late-starting venue. Keeps the 1991-01-01
anchor. Cost: the earliest SZSE sessions are inherited, not observed, and that
provenance must survive into every downstream join.

**D — Declare the anchor era out of scope** for the primary target and start the
canonical clock at a modern date. Cost: forecloses deep-history work later.

Fable's read, offered as input and not as a decision: **C** is most consistent with
the contract's own precedent and with "missing is never zero", and **A** is the most
honest to the source; **B** discards real data to buy tidiness. Any of them needs the
provenance to be legible downstream, which is the part that must not be improvised.

What Fable explicitly did **not** do: relax the exact-range validator. That would be
fail-open — a truncated response would thereafter prove its own truncation
legitimate anywhere in the range — and it would silently convert a coverage
boundary into apparent measured truth.

## 4. What is already proven, and what this does not block

Milestone 0 is closed: #6207 is merged, the Chairman compliance ruling and the
bounded canary envelope are intact on main, and no vendor-letter prerequisite
survives anywhere.

The canary has produced genuine production evidence — 84 receipts (76 accepted,
7 empty, 1 the rejection above), 32,932 source rows, request/response hash binding,
live-proven non-canonical classification, resumable cap-refusal behaviour, and
~1.3 s/request measured throughput. Three latent defects were found and fixed
(#6431, #6438, #6446), each invisible to the suite until real vendor contact.

DEP-EXACT is **not** complete and is not being represented as complete.
`BULK_HISTORICAL_BACKFILL_READY` stays False and unpromoted: the §10C gate requires
canary evidence this canary has not yet been allowed to finish producing.

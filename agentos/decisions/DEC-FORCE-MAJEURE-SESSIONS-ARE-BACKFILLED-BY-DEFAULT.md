---
key: FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT
question: >
  When an infrastructure outage costs a trading session its board, is backfilling
  the session the DEFAULT, or an exception requiring a per-case charter and an
  origination event that can be replayed byte-for-byte?
answer: >
  Backfill is the DEFAULT. Force majeure — an infrastructure outage, as distinct
  from a data-correctness defect — authorizes reconstructing the missing session
  without a fresh per-case charter and without a pre-existing bake-time board to
  replay. Reconstruction is permitted even where no origination event executed,
  and reconstructed rows enter the forward ledger with NO reconstructed/live
  distinction and no marking. The operator has weighed and accepted the resulting
  ledger effect. This supersedes the ad-hoc practice in which each outage needed
  its own operator-ordered charter (PROPHET_OUTAGE_BACKFILL_2026_08) and in which
  "no origination event executed" was itself sufficient grounds to refuse.
rationale: >
  Two prior refusals were read by later sessions as a standing "do not backfill"
  law, and it never was one: the 2026-08-11 charter is titled "force-majeure,
  operator-ordered" and WAS executed, and its §2 refusal was scoped to
  2026-08-03→08-06 for a data reason (those boards ran on a frozen stale alpha
  panel, so "backfilling with corrected dates fixes the dates and leaves the
  rankings wrong"). No general rule existed in CLAUDE.md, AGENTS.md,
  DO_NOT_REBUILD.md, or agentos. The absence of a standing policy is what made
  every outage re-litigate the question and left the 2026-08-14 session
  unrecovered by default rather than by decision. The operator's standard is that
  an infrastructure outage is not the user's problem and a missing board is worse
  than a reconstructed one; the forward ledger's degradation from reconstructed
  rows was judged acceptable against a visibly stale product. This record makes
  the default explicit so no future session refuses a backfill by citing a law
  that does not exist.
  ACCEPTED COST, recorded so it is never discovered by surprise: a session
  reconstructed after the fact is built from inputs that have since advanced, so
  its picks carry information the live bake could not have had. With no
  reconstructed/live flag, graded forward-ledger statistics cannot separate those
  rows, and the published track record is to that extent flattering rather than
  measured. This is a deliberate operator trade, not an oversight.
alternatives:
  - option: Permit reconstruction but flag rows via origination_disclosure so the ledger can separate reconstructed from live-originated picks
    why_not: >
      Offered and explicitly declined by the operator 2026-08-18 in favour of the
      simpler rule. Retained here as the obvious reversal path if graded stats are
      ever needed at measurement grade.
  - option: Leave the ad-hoc charter practice unchanged and skip the 2026-08-14 session
    why_not: >
      Declined. It is the status quo that produced a five-day stale board and a
      session lost by default rather than by decision.
  - option: Delete the charter's §2 refusal and the disclosed_gaps.json entry outright
    why_not: >
      Rejected on inspection as the wrong target. §2 is a dated adjudication record
      (deleting it rewrites history), and us-board-frozen-alpha-2026-08 in
      data/us_board_ledger/disclosed_gaps.json marks a window whose RANKINGS are
      known-wrong from a GHA cache regression — removing it would hide a data defect
      rather than enable a backfill. That entry is NOT the clause this record relaxes
      and stays exactly as it is, CI-enforced by tests/test_grade_us_board.py:1101.
evidence:
  - "Census 2026-08-18: grep over CLAUDE.md, AGENTS.md, research/DO_NOT_REBUILD.md, agentos/ found NO general anti-backfill law; the only CI-enforced entry is data/us_board_ledger/disclosed_gaps.json key us-board-frozen-alpha-2026-08 (tests/test_grade_us_board.py:1101), scoped to 2026-08-01→08-06."
  - "research/PROPHET_OUTAGE_BACKFILL_2026_08.md:1-3 — the charter is itself a force-majeure override, operator-ordered 2026-08-11 ~00:05Z, and was executed."
  - "research/PROPHET_US_AVAILABILITY_HARDENING_2026-08-14.md:149-155 — the Aug-11 refusal cites 'no origination event executed' plus uncollected bars; that is the clause this record relaxes."
  - "2026-08-14 session: gh api runs/31848262472 → conclusion=cancelled, total_count=0 jobs. The run was superseded while queued (created 22:52:07Z, updated 23:45:42Z) and never created a job, so no board exists to replay; git log shows no site/prophet/index.json checkpoint for 08-14 or 08-15."
  - "scripts/backfill_prophet_outage.py is 1,701 lines hard-pinned to the 2026-08-09 refused bake (exact commit SHAs and us_standouts.json bytes); it is NOT a reusable harness and cannot be pointed at another session."
  - "build_stock_library.py has no as-of capability (as_of derives from the panel on disk), so a vintage-correct PIT replay harness does not exist — noted in the charter §2."
affects:
  - "WS:PROPHET-US-AVAILABILITY"
  - "research/PROPHET_OUTAGE_BACKFILL_2026_08.md"
  - "research/PROPHET_US_AVAILABILITY_HARDENING_2026-08-14.md"
  - "scripts/backfill_prophet_outage.py"
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-18
---

## What changes in practice

1. A session lost to an **infrastructure outage** (cron strand, concurrency
   supersede, push-blocking ruleset, runner wedge, host contention) is backfilled
   as the default action. No new operator charter is required, and "no origination
   event executed" is no longer grounds to refuse.
2. Reconstructed rows are written into the forward ledger **unmarked**, on the
   same footing as live-originated rows.
3. A session lost to a **data-correctness defect** — corrupted, frozen or stale
   inputs that make the rankings themselves wrong — is a different question and is
   NOT covered here. `us-board-frozen-alpha-2026-08` stays disclosed and
   `backfillable: false`; fixing dates there would leave the rankings wrong, which
   is a defect to disclose, not an outage to recover.

## The blocker this record does not remove

Policy now permits reconstructing 2026-08-14, but **no tool can currently do it**.
`scripts/backfill_prophet_outage.py` is pinned to one historical event, and there
is no point-in-time board replay harness — `build_stock_library.py` derives
`as_of` from whatever panel is on disk. Executing a 08-14 backfill therefore needs
a PIT replay harness commissioned as its own build, with its own acceptance gates.
Until that exists, the honest product statement for the 14th is a disclosed gap,
not a silently missing day.

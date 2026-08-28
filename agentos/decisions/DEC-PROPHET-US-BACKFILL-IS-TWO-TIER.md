---
key: PROPHET-US-BACKFILL-IS-TWO-TIER
question: >
  The Chairman ordered every missing Prophet US date "properly backfilled" with
  override authority on blockers (2026-08-27). Sessions exist where nothing fresh
  was published (boards late or stale at open; the 5-minute live lane dark from
  2026-07-30 to 2026-08-26). What may enter which record?
answer: >
  Three tiers. (1) The graded forward ledger records only what was PUBLISHED at
  the time; gap sessions carry typed force-majeure rows (cause era + receipt
  links), never reconstructed picks. (2) Journal-recovered VERBATIM production
  output is legitimate history: PR #6484's recovery of 588 self-checking
  evaluator passes across 7 sessions is recovery, not synthesis, and stands
  (schema prophet_live.recovered_events/v1, labeled recovered end to end).
  (3) Counterfactual reconstruction (replaying today's code over frozen inputs
  for sessions where the system published nothing and recorded nothing) may be
  built only as a labeled non-graded display tier and never enters grading or
  performance stats. August 2026 outcome under this ruling: zero fabrication was
  needed — every session's board eventually minted except the asof-2026-08-11
  build (one true mint hole, recorded as force-majeure), and the live lane
  accrues from its first genuine session (2026-08-26) forward.
rationale: >
  A pick nobody could have acted on must never be graded as if offered; one
  discovered fabrication would cost more credibility than every outage combined.
  Conversely, output the production system emitted contemporaneously to its own
  journal (declared events=N then printed N lines, exit-3 on mismatch) is real
  history that failed only at the publish step — refusing it would hide truth.
  The outage days stay visible as outage days: accountability is part of the
  product's honesty (nulls-printed law).
alternatives:
  - option: Grade reconstructed picks into the forward ledger under Chairman override
    why_not: >
      Chairman authority unblocks process, not evidence. Users could not act on
      unpublished picks; grading them fabricates a track record and violates the
      standing epistemics law that replay/LLM output never originates graded
      signals. Discoverable and fatal to the product.
  - option: Leave gaps entirely unrecorded
    why_not: >
      Hides the outage, breaks continuity views, and defies the directive; the
      Chairman explicitly witnessed the force-majeure days.
evidence: >
  Origination receipts 32786396919/32908543584-era prove Aug-24/25 minted 11/9
  plans (no board backfill needed); site/prophet/index.json recorded_at
  histogram (08-21:27, 08-24:11, 08-25:9); git history walk shows the only
  missing mint is the asof-2026-08-11 build (Aug-12 force-cancel incident);
  #6484's receipt (passes_parsed 588, sessions 7, source journal archived +
  sha256-pinned at data/pit_replay/prophet_live_recovery/) spot-checked against
  the VPS journal (84 events= declarations on 2026-08-25) and
  data/prophet_live/forward.parquet now exists on main; live-lane restoration
  proof 2026-08-26 (84 publishes 13:28:09→20:23:08Z, 180 states, R2==served).
  Full ledger: research/PROPHET_US_AVAILABILITY_LEDGER_2026-08.md.
affects: ["data/prophet_live/forward.parquet", "data/pit_replay/prophet_live_recovery/", "research/PROPHET_US_AVAILABILITY_LEDGER_2026-08.md", "site/prophet/index.json"]
confidence: high
reversibility: easy
decided_by: coo-fable-ceo-takeover-session
decided_at: 2026-08-27
---

Chairman directive context: "at least 10 force majeure days this month … ensure
that all dates that are missing are properly backfilled, with full authority and
authorization from Chairman and Chairman override on anything that blocks the
backfill." This ruling executes the directive's intent — a complete, continuous,
credible record — while keeping the one line that protects the asset the
directive exists to protect. The honest August accounting that resulted: 14/18
sessions fresh at standard time; Aug 6/12/17 stale at open (late boards); Aug 26
board ~5h late (schedule strand, rescue-caught); one true mint hole
(asof-2026-08-11); live intraday lane 1/18 sessions (Aug-26 only), with 7
sessions carrying journal-recovered genuine events (#6484).

---
key: SRC-A1-DRIP-CURSOR-DEFERS-REVISION-PROOF
claim: >
  SRC-A1's collection lane drips the 200 STALEST names per night across a
  1,506-name universe with a 6-day freshness skip, so consecutive nightly
  collections are DISJOINT security sets — a second natural collection proves
  accrual, session lineage and as-known immutability, but cannot prove
  revision, supersession, correction-lineage or fiscal-rollover semantics,
  which stay unexercised until the cursor wraps at roughly 7.5 nights.
falsifier: >
  Read any two consecutive collection sessions out of
  data/revisions/expectation_observations.parquet and intersect their
  ticker_compat sets — a non-empty intersection refutes the disjointness claim.
  Equivalently, a non-zero count of non-null supersedes_observation_id, or any
  correction_state value outside {original, missing}, refutes the
  "machinery never fired" half. Measured 2026-08-26 across the only two
  production sessions: 0 shared tickers, 0 shared logical keys, 0 of 22,344
  rows carrying a supersession.
so_what: >
  A future session must not read "a second natural collection succeeded" as
  proof that SRC-A1 handles revisions, and must not flip SRC-A1 to PROVEN_LIVE
  on a same-week second night. The comparable same-security/same-metric/
  same-horizon slice the proof law requires only becomes observable after the
  cursor wraps — first re-observations expected on or after 2026-09-01, since
  A-to-BOH was collected 2026-08-25 and _FRESH_DAYS=6 gates re-eligibility.
  Waiting for that natural wrap is the lawful path; widening cadence, batch
  size or universe to force an overlap is a mutation the frozen contract gates
  behind operating evidence and must not be done merely to obtain proof faster.
kind: data
verified_at: 2026-08-26
verified_by: >
  Per-session groupby over the two production collections extracted from
  commits be061c6d49e9b9e40cea5b01b9b7b9acacdc757a and
  576959b11804d4d7a0b0f19d443b232234c00ce7: session 74cfd4a71620 covers 200
  tickers A->BOH, session d9fa989a6c9e covers 199 tickers BOOT->DHI, ticker
  overlap 0, logical-key overlap 0. Cursor mechanics read at
  collectors/equity_revisions.py:67 (_FRESH_DAYS = 6) and :612-634
  (fetch_revisions drips max_new=200 stalest names). Universe size 1,506 =
  breadth 503 + midcap_breadth 400 + smallcap_breadth 603 from
  data/<grp>/constituents.parquet at origin/main.
scope:
  - "collectors/equity_revisions.py"
  - "data/revisions/expectation_observations.parquet"
  - "data/revisions/expectation_attempts.parquet"
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
confidence: verified
---

The SRC-A1 proof law asks for a later scheduled collection of a comparable
same-security / same-metric / same-horizon slice. The lane's drip design means
consecutive nights cannot supply one. This is a property of the collector's
freshness cursor, not a fault in the second run: the run behaved lawfully and
proved what a disjoint second collection CAN prove.

What the second collection did prove: independent session and attempt lineage,
strict append-only accrual, byte-equal retention of all 11,200 prior
observations across all 30 columns, distinct provider and system clocks on
every row, and no backfill into an earlier cutoff.

What it structurally could not prove, and what the wrap-night audit must
therefore still test: unchanged payloads not fabricating revisions, changed
payloads appending and superseding with explicit lineage, failure and null
states not overwriting good prior evidence, and fiscal rollover not being
misclassified as an analyst revision.

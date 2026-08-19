---
key: W3-FIRST-DURABLE-COMPLETE-OBSERVATION-WINS
question: >
  When multiple Prophet publications carry the same economic stamp_date, which
  W3 observation is canonical, and what happens to later same-stamp board bytes?
answer: >
  The first durably committed complete W3 observation (nonempty paired + family
  + coverage parts) for a stamp_date is canonical. A later Prophet publication
  with the same stamp is a SAME_STAMP_REVISION_REFUSED: frozen identities are
  not rewritten, honest-N does not increment, no second session is created, and
  the refusal is diagnostic telemetry rather than a crash. Identity mismatch
  while constructing a brand-new (incomplete) first observation remains fatal.
  No float tolerance, averaging, latest-wins, or outcome authority. This law
  lives only inside the W3 measurement plane; the general Prophet product may
  still republish (#5878).
rationale: >
  stamp_date / board as_of names an economic session, not a publication version
  (DSC:PROPHET-BOARD-ASOF-IS-ECONOMIC-SESSION-ID). Production run 32084697588
  rebuilt F1_TECHNICAL_CONFLUENCE from a later same-stamp receipt
  (3.696969697 → 3.8484848485). Keep-first correctly held the frozen family
  bytes, but persist order (paired → family → sessions) meant the lawful
  refusal never wrote PR-3D session history, and the exception reded the
  nightly forever. Treating a complete frozen stamp's later publication as a
  crash re-litigates keep-first every night. Treating it as a new session would
  inflate honest-N. The repair is: refuse the revision, keep the first complete
  observation, persist sessions/status, and preflight new stamps so a later
  grain cannot land paired-new / family-missing.
alternatives:
  - option: Latest same-stamp publication wins / overwrite the frozen W3 parts
    why_not: >
      Violates the frozen prereg. The first durable observation is the
      prospective sample. Latest-wins is look-ahead from a later board build.
  - option: Average or apply float tolerance on mean_abs_rank_delta
    why_not: >
      The production delta is a real board republish, not floating-point noise.
      Tolerance would silently accept identity changes and un-freeze the race.
  - option: Count each publication as another W3 session
    why_not: >
      Honest-N is distinct economic sessions, not publication retries. A second
      session under one stamp_date is the independent-sessions failure the
      prereg forbids.
  - option: Change global Prophet publication policy so as_of versions on republish
    why_not: >
      Out of scope. #5878 and live board republish stay product law. W3 can
      keep its own keep-first measurement plane without forcing the product
      ledger to grow a publication id.
  - option: Leave the family conflict as a crashing W3ConflictError
    why_not: >
      The 2026-08-17 observation is already complete. Crashing is successful
      keep-first turned into a nightly red loop, and it drops session/status
      persistence that PR-3D exists to land.
evidence:
  - "research/prophet_fusion/W3_RACE_PREREG.md — first durable observation; no rewrite; honest-N is distinct matured H=10 sessions."
  - "PR-3C #5839 wrote the 2026-08-17 paired/family/coverage parts; PR-3D #5890 added sessions/status but persist-after-family-raise lost them."
  - "Run 32084697588 job 95749508810: W3ConflictError on F1_TECHNICAL_CONFLUENCE 3.696969697 vs 3.8484848485; frozen blobs 4486cd6199b465431b0e1f27b1057e87b1aaf628 / 6885cfc4f5c180177ed307953f3b67b2021e0371 / dc5edb4082b536adcbb5d3fbc1b22af8a57f6d2e unchanged; sessions.jsonl absent."
  - "DEC:W3-PROSPECTIVE-SAMPLE-IGNORES-GENERIC-BACKFILL — gaps remain gaps; this decision does not reopen #5878 resurrection."
affects:
  - "WS:PROPHET-CONDITIONAL-FUSION"
  - "engine/us_prophet_w3.py"
  - "data/us_prophet_rank/w3/"
  - "DSC:PROPHET-BOARD-ASOF-IS-ECONOMIC-SESSION-ID"
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-18
---

## What this does not change

C1, floors, families, SELECTION_ERA, board definition, and the grader are
untouched. The general Prophet product may still republish under the same
`as_of`. #5878 reconstruction still cannot upgrade a terminal W3
`session_missing` or `degraded_or_unpaired` receipt. Comparison reads remain
forbidden below honest-N=20. C2–C5 and Prophet V4 are not started.

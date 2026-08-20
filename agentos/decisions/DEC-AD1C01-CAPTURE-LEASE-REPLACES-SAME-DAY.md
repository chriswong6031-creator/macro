---
key: AD1C01-CAPTURE-LEASE-REPLACES-SAME-DAY
question: >
  AD-1C0's partial-replacement rule required the replacement capture's ET calendar
  date to equal the session date — but the production nightly's collect job
  measurably crosses midnight ET on ordinary nights (observed accrual instants
  18:20 ET to 00:42 ET; one clean cron sample ran 21:07 ET to 00:08 ET), so a
  lawful same-night post-midnight repair of a partial capture was refused. What
  clock law governs when a stored partial polygon_gex capture may be replaced?
answer: >
  A bounded lawful capture lease plus a measured same-book proof (Sol AD-1C0.1
  Option B). Replacement of a stored partial for session S requires ALL of:
  (1) LEASE — nyse_calendar.expected_last_session(capture_instant) == S AND the
  capture instant in ET falls strictly before 03:00 on the calendar day after S
  (LEASE_END_ET_HOUR = 3), bounding the window to the overnight hours contiguous
  with the session evening, before plausible overnight OI propagation and pre-market
  quoting, and structurally excluding Saturday/Sunday/Monday-preopen recapture of a
  Friday session; (2) SAME-BOOK PROOF — per-contract open-interest agreement on the
  stored/candidate contract intersection (vendor-ticker-preferred join, symmetric
  float32 grid on both sides, deterministic ordering; overlap floor
  min(20, ceil(0.25 x stored contracts))) — disagreement is skipped_vintage_mismatch,
  insufficient overlap or an unreadable store is skipped_unverifiable_vintage,
  outside the window is skipped_outside_lease; (3) the unchanged quality prongs
  (strictly more successes AND healthy-or-+0.10). First-write, healthy-immutability,
  write-ahead receipts, atomic writes, --force (recorded), and single-vintage
  semantics are unchanged. Option A (moving the accrual earlier) was rejected: the
  accrual depends on the same-night membership rebuild immediately preceding it,
  the timing drift is queue-driven rather than schedule-driven, and an earlier slot
  would not fix the retry-path boundary.
rationale: >
  The same-ET-day predicate encoded a calendar coincidence, not the lawful boundary.
  The lawful boundary is the session-relative overnight window in which the vendor
  snapshot still carries the settled book — and rather than assuming that, the
  same-book proof measures it per replacement via OI agreement on shared contracts.
  Sol's warning that expected_last_session(now) == asof alone cannot exclude
  weekend/preopen stale tape was confirmed by census (it holds all weekend), hence
  the hard 03:00-next-day endpoint. The adversarial boundary pass held every
  DST/holiday/early-close/edge attack against this construction.
alternatives:
  - option: Option A — move the accrual to a dedicated close-proximate execution point
    why_not: dependency-unsafe (same-night membership rebuild precedes it in-sequence), queue-driven drift persists regardless of schedule, and the retry-path boundary defect remains
  - option: expected_last_session(now) == asof alone as the lease
    why_not: holds all weekend for a Friday session and through Monday 16:59 ET — exactly the stale-recapture window it must exclude (Sol §3 anticipated this; census confirmed)
  - option: Wall-clock lease without the same-book proof
    why_not: the lease bounds plausibility but proves nothing about the book; the OI-intersection check converts the vintage claim into per-replacement evidence
affects:
  - "WS:ADVANCED-DATA-OPTIONS"
  - scripts/build_polygon_gex.py
  - "DEC:AD1C0-FIRST-WRITER-QUALITY-RULE (rule 3's same-ET-day clause superseded by this lease)"
evidence:
  - "Scripted source-clock census (session 25dc7757, 2026-08-20): daily.yml crons 22:30/23:30Z + et_gate; collect job 21:07->00:08 ET on run 32077948964; accrual after the membership rebuild at scripts/collect.py:823->842; run_status checked_at samples 18:20 ET to 00:42 ET"
  - "PR #6080 (claude/ad1c01-capture-lease, head e9346ea1291b): implementation + Sol §4 time-boundary matrix, 123 focused tests"
  - "Opus boundary review: clock boundary held every attack (DST 2026-2028 both directions, 02:59/03:00 edge, holiday-adjacent, early-close); same-book proof defects F1-F7 repaired and flip-verified"
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-20
---

Scope note: the lease governs REPLACEMENT of a stored partial only. First writes
(no stored file) remain lawful at any instant that resolves to the session — the
capture instant is recorded in the health receipt and the vintage stays visible.
This PR is held for Sol per the AD-1C0.1 handoff; the decision takes effect on
merge.

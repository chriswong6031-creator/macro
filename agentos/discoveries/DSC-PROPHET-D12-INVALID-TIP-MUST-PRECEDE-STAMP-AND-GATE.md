---
key: PROPHET-D12-INVALID-TIP-MUST-PRECEDE-STAMP-AND-GATE
claim: >
  US Prophet Live D12 cannot be repaired by capping only the published pack
  `as_of`. `engine.prophet_live.armed_pack.as_of_date()` reports the raw maximum
  store tip and `session_lag()` intentionally returns zero when a name's last bar
  is at or ahead of that tip. Therefore one Saturday, future-session, same-session-
  before-close, or malformed final index can affect BOTH the global pack stamp and
  the name's gate input. The US pack owner must quarantine that entire name before
  selecting the pack tip and before submitting fresh names to the gate. The bad
  series must not be trimmed and reused, because that would make Prophet evaluate a
  different price series from the board owner while looking healthy.
falsifier: >
  On the US builder, feed a clean Friday series plus either (a) a Saturday series,
  (b) a not-yet-completed future-session series, or (c) a NaT final index. The
  discovery is falsified if the bad name remains in the admitted series set, changes
  the selected pack tip, reaches the fresh/gate loop, crashes the builder instead of
  being quarantined, or if the shared `armed_pack.as_of_date()` semantics must change
  to make the US repair work. A genuinely stale but valid-session series must remain
  honestly stale rather than being promoted to the completion bound.
so_what: >
  The incident mechanism was a one-name-to-whole-pack contagion. A cosmetic stamp
  repair would make `pack_ok` look correct while still letting contaminated evidence
  into the signal gate. The accepted boundary is therefore US-owner admission:
  `last_completed_session(now)` supplies the completion bound; only series whose last
  index is a real NYSE session at or before that bound are admitted. Rejected names
  publish an explicit `invalid_series_tip` non-verdict and never run the gate. Shared
  `engine/prophet_live/armed_pack.py` stays calendar-neutral so China and other callers
  keep their own calendar semantics. This also preserves the stale-store invariant:
  among valid series the raw maximum remains the real store tip, not a fabricated
  freshness date.
scope:
  - macro
  - scripts/build_prophet_live_pack.py
  - tests/test_prophet_live_pack_d12.py
  - WS:PROPHET-US-AVAILABILITY
kind: constraint
confidence: verified
verified_at: 2026-08-27
verified_by: >
  Operation prophet-us-d12-pack-tip-hardening-20260827-sol-001. Binding RED run
  33068839608 failed 5 D12 owner-bound assertions while preserving the existing
  completion clock and shared raw as_of semantics. Committed-head GREEN run
  33069264975 passed 8/8. Mutation run 33069337428 removed only NYSE-session
  validation; the Saturday-before-bound case failed by selecting 2026-08-01 instead
  of 2026-07-31, so the mutation was killed. Cross-market run 33069685528 passed
  81/81 existing US+CN armed-pack tests. A ninth hostile NaT test then reproduced a
  real TypeError in run 33069928015; one fail-closed predicate repaired it and apply
  run 33069998807 passed 9/9 before committing e2d612e4bd3b2dbddff4b25103c09aac3dc7434d.
---

# D12 is an admission-ordering defect, not only a metadata-stamp defect

The dangerous shortcut is `min(raw_tip, completed_session)` or an equivalent cap on
`meta.as_of`. That changes what the pack says without changing what the gate consumed.
The safe repair removes impossible evidence from the US pack's admissible input first,
then derives the pack's raw store tip from what remains. Do not move this NYSE-specific
law into shared `armed_pack`; that module is also used by China.

---
key: INTL-BOARD-CARRIES-NO-ASOF
claim: >
  `site/factordata/intl_setups.json` has carried `as_of: null` on every commit in main's
  history. `compute_intl_alpha` returns no `as_of` key on any path, and the artifact's
  stamp is assigned straight from `(alpha or {}).get("as_of")`
  (scripts/build_intl_library.py:489), so the International board publishes with no
  freshness stamp at all. The builder's own module comment already records this
  (build_intl_library.py:282-290, adversarial review D1, PR #5674); the ANCHOR that
  falls back to the library tip (`_intl_session_asof`) is used for scoring context and
  never reaches the published artifact.
falsifier: >
  `git show origin/main:site/factordata/intl_setups.json | python3 -c "import json,sys;
  print(json.load(sys.stdin).get('as_of'))"` returning a date rather than None, or
  `compute_intl_alpha` gaining an `as_of` on its return path.
so_what: >
  International cannot be graded for staleness by ANY content-stamp instrument until the
  builder stamps it — a freshness check on that board can only report INDETERMINATE, and
  one that reports "fresh" is reporting on nothing. Treat it as a NAMED blind spot rather
  than a healthy market. Compounding it, the board unions eight-plus venues (Tokyo,
  London, Seoul, Sydney, Mumbai, Milan, Taipei, Madrid — read off its own tickers), whose
  holiday schedules are disjoint, so even once stamped there is no single exchange
  calendar to grade it against; a Mon-Fri approximation with a documented tolerance is
  the honest ceiling.
kind: landmine
verified_at: 2026-08-17
verified_by: >
  origin/main @789e6e10 and every commit walked back to 2026-07-25: top-level `as_of` is
  None; scripts/build_intl_library.py:489 (`rank_setups(..., as_of=(alpha or {}).get("as_of"))`),
  :282-290 (the in-code note that compute_intl_alpha carries no as_of on any return path),
  :525 (the write); ticker list read from the artifact's own `buy` array.
scope: [macro]
confidence: verified
---

## Detail

`scripts/check_nightly_liveness.py` check D (PR #5852) registers International with the
other four markets and reports it INDETERMINATE every run, naming the reason, rather than
dropping it from the registry or inventing a verdict. `tests/test_nightly_liveness.py::
test_intl_board_is_a_known_blind_spot_today` pins the current state deliberately, so the
day the builder starts stamping, that test is what says International has become
gradeable and its registry entry should be re-derived against a real calendar instead of
the weekday approximation.

The fix belongs to the intl library, not to the guard: give `compute_intl_alpha` an
`as_of` on its return paths, or stamp the artifact from `_intl_session_asof` (the anchor
that already resolves alpha as_of -> library tip -> wall clock) at the write site.

Related: [[BOARD-RECOMMIT-IS-NOT-A-BOARD-ADVANCE]].

---
key: ARB-PLAUSIBILITY-BAND-ADMITTED-THE-DEFECT-IT-GUARDED
claim: >
  The 42,790.2% LGMK annualized spread that led `risk_arb_top` in
  data/special_situations/context/latest.json was NOT produced by an unguarded path: a
  plausibility band (`_PLAUS_LO=0.6`, `_PLAUS_HI=1.8`) and a `_DAYS_CAP=1095` clamp were
  already in engine/special_arb.py specifically to keep "a garbage spread out of the TOP of
  the risk_arb book", and both PASSED the row. LGMK's offer/price ratio was 1.6457, inside
  the band, and its 30-day close was inside the cap. The magnitude came from a
  `YYYY-MM -> month end` substitution in `_to_date` that turned an unobserved close month
  into a precise 30-day denominator, which the band cannot see because the ratio is
  perfectly ordinary. Test coverage of that entire publication path was ONE assertion,
  `assert "risk_arb_top" in result` in tests/test_special_sits_intel.py.
falsifier: >
  `git show <pre-F09 sha>:engine/special_arb.py` and check that _PLAUS_LO/_PLAUS_HI/_DAYS_CAP
  exist and that 25.00/15.19 = 1.6457 falls inside [0.6, 1.8]; or run the pre-change
  `arb_metrics(25.0, 15.19, expected_close="2026-11")` and observe it returns
  `annualized_pct` rather than None. If either shows the band rejecting the row, this is wrong.
so_what: >
  Do not answer an absurd published number with a wider or tighter magnitude band - that is
  the control which already failed, and adding a second one hides the cause instead of
  removing it. An implausible output whose INPUTS are all plausible is a provenance defect:
  find the field that was invented (here, a day that no filing ever stated) rather than the
  number that looks wrong. Corollary for reviewers: a magnitude guard on a derived value
  proves nothing about the derivation, and a path guarded by one can still be untested.
kind: landmine
verified_at: 2026-09-03
verified_by: "engine/special_arb.py:130 and :185-187 pre-F09; PR #6793 RED receipt"
scope:
  - macro
  - engine/special_arb.py
  - engine/special_situations.py
  - engine/special_sits_intel.py
confidence: verified
---

The band was not negligence — it was written deliberately, with a comment naming the exact
risk it was meant to stop ("keep a garbage spread out of the TOP of the risk_arb book, which
sorts by annualized_pct desc"). It failed anyway, because it inspected the derived ratio and
the derived ratio was fine. The invented input was the close DAY, and no output guard can see
a day that was never observed.

The second half of the landmine is coverage: this path shipped a number into every Neural Web
consumer (`mastermind_context`, `world_state`, `ask_brain`, `brief_context`, `cortex`) behind a
single `assert "risk_arb_top" in result`. When auditing a display-tier lane, check whether its
publication path is asserted at all before trusting that a guard in it works — a guarded path
and a tested path are different claims.

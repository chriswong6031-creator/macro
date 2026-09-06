---
key: A-GREEN-SUITE-CANNOT-TELL-YOU-WHICH-GUARDS-IT-PINS
claim: >
  A guard can be present, correct, reviewed and shipped while NO test pins it, because sibling
  tests that perturb more state than the guard needs let a coarser downstream check absorb the
  failure — so the fine guard is never the reason anything goes red, and deleting it changes
  nothing.
falsifier: >
  Delete the `expected_session` equality comparison from `validate_price_receipt()` in
  `engine/special_arb.py` (the two lines that append `PRICE_RECEIPT_INVALID` when the receipt's
  declared expected session differs from the one re-derived through `lib/nyse_calendar`), then
  run the four owned suites. If any test fails, this is wrong.
so_what: >
  A green suite is evidence about the SUITE, not about any individual guard, and no amount of
  review reads the difference — the guard is right there in the diff, correct, and unpinned.
  Mutate each guard separately and require a named killing test for each. When you write that
  test, hold every other input HONEST and perturb exactly the one field: the reason the gap
  existed here is that all four sibling freshness tests moved `session` or `sessions_behind` as
  well, so recomputed staleness arithmetic reddened them first and the finer check never
  decided anything. This also tells you which guards are load-bearing and which are decoration:
  a guard whose deletion no test notices is, until pinned, indistinguishable from a comment.
kind: landmine
verified_at: 2026-09-03
verified_by: >
  10-mutant adversarial matrix over macro#6793 staged head; mutant M4 (expected_session
  comparison deleted) SURVIVED 197 passing tests while the other 9 mutants were each killed by
  exactly one test. Closed by
  tests/test_special_arb.py::test_a_false_expected_session_field_is_invalid_even_when_the_price_is_current,
  after which 10/10 mutants are killed at 198 passing.
scope:
  - macro
  - engine/special_arb.py
  - tests/test_special_arb.py
confidence: verified
---

The F09-1 repair added a real gate: `validate_price_receipt()` re-derives a price receipt's
clocks through the approved calendar owner instead of believing the caller
([[A-PURE-REDUCER-THAT-TRUSTS-ITS-RECEIPT-HAS-NO-GATE]]). Four tests were written for it, the
suite went to 197 green, and an exact-head adversarial review reproduced the original exploits
against it. All of that was true, and one of its checks was still pinned by nothing.

The check is the one that compares the receipt's own `expected_session` field against the session
re-derived from `now_utc`. Deleting it left **197/197 passing**. It was found by mutation, not by
reading — and it is worth noting the review that found four other critical defects in this same
function did not find it either, because the code is *correct*; there is nothing to see.

The masking mechanism is the transferable part:

| sibling test | what it perturbs | what actually reddens it |
|---|---|---|
| stale session + caller-authored `sessions_behind=0` | `session` **and** `expected_session` **and** `sessions_behind` | recomputed `behind > 0` → `PRICE_STALE` |
| `sessions_behind` is recomputed | `session` and `sessions_behind` | recomputed `behind` ≠ claimed |
| made-up basis | `basis` | closed-vocabulary check |
| stale panel self-certification | `session` | recomputed `behind > 0` |

Every one moves the clock as well as the claim, so the coarse staleness arithmetic fires first
and the `expected_session` field comparison is never the deciding check. The killing test has to
do the opposite of what feels thorough: leave `session` and `sessions_behind` genuinely correct
for `now_utc` — the price really is current, nothing downstream disagrees — and corrupt only the
receipt's own statement about which session the market last completed.

That case matters beyond the test, because the receipt is **published**. A VERIFIED row would
have carried a calendar fact that no calendar owner ever produced and that no consumer could
contradict — the same false-precision shape this wave exists to remove, one field further in.

---
key: A-PURE-REDUCER-THAT-TRUSTS-ITS-RECEIPT-HAS-NO-GATE
claim: >
  Moving a decision into a pure, well-tested owner does not make it verified if the owner accepts
  the CALLER's conclusions as facts: a gate that checks a receipt's SHAPE is a schema check
  wearing a gate's name.
falsifier: >
  Hand `engine.special_arb.reduce_cash_deal()` a price receipt whose `session` is years before
  its own `expected_session` with `sessions_behind=0`, or whose `basis` is an invented string.
  If the row is not VERIFIED, this is wrong.
so_what: >
  Split every receipt field into three kinds and treat them differently. (1) RECOMPUTABLE from
  first principles — expected session and sessions-behind, re-derived through the approved
  calendar owner from an explicit `now_utc`; note `lib/nyse_calendar` is pure date arithmetic,
  so a no-IO module can still recompute them, which removes the usual excuse for trusting the
  caller. (2) CHECKABLE against a closed vocabulary — basis, column, writer owner + reviewed
  blob, calendar id, digest shape, byte length. (3) GENUINELY UNRECOMPUTABLE by a pure owner —
  whether a series' sessions were unique and monotonic — which must travel as explicit named
  booleans the impure producer sets from the artifact it actually opened. And never give a
  receipt field a DEFAULT: an omitted basis silently becomes an asserted one.
kind: landmine
verified_at: 2026-09-03
verified_by: >
  tests/test_special_arb.py::test_a_stale_session_with_a_caller_authored_zero_behind_is_not_verified,
  ::test_a_made_up_price_basis_is_not_verified, ::test_sessions_behind_is_recomputed_not_accepted,
  ::test_price_input_has_no_raw_close_default — all RED at macro#6793 head
  a88c12f2b0a501a42328d87797e4fb5b33d0b984
scope:
  - macro
  - engine/special_arb.py
confidence: verified
---

The F09-1 reducer was the wave's headline improvement: one pure owner, no IO, every consumer
reading the same contract, 143 tests. It still published wrong numbers, because it required a
freshness receipt and then believed it.

Measured at head `a88c12f2`, each of these reached `VERIFIED`:

| receipt | why it should have failed |
|---|---|
| `session=2020-01-02`, `expected_session=2026-06-01`, `sessions_behind=0` | the two clocks contradict each other |
| `basis="totally_made_up_basis"` | no closed vocabulary |
| a genuinely five-sessions-stale close, caller declares `sessions_behind=0` | the caller's arithmetic was never checked |
| `basis` omitted entirely | `price_input()`'s own default was `"close_raw"` |

The last one is the sharpest: the false-raw fiction that the owner ruling prohibited lived in the
**pure module's signature**, not only in the producer that the review was aimed at. A default
value on a provenance field is an assertion made on the caller's behalf.

`_has_calendar_receipt()` — `bool(calendar_owner and expected_session and sessions_behind is not
None and artifact_sha256)` — is what this looks like in review: four real field names, a
plausible name, and no arithmetic. The repaired `validate_price_receipt()` returns a reason list
and re-derives the clocks; the reducer then reports `sessions_behind` from its own recomputation
rather than from the receipt, so the published number cannot disagree with the calendar even if
the producer is wrong. Related: [[A-RESEALED-ROW-IS-SELF-CONSISTENT-NOT-EVIDENCED]].

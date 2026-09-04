---
key: A-RESEALED-ROW-IS-SELF-CONSISTENT-NOT-EVIDENCED
claim: >
  A content-addressed identity binds only what the digest COVERS, and re-deriving that identity
  from the row's own fields proves nothing about the world — so a forger who can recompute the
  id passes every validation the row is subject to.
falsifier: >
  Take any row from data/special_situations/observations/observations.jsonl, change
  `normalized`, call `engine.special_arb.reseal()` on it, then call
  `engine.special_arb.validate_observation()`. If that returns False, this is wrong. Or stamp a
  supersession with `link_supersession()` and compare `observation_id` before and after — if it
  changes, the relation was already inside the digest.
so_what: >
  Every field that can change what a row MEANS must be inside the identity — value, span,
  projection, source, status, unit, currency basis AND the correction relation — because a
  relation that can change without changing the identity is an authorization boundary anyone can
  cross. Even a complete digest then needs an EXTERNAL closure: the reader must re-run the
  deterministic extractor over the re-verified source bytes and admit the row only if the
  extractor actually authors it (`authored_terms()` / `rebind_observation()`). Digest checks
  catch tampering by someone who cannot recompute; only re-derivation from the source catches a
  forger who can.
kind: landmine
verified_at: 2026-09-03
verified_by: >
  tests/test_special_situations.py::test_a_row_that_does_not_descend_from_the_retained_bytes_is_unbound[forged_value_resealed]
  and tests/test_special_arb.py::test_a_forged_supersession_field_cannot_pull_an_unrelated_price_into_a_deal,
  both RED at macro#6793 head a88c12f2b0a501a42328d87797e4fb5b33d0b984
scope:
  - macro
  - engine/special_arb.py
  - engine/special_situations.py
  - collectors/special_situations.py
confidence: verified
---

Three instances of one shape in a single module, all of them passing 146 green tests.

**Resealed value.** `observation_id` was already a closed digest over accession + raw/projection
digests + locator + field + value + extraction revision — genuinely more than most provenance
schemes carry. But `validate_observation()` recomputes that id *from the row*, so the check is
"is this row internally consistent", not "did these bytes say this". Measured at head
`a88c12f2`: a ledger row resealed with `normalized=999.0`, its locator still pointing at the
true `"$25.00 … per share"` span, validated True, compiled, and reached `VERIFIED`.

**Relation outside the digest.** `prior_observation_id`, `supersedes_observation_id` and
`correction_reason` sat outside it, so `link_supersession()` recomputed the id and got the *same
string back* — a no-op. One hand-forged link therefore pulled an unrelated accession's price
into a VERIFIED deal: offer 250.00, spread +1150%. The compiler compounded it by admitting an
entire multi-accession bucket the moment *any* supersession matched *any* id in it, so one
lawful amendment link legalized an unrelated third accession.

**Status outside the digest.** `status` was outside it too. Since the repaired extractor records
out-of-scope prices as `deferred` rows, a flip from `deferred` to `observed` would have promoted
a rejected background proposal to the live offer — a hole created by the fix for a different
defect, which is the reason the semantic tuple is enumerated explicitly rather than derived from
"the fields the digest happens to cover".

The generalisable question to ask of any provenance chain: *who could produce this receipt?* If
the answer includes "anyone holding the row", the receipt authenticates the row against itself.
Related: [[A-DIGEST-OF-A-DERIVED-PROJECTION-IS-NOT-BYTE-BINDING]],
[[A-PURE-REDUCER-THAT-TRUSTS-ITS-RECEIPT-HAS-NO-GATE]].

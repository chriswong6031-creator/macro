---
key: A-DIGEST-OF-A-DERIVED-PROJECTION-IS-NOT-BYTE-BINDING
claim: >
  Hashing the artifact you happen to have retained is not provenance. The F09-1 deal-term
  observations hashed `collectors/special_situations.py`'s doc_cache, which is
  `_strip_markup(raw)[:40000]` - a LOSSY, TRUNCATED projection - then labelled the span
  `full_submission_text` and let conflict detection scan only those retained 40k characters.
  Every layer downstream was honest about its own step, so the row reached the machine context
  as VERIFIED with a sha256, an accession, exact character offsets and an excerpt digest. All
  of it was true about the projection and none of it was true about the filing. The same shape
  appeared twice more in one wave: `_calendar_index` derived "expected session" from the very
  price panel it was grading (so a globally frozen panel reports every listing 0 sessions
  behind), and `_load_observations` verified a `schema` string rather than re-deriving each
  row's digest (so a hand-edited value published unchallenged).
falsifier: >
  `git show <pre-repair sha>:collectors/special_situations.py` and read `_fetch_filing_text`:
  if the cached object is the complete response rather than `_strip_markup(raw)[:max_chars]`,
  this is wrong. Or bind an observation to a body whose tail was cut, place a contradicting
  price past the cut, and check whether the compiler still reports no conflict.
so_what: >
  When auditing a provenance chain, ask what the digest is a digest OF, and whether the thing
  being graded is independent of the grader. A receipt that names a derived artifact certifies
  the derivation, not the source, and "no conflicting value found" inside a truncated body is
  not evidence of absence - it is absence of evidence wearing a receipt. Three concrete rules
  came out of it: retain the complete source object and keep the normalized projection as a
  SEPARATE, versioned receipt (`raw_sha256` + `projection_revision`); grade freshness with an
  owner that cannot be the store being graded (`lib/nyse_calendar.py`); and make the row id a
  closed digest over value+span+projection+source so re-validation is real rather than a label
  check. Truncated or unknown completeness can never yield VERIFIED.
kind: landmine
verified_at: 2026-09-03
verified_by: "Sol review 5099936758 on macro#6793; repaired at head 5db9634a31a3 -> successor"
scope:
  - macro
  - engine/special_arb.py
  - engine/special_situations.py
  - collectors/special_situations.py
confidence: verified
---

The reason this class is worth naming is that **no single layer lied.** The collector honestly
cached what it fetched. The extractor honestly recorded offsets into what it was handed. The
compiler honestly reported the conflicts it could see. The reducer honestly published what the
compiler certified. The falsehood only exists at the seam, in the gap between "the bytes I
hashed" and "the document I claimed" — and seams are exactly what per-layer review does not
look at.

Practical tell for reviewers: follow a single published number backwards and ask, at each hop,
*what would have to be true for this receipt to be worthless?* For a digest, the answer is
"if it names something derived." For a freshness verdict, "if the clock came from the thing
being timed." For an integrity check, "if it validates a label instead of re-deriving the
value." All three were present here at once, and all three passed 146 green tests.

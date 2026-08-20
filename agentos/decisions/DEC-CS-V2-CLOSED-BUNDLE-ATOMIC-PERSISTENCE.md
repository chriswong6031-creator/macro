---
key: CS-V2-CLOSED-BUNDLE-ATOMIC-PERSISTENCE
question: >
  When W1A bundle classification finds that some but not all members of a
  retained filing changed, may the collector append only the changed source
  manifests at the newly allocated accession-wide document_version?
answer: >
  No. Re-observation appends zero rows, and only when every candidate is
  already known and interpretation-equivalent *and* the candidate membership
  equals the latest published closed bundle for that accession. Any added,
  removed/deselected, newly resolvable, or interpretation-revised member is
  a bundle revision and must persist the entire candidate bundle at that
  accession-wide version. Do not copy a removed/deselected member into N+1.
  Every surviving child in the new bundle points at the new candidate
  complete-submission manifest_id. The classifier may name which members
  changed or were removed for diagnostics; durable persistence is
  bundle-atomic. Historical v1 rows are not rewritten. A later
  coordinate-bound identity for the same accession+source_id+bytes is
  comparison-time identity refinement, not a new economic capital-change
  event.
rationale: >
  _next_bundle_document_version already allocates one version across the
  complete submission and all retained children. _current_manifest_bundle
  requires the latest complete and all current children to share that
  version and every child to reference the latest complete manifest_id.
  W1A classify_bundle_against_published returned only changed members in
  append, so a primary-only interpretation change could persist an
  incomplete N+1 bundle and drop unchanged children from the compiled
  event. Candidate-only classification also missed membership
  subtraction: a published current exhibit absent from an otherwise
  unchanged candidate was treated as re-observation. Bundle-atomic
  persist plus published-current membership compare preserves the
  closed-bundle contract without reminting evidence_id for unchanged
  occurrence+bytes.
alternatives:
  - option: Keep appending only changed members and teach the compiler to
      splice older-version children into the latest complete
    why_not: Breaks the closed-bundle invariant already enforced by
      _current_manifest_bundle; mixed-version current sets are exactly
      the leak the compiler refuses.
  - option: Remint only the changed child and rewrite its parent pointer
      onto the previous complete manifest_id
    why_not: Leaves N+1 children pointing at an N complete, which the
      compiler rejects.
  - option: Treat a smaller candidate as re-observation when every
      remaining member is interpretation-equivalent
    why_not: Drops a previously current member from the live bundle
      without minting N+1, so the compiler keeps compiling the stale
      exhibit. Deselection is a selection-policy revision.
  - option: Copy the removed member into N+1 so membership stays
      unchanged
    why_not: The candidate no longer selected that member; persisting it
      would invent a current occurrence the collector did not retain.
evidence:
  - "collectors/sec_capital_structure.py:_next_bundle_document_version"
  - "engine/capital_structure/source_identity.py:current_manifest_bundle"
  - "engine/capital_structure/source_identity.py:classify_bundle_against_published persist=all candidates on revision; removed membership is revision"
  - "scripts/compile_capital_structure_events.py:_current_manifest_bundle wraps current_manifest_bundle"
  - "tests/test_capital_structure_closed_bundle.py"
  - "DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES"
  - "DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - "collectors/sec_capital_structure.py"
  - "engine/capital_structure/source_identity.py"
  - "scripts/compile_capital_structure_events.py"
confidence: high
reversibility: costly
decided_by: cursor-grok-4.6
decided_at: 2026-08-20
review_by: 2026-08-25
---

W1B correction on merged #6012. Classifier diagnostics may still list
changed or removed members. Persistence of a revision is the whole
candidate bundle, never a stale published member that the candidate
deselected. Identity refinement of `legacy:{source_id}` onto later
coordinate-bound ids is comparison-only and does not rewrite historical
rows.

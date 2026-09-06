---
key: STALE-SEMANTIC-PROOF-HAS-NO-CURRENT-VERDICT-AUTHORITY
question: >
  May a semantic CI receipt bound to a superseded tested base decide the current
  merge-on-green disposition before the existing ProofFreshness controller has
  established that the receipt is current?
answer: >
  No. After the physical proof anchors have concluded and a semantic-v1 artifact
  has been loaded and identity-bound, ProofFreshness decides whether that receipt
  is current before its semantic classifications receive either merge authority
  or blocking authority. A stale receipt routes through the one canonical
  reconciliation/reproof mechanism. Only a current receipt may be classified;
  current unknown or regression evidence still blocks normally.
rationale: >
  PR #6391 exposed an ordering defect rather than a semantic-classification
  defect. Its historical receipt truthfully described an old tested base, but
  merge-on-green converted its unknown/not_run_prior_failure unit into a current
  block before calling freshness.stale_for(), so the already-governed reproof
  path was unreachable after main healed. Moving freshness ahead of semantic
  classification for an actual semantic-v1 receipt restores temporal authority
  without changing any verdict vocabulary. Physical pending/incomplete anchors
  still wait, malformed advertised evidence still fails closed, pre-epoch
  legacy_absent evidence retains legacy law, the existing refresh lease prevents
  duplicate generations, and a fresh failure remains final for that proof.
alternatives:
  - option: Treat unknown or inherited_base as an implicit request for reproof
    why_not: >
      Classification is not freshness. This would retry fresh failures merely
      because their verdict is inconvenient and could create a proof loop.
  - option: Accept a stale green receipt but reprove only stale red receipts
    why_not: >
      Freshness is symmetric authority. A stale success no longer proves the
      current candidate any more than a stale failure disproves it.
  - option: Add a force-proof label or second dispatcher
    why_not: >
      The canonical ProofFreshness, refresh lease, reprove(), and update-branch
      lifecycle already own this transition; a parallel trigger would duplicate
      authority and idempotency state.
evidence:
  - "pickup 221f72b413ed8250548f6393ecb665ea894ee293 scripts/merge_on_green.py: semantic blocked returned before the later ProofFreshness.stale_for/reprove path"
  - "tests/test_merge_on_green_semantic.py::test_stale_6391_semantic_receipt_reproves_before_unknown_can_block reproduced the old mark_blocked return before implementation"
  - "tests/test_merge_on_green_semantic.py fresh-failure, pending-generation, stale-green, legacy-absent, and malformed-artifact discriminators"
affects:
  - WS:CI-MERGE-CONTROL-PLANE
  - scripts/merge_on_green.py
  - tests/test_merge_on_green_semantic.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-25
---

This decision changes decision order, not the meaning of semantic evidence.
Semantic CI remains the sole authority for the exact tested merge tree and base;
ProofFreshness remains the sole controller for whether that proof still describes
the current candidate surface.

## Amendment 2026-09-05 — unavailable is not stale

Question: when the pull request's own changed-file inventory cannot be read, may
that failure be treated as affirmative staleness and trigger update-branch?

No. Staleness is an observation that main moved inside a surface. A failed
transport is the absence of observation, and an update-branch cannot repair a
failed read; issuing one lets a GET failure author a non-GET effect. Such a read
is `PROOF_SURFACE_UNAVAILABLE` and defers (freshness-deferred, zero writes),
while genuinely observed conditions — a truncated/broad footprint, and a complete
inventory that matches no gate — keep their existing conservative reproof.

This extends the ordering law without changing any verdict vocabulary, and
introduces no dispatcher, proof store, queue, retry loop or negative cache.
Diagnostics are bounded to PR number, failure class, page and numeric HTTP
status; response bodies and headers are never emitted, because a body is
attacker-influenced and can echo a token.

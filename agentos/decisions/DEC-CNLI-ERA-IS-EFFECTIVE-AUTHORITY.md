---
key: CNLI-ERA-IS-EFFECTIVE-AUTHORITY
question: >
  Is the champion era for CN-Limit comparisons keyed by board_definition
  alone, or by the effective serving authority?
answer: >
  By effective authority: board definition PLUS effective order basis, order
  mode, score/admission hashes, and candidate schema. Eras with different
  effective authority are never pooled, even under the same board_definition
  string.
rationale: >
  A v4 bake served through v3 fallback is not the same treatment as a
  complete Intelligence-ordered v4 bake: the candidate set is identical but
  the effective ordering authority differs, so pooling them attributes one
  regime's outcomes to the other's ranking. Champion/challenger deltas,
  era reconstruction, and G4 ablation are only honest when the era key
  captures what actually ordered the board that night, not what the version
  label claims.
alternatives:
  - option: Key eras by board_definition alone
    why_not: >
      Silently pools fallback-served and fully-served nights; the fallback
      regime's outcomes contaminate the champion baseline the challenger is
      measured against.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §8.6, §12"
  - "R5 integration architecture, pinned in freeze Appendix C (6b7f322d...)"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "research/cn_limit/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze. Prophet definition and effective-order eras
are never pooled (freeze §1.2 binding invariant).

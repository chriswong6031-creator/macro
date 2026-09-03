---
key: CODE-INTELLIGENCE-ENGINES-ARE-DISPOSABLE-BACKENDS
claim: >
  Serena, language servers and Zoekt can improve code retrieval or semantics, but none may be the
  model-facing authority, canonical code truth, workspace selector or lifecycle owner; they are
  replaceable engines behind fixed Mastermind read contracts whose results remain freshness- and
  verification-qualified.
falsifier: >
  Re-run the C0 and Z0 benchmark/adversarial matrices frozen in Mastermind PR #276. This discovery
  is disproved only if a direct upstream surface demonstrates a strictly smaller authority surface,
  exact concurrent-worktree isolation, immutable schema and binary provenance, truthful stale/null/
  coverage behavior, multi-language parity and canonical verification without a Mastermind facade.
  Merely returning useful results, starting successfully or passing a happy-path MCP census does not
  falsify it.
so_what: >
  Future sessions compare engines behind the stable facade and may truthfully select Serena, direct
  LSP, Zoekt or NO_SAFE_BACKEND. They must not expose upstream project switching, shell/edit/memory,
  arbitrary roots, index administration or mutable package launchers to workers, and must not build
  a replacement lifecycle, workspace registry, source-of-truth store or central semantic router.
kind: architecture
verified_at: 2026-08-30
verified_by: >
  Mastermind PR #276 final candidate e6553b3b640712de4446b0337c291243fde07c61,
  accepted squash merge 620263090fb9f272f763e420ba103b0ff8dc5f31; F0 upstream source/tool
  census, hostile two-worktree design, benchmark charter and supply-chain amendment.
scope:
  - WS:CODE-INTELLIGENCE-FABRIC
  - macro-context-index
  - mastermind
  - terminal
  - macro
confidence: verified
---

## Consequence

The promotion question is never “does Serena or Zoekt work?” It is whether a pinned backend behind
the closed contract makes real Mastermind implementation and review journeys faster and more
correct while preserving isolation, truth and resource budgets. A component can be technically
successful and still be rejected for authority, provenance, multi-language, stale-result or
operational-cost reasons.

# Capital Structure Parity — Continuation Handoff

Date: 2026-08-02

This is the canonical resume note. Continue with clean-room, public-source implementation only; do not bypass competitor access controls or reuse protected code/content.

## Shipped

- PR #4212 — evidence-bound issuer projection.
- PR #4224 — observed filing desk, private API, and front-facing Capital Structure surface.
- PR #4240 — normalized document-term truth plane; merged as `53be3416bef9e9bfb8318453b0a89a1dda6b5274`.

PR #4240's feature tests passed. Its post-merge repository CI run `30731687782` failed only after a Government Revenue render introduced an unrelated user-facing `proven` claim at `site/government_revenue.html:407`; both `validated-claims` and the larger render-guard pack reported the same issue. Reproduce after the Government Revenue render before changing the term engine.

## Open dependency

- PR #4243 — `codex/capital-structure-wave2c-intake`
- Commit: `97a9722745915e5dc344347f9ed16fabba7e01d0`
- Purpose: SEC file-number provenance, EFFECT linkage support, issuer-scoped reconciliation, deterministic intake queues, and legacy-ledger migration.
- Local result: 207 passed, 1 skipped; DAG and Synapse checks clean except two inherited unrelated DAG drifts.
- Resume action: wait for CI; if green, squash-merge and verify `origin/main`.

## Preserved packets

### Registration lifecycle

- Branch: `codex/capital-structure-registration-lifecycle-20260801`
- Worktree: `/Users/chriswong/.codex/worktrees/capital-structure-registration-lifecycle-20260801/Macro Dashboard`
- Scope: filing-to-amendment-to-EFFECT/pricing lifecycle, causal clocks, correction ancestry, and exact-authority firewall.
- Local result: 27 focused tests passed.
- Dependency: rebase only after PR #4243 lands; the lifecycle intentionally rejects legacy or ambiguous file-number provenance.

### Share-count truth plane

- Branch: `codex/capital-structure-share-count-truth`
- Worktree: `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/capital-structure-share-count-truth`
- Scope: hash-bound SEC Company Facts observations for common shares outstanding and public float, with PIT clocks, source receipts, corrections, ambiguity, and defer states.
- Local result: 45 focused/relevant tests plus 169 existing capital/SEC tests passed (1 skipped).
- Boundary: this is a normalizer, not coverage. Build a Company Facts collector that retains exact response bytes and a receipt before claiming issuer coverage.

## Exact resume order

1. Reproduce or clear the unrelated Government Revenue `validated-claims` failure from run `30731687782`.
2. Finish PR #4243 and verify the merged SEC-intake lineage.
3. Rebase, revalidate, and ship the registration-lifecycle packet.
4. Rebase, revalidate, and ship the share-count packet.
5. Add hash-retaining Company Facts acquisition and coverage receipts.
6. Then build instrument state, remaining capacity, cash runway, issuer dossier/alerts, and only afterward calibrated 7/30/90-day financing probabilities and Prophet gating.

Do not let raw filings or normalized terms become trading authority. Neural Web, Mastermind AI, and Prophet may consume only evidence-bound issuer-state projections with explicit freshness, ambiguity, and lineage.

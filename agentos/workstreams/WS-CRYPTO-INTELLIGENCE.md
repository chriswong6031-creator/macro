---
key: CRYPTO-INTELLIGENCE
title: Governed crypto intelligence and decision presentation
objective: >
  Keep BTC Vector and adjacent crypto surfaces provenance-honest, with one
  declared authority for every decision-bearing output and advisory evidence
  unable to silently override it. Each wave is complete only at its separately
  authorized acceptance boundary.
status: parked
program: crypto-intelligence
repos: [macro]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: specified
waves:
  - id: P0A
    title: BTC Decision Authority Closure on Vector
    status: done
    pr: 6294
    note: >
      Repository-built on Draft HOLD-FOR-SOL PR #6294. Sol returned two bounded
      integrity blockers plus current-main reconciliation; both defects are
      repaired on the same branch, the seven P0A commits were preserved by a
      normal merge onto origin/main pickup cd42b890d1df and subsequent normal
      merges through final render pickup 0e8cd8f28edd at f792c107473d, followed
      by a cleanly composing CI/White-House-only refresh to 21fab3521143 at the
      final PR head. Refreshed local product proof is complete. P0A is not
      Sol-accepted, merged, deployed or live. The done status describes the
      bounded build wave only.
  - id: P0B
    title: Crypto H5 authority closure
    status: todo
    depends_on: [P0A]
    next_action: >
      Remain unstarted until Sol separately commissions P0B after reviewing P0A.
next_action: >
  Sol reviews the repaired/reconciled Draft PR #6294 at its final exact head.
  Keep it Draft and HOLD-FOR-SOL with merge-on-green absent and native auto-merge
  null; do not start P0B, alerts or broader redesign.
owns_paths:
  - "engine/btc_decision.py"
  - "contracts/btc_decision.schema.json"
  - "scripts/build_vector.py"
  - "templates/vector.html.j2"
  - "site/vector.html"
  - "tests/test_btc_decision.py"
decisions:
  - "DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED"
landmines:
  - >
    build_vector writes data ledgers before HTML; use a disposable full
    worktree for rendered evidence and carry only normalized page assets.
  - >
    Economically meaningful raw/final allocation drift without an active named
    override is an integrity failure; only representation jitter is tolerated.
  - >
    The most-recent non-null prior allocation is continuity authority. Invalid,
    non-finite or out-of-range content fails closed instead of searching older rows.
do_not_redo:
  - >
    Do not restore the retired midterm calendar veto or create a second
    allocation/override authority.
  - >
    Do not expand P0A into P0B, alerts, recommender removal or product redesign.
artifacts:
  - agentos/handoffs/CRYPTO-INTELLIGENCE-2026-08-23-p0a-btc-decision.md
  - contracts/btc_decision.schema.json
  - verify_shots/p0a_btc_decision/
needs_ceo:
  question: >
    Does Sol accept the exact P0A implementation on Draft PR #6294 and release
    it from HOLD-FOR-SOL?
  options:
    - "Accept and explicitly authorize release of the exact head."
    - "Reject with a named P0A defect for bounded repair."
  recommendation: >
    Review the exact final head and local/GitHub evidence; keep the hold unless
    the single-authority and fail-closed behavior are accepted without caveat.
  by_when: "Before any Draft/merge state change or P0B commission."
---

P0A began from the Sol CEO directive to repair only Bitcoin Vector decision
authority and stop for review. Sol's bounded return was repaired on the same
branch and PR, without starting P0B or changing the hold. The durable
implementation and exact evidence live in PR #6294 and the linked handoff; the
workstream record grants no runtime or merge authority.

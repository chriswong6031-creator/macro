---
key: CRYPTO-INTELLIGENCE
title: Governed crypto intelligence and decision presentation
objective: >
  Keep BTC Vector and adjacent crypto surfaces provenance-honest, with one
  declared authority for every decision-bearing output and advisory evidence
  unable to silently override it. Each wave is complete only at its separately
  authorized acceptance boundary.
status: active
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
      Sol accepted the P0A decision logic at exact head 9ce6ce711602 and then
      ruled that continuously regenerated site/vector.html is not feature-branch
      release ownership. Normal reconciliation merge 78b07d80b9f7 picked up
      current main 5ad13e2ed335, retained every accepted P0A source blob, restored
      site/vector.html byte-for-byte to current-main truth and removed the
      branch-only e7978af3 CSS asset. A final pre-push normal merge carries
      unrelated current-main parent a8b7de1a47ae without changing any protected
      P0A path. The source build wave is done; exact-head CI, merge, canonical
      main render and production acceptance remain active.
  - id: P0B
    title: Crypto H5 authority closure
    status: todo
    depends_on: [P0A]
    next_action: >
      Remain unstarted until Sol separately commissions P0B after P0A release.
next_action: >
  Prove the exact reconciliation head, release and merge existing PR #6294 only
  under Sol's pre-authorized clean-merge conditions, then wait for the canonical
  main render and verify the real production Vector. Keep P0B, alerts and broader
  redesign unstarted.
owns_paths:
  - "engine/btc_decision.py"
  - "contracts/btc_decision.schema.json"
  - "scripts/build_vector.py"
  - "templates/vector.html.j2"
  - "tests/test_btc_decision.py"
decisions:
  - "DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED"
landmines:
  - >
    site/vector.html is a canonical-render publication artifact for this release,
    not a P0A feature-branch delta. Do not regenerate it before merge; production
    proof belongs after the normal main render completes.
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
---

P0A began from the Sol CEO directive to repair only Bitcoin Vector decision
authority and stop for review. Sol accepted the repaired source logic and later
authorized generated-artifact ownership reconciliation plus merge under exact
mechanical gates. The durable implementation and evidence remain in PR #6294
and the linked handoff. P0B still requires a separate commission.

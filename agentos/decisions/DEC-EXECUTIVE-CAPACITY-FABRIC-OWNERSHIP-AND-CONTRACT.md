---
key: EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT
question: >
  Should heterogeneous Executive worker capacity be implemented by adding a new
  ProviderAccount/quota database inside Mastermind Executive OS, by importing Macro
  provider internals directly, or by projecting the existing Shared AI Provider Control
  Plane through one secret-free versioned capacity contract consumed by Executive placement?
answer: >
  Extend the existing `shared-ai-provider-control` program. Macro remains the canonical
  provider availability/auth-pool/cooling/quota-capacity owner and emits a deterministic,
  secret-free `mastermind.provider_capacity.v1` projection. Mastermind Model Router remains
  the stateless task-to-acceptable-model/execution-class filter. Executive OS remains the
  sole Job/Attempt/Worker/Event lifecycle and placement authority and may later consume the
  capacity projection when choosing among workers that are already eligible under its own
  route, authority, capability, independence and quota-registration law. Do not create a
  second provider/account/quota truth store.
rationale: >
  The provider substrate already exists and is materially richer than the older Phase 1G
  drafts assumed: Macro has multi-account Claude and Codex capability identities, isolated
  Codex homes, presence checks that do not open credentials, provider-reported and estimated
  budget evidence, cooling/reset semantics, provider-health error classes and a cross-repo
  provider-capacity boundary with Portfolio. Rebuilding those facts in Executive SQLite would
  create competing identities and correction semantics. Direct floating imports from Macro
  into Mastermind would instead couple Executive correctness to a moving implementation.
  A versioned projection preserves one canonical owner while giving Executive placement a
  stable, auditable input. The contract keeps unknown/stale evidence honest and can later
  express Z.AI/Alibaba subscription plans, ACP workers, metered APIs and local capacity
  without vendor-specific scheduler forks.
alternatives:
  - option: Add ProviderAccount, CapacityPool and QuotaHorizon tables to Executive SQLite
    why_not: >
      Duplicates Macro `shared-ai-provider-control`, creates a second credential/account/quota
      identity plane, and makes provider corrections race Executive lifecycle state. It also
      conflicts with the current sequencing in which Phase 1F-C owns schema v4.
  - option: Import `engine.neuralweb.key_pool`, `engine.llm_auth` and provider modules directly from Macro
    why_not: >
      The cross-repository audit already identifies floating implementation/version coupling
      as a hardening risk. Executive placement needs a versioned contract, not an implicit
      dependency on whatever Macro implementation happens to be checked out.
  - option: Put provider availability and quota logic into the Mastermind Model Router
    why_not: >
      Model suitability and live capacity answer different questions. Mixing them makes a
      deterministic task/model policy stateful and encourages provider health to redefine
      model quality or authority.
  - option: Build one scheduler/adapter policy per provider
    why_not: >
      Hard-codes vendor ordering, makes quota semantics incomparable, and forces every new
      coding-plan or ACP provider to grow another placement/control plane instead of joining
      one normalized capacity fabric.
evidence:
  - "Macro config/mastermind_programs.yml @ 21f51a1ecfed778a738b048bd7e5efd30b1d9336 — `shared-ai-provider-control` owns provider availability/capacity coordination and shared auth-pool/cooling semantics; Mastermind is an adapter"
  - "Macro engine/neuralweb/key_pool.py @ 21f51a1 — usage_snapshot exposes presence, enablement, cooling, reset hints, estimated window/week usage, safe ratelimit headers and outcomes without returning secret values"
  - "Macro engine/metabolism/budget_gate.py @ 21f51a1 — reported-first utilisation, estimated fallback, 429 window evidence and explicit unknown-usage behavior"
  - "Macro engine/codex_provider.py @ 21f51a1 — isolated CODEX_ACCOUNT_HOMES and stable capability IDs; auth files are presence-checked but never opened"
  - "Macro research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md — provider/auth-capacity bridge is safe while floating implementation coupling requires hardening"
  - "Mastermind research/EXECUTIVE_OS_PHASE1FC_CEO_POLICY_AND_IMPLEMENTATION_COMMISSION_2026-08-20.md — later accepted COO-cycle law owns schema-v4 placement/principal evidence"
  - "Mastermind control_plane/model_router.py + config/executive_worker_routes.json — current deterministic task/model routing remains separate from provider capacity"
affects:
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - shared-ai-provider-control
  - macro/engine/**
  - mastermind/control_plane/**
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-22
---

## Operational consequence

Provider Control answers **what intelligence capacity exists and what is currently known about
its usability**. Model Router answers **what model/execution classes are acceptable for the
Job**. Executive OS answers **which already-eligible worker actually receives one Attempt**.
Neither provider observations nor model output grants authority.

`mastermind.provider_capacity.v1` is a projection, not a new lifecycle store. A later
Executive placement receipt may bind the exact projection/snapshot digest used for a claim,
but it must never mutate historical placement evidence when provider state is corrected later.

## No-rebuild boundary

Do not add an Executive provider-account database, a second quota ledger, a second cooling
ledger, another host/session registry, a provider-specific scheduler, or a hidden retry/failover
plane. New providers extend Shared Provider Control plus reviewed worker harnesses; they do not
change the ownership law above.

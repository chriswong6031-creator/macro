---
key: CROSS-REPO-CONTRACT-GOVERNANCE
title: Cross-Repository Contract Governance — Macro / Terminal / Portfolio
objective: >
  Make every material cross-repository producer/consumer seam explicit, versioned,
  correction-safe, authority-safe and production-provable through its existing system
  so a fresh Sol/Fable session can determine exactly what crosses repositories, what
  it is allowed to do, and whether the real consumer path is live. Done means every
  major seam is formally contracted and production-proven or explicitly rejected by
  design, with current semantic-system and Agent OS records matching canonical proof.
status: active
program: cross-repo-contract-governance
repos: [macro, terminal, mastermind]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: R0
    title: Durable home and architecture freeze
    status: awaiting_ci
    pr: 6596
    next_action: >
      Sol reviews exact PR #6596 head after required hosted validation; only accepted
      merge may make R0 durable on main. R0 creates no Executive Job and proves no
      Fable execution.
  - id: R1
    title: P0 authority and imported-state identity
    status: todo
    depends_on: [R0]
    next_action: >
      After R0 is durable and an actual Fable principal carrier is claimed, execute
      CRG-NW-AUTHORITY-V1 then CRG-MACRO-IMPORT-IDENTITY-V1 under fresh collision checks.
  - id: R2
    title: High-value real-consumer contracts
    status: todo
    depends_on: [R1]
    next_action: >
      Contract and prove Prophet, Terminal washout authority, intel, risk, opportunity
      and the other material live consumers one independently useful vertical at a time.
  - id: R3
    title: Shared semantic consolidation
    status: todo
    depends_on: [R2]
    next_action: >
      Generate consumer conformance fixtures/manifests and route/schema/freshness
      descriptors from canonical producer contracts without creating a runtime registry.
  - id: R4
    title: Reverse publication ownership
    status: todo
    depends_on: [R1]
    next_action: >
      Replace Portfolio's direct Macro working-tree commit/push behavior through a proven
      existing owner-native publication path, one real artifact family per carrier.
  - id: R5
    title: Production contract dossier
    status: todo
    depends_on: [R2, R3, R4]
    next_action: >
      Produce exact-release production receipts for every material seam, including
      negative/stale/null/correction/auth/privacy states and actual consumer behavior.
  - id: R6
    title: Semantic and Agent OS closeout
    status: todo
    depends_on: [R5]
    next_action: >
      Reconcile the semantic system map/registry and Agent OS only after canonical proof
      exists; remove stale unresolved claims without advancing any layer beyond evidence.
decisions:
  - DEC:CROSS-REPO-CONTRACT-GOVERNANCE-FEDERATED-NO-RUNTIME
landmines:
  - >-
    Agent OS is organizational memory only. `status: active`, `owner: ceo-sol`, a Fable
    handoff, or an advisory claim is not proof that a Job/Worker/session is running.
    Executive OS/runtime evidence owns liveness.
  - >-
    Governance must never become a traffic proxy, release gate, contract-status runtime,
    queue, scheduler, retry plane, identity plane or second semantic/artifact registry.
  - >-
    Direct Terminal -> Portfolio integration is REJECTED_BY_DESIGN under the 2026-08-28
    freeze. Terminal Conviction Book, Macro descriptive portfolio context and Mastermind
    autonomous paper books are distinct objects; a future direct seam requires a concrete
    user/machine job and a new Sol ruling.
  - >-
    `PROVEN_LIVE` requires genuine exact producer->existing transport->actual consumer
    production proof. Schema existence, tests, merge, Slack delivery, Linear status and
    Executive QUEUED admission are weaker states.
  - >-
    Cross-repo fallback/last-good behavior is allowed only when it remains observable as
    last-good/stale/error. Readable old bytes must never make a stopped current producer or
    importer look healthy.
  - >-
    Macro Neural Web currently states all five Portfolio authority booleans FALSE/context-only.
    Consumer defaults can never silently widen authority; missing/unknown authority is inert.
  - >-
    Portfolio's `vendor/macro` / managed checkout is transport, not imported-state identity.
    Decision/run evidence must ultimately bind to one exact Macro revision/object generation
    through an existing receipt owner rather than a new database.
  - >-
    Portfolio's current snapshot exporter mutates/commits/pushes Macro `main`. Do not replace
    that defect by inventing a new Contract Bus; first prove the existing owner-native
    publication/object/API lane or return to Sol if none is lawful.
  - >-
    Watchers own attention only. After every nonterminal worker return Sol must explicitly
    continue/rule or STOP; terminal STOP/ACCEPTED requires worker stop + temporary watcher
    disarm, and watcher shutdown failure never authorizes another wave.
do_not_redo:
  - >-
    Do not create another semantic program. The parent already exists as
    `cross-repo-contract-governance` in `config/mastermind_programs.yml`.
  - >-
    Do not recreate `portfolio/prophet_feed.py`; the current adapter exists. Its remaining
    gap is formal contract/registry identity, authority, imported-state provenance and
    current production proof.
  - >-
    Do not reopen the historical Portfolio `/api/pfolio/*` source-code fail-open finding as
    if unfixed; current code is fail-closed on the authoritative VPS. Re-attest production
    rather than rebuilding the gate.
  - >-
    Do not flatten distinct producer clocks into one generic `fresh_at`. Preserve source-native
    observed/as-of/known/import clocks and correction identity.
  - >-
    Do not turn governance conformance into signal, rank, sizing, Prophet, portfolio or trade
    authority.
artifacts:
  - docs/superpowers/specs/2026-08-28-cross-repo-contract-governance-design.md
  - docs/superpowers/plans/2026-08-28-cross-repo-contract-governance-r0.md
  - research/CROSS_REPO_CONTRACT_GOVERNANCE_CURRENT_STATE_2026-08-28.md
  - research/CROSS_REPO_CONTRACT_GOVERNANCE_R0_CARRIER_RECEIPT_2026-08-28.md
  - agentos/decisions/DEC-CROSS-REPO-CONTRACT-GOVERNANCE-FEDERATED-NO-RUNTIME.md
  - agentos/handoffs/CROSS-REPO-CONTRACT-GOVERNANCE-2026-08-28-fable-principal.md
next_action: >
  Complete exact-head validation and Sol review of PR #6596. After R0 merges, reconcile
  current runtime/transport state and establish one actual claimed Fable principal carrier
  for operation `crg-fable-principal-20260828-sol-001`; only then commission
  CRG-NW-AUTHORITY-V1 on a fresh stable child operation key.
---

## Context

The semantic registry has carried Cross-Repository Contract Governance as `building`, but the
program had no dedicated Agent OS execution home. The 2026-08-11 boundary audit identified
important cross-repo risks; by 2026-08-28 some findings had been repaired and others had drifted,
so the Chairman assigned Sol end-to-end ownership and explicitly approved the recovered
architecture.

R0 creates the missing organizational home without creating a second runtime. The current-state
census is `research/CROSS_REPO_CONTRACT_GOVERNANCE_CURRENT_STATE_2026-08-28.md`; the binding
architecture is `docs/superpowers/specs/2026-08-28-cross-repo-contract-governance-design.md`.

## Current capability frontier

The highest-priority current defects are:

1. **CRG-01 / BROKEN** — Macro Neural Web producer authority is all-false/context-only while
   Portfolio defaults can exceed that contract.
2. **CRG-02 / PARTIAL** — Portfolio's Macro imports are not universally attributable to one exact
   imported Macro revision/object generation per production decision/run.
3. **CRG-03 / BROKEN** — Portfolio currently writes into and commits/pushes the Macro working tree
   for reverse publication.
4. **CRG-04 / BUILT_NOT_PROVEN** — Portfolio Prophet adapter is real but formally unregistered and
   lacks a current production contract dossier.
5. **CRG-05 / BROKEN** — Terminal washout transport says display-only despite a real fenced
   admission consequence.
6. **CRG-06+ / PARTIAL** — several older Terminal bridges rely on implementation/test law rather
   than formal producer-owned schema/conformance/import receipts.

## Operating model

Sol remains accountable CEO for product thesis, authority, architecture and final acceptance.
Fable is the preferred sustained cross-repository principal COO after an actual carrier is claimed.
Routine implementation is decomposed into one useful producer + contract + consumer + proof
vertical per PR where possible. No child inherits authority merely because this parent exists.

The durable principal organizational operation key is
`crg-fable-principal-20260828-sol-001`. Until approved runtime/session evidence shows an actual
claim, it must be described as **UNCLAIMED**, not queued/executing/working.

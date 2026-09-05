---
key: SOL-CAPABILITY-FABRIC
title: Mastermind Sol Capability Fabric — governed executive visibility and control
objective: Give Chat-native CEO Sol one coherent, source-attributed and safely writable operating
  experience across the existing canonical systems. Complete only with Truth, Intelligence, Product
  and Learning proven through real production and measured canaries, not source, CI, merge, installation
  or QUEUED admission alone. Never create another lifecycle, authority, identity, memory, queue, retry
  or control plane.
status: active
program: project-active-build-control
repos:
- macro
- mastermind
owner: ceo-sol
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
- mastermind:docs/superpowers/specs/2026-08-30-sol-capability-fabric-design.md
- mastermind:docs/superpowers/specs/2026-08-30-sol-capability-fabric-prepared-action-token-correction.md
- mastermind:docs/superpowers/plans/2026-08-30-sol-capability-fabric-tool-catalog.md
- mastermind:docs/superpowers/plans/2026-08-30-sol-capability-fabric-program.md
- mastermind:docs/superpowers/plans/2026-09-01-sol-capability-fabric-package-generation-convergence-index.md
- agentos/workstreams/WS-SOL-CAPABILITY-FABRIC.md
- agentos/decisions/DEC-SOL-CAPABILITY-FABRIC-FEDERATED-TYPED-CONTROL.md
- agentos/discoveries/DSC-SCF-DIGEST-ONLY-PREPARED-ACTION-REQUIRES-HIDDEN-STORE.md
- agentos/discoveries/DSC-CAP-S1-SOURCE-ABSENT-W3A-COMPOSITION-REQUIRED.md
- agentos/discoveries/DSC-CAP-S1-CURRENT-CARRIER-REQUIRES-SERIALIZED-RELEASE-CLOSURE.md
- agentos/discoveries/DSC-BSC-E1-PR-SCOPE-FENCE-BECAME-FLEET-WIDE.md
- agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-08-30-f0-protected-gh0-next.md
- agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-09-01-cap-s1-current-source.md
- agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-09-02-autonomy-critical-path.md
- agentos/discoveries/DSC-MCP-RESEARCH-JSON-BYTE-AND-ERROR-BOUNDARY.md
- agentos/discoveries/DSC-COMPANY-DIALOGUE-OBSERVATION-IS-NOT-CALLER-AUTH.md
- agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-09-05-mcp-evidence-and-source-reconciliation.md
waves:
- id: SCF-F0
  title: Protect architecture, closed capability catalog, program DAG and prepared-action correction
  status: done
  pr: 283
- id: SCF-GH0
  title: Current GitHub estate, native/custom reuse and semantic-contract archaeology
  status: done
  pr: 294
  depends_on:
  - SCF-F0
- id: SCF-GH1
  title: Pure release and collision assessment engine
  status: in_progress
  pr: 295
  depends_on:
  - SCF-GH0
  next_action: Reconcile existing PR295 at actual head59b6e81bf147b3730b811c3ad252a4e65775b521; preserve
    its owner, source/integration distinction and independent review. Older body SHA is not current.
- id: SCF-CAP1
  title: Truthful capability-status projection over immutable owner facts
  status: in_progress
  pr: 290
  depends_on:
  - SCF-F0
  next_action: Reconcile existing PR290 at actual head15675237f1d2ac44d91ef5c53aa8c7e38a7a7d60; do
    not create another projector or assume old body proof describes this head.
- id: SCF-PKG0
  title: Protect immutable Operator package-generation and complete CAP-S1 source law
  status: done
  pr: 325
  depends_on:
  - SCF-F0
- id: CAP-S1
  title: Exact package verification, V4 canary profile and real four-Skill Codex vertical
  status: in_progress
  pr: 350
  depends_on:
  - SCF-PKG0
  next_action: 'Continue existing PR350 and its exact owner; current head6cc4c6c413b0572b54f194058b7714aa5df25d8d
    remains open. #329/#326 source releases are complete; do not revive their old wait. Historical
    consumed provider attempt is not reusable proof.'
- id: CAP-PROMOTE1
  title: Separately reviewed checked-in V4 policy, host and route promotion
  status: todo
  depends_on:
  - CAP-S1
- id: AUTONOMY-CI1
  title: Repair BSC-E1 historical release-scope tests without weakening source fences
  status: done
  pr: 381
  next_action: Source repair released through381/cba0424f10ad6a9a917234c6740d92b19b018642. Closed-unmerged373
    is historical and must not be reopened.
- id: AUTONOMY-RET1
  title: Deterministic sealed-worker terminal RESULT projection into Executive events
  status: done
  pr: 352
  depends_on:
  - AUTONOMY-CI1
  next_action: Source merged352/98bc4614f02aea82530ea4c7a076e9e6c898397a. Done means this source projection
    only, not live Company return, Wake or sustained-provider proof.
- id: AUTONOMY-WATCHER1
  title: Closed-template Sol watcher source and account deployment proof
  status: in_progress
  pr: 268
  next_action: Source merged268/8a985de8ce5d6107297fc8609b9391e7a1028d6a. Continue account-local proof
    and unattended dialogue under its actual owner; do not rebuild the renderer/auditor.
- id: SCF-GH2
  title: Live GitHub evidence composition and guarded native actions
  status: todo
  depends_on:
  - SCF-GH1
- id: SCF-RUN1
  title: Read-only runner observatory and queue diagnosis
  status: todo
  depends_on:
  - SCF-GH0
- id: SCF-S1
  title: Authenticated Steward company-state read app
  status: in_progress
  depends_on:
  - SCF-F0
  next_action: Closed-unmerged314 preserves source at a73020f485def3101b607387f054f23099244dc1. The
    existing Cockpit owner must reconcile the accepted successor; do not reopen314 or infer absent
    implementation from an old todo.
- id: SCF-E1
  title: One bounded authenticated Executive admission action
  status: in_progress
  pr: 363
  depends_on:
  - SCF-F0
  next_action: Preserve source363; historical CI prerequisite is already released381. Existing Business/Runtime
    owners must establish installed authentication/admission and current host grounding; no production
    proof is inferred.
- id: SCF-SURF1
  title: Exact Sol-surface and RuntimeBinding observability
  status: todo
  depends_on:
  - SCF-F0
- id: SCF-SURF2
  title: Exact provision, foreground and Wake action
  status: todo
  depends_on:
  - SCF-SURF1
- id: SCF-SURF3
  title: Context rotation, durable target transfer and predecessor fencing
  status: in_progress
  pr: 368
  depends_on:
  - SCF-SURF2
  next_action: Stage-B0 source law merged368/642fa62540f0f2565ccc484a350f2cd0a2259015. Reconcile current
    Runtime/Web owner dependencies for implementation and real succession; do not repeat the historical
    source-law repair.
- id: SCF-FLEET1
  title: Capacity, placement explanation and bottleneck reads
  status: in_progress
  pr: 329
  depends_on:
  - SCF-F0
  next_action: Capacity C1 source merged329/351402f4f5d5e55e8c0f0b7f973f01c19aa98d97. Current Capacity
    owner retains real placement/host proof; do not create another selector.
- id: SCF-FLEET2
  title: Semantic child commissioning through Executive OS and Capacity
  status: todo
  depends_on:
  - SCF-FLEET1
- id: SCF-OPS1
  title: Host, service, tunnel and deployment observability
  status: todo
  depends_on:
  - SCF-F0
- id: SCF-OPS2
  title: One predefined, owner-specific operational action
  status: todo
  depends_on:
  - SCF-OPS1
- id: SCF-A3
  title: Isolated, normally disabled administrative app generation
  status: todo
  depends_on:
  - SCF-OPS2
- id: SCF-OBS1
  title: Audit and economic-outcome measurement projection
  status: todo
  depends_on:
  - SCF-F0
- id: SCF-UI1
  title: Coherent Chat-native executive cockpit over accepted apps
  status: in_progress
  pr: 326
  depends_on:
  - SCF-CAP1
  - SCF-GH2
  - SCF-RUN1
  - SCF-E1
  - SCF-SURF3
  - SCF-FLEET2
  - SCF-OPS2
  - SCF-OBS1
  next_action: Control Room source merged326/b5baa9ed1a38bae5e6821e297f6757fabb7f33a2. Existing Cockpit
    owner retains installed and user-visible proof; this broad product wave is not done merely from
    source protection.
- id: SCF-CANARY1
  title: Reversible real multi-program canary with independent audit
  status: todo
  depends_on:
  - SCF-UI1
  - AUTONOMY-RET1
  - AUTONOMY-WATCHER1
- id: SCF-CUTOVER
  title: Evidence-based adoption and subtraction
  status: todo
  depends_on:
  - SCF-CANARY1
decisions:
- DEC:SOL-CAPABILITY-FABRIC-FEDERATED-TYPED-CONTROL
discoveries:
- DSC:SCF-DIGEST-ONLY-PREPARED-ACTION-REQUIRES-HIDDEN-STORE
- DSC:CAP-S1-SOURCE-ABSENT-W3A-COMPOSITION-REQUIRED
- DSC:CAP-S1-CURRENT-CARRIER-REQUIRES-SERIALIZED-RELEASE-CLOSURE
- DSC:BSC-E1-PR-SCOPE-FENCE-BECAME-FLEET-WIDE
- DSC:MCP-RESEARCH-JSON-BYTE-AND-ERROR-BOUNDARY
- DSC:COMPANY-DIALOGUE-OBSERVATION-IS-NOT-CALLER-AUTH
artifacts:
- agentos/discoveries/DSC-MCP-RESEARCH-JSON-BYTE-AND-ERROR-BOUNDARY.md
- agentos/discoveries/DSC-COMPANY-DIALOGUE-OBSERVATION-IS-NOT-CALLER-AUTH.md
- agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-09-05-mcp-evidence-and-source-reconciliation.md
landmines:
- Technical app/OAuth permission, source merge and installed presence are not organizational authority
  or production proof.
- EFFECT_UNKNOWN stays on its existing operation/carrier for canonical reconciliation; no retry, provider/account
  failover or writer election.
- Agent OS records organizational knowledge, never Job/Attempt/Worker liveness or dispatch. Carrier
  coordinates are lookup targets, not active-runtime assertions.
- Dated discoveries and handoffs retain their original observation epochs. Their prospective release
  instructions are superseded by the September5 handoff and current source predicates.
- Current PR head may differ from body/title and historical check claims. Bind actual immutable head
  and current integration separately.
- An SDK handler error flag must survive the owner converter; current observation actor text is not
  independent launching-process identity.
do_not_redo:
- Continue Macro PR6700 on its original branch; do not create another workstream or records carrier.
- Do not reopen Mastermind373 or redo source releases381,352,329,326,268,368.
- Do not replace source/review carriers for448 or open another JSON repair besides487.
- Do not restart stopped MCP-PV2; preserve its FAIL findings, published evidence and exact child-source
  shutdown.
- Do not replay consumed CAP-S1 provider attempts, promote default V4, or absorb the six marathon
  owners.
- Do not create a super-MCP, generic actuator, plugin memory, parallel SDK shim, binding/identity
  store, lifecycle, scheduler or retry owner.
- Do not infer production from source merges, compatibility tests, records or Slack delivery.
next_action: Consume R3 independent-review and MCP JSON repair returns on their exact existing carriers.
  Preserve Company466 and the six marathon implementation owners. Validate/review this same records
  PR against current Macro source; never redo released source predecessors or represent records as
  runtime acceptance.
---

# Current source and capability boundary

This is a bounded predicate refresh, not a fresh exhaustive inventory of every
planning wave. Unrefreshed todo states retain prior planning and cannot prove
that current code is absent; consult the exact owning carrier before commission.

This September5 reconciliation replaces the old September2 current-state view.
Source predicates and evidence are pinned in the dated handoff. Existing wave
identities and broad product dependencies are preserved; only CI1 and RET1's
source-defined missions are marked done from verified merges. Watcher rollout,
Capacity product proof, Cockpit experience and target-transfer implementation
remain in progress or explicitly unproven. Source368 is architecture, not built
succession. The six marathon CEOs retain their implementation and release roles.

MCP-PV2 evidence is accepted, not the safety of its three tested cells. Research
JSON repair487 remains pre-START at this observation; a placement request is not
a worker. R3 candidate d15fea1a is frozen pending its exact independent review
and separate current integration proof. Company466 still needs its actual
trusted launch-identity composition.

One Experience, Federated Authority remains controlling. Executive OS owns
lifecycle/admission; Agent OS owns knowledge; GitHub owns source/evidence;
RuntimeBinding and Wake own exact targets/attention; Capacity owns eligibility;
Slack is transport; Steward/Control Room compose reads. Full completion still
requires real intent-to-worker-to-return-to-Sol continuation, user-visible
current state, cleanup, restart/replay refusal and measurable reduction in
Chairman message shuttling. No production stage is graduated here.

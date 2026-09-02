---
key: SOL-CAPABILITY-FABRIC
title: Mastermind Sol Capability Fabric — governed executive visibility and control
objective: >
  Give Chat-native CEO Sol one coherent, source-attributed and safely writable
  operating experience across Mastermind's existing canonical systems without
  creating another lifecycle, authority, identity, memory, queue, retry or
  control plane. Done only when the full Truth, Intelligence, Product and
  Learning standard is proven through the real production path and measured
  canaries, not when source, CI, merge, installation or QUEUED admission alone
  is green.
status: active
program: project-active-build-control
repos: [macro, mastermind]
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
  - agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-08-30-f0-protected-gh0-next.md
  - agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-09-01-cap-s1-current-source.md
waves:
  - id: SCF-F0
    title: Protect architecture, closed capability catalog, program DAG and prepared-action correction
    status: done
    pr: 283
  - id: SCF-GH0
    title: Current GitHub estate, native/custom reuse and semantic-contract archaeology
    status: done
    pr: 294
    depends_on: [SCF-F0]
  - id: SCF-GH1
    title: Pure release and collision assessment engine
    status: in_progress
    pr: 295
    depends_on: [SCF-GH0]
    next_action: >
      Reconcile the same #295 carrier after its owner-convergence REQUEST_CHANGES;
      obtain fresh exact-head proof and review before any release or GH2 START.
  - id: SCF-CAP1
    title: Truthful capability-status projection over immutable owner facts
    status: in_progress
    pr: 290
    depends_on: [SCF-F0]
    next_action: >
      Finish the same #290 R2 write-guard repair and exact-head review; do not
      install a gatherer, app or write authority from the pure projector.
  - id: SCF-PKG0
    title: Protect immutable Operator package-generation and complete CAP-S1 source law
    status: done
    pr: 325
    depends_on: [SCF-F0]
  - id: CAP-S1
    title: Exact package verification, V4 canary profile and real four-Skill Codex vertical
    status: todo
    depends_on: [SCF-PKG0]
    next_action: >
      Capacity selects one concrete eligible CTO Sol receiver. The receiver then
      re-pins current protected source, returns the exact path/owner SCOPE_MAP,
      and creates one fresh CAP-S1 operation, branch and PR only after lawful
      pickup and separate START.
  - id: CAP-PROMOTE1
    title: Separately reviewed checked-in V4 policy, host and route promotion
    status: todo
    depends_on: [CAP-S1]
  - id: SCF-GH2
    title: Live GitHub evidence composition and guarded native actions
    status: todo
    depends_on: [SCF-GH1]
  - id: SCF-RUN1
    title: Read-only runner observatory and queue diagnosis
    status: todo
    depends_on: [SCF-GH0]
  - id: SCF-S1
    title: Authenticated Steward company-state read app
    status: todo
    depends_on: [SCF-F0]
  - id: SCF-E1
    title: One bounded Executive admission action
    status: todo
    depends_on: [SCF-S1]
  - id: SCF-SURF1
    title: Exact Sol-surface and RuntimeBinding observability
    status: todo
    depends_on: [SCF-F0]
  - id: SCF-SURF2
    title: Exact provision, foreground and Wake action
    status: todo
    depends_on: [SCF-SURF1]
  - id: SCF-SURF3
    title: Context rotation, binding transfer and predecessor fencing
    status: todo
    depends_on: [SCF-SURF2]
  - id: SCF-FLEET1
    title: Capacity, placement explanation and bottleneck reads
    status: todo
    depends_on: [SCF-F0]
  - id: SCF-FLEET2
    title: Semantic child commissioning through Executive OS and Capacity
    status: todo
    depends_on: [SCF-FLEET1]
  - id: SCF-OPS1
    title: Host, service, tunnel and deployment observability
    status: todo
    depends_on: [SCF-F0]
  - id: SCF-OPS2
    title: One predefined, owner-specific operational action
    status: todo
    depends_on: [SCF-OPS1]
  - id: SCF-A3
    title: Isolated, normally disabled administrative app generation
    status: todo
    depends_on: [SCF-OPS2]
  - id: SCF-OBS1
    title: Audit and economic-outcome measurement projection
    status: todo
    depends_on: [SCF-F0]
  - id: SCF-UI1
    title: Coherent Chat-native executive cockpit over accepted apps
    status: todo
    depends_on:
      - SCF-CAP1
      - SCF-GH2
      - SCF-RUN1
      - SCF-E1
      - SCF-SURF3
      - SCF-FLEET2
      - SCF-OPS2
      - SCF-OBS1
  - id: SCF-CANARY1
    title: Reversible real multi-program canary with independent audit
    status: todo
    depends_on: [SCF-UI1]
  - id: SCF-CUTOVER
    title: Evidence-based adoption and subtraction
    status: todo
    depends_on: [SCF-CANARY1]
decisions:
  - DEC:SOL-CAPABILITY-FABRIC-FEDERATED-TYPED-CONTROL
discoveries:
  - DSC:SCF-DIGEST-ONLY-PREPARED-ACTION-REQUIRES-HIDDEN-STORE
  - DSC:CAP-S1-SOURCE-ABSENT-W3A-COMPOSITION-REQUIRED
landmines:
  - >
    A technically broad OAuth scope, a successful connector call or an installed
    app is not organizational authority and is not PROVEN_LIVE.
  - >
    An ambiguous modifying response is EFFECT_UNKNOWN. Reconcile against the
    same canonical owner; never retry through another account, provider,
    surface or carrier.
  - >
    Agent OS records knowledge only. They do not create Jobs, Workers,
    RuntimeBindings, placements, ACK, START, production arming or acceptance.
  - >
    Protected W3A/current-writer semantics now occupy two CAP-S1 shared seams;
    CAP-S1 must compose them rather than restoring the older adapter/harness
    shape.
do_not_redo:
  - Do not build a universal super-MCP or generic shell, SQL, HTTP, filesystem or browser actuator.
  - Do not create plugin-owned memory, an MCP scheduler, a provider process spawner or another lifecycle.
  - Do not let GitHub, Slack, Linear or Agent OS originate Executive execution.
  - Do not select a numbered provider account, host, branch writer, credential or RuntimeBinding in model input.
  - Do not create a second Agent OS workstream or replacement carrier for this program; continue Macro PR #6700.
  - Do not revive or relabel the refused CAP-S1 native preflight, broker or provider operations as proof.
  - Do not release a parser-only package implementation or migrate the checked-in V3 policy inside CAP-S1.
next_action: >
  Obtain exact-head Macro Agent OS validation, fences and final Sol review on
  the same PR #6700 carrier, then protect the durable record with one guarded
  merge. After that record is protected, existing Capacity/Executive placement
  selects one concrete CTO Sol receiver for CAP-S1; until such a binding exists,
  CAP-S1 remains WAITING_CAPACITY / needs_placement and no implementation
  branch, PR, watcher or provider process is authorized.
---

# Current capability truth

Fresh reconciliation used protected Mastermind
`21a721427743fdae6d513eeb0f993ebd1c327a81` and same-commit Skillpack
`mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.

| Wave | Canonical state |
|---|---|
| SCF-F0 | `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED`; PR #283 merge `98bc7a71dcd70947c7a18eb5af7493a2f62a2571`. |
| SCF-GH0 | `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED`; PR #294 merge `eccf0a3fae8b8597c2ad0bc4f830e31b220415d2`. |
| SCF-GH1 | `BUILT_NOT_PROVEN / PRODUCTION_INERT / DRAFT / REQUEST_CHANGES`; canonical PR #295, branch head `7c84f65167be97285102e9c8bd903c4915a251f5`. |
| SCF-CAP1 | `BUILT_NOT_PROVEN / PRODUCTION_INERT / DRAFT / R2`; canonical PR #290, branch head `93f72d6198d6dab6bdfed0109583a01f33bafbe1`. |
| SCF-PKG0 | `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED`; PR #325 merge `484fb1d5b3660d69709767421c63aaa2fafb587a`. |
| CAP-S1 | `NOT_BUILT / NOT_PROVEN / PRODUCTION_UNARMED`; no source carrier or receiver binding. |
| CAP-PROMOTE1 | `NOT_BUILT`; forbidden before accepted CAP-S1 source and real isolated proof. |

The `project-active-build-control` program is the established organizational
grouping used by `WS:AGENT-OS`. It does not transfer SCF authority to Macro or
turn Agent OS into an execution plane.

# CAP-S1 current-source boundary

At the protected Mastermind SHA, `control_plane/executive_capability_packages.py`
does not exist and no CAP-S1 implementation PR or branch is present. The
checked-in capability policy remains V3. A records merge, a historical local
scratch file or a refused native operation is not source implementation.

Protected W3A merge `fc407e1638a26932c8615c98c7732d7f3202b3b1`
changed two shared CAP-S1 seams:

```text
control_plane/operator_harness_contract.py
control_plane/codex_operator_adapter.py
```

Any CAP-S1 implementation must preserve current OperationId/effect,
SessionEpoch/ProcessGeneration, same-current-writer Wake,
`attention_inflight`, ordinary text-turn and no-false-acknowledgement
semantics. Its Codex structured Skill input is an optional V4-canary extension,
not a replacement common wire.

The generic comparator defect remains present: one exact observed capability can
currently satisfy a required name through `any(...)` even when another
same-name observation exists. CAP-S1 must require exactly one matching observed
identity for each required name while preserving every non-duplicate decision
and the accepted W3A lifecycle/attention behavior.

# CAP-S1 complete useful vertical

```text
exact package source verification
-> opt-in V4 registry/profile compilation
-> exactly-one requested-vs-observed comparison
-> attempt-local verified Codex Skill projection
-> exact-binary protocol/schema attestation
-> empty/add-four/clear-empty causal proof
-> four path-bound real Operator Skill turns
-> source/list/schema invalidation
-> process/thread/artifact/projection cleanup
```

There is no independently releasable parser-only phase. CAP-S1 leaves the
checked-in default policy V3, adds no general route, rotates no host receipt and
arms no production fleet. `CAP-PROMOTE1` owns any later checked-in V4
policy/host/route migration.

# Authority boundary

- Executive OS owns Chairman-intent admission and Job / Attempt / Worker / Event lifecycle.
- Agent OS owns durable workstreams, decisions, discoveries and handoffs.
- GitHub owns implementation and evidence truth.
- RuntimeBinding / SessionTargetRegistry and Wake own exact Sol surfaces and attention.
- Capacity Fabric / Model Router own eligibility and provider/account/surface placement.
- Company Dialogue / Agent Relay / Slack own bounded dialogue and transport.
- Executive Steward / Chairman Control Room own cross-owner read composition.
- The Mastermind Sol plugin owns reviewed procedure only.

No child inherits START from this record. No worker-facing commission or
receiver-specific watcher is authorized before Capacity selects a concrete
receiver and the current commissioning procedure is satisfied.

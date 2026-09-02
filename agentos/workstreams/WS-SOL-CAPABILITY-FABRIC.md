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
  - agentos/discoveries/DSC-CAP-S1-CURRENT-CARRIER-REQUIRES-SERIALIZED-RELEASE-CLOSURE.md
  - agentos/discoveries/DSC-BSC-E1-PR-SCOPE-FENCE-BECAME-FLEET-WIDE.md
  - agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-08-30-f0-protected-gh0-next.md
  - agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-09-01-cap-s1-current-source.md
  - agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-09-02-autonomy-critical-path.md
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
      Finish the same #295 owner-convergence repair and obtain fresh exact-head
      proof and review before GH2 starts.
  - id: SCF-CAP1
    title: Truthful capability-status projection over immutable owner facts
    status: in_progress
    pr: 290
    depends_on: [SCF-F0]
    next_action: >
      Finish the same #290 consequential/admin write-guard repair and exact-head
      review; do not turn the pure projector into a gatherer or authority owner.
  - id: SCF-PKG0
    title: Protect immutable Operator package-generation and complete CAP-S1 source law
    status: done
    pr: 325
    depends_on: [SCF-F0]
  - id: CAP-S1
    title: Exact package verification, V4 canary profile and real four-Skill Codex vertical
    status: in_progress
    pr: 350
    depends_on: [SCF-PKG0]
    next_action: >
      Continue only on PR #350 with sticky Fable ownership. Close forged receipt,
      retained-descriptor, exact-binary evidence, skills/changed, closure and
      cleanup defects; serialize the Control Room install closure behind #329
      then #326; run one real four-turn read-only Codex canary only after source
      is exact and all pre-turn gates pass.
  - id: CAP-PROMOTE1
    title: Separately reviewed checked-in V4 policy, host and route promotion
    status: todo
    depends_on: [CAP-S1]
  - id: AUTONOMY-CI1
    title: Repair BSC-E1 historical release-scope tests without weakening source fences
    status: in_progress
    pr: 373
    next_action: >
      Require terminal exact-head repository/security proof and independent
      review, then expected-head squash merge only.
  - id: AUTONOMY-RET1
    title: Deterministic sealed-worker terminal RESULT projection into Executive events
    status: in_progress
    pr: 352
    depends_on: [AUTONOMY-CI1]
    next_action: >
      After #373 protects, history-preservingly compose #352 onto then-current
      protected master, rerun exact-head proof, preserve its four semantic blobs
      and two approvals, then release without calling it production-live.
  - id: AUTONOMY-WATCHER1
    title: Closed-template Sol watcher self-deadlock and multi-account authority hardening
    status: in_progress
    pr: 268
    next_action: >
      On the same carrier, repair duplicate-key parsing, discriminator versus
      NON_WATCHER classification, malformed-entry reporting and resource bounds;
      then current-base proof and exact-head review. Native task rollout remains separate.
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
    title: One bounded authenticated Executive admission action
    status: in_progress
    pr: 363
    depends_on: [SCF-F0]
    next_action: >
      Source is protected but production-disabled. First protect #373 so the
      repository gate is sound; installation, authentication and a real
      no-execution/QUEUED canary remain separate production proof.
  - id: SCF-SURF1
    title: Exact Sol-surface and RuntimeBinding observability
    status: todo
    depends_on: [SCF-F0]
  - id: SCF-SURF2
    title: Exact provision, foreground and Wake action
    status: todo
    depends_on: [SCF-SURF1]
  - id: SCF-SURF3
    title: Context rotation, durable target transfer and predecessor fencing
    status: in_progress
    pr: 368
    depends_on: [SCF-SURF2]
    next_action: >
      Repair Stage-B0 source law before Stage-B1: identify an accepted root/CEO
      binding producer with a binding-specific fingerprint, add one accepted
      canonical Codex CEO target through SessionTargetRegistry ownership, and
      use canonical reasoning_surface token chatgpt-sol. Do not implement Stage-B1 first.
  - id: SCF-FLEET1
    title: Capacity, placement explanation and bottleneck reads
    status: in_progress
    pr: 329
    depends_on: [SCF-F0]
    next_action: >
      Finish source-ref symmetry, stale/unknown discriminators, warm-cache
      selection and optional-Steward degradation on the same #329 carrier.
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
    next_action: >
      Keep #326 production-inert and serialized behind #329. After Capacity C1
      protects, current-base its existing Control Room carrier and close its
      exact remote-install closure before CAP-S1 consumes that closure.
  - id: SCF-CANARY1
    title: Reversible real multi-program canary with independent audit
    status: todo
    depends_on: [SCF-UI1, AUTONOMY-RET1, AUTONOMY-WATCHER1]
  - id: SCF-CUTOVER
    title: Evidence-based adoption and subtraction
    status: todo
    depends_on: [SCF-CANARY1]
decisions:
  - DEC:SOL-CAPABILITY-FABRIC-FEDERATED-TYPED-CONTROL
discoveries:
  - DSC:SCF-DIGEST-ONLY-PREPARED-ACTION-REQUIRES-HIDDEN-STORE
  - DSC:CAP-S1-SOURCE-ABSENT-W3A-COMPOSITION-REQUIRED
  - DSC:CAP-S1-CURRENT-CARRIER-REQUIRES-SERIALIZED-RELEASE-CLOSURE
  - DSC:BSC-E1-PR-SCOPE-FENCE-BECAME-FLEET-WIDE
landmines:
  - >
    A technically broad OAuth scope, successful connector call, protected source
    merge or installed app is not organizational authority and is not PROVEN_LIVE.
  - >
    An ambiguous modifying response is EFFECT_UNKNOWN. Reconcile against the
    same canonical owner; never retry through another account, provider,
    surface or carrier.
  - >
    Agent OS records knowledge only. They do not create Jobs, Workers,
    RuntimeBindings, placements, ACK, START, production arming or acceptance.
  - >
    Historical release-scope tests must bind their immutable release commit and
    parent. Binding them to current HEAD turns one PR's scope fence into a fleet-wide false red.
  - >
    CAP-S1, Control Room and Capacity share release-closure paths. Preserve the
    serialization #329 -> #326 -> #350 rather than allowing parallel writers.
  - >
    Stage-B cannot bootstrap initial assignment from caller-created
    root_job_bindings or a destination Wake ACK; the binding producer and one
    canonical Codex CEO target must be accepted first.
do_not_redo:
  - Do not build a universal super-MCP or generic shell, SQL, HTTP, filesystem or browser actuator.
  - Do not create plugin-owned memory, an MCP scheduler, provider process spawner or another lifecycle.
  - Do not let GitHub, Slack, Linear or Agent OS originate Executive execution.
  - Do not select a numbered provider account, host, branch writer, credential or RuntimeBinding in model input.
  - Do not create a second Agent OS workstream or replacement carrier for this program; continue Macro PR #6700.
  - Do not create replacement carriers for #350, #329, #326, #352, #268 or #368.
  - Do not revive or relabel refused historical CAP-S1 native attempts as current proof.
  - Do not release a parser-only package implementation or migrate checked-in V3 policy inside CAP-S1.
  - Do not implement Stage-B1 before root-binding authority and canonical Codex target prerequisites are protected.
next_action: >
  Protect the one-file BSC-E1 CI repair on Mastermind PR #373 after exact-head
  proof and independent review; then current-base and release RET1 PR #352.
  In parallel continue the existing #329 -> #326 -> #350 chain, the same-carrier
  #268 watcher repair, and the #368 Stage-B0 predecessor correction. Merge this
  same Agent OS carrier only after current-base validation; it grants none of
  those operations START or production acceptance.
---

# Current capability truth

Fresh reconciliation used protected Mastermind
`24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8` and same-commit Skillpack
`mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.

| Capability | Current state |
|---|---|
| Authenticated Executive admission app, BSC-E1 | Protected source, production-disabled, `BUILT_NOT_PROVEN`; PR #363. |
| BSC-E1 historical release-scope test repair | PR #373 exact one-file candidate; security green, full repository proof/review pending at reconciliation. |
| Deterministic terminal RESULT projection, RET1 | PR #352 current semantic candidate; held only on #373 and a fresh current-base green run. |
| Capacity C1 | PR #329 `BUILT_NOT_PROVEN / REQUEST_CHANGES`; first owner in the #329 -> #326 -> #350 serialization. |
| Zero-Slack Control Room composition | PR #326 `BUILT_NOT_PROVEN / PRODUCTION_NOT_DEPLOYED`; held on #329. |
| CAP-S1 four-Skill Codex vertical | PR #350 `BUILT_NOT_PROVEN / RED / REPAIR`; real model proof and cleanup not accepted. |
| Sol watcher closed-template source | PR #268 `BUILT_NOT_PROVEN / REQUEST_CHANGES`; native three-account rollout not performed. |
| Stage-B durable target transfer | PR #368 records correction `REQUEST_CHANGES`; Stage-B1 runtime `NOT_BUILT / HELD`. |
| CAP-PROMOTE1 and full autonomous fleet cutover | `NOT_BUILT`; forbidden before accepted canaries. |

# Critical-path architecture

```text
#373 BSC-E1 CI-scope repair
  -> #352 RET1 current-base release

#329 Capacity C1
  -> #326 Control Room current-base release closure
  -> #350 CAP-S1 exact closure + real four-turn canary
  -> CAP-PROMOTE1 only after separate review

#268 watcher export hardening
  -> source release
  -> account-local replacement/readback
  -> unattended return -> Sol edge -> worker continuation -> terminal STOP canary

#368 Stage-B0 correction
  -> accepted root/CEO binding producer and binding fingerprint
  -> accepted canonical Codex CEO target
  -> Stage-B1 durable assignment/transfer runtime
```

These chains may progress concurrently only where changed paths and canonical
owners are disjoint. Within each chain, a later carrier must not absorb or race
its prerequisite owner.

# Completion boundary

The autonomous project is not complete when these PRs merge. Final acceptance
requires a real reversible multi-program interval demonstrating:

1. authenticated Chairman/Sol intent reaches the single Executive lifecycle;
2. Capacity selects an eligible worker without Chairman account selection;
3. CAP-S1 supplies the exact four governed Operator Skills to a real isolated worker;
4. RET1 projects mechanical terminal returns independently of voluntary Slack behavior;
5. current exact Sol receives attention, writes one lawful same-carrier edge, and the worker continues;
6. Stage-B transfers durable action authority without duplicate roots or stale writers;
7. Control Room presents source-attributed live state without Slack as truth;
8. terminal STOP, acknowledgement, source resolution and cleanup are visible;
9. restart/replay and effect-unknown paths fail closed;
10. instrumentation shows reduced Chairman message shuttling, session hunting and stale-project incidence.

Until those facts exist, protected source remains `BUILT_NOT_PROVEN` or
`PRODUCTION_INERT`, never complete autonomy.

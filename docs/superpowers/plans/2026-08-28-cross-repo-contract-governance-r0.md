# Cross-Repository Contract Governance R0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the single durable Agent OS execution home and approved architecture/commission records for Cross-Repository Contract Governance without changing any runtime, payload, transport, release gate, or seam implementation.

**Architecture:** R0 is a records/research-only vertical in Macro because the semantic parent already lives there. It creates one workstream, one federated/no-runtime decision, one current-state census, and one Sol-authored principal Fable handoff. The workstream records organizational continuity only; actual Fable execution remains unclaimed until an approved carrier produces evidence.

**Tech Stack:** Markdown/YAML frontmatter, existing Macro Agent OS validator, GitHub branch/PR/CI.

**Spec:** `docs/superpowers/specs/2026-08-28-cross-repo-contract-governance-design.md`

## Global Constraints

- Protected Skillpack pickup is `mastermindx-market-intelligence/Mastermind@97f85ce5b84030faf4d291f988a1c642fb15e80a`, schema `mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1`.
- R0 operation key is `crg-r0-governance-home-20260828-sol-001`.
- Principal organizational commission key is `crg-fable-principal-20260828-sol-001`.
- Semantic parent is the existing `cross-repo-contract-governance`; do not create another program.
- Agent OS is knowledge-only and may not dispatch, lease, schedule, rank, retry, gate, or determine worker liveness.
- Executive OS remains the sole Job/Attempt/Worker/Event and CEO-intent admission owner.
- No runtime/schema/payload/transport implementation changes in R0.
- No direct Terminal -> Portfolio seam is authorized; it remains `REJECTED_BY_DESIGN` under the approved architecture.
- Every watcher-enabled future child must obey reciprocal continuation and explicit STOP/disarm discipline from the current `COMMISSION_WAVE.md`.
- R0 merge is not Fable pickup, Executive admission, seam repair, or production proof.

---

### Task 1: Create the current-state census

**Files:**
- Create: `research/CROSS_REPO_CONTRACT_GOVERNANCE_CURRENT_STATE_2026-08-28.md`

**Interfaces:**
- Consumes: current semantic registry, current protected Skillpack, current three-repository heads, the historical `research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md`, and current seam implementation evidence.
- Produces: the authoritative R0 census referenced by the workstream, decision, and Fable handoff.

- [ ] **Step 1: Write the census with exact pickup pins and disagreement corrections**

The census must record at minimum:

```text
Macro: 24ccea3fe482ab97c415db387f272b34c4852ed3
Terminal: b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea
Portfolio/Skillpack: 97f85ce5b84030faf4d291f988a1c642fb15e80a
```

It must explicitly correct the two stale historical claims:

```text
Portfolio Prophet adapter: exists -> BUILT_NOT_PROVEN, not NOT_BUILT.
Portfolio pfolio auth: current code is fail-closed -> BUILT_NOT_PROVEN pending current production re-attestation.
```

It must preserve current critical defects:

```text
Neural Web authority mismatch -> BROKEN.
Macro imported-state identity in Portfolio -> PARTIAL.
Portfolio direct commit/push into Macro main -> BROKEN.
Terminal washout display-only description vs admission consequence -> BROKEN.
Older Terminal bridge formal-contract coverage -> PARTIAL.
Direct Terminal -> Portfolio -> REJECTED_BY_DESIGN under current architecture.
```

- [ ] **Step 2: Self-review the census against the approved contract-ledger fields**

Verify every material seam row names producer, owner, actual consumer, schema/version, clocks, null/correction behavior, auth/privacy, authority, fallback, proof state, and capability state. If evidence is not current enough for a field, write `unverified` rather than infer it.

- [ ] **Step 3: Commit the census on the R0 branch**

```bash
git add research/CROSS_REPO_CONTRACT_GOVERNANCE_CURRENT_STATE_2026-08-28.md
git commit -m "research(crg): record current three-repo contract census"
```

### Task 2: Create the Agent OS workstream and decision

**Files:**
- Create: `agentos/workstreams/WS-CROSS-REPO-CONTRACT-GOVERNANCE.md`
- Create: `agentos/decisions/DEC-CROSS-REPO-CONTRACT-GOVERNANCE-FEDERATED-NO-RUNTIME.md`

**Interfaces:**
- Consumes: semantic parent `cross-repo-contract-governance`, approved design, R0 census.
- Produces: one durable organizational execution home and one binding architecture/no-rebuild ruling.

- [ ] **Step 1: Author the workstream using `agentos.workstream.v1`**

Required identity:

```yaml
key: CROSS-REPO-CONTRACT-GOVERNANCE
program: cross-repo-contract-governance
repos: [macro, terminal, mastermind]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: scoped
```

Required waves:

```yaml
- id: R0
  title: Durable home and architecture freeze
  status: in_progress
- id: R1
  title: P0 authority and imported-state identity
  status: todo
- id: R2
  title: High-value real-consumer contracts
  status: todo
- id: R3
  title: Shared semantic consolidation
  status: todo
- id: R4
  title: Reverse publication ownership
  status: todo
- id: R5
  title: Production contract dossier
  status: todo
- id: R6
  title: Semantic and Agent OS closeout
  status: todo
```

The workstream must state that `owner: ceo-sol` is accountability, not a runtime claim, and that Fable is the preferred principal operator after an actual carrier is claimed.

- [ ] **Step 2: Author the architecture decision using `agentos.decision.v1`**

Decision answer must freeze:

```text
Federated producer-owned contracts + consumer conformance + existing transports + receipts.
No governance runtime/proxy/gateway/release gate/queue/store.
No direct Terminal -> Portfolio seam without a future concrete job and Sol ruling.
```

Include at least these rejected alternatives:

```yaml
- option: Central Contract Governance service/gateway
  why_not: Creates a second traffic/control plane and converts governance into runtime authority.
- option: Documentation-only audits with no producer/consumer conformance
  why_not: Cannot prevent semantic drift or fallback-green failures.
- option: Direct Terminal-to-Portfolio integration because both mention portfolio
  why_not: Conflates distinct products and invents a seam with no current user/machine job.
```

- [ ] **Step 3: Validate the two records locally or through the repository's canonical validation path**

Run when a repository checkout is available:

```bash
python3 scripts/agentos.py validate
```

Expected result: exit 0, zero new schema errors on the CRG records. Existing unrelated warnings do not make R0 complete, but no new CRG warning/error may be ignored without explanation.

- [ ] **Step 4: Commit the workstream and decision**

```bash
git add agentos/workstreams/WS-CROSS-REPO-CONTRACT-GOVERNANCE.md \
  agentos/decisions/DEC-CROSS-REPO-CONTRACT-GOVERNANCE-FEDERATED-NO-RUNTIME.md
git commit -m "records(crg): establish durable workstream and no-runtime law"
```

### Task 3: Create the Fable principal commission handoff

**Files:**
- Create: `agentos/handoffs/CROSS-REPO-CONTRACT-GOVERNANCE-2026-08-28-fable-principal.md`

**Interfaces:**
- Consumes: approved design, R0 census, workstream, decision, current `COMMISSION_WAVE.md` watcher law.
- Produces: a cold-stranger-complete organizational commission packet for the future actual Fable carrier.

- [ ] **Step 1: Author the handoff using `agentos.handoff.v1`**

The packet must name:

```text
operation_key = crg-fable-principal-20260828-sol-001
workstream = WS:CROSS-REPO-CONTRACT-GOVERNANCE
principal = Fable
current runtime state = UNCLAIMED unless an approved runtime receipt is appended later
```

It must include the first bounded children, each requiring its own later stable operation key and fresh collision check:

```text
CRG-NW-AUTHORITY-V1
CRG-MACRO-IMPORT-IDENTITY-V1
CRG-PORTFOLIO-PUBLICATION-V1
CRG-PROPHET-PORTFOLIO-V1
```

The initial sequence is authority -> imported identity -> publication ownership -> Prophet. Terminal washout and broader bridge formalization remain behind those P0/P1 dependencies.

- [ ] **Step 2: Include reciprocal watcher/STOP discipline**

The handoff must explicitly require:

```text
ACK exact operation on the same carrier.
BLOCKED / DECISION_REQUEST / RESULT are nonterminal unless Sol explicitly says STOP/ACCEPTED.
After a nonterminal return, re-arm the approved watcher/wait path.
If watcher unavailable, return WATCH_UNAVAILABLE.
On STOP/ACCEPTED, stop work, disarm temporary watcher, and do not originate another child.
Watcher shutdown failure never reopens the terminal child.
A new child requires a new operation key and explicit commission.
```

- [ ] **Step 3: State what the packet proves and does not prove**

Required statement:

```text
This Agent OS handoff is durable organizational commission truth only.
It is not EXECOS/CEO_REQUEST_V1, not a Job, not a Worker claim, not a Slack ACK, and not execution proof.
```

- [ ] **Step 4: Commit the handoff**

```bash
git add agentos/handoffs/CROSS-REPO-CONTRACT-GOVERNANCE-2026-08-28-fable-principal.md
git commit -m "records(crg): add Fable principal commission packet"
```

### Task 4: Open the R0 review carrier and freeze execution boundary

**Files:**
- Modify after PR creation: `agentos/workstreams/WS-CROSS-REPO-CONTRACT-GOVERNANCE.md`

**Interfaces:**
- Consumes: completed Tasks 1-3 and hosted GitHub checks.
- Produces: one reviewable R0 PR with exact carrier identity; no Fable execution claim.

- [ ] **Step 1: Re-pin Macro main and re-run collision search immediately before PR creation**

Required checks:

```text
current Macro main
open PRs matching cross-repo contract governance / target record paths
unexpected branch movement on sol/cross-repo-contract-governance-r0-20260828
```

If the R0 branch moved unexpectedly, stop and reconcile it under current `RECONCILE_STATE.md`; do not reset or replace it.

- [ ] **Step 2: Open one PR against Macro `main`**

PR title:

```text
records(crg): establish cross-repo contract governance execution home
```

PR body must say records/research only, list exact pickup pins, operation key, capability state `SPEC_ONLY` for architecture/R0, and explicitly state that no Fable/Executive execution is claimed.

- [ ] **Step 3: Update the workstream with the actual PR number and R0 review state**

After PR creation, change only the R0 wave:

```yaml
- id: R0
  title: Durable home and architecture freeze
  status: awaiting_ci
  pr: <actual PR number>
  next_action: Sol reviews exact PR head after required hosted validation; only accepted merge may make R0 durable on main.
```

Then commit the exact PR binding on the same branch.

- [ ] **Step 4: Require exact-head validation before Sol release**

At minimum verify the repository's selected Agent OS/schema and fence/CI checks for the exact final PR head. A docs/records merge may still not be represented as seam implementation or production proof.

- [ ] **Step 5: Stop R0 at Sol review**

Do not dispatch `CRG-NW-AUTHORITY-V1` from this records carrier. After R0 is merged and current runtime/transport gates are reconciled, Sol establishes one actual claimed Fable principal carrier. Only then may the first child be commissioned.
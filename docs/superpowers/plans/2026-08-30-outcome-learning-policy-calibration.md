# Outcome Learning & Policy Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a correction-safe organizational learning loop that preserves ex-ante expectations, compiles actual outcomes from existing canonical owners, states honest causal limits, and proves one reviewed operating-policy improvement without creating another memory, lifecycle, experiment, routing or policy authority.

**Architecture:** Register one advisory `organizational-learning` semantic program, then implement a deterministic Outcome Compiler in Mastermind over immutable owner references and versioned contracts. Routine evidence remains in Executive OS, GitHub, Agent Dialogue/Wake, Provider Control and Agent OS; only load-bearing consequences become Agent OS discoveries, and policy changes remain explicit Agent OS decisions tested through existing Executive/GitHub canary and proof paths.

**Tech Stack:** Python 3.11, frozen dataclasses/enums, canonical JSON + SHA-256, pytest, existing Macro semantic-map/Agent OS validators, existing Mastermind Executive OS event/runtime contracts, GitHub evidence, optional JSON Schema only where the repository already uses it.

**Spec:** `docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-design.md`

## Global Constraints

- Operation key is `mastermind-outcome-learning-policy-calibration-20260830-sol-001`.
- Protected procedure basis is Mastermind `5a7046c46046a2ecf597c849aaab914b4f7cd5e1`, Skillpack v1.0.1/bootstrap major 1; every modifying wave must re-pin action-time protected procedure.
- Executive OS remains the sole Job/Attempt/Worker/Event lifecycle and placement owner.
- Agent OS remains the sole durable WS/DEC/DSC/handoff organizational-memory owner.
- GitHub remains implementation, review, CI, merge and production-evidence truth.
- Provider Control owns provider/account/quota/cooling state; Model Router owns deterministic suitability policy.
- Wake is attention only; Slack is transport/hot state; Linear is selective projection.
- Do not add an outcome DB, general company experiment registry, worker/model leaderboard, universal identity store, lifecycle, queue, watcher, retry plane, routing authority, hidden utility score or automatic policy editor.
- Do not ingest or persist private chain of thought, credentials, provider tokens or raw secret-bearing account data.
- No wave may infer that a schema, generated report, green CI, merge or Slack delivery proves the complete learning loop.
- Every implementation PR unlocks one independently useful capability and stops. A later wave requires a fresh commission, pickup ACK, separate START, review and terminal STOP.
- Current active owner collisions must be re-read before each wave, especially Macro PR #6615, Macro PR #6642, Mastermind PR #255 and Mastermind PR #266.
- Where the current codebase differs from a path or symbol below, stop with a typed `DECISION_REQUEST`; do not create a parallel subsystem to preserve this plan's spelling.

---

## Delivery topology

| Wave | Repository | Independently useful capability | Must not absorb |
|---|---|---|---|
| OL-1 | Macro | Truthful semantic program + durable Agent OS home | Compiler/runtime |
| OL-2 | Mastermind | Pure validated expectation/study contracts + fixture compiler | Live owner reads/policy |
| OL-3 | Mastermind | Read-only owner evidence bundle + real descriptive study | Causal promotion |
| OL-4 | Mastermind, then Macro record amendment | Decision-time expectation capture in existing owners | Exploration/canary |
| OL-5 | Mastermind | Law-compliant handoff preflight/checksum shadow + randomized canary | Worker routing change |
| OL-6 | Macro | Independent study review, DSC consequence and DEC ruling | Runtime implementation |
| OL-7 | Owning runtime + GitHub proof | Approved policy production proof and delayed follow-up | New policy beyond DEC |

OL-0 is this records-only architecture carrier and has no runtime deliverable.

---

### Task 1: OL-1 — Register the semantic program and durable workstream

**Files:**
- Modify: `config/mastermind_programs.yml`
- Modify: `tests/test_mastermind_system_map.py`
- Regenerate: `docs/MASTERMIND_SYSTEM_MAP.md`
- Create: `agentos/workstreams/WS-OUTCOME-LEARNING-POLICY-CALIBRATION.md`
- Preserve: `agentos/decisions/DEC-OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE.md`
- Preserve: `agentos/discoveries/DSC-HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED.md`

**Interfaces:**
- Consumes: current semantic registry and Agent OS schema on action-time Macro `main`.
- Produces: program key `organizational-learning` and workstream key `WS:OUTCOME-LEARNING-POLICY-CALIBRATION` for all later waves.

- [ ] **Step 1: Re-pin and collision-census the exact execution base**

Run:

```bash
git fetch origin main
git switch --detach origin/main
git rev-parse HEAD
gh pr view 6615 --json state,isDraft,baseRefName,headRefName,mergeStateStatus,files
rg -n '^  organizational-learning:' config/mastermind_programs.yml || true
rg -n '^key: OUTCOME-LEARNING-POLICY-CALIBRATION$' agentos/workstreams || true
python3 scripts/agentos.py validate
```

Record the exact base SHA and the current program count from:

```bash
python3 - <<'PY'
import yaml
with open('config/mastermind_programs.yml', encoding='utf-8') as f:
    print(len(yaml.safe_load(f)['programs']))
PY
```

Stop if another branch/PR owns either key or if #6615/current semantic work is changing the same paths without a reconciled landing order.

- [ ] **Step 2: Write the focused failing program-boundary test**

Append a test named exactly:

```python
def test_organizational_learning_program_is_advisory_and_does_not_duplicate_owners(model):
    program = model.registry["programs"]["organizational-learning"]
    assert program["category"] == "project_infrastructure"
    assert program["kind"] == "research_program"
    assert program["lifecycle_state"] == "building"
    assert program["scope"] == "project"
    assert program["product_surfaces"] == []
    assert program["decision_boundary"]["authority_class"] == "advisory_only"

    boundary = " ".join(program["does_not_own"]).lower()
    for forbidden_owner in (
        "lifecycle",
        "routing",
        "provider",
        "experiment registry",
        "policy authority",
        "worker leaderboard",
    ):
        assert forbidden_owner in boundary

    bindings = {(row["repo"], row["role"]) for row in program["repo_bindings"]}
    assert ("macro", "state_owner") in bindings
    assert ("mastermind", "implementation_owner") in bindings
```

Update the existing exact program-census assertion from the value observed in Step 1 to exactly that value plus one. Preserve the historical census comment and append a dated organizational-learning line; do not erase prior additions.

- [ ] **Step 3: Prove the test is red for the intended reason**

Run:

```bash
python3 -m pytest \
  tests/test_mastermind_system_map.py::test_organizational_learning_program_is_advisory_and_does_not_duplicate_owners \
  -q
```

Expected: `KeyError: 'organizational-learning'`. Any other failure is a current semantic-system problem and must be returned before editing the registry.

- [ ] **Step 4: Add exactly one semantic program**

Add this program block, preserving current registry ordering conventions:

```yaml
  organizational-learning:
    name: Organizational Outcome Learning and Policy Calibration
    category: project_infrastructure
    kind: research_program
    lifecycle_state: building
    scope: project
    purpose: >
      Preserve decision-time expectations, compile correction-safe consequences from
      existing canonical owners, quantify comparability and causal uncertainty, and
      support explicit reviewed improvement of Mastermind operating policy.
    strategic_role: >
      Give the organization a scientific memory of what it expected, what happened,
      what was attributable enough to learn from, and which policy change is justified.
    owns:
      - Decision-expectation and outcome-study semantic contracts
      - Organization-level metric, causal-grade, correction and policy-canary methodology
      - Outcome Compiler research, implementation and internal study experience
    does_not_own:
      - Executive Job, Attempt, Worker, Event, placement, retry or lifecycle authority
      - Model routing, worker eligibility, provider account, quota or cooling truth
      - Portfolio or market experiment registry, qledger, Eval OS or signal promotion
      - Agent OS memory primitives, source-law policy authority or automatic policy edits
      - Worker leaderboard, universal productivity score or punitive individual ranking
      - GitHub implementation, review, CI, merge or production-evidence truth
    repo_bindings:
      - repo: macro
        role: state_owner
      - repo: mastermind
        role: implementation_owner
    relationships:
      consumes_from:
        - project-active-build-control
        - shared-ai-provider-control
      coordinates_with:
        - mastermind-semantic-system-map
        - cross-repo-contract-governance
    canonical_docs:
      - repo: macro
        path: docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-design.md
      - repo: macro
        path: agentos/decisions/DEC-OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE.md
    implementation:
      - repo: mastermind
        roots:
          - control_plane/outcome_learning_contracts.py
          - control_plane/outcome_compiler.py
    product_surfaces: []
    decision_boundary:
      authority_class: advisory_only
      summary: >
        Compiles evidence and proposes reviewed policy deltas; it creates no job,
        placement, route, promotion, merge, runtime mutation or source-law authority.
```

Do not add a product surface before a real study consumer is production-proven. Do not create a synthetic `executive-os` relationship merely because Executive OS is a required evidence owner.

- [ ] **Step 5: Regenerate and verify the semantic map**

Run:

```bash
python3 scripts/build_mastermind_system_map.py
python3 -m pytest tests/test_mastermind_system_map.py -q
```

Expected: deterministic generated-map delta plus passing semantic tests.

- [ ] **Step 6: Create the workstream under the exact program key**

Create `agentos/workstreams/WS-OUTCOME-LEARNING-POLICY-CALIBRATION.md` with this frontmatter:

```yaml
---
key: OUTCOME-LEARNING-POLICY-CALIBRATION
title: Outcome Learning and Policy Calibration — scientific operating-policy loop
objective: >
  Prove one correction-safe loop from sealed ex-ante expectation through owner-native
  outcomes, honest causal grading, independent review, explicit policy decision,
  bounded canary and delayed production proof without creating a parallel authority.
status: active
program: organizational-learning
repos: [macro, mastermind]
owner: ceo-sol
class: research
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-design.md
  - docs/superpowers/plans/2026-08-30-outcome-learning-policy-calibration.md
  - agentos/decisions/DEC-OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE.md
  - agentos/discoveries/DSC-HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED.md
  - mastermind/control_plane/outcome_learning_*.py
  - mastermind/tests/test_outcome_learning_*.py
depends_on: []
waves:
  - id: OL-0
    title: Estate research and architecture freeze
    status: done
  - id: OL-1
    title: Semantic program and durable workstream registration
    status: in_progress
  - id: OL-2
    title: Pure decision-expectation and outcome-study compiler
    status: todo
    depends_on: [OL-1]
  - id: OL-3
    title: Read-only owner adapters and one real descriptive study
    status: todo
    depends_on: [OL-2]
  - id: OL-4
    title: Decision-time expectation capture in canonical owners
    status: todo
    depends_on: [OL-3]
  - id: OL-5
    title: Law-compliant handoff-quality randomized canary
    status: todo
    depends_on: [OL-4]
  - id: OL-6
    title: Independent study review and explicit policy DEC
    status: todo
    depends_on: [OL-5]
  - id: OL-7
    title: Production policy proof and delayed consequence read
    status: todo
    depends_on: [OL-6]
decisions:
  - DEC:OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE
discoveries:
  - DSC:HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED
landmines:
  - "Raw success rates by worker/model are selection-biased and cannot identify route effects."
  - "Missing, immature, externally blocked and censored outcomes are never coerced to zero or failure."
  - "Statistical evidence proposes policy; it never grants authority or edits source law."
  - "Portfolio experiments and Eval OS remain domain-specific owners."
do_not_redo:
  - "Do not create another outcome, experiment, identity, lifecycle, queue, watcher, retry, routing or policy authority."
  - "Do not add an Agent OS LRN type unless repeated production evidence proves DSC/DEC semantically insufficient."
  - "Do not publish a worker/model leaderboard or hidden composite productivity score."
artifacts:
  - docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-design.md
  - docs/superpowers/plans/2026-08-30-outcome-learning-policy-calibration.md
  - agentos/decisions/DEC-OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE.md
  - agentos/discoveries/DSC-HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED.md
next_action: >
  Commission OL-2 as one pure Mastermind contract/compiler PR over fixtures, with no
  live owner reads, Executive schema mutation, policy change or canary.
---
```

The body must state that later waves are sequence, not active commissions.

- [ ] **Step 7: Validate Agent OS and exact changed files**

Run:

```bash
python3 scripts/agentos.py validate
python3 -m pytest \
  tests/test_mastermind_system_map.py \
  tests/test_agentos_compile.py \
  tests/test_agentos_schema.py \
  tests/test_agentos_status.py \
  -q
git diff --check
git diff --name-only origin/main...HEAD
```

Expected changed paths are only the five OL-1 files listed above. Open one bounded PR and stop. Green CI proves truthful registration only; it does not prove outcome learning.

---

### Task 2: OL-2 — Build pure contracts and deterministic compiler

**Task 2a boundary (2026-09-01, per the CCL reconciliation amendment §B):** the receipt-contract subset of this task — schema, sealing, and validation for `mastermind.decision_expectation_receipt.v2` (`docs/superpowers/specs/2026-09-01-outcome-learning-executive-memory-ccl-reconciliation-amendment.md` §C), with no compiler/study dependency — is `OL-2a` and must be protected before the first CCL-A3 effect (see Task 4's CCL-A3 gate cross-ref below). The compiler and everything else in this task remain OL-2 proper and are not required before CCL-A3.

**Files:**
- Create: `control_plane/outcome_learning_contracts.py`
- Create: `control_plane/outcome_compiler.py`
- Create: `tests/test_outcome_learning_contracts.py`
- Create: `tests/test_outcome_compiler.py`

**Interfaces:**
- Consumes: plain Python mappings/lists containing already-normalized owner references and observations; no network, repository, SQLite or provider reads.
- Produces: canonical JSON-compatible `DecisionExpectationReceipt` and `OutcomeStudy` values plus semantic hashes.

- [ ] **Step 1: Create the contract tests before implementation**

The tests must cover these exact public symbols:

```python
from control_plane.outcome_learning_contracts import (
    CausalGrade,
    DecisionExpectationReceipt,
    EvidenceOwner,
    OwnerRef,
    PolicyRecommendation,
    canonical_payload_hash,
)
from control_plane.outcome_compiler import StudySpec, compile_outcome_study
```

Required red tests:

```python
def test_expectation_hash_excludes_only_nonsemantic_generation_time(): ...
def test_expectation_rejects_outcome_observed_before_seal(): ...
def test_expectation_rejects_duplicate_action_ids(): ...
def test_deterministic_assignment_requires_null_counterfactual_probability_reason(): ...
def test_randomized_assignment_probabilities_sum_to_one(): ...
def test_owner_ref_preserves_owner_type_and_id_without_universal_identity(): ...
def test_missing_outcome_is_censored_not_zero(): ...
def test_ope_claim_requires_logged_propensities_and_overlap(): ...
def test_unmeasured_confounding_forces_partial_or_not_identified_grade(): ...
def test_randomized_canary_requires_preoutcome_assignment_and_guardrail_definitions(): ...
def test_model_summary_cannot_change_machine_grade_or_recommendation(): ...
def test_study_output_is_byte_deterministic_for_equal_semantic_input(): ...
```

- [ ] **Step 2: Define the closed enums and immutable references**

Implement:

```python
class EvidenceOwner(str, Enum):
    EXECUTIVE_OS = "executive_os"
    AGENT_OS = "agent_os"
    GITHUB = "github"
    AGENT_DIALOGUE = "agent_dialogue"
    PROVIDER_CONTROL = "provider_control"
    LINEAR = "linear"
    SLACK = "slack"

class CausalGrade(str, Enum):
    DESCRIPTIVE_ONLY = "descriptive_only"
    ADJUSTED_ASSOCIATION = "adjusted_association"
    PARTIALLY_IDENTIFIED = "partially_identified"
    OPE_SUPPORTED = "ope_supported"
    RANDOMIZED_CANARY = "randomized_canary"
    NOT_IDENTIFIED = "not_identified"

class PolicyRecommendation(str, Enum):
    NO_CHANGE = "no_change"
    MORE_EVIDENCE = "more_evidence"
    PROPOSE_DEC = "propose_dec"
    ROLLBACK_REVIEW = "rollback_review"

@dataclass(frozen=True)
class OwnerRef:
    owner: EvidenceOwner
    ref_type: str
    ref_id: str
    observed_at: str
    semantic_hash: str
```

All identifiers must be bounded, timestamps RFC3339 UTC, hashes `sha256:<64 lowercase hex>`, collections tuple-normalized, and unknown enum values rejected.

- [ ] **Step 3: Implement canonical semantic hashing**

Expose:

```python
def canonical_payload_hash(value: Mapping[str, Any]) -> str:
    """SHA-256 over UTF-8 canonical JSON: sorted keys, compact separators, no NaN."""
```

Nonsemantic wall-clock generation fields may be excluded only by the calling contract's explicit `semantic_dict()` method. The generic hasher must not guess field names.

- [ ] **Step 4: Implement `DecisionExpectationReceipt` validation**

Required fields and behavior:

- typed decision owner/ref and operation key;
- `recorded_at`, information cutoff and semantic hash;
- context source refs and bounded pre-outcome context;
- complete alternatives with eligibility/exclusion reason;
- chosen action;
- assignment method, policy version and probabilities/null reasons;
- expected metric vector with horizon, estimate and interval;
- guardrails, causal question, known confounders and privacy class;
- immutable `supersedes` reference for corrections.

Reject post-outcome source times, a chosen ineligible action, missing chosen action, duplicate alternatives, randomized probabilities outside `[0,1]`, supported probabilities not summing to one within `1e-9`, secret-like keys, raw transcript fields and any private-chain-of-thought field.

- [ ] **Step 5: Implement fail-closed causal admission**

Create a frozen `StudySpec` that names treatment, comparison, estimand, cohort rules, metric definitions, observation horizons, estimator, propensity source, censoring policy, sensitivity plan and guardrails.

`compile_outcome_study(...)` must apply this order:

1. validate identities and temporal order;
2. apply predeclared inclusion/exclusion rules;
3. preserve missing/immature/corrected observations;
4. compute deterministic descriptive metric vectors;
5. compute balance/overlap/effective-sample diagnostics when requested;
6. admit the highest grade whose required evidence is present;
7. lower the grade for uncontrolled censoring, unsupported actions, missing propensities, post-treatment leakage or unmeasured-confounding limits;
8. attach a recommendation class without enacting it;
9. emit deterministic machine output; optional prose remains a separate field excluded from machine rulings.

OL-2 may implement descriptive statistics and admission logic using Python standard library. Do not add a numerical dependency solely to imitate a production estimator before a real cohort exists.

- [ ] **Step 6: Prove hostile and determinism cases**

Run:

```bash
python3 -m pytest \
  tests/test_outcome_learning_contracts.py \
  tests/test_outcome_compiler.py \
  -q
python3 -m pytest tests/test_model_router.py tests/test_executive_runtime.py -q
git diff --check
```

Open one PR. Stop when fixture inputs deterministically produce an honest study and every unsupported causal claim fails closed. Do not add live owner reads or mutate Executive schemas in this PR.

---

### Task 3: OL-3 — Add read-only evidence bundles and produce one real descriptive study

**Files:**
- Create: `control_plane/outcome_evidence_bundle.py`
- Create: `scripts/build_outcome_study.py`
- Create: `tests/test_outcome_evidence_bundle.py`
- Create: `tests/fixtures/outcome_learning/`
- Create: `research/outcome_learning/<dated-study-id>.json`
- Create: `research/outcome_learning/<dated-study-id>.md`

**Interfaces:**
- Consumes: explicit read-only exports/receipts from Executive OS, GitHub, Agent OS and Agent Dialogue/Wake, each with owner ref, cutoff and hash.
- Produces: one immutable `mastermind.outcome_evidence_bundle.v1` and one `DESCRIPTIVE_ONLY` or `NOT_IDENTIFIED` study.

- [ ] **Step 1: Freeze one historical question without inspecting its result**

Use a bounded question such as whether current law-compliant handoffs with complete return packets have fewer handoff-attributable repair loops than incomplete historical handoffs. Record cohort rules, metric definitions and exclusions in a `StudySpec` before assembling outcomes. This first study is instrumentation validation and cannot promote policy.

- [ ] **Step 2: Implement a closed evidence-bundle contract**

The bundle must preserve typed refs, event/available/observed/corrected times, semantic hashes, source availability, redaction class and correction generation. It must not copy credentials, chain of thought or unrestricted raw transcript text.

- [ ] **Step 3: Build adapters only for currently available owner exports**

Each adapter accepts a supplied export path or mapping and performs no mutation. Missing sources produce a typed unavailable observation. Do not scrape Slack or GitHub through an undocumented runtime side channel; the production collection seam must be a reviewed owner API/export or an explicitly committed receipt.

- [ ] **Step 4: Compile and publish the first real study**

Run:

```bash
python3 scripts/build_outcome_study.py \
  --spec tests/fixtures/outcome_learning/historical_handoff_spec.json \
  --evidence tests/fixtures/outcome_learning/historical_handoff_evidence.json \
  --json-out research/outcome_learning/<dated-study-id>.json \
  --markdown-out research/outcome_learning/<dated-study-id>.md
```

The actual child-wave plan must replace `<dated-study-id>` with the frozen study ID before execution. Output must disclose missingness, censoring, source availability, comparability limits and why the study is not causal.

- [ ] **Step 5: Verify byte determinism and owner correction behavior**

Run the builder twice and compare SHA-256. Replace one fixture with a superseding owner correction; assert the new study links `supersedes`, preserves the old study and explains the changed source hash/result.

Stop after one real descriptive study proves the cross-owner read path. Do not call the historical association a policy effect.

---

### Task 4: OL-4 — Capture ex-ante expectations in canonical owners

**CCL-A3 gate cross-ref (2026-09-01, per the CCL reconciliation amendment §A.3–A.4):** the CCL program's first CCL-A3 effect may not begin before the minimal `OL-2a` receipt (Task 2a) is available and a sealed expectation/assumption receipt exists for that effect. The CCL program's canonical carrier owes the corresponding narrow correction before CCL-A3 START; this task does not implement that correction on the CCL side.

**Files:**
- Modify only after owner clearance: `control_plane/executive_runtime.py`
- Modify only after owner clearance: `control_plane/model_router.py`
- Create/modify focused tests discovered from current `tests/test_executive*.py` and `tests/test_model_router.py`
- Later Macro record/schema amendment only if accepted: `agentos/schema/decision.schema.yml`, `scripts/agentos.py`, focused Agent OS tests

**Interfaces:**
- Consumes: validated `DecisionExpectationReceipt` payload from OL-2.
- Produces: immutable Executive `DECISION_EXPECTATION_RECORDED` event linked to the owning Job/Attempt/placement; optional material DEC `ex_ante` block after separate Agent OS review.

- [ ] **Step 1: Reconcile active owners**

Do not start while Mastermind PR #255/#266 or their successors own the same runtime/router surfaces, or while Macro PR #6642 owns the DEC compiler/schema surface without explicit sequencing.

- [ ] **Step 2: Write atomic event tests**

Tests must prove: expectation is recorded before assignment/outcome; duplicate semantic hash is idempotent; conflicting second expectation fails; correction creates a superseding event; event transaction cannot partially commit; event carries route policy/capacity refs without copying provider secrets.

- [ ] **Step 3: Add the existing-owner event path**

Use Executive OS's current event append/transaction mechanism. Do not add a table. The event payload stores or references the sealed receipt and exact semantic hash. Existing Job/Attempt/Worker semantics remain unchanged.

- [ ] **Step 4: Extend route evidence without arming exploration**

Record the complete eligible action set after hard exclusions and the deterministic assignment method. Until an approved exploratory policy exists, assignment probabilities remain null with typed `DETERMINISTIC_NO_COUNTERFACTUAL_SUPPORT`; do not fake probabilities.

- [ ] **Step 5: Evaluate the optional DEC schema extension separately**

Only after Agent OS compiler owner clearance, add a closed optional `ex_ante` object to DEC if a material-decision canary proves that external receipt references are insufficient. Otherwise preserve expectations as linked evidence artifacts and avoid schema growth.

Stop when ex-ante expectations survive a real owner-native write/read round trip. No policy canary or randomization belongs in OL-4.

---

### Task 4E: OL-4E — Executive-memory efficacy benchmark (stub)

**Added 2026-09-01 per the CCL reconciliation amendment §G.** This is a stub for a later wave sequenced between OL-4D and OL-5A (governance §7 revision); it is not commissioned by this plan and carries no files, steps, or acceptance proof yet.

**Scope at commissioning time:** an empirical, non-psychological self-model for the logical office, partitioned by decision class/domain/ambiguity/blast radius/topology/model-surface cohort where known; forecast calibration, time-to-evidence bias, intervention classes, rework classes, assumption-failure patterns, and topology outcomes with sample size/coverage/uncertainty; never a universal CEO/worker/model score. Minimum three benchmark arms: memory-light reasoning, naive memory injection, anti-anchored two-pass memory (§F future retrieval law). Memory is promoted for use only on measured decision improvement with no hidden quality regression, mirroring the two-decision canary promotion discipline.

Do not begin implementation from this stub alone; a fresh commission with its own Files/Interfaces/Steps is required when OL-4E is actually scheduled.

---

### Task 5: OL-5 — Run the law-compliant handoff-quality canary

**Files:**
- Exact validator path must extend the current Commission Wave/handoff implementation discovered at START; do not create a parallel handoff subsystem.
- Create focused validator/randomization/outcome tests adjacent to that owner.
- Create one pre-registered canary spec and one immutable assignment/outcome study artifact.

**Interfaces:**
- Consumes: current required handoff fields and OL-4 expectation event.
- Produces: deterministic mission checksum, preflight pass/fail, blocked-random assignment receipt and randomized-canary evidence; never worker placement.

- [ ] **Step 1: Freeze eligibility and treatment before assignment**

Baseline and candidate must both satisfy current Commission Wave, routing, pickup ACK, START and dialogue-close law. Candidate adds only a deterministic validator/checksum for mission, non-goals, proof, stop and return packet.

- [ ] **Step 2: Build the validator with fail-closed reason codes**

Required reason codes include `MISSION_MISSING`, `NON_GOALS_MISSING`, `PROOF_TARGET_MISSING`, `STOP_CONDITION_MISSING`, `RETURN_PACKET_MISSING`, `AUTHORITY_PRECEDENCE_MISSING` and `CURRENT_STATE_MISSING`. Validator rejection prevents dispatch but grants no alternative route or authority.

- [ ] **Step 3: Pilot instrumentation without promotion claims**

Use pilot cases only to verify event identity, metric attribution, censoring and delayed follow-up. Mark pilot results `DESCRIPTIVE_ONLY`; exclude them from the promotion estimand.

- [ ] **Step 4: Freeze power/sequential and rollback rules**

Use observed pilot baseline rates to pre-register sample size or a valid sequential boundary, minimum detectable effect, missingness handling and guardrail stop thresholds. Do not repeatedly peek at ordinary confidence intervals and promote on the first favorable result.

- [ ] **Step 5: Run the bounded canary through Executive OS**

Randomize 1:1 within declared task-kind/risk/ambiguity/repository blocks where lawful. Record action probabilities before delivery. Exclude critical, destructive, exact-session, emergency, unresolved-owner and principal-ambiguity cases.

- [ ] **Step 6: Compile first-return, terminal and 14-day delayed outcomes**

Primary metric is `first_substantive_return_accepted_without_handoff_attributable_repair`. Guardrails include escaped defects, downstream rework, independent-review severity, effect-unknown, authority/duplicate-carrier defects, abandonment and cost/quota class.

Stop/rollback on a material safety or quality regression. Completion requires a real `RANDOMIZED_CANARY` study, not merely assignment code.

---

### Task 6: OL-6 — Independent review and explicit policy ruling

**Files:**
- Create: `agentos/discoveries/DSC-<CANARY-CONSEQUENCE>.md` with the final concrete key
- Create: `agentos/decisions/DEC-<HANDOFF-POLICY-RULING>.md` with the final concrete key
- Update: `agentos/workstreams/WS-OUTCOME-LEARNING-POLICY-CALIBRATION.md`

**Interfaces:**
- Consumes: exact-head canary study, assignment receipts, code/review/CI evidence and delayed outcomes.
- Produces: independent audit, one falsifiable load-bearing DSC, and one explicit promote/hold/reject DEC.

- [ ] **Step 1: Commission an independent reviewer**

The reviewer must not be the canary implementer. Review cohort leakage, randomization integrity, missingness, attribution, metric gaming, guardrails, sequential analysis, correction handling and whether the causal grade is earned.

- [ ] **Step 2: Record only a load-bearing consequence**

The DSC claim must be falsifiable by rerunning the exact study against cited owner hashes and must state what a fresh session does differently. Do not store every metric row in Agent OS.

- [ ] **Step 3: Decide policy through an ordinary DEC**

The DEC must choose `PROMOTE_BOUNDED`, `CONTINUE_CANARY`, `HOLD`, `ROLLBACK` or `REJECT`; state alternatives, rationale, evidence, confidence, reversibility, owner, rollout scope and rollback. The study recommendation cannot create the DEC automatically.

- [ ] **Step 4: Validate durable records**

Run:

```bash
python3 scripts/agentos.py validate
python3 -m pytest \
  tests/test_agentos_compile.py \
  tests/test_agentos_schema.py \
  tests/test_agentos_status.py \
  -q
```

Stop after the reviewed ruling; runtime application is OL-7.

---

### Task 7: OL-7 — Apply the approved policy and prove delayed benefit

**Files:**
- Modify only the existing owner path named by the OL-6 DEC.
- Update the workstream and closeout records only after production proof.

**Interfaces:**
- Consumes: accepted OL-6 DEC and exact canary/rollback contract.
- Produces: production-applied policy, visible proof, rollback receipt, terminal/delayed outcome study and durable closeout.

- [ ] **Step 1: Apply only the approved bounded delta**

No implementation worker may reinterpret or widen the DEC. Preserve baseline rollback and current routing/authority behavior.

- [ ] **Step 2: Prove the real production path**

Exercise one real eligible handoff through the actual validator, Executive admission/assignment, pickup ACK, START, return, review and terminal STOP path. Capture exact operation, Job/Attempt, GitHub and dialogue refs.

- [ ] **Step 3: Exercise rollback/adverse paths**

Prove malformed handoff rejection, source unavailability, stale expectation, duplicate carrier, effect-unknown and rollback behavior without creating a second lifecycle.

- [ ] **Step 4: Compile terminal and delayed studies**

After the declared maturation window, compare production policy outcomes against the pre-registered ruler. Confirm measured benefit remains supported and no hidden quality/safety regression appeared.

- [ ] **Step 5: Close durable state truthfully**

Mark OL-7 done only when production proof and delayed consequence exist. Update the workstream next action, any superseding DSC/DEC, exact PR/merge/deployed proof and the canonical Slack carrier. Linear may then project the accepted state; it must not lead it.

---

## Program verification matrix

| Claim | Minimum proof |
|---|---|
| Semantic home exists | Registry/system-map tests + Agent OS validation on exact head |
| Compiler exists | Hostile fixture tests + byte-deterministic output |
| Evidence joins correctly | Real owner refs/cutoffs/hashes + descriptive study |
| Ex-ante expectation is preserved | Owner-native pre-outcome event round trip + correction test |
| Canary is causal enough | Pre-registration + assignment probabilities + randomization/overlap/missingness audit |
| Policy changed lawfully | Independent review + DSC + explicit DEC + rollback scope |
| Improvement is real | Production path + terminal/delayed study + no guardrail regression |
| Sealed-before-effect (2026-09-01) | CCL-A3 effect timestamp postdates its OL-2a receipt `recorded_at`/`sealed_hash` |
| Assumption resolution states present (2026-09-01) | `assumption_resolutions[]` entries use only `HELD`/`FALSIFIED`/`UNRESOLVED`/`NOT_TESTED`/`CONFOUNDED`, never a forced binary |
| Memory-exposure lineage present (2026-09-01) | Receipt's `memory_exposure.consulted[]` names every DEC/DSC/source-law consulted with an `influence` value |
| PUBLIC_SAFE fail-closed (2026-09-01) | Every V1 durable learning artifact in a public repo carries an explicit `PUBLIC_SAFE` classification; unresolved/restricted material is withheld, not redacted-and-published |
| Two-pass retrieval delta recorded (2026-09-01) | A major ambiguous decision's memory-light first pass and source-attributed second pass produce a delta record naming what changed and what was rejected |

## Plan self-review

- The plan extends existing semantic, Agent OS, Executive, GitHub, dialogue, provider and routing owners; it creates no parallel authority.
- The first causal consumer is handoff quality, not worker/model ranking.
- Decision-process quality, probabilistic calibration and realized consequence remain separate.
- Missing, censored, externally blocked and delayed outcomes are not coerced to failures or zeros.
- A causal estimator cannot raise authority or hide missing support.
- Every wave has a distinct repository surface, acceptance proof and stop condition.
- Runtime/schema collisions are explicitly gated rather than papered over.
- Program completion requires one measured, reviewed, production-proven policy improvement with delayed guardrail follow-up.
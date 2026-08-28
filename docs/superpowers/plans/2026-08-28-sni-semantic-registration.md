# Single-Name Intelligence Semantic Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register `single-name-intelligence` as a canonical project-scope Mastermind program, create its durable Agent OS workstream, and close the SNI-1 semantic-program gate before any SNI-1A implementation begins.

**Architecture:** This is a records/semantic-map predecessor, not product code. It extends the existing `config/mastermind_programs.yml` authority and Agent OS workstream store; it creates no new registry, lifecycle, queue, runtime, identity, data, forecast, or product plane. The new program is a composition/research/product owner over existing canonical owners and retains a context-only authority ceiling.

**Tech Stack:** YAML semantic registry, Python system-map generator/tests, Agent OS Markdown/frontmatter validation.

**Spec:** `docs/superpowers/specs/2026-08-28-single-name-intelligence-os-design.md`, `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md`, and binding amendment `docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md`.

## Global Constraints

- Execute only after PR #6613 is merged on current `main`; do not make this registration the vehicle that lands the parent SNI-1 architecture.
- Program key is exactly `single-name-intelligence`.
- Data OS remains canonical issuer/security/listing identity authority; SNI owns no identity master.
- Earnings/Company Event, Fundamental Forensics, Capital Structure, Stock Identity/Market Timing, China System, Options Intelligence, Factor/Regime owners, Neural Web, Terminal market data/charting, qledger/Evaluation OS all retain their existing semantic ownership.
- `single-name-intelligence` owns derived reference-twin composition, single-name experience architecture, SNI-specific residual/response/forecast research definitions, and forecast-memory projection only.
- No product surface is claimed live by this registration; `product_surfaces` stays empty until a real SNI consumer ships.
- Decision boundary is `context_only`; this registration grants no rank, gate, size, signal, escalation, portfolio, execution, or trade authority.
- `docs/MASTERMIND_SYSTEM_MAP.md` is generated, never hand-edited.
- The Agent OS workstream must validate against the newly registered program key; do not create it under an approximate existing program.

---

### Task 1: Register the canonical semantic program

**Files:**
- Modify: `config/mastermind_programs.yml`
- Modify: `tests/test_mastermind_system_map.py`
- Regenerate: `docs/MASTERMIND_SYSTEM_MAP.md`

**Interfaces:**
- Consumes: existing `mastermind_programs.v1` schema and relationship vocabulary.
- Produces: canonical program key `single-name-intelligence` accepted by the semantic-system validator and available to Agent OS workstreams.

- [ ] **Step 1: Write the failing census/semantics test**

In `tests/test_mastermind_system_map.py`, update the program-count assertion from 60 to 61 and add a focused contract test:

```python
def test_single_name_intelligence_program_has_narrow_composition_boundary(model):
    program = model.registry["programs"]["single-name-intelligence"]
    assert program["category"] == "market_intelligence"
    assert program["kind"] == "intelligence_program"
    assert program["lifecycle_state"] == "building"
    assert program["scope"] == "project"
    assert program["product_surfaces"] == []
    assert program["decision_boundary"]["authority_class"] == "context_only"

    consumes = set(program["relationships"]["consumes_from"])
    assert {
        "fundamental-forensics",
        "earnings-intelligence",
        "capital-structure-intelligence",
        "market-timing-intelligence",
        "china-system",
        "options-intelligence",
        "factor-intelligence",
    } <= consumes

    does_not_own = " ".join(program["does_not_own"]).lower()
    for forbidden_owner in (
        "identity",
        "earnings",
        "capital",
        "options",
        "portfolio",
        "trade",
    ):
        assert forbidden_owner in does_not_own
```

Also replace the census comment above the count with:

```python
# 60 -> 61: SNI semantic registration adds the cross-owner
# single-name-intelligence composition/research/product program.
assert len(registry["programs"]) == 61
```

- [ ] **Step 2: Run the focused test and confirm it fails for the missing program**

Run:

```bash
python3 -m pytest tests/test_mastermind_system_map.py::test_single_name_intelligence_program_has_narrow_composition_boundary -q
```

Expected: FAIL with `KeyError: 'single-name-intelligence'`.

- [ ] **Step 3: Add the exact registry entry**

Add this program block under `programs:` in `config/mastermind_programs.yml` without modifying any existing program's ownership:

```yaml
  single-name-intelligence:
    name: Single-Name Intelligence OS
    category: market_intelligence
    kind: intelligence_program
    lifecycle_state: building
    scope: project
    purpose: >
      Compose canonical issuer, company-event, capital, market, options, regional,
      relationship and behavioral owners into correction-safe per-security reference
      twins, then research stock-specific residual, response and calibrated forecast
      behavior without creating parallel truth or trade authority.
    strategic_role: >
      Make a deliberately small set of important securities deeply understandable as
      continuously monitored issuer + instrument organisms before scaling the same
      compiler across broader equity universes.
    owns:
      - Derived single-name reference-twin composition and typed relationship contracts
      - Single-name experience architecture and reference-organism coverage packs
      - SNI-specific normal-versus-abnormal, response-surface and forecast research definitions
      - Projection of SNI forecast history through existing qledger and Evaluation OS owners
    does_not_own:
      - Canonical issuer, security, listing or ticker identity; Data OS remains authoritative
      - Earnings, company-event, filing, fundamental, capital-structure, options, China/HK, market-data, relationship-graph or Stock Identity truth stores
      - Neural Web, qledger, Evaluation OS, Prophet, Terminal signal, Portfolio sizing, execution or trade authority
      - User-facing product proof merely because a reference contract or research artifact exists
    repo_bindings:
      - repo: macro
        role: implementation_owner
      - repo: terminal
        role: renderer
    relationships:
      consumes_from:
        - fundamental-forensics
        - earnings-intelligence
        - capital-structure-intelligence
        - market-timing-intelligence
        - china-system
        - options-intelligence
        - factor-intelligence
        - market-regime-risk
      feeds_context_to:
        - neural-web
        - macro-mastermind-ai
      coordinates_with:
        - terminal-market-data
        - terminal-charting
        - signal-governance
    canonical_docs:
      - repo: macro
        path: docs/superpowers/specs/2026-08-28-single-name-intelligence-os-design.md
      - repo: macro
        path: docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md
      - repo: macro
        path: docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md
    implementation:
      - repo: macro
        roots:
          - research/single_name_intelligence/
    product_surfaces: []
    decision_boundary:
      authority_class: context_only
      summary: >
        SNI may compose and research single-name intelligence; predictive, rank, gate,
        size, portfolio and trade authority must be earned and granted by their existing owners.
```

- [ ] **Step 4: Regenerate the semantic map**

Run:

```bash
python3 scripts/build_mastermind_system_map.py
```

Expected: exit 0 and `docs/MASTERMIND_SYSTEM_MAP.md` changes only as the deterministic projection of the new registry program.

- [ ] **Step 5: Run semantic-map validation**

Run:

```bash
python3 -m pytest tests/test_mastermind_system_map.py -q
```

Expected: all tests PASS, including the census count of 61 and the new SNI boundary test.

- [ ] **Step 6: Commit the semantic registration**

```bash
git add config/mastermind_programs.yml tests/test_mastermind_system_map.py docs/MASTERMIND_SYSTEM_MAP.md
git commit -m "records(sni): register single-name intelligence program"
```

---

### Task 2: Create the durable Agent OS workstream and close the registry gate

**Files:**
- Create: `agentos/workstreams/WS-SINGLE-NAME-INTELLIGENCE-OS.md`
- Modify: `research/single_name_intelligence/SNI1_PROGRAM_REGISTRY_GATE_2026-08-28.md`

**Interfaces:**
- Consumes: `program: single-name-intelligence` from Task 1 and `DEC:SNI-IDENTITY-AUTHORITY-CHAIN` from SNI-1.
- Produces: canonical cross-session SNI workstream identity and an exact SNI-1A next action.

- [ ] **Step 1: Create the workstream with the exact frozen sequence**

Create `agentos/workstreams/WS-SINGLE-NAME-INTELLIGENCE-OS.md` with this frontmatter:

```yaml
---
key: SINGLE-NAME-INTELLIGENCE-OS
title: Single-Name Intelligence OS — issuer and instrument digital twins
objective: >
  Build continuously learning, evidence-grounded reference twins for a deliberately
  small set of important securities before scaling. The first arc is complete only
  when Alibaba/9988/BABA/89988 and Tencent/700/80700 compose real canonical owner
  outputs into one correction-safe product path, with typed absences and zero unearned
  forecast or trade authority.
status: active
program: single-name-intelligence
repos: [macro, terminal]
owner: ceo-sol
class: research
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - contracts/single_name_intelligence/**
  - lib/single_name_intelligence/**
  - engine/single_name_intelligence/**
  - research/single_name_intelligence/**
  - docs/superpowers/specs/2026-08-28-single-name-intelligence-os-design.md
  - docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md
  - docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md
depends_on: []
waves:
  - id: SNI-0
    title: Program architecture and no-rebuild freeze
    status: done
    next_action: Preserve the merged program thesis and architecture boundaries.
  - id: SNI-1
    title: Alibaba/Tencent reference-twin contract and source qualification
    status: done
    depends_on: [SNI-0]
    next_action: Preserve PR #6613 and its binding identity-authority amendment as the implementation source.
  - id: SNI-1A
    title: Pure identity/counter relationship contract
    status: todo
    depends_on: [SNI-1]
    next_action: Execute docs/superpowers/plans/2026-08-28-sni1a-identity-relationship-contract.md as one bounded contract-only PR.
  - id: SNI-1B
    title: Owner/source manifest and ontology registry
    status: todo
    depends_on: [SNI-1A]
  - id: SNI-1C
    title: Pure reference-twin compiler
    status: todo
    depends_on: [SNI-1B]
  - id: SNI-1D
    title: Real owner adapters and reference payloads
    status: todo
    depends_on: [SNI-1C]
  - id: SNI-1E
    title: One bounded premium reference consumer
    status: todo
    depends_on: [SNI-1D]
  - id: SNI-3
    title: Normal-versus-abnormal statistical research
    status: todo
    depends_on: [SNI-1D]
  - id: SNI-4
    title: Hierarchical response-surface lab
    status: todo
    depends_on: [SNI-3]
  - id: SNI-5
    title: Multi-horizon forecast book and Evaluation OS bridge
    status: todo
    depends_on: [SNI-3, SNI-4]
  - id: SNI-6
    title: NVDA/MSFT/TSLA U.S. stress set
    status: todo
    depends_on: [SNI-1E]
  - id: SNI-7
    title: Complete Mag 7 ontology and reference twins
    status: todo
    depends_on: [SNI-6]
  - id: SNI-8
    title: Declarative scale compiler for Nasdaq 100, Dow 30 and S&P 500
    status: todo
    depends_on: [SNI-5, SNI-7]
decisions:
  - DEC:SNI-IDENTITY-AUTHORITY-CHAIN
discoveries:
  - DSC:SNI-HK-MULTI-COUNTER-IS-NOT-MULTI-SECURITY
landmines:
  - "Data OS owns canonical ISS:/SEC:/listing identity; SNI relationship records never mint those namespaces."
  - "Current Data OS HK listing/security admission does not imply canonical HK issuer resolution."
  - "A syntactically derivable Data OS ID is not authority until the stored master admits it."
  - "BABA is a distinct ADS; 9988/89988 are ordinary-share counters; KWEB remains only Tencent group proxy context."
  - "Stock Identity W3+ remains owned by WS:STOCK-IDENTITY; SNI does not rebuild it."
do_not_redo:
  - "Do not turn stock_dossier.py into the deep semantic owner."
  - "Do not create another identity, event, earnings, capital, options, China/HK, graph, quote, qledger, evaluation, queue or lifecycle plane."
  - "Do not use ticker-specific outcome audition to customize a stock."
  - "Do not purchase HKEX data before the separately frozen rights/economics gate."
artifacts:
  - docs/superpowers/specs/2026-08-28-single-name-intelligence-os-design.md
  - docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md
  - docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md
  - research/single_name_intelligence/SNI1_OWNER_SOURCE_MATRIX_2026-08-28.md
  - research/single_name_intelligence/SNI1_ALIBABA_TENCENT_ONTOLOGY_V0_2026-08-28.md
  - research/single_name_intelligence/SNI1_HK_DATA_QUALIFICATION_2026-08-28.md
  - docs/superpowers/plans/2026-08-28-sni1a-identity-relationship-contract.md
next_action: >
  Build SNI-1A only as a pure relationship contract with Alibaba/Tencent fixtures and hostile tests;
  no owner reads, Data OS mutation, reference-twin compiler, product route, forecast or source purchase.
---
```

Add a short body explaining that SNI-1A is the current frontier and that later waves are named sequence, not commissions.

- [ ] **Step 2: Mark the old registry gate as satisfied without deleting its history**

In `research/single_name_intelligence/SNI1_PROGRAM_REGISTRY_GATE_2026-08-28.md`, change the state line to:

```text
**State:** SATISFIED — `single-name-intelligence` registered; see `WS:SINGLE-NAME-INTELLIGENCE-OS`
```

Append a `## Resolution` section stating the accepted program key, registry commit/PR reference, and that no authority or runtime was created by registration.

- [ ] **Step 3: Run Agent OS validation**

Run:

```bash
python3 scripts/agentos.py validate
```

Expected: exit 0; no unknown `program: single-name-intelligence`, no dangling `DEC:`/`DSC:` reference, no malformed wave dependency.

- [ ] **Step 4: Run the semantic and Agent OS focused suite together**

Run:

```bash
python3 -m pytest tests/test_mastermind_system_map.py tests/test_agentos.py -q
```

If `tests/test_agentos.py` is not the repository's current Agent OS test filename, use the existing Agent OS test module(s) returned by `git ls-files 'tests/test_agentos*.py'`; do not create a duplicate test harness.

Expected: all selected tests PASS.

- [ ] **Step 5: Commit the workstream/gate closure**

```bash
git add agentos/workstreams/WS-SINGLE-NAME-INTELLIGENCE-OS.md research/single_name_intelligence/SNI1_PROGRAM_REGISTRY_GATE_2026-08-28.md
git commit -m "records(sni): establish durable single-name workstream"
```

---

## Plan self-review

- The plan modifies the existing semantic registry rather than introducing another program map.
- The new program does not absorb Data OS, Earnings, Capital Structure, Stock Identity, China/HK, Options, graph, quote, qledger/Evaluation OS, Prophet or Portfolio ownership.
- Product surfaces remain empty until a real consumer exists.
- The workstream cannot validate until the program key exists, preserving the intended gate ordering.
- SNI-1A remains a separate code PR and is not bundled into this records-only registration carrier.
- No placeholder implementation requirement remains in this plan.

## Completion evidence

This registration carrier is complete only when the exact PR head has:

```bash
python3 -m pytest tests/test_mastermind_system_map.py -q
python3 scripts/agentos.py validate
```

both exiting 0, hosted CI green on that exact head, and `config/mastermind_programs.yml`, generated `docs/MASTERMIND_SYSTEM_MAP.md`, and `WS:SINGLE-NAME-INTELLIGENCE-OS` all agree on the same program key and authority boundary.

# SNI-1A — Terra Gated Implementation Handoff

**Packet state:** PRECOMMISSION / GATED — this file is a complete operator packet but is **not** a receiver assignment merely by existing in GitHub.  
**Operation key:** `SNI-1A-IDENTITY-RELATIONSHIP-V1`  
**Preferred avenue:** `Terra`  
**Receiver mode when Chairman assigns a concrete session:** `DIRECT_TARGETED`  
**Receiver binding mode:** `CAPACITY_SELECTABLE`  
**Account binding:** `CHAIRMAN_SELECTS`  
**Repository:** `mastermindx-market-intelligence/macro`  
**Expected execution plan:** `docs/superpowers/plans/2026-08-28-sni1a-identity-relationship-contract.md`  

---

## Routing receipt

```text
PREFERRED_AVENUE: Terra
WHY: SNI-1A is a well-specified, single-repository, contract-heavy implementation with frozen architecture, exact schemas, hostile cases and adjacent regression suites. Terra can reliably implement and independently reason about the bounded identity/evidence semantics.
ACCOUNT_BINDING: CHAIRMAN_SELECTS
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
WHY NOT FABLE: Principal continuity and unresolved system architecture are no longer required. Sol has frozen Data OS authority, SNI relationship ownership, schemas, methods, tests and stop conditions. Any new authority/architecture fork returns to Sol rather than being decided inside the worker PR.
```

This packet recommends capability only. It does not choose a numbered account/session. The Chairman selects the concrete current Terra-capable receiver.

---

## Delivery / pickup / START contract

When the Chairman deliberately delivers this packet to one concrete eligible session, that live delivery is the receiver assignment for the operation.

The receiving session must treat the delivery as:

```text
RECEIVER_MODE: DIRECT_TARGETED
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
THIS DELIVERY IS YOUR RECEIVER ASSIGNMENT FOR SNI-1A-IDENTITY-RELATIONSHIP-V1.
Do not wait for a second Chairman/Slack assignment and do not ask the Chairman to claim it again.
```

Immediately reply on the same lawful carrier:

```text
PICKUP_ACK SNI-1A-IDENTITY-RELATIONSHIP-V1
receiver=<actual current session/account identity>
```

Pickup ACK proves context pickup only. It is **not** START and is not permission to work through a held dependency.

Before ending the pickup turn:

1. read the complete current handoff plus every authority source named below;
2. reconcile the exact current Macro `main`, parent/plan PRs and adjacent identity owners;
3. arm the exact-carrier continuation watcher/wait path using the currently accepted watcher law and emit a truthful `WATCH_ARMED` receipt, or return a concrete `WATCH_UNAVAILABLE` only after the required tool-first create/arm attempt fails;
4. evaluate every START gate below.

If all gates are clear, emit separately:

```text
START SNI-1A-IDENTITY-RELATIONSHIP-V1
```

and begin execution. If any gate is held, return `BLOCKED` with the exact gate, keep the continuation path armed, do no modifying implementation, and emit `START` only after the gate is actually cleared.

Before START, the Chairman may perform a lawful `PRESTART_REBIND` to another eligible Terra-capable session using the same operation key and carrier if no modifying effect, START, conflicting pickup or `EFFECT_UNKNOWN` exists. After START, the concrete runtime is sticky unless canonically reconciled.

---

# 1. Observable mission

Implement and prove one **pure Single-Name Intelligence identity-relationship contract** that can represent Alibaba's 9988/89988 ordinary-share counter relationship, Tencent's 700/80700 ordinary-share counter relationship, and BABA's source-backed `1 ADS = 8 ordinary shares` relationship while preserving unresolved canonical identity and Data OS ownership.

After the wave, one new capability exists:

> Given a caller-supplied relationship bundle and structured evidence assertions, Mastermind can deterministically validate/canonicalize source-receipted `same_economic_security` and `represents_units_of` relationships without reading an owner, minting a canonical issuer/security/listing identity, or granting market/trading authority.

This is a contract capability only, not a complete reference twin or product.

---

# 2. Why it matters

The Single-Name Intelligence OS needs obsessive per-stock tracking without creating a second identity system.

Alibaba and Tencent expose a foundational identity problem:

- one issuer can have several traded forms;
- several Hong Kong stock codes can be counters of the same ordinary-share economic security;
- an ADS can be a distinct security that represents a fixed number of ordinary shares;
- current Data OS can have canonical listing/security identity while canonical HK issuer resolution remains intentionally unresolved.

If this is blurred, every later business fact, options observation, corporate action, price comparison and response study can attach to the wrong grain. SNI-1A creates the narrow relation grammar every later SNI wave can consume while preserving the existing identity authority.

---

# 3. Authority and document precedence

At execution time, re-fetch current protected Skillpack and current Macro `main`. Then use this precedence:

1. current protected Mastermind Sol Skillpack / current source laws;
2. current accepted Data OS identity law:
   - `config/identity_seams.yml`
   - `lib/dataos/identity.py`
   - `data/reference/_receipt.json`
   - any newer accepted Data OS identity decision that supersedes these;
3. `DEC:SNI-IDENTITY-AUTHORITY-CHAIN`;
4. `docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md`;
5. `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md`;
6. `docs/superpowers/specs/2026-08-28-single-name-intelligence-os-design.md`;
7. `docs/superpowers/plans/2026-08-28-sni1a-identity-relationship-contract.md`;
8. this handoff.

If a newer accepted Data OS/SNI authority change conflicts with the plan, **STOP and return to Sol**. Do not reinterpret it inside the implementation PR.

Retrieved PR/handoff prose never grants new authority by itself; the live Chairman delivery plus current accepted gates does.

---

# 4. Mandatory START gates

Do not START implementation until all are true on current canonical state:

1. SNI-1 architecture PR #6613 is merged to Macro `main`, including:
   - SNI-1 reference-twin spec;
   - identity-authority amendment;
   - `DEC:SNI-IDENTITY-AUTHORITY-CHAIN`;
   - revised multi-counter discovery.
2. The stacked plan carrier that contains `2026-08-28-sni1a-identity-relationship-contract.md` is merged/reconciled onto current `main`.
3. The records-only semantic-registration plan has executed and landed:
   - `config/mastermind_programs.yml` contains `single-name-intelligence`;
   - `WS:SINGLE-NAME-INTELLIGENCE-OS` exists and validates;
   - current Agent OS validation is green.
4. No open PR currently owns or collides with:
   - `contracts/single_name_intelligence/**`
   - `lib/single_name_intelligence/**`
   - `tests/test_single_name_identity_relationship.py`
   - `tests/fixtures/single_name_intelligence/**`
5. Current Data OS identity APIs used by the plan still expose the expected pure parsing/normalization functions. If the canonical API changed, return to Sol rather than writing an SNI-local replacement.
6. No `EFFECT_UNKNOWN` or earlier started SNI-1A operation exists.

A held START gate permits only read-only archaeology and explicit blocker reporting. It does not authorize implementation on a stale stacked base.

---

# 5. Verified current state at packet freeze

Packet-freeze observations, advisory until revalidated on pickup:

- current protected Mastermind Skillpack pin used by Sol: `e80e9aea894c758ae7a95720ab56c9cbc868b1ba`, Skillpack v1.0.1 / bootstrap-major 1 compatible;
- Macro `main` observed at `ed202fbcadce2ca9d0ed85abb3b1178318825653`;
- SNI-1 parent PR #6613 current amended head: `a1c85003fe69a7ae80e57f77ced9f80c5e9c1c3a`, draft/unmerged at packet freeze;
- SNI-1A plan branch: `sol/sni1a-plan-20260828`, stacked on #6613;
- current Data OS `data/reference/_receipt.json` reports HK target listing/security resolution `147/147` but the accepted D2B2 contract deliberately introduced no CN/HK issuer-evidence class;
- `company_identity.v1` remains useful PIT owner-native identity/event attribution but is not the estate-wide Data OS identity master;
- Stock Identity W3+ is a separate active workstream and must not enter this wave;
- no SNI-1A implementation files exist in the frozen plan branch.

Revalidate every bullet before START.

---

# 6. Exact scope

Repository: Macro only.

Expected changed files are exactly the SNI-1A plan allow-list unless a tiny test-support change is proven necessary and Sol accepts the scope widening:

```text
contracts/single_name_intelligence/README.md
contracts/single_name_intelligence/identity_relationship.v1.schema.json
lib/single_name_intelligence/__init__.py
lib/single_name_intelligence/identity_relationship.py
tests/test_single_name_identity_relationship.py
tests/fixtures/single_name_intelligence/alibaba_identity_relationship_valid.json
tests/fixtures/single_name_intelligence/tencent_identity_relationship_valid.json
```

Do not modify:

```text
lib/dataos/**
scripts/build_security_master.py
data/reference/**
engine/company_intelligence/**
engine/stock_identity/**
engine/hk_adr_bridge.py
engine/hk_southbound_stocks.py
engine/options*/**
config/identity_seams.yml
config/mastermind_programs.yml
agentos/workstreams/**
Terminal repository
```

If an expected test or API cannot be satisfied without touching one of those protected paths, return `DECISION_REQUEST` to Sol.

---

# 7. Explicit non-goals

SNI-1A must not:

- create a canonical issuer/security/listing ID;
- modify Data OS identity or the security/issuer master;
- build a general ListingAlias↔DataOS namespace renderer;
- read any production owner or market-data artifact at runtime;
- scrape Alibaba/Tencent/HKEX sources;
- build SNI owner/source manifests;
- build the full reference-twin compiler;
- add FX or price conversion;
- calculate cross-listing basis;
- build options, market, capital, earnings or company adapters;
- build Terminal/Macro UI;
- register forecasts or qledger claims;
- customize indicators or models per ticker;
- rank, gate, size, signal, escalate, allocate or trade;
- purchase or integrate HKEX data;
- absorb SNI-1B or any later wave.

---

# 8. Complete machine journey

Input:

```text
caller-supplied issuer subject
+ source-observed counter descriptors
+ optional owner-receipted canonical Data OS IDs
+ structured relationship evidence assertions
+ relationship clocks
```

Processing:

```text
schema validation
→ canonical sort
→ relationship ID normalization
→ bundle ID normalization
→ Data OS receipt/internal identity consistency checks
→ exact evidence-member/unit binding
→ clock checks
→ all-false authority check
```

Output:

```text
canonical validated mastermind.single_name.identity_relationship_bundle/v1
```

Degraded/failure journey:

- no canonical Data OS ID: valid unresolved state if fields/receipt stay null;
- valid-looking canonical ID without receipt: reject;
- security/listing IDs disagree: reject;
- canonical ID disagrees with observed country/MIC/code: reject;
- evidence references wrong counters: reject;
- BABA unit relation differs from structured evidence: reject;
- target relation absent: reject;
- evidence observed after relationship known-at: reject;
- attempted non-false authority: reject;
- ambiguous schema/identity: reject rather than guess.

---

# 9. Contract, identity, time, null and correction behavior

## Identity

- Data OS is canonical for admitted `ISS:` / `SEC:` / listing identity.
- SNI IDs are only `snir_<sha256>` relationship IDs and `snib_<sha256>` bundle IDs.
- A relationship record never becomes a canonical security identity.
- External CIK/name evidence cannot self-promote to a Data OS issuer ID.
- Canonical IDs require caller-supplied Data OS master receipts.
- Canonical resolved member must agree with its observed counter descriptor.

## Time

Every relationship has `known_at` and an explicit effective-state tuple.
Every evidence ref has `observed_at` and optional `published_at`.
Relationship `known_at` cannot predate referenced evidence observation.

No later knowledge is backdated into the relationship.

## Nulls

Null canonical issuer/listing/security is a valid explicit unresolved state.
Missing is never zero and never replaced by a derived ticker string.
Resolved state with null canonical identity is invalid.
Unresolved state with populated canonical identity/receipt is invalid.

## Corrections

SNI-1A persists nothing. It validates the record's `correction_state` only. Append/supersede persistence belongs to later SNI composition. Do not create a relationship database in this wave.

---

# 10. Method class

Everything in SNI-1A is **deterministic**.

Allowed:

- JSON Schema validation;
- pure parsing/normalization;
- canonical JSON hashing;
- set/tuple equality;
- typed receipt/clock checks.

Statistical methods: none.
Model/LLM methods: none.

Any proposal to use a model to infer counter equivalence, issuer identity, ratio or source meaning is outside this wave and returns to Sol.

---

# 11. Failure reason families

Preserve the plan's stable reason prefixes:

```text
SNI1A_R001_SCHEMA
SNI1A_R002_RELATIONSHIP_ID
SNI1A_R003_BUNDLE_ID
SNI1A_R004_AUTHORITY
SNI1A_R005_UNRESOLVED_HAS_CANONICAL_ID
SNI1A_R006_CANONICAL_MEMBER_MISMATCH
SNI1A_R007_RESOLVED_WITHOUT_DATAOS_RECEIPT
SNI1A_R008_SAME_SECURITY_MEMBER_INVALID
SNI1A_R009_UNIT_ASSERTION_MISMATCH
SNI1A_R010_EVIDENCE_CLOCK_INVALID
SNI1A_R011_TARGET_RELATION_INVALID
SNI1A_R012_EVIDENCE_MEMBER_MISMATCH
SNI1A_R013_EVIDENCE_SOURCE_COUNTER_MISMATCH
```

Do not proliferate reason codes casually. If a genuinely distinct semantic failure appears, return to Sol before widening the public failure vocabulary.

---

# 12. Ordered implementation sequence

Follow the committed plan exactly:

1. freeze JSON Schema + positive Alibaba/Tencent fixtures and prove red→green;
2. implement normalization, deterministic relation/bundle IDs and base validation;
3. canonicalize golden fixture IDs;
4. enforce Data OS receipt and observed-member consistency;
5. enforce exact source assertion members/units and clocks;
6. enforce no-owner/runtime-I/O boundary;
7. document public contract boundary;
8. run focused + adjacent Data OS regressions;
9. run Agent OS validation;
10. hosted CI on exact PR head;
11. return to Sol for adversarial acceptance — do not self-merge unless a separately current authority explicitly grants it.

No SNI-1B prework is needed in this carrier.

---

# 13. Acceptance tests

At minimum the exact head must prove:

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
python3 -m pytest tests/test_dataos_identity.py tests/test_dataos_security_master.py tests/test_identity_seam_agreement.py -q
python3 -m compileall -q lib/single_name_intelligence
python3 scripts/agentos.py validate
```

Required discriminating cases:

- Alibaba 9988/89988 exact same-security evidence membership passes;
- Tencent 700/80700 exact same-security evidence membership passes;
- BABA 1:8 source relation passes;
- wrong BABA ratio while evidence remains 1:8 fails;
- synthetic non-BABA 1:2 relation passes when evidence also says 1:2;
- unresolved canonical IDs pass only when null/no receipt;
- resolved IDs fail without Data OS receipt;
- Data OS security/listing pair mismatch fails;
- Data OS ID versus observed member mismatch fails;
- same-security evidence with wrong member set fails;
- conversion evidence with wrong source counter fails;
- target relation missing/wrong type fails;
- post-known-at evidence fails;
- authority flip fails;
- static guard proves no owner/network/store I/O dependency.

Hosted CI must be green on the exact head. Local tests do not substitute for hosted repository acceptance.

---

# 14. Production proof / capability state

There is intentionally **no production/browser proof owed in SNI-1A**, because the wave creates no runtime consumer or product route.

Successful merge state is:

```text
BUILT_NOT_PROVEN / CONTRACT-FROZEN
```

Do not call it `PROVEN_LIVE`.

The first real-owner path arrives in later SNI waves and will require production proof.

---

# 15. Stop condition

Stop the instant all SNI-1A contract files are exact-head green and the PR is ready for Sol acceptance.

Do **not**:

- start SNI-1B;
- read current Alibaba/Tencent owner payloads;
- build adapters;
- implement full reference twin;
- create UI;
- write statistical research;
- alter Data OS.

Any authority collision, need for Data OS modification, new relationship type, new owner I/O, or price/FX requirement is a `DECISION_REQUEST` to Sol.

---

# 16. Required continuation handoff

Return on the same carrier with:

```text
RESULT SNI-1A-IDENTITY-RELATIONSHIP-V1
receiver=<actual receiver>
branch=<branch>
head_sha=<exact sha>
pr=<number>
changed_files=<exact list>
focused_tests=<command + result>
dataos_regression_tests=<command + result>
agentos_validate=<result>
hosted_ci=<exact-head status>
capability_state=BUILT_NOT_PROVEN/CONTRACT-FROZEN
new_reason_codes=<none or exact list>
new_architecture_collision=<none or exact issue>
remaining_gates=<exact list>
recommended_next_action=<one sentence>
```

If blocked:

```text
BLOCKED SNI-1A-IDENTITY-RELATIONSHIP-V1
held_gate=<exact gate>
evidence=<current source/sha/error>
modifying_effect=false|true|unknown
```

If a new architecture/authority question is discovered:

```text
DECISION_REQUEST SNI-1A-IDENTITY-RELATIONSHIP-V1
question=<one precise fork>
why_plan_cannot_safely_decide=<evidence>
```

After any nonterminal return, re-arm the exact-carrier continuation watcher/wait path. After Sol sends terminal `SOL ACCEPTED / STOP`, stop the child wave and disarm the temporary watcher. No next wave is authorized by this packet.

---

# 17. Watcher receipt

When the worker actually arms its continuation path, report truthfully:

```text
WATCH_ARMED SNI-1A-IDENTITY-RELATIONSHIP-V1
mechanism=<turn_watch_v1|live_exact_waiter|native_condition_watch>
watch_id=<id or n/a>
carrier=<exact carrier/thread>
baseline=<last consumed message key/timestamp>
cadence=<actual cadence or live-wait behavior>
trigger=<first qualifying Sol reply after baseline>
after_match=<pause/rearm semantics>
terminal=<disarm on terminal STOP>
```

Do not claim `WATCH_ARMED` before the arm/create action succeeds. A Slack connector lacking push subscriptions does not by itself establish unavailability; follow the current tool-first watcher law.

---

# 18. Final routing law

This mission remains **Terra** unless current implementation evidence proves Terra is insufficient.

Do not escalate to Fable because the program is strategically important. If implementation uncovers a genuine principal-level architecture/authority conflict, stop SNI-1A and return to Sol; Sol decides whether the conflict needs CTO Sol, Opus, Fable, or a new architecture wave.

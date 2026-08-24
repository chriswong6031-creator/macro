# Market OS B1A Commission — `security_state.v1` Golden AAPL Product Vertical
## Prepared implementation handoff — gated, not yet authorized

**Date:** 2026-08-23  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@db0bac5fe3f72348262d42c8bd26b836bda9f61d`  
**Macro archaeology pin:** `mastermindx-market-intelligence/macro@fb2375441f21b94201edc4ed6ac2c40f67274cde`  
**Terminal archaeology pin:** `mastermindx-market-intelligence/mastermind-terminal@449439c690e93ba968185499af4041c2f512b659`  
**Canonical product workstream:** `WS:MARKET-OS`  
**Wave:** `B1 — Canonical Security State`, bounded subwave `B1A`  
**Preferred operator:** Fable principal builder, with one bounded Macro builder and independent product reviewer  
**State:** `PREPARED_NOT_AUTHORIZED`

---

# 1. Dispatch gates

Do not start implementation until all four are true:

1. Market OS A1A production acceptance is canonical on `main`—PR #6310 or a later superseding record has landed.
2. Alpha Intelligence K1 Evidence Foundation has been accepted by Sol.
3. A fresh Macro/Terminal open-PR, worktree, path-ownership, and production-state census is clean.
4. The canonical AAPL event workspace used by Earnings E2 remains available, identity-consistent, and suitable as the golden producer.

If any gate fails, return a typed blocker. Do not choose another architecture or issuer silently.

---

# 2. Observable mission

Ship the first real Market Intelligence product vertical:

> A user opens the existing AAPL dossier and receives one coherent, source-grounded Security State answering State, Change, Opportunity Context, Risk, Catalyst, and Personal Impact—with typed freshness, evidence, failed gates, strongest unresolved fact, and next observables.

The flow is:

```text
canonical AAPL identity
+ current market state
+ live AAPL event_workspace.v1
+ existing owner-native Prophet context
+ existing timing/availability context or typed unavailable
+ existing risk/catalyst/falsifier fields
+ accepted K1 evidence recipe
        ↓
security_state.v1
        ↓
existing public AAPL dossier Decision Spine
```

This is product implementation.

It is not another research packet.

---

# 3. Why this matters

Mastermind already has many strong organs:

- current market/security data;
- a proven AAPL Earnings Event Workspace;
- Prophet context;
- entry/timing systems;
- deterministic dossier fields;
- evidence and source receipts;
- Portfolio and Watchlist state.

The user still has to reconcile them manually.

B1A creates the first coherent product answer.

The independently useful capability is:

> A real security page explains what changed, what the current opportunity context is, which gates failed, what comes next, and exactly which canonical evidence supports the read.

---

# 4. Authority and document precedence

1. Current protected Skillpack.
2. Current Macro `main`.
3. `WS:MARKET-OS`.
4. Market OS architecture freeze and Decision Spine.
5. Accepted K1 Evidence Foundation.
6. Current Earnings E0–E2 contracts and live AAPL `event_workspace.v1`.
7. Current issuer/security identity authority.
8. Current Prophet / Conditional Fusion / Entry Availability / Radar owner contracts.
9. Current stockdata and dossier integrity contracts.
10. Authenticated Market Ontology acceptance laws.
11. This commission.

No retrieved page, worker prompt, or model output grants authority.

---

# 5. Verified current owner map

## Product owner

`WS:MARKET-OS` owns the Market/Security/My Market flagship experience.

## Security state publication

The architecture freeze prefers an additive `security_state` block inside the existing per-security stockdata plane and a compact existing-index projection.

Do not create a second per-ticker publication estate.

## Golden event producer

Earnings E2 has a live AAPL FY2026 Q3 `event_workspace.v1` consumed by Terminal and the public dossier.

B1A reads it through its owner.

Do not duplicate the event or rewrite its clocks.

## Existing dossier seed

`engine/stock_dossier.py` is a display-tier composition seed over already-computed fields.

It is not a universal OpportunityCase and cannot mint new values.

## Prophet/timing

Read only from current owner outputs.

Do not touch:

- Prophet ranking;
- Conditional Fusion;
- Candidate lifecycle;
- Entry Availability;
- Live Entry Radar;
- Prophet Lab;
- their ledgers or publication paths.

## Portfolio/personal state

The public dossier has no user Portfolio context.

B1A must render:

```text
personal_impact.state = NO_USER_CONTEXT
```

unless an existing privacy-safe user overlay already exists at request time.

Do not create or persist a user overlay in this wave.

---

# 6. Exact scope

## In scope

### Producer contract

Freeze and implement `security_state.v1` as a pure, deterministic compiler over owner reads.

### Golden AAPL compilation

Compile one real AAPL Security State using:

- canonical issuer and security identity;
- current quote/price state and freshness;
- current AAPL Earnings Event Workspace;
- accepted K1 evidence references/blocks;
- current available Prophet context;
- current deterministic entry/timing context or typed unavailable;
- existing risk, catalyst, falsifier, and freshness fields;
- optional future `opportunity_case_ref = null/unavailable`.

### Existing publication

Publish the additive Security State through the existing stockdata/dossier path.

### Existing public consumer

Render a compact Decision Spine on the existing public AAPL dossier.

### Evidence drilldown

Allow the user to inspect:

- owner;
- owner object ID/version;
- source;
- published/available/observed clocks;
- supported claim;
- freshness/coverage;
- correction/conflict state.

### Failure-state suite

Implement the required typed states and user copy.

### Production proof

Prove the real AAPL flow in production and capture browser evidence.

## Explicit non-goals

- no OpportunityCase kernel/store;
- no Evidence Mesh store;
- no new source/event/security identity;
- no new rank, score, recommendation, size, gate, or probability;
- no Prophet/Radar/Availability edits;
- no financial statements or valuation;
- no event-to-portfolio math;
- no Thesis/RMS;
- no Workbench/analogs;
- no LLM factual fields;
- no broad security-universe migration;
- no Terminal/Desk implementation in B1A;
- no second issuer;
- no Market discovery board;
- no external API.

---

# 7. Complete user journey

## Entry

The user opens AAPL from an existing Market, Prophet, Watchlist, or direct security route.

## First ten seconds

The page shows:

```text
AAPL
current price and market timestamp
dominant freshness/degradation state
owned/watched state if already available
Prophet context
Entry Availability or explicit unavailable state
```

## One-minute Decision Spine

### STATE

What the security is doing now, using existing deterministic state.

### CHANGE

What newly happened, anchored to the AAPL Earnings Event Workspace and exact source clock.

### OPPORTUNITY CONTEXT

The currently lawful favorable context:

- Prophet reference;
- market-incorporation/dislocation only if owner output exists;
- entry/timing state;
- no composite score.

### RISK

- existing deterministic risk/falsifier references;
- failed gates;
- strongest unresolved fact;
- missing/partial legs.

### CATALYST

- next observables;
- deadlines/windows;
- source or owner references.

### PERSONAL IMPACT

- owned/watched state if available under existing law;
- otherwise `NO_USER_CONTEXT`;
- no public holdings.

## Drilldown

The user opens evidence details without leaving the Security context.

## Return

A later source correction or refreshed event changes the state explicitly rather than silently rewriting the prior conclusion.

---

# 8. `security_state.v1` contract

Recommended contract:

```yaml
schema: security_state.v1
security_id:
issuer_id:
listing_id:
generated_at:
content_sha256:

as_of:
  market_at:
  source_frontier_at:
  state_compiled_at:

authority:
  class: context_only
  display_only: true
  can_rank: false
  can_gate: false
  can_size: false
  can_originate_signal: false
  can_execute: false

coverage:
  overall_state:
  required_legs_total:
  required_legs_available:
  optional_legs_total:
  optional_legs_available:
  missing_legs:
  stale_legs:
  rights_blocked_legs:
  conflicted_legs:

state:
  deterministic_state_refs:
  summary:
  coverage_state:

change:
  economic_episode_ref:
  event_refs:
  source_available_at:
  summary:
  correction_state:
  coverage_state:

opportunity_context:
  prophet_ref:
  opportunity_case_ref:
  market_incorporation_ref:
  dislocation_ref:
  entry_availability_ref:
  state:
  reason:
  coverage_state:

risk:
  risk_refs:
  failed_gates:
  strongest_unresolved_fact:
  coverage_state:

catalyst:
  next_observables:
  deadlines:
  coverage_state:

personal_impact:
  state:
  user_exposure_overlay_ref:

evidence:
  evidence_block_refs:
  conflicts:
  coverage_state:
```

The final field names are owned by the builder's current-state reconciliation, but the semantic separation is binding.

---

# 9. Data, time, null, and correction behavior

## Identity

Use current issuer/security/listing authority.

Do not use ticker alone as durable identity.

## Clocks

Preserve:

- market timestamp;
- source available time;
- owner observation/build time;
- Security State compilation time.

Never relabel the Earnings `source_available_at` clock.

## Nulls

Every leg has one of:

```text
AVAILABLE
NOT_COVERED
NOT_APPLICABLE
UNAVAILABLE
STALE
RIGHTS_BLOCKED
CONFLICTED
CORRECTED
PARTIAL
```

No `null` silently means neutral.

## Dominant degradation

If a required leg is materially unavailable or stale, the affected section and overall header inherit a degraded/partial state.

## Corrections

A corrected source/event produces:

- a new Security State version;
- explicit correction state;
- changed evidence references;
- preserved old state for replay where current owner/publication law permits;
- no silent overwrite claim.

## Aggregate denominator receipt

The Security State publishes a leg-coverage receipt.

If future personal/portfolio context is present, it also prints the portfolio denominator receipt under its owner law.

---

# 10. Deterministic, statistical, and model-generated method

## Deterministic compiler

- owner reads;
- identity;
- field selection;
- freshness/degradation;
- failed-gate enumeration;
- evidence mapping;
- next-observable mapping;
- output hash/version.

## Owner-native model/context

Prophet or another owner-native statistical/model result remains labeled by owner, method class, version, and authority.

B1A does not recalculate it.

## LLM

Not required.

If summary copy already comes from an owner-native model, it remains cited and marked model-generated.

No LLM may originate facts, rank, gate, probability, recommendation, or strongest unresolved fact.

`strongest_unresolved_fact` must be selected deterministically from a frozen typed priority rule or remain unavailable.

---

# 11. Authenticated-MO integrity laws

## Aggregate denominator

Print available/missing/stale/conflicted required legs.

## Dominant degradation

Partial context cannot look complete.

## Durable execution receipt

If any upstream compile/refresh fails, the current Security State shows failure/stale/last-good explicitly.

A failed refresh cannot leave a calm current state.

## Write/read-model reconciliation

B1A is read-only, but publication acceptance requires:

- direct generated object;
- existing stockdata/dossier enumeration;
- matching version/hash;
- real consumer render.

## Confidence/probability

B1A emits no new confidence/probability.

Owner-native values require owner receipts.

## Output-specific prerequisites

A missing Prophet leg does not erase a valid Event Change leg.

Each affected section fails/degrades independently.

---

# 12. Failure states and reference cases

Required cases:

1. **Golden current AAPL event**
2. **No current event**
3. **Source event stale**
4. **Source event corrected**
5. **Prophet unavailable**
6. **Entry availability unavailable**
7. **GMI/dislocation not covered**
8. **Conflicting event/source observations**
9. **Rights-blocked evidence**
10. **Price unavailable/stale**
11. **No user context**
12. **Compiler failure with last-good state**
13. **First compile failure with no last-good**
14. **Owner schema/version unsupported**

Every case needs deterministic fixture coverage.

At least the golden, stale, missing, corrected, and no-user-context states need browser reference proof.

---

# 13. Ordered implementation sequence

## Step 0 — pickup and collision census

- re-pin current Macro and Terminal;
- inspect #6310 disposition;
- inspect all open PRs/worktrees/owned paths;
- confirm K1 accepted;
- confirm AAPL owner object and current route.

Stop on collision.

## Step 1 — contract and pure compiler

Implement the smallest pure Security State compiler and schema/contract.

Use owner-reader fixtures.

No page changes yet unless producer+consumer remain reviewable in one PR.

## Step 2 — real producer

Wire one AAPL real owner-read path into the existing stockdata/publication pipeline.

No universe migration.

## Step 3 — public dossier consumer

Add the Decision Spine to the existing AAPL/public dossier composition.

Use current design system and responsive patterns.

## Step 4 — failure/correction hardening

Run fixture mutations and real read/freshness cases.

## Step 5 — production proof

Deploy through the real path.

Capture:

- exact deployed commit;
- real AAPL object;
- public page;
- evidence drilldown;
- responsive views;
- stale/degraded test where safely reproducible.

## Step 6 — durable handoff

Update Market OS records and stop.

---

# 14. PR decomposition

Preferred one-wave sequence:

```text
B1A-1  security_state.v1 contract + pure compiler + fixtures
B1A-2  AAPL real owner adapter + existing stockdata publication
B1A-3  public dossier Decision Spine + production browser proof
```

The operator may combine B1A-1 and B1A-2 if the change remains one independently reviewable capability and includes a real consumer in the same accepted wave.

Do not leave a long-lived infrastructure-only compiler with no product consumer.

Each PR must preserve the exact continuation handoff and stop before another issuer or Terminal.

---

# 15. Acceptance tests

## Contract

- schema/version pinned;
- authority all false;
- identity not ticker-only;
- owner refs unchanged;
- K1 evidence contract used;
- object hash excludes wall-clock-only identity noise.

## Field semantics

- no current-context label becomes probability;
- no missing leg becomes zero;
- no owner-native model result becomes fact;
- strongest unresolved fact is deterministic or unavailable;
- failed gates are explicit codes.

## Correction/freshness

- stale source creates stale/degraded state;
- corrected source changes version/ref;
- last-good and first-failure are distinguished;
- generated-at cannot mint source freshness.

## No-rebuild

Mutation tests kill:

- copied event payload store;
- second per-ticker file;
- ticker-only identity;
- dossier-side arithmetic;
- derived rank/score;
- private user data in public output;
- Prophet/Radar write;
- null-to-neutral conversion;
- failure-to-current fallback.

## User experience

At 1440px, ~820px, and ~390px:

- first viewport is legible;
- Decision Spine hierarchy remains clear;
- evidence drawer is usable;
- no horizontal overflow;
- failure states remain visible;
- chart/security context remains primary.

## Production

- real producer → real public consumer;
- page/object commit matches deployed release;
- browser proof;
- no private data in artifacts/logs/analytics;
- no duplicate canonical store;
- one issuer only.

---

# 16. Stop condition

Stop after AAPL B1A is production-proven and returned to Sol.

Do not:

- begin B1B/Terminal;
- add another issuer;
- begin B2 cockpit;
- implement OpportunityCase;
- implement valuation/portfolio/thesis;
- widen K1;
- change Prophet, Radar, or Earnings owners;
- call B1 complete beyond the accepted AAPL slice.

---

# 17. Required continuation handoff

Return:

```text
exact pickup/deployed pins
open-PR/path collision receipt
contract/schema
changed files
owner reads
AAPL object and hash
Decision Spine screenshots
evidence/clock receipts
failure-state matrix
mutation proofs
production URL/commit proof
capability state
unresolved gaps
recommended B1B/B2 next action
```

The next action after Sol acceptance is a separate commission for B1B—Terminal/Desk projection over the frozen `security_state.v1`.

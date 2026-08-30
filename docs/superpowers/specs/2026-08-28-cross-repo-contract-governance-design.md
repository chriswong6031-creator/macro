# Cross-Repository Contract Governance Design

**Date:** 2026-08-28  
**Authority:** Chairman-approved Sol architecture freeze  
**Program:** `cross-repo-contract-governance`  
**Target Agent OS home:** `WS:CROSS-REPO-CONTRACT-GOVERNANCE`  
**R0 operation key:** `crg-r0-governance-home-20260828-sol-001`

## 1. Outcome

Mastermind-X must make every material seam among Macro, Mastermind Terminal, and Mastermind Portfolio explicit, versioned, testable, correction-safe, and attributable to its canonical owner without introducing a new runtime, traffic proxy, release gate, queue, identity plane, lifecycle, or control plane.

The user/company outcome is not "more governance documentation." It is that a product or machine consumer can cross a repository boundary without hidden assumptions about schema, freshness, nulls, corrections, privacy, authority, or fallback behavior, and that a fresh Sol/Fable session can determine whether that crossing is actually production-proven.

Completion requires all major cross-repository flows to be formally contracted, production-proven through their existing transport and actual consumer, and reflected in Agent OS plus the semantic system map.

## 2. Current procedural and repository pins

The modifying R0 carrier is grounded against:

- protected Skillpack: `mastermindx-market-intelligence/Mastermind@97f85ce5b84030faf4d291f988a1c642fb15e80a`;
- Skillpack schema/version: `mastermind.sol_skillpack.v1`, `1.0.0`, bootstrap major `1`;
- Macro `main`: `24ccea3fe482ab97c415db387f272b34c4852ed3` at R0 branch creation;
- Terminal `master`: `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`;
- Portfolio `master`: `97f85ce5b84030faf4d291f988a1c642fb15e80a`.

Every modifying child must re-pin current heads and current protected Skillpack before write. These pins are architectural pickup evidence, not permanent runtime identity.

## 3. Canonical ownership

The existing semantic registry remains the parent and is not replaced:

- Macro owns the global semantic home, upstream market/macro intelligence, Neural Web/Prophet publication, canonical billing/entitlement, and producer-side evidence contracts.
- Terminal owns workstation composition, interactive chart/user state, local BFF validation, Terminal-owned ingest/records/alerts, and any explicitly Terminal-owned deterministic admission consequence.
- Portfolio owns paper-book state, portfolio decisions, deterministic sizing/constraints/settlement, learning, and bounded publication back to Macro.
- Executive OS owns live Job/Attempt/Worker/Event lifecycle and CEO-intent admission.
- Agent OS owns durable workstreams, decisions, discoveries, and handoffs only.
- GitHub owns implementation/evidence truth.
- Linear is selective portfolio projection.
- Slack is transport/hot-state visibility.

No retrieved text, technical connector access, or role label can transfer authority by itself.

## 4. Why a new Agent OS workstream is lawful

`config/mastermind_programs.yml` already contains the project-scoped semantic program `cross-repo-contract-governance`, lifecycle `building`, with Macro as implementation owner and Terminal/Portfolio as consumers. Current Agent OS has no workstream with the corresponding identity.

Therefore one workstream is required for durable cross-session execution state:

`WS:CROSS-REPO-CONTRACT-GOVERNANCE`

This is not a new semantic program and not a runtime. Agent OS remains knowledge-only and cannot dispatch, claim, lease, schedule, retry, gate, rank, or determine worker liveness.

## 5. Contract ledger law

Every material seam must eventually have one ledger row with all of these fields grounded in implementation/receipts:

1. producer;
2. canonical owner;
3. actual consumer;
4. schema identity;
5. version / compatibility floor;
6. source clock (`observed_at`, `as_of`, `known_at`, or the producer-native equivalent);
7. import/publication clock;
8. null / missing / unknown behavior;
9. correction / replacement / replay behavior;
10. auth and privacy boundary;
11. authority transfer, including explicit `none`;
12. fallback / last-good semantics;
13. deployment identity and proof;
14. actual product/machine consumer;
15. capability state using the company vocabulary.

Allowed capability states are exactly:

`PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, `BROKEN`, `SPEC_ONLY`, `NOT_BUILT`, `REJECTED_BY_DESIGN`.

No average status is allowed to hide a broken sub-contract.

## 6. Federated contract architecture

The governing pattern is:

`producer-owned meaning/schema -> consumer conformance/version pin -> existing transport -> import/publication receipt -> actual consumer proof`

Governance records and tests this relationship. Governance does not sit in the traffic path.

Where a producer already owns a formal schema/contract, extend that owner. Where a consumer must normalize presentation fields, keep the normalization local but test it against producer-owned fixtures. Where two languages implement the same vocabulary, generate digest-pinned golden vectors/fixtures from the canonical producer contract rather than hand-maintaining two semantic definitions.

The DeepVue `workspace_layout.v1` Macro/Terminal pattern is the positive precedent: frozen owner contract, byte-identical fixtures/digest, consumer validator, real persistence/consumer, no second store.

## 7. No-rebuild boundary

The following are explicitly rejected:

- Contract Governance service/microservice;
- cross-repo traffic proxy or gateway owned by this program;
- release/merge gate owned by this program;
- central lifecycle or contract-status database;
- queue, scheduler, worker registry, retry engine, cursor DB, or watcher DB;
- second semantic registry beside `config/mastermind_programs.yml`;
- second Agent OS or Executive OS;
- duplicate auth, identity, evidence, event, graph, publication, portfolio, or correction authority;
- one generic "Contract Bus" introduced because existing transports differ;
- direct Terminal -> Portfolio integration without a concrete user/machine job and a new Sol ruling.

Direct Terminal -> Portfolio is `REJECTED_BY_DESIGN` under this freeze. Terminal Conviction Book, Macro descriptive portfolio context, and Mastermind autonomous paper books are distinct semantic objects; name similarity is not a bridge.

## 8. Current critical seam rulings

### CRG-01 Neural Web authority — P0 / BROKEN

Macro's current producer source states that all five Neural Web -> Portfolio authority booleans are false and every field is context-only. Portfolio must never activate candidacy, shrink, vote, rank, gate, size, or another stronger effect solely from consumer defaults.

Contract law: effective authority can never exceed the intersection of producer-stamped authority and the consumer's explicit governance map. Missing, malformed, stale, or unknown authority is inert.

### CRG-02 Macro imported-state identity in Portfolio — P0 / PARTIAL

Portfolio currently consumes Macro through a managed checkout/symlink plus published artifacts. Transport location is not imported-state identity.

Every production Portfolio run that uses Macro must become attributable to the exact resolved Macro revision/object generation, contract generation, producer/source clock, import mode, and correction/replay identity using existing run/receipt owners. No new database is authorized.

### CRG-03 Portfolio -> Macro publication ownership — P0 / BROKEN

Portfolio currently contains code that resolves the Macro checkout, writes cross-repo artifacts into it, stages them, commits, rebases, and pushes Macro `main`. This violates clean producer/publication ownership even where the payload itself is safe.

The target is an existing owner-native publication/object/API lane after archaeology proves the correct owner. Portfolio publishes; Macro ingests/reads. Neither side impersonates the other's normal source checkout. If no current lawful lane exists, Fable returns to Sol; it does not invent a new bus.

The `data/mastermind/key_events.jsonl` projection requires a closed field/value publication contract before it is treated as safe merely because it is filtered by age/count.

### CRG-04 Prophet -> Portfolio — P1 / BUILT_NOT_PROVEN

The current Portfolio `portfolio/prophet_feed.py` is real and has real consumers. The stale claim that the adapter is absent is rejected.

The remaining gap is formal registration of `prophet.index/v1`, consumer modules, clocks, stale/null/correction semantics, authority, imported identity, and genuine current production proof.

Do not rebuild the adapter.

### CRG-05 Macro washout -> Terminal admission — P1 / BROKEN

The transport currently describes the washout bridge as display-only while Terminal code consumes the state in a fenced admission path. The contract must distinguish:

- Macro ownership of washout evidence/state;
- Terminal ownership of the explicitly ratified deterministic admission consequence;
- zero transfer of broader signal, rank, sizing, or trading authority.

False display-only prose must not survive once the real consumer is decision-bearing.

### CRG-06 Terminal bridge conformance/freshness receipts — P1 / PARTIAL

Older live Macro -> Terminal bridges such as `intel/v1`, market risk, opportunity timeline, and washout carry important wire semantics inside ingest implementation/tests rather than one producer-owned formal contract package.

Preserve last-good serving where product law requires it, but every import must expose enough receipt truth that a stopped producer/import cannot look healthy merely because old bytes remain readable.

### CRG-07 shared vocabularies/routes — P2 / PARTIAL

Tier/status vocabulary and options/Prophet source routing are independently hand-maintained in multiple implementations. The target is generated conformance fixtures/route descriptors from canonical producers, not a runtime registry service.

### CRG-08 reverse snapshot/feedback correction proof — P2 / PARTIAL

`mastermind_snapshot.v1` and `mastermind_nw_feedback.v3` remain valid product contracts unless a later incompatible change requires versioning. After publication ownership is repaired, prove success, stale last-good, publication failure, correction, and privacy through the real path.

## 9. Program sequence

### R0 — durable home and architecture freeze

Create the one Agent OS workstream, this design, a no-runtime/federated decision, a current-state census, a R0 implementation plan, and a Fable principal handoff. R0 is records/research only and creates no Executive Job.

### R1 — P0 authority and identity

Close CRG-01, CRG-02, and the ownership architecture/first vertical of CRG-03. These precede lower-risk contract cleanup because a perfectly versioned feed is still unsafe if authority or imported identity is wrong.

### R2 — high-value real consumers

Contract and prove Prophet, washout, intel, risk, opportunity, then other material live bridges as bounded producer + contract + consumer verticals.

### R3 — shared semantic consolidation

Generate Portfolio consumer manifest inputs from current producer truth plus explicit consumer overrides; produce shared tier/status fixtures and route/schema/freshness descriptors.

### R4 — reverse publication completion

Finish migration away from direct cross-repo Git working-tree mutation, one artifact family at a time, while preserving the existing real Macro consumers.

### R5 — production dossier

For every material seam preserve one exact-head/current-release production receipt:

`producer revision/generation -> schema/version -> source clock -> publication attempt/result -> consumer/import revision -> imported_at -> stale/null/error -> correction identity -> actual consumer -> authority effect -> auth/privacy result`.

CI, fixtures, merge, Slack delivery, and QUEUED admission are not production proof.

### R6 — semantic/Agent OS closeout

Reconcile the semantic registry/system map and Agent OS only after canonical proof exists. Remove stale unresolved claims, preserve rejected-by-design boundaries, and leave exact next action recoverable from a cold session.

## 10. Fable principal operating model

After R0 architecture is durable, Fable is the preferred sustained cross-repository principal COO. Sol remains accountable CEO/architecture/final acceptance.

The principal program operation key is:

`crg-fable-principal-20260828-sol-001`

This key identifies the organizational commission. It is not a canonical Executive Job unless/until the approved Executive path returns an accepted intent/job receipt for the same logical operation.

Fable must:

- re-bootstrap the current protected Skillpack on pickup;
- re-pin all three repository heads;
- reconcile current Agent OS, relevant open PRs/branches, and the semantic parent;
- preserve one carrier per logical modifying operation;
- decompose work into bounded seam-specific verticals;
- require each child to declare producer/owner/consumer/schema/clocks/nulls/corrections/auth/privacy/authority/fallback/proof;
- keep code waves independently useful and avoid mega-branches;
- return to Sol for authority changes, new persistent systems, rights/commercial changes, ambiguous cross-owner conflicts, production acceptance, or architecture amendments.

No Slack message is execution proof. A Fable lane is `UNCLAIMED` until an approved runtime/session/PR carrier is actually claimed and evidenced.

## 11. Watcher and dialogue discipline

Any watcher is transport/attention behavior only. It owns no Job, Attempt, Worker, completion, retry, provider selection, or session identity.

For every watcher-enabled Fable/worker dialogue:

- initial envelope requires ACK of the exact operation and same-thread continuation;
- after every nonterminal `BLOCKED`, `DECISION_REQUEST`, or `RESULT`, Sol must issue an explicit continuation/ruling or an explicit terminal STOP boundary;
- after every nonterminal Sol return the worker must re-arm the available approved wait/watch path;
- if watch is unavailable, the worker returns a typed `WATCH_UNAVAILABLE` blocker rather than silently disappearing;
- on terminal acceptance/STOP, the child operation is terminal, work stops, temporary watcher is disarmed, and no next child is authorized;
- watcher shutdown failure is reported without reopening the terminal operation;
- a next independent child requires a new stable operation key, lawful carrier, fresh reconciliation, and explicit commission.

Silence is never terminal receipt.

## 12. Proof and acceptance law

A seam can be `PROVEN_LIVE` only when the exact claimed producer/consumer path has a genuine production receipt and actual consumer. Green CI, merge, a generated schema, Slack delivery, or a fixture proves less.

Every seam proof must test relevant negative states, including:

- missing producer;
- stale payload;
- unsupported version;
- null vs known-zero;
- correction/replacement;
- partial import/publication;
- authorization refusal;
- privacy boundary failure;
- fallback/last-good behavior;
- authority mismatch.

## 13. R0 completion boundary

R0 is complete only when the design, implementation plan, current-state census, Agent OS workstream, decision, and principal handoff are merged on Macro `main` after exact-head repository validation.

R0 completion does **not** mean:

- Fable has ACKed or begun work;
- any Executive Job exists;
- any seam defect is fixed;
- production proof exists;
- the semantic program is complete.

The exact post-R0 action is to establish one actual claimed Fable principal carrier under current runtime/transport law, then open the first bounded child `CRG-NW-AUTHORITY-V1` after a fresh collision check.
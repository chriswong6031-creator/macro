---
workstream: WS:STOCK-IDENTITY
operation_key: SI-W3AR-CENSUS-P2-PREREG-V1
parent_operation: SI-FABLE-COO-PROGRAM-20260828
wave: W3AR-CENSUS
repository: mastermindx-market-intelligence/macro
status: waiting_capacity
preferred_avenue: CTO Sol
receiver_binding_mode: CAPACITY_SELECTABLE
placement_state: WAITING_CAPACITY / needs_placement
why: >
  The source-law architecture is now Sol-frozen. Remaining work is bounded but technically
  demanding: exact family-method/source-input archaeology, deterministic clean-pool census,
  fail-closed eligibility projection and prereg mechanics. CTO Sol is preferred for the
  architecture-sensitive repository work; Terra is the economical second choice; Opus is
  an acceptable bounded fallback if Codex-backed capacity is unavailable.
why_not_fable: >
  Fable principal capacity is no longer required. Sol has adjudicated the principal ambiguity
  and frozen the two-clock/source-law boundary; the worker is not being asked to reconstruct
  strategy or choose scientific authority.
---

# W3AR Census / P2 Prereg — Bounded Execution Packet

## Observable mission

Produce an outcome-free, independently reviewed evidence packet proving whether the existing W2 replay/source substrate and still-untouched name pool can support a fresh PR-3 calibration epoch, and if so return a complete **unexecuted** P2 preregistration. Stop before any P2 membership is drawn or read.

Terminal recommendation is exactly one of `GO_P2_PREREG`, `NO_GO_CALIBRATION_RECOVERY`, or `BLOCKED_NEW_SOURCE_LAW`.

## Why it matters

W3A Attempt-1 cannot be repaired by rereading P1. The program can only continue lawfully if a genuinely fresh evidence epoch can be created from untouched names using the original registered historical replay methods without outcome leakage. This wave burns down that question without risking the blind arm or consuming the future P2 look.

## Authority / document precedence

Read in this order, always re-pinning current revisions at pickup:

1. current live Chairman instruction carried by Sol's deliberate receiver assignment;
2. current protected Mastermind Sol Skillpack + universal routing/dialogue laws;
3. `research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md`;
4. `research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md` and `data/stock_identity/expert_events/family_registry.json`;
5. `research/stock_identity/W3_FINAL_ARCHITECTURE_FREEZE_2026-08-27.md`;
6. `research/stock_identity/W3AR_CENSUS_P2_PREREG_CHARTER_2026-08-30.md`;
7. `DEC:SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY` as a **ratified Sol ruling**, not a hypothesis;
8. closed PR #6638 exact head `f0b265f82cc7066a4e8d0b87a8fd62a64dd10177` only as immutable negative/audit evidence. Never branch from or revive it.

If a newer source law materially collides, return the exact conflict before changing the question.

## Verified current state at commission authoring

- W0/W1/W2 accepted.
- W3A Attempt-1 #6638 is CLOSED UNMERGED and scientifically rejected.
- P1 is consumed/rejected for the PR-3 ruler constant family; no second look.
- Old bundled W3AR operation `SI-W3AR-REPLAY-ELIGIBILITY-P2-V1` is terminal/effect-NONE after Sol resolved its source-law question.
- W3B is HELD until Sol accepts a recovered ruler/support schema.
- W3S is independent and may run in parallel on its own carrier.
- Recovery records live on PR #6672; at authoring it had exact-head green CI/fences before this successor packet update and will require fresh exact-head validation after the new commits.
- Unauthorized W3S PR #6678 is CLOSED UNMERGED/inert and supplies no accepted scientific verdict.

Fresh pickup must re-check current Macro main, open Stock Identity/identity/delisting/replay PRs, and changed-path collisions.

## Sol-ratified source-law boundary

Historical replay eligibility and live/prospective availability are separate clocks.

Historical eligibility exists only through the exact W2-registered method and required PIT inputs. The closed basis vocabulary for this operation is:

- `LEDGER_COVERAGE`
- `PIT_RECOMPUTE`
- `LOCKED_SPEC_BACKCAST`
- `STORE_VINTAGE`
- `PRICE_REFERENCE`
- `PROSPECTIVE_ONLY`

Do not invent another basis type without returning to Sol.

Generic spec/code existence, actual deployment date, fire occurrence, first/last fire or event min/max never establish historical replay coverage. Ledger-only means ledger-only. Class-P means historical false. `spec_postdates_history=true` remains explicit on lawful backcasts. Live/Radar/W7 uses real deployment/known-at availability, not the retrospective clock.

## Exact scope

Expected read/implementation surface, only as needed:

- `engine/stock_identity/replay/**`
- current family registry / Stock Identity partition and universe manifests;
- existing canonical price/identity/source-owner readers required to establish input coverage;
- a bounded derived Stock Identity eligibility/census module or script if needed;
- `data/stock_identity/**` only for derived, recomputable census/spec artifacts — never another source-of-truth store;
- `research/stock_identity/**`, tests and Agent OS continuation records for this operation.

Protected/non-goal surfaces:

- no edits to Prophet, signal gate, Entry Radar ownership, Terminal internals or unrelated producers;
- no new market-data provider/source authority;
- no W3S implementation;
- no P2 draw;
- no W3B/Q1 fit read;
- no production authority change.

## Complete machine journey

1. Load current W2 family registry and exact registered method/era/spec metadata.
2. For each family, derive one lawful historical basis and required PIT input contract or fail it closed.
3. Build/derive source-input coverage by name/date/grain without looking at output fires to invent availability.
4. Load W1 universe + partition/design-touch membership only for exclusion/accounting.
5. Deterministically remove pilot/B, blind, P1, design-touched and unresolved identity/plane-contamination names.
6. Emit clean-pool count + canonical sorted-name hash, **not P2 membership**.
7. Produce family × era × grain source/input support counts and typed missing reasons, no localization metrics.
8. If feasible, produce a complete deterministic P2 draw/prereg spec without executing its seed/draw.
9. Independent reviewer attacks leakage, basis widening, Class-P history, hidden outcome reads, partition contamination and duplicate-plane creation.
10. Return one terminal recommendation to Sol and stop.

Degraded journey: if source coverage or clean pool is insufficient, return `NO_GO_CALIBRATION_RECOVERY`; if a genuinely new source-law/authority decision is necessary, return `BLOCKED_NEW_SOURCE_LAW`. Never loosen criteria to obtain GO.

## Data / identity / time / null / correction behavior

- Instrument identity, ticker reuse and corporate-action hygiene precede all coverage joins.
- Use only lawful adjusted planes for fingerprint/ruler-compatible geometry.
- Historical eligibility is nullable/fail-closed. Unknown input/source coverage is not measured zero.
- Required typed failure reasons must distinguish at least prospective-only, ledger-not-covered, source-vintage-unavailable, PIT-input-unavailable, identity-unresolved, price-plane-unavailable/contaminated and method-unsupported.
- Corrections to source/identity coverage must be recomputable from canonical owners; do not write a parallel correction ledger.
- Membership from P1/blind may be read solely to exclude names; no P1 constant/result or blind per-name outcome may be opened.

## Deterministic vs statistical vs model-generated

Primary outputs are deterministic. No statistical fit and no model-generated eligibility facts are required. LLM assistance has zero authority and cannot originate a source-coverage or family-method classification contrary to the registered artifacts.

## Failure states

Return to Sol rather than proceeding on:

- current W2/registry law no longer supports the Sol-frozen basis interpretation;
- a family requires a source or provider outside accepted owners;
- design-touch/partition exclusions cannot be reconstructed without opening protected outcomes;
- identity/ticker reuse makes the clean pool ambiguous;
- a proposed P2 size/draw rule would require outcome inspection;
- a parallel active carrier already owns overlapping Stock Identity replay/partition paths;
- any tool/code path incidentally opens P1 ruler results, blind outcomes or P2 membership.

## Ordered implementation sequence

1. Re-pin Skillpack, Macro main, current Stock Identity source blobs, open PRs and collision paths.
2. Freeze a machine-readable family-method table from W2/registry, with tests that ledger-only/Class-P cannot gain history.
3. Derive outcome-free source/input coverage and typed failures.
4. Derive clean-pool exclusion ledger/count/hash.
5. Produce family/era/grain support census.
6. Draft unexecuted P2 prereg/draw specification.
7. Run independent adversarial review and discriminating mutation tests.
8. Return to Sol; do not run P2.

## Acceptance tests / proof

At minimum prove that deliberate mutations fail:

- using event min/max as availability;
- backcasting `rebuy` beyond ledger coverage;
- backfilling a Class-P family;
- converting current code/spec existence into historical coverage;
- dropping `spec_postdates_history` from Class-B backcasts;
- allowing a P1/blind/pilot/design-touched name into the clean pool;
- reading a banned outcome/localization column in the census path;
- executing the P2 draw/seed from the prereg artifact;
- creating a second replay/availability authority store.

Hosted CI must be green on the exact returned head for any implementation. Green CI is not scientific acceptance; Sol reviews the evidence packet.

## Stop condition

STOP immediately after posting the complete return with exactly one of `GO_P2_PREREG`, `NO_GO_CALIBRATION_RECOVERY`, or `BLOCKED_NEW_SOURCE_LAW`. `GO_P2_PREREG` is not P2 execution authority.

## Continuation handoff to Sol

Return in the exact assigned carrier with:

- actual receiver identity/avenue and pickup/start/watch receipts;
- current Skillpack/main/source pins;
- branch/PR/exact head and changed paths;
- family-method table + basis/input receipts;
- clean-pool exclusion ledger/count/hash;
- family/era/grain support census;
- complete unexecuted P2 prereg if GO;
- independent reviewer findings;
- exact CI/tests;
- discovered source/identity conflicts;
- one terminal recommendation.

After any nonterminal BLOCKED/DECISION_REQUEST/RESULT requiring Sol action, keep/re-arm the exact-carrier continuation path. Sol will explicitly CONTINUE/REQUEST_REPAIR/STOP. Silence is never terminal.
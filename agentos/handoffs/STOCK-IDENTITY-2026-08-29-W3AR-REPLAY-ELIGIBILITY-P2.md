---
workstream: WS:STOCK-IDENTITY
session: sol/stock-identity-w3ar-recovery-20260829
model: codex
mission: >
  Commission SI-W3AR-REPLAY-ELIGIBILITY-P2-V1 to determine, without drawing or
  reading a new calibration partition, whether W2 supports a lawful retrospective
  replay-eligibility clock distinct from live availability and whether an untouched
  clean pool can support a fresh PR-3 calibration epoch.
state_before: >
  W0-W2 were accepted. W3A Attempt-1 PR #6638 was closed unmerged after its one-time
  P1 PR-3 seal was rejected for an unlawful availability population; P1 is consumed
  for that constant family. W3B was held and no lawful W3AR receiver was bound.
changed:
  - path: research/stock_identity/W3AR_REPLAY_ELIGIBILITY_P2_RECOVERY_CHARTER_2026-08-29.md
    what: >
      Freezes the upstream recovery question, two-clock hypothesis, outcome-free clean-pool
      census, P2 feasibility requirements, and STOP-before-draw law.
  - path: agentos/decisions/DEC-SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY.md
    what: >
      Records Sol's decision to validate historical replay eligibility separately from live
      availability rather than assume either the strict single-clock or blanket-history reading.
  - path: agentos/handoffs/STOCK-IDENTITY-2026-08-29-W3AR-REPLAY-ELIGIBILITY-P2.md
    what: >
      Creates the bounded W3AR commission/return packet and hard non-goals for a future lawful receiver.
prs: [6672]
verified:
  - claim: Old W3A Attempt-1 is terminal and cannot lawfully reread P1 for the PR-3 constant family.
    command: "gh pr view 6638 --repo mastermindx-market-intelligence/macro --json state,isDraft,mergedAt,headRefOid"
    result: "CLOSED, unmerged; exact failed-attempt head f0b265f82cc7066a4e8d0b87a8fd62a64dd10177."
  - claim: W2 source law distinguishes stored-ledger extraction, registered recomputation, Class-B locked-spec backcast, and Class-P prospective-only history.
    command: "open research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md and data/stock_identity/expert_events/family_registry.json"
    result: "The four provenance/replay classes are explicitly registered; Class P has no historical rows."
  - claim: The recovery packet itself draws no P2 membership and authorizes no P1/blind/outcome read.
    command: "open research/stock_identity/W3AR_REPLAY_ELIGIBILITY_P2_RECOVERY_CHARTER_2026-08-29.md"
    result: "Records-only charter; explicit STOP before any P2 draw/read and no P1/blind/outcome authority."
unverified:
  - claim: A lawful family-by-family two-clock interpretation leaves enough replay support for a nondegenerate fresh calibration epoch.
    what_would_verify: >
      A lawfully bound W3AR principal must perform the source-law audit, clean-pool hash/census,
      outcome-free coverage analysis, and independent adversarial review, then return one of the
      three frozen terminal recommendations before any P2 draw.
decisions:
  - DEC:SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY
unresolved:
  - W3AR still requires a lawful receiver-assignment edge; current state is WAITING_CAPACITY / needs_placement.
  - The two-clock source-law interpretation is a hypothesis to validate, not an accepted family-eligibility result.
  - No P2 sample/draw law may be accepted until the outcome-free feasibility packet returns to Sol.
next_actions:
  - Bind one eligible principal through an authorized placement/commissioning edge; do not infer assignment from Secretary attention transport.
  - Re-pin current Skillpack/Macro/source owners and execute only the read-only/source-law feasibility audit first.
  - Return DECISION_REQUEST SI-W3AR-REPLAY-ELIGIBILITY-P2-V1 with exactly GO_P2_PREREG, NO_GO_CALIBRATION_RECOVERY, or BLOCKED_NEW_SOURCE_LAW; stop before P2 draw.
do_not_redo:
  - Do not revive PR #6638 or reread/reseal/overwrite/relabel its P1 Attempt-1 evidence.
  - Do not use fire occurrence/event min-max as historical availability evidence.
  - Do not backfill Class-P families or create a second replay/availability/evidence/data plane.
  - Do not open W3B, Q1, or Prophet authority from this commission.
danger_areas:
  - P1 and the blind arm are protected evidence partitions; even per-name inspection can contaminate the recovery design.
  - Historical research replay eligibility must never be exported as historical live deployment availability.
  - Generic spec existence is integrity/provenance metadata, not date-specific reconstructibility proof.
  - Receiver attention/ACK without a lawful commissioning edge is not lifecycle authority.
ended_because: blocked
---

# W3AR — Replay Eligibility / Fresh P2 Feasibility

**Operation:** `SI-W3AR-REPLAY-ELIGIBILITY-P2-V1`  
**Parent:** `SI-FABLE-COO-PROGRAM-20260828`  
**Current operational state:** `WAITING_CAPACITY / needs_placement`. Any attention-only or invalid-placement session must stand down with effect NONE; this packet remains the bounded commission for a later lawfully assigned receiver.

## Observable mission

Determine, without drawing or reading a new calibration partition, whether the original W2 historical replay law supports a clean retrospective replay-eligibility clock distinct from live availability and whether the still-untouched name pool can support a lawful fresh PR-3 calibration epoch. Return a preregistration-ready GO or a scientific NO-GO.

## Why this matters

W3A Attempt-1 failed because P1 was consumed under an unlawful eligibility population and cannot be reread. The implementation failure does not by itself falsify Stock Identity's research thesis. A lawful restart requires a new evidence basis, not a retry. This wave decides whether that basis exists before another name is design-touched.

## Authority / precedence

1. Current Chairman intent: recover and finish Stock Identity end to end.
2. Current protected Sol Skillpack at pickup; re-pin fresh.
3. `research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md` — original frozen research contract.
4. `research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md` + `data/stock_identity/expert_events/family_registry.json` — historical replay/family truth.
5. `research/stock_identity/W3AR_REPLAY_ELIGIBILITY_P2_RECOVERY_CHARTER_2026-08-29.md`.
6. `DEC:SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY` as a recovery hypothesis to validate, not a license to widen history.
7. Closed failed carrier PR #6638 exact head `f0b265f82cc7066a4e8d0b87a8fd62a64dd10177` as immutable negative evidence only.

If newer source law collides, stop and return the exact conflict before changing the question.

## Verified current state

- W0/W1/W2 accepted.
- PR #6529 architecture merged at `2b5473dad21491a3cd6225f97ad90adeedba5d56`.
- W3A Attempt-1 PR #6638 is CLOSED UNMERGED; its P1 constants are rejected and P1 is consumed for this constant family.
- The availability repair itself established 0/14 null-bound R/B families with date-specific historical deployment/source-era evidence under the stricter interpretation.
- W1 documented universe: 2,781 names; blind arm 229, P1 759; documented arithmetic leaves roughly 1.77k names outside pilot+blind+P1 before later design-touch exclusions. Exact clean pool must be recomputed and hashed; do not rely on the arithmetic as membership truth.
- W3B held; W3S may proceed independently once lawfully placed.

## Exact scope

Repository: `mastermindx-market-intelligence/macro`.

Read current owners and build only records/research/diagnostic audit artifacts needed for this feasibility decision. Expected areas:

- `research/stock_identity/`
- `agentos/` records for the return
- read-only `engine/stock_identity/replay/**`, W1 partition artifacts and W2 family registry
- optional new **outcome-free diagnostic script/tests** under `scripts/stock_identity_*` / `tests/test_stock_identity_*` only if needed to mechanically reproduce coverage counts; such code must read no P1 result constants, blind per-name evidence or outcome columns.

Do not modify the closed #6638 branch. Do not implement P2 calibration or W3B.

## Explicit non-goals

- no P2 draw or membership reveal;
- no P1 re-read, re-seal, overwrite or reinterpretation;
- no blind-arm per-name read;
- no localization/composite/outcome/fit/rank table;
- no expert selection or `DNR:KILL-OUTCOME-AUDITION` reopening;
- no Class-P backfill;
- no new event/replay/availability/evidence/data/identity/watch/control plane;
- no Prophet/rank/gate/size/trade authority;
- no fixing unrelated Caddy/Linear CI estate failures from #6638.

## Method

This wave is deterministic source-law archaeology + outcome-free coverage census, not a statistical fit.

For every registered family, produce one row with:

- provenance class R/B/P;
- ledger-only vs registered recompute vs locked-spec backcast;
- exact registered producer/method;
- required PIT inputs and their owner;
- historical replay-eligibility rule that does not inspect whether the family fired;
- live/prospective availability rule;
- whether `spec_postdates_history` applies;
- earliest lawful replay support only when derivable from source/input coverage rather than event occurrence;
- reason code if replay eligibility is absent/unknown.

Then compute the clean-pool identity/hash and only **coverage/availability** counts by family × era × grain over that pool. Do not compute ruler metrics.

## Key adjudication test

The audit must explicitly answer whether the prior strict Sol rule accidentally conflated deployment availability with the W2-registered retrospective replay construction.

A lawful retrospective rule may exist only if it follows the already-registered W2 method and PIT inputs. Examples:

- a Class-B locked-spec backcast can be replay-eligible historically if W2 registered that backcast and the required price/context inputs exist, while remaining `spec_postdates_history=true` and never implying live deployment;
- a ledger-only family cannot become historically eligible before the ledger merely because a spec exists;
- a registered recompute arm may extend history only as far as its required PIT inputs and causality fixtures support;
- Class P remains false for all historical dates.

Unknown = unavailable/UNESTIMABLE. Fire min/max is not an availability clock.

## Clean-pool law

Exclude from candidate P2 feasibility:

- all pilot/exemplar names;
- W1-A1 `B` / any later explicitly design-touched name;
- all 229 blind-arm names;
- all 759 P1 names;
- any name individually inspected or used to tune W3 Attempt-1 beyond the frozen pilot/P1 scopes, if discovered.

Return exact count + SHA256 over canonical sorted membership. Do not draw P2.

## Feasibility / power-before-draw

Return enough outcome-free information for Sol to decide whether a P2 can be preregistered without wasting another sealed look:

- coverage under lawful replay eligibility by family/era/grain;
- whether the fixed A2/B1 constant functions would have a mathematically defined input population, without evaluating their values;
- candidate P2 sample-size rule and deterministic seed derivation chosen without memberships/outcomes;
- number of clean names that would remain outside P2 for later grading;
- expected exclusion impact from P1+P2+pilot+blind separation.

Do not calculate P2 constants or inspect P1 constants to choose the proposal.

## Failure states

- `NO_GO_CALIBRATION_RECOVERY`: lawful replay support is too sparse/undefined to justify a fresh epoch.
- `BLOCKED_NEW_SOURCE_LAW`: recovery needs data/source authority not already owned by W2/current owners.
- `SOURCE_LAW_CONFLICT`: newer accepted law contradicts the two-clock interpretation.
- `CONTAMINATED_CLEAN_POOL`: no sufficiently untouched population remains.
- `WATCH_UNAVAILABLE`: COO cannot maintain the agreed return loop.

All are valid returns; none authorizes a workaround.

## Acceptance tests / proof

The return must include:

1. current Skillpack + Macro main pins;
2. exact family-by-family law table with source citations;
3. grep/code proof that no outcome/localization columns enter eligibility/census;
4. exact clean-pool count/hash and exclusion receipt;
5. no-P1/no-blind access proof for any diagnostic script;
6. independent adversarial review focused on outcome leakage, Class-P backfill, source-law widening and hidden second-plane creation;
7. current changed-path/open-PR collision census;
8. one terminal recommendation only: `GO_P2_PREREG`, `NO_GO_CALIBRATION_RECOVERY`, or `BLOCKED_NEW_SOURCE_LAW`.

## Stop condition

STOP before any P2 draw/read. Post `DECISION_REQUEST SI-W3AR-REPLAY-ELIGIBILITY-P2-V1` in the W3AR Slack child thread with exact branch/PR/head and the full evidence packet, then arm the exact-thread temporary watcher. Sol alone decides whether a P2 preregistration wave opens.

## Continuation

This child is fresh and must use its own GitHub carrier. Do not revive `SI-W3A-RULER-V1` / PR #6638. Fable is preferred because the work is architecture/science recovery; any mechanical census subtask may be delegated to Terra/Codex once the rules are explicit.

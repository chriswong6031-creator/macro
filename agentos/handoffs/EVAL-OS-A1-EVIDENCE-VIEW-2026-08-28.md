---
workstream: "WS:EVAL-OS-EVIDENCE-VIEW"
session: sol/eval-os-a1-evidence-view-20260828
model: sol
ended_because: complete
mission: >
  Commission A1 so the existing Intelligence OS admin surface answers, per canonical T1 engine,
  whether evidence is Validated, Accruing, Ungraded by design, Degraded, or Disproven, plus one
  global CEO view ranked by evidence strength, using only existing canonical evidence owners and
  persisting no new score/control state.
state_before: >
  T1 is the canonical engine registry. H1/T4 is PROVEN_LIVE on the deployed authenticated admin
  path. E1 is still accruing real stock/thematic evidence clocks. T7/T8 remain NOT_BUILT. The
  recovery freeze authorizes A1 after H1 and allows incomplete E1 accrual to appear honestly.
changed:
  - path: agentos/workstreams/WS-EVAL-OS-EVIDENCE-VIEW.md
    what: "Opened the dedicated organizational parent for A1."
  - path: agentos/handoffs/EVAL-OS-A1-EVIDENCE-VIEW-2026-08-28.md
    what: "Created the bounded implementation/proof packet."
verified:
  - claim: "H1 is terminal PROVEN_LIVE and explicitly unlocks A1."
    command: "Read current WS:EVAL-OS-OUTPUT-HEALTH and the merged recovery freeze."
    result: "PASS."
  - claim: "No named open competing Intelligence OS/evidence-scorecard implementation PR was found at commission time."
    command: "Search current open Macro PRs for intelligence_os/output-health/evidence-scorecard terms."
    result: "PASS — none returned."
  - claim: "E1 remains independent and nonterminal."
    command: "Read current E1 thread and current main clock receipts."
    result: "PASS — stock_desk/thematic_desk general clock receipts still absent on main."
unverified:
  - claim: "Exact smallest implementation seam for all evidence classes."
    what_would_verify: "Fresh operator archaeology over admin/intelligence_os.py, T1 registry, T4 health, qledger readiness/track record and owner-native evidence providers."
  - claim: "Real deployed admin surface can render the full A1 answer without a bounded API schema extension."
    what_would_verify: "Implementation + authenticated production proof."
unresolved:
  - "Exact deterministic evidence-classification function and evidence-provider mapping per T1 output_class."
  - "Whether a new pure derived module is cleaner than keeping derivation inside admin/intelligence_os.py; either is allowed only if it creates no persisted score state."
next_actions:
  - "Operator re-pins Skillpack/main and performs collision + exact evidence-provider archaeology."
  - "Build the smallest derived scorecard/global-view contract, RED-first, extending the existing admin page/API."
  - "Return exact head, changed files, CI, real authenticated production proof and negative proof of no new score store/authority."
do_not_redo:
  - "Do not reopen H1/T4 or create another health monitor/store."
  - "Do not create a second engine registry, evidence/score DB, promotion service, generated score artifact, admin product or work queue."
  - "Do not block on E1; represent incomplete accrual as incomplete/accruing evidence."
  - "Do not rank by raw performance. Rank evidence strength and legality."
danger_areas:
  - "Mixed clock bases may not pool."
  - "Null output_class must remain null."
  - "Validated may be empty."
  - "Qledger readiness does not grant promotion authority."
---

# Eval OS A1 — T7 per-engine evidence scorecards + T8 CEO evidence view

**Operation key:** `eval-os-a1-evidence-view-20260828-sol-001`  
**Organizational parent:** `WS:EVAL-OS-EVIDENCE-VIEW`  
**Architecture authority:** merged `research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md`  
**Skillpack at commission:** `mastermindx-market-intelligence/Mastermind@c4c39423f595cfe669961b871405eb2b13ff65c2`, v1.0.1  
**Macro commission base:** `60f239478b06cea2fe1704ea47a4af1227647b45`  
**Preferred avenue:** Terra — bounded single-repo implementation with frozen architecture; Fable is unnecessary scarcity for this wave.  

## Observable mission

On the real authenticated Intelligence OS admin surface, an operator can inspect every T1 engine
and see one truthful evidence disposition — `Validated`, `Accruing`, `Ungraded by design`,
`Degraded`, or `Disproven` — with the underlying evidence/ruler/basis visible, and can inspect a
global CEO view ordered by evidence strength. Empty `Validated` is a valid result.

## Why it matters

T4 tells us whether outputs are operationally healthy; it does not answer whether an engine has
lawful forward evidence strong enough to support a claim. A1 supplies that human answer layer
without creating another measurement or authority plane.

## Authority / precedence

1. current Chairman directive and current protected Sol Skillpack;
2. merged Eval OS recovery freeze / no-rebuild law;
3. current T1 engine registry contract;
4. current H1-proven T4 health contract;
5. qledger/owner-native evidence contracts and current promotion legality law;
6. this A1 packet.

If current main or an accepted owner law changes a material evidence/clock/authority contract,
stop and return `DECISION_REQUEST`; do not invent a local substitute.

## Exact scope

Expected implementation surface is the existing read-only Intelligence OS admin path and a pure
derivation helper if useful. Likely reads: T1 `output_class`; T4 health; qledger track record,
readiness and lawful clock/basis metadata; owner-native evidence where T1 declares a non-qledger
class. Expected writes are bounded to admin/derivation/tests plus this workstream/handoff.

## Explicit non-goals

No new score/evidence database, generated score artifact, monitor, engine registry, qledger copy,
promotion authority, admin product, queue or routing layer. No T9 fleet enrollment. No P1 promotion
mutation suite. No T2/T5/T6/T10/T11/T12 implementation.

## Complete user journey

1. Authenticated operator opens existing Intelligence OS page/API.
2. T1 resolves the canonical engine/output identity and `output_class`.
3. T4 supplies operational health/blindness without becoming performance evidence.
4. A1 reads the existing lawful evidence owner for that output class and derives its evidence
   disposition plus why it can/cannot claim yet.
5. Per-engine drilldown exposes sample/maturity/ruler/basis/coverage/health sufficient to audit the
   disposition without pooling illegal clock bases.
6. Global view groups/orders engines by evidence strength, with empty/null/degraded states given
   equal visual weight to positive states.
7. Missing/ambiguous evidence is explicit, never coerced to zero/neutral/Validated.

## Data / contract / time / null / correction law

Evidence identity preserves horizon value/unit, market calendar, clock basis, maturity and governed
control policy. Legacy and explicit bases never pool; different explicit market/unit bases never
pool. `output_class=null` stays unclassified/null. `Ungraded by design` must be evidence-backed by
output semantics, not used as a catch-all for missing data. Corrections are derived from current
canonical evidence stores; A1 persists no competing score history.

## Method law

Classification and ordering are deterministic. Models generate no evidence class, score or
promotion authority. Any owner-native statistical result remains labeled with its own contract and
uncertainty; A1 only maps accepted evidence into the frozen answer categories.

## Failure states

Fail closed or show explicit incomplete state on unknown output class, missing owner, mixed bases,
clock ambiguity, immature sample, stale/unavailable health, missing coverage, unresolved control,
owner disagreement or unsupported evidence category. Never make UI neatness override truth.

## Ordered implementation

1. Re-pin current Skillpack and Macro main; collision census exact paths.
2. Census T1 output classes and existing evidence-provider/read APIs; write the mapping before code.
3. Freeze a minimal derived `evidence_status` contract with reason/evidence refs and no numeric magic score.
4. RED-first tests for empty Validated, null output_class, mixed-basis refusal, immature Accruing,
   health-degraded evidence, explicit ungraded-by-design and disproven evidence.
5. Implement pure derivation and extend existing admin API/page.
6. Test current real estate locally/in integration; no generated state.
7. Independent review on exact head.
8. Prove authenticated `admin.mastermind-x.com` on the deployed release, including at least one
   empty/null/degraded/incomplete case and negative proof of no persisted score store.

## Acceptance / stop

Stop at A1. Completion requires exact-head tests/CI, independent review, authenticated production
browser/API proof, truthful categories and zero duplicate authority/store. A merged library or green
CI without real admin proof is `BUILT_NOT_PROVEN`, not done. Return to Sol with exact SHA/files/CI,
proof receipts, current capability ledger delta, blockers/discoveries and explicit watcher state.

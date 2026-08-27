---
workstream: "WS:GMI-THEME-GRAPH"
session: sol/gmi-d2e-acceptance-commission-20260827
model: sol
ended_because: complete
mission: >
  Freeze the dependency-held D2E acceptance wave that closes D2 only after D2C PIT
  and D2D ontology/probation are accepted, including rights, coverage, D2B3 natural
  proof reconciliation, strict graph guards and a natural production receipt.
state_before: >
  D2E was never implemented. D2B3 implementation exists but a dedicated later Agent
  OS acceptance record was not found; D2C/D2D remain missing and are hard predecessors.
changed:
  - path: agentos/handoffs/GMI-THEME-GRAPH-2026-08-27-d2e-acceptance-commission.md
    what: "Created the held D2 closeout/acceptance packet."
verified:
  - claim: "D2E cannot start before D2C+D2D."
    command: "Completion freeze + D2 gate law"
    result: "PASS."
  - claim: "D2B3 current natural behavior warrants reconciliation, not blind reimplementation."
    command: "Current graph receipt + PR #6232 completion law"
    result: "PASS; acceptance itself remains unpromoted here."
unverified:
  - claim: "All user-display rights questions needed by later W6 are resolved."
    what_would_verify: "D2E source-family rights census and current registry decisions."
unresolved:
  - "DEPENDENCY_HELD until D2C+D2D are canonical accepted."
next_actions:
  - "Do not claim until both D2C and D2D accepted receipts are on canonical main/Agent OS."
  - "On claim, refresh all D2 predecessor evidence and current natural graph generation before judging anything."
do_not_redo:
  - "Do not reimplement D2A/D2B/D2C/D2D inside acceptance."
  - "Do not wave through missing rights, PIT, identity or coverage evidence because CI is green."
  - "Do not start W3B in the same carrier."
danger_areas:
  - "Marking D2B3 PROVEN_LIVE from current behavior without checking every frozen completion clause."
  - "Treating internal rights as public-display rights."
---

# D2E — Rights, Coverage & D2 Acceptance · held principal-review commission

**Operation key:** `gmi-theme-accept-d2e-20260827-sol-001`  
**State at mint:** `DEPENDENCY_HELD`  
**Depends on:** accepted D2C + D2D

## Observable mission

Produce one canonical D2 acceptance packet answering, with receipts: Are identity, PIT, ontology/probation, rights and coverage now sufficiently complete and truthful for GMI W3B to construct ThemeState? If yes, close D2 and release W3B. If no, return the smallest typed predecessor defect and keep W3B held.

## Why it matters

D2E is the firewall between a live semantic graph and market-state computation. It prevents W3B from turning incomplete identity, lookahead membership, illegal display rights or sparse/unreviewed mappings into apparently authoritative state.

## Authority / precedence

Current Chairman decision and completion freeze; D2 handoff gates; D2A/D2B frozen contracts/accepted evidence; D2C/D2D accepted returns; current `contracts/theme_graph/README.md`; current `config/theme_sources.yml`; Data OS identity authority; current DNR/rights/house law.

## Exact scope / non-goals

Read/reconcile all D2 evidence, run existing guards/censuses, make only bounded acceptance-repair changes proven necessary to the D2 acceptance harness/records. No new feature family, no new graph/state store, no ThemeState, no mapping expansion beyond fixing an acceptance defect routed back to its owner, no user product work.

## Complete machine journey

1. Load exact accepted predecessor SHAs/generations.
2. Re-run every D2 gate from fresh current data.
3. Verify D2B3 against its frozen completion clauses: lifecycle status, GOLD current-edge state, IBIT refusal/resurrection fence, identity sidecar non-regression and strict guard.
4. Compute closed denominators for identity, PIT vintage coverage, mapping/probation status and rights/source-family display tier.
5. Re-run classification/coverage/eligibility census for relevant U.S./China universes using current population definitions.
6. Run a natural nightly after all accepted predecessors are on main and prove the exact generation consumed them.
7. Emit PASS releasing W3B only if every required gate is satisfied; otherwise emit a typed hold pointing to the exact predecessor/owner.

## Data / time / null / correction law

Counts always carry denominator/population/as-of; unknown or rights-unresolved is not zero; reconstructed history is not observed proof; a current natural generation cannot back-prove older as-of behavior; correction-safe identity and append-only graph laws remain unchanged.

## Method

Deterministic audit/validation. No LLM decides acceptance, mapping, identity or rights. Models may summarize receipts only after verdict is mechanically grounded.

## Failure states

Any unresolved required identity class, PIT lookahead, unaccounted mapping denominator, source family without rights row, D2B3 completion clause not proven, strict contract red, natural nightly not consuming the intended main state, or source/Agent OS disagreement keeps D2 open.

## Ordered sequence / acceptance proof

1. Confirm D2C+D2D canonical acceptance and no overlapping open carrier.
2. Freeze exact audit pin/populations.
3. Execute D2A→D2D gate matrix and D2B3 clause check.
4. Run strict graph guards and all affected identity/PIT/ontology tests.
5. Run current coverage/eligibility census; preserve negative/unmapped/refusal categories.
6. Wait for/inspect the first ordinary natural nightly on the accepted predecessor main; manual/replay/CI is not the sole natural receipt.
7. Verify natural graph metadata, exact input ancestry and representative PIT/ontology reader queries.
8. Independent adversarial review attacks false-green rights, lookahead, denominator drift and stale receipts.
9. Record PASS or typed HOLD in Agent OS. PASS changes D2E to done and releases W3B; HOLD changes no downstream state.

## Stop condition / continuation

Stop at the D2 verdict. On PASS, emit exact release handoff for `gmi-theme-state-w3b-20260827-sol-001`; do not implement W3B in this carrier. On HOLD, return the smallest predecessor repair packet to its canonical owner. Sol attention is required only for an authority/source-law conflict or a final D2 acceptance dispute.

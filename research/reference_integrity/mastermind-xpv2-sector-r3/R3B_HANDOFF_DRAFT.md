# DRAFT — DO NOT START — XPV2-SC-R3B commission draft

**This file is a DRAFT for the commissioning session to review, edit, and
formally issue. It is NOT a live commission. Nobody should begin R3 visual
work off this file as written.** It exists so the next wave does not have to
reconstruct routing/scope decisions from scratch — everything binding is
already frozen in the sibling deliverables it points at.

---

## Working commission text (subject to commissioning-session edits)

**ROUTE**: orchestration (this wave needs a design/build sequence spanning
multiple sessions, not a single mechanical spawn) → seat runs the
`orchestrator` agent, either `model: 'fable'` + `FABLE-WHY: orchestration: R3
visual design spans creative judgment (palette/type/layout choices) and
multi-session sequencing that a single sonnet builder cannot safely own` per
the fable-spawn gate, OR `model: 'opus'` + the `fable-mode` skill if the
commissioning session judges this orchestration does not need frontier
judgment. That choice is the commissioning session's call, not this draft's.

**MISSION**: Produce the R3 visual reference for Sector Central (US) — the
six-view SI Workspace page (Overview/Map/Moving/Money/Explore/Confluence) —
bounded by every rule in `R3_DESIGN_BRIEF.md` and bound to the frozen
fixture at `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/`.

**DESIGN LANE ROUTING (CLAUDE.md §Model routing, unchanged by this draft)**:
the actual palette/type/layout/copy choices are judgment work and route to
`designer` (opus-pinned, auto-loads the frontend-design skill + DESIGN_DOCTRINE.md)
— NOT to a sonnet `builder`. A `builder` may only implement a fully specified
design (exact markup/CSS already pinned) once the designer has produced one.
Flagship-surface taste-as-deliverable work (a new visual language, a hero
treatment) that fails the draft-and-review test may warrant the fable
orchestrator gate directly per CLAUDE.md's Design lane — the orchestrator
seat should make that call explicitly and name it.

**ACCEPTANCE GATES — inline, "not done unless" (spawn-handoff law, CLAUDE.md)**:

1. Fresh end-to-end happy path with zero manual workarounds for all six
   views, driven against `fixture/` (never live `site/`/`data/` — the
   fixture is frozen specifically so this is reproducible).
2. Per-step visual crops vs the `R3_DESIGN_BRIEF.md` §9 evidence matrix:
   18 view/theme screenshots (6 views × light/dark/zh) minimum, posted in
   the PR body — not merely claimed.
3. Hash-routing proof per `R3_DESIGN_BRIEF.md` §9 item 2 (canonical hashes,
   legacy anchors, `#theme-*` boot redirect, `#read-*` trace, unknown/empty
   fallback).
4. Access-state proof against the fixture's three access states (ungated,
   gated-shell, hydrated) — never against a live fetch.
5. 200% zoom pass on Overview and Confluence.
6. Two new accessible-equivalent surfaces (sector-cycle clock chart,
   market-heat treemap) per `R3_DESIGN_BRIEF.md` §6, each with its own
   evidence crop.
7. A written capability cross-check against `capability_disposition_ledger.md`
   — every RETAIN row's journey demonstrated present in the new build, row
   by row, not summarized as "looks complete."
8. Entry points actually wired — every legacy anchor and canonical hash
   from `routing_contract.md` must resolve inside the new build, not just
   in isolated component previews.

**REFERENCE IMAGES**: if the commissioning session has existing reference
shots (the rejected R2 mockup screenshots, prior Sector Central captures,
competitor benchmarks), they must be committed as files under
`mockups/refs/xpv2-sc-r3/` with paths named explicitly in the final
commission — never handed off as prose descriptions. This draft does not
have any reference images to point at; the commissioning session must supply
them or explicitly note none exist.

**NO CHILD-AGENT SELF-MERGE ON FIRST PASS** (spawn-handoff law): the R3
builder/designer returns its PR + visual artifact to the commissioning
session. The commissioning session reviews it and completes the normal
squash-merge/live chain in the same task, unless the operator explicitly
requests a hold or a genuine check is red.

**OUT OF SCOPE for R3B** (carried forward from this pack, still binding):

- No repair of the recorded-not-repaired defects (A3 Map reco/context
  conflation, A6 Overview stale-guard fail-open, A7 routing seams) unless a
  new `ADJUDICATIONS.md`-style ruling explicitly authorizes it.
- No REMOVE or RELOCATE of any capability — the ledger's "nothing in this
  wave is REMOVE or RELOCATE" line still holds until a new ruling changes it.
- No invented correction/revision affordance or Baskets-tab thin-disclosure
  UI (both BLOCKED_DATA — no producer field backs either).
- No production template/engine/scripts changes beyond what is strictly
  needed to ship the new R3 markup itself — this draft does not authorize a
  data-layer rewrite.

**BOUND DELIVERABLES** (read all before starting, they are the frozen
spec for this wave too): `capability_disposition_ledger.md`,
`producer_binding_matrix.md`, `routing_contract.md`,
`access_hydration_contract.md`, `R3_DESIGN_BRIEF.md`, `fixture/` +
`fixture/PROVENANCE.md` + `fixture/receipts.json`.

---

## Open items the commissioning session must resolve before issuing this

- Confirm whether R3B should be one orchestrated wave or split per-view
  (six smaller commissions). This draft assumes one wave; splitting changes
  the acceptance-gate wording (per-view gates instead of one combined pass).
- Supply reference images (see above) or explicitly rule none are needed.
- Decide fable vs opus+fable-mode for the orchestrator seat (see ROUTE line)
  — this draft intentionally leaves that call unmade.
- Confirm the fixture capture (`4c55fe433490adfd75fd901ef25f5793db2202db`,
  2026-08-20) is still an acceptable freeze point, or commission a fresh
  capture if enough nightly runs have passed that the commissioning session
  wants R3 evidence against more current numbers (the fixture is frozen ON
  PURPOSE for reproducibility — refreshing it is a deliberate act, not a
  default).

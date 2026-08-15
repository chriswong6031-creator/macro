---
key: EVAL-OS-T4-ADMIN-SURFACE
question: >
  Where does the T4 output-health substrate become visible to the operator/CEO before T7's
  scorecard exists — and does exposing it early create a second registry or a new control
  surface?
answer: >
  T4 ships a read-only Intelligence OS page in the EXISTING admin console
  (admin.mastermind-x.com SPA): admin/intelligence_os.py derives the T1+T4 estate on demand
  (panel + per-engine drill-down), server.py gains two GET routes, the SPA gains one page
  cross-linked both ways with the Neural Web Observatory. No persisted admin state, no new
  registry, no POST routes, no authority: a Synapse-registered engine/output appears (and
  disappears) in the API/UI census with zero admin code edits; output_class renders only
  what the T1 overlay adjudicated (null shows as null, never guessed). T7/T8
  performance/CEO scoring remain out of scope.
rationale: >
  The health substrate is only trustworthy if someone can look at it; waiting for T7 leaves
  the contract invisible for a calendar-bound wave. The admin console already carries the
  Observatory (per-lobe view of the same estate), so the census surface belongs beside it —
  replacing or duplicating the Observatory would fork the operator's mental model. Derived
  on demand + fixture-reflectivity tests keep invariant I1 intact (knowledge plane, not
  control plane) and keep DNR:KILL-PARALLEL-KNOWLEDGE-BASE closed: the page is a VIEW over
  build_intelligence_registry.build() + resolve_output_health(), not a store.
alternatives:
  - option: defer all visibility to T7's scorecard
    why_not: >
      T7 is separately commissioned and calendar-sensitive; the health contract would ship
      dark, and the could_not_look observability findings (the census's main yield) would
      reach no eyes until then.
  - option: extend the Neural Web Observatory in place
    why_not: >
      The Observatory is scoped to NW lobes (132 artifacts) with NW-specific rollup
      conventions; the estate view spans 642 artifacts / 378 engines with a different unit
      of account. Folding them conflates the two scopes the whole Eval OS program exists to
      separate. Cross-links preserve navigation without the conflation.
  - option: a committed health JSON the admin serves statically
    why_not: >
      A committed generated artifact is the exact pattern T1 killed twice (scheduled
      fleet-wide reds; ~70 synapse commits/14d) and would create the self-monitoring fixed
      point §22 forbids.
evidence:
  - "CEO amendment 2026-08-14 (operator relay, mid-session): admin integration in scope; read-only; no new registry; fixture add/remove reflectivity; do not replace the Observatory; T7/T8 out of scope."
  - "tests/test_admin_intelligence_os.py: fixture add/remove reflectivity + no-persisted-state + output_class-never-guessed gates (PR carries the receipts)."
  - "admin scout brief 2026-08-14: update.sh admin restart regex covers admin/.* wholesale, so the new module deploys with no deploy-script edit."
affects:
  - "WS:EVAL-OS-OUTPUT-HEALTH"
  - qualitative-intelligence
  - admin/intelligence_os.py
  - admin/server.py
  - admin/static/app.js
confidence: high
reversibility: easy
decided_by: ceo-sol (relayed operator amendment; implementation shape coo-fable)
decided_at: 2026-08-14
---

The page is a window, not a lever: nothing in it gates, dispatches, or grants authority, and
its census must always be re-derivable from `config/synapse.yml` + the T1 overlay + the T4
resolver alone. If a future wave wants the page to ENFORCE anything (withhold an unavailable
output, route tiers), that belongs to T12/authority-routing with its own decision record —
not to this surface.
